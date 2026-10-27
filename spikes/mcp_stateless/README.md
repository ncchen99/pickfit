# spike: mcp_stateless

最小的無狀態 Streamable HTTP MCP server（官方 TypeScript SDK v2），含一個回傳**假資料**的 `find_software`。
同一份 `worker.mjs` 可以當 Cloudflare Workers 的 default export。2026-10-28 實測。

## 檔案

| 檔案 | 做什麼 |
|---|---|
| `worker.mjs` | `createMcpHandler(factory)`；註冊 `find_software`（inputSchema、outputSchema、annotations）；`export default handler` |
| `serve.mjs` | 本機用 `node:http` 掛上 handler，只綁 127.0.0.1:8787，前面加 Host／Origin 檢查 |
| `curl.sh` | 用 curl 打兩個協定世代：legacy（2025-11-25，有 `initialize`）與 modern（2026-07-28，無 handshake） |
| `client.mjs` | 用官方 `@modelcontextprotocol/client` 分別以 legacy、auto、pin 2026-07-28 連線並呼叫工具 |
| `py_client.py` | 用官方 Python SDK v2 `Client` 呼叫同一台 TS server（跨 SDK） |
| `bench.mjs` | 在同一個 process 內連打 300 次，估每次請求的成本 |
| `wrangler.toml` | 用 `wrangler dev` 在真的 Workers runtime（workerd）裡跑 `worker.mjs` |

## 怎麼跑

```bash
cd spikes/mcp_stateless
npm install                      # @modelcontextprotocol/server 2.4.0、client 2.4.0、node 2.1.2、zod 4.6.7
node serve.mjs &                 # http://127.0.0.1:8787/mcp
bash curl.sh                     # 9 個 raw HTTP 檢查
node client.mjs                  # 官方 TS client，三種連線模式
uv run --no-project --with mcp==2.3.0 python py_client.py   # 官方 Python client
node bench.mjs                   # 不需要先啟動 server
# 選用：Workers runtime
npx wrangler@4.153.0 dev --port 8788 --ip 127.0.0.1
MCP_URL=http://127.0.0.1:8788/mcp bash curl.sh
```

環境有 HTTPS proxy 時，打本機要加 `--noproxy '*'`（curl.sh 已加）或 `NO_PROXY='*'`。

## 結果（2026-10-28，Node 22.22.0）

| 檢查 | 結果 |
|---|---|
| L1 legacy `initialize` | 200，SSE 回應，**沒有 `Mcp-Session-Id` header** |
| L2 legacy `tools/list`，不帶 session id | 200；工具定義含 `outputSchema`、`annotations` |
| L3 legacy `tools/call` | 200；同時有 `content`（JSON 字串）與 `structuredContent` |
| legacy `GET /mcp` | 405（沒有獨立 SSE stream） |
| M1 modern `server/discover` | 200 JSON；`supportedVersions: ["2026-07-28"]`、`ttlMs: 0`、`cacheScope: "private"` |
| M2 modern `tools/list` | 200 JSON；`resultType: "complete"` |
| M3 modern `tools/call`（帶 `Mcp-Method`、`Mcp-Name`） | 200 JSON；server 端看到 `era: "modern"` |
| M4 modern 少了 `Mcp-Name` header | 400，`-32020` HeaderMismatch |
| M5 輸入不合 schema（`need` 太短） | 200，`isError: true`（模型看得到的工具錯誤，不是協定錯誤） |
| M6 不支援的版本 `2099-01-01` | 400，`-32022`，`data.supported: ["2026-07-28"]` |
| TS client：legacy／auto／pin | 都成功；era 分別是 legacy／modern／modern |
| Python client 2.3.0：legacy／auto | 都成功；protocol_version 分別是 2025-11-25／2026-07-28 |
| `wrangler dev`（workerd） | 上面 L1–M6 與 TS client 三種模式全部相同結果 |
| bench（Node，同 process） | 暖機後每次 ≈1.2 ms；第一次 `tools/list` ≈55 ms |
| workerd 本機 wall time（20 次） | 第一次 14 ms，之後 1–8 ms，平均 4 ms |

注意：Node 的時間和 workerd 本機的 wall time 都不等於 Cloudflare 線上的 CPU time。Free 方案每次請求 10 ms CPU 的限制，部署後要在 dashboard 再看一次。
