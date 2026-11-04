# 知名開源專案擴充清單与領域搜尋紀錄（`curated-well-known.v2`）

2026-11-04（台北）整理 · 對應 [`docs/discovery/curated-well-known-v2.json`](curated-well-known-v2.json) 與 [`docs/source-terms.md`](../source-terms.md)。

## 1. 背景與 Credit 資源分配策略

- **為什麼擴充知名開源軟體**：pickfit 的定位是「讓合適的軟體被需要它的人用到」，什麼軟體都收（見 [`docs/submission/story.md`](../submission/story.md) 第 1 節）。前期刻意優先驗證低知名度的小眾軟體，是為了證明尚未成名的作品同樣能透過沙盒實測獲得保障並發掘出「寶藏（Hidden Gems）」。在評測中我們也觀察到，當使用者詢問常見需求時，目錄仍需補齊各領域廣受認可的知名開源標竿專案。
- **有限 Credit 下的分級驗證策略**：
  1. **低知名度／新興軟體（優先深測功能）**：由於缺乏社群與公開評價背書，使用者與 AI Agent 無法確定其功能是否真能運作，因此我們將有限的 API credits 優先投入在沙盒中執行深度的功能實測（`function`、`service`、`inference`）與多步 GUI 操作驗證。
  2. **高星知名開源軟體（優先收錄並驗證至 `install`）**：對於在 GitHub 上已累積數千至數萬顆星、具備廣泛社群信賴與長期維護紀錄的知名開源專案，我們優先擴大目錄收錄覆蓋率，並在沙盒中驗證至 `install` 等級（確認能乾淨安裝、基礎啟動或印出版本／說明），而不額外消耗大量 API credits 進行多步功能操作測試。
- **預算控管（2026-11-04 13:00 盤點）**：
  - 當時剩餘額度：OpenRouter `$48.86`、Modal `$61.76`。
  - 單款跑完 `install` 全流程（`extract` + `verify` 至 `install` + `verify-judge` + `score-rubric` + `jobs` + `translate`）平均消耗：OpenRouter 約 `$0.06–$0.08`／款、Modal 約 `$0.13–$0.20`／款。
  - 為預留充裕額度給線上 Demo（Cloudflare Worker `find_software` 與 Modal 端點），從 6 個 `3.8 flash` 子代理搜尋出的 **231 款候選池** 中，先精選出 **87 款**（念誠指定的 7 款 macOS 開源工具 + 6 大領域 80 款功能不重疊、安裝路徑乾淨的代表作）納入本批收錄與驗證。

---

## 2. 本批精選收錄的 87 款知名開源軟體

### A. 指定收錄的 7 款 macOS 開源應用（7 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `sindresorhus/Gifski` | 8,595 | MIT | macOS 高畫質影片轉 GIF 工具（基於 pngquant 跨幀調色盤） |
| 2 | `Clipy/Clipy` | 8,961 | MIT | macOS 經典剪貼簿歷史與常用片段（Snippets）管理工具 |
| 3 | `pilotmoon/Scroll-Reverser` | 3,695 | Apache-2.0 | macOS 觸控板與滑鼠滾輪方向獨立反轉工具 |
| 4 | `exelban/stats` | 43,094 | MIT | macOS 選單列系統硬體監控（CPU、GPU、記憶體、網路、電池、風扇） |
| 5 | `rxhanson/Rectangle` | 30,226 | MIT | macOS 快捷鍵與拖曳邊緣視窗分屏管理工具 |
| 6 | `sfsam/Itsycal` | 4,044 | MIT | macOS 選單列輕量迷你月曆與行程速覽工具 |
| 7 | `thaw-app/Thaw` | 12,529 | GPL-3.0 | macOS 選單列圖示隱藏與排列管理工具（Ice 繼任維護版） |

