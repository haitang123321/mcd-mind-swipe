"""Mock 菜单 Provider：读 data/mock_menu.json，离线可演示（8.1 案例 4 的降级路径）。"""

from __future__ import annotations

import json
from datetime import datetime

from ..config import DATA_DIR
from ..models.schemas import DataSource, Product
from .base import MenuProvider


class MockMenuProvider(MenuProvider):
    name = "mock"

    def __init__(self, path=None):
        self._path = path or (DATA_DIR / "mock_menu.json")
        self._cache: list[Product] | None = None
        self._meta: dict = {}

    def _load(self) -> None:
        if self._cache is not None:
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._meta = raw.get("meta", {})
        store = raw.get("store", {})
        self._store = store
        self._cache = [Product(**p) for p in raw["products"]]

    async def get_menu(self, store_id: str | None = None) -> tuple[list[Product], DataSource]:
        self._load()
        source = DataSource(
            type="mock",
            label=self._meta.get("label", "示例菜单（非实时）"),
            store_id=store_id or self._store.get("id"),
            store_name=self._store.get("name"),
            fetched_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            price_notice=self._meta.get("note", "价格为示例估价"),
        )
        assert self._cache is not None
        return list(self._cache), source
