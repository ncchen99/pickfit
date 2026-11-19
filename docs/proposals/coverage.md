# Verification Coverage

> 提案（2026-11-19）。方向是念誠 11/19 定的。總覽和共同規則在 [README.md](README.md)。

## 念誠定的方向

- 保留 Software Quality Score。
- 另外建立 Verification Coverage，不併進品質分數。
- 安全狀態未知，不等於有安全問題。
- 沒辦法驗證的原因要分類。
- 重大的已知漏洞和「未知」分開記、分開顯示。
- treasure 的資格規則先不定案，等看到未知狀態的實際分布再決定。

## 三件分開的事

| | 回答什麼問題 | 例子 |
|---|---|---|
| Software Quality Score | 從驗證到的證據看，這款軟體好不好 | 82 分 |
| Verification Coverage | pickfit 驗證了多少、哪些沒驗證、為什麼沒驗證 | 安裝 ✓、功能 3/4、安全 40%（Rust binary 沒有依賴資訊） |
| 已知問題 | 有沒有已知的重大問題 | exposed：undici 的 TLS 繞過 |

「沒驗證」只出現在 coverage，不會扣品質分數，也不會被當成安全問題。

## 信心分數放哪裡

現在的 `scores.quality.confidence`，算的是品質公式裡有資料的權重占多少（[score.py:661](../../pickfit/score.py)）。它其實已經是一種 coverage，只是把所有項目混成一個數字。

建議安全掃描的信心不要併進這個數字，改成 coverage 底下的一個維度：

- 品質分數和驗證範圍回答的是不同問題。一款功能全部測過、但 binary 掃不了依賴的軟體，品質分數不該因此變低。
- 混成一個數字，就看不出是哪裡沒驗證、為什麼。這樣就沒辦法轉成 harness 的改善任務。
- treasure 的規則之後要怎麼結合兩者（例如「品質 ≥ X 而且安全 coverage ≥ Y」），可以等看到分布再明確地寫出來。

`quality.confidence` 保留，改成從 coverage 推算，舊的讀者不會壞。頁面需要一個總結時，再從各維度算一個「pickfit 驗證了多少」來顯示。

## coverage 的資料格式

每筆紀錄一個 `coverage`，底下分維度：

| 維度 | 量什麼 |
|---|---|
| install | 照步驟裝起來了沒 |
| function | 列出的功能驗證了幾項 |
| service | 服務能不能啟動、MCP 握手 |
| security | 掃了多少套件、掃的是裝好的東西還是 lockfile |
| docs | 文件 rubric 有沒有評 |
| usability | GUI 和網頁的易用性（適用時） |
| video | 有沒有錄到操作影片 |
| repo_signals | GitHub 訊號有沒有抓到 |

每個維度記：

- `status`：verified、partial、unverified、not_applicable
- `measure`：比例，例如 3/4 個功能、120/300 個套件
- `gaps`：沒驗證的原因清單
- `checked_at`、`harness_version`

每個 gap 記：

- `code`：穩定不變的代號
- `category`：原因類別
- `detail`、`ecosystem`、`platform`、`component`
- `capability`：要補哪一項 harness 能力才能驗證
- `first_seen`、`last_seen`

## 原因分類

「軟體自己壞了」是驗證的結果，算進品質，不是 gap。gap 只記 pickfit 自己做不到的部分。[failure.py](../../pickfit/verify/failure.py) 已經在分「軟體的問題」和「harness 的問題」，要沿用這套分法，不要另外再做一套。

類別至少包括：

- **安全：** advisory 資料庫沒收這個生態系、沒有 lockfile、lockfile 解析不了或格式不支援、依賴解析失敗、這個生態系沒有掃描器、binary 沒有依賴資訊、沒有原始碼或安裝檔、環境或工具出錯、這個平台還不支援。security 的 subagent 正在定這一類的代號。
- **安裝和功能：**
  - 沙盒缺東西（GPU、顯示器、音訊、網路）
  - 平台沒有主機（目前沒有 Mac 主機）
  - 需要帳號、API key 或付費方案
  - 需要特定硬體
  - harness 缺操作能力（例如拖曳）
  - 文件沒寫安裝步驟
  - 逾時
- **其他維度：** 沒有 README、GitHub API 失敗、錄影失敗等。

沒辦法歸類的放進 `unclassified`。這一類本身也要定期整理成新的代號。

## 從缺口到能力：Verification Coverage Roadmap

1. **發現缺口。** 每次驗證都把 gap 寫進紀錄。
2. **分類原因。** 每個 gap 都有代號和類別。
3. **建立 harness 改善任務。** 用一個指令把所有紀錄的 gap 依代號彙整，依卡住的紀錄數排序，並列出卡住的軟體類型、平台和生態系，產生可以執行的工程任務清單。每項任務附上代號、筆數、例子、要補的能力。
4. **擴充驗證能力。** 每項能力有 id 和版本，記在一份能力登記表裡。gap 的代號寫明要靠哪一項能力解決，例如 yarn.lock 解析器、cargo-auditable 偵測、macOS SBOM。
5. **重新驗證。** 能力的新版本上線後，用指令找出被這項能力卡住的紀錄，只重跑受影響的那個維度（例如只重掃安全），再更新 coverage。資格的變化也一起列出來。

## 報表

`pickfit coverage report`（或同等的指令）要能回答：**pickfit 目前在哪些軟體類型、平台、生態系最缺驗證能力？**

- coverage 依軟體類別、平台（linux、macos、windows、web）、生態系（npm、cargo、go、pypi…）、維度分組。
- 卡住最多紀錄的 gap 代號排行。
- 存每次的快照，看得出趨勢。

這份報表直接指引工程資源該花在哪裡。之後也可以做成公開頁面。

## 評分這邊怎麼改

`proposals/scoring` 的 b3.v7 patch 照這個方向重做：

- 保留：R1 原始輸入、R2 rubric 版本、R3 抽取重用、R8 熱門度基準、R10 從輸入重算。R5 只處理已知漏洞（blocked、exposed），未知不扣分。
- 移到 coverage：R6（依資料多寡往類別平均拉）和 R7（驗證層級算進分數）。這兩項都是「驗證了多少」，不放進品質分數。
- 先不定：R9（unchecked 能不能當 treasure），還有現在 69 分的「未驗證上限」要不要改成 coverage 規則。都維持現狀，等分布出來再決定。

## treasure

這次不改 treasure 的規則。這份工作要交出一份未知狀態的分布報告：各維度、各原因、各類別各有多少筆。念誠看完再決定資格規則。報告也要列出幾種候選規則各會讓多少筆失去或得到 treasure。

## 驗收

- coverage 的格式、gap 代號表、能力登記表、彙整指令、重新驗證指令都有測試。
- 用 `data/software/` 現有的紀錄（只讀）在本機產生一次 coverage 和報表，附上分布和卡住最多紀錄的前 10 個 gap 代號。不要寫回紀錄。
- 受保護的檔案（`pickfit/score.py`、`pickfit/schema.py`、`schema/`、`pickfit/verify/failure.py` 等）照 loop guard 的規定寫成 `loop/proposals/` 底下的 patch。
