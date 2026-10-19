"""会话编排：状态机 + 幂等 + 撤销 + 降级（规划书 7.1 / 4.6）。

状态流：CREATED → UNDERSTANDING → QUESTIONING ↔ FEEDBACK → RECOMMENDING → ACCEPTED / ENDED
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from .config import settings
from .engines import intent, question as qengine, ranker
from .models import db
from .models.schemas import (
    AnswerRecord,
    AnswerRequest,
    DataSource,
    DebugInfo,
    FeedbackRequest,
    FeedbackResponse,
    MealRecommendation,
    ParsedContext,
    Product,
    SessionView,
    StartRequest,
    UndoRequest,
)
from .providers.base import MenuProvider
from .providers.mcd_mcp import McdMcpMenuProvider, McpError
from .providers.mock import MockMenuProvider


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _provider(store_id: str | None) -> MenuProvider:
    if settings.menu_provider == "mcp" and settings.mcp_token:
        return McdMcpMenuProvider(store_id)
    return MockMenuProvider()


async def _load_candidates(
    store_id: str | None,
) -> tuple[list[Product], DataSource, str | None]:
    """返回 (候选, 数据源, 降级说明)。真实 MCP 失败时自动降级 Mock 并如实标注。"""
    provider = _provider(store_id)
    notice: str | None = None
    try:
        products, source = await provider.get_menu(store_id)
    except McpError as exc:
        products, source = await MockMenuProvider().get_menu(store_id)
        notice = f"实时门店数据不可用（{exc}），已降级为示例菜单，价格与供应状态非实时。"
    except Exception as exc:  # noqa: BLE001 - 任何 Provider 异常都必须降级而非 500
        products, source = await MockMenuProvider().get_menu(store_id)
        notice = f"菜单服务异常（{type(exc).__name__}），已降级为示例菜单。"
    return products, source, notice


def _dump(session: dict) -> dict:
    return session


def _save(session: dict) -> None:
    db.save_session(session["id"], _dump(session), settings.session_ttl_sec)


def _parse_products(raw: list[dict]) -> list[Product]:
    return [Product(**p) for p in raw]


ANSWER_DECAY = 0.78  # 越靠后的选择权重越高：用户「今天想吃」会盖过前几轮的犹豫


def recompute_bias(answers: list[dict], decay: float = ANSWER_DECAY) -> dict[str, float]:
    """bias 是「答题记录的派生状态」，不是累加器。

    从记录重算的好处：撤销只需删记录，偏好回滚天然正确（11.1 第 3 条）。
    """
    bias: dict[str, float] = {}
    for a in answers:
        if a.get("choice") == "SKIP":
            continue
        for k in list(bias):
            bias[k] *= decay
        for k, v in (a.get("effects") or {}).items():
            bias[k] = bias.get(k, 0.0) + v
    return {k: round(v, 4) for k, v in bias.items() if abs(v) > 1e-4}


def _confidence(gap: float) -> str:
    if gap >= 0.06:
        return "high"
    if gap >= 0.03:
        return "medium"
    return "low"


def _build_recommendations(
    scored: list[ranker.Scored],
    ctx: ParsedContext,
    source_type: str,
    bias: dict[str, float] | None = None,
    limit: int = 3,
) -> list[MealRecommendation]:
    out: list[MealRecommendation] = []
    top = scored[:limit]
    for i, s in enumerate(top):
        nxt = top[i + 1].score if i + 1 < len(top) else s.score - 0.06
        out.append(
            MealRecommendation(
                rank=i + 1,
                code=s.product.code,
                name=s.product.name,
                price=s.product.price,
                category=s.product.category,
                score=s.score,
                reason=ranker.build_reason(s, ctx, source_type, bias),
                nutrition=s.product.nutrition,
                tags=s.product.tags,
                confidence=_confidence(s.score - nxt),  # type: ignore[arg-type]
            )
        )
    return out


def _debug(session: dict, scored: list[ranker.Scored], stop_reason: str | None, engine_ms: float) -> DebugInfo:
    return DebugInfo(
        candidates=len(session["candidates"]),
        questions_asked=len(session["answers"]),
        engine_ms=round(engine_ms, 2),
        llm_used=False,
        llm_tokens=0,
        top_score=scored[0].score if scored else 0.0,
        second_score=scored[1].score if len(scored) > 1 else 0.0,
        stop_reason=stop_reason,
    )


def _view(
    session: dict,
    *,
    question=None,
    recommendations=None,
    notice: str | None = None,
    duplicate: bool = False,
    debug: DebugInfo | None = None,
) -> SessionView:
    return SessionView(
        session_id=session["id"],
        stage=session["stage"],
        parsed=ParsedContext(**session["parsed"]),
        question=question,
        recommendations=recommendations or [],
        data_source=DataSource(**session["source"]),
        debug=debug or DebugInfo(**session["debug"]),
        revision=session["revision"],
        duplicate=duplicate,
        notice=notice,
    )


async def start_session(req: StartRequest) -> SessionView:
    t0 = time.perf_counter()
    session_id = f"s_{uuid.uuid4().hex[:12]}"
    anonymous_id = req.anonymous_id or f"a_{uuid.uuid4().hex[:10]}"

    ctx = intent.parse(req.input)
    products, source, notice = await _load_candidates(req.store_id)
    candidates, constraint_notes = ranker.apply_hard_constraints(products, ctx)

    session: dict = {
        "id": session_id,
        "anonymous_id": anonymous_id,
        "consent": req.consent,
        "store_id": req.store_id,
        "raw_input": req.input,
        "parsed": ctx.model_dump(),
        "stage": "understanding",
        "bias": {},
        "answers": [],
        "asked": [],
        "revision": 1,
        "request_ids": [],
        "mode": req.mode,
        "source": source.model_dump(),
        "candidates": [p.model_dump() for p in candidates],
        "all_count": len(products),
        "constraint_notes": constraint_notes,
        "debug": {},
        "created_at": time.time(),
    }

    if not candidates:
        session["stage"] = "recommending"
        session["debug"] = _debug(session, [], "no_candidate", (time.perf_counter() - t0) * 1000).model_dump()
        _save(session)
        db.log_event(session_id, "fallback_triggered", {"reason": "no_candidate"})
        hint = "没有符合当前条件的在售餐品。可以试试放宽预算、取消忌口，或换一家门店。"
        if constraint_notes:
            hint += "（" + "；".join(constraint_notes) + "）"
        return _view(session, notice=(notice + " " if notice else "") + hint)

    scored = ranker.score_products(candidates, ctx, {})
    asked: list[str] = []

    # 模式 B：熟客 / 明确指令 → 直接给结果
    fast = req.mode == "fast"
    if req.mode == "auto" and ctx.confidence >= 0.8 and ctx.satiety_pref is not None and ctx.budget is not None:
        fast = True

    if fast:
        session["stage"] = "recommending"
        recs = _build_recommendations(scored, ctx, source.type, session["bias"])
        session["debug"] = _debug(session, scored, "fast_mode", (time.perf_counter() - t0) * 1000).model_dump()
        _save(session)
        db.log_event(session_id, "session_started", {"mode": "fast"})
        db.log_event(session_id, "recommendations_shown", {"count": len(recs)})
        return _view(session, recommendations=recs, notice=notice)

    q, value, _diag = qengine.pick_question(candidates, ctx, {}, asked, session["revision"])
    if q is None or value < settings.question_value_floor:
        session["stage"] = "recommending"
        recs = _build_recommendations(scored, ctx, source.type, session["bias"])
        stop = "no_question" if q is None else "low_value"
        session["debug"] = _debug(session, scored, stop, (time.perf_counter() - t0) * 1000).model_dump()
        _save(session)
        db.log_event(session_id, "session_started", {"mode": "explore"})
        db.log_event(session_id, "recommendations_shown", {"count": len(recs)})
        return _view(session, recommendations=recs, notice=notice)

    session["stage"] = "questioning"
    session["current_question"] = q.model_dump()
    session["debug"] = _debug(session, scored, None, (time.perf_counter() - t0) * 1000).model_dump()
    _save(session)
    db.log_event(session_id, "session_started", {"mode": "explore"})
    db.log_event(session_id, "intent_parsed", {"confidence": ctx.confidence})
    db.log_event(session_id, "question_shown", {"dimension": q.dimension, "value": value})
    return _view(session, question=q, notice=notice)


async def answer(session_id: str, req: AnswerRequest) -> SessionView:
    t0 = time.perf_counter()
    raw = db.load_session(session_id)
    if not raw:
        raise KeyError("session_not_found")

    session = raw
    # 幂等：同一 request_id 重复提交，直接返回当前状态
    if req.request_id in session["request_ids"]:
        return _resume(session, duplicate=True)

    # 旧 revision 的响应不得覆盖新状态
    if req.revision < session["revision"]:
        return _resume(session, notice="已忽略过期选择")

    candidates = _parse_products(session["candidates"])
    ctx = ParsedContext(**session["parsed"])

    current = session.get("current_question") or {}
    dim = current.get("dimension") if current.get("id") == req.question_id else None
    if not dim:
        raise KeyError("question_not_found")

    if req.choice != "SKIP":
        effects = qengine.effects_for(dim, req.choice)
        session["asked"].append(dim)
        record = AnswerRecord(
            question_id=req.question_id, dimension=dim, choice=req.choice,
            effects=effects, revision=req.revision,
        )
        db.append_event(session_id, req.question_id, dim, req.choice, effects, req.revision, req.request_id)
        session["answers"].append(record.model_dump())
        session["bias"] = recompute_bias(session["answers"])
        db.log_event(session_id, "choice_selected", {"dimension": dim, "choice": req.choice})
    else:
        session["asked"].append(dim)
        db.append_event(session_id, req.question_id, dim, "SKIP", {}, req.revision, req.request_id)
        session["answers"].append(
            AnswerRecord(question_id=req.question_id, dimension=dim, choice="SKIP", revision=req.revision).model_dump()
        )
        db.log_event(session_id, "question_skipped", {"dimension": dim})

    session["request_ids"].append(req.request_id)
    session["revision"] += 1

    scored = ranker.score_products(candidates, ctx, session["bias"])
    stop_reason = _stop_reason(session, scored, candidates, ctx)

    if stop_reason:
        session["stage"] = "recommending"
        recs = _build_recommendations(scored, ctx, session["source"]["type"], session.get("bias", {}))
        session["debug"] = _debug(session, scored, stop_reason, (time.perf_counter() - t0) * 1000).model_dump()
        _save(session)
        db.log_event(session_id, "recommendations_shown", {"count": len(recs), "stop": stop_reason})
        return _view(session, recommendations=recs)

    q, value, _ = qengine.pick_question(candidates, ctx, session["bias"], session["asked"], session["revision"])
    if q is None or value < settings.question_value_floor:
        session["stage"] = "recommending"
        recs = _build_recommendations(scored, ctx, session["source"]["type"], session.get("bias", {}))
        session["debug"] = _debug(session, scored, "low_value", (time.perf_counter() - t0) * 1000).model_dump()
        _save(session)
        db.log_event(session_id, "recommendations_shown", {"count": len(recs), "stop": "low_value"})
        return _view(session, recommendations=recs)

    session["stage"] = "questioning"
    session["current_question"] = q.model_dump()
    session["debug"] = _debug(session, scored, None, (time.perf_counter() - t0) * 1000).model_dump()
    _save(session)
    db.log_event(session_id, "question_shown", {"dimension": q.dimension, "value": value})
    return _view(session, question=q)


def _stop_reason(
    session: dict, scored: list[ranker.Scored], candidates: list[Product], ctx: ParsedContext
) -> str | None:
    answers = len(session["answers"])
    if answers >= settings.max_questions:
        return "max_questions"
    if len(candidates) <= 1:
        return "single_candidate"
    if answers >= 1 and len(scored) >= 2:
        gap = scored[0].score - scored[1].score
        if gap >= settings.stop_confidence_gap and scored[0].score >= 0.55:
            # 分差足够大且首位够稳 → 不再打扰
            q, value, _ = qengine.pick_question(candidates, ctx, session["bias"], session["asked"], session["revision"])
            if q is None or value < 0.38:
                return "confident"
    return None


def _resume(session: dict, *, duplicate: bool = False, notice: str | None = None) -> SessionView:
    candidates = _parse_products(session["candidates"])
    ctx = ParsedContext(**session["parsed"])
    scored = ranker.score_products(candidates, ctx, session["bias"])
    if session["stage"] == "questioning":
        q, _value, _ = qengine.pick_question(candidates, ctx, session["bias"], session["asked"], session["revision"])
        return _view(session, question=q, duplicate=duplicate, notice=notice)
    recs = _build_recommendations(scored, ctx, session["source"]["type"], session.get("bias", {}))
    return _view(session, recommendations=recs, duplicate=duplicate, notice=notice)


async def undo(session_id: str, req: UndoRequest) -> SessionView:
    raw = db.load_session(session_id)
    if not raw:
        raise KeyError("session_not_found")
    session = raw
    event = db.undo_last_event(session_id)
    if not event:
        return _resume(session, notice="没有可撤销的选择")

    effects = event.get("effects") or {}
    if isinstance(effects, str):
        import json

        effects = json.loads(effects)
    for i in range(len(session["answers"]) - 1, -1, -1):
        if session["answers"][i]["question_id"] == event["question_id"]:
            session["answers"].pop(i)
            break
    session["bias"] = recompute_bias(session["answers"])
    if session["asked"] and session["asked"][-1] == event["dimension"]:
        session["asked"].pop()
    session["revision"] += 1
    session["stage"] = "questioning"
    db.log_event(session_id, "answer_undone", {"dimension": event["dimension"]})

    candidates = _parse_products(session["candidates"])
    ctx = ParsedContext(**session["parsed"])
    q, value, _ = qengine.pick_question(candidates, ctx, session["bias"], session["asked"], session["revision"])
    if q is None or value < settings.question_value_floor:
        scored = ranker.score_products(candidates, ctx, session["bias"])
        session["stage"] = "recommending"
        session.pop("current_question", None)
        _save(session)
        return _view(session, recommendations=_build_recommendations(scored, ctx, session["source"]["type"], session.get("bias", {})))
    session["current_question"] = q.model_dump()
    _save(session)
    return _view(session, question=q)


async def recommendations(session_id: str) -> SessionView:
    raw = db.load_session(session_id)
    if not raw:
        raise KeyError("session_not_found")
    return _resume(raw)


async def feedback(session_id: str, req: FeedbackRequest) -> FeedbackResponse:
    raw = db.load_session(session_id)
    if not raw:
        raise KeyError("session_not_found")
    session = raw
    action = req.action

    if action in {"accept", "like"}:
        session["stage"] = "accepted"
        db.log_event(session_id, "recommendation_accepted", {"code": req.meal_code, "scope": req.scope})
        notice = "已记录：这次的选择"
    elif action in {"dislike", "not_today"}:
        db.log_event(session_id, "recommendation_rejected", {"code": req.meal_code, "scope": req.scope})
        # 本次会话内把该菜品排到后面
        session["bias"].setdefault("__exclude_codes", [])
        if req.meal_code not in session["bias"]["__exclude_codes"]:
            session["bias"]["__exclude_codes"].append(req.meal_code)
        notice = "已换下这款，仅影响本次会话" if req.scope == "session" else "已记录到长期偏好"
        if req.scope == "long_term" and session.get("consent"):
            prof = db.get_profile(session["anonymous_id"]) or {"consent": True, "pref": {}}
            pref = prof["pref"]
            pref.setdefault("disliked", [])
            if req.meal_code not in pref["disliked"]:
                pref["disliked"].append(req.meal_code)
            db.save_profile(session["anonymous_id"], True, pref)
        elif req.scope == "long_term":
            notice = "长期偏好需先同意保存，本次仅影响本会话"
    else:
        notice = "已收藏"

    _save(session)
    return FeedbackResponse(updated=True, stage=session["stage"], notice=notice)
