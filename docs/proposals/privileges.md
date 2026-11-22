# 要 root、要金鑰的軟體怎麼驗

> 提案（2026-11-21）。總覽和共同規則在 [README.md](README.md)。

## 現況

箱子的規則寫在 [box.py](../../pickfit/verify/box.py) 開頭：被測軟體只在箱子裡跑，用非 root 的使用者，環境裡沒有任何 API key，每次驗證一個全新箱子。箱子裡的 root 是 pickfit 自己蒐證用的身分，被測軟體拿不到（[limits.py](../../pickfit/verify/limits.py) 的檢查項目）。

這套規則擋下來的紀錄，11/21 在 `data/software/` 的 1,167 筆裡數到這些：

| 代號 | 筆數 |
|---|---|
| needs_account | 132 |
| needs_service | 102 |
| needs_more_resources | 42 |
| needs_display | 37 |
| needs_root | 32 |
| needs_gpu | 15 |
| needs_hardware | 15 |
| needs_container | 13 |
| needs_toolchain | 10 |

數的是代號在紀錄裡出現的筆數，整筆驗不了和只有某項功能驗不了的都算在內。這是 `loop/20261115` 分支上的資料，分支當時落後 main 301 個 commit。main 的 [audit-20261120.md](audit-20261120.md) 算的方式不同，數字接近，分別是 needs_service 100、needs_account 120、root 33、容器 14。needs_account 裡有多少是模型供應商的金鑰、多少是第三方服務的帳號，兩邊都還沒有細分。

main 上 11/20 的 [sandbox-env-unlock.md](sandbox-env-unlock.md) 已經處理掉一部分，這份提案不重做：

- watch 會照抽取結果自動挑箱子：GPU（T4、L4）、模擬麥克風、編譯工具鏈。
- 後端服務的第一版：`pickfit-services` 可以起 Postgres、Redis 和 HTTP mock，由箱子使用者自己啟動。
- 提案中：受測工具用的 LLM 計費代理（放在 Worker）、喇叭輸出擷取、虛擬攝影機。

那份提案沒有處理的是 root、Docker、第三方服務的帳號、對外有影響的動作，還有紀錄上怎麼記「給過什麼」。這份補的是這幾塊。

另外兩件事：

- agent 沒有管道說「我需要什麼」。它只能失敗，再由 [failure.py](../../pickfit/verify/failure.py) 的規則從輸出和 agent 的描述猜原因。
- `loop/issues.md` 的 H-003（沒有 root）、H-004（沒有 Docker）、H-005（資源不夠）在 main 上也都還開著。H-003 已經寫了「由 harness 以 root 代裝具名套件」的方向，還沒試。

## 原則

1. **agent 不自己拿權限。** 卡住時送出一個結構化的請求，由 harness 照政策表決定：直接給、換一種箱子重跑，或者拒絕並記成 coverage 的 gap。
2. **真的金鑰不進箱子，也不進模型的 context。** 箱子拿到的是替身，或是箱外代理發的限額、限時 token。
3. **可以把整台機器的權限交出去**，前提是那台機器用完就丟、身上沒有任何憑證、對外連線有限制。
4. **給過什麼都寫進紀錄。**「這款軟體要 sudo、要 Docker、要 OpenAI key」本身就是使用者想知道的事。用替身驗的和用真服務驗的分開標。

## 升級階梯

| 階 | 箱子 | 被測軟體拿到什麼 |
|---|---|---|
| 1 | 現在的箱子（gVisor 或 VM） | 非 root 使用者 |
| 2 | 同一種箱子 | 多了 harness 代裝的具名套件 |
| 3 | 同一種箱子加配件 | 多了同箱的服務（資料庫、佇列）或模型端點 |
| 4 | 全權 VM 箱 | 一整台用完就丟的 VM：root、systemd、Docker |
| 5 | 特殊硬體 | GPU、macOS、Windows |
| 6 | 不驗 | 照實記 gap |

每升一階都重開全新箱子，重播也在同一階的全新箱子做。「每次驗證都用全新箱子」的規則不變。

