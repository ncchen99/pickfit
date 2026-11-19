# 驗證範圍的分布與 treasure 候選規則

> 報告（2026-11-19），給念誠決定 treasure 規則用。方向在 [coverage.md](coverage.md)。資料是 `data/software/` 裡 1,150 筆上架紀錄，在本機只讀計算，沒有寫回。

## 11/19 的決定

先上規則 6：未驗證的紀錄不再封頂 69 分，但不能當寶藏。規則 3 到 5 不上。規則 1 等 sec.v2 重掃後看 conditional 的分布再定。規則 6 是 `loop/proposals/coverage-rule6-unverified.patch`，接在第四份 patch 後面套，套完馬上跑 `pickfit score --refresh`。

## 重點

- **預設設定不改分數。** 四份 patch 全部套上、設定都用預設值時，1,150 筆的品質總分、confidence、封頂和寶藏一筆都沒變。會動的只有 R8：`other` 和五個新類別共 124 筆的熱門度改用合併的基準，差距在 −1.3 到 +0.7 分之間，沒有一筆因此得到或失去寶藏。
- **沒驗證到最多的是功能。** 1,022 筆的功能沒有全部驗完。其中 321 筆是裝都沒裝起來，其餘最常見的原因是 feature judge 沒看到功能在運作（249 筆）、agent 沒回報（131 筆）、需要帳號（115 筆）。
- **安全的未知，重掃後會少三分之一。** 現在 642 筆的安全只掃了一部分或完全沒掃。其中 335 筆是 sec.v1 判成 vulnerable、但沒有記錄哪些東西沒讀到的。照 security 工作串的 sec.v2 dry run 估計，重掃後剩 430 筆，原因也會分得清楚：沒有 lockfile 123 筆、沒有讀取器（Maven、NuGet、Swift 等）106 筆、advisory 資料庫沒有收（C/C++）104 筆。
- **GUI 和網頁 App 的易用性、影片幾乎都沒有。** 336 筆適用，易用性 0 筆有評分，影片只有 10 筆。
- **候選規則裡，影響最大的是「功能驗證到一半才能當寶藏」**，161 個寶藏會掉 105 個。最溫和的是「未驗證改成不能當寶藏、不再封頂 69」，寶藏數不變，剛好 69.0 分的 217 筆全部散開。

## 怎麼算的

- 每筆紀錄的 Verification Coverage 分成 8 個維度：install、function、service、security、docs、usability、video、repo_signals。每個維度記狀態（verified、partial、unverified、not_applicable）、比例和原因。格式、gap 代號表和能力登記表在 [pickfit/coverage.py](../../pickfit/coverage.py)，`uv run pickfit coverage report` 會重算這份報告的大部分數字。
- 這份報告的「未知」是 partial 加 unverified。一筆在同一個維度可以有好幾種原因，每種各算一次。
- 前一個維度沒過，後面的維度就記成 `blocked_by_install` 或 `blocked_by_function`，不另外算原因，免得同一個原因重複出現。
- 軟體自己壞掉（suspected_tool_fault、人工判定的 failed、功能因為工具本身的錯誤失敗）算驗證的結果，不算未知。這套分法沿用 [failure.py](../../pickfit/verify/failure.py)。
- 一個平台通過，就代表其他平台也驗過，只有 desktop_app 和 browser_extension 例外，因為這兩種的介面跟著平台走。這是照 CLAUDE.md 的方針：CLI 和 MCP 在 Linux 沙盒的結果和 macOS、Windows 一致。
- 「重掃後估計」是把 security 工作串 11/19 的 sec.v2 dry run（`gaps-dryrun.json`）讀進記憶體，取代紀錄裡的 sec.v1 結果。這不是重掃的結果，重掃由協調 session 跑。指令是 `uv run pickfit coverage rules --security-estimate <檔案>`。

原因類別：

| 類別 | 意思 |
|---|---|
| not_attempted | pickfit 還沒試：從沒跑過、只跑了安裝、agent 沒回報某項功能 |
| check_unconfirmed | 試了，但證據沒有站住：全新箱子重跑沒過、指令太長存不進紀錄、log 裡沒有通過的檢查、feature judge 沒看到功能在運作 |
| sandbox_missing | 沙盒缺東西：root、工具鏈、Docker、GPU、螢幕、後端服務、記憶體 |
| no_host | 平台沒有常態的主機（macOS、Windows） |
| needs_account | 需要帳號、API key 或付費方案 |
| needs_hardware | 需要特定硬體 |
| harness_operation | GUI 操作沒做完，或缺桌面元件 |
| unclassified | agent 自己寫的原因，還沒歸進代號 |
| lockfile_missing 等 | 安全的原因，代號沿用 [security.py](../../pickfit/security.py) |

