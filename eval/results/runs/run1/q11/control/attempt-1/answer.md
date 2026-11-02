## 推薦：用 **Ollama** 跑 **Llama-3-Taiwan-8B-Instruct**（Q4_K_M 量化版）

**為什麼選這個組合：**
- **Ollama** 免費、開源，終端機就能用，不用註冊帳號。下載模型後就能完全離線使用。
- **Llama-3-Taiwan-8B-Instruct** 是台大林彥廷團隊用大量繁體中文和台灣資料調整的模型，用詞偏台灣習慣，例如「軟體、資訊、影片」，不會講成「软件、信息、视频」。有使用者實測說它很守指令、中文也講得更自然，只是做摘要時偶爾會重複跳針。
- 8B 模型的 Q4 量化版大約 5 GB，M2 16GB 跑起來很順，速度大概每秒十幾到二十幾個 token（這是我的估計，沒有實際量過）。
- Hugging Face 上有現成的 GGUF 檔，**公開、不用登入**，Ollama 可以直接從 Hugging Face 下載。

> **我的假設：** 你主要用來問答、寫作、整理資料，不是寫程式或解很難的數學。如果是後兩種，看最後的「備案」。

---

## 安裝步驟（第一次需要網路，之後可以完全離線）

**1. 安裝 Ollama**（二選一）
- 到 https://ollama.com/download 下載 macOS 版，拖進「應用程式」再打開就好，不用登入。
- 如果有裝 Homebrew，也可以用：`brew install ollama`，然後 `ollama serve`（這個視窗要一直開著）

**2. 下載並試跑模型**
```bash
ollama run hf.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF
```
第一次執行會先下載大約 5 GB，下載完就會進入對話模式。輸入 `/bye` 可以離開。

**3. 固定成「台灣繁中模式」（建議做）**
建一個檔案叫 `Modelfile`，內容如下：
```
FROM hf.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF
SYSTEM """你是一位台灣的助理。請一律使用繁體中文與台灣慣用語回答（例如：軟體、網路、影片、資訊、品質），絕對不要使用簡體字或中國大陸用語。"""
PARAMETER temperature 0.6
```
然後執行：
```bash
ollama create tw -f Modelfile
ollama run tw
```
之後每次只要打 `ollama run tw` 就能用。也可以直接單次提問：`ollama run tw "幫我解釋什麼是邊際效用"`

**4. 想百分之百不出現簡體字的話：加 OpenCC 轉換（選用）**
```bash
brew install opencc
ollama run tw "你的問題" | opencc -c s2twp
```
`s2twp` 會把簡體字轉成繁體，也會換成台灣用語，例如「軟件→軟體」。這個方法只適合單次提問，互動對話模式沒辦法這樣接。

---

## 注意事項
- **離線確認：** 下載完成後把 Wi-Fi 關掉，再跑 `ollama run tw`，應該還是能正常回答。
- **如果回答亂掉或答非所問：** 有些社群轉檔的對話範本（chat template）跟 Ollama 不合。這時可以換另一個轉檔版本試試，例如 `hf.co/tliobnih/Llama-3-Taiwan-8B-Instruct-Q5_K_M-GGUF`（大約 5.7 GB，品質稍好一點）。
- **為什麼不推官方 TAIDE：** 國科會 TAIDE 的官方 Hugging Face 頁面需要登入並同意條款，不符合你「不註冊」的條件。社群有轉好的 GGUF（例如 QuantFactory 的 Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF），也可以用 `ollama run hf.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF:Q4_K_M` 試試看。不過這是比較舊的 Alpha 版，而且轉檔者提醒 4-bit 版本可能影響品質。
- **備案（推理能力更強）：** 通用模型像 `ollama run qwen3:8b` 邏輯和程式能力比較好，但很容易跑出簡體字。如果要用它，記得搭配上面的 Modelfile 系統提示加上 `opencc -c s2twp`。

我沒有在你的電腦上執行或修改任何東西。上面的模型路徑是根據 Hugging Face 上目前公開的 repo 寫的，萬一某個 repo 被刪掉，換同名模型的其他轉檔版本就可以。

**資料來源：**
- [phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF](https://huggingface.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF/raw/main/README.md)
- [tliobnih/Llama-3-Taiwan-8B-Instruct-Q5_K_M-GGUF](https://huggingface.co/tliobnih/Llama-3-Taiwan-8B-Instruct-Q5_K_M-GGUF/blob/main/README.md)
- [QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF](https://huggingface.co/QuantFactory/Llama3-TAIDE-LX-8B-Chat-Alpha1-GGUF)
- [lianghsun/Llama-3.2-Taiwan-3B-Instruct-GGUF（Ollama 範本問題）](https://huggingface.co/lianghsun/Llama-3.2-Taiwan-3B-Instruct-GGUF)
- [iThome 鐵人賽：台灣 LLM 實測](https://ithelp.ithome.com.tw/articles/10347843)
- [中央社：TAIDE 釋出 8B 模型](https://www.cna.com.tw/news/ait/202404290314.aspx)
- [Taiwan LLM 發展現況盤點](https://cloudinsight.cc/zh/blog/taiwan-llm)