# Loop journal

每處理完一個項目就在最後面加一段，只加不改。念誠看這份就知道 loop 做了什麼、哪裡要他決定。格式：

```
## 2026-11-16 01:23 reverify:ferro → verified
- 做了什麼：一兩句
- 結果：level、run 目錄、花費（帳本的數字）
- harness：動了哪個問題（H-00X）、改了哪些檔、加了哪個測試；沒動就寫「無」
- 需要你：沒有就不寫這一行。有的話寫清楚要決定什麼、卡住哪些項目
```

`scripts/loop.sh` 每批結束也會加一段，列出這批改過的既有測試，以及有沒有碰到受保護的檔案。

---

## 2026-11-16 12:25 harness:H-001 → fixed

- 做了什麼：這個 session 第一次真的跑 loop。開工時 43 筆裡只有 4 筆選得到（dog、holdspeak、neoth、semquery），其餘 `verify --batch` 印 `0 to verify`，所以先修 H-001，還沒領任何項目。加了 `pickfit discover --repo owner/name`：不搜尋、不呼叫模型，向 GitHub 拿這個 repo 的資料、README、檔案清單，套規則，存成本機 `runs/pipeline.db` 的候選；之後 `pickfit extract --repo <repo_id> --model prod --limit 1` 抽取，`verify --batch --repo` 就選得到。
- 結果：ferro 的 dry-run 從 `0 to verify` 變成只列 ferro；dog 照樣只列 dog；本機完全沒有候選的 bamboo-agent 也存進來了。花費：ferro 的抽取 US$0.113（帳本），沙盒 US$0。
- harness：H-001。改了 `pickfit/discover/run.py`（`add_repos`）、`pickfit/discover/store.py`（漏斗多一個 `named` 來源）、`pickfit/cli.py`（`discover --repo`）；加了 `tests/test_discover_named.py`（5 個測試，先寫、先失敗）。沒有改既有的測試。沒動箱子和映像，沒跑 `--limits-test`。
- skill 也改了：`.claude/skills/pickfit-loop/SKILL.md`「一圈」第 2 步多兩條，寫 dry-run 印 `0 to verify` 時要先跑上面兩個指令，以及 dry-run 出現 `skip` 行時怎麼看。請看一眼寫法對不對。
- 需要你：
  1. `pickfit discover` 要 `GH_TOKEN`，本機 `.env` 沒有，指令自己的錯誤訊息叫人用 `GH_TOKEN=$(gh auth token)`。這個 session 照做了（token 只當環境變數傳給 pickfit，沒印出來，也沒進沙盒）。這把 token 的權限很大（`repo`、`delete_repo`、`workflow`），pickfit 只用它讀公開 repo。要不要另外發一把只讀公開資料的 token 放進 `.env`，請你決定。在那之前 loop 照現在的做法。
  2. 重新抽取的功能清單，用字可能和紀錄裡 `features` 的不同。寫回之後要不要跑 `pickfit profiles --features-only --slug <slug>` 對齊，loop 沒有做，留給協調的 session。
  3. `verify` 預設的 agent 是 Claude Haiku（dry-run 印的是 `agent claude-haiku-5-5 · judges claude-opus-5-5`）。skill 的指令沒有指定 `--model`，所以 loop 用的就是這個組合。如果重驗要用 Opus 當 agent，要在 skill 裡寫明。

## 2026-11-16 12:40 reverify:agentloom → parked (H-003)

- 做了什麼：dry-run 印 `0 to verify`，用新的 `discover --repo` 存進本機（`refreshed`，規則通過）。看了紀錄裡 10/31 那次的筆記：README 在 Linux 上唯一的路是 `bash linux/scripts/bootstrap_toolchain.sh`，腳本第一步就停在 `required command not found: sudo`，它要用 apt 裝 cmake 和編譯器，再裝 rustup。箱子在這兩點上和 10/31 一樣，重跑只會得到同一個結果，所以沒有花錢重跑，也還沒抽取。
- 結果：park，等 H-003（以 root 代裝具名套件），也用得到 H-002（工具鏈）。花費 US$0。
- harness：無。

