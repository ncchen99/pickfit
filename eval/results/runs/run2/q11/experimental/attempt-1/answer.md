## 建議：Ollama ＋ 台灣的 TAIDE 模型，再用 OpenCC 轉一次字

主要要靠**模型**解決，不是靠工具。Qwen 這類中國模型就算你要求繁體，也常常跑回簡體或大陸用語。**TAIDE** 是國科會主導、用台灣語料訓練的模型，它的 8B 版本 **Llama-3.1-TAIDE-LX-8B-Chat** 在 M2 16GB 上跑得動。

執行工具我建議用 **Ollama**：免費、開源、不用註冊、可以在終端機直接問，模型下載完就能離線使用。

**要先說清楚的地方：**
- 我沒有在你的電腦上執行任何指令。Ollama 也不在 pickfit 測過的清單裡。pickfit 推薦的 Camelid、Xyntetik Runner、TurboLLM 都沒有驗證過繁體中文輸出，Camelid 只測到能安裝、能開啟，所以我沒有選它們。
- 我假設你已經裝好 Homebrew。沒有的話，可以到 [ollama.com](https://ollama.com) 下載 Mac 版 App，效果一樣。
- TAIDE 官方的 Hugging Face 頁面要登入、同意授權才能下載。以下用的是社群轉好的 GGUF 檔（[tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF](https://huggingface.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF)），應該不用帳號。它不是官方發布的，授權是「TAIDE L 類模型社群授權」，自己用或做學業沒問題，商業用途要先看條款。

---

### 安裝步驟

```bash
# 1. 安裝 Ollama 並在背景啟動
brew install ollama
brew services start ollama

# 2. 安裝 OpenCC（簡轉繁、大陸用語轉台灣用語，當保險用）
brew install opencc
```

### 下載模型並設定「台灣模式」

先下載模型。Q4_K_M 約 5.3 GB，16GB 記憶體跑起來剛好：

```bash
ollama pull hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
```

接著建立一個叫 `Modelfile` 的文字檔，把系統提示固定下來：

```
FROM hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
SYSTEM """你是一個來自台灣的AI助理，名字是 TAIDE。請一律使用繁體中文（台灣）與台灣慣用語回答，例如：軟體、程式、網路、影片、資訊，不要使用簡體字或中國大陸用語。"""
PARAMETER temperature 0.3
```

用它建立你自己的模型，名字叫 `tw`：

```bash
ollama create tw -f Modelfile
```

### 第一次使用

```bash
# 互動模式：直接打字問，輸入 /bye 離開
ollama run tw

# 問一句就結束，再交給 OpenCC 轉成台灣用字（s2twp = 簡體轉台灣正體並轉換慣用詞）
ollama run tw "請用三點說明什麼是機器學習" | opencc -c s2twp.json
```

**確認離線也能用：** 下載完成後關掉 Wi-Fi，再執行一次 `ollama run tw`，能正常回答就沒問題了。

---

### 小提醒
- **想讓回答更好：** 可以改用 `:Q5_K_M`（約 6.1 GB），16GB 還跑得動。不建議用 Q8_0（約 9 GB），會跟瀏覽器搶記憶體。
- **OpenCC 是最後一道防線：** TAIDE 本身出現簡體的機率就不高，但偶爾有漏網之魚時，`| opencc -c s2twp.json` 會把「软件／视频」轉成「軟體／影片」。你也可以在 `~/.zshrc` 加上 `ask() { ollama run tw "$*" | opencc -c s2twp.json; }`，之後打 `ask 你的問題` 就能問。
- **備案：** 如果 TAIDE 這個 GGUF 有問題，可以改試聯發科的 Breeze 系列（例如 Breeze-7B-Instruct 的社群 GGUF）。它同樣是針對繁體中文訓練的，換掉 `FROM` 那一行就可以用。
- **不再使用時：** `brew services stop ollama` 會停止背景服務，`ollama rm tw` 會刪掉模型、釋放空間。

Sources:
- [tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF](https://huggingface.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF)
- [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF)
- [MediaTek-Research/Llama-Breeze2-8B-Instruct 討論區](https://huggingface.co/MediaTek-Research/Llama-Breeze2-8B-Instruct/discussions/1)
- [tliobnih/Breeze-7B-Instruct-v1_0-Q4_K_M-GGUF](https://huggingface.co/tliobnih/Breeze-7B-Instruct-v1_0-Q4_K_M-GGUF/raw/main/README.md)