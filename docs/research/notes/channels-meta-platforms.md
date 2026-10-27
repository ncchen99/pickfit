2026-10-28 · Meta 平台（Threads、Facebook、Instagram）作為「作者分享作品」的管道 · 由調研 agent 撰寫，待主控者整合

# 管道調研：Meta 自家平台

需求來源：[brief.md](../../brief.md) 第 4.1、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。所有查證日期都是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。

## 一句話結論

Meta 平台**不能當「主動發現」的來源**，也**不能合規地把 Threads 貼文內容交給模型讀**；只能當**「展示、擴散」的管道**（oEmbed 嵌入原貼文、分享按鈕、自家帳號發文）。作者提交改走「自己貼 GitHub 連結」。〔查核修正：原寫「可以當作者本人提交的管道」〕

- 搜尋別人的公開貼文（Threads keyword search、IG hashtag、FB 粉專）都要 App Review；商家驗證 FB 粉專寫明必要，其他是「可能需要」（官方用語 may／might，見第 3 節）。允許用途各不相同：Threads keyword search 是「管理自己的社群形象」，IG hashtag 是品牌活動與輿情，FB 粉專是「分析或顯示粉專貼文」，都不是建軟體目錄。6 天內過不了，就算有時間，用途也對不上。〔查核修正：原文寫「都要商家驗證」「允許用途都是經營自己的社群形象」，過度概括〕
- 不審核（Development mode）時，Threads API 只讀得到 **app 角色使用者（Threads tester）自己的貼文**。技術上夠做「作者用 Threads 登入、選自己的貼文提交」，**但條款上不行**：`threads_basic` 的允許用途只限「把作者自己的貼文顯示給作者本人看」，把貼文交給 Muse Spark 抽取、變成公開檔案，屬於允許用途以外的處理，Platform Terms 3.a.viii 禁止（見 2.1）。〔查核修正〕
- oEmbed 現在不用 token，但回傳的 html **不含貼文文字**（實測），而且條款**禁止**把 oEmbed 內容拿去做顯示以外的用途。只能拿來在展示頁嵌入原貼文。
- 連結提交的含意：**Threads 貼文內容，我們沒有合規的方法交給模型讀**（不能爬、oEmbed 沒文字、讀單篇貼文要 Advanced Access、作者登入讀自己貼文也受允許用途限制）。所以 brief 4.1「貼 Threads 連結就收錄」要改成「提交者自己附上 GitHub 連結與說明」，Threads 連結只拿來用 oEmbed 嵌入。〔查核修正：原文把「作者用 Threads 登入」列為可行選項〕

---

## 1. 比較表

整合成本只算黑客松版本、一個人的人時，不含等待審核的時間。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制 | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| Threads 作者登入提交（`threads_basic`，讀 `/me/threads`，交給模型抽取） | 高：作者本人選的貼文，附連結、截圖，身分已驗證 | 少，靠作者主動來 | 低 | API（OAuth） | 未審核只限 app 角色使用者；公開上線要 App Review（商家驗證可能需要）；**允許用途只限把貼文顯示給作者本人，交給模型抽取並公開衍生內容不在允許用途內**（見 2.1） | 5–7 h | **避開**〔查核修正：原為「黑客松接」。與 `threads_basic` 允許用途及 Platform Terms 3.a.viii 衝突，比賽規則第 3 節也禁止違反平台政策的專案〕 |
| **GitHub 連結提交＋可選的 Threads 貼文連結**（查核者補充） | 高：提交者自己貼 GitHub 連結與說明，不經 Meta API | 少，靠作者主動來 | 低 | 表單 | Threads 連結只拿來 oEmbed 嵌入，不讀內容 | 1 h（表單；GitHub 讀取另計） | **黑客松接**（取代上一列） |
| **Threads oEmbed**（無 token） | 無：html 裡沒有貼文文字 | — | — | API（免金鑰） | 只能做前端顯示；禁止抽取、保存、分析；文件寫每小時 1,000 次，但免 token 版「Rate limits may differ」（未驗證） | 0.5–1 h | **黑客松接**（只用來嵌入原貼文） |
| **Threads Web Intents**（分享按鈕） | 不是資料來源，是擴散 | — | — | 網址 | 無審核 | 0.5 h | **黑客松接**（被收錄的作者一鍵分享） |
| **Threads 自家帳號發文＋讀自己貼文的回覆**（`threads_content_publish`、`threads_read_replies`） | 中：回覆者主動貼作品，但要過濾 | 視貼文觸及率，初期很少 | 中 | API（OAuth，自己帳號） | 發文 250 篇／24h；非角色使用者的回覆在未審核時看不看得到，**文件沒寫，未驗證**；把回覆內容交給模型收錄是否在 `threads_read_replies` 允許用途內，**未驗證，風險高**（見 2.4） | 2–4 h | **可選**：只做「發文」；「讀回覆收錄」先不做〔查核修正〕 |
| Threads keyword／topic tag search（`threads_keyword_search`） | 中：可搜 "I built"、topic tag，但大多是閒聊 | 多 | 高 | API | 未審核只搜得到**自己的**貼文；審核可能要商家驗證；允許用途是「管理社群形象」，**消費者 app 嚴格禁止**；2,200 次／24h | 3 h＋審核 | **避開**（黑客松）；之後也不建議 |
| Threads mentions（被 @pickfit 標記；含 webhook） | 高：作者主動標記 | 少 | 低 | API／webhook | 未審核只回 Threads tester 的標記；webhook 要 Live mode＋商家驗證 | 3–4 h＋審核 | **之後擴充** |
| Threads profile discovery（`profile_lookup`、`profile_posts`） | 中 | — | 中 | API | 未審核只能查 @meta、@threads、@instagram、@facebook；只回 ≥100 粉絲的帳號；允許用途是「競品分析」 | 2 h＋審核 | **避開**：長尾作者常不到 100 粉絲 |
| 直接抓 threads.com 網頁、非官方 API | — | — | — | 爬取 | robots.txt 與 Automated Data Collection Terms 禁止，需 Meta 書面許可 | — | **避開** |
| Facebook Groups API | — | — | — | 已移除 | 2024-04-22 全版本移除 | — | **避開**（不存在） |
| Facebook 粉專（Page Public Content Access） | 低：獨立開發者很少經營粉專 | 少 | 中 | API | App Review＋商家驗證；未審核只看得到自己管理的粉專 | 3 h＋審核 | **避開** |
| Facebook／Instagram oEmbed（無 token） | 無：html 沒有文字 | — | — | API（免金鑰） | 同 Threads oEmbed，只能做前端顯示 | 0.5 h | 之後擴充（只嵌入） |
| Instagram hashtag search | 低：開發工具很少在 IG 發表 | 少 | 高 | API | 要 IG 商業／創作者帳號、App Review；每 7 天 30 個 hashtag；`recent_media` 只回 24 小時內；允許用途是品牌活動 | 4 h＋審核 | **避開** |
| Meta Content Library／API | 高（全量公開資料） | 多 | 中 | 研究用 cleanroom | 只限合格學術或非營利研究機構；審查約 4–6 週；API 只能在 cleanroom 用；UI 只能下載 FB／IG 的公開資料子集，Threads 不能下載〔查核修正：原寫「資料不能帶出 cleanroom」〕 | — | **避開**：pickfit 不符資格 |

