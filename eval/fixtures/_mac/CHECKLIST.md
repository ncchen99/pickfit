# Mac 題檢查清單（q08、q11、q12）

依 9.3 E（念誠 2026-10-31 決定第 5 項）：Mac 題在念誠另開的乾淨 macOS 使用者帳號裡跑，帳號由念誠自己建，帳號裡只裝 Homebrew；每次跑前、跑後各拍一次快照。由念誠親手執行（`method: human`）。細節與腳本在各題資料夾，本清單只把順序與必做的事列成一張表：

- 共用腳本：[`../q11/mac/`](../q11/mac/RUNBOOK.md)（`snapshot_state.sh`、`diff_state.py`、`preflight.sh`、`offline.sh`、`footprint_watch.py`、`scan_transcript.py`），q08、q11、q12 都用它拍快照與比對。
- q08 另外用 [`../q08/preflight.sh`](../q08/README.md)（Docker Desktop、`DOCKER_HOST`、docker context 的檢查）與 `checks.sh`、`compose.yaml`。
- q11 另外量記憶體（`footprint_watch.py`，9.3 D：24 GiB 的 M5，實測峰值對照 12 GB）。q12 另外要空的 `HF_HOME`、沒有 hub token。

**一次實跑**＝一題 × 一組（對照或實驗）× 一個新帳號。兩組不共用帳號，跑完刪帳號。

## 0. 一次就好（第一次實跑前）

- [ ] 記下機器：晶片、記憶體、macOS 版本（`sysctl -n machdep.cpu.brand_string hw.memsize; sw_vers`），寫進 `q11/calibration.md`。
- [ ] Xcode／Command Line Tools 保持原樣，記下版本（`xcode-select -p`；`pkgutil --pkg-info=com.apple.pkg.CLTools_Executables`）。
- [ ] 把 `eval/fixtures/_mac`、`q08`、`q11`、`q12` 複製到 `/Users/Shared/eval-fixtures/`，`sudo chmod -R a+rX /Users/Shared/eval-fixtures`。

## 1. 每次實跑前（主帳號）

- [ ] 停掉所有虛擬機與佔記憶體的 app；`ifconfig` 沒有 `bridge100` 以上的介面。
- [ ] 主帳號的 Homebrew 移開：`brew services stop --all`，`sudo mv /opt/homebrew /opt/homebrew.main`（測試帳號才能裝自己那一份空的）。
- [ ] q08：另一個 Docker 引擎（Docker Desktop 等）完全結束，`/var/run/docker.sock` 不存在（q08 README 第 3 節）。
- [ ] 念誠建新帳號（管理者；密碼在提示時輸入，不寫在指令裡）：`sudo sysadminctl -addUser <帳號> -fullName "Eval <題號-組別>" -password - -admin`。不登入 Apple ID、不開 iCloud，設定輔助程式一律略過。
- [ ] **跑前快照**：`sudo sh /Users/Shared/eval-fixtures/q11/mac/snapshot_state.sh /Users/Shared/eval-runs/<題號-組別> before <帳號>`。

## 2. 在新帳號裡（只裝 Homebrew，再照答案做）

- [ ] 用 Homebrew 官方安裝程式裝一份空的 Homebrew（算起始環境，不算答案的步驟），照安裝程式最後的提示把 `brew shellenv` 加進 `~/.zprofile`；記下 `brew --version`。除此之外不裝任何東西。
- [ ] 開新的終端機視窗，跑 preflight，要 PASS（q08 用 `q08/preflight.sh`，沒有 FAIL 即可）：`sh /Users/Shared/eval-fixtures/q11/mac/preflight.sh /Users/Shared/eval-runs/<題號-組別>/preflight.txt`。
- [ ] `script -q /Users/Shared/eval-runs/<題號-組別>/steps-transcript.txt`，答案的指令逐行原樣執行；第 5 節允許的調整照做並記錄；每一步看 exit code，失敗就停並記錄。
- [ ] 題目要斷網時（q11、q12）：`sudo sh .../q11/mac/offline.sh off`，`offline.sh check` 要 PASS；做完 `offline.sh on`。
- [ ] 題目的檢查照各題 README（q08 第 4 節、q11 第 3 節、q12）；固定 seed 只用工具文件寫明的環境變數或設定檔，做不到就跑 3 次、2 次過算過（9.3 F）。
- [ ] `exit` 結束 transcript，登出。

## 3. 每次實跑後（主帳號）

- [ ] `sudo pkill -u <帳號>`；**跑後快照**：`sudo sh .../q11/mac/snapshot_state.sh /Users/Shared/eval-runs/<題號-組別> after <帳號>`。
- [ ] `python3 .../q11/mac/diff_state.py .../before .../after | tee .../removal-checklist.md`，逐項移除並打勾（背景服務、app、`.pkg`、`/usr/local`、`/etc/paths.d`、測試期間新建的系統檔；細節見 `q11/mac/RUNBOOK.md` 第 5 節）。
- [ ] 把要保留的紀錄從 `/Users/Shared/eval-runs/<題號-組別>` 複製出來（transcript、回覆、量測、preflight、清單）。
- [ ] 刪帳號連家目錄：`sudo sysadminctl -deleteUser <帳號>`；刪測試帳號那份 Homebrew：`sudo rm -rf /opt/homebrew`。
- [ ] 清理後再拍一次並比對，要印 `nothing left`（macOS 自己更新的檔逐項註明）：`snapshot_state.sh ... cleanup <帳號>`，`diff_state.py .../before .../cleanup`。
- [ ] 比對乾淨後才把主帳號的 Homebrew 搬回來：`sudo mv /opt/homebrew.main /opt/homebrew`，恢復主帳號的 `brew services`。

下一次實跑從第 1 節重來。
