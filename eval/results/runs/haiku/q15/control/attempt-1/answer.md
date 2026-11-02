# 主要建議：whisper.cpp + 量化模型 + OpenCC 轉繁體

whisper.cpp 是 C/C++ 實作，不需要 PyTorch，CPU 上通常比 openai-whisper 快很多，原生支援 SRT 輸出，全程離線。簡體問題用 **初始提示詞（`--prompt`）** 引導成繁體，再用 **OpenCC** 做最後的簡轉繁，這樣結果比較穩定。

我假設你的筆電是 Linux（Debian/Ubuntu 系）。我沒有執行任何指令，以下都是建議步驟。

## 安裝步驟（只需要網路下載一次）

```bash
# 1. 系統套件（Debian/Ubuntu）
sudo apt update
sudo apt install -y git build-essential cmake ffmpeg opencc

# 2. 取得原始碼並編譯（純 CPU，不需要 GPU 或 PyTorch）
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載量化模型（large-v3-turbo 是速度與準確度的好平衡）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
```

如果 `download-ggml-model.sh` 不認得 `large-v3-turbo-q5_0`，就改用 `large-v3-turbo`，或筆電較弱時用 `small`/`medium`。

## 第一次執行

```bash
# 1. 轉成 16kHz 單聲道 WAV（whisper.cpp 的要求）
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:pcm_s16le meeting.wav

# 2. 轉寫，輸出 SRT
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh \
  --prompt "以下是繁體中文的會議逐字稿。" \
  -t $(nproc) \
  -osrt -of meeting
# 產出 meeting.srt
# 舊版 whisper.cpp 的執行檔叫 ./main，新版叫 whisper-cli。

# 3. 簡體轉台灣繁體（只改文字，時間軸不受影響）
opencc -i meeting.srt -o meeting-tw.srt -c s2twp.json
```

建議先用 5 分鐘左右的片段測試速度和品質，再跑完整錄音。

## 注意事項

- **離線**：模型下載完之後，whisper.cpp 不需要網路。若想確保沒有外連，可以在下載後斷網執行。
- **繁體字形**：`s2twp.json` 是台灣繁體加上用詞轉換（例如「软件」→「軟體」）。如果你要的是字形而不改用詞，用 `s2tw.json`。香港用字則用 `s2hk.json`。
- **初始提示詞**：`--prompt` 裡寫繁體句子，會讓模型更傾向輸出繁體。如果會議有固定專有名詞（人名、公司名、專案名），也可以把它們放進提示詞。

## 備選方案

- **faster-whisper**（Python，CTranslate2，CPU 用 int8）：不需要 PyTorch，`pip install faster-whisper` 即可。用法是 `WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")`，轉寫時傳 `language="zh"` 和 `initial_prompt="以下是繁體中文的會議逐字稿。"`。它的 SRT 要自己寫，之後一樣用 OpenCC 轉換。如果你偏好 Python 工作流，可以選它。
- **SenseVoice（經 sherpa-onnx）**：中文辨識通常很好，也有 ONNX 版本可以避開 PyTorch。但我沒有實際驗證它的安裝細節，而且輸出仍是簡體，需要 OpenCC。

Sources:
- whisper.cpp 專案（建置、模型下載、whisper-cli 用法）：https://github.com/ggml-org/whisper.cpp
- faster-whisper：https://github.com/SYSTRAN/faster-whisper
- OpenCC：https://github.com/BYVoid/OpenCC