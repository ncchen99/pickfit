# q16 測試資料

題目：在只有 CPU、16 GB RAM 的 Linux 主機上，離線把一個資料夾的英文 Markdown 文件批次翻成歐洲葡萄牙文（pt-PT），程式碼區塊與連結網址不能動。沙盒：`linux_sandbox`。

這個資料夾只給評分者，受測 agent 看不到。內容全部自己寫、合成、固定：產品名稱（Quillstack、Tarnwave、Mossgate）是虛構的，網址都在保留給範例用的 `example.com` 底下；不含任何工具名稱、廠商、模型名稱或預期答案。腳本只用 Python 3.9+ 標準函式庫；評分端另需固定版本的語言辨識器。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `sandbox.json` | 沙盒規格：x86_64、4 vCPU、16 GB、無 GPU；A、B 兩個階段 |
| `docs/` | 凍結的輸入：3 個 `.md`，共 1,021 字；有標題、清單、行內連結、參考式連結、自動連結、裸網址、fenced code（bash、yaml、json，含英文註解）、數字與產品名稱 |
| `warmup/hello.md` | 暖機用的小檔（可連網時先跑一次，讓工具下載需要的東西） |
| `manifest.json` | 由 `build_manifest.py` 從 `docs/` 產生的凍結事實：每檔 SHA-256、標題數、code block、URL、數字、產品名稱、要檢查的英文句子、變體清單、意義抽樣的 5 句 |
| `mdtools.py` | 輸入與輸出用同一套規則讀 Markdown |
| `md_check.py` | L2-3、L2-4、L2-5 的「沒有英文原句」、L2-6 |
| `lang_check.py` | L2-5 的語言辨識 |
| `meaning/rubric.md`、`meaning/make_judge_input.py` | L2-7：凍結的評分說明、盲評輸入、計分 |
| `calibration/` | 校準用：自己翻的 pt-PT 對照、pt-BR 對照（只有變體檔）、6 題已知答案的評分案例 |
| `egress_check.py` | L2-2：證明外連被擋、記錄外連嘗試、計時（q14、q15、q16 各一份，內容相同） |
| `needs.json` | 要從外部取得的東西（語言辨識器、意義評分者等），待念誠決定 |
| `calibration.md` | 第一次開跑前要做的固定與紀錄 |
| `tests/` | 本資料夾腳本的自我測試 |

## 2. 共同設定