### B. 領域一：macOS 桌面與選單列效率工具精選（13 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 8 | `MonitorControl/MonitorControl` | 32,761 | MIT | 外接顯示器亮度與音量硬體控制（DDC/CI） |
| 9 | `lwouis/alt-tab-macos` | 15,738 | GPL-3.0 | Windows 風格視窗縮圖切換器（補足 macOS Cmd+Tab 痛點） |
| 10 | `nikitabobko/AeroSpace` | 20,257 | MIT | i3 風格平鋪式視窗管理器（與快捷鍵分屏的 Rectangle 互補） |
| 11 | `p0deje/Maccy` | 19,165 | MIT | 現代原生 Swift 輕量鍵盤優先剪貼簿管理器 |
| 12 | `lihaoyun6/QuickRecorder` | 7,968 | GPL-3.0 | 基於 ScreenCaptureKit 的輕量多功能錄屏工具 |
| 13 | `PlayCover/PlayCover` | 11,488 | GPL-3.0 | Apple Silicon 原生執行 iOS 應用程式與鍵盤映射工具 |
| 14 | `leits/MeetingBar` | 6,408 | MIT | macOS 選單列線上會議提醒與一鍵加入工具（支援 Zoom/Meet/Teams；原 `Whisky` 已封存故替補） |
| 15 | `objective-see/LuLu` | 13,221 | GPL-3.0 | macOS 開源應用層防火牆（阻擋未知外聯請求） |
| 16 | `TheBoredTeam/boring.notch` | 7,019 | GPL-3.0 | 將 MacBook 瀏海轉化為動態音樂控制與檔案暫存置物架 |
| 17 | `kyleneideck/BackgroundMusic` | 13,841 | GPL-2.0 | macOS 各應用程式獨立音量控制與系統音訊錄製工具 |
| 18 | `newmarcel/KeepingYouAwake` | 5,914 | MIT | 選單列防止 Mac 進入休眠的小工具（caffeinate GUI） |
| 19 | `iglance/iGlance` | 3,138 | GPL-3.0 | 高度客製化的選單列系統狀態圖表監控 |
| 20 | `keycastr/keycastr` | 5,863 | BSD-3-Clause | 錄影與教學演示專用的開源按鍵螢幕顯示器 |

### C. 領域二：跨平台桌面生產力、筆記、影音與創作軟體精選（14 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 21 | `AppFlowy-IO/AppFlowy` | 69,482 | AGPL-3.0 | Notion 開源本地優先替代方案（筆記、Wiki、看板與資料表） |
| 22 | `logseq/logseq` | 41,923 | AGPL-3.0 | 本地優先大綱式雙鏈知識庫與白板筆記軟體 |
| 23 | `laurent22/joplin` | 54,199 | AGPL-3.0 | 支援端到端加密同步的 Markdown 筆記與待辦應用 |
| 24 | `ankitects/anki` | 27,232 | AGPL-3.0 | 間隔重複（Spaced Repetition）記憶閃卡標竿軟體 |
| 25 | `HandBrake/HandBrake` | 23,441 | GPL-2.0 | 跨平台開源影片轉檔與壓縮標準工具 |
| 26 | `iina/iina` | 44,507 | GPL-3.0 | 基於 mpv 的現代 macOS 原生全能影音播放器 |
| 27 | `mifi/lossless-cut` | 39,968 | GPL-2.0 | 影音無損極速剪輯與分段合併工具（FFmpeg GUI） |
| 28 | `audacity/audacity` | 17,221 | GPL-3.0 | 跨平台多軌音訊錄製與編輯標準工具 |
| 29 | `LibreSprite/LibreSprite` | 4,060 | GPL-2.0 | 像素畫（Pixel Art）繪製與精靈動畫編輯器 |
| 30 | `bitwarden/clients` | 13,077 | GPL-3.0 | Bitwarden 跨平台開源密碼管理器客戶端 |
| 31 | `keepassxreboot/keepassxc` | 26,955 | GPL-2.0 | 完全離線本機加密儲存的跨平台密碼管理器 |
| 32 | `localsend/localsend` | 77,610 | MIT | 免網際網路、跨平台局域網極速傳檔工具 |
| 33 | `transmission/transmission` | 14,769 | GPL-2.0 | 極簡、低資源佔用的跨平台 BitTorrent 客戶端 |
| 34 | `readest/readest` | 10,800+ | AGPL-3.0 | 現代跨平台電子書閱讀器（支援 EPUB/PDF 雙頁對照與本地標註） |

