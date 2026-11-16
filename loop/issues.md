# Harness issues

pickfit 的驗證環境自己的問題。每一段的標題列由 `scripts/loop_state.py` 管（`issue-new`、`issue-status`），不要手改。標題下面的內容是 loop session 的筆記，隨時補。狀態：`open` 還沒人動、`fixing` 正在修、`fixed` 修好了（等它的項目會自動排回佇列）、`parked` 試過幾種做法都不行、`review` 要改到受保護的檔案，等念誠看 `loop/proposals/`。

## H-001 [fixed] 紀錄不能只靠自己重驗：verify --batch 要本機 pipeline.db 裡有抽取結果

- opened: 2026-11-15T23:33:07+08:00
- symptom: `pickfit verify --batch` 的候選來自 `runs/pipeline.db` 的 `extractions` 表。1,058 筆紀錄裡只有 185 筆在本機的 pipeline.db 有可用的抽取結果（11/15 查），其餘是別台機器、別的 worktree 或 `pickfit watch` 寫進來的。佇列裡 43 筆卡在沙盒限制的紀錄，只有 7 筆選得到。
- reproduce: `uv run pickfit verify --batch 1 --repo paragontasx/ferro --force --runner modal --dry-run` 印出 `0 to verify · 0 set aside`。
- 陷阱：`--records` 和 `--repo` 是聯集，不是交集。`--records --repo paragontasx/ferro` 會選到別款（那次選到 patient-zero）。重驗單一筆時不要加 `--records`，而且一定先 `--dry-run`，確認清單上只有目標那一款。
- 方向（還沒試）：讓 `verify` 能從 `data/software/<slug>.json` 自己組出 `VerifyTask`（紀錄裡有 repo、安裝方式、功能清單），或補一個只對單一 repo 重跑抽取的入口。`pickfit reverify` 與 `scripts/rereplay.py` 已經會從紀錄重播，先看能不能沿用。
- 11/16 查到的：43 筆裡 7 筆本機有抽取結果，17 筆只有候選（有 README、沒抽取），19 筆連候選都沒有。紀錄本身組不出 `VerifyTask`：未驗證的紀錄 `install` 是空的，安裝指令和 smoke test 候選只存在抽取結果裡，所以第一個方向行不通，要重讀 repo。
- tried: 11/16 第一種做法，修好。加了 `pickfit discover --repo owner/name`（`pickfit/discover/run.py` 的 `add_repos`）：不搜尋、不呼叫模型，向 GitHub 拿這個 repo 的資料、README、檔案清單，套規則，存成本機的候選；有紀錄的沿用紀錄的 category。接著 `pickfit extract --repo <repo_id> --model prod --limit 1` 抽取（ferro 一筆 US$0.113），`verify --batch --repo` 就選得到。做法和 `pickfit reverify`、`pickfit watch` 接一筆 repo 的流程一樣，只是拆成指令。名字現在指到另一個 repo（原本的被刪、名字被佔走）時不存，回報 `another_repository`。測試在 `tests/test_discover_named.py`（5 個）。驗收：ferro 的 dry-run 從 `0 to verify` 變成只列 ferro；原本選得到的 dog 照樣只列 dog；沒有候選的 bamboo-agent 也存得進來。沒動到箱子和映像，所以沒跑 `--limits-test`。
- 還留著的落差：重新抽取的功能清單，用字可能和紀錄裡 `features` 的不一樣（`pickfit reverify` 在 README 改過時也是這樣）。寫回後要對齊，跑 `uv run pickfit profiles --features-only --slug <slug>`，這一步 loop 沒有做。

## H-002 [fixed] 沙盒映像沒有編譯器與 Rust、Go 工具鏈

reason: needs_toolchain

