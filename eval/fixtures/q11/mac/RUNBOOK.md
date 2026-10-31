# Mac 實跑手冊（q11、q12 共用）

第 5 節：Mac 題「念誠的 Apple silicon Mac，用另開的 macOS 使用者帳號，每次跑完照清單移除裝過的東西。由念誠親手執行（`method: human`）」。本手冊把這句話寫成步驟。q11、q12 的題目專屬步驟在各自的 README；這裡是兩題共用的準備、斷網、量測與移除。

**每一次實跑**＝一題、一組（對照或實驗）、一個新的測試帳號。跑完就刪帳號，下一次再開新的。

## 0. 腳本

都在本資料夾（`eval/fixtures/q11/mac/`），開跑前複製到 `/Users/Shared/eval-fixtures/`，讓測試帳號讀得到：

| 腳本 | 誰執行 | 用途 |
|---|---|---|
| `snapshot_state.sh` | 主帳號，sudo | 記下系統層級裝了什麼（before／after／cleanup） |
| `diff_state.py` | 主帳號 | 比對快照，印出移除清單 |
| `preflight.sh` | 測試帳號 | 確認帳號是新的：家目錄、環境變數、模型檔、VM |
| `offline.sh` | 測試帳號，sudo | 關掉／檢查／恢復所有網路介面 |
| `footprint_watch.py` | 測試帳號，sudo | q11 的記憶體量測（q12 不需要） |
| `scan_transcript.py` | 任何人 | 找出終端機紀錄裡像登入、token、帳號的行 |

## 1. 基準環境（開跑前決定一次，兩組相同）

見 `../needs.json` 的「Mac baseline」。建議做法（選項 A）：

- 機器：念誠的 Mac（2026-10-30 記錄：Apple M5、24 GiB、macOS 27.0.1）。這台不是 16 GB；q11 的記憶體條件以量到的 footprint（< 12 GiB）判定，報告寫明實際硬體。
- 主帳號的 Homebrew 在實跑期間移開：`sudo mv /opt/homebrew /opt/homebrew.main`（先 `brew services stop --all`）。測試帳號登入後，用 Homebrew 官方安裝程式裝一份**空的** Homebrew（算基準環境，不算答案的步驟），照安裝程式最後的提示把 `brew shellenv` 加進 `~/.zprofile`，記下版本。跑完刪掉這份，再把主帳號的搬回來。
- Xcode／Command Line Tools 是系統層級的，保持原樣並記下版本（`xcode-select -p`、`pkgutil --pkg-info=com.apple.pkg.CLTools_Executables`）。
- 跑之前停掉所有虛擬機（`ifconfig` 不能有 `bridge100` 以上的介面），關掉佔記憶體的 app。

## 2. 開一個測試帳號（主帳號）

```sh
RUN=q11-control            # 題號-組別，例如 q12-treatment
TU=evalq11c                # 測試帳號，每次新的名字
sudo sysadminctl -addUser "$TU" -fullName "Eval $RUN" -password - -admin   # 互動輸入密碼
sudo mkdir -p /Users/Shared/eval-fixtures /Users/Shared/eval-runs/$RUN
sudo cp -R eval/fixtures/q11 eval/fixtures/q12 /Users/Shared/eval-fixtures/
sudo chmod -R a+rX /Users/Shared/eval-fixtures
sudo chown "$TU" /Users/Shared/eval-runs/$RUN
sudo sh /Users/Shared/eval-fixtures/q11/mac/snapshot_state.sh /Users/Shared/eval-runs/$RUN before "$TU"
```

- 測試帳號是管理者（Homebrew 與 `sudo` 步驟需要）。
- 不登入 Apple ID、不開 iCloud、不改系統設定；設定輔助程式的選項一律選「略過」或不分享。

## 3. 在測試帳號裡跑

用「快速切換使用者」登入測試帳號，打開「終端機」。

```sh
F=/Users/Shared/eval-fixtures; R=/Users/Shared/eval-runs/q11-control   # 依實際名稱
# （選項 A）先裝基準 Homebrew，再開一個新的終端機視窗
sh $F/q11/mac/preflight.sh $R/preflight.txt        # 要 PASS；不 PASS 就修好環境再開始
script -q $R/steps-transcript.txt                  # 之後在這個 shell 裡照答案的步驟做
echo $$                                            # q11：記下這個 shell 的 pid，給 footprint_watch.py
```