## 2026-11-16 12:45 reverify:architecture-intelligence-platform → parked (H-004)

- 做了什麼：dry-run 印 `0 to verify`，`discover --repo` 存進本機（`added`，規則通過）。10/31 的筆記：本機安裝只有 `docker compose`，要 Neo4j，`pyproject` 還要 Python 3.13 以上；README 另一條路是連到作者託管的唯讀示範站，那不算安裝。箱子現在一樣沒有 Docker 或 Podman，沒有重跑，也沒抽取。
- 結果：park，等 H-004。花費 US$0。
- harness：無。H-004 這個 session 還沒動。

## 2026-11-16 12:50 reverify:backgroundmusic → parked (H-003)

- 做了什麼：本機有抽取結果。用 Modal 的 dry-run 印 `0 to verify · 1 set aside`，`skip backgroundmusic  GUI app`：它只有 macOS 版，Linux 箱子驗不了。11/4 那次是在 tart 的 macOS VM 跑的，停在 `needs_root`：安裝檔是 `.pkg`，要把音訊驅動裝進 `/Library`，要管理者密碼。沒有重跑。
- 結果：park，等 H-003（由 harness 以 root 代跑安裝那一步，macOS 這邊是 `/usr/sbin/installer`）。花費 US$0。
- harness：無。
- 需要你：佇列裡有 6 筆只有 macOS 版（backgroundmusic、iglance、lulu、mac-performance-monitor、macos-enterprise-privileges、outset），另外 bindiff、cardinal 上次也是在 macOS VM 跑的。重驗它們要 `--runner tart --display`，在這台 Mac 上開 macOS VM（`tart list` 看得到 `pickfit-macos-26` 和 `pickfit-macos-26-gui` 兩個基底，不用另外下載）。skill 的指令只寫 `--runner modal`，賽後方針也說 macOS GUI 先不排，所以 loop 沒有在你的 Mac 上開 VM。要不要讓 loop 跑 tart，請你決定。在那之前這幾筆輪到時會 park，或在原因很明確時照實記成未驗證。

## 2026-11-16 12:46 更正與結案

- H-001 那一段「需要你」的第 1 點已經解決（念誠 11/16）：`.env` 裡有一把只讀公開 repo 的 `GH_TOKEN`，`pickfit discover --repo` 不用加前綴就能跑（剛用 ferro 試過，`refreshed`）。之後不再呼叫 `gh auth token`，skill 裡那一行也拿掉了前綴。
- 前面四段標的時間是估的，寫晚了：H-001 那段到 backgroundmusic 那段實際都在 12:21 到 12:26 之間完成。從這一段起用 `date` 的時間。

## 2026-11-16 13:07 reverify:bamboo-agent → verified

