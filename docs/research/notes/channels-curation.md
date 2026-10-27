2026-10-28 · 策展、彙整與公開資料集（awesome 清單、開發者週報、GitHub trending 替代、GH Archive、BigQuery、ClickHouse、OSS Insight、Terminal Trove、Hugging Face trending、ecosyste.ms） · 由調研 agent 撰寫，待主控者整合

# 管道調研：策展、彙整與公開資料集

需求來源：[brief.md](../../brief.md) 第 4、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期一律是 2026-10-28（台北），也就是 2026-10-27 UTC。條款引用是原文摘錄，解讀只供產品決策參考，不是法律意見。

## 一句話結論

**「星數剛開始長」這個訊號，在 2026-10 已經沒有便宜的公開資料集可以直接算。** GitHub 公開事件流在 2025-10 之後大幅縮水，GH Archive、BigQuery、ClickHouse playground、OSS Insight、Changelog Nightly、ecosyste.ms Timeline 都跟著失準或停更（實測數字見第 3 節）。能便宜、條款風險較低地拿到早期訊號的只剩兩類：

1. **自己用 GitHub API 算**：search API 找「近 N 天建立、星數在某區間」的 repo，每天存一次星數做差分；要細看成長曲線再用 stargazers API 的 `starred_at`。（search API 的細節在 [channels-hosting.md](channels-hosting.md) 2.1。）走 API 只是避開 scraping；資料用途是否在 GitHub AUP §7 的列舉內仍有解讀空間（見 2.15 查核更正）。
2. **活躍、低門檻的策展清單的 git diff**：`rothgar/awesome-tuis`（CLI/TUI）近 90 天新增 51 筆、`EndoTheDev/awesome-ollama`（本地 AI）新增 43 筆（查核更正：原寫 54，其中 11 個是舊項目換成 GitHub 連結），新增項目的星數中位數只有 42 與 12。兩份都**沒有授權**，只能拿連結當發現訊號，不能轉載描述。

**任務指定的三份 CLI 清單都不能當新作品來源**：`awesome-cli-apps` 已封存（archived），`awesome-shell` 最後 commit 是 2024-02，`terminals-are-sexy` 是 2022-04。

