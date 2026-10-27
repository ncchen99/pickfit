# 沙盒方案比較：執行陌生、不受信任的程式

2026-10-28 查證（台北時間）· 技術調研筆記 · 沒有任何沙盒服務的金鑰，雲端服務都**未實測**；本機 Docker／gVisor 有實測（第 8 節）。

範圍：pickfit 的驗證 agent（brief 第 4.2 節）要在沙盒裡「照 README 安裝並執行」陌生的 GitHub 專案。比較 Modal Sandbox、E2B、Daytona、Cloudflare Sandbox（Containers）、Vercel Sandbox、GitHub Actions（含 macOS）、Fly.io（簡要）、本機 Docker（含 gVisor）。

狀態標記：**已確認**＝親自讀過官方文件、價格頁或條款原文；**實測**＝在本機跑過；**估算**＝自己算的，假設寫在旁邊；**未驗證**＝沒找到第一手資料，或要金鑰才能確認。

---

## 0. 結論

1. **主要沙盒選 Modal Sandbox。** 比賽給 $100 credits（前 1,000 人），Starter 方案每月另含 $30。官方定位就是「執行不受信任程式的安全容器」，runtime 是 gVisor 或 VM（不指定時「let Modal choose」，文件沒寫預設是哪個）。可以「安裝時開網路、執行時斷網」，有 GPU（GPU 沙盒只能用 gVisor，而且會被搶占）、有 Volume 可快取模型，Python SDK 直接接進管線。（已確認；查核修正：原寫「預設用 gVisor」）
2. **Linux 備案選 E2B。** 免信用卡、送 $100 一次性 credits、Firecracker microVM、Python SDK 用法和 Modal 很像。缺點：沒有 GPU、Hobby 方案單次最長 1 小時、磁碟 10 GiB。（已確認）
3. **錄 demo 的保底是本機 Docker**（`--network none`），不靠任何雲端帳號。它和主機共用 kernel，只能跑 demo 要用的那幾個專案，不要拿來大量跑陌生程式。（實測：啟動 0.3–0.5 秒）
4. **macOS 驗證：GitHub Actions 的 macOS runner 免費、按分鐘計，但不是唯一這樣的雲端做法。** CI 服務也按分鐘：CircleCI Free 每月 30,000 credits，macOS M4 Pro Medium 200 credits／分，約 150 分鐘，macOS 並行 1；Codemagic 個人免費方案每月 500 分鐘 M2，並行 1。**整台出租的 Mac**（AWS EC2 Mac、Daytona 透過 use.computer）才要**至少租 24 小時**，原因是 Apple 授權第 3 節規定出租「minimum period of twenty-four (24) consecutive hours」。如果念誠有 Apple silicon 的 Mac，用 Tart 跑 macOS VM 也可以（Apple 授權允許每台 Mac 另跑 2 個 macOS VM，用途限開發、開發中的測試、macOS Server、個人非商業）。（已確認；查核修正：原寫「GitHub Actions 是唯一免費、不用租 24 小時的雲端做法」。CircleCI、Codemagic 的使用條款未驗證）
5. **GitHub Actions 的條款是灰色地帶。** 原文限制 GitHub-hosted runner 只能做「與該 repo 的軟體專案的開發、測試、部署、發布相關」的事；同一節另有「只能用來開發與測試你的應用程式」（條文沒有限定 macOS，查核修正）。違反時 GitHub 可停 job、停用 repo，甚至停權帳號；交件要用 GitHub repo，風險不能忽略。拿來驗證 pickfit 自己產出的安裝指南，勉強說得通；拿來大量掃第三方軟體，不符合。**只用在 demo 的少數幾筆。**（條款已確認；適用與否是我的解讀）
6. **不選 Daytona 當主要沙盒。** Tier 1、2 的對外網路被限制在「必要服務」清單，**沙盒層級無法覆寫**；要完全開放得到 Tier 3（儲值 $500）。照 README 跑 `curl https://某專案網域/install.sh` 這類安裝會被擋，造成誤判。預設隔離也只是容器（namespaces）。（已確認）
7. **每次驗證（5 分鐘、2 vCPU、4 GiB）約 $0.014–0.03**：Modal 約 $0.020、E2B 約 $0.014、Daytona 約 $0.014、Vercel Pro 約 $0.01–0.03。$100 credits 夠跑幾千次，錢不是限制，**時間才是**。（估算，第 3 節）
8. **本地 AI 工具不要下載大模型。** 驗證「裝得起來、能回一句話」用最小的模型就夠（< 1 GB）。需要 CUDA 才用 Modal 的 T4／L4（$0.59／$0.80 每小時），模型放 Volume 快取。（價格已確認；做法是建議）

---

## 1. pickfit 對沙盒的需求

| 需求 | 來源 | 對選型的影響 |
|---|---|---|
| 照 README 安裝並執行陌生專案 | brief 4.2 | 要能安全跑不受信任程式；要能出網下載 |
| 記錄步驟、卡在哪裡，讓 Meta 模型讀錯誤訊息並重試 | brief 4.2、6 | 沙盒要能多次 `exec`、保持狀態數分鐘到數十分鐘 |
| 執行畫面截圖給視覺模型判讀 | brief 4.2 | CLI 可以把終端輸出轉成圖；GUI 才需要桌面環境 |
| 兩個 demo 類別：開發者 CLI、本地 AI／LLM 工具 | brief 14 | 後者可能要 GPU 與模型下載 |
| demo 使用者在 Mac 上 | 任務說明 | 「Mac 上 brew 裝得起來」最好真的在 macOS 驗證 |
| 一個人、6 天、Python 管線 | brief 11、12 | 整合成本要低；Python SDK 優先 |
| 建議用 Modal sandbox（合作夥伴有 credits） | brief 11、rules 6 | Modal 有 $100 credits |

---

## 2. 比較表

所有雲端欄位都是 2026-10-28 讀官方文件的結果（已確認），除非標「未驗證」或「估算」。費用以美元計。

