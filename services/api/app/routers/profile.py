"""偏好路由：查询与删除。未同意保存时返回空偏好，不读取历史（11.1 第 4 条）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models import db

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("")
async def get_profile(anonymous_id: str = Query(..., min_length=3)) -> dict:
    prof = db.get_profile(anonymous_id)
    if not prof or not prof["consent"]:
        return {"anonymous_id": anonymous_id, "consent": False, "pref": {}}
    return {"anonymous_id": anonymous_id, **prof}


@router.delete("")
async def delete_profile(anonymous_id: str = Query(..., min_length=3)) -> dict:
    db.delete_profile(anonymous_id)
    return {"deleted": True, "anonymous_id": anonymous_id}