---

## 2. 各管道細節

### 2.1 Threads：作者用 Threads 登入、提交自己的貼文（查核結論：避開，理由見「條款風險」）

- **做法**：作者按「用 Threads 提交」→ OAuth 取得 `threads_basic` → 呼叫 `GET /me/threads?since=…` 列出最近的貼文 → 作者選一篇 → 拿 `text`、`link_attachment_url`、`media_url`（截圖、影片）交給 Muse Spark 讀懂 → 找到 GitHub 連結後進驗證流程。
- **能不能拿到「作者自己發表、最近才出現、沒什麼人知道」的貼文**：技術上能（貼文是作者本人的，可以用 `since` 限定最近幾天），**但條款上不行**，見下方「條款風險」。〔查核修正：原寫「這是唯一合規又拿得到內容的路」〕
- **不審核時**：只有 app 角色使用者能授權。官方原文：「[Threads testers] can grant your app these permissions at any time. In order for app users without a role on your app to be able to grant your app these permissions, each permission must first be approved through the App Review process, and your app must be published.」（[Get started](https://developers.facebook.com/documentation/threads/get-started)）
- **Threads tester 不能隨便邀**：「You may only add a person as a Tester to your app if they are your employee or you have an agreement with them which establishes that they are acting on your behalf as a tester of your app.」（[App Roles](https://developers.facebook.com/documentation/development/build-and-test/app-roles)）。未連結已驗證商家的 app 最多 50 位 tester。demo 用自己的帳號最乾淨。
- **條款風險（高，查核修正：原為「中」）**：`threads_basic` 的允許用途寫得很窄：「The allowed usage for this permission is to display a user's own Threads posts within a business app, and make these visible only to the user who created them. It is not intended for any other purpose. For example, using threads_basic permission in a consumer app is strictly prohibited.」Allowed Usage 欄還多一句「for the purpose of managing the user's presence on Threads」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)，2026-10-28 查證）。Threads API 總覽也寫「display those posts within your app solely to the person who created it」（[Overview](https://developers.facebook.com/documentation/threads/overview)）。再加上 Platform Terms 3.a.viii 禁止「Processing Platform Data for purposes other than the applicable permitted purposes set forth in Meta's Developer Docs」（[Platform Terms](https://developers.facebook.com/terms/)）。
  - **為什麼原本的因應不夠**：Platform Terms 對 Platform Data 的定義包含「data anonymized, aggregated, or derived from such data」，「Process」包含 use、transmission。把貼文交給 Muse Spark 抽取、再把抽出的 GitHub 連結與摘要變成公開檔案，就是把 Platform Data 處理成衍生資料並給別人看，超出「只顯示給作者本人、用於經營作者自己的 Threads 形象」。「不長期保存」「公開檔案以 GitHub 為主」都不改變這一點，因為 GitHub 連結本身是從貼文取出的。Platform Terms 自使用 Platform 起就適用，Development mode 不豁免。比賽規則第 3 節也排除「違反平台政策的專案」，評審又是 Meta。
  - **改為**：黑客松不做 Threads 登入讀貼文。提交入口改成「提交者自己貼 GitHub 連結與說明」（使用者自己提供的內容，不是透過 API 取得的 Platform Data），可選附上 Threads 貼文連結，只用 oEmbed 嵌入。若之後仍想做，先向 Meta 確認允許用途（例如透過 App Review 的 use case 說明或開發者支援），再動工。
  - **灰色地帶（未驗證）**：只把作者自己的貼文列給作者看、讓他挑一篇存 permalink 供 oEmbed 嵌入、不把內容交給模型。這可能在允許用途內，但「用登入證明提交者就是作者」本身是不是允許用途，文件沒寫。花 5–7 h 換這點價值不划算。
- **兩個 demo 類別**：開發者 CLI 工具、本地 AI／LLM 工具的作者都會在發文附 GitHub 連結與終端機截圖，`link_attachment_url` 與 `media_url` 剛好能讓 Muse Spark 的多模態發揮。兩類差別不大。
- **頻率**：每個 app 與使用者組合每 24 小時可呼叫 `4800 × 曝光數` 次，曝光數最低算 10，所以至少 48,000 次（[Overview](https://developers.facebook.com/documentation/threads/overview)）。對提交流程綽綽有餘。

### 2.2 Threads oEmbed（不用 token）

- 2026-03-03 起 Threads oEmbed 不需要 token：「You can now call Threads oEmbed API without an access token.」（[Threads Changelog](https://developers.facebook.com/documentation/threads/changelog)）。2026-06-15 起 Facebook、Instagram 的 oEmbed 也一樣（[Meta 部落格](https://developers.facebook.com/blog/post/2026/06/15/tokenless-access-to-meta-oembed-apis/)）。
- **實測**：回傳欄位只有 `html`、`provider_name`、`provider_url`、`type`、`version`、`width`。html 裡可見的文字只有「View on Threads」，**沒有貼文內文、沒有 GitHub 連結**；內容是瀏覽器載入 `embed.js` 之後才畫出來的。
- **條款**：「Using metadata and post content (or their derivations) from the endpoint for any purpose other than providing a front-end view of the post is strictly prohibited. This prohibition encompasses consuming, manipulating, extracting, or persisting the metadata and content…」（[Embed a Threads Post](https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post)）。
- **結論**：「貼 Threads 連結 → oEmbed 取文字 → Muse Spark 讀懂」這條路**技術上拿不到文字，條款上也不准**。oEmbed 只能用在展示頁嵌入原貼文。限制：每小時 1,000 次（文件數字；免 token 呼叫的上限部落格寫「Rate limits may differ」，未驗證）；私人、停用、年齡限制、地區限定的貼文不支援。

### 2.3 Threads Web Intents（分享按鈕）

- `https://www.threads.com/intent/post?text=…&url=…&tag=…` 會打開 Threads 的發文框，預先填好文字、連結與 topic tag（[Web Intents](https://developers.facebook.com/documentation/threads/threads-web-intents)）。不需要 app、token 或審核。
- 用途：作品被收錄、驗證通過後，展示頁給作者一個「分享到 Threads」按鈕。這是供給端的擴散迴圈，可能間接幫到 Community Vote（看公開展示頁的票數）。**Most Viral 只算 X 上 demo 貼文的讚、轉推、留言**（[hackathon-rules.md](../../hackathon-rules.md) 第 5 節），Threads 分享不計入。〔查核修正：原寫「也對 Most Viral／Community Vote 有幫助」〕

### 2.4 Threads 自家帳號：發文與讀回覆

- **發文**：pickfit 自己的 Threads 帳號（app 管理員本人）用 `threads_content_publish` 發「今日寶藏」。允許用途「enable a business app user to create and publish content to their Threads profile」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)），符合。上限 250 篇／24h（[Overview](https://developers.facebook.com/documentation/threads/overview)）。
- **徵件串**：發一篇「留言貼你的 CLI 或本地 AI 工具」，再用 `GET /{media-id}/replies` 讀回覆。`threads_read_replies` 的允許用途是「get replies to a thread owned by the business app user」，**讀取本身符合**；但同一段也寫「It is not intended for any other purpose. For example, using threads_read_replies permission in a consumer app is strictly prohibited.」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)）。把別人的回覆交給 Muse Spark 抽取、收進公開目錄，是否算允許用途，**文件沒寫，未驗證**；比照 2.1 的解讀，風險高。〔查核修正：原寫「符合」〕可以搭配 2026-02-13 新增的 reply approvals，回覆要審核才公開，可擋垃圾留言（[Changelog](https://developers.facebook.com/documentation/threads/changelog)）。
- 補充：所有 `threads_*` 權限（含 `threads_content_publish`、`threads_read_replies`）的允許用途都附「in a consumer app is strictly prohibited」，不只 keyword search 與 basic。用 pickfit 自家帳號發文屬於「經營自己的 Threads 形象」，查核者判斷在允許用途內。
- **未驗證的關鍵點**：mentions、keyword search、讀單篇貼文的文件都寫明「未審核只回 tester 的內容」，回覆的文件（[Replies and Conversations](https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/replies-and-conversations)）**沒有這句**，只說 `username` 「only works for public users and your own user」。未審核時看不看得到非角色使用者的回覆，要拿到 token 後實測。
- **雜訊與新作品量**：取決於 pickfit 帳號的觸及，新帳號初期回覆會很少。對兩個 demo 類別沒有差別。

### 2.5 Threads keyword／topic tag search

- 端點 `GET /keyword_search`，參數 `q`、`search_type`（TOP／RECENT）、`search_mode`（KEYWORD／TAG）、`media_type`、`since`、`until`、`limit`（最多 100）、`author_username`（[Keyword Search](https://developers.facebook.com/documentation/threads/keyword-search)）。
- **搜誰的貼文**：「If your app has not been approved for the threads_keyword_search permission, the search will be performed only on posts owned by the authenticated user. After approval, public posts will be searchable.」不審核就只搜得到自己的貼文，對發現毫無用處。
- **時間範圍**：沒有「只限最近 7 天」的限制。`since` 只要求「greater than or equal to 1688540400」（2023-07-05），`until` 不超過現在。
- **次數**：「A user can send a maximum of 2,200 queries within a rolling 24-hour period.」上限算在使用者身上、跨 app 共用；同一關鍵字重查也算；沒結果的查詢不算。敏感字回空陣列。
- **topic tag**：`search_mode=TAG` 可搜 topic tag。但 Threads 每篇貼文**只能有一個** topic tag（[Posts](https://developers.facebook.com/documentation/threads/posts)），和 X 的多 hashtag 習慣不同，#buildinpublic 這類標籤的覆蓋率未驗證。
- **允許用途對不上**：「The allowed usage for this permission is to help the user manage their social media presence. It is not intended for any other purpose. For example, using threads_keyword_search permission in a consumer app is strictly prohibited.」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)）。用來建軟體目錄，審核大概會被拒。
- 回傳不含 `owner`；欄位有 `text`、`permalink`、`timestamp`、`username` 等。

### 2.6 Threads mentions 與 webhook

- 「If your app has not been approved for advanced access for the threads_manage_mentions permission, the API returns only mentions made by a Threads tester on the app.」（[Mentions](https://developers.facebook.com/documentation/threads/threads-mentions)）。私人帳號的貼文不會回傳。
- Webhook 可以即時收到「有人 @pickfit」，但條件是「For non-tech providers, the apps must be in Live Mode」與「The business connected to the app must be verified」，而且「Your app must have successfully completed App Review (Advanced Access) to receive webhook notifications for all of the fields.」（[Webhooks](https://developers.facebook.com/documentation/threads/webhooks)）。
- 長期很適合：作者發文時標記 @pickfit 就等於提交，訊號乾淨。黑客松期間做不到。

### 2.7 Threads profile discovery

- `GET /profile_lookup`、`GET /profile_posts` 需要 `threads_profile_discovery`。「With standard access, only some of the official Meta accounts can be looked up. These include @meta, @threads, @instagram, and @facebook.」「Only returns public profiles with at least 100 followers.」每 24 小時 1,000 次（[Threads Profiles](https://developers.facebook.com/documentation/threads/threads-profiles)、[Retrieve Posts](https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts)）。
- 允許用途是「to conduct competitor analyses」。長尾作者常常不到 100 粉絲，正好是我們要找的人被排除。避開。
- 讀單篇貼文 `GET /{media-id}` 也一樣：「If your app has not been approved for advanced access for the threads_basic permission, only posts created by a Threads tester are retrievable.」

### 2.8 爬 Threads、Facebook、Instagram 網頁

- 三站 robots.txt 開頭都寫：「Collection of data on Threads through automated means is prohibited unless you have express written permission from Threads…」（實測，見第 4 節）。
- [Automated Data Collection Terms](https://www.facebook.com/legal/automated_data_collection_terms)（2024-10-07 生效）：「You will not engage in Automated Data Collection without first obtaining Meta's express written permission.」定義包含 scraper、bot、crawler。
- 就算是使用者貼來的單一連結，程式去抓 threads.com 頁面也算自動化收集。避開。
- 補充來源（查核者，2026-10-28）：Meta 開發者文件 [Automated Data Collection](https://developers.facebook.com/documentation/development/terms-and-policies/automated-data-collection) 寫「Platform APIs are the only allowable means to access data programmatically, unless you have our prior written permission.」並引用 Facebook Terms of Service 3.2.3。

### 2.9 Facebook

- **Groups API**：「The Facebook Groups API is deprecated in v19 and in 90 days will be removed from all versions. This deprecation includes all Permissions (publish_to_groups, groups_access_member_info) and Reviewable Features (Groups API)…」（[v19 公告](https://developers.facebook.com/blog/post/2024/01/23/introducing-facebook-graph-and-marketing-api-v19/)）。[v19 changelog](https://developers.facebook.com/docs/graph-api/changelog/version19.0) 寫「These permissions, features, and abilities will be removed April 22, 2024.」2026-10-28 實測，舊的 `/docs/groups-api` 網址已轉回文件首頁。
- **粉專（PPCA）**：「This permission or feature requires successful completion of the App Review process before your app can access live data.」「This permission or feature is only available with business verification.」未審核時「your app can only access content on a Page for which… The person who holds the admin role for the Page also holds an admin, developer, or tester role on the app.」允許用途「Analyze and/or display posts and engagement on Pages.」（[Page Public Content Access](https://developers.facebook.com/docs/features-reference/page-public-content-access)）。
- **對 pickfit**：獨立開發者、學生很少為 CLI 或本地 AI 工具開粉專（判斷，未量化）。成本高、訊號少，避開。
- **oEmbed**：`oembed_post` 不帶 token 回 200，但 html 只有一個 `fb-post` 的 div，沒有文字（實測）。舊的 [oEmbed Read 功能頁](https://developers.facebook.com/docs/features-reference/oembed-read) 還寫「Requires App Review」，已被 2026-06-15 的免 token 公告取代。

### 2.10 Instagram hashtag search

- 「You can query a maximum of 30 unique hashtags on behalf of an Instagram Business or Creator Account within a rolling, 7 day period.」「In order to use this API, you must undergo App Review and request approval for: the Instagram Public Content Access feature, the instagram_basic permission」（[Hashtag Search](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/hashtag-search)）。
- `recent_media`：「Only returns media objects published within 24 hours of query execution.」每頁最多 50 筆；「You cannot request the username field on returned media objects.」（[IG Hashtag Recent Media](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-hashtag/recent-media)）。
- 允許用途：「discover content associated with your hashtag campaigns, understand public sentiment around your brand or identify contest, competition and sweepstakes entrants」（[Features Reference](https://developers.facebook.com/documentation/development/features-reference)）。用途不合、拿不到作者名、開發工具也很少在 IG 發表。避開。

### 2.11 Meta Content Library 與 API

- 資格：「applicants must be affiliated with a qualified academic institution or a qualified non-academic research institution」，非學術機構要是「a not-for-profit institution whose primary purpose or core activity is to conduct scientific or public interest research」（[Get Access](https://developers.facebook.com/docs/content-library-and-api/get-access)）。
- 時程：CASD 審查「can take 2 to 3 weeks」，之後 Meta 處理「typically takes 2 to 3 weeks」。不收費。
- Content Library API 只能在 Secure Research Environment 或核准的第三方 cleanroom 裡用；網頁版 Content Library 在申請核准、簽約後，可下載 Facebook、Instagram 的「公開資料子集」CSV（[總覽](https://developers.facebook.com/docs/content-library-and-api)）。〔查核修正：原寫「資料只能在 cleanroom 裡分析」〕Threads 資料集只收 100 粉絲以上的公開帳號，而且還在開發中：「Threads content is not available for download while this dataset is in development」（[Content Library](https://developers.facebook.com/docs/content-library-and-api/content-library)）。
- pickfit 是產品不是研究，個人參賽也不屬於合格機構。避開。

---

## 3. App Review：一個人 6 天過得了嗎？

**過不了，也不建議送。** 送審要準備的東西：

| 項目 | 官方要求 | 來源 |
|---|---|---|
| 商家驗證 | Access Levels 寫「Business Verification is required to get Advanced Access」，但同頁開頭註明「This document is only applicable to apps created using an App Type」，Threads app 是用 use case 建的；Business Verification 頁寫「you might need to complete Business Verification」，送審指南寫「you may be prompted to complete business verification」。Threads 文件只有 webhook 寫明「The business connected to the app must be verified」。**判定：Threads 的 Advanced Access 很可能要商家驗證，但文件用語是 may／might，未驗證。**〔查核修正：原寫成確定要〕要用 Business Manager 交公司文件 | [Access Levels](https://developers.facebook.com/documentation/development/graph-api/overview/access-levels)、[Business Verification](https://developers.facebook.com/documentation/development/release/business-verification)、[Submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide)、[Webhooks](https://developers.facebook.com/documentation/threads/webhooks) |
| 先打過 API | 每個權限 30 天內至少成功呼叫一次；「The API call data will be logged within 2 days」 | [Submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide) |
| 螢幕錄影 | 每個權限都要錄影示範，缺一個就不核准 | 同上 |
| 公開可測的 app | 「If we are unable to access your app to test it, your entire submission will be rejected.」 | [App Review](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review) |
| 隱私權政策、資料刪除網址、app icon | 發布 app 必備 | [Threads use case](https://developers.facebook.com/documentation/development/create-an-app/threads-use-case) |
| 允許用途相符 | 「If your app does not satisfy the allowed usage for a permission or feature, your app will not be approved」 | [Submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide) |
| 審核時間 | 官方文件查不到明確天數（App Review、送審指南、FAQ 都查過）。2026-06 的論壇文轉述後台寫「most requests are reviewed within 10 days」，發文者等了 13 天；另一篇約 3 年前的論壇文是 Facebook Login／Instagram 權限「up to 10 days」（**未驗證**） | 論壇：[超過 10 天](https://developers.secure.facebook.com/community/threads/393000170176255)、[等了 13 天](https://developers.facebook.com/community/threads/2119529588613973/) |

光是（很可能需要的）商家驗證加上「API 呼叫最多 2 天內才記錄」就吃掉大半時間，而且搜尋類權限與 `threads_basic` 的允許用途都和 pickfit 不符。

## 4. 不審核（Development mode＋Threads tester）能做到什麼

「Apps in Development mode can only request permissions from role users… features will only be active for role users」（[App Modes](https://developers.facebook.com/documentation/development/build-and-test/app-modes)）。

| 想做的事 | 不審核時的結果 | 狀態 |
|---|---|---|
| 讀 tester 自己的貼文（`/me/threads`） | 技術上可以；用途只限顯示給作者本人（見 2.1） | 文件確認 |
| 讀 tester 貼文的文字、連結、圖片網址 | 技術上可以（`text`、`link_attachment_url`、`media_url`）；交給模型抽取不在允許用途內 | 文件確認 |
| 用 tester 帳號發文 | 可以 | 文件確認 |
| 讀 tester 貼文底下**別人**的回覆 | 文件沒寫限制 | **未驗證** |
| keyword／topic tag search | 只搜得到 tester 自己的貼文 | 文件確認 |
| 讀被 @ 的貼文（mentions） | 只回 tester 做的標記 | 文件確認 |
| 讀別人的單篇貼文 | 只限 tester 的貼文 | 文件確認 |
| profile discovery | 只有 @meta、@threads、@instagram、@facebook | 文件確認 |
| webhook | 要 Live mode＋商家驗證 | 文件確認 |
| oEmbed 嵌入任何公開貼文 | 可以，不用 token | 實測確認 |

## 5. 實測

所有實測只打不需金鑰的端點，2026-10-27 19:55 UTC 執行。

### 5.1 `spikes/ch_meta_probe.py`：哪些端點免金鑰、oEmbed 給什麼

執行：`python3 spikes/ch_meta_probe.py`（只用標準函式庫）。

| 端點（不帶 token） | 結果 |
|---|---|
| Threads oEmbed（官方範例貼文） | HTTP 200；欄位 `html, provider_name, provider_url, type, version, width`；html 3,094 bytes；可見文字只有「View on Threads」 |
| Threads oEmbed（不存在的貼文） | HTTP 400，code 24；`message` 是「The requested resource does not exist」，`error_user_title` 是「Media Not Found」（腳本只印 `message`） |
| Threads `keyword_search`、`profile_lookup`、`profile_posts`、`/me` | 都是 HTTP 400，code 190「Invalid OAuth 2.0 Access Token」：端點存在，要 token |
| Instagram `instagram_oembed` | HTTP 200；可見文字只有「View this post on Instagram」 |
| Facebook `oembed_post` | HTTP 200；html 274 bytes，沒有文字 |
| Facebook `/facebook/feed` | HTTP 403，code 200「Provide valid app ID」 |
| Facebook `pages/search` | HTTP 401，code 190 |
| Instagram `ig_hashtag_search` | HTTP 400，code 100「The parameter user_id is required.」 |
| threads.com、instagram.com、facebook.com 的 robots.txt | 開頭都聲明未經書面許可禁止自動化收集 |

### 5.2 `spikes/ch_meta_threads_hn.py`：作者多常用 Threads 當發表連結？

執行：`python3 spikes/ch_meta_threads_hn.py --days 365`。用 HN 的 Algolia 搜尋 API 找連到 Threads 或 X 的 story，只算主機名稱完全相符的；再對最近 5 筆 Threads 連結打 oEmbed。

| 主機 | 7 天 | 30 天 | 365 天 | 其中 Show HN（365 天） |
|---|---|---|---|---|
| threads.com／threads.net | 1 | 2 | 33 | 1 |
| x.com／twitter.com | 137 | 540 | ≥1,110 | ≥34 |

（X 的 365 天數字碰到 Algolia 每個查詢 1,000 筆的上限，只是下限。）

最近 5 筆 Threads 連結（含 2026-10-27 的「Show HN: UI experiment - Peek and Pop for the macOS Dock」）的 oEmbed 都回 HTTP 200、html 都是 3,094 bytes、可見文字都只有「View on Threads」、0 筆含 github.com。

**解讀**：
- 在 HN 這個英文開發者社群，把 Threads 貼文當主連結的作品發表一年只有 1 筆 Show HN，X 至少 34 筆。Threads 在英文開發者圈不是主要發表管道。這只是旁證：中文（台灣）開發者在 Threads 上分享作品的比例可能高很多，**未量化**。
- 即使拿到 Threads 連結，oEmbed 也給不出可讀的內容。要讀內容，只能靠作者登入（2.1）。
- 「最近 7 天有幾筆 Threads 貼文、幾筆連到 GitHub」這種數字，要 `threads_keyword_search` 的 Advanced Access 才量得到，現在無法實測。

### 5.3 拿到 token 後第一件要測的

1. 在 [Meta App Dashboard](https://developers.facebook.com/apps) 建 app，選 Threads use case，加上 `threads_basic`、`threads_read_replies`、`threads_content_publish`。
2. 在 App roles 把自己的 Threads 帳號加成 Threads Tester，到 Threads 的「帳號設定 → 網站權限」接受邀請。
3. 用 Graph API Explorer 或授權視窗拿 token，存在 `.env`，不要 commit。
4. 測：`GET /me/threads?fields=id,text,permalink,link_attachment_url,media_url,timestamp&since=<7 天前>`。
5. 測：用小帳號在自己的貼文底下回覆，再呼叫 `GET /{media-id}/replies?fields=id,text,username,permalink`，看非角色帳號的回覆有沒有出現。這只回答「技術上看不看得到」；徵件串能不能做，還要先過 2.4 的允許用途問題。〔查核補充〕
6. 查核補充：黑客松若不做 Threads 登入提交（見 2.1），第 4 步只是驗證用，不進產品。

---

## 6. 結論

### 黑客松期間值得接

| 項目 | 理由 | 預估工時 |
|---|---|---|
| **GitHub 連結提交，可附 Threads 貼文連結**（查核修正：取代原本的「Threads 登入提交」） | 提交者自己貼 GitHub 連結與說明，不經 Meta API，沒有允許用途問題；Muse Spark 讀 GitHub README 與截圖，一樣展示多模態；Threads 連結只用 oEmbed 嵌入。demo 第 5 幕改成「作者在 Threads 發文 → 把 GitHub 連結（與貼文連結）貼進 pickfit → 幾分鐘後出現在推薦結果，展示頁嵌入原貼文」 | 約 1 h（表單；GitHub 讀取與抽取另計） |
| **oEmbed 嵌入原貼文** | 免 token、免審核，展示頁一眼看到「這是作者在 Threads 發的」 | 0.5–1 h |
| **「分享到 Threads」按鈕**（Web Intents） | 被收錄的作者一鍵分享，供給端擴散；零審核 | 0.5 h |
| （可選）**pickfit 自家帳號發「今日寶藏」** | 允許用途相符（經營自己的 Threads 形象）；評審是 Meta，看得到產品真的在 Threads 上運作 | 2 h |

〔查核修正〕原表第一列「Threads 登入提交（threads_basic，讀貼文交給 Muse Spark）」移到「要避開」：與 `threads_basic` 允許用途「只顯示給作者本人」衝突，Platform Terms 3.a.viii 禁止，Development mode 不豁免（見 2.1）。

注意事項：
- 〔查核修正〕demo 第 5 幕不需要 Threads 登入，所以「作者」不必是 app 角色使用者。只有做「今日寶藏」發文時，要把自己的帳號加成 Threads Tester；不要找朋友當 tester（要有「代表我們測試」的約定，見 2.1；而且只能當使用者，不能參與製作，hackathon-rules 第 2 節）。
- brief 4.1 的「任何人貼 Threads 連結就收錄」做不到。改成：提交者同時貼 GitHub 連結與說明，Threads 連結只拿來嵌入。〔查核修正：刪除「作者用 Threads 登入」這個選項〕
- 不透過 API 讀 Threads 貼文內容；公開檔案以 GitHub 為準。README 寫明 Threads 只用在嵌入與分享。

### 之後擴充

- 商家驗證後送 App Review：`threads_manage_mentions`＋webhook（被 @pickfit 就自動提交）。`threads_basic`（讓所有作者都能登入提交）的允許用途與 pickfit 衝突，除非 Meta 書面確認可用，否則不送。〔查核修正〕`threads_manage_mentions` 的允許用途同樣是「help the user manage their social media presence」，把 mention 內容收進目錄是否允許，未驗證。
- 確認回覆可見性，**並確認把回覆內容收進目錄在 `threads_read_replies` 允許用途內**之後，才經營「徵件串」。〔查核修正：原只寫確認可見性〕
- Facebook／Instagram oEmbed：作者在那邊發表時也能嵌入。

### 要避開

| 項目 | 原因 |
|---|---|
| Threads 登入後由 API 讀作者貼文、交給模型（`threads_basic`）〔查核修正：新增〕 | 允許用途只限「把作者自己的貼文顯示給作者本人」；交給模型抽取並公開衍生內容違反 Platform Terms 3.a.viii |
| Threads keyword／topic tag search 做發現 | 未審核只搜自己的貼文；允許用途是管理自己的社群形象，消費者 app 嚴格禁止 |
| Threads profile discovery | 未審核只有 4 個 Meta 官方帳號；只回 ≥100 粉絲；用途是競品分析 |
| 用 oEmbed 取文字給模型讀 | html 沒有文字（實測）；條款禁止抽取與保存 |
| 爬 threads.com／facebook.com／instagram.com | robots.txt 與 Automated Data Collection Terms 禁止 |
| Facebook Groups API | 2024-04-22 已移除 |
| Facebook 粉專（PPCA） | App Review＋商家驗證（文件寫明）；長尾作者少有粉專 |
| Instagram hashtag search | App Review（商家驗證文件沒寫明，未驗證）；每 7 天 30 個 hashtag；只回 24 小時內；用途是品牌活動 |
| Meta Content Library | 只限學術或非營利研究機構；審查 4–6 週 |

---

## 7. 來源（查證日期都是 2026-10-28）

Threads API
- Overview（用途聲明、rate limit）：https://developers.facebook.com/documentation/threads/overview
- Get started（Threads tester、App Review）：https://developers.facebook.com/documentation/threads/get-started
- Keyword and Topic Tag Search（2026-01-21 更新）：https://developers.facebook.com/documentation/threads/keyword-search
- Mentions：https://developers.facebook.com/documentation/threads/threads-mentions
- Threads Profiles：https://developers.facebook.com/documentation/threads/threads-profiles
- Retrieve User Posts：https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts
- Replies and Conversations：https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/replies-and-conversations
- Posts（topic tag、連結）：https://developers.facebook.com/documentation/threads/posts
- Embed a Threads Post：https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post
- oEmbed reference：https://developers.facebook.com/documentation/threads/reference/oembed
- App Access Tokens：https://developers.facebook.com/documentation/threads/get-started/app-access-tokens
- Webhooks：https://developers.facebook.com/documentation/threads/webhooks
- Web Intents：https://developers.facebook.com/documentation/threads/threads-web-intents
- Changelog：https://developers.facebook.com/documentation/threads/changelog

權限、審核、條款
- Permissions Reference（threads_* 的允許用途）：https://developers.facebook.com/documentation/development/permissions
- Features Reference：https://developers.facebook.com/documentation/development/features-reference
- Page Public Content Access：https://developers.facebook.com/docs/features-reference/page-public-content-access
- oEmbed Read（舊）：https://developers.facebook.com/docs/features-reference/oembed-read
- Access Levels：https://developers.facebook.com/documentation/development/graph-api/overview/access-levels
- App Modes：https://developers.facebook.com/documentation/development/build-and-test/app-modes
- App Roles：https://developers.facebook.com/documentation/development/build-and-test/app-roles
- Threads use case：https://developers.facebook.com/documentation/development/create-an-app/threads-use-case
- App Review：https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review
- App Review content：https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/content
- App Review submission guide：https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide
- Business Verification：https://developers.facebook.com/documentation/development/release/business-verification
- Meta Platform Terms（2026-02-03 更新）：https://developers.facebook.com/terms/
- Automated Data Collection Terms（2024-10-07 生效）：https://www.facebook.com/legal/automated_data_collection_terms
- robots.txt：https://www.threads.com/robots.txt 、https://www.instagram.com/robots.txt 、https://www.facebook.com/robots.txt

Facebook、Instagram、Content Library
- Graph API v19 changelog：https://developers.facebook.com/docs/graph-api/changelog/version19.0
- v19 公告（Groups API 移除）：https://developers.facebook.com/blog/post/2024/01/23/introducing-facebook-graph-and-marketing-api-v19/
- 免 token oEmbed 公告（2026-06-15）：https://developers.facebook.com/blog/post/2026/06/15/tokenless-access-to-meta-oembed-apis/
- Instagram oEmbed：https://developers.facebook.com/documentation/instagram-platform/oembed
- Instagram Hashtag Search：https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/hashtag-search
- IG Hashtag Recent Media：https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-hashtag/recent-media
- Meta Content Library and API：https://developers.facebook.com/docs/content-library-and-api
- Content Library Get Access：https://developers.facebook.com/docs/content-library-and-api/get-access
- Content Library（Threads 資料集）：https://developers.facebook.com/docs/content-library-and-api/content-library

其他
- HN Algolia 搜尋 API：https://hn.algolia.com/api
- App Review 等待時間（論壇轉述，未驗證）：https://developers.secure.facebook.com/community/threads/393000170176255 、https://developers.facebook.com/community/threads/2119529588613973/

---

## 查核紀錄（2026-10-28）

查核者：反向查核 agent。時間：2026-10-28 04:15 台北（2026-10-27 20:15 UTC）。方法：用 curl 抓官方文件原始 HTML，逐句比對引文；不帶 token 實際打 API；重跑兩支 spike。只改本檔，沒動其他檔案，沒有執行 git。

### 1. 關鍵主張

| # | 主張 | 判定 | 依據（皆 2026-10-28 查證） |
|---|---|---|---|
| 1 | 未核准 `threads_keyword_search` 只搜登入者自己的貼文 | 正確 | [Keyword Search](https://developers.facebook.com/documentation/threads/keyword-search) 原句相符；頁面 Updated: Jan 21, 2026 |
| 2 | 2,200 次／24h、跨 app 共用、無結果不計、無 7 天限制、since ≥ 1688540400、`search_mode=TAG`、limit 最多 100 | 正確 | 同上。另確認：同關鍵字重查也算；預設 limit 25；`owner` 不回傳；敏感字回空陣列 |
| 3 | `threads_keyword_search`、`threads_basic` 的允許用途原文 | 正確 | [Permissions Reference](https://developers.facebook.com/documentation/development/permissions)。補：`threads_basic` 的 Allowed Usage 欄多一句「for the purpose of managing the user's presence on Threads」；所有 `threads_*` 權限都有「consumer app strictly prohibited」 |
| 4 | 非角色使用者要等 App Review 且 app 發布才能授權；Threads tester 隨時可授權 | 正確 | [Get started](https://developers.facebook.com/documentation/threads/get-started) |
| 5 | mentions、單篇貼文、profile discovery 的未審核限制；≥100 粉絲；1,000 次／24h | 正確 | [Mentions](https://developers.facebook.com/documentation/threads/threads-mentions)、[Retrieve Posts](https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts)、[Threads Profiles](https://developers.facebook.com/documentation/threads/threads-profiles) |
| 6 | Advanced Access 需要商家驗證；30 天內成功呼叫；約 2 天記錄；每個權限要螢幕錄影 | **部分修正** | 30 天、錄影正確。「2 天」原文是「logged within 2 days」，即最多 2 天內。商家驗證：Access Levels 頁註明只適用 App Type 建立的 app，其他頁用 may／might，Threads 文件只有 webhook 寫明必要 → 改成「很可能需要，未驗證」 |
| 7 | Threads oEmbed 2026-03-03 起免 token；Meta oEmbed 2026-06-15 起免 token、免 App Review；實測 HTTP 200 | 正確 | [Threads Changelog](https://developers.facebook.com/documentation/threads/changelog)「Mar 3, 2026 … without an access token」；[Meta 部落格](https://developers.facebook.com/blog/post/2026/06/15/tokenless-access-to-meta-oembed-apis/)「no token, no App Review submission」。本次重跑三個 oEmbed 都是 200 |
| 8 | oEmbed html 沒有貼文文字與外部連結；條款禁止抽取、保存；每小時 1,000 次 | 正確，**加註** | 原始 html 只有 blockquote、Threads permalink、「View on Threads」與 embed.js。條款原句相符（[Embed a Threads Post](https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post)）。加註：部落格寫免 token 版「Rate limits may differ」，1,000 次／小時對免 token 呼叫未驗證 |
| 9 | 三站 robots.txt 與 Automated Data Collection Terms | 正確 | robots.txt 本次重抓相符；ADC Terms 原句「You will not engage in Automated Data Collection without first obtaining Meta's express written permission」，Effective October 7, 2024（curl 抓不到內容，用 WebFetch 讀）。補充開發者文件 [Automated Data Collection](https://developers.facebook.com/documentation/development/terms-and-policies/automated-data-collection) |
| 10 | Platform Terms 3.a.viii 原句；2026-02-03 更新 | 正確 | [Platform Terms](https://developers.facebook.com/terms/)「Last updated February 3, 2026」 |
| 11 | Groups API v19 棄用、2024-04-22 全版本移除 | 正確 | [v19 changelog](https://developers.facebook.com/docs/graph-api/changelog/version19.0)、[v19 公告](https://developers.facebook.com/blog/post/2024/01/23/introducing-facebook-graph-and-marketing-api-v19/)。`/docs/groups-api` 實測 301 轉到 `/docs` |
| 12 | PPCA 要 App Review＋商家驗證；未審核只讀得到管理員也有 app 角色的粉專 | 正確 | [PPCA](https://developers.facebook.com/docs/features-reference/page-public-content-access)。注意：PPCA 允許用途是「Analyze and/or display posts and engagement on Pages」，不是「管理社群形象」，已改第 7 行的概括 |
| 13 | IG hashtag：App Review、商業／創作者帳號、30 個／7 天、recent_media 24h、每頁 50、不能取 username | 正確 | [Hashtag Search](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/hashtag-search)、[Recent Media](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-hashtag/recent-media)。這兩頁沒寫商家驗證 |
| 14 | Content Library 資格、CASD 2–3 週＋Meta 2–3 週、只能在 cleanroom 分析、Threads 不能下載 | **部分修正** | [Get Access](https://developers.facebook.com/docs/content-library-and-api/get-access) 相符。「只能在 cleanroom」過度：API 只能在 cleanroom，但網頁版核准後可下載 FB／IG 公開資料子集 CSV（[總覽](https://developers.facebook.com/docs/content-library-and-api)） |
| 15 | App Review 約 10 天以上 | 未驗證（維持） | 官方 App Review、送審指南、FAQ 都沒有天數。[2026-06 論壇文](https://developers.facebook.com/community/threads/2119529588613973/)轉述後台「most requests are reviewed within 10 days」 |
| 16 | 未審核時讀得到非角色使用者在自家貼文下的回覆 | 未驗證（維持） | [Replies and Conversations](https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/replies-and-conversations)、[Retrieve Replies](https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/retrieve-replies) 確實沒有 tester 限制的句子。要 Threads user token 才能測 |

### 2. 其他影響決策的事實

| 項目 | 判定 | 修正 |
|---|---|---|
| 「Threads 登入提交」是唯一合規又讀得到內容的路，黑客松接 | **與條款衝突** | `threads_basic` 允許用途只限把作者自己的貼文顯示給作者本人；交給 Muse Spark 抽取並公開衍生資料，違反 Platform Terms 3.a.viii（Platform Data 含衍生資料；Development mode 不豁免）。比賽規則第 3 節排除違反平台政策的專案。改為「避開」，以「GitHub 連結提交＋Threads 連結只嵌入」取代（第 1 節表、2.1、第 4 節、第 6 節） |
| 徵件串：`threads_read_replies` 允許用途「符合」 | **加註風險** | 讀取符合；把別人回覆收進公開目錄是否允許，文件沒寫，未驗證，風險高（2.4、第 6 節） |
| Web Intents 對 Most Viral 有幫助 | **錯誤** | Most Viral 只算 X 上 demo 貼文的互動（hackathon-rules 第 5 節），已改 2.3 |
| 第 7 行「都要商家驗證」「允許用途都是經營自己的社群形象」 | **過度概括** | 已逐一改寫 |
| 2.1 的 4800 × 曝光數（最低 10）、發文 250 篇／24h | 正確 | [Overview](https://developers.facebook.com/documentation/threads/overview) |
| 每篇只能有一個 topic tag | 正確 | [Posts](https://developers.facebook.com/documentation/threads/posts)「Only one topic tag is allowed per post」 |
| tester 限 50 人、要有「代表我們測試」的約定 | 正確 | [App Roles](https://developers.facebook.com/documentation/development/build-and-test/app-roles) |
| Webhook 條件（Live Mode、已驗證商家、App Review） | 正確 | [Webhooks](https://developers.facebook.com/documentation/threads/webhooks) |
| Web Intents 參數 `text`、`url`、`tag` | 正確 | [Web Intents](https://developers.facebook.com/documentation/threads/threads-web-intents) |
| 舊 oEmbed Read 頁還寫 Requires App Review | 正確 | [oEmbed Read](https://developers.facebook.com/docs/features-reference/oembed-read) |

### 3. spike 重跑

| 腳本 | 指令 | 結果 | 與本檔一致？ | 金鑰 |
|---|---|---|---|---|
| `spikes/ch_meta_probe.py` | `python3 spikes/ch_meta_probe.py`（約 3.5 秒） | 11 個端點狀態碼與錯誤碼全部相同；Threads oEmbed html 3,094 bytes、可見文字「View on Threads」；IG oEmbed 6,433 bytes；FB oEmbed 274 bytes；robots.txt 聲明相同 | 一致。唯一差異：不存在貼文的 `message` 是「The requested resource does not exist」，「Media Not Found」是 `error_user_title`，已在 5.1 註明 | 無 |
| `spikes/ch_meta_threads_hn.py` | `python3 spikes/ch_meta_threads_hn.py --days 365`（約 3.5 秒） | Threads 1／2／33（Show HN 1）；X 137／540／≥1,110（Show HN ≥34）；最近 5 筆 oEmbed 都是 200、3,094 bytes、「View on Threads」、0 筆含 github.com | 一致 | 無 |
| 交叉檢查（查核者另跑，未存檔） | 改用 Algolia 查詢詞 `threads`（不加 `.com`），一年內 392 筆 | 主機為 `www.threads.com` 的仍是 33 筆；`threads.net` 0 筆；Show HN 仍只有 1 筆 | 一致：原查詢詞沒有漏抓 | 無 |

### 4. 仍未驗證

- 未審核時看不看得到非角色使用者的回覆（要 token）。
- Threads 的 Advanced Access 是否一定要商家驗證；個人開發者能否通過商家驗證。
- App Review 實際天數。
- 免 token oEmbed 的實際 rate limit。
- 「把作者自己的貼文列給作者挑、只存 permalink 做嵌入」是否在 `threads_basic` 允許用途內。
