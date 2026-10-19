"""排序引擎：硬约束过滤 + 多属性打分（规划书 4.3 step 3）。

score = fit + personal_preference + context_match - uncertainty_penalty
各项系数集中在 WEIGHTS，便于离线评估时调整，不埋在业务分支里。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.schemas import ParsedContext, Product

WEIGHTS = {
    "fit": 0.44,
    "personal": 0.26,
    "context": 0.12,
    "value": 0.05,
    "role": 0.28,
    "uncertainty_empty": 0.04,
}

# 「能不能当一餐」的先验。没有它，用户一说「清爽」就会被咖啡和冰淇淋刷屏。
MEAL_ROLE: dict[str, float] = {
    "burger": 0.82,
    "breakfast": 0.80,
    "chicken": 0.72,
    "side": 0.30,
    "other": 0.45,
    "dessert": 0.12,
    "beverage": 0.06,
    "coffee": 0.05,
}

ATTRS = ("satiety", "lightness", "spicy", "value", "veg", "sweet", "caffeine", "novelty")


@dataclass
class Scored:
    product: Product
    score: float
    parts: dict[str, float] = field(default_factory=dict)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def apply_hard_constraints(products: list[Product], ctx: ParsedContext) -> tuple[list[Product], list[str]]:
    """硬约束：预算、忌口、不吃辣。返回候选与生效的约束说明（用于解释「为何没推荐」）。"""
    notes: list[str] = []
    kept: list[Product] = []
    dropped_budget = dropped_main = dropped_spicy = 0

    for p in products:
        if ctx.budget is not None and p.price > ctx.budget + 1e-6:
            dropped_budget += 1
            continue
        if p.main in ctx.mains_exclude:
            dropped_main += 1
            continue
        if ctx.accept_spicy is False and p.attributes.spicy >= 0.45:
            dropped_spicy += 1
            continue
        kept.append(p)

    if dropped_budget:
        notes.append(f"{dropped_budget} 项超出预算 ¥{ctx.budget:g}")
    if dropped_main:
        notes.append(f"{dropped_main} 项含忌口食材")
    if dropped_spicy:
        notes.append(f"{dropped_spicy} 项偏辣已排除")
    return kept, notes


def _fit(p: Product, ctx: ParsedContext) -> float:
    a = p.attributes
    score = 0.0

    if ctx.satiety_pref is not None:
        if ctx.satiety_pref > 0:
            score += ctx.satiety_pref * a.satiety * 0.55
        else:
            score += (-ctx.satiety_pref) * a.lightness * 0.55

    if ctx.exclude_oily:
        score += a.lightness * 0.30
    if ctx.caffeine_need:
        score += a.caffeine * 0.50
    if ctx.want_spicy:
        score += a.spicy * 0.45
    if ctx.categories and p.category in ctx.categories:
        score += 0.25

    if ctx.meal_period == "breakfast":
        score += 0.22 if p.category == "breakfast" else -0.05
    elif ctx.meal_period in {"lunch", "dinner"} and p.category == "breakfast":
        score -= 0.25

    if ctx.budget is not None and ctx.budget > 0:
        # 预算内留有余地更好，但不惩罚「用满」
        score += (1 - p.price / ctx.budget) * 0.12

    return _clamp(score)


def _personal(p: Product, bias: dict[str, float]) -> float:
    if not bias:
        return 0.0
    total = 0.0
    for attr, weight in bias.items():
        if attr in ATTRS:
            total += weight * getattr(p.attributes, attr)
    # bias 为累加权重，做一次软归一，避免问得越多分数越极端
    norm = max(0.6, min(2.0, sum(abs(v) for v in bias.values()) or 1.0))
    return _clamp(total / norm * 0.5 + 0.5) - 0.5  # 映射到 [-0.5, 0.5]


def _context(p: Product, ctx: ParsedContext) -> float:
    a = p.attributes
    mood = (ctx.mood or "").lower()
    if mood in {"tired", "加班", "累"}:
        return _clamp(a.satiety * 0.5 + a.lightness * 0.2)
    if mood in {"happy", "开心"}:
        return _clamp(a.sweet * 0.5 + a.novelty * 0.3)
    if mood in {"diet", "减肥"}:
        return _clamp(a.lightness * 0.7 + a.veg * 0.3)
    return 0.5


def _meal_role(p: Product, ctx: ParsedContext, bias: dict[str, float]) -> float:
    """先验：这份餐品能否独立当一餐。用户明确要某品类或明确要甜口时放宽。"""
    role = MEAL_ROLE.get(p.category, 0.45)
    if p.category in ctx.categories:
        role = max(role, 0.85)
    if p.category in {"dessert", "beverage", "coffee"} and bias.get("sweet", 0.0) >= 0.6:
        role = max(role, 0.65)
    if ctx.caffeine_need and p.category == "coffee":
        role = max(role, 0.55)
    return role


def score_products(products: list[Product], ctx: ParsedContext, bias: dict[str, float]) -> list[Scored]:
    out: list[Scored] = []
    for p in products:
        fit = _fit(p, ctx)
        personal = _personal(p, bias)
        context = _context(p, ctx)
        value = p.attributes.value
        role = _meal_role(p, ctx, bias)
        raw = (
            WEIGHTS["fit"] * fit
            + WEIGHTS["personal"] * personal
            + WEIGHTS["context"] * context
            + WEIGHTS["value"] * value
            + WEIGHTS["role"] * role
        )
        if not bias:
            raw -= WEIGHTS["uncertainty_empty"]
        out.append(
            Scored(
                product=p,
                score=round(_clamp(raw), 4),
                parts={
                    "fit": round(fit, 3),
                    "personal": round(personal, 3),
                    "context": round(context, 3),
                    "role": round(role, 3),
                },
            )
        )
    out.sort(key=lambda s: (-s.score, s.product.price))
    return out


def top_k(scored: list[Scored], k: int = 3) -> list[Scored]:
    return scored[:k]


BIAS_LABEL = {
    "satiety": "吃饱扛饿",
    "lightness": "清爽不腻",
    "spicy": "来点辣的",
    "value": "省钱划算",
    "sweet": "甜口满足",
    "novelty": "尝点新花样",
    "caffeine": "需要提神",
    "veg": "多些蔬菜",
}


def build_reason(
    s: Scored, ctx: ParsedContext, source_type: str, bias: dict[str, float] | None = None
) -> str:
    """解释只引用「已证实」的信息：预算、用户回答、实测营养。

    没有营养数据时不输出热量 / 油脂类断言（4.5：不可编造健康结论）。
    """
    p = s.product
    bits: list[str] = []
    has_nutrition = p.nutrition.energy_kcal > 0

    if ctx.budget is not None:
        bits.append(f"¥{p.price:g} 在 ¥{ctx.budget:g} 预算内")
    if ctx.satiety_pref is not None and ctx.satiety_pref > 0.2 and p.attributes.satiety >= 0.55:
        bits.append("扛饿管饱")
    if ctx.satiety_pref is not None and ctx.satiety_pref < -0.2 and p.attributes.lightness >= 0.55:
        bits.append("口味偏清爽" if not has_nutrition else "偏清爽")
    if ctx.exclude_oily and has_nutrition and p.attributes.lightness >= 0.55:
        bits.append("油脂负担较低")
    if ctx.caffeine_need and p.attributes.caffeine >= 0.5:
        bits.append("可以提神")

    # 引用用户自己选过的方向，避免出现「综合平衡」这类空话
    if bias:
        matched = [
            label
            for attr, label in BIAS_LABEL.items()
            if bias.get(attr, 0) > 0.25 and getattr(p.attributes, attr) >= 0.55
        ]
        if matched:
            bits.append("对上你选的「" + "」「".join(matched[:2]) + "」")

    if has_nutrition:
        bits.append(f"约 {int(p.nutrition.energy_kcal)} kcal")
        if p.nutrition.protein >= 15:
            bits.append(f"蛋白 {p.nutrition.protein:g}g")

    if not bits:
        bits.append(f"门店在售价 ¥{p.price:g}，当前预算与口味条件下排序靠前")

    tail = "（示例菜单）" if source_type == "mock" else ""
    return "，".join(bits) + tail