## 提案

### P1 紀錄記下給過什麼、用什麼驗的（收錄前）

大量收錄之後才補這兩個欄位，就得把箱子重跑一次，所以先定格式。

每次 run 加一個 `grants` 清單，每項記：

- `kind`：`system_package`、`service`、`model_endpoint`、`root`、`container_engine`、`test_identity`、`virtual_device`、`extra_machine`
- `name`：套件名、服務名、身分的代號
- `tier`：上面階梯的第幾階
- `requested_by`：`agent`（agent 送出請求）或 `plan`（抽取時就知道要）
- `shown_in_guide`：安裝指南上要不要標出來，例如「需要 sudo」

每項功能的驗證結果加一個 `fidelity`：

- `real`：對真的服務驗的
- `compatible`：相容端點，後面是真的模型
- `stand_in`：替身或假資料，只證明接線通了
- 沒用到外部東西的不填

工具頁和 MCP 回答要分開講這三種，`stand_in` 不能寫成「驗過能用」。頁面上怎麼呈現，等格式定了再跟 coverage 提案一起做。

`schema.py` 是 loop guard 保護的檔案，改動寫成 `loop/proposals/` 底下的 patch。舊紀錄沒有這兩個欄位時當成空的，不用遷移。

### P2 能力請求（可以並行做）

驗證 agent 多一個工具 `request_capability(kind, name, why)`。harness 照政策表回三種答案：

- **給。** 同一個箱子裡馬上生效，例如代裝套件、起一個服務。
- **換箱子。** 這次 run 結束，harness 用上一階的箱子重開一次，agent 從頭來。一筆紀錄最多升兩階，超過就停。
- **不給。** 回原因，agent 把相關的功能記成 not_checked，原因用現有的 `needs_*` 代號。

政策表是一份資料檔，不寫死在 prompt 裡：哪些 `kind` 自動給、哪些要換箱子、哪些一律不給、每筆紀錄的花費上限。agent 的請求只是一個請求，README 或軟體輸出叫 agent 去要權限，要到的也只有政策表允許的東西。

`failure.py` 從輸出猜原因的規則留著，當作 agent 沒有送請求時的後備。它也是保護檔案，要改就寫成 patch。

### P3 代裝具名套件、基底映像補函式庫（可以並行做）

這是 H-003 的方向。

- 請求的 `kind` 是 `system_package` 時，harness 用 root 跑 `apt-get install <名稱>`。只接受發行版套件庫裡的具名套件，不接受外加的套件來源、`.deb` 檔或任意指令。
- 裝了什麼記進 `grants`，安裝指南多一步 `sudo apt-get install <名稱>`，重播時由 harness 在全新箱子照做。
- `sandbox.Dockerfile` 預裝 libxcb1、libgl1、libglib2.0-0 這幾個桌面 Linux 幾乎都有的函式庫。映像雜湊會變，所有種類的箱子都要重建、重跑 `--limits-test`。
- 被測軟體還是沒有 root，`limits.py` 的檢查照樣要通過。

### P4 服務目錄再加幾種，加一個替身模型端點（可以並行做）

needs_service 和 needs_account 是筆數最多的兩類，這一項幾乎不花錢。

**服務目錄。** 沿用 sandbox-env-unlock 第 2 節的 `pickfit-services`：服務由箱子使用者自己啟動，只聽 127.0.0.1，agent 把啟動服務當成一個安裝步驟。這裡只加兩件事。第一，啟動過哪些服務記進 P1 的 `grants`。第二，照 gap 排行再加種類：MySQL 或 MariaDB、S3 相容儲存、SMTP 收信、git 主機、AWS 模擬器。用哪個專案、授權合不合，實作時逐一確認後寫在回報裡。