- 答案的指令逐行貼進這個 shell，照原樣執行；第 5 節允許的調整（填版本號、佔位字、接受預設值）照做並記錄。
- 每個指令的 exit code 都看一下（`echo $?`），失敗就停，記錄在哪一步。
- 題目專屬的檢查見 `../README.md`（q11）與 `../../q12/README.md`（q12）。
- 結束時打 `exit` 關掉 `script` 紀錄。

## 4. 斷網

```sh
sudo sh $F/q11/mac/offline.sh off $R/net-state.txt   # 關掉所有網路服務與 Wi-Fi，然後自動檢查
sh $F/q11/mac/offline.sh check                       # 要印 offline check: PASS
...
sudo sh $F/q11/mac/offline.sh on $R/net-state.txt    # 檢查做完就恢復
```

「所有網路介面都關掉」的判準（`offline.sh check`）：所有網路服務停用、Wi-Fi 關閉、沒有 IPv4／IPv6 預設路由、除了 loopback 沒有介面有 IPv4 位址或非 link-local 的 IPv6 位址、測試用的 HTTPS 請求失敗。VM 的 bridge 介面也算，所以要先停掉所有 VM。

## 5. 跑完之後：移除清單

登出測試帳號，回到主帳號：

```sh
sudo pkill -u "$TU"; sleep 2; sudo pkill -9 -u "$TU"
sudo sh /Users/Shared/eval-fixtures/q11/mac/snapshot_state.sh /Users/Shared/eval-runs/$RUN after "$TU"
python3 /Users/Shared/eval-fixtures/q11/mac/diff_state.py /Users/Shared/eval-runs/$RUN/before /Users/Shared/eval-runs/$RUN/after \
  | tee /Users/Shared/eval-runs/$RUN/removal-checklist.md
```

照 `removal-checklist.md` 逐項處理並打勾，固定要做的有：

- [ ] 停掉並移除測試期間新增的背景服務（`launchd-plists`：先 `launchctl bootout`，再刪 plist；`listeners` 不能留下測試帳號的程式）。
- [ ] 移除新增的 app（`applications`）、`.pkg` 安裝的檔案（`pkg-receipts`：`pkgutil --files` 列出的檔，再 `pkgutil --forget`）、`/usr/local/bin` 等目錄裡新增的指令、`/etc/paths.d` 新增的項目、`/Users/Shared` 新增的檔（評測腳本與紀錄除外）。
- [ ] 「files outside the test home changed」裡測試期間新建的檔逐一刪除；macOS 自己更新的檔不動。
- [ ] Homebrew（選項 A）：測試帳號那一份整個刪掉（`sudo rm -rf /opt/homebrew`）。主帳號的那一份**等最後的比對做完**再搬回來。
- [ ] 網路恢復（`offline.sh on`）。
- [ ] 把要保留的紀錄（transcript、回覆、量測 JSON、preflight、清單）從 `/Users/Shared/eval-runs/$RUN` 複製出來。
- [ ] 刪除測試帳號與家目錄：`sudo sysadminctl -deleteUser "$TU"`（會刪掉家目錄裡下載的模型、快取、設定）。
- [ ] 再拍一次快照並比對，要印出 `nothing left`（macOS 自己的檔除外，逐項註明）：

```sh
sudo sh /Users/Shared/eval-fixtures/q11/mac/snapshot_state.sh /Users/Shared/eval-runs/$RUN cleanup "$TU"
python3 /Users/Shared/eval-fixtures/q11/mac/diff_state.py /Users/Shared/eval-runs/$RUN/before /Users/Shared/eval-runs/$RUN/cleanup
```

- [ ] 比對乾淨之後，把主帳號的 Homebrew 搬回來：`sudo mv /opt/homebrew.main /opt/homebrew`，主帳號的 `brew services` 照原本的恢復。

清單、處理結果與最後的比對一起存進檢查紀錄。下一次實跑從第 2 步重新開始。
