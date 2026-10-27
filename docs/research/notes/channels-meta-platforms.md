2026-10-28 · Meta 平台（Threads、Facebook、Instagram）作為「作者分享作品」的管道 · 由調研 agent 撰寫，待主控者整合

# 管道調研：Meta 自家平台

需求來源：[brief.md](../../brief.md) 第 4.1、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。所有查證日期都是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。

## 一句話結論

Meta 平台**不能當「主動發現」的來源**，但可以當**「作者本人提交」與「展示、擴散」的管道**。

- 搜尋別人的公開貼文（Threads keyword search、IG hashtag、FB 粉專）都要 App Review 加商家驗證，而且官方寫明的「允許用途」是經營自己的社群形象，不是建目錄。6 天內過不了，就算有時間，用途也對不上。
- 不審核（Development mode）時，Threads API 只讀得到 **app 角色使用者（Threads tester）自己的貼文**。這剛好夠做「作者用 Threads 登入、選自己的貼文提交」。
- oEmbed 現在不用 token，但回傳的 html **不含貼文文字**（實測），而且條款**禁止**把 oEmbed 內容拿去做顯示以外的用途。只能拿來在展示頁嵌入原貼文。
- 連結提交的含意：**別人貼來的 Threads 連結，我們沒有合規的方法自動讀內容**（不能爬、oEmbed 沒文字、讀單篇貼文要 Advanced Access）。所以 brief 4.1「貼 Threads 連結就收錄」要改成「作者用 Threads 登入」或「提交者自己附上 GitHub 連結與說明」。

---

## 1. 比較表

整合成本只算黑客松版本、一個人的人時，不含等待審核的時間。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制 | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| **Threads 作者登入提交**（`threads_basic`，讀 `/me/threads`） | 高：作者本人選的貼文，附連結、截圖，身分已驗證 | 少，靠作者主動來 | 低 | API（OAuth） | 未審核只限 app 角色使用者；公開上線要 App Review＋商家驗證；`threads_basic` 的允許用途很窄（見 2.1） | 5–7 h | **黑客松接**（demo 用自己的帳號） |
| **Threads oEmbed**（無 token） | 無：html 裡沒有貼文文字 | — | — | API（免金鑰） | 只能做前端顯示；禁止抽取、保存、分析；每小時 1,000 次 | 0.5–1 h | **黑客松接**（只用來嵌入原貼文） |
| **Threads Web Intents**（分享按鈕） | 不是資料來源，是擴散 | — | — | 網址 | 無審核 | 0.5 h | **黑客松接**（被收錄的作者一鍵分享） |
| **Threads 自家帳號發文＋讀自己貼文的回覆**（`threads_content_publish`、`threads_read_replies`） | 中：回覆者主動貼作品，但要過濾 | 視貼文觸及率，初期很少 | 中 | API（OAuth，自己帳號） | 發文 250 篇／24h；非角色使用者的回覆在未審核時看不看得到，**文件沒寫，未驗證** | 2–4 h | **可選**：第一天先用 token 實測 10 分鐘再決定 |
| Threads keyword／topic tag search（`threads_keyword_search`） | 中：可搜 "I built"、topic tag，但大多是閒聊 | 多 | 高 | API | 未審核只搜得到**自己的**貼文；審核要商家驗證；允許用途是「管理社群形象」，**消費者 app 嚴格禁止**；2,200 次／24h | 3 h＋審核 | **避開**（黑客松）；之後也不建議 |
| Threads mentions（被 @pickfit 標記；含 webhook） | 高：作者主動標記 | 少 | 低 | API／webhook | 未審核只回 Threads tester 的標記；webhook 要 Live mode＋商家驗證 | 3–4 h＋審核 | **之後擴充** |
| Threads profile discovery（`profile_lookup`、`profile_posts`） | 中 | — | 中 | API | 未審核只能查 @meta、@threads、@instagram、@facebook；只回 ≥100 粉絲的帳號；允許用途是「競品分析」 | 2 h＋審核 | **避開**：長尾作者常不到 100 粉絲 |
| 直接抓 threads.com 網頁、非官方 API | — | — | — | 爬取 | robots.txt 與 Automated Data Collection Terms 禁止，需 Meta 書面許可 | — | **避開** |
| Facebook Groups API | — | — | — | 已移除 | 2024-04-22 全版本移除 | — | **避開**（不存在） |
| Facebook 粉專（Page Public Content Access） | 低：獨立開發者很少經營粉專 | 少 | 中 | API | App Review＋商家驗證；未審核只看得到自己管理的粉專 | 3 h＋審核 | **避開** |
| Facebook／Instagram oEmbed（無 token） | 無：html 沒有文字 | — | — | API（免金鑰） | 同 Threads oEmbed，只能做前端顯示 | 0.5 h | 之後擴充（只嵌入） |
| Instagram hashtag search | 低：開發工具很少在 IG 發表 | 少 | 高 | API | 要 IG 商業／創作者帳號、App Review；每 7 天 30 個 hashtag；`recent_media` 只回 24 小時內；允許用途是品牌活動 | 4 h＋審核 | **避開** |
| Meta Content Library／API | 高（全量公開資料） | 多 | 中 | 研究用 cleanroom | 只限合格學術或非營利研究機構；審查約 4–6 週；資料不能帶出 cleanroom | — | **避開**：pickfit 不符資格 |

