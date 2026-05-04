import secrets
import hashlib
from pathlib import Path

import uvicorn
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from server.models.sa_orm import _DB, init_orm, close_orm, SADeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

#  # (description)

class _ConnWrapper:
    async def execute_query(self, sql: str, params=None):
        async with _DB.session_factory() as s:
            result = await s.execute(text(sql), params or {})
            rows = [dict(r) for r in result.mappings().all()] if result.returns_rows else []
            await s.commit()
            return len(rows), rows


class ORMDriver:
    @staticmethod
    async def init(db_url=None, **kwargs):
        if db_url is not None:
            if _DB.initialized:
                return
            _DB.engine = create_async_engine(db_url.replace("mysql://", "mysql+aiomysql://").replace("postgres://", "postgresql+asyncpg://"), echo=False, pool_pre_ping=True)
            _DB.session_factory = async_sessionmaker(_DB.engine, expire_on_commit=False)
            _DB.initialized = True
        else:
            await init_orm()

    @staticmethod
    def get_connection(name='default'):
        return _ConnWrapper()

    @staticmethod
    async def generate_schemas():
        async with _DB.engine.begin() as conn:
            await conn.run_sync(SADeclarativeBase.metadata.create_all)

    @staticmethod
    async def close_connections():
        await close_orm()

BASE_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = Path(__file__).parent / "templates"
DATA_DIR = Path(__file__).parent / "data"
CONFIG_PATH = BASE_DIR / "config.yaml"


class DatabaseConfig(BaseModel):
    """Database configuration"""
    engine: str = "mysql"
    host: str = "127.0.0.1"
    port: int = 3307
    username: str = "root"
    password: str = "123456"
    database: str = "fva_db"


class RedisConfig(BaseModel):
    """Redis"""
    mode: str = "server"
    host: str = "127.0.0.1"
    port: int = 6379
    password: str = ""
    database: int = 1


class JwtConfig(BaseModel):
    """JWT"""
    secret_key: str = ""
    salt: str = "fastapi-vue-admin"
    expire_minutes: int = 1440


class AppConfig(BaseModel):
    """Application configuration"""
    name: str = "FastAPI-Vue-Admin"
    host: str = "0.0.0.0"
    port: int = 9090
    env: str = "dev"


class AdminConfig(BaseModel):
    """Admin configuration"""
    username: str = "admin"
    password: str = "admin123"
    nickname: str = "Super Admin"
    email: str = "admin@example.com"


class SetupConfig(BaseModel):
    """Complete initialization configuration"""
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    jwt: JwtConfig = JwtConfig()
    admin: AdminConfig = AdminConfig()


#  # (description)
setup_app = FastAPI(
    title="System initialization",
    description="System initialization configuration wizard",
    docs_url=None,
    redoc_url=None,
)


def get_setup_html() -> str:
    """Get setup page HTML"""
    html_path = TEMPLATE_DIR / "setup.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>     </h1>"


@setup_app.get("/", response_class=HTMLResponse)
async def setup_page():
    """Setup page"""
    return get_setup_html()


@setup_app.post("/api/setup/test-database")
async def test_database(config: DatabaseConfig):
    """Test database connection"""
    try:
        if config.engine == "sqlite":
            # SQLite  # (description)
            import aiosqlite
            import os
            db_path = config.database if config.database else "fva.db"
            #  # (description)
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute("SELECT 1")
            return {"success": True, "msg": "SQLite database is ready"}
        elif config.engine == "mysql":
            import aiomysql
            conn = await aiomysql.connect(
                host=config.host,
                port=config.port,
                user=config.username,
                password=config.password,
                connect_timeout=5
            )
            #  # (description)
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{config.database}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            await conn.ensure_closed()
        elif config.engine == "postgresql":
            import asyncpg
            # PostgreSQL  # (description)
            conn = await asyncpg.connect(
                host=config.host,
                port=config.port,
                user=config.username,
                password=config.password,
                database="postgres",
                timeout=10
            )
            #  # (description)
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                config.database
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{config.database}"')
            await conn.close()
        return {"success": True, "msg": "   "}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {"success": False, "msg": f": {type(e).__name__}: {str(e) or repr(e)}", "detail": error_detail}


