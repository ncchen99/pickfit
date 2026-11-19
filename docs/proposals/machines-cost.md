# 機器時間和成本帳

> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。

## 現況

- 箱子費用是估算的。帳本裡 242 次 Modal 驗證，箱子估 US$4.43，模型 US$23.10。tart 算 0，EC2 的暖機（Windows 約 225 秒）、映像烘焙、網頁沙盒都沒算進去。所以現在說不出一筆實際花多少錢。
- Windows 開機占 32% 的時間，graphtty 開機占一次驗證的 53–75%。replay 箱要等 agent 箱關掉才開（[pipeline.py:232-238](../../pickfit/verify/pipeline.py)）。
- macOS 有一次等了 2 小時 7 分。base 的狀態分在兩處：VM 在主機上，manifest 在 harness（[mac_host.py:499-501](../../pickfit/verify/mac_host.py)、[tart_box.py:1227](../../pickfit/verify/tart_box.py)）。設定錯誤每 30 分鐘默默重試一次（watch 的 `LANE_HOLD`）。
- Mac 上 agent 過了、replay 沒過的 run，浪費了 15,743 箱子秒。
- 兩個 cargo 專案撞到 1800 秒逾時，而且每筆要編兩次（agent 一次、replay 一次）。
- Modal 的 CPU request 等於 limit（[modal_box.py:222](../../pickfit/verify/modal_box.py)），但 agent 有 54% 的時間在等模型回應。

## 提案

### M1 帳本記下每個箱子（收錄前）

在 [pickfit/ledger.py](../../pickfit/ledger.py) 加一張 `boxes` 表，每個箱子一列：

- `box_id`、`provider`（modal、ec2、tart、web、scaleway…）、`lane`、`purpose`（agent、replay、warmup、bake、build、web）
- `run_id`、`slug`、`started_at`、`ended_at`
- `vcpu`、`memory_gb`、`rate_usd_per_hour`、`est_usd`、`rate_source`（價格從哪來、哪天查的）
- `provider_ref`（Modal sandbox id、EC2 instance id 之類，對帳用）

在各 box 類別建立和關閉的地方寫入（`modal_box.py`、`ec2_machine.py`、`ec2_windows.py`、`windows_box.py`、`tart_box.py`、`web_box.py` 等），不要改 watch 的排程。箱子異常結束、沒走到關閉的，下次啟動時要能補上結束時間（例如用 provider 查狀態，或標成 `ended_at` 未知）。

tart 不是 0 元：Mac 主機是按天租的，費用平均攤到那段租期跑過的 VM 上。攤法寫在程式註解和回報裡。

EC2 instance 建立時加上 tag（`pickfit:run_id`、`pickfit:purpose`），之後在 AWS 開 cost allocation tag 就能對帳。開 tag 是帳號設定，由念誠決定，程式只負責加 tag。

### M2 對帳指令（收錄前，程式先寫好）

新增 `scripts/box_reconcile.py`：

- 讀 `boxes` 表的估算，和 Modal 的 billing report、AWS Cost Explorer（依 tag）對照，印出每天、每個 provider 的差額。
- 用 fixture 測。不要對真的帳號跑，`aws login` 會過期，只有念誠能續。

### M3 Windows 的 replay 箱提早開（可以並行做）

agent 箱開始跑時，就同時開 replay 箱讓它開機，agent 過了直接用。agent 沒過就把 replay 箱關掉，費用照樣記在帳本。

- 只在開機慢的 lane 開這個選項（Windows，之後可能加 macOS）。Linux 開機只占 7%，不需要。
- replay 箱還是全新的，agent 從來沒碰過它，fresh-box 規則不變。
- 同時開的 EC2 不能超過兩台。agent 和 replay 各一台時，同一時間只能有一筆 Windows 驗證。要寫成 lane 的並行限制，不能讓第三台開起來。

估計 Windows 驗證的實際時間少 28–42%。

`pipeline.py` 只改 replay 箱什麼時候開的那一段。security 提案會在 replay 裝完之後加一步收 SBOM，兩邊都盡量只動幾行。

### M4 Modal 的 CPU request 調低（可以並行做）

request 調到 agent 等模型時夠用的大小（例如 0.5–1 core），limit 維持。Modal 按 request 和實際用量較大的那個計費，所以等模型的時間會便宜很多。測試要涵蓋 build 類工作仍拿得到足夠的 CPU。

### M5 長編譯用大一點的 build 箱（可以並行做）

安裝步驟裡有 `cargo install`、`cargo build`、`go build` 之類的，就開 8 vCPU 的箱子。Modal 按核心秒計費，總價差不多，估計快 1.5–1.9 倍。逾時 1800 秒不變。

抽取時應該優先選 release binary，這部分屬於抽取的 prompt，記在回報裡給 scoring 提案。

### M6 macOS base 狀態放在主機上（可以並行做）

- manifest 跟 VM 一起放在主機上，harness 啟動時讀主機那份。
- prepare-base 發現主機上已經有符合 manifest 的 VM，就直接接手，不要重建。
- 同一個設定錯誤連續發生，就回報成「需要人處理」的狀態，不要每 30 分鐘默默重試。watch 只需要顯示這個狀態。真的要改 watch 的話，只加讀狀態的幾行，其他留給 throughput 提案。

現在沒有 Mac 主機（scw1 已刪除），只能用 fixture 和假的主機測。

### M7 運作建議（不用寫程式）

Mac 主機最少租 24 小時。攢到 150–300 筆 macOS 項目再租一次，比零星租划算。寫進 `docs/loop.md` 或部署文件。

## 驗收

- `boxes` 表的 schema 遷移（舊帳本可以直接開，不會壞）、各 provider 寫入、異常結束補值、tart 攤提，都有測試。
- replay 箱提早開：agent 過、agent 沒過、EC2 台數上限三種情況都有測試。
- 回報寫出每項的預期效果和還沒實測的地方。

## 不做的事

這三種會削弱「每次驗證都用全新箱子」的規則，不做：

- 同一個箱子跑好幾款軟體。
- 在 agent 的箱子裡重播。
- agent 和 replay 共用套件快取，或沿用用過的箱子。
