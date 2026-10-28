# Demo 候選（P3.8）

2026-10-29 · 從 P2.6 的 39 份 profile 挑出。根據：Modal 驗證後寫回 `data/software/<slug>.json` 的 `VerificationRun`（`muse-spark-1.3`、gVisor、Linux x86_64），每次的完整證據在 `runs/verify/<run_id>/`（不進 git）。

## 條件

1. **免費**：`pricing` 是 `free`，或沒寫價格但有 OSI 開源授權。
2. **安裝後能離線**：全新沙盒重播時，先開網路安裝，再斷網跑 smoke test；`first_task` 斷網通過（record 的 `offline: true`）。
3. **在 Modal 驗證並重播成功**：agent、指令紀錄、全新沙盒重播、畫面判讀都過。
4. **macOS arm64 有官方安裝方式**：brew、pipx／uv（PyPI 純 Python wheel）、npm（套件沒有排除 darwin／arm64），或 release 有 darwin-arm64 檔。

另外排除：核心功能需要雲端服務或 API key 的工具。它們的離線 smoke test 只證明 CLI 能啟動，demo 說「能離線」會誤導。

## 10 筆（建議順序；前 3 筆最適合念誠在 Mac 上親手驗證，P6.4）

| # | slug | 等級 | 為什麼適合 | Mac arm64 安裝 |
|---|---|---|---|---|
| 1 | `orbit` | service | 本機優先的 coding-agent 任務佇列；本機 web 服務斷網照樣回應 | `npm install -g @orbit-tools/cli`（npm 標明 darwin、arm64） |
| 2 | `mcp-audit` | function | 離線掃描 MCP 設定的安全問題；`scan`／`check` 斷網通過 | `uv tool install mcp-audit-scanner`（或 `pipx install mcp-audit-scanner`） |
| 3 | `patient-zero` | function | 掃 npm／PyPI 供應鏈 IoC；`patient-zero scan --offline --no-github` 斷網通過 | `npm install -g patient-zero` |
| 4 | `shep` | function | Rust 寫的程序管理器；起服務、重啟、看輸出都在本機 | `brew install shep-pm/shep/shep` |
| 5 | `mi-lsp` | function | 幫 agent 建本機程式碼索引並導覽；`init`、`nav intent` 斷網通過 | release v0.16.1 的 `mi-lsp_0.16.1_darwin-arm64.tar.gz` |
| 6 | `phantom` | service | 本機 coding-agent 工作台；`phm verse` 的本機 UI 斷網照樣回應 | `npm install -g @ashlr/phantom` |
| 7 | `rimz` | function | 在 tmux／Zellij 裡集中看多個 coding agent；`doctor`、`hooks install --dry-run` 斷網通過 | release latest-main 的 `rimz-aarch64-apple-darwin.tar.gz`（README 平台只寫 Linux） |
| 8 | `corvus` | install | .NET 與原生執行檔的反組譯 MCP／CLI，完全本機；只驗到安裝等級 | release v2.7.1 的 `corvus-osx-arm64.tar.gz` |
| 9 | `apexo-code` | function | 開源 coding agent 的本機 runtime；離線只驗到 `apexo auth list`，跑 agent 要有模型 | `npm install -g apexo-code`（release 另有 darwin-arm64） |
| 10 | `localm` | function | 唯一的 local_ai：本機跑 LLM 的 CLI；`doctor`、`info` 斷網通過 | `pipx install localm`（PyPI 純 Python；README 只寫 Windows、Linux，Mac 上的模型後端沒驗過） |

**G2**：10 筆都已在 Modal 通過並重播（10/10，門檻 ≥5），已達成。

### 符合四項條件但沒選

- `ccclub`（排行榜要連伺服器）、`xenon`（要 LLM API key）、`praana`（要 Anthropic／OpenAI key）、`aura`（要 OpenRouter key 與 Docker，只到安裝等級）：核心功能不能離線。
- `muxr`：npm 裝得到 Mac，但 README 平台只寫 Linux；需要替補時排在 `localm` 之後。

## 39 份 profile 的驗證結果

| 結果 | 數量 | slug |
|---|---|---|
| 通過並重播 | 25（第一輪 23，重試後 +2） | adapty-cli、apexo-code、aura、ccclub、corvus、detent、future-os、ggrun、gokin、localm、mcp-audit、mi-lsp（重試）、muxr、nadzoring、orbit、overtchat、patient-zero、phantom、praana、proc-cli、rimz（重試）、shep、tricorderkit、xenon、xmatrix |
| 沒通過 | 3 | `lattice`：最新版沒附預編譯檔、cargo 需要 Rust，v0.9.0 的執行檔沒有 README 的 `chat -p`，範例模型要約 3.2 GB 記憶體；`holdspeak`：`evdev` 要 kernel headers（沙盒沒有 root），web UI 建置在 Node 下中止；`coderai`：要 docker／podman 或整套 GPU ML 套件 |
| Linux 沙盒無法驗證 | 11 | GUI 程式 8（neuraldeck、tidytalk、dormouse、hivemind、hilbertraum、flint、lokalbot、ohmail）、只支援 macOS 1（paparats-mcp）、需要 GPU 1（bloomery）、只支援 Apple Silicon 1（krill） |

通過的 25 筆裡沒選的其他原因：

- 不能離線：`nadzoring`（網路診斷工具，`core doctor` 要連網）、`proc-cli`（npm 版第一次執行會下載預編譯檔，斷網全部失敗）。
- 沒有官方 macOS arm64 安裝方式：`tricorderkit`（git clone＋Python）、`ggrun`、`future-os`、`overtchat`、`xmatrix`（release 沒有 darwin-arm64，README 只給安裝腳本）。
- 不確定是否免費：`detent`、`adapty-cli`、`xmatrix`（沒寫價格也沒有授權）；`gokin` 是 freemium。

## 沙盒實測和 README、profile 不符的地方

以下只列出，沒有改寫抽取出的事實：

- `gokin`：profile `runtimes: Go 1.25+`，但用預編譯檔安裝時完全不需要 Go（只有從原始碼建置才要）。
- `shep`：profile `system_packages: Visual C++ redistributable`，只有 Windows 需要；Linux 不用。
- `rimz`：profile 平台只有 Linux，但 release 有 macOS（arm64、x64）執行檔。
- `mcp-audit`：沒有 `--version`（exit 2），要用 `mcp-audit version`。
- `muxr`：README 的 `muxr link` 實際是 `muxr pair`。
- `mi-lsp`：README 的 `install-agent.sh` 單獨下載會失敗（要同目錄的 `validate-worker-manifest.js`）；`install.sh` 預設在 worker 驗證失敗，要加 `--skip-worker-install`。
- `lattice`：README 的 `lattice chat -p` 在有預編譯檔的 v0.9.0 不存在；README 的 `huggingface-cli` 已改名為 `hf`。
- `ggrun`：裝完不在 PATH（要自己 symlink）；`--help` 印到 stderr。
- `future-os`：Debian 上的 install.sh 要 root／sudo 裝 .deb；沒有 root 要改用 portable 檔。
- `holdspeak`：README 說 Linux 上 `uv pip install -e '.[linux]'` 可用，沙盒裡因 `evdev` 與 web UI 建置失敗（部分原因是沙盒沒有 root）。