| 方案 | 隔離技術 | 能否安全跑不受信任程式（官方說法） | 啟動時間 | 最長執行 | 費用（CPU／記憶體／免費額度／比賽 credits） | GPU | 網路 | 套件與映像檔 | 作業系統 | SDK | 並行上限 | 整合成本（估算） |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Modal Sandbox** | gVisor 或 VM（獨立 kernel）；不指定時由 Modal 決定 | 「secure containers for executing untrusted code」 | 未公布沙盒數字；容器「about one second」；快照可讓大型 image「under a second」 | 預設 5 分鐘，最長 24 小時 | 沙盒是一般價 3 倍：$0.142／core-h（1 core＝2 vCPU，約 $0.071／vCPU-h）、$0.024／GiB-h；Starter 每月含 $30；**比賽 $100** | 有，只限 gVisor，**GPU 沙盒會被搶占**；T4 $0.59、L4 $0.80、A10 $1.10、L40S $1.95、A100 $2.10–2.50、H100 $3.95／h | 預設可出網；`block_network`、CIDR allowlist、網域 allowlist（Beta）；執行中可改政策（Alpha） | Image builder（apt／pip／Dockerfile／registry）；檔案系統、目錄、記憶體快照 | Linux | Python、JS/TS、Go | Starter 100 containers、GPU 10 | 4–6 h |
| **E2B** | Firecracker microVM | 「Every sandbox is a Firecracker microVM … safe to run code an LLM wrote or a user supplied」 | 從 template 快照載入約 80 ms | Hobby 1 小時、Pro 24 小時（暫停後重算） | $0.0504／vCPU-h、$0.0162／GiB-h；Hobby 送 $100 一次、免信用卡；Pro $150／月 | **沒有** | 預設可出網；可全關；allow 清單（IP、CIDR、網域）、deny 清單（只有 IP、CIDR）；執行中可改 | Template（Dockerfile 式）；pip／npm／apt；暫停（含記憶體）可無限保存、snapshot、fork | Linux | Python、JS/TS | Hobby 20、Pro 100–1,100；建立速率 Hobby 1／秒 | 3–5 h |
| **Daytona** | 預設**容器**（Linux namespaces）；可選 Linux VM、Windows VM | 首頁「Secure Infrastructure for Running AI-Generated Code」；網路文件提醒「unrestricted network access may pose security risks when executing untrusted code」 | 「<90ms」 | 無固定上限；閒置 15 分鐘自動停止（可設 0） | $0.0504／vCPU-h、$0.0162／GiB-h、磁碟 5 GiB 後 $0.000108／GiB-h；送 $200（不能用在 GPU） | 有：RTX 4090／5090、RTX PRO 6000、H100、H200、B200、B300、MI355X；隨需 $0.99–6.25／h；可搶占 $0.57 起（需 Tier 2） | **Tier 1、2 只能連「必要服務」清單，沙盒層級不能覆寫，執行中也不能改**；Tier 3（儲值 $500）才全開 | Docker image／Dockerfile 建 snapshot；VM snapshot；Volume（FUSE＋S3） | Linux、Windows；macOS 經 use.computer（另一套 API） | Python、TS、Ruby、Go、Java | Tier 1：10 vCPU／20 GiB／30 GiB | 3–5 h，加網路限制的處理 |
| **Cloudflare Sandbox（Containers）** | Firecracker microVM（每個 instance 獨立 kernel） | 「Execute untrusted or generated code in Linux virtual machines」 | 冷啟動「often in the 1-3 second range」 | 不保證；閒置逾時最長 6 小時；容器內的程式不算「活動」 | 需 Workers Paid（$5／月）；$0.072／vCPU-h（只算實際使用）、$0.009／GiB-h；每月含 375 vCPU-分、25 GiB-h；磁碟另計（含 200 GB-h） | 文件未列 GPU（未驗證是否另有） | 範例預設 `enableInternet: false`；可由 Worker 攔截並放行特定主機 | 自己的 Docker image（≤ 磁碟大小，帳號總共 50 GB）；容器快照 Beta（≤ 20 GB、30 天） | Linux | 只有 Worker 裡的 TS（其他語言要經自己的 Worker API） | 帳號 1,500 vCPU 同時 | 10–16 h |
| **Vercel Sandbox** | Firecracker microVM | 「Designed for untrusted code; microVM boundary prevents escapes」 | 「milliseconds」（沒有數字） | 預設 5 分鐘；Hobby 45 分鐘、Pro 24 小時 | Active CPU $0.128／h、記憶體 $0.0212／GB-h；Hobby 每月免費 5 CPU-h、420 GB-h；下載免費 | **沒有**（文件未提） | 預設全開；可 deny-all 或自訂（網域、CIDR）；執行中可改 | 預設 Ubuntu image；自訂 OCI image（Vercel Container Registry）；root；快照、持久沙盒 | Linux | JS/TS、Python | Hobby 10、Pro 10,000 | 4–6 h |
| **GitHub Actions** | 每個 job 一台新 VM（ephemeral） | 「ephemeral and clean isolated virtual machines」；但**條款限制用途**（第 5 節） | 未公布（排隊＋開機，未驗證） | 每個 job 6 小時 | **public repo 用標準 runner 免費**；private：Linux 2 核 $0.006／分、macOS $0.062／分；Free 方案每月 2,000 分鐘 | 只有付費的大型 runner（Linux 4 核 GPU $0.052／分，需 Team 以上） | 全開，沒有內建 egress 限制 | 預裝 image（macos-15 已有 Homebrew 6.0.22）；passwordless sudo；cache 每 repo 10 GB | Linux、Windows、**macOS**（M1 3 核 7 GB；Intel 4 核 14 GB） | REST API、`gh` CLI（任何語言） | Free：20 個 job、其中 macOS 5 個 | 4–6 h（macOS 部分） |
| **Fly.io（Machines／Sprites）** | Firecracker microVM（GPU 機器用 Cloud Hypervisor） | Sprites：「Run it in a hardware-isolated VM … Egress-locked and disposable」 | 未查到官方數字（未驗證） | 不限 | 無免費額度（試用 2 小時或 7 天）；shared-cpu-1x 1 GB $6.70／月；Sprites $0.0385／CPU-h、$0.0219／GB-h | GPU Machines 還在但不再擴充（官方部落格）；型號與價格未驗證 | Machines 的 egress 控制未驗證；Sprites 有 egress policy | 任何 OCI image；Volume；Sprites 有檢查點 | Linux | Machines REST API／Go；Sprites 有 Python、JS/TS、Go | 未驗證 | 8–12 h |
| **本機 Docker（runc）** | 容器，與主機共用 kernel | Vercel 文件：容器「Suitable for trusted code; container escapes are possible」 | **實測 0.30–0.50 秒** | 不限 | $0 | 看主機；Mac 上的 Docker 用不到 Apple GPU（未驗證） | `--network none` 可全斷；allowlist 要自己架 proxy | 任何 image | Linux 容器（Mac 上跑在 Docker Desktop 的 Linux VM 裡） | Docker CLI／Python SDK | 看主機 | 1–3 h |
| **本機 Docker＋gVisor** | gVisor（使用者空間 kernel） | gVisor：「additional defense against the exploitation of kernel bugs by untrusted userspace code」 | **實測 `runsc do` 0.08–0.16 秒**（兩輪合計，見第 8 節） | 不限 | $0 | 看主機 | 同上 | 同上 | **只支援 Linux 主機**（x86_64／ARM64，kernel 5.6+） | 同上 | 看主機 | 再加 2–4 h |

