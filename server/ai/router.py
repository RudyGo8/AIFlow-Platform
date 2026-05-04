"""
AI 模块路由 — 将 RAG Agent 端点的 /api/r1/* 映射为 /api/ai/*
"""
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute

# ── 确保 RAG backend 在 Python path，env 从正确位置加载 ──────────
_RAG_BACKEND = Path(__file__).resolve().parent.parent.parent / "Rag_Agent" / "backend"
if str(_RAG_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RAG_BACKEND))

# 强制从 RAG backend 目录加载 .env
from dotenv import load_dotenv
_ENV_PATH = _RAG_BACKEND / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def create_ai_router() -> APIRouter:
    """创建 /api/ai/* 路由，将 RAG 原始路由前缀重写"""
    from app.routes.common.chat import router_r1 as chat_r1
    from app.routes.common.document import router_r1 as doc_r1
    from app.routes.common.version import router_r1 as ver_r1

    rewrite_map = {
        "/api/r1/chat": "/api/ai/chat",
        "/api/r1/documents": "/api/ai/documents",
        "/api/r1/version": "/api/ai/version",
    }

    router = APIRouter(tags=["AI 知识库"])

    for src_router in (chat_r1, doc_r1, ver_r1):
        old_prefix = src_router.prefix
        new_prefix = rewrite_map.get(old_prefix, old_prefix)

        for route in src_router.routes:
            if not isinstance(route, APIRoute):
                # Mount / WebSocket etc — skip
                continue
            # Rewrite path: /api/r1/chat/stream → /api/ai/chat/stream
            new_path = route.path.replace(old_prefix, new_prefix, 1)
            router.add_api_route(
                path=new_path,
                endpoint=route.endpoint,
                methods=route.methods,
                response_model=route.response_model,
                status_code=route.status_code,
                tags=route.tags or ["AI 知识库"],
                summary=route.summary,
                description=route.description,
                include_in_schema=route.include_in_schema,
            )

    return router


def patch_rag_auth(app):
    """替换 RAG 原始鉴权为管理端 JWT 桥接"""
    from ai.auth import get_rag_user, require_rag_admin
    from app.utils import auth_utils
    app.dependency_overrides[auth_utils.get_current_user] = get_rag_user
    app.dependency_overrides[auth_utils.require_admin] = require_rag_admin


def init_rag_db():
    """初始化 RAG 数据库表"""
    from app.database import init_db
    init_db()
