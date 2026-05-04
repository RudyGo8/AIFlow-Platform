"""
AI 知识库模块 — RAG Agent 集成

路由前缀 /api/ai/*，复用管理端 JWT 认证和 Casbin 权限控制。
"""
from .router import create_ai_router, patch_rag_auth, init_rag_db

__all__ = ["create_ai_router", "patch_rag_auth", "init_rag_db"]
