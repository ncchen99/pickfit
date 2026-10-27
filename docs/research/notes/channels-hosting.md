2026-10-28 · 程式碼與模型託管平台（GitHub、GitLab.com、Codeberg、Gitee、SourceHut、Hugging Face Hub） · 由調研 agent 撰寫，待主控者整合

# 管道調研：程式碼與模型託管平台

需求來源：[brief.md](../../brief.md) 第 4、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期一律是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。條款引用是原文摘錄，解讀只供產品決策參考，不是法律意見。

> **先看這條（影響主控者怎麼跑）**：這個雲端 session 的出口代理把 `api.github.com` 綁在 `ncchen99/pickfit` 這一個 repo。`/search/*`、GraphQL、別人 repo 的 `/repos/...` 都回 403（GitHub MCP 的 search 回 502）。所以 **GitHub search 的 7／14 天筆數本 session 量不到**。腳本已寫好，要在念誠自己的電腦上跑（見「實測」）。同一環境裡 `raw.githubusercontent.com` 與 `git ls-remote` 可以用，`codeload.github.com` 與 `github.com` 網頁是 403。這會影響之後在雲端跑發現 agent 與驗證 agent。

---

## 1. 比較表

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制（ToS／授權／費用／rate limit／權限） | 整合成本（人時） | 建議 |
|---|---|---|---|---|---|---|---|
| **GitHub search API**（REST／GraphQL／`gh search`） | **中高**：一次就拿到 stars、topics、license、homepage、created／pushed，能直接做「新、低星、有在動」的篩選 | 極多（官方 Octoverse：每分鐘 230+ 個新 repo，含私有）。兩個類別的 7 天筆數**未實測**（本 session 被擋） | 高：作業、空 repo、AI 生成的 demo；要靠 topic、stars、pushed 過濾 | API | 每個 query 最多 1,000 筆；search 30 次／分；core 5,000 次／時；ToS H 禁止過量與共用 token 繞限；AUP §6、§7 限制資訊用途（見 2.1） | 4–6 | **黑客松接（主力）** |
| **GitHub repo／releases／topics／README** | **高**（當品質訊號）：有沒有 binary release、release 頻率、README 長度 | 逐筆補資料，不是發現來源 | 低 | API；README 也可走 raw.githubusercontent.com | 吃 core 5,000 次／時；`releases/latest` 不含 prerelease、draft | 2–3 | **黑客松接（搭配上一列）** |
| **GitHub events API／GH Archive／BigQuery** | **低**：公開事件流 2025 年後大幅縮水 | 實測 2026-10 每小時檔 **0 筆**新 repo 事件 | — | API（`/events`）、每小時 dump、BigQuery 資料集 | events 只回 300 筆、30 天內，延遲 30 秒–6 小時；BigQuery 要 GCP 帳號（每月 1 TB 免費查詢） | — | **避開** |
| **GitHub trending 頁面** | 中，但偏向已經爆紅的 | 少（未驗證） | 低 | 只有 HTML；官方 REST OpenAPI 824 個路徑沒有 trending | 爬 HTML 不屬於 AUP §7 允許的用途（研究、封存） | — | **避開** |
| **Hugging Face Spaces API** | **低–中**：多數是線上 demo，不是可安裝的工具；「trending 前 1000 名 ∩ 14 天內建立」能撈到瀏覽器端 AI 小工具 | 全站約 1,300 個新 Space／天；本地 AI 關鍵字 7 天約 20 筆 | 高：大量 GGUF 模型展示、BUILD_ERROR、複製品 | API（免金鑰；`sort`、`filter`、`search`、`expand`） | 匿名 500 次／5 分（每 IP），免費帳號 1,000 次／5 分；ToS 未禁止自動存取，robots.txt `Allow: /`；內容授權依各 Space 自己的 license | 2–3 | **之後擴充**（黑客松有空可加一條 query，約 2 人時） |
| **Hugging Face models API** | 低：是模型不是軟體 | 約 5,600 個新 model／天 | 極高 | API | 同上 | — | **不當發現管道**；可當本地 AI 工具的輔助訊號（支援哪些格式、哪些 app） |
| **GitLab.com API** | 低：新 public project 多，但 stars 幾乎都是 0 | 約 0.95–1.35 萬個 public／天；`topic=cli` 7 天 11 筆 | 高 | API（`/api/v4/projects`，`topic`、`search`、`order_by=created_at`；**沒有** `created_after`） | API Terms 1.3.9 **禁止 bulk collection 與「repeated or systematic bulk exporting」**；未登入 `/projects` 400 次／10 分／IP，實測很快 429 | 1–2（只處理使用者貼的連結） | **之後擴充**（只接提交連結，不輪詢） |
| **Codeberg（Forgejo API）** | 中：public 內容一律是自由授權，作者偏開發者；但混入帳號農場類工具 | 少：全站約 1,500 個新 repo／天；`topic:cli` 7 天 15 筆、`topic:llm` 9 筆 | 中 | API（`/api/v1/repos/search`，`sort=created`、`topic=true`；免金鑰） | 回應標頭 2,000 次／600 秒；robots.txt 對所有爬蟲 `Disallow: /api/`，並整站封鎖 GPTBot、ClaudeBot | 1–2 | **之後擴充**（只接提交連結；要定期輪詢先問 Codeberg） |
| **Gitee** | 低：未登入搜尋回 0 筆；不能依建立時間排序 | 未驗證 | 未驗證 | API v5（實際要 access_token） | 標頭 `X-RateLimit-Limit: 60`（未登入）；2022 年起公開 repo 要人工審核（二手來源）；條款頁要 JS 才讀得到，未驗證 | — | **避開** |
| **SourceHut** | 低（量小，未驗證） | 少（未驗證） | — | GraphQL API，一律要 OAuth token | 條款：自動化大量收集**只限**搜尋引擎索引、開放研究、封存，不得營利；且禁止「促進使用 LLM」的內容 | — | **避開** |

