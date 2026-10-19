"""端到端契约测试（对应规划书 11.1 的 Must pass 条目）。

运行：cd services/api && ../../.venv/bin/pytest -q
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "api"))

# 固定路径而非 tempfile.gettempdir()：部分受限环境里后者自身会抛 FileNotFoundError。
# 若该路径不可写，持久层会自动降级到内存后端，测试语义不变。
os.environ["DB_PATH"] = "/tmp/mind_swipe_test.db"
os.environ["MENU_PROVIDER"] = "mock"

from app import service  # noqa: E402
from app.models import db  # noqa: E402
from app.models.schemas import AnswerRequest, StartRequest, UndoRequest  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def _start(text: str, **kw):
    db.init_db()
    return run(service.start_session(StartRequest(input=text, **kw)))


def _answer(view, choice="R", request_id="r1"):
    return run(
        service.answer(
            view.session_id,
            AnswerRequest(question_id=view.question.id, choice=choice, revision=view.revision, request_id=request_id),
        )
    )


def test_blank_input_can_start_and_terminates():
    """空白偏好也能开始，且不会无限追问。"""
    v = _start("")
    assert v.stage in {"questioning", "recommending"}
    rounds = 0
    while v.question and rounds < 10:
        v = _answer(v, "R", f"r{rounds}")
        rounds += 1
    assert rounds <= 5, "提问轮次必须封顶在 5 次"
    assert v.stage == "recommending"
    assert 1 <= len(v.recommendations) <= 3


def test_budget_is_hard_constraint():
    v = _start("20元以内")
    assert v.debug.candidates < 49, "预算必须参与硬过滤"
    while v.question:
        v = _answer(v, "L", f"b{v.revision}")
    assert all(r.price <= 20 for r in v.recommendations)


def test_exclusion_is_hard_constraint():
    v = _start("不吃牛肉，预算30元")
    assert v.parsed.mains_exclude == ["beef"]
    while v.question:
        v = _answer(v, "L", f"x{v.revision}")
    names = " ".join(r.name for r in v.recommendations)
    assert "巨无霸" not in names and "安格斯" not in names


def test_impossible_budget_gives_hint_not_fake_recommendation():
    v = _start("预算1元")
    assert v.stage == "recommending"
    assert v.recommendations == []
    assert v.notice and "放宽" in v.notice


def test_idempotent_answer():
    v = _start("今天吃什么")
    assert v.question is not None
    first = _answer(v, "L", "same-req")
    second = run(
        service.answer(
            v.session_id,
            AnswerRequest(question_id=v.question.id, choice="L", revision=v.revision, request_id="same-req"),
        )
    )
    assert second.duplicate is True
    assert second.revision == first.revision


def test_undo_restores_previous_question():
    v = _start("今天吃什么")
    q1 = v.question
    v2 = _answer(v, "L", "u1")
    v3 = run(service.undo(v2.session_id, UndoRequest(request_id="u2")))
    assert v3.stage == "questioning"
    assert v3.question is not None
    # 撤销后回到同一维度（revision 会前进，维度应可再次被问）
    assert v3.question.dimension == q1.dimension


def test_stale_revision_rejected():
    v = _start("今天吃什么")
    _answer(v, "L", "s1")
    stale = run(
        service.answer(
            v.session_id,
            AnswerRequest(question_id=v.question.id, choice="R", revision=v.revision, request_id="s2"),
        )
    )
    assert stale.notice == "已忽略过期选择"


def test_fast_mode_skips_questions():
    v = _start("预算35元，不想吃太油", mode="fast")
    assert v.stage == "recommending"
    assert len(v.recommendations) == 3
    assert all(r.price <= 35 for r in v.recommendations)


def test_negated_oily_expression_is_parsed():
    """「不想太油」这类隔字否定必须被识别，否则预算场景会失去软约束。"""
    v = _start("30元以内不想太油")
    assert v.parsed.budget == 30
    assert v.parsed.exclude_oily is True
    assert v.parsed.satiety_pref is not None and v.parsed.satiety_pref < 0


def test_mock_source_is_labeled():
    v = _start("今天吃什么")
    assert v.data_source.type == "mock"
    assert "非实时" in v.data_source.label or "示例" in v.data_source.label