## 1. 各維度的狀態

| 維度 | verified | partial | unverified | not_applicable |
|---|---|---|---|---|
| install | 759 | 82 | 309 | 0 |
| function | 128 | 319 | 703 | 0 |
| service | 198 | 22 | 189 | 741 |
| security | 508 | 335 | 307 | 0 |
| docs | 1045 | 0 | 0 | 105 |
| usability | 0 | 0 | 336 | 814 |
| video | 10 | 0 | 326 | 814 |
| repo_signals | 1100 | 0 | 0 | 50 |

重掃後估計，security 變成 verified 720、partial 167、unverified 263。已知問題的等級另外算，不在 coverage 裡：none 815、conditional 295、not_shipped 22、exposed 13、present_unreachable 5。

## 2. 未知的原因

| 維度 | 原因類別 | 筆數 |
|---|---|---|
| install | no_host | 175 |
| install | not_attempted | 165 |
| install | sandbox_missing | 41 |
| install | needs_account | 12 |
| install | needs_hardware | 1 |
| function | check_unconfirmed | 331 |
| function | blocked_by_install | 321 |
| function | sandbox_missing | 207 |
| function | not_attempted | 197 |
| function | needs_account | 115 |
| function | unclassified | 47 |
| function | needs_hardware | 14 |
| function | harness_operation | 13 |
| function | no_host | 2 |
| service | blocked_by_install | 154 |
| service | not_attempted | 41 |
| service | needs_account | 10 |
| service | sandbox_missing | 6 |
| security | not_attempted | 335 |
| security | lockfile_missing | 182 |
| security | resolve_failed | 61 |
| security | no_source | 50 |
| security | lockfile_unreadable | 14 |
| usability | not_attempted | 240 |
| usability | blocked_by_install | 89 |
| usability | sandbox_missing | 7 |
| video | not_attempted | 129 |
| video | blocked_by_function | 108 |
| video | blocked_by_install | 89 |

security 的 not_attempted 335 筆，全是 sec.v1 判成 vulnerable 的紀錄。sec.v1 沒有記下哪些東西沒讀到，所以 coverage 只能記成 `security.v1_scope_unknown`。重掃後估計的 security 原因如下。

| 維度 | 原因類別 | 筆數 |
|---|---|---|
| security | lockfile_missing | 123 |
| security | no_adapter | 106 |
| security | advisory_db | 104 |
| security | resolve_failed | 79 |
| security | no_source | 50 |
| security | lockfile_unreadable | 40 |
| security | platform_unsupported | 36 |

## 3. 依軟體類別

每格是該類別在這個維度未知的筆數。

| 軟體類別 | 筆數 | install | function | service | security | docs | usability | video | repo_signals |
|---|---|---|---|---|---|---|---|---|---|
| dev_cli | 335 | 51 | 284 | 18 | 149 | 0 | 18 | 18 | 0 |
| local_ai | 291 | 163 | 260 | 90 | 176 | 0 | 67 | 66 | 0 |
| mcp_server | 223 | 69 | 192 | 94 | 75 | 0 | 4 | 4 | 0 |
| other | 244 | 99 | 239 | 3 | 209 | 0 | 238 | 229 | 0 |
| infra_devops | 16 | 3 | 13 | 3 | 8 | 0 | 0 | 0 | 0 |
| security_net | 15 | 1 | 13 | 0 | 8 | 0 | 2 | 2 | 0 |
| data_db | 10 | 2 | 6 | 0 | 4 | 0 | 1 | 1 | 0 |
| productivity_docs | 10 | 2 | 9 | 2 | 8 | 0 | 4 | 4 | 0 |
| media_files | 6 | 1 | 6 | 1 | 5 | 0 | 2 | 2 | 0 |

最弱的是 `other`（大多是網頁 App 和桌面 App）和 `local_ai`。`local_ai` 有一半以上的安裝沒驗到：78 筆從沒跑過，其餘多半只能在 macOS 或 Windows 上跑，或需要 GPU、更多記憶體。

## 4. 依平台

