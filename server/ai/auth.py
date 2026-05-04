"""
AI 模块鉴权适配层 — 复用管理端 JWT，自动在 RAG 数据库创建用户。
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request


@dataclass
class RagUser:
    username: str
    role: str = "user"


async def get_ai_user(request: Request) -> dict:
    """从管理端 JWT 获取当前用户信息（返回 dict 供 RAG 业务使用）"""
    from annotation.auth import AuthController

    token = request.headers.get("Authorization", "")
    admin_user = await AuthController.get_current_user(request, token)
    return admin_user


async def get_rag_user(request: Request) -> RagUser:
    """
    RAG 兼容用户对象 — 自动在 RAG 数据库创建用户记录。
    用于 dependency_overrides 替换 RAG 原始 get_current_user。
    """
    admin_user = await get_ai_user(request)
    user_type = admin_user.get("user_type", 3)
    username = admin_user["username"]
    role = "admin" if user_type <= 1 else "user"

    try:
        from app.database import SessionLocal
        from app.models.db_user import User
        db = SessionLocal()
        try:
            if not db.query(User).filter(User.username == username).first():
                db.add(User(username=username, password_hash="", role=role))
                db.commit()
        finally:
            db.close()
    except Exception:
        pass

    return RagUser(username=username, role=role)


async def require_rag_admin(user: RagUser = Depends(get_rag_user)) -> RagUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="管理员权限不足")
    return user