---

## 3. 每次驗證的成本（估算）

假設：一次驗證 5 分鐘（安裝＋smoke test），2 vCPU、4 GiB，CPU 使用率視為 100%（保守）。

| 方案 | 一次 | 免費額度能跑幾次 | 備註 |
|---|---|---|---|
| Modal | 約 $0.020 | $100＋$30／月 → 約 6,500 次 | 以 max(request, actual) 計費；可突發超過 request |
| E2B | 約 $0.014 | $100 → 約 7,200 次 | 磁碟 10 GiB 免費 |
| Daytona | 約 $0.014 | $200 → 約 14,000 次 | 但網路受 Tier 限制 |
| Vercel（Pro） | 約 $0.028（CPU 10% 時 $0.009） | Hobby 每月 5 active CPU-h → 約 30–300 次 | Hobby 超額會暫停，不會扣錢 |
| Cloudflare（standard-3） | 約 $0.018（超過月含量後） | 每月含量約 37 次 | 要先付 $5／月 |
| GitHub Actions macOS | public $0；private $0.31 | public 不限（受條款與並行 5 限制） | |
| 本機 Docker | $0 | — | |

**GPU smoke test（5 分鐘）**：Modal T4 約 $0.07、L4 約 $0.09（含 CPU／記憶體）；Daytona RTX 4090 約 $0.08（free credits 不能用）。

結論：預算不是瓶頸。瓶頸是**整合時間**與**誤判率**（網路被擋、gVisor 不相容、沙盒是 Linux 而使用者在 Mac）。

---

## 4. 各方案細節

### 4.1 Modal Sandbox

| 項目 | 內容 | 狀態 |
|---|---|---|
| 定位 | 「secure containers for executing untrusted code on Modal」 | 已確認 |
| Runtime | gVisor（「provides strong isolation and is suitable for most workloads」）或 VM（自己的 Linux kernel，可跑 Docker、FUSE）。不指定時由 Modal 決定。**GPU 沙盒只能用 gVisor，而且「subject to preemption」**（CPU 沙盒不會被搶占；資料來源：sandbox-resources）。Enterprise 才有巢狀虛擬化 | 已確認 |
| 生命週期 | 預設 5 分鐘，`timeout` 最長 24 小時；可設 `idle_timeout`；有 readiness probe | 已確認 |
| 網路 | 預設不能被連入、可以連出。三種限制：`block_network=True`、`outbound_cidr_allowlist`、`outbound_domain_allowlist`（Beta，只看 TLS SNI，443 port）。**DNS 除非全擋，否則不受限制**。執行中改政策：`sb._experimental_set_outbound_network_policy(...)`（Alpha），建立時要先設 `["*"]` 與 `["0.0.0.0/0"]` 才能之後收緊 | 已確認 |
| 資源 | `cpu`（physical core，1 core＝2 vCPU）、`memory`（MiB）；可設上限防止失控。磁碟與一般容器相同，**沙盒不能加大**；VM runtime 根目錄固定 512 GiB | 已確認 |
| 快照 | 檔案系統快照（預設保留 30 天，可改成不過期）、目錄快照、記憶體快照（Alpha，7 天）。快照就是 Image，可以 fork 出多個沙盒 | 已確認 |
| 映像檔 | 建議事先 publish 成 named image（`Image.from_name`），避免建立沙盒時才 build | 已確認 |
| 價格 | 沙盒以「不可搶占」計價，CPU／記憶體是一般價 3 倍：$0.00003942／core／秒、$0.00000667／GiB／秒；GPU 用一般價 | 已確認 |
| 方案 | Starter：$0＋用量，每月含 $30，100 containers、GPU 並行 10；Team：$250／月，含 $100 | 已確認 |
| Volume | 建議用 v2；「up to 2.5 GB/s of bandwidth」（不保證）；每月 1 TiB 免費，超過 $0.09／GiB-月 | 已確認 |
| 啟動時間 | 沙盒沒公布數字。cold-start 文件說容器「boot in about one second」；產品頁說用快照可讓大型 image「under a second」啟動 | 已確認（措辭）；實際數字未驗證 |
| 風險 | gVisor 不是完整 Linux kernel，少數需要特殊 syscall 或 kernel 功能的工具可能裝不起來（要改用 VM runtime，但 VM 不能配 GPU） | 未驗證（推論） |

### 4.2 E2B

