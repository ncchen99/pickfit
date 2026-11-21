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
- tried: 11/21 前兩種做法都寫好了，還沒在真的箱子裡跑過（分支 `feat/priv-packages-services`，這個 session 沒開箱子，本機的 Docker 也沒在跑）。
  - 基底映像：`sandbox.Dockerfile` 多裝 libxcb1、libgl1、libglib2.0-0。映像標籤從 `pickfit-sbx:01363ad5a469` 變成 `pickfit-sbx:0fc69b8367dd`，每一種箱子都要重建、重跑 `--limits-test`。照 Debian 13 套件索引的 Installed-Size 估，libgl1 會帶進 Mesa 和 libllvm19，三個套件合起來多約 200 MB。
  - 代裝具名套件：`pickfit/verify/sysdeps.py` 的 `install_named(box, names, timeout_s)`。pickfit 用自己在箱子裡的 root 跑 `apt-get install -y --no-remove -- <名稱>`，箱子使用者還是 uid 1000。名稱先在主機上檢查，選項、版本、萬用字元、路徑、`.deb`、網址、套件來源都不收。sudo、docker.io、systemd、linux-headers 這類要整台機器的也不收，理由寫明要換全權箱。進箱子之後再確認兩件事：箱子設定的套件來源只有 deb.debian.org 和 security.debian.org，apt 打算裝的每個套件（含相依）都標著 Debian 的 label。
  - 每一種箱子能不能裝，是從程式讀出來的：Modal（gVisor 和 VM）和 EC2 的 root 檔案系統可寫，`harness_exec` 走得通。本機的 DockerBox 是唯讀 root，也沒有 root 通道，改成先在一個用完就丟的 root 容器裝好，commit 成 `pickfit-sbx-pkg:<hash>` 再開箱子。gVisor 裡 apt 跑不跑得動還沒實測，一行指令可以確認：`uv run python -m pickfit.verify.sysdeps --runner modal jq`。
  - 觸發：agent 還不能自己開口要（privileges.md 的 P2 是另一個 session 在做），先由 `box_needs` 從抽取結果的 system_packages 挑名稱。上一次停在 `needs_root` 的紀錄，再加讀 README 自己寫的 `apt-get install` 那幾行。`pickfit verify --apt <名稱>` 可以手動指定，`PICKFIT_SYSDEPS=0` 關掉 watch 這一段。
  - 重播和指南：重播的全新箱子只裝 agent 那個箱子裝成功的套件，少一個就開不起來。通過之後，這次 run 的第一個安裝步驟是 `sudo apt-get install -y <名稱>`。
  - 測試：`tests/test_verify_sysdeps.py`，箱子裡那支 root 腳本是對著一個假的 apt 實際執行的。`limits.py` 的新檢查寫成 `loop/proposals/limits-sysdeps-services.patch`，等人審。
- 還沒解的：第三種（安裝程式要 root 加 systemd）不在這裡，等全權箱。工具本身只能用 apt 裝的（例如 `sudo apt install hurl`），目前刻意不由 pickfit 代裝，要等 P2 的政策表決定。
- tried: 11/21 做了全權 VM 箱（`pickfit verify --runner ec2 --runtime rootvm`，程式在 `root_box.py`、`ec2_root.py`），給上面第三種情況用，也就是安裝程式要 root 加 systemd 的那幾筆。
  - 箱子使用者在一台用完就刪的 EC2 VM 上有 sudo。限制都放在 VM 外面：安全群組只開 DNS、80、443，斷網時換安全群組和 network ACL，metadata 在 instance 層級關掉。
  - 只用假的 EC2 client 測過，還沒在真的機器上開過，所以這一項維持 open。要先跑 `--runtime rootvm --limits-test`，通過了再拿 hal0、whisper-install、agentloom 來試。
  - 前兩種情況（缺函式庫、建置要 `-dev` 套件）不歸這個箱子，照原本的方向做。
- 11/21 合併到 `feat/privileges-aws-integration` 之後的狀態，一樣還沒在真的箱子裡跑過：
  - watch 代裝套件預設關，設 `PICKFIT_SYSDEPS=1` 才開（念誠 11/21 決定，等真的箱子確認 apt 跑得動）。上面寫的 `PICKFIT_SYSDEPS=0` 是合併前的做法。`pickfit verify --apt <名稱>` 和單箱探測不看這個開關。
  - agent 用 `request_capability` 要 `system_package` 時，由 `sysdeps.install_named` 代裝。sysdeps 不收的名稱照樣拒絕，代號是 `needs_root`。政策表 `grants_policy.json` 還關著，所以 agent 現在沒有這個工具。
  - 代裝的套件記進這次 run 的 grants，`requested_by` 是 `plan`。`sysdeps.json` 和指南的第一步照舊，指南不會重複列一次。
  - 全權箱裡 agent 要 `root` 或 `container_engine`，政策表直接回「箱子有」。其他箱子一律拒絕，代號 `needs_root`、`needs_container`。watch 還是不會把紀錄送進全權箱。
  - `limits-sysdeps-services.patch` 已經套用。`limits-root-vm-hook.patch` 還沒套，原因和套法寫在 `loop/proposals/APPLY.md`。

## H-004 [open] 沙盒裡沒有 Docker 或 Podman

reason: needs_container

- opened: 2026-11-15T23:33:07+08:00
- symptom: 4 筆紀錄的安裝方式只有 `docker run` 或 `docker compose`。
- reproduce: 佇列裡 note 是 `needs_container` 的任一筆。
- 方向（還沒試）：gVisor 箱子裡跑不了 Docker daemon。`--runtime vm` 的 microVM 有自己的核心，先查 rootless Podman 在裡面能不能跑。不行的話看 Modal 能不能直接把那個映像當成另一個沙盒起來。
- tried: 11/21 沒有照上面的方向去查 Modal 的 `--runtime vm` 跑不跑得動 rootless Podman，改做全權 VM 箱（見 H-003 的紀錄）。映像裡裝了 Docker、compose 和 buildx，箱子使用者在 docker 群組裡。同樣只用假的 client 測過，還沒在真的機器上跑過 `docker run`，這一項維持 open。

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
- tried: 11/1 試過 MIT 授權的 cua-driver 取元件編號清單（brief 2.1 節）。11/16 做完 Linux 這半的執行端，模型端先擴充 pickfit 自己的動作格式（分支 `claude/sad-cori-9f0919`）：
  - 執行端：display uid 的 hands（`gui_operate._HANDS`）改照 computer-use-demo 執行器（`ComputerToolset20260801`）的 xdotool 指令序列。`computer_toolset_20260801` 的 17 個成員做了 16 個：左中右鍵、雙擊、三擊、按住修飾鍵點擊、拖曳、按下與放開、移動、四個方向的捲動加格數、打字、組合鍵加重複次數、按住某鍵、放大、等待，截圖就是每一步原本那張。沒做的是 `cursor_position`，游標在哪 pickfit 自己知道。授權 MIT，釘在 claude-quickstarts `4a4224bd`（`computer.py` 最後一次改在 `5264b729`，就是加上 toolset 那次），記在 `NOTICE`。
  - 沒有整份照搬。上游組的是 shell 字串，點擊時按住的修飾鍵沒加引號，xdotool 本身又能用 `exec` 串指令，所以 pickfit 傳 argv，按鍵與修飾鍵先過自己的白名單。拖曳在按下與放開之間分 12 步移動，上游是直接跳到終點。放大在主機上裁那一步的截圖，不進箱子。一步做到一半失敗時，按住的鍵和滑鼠鍵會放開。操作結束時滑鼠鍵還按著的話，等 App 停掉後放開。
  - 模型端：`pickfit/anthropic_messages.py` 還沒進 `main`，所以照指示擴充 pickfit 的動作格式。`OperatorAction` 多了 drag、move、mouse_down、mouse_up、hold_key、zoom 六種動作，和 x2、y2、hold、repeat、amount 五個欄位。Mac 的 schema 和提示逐字比對過沒變（`BasicOperatorAction`）。
  - 紀錄格式只加不改：舊的 click、type、key、scroll、wait 照原樣重播，沒寫 amount 的 scroll 照舊捲 3 格。zoom 不寫進重播清單。
  - 驗收：單元測試全過，新增的 28 個在 `tests/test_verify_gui_toolset.py`，hands 接一個假的 xdotool 真的跑一遍，記下的 argv 逐一對照上游的指令序列。`--limits-test --runner modal --display` 31/31。LibreSprite 那次 Modal 紀錄（`verify-libresprite-20261104-191755-508f`，四個 GUI 操作）用 `scripts/rereplay.py` 在新箱子重播，五個檢查照舊通過，離線也過，四個操作都靠舊的紀錄動作完成，沒有退回模型。拖曳的示範是 `scripts/probe_gui_drag.py`，在 Chromium 裡放一個 HTML 拖放和一個用指標事件做的滑桿，拖到位才會下載一個含 nonce 的檔案，由 pickfit 自己找檔案驗收。兩種都通過，只點一下的對照組都沒過，換新箱子照紀錄重播也都通過（證據在主 checkout 的 `runs/probe-gui-drag/20261116-002046/`）。
  - 花費：Modal 約 US$0.047（limits test 約 US$0.005、LibreSprite 重播 US$0.030、拖曳 probe 兩次共 US$0.013）。模型 US$0，三次 Baseten 呼叫都回 400，沒有計費。
  - 卡住的：Baseten 上 Muse Spark Open 的部署從 11/16 00:15 起回 400「Model version wpgy40e is deactivated」，11/15 23:23 還正常。GUI operator 現在叫不動，所以拖曳示範用的是照顏色算出位置的紀錄動作，沒有讓模型從目標自己選 drag。新的動作格式還沒在真的模型上試過。
  - 11/21 併進分支 `merge/h006-20261121`，等念誠推上 main：main 這段期間加了 Windows 桌面和 OCR 標記，`operate()` 有三處衝突。解法是 Mac 和 Windows 照舊用基本五種動作加編號文字（`MacOperatorAction`），只有 pickfit 的 Xvfb 用新的動作格式。Windows 的提示原本從 `OPERATOR_INSTRUCTIONS` 產生，合併後那份會變成新格式的文字，git 沒有標成衝突，已改成從 `BASIC_INSTRUCTIONS` 產生，並補了測試。測試 2547 過、7 略過。還沒做的有兩件：新的動作格式仍然沒在真的模型上試過（`scripts/probe_gui_drag.py --operator`），做合併的 session 拿不到金鑰；影片的字幕和動作清單（`video.py`）只認 click、type、key、scroll，拖曳這些新動作不會有字幕。
