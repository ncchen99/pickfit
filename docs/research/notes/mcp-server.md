# MCP server 調研筆記（E 節）

2026-10-28（台北）· 查證日一律為 2026-10-28。資料來自 modelcontextprotocol.io、官方 SDK 文件、Cloudflare／Anthropic／OpenAI／Cursor 官方文件，以及 npm、PyPI、crates.io 的套件資料。
實測在 [spikes/mcp_stateless/](../../../spikes/mcp_stateless/)（TypeScript SDK v2，Node 與 workerd 都跑過）。沒親自確認的標「未驗證」。

---

## 0. 結論（影響決策的部分）

| # | 事實 | 對 pickfit 的意思 |
|---|---|---|
| 1 | MCP 目前的 **Current 版本是 `2026-07-28`**。這版拿掉 `initialize` handshake 與 `Mcp-Session-Id`，協定本身就是無狀態；每個請求自帶版本與能力（`_meta`），另有必備的 `server/discover` | brief 4.4／11 節「無狀態」已經是規格的預設，不用自己發明 |
| 2 | 但不少客戶端還會用舊的 `initialize`（2025-11-25 以前，稱 legacy）。TS SDK v2 client 與 MCP Inspector 預設都是 legacy。Claude Code 要在 v2 runtime 才會先問 server 支不支援新版：會抓 feature flag 的 session 從 v2.1.232 起用 v2，其他 session 從 v2.1.274 起預設 v2（查核修正，見 4 節） | server 必須**同時服務兩個世代**。官方 SDK v2 的 `createMcpHandler` 預設就這樣做，而且 legacy 那一路也是每請求一個實例、**不發 session id**（spike 實測） |
| 3 | 官方 TS SDK 拆成 `@modelcontextprotocol/server`／`client`（2.4.0）；Python SDK 是 `mcp` 2.3.0，`FastMCP` 改名 `MCPServer`。兩者都以 2026-07-28 為主、相容舊版 | 新程式直接用 v2；網路上大量 v1 範例（`StreamableHTTPServerTransport`、`FastMCP`）已過時 |
| 4 | Cloudflare 官方：**`McpAgent`（Durable Objects）已 deprecated、功能凍結**；新做法是 `agents/mcp/server` 的 `createMcpHandler`，每請求建新 server、不需 DO | 照 brief 部署在 Workers 是對的，而且不需要 Durable Objects |
| 5 | spike：同一份 `worker.mjs` 在 Node 與 `wrangler dev`（workerd）都通過 legacy 與 modern 兩套檢查；官方 TS client（legacy／auto／pin）與 Python client（legacy／auto）都能呼叫 | 10/30「4 個工具上線，接上 Claude Code」的骨架可以直接從 spike 長出來，估半天 |
| 6 | Workers Free：每天 10 萬次請求、每次 **10 ms CPU**、50 個 subrequest；超過每日上限回 Error 1027。Paid 最低每月 5 美元 | 本機量到暖機後每次約 1–8 ms（不是線上 CPU 數字）。`wrangler check startup` 本機量到 global scope 啟動約 57 ms CPU（另有 1 秒啟動上限）。冷啟動的請求是否超過 10 ms：**未驗證**。demo 週考慮直接開 Paid |
| 7 | 不登入時，能用的限流 key 幾乎只剩 IP。Workers 有 Rate Limiting binding（10 或 60 秒週期，每個機房各自計數、近似值）；WAF 免費方案只有 1 條、以 IP 計、10 秒週期 | 最該保護的是 **Meta API credits**：`find_*` 會呼叫 Muse Spark，要有每日預算上限與降級路徑，不只擋請求數 |
| 8 | 客戶端都支援遠端 Streamable HTTP：Claude Code `claude mcp add --transport http`、Codex `[mcp_servers.x] url = …`、Cursor `mcp.json` 的 `url`、Claude（含 Desktop）的 custom connector | demo 用一個公開 URL 就能接所有 agent；Claude custom connector 從 Anthropic 雲端連線，**URL 必須公開可達** |
| 9 | Tool annotations 會實際影響客戶端：Claude Code 對 `readOnlyHint` 的工具會並行執行、斷線時可重試；Codex 的 `writes` 核准模式只對沒標 read-only 的工具跳確認 | 3 個查詢工具標 `readOnlyHint: true`；寫入型工具標 `idempotentHint` 並在 server 端真的去重 |
| 10 | 舊版（2025-11-25）規定 `outputSchema` 根節點必須是 `type: object`、`structuredContent` 必須是 object；新版放寬 | 為了相容 legacy 客戶端，**輸出一律用 object 根節點**，並同時回傳 JSON 文字版 `content` |
| 11 | 在無狀態 legacy 連線上，server 不能主動對 client 發請求（elicitation、sampling） | **不要用 elicitation 問使用者**。改成：description 告訴 agent 先問什麼；server 在結果裡回 `clarifying_question` |
| 12 | MCP Registry 仍是 preview；主要給下游 aggregator 定期抓取（文件舉例：每小時一次），不是給 host 直接用。用 GitHub 登入即可用 `io.github.<帳號>/pickfit` 命名空間登錄遠端 server。Registry 裡已經有 `toolradar`、`topalternativesto` 這類軟體比價／替代品 server | 登錄成本低（約 30 分鐘），對評審曝光幫助有限；差異化仍要靠「長尾」與「實際驗證」 |
| 13 | brief 的 4 個工具大致合理。建議加第 5 個 `submit_software`（同一個 URL 重送就是查進度，冪等），用 server 簽發的 `rec_id` 把 `report_outcome` 綁回某次推薦 | 供給端與回饋都能在 agent 裡 demo；`rec_id` 用 HMAC 簽章就不需要 server 存 session |

---

## 1. MCP 規格現況

### 1.1 版本

| 版本 | 狀態 | 備註 |
|---|---|---|
| 2024-11-05 | Final | HTTP+SSE 傳輸 |
| 2025-03-26 | Final | 引入 Streamable HTTP；HTTP+SSE 開始 deprecated |
| 2025-06-18 | Final | 引入 `MCP-Protocol-Version` header、structured tool output、elicitation；移除 JSON-RPC batching |
| 2025-11-25 | Final | 最後一個 handshake 世代（legacy） |
| **2026-07-28** | **Current** | 無狀態（modern）。版本頁：「The current protocol version is 2026-07-28」 |
| draft | Draft | changelog 目前是空的（「Changes since the most recent release will accumulate here.」） |