@setup_app.post("/api/setup/test-redis")
async def test_redis(config: RedisConfig):
    """Redis"""
    try:
        
        #  # (description)
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=config.host,
            port=config.port,
            password=config.password or None,
            db=config.database,
            socket_timeout=5
        )
        await r.ping()
        await r.aclose()
        return {"success": True, "msg": "Redis"}
    except Exception as e:
        return {"success": False, "msg": f": {str(e)}"}


def hash_password(password: str, salt: str) -> str:
    """ """
    password_with_salt = (salt + password).encode('utf-8')
    return hashlib.sha256(password_with_salt).hexdigest()


async def init_database_tables(db_config: DatabaseConfig):
    """Initialize database tables"""
    from sqlalchemy import text
    from server.models.sa_orm import _DB, init_orm, close_orm, SADeclarativeBase
    
    #  # (description)
    if db_config.engine == "sqlite":
        db_path = db_config.database if db_config.database else "fva.db"
        db_url = f"sqlite://{db_path}"
    elif db_config.engine == "mysql":
        #  # (description)
        import aiomysql
        conn = await aiomysql.connect(
            host=db_config.host,
            port=db_config.port,
            user=db_config.username,
            password=db_config.password,
            connect_timeout=10
        )
        async with conn.cursor() as cursor:
            #  # (description)
            await cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                (db_config.database,)
            )
            db_exists = await cursor.fetchone()
            
            if not db_exists:
                #  # (description)
                await cursor.execute(
                    f"CREATE DATABASE `{db_config.database}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        await conn.ensure_closed()
        
        db_url = (
            f"mysql://{db_config.username}:{db_config.password}@"
            f"{db_config.host}:{db_config.port}/{db_config.database}"
        )
    else:  # postgresql
        import asyncpg
        conn = await asyncpg.connect(
            host=db_config.host,
            port=db_config.port,
            user=db_config.username,
            password=db_config.password,
            database="postgres",
            timeout=10
        )
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_config.database
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_config.database}"')
        await conn.close()
        
        db_url = (
            f"postgres://{db_config.username}:{db_config.password}@"
            f"{db_config.host}:{db_config.port}/{db_config.database}"
        )
    
    await ORMDriver.init(
        db_url=db_url,
        modules={"system": [
            "models.user",
            "models.role", 
            "models.department",
            "models.permission",
            "models.log",
            "models.config",
            "models.notification",
            "models.file",
            "models.casbin",
        ]},
        use_tz=False,
        timezone="Asia/Shanghai"
    )
    
    #  # (description)
    conn = ORMDriver.get_connection("default")
    
    #  # (description)
    tables_to_drop = [
        "system_user_role",
        "user_notification",
        "system_login_log",
        "system_operation_log",
        "system_user", 
        "system_role",
        "system_department",
        "system_permission",
        "system_config",
        "system_notification",
        "system_file",
        "casbin_rule",
    ]
    
    #  # (description)
    try:
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 0")
    except Exception:
        pass
    
    for table in tables_to_drop:
        try:
            await conn.execute_query(f"DROP TABLE IF EXISTS `{table}`")
        except Exception:
            pass  #    ?
    
    #  # (description)
    try:
        await conn.execute_query("SET FOREIGN_KEY_CHECKS = 1")
    except Exception:
        pass
    
    #  # (description)
    await ORMDriver.generate_schemas()
    await ORMDriver.close_connections()