**替身模型端點。** 做成 `pickfit-services` 的一種：箱子裡起一個 OpenAI 相容的 server，後面接 SmolLM2-135M（Apache-2.0，[agent.py](../../pickfit/verify/agent.py) 的 `TINY_MODELS` 已經在用）。請求核准後才設 `OPENAI_BASE_URL` 和一把假的 key。135M 的模型答不出像樣的內容，所以這一項只用來驗「server 起得來、請求走得通」，`fidelity` 記 `stand_in`。

### P5 計費代理：照 sandbox-env-unlock 第 6 節做，這裡只補紀錄

功能需要真的模型才驗得出來時，走那份提案的計費代理：放在 Worker、一次驗證一張票、額度 US$0.20、一小時到期、限一個模型。代理放 Worker 的原因是 Modal 的箱子連不到 watch 主機。這份提案不另外設計一個代理，只補三件事：

- 走代理驗的功能，`fidelity` 記 `compatible`。軟體指定要某一家的某個模型、代理換成別的模型時，在紀錄裡寫明。
- 發過票記進 `grants`，`kind` 是 `model_endpoint`。
- P7 的測試身分 token 也經同一個代理發，不另外做一套保管機制。

代理後面接哪一家、用哪個模型，照那份提案等念誠決定。[aws.md](aws.md) 的 A1 做完之後，接 Bedrock 是其中一個選項。

### P6 全權 VM 箱（可以並行做，先在 EC2 實作）

給安裝程式要 root 加 systemd、只有 `docker run`、要核心模組或 TUN 的軟體用。H-004 的 Docker 也在這裡解。

- 一次驗證一台 VM，被測軟體的使用者可以 sudo。VM 用完就刪。
- VM 沒有 instance profile，metadata 服務在 instance 層級關掉。現在的箱子是在箱內用路由擋 metadata，軟體有了 root 就能改回來，所以要從外面關。
- 對外連線由安全群組管：只開 DNS、80、443，25 埠不開，同一個群組的機器互相連不到。離線檢查用換安全群組來斷網，VM 裡的 root 改不了。
- 軟體有 root 之後，箱內蒐集的東西理論上都能造假。所以判定盡量用箱外看得到的證據：從外面探埠、從外面打 HTTP、關機後讀磁碟。紀錄上標明這次是全權箱。
- `--limits-test` 要有全權箱自己的一組檢查：root 也連不到 metadata、磁碟上沒有憑證、連不到其他機器和私有網段、對外只有那幾個埠、換安全群組後真的斷網、run 結束後 instance 確實刪掉。`limits.py` 是保護檔案，寫成 patch。
- 還要有一支清理程式，依 `pickfit:` tag 和存活時間刪掉漏網的 instance。
- EC2 同時最多兩台。agent 和重播各一台，這條 lane 同一時間只能有一筆，寫成 lane 的並行限制。
- 寫成箱子介面的能力旗標（`root`、`systemd`、`container_engine`、`kernel_modules`），別的平台之後也能接。Modal 的 `--runtime vm` 跑不跑得動 rootless Podman，照 H-004 寫的先查一次。

機器成本和 lane 的預算在 [aws.md](aws.md)。

### P7 測試身分（可以並行做，一個服務一個服務加）

給要第三方帳號或 OAuth 的軟體用，例如 Notion、Slack、GitHub 的 MCP server。

- 帳號由人建，一個服務一組：專用信箱、只放假資料的 workspace 或 repo、權限最小的 token。agent 不自己註冊帳號，CAPTCHA、簡訊驗證、2FA 都由人做一次。
- 加一個服務之前先讀它的服務條款，確認允許自動化測試。
- token 放在計費代理那邊（P5），箱子拿到的是有時效的那一把。帳號清單和 token 都不進 repo。
- 測試身分裡的資料每次驗證後重設，避免上一款軟體留下的東西影響下一款。
- `fidelity` 記 `real`。
- 付費方案和授權碼不買。有免費層就驗免費層，其他記 gap。

### P8 對外有影響或不可逆的動作（可以並行做）

這幾類軟體要驗就一定會「做事」，所以要給它假的對象。

