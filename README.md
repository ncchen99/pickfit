# pickfit

一個不屬於任何一家的軟體顧問：讓合適的軟體被需要它的人用到。每款軟體都先在沙盒裡裝過、測過、整理好，讓每個人的 AI agent 都能推薦、安裝並帶人上手。

要做什麼、為什麼做、怎麼做，見 [docs/brief.md](docs/brief.md)。

## 關於黑客松

本專案參加 [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)（開發期間 2026-10-27 – 11-04 ET）。

- **這個 repo 只包含比賽期間的成果**，建立於 2026-10-28。
- **賽前做過的事**：題目構想、使用者與市場研究、資料欄位與評測題目的草稿。這些資料**不在這個 repo 裡**，也不是要展示的作品。
- 所有程式碼均於黑客松期間開發。

規則與做法見 [docs/hackathon-rules.md](docs/hackathon-rules.md)。

## 經 OpenRouter 呼叫 Meta 模型（11/3 起）

2026-11-03 04:21 起，Meta 的 API 對本團隊的金鑰回 402「billing_not_configured」（帳單驗證失敗），所以之後的 Meta 模型呼叫改經 [OpenRouter](https://openrouter.ai/meta) 送出：模型不變（`meta/muse-spark-1.3`、`meta/muse-wonder`），而且每個請求都指定只能由 Meta 提供，而且不能用會收集資料的端點（`provider: {order: ["meta"], allow_fallbacks: false, data_collection: "deny"}`），OpenRouter 不會改用別家的模型或供應商。OpenRouter 上的 Meta 端點沒有「零資料保留」選項，所以我們不宣稱零保留。

- **怎麼切換**：Python 流程看 `PICKFIT_META_VIA=openrouter`（`pickfit/meta.py`，帳本另記一個 `openrouter` 預算，上限 $40：念誠在 OpenRouter 儲值 $50，留約 $10 給線上 Worker）；線上 Worker 看 `META_VIA`（`worker/wrangler.jsonc`）。改回 `meta` 就回到 Meta 的 API。
- **紀錄怎麼寫**：資料裡的模型名稱仍是 Meta 的 id（例如 `muse-spark-1.3`），帳本那一筆的 provider 記成 `openrouter`。
- **OpenRouter 沒有的**：contributor 方案在 OpenRouter 上沒有，改用 `muse-spark-1.3`、照它的價格計；SAM 3.1、Muse Image、Muse Voice Transcribe 不經 OpenRouter。

## 非 Meta 模型產生的內容

產品的發現、抽取、驗證、配對與計分都用 Meta 模型。例外如下，每筆都在資料裡記下產生它的模型：

- **工具頁的功能說明**（`usage_guide`：功能的白話標題、已驗證功能的使用步驟、安裝後怎麼打開）：2026-11-02 改版工具頁時，已有的 667 筆紀錄由 Anthropic 的 `claude-opus-5-5` 補產生（`usage_guide.model`）。內容只根據紀錄與驗證 run 已有的資料改寫；產生時只替 run 驗證過的功能寫步驟，網頁也只在仍有通過的 run 驗證該功能時顯示步驟。產生程式 `pickfit/usage_guide.py` 預設用 Meta 模型，之後的新紀錄用 Meta 模型產生。
- **網頁的繁中翻譯**：見下一節。
- **評測**：受測 agent 與部分評分用 Anthropic 模型，不屬於產品流程。

## 網頁的雙語（英文、繁體中文）

產品網頁可以切換英文與繁體中文（右上角的切換，或 `?lang=zh-TW`；之後記在 cookie，沒選過就看瀏覽器語言）。只有網頁是雙語的：MCP 工具、`find_software` 的配對與每一步驗證都照舊用英文資料和 Meta 的模型。

- 介面文字在程式裡寫成 `L('English', '中文')`（`worker/src/i18n.ts`）。
- 每款工具的說明（摘要、功能、安裝步驟的用途、測試紀錄的註記）由 `scripts/translate_zh.py` 用 Claude（Anthropic API）翻成繁中，存在 `data/i18n/zh-TW/<slug>.json`；紀錄本身不動。網頁只在英文原句完全相同時換成中文，所以紀錄改了、還沒重翻的句子會顯示新的英文，不會顯示過期的翻譯。指令、名稱、網址與程式判斷用的值永遠不翻。
- 搜尋時模型拿到的內容和英文頁完全一樣；配對當下產生的理由句子仍是英文。

## GUI 與網頁 App 的易用性評分（試點；只有視覺缺陷算分）

給人直接用的軟體，「打得開、能操作」不代表好用，所以 11/2 試做了易用性評分。四項的易用性分數沒有上線；11/3 起，只有其中量得到的視覺缺陷會讓品質分扣分（見本節最後一點）。

- **做法**：Muse Spark 1.3 看 pickfit 在沙盒裡自己拍的截圖和操作紀錄，照固定檢核表評四項：一打開就能用、功能找得到、操作有回應、看起來舒服。每個判斷都要引用畫面上的字，pickfit 用 OCR 或網頁 DOM 找不到那段字就不算；只有 app 自己造成的問題才扣分。程式在 `pickfit/usability.py`。
- **校準**：抽樣規則和四個通過標準在第一次付費呼叫前 commit。念誠在看不到 pickfit 分數的情況下盲評 12 款；沒過只能改一次評分標準，再比一次。
- **結果：兩輪都沒過**（第一輪 → 改一次後），細節見 [docs/usability-pilot.md](docs/usability-pilot.md)：
  - 各項和念誠差距 ≤1 級（門檻 10/12）：「看起來舒服」9/11 → 8/10，其他三項全部在 1 級內。
  - 和念誠整體分數的 Spearman（門檻 ≥0.5）：−0.40 → −0.73。
  - 兩個「好看但難用」探針（門檻都 ≤50）：87.5、91.7 → 87.5、95.8。
  - 判語差兩級（門檻 0 款）：兩輪都有 1 款（usdx）。
- **所以不上線**：`EASE_SCORED` 關閉，四項的易用性分數不影響品質分、排名與寶藏，工具頁也不顯示。程式、念誠的評分和兩輪結果留在 repo 裡；兩輪共花 $0.83。
- **學到的事**：
  - 一打開就能用、功能找得到、操作有回應這三項，Muse Spark 1.3 和念誠在可比的 App 上差距都在 1 級內（12/12、8/8、9/9）；落差在「看起來舒服」和整體印象。念誠看的是畫面新舊、精緻度、間距和破圖，這要靠模型對視覺設計與使用體驗的判斷力（美感），這次的評審沒有抓到；檢核表照設計也刻意不評風格。這是多模態模型普遍還在進步的能力。
  - pickfit 的流程不綁定模型：同一份檢核表和這 12 款盲評，可以直接拿來校準之後更強的模型，通過了才上線。
  - 網頁只留下 2–3 張截圖（載入後、操作前後），證據太少。
  - 有操作的 9 款分數都在約 74–100，分不出高下。
- **現在的替代**：工具頁的操作影片依功能分段（目前 8 款桌面 App 有），讓人自己看介面判斷。
- **量得到的視覺缺陷只扣分、不加分（11/3 起）**：
  - **做法**：念誠看過各模型扣分的截圖後決定，「看起來舒服」改成只看量得到的缺陷。由 Muse Wonder 看 pickfit 自己的截圖，列出文字被截斷、元素蓋住內容、控制項被切掉、在字中間斷行、對比太低、字太小、顯示原始碼、圖片壞掉、沒對齊、太擠，不評品味；每個缺陷都附原因和位置。
  - **怎麼算分**：只要找到 app 本身造成的缺陷，品質分就乘 0.95（扣 5%）；沒找到不加分。公式名稱是 `b3.v5+visual.v1`、`web.v1+visual.v1`，紀錄的 `quality.visual` 記下係數和扣之前的分數。寶藏門檻不變。
  - **還沒檢查的 App**：186 款有 pickfit 截圖的桌面和網頁 App 都檢查過；另外 104 款還沒檢查（大多沒有 pickfit 的截圖，少數的截圖或 run 已經不在），分數完全不變，工具頁寫「尚未做視覺檢查」。
  - **已知限制**：缺陷說明是模型寫的英文，中文頁面目前也顯示英文原句。
  - **上線前的人工複查**（[docs/usability-pilot.md](docs/usability-pilot.md) 第 11 節）：兩位沒參與開發的獨立複查者（Claude）看了 14 款。模型列的缺陷約每 4 個有 1 個不是真的（24 個中 6 個）；標成「嚴重」的只有三分之一站得住，所以嚴重程度先不算，等更多人工標註校準後再用。
  - **影響**（對照沒有這項的版本）：有檢查的 186 款品質分中位數 0、平均 −1.4（桌面 −0.9、網頁 −2.0）；69 款有缺陷的各扣 5%；寶藏從 162 款變 161 款（boltzyml-v2-0）；沒有任何一款變動超過 5 分。
  - **花費**：檢查一次 Muse Wonder，每款約 $0.03，186 款共約 $6.4。
  - **依嚴重度扣分：試過、不上線**：嚴重扣 10%、輕微扣 5%，而且「嚴重」要第二位評審（Muse Spark 1.3）也同意才算。第二位評審沒過事先寫下的門檻：複查者確認的 4 個嚴重缺陷只保住 1 個（有爭議的 8 個倒是降級了 7 個）。念誠逐一看過這 12 個判斷的截圖，認同 Claude 複查者的判斷，決定維持一律扣 5%。細節見 [docs/usability-pilot.md](docs/usability-pilot.md) 第 13 節；程式留在分支 `claude/usability-wonder`，沒有合併。
- **已知安全弱點：有就不當寶藏（11/3 起）**：
  - **原則**（念誠）：軟體是 pickfit 推薦的，寧可錯殺一款寶藏，也不推薦有已知漏洞的軟體。
  - **做法**（`pickfit security`，不用模型、不花錢）：先照「今天全新安裝」的方式解析使用者會裝到的套件（`npm --package-lock-only --ignore-scripts`、`uv pip compile --no-build`，都不會執行套件的程式碼；沒有套件就讀 repo 的 lockfile，Python 照 `pyproject.toml` 重新解析），再逐一到 [OSV.dev](https://osv.dev) 查。開發用的相依，以及文件網站、編輯器擴充、CI 這些使用者不會裝到的部分，都不算。
  - **怎麼算分**：只要有任何 high 或 critical 弱點，不論有沒有修正版、是不是只造成 DoS，品質分最高 79（`known_vulnerability`），也就不能當寶藏。malicious 套件會直接下架。工具頁列出弱點和修正版本，MCP 的回答也帶 `security`，請 agent 在安裝前告訴使用者。
  - **沒檢查到的**：246 款沒有可讀的來源，或有一部分讀不到（大多是沒有 lockfile 的桌面 App，以及沒有 repo 的網頁），分數不變，工具頁寫明沒檢查和原因。只要有一部分讀不到，就算沒找到弱點也不寫「沒有已知弱點」。
  - **影響**：961 款上線的軟體裡，241 款有已知弱點、474 款沒有、246 款沒檢查到；73 款的分數有變；寶藏從 161 款變成 135 款。細節與先前用 AI 判斷「會不會影響使用者」的試跑（沒有採用）見 [docs/security-pilot.md](docs/security-pilot.md)。

## 驗證環境的限制與之後的方向

pickfit 在隔離的環境裡驗證：Linux 用 Modal 的沙盒（gVisor；網頁 App 與部分桌面 App 用有自己核心的 microVM），Mac 用 tart（Apple 的 Virtualization.framework），Windows 用 VirtualBox。這些環境和一般人的電腦不一樣，所以有些功能在裡面測不了，不代表軟體有問題。

- **環境造成的問題只記「未驗證」，不記「失敗」**：驗證 agent 判斷是環境限制時，寫成未驗證並記下原因（例如 `needs_gpu`、`needs_hardware`、`needs_display`、`needs_service`）。整筆工具的「失敗」只能來自人工驗證或人工檢查發布的檔案。環境不足的代價是覆蓋率，不會冤枉軟體。
- **目前的限制**：
  - Linux：gVisor 沙盒裡沒有 root、不能載入核心模組、不能跑 Docker；虛擬畫面是 1280×800、沒有視窗管理員，也沒有一般桌面的檔案對話框、開網址的預設程式和 Wayland。GPU（NVIDIA T4 等）只有 gVisor 拿得到，microVM 不行。麥克風有 pickfit 自己的模擬（`pickfit/verify/audio.py`：播放新產生的詞，檢查 App 是否收到）；攝影機沒有模擬。
  - Mac：tart 的 GPU 是虛擬的（Metal 可用，但回報的功能比實機少），沒有攝影機；為了隔離，聲音也關掉。
  - Windows：VirtualBox 沒有真正的 GPU；為了隔離，3D、聲音和 USB 都關掉。
- **資料**（2026-11-03，193 款桌面 App 中沒檢查到的功能，依每個功能記錄的原因統計；原因寫 `other` 的依註記文字粗分）：

  | 原因 | Linux | Mac |
  |---|---|---|
  | 沒有試（那次只跑到安裝） | 169 | 17 |
  | 環境：缺背景服務或桌面元件、缺硬體或 GPU、畫面、資源不夠 | 63 | 21 |
  | 操作的 agent 步數用完或繞圈（註記裡有寫到的） | 13 | 2 |
  | 需要帳號 | 13 | 3 |
  | 其他或原因不明 | 32 | 28 |

  最多的是根本沒試，這要多跑操作，不用換硬體。試了沒過的裡面，環境是最大的原因；其中真的缺硬體的（`needs_hardware`、`needs_gpu`）Linux 18、Mac 3，其餘多是缺背景服務、桌面元件或資源。

  「步數用完」這一列偏低：它來自 agent 寫的註記，但每次操作停在哪裡是 pickfit 自己記的。依現場紀錄（`~/.pickfit/evidence`，Linux 與 Mac 共 117 次 GUI 操作），59 次跑到 28 步的上限（其中 12 次在最後一步才通過），44 次自己說完成；通過的 36 次中位數用 14 步。停在上限的功能，原因常被記成 `other`，註記也不一定寫到。所以每個功能的原因之後改用 pickfit 記錄的停止原因，不再只靠註記。
- **研究上的做法**：電腦操作 agent 的基準（[OSWorld](https://api.emergentmind.com/topics/osworld-and-windowsagentarena)、Windows Agent Arena、macOSWorld、[MacArena](https://huggingface.co/papers/2606.06560.md)）也都跑在 VM 裡，接受同樣的限制；GPU、麥克風、攝影機都要真的，通常要靠真機。
- **之後的方向**（賽後；比賽期間沒有做）：
  - Linux：改用有 NVIDIA GPU 的完整雲端 VM（例如 AWS G5/G6），裝真正的桌面（視窗管理員、檔案對話框、預設程式、PipeWire），用 [Amazon DCV](https://docs.aws.amazon.com/dcv/latest/adminguide/servers.html) 的虛擬螢幕（最高 4K），畫面改成 1920×1080。完整 VM 能裝虛擬攝影機與麥克風的驅動；每次檢查從快照重開，OSWorld 也是這樣做。
  - Windows：從 VirtualBox 改成雲端 GPU VM：AWS 加 DCV（Windows 版支援攝影機與錄音），或 Azure、[Windows 365 GPU Cloud PC](https://learn.microsoft.com/windows-365/enterprise/gpu-cloud-pc)。
  - Mac：大部分仍用 tart；需要完整 GPU 或真實螢幕的 App 改到 [AWS EC2 Mac](https://aws.amazon.com/ec2/instance-types/mac/faqs/)（實體 Mac mini／Mac Studio；DCV 支援 4K、60 FPS 與聲音輸出，沒有麥克風輸入）。
  - 實體機房，只用來複核：Mac mini、有顯示卡的 Windows PC、Linux PC，各接一台 [PiKVM V4](https://docs.pikvm.org/camera/)（擷取真實畫面、模擬鍵盤滑鼠，也能模擬成 USB 攝影機與麥克風）。只有「只因環境而沒驗證」的 App 才送去重跑。
