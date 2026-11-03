# 安全性試跑：已知弱點會不會碰到使用者

2026-11-03 · 念誠要求先做只讀試跑，不改分數、不改紀錄、不發布。

## 1. 要回答的問題

寶藏的相依套件裡有沒有已知弱點（CVE／GHSA），而且**這個弱點會不會碰到照 pickfit 的說明安裝、使用它的人**。如果答案可靠，之後才考慮放進工具頁或計分。

## 2. 掃描（免費，不用模型）

- 有發布到 npm、PyPI、crates 的寶藏：照「今天全新安裝」的方式解析相依（`npm install --package-lock-only --ignore-scripts`、`uv pip compile --no-build`、crates 用 deps.dev），這些指令都不會執行套件的程式碼。解析出的每個版本都拿去 [OSV.dev](https://osv.dev) 查。
- 沒有套件的：shallow clone repo，讀 lockfile。用 pip、uv 從原始碼安裝的 Python 專案，改用 `pyproject.toml` 照今天的版本重新解析。
- 161 款寶藏裡，掃得到的 119 款（全新安裝解析 64 款、repo lockfile 55 款）；掃不到的 42 款：31 款網頁沒有 repo，11 款工具沒有能讀的 lockfile。
- 惡意套件（OSV `MAL-`）：0。

| 篩選 | 有 high／critical 弱點、且已有修正版的寶藏 |
|---|---|
| 照 lockfile 直接數 | 25 |
| 從原始碼安裝的 Python 專案改照今天的版本解析 | Python 的命中 139 → 0 |
| 去掉開發用相依、周邊檔案（網站、編輯器擴充、CI action）、只造成 DoS 的 | 15 |

**最大的誤判來源是 repo 裡過期的 lockfile**：使用者實際安裝時會拿到已經修好的版本。所以要照全新安裝的結果查，不能直接讀 lockfile。

## 3. 相關性判斷（muse-spark-1.3）

- 題目：上一步的 high／critical 命中，以「寶藏 × 套件」為單位，共 129 題，分屬 28 款寶藏：
  - 規則標出的 45 題；
  - 規則濾掉的 84 題當對照（開發用相依、周邊檔案、只造成 DoS 的），正確答案應該是「不相關」。
- 模型讀到的資料：pickfit 對這款軟體知道的事（簡介、功能、安裝方式、在本機還是雲端處理），以及每個套件的 OSV 公告（摘要、細節、CWE）。每個套件給 `exposed`／`conditional`／`not_exposed`，`conditional` 要寫出在什麼用法下才會碰到。
- 參考答案：Claude 在模型跑之前寫好、先 commit（`a89ec16a`）。標了 11 題的例外，其中 7 題標「不確定」。**念誠還沒審。**
- 腳本：[spikes/security_relevance_pilot.py](../spikes/security_relevance_pilot.py)；題目、參考答案、兩次結果都在 `data/calibration/security-relevance-*.json`。

### 結果

| | 第 1 次 | 第 2 次 |
|---|---|---|
| 花費 | $0.22 | $0.21 |
| 模型標出的 45 題，和參考答案一致（相關／不相關） | 38 | 39 |
| 參考答案確定的 38 題 | 36 一致 | 36 一致 |
| 84 題對照被模型判成相關 | 0 | 0 |
| 兩次結果不同 | 129 題裡 1 題（pooprusteek 的 wasmtime） | |

模型判斷相關的（第 1 次）：

| 寶藏 | 套件 | 判斷 | 在什麼用法下會碰到 |
|---|---|---|---|
| privateer-agent | undici | exposed | 一般使用就會碰到：透過 HTTPS 連 AI 服務時，憑證檢查可以被繞過 |
| free-online-tools… | pdfjs-dist | conditional | 打開別人給的 PDF |
| free-online-tools… | @xmldom/xmldom | conditional | 打開來路不明的 XML 類文件 |
| mergegate | gix | conditional | 審查來路不明的 agent 分支或 repo |
| pooprusteek | wasmtime | conditional（第 2 次判 not_exposed） | 執行別人的 wasm |

### 意見不同的題目

- **模型的理由比參考答案好的（4 題，參考答案都標了不確定）**：
  - DOMPurify 的兩個漏洞都要開非預設選項才會觸發；
  - adm-zip 要用 root 執行、而且開了 `keepOriginalPermission`；
  - nlm-memory 沒有處理圖片或解壓縮的功能；
  - all-code 沒有解壓縮的用途。
- **參考答案確定、模型不同意的（2 題）**：
  - homebotbuild 的 Next.js：參考答案認為放在區網上就會碰到，模型指出這些漏洞要開遠端圖片或 OG 圖片產生才會觸發，描述裡看不到這些功能。兩邊都有道理，要看這個 dashboard 實際的設定。
  - free-online-tools 的 xmldom：參考答案套用了「網頁的伺服器端套件不影響訪客」，但文件工具確實會在瀏覽器裡解析 XML，模型的判斷比較對。

## 4. 這代表什麼

1. **流程可行而且便宜**：一次 $0.22。結果穩定（兩次只差 1 題），模型也沒有把規則濾掉的判成相關。
2. **真正會碰到一般使用者的很少**：161 款寶藏裡只有 privateer-agent 1 款；另外 3–4 款是有條件才會碰到。
3. **還不能拿來扣分**：
   - 參考答案是 Claude 寫的，念誠沒審；
   - 確定「相關」的題目只有 4 題，太少，算不出可信的準確率；
   - 對照題本來就是規則濾掉的，判對不難，一致率因此偏高；
   - 有 26% 的寶藏掃不到。

## 5. 建議

- **工具頁可以先「顯示、不計分」**：
  - `exposed` 寫成「已知弱點：某套件某版本，作者升到某版本即可修正（OSV 某日查詢）」；
  - `conditional` 寫成「打開別人給的 PDF 時要注意」這類一句話的提醒；
  - 其餘只寫「OSV 某日查詢：沒有會影響一般使用的已知弱點」。
- **要計分的話，先請念誠審 §3 那 11 題**，再擴大到所有已驗證的軟體（不只寶藏），累積更多「相關」的題目後重新校準。計分方式沿用視覺扣分：只扣不加，`exposed` 才扣。
- **回饋作者**：每個 `exposed` 都附有修正版本，可以提醒作者升級。這一步是對外發言，要念誠同意才做。
