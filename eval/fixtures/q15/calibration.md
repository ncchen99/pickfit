# q15 開跑前的固定與紀錄

第 3 節：「frozen」「pinned」的東西在**第一次開跑評測前 commit**。下面每一步在任何一組開跑前做完，結果填在本檔、commit；之後不改。

原則：音檔依事先寫定的規則選，不先聽、不先拿任何語音辨識工具試過再挑；不跑任何候選答案的工具。

## 1. 做出凍結的音檔（念誠）

1. 從 `needs.json` 第 1 項選來源（念誠 2026-10-28 已決定用 CC0 的公開中文錄音）。
2. Common Voice（候選 1、2）：
   1. 下載該版本的資料集，只留 `validated.tsv` 與它指到的檔案。
   2. 依規則選片段（不聽）：
      ```bash
      python3 eval/fixtures/q15/select_clips.py --tsv <validated.tsv> --clips-dir <clips/> --count 25 \
        --dataset "<資料集名稱與版本>" --url "<下載網址>" --out /tmp/q15/manifest.json
      ```
      規則：`up_votes >= 2`、`down_votes == 0`、句子至少 12 個漢字；每位說話者只取第一句；再依 SHA-256(`q15-clip-v1` + 換行 + path) 排序取前 25 句。
   3. 只把選中的檔案轉成 16 kHz、單聲道、16-bit WAV（同檔名、副檔名 `.wav`，放在 manifest 同一個資料夾）：
      ```bash
      ffmpeg -nostdin -i <clip>.mp3 -ac 1 -ar 16000 -c:a pcm_s16le <clip>.wav
      ```
   4. 組成 60 秒：
      ```bash
      python3 eval/fixtures/q15/build_clip.py concat --manifest /tmp/q15/manifest.json --out-dir eval/fixtures/q15/clip
      ```
      依 manifest 順序取用、放不下 60 秒的那句跳過、句間 0.30 秒靜音、結尾補靜音到剛好 60.000 秒（最多 2.5 秒，超過就停：把 `--count` 加大重跑，規則不變）。
3. LibriVox（候選 3）：選定章節與起點後
   ```bash
   python3 eval/fixtures/q15/build_clip.py cut --wav <章節>.wav --start <秒> --text-file <逐字稿> \
     --source-json <來源說明.json> --out-dir eval/fixtures/q15/clip
   ```
   逐字稿以出版文字為準，照實際唸的內容逐句校正。
4. 只聽一次組好的 `clip.wav`，確認檔案完整（沒有破音、整段靜音）。不能因為「太難」「太簡單」換句子；壞掉的片段才照規則換下一句，並記在下表。