- 下一步：
  - toolset 接線：`anthropic_messages.py` 合進 `main` 後，operator 是 Claude 時送 `{"type": "computer_toolset_20260801"}`。每個 tool_use（成員名稱加輸入）照 `gui_operate.py` 開頭那張對照表轉成 pickfit 的動作，一樣先過 `to_action` 的檢查才執行。座標是模型看到的那張圖的像素，要用那一輪的 `View` 換回螢幕座標。tool_result 要帶 `toolset_name: "computer"` 和下一張截圖。done 與 give_up 另外給一個工具。驗收方式不變。
  - 拖曳的起點也可以像點擊一樣再對準一次（`aim`），現在只有點擊會。
  - macOS 照原計畫換成 cua-driver，經 `tart exec` 呼叫。

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

## H-009 [open] 紀錄的 kind 和新的抽取不一致時，通過的 run 寫不回紀錄

- opened: 2026-11-16T14:53:05+08:00
- symptom: ling-stack 的紀錄 `kind` 是 `desktop_app`（別台機器上舊的抽取寫的）。這次重新抽取，README 預設的路已經是 Web、daemon、CLI，新的抽取讀成 `self_hosted_web_app`，batch 就照伺服器的方式驗（沒有顯示箱子、沒有 GUI 操作），run 通過，level `service`。寫回時 `SoftwareRecord` 的檢查擋下來：`a desktop app is not service`。`guarded_write_back.py` 直接丟出 traceback，紀錄沒有變。batch 只沿用紀錄的 category（`known_categories`），沒有比對 kind。
- reproduce: `uv run python scripts/guarded_write_back.py runs/verify/verify-ling-stack-20261116-140801-b206`（pydantic 的 ValidationError）。
- 影響：凡是從別台機器來、用新抽取重驗的紀錄都可能遇到。這個 session 寫回的 13 筆裡只有這一筆。
- 方向（還沒試）：
  1. dry-run 就講出來：`load_candidates` 手上同時有紀錄和抽取，kind 不一樣時在清單上標出來，loop 就不會花一次驗證在寫不回去的 run 上。這在 `pickfit/verify/batch.py`，loop 可以改。
  2. 紀錄的 kind 要由管線更新。現在 `pickfit profiles` 沒有「只重寫一筆」的模式（`--slug` 只給 `--features-only` 用），整批重寫會動到所有本機有抽取的紀錄，loop 不敢跑。要念誠或協調的 session 決定：加一個單筆的模式，還是由人改這一筆。
  3. `guarded_write_back.py` 應該印 `not written: <原因>` 而不是 traceback。那個檔受保護，要寫成提案。
- tried:

## H-010 [fixed] Windows 箱子沒有畫面層：GUI App 驗不了

- opened: 2026-11-17T11:21:22+08:00
- symptom: EC2 上的 Windows 箱子（`--runner ec2-windows`）把指令跑在 sbx 的桌面工作階段，App 的視窗打得開，但 pickfit 看不到畫面，也送不了滑鼠和鍵盤。`launch_gui`、`operate_gui` 在這個箱子上沒有實作：`gui.py` 是 Linux 的 Xvfb，`gui_mac.py` 是 tart 的 VNC。只有 GUI 的 Windows 軟體因此驗不了。
- reproduce: `uv run pickfit verify --runner ec2-windows --display <fixture>` 會被 `verify/cli.py` 擋下，`--display` 只收 modal、ec2、tart。
- 11/17 在一台開發機上量到的（映像 `pickfit-win-server2025-3bf708d837`，台北，m7i-flex.large，東西是手動裝的，沒有進映像）：
  1. 截圖和輸入走得通。TightVNC 2.8.89（GPLv2，winget 的 `GlavSoft.TightVNC`，當獨立程式安裝）裝成服務、只聽 `127.0.0.1:5900`。設定在 `HKLM\SOFTWARE\TightVNC\Server`，存取權只有 SYSTEM 和 Administrators，sbx 讀不到密碼。有人連上時，服務會在 sbx 的工作階段裡起一個 SYSTEM 身分的 `tvnserver -desktopserver` 抓畫面、送輸入，sbx 動不了它。從主機用管理員那條 SSH 連線開 `-L` 通道，`pickfit/verify/vnc.py` 的 `VncClient` 連得上：800x600，一張截圖 0.3 到 0.5 秒，點擊和打字都進得了記事本（截圖上看得到打進去的字）。
  2. `VncClient.capture()` 每張截圖都重新連線、拿第一張畫面，那是為 Apple 的 VNC 寫的。TightVNC 連上後的第一張是全黑，馬上重連會被拒。Windows 要保持同一條連線，每次送非增量的更新要求。
  3. 螢幕固定 800x600。EC2 的 Windows 用 Microsoft Basic Display Adapter，`EnumDisplaySettings` 只列出 800x600 一種模式。要 1280x800 得裝虛擬顯示器驅動。查到 `VirtualDrivers.Virtual-Display-Driver`（MIT，SignPath 簽章，winget 上是 zip 加一個控制用的 GUI 程式），無人介入的安裝還沒試。
- 方向（還沒做）：
  1. 另烘一個帶畫面的 Windows 映像（VNC 服務、虛擬顯示器），不要加進一般的映像。sshd 只准管理員開通道，而且只到 `127.0.0.1:5900`。VNC 的密碼照 sbx 密碼的做法：烘映像時在機器上產生，存 LSA secret，開箱時由管理員讀。
  2. `WindowsBox(display=True)`，`screen()` 回傳 `gui_operate.Display`：截圖、點、打字、按鍵、滾輪走 VNC，剪貼簿在 sbx 的工作階段裡讀。
  3. `gui_win.py`，對應 `gui_mac.py` 的 `open_app`、`close_app`、`stop_box_user`。視窗清單要在 sbx 的工作階段裡列（EnumWindows），列的程式又不能是 sbx 動得了的，這一點還沒有解法：管理員的 SSH 工作階段看不到別的工作階段的視窗。可能要一支 SYSTEM 身分、開在 sbx 工作階段裡的小程式。
  4. `gui_operate.py` 的檔案檢查（`_FILE_PY`）是 POSIX 的寫法（lstat、uid、O_NOFOLLOW），Windows 要另一份（擁有者的 SID、reparse point）。`run_operation` 清 `pickfit-out` 用的是 bash 指令。
  5. 操作員的提示詞、`agent.py` 的 GUI 規則、`replay.py`、`record.py`、`verify/cli.py` 的 `--display` 都要加 Windows 一支。`limits.py` 受保護，畫面的控制項目可以加在 `WindowsBox.validate_containment()`，limits test 會照樣記下來。
- 和 H-006 的關係：這裡用的是現成的 VNC 服務加 pickfit 既有的 VNC client，沒有新寫輸入驅動。
- 專案方針（`CLAUDE.md`，11/15）把 Windows 桌面 GUI App 排在後面，所以先記在這裡，沒有往下做。
- tried: 11/17 做了上面量到的 1 到 3。
- 11/17 下午接著做完方向 1 到 5（程式在 `pickfit/verify/gui_win.py`，帶畫面的映像由 `ec2_windows.bake_win_image(display=True)` 烘）：
  1. 螢幕：裝 Virtual Display Driver（root 裝置加 SetupAPI，不用重開機），設定檔只留 1280x800，sbx 登入後把它設成唯一的螢幕。新機器開出來仍是 1280x800。
  2. VNC：密碼改成主機每次開箱產生，只把加密後的值寫進設定（`vnc.vnc_stored_password`，"password" 對得上大家引用的 `dbd83cfd727a1458`）。TightVNC 不支援 Zlib，改寫 ZRLE 解碼：一張 1280x800 從 1.5 到 3 秒、4 MB 降到 0.1 秒、17 KB。
  3. 列視窗：`desk.exe` 由管理員執行，拿 console 工作階段 winlogon 的 SYSTEM token 在那個工作階段開 `deskin.exe`。CreateProcessWithTokenW 會把行程放回呼叫者的工作階段（0），所以改成模擬 SYSTEM 再 CreateProcessAsUser。sshd 把每個指令放在 job object 裡，跨工作階段開行程會被拒（Access is denied），要加 CREATE_BREAKAWAY_FROM_JOB。
  4. 檔案檢查：`_FILE_PY` 加了 Windows 分支（reparse point 當連結、擁有者用 SID 比、FILE_FLAG_OPEN_REPARSE_POINT 開檔），由管理員用映像裡的 Python 跑。
  5. agent 的 `WIN_GUI_RULES`、操作員的 `WIN_OPERATOR_INSTRUCTIONS`（Windows 上也給螢幕文字編號）、`--display` 收 `ec2-windows`。畫面的 8 個控制項目放在 `WindowsBox.validate_containment()`。
