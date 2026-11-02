# 建議：改用 faster-whisper（`whisper-ctranslate2` 指令）＋ OpenCC 轉繁體

我沒有在你的機器上執行任何東西，以下都是建議。

**假設：** 你用 Ubuntu 或 Debian 系的發行版，有 Python 3.9 以上，會議主要說國語，想要台灣用字。

## 為什麼選這個

- **不用 PyTorch：** faster-whisper 用 CTranslate2 推論引擎，安裝約幾百 MB，不是好幾 GB。
- **CPU 快很多：** 用 int8 量化，同樣的模型一般比 openai-whisper 快大約 3～4 倍，也比較省記憶體。
- **靜音段處理：** 內建 VAD（語音偵測）會跳過沒人講話的段落，比較快，也比較少在靜音時亂生出字。
- **SRT 輸出：** 可以直接輸出 SRT，指令用法跟 openai-whisper 很像。
- **離線：** 第一次下載模型後就能完全離線。錄音一直留在本機，不會上傳。
- **繁體字：** Whisper 沒有「繁體中文」語言選項，`zh` 常常輸出簡體。用繁體的 prompt 可以提高繁體比例，但不保證。最可靠的做法是轉完後用 OpenCC 把 SRT 轉成繁體。OpenCC 只改文字，時間軸不會動。

## 安裝

```bash
# 1. 用 pipx 安裝到獨立環境，不會弄亂系統 Python
sudo apt install pipx opencc
pipx ensurepath          # 然後重開終端機
pipx install whisper-ctranslate2
```

不需要另外裝 ffmpeg，faster-whisper 用 PyAV 解碼 mp3、m4a、wav 等格式。

## 第一次執行

第一次執行需要連網，從 Hugging Face 下載模型，約 0.8～1.5 GB。這一步只下載模型，不會上傳錄音。

```bash
whisper-ctranslate2 meeting.m4a \
  --model large-v3-turbo \
  --language zh \
  --device cpu --compute_type int8 \
  --threads 8 \
  --vad_filter True \
  --condition_on_previous_text False \
  --initial_prompt "以下是繁體中文的會議逐字稿，請使用台灣用語與全形標點。" \
  --output_format srt \
  --output_dir out/
```

- `--threads`：設成你的實體核心數。
- `--condition_on_previous_text False`：可以減少長錄音常見的「同一句一直重複」問題。

## 轉成繁體（台灣用語）

```bash
opencc -c s2twp.json -i out/meeting.srt -o out/meeting.zh-TW.srt
```

- `s2twp`：簡體轉台灣正體，也會轉詞彙，例如「软件」變「軟體」。
- 如果它把人名或專有名詞改錯，可以改用 `s2tw`，只轉字、不轉詞。

## 之後完全離線使用

```bash
export HF_HUB_OFFLINE=1   # 可以加進 ~/.bashrc
```

模型存在 `~/.cache/huggingface/hub`。設了這個變數之後，程式就不會再連網。

## 模型怎麼選（CPU 上）

| 模型 | 速度 | 中文準確度 | 說明 |
|---|---|---|---|
| `large-v3-turbo` | 快 | 好 | 建議先試這個 |
| `medium` | 中 | 不錯 | turbo 在你的錄音上表現不好時，改用這個 |
| `small` | 很快 | 普通 | 筆電很舊、要求速度時用 |
| `large-v3` | 慢 | 最好 | CPU 上通常太慢 |

建議先拿一段 5 分鐘的錄音試 turbo 和 medium，比較速度和錯字。

## 備案

- **whisper.cpp：** 純 C/C++，完全不用 Python。用 `cmake` 編譯，模型下載 `ggml-large-v3-turbo-q5_0.bin`，執行 `whisper-cli -m <模型> -l zh -osrt --prompt "以下是繁體中文的會議逐字稿。" -f meeting.wav`。輸入要先用 ffmpeg 轉成 16 kHz 單聲道 wav。速度跟 faster-whisper 差不多，轉完一樣要用 OpenCC 轉繁體。
- **FunASR / SenseVoice（阿里開源）：** 專門做中文，CPU 上可能更快、中文更準。但輸出成 SRT 時間軸要自己多寫一些設定，輸出也是簡體，同樣要用 OpenCC 轉。faster-whisper 的結果不夠好時再考慮。

## 小提醒

如果會議需要分辨誰在說話，whisper-ctranslate2 有 `--hf_token` 搭配 pyannote 的說話者辨識功能。但那會把 PyTorch 裝回來，跟你想避開的東西衝突，不建議開。