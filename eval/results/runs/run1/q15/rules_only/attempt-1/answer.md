# 建議：whisper.cpp 轉錄，再用 OpenCC 轉成繁體

我的假設：筆電是 x86_64、Debian/Ubuntu 系、有 4 核以上 CPU、8 GB 以上記憶體，錄音是普通話。依照你的要求，我沒有在你的機器上執行任何指令。

**主要建議**是用 **whisper.cpp** 轉錄，再用 **OpenCC** 把 SRT 轉成繁體。
- **速度與安裝大小：** whisper.cpp 是 Whisper 的 C/C++ 版本，不需要 PyTorch 或 Python，只要編出一個執行檔，再下載一個約 0.5–1.6 GB 的模型檔。它在 CPU 上通常比 openai-whisper 快很多，量化模型又更快、更省記憶體。
- **繁體輸出：** Whisper 對中文的訓練資料大多是簡體，所以輸出常是簡體。用提示詞引導不一定有效，**最可靠的做法是轉錄後再用 OpenCC 轉換**。OpenCC 是固定規則轉換，結果每次都一樣。
- **離線：** 模型下載一次之後就完全離線，音檔不會上傳。

說明一下來源：我先查了 pickfit，它驗證過的工具裡沒有適合這個需求的。最接近的 babelscribe 主打 GPU，也沒有中文或 CPU 加速的資訊，所以我不推薦。whisper.cpp、OpenCC 和下面的 faster-whisper 都是有名的開源專案，但**pickfit 沒有驗證過它們**，以下步驟來自我對這些專案的了解，我沒有實際跑過。

---

## 安裝步驟（只需連網一次）

```bash
# 1. 系統套件（需要 sudo）
sudo apt install build-essential cmake git ffmpeg opencc

# 2. 下載並編譯 whisper.cpp
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release

# 3. 下載模型（擇一）
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0   # 推薦：品質好、CPU 上還算快（約 550 MB）
# sh ./models/download-ggml-model.sh small               # 舊筆電或想更快時用，準確度較低
```

如果 `opencc` 指令裝好後不存在，請另外裝 `opencc` 或 `opencc-tools` 套件，不同發行版的套件名稱不一樣。

## 第一次使用

```bash
# 1. 轉成 whisper.cpp 需要的 16 kHz 單聲道 WAV
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄並輸出 SRT（會產生 meeting.srt）
./build/bin/whisper-cli \
  -m models/ggml-large-v3-turbo-q5_0.bin \
  -f meeting.wav \
  -l zh \
  -t 8 \
  --prompt "以下是一場會議的逐字稿，使用繁體中文。" \
  -osrt -of meeting

# 3. 轉成台灣繁體（含用詞，例如 軟件→軟體、信息→資訊）
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

**參數說明：**
- `-t 8`：設成你 CPU 的實體核心數。
- `--prompt`：讓模型偏向輸出繁體，也會加上比較多標點。可以放進會議會出現的人名或專有名詞，提高辨識準確度。
- `-c s2twp.json`：除了轉字，也會換成台灣用詞。如果只想轉字、不改用詞，改用 `s2tw.json`；香港用法請用 `s2hk.json`。
- OpenCC 只改文字，不會動到 SRT 的時間軸。

**快速測試：** 先剪 2 分鐘試跑，看速度和品質是否可以接受：
```bash
ffmpeg -i meeting.m4a -t 120 -ar 16000 -ac 1 test.wav
```

**長錄音的小技巧：**
- 如果出現同一句話一直重複，可以加上 `-mc 0`，讓模型不參考前文。
- 太慢的話就換成 `small` 模型。

---

## 備選：faster-whisper（如果你想繼續用 Python）

`whisper-ctranslate2` 的參數和 openai-whisper 幾乎一樣。它底層用 CTranslate2，**不需要 PyTorch**，用 CPU 的 int8 模式也會快很多。

```bash
python3 -m venv ~/fw && source ~/fw/bin/activate
pip install whisper-ctranslate2

whisper-ctranslate2 meeting.m4a --model large-v3-turbo --language zh \
  --compute_type int8 --threads 8 --vad_filter True \
  --initial_prompt "以下是一場會議的逐字稿，使用繁體中文。" \
  --output_format srt --output_dir .

opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
```

- 第一次執行會從 Hugging Face 下載模型，之後就可以離線使用。
- `--vad_filter True` 會跳過靜音段落，能加快速度，也比較不會在靜音處憑空產生文字。

---

## 補充

- **台灣口音：** 聯發科的 **Breeze-ASR-25** 是針對台灣華語和中英夾雜調整過的 Whisper 模型，可能更準。不過它是 large 尺寸，在 CPU 上會比 turbo 慢，而且要先轉成 ggml 或 CTranslate2 格式才能用在上面兩個工具，比較麻煩。建議先用 turbo，不滿意再試它。
- **速度：** 實際速度看你的 CPU。q5_0 的 turbo 模型在近幾年的 4–8 核筆電上，通常能做到接近或快於錄音本身的長度，但我沒有在你的機器上測過，請以 2 分鐘的測試結果為準。