### D. 領域三：開發者核心 CLI & TUI 工具（Shell、檔案、Git、系統監控）精選（20 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 35 | `BurntSushi/ripgrep` | 62,158 | MIT | 極速正則內容搜尋工具（`rg`，取代 grep） |
| 36 | `sharkdp/fd` | 42,740 | Apache-2.0 | 直覺極速的檔案查找工具（取代 find） |
| 37 | `sharkdp/bat` | 58,200 | Apache-2.0 | 具備語法高亮與 Git 整合的檔案檢視器（取代 cat） |
| 38 | `eza-community/eza` | 21,092 | MIT | 現代色彩與圖標化的檔案列表工具（取代 ls / exa） |
| 39 | `ajeetdsouza/zoxide` | 35,342 | MIT | 智慧型目錄快速跳轉工具（`z`，取代 cd） |
| 40 | `junegunn/fzf` | 79,576 | MIT | 命令列通用互動式模糊搜尋器 |
| 41 | `starship/starship` | 56,089 | ISC | 跨 Shell 極速高顏值終端提示符（Prompt） |
| 42 | `atuinsh/atuin` | 29,215 | MIT | SQLite 驅動的 Shell 歷史記錄搜尋與加密同步工具 |
| 43 | `nushell/nushell` | 39,105 | MIT | 結構化資料管道（Structured Data）現代 Shell |
| 44 | `zellij-org/zellij` | 31,422 | MIT | 開箱即用、支援浮動面板與外掛的終端多工器（取代 tmux） |
| 45 | `alacritty/alacritty` | 63,365 | Apache-2.0 | OpenGL GPU 加速跨平台極速終端模擬器 |
| 46 | `sxyazi/yazi` | 35,969 | MIT | 非同步極速終端檔案管理器（支援圖片/PDF/程式碼預覽） |
| 47 | `jesseduffield/lazygit` | 76,568 | MIT | 終端機裡最受歡迎的互動式 Git TUI 介面 |
| 48 | `dandavison/delta` | 30,224 | MIT | 支援語法高亮與並排對比的 Git Diff 分頁檢視器 |
| 49 | `Wilfred/difftastic` | 24,812 | MIT | 基於 AST 語法樹理解程式碼結構的語義化 Diff 工具 |
| 50 | `jj-vcs/jj` | 28,287 | Apache-2.0 | Jujutsu：相容 Git 後端的新一代極簡版本控制系統 |
| 51 | `cli/cli` | 43,727 | MIT | GitHub 官方命令列工具（`gh`，管理 PR、Issue、Release、Actions） |
| 52 | `aristocratos/btop` | 32,053 | Apache-2.0 | 終端機互動式系統資源與進程監控儀表板（取代 htop） |
| 53 | `ClementTsang/bottom` | 13,254 | MIT | Rust 編寫的跨平台圖形化終端系統監控 TUI（`btm`） |
| 54 | `sharkdp/hyperfine` | 28,041 | Apache-2.0 | 具備統計分析與預熱機制的命令列基準測試（Benchmark）工具 |