一筆宣稱幾個平台就算進幾個，所以加總會超過 1,150。

| 平台 | 筆數 | install | function | service | security | docs | usability | video | repo_signals |
|---|---|---|---|---|---|---|---|---|---|
| linux | 863 | 239 | 739 | 139 | 433 | 0 | 161 | 156 | 0 |
| macos | 613 | 224 | 535 | 87 | 342 | 0 | 154 | 150 | 0 |
| windows | 478 | 205 | 417 | 79 | 253 | 0 | 118 | 114 | 0 |
| web | 105 | 5 | 104 | 0 | 89 | 0 | 105 | 101 | 0 |
| unknown | 45 | 45 | 45 | 33 | 26 | 0 | 1 | 1 | 0 |

`unknown` 是沒寫平台、也還沒跑過的 45 筆。網頁 App 幾乎都裝得起來（打得開），但功能只有 1 筆驗過，安全有 89 筆掃不完整（大多沒有公開原始碼）。

## 5. 卡住最多紀錄的 gap 代號

現在的紀錄：

| # | 代號 | 維度 | 原因類別 | 卡住的筆數 | 要補的能力 | 主要類別 | 主要平台 |
|---|---|---|---|---|---|---|---|
| 1 | security.v1_scope_unknown | security | not_attempted | 335 | security_scan | dev_cli 111、local_ai 96 | linux 270、macos 200 |
| 2 | function.not_shown | function | check_unconfirmed | 249 | feature_judge | dev_cli 112、mcp_server 70 | linux 211、macos 34 |
| 3 | usability.not_judged | usability | not_attempted | 240 | ease_judge | other 191、local_ai 31 | web 100、linux 89 |
| 4 | lockfile.missing | security | lockfile_missing | 182 | lockfile_from_manifest | other 105、local_ai 51 | linux 111、macos 104 |
| 5 | install.not_run | install | not_attempted | 165 | verify_backlog | local_ai 78、dev_cli 28 | linux 115、unknown 45 |
| 6 | function.not_reported | function | not_attempted | 131 | feature_checks | other 91、local_ai 13 | web 97、linux 28 |
| 7 | video.not_recorded | video | not_attempted | 129 | video_recording | other 109、dev_cli 6 | web 96、macos 19 |
| 8 | function.needs_account | function | needs_account | 115 | test_accounts | dev_cli 69、mcp_server 22 | linux 98、macos 15 |
| 9 | function.claim_unconfirmed | function | check_unconfirmed | 108 | agent_checks | dev_cli 49、mcp_server 21 | linux 84、macos 24 |
| 10 | function.needs_service | function | sandbox_missing | 96 | service_fixtures | dev_cli 33、mcp_server 25 | linux 81、macos 15 |

重掃後估計，第 1 名的 `security.v1_scope_unknown` 和第 4 名的 `lockfile.missing`（sec.v1 的舊原因）會換成 sec.v2 的代號，進前 10 名的是 `adapter.missing`（106 筆，Maven、Swift、NuGet）和 `advisory_db.no_ecosystem`（104 筆，C/C++）。

`uv run pickfit coverage tasks` 把同一份排名轉成工程任務，附上例子、要補的能力和它目前的版本。版本 0 代表還沒做，例如 `test_accounts`、`service_fixtures`、各種安全的讀取器。

## 6. treasure 和封頂的候選規則

每條規則都做成設定，預設值就是現行規則，要換只改 `pickfit/schema.py` 或 `pickfit/score.py` 裡的一個常數，再跑 `pickfit score --refresh`，不用寫新程式。`uv run pickfit coverage rules` 會在記憶體裡重算一次，不寫回紀錄。

| 規則 | 設定 |
|---|---|
| 規則 1：conditional 不再封頂 79，blocked 和 exposed 照樣封頂 | `schema.SECURITY_CAP_LEVELS = {"blocked", "exposed"}` |
| 規則 2：blocked 和 exposed 不能當寶藏、exposed 扣 10 分，不再封頂（scoring.md R5 原本的提法） | `SECURITY_CAP_LEVELS = set()`、`SECURITY_NO_TREASURE_LEVELS = {"blocked", "exposed"}`、`score.SECURITY_EXPOSED_DEDUCTION = 10` |
| 規則 3：安全完全沒掃到的不能當寶藏（R9 選項 1） | `schema.UNCHECKED_CAN_BE_TREASURE = False` |
| 規則 4：掃到的套件要有八成以上才能當寶藏 | `schema.TREASURE_MIN_SECURITY_COVERAGE = 0.8` |
| 規則 5：列出的功能要有一半以上有結論才能當寶藏 | `schema.TREASURE_MIN_FUNCTION_COVERAGE = 0.5` |
| 規則 6：未驗證不再封頂 69，改成不能當寶藏 | `schema.UNVERIFIED_CAP = False` |

