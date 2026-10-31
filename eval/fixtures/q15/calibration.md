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
| 來源（資料集與版本，或 archive.org 識別碼） | |
| 授權（來源頁面原文） | |
| 下載網址與日期 | |
| ffmpeg 版本（`ffmpeg -version` 第一行） | |
| 用了幾句、跳過幾句（`SOURCE.json`） | |
| 因壞掉而換掉的片段與原因 | （預期是「無」） |
| `clip.wav` SHA-256 | |
| `reference.txt` SHA-256 | |

`clip/` 底下四個檔（`clip.wav` 約 1.9 MB、`warmup.wav`、`reference.txt`、`SOURCE.json`）一起 commit。`clip.wav` 超過「每題 1 MB」的目標：60 秒 16 kHz 單聲道 PCM 就是 1.92 MB，而 WAV 是每個語音辨識 CLI 都能讀的格式，不換成壓縮格式（換了就可能變成某些工具要多一步轉檔）。

## 2. 固定 OpenCC 與 SRT 解析器（評分端，沙盒外）

在評分者自己的 venv 裝固定版本，記下：

| 項目 | 值 |
|---|---|
| OpenCC 套件與版本、wheel SHA-256 | |
| srt 版本、wheel SHA-256 | |
| 與 q11 是否共用同一個 OpenCC 版本與 `zh_score.py` | |

然後：

```bash
python3 eval/fixtures/q15/build_clip.py stats --clip eval/fixtures/q15/clip/clip.wav --ref eval/fixtures/q15/clip/reference.txt
python3 eval/fixtures/q15/zh_score.py all --ref eval/fixtures/q15/clip/reference.txt --text eval/fixtures/q15/clip/reference.txt
```

| 項目 | 條件 | 值 |
|---|---|---|
| `speech_seconds` | ≥ 55 | |
| `script_differing`（`ref-stats`） | ≥ 60 | |
| 逐字稿對自己的 CER | 0 | |
| 逐字稿自己的繁體比例（簡體來源先 s2tw） | 記錄 | |
| 逐字稿裡被判為簡體的字（`simplified_chars`） | 記錄 | |

逐字稿是人寫的繁體，若有字被判為簡體，多半是台灣常用的字形（例如「台」）。念誠在開跑前決定是否列入 `script_allow.txt`（每行一個字，`zh_score.py script --allow`），兩組一體適用；決定與理由記在這裡。沒有這種字就不建立這個檔。

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

在擋住的沙盒裡（先 `apt-get install -y strace` 再擋）：

```bash
python3 /eval/q15/egress_check.py probe --log /results/probe.json        # exit 0
python3 /eval/q15/egress_check.py selftest --log /results/selftest.json  # ok: true
python3 /eval/q15/egress_check.py run --log /results/quiet.json -- sleep 10   # attempt_count 0
```

| 項目 | 值 |
|---|---|
| 擋法與指令（受測與基準容器相同） | |
| strace 版本 | |
| `selftest` 的 monitor 與結果 | |

`selftest` 不通過時，不改用 `/proc` 輪詢判過（它抓不到立刻失敗的連線）；請念誠決定替代做法並寫在這裡。

## 5. dev image 與自我測試

| 項目 | 值 |
|---|---|
| dev image digest | |
| `python3 -m unittest discover -s eval/fixtures/q15/tests -v` | |
| commit | |
