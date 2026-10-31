# q08 測試資料：Apple silicon 上取代 Docker Desktop（只在 Mac 驗證）

題目在 [../../questions.yaml](../../questions.yaml) 的 q08。這題 `sandbox: mac_only`，由念誠在自己的 Apple silicon Mac 上、用另開的 macOS 使用者帳號**親手執行**（`method: human`），每次跑完照第 6 節的清單移除裝過的東西（[../../README.md](../../README.md) 第 5 節）。

這裡的腳本只用 macOS 內建的 `sh`、`curl`、`nc`、`pgrep` 等，不需要 Python、git 或 Xcode 工具，也不會自己啟動任何容器引擎。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `compose.yaml` | **凍結的 compose 測試檔**：nginx（alpine）服務發布在主機 8080 埠、redis（alpine）服務 |
| `preflight.sh` | 在評測帳號、裝任何東西之前跑：確認環境乾淨（PASS／WARN／FAIL） |
| `checks.sh` | 裝完之後跑：照檢查項目原文執行 L2-2、L2-3 的指令並記錄 |
| `snapshot.sh` | 在主帳號跑：列出系統層級可能被安裝程式動到的地方，跑前跑後各一次比對 |
| `run-log-template.md` | 每個答案一份的紀錄表（安裝步驟、看到的視窗、移除） |
| `needs.json`、`calibration.md` | 待念誠決定的環境事項、開跑前的校正步驟與紀錄表 |

## 2. 名詞

- **照步驟原樣（as written）**：答案的安裝與第一次執行步驟逐條照打（可以複製貼上）。只允許第 5 節的調整：填入版本號與佔位字、接受安裝程式的預設值。不可以修正錯的指令或旗標、補上缺的步驟。
- **評測帳號**：每個答案各開一個新的 macOS 使用者帳號（管理者），用完整個刪掉。兩組的答案不共用帳號。
- **沒有 GUI**（L2-4）：見第 5 節 L2-4。

## 3. 每個答案開跑前的準備（在主帳號）

2026-10-30 檢查這台 Mac 時發現下面幾件事，會讓結果失真或違反「沒有 GUI」，每次開跑前都要處理，跑完再復原（第 6 節）：

| 狀況（2026-10-30） | 為什麼有問題 | 處理 |
|---|---|---|
| `sudo` 設成用 Touch ID（`/etc/pam.d/sudo_local` 有 `pam_tid`） | sudo 會跳出 Touch ID 視窗，不是終端機密碼提示 | 開跑前把那一行註解掉，跑完復原 |
| 主機的 8080 埠已有別的程式在聽（127.0.0.1:8080） | compose 會搶不到埠；更糟的是 `curl` 可能拿到那個程式的 200，變成假通過 | 開跑前停掉那個程式；`checks.sh` 在 `compose up` 前也會再查一次，被佔用就不判定 |
| `/usr/local/bin/docker`、`docker-compose` 等是另一套已安裝的容器 app 附的 CLI，`/var/run/docker.sock` 也指向那個 app 的 socket | 登入 shell 的 PATH 中 `/usr/local/bin` 排在很前面；執行它可能直接啟動那個 app（2026-10-30 做腳本測試時實際發生過），結果就不是答案的工具 | 開跑前結束那個 app；把它在 `/usr/local/bin` 的連結與 `/var/run/docker.sock` 移到旁邊（記下原樣），跑完放回 |
| 有虛擬機在跑（Android 模擬器、其他 VM） | 只是佔資源，不影響判定 | `preflight.sh` 只給 WARN；建議開跑時關掉 |
| Homebrew 在 `/opt/homebrew`，擁有者是主帳號 | 評測帳號不能 `brew install` | 依 `needs.json` 念誠的決定處理 |

步驟：

1. 主帳號：處理上表各項。
2. 把本資料夾複製到所有帳號都讀得到的地方：

   ```sh
   cp -R eval/fixtures/q08 /Users/Shared/q08-fixture && chmod -R a+rX /Users/Shared/q08-fixture
   mkdir -p /Users/Shared/q08-runs/<編號> && chmod 777 /Users/Shared/q08-runs/<編號>
   sh /Users/Shared/q08-fixture/snapshot.sh /Users/Shared/q08-runs/<編號>/before.txt
   ```
