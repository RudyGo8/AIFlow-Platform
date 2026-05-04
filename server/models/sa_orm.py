from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, BigInteger, SmallInteger, String, Text, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from utils.config import config


class SADeclarativeBase(DeclarativeBase):
    pass


class _DB:
    engine = None
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    initialized = False


def _db_url() -> str:
    db = config.database()
    if db.engine == "mysql":
        pwd = db.password.get_secret_value() if db.password else ""
        return f"mysql+aiomysql://{db.username}:{pwd}@{db.host}:{db.port}/{db.database}?charset={getattr(db, 'charset', 'utf8mb4')}"
    if db.engine == "postgresql":
        pwd = db.password.get_secret_value() if db.password else ""
        return f"postgresql+asyncpg://{db.username}:{pwd}@{db.host}:{db.port}/{db.database}"
    return f"sqlite+aiosqlite:///{db.database}"


async def init_orm() -> None:
    if _DB.initialized:
        return
    _DB.engine = create_async_engine(_db_url(), echo=bool(config.database().echo), pool_pre_ping=True)
    _DB.session_factory = async_sessionmaker(_DB.engine, expire_on_commit=False)
    _DB.initialized = True


async def close_orm() -> None:
    if _DB.engine is not None:
        await _DB.engine.dispose()
    _DB.engine = None
    _DB.session_factory = None
    _DB.initialized = False


class Q:
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self.op = "and"
        self.children: List[Q] = []

    def __or__(self, other: "Q") -> "Q":
        q = Q()
        q.op = "or"
        q.children = [self, other]
        return q

    def __and__(self, other: "Q") -> "Q":
        q = Q()
        q.op = "and"
        q.children = [self, other]
        return q


class Count:
    def __init__(self, field: str):
        self.field = field


class Sum:
    def __init__(self, field: str):
        self.field = field


def _build_expr(model: type["Model"], key: str, value: Any):
    if "__" in key:
        field, op = key.split("__", 1)
    else:
        field, op = key, "eq"
    try:
        col = getattr(model, field)
    except AttributeError:
        # FK field fallback: user_id -> user (FK column)
        if field.endswith("_id") and "_" not in field[:-3]:
            base = field[:-3]
            try:
                col = getattr(model, base)
            except AttributeError:
                raise AttributeError(f"type object '{model.__name__}' has no attribute '{field}' or '{base}'")
        else:
            raise
    if op == "eq":
        return col == value
    if op == "in":
        return col.in_(value)
    if op == "icontains":
        return col.ilike(f"%{value}%")
    if op == "gte":
        return col >= value
    if op == "lte":
        return col <= value
    if op == "gt":
        return col > value
    if op == "lt":
        return col < value
    if op == "range":
        return col.between(value[0], value[1])
    if op == "isnull":
        return col.is_(None) if value else col.isnot(None)
    return col == value


def _build_q(model: type["Model"], q: Q, joins: list = None):
    if q.children:
        parts = [_build_q(model, c, joins) for c in q.children]
        return or_(*parts) if q.op == "or" else and_(*parts)
    if q.kwargs:
        exprs = []
        for k, v in q.kwargs.items():
            if "__" in k and joins is not None:
                exprs.append(_build_expr_with_join_static(model, k, v, joins))
            else:
                exprs.append(_build_expr(model, k, v))
        return and_(*exprs)
    return None


def _build_expr_with_join_static(model, key, value, joins):
    """Build filter expression with FK join support, adding joins to the provided list."""
    parts = key.rsplit("__", 1)
    if len(parts) == 2 and parts[1] in ("in", "eq", "gte", "lte", "gt", "lt", "icontains", "contains", "range", "isnull"):
        field_path, op = parts
    else:
        field_path, op = key, "eq"

    col, needs_join = _resolve_fk_static(model, field_path, joins)
    if op == "eq": return col == value
    if op == "in": return col.in_(value)
    if op == "icontains": return col.ilike(f"%{value}%")
    if op == "gte": return col >= value
    if op == "lte": return col <= value
    if op == "gt": return col > value
    if op == "lt": return col < value
    if op == "range": return col.between(value[0], value[1])
    if op == "isnull": return col.is_(None) if value else col.isnot(None)
    return col == value