- **dev image**：第 5 節的 Linux 沙盒（Modal Sandbox、x86_64、以 `ubuntu:24.04` 為底，digest 記在 `calibration.md`），不接 GPU，4 vCPU、16 GB。
- **掛載**：本資料夾唯讀掛在 `/eval/q16`；評分輸出寫到 `/results`。每次翻譯前把 `docs/` 複製成全新的 `/work/docs`（答案要求就地翻譯也只動這份複本）。下文的 `$EVAL_PY` 是評分者自己的 Python 3（dev image 的 `python3`，或 `/eval` 上的獨立版本），不裝進受測環境。`md_check.py`、`lang_check.py`、評分者工具都在沙盒外，對複製出來的輸出檔跑。
- **佔位字**：答案裡的資料夾、輸出位置、模型檔名是佔位字時，評分者填入（輸入一律是 `/work/docs`）。
- **照原樣（verbatim）**：評分者把答案的安裝指令依序、原封不動複製成 `/results/steps.sh`，在同一個 bash 裡逐條執行（`bash -x steps.sh 2>&1 | tee /results/install.log`）。答案給的膠水程式（題目允許最多 50 行）原封不動存成答案指定的檔名（沒指定時用答案提到的名稱或 `glue` 加上對應副檔名，記為佔位字替換），算安裝的一部分。只做第 5 節允許的調整：填版本號與佔位字、安裝程式詢問時接受預設值；替換記在 `/results/substitutions.json`。任何一條非 0 結束，或超過 20 分鐘，就是不過。Ubuntu 擋下裸 `pip install` 時可以改在 venv 裡繼續做後面的項目（記 `needed_venv`），但「照原樣成功」不過。修正指令或旗標、補步驟、改膠水程式、換模型都不允許。
- **答案的翻譯指令**：把整個資料夾翻完所需的指令（含啟動本機模型服務），照答案原樣寫成 `/results/run.sh`，用 `bash /results/run.sh` 一次執行。答案要求在另一個終端機先啟動服務時，評分者用 `egress_check.py run` 另外包住那個服務（另一份 log），兩份 log 都要通過外連檢查。
- **擋外連（egress blocked）**：在 A 階段（安裝、模型下載、暖機）完成之後才擋。做法：從檔案系統快照開新沙盒、網路在沙盒層級關閉（首選）；或在同一個沙盒以 root 用 iptables／ip6tables 只放行 `lo`，其餘 REJECT。用哪一種記在 `calibration.md`；兩組、所有答案都用同一種。
- **外連檢查（egress check）**：翻譯指令用 `egress_check.py run` 包起來：
  1. 執行前、後各探測一次：TCP 連 `1.1.1.1:443`、`8.8.8.8:53`、`9.9.9.9:443`、`[2606:4700:4700::1111]:443`，UDP 對 `8.8.8.8:53`、`1.1.1.1:53` 送 DNS 查詢，解析 `example.com`。全部失敗才算「確實擋住」。
  2. 執行期間用 strace（`-f --seccomp-bpf`，追蹤 `connect`、`sendto`、`sendmsg`、`sendmmsg`）記錄指令與所有子程序的連線；目的地不是 loopback、也不是未指定位址的，都算一次外連嘗試（包括 DNS 查詢、私有網段、`169.254.169.254`）。指令本身結束後，它留在背景的程序有 2 秒，之後被停掉。
  3. 通過：前後探測都擋住，而且外連嘗試 0 次（`verdict.egress_check_passed` 是 `true`）。探測顯示沒擋住，是評分環境的問題：修好重跑，不記答案不過。
  4. strace 不能用時，`/proc` 輪詢只是備案，抓不到立刻失敗的連線，不能用來判過（`calibration.md`）。
- **判讀模型輸出（L2-4～L2-7）**：答案的指令或設定明確固定了 temperature（例如 0）或 seed，就只用第 1 次翻譯的輸出；沒有固定，就再跑第 2、3 次（同樣擋外連、同樣 1800 秒上限，`--monitor none`），每一項 3 次中 2 次過算過（第 5 節）。L2-2、L2-3 只看第 1 次。評分者不自己加參數。
- **逾時**：安裝 20 分鐘；每次翻譯 1800 秒（題目的 30 分鐘，取代第 5 節的 10 分鐘），到時間 `egress_check.py --timeout 1800` 會停掉它。

## 3. 執行順序

### A 階段（可連網）

1. 照 `sandbox.json` 開沙盒，確認 `nproc` 是 4、沒有 `nvidia-smi`。
2. 照原樣執行安裝步驟（L2-1），含答案寫的模型下載。
3. 暖機：把 `/eval/q16/warmup` 複製成 `/work/docs`，執行一次 `bash /results/run.sh`，讓需要下載的東西下載完；結束後刪掉 `/work/docs` 與它的輸出。所有答案都做這一步。
4. 裝評分工具 `apt-get install -y strace`，然後擋外連。

### B 階段（擋外連）

5. `cp -r /eval/q16/docs /work/docs`，第 1 次翻譯：
   ```bash
   $EVAL_PY /eval/q16/egress_check.py run --timeout 1800 --log /results/translate-1.json -- bash /results/run.sh
   ```
   把答案的輸出資料夾整個複製到 `/results/out-1/`。
6. 答案沒有固定 temperature 或 seed：刪掉 `/work/docs` 與輸出，重新複製，第 2、3 次（`--monitor none --timeout 1800 --log /results/translate-N.json`），輸出存 `/results/out-2/`、`/results/out-3/`。

