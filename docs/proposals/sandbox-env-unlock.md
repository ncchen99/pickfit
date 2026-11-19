# 打通沙盒環境：GPU、麥克風、喇叭、攝影機、後端服務、網頁功能與影片、LLM 金鑰

2026-11-20（台北）· 分支 `feat/opt-sandbox-env`。念誠要把 GPU、顯存、錄音、麥克風這類環境打通，不然很多軟體驗不了。[audit-20261120.md](audit-20261120.md) 列的環境建議也一起處理：Postgres／Redis／HTTP mock、網頁功能檢查與錄影、需要 LLM API key 的工具。

這份分兩部分。第一部分是這個分支已經做好、有測試的。第二部分是還要開機器、改基礎設施或做安全審查的，寫成可以照著做的步驟。所有改動都沒有碰 `limits.py`、`web_guard.py`、`schema.py` 或其他 `scripts/loop_guard.py` 保護的檔案。

## 一覽

| 環境 | 狀態 | 解鎖的大約筆數 | 一筆多花的錢 |
|---|---|---|---|
| GPU（T4 16 GB、L4 24 GB） | **已接進 watch** | audit 的 GPU 12 筆，加上 `local_ai` 裡要 GPU 的 | T4 最多約 US$0.43，L4 最多約 US$0.59（兩個箱子各活滿 22 分鐘的上限）；實際多半是一半以下 |
| 麥克風（模擬） | **已接進 watch**（audio.py 原本就有，limits.py 也測過） | 語音、聽寫、STT 工具 | 幾乎 0（CPU） |
| 編譯工具鏈 | **已接進 watch** | audit 的工具鏈 13 筆，加上只能 `cargo install`／`go install` 的 | 8 核心時間，約 US$0.1–0.3 |
| Postgres、Redis、HTTP mock | **第一版已做**（新映像，還沒在 Modal 跑 limits test） | `needs_service` 100 筆的大部分，加上 API／REST client | 幾乎 0，映像第一次建約 1–2 分鐘 |
| 喇叭輸出擷取（TTS、播放器） | 提案，步驟在下面 | 幾十筆 | 幾乎 0 |
| 攝影機 | 提案：網頁 App 很快能做，原生 App 要 EC2 VM | 少量 | 網頁約 0；EC2 每次幾分錢 |
| 網頁多項功能檢查與影片 | 查清原因，提案 | 132 筆 not_reported、130 筆沒影片 | 每多一項功能約 US$0.3；一段影片約 US$0.8 |
| 只缺 LLM API key 的工具 | 提案：託管在 Worker 的計費代理 | `needs_account` 120 筆裡只缺 LLM key 的那部分 | 每筆幾分錢，有硬上限 |

## 第一部分：已經做好的

### 1. watch 自動挑箱子（`pickfit/verify/box_needs.py`、`pickfit/watch.py`）

`modal_box.py` 早就能開 `gpu="T4"/"L4"/"A10"`、`audio=True`、`toolchain=True`，但 watch 只開一般箱子和有顯示器的箱子。更糟的是，extraction 寫「需要 GPU」的紀錄在分流那一步就被擋下（`not_in_box` 回「needs a GPU」），連驗都沒驗。

現在每筆紀錄進 watch 時，`box_needs` 讀 extraction 的欄位和引文（verify 時再加上 README），決定要哪種箱子。不連網，也不問模型。

