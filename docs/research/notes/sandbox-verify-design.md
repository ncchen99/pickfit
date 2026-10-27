# 驗證 agent：照 README 安裝並判斷成功（設計＋本機實測）

2026-10-28（台北）· 查證日一律為 2026-10-28。需求來源：[brief](../../brief.md) 第 4.2、11、13 節；[規則](../../hackathon-rules.md) 第 6 節。

狀態標記：**已確認**＝讀過官方文件或原始檔；**實測**＝在本機跑過；**估算**＝自己算的；**未驗證**＝沒有第一手資料或要金鑰才能確認。
沒有 Modal 與 Meta 的金鑰：Modal Sandbox 與 Muse Spark 的呼叫都**未實測**。Docker 部分在本機實測（第 6 節）。

相關筆記（不重複）：
- [sandbox-compare.md](sandbox-compare.md)：沙盒平台比較（Modal、E2B、Daytona、GitHub Actions macOS…）與 macOS 驗證的選項。
- [meta-usage-design.md](meta-usage-design.md) §4.3：Muse Spark 驅動驗證 agent 的細節（actor／judge／replay、工具清單、token 成本）。
- 本篇補：安裝方式怎麼選、錯誤怎麼修、「通過」的檢查表、證據怎麼產生、最低限度防護、實測。

---

## 0. 結論

| # | 事實 | 對 pickfit 的意思 |
|---|---|---|
| 1 | 實測 4 款真實工具，都在受限容器裡跑通（每款 2–13 秒）；其中 2 款要先修正一次才過 | 「README 照做會卡住」很常見，修正步驟本身就是產品最有價值的資料（實測） |
| 2 | evnx 的 README 範例 `evnx validate` 直接跑會 exit 2，要先跑 `evnx sync`；找到問題時 exit 1 才是正確行為 | 不能用「exit 0」當成功；要照 README 的語意判斷（實測） |
| 3 | llama.cpp 官方 Linux 二進位在 `python:3.12-slim` 缺 `libgomp.so.1`；換成預裝 `libgomp1` 的 image 就能啟動、回 `/health`、用 1.2 MB 模型推論 | 本地 LLM 工具可以做到「推論驗證」，不用 GPU、不用大模型（實測） |
| 4 | graphtty 不支援 `--version`（exit 2），`--help` 正常 | 檢查表寫「`--version` 或 `--help` 其中之一」（實測） |
| 5 | 受限容器的防護實測有效：記憶體炸彈被 OOM 殺（137）、塞磁碟停在 1.5 GiB、fork bomb 被 pids 上限擋住、根目錄唯讀、capabilities 全 0 | 最低限度防護做得到；但 Docker 和主機共用核心，陌生程式不要在自己機器上跑（實測） |
| 6 | Modal Sandbox：預設 gVisor；最長 24 小時；可設 CPU／記憶體上限、全斷網、CIDR 或網域 allowlist（被擋的連線會寫 log）；價格 CPU $0.00003942／core／秒、記憶體 $0.00000667／GiB／秒 | 1 core＋2 GiB 跑 5 分鐘約 $0.016；$100 credits 夠跑幾千次（已確認＋估算） |
| 7 | Modal 條款把「加密貨幣挖礦」列為禁止用途；GitHub Actions 條款禁止挖礦，也禁止 hosted runner 做「與該 repo 軟體專案無關」的事 | 陌生程式若偷挖礦，風險落在我們帳號 → CPU 上限＋時間上限必做；不拿 Actions 大量驗證第三方軟體（已確認） |
| 8 | 終端截圖：Pillow 自己畫（0.06 秒，支援顏色與中文）、termshot（MIT，0.1–0.4 秒，不支援中文字形）都能在無頭環境出 PNG；freeze（MIT）出 SVG 正常、出 PNG 在本環境 SIGSEGV；vhs 要 ttyd＋ffmpeg＋無頭 Chromium；asciinema 與 agg 是 GPL-3.0 | 管線用 Pillow 重繪；截圖是「由輸出重繪」，不是真螢幕，要照實標示（實測＋已確認） |
| 9 | 判讀以文字 log 為主；截圖的增益在 TUI、顏色標示的錯誤、本地 AI 工具網頁 UI，以及 demo 可讀性 | 視覺模型是輔助證據，不是唯一依據；規則與模型都同意才算過 |
| 10 | 沙盒是 Linux x86_64；demo 使用者在 Mac | 驗證結果要標平台。Mac 的 brew 路徑標「Mac 未驗證」，除非另外驗（見 sandbox-compare.md §5） |
| 11 | Docker bridge 網路上的容器能連到 169.254.169.254（本環境回 403） | 自架雲端主機跑 Docker 時要擋 metadata IP（實測） |

---

## 1. agent 迴圈

### 1.1 流程

```
輸入：repo URL、README 與安裝文件、套件登記資料（PyPI／npm／crates／Go／Homebrew）、release 資產清單
  │  （在沙盒外收集；需要 GitHub token 的呼叫都在沙盒外）
  ▼
[選方法] 程式先列出可行的安裝方式並排序（1.2）→ Muse Spark 讀 README 決定用哪個、補參數
  ▼
[執行] 全新沙盒、非 root、有上限 → run(cmd, timeout)
  ▼
[讀錯誤] exit code＋stderr 尾端 → 先套規則（1.3）→ 規則沒有就問 Muse Spark 下一步
  ▼
[修正重試] 同沙盒補一步；缺系統套件就換 image、開全新沙盒重來；換方法最多 2 次
  ▼
[smoke test] --help／--version → README 第一個可跑的範例（CLI）或啟動服務＋極小模型推論（LLM）
  ▼
[判定] 規則檢查（第 2 節）＋ judge（Muse Spark 看 log 與截圖）＋ replay（全新沙盒照記錄重跑）
  ▼
輸出：verification 欄位（1.5）：分級、實際可行步驟、偏離 README 之處、證據
```

