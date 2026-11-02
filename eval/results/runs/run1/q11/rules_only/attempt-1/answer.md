# 建議：用 Ollama 跑 TAIDE（國科會的台灣繁中模型）

**我的假設：** 你要的是在終端機打字問答的聊天模型，不是語音轉文字。你的 Mac 已經有 Homebrew。如果沒有，可以改從官網下載 Ollama 的 App。

**結論：** 用 **Ollama**（免費、開源、不用註冊）載入 **Llama‑3.1‑TAIDE‑LX‑8B‑Chat**。這個模型是國科會 TAIDE 計畫針對台灣用語和繁體中文訓練的，所以比一般的中文模型更不容易冒出簡體字和中國用語。我建議用 Q4_K_M 量化版，檔案約 5.3 GB，在 M2 16GB 上可以跑得很順。只有第一次下載模型需要網路，之後完全離線。

> 說明：我先查了 pickfit 的已驗證工具清單，結果都不符合你的需求，大多是語音轉字幕的工具。所以這個建議 **不是 pickfit 實測過的**。指令是我依照 Ollama 的 Hugging Face 載入方式，和該模型頁面上寫的用法整理的。我沒有在你的機器上執行任何東西。

## 安裝步驟

```bash
# 1. 安裝 Ollama（或到 https://ollama.com 下載 Mac App，不用帳號）
brew install ollama

# 2. 啟動 Ollama 服務（開一個終端機視窗讓它跑著；用 App 的話會自動啟動）
ollama serve
```

## 第一次執行

另外開一個終端機視窗：

```bash
# 下載並啟動 TAIDE（約 5.3 GB，只需要下載一次）
ollama run hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
```

出現 `>>>` 提示字元之後就可以直接用中文問。輸入 `/bye` 離開。

## 進一步固定繁體中文和台灣用語（建議做）

建一個名為 `Modelfile` 的檔案，加上 TAIDE 官方建議的系統提示詞：

```
FROM hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
SYSTEM 你是一個來自台灣的AI助理，你的名字是 TAIDE，樂於以台灣人的立場幫助使用者，會用繁體中文回答問題。
PARAMETER temperature 0.6
```

```bash
ollama create taide -f Modelfile
ollama run taide            # 之後只要打這行就好
```

## 保險機制：用 OpenCC 自動轉成台灣正體

如果偶爾還是出現簡體字或中國用語，可以把輸出交給 OpenCC 轉換。它是離線、免費的開源工具：

```bash
brew install opencc
ollama run taide "請解釋什麼是遞迴" | opencc -c s2twp
```

`s2twp` 除了把字轉成繁體，也會換掉用語，例如「软件」會變成「軟體」，「内存」會變成「記憶體」。不過這種一次問一題的寫法不能連續對話，適合單次提問。

## 注意事項
- **授權：** TAIDE 採用自己的「TAIDE L 類模型社群授權」。學生個人使用沒問題，商業用途請先看條款。
- **記憶體：** 跑模型時大約占 6 GB。建議不要同時開太多瀏覽器分頁。想更快可以改成 `:Q3_K_M`（4.3 GB），但品質會稍微下降。
- **備案：** 如果你比較想要圖形介面，可以用 LM Studio 載入同一個 GGUF 檔。它也是免費、免帳號，但這次沒有驗證過。

Sources:
- [tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF（Hugging Face）](https://huggingface.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF)
- [聯合新聞網：國科會開放具台灣文化的大型繁體中文模型](https://udn.com/news/story/6885/7930892)
- [TechNews：Gemma 3 TAIDE 系列發布](https://technews.tw/2025/08/27/gemma-3-taide-series-launched/)
- [TechNews：TAIDE 模型開發](https://technews.tw/2024/05/03/developing-the-taide-model/)
- [Taiwan LLM 發展概況（2026）](https://cloudinsight.pages.dev/en/blog/taiwan-llm/)