結果（寶藏數、比現行多得到或失去的寶藏、剛好 69.0 和 79.0 分的筆數）：

| 規則 | 寶藏（現在） | 得／失（現在） | 69.0／79.0（現在） | 寶藏（重掃後估計） | 得／失（重掃後） | 69.0／79.0（重掃後） |
|---|---|---|---|---|---|---|
| 現行（預設） | 161 | - | 217／149 | 164 | - | 217／137 |
| 規則 1 | 161 | +0／−0 | 217／149 | 203 | +39／−0 | 217／4 |
| 規則 2 | 161 | +0／−0 | 217／149 | 203 | +39／−0 | 213／0 |
| 規則 3 | 108 | +0／−53 | 217／149 | 119 | +0／−45 | 217／137 |
| 規則 4 | 108 | +0／−53 | 217／149 | 116 | +0／−48 | 217／137 |
| 規則 5 | 56 | +0／−105 | 217／149 | 57 | +0／−107 | 217／137 |
| 規則 6 | 161 | +0／−0 | 0／196 | 164 | +0／−0 | 0／181 |

各條規則會做的事：

1. **規則 1** 對現在的紀錄沒有作用，因為全部還是 sec.v1，vulnerable 照 sec.v1 的規則封頂。重掃後，295 筆 conditional 不再封頂，多 39 個寶藏，例如 actual-cli、all-code、dreamd、fetchira。剛好 79.0 分的從 137 筆剩 4 筆。
2. **規則 2** 重掃後的寶藏數和規則 1 一樣（+39）。差別在 13 筆 exposed：不再封頂，改成扣 10 分、不能當寶藏，所以 79.0 分歸零，另有 4 筆未驗證又 exposed 的紀錄從 69 分扣到 59 分。
3. **規則 3** 現在會拿掉 53 個寶藏，就是 unchecked 的那 53 個。其中 29 個是網頁 App，24 個沒有公開原始碼（4d-chess、bay-area-traffic-trends、can-i-park-here 等）。另外 15 個是 CLI 工具，大多沒有 lockfile 或解析失敗。重掃後掃得到的變多，剩 45 個。
4. **規則 4** 現在的結果和規則 3 一樣，因為 sec.v1 只有 clean 能確定讀到全部。重掃後會多拿掉幾筆只掃到一部分的，共 48 個。
5. **規則 5** 最嚴，寶藏剩三分之一左右。原因是多數寶藏的功能只驗過一部分，常見的是需要帳號、feature judge 沒看到功能在運作。這條規則量的是 pickfit 的驗證能力，不是軟體本身，在補上 `test_accounts` 和 `service_fixtures` 之前，會懲罰需要帳號的工具。
6. **規則 6** 寶藏數不變，剛好 69.0 分的 217 筆會依各自的分數散開，未驗證的紀錄之間也排得出先後。但剛好 79.0 分的會從 149 筆變成 196 筆：原本被 69 分壓住、又有已知漏洞的紀錄，改由 79 分封頂。

規則可以疊加，例如規則 1 加規則 3。疊加的結果這次沒有算，要算的話把兩組設定一起放進 `pickfit/coverage.py` 的 `CANDIDATE_RULES` 再跑一次 `pickfit coverage rules`。

## 附錄：維度 × 原因 × 軟體類別 × 平台

只列 10 筆以上的組合，現在的紀錄共 307 種組合，其中 191 種不到 10 筆。平台是 gap 發生的平台。沒有平台的 gap（例如安全）用紀錄宣稱的平台，所以同一筆可能出現在好幾列。完整的表用 `uv run pickfit coverage rules` 印出（JSON 的 `distribution`）。