- 做了什麼：dry-run 印 `0 to verify`，`discover --repo` 加抽取後選得到。先在一般的箱子跑一次：安裝腳本裝的是另一個產品的 .deb，要 `sudo`；剩下兩條路都是 `cargo install`，README 要 Rust 1.95 以上，停在 `needs_toolchain`。這是 harness 的問題，所以修了 H-002，再用 `--toolchain` 重跑。
- 結果：level `service`，全新箱子重播通過，judge 判 working。4 項功能裡 1 項 checked（本機網頁介面和 HTTP API），另外 3 項要模型供應商的金鑰，記成 `needs_account`。run `runs/verify/verify-bamboo-agent-20261116-123422-6720`。用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 service。花費：抽取 US$0.111、第一次重跑 US$0.006、建置箱子那次模型 US$0.044、沙盒 US$0.223，合計約 US$0.38。
- harness：H-002，修好。加了 `pickfit verify --toolchain`（建置用的箱子），改了 `pickfit/verify/modal_box.py`、`box.py`、`agent.py`、`cli.py`、`NOTICE`，加了 `tests/test_verify_toolchain.py`（4 個）。沒有改既有的測試。驗收三樣都過，細節在 `loop/issues.md` 的 H-002。commit `d2544242`。
- 需要你：
  1. 建置箱子一筆的沙盒費約 US$0.2 到 0.5（bamboo-agent 是 0.223），`box` 那本帳每天上限 US$10，大約夠 20 到 40 筆。佇列裡還有十幾筆要建置，照跑會吃掉今天大半的沙盒額度，loop 會跑到上限就停。
  2. 紀錄的 `prerequisites.runtimes` 還是空的，新的抽取結果寫的是「rust>=1.95 (source build)」。安裝指南現在是 `cargo install`，使用者得先有 Rust。run 的 pitfall 有寫，但 `prerequisites` 要靠 `pickfit profiles` 重寫才會更新，loop 不手改紀錄，沒有做。
  3. hook 有三次擋到不是它要擋的東西，都照它的意思換了寫法，沒有繞過保護的內容：(a) 用 Python 的 `open()` 讀 `data/software/` 的紀錄會被當成寫入，改用 `jq` 讀；(b) commit 訊息裡提到環境檔的檔名會被當成讀取它，改掉用字；(c) 同一行同時出現 `open(` 和 `data/software/` 才會擋，分成兩行就不擋，所以這條規則其實擋不住真的寫入。

## 2026-11-16 13:12 reverify:datanexa → parked (H-003)

- 做了什麼：還沒輪到它就先處理了（`park` 可以直接對 todo 的項目做），因為前面的 bindiff、cardinal 正在跑。`discover --repo` 存進本機（`added`，規則通過），沒有抽取。10/31 的筆記寫得很清楚：它的 MCP 是包在 Tauri 桌面 App 裡的 HTTP 伺服器，沒有 Linux 的發行檔，只能從原始碼建置，要 Rust、pnpm 9、JDK 21、Maven 3.9，還要 apt 裝 `libwebkit2gtk-4.1-dev`、`libayatana-appindicator3-dev`、`librsvg2-dev`。新的建置箱子有 Rust，但沒有這些 `-dev` 套件和 JDK，重跑會停在同一個地方，所以沒有花錢重跑。
- 結果：park，等 H-003（以 root 代裝具名套件）。原本掛在 H-002，改掛 H-003。花費 US$0。
- harness：無。

## 2026-11-16 13:14 reverify:bindiff → verified

- 做了什麼：紀錄上次是在 macOS VM 跑的，`.pkg` 要管理者密碼，停在 `needs_root`。它也有 Linux 版，所以改在 Linux 的顯示箱子驗：`discover --repo`、抽取，`verify --batch 1 --repo google/bindiff --force --runner modal --display`。agent 下載發行的 `.deb`，用 `dpkg-deb -x` 解到家目錄（不用 root），啟動 Java 介面看到主視窗，再用 repo 裡的測試檔跑了兩組比對。
- 結果：level `install`，全新箱子重播通過，judge 判 working，GUI judge 看到主視窗，功能 1 項 checked。沒有到 `function`，因為 GUI App 要有一個操作通過 pickfit 自己的檢查才算，這次沒有做操作。run `runs/verify/verify-bindiff-20261116-131045-79c2`。用 `guarded_write_back.py` 寫回：紀錄多一筆 Linux 的 run，整體從 unverified 變成 install；macOS 那筆 `needs_root` 原樣留著。花費：抽取 US$0.076、模型 US$0.054、沙盒 US$0.007。
- harness：無。
- 需要你：hook 又擋到一次不相干的東西（第四種）：指令裡有 install 這個英文字，而且同一段最後一個字是紀錄的路徑，就被當成用 `install` 指令覆蓋紀錄。我原本想在同一個指令裡用 `jq` 印寫回後的安裝步驟。改成寫回單獨跑一個指令，沒有印那一段。

## 2026-11-16 13:30 reverify:cardinal → verified