| 項目 | 內容 | 狀態 |
|---|---|---|
| 隔離 | 「Every sandbox is a Firecracker microVM, not a container. Each one boots its own kernel」；kernel 為 LTS 6.1 | 已確認 |
| 啟動 | template 是「已在執行的沙盒快照」，「load the sandbox in ~80ms」 | 已確認 |
| 方案 | Hobby：免費、$100 一次性 credits、免信用卡、單次 1 小時、20 個並行、最多 8 vCPU／8 GiB、磁碟 10 GiB、建立 1 個／秒。Pro：$150／月、24 小時、100–1,100 並行、磁碟 20 GiB | 已確認 |
| 網路 | 預設可出網；`allow_internet_access=False` 全關；`network.allow_out` 支援 IP、CIDR、網域，`deny_out` 只支援 IP、CIDR（「Domains are not supported in the deny lists」）；網域只看 80 的 Host 與 443 的 SNI，且要把 `0.0.0.0/0` 放進 deny；執行中可 `update_network` | 已確認 |
| GPU | 「No. E2B sandboxes are CPU-only.」 | 已確認 |
| 持久化 | 暫停會存檔案系統與記憶體，暫停中的沙盒無限期保存；有 snapshot、fork。Volume 還在 private beta（要寫信申請） | 已確認 |
| 自訂環境 | `Template().from_template(...).pip_install(...).npm_install(...)`；也可從 Dockerfile／base image | 已確認 |
| 地區 | Google Cloud，以及 AWS US West | 已確認 |

### 4.3 Daytona

| 項目 | 內容 | 狀態 |
|---|---|---|
| 隔離 | 預設 **Linux 容器**（「Isolated container with dedicated namespaces」）；VM 類別（Linux VM、Windows）有獨立 kernel；GPU 沙盒是容器 | 已確認 |
| 啟動 | 文件標示「<90ms」 | 已確認（未說明測量條件） |
| 預設大小 | 1 vCPU／1 GB／3 GiB；組織上限 4 vCPU／8 GB／10 GB | 已確認 |
| 網路 | **Tier 1、2：網路受限，沙盒層級設定無法覆寫**，只能連「必要服務」（GitHub、`*.githubusercontent.com`、ghcr.io、PyPI、npm、crates.io、Go proxy、Ubuntu／Debian 套件庫、Hugging Face 等）。清單沒有 Homebrew API（formulae.brew.sh）、也沒有一般專案網域。Tier 1、2 也不能在執行中改網路政策（API 回錯誤），所以做不到「先開網路、再斷網」。Tier 3、4 才預設全開 | 已確認 |
| Tier | Tier 1：驗證 email；Tier 2：綁卡＋儲值 $25；Tier 3：儲值 $500；Tier 4：每 30 天儲值 $2,000。同一份文件兩張表對 Tier 1 記憶體寫 10 GiB 與 20 GiB，不一致 | 已確認 |
| 價格 | vCPU $0.0504／h、記憶體 $0.0162／GiB-h；送 $200；free credits「not available for GPU sandboxes」 | 已確認 |
| GPU | H100、B200、RTX PRO 6000、RTX 4090／5090、AMD MI355X；最多 8 張；GPU 沙盒是 ephemeral（停止即刪）。價格頁：隨需 RTX 4090 $0.99／h 起；可搶占（spot）RTX 4090 $0.57／h 起，spot 需 Tier 2 | 已確認 |
| macOS | 不由 Daytona 管理，要另外申請 use.computer 的 API key、先「reserve a Mac」。use.computer API 的租用時數「minimum 24」 | 已確認；價格未驗證 |

### 4.4 Cloudflare Sandbox（Containers）

| 項目 | 內容 | 狀態 |
|---|---|---|
| 形式 | 2026 年的文件把沙盒分成兩種：Containers（完整 Linux）與 Dynamic Workers（只跑 JS／Python／Wasm）。pickfit 要裝軟體，只能用 Containers | 已確認 |
| 隔離 | 「Each container instance runs in a Firecracker microVM with its own kernel and network」 | 已確認 |
| 冷啟動 | 「often in the 1-3 second range」，看 image 大小 | 已確認 |
| 壽命 | Durable Object 不活動後，instance 最多再跑 `setInactivityTimeout()` 設的時間（上限 6 小時）；**容器裡跑的程式不算活動**；Cloudflare 不保證執行時間 | 已確認 |
| 規格 | 最大 4 vCPU／12 GiB／20 GB（文件說這些是預設上限，可申請提高）；image 不能超過 instance 磁碟；帳號 image 總量 50 GB | 已確認 |
| 價格 | 需 Workers Paid（$5／月）；CPU 只算實際使用；記憶體與磁碟按 instance type 的配置量計 | 已確認 |
| 網路 | 沙盒範例用 `enableInternet: false`；可用 `interceptOutboundHttps()` 讓 Worker 決定放行哪些主機 | 已確認 |
| 整合 | 要寫 Worker＋Durable Object＋container image，用 wrangler 部署；Python 管線要透過自己的 HTTP API 呼叫。和 brief 第 11 節「MCP server 放 Cloudflare Worker」同平台是加分，但工時最高 | 估算 |

### 4.5 Vercel Sandbox

| 項目 | 內容 | 狀態 |
|---|---|---|
| 隔離 | Firecracker microVM，「Designed for untrusted code」 | 已確認 |
| 映像檔 | 預設 `vercel/sandbox/universal`（Ubuntu、Node LTS、Python 3.14）；可用自訂 OCI image；有 root | 已確認 |
| 方案 | Hobby：免費、每月 5 active CPU-h、420 GB-h、5,000 次建立、10 個並行、45 分鐘、4 vCPU／8 GB；超額會暫停到下個週期，不會扣款。Pro：$20／月 credit、24 小時、8 vCPU／16 GB | 已確認 |
| 磁碟 | 每個沙盒 64 GB NVMe；Drives（public beta）每個預設 1 TiB（Hobby 1 GiB） | 已確認 |
| 網路 | 預設 allow-all；可 deny-all（連 DNS 都擋）或自訂（網域、CIDR、拒絕 CIDR）；執行中可改；**從網路下載的流量免費** | 已確認 |
| GPU | 文件沒有提到 | 已確認（文件未列） |
| 認證 | 在 Vercel 外部呼叫要用 access token | 已確認 |

### 4.6 GitHub Actions（含 macOS）

