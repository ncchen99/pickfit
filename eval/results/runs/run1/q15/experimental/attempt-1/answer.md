# 建議：whisper.cpp + OpenCC 轉繁體

最推薦的組合是 **whisper.cpp**（純 C/C++，不需要 PyTorch）加上 **OpenCC**（簡轉繁）。兩者都免費、開源、完全離線。

**為什麼選這個組合：**
- **不用 PyTorch**：whisper.cpp 編譯完只有幾 MB，模型檔另外下載。large-v3-turbo 量化版大約 550 MB，比裝好幾 GB 的 PyTorch 小很多。
- **CPU 上比較快**：在 CPU 上通常比 openai-whisper 快好幾倍，主要靠 SIMD/AVX、多執行緒和量化模型。large-v3-turbo 的解碼層比 large-v3 少很多，準確度接近，速度快很多。實際速度要看你的 CPU。
- **可以直接輸出 SRT**：加 `-osrt` 就會產生含時間軸的字幕檔。
- **繁體輸出穩定**：Whisper 的中文訓練資料以簡體居多，加提示詞（prompt）可以提高輸出繁體的機率，但不保證。最穩的做法是轉完再用 OpenCC 轉一次。OpenCC 只改字，不會動 SRT 的時間軸。

**我的假設：** 你用 Ubuntu/Debian 系的發行版、x86_64 CPU，錄音是普通話會議。下面的指令我沒有在你的電腦上執行過，請先確認內容再跑。

## 安裝

```bash
# 1. 編譯工具、ffmpeg、OpenCC（需要 sudo）
sudo apt install build-essential cmake git ffmpeg opencc

# 2. 下載並編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載模型（建議先試 turbo 量化版，兼顧速度與準確度）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
# 太慢的話可以改用 small 或 medium，速度快但錯字較多

# 4.（選用）下載 VAD 模型：跳過靜音段，可以減少「幻聽」重複句
sh ./models/download-vad-model.sh silero-v5.1.2
```

## 第一次執行

```bash
# 1. 轉成 whisper.cpp 需要的格式：16 kHz、單聲道 WAV
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄並輸出 SRT（-t 填你的 CPU 實體核心數）
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh -t 8 \
  --prompt "以下是繁體中文的會議逐字稿。" \
  --vad -vm models/ggml-silero-v5.1.2.bin \
  -osrt -of meeting
# 產生 meeting.srt（沒有下載 VAD 模型的話，拿掉 --vad 那一行）

# 3. 轉成台灣繁體，s2twp 會連用語一起轉，例如 软件→軟體、视频→影片
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

- 只想轉字、不想改用語的話，把 `s2twp.json` 換成 `s2tw.json`。
- 建議先剪一段 5 分鐘的音檔測速度，再決定要用 turbo 還是 small/medium。
- 可以把會議常出現的人名和專有名詞寫進 `--prompt`，辨識會比較準。

## 其他選擇

1. **whisper-ctranslate2（底層是 faster-whisper）**
   - 用 CTranslate2 引擎，同樣不需要 PyTorch，CPU 上用 int8 也很快。
   - 用法跟 openai-whisper 幾乎一樣，適合想繼續用 Python 的人。
   ```bash
   pipx install whisper-ctranslate2
   whisper-ctranslate2 meeting.m4a --model large-v3-turbo --language zh \
     --compute_type int8 --vad_filter True \
     --initial_prompt "以下是繁體中文的會議逐字稿。" --output_format srt
   opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
   ```

2. **MediaTek Breeze-ASR-25**
   - 這是針對台灣華語（含中英夾雜）微調的 Whisper 模型，原生輸出繁體。
   - 如果會議是台灣口音或常夾英文，值得試試。
   - 不過我沒確認它目前有沒有現成的 whisper.cpp（ggml）或 CTranslate2 格式。沒有的話要自己轉換，或改用需要 PyTorch 的 transformers。

3. **babelscribe（pickfit 查到的）**
   - pickfit 有在 Linux 沙盒實際安裝，也確認能產生 SRT。
   - 但它沒有驗證 CPU 上的速度，也沒有驗證會不會輸出繁體。pickfit 自己的結論也是：沒有候選工具證明比你現在的做法更好。
   - 所以我不把它當首選。
   - 網址：https://github.com/phonology024/babelscribe

**隱私：** 以上做法都只在第一次下載模型時需要連網，之後轉錄全部在本機進行，會議內容不會上傳。

Sources:
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [OpenCC](https://github.com/BYVoid/OpenCC)
- [whisper-ctranslate2](https://github.com/Softcatala/whisper-ctranslate2)
- [babelscribe](https://github.com/phonology024/babelscribe)