| 項目 | 值 |
|---|---|
| 來源（資料集與版本，或 archive.org 識別碼） | LibriVox《呐喊 - Call to Arms》（魯迅），Jing Li 朗讀；archive.org `call_to_arms_jl_librivox`，檔案 `calltoarms_06_lu.mp3`（第 06 段〈一件小事〉，原始 VBR MP3，262.94 秒）。念誠 2026-10-31 選定（協調 session 轉達）。逐字稿的出版文字：Project Gutenberg #27166《吶喊》（Gutenberg 標示 Public domain in the USA；純文字檔 sha256 `ddf28d52…a429732`） |
| 授權（來源頁面原文） | archive.org 項目的 licenseurl：`http://creativecommons.org/publicdomain/mark/1.0/`（Public Domain Mark 1.0），`source` 欄：「Librivox recording of a public-domain text」。LibriVox 目錄頁（https://librivox.org/call-to-arms-by-xun-lu/）：「LibriVox recordings are Public Domain in the USA.」**是公有領域，不是 CC0。** |
| 下載網址與日期 | https://archive.org/download/call_to_arms_jl_librivox/calltoarms_06_lu.mp3，2026-10-31T08:11:12Z（UTC）。4,208,942 位元組；md5 `a284f268bc8edee002d12ae1ccfe5864`、sha1 `4d27b7e3691f30076d3f72e5d11bce30f330d046` 與 archive.org metadata 相同；sha256 `3fb8a83babca98710097bd0fd7a075fd72098c7bfc7736987274603d8aa656e3`。MP3 不 commit（只 commit 切出來的 `clip/`）；來源細節在 `source_librivox.json`（`build_clip.py cut --source-json` 讀它，寫進 `SOURCE.json`） |
| ffmpeg 版本（`ffmpeg -version` 第一行） | `ffmpeg version 9.0.1 Copyright (c) 2000-2026 the FFmpeg developers`（念誠的 Mac，Homebrew）；轉出的 WAV sha256 `5377aee4…6005d57b`、262.88475 秒 |
| 用了幾句、跳過幾句（`SOURCE.json`） | 不適用（一段連續錄音）。先試過 `cut` 從 45.000 秒起 60.000 秒（`speech_seconds` 41.56），念誠改成下面的「縮短長停頓」 |
| 因壞掉而換掉的片段與原因 | 無（念誠 2026-10-31 聽過縮短後的 `clip.wav`，沒有換片段） |
| `clip.wav` SHA-256 | `ac7e3aabafe151807d8c11f5b87ee2db61ce635d9efed11a49f60fc19ee5cf17`（1,920,044 位元組；`warmup.wav` `8ddd2c177c9a6d921b79b6e1b83b40daf4522920d4c75c6998cca9a7c07a23bb`） |
| `reference.txt` SHA-256 | `30b549562c15bfa032ba29727aae2879c28153378b1a6cf6f967ff621a354568`（念誠存的 `reference-draft.txt`，sha256 `a558ed0f…07beca2c`，原樣交給 `build_clip.py squeeze --text-file`；只多了 `build_clip.py` 一律補的結尾換行） |

2026-10-31：`build_clip.py cut --start 45.000` 建了兩次，`clip.wav`（sha256 `115a528a…676536c`，1,920,044 位元組）與 `warmup.wav`（`146ba9bd…cd4b1c43`）兩次逐位元相同。起點落在 45.04–45.68 秒的停頓裡，105.000 秒的終點切在句子中間。（當時寫「停頓前剛唸完『…一轉眼已經六年了。』」，那是從時間推的猜測；念誠後來聽縮短版時推翻了同一個推測，見下面第 2 條的更正。45 秒這段沒有採用。）逐字稿草稿（Gutenberg 原文那一段，去掉註腳記號，機器轉換留下的「里、于、關系、頭發」等改成正體）交給念誠聽一次校正，**還沒定**；所以 `clip/` 還沒 commit。

**校準發現（後來念誠改成下面的「縮短長停頓」）**：這一段的 `speech_seconds` 是 41.56，低於下面第 2 節要的 55。這個錄音每 5 秒取一個起點、每段 60 秒都算過，最多 45.0（130 秒起）：朗讀的句間停頓多（這一段裡 0.5 秒以上的停頓合計約 8.5 秒）。當時算的字數（草稿到「車夫已經讓開道」為止的 `script_differing` 64、到「…所以終於兜著車把。」73）用的是猜錯的文字段，作廢；45 秒這段沒有採用，不再重算。

### 縮短長停頓（念誠 2026-10-31 決定；規則在量任何結果之前寫下並 commit）

念誠的決定（協調 session 轉達）：用同一份 LibriVox 錄音、取長一點的一段，把超過 0.5 秒的停頓縮成固定長度，讓 60 秒的片段至少有 55 秒語音；處理固定、兩組相同。規則（`build_clip.py squeeze`）：

