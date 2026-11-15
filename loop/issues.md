# Harness issues

pickfit 的驗證環境自己的問題。每一段的標題列由 `scripts/loop_state.py` 管（`issue-new`、`issue-status`），不要手改。標題下面的內容是 loop session 的筆記，隨時補。狀態：`open` 還沒人動、`fixing` 正在修、`fixed` 修好了（等它的項目會自動排回佇列）、`parked` 試過幾種做法都不行、`review` 要改到受保護的檔案，等念誠看 `loop/proposals/`。

## H-001 [open] 紀錄不能只靠自己重驗：verify --batch 要本機 pipeline.db 裡有抽取結果

- opened: 2026-11-15T23:33:07+08:00
- symptom: `pickfit verify --batch` 的候選來自 `runs/pipeline.db` 的 `extractions` 表。1,058 筆紀錄裡只有 185 筆在本機的 pipeline.db 有可用的抽取結果（11/15 查），其餘是別台機器、別的 worktree 或 `pickfit watch` 寫進來的。佇列裡 43 筆卡在沙盒限制的紀錄，只有 7 筆選得到。
- reproduce: `uv run pickfit verify --batch 1 --repo paragontasx/ferro --force --runner modal --dry-run` 印出 `0 to verify · 0 set aside`。
- 陷阱：`--records` 和 `--repo` 是聯集，不是交集。`--records --repo paragontasx/ferro` 會選到別款（那次選到 patient-zero）。重驗單一筆時不要加 `--records`，而且一定先 `--dry-run`，確認清單上只有目標那一款。
- 方向（還沒試）：讓 `verify` 能從 `data/software/<slug>.json` 自己組出 `VerifyTask`（紀錄裡有 repo、安裝方式、功能清單），或補一個只對單一 repo 重跑抽取的入口。`pickfit reverify` 與 `scripts/rereplay.py` 已經會從紀錄重播，先看能不能沿用。
- tried:

## H-002 [open] 沙盒映像沒有編譯器與 Rust、Go 工具鏈

reason: needs_toolchain

- opened: 2026-11-15T23:33:07+08:00
- symptom: 15 筆紀錄停在 `needs_toolchain`。映像是 `python:3.12-slim` 加少量套件（`pickfit/verify/sandbox.Dockerfile`），沒有 gcc、cargo、go，只能從原始碼建置的工具裝不起來。
- reproduce: 佇列裡 note 是 `needs_toolchain` 的任一筆。
- 方向（還沒試）：`modal_box.image_layers` 已經會依箱子種類（vm、gui、audio）在基底映像上加 apt 套件，可以照樣加一種帶工具鏈的箱子，只在安裝方式需要建置時用。使用者照安裝指南做的時候也得自己有工具鏈，這要寫進紀錄的 `prerequisites`，不能讓人以為不用。
- tried:

## H-003 [open] 沙盒使用者沒有 root，裝不了系統套件

reason: needs_root