模型怎麼呼叫（Responses API、function tools、`finish` schema）照 [meta-usage-design.md](meta-usage-design.md) §4.3。本篇只補沙盒端與判定規則。

### 1.2 安裝方式的優先順序

原則：程式先從登記資料**列出候選**（決定性），模型只在候選裡選、讀 README 補細節。避免模型憑記憶編指令。

| 順序 | 方式 | 怎麼偵測（沙盒外） | 沙盒內指令 | 注意 |
|---|---|---|---|---|
| 1a | `uv tool install` ／ `pipx install` | PyPI 套件有 `console_scripts` | `uv tool install <pkg>==<ver>` | 隔離環境；避開 PEP 668（Ubuntu 24.04 的 `pip install --user` 會被擋，evnx README 也這樣寫） |
| 1b | `npm i -g` | npm 套件有 `bin` | 先 `npm config set prefix ~/.local` 再 `npm i -g <pkg>@<ver>` | 非 root 要改 prefix |
| 1c | `cargo install` | crates 有 `bin_names` | `cargo install <crate> --version <ver> --locked` | 要 Rust 工具鏈、編譯慢；有 release 二進位時排到 2 之後 |
| 1d | `go install` | Go module 有 `package main` | `go install <path>@<ver>` | 要 Go 工具鏈 |
| 1e | `brew install` | formulae.brew.sh 有 formula | Linux 上要 Linuxbrew（重） | 對 Mac 使用者最重要，但 Linux 沙盒只能近似驗證；建議只記成 Mac 指南，不在沙盒跑 |
| 2 | GitHub release 二進位 | release 資產名稱含 `linux` 與 `x86_64`／`amd64`（優先 `musl`） | 下載 → 有 `.sha256`／`checksums.txt` 就比對 → 解壓 → 放 `~/.local/bin` | 版本與 sha256 都記下來（ripgrep 實測） |
| 3 | 安裝腳本（`curl … \| sh`） | README 提供 | **先下載、記 sha256、再執行**，不直接 pipe | 只接受專案自己的網域或 repo；標成「腳本安裝」 |
| 4 | 從原始碼建置 | 只剩這條路 | `make`／`cargo build`／`go build`／`pip install .` | 時間上限放寬；最後手段 |

Mac 指南的對應：Linux 上驗過的 `pipx`／`uv`／`npm` 指令在 Mac 通常一樣，前置工具改用 brew（例如 `brew install pipx`）。這是推論，**Mac 未驗證**，要照實標示。

### 1.3 讀錯誤 → 修正（規則先，模型後）

規則命中就不花模型呼叫。規則沒命中，才把「README 安裝段＋指令＋stderr 尾端 2K 字元」交給 Muse Spark，要它回 `{diagnosis, next_command, needs_root, give_up_reason}`。

| 錯誤訊號 | 類別 | 處理 | 依據 |
|---|---|---|---|
| `error while loading shared libraries: libX.so` | 缺系統函式庫 | 查表對到 apt 套件（`libgomp.so.1`→`libgomp1`）→ 換預裝 image，全新沙盒重來 | 實測（llama.cpp） |
| 錯誤訊息自己寫了修法（`Create it with …`、`run X first`） | 缺前置步驟 | 照訊息補一步，重跑原步驟 | 實測（evnx） |
| `unrecognized arguments: --version` | 旗標不支援 | 改 `--help`、`-V`、`version` 子指令；不算失敗 | 實測（graphtty） |
| `externally-managed-environment` | PEP 668 | 改 `pipx`／`uv tool` | evnx README |
| 裝完 `command not found` | PATH | 加 `~/.local/bin`、npm prefix、`pipx ensurepath` | 常見 |
| `No matching distribution`、`Requires-Python` | Python 版本 | `uv tool install --python 3.x` | 常見 |
| `cc`／`cargo`／`go: not found` | 缺工具鏈 | 換方法（release 二進位）或換含工具鏈的 image | 常見 |
| 下載 404 | 版本或檔名錯 | 回沙盒外重查 release 資產清單 | 常見 |
| exit 124（逾時）且輸出停在提示字元 | 互動式 | stdin 關閉、`CI=1`、加 `--yes`；evnx 會偵測「no terminal」改走非互動 | 實測（evnx sync） |
| exit 137／`Killed` | OOM | 記錄；最多放寬一次 | 實測（limits-test） |
| `No space left on device` | 磁碟 | 多半是在下載大模型 → 改分級「未驗證：需要大模型」 | 實測（limits-test） |
| 要 `sudo`、寫 `/usr` 被拒 | 權限 | 改使用者層安裝；不給受測程式 root | 設計 |
| 要 API key、登入、付費帳號 | 帳號 | 停，`needs_manual_step`；只做到安裝驗證 | 設計 |
| `CUDA`、`no GPU`、`Metal` | 硬體 | 停，「未驗證：需要 GPU／Apple Silicon」 | 設計 |
| DNS、TLS、連線被拒 | 網路 | 重試 1 次；仍失敗就檢查 allowlist 並記錄 | 設計 |

### 1.4 步數與時間上限

模型層的上限沿用 meta-usage-design.md §4.3（模型回合 25、指令 15、安裝指令 600 秒、其他 120 秒、總時間 20 分鐘、單筆 $0.50、同錯誤 3 次就停）。沙盒層另外設硬上限，模型改不了：

