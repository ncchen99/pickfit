# q15 測試資料

題目：沒有 GPU 的 Linux 筆電上，把中文會議錄音轉成有時間軸的 SRT 逐字稿；要比 openai-whisper 快、不裝 PyTorch、離線、直接輸出繁體中文（找替代品）。沙盒：`linux_sandbox`。

這個資料夾只給評分者，受測 agent 看不到。除了音檔（公有領域的 LibriVox 錄音，**不是 CC0**；見 `needs.json`、`source_librivox.json`），內容全部自己寫、固定；不含任何工具名稱、廠商、模型名稱或預期答案。腳本只用 Python 3.9+ 標準函式庫與 POSIX 工具；評分端另需固定版本的 OpenCC 與 `srt`。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `sandbox.json` | 沙盒規格：x86_64、4 vCPU、16 GB、無 GPU；受測容器與基準容器 |
| `source_librivox.json` | 錄音的來源（archive.org 項目與檔案、大小、md5／sha1／sha256、授權原文、解碼指令、切的起點、逐字稿的出版文字）；`build_clip.py cut --source-json` 讀它 |
| `clip/` | **開跑前由念誠建立並 commit**：`clip.wav`（60.000 秒，16 kHz 單聲道 16-bit PCM）、`warmup.wav`（前 10 秒）、`reference.txt`、`SOURCE.json`（來源、授權、每個輸入檔的 SHA-256） |
| `select_clips.py` | 依固定規則從語料庫選片段（不先聽、不先試工具） |
| `build_clip.py` | 把選好的片段組成 60 秒音檔與逐字稿；`stats` 檢查語音秒數與繁簡不同字數 |
| `srt_check.py` | L2-2：SRT 是否有效、cue 涵蓋多少秒 |
| `zh_score.py` | L2-3、L2-4：CER 與繁體比例；轉換與比例都用共用的 `../_shared/zh_script.py`（第 5 節的共用 OpenCC 評分器，q11 用同一個） |
| `check_no_torch.sh` | L2-1：容器裡有沒有裝 torch |
| `baseline/run_baseline.sh` | L2-5：openai-whisper `small` 預設設定的速度基準（另一個容器） |
| `../_shared/egress.py` | L2-2、L2-6：證明外連被擋、記錄外連嘗試；`--no-trace` 只計時（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節） |
| `needs.json` | 要從外部取得的東西（音檔候選 3 個、OpenCC、SRT 解析器、基準版本等），待念誠決定 |
| `calibration.md` | 第一次開跑前要做的固定與紀錄 |
| `tests/` | 本資料夾腳本的自我測試 |

## 2. 共同設定