- opened: 2026-11-15T23:33:07+08:00
- symptom: 15 筆紀錄停在 `needs_toolchain`。映像是 `python:3.12-slim` 加少量套件（`pickfit/verify/sandbox.Dockerfile`），沒有 gcc、cargo、go，只能從原始碼建置的工具裝不起來。
- reproduce: 佇列裡 note 是 `needs_toolchain` 的任一筆。
- 方向（還沒試）：`modal_box.image_layers` 已經會依箱子種類（vm、gui、audio）在基底映像上加 apt 套件，可以照樣加一種帶工具鏈的箱子，只在安裝方式需要建置時用。使用者照安裝指南做的時候也得自己有工具鏈，這要寫進紀錄的 `prerequisites`，不能讓人以為不用。
- 11/16 重現：bamboo-agent 在一般的箱子重跑（run `verify-bamboo-agent-20261116-122612-b589`，30 秒，US$0.006）。安裝腳本要 `sudo`，剩下的兩條路都是 `cargo install`，README 要 Rust 1.95 以上，agent 照規則不裝工具鏈，回報 `needs_toolchain`。
- tried: 11/16 第一種做法。加了建置用的箱子 `pickfit verify --toolchain`（只有 Modal）：
  - 映像 `pickfit-sbx-build:<hash>`：在基底映像上加 Debian 的 build-essential、clang、cmake、ninja、pkg-config、autoconf、automake、libtool、perl、protobuf-compiler 和幾個常用標頭（libssl-dev、zlib1g-dev、libffi-dev、libsqlite3-dev、libclang-dev）；Rust 1.100.0 和 Go 1.27.4 用官方發行檔，下載後先核對釘住的 SHA-256 才解開，裝在 `/usr/local`（`modal_box.TOOLCHAIN_INSTALL`）。授權記在 `NOTICE`。
  - 箱子 4 vCPU、6 GiB、單一指令上限 30 分鐘，agent 的時間上限 45 分鐘（`box.TOOLCHAIN_LIMITS`、`cli.TOOLCHAIN_AGENT_S`）。箱子使用者照樣不是 root，行程數、開檔數、單檔大小的上限都沒動。
  - agent 的提示只在這種箱子換兩句：原本「不要裝語言工具鏈，換別的候選」改成「沒有套件或發行檔可裝時，照 README 的指令建置」，並要求把建置用到的工具鏈記成一則 `note` 的 pitfall，讓照著做的人知道要先裝。候選清單上 cargo、go、source 的附註也跟著換。
  - 測試：`tests/test_verify_toolchain.py`（4 個，先寫、先失敗）。沒有改既有的測試。
  - 驗收：`--limits-test --runner modal --toolchain` 22/22 通過（`runs/verify/limits-modal-gvisor-20261116-123329.json`）。全部測試 1,795 個通過。原本失敗的 bamboo-agent 在建置箱子裡通過：`cargo install bamboo-agent --locked`，level `service`，全新箱子重播通過，judge 判 working（run `verify-bamboo-agent-20261116-123422-6720`，31 分鐘，模型 US$0.044，沙盒 US$0.223）。原本就通過的 fd 在同一種箱子重跑沒有變差：`function`、4 項功能 checked，紀錄裡原本是 3 項（run `verify-fd-20261116-123422-5bf4`，沒有寫回，那只是對照）。
- 修好之後還留著的事：
  - 建置很慢也比較貴。bamboo-agent 的 `cargo install` 在 4 vCPU 上跑了 12 到 18 分鐘，agent 和重播各建一次，一筆的沙盒費約 US$0.22，是一般箱子的一百倍左右。
  - 箱子的 PATH 沒有 `~/.cargo/bin` 和 `~/go/bin`，agent 每個指令前面都加了 `export PATH=...`，這會跟著進安裝指南。要不要在建置箱子的 PATH 裡先加好，還沒做。
  - 映像只有通用的編譯工具。要特定 `-dev` 套件的（ferro、hw-smi 要 OpenCL 標頭，ducklab 的桌面版要 GTK、WebKit）還是會停在缺套件，那是 H-003 的範圍。
  - 在建置箱子裡，agent 會挑 cargo 而不挑發行檔（fd 那次就是）。所以 `--toolchain` 只給確定要建置的紀錄用，不要整批都加。

## H-003 [open] 沙盒使用者沒有 root，裝不了系統套件

reason: needs_root