3. 建評測帳號（管理者；密碼在提示時輸入，不寫在指令裡）：`sudo sysadminctl -addUser q08eval<編號> -fullName "q08 eval <編號>" -password - -admin`。第一次登入時的設定助理畫面屬於開帳號，不算在評測裡；不登入 Apple ID。
4. 切到評測帳號，開「終端機」，跑 `sh /Users/Shared/q08-fixture/preflight.sh`。要**沒有 FAIL**（WARN 可以）。有 FAIL 就回主帳號處理，再跑一次。preflight 的結果會存在 `~/q08-run/preflight.txt`，跑完複製到 `/Users/Shared/q08-runs/<編號>/`。

## 4. 執行（在評測帳號）

1. 從 `run-log-template.md` 複製一份紀錄表，邊做邊填。
2. 照答案的安裝與第一次執行步驟逐條在終端機輸入（L2-1）。全程注意螢幕上有沒有跳出視窗（L2-4）。
3. **開一個新的終端機視窗**（讓答案改過的 shell 設定生效，和使用者實際操作一樣），執行：

   ```sh
   zsh -il /Users/Shared/q08-fixture/checks.sh
   ```

   用 `zsh -il` 而不是 `sh`，是為了讓評測帳號的登入 shell 設定（PATH、環境變數、alias）和直接在終端機打指令時一樣。腳本裡的檢查指令和檢查項目原文一字不差；有疑慮時也可以在同一個視窗親手打那幾條指令，結果以親手打的為準。
4. 把 `~/q08-run/` 整個複製到 `/Users/Shared/q08-runs/<編號>/`，再照第 6 節移除。

## 5. 各 [L2] 項目

### L2-1

> [L2] In a separate macOS user account on Apple silicon, with Docker Desktop not running and not the active docker context or DOCKER_HOST, the install steps run as written

- **用到**：評測帳號、`preflight.sh`、紀錄表。
- **做法**：第 3 節準備、第 4 節第 2 步。
- **判定**：
  - 前提：`preflight.sh` 沒有 FAIL（裡面確認了：Apple silicon、不是主帳號、沒有 Docker Desktop 程序、`DOCKER_HOST`／`DOCKER_CONTEXT` 沒設、沒有別的引擎在 `/var/run/docker.sock` 回應、PATH 上沒有別的 app 附的 docker CLI、8080 埠沒被佔用、sudo 是終端機密碼）。前提不成立時不是答案的錯，處理好環境重跑。
  - 每條步驟都照原樣成功（exit 0，或答案說明的成功狀態）才過。需要在跳出的視窗點按才能繼續的步驟，本項仍看指令本身是否成功；視窗另由 L2-4 判定。

### L2-2

> [L2] `docker run --rm hello-world` succeeds and `docker image inspect hello-world --format '{{.Architecture}}'` prints arm64

- **用到**：`checks.sh`（指令照原文）。
- **判定**：`docker run --rm hello-world` exit 0 而且輸出有 `Hello from Docker!`；`docker image inspect …` 印出的字剛好是 `arm64`。`checks.log` 的 `L2-2` 行是 PASS 才過。

### L2-3

> [L2] Frozen compose fixture (an nginx-alpine web service published on port 8080 and a redis-alpine service): `docker compose up -d` starts both, and `curl -s -o /dev/null -w '%{http_code}' http://localhost:8080` run on the macOS host returns 200

- **用到**：`compose.yaml`、`checks.sh`。
- **做法**：`checks.sh` 把 `compose.yaml` 複製到 `~/q08-compose/`，先確認 8080 埠沒人在聽，再執行 `docker compose up -d`。
- **判定**（`checks.log` 的 `L2-3` 行）：
  - `docker compose up -d` exit 0；
  - 兩個容器 `q08-web`、`q08-cache` 都在執行（`docker inspect -f '{{.State.Running}}'` 都是 `true`）；
  - 在 macOS 主機上執行的那條 `curl` 印出 `200`。容器剛起來時連接埠轉發可能要幾秒，所以最多重試 30 次、每次間隔 2 秒，任一次 200 就算。
  - `compose up` 之前 8080 埠已被佔用時，腳本印 INVALID、不判定，處理後重跑這一步。
  - 回應的 `Server` 標頭記在紀錄裡當證據（應該是 nginx），不影響判定。