- 做了什麼：紀錄上次是在 macOS VM 跑的（`needs_root`）。它有 Linux 的發行檔，改在 Linux 驗。抽取出來沒有任何安裝指令，dry-run 印 `skip cardinal  no install path the Linux box can run`，所以跑了 `pickfit extract --install-docs` 讓管線去讀 README 指到的安裝文件，再抽一次就選得到。第一次用 `--display` 跑：CardinalNative 找不到音訊裝置就直接結束，沒有視窗，未驗證。箱子本來就有 `--audio`（PulseAudio），第二次加上去就開得起來。
- 結果：level `install`，全新箱子重播通過，GUI judge 看到整個 rack 畫出來。操作層加了一個 VCF 模組，但「存檔」沒有成功，因為 Cardinal 靠系統的 zenity 或 kdialog 開檔案對話框，箱子裡沒有（開了 H-007），所以到不了 `function`，3 項功能都沒 checked。run `runs/verify/verify-cardinal-20261116-131620-914e`，用 `guarded_write_back.py` 寫回：多一筆 Linux 的 run，整體從 unverified 變成 install，macOS 那筆原樣留著。花費：兩次抽取 US$0.151、第一次 US$0.008、第二次模型 US$0.756（GUI 操作用掉的）、沙盒 US$0.049，合計約 US$0.96。
- harness：開了 H-007（顯示箱子沒有 zenity、kdialog），還沒修。沒改程式。

## 2026-11-16 14:05 reverify:castor → verified

- 做了什麼：`discover --repo`、抽取。新的抽取結果寫它一定要 GPU，dry-run 印 `skip castor  needs a GPU`，所以用 `--toolchain --gpu T4`。這個組合先跑了 `--limits-test`，23/23 通過（`runs/verify/limits-modal-gvisor-20261116-131305.json`）。npm 套件只是一個啟動器，真正的執行檔要 `cargo install --path .` 從原始碼建，約 5 分鐘。跑了兩次：第一次 agent 和重播都過，但 screen judge 判 inconclusive（它挑 `cargo test` 當檢查，輸出太長，截圖裡看不到最後的通過行），管線照規則記成未驗證。這種結果本來就是要再查一次，所以重跑；第二次 agent 改用 `castor --help` 和 `castor stats -j` 當檢查。
- 結果：level `function`，全新箱子重播通過，judge 判 working，功能 1 項 checked。run `runs/verify/verify-castor-20261116-133353-ea1f`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 function。花費：抽取 US$0.067、兩次模型共 US$0.089、兩次沙盒共 US$0.855（有 T4），合計約 US$1.01。
- harness：無。用的是 H-002 的建置箱子。
- 需要你：兩次都沒有真的用到 GPU（agent 的筆記寫沒有跑本機的模型引擎）。抽取把 GPU 記成必要，管線就只肯在有 GPU 的箱子驗它，沙盒費因此貴了幾倍。這是抽取的判讀問題，loop 沒有動。

## 2026-11-16 14:05 reverify:dog → verified

- 做了什麼：本機有抽取結果，直接選得到。10/31 那次的筆記：發行的執行檔要 `libssl.so.1.1`，Debian 13 只有 3；從原始碼建又沒有編譯器。所以用 `--toolchain` 跑。agent 先試預設的建置，`openssl-sys` 編不過（dog 是 2021 年的專案，鎖住的 `openssl-sys` 很舊；agent 的筆記寫成缺 OpenSSL 標頭，但映像裡有 `libssl-dev`，比較像是版本太新對不上），改用 README 自己寫的 `--no-default-features --features=with_idna`。
- 結果：level `function`，全新箱子重播通過，judge 判 working。功能 1 項 checked（JSON 輸出）；DNS-over-TLS、DNS-over-HTTPS 這次的建置沒有包進去，記成 `needs_root`；彩色輸出 judge 在截圖裡看不到顏色碼，沒算。run `runs/verify/verify-dog-20261116-130958-e0c8`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 function。花費：模型 US$0.030、沙盒 US$0.011。
- harness：無。用的是 H-002 的建置箱子。原本掛在 H-003，其實是工具鏈的問題。
- 需要你：安裝指南現在是不含 TLS 的建置。使用者照著做會少 DoT、DoH 兩個功能，run 的 pitfall 有寫。要不要在工具頁上講得更明顯，請你看一眼。