| 項目 | 內容 | 狀態 |
|---|---|---|
| 隔離 | 「GitHub-hosted runners execute code within ephemeral and clean isolated virtual machines」 | 已確認 |
| 費用 | 「GitHub Actions usage is free for self-hosted runners and for public repositories that use standard GitHub-hosted runners」。大型 runner 在 public repo 也收費 | 已確認 |
| private repo | Free 方案每月 2,000 分鐘；Linux 2 核 $0.006／分、macOS 3／4 核 $0.062／分、macOS 5 核（M2 Pro）$0.102／分。舊版文件的「macOS 分鐘數乘 10 倍」在現行文件沒看到 | 價格已確認；倍數未驗證 |
| macOS runner | `macos-15`／`macos-14`／`macos-26`／`macos-latest`：M1 3 核、7 GB RAM、14 GB SSD、arm64；Intel 版 4 核 14 GB。macos-15 image 已裝 Homebrew 6.0.22；passwordless sudo；**不支援巢狀虛擬化** | 已確認 |
| 限制 | 每個 job 最長 6 小時；Free 方案同時 20 個 job、macOS 5 個 | 已確認 |
| 網路 | 沒有內建 egress 限制 | 已確認（文件未提供）；第三方工具未評估 |
| 安全 | 官方建議 `GITHUB_TOKEN` 給最小權限；跑陌生程式的 repo 不要放 secrets、`permissions: {}` | 已確認 |
| 條款 | 見第 5 節 | 已確認 |

### 4.7 Fly.io（簡要）

- Machines 跑在 Firecracker microVM；GPU 機器用 Intel Cloud Hypervisor。（已確認：架構文件、GPU 部落格）
- 沒有免費方案；新帳號試用「up to 2 hours of Machine runtime or 7 days」。（已確認）
- 官方部落格〈We Were Wrong About GPUs〉：GPU Machines 不會下架，但也不會有下一版。價格頁沒列 GPU。（已確認；目前型號與價格未驗證）
- 新產品 Sprites 專做 agent 沙盒：硬體隔離 VM、約 1 秒檢查點、egress policy；$0.0385／CPU-h、$0.021875／GB-h；有 Python、JS/TS、Go SDK。（已確認：sprites.dev）
- 對 pickfit：要自己處理映像檔、exec、清理；沒有比賽 credits。不建議。

### 4.8 本機 Docker（加或不加 gVisor）

- Docker 的隔離是 namespaces＋cgroups，和主機共用 kernel。Docker 自己的 Enhanced Container Isolation（用 Sysbox）是給「running untrusted or third-party container images」的，但要 **Business 訂閱**。（已確認）
- Mac 上的 Docker Desktop 把容器跑在一個 Linux VM 裡，所以對 Mac 主機有一層 VM 邊界；但驗證的仍是 **Linux**，不是 macOS。（推論，未驗證細節）
- gVisor「requires Linux 5.6+」，只支援 x86_64／ARM64 Linux 主機，Mac 上不適用。（已確認）
- Docker 另有 **Docker Sandboxes**（`sbx` CLI）：本機 microVM 跑 agent，對外 TCP 都經過主機上的 proxy 執行網路政策；本機使用免費。（已確認；未實測、未確認 Mac 上的效能）
- Docker Desktop 個人使用、或員工 < 250 人且營收 < $10M 的公司免費。（已確認）

---

## 5. 問題 1：驗證 macOS 安裝，只能靠 GitHub Actions 嗎？

**不是唯一。按分鐘計費、有免費額度的雲端做法至少有三個：GitHub Actions、CircleCI、Codemagic。**（查核修正：原寫「唯一免費、可按分鐘計費的雲端做法」）

| 做法 | 真的 macOS？ | 最低費用 | 隔離 | 對 6 天的可行性 |
|---|---|---|---|---|
| GitHub Actions `macos-15`（public repo） | 是，M1、已裝 Homebrew | $0 | 每個 job 一台新 VM | 高，但受條款限制 |
| GitHub Actions（private repo） | 是 | $0.062／分（扣免費分鐘） | 同上 | 高 |
| CircleCI Free | 是，M4 Pro Medium（6 CPU、28 GB RAM） | $0：每月 30,000 credits，macOS 200 credits／分 → 約 150 分鐘；macOS 並行 1 | CI VM（細節未驗證） | 中：要另開帳號、寫 config；使用條款未驗證 |
| Codemagic 個人免費 | 是，Mac mini M2 | $0：每月 500 分鐘，並行 1；超過 $0.095／分 | CI VM（細節未驗證） | 中：偏向行動 App CI；使用條款未驗證 |
| AWS EC2 Mac（Dedicated Host） | 是 | **最少租 24 小時**：mac2（M1）$0.65／h → 至少 $15.6；mac-m4 $1.23／h → 至少 $29.5 | 整台 Mac | 中：要開 AWS 帳號、設定 SSH |
| Daytona → use.computer macOS sandbox | 是 | **最少租 24 小時**，價格未公開 | 每台 Mac 上的 VM | 低：價格不明、另一套 API |
| 自己的 Apple silicon Mac＋Tart（macOS VM） | 是 | $0（Tart 在個人電腦上免授權費） | VM | 高，**前提是念誠有 Apple silicon Mac** |
| 直接在自己的 Mac 上跑 | 是 | $0 | **沒有** | 只適合已確認安全的 demo 專案 |

依據：
- AWS：「Mac instances are available only as bare metal instances on Dedicated Hosts, with a minimum allocation period of 24 hours」。價格取自 AWS 公開的 Dedicated Host 隨需價（US East Ohio／US West Oregon）。（已確認）
- use.computer API：`hours` 欄位「Lease duration in hours (minimum 24)」。（已確認）價格：官網是 SPA，抓不到價格（未驗證）。
- 24 小時的來源：Apple macOS Tahoe 26 授權第 3 節「Leasing for Permitted Developer Services」：出租 macOS 時「each lease period must be for a minimum period of twenty-four (24) consecutive hours」。（已確認）
- CircleCI：價格頁 Free 方案「30,000 credits」、macOS VM「M4 Pro Medium … 200 credits/min」、macOS 並行 1。（已確認：circleci.com/pricing、circleci.com/pricing/price-list）
- Codemagic：個人方案「500 free macOS M2 minutes / month」、「Max 1 parallel build」；pay-as-you-go「Mac mini M2 minutes $0.095/minute」。（已確認：codemagic.io/pricing）
- Apple macOS Tahoe 26 授權第 2B(iii) 條：允許在你擁有或控制的每台 Mac 上，在虛擬環境中再跑「up to two (2) additional copies or instances」，用途限「(a) software development; (b) testing during software development; (c) using macOS Server; or (d) personal, non-commercial use」，且不得用於「service bureau, time-sharing … or other similar types of services」。（已確認）
- Tart：「Usage on personal computers including personal workstations is royalty-free」，超過 100 個 CPU core 的伺服器安裝才要付費。（已確認）