### E. 領域四：開發者 CLI & TUI 工具（資料處理、網路、容器、任務建置）精選（14 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 55 | `jqlang/jq` | 34,373 | MIT | 命令列 JSON 解析、過濾與轉換標準工具 |
| 56 | `mikefarah/yq` | 15,244 | MIT | YAML / JSON / XML / TOML 結構化配置解析與修改工具 |
| 57 | `johnkerl/miller` | 9,854 | BSD-2-Clause | CSV / TSV / JSON 結構化表格資料查詢、統計與轉換命令列工具（`mlr`；原 `xsv` 已封存故替補） |
| 58 | `saulpw/visidata` | 10,879 | GPL-3.0 | 終端機互動式表格與資料探索分析神器（支援 CSV/SQLite/Parquet/JSON） |
| 59 | `tconbeer/harlequin` | 5,093 | MIT | 終端機裡的全功能 SQL IDE（支援 DuckDB、SQLite、Postgres） |
| 60 | `ducaale/xh` | 7,462 | MIT | Rust 編寫的極速人性化 HTTP 請求發送工具（HTTPie 極速替代版） |
| 61 | `Orange-OpenSource/hurl` | 19,205 | Apache-2.0 | 基於純文字檔執行與斷言測試 HTTP/REST/GraphQL API 的 CLI |
| 62 | `imsnif/bandwhich` | 11,945 | MIT | 按進程、連線與遠端 IP 即時顯示終端網路頻寬佔用情況 |
| 63 | `ogham/dog` | 7,031 | EUPL-1.2 | 支援 DoT/DoH 與 JSON 輸出的彩色化 DNS 查詢客戶端（取代 dig） |
| 64 | `derailed/k9s` | 33,572 | Apache-2.0 | Kubernetes 叢集全功能終端互動管理 TUI |
| 65 | `wagoodman/dive` | 54,282 | MIT | 逐層分析 Docker 映像檔體積與尋找空間浪費的終端工具 |
| 66 | `casey/just` | 33,281 | CC0-1.0 | 專案命令執行器（取代 Makefile 處理專案腳本任務） |
| 67 | `jdx/mise` | 26,886 | MIT | 多語言開發環境版本管理器 + 環境變數 + 任務執行器（取代 asdf/nvm） |
| 68 | `direnv/direnv` | 15,013 | MIT | 進出資料夾時自動載入與卸載 `.envrc` 環境變數的 Shell 擴充 |

### F. 領域五：本地 AI / LLM 推論、Coding Agent 與離線語音工具精選（11 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 69 | `ollama/ollama` | 169,365 | MIT | 本地下載、管理與執行大模型（Llama、DeepSeek、Qwen、Gemma）的最普及工具 |
| 70 | `janhq/jan` | 41,704 | Apache-2.0 | 100% 離線優先的本地 AI 桌面對話應用與本地 OpenAI 相容 API 伺服器 |
| 71 | `OpenInterpreter/open-interpreter` | 62,794 | AGPL-3.0 | 在本地終端機透過自然語言編寫並執行程式碼完成系統任務的 AI Agent |
| 72 | `continuedev/continue` | 32,499 | Apache-2.0 | 開源 IDE AI 編程助手與 CLI Agent（支援連接本地模型與自訂規則） |
| 73 | `TabbyML/tabby` | 33,315 | Apache-2.0 | 可完全自架於本地/內網的開源 AI 程式碼自動補全伺服器 |
| 74 | `sigoden/aichat` | 9,854 | Apache-2.0 | 支援 Shell 助手、RAG、Function Calling 與 20+ 本地/雲端模型的全能 CLI |
| 75 | `simonw/llm` | 11,813 | Apache-2.0 | Simon Willison 開發的模組化命令列 LLM 調用、Embedding 與 SQLite 記錄工具 |
| 76 | `ggml-org/whisper.cpp` | 48,546 | MIT | 高性能純 C/C++ 本地離線語音轉文字（Whisper）推論引擎（支援 Apple Metal） |
| 77 | `SYSTRAN/faster-whisper` | 22,068 | MIT | 基於 CTranslate2 的高速低顯存 Whisper 語音轉錄工具 |
| 78 | `m-bain/whisperX` | 20,977 | BSD-2-Clause | 具備詞級時間戳對齊與語者分離（Speaker Diarization）的快速離線語音轉文字工具（原 `rhasspy/piper` 已封存故替補） |
| 79 | `Comfy-Org/ComfyUI` | 108,079 | GPL-3.0 | 模組化節點工作流式本地圖像、影片與音訊生成式 AI 引擎 |

### G. 領域六：高頻實用 MCP Servers 與本地優先開源 Web / 自架工具精選（8 款）

