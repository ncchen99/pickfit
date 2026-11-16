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
- tried: 11/1 試過 MIT 授權的 cua-driver 取元件編號清單（brief 2.1 節）。
