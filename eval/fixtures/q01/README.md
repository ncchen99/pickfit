# q01 測試資料：一份 MCP 清單同步到三個 agent

題目要一個免費、免帳號的命令列工具，維護一份 MCP server 清單，同步寫進 Claude Code、Codex CLI、Gemini CLI 的設定檔，而且不動其他設定。`sandbox: linux_sandbox`。

這個資料夾放 L2 項目用到的全部測試資料與檢查腳本。全部自己寫、合成、固定；沒有金鑰或 token。腳本只用 Python 3 標準函式庫（`seed/` 需要 3.11 以上，因為用 `tomllib`）或 POSIX sh。內容不含任何工具名稱或預期答案，對任何答案推薦的工具都一樣適用。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `server/fixture_mcp_server.py` | 凍結的 stdio MCP fixture server（名稱 `fixture-echo`，一個工具 `echo`）。只走 stdin／stdout，不連網、不寫檔 |
| `server/server.json` | 這個 server 的凍結定義：評分者透過答案的工具加進清單的就是這一筆 |
| `server/selftest.py` | 自我測試：啟動 server，跑 initialize、ping、tools/list、tools/call |
| `seed/locations.json` | 三個 agent 文件列出的每一個 MCP 設定位置（user 與 project scope），各自的一個無關設定 |
| `seed/seed_configs.py` | `seed`：寫入上面每個位置；`check`：檢查每個檔還在、還能解析、無關設定沒變 |
| `seed/validate_shape.py` | 只在校準判定某個 agent 的 list 指令不能離線、免登入執行時，代替該 agent 的 list 檢查 |
| `egress/run_traced.sh` | 在 strace 下執行一行指令，留下系統呼叫紀錄 |
| `egress/egress_check.py` | 讀紀錄，列出所有對外連線嘗試 |
| `needs.json` | 需要從外部取得、這裡沒有放的東西（三個 agent CLI 的固定版本、Node.js、strace、dev image） |
| `calibration.md` | 第一次開跑前要做的校準步驟與紀錄表（待填） |

## 2. 共同設定

- **環境**：dev image（定義見 `needs.json`；需要 `python3` 3.11 以上、`git`、`strace`）＋評分者事先裝好的三個 agent CLI 固定版本（版本記在 `calibration.md`）。使用者本來就在用這三個 agent，所以先裝好，再照答案裝工具。
- **路徑**：本資料夾複製到 `FIXTURE=/opt/eval/fixtures/q01`；評分紀錄放 `/opt/eval/state/`（不在任何 git repo 裡）；專案目錄 `PROJECT=/work/proj`（`git init` 過的空 repo）。`HOME` 用沙盒預設值（全新、空的）。
- **不登入**：`HOME` 裡沒有任何 agent 的登入檔，環境變數沒有任何 API key。執行 agent 指令一律用 `env -i HOME="$HOME" PATH="$PATH"`。
- **工作目錄**：答案的所有步驟與 agent 的 list 指令都在 `PROJECT` 裡執行，讓 user 與 project 兩層設定都看得到。

## 3. 名詞

- **原樣（verbatim）**：逐字複製答案的指令執行，只做 `eval/README.md` 第 5 節允許的調整（填版本號與佔位字、接受安裝程式的預設值）。任何一步 exit code 不是 0、或要改指令或旗標、補步驟才能成功，就不過。Ubuntu 擋下裸 `pip install` 時改在 venv 裡跑並記 `needed_venv`，但這一項不過。
- **egress check（對外連線檢查）**：把指定步驟的每一行指令包在 `egress/run_traced.sh` 裡執行，strace 記下它和所有子程序（包括留在背景的 daemon）的 `connect`、`sendto`、`sendmsg`、`sendmmsg`。之後 `egress/egress_check.py` 把以下都算成對外連線嘗試：目的地是非 loopback 的 IPv4／IPv6 位址；任何位址的 port 53（DNS，連 loopback 上的 stub resolver 也算，因為它會往外轉送）；其他能上網的 socket 家族（例如 `AF_PACKET`）。失敗的嘗試也算。`AF_UNIX`、`AF_NETLINK` 不算。結果 exit 0＝過；1＝不過；2＝紀錄裡沒有 strace 有效的證據（沒有 execve），這一步要修好追蹤方式後重跑，不能判過。
- **填入的 fixture server**：名稱 `fixture-echo`、transport stdio、command `python3`、args `["/opt/eval/fixtures/q01/server/fixture_mcp_server.py"]`、沒有 env（`server/server.json`）。答案的工具問要同步到哪些 agent 時，選這三個；其他問題接受預設值。