def _resolve_fk_static(model, src, joins):
    """Resolve FK paths and add joins to the provided list."""
    if "__" not in src:
        try:
            return getattr(model, src), False
        except AttributeError:
            if src.endswith("_id") and "_" not in src[:-3]:
                return getattr(model, src[:-3]), False
            raise

    parts = src.split("__")
    if len(parts) == 2 and parts[1] == "id":
        fk_col_name = f"{parts[0]}_id"
        if fk_col_name in model.__table__.columns:
            return model.__table__.columns[fk_col_name], False

    rel_attr = parts[0]
    col = getattr(model, rel_attr, None)
    if col is None:
        return getattr(model, src), False

    fk_info = col.info.get("_fk_model") if hasattr(col, "info") else None
    if fk_info is None:
        return getattr(model, src), False

    target_cls = Model._model_registry.get(fk_info)
    if target_cls is None:
        return getattr(model, src), False

    remaining = "__".join(parts[1:])
    if "__" in remaining:
        sub_parts = remaining.split("__", 1)
        sub_rel_attr = sub_parts[0]
        sub_col = getattr(target_cls, sub_rel_attr, None)
        if sub_col is None:
            return getattr(model, src), False
        sub_fk_info = sub_col.info.get("_fk_model") if hasattr(sub_col, "info") else None
        if sub_fk_info is None:
            return getattr(model, src), False
        sub_target_cls = Model._model_registry.get(sub_fk_info)
        if sub_target_cls is None:
            return getattr(model, src), False
        sub_remaining = sub_parts[1]
        target_col = getattr(sub_target_cls, sub_remaining, None)
        if target_col is None:
            return getattr(model, src), False
        # First join
        fk_col_name = f"{rel_attr}_id"
        fk_col = model.__table__.columns.get(fk_col_name)
        if fk_col is None:
            fk_col = model.__table__.columns.get(rel_attr)
        if fk_col is None:
            return getattr(model, src), False
        target_pk = target_cls.__table__.columns.get("id")
        if target_pk is None:
            return getattr(model, src), False
        jc1 = (fk_col == target_pk)
        t1 = target_cls.__tablename__
        if not any(t.__tablename__ == t1 for t, _ in joins):
            joins.append((target_cls, jc1))
        # Second join
        sub_fk_col_name = f"{sub_rel_attr}_id"
        sub_fk_col = target_cls.__table__.columns.get(sub_fk_col_name)
        if sub_fk_col is None:
            sub_fk_col = target_cls.__table__.columns.get(sub_rel_attr)
        if sub_fk_col is None:
            return getattr(model, src), False
        sub_target_pk = sub_target_cls.__table__.columns.get("id")
        if sub_target_pk is None:
            return getattr(model, src), False
        jc2 = (sub_fk_col == sub_target_pk)
        t2 = sub_target_cls.__tablename__
        if not any(t.__tablename__ == t2 for t, _ in joins):
            joins.append((sub_target_cls, jc2))
        return target_col, True
    else:
        target_col = getattr(target_cls, remaining, None)
        if target_col is None:
            return getattr(model, src), False
        fk_col_name = f"{rel_attr}_id"
        target_pk = target_cls.__table__.columns.get("id")
        if target_pk is None:
            return getattr(model, src), False
        fk_col = model.__table__.columns.get(fk_col_name)
        if fk_col is None:
            fk_col = model.__table__.columns.get(rel_attr)
        if fk_col is None:
            return getattr(model, src), False
        jc = (fk_col == target_pk)
        tn = target_cls.__tablename__
        if not any(t.__tablename__ == tn for t, _ in joins):
            joins.append((target_cls, jc))
        return target_col, True