來源：[Versioning](https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning.md)、[llms.txt 版本清單](https://modelcontextprotocol.io/llms.txt)、[2025-06-18 changelog](https://modelcontextprotocol.io/specification/2025-06-18/changelog.md)、[draft changelog](https://modelcontextprotocol.io/specification/draft/changelog.md)。

### 1.2 2026-07-28 跟本專案有關的變更

出處：[Key Changes（2026-07-28）](https://modelcontextprotocol.io/specification/2026-07-28/changelog.md)。

| 主題 | 變更 | 對 pickfit |
|---|---|---|
| Session | 移除協定層 session 與 `Mcp-Session-Id`；`tools/list` 不再隨連線變動。需要跨呼叫狀態時，用 server 簽發的 handle 當一般工具參數傳（SEP-2567） | `rec_id` 就是這種 handle |
| Handshake | 移除 `initialize`／`notifications/initialized`。每個請求的 `_meta` 帶 `io.modelcontextprotocol/protocolVersion`、`clientCapabilities`，建議帶 `clientInfo`；結果的 `_meta` 帶 `serverInfo`（SEP-2575） | SDK 處理，不用寫 |
| `server/discover` | server **MUST** 實作，回傳支援版本、能力、身分、`instructions` | SDK 自動提供（spike M1） |
| HTTP header | POST 必須帶 `MCP-Protocol-Version`、`Mcp-Method`；`tools/call` 另需 `Mcp-Name`；header 與 body 不符回 400 `-32020`（SEP-2243） | 方便在 Worker 前面依工具名稱限流，不必解析 body（要先確認版本是 2026-07-28 才可信，見 [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md)） |
| GET stream | 移除 GET 端點與 `resources/subscribe`，改成 `subscriptions/listen` | 不需要；我們沒有推播 |
| Resumability | 移除 SSE 續傳（`Last-Event-ID`） | 工具要短、可重送 |
| 互動 | Server→client 的請求（elicitation、sampling、roots）改成 MRTR：回 `resultType: "input_required"`，client 帶答案重送（SEP-2322） | 不採用，見 0 節 #11 |
| `resultType` | 所有結果必帶 `"complete"` 或 `"input_required"` | SDK 處理 |
| 快取 | `tools/list` 等結果必帶 `ttlMs`、`cacheScope`；建議 `tools/list` 順序固定 | SDK 預設 `ttlMs: 0`、`private`（spike M1/M2）。工具清單穩定後可調高 |
| JSON Schema | `inputSchema`／`outputSchema` 可用任何 2020-12 關鍵字；`structuredContent` 可為任何 JSON 值（SEP-2106） | 為了 legacy 相容，仍用 object 根節點、避免 `$ref` |
| Tool annotations | 沒變：`title`、`readOnlyHint`（預設 false）、`destructiveHint`（預設 true）、`idempotentHint`（預設 false）、`openWorldHint`（預設 true），全部只是提示，client 不應信任不可信 server 的 annotations | 見 5.6 |
| Elicitation | 移除 `notifications/elicitation/complete` 與 URL mode 的 `elicitationId` | 不採用 |
| Deprecated | Roots、Sampling、Logging；HTTP+SSE 傳輸；DCR 改推 Client ID Metadata Documents | 不用 SSE、不做 OAuth |
| 錯誤碼 | `HeaderMismatch -32020`、`MissingRequiredClientCapability -32021`、`UnsupportedProtocolVersion -32022` | spike M4、M6 實測 |

### 1.3 「無狀態 HTTP」的現況

| 問題 | 答案 | 來源 |
|---|---|---|
| 有正式的 stateless 模式嗎？ | 有，而且不是「模式」：2026-07-28 的協定本身就沒有 session | [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog.md)（SEP-2567、SEP-2575） |
| session id 可以省略嗎？ | modern：規格裡已經沒有這個 header。legacy（2025-11-25）：server「**MAY** assign a session ID」，本來就可以不發 | [2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports.md) |
| 同一個端點能服務兩代嗎？ | 可以（dual-era）。帶 modern `_meta` 的請求走無狀態；`initialize` 走 legacy | [Versioning and Compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning.md) |
| legacy client 遇到只支援 modern 的 server？ | 失敗，legacy client 沒有往新版升級的機制 | 同上，相容矩陣 |
| modern client 遇到 legacy server？ | 只支援 modern 的 client：失敗。dual-era client：modern 請求回 4xx、且 body 不是可辨識的 modern 錯誤時，才退回 `initialize`（查核修正：原寫「HTTP 400 後」） | 同上 |

結論：pickfit 的 server 一定要 dual-era。官方 SDK v2 預設就是。

---

## 2. 官方 SDK

### 2.1 版本與授權（2026-10-28 查 npm／PyPI）

| 套件 | 版本 | 授權 | 備註 |
|---|---|---|---|
| `@modelcontextprotocol/server` | 2.4.0 | Apache-2.0 | v2 server；依賴 `zod ^4.2.0` |
| `@modelcontextprotocol/client` | 2.4.0 | Apache-2.0 | v2 client；`versionNegotiation` 預設 legacy |
| `@modelcontextprotocol/node` | 2.1.2 | Apache-2.0 | `toNodeHandler`、localhost Host／Origin 檢查 |
| `@modelcontextprotocol/sdk` | 1.32.2 | MIT（查核補上） | v1，舊 |
| `mcp`（PyPI） | 2.3.0（2026-10-02） | MIT | v2.0.0 於 2026-07-28 發布 |
| `agents`（Cloudflare） | 0.31.0 | MIT | peer 依賴**固定** `@modelcontextprotocol/server@2.3.1` |
| `mcp-handler`（Vercel） | 2.3.0 | Apache-2.0 | peer 依賴 `@modelcontextprotocol/server ^2.0.0` |
| `zod` | 4.6.7 | MIT | Cloudflare 建議 ≥4.5.0 以降低記憶體 |

SDK 列表與分級：[SDKs](https://modelcontextprotocol.io/docs/2026-07-28/sdk.md)（TS、Python 都是 Tier 1）。

### 2.2 TypeScript：最小無狀態 server（spike 實測）

出處：[Serve over HTTP](https://ts.sdk.modelcontextprotocol.io/v2/serving/http.md)、[Web-standard runtimes](https://ts.sdk.modelcontextprotocol.io/v2/serving/web-standard.md)、[Tools](https://ts.sdk.modelcontextprotocol.io/v2/servers/tools.md)、[Legacy clients](https://ts.sdk.modelcontextprotocol.io/v2/serving/legacy-clients.md)。

```js
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const handler = createMcpHandler(({ era }) => {          // 每個 HTTP 請求跑一次
  const server = new McpServer({ name: 'pickfit', version: '0.1.0' }, { instructions: '…' });
  server.registerTool('find_software', {
    title: 'Find software',
    description: '…',
    inputSchema: z.object({ need: z.string().min(3).max(500), os: z.enum(['macos','linux','windows']).optional() }),
    outputSchema: z.object({ picks: z.array(/* … */), best_free: z.object({/* … */}).nullable() }),
    annotations: { readOnlyHint: true, openWorldHint: false }
  }, async (args) => {
    const out = { /* … */ };
    return { content: [{ type: 'text', text: JSON.stringify(out) }], structuredContent: out };
  });
  return server;
});
export default handler;                                    // Cloudflare Workers 直接吃 { fetch }
```

要點：

- `createMcpHandler(factory)` 回傳 `{ fetch, close, notify, bus }`；factory 收到 `era`（`modern`／`legacy`）、`authInfo`、`requestInfo`。
- `legacy` 選項預設 `'stateless'`：legacy 請求也是每請求一個實例、無 session。`'reject'` 會變成只收 modern。**保持預設**。
- `responseMode` 預設 `auto`（有中途通知才升級成 SSE）。spike 觀察：legacy 回應是 SSE、modern 回應是 JSON。
- SDK 會先用 `inputSchema` 驗證輸入，失敗時回 `isError: true` 的工具結果（spike M5），並在送出前用 `outputSchema` 驗證 `structuredContent`。
- handler **不檢查 Host／Origin**，要自己在前面加 `hostHeaderValidationResponse`／`originValidationResponse`；Cloudflare 的包裝版會幫你做（3.1）。

### 2.3 Python：最小無狀態 server（暫存目錄快速實測，未放進 repo）

出處：[Tools](https://py.sdk.modelcontextprotocol.io/servers/tools/index.md)、[Structured Output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/index.md)、[Serving legacy clients](https://py.sdk.modelcontextprotocol.io/run/legacy-clients/index.md)、[Deploy & scale](https://py.sdk.modelcontextprotocol.io/run/deploy/index.md)。

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from mcp.server import MCPServer                 # v1 是 from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = MCPServer("pickfit", instructions="…")

class Pick(BaseModel):
    slug: str
    name: str
    why: str

class FindResult(BaseModel):                     # 回傳型別 = outputSchema
    picks: list[Pick]
    best_free_slug: str | None

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def find_software(
    need: Annotated[str, Field(min_length=3, max_length=500)],
    os: Literal["macos", "linux", "windows"] | None = None,
) -> FindResult:
    """docstring 就是 description"""
    ...

app = mcp.streamable_http_app(stateless_http=True)   # uvicorn server:app
```

要點：

- SDK 依 `MCP-Protocol-Version` header 分流：2026-07-28 本來就無狀態；`stateless_http=True` **只影響 legacy 那一路**（不發 session、可任意水平擴展，代價是不能主動對 client 發請求）。
- 上線要設 `transport_security=TransportSecuritySettings(allowed_hosts=[…])`，否則非 localhost 的請求一律 421。
- 實測：legacy `initialize` 200 且沒有 session header；modern `tools/call` 回 `structuredContent` 與 `resultType: "complete"`；annotations 正確出現在 `tools/list`。和 TS 的差異：`GET /mcp` 會開一條不結束的 SSE（TS 回 405）。

### 2.4 Schema 怎麼寫才兩代都相容

| 規則 | 理由 |
|---|---|
| `inputSchema`、`outputSchema` 的根節點都用 `type: "object"` | 2025-11-25 schema 寫明 outputSchema「Currently restricted to type: "object" at the root level」 |
| `structuredContent` 一律是 object | 2025-11-25 的型別是 `{ [key: string]: unknown }` |
| 同時回 `content: [{type:"text", text: JSON.stringify(out)}]` | 規格：「a tool that returns structured content SHOULD also return the serialized JSON in a TextContent block」。Python SDK 文件說模型只看得到 `content`（各 host 實際行為未逐一驗證） |
| 不用 `$ref`／`$defs`，直接展開 | 舊客戶端的驗證器支援度未驗證；zod 轉出來的 schema 本來就是展開的（spike） |
| 字串都設 `maxLength`、陣列都設 `maxItems` | 規格要求 server 驗證輸入並限流；也是最便宜的防濫用 |
| 回應控制在幾 KB | Claude Code：超過 10,000 token 警告、預設上限 25,000 token、超過 50,000 字元的文字結果存成檔案 |

### 2.5 選哪個語言

**建議 TypeScript SDK v2 + Cloudflare Workers**。理由：spike 已在 workerd 驗證；`export default handler` 一行就能部署；brief 11 節已選 Workers。發現與驗證管線照常用 Python，產出 JSON 索引給 Worker 讀。
若想全用 Python：Python SDK 在 Workers 上能不能跑沒查（未驗證），要改走 Modal 或 Fly。

---

## 3. 部署

### 3.1 Cloudflare Workers：兩種寫法

出處：[MCP Server（createMcpHandler）](https://developers.cloudflare.com/agents/model-context-protocol/apis/handler-api/index.md)、[McpAgent (deprecated)](https://developers.cloudflare.com/agents/model-context-protocol/apis/agent-api/index.md)（兩頁皆 Last updated Oct 27, 2026）。

| | `createMcpHandler`（`agents/mcp/server`） | `McpAgent`（`agents/mcp`） |
|---|---|---|
| 狀態 | 官方推薦 | **Deprecated、feature-frozen**，只留給既有 server 遷移 |
| 架構 | 每請求建一個 SDK v2 server，不需 Durable Object、session、WebSocket | 每個 session 一個 Durable Object |
| SDK | `@modelcontextprotocol/server@2.3.1`（固定版本） | `@modelcontextprotocol/sdk@1.32.1`（v1） |
| 預設 | route `/mcp`；wildcard CORS；Host／Origin 檢查預設允許 localhost 與 `workers.dev`；`legacy: "stateless"` | — |
| Elicitation | 走 MRTR，Worker 不會掛著等使用者 | 舊式推送 |

另一個選擇：**直接用 SDK 的 `createMcpHandler`**（spike 用的就是這個，2.4.0），自己加 20 行左右的包裝：只接 `/mcp`、Host／Origin 檢查、限流。兩者都可以；用 Cloudflare 包裝要配合它固定的 2.3.1。

### 3.2 Workers 方案限制

出處：[Limits](https://developers.cloudflare.com/workers/platform/limits/index.md)、[Pricing](https://developers.cloudflare.com/workers/platform/pricing/index.md)。

| 項目 | Free | Paid |
|---|---|---|
| 請求數 | 100,000／天（UTC 午夜重置），超過回 Error 1027 | 每月 1,000 萬內含，之後每百萬 0.30 美元 |
| CPU time／請求 | **10 ms** | 預設 30 秒，最多 5 分鐘；每月 3,000 萬 CPU ms 內含 |
| 等待網路（呼叫 Meta API） | 不算 CPU time | 同左 |
| Subrequest／請求 | 50 | 10,000 |
| 記憶體 | 128 MB／isolate | 同左 |
| 最低費用 | 0 | 每月 5 美元 |

本機量測（spike `bench.mjs`、`wrangler dev`）：暖機後 1–8 ms，第一次請求 14 ms（workerd wall time）到 55 ms（Node）。線上 CPU time 會不會在冷啟動時超過 10 ms：**未驗證**，部署後看 dashboard 的 Invocation Statuses。

查核補充（2026-10-28 重跑）：

| 量測 | 結果 | 備註 |
|---|---|---|
| `node bench.mjs` 兩次 | 暖機 1.25–1.41 ms；第一次 `tools/list` 55–58 ms | Node wall time |
| `wrangler dev` 本機 traces（63 筆） | 0–14 ms，平均 3.2 ms | 本機 trace 的 `cpu_time_ms` 都是 0，量不到 CPU |
| `wrangler check startup`（wrangler 4.153.0） | bundle 670 KiB（gzip 134 KiB）；global scope 啟動 active 57.2 ms | 本機 CPU。Workers 另有「啟動 1 秒」上限（[Limits › Worker startup time](https://developers.cloudflare.com/workers/platform/limits/index.md)）。啟動時間是否算進 Free 的每請求 10 ms：文件沒寫，**未驗證** |

TS SDK 文件建議 factory 要便宜、無副作用，連線池與快取放 module scope（[Serve over HTTP](https://ts.sdk.modelcontextprotocol.io/v2/serving/http.md)）。正式版的工具清單與 schema 也照這個原則，減少每請求的 CPU。

### 3.3 其他部署選項

| 選項 | 做法 | 優點 | 缺點 | 查證 |
|---|---|---|---|---|
| Vercel | `mcp-handler` 2.3.0（Next.js，peer 依賴 SDK v2） | 有官方指南 | 要帶 Next.js | 只看文件與 npm（[Deploy MCP servers to Vercel](https://vercel.com/docs/mcp/deploy-mcp-servers-to-vercel)） |
| Modal | `@modal.fastapi_endpoint` 或 ASGI app，掛 Python `MCPServer.streamable_http_app()` | 和驗證管線同一個平台、有合作夥伴 credits；有官方範例頁 `mcp_server_stateless` | 冷啟動；URL 是 `*.modal.run` | 只確認[範例頁](https://modal.com/docs/examples/mcp_server_stateless)存在（HTTP 200），未實測 |
| Fly.io | 任何 Docker | 不受 10 ms CPU 限制 | 要管機器 | 未查 |

### 3.4 認證與防濫用

brief 4.4：黑客松期間不登入。規格對工具的要求：server **MUST** 驗證輸入、做存取控制、**限流**、清理輸出（[Tools › Security](https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md)）。

| 層 | 做法 | 備註 |
|---|---|---|
| Schema | 所有字串 `maxLength`、陣列 `maxItems`、enum | SDK 自動驗證（spike M5） |
| Worker 限流 | [Rate Limiting binding](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/index.md)：key = `hash(cf-connecting-ip) + 工具名稱`（工具名稱可讀 `Mcp-Name` header，但只對 2026-07-28 請求可信，legacy 要解析 body）。例：查詢工具 60 次／60 秒，寫入工具 10 次／60 秒 | 週期只能 10 或 60 秒；每個機房各自計數、是近似值；要全球嚴格上限得自己用 Durable Object 做。Cloudflare 不建議用 IP 當 key，但沒有登入就沒有別的 key。binding 2025-09-19 GA（[changelog](https://developers.cloudflare.com/changelog/post/2025-09-19-ratelimit-workers-ga/index.md)）。Free 方案能不能用：binding 頁、Limits、Pricing 都沒寫，**未驗證** |
| Meta 預算 | 每日呼叫數／token 計數（D1 或 KV）；超過門檻就跳過 Muse Spark，改用確定性排序與模板理由，並在結果標 `degraded: true` | $150 credits 是硬限制；Meta 的 Spend Limit 只寄信（見 [meta-model-api.md](meta-model-api.md)） |
| 寫入防灌水 | `report_outcome` 必須帶 server 簽發的 `rec_id`，同一 `rec_id`＋`stage` 只記一次；`submit_software` 同一 URL 冪等、每 IP 每小時上限 | 回報只當弱訊號，品質分數以沙盒驗證為主（brief 13 節） |
| WAF | Free 方案 1 條 rate limiting rule，以 IP 計、10 秒週期（[文件](https://developers.cloudflare.com/waf/rate-limiting-rules/index.md)） | 要自訂網域的 zone；`workers.dev` 能不能套：未驗證 |
| 不記 IP | 限流計數存在 Cloudflare 的 binding，不寫進我們的事件表 | 符合 brief 11 節「不記 IP」 |
| Origin | 有 `Origin` header 時要驗證（規格 MUST）；CLI 類客戶端不送 Origin | Cloudflare 包裝或 SDK helper 處理 |

---

## 4. 客戶端怎麼連

| 客戶端 | 加遠端 server | 協定世代 | 跟我們有關的細節 | 來源 |
|---|---|---|---|---|
| Claude Code | `claude mcp add --transport http pickfit https://<host>/mcp`（加 `--scope user` 就全域）；`.mcp.json` 的 `type` 可寫 `http` 或 `streamable-http` | v1 runtime（TS SDK 1.x）走 legacy。v2 runtime 會先問 HTTP、stdio、claude.ai connector server 支不支援 2026-07-28，支援就用。哪個 session 用 v2：會抓 feature flag 的 session 從 v2.1.232 起；不抓 flag 的 session（Bedrock、Google Agent Platform、Foundry、Claude apps gateway、關掉 telemetry）從 v2.1.274 起預設。Anthropic 可用 flag 讓個別 server 留在舊協定。可用 `MCP_SDK_GENERATION`（v1／v2）、`MCP_PROTOCOL_NEGOTIATION`（auto／legacy）控制（查核修正：原寫「v2.1.232 起依 feature flag」，易誤解為逐步開放） | server instructions 與預先載入的工具 description 截在 4,096 字元，tool search 載入的 description 截在 16,384 字元；關鍵字放前面。`readOnlyHint` → 並行；`idempotentHint`／`readOnlyHint` → 斷線可重送 | [Claude Code MCP](https://code.claude.com/docs/en/mcp.md) |
| Codex（CLI、IDE、ChatGPT desktop 共用設定） | `~/.codex/config.toml`：`[mcp_servers.pickfit]` + `url = "https://<host>/mcp"`；CLI 有 `codex mcp add <name> --url <url>`，OAuth 參數是選用（查核實測 Codex CLI 0.165.0：寫出 `[mcp_servers.pickfit]` + `url = …`，`codex mcp list` 顯示 Auth `Unsupported`；實際連線與呼叫工具未測，需 OpenAI 登入） | 文件寫「reads the MCP `instructions` field returned during initialization」，暗示走 handshake。Codex 釘的 rmcp 3.5.1 已支援 2026-07-28，但 client 預設用哪一代：**未驗證**（dual-era server 不受影響） | `instructions` 前 512 字元要能獨立看懂；`default_tools_approval_mode = "writes"` 只對沒標 read-only 的工具跳確認；`tool_timeout_sec` 預設 60 | [Codex MCP](https://developers.openai.com/codex/mcp.md)、[Codex Cargo.toml](https://raw.githubusercontent.com/openai/codex/main/codex-rs/Cargo.toml)、[rmcp CHANGELOG](https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/main/crates/rmcp/CHANGELOG.md) |
| Cursor | `~/.cursor/mcp.json` 或 `.cursor/mcp.json`：`{"mcpServers":{"pickfit":{"url":"https://<host>/mcp"}}}`；也能做一鍵安裝連結 `cursor://anysphere.cursor-deeplink/mcp/install?name=pickfit&config=<base64>` | 未查 | README 可放「Add to Cursor」按鈕 | [Cursor MCP](https://cursor.com/docs/mcp.md)、[Install links](https://cursor.com/docs/mcp/install-links.md) |
| Claude（claude.ai、Desktop、Cowork、手機） | Customize › Connectors › Add custom connector，貼 URL | 未查 | Free 方案限 1 個 custom connector；**從 Anthropic 雲端連線，URL 必須公開** | [Custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) |
| MCP Inspector | 可選 `legacy`／`auto`／`modern` | 預設 legacy | 除錯兩代行為 | [Protocol eras](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/protocol-eras.md) |

### 4.1 MCP Registry

出處：[About](https://modelcontextprotocol.io/registry/about.md)、[Remote servers](https://modelcontextprotocol.io/registry/remote-servers.md)、[Authentication](https://modelcontextprotocol.io/registry/authentication.md)、[Aggregators](https://modelcontextprotocol.io/registry/registry-aggregators.md)。

| 項目 | 內容 |
|---|---|
| 狀態 | **preview**，可能有破壞性變更或資料重置 |
| 定位 | 只放 metadata；主要給下游 aggregator（市集）定期抓取（文件舉例每小時一次）；「not intended to be directly consumed by host applications」 |
| 登錄遠端 server | `server.json` 的 `remotes: [{ "type": "streamable-http", "url": "https://…/mcp" }]`；URL 必須公開可達 |
| 命名空間 | GitHub 登入 → `io.github.<帳號>/*`；DNS 驗證 → 反向網域（如 `dev.pickfit/*`） |
| 工具 | `mcp-publisher login github` → `mcp-publisher publish`（可用 Homebrew 或 GitHub release 二進位安裝） |
| 公開 API | `GET https://registry.modelcontextprotocol.io/v0.1/servers?search=…`（實測可用，免認證） |
| 同類 | 搜尋結果已有 `io.github.Nadeus/toolradar`（「Search, compare and price software tools」）、`io.github.Natden444/topalternativesto` |

建議：部署並轉 public 之後（11/3–11/4）再登錄，順手做；不要排進關鍵路徑。

---

## 5. 工具設計

### 5.1 brief 4.4 的 4 個工具：評估

| 工具 | 評估 | 建議 |
|---|---|---|
| `find_software` | 合理，是主入口 | 輸出加 `rec_id`、`best_free`、`no_install_option`（「內建的就夠了」）、`clarifying_question`、驗證證據 |
| `find_alternatives` | 合理。和 `find_software` 共用後端，但獨立工具讓 agent 在「換掉 X」時選得準，且能把「哪裡不滿意」設成必填 | 加 `keep_current`：沒有更好的就直說 |
| `get_install_guide` | 合理，是差異化核心 | 區分 agent 能跑的步驟與使用者手動步驟；標出驗證時的系統與使用者系統是否相符；附驗證指令與第一個任務 |
| `report_outcome` | 合理 | 必須帶 `rec_id` 才算數；server 去重後才標 `idempotentHint` |
| （缺）供給端 | brief 4.1、第 5 節 demo 第 5 步需要「貼連結就被收錄」 | 加 `submit_software`（5.5） |

不做的：elicitation（理由見 0 節 #11）；prompts／resources（不影響 demo）；`get_software(slug)`（`get_install_guide` 已涵蓋）。工具總數控制在 5 個以內。

### 5.2 共通原則

- **description 用英文**（給全球 agent 讀），第一句寫「什麼時候呼叫」，第二句寫「呼叫前最多問什麼」，第三句寫「回什麼、下一步呼叫誰」。每個在 1,000 字元內。
- **問問題**：agent 只在不知道時問 1–2 題（作業系統；必須免費或離線）。其他交給 server：模糊時 server 回 `clarifying_question`（由 Muse Spark 挑最能分開候選的那一題），agent 問完再呼叫一次。
- **Meta 模型的位置**：`find_*` 先用索引做確定性過濾（OS、價格、本機執行），再用 Muse Spark 重排、寫理由、挑追問。Meta 失敗或超預算時降級，結果標 `degraded: true`。
- **回傳證據**：每個推薦帶 `verification`（狀態、哪個 OS、何時、證據連結）與分開的 `quality`／`popularity`。這是「不是基本 RAG」最直接的證明。
- **`rec_id`**：server 簽發的 opaque handle（HMAC 簽章，內含推薦的 slug 與時間，7 天有效）。Worker 不用存狀態就能驗證；符合規格 Stateful Tools 一節「無認證 server 的 handle 要高熵、有期限，並在 description 寫明期限」。查核補充：同一節也建議 handle 不透露內部結構（Opacity），因為可讀的結構會引來解析或猜測。slug 與時間若以明文放在 token 裡，建議加密，或只放隨機 nonce＋HMAC（[Tools 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md)）。
- **中立**：description 與結果都不放推薦碼、廣告、付費排序。

### 5.3 Server instructions（Codex 只保證讀前 512 字元）

```text
pickfit recommends lesser-known software that it has installed and tested in a sandbox. Scope today: developer CLI tools and local AI/LLM tools. Flow: find_software (or find_alternatives when replacing a tool) -> user picks -> get_install_guide -> run steps with the user's consent -> report_outcome. Ask at most 1-2 questions first (OS; must be free/offline). No ads or affiliate links; ranking is fit, not stars.
```

（約 430 字元）

### 5.4 各工具的定義

以下 JSON Schema 都是 2020-12、根節點 object、沒有 `$ref`。共用片段先列出，實作時直接展開。

**共用：`pick`（推薦項目）**

```json
{
  "type": "object",
  "properties": {
    "slug": { "type": "string", "maxLength": 64 },
    "name": { "type": "string", "maxLength": 100 },
    "summary": { "type": "string", "maxLength": 200 },
    "why": { "type": "array", "items": { "type": "string", "maxLength": 200 }, "maxItems": 4,
             "description": "Reasons tied to the user's stated conditions" },
    "tradeoffs": { "type": "array", "items": { "type": "string", "maxLength": 200 }, "maxItems": 3 },
    "repo": { "type": ["string", "null"], "format": "uri" },
    "homepage": { "type": ["string", "null"], "format": "uri" },
    "platforms": { "type": "array", "items": { "enum": ["macos", "linux", "windows"] } },
    "pricing": { "enum": ["free", "freemium", "paid", "unknown"] },
    "open_source": { "type": ["boolean", "null"] },
    "license": { "type": ["string", "null"], "description": "SPDX id" },
    "processing": { "enum": ["local", "cloud", "hybrid", "unknown"] },
    "last_release": { "type": ["string", "null"], "format": "date" },
    "verification": {
      "type": "object",
      "properties": {
        "status": { "enum": ["passed", "partial", "failed", "unverified"] },
        "os": { "type": ["string", "null"] },
        "checked_at": { "type": ["string", "null"], "format": "date-time" },
        "evidence_url": { "type": ["string", "null"], "format": "uri" }
      },
      "required": ["status", "checked_at"]
    },
    "scores": {
      "type": "object",
      "properties": {
        "quality": { "type": "number", "minimum": 0, "maximum": 1 },
        "popularity": { "type": "number", "minimum": 0, "maximum": 1 }
      },
      "required": ["quality", "popularity"]
    },
    "sources": { "type": "array", "items": { "type": "string", "format": "uri" }, "maxItems": 5 }
  },
  "required": ["slug", "name", "why", "platforms", "pricing", "processing", "verification", "scores"]
}
```

**共用：使用者條件（`find_software` 與 `find_alternatives` 的輸入都有）**

```json
{
  "os": { "enum": ["macos", "linux", "windows"] },
  "arch": { "enum": ["arm64", "x86_64"] },
  "budget": { "enum": ["free_only", "free_or_paid"], "default": "free_or_paid" },
  "must_run_locally": { "type": "boolean", "description": "true = must work offline / no data leaves the machine" },
  "ui_language": { "type": "string", "maxLength": 35, "description": "BCP 47 tag, only if the user needs the UI or docs in that language" },
  "exclude": { "type": "array", "items": { "type": "string", "maxLength": 64 }, "maxItems": 20, "description": "Slugs already shown or rejected" },
  "limit": { "type": "integer", "minimum": 1, "maximum": 3, "default": 3 }
}
```

#### `find_software`

description：

```text
Use when the user wants a tool for a job and has not settled on a product (e.g. "a free offline CLI to transcribe audio on my Mac"). Before calling, ask at most one or two questions, and only if unknown: which OS, and whether it must be free or run fully offline. Returns up to 3 lesser-known tools that pickfit installed and ran in a sandbox, ranked by fit (not popularity), each with reasons, trade-offs, verification status and separate quality/popularity scores, plus the best free option. If clarifying_question is set, ask it and call again. Next: get_install_guide(slug, os). Coverage: developer CLI tools and local AI/LLM tools.
```

inputSchema：

```json
{
  "type": "object",
  "properties": {
    "need": { "type": "string", "minLength": 3, "maxLength": 500, "description": "The job to get done, in the user's words. Describe the task, not a product name." },
    "category": { "enum": ["dev_cli", "local_ai", "any"], "default": "any" },
    "os": "…共用", "arch": "…共用", "budget": "…共用", "must_run_locally": "…共用",
    "ui_language": "…共用", "exclude": "…共用", "limit": "…共用"
  },
  "required": ["need"],
  "additionalProperties": false
}
```

outputSchema：

```json
{
  "type": "object",
  "properties": {
    "rec_id": { "type": "string", "maxLength": 200, "description": "Opaque handle for report_outcome; valid 7 days" },
    "picks": { "type": "array", "maxItems": 3, "items": "…pick" },
    "best_free": {
      "type": ["object", "null"],
      "properties": { "slug": { "type": "string" }, "reason": { "type": "string", "maxLength": 200 } },
      "required": ["slug", "reason"]
    },
    "no_install_option": { "type": ["string", "null"], "maxLength": 300, "description": "A built-in OS feature or common tool that may already be enough" },
    "clarifying_question": { "type": ["string", "null"], "maxLength": 200, "description": "One question whose answer would change the top pick" },
    "coverage_note": { "type": ["string", "null"], "maxLength": 300 },
    "degraded": { "type": "boolean", "description": "true = ranked without the Meta model (budget or outage)" }
  },
  "required": ["rec_id", "picks", "best_free", "clarifying_question", "degraded"]
}
```

annotations：`{ "readOnlyHint": true, "openWorldHint": false }`

#### `find_alternatives`

description：

```text
Use when the user already uses a specific tool and wants something different ("replace X", "X is too slow / too expensive / needs an account"). Requires the current tool's name and what the user dislikes about it: ask for the dislike if they have not said it; do not guess. Returns up to 3 sandbox-verified alternatives, or keep_current advice when nothing fits better, plus the best free option. Next: get_install_guide(slug, os).
```

inputSchema：

```json
{
  "type": "object",
  "properties": {
    "current_software": { "type": "string", "minLength": 1, "maxLength": 100 },
    "pain_points": { "type": "string", "minLength": 3, "maxLength": 500, "description": "What the user dislikes about the current tool" },
    "must_keep": { "type": "array", "items": { "type": "string", "maxLength": 100 }, "maxItems": 5, "description": "Features the replacement must keep" },
    "os": "…共用", "arch": "…共用", "budget": "…共用", "must_run_locally": "…共用",
    "ui_language": "…共用", "exclude": "…共用", "limit": "…共用"
  },
  "required": ["current_software", "pain_points"],
  "additionalProperties": false
}
```

outputSchema：同 `find_software`，另加

```json
{
  "current": {
    "type": "object",
    "properties": { "matched_slug": { "type": ["string", "null"] }, "known": { "type": "boolean" } },
    "required": ["known"]
  },
  "keep_current": {
    "type": ["object", "null"],
    "properties": { "recommended": { "type": "boolean" }, "reason": { "type": "string", "maxLength": 300 } },
    "required": ["recommended", "reason"]
  }
}
```

annotations：`{ "readOnlyHint": true, "openWorldHint": false }`

#### `get_install_guide`

description：

```text
Use after the user picks a tool from find_software or find_alternatives. Returns install and setup steps that pickfit actually ran in a sandbox (with OS, date and evidence), marks which steps the agent can run and which the user must do by hand (permissions, sign-ups, API keys), and gives a command to verify the install plus a first task to try. Show each command to the user before running it, and ask before any step that needs sudo. If applies_to_user_system.match is not "exact", tell the user the steps were verified on a different system. After the user tries it, call report_outcome.
```

inputSchema：

```json
{
  "type": "object",
  "properties": {
    "slug": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]{1,63}$" },
    "os": { "enum": ["macos", "linux", "windows"] },
    "arch": { "enum": ["arm64", "x86_64"] },
    "available_tools": {
      "type": "array", "maxItems": 15,
      "items": { "enum": ["brew", "apt", "dnf", "pacman", "winget", "scoop", "npm", "pnpm", "pipx", "uv", "pip", "cargo", "go", "docker", "nix"] },
      "description": "Package managers already installed, if known"
    },
    "rec_id": { "type": "string", "maxLength": 200 }
  },
  "required": ["slug", "os"],
  "additionalProperties": false
}
```

outputSchema：

```json
{
  "type": "object",
  "properties": {
    "slug": { "type": "string" },
    "name": { "type": "string" },
    "version_tested": { "type": ["string", "null"] },
    "verification": {
      "type": "object",
      "properties": {
        "status": { "enum": ["passed", "partial", "failed", "unverified"] },
        "os": { "type": ["string", "null"] }, "arch": { "type": ["string", "null"] },
        "checked_at": { "type": ["string", "null"], "format": "date-time" },
        "log_url": { "type": ["string", "null"], "format": "uri" },
        "screenshot_url": { "type": ["string", "null"], "format": "uri" }
      },
      "required": ["status", "checked_at"]
    },
    "applies_to_user_system": {
      "type": "object",
      "properties": {
        "match": { "enum": ["exact", "same_os_other_arch", "other_os", "none"] },
        "note": { "type": ["string", "null"], "maxLength": 300 }
      },
      "required": ["match"]
    },
    "prerequisites": { "type": "array", "maxItems": 10, "items": {
      "type": "object",
      "properties": { "name": { "type": "string" }, "check_command": { "type": ["string", "null"] }, "install_command": { "type": ["string", "null"] } },
      "required": ["name"] } },
    "steps": { "type": "array", "maxItems": 20, "items": {
      "type": "object",
      "properties": {
        "order": { "type": "integer", "minimum": 1 },
        "title": { "type": "string", "maxLength": 150 },
        "command": { "type": ["string", "null"], "maxLength": 1000 },
        "run_by": { "enum": ["agent", "user"] },
        "needs_sudo": { "type": "boolean" },
        "needs_network": { "type": "boolean" },
        "expected": { "type": ["string", "null"], "maxLength": 300 }
      },
      "required": ["order", "title", "run_by"] } },
    "manual_steps": { "type": "array", "maxItems": 10, "items": {
      "type": "object",
      "properties": { "title": { "type": "string" }, "why": { "type": "string" }, "how": { "type": "string" } },
      "required": ["title", "how"] } },
    "verify": {
      "type": "object",
      "properties": { "command": { "type": "string" }, "expected_contains": { "type": ["string", "null"] } },
      "required": ["command"]
    },
    "first_task": { "type": ["object", "null"], "properties": { "description": { "type": "string" }, "command": { "type": ["string", "null"] } }, "required": ["description"] },
    "uninstall": { "type": "array", "items": { "type": "string" }, "maxItems": 5 },
    "known_issues": { "type": "array", "maxItems": 5, "items": {
      "type": "object", "properties": { "symptom": { "type": "string" }, "fix": { "type": "string" } }, "required": ["symptom", "fix"] } },
    "warnings": { "type": "array", "items": { "type": "string", "maxLength": 300 }, "maxItems": 5,
                  "description": "e.g. a step pipes a remote script into a shell" },
    "sources": { "type": "array", "items": { "type": "string", "format": "uri" }, "maxItems": 5 }
  },
  "required": ["slug", "verification", "applies_to_user_system", "steps", "manual_steps", "verify"]
}
```

annotations：`{ "readOnlyHint": true, "openWorldHint": false }`（工具本身不改任何東西；指令由 agent 在使用者同意下執行）。

安全：指令來自沙盒實跑的紀錄，不是直接轉貼 README。`warnings` 標出 `curl … | sh` 這類步驟。指令文字仍是不可信內容，靠 description 要求 agent 先給使用者看。

unknown slug 時回 `isError: true`，訊息附「先呼叫 find_software」。

#### `report_outcome`

description：

```text
Call once after the user tried a tool that pickfit recommended: whether it installed, whether the first run worked, and whether the user is satisfied. Pass the rec_id from the recommendation. This feeds pickfit's quality score; pickfit stores no account or IP. Do not put names, file paths, tokens or other personal data in error_excerpt or comment. If the install failed, the result may include a fix or alternatives.
```

inputSchema：

```json
{
  "type": "object",
  "properties": {
    "slug": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]{1,63}$" },
    "rec_id": { "type": "string", "maxLength": 200 },
    "stage": { "enum": ["installed", "install_failed", "first_run_ok", "first_run_failed", "abandoned", "still_using", "replaced"] },
    "satisfaction": { "enum": ["satisfied", "neutral", "dissatisfied", "unknown"], "default": "unknown" },
    "os": { "enum": ["macos", "linux", "windows"] },
    "arch": { "enum": ["arm64", "x86_64"] },
    "failed_step": { "type": "integer", "minimum": 1, "maximum": 50 },
    "error_excerpt": { "type": "string", "maxLength": 1000, "description": "Last lines of the error, with usernames, paths and tokens removed" },
    "replaced_with": { "type": "string", "maxLength": 100 },
    "comment": { "type": "string", "maxLength": 300 }
  },
  "required": ["slug", "stage"],
  "additionalProperties": false
}
```

outputSchema：

```json
{
  "type": "object",
  "properties": {
    "accepted": { "type": "boolean" },
    "report_id": { "type": ["string", "null"] },
    "deduplicated": { "type": "boolean" },
    "counted_in_score": { "type": "boolean", "description": "false when rec_id is missing, invalid or expired" },
    "next": {
      "type": "object",
      "properties": {
        "kind": { "enum": ["none", "fix", "alternatives"] },
        "fix": { "type": ["string", "null"], "maxLength": 500 },
        "alternatives": { "type": "array", "items": { "type": "string" }, "maxItems": 3 }
      },
      "required": ["kind"]
    }
  },
  "required": ["accepted", "deduplicated", "counted_in_score", "next"]
}
```

annotations：`{ "readOnlyHint": false, "destructiveHint": false, "idempotentHint": true, "openWorldHint": false }`。`idempotentHint` 只有在 server 依 `rec_id`＋`stage` 去重時才成立。

#### `submit_software`（建議新增的第 5 個）

description：

```text
Use when the user (often the author) shares a GitHub repository or a Threads post about a software project and wants pickfit to evaluate it. pickfit reads it with Meta's Muse Spark, tries to install it in a sandbox, and lists it if it works. Processing takes several minutes: call again with the same url to check status. Developer CLI tools and local AI/LLM tools are verified today; other software is listed as unverified.
```

inputSchema：

```json
{
  "type": "object",
  "properties": {
    "url": { "type": "string", "format": "uri", "maxLength": 300, "description": "https URL of a GitHub repository or a Threads post" },
    "submitter_role": { "enum": ["author", "user", "unknown"], "default": "unknown" },
    "note": { "type": "string", "maxLength": 300 }
  },
  "required": ["url"],
  "additionalProperties": false
}
```

outputSchema：

```json
{
  "type": "object",
  "properties": {
    "submission_id": { "type": "string" },
    "status": { "enum": ["queued", "reading", "verifying", "listed", "listed_unverified", "rejected", "duplicate"] },
    "slug": { "type": ["string", "null"] },
    "reason": { "type": ["string", "null"], "maxLength": 300 },
    "check_again_after_s": { "type": ["integer", "null"], "minimum": 10 }
  },
  "required": ["submission_id", "status"]
}
```

annotations：`{ "readOnlyHint": false, "destructiveHint": false, "idempotentHint": true, "openWorldHint": true }`（會去抓外部 URL）。

要不要做：值得，因為 demo 第 5 步（作者貼連結 → 幾分鐘後出現在推薦）可以全在 agent 裡完成，也對上 Best Agentic Use-Case。但它依賴發現與驗證管線（11/1 才做），而且最容易被灌。**時間不夠時的砍法**：先只做網頁表單或 GitHub issue 模板，MCP 工具最後加。URL 只收 GitHub 與 Threads 網域，伺服器端再驗證。

### 5.5 annotations 總表

| 工具 | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | 對客戶端的影響 |
|---|---|---|---|---|---|
| `find_software` | true | — | — | false | Claude Code 可並行、可重送；Codex `writes` 模式不跳確認 |
| `find_alternatives` | true | — | — | false | 同上 |
| `get_install_guide` | true | — | — | false | 同上 |
| `report_outcome` | false | false | true | false | Codex `writes` 模式會跳確認；Claude Code 可重送 |
| `submit_software` | false | false | true | true | 同上 |

規格的預設值：`readOnlyHint` false、`destructiveHint` true、`idempotentHint` false、`openWorldHint` true。不寫就會被當成「可能破壞、對外開放」。

---

## 6. Spike 結果

檔案與重跑方法：[spikes/mcp_stateless/README.md](../../../spikes/mcp_stateless/README.md)。

| 檢查 | Node | workerd（`wrangler dev`） |
|---|---|---|
| legacy `initialize`，回應沒有 `Mcp-Session-Id` | 通過 | 通過 |
| legacy 不帶 session 直接 `tools/list`、`tools/call` | 通過 | 通過 |
| modern `server/discover`、`tools/list`、`tools/call` | 通過 | 通過 |
| 少 `Mcp-Name` header → 400 `-32020` | 通過 | 通過 |
| 不支援的版本 → 400 `-32022` | 通過 | 通過 |
| 輸入不合 schema → `isError: true` | 通過 | 通過 |
| 官方 TS client：legacy／auto／pin 2026-07-28 | 通過 | 通過 |
| 官方 Python client 2.3.0：legacy／auto | 通過 | 未跑 |
| 每次請求成本（暖機） | ≈1.2 ms | 1–8 ms wall time |

實測發現：

- `server/discover` 的 `supportedVersions` 只列 `2026-07-28`，但同一端點仍服務 legacy（`2025-03-26`、`2025-11-25` 的 `initialize` 都成功）。
- legacy 回應是 SSE、modern 回應是單一 JSON。
- SDK 預設 `ttlMs: 0`、`cacheScope: "private"`。

沒做到的：沒有部署到 Cloudflare 線上（需要帳號）；沒有用 Claude Code、Codex、Cursor 實際連線（需要公開 URL 或本機互動式 CLI）。

---

## 7. 未驗證／待確認

| 項目 | 為什麼重要 | 怎麼確認 |
|---|---|---|
| 線上 Workers Free 的冷啟動 CPU 是否超過 10 ms | 超過會回 Error 1102 | 部署後看 dashboard；或直接開 Paid（每月 5 美元） |
| Workers Rate Limiting binding 在 Free 方案能不能用 | 防濫用主力 | 部署時試 |
| Codex 預設用哪個協定世代（`codex mcp add <name> --url <url>` 不帶 OAuth 已確認可寫入設定，見 4 節） | 影響 README 的安裝說明 | 登入 Codex 後實連 |
| Claude Code 實際把 `content` 還是 `structuredContent` 給模型 | 決定理由要寫在哪 | 兩者都放（已是建議做法） |
| Claude Desktop custom connector、Cursor 對 2026-07-28 的支援 | dual-era server 下影響不大 | 部署後實連 |
| WAF rate limiting rule 能否套在 `workers.dev` | 第二道防線 | 部署時看 |
| Muse Spark 在 `find_*` 的延遲 | Codex 預設工具逾時 60 秒 | D 節實測 |

---

## 8. 來源（查證日 2026-10-28）

| 主題 | URL |
|---|---|
| 規格版本 | https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning.md |
| 2026-07-28 Key Changes | https://modelcontextprotocol.io/specification/2026-07-28/changelog.md |
| Versioning and Compatibility（dual-era） | https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning.md |
| Streamable HTTP（2026-07-28） | https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md |
| `server/discover` | https://modelcontextprotocol.io/specification/2026-07-28/server/discover.md |
| Tools（2026-07-28） | https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md |
| Schema（ToolAnnotations） | https://modelcontextprotocol.io/specification/2026-07-28/schema.md |
| Transports（2025-11-25，session id MAY） | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports.md |
| Schema（2025-11-25，outputSchema 限 object） | https://modelcontextprotocol.io/specification/2025-11-25/schema.md |
| draft changelog | https://modelcontextprotocol.io/specification/draft/changelog.md |
| Inspector protocol eras | https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/protocol-eras.md |
| SDK 列表 | https://modelcontextprotocol.io/docs/2026-07-28/sdk.md |
| TS SDK v2 文件索引 | https://ts.sdk.modelcontextprotocol.io/v2/llms.txt |
| TS SDK：HTTP、web-standard、legacy、tools、protocol versions | https://ts.sdk.modelcontextprotocol.io/v2/serving/http.md 、…/serving/web-standard.md 、…/serving/legacy-clients.md 、…/servers/tools.md 、…/protocol-versions.md |
| Python SDK：what's new、protocol versions、legacy clients、deploy、tools、structured output | https://py.sdk.modelcontextprotocol.io/whats-new/index.md 、…/protocol-versions/index.md 、…/run/legacy-clients/index.md 、…/run/deploy/index.md 、…/servers/tools/index.md 、…/servers/structured-output/index.md |
| npm／PyPI／crates.io | `npm view <pkg>`；https://pypi.org/pypi/mcp/json ；https://crates.io/api/v1/crates/rmcp |
| Cloudflare createMcpHandler | https://developers.cloudflare.com/agents/model-context-protocol/apis/handler-api/index.md |
| Cloudflare McpAgent（deprecated） | https://developers.cloudflare.com/agents/model-context-protocol/apis/agent-api/index.md |
| Workers limits／pricing | https://developers.cloudflare.com/workers/platform/limits/index.md 、https://developers.cloudflare.com/workers/platform/pricing/index.md |
| Workers Rate Limiting binding | https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/index.md |
| WAF rate limiting rules | https://developers.cloudflare.com/waf/rate-limiting-rules/index.md |
| Vercel | https://vercel.com/docs/mcp/deploy-mcp-servers-to-vercel |
| Modal | https://modal.com/docs/guide/webhooks.md 、https://modal.com/docs/examples/mcp_server_stateless |
| Claude Code MCP | https://code.claude.com/docs/en/mcp.md |
| Codex MCP | https://developers.openai.com/codex/mcp.md |
| Codex 的 rmcp 版本 | https://raw.githubusercontent.com/openai/codex/main/codex-rs/Cargo.toml |
| rmcp CHANGELOG | https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/main/crates/rmcp/CHANGELOG.md |
| Cursor MCP、install links | https://cursor.com/docs/mcp.md 、https://cursor.com/docs/mcp/install-links.md |
| Claude custom connectors | https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp |
| MCP Registry | https://modelcontextprotocol.io/registry/about.md 、…/remote-servers.md 、…/authentication.md 、…/registry-aggregators.md 、https://registry.modelcontextprotocol.io/v0.1/servers |

---

## 查核紀錄（2026-10-28）

查核者：另一個 agent，預設懷疑。方法：用 curl 抓官方文件原文比對；`npm view`、PyPI、crates.io 查套件；spike 全部重跑一次。

### 關鍵主張

| # | 主張 | 結果 | 依據 |
|---|---|---|---|
| 1 | Current 版本是 2026-07-28；draft changelog 是空的 | 正確 | [Versioning](https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning.md)：「The current protocol version is 2026-07-28」；[draft changelog](https://modelcontextprotocol.io/specification/draft/changelog.md) 只有一句 |
| 2 | 移除 `initialize` 與 `Mcp-Session-Id`（SEP-2567、SEP-2575）；`_meta` 帶版本與能力；server MUST 實作 `server/discover` | 正確 | [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog.md) Major changes 1–3 |
| 3 | POST 要帶 `MCP-Protocol-Version`、`Mcp-Method`；`tools/call` 要 `Mcp-Name`；不符回 400 `-32020` | 正確 | [Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md) Server Validation；`Mcp-Name` 也用在 `resources/read`、`prompts/get`。spike M4 重跑一致 |
| 4 | 只支援 modern 的 server 讓 legacy client 失敗；dual-era 可同端點服務兩代 | 正確 | [Versioning and Compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning.md) 相容矩陣。順手修正 1.3 節「modern client 遇到 legacy server」一列 |
| 5 | TS SDK v2 `createMcpHandler` 每請求一個 server，`legacy` 預設 `'stateless'`；legacy `initialize` 不回 `Mcp-Session-Id`；Node 與 workerd 都可用 | 正確 | [Legacy clients](https://ts.sdk.modelcontextprotocol.io/v2/serving/legacy-clients.md)。重跑：Node 與 `wrangler dev` 的 `initialize`（2025-11-25、2025-03-26）都 200、沒有 session header；legacy `GET /mcp` 405 |
| 6 | TS client `versionNegotiation` 預設 legacy，`auto` 才探測 `server/discover` | 正確 | [Protocol versions](https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions.md)：「Absent, or mode: 'legacy' … No probe」 |
| 7 | Claude Code 只有 v2 runtime 會問並使用 2026-07-28 | 正確，措辭已修 | [Claude Code MCP › MCP client runtimes](https://code.claude.com/docs/en/mcp.md)。原文是「會抓 feature flag 的 session 在 v2.1.232 起用 v2」，不是「依 flag 逐步開放」；不抓 flag 的 session 在 v2.1.274 起預設 v2。已改 0 節 #2 與 4 節 |
| 8 | `McpAgent` deprecated、feature-frozen；改用 `agents/mcp/server` 的 `createMcpHandler`（無狀態、不需 DO）；固定 `@modelcontextprotocol/server@2.3.1` | 正確 | [McpAgent](https://developers.cloudflare.com/agents/model-context-protocol/apis/agent-api/index.md)、[createMcpHandler](https://developers.cloudflare.com/agents/model-context-protocol/apis/handler-api/index.md)（皆 Last updated Oct 27, 2026）。`npm view agents@0.31.0 peerDependencies`：server／client `2.3.1`、sdk `1.32.1` |
| 9 | Workers Free：10 萬請求／天（超過 Error 1027）、10 ms CPU、50 subrequest；Paid 最低 5 美元／月 | 正確 | [Limits](https://developers.cloudflare.com/workers/platform/limits/index.md)（Oct 12, 2026）、[Pricing](https://developers.cloudflare.com/workers/platform/pricing/index.md)（Oct 2, 2026） |
| 10 | 線上冷啟動 CPU 是否超過 10 ms | 仍未驗證 | 需部署。新增本機 `wrangler check startup` 數據（啟動 active 57.2 ms），見 3.2 節 |
| 11 | Rate Limiting binding 10／60 秒、各機房分開、近似；不建議 IP 當 key；Free 可否用文件沒寫 | 前半正確；Free 仍未驗證 | [Rate Limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/index.md)（Oct 21, 2026）；Limits、Pricing 頁也沒提。補 GA 日期 2025-09-19 |
| 12 | 2025-11-25 `outputSchema` 根節點限 object、`structuredContent` 是 object；2026-07-28 放寬 | 正確 | [2025-11-25 schema](https://modelcontextprotocol.io/specification/2025-11-25/schema.md)「Currently restricted to type: "object" at the root level」；2026-07-28 changelog Minor 10（SEP-2106） |
| 13 | Codex `[mcp_servers.<name>] url=`；`writes` 只對沒標 read-only 的工具跳確認；`instructions` 前 512 字元自足 | 正確 | [Codex MCP](https://developers.openai.com/codex/mcp.md)。另實測 Codex CLI 0.165.0：`codex mcp add pickfit --url …` 不帶 OAuth 可寫入設定（暫存 `CODEX_HOME`，已刪） |
| 14 | Claude custom connector 從 Anthropic 雲端連線、URL 要公開；Free 限 1 個 | 正確 | [Custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)：「Free users are limited to one custom connector」「must be reachable over the public internet from Anthropic's IP ranges」 |
| 15 | Registry preview、主要給 aggregator；GitHub 登入得 `io.github.<帳號>/*`；已有 toolradar、topalternativesto | 正確，措辭小修 | [About](https://modelcontextprotocol.io/registry/about.md)、[Authentication](https://modelcontextprotocol.io/registry/authentication.md)；API 搜尋 `toolradar` 回 3 筆（含 `streamable-http` remote）、`topalternativesto` 1 筆。「每小時」是文件的舉例，已改 |

### 其他順手查的

| 項目 | 結果 |
|---|---|
| 1.1 版本表（2025-03-26 引入 Streamable HTTP；2025-06-18 引入 structured output、elicitation、版本 header、移除 batching） | 正確（兩版 changelog） |
| 2.1 套件版本：server／client 2.4.0、node 2.1.2、sdk 1.32.2、`mcp` 2.3.0（2026-10-02，MIT；2.0.0 於 2026-07-28）、`mcp-handler` 2.3.0、zod 4.6.7 | 正確。`@modelcontextprotocol/sdk` 授權原寫「—」，實為 MIT，已補 |
| zod ≥4.5.0 省記憶體 | 正確，出處是 Workers Limits 頁的 Memory 一節 |
| Python SDK：`FastMCP` → `MCPServer`；`stateless_http=True` 只影響 legacy；Host 不在 allowlist 回 421；`content` 是模型唯一看得到的部分 | 正確（what's new、legacy clients、deploy、structured output 各頁） |
| Claude Code：instructions 與預載 description 4,096 字元、tool search 16,384；`readOnlyHint` 並行；`idempotentHint`／`readOnlyHint` 斷線可重送一次；輸出 10k 警告、25k 上限、50,000 字元存檔 | 正確 |
| 規格 Tools：server MUST 驗證輸入、存取控制、限流、清理輸出；structured content SHOULD 另附 JSON 文字 | 正確。另補 handle 的 Opacity 建議到 5.2 節 |
| WAF Free：1 條規則、以 IP 計、10 秒週期 | 正確（[Rate limiting rules › Availability](https://developers.cloudflare.com/waf/rate-limiting-rules/index.md)） |
| Inspector 預設 `legacy` | 正確 |
| Codex 釘 rmcp `=3.5.1` | 正確（Codex `Cargo.toml`；rmcp 3.5.1 changelog 有 2026-07-28 相關修正）。Codex client 預設用哪一代仍未驗證 |
| Scorecard／CHAOSS／ecosyste.ms | 本檔沒有相關主張，未查 |

### Spike 重跑（`spikes/mcp_stateless/`）

| 檢查 | Node 22.22.0 | `wrangler dev`（wrangler 4.153.0） |
|---|---|---|
| `curl.sh` L1–L3、M1–M6 | 與 README 一致 | 與 README 一致 |
| `client.mjs` legacy／auto／pin | 全過；era 為 legacy／modern／modern | 全過 |
| `py_client.py`（`mcp==2.3.0`） | legacy 2025-11-25、auto 2026-07-28，全過 | 未跑 |
| `bench.mjs` | 暖機 1.25–1.41 ms；首次 `tools/list` 55–58 ms | — |

金鑰檢查：spike 目錄（不含 `node_modules`、`.wrangler`）沒有 key、token、secret；`.gitignore` 排除 `node_modules/`、`.wrangler/`。重跑沒有在 spike 目錄留下新檔。