- **dev image**：第 5 節的 Linux 沙盒（Modal Sandbox、x86_64、以 `ubuntu:24.04` 為底，digest 記在 `calibration.md`），不接 GPU，4 vCPU、16 GB。
- **掛載**：本資料夾（含 `clip/`）唯讀掛在 `/eval/q15`；評分輸出寫到 `/results`。下文的 `$EVAL_PY` 是評分者自己的 Python 3（dev image 的 `python3`，或 `/eval` 上的獨立版本），不裝進受測環境。評分用的 OpenCC 與 `srt` 裝在沙盒外評分者自己的 venv；SRT 檔複製出來再評。
- **佔位字**：答案裡的輸入檔名、輸出位置、模型檔名是佔位字時，評分者填入（輸入一律是 `/work/meeting.wav`，由 `/eval/q15/clip/clip.wav` 複製；暖機用 `/eval/q15/clip/warmup.wav` 複製成同名檔）。
- **照原樣（verbatim）**：評分者把答案的安裝指令依序、原封不動複製成 `/results/steps.sh`，在同一個 bash 裡逐條執行（`bash -x steps.sh 2>&1 | tee /results/install.log`）。只做第 5 節允許的調整：填版本號與佔位字、安裝程式詢問時接受預設值；替換記在 `/results/substitutions.json`。Ubuntu 擋下裸 `pip install` 時可以改在 venv 裡繼續（記 `needed_venv`）。修正指令或旗標、補步驟、換模型都不允許。
- **答案的完整指令**：從音檔到最後交出的 SRT 為止的所有指令（轉檔、辨識、繁體轉換等後處理），照答案原樣寫成 `/results/run.sh`，用 `bash /results/run.sh` 一次執行。「最後交出的 SRT」是答案說要用的那一個（例如轉成繁體之後的檔）。
- **擋外連（egress blocked）**：照 9.3 B.3 與 [`_shared/README.md`](../_shared/README.md) 第 1 節：`egress.py run --block-network`（只有 loopback 的 network namespace，DNS 也查不到；在 Modal 的 gVisor 沙盒裡是 user＋network namespace，uid 照原樣對應，2026-10-31 實測）。在 setup（安裝、模型下載、暖機）完成之後才擋。要互相連線的步驟（啟動服務與送請求、檢查）寫進同一個腳本，用一次 `egress.py run --block-network --sh 'bash 腳本'` 跑完，因為每一次 `--block-network` 都是新的 namespace。兩組、所有答案都用同一種。
- **外連檢查（egress check）**：定義與判定見 [`_shared/README.md`](../_shared/README.md) 第 1 節（共用工具在沙盒裡的 `$SHARED`）：
  1. 擋了之後、Run B 前後各跑一次 `egress.py probe`：直接連公開位址的 TCP 與送往公開 DNS 的 UDP 都失敗，才算「確實擋住」；透過沙盒 resolver 查名稱只記錄。
  2. Run B 用 `egress.py run` 包起來，strace 記錄指令與所有子程序的連線；目的地不是 loopback、未指定位址、沙盒自己的位址的，以及任何查名稱（DNS），都算一次外連嘗試（包括私有網段、`169.254.169.254`）。
  3. 通過：前後探測都擋住，而且 `egress.py report` 是 `pass`。探測顯示沒擋住，是評分環境的問題：修好重跑，不記答案不過。
  4. strace 不能用時不能判過（`_shared/README.md` 第 1 節）。
- **判讀模型輸出（L2-2～L2-4）**：答案的指令或設定已經固定 temperature（例如 0 或 greedy）或 seed，或工具文件寫明可以用環境變數或設定檔固定（評分者照文件設定、記錄），就只用第 1 次（Run A）的輸出；都沒有，就用 Run A、Run B、Run C 三次的輸出，每一項 3 次中 2 次過算過（第 5 節，9.3 F.1）。評分者不加或改答案指令裡的旗標。
- **逾時**：安裝 20 分鐘；每次轉錄 10 分鐘（第 5 節）；超過就停，那一次記不過。

## 3. 執行順序

### 受測容器

1. 照 `sandbox.json` 開沙盒，確認 `nproc` 是 4、沒有 `nvidia-smi`。
2. 照原樣執行安裝步驟（含答案寫的模型下載）。
3. 暖機（可連網）：把 `warmup.wav` 複製成 `/work/meeting.wav`，執行一次 `bash /results/run.sh`，讓需要下載的東西下載完；結束後刪掉它產生的輸出。所有答案都做這一步，不論答案是否另有下載指令。
4. L2-1：`sh /eval/q15/check_no_torch.sh / > /results/no-torch.txt`；暖機那次成功結束（exit 0 且產生 SRT）就是「CLI 可用」。
5. 擋外連（strace 已在 dev image 裡，9.3 B.2；不另外安裝）。
6. 把 `clip.wav` 複製成 `/work/meeting.wav`，Run A（計時，不監測）：
   ```bash
   $EVAL_PY $SHARED/egress.py run --out /results/eg --label runA --no-trace --timeout 600 -- bash /results/run.sh
   ```
   SRT 複製成 `/results/runA.srt`，然後刪掉輸出。