- 11/17 驗收：帶畫面的映像 `pickfit-win-server2025-gui-080d04058a` limits test 40/40（`runs/verify/limits-ec2-windows-20261117-143635.json`）。
- 11/17 第一次實跑 KeePassXC（`verify-keepassxc-20261117-143651-6a19`，Opus）：裝好、開得起來，命令列功能在全新機器重播也過了，但 GUI 評審只看到桌布，記成 unverified。原因是 KeePassXC 預設呼叫 `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`，任何截圖（VNC、BitBlt 加 CAPTUREBLT）都拍不到它的視窗；加 `--allow-screencapture` 就看得到。`desk.exe` 現在回報每個視窗的 display affinity，launch 會寫一行 note 說截圖看不到，`WIN_GUI_RULES` 叫 agent 找 App 自己允許截圖的選項。同時讓 `desk.exe` 回報父行程，pickfit 自己待命的 job.exe 和它的 pwsh 不再算成 App 的程序，也不會被停掉。映像改成 `pickfit-win-server2025-gui-51e78224e2`。
- 11/17 第二次實跑 KeePassXC（`verify-keepassxc-20261117-150627-d097`，Opus，模型 US$1.29）：agent 讀到 launch 的 note，自己改用 `--allow-screencapture` 重開，截圖看得到視窗。操作員開了密碼產生器、打字、關掉 KeePassXC 的「10 秒後清剪貼簿」再複製，剪貼簿檢查通過。存檔加匯出 CSV 的兩次檢查都是「pickfit 的檢查沒有回應」：`WindowsBox.harness_exec` 走 run.ps1，run.ps1 把指令放在環境變數裡交給子程序，Windows 單一環境變數上限 32,767 字元，檔案檢查腳本編碼後是 38,000。已改成直接從 ssh 的 stdin 交給 Windows PowerShell，還沒在機器上重跑。這次的重播因為 AWS 登入過期沒開成箱子，所以結果是 unverified。
- 11/17 第三、四次實跑 KeePassXC：檔案檢查修好了（匯出的 CSV 被找到、格式對、含 nonce）。第三次的重播在指令中途 ssh 斷線（這台主機當天對外 IP 換了 4 次，3 個不同網段，最可能是這個），第四次完整通過：level function，全新機器重播通過（離線時錄下的點擊沒對上，上線後操作迴圈重做一次通過），judge working，GUI judge working，重播有錄影（`runs/verify/verify-keepassxc-20261117-155444-e224/replay-10-4.mp4`）。這一項算修好。
- 還可以做：主機 IP 換掉時，進行中的指令一定斷，但之後的指令可以先把新 IP 加進 control 群組再重連，現在不會。
- 操作錄影：`record.WinVncRecorder` 用自己的一條 VNC 連線（壓縮、保持開著）錄，和 Mac 一樣在主機上用 ffmpeg 編碼。

## H-011 [fixed] 影片剪輯只能用 Modal 上的 Muse：改用 Anthropic API 時沒有辦法剪

- opened: 2026-11-17T19:05:00+08:00
- symptom: `pickfit/verify/video.py` 的剪輯和審片都把整支 mp4 交給 Muse Spark Open（Modal 的 endpoint，`open-modal`），因為當時只有它收影片。11/15 起主要模型換成 Anthropic API，Claude 不收影片（vision 文件：JPEG、PNG、GIF、WebP，GIF 只讀第一格），所以沒有 Modal 就剪不了片。另外 `video record` 只會開 tart 或 Modal 的箱子，Windows 的錄影（`WinVncRecorder`）接不進剪輯。
- 做法（參考 11/17 查到的做法：依動作抽關鍵畫面、在畫面上印編號、標出點擊位置、讓模型回答格數再由程式換算時間）：
  1. `Editor`：`--editor muse|claude`（或 `PICKFIT_VIDEO_EDITOR`），預設還是 muse。claude 用 Opus 5.5，剪輯 effort medium、16,000 tokens，審片 low、6,000 tokens，一個紀錄的預算上限 US$3。
  2. 剪輯送的畫面由 pickfit 從自己的事件表挑：每個動作前一刻（紅圈標出點擊位置）和畫面回應之後，加上每次畫面變化之後。跟上一張看起來一樣的畫面併進上一張（全尺寸比對，遮掉 pickfit 自己的游標和作業系統的工作列或選單列；一個打進去的字約 100 個像素，算不同）。最多 160 張，超過時先丟掉沒有動作的。畫面裁到 App 用到的範圍，左上角印編號，每張圖前面一行文字寫編號、時間和它代表的事件，圖片全部放在問題前面。模型回答的格式沿用 EditList（事件編號），誠實規則照舊由程式檢查。
  3. 審片和補字幕：每段剪下來的片子每半秒一張（最多 40 張），同樣併掉相同的畫面。模型回答第幾張，pickfit 換算成片中的秒數。
  4. `app_box` 原本用整張差異圖的外框，Windows 桌布細節多，壓縮雜訊只有 7 個像素卻散在整個畫面上，外框變成全螢幕。改成只看變化密集的 16x16 區塊（`dense_bbox`）。Windows 的工作列（有時鐘、會出現 App 的按鈕）和 Mac 的選單列一樣不算 App 的範圍。
  5. `video edit` 也收驗證的證據資料夾（`runs/verify/<id>/`，裡面有 `verification_run.json`、`report.json`），那次的 run 不必已經寫進紀錄；這種片子不能 write-back。`video record` 依 run 的 runner 開同一種箱子（`--runner` 可改），片頭寫實際的沙盒（Windows 是「Windows Server VM (AWS EC2)」）和挑段落的模型。
- 11/17 實測 KeePassXC（Windows，`runs/verify/verify-keepassxc-20261117-155444-e224/replay-10-4.mp4`，5 分 37 秒，51 個事件，24 個動作）：51 張畫面、約 4.6 萬 input tokens，剪輯 US$0.22（23 秒）；15 段審片全數看到字幕說的事，US$0.27；合計 US$0.49。成品 `~/.pickfit/videos/keepassxc/keepassxc-20261117-1613.mp4`，96 秒，沒有被標記。模型還在 notes 寫了第一次按 Done 時跳出「沒有密碼」的警告、被取消，以及匯出的 CSV 不會出現在畫面上。對照：Muse 約每分鐘 US$0.02。
- 11/17 實測 gifski（macOS，本機 tart，`video make gifski --editor claude`，`runs/video/video-gifski-20261117-195359-f2fb`）：全新 VM 重播，離線時錄下的動作沒產出 GIF，連網後重跑同一組動作通過（138,190 bytes 的 GIF，格式正確）。剪輯 61 張畫面、8.6 萬 input tokens，US$0.37；10 段審片全數通過，US$0.40；合計 US$0.77，成品 48 秒，沒有被標記。這支沒有裁切（App 和存檔對話框用掉大半個螢幕），所以每張畫面比 KeePassXC 的大。模型在 notes 記下第一次存檔後又按了幾次 Cmd+S、檔名打亂一次、跳出「已存在，要取代嗎」，這些重試它沒放進片子。
- 11/18 下午把片子剪得更順、更便宜，兩件事都不用多叫模型。
  1. 慢連線的錄影會把同一張畫面重複 10 到 80 秒。新的 `still_waits` 逐格比對片子顯示的範圍（RGB 三個通道都看，壓縮雜訊不算，指標移動算），同一張畫面在片中超過 2.5 秒的只留前 1.5 秒，段落的最後一張（結果）不剪。接點是硬切，不做淡入淡出，所以不會出現錄影裡沒有的畫面。標題列比照「2x speed」的寫法加上「N s of unchanged screen cut」，clip.json 的段落多記 `waits`。
  2. 剪掉的都是重複的畫面，每張出現過的畫面都還在段落裡，順序也沒變，所以審片的結論照樣成立，只要把 `first_seen_s` 換成新的時間。`video smooth <run>` 照這個規則重剪已經做好的片子，不叫模型，存成旁邊的 `<stem>.smooth.mp4` 和 .json，原本的檔案不動。新做的片子在審片前就先剪好。重剪三支 alacritty（含前後兩張卡片共 7 秒）：842b 從 26.6 秒變 21.4 秒（剪點沒改，仍被標記），7048 從 34.8 秒變 19.3 秒，5f9f 從 36.4 秒變 22.0 秒。
  3. 花費九成以上是輸入的圖片。`looks_same` 原本只數像素，超過 40 個就算新畫面，但同一張靜止畫面兩格之間的壓縮雜訊就有 67 個，同一張圖因此送了好幾次。改成和 `action_changed` 同一個標準（有一整塊 16x16 變了，或總共超過 160 個像素）。複製一份 5f9f 重新剪輯加審片，剪輯的畫面從 10 張變 5 張，花費從 US$0.135 降到 US$0.074，3 段全部審過。
  4. 評估過還沒做的：Batch API 半價，但要改 `meta.py`，而且批次不能帶 fallbacks。縮小畫面能省 token，終端機的小字可能讀不清，要先比較。Files API 不省錢，圖片照樣算 input tokens。Haiku 便宜 40 倍，但念誠說不用較弱的模型，只能當量過的選項。
- 測試：`tests/test_verify_video_frames.py`。
- 還沒做：預設要不要換成 claude（Claude 一支約 US$0.5，Muse 約 US$0.1）；Files API 上傳一次、剪輯和審片共用同一批畫面還沒做，`anthropic_messages` 目前不收 file id。

## H-012 [open] macOS 沙盒只能跑在這台 Mac 上