| 維度 | 原因類別 | 軟體類別 | 平台 | 筆數 |
|---|---|---|---|---|
| install | not_attempted | local_ai | linux | 58 |
| install | no_host | other | windows | 57 |
| install | no_host | local_ai | macos | 40 |
| install | no_host | local_ai | windows | 35 |
| install | no_host | other | macos | 34 |
| install | not_attempted | dev_cli | linux | 24 |
| install | not_attempted | local_ai | unknown | 20 |
| install | not_attempted | other | linux | 20 |
| install | no_host | mcp_server | windows | 17 |
| install | sandbox_missing | local_ai | linux | 17 |
| install | no_host | mcp_server | macos | 13 |
| install | no_host | other | linux | 13 |
| install | not_attempted | mcp_server | unknown | 13 |
| install | needs_account | mcp_server | linux | 12 |
| install | no_host | dev_cli | windows | 12 |
| install | not_attempted | mcp_server | linux | 12 |
| install | no_host | dev_cli | macos | 11 |
| install | sandbox_missing | mcp_server | linux | 10 |
| function | check_unconfirmed | dev_cli | linux | 121 |
| function | not_attempted | other | web | 83 |
| function | blocked_by_install | local_ai | linux | 78 |
| function | blocked_by_install | local_ai | macos | 75 |
| function | check_unconfirmed | mcp_server | linux | 75 |
| function | needs_account | dev_cli | linux | 63 |
| function | sandbox_missing | dev_cli | linux | 63 |
| function | blocked_by_install | local_ai | windows | 58 |
| function | sandbox_missing | local_ai | linux | 53 |
| function | not_attempted | other | linux | 48 |
| function | check_unconfirmed | local_ai | linux | 45 |
| function | blocked_by_install | mcp_server | linux | 37 |
| function | sandbox_missing | mcp_server | linux | 37 |
| function | blocked_by_install | mcp_server | windows | 34 |
| function | blocked_by_install | dev_cli | macos | 33 |
| function | blocked_by_install | mcp_server | macos | 31 |
| function | blocked_by_install | dev_cli | linux | 30 |
| function | blocked_by_install | dev_cli | windows | 26 |
| function | blocked_by_install | other | linux | 26 |
| function | check_unconfirmed | dev_cli | macos | 24 |
| function | blocked_by_install | other | macos | 23 |
| function | blocked_by_install | local_ai | unknown | 20 |
| function | check_unconfirmed | other | linux | 20 |
| function | needs_account | mcp_server | linux | 20 |
| function | check_unconfirmed | other | macos | 19 |
| function | unclassified | mcp_server | linux | 14 |
| function | blocked_by_install | mcp_server | unknown | 13 |
| function | blocked_by_install | other | windows | 11 |
| function | needs_account | local_ai | linux | 11 |
| function | not_attempted | local_ai | macos | 11 |
| function | not_attempted | other | macos | 11 |
| function | not_attempted | dev_cli | linux | 10 |
| function | not_attempted | local_ai | linux | 10 |
| function | sandbox_missing | dev_cli | macos | 10 |
| function | sandbox_missing | other | macos | 10 |
| service | blocked_by_install | local_ai | linux | 39 |
| service | blocked_by_install | mcp_server | linux | 37 |
| service | blocked_by_install | mcp_server | windows | 34 |
| service | blocked_by_install | mcp_server | macos | 31 |
| service | blocked_by_install | local_ai | macos | 23 |
| service | not_attempted | local_ai | linux | 21 |
| service | blocked_by_install | local_ai | windows | 20 |
| service | blocked_by_install | local_ai | unknown | 13 |
| service | blocked_by_install | mcp_server | unknown | 13 |
| service | not_attempted | dev_cli | linux | 10 |
| security | not_attempted | dev_cli | linux | 101 |
| security | not_attempted | dev_cli | macos | 81 |
| security | not_attempted | local_ai | linux | 77 |
| security | lockfile_missing | other | linux | 61 |
| security | lockfile_missing | other | macos | 61 |
| security | not_attempted | dev_cli | windows | 57 |
| security | not_attempted | local_ai | macos | 57 |
| security | not_attempted | local_ai | windows | 54 |
| security | not_attempted | mcp_server | linux | 48 |
| security | no_source | other | web | 44 |
| security | lockfile_missing | other | windows | 33 |
| security | not_attempted | mcp_server | macos | 33 |
| security | lockfile_missing | local_ai | linux | 29 |
| security | lockfile_missing | local_ai | macos | 28 |
| security | not_attempted | other | linux | 27 |
| security | not_attempted | mcp_server | windows | 25 |
| security | lockfile_missing | local_ai | windows | 19 |
| security | not_attempted | other | web | 17 |
| security | resolve_failed | local_ai | macos | 16 |
| security | lockfile_missing | dev_cli | linux | 14 |
| security | not_attempted | other | macos | 14 |
| security | not_attempted | other | windows | 14 |
| security | resolve_failed | local_ai | linux | 14 |
| security | resolve_failed | dev_cli | linux | 13 |
| security | lockfile_missing | dev_cli | macos | 12 |
| security | lockfile_missing | other | web | 11 |
| security | resolve_failed | dev_cli | macos | 10 |
| usability | not_attempted | other | web | 85 |
| usability | not_attempted | other | linux | 69 |
| usability | not_attempted | other | macos | 37 |
| usability | blocked_by_install | local_ai | macos | 23 |
| usability | blocked_by_install | other | linux | 23 |
| usability | blocked_by_install | other | macos | 22 |
| usability | blocked_by_install | local_ai | windows | 21 |
| usability | blocked_by_install | local_ai | linux | 16 |
| usability | not_attempted | local_ai | linux | 16 |
| usability | not_attempted | local_ai | macos | 12 |
| usability | blocked_by_install | other | windows | 10 |
| video | not_attempted | other | web | 82 |
| video | blocked_by_function | other | linux | 62 |
| video | blocked_by_function | other | macos | 45 |
| video | blocked_by_function | other | windows | 32 |
| video | blocked_by_install | local_ai | macos | 23 |
| video | blocked_by_install | other | linux | 23 |
| video | blocked_by_install | other | macos | 22 |
| video | blocked_by_install | local_ai | windows | 21 |
| video | blocked_by_function | local_ai | macos | 20 |
| video | blocked_by_function | local_ai | linux | 18 |
| video | blocked_by_function | local_ai | windows | 17 |
| video | blocked_by_install | local_ai | linux | 16 |
| video | not_attempted | other | macos | 16 |
| video | not_attempted | other | linux | 11 |
| video | blocked_by_install | other | windows | 10 |