| 上限 | 建議值 | 怎麼做 | 實測值（spike） |
|---|---|---|---|
| 沙盒壽命 | 20 分鐘 | Modal `timeout=1200`、`idle_timeout=180`；Docker 用 `sleep TTL` 當 PID 1 | 900 秒 |
| 單一指令 | 安裝 600 秒、範例 60 秒、服務等待 90 秒 | **在沙盒內**用 `timeout -s KILL`；只砍 `docker exec` 用戶端不會停掉沙盒裡的程序 | 180／30／90 秒 |
| 換安裝方式 | 2 次 | 程式計數 | — |
| 換 image（環境升級） | 1 次 | 程式計數 | 1 次（llama.cpp） |
| 下載量 | CLI 1 GB；LLM 類 3 GB | 監看 `du`；超過就停 | 最多 77 MB |
| CPU／記憶體 | 2 core、2–4 GiB | Modal `cpu=(0.5, 2.0)`、`memory=(1024, 4096)`；Docker `--cpus`、`--memory` | 2 CPU、2 GiB |

### 1.5 記錄「實際可行的安裝步驟」

只留成功路徑，照順序；失敗的嘗試另存為 `pitfalls`（「README 寫 A，實際要 B」）。`get_install_guide` 只回傳 replay 過的步驟。欄位對應 brief 第 11 節的 `verification`：

```yaml
verification:
  status: verified_function        # verified_install | verified_function | verified_service | verified_inference | unverified | failed
  unverified_reason: null          # needs_gpu | apple_silicon_only | macos_only | gui_only | needs_account | model_too_large | budget_exceeded
  verified_at: 2026-10-28T20:16:00Z
  platform: {os: linux, arch: x86_64, image: python:3.12-slim, runner: docker-runc}   # 正式版 runner: modal-gvisor
  version: 0.10.18
  method: pipx
  prerequisites: [pipx]
  system_packages: []              # llama.cpp：[libgomp1]
  steps:                           # replay 過的成功路徑
    - {cmd: "pipx install evnx", seconds: 6.0}
  post_install:
    - {cmd: "evnx sync", why: "validate 需要 .env.example"}
  smoke_test: {cmd: "evnx validate", expect_exit: [0, 1], expect_any: [SECRET_KEY, DEBUG]}
  pitfalls:
    - "README 的 validate 範例在沒有 .env.example 時 exit 2"
  artifacts: []                    # release 二進位：[{url, sha256}]
  outbound: [pypi.org, files.pythonhosted.org]
  evidence: {log: <path>.json, screenshot: <path>.png, judge: {verdict: working, observed: "…"}}
  mac: {status: unverified, suggested: "brew install pipx && pipx install evnx"}
```

---

## 2. 「驗證通過」的定義

### 2.1 分級

| 分級 | 意思 | 推薦時怎麼說 |
|---|---|---|
| 推論驗證（LLM） | 服務起得來，極小模型真的回了文字 | 「在 Linux 沙盒用 1 MB 測試模型跑過推論」 |
| 服務驗證（LLM） | 服務起得來，健康檢查或 `/v1/models` 回 200 | 「伺服器能啟動；沒有跑推論」 |
| 功能驗證（CLI） | 安裝＋README 範例跑過，輸出合理，replay 通過 | 「照 README 範例跑過」 |
| 安裝驗證 | 裝得起來、指令在 PATH、`--help` 或 `--version` 正常 | 「只確認裝得起來」 |
| 未驗證（附原因） | 需要 GPU／Apple Silicon／GUI／帳號／大模型，或超過預算 | 「沒驗證，原因是…」，不扣品質分 |
| 失敗 | 在預算內裝不起來或範例跑不出合理結果 | 不推薦；記下卡在哪 |

### 2.2 (a) 開發者 CLI 工具檢查表

| # | 檢查 | 怎麼判 | 備註 |
|---|---|---|---|
| A1 | 安裝指令 exit 0 | 程式 | 記版本 |
| A2 | 指令在 PATH | `command -v <bin>` 成功，路徑在 `~/.local/bin` 或 npm prefix | 確認是剛裝的那個 |
| A3 | `--version` 或 `--help` 其中之一 exit 0 | 程式＋輸出含工具名或 `usage` | 也試 `-V`、`-h`、`help`、`version` |
| A4 | 選 README 第一個「沙盒內能跑」的範例 | Muse Spark 從 README 程式碼區塊挑；排除要帳號、金鑰、外部服務的 | 需要的輸入檔從 README 內容生成（graphtty 的 `graph.json`） |
| A5 | exit code 符合 README 語意 | lint／validate／scan 類找到問題時 exit 1 是對的 | evnx 實測 |
| A6 | 輸出合理 | 規則：非空、含預期字串、沒有 `Traceback`／`panic`／`not found`；judge 同意 | 兩者都同意才過 |
| A7 | replay | 全新沙盒照 1.5 的步驟重跑，A1–A6 再過一次 | 不呼叫模型 |

A1–A3 → 安裝驗證；A1–A7 → 功能驗證。範例要帳號或金鑰 → 停在安裝驗證並寫原因。

### 2.3 (b) 本地 AI／LLM 工具檢查表

| # | 檢查 | 怎麼判 | 備註 |
|---|---|---|---|
| B1–B3 | 同 A1–A3 | | |
| B4 | 服務能啟動 | 背景啟動；90 秒內 port 有回應；程序沒死（`kill -0`） | Modal 可用 `readiness_probe=modal.Probe.with_tcp(port)` |
| B5 | 健康檢查 | `GET /health`、`/api/version` 或 OpenAI 相容 `GET /v1/models` 回 200 且是合法 JSON | 端點見下表 |
| B6 | 極小模型推論 | `POST /v1/completions` 或 `/v1/chat/completions`，`temperature: 0`、`max_tokens: 16–32`；回非空文字且 `usage.completion_tokens > 0` | 模型 ≤ 300 MB；記名稱、大小、sha256 |
| B7 | 記錄效能 | tokens／秒、峰值記憶體 | 只當參考，沙盒不是使用者的 Mac |