- opened: 2026-11-17T19:20:00+08:00
- symptom: `TartBox` 在本機跑 `tart`，VM 的網路政策（softnet 的控制通道）、VNC、日誌、清除程序都假設主機就是這台 Mac。macOS 沙盒因此綁在念誠的電腦上，違反「沙盒層不能被平台綁定」的準則，也沒辦法只在測試時才開機。
- 11/17 查到的雲端 Mac：Scaleway 巴黎 fr-par-1 有 M1-M、M2-M、M4-S、M4-SP、M4-M，fr-par-3 有 M1-M，查了 5 次（19:00 到 19:40）都是 `no_stock`。M4-S 約 €0.22／小時，最少計 24 小時（約 €5.3）。AWS 台北沒有 Mac，美東有 mac 系列但 Dedicated Host 配額是 0（念誠說配額不提高）。macOS 的授權允許一台 Mac 同時跑兩個 macOS VM 做開發測試（tart_box 的 docstring），所以租來的 Mac mini 上照樣跑 tart。
- 做了（`pickfit/verify/tart_host.py`）：`TartBox` 在主機上做的事都經過一個主機物件。`LocalHost` 和以前一樣；`SshHost` 走一條 SSH 主連線（ControlMaster），tart 指令變成一個引號包好的遠端指令。softnet 的控制通道由主機上的 `RELAY`（主機自己的 /usr/bin/python3）握著，JSON-RPC 走 SSH 的 stdin/stdout；SSH 斷掉時 RELAY 對 `tart run` 送 SIGINT，VM 不會留著。VM 日誌在主機上建成 0600，清除程序是主機上的背景 shell。VNC 只聽主機的 loopback，`SshHost.vnc_url` 開一個本機轉送埠；guest 不准連主機 VNC 埠的檢查仍用主機上的埠號（`vnc_host_port`）。選主機：`PICKFIT_TART_HOST=user@host`（另有 `PICKFIT_TART_SSH_KEY`、`PICKFIT_TART_SSH_PORT`），沒設就是本機；主機的基底映像說明檔存在這裡的 `~/.pickfit/tart/hosts/<host>/`。`--prepare-base` 也照這個變數在遠端建基底。
- 測試：`tests/test_verify_tart_host.py` 用一支假的 ssh 在本機執行「遠端」指令，接 test_verify_tart 的假 tart：政策經 RELAY 送到 softnet、VNC 埠轉送、關箱時刪 VM 和清除程序、SSH 斷線時 VM 停掉，都有測。本機的 tart 測試全數照舊通過。
- 11/17 22:16 fr-par-1 的 M4-SP 有貨（`low_stock`，€0.24／小時，€165／月，價格頁 scaleway.com/en/pricing/apple-silicon）。念誠同意開一台，也同意加金鑰：pickfit 專用的 ed25519 金鑰在 `~/.pickfit/ssh/scaleway-mac`，公鑰以 `pickfit-scaleway-mac` 上傳到 Scaleway 專案（IAM SSH key `dacc4408-…`）。建立時被拒：`Quota exceeded for resources 'AsServersType_M4_SP' (0/0)`。Scaleway 文件說組織的配額看帳號等級，要驗證付款方式和身分才會調高（M2-M 的那一行直接寫要先驗證身分），驗證後還不夠要開客服單。這兩件都要念誠在主控台做；`scw` 沒有查配額的指令，主控台的配額頁在 Chrome 分頁裡沒畫出內容。
- 11/17 22:42 再試一次仍是配額不足（M4-SP 這時也沒貨了，M2-M 有少量）。用 Chrome 看主控台（只看，沒改設定）：付款方式有一張 11/16 加的卡；配額頁上方寫「加一份有效的身分證件來提高上限（Verify ID）」，篩選 Apple silicon（連 Instances 也是）列出「No quotas matching your search」；按 Verify ID 開出來的是全新的 Jumio 證件加自拍流程，表示證件驗證還沒做；首頁的開始清單 5 項只完成 1 項，「設定付款方式」「驗證身分」都還在；另有一張 11/16 開、還沒結的客服單「在台灣收不到簡訊驗證碼，無法啟用帳號」。念誠以為的身分驗證，可能是手機或付款那一步，不是 Scaleway 要的證件驗證。證件驗證含生物特徵，只能念誠自己做。
- 11/17 晚上念誠完成證件驗證後，配額頁的「Verify ID」提示消失；建立 M4-SP 的錯誤從配額不足變成 `Resource out of stock 'server'`，配額這關過了（配額頁仍列不出 Apple silicon 的項目）。這時巴黎每一型都沒貨，背景每 2 分鐘查一次，M4-S 或 M4-SP 一有貨就開（兩型念誠都同意過，24 小時內）。
- 11/17 23:42 開成一台 M4-SP（`17afd9ad-…`，62.210.194.156，macOS 26.7.3，24 小時承諾到 11/18 23:42）。主機沒有 Homebrew，但有 Xcode 和 /usr/bin/python3；tart 2.41.1、softnet 0.24.1 從 GitHub 發行檔裝到 `~/.local/bin`（checksum 對過，`REMOTE_PATH` 加了 `$HOME/.local/bin`），念誠打 sudo 密碼設了 softnet 的 setuid。映像拉了約 5 分鐘（digest `65c3133a…`，比本機的新）。
- 11/18 建基底失敗：`tart run` 一開就結束，`VZErrorDomain Code=-9 ... Failed to get current host key ... Failed to create new HostKey`。主機的 console 使用者是 root（沒人登入桌面），m1 的登入鑰匙圈鎖著。念誠用 sudo 密碼解鎖登入鑰匙圈被拒（密碼不正確，看來 Scaleway 給的帳號密碼和鑰匙圈的不同步）。另建一個無密碼的鑰匙圈設成預設、再設成登入鑰匙圈，VM 都一樣開不起來（`security login-keychain` 沒有生效），已改回原狀。Apple 開發者論壇 thread 822670：DTS 說 Virtualization「is not daemon safe」，那串的主機只有在自動登入或有人登入桌面時才開得了 VM，最後的解法是用 `sysadminctl` 讓帳號密碼和登入鑰匙圈重新一致再解鎖。
- 下一步（要念誠決定，會改主機的登入設定）：刪掉密碼不同步的舊登入鑰匙圈（新機器裡沒有東西），`sudo sysadminctl -autologin set -userName m1 -password -` 開自動登入，重開機。開機後 m1 自動登入桌面，loginwindow 用現在的密碼建新的登入鑰匙圈並解鎖，SSH 開 VM 應該就可以。之後每台新租的 Mac mini 都把這三步併進那支要 root 的設定腳本（和 softnet 的 setuid 一起）。
- 11/18 凌晨續：`sysadminctl -autologin set` 回 `SACSetAutoLoginPassword error:22` 卻以 0 結束，沒寫出 /etc/kcpassword。改用 `~/.pickfit/autologin.py`（念誠在主機上輸入密碼，先 `sudo -v` 驗證，照 loginwindow 的格式寫 kcpassword：密碼加結尾 0、隨機補到 12 的倍數、11 位元組金鑰 XOR，root:wheel 0600，再設 `autoLoginUser`／`autoLoginUserUID`），重開後 m1 自動登入桌面，系統建了新的登入鑰匙圈。
- VM 仍然開不起來（同一個 HostKey 錯誤），試過：SSH 直接 `tart run`；`launchctl asuser`（要 root，m1 被拒）；在 m1 的 GUI domain 掛 LaunchAgent（`launchctl bootstrap gui/501` 後要 `kickstart` 才會跑，跑在 Aqua 工作階段）；把預設鑰匙圈指回新的登入鑰匙圈（之前刪舊鑰匙圈時被拿掉）。都失敗。m1 的 `passwordLastSetTime` 是 16:22 UTC（第一次重開後，不是我們改的，之後沒再變），Local Items 鑰匙圈和 `user.kb` 用密碼加密，推測還在舊密碼上；error:22 也符合。下一步照 Apple 論壇的解法：念誠執行 `sysadminctl -oldPassword - -newPassword -`（同一組密碼）後重開，再跑 `~/.pickfit/vmtest.sh`（從 Aqua 工作階段開測試 VM）。11/18 01:50 時終端機還停在 Old password，沒有動。
- 11/18 02:27 念誠完成 `sysadminctl -oldPassword - -newPassword -`（同一組，`passwordLastSetTime` 更新）並重開，m1 自動登入，從 Aqua 工作階段開 macOS 26 客體仍然 `Failed to create new HostKey`。同一台主機上 Linux 客體（ghcr.io/cirruslabs/ubuntu）15 秒就跑起來並拿到 IP；macOS 15 客體（macos-sequoia-base）一樣是 HostKey 錯誤。所以是這台主機上任何 macOS 客體都開不了，主機的虛擬化本身沒問題。這台 Mac mini 是 DEP 註冊、由 Scaleway 的 MDM（mdm-par-1.as.fr-par.scw.cloud）管理，m1 底下沒有設定描述檔，全機的描述檔要 sudo 才看得到，還沒看。主機 macOS 26.7.3。
- 還能試的：用 `scw apple-silicon server reinstall` 把主機重裝成 macOS 15（同一個租期內不另外收費，但 tart、softnet、自動登入都要重做，念誠要再輸入 sudo）；或問 Scaleway 客服 macOS 26 主機加他們的 MDM 能不能跑 Virtualization.framework 的 macOS 客體。
- 11/18 03:00 念誠決定重裝成 macOS 15 主機，不行再寫信問客服。`scw apple-silicon server reinstall os-id=61b842ab-…`（macos-sequoia-15，同一租期內不另外收費），主機變成 macOS 15.8.3。softnet 0.24.1 在 macOS 15 上載入失敗（`Symbol not found: _vmnet_interface_start_with_network`，macOS 26 才有），改裝 0.23.0（checksum 對過，有 `--control-fd`）。第一次背景拉 macOS 15 映像時，`nohup … &` 的 `tart pull` 在 SSH 結束時跟著斷在 6%，改成保持連線在前景拉。自動登入前，從 SSH 開 macOS 15 客體失敗（`VZErrorDomain Code=1 Internal Virtualization error`）；念誠執行 `~/.pickfit/rootsetup.py`（密碼只輸入一次：softnet setuid、kcpassword、自動登入、重開）之後，macOS 15.7.7 客體從 Aqua 工作階段和直接從 SSH 都在 8 秒內回應。所以不需要在 Aqua 工作階段啟動 tart，RELAY 經 SSH 的做法可以照用。
- 結論：Scaleway 的 macOS 26 主機開不了任何 macOS 客體（HostKey）；macOS 15 主機加自動登入可以開 macOS 15 客體（macOS 15 主機不能跑 macOS 26 客體）。`PICKFIT_TART_SOURCE`、`PICKFIT_TART_BASE` 讓一台主機改用別的來源和基底名稱（預設仍是 macos-tahoe-base、pickfit-macos-26）。
- 卡在：`PICKFIT_TART_HOST=m1@62.210.194.156 PICKFIT_TART_SOURCE=…sequoia… PICKFIT_TART_BASE=pickfit-macos-15 pickfit verify --runner tart --prepare-base`，基底在遠端 23 秒開起來、建好 sbx，但 online 的網路檢查失敗：`internet unreachable online (public=28); multicast mDNS was answered by the host`，失敗後自動刪掉基底。同一台主機上不加政策的 VM（預設 NAT 或 `--net-softnet`）連 pypi 都是 200。可能是 softnet 0.23.0 對控制通道送來的政策（block @host、224.0.0.0/4、255.255.255.255/32）處理和 0.24 不同，也可能是 DNS 被固定成 1.1.1.1 後在 0.23 被擋（curl -m 4 在解析時逾時也會是 28），還沒分清楚。用 tart 的 `--net-softnet-block=@host,224.0.0.0/4,255.255.255.255/32` 直接測時，20:58 Virtualization 的 VM 程序 EXC_BREAKPOINT 當掉，21:00 主機做了一次正常關機重開（有 shutdown stall 報告，原因不明），自動登入有接上。
- 下一步：在 macOS 15 主機上分開測 softnet 0.23.0 的政策（只 block @host、只 block multicast、DNS 用閘道或 1.1.1.1），找出哪一條讓上網斷掉；需要時 `tart_host` 依主機的 macOS 版本挑 softnet 版本與規則。macOS 26 主機開不了 macOS 客體這件事可以問 Scaleway 客服（念誠說過重裝不行就寫信；macOS 15 可以，所以還沒寫）。
- 11/18 上午查出網路檢查失敗的兩個原因，都不是 softnet 0.23.0 的政策（0.23.0 和 0.24 的規則邏輯一樣，查過原始碼）。用 tart 的 `--net-softnet-block` 在主機上分開測：不加規則時一切正常。加上 pickfit 的三條規則後，直接連 IP（1.1.1.1、pypi 的位址）都通，只有用名稱的網址逾時。
  1. DNS 固定到錯的網路服務：程式取 `networksetup -listallnetworkservices` 的第 2 行，sequoia 映像那一行是 `com.redhat.spice.0`（後面還有三個 `tart-version-*`，Ethernet 在最後）。DNS 因此還留在閘道，閘道就是被擋的 @host，所有名稱解析逾時，curl 回 28，看起來像上不了網。改成每個網路服務都設 1.1.1.1，再用 `scutil --dns` 讀回來，沒改成功就直接報 DNS 的錯。
  2. mDNS 的回應是 VM 自己發的：回應來自 192.168.64.2（VM 自己），不是主機。sequoia 映像有廣播 SSH 服務，查詢經 multicast loopback 回到 VM 自己的 mDNSResponder。探測程式關掉 `IP_MULTICAST_LOOP`，也略過來自自己位址的回應。不擋時主機（192.168.64.1）照樣會回，擋了就沒有回應，正反兩面都量過。
