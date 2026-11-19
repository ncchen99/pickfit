# watch 吞吐量和 loop runner

> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。

## 現況

機器本身不慢。Linux 開機只占 7% 的時間，一筆 Linux 送件從頭到尾約 3 分鐘。`verify --batch` 在 Modal 上並行 8 個，664 秒做完 43 筆，一小時約 230 筆。

卡住的是 watch（[pickfit/watch.py](../../pickfit/watch.py)）自己的入場限制：

| 限制 | 現在的值 | 位置 |
|---|---|---|
| 每小時最多開始幾筆 | 20（`DEFAULT_HOURLY_CAP`） | watch.py 開頭的常數 |
| 同時跑幾個 | 2（`DEFAULT_CONCURRENCY`），網頁送件也擠在這 2 格 | 同上 |
| 錢的上限 | `--max-usd` 30，每個在跑的工作先保留 US$6（`WORST_CASE_META_USD`） | `_money_blocked`，[watch.py:80](../../pickfit/watch.py) 附近 |
| 輪詢 | 每輪做完睡滿 60 秒 | [watch.py:1411](../../pickfit/watch.py) |
| harvest | 每小時最多 15 筆 | `pickfit/harvest/`（另一個 session 還沒 commit，不要碰）、`worker/wrangler.jsonc:33` |

最傷的是錢的上限。`spent_usd` 只在程式重啟時歸零，花到約 US$24（60–90 筆）之後，`spent + (busy+1) × 6 > 30` 就成立了，watch 不再開新工作，一直要等新程式碼部署、重啟才會再動。每日 US$80 的帳號上限，換算約 250 筆一天，這才是該卡的地方。

## 提案

### W1 錢的上限改成滾動 24 小時（收錄前）

- 已花的錢從帳本算最近 24 小時，不要用程式啟動以來的累計。
- 每個工作保留的金額，改用帳本裡這個 lane 最近的 p95 花費（Linux CLI 約 US$0.6，網頁和 GUI 另外算），沒有資料時才用保守的預設值。
- 每日上限和 `loop/budget.json` 的帳號上限對齊，watch 不要另外再卡一個更小的數字。
- 被錢卡住時，狀態和 log 要寫清楚是卡在哪個數字。

### W2 每個 lane 自己的並行數（收錄前）

- Linux（Modal）預設 6–8，網頁另外 2–4，Windows 最多 2（EC2 配額 8 vCPU，同時最多兩台），macOS 照主機能開的 VM 數。
- 每小時開始筆數的上限拿掉，或者調到不會比並行數先卡住。
- harvest 的來源要有自己的額度，不能把使用者的送件擠掉。使用者送件優先。harvest 本身的程式不要動，只在 watch 這邊分配額度。

### W3 工作做完就叫醒（可以並行做）

把「睡滿 60 秒」改成等一個 event：工作做完、有空位時馬上取下一筆。新送件的輪詢間隔維持 60 秒。估計快 10–15%。

### W4 看得到為什麼沒在跑

watch 的狀態輸出（log 和 `status` 指令或狀態檔）列出每個 lane：在跑幾個、排隊幾個、沒開新工作的原因（錢、並行數、lane hold、等主機）。

### W5 loop runner 少讀一點（可以並行做）

loop 走訂閱，但每批的 session 讀進太多東西：

- 每批都讀整份 `loop/issues.md`，現在 75 KB 還在變大。加一個指令（例如 `scripts/loop_state.py open-issues`）只列還沒解決的項目標題和編號，skill（`.claude/skills/pickfit-loop/SKILL.md`）改成先讀這份清單，要細節才讀單一項目。
- `verify` 會把 thinking 的內容一行行印進 session。改成整份輸出寫到 log 檔，session 只讀 `report.json` 的摘要欄位。
- `LOOP_ITEMS`（`scripts/loop.sh`）可以調大，讓每個 session 多做幾筆再結束，少付幾次讀規則和讀 issues 的成本。

`loop/issues.md` 和 `loop/journal.md` 的內容不要改，只改讀法。

### W6 部署設定

新的設定加到 `deploy/watch/watch.env.example` 的檔尾，附上預設值和說明。這個檔案和 `bootstrap.sh` 在 loop worktree 裡有別的 session 還沒 commit 的修改，只在檔尾加，不要改既有的行。

## 驗收

- 用假的時鐘和假的帳本測：錢的上限滾動、各 lane 並行、使用者送件優先、做完就叫醒、狀態裡的原因。
- 回報寫出改完之後，照 Modal 實測數字估算的每小時和每天筆數。

## 不做的事

- 不碰 `pickfit/harvest/`。
- 不削弱「每次驗證都用全新箱子」：不讓同一個箱子跑好幾筆，不共用快取。
- Windows 同時最多兩台，這是 EC2 配額，不能調。
