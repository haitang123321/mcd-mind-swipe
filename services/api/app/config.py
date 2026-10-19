"""全局配置。

所有敏感信息（MCP Token / LLM Key）只从环境变量读取，绝不落代码与前端。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_name: str = "麦麦读心术 · MCD Mind Swipe"
    version: str = "0.1.0"

    # 菜单来源：mock | mcp
    menu_provider: str = field(default_factory=lambda: os.getenv("MENU_PROVIDER", "mock"))
    mcp_url: str = field(default_factory=lambda: os.getenv("MCD_MCP_URL", "https://mcp.mcd.cn"))
    mcp_token: str = field(default_factory=lambda: os.getenv("MCD_MCP_TOKEN", ""))
    mcp_timeout_sec: float = field(default_factory=lambda: float(os.getenv("MCD_MCP_TIMEOUT", "12")))
    store_id: str = field(default_factory=lambda: os.getenv("MCD_STORE_ID", ""))

    # 会话与存储
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", str(BASE_DIR / "data" / "mind_swipe.db")))
    session_ttl_sec: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_SEC", "7200")))

    # 引擎参数（第 4.3 / 4.4 章的可调系数）
    max_questions: int = field(default_factory=lambda: int(os.getenv("MAX_QUESTIONS", "5")))
    stop_confidence_gap: float = field(default_factory=lambda: float(os.getenv("STOP_CONFIDENCE_GAP", "0.075")))
    question_value_floor: float = field(default_factory=lambda: float(os.getenv("QUESTION_VALUE_FLOOR", "0.30")))

    # LLM（可选，缺省则纯规则引擎；接口保持 OpenAI 兼容）
    llm_enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", False))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))

    # 前端地址（CORS）
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")


settings = Settings()