- 修好後在遠端建 pickfit-macos-15 基底，108 秒完成，GUI 基底 64 秒。limits test 第一次 32/33：正向對照要求主機有「開著的 HTTP 埠」，桌機有 AirPlay 的 5000／7000，租來的 headless Mac mini 沒有，那些埠只會拒絕連線（curl 7），sshd 的 22 回 banner（1），KDC 的 88 回空回應（52）。這些都要主機回封包才會出現，擋住後都變成 28。正向對照改成「主機有回應就算」，第二次 33/33。
- 自動化（`pickfit/verify/mac_host.py`，`pickfit mac-host ...`）：供應商只管開機、查狀態、刪機（現在有 Scaleway，經 `scw`，另有給現成 Mac 用的 `ssh`）。其他步驟都走 SSH，換供應商也一樣。
  - `up NAME`：上傳金鑰，挑有貨的型號（M4-S 優先，賣完換下一型），開 macOS 15 主機並等它好。
  - `setup`：裝 tart 2.41.1，以及這版 macOS 跑得動的 softnet（15 用 0.23.0，26 用 0.24.1），都從 openai/ 的發行檔下載並對 checksum。另外寫入 root 步驟的腳本、拉來源映像。不用 sudo，重跑也不會重裝。
  - `root`：唯一要人做的一步。`ssh -t` 執行 `~/.pickfit/rootsetup.py`，念誠打一次 sudo 密碼，設好 softnet setuid 和自動登入後重開。要整段無人值守，可以用 `--password-stdin` 從自己的密碼庫輸入。pickfit 不讀 Scaleway 的 `sudo_password`，所有回應存檔前都先刪掉含 password 的欄位。
  - `check [--boot]`：檢查版本、setuid、console 使用者、映像、基底。`--boot` 再開一台拋棄式 VM，能開表示 Virtualization、softnet、自動登入三件都好。
  - `test`：不夠的基底先建好，再跑 limits test。`--verify REPO`、`--record SLUG` 加上要付模型費的步驟。每步的日誌和 report.json 放在 `runs/mac-host/`。
  - `env`：印出 PICKFIT_TART_* 環境變數。
  - `down --yes`：刪機。Scaleway 的機器滿 24 小時才刪得掉，沒加 `--yes` 不會刪。
- 11/18 10:50 對這台主機（以 `mac-host add scw1 --scaleway-id …` 收編）跑 `pickfit mac-host test scw1 --verify oraios/serena --record gifski`。check 全過，拋棄式 VM 12 秒開好，limits test 33/33。serena 到 service 等級，全新 VM 重播通過、judge working、功能 3/3，模型 US$0.32（`runs/verify/verify-serena-20261118-105238-6136`）。gifski 的錄影失敗：`open Gifski.app` 回 LaunchServices -10825，這個版本要比 macOS 15.7.7 新的系統（當初在 macOS 26 驗的），不是沙盒的問題。改錄 alacritty（結果見下一條）。
- alacritty 在遠端重播通過（function，離線，畫面上讀到 80235），Claude 剪輯加審片共 US$0.23，但片子被標記，因為終端機裡出現「System going down at 04:06」。這是 pickfit 自己的 `shutdown -h +62`（箱子到期自動關機的保險）在 1 小時的警告點對每個 tty 廣播，本機的 Mac 箱子一樣會有，只要錄的 App 是終端機。改成 root 在背景 `sleep` 到期再 `shutdown -h now`（經 detach helper），到期前不廣播。在遠端 VM 上確認過這個程序在設定結束後還在、是 root 的，sbx 的 `pkill` 殺不掉。重錄一次（`runs/video/video-alacritty-20261118-111330-842b`，US$0.18），關機訊息沒了，剩下審片標記「輸入 expr 12345 + 67890」那段結束時最後的 0 還沒出現。截圖上整行是完整的，問題在剪點比畫面早，可能是 VNC 畫面經巴黎晚到（上面第 4 點預料過）。這要調剪輯的剪點或在主機上錄影，還沒做。
- 11/18 中午查清楚上一條的剪點問題並修好。
  1. 原因在錄影。從台北經 SSH 轉送到巴黎，錄影每一格都是新的 VNC 連線加一張 4 MB 的 Raw 畫面，連線 1.3 秒，傳完還要 9 到 12 秒（試過 ZRLE，照片桌布壓完還有 2.4 MB，加上 Python 解碼沒有比較快）。所以約 10 秒才有一張新畫面。舊的 `VncRecorder` 在畫面傳完時，把要這張畫面以來的每一格都補成這張，指標也畫在當下的位置，於是畫面會提早出現，之後又停在舊畫面。上一條那支（842b）打字是 148.26 到 153.15 秒，片子在 151.5 秒就有「6789」，最後的 0 到 163.0 秒才出現（打完後 9.85 秒），剪點卻是打完加 3 秒的 156.15 秒。
  2. 修 `video.py`。新的 `shown_times` 拿 pickfit 每個動作之後等畫面穩定才拍的截圖（下一步的 `op-N.png`，最後一步是 `op-<n+1>.png`），從動作開始往後找第一格沒有任何 16x16 區塊跟截圖不同的畫面（遮掉指標和選單列），當成片子顯示結果的時間。段落至少剪到那之後 `HOLD_S`，給 Claude 的「動作之後」那張也用這個時間。不管連線多慢都適用，用新程式重算 842b，打字那段的結尾從 156.15 延到 166.0。`action_changed` 也改成遮掉選單列和指標上一次的位置，有一整塊變了或超過 160 個像素才算畫面有變。
  3. 修 `record.py`、`vnc.py`。每張畫面從伺服器開始回傳那一刻才放進片子，指標只畫在 pickfit 移動之後的格子上，片子不再比實際早。`Recording` 多記新畫面張數（`captures`）和最久間隔（`frame_gap_s`）。
  4. 重錄第一次是 `video-alacritty-20261118-120759-7048`（重播 US$0.017，剪輯加審片 US$0.29），新畫面 26 張，最久隔 27.87 秒。這次打完 0.54 秒片子就看得到整行，打字那段審片通過。片子仍被標記，被標的是「Click inside the terminal window」那段，審片只看到指標。這是 `action_changed` 舊的毛病，選單列的時鐘剛好跳一分鐘，加上兩格之間零星 67 個像素的壓縮雜訊（舊門檻 40），四次沒有效果的點擊都被寫成「畫面有變」。改好後同一支錄影重新 `video edit`（US$0.096），3 段全部審過，沒有標記，成品 `alacritty-20261118-1209.mp4` 35 秒。
  5. 重錄第二次是 `video-alacritty-20261118-122045-5f9f`（重播 US$0.017，剪輯加審片 US$0.135），沒有標記，成品 `alacritty-20261118-1222.mp4` 36 秒，3 段全部審過。這次連線更慢，460 秒只有 26 張新畫面，最久隔 79.85 秒。打字在 291.25 秒結束，整行到 303.25 秒才出現（晚 12 秒），段落剪到 306.25 秒。照舊的規則會停在 294.25 秒，又是看不到 0 的那種片子。三次合計約 US$0.56。
  6. 還沒做的是在主機上錄影。一張畫面 10 秒以上，最久等過 80 秒，片子裡的動作會一頓一頓的，但剪點現在對得上。測試在 `tests/test_verify_video_frames.py`、`tests/test_verify_vnc.py`。