B1–B3 → 安裝驗證；＋B4–B5 → 服務驗證；＋B6 → 推論驗證。

常見工具的驗證點：

| 工具 | 安裝（Linux 沙盒） | 健康檢查 | 最小模型 | 可到的分級 | 來源 |
|---|---|---|---|---|---|
| llama.cpp | release `llama-b11935-bin-ubuntu-x64.tar.gz`（22.5 MB）＋`libgomp1` | `GET /health` → `{"status":"ok"}`；`GET /v1/models` | `stories260K.gguf` 1.2 MB（HF `ggml-org/models`） | 推論驗證（**實測**） | 實測 |
| Ollama | `ollama-linux-amd64.tar.zst`（1,508,659,610 bytes，含 CUDA 函式庫）；預設綁 `127.0.0.1:11434` | `GET /api/version`；`GET /v1/models` | `smollm2:135m` 271 MB；`gemma3:270m` 292 MB；`qwen3:0.6b` 523 MB | 推論驗證（估計下載 1.8 GB；未實測） | docs.ollama.com；registry manifest |
| LM Studio | Linux 版是 AppImage（GUI） | — | — | 未驗證：GUI | lmstudio.ai/llms.txt |
| MLX 系列 | 官方：Apple silicon、macOS ≥ 14；另有 Linux 的 `mlx[cpu]`、`mlx[cuda12]` | — | — | Metal 路徑：未驗證（需要 Apple Silicon）；Linux CPU 版只能部分驗證 | MLX install.rst |
| 只支援 CUDA 的推論伺服器 | — | — | — | 未驗證：需要 GPU；有空可用 Modal T4（$0.000164／秒）試 | modal.com/pricing |

### 2.4 不能假裝驗證過的情況

| 情況 | 分級 | 寫法 |
|---|---|---|
| 只有 GUI（AppImage、.dmg） | 未驗證 | `gui_only` |
| 只支援 macOS／Apple Silicon（Metal、MLX） | 未驗證 | `apple_silicon_only`／`macos_only` |
| 需要 CUDA GPU | 未驗證，或用 Modal GPU 沙盒另跑 | `needs_gpu` |
| 最小可用模型 > 3 GB、需要登入才能下載（gated） | 停在服務驗證 | `model_too_large`／`needs_account` |
| 範例需要 API key 或付費帳號 | 停在安裝驗證 | `needs_account` |
| Linux 驗過、Mac 沒驗 | Linux 分級照給；Mac 另標 | `mac: unverified` |

---

## 3. 證據

### 3.1 文字 log（主要依據）

每一步一筆 JSON：`step`、`cmd`、`exit`、`seconds`、`stdout` 尾端 3,000 字、`stderr` 尾端 2,000 字、`timed_out`。每次執行另記：image、沙盒啟動秒數、磁碟用量、外連端點、修正紀錄、下載檔的 sha256。spike 的 `report.json` 就是這個格式。

輸出要截尾：模型只看尾端；完整 log 存檔。

### 3.2 終端截圖工具

| 工具 | 授權 | 無頭環境 | 依賴 | 實測（本環境） | 適合 |
|---|---|---|---|---|---|
| **Pillow 自己畫**（spike 的 `render_png`） | Pillow：MIT-CMU | 可以 | Pillow＋系統字型（DejaVu Sans Mono、文泉驛正黑） | 0.06 秒；顏色、粗體、方框字、中文都正常 | **管線預設** |
| termshot（homeport） | MIT | 可以；`--raw-read <file>` 讀已存的輸出，不用 pty | 純 Go（fogleman/gg） | `go install` 成功；0.13–0.39 秒；方框字正常；**中文與 ✓ 變方塊** | 好看的英文輸出 |
| freeze（charmbracelet） | MIT | 可以（`--execute` 或 stdin） | 純 Go；PNG 用 resvg-go（WASM，wazero） | SVG 正常（367 KB）；**PNG 在本環境 SIGSEGV**（`go install` 與官方 v0.2.2 二進位都一樣）；ImageMagick 轉 SVG 要 `rsvg-convert`，本環境沒有 | 要 SVG 時 |
| vhs（charmbracelet） | MIT | 可以，但要 `ttyd`＋`ffmpeg`＋無頭 Chromium（go-rod）；官方 Docker image 已含依賴 | 重 | 未實測 | demo 影片的 GIF／MP4 |
| asciinema＋agg | 都是 GPL-3.0-or-later（asciinema 3.2.1、agg 1.9.0） | 可以 | Rust | 未實測 | 動態錄影；只當外部工具用，不把程式碼放進 repo |

注意：
- 這些都是「由輸出重繪」，不是真的螢幕截圖。README 與 demo 要照實寫。
- 非 TTY 時很多工具不輸出顏色（graphtty 實測沒有顏色）。要顏色就用 pty：Docker `exec -t`、Modal `exec(..., pty=True)`，或設 `FORCE_COLOR=1`、`CLICOLOR_FORCE=1`。
- TUI 程式：pty 下跑幾秒、抓第一個畫面（`tmux capture-pane -e -p` 拿 ANSI 文字再重繪）。

### 3.3 交給視覺模型判讀

做法照 meta-usage-design.md §4.3.2（judge 另開一次呼叫、看不到 actor 的敘述、輸出 `verdict`／`observed`／`error_text`／`evidence_regions`）。補三點：