> **環境限制（影響怎麼重跑）**：這個雲端 session 的出口代理只放行 `api.github.com` 上 `ncchen99/pickfit` 這一個 repo，其他 repo 與 `/search/*` 都回 403（與 [channels-hosting.md](channels-hosting.md) 相同）。所以本筆記的 repo 中繼資料（星數、建立日期、是否封存）改用 `git clone`（可用）＋ [ecosyste.ms](https://repos.ecosyste.ms) API 取得，並用 OSS Insight 的 GitHub 代理端點交叉確認了 `awesome-cli-apps` 的封存狀態。`github.com` 網頁本身也是 403。

---

## 1. 比較表

整合成本以「一個人、已有 Python 骨架」估。「黑客松接」＝11/4 前值得做；「之後擴充」＝有用但不是 demo 主線；「避開」＝條款、資料品質或成本不划算。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制（ToS／授權／費用／rate limit／權限） | 整合成本（人時） | 建議 |
|---|---|---|---|---|---|---|---|
| **rothgar/awesome-tuis** | **高**：人工收錄、門檻低，新增項目星數中位數 42 | 多：近 90 天 +51（57 commits） | 中：混入遊戲、玩具專案 | git（README.md diff） | **沒有授權檔**：只能用連結（事實），不能轉載描述 | 2（與其他清單共用腳本） | **黑客松接**（CLI 主力訊號） |
| **EndoTheDev/awesome-ollama** | **中高**：新增多為小專案（星數中位數 12），表格有 Install、License 欄 | 中：近 90 天 +43 個新項目（另有 11 個舊項目改成 GitHub 連結，URL diff 會誤算成 54），集中在 2026-10-16 一天批次加入 | 中：品質不一，維護者 10-16 才剛清掉 24 筆死專案 | git（README 表格 diff） | **沒有授權檔**：同上，只取連結 | 0.5（同一支腳本） | **黑客松接**（本地 AI 主力訊號） |
| agarrharr/awesome-cli-apps | 中：有門檻（>3 個月、>20 星），新增項目星數中位數 219 | **無**：2026-10 已封存（最後 commit 2026-10-12）；封存前 90 天 +24 | 低 | git／awesome.ecosyste.ms | **CC0**（README 授權段） | 0.5（一次性匯入） | **黑客松接（一次性）**：當約 550 筆 CLI 種子（560 是不重複 URL 數）與「已知工具」對照組 |
| alebcay/awesome-shell | 低：停更 | 無：最後 commit 2024-02-20 | 低 | git | CC0 | — | **避開**（要種子可順手匯入） |
| k4m4/terminals-are-sexy | 低：停更 | 無：最後 commit 2022-04-13 | 低 | git | CC0 | — | **避開** |
| toolleeo/awesome-cli-apps-in-a-csv | 中：CSV 好解析，2,202 筆 | 少：近 90 天 +1 | 中 | git（`data/apps.csv`） | **沒有授權** | 0.5 | **之後擴充**（只當已知清單） |
| sindresorhus/awesome | 低：清單的清單，不是工具 | 無：近 90 天新增連結 0 | — | git | CC0 | — | **避開**（只用來找清單） |
| awesome-selfhosted（-data） | 中：每筆是 YAML，含星數、最新 release、每月 commit 數 | 中：近 90 天 +52；但規定「首次 release 超過 4 個月」 | 低 | git（`software/*.yml`） | **CC BY-SA 3.0**；GenAI 類只有 13 筆、IDE 類 12 筆 | 1 | **之後擴充**（不是兩個 demo 類別的重點） |
| rafska/awesome-local-llm | 低（對「沒人知道」而言）：新增 repo 星數中位數 9,388 | 中：近 90 天 +54 個連結，GitHub repo 只 10 個 | 中：大量是部落格與模型 | git | MIT | 0.5 | **之後擴充**（當「已知工具」過濾） |
| vince-lam/awesome-local-llms | 低：爬蟲自動生成的指標表，新增 repo 星數中位數 14,268 | 中：表格每次重生，連結變動大 | 高：混入與本地 LLM 無關的高星 repo | git | MIT | — | **避開**當發現來源 |
| janhq/awesome-local-ai | 低：停更 | 無：最後 commit 2024-11-13 | — | git | 沒有授權 | — | **避開** |
| Shubhamsaboo/awesome-llm-apps | 低：是教學範例集，程式碼在 repo 裡，不是第三方工具目錄 | 少：外部連結只有 16 個 | — | git | Apache-2.0 | — | **避開** |
| ollama README「Community Integrations」 | 中：都真的整合 Ollama | 少：171 個連結，近 90 天 +7 | 低 | git | MIT（repo 授權） | 0.5 | **之後擴充** |
| **Console.dev**（newsletter、API、MCP） | **中高**：人工評測，有公開選擇標準；但偏商業 devtools | 少：每週 2–3 篇評測、約 10 個 beta；共 484 個工具，Terminal 類 85、AI 類 35 | 低 | RSS（3 條）、免金鑰 API、MCP、`/reviews/index.json` | 「may be queried and used ... for the purposes of evaluating tools」；**storage、reproducing 要先聯絡**；API 60 次／分／IP（搜尋可能更早被限） | 1（＋寫信） | **之後擴充**（今天先寄信問能否存結構化事實） |
| Changelog News | 中（過去） | **無**：最新一期是 #185（2026-04-29），半年沒新刊 | — | RSS | ToS：「You agree not to copy, republish, frame, download ...」 | — | **避開** |
| Changelog Nightly | 原本**高**（就是「爆紅前的新 repo」） | 幾乎無：2026-10-26 那期只剩 1 個 repo；09-15 還有約 15 個 | — | HTML（nightly.changelog.com/YYYY/MM/DD） | 「All rights reserved」；資料來自 GH Archive，跟著失效 | — | **避開** |
| TLDR（Dev、AI） | 低–中：每期 Dev 約 2–3 個 GitHub repo | 中：週一到五每天一期 | 高：多為新聞、大公司 | RSS（只有標題＋期刊連結）＋期刊 HTML | ToS 沒提自動存取與內容授權；robots.txt `Allow: /` | 2 | **之後擴充**（低優先） |
| Terminal Trove | 中高（CLI 專門目錄），但本次**讀不到** | 未驗證 | 未驗證 | 只有 `blog.xml`（月報）可讀；主站、sitemap、terms 都被 Cloudflare 驗證頁擋（403） | robots.txt `Allow: /`、`Content-Signal: ai-input=yes, ai-train=yes`；ToS 內容**未驗證**；不要繞過 Cloudflare | — | **之後擴充**（寫信問 feed／API） |
| This Week in Rust | 中高：Crate of the Week＋「CFP - Projects」多為新、低星專案 | 少：近 30 天 13 個非 rust-lang 的 repo | 低 | RSS／Atom | 內容 **CC BY-SA**（README） | 1 | **之後擴充**（量小、只有 Rust） |
| Golang Weekly | 中 | 中 | 中 | RSS（全文） | 連結都是追蹤轉址 `golangweekly.com/link/N/rss`，而 robots.txt **`Disallow: /link/`**；Cooperpress ToS（2013-12）未談自動存取 | — | **避開**（解析不到 repo；少數連結的 `title` 只標網域 `github.com`） |
| Python Weekly | — | — | — | **沒有公開 RSS**（beehiiv 頁面 `"rss_feeds":[]`） | — | — | **避開** |
| HelloGitHub | 中：每月約 40 個開源專案，偏中文社群 | 中：月刊；抽樣多為已有上千星 | 低 | RSS（只有摘要）＋ GitHub repo 裡的 Markdown 月刊 | **CC BY-NC-ND 4.0**：不能商用、不能改作，只取連結 | 1.5 | **之後擴充** |
| GitHub trending 頁面 | 中，但多半已經紅了 | — | 低 | 只有 HTML，**沒有官方 API** | 爬 HTML 屬 AUP 定義的 scraping；AUP §7 只明列研究、封存兩種用途（不分 scraped 或 API 取得都一樣，見 2.15 查核更正） | — | **避開** |
| **GitHub search API＋stargazers `starred_at`（自算 trending）** | **高**：直接篩「新、低星、有在動」，再看星數曲線 | 極多 | 高（要靠 topic、星數下限過濾） | API | search 30 次／分、1,000 筆／查詢；core 5,000 次／時；細節見 hosting 筆記 | 4–6（hosting 已估） | **黑客松接（主力）** |
| GH Archive | **低**（2025-10 之後） | 新 repo 事件 **0**；加星事件約為 2024 年的 2% | 高 | 每小時 `.json.gz` | 程式碼 MIT、網站內容 CC BY 4.0；**事件資料本身沒有授權聲明**，README 明寫 repo 不含資料集，且「The dataset includes material that may be subject to third party rights」；免費 | 4–6 | **避開** |
| BigQuery `githubarchive` | 同 GH Archive（同一份資料） | 同上 | — | 公開資料集 | $6.25／TiB，每月前 1 TiB 免費；sandbox 免信用卡；要 GCP 帳號（本 session 沒有憑證，dry-run 未執行） | 3–4 | **避開** |
| ClickHouse playground `github_events` | 低：資料停在 **2026-07-02** | 無 | — | HTTPS SQL（免帳號） | 唯讀、「The service also has quotas on its usage」；條款未查到 | — | **避開** |
| OSS Insight API | 低：trending 已關閉 | 無 | — | API（免金鑰） | 600 次／時／IP、全站 1,000 次／分；**trends 自 2026-03-01 起 unavailable**；多個 v1 端點回 500；條款未查到 | — | **避開** |
| Hugging Face trending | 低（對「沒人知道」）：前 100 名 Space 有 22 個是 14 天內建立，但多是大公司 demo | 中 | 高：模型、展示頁 | API（`sort=trendingScore`） | 匿名 500 次／5 分；ToS 未禁止自動存取（見 hosting 筆記 2.5） | 1 | **之後擴充**（只當本地 AI 的旁證） |
| **ecosyste.ms**（awesome、repos） | 中：把 awesome 清單解析成專案，附星數、建立日期、封存狀態 | 依來源 | 低 | API（免金鑰） | 資料 **CC BY-SA 4.0**（要標示來源，**而且是 ShareAlike**：混用後公開的資料要用同授權釋出；商用另有付費授權，見 2.21）；匿名 5,000 次／時；同步延遲數天；Timeline 服務停在 2025-10-08 | 1 | **黑客松接**（只當開發期 GitHub API 被擋時的備援，不寫進正本資料） |

---

## 2. 各管道細節

### 2.1 rothgar/awesome-tuis（CLI 類首選）

- **新作品**：近 90 天 57 個 commit、新增 51 個連結（全是 GitHub repo）。用 ecosyste.ms 查其中 50 個：星數中位數 42，35 個 <100 星，28 個是一年內建立。這是本次所有清單裡最接近「最近才出現、還沒什麼人知道」的。
- **兩個類別**：CLI 很好用（TUI 是 CLI 的子集，安裝多為單一 binary 或 `cargo install`，適合沙盒驗證）。本地 AI 只零星幾筆。
- **抽樣**：`Alexandro521/Tanko`（94 星，2026-02 建立）、`Cod-e-Codes/marchat`（138 星）、`Bimbok/fyzenor`（14 星）、`13DoesPython/animpy`（5 星）。品質差異大，要靠驗證 agent 把關。
- **授權**：repo 沒有 LICENSE 檔、README 也沒有授權段（ecosyste.ms 的 `license` 也是 null）。沒有授權＝預設保留所有權利。**做法**：只把 repo URL 當「候選」放進管線（URL 是事實，不受著作權保護），描述一律由 Meta 模型讀原 repo 的 README 自己寫，不複製清單的文字。（查核補充：單一 URL 是事實，但整份清單的「選擇與編排」在部分法域可能受編輯著作或資料庫權保護。這段是解讀，**未驗證**、非法律意見。保守做法：只當內部發現訊號，不公開重建整份清單或其分類；黑客松後若要長期用，寫信問維護者。）
- **解析**：`- [name](url) description` 一行一筆，比對兩個版本的 URL 集合就好（`spikes/ch_curation_lists.py awesome`）。

### 2.2 EndoTheDev/awesome-ollama（本地 AI 類首選）

- **新作品**：近 90 天新增 **43 個新項目**，其中 37 筆在 ecosyste.ms 查得到：星數中位數 12，30 筆 <100 星，32 筆一年內建立。
  - 查核更正（2026-10-28）：原文寫「新增 54 筆，查到 46 筆，中位數 22，31 筆 <100 星，33 筆一年內建立」。54 是新 URL 數，其中 11 個 URL 是 12 個舊項目換成 GitHub 連結（`n8n`、`vs code`、`zed`、`goose`、`opencode`、`marimo`、`onyx`、`cline`／`cline cli` 等），不是新作品，還把中位數拉高。依項目名稱比對才準：舊版 91 項、新版 105 項，新名稱 43 個，與 commit 訊息「add 43 tools」一致。重跑：`python3 spikes/ch_curation_verify.py ollama`。
- **注意**：這批新項目是 2026-10-16 一天的批次（commit 訊息「add 43 tools from triaged submission PRs」「prune 24 stale entries」），之前一次更新是 2026-06-24。更新頻率不穩，不能當每日來源，但這次正好給了一批新鮮候選。
- **好處**：表格有 `Install` 與 `License` 欄，CONTRIBUTING 寫「entries are removed when the repo is dead (404), archived, unlicensed, or has had no push for over a year」。對驗證 agent 的安裝步驟是好起點。
- **抽樣**：`Detrol/quorum-cli`（121 星）、`CorvinLabs/CorvinOS`（21 星）、`Acekorneya/POK-Agent`（1 星）、`FabianGallardo-coder/digibuddy`（0 星）。
- **授權**：沒有 LICENSE 檔。做法同 2.1，只取連結。

### 2.3 agarrharr/awesome-cli-apps（已封存）

- **狀態**：ecosyste.ms（2026-10-21 同步）與 OSS Insight 的 GitHub 代理（`/gh/repos/agarrharr/awesome-cli-apps`）都回 `"archived": true`；最後一個 commit 是 2026-10-12「Remove my maintenance note」，刪掉維護者署名。**不會再有新項目**。
- **收錄門檻**（contributing.md）：「Be more than 3 months old.」「Have more than 20 stars (if it is hosted on GitHub.)」「AI-generated PRs are not welcome.」所以就算還活著，也是「已經被一些人知道」的層級。封存前 90 天新增 24 筆，星數中位數 219。
- **授權**：沒有 LICENSE 檔，但 README 的 License 段寫 CC0：「To the extent possible under law, Adam Garrett-Harris has waived all copyright and related or neighboring rights to this work.」符合 brief 第 8 節「CC0 的 awesome 清單：可以」。
- **用法**：一次性匯入約 550 筆（README 清單項目 550 個；560 是不重複 URL 數，含徽章、授權等非工具連結；其中 GitHub repo 515 個），當 (1) CLI 類別的種子資料；(2) 評測時的「已知工具」對照（agent 自己就知道的那群）。

### 2.4 awesome-shell、terminals-are-sexy、sindresorhus/awesome

- `alebcay/awesome-shell`：CC0，378 個連結，預設分支最後 commit 2024-02-20（committer date；author date 2023-11-13）。ecosyste.ms 的 `pushed_at` 是 2025-08-28：查核確認是 dependabot 分支（`dependabot/github_actions/dot-github/workflows/lycheeverse/lychee-action-2.0.2`，commit 2025-08-28T14:40:51Z），預設分支沒動。
- `k4m4/terminals-are-sexy`：CC0，207 個連結，最後 commit 2022-04-13。
- `sindresorhus/awesome`：CC0，689 個連結，是「清單的清單」，近 90 天 3 個 commit、新增連結 0。
- 三者都拿不到新作品。要種子可以一次性匯入（CC0 沒有限制），但不必排進黑客松。

### 2.5 其他 CLI 清單：awesome-cli-apps-in-a-csv

- 2,202 筆，`data/apps.csv` 欄位 `category,name,homepage,git,description`，是最好解析的格式。另有 `abandoned-apps.csv`。
- 但近 90 天只新增 1 筆（`loki-inu/relnote`，1 星）；沒有授權。適合當「已知 CLI」名單，不是發現來源。

### 2.6 awesome-selfhosted（awesome-selfhosted-data）

- 正本在 `awesome-selfhosted-data`，每款軟體一個 YAML，欄位有 `source_code_url`、`licenses`、`platforms`、`tags`、`stargazers_count`、`current_release`、`commit_history`（每月 commit 數）。授權 CC BY-SA 3.0。這個結構跟 brief 第 11 節的檔案欄位很像，可以參考。
- **不適合找新作品**：CONTRIBUTING 寫「first release more than four months old, actively maintained, working installation instructions」，還附了退件範本「Once the first release is four months old, feel free to resubmit」。
- 近 90 天新增 52 筆，查到 51 筆：星數中位數 247，24 筆一年內建立。
- 兩個 demo 類別的覆蓋很少：Generative AI 段 13 筆、Software Development - IDE & Tools 段 12 筆；而且都是要架伺服器的 Docker 服務，不是 CLI。

### 2.7 本地 AI／LLM 清單：哪些最活躍

| 清單 | 星數 | 授權 | commits 30／90／365 天 | 現有項目 | 近 90 天新增 | 新增 repo 星數中位數 |
|---|---|---|---|---|---|---|
| EndoTheDev/awesome-ollama | 492 | 無 | 5／5／6 | 105 | 43（URL diff 算成 54，見 2.2） | **12** |
| rafska/awesome-local-llm | 3,005 | MIT | 22／42／174 | 541 | 54（GitHub 10） | 9,388 |
| vince-lam/awesome-local-llms | 812 | MIT | 14／38／116 | 95 | 57（GitHub 40） | 14,268 |
| ollama/ollama README | 184,491 | MIT | 154／370／1,263（整個 repo） | 171 | 7 | 2,475 |
| Shubhamsaboo/awesome-llm-apps | 143,195 | Apache-2.0 | 44／175／551 | 16 | 1 | — |
| janhq/awesome-local-ai | 2,039 | 無 | 0／0／0 | 121 | 0 | — |

- `rafska/awesome-local-llm`、`vince-lam/awesome-local-llms` 活躍、MIT，但新增的多是已經爆紅的 repo（例如 `TencentCloud/TencentDB-Agent-Memory` 29,751 星、`Niko1221/Strata` 27,515 星）。`vince-lam` 的表是 `scraper/` 自動產生，還混入 `AgriciDaniel/claude-seo` 這類與本地 LLM 無關的 repo。**這兩份適合反過來用**：當「已經有名」的過濾名單。
- `Shubhamsaboo/awesome-llm-apps` 名字像清單，實際是範例程式碼集（`advanced_ai_agents/`、`rag_tutorials/` 等資料夾），不是第三方工具目錄。
- `janhq/awesome-local-ai` 2024-11 之後沒動。
- 星數來源：ecosyste.ms（2026-10-19 至 10-27 同步）。

### 2.8 Console.dev

- **能拿到什麼**：三條 RSS（`/rss.xml`、`/tools/rss.xml`、`/betas/rss.xml`，只有最新一期）、評測更新 feed（`/reviews/feed.xml`）、免金鑰 HTTP API（`/api/v1/tools?q=`）、MCP（`https://console.dev/mcp`，`search_tools`、`get_tool`）、整份評測匯出（`/reviews/index.json`）。限制「API requests and MCP tool calls: Up to 60 per minute」（每 IP），另寫「Searches may be limited sooner」。來源：[developers.md](https://console.dev/developers.md)。
- **查核補充**：developers.md 一邊教人下載整份匯出（「Download the archive ... Keep the snapshot’s review URLs and dates with the content you use」），一邊 API 回應與匯出檔都內嵌 `rights.usageTerms`，寫 storage 要先聯絡。兩者有落差，以版權聲明為準，先寄信再存。
- **實測**：API 全部翻完共 484 個工具，網站是 github.com 的 123 個；分類 Developer Tools 160、Terminal 85、DevOps 84、AI 35；近 90 天評測 26 篇（約每週 2 篇）。betas RSS 本週 10 筆，3 筆連到 GitHub（`kksimp/mac.apk` 610 星、`google-pytorch/torch_tpu`、`perplexityai/space`）。
- **新作品**：beta 是「the release must be pre 1.0」，算新；評測選的是「most interesting」，偏向有商業團隊的 devtools，不是長尾。來源：[Selection criteria](https://console.dev/selection-criteria)。
- **條款**：「Copyright Console 2026. All rights reserved. Reviews may be queried and used by humans and AI for the purposes of evaluating tools, including in commercial contexts, such as finding a tool for use at work. For any other usage, including reproducing reviews, storage, or commercialized usage, please contact hello@console.dev.」robots.txt：`Content-Signal: ai-train=no, search=yes, ai-input=yes`。來源：[about#copyright](https://console.dev/about)、[llms.txt](https://console.dev/llms.txt)、RSS 的 `<copyright>`。
- **對 pickfit 的意思**：在使用者查詢當下呼叫 API「評估工具」看起來在允許範圍；把評測存進我們的資料庫、轉載評語則要先問。透過 pickfit 的 MCP 把評語原文轉給別的 agent，可能算「reproducing reviews」（解讀，未驗證）；回信前只回工具名稱＋評測連結。建議今天寄信給 hello@console.dev，問能不能存「工具名稱＋網址＋評測連結」。
- **兩個類別**：Terminal 類 85 筆對 CLI 有用；AI 類 35 筆多是雲端服務，本地 AI 少。

### 2.9 Changelog News 與 Changelog Nightly

- **Changelog News**：RSS（`/news/feed`）185 筆，最新是 #185「Bitwarden CLI compromised」（2026-04-29）。`/news` 頁面列到的最新一期也是 185。半年沒有新刊（原因未驗證）。主 podcast feed 仍在更新（最新 2026-10-22）。
- **Changelog Nightly**：「unearths the top new and top starred projects on GitHub before they blow up」，正是我們要的訊號，但它用 GH Archive 算。實測 `nightly.changelog.com/2026/10/26` 只剩「Repeat Performers」1 個 repo；`2026/10/20` 5 個 GitHub 連結；`2026/09/15` 約 15 個 repo（不含 trending 頁與 Nightly 自己的 repo）；`2025/10/15` 404。跟 GH Archive 的資料崩落時間一致。
- **條款**（[changelog.com/terms](https://changelog.com/terms)）：「You agree not to copy, republish, frame, download, transmit, modify, adapt, create derivative works based on, rent, lease, loan, sell, assign, distribute, display, perform, license, sublicense or reverse engineer Changelog service or Changelog Materials or any portions of them.」Nightly 頁尾「© Changelog Media, All rights reserved」。
- 結論：兩條都避開。

### 2.10 TLDR

- RSS（`/api/rss/dev`、`/api/rss/ai`、`/api/rss/tech` 等）每個 item 只有標題與期刊頁連結，沒有內文。要拿連結得抓期刊 HTML。
- 實測：Dev 2026-10-27 那期 31 個外連、3 個 GitHub repo（`JetBrains/thinkrail`、`nightly-labs/openbot`…）；10-26 那期 2 個；AI 10-27 那期 0 個。
- 條款（[tldr.tech/terms](https://tldr.tech/terms)）沒提到 scraping、automated、RSS，也沒有 TLDR 自己內容的授權條款；robots.txt `Allow: /`（只擋訂閱管理頁）。可以只取連結，但 GitHub 比例低、雜訊多。

### 2.11 Terminal Trove

- 本次主站、`/new/`、`/terms`、sitemap 都回 Cloudflare「Just a moment...」驗證頁（curl 與 WebFetch 都是 403）。**不要繞過**。能讀到的只有 `blog.xml`（Atom，38 筆月報，最新 2026-10-01），內容是當月「Tool of the Week」，例如 9 月的 `streamtop`、`chroncal`、`jid`、`upmd`；其中 `jid` 是老專案，所以不全是新作品。`<rights>Copyright 2026 Terminal Trove. All Rights Reserved.</rights>`。
- robots.txt：`User-agent: * / Content-Signal: search=yes, ai-input=yes, ai-train=yes / Allow: /`。代表站方歡迎被 AI 讀取，但 Cloudflare 的機器人驗證仍擋自動存取。
- 收錄條件（只看到搜尋摘要，**未驗證**）：偏好跨平台、單一 binary，要附預覽圖、要有 repo 連結。
- ToS 內容**未驗證**（頁面讀不到）。查核時再試：`/`、`/terms`、`/terms/`、`/new/`、robots.txt 列的 `sitemap-index.xml`、`sitemap-0.xml` 都是 403 驗證頁，WebFetch 也是 403；網頁搜尋只找到 terms 頁標題，沒有條文。
- 建議：之後寫信問有沒有 feed 或 API。它的定位（CLI 專門、附安裝方式）跟 pickfit 的 CLI 類別最對口。

### 2.12 This Week in Rust（含 Crate of the Week）

- Atom／RSS 各保留最近 4 期。內容授權：README「Content for this-week-in-rust.org. Made available under CC-BY-SA.」來源：[README](https://github.com/rust-lang/this-week-in-rust)。
- 實測近 30 天 4 期：非 `rust-lang/*` 的 GitHub repo 共 13 個。分布：Crate of the Week 每期 1 個（`alordash/hotcode` 14 星、`velvia/ying-profiler`）；「CFP - Projects」每期 2–4 個找貢獻者的小專案（`lacs-project/sysknife` 16 星、`incyashraj/krate` 22 星、`alessonqueirozdev-hub/manguebyte` 0 星）。
- README 也寫了「We are no longer accepting pull request submissions for the Project/Tooling Updates section」，所以那一段以後會變少。
- 對 CLI 類有用（Rust 寫的 CLI 很多），本地 AI 少。量太小，不值得在黑客松期間接。

### 2.13 Golang Weekly、Python Weekly

- **Golang Weekly**：RSS 有全文，但每個連結都是 `https://golangweekly.com/link/<id>/rss` 追蹤轉址；robots.txt 明寫 `Disallow: /link/`。要知道目的地就得去打這些網址，等於違反 robots。實測近 30 天兩期（10-09、10-23）共 91 個不重複 URL；10-23 那期有 45 個 `/link/` 轉址，其中 3 個的 `title` 屬性標 `github.com`（只有網域，沒有 owner/repo），所以看得出「連到 GitHub」，看不出是哪個 repo。（查核更正：原文寫「那期 91 個外連、0 個能看出是 GitHub」；91 是兩期合計。）若真要用，只能拿連結文字（專案名稱）去 GitHub search API 查，不要打 `/link/`；每期只有 1–3 筆，不值得。Cooperpress ToS（Last updated: December 2013）只有年齡與隱私條款，頁尾「All Rights Reserved」。
- **Python Weekly**：現在在 beehiiv（頁尾「Powered by beehiiv」），頁面資料 `"rss_feeds":[]`，沒有公開 RSS；`/feed` 回 HTML。curl 預設 UA 會被 Cloudflare 擋（403）。
- 兩者避開。

### 2.14 HelloGitHub

- RSS（`hellogithub.com/rss`）是月刊，只有摘要（例如第 126 期「本期共有 39 个项目」）。完整內容在 GitHub repo 的 `content/HelloGitHub126.md`，可用 raw 讀取，實測 40 個 GitHub repo。
- 抽樣 12 個：多數已經有上千星（`QL-Win/QuickLook` 25,380、`Canop/broot` 13,096），一年內建立的有 `Lakr233/vphone-cli`、`OpenMouse-Project/openmouse`、`RayrenSX/iPhoneMirror` 等。偏「中文社群的好專案」，不是「剛出現」。
- 授權：「本作品采用署名-非商业性使用-禁止演绎 4.0 国际 进行许可」（CC BY-NC-ND 4.0）。只能取連結，不能翻譯或改寫描述；pickfit 若商業化要重新評估。

### 2.15 GitHub trending 與官方 API 替代

- 官方沒有 trending API（hosting 筆記查過官方 OpenAPI 824 個路徑）。爬 `github.com/trending` 屬於 AUP 定義的 scraping：「Scraping refers to extracting information from our Service via an automated process, such as a bot or webcrawler. Scraping does not refer to the collection of information through our API.」而 §7 只明列研究（成果需 open access）與封存兩種用途。來源：[GitHub Acceptable Use Policies §7](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)。第三方「trending API」多半也是爬 HTML，一樣避開。
- **查核更正（2026-10-28）**：§7 的用途清單開頭是「You may use information from our Service for the following reasons, regardless of whether the information was scraped, collected through our API, or obtained otherwise」。所以這份清單**不只管 scraped 資料，API 取得的也一樣**；「Scraping does not refer to the collection of information through our API」只是定義，不是豁免。§7 是「你可以…」的列舉，有沒有排除其他用途，條文沒寫明；另外 ToS D.8 寫「these Terms do not restrict lawful access to or use of the contents of public repositories by third parties」，AUP §6 要求「reproduce ... or exploit any portion of the Service」需書面同意。結論：**避開 trending HTML 的理由是「沒有官方 API、屬於 scraping」，不是「API 合規、HTML 不合規」**；走 API 的用途是否被允許有解讀空間（未驗證，非法律意見）。這點與 [channels-hosting.md](channels-hosting.md) 2.1 的查核更正一致。來源：AUP §6、§7；[ToS D.8](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#8-public-repositories-and-lawful-access)。
- **替代：走官方 API 自己算**（條款風險較低，但用途仍受上面 §7 的解讀影響）。
  1. 每天用 search API 抓 `created:>=<30 天前> stars:5..500 topic:cli`（或 `in:name,description,readme` 關鍵字），存下 `stargazers_count`。隔天再抓一次，差分就是「星數成長」。兩個類別各 10 組 query × 10 頁，每天約 200 次 search（上限 30 次／分），沒問題。
  2. 對進入候選的 repo 打 `GET /repos/{owner}/{repo}/stargazers`，Header `Accept: application/vnd.github.star+json`，回應帶 `starred_at`（官方文件：「Includes a timestamp of when the star was created」）。≤300 星的 repo 只要 3 頁，就能畫出完整星數曲線，不必等兩天。500 個候選約 1,500 次 core 請求（上限 5,000 次／時）。本 session 只能對自己的 repo 測：端點回 200、空陣列（pickfit 還沒有星）。來源：[Starring API](https://docs.github.com/en/rest/activity/starring)。
  3. 黑客松第一天就沒有歷史快照，所以第 2 步比第 1 步重要。

### 2.16 GH Archive

- **格式**：`https://data.gharchive.org/YYYY-MM-DD-H.json.gz`，一行一個 Events API 事件 JSON。首頁：「Each archive contains JSON encoded events as reported by the GitHub API.」
- **授權**：gharchive.org repo 的 README「MIT, for code and documentation in this repository」「www.gharchive.org website content (gh-pages branch) is also released under CC-BY-4.0」。**事件資料本身沒有授權聲明**：查核時讀到同一段 README 明寫「Note this repository does _not_ contain the GH Archive dataset (event archives/data). The dataset includes material that may be subject to third party rights.」，gharchive.org 首頁也沒有資料授權。資料源自 GitHub，使用時仍受 GitHub ToS／AUP 約束。來源：[README Licenses 段](https://raw.githubusercontent.com/igrigorik/gharchive.org/master/README.md)。
- **2025-10 之後的資料**（本次下載實測，見 3.3）：
  - 檔案大小：2024-10-15 15 時 124 MB → 2026-10-27 17–19 時每小時 3.3 MB。
  - `CreateEvent` 的 `ref_type=repository`：2024-10 一小時 10,196 筆；**2025-10-09 起全是 0**（只剩 branch，最近幾小時連 branch 都沒有）。所以「新 repo」不能從事件直接看。查核補充：ClickHouse playground（GH Archive 的鏡像）逐日統計，2025-10-08 還有 105,061 筆，10-09 起 0；10-09 到 10-13 每天事件只剩 1.5–1.9 萬筆，10-15 回到約 350 萬筆但不再有 repository 事件。與 ecosyste.ms Timeline 停在 2025-10-08 一致。重跑：`python3 spikes/ch_curation_verify.py clickhouse`。
  - `WatchEvent`（加星）：2024-10 一小時 9,598 筆；2026-09-15 3,933 筆；2026-10-27 每小時 174–231 筆，約 2024 年的 2%。
  - `PushEvent` 時有時無：2026-10-25 15 時 71,105 筆、10-27 17–19 時 0 筆。
  - GitHub 官方只公告過 2025-10-07 修剪 payload 欄位（[changelog](https://github.blog/changelog/2025-08-08-upcoming-changes-to-github-events-api-payloads/)），沒提事件量。量大減的原因**未驗證**。
- **找「剛出現、星數開始長」的具體做法**（已在 `spikes/ch_curation_gharchive.py` 實作）：GitHub repo ID 遞增，所以下載 30 天前某小時、取 `ForkEvent.payload.forkee.id` 最大值當門檻（實測 1,391,082,587）；最近 N 小時 `WatchEvent` 落在 ID 大於門檻的 repo，就是「30 天內建立、正在被加星」。
- **結果**：最近 3 小時 592 筆加星，落在年輕 repo 150 筆、133 個 repo，單一 repo 最多 5 筆。抽樣 `Gathin23/cleanyourtv`（實際 41,530 星，10 天前建立）、`Zagitta/gpu-unlock`（8,382 星）。**取樣率約 2%，而且偏向已經爆紅的**；拿來排序「剛開始長」沒有意義。
- **運算量**：一小時 3 MB、單核 Python 約 3 秒；一天 24 檔約 80–350 MB（PushEvent 有無差很多）。成本很低，但資料不可靠。避開。

### 2.17 BigQuery `githubarchive`

- 資料集：`githubarchive.day.YYYYMMDD`、`month.YYYYMM`、`year.YYYY`，每小時更新，就是 GH Archive 同一份資料，所以 2.16 的問題全部繼承。
- **費用**（[BigQuery pricing](https://cloud.google.com/bigquery/pricing)）：「The first 1 TiB of query data processed per month is free」，之後「$6.25 / 1 tebibyte」；「a minimum 10 MB data processed per table referenced by the query」。萬用字元查 30 個日表，若每張表各算最低 10 MB，就是 300 MB（推算）。
- **Sandbox**（[docs](https://docs.cloud.google.com/bigquery/docs/sandbox)）：「lets you experience BigQuery without providing a credit card or creating a billing account」，同樣 1 TiB／月；「tables, views, and partitions automatically expire after 60 days」。
- **dry-run 未執行**：本 session `gcloud auth list` 是「No credentialed accounts」，`bq ls` 回「Invalid Credentials」。要測需要 Google 帳號＋一個 GCP 專案（`gcloud auth login`、`gcloud config set project <id>`）。要跑的指令：

  ```bash
  bq query --dry_run --use_legacy_sql=false '
  SELECT repo.name, COUNT(*) AS stars
  FROM `githubarchive.day.2026*`
  WHERE _TABLE_SUFFIX BETWEEN "0928" AND "1027"
    AND type = "WatchEvent" AND repo.id > 1391082587
  GROUP BY 1 ORDER BY 2 DESC LIMIT 100'
  ```

  估計（**未驗證**）：只讀 `type`、`repo.id`、`repo.name` 三欄，以 2026-10 每天 10 萬–300 萬列計，30 天在數 GB 以內，遠低於 1 TiB；`payload` 欄位很大，一定不要選。
- 結論：省得了下載，換不到更好的資料。避開。

### 2.18 ClickHouse playground `github_events`

- 端點 `https://play.clickhouse.com/?user=play`，免帳號，HTTPS 直接送 SQL。官方：「The queries are executed as a read-only user」「The service also has quotas on its usage」。來源：[ClickHouse playground](https://clickhouse.com/docs/getting-started/playground)。
- 實測：表 `github_events` 31.7 億列、192 GiB；`max(created_at)` = **2026-07-02 22:59:59**，之後沒有資料。每月 `CreateEvent`（repository）2025-11 起是 0；`WatchEvent` 從 2026-01 的 295 萬筆掉到 2026-06 的 31 萬筆。而且 2024-06 到 2025-08 幾乎沒有資料（每月筆數：2024-01 到 05 各約 1.5 億，2024-06 只有 2 千萬，接著直接跳到 2025-09）。
- 官方 dataset 頁還寫「all events on GitHub from 2011 to Dec 6 2020」，跟實際內容對不上。
- 定位是 demo，不是穩定的資料服務；條款沒有查到。避開。

### 2.19 OSS Insight

- Public API（beta）：「No authentication is required ... Per IP address, the current limit is 600 requests per hour」「There is also a global limit of 1000 requests per minute」。來源：[API docs](https://ossinsight.io/docs/api)。回應標頭 `x-ratelimit-limit: 600` 一致。
- **trending 已關閉**：`/v1/trends/repos/` 回 `row_count: 0`，並附 `data_quality`：「unavailable_since: 2026-03-01」「our capture of those events fell to roughly 0.3% of baseline, so the ordering would be noise」「Totals synced directly from GitHub remain accurate: use /gh/repos/{owner}/{repo}」。
- `/v1/collections`、`/v1/repos/{owner}/{repo}/stargazers/...` 回 500 `{"message":"Request failed with status code 401"}`。`/gh/repos/{owner}/{repo}` 能用（是 GitHub API 代理）。
- 條款與資料授權**未查到**。避開。

### 2.20 Hugging Face trending

- `GET /api/spaces?sort=trendingScore&direction=-1&limit=100&expand[]=createdAt`；標頭 `RateLimit-Policy: "fixed window";"api";q=500;w=300`（匿名每 5 分鐘 500 次）。
- 實測前 100 名 Space：22 個是 14 天內建立，但多是大公司 demo（`black-forest-labs/flux-3-image-klein`、`ibm-granite/speech-to-decisions`、`fishaudio/Drama-3`）。前 50 名 model 幾乎都是新模型（`deepseek-ai/DeepSeek-V4.1-Flash-1017` 等），不是軟體。
- 條款、Space 的形態、對兩個類別的評估，hosting 筆記 2.5 已寫，這裡不重複。結論一樣：只當本地 AI 的旁證（例如哪些 GGUF 模型正熱，可推論哪些本地執行器會被需要）。

### 2.21 ecosyste.ms（awesome、repos）

- `awesome.ecosyste.ms/api/v1/lists/lookup?url=<github url>` 回清單的中繼資料，`/lists/{id}/projects` 回解析好的專案與 repo 資料（星數、建立日期、topics、license、archived）。`repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{owner}/{repo}` 查單一 repo。
- 授權：ToS「(“The Data”) is subject to a creative commons attribution share-alike license ... attributing ‘ecosyste.ms’ as the source of data when published alongside, or combined with other data.」API 頁「available under CC-BY-SA-4.0 license」。來源：[Terms](https://ecosyste.ms/terms)、[API](https://ecosyste.ms/api)。
- rate limit：回應標頭 `x-ratelimit-limit: 5000`、`x-ratelimit-tier: anonymous`；附 email 可進「polite pool」。
- 限制：同步有延遲（例如 `AienTech/dossier` 在 ecosyste.ms 是 0 星）；`/topics/cli` 回 0 筆，不能拿來搜尋新 repo；Timeline 服務（「Data updated hourly from GH Archive」）最新事件停在 2025-10-08。
- **查核補充：ShareAlike 與商用**。ToS 要求「comply with this licence」，不只標來源；CC BY-SA 是 ShareAlike，混用後公開的資料要用相同授權釋出。[Commercial 頁](https://ecosyste.ms/commercial)寫「Our code and data are licensed (AGPL and CC-BY-SA respectively) to ensure that the community can use the services we provide, free of charge, if you contribute your work back」，「utilise ecosyste.ms' data for your own use」另有付費方案。單一事實（星數、建立日期）是否受這個約束有解讀空間（未驗證）。brief 第 11 節的正本是 git 裡的 YAML，混進 ecosyste.ms 的值就可能讓那份資料受 ShareAlike 約束。
- 用法：**只當開發期** GitHub API 被擋時的中繼資料備援；正本資料的星數、建立日期改用 GitHub API 的值。若真的寫進正本，要在 `sources` 標「ecosyste.ms（CC BY-SA 4.0）」並接受 ShareAlike。

---

## 3. 實測

兩支腳本都只用 Python 標準函式庫（另需 `git`），不需要金鑰。快取放在 `$PICKFIT_CACHE`（預設 `~/.cache/pickfit-spikes`）。查核時另加 `spikes/ch_curation_verify.py`（同樣免金鑰），重現查核更正的數字（見第 6 節）。

### 3.1 `spikes/ch_curation_lists.py awesome`：清單近 90 天新增了什麼

```bash
python3 spikes/ch_curation_lists.py awesome --days 90 --enrich 60   # 約 2 分鐘（13 份清單 blobless clone＋ecosyste.ms 查星數）
```

做法：`git clone --filter=blob:none --no-checkout --shallow-since=<400 天前>`（一年多沒動的 repo 改 `--depth=1`）；「最後 commit」用 committer date，只取「90 天前最後一個 commit」與 HEAD 兩個版本的清單檔，比 URL 集合差異；selfhosted-data 改算新增的 YAML 檔。結果（2026-10-27 UTC 執行）：

| 清單 | 授權 | 最後 commit | commits 30/90/365 天 | 現有項目 | 近 90 天新增 | 其中 GitHub repo |
|---|---|---|---|---|---|---|
| agarrharr/awesome-cli-apps | CC0（README 段落） | 2026-10-12 | 8/24/151 | 560 | 24 | 24 |
| alebcay/awesome-shell | CC0 | 2024-02-20 | 0/0/0 | 378 | 0 | 0 |
| k4m4/terminals-are-sexy | CC0 | 2022-04-13 | 0/0/0 | 207 | 0 | 0 |
| rothgar/awesome-tuis | 無 | 2026-10-11 | 12/57/234 | 724 | 51 | 51 |
| toolleeo/awesome-cli-apps-in-a-csv | 無 | 2026-09-22 | 0/4/468 | 2,202 | 1 | 1 |
| sindresorhus/awesome | CC0 | 2026-09-02 | 0/3/30 | 689 | 0 | 0 |
| awesome-selfhosted/awesome-selfhosted-data | CC BY-SA 3.0 | 2026-10-24 | 58/196/733 | 1,358 | 52 | 52 |
| rafska/awesome-local-llm | MIT | 2026-10-22 | 22/42/174 | 541 | 54 | 10 |
| vince-lam/awesome-local-llms | MIT | 2026-10-26 | 14/38/116 | 95 | 57 | 40 |
| EndoTheDev/awesome-ollama | 無 | 2026-10-16 | 5/5/6 | 105 | 54（真正新項目 43，見查核註記） | 54 |
| janhq/awesome-local-ai | 無 | 2024-11-13 | 0/0/0 | 121 | 0 | 0 |
| Shubhamsaboo/awesome-llm-apps | Apache-2.0 | 2026-10-21 | 44/175/551 | 16 | 1 | 1 |
| ollama/ollama（Community Integrations 段） | MIT | 2026-10-27 | 154/370/1,263 | 171 | 7 | 5 |

新增的 GitHub repo 有多「新」、多「沒人知道」（ecosyste.ms 查星數）：

| 清單 | 查到 | 星數中位數 | 一年內建立 | <100 星 | <1,000 星 |
|---|---|---|---|---|---|
| agarrharr/awesome-cli-apps | 24 | 219 | 15/24 | 8/24 | 19/24 |
| **rothgar/awesome-tuis** | 50 | **42** | 28/50 | **35/50** | 46/50 |
| awesome-selfhosted-data | 51 | 247 | 24/51 | 21/51 | 36/51 |
| rafska/awesome-local-llm | 9 | 9,388 | 5/9 | 1/9 | 1/9 |
| vince-lam/awesome-local-llms | 33 | 14,268 | 29/33 | 0/33 | 3/33 |
| **EndoTheDev/awesome-ollama** | 46 | **22** | 33/46 | **31/46** | 36/46 |
| ↳ 只算真正新項目（查核更正） | 37 | **12** | 32/37 | **30/37** | 34/37 |
| ollama/ollama | 5 | 2,475 | 1/5 | 1/5 | 1/5 |

> 查核註記：上表是 `ch_curation_lists.py` 的原始輸出（2026-10-28 查核時重跑，數字一致）。它比對的是 URL 集合，舊項目換連結也會算成「新增」。awesome-ollama 受影響最大（54 個新 URL 裡 11 個是舊項目換連結），改看「只算真正新項目」那一列；awesome-tuis 的 51 個新 URL 沒有這個問題（清單項目 668 → 718）。「現有項目」欄也是不重複 URL 數，不是清單項目數（例如 awesome-cli-apps 560 個 URL、550 個項目）。

抽樣 5 筆（awesome-tuis）：`13DoesPython/animpy`（5 星，2026-03）、`Alexandro521/Tanko`（94 星，2026-02）、`Avazbek22/DevProjex`（37 星）、`Bimbok/fyzenor`（14 星）、`Cod-e-Codes/marchat`（138 星）。抽樣 5 筆（awesome-ollama）：`Acekorneya/POK-Agent`（1 星）、`CorvinLabs/CorvinOS`（21 星）、`DaveSimoes/CrustAI`（10 星）、`Detrol/quorum-cli`（121 星）、`FabianGallardo-coder/digibuddy`（0 星）。看名字與描述，前者大多是實際可裝的 TUI；後者品質落差大（有 0 星、建立當天就沒再動的）。

### 3.2 `spikes/ch_curation_lists.py feeds`：週報 RSS 近 7／30 天

```bash
python3 spikes/ch_curation_lists.py feeds --days 7
python3 spikes/ch_curation_lists.py feeds --days 30 --enrich   # 抽樣 repo 補星數
```

近 30 天（2026-09-27 之後）：

| 管道 | 全部 item | 最新一筆 | 近 30 天 item | 外連（去重） | GitHub repo（排除週報自己的 org） |
|---|---|---|---|---|---|
| console-tools | 4 | 2026-10-22 | 4 | 4 | 0 |
| console-betas | 10 | 2026-10-22 | 10 | 10 | 3 |
| console-reviews | 50 | 2026-10-22 | 6 | 6 | 0 |
| changelog-news | 185 | **2026-04-29** | 0 | 0 | 0 |
| tldr-dev | 20 | 2026-10-27 | 20 | 20 | 0（要另抓期刊 HTML） |
| tldr-ai | 20 | 2026-10-27 | 20 | 20 | 0（同上） |
| this-week-in-rust | 4 | 2026-10-21 | 4 | 596 | 13 |
| golang-weekly | 4 | 2026-10-23 | 2 | 91 | 0（全是追蹤轉址） |
| hellogithub | 126 | 2026-09-28 | 1 | 1 | 0（全文在 GitHub Markdown） |
| terminaltrove-blog | 38 | 2026-10-01 | 1 | 7 | 0（站內連結） |
| python-weekly | — | — | — | — | 錯誤：不是 RSS（回 HTML） |

近 7 天：Console betas 10 筆（3 個 GitHub repo）、TWiR 1 期（4 個 repo）、TLDR Dev／AI 各 5 期，其餘 0。

抽樣（`--enrich`）：`kksimp/mac.apk` 610 星（2026-05 建立）、`google-pytorch/torch_tpu` 762 星、`perplexityai/space` 1,749 星、`lacs-project/sysknife` 16 星（2026-06）、`alessonqueirozdev-hub/manguebyte` 0 星（2026-10-13）、`incyashraj/krate` 22 星、`alordash/hotcode` 14 星。8 個裡 5 個是一年內建立、<1,000 星；其中低星的都來自 This Week in Rust。

另外手動量的：Console API 共 484 個工具（翻 25 頁，每頁間隔 1.2 秒）；TLDR Dev 兩期各 2–3 個 GitHub repo；HelloGitHub 第 126 期 40 個 repo。

### 3.3 `spikes/ch_curation_gharchive.py`：GH Archive 還能不能用

```bash
python3 spikes/ch_curation_gharchive.py --hours 3 --young-days 30 --baseline 2024-10-15-15
# 不加 --baseline 只下載約 30 MB；加了另外下載約 125 MB
```

| 小時（UTC） | 檔案 MB | 事件數 | WatchEvent | ReleaseEvent | PushEvent | CreateEvent（repository／branch） | ForkEvent |
|---|---|---|---|---|---|---|---|
| 2026-10-27-19 | 3.3 | 3,226 | 174 | 100 | 0 | 0／0 | 41 |
| 2026-10-27-18 | 3.4 | 3,213 | 187 | 134 | 0 | 0／0 | 53 |
| 2026-10-27-17 | 3.4 | 3,251 | 231 | 116 | 0 | 0／0 | 49 |
| 2026-09-27-15（錨點） | 17.9 | 125,787 | 124 | 60 | 104,528 | 0／15,159 | 36 |
| 2024-10-15-15（對照） | 124.4 | 264,940 | 9,598 | 1,485 | 146,350 | 10,196／19,977 | 3,001 |

另外手動統計的小時：2025-10-20 15 時 149,127 筆事件、WatchEvent 2,534、CreateEvent 全是 branch；2026-01-15 15 時 WatchEvent 3,838；2026-09-15 15 時 WatchEvent 3,933；2026-10-25 15 時 WatchEvent 187、PushEvent 71,105。HEAD 查檔案大小：2025-10-10 15 時只有 0.18 MB，2026-10-23 到 10-27 之間每小時在 2.5–14 MB 之間跳動。

ID 門檻 1,391,082,587。最近 3 小時：年輕 repo 有任何事件 2,447 個；WatchEvent 592 筆，其中 150 筆落在 133 個年輕 repo（最多 5 筆）；年輕 repo 的 ReleaseEvent 197 筆。腳本最後也查了：ClickHouse playground 最新事件 2026-07-02 22:59:59、近 30 天 WatchEvent 0；OSS Insight trends `status=unavailable`、`unavailable_since=2026-03-01`。

### 3.4 沒測到的

- GitHub search API、stargazers 的實際星數曲線：本 session 被代理擋（403），腳本在 hosting 筆記的 `spikes/ch_hosting_github.py`，要在念誠的電腦上跑。
- BigQuery dry-run：沒有 GCP 憑證。
- Terminal Trove 主站與條款：Cloudflare 驗證頁。

---

## 4. 結論

### 4.1 黑客松期間值得接

| 項目 | 理由 | 工時 |
|---|---|---|
| **awesome-tuis 與 awesome-ollama 的 git diff → 候選佇列** | 實測最「新、低星」的兩個人工策展來源，正好對上兩個 demo 類別。只取 URL，描述交給 Muse Spark 讀原 README 生成，不碰清單文字的著作權。diff 要用「項目名稱＋URL」比對，只比 URL 會把舊項目換連結當成新增（見 3.1 查核註記） | 2–3（共用一支腳本，每天跑一次） |
| **awesome-cli-apps 一次性匯入（CC0）** | 約 550 筆 CLI 種子；也是評測時「agent 本來就知道」的對照組 | 0.5 |
| **GitHub search API＋stargazers `starred_at`** | 唯一走官方介面、能算「星數剛開始長」的方法（用途是否在 AUP §7 列舉內有解讀空間，見 2.15）；主體已在 hosting 筆記，這裡補「用 `starred_at` 直接畫曲線，不必等快照」 | 2（在 hosting 的 4–6 之外） |
| **ecosyste.ms 當中繼資料備援** | 雲端環境打不到 GitHub API 時，用它補星數、建立日期、封存狀態；CC BY-SA 4.0 是 ShareAlike，只在開發期用，不寫進正本資料（見 2.21） | 1 |
| **寄兩封信**：Console.dev（能否存工具名稱＋連結＋評測連結）、Terminal Trove（有沒有 feed／API） | 兩者都是 CLI 類最對口的人工策展；條款或技術上目前不能直接接，問一下成本很低 | 0.5 |

**rafska/awesome-local-llm、vince-lam/awesome-local-llms 反過來用**：它們收的多是已經上萬星的專案，可以當「知名度高」的名單，幫寶藏分數的知名度那一側定錨（MIT，可用；轉載清單內容時要保留授權聲明）。0.5 人時。

### 4.2 之後擴充

- This Week in Rust（CC BY-SA）的 Crate of the Week 與 CFP - Projects：新、低星、可信，但每週只有 3–5 個。
- HelloGitHub（CC BY-NC-ND）：中文社群好專案，只取連結。
- Console.dev：等回信。API／MCP 免金鑰，也可以在 `find_alternatives` 時即時查（「evaluating tools」屬允許範圍），不落地儲存。
- TLDR Dev：期刊 HTML 有少量 GitHub repo，雜訊多。
- awesome-selfhosted-data：結構化 YAML 很好，但有「首次 release 滿 4 個月」規則，且不是兩個 demo 類別的重點。
- Hugging Face trending：本地 AI 的旁證。
- toolleeo CSV、ollama Community Integrations：當「已知工具」名單。

### 4.3 要避開

| 管道 | 原因 |
|---|---|
| GH Archive、BigQuery `githubarchive`、ClickHouse playground、OSS Insight trends、Changelog Nightly、ecosyste.ms Timeline | 全部依賴 GitHub 公開事件流。2025-10 之後沒有新 repo 事件，加星事件只剩約 2%（OSS Insight 自己說 0.3%），而且時有時無。算出來的「成長」是雜訊 |
| github.com/trending（含第三方 trending API） | 沒有官方 API；爬 HTML 屬 AUP 定義的 scraping（§7 的用途列舉對 API 資料也適用，見 2.15） |
| awesome-shell、terminals-are-sexy、janhq/awesome-local-ai、sindresorhus/awesome | 停更或不是工具清單 |
| vince-lam/awesome-local-llms（當發現來源）、Shubhamsaboo/awesome-llm-apps | 前者自動生成、混雜；後者是範例程式集 |
| Changelog News | 2026-04-29 後停刊，ToS 禁止 copy／download／republish |
| Golang Weekly | 連結全是追蹤轉址，robots.txt `Disallow: /link/`；每期只有 1–3 個連結標 `github.com`，而且看不出 repo |
| Python Weekly | 沒有公開 RSS |
| Terminal Trove 主站自動存取 | Cloudflare 機器人驗證，不要繞過；改寫信 |

### 4.4 給主控者：建議修改 brief

- 第 4.1 節「來源」的「awesome 清單」建議寫明是哪幾份：**awesome-tuis、awesome-ollama（只取連結）＋ awesome-cli-apps（CC0，一次性種子）**。
- 第 8 節「CC0 的 awesome 清單：可以」建議補一行：「沒有授權的清單只取 repo 連結當候選，不轉載描述；CC BY-SA／CC BY-NC-ND 的來源要在 `sources` 標授權。ecosyste.ms（CC BY-SA，ShareAlike）只當開發期備援，不寫進正本。」
- 第 8 節可補「避開」：GH Archive 類資料集（品質，不是條款）、GitHub trending 頁（AUP）、Golang Weekly 轉址（robots）。
- 「寶藏分數」的知名度那一側：可用 rafska／vince-lam 兩份 MIT 清單當「已知」標記。

---

## 5. 來源（查證日期一律 2026-10-28 台北，即 2026-10-27 UTC）

**awesome 清單**（git clone 實測；星數、封存狀態取自 ecosyste.ms API）
- awesome-cli-apps：<https://github.com/agarrharr/awesome-cli-apps>（contributing.md、readme.md 的 License 段）；封存狀態 <https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/agarrharr/awesome-cli-apps>、<https://api.ossinsight.io/gh/repos/agarrharr/awesome-cli-apps>
- awesome-shell：<https://github.com/alebcay/awesome-shell>
- terminals-are-sexy：<https://github.com/k4m4/terminals-are-sexy>
- awesome-tuis：<https://github.com/rothgar/awesome-tuis>
- awesome-cli-apps-in-a-csv：<https://github.com/toolleeo/awesome-cli-apps-in-a-csv>
- sindresorhus/awesome：<https://github.com/sindresorhus/awesome>
- awesome-selfhosted：<https://github.com/awesome-selfhosted/awesome-selfhosted>、<https://github.com/awesome-selfhosted/awesome-selfhosted-data>（CONTRIBUTING.md）
- rafska/awesome-local-llm：<https://github.com/rafska/awesome-local-llm>
- vince-lam/awesome-local-llms：<https://github.com/vince-lam/awesome-local-llms>
- EndoTheDev/awesome-ollama：<https://github.com/EndoTheDev/awesome-ollama>（CONTRIBUTING.md）
- janhq/awesome-local-ai：<https://github.com/janhq/awesome-local-ai>
- Shubhamsaboo/awesome-llm-apps：<https://github.com/Shubhamsaboo/awesome-llm-apps>
- ollama README：<https://github.com/ollama/ollama>
- 找清單用的搜尋結果（二手，只用來列候選）：<https://github.com/homebrewltd/awesome-local-ai>、<https://awesome.ecosyste.ms/lists/janhq%2Fawesome-local-ai>、<https://gittrend.io/repo/rafska/awesome-local-llm>、<https://www.sourcepulse.org/projects/2335378>

**週報與目錄**
- Console.dev：<https://console.dev/rss.xml>、<https://console.dev/tools/rss.xml>、<https://console.dev/betas/rss.xml>、<https://console.dev/reviews/feed.xml>、<https://console.dev/llms.txt>、<https://console.dev/developers.md>、<https://console.dev/selection-criteria>、<https://console.dev/about>、<https://console.dev/robots.txt>、<https://console.dev/api/v1/tools>
- Changelog：<https://changelog.com/news/feed>、<https://changelog.com/news>、<https://changelog.com/feed>、<https://changelog.com/nightly>、<https://nightly.changelog.com/2026/10/26>、<https://changelog.com/terms>
- TLDR：<https://tldr.tech/api/rss/dev>、<https://tldr.tech/api/rss/ai>、<https://tldr.tech/dev/2026-10-27>、<https://tldr.tech/terms>、<https://tldr.tech/robots.txt>
- Terminal Trove：<https://terminaltrove.com/blog.xml>、<https://terminaltrove.com/robots.txt>；條款 <https://terminaltrove.com/terms>（403，未讀到）；收錄條件只見搜尋摘要 <https://terminaltrove.com/submit/>（未驗證）
- This Week in Rust：<https://this-week-in-rust.org/atom.xml>、<https://github.com/rust-lang/this-week-in-rust>（README）
- Golang Weekly：<https://golangweekly.com/rss/>、<https://golangweekly.com/robots.txt>、<https://cooperpress.com/terms/>
- Python Weekly：<https://www.pythonweekly.com/>（beehiiv 頁面）
- HelloGitHub：<https://hellogithub.com/rss>、<https://github.com/521xueweihan/HelloGitHub>（README 授權段、`content/HelloGitHub126.md`）

**資料集與 API**
- GitHub AUP §6、§7：<https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies>；ToS D.8、H：<https://docs.github.com/en/site-policy/github-terms/github-terms-of-service>
- GitHub Starring API（`starred_at`）：<https://docs.github.com/en/rest/activity/starring>
- GitHub Search API：<https://docs.github.com/en/rest/search/search>
- GitHub Events API payload 變更：<https://github.blog/changelog/2025-08-08-upcoming-changes-to-github-events-api-payloads/>
- GH Archive：<https://www.gharchive.org/>、<https://data.gharchive.org/2026-10-27-19.json.gz>（等每小時檔）、<https://github.com/igrigorik/gharchive.org>（README 授權段、LICENSE.md）
- BigQuery：<https://cloud.google.com/bigquery/pricing>、<https://docs.cloud.google.com/bigquery/docs/sandbox>
- ClickHouse：<https://clickhouse.com/docs/getting-started/playground>、<https://clickhouse.com/docs/getting-started/example-datasets/github-events>、`https://play.clickhouse.com/?user=play`（實際查詢）
- OSS Insight：<https://ossinsight.io/docs/api>、<https://api.ossinsight.io/v1/trends/repos/?period=past_week&language=All>（實際回應）
- Hugging Face：<https://huggingface.co/api/spaces?sort=trendingScore&direction=-1&limit=100>、<https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=50>；條款見 [channels-hosting.md](channels-hosting.md) 2.5
- ecosyste.ms：<https://ecosyste.ms/terms>、<https://ecosyste.ms/api>、<https://ecosyste.ms/commercial>、<https://awesome.ecosyste.ms/api/v1/lists>、<https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/>、<https://timeline.ecosyste.ms/>

---

## 6. 查核紀錄（2026-10-28）

查核者：查核 agent（預設懷疑）。查證日期 2026-10-28 台北（2026-10-27 UTC）。方法：官方文件原文、實際打 API、git clone 原始 repo、重跑腳本。本 session 的 `api.github.com` 只放行 `ncchen99/pickfit`、`github.com` 網頁 403，所以 repo 中繼資料用 git、ecosyste.ms、OSS Insight 的 GitHub 代理交叉確認。

### 6.1 逐條結果

| # | 主張 | 判定 | 怎麼查 | 改了什麼 |
|---|---|---|---|---|
| 1 | awesome-cli-apps 已封存、最後 commit 2026-10-12、README CC0、門檻 >3 個月、>20 星 | **正確**；「560 筆」要改 | ecosyste.ms 與 OSS Insight `/gh/repos/...` 都回 `archived: true`、`pushed_at 2026-10-12`；git log 最後 commit `1f85964` 2026-10-12；contributing.md 第 13、14、34 行原文；readme.md License 段 CC0 | 560 是不重複 URL 數；清單項目 550 個、GitHub repo 515 個。2.3、比較表、4.1 改成「約 550 筆」 |
| 2 | awesome-shell 最後 commit 2024-02-20、terminals-are-sexy 2022-04-13、都 CC0、近 365 天沒 commit | **正確** | git log（committer date）；LICENSE／license 檔開頭「CC0 1.0 Universal」；`git ls-remote` | 2.4 的「pushed_at 2025-08-28 可能是其他分支，未驗證」改成已確認：dependabot 分支 |
| 3 | awesome-tuis、awesome-ollama 沒有授權；tuis 近 90 天 +51、查到 50、中位數 42、35 個 <100；ollama +54、查到 46、中位數 22 | **部分錯誤** | 兩個 repo 都沒有 LICENSE 檔，README 也沒有授權段；重跑腳本數字相同；再依「項目名稱」比對 | tuis 正確（清單項目 668 → 718）。ollama 的 54 是新 URL 數，11 個是 12 個舊項目換成 GitHub 連結（n8n、vs code、zed、goose 等）。真正新項目 **43**（= commit 訊息「add 43 tools」），查到 37、**中位數 12**、30 個 <100 星、32 個一年內建立。改 1、2.2、2.7、3.1、比較表 |
| 4 | awesome-selfhosted CC BY-SA 3.0、首次 release 滿 4 個月 | **正確** | awesome-selfhosted-data 的 LICENSE 第一行「Creative Commons Attribution-ShareAlike 3.0 Unported」；CONTRIBUTING.md 第 21、142–154 行 | 無 |
| 5 | Console.dev 免金鑰、60 次／分／IP、條款原文 | **正確**，補兩點 | developers.md「Free to use, with no account or API key」「Up to 60 per minute」；llms.txt、about、API 回應的 `rights.usageTerms` 原文一致；API 實際翻頁 484 個工具、website 是 GitHub 的 123 個 | 補「Searches may be limited sooner」；補 developers.md 教人下載整份匯出、但版權聲明說 storage 要先問的落差；補「經 MCP 轉出評語原文可能算 reproducing，回信前只回名稱＋連結」 |
| 6 | Changelog News 最後一期 #185（2026-04-29）；ToS 原文 | **正確** | RSS 185 筆，第一筆 `link` 是 `/news/185`、pubDate 2026-04-29；主 podcast feed 最新 2026-10-22；terms 原文相符 | 無 |
| 7 | GH Archive 2025-10 起沒有 CreateEvent(repository)；2026-10-27 每小時約 3,200 事件、WatchEvent 174–231；2024-10-15-15 264,940、9,598 | **正確**，日期可更精確 | 重跑 `ch_curation_gharchive.py --baseline 2024-10-15-15`，五個小時的數字全部相同；ClickHouse 逐日查詢 | 起點改成「2025-10-09 起」（10-08 還有 105,061 筆）。GitHub 官方 changelog 只談 payload 修剪（2025-10-07 生效），沒談事件量，原文「原因未驗證」保留 |
| 8 | GH Archive 程式碼 MIT、網站 CC BY 4.0、事件資料沒有授權聲明 | **未驗證 → 已確認** | README Licenses 段原文；首頁沒有資料授權 | 補 README 原文「does _not_ contain the GH Archive dataset ... may be subject to third party rights」，拿掉「未驗證」 |
| 9 | OSS Insight trends 2026-03-01 起 unavailable、約剩 0.3%；600 次／時／IP | **正確** | API 實際回應的 `data_quality` 原文；docs 原文「600 requests per hour」「global limit of 1000 requests per minute」；回應標頭 `x-ratelimit-limit: 600`；`/v1/collections/` 回 500 | 無 |
| 10 | ClickHouse playground 最新事件 2026-07-02 22:59:59；唯讀、有 quota | **正確** | 實際 SQL：`max(created_at)` = 2026-07-02 22:59:59、3,173,399,592 列、192 GiB；每月統計與 2.18 相符；文件原文（網址已轉到 `/docs/get-started/sample-datasets/playground`） | 無 |
| 11 | BigQuery $6.25／TiB、前 1 TiB 免費、每表最少 10 MB；sandbox 免信用卡、60 天過期；本 session 無 GCP 憑證 | **正確** | pricing 頁與 sandbox 頁原文；`gcloud auth list` 回「No credentialed accounts」 | 無。dry-run 仍未執行：需要 Google 帳號＋GCP 專案（`gcloud auth login`、`gcloud config set project <id>`） |
| 12 | AUP §7 對 scraped 資料只明列研究與封存；API 不算 scraping；trending 沒有官方 API | **推論錯** | AUP 原文：用途清單「regardless of whether the information was scraped, collected through our API, or obtained otherwise」 | §7 的列舉對 API 資料也適用。2.15 加查核更正；比較表、4.1、4.3、一句話結論的「合規／合法」改成「走官方介面、條款風險較低」。與 channels-hosting.md 2.1 的更正一致 |
| 13 | stargazers 帶 `star+json` 回 `starred_at` | **正確** | 官方文件原文「Includes a timestamp of when the star was created」、`per_page` 最多 100；對 `ncchen99/pickfit` 實打回 200 | 無 |
| 14 | Golang Weekly 全是 `/link/N/rss` 轉址、robots 擋 `/link/`；Python Weekly 沒有公開 RSS | **大致正確**，一個數字錯 | robots.txt 原文；RSS 解析；pythonweekly.com 頁面 `"rss_feeds":[]`，`/feed`、`/rss` 都 302 到 `/?404=...` | 「那期 91 個外連、0 個能看出是 GitHub」改成：91 是兩期合計；10-23 那期 45 個轉址，3 個的 `title` 標 `github.com`（只有網域）。結論「避開」不變 |
| 15 | Terminal Trove 主站、sitemap、terms 都 403，只有 blog.xml 讀得到；條款未確認 | **維持未驗證** | curl、WebFetch 都 403；robots.txt 列的兩個 sitemap 也 403；網頁搜尋沒有條文 | 只補查核過程；不要繞過 Cloudflare |

### 6.2 另外檢查的事實

| 事實 | 判定 | 來源 |
|---|---|---|
| ecosyste.ms 資料 CC BY-SA 4.0、匿名 5,000 次／時 | 正確，但**漏了 ShareAlike 與商用條件** | [terms](https://ecosyste.ms/terms)「comply with this licence」；[commercial](https://ecosyste.ms/commercial)；回應標頭 `x-ratelimit-limit: 5000`。已改 2.21、比較表、4.1、4.4 |
| ecosyste.ms Timeline 停在 2025-10-08 | 正確 | `timeline.ecosyste.ms` 首頁最新事件 2025-10-08；`/api/v1/events/rothgar/awesome-tuis` 最新 2025-10-08T15:57:52Z |
| 沒有授權的清單「URL 是事實，不受著作權保護」 | 單一 URL 是事實；**整份清單的選擇與編排可能受保護**（解讀，未驗證） | 2.1 補保守做法：只當內部訊號，不公開重建清單 |
| Changelog Nightly 2026-10-26 只剩 1 個 repo、09-15 約 15 個、2025-10-15 404；資料來自 GH Archive | 正確 | 實際抓頁面（09-15 去掉 trending 與 Nightly 自己的 repo 後 15 個）；thechangelog/nightly README 致謝 GitHub Archive、用 BigQuery |
| This Week in Rust CC-BY-SA、不再收 Project/Tooling Updates PR；HelloGitHub CC BY-NC-ND 4.0、第 126 期 40 個 repo | 正確 | 兩個 README 原文；raw 檔實測 |
| TLDR ToS 沒提 scraping／automated／RSS；robots `Allow: /` | 正確 | tldr.tech/terms、robots.txt |
| HF trending 前 100 Space 有 22 個 14 天內建立；匿名 500 次／5 分 | 正確（排名本身會變） | 實打 API；`ratelimit-policy: "fixed window";"api";q=500;w=300` |
| GitHub search 30 次／分、1,000 筆／查詢；core 5,000 次／時 | 正確 | Search API 與 rate limit 官方文件原文 |
| rafska、vince-lam 是 MIT「可直接用」 | 補一句：轉載時要保留授權聲明 | 兩個 repo 的 LICENSE |

### 6.3 腳本重跑

| 腳本 | 指令 | 結果 | 與筆記一致？ | 金鑰 |
|---|---|---|---|---|
| `ch_curation_lists.py awesome` | `--days 90 --enrich 60`，新的空快取 | 跑完，約數分鐘（13 份 blobless clone） | 兩張表的數字**完全一致**；但方法會把「舊項目換連結」算成新增（見 6.1 #3） | 無 |
| `ch_curation_lists.py feeds` | `--days 30 --enrich` | 跑完 | 一致（含 8 個 repo 的星數） | 無 |
| `ch_curation_gharchive.py` | `--hours 3 --young-days 30 --baseline 2024-10-15-15` | 跑完；下載約 155 MB | **完全一致**（同一組小時檔，ID 門檻 1,391,082,587、592／150／133） | 無 |
| `ch_curation_verify.py`（查核新增） | 無參數 | 跑完 | 產出 6.1 #3、#7、#14 的更正數字 | 無 |

注意：GH Archive 腳本用「現在往回找」的小時檔，之後重跑會拿到不同小時，數字會變；比對時用同一組小時。`ch_curation_lists.py` 用本機日期算 90 天窗口，在台北時區跑會差一天。

### 6.4 對結論的影響

- 主結論不變：事件流類資料集全部避開；awesome-tuis、awesome-ollama 的 git diff 仍是最好的早期訊號，而且 ollama 更正後中位數更低（12）。
- 要改的是兩個說法：「走 GitHub API＝合規」（改成「走官方介面、條款風險較低，用途有解讀空間」），以及「ecosyste.ms 標來源即可」（改成「ShareAlike，只當開發期備援」）。
