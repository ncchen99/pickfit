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

## 6. 念誠的決定與上線版本（11/3）

念誠看完試跑後決定：**不用 AI 判斷「會不會影響使用者」，改用簡單的是非題**，像 Dependabot 那樣只看有沒有已知弱點。理由有兩個：要 AI 判斷，又會碰到跟視覺嚴重度一樣難校準的評分問題；而且軟體是 pickfit 推薦的，寧可錯殺寶藏，也不讓使用者暴露在已知的風險裡。

- **規則**（`sec.v1`，[pickfit/security.py](../pickfit/security.py)，`pickfit security`）：
  - 使用者實際裝到的套件裡，只要有任何 high 或 critical 弱點，不論有沒有修正版、是不是只造成 DoS，都算；作者架設的網頁，伺服器端的套件也算。
  - 只保留一種過濾：確認查的是使用者會裝到的東西（照全新安裝解析；開發用的相依和文件網站、編輯器擴充這類周邊不算）。
  - RUSTSEC、GO、PYSEC 這類沒有標嚴重度的公告，改用對應 GHSA 的嚴重度，沒有就用 CVSS v3 算；RustSec 的 unmaintained、unsound 只是提醒，不算弱點。
- **後果**：品質最高 79（`known_vulnerability`），所以不能當寶藏；malicious 套件直接下架；工具頁和 MCP 的回答列出弱點與修正版本。
- **掃不到的**：照常保留寶藏，工具頁寫「沒檢查」和原因（念誠決定）。
- **結果**（961 款上線的軟體）：

  | 狀態 | 款數 |
  |---|---|
  | 有已知弱點 | 248 |
  | 沒有已知弱點 | 433 |
  | 掃不到 | 280（沒有 lockfile 151、解析失敗 59、沒有來源 46、lockfile 格式不支援或根目錄有一部分讀不到 24） |

  惡意套件 0 款。79 款分數有變；寶藏從 161 款變成 134 款（少 27 款）。每款的變化見 [security-score-changes.md](security-score-changes.md)。
- **協調 session 審查後的修正**（第一次跑完後發現，修正後全部重掃）：
  - 重建簡介（`pickfit profiles`）時會把 `security` 弄丟，連帶解除 79 分上限；
  - deps.dev 沒有相依圖的 crate 被當成「查過」，沒去讀 repo；
  - 驗證步驟裡裝的前置套件或測試工具被當成軟體本身來查（例如只查了 numpy），而不是軟體自己的套件；
  - agent 或工具資料夾（`.claude/`、`tools/`、`reference/` 等）裡的 lockfile 被算進去；
  - 根目錄的 lockfile 讀不到時，仍然寫「沒有已知弱點」。現在只要有一部分讀不到、又沒找到弱點，就寫「沒檢查」。

  修正前寶藏是 139 款，修正後是 135 款。另外少掉的 4 款是 dreamd、fetchira、mati、rvpm：它們的 Rust 相依原本沒讀到，現在讀到了，也找到了弱點。
- **第二輪審查後改用一條保守的規則**：只有軟體自己的相依完整讀到，才算「沒有已知弱點」。完整讀到是指下列其中一種：
  - 軟體自己的每個套件都解析成功，而且有真正的相依（不是只包一個編譯好的執行檔）；
  - repo 的主要 lockfile（根目錄或下一層）有讀到套件，而且根目錄沒有讀不到的部分。

  其他情況一律「沒檢查」並寫明原因，分數不變；有找到弱點的照樣算有弱點。修正的情況包括：
  - npm 包執行檔的套件（每個平台各一個子套件，例如 `@x/tool-darwin-arm64`）改讀 repo：actual-cli、nika、dryrun 等因此找到 Rust 或 Go 相依裡的弱點；
  - 有任何一個自己的套件解析失敗，就改讀 repo；
  - 包執行檔的套件，如果 repo 沒有 lockfile，就算沒檢查；
  - 沒有固定版本的 requirements.txt 不算讀到；
  - `fuzz/`、`testdata/`、`skills/`、`probes/` 等資料夾不算進去。

  寶藏又少 1 款（actual-cli），變成 134 款。
- **加上 pnpm-lock 支援**（念誠 11/3，為了檢查 demo App OpenPets）：
  - 讀法：只算每個 workspace importer 的 dependencies 和 optionalDependencies，以及它們再帶進來的套件；devDependencies 不算，但 `electron` 例外，因為它的執行環境會打包進 App；文件網站這類周邊的 importer 也不算。
  - 支援 lockfile v6 到 v9；更舊的版本當成讀不到。
  - 結果：之前掃不到的 281 款重掃後，11 款有已知弱點、7 款沒有。
  - **OpenPets 有已知弱點**：讀了 `pnpm-lock.yaml` 裡 755 個執行期套件，有 53 個 high 或 critical 弱點，最嚴重的是 proxy-addr 2.0.7 和 tar 6.2.1，兩個都有修正版。它的品質分原本就是 79.0（不是寶藏），所以分數沒變，只是上限的原因改成 `known_vulnerability`，工具頁會出現警告。
  - 寶藏再少 2 款（stegmoji、xprite，都是網頁），變成 132 款。
  - 最新總數（962 款，含 OpenPets）：有已知弱點 259、沒有 440、掃不到 263（沒有 lockfile 151、解析失敗 58、沒有來源 46、lockfile 格式不支援 8）。
- **還沒算進去的**：225 款有「完全沒有嚴重度」的公告（多半是 RustSec 和 Go，既沒有 GHSA 評級，也沒有 CVSS v3），其中 95 款沒有其他弱點。這些目前不算；念誠決定先不算。