### 評分（沙盒外，每一次的輸出各跑一遍）

7. ```bash
   python3 eval/fixtures/q16/md_check.py --output out-1 --run-log translate-1.json --out md-1.json
   python3 eval/fixtures/q16/lang_check.py --output out-1 --backend <固定的> [--model-path ...] --out lang-1.json
   python3 eval/fixtures/q16/meaning/make_judge_input.py build --output out-1 --out judge-1.json
   ```
   輸出檔名認不出來時（見 L2-3），加 `--map 原檔名=輸出路徑`，三個工具用同一組對應。

## 4. L2 項目

### L2-1

> [L2] The install steps succeed verbatim in the dev image (CPU only, 4 vCPU and 16 GB)

- 測試資料：`sandbox.json`。
- 設定：第 3 節步驟 1–2。
- 通過：第 2 節「照原樣」的每一條都成功。用了 venv 或任何不允許的修改，就不過。

### L2-2

> [L2] After model download, with egress blocked, translation runs and the egress check passes

- 測試資料：`docs/`、`egress_check.py`。
- 設定：第 3 節步驟 4–5。
- 通過：`translate-1.json` 的 `exit_code` 是 0、沒有逾時，而且 `verdict.egress_check_passed` 是 `true`（另外包住的服務 log 也要是 `true`）。

### L2-3

> [L2] Frozen fixture folder of 3 .md files (about 1,000 words total; headings, lists, links, fenced code blocks, numbers and frozen product names): 3 output files are produced within 30 minutes

- 測試資料：`docs/`（1,021 字）；`md_check.py`。
- 輸出檔的認法（`mdtools.map_outputs`）：輸出資料夾底下（含子資料夾）檔名等於原檔名，或以原檔名主檔名開頭、接著 `.`、`_`、`-` 的 `.md` 檔（例如 `01-getting-started.pt.md`）；和原文一模一樣的檔不算輸出（沒翻）。同一個原檔有多個候選時，名稱裡有 `pt` 的那個優先；仍有多個就由評分者照答案說的命名用 `--map` 指定。
- 檢查：`md-1.json` 的 `files`：3 個原檔都有非空的輸出，`translate-1.json` 的 `wall_seconds` ≤ 1800 而且沒有逾時。
- 通過：`items.files_within_30_min` 是 `true`。

### L2-4

> [L2] Every fenced code block and link URL is byte-identical to the input, heading counts match per file, and the numbers and frozen product names appear unchanged

- 測試資料：`docs/`、`manifest.json`；`md_check.py`、`mdtools.py`。
- 逐檔檢查：
  - fenced code block：依序一一相同，逐位元組比較，開頭與結尾的 fence 行、語言標記、行尾都算（CRLF 與 LF 不同）；數量也要相同。
  - 連結網址：輸入的每個網址（行內連結與圖片、`<...>` 自動連結、參考式連結的定義、內文裡的裸網址）在輸出至少出現一樣多次，逐字相同。code block 裡的網址由上一條管。
  - 標題：code block 以外的 ATX 標題（`#`～`######`）數量相同；code 裡以 `#` 開頭的註解不算。
  - 數字與產品名稱：輸入內文（code block、行內 code、網址以外；清單編號不算）裡每個數字與每個產品名稱，在輸出內文至少出現一樣多次。數字以連續的阿拉伯數字為單位（`8h` 裡的 `8` 也算），把數字寫成文字就不算。
- 通過：三個檔都沒有問題（`items.structure` 是 `true`）。

### L2-5

> [L2] Each output prose paragraph is identified as Portuguese by a pinned language identifier with confidence of at least 0.9, and no English source sentence appears verbatim

