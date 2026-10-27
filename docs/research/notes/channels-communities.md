2026-10-28 · 西方開發者社群與社交平台（HN、Lobsters、Reddit、X、Product Hunt、dev.to、Indie Hackers、LinkedIn、Discord、Bluesky、Mastodon） · 由調研 agent 撰寫，待主控者整合

# 管道調研：西方開發者社群與社交平台

需求來源：[brief.md](../../brief.md) 第 4、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期一律是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。

問的問題只有一個：**哪些管道能合法、便宜地拿到「作者自己發表作品、最近才出現、還沒什麼人知道」的貼文**，而且對兩個 demo 類別（開發者 CLI 工具、本地 AI／LLM 工具）有用。

標記方式：
- **已驗證**：我親自讀了官方文件原文，或親自打了 API 看到回應。
- **未驗證**：只有第三方資料、或官方頁在這個環境打不開。

---

## 1. 比較表

數字來自第 3 節的實測（2026-10-27 UTC），「CLI」「本地 AI」是關鍵字粗估，不是模型判斷。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制（ToS／授權／費用／rate limit／審核） | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| **Hacker News（Show HN）** | **高**：Show HN 規則要求「你親自做的、別人能試用的東西」 | **多**：7 天 992 筆（約 142／天）；35% 連 GitHub；兩類別且連 GitHub 約 75 筆／週 | 中：有 landing page、SaaS、AI 一次性作品 | API：官方 Firebase（無金鑰）＋ Algolia 搜尋（無金鑰） | 免費、無審核。Firebase「目前沒有 rate limit」；Algolia 每 IP 10,000 次／小時。YC 使用條款禁止爬網站與商用重製 → 只走 API、只存連結與 metadata | 2–4 人時 | **黑客松接** |
| Lobsters（`show` tag） | 高：邀請制；`user_is_author` 欄位 23/25 為真 | **很少**：最新 25 筆（25 是單頁上限）橫跨近 60 天（約 3／週）；最近 7 天 0 筆 | 低 | JSON（`/t/show.json`）、RSS | robots.txt 對 `User-agent: *` 寫 `Disallow: /`；另有 `Content-Signal: ai-input=no, ai-train=no`；沒有 API 條款 | 1 人時 | **避開**自動抓取（作者自己提交連結可收） |
| Reddit | 中（未實測） | 多（未實測） | 高（未實測） | Data API（OAuth） | 商用要另簽約；不得未經權利人同意拿去訓練模型；只能保留核准用途需要的資料；Responsible Builder Policy：經 API 存取任何 Reddit 資料都要先申請、取得明確核准（已驗證）；免費層每個 OAuth client 100 QPM（已驗證） | 4–8 人時＋等審核 | **避開** |
| X | 中：#buildinpublic 多，但行銷文多（未實測） | 多（未實測） | 高 | API v2，pay-per-use | 讀一則貼文 $0.005（24 小時內去重）；每月上限 300 萬則；官方定價頁沒有免費讀取層；Recent search 只回 7 天；要綁卡買 credits；刪文要 24 小時內同步刪 | 3–4 人時＋費用 | **之後擴充** |
| Product Hunt | 中：maker 自己 launch，但以商業 SaaS 為主、行銷味重 | 多（未實測） | 中 | GraphQL API v2（需 token） | 「The Product Hunt API must not be used for commercial purposes」；需 access token（不帶 token 打 GraphQL 實測 401）；fair-use 限流 | 2–3 人時 | **避開** |
| dev.to（`#showdev`） | 中：多是作者自介，但 reactions 中位數 0、推廣文多 | **多**：7 天約 887 篇（約 127／天；原寫 713 是腳本翻頁 bug 造成的低估，見查核紀錄）；抽 40 篇內文 57% 有 GitHub repo；CLI 25、本地 AI 33 | 中高 | Forem API v1（文章列表免金鑰）、RSS | 沒有獨立 API 條款；網站 Terms 的 Use License 寫「personal, non-commercial transitory viewing only」；文件沒寫 rate limit | 2–3 人時 | **之後擴充**（黑客松有空才接） |
| Indie Hackers | 中：創業者自述，多為 SaaS（未實測） | 中（未實測） | 高 | 無公開 API | robots.txt 擋 `/api/`，並對 `meta-externalagent` 等 AI bot `Disallow: /`；本環境打首頁、RSS、terms 都回 403 | — | **避開** |
| LinkedIn | 低（對兩個類別） | — | 高 | API 需核准 | 免審核的權限只有 `profile`、`email`、`w_member_social`（寫）；沒有讀別人貼文的開放權限；Community Management API 只給管理 Page，member data 最多存 48 小時、不得匯出或與其他資料結合 | — | **避開** |
| Discord | 中高：專案伺服器的 #showcase（只限 bot 被邀請的伺服器） | 少（要一個個伺服器邀請） | 中 | Bot＋Gateway | 讀訊息內容要 `MESSAGE_CONTENT` 特權 intent；100+ 伺服器要驗證並核准；Developer Policy 禁止 mine／scrape、禁止拿 API 取得的訊息內容訓練 AI、禁止將 API Data 商業化（已驗證，經 Help Center API 讀到原文） | 4–6 人時 | **避開**（之後可做「作者邀 bot 進自己伺服器」） |
| Bluesky | 中：有作者自發，也有大量 bot 轉貼 | 中：7 天內「"I built"／"I made"／"just released"／"I wrote" + github.com」各 39／45／21／19 則 | 高 | Jetstream live tail（免認證、不計量）；AppView API；searchPosts | 未登入搜尋只拿得到第一頁（帶 cursor → 403）；官方建議的 `public.api.bsky.app` 搜尋 → 403；Jetstream 歷史 replay 要 API key、按位元組計量；Developer Guidelines 要求能刪除使用者要求刪除的內容 | 3–4 人時（@mention 提交）；4–6 人時（搜尋） | **黑客松可選**（Threads 提交入口的備案）；之後擴充 |
| Mastodon／fediverse | 低～中 | 少：3 個大站 6 個 tag 7 天去重 1,098 則，含 GitHub repo 66 則，像作者自介只有 4 則 | 高：mastodon.social 的 #showdev 40 則有 36 則是 hackaday 轉貼 bot | hashtag timeline API（實測 4 站中 3 站免登入） | 各站自訂；66 則中 32 則的帳號 `indexable=false`（沒同意被搜尋）；infosec.exchange 要登入（422）；fediverse 普遍反感未經同意的抓取 | 3 人時 | **之後擴充**（只做 @mention 提交） |