7. Run B（外連監測）：先 `$EVAL_PY $SHARED/egress.py probe --json /results/probe-before.json`（exit 0），再用同一個指令、`--label runB`、不加 `--no-trace`；SRT 存成 `/results/runB.srt`。之後 `$EVAL_PY $SHARED/egress.py stop --out /results/eg --kill`、`$EVAL_PY $SHARED/egress.py probe --json /results/probe-after.json`（exit 0）、`$EVAL_PY $SHARED/egress.py report --out /results/eg --json /results/egress.json`（只納入有記錄的 runB）。
8. 答案沒有固定 temperature 或 seed 時，Run C：同 Run A（`--label runC --no-trace`），SRT 存成 `/results/runC.srt`。

### 基準容器（另一個沙盒，同一個 dev image、同樣 4 vCPU 16 GB）

9. `sh /eval/q15/baseline/run_baseline.sh setup`（可連網；版本照 `calibration.md`）。
10. 用同一種方法擋外連，`sh /eval/q15/baseline/run_baseline.sh time /results/baseline`。
11. 兩個容器都記下 `/proc/cpuinfo` 的 model name。不同時，兩個容器整組重開重跑，最多 3 組，用第一組 CPU 相同的結果；3 組都不同，用第 3 組並在結果註明。

### 評分（沙盒外）

12. 每個 SRT：
    ```bash
    python3 eval/fixtures/q15/srt_check.py runA.srt --out srtA.json
    python3 eval/fixtures/q15/zh_score.py --dict-dir $OPENCC all --ref eval/fixtures/q15/clip/reference.txt --srt runA.srt --out scoreA.json
    ```

## 4. L2 項目

### L2-1

> [L2] Following the steps in the dev image (x86_64, CPU only, 4 vCPU and 16 GB) produces a working CLI, and no torch package is installed

- 測試資料：`sandbox.json`、`check_no_torch.sh`、`clip/warmup.wav`。
- 「照步驟」：第 2 節的照原樣規則。
- 「可用的 CLI」：第 3 節步驟 3 的暖機執行 exit 0，而且產生了 SRT。
- 「沒裝 torch」：`check_no_torch.sh` 搜尋整個檔案系統（跳過 `/proc`、`/sys`、`/dev`）所有 `site-packages`、`dist-packages` 底下的 `torch`、`torch-*.dist-info`、`torch-*.egg-info`、`torch-*.egg`，以及 conda 的 `pkgs/pytorch-*`；下載快取不算安裝。
- 通過：安裝與暖機都成功，而且 `check_no_torch.sh` exit 0。

### L2-2

> [L2] Frozen 60-second Mandarin clip (scripted text read by a consenting speaker, or CC0/CC-BY) with a frozen reference transcript: with egress blocked after setup, the output is valid SRT (parses with the pinned SRT parser, sequential indices, start before end in every cue, non-decreasing start times) and its cues cover at least 50 seconds

- 測試資料：`clip/clip.wav`、`clip/reference.txt`（錄音是公有領域：archive.org 標 Public Domain Mark 1.0，LibriVox 寫 public domain in the USA；不是 CC0，也不是 CC-BY。檢查項目原文寫 CC0/CC-BY，念誠 2026-10-31 知道這點後選了這份錄音。`SOURCE.json` 記來源）；`srt_check.py`；固定版本的 `srt`。
- 設定：第 3 節步驟 5–8（擋外連之後的輸出）。
- 檢查（`srt_check.py`）：UTF-8（可有 BOM）；固定版本的 `srt` 解析沒有錯誤；至少 1 個 cue；每個 cue 的序號 = 前一個 + 1；每個 cue 開始 < 結束；開始時間不倒退；所有 cue 區間的聯集（截在 0–60 秒內）≥ 50 秒。
- 通過：`passed: true`（沒固定 temperature／seed 時，3 次中 2 次）。

### L2-3

> [L2] Accuracy: character error rate is at most 25% against the reference, after converting both to Traditional with the pinned OpenCC and removing punctuation

