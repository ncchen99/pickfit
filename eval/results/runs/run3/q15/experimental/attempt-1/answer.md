# 建議：用 whisper.cpp 轉錄，再用 OpenCC 轉成繁體

我沒有在你的機器上執行任何指令，下面的步驟也還沒在你的系統上測過。我查了 pickfit 的已驗證工具庫，裡面沒有同時支援中文、SRT 和繁體輸出的工具。所以以下建議是根據我自己對這些工具的了解，不是 pickfit 測過的結果。

## 主推薦：whisper.cpp + OpenCC

**為什麼選它：**
- **不用裝 PyTorch。** 它是純 C/C++ 程式，編譯出來只有幾 MB。模型檔用量化版本，大約 0.5–1.1 GB。
- **CPU 上快很多。** 它針對 CPU 指令集（AVX2 等）做了最佳化，又用量化模型，通常比 openai-whisper 在 CPU 上快好幾倍。
- **完全離線。** 模型只要下載一次，之後錄音不會離開你的電腦。
- **可以直接輸出 SRT**（參數 `-osrt`）。
- **繁體輸出分兩層處理。** 先用 `--prompt` 給一段繁體提示，模型就比較會輸出繁體。不過 Whisper 偶爾還是會混進簡體，所以再用 OpenCC 轉一次，結果就穩定是繁體。

### 安裝（Debian/Ubuntu，假設你是這類發行版）

```bash
# 1. 編譯所需工具、ffmpeg（轉音檔用）、OpenCC（簡轉繁）
sudo apt install build-essential cmake git ffmpeg opencc

# 2. 下載並編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載模型（只需一次，之後可離線）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0   # 約 550 MB，速度和準確度比較平衡
# 筆電較弱的話可以改用：medium-q5_0 或 small
```

### 第一次執行

```bash
# 1. 把錄音轉成 16kHz 單聲道 WAV（whisper.cpp 最穩定支援的格式）
ffmpeg -i 會議.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄並輸出 SRT
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh \
  -t 8 \
  --prompt "以下是繁體中文的會議逐字稿，請使用台灣用語與全形標點。" \
  -osrt -of meeting
# 執行後會產生 meeting.srt；-t 請設成你 CPU 的實體核心數

# 3. 簡轉繁（同時保留時間軸）
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

**OpenCC 設定怎麼選：**
- `s2twp`：轉成繁體，也會換成台灣用語，例如「软件→軟體」。
- `s2tw`：只轉字，不換用詞。
- `s2hk`：轉成香港繁體。

**小提示：**
- 先拿一段 5 分鐘的錄音比較 `large-v3-turbo-q5_0` 和 `medium-q5_0`，看哪個在你的筆電上速度和準確度比較能接受。
- 會議中如果有很長的安靜片段，Whisper 可能會「幻覺」出重複的句子。新版 whisper.cpp 有 VAD 參數（`--vad`，要另外下載 Silero VAD 模型），可以改善這個問題。詳細用法請執行 `whisper-cli --help` 確認。

## 替代方案：faster-whisper（透過 whisper-ctranslate2）

如果你想沿用和 openai-whisper 幾乎一樣的指令參數，可以考慮這個方案。它底層用 CTranslate2，不需要 PyTorch，在 CPU 上用 int8 量化也比原版快很多，而且內建 VAD。

```bash
pipx install whisper-ctranslate2
whisper-ctranslate2 會議.m4a --model large-v3-turbo --language zh \
  --compute_type int8 --vad_filter True \
  --initial_prompt "以下是繁體中文的會議逐字稿。" \
  --output_format srt --output_dir .
opencc -i 會議.srt -o 會議.zh-TW.srt -c s2twp.json
```

要注意的是，第一次執行時它會從 Hugging Face 下載模型，下載完之後就能離線使用。下載的只是模型檔，你的錄音不會被上傳。

## 總結

| 問題 | 解法 |
|---|---|
| 慢 | whisper.cpp 搭配量化模型（或 faster-whisper int8） |
| 要裝好幾 GB 的 PyTorch | 兩個方案都不需要 PyTorch |
| 輸出簡體 | 用 `--prompt` 引導，再用 OpenCC 轉換確保是繁體 |
| 要 SRT | `-osrt` / `--output_format srt` |
| 不能上傳 | 全部在本機執行 |

如果只能選一個，我推薦 **whisper.cpp + `large-v3-turbo-q5_0` + OpenCC `s2twp`**。