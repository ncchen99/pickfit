# 建議：whisper.cpp 加 OpenCC 轉繁體

我的假設：你的筆電是 x86_64、Debian/Ubuntu 系列，錄音主要是台灣華語。以下我都沒有在你的機器上執行，只是列出指令。

## 主要建議：whisper.cpp + OpenCC（`s2twp`）

**為什麼選它**
- **不用 PyTorch**：whisper.cpp 是純 C/C++ 寫的 Whisper，編譯出來只有幾 MB。模型檔是單一個 `.bin`，量化版 large-v3-turbo 大約 500–600 MB。
- **CPU 上快很多**：它針對 AVX2 等 CPU 指令和多執行緒做過最佳化，也支援量化模型（q5_0／q8_0）。一般比 openai-whisper 在 CPU 上快好幾倍。實際速度要看你的 CPU，我沒辦法保證倍數。
- **直接輸出 SRT**：加上 `-osrt` 就會產生含時間軸的 `.srt`。
- **完全離線**：只有下載模型時需要連網，之後不會上傳任何東西。
- **繁體字**：Whisper 模型本身偏向輸出簡體。用 prompt 引導有幫助，但不一定每次都有效。所以建議最後一定要用 OpenCC 的 `s2twp` 轉換，它會轉成台灣正體，也會換成台灣用詞（例如「软件」變「軟體」）。這一步是固定規則，結果穩定，而且只改文字，不會動到 SRT 的時間軸。

### 安裝
```bash
# 1. 建置工具、ffmpeg、OpenCC
sudo apt install build-essential cmake git ffmpeg opencc

# 2. 編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載模型（量化 turbo：準確度接近 large-v3，速度快很多）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
```

### 第一次執行
```bash
# whisper.cpp 需要 16kHz 單聲道 WAV
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 轉錄並輸出 SRT（-t 設成你的實體核心數）
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav -l zh -t 8 \
  --prompt "以下是繁體中文的會議逐字稿。" \
  -osrt -of meeting

# 轉成台灣正體，時間軸不變
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

**調整建議**
- 如果還是太慢，可以把模型換成 `medium-q5_0` 或 `small`。速度會快很多，但中文準確度會下降。
- 建議先拿一段 5 分鐘的錄音測試，看速度和準確度能不能接受，再處理整場會議。
- 如果你的發行版裡 `s2twp.json` 找不到，改成 `-c s2twp` 試試看。

## 備選：faster-whisper（Python，也不用 PyTorch）

如果你想留在 Python 環境，可以用它。它的底層是 CTranslate2，可以用 int8 在 CPU 上跑，安裝也比 PyTorch 小很多。
```bash
python3 -m venv ~/fw && source ~/fw/bin/activate
pip install whisper-ctranslate2 opencc-python-reimplemented
whisper-ctranslate2 meeting.m4a --model medium --language zh \
  --compute_type int8 --output_format srt \
  --initial_prompt "以下是繁體中文的會議逐字稿。"
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp   # 或用 apt 裝的 opencc
```

## 關於 pickfit 的查詢結果

我也用 pickfit 查了替代工具。它推薦的 **babelscribe**（MIT 授權，已在 Linux x86_64 沙箱實測過可以離線產生 SRT）主要是針對 GPU 設計的。它的說明沒有證明在 CPU 上比較快，也沒有保證輸出繁體，所以我沒有把它當主要建議。上面的 whisper.cpp 和 faster-whisper 是我根據自己的了解推薦的，pickfit 沒有驗證過它們。

**一句話總結**：用 whisper.cpp 的 `large-v3-turbo-q5_0` 模型加上 `-osrt` 輸出，再用 `opencc -c s2twp` 轉換，就能離線、不裝 PyTorch、在 CPU 上做出繁體 SRT。