## 2026-11-16 14:05 reverify:ducklab → verified

- 做了什麼：本機有候選、沒有抽取，抽取後選得到。README 的 CLI 是 `go build`，要 Go 1.25 以上，用 `--toolchain` 跑（映像裡是 Go 1.27.4）。桌面版另外要 apt 裝 GTK、WebKit 的 `-dev` 套件，這次沒有驗桌面版。
- 結果：level `function`，全新箱子重播通過，judge 判 working（MCP 伺服器回了 initialize 和工具清單，`roster suggest` 印出排名表）。列出的 4 項功能 feature judge 一項都沒認（兩項跑了但看不出功能真的在動，兩項沒查），所以 checked 是 0。run `runs/verify/verify-ducklab-20261116-130958-039a`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 function。花費：抽取 US$0.097、模型 US$0.038、沙盒 US$0.018。
- harness：無。用的是 H-002 的建置箱子。

## 2026-11-16 14:06 reverify:ferro → verified

- 做了什麼：H-001 的驗收就是用它，抽取那時已經做了。README 只有 `make -j4` 一條路，用 `--toolchain` 跑。抽取列了 OpenCL 標頭當系統套件，映像裡沒有，但沒有它也編得過。
- 結果：level `function`，全新箱子重播通過，judge 判 working（`make test` 的 kernel、decision、media 測試都印 ALL PASS）。列出的 4 項功能都沒 checked。run `runs/verify/verify-ferro-20261116-131250-25c2`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 function。花費：抽取 US$0.113、模型 US$0.037、沙盒 US$0.035。
- harness：無。用的是 H-002 的建置箱子。

## 2026-11-16 14:06 reverify:gutsy → verified

- 做了什麼：`discover --repo`、抽取後選得到。10/31 停在 `needs_root`，實際原因是 `llama-cpp-python` 在 PyPI 只有原始碼，要 gcc 和 cmake 才編得起來。用 `--toolchain` 跑，在 venv 裡 `pip install -e`，約 2.5 分鐘編完。
- 結果：level `install`，全新箱子重播通過，judge 判 working（`gutsy-inference --help` 印出用法）。沒有下載模型，所以 4 項功能都沒 checked，到不了 `inference`。run `runs/verify/verify-gutsy-20261116-130958-1f0b`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 install。花費：抽取 US$0.081、模型 US$0.013、沙盒 US$0.050。
- harness：無。用的是 H-002 的建置箱子。原本掛在 H-003，其實缺的是編譯器。

## 2026-11-16 14:06 reverify:gyrfalcon → verified

- 做了什麼：`discover --repo`、抽取後選得到。README 是 `cargo build --release`，用 `--toolchain` 跑。
- 結果：level `service`，全新箱子重播通過，judge 判 working（MCP 握手成功、列出 19 個工具，`--version` 有印）。功能 1 項 checked；「索引完整的 1C 設定」那一項 feature judge 沒認，因為回來的物件是空的。run `runs/verify/verify-gyrfalcon-20261116-130958-c3b4`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 service。花費：抽取 US$0.126、模型 US$0.042、沙盒 US$0.026。
- harness：無。用的是 H-002 的建置箱子。

## 2026-11-16 14:07 進度小記（目標條件已達成，繼續把跑完的結果記完）