- opened: 2026-11-15T23:33:07+08:00
- symptom: 17 筆紀錄停在 `needs_root`：安裝步驟要 `sudo apt-get install`、要 systemd，或缺某個共用函式庫（`failure.py` 的 `needs_root` 規則）。
- reproduce: 佇列裡 note 是 `needs_root` 的任一筆。
- 限制：箱子裡 root 是 pickfit 自己蒐證用的身分，被測的軟體不能拿到 root（`limits.py` 的檢查要照樣通過）。
- 方向（還沒試）：把「裝發行版套件庫裡的具名套件」做成 harness 代為執行的一步（由 pickfit 以 root 跑 `apt-get install <名稱>`，不是把 root 交給箱子使用者），並記進安裝步驟。要 systemd 或核心模組的另外分出來，那些多半要 `--runtime vm` 或真的做不到。
- 11/16 這一批看到的，分成三種，做法不一樣：
  - 缺常見的執行期函式庫。joyboy 的 `opencv-python-headless` 要 `libxcb.so.1`，箱子沒有（run `verify-joyboy-20261116-140702-72b9`）。`sandbox.Dockerfile` 本來就為同樣的理由預裝了 libgomp1、libicu。把 libxcb1、libgl1、libglib2.0-0 這幾個幾乎每台桌面 Linux 都有的函式庫加進基底映像，是最便宜的一步。會改到基底映像的雜湊，所有種類的箱子都要重建、重跑 `--limits-test`。這個 session 沒有做。
  - 建置要特定的 `-dev` 套件：datanexa（webkit2gtk、appindicator、rsvg）、neoth 的桌面功能（ALSA）、ducklab 的桌面版（GTK、WebKit）。這才是「由 harness 以 root 代裝具名套件」要解的。
  - 安裝程式本身要 root 加 systemd：hal0（apt、podman、systemd 當 PID 1）、whisper-install、agentloom 的 bootstrap 腳本。代裝套件不夠，要一台開好機的系統，多半是 `--runtime vm` 的事，或照實記成驗不了。
  - 另外有 5 筆掛在這裡其實是缺編譯器，建置箱子（H-002）就解了：dog、gutsy、holdspeak 已經驗過。
- tried:

## H-004 [open] 沙盒裡沒有 Docker 或 Podman

reason: needs_container

- opened: 2026-11-15T23:33:07+08:00
- symptom: 4 筆紀錄的安裝方式只有 `docker run` 或 `docker compose`。
- reproduce: 佇列裡 note 是 `needs_container` 的任一筆。
- 方向（還沒試）：gVisor 箱子裡跑不了 Docker daemon。`--runtime vm` 的 microVM 有自己的核心，先查 rootless Podman 在裡面能不能跑。不行的話看 Modal 能不能直接把那個映像當成另一個沙盒起來。
- tried:

## H-005 [open] 沙盒的記憶體、磁碟或時間不夠

reason: needs_more_resources

- opened: 2026-11-15T23:33:07+08:00
- symptom: 7 筆紀錄停在 `needs_more_resources`。箱子預設 2 GiB 記憶體、單檔 1536 MB。
- reproduce: 佇列裡 note 是 `needs_more_resources` 的任一筆。
- 方向（還沒試）：`verify` 已經有 `--memory-mb` 與 `--file-mb`。先看每一筆缺的是什麼，能靠這兩個參數解的直接重跑。賽後沒有硬性額度上限，但單筆花費照樣記進帳本。
- tried:

## H-006 [open] GUI 操作層是自己寫的：改用現成的 computer-use 套件

- opened: 2026-11-15T23:33:07+08:00
- symptom: 模型的每個動作（點、打字、按鍵、捲動）都由 pickfit 自己的程式送進去：Linux 用 xdotool（`gui_operate.py`），macOS 經 VNC（`vnc.py`、`gui_mac.py`）。Virtualization.framework 的 VNC 收不到滾輪事件，11/3 是在 VM 裡用 launchd 跑一段 JXA 送 `CGEventCreateScrollWheelEvent2` 繞過去的。拖曳、右鍵、組合鍵、觸控板手勢都還沒有。每多一種動作就要再寫一次、再踩一次同樣的坑。
- 要守住的：驗收照舊由 pickfit 自己檢查（檔案、剪貼簿、畫面上的字、nonce），被測的 App 與操作它的套件都不能替自己回報結果。套件只換掉「送動作、拿截圖與元件清單」這一層，也就是 `gui_operate.py` 裡 display 的介面（`screenshot`、`click`、`type_text`、`key`、`scroll`）。
- 授權：MIT、Apache、BSD 可以，AGPL 不行（11/1 已經因此沒裝 cua 的影像辨識擴充）。新增前記進 `NOTICE`。
- 方向：見 `docs/loop.md` 的「GUI 操作改用現成套件」一節。
- tried: 11/1 試過 MIT 授權的 cua-driver 取元件編號清單（brief 2.1 節）。

## H-007 [open] 顯示箱子沒有 zenity 或 kdialog：靠它們開檔案對話框的 App 存不了檔

