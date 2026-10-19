"""健康检查：刻意不返回任何凭证、Token 或内部路径。"""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..models import db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "menu_provider": settings.menu_provider,
        "mcp_token_configured": bool(settings.mcp_token),
        "storage": db.backend(),
        "llm_enabled": settings.llm_enabled,
    }