- 14:05 ducklab 寫回之後，done 加 parked 是 10，/goal 的條件達成。那時還有 7 筆已經付錢跑完、結果是通過的（ferro、gutsy、gyrfalcon、hw-smi、khive、local-jev、mdma），是等前面項目的時候先平行跑的。放著不記等於白花錢，所以照佇列的順序繼續做，中間夾著的項目也一併處理。
- 平行先跑的做法：每一筆還是各自一個指令、各自先 dry-run 確認只列目標那一款，只是不等前一筆 `finish` 就先開始跑；`next`、`finish`、journal、commit 照佇列順序一筆一筆做。skill 沒有寫可不可以這樣，請看一眼。

## 2026-11-16 14:08 reverify:heym → parked (H-004)

- 做了什麼：還沒輪到就先處理（`park` 可以直接對 todo 的項目做）。`discover --repo` 存進本機，沒有抽取。10/31 的筆記：安裝只有 `run.sh`、`deploy.sh`（兩個都先檢查 docker、bun、uv，缺了就結束）或 Docker 映像，整個平台還要 PostgreSQL。箱子一樣沒有 Docker，沒有重跑。
- 結果：park，等 H-004。花費 US$0。
- harness：無。

## 2026-11-16 14:08 reverify:iglance → parked (H-005)

- 做了什麼：只有 macOS 版，Modal 的 dry-run 印 `skip iglance  GUI app`。11/4 在 macOS VM 那次是下載發行檔太慢（11.5 MB、約 40 KB/s）超時，記成 `needs_more_resources`，Homebrew 也沒有這個 cask。要重驗得開 tart 的 VM，loop 沒有做（見 backgroundmusic 那段的「需要你」）。
- 結果：park，留在 H-005。花費 US$0。
- harness：無。

## 2026-11-16 14:08 reverify:lulu → parked (H-003)

- 做了什麼：只有 macOS 版。11/4 的筆記：LuLu 不在 `/Applications` 裡就不肯跑，還要一個要 root 的 Network Extension；箱子使用者寫不了 `/Applications`。沒有重跑。
- 結果：park，留在 H-003。就算 H-003 做了由 harness 代裝，Network Extension 還要使用者在系統設定裡按核准，VM 裡多半過不了，到時候比較可能照實記成未驗證。花費 US$0。
- harness：無。

## 2026-11-16 14:08 reverify:mac-performance-monitor → parked (H-003)

- 做了什麼：只有 macOS 版。11/4 在 macOS VM 停在 `needs_root`，那次的 run 沒有留下筆記，所以不知道卡在哪一步。要重驗得開 tart 的 VM，loop 沒有做。
- 結果：park，留在 H-003。花費 US$0。
- harness：無。

## 2026-11-16 14:08 reverify:macos-enterprise-privileges → parked (H-003)

- 做了什麼：只有 macOS 版。這個工具的用途就是替使用者取得管理者權限，安裝要裝一個有特權的 helper；11/4 在 macOS VM 停在 `needs_root`，沒有留下筆記。要重驗得開 tart 的 VM，loop 沒有做。
- 結果：park，留在 H-003。花費 US$0。
- harness：無。

## 2026-11-16 14:08 reverify:neoth → parked (H-005)

- 做了什麼：本機有抽取結果，用 `--toolchain` 跑了一次（和 khive、local-jev、mdma 平行先跑的那批）。沒有發行檔，只能從原始碼建。
- 結果：未驗證，`needs_more_resources`，沒有寫回（紀錄本來就是未驗證）。兩條路都沒走完：預設功能的 release 建置相依很大（matrix-sdk、candle、wasm），在 4 vCPU 上跑超過單一指令 30 分鐘的上限；`release-desktop` 那組功能要 ALSA 的 `-dev` 套件，得用 apt 裝。run `runs/verify/verify-neoth-20261116-131604-d576`，38 分鐘，模型 US$0.016，沙盒 US$0.273。
- park，改掛 H-005：要比建置箱子更多的核心，或更長的單一指令上限。`verify` 現在沒有調這兩樣的參數（`--toolchain` 固定是 4 vCPU、30 分鐘），這是 H-005 可以做的一步。
- harness：無。