async def init_admin_and_data(db_config: DatabaseConfig, admin_config: AdminConfig, jwt_salt: str):
    """ - ?JSON """
    from sqlalchemy import text
    from server.models.sa_orm import _DB, init_orm, close_orm, SADeclarativeBase
    from datetime import datetime
    import json
    
    #  # (description)
    now = datetime.now()
    
    #  # (description)
    if db_config.engine == "sqlite":
        db_path = db_config.database if db_config.database else "fva.db"
        db_url = f"sqlite://{db_path}"
    elif db_config.engine == "mysql":
        db_url = (
            f"mysql://{db_config.username}:{db_config.password}@"
            f"{db_config.host}:{db_config.port}/{db_config.database}"
        )
    else:  # postgresql
        db_url = (
            f"postgres://{db_config.username}:{db_config.password}@"
            f"{db_config.host}:{db_config.port}/{db_config.database}"
        )
    
    await ORMDriver.init(
        db_url=db_url,
        modules={"system": [
            "models.user",
            "models.role",
            "models.department", 
            "models.permission",
            "models.log",
            "models.config",
            "models.notification",
            "models.file",
            "models.casbin",
        ]},
        use_tz=False,
        timezone="Asia/Shanghai"
    )
    
    from models import SystemUser, SystemDepartment, SystemRole, SystemPermission
    from models.user import SystemUserRole
    from models.casbin import CasbinRule
    
    # 1.  # (description)
    dept_file = DATA_DIR / "system_department.json"
    if dept_file.exists():
        departments = json.loads(dept_file.read_text(encoding="utf-8"))
        for dept in departments:
            await SystemDepartment.create(
                id=dept["id"],
                name=dept["name"],
                parent_id=dept.get("parent_id"),
                sort=dept.get("sort", 0),
                phone=dept.get("phone"),
                principal=dept.get("principal"),
                email=dept.get("email"),
                status=dept.get("status", 1),
                remark=dept.get("remark"),
                created_at=now,
                updated_at=now
            )
    
    # 2.  # (description)
    role_file = DATA_DIR / "system_role.json"
    if role_file.exists():
        roles = json.loads(role_file.read_text(encoding="utf-8"))
        for role in roles:
            await SystemRole.create(
                id=role["id"],
                name=role.get("role_name", role.get("name")),
                code=role.get("role_code", role.get("code")),
                description=role.get("role_description", role.get("description")),
                status=role.get("status", 1),
                department_id=role.get("department_id"),
                created_at=now,
                updated_at=now
            )
    
    # 3.  # (description)
    perm_file = DATA_DIR / "system_permission.json"
    if perm_file.exists():
        permissions = json.loads(perm_file.read_text(encoding="utf-8"))
        for perm in permissions:
            await SystemPermission.create(
                id=perm["id"],
                menu_type=perm.get("menu_type", 0),
                parent_id=perm.get("parent_id"),
                name=perm.get("name"),
                path=perm.get("path"),
                component=perm.get("component"),
                title=perm.get("title"),
                icon=perm.get("icon"),
                order=perm.get("order", 0),
                authTitle=perm.get("authTitle"),
                authMark=perm.get("authMark"),
                api_path=perm.get("api_path"),
                api_method=perm.get("api_method"),
                min_user_type=perm.get("min_user_type", 3),
                isHide=perm.get("isHide", 0),
                isHideTab=perm.get("isHideTab"),
                isIframe=perm.get("isIframe"),
                link=perm.get("link"),
                keepAlive=perm.get("keepAlive"),
                isFirstLevel=perm.get("isFirstLevel"),
                fixedTab=perm.get("fixedTab"),
                activePath=perm.get("activePath"),
                isFullPage=perm.get("isFullPage"),
                showBadge=perm.get("showBadge", 0),
                showTextBadge=perm.get("showTextBadge"),
                data_scope=perm.get("data_scope", 4),
                remark=perm.get("remark"),
                created_at=now,
                updated_at=now
            )
    
    # 4.  # (description)
    hashed_pwd = hash_password(admin_config.password, jwt_salt)
    dept = await SystemDepartment.get_or_none(name="系统管理", is_del=False)
    admin = await SystemUser.create(
        username=admin_config.username,
        password=hashed_pwd,
        nickname=admin_config.nickname,
        email=admin_config.email,
        user_type=0,  # $?
        status=1,
        department=dept,
        created_at=now,
        updated_at=now
    )
    
    # 5.  # (description)
    admin_role = await SystemRole.get_or_none(code="admin", is_del=False)
    if admin_role:
        await SystemUserRole.create(
            user=admin, 
            role=admin_role,
            created_at=now,
            updated_at=now
        )
    
    # 6.  # (description)
    casbin_file = DATA_DIR / "casbin_rule.json"
    if casbin_file.exists():
        casbin_rules = json.loads(casbin_file.read_text(encoding="utf-8"))
        for rule in casbin_rules:
            await CasbinRule.create(
                id=rule["id"],
                ptype=rule["ptype"],
                v0=rule.get("v0"),
                v1=rule.get("v1"),
                v2=rule.get("v2"),
                v3=rule.get("v3"),
                v4=rule.get("v4"),
                v5=rule.get("v5"),
                created_at=now,
                updated_at=now
            )
    
    # 7.  # (description)
    if admin_role:
        await CasbinRule.create(
            ptype="g",
            v0=str(admin.id),
            v1=admin_role.code,
            created_at=now,
            updated_at=now
        )
    
    await ORMDriver.close_connections()