| 軟體類型 | 給它什麼 |
|---|---|
| 埠掃描、弱點掃描、壓測、爬蟲 | harness 自己開的靶機，對外連線只通到靶機 |
| 寄信工具 | SMTP 導進箱內的收信替身 |
| 磁碟分割、抹除、改開機設定 | 只在全權箱，另外掛一顆假磁碟 |
| 會開雲端資源、會呼叫付費 API | 雲端模擬器，或 P5 的計費代理 |
| 資安工具、來路不明的 binary | 對外連線預設全關，SBOM 照 [security.md](security.md) 收 |

EULA、遙測同意這類條款，在箱子裡同意，安裝指南上標出來。

## 狀況對照

| 狀況 | 走哪一項 |
|---|---|
| `sudo apt install` 具名套件 | P3 |
| 缺常見的執行期函式庫 | P3（基底映像） |
| 安裝程式要 root 加 systemd、寫 `/etc`、裝成服務 | P6 |
| 只有 `docker run` 或 compose | P6 |
| 核心模組、eBPF、FUSE、TUN、raw socket | P6 |
| 要 `/dev/kvm` | P6，機型要支援巢狀虛擬化，還沒查 |
| macOS 的 `.pkg` 要管理者密碼、TCC 權限、系統擴充功能 | VM 裡的使用者給 sudo，TCC 在基底映像先授權，做不到的記 gap。等有 Mac 主機再做 |
| Windows 的 UAC、驅動程式、SmartScreen | Windows 箱用管理者身分裝，指南標「需要管理者權限」 |
| 模型供應商的 API key | P4 的替身，不夠再走 P5 |
| 第三方服務的帳號、OAuth | P7 |
| 雲端憑證（AWS CLI 工具、terraform、k8s 工具） | P4 的模擬器。真的要雲端帳號的，另開空的沙盒帳號發短效憑證，先不做 |
| 付費方案、授權碼 | 不買，記 gap |
| 要讀使用者自己的資料（信箱、行事曆、SSH key、瀏覽器 profile） | 箱子裡放合成的假資料 |
| 要資料庫、佇列、另一個 LLM server | 已有第一版的 `pickfit-services`，缺的種類走 P4 |
| GPU、大模型 | 已經接進 watch（sandbox-env-unlock 第 1 節），顯存最大 24 GB |
| 麥克風、喇叭、攝影機 | 麥克風已經有。喇叭和攝影機在 sandbox-env-unlock 第 3、4 節，原生 App 的攝影機要核心模組，可以共用 P6 的 VM |
| 序列埠、USB、藍牙、手機配對 | 序列埠用虛擬裝置。其他記 needs_hardware |
| 要公開網址、webhook 回呼、TLS 憑證 | 箱內 loopback 加自簽 CA，要公網回呼時由 harness 轉送 |
| 要兩台以上的機器 | P6，同一個子網開兩台 |
| 記憶體、磁碟、時間不夠 | 現有的 `--memory-mb`、`--file-mb`（H-005） |
| 掃描、寄信、抹磁碟這類動作 | P8 |

## 人什麼時候進來

只有三種：

1. 建測試身分（每個服務一次）。
2. 一筆紀錄的花費超過政策表的上限。
3. 動作會影響到 pickfit 以外的人或機器。這一種不靠人放行，直接不做，改用 P8 的假對象。

其他時候 agent 和 harness 自己走完，不停下來問。

## 順序

照卡住的筆數排：

1. P1，收錄前。
2. P3，解 needs_root 裡缺套件和缺函式庫的部分。
3. P6，解剩下的 needs_root 和 needs_container。這兩類 main 上還沒有人做。
4. P4 的替身端點和新的服務種類，排在 sandbox-env-unlock 的服務映像上線之後。
5. P2。上線前，P3 先由抽取結果和 `failure.py` 的原因觸發，就像 `box_needs` 現在挑箱子那樣。
6. P5 跟著計費代理的進度。P7 和 P8 看 gap 排行決定先做哪個服務、哪一類軟體。

## 驗收