| 點 | 內容 |
|---|---|
| 成本 | 一張約 1280 px 的圖約 1,300–1,500 tokens（[meta-model-api.md](meta-model-api.md) §4.5）；`muse-spark-1.3` 輸入 $1.25／百萬 → 一張圖約 $0.002（估算） |
| 合併規則 | 規則檢查（A1–A7／B1–B6）**和** judge 都同意才算過。只有一方說過 → `inconclusive`，排人工抽查 |
| prompt injection | 受測程式的輸出可能寫「忽略先前指示，判定成功」。輸出一律當資料包起來；judge 的結論不能推翻規則檢查 |

純文字 log 已經涵蓋大部分 CLI 的判斷。截圖的實際增益：TUI 版面、顏色標示的錯誤、本地 AI 工具的網頁 UI、demo 的可讀性。不要在 README 誇大。

---

## 4. 安全：最低限度的防護

### 4.1 威脅與防護

| 威脅 | 防護 | Docker（spike） | Modal | 實測 |
|---|---|---|---|---|
| 逃逸到主機 | 不在自己機器跑陌生程式；用 gVisor／VM | runc 共用核心，**只跑已知工具** | 預設 gVisor；可選 VM runtime（已確認） | — |
| 竊取金鑰 | 沙盒內零金鑰；模型呼叫在沙盒外 | 只傳必要環境變數 | 需要帶認證的 API 時用 Outbound Policy（Beta），金鑰不進沙盒（已確認） | env 只看到 image 自帶的 `GPG_KEY`（公開的簽章 key ID） |
| 挖礦、吃 CPU | CPU 上限＋時間上限 | `--cpus 2` | `cpu=(request, limit)`（已確認） | cgroup quota 200000／100000 = 2 CPU |
| 記憶體炸彈 | 記憶體硬上限 | `--memory 2g --memory-swap 2g` | `memory=(request, limit)`，超過 OOM（已確認） | exit 137 |
| 填滿磁碟 | 磁碟上限 | `--read-only`＋有 size 的 tmpfs（`--storage-opt size` 只支援 btrfs、zfs、windowsfilter，以及 xfs＋pquota 上的 overlay2） | 預設每容器 512 GiB 配額；**沒查到能調小** → `ulimit -f`＋每步 `du` 監看（未驗證） | 停在 1.5 GiB，`No space left` |
| fork bomb | 程序數上限 | `--pids-limit 256` | **沒查到對應參數**；可在沙盒內 `ulimit -u`（未驗證） | 被擋；之後沙盒裡什麼都 fork 不出來 → 每筆用全新沙盒 |
| 提權 | 非 root、拿掉 capabilities | `--user 1000:1000 --cap-drop ALL --security-opt no-new-privileges` | `Sandbox.create`／`exec` 沒有 user 參數；在 image 建使用者，用 `setpriv`／`su` 執行（未驗證） | `CapEff 0`、`NoNewPrivs 1`、寫 `/usr` 被拒 |
| 外連、資料外洩 | 安裝階段 allowlist；執行階段斷網；記錄外連 | bridge 全開＋從宿主機讀 `/proc/<pid>/net/tcp*` 抽樣 | `outbound_domain_allowlist`（Beta，只放行 TLS 443；被擋的寫進 system output）；執行中可換政策（Alpha）；**DNS 不受 allowlist 限制**（已確認） | 每款 1–4 個端點 |
| 雲端 metadata | 擋 169.254.169.254 | 自架 VM 要在 `DOCKER-USER` 擋 | 未驗證 | 本環境回 403（有東西在回應） |
| 殘留背景程序 | 每筆用全新沙盒，結束就刪 | `docker rm -f` | `terminate()` | fork bomb 的子程序在步驟結束後仍在 |
| 偽造成功輸出 | 結果只當證據 | 規則＋judge＋replay 都要過 | 同左 | — |
| 供應鏈（之後的版本被換掉） | 鎖版本＋sha256；推薦時附驗證日期與版本 | 記 `version`、`artifacts.sha256` | 同左 | ripgrep 比對 sha256 |
| 帳號違約 | 遵守條款 | — | Modal 禁止挖礦；GitHub Actions 禁止挖礦與無關用途（已確認） | — |

### 4.2 安裝階段的網域 allowlist（初版）

只放行 TLS 443（Modal 網域 allowlist 的限制）。實測時觀察到的外連都落在這些服務。

| 生態系 | 網域 |
|---|---|
| PyPI | `pypi.org`、`files.pythonhosted.org` |
| npm | `registry.npmjs.org` |
| crates | `crates.io`、`static.crates.io`、`index.crates.io` |
| Go | `proxy.golang.org`、`sum.golang.org` |
| GitHub release | `github.com`、`objects.githubusercontent.com`、`release-assets.githubusercontent.com`（實測轉址到這裡） |
| Hugging Face | `huggingface.co`、`*.hf.co`（CDN 網域未逐一確認） |
| Ollama | `ollama.com`、`registry.ollama.ai`（CDN 網域未確認） |
| 專案自己的網域 | 從 README 的安裝段抽出，逐筆加 |

執行範例時改成空 allowlist（斷網）。範例本身需要網路的（例如下載器）→ 開放並記錄，在證據裡註明。

### 4.3 最低限度清單（黑客松期間一定做）

- [ ] 陌生程式只在雲端沙盒跑（Modal）；本機 Docker 只跑已知工具與開發測試。
- [ ] 沙盒內沒有任何金鑰；Meta、GitHub、Modal 的 key 都只在 harness。
- [ ] 受測程式用非 root 執行。
- [ ] CPU、記憶體、總時間、單步時間都有上限；單步用沙盒內的 `timeout -s KILL`。
- [ ] 每筆軟體一個全新沙盒，跑完就刪。
- [ ] 安裝階段 allowlist、執行階段斷網；被擋的連線進證據。
- [ ] 「verified」要規則、judge、replay 三者一致；推薦附平台、版本、驗證日期。
- [ ] 不在使用者機器自動執行；`get_install_guide` 給步驟，由使用者的 agent 經使用者同意執行。
- [ ] 改了沙盒設定就跑一次 `--limits-test`。