@setup_app.post("/api/setup/initialize")
async def initialize_system(config: SetupConfig):
    """Initialize system configuration"""
    try:
        #  # (description)
        jwt_secret = config.jwt.secret_key or secrets.token_hex(32)
        jwt_salt = config.jwt.salt or "digital-research-system"
        
        # 1.  # (description)
        config_content = f"""# 
#  # (description)
#  # (description)

#  # (description)
initialized: true

app:
  name: "{config.app.name}"
  version: "1.0.7"
  host: "{config.app.host}"
  port: {config.app.port}
  env: "{config.app.env}"
  api_prefix: "/api"
  reload: {str(config.app.env == 'dev').lower()}
  api_status_enabled: {str(config.app.env != 'prod').lower()}

jwt:
  algorithm: "HS256"
  secret_key: "{jwt_secret}"
  salt: "{jwt_salt}"
  expire_minutes: {config.jwt.expire_minutes}
  redis_expire_minutes: 30

database:
  engine: "{config.database.engine}"
  host: "{config.database.host}"
  port: {config.database.port}
  username: "{config.database.username}"
  password: "{config.database.password}"
  database: "{config.database.database}"
  pool_size: 10
  pool_timeout: 30
  echo: false
  timezone: "Asia/Shanghai"
  charset: "utf8mb4"

redis:
  mode: "{config.redis.mode}"
  host: "{config.redis.host}"
  port: {config.redis.port}
  password: "{config.redis.password}"
  database: {config.redis.database}
  max_connections: 10
  socket_timeout: 5
  retry_on_timeout: true
"""
        
        #  # (description)
        CONFIG_PATH.write_text(config_content, encoding="utf-8")
        
        # 2.  # (description)
        await init_database_tables(config.database)
        
        # 3.  # (description)
        await init_admin_and_data(config.database, config.admin, jwt_salt)
        
        return {
            "success": True,
            "msg": "   ",
            "data": {
                "admin_username": config.admin.username,
                "app_port": config.app.port
            }
        }
    except Exception as e:
        import traceback
        return {"success": False, "msg": f"   ? {str(e)}\n{traceback.format_exc()}"}


@setup_app.get("/api/setup/status")
async def get_setup_status():
    """Get initialization status"""
    initialized = False
    if CONFIG_PATH.exists() and CONFIG_PATH.is_file():
        try:
            import yaml
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            initialized = config.get('initialized', False) is True
        except Exception:
            pass
    
    return {
        "initialized": initialized,
        "config_path": str(CONFIG_PATH)
    }


def run_setup_server(host: str = "0.0.0.0", port: int = 9090):
    """Setup wizard"""
    print("\n" + "=" * 60)
    print("   System Setup Wizard")
    print("=" * 60)
    print("\n  System not yet initialized. Please visit the following address to complete configuration:")
    print(f"\n    http://localhost:{port}")
    print(f"    http://127.0.0.1:{port}")
    print("\n" + "=" * 60 + "\n")
    
    uvicorn.run(
        setup_app,
        host=host,
        port=port,
        log_level="warning"
    )


if __name__ == "__main__":
    run_setup_server()