---

## 2. 各管道細節

### 2.1 Hacker News：Show HN

- **作者自己發表**：[Show HN 規則](https://news.ycombinator.com/showhn.html)原文：「Show HN is for something you've made that other people can play with.」「The project must be something you've worked on personally and which you're around to discuss.」現行版本另有「Don't post quickly-generated one-offs; anybody can do that now.」→ 這是所有管道中**最接近「作者本人發表、可試用的作品」的定義**。已驗證。
- **最近才出現、沒人知道**：7 天 992 筆中，**86% 只有 ≤3 points，points 中位數 1**，≥50 points 只有 2%。大部分 Show HN 沒上過 /show 頁。正好是要找的長尾。已驗證（實測）。
- **哪個端點要用**：
  - 官方 Firebase `/v0/showstories`：README 寫「Up to 200 of the latest … Show HN … stories」。[FAQ](https://news.ycombinator.com/newsfaq.html)：「there is a small points threshold before a post makes it to ask or show」；[Show HN 規則](https://news.ycombinator.com/showhn.html)：「Every Show HN appears on shownew. Once it clears a small points threshold, it will appear on the show page」。實測同期只涵蓋 Algolia 的 **14%（142/992）**。**查核修正（2026-10-27 20:3x UTC 實測）**：它不是「過門檻就收」的完整清單，而是排名後的子集合。回傳 142 筆、橫跨 5.3 天，全部 ≥2 points（1 point 的一筆都沒有）；但同一段時間 ≥2 points 的 Show HN 只有 37%（142/381）在裡面，≥5 points 的也只有 53/77。142 筆中有 73 筆是 2–3 points，所以不是「把 ≤3 points 的全濾掉」；≤3 points 的貼文約 89%（607/680）不在裡面。結論不變：不要只用它。
  - 官方 Firebase `/v0/newstories` 回最新 500 筆 story（實測約涵蓋 6.6 小時）。標題以「Show HN」開頭的 97 筆和 Algolia 同期結果 **100% 重疊**。每 1–3 小時輪詢一次，就能只靠官方 API 拿到全部 Show HN。
  - Algolia `search_by_date?tags=show_hn&numericFilters=created_at_i>T`：一次查詢就能回補任意時段，含 `points`、`num_comments`、`story_text`。HN 首頁的搜尋框就指向 hn.algolia.com。每次查詢最多 1,000 筆，要按天切片。
- **兩個類別**：關鍵字粗估，7 天 CLI 79 筆（連 GitHub 48）、本地 AI 82 筆（連 GitHub 38），兩類聯集且連 GitHub 75 筆。人工看過清單：CLI 的精準度約七成；「本地 AI」誤判較多（例如記帳 App）。分類要交給 Muse Spark。**兩個類別都夠用**，本地 AI 這週還有好幾個語音聽寫工具（UnCode、VoxScribe、Murmur），可以呼應 brief 第 1 節的例子。
- **條款**：HN 頁尾的「Legal」連到 [YC Terms of Use](https://www.ycombinator.com/legal/)。相關原文有四句（查核修正：原稿說「兩段都以 Except as expressly authorized 開頭」不正確）：
  1. 「Except as expressly authorized by Y Combinator, you agree not to modify, copy, frame, scrape, … or create derivative works based on the Site or the Site Content」——有例外字樣。
  2. 緊接的下一句**沒有例外字樣**：「In connection with your use of the Site you will not engage in or use any data mining, robots, scraping or similar data gathering or extraction methods.」
  3. Commercial Use：「Unless otherwise expressly authorized herein or in the Site, you agree not to display, distribute, … reproduce, duplicate, copy, create derivative works from, … for any commercial purposes, any portion of the Site」——有例外字樣，而且例外可以來自「in the Site」。
  4. 禁止「obtain or attempt to access or otherwise obtain any materials or information through any means not intentionally made available or provided for through the Site」。

  HN 頁尾的「API」連到 [HackerNews/API](https://github.com/HackerNews/API)：「we're making the public Hacker News data available in near real time」「There is currently no rate limit」。HN 頁面的搜尋表單 `action` 指向 `//hn.algolia.com/`。**解讀**（非法律意見）：官方 API 與 Algolia 搜尋都是 HN 網站本身連出去的管道，屬於第 4 句的「intentionally made available … through the Site」；但第 2 句的 data mining／robots 禁令沒有例外字樣，所以**絕對不要爬 HN 的 HTML**，只走這兩個 API。只存標題、連結、時間、points 等 metadata，軟體的事實從 GitHub repo 取，不轉載貼文全文，也不做商業展示。已驗證原文。
- **Algolia 限制**：[hn.algolia.com/api](https://hn.algolia.com/api)（頁面以 JS 渲染，原文在其 main.js）：「We are limiting the number of API requests from a single IP to 10,000 per hour.」已驗證。每個查詢只拿得到前 1,000 筆（實測 `hitsPerPage=1000&page=1` 回 0 筆；`hitsPerPage=50&page=25` 也回 0 筆），所以要按天切片。Algolia 不是 YC 營運的服務；頁面上沒找到另外的使用條款連結（「不存在」未驗證）。

### 2.2 Lobsters

- `/t/show.json` 有 `user_is_author` 欄位，25 筆中 23 筆為真；9 筆連 GitHub、3 筆連 Codeberg。訊號很乾淨。
- 但量太少：25 筆橫跨 2026-08-15 到 10-14，約每週 3 筆；最近 7 天 0 筆。對 demo 幫助不大。（查核補充：25 是 Lobsters 單頁上限，原始碼 `StoriesPaginator::STORIES_PER_PAGE = 25`，見 [stories_paginator.rb](https://github.com/lobsters/lobsters/blob/master/app/models/stories_paginator.rb)；所以「最新 25 筆橫跨 60 天」的推論成立。查核者為遵守 robots.txt 沒有重抓 `/t/show.json`，筆數未獨立重測。）
- [robots.txt](https://lobste.rs/robots.txt) 只放行 GoogleBot、BingBot 等特定搜尋引擎，對其他所有 UA 寫 `Crawl-delay: 1`、`Disallow: /`（另外單獨點名封鎖 Brave）。另有 `Content-Signal: ai-input=no, ai-train=no`（寫在搜尋引擎那一組）。[About](https://lobste.rs/about) 頁說「Per-tag, multi-tag and site-wide RSS feeds are available to the public」，但沒有 API 條款。
- **結論**：站方明確不歡迎一般 bot，而且不希望內容當 AI 輸入。自動抓取避開。作者自己貼 Lobsters 連結到提交入口時，**pickfit 也不要去抓那個 Lobsters 頁面**（robots.txt 對一般 UA 全擋、`ai-input=no`），改請提交者直接貼 GitHub 連結。（查核修正：原稿「只當線索、改讀 GitHub」隱含要先讀 Lobsters 頁面才拿得到 GitHub 連結。）

### 2.3 Reddit

- brief 第 8 節寫「條款禁止爬取、建立競爭資料庫或商用」。**結論對，理由要改**：[Data API Terms](https://redditinc.com/policies/data-api-terms)（Effective June 19, 2023）和 [Developer Terms](https://redditinc.com/policies/developer-terms)（Effective September 24, 2024）裡**沒有「競爭資料庫」的字樣**。真正卡住的是下面幾條（已驗證原文）：
  - 商用要另簽約：「If you are interested in using the Data APIs for commercial purposes, research in excess of rate limits, or for any use that is not expressly permitted under the Data API Terms, then you will need to enter into a separate agreement with Reddit.」
  - 不能營利：「sell, lease, or sublicense the Data APIs … or derive revenues from the use or provision of the Data APIs … unless there is express written approval from Reddit」；Developer Terms 4.1 更廣：不得「access or use any of the Reddit Services and Data by or on behalf of a business or as part of a service or product that is monetized」。
  - 不能拿去訓練模型：「including using User Content to train a machine learning or AI model without the express permission of rightsholders」；Developer Terms：不得透過 API「indexing, caching, or crawling」來「train large language, artificial intelligence, or other algorithmic models … without our permission」。
  - 資料保留：「use or retain any User Content … beyond your approved use case, and you must immediately delete any data not required for it」；終止時要刪除「any data or models that were derived from User Content」。
  - 可隨時要求 App Review：「Reddit may require you to submit your App for Reddit's review and approval … at any time at Reddit's sole discretion」。
- **申請流程**（查核更新，已驗證）：官方 HTML 頁仍回 403，但同一篇文章可以從 Reddit 官方 Help Center 的公開 API 讀到：[articles/42728983564564.json](https://support.reddithelp.com/api/v2/help_center/en-us/articles/42728983564564.json)。原文：「Approval is required: You must request access and get explicit approval before accessing any Reddit data through our API」；非商用開發者「should use the Developer Platform ("Devvit")」；商用要「explicit written approval」；「No Unapproved Commercialization or AI Training … This extends to commercial and non-commercial mining, scraping」。文章建立時間 2025-10-28T17:49Z、最後編輯 2026-10-05（Zendesk metadata）。社群轉述的公告日 2025-11-11 未驗證；「有人被秒拒、有人等數月」仍是社群說法，未驗證。
- **免費額度**（查核更新，已驗證）：[Data API Wiki](https://support.reddithelp.com/api/v2/help_center/en-us/articles/16160319875092.json)：「100 queries per minute (QPM) per OAuth client id」，以 10 分鐘平均；「Clients must authenticate with a registered OAuth token」；另外「we strongly recommend routinely deleting any stored user data and content within 48 hours」。
- **兩個類別**：r/commandline、r/LocalLLaMA、r/SideProject 的作者自發貼文應該很多（未實測）。可惜管道本身走不通：要審核、商用受限、資料要配合刪除。

### 2.4 X

- [官方定價頁](https://docs.x.com/x-api/getting-started/pricing)：「The X API uses pay-per-usage pricing. No subscriptions」。Posts: Read **$0.005 per resource**；「Pay-per-usage plans are capped at 3 million Post reads per monthly billing cycle」；同一資源 24 小時（UTC 日）內重複讀取不另計費。**頁面上沒有免費的讀取層**。已驗證。[免費額度頁](https://docs.x.com/x-api/getting-started/free-credits)：首張合格卡＋**完成第一次購買** credits 後送一次 $20（2026-10-13 起只加卡不算），首次自動儲值再送最多 $50；免費額度 3 個月後過期。已驗證。
- [Search 文件](https://docs.x.com/x-api/posts/search/introduction)：Recent Search「Search Posts from the last 7 days. Available to all developers」；需「An approved developer account」。已驗證。
- [Developer Policy](https://docs.x.com/developer-terms/policy)：離線儲存要同步刪改，「within 24 hours after receiving a request」；不得用 API 計算「aggregate X Post metrics」。已驗證。
- 費用估算：每天搜 1,000 則 ≈ $5／天、$150／月；黑客松一週 $20 免費額度只夠約 4,000 則，而且要先自己付一筆儲值才拿得到。量可以用，但要綁卡、要盯用量。
- **結論**：之後擴充。黑客松期間，作者貼 X 連結到提交入口時只取連結，不打 API。

### 2.5 Product Hunt

- [API v2 文件](https://api.producthunt.com/v2/docs)原文：「The Product Hunt API must not be used for commercial purposes. If you would like to use it for your business, please contact us at hello@producthunt.com.」「Currently the API is only accessible with a provided access_token.」「We reserve the right to rate-limit any application if we feel you are not following fair-use.」已驗證。實測不帶 token POST `https://api.producthunt.com/v2/api/graphql` 回 401。
- 內容以商業 SaaS 為主，和「默默無聞」相反。**brief 的「不要用」正確**。

### 2.6 dev.to（Forem API）

- `GET https://dev.to/api/articles?tag=showdev&per_page=1000` 不帶金鑰回 200。[Forem API 文件](https://developers.forem.com/api/v1)：「All endpoints can be accessed with the 'api-key' header … but some of them are accessible publicly without authentication」；`per_page` 上限 1000；文件沒有寫 rate limit。已驗證。
- 量（查核修正，2026-10-27 20:34 UTC 重跑）：7 天約 **887 篇（約 127／天）**。原稿 713 篇是低估：`/api/articles?tag=showdev` 的列表**不是嚴格按時間排序**（第 1 頁 1,000 筆有 462 處倒序，第 2、3 頁仍各有 86 篇落在 7 天內），舊版腳本看到第 1 頁最後一筆超過 7 天就停。腳本已修正。645 篇（73%）0 個 reaction。抽 40 篇讀內文，23 篇（57%）有 GitHub repo 連結。關鍵字判為 CLI 25 篇、本地 AI 33 篇。看到的例子：把 macOS OCR 包成 CLI 的 d2md、zsh 的 Term-Undo。原稿「本地 AI 類偏少」和自己的關鍵字數字不符（兩類量相近）；關鍵字精準度沒有人工檢查，**兩類的實際可用量未驗證**。
- 條款：[DEV Terms](https://dev.to/terms) 第 2 節 Use License：「Permission is granted to temporarily download one copy of the materials … for personal, non-commercial transitory viewing only」，不得「use the materials for any commercial purpose, or for any public display」。沒有獨立的 API 條款。已驗證原文。**解讀**：官方公開了 API，但網站條款對內容重用很保守 → 只拿「文章連結＋GitHub 連結」當線索，不存、不展示文章內文。注意：要拿到 GitHub 連結就得透過 API 讀內文（列表不含內文），而 Terms 沒有寫 API 的例外；正式接之前應先向 DEV 書面確認（未聯絡）。
- **結論**：之後擴充。黑客松期間 HN 已足夠，dev.to 有空才接。

### 2.7 Indie Hackers

- 沒有公開 API。[robots.txt](https://www.indiehackers.com/robots.txt) 對所有 UA 擋 `/api/`，並對 `meta-externalagent`、`GPTBot`、`ClaudeBot` 等 AI bot 寫 `Disallow: /`。本環境打首頁、`/feed.xml`、`/rss`、`/terms` 都回 403。已驗證。
- 內容以 SaaS 營收故事為主，跟兩個類別關係小。**避開**。

### 2.8 LinkedIn

- [Getting Access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access) 原文：「Open Permissions are the only permissions that are available to all developers without special approval」，清單只有 `profile`、`email`、`w_member_social`（代使用者發文）。沒有讀別人貼文的開放權限。已驗證。
- [Restricted Uses](https://learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases)：member data「Accessing, using, or storing member data for any use case other than to manage LinkedIn Pages or Profiles via your application is a violation」；「member social activity data can only be stored for 48 hours」；不得「combined with … any third party data」；「No Social Feeds」。已驗證。
- `r_member_social` 是否已對外關閉：第三方轉述官方 FAQ 說「closed permission」。官方 FAQ 頁本環境 404。**未驗證**。
- **避開**。

### 2.9 Discord

- Bot 只能讀被加進去的伺服器：[OAuth2 文件](https://docs.discord.com/developers/topics/oauth2)的 Bot Authorization Flow 是「makes it easy for users to add bots to guilds」，由使用者把 bot 加進伺服器。已驗證。
- 讀訊息內容要特權 intent：[Gateway 文件](https://docs.discord.com/developers/events/gateway)「MESSAGE_CONTENT (1 << 15) is a unique privileged intent」；「For verified apps (required for apps in 100+ guilds), the intent must also be approved」。已驗證。
- [Developer Policy](https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy) 的 HTML 頁本環境 403，但官方 Help Center 的公開 API 讀得到原文：[articles/8563934450327.json](https://support-dev.discord.com/api/v2/help_center/en-us/articles/8563934450327.json)（Effective date: July 8, 2024）。原文（查核更新，已驗證）：第 18 條「Do not sell, license, or otherwise commercialize API Data」；第 20 條「Do not mine or scrape any data, content, or information available on or through Discord services」；第 21 條「Do not use message content obtained through the APIs to train machine learning or AI models (including large language models) unless express permission is granted by Discord」；另有「You may not request, access, or use API Data for any purpose other than as necessary to provide your Application's stated … functionality」。原稿引用的第三方轉述措辭和原文不同，以原文為準。pickfit 是用模型「讀」不是「訓練」，但「發現作品」需要大量讀別人伺服器，和第 20 條方向不合。
- **黑客松避開**。之後可做「作者把 pickfit bot 邀進自己伺服器、在指定頻道貼作品」的提交管道（屬於同意制）。

### 2.10 Bluesky（AT Protocol）

- **Jetstream live tail 免認證**：[Jetstream 文件](https://bsky.network/docs/jetstream)「No authentication is required for the live tail; these instances serve the full network.」v2 端點 `wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents?collections=app.bsky.feed.post&kinds=commit`（子協定 `xrpc.v1.json`）。實測連得上。已驗證。
- **歷史 replay 要 API key**：[Network Replay](https://bsky.network/docs/jetstream-replay)「On Bluesky-hosted instances, the HTTP side of replay requires an API key」「Usage is metered in bytes」「The live WebSocket needs no key and is not metered」。已驗證。
- **searchPosts 認證現況**：[API Hosts and Auth](https://bsky.network/docs/api-directory) 說公開端點「do not require authentication」，「preferably via the https://public.api.bsky.app hostname」。「do not support authentication」這句實際在 [Rate Limits](https://bsky.network/docs/rate-limits) 頁（查核修正來源）。實測（查核者 2026-10-27 20:2x UTC 重測，結果相同）：
  - `public.api.bsky.app` 的 searchPosts → **403**（BunnyCDN 擋）；
  - `api.bsky.app` 的 searchPosts 第一頁 → 200；帶 `cursor` 翻頁 → **403**「Request forbidden by administrative rules」；
  - `bsky.social` 不帶 token → 401 `AuthMissing`。
  → 未登入只能拿每個查詢的前 100 筆。要完整搜尋就用 pickfit 的 Bluesky 帳號＋App Password 登入（免費、不用審核），經 PDS 代理呼叫。已驗證（實測）。官方沒有公告這個限制，第三方（bsky-docs issue #332 等）有回報。
- **條款**：[Developer Guidelines](https://bsky.network/docs/developer-guidelines)：「All services must have a method for deleting content a user has requested to be deleted」；要能回應檢舉、公開維護聯絡 email；禁止自動大量互動。[Bluesky ToS](https://bsky.social/about/support/tos)（Last Updated 14 August 2025）沒有限制第三方讀取公開資料的條款。[Rate Limits](https://bsky.network/docs/rate-limits)：PDS 每 IP 3000 次／5 分；AppView「generous rate-limits」。已驗證。
- **量與雜訊**：Jetstream 每秒約 50–60 則新貼文（約 450–540 萬／天；查核重跑 120 秒為 5,695 則，約 47 則／秒、410 萬／天，GitHub repo 連結 1 則）。連到 GitHub repo 的很少而且不穩：300 秒樣本 15,571 則中只有 5 則（5 個帳號，換算約 1,400 則／天，0 則像作者自介）；120 秒樣本 42 則（一次 bot 爆量）；30 秒樣本 0 則。抽到的唯一一則「作者口吻」其實是 HN 轉貼 bot。**被動聽整條 firehose 找作品不划算**。用搜尋找作者口吻比較準：7 天內「"I built"＋github.com」39 則、「"I made"」45 則（其中 12 則像 CLI）。
- **兩個類別**：CLI 有一些；本地 AI 很少（"open source"＋github 的 97 則中 10 則）。
- **對 pickfit 最有價值的用法**：**@mention 提交**。作者發文時標記 pickfit 的帳號，Jetstream 即時收到，幾秒內進入讀懂→驗證流程。好處：(1) 免認證、免費；(2) 作者主動標記，等於同意；(3) 可以在 demo 裡即時展示「作者發文 → 幾分鐘後可被推薦」。如果 Threads 的關鍵字搜尋或 mention 權限拿不到（見 [channels-meta-platforms.md](channels-meta-platforms.md)），這是 brief 第 5 節第 5 步的備案。要處理 delete 事件（Jetstream 會送）以符合 Developer Guidelines。**查核補充**：Developer Guidelines 把「Generating automated or bulk interactions, including any that would cause a notification to a user like a message, follow, like or reply」列為 spam。如果 pickfit 對每個 mention 自動回覆「已收錄」，就是會觸發通知的自動互動；建議不自動回覆，或只對明確標記 pickfit 的貼文回覆一次，結果放在展示頁（解讀，非官方確認）。

### 2.11 Mastodon／fediverse

- [hashtag timeline](https://docs.joinmastodon.org/methods/timelines/#tag)：「OAuth: Public. Requires app token + read:statuses if the instance has disabled public preview.」4.5.0 起站方可細設存取控制。實測 mastodon.social、fosstodon.org、hachyderm.io 免登入可讀；infosec.exchange 回 422「This method requires an authenticated user」。已驗證。
- 量：3 站 × 6 tag（showdev、opensource、selfhosted、cli、ollama、localllm）7 天去重 1,098 則，含 GitHub repo 66 則，像作者自介只有 4 則。mastodon.social 的 #showdev 最近 40 則中 36 則是 hackaday 轉貼 bot。
- **作者意願**：[Account 實體](https://docs.joinmastodon.org/entities/Account/)有 `indexable`（「Whether the account allows indexing by search engines」，4.3.0 起）、`noindex`、`discoverable`、`bot`。含 GitHub 的 66 則中，**32 則的帳號 `indexable=false`**。fosstodon.org 的 robots.txt 擋 GPTBot；fosstodon 規則「DO NOT post commercial promotions, or advertise」，作者在那裡本來就少自我推銷。mastodon.social 的 [ToS](https://mastodon.social/api/v1/instance/terms_of_service)（2026-08-31 生效）只規範站方對使用者內容的授權，沒有規範第三方讀取。
- **結論**：量少、雜訊多、文化上反感未經同意的收集。之後只做 @mention 提交，並尊重 `indexable=false`、`noindex`、bio 裡的 `#nobot`／`#noindex`。

---

## 3. 實測

兩支腳本都只打無需金鑰的公開 API（HN Firebase、Algolia、Forem、Mastodon、Bluesky）；不含任何金鑰。執行時間 2026-10-27 19:55–20:10 UTC。查核者 20:17–20:34 UTC 重跑，結果見文末「查核紀錄」。

### 3.1 `spikes/ch_comm_hn_showhn.py`（Python 標準函式庫）

```bash
python3 spikes/ch_comm_hn_showhn.py                 # 最近 7 天，抽 5 筆
python3 spikes/ch_comm_hn_showhn.py --days 3 --sample 8 --seed 1
```

做的事：用 Algolia 按天切片抓 Show HN；再抓官方 Firebase `/v0/showstories` 比對涵蓋率；用關鍵字粗分 CLI／本地 AI；抽樣。約 10 秒。

結果（7 天）：

| 項目 | 數字 |
|---|---|
| Show HN 總數 | 992（約 142／天；10/27 單日 173） |
| 有外部連結 | 972（98%） |
| 連到 GitHub repo | 345（35%） |
| 關鍵字判為 CLI | 79（8%），其中連 GitHub 48 |
| 關鍵字判為本地 AI／LLM | 82（8%），其中連 GitHub 38 |
| 兩類聯集且連 GitHub | 75 |
| points 中位數 | 1 |
| ≤3 points | 855（86%） |
| ≥50 points／≥100 points | 20（2%）／11（1%） |
| Firebase `/v0/showstories` 落在 7 天內 | 142，只涵蓋 Algolia 的 14%，且全部包含在 Algolia 結果內（全部 ≥2 points，但不是 ≥2 points 的完整清單，見 2.1） |
| Firebase `/v0/newstories`（500 筆≈6.6 小時）中的 Show HN | 97，與 Algolia 同時段 100% 重疊（另以一次性指令驗證） |

抽樣 5 筆（seed=20261028，CLI 或本地 AI 且連 GitHub）：

| 標題 | 連結 | points／留言 | 初看 |
|---|---|---|---|
| Code Counter Machine – a modern analysis of AI driven development costs | github.com/insanai/ccm | 1／0 | 分類對（CLI），用途偏小眾 |
| Graph-MIND – Local memory for AI coding agents, no LLM calls | github.com/goyohan0611-png/graph-mind | 1／0 | 本地 AI 工具，符合 |
| PoseForge – Local-first AI studio for images and video | github.com/vishwakulkarni/PoseForge | 1／1 | 本地 AI，GUI 為主，沙盒驗證較難 |
| Local DirectML AI and Floating Toolstrip for PhotoCraft in Rust | github.com/kobaltgit/photocraft-companion | 1／0 | Windows 限定，沙盒難驗證 |
| UnCode – Local voice dictation for Linux | github.com/XLongLink/uncode | 1／0 | 本地 AI，正好是 brief 的語音輸入例子 |

（查核重跑時候選池多了新貼文，同一個 seed 抽到的第 4 筆變成「Grass – a zero-config terminal text editor」，github.com/mukundzha/grass，3 points。抽樣結果會隨時間變，不是固定清單。）

觀察：5 筆都是 1 point、幾乎沒人看過，符合「默默無聞」；但品質未知，**要靠驗證 agent 判斷**。GitHub 星數與 repo 建立時間沒測到：這個環境的 proxy 擋 `api.github.com`，腳本沒有呼叫 GitHub。

### 3.2 `spikes/ch_comm_feeds.py`（`uv run --script`，內嵌依賴 `websockets`）

```bash
uv run --script spikes/ch_comm_feeds.py                                   # 全部，約 4 分鐘
uv run --script spikes/ch_comm_feeds.py --only devto,bsky                 # 只跑部分
uv run --script spikes/ch_comm_feeds.py --only jetstream --jetstream-seconds 300
```

做的事：dev.to `#showdev` 7 天計數＋抽樣讀內文（查核者已修正翻頁邏輯，見 2.6）；Mastodon 3 站 6 tag 7 天計數；Bluesky 未登入搜尋；Bluesky Jetstream live tail 取樣。Lobsters 刻意不抓（robots.txt）。

| 管道 | 7 天量 | GitHub repo 連結 | 兩類別（關鍵字） | 備註 |
|---|---|---|---|---|
| dev.to #showdev | 887 篇（修正後重跑；原 713 為低估） | 抽 40 篇內文，23 篇（57%） | CLI 25、本地 AI 33 | 645 篇 0 reaction |
| Mastodon（3 站 6 tag） | 1,098 則（去重） | 66 則 | 像作者自介 4 則 | 32/66 帳號 `indexable=false`；8 則來自 bot 帳號 |
| Bluesky 搜尋（未登入） | "I built" 39、"I made" 45、"just released" 21、"I wrote" 19、"open source" 252 | 全部限 `domain=github.com` | "I made" 中 CLI 12；"open source" 中本地 AI 10 | 翻頁 403；public.api 403 |
| Bluesky Jetstream | 約 52 則／秒（300 秒 15,571 則，約 450 萬／天） | 300 秒 5 則（5 個帳號，約 1,400／天）；120 秒 42 則（bot 爆量）；30 秒 0 則 | 作者口吻 0 則（300 秒）；120 秒那 1 則是 HN 轉貼 bot | 被動聽 firehose 找作品不划算；適合 @mention 即時提交 |

---

## 4. 結論

### 黑客松期間值得接

| 管道 | 理由 | 預估工時 |
|---|---|---|
| **HN Show HN** | 規則定義就是「作者本人做、可試用」；每週約 75 筆兩類別候選且連 GitHub；86% 幾乎沒人看過；官方 Firebase API 與 HN 搜尋框所連的 Algolia API 都免金鑰、免審核、免費（Algolia 不是 YC 營運） | 2–4 人時：Algolia 每日回補＋Firebase `newstories` 輪詢、去重、只存 metadata，交給 Muse Spark 分類 |
| （可選）**Bluesky @mention 提交** | Threads 提交入口的備案；Jetstream 免認證、即時，demo 可現場展示「發文 → 幾分鐘後可推薦」；作者主動標記等於同意 | 3–4 人時：開 pickfit 帳號、Jetstream 篩 mention、處理 delete 事件；不要對每個 mention 自動回覆（Developer Guidelines 的 spam 定義） |

做法上的共同原則：**社群貼文只當「發現線索」，軟體事實一律從 GitHub repo（README、release、授權）讀**。這樣同時降低條款風險（不轉載貼文內容），也讓 demo 看起來是「主動發現＋驗證」而不是「把貼文存起來再查」的基本 RAG。

### 之後擴充

| 管道 | 條件或原因 |
|---|---|
| dev.to #showdev | 量大（7 天約 887 篇）、免金鑰；但網站 Terms 對內容重用保守，接之前先向 DEV 書面確認。兩類關鍵字量相近（CLI 25、本地 AI 33），精準度未驗證。黑客松有空檔才接（2–3 人時） |
| Bluesky 關鍵字搜尋 | 需用 App Password 登入才能翻頁；雜訊高，要模型過濾 |
| X | 量大，但每則 $0.005，要綁卡；先只收作者提交的連結 |
| Mastodon | 只做 @mention 提交；尊重 `indexable`、`noindex`、`#nobot` |
| Discord | 只做「作者邀 bot 進自己伺服器」的同意制提交 |

### 要避開

| 管道 | 原因 |
|---|---|
| Reddit | 商用要另簽約、不能營利、不能拿去訓練、只能保留核准用途的資料；Responsible Builder Policy 規定經 API 存取任何資料都要先申請核准（已驗證），非商用開發者被導向 Devvit。brief 的結論對，但「競爭資料庫」不是條款原文，建議改寫理由 |
| Product Hunt | API 文件明寫不得商用；要 token；內容以行銷型 SaaS 為主 |
| LinkedIn | 沒有讀別人貼文的開放權限；member data 限 48 小時、不得匯出或合併 |
| Indie Hackers | 沒有 API；robots.txt 擋 `/api/` 與 AI bot；網站回 403 |
| Lobsters（自動抓，包括抓使用者提交的 Lobsters 連結） | robots.txt 對一般 bot `Disallow: /`，並宣告 `ai-input=no`；量也太少（約 3 筆／週）。提交入口收到 Lobsters 連結時，請提交者改貼 GitHub 連結 |

### 建議 brief 修改（給主控者）

- 第 8 節 Reddit 的理由改成：「商用需另簽約、禁止用於訓練模型、資料只能留在核准用途、經 API 存取一律要先申請核准（Responsible Builder Policy）」。
- 第 8 節 Hacker News 補一句：用 Algolia 或 Firebase `newstories`，**不要只用 `showstories`**（它只收過門檻的 14%，剛好漏掉沒人知道的作品）。
- 第 4.1 節來源可加「Bluesky @mention 提交（Jetstream）」當 Threads 的備案。

---

## 5. 來源

全部於 2026-10-28（台北）／2026-10-27 UTC 查證。

**Hacker News**
- HN API（官方）：https://github.com/HackerNews/API
- Firebase 端點：https://hacker-news.firebaseio.com/v0/showstories.json 、https://hacker-news.firebaseio.com/v0/newstories.json
- Algolia HN Search API：https://hn.algolia.com/api （rate limit 原文在 https://hn.algolia.com/public/main-6e634771f729331a3c3c.js）
- Show HN Guidelines：https://news.ycombinator.com/showhn.html
- HN FAQ：https://news.ycombinator.com/newsfaq.html
- YC Terms of Use／Privacy（HN 頁尾「Legal」）：https://www.ycombinator.com/legal/
- HN robots.txt：https://news.ycombinator.com/robots.txt

**Lobsters**
- https://lobste.rs/t/show.json 、https://lobste.rs/newest.json
- https://lobste.rs/robots.txt
- https://lobste.rs/about（查核者改讀原始碼 https://github.com/lobsters/lobsters/blob/master/app/views/about/about.html.erb ，未抓網站）
- 單頁筆數：https://github.com/lobsters/lobsters/blob/master/app/models/stories_paginator.rb

**Reddit**
- Data API Terms：https://redditinc.com/policies/data-api-terms
- Developer Terms：https://redditinc.com/policies/developer-terms
- Data API Wiki（HTML 頁 403；查核者經 Help Center API 讀到原文）：https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki ；https://support.reddithelp.com/api/v2/help_center/en-us/articles/16160319875092.json
- Responsible Builder Policy（HTML 頁 403；查核者經 Help Center API 讀到原文）：https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy ；https://support.reddithelp.com/api/v2/help_center/en-us/articles/42728983564564.json
- 社群轉述（未驗證）：https://r.datuan.dev/r/redditdev/comments/1oug31u/introducing_the_responsible_builder_policy_new/noc31sg

**X**
- 定價：https://docs.x.com/x-api/getting-started/pricing
- 概覽：https://docs.x.com/x-api/getting-started/about-x-api
- Search：https://docs.x.com/x-api/posts/search/introduction
- 免費額度：https://docs.x.com/x-api/getting-started/free-credits
- Developer Policy：https://docs.x.com/developer-terms/policy

**Product Hunt**
- API v2 文件：https://api.producthunt.com/v2/docs

**dev.to**
- Forem API v1：https://developers.forem.com/api/v1
- 端點：https://dev.to/api/articles?tag=showdev
- DEV Terms：https://dev.to/terms
- robots.txt：https://dev.to/robots.txt

**Indie Hackers**
- robots.txt：https://www.indiehackers.com/robots.txt

**LinkedIn**
- Getting Access：https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access
- Restricted Uses：https://learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases

**Discord**
- OAuth2：https://docs.discord.com/developers/topics/oauth2
- Gateway（Message Content Intent）：https://docs.discord.com/developers/events/gateway
- Developer Policy（HTML 頁 403；查核者經 Help Center API 讀到原文）：https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy ；https://support-dev.discord.com/api/v2/help_center/en-us/articles/8563934450327.json
- 第三方轉述（已由上面原文取代）：https://gigazine.net/gsc_news/en/20250522-discord-scrape-publish-2-billion-message

**Bluesky**
- Jetstream：https://bsky.network/docs/jetstream
- Network Replay：https://bsky.network/docs/jetstream-replay
- API Hosts and Auth：https://bsky.network/docs/api-directory
- Rate Limits：https://bsky.network/docs/rate-limits
- Developer Guidelines：https://bsky.network/docs/developer-guidelines
- Terms of Service：https://bsky.social/about/support/tos
- searchPosts 403 的社群回報（未驗證）：https://github.com/bluesky-social/bsky-docs/issues/332
- （舊網址 docs.bsky.app 已 308 轉到 bsky.network/docs）

**Mastodon**
- Timelines API：https://docs.joinmastodon.org/methods/timelines/#tag
- Account 實體：https://docs.joinmastodon.org/entities/Account/
- mastodon.social 規則與 ToS：https://mastodon.social/api/v1/instance/rules 、https://mastodon.social/api/v1/instance/terms_of_service
- fosstodon.org 規則與 robots：https://fosstodon.org/api/v1/instance/rules 、https://fosstodon.org/robots.txt
- hachyderm.io 規則：https://hachyderm.io/api/v1/instance/rules

---

## 查核紀錄（2026-10-28）

查核者：另一個 agent。時間：2026-10-28（台北）／2026-10-27 20:17–20:40 UTC。方法：官方文件原文（curl 下載後擷取原句）、實際打 API、重跑兩支腳本。沒有用第三方文章當證據。

### 關鍵主張逐條結果

| # | 主張 | 判定 | 怎麼查的 | 改了什麼 |
|---|---|---|---|---|
| 1 | Show HN 規則：「something you've made that other people can play with」「worked on personally」 | 正確 | 下載 showhn.html 擷取原句；另確認「Don't post quickly-generated one-offs」也在 | 無 |
| 2 | Firebase 無 rate limit；showstories 最多 200、只收過門檻的；只涵蓋 14% | 部分修正 | README 原句確認；重跑腳本 142/993＝14%；另寫一次性檢查 | showstories 不是「過門檻就收」的完整清單：全部 ≥2 points，但 ≥2 points 的只有 37% 在裡面，且 142 筆中 73 筆是 2–3 points。改寫 2.1 |
| 3 | Algolia 10,000 次／小時／IP；992 筆、35% 連 GitHub、86% ≤3 points | 正確 | main.js 原句；重跑得 993 筆、346（35%）、856（86%）、兩類且連 GitHub 75 | 補「每個查詢最多前 1,000 筆」實測；Algolia 不是 YC 營運，結論表的「兩個官方入口」改寫 |
| 4 | YC 條款禁止 data mining／robots／scraping 與商用重製；兩段都以「Except as expressly authorized」開頭 | 部分錯誤 | 下載 ycombinator.com/legal 擷取原句 | data mining／robots 那句**沒有**例外字樣，例外字樣在前一句（modify, copy, frame, scrape…）。改寫 2.1 條款段，並補「intentionally made available … through the Site」一句當 API 的依據 |
| 5 | Reddit：商用另簽約、不得訓練、只保留核准用途資料；沒有「競爭資料庫」字樣 | 正確 | 下載 Data API Terms（Last Revised July 20, 2026）與 Developer Terms（Last Revised March 24, 2026），原句都在；搜尋「compet」只出現在 Reddit 可能開發競品的免責句 | 無 |
| 6 | Responsible Builder Policy：2025-11 起新 OAuth token 要先核准（未驗證） | 改為已驗證，日期修正 | HTML 頁仍 403，但 Help Center API `…/articles/42728983564564.json` 回 200，讀到全文 | 原文是「must request access and get explicit approval before accessing any Reddit data through our API」，不限「新 token」；文章建立 2025-10-28。順便驗證 Data API Wiki 的 100 QPM |
| 7 | X：$0.005／則、24 小時去重、每月 300 萬上限、無免費讀取層；Recent Search 7 天 | 正確 | 下載 pricing.md、search introduction.md、free-credits.md | 補充 $20 免費額度要先完成第一次購買、3 個月過期 |
| 8 | Product Hunt API 不得商用、要 access_token | 正確 | 下載 v2/docs 擷取原句；實測無 token 打 GraphQL 回 401 | 補 401 實測 |
| 9 | dev.to 免金鑰 200；#showdev 7 天 713 篇；Terms 只允許 personal non-commercial viewing；無獨立 API 條款 | 數字錯誤，其餘正確 | 實測 200；Forem 文件原句；dev.to/terms 原句；逐頁計數 | **713 是低估，實際約 887**。列表不是按時間排序，舊腳本第 1 頁就停。已修正 `spikes/ch_comm_feeds.py` 並重跑。「本地 AI 偏少」與數字不符，改寫 |
| 10 | Jetstream live tail 免認證、不計量；replay 要 key、按位元組計量 | 正確 | jetstream 與 jetstream-replay 頁原句 | 無 |
| 11 | searchPosts：public.api 403；api.bsky.app 第一頁 200、翻頁 403；bsky.social 401 | 正確 | 逐一 curl 重測，三個結果都一樣（翻頁回「Request forbidden by administrative rules」） | 「do not support authentication」的出處改成 Rate Limits 頁 |
| 12 | Bluesky Developer Guidelines：刪除、檢舉、公開 email、禁止自動大量互動 | 正確 | developer-guidelines 頁原句 | 補充：自動回覆 mention 也算會觸發通知的自動互動，建議不要每則都回 |
| 13 | Mastodon tag timeline 公開、關閉預覽時要 token（infosec.exchange 422）；32/66 帳號 indexable=false | 正確 | Mastodon 官方文件 repo 的 timelines.md／Account.md；實測 infosec.exchange 422；重跑得 1,101 則、66、32 | 表格「多數站免登入」改成「實測 4 站中 3 站」 |
| 14 | LinkedIn 開放權限只有 profile、email、w_member_social；member social activity 最多存 48 小時、不得匯出或結合 | 正確 | 兩頁原句（Getting Access ms.date 2025-06-24；Restricted Uses ms.date 2022-12-09） | 無；`r_member_social` 是否關閉仍未驗證 |
| 15 | Discord：MESSAGE_CONTENT 特權 intent；100+ 伺服器要驗證核准；Developer Policy 禁止訓練與 scraping（未驗證） | 改為已驗證 | gateway 頁原句；Developer Policy 經 Help Center API `…/articles/8563934450327.json` 讀到全文（Effective July 8, 2024） | 換成原文第 18、20、21 條；第三方轉述降為參考 |
| 16 | Lobsters robots：一般 UA `Disallow: /`、搜尋引擎組 `Content-Signal: ai-input=no, ai-train=no`；show tag 近 60 天 25 筆 | robots 正確；筆數未重測 | 下載 robots.txt；從 GitHub 原始碼確認單頁上限 25、About 頁 RSS 原句 | 為遵守 robots.txt 沒有重抓 show.json。補註 25 是單頁上限 |

### 其他影響決策的檢查

| 項目 | 結果 |
|---|---|
| Firebase `/v0/newstories` 涵蓋時間與 Show HN 重疊 | 重測：500 筆涵蓋 6.7 小時，其中 Show HN 89 筆，與 Algolia 同時段 100% 重疊。每 1–3 小時輪詢的建議成立 |
| HN 搜尋框是否連到 Algolia | 是，表單 `action="//hn.algolia.com/"` |
| Indie Hackers robots 與 403 | robots.txt 原文正確（`/api/` 對所有 UA 擋；`meta-externalagent`、`ClaudeBot` 等 `Disallow: /`）；首頁實測 403 |
| Bluesky ToS | Last Updated 14 August 2025；全文沒有 scrape／crawl 相關限制 |
| mastodon.social ToS 生效日、fosstodon 規則與 robots | 2026-08-31 生效；「DO NOT post commercial promotions, or advertise」；robots 擋 GPTBot。皆正確 |
| 建議是否與條款衝突 | 兩處調整：(1) Lobsters 提交連結不要去抓頁面；(2) Bluesky 不要自動回覆每個 mention。HN 補強「絕不爬 HTML」的理由。其餘建議（Reddit／PH／LinkedIn／Indie Hackers 避開、X 只收連結、Discord 與 Mastodon 只做同意制提交）與條款一致 |

### 腳本重跑

| 腳本 | 能否重跑 | 結果與原稿是否一致 |
|---|---|---|
| `spikes/ch_comm_hn_showhn.py` | 可以，約 10 秒，無金鑰 | 一致（993 vs 992 筆，差異來自時間窗移動）。同一 seed 的第 4 筆抽樣換了一筆，因為候選池變了 |
| `spikes/ch_comm_feeds.py` | 可以，約 4 分鐘，無金鑰（`uv run --script`） | Mastodon、Bluesky 搜尋、Jetstream 一致；**dev.to 不一致**（800 vs 713），原因是翻頁 bug。已修正：改成翻到某頁沒有新的 7 天內文章才停（最多 10 頁）、依 id 去重。修正後重跑 887 篇 |

兩支腳本都沒有金鑰、token 或密碼字串（已 grep 確認）。

### 仍未驗證

- Reddit 審核實際要等多久、通過率（只有社群說法）。
- LinkedIn `r_member_social` 是否已對外關閉。
- Algolia HN Search 是否有獨立使用條款（只確認頁面上沒有連結）。
- Lobsters show tag 的最新筆數（為遵守 robots.txt 未重抓）。
- dev.to 兩類關鍵字分類的精準度。