重掃後估計的 security 列（10 筆以上）：

| 維度 | 原因類別 | 軟體類別 | 平台 | 筆數 |
|---|---|---|---|---|
| security | advisory_db | other | linux | 59 |
| security | no_source | other | web | 44 |
| security | no_adapter | local_ai | macos | 37 |
| security | lockfile_missing | local_ai | linux | 34 |
| security | advisory_db | other | windows | 30 |
| security | resolve_failed | local_ai | linux | 28 |
| security | advisory_db | local_ai | linux | 27 |
| security | advisory_db | other | macos | 27 |
| security | lockfile_missing | other | macos | 26 |
| security | platform_unsupported | other | macos | 26 |
| security | lockfile_missing | local_ai | macos | 25 |
| security | no_adapter | other | macos | 25 |
| security | lockfile_missing | local_ai | windows | 23 |
| security | resolve_failed | local_ai | macos | 23 |
| security | no_adapter | local_ai | linux | 22 |
| security | advisory_db | local_ai | windows | 21 |
| security | no_adapter | other | linux | 20 |
| security | no_adapter | local_ai | windows | 17 |
| security | no_adapter | other | windows | 17 |
| security | resolve_failed | local_ai | windows | 17 |
| security | lockfile_missing | dev_cli | linux | 16 |
| security | lockfile_missing | other | linux | 15 |
| security | lockfile_missing | dev_cli | macos | 14 |
| security | no_adapter | dev_cli | linux | 14 |
| security | resolve_failed | dev_cli | linux | 14 |
| security | lockfile_unreadable | dev_cli | linux | 13 |
| security | no_adapter | dev_cli | macos | 13 |
| security | resolve_failed | dev_cli | macos | 11 |
| security | advisory_db | local_ai | macos | 10 |
| security | lockfile_missing | mcp_server | linux | 10 |
| security | resolve_failed | other | linux | 10 |

## 還沒確認的

- 重掃後的數字來自 dry run，不是重掃。dry run 讀的是快取裡的 clone，沒有 SBOM，也沒有重新解析 npm 的 registry 套件。
- `function.not_shown` 是 feature judge 沒有確認的功能。有些可能是軟體本身的功能沒做出來，現在的紀錄分不出來，這裡先算成 pickfit 這邊沒有確認。
- agent 自己寫的原因（`function.unclassified`，47 筆）還沒歸進代號，下一輪整理時可以從 `pickfit coverage report` 的例子裡找共同點。