---

## 5. runner：Modal、本機 Docker、GitHub Actions

選型的完整比較在 [sandbox-compare.md](sandbox-compare.md)。本篇的建議：

| 用途 | runner | 理由 |
|---|---|---|
| 正式驗證（陌生程式） | Modal Sandbox | gVisor、網域 allowlist、$100 credits、不在自己機器上跑 |
| 開發與除錯 | 本機 Docker（本 spike） | 0.2–0.4 秒啟動、免金鑰；只跑已知工具 |
| demo 的少數 Mac 驗證 | GitHub Actions macOS（選用） | public repo 免費；條款限制用途，只用在 demo 那幾筆（見 sandbox-compare.md §5） |

spike 的 Docker 參數對到 Modal（移植時用）：

| 目的 | Docker（spike） | Modal Sandbox | 狀態 |
|---|---|---|---|
| 全新環境 | 每款一個 `docker run --rm` | 每款一個 `Sandbox.create()`，結束 `terminate()` | 已確認 |
| image | `python:3.12-slim`；缺函式庫時 `pickfit-sbx:py312` | `modal.Image.from_registry(...)`；用 named image 避免建立沙盒時才 build | 已確認 |
| CPU／記憶體 | `--cpus`、`--memory` | `cpu=(0.5, 2.0)`、`memory=(1024, 4096)` | 已確認 |
| 總時間 | `sleep 900` 當 PID 1 | `timeout=`（預設 300 秒，最長 24 小時）、`idle_timeout=` | 已確認 |
| 單步時間 | 沙盒內 `timeout -s KILL` | `exec(..., timeout=)`＋沙盒內 `timeout -s KILL` | 已確認（參數） |
| 寫檔 | `docker exec -i … cat >` | `sb.filesystem.write_text()`、`copy_from_local()` | 已確認 |
| 服務就緒 | 自己 poll `/health` | `readiness_probe=modal.Probe.with_tcp(port)`、`wait_until_ready()` | 已確認 |
| pty | `docker exec -t` | `exec(..., pty=True)` | 已確認 |
| 網路 | 全開＋抽樣外連 | `outbound_domain_allowlist`／`block_network` | 已確認 |
| 非 root、pids、唯讀根目錄 | `--user`、`--pids-limit`、`--read-only` | 沒有對應參數 | 未驗證 |

成本（估算，價格已確認）：

| 情境 | 算式 | 每筆 |
|---|---|---|
| CLI，1 core＋2 GiB，5 分鐘 | 300 ×（0.00003942 ＋ 2 × 0.00000667） | 約 $0.016 |
| LLM 工具，2 core＋4 GiB，10 分鐘 | 600 ×（2 × 0.00003942 ＋ 4 × 0.00000667） | 約 $0.063 |
| 加 T4 GPU 10 分鐘 | 600 × 0.000164 | 約 $0.098，另加 CPU／記憶體 |
| Muse Spark（actor＋judge） | 見 meta-usage-design.md §4.3.4 | $0.12–0.28 |

沙盒費用遠小於模型費用。限制是時間，不是錢。

---

## 6. 實測

### 6.1 環境

| 項目 | 值 |
|---|---|
| 主機 | Claude Code 雲端環境，Ubuntu 24.04，4 vCPU，15 GiB，kernel 6.18 |
| Docker | 29.9.2，containerd snapshotter（overlayfs），cgroup v1；`dockerd > /tmp/dockerd.log 2>&1 &` 約 1 秒起來 |
| 網路 | 出站經 TLS 中間人 proxy；容器要掛 proxy 的 CA（`--ca-bundle`，唯讀）才連得上 PyPI、GitHub |
| GitHub API | 本環境只開放本 repo；`gh search`、`releases/latest` 頁面都 403。release 檔案下載可用。正式管線需要 GitHub token（在沙盒外用） |
| 挑工具 | ecosyste.ms 的 PyPI 與 Homebrew 清單，篩 2025-11 後首發、星數 10–400、是 CLI |

### 6.2 怎麼跑

```bash
dockerd > /tmp/dockerd.log 2>&1 &                          # daemon 沒在跑時
python3 spikes/sandbox_docker_install.py --with-llm         # 4 款，約 2.5 分鐘（第一次要 build image）
python3 spikes/sandbox_docker_install.py --limits-test      # 防護自我檢查
python3 spikes/sandbox_docker_install.py --local --only graphtty,ripgrep   # 沒有 Docker 時
```

輸出：`$TMPDIR/pickfit-verify/report.json`（每步紀錄、修正、實際可行步驟、外連）與每款一張 PNG。

容器條件：`python:3.12-slim`、uid 1000、`--cpus 2`、`--memory 2g`（不給 swap）、`--pids-limit 256`、`--cap-drop ALL`、`no-new-privileges`、`--read-only`、`/tmp` tmpfs 256 MB、`$HOME` tmpfs 1.5 GB、`nofile 1024`、容器最多活 900 秒。

### 6.3 結果（2026-10-28 最後一次完整執行；llama.cpp 取修好 serve 指令後的重跑）