class QuerySet:
    def __init__(self, model: type["Model"]):
        self.model = model
        self._filters = []
        self._exclude = []
        self._limit = None
        self._offset = None
        self._order = []
        self._aggregates: Dict[str, Any] = {}
        self._group_by: List[str] = []
        self._joins: List[Tuple[Any, Any]] = []

    def _resolve_fk(self, src: str):
        """Resolve a __-separated field path like 'department__name' to (column, needs_join).
        Returns (column_or_label, is_joined).
        - 'department__id' → use FK column 'department_id' directly (no join)
        - 'department__name' → join to department table and return name column
        """
        if "__" not in src:
            try:
                return getattr(self.model, src), False
            except AttributeError:
                if src.endswith("_id") and "_" not in src[:-3]:
                    return getattr(self.model, src[:-3]), False
                raise

        parts = src.split("__")
        if len(parts) == 2 and parts[1] == "id":
            fk_col_name = f"{parts[0]}_id"
            if fk_col_name in self.model.__table__.columns:
                return self.model.__table__.columns[fk_col_name], False

        rel_attr = parts[0]
        col = getattr(self.model, rel_attr, None)
        if col is None:
            return getattr(self.model, src), False

        fk_info = col.info.get("_fk_model") if hasattr(col, "info") else None
        if fk_info is None:
            return getattr(self.model, src), False

        target_cls = Model._model_registry.get(fk_info)
        if target_cls is None:
            return getattr(self.model, src), False

        remaining = "__".join(parts[1:])
        # Recursively resolve multi-level FK paths (e.g. user_id__department__name)
        if "__" in remaining:
            sub_parts = remaining.split("__", 1)
            sub_rel_attr = sub_parts[0]
            sub_col = getattr(target_cls, sub_rel_attr, None)
            if sub_col is None:
                return getattr(self.model, src), False
            sub_fk_info = sub_col.info.get("_fk_model") if hasattr(sub_col, "info") else None
            if sub_fk_info is None:
                return getattr(self.model, src), False
            sub_target_cls = Model._model_registry.get(sub_fk_info)
            if sub_target_cls is None:
                return getattr(self.model, src), False
            sub_remaining = sub_parts[1]
            target_col = getattr(sub_target_cls, sub_remaining, None)
            if target_col is None:
                return getattr(self.model, src), False
            # First join: self.model -> target_cls
            fk_col_name = f"{rel_attr}_id"
            fk_col = self.model.__table__.columns.get(fk_col_name)
            if fk_col is None:
                fk_col = self.model.__table__.columns.get(rel_attr)
            if fk_col is None:
                return getattr(self.model, src), False
            target_pk = target_cls.__table__.columns.get("id")
            if target_pk is None:
                return getattr(self.model, src), False
            join_condition1 = (fk_col == target_pk)
            target_table1 = target_cls.__tablename__
            if not any(t.__tablename__ == target_table1 for t, _ in self._joins):
                self._joins.append((target_cls, join_condition1))
            # Second join: target_cls -> sub_target_cls
            sub_fk_col_name = f"{sub_rel_attr}_id"
            sub_fk_col = target_cls.__table__.columns.get(sub_fk_col_name)
            if sub_fk_col is None:
                sub_fk_col = target_cls.__table__.columns.get(sub_rel_attr)
            if sub_fk_col is None:
                return getattr(self.model, src), False
            sub_target_pk = sub_target_cls.__table__.columns.get("id")
            if sub_target_pk is None:
                return getattr(self.model, src), False
            join_condition2 = (sub_fk_col == sub_target_pk)
            sub_target_table = sub_target_cls.__tablename__
            if not any(t.__tablename__ == sub_target_table for t, _ in self._joins):
                self._joins.append((sub_target_cls, join_condition2))
            return target_col, True
        else:
            target_col = getattr(target_cls, remaining, None)
            if target_col is None:
                return getattr(self.model, src), False

            fk_col_name = f"{rel_attr}_id"
            target_pk = target_cls.__table__.columns.get("id")
            if target_pk is None:
                return getattr(self.model, src), False

            fk_col = self.model.__table__.columns.get(fk_col_name)
            if fk_col is None:
                fk_col = self.model.__table__.columns.get(rel_attr)
            if fk_col is None:
                return getattr(self.model, src), False

            join_condition = (fk_col == target_pk)
            target_table = target_cls.__tablename__
            if not any(t.__tablename__ == target_table for t, _ in self._joins):
                self._joins.append((target_cls, join_condition))

            return target_col, True

    def _build_expr_with_join(self, key: str, value: Any):
        """Build filter expression supporting __ traversal for fk fields."""
        if "__" not in key:
            return _build_expr(self.model, key, value)

        parts = key.rsplit("__", 1)
        if len(parts) == 2 and parts[1] in ("in", "eq", "gte", "lte", "gt", "lt", "icontains", "contains", "range", "isnull"):
            field_path, op = parts
        else:
            field_path, op = key, "eq"

        col, is_joined = self._resolve_fk(field_path)
        if is_joined:
            if op == "eq":
                return col == value
            if op == "in":
                return col.in_(value)
            if op == "icontains":
                return col.ilike(f"%{value}%")
            if op == "gte":
                return col >= value
            if op == "lte":
                return col <= value
            if op == "gt":
                return col > value
            if op == "lt":
                return col < value
            if op == "range":
                return col.between(value[0], value[1])
            if op == "isnull":
                return col.is_(None) if value else col.isnot(None)
            return col == value
        return _build_expr(self.model, key, value)

    def filter(self, *args, **kwargs):
        for a in args:
            if isinstance(a, Q):
                e = _build_q(self.model, a, self._joins)
                if e is not None:
                    self._filters.append(e)
        for k, v in kwargs.items():
            if "__" in k:
                self._filters.append(self._build_expr_with_join(k, v))
            else:
                self._filters.append(_build_expr(self.model, k, v))
        return self

    def exclude(self, **kwargs):
        for k, v in kwargs.items():
            self._exclude.append(_build_expr(self.model, k, v))
        return self

    def order_by(self, *fields):
        self._order.extend(fields)
        return self

    def offset(self, value: int):
        self._offset = value
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def prefetch_related(self, *args):
        return self

    def select_related(self, *args):
        return self

    def annotate(self, **kwargs):
        for alias, expr in kwargs.items():
            if isinstance(expr, Count):
                col = getattr(self.model, expr.field)
                self._aggregates[alias] = func.count(col).label(alias)
            elif isinstance(expr, Sum):
                col = getattr(self.model, expr.field)
                self._aggregates[alias] = func.sum(col).label(alias)
        return self

    def group_by(self, *fields):
        self._group_by = list(fields)
        return self

    async def _select(self, cols):
        await init_orm()
        stmt = select(*cols)
        for target_cls, condition in self._joins:
            stmt = stmt.join(target_cls, condition, isouter=True)
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        if self._exclude:
            stmt = stmt.where(~and_(*self._exclude))
        if self._group_by:
            stmt = stmt.group_by(*[getattr(self.model, f) for f in self._group_by])
        for f in self._order:
            if f.startswith("-"):
                stmt = stmt.order_by(getattr(self.model, f[1:]).desc())
            else:
                stmt = stmt.order_by(getattr(self.model, f).asc())
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        async with _DB.session_factory() as s:
            return await s.execute(stmt)

    async def count(self):
        await init_orm()
        stmt = select(func.count(getattr(self.model, "id")))
        for target_cls, condition in self._joins:
            stmt = stmt.outerjoin(target_cls, condition)
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        if self._exclude:
            stmt = stmt.where(~and_(*self._exclude))
        async with _DB.session_factory() as s:
            return (await s.scalar(stmt)) or 0

    async def first(self):
        self._limit = 1
        res = await self._select([self.model])
        row = res.first()
        return row[0] if row else None

    async def update(self, **kwargs):
        await init_orm()
        stmt = update(self.model)
        if self._filters:
            stmt = stmt.where(and_(*self._filters))
        if self._exclude:
            stmt = stmt.where(~and_(*self._exclude))
        stmt = stmt.values(**kwargs)
        async with _DB.session_factory() as s:
            result = await s.execute(stmt)
            await s.commit()
            return result.rowcount

    async def all(self):
        res = await self._select([self.model])
        return [r[0] for r in res.all()]

    async def values(self, *fields, **aliases):
        if self._aggregates:
            cols = []
            for f in fields:
                if f in self._aggregates:
                    cols.append(self._aggregates[f])
                else:
                    cols.append(getattr(self.model, f).label(f))
            for dst, src in aliases.items():
                col, _ = self._resolve_fk(src)
                cols.append(col.label(dst))
            for k, v in self._aggregates.items():
                if k not in fields and k not in aliases:
                    cols.append(v)
            res = await self._select(cols)
            rows = []
            for r in res.mappings().all():
                rows.append(dict(r))
            return rows
        mapping = {f: f for f in fields}
        mapping.update(aliases)
        cols = []
        for dst, src in mapping.items():
            col, _ = self._resolve_fk(src)
            cols.append(col.label(dst))
        res = await self._select(cols)
        return [dict(r) for r in res.mappings().all()]

    async def values_list(self, field: str, flat: bool = False):
        res = await self._select([getattr(self.model, field)])
        vals = [r[0] for r in res.all()]
        return vals if flat else [(v,) for v in vals]

    def __await__(self):
        async def _load():
            res = await self._select([self.model])
            return [r[0] for r in res.all()]
        return _load().__await__()


