"""意图解析（规划书 4.3 step 1 / 4.5）。

默认走规则解析：零延迟、可解释、可单测，且是 LLM 的降级路径。
若配置了 OpenAI 兼容接口，可把 LLM 输出套进同一个 ParsedContext 校验，
不合法则回退到这里 —— 两条路径的产物完全同构。
"""

from __future__ import annotations

import re

from ..models.schemas import ParsedContext

CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int | None:
    if not s:
        return None
    if s == "十":
        return 10
    if len(s) == 1:
        return CN_NUM.get(s)
    if len(s) == 2 and s[0] == "十":
        return 10 + (CN_NUM.get(s[1]) or 0)
    if len(s) == 2 and s[1] == "十":
        return (CN_NUM.get(s[0]) or 0) * 10
    if len(s) == 3 and s[1] == "十":
        return (CN_NUM.get(s[0]) or 0) * 10 + (CN_NUM.get(s[2]) or 0)
    return None


def parse_budget(text: str) -> float | None:
    m = re.search(r"(?:¥|预算)?\s*(\d{1,3}(?:\.\d)?)\s*(?:元|块|rmb|以内|以下)", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"([一二两三四五六七八九十]{1,3})\s*(?:元|块)", text)
    if m:
        val = _cn_to_int(m.group(1))
        if val:
            return float(val)
    m = re.search(r"预算\s*(\d{1,3})", text)
    if m:
        return float(m.group(1))
    return None


NEG_WORDS = ("不", "别", "不要", "不想", "吃不了", "没法")


def _negated(text: str, word: str) -> bool:
    for neg in NEG_WORDS:
        if neg + word in text or neg + "太" + word in text:
            return True
    return False


def parse(text: str) -> ParsedContext:
    raw = (text or "").strip()
    t = raw.lower()
    ctx = ParsedContext()
    evidence: list[str] = []

    ctx.budget = parse_budget(raw)
    if ctx.budget is not None:
        evidence.append(f"预算 ¥{ctx.budget:g}")

    # 辣
    if "辣" in t:
        if _negated(raw, "辣") or "不辣" in raw or "微辣" in raw:
            ctx.accept_spicy = False
            ctx.want_spicy = False
            evidence.append("不要辣")
        else:
            ctx.accept_spicy = True
            ctx.want_spicy = True
            evidence.append("想吃辣")

    # 油腻 / 清淡（要覆盖「不想太油」「别太腻」这类隔字否定）
    mild_negative = re.search(r"不.{0,4}(油|腻)", raw) or re.search(r"别.{0,4}(油|腻)", raw)
    if mild_negative or any(w in raw for w in ("少油", "清淡", "清爽", "轻食", "健康", "减脂", "减肥")):
        ctx.exclude_oily = True
        ctx.satiety_pref = -0.7
        evidence.append("偏清淡")
    elif any(w in raw for w in ("饿", "扛饿", "管饱", "吃饱", "大份", "过瘾", "饱腹")):
        ctx.satiety_pref = 0.7
        evidence.append("要吃饱")
    elif any(w in raw for w in ("随便", "都行", "不知道", "纠结")):
        evidence.append("需求模糊")

    # 提神
    if any(w in raw for w in ("提神", "困", "熬夜", "咖啡", "醒神")):
        ctx.caffeine_need = True
        evidence.append("需要提神")

    # 时段
    if any(w in raw for w in ("早餐", "早上", "早饭", "早安")):
        ctx.meal_period = "breakfast"
        evidence.append("早餐时段")
    elif any(w in raw for w in ("中午", "午饭", "午餐", "午间")):
        ctx.meal_period = "lunch"
        evidence.append("午餐时段")
    elif any(w in raw for w in ("晚上", "晚饭", "晚餐", "下班")):
        ctx.meal_period = "dinner"
        evidence.append("晚餐时段")
    elif any(w in raw for w in ("夜宵", "加班", "深夜")):
        ctx.meal_period = "late_night"
        evidence.append("加班/夜宵")

    # 情绪
    if any(w in raw for w in ("加班", "累", "疲惫", "烦", "压力")):
        ctx.mood = "tired"
        evidence.append("状态疲惫")
    elif any(w in raw for w in ("开心", "庆祝", "奖励", "犒劳")):
        ctx.mood = "happy"
        evidence.append("心情不错")
    elif any(w in raw for w in ("减肥", "控卡", "减脂")):
        ctx.mood = "diet"

    # 忌口与想吃
    main_map = {"牛肉": "beef", "牛": "beef", "鸡肉": "chicken", "鸡": "chicken",
                "鱼肉": "fish", "鱼": "fish", "猪肉": "pork", "猪": "pork"}
    for word, key in main_map.items():
        if f"不吃{word}" in raw or f"不要{word}" in raw:
            if key not in ctx.mains_exclude:
                ctx.mains_exclude.append(key)
                evidence.append(f"忌口{word}")
        elif f"想吃{word}" in raw or f"来点{word}" in raw:
            if key not in ctx.mains_include:
                ctx.mains_include.append(key)
                evidence.append(f"偏好{word}")

    # 品类线索
    cat_map = {
        "burger": ("汉堡", "堡"),
        "chicken": ("炸鸡", "鸡翅", "鸡块", "鸡排"),
        "dessert": ("甜品", "冰淇淋", "雪糕", "甜筒", "麦旋风", "派"),
        "coffee": ("咖啡", "美式", "拿铁", "奶铁"),
        "beverage": ("饮料", "可乐", "汽水", "果汁", "奶茶"),
        "side": ("薯条", "小食", "配餐", "玉米"),
        "breakfast": ("早餐", "麦满分", "粥"),
    }
    for cat, words in cat_map.items():
        if any(w in raw for w in words):
            if cat not in ctx.categories:
                ctx.categories.append(cat)
    if ctx.categories:
        evidence.append("品类 " + "/".join(ctx.categories))

    if "甜" in raw and "不甜" not in raw:
        ctx.keywords.append("sweet")
    if "清爽" in raw or "解腻" in raw:
        ctx.keywords.append("light")
    if "划算" in raw or "省钱" in raw or "便宜" in raw:
        ctx.keywords.append("value")

    # 置信度：命中项越多越可信；完全无输入则低
    hit = len(evidence)
    ctx.confidence = min(0.95, 0.25 + 0.12 * hit) if raw else 0.0
    ctx.evidence = evidence
    ctx.keywords.extend([w for w in ("饿", "清淡", "辣", "提神") if w in raw])
    return ctx
