"""MenuProvider 抽象（规划书 5.2 / 6.2）。

上层引擎只认 Product + DataSource，不关心数据来自 Mock 还是真实 MCP。
切换时 DataSource.label 会原样透传到 UI，避免把模拟数据说成实时数据。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.schemas import DataSource, Product


class MenuProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def get_menu(self, store_id: str | None = None) -> tuple[list[Product], DataSource]:
        """返回当前门店可售餐品与数据源描述。"""

    async def get_detail(self, code: str) -> dict | None:
        """套餐组成 / 可替换选项。Mock 默认无详情。"""
        return None

    async def price_quote(self, codes: list[str], store_id: str | None = None) -> dict | None:
        """实付核算。仅真实 Provider 实现；Mock 返回 None 表示「无法核算」。"""
        return None

    @property
    def is_realtime(self) -> bool:
        return False