- **GPU**：`prerequisites.gpu` 是 `required` 才開。卡選來源寫的顯存裝得下的最小一張：沒寫或 16 GB 以下用 T4，24 GB 以下用 L4。A10 也是 24 GB 但比較貴，不選。寫明要超過 24 GB 的，理由寫「pickfit 最大只有 24 GB」，不驗。`optional` 的不開 GPU，跑 CPU 路徑。
- **GPU 費用上限**：開之前先算最壞情況，也就是 agent 的箱子和重播的箱子各活滿整個 lifetime 的 GPU 費。超過 `PICKFIT_GPU_MAX_USD`（預設 US$1.50）就不開，理由寫出估的金額和上限。要編譯的紀錄箱子活得比較久（47 分鐘），所以用比較長的時間算。
- **麥克風**：系統套件或 runtime 有 PortAudio、ALSA、PulseAudio、sounddevice，或摘要、功能、用途寫錄音、麥克風、speech-to-text、聽寫、push-to-talk、wake word，就開 `audio=True`。README 要提到兩次以上才算，因為 README 常順口提一句。
- **工具鏈**：pickfit 會先跑的那條安裝方式是從原始碼建置（`cargo install/build`、`go install/build`、`make`、`cmake`、`meson`、`./configure`），或者每條都是，就開 `toolchain=True`，agent 的時間也從 20 分鐘放寬到 45 分鐘。排第一的是預建執行檔或套件管理器時不開。
- **服務**：見下一節。

`routed_verify` 每種箱子只建一次 factory、每種映像只發布一次，再交給既有的 `sized_for_build`。GPU 只有 Modal 有（gVisor），EC2 跑同一筆紀錄時只拿得到麥克風、工具鏈和服務。分流（`_lane_for`）只在 Modal 給得了卡、又在費用上限內時，才讓 GPU 紀錄進 Linux 這條。

測試：`tests/test_box_needs.py`（14 個：顯存解析、選卡、費用上限、麥克風誤判、工具鏈、服務）和 `tests/test_watch.py` 新增 5 個（麥克風、工具鏈與時間、GPU 選卡、服務箱子、分流的費用上限），另外改寫一個原本假設箱子在啟動時就建好的測試。

### 2. 沙盒後端服務第一版（`pickfit/verify/services.py`）

新的映像種類 `services`（標籤 `pickfit-sbx-svc:<hash>`）多了 `postgresql`、`redis-server` 兩個套件和一個指令 `pickfit-services`：

```text
pickfit-services start postgres     postgresql://pickfit@127.0.0.1:5432/pickfit
pickfit-services start redis        redis://127.0.0.1:6379/0
pickfit-services start http-mock    http://127.0.0.1:8080/（任何請求都回 200 和請求內容的 JSON）
pickfit-services env                印出 DATABASE_URL、REDIS_URL、MOCK_URL
pickfit-services status | stop
```

開機時什麼都不跑。agent 照提示把啟動服務當成一個安裝步驟，重播時就會在全新的箱子裡再啟動一次。

為什麼不破 `limits.py` 的隔離：服務由 box user 自己啟動，受 box user 的限制，只聽 box user 自己網路命名空間裡的 127.0.0.1。斷網時跟 box user 跑的其他東西一樣被切斷。套件沒有新增任何 setuid 執行檔（在容器裡比對過前後），套件自己的 init script 在箱子裡不會執行。

實測：在本機的 `python:3.12-slim` 容器（`sandbox.Dockerfile` 的基底）以 uid 1000 執行，三個服務都起來了。Postgres 建表、寫入、讀回 42，Redis 設值、讀值，HTTP mock 回應了 POST。三個都只聽 127.0.0.1，`stop` 也正常。

`box_needs` 看到 PostgreSQL、Redis、`DATABASE_URL`，或「HTTP／REST／API client」「postman like」這類字，就開服務箱子。atac、slumber 這類 API client 從 harvest 進來時就有東西可以打。驗證指令也多了 `--services`。

**上線前還要做的一步**：在 Modal 對新映像跑一次 limits test（`--limits --services --runner modal`，約幾分錢）。過了再讓 watch 送紀錄進去。這次沒有開任何 Modal 機器。

## 第二部分：提案

### 3. 喇叭輸出擷取（驗 TTS、播放器、會出聲的工具）

現況：audio.py 的 PulseAudio 只有一個 null sink `pickfit_speaker`，pickfit 把語音播進去，它的 monitor 再變成麥克風。這個 sink 同時也是預設輸出，所以 App 播的聲音會繞回自己的麥克風，pickfit 也聽不到 App 播了什麼。

做法：