1. **來源**：上面那份 `calltoarms_06_lu.mp3`（sha256 `3fb8a83b…656e3`）用固定版本的 ffmpeg 轉成的 16 kHz 單聲道 16-bit WAV（sha256 `5377aee417f093090a46c4c6ed44391ed75c6d2014e973ec9db7446e6005d57b`）。
2. **起點**：39.02 秒，也就是第一句「我從鄉下跑到京城裡，一轉眼已經六年了。」前面那段停頓（39.02–41.16 秒）的開頭，在 LibriVox 的開場白與篇名之後。這是從時間推出來的：照全篇平均每秒 4.2 字，第一句在 45.04 秒的停頓唸完，和實際的停頓位置相符；念誠聽的時候確認。
   **更正（2026-10-31，念誠聽過）**：這個推測錯了。念誠聽到片段的第一句是第三段開頭的「這是民國六年的冬天」，所以 39.02–41.16 秒的停頓在第二段「……使我至今忘記不得。」之後，正文前兩段在 39.02 秒以前就唸完了（片段仍在開場白與篇名之後）。起點的秒數、規則、建出來的音檔與上面量到的數字都不變；改正的只有「起點在文字的哪裡」，以及由文字算出的字數（下面結果的最後一條）。
3. **停頓偵測**：20 毫秒一格（320 個樣本），從來源 WAV 的第 0 個樣本對齊；每格算 RMS，低於門檻就是靜音。門檻＝整個來源最大聲那一格減 35 dB（下限 RMS 30），和 `speech_seconds` 判語音用的同一條規則（`build_clip.py` 的 `voiced()`），換算成 dBFS 記在 `SOURCE.json`。停頓＝連續的靜音格。
4. **縮短**：長度超過 0.50 秒（26 格以上）的停頓，一律縮成 0.30 秒：保留它開頭 0.15 秒與結尾 0.15 秒的原始樣本，拿掉中間。0.50 秒以下的停頓不動；語音的樣本一個都不改（不變速、不變調、不調音量、不重新取樣、不在字中間切）。
5. **終點**：可以切的位置只在停頓裡：縮短過的長停頓的正中間（兩個 0.15 秒之間），或沒動過、至少 0.10 秒的停頓的正中間。取 60.000 秒以內最後一個「長停頓」切點，只要它離 60.000 秒不超過 2.5 秒（盡量整句）；不然取 60.000 秒以內最後一個短停頓切點。後面用數位靜音補到剛好 60.000 秒（960,000 個樣本）。
6. **固定**：只用 Python 標準函式庫，同樣的輸入兩次建出來要逐位元相同。`SOURCE.json` 記規則的參數、門檻的 dBFS、每一個縮短的停頓（來源的起訖秒數、原長 → 0.30 秒）、終點落在來源的哪裡、補了幾秒。
7. **目標**：建好後 `stats` 量 `speech_seconds`（要 ≥ 55）與逐字稿的 `script_differing`（要 ≥ 60）。沒達到就照實記下、回報，不為了達標調任何參數。

**結果**（2026-10-31，照上面的規則建，規則在 commit bffebcc 先寫下）：

