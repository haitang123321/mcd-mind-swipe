"""问题引擎（规划书 4.3 step 4 / 4.4）。

question_value = a*split_balance + b*expected_rank_change + c*attribute_relevance - d*repetition
所有系数在 VALUE_WEIGHTS 中，便于后续用离线样本调参。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.schemas import Attributes, ChoiceOption, ParsedContext, Product, Question
from . import ranker


@dataclass(frozen=True)
class Dimension:
    id: str
    prompt: str
    left_label: str
    left_attr: str
    left_effects: dict[str, float]
    right_label: str
    right_attr: str
    right_effects: dict[str, float]
    relevance: tuple[str, ...] = field(default_factory=tuple)


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        id="satiety_vs_lightness",
        prompt="这一餐，你更想要哪种感觉？",
        left_label="吃饱扛饿",
        left_attr="high_satiety",
        left_effects={"satiety": 0.85},
        right_label="清爽不腻",
        right_attr="light_meal",
        right_effects={"lightness": 0.85},
        relevance=("饿", "清淡", "清爽", "light"),
    ),
    Dimension(
        id="value_vs_treat",
        prompt="预算和快乐，这顿更偏向哪边？",
        left_label="省钱划算",
        left_attr="value_first",
        left_effects={"value": 0.85},
        right_label="快乐放纵",
        right_attr="treat_self",
        right_effects={"sweet": 0.35, "novelty": 0.55, "satiety": 0.25},
        relevance=("value",),
    ),
    Dimension(
        id="spicy_vs_mild",
        prompt="口味上，今天想来点刺激吗？",
        left_label="来点辣的",
        left_attr="spicy",
        left_effects={"spicy": 0.9},
        right_label="不辣温和",
        right_attr="mild",
        right_effects={"spicy": -0.9, "lightness": 0.2},
        relevance=("辣",),
    ),
    Dimension(
        id="savory_vs_sweet",
        prompt="更想吃咸香的，还是甜口的？",
        left_label="咸香正餐",
        left_attr="savory",
        left_effects={"satiety": 0.35, "sweet": -0.3, "value": 0.2},
        right_label="甜口满足",
        right_attr="sweet_tooth",
        right_effects={"sweet": 0.9},
        relevance=("sweet",),
    ),
    Dimension(
        id="classic_vs_novel",
        prompt="选熟悉的老朋友，还是尝点新花样？",
        left_label="经典稳妥",
        left_attr="classic",
        left_effects={"value": 0.45, "novelty": -0.2},
        right_label="尝点新花样",
        right_attr="novelty",
        right_effects={"novelty": 0.9},
        relevance=(),
    ),
)

VALUE_WEIGHTS = {"balance": 0.50, "rank_change": 0.30, "relevance": 0.20, "repetition": 0.60}


def _dot(attrs: Attributes, effects: dict[str, float]) -> float:
    return sum(effects.get(k, 0.0) * getattr(attrs, k, 0.0) for k in effects)


def _merge(bias: dict[str, float], effects: dict[str, float]) -> dict[str, float]:
    merged = dict(bias)
    for k, v in effects.items():
        merged[k] = merged.get(k, 0.0) + v
    return merged


def _top_codes(products: list[Product], ctx: ParsedContext, bias: dict[str, float]) -> set[str]:
    return {s.product.code for s in ranker.top_k(ranker.score_products(products, ctx, bias), 3)}


def evaluate(
    dim: Dimension,
    products: list[Product],
    ctx: ParsedContext,
    bias: dict[str, float],
    asked: list[str],
    answered_only_high: bool = False,
) -> tuple[float, dict[str, float]]:
    """返回 (价值分, 诊断明细)。价值过低表示「问了也没用」。"""
    if len(products) < 4:
        return 0.0, {"reason": "候选过少"}

    left_scores = [_dot(p.attributes, dim.left_effects) for p in products]
    right_scores = [_dot(p.attributes, dim.right_effects) for p in products]
    total = len(products)
    L = sum(1 for a, b in zip(left_scores, right_scores) if a > b + 1e-6)
    R = sum(1 for a, b in zip(left_scores, right_scores) if b > a + 1e-6)

    if L + R < max(3, int(total * 0.30)):
        return 0.0, {"reason": "区分度不足", "L": L, "R": R}

    balance = 1 - abs(L - R) / (L + R)

    base_top = _top_codes(products, ctx, bias)
    left_top = _top_codes(products, ctx, _merge(bias, dim.left_effects))
    right_top = _top_codes(products, ctx, _merge(bias, dim.right_effects))
    changed = (len(base_top - left_top) + len(base_top - right_top)) / 6.0

    relevance = 0.25 if any(k in ctx.keywords for k in dim.relevance) else 0.0
    repetition = VALUE_WEIGHTS["repetition"] if dim.id in asked else 0.0
    # 已明确表达的偏好再问一次，价值打折
    if dim.id == "satiety_vs_lightness" and ctx.satiety_pref is not None:
        repetition += 0.45
        if ctx.exclude_oily:
            repetition += 0.20
    if dim.id == "spicy_vs_mild" and ctx.accept_spicy is not None:
        repetition += 0.40
    if dim.id == "savory_vs_sweet" and "sweet" in ctx.keywords:
        repetition += 0.35

    value = (
        VALUE_WEIGHTS["balance"] * balance
        + VALUE_WEIGHTS["rank_change"] * changed
        + VALUE_WEIGHTS["relevance"] * relevance
        - repetition
    )
    return round(max(0.0, value), 4), {"L": L, "R": R, "balance": round(balance, 3),
                                      "rank_change": round(changed, 3), "relevance": relevance}


def pick_question(
    products: list[Product],
    ctx: ParsedContext,
    bias: dict[str, float],
    asked: list[str],
    revision: int,
) -> tuple[Question | None, float, list[dict]]:
    best: tuple[Dimension, float, dict] | None = None
    diag: list[dict] = []

    for dim in DIMENSIONS:
        if dim.id in asked:
            diag.append({"dim": dim.id, "value": 0.0, "skipped": "已问过"})
            continue
        value, detail = evaluate(dim, products, ctx, bias, asked)
        diag.append({"dim": dim.id, "value": value, **detail})
        if value > 0 and (best is None or value > best[1]):
            best = (dim, value, detail)

    if best is None:
        return None, 0.0, diag

    dim, value, _ = best
    q = Question(
        id=f"q{revision}",
        dimension=dim.id,
        prompt=dim.prompt,
        left=ChoiceOption(id="L", label=dim.left_label, attribute=dim.left_attr),
        right=ChoiceOption(id="R", label=dim.right_label, attribute=dim.right_attr),
        allow_skip=True,
        revision=revision,
        value_score=value,
        why=_why(dim.id),
    )
    return q, value, diag


def _why(dimension: str) -> str:
    return {
        "satiety_vs_lightness": "当前候选在份量与清爽度上分成两派，先确定你想要的手感",
        "value_vs_treat": "候选里既有便宜管饱款，也有更贵但更快乐的选择",
        "spicy_vs_mild": "菜单里辣与不辣恰好各占一半",
        "savory_vs_sweet": "你的描述里还没排除甜品路线",
        "classic_vs_novel": "候选里经典款和新品都有，需要确认探索意愿",
    }.get(dimension, "")


def effects_for(dim_id: str, choice: str) -> dict[str, float]:
    for dim in DIMENSIONS:
        if dim.id == dim_id:
            if choice == "L":
                return dict(dim.left_effects)
            if choice == "R":
                return dict(dim.right_effects)
    return {}