### GitHub Actions 的費用與條款

**費用**：public repo 用標準 runner 免費（含 macOS）。目前 pickfit repo 是 private，在 private repo 跑 macOS 是 $0.062／分。（已確認）

**條款原文**（GitHub Terms for Additional Products and Features，Actions 一節）：

> Actions and any elements of the Actions product or service may not be used in violation of the Agreement, the GitHub Acceptable Use Policies, or the GitHub Actions service limitations set forth in the Actions documentation. Additionally, regardless of whether an Action is using self-hosted runners, Actions should not be used for:
> …
> - The provision of a stand-alone or integrated application or service offering the Actions product or service, or any elements of the Actions product or service, for commercial purposes;
> - Any activity that places a burden on our servers, where that burden is disproportionate to the benefits provided to users (for example, don't use Actions as a content delivery network or as part of a serverless application, but a low benefit Action could be ok if it's also low burden); or
> - If using GitHub-hosted runners, any other activity unrelated to the production, testing, deployment, or publication of the software project associated with the repository where GitHub Actions are used.

同一節緊接的段落（標題「Use for Development and Testing」，條文本身沒有限定 macOS；下一段是 Apple 的「Authorized Developer」）：

> **Use for Development and Testing**
> You may only access and use GitHub Actions to develop and test your application(s). Only one licensed user may access a virtual machine provided by Actions at any time.

同一節也寫：「GitHub may monitor your use of GitHub Actions. Misuse of GitHub Actions may result in termination of jobs, restrictions in your ability to use GitHub Actions, disabling of repositories … or in some cases, suspension or termination of your GitHub account.」（已確認）

**解讀（不是法律意見）**：
- 用 Actions 大量安裝、驗證**第三方**軟體來建資料庫，和「該 repo 的軟體專案」無關，也不是「your application(s)」。**不符合條款。**
- 把它定位成「測試 pickfit 自己產出的安裝指南」（`get_install_guide` 的輸出是 pickfit 的產品），在 pickfit 自己的 repo 裡跑少量 CI，**說得通但仍是灰色地帶**。
- 做法：只驗證 demo 那 2–5 筆；workflow 放在 pickfit 自己的 repo；README 寫清楚用途；不做排程、不做大量掃描；`permissions: {}`、不放 secrets。
- 另一條路：如果念誠有 Apple silicon Mac，用 Tart 在本機跑 macOS VM，就沒有 GitHub 條款問題。但 Apple 授權的 VM 用途是「software development」「testing during software development」「personal, non-commercial use」等，並禁止「service bureau, time-sharing … or other similar types of services」。驗證**第三方**軟體算不算其中一種，和 GitHub 條款是同一類解讀問題；只跑 demo 幾筆、不對外提供服務，風險較低。（條文已確認；適用與否是解讀，查核補充）
- 也可以改用 CircleCI 或 Codemagic 的免費 macOS 分鐘數；它們的使用條款沒有查（未驗證）。

**另外的限制**：macOS runner 只有 7 GB RAM，不能巢狀虛擬化；Metal／GPU 在 runner 裡能不能用，未驗證。本地 AI 工具只能跑很小的模型。

---

## 6. 問題 2：大型模型下載

| 方案 | 持久儲存 | 磁碟上限 | 下載速度 | 適不適合放模型 |
|---|---|---|---|---|
| Modal | Volume（建議 v2）；每月 1 TiB 免費，之後 $0.09／GiB-月；v1 上限 50 萬個 inode | 每個容器預設 512 GiB 配額；沙盒不能加大；VM runtime 固定 512 GiB | Volume「up to 2.5 GB/s」（不保證）；從 Hugging Face 下載的速度未驗證；官方範例用 `HF_XET_HIGH_PERFORMANCE=1` | **最適合**，而且有 GPU |
| E2B | Volume 還在 private beta | Hobby 10 GiB、Pro 20 GiB | 未驗證 | 不適合（沒有 GPU、磁碟小） |
| Daytona | Volume（FUSE＋S3 相容儲存），免費，每組織最多 100 個；不計入儲存配額 | 每沙盒最多 10 GB（預設上限）；`daytona-gpu` 預設只有 1 GiB | 未驗證；FUSE 讀大檔可能慢（推論） | 可以，但要處理網路 Tier |
| Cloudflare | 掛 R2 bucket；容器快照 ≤ 20 GB | 最大 20 GB | 未驗證 | 不適合（沒有 GPU） |
| Vercel | Drives（public beta，每個預設 1 TiB；Hobby 1 GiB）、快照 | 64 GB NVMe | 下載流量免費；速度未驗證 | 可放小模型；沒有 GPU |
| GitHub Actions | cache 每 repo 10 GB | 14 GB SSD | 未驗證 | 只能小模型；macOS 7 GB RAM |
| 本機 | 主機磁碟 | 主機磁碟 | 看網路 | demo 用；Mac 上的 Docker 用不到 Apple GPU（未驗證），本地 AI 工具應直接在 macOS 跑 |

**建議**：
- 驗證「本地 AI 工具」的目標是「裝得起來、能回一句話」，不是跑大模型。每個工具挑它支援的**最小模型**（幾百 MB 的量化模型），第一次下載後放 Modal Volume，之後所有沙盒共用。
- 只有工具本身需要 CUDA 時才開 GPU（T4 $0.59／h、L4 $0.80／h）。只支援 Apple Silicon／MLX 的工具，只能在 macOS 驗證（第 5 節）。

---

## 7. 問題 3：一個人、六天，推薦哪個