- 主機 `17afd9ad-…` 計費到 11/18 23:42（台北），之後 `pickfit mac-host down scw1 --yes` 才刪得掉。刪除前要念誠確認。
- 11/19 00:10（台北）念誠確認後用 `pickfit mac-host down scw1 --yes` 刪掉了，Scaleway 上已經查不到這台。刪之前 watch 從 11/18 21:11 起就沒有工作。watch 機器和這台 Mac 上的 `mac-hosts/scw1.json`、`tart/hosts/62.210.194.156/` 的兩個 manifest 也一起刪了，免得之後租到同一個 IP 的主機被當成已經有 base。現在 watch 沒有 Mac 可用，renting 又沒開，macOS 的送出會停在「no Mac host is ready and renting is off」，等 `mac-host add`／`up` 加了主機，或服務加上 `--mac-rent`，才會開始跑。
- 若要改回 Aqua 工作階段啟動：`SshHost.start_vm` 要改成在 Aqua 工作階段啟動 `tart run`（LaunchAgent + kickstart），softnet 的控制通道不能再靠繼承 fd 跨過 launchd，要改成 RELAY 在 Aqua 那邊開一個 UNIX socket、SSH 這邊連上去轉送。
- 還沒在真的遠端 Mac 上跑過驗證。可以開 VM 之後要做的：
  1. 在 Scaleway 專案加一把 pickfit 專用的 SSH 公鑰（要念誠同意，這是新增存取用的金鑰），開 M4-S、macOS 26，`ssh m1@<ip>`。
  2. 主機上裝 tart 和 softnet。softnet 需要一次 setuid root（`sudo chown root:wheel <softnet> && sudo chmod u+s <softnet>`），要 m1 的 sudo 密碼，由念誠自己打。確認 /usr/bin/python3（Command Line Tools）在，RELAY 要用。
  3. `tart pull ghcr.io/cirruslabs/macos-tahoe-base:latest`（約 25 GB），再 `PICKFIT_TART_HOST=m1@<ip> uv run pickfit verify --runner tart --prepare-base`，`--display` 再一次；limits test 過了才跑真的工具。
  4. 量 VNC：每張截圖、每格錄影都是新的連線（Apple 的伺服器在同一條連線上會給舊畫面），跨到巴黎每張可能要 1 到 2 秒。截圖可以接受；錄影每秒 4 格會變成同一張重複好幾格，可能要把錄影搬到主機上做。
  5. 測完刪機器。最少計 24 小時（server type 的 `minimum_lease_duration` 是 86400 秒），24 小時內能不能刪還沒查證。

## H-013 [open] 這台 Mac 開著全通道 VPN 時，tart 的 VM 連不到 GitHub 和 ghcr.io

- opened: 2026-11-17T20:00:00+08:00
- symptom: 11/17 在本機 tart 驗 serena（`runs/verify/verify-serena-20261117-193224-7c30`，Opus，US$0.30，988 秒）記成 unverified：`uv tool install -p 3.13 serena-agent` 下載 Python 3.13 時連 github.com 逾時三次，`brew install python@3.13` 卡到 600 秒被砍，astral 的鏡像被 reset，conda-forge 也失敗。這是主機網路的問題，不是 serena 的。
- reproduce: 一台乾淨的 headless 箱子裡 curl：github.com、api.github.com、ghcr.io（都在 20.27.177.0/24）全部 000（TCP 連不上），ping 20.27.177.113 卻通；pypi.org、files.pythonhosted.org、formulae.brew.sh、registry.npmjs.org、releases.astral.sh、objects.githubusercontent.com 都正常。主機自己連 github.com 正常（0.08 秒連上）。主機的預設路由是 `utun4`（Pulse Secure 在跑），到 20.27.177.113 的路由也走 utun4：主機自己的連線過得去，VM 經 vmnet NAT 出去的過不去。Homebrew 的 bottle 放在 ghcr.io，所以這段期間 Mac 箱子裡幾乎所有 `brew install` 都會失敗。
- 不只 GitHub：同一晚重驗 orbit（之前在 macOS 驗到 service，npm 安裝；`runs/verify/verify-orbit-20261117-200052-574e`，US$0.10）也是 unverified。`npm install -g @orbit-tools/cli` 連 registry.npmjs.org 三次都 ECONNRESET（含 IPv4 優先和 `--fetch-retries=5`），同一個網址 curl 拿到 200。看起來是 VPN 對 NAT 出去、連線多或資料量大的流量會斷。新的開機偵測有記下「github.com、ghcr.io do not answer」，agent 把它寫成 sandbox 類的 pitfall。
- 做了：箱子開機時（online 政策設好之後）測一次 github.com 和 ghcr.io（`SOURCE_PROBES`），連不上就寫進 `describe()`，叫 agent 別去找鏡像、記成 pitfall；主機的 log 也記一行。不讓箱子直接失敗，因為不經過 GitHub 的工具（例如從 Dropbox 下載的 gifski）照樣驗得了。
- 11/17 晚上念誠關掉 VPN 後重驗（同一套本機 tart，Opus）：serena 到 service 等級，全新 VM 重播通過（online），judge working，feature judge 3 項中 3 項看到在運作，模型 US$0.36（`runs/verify/verify-serena-20261117-221251-632a`）。orbit 這次 agent 到 service，重播的第 5 項檢查沒過，記成 function，重播通過、judge working，模型 US$0.18（`runs/verify/verify-orbit-20261117-220421-d246`）；這一項沒過跟網路無關。serena 開機時 github.com 漏答一次探測，後來安裝照樣從 GitHub 下載成功，所以探測改成漏答時隔 2 秒再試一次，避免偶發逾時誤導 agent。
- 解法不在程式裡：跑 Mac 驗證時關掉 VPN，或讓 VPN 不接管 VM 的流量；或改用遠端 Mac 主機（H-012）。VPN 是念誠的設定，pickfit 不去改它。
- 另外記一筆：11/17 寫 H-012 時，`prepare_base` 的失敗路徑測試在預設狀態目錄搬到 tart_host 的中間版本跑了一次，刪掉了真的 `~/.pickfit/tart/pickfit-macos-26.json`，並把 `pickfit-macos-26.log` 清成 0 位元組（兩台基底 VM 本身沒事）。說明檔已照原內容寫回（build id、digest 和 GUI 基底記的上層版本一致），日誌救不回來。`tests/conftest.py` 現在讓每個測試都用自己的 tart 狀態目錄，也拿掉 `PICKFIT_TART_HOST`。

## H-014 [fixed] macOS 的 GUI 箱子跑 limits test 時，跑到的是 Linux 的畫面檢查

- opened: 2026-11-18T10:50:00+08:00
- symptom: 11/18 在 Scaleway 的 macOS 15 主機上跑 `pickfit verify --runner tart --display --limits-test`，前面 macOS 的檢查都過，接著跑的是 Xvfb 那一組：`display_up`（`/usr/bin/xdpyinfo` 不存在，exit 127）、`display_server_uid`（`pgrep -x Xvfb`）、`display_server_held`，全部失敗。`limits.py` 的 `run_limits_test` 只要 `box.display` 有值就跑這一組，沒有分作業系統。TartBox 的 GUI 箱子 `display` 是真值。
- 為什麼沒改 limits.py：它在不能動的檔案清單裡（和 verdict、judge、score 那些一樣）。
- 做了：`pickfit verify --runner tart --display --limits-test` 現在直接拒絕，說明 macOS 還沒有畫面的檢查，改跑不加 `--display` 的 limits test。GUI 箱子的網路政策和 CLI 箱子一樣，每個 GUI 箱子開機時 `_check_firewall` 也會再檢查一次。`pickfit mac-host test` 不排這一步。
- 要補的（要能改 limits.py 時）：macOS GUI 箱子自己的檢查，例如 sbx 碰不到 VNC 的密碼與埠（日誌在主機上、0600）、`screencapture` 和輔助使用權限只給 pickfit 的 helper、sbx 不能結束 WindowServer 或 loginwindow。
- 11/18 中午念誠要求修這一項，交給一個 subagent 做（不改 limits.py，另寫 macOS 的畫面檢查模組，再接到 `verify --limits-test` 和 `mac-host test`）。做到一半被 Opus 5.5 的安全防護擋下（判成資安類工作），沒有留下任何檔案或改動：`verify/cli.py` 的拒絕還在，tart 和 mac-host 的 79 個測試照樣通過。這項仍然 open。要再做的話，可以由念誠申請 Anthropic 的 Cyber Verification Program，或自己寫這組檢查。
- 11/18 下午改用另一個 subagent 重做，這次做完了（`pickfit/verify/limits_mac.py`）。上面「直接拒絕」那一步已拿掉。
  - `limits_mac.py` 對 macOS GUI 箱子的角色和 `limits.py` 一樣。`run_gui_limits_test` 先把箱子包成 `display` 是 None 的樣子交給 `limits.run_limits_test`，limits.py 原有的 macOS 檢查照跑、一項沒少，只跳過 Xvfb 那組，接著再跑 GUI 箱子自己的 19 項。
  - 功能檢查 3 項。
    - `desktop_screenshot`：sbx 是 console 使用者，Dock 和 Finder 在跑，pickfit 在主機端經 VNC 截到整個 1280x800 的畫面。
    - `app_window_seen`：以 sbx 身分開 TextEdit，pickfit 自己的 helper 從 WindowServer 列出這個視窗，執行檔由核心查出，截圖裡那塊範圍也跟著變了。
    - `report_unforgeable`：照 Linux 的 `display_report_unforgeable` 寫。程式印出假的回報行、留一個 detach 的子行程，結果到不了 window，子行程也被收掉。回報來自 root helper 的輸出，用新的 nonce 對，程式自己的輸出只進 app 的 log。
  - 設定檢查 8 項，盡量唯讀。每項都配一個 `_control`，用設定不同的對象跑同一個判斷，必須判成不通過，這樣檢查看不到設定時會失敗，不會默默通過。
    - `sbx_standard_user`：sbx 不在 admin 和 wheel 群組。對照是 admin 帳號。
    - `helper_locked`：sbx 寫不了 pickfit 的 helper 和 helper 的目錄。對照是 sbx 自己的 app log 目錄，寫得了。
    - `vnc_log_owner_only`：VNC 的位址和密碼只在主機的 VM log 裡，檔案屬於主機帳號、權限 600。對照是主機的 /etc/hosts。
    - `vnc_password_not_in_guest`：root 掃 guest 的檔案、所有行程的命令列和環境變數，只把「四個小寫字以連字號相接」這種字串的雜湊傳回主機比對，密碼本身不進 guest。對照是在 sbx 的工作目錄放一個同形狀的誘餌，必須找得到。
    - `tcc_grants_scoped`：系統 TCC 資料庫的敏感權限只給 sbx 改不了、也冒充不了的程式。對照是複製一份資料庫、塞進兩筆這種權限，必須被抓出來。
    - `tcc_box_user_none`：sbx 自己裝的程式以 launchd job 啟動，就算 sbx 先在自己的 TCC.db 寫了授權，也拿不到螢幕錄製、輔助使用、輸入監控、PostEvent。照模型指令的方式跑的 osascript 也拿不到。對照是 pickfit 捲動用的 osascript job，有 PostEvent。
    - `window_server_not_box_user`：WindowServer 屬於 _windowserver，sbx 對它下 `kill -0` 被拒。對照是 sbx 對自己的 Dock 下同一個指令，可以。
    - `vnc_port_unreachable`：guest 以 root 連主機的 VNC 埠，online 和 offline 都是 exit 28。對照是放行 @host 時連得到。
  - 和原本列的不一樣的地方。loginwindow 由 macOS 設計就是以 console 使用者的身分跑（實測 uid 1001），「不屬於 sbx」不是箱子做得到的設定，所以只記下是誰的，判斷只看 WindowServer（uid 88）。sbx 結束 loginwindow 只會把自己登出，每次啟動的 watcher 在 sbx 的 session 不在畫面上時就判失敗。螢幕錄製的部分，pickfit 在 guest 裡沒有東西用得到（截圖是主機那端的 VNC，helper 列視窗不需要標題），所以檢查改成「沒有任何程式拿得到」。VNC 埠原本由 `_check_firewall` 在開機和每次切網路時檢查，但沒有正向對照，也不進 limits 結果，所以另加一項有對照的。
  - 實測發現並修掉的漏洞（`tart_box.py` 的 `TCC_SCOPE`）。來源映像的系統 TCC 資料庫把螢幕錄製、輔助使用、PostEvent 等權限給了 osascript、sshd-keygen-wrapper、bundle id `org.python.python`（沒有 code requirement，任何自稱這個 id 的 App 都算），還有 `/opt/homebrew/Cellar/tart-guest-agent/0.15.0/bin/tart-guest-agent`。最後這個路徑在屬於 sbx 的 /opt/homebrew 底下。在探索用的 VM 裡，sbx 把自己的程式放到這個路徑、以 launchd job 啟動，就拿到螢幕錄製、輔助使用、輸入監控和 PostEvent。映像關了 SIP，root 改得了資料庫，改完 tccd 馬上照新的內容判斷。GUI 箱子現在開機時（`_setup`，任何 sbx 的程式碼跑之前）刪掉這些權限，只留 osascript 的輔助使用和 PostEvent 給 `gui_mac.post_scroll` 用。CLI 箱子不動。
  - 接線：`pickfit verify --runner tart --display --limits-test` 改跑 `limits_mac.gui_limits_test`。`mac_host.plan_steps` 在 gui-base 後面加一步 gui-limits，GUI 基底已經建好時也照跑。