1. 在 `audio.MODULES` 加第二個 null sink `pickfit_app_out`，設成預設 sink（`set-default-sink` 在啟動時一次做完，之後照舊禁止載入或卸載模組）。App 播的聲音進這裡，跟麥克風分開。
2. pickfit 以 DISPLAY_UID 用 `parecord --device=pickfit_app_out.monitor` 錄到 EVIDENCE_DIR（0700，box user 讀不到）。
3. 判定分兩層。先看有沒有聲音（RMS 超過門檻，不需要模型）。要驗 TTS「說了指定的字」時，在 harness 這邊用 CPU 跑 whisper.cpp tiny 或 vosk 小模型轉文字（約 75 MB，放映像裡），比對 pickfit 隨機產生的字。跟麥克風的檢查一樣，字不出現在命令列、檔名或 box user 看得到的地方。
4. agent 多一個工具 `capture_audio(seconds)`，回傳「有聲音、幾秒、轉出的文字」。

隔離：`limits.py` 現有的 audio 檢查（box user 不能重設、停止或殺掉 PulseAudio）照樣適用。要新增一項：box user 不能錄 `pickfit_app_out.monitor` 以外 pickfit 自己的音訊。這要改 `limits.py`，屬於受保護檔案，要照 loop 的規則寫 patch 提案，由人審。

花費：CPU 時間，幾乎 0。

### 4. 虛擬攝影機

分兩種情況：

- **網頁 App（很快能做）**：Chromium 有 `--use-fake-device-for-media-stream`、`--use-fake-ui-for-media-stream` 和 `--use-file-for-fake-video-capture=<y4m>`／`--use-file-for-fake-audio-capture=<wav>`。在 `web_harness.py` 的 Chromium 參數裡，當網頁要求攝影機或麥克風時，餵 pickfit 自己產生、每次都不同的測試畫面（畫面上印隨機字串）和語音。判定沿用網頁的功能檢查：例如 QR 掃描、OCR、手勢 App 的結果要出現 pickfit 隨機產生的內容。不需要核心模組，`web_guard` 不用改。
- **原生 App（要 VM 的核心）**：`v4l2loopback` 是核心模組。gVisor 沒有真的核心，做不到。Modal 的 VM runtime 能不能載入模組要先實測（`modprobe v4l2loopback`，多半核心沒編這個模組）。可行的是 EC2 VM：AMI 裡裝 `v4l2loopback-dkms`，開機時由 root 建 `/dev/video10`，pickfit 以 DISPLAY_UID 用 ffmpeg 餵測試影格。box user 只能讀這個裝置（加進專屬群組），不能寫。

原生 App 這條要在 `limits.py` 加檢查（box user 不能寫 `/dev/video10`、不能 `modprobe`），一樣要寫 patch 提案。花費是 EC2 每次幾分錢，筆數少，建議排在網頁那條之後。

### 5. 網頁 App：為什麼只到「打得開」，以及怎麼補

查過程式之後，問題不是 web 路徑只驗載入。`web_verify.verify_site` 一次造訪會做 install（頁面判讀），也會用 browser-use 實際操作**一項**宣稱的功能，由 pickfit 自己和第二個 judge 確認結果。缺口在兩個地方：

1. **只操作一項功能**：紀錄列了四項功能，另外三項在 `web_record.web_run` 裡記成 `not_attempted`，coverage 就算成 `function.not_reported`（132 筆裡網頁 97 筆）。
2. **影片從來沒有接進 watch**：`web_video.record_web` 是另外手動跑的指令（第二次造訪、無模型重播、Chromium screencast），之後還要 `video.py edit --write-back` 和 R2 上傳。watch 的每一條（Linux、Windows、macOS、網頁）都沒有呼叫影片流程。

建議做法：