## 4. L2 項目

### 項目 1

> [L2] The answer's install steps succeed verbatim in the dev image

- **測試資料**：無（只用 dev image 與預先裝好的三個 agent）。
- **做法**：先做第 5 節流程的步驟 1–3（建專案、寫入設定），再在 `PROJECT` 裡逐行原樣執行答案的安裝步驟，記下每行的 exit code 與輸出。安裝步驟不在 egress check 範圍內（允許下載）。
- **判定**：每一行 exit code 都是 0，而且沒有超出第 5 節允許的調整 → 過。

### 項目 2

> [L2] Fixture: every MCP config location each pinned agent documents (user scope and project scope) is seeded with one unrelated setting. After adding the frozen stdio fixture MCP server through the tool and syncing, every seeded file still parses as JSON or TOML and every seeded unrelated setting is unchanged

- **測試資料**：`seed/locations.json`、`seed/seed_configs.py`、`server/`。寫入的位置與無關設定（凍結前依校準步驟 2 對照固定版本的文件再確認一次）：

  | id | 檔案 | 格式 | 無關設定 |
  |---|---|---|---|
  | claude-user | `$HOME/.claude.json`（也放 local scope） | JSON | `editorMode = "vim"` |
  | claude-project | `$PROJECT/.mcp.json` | JSON | 一筆使用者原本手動加的 server `keep-existing`（這個檔只有 `mcpServers`） |
  | codex-user | `$HOME/.codex/config.toml` | TOML | `[projects."/work/proj"] trust_level = "trusted"` |
  | codex-project | `$PROJECT/.codex/config.toml` | TOML | `model_reasoning_effort = "high"` |
  | gemini-user | `$HOME/.gemini/settings.json` | JSON | `ui.theme = "GitHub"` |
  | gemini-project | `$PROJECT/.gemini/settings.json` | JSON | `general.vimMode = true` |

  不寫入的：管理者層級（Claude Code 的 managed MCP）、系統層級（Gemini CLI 的系統設定）、extension／plugin 的設定，因為題目只說 user 與 project scope。
- **做法**：
  1. 在安裝答案的工具之前寫入：
     ```sh
     python3 $FIXTURE/seed/seed_configs.py seed --home "$HOME" --project /work/proj \
       --fixture $FIXTURE --state /opt/eval/state/q01-seeded.json
     ```
  2. 安裝之後，照答案的做法把 fixture server 加進工具的清單並同步到三個 agent。答案要求的初始化或匯入步驟、加入、同步，每一行都包在 egress check 裡執行（項目 4）：
     ```sh
     cd /work/proj
     sh $FIXTURE/egress/run_traced.sh /opt/eval/state/q01-egress-01.log '<答案的第一行指令，佔位字已填>'
     sh $FIXTURE/egress/run_traced.sh /opt/eval/state/q01-egress-02.log '<下一行>'
     ```
  3. **在執行任何 agent 指令之前**檢查（agent 自己可能會改寫自己的設定檔，所以先檢查）：
     ```sh
     python3 $FIXTURE/seed/seed_configs.py check --state /opt/eval/state/q01-seeded.json \
       --report /opt/eval/state/q01-check.json
     ```
- **判定**：`check` 印出 `RESULT PASS`（每個寫入的檔都還在、都能用 JSON 或 TOML 嚴格解析、無關設定與寫入時深度相等）→ 過。檔案被刪掉、出現 JSONC 註解或尾逗號而無法嚴格解析、無關設定被改或被刪，都不過。設定的值不變即可，排版、key 的順序、TOML 註解不要求保留（報告裡另外記註解是否保留，只供參考）。報告也列出每個檔裡有沒有 `fixture-echo`，只供參考，判定看項目 3。

### 項目 3

> [L2] With pinned versions of the three agent CLIs installed (versions recorded at freeze), each agent's own MCP list command, run with no login and with egress blocked, shows the new server. If pre-freeze calibration shows a pinned agent's list command cannot run offline without login, that agent is checked by validating its config against its documented schema instead, and the substitution is recorded before the freeze