---

## 2. 各管道細節

### 2.1 Threads：作者用 Threads 登入、提交自己的貼文

- **做法**：作者按「用 Threads 提交」→ OAuth 取得 `threads_basic` → 呼叫 `GET /me/threads?since=…` 列出最近的貼文 → 作者選一篇 → 拿 `text`、`link_attachment_url`、`media_url`（截圖、影片）交給 Muse Spark 讀懂 → 找到 GitHub 連結後進驗證流程。
- **能不能拿到「作者自己發表、最近才出現、沒什麼人知道」的貼文**：能，這是唯一合規又拿得到內容的路。貼文就是作者本人的，可以用 `since` 限定最近幾天。作者登入也順便證明「提交者就是作者」，對 brief 第 13 節的「被刷」風險有幫助。
- **不審核時**：只有 app 角色使用者能授權。官方原文：「[Threads testers] can grant your app these permissions at any time. In order for app users without a role on your app to be able to grant your app these permissions, each permission must first be approved through the App Review process, and your app must be published.」（[Get started](https://developers.facebook.com/documentation/threads/get-started)）
- **Threads tester 不能隨便邀**：「You may only add a person as a Tester to your app if they are your employee or you have an agreement with them which establishes that they are acting on your behalf as a tester of your app.」（[App Roles](https://developers.facebook.com/documentation/development/build-and-test/app-roles)）。未連結已驗證商家的 app 最多 50 位 tester。demo 用自己的帳號最乾淨。
- **條款風險（中）**：`threads_basic` 的允許用途寫得很窄：「The allowed usage for this permission is to display a user's own Threads posts within a business app, and make these visible only to the user who created them. It is not intended for any other purpose. For example, using threads_basic permission in a consumer app is strictly prohibited.」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)）。Threads API 總覽也寫「display those posts within your app solely to the person who created it」（[Overview](https://developers.facebook.com/documentation/threads/overview)）。再加上 Platform Terms 3.a.viii 禁止「Processing Platform Data for purposes other than the applicable permitted purposes set forth in Meta's Developer Docs」（[Platform Terms](https://developers.facebook.com/terms/)）。
  - **因應**：選貼文的畫面只給作者本人看；貼文內容只在處理當下交給 Muse Spark，不長期保存、不公開顯示原文；公開的軟體檔案以 GitHub README 為主；展示頁要顯示原貼文時用 oEmbed 嵌入。黑客松期間只用自己的資料，風險低；正式上線前要確認能否通過 App Review（可能被認定為消費者 app 而拒絕）。
- **兩個 demo 類別**：開發者 CLI 工具、本地 AI／LLM 工具的作者都會在發文附 GitHub 連結與終端機截圖，`link_attachment_url` 與 `media_url` 剛好能讓 Muse Spark 的多模態發揮。兩類差別不大。
- **頻率**：每個 app 與使用者組合每 24 小時可呼叫 `4800 × 曝光數` 次，曝光數最低算 10，所以至少 48,000 次（[Overview](https://developers.facebook.com/documentation/threads/overview)）。對提交流程綽綽有餘。

### 2.2 Threads oEmbed（不用 token）

- 2026-03-03 起 Threads oEmbed 不需要 token：「You can now call Threads oEmbed API without an access token.」（[Threads Changelog](https://developers.facebook.com/documentation/threads/changelog)）。2026-06-15 起 Facebook、Instagram 的 oEmbed 也一樣（[Meta 部落格](https://developers.facebook.com/blog/post/2026/06/15/tokenless-access-to-meta-oembed-apis/)）。
- **實測**：回傳欄位只有 `html`、`provider_name`、`provider_url`、`type`、`version`、`width`。html 裡可見的文字只有「View on Threads」，**沒有貼文內文、沒有 GitHub 連結**；內容是瀏覽器載入 `embed.js` 之後才畫出來的。
- **條款**：「Using metadata and post content (or their derivations) from the endpoint for any purpose other than providing a front-end view of the post is strictly prohibited. This prohibition encompasses consuming, manipulating, extracting, or persisting the metadata and content…」（[Embed a Threads Post](https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post)）。
- **結論**：「貼 Threads 連結 → oEmbed 取文字 → Muse Spark 讀懂」這條路**技術上拿不到文字，條款上也不准**。oEmbed 只能用在展示頁嵌入原貼文。限制：每小時 1,000 次；私人、停用、年齡限制、地區限定的貼文不支援。

### 2.3 Threads Web Intents（分享按鈕）

- `https://www.threads.com/intent/post?text=…&url=…&tag=…` 會打開 Threads 的發文框，預先填好文字、連結與 topic tag（[Web Intents](https://developers.facebook.com/documentation/threads/threads-web-intents)）。不需要 app、token 或審核。
- 用途：作品被收錄、驗證通過後，展示頁給作者一個「分享到 Threads」按鈕。這是供給端的擴散迴圈，也對 Most Viral／Community Vote 有幫助。

### 2.4 Threads 自家帳號：發文與讀回覆

- **發文**：pickfit 自己的 Threads 帳號（app 管理員本人）用 `threads_content_publish` 發「今日寶藏」。允許用途「enable a business app user to create and publish content to their Threads profile」（[Permissions Reference](https://developers.facebook.com/documentation/development/permissions)），符合。上限 250 篇／24h（[Overview](https://developers.facebook.com/documentation/threads/overview)）。
- **徵件串**：發一篇「留言貼你的 CLI 或本地 AI 工具」，再用 `GET /{media-id}/replies` 讀回覆。`threads_read_replies` 的允許用途是「get replies to a thread owned by the business app user」，符合。可以搭配 2026-02-13 新增的 reply approvals，回覆要審核才公開，可擋垃圾留言（[Changelog](https://developers.facebook.com/documentation/threads/changelog)）。
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
- 資料只能在 Secure Research Environment 或核准的 cleanroom 裡分析（[總覽](https://developers.facebook.com/docs/content-library-and-api)）。Threads 資料集還在開發中：「Threads content is not available for download while this dataset is in development」（[Content Library](https://developers.facebook.com/docs/content-library-and-api/content-library)）。
- pickfit 是產品不是研究，個人參賽也不屬於合格機構。避開。

---

## 3. App Review：一個人 6 天過得了嗎？

**過不了，也不建議送。** 送審要準備的東西：

| 項目 | 官方要求 | 來源 |
|---|---|---|
| 商家驗證 | 「Advanced Access … Business Verification is required to get Advanced Access.」要用 Business Manager 交公司文件 | [Access Levels](https://developers.facebook.com/documentation/development/graph-api/overview/access-levels)、[Business Verification](https://developers.facebook.com/documentation/development/release/business-verification) |
| 先打過 API | 每個權限 30 天內至少成功呼叫一次；「The API call data will be logged within 2 days」 | [Submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide) |
| 螢幕錄影 | 每個權限都要錄影示範，缺一個就不核准 | 同上 |
| 公開可測的 app | 「If we are unable to access your app to test it, your entire submission will be rejected.」 | [App Review](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review) |
| 隱私權政策、資料刪除網址、app icon | 發布 app 必備 | [Threads use case](https://developers.facebook.com/documentation/development/create-an-app/threads-use-case) |
| 允許用途相符 | 「If your app does not satisfy the allowed usage for a permission or feature, your app will not be approved」 | [Submission guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide) |
| 審核時間 | 官方文件查不到明確天數。開發者論壇轉述後台寫「約 10 天」，也有人等超過 13 天（**未驗證**） | 論壇：[超過 10 天](https://developers.secure.facebook.com/community/threads/393000170176255)、[等了 13 天](https://developers.facebook.com/community/threads/2119529588613973/) |

光是商家驗證加上「API 呼叫要 2 天才記錄」就吃掉大半時間，而且搜尋類權限的允許用途和 pickfit 不符。

## 4. 不審核（Development mode＋Threads tester）能做到什麼

「Apps in Development mode can only request permissions from role users… features will only be active for role users」（[App Modes](https://developers.facebook.com/documentation/development/build-and-test/app-modes)）。

| 想做的事 | 不審核時的結果 | 狀態 |
|---|---|---|
| 讀 tester 自己的貼文（`/me/threads`） | 可以 | 文件確認 |
| 讀 tester 貼文的文字、連結、圖片網址 | 可以（`text`、`link_attachment_url`、`media_url`） | 文件確認 |
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
| Threads oEmbed（不存在的貼文） | HTTP 400，code 24，「Media Not Found」 |
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
5. 測：用小帳號在自己的貼文底下回覆，再呼叫 `GET /{media-id}/replies?fields=id,text,username,permalink`，看非角色帳號的回覆有沒有出現。這決定 2.4 的徵件串能不能做。

---

## 6. 結論

### 黑客松期間值得接

| 項目 | 理由 | 預估工時 |
|---|---|---|
| **Threads 登入提交**（作者本人、Development mode） | 唯一合規又拿得到貼文內容的路；作者身分已驗證；Muse Spark 讀文字加截圖，展示多模態；對上 demo 第 5 幕 | 5–7 h（建 app 與 tester 1 h、OAuth 與列貼文 3–4 h、接進抽取流程 1–2 h） |
| **oEmbed 嵌入原貼文** | 免 token、免審核，展示頁一眼看到「這是作者在 Threads 發的」 | 0.5–1 h |
| **「分享到 Threads」按鈕**（Web Intents） | 被收錄的作者一鍵分享，供給端擴散；零審核 | 0.5 h |
| （可選）**pickfit 自家帳號發「今日寶藏」** | 允許用途相符；評審是 Meta，看得到產品真的在 Threads 上運作 | 2 h |

注意事項：
- demo 第 5 幕的「作者」要是 app 角色使用者。用自己的帳號最乾淨；找朋友當 tester 要有「代表我們測試」的約定（見 2.1），而且只能當使用者，不能參與製作（hackathon-rules 第 2 節）。
- brief 4.1 的「任何人貼 Threads 連結就收錄」做不到。改成：作者用 Threads 登入；或提交者同時貼 GitHub 連結與說明，Threads 連結只拿來嵌入。
- 貼文原文不要長期保存或公開顯示；公開檔案以 GitHub 為準。README 寫明 Threads 資料怎麼用。

### 之後擴充

- 商家驗證後送 App Review：`threads_basic`（讓所有作者都能登入提交）、`threads_manage_mentions`＋webhook（被 @pickfit 就自動提交）。送審前要先確認允許用途說得通。
- 確認回覆可見性後，經營「徵件串」。
- Facebook／Instagram oEmbed：作者在那邊發表時也能嵌入。

### 要避開

| 項目 | 原因 |
|---|---|
| Threads keyword／topic tag search 做發現 | 未審核只搜自己的貼文；允許用途是管理自己的社群形象，消費者 app 嚴格禁止 |
| Threads profile discovery | 未審核只有 4 個 Meta 官方帳號；只回 ≥100 粉絲；用途是競品分析 |
| 用 oEmbed 取文字給模型讀 | html 沒有文字（實測）；條款禁止抽取與保存 |
| 爬 threads.com／facebook.com／instagram.com | robots.txt 與 Automated Data Collection Terms 禁止 |
| Facebook Groups API | 2024-04-22 已移除 |
| Facebook 粉專（PPCA） | App Review＋商家驗證；長尾作者少有粉專 |
| Instagram hashtag search | App Review；每 7 天 30 個 hashtag；只回 24 小時內；用途是品牌活動 |
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