- **多項功能**：同一次造訪裡，`function` 這一步依序操作前 N 項功能（建議 N=3），每項都照現有的規則檢查。一站一次造訪的規則不變，因為還是同一次造訪。花費每多一項約 US$0.3（operator 加 judge，照帳本 web-operate 的平均）。改的是 `web_verify.py` 的 function 步驟和 `web_record.web_run` 的功能對應，都不是受保護的檔案。判定由 `web_guard`、judge 負責，不動。
- **影片**：在 watch 的網頁和 GUI 流程通過之後，排一個背景工作：`record_web`（或 GUI 的 `video.py record`），接著 `make_clip`、write-back、上傳 R2。要先做兩件事：watch 機器要有 R2 的寫入憑證（S3 API key，只開 `pickfit-videos` bucket 寫入），以及決定預算。一段影片的模型費約 US$0.8（帳本：video-edit 約 US$0.33、video-review 約 US$0.43），比 audit 估的 US$0.05–0.1 高很多。想省錢的話，可以不做模型剪輯，只用自動章節，一段約 US$0.05，品質比較粗。

### 6. 需要 LLM API key 的工具：計費代理

目標：沙盒裡**絕不放真的金鑰**，但要讓只缺 OpenAI／Anthropic 相容 API key 的 AI CLI、MCP server 能實際跑一次。

架構：

1. **代理放在 Cloudflare Worker**（pickfit 已經有 Worker 和 D1）：路徑 `/llm/v1/...`，提供 OpenAI 相容（`/chat/completions`、`/responses`）和 Anthropic 相容（`/messages`）兩種介面。真的金鑰只放 Worker secret。Modal 箱子連得到公開網路（有白名單），連不到 watch 主機，所以代理不放主機上。
2. **一次驗證一張票**：verify 開始時，watch 用 HMAC 簽一張票 `pfk_<run>_<到期時間>_<簽章>`。這張票只對這次 run 有效，1 小時到期，額度 US$0.20，模型限一個便宜的（例如 Claude Haiku），`max_tokens` 上限 1,024，每分鐘 20 次。重播的箱子拿另一張新票。
3. **放進箱子的方式**：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 設成這張票，`OPENAI_BASE_URL`、`ANTHROPIC_BASE_URL` 指向代理。很多工具支援改 base URL。不支援的工具維持「需要帳號」，不硬套。
4. **計費與上限**：每次呼叫在 D1 記帳（沿用 `meta_budget` 的做法），以票為單位扣額度。另外有每日總上限（建議 US$5）。超過就回 429，agent 會看到明確的錯誤。
5. **風險**：票被工具外傳時，損失被額度、到期時間、模型白名單和速率限制框住。工具送出的提示詞會經過 pickfit 的代理，只記長度和花費，不存內容。這要在 `docs/source-terms.md` 寫明。

要先決定的：每日上限、代理用哪個模型（念誠 11/17 說過管線本身不換弱模型；這裡是給受測工具用的，建議用最便宜的）。實作在 `worker/src/` 加一個路由，另外在 `pickfit/verify/` 加簽票和放環境變數，limits.py 要加一項檢查：箱子裡的環境變數不能有 `sk-` 開頭的真金鑰。這項同樣要寫 patch 提案。

### 7. 超過 24 GB 顯存

Modal 有更大的卡（A100、H100），費率是 T4 的好幾倍。這次沒開。要開的話，在 `GPU_TIERS` 和 `modal_box.GPU_USD_PER_S` 加上卡和官方費率，費用上限要另外設，而且最好只對 `local_ai` 類、有明確模型大小的紀錄開。

## 上線順序建議

1. 在 Modal 跑新服務映像的 limits test，再跑一筆要 Postgres 的工具和一筆 API client 實測（約 US$1）。
2. 合併這個分支，watch 就會自動把 GPU、麥克風、工具鏈、服務的紀錄送進對的箱子。先看一天的 GPU 花費，必要時調 `PICKFIT_GPU_MAX_USD`。
3. 網頁多項功能檢查（第 5 節），再來是網頁攝影機（第 4 節前半）。
4. LLM 計費代理（第 6 節），要先定預算。
5. 喇叭擷取、原生 App 攝影機、影片自動化，這些都要改受保護的檔案或加憑證，逐項審。