- **測試資料**：項目 2 之後的設定檔；`server/fixture_mcp_server.py`（agent 的 list 指令會啟動它做健康檢查）；替代檢查用 `seed/validate_shape.py`。
- **做法**：項目 2 的檢查做完後，切到對外連線封鎖的環境（方式在校準步驟 6 決定並記錄，例如從同一個檔案系統快照另開不能上網的沙盒），不登入，在 `PROJECT` 執行：
  ```sh
  cd /work/proj
  env -i HOME="$HOME" PATH="$PATH" timeout 120 claude mcp list > /opt/eval/state/q01-list-claude.txt 2>&1
  env -i HOME="$HOME" PATH="$PATH" timeout 120 codex mcp list  > /opt/eval/state/q01-list-codex.txt 2>&1
  env -i HOME="$HOME" PATH="$PATH" timeout 120 gemini mcp list > /opt/eval/state/q01-list-gemini.txt 2>&1
  grep -F -w fixture-echo /opt/eval/state/q01-list-claude.txt   # 每個 agent 各查一次
  ```
  指令名稱以校準步驟 1 記下的固定版本為準。校準判定為替代的 agent，改跑：
  ```sh
  python3 $FIXTURE/seed/validate_shape.py --agent <claude-code|codex-cli|gemini-cli> \
    --state /opt/eval/state/q01-seeded.json
  ```
- **判定**：每個 agent 的 list 輸出都有 `fixture-echo` 這個完整名稱（`grep -F -w` 找得到）→ 該 agent 過；連線狀態（connected、pending approval、disconnected）不影響。替代的 agent 以 `validate_shape.py` 印出 `RESULT PASS` 為過：該 agent 會讀的某個位置裡，有一筆格式符合文件的 stdio 項目，而且 command 經 PATH 查找後與 `python3` 相同、args 與凍結定義相同。三個 agent 都過，這一項才過。list 指令逾時或要求登入（沒有事先登記替代）都算該 agent 不過。

### 項目 4

> [L2] Egress check passes for the add and sync steps

- **測試資料**：`egress/run_traced.sh`、`egress/egress_check.py`。
- **範圍**：安裝之後、為了把 fixture server 加進清單並寫進三個 agent 設定所執行的每一行答案指令（初始化或匯入、加入、同步）。安裝步驟、評分者自己的檢查與 agent 的 list 指令不算。
- **做法**：項目 2 的步驟 2 已經把每一行包在 `run_traced.sh` 裡。之後（可在沙盒裡，或把紀錄複製到評分者電腦上）：
  ```sh
  python3 $FIXTURE/egress/egress_check.py /opt/eval/state/q01-egress-*.log \
    --json /opt/eval/state/q01-egress.json
  ```
- **判定**：exit 0（`RESULT PASS`）→ 過；exit 1 → 不過，報告附上每一筆連線嘗試；exit 2 → 量測失敗，修好追蹤方式後在新沙盒重跑整個 q01 流程（答案原文不變），並記錄重跑原因。

## 5. 一次跑完的流程

1. 開新沙盒（dev image＋三個 agent 的固定版本），複製本資料夾到 `/opt/eval/fixtures/q01`，`mkdir -p /work/proj /opt/eval/state && git -C /work/proj init -q`。
2. `python3 $FIXTURE/server/selftest.py`：必須 `RESULT PASS`，否則是環境問題，先修環境。
3. 寫入設定（項目 2 的步驟 1）。
4. 原樣安裝（項目 1）。
5. 加入並同步，每行包 egress check（項目 2 的步驟 2、項目 4）。
6. `seed_configs.py check`（項目 2 的步驟 3）。
7. 封鎖對外連線、不登入，跑三個 list 指令或替代檢查（項目 3）。
8. `egress_check.py`（項目 4）。
9. 保存 `/opt/eval/state/` 全部檔案。這些檔案沒有機密，可以和結果一起 commit。

## 6. 外部材料與校準

- 三個 agent CLI 的固定版本、它們需要的 Node.js、strace、dev image：見 `needs.json`，由念誠決定後記在 `calibration.md`。這裡不下載、不放任何第三方檔案。
- 凍結前的校準（版本、設定位置、list 指令能不能離線免登入、替代登記、封鎖對外連線的方式、strace 是否可用）：見 `calibration.md`，在第一次開跑前做完並 commit。