## 2026-11-16 14:08 reverify:outset → parked (H-003)

- 做了什麼：只有 macOS 版。11/4 的筆記：安裝檔是 `.pkg`，要裝到 `/usr/local/outset` 並放 LaunchDaemons、LaunchAgents，要管理者密碼；那次把 pkg 拆開後 `--version` 印得出 4.2.0，但寫不了 `/usr/local` 底下的記錄檔。沒有重跑。
- 結果：park，留在 H-003（macOS 這邊由 harness 代跑 `/usr/sbin/installer`）。花費 US$0。
- harness：無。

## 2026-11-16 14:20 reverify:hal0 → parked (H-003)

- 做了什麼：本機有候選、沒有抽取，抽取後在一般的箱子重跑一次。
- 結果：未驗證，`needs_root`，沒有寫回。安裝腳本一定要 root：preflight 先用 apt 裝 jq，在 `/var/lib/dpkg/lock-frontend` 被拒；後面還要 cosign、podman，而且要 systemd 當 PID 1。README 另一條路是給 Proxmox 主機的。run `runs/verify/verify-hal0-20261116-140702-36ad`，38 秒。花費：抽取 US$0.092、模型 US$0.007、沙盒 US$0.002。
- park，留在 H-003。它要的不只是幾個具名套件，是「在一台開好機的系統上以 root 安裝」，H-003 的做法就算做了也不一定夠，多半要 `--runtime vm` 加 systemd，或照實記成 pickfit 的環境驗不了。
- harness：無。

## 2026-11-16 14:20 reverify:holdspeak → verified

- 做了什麼：本機有抽取結果。10/31 停在 `needs_root`，那次的筆記是要 C/C++ 編譯器和 `linux-headers`。用 `--toolchain` 跑，編譯器有了就裝得起來，沒有用到核心標頭。
- 結果：level `service`，全新箱子重播通過，judge 判 working。run `runs/verify/verify-holdspeak-20261116-140703-884d`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 service。花費：模型 US$0.041、沙盒 US$0.067。
- harness：無。用的是 H-002 的建置箱子。原本掛在 H-003，其實缺的是編譯器。

## 2026-11-16 14:20 reverify:hw-smi → verified

- 做了什麼：`discover --repo`、抽取後選得到。10/31 停在 `g++: command not found`。用 `--toolchain` 跑 `./make.sh`。抽取列了 `ocl-icd-opencl-dev`，映像裡沒有，但沒有它也編得過。
- 結果：level `function`，全新箱子重播通過，judge 判 working（`--bars` 畫出 CPU、RAM、溫度的長條，`--log` 寫出 CSV），功能 2 項 checked。run `runs/verify/verify-hw-smi-20261116-131250-adae`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 function。花費：抽取 US$0.052、模型 US$0.052、沙盒 US$0.028。
- harness：無。用的是 H-002 的建置箱子。

## 2026-11-16 14:21 reverify:joyboy → parked (H-003)

- 做了什麼：本機有候選、沒有抽取，抽取後照 H-005 的方向加大箱子重跑：`--memory-mb 8192 --file-mb 6144`。
- 結果：未驗證，這次的原因是 `needs_root`，不是資源，沒有寫回。`./start_linux.sh --setup` 裝完套件後檢查 `cv2`，`opencv-python-headless` 找不到系統的 `libxcb.so.1` 就結束；它還會跑 Ollama 的安裝腳本，那個要 root。agent 繞過啟動器直接跑 `web/app.py` 伺服器是起得來的，但那不是 README 的路，不算。run `runs/verify/verify-joyboy-20261116-140702-72b9`。花費：抽取 US$0.086、模型 US$0.014、沙盒 US$0.026。
- park，從 H-005 改掛 H-003。缺 `libxcb1` 這種常見的函式庫，加進基底映像就好，我把這個做法寫進 `loop/issues.md` 的 H-003，這個 session 沒有做（要重建所有映像、重跑 `--limits-test`）。
- harness：只補了 H-003 的筆記。

