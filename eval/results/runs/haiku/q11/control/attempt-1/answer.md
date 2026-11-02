## 主要推薦：Ollama + Qwen3 8B

Qwen3 8B 是目前最適合你這台機器的選擇。它的中文能力好，Ollama 官方就有提供，而且 Q4 量化版約 5.2 GB，在 16GB 統一記憶體上跑得動，還能留給其他程式。Ollama 免費、免註冊，在終端機用 `ollama run` 就能對話，模型下載完之後可以完全離線使用。

**需要注意的是**：Qwen3 的預設重心不是繁體中文，偶爾會冒出簡體字。所以下面的步驟會用 system prompt 把它固定在繁體與台灣用語。這是提示詞的約束，無法保證 100% 不出現簡體字，遇到時可以直接再要求它改寫。

### 安裝步驟

1. 安裝 Ollama（二選一）：
   - 到 ollama.com/download 下載 macOS 版並安裝，或
   - 若已有 Homebrew：`brew install ollama`
2. 確認安裝成功：`ollama --version`

### 第一次執行

1. 下載模型（需要網路，約 5.2 GB）：
   ```
   ollama pull qwen3:8b
   ```
2. 建立一個固定繁體與台灣用語的版本。在任意資料夾建立名為 `Modelfile` 的文字檔，內容如下：
   ```
   FROM qwen3:8b
   SYSTEM """你是一位使用台灣繁體中文的助理。請一律使用繁體中文與台灣用語（例如：軟體、資料、網路、影片、計程車、品質），不要使用簡體字。"""
   ```
3. 建立並執行：
   ```
   ollama create tw-qwen3 -f Modelfile
   ollama run tw-qwen3
   ```
4. 進入對話後直接輸入問題。輸入 `/bye` 離開。

### 可選調整

- Qwen3 預設會先輸出思考過程，回答較慢。若想直接看答案，可在對話中輸入 `/set nothink`。
- 若記憶體吃緊，可改用 `qwen3:4b`（約 2.5 GB），回答品質會下降一些。

## 備選：TAIDE（台灣本土模型）

如果你特別在意台灣用語與知識，可以試國科會 TAIDE 計畫的 Llama 3 8B。它是為繁體中文與台灣用語訓練的，但 Ollama 官方庫目前沒有直接提供，要從 Hugging Face 下載第三方轉出的 GGUF 檔，再用 `FROM ./檔名.gguf` 的 Modelfile 匯入。這個做法比較麻煩，而且模型基於 2024 年的版本，較舊。來源可參考 [QuantFactory 的 GGUF 版本](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF) 與 [TAIDE-Llama3 的說明頁](https://huggingface.co/UOfficeForceX/TAIDE-Llama3)。建議先用 Qwen3 上手，覺得台灣用語不夠道地再來試 TAIDE。

## 假設與限制

- 我假設你要的是「能在終端機對話、免費、免帳號」的方案，並沒有實際在你的機器上執行任何指令。
- 模型大小與版本來自網路搜尋的第三方資料，實際下載大小與可用標籤請以 Ollama 官方模型頁為準。
- 我沒有實際測試 Qwen3 在繁體輸出上的表現，建議安裝後先問幾個台灣常用詞（例如「影片」「軟體」「計程車」）確認效果。

Sources:
- [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF)
- [UOfficeForceX/TAIDE-Llama3](https://huggingface.co/UOfficeForceX/TAIDE-Llama3)
- [Qwen3 on Ollama: sizes and tags (glukhov.org / agenticwire.news summaries)](https://glukhov.org/post/2025/06/qwen3-embedding-qwen3-reranker-on-ollama)