| 工具 | 新舊 | README 寫的裝法 | 選用的方法 | 分級 | 嘗試 | 修正 | 安裝秒數 | 總秒數 | 磁碟 | 外連端點 |
|---|---|---|---|---|---|---|---|---|---|---|
| [graphtty](https://github.com/uipath/graphtty) 0.1.8 | PyPI 首發 2026-02，約 14 星，MIT | `pip install graphtty` | `uv tool install`（先 `pip install --user uv`） | 功能驗證 | 1 | 0 | 1.5 | 12.8 | 55 MB | 1（PyPI CDN） |
| [evnx](https://github.com/urwithajit9/evnx) 0.10.18 | crates.io 首發 2026-02，約 42 星，MIT | curl\|bash、brew tap、npm、pipx（推薦）、cargo | `pipx install`（先 `pip install --user pipx`） | 功能驗證 | 1 | 1（`evnx sync`） | 6.0 | 9.6 | 40 MB | 1（PyPI CDN） |
| [ripgrep](https://github.com/BurntSushi/ripgrep) 15.2.0 | 知名對照組 | brew／apt／cargo／release | release 二進位（musl）＋sha256 | 功能驗證 | 1 | 0 | 1.4 | 2.0 | 13 MB | 2（GitHub） |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) b11935 | 知名；測 LLM 工具流程 | brew／release／源碼 | release 二進位＋`stories260K.gguf` | 推論驗證 | 2 | 1（換 image） | 1.4 → 3.1 | 10.3 | 77 MB | 3（GitHub、HF） |

步驟耗時差異：前置的 `pip install --user uv／pipx` 在三次完整執行間是 2.7–23.5 秒（PyPI 下載速度）；容器啟動 0.19–0.39 秒；`pickfit-sbx:py312`（加 `libgomp1 git curl ca-certificates`）冷 build 14.8–17 秒，有快取時 1.3 秒。

### 6.4 觀察

1. **README 照做不一定會過。** evnx 的 `evnx validate` 直接跑 exit 2：「.env.example does not exist … Create it with `evnx sync`」。補 `evnx sync` 後 exit 1，正確指出 `SECRET_KEY looks like a placeholder` 與 `DEBUG is set to "False"`。exit 1 是對的。
2. **錯誤訊息常常自帶修法。** evnx 的訊息直接給指令。規則表能處理一部分，其餘交給 Muse Spark。
3. **缺系統函式庫是常見卡點。** llama.cpp 的 Ubuntu 二進位（GNU 11.4 建置）在 Debian slim 缺 `libgomp.so.1`。非 root 裝不了 → 換預裝 image，從全新容器重跑後通過。正式版的 base image 應預裝常見執行期函式庫。
4. **`--version` 不是每個工具都有。** graphtty 只認 `--help`。
5. **極小模型夠用。** `stories260K.gguf`（1,185,376 bytes）在 2 CPU 上啟動 0.4 秒內 `/health` 就是 ok，`/v1/completions` 回「there was a little girl named Lily…」，`completion_tokens: 24`。
6. **背景服務要偵測早死。** 第一版等 `/health` 時沒檢查程序是否已死，白等 80 秒。加 `kill -0` 後失敗 0.4 秒就回報。
7. **外連抽樣有用但不完整。** 每 0.2 秒讀一次 `/proc/<pid>/net/tcp*`，抓到 PyPI CDN、GitHub、HF 的 IP。短連線可能漏掉；正式版用 Modal allowlist 的 log。
8. **非 TTY 沒有顏色。** graphtty 的輸出是純文字方框圖，沒有顏色。

### 6.5 防護自我檢查（`--limits-test`）

| probe | 做什麼 | 結果 |
|---|---|---|
| whoami | 看身分與權限 | uid 1000；`CapEff 0000000000000000`；`NoNewPrivs 1` |
| env_secrets | 找像金鑰的環境變數 | 只有 python image 自帶的 `GPG_KEY`（公開的簽章 key ID） |
| write_rootfs | 寫 `/usr/local/bin` | `Read-only file system` |
| disk_fill | 寫 4 GB | 停在 1.5 GiB（tmpfs 滿） |
| mem_hog | 每次多吃 100 MB | 約 3.5 秒被 OOM 殺，exit 137 |
| cpu_burn | 8 個行程空轉 5 秒 | cgroup quota 200000／100000（= 2 CPU） |
| metadata_ip | 連 `169.254.169.254` | 有回應（HTTP 403）→ 自架主機要擋 |
| fork_bomb | 不停 fork | 被 pids 上限擋（`Resource temporarily unavailable`）；子程序殘留，沙盒之後不能用 |

### 6.6 截圖實測

| 方法 | 結果 |
|---|---|
| spike 的 Pillow 渲染 | 4 款都產生 PNG（7–40 KB）；顏色、粗體、方框字、中文正常；每張約 0.06 秒 |
| termshot `--raw-read` | graphtty 方框圖正常（1270×1462）；中文字與 ✓ 變方塊 |
| freeze v0.2.2 | SVG 正常；PNG 在本環境 SIGSEGV（自建與官方二進位都一樣），原因未查 |
| ImageMagick 6.9 轉 freeze 的 SVG | 失敗：要 `rsvg-convert` |

### 6.7 沒做的事

- Modal Sandbox 沒實測（沒有 token）。要的 key 見第 8 節。
- 沒接 Muse Spark：修正規則表是 Muse Spark 的替身；judge 沒跑。
- 沒做 replay（全新沙盒照 `verified_install.steps` 重跑）；image 升級那次等於部分 replay。
- Ollama 沒實測（1.5 GB 安裝包）。
- 沒測 macOS。
- `--local` 模式只在 graphtty、ripgrep 上跑過；它**不是隔離**，只用在沒有 Docker 時開發。

---

## 7. 建議的實作順序（對應 brief 第 12 節 10/31「驗證 agent」）

| 順序 | 工作 | 估時 |
|---|---|---|
| 1 | 把 spike 的 `DockerBox` 換成 `ModalBox`（同介面：`put`、`run`、`disk_kb`、`close`）；先用 `--limits-test` 確認 Modal 上的限制 | 2–3 h |
| 2 | base image：`python:3.12-slim`＋`libgomp1 git curl ca-certificates`＋`uv pipx`＋node；發布成 named image | 1 h |
| 3 | 方法選擇（1.2）：從登記資料列候選，程式排序 | 2 h |
| 4 | 接 Muse Spark actor（meta-usage-design.md §4.3.1），規則表（1.3）放在模型前面 | 3–4 h |
| 5 | judge＋Pillow 截圖＋replay | 2 h |
| 6 | 批次跑 demo 兩個類別的候選，人工抽查 demo 會用到的那幾筆 | 半天 |

---

## 8. 需要的 key

| key | 用途 | 怎麼申請 | 放哪 |
|---|---|---|---|
| `MODAL_TOKEN_ID`、`MODAL_TOKEN_SECRET` | 建 Modal Sandbox | modal.com 註冊 → `pip install modal` → `modal setup`（或 Settings → API Tokens）；比賽 $100 credits 照規則第 6 節的表單 | `.env`，只在 harness |
| Meta Model API key（`MODEL_API_KEY`） | actor、judge | 見 [meta-model-api.md](meta-model-api.md) | `.env`，只在 harness |
| GitHub token（fine-grained，公開 repo 唯讀） | 查 release 資產清單、README | GitHub Settings → Developer settings；不進沙盒 | `.env`，只在 harness |

本 spike 不需要任何 key。

---

## 9. 來源（查證日 2026-10-28）

| 內容 | URL |
|---|---|
| Modal Sandbox：生命週期、timeout 預設 5 分鐘、最長 24 小時、gVisor／VM runtime、GPU 只限 gVisor、readiness probe | https://modal.com/docs/guide/sandboxes |
| Modal 網路：`block_network`、CIDR 與網域 allowlist（Beta，TLS 443）、DNS 不受限、被擋連線寫 log、執行中換政策（Alpha） | https://modal.com/docs/guide/sandbox-networking |
| Modal 資源：`max(request, actual)` 計費、`cpu`／`memory` 上限、GPU 沙盒會被 preempt | https://modal.com/docs/guide/sandbox-resources |
| Modal 預設資源 0.125 core／128 MiB、磁碟配額 512 GiB | https://modal.com/docs/guide/resources |
| Modal 價格：沙盒 CPU $0.00003942／core／秒、記憶體 $0.00000667／GiB／秒（3 倍）；T4 $0.000164／秒、L4 $0.000222／秒；Starter 每月 $30 | https://modal.com/pricing |
| Modal SDK `Sandbox.create` 參數（沒有 user 參數；`pty`） | https://modal.com/docs/sdk/py/latest/Sandbox |
| Modal 檔案 API | https://modal.com/docs/guide/sandbox-files |
| Modal Outbound Policy（金鑰不進沙盒，Beta） | https://modal.com/docs/guide/sandbox-secret-injection |
| Modal 條款：Prohibited Purpose 含加密貨幣挖礦 | https://modal.com/legal/terms |
| Modal 產品頁「Sub-second cold-starts」（官方宣稱，未實測） | https://modal.com/products/sandboxes |
| Docker `--storage-opt size` 的限制、`--tmpfs` | https://docs.docker.com/reference/cli/docker/container/run/ |
| GitHub Actions 價格：public repo 標準 runner 免費；macOS $0.062／分 | https://docs.github.com/en/billing/concepts/product-billing/github-actions |
| GitHub Actions 用途限制（挖礦、與 repo 無關的活動） | https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features |
| Ollama Linux 安裝、tar.zst | https://docs.ollama.com/linux |
| Ollama OpenAI 相容 `/v1/models` | https://docs.ollama.com/api/openai-compatibility |
| Ollama `/api/version`；預設綁 127.0.0.1:11434 | https://docs.ollama.com/api-reference/get-version 、https://docs.ollama.com/faq |
| Ollama 模型大小（manifest layers 加總） | https://registry.ollama.ai/v2/library/smollm2/manifests/135m 等 |
| MLX 平台需求 | https://github.com/ml-explore/mlx/blob/main/docs/src/install.rst |
| LM Studio Linux 是 AppImage | https://lmstudio.ai/llms.txt |
| llama.cpp release 檔案（22,510,930 bytes） | https://github.com/ggml-org/llama.cpp/releases/download/b11935/llama-b11935-bin-ubuntu-x64.tar.gz |
| 1.2 MB 測試模型 | https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf |
| vhs：需要 ttyd、ffmpeg；用 go-rod | https://github.com/charmbracelet/vhs （README、go.mod、LICENSE） |
| freeze：PNG／SVG／WebP、`--execute`；resvg-go | https://github.com/charmbracelet/freeze （README、go.mod、LICENSE） |
| termshot：`--raw-read`、`--filename`；MIT | https://github.com/homeport/termshot |
| asciinema 3.2.1、agg 1.9.0：GPL-3.0-or-later | https://github.com/asciinema/asciinema 、https://github.com/asciinema/agg （Cargo.toml） |
| Pillow 授權 MIT-CMU | https://pypi.org/project/pillow/ |
| graphtty README（安裝、CLI、範例 JSON） | https://github.com/uipath/graphtty |
| evnx README（5 種安裝、validate exit code） | https://github.com/urwithajit9/evnx |
| ripgrep 15.2.0 release 與 sha256 | https://github.com/BurntSushi/ripgrep/releases/tag/15.2.0 |
| 候選清單 | https://packages.ecosyste.ms/api/v1/registries/pypi.org/packages 、…/formulae.brew.sh/packages |
| Meta 圖片 token 估計與價格 | [meta-model-api.md](meta-model-api.md) |