- opened: 2026-11-16T13:30:41+08:00
- symptom: Cardinal 的「存檔」不開自己的對話框，而是去叫系統的 zenity 或 kdialog。顯示箱子的映像兩個都沒有，所以操作層選了「Save as」之後什麼都沒出現，pickfit 檢查 `~/pickfit-out/patch.vcv` 不存在，操作判失敗，紀錄只能到 `install`。用同一種做法開檔案對話框的 App（JUCE、DPF、部分 SDL 與 Electron 的 portal 後備路徑）都會遇到。
- reproduce: `uv run pickfit verify --batch 1 --repo DISTRHO/Cardinal --force --runner modal --display --audio`，run `verify-cardinal-20261116-131620-914e` 的 report 裡有 `gui check failed · file /home/sbx/pickfit-out/patch.vcv: missing`，agent 的 pitfall 寫「no zenity/kdialog here」。
- 方向（還沒試）：在 `gui.GUI_PACKAGES` 加 `zenity`（Debian 套件，LGPL-2.1-or-later，當獨立程式執行，照 `NOTICE` 裡 GUI 套件的寫法記）。加了要重跑 `--limits-test --runner modal --display`，再拿 Cardinal 重跑看操作過不過。
- tried:

## H-008 [fixed] gVisor 箱子裡 /、/home、/tmp 的擁有者顯示成 nobody（65534）：檢查目錄擁有者的工具不肯啟動

- opened: 2026-11-16T13:34:14+08:00
- symptom: khive 在建置箱子裡編得過（約 11.5 分鐘），但伺服器一啟動就結束：它會檢查資料庫路徑每一層上層目錄的擁有者，箱子使用者看到 `/`、`/home`、`/tmp`、`/var` 的擁有者是 uid 65534，不是 root 也不是自己，於是報 `store-path ancestor ...` 或 `database volume changed after admission identity was captured`。原因多半是 gVisor 箱子把使用者放在自己的 user namespace 裡（`modal_box.NETNS_MAPS` 只對應了網路用的 uid 和箱子使用者），真正的 root 沒有對應，就顯示成 nobody。這是 pickfit 的箱子長得和一般機器不一樣，不是軟體壞了。
- reproduce: `uv run pickfit verify --batch 1 --repo ohdearquant/khive --force --runner modal --toolchain`，run `verify-khive-20261116-131604-806d`（未驗證，`other`，沒重播；模型 US$0.009，沙盒 US$0.088）。最小的重現：在箱子裡以使用者身分跑 `stat -c '%u %n' / /home /tmp`。
- 方向（還沒試）：(1) `--runtime vm` 的箱子不靠 user namespace 斷網（用 nftables），先看那裡的擁有者是不是正常；是的話這類工具改用 `--runtime vm --toolchain` 跑，那個組合要先過 `--limits-test`。(2) 在 gVisor 的對應表裡把 root 也對應進去只讀，這會動到隔離，要非常小心，`limits.py` 的 `netns_held` 等檢查必須照樣通過。
- 可能同一類：tracedecay（`FilesystemLocalityUnverified { filesystem_type: "overlay" }`，它檢查的是檔案系統種類）。
- tried: 11/16 量過了（各開一個 5 分鐘的箱子，以使用者身分跑 `stat -c '%u:%g %n' / /home /tmp /var` 和 `cat /proc/self/uid_map`）。gVisor 箱子：四個目錄都是 `65534:65534`，uid_map 是 `0 1002 1` 和 `1000 1000 1`。`--runtime vm` 的箱子：四個目錄都是 `0:0`，uid_map 是整段對應。所以方向 (1) 成立：這類工具改在 `--runtime vm` 跑就看得到正常的擁有者，不用動 gVisor 的對應表。
- 11/16 驗收：沒有改程式，做法是換箱子。`--limits-test --runner modal --runtime vm --toolchain` 23/23 通過（`runs/verify/limits-modal-vm-20261116-133712.json`）。原本失敗的 khive 用 `--runtime vm --toolchain` 重跑通過：level `service`，全新箱子重播通過，judge 判 working（run `verify-khive-20261116-133734-9074`，模型 US$0.040，沙盒 US$0.161）。gVisor 箱子本身沒有變，擁有者照樣顯示成 nobody；遇到這種工具就改用 `--runtime vm`，skill 裡寫了。標成 fixed 的意思是「等它的項目有路可走」，不是 gVisor 的對應表改了。