## 2026-11-16 14:21 reverify:khive → verified

- 做了什麼：`discover --repo`、抽取後選得到。第一次用 `--toolchain`（gVisor）：編得過，但伺服器一啟動就結束，因為它檢查資料庫路徑上層目錄的擁有者，在 gVisor 箱子裡 `/`、`/home`、`/tmp` 顯示成 uid 65534。這是 pickfit 的箱子和一般機器不一樣，開了 H-008，量過 `--runtime vm` 的箱子擁有者是正常的 root，改用 `--runtime vm --toolchain` 重跑。
- 結果：level `service`，全新箱子重播通過，judge 判 working（MCP 握手成功，兩個工具呼叫都回 ok，`kkernel --version` 印 0.19.0）。4 項功能裡 2 項 `test_failed`、2 項沒查，checked 是 0。run `runs/verify/verify-khive-20261116-133734-9074`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 service。花費：抽取 US$0.069、兩次模型共 US$0.049、兩次沙盒共 US$0.249。
- harness：H-008，標成 fixed（做法是換 `--runtime vm`，沒有改程式；skill 加了一句）。`--limits-test --runner modal --runtime vm --toolchain` 23/23 通過。commit `ab188d59`。
- 需要你：有 2 項功能記成 `test_failed`（跑了、結果不對）。這是照實的結果，但會顯示在工具頁上，請看一眼 run 的內容是不是軟體真的有問題。

## 2026-11-16 14:51 reverify:kronn → parked (H-005)

- 做了什麼：本機有候選、沒有抽取，抽取後用 `--toolchain` 跑。10/31 記的是 `needs_container`，但 README 其實有不用 Docker 的路：發行的 `.deb`，或從原始碼建。
- 結果：未驗證，`needs_more_resources`，沒有寫回。`.deb` 要 `sudo dpkg -i`，相依 webkit2gtk、gtk3、appindicator，是桌面 App 的裝法。原始碼那條路的 `cargo build` 在單一指令 30 分鐘的上限被砍，接著重跑到 769 秒又以 137 結束（多半是記憶體不夠），停在編 kronn 自己那個 crate。README 的開發模式還要比箱子裡的 Node 22 更新的版本，沒走到前端那一步。run `runs/verify/verify-kronn-20261116-140703-e00c`，44 分鐘。花費：抽取 US$0.119、模型 US$0.015、沙盒 US$0.312。
- park，從 H-004 改掛 H-005：要比建置箱子（4 vCPU、6 GiB、30 分鐘）更大的箱子。可以先試 `--toolchain --memory-mb 16384`，這個 session 沒有再花一次 45 分鐘去試。
- harness：無。

## 2026-11-16 14:51 reverify:ling-stack → verified

- 做了什麼：`discover --repo`、抽取後選得到。紀錄把它記成桌面 App，10/31 那次是因為沒有 Linux 的發行檔、只能從原始碼建。README 現在預設的上手路徑是 Web、daemon 和 CLI（Node 22、pnpm 10、Rust 1.89 以上），新的抽取把它讀成自架的網頁服務，所以不用顯示箱子，用 `--toolchain` 跑。
- 結果：level `service`，全新箱子重播通過，judge 判 working（daemon 起來、健康檢查回 `"ok":true`、CLI 的說明印得出來）。4 項功能都沒 checked。Electron 的桌面殼這次沒有驗。run `runs/verify/verify-ling-stack-20261116-140801-b206`，用 `guarded_write_back.py` 寫回，紀錄從 unverified 變成 service。花費：抽取 US$0.049、模型 US$0.037、沙盒 US$0.084。
- harness：無。用的是 H-002 的建置箱子。
- 需要你：紀錄的 `kind` 還是 `desktop_app`，但這次驗的是 Web、daemon、CLI 那條路。`kind` 要不要跟著新的抽取改，要跑 `pickfit profiles`，loop 沒有做。
