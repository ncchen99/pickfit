# 建議：Ollama ＋ TAIDE（Llama‑3.1‑TAIDE‑LX‑8B‑Chat）

我沒有在你的電腦上執行任何指令，也沒有修改檔案。

**我的推薦：** 用 **Ollama** 在終端機跑模型，模型選 **TAIDE**。TAIDE 是國科會主導的台灣模型，訓練時刻意加強繁體中文和台灣用語，比 Qwen 這類中國模型更少冒出簡體字。

- **免費、不用註冊：** Ollama 和模型下載都不用帳號。
- **完全離線：** 模型下載後就不需要網路。
- **硬體夠用：** 8B 模型的 Q4_K_M 量化版大約 5 GB，M2 16GB 跑起來很順。
- **簡體字保險：** 另外加裝 OpenCC 這個小工具，把模型輸出強制轉成台灣繁體（例如「软件」會變「軟體」）。

我的假設：
- 你有裝 Homebrew。沒有的話，也可以到 [ollama.com](https://ollama.com) 下載 Mac 版 App，同樣不用帳號。
- 我會用的 TAIDE GGUF 檔是社群轉檔的版本（[tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF](https://huggingface.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF)），不是官方發布的。TAIDE 官方原始版本需要登入 Hugging Face 同意授權，社群轉檔版通常不需要，但我沒有實際測試過。

---

## 安裝步驟

```bash
# 1. 安裝 Ollama 和 OpenCC（OpenCC 用來把簡體轉成台灣繁體）
brew install ollama opencc

# 2. 在背景啟動 Ollama 服務
brew services start ollama

# 3. 下載 TAIDE 模型（約 5 GB，只有這一步需要網路）
ollama pull hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
```

## 設定：固定要求繁中、台灣用語

在任意資料夾建立一個叫 `Modelfile` 的檔案，內容如下：

```
FROM hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
SYSTEM """你是來自台灣的 AI 助理。請一律使用繁體中文與台灣慣用語回答（例如：軟體、程式、網路、影片、資訊、品質），絕對不要使用簡體字或中國大陸用語。"""
PARAMETER temperature 0.6
```

然後建立你自己的模型名稱：

```bash
ollama create tw -f Modelfile
```

## 第一次使用

```bash
# 互動式聊天（輸入 /bye 離開）
ollama run tw

# 只問一題，並用 OpenCC 保證輸出是台灣繁體
ollama run tw "請用三句話解釋什麼是機器學習" | opencc -c s2twp
```

`s2twp` 會轉成台灣正體，並一併換成台灣用語（例如「信息」變「資訊」、「视频」變「影片」）。測試的時候可以把**網路關掉**，確認真的能離線執行。

想更方便的話，可以在 `~/.zshrc` 加一行，之後直接輸入 `問 你的問題` 就好：

```bash
問() { ollama run tw "$*" | opencc -c s2twp; }
```

---

## 備案與注意事項

- **如果 TAIDE 回答品質不好或一直重複**（社群轉檔有時對話範本設定不完整）：可以改用 `ollama pull qwen3:8b`，Modelfile 一樣加上面的 SYSTEM 提示。Qwen 的推理能力比較強，但比較常冒出簡體字，這時候 `| opencc -c s2twp` 就很重要。
- **Ollama 是知名工具**，但不在 pickfit 驗證過的清單裡。pickfit 另外推薦了 [Camelid](https://github.com/timtoole02/Camelid) 和 Xyntetik Runner。兩者都在 M 系列 Mac 上實際裝過，可以離線執行，但都沒有任何繁體中文或台灣用語方面的證據。Camelid 的聊天功能沒有被實際測試過；Xyntetik Runner 只提供 API 服務，還需要另外裝一個用戶端才能在終端機提問。所以我認為對你來說，它們都不如 Ollama ＋ TAIDE ＋ OpenCC 合適。
- **授權：** TAIDE 有自己的使用授權條款。學生自用沒問題，但如果要拿去商業用途，請先讀條款。

Sources:
- [tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF](https://huggingface.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF)
- [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF/tree/main)
- [UOfficeForceX/TAIDE-Llama3（TAIDE 轉 GGUF 供 Ollama 使用）](https://huggingface.co/UOfficeForceX/TAIDE-Llama3)
- [How to run GGUF models from Hugging Face in Ollama](https://webscraft.org/blog/yak-zapuskati-ggufmodeli-z-hugging-face-v-ollama?lang=en)
- [Hugging Face 討論：Running Hugging Face GGUF models in Ollama](https://huggingface.co/spaces/huggingface/HuggingDiscussions/discussions/46)