- 兩次建出來逐位元相同：`clip.wav` sha256 `ac7e3aabafe151807d8c11f5b87ee2db61ce635d9efed11a49f60fc19ee5cf17`、`warmup.wav` `8ddd2c177c9a6d92…`。
- 門檻 −42.27 dBFS；用到來源 39.02–107.56 秒（68.54 秒）；縮短 12 個停頓、拿掉 8.58 秒；終點在一個短停頓裡（片段 59.96 秒，來源 107.56 秒），補 0.04 秒靜音。60.000 秒以內最後一個長停頓切點離 60 秒超過 2.5 秒，所以照第 5 條用短停頓。
- **量測一：`speech_seconds` 46.66 秒。55 秒的目標沒有達到（not met），不算通過。** 照第 7 條沒有調任何參數。沒算成語音的 13.34 秒裡，縮短後的長停頓共 3.6 秒，其餘約 9.7 秒是 0.5 秒以下的字詞間隙與字內輕聲的格子，照規則不動；就算把長停頓全拿掉也只有約 49.6 秒。
- **量測二（另一項，不代替量測一）：cue 涵蓋可達的上限。** 算法：在這個片段上用同樣的 20 毫秒格子與門檻找出所有停頓，假設工具在每個不短於 X 秒的停頓都斷開 cue，60 秒減掉這些停頓的總長。X = 0.2 秒時 50.84 秒、0.3 秒時 52.72 秒、0.4 秒時 57.44 秒（原本從 45 秒起那段：45.16、46.20、47.86 秒）。片段裡最長的停頓 0.46 秒。這是片段本身容許的上限，不是任何工具的結果；L2-2 的「cue 涵蓋 ≥ 50 秒」仍照 `srt_check.py` 對每個答案的實際輸出判定。
- **念誠的決定（2026-10-31）**：接受這個片段（`speech_seconds` 46.66）。不再縮短 0.5 秒以下的停頓、不換 Common Voice：保留原始語音、處理固定，比硬達到 55 秒重要。報告把兩項量測分開寫，並寫明 55 秒的目標沒達到。
- `script_differing`：原本寫的「69–78，≥ 60」是用猜錯的文字段（從正文第一句起）算的，**作廢**。照念誠聽到的起點重算（`reference-draft.txt` 從「這是民國六年的冬天」起到全篇結尾，一句一行，逐行累計；累計表在 q15-draft 的 `script-differing-by-line.tsv`）：到第 10 行「車夫便也立住腳。」為止 53，到第 11 行「……也誤了我的路。」61，到第 14 行「……問伊說︰『你怎麼啦？』」78。**逐字稿至少要到第 11 行，`script_differing` 才 ≥ 60**；片段實際唸到哪一行，要等念誠聽過、校正後才知道（後來判定了，見下一條）。
- **念誠聽過、校正（2026-10-31 20:34 存檔）**：片段唸到第 11 行的「……便很怪他多事，要自己惹出是非」為止，後面都聽不到；第 1–10 行照草稿沒改，第 11 行刪掉「，也誤了我的路。」（沒有句末標點）。照這份文字（`clip/reference.txt`，244 個漢字）：**`script_differing` 正好 60**，第 1–10 行 53、第 11 行再加 7（刪掉的那段只少一個「誤」）。門檻是 ≥ 60，**通過，但沒有任何餘裕**（`build_clip.py stats` 同樣是 60、pass）。

縮短的停頓（來源秒數；片段裡的位置是縮短後那 0.30 秒的開頭）：

| # | 來源（秒） | 原長 → 新長（秒） | 片段裡（秒） |
|---|---|---|---|
| 1 | 39.02–41.16 | 2.14 → 0.30 | 0.00 |
| 2 | 45.04–45.68 | 0.64 → 0.30 | 4.18 |
| 3 | 48.80–49.84 | 1.04 → 0.30 | 7.60 |
| 4 | 55.64–56.58 | 0.94 → 0.30 | 13.70 |
| 5 | 62.78–63.32 | 0.54 → 0.30 | 20.20 |
| 6 | 64.74–65.56 | 0.82 → 0.30 | 21.92 |
| 7 | 70.30–71.90 | 1.60 → 0.30 | 26.96 |
| 8 | 76.18–77.10 | 0.92 → 0.30 | 31.54 |
| 9 | 86.66–87.22 | 0.56 → 0.30 | 41.40 |
| 10 | 88.88–89.54 | 0.66 → 0.30 | 43.36 |
| 11 | 95.52–97.22 | 1.70 → 0.30 | 49.64 |
| 12 | 100.16–100.78 | 0.62 → 0.30 | 52.88 |

`clip/` 底下四個檔（`clip.wav` 約 1.9 MB、`warmup.wav`、`reference.txt`、`SOURCE.json`）一起 commit。`clip.wav` 超過「每題 1 MB」的目標：60 秒 16 kHz 單聲道 PCM 就是 1.92 MB，而 WAV 是每個語音辨識 CLI 都能讀的格式，不換成壓縮格式（換了就可能變成某些工具要多一步轉檔）。

