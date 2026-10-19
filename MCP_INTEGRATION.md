# MCP 集成说明

本文记录本项目**实际使用**的麦当劳 MCP Server、Tool、调用流程与真实返回结构。
所有字段名与结构来自本机真实调用，不是照抄文档示例；接口若有版本差异，以运行时返回为准。

---

## 1. 接入方式

| 项 | 值 |
|---|---|
| 服务地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（JSON-RPC 2.0） |
| 鉴权 | `Authorization: Bearer <MCD_MCP_TOKEN>` |
| 客户端实现 | `services/api/app/providers/mcd_mcp.py`（httpx，无额外 SDK） |
| 限流 | 官方 600 次/分钟；本项目的菜单结果有 180s 缓存，避免重复拉取 |

协议握手：

```
initialize → 服务端返回 Mcp-Session-Id 响应头
notifications/initialized → 返回 202 且 body 为空（正常，不是错误）
tools/call → 内容在 result.content[0].text
```

两个容易踩的点：

1. **`202` 空响应要当成功处理。** 首次实现时把它当 JSON 解析失败，直接抛错。
2. **`content[0].text` 是「说明文字 + JSON + 尾部提示」的混合文本**，不是纯 JSON：

```
每个门店的基本信息按单行展示：
- **门店名称**: data[].storeName
...
{"success":true,"code":200,"data":[{"storeCode":"1400205",...}]}
## 展示结果时，每个门店的 storeCode 和 beCode 必须完整展示，
```

所以要截取第一个 `{"success"` 到最后一个 `}` 再解析，见 `_extract_json()`。

---

## 2. 实际使用的 Tool

### 2.1 `query-nearby-stores` — 选门店（已接入，已实测）

未配置 `MCD_STORE_ID` 时自动定位门店。

```json
{ "searchType": 2, "city": "广州", "keyword": "珠江新城", "beType": 1 }
```

返回 `data[]`，每项含 `storeCode / storeName / address / distance / businessStatus / reservation`。
本项目取第一家，把 `storeCode` 传给后续工具。

> 实测：返回「麦当劳广州华夏路餐厅」，storeCode `1400205`，距离 90m。

### 2.2 `query-meals` — 门店在售菜单（**核心**，已接入，已实测）

```json
{ "storeCode": "1400205", "orderType": 1, "beType": 1 }
```

参数规则（来自运行时 schema）：

- `orderType=1` 到店（含自取与得来速），`orderType=2` 外送
- `beType=1` 到店自取 / `2` 麦乐送 / `5` 得来速 / `6` 团餐
- 到店自取**不要传 `beCode`**，传了会报错

返回结构（关键，与直觉不同）：

```
data.categories[]        ← 分类树，每项 { name, meals: [{ code, tags }] }
data.meals{}             ← 真正的商品字典：{ productCode: { name, currentPrice, originalPrice, image } }
```

商品**没有** `price` 字段，价格叫 `currentPrice`，且是**字符串**（如 `"33.5"`）。

> 实测：该门店返回 120 个条目，剔除联名周边（毛绒玩偶、丝巾、徽章）后剩 119 个可推荐餐品。

### 2.3 `query-meal-detail` — 套餐组成（已实现，已实测）

```json
{ "storeCode": "1400205", "orderType": 1, "beType": 1, "code": "9900016076" }
```

返回 `data.rounds[]`，每轮含 `name / choices[] / isDefault / diffPrice / supportModify`。
用于 V1.1 的「套餐可换」说明；当前 UI 只在推荐详情里使用，不展开特调。

### 2.4 `calculate-price` — 实付核算（已实现，未在 V1 流程启用）

```json
{
  "storeCode": "1400205",
  "orderType": 1,
  "beType": 1,
  "items": [{ "productCode": "511781", "quantity": 1 }]
}
```

用于「结算前再次核价」。V1 只推荐不下单，因此没有在主流程调用；菜单展示的价格明确标注为「门店标价」，不冒充实付。

---

## 3. 调用链

```
启动会话
  └─ query-nearby-stores（仅当未配置门店）→ storeCode
        └─ query-meals（180s 缓存）
              └─ 本地建立候选集与属性标签
                    ├─ 二选一提问（纯本地计算，不访问 MCP）
                    ├─ 二选一提问
                    └─ Top 3
                          └─ query-meal-detail（可选，展示套餐组成）
                                └─ calculate-price（可选，核价；V1 未接入 UI）
```

关键取舍：**提问阶段完全不碰网络。** 菜单一次拉取后在会话内复用，滑动反馈在本地 100ms 内完成；否则每问一次都要等 2–3 秒，手势体验会断。

一次典型会话的 MCP 调用：**2 次**（选门店 + 拉菜单），之后全部本地计算。

---

## 4. 从真实数据到可推荐，中间补了什么

真实 MCP 只给「编码 / 名称 / 价格」，没有口感标签，也没有营养成分。因此 `providers/enrich.py` 做了一层推导：

| 属性 | 有营养数据 | 无营养数据 |
|---|---|---|
| 饱腹感 | 按 `energy_kcal/700` + 蛋白占比 | 按品类给中性先验（汉堡 0.68 / 炸鸡 0.5 / 饮品 0.05） |
| 清爽度 | 按脂肪含量 + 名称关键词 | 只按名称关键词（板烧/烤/粥 +，炸/脆/芝士/双层 −） |
| 辣度 | — | 名称含「辣/龙焰/韩式/椒」 |
| 性价比 | 每元热量 | 中性 0.5 |

分类顺序有个坑：`burger` 必须排在 `chicken` 之前，否则「麦辣鸡腿**汉堡**」会因为含「鸡」被判成炸鸡，进而被「能不能当一餐」的先验压到推荐末尾。实测中这个 bug 导致过「想吃辣 → 推荐鸡块」的坏结果。

---

## 5. 降级策略

| 故障 | 表现 | 处理 |
|---|---|---|
| Token 缺失 / 401 | `McpError` | 自动切 Mock，界面标注「示例菜单（非实时）」，并在 notice 里说明原因 |
| MCP 超时 / 网络异常 | 任何异常 | 同上，绝不返回假数据 |
| `query-meals` 结构变化 | 解析不到 `meals` 字典 | 抛错并降级，不猜测字段 |
| 门店解析失败 | 无 `storeCode` | 提示通过 `MCD_STORE_ID` 指定门店 |
| 数据库不可写 | `disk I/O error` | 自动降级内存存储，`/api/health` 的 `storage` 字段如实显示 `memory` |

降级后界面上的数据源标签会从「实时门店数据」变成「示例菜单（非实时）」，两者在 UI 上视觉区分明显，不会把模拟数据说成真实数据。

---

## 6. 业务价值

1. **降低决策成本**：把「翻 119 个餐品」变成「答 2–3 道二选一」。
2. **把预算约束前置**：用户说 35 元，菜单直接滤到 100 个以内，不会推荐超预算的安格斯。
3. **可解释**：每条推荐都给出「凭什么」，且只引用真实价格与用户自己的回答。
4. **不越权**：只读菜单与价格，不创建订单、不代付、不读历史订单。
5. **可审计**：`/api/session/{id}` 的每一步都有 `revision` 与事件记录，能回放一次决策。

---

## 7. 安全边界

- Token 只在后端进程环境变量中，前端 bundle 内不存在任何密钥（构建产物可全文搜索 `Bearer` 验证）。
- `mcp-config.example.json` 只有 `${MCD_MCP_TOKEN}` 占位符。
- 日志不记录 Token、完整地址、订单。
- `/api/health` 只返回 `mcp_token_configured: true/false`，不回显任何凭证片段。