- 測試：`tests/test_verify_tart.py` 加了一個假的 GUI 箱子，照實測的輸出回答。設定正確時 19 項都過，改掉其中一項設定（密碼外洩、log 權限 644、TCC 有壞的授權、sbx 是 admin）就只有那一項不過，有一項跑不起來時記成失敗、其他照跑。另外拿實測的那批 TCC 權限驗 `TCC_SCOPE` 的 SQL，並在本機實際跑 TCC 分類和密碼掃描的腳本。`tests/test_mac_host.py` 原本測拒絕的那一個改成測新的行為（跑 limits_mac、不跑 Linux 的畫面檢查，有一項不過就 exit 1），plan 的步驟也一併更新。全部測試 2042 passed、4 skipped。
- 實測（scw1，主機 macOS 15.8.3，基底 pickfit-macos-15-gui，同時只開一台 VM，沒有模型費用）：
  - `pickfit verify --runner tart --display --limits-test` 52/52 通過，limits.py 的 33 項加上 GUI 的 19 項，花了 332 秒，結果在 `runs/verify/limits-tart-vz-20261118-133641.json`。
  - 之後的版本再跑一次 `pickfit mac-host test scw1`（只排免費的 limits 和 gui-limits），開機檢查通過，limits 33/33（`runs/verify/limits-tart-vz-20261118-133938.json`），gui-limits 52/52，331 秒（`runs/verify/limits-tart-vz-20261118-134511.json`）。各步的輸出在 `runs/mac-host/scw1-20261118-053730/`，跑完主機上沒有留下 VM。
- 還開著的：
  - sbx 也能把 `/usr/bin/osascript` 當 launchd job 啟動，拿到輔助使用、輸入監控和 PostEvent（實測）。影響範圍是 sbx 自己的桌面 session，pickfit 不會在裡面輸入任何秘密。要關掉得換掉捲動的做法。
  - Virtualization.framework 的 VNC 伺服器在主機上聽所有介面（實測 `*.61451`），不是只聽 loopback。guest 碰不到（softnet 擋 @host，實測 exit 28），但主機的公網 IP 擋不擋這些埠，要看 Scaleway 那邊的防火牆。VNC 的驗證只用密碼的前 8 個字元。
  - sbx 的 TCC.db 是 sbx 自己的檔案，SIP 關著時寫得進去。實測寫進去的螢幕錄製、輔助使用、輸入監控、PostEvent 授權不會生效。麥克風、相機、AppleEvents 這類使用者層級的權限，sbx 可以自己給自己，不過 VM 沒有麥克風和相機。
  - 密碼掃描涵蓋 `SCAN_ROOTS` 列的目錄、所有行程的命令列和環境變數，不含 unified log。
  - `limits_mac.py` 和 limits.py 一樣是決定箱子能不能用的檢查，`tart_box.py` 的 `TCC_SCOPE` 也是同一類。建議念誠把 `pickfit/verify/limits_mac.py` 加進 `scripts/loop_guard.py` 的 PROTECTED。guard 本身在保護清單裡，這次沒有改。

## H-015 [open] 官網送出的軟體只有 Linux 跑得動的會自動處理

- opened: 2026-11-18T12:06:00+08:00
- symptom: 官網的 `/submit` 和 MCP 的 `submit_software` 都把網址寫進 D1 的 `submissions`。`pickfit watch` 只拿 GitHub 的列，讀完就在 Linux 箱子驗。只支援 macOS 或 Windows 的軟體被 `not_in_box` 判成 Linux 跑不了，直接記成 listed_unverified。網站的送出（託管的 web app）一直停在 queued，沒有程式處理。`pickfit watch` 也沒有排程，要有人手動開。
- 做了（`pickfit/lanes.py`、`pickfit/verify/mac_batch.py`、`pickfit/watch.py`、`pickfit watch` 的參數）：
  - 分流：紀錄讀完後，依序看 Linux、Windows、macOS 的箱子跑不跑得動（`batch.not_in_box`），交給第一個。Linux 照舊當場驗。Windows 和 macOS 的工作先停著，D1 的列維持 `verifying`，原因以「Waiting for pickfit's」開頭，送出頁看得到，`requeue_stale` 也不會把它丟回佇列。紀錄留在 `runs/watch/<submission>/software/`，watch 重開後 slug 照樣保留。
  - Windows：每次開新的 EC2 Windows 箱子，AWS 有回應就跑。`aws login` 過期時這條先等，每 30 分鐘再試一次。
  - macOS 用批次跑。等的數量到 `--mac-batch`（預設 10），或最舊的等了 `--mac-max-wait-hours`（預設 24 小時）才開始。先找 `~/.pickfit/mac-hosts` 裡能用的主機（`mac-host check` 通過，缺基底或還沒跑過 limits test 就先補）。都沒有時，要加 `--mac-rent` 才會租新的，預設一週最多 1 台（`--mac-max-rentals`）。租到後裝 tart、softnet、拉映像，接著是要 sudo 密碼的 root 步驟。加了 `--mac-root-from-provider`，watch 會向 Scaleway 讀這台機器的密碼，直接從 stdin 餵給主機上的腳本，不記錄也不存檔。沒加的話，日誌和 `--status` 會寫要跑 `pickfit mac-host root NAME`，等人做完再用，也不會再租第二台。主機在手上時，新停下的 Mac 工作馬上跑，一次 2 個（Apple 的授權允許一台 Mac 同時跑兩個 macOS VM）。watch 自己租的主機，等付費的第一天過完、手上又沒有工作時刪掉。念誠自己加的主機（例如 scw1）不會刪。租用紀錄在 `~/.pickfit/mac-hosts/rentals.jsonl`。
  - 箱子沒開起來（box_error、model_error）算機器的問題，不算軟體的。工作重新停著，這條分流休息 30 分鐘。同一個工作連續 3 次都這樣，才記成 listed_unverified，原因寫沙盒沒開起來。
  - 網站的送出：交給 `pickfit/web_intake.py`（另一個 subagent 寫的，測試在 `tests/test_web_intake.py`）。規則和批次收錄網頁應用的一樣。只收公開的 https 網址（DNS 解出私有位址就拒絕，轉址後再查一次），再看 robots.txt、首頁、使用條款，由模型判斷是不是不用帳號就能免費試用的網頁應用，接著抽取、建 web_app 紀錄，最後在 Modal 的 VM 裡造訪一次。退件理由都是程式寫的固定句子，模型的文字不會進到理由裡。暫時的問題（robots.txt 或首頁 5xx、抽取失敗、VM 沒開起來）回佇列，試 3 次不成才退件，理由寫「this site」。網頁應用只造訪一次、沒有重播，所以造訪通過就算驗證通過（`watch.record_passed`）。最壞情況一個網站約 US$6.10，和一個 repository 的 US$6 差不多。要注意的有三件。第一，同一個可註冊網域只造訪一次，同網域的第二個 App 會記成 listed_unverified。第二，紀錄的來源會寫 `submission:<id>`，送出編號因此公開在紀錄裡。第三，靠 script 畫出來的頁面要有 playwright（`uv run --with playwright pickfit watch ...`），沒有時 watch 會提醒，那種網站會一直重試到退件。
  - `pickfit watch` 新參數：`--lanes`（預設 linux,windows,macos,web）、`--mac-batch`、`--mac-max-wait-hours`、`--mac-rent`、`--mac-max-rentals`、`--mac-provider`、`--mac-zone`、`--mac-root-from-provider`。`--status` 多印每條分流停著的工作、最舊的等了多久、批次到了沒，以及 Mac 主機和租用次數。