- 測試資料：`clip/reference.txt`；`zh_score.py`；固定版本的 OpenCC。
- 正規化（兩邊相同）：Unicode NFKC → 共用工具的 `s2tw`（固定版本的 OpenCC 字典檔，轉繁體、台灣字形；`_shared/README.md` 第 2 節）→ 刪掉所有不是字母或數字的字元（標點、符號、空白、換行），拉丁字母轉小寫。答案這邊是所有 cue 文字依序接起來（格式標籤已去掉）。
- CER = Levenshtein 距離 ÷ 參考字數。
- 通過：CER ≤ 0.25。

### L2-4

> [L2] Script: the shared OpenCC scorer gives a Traditional ratio of at least 0.95 (the reference script contains at least 60 script-differing characters)

- 測試資料：`zh_score.py script`，也就是共用評分器 `../_shared/zh_script.py`（與 q11 同一個）；固定版本的 OpenCC 字典檔；參考逐字稿的繁簡不同字數在 `calibration.md`（≥ 60）。
- 判斷方式：[`_shared/README.md`](../_shared/README.md) 第 2 節。答案的字照原樣逐字判斷、不轉換；兩種寫法都對的字（例如 台、后、里）不計。沒有例外清單。
- 比例 = 繁體 ÷（繁體 + 簡體）。
- 通過：繁體 + 簡體 ≥ 30（第 5 節），而且比例 ≥ 0.95。

### L2-5

> [L2] Speed: the answer's full end-to-end command, including any post-processing for Traditional output, finishes faster than openai-whisper 'small' with default settings, run once in an identical but separate container on the same host

- 測試資料：`clip/clip.wav`；`baseline/run_baseline.sh`；`$SHARED/egress.py run --no-trace`（只計時，兩邊同一個包裝）。
- 答案的時間：`/results/eg/runA.json` 的 `duration_s`（`bash /results/run.sh` 從開始到結束，含載入模型與後處理，不含已在 setup 完成的下載）。
- 基準的時間：`baseline.json` 的 `duration_s`，指令是 `whisper /eval/q15/clip/clip.wav --model small`，其他全用預設值（語言自動偵測、預設 beam 與溫度遞增、CPU 上用 fp32、預設輸出格式）。
- 「相同的另一個容器、同一台主機」：同一個 dev image、同樣的 CPU 與記憶體上限、同一種擋外連方法、都在擋住之後跑一次；Modal 不能指定主機，所以用 CPU 型號相同代替（第 3 節步驟 11）。
- 通過：答案的時間 < 基準的時間。Run A 失敗或逾時，就不過。

### L2-6

> [L2] Egress check passes during transcription

- 測試資料：`$SHARED/egress.py`。
- 設定：第 3 節步驟 7（Run B）：與 Run A 相同的指令、相同的輸入，在 strace 監測下跑；和計時的 Run A 分開，監測不影響速度項目。
- 通過：`probe-before.json`、`probe-after.json` 都是 `blocked: true`，`egress.json` 的 `result` 是 `pass`，而且 Run B exit 0（`/results/eg/runB.json`）。

## 5. 不適用

本題不是 Mac 題，沒有移除清單。

## 6. 自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q15/tests -v
```

用合成的音調 WAV 測 `build_clip.py`（裁靜音、跳過放不下的片段、補到剛好 60 秒）；用 `_shared/selftest_dict/` 的手寫小字典代替 OpenCC 測 `zh_score.py` 怎麼用共用評分器（規則本身的測試在 `_shared/test_shared.py`；真正的 OpenCC 字典在 `calibration.md` 對真正的逐字稿跑）；用手寫的 SRT 測 `srt_check.py`（內建的嚴格解析器，正式評分用固定版本的 `srt`）；用暫存資料夾測 `check_no_torch.sh`。2026-10-30 另在離線的 x86_64 Linux 容器跑過全部測試。