### L2-4

> [L2] No GUI: a terminal sudo prompt is allowed; any macOS dialog or app window that must be clicked fails this item

- **用到**：紀錄表的「視窗」欄。
- **做法**：從第一條安裝步驟到 `checks.sh` 結束，念誠看著螢幕，記下每一個跳出的對話框或 app 視窗：時間、標題、內容、是不是一定要點才能繼續。看到視窗時**先不要點**，等至少 60 秒看步驟會不會自己繼續。
- **判定**：
  - 允許：終端機裡的 `sudo` 密碼提示；不需要任何操作就會自己消失、也不擋住步驟的通知橫幅（例如「已加入背景項目」）。
  - 不過：任何一定要點按才能讓步驟或檢查繼續的 macOS 對話框或 app 視窗，例如圖形化的密碼／授權視窗、系統設定裡「允許」系統延伸功能或網路延伸功能、區域網路存取權限詢問、防火牆的連入連線詢問、app 第一次開啟的授權或歡迎視窗、要求安裝 Rosetta 的視窗。
  - 視窗跳出、但不點它步驟與檢查也都完成：本項仍過，紀錄寫「出現但不需要點」。
  - 記為不過之後，可以點選讓流程繼續的選項，把其餘項目做完，並在紀錄寫明點了什麼。

## 6. 移除清單（每個答案跑完都做）

照順序做，每一步記在紀錄表：

1. **評測帳號裡**：`checks.sh` 已經 `docker compose down`。再照答案或該工具官方文件的指令停止並刪除它建立的虛擬機或引擎（例如 stop、delete 類的子指令），記下用了哪些指令。
2. **評測帳號裡**：照工具官方文件的方式反安裝答案裝的每一樣東西（套件管理器的 uninstall、官方解除安裝程式、刪除 app），倒序進行。
3. 登出評測帳號。**主帳號**：`sudo sysadminctl -deleteUser q08eval<編號>`（連同家目錄刪除）。
4. **主帳號**：`sh /Users/Shared/q08-fixture/snapshot.sh /Users/Shared/q08-runs/<編號>/after.txt`，再 `diff before.txt after.txt`。除了第一行時間，其他差異逐項處理：
   - `/Library/LaunchDaemons`、`/Library/LaunchAgents`、`/Library/PrivilegedHelperTools` 多出來的：先 `sudo launchctl bootout system /Library/LaunchDaemons/<檔名>`（Agent 用 `gui/<uid>`）再刪檔；
   - `/usr/local/bin`、`/opt`、`/etc/paths.d`、`/etc/sudoers.d`、`/etc/resolver` 多出來的：刪掉；`/etc/hosts`、`/etc/exports` 雜湊變了：比對後改回；
   - `/var/run/docker.sock` 變了：刪掉（原本的連結在第 5 步放回）；
   - 安裝收據（`pkgutil --pkgs`）多出來的：照該套件的官方解除方式移除檔案後 `sudo pkgutil --forget <id>`；
   - 系統延伸功能多出來的：用該 app 的解除安裝方式移除；做不到時記在紀錄並告訴念誠；
   - `/Applications` 多出來的 app：刪除；
   - 網路介面多出來的（橋接、虛擬網卡）：通常在第 1、2 步就會消失；還在的話重開機後再比一次。
   - 處理完再跑一次 `snapshot.sh` 比對，直到只剩時間不同。
5. **主帳號**：復原第 3 節暫時改動的東西：`/etc/pam.d/sudo_local` 的 Touch ID 行、另一套容器 app 的 `/usr/local/bin` 連結與 `/var/run/docker.sock`、Homebrew（依 `needs.json` 的決定）、停掉的 8080 埠程式。最後再跑一次 `snapshot.sh`，和**第一個答案開跑前**的基準比，只剩時間不同。

兩組都照同一套準備、執行、移除；開跑順序與每個答案用的帳號編號記在紀錄表。