- 測試資料：`manifest.json` 的 `sentences`；`lang_check.py`、`md_check.py`；固定版本的語言辨識器（`calibration.md`）。
- 「內文段落」：輸出檔的段落與清單（一個清單算一段），不含標題、code block、連結定義。送進辨識器前拿掉行內 code、網址、產品名稱與數字；剩不到 5 個字的段落不判（列在 `skipped`；原文沒有這麼短的段落）。
- 「英文原句」：輸入內文的每一句（清單逐項），扣掉產品名稱後至少 4 個英文字的，共 62 句，凍結在 `manifest.json`。空白壓成一個後，在輸出（標題、段落、清單，去掉 Markdown 語法）裡逐字（分大小寫）找得到，就算原樣留下。
- 通過：`lang-1.json` 的 `passed` 是 `true`（至少判了一段，每一段都是 `pt` 且信心 ≥ 0.9），而且 `md-1.json` 的 `items.no_verbatim_english` 是 `true`。

### L2-6

> [L2] Variant: the fixture's list items for 'file', 'screen', 'user', 'mobile phone' and 'to download' come out with at least 4 of ficheiro, ecrã, utilizador, telemóvel, transferir, and none of arquivo, tela, usuário, celular, baixar

- 測試資料：`docs/02-team-handbook.md` 的項目符號清單（那個檔唯一的 `-` 清單，5 項各含一個概念）；`md_check.py`。
- 檢查：對應輸出檔裡的所有項目符號清單項，Unicode NFC、不分大小寫，接受詞形變化：
  - 歐洲葡萄牙文：`ficheiro(s)`、`ecrã(s)`、`utilizador(es／a／as)`、`telemóvel／telemóveis`、`transfer…`（transferir、transfira、transferência 等）；
  - 巴西葡萄牙文：`arquivo(s)`、`tela(s)`、`usuário(s)／usuária(s)`、`celular(es)`、`baixar／baixe／baixem／baixando／baixado…`。
- 輸出檔裡找不到任何項目符號清單時，改搜整個檔（記為 `fallback_whole_file`）。
- 通過：5 個概念中至少 4 個出現歐洲用詞，而且沒有任何巴西用詞（`items.variant` 是 `true`）。

### L2-7

> [L2] Meaning: 5 sentences sampled with a fixed seed are each judged fully translated and meaning-preserving by a blind grader who reads Portuguese or, if none is available, by a pinned LLM judge with a frozen rubric (choice recorded before freeze); at least 4 of 5 pass

- 測試資料：`manifest.json` 的 `meaning_sample`（種子 `q16-meaning-v1`：依 SHA-256(種子 + 換行 + 句子編號) 排序取前 5 句，至少 6 個英文字，不受 Python 版本影響）；`meaning/rubric.md`；`meaning/make_judge_input.py`。
- 盲評輸入（`build`）：每句給原句、原句所在的英文段落，以及輸出檔同一位置的段落與前後各一段（純文字）。不含組別、工具名稱或檔名。
- 評分者：`calibration.md` 記下的那一位（人或固定的 LLM）。人用 `sheet` 產生的表；LLM 用 `requests` 產生的請求（temperature 0），回答存成 JSON Lines，`score` 計分。
- 通過：5 句中至少 4 句 PASS（`score` 的 `passed`）。答案沒固定 temperature／seed 而跑了 3 次時，每次各評 5 句，3 次中 2 次通過算過。

## 5. 不適用

本題不是 Mac 題，沒有移除清單。

## 6. 自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q16/tests -v
python3 eval/fixtures/q16/build_manifest.py --check
```

正向對照用 `calibration/control-pt-PT`（自己翻的變體檔）加上另外兩檔的機械替換版；反向對照用 pt-BR 版與刻意改壞的輸出（改 code 註解、在 code 行尾加空白、改網址、把數字寫成文字、拿掉標題、留下英文原句、沒翻的原檔）。語言辨識與 LLM 都用假的代替，只測規則；真正的辨識器與評分者在 `calibration.md` 校準。
