# q06 測試資料：OpenAPI 規格轉成 MCP server

題目在 [../../questions.yaml](../../questions.yaml) 的 q06。這裡放 q06 各 [L2] 項目用到的測試資料、檢查腳本與評分步驟。評分規則以 [../../README.md](../../README.md) 第 5 節與第 9.1 節為準。

所有檔案都是為這題自己寫的，只用 Python 3.8 以上的標準函式庫，不需要網路。API 是虛構的「庫存品項」API，和任何 MCP 工具無關。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `openapi.json` | 凍結的 OpenAPI 3.0.3 規格：`GET /items/{id}`（operationId `getItem`）與 `POST /items`（`createItem`） |
| `openapi.yaml` | 同一份規格的 YAML 版（已確認與 JSON 版解析後完全相同）；工具只讀 YAML 時用 |
| `post_body.json` | 凍結的 POST 內容：`{"name": "widget-alpha", "quantity": 3, "tags": ["blue", "small"]}` |
| `mock_api.py` | 本機假 API（127.0.0.1 與 ::1 的 18080 埠），每次啟動產生一個隨機 token，記錄每個請求 |
| `mcp_ref_client.py` | **固定版本的參考 MCP client**（stdio、streamable HTTP、舊版 HTTP+SSE） |
| `check_q06.py` | 從 client 報告、假 API 紀錄、egress 報告算出 L2-2、L2-3、L2-4 的判定 |
| `egress_run.py` | 記錄連線、計時、逾時的執行包裝（q05、q06、q07 三份相同） |
| `calib_mcp_server.py` | **只供校正**的 MCP server，證明整套檢查會讓正確的 server 過、壞的 server 不過；不是答案，也不給受測 agent 看 |
| `test_q06.py` | 本機自我測試（不需要 strace） |
| `needs.json`、`calibration.md` | 待決定的外部素材、開跑前的校正步驟與紀錄表 |

### 規格的設計

- 規格的 `servers` 是 `https://items-api.example.internal`，一個保留給內部用途、不會解析的網域。評分時要把 base URL **設成假 API**（`http://127.0.0.1:18080`）。工具若不理會設定、照規格裡的網址送出，呼叫會失敗，egress 檢查也會記到它查 DNS。
- 規格**沒有**宣告驗證方式；假 API 也不檢查驗證標頭（收到的話只記錄有沒有、長度多少）。
- `GET` 的回應內容含有假 API 這次啟動時產生的 token（`q06tok-` 加 16 個十六進位字），只有真的打到假 API 才拿得到。這不是機密，不需要保護。
- 請求主體的 schema 用 `$ref` 指到 `components`，和一般規格一樣。

## 2. 評分環境

- Modal Sandbox，x86_64；image 是第 5 節的開發 image 加上評分工具 `python3`、`strace`（見 `needs.json`）。記下 image digest。兩組用同一個 image。
- 目錄約定：`/opt/eval-q06/` 放本資料夾；`/work/api/` 放規格的副本；`/work/out/` 放紀錄。答案要求的專案目錄或產生的程式碼放 `/work/project/`。
- 安裝 20 分鐘逾時，每個檢查 10 分鐘逾時（第 5 節）。

## 3. 名詞

- **照步驟原樣（verbatim）**：同 q05：答案的指令逐字執行，只允許第 5 節的調整（填版本號與佔位字、接受預設值、`needed_venv`）。不可以修正錯的指令或旗標、補上缺的步驟。
- **只改設定值**（L2-2 的 "only config values changed"）：評分者只能把下面三種值填成本題的值，其他照答案：
  - 規格位置：`/work/api/openapi.json`（工具只讀 YAML 時用 `/work/api/openapi.yaml`；工具只收網址時用 `http://127.0.0.1:18080/openapi.json`）；
  - base URL：`http://127.0.0.1:18080`。答案說要在規格的 `servers` 裡改 base URL 時，只改 `/work/api/` 那份副本的 `servers[0].url`，凍結的原檔不動；
  - 驗證佔位字：答案的設定有 token、API key 之類的佔位字時，填一個執行時產生的假值：`python3 -c "import secrets; print('fake-' + secrets.token_hex(16))"`。這個值不寫進任何 commit。
- **產生的程式碼原樣使用**：答案的工具若先產生程式碼或專案，產生之後不改任何一行；需要的安裝、建置照答案做。
- **參考 MCP client**：`mcp_ref_client.py`，以測試資料凍結那個 commit 的版本為準（sha256 記在 `calibration.md`；每份 client 報告的 `client.sha256` 要與它相同）。它做的事：`initialize` → `notifications/initialized` → `tools/list`（翻完所有頁）→ 呼叫 GET 工具（id 42）→ 呼叫 POST 工具（`post_body.json`）。協定版本先送 `2025-06-18`，伺服器回什麼版本就用什麼版本。
- **egress 檢查**：同 q05 第 4 節的定義（`strace -f` 記下所有子程序的連線；目的地不是 loopback、任何 DNS 類埠、系統解析 socket、原始封包，都算一次嘗試，失敗的嘗試也算）。這題**不斷網**，只記錄。假 API 在被記錄的程序之外另外啟動；參考 client 與它啟動的 MCP server 一起被記錄。連到 loopback 都允許（包括 client 連 MCP server 的 HTTP 埠）；「只連到本機假 API」的意思就是除了 loopback 之外沒有任何連線嘗試。

## 4. 每個答案的流程

每個答案在**全新的 sandbox** 從頭做：