## 2. 固定 OpenCC 與 SRT 解析器（評分端，沙盒外）

OpenCC 的字典檔照 [`_shared/calibration.md`](../_shared/calibration.md) 步驟 3（q11 用同一份，放在 `$OPENCC`）。SRT 解析器在評分者自己的 venv 裝固定版本，記下：

| 項目 | 值 |
|---|---|
| srt 版本、wheel SHA-256 | |

然後：

```bash
python3 eval/fixtures/q15/build_clip.py stats --clip eval/fixtures/q15/clip/clip.wav --ref eval/fixtures/q15/clip/reference.txt --dict-dir $OPENCC
python3 eval/fixtures/q15/zh_score.py --dict-dir $OPENCC all --ref eval/fixtures/q15/clip/reference.txt --text eval/fixtures/q15/clip/reference.txt
```

| 項目 | 條件 | 值 |
|---|---|---|
| `speech_seconds` | ≥ 55 | **46.66：沒達到**（念誠 2026-10-31 接受這個片段；見上面「縮短長停頓」的量測一、二） |
| `script_differing`（`ref-stats`） | ≥ 60 | **60：通過（正好在門檻上）** |
| 逐字稿對自己的 CER | 0 | 0（246 個字，0 個編輯） |
| 逐字稿自己的繁體比例（簡體來源先 s2tw） | 記錄 | 1.0（繁體 60、簡體 0；來源本來就是繁體，不用 s2tw） |
| 逐字稿裡被判為簡體的字（`simplified_chars`） | 記錄 | 沒有 |

逐字稿是人寫的繁體；共用規則把兩種寫法都對的字（例如「台」）一律算成不計，所以不再有例外清單（原本的 `script_allow.txt` 拿掉）。若仍有字被判為簡體，記下來給念誠看。

## 3. 速度基準（openai-whisper small）

1. 照 `needs.json` 第 4 項填好 `WHISPER_VERSION`、`TORCH_VERSION`、`TORCH_INDEX_URL`、`SMALL_PT_SHA256`。
2. 開一個與受測容器相同的沙盒，`sh /eval/q15/baseline/run_baseline.sh setup`，擋外連後 `sh /eval/q15/baseline/run_baseline.sh time /results/baseline-trial`，確認能跑完。這次的時間只用來確認可行，不拿來評分（評分時每題另跑一次）。

| 項目 | 值 |
|---|---|
| WHISPER_VERSION | |
| TORCH_VERSION、TORCH_INDEX_URL | |
| SMALL_PT_SHA256 | |
| ffmpeg 套件版本 | |
| `pip-freeze.txt` 存放位置 | |
| 試跑秒數（只記錄） | |
| 試跑沙盒的 CPU 型號 | |

## 4. 擋外連與外連監測（與 q14 相同）

在擋住的沙盒裡：

```bash
python3 $SHARED/egress.py probe --json /results/probe.json                 # exit 0
python3 $SHARED/egress.py selftest --out /results/selftest                 # _shared/calibration.md 步驟 1，各題共用一次
python3 $SHARED/egress.py run --out /results/quiet --label quiet -- sleep 10
python3 $SHARED/egress.py report --out /results/quiet                      # pass
```

| 項目 | 值 |
|---|---|
| 擋法與指令（受測與基準容器相同） | |
| `selftest` 結果 | （記在 `_shared/calibration.md`） |

`selftest` 不通過時，不改用 `/proc` 輪詢判過（它抓不到立刻失敗的連線）；照 `_shared/README.md` 第 1 節，請念誠決定替代做法並寫在這裡。

## 5. dev image 與自我測試

| 項目 | 值 |
|---|---|
| dev image digest | |
| `python3 -m unittest discover -s eval/fixtures/q15/tests -v` | |
| commit | |