- 測試：`tests/test_watch_lanes.py`、`tests/test_mac_batch.py`，主機、供應商和 D1 都是假的。
- 11/18 下午念誠決定的三件：
  - 送出編號不公開。網站紀錄的來源改成 `submission`，不帶編號（`webrecords.build_web_record`）。watch 的 commit 訊息也拿掉編號，因為 repo 是公開的，推上去就看得到。之前的 commit 不動。送出的人照樣用編號查自己的進度。
  - 通過的紀錄自動發布。新的 `--publish push`：commit 後先翻好 zh-TW 的頁面句子，`git fetch` 加 rebase 到 `origin/main`，重新檢查一次，再推上去，由 main 的 CI 部署（和 `--publish`、`--publish deploy` 在本機部署的做法不同，不會和 CI 的部署互相蓋掉）。rebase 衝突就放棄，commit 留在本機等下次。D1 的狀態要等線上 Worker 的 data_sha256 和本機一致才改成 listed。推上去時若 main 帶來新的程式碼，或 `--update-check-hours` 到了、閒著時發現 main 有新程式碼，watch 不再接新工作，做完手上的就以 exit 75 結束，讓服務拉新版重開。
  - watch 不放在念誠的電腦上，放一台一直開著的 Linux 機器。`deploy/watch/` 有 `bootstrap.sh`（Ubuntu 24.04，下載的東西都對 SHA-256）、systemd 服務、環境變數名稱表和說明。比過的選項與價格在 `deploy/watch/README.md`，用 Scaleway DEV1-S（約 €9.5 一個月含 IPv4）：最便宜又夠用，離租來的 Mac mini 近，錄影的畫面不會 10 秒才一張，也不占 AWS 的 vCPU 配額。
- 11/18 12:30 唯讀看了一次真的佇列（`pickfit watch --status`）：5 個網站送出停在 queued（generatorbudget.com、routemux.com、jsonl.co、clockzone.net、carhistory.cc），換成新的 watch 就會由網站這條處理。parley 之前因為 Linux 箱子跑不了記成 listed_unverified，現在同樣的送出會停在 Windows 或 macOS 那條。gh-pull 通過驗證，等發布。Mac 這條認得 scw1，沒有停著的工作。
- 還沒做：
  - 放 watch 的機器 11/18 傍晚開好了：Scaleway `pickfit-watch`（DEV1-S，nl-ams-1，ID `8e33043a-25e8-4913-9833-48e0196c6da7`，IPv4 51.15.56.181）。經過是這樣：念誠先同意開 DEV1-S，在 fr-par-1 建立時 Scaleway 回 `quota exceeded for resources 'cp_servers_type_DEV1_S' (0/0)`。念誠接著同意改開 PLAY2-PICO，同樣回 0/0。查 IAM API 的 `/iam/v1alpha1/quota` 才知道，這個帳號在巴黎三個區所有一般機型的配額都是 0，阿姆斯特丹、米蘭、華沙、斯德哥爾摩才有。最後在 nl-ams-1 開了 DEV1-S，就是念誠一開始同意的那個價格，比 PLAY2-PICO 便宜，CPU 也多一個。前兩次失敗都沒有留下機器或 IP。念誠的 Scaleway 帳號有 €100 的試用額度，43 天內要用完。
  - `bootstrap.sh` 在這台上跑過了，第一次失敗兩處，都改好了。第一處是 playwright 自帶的 node 要 `libatomic1`，最小映像沒有，現在先用 apt 裝。第二處是 `install-deps` 原本以 root 在 pickfit 的 repo 裡 `uv run`，可能在 `.venv` 留下 root 擁有的檔案，改成在 `/` 用 `uvx`。另外加了一段：記憶體小於 4 GB 的機器開 2 GB swap。第二次跑完確認了這些：Node 24.22.3、uv 0.13.9、scw 2.66.0、wrangler 4.153.0；`pickfit --help` 可以跑；headless Chromium 開得起來；repo 檔案都屬於 pickfit。服務裝好了，但沒啟用也沒啟動，`/etc/pickfit/watch.env` 是空的。對外只開 22 埠，SSH 不收密碼。
  - 金鑰用 `deploy/watch/send_secrets.py` 送：念誠在 Mac 上跑一個指令，腳本從 `.env`、`~/.modal.toml`、`~/.config/scw/config.yaml` 拿已有的值，問 Cloudflare 和 GitHub 的 token，經 SSH 的 stdin 寫進機器的 `/etc/pickfit/watch.env`，再搬 `runs/watch/jobs/`、`runs/web/visits.jsonl`，最後啟動服務。測試（`tests/test_send_secrets.py`）只用假的設定檔和假的 ssh，確認值不出現在畫面和指令列。
  - 服務跑的是 main 上的程式，這個分支的 watch 程式還沒併進 main，所以機器開好也要等合併後才能啟動（腳本會先檢查，main 沒有就只放金鑰和狀態）。
  - watch 自己租的 Mac 只有 watch 在跑時才會被刪。watch 停掉時，主機過了 24 小時會按小時繼續計費，要手動 `pickfit mac-host down NAME --yes`。
  - macOS GUI 箱子的 limits test 11/18 下午補上了（H-014，scw1 上 52/52），Mac 批次在用一台新主機前會跟著 `plan_steps` 的 gui-limits 一起跑。
  - 還沒用真的 D1、真的主機整條跑過。
- 11/18 晚上第一次在 watch 機器上跑完整的端到端測試（`systemctl start pickfit-e2e@all`，run `e2e-20261118-185431-15b1`）。五個測試網址照一般人的方式從官網表單和 MCP 送進 D1：
  - reject（sindresorhus/awesome，經 MCP）：約 1 分鐘退件，理由是 non_software，符合預期。
  - linux（sharkdp/hexyl）：約 2 分鐘，Modal 箱子驗證加重播都通過，判成 verified (function)，紀錄只留在 `runs/e2e/<run>/records`。模型約 US$0.27。
  - windows（lptstr/winfetch）：在 EC2 台北開箱子，約 5 分鐘通過。用的是 watch 自己的 IAM 使用者 `pickfit-watch`，所以 `aws-watch-policy.json` 的權限夠用。模型約 US$0.31。
  - web（demo.playwright.dev/todomvc）：沒過，但錯的是測試網址。篩選判它是網頁應用，抽取卻讀成 `demo_prototype`，因為頁面自己寫著「This is just a demo of TodoMVC for testing」，pickfit 不收是對的。備用的 todomvc.com 範例頁也是示範用。兩個都換成真的開源網頁應用：regexr.com，備用 dillinger.io。兩個都不用帳號、pickfit 還沒收錄，pickfit 自己的 robots.txt 和使用條款檢查也都通過。同一批查過的還有 tldraw.com（robots.txt 不允許）和 jsoncrack.com（條款禁止自動存取），都不能用。改完推上 main，21:09 單獨重跑 web（`pickfit-e2e@web`，run `e2e-20261118-210901-e6da`）：regexr.com 在 microVM 裡操作 7 次，判成 verified (function)，約 3 分鐘，模型約 US$0.39。
  - macos（rgcr/m-cli）：卡住了。e2e 的工作讓這條馬上開始（「an end-to-end test is waiting」），但每 30 分鐘 scw1 的 base 步驟都以 exit 1 失敗：`base VM 'pickfit-macos-15' already exists`。原因是 `send_secrets.py` 只搬了 `~/.pickfit/mac-hosts` 和 SSH 金鑰，沒搬 `~/.pickfit/tart/hosts/<主機>/` 裡 base VM 的 manifest。`mac-host check` 要 VM 和 manifest 都在才算 base 建好，所以 watch 以為沒有 base，去重建，又因為 VM 已存在而失敗。已把 scw1 的兩個 manifest（裡面只有映像和工具的版本，沒有機密）搬到機器上，`send_secrets.py` 之後也會一起搬，測試在 `tests/test_send_secrets.py`。搬完後 13:03 UTC 那一輪就跳過 base，limits 和 gui-limits 分別 96 秒、191 秒通過，m-cli 在 scw1 上用 Homebrew 裝好、跑了 3 個指令、重播也過，判成 verified (function)。驗證本身約 2 分鐘，模型約 US$0.18。從送出到通過共 2 小時 7 分，幾乎都是卡在 base 的時間。
  - 發布那一段：workers.dev 的 data_sha256 和 origin/main 一致，CI 部署正常。pickfit.app 還是舊的資料，因為它從 11/18 起由 Cloud Run 提供，CI 只部署 workers.dev 的 Worker。watch 自動推上去的 jsonl-co、generator-budget 因此一直停在 ready，D1 要等 pickfit.app 也更新才會改成 listed。兩次報告的整體結果都是 FAILED，就是因為這一段。
  - 合計：五條分流都通過過一次，發布那一段要等 pickfit.app 跟著 main 部署。五條的模型費加起來約 US$1.2（reject 幾乎不花錢，default 三條約 US$0.7）。測試網址的 D1 列跑完都刪了，五筆紀錄只留在兩次 run 的 `records/`，data/software 沒有多任何東西。