| 角色 | 選擇 | 理由 |
|---|---|---|
| **主要** | **Modal Sandbox** | 比賽 $100＋每月 $30；gVisor 隔離，官方明說給不受信任程式用；「先開網路安裝、再斷網執行」有 API；GPU 與 Volume 都有，本地 AI 類別用得到；Python SDK；brief 第 11 節本來就建議 |
| **Linux 備案** | **E2B** | 免信用卡、$100 credits、microVM、API 幾乎可以一對一替換（create → run → kill）。Modal 的 credits 沒發下來、或遇到 gVisor 不相容時切過去 |
| **macOS** | **GitHub Actions `macos-15`**（只跑 demo 的幾筆）；若念誠有 Apple silicon Mac，改用 **Tart** | 免費、按分鐘、已裝 Homebrew、`gh` 已在手上；條款限制見第 5 節。備選：CircleCI／Codemagic 免費分鐘數（條款未驗證） |
| **錄影保底** | **本機 Docker `--network none`** | 不靠網路與帳號；只跑已確認的 demo 專案 |

不選的理由（一句話）：
- Daytona：Tier 1／2 網路無法開放，Tier 3 要儲值 $500；預設只是容器。
- Cloudflare：只能從 Worker 用 TS 操作、要付 $5／月、冷啟動 1–3 秒，工時最高。
- Vercel：可以當第二個 Linux 備案（Hobby 免費，超額只會暫停、不扣款）；但沒有 GPU、Hobby 每月只有 5 active CPU-h。
- Fly：沒有免費額度，要自己處理太多。

### 建議的驗證流程（Modal）

1. 事先 publish 一個 named image：Debian＋git、curl、build-essential、Python、Node、Rust／cargo、Go（加快每次啟動）。
2. 建立沙盒：`timeout=900`、`cpu=1`、`memory=2048`、`outbound_domain_allowlist=["*"]`、`outbound_cidr_allowlist=["0.0.0.0/0"]`；不要帶任何 secrets。
3. Muse Spark 讀 README → 產生安裝指令 → `sb.exec` → 讀 exit code 與 stderr → 失敗就讓模型修正，最多 N 次。
4. 安裝成功後收緊網路（`_experimental_set_outbound_network_policy` 給空清單），跑 smoke test（`--help`、`--version`、一個最小範例）。
5. 把終端輸出轉成圖片給視覺模型判讀（CLI 不需要桌面環境）；記錄步驟、時間、截圖、結果。
6. `sb.terminate()`。

### 導入順序（對應 brief 第 12 節，10/31 做驗證 agent）

| 時間 | 做什麼 |
|---|---|
| 今天（10/28） | 申請 Modal credits；註冊 E2B（免卡）當備案；確認念誠有沒有 Apple silicon Mac |
| 10/31 上午 | 跑 `spikes/sb_modal_verify.py`，量啟動時間與一次驗證的成本 |
| 10/31 下午 | 驗證 agent 的重試迴圈；先跑 10 個 CLI 工具 |
| 11/1 | 本地 AI 類別：選一個小模型放 Volume；必要時試 GPU 沙盒 |
| 11/2 | demo 那幾筆在 macOS 跑一次（GitHub Actions 或 Tart） |

---

## 8. 本機實測紀錄（2026-10-28）

環境：雲端 Linux VM（Firecracker，kernel 6.18），4 vCPU、15.7 GiB，Docker 29.9.2（runc v1.5.2），gVisor runsc release-20261019.0。**不是 Mac**，數字只能當量級參考。腳本：`spikes/sb_local_timing.sh`。

| 測試 | 結果 |
|---|---|
| `docker run --rm python:3.12-slim true`（runc） | 0.30–0.50 秒（8 次） |
| `docker run --rm --network none python:3.12-slim python -c 'print(1)'` | 0.23–0.28 秒（6 次） |
| `runsc --network=none do python3 -c 'print(1)'`（gVisor，不經 Docker） | 0.11–0.12 秒；同一指令直接在主機跑 0.02 秒 |
| `runsc do` 回報的 kernel | `4.19.0-gvisor`，dmesg 第一行「Starting gVisor...」，確認真的在 gVisor 裡 |
| Docker 搭 gVisor shim（`--runtime io.containerd.runsc.v1`） | 失敗：寫 `oom_score_adj` 被拒（這個 VM 的限制） |
| gVisor `--network=host` 下 `pip install` | 失敗：Network is unreachable（這個 VM 的限制） |
| 主機上 `pip install httpie`（經 proxy） | 8.7–14.0 秒 |

測完已移除 runsc 與 shim，沒有留下容器。

---

## 9. Spikes

| 檔案 | 驗證什麼 | 需要 | 狀態 |
|---|---|---|---|
| `spikes/sb_modal_verify.py` | Modal 沙盒：建立時間、安裝、斷網後 smoke test、總時間 | `pip install modal`、`modal token new` | 未實測 |
| `spikes/sb_local_timing.sh` | 本機 runc 與 gVisor 的啟動時間 | Docker；gVisor 選用 | 已實測（第 8 節） |
| `spikes/sb_gha_macos_brew.yml` | macOS runner 上 brew 安裝與 smoke test、排隊時間 | 複製到 public repo 的 `.github/workflows/`、`gh` CLI | 未實測 |

建議再補（沒寫）：E2B 版的 `sb_e2b_verify.py`（同樣流程，換成 `Sandbox.create()`／`commands.run()`），以及 Modal GPU 沙盒跑一個小模型的 smoke test。

---

## 10. 需要的金鑰與申請方式

| 服務 | 要什麼 | 怎麼申請 | 狀態 |
|---|---|---|---|
| Modal | `MODAL_TOKEN_ID`、`MODAL_TOKEN_SECRET` | modal.com 註冊 → `pip install modal` → `modal token new`；比賽 credits 依 Discord／活動頁流程領（前 1,000 人） | 未申請 |
| E2B | `E2B_API_KEY` | e2b.dev 註冊（免信用卡）→ dashboard 產生 API key | 未申請 |
| Daytona | `DAYTONA_API_KEY` | app.daytona.io 註冊 → API Keys | 不建議 |
| Vercel | access token（＋team／project） | vercel.com Hobby → Account Settings → Tokens | 備用 |
| Cloudflare | Workers Paid 方案＋`wrangler login` | dash.cloudflare.com | 不建議 |
| GitHub Actions | 對目標 repo 有 `actions:write` 的 token；已有 `gh` | 已有帳號 | 可直接用 |
| AWS EC2 Mac | AWS 帳號、Dedicated Host 配額 | AWS console | 不建議 |

---

## 11. 未驗證清單

