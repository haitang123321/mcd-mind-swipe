"""Pydantic 数据契约（对应规划书 6.3 / 6.4 / 附录 A）。

严格程度：所有 API 出入参由此文件定义，LLM 输出必须能通过 ParsedContext 校验，
不通过则回退规则解析（4.5 / 4.6）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["created", "understanding", "questioning", "recommending", "accepted", "ended"]


class Nutrition(BaseModel):
    energy_kcal: float = 0
    protein: float = 0
    fat: float = 0
    carbohydrate: float = 0
    sodium: float = 0
    calcium: float = 0


class Attributes(BaseModel):
    satiety: float = 0.5
    lightness: float = 0.5
    spicy: float = 0.0
    value: float = 0.5
    veg: float = 0.0
    sweet: float = 0.0
    caffeine: float = 0.0
    novelty: float = 0.0


class Product(BaseModel):
    code: str
    name: str
    category: str
    main: str = "none"
    price: float
    nutrition: Nutrition = Field(default_factory=Nutrition)
    attributes: Attributes = Field(default_factory=Attributes)
    tags: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    available: list[str] = Field(default_factory=lambda: ["all_day"])


class DataSource(BaseModel):
    type: Literal["mock", "mcp", "cache"] = "mock"
    label: str = "示例菜单（非实时）"
    store_id: str | None = None
    store_name: str | None = None
    fetched_at: str | None = None
    price_notice: str = "价格为示例估价，不代表任何门店实时售价"


class ParsedContext(BaseModel):
    """意图结构化结果。字段为 None 表示「用户没说」，不得臆造成长期偏好。"""

    budget: float | None = None
    satiety_pref: float | None = None  # -1 极清爽 .. +1 极扛饿
    accept_spicy: bool | None = None
    want_spicy: bool = False
    exclude_oily: bool = False
    caffeine_need: bool = False
    categories: list[str] = Field(default_factory=list)
    mains_exclude: list[str] = Field(default_factory=list)
    mains_include: list[str] = Field(default_factory=list)
    meal_period: Literal["breakfast", "lunch", "afternoon", "dinner", "late_night"] | None = None
    mood: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ChoiceOption(BaseModel):
    id: Literal["L", "R"]
    label: str
    attribute: str
    description: str | None = None


class Question(BaseModel):
    id: str
    dimension: str
    prompt: str
    left: ChoiceOption
    right: ChoiceOption
    allow_skip: bool = True
    revision: int = 1
    value_score: float = 0.0
    why: str | None = None


class MealRecommendation(BaseModel):
    rank: int
    code: str
    name: str
    price: float
    category: str
    score: float
    reason: str
    nutrition: Nutrition
    tags: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class AnswerRecord(BaseModel):
    question_id: str
    dimension: str
    choice: Literal["L", "R", "SKIP"]
    effects: dict[str, float] = Field(default_factory=dict)
    revision: int = 0
    undone: bool = False


class DebugInfo(BaseModel):
    candidates: int = 0
    questions_asked: int = 0
    engine_ms: float = 0.0
    llm_used: bool = False
    llm_tokens: int = 0
    top_score: float = 0.0
    second_score: float = 0.0
    stop_reason: str | None = None


class SessionView(BaseModel):
    session_id: str
    stage: Stage
    parsed: ParsedContext
    question: Question | None = None
    recommendations: list[MealRecommendation] = Field(default_factory=list)
    data_source: DataSource
    debug: DebugInfo = Field(default_factory=DebugInfo)
    revision: int = 0
    duplicate: bool = False
    notice: str | None = None


# ---- 请求体 ----


class StartRequest(BaseModel):
    input: str = Field(default="", max_length=300)
    store_id: str | None = None
    consent: bool = False  # 是否同意跨会话保存偏好
    anonymous_id: str | None = None
    mode: Literal["auto", "explore", "fast"] = "auto"


class AnswerRequest(BaseModel):
    question_id: str
    choice: Literal["L", "R", "SKIP"]
    revision: int
    request_id: str
    skip_reason: str | None = None


class UndoRequest(BaseModel):
    request_id: str


class FeedbackRequest(BaseModel):
    meal_code: str
    action: Literal["like", "dislike", "not_today", "accept", "save"]
    scope: Literal["session", "long_term"] = "session"
    request_id: str | None = None


class FeedbackResponse(BaseModel):
    updated: bool
    stage: Stage
    notice: str