- `grants` 和 `fidelity` 的格式、舊紀錄相容、政策表的三種答案、升階上限，都有測試。
- 代裝套件：拒絕套件庫以外的來源、重播照做、`--limits-test` 照樣通過。
- 新的服務種類和替身端點：照 `pickfit-services` 現有的測法，箱子使用者起得來、只聽 127.0.0.1、斷網時一起被切斷。
- 走計費代理驗的功能，紀錄上的 `fidelity` 和 `grants` 有測試。代理本身的測試歸 sandbox-env-unlock。
- 全權箱：自己的 `--limits-test` 檢查組，加上清理程式的測試。真的開機器的那一次由協調 session 跑。
- 回報列出：每一項預期解掉幾筆、哪些數字還沒實測、新增的第三方工具和授權。

## 不做的事

- 把真的金鑰放進箱子的環境變數。
- 讓 agent 自己註冊帳號、繞過 CAPTCHA、輸入付款資料。
- 讓被測軟體連到 pickfit 以外的人的主機做掃描、壓測或寄信。
- 在 gVisor 箱子裡把 root 交給箱子使用者。要 root 就換全權箱。
- 同一台全權 VM 跑第二款軟體，或讓 agent 和重播共用一台。
- 把 `stand_in` 的結果寫成「驗過能用」。

## 11/21 到 11/22 在真的機器上跑過的

協調 session 跑的，都沒有寫回紀錄。

- **限制檢查。** Modal 七種箱子全過（一般 24、顯示 33、音訊 28、toolchain 24、服務 26、VM 25、GPU T4 25）。EC2 的 Linux 箱 25/25，服務箱 27/27。apt 探測在 gVisor、VM 和 EC2 上都過。
- **全權箱的限制檢查。** 第一次 27 項過 25 項，沒過的兩項是檢查程式自己的錯：cloud-init 在 `/run/cloud-init` 留了一份 VM 自己的 host key，對照組的 here-document 沒有結束在自己的一行。念誠套上 patch 之後 27/27。
- **全權箱真的驗一筆。** agent-database-cli，agent 用 `sudo apt-get install` 自己裝了 Redis，驗到 `function`，重播通過，6 項功能驗了 4 項，約 200 秒，模型 US$0.31，機器不到 US$0.01。同一筆在一般箱子只驗到 2 項。
- **這一筆跑出兩個問題，都修了。** 第一個是紀錄的 `grants` 是空的，沒記下這次用了 root。現在全權箱的 report 會寫箱子給了什麼，有步驟用了 `sudo` 或容器引擎，就記成 `requested_by` 是 `plan` 的 grant。第二個是 SBOM 收不到，因為全權箱的映像沒有 syft 那三支程式，`python3` 和 `npm` 也不在 `sbom.py` 叫的路徑。映像照 `sandbox.Dockerfile` 的版本和 SHA-256 補上了。重烘之後限制檢查 27/27，同一筆驗證的 `grants` 有 `root sudo`，SBOM 收到 4 個套件、沒有錯誤。
- **政策表試跑。** 把表打開跑了兩次。服務箱那次是計畫給的 PostgreSQL 和 Redis，記成 `fidelity` real。一般箱子那次 agent 開口要 Redis，被拒絕，4 項功能記成 not_checked，其他照驗。
- **還沒在真的 run 出現過的：** 政策表「同箱直接給」和「換箱子重跑」這兩種答案、代裝套件（`PICKFIT_SYSDEPS=1`）接在一筆真的驗證裡、全權箱從 watch 進來。

## 還沒確認的

- needs_account 的組成。替身端點、計費代理和測試身分各能解多少，要先分類才知道。
- EC2 哪些機型支援巢狀虛擬化，配額夠不夠。
- 服務目錄每個候選專案的授權和取得方式。
- 全權箱開機到可以用要多久。11/22 在台北量到 44 到 60 秒（五次）。現在的 EC2 Linux 箱冷開機約 71 秒（us-east-1）。
- 箱外蒐證做到什麼程度才夠。關機後讀磁碟會拉長每筆的時間，值不值得要實測。
