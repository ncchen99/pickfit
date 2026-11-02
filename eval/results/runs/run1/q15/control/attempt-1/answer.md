# 建議：whisper.cpp 加 OpenCC 轉繁體

**主要建議：用 [whisper.cpp](https://github.com/ggml-org/whisper.cpp) 轉錄，再用 [OpenCC](https://github.com/BYVoid/OpenCC) 的 `s2twp` 設定把字幕轉成台灣繁體。**

兩者都免費、開源、可以離線使用。whisper.cpp 是 C/C++ 寫的，不需要 Python 也不需要 PyTorch，對 CPU 有特別最佳化，還能直接輸出 SRT。模型檔大約 0.5～1.6 GB，比 PyTorch 那一大包小很多。用量化模型在 CPU 上跑，通常比 openai-whisper 快好幾倍。

**我的假設：** 你用 Debian 或 Ubuntu 類的發行版，需要台灣慣用的繁體中文（如果要香港用字，把 `s2twp` 換成 `s2hk`）。下面的指令我沒有在你的機器上執行過。

---

## 為什麼要分兩步處理繁體

Whisper 的中文訓練資料以簡體為主，所以就算加了繁體提示詞（prompt），還是常常混入簡體字。提示詞可以改善，但不保證每次都對。最可靠的做法是轉錄完再用 OpenCC 轉換一次。`s2twp` 除了轉字，也會轉詞彙，例如「软件」會變成「軟體」，「视频」會變成「影片」。

---

## 安裝（只需做一次）

```bash
# 1. 系統套件
sudo apt update
sudo apt install -y build-essential cmake git ffmpeg opencc

# 2. 下載並編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載模型（只有這一步需要連網，會從 Hugging Face 下載，不會上傳任何東西）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
```

**模型怎麼選：**

| 模型 | 大小（約） | 說明 |
|---|---|---|
| `large-v3-turbo-q5_0` | ~550 MB | **建議先用這個**，速度和中文準確度比較平衡 |
| `large-v3-q5_0` | ~1.1 GB | 最準，但比較慢，適合口音重或很多專有名詞的會議 |
| `small` / `base` | 小很多 | 很快，但中文錯字明顯變多 |

## 第一次執行

```bash
# 1. 先轉成 16 kHz 單聲道 WAV（最穩定的輸入格式）
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄並輸出 SRT（會產生 meeting.wav.srt）
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh \
  -t 8 \
  --prompt "以下是一場會議的逐字稿，使用繁體中文與全形標點符號。" \
  -osrt

# 3. 轉成台灣繁體
opencc -i meeting.wav.srt -o meeting.zh-TW.srt -c s2twp.json
```

**參數說明：**
- `-l zh`：直接指定語言是中文，省掉自動偵測，也比較不會誤判。
- `-t 8`：使用的執行緒數，建議設成 CPU 的實體核心數（用 `nproc` 或 `lscpu` 查詢）。
- `--prompt`：讓模型偏向輸出繁體和全形標點。也可以把會議中常出現的人名或專有名詞加進去，會更準。
- `-osrt`：直接輸出 SRT 字幕檔。
- 如果你的 OpenCC 版本找不到 `s2twp.json`，改成 `-c s2twp` 試試。設定檔通常放在 `/usr/share/opencc/`。

**選用設定：** 如果錄音裡有很多靜音或停頓，可以開啟 VAD（語音活動偵測）來跳過靜音段。這樣比較快，也能減少 Whisper 在靜音時亂編文字（幻覺）。新版 whisper.cpp 有支援：先執行 `sh ./models/download-vad-model.sh silero-v5.1.2`，轉錄時再加上 `--vad --vad-model models/ggml-silero-v5.1.2.bin`。這組參數會隨版本變動，請先用 `./build/bin/whisper-cli --help` 確認你的版本有沒有。

---

## 替代方案：faster-whisper（想留在 Python 的話）

如果你比較習慣 Python，可以用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)。它的底層是 CTranslate2，**不需要 PyTorch**，在 CPU 上用 int8 運算，速度和 whisper.cpp 差不多，也內建 VAD。

```bash
python3 -m venv ~/fw && source ~/fw/bin/activate
pip install faster-whisper
```

```python
# transcribe.py — 用法：python transcribe.py meeting.m4a
import sys
from faster_whisper import WhisperModel

def ts(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"

model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
segments, _ = model.transcribe(
    sys.argv[1], language="zh", vad_filter=True,
    initial_prompt="以下是一場會議的逐字稿，使用繁體中文與全形標點符號。")
with open(sys.argv[1] + ".srt", "w", encoding="utf-8") as f:
    for i, s in enumerate(segments, 1):
        f.write(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n\n")
```

第一次執行會從 Hugging Face 下載模型，之後就能完全離線使用。輸出的 SRT 一樣要再用 `opencc ... -c s2twp.json` 轉一次繁體。

---

## 小提醒

- **完全離線：** 模型下載好之後就可以拔網路線。音訊只會在你的電腦上處理。
- **如果需要區分講者：** whisper.cpp 和 faster-whisper 都不會分辨誰在說話。需要的話可以另外看 WhisperX 或 pyannote，但這兩個又會用到 PyTorch。
- **SRT 時間軸：** 一定要保留 OpenCC 處理之前的原始檔。OpenCC 只會改文字，不會動到時間軸，所以轉完可以直接拿去用。