class Model(SADeclarativeBase):
    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    is_del: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    _model_registry: Dict[str, type["Model"]] = {}

    def __init_subclass__(cls, **kwargs):
        meta = getattr(cls, 'Meta', None)
        if meta is not None:
            if getattr(meta, 'abstract', False):
                cls.__abstract__ = True
            table = getattr(meta, 'table', None)
            if table is not None:
                cls.__tablename__ = table
                full_name = f"system.{cls.__name__}"
                Model._model_registry[full_name] = cls
                Model._model_registry[cls.__name__] = cls
                Model._model_registry[table] = cls
        super().__init_subclass__(**kwargs)

    @classmethod
    def filter(cls, *args, **kwargs):
        return QuerySet(cls).filter(*args, **kwargs)

    @classmethod
    async def get_or_none(cls, *args, **kwargs):
        return await QuerySet(cls).filter(*args, **kwargs).first()

    @classmethod
    async def create(cls, **kwargs):
        await init_orm()
        obj = cls()
        cols = cls.__table__.columns
        for k, v in kwargs.items():
            if hasattr(v, "id"):
                if k.endswith("_id"):
                    setattr(obj, k, getattr(v, "id"))
                elif f"{k}_id" in cols:
                    setattr(obj, f"{k}_id", getattr(v, "id"))
                else:
                    setattr(obj, k, v)
            elif k.endswith("_id") and k in cols and not hasattr(cls, k):
                # FK column without matching Python attribute: use base attr name
                base = k[:-3]
                if hasattr(cls, base):
                    setattr(obj, base, v)
                else:
                    setattr(obj, k, v)
            else:
                setattr(obj, k, v)
        async with _DB.session_factory() as s:
            s.add(obj)
            await s.commit()
            await s.refresh(obj)
        return obj

    async def save(self):
        await init_orm()
        async with _DB.session_factory() as s:
            await s.merge(self)
            await s.commit()
        return self

    async def update_from_dict(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)
        await self.save()

    @classmethod
    async def get_or_create(cls, **kwargs):
        obj = await cls.get_or_none(**kwargs)
        if obj:
            return obj, False
        obj = await cls.create(**kwargs)
        return obj, True

    async def delete(self):
        await init_orm()
        async with _DB.session_factory() as s:
            await s.delete(await s.merge(self))
            await s.commit()
        return True


