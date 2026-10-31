# macOS／Windows 真機驗證：可行性比較

2026-10-29 13:30（台北）查證 · Phase 1 · 給念誠與協調的 session。這一階段**沒有安裝任何東西、沒有花錢、沒有開帳號**；雲端與 VM 都**未實測**。

標記同 [sandbox-compare.md](sandbox-compare.md)：**已確認**＝讀過官方文件、條款或價格頁原文；**估算**＝自己算的；**未驗證**＝沒有第一手資料或要實測才知道。來源編號 [S#] 見第 7 節。

---

## 0. 結論

1. **macOS（11/2 前）：在這台 Mac 上用 Tart 跑 macOS VM。** 每次驗證從 base image `tart clone` 一台（APFS copy-on-write，幾乎不佔空間），用完 `tart delete`。費用 $0。Apple 授權允許每台 Mac 另跑 2 個 macOS VM，用途包含「software development」與「testing during software development」[S1]；Tart 的 FSL 授權只禁止做競爭產品 [S4]。`tart exec` 走 vsock，不走網路，**斷網後仍能下指令**，所以重播時的斷網 smoke test 做得到 [S6]。要念誠同意：`brew install openai/tools/tart`，以及下載約 25 GB 的 image（磁碟約 33 GB）[S7][S8]。
2. **Windows（11/2 前，有條件）：GitHub Actions 的 `windows-2025`（x64），只跑 demo 規模（≤10 款）。** 每個 job 一台新 VM、管理員權限；private repo 每月含 $12 額度，Windows 每分 $0.010，約 1,200 分鐘 [S12][S13]。兩個前提：(a) 念誠接受條款的灰色地帶（第 3.1 節）；(b) 斷網重播要先實測（Windows 防火牆擋出站，runner 本身還要連 GitHub），失敗就在紀錄寫「沒有斷網重播」。念誠不接受 (a)，Windows 就只做第 4 節的「發佈證據」，真機留到賽後。
3. **不用 VM 的較弱證據**：查 release 資產、Homebrew bottle、winget／Scoop manifest、npm 的 `os`／`cpu`、PyPI wheel 標籤、上游 CI 在 macOS／Windows runner 的結果。只能說「有發佈 macOS／Windows 版」或「上游 CI 在該 OS 過」，**不能寫成我們驗證過**。建議放在 `VerificationRun` 以外的新欄位（第 4 節），schema 要協調 session 決定。
4. **賽後才實際**：Windows 11 on Arm 本機 VM（Parallels／UTM＋正式授權）、Azure／AWS 上的 Windows VM（x64、可用網路規則真的斷網）、Windows Sandbox（要實體 Windows PC）、dockur/windows（要 KVM 主機＋授權）、Mac 主機群（Scaleway、EC2 Mac，24 小時起租）、Intel Mac（x86_64）。
5. **Linux 跑不出來、真機才看得到的問題，demo 候選裡已經有**（第 4.3 節，查 release 與 CI 得知，沒有執行）：`rimz` 的 macOS 執行檔在 Ubuntu 上交叉編譯，CI 從沒在 macOS 跑過；`shep` 的 brew tap 停在 0.1.26（現行 0.19.0）而且要用 cargo 從原始碼編；`orbit` 的 npm 套件排除 Windows。

---

## 1. runner 要做到什麼

| 需求 | 為什麼 | 對選型的影響 |
|---|---|---|
| 每次驗證一台全新、用完即丟的環境 | agent 與重播各用一台（`pipeline.verify_task` 先關 agent 的 box 再開重播的 box） | 要能快速 clone／重開；同時只需要 1 台 |
| 安裝時開網路，smoke test 時斷網 | 「安裝後能離線」是 demo 條件 2（[demo-candidates.md](../../demo-candidates.md)） | 斷網後控制通道（exec）不能跟著斷 |
| 下指令、拿 stdout／stderr／exit code、讀寫檔案 | `Box` 介面（`pickfit/verify/box.py`） | 要有 exec 通道：guest agent、SSH 或自架 |
| 截圖 | 判讀用的「截圖」是 Pillow 把終端輸出重繪成圖（`screenshot.py`），不是螢幕截圖 | **不需要 GUI 截圖**，CLI 工具不受影響 |
| 沙盒裡沒有金鑰；不受信任的程式碰不到主機與區網 | plan 第 5 節、`DockerBox` 的限制 | box 使用者不能是管理員；要擋私有網段 |
| 誠實記錄 `os`、`arch`、`runner`、`image` | `VerificationRun`（`pickfit/schema.py`） | 記 guest 的 OS 版本，不是主機的 |

---

## 2. macOS

### 2.1 比較表

| 方案 | 費用 | 準備時間（估算） | 授權／條款 | 用完即丟 | 斷網重播 | 自動化 | 判斷 |
|---|---|---|---|---|---|---|---|
| **Tart（本機，Virtualization.framework）** | $0 | 安裝 5 分；下載 25 GB 約 20–60 分（看頻寬）；base image 準備＋`TartBox` 約半天 | Apple SLA 2B(iii)：每台 Mac 另 2 個 VM，限開發／開發中的測試／macOS Server／個人非商業；不得用於 service bureau、time-sharing [S1]。Tart：FSL-1.1-ALv2，除「Competing Use」外都可用，2 年後轉 Apache 2.0 [S4] | 是：`tart clone`（APFS CoW）→ 跑 → `tart delete` [S5] | 做得到：`tart exec` 經 vsock [S6]；guest 內 `pfctl`（box 使用者非管理員）或 softnet 執行中改政策 [S6][S9] | `tart exec` 回 stdout、stderr、exit code（需 guest agent，Cirrus 的 base image 內建）[S6]；`--dir` 共用資料夾；無 GUI 截圖指令（我們也不需要） | **推薦** |
| Lume（trycua/cua） | $0 | 同上 | MIT [S10] | clone（沒寫是否 CoW）[S10] | 只有 NAT／bridged；控制走 SSH，**斷網就失聯** [S10] | `lume ssh`、HTTP API；預設開遙測 [S10] | 斷網重播做不到，不選 |
| UTM／Anka Develop／Orka Desktop | $0 | 中 | Anka Develop 免授權、一次 1 台 VM [S11] | 可 | UTM 的 exec 要 QEMU guest agent，Apple 虛擬化的 macOS guest 未驗證 | 弱 | 不選 |
| **GitHub Actions macOS**（`macos-15`／`macos-26`，M1 3 核、7 GB） | public repo 免費；private：$0.062／分，Free 方案每月 $12 額度 ≈ 190 分鐘（估算）[S12][S13] | 約半天到 1 天（見 3.1 的架構問題） | 條款灰色地帶（3.1） | 是：每個 job 新 VM [S14] | **不能整台斷網**（runner 要連 GitHub）[S14]；`pf` 只擋 box 使用者理論上可行，**未驗證** | REST／`gh`；passwordless sudo [S14] | macOS 的**備案** |
| AWS EC2 Mac | mac2（M1）$0.65／h，**24 小時起租** → $15.60；mac-m4 $1.23／h → $29.52（us-east-1）[S15][S16] | 開帳號＋開機 6–20 分 [S17] | Apple SLA 第 3 節：出租每次至少 24 小時 [S1] | 整台 Mac，自己做 VM | 可（VPC） | SSH、SSM | 要刷念誠的卡，不選 |
| Scaleway Mac mini | M1 €0.11／h，24 小時起 ≈ €2.64；關機也計費到刪除為止 [S18][S19] | 開帳號 | 同上 | 整台 | 可 | SSH | 最便宜的租用，但要開帳號＋卡；賽後擴量才考慮 |
| MacStadium | M2.S $109／月起，只有月租或年租，**沒有試用** [S20] | — | — | — | — | — | 不選 |
| 按分鐘計費的 CI：Codemagic（每月 500 分免費，並行 1）、Namespace（30 天免卡試用）、Blacksmith、WarpBuild、CircleCI（每月約 150 分 macOS） | $0 起 [S21]–[S23]、sandbox-compare.md 第 5 節 | 要開帳號 | 各家條款未驗證 | 是 | 未驗證 | 各家不同 | 不選（要開帳號） |

另外：Cirrus CI 已在 2026-06-01 停止服務（Cirrus Labs 加入 OpenAI），Tart 的 repo 也搬到 `openai/tart` [S2][S3]。

### 2.2 Tart 的限制與風險

- **主機是 macOS 27，官方文件沒寫支援。** 但 Tart issue #1394 的回報者用的正是這台的版本（macOS 27.0.1、26A434），`brew install openai/tools/tart` 成功；舊的 `cirruslabs/cli/tart` formula 會失敗 [S3]。（已確認：issue 原文；本機未實測）
- **同時最多 2 台 macOS VM**（Apple 的限制）[S10]。我們一次只開 1 台（agent 與重播是先後），批次並行最多 2。
- **Apple 的 VM 名額外洩 bug**：guest 關機或 `tart stop` 後，再開 VM 可能回 `VZErrorVirtualMachineLimitExceeded`，**只能重開主機**；回報在 macOS 26.5（2026-06／07），Apple 還不能重現（FB22967193）。macOS 27.0.1 是否修好不知道 [S24]。每次驗證都會建立、刪除 VM，正好會踩到。對策：並行 1；遇到這個錯誤就停批次、提示重開機，不要一直重試。（未驗證是否會在這台發生）
- **guest 版本**：建議用 `macos-tahoe-base`（macOS 26.6.2，模板 50 GB 磁碟、4 CPU、8 GB）[S8]，而不是和主機一樣的 27：11 月使用者多數還在 26 以前，而 27 guest 在 6–8 月曾安裝失敗（#1261，9 月回報可用）[S3]。`macos-golden-gate-base`（27）也有 [S7]。紀錄的 `image` 寫 guest 版本與 image digest。
- **base image 已裝 Homebrew**（base＝vanilla＋Homebrew）[S7]。這接近開發者的 Mac，但要在 prompt 與紀錄裡寫明「已預裝 Homebrew」。
- **磁碟**：image 約 25 GB 下載、約 33 GB 落地 [S8][S25]；clone 只佔變動量。這台剩 363 GB。**記憶體**：每台 4–8 GB，主機 24 GB，夠。
- **Intel Mac（x86_64）做不到**：Apple silicon 只能跑 arm64 的 macOS guest。要 x86_64 只能用 GitHub 的 `macos-15-intel`／`macos-26-intel` [S14] 或 EC2 mac1。

---

## 3. Windows

### 3.1 GitHub Actions 的條款與架構問題（macOS、Windows 都適用）

**條款原文**（Additional Products and Features，Actions 一節，2026-08-27 生效）[S26]：GitHub 主機上的 runner 不得用於「unrelated to the production, testing, deployment, or publication of the software project associated with the repository」的活動；同一節另有「You may only access and use GitHub Actions to develop and test your application(s)」；也禁止對伺服器造成「disproportionate」負擔。Acceptable Use 另禁「excessive automated bulk activity」[S27]。

**我的解讀**（不是法律意見）：在 pickfit 自己的 repo 裡，用 runner 測試 pickfit 的驗證管線、產生 pickfit 自己的資料，少量執行說得通；大量掃第三方軟體來建目錄就偏離了。這個 repo 是交件用的，被停權的代價很高，所以**只跑 demo 規模**，而且由念誠決定要不要冒這個險。sandbox-compare.md 第 5 節（10/28）也得到同樣結論。

**架構**：模型呼叫目前在 Mac 上，`Box` 只負責執行指令。runner 上有兩種接法：

| | A. 整個 `pickfit verify` 在 runner 上跑 | B. Mac 上的 agent 遠端控制 runner（推薦） |
|---|---|---|
| 做法 | `MODEL_API_KEY` 放 Actions secret；agent、重播分兩個 job（重播要新 VM），判讀回 Mac 做 | runner 上跑一個小的 exec server（Python 標準庫），經 Cloudflare quick tunnel（不用帳號）讓 Mac 連；每個 `start()` 觸發一個新 job＝新 VM |
| 金鑰 | **Meta key 進到跑陌生程式的機器**（box 使用者另開一般帳號可降低風險） | 金鑰留在 Mac；runner 上只有一次性的連線 token |
| 花費上限 | 共用帳本 `~/.pickfit/ledger.sqlite` 在 runner 上是空的，**上限要另外做** | 帳本與上限照舊 |
| 改動 | 要把 `verify_task` 拆成階段 | `verify_task` 不動，只多一個 Box |
| 風險 | 金鑰外洩 | quick tunnel 沒有 SLA（未驗證穩定度）；遠端操作 runner 也是條款的灰色地帶（類似 action-tmate） |

### 3.2 比較表

| 方案 | 費用 | 準備時間（估算） | 授權／條款 | 用完即丟 | 斷網重播 | 自動化 | 判斷 |
|---|---|---|---|---|---|---|---|
| **GitHub Actions** `windows-2025`（x64）、`windows-11-arm`（arm64） | public 免費；private $0.010／分（x64、arm64 同價），每月 $12 額度 ≈ 1,200 分 [S12][S13] | 約 1 天（架構 B） | Windows 授權由 GitHub 負責；Actions 條款見 3.1 | 是 | `Set-NetFirewallProfile -DefaultOutboundAction Block`＋放行 runner 與 tunnel 程式 [S28]；**job 能否活下來沒有官方說法，要實測**。GitHub 官方的出站限制功能已「not planned」[S29] | 管理員、UAC 關閉 [S14]；預裝 Chocolatey、Node 22、Python 3.12、pipx；**沒列 winget、Scoop、uv** [S30] | **推薦（有條件）** |
| Windows Sandbox | 隨 Windows Pro 附 | — | 要 Pro／Enterprise／Education 主機 [S31] | 是，關掉就清空 [S32] | `<Networking>Disable</Networking>` [S33] | `wsb exec` 只回 exit code，**拿不到輸出**（要寫到共用資料夾）[S34] | **這台 Mac 跑不了**：M 系列 Mac 上的 Windows VM 不支援巢狀虛擬化 [S35]。賽後在實體 Windows PC 上很適合 |
| Windows 11 on Arm＋UTM | UTM 免費 | ISO＋安裝＋OpenSSH 設定約 2–3 小時 | 見下方授權 | clone／snapshot [S36] | QEMU `restrict=on` 可斷外網、保留轉發的 SSH [S37]；UTM 設定是否支援未驗證 | ARM64 Windows **沒有官方 QEMU guest agent**（UTM #5134）[S38]，要改走 Windows 內建 OpenSSH [S39] | 只有 ARM64；賽後 |
| Windows 11 on Arm＋Parallels Desktop | Pro 試用 14 天（到約 11/12），之後 $119.99／年 [S40][S41] | 1–2 小時 | Microsoft 唯一點名授權的方案（Parallels 18–20；頁面只列 M1–M3）[S35] | `prlctl` clone／snapshot（Pro）[S42] | Host-Only 網路（Pro）[S42] | `prlctl exec` 要 Parallels Tools；是否回傳 stdout／exit code 未驗證 [S43] | 試用期過了要付錢；賽後 |
| VMware Fusion | 免費 [S44] | 中 | 同上 | clone 標 Pro only [S45] | 可 | `vmrun` 不回 stdout（未驗證） | 不選 |
| Azure Windows VM | B2s $0.0664／h（East Asia），按整分鐘計 [S46]；新帳號 $200／30 天，要手機與信用卡 [S47] | 開帳號＋設定約半天 | Windows 11 要 E3／E5，試用帳號可用於 dev／test [S48] | image／snapshot | NSG 擋出站；但 Run Command 要連 Azure，輸出只回最後 4,096 bytes [S49] → 改用 SSH | 好 | 要開帳號＋卡；賽後 |
| AWS EC2 Windows | t3.medium $0.060／h（us-east-1），每秒計、最少 60 秒 [S50][S51] | 同上 | **只有 Windows Server 授權內含**；Windows 11 要自帶授權＋專屬主機 [S52] | AMI／snapshot | 無網際網路的 VPC＋SSM PrivateLink [S53] | SSM Run Command | Server ≠ Windows 11，要另外標；賽後 |
| dockur/windows（Linux＋KVM 裡的 Windows） | 程式 MIT [S54] | 第一次安裝 15–30 分（未驗證） | **不附授權**，要自己的 Windows 授權 [S54] | 是 | 可（Docker 網路） | 共用資料夾、`/oem` 腳本 | OrbStack 在 Apple silicon 不支援巢狀 KVM [S55]；Modal 的巢狀虛擬化只限 Enterprise [S56]。賽後可在 GitHub 的 Ubuntu runner（有 KVM）[S57] 或支援巢狀虛擬化的雲端 VM 上跑 |
| AppVeyor／CircleCI／Azure Pipelines | 有免費額度 [S58]–[S60] | 要開帳號 | 各家條款未驗證 | 是 | 未驗證 | — | 不選 |

**Windows 授權**：Windows 授權條款第 5 節要求「properly licensed and ... properly activated」才能使用，每個（虛擬）裝置一份授權 [S61]，所以沒啟用的 VM 和 dockur 內附的通用金鑰都**不算合法授權**。免費又合法的是 **Windows 11 Enterprise 26H2 的 90 天評估版**（有 x64 與 Arm64 ISO，要註冊、要登入 Microsoft 帳號，過期後每小時關機）[S62]；評估版 EULA 的用途限制未驗證。以前的 Windows Dev Environment VM 已停供 [S63]。

**ARM64 與 x64**：這台 Mac 上能跑的只有 ARM64 Windows。Prism 能模擬 x64 的使用者模式程式，不能跑驅動程式 [S64]；安裝程式也可能挑 arm64 版。要給「Windows x64」的紀錄，只能用 GitHub 的 `windows-2025`、Azure 或 AWS。

---

## 4. 不用 VM 的較弱證據

### 4.1 來源

| 來源 | 怎麼查 | 證明什麼 | 不證明什麼 | 授權／條款 |
|---|---|---|---|---|
| GitHub Release 資產 | `GET /repos/{o}/{r}/releases`（`/latest` 遇到只有 prerelease 會 404，例如 cluaiz）；看資產名稱；2025-06 起有 `digest`（舊資產是 null）[S65][S66] | 有發佈某 OS／arch 的檔案 | 能不能跑；`content_type` 是上傳者填的，不可靠 | GitHub AUP 第 7 節：可用公開、非個人資料 [S67] |
| GitHub 簽章（attestation） | `GET /repos/{o}/{r}/attestations/{digest}`；沒做過簽章的 repo 回 404 [S68] | 檔案由哪個 repo、workflow、commit 建出來 | 在哪個 OS 建、能不能跑（官方：不保證安全）[S68] | 同上 |
| 上游 CI | `GET .../actions/workflows/{file}/runs?branch=<預設分支>&status=completed` → jobs 的 `labels`、`conclusion`；label 對照 OS／arch [S14] | 專案自己的 CI 在該 OS 的 runner 跑過且成功 | job 實際測了什麼（可能只有 lint） | 同上 |
| Homebrew（core） | `formulae.brew.sh/api/formula/<name>.json` 的 `bottle.stable.files`（`arm64_tahoe`、`arm64_sequoia`…）[S69] | BrewTestBot 在該 OS／arch 建出 bottle，formula 有 `test do` 就跑 `brew test`，失敗的不發佈 [S70][S71] | 測試常常只有 `--version` | BSD-2-Clause；API 沒寫資料授權 |
| Homebrew cask | `depends_on.macos`、`depends_on.arch`；CI 只做 audit、install、uninstall，不啟動 app [S72] | 能裝 | 能跑 | 同上 |
| 第三方 tap | 讀 `homebrew-<tap>/Formula/<name>.rb`：有沒有 `bottle do`、是不是 `on_macos { on_arm { url … } }` 包官方檔 | 很弱：多半沒有 CI | — | 看 tap |
| winget | `microsoft/winget-pkgs` 的 `manifests/<字首>/<Publisher>/<Name>/<版本>/*.installer.yaml`：`Architecture`、`InstallerType`、`InstallerSha256` [S73]；code search 沒索引這個 repo，改用 issue search 找 PR | 驗證管線查 schema、網址、雜湊、防毒，並有安裝／解除安裝測試（`Validation-Completed`）[S74] | 文件沒說 arm64 安裝檔有實際安裝（推論：只查網址與雜湊） | MIT |
| Scoop | `ScoopInstaller/{Main,Extras}/bucket/<name>.json` 的 `architecture.{64bit,arm64}` | 網址與雜湊對得上 | **CI 的安裝測試被註解掉** [S75] | Unlicense |
| npm | registry 的 `os`、`cpu`、平台專用 `optionalDependencies`、`dist.attestations` [S76] | 宣告支援或有發佈平台檔 | 能不能跑 | 公開 API，禁「unreasonable volume」[S77] |
| PyPI | `pypi.org/pypi/<name>/json` 的 wheel 標籤（`macosx_11_0_arm64`、`win_amd64`、`py3-none-any`）[S78][S79] | 有平台 wheel；純 Python 只代表「沒限制」 | 能不能跑 | PyPI ToS [S80] |
| conda-forge | `api.anaconda.org/package/conda-forge/<name>` 的 subdir | osx-64、win-64 原生建置並測試；**osx-arm64、win-arm64 是交叉編譯、沒測** [S81] | — | BSD-3-Clause |

### 4.2 建議的等級（強到弱）

1. `ran_on_os`：我們自己在該 OS 跑過 smoke test（＝`VerificationRun`，`method: sandbox` 或 `human`）。**以下全部比它弱。**
2. `upstream_ci_passed`：專案自己的 CI 在對得上 OS／arch 的 runner、預設分支上成功。記 run 網址、`head_sha`、是否就是 release 的 commit。
3. `package_tested_by_ci`：第三方套件管線在該 OS 裝起來並跑過檢查（homebrew-core bottle＋`test do`、conda-forge 原生 subdir、winget `Validation-Completed`）。
4. `package_built_by_ci`：有建置、沒有測試（沒有 `test do` 的 bottle、conda-forge 的 arm64、cask）。
5. `artifact_published`：只有該 OS／arch 的檔案（release 資產、npm 平台套件、wheel 標籤、Scoop、tap、winget arm64）。有簽章時加註 `provenance_attested`（只證明誰建的）。
6. `declared_only`／`declared_unsupported`：純語言套件沒有平台限制，或 `os` 明確排除（orbit 在 Windows）。

每筆證據都要記**適用的版本**與查證時間：shep 的 winget 是 0.1.25、tap 是 0.1.26，現行是 0.19.0。這些不該進 `VerificationRun`（它的意思是「跑過」），建議另開 `platform_evidence` 欄位；MCP 回應的 `how_we_know` 要寫清楚是哪一級。

### 4.3 10 筆 demo 候選（2026-10-29 查，沒有下載、沒有執行）

| slug | macOS arm64 | Windows |
|---|---|---|
| orbit | release `orbit-aarch64-apple-darwin.tar.gz`；npm `os: [darwin, linux]`，postinstall 下載執行檔 | **不支援**（npm `os` 排除 win32、沒有 Windows 檔） |
| mcp-audit | PyPI 只有 `py3-none-any`（有 PEP 740 簽章）；release 有 `mcp-audit-darwin-arm64`；上游 CI 在 `macos-latest` 成功 | `mcp-audit-windows-x86_64.exe`；CI 在 `windows-latest` 成功 |
| patient-zero | 純 JS；上游 CI 在 `macos-latest`×Node 18／20／22 成功（2026-05-17 的 commit） | CI 在 `windows-latest` 成功 |
| shep | release `shep-aarch64-apple-darwin.tar.gz`（有簽章）；**tap 沒有 bottle，用 cargo 從原始碼編，停在 0.1.26** | release `x86_64-pc-windows-msvc.zip`（有簽章）；winget 0.1.25（x64，`Validation-Completed`） |
| mi-lsp | `mi-lsp_0.16.6_darwin-arm64.tar.gz`（沒有 CI、沒有簽章） | `win-x64.zip`、`win-arm64.zip` |
| phantom | npm 是純 JS（Node ≥22.15，有 provenance）；release 有桌面 app `Phantom_3.29.15_aarch64.app.tar.gz`；最新 CI 失敗 | 沒有 Windows 檔；CI 結果不一 |
| rimz | `rimz-aarch64-apple-darwin.tar.gz`；**在 ubuntu-latest 交叉編譯，CI 從沒在 macOS 執行過** | 沒有 |
| corvus | `corvus-osx-arm64.tar.gz`（有簽章）；CI 的一個 `macos-latest` job 失敗 | `win-x64.zip`、`win-arm64.zip`（有簽章）；`windows-latest` 成功 |
| apexo-code | npm 平台套件 `apexo-code-darwin-arm64`（168 MB）；`macos-15` 建置成功 | `-windows-x64`、`-windows-arm64`；建置 job 成功，但整個 run 是 failure |
| cluaiz | prerelease `cluaiz-0.1.0-mac-arm64.tar.gz`；`macos-14` 建置成功 | `win-x64.zip`＋7 個 GPU 版，沒有 arm64；`windows-2022` 成功 |

---

## 5. 建議的實作（念誠點頭後的 Phase 2）

### 5.1 `TartBox`（macOS）

- **一次性準備**（腳本化，進 repo）：`tart pull ghcr.io/cirruslabs/macos-tahoe-base:<tag>` → clone 成 `pickfit-macos-base` → 用 `tart exec`（admin）建一般使用者 `sbx`（不是管理員、沒有 sudo），把 Homebrew prefix 交給 `sbx`，讓它能 `brew install` 卻改不了防火牆；放一支 perl 寫的 timeout／process group 小工具（macOS 沒有 `timeout`、`setsid`）。
- **每次驗證**：`tart clone pickfit-macos-base pf-verify-<hex>` → `tart run --no-graphics` 背景執行 → 等 guest agent → 指令一律 `tart exec <vm> sudo -u sbx -H env -i <BOX_ENV> /bin/bash -c …` → `close()` 時 `tart stop` ＋ `tart delete`。
- **網路**：開機時 guest 內 `pf` 擋私有網段與主機（只放行 gateway 的 DNS），避免陌生程式碰到念誠的區網與 Mac 上的服務；`set_network(False)` 改成擋全部出站、保留 `lo0`。控制走 vsock，不受影響。`--limits-test` 要多驗：`sbx` 沒有 sudo、改不了 `pf`、連不到區網、斷網後 loopback 服務還在。softnet 是備案（要一次 sudo 設 SUID）。
- **共用程式的修改**：`Box` 加 `describe()` 讓 prompt 不再寫死「Debian-based Linux」；`background_script` 改掉 `setsid`；`plan_for(..., "macos")` 讓 brew 排第一；規則表加 macOS 版（`xcode-select`、Gatekeeper、Homebrew）；`pickfit verify --runner tart`；批次並行上限 1（最多 2）。
- **紀錄**：`os: macos`、`arch: arm64`、`runner: tart-vz`（Apple Virtualization.framework，主機 M5）、`image` 寫 guest 版本與 digest；`replayed`、`offline` 照實；斷網做不到時寫「沒有斷網重播」。寫回時填 `install.macos`（`write_back` 已經依 `run.os` 分開）。
- **測試**：單元測試用假的 `tart` 執行檔（記錄參數），不開真 VM。
- **順序**：先 1 筆（建議 `mcp-audit`：`uv tool install`，最單純），再 5 筆（mcp-audit、patient-zero、orbit、mi-lsp、rimz）。花費：box $0，Meta 每筆約 $0.05–0.08（Modal 批次的中位數）→ 5 筆約 $0.5，在 $3 上限內。

### 5.2 `GitHubRunnerBox`（Windows，選做）

架構 B：一個 `workflow_dispatch` workflow（輸入 `os`、一次性 token），job 內建一般使用者、起 exec server 與 quick tunnel，把網址寫進 job log；Mac 用 `gh run view --log` 讀網址後開始下指令；`close()` 時通知 server 結束、`gh run cancel`。Windows 的指令用 PowerShell 7（`Box` 加 `shell` 屬性，prompt 與重播跟著換）。先實測防火牆擋出站後 job 與 tunnel 是否還活著。

### 5.3 時程（估算）

| 日期（台北） | 做什麼 |
|---|---|
| 10/29 下午–晚上 | 念誠點頭 → 裝 Tart、下載 image（背景）；寫 `TartBox`＋單元測試 |
| 10/30 | base image 準備、`--limits-test`、1 筆 → 5 筆 |
| 10/31 | （選做）Windows `GitHubRunnerBox`：防火牆實測 → 1 筆 → 5 筆 |
| 11/1 | （選做）`platform_evidence` 跑全部 96 筆 |
| 11/2 | 功能凍結 |

### 5.4 實測（2026-10-29 16:20–19:50 台北）

念誠 10/29 選 Tart。實作在 `pickfit/verify/tart_box.py`（`pickfit verify --runner tart`；`--prepare-base` 建 base VM）。

**環境**：Tart 2.41.1（`openai/tools` tap）；image `ghcr.io/cirruslabs/macos-tahoe-base@sha256:4aaa751fa753…`（macOS 26.6.2，25G83），壓縮 26.4 GB，家裡網路約 2.5–4 MB/s，下載約 2 小時 50 分，落地 30 GB。base VM `pickfit-macos-26` 準備約 150 秒：一般使用者 `sbx`（UID 1001，非 admin、沒有 sudo，擁有 `/opt/homebrew`），Homebrew 7.0.11、uv 0.13.6、pipx 1.18.6、node v26.13.0、CLT 的 Python 3.9.6；版本記在 `~/.pickfit/tart/pickfit-macos-26.json`。每台 box（clone＋開機＋檢查＋防火牆）約 20–30 秒，同時只開 1 台。

**安全審查（10/29 18:50）後的加固**：獨立審查確認 box 使用者能變成 root：image 的 `admin`/`admin` 帳號有 NOPASSWD sudo，`sbx` 能用 pty 跑 `su admin`、或 `ssh admin@127.0.0.1`（pf 跳過 lo0），再 `sudo pfctl -d` 關掉防火牆，而重播照樣記 `offline: true`。實測屬實：`sbx` 執行 `dscl . -authonly admin admin` 成功，sshd（22）與螢幕共享（5900）都在聽，`/etc/kcpassword` 人人可讀。修補時另外發現：guest agent 的 LaunchDaemon（root）與 LaunchAgent 都從 `sbx` 擁有的 `/opt/homebrew/bin` 啟動。現在：

- `--prepare-base` 在 guest 裡產生 admin 的隨機密碼（不進 repo、不印出；guest agent 會把每條指令寫進人人可讀的 log，所以密碼不出現在任何指令列），改寫 `/etc/kcpassword`（只有 root 可讀）讓自動登入照常啟動 agent；關掉 Remote Login 與螢幕共享；`/etc/pam.d/su` 只准 root；agent 改從 root 擁有的 `/usr/local/libexec/pickfit-agent/` 啟動。加固後重開一次 base（證明自動登入與 agent 正常）並跑完整檢查才寫 manifest；建置失敗就刪掉 base 與舊 manifest。
- 每台 box 在跑任何 model 指令前以 root 檢查上面每一項，不合格就拒用。
- pf 規則加 label；每次切換網路後檢查 pf 啟用且載入的是 pickfit 的那一組；斷網時以 root 實際連 1.1.1.1 必須失敗；恢復網路前再確認斷網一直有效。任何一項不成立就是 box error，不會記成 offline。
- VM 壽命：guest 自己排 `shutdown -h +N`，host 另有獨立 session 的 reaper 在壽命＋5 分鐘後停掉並刪除 clone；`close()` 不會丟例外，刪不掉就留給 reaper。DHCP 規則只放行到 gateway 與廣播。
- 防火牆政策仍在 guest 裡。改到 host 端（Tart softnet：`--net-softnet-allow/-block`，執行中用 `--net-softnet-control-fd` 換政策）可行，guest 的 root 也改不了；但 softnet 要 setuid root，需要念誠在這台 Mac 上親自執行一次 `sudo`，所以這次沒做。

**`--limits-test` 18／18**（加固後的 base）：不是 root、不在 admin、sudo 被拒；`sbx` 關不掉 pf；admin 的預設密碼失效（`dscl -authonly` 失敗）；pty 裡 `su admin` 輸入預設密碼得到 `su: Sorry`；localhost 的 22 與 5900 沒人聽；`/etc/kcpassword` 讀不到；換不掉 agent 的執行檔與 launchd plist；環境變數沒有金鑰；169.254.169.254、10.0.0.1、主機（VM 的 gateway）都連不到（逾時）；斷網後 PyPI 不通、loopback 服務照常；恢復後再通；指令 3 秒被殺；1.7 GB 檔案被擋；fork 在 248 個行程停下。macOS 沒有單一行程的記憶體上限，VM 的 8 GB 就是上限，所以沒測 `memory_cap`。

**實機才發現、已修正的事**：guest agent 以 `admin` 執行而 PATH 沒有 `/sbin`；vmnet 先給一個 IPv6 link-local DNS，擋住 IPv6 後每次查詢多等 3 秒，改成把 DNS 固定為 IPv4 gateway（3–34 ms）；macOS 的 `nohup` 在沒有 console 的 session 裡直接結束，改用自己的 detach helper；`/usr/bin/python3` 是 xcrun shim，會塞 `SDKROOT`、`CPATH` 等變數，改呼叫 CLT 的 python 本體；開機早期 `tart exec` 會卡住；admin 有 Secure Token，連 root 改密碼都要給舊密碼。**`run_background` 在 macOS 一律 exit 124**：背景腳本寫成 `a && b &`，bash 3.2 會留一個握著 stdout 的 subshell，指令永遠不回來（bash 5 直接 exec，所以 Linux 沒事）；改成只把一個指令丟到背景後，1.4 秒回來、exit 0。之前把 orbit、cluaiz 只到 function 歸因於「agent 宣稱 service、指令紀錄撐不起」是錯的，真正原因是這個 bug。

**6 筆 demo 候選，在加固後的 base 上用合併 main（ee303ed）的程式重跑，全部通過並在全新 VM 重播**（`muse-spark-1.3`）：

| slug | macOS 等級（Linux） | 安裝 | 斷網 smoke test | 秒 | Meta |
|---|---|---|---|---|---|
| mcp-audit | function（function） | `uv tool install mcp-audit-scanner` | 是 | 108 | $0.043 |
| patient-zero | function（function） | `npx -y patient-zero@latest`（沒有全域安裝） | **否**：步驟與 smoke test 都走 `npx`，每次都要連 npm registry | 278 | $0.028 |
| orbit | **service**（service） | `npm install -g @orbit-tools/cli` | 是 | 122 | $0.042 |
| mi-lsp | function（function） | 官方 `install.sh`（agent 讀完整份 `install.sh`，但 `install.sh` 用 node 執行的 `validate-worker-manifest.js` 只下載、沒讀） | 是 | 750 | $0.118 |
| shep | function（function） | `brew install shep-pm/shep/shep` | 是 | 968 | $0.054 |
| cluaiz | **service**（service） | 官方 `install.sh`（先下載、讀過再跑） | 是 | 201 | $0.140 |

- 6 筆的 `install.macos` 都是重播過的步驟（`basis: replayed`），索引裡這 6 筆的 `verified_on_user_os`（macOS）是 true；96 筆中原本是 0。**但 Worker 判斷時沒看 CPU 架構**（`worker/src/find.ts:120`、`worker/src/cards.ts:67` 只看 `entry.install[os]` 在不在），6 筆都只跑過 arm64，Intel Mac 使用者也會看到 true；索引已帶 `install.macos.run.arch`，修法是使用者給了 arch 時要求相符。這屬於 Worker，交給協調的 session。
- **shep 在 Mac 上照 brew 裝到的是 0.1.26**：tap 過期（release 是 0.18.2，10/29 出了 0.19.0），而且從原始碼編：brew 先裝 llvm 23.1.4（1.9 GB）與 rust 1.99.1（407 MB），cargo 再編約 4 分鐘。Linux 的紀錄是 0.18.2。agent 沒寫 pitfall，我依這次 run 的輸出與 release 清單手動補了一條 `readme_wrong` pitfall。shep 的品質分數從 75.2 變成 90.2（macOS run 只有 1 步、沒有計分程式認得的 README 修正，sandbox 0.7→1.0）；照過期 tap 裝的 run 該不該加分，由計分的 session 決定。
- 這個 task 的 Meta 花費約 $1.56（合併前一輪 $0.50 沒寫回；合併後重跑 $0.63 被加固前的結果取代；加固後重跑 $0.42），在 $3 上限內；box 費用 $0。

### 5.5 安全審查後改用 host 端防火牆（softnet，2026-10-29 晚）

兩輪對抗審查指出：box 使用者（`sbx`）能變成 root。`tart exec` 由 **admin 的 Aqua 登入 session** 裡的 guest agent 服務（實測：拔掉那個 agent，exec 直接卡住，所以沒辦法把 exec 換到 root daemon），admin 有 NOPASSWD sudo，所以 guest 內的不受信任程式可以經由共用的 session 取得 admin→root，再關掉 **guest 內的** pf，而重播仍記成 `offline`。

**修法：把網路政策搬到 host（Tart 的 softnet），guest 的 root 也改不了。**

- 每台 VM 以 `tart run --net-softnet --net-softnet-control-fd=N` 開機；harness 經那個 fd 用 JSON-RPC 下 `softnet.policy.set`。**（第一版寫成 online＝allow/block 皆空，以為預設就擋 host；錯了，見 5.6：softnet 預設放行 vmnet gateway＝本機。已改成 online＝`block ["@host"]`。）** offline＝`block 0.0.0.0/0`。softnet 換政策時清空 flow table，已建立的連線會斷，所以斷網前開的連線撐不過切換。
- 每次切換後，harness **以 guest 內的 root** 確認：online 時連得到公網、連不到 host／metadata／私有位址；offline 時連公網也失敗。這條驗證因此不再依賴任何 guest 內 root 改得動的東西。
- softnet 要一次性 setuid-root（它建好網路介面後會把權限降回呼叫者）：念誠 10/29 設好（`-r-sr-xr-x root:wheel`）。沒設好時 box 會拒絕開機並印出設定指令。
- 拿掉 guest pf；`--limits-test` 的 `firewall_locked`（sbx 關不掉 pf）移除，保留逃逸面探針（admin 密碼、su、遠端登入、agent 執行檔）當縱深防禦。**`--limits-test` 在 softnet base 上 17／17**（含 host／metadata／私有位址以 root 仍不可達、斷網以 root 仍不可達）。

**順手修掉的其他審查項**：

- `masked_exit` 的 bug（跨平台）：分隔符後的 `&&`／`||` 串接原本看第一個指令，於是把 `cat X && shep start Y` 誤判成「被 cat 遮住」，害重播漏跑 shep 的 start 步驟、flock 檢查跑在錯的狀態上。改成看最後一個 pipeline 的最後一個指令，加了回歸測試。
- 把手動加進 shep run 的 pitfall 撤掉（審查指出不該把人寫的註記混進 agent 的 run，且計分的 `readme_fix()` 把它當成 box pitfall）。stale-tap 的事實改由重驗自然產生，不手改紀錄。
- base build 再加固（這次重建已套用）：在 `sbx` 跑 brew **之前** 就把 guest agent 執行檔釘到 root 擁有的目錄；agent／daemon 的啟動 PATH 拿掉 `sbx` 擁有的 `/opt/homebrew/bin`；`describe()` 不再說「no GUI session」（改說 headless）。

**在 softnet base 上重跑 6 筆（`muse-spark-1.3`，全部通過並重播、judge working）：**

| slug | macOS 等級 | 斷網 smoke test | 秒 | Meta |
|---|---|---|---|---|
| mcp-audit | function | 是 | 152 | $0.035 |
| patient-zero | function | 否（`npx` 每次連 registry） | 422 | $0.055 |
| orbit | service | 是 | 197 | $0.072 |
| mi-lsp | function | 是 | 1003 | $0.126 |
| shep | function | 是 | 1009 | $0.060 |
| cluaiz | service | 是 | 259 | $0.187 |

- 6 筆的 `install.macos` 都是重播過的步驟，索引裡 `verified_on_user_os`（macOS）為 true（96 筆中這 6 筆）。
- 審查點名的紀錄問題這輪都消失：shep 不再有壞掉的 `shep flock` smoke test；cluaiz 的離線 `first_task` 現在把測試模型（stories260K，1.2 MB）當成線上 setup 先抓；orbit 這輪沒把 `doctor` 當 smoke test（只留一條 note）。**仍在的小項**：mi-lsp 這輪完整讀了 `install.sh`，但 `install.sh` 用 node 跑的 `validate-worker-manifest.js` 只下載沒讀（比上輪好但沒全好）；這是共用 agent 提示的調整，交給驗證 agent 的 session。
- 計分變動（公式 b3.v4 自動算，非手改）：shep 品質 75.2→90.2、cluaiz 74.7→81.5，因為 macOS 的安裝路徑比 Linux 乾淨（步驟少、無計分認得的 README 修正）。「用過期 tap 從原始碼編的乾淨 brew 步驟該不該給滿分」是計分 session 的事，已轉達。
- 這一輪（softnet 重跑）Meta 約 $0.54；本 task 累計約 $2.1，在 $3 上限內；box $0。
- **arch 未解**：softnet 之後 `verified_on_user_os` 仍只看 OS、不看 arch（這 6 筆都只跑 arm64），Intel Mac 使用者會誤看成 true；修法在 Worker（`worker/src/find.ts`、`cards.ts`），已轉達。

---

### 5.6 第三輪審查：softnet 預設其實放行 host，探針被我放鬆（2026-10-29 深夜～10-30）

第三輪對抗審查抓到兩件事，都成立：

1. **softnet 的預設政策放行 vmnet gateway，而那就是本機。** README 明寫預設允許「send traffic to gateway IP of the vmnet bridge」。我原本的 online 政策是 `block=[]`（以為預設擋 host），所以**安裝階段** guest 能連到本機服務。實測：預設政策下，guest（root）連本機 `:3000`／`:5000`／`:7000` 得到 HTTP 回應（exit 0）。這台的應用防火牆是關的。
2. **探針被我放鬆到不會失敗。** 我在 ae014c8 把 `host_blocked` 從「必須逾時（被丟棄）」改成「exit 非 0 即可」——但 exit 7 是「封包到了本機、被拒」，等於沒擋住。那次（215257）就是這樣「通過」的。**不該為了讓探針變綠就放寬它；探針失敗時該修的是政策。**

**先實測再改**（在 clone 上，非驗證跑）：預設政策 → 本機 3000/5000/7000 可連（0）；改 `block=["@host"]`＋DNS 指到 1.1.1.1 → 每個本機埠都逾時丟棄（28）、PyPI 仍 200、metadata／private 丟棄；offline（`block 0.0.0.0/0`）→ 全丟棄。softnet 丟封包是**靜默丟棄**，所以「被擋」＝curl exit 28，「到了本機被拒」＝exit 7。

**修正**（commit 2406517、8f4f43e）：

- online 政策改成 `block=["@host"]`（offline 不變）。gateway 既然被擋就不能當 DNS，guest 改用公用 resolver（1.1.1.1、1.0.0.1）。
- `_check_firewall` 變嚴格、fail-closed、以 root 執行：本機數個埠與一個 private 位址**必須靜默丟棄（exit 28）**，exit 7（到了本機）算失敗；metadata（link-local）與 IPv6 只要**連不到**（非 0 即可，本來就沒路由，curl 直接 exit 7）；公網只有 online 可連、offline 必須丟棄；查不到 gateway 或任何一項跑不出結果就失敗。
- `--limits-test` 把網路探針**以 root 執行並記錄**，而且加了**正對照**：先放行 @host、找出一個真的會回應的本機埠（證明探針抓得到「連得到」），再擋 @host、確認同一埠變成丟棄（證明政策真的生效）。offline 另外檢查 host、resolver、IPv6。
- 每個 run 記錄 base 的 build id（manifest `build_id` → `image`），所以一筆 run 指得出它用的是哪一次 base。
- 文件／docstring 更正（不再說「預設擋 host」、不再提 guest pf）。

**`--limits-test` 在新 base（build `c7b08f9f7074`）上 26／26**，正對照顯示 @host 放行時本機 5000／7000／3000 可連、擋了之後全部 28。

**6 筆在這個新 base（同一個 build）重跑，全部通過並重播、judge working**（`muse-spark-1.3`；mi-lsp 第一次開機 guest agent 240 秒沒回應，重跑成功；cluaiz 第一次只到 function，重跑回到 service）：

| slug | macOS 等級 | 斷網 smoke test | 秒 | Meta |
|---|---|---|---|---|
| mcp-audit | function | 是 | 163 | $0.044 |
| patient-zero | function | 否（`npx` 每次連 registry） | 384 | $0.044 |
| orbit | service | 是 | 411 | $0.063 |
| mi-lsp | function | 是 | 992 | $0.104 |
| shep | function | 是 | 1146 | $0.077 |
| cluaiz | service | 是 | 354 | $0.158 |

- 6 筆的 `install.macos` 都是重播過的步驟、base build 都是 `c7b08f9f7074`；索引裡 `verified_on_user_os`（macOS）為 true。
- 計分（b3.v4 自動）：這一輪 shep 落在 76.4（Linux 75.2，之前那次偶然的 90.2 沒再出現）、cluaiz 81.5（service）。
- 這一輪 Meta 約 $0.66（第一批＋mi-lsp/cluaiz 重跑）；本 task 累計約 $2.8，接近 $3 上限，之後非必要不再重跑。
- **仍未解、已轉達**（同 5.5 結尾）：Worker 的 `verified_on_user_os` 不看 arch（6 筆都 arm64）；mi-lsp 的 `install.sh` 用 node 跑的 validator 只下載沒讀。

---

### 5.7 第四輪審查：擋掉 IPv4 multicast（2026-10-30）

第四輪確認 @host 修正與嚴格探針成立、6 筆紀錄與 artifact 一致、base build id 對得上。還剩一個 medium：**softnet 把 224.0.0.0/4（multicast）與 255.255.255.255 當成 globally routable**，所以 online（`block ["@host"]`）時 guest 仍能打到本機的 mDNSResponder／SSDP，讀到這台的 `.local` 名稱與 Bonjour 服務。實測重現：guest 對 224.0.0.251:5353 送 mDNS 查詢，本機回了 124 bytes。

**修正**（commit 30e7091）：

- online block 改成 `["@host", "224.0.0.0/4", "255.255.255.255/32"]`。guest 自己的 private /29（含其 directed broadcast）本來就被 softnet 預設擋掉（private 不是 routable）。clone 實測：加了之後 mDNS 不再有回應、PyPI 仍 200、網路與 DHCP 照常。
- `_check_firewall`（online）與 limits 的正對照都加了 mDNS 探針（多播查詢 → online 必須無回應；放行時有回應）。**`--limits-test` 27／27**。
- docstring 更正：政策只過濾 **egress**；softnet 這個模式不過濾 host→guest 的封包，所以本機的主動廣播仍可能被動到達 guest（列為已知限制，但 guest 無法藉此抓取或外送，不影響離線驗證）。另外 metadata／IPv6 的「連不到」只證明 guest 沒有路由、不證明 softnet 在過濾；真正證明政策生效的是 host 埠與 mDNS 的正對照。

**沒有重跑 6 筆**：multicast 這個洞是**安裝階段**對本機的資訊洩漏，不改變任何工具的安裝結果，而離線階段（`block 0.0.0.0/0`）本來就把 multicast 一起擋了，所以 6 筆紀錄（base build `c7b08f9f7074`）仍成立。Meta 已近 $3 上限，這一輪只跑 limits test（不花 Meta）。

**已知限制／未解**（記錄，非這次要修）：

- softnet legacy 模式只過濾 egress，不過濾入站；本機未經請求的廣播可被動到達 guest。要連入站都擋，得看 softnet 是否有 flow-table 模式；目前當已知限制記著。
- NAT hairpin：家用路由器可能可經自己的公網 WAN 位址被打到（繞一圈）。這要先找出 WAN 位址才能擋，成本高，記為已知限制。
- 第三輪結尾列的兩項已在別處修掉：Worker 的 `verified_on_user_os` 已看 arch（併入 c199445）；「讀過 installer 會執行的腳本」的提示規則在 P3 分支上。

### 5.8 Windows：VirtualBox box（`VBoxBox`，2026-10-30～31）

GitHub Actions 沒有採用。改在念誠的 Windows 11 Home 筆電（i5-1135G7，4 核 8 緒，16 GB）上用 VirtualBox 7.2.22。guest 是 Windows 11 Enterprise LTSC 2024 評估版（26100.1742，x86_64，90 天，線上啟用）。另有一台 Alpine router VM 當出口（規則與 5.5 節相同精神：所有私有、保留、multicast 範圍都丟掉，只放行 DHCP／DNS 到 router）。

**安裝的實測**：

- Hyper-V 開著時，VirtualBox 只能走 NEM（Hyper-V 的 API），非常慢，而且多 vCPU 會凍住。6 vCPU 時，韌體卡在 PciHostBridgeDxe；4 vCPU 時，安裝第一階段與 OOBE 各凍住過一次（vCPU0 的 TSC 跟其他顆差約 35,000 秒）；1 vCPU 才裝得完。念誠關掉 Hyper-V 與 Memory Integrity 後改走 VT-x：2 vCPU 開機正常，啟用、winget、工具安裝 12 分鐘完成。
- LTSC 沒有 Store，所以 winget 由 pickfit 從 github.com/microsoft/winget-cli 的 v1.29.380 release 裝（檔名、大小、SHA-256 記在 manifest）。

**為什麼 sbx 要自動登入（2026-10-31，跟 macOS 對照）**：

- winget 和 PowerShell 7（winget 現在只發 MSIX 版）都是 MSIX 套件。Windows 只在使用者「互動登入」時註冊這類套件（guestcontrol 的工作階段部署會失敗：0x80073D19），而且使用者沒有桌面工作階段時根本啟動不了（"The specified user does not have a valid profile"）。所以受測使用者 `sbx` 在每個 box 都要登入桌面，就像一般使用者的電腦。
- 原本的探測是「不准自動登入」，目的是受測工具（以 `sbx` 執行）拿不到能提權或冒用帳號的憑證。協調 session 同意改成一樣嚴的版本：
  - 自動登入只限 `sbx`。
  - Winlogon（HKLM 與 HKCU）不能有 DefaultPassword。
  - 密碼存成 LSA secret `DefaultPassword`。Winlogon 在登錄檔沒有密碼時讀這裡，標準使用者在 LsaOpenPolicy 就被拒。
  - 不留任何 answer file：查 Panther、Panther\Unattend、Sysprep、各磁碟根目錄、`C:\vboxpostinstall.log`。
  - 沒有光碟：安裝 ISO 與帶 Administrator 密碼的 aux ISO 在拍快照前拔掉。
  - Administrator 的自動登入只在建置時用（裝 winget 需要它），HARDEN 會移除。
- 這跟 macOS 一致：macOS box 也讓 `sbx` 自動登入（guest agent 要靠它啟動），密碼放在只有 root 能讀的 `/etc/kcpassword`，limits 檢查 `kcpassword_unreadable`。Windows 的對應探測是 `no_logon_secret`：`sbx` 讀 LSA secret 要得到 `denied`。
- 每次建 base 都隨機產生密碼。密碼只用 guestcontrol 的 `--putenv` 傳進 guest 程序的環境，不寫進指令列、腳本內容、log、manifest。
- 拍快照前，Administrator 以自己的密碼掃描 Panther、Sysprep、Setup、Temp、Public、`C:\Users\sbx`、harness 資料夾與各磁碟根目錄的檔案（明文，以及 answer file 用的 base64 形式），有命中就不拍。
- 對照：
  - 正向：同一個探測由 Administrator 跑時，LSA secret 是 `readable`。
  - 反向：在用完就丟的 box 裡把 DefaultPassword 寫回 Winlogon，`sbx` 的探測要判失敗。
  - 其他 Windows 探測也都加了對照：Administrator 會被 `non_admin` 判出、Administrator 寫得進 harness、刻意設的 `*_TOKEN` 變數會被看到、短指令不會被當成逾時。
- harness 的 Administrator 檢查改用 Windows PowerShell 5.1：box 裡只有 `sbx` 有桌面工作階段，MSIX 的 pwsh 對 Administrator 啟動不了。模型指令仍走 pwsh 7。pwsh 的套件路徑記在 harness 資料夾的 `pwsh.path`（`sbx` 只能讀）。

### 5.9 Windows 實測結果與交接（2026-10-31）

**base**：

- build `42796005b373`（15:00）。
- Windows 11 Enterprise LTSC Evaluation 24H2（26100.1742，EnterpriseSEval，Licensed）。
- Windows Update 關閉。ISO SHA-256 `67cec586…5da68`。
- VirtualBox 7.2.22 走 VT-x（主機已關 Hyper-V 與 Memory Integrity）。
- 2 vCPU、6 GB RAM、64 GB 動態 VDI、host I/O cache。
- 從零建置約 6 分鐘（不含 Windows 安裝本身）。box 從 `clean` 快照冷開機到 `sbx` 桌面約 80 秒。

**`--limits-test` 41／41**（`runs/verify/limits-vbox-20261031-150054.json`，每一項都有對照）：

- 帳號與憑證：
  - 不是管理員（對照：Administrator 會被判出）。
  - 改不了 harness（對照：Administrator 寫得進）。
  - `no_logon_secret`（見 5.8）：sbx 看到 `autologon=1 user=sbx`、沒有 Winlogon 密碼、`lsa=denied`、沒有 answer file、沒有光碟。正向對照是 Administrator 讀得到 `readable len=24`；反向對照是把 DefaultPassword 寫回後探測判失敗。
  - 環境變數沒有金鑰（對照：自設的 `*_TOKEN` 會被看到）。
- 網路：
  - 經 router 時，主機與 LAN 的埠、gateway、VirtualBox NAT 位址、metadata、私有網段、router SSH 全部逾時（對照：plain NAT 下主機的埠是 open）。
  - router DNS 開著；mDNS、SSDP 沒有回應。
  - 斷網後 HTTPS 失敗、localhost 照常，恢復後 PyPI 再通。
- 指令：3 秒逾時被殺（對照：1 秒的指令正常結束）；exit code 0／1／3／93／94／1603 都正確傳回。

**9 款工具**（Mac pipeline 匯出的 muse-spark-1.3 抽取結果；每款都在第二個從快照冷開機的 box 斷網重播通過，judge 都判 working。Meta 共 $0.114）：

| 工具 | Windows 等級 | 版本 | 裝法 | 和 Linux（Modal gVisor）的差異 |
|---|---|---|---|---|
| frugon | function | 0.2.6 | `uv tool install frugon` | 相同 |
| agent-database-cli | function | 0.4.1 | `npm install -g agent-database-cli` | 相同，多了 `list` |
| nlm-memory | function | 0.21.20 | `npm install -g nlm-memory` | 相同 |
| agent-history | function | 0.16.0 | `uv tool install git+…` | smoke 改成 `doctor` 與 `search --mode text`；沒有 Ollama 時 `index` 做不了，`search` 回 `(no matches)`；3 條裡 2 條離線 |
| akm | function | 0.10.261022 | `npm install -g akm-cli` | 版本比 Linux 的 0.10.261019 新；另外跑了 `index`、`curate` |
| martty | function | 0.3.3 | `npm install --global martty` | 用 `martty-cli`：`martty` 指令要第一次互動啟動才出現；`--demo` 要加 `--dump-frame` 才不需要 TTY；Linux 的 `--help` 要網路，這裡全部離線 |
| aria-code | **install** | 0.165.0 | `npm install -g @artheras/aria-code` | Linux 是 function。Windows 只有 `--help`、`--version` 算進去，`aria update --check` 要網路，log 把等級降成 install |
| alysiscode | function | 0.15.2 | `pipx install alysis-code` | 沒有 Docker Desktop，`sandbox doctor --smoke` 回 not ready（記為 note）；`doctor` 正常 |
| labelize | function | 1.10.0 | `npm install @goodboy008/labelize-wasm` | 跟 Linux 一樣用 wasm 套件、node 腳本轉圖（PNG 8506 bytes，再轉回 ZPL）；cargo、docker 的裝法沒試 |

紀錄與證據在這台的 `runs/verify/`（不進 git，沒有寫回 `data/software`），合併時再帶到 Mac。frugon 的第一筆 run（150518）image 標籤被截斷，以 151653 那筆為準。

**每筆 Windows 紀錄合併時要加的 note**（協調 session 決定：指令照實際跑的原樣保留，PATH 前綴不拿掉）："On Windows, open a new terminal after installing so PATH includes the tool; the sandbox refreshed PATH in the same session instead."

**已知限制**：

- 主機要關掉 Hyper-V 與 Memory Integrity，VirtualBox 才走 VT-x。走 NEM 時多 vCPU 會凍住（見 5.8）。
- 評估版授權 90 天（約到 2027-01-29），過期後每小時關機，要重建 base。Windows Update 關閉，所以快照停在 26100.1742，沒有累積更新，跟一般使用者的電腦不同。
- winget 由 pickfit 從 GitHub release 安裝（LTSC 沒有 Store），版本與雜湊記在 manifest。只能從 Store 裝的工具記為 `needs_store` 未驗證。
- 沒有 Docker：要 Docker 的功能驗證不到。
- 沒有單一使用者的記憶體、程序數或檔案大小上限，VM 的 6 GB RAM 和磁碟就是上限。
- 一次只能一個 box。每款工具 6–13 分鐘。
- `run_background`：agent-history 用它在背景啟動 `serve`，75 秒後 VBoxManage 回 20，跟 sentinel 的 0 對不上，harness 判為不可信（方向是安全的），所以這款沒能宣稱 service 等級。要再查。
- VirtualBox 安裝程式忽略了參數，裝上了 host-only 網卡與橋接 filter（VBoxNetLwf）。box 沒有用到，每次開機前檢查網卡會拒絕它們。
- NAT hairpin：router 擋了主機自己的公網 IPv4（extra set），但家用路由器可能經 WAN 位址被打到，記為已知限制（跟 5.7 相同）。
- 主機上還有一個舊的 Oracle Extension Pack 7.0.6（版本不合、無法載入，沒有用到），要不要移除由念誠決定。

---

## 6. 要念誠決定的事

（10/29：第 1 項已決定走 Tart、guest 用 macOS 26，見 5.4。第 2、3 項還沒決定。另待念誠：要把防火牆移到 host 端（softnet）就要在這台 Mac 上親自設一次 setuid。）

1. **macOS 走 Tart 嗎？** 同意後我會執行：`brew install openai/tools/tart`；`tart pull ghcr.io/cirruslabs/macos-tahoe-base:latest`（約 25 GB 下載、約 33 GB 磁碟，clone 另佔變動量）。guest 用 macOS 26（建議）還是 27？
2. **Windows 要不要在賽前用 GitHub Actions？** 要的話：(a) 接受 3.1 的條款風險；(b) 先到 GitHub Settings → Billing 把 Actions 預算設 $0（超過免費額度就停，不扣卡）；(c) 同意在 private repo 加一個 workflow、用 Cloudflare quick tunnel。不要的話，Windows 只做第 4 節的證據。
3. **第 4 節的證據層級要不要做？** 要的話需要 schema 加欄位，由協調 session 決定放哪裡。

---

## 7. 來源（2026-10-29 讀取）

macOS：
- [S1] Apple macOS 27 SLA（第 2B(iii)、3 節）：https://www.apple.com/legal/sla/docs/macOSGoldenGate.pdf；macOS 26：https://www.apple.com/legal/sla/docs/macOSTahoe.pdf
- [S2] Cirrus Labs 首頁（加入 OpenAI、Cirrus CI 停止服務）：https://cirruslabs.org/
- [S3] Tart repo 與 issue：https://github.com/openai/tart（#1394、#1261）
- [S4] Tart LICENSE（FSL-1.1-ALv2）：https://raw.githubusercontent.com/cirruslabs/tart/main/LICENSE；舊的授權頁：https://tart.run/licensing/
- [S5] `tart clone`（APFS CoW）：https://raw.githubusercontent.com/cirruslabs/tart/main/Sources/tart/Commands/Clone.swift
- [S6] `tart run` 網路選項、`tart exec`、vsock 控制：https://raw.githubusercontent.com/cirruslabs/tart/main/Sources/tart/Commands/Run.swift、.../Commands/Exec.swift、.../ControlSocket.swift
- [S7] macOS image 模板與套件：https://github.com/cirruslabs/macos-image-templates、https://github.com/cirruslabs/macos-image-templates/pkgs/container/macos-tahoe-base
- [S8] Tart quick start（下載約 25 GB、admin/admin）：https://tart.run/quick-start/；Tahoe 模板規格：https://raw.githubusercontent.com/cirruslabs/macos-image-templates/main/templates/vanilla-tahoe.pkr.hcl
- [S9] softnet：https://github.com/cirruslabs/softnet；Tart FAQ：https://tart.run/faq/
- [S10] Lume：https://cua.ai/docs/lume、https://cua.ai/docs/lume/reference/cli-reference、授權 https://raw.githubusercontent.com/trycua/cua/main/LICENSE.md
- [S11] Anka 授權：https://docs.veertu.com/anka/licensing/
- [S12] GitHub Actions runner 價格：https://docs.github.com/en/billing/reference/actions-runner-pricing
- [S13] GitHub Actions 計費與免費額度：https://docs.github.com/en/billing/concepts/product-billing/github-actions
- [S14] GitHub-hosted runner 規格、label、網路需求：https://docs.github.com/en/actions/reference/runners/github-hosted-runners、https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
- [S15] EC2 Mac：https://aws.amazon.com/ec2/instance-types/mac/
- [S16] AWS Dedicated Host 價格 JSON：https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/dedicatedhost-ondemand.json
- [S17] EC2 Mac 使用指南：https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-mac-instances.html
- [S18] Scaleway Apple silicon 價格：https://www.scaleway.com/en/pricing/apple-silicon/（頁面擋抓取，數字來自搜尋摘要）
- [S19] Scaleway FAQ：https://www.scaleway.com/en/docs/apple-silicon/faq/
- [S20] MacStadium 價格：https://www.macstadium.com/pricing
- [S21] Codemagic：https://codemagic.io/pricing/
- [S22] Namespace：https://namespace.so/pricing
- [S23] Blacksmith：https://www.blacksmith.sh/pricing；WarpBuild：https://www.warpbuild.com/pricing
- [S24] Apple Developer Forums（VM 名額外洩）：https://developer.apple.com/forums/thread/830119
- [S25] 社群部落格（落地約 33 GB，2026-10）：https://flaviocopes.com/mac-test-vm/

GitHub 條款：
- [S26] GitHub Terms for Additional Products and Features：https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features
- [S27] GitHub Acceptable Use Policies：https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies

Windows：
- [S28] `Set-NetFirewallProfile`：https://learn.microsoft.com/en-us/powershell/module/netsecurity/set-netfirewallprofile
- [S29] GitHub roadmap #821（出站限制，not planned）：https://github.com/github/roadmap/issues/821
- [S30] runner image 內容：https://raw.githubusercontent.com/actions/runner-images/main/images/windows/Windows2025-Readme.md、.../Windows11-Arm64-Readme.md
- [S31] Windows Sandbox 安裝需求：https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install
- [S32] Windows Sandbox 概觀：https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-overview
- [S33] `.wsb` 設定：https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file
- [S34] `wsb` CLI：https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-cli
- [S35] Microsoft：在 M 系列 Mac 上使用 Windows 11：https://support.microsoft.com/en-us/windows/options-for-using-windows-11-with-mac-computers-with-apple-m1-m2-and-m3-chips-cd15fd62-9b34-4b78-b0bc-121baa3c568c
- [S36] UTM scripting：https://docs.getutm.app/scripting/reference/；Windows 指南：https://docs.getutm.app/guides/windows/
- [S37] QEMU `restrict=on`：https://www.qemu.org/docs/master/system/invocation.html
- [S38] UTM issue #5134（ARM64 guest agent）：https://github.com/utmapp/UTM/issues/5134
- [S39] Windows OpenSSH：https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse
- [S40] Parallels 試用：https://www.parallels.com/products/desktop/trial/
- [S41] Parallels 價格（2026-07-28）：https://www.parallels.com/blogs/parallels-desktop-vs-windows-laptop-cost/
- [S42] Parallels Pro 功能：https://www.parallels.com/products/desktop/pro/
- [S43] `prlctl exec`：https://docs.parallels.com/parallels-desktop-developers-guide/command-line-interface-utility/manage-virtual-machines-from-cli/general-virtual-machine-management/execute-a-command-in-a-virtual-machine
- [S44] VMware Fusion 免費：https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/
- [S45] Fusion 上的 Windows 11：https://knowledge.broadcom.com/external/article/315609/features-of-windows-11-vm-on-vmware-fusi.html
- [S46] Azure Retail Prices API：https://prices.azure.com/api/retail/prices；計費：https://azure.microsoft.com/en-us/pricing/details/virtual-machines/windows/
- [S47] Azure 免費帳號：https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account
- [S48] Azure 上的 Windows 11 授權：https://learn.microsoft.com/en-us/azure/virtual-machines/windows/windows-desktop-multitenant-hosting-deployment
- [S49] Azure Run Command：https://learn.microsoft.com/en-us/azure/virtual-machines/windows/run-command
- [S50] AWS Windows 價格檔：https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Windows/index.json
- [S51] EC2 計費：https://aws.amazon.com/ec2/pricing/on-demand/
- [S52] AWS Windows FAQ：https://aws.amazon.com/windows/faq/
- [S53] SSM 無網際網路的 VPC：https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html
- [S54] dockur/windows：https://github.com/dockur/windows；ARM64：https://github.com/dockur/windows-arm
- [S55] OrbStack machines：https://docs.orbstack.dev/machines/
- [S56] Modal VM Sandboxes：https://modal.com/docs/guide/vm-sandboxes
- [S57] GitHub Linux runner 有 KVM：https://github.blog/changelog/2024-04-02-github-actions-hardware-accelerated-android-virtualization-now-available/
- [S58] AppVeyor：https://www.appveyor.com/pricing/
- [S59] CircleCI：https://circleci.com/pricing/、https://circleci.com/pricing/price-list/
- [S60] Azure Pipelines：https://learn.microsoft.com/en-us/azure/devops/pipelines/licensing/concurrent-jobs
- [S61] Windows 11 授權條款（OEM 版，2024-04）：https://microsoft.com/content/dam/microsoft/usetm/documents/windows/11/oem-(pre-installed)/UseTerms_OEM_Windows_11_English.pdf
- [S62] Windows 11 Enterprise 評估版：https://www.microsoft.com/en-us/evalcenter/evaluate-windows-11-enterprise
- [S63] Windows Dev Environment（舊 VM 網址轉址）：https://learn.microsoft.com/windows/dev-environment/
- [S64] Windows on Arm 的 x64 模擬：https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation

發佈證據：
- [S65] GitHub Releases API：https://docs.github.com/en/rest/releases/releases
- [S66] Release 資產 digest：https://github.blog/changelog/2025-06-03-releases-now-expose-digests-for-release-assets/
- [S67] GitHub AUP 第 7 節：同 [S27]
- [S68] Artifact attestations：https://docs.github.com/en/actions/concepts/security/artifact-attestations
- [S69] Homebrew JSON API：https://formulae.brew.sh/docs/api/
- [S70] Homebrew bottles：https://docs.brew.sh/Bottles；BrewTestBot：https://docs.brew.sh/BrewTestBot
- [S71] test-bot 原始碼（`brew test`）：https://github.com/Homebrew/brew/blob/main/Library/Homebrew/test_bot/formulae.rb
- [S72] homebrew-cask CI：https://github.com/Homebrew/homebrew-cask/blob/main/.github/workflows/ci.yml
- [S73] winget manifest schema 1.12.0：https://github.com/microsoft/winget-cli/blob/master/schemas/JSON/manifests/v1.12.0/manifest.installer.1.12.0.json
- [S74] winget-pkgs 驗證流程：https://learn.microsoft.com/en-us/windows/package-manager/package/repository
- [S75] Scoop bucket CI：https://github.com/ScoopInstaller/GithubActions/blob/develop/src/Action/PR.psm1
- [S76] npm package.json（`os`、`cpu`、`optionalDependencies`）：https://docs.npmjs.com/cli/v11/configuring-npm/package-json
- [S77] npm 條款：https://docs.npmjs.com/policies/open-source-terms
- [S78] PyPI JSON API：https://docs.pypi.org/api/json/
- [S79] wheel 平台標籤：https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/
- [S80] PyPI ToS：https://policies.python.org/pypi.org/Terms-of-Service/
- [S81] conda-forge win-arm64（arm64 交叉編譯未測）：https://conda-forge.org/blog/2026/02/09/win-arm64/
