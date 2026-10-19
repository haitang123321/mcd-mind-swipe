"""会话路由（规划书 6.3）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import service
from ..models.schemas import (
    AnswerRequest,
    FeedbackRequest,
    FeedbackResponse,
    SessionView,
    StartRequest,
    UndoRequest,
)

router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("/start", response_model=SessionView)
async def start(req: StartRequest) -> SessionView:
    return await service.start_session(req)


@router.post("/{session_id}/answer", response_model=SessionView)
async def answer(session_id: str, req: AnswerRequest) -> SessionView:
    try:
        return await service.answer(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=_msg(exc)) from exc


@router.post("/{session_id}/undo", response_model=SessionView)
async def undo(session_id: str, req: UndoRequest) -> SessionView:
    try:
        return await service.undo(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=_msg(exc)) from exc


@router.get("/{session_id}/recommendations", response_model=SessionView)
async def recommendations(session_id: str) -> SessionView:
    try:
        return await service.recommendations(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=_msg(exc)) from exc


@router.post("/{session_id}/feedback", response_model=FeedbackResponse)
async def feedback(session_id: str, req: FeedbackRequest) -> FeedbackResponse:
    try:
        return await service.feedback(session_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=_msg(exc)) from exc


def _msg(exc: KeyError) -> str:
    return str(exc).strip("'\"")
