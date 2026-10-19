"""真实菜单的属性补全。

真实 MCP 菜单只保证「编码 / 名称 / 价格」，不提供口感标签，也没有营养成分。
这里用名称关键词推导一套可解释的属性；有营养数据时优先用营养数据。

硬约束（规划书 4.5）：不因为数据缺失就给出偏高或偏低的营养结论。
缺营养时属性保持中性，且下层解释器不得输出热量 / 油脂类断言。
"""

from __future__ import annotations

from ..models.schemas import Product

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("breakfast", ("麦满分", "粥", "豆浆", "油条", "营养卷")),
    ("coffee", ("咖啡", "美式", "拿铁", "奶铁", "卡布奇诺", "玛奇朵", "浓缩", "雪冰")),
    ("dessert", ("冰淇淋", "麦旋风", "新地", "圆筒", "派", "阿芙佳朵", "拉明顿", "奶冻")),
    # 汉堡必须排在炸鸡之前：「麦辣鸡腿汉堡」含「鸡」，否则会被判成炸鸡
    ("burger", ("堡", "卷")),
    ("chicken", ("鸡", "翅", "鸡球", "鸡排", "鸡块")),
    # 薯饼/薯条属于配餐，不能算「能独立当一餐」
    ("side", ("薯条", "薯饼", "玉米", "苹果片", "薯角")),
    ("beverage", ("可乐", "雪碧", "红茶", "果汁", "牛奶", "朱古力", "怡泉", "橙")),
]

SPICY_WORDS = ("辣", "龙焰", "韩式", "椒", "芥末")
LIGHT_WORDS = ("玉米", "苹果", "蔬菜", "笋", "沙拉", "粥", "美式", "无糖", "零度", "豆浆", "柠檬", "茶")
HEAVY_WORDS = ("炸", "脆", "酥", "芝士", "安格斯", "培根", "厚牛", "双层", "双牛", "三件套", "四件套")
GRILL_WORDS = ("板烧", "烤", "蒸", "粥", "煮")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def classify(name: str) -> str:
    for category, words in CATEGORY_RULES:
        if any(w in name for w in words):
            return category
    return "other"


def enrich_product(p: Product) -> Product:
    """就地补全分类与可解释属性，已有属性（Mock 数据）不覆盖。"""
    if p.category in {"other", ""}:
        p.category = classify(p.name)

    attrs = p.attributes
    kcal = p.nutrition.energy_kcal
    fat = p.nutrition.fat
    protein = p.nutrition.protein
    price = p.price or 1.0

    if kcal > 0:
        attrs.satiety = _clamp(kcal / 700 * 0.85 + protein / 40 * 0.15)
        light = _clamp(1 - fat / 40) * 0.75
    else:
        attrs.satiety = {"burger": 0.68, "chicken": 0.5, "side": 0.28, "dessert": 0.2,
                         "beverage": 0.05, "coffee": 0.05, "breakfast": 0.5}.get(p.category, 0.4)
        light = 0.5

    if any(w in p.name for w in LIGHT_WORDS):
        light += 0.22
    if any(w in p.name for w in GRILL_WORDS):
        light += 0.18
    if any(w in p.name for w in HEAVY_WORDS):
        light -= 0.22
    attrs.lightness = _clamp(light)

    attrs.spicy = 0.8 if any(w in p.name for w in SPICY_WORDS) else 0.0

    # 性价比：只有拿到热量时才按「每元热量」估算，否则保持中性
    attrs.value = _clamp((kcal / price) / 30) if kcal > 0 else 0.5

    if any(w in p.name for w in ("玉米", "苹果", "蔬菜", "笋", "沙拉")):
        attrs.veg = 0.55
    if p.category == "dessert" or any(w in p.name for w in ("新地", "麦旋风", "派", "朱古力")):
        attrs.sweet = 0.82
    elif p.category == "beverage" and "无糖" not in p.name and "零度" not in p.name:
        attrs.sweet = 0.6
    if p.category == "coffee" or any(w in p.name for w in ("可乐", "红茶", "美式")):
        attrs.caffeine = 0.8 if p.category == "coffee" else 0.15

    if any(w in p.name for w in ("新", "联名", "限定", "龙焰", "月", "厚")):
        attrs.novelty = 0.4

    if not p.tags:
        p.tags = [p.category]
    return p