| # | GitHub Repo | Stars | License | 子領域與定位 |
| :---: | :--- | :---: | :---: | :--- |
| 80 | `microsoft/playwright-mcp` | 30,855 | Apache-2.0 | 微軟官方基於 Playwright 無障礙樹的瀏覽器自動化 MCP Server |
| 81 | `ChromeDevTools/chrome-devtools-mcp` | 36,158 | Apache-2.0 | Chrome 官方 DevTools 調試、效能追蹤與 DOM 檢視 MCP Server |
| 82 | `github/github-mcp-server` | 29,211 | MIT | GitHub 官方 MCP Server（讓 Agent 搜尋倉庫、讀寫 Issue/PR 與分析 Actions） |
| 83 | `oraios/serena` | 23,517 | MIT | 基於 LSP 符號級程式碼語義檢索與編輯的 Coding Agent MCP 工具箱 |
| 84 | `hoppscotch/hoppscotch` | 78,899 | MIT | 開源輕量 Web API 開發與測試平台（Postman 開源替代） |
| 85 | `Stirling-Tools/Stirling-PDF` | 75,650 | MIT | 本地/自架一站式 PDF 合併、拆分、轉換、OCR 與簽署工具 |
| 86 | `CorentinTh/it-tools` | 38,376 | GPL-3.0 | 匯集 80+ 款開發者常用編碼、加密、格式轉換與網路計算器的純淨 Web 工具箱 |
| 87 | `usememos/memos` | 58,927 | MIT | 極速輕量、隱私優先的自架碎片化筆記與靈感閃念記錄服務 |

---

## 3. 子代理搜尋之完整候選池備查（其餘 144 款候選，供後續批次擴充）

以下為 6 個 `3.8 flash` 子代理針對 28 個子領域搜尋並驗證通過、本批因預算預留而暫列備查的其餘高星開源專案：

