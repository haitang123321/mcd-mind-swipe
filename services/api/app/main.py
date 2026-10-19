"""FastAPI 入口。

启动：cd services/api && ../../.venv/bin/uvicorn app.main:app --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .models.db import init_db
from .routers import health, profile, session

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="AI 动态二选一 · 滑动推荐 · 长期偏好学习（独立第三方创意项目，非麦当劳官方产品）",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(session.router)
app.include_router(profile.router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()


# 生产演示：若前端已构建，直接由 API 托管（单进程起服务，方便录屏）
_dist = BASE_DIR / "apps" / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