- opened: 2026-11-15T23:33:07+08:00
- symptom: 17 筆紀錄停在 `needs_root`：安裝步驟要 `sudo apt-get install`、要 systemd，或缺某個共用函式庫（`failure.py` 的 `needs_root` 規則）。
- reproduce: 佇列裡 note 是 `needs_root` 的任一筆。
- 限制：箱子裡 root 是 pickfit 自己蒐證用的身分，被測的軟體不能拿到 root（`limits.py` 的檢查要照樣通過）。
- 方向（還沒試）：把「裝發行版套件庫裡的具名套件」做成 harness 代為執行的一步（由 pickfit 以 root 跑 `apt-get install <名稱>`，不是把 root 交給箱子使用者），並記進安裝步驟。要 systemd 或核心模組的另外分出來，那些多半要 `--runtime vm` 或真的做不到。
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
- tried: 11/1 試過 MIT 授權的 cua-driver 取元件編號清單（brief 2.1 節）。11/16 做完 Linux 這半的執行端，模型端先擴充 pickfit 自己的動作格式（分支 `claude/sad-cori-9f0919`）：
  - 執行端：display uid 的 hands（`gui_operate._HANDS`）改照 computer-use-demo 執行器（`ComputerToolset20260801`）的 xdotool 指令序列。`computer_toolset_20260801` 的 17 個成員做了 16 個：左中右鍵、雙擊、三擊、按住修飾鍵點擊、拖曳、按下與放開、移動、四個方向的捲動加格數、打字、組合鍵加重複次數、按住某鍵、放大、等待，截圖就是每一步原本那張。沒做的是 `cursor_position`，游標在哪 pickfit 自己知道。授權 MIT，釘在 claude-quickstarts `4a4224bd`（`computer.py` 最後一次改在 `5264b729`，就是加上 toolset 那次），記在 `NOTICE`。
  - 沒有整份照搬。上游組的是 shell 字串，點擊時按住的修飾鍵沒加引號，xdotool 本身又能用 `exec` 串指令，所以 pickfit 傳 argv，按鍵與修飾鍵先過自己的白名單。拖曳在按下與放開之間分 12 步移動，上游是直接跳到終點。放大在主機上裁那一步的截圖，不進箱子。一步做到一半失敗時，按住的鍵和滑鼠鍵會放開。操作結束時滑鼠鍵還按著的話，等 App 停掉後放開。
  - 模型端：`pickfit/anthropic_messages.py` 還沒進 `main`，所以照指示擴充 pickfit 的動作格式。`OperatorAction` 多了 drag、move、mouse_down、mouse_up、hold_key、zoom 六種動作，和 x2、y2、hold、repeat、amount 五個欄位。Mac 的 schema 和提示逐字比對過沒變（`BasicOperatorAction`）。
  - 紀錄格式只加不改：舊的 click、type、key、scroll、wait 照原樣重播，沒寫 amount 的 scroll 照舊捲 3 格。zoom 不寫進重播清單。
  - 驗收：單元測試全過，新增的 28 個在 `tests/test_verify_gui_toolset.py`，hands 接一個假的 xdotool 真的跑一遍，記下的 argv 逐一對照上游的指令序列。`--limits-test --runner modal --display` 31/31。LibreSprite 那次 Modal 紀錄（`verify-libresprite-20261104-191755-508f`，四個 GUI 操作）用 `scripts/rereplay.py` 在新箱子重播，五個檢查照舊通過，離線也過，四個操作都靠舊的紀錄動作完成，沒有退回模型。拖曳的示範是 `scripts/probe_gui_drag.py`，在 Chromium 裡放一個 HTML 拖放和一個用指標事件做的滑桿，拖到位才會下載一個含 nonce 的檔案，由 pickfit 自己找檔案驗收。兩種都通過，只點一下的對照組都沒過，換新箱子照紀錄重播也都通過（證據在主 checkout 的 `runs/probe-gui-drag/20261116-002046/`）。
  - 花費：Modal 約 US$0.047（limits test 約 US$0.005、LibreSprite 重播 US$0.030、拖曳 probe 兩次共 US$0.013）。模型 US$0，三次 Baseten 呼叫都回 400，沒有計費。
  - 卡住的：Baseten 上 Muse Spark Open 的部署從 11/16 00:15 起回 400「Model version wpgy40e is deactivated」，11/15 23:23 還正常。GUI operator 現在叫不動，所以拖曳示範用的是照顏色算出位置的紀錄動作，沒有讓模型從目標自己選 drag。新的動作格式還沒在真的模型上試過。
- 下一步：
  - toolset 接線：`anthropic_messages.py` 合進 `main` 後，operator 是 Claude 時送 `{"type": "computer_toolset_20260801"}`。每個 tool_use（成員名稱加輸入）照 `gui_operate.py` 開頭那張對照表轉成 pickfit 的動作，一樣先過 `to_action` 的檢查才執行。座標是模型看到的那張圖的像素，要用那一輪的 `View` 換回螢幕座標。tool_result 要帶 `toolset_name: "computer"` 和下一張截圖。done 與 give_up 另外給一個工具。驗收方式不變。
  - 拖曳的起點也可以像點擊一樣再對準一次（`aim`），現在只有點擊會。
  - macOS 照原計畫換成 cua-driver，經 `tart exec` 呼叫。