1. Modal 沙盒的實際啟動時間（官方沒給數字）。
2. Modal 的 gVisor 對常見 CLI 安裝（cargo、go install、預編譯 binary、Homebrew on Linux）的相容性。
3. Modal Starter 方案註冊要不要綁信用卡；比賽 $100 credits 的領取方式與到帳時間。
4. Modal 網域 allowlist（Beta）與動態網路政策（Alpha）是否穩定。
5. 從 Hugging Face 下載到 Modal／Daytona／Vercel 的實際速度。
6. GitHub Actions macOS runner 的排隊與開機時間；private repo 的 macOS 分鐘數是否還有倍數。
7. GitHub macOS runner 裡 Metal／GPU 能不能用（影響 MLX 類工具）。
8. use.computer 的 Mac 租用價格。
9. Cloudflare Containers 是否有 GPU（文件沒列）。
10. Fly.io GPU 目前的型號、價格與可用性；Fly Machines 的啟動時間與 egress 控制。
11. Mac 上的 Docker Desktop 能否使用 Apple GPU（推論不行）。
12. Daytona 的「<90ms」與 Vercel 的「milliseconds」是在什麼條件下量的。
13. 以上雲端服務都沒有實際呼叫過。

---

## 12. 來源

全部於 2026-10-28 讀取。

**Modal**
- Sandboxes 指南：https://modal.com/docs/guide/sandbox
- Networking and security：https://modal.com/docs/guide/sandbox-networking
- Snapshots：https://modal.com/docs/guide/sandbox-snapshots
- Sandbox resources and pricing：https://modal.com/docs/guide/sandbox-resources
- 價格頁：https://modal.com/pricing
- CPU、記憶體、磁碟：https://modal.com/docs/guide/resources
- Volumes：https://modal.com/docs/guide/volumes
- Storing model weights：https://modal.com/docs/guide/model-weights
- Cold start：https://modal.com/docs/guide/cold-start
- Security and privacy：https://modal.com/docs/guide/security
- 產品頁：https://modal.com/products/sandboxes

**E2B**
- 價格頁：https://e2b.dev/pricing
- Billing & limits：https://e2b.dev/docs/billing
- Sandbox lifecycle：https://e2b.dev/docs/sandbox
- Internet access：https://e2b.dev/docs/sandbox/internet-access.md
- GPU FAQ：https://e2b.dev/docs/faq/gpu-support.md
- Security & compliance：https://e2b.dev/docs/sandbox/security
- Template how it works：https://e2b.dev/docs/template/how-it-works.md
- Volumes：https://e2b.dev/docs/volumes.md、https://e2b.dev/docs/faq/volumes-beta-limitations.md
- 首頁：https://e2b.dev

**Daytona**
- 價格頁：https://www.daytona.io/pricing
- Limits：https://www.daytona.io/docs/en/limits/
- Network limits：https://www.daytona.io/docs/en/network-limits/
- Isolation：https://www.daytona.io/docs/en/isolation.md
- Sandboxes：https://www.daytona.io/docs/en/sandboxes.md
- Linux sandboxes：https://www.daytona.io/docs/en/linux-sandboxes.md
- GPU sandboxes：https://www.daytona.io/docs/en/gpu-sandboxes.md
- macOS sandboxes：https://www.daytona.io/docs/en/macos-sandboxes.md
- Volumes：https://www.daytona.io/docs/en/volumes.md
- Billing：https://www.daytona.io/docs/en/billing/
- Architecture：https://www.daytona.io/docs/en/architecture.md
- use.computer API：https://api.use.computer/openapi.yaml

**Cloudflare**
- Sandboxes on Cloudflare：https://developers.cloudflare.com/sandbox/
- Sandbox lifetime：https://developers.cloudflare.com/sandbox/concepts/lifetime/
- Sandbox security：https://developers.cloudflare.com/sandbox/concepts/security/
- Credentials and network：https://developers.cloudflare.com/sandbox/network/
- Containers pricing：https://developers.cloudflare.com/containers/platform/pricing/
- Containers limits：https://developers.cloudflare.com/containers/platform/limits/
- Containers architecture：https://developers.cloudflare.com/containers/concepts/architecture/

**Vercel**
- Vercel Sandbox：https://vercel.com/docs/sandbox
- Concepts：https://vercel.com/docs/sandbox/concepts
- Pricing and quotas：https://vercel.com/docs/sandbox/pricing
- Firewall：https://vercel.com/docs/sandbox/concepts/firewall

**GitHub**
- Terms for Additional Products and Features（Actions 一節）：https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features
- Actions billing：https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Runner pricing：https://docs.github.com/en/billing/reference/actions-runner-pricing
- Product usage included：https://docs.github.com/en/billing/reference/product-usage-included
- GitHub-hosted runners：https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Actions limits：https://docs.github.com/en/actions/reference/limits
- Secure use：https://docs.github.com/en/actions/reference/security/secure-use
- Acceptable Use Policies：https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
- macOS 15 arm64 runner image：https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md

**Fly.io**
- Pricing：https://fly.io/docs/about/pricing/
- Architecture：https://fly.io/docs/reference/architecture/
- We Were Wrong About GPUs（/docs/gpus/ 轉址到此）：https://fly.io/blog/wrong-about-gpu/
- Sprites：https://sprites.dev/

**本機 Docker／gVisor／macOS**
- gVisor docs：https://gvisor.dev/docs/
- gVisor install：https://gvisor.dev/docs/user_guide/install/
- gVisor security：https://gvisor.dev/docs/architecture_guide/security/
- Docker engine security：https://docs.docker.com/engine/security/
- Docker Enhanced Container Isolation：https://docs.docker.com/enterprise/security/hardened-desktop/enhanced-container-isolation/
- Docker Sandboxes：https://docs.docker.com/ai/sandboxes/、https://docs.docker.com/ai/sandboxes/architecture/
- Docker Desktop 授權：https://docs.docker.com/subscription/desktop-license/
- AWS EC2 Mac：https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-mac-instances.html
- AWS Dedicated Host 隨需價（價格頁使用的公開 JSON）：https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/dedicatedhost-ondemand.json
- Apple macOS Tahoe 26 授權：https://www.apple.com/legal/sla/docs/macOSTahoe.pdf
- Tart 授權：https://tart.run/licensing/