class models:
    Model = Model


class _Fields:
    CASCADE = "CASCADE"
    SET_NULL = "SET_NULL"

    @staticmethod
    def _coltype(kind: str, **kwargs):
        if kind == "char":
            return String(kwargs.get("max_length", 255))
        if kind == "text":
            return Text
        if kind == "bool":
            return Boolean
        if kind == "smallint":
            return SmallInteger
        if kind == "int":
            return Integer
        if kind == "bigint":
            return BigInteger
        if kind == "float":
            return Float
        if kind == "json":
            return JSON
        if kind == "datetime":
            return DateTime
        if kind == "uuid":
            return String(36)
        return String(255)

    @classmethod
    def _mk(cls, kind: str, **kwargs):
        source_field = kwargs.get("source_field")
        col = mapped_column(
            source_field,
            cls._coltype(kind, **kwargs),
            nullable=kwargs.get("null", False),
            default=kwargs.get("default", None),
            unique=kwargs.get("unique", False),
        )
        return col

    @classmethod
    def CharField(cls, **kwargs): return cls._mk("char", **kwargs)
    @classmethod
    def TextField(cls, **kwargs): return cls._mk("text", **kwargs)
    @classmethod
    def BooleanField(cls, **kwargs): return cls._mk("bool", **kwargs)
    @classmethod
    def SmallIntField(cls, **kwargs): return cls._mk("smallint", **kwargs)
    @classmethod
    def IntField(cls, **kwargs): return cls._mk("int", **kwargs)
    @classmethod
    def BigIntField(cls, **kwargs): return cls._mk("bigint", **kwargs)
    @classmethod
    def FloatField(cls, **kwargs): return cls._mk("float", **kwargs)
    @classmethod
    def JSONField(cls, **kwargs): return cls._mk("json", **kwargs)
    @classmethod
    def DatetimeField(cls, auto_now=False, auto_now_add=False, **kwargs):
        default = datetime.utcnow if (auto_now or auto_now_add) else kwargs.get("default", None)
        onupdate = datetime.utcnow if auto_now else None
        return mapped_column(kwargs.get("source_field"), DateTime, nullable=kwargs.get("null", False), default=default, onupdate=onupdate)
    @classmethod
    def UUIDField(cls, pk=False, **kwargs):
        return mapped_column(kwargs.get("source_field"), String(36), primary_key=pk, default=lambda: str(uuid.uuid4()), nullable=kwargs.get("null", False))
    @classmethod
    def ForeignKeyField(cls, _model, source_field=None, null=False, **kwargs):
        info = kwargs.pop("info", {}) if "info" in kwargs else {}
        info["_fk_model"] = _model
        return mapped_column(source_field, String(36), nullable=null, info=info)


fields = _Fields()