```sh
mkdir -p /work/api /work/out /work/project
cp /opt/eval-q06/openapi.json /opt/eval-q06/openapi.yaml /work/api/
python3 /opt/eval-q06/mock_api.py --port 18080 \
    --log /work/out/mock_log.jsonl --state /work/out/mock_state.json &
```

1. **安裝**（L2-1）：照答案逐條執行，每條記 exit code 與輸出。
2. **產生**（答案有這一步才做）：

   ```sh
   cd /work/project
   python3 /opt/eval-q06/egress_run.py --timeout 600 --report /work/out/gen.json -- <答案的產生指令>
   ```
3. **啟動＋兩個工具呼叫**，看答案的 server 用哪種傳輸：
   - stdio（答案給啟動指令，或給一段 MCP client 設定，例如 `{"command": …, "args": […], "env": {…}}`；設定裡的 command、args、env 原樣搬過來）：

     ```sh
     python3 /opt/eval-q06/egress_run.py --timeout 600 --report /work/out/session.json -- \
         python3 /opt/eval-q06/mcp_ref_client.py --report /work/out/client.json \
         --stdio [--env KEY=VALUE]... [--cwd /work/project] -- <答案的 server 指令>
     ```
   - streamable HTTP（答案給啟動指令與網址）：

     ```sh
     python3 /opt/eval-q06/egress_run.py --timeout 600 --report /work/out/session.json -- \
         python3 /opt/eval-q06/mcp_ref_client.py --report /work/out/client.json \
         --http http://127.0.0.1:<埠>/<路徑> --spawn '<答案的 server 啟動指令>' [--cwd /work/project]
     ```

     `--spawn` 讓 server 在同一個被記錄的程序樹裡啟動，結束時由 client 停掉。答案只提供舊版 HTTP+SSE 時用 `--sse <網址>`，並在紀錄註明（題目的硬條件是 stdio 或 streamable HTTP，屬 L1 判斷）。
   - client 自動對應工具與組參數失敗時（報告的 `errors` 會寫），評分者依工具的 `inputSchema` 用 `--get-tool`、`--get-args`、`--post-tool`、`--post-args` 指定，值只能表達「id 是 42」與 `post_body.json` 的內容，記下用了什麼。
4. **判定**：

   ```sh
   python3 /opt/eval-q06/check_q06.py --client-report /work/out/client.json \
       --mock-log /work/out/mock_log.jsonl --mock-state /work/out/mock_state.json \
       [--egress /work/out/gen.json] --egress /work/out/session.json --report /work/out/verdict.json
   ```

## 5. 各 [L2] 項目

### L2-1

> [L2] The install steps succeed verbatim in the dev image

- **用到**：只有乾淨的開發 image。
- **做法**：第 4 節第 1 步。
- **判定**：每條步驟都成功（exit 0，或答案說明的成功狀態）才過。

### L2-2

> [L2] Frozen fixtures: an OpenAPI 3.0 spec with GET /items/{id} and POST /items, and a mock API script on localhost. Following the answer, with only config values changed (spec path, base URL, auth placeholder) and any generated code used unmodified, a pinned reference MCP client lists exactly two tools that correspond to the two operations

- **用到**：`openapi.json`／`openapi.yaml`、`mock_api.py`、`mcp_ref_client.py`、`check_q06.py`。
- **做法**：第 4 節第 2–4 步。
- **判定**（`verdict.json` 的 `tools_list.pass`）：
  - `tools/list`（所有頁合計）剛好 **2 個**工具；多一個輔助工具（例如列出端點、通用呼叫）也不過；
  - 兩個工具能一對一對應到兩個操作：名稱、標題或說明對得上 operationId、摘要或「方法＋路徑」，或 `inputSchema` 分得出來（一個有 `id`、一個有請求主體的欄位）；以上都分不出來時，以行為為準：一個工具的呼叫讓假 API 收到 `GET /items/42`、另一個讓它收到 `POST /items`。
  - 啟動失敗、`initialize` 失敗、列不出工具，都不過。

### L2-3

> [L2] Calling the GET tool with id 42 returns content that includes the mock's unique token, and the mock's log shows GET /items/42; calling the POST tool with the frozen body makes the mock receive that JSON body

- **用到**：`mock_api.py`（token 在 `mock_state.json`、請求紀錄在 `mock_log.jsonl`）、`post_body.json`、`mcp_ref_client.py`、`check_q06.py`。
- **判定**（`tool_calls.pass`，三個條件都要）：
  - GET 工具的結果（`content` 與 `structuredContent` 全文）含有這次的 token，而且不是錯誤結果（`isError` 不是 true）；
  - 假 API 的紀錄有 `GET /items/42`；
  - 假 API 的紀錄有 `POST /items`，請求主體解析成 JSON 後**與 `post_body.json` 完全相同**（多欄位、少欄位、型別不同都不算）。

### L2-4

> [L2] Egress check passes for generation, startup and both tool calls (only the localhost mock is reached)

- **用到**：`egress_run.py`、第 4 節的 `gen.json`（有產生步驟時）與 `session.json`。
- **判定**（`egress.pass`）：給的每一份報告 `egress.verdict` 都是 `pass`。`npx`、`uvx` 之類在啟動時才去抓套件或查版本，也算對外連線嘗試。安裝步驟本身不在這項檢查內。

## 6. 自我測試（不是校正）

```sh
python3 test_q06.py            # 7 個案例：stdio、HTTP（JSON 與 SSE 回應）、舊版 SSE 都過；多一個工具、丟掉 POST 主體、base URL 錯都抓得到
python3 egress_run.py --selftest
```

2026-10-30 在 macOS 上跑過，全部符合預期。strace 只能在 Linux 上測，放在 `calibration.md`。