---

## 2. 各管道細節

### 2.1 GitHub search API（主力）

- **能不能拿到「最近才出現、沒人知道」的**：可以，這是所有管道裡最直接的。`created:>=YYYY-MM-DD` 抓新建，`pushed:>=` 抓最近有動，`stars:5..300` 同時設品質下限與知名度上限。日期可精確到秒（`created:2026-10-26T00:00:00Z..2026-10-26T11:59:59Z`）。來源：[Searching for repositories](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)。
- **可用的篩選**：`topic:`、`topics:>N`、`language:`、`license:`、`in:name,description,readme`、`fork:`（預設就排除 fork）、`archived:`、`mirror:`、`template:`、`size:`。同一份文件。
- **一次回傳的欄位**：搜尋結果本身就有 `topics`、`license`、`homepage`、`created_at`、`pushed_at`、`stargazers_count`、`forks_count`、`open_issues_count`、`archived`、`description`，不必逐筆再查。來源：[官方 OpenAPI 描述檔](https://github.com/github/rest-api-description) 的 `repo-search-result-item`。
- **1,000 筆上限**：REST「provides up to 1,000 results for each search」；GraphQL「Regardless of the total number of matches, a maximum of 1,000 results will be available」。但 `total_count`／`repositoryCount` 是完整數字。繞法：把 `created:` 切成小段，每段 ≤1,000 再分頁（`spikes/ch_hosting_github.py slice` 有遞迴切半的示範）。repo 搜尋**不能依建立時間排序**（`sort` 只有 `stars`、`forks`、`help-wanted-issues`、`updated`），所以分片是唯一能完整列舉的方法。來源：[REST search](https://docs.github.com/en/rest/search/search)、[GraphQL search](https://docs.github.com/en/graphql/reference/search)。
- **rate limit**：search「30 requests per minute」（已登入）、未登入 10 次；core 一般帳號 5,000 次／時；GraphQL 5,000 點／時；secondary limit 是同時 100 個請求、REST 每分鐘 900 點。query 不能超過 256 字元、不能超過 5 個 `AND`／`OR`／`NOT`。來源：[REST search](https://docs.github.com/en/rest/search/search)、[REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)、[GraphQL limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)。
- **兩個類別好不好用**：CLI 工具很好用（`topic:cli`、`topic:tui`、`topic:terminal` 都是常見 topic）。本地 AI 工具也好用（`topic:local-llm`、`topic:ollama`、`topic:llama-cpp`、`topic:gguf`、`topic:mlx`），但很多作者不打 topic，要補 `in:name,description` 關鍵字。具體 q 字串見第 3 節。
- **條款（ToS H，API Terms）**：「Abuse or excessively frequent requests to GitHub via the API may result in the temporary or permanent suspension of your Account's access to the API.」「You may not share API tokens to exceed GitHub's rate limitations.」「You may not use the API to download data or Content from GitHub for spamming purposes...」「GitHub may offer subscription-based access to our API for those Users who require high-throughput access or access that would result in resale of GitHub's Service.」來源：[GitHub Terms of Service §H](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#h-api-terms)（生效日 2026-04-27）。
- **條款（AUP §6、§7）**：§6「You will not reproduce, duplicate, copy, sell, resell or exploit any portion of the Service ... without our express written permission.」§7 只明列兩種用途「regardless of whether the information was scraped, collected through our API, or obtained otherwise」：研究（成果需開放取用）與封存；並定義「Scraping does not refer to the collection of information through our API」。來源：[Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)。**對 pickfit 的意思**：走 API、守 rate limit 是正路；不要爬 HTML；不要整份轉貼 README（ToS D.5 給其他使用者的授權是「through the Service as permitted by GitHub's functionality」，站外再利用要看該 repo 自己的 license）；存的是我們自己抽出的結構化事實＋連回 GitHub；不存 email 等個資，收到移除要求要處理（AUP §8）。brief 第 8 節的「可以；注意 rate limit」建議補上這幾點。

### 2.2 GitHub releases、topics、README（補資料）

- `GET /repos/{owner}/{repo}/releases/latest`：「the most recent non-prerelease, non-draft release」。有 release＋附件＝可能有預編譯 binary，是「裝得起來」的好訊號，也是驗證 agent 的安裝線索。
- `GET /repos/{owner}/{repo}/topics`：搜尋結果已含 topics，通常不用另外打。
- README：`GET /repos/{owner}/{repo}/readme` 或 `raw.githubusercontent.com`。本 session 只有後者能用。
- 成本：每個候選 1–3 次 core 請求。每天幾百個候選，遠低於 5,000 次／時。
- 來源：[Releases API](https://docs.github.com/en/rest/releases/releases)、[官方 OpenAPI](https://github.com/github/rest-api-description)。

### 2.3 GitHub events API、GH Archive、BigQuery（避開）

- 官方文件：`/events`「The timeline will include up to 300 events. Only events created within the past 30 days」、「This API is not built to serve real-time use cases. Depending on the time of day, event latency can be anywhere from 30s to 6h.」來源：[Events API](https://docs.github.com/en/rest/activity/events)。
- **實測 GH Archive 每小時檔**（腳本 `gharchive` 子命令）：2024-10 一小時有 10,466 筆「新 repo」事件，2025-06 有 6,629 筆，**2025-10 之後是 0**；2026-10-26 那一小時總事件只剩 2,780 筆，PushEvent 也是 0。檔案大小從 2025-03 的 152 MB 掉到 2026-10 的 2.8 MB。
- 第三方佐證：OSS Insight 的 trends API 直接回「unavailable_since: 2026-03-01 ... our capture of those events fell to roughly 0.3% of baseline」（實際 API 回應，見「來源」）。
- GitHub 官方只公告過 2025-10-07 移除部分 payload 欄位（[changelog](https://github.blog/changelog/2025-08-08-upcoming-changes-to-github-events-api-payloads/)），**沒有找到**移除新 repo 事件的公告。原因未驗證，但結果是：靠事件流找新 repo 這條路已經不通。

### 2.4 GitHub trending 頁面（避開）

- 官方 REST OpenAPI 描述檔（v1.1.4，824 個路徑）沒有任何 trending 端點，搜尋類只有 `/search/{code,commits,issues,labels,repositories,topics,users}`。
- 唯一取得方式是爬 `github.com/trending` HTML，不屬於 AUP §7 允許的用途；而且 trending 上多半已經不是「沒人知道」的作品。
- 想要「最近熱起來」的訊號，改用 search：`created:>=<14 天前> stars:>=20 sort=stars`，效果類似，而且合規。

### 2.5 Hugging Face Hub

- **API**：`GET /api/spaces`、`GET /api/models`，參數 `sort`（`createdAt`、`likes`、`trendingScore`、`lastModified`，models 另有 `downloads`）、`direction=-1`、`filter`（tag）、`search`（比對 id）、`author`、`limit`（實測可到 1,000）、`expand[]=`；分頁用 `Link` 標頭的 cursor。另有 `/api/trending`、`/api/spaces/semantic-search`（實測結果不穩，有時回空陣列）。models 可用 `apps=ollama` 篩出支援某個本地 app 的模型。來源：[huggingface_hub HfApi 參考](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)、[Hub API](https://huggingface.co/docs/hub/api)、實際 API 回應。
- **本地 AI 工具在 HF 上的樣子**：不是可安裝的軟體，而是三種東西：(1) `sdk: static`＋`webgpu`／`transformers.js` tag 的瀏覽器端 AI 小工具（例如 `gradium/phonon`「Text-to-speech that runs in your browser」，10-20 建立、51 likes）；(2) 包著 Ollama／GGUF 的 gradio／docker demo，多數品質低、常 BUILD_ERROR；(3) 模型本身。真正的本地 AI 執行器（llama.cpp、Ollama、Jan、LM Studio）在 HF 上是「Local Apps」整合清單，都是已經有名的。來源：[Local Apps](https://huggingface.co/docs/hub/local-apps)。
- **能不能拿到新的、沒人知道的**：用 `sort=createdAt` 量很大但幾乎全是雜訊；用 `sort=trendingScore` 取前 1,000 名再留「14 天內建立」的，品質明顯較好（實測 124 個，其中 10 個像本地／瀏覽器端 AI）。
- **對兩個類別**：CLI 工具幾乎沒有（`search=cli` 會比對到 `client`）。本地 AI 只適合「瀏覽器端、免安裝」那一小群；pickfit 的沙盒安裝驗證用不上，要改成 headless 瀏覽器驗證。README 有連到 GitHub repo 的只有 6／20（7 天內），可以順藤摸瓜回 GitHub。
- **rate limit**：「Anonymous user (per IP address)」API 500 次、Free user 1,000 次、PRO 2,500 次，都是 5 分鐘窗；實測標頭 `RateLimit-Policy: "fixed window";"api";q=500;w=300`。來源：[Hub Rate limits](https://huggingface.co/docs/hub/rate-limits)。
- **條款**：ToS 全文沒有 scrape、crawl、automated 等禁止字樣；robots.txt 是 `User-agent: * / Allow: /`。公開內容的授權是「If you decide to set your Repository public, you grant each User a perpetual, irrevocable, worldwide, royalty-free, non-exclusive license to use, display, publish, reproduce, distribute, and make derivative works of your Content through our Services and functionalities」，並且「When Content contains notice of a reasonable and customary license, (such as an open source license) such Content is intended to remain under the terms of such license」。站外再利用要看各 Space 的 `license`。來源：[HF Terms of Service](https://huggingface.co/terms-of-service)（Effective 2022-09-15）。
- **即時通知**：Webhooks 可以監看「specific repos or ... all repos belonging to particular set of users/organizations」，不能監看全站新建。來源：[Webhooks](https://huggingface.co/docs/hub/webhooks)。

### 2.6 GitLab.com

- **API**：`GET /api/v4/projects?visibility=public&order_by=created_at&sort=desc&topic=cli`；可用 `search`（name、path、description 的子字串）、`last_activity_after`；**沒有 `created_after`**（官方參數表沒有；實測帶了也被忽略，結果仍有 10-20 以前建立的 project）。offset 分頁最多 50,000 筆。來源：[Projects API](https://docs.gitlab.com/api/projects/)。
- **量與品質**：全站最新 100 個 public project 只橫跨 11–15 分鐘（約 0.95–1.35 萬個／天）；但 `topic=cli` 7 天 11 筆、`topic=llm` 9 筆，stars≥1 的幾乎沒有。抽樣看到 `kpihx-labs/web`（Local-first web investigation CLI）、`checkmk1/checkmk_top`、`weaverlab/git-reconcile` 這類有意思的，也看到同一帳號（`toolmanager244`）4 天內建 6 個內容型 repo（測試用 WAV、輪胎尺寸表）都打上 `cli` topic 的。
- **rate limit**：未登入每 IP 500 次／分；`/api/v4/projects` 未登入 400 次／10 分／IP；搜尋 API 100 次／分。實測在共用出口 IP 下第 2–3 次就 429。來源：[GitLab.com rate limits](https://docs.gitlab.com/user/gitlab_com/rate_limits/)。
- **條款**：API Terms 1.3.9「Not to use the GitLab APIs for the bulk collection or scraping of information, including for repeated or systematic bulk exporting GitLab API Data, except where permitted by applicable law.」1.3.5.2「You will not use, or attempt to use, the GitLab APIs in a manner that exceeds such limitations, including rate limits」。來源：[GitLab API Terms of Use](https://handbook.gitlab.com/handbook/legal/api-terms/)。**定期掃新 project 很可能落在「systematic bulk exporting」**，所以只做「使用者貼 GitLab 連結 → 查單一 project」。

### 2.7 Codeberg（Forgejo API）

- **API**：`GET /api/v1/repos/search?q=cli&topic=true&mode=source&sort=created&order=desc&limit=50`；`X-Total-Count` 給總數；`includeDesc=true` 會比對描述（但 `cli` 會比對到 `client`，雜訊大）。release、topics、activity feed 都有端點。來源：[Codeberg swagger](https://codeberg.org/swagger.v1.json)（Forgejo 16.0.0-dev）。
- **量與品質**：最新 3,000 個 repo 橫跨約 46 小時（約 1,500 個／天）。`topic:cli` 7 天 15 筆、`topic:llm` 9 筆、`topic:ollama` 1 筆。有好東西（`satgo1546/trect` 截圖選區工具、`bebx/blook` CLI 檔案瀏覽器、`gophercore/compiles`），也有**帳號農場工具**：`0xgetz` 一週建 9 個「Bulk-create ... accounts, harvest tokens & cookies」的 repo，而且依 stars 排序時全部排在最前面。這說明 pickfit 需要「違反第三方 ToS 的工具」過濾規則。
- **條款**：ToU §2「Public repository content shall be made available under a copyright licence which gives all natural and legal persons ... the right to use the content for any purpose, including both commercial and non-commercial purposes」，資料再利用最乾淨。§2(5)「In the case of excessive traffic/resource usage ... a warning will normally be issued at first」。來源：[Codeberg Terms of Use](https://codeberg.org/Codeberg/org/src/branch/main/TermsOfUse.md)。
- **robots.txt**：`User-agent: *` 下 `Disallow: /api/`、`Disallow: /*/*/raw/`、`Crawl-delay: 2`，並對 GPTBot、ClaudeBot `Disallow: /`。API 本身沒有條款禁止，但定期輪詢會違背他們公開表達的意願。來源：[codeberg.org/robots.txt](https://codeberg.org/robots.txt)。
- **rate limit**：回應標頭 `ratelimit-policy: "baseline";q=2000;w=600`（2,000 次／10 分，實測，文件未驗證）。

### 2.8 Gitee（避開）

- `GET /api/v5/search/repositories?q=cli` 未登入回 `total_count: 0`；`sort` 只有 `last_push_at`、`stars_count`、`forks_count`、`watches_count`，不能依建立時間。來源：[Gitee OpenAPI swagger](https://gitee.com/api/v5/swagger_doc.json)（5.4.93）、實際 API 回應。
- 未登入 `X-RateLimit-Limit: 60`（時間窗未驗證）。
- 2022-05-18 起「新上線的開源倉庫需經人工審核後才能正式公開」：二手來源（[The Register](https://www.theregister.com/2022/05/20/gitee_code_review/)、[SCMP](https://amp.scmp.com/tech/big-tech/article/3178323/gitee-chinas-answer-github-review-all-code-temporarily-closing-open)），官方原文未驗證。
- [使用條款](https://gitee.com/terms)由 JS 載入，curl 讀不到內文，**未驗證**。
- 對全球使用者的 demo 價值低，又要申請 token，黑客松不碰。

### 2.9 SourceHut（避開）

- API 是 GraphQL，一律要 OAuth personal access token。來源：[GraphQL on SourceHut](https://man.sr.ht/graphql.md)。
- 條款「You may only collect this data for one or more of the following purposes: Search engine indexing / Open-access research / Data archival. You may not use automated tools to collect SourceHut data for solicitation, profit, or the training of a machine learning model.」來源：[SourceHut Terms](https://man.sr.ht/terms.md)。
- 同一份條款禁止「original content written with or which facilitates the use of LLMs (large language models) or other generative AI technologies」，所以本地 AI 類別不會在這裡。

---

## 3. 兩個 demo 類別的 query

`{d}` 是起始日（7 天或 14 天前），`{y}` 是今年 1 月 1 日。腳本 `python3 spikes/ch_hosting_github.py queries` 會印出代入日期後的版本。

### 3.1 GitHub（search/repositories）

| 類別 | 用途 | q |
|---|---|---|
| CLI | 新建（召回） | `topic:cli created:>={d} fork:false` |
| CLI | 新建（召回） | `topic:command-line created:>={d} fork:false` |
| CLI | 新建（召回） | `topic:terminal created:>={d} fork:false` |
| CLI | 新建（召回） | `topic:tui created:>={d} fork:false` |
| CLI | 沒打 topic 的 | `cli in:name,description created:>={d} fork:false` |
| CLI | 沒打 topic 的 | `"command-line tool" in:description created:>={d} fork:false` |
| CLI | **寶藏候選（主力）** | `topic:cli created:>={y} pushed:>={d} stars:5..300 fork:false archived:false` |
| 本地 AI | 新建（召回） | `topic:local-llm created:>={d} fork:false` |
| 本地 AI | 新建（召回） | `topic:ollama created:>={d} fork:false` |
| 本地 AI | 新建（召回） | `topic:llama-cpp created:>={d} fork:false` |
| 本地 AI | 新建（召回） | `topic:gguf created:>={d} fork:false` |
| 本地 AI | 新建（召回） | `topic:local-ai created:>={d} fork:false` |
| 本地 AI | 新建（召回） | `topic:mlx created:>={d} fork:false` |
| 本地 AI | 沒打 topic 的 | `"local llm" in:name,description created:>={d} fork:false` |
| 本地 AI | 沒打 topic 的 | `ollama in:name,description created:>={d} fork:false` |
| 本地 AI | **寶藏候選（主力）** | `topic:local-llm created:>={y} pushed:>={d} stars:5..300 fork:false archived:false` |

設計說明：
- 「召回」那幾條每天跑一次，加 `stars:>=1` 或 `stars:>=5` 當品質下限；`stars:5..300` 同時是知名度上限。
- 「寶藏候選」把範圍放寬到今年建立、最近 7 天有 push：剛建 7 天的 repo 多半還沒有 release，用驗證 agent 也裝不起來。
- 排除規則（雜訊來自 Codeberg 實測，GitHub 應該更多）：描述含 `bulk-create accounts`、`harvest cookies`、`captcha bypass` 這類的直接丟掉；同一作者一週建很多 repo 的降權。
- 其他候選 topic（存在與否未驗證）：`llm-inference`、`on-device-ai`、`offline-first`、`local-first`、`whisper-cpp`。

### 3.2 其他平台（實測過）

| 平台 | 類別 | 請求 |
|---|---|---|
| HF Spaces | 本地 AI（瀏覽器端） | `/api/spaces?sort=trendingScore&direction=-1&limit=1000&expand[]=createdAt&expand[]=cardData&expand[]=likes&expand[]=sdk`，在用戶端留 `createdAt` 14 天內、描述含 local／offline／webgpu／in-browser／gguf／ollama 的 |
| HF Spaces | 本地 AI（瀏覽器端） | `/api/spaces?filter=webgpu&sort=createdAt&direction=-1&limit=1000`；`filter=transformers.js` 同理 |
| Codeberg | CLI | `/api/v1/repos/search?q=cli&topic=true&mode=source&sort=created&order=desc&limit=50`；`q=tui`、`q=terminal` 同理 |
| Codeberg | 本地 AI | 同上，`q=llm`、`q=ollama`、`q=local-llm` |
| GitLab | CLI／本地 AI | `/api/v4/projects?topic=cli&visibility=public&order_by=created_at&sort=desc&per_page=100&simple=true`（只做計數；正式只接提交連結） |

---

## 4. 實測

兩個腳本都在 `spikes/`，只用 Python 標準函式庫，不含金鑰。執行時間 2026-10-27 約 20:00–20:10 UTC（台北 10-28 凌晨）。

### 4.1 `spikes/ch_hosting_github.py`

```bash
# 需要 GitHub personal access token。fine-grained token 就夠：
# GitHub → Settings → Developer settings → Personal access tokens → Fine-grained，
# 不用勾任何權限（官方：「Tokens always include read-only access to all public repositories on GitHub」）
export GH_TOKEN=...
python3 spikes/ch_hosting_github.py counts          # 約 60 次 search，2–3 分鐘
python3 spikes/ch_hosting_github.py sample          # 7 天聯集，抽 5 筆低星作品＋查 latest release
python3 spikes/ch_hosting_github.py slice 2026-10-26   # 示範日期分片
python3 spikes/ch_hosting_github.py gharchive 2026-10-26-15 2025-06-16-15   # 不需要 token
```

**結果 A：GitHub search 本 session 跑不了。**`counts` 第一個請求就回：

```
HTTP 403 ... "This GitHub API path is not available: sessions are bound to their configured repositories. Use repository-scoped endpoints (repos/{owner}/{repo}/...)."
```

GraphQL 回「GitHub GraphQL is not available from Claude Code sessions」。這是本 session 代理的限制，不是 GitHub 的限制。程式流程已用本機 mock server 跑過 `counts`、`sample`、`slice` 三個子命令，輸出格式正常。**7／14 天筆數與抽樣品質要請念誠在自己電腦上跑 `counts` 與 `sample`**，結果貼回這一節。

**結果 B：GH Archive（`gharchive` 子命令，實際下載）**

| 小時檔（UTC） | 事件數 | 新 repo 事件（CreateEvent, ref_type=repository） | PushEvent | ReleaseEvent | WatchEvent |
|---|---|---|---|---|---|
| 2024-10-21-15（手動跑） | 273,583 | 10,466 | — | — | — |
| 2025-06-16-15 | 163,657 | 6,629 | 93,525 | 874 | 5,477 |
| 2025-10-20-15（手動跑） | 149,127 | 0 | 96,756 | 446 | 2,534 |
| 2026-01-15-15 | 146,635 | 0 | 97,889 | 709 | 3,838 |
| 2026-10-20-15 | 55,085 | 0 | 42,730 | 126 | 226 |
| 2026-10-26-15 | 2,780 | 0 | 0 | 125 | 194 |
| 2026-10-27-10 | 2,741 | 0 | 0 | 120 | 192 |

結論：從 2025 下半年開始，公開事件流就看不到新 repo；2026-10 連 push 都沒了。不能拿來發現新作品。

### 4.2 `spikes/ch_hosting_hf_forges.py`

```bash
python3 spikes/ch_hosting_hf_forges.py              # hf、codeberg、gitlab 全跑，約 2 分鐘
python3 spikes/ch_hosting_hf_forges.py hf           # 可選：export HF_TOKEN=...（huggingface.co/settings/tokens 建 read token），rate limit 由 500 升到 1,000 次／5 分
```

**Hugging Face Spaces**（每個查詢取最新 1,000 筆，數最近 7／14 天）

| 查詢 | 7 天 | 14 天 |
|---|---|---|
| `filter=webgpu` | 6 | 10 |
| `filter=transformers.js` | 5 | 13 |
| `filter=mcp-server`（不屬於 demo 類別，只計數） | 336 | 624 |
| `search=ollama` | 3 | 11 |
| `search=gguf` | 6 | 35 |
| `search=local` | 3 | 36 |
| `search=offline` | 0 | 0 |
| `search=cli`（會比對到 client） | 47 | 97 |

- 全站：最新 1,000 個 Space 橫跨 18.3 小時（約 1,315 個／天）；最新 1,000 個 model 橫跨 4.3 小時（約 5,637 個／天）。
- 本地 AI 相關（webgpu、transformers.js、ollama、gguf、local、offline 去重）7 天 **20 筆**：README 連到 GitHub repo 的 **6**、RUNNING 16、likes≥1 只有 **2**。
- 抽樣（likes 高者優先）：`samliumay/local-llm-pentesting-lab`（2 likes，有 GitHub repo，LLM 滲透測試練習場）、`bardsai/eu-pii-anonymization-demo`（瀏覽器端 PII 去識別化）、`Caspivs/embeddinggemma-2-demo`（瀏覽器端語意搜尋）、`Gelyx59430/llama31-heretic-gguf-demo`（GGUF 聊天 demo）、一個 BUILD_ERROR 的 GGUF Space。**可安裝、可推薦的工具：0 筆。**
- 換成 trending 前 1,000 名：14 天內建立的有 124 個（7 天內 64 個），描述像本地／瀏覽器端 AI 的 10 個，例如 `gradium/phonon`（瀏覽器內 TTS，51 likes）、`webml-community/ternary-bonsai-2-hermes-webgpu`（21 likes）、`yayaiu6/Verto-Arabic-ASR`。品質明顯較好，但仍是「免安裝的網頁工具」，不是 CLI 或本地執行器；關鍵字比對也會誤中（例如 LoRA 圖片生成 Space）。

**Codeberg**（topic 搜尋，`mode=source`，取第 1 頁 50 筆）

| topic | 7 天 | 14 天 | 該 topic 總 repo 數 |
|---|---|---|---|
| cli | 15 | 26 | 1,623 |
| terminal | 2 | 4 | 408 |
| tui | 3 | 7 | 341 |
| llm | 9 | 15 | 239 |
| ollama | 1 | 1 | 59 |
| local-llm | 1 | 1 | 19 |

- 7 天去重 25 筆：stars≥1 只有 5、全部有描述、有 release 3。
- 同一作者 7 天建 ≥3 個：`0xgetz` 9 個（全是帳號農場）、`sidmulajkar` 3 個（同一專案的複本也被別人 mirror）。
- 抽樣（每位作者 1 筆）：`0xgetz/sparkian-bulk-9router`（帳號農場，**應排除**）、`CyberSys/rea`（別人專案的複本）、`SpoTUI/SpoTUI`（Spotify 主題）、`adrianpk/rev`（Rust 編輯器）、`axegon/lxsh`（Shell over Meshtastic）。5 筆裡可推薦的約 1–2 筆。
- 全站：最新 3,000 個 repo 橫跨約 46 小時（約 1,500 個／天）。

**GitLab.com**（未登入，`topic=…`，取第 1 頁 100 筆）

| topic | 7 天 | 14 天 | 7 天內 stars≥1 |
|---|---|---|---|
| cli | 11 | 17 | 0 |
| command-line | 0 | 0 | 0 |
| llm | 9 | 40 | 1 |
| ollama | 0 | 1 | 0 |

- 全站：最新 100 個 public project 橫跨 11–15 分鐘（三次量測，約 9,500–13,500 個／天）。
- 第一次跑時 `command-line`、`llm` 兩個請求 429；腳本改成依 `Retry-After` 等一次再試後才拿到。

---

## 5. 結論

### 5.1 黑客松期間值得接的

| 管道 | 理由 | 預估工時 |
|---|---|---|
| **GitHub search API**（第 3.1 節的 16 條 q） | 唯一能大量、合規、即時拿到「今年新建、最近有動、星少」作品的來源；一次回傳就有 topics、license、stars、pushed，篩選便宜；兩個類別都有成熟的 topic | 4–6（query 集、日期分片、2.1 秒節流、去重、轉成候選檔） |
| **GitHub repo／releases／README** | 補「有沒有 binary release、最近 release、README」，同時是品質分數與驗證 agent 的安裝線索 | 2–3 |

注意：
- 發現 agent 要在**本機或 Modal 這類有正常網路的地方**跑，這個雲端 session 打不到 GitHub search。
- 每次執行控制在 ≤20 次 search（約 40 秒），每天 1–2 次就夠 demo。
- 只存抽出的事實＋連結，不轉貼 README 全文；不存個資。

### 5.2 之後擴充的

| 管道 | 條件 |
|---|---|
| HF Spaces（trending ∩ 14 天內） | 本地 AI 類別若要涵蓋「瀏覽器端、免安裝」的小工具；驗證要改成 headless 瀏覽器。有空可在黑客松加一條 query（約 2 人時），README 有 GitHub 連結的再丟回 GitHub 流程 |
| Codeberg | 先只接使用者貼的連結（查單一 repo）；要定期輪詢先寫信問 Codeberg，並用清楚的 User-Agent |
| GitLab.com | 只接使用者貼的連結；不要定期掃 `/projects`（API Terms 1.3.9） |

### 5.3 要避開的

| 管道 | 原因 |
|---|---|
| GitHub events API／GH Archive／BigQuery | 公開事件流已看不到新 repo（實測 2025-10 起 0 筆；OSS Insight 稱事件擷取剩 0.3%） |
| GitHub trending 頁面 | 沒有官方 API；爬 HTML 不在 AUP 允許的用途；上面多半已經有名 |
| HF models 當發現來源 | 是模型不是軟體，每天 5,600 個，雜訊極高 |
| Gitee | 未登入搜尋回 0、不能依建立時間排序、公開 repo 需審核（二手來源）、條款讀不到 |
| SourceHut | 條款只允許索引／研究／封存用途的自動收集，禁止營利；並禁止 LLM 相關內容 |

---

## 6. 來源

查證日期一律 2026-10-28（台北）。

**GitHub**
- REST search：<https://docs.github.com/en/rest/search/search>
- Searching for repositories（qualifier）：<https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories>
- REST rate limits：<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>
- GraphQL rate limits：<https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api>
- GraphQL search（1,000 筆上限）：<https://docs.github.com/en/graphql/reference/search>
- Events API：<https://docs.github.com/en/rest/activity/events>
- Event types：<https://docs.github.com/en/rest/using-the-rest-api/github-event-types>
- Releases API：<https://docs.github.com/en/rest/releases/releases>
- 官方 REST OpenAPI 描述檔（v1.1.4，824 路徑）：<https://github.com/github/rest-api-description>（檔案 `descriptions/api.github.com/api.github.com.json`）
- Terms of Service（生效日 2026-04-27）：<https://docs.github.com/en/site-policy/github-terms/github-terms-of-service>
- Acceptable Use Policies：<https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies>
- Fine-grained PAT：<https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens>
- Events API payload 變更（2025-10-07 生效）：<https://github.blog/changelog/2025-08-08-upcoming-changes-to-github-events-api-payloads/>
- Octoverse 2025（230+ 新 repo／分鐘、121M 新 repo）：<https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/>
- GH Archive：<https://www.gharchive.org/>；每小時檔 `https://data.gharchive.org/YYYY-MM-DD-H.json.gz`（實際下載）
- OSS Insight trends API 回應：<https://api.ossinsight.io/v1/trends/repos/?period=past_week&language=All>（實際呼叫）

**Hugging Face**
- Hub API：<https://huggingface.co/docs/hub/api>；OpenAPI：<https://huggingface.co/.well-known/openapi.md>
- huggingface_hub `list_spaces`／`list_models`：<https://huggingface.co/docs/huggingface_hub/package_reference/hf_api>
- Rate limits：<https://huggingface.co/docs/hub/rate-limits>
- Local Apps：<https://huggingface.co/docs/hub/local-apps>
- Webhooks：<https://huggingface.co/docs/hub/webhooks>
- Terms of Service：<https://huggingface.co/terms-of-service>
- Content Policy：<https://huggingface.co/content-policy>
- robots.txt：<https://huggingface.co/robots.txt>
- 實際 API：`https://huggingface.co/api/spaces?...`、`https://huggingface.co/api/models?...`、`https://huggingface.co/api/trending`

**GitLab**
- Projects API：<https://docs.gitlab.com/api/projects/>（原始檔 <https://gitlab.com/gitlab-org/gitlab/-/raw/master/doc/api/projects.md>）
- GitLab.com rate limits：<https://docs.gitlab.com/user/gitlab_com/rate_limits/>
- API Terms of Use：<https://handbook.gitlab.com/handbook/legal/api-terms/>（原始檔 <https://gitlab.com/gitlab-com/content-sites/handbook/-/raw/main/content/handbook/legal/api-terms.md>）
- 法律文件總表：<https://about.gitlab.com/terms/>

**Codeberg**
- Terms of Use：<https://codeberg.org/Codeberg/org/src/branch/main/TermsOfUse.md>
- API swagger：<https://codeberg.org/swagger.v1.json>
- robots.txt：<https://codeberg.org/robots.txt>

**Gitee**
- OpenAPI swagger：<https://gitee.com/api/v5/swagger_doc.json>
- 使用條款（內文未能讀取）：<https://gitee.com/terms>
- 2022 審核制度（二手）：<https://www.theregister.com/2022/05/20/gitee_code_review/>、<https://amp.scmp.com/tech/big-tech/article/3178323/gitee-chinas-answer-github-review-all-code-temporarily-closing-open>

**SourceHut**
- Terms：<https://man.sr.ht/terms.md>
- GraphQL：<https://man.sr.ht/graphql.md>
