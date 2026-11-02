# 建議：用 **whisper.cpp** 轉錄，再用 **OpenCC** 轉成繁體

我假設你的筆電是 x86_64 的 Ubuntu 或 Debian，記憶體至少 8 GB。我沒有在這台機器上執行任何指令，以下只是建議步驟。

**為什麼選這個組合：**
- **不用 PyTorch**：whisper.cpp 是 Whisper 的 C/C++ 版本，編譯出來只有一個小程式，加上一個模型檔（約 0.5～1.6 GB）。
- **CPU 比較快**：它有針對 CPU 做最佳化，也支援壓縮過的小模型（例如 `q5_0`），通常比原版 openai-whisper 在 CPU 上快很多。實際速度要看你的 CPU。
- **可以直接輸出 SRT**：加上 `-osrt` 參數就會產生有時間軸的字幕檔。
- **繁體字有保證**：Whisper 本身沒有「只輸出繁體」的開關，提示詞只能提高繁體的比例。所以最後再用 OpenCC 轉一次，結果才穩定。
- **完全離線**：只有第一次需要上網下載程式和模型。下載完之後，錄音檔都在本機處理，不會上傳。

---

## 安裝（只需做一次）

```bash
# 1. 安裝編譯工具、ffmpeg、OpenCC
sudo apt update
sudo apt install -y git cmake build-essential ffmpeg opencc

# 2. 下載並編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --config Release

# 3. 下載模型（這是最後一次需要上網）
#    兼顧準確度和速度的建議：
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
#    如果還是太慢，可以改用比較小的模型：
# sh ./models/download-ggml-model.sh medium-q5_0
# sh ./models/download-ggml-model.sh small
```

裝好之後，可以把原本的 openai-whisper 和 PyTorch 移除（`pip uninstall openai-whisper torch`），收回好幾 GB 的空間。

## 第一次使用

```bash
# 1. 轉成 whisper.cpp 需要的格式：16 kHz、單聲道 WAV
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄成 SRT
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh \
  -t $(nproc) \
  --prompt "以下是繁體中文的會議逐字稿，請使用台灣用語與標點符號。" \
  -osrt -of meeting
# 這一步會產生 meeting.srt

# 3. 把簡體轉成台灣繁體
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

**小提醒：**
- 建議先剪一段 5 分鐘的錄音試跑，看速度和準確度再決定用哪個模型。
- `s2twp` 除了轉字，也會把用語換成台灣說法，例如「軟件→軟體」、「視頻→影片」。如果你只想轉字、不想改用語，就把參數換成 `-c s2t.json`。
- OpenCC 只會改字幕文字，SRT 的時間軸不受影響。
- 如果字幕一行太長，可以加 `-ml 30`，限制每段字幕的長度。
- 如果你的程式版本裡找不到 `whisper-cli`，舊版的程式名稱是 `./build/bin/main` 或 `./main`。
- 會議錄音裡如果有長時間的靜音，Whisper 偶爾會自己「編」出重複的句子。新版 whisper.cpp 有 `--vad` 選項，可以先把靜音段落濾掉。用法請看 `whisper-cli --help` 和 README 的 VAD 說明（需要另外下載一個 Silero VAD 模型）。

---

## 備選：faster-whisper（如果你偏好 Python）

faster-whisper 是用 CTranslate2 做的 Whisper，**一樣不需要 PyTorch**。它在 CPU 上用 int8 模式跑，速度也比原版快很多，而且內建 VAD（濾掉靜音）。

```bash
python3 -m venv ~/fw && source ~/fw/bin/activate
pip install faster-whisper opencc-python-reimplemented
```

把下面這段存成 `transcribe.py`：

```python
import sys
from faster_whisper import WhisperModel
from opencc import OpenCC

cc = OpenCC("s2twp")
model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
segments, _ = model.transcribe(sys.argv[1], language="zh", vad_filter=True,
                               initial_prompt="以下是繁體中文的會議逐字稿。")

def ts(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"

with open(sys.argv[2], "w", encoding="utf-8") as f:
    for i, s in enumerate(segments, 1):
        f.write(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{cc.convert(s.text.strip())}\n\n")
```

執行：`python transcribe.py meeting.m4a meeting.zh-TW.srt`

第一次執行時會從 Hugging Face 下載模型，之後就可以離線使用。這個方法可以直接讀 m4a、mp3 等格式，不用先轉成 WAV。

---

**總結：** 想要安裝最輕、速度最快，就選 whisper.cpp 加 OpenCC。想用 Python 寫成一個指令搞定，而且要內建靜音過濾，就選 faster-whisper。兩個都免費、開源、可以離線跑，都不需要 PyTorch，也都能穩定輸出繁體中文的 SRT。