- **macOS 桌面與選單列工具**：`ianyh/Amethyst`、`Asmvik/yabai`、`FelixKratz/SketchyBar`、`MrKai77/Loop`、`AzimsTech/DockDoor`、`dwarvesf/hidden`、`jordanbaird/Ice`、`leits/MeetingBar`、`Linearmouse/linearmouse`、`pqrs-org/Karabiner-Elements`、`jekkos/iplocation` (`waydabber/BetterDisplay`)、`TierOneApps/OnlySwitch` (`jacklandrin/OnlySwitch`)、`Dimillian/IceCubesApp`、`wulkano/Kap`、`SoftFever/OrcaSlicer`、`FreeTubeApp/FreeTube`、`MonitorControl/MonitorControl`、`finestructure/Arena`、`guillaume-b/mac-cleanup-py`、`HotKeyApp/HotKey`、`TermiT/Flycut`、`Hammerspoon/hammerspoon`、`sieren/QSpace`、`JayGarza/QuickLook-plugins` 等。
- **跨平台桌面生產力與創作**：`AffinePro/AFFiNE` (`toeverything/AFFiNE`)、`siyuan-note/siyuan`、`TriliumNext/Notes`、`Zettlr/Zettlr`、`marktext/marktext`、`Notable/notable`、`obsidianmd/obsidian-releases`（非開源，排除）、`VSCodium/vscodium`、`lapce/lapce`、`zed-industries/zed`、`obsproject/obs-studio`、`Shotcut/shotcut`、`kde/kdenlive`、`darktable-org/darktable`、`NatronGitHub/Natron`、`krita/krita`、`inkscape/inkscape`、`FreeCAD/FreeCAD`、`openscad/openscad`、`Syncthing/syncthing`、`qbittorrent/qBittorrent`、`Cryptomator/cryptomator`、`ProtonMail/WebClients`、`thunderbird/thunderbird-desktop`、`johnfactotum/foliate`、`bambulab/BambuStudio` 等。
- **開發者 CLI & TUI 工具（Core / Data / Net / Ops）**：`dalance/procs`、`bootandy/dust`、`Byron/dua-cli`、`Dusk-Labs/dysk`、`ClementTsang/bottom`、`ksdme/ut`、`ouch-org/ouch`、`Peltoche/lsd`、`gokcehan/lf`、`jarun/nnn`、`zyedidia/micro`、` helix-editor/helix`（已收）、`neovim/neovim`、`extrawurst/gitui`、`Jonas/tig`、`newren/git-filter-repo`、`Gitleaks/gitleaks`、`trufflesecurity/trufflehog`、`charmbracelet/glow`、`charmbracelet/gum`、`charmbracelet/vhs`、`dbrgn/tealdeer`、`tldr-pages/tldr`、`nvbn/thefuck`、`AykutSarac/jsoncrack.com`、`antonmedv/fx`、`tomwright/dasel`、`johnkerl/miller`、`dbohdan/sq`、`ankane/pghero`、`httpie/cli`、`curlie/curlie` (`rs/curlie`)、`hatoo/oha`、`tsenart/vegeta`、`fujiapple852/trippy`、`CrunchyData/pg_activity`、`avelino/awesome-go`（非軟體，排除）、`go-task/task`、`watchexec/watchexec`、`mattgreen/watchexec`、`earthly/earthly`、`tilt-dev/tilt`、`ahmetb/kubectx`、`stern/stern`、`derailed/popeye`、`aquasecurity/trivy`、`anchore/grype`、`anchore/syft`、`typst/typst`、`mdBook/mdBook` (`rust-lang/mdBook`)、`Morganamilo/paru`、`Jguer/yay`、`topgrade-rs/topgrade` 等。
- **本地 AI、語音與模型工具**：`BerriAI/litellm`（已收）、`LM-Studio`（閉源，排除）、`mudler/LocalAI`、`Mintplex-Labs/anything-llm`、`lobehub/lobe-chat`、`danny-avila/LibreChat`、`SillyTavern/SillyTavern`、`text-generation-webui/text-generation-webui` (`oobabooga/text-generation-webui`)、`exo-explore/exo`、`gpustack/gpustack`、`Mozilla-Ocho/llamafile`、`ml-explore/mlx-examples`、`charmbracelet/mods`、`Pythagora-io/gpt-pilot`、`All-Hands-AI/OpenHands`、`Swe-agent/SWE-agent`、`BuilderIO/gpt-crawler`、`repomix/repomix` (`yamadashy/repomix`)、`m1guelpf/auto-subtitle`、`jianfch/stable-ts`、`m-bain/whisperX`、`coqui-ai/TTS`、`SWivid/F5-TTS`、`fishaudio/fish-speech`、`netease-youdao/EmotiVoice`、`RVC-Boss/GPT-SoVITS`、`lllyasviel/Fooocus`、`invoke-ai/InvokeAI`、`VikParuchuri/marker`、`Umi-OCR/Umi-OCR`、`JaidedAI/EasyOCR`、`PaddlePaddle/PaddleOCR`、`Unstructured-IO/unstructured`、`QuivrHQ/quivr`、`khoj-ai/khoj`、`chatchat-space/Langchain-Chatchat`、`infiniflow/ragflow` 等。
- **MCP Servers 與自架/本地優先 Web 工具**：`modelcontextprotocol/servers`、`firecrawl/firecrawl-mcp-server`、`mendableai/firecrawl`、`browserbase/mcp-server-browserbase`、`executeautomation/mcp-playwright`、`upstash/context7`、`qdrant/mcp-server-qdrant`、`supabase-community/supabase-mcp`、`cloudflare/mcp-server-cloudflare`、`stripe/agent-toolkit`、`linear/linear-mcp`、`sooperset/mcp-atlassian`、`korotovsky/slack-mcp-server`、`taylorwilsdon/google_workspace_mcp`、`exa-labs/exa-mcp-server`、`tavily-ai/tavily-mcp`、`brave/brave-search-mcp-server`、`jlowin/fastmcp`、`mark3labs/mcp-go`、`nocodb/nocodb`、`n8n-io/n8n`（Fair-code，排除）、`activepieces/activepieces`、`louislam/uptime-kuma`、`ActualBudget/actual`、`immich-app/immich`、`paperless-ngx/paperless-ngx`、`pairdrop/pairdrop`、`penpot/penpot`、`drawdb-io/drawdb`、`tldraw/tldraw`（非 OSI，排除）、`jgraph/drawio` 等。
