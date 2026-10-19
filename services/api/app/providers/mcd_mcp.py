"""真实麦当劳 MCP Provider（Streamable HTTP / JSON-RPC 2.0）。

安全边界（规划书 5.2）：
- Token 只在此处的服务端进程内使用，不下发前端、不写仓库、不进日志。
- 所有失败均抛 McpError，由上层降级到 Mock，不伪造数据。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import httpx

from ..config import settings
from ..models.schemas import DataSource, Nutrition, Product
from .base import MenuProvider
from .enrich import enrich_product


class McpError(RuntimeError):
    pass


class McpClient:
    """最小 MCP 客户端：initialize → tools/call。"""

    def __init__(self, url: str, token: str, timeout: float = 12.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "McpClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        await self.initialize()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            last: dict[str, Any] | None = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if not chunk:
                        continue
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                        last = obj
            if last is None:
                raise McpError("MCP SSE 响应中没有可解析的消息")
            return last
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise McpError(f"MCP 响应非 JSON（HTTP {resp.status_code}）") from exc

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._client:
            raise McpError("MCP 客户端未初始化")
        resp = await self._client.post(self.url, headers=self._headers(), json=payload)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if resp.status_code >= 400:
            raise McpError(f"MCP HTTP {resp.status_code}: {resp.text[:200]}")
        # 202/204 且有 notifications 时无 body，属正常协议行为
        if resp.status_code in (202, 204) and not resp.content.strip():
            return {}
        if not resp.content.strip():
            return {}
        data = self._parse(resp)
        if "error" in data:
            raise McpError(f"MCP error: {data['error']}")
        return data

    async def initialize(self) -> None:
        await self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "mcd-mind-swipe", "version": "0.1.0"},
                },
            }
        )
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        data = await self._post(
            {
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000) % 1_000_000,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        result = data.get("result", {})
        content = result.get("content") or []
        for item in content:
            if item.get("type") == "text":
                return _extract_json(item.get("text", ""))
        if result.get("structuredContent"):
            return result["structuredContent"]
        return result


class McdMcpMenuProvider(MenuProvider):
    name = "mcp"

    def __init__(self, store_id: str | None = None, be_type: int = 1, order_type: int = 1):
        self.store_id = store_id or settings.store_id
        self.be_type = be_type
        self.order_type = order_type
        self._store_name: str | None = None
        self._cache: list[Product] | None = None
        self._cache_at: float = 0
        self._ttl = 180.0

    @property
    def is_realtime(self) -> bool:
        return True

    async def _resolve_store(self, client: McpClient) -> str:
        if self.store_id:
            return self.store_id
        data = await client.call_tool(
            "query-nearby-stores",
            {"searchType": 2, "city": "广州", "keyword": "珠江新城", "beType": 1},
        )
        items = data.get("data") if isinstance(data, dict) else data
        if not isinstance(items, list) or not items:
            raise McpError("未从 query-nearby-stores 解析到门店，请通过 MCD_STORE_ID 指定门店编码")
        first = items[0]
        self.store_id = str(first.get("storeCode") or "")
        self._store_name = first.get("storeName")
        if not self.store_id:
            raise McpError("门店缺少 storeCode 字段")
        return self.store_id

    async def get_menu(self, store_id: str | None = None) -> tuple[list[Product], DataSource]:
        if not settings.mcp_token:
            raise McpError("缺少 MCD_MCP_TOKEN，无法使用真实门店数据")
        now = time.time()
        if self._cache and now - self._cache_at < self._ttl:
            return list(self._cache), self._source("cache")

        async with McpClient(settings.mcp_url, settings.mcp_token, settings.mcp_timeout_sec) as client:
            code = store_id or await self._resolve_store(client)
            raw = await client.call_tool(
                "query-meals",
                {"storeCode": code, "orderType": self.order_type, "beType": self.be_type},
            )

        payload = raw.get("data", raw) if isinstance(raw, dict) else {}
        # 真实结构：data.meals 是 {productCode: {name, currentPrice, ...}} 字典
        meals = payload.get("meals") or {}
        if not isinstance(meals, dict) or not meals:
            raise McpError("query-meals 未返回 meals 字典，接口结构可能已变更")

        cat_of: dict[str, str] = {}
        for cat in payload.get("categories") or []:
            cat_name = (cat.get("name") or "").replace("\n", "").strip()
            for item in cat.get("meals") or []:
                c = item.get("code")
                if c:
                    cat_of[str(c)] = cat_name

        products: list[Product] = []
        for code, m in meals.items():
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or "").strip()
            if not name or _is_non_food(name):
                continue
            price = _to_price(m.get("currentPrice") or m.get("originalPrice"))
            p = Product(code=str(code), name=name, category="other", price=price,
                        tags=[cat_of[code]] if code in cat_of else [])
            products.append(enrich_product(p))

        if not products:
            raise McpError("query-meals 返回成功但过滤后无餐品")

        self._cache = products
        self._cache_at = now
        return products, self._source("mcp")

    def _source(self, kind: str) -> DataSource:
        return DataSource(
            type="mcp" if kind == "mcp" else "cache",
            label="实时门店数据" if kind == "mcp" else "门店缓存数据（180s 内）",
            store_id=self.store_id,
            store_name=self._store_name,
            fetched_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            price_notice="价格为门店实时标价；实际应付以计价接口结果为准",
        )

    async def get_detail(self, code: str) -> dict | None:
        if not settings.mcp_token or not self.store_id:
            return None
        async with McpClient(settings.mcp_url, settings.mcp_token, settings.mcp_timeout_sec) as client:
            return await client.call_tool(
                "query-meal-detail",
                {"storeCode": self.store_id, "orderType": self.order_type, "beType": self.be_type, "code": code},
            )

    async def price_quote(self, codes: list[str], store_id: str | None = None) -> dict | None:
        if not settings.mcp_token or not self.store_id:
            return None
        async with McpClient(settings.mcp_url, settings.mcp_token, settings.mcp_timeout_sec) as client:
            return await client.call_tool(
                "calculate-price",
                {
                    "storeCode": store_id or self.store_id,
                    "orderType": self.order_type,
                    "beType": self.be_type,
                    "items": [{"productCode": c, "quantity": 1} for c in codes],
                },
            )


def _extract_json(text: str) -> Any:
    """真实 MCP 的 text content 是「给人看的说明 + JSON 片段 + 尾部提示」的混合体。

    先按整体 JSON 解析，失败则截取第一个 '{' 到最后一个 '}'。
    """
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find('{"success"')
    if start == -1:
        start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return text


NON_FOOD_WORDS = ("周边", "毛绒", "玩具", "盲盒", "徽章", "丝巾", "帽子", "礼盒", "兑换券", "卡片", "纸巾")


def _is_non_food(name: str) -> bool:
    """菜单里混着联名周边与卡券，它们不是「一餐」，必须排除。"""
    return any(w in name for w in NON_FOOD_WORDS)


def _to_price(raw: Any) -> float:
    try:
        val = float(str(raw).replace("¥", "").replace("元", "").strip())
    except (TypeError, ValueError):
        return 0.0
    if val > 1000:  # 少数接口以「分」为单位
        val /= 100
    return round(val, 2)
