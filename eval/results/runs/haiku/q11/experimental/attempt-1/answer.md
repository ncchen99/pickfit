## 主要推薦：Ollama + TAIDE LX 8B（Q4_K_M）

TAIDE 是台灣團隊以繁體中文資料訓練的模型，比一般多語言模型更容易得到台灣用語。它是 8B 模型，Q4_K_M 量化版約 5GB，你的 M2 16GB 跑得動。Ollama 免費、在終端機執行，本機使用不需要註冊帳號。

我沒有在 Ollama 官方模型庫找到 TAIDE，所以要自己下載 GGUF 檔再匯入。這個步驟比 `ollama pull` 多幾步，但不需要帳號。

**安裝與設定（請先看過再執行）**

1. **安裝 Ollama**：到 https://ollama.com/download 下載 macOS 版並安裝。也可以用 Homebrew：`brew install ollama`。
2. **下載模型檔**：到 Hugging Face 的 [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF/tree/main) 頁面，下載檔名含 `Q4_K_M` 的 `.gguf` 檔，約 4.9GB。確認檔名後，直接用瀏覽器下載即可。
3. **建立 Modelfile**：在下載資料夾新增一個名為 `Modelfile` 的純文字檔，內容如下（`FROM` 那行的檔名換成你實際下載的檔名）：
   ```
   FROM ./你下載的檔名.gguf
   PARAMETER temperature 0.7
   SYSTEM """你是一位台灣的助理，請一律使用台灣繁體中文與台灣慣用語，例如：軟體、資料、網路、影片、記憶體、程式、資訊。不要使用簡體字或中國大陸用語。"""
   ```
4. **匯入模型**（在該資料夾的終端機執行）：`ollama create taide-8b -f Modelfile`
5. **開始對話**：`ollama run taide-8b`

**第一次測試**：輸入「請用台灣繁體中文，用約 200 字解釋什麼是機器學習。」如果輸出是亂碼或不停重複，代表聊天模板不對。這時可以到 TAIDE 或 Llama 3 的模型卡複製 `TEMPLATE` 設定加到 Modelfile，再重新執行 `ollama create`。

**用字檢查**：如果模型偶爾跑出簡體用語，可以在 SYSTEM 裡加上對照表，例如「軟件→軟體、信息→資訊、內存→記憶體、網絡→網路、視頻→影片、數據→資料、程序→程式」。

## 備案：Qwen3 8B（最省事）

如果你只想快速開始，可以用 Ollama 官方模型庫的 Qwen3 8B，指令是 `ollama run qwen3:8b`。它的中文能力很好，但訓練資料偏向簡體，台灣用語也不一定自然。使用時要像上面一樣設定繁體與台灣用語的 SYSTEM 提示。這個指令我沒有在這次查詢中實際確認，執行前可以先到 ollama.com/library 核對。

## 我的假設

- 你是在 macOS 的「終端機」或 iTerm 中操作。
- 「不付費、不註冊」指的是本機使用。Hugging Face 的這個 repo 我沒有確認是否需要登入，若頁面要求登入，代表它是有限制的 repo，請改用別的檔案或改走備案。
- TAIDE 採社群授權，個人學習使用沒問題，但若要商用或再散布，請先讀授權條款。
- 目前 TAIDE 版本為 Alpha1，較大的 8B 模型回答品質不一定穩定，遇到明顯錯誤時請自行查證。

Sources:
- [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF/tree/main)
- [gonjo9/Llama3-TAIDE-LX-8B-Chat-Alpha1-Q4_K_M-GGUF](https://huggingface.co/gonjo9/Llama3-TAIDE-LX-8B-Chat-Alpha1-Q4_K_M-GGUF/tree/main)
- [mchl914/Llama3-TAIDE-LX-8B-Chat-Alpha1-Q8_0-GGUF（社群授權說明）](https://huggingface.co/mchl914/Llama3-TAIDE-LX-8B-Chat-Alpha1-Q8_0-GGUF/blob/ca08e0947fdc525e2027d1aa97abdb7151e25bfc/README.md?code=true)
- [chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF（備用的台灣繁中模型）](https://huggingface.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF/tree/d512a44e635b1db81ef9640563d3a3667af566de)
- [Ollama 下載頁](https://ollama.com/download)