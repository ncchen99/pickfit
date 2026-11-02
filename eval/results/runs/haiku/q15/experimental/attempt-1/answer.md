## 主要建議：whisper.cpp + OpenCC 轉繁體

**whisper.cpp** 是 Whisper 的 C/C++ 移植版，不需要 PyTorch，在 CPU 上用量化模型跑通常比 openai-whisper 快很多，而且原生支援 `-osrt` 直接輸出 SRT。簡繁問題用 `--prompt` 給繁體範例句引導，再用 OpenCC 把結果轉成台灣繁體。

pickfit 沒有把 whisper.cpp 列為已驗證的推薦，以下是我根據其公開資料整理的內容，沒有在沙箱裡實測。

### 安裝步驟（Linux，需要你自己執行）

1. 安裝相依套件（需要 sudo，請先確認）：
   ```
   sudo apt install build-essential cmake ffmpeg opencc
   ```
2. 取得並編譯：
   ```
   git clone https://github.com/ggml-org/whisper.cpp
   cd whisper.cpp
   cmake -B build && cmake --build build -j --config Release
   ```
3. 下載模型（只在第一次需要網路）：
   ```
   sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
   ```
   CPU 太慢時改用 `small-q5_1` 或 `medium-q5_0`，先用一小段錄音測速再決定。

### 第一次執行

```
# 1. 轉成 16kHz 單聲道 WAV
ffmpeg -i meeting.m4a -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav

# 2. 轉錄成 SRT（簡體）
./build/bin/whisper-cli -m models/ggml-large-v3-turbo-q5_0.bin \
  -l zh -t 8 -osrt -of meeting \
  --prompt "以下是繁體中文的會議逐字稿。" meeting.wav

# 3. 簡體轉台灣繁體（字和用語）
opencc -i meeting.srt -o meeting.tw.srt -c s2twp.json
```

- `-t 8` 設成你的 CPU 核心數。
- 香港用字改用 `-c s2hk.json`。
- 轉錄前把錄音存在本機，全程不需要連網，轉完可以斷網確認。

## 備選：faster-whisper（Python）

如果你比較習慣 Python，可以用 **faster-whisper**（CTranslate2 後端）。它不需要 PyTorch，CPU 上用 int8 量化也很快，同樣可以輸出 SRT 再用 OpenCC 轉換。安裝大約是 `pip install faster-whisper opencc`，並在 `transcribe()` 裡傳入 `language="zh"` 和 `initial_prompt="以下是繁體中文的會議逐字稿。"`。

## pickfit 找到的另一個選項：babelscribe

pickfit 驗證過它能在 Linux x86_64 沙箱裡用 tiny 模型產生 SRT。但它的說明寫的是「使用本機 GPU」，pickfit 也沒有確認它能輸出繁體中文，所以我不建議優先用它。

## 注意事項

- 兩個主要方案都是免費開源、完全離線，音訊不會上傳。
- 簡體問題的根本解法是 `initial_prompt` 或 `--prompt`，OpenCC 負責最後的字形修正。如果轉換後還有少數用詞不對，可以在 OpenCC 之後用自訂詞典補正。
- 目前我只能確定官方文件和社群資料的描述，還沒有在你的機器上測過速度和繁體輸出。第一次跑完，請用一段 5 分鐘的錄音確認速度與字幕品質。

Sources:
- pickfit `find_alternatives` 結果（babelscribe，rec_id rec_3ee453450064416ab56d26c1491ae593）
- whisper.cpp（ggml-org/whisper.cpp）與 faster-whisper 的公開說明（未用網路搜尋再確認）