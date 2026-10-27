2026-10-28 · 各地區開發者社群（中文、台灣、日本、韓國、俄語）作為發現管道 · 由調研 agent 撰寫，待主控者整合

# 管道調研：各地區開發者社群

需求來源：[brief.md](../../brief.md) 第 4、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期都是 2026-10-28（台北），也就是 2026-10-27 UTC 19:40–20:30。實測腳本在 `spikes/ch_regional_*.py`。

## 一句話結論

- 有「作者發表作品」專區、又有免金鑰官方入口的只有三個：**V2EX「分享创造」**（Atom 全文）、**Qiita `個人開発` tag**（API v2）、**GeekNews「Show GN」**（RSS，但沒有原始連結）。
- **阮一峰《科技爱好者周刊》的「工具」小節**是每週人工精選，近 3 期 45 個工具有 40 個是 GitHub repo、33 個是作者自己投稿，CLI 比例高。
- **黑客松接 3 個**：V2EX、Qiita、阮一峰周刊，含共用 adapter 合計約 3.5–5 人時。GeekNews 可選（再加 2 人時）。
- **避開**：掘金（用戶協議明文禁止機器人、蜘蛛）、Dcard（沒有公開 API，Cloudflare 403）、PTT（沒有 API、feed 幾乎都 522、內容訊號禁止 AI 訓練）、velog（全站 RSS 被垃圾灌滿）、iThome 鐵人賽（2026 賽季已結束）。
- **共同限制**：中、日、韓社群的條款都把著作權留給作者。只能拿「連結、標題、日期」當線索；軟體的事實一律回 GitHub README 與沙盒驗證取得；展示頁只放回連，不轉貼原文。

---

## 1. 比較表

整合成本只算黑客松版本、一個人的人時，不含等待。新作品數量是 2026-10-27 實測（見第 3 節）。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制 | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| **V2EX「分享创造」**（node `create`） | **高**：節點說明寫「欢迎你在这里发布自己的最新作品」，幾乎都是作者本人發文；feed 有全文 | 約 270 篇／週（50 篇涵蓋 31 小時外推）；40% 連 GitHub repo | 中：AI 影片站、小遊戲、小程式不少 | RSS（Atom，免金鑰）；API v1（只回 10 篇）；API 2.0（要 token） | API 公平使用規則「反对将 API 输出的结果用于填充你的商业或是个人网站的内容」；v1 文件寫 120 次／小時，回應標頭是 600；沒有正式 ToS 全文 | 1–1.5 h | **黑客松接** |
| **Qiita `tag:個人開発`** | **中高**：作者寫的開發記錄；likes 中位數 1（真的沒人知道）；但很多是 App、網頁、連載 | 約 200 篇／週；29% 連 GitHub repo | 中 | API v2（免金鑰 60 次／小時／IP；token 1,000 次／小時，免審核） | 利用規約第 8 條：著作權法第 21–28 條的權利留給作者；授權只給 Qiita；不可轉貼 | 1–1.5 h | **黑客松接** |
| **阮一峰周刊「工具」**（ruanyf/weekly） | **高**：人工精選；近 3 期 45 個工具中 40 個連 GitHub、33 個是作者投稿；抽樣 57–1,926★ | 12–18 個／週（每週五一期） | 低 | GitHub raw 檔（git，免金鑰）；作者投稿走 GitHub issues | 部落格版標 CC BY-NC-ND 3.0；repo 沒有 LICENSE 檔；只取連結，不抄描述 | 0.5–1 h | **黑客松接** |
| **GeekNews「Show GN」**（news.hada.io） | **高**：規則要求「直接做的、別人能實際試用的」，同專案限期內不能重貼 | 約 70 篇／週；Show 頁 20 篇中 6 篇是 github.com | 低–中：SaaS、App、網頁也多 | RSS（`/rss/news` 全站，要篩標題）；沒有 Show 專用 RSS、沒有公開 API | RSS 不含原始連結，要另讀 topic 頁；條款只禁止「造成過大負荷的自動化存取、爬取」；robots `Content-Signal: ai-train=no, search=yes, ai-input=yes`；韓文 | 2 h | **可選**（黑客松第二優先） |
| **Zenn topic feed**（`cli`、`個人開発`、`ollama`、`localllm`） | 中：`cli` 主題有作者自製 CLI（1–2★）；`ollama`、`localllm` 多是教學與實測，可當「使用者提及」 | `個人開発` 估約 370 篇／週；`cli` 約 33 篇／週 | 中 | RSS（每個 topic 只回 20 篇）；沒有官方公開 API | 利用規約第 6 條第 3 項禁止無斷轉載、二次配布；feed 只有摘要，取 GitHub 連結要讀文章頁 | 1.5–2 h | 之後擴充 |
| **Hatena Bookmark `site/github.com`** | 中：日本使用者新收藏的 GitHub 頁面；18/30 筆 ≤3 users，但混有千星專案 | 30 筆涵蓋 4.5 天（估 45 個 repo／週） | 中：含 blob 頁、大專案、疑似灌星專案 | RSS（只回最新 30 筆，`page`、`of` 都無效） | Developer Center 規約禁止把取得的資訊提供給第三方、禁止宣傳或商用目的；不是作者發表 | 0.5–1 h | 之後擴充（只當線索） |
| **HelloGitHub 月刊** | 中：39 個專案 100% 是 GitHub，但混有 2 萬星老專案 | 約 39 個／月（每月 28 日）；最新一期在 7 天窗外 | 低 | GitHub raw 檔；`hellogithub.com/rss` 只到期數 | CC BY-NC-ND 4.0（非商業、禁止演繹） | 0.5 h | 之後擴充 |
| **Gitee** | 低–中：中國開源多在這，但沒有「新作品」專區 | 未量（搜尋回 0 筆） | — | API v5 | 未帶 token 時搜尋回 0 筆（實測）；排序不能依建立時間；60 次／小時；repo 不在 GitHub，沙盒從海外下載可能慢（未驗證） | 2–3 h | 之後擴充 |
| **OSChina** | 低：以資訊為主，有「XX 发布」的軟體更新稿 | 50 篇／5 天，21 篇是「发布」稿 | 高 | RSS（`/news/rss`，連線常被 reset） | 條款沒找到（未驗證）；robots 允許 | 1 h | 避開（黑客松） |
| **掘金**（juejin.cn） | — | 多（未量） | — | 沒有官方公開 API | 用戶協議 10.1 禁止「通过任何机器人、蜘蛛等程序或设备监视、复制……」；2.6 禁止垂直搜索、鏡像 | — | **避開** |
| **PTT**（Soft_Job 等） | 低：沒有作品專區；`[分享]` 很少；Soft_Job 是職涯版 | Linux 版 20 篇跨 8 個月 | 高 | 沒有官方 API；網頁版 Atom（非正式，多數請求 522） | robots `Content-Signal: search=yes,ai-train=no,use=reference`，並擋 `meta-externalagent`、`Claude-User` 等；網頁版使用者條款找不到（未驗證） | 1–2 h | **避開** |
| **Dcard** | 低 | 未量 | — | 沒有公開 API；內部 API 與條款頁都回 Cloudflare 403 | 條款讀不到（未驗證） | — | **避開** |
| **iThome 鐵人賽** | 低：教學系列為主；有「SideProject30」組 | 一年一次，2026 已結束 | 中 | iT 邦幫忙 RSS（20 篇，0 篇連 GitHub） | 條款頁 404（未驗證） | 1 h | 避開（黑客松） |
| **velog** | 低 | — | **極高**：全站 RSS 兩次抽樣 20/20、7/20 是中文色情廣告 | RSS（全站、每位作者）；GraphQL 非官方 | 條款：著作權歸會員 | — | **避開** |
| **Habr** | 低–中：`open_source` hub 有作者文 | 40 篇／55 小時；7/40 摘要含 GitHub | 中 | RSS（hub） | 使用者協議禁止商業目的使用內容，只允許個人非商業使用；俄文 | 1 h | 避開 |

---

## 2. 各管道細節

### 2.1 V2EX「分享创造」（中國、全球華語）

- **作者專區**：節點 API 回傳 `header`：「欢迎你在这里发布自己的最新作品！」，累計 38,235 篇。實測 50 篇中 40% 附 GitHub repo，多數 0 回覆。抽樣的 `fulln/health-native` 發文當天建立、0★。
- **取得**：`https://www.v2ex.com/feed/create.xml`（Atom，免金鑰）回最新 50 篇、**含全文 HTML**，涵蓋約 31 小時，每 6 小時輪詢一次就不漏。API v1 `/api/topics/show.json?node_name=create` 只回 10 篇、不能翻頁。API 2.0 `/api/v2/nodes/create/topics?p=N` 可以翻頁，但要 Personal Access Token（實測未帶 token 回 401 `Token not found`）。
- **條款**：V2EX 沒有一般 ToS，只有 [API 公平使用規則](https://www.v2ex.com/p/7v9TEc53)：「我们鼓励将 V2EX API 用于学术研究、手机应用及浏览器扩展」「我们反对将 API 输出的结果用于填充你的商业或是个人网站的内容……只是不希望 V2EX 的数据被用在垃圾站和 content farm」。社區規則也寫「这里绝对不会全文转载任何文章，而只会以链接方式分享」。
- **含意**：拿來當發現線索可以；**展示頁不能放 V2EX 原文**，只放 repo 自己的描述與回連。
- **Rate limit**：v1 文件寫每 IP 每小時 120 次；實測回應標頭 `X-Rate-Limit-Limit: 600`。API 2.0 文件寫 600 次。feed 走 CDN，影響不大。
- **兩個 demo 類別**：CLI 關鍵字 5/50（例如 `heydeer/pngdeer`，Rust PNG 壓縮 CLI，10-25 建立，255★）；本地 AI 3/50。CLI 類好用，本地 AI 類量少。
- **要 token 時**：到 `https://www.v2ex.com/settings/tokens` 自己產生，免審核，效期 30–180 天。黑客松用 Atom 就夠，不需要。

### 2.2 Qiita `個人開発` tag（日本）

- **作者專區**：沒有專區，但 `個人開発` 是約定俗成的 tag。實測 2026-10-20 起 236 篇；7 天內 198 篇，29% 連 GitHub repo，likes 中位數 1。抽樣 repo 都是 0★（`Morishita-mm/Yushario`、`cuculhart/sagbal`、`HidekiMorisaki/sph`）。
- **取得**：`GET https://qiita.com/api/v2/items?query=tag:個人開発 created:>=YYYY-MM-DD&per_page=100&page=N`，回應標頭 `total-count` 直接給總數，body 有 Markdown 全文。
- **Rate limit**：官方文件「60 is on non-authenticated request per its IP address」，帶 token 1,000 次；`per_page` 最大 100，`page` 最大 100。token 在 `https://qiita.com/settings/applications` 自己產生，免審核。
- **條款**：[利用規約](https://qiita.com/terms) 第 8 條「著作権法第21条から第28条までにおいて定義される権利については、ユーザー又は第三者に留保されます」；第 7 條的授權對象是 Qiita 與其他登錄使用者，而且只限「コード、スニペットなどプログラムに類するもの」。規約沒有提到 API 或爬取。結論：可讀、可抽連結，不可轉貼全文。
- **兩個 demo 類別**：同期間 `tag:CLI` 13 篇、`tag:ローカルLLM` 21 篇、`tag:Ollama` 14 篇。本地 LLM 類多是教學與實測（例如「LM Studio MTP 投機的デコーディング」），比較適合當「真實使用者提及」的品質訊號（brief 4.3），不是新作品來源。

### 2.3 阮一峰《科技爱好者周刊》「工具」小節（中國）

- **作者專區**：每期固定有「工具」小節。第 414–416 期共 45 個工具，40 個是 GitHub repo，**33 個標「投稿」**（作者在 [GitHub issues](https://github.com/ruanyf/weekly/issues) 自薦，由阮一峰挑選）。
- **新與冷**：抽樣 7 個 repo 是 57–1,926★，多數 2026 年建立（`CLoaKY233/siltop` 10-16 建立 80★；`lyuangg/tui-dashboard` 57★）。比 V2EX、Qiita 有名一點，但多半不在模型訓練資料裡。
- **取得**：`https://raw.githubusercontent.com/ruanyf/weekly/master/docs/issue-N.md`，Markdown 格式固定：`N、[名稱](連結)` 加一段描述。週五出刊。部落格也有 Atom（`/blog/atom.xml`），但只回 3 期。
- **條款／授權**：repo 沒有 LICENSE 檔（實測 404）；部落格每篇文末寫「版权声明：自由转载-非商用-非衍生-保持署名（创意共享3.0许可证）」。**只取 repo 連結這個事實，不抄描述**，就不涉及演繹。
- **兩個 demo 類別**：CLI 好用（第 416 期 12 個工具有 5 個是命令列：`glincker/sslx`、`CLoaKY233/siltop`、`wx4766/html-to-video` 等）。本地 AI 少（3 期只有 `leemysw/yovoice`，本地 TTS，1,926★）。
- **未做**：issues API 在本環境被代理擋住，沒量到每週投稿 issue 數（未驗證）。

### 2.4 GeekNews「Show GN」（韓國）

- **作者專區**：[使用指南](https://news.hada.io/guidelines)：「본인 또는 소속 조직이 만든 서비스, 제품, 앱, 오픈소스, 도구를 소개할 때는 뉴스가 아니라 Show로 등록해야 합니다」「직접 사용해 볼 수 있는 작업물만 등록해 주세요」「같은 프로젝트는 일정 기간 내에 다시 등록할 수 없습니다」。品質門檻比 V2EX 高。
- **量**：RSS 50 篇涵蓋 23 小時，其中 Show GN 10 篇，外推約 70 篇／週。Show 頁第 1 頁 20 篇（1–2 天內）有 6 篇連 github.com、2 篇 github.io。
- **取得的問題**：只有全站 `https://news.hada.io/rss/news`，沒有 Show 專用 RSS；Atom 的 `link` 指向 GeekNews 自己的 topic 頁，`content` 是截斷的介紹文，**不含原始連結**（實測 10 篇只抽到 1 個 repo）。要拿 repo 連結得每篇再讀一次 topic 頁 HTML。
- **條款**：[이용약관](https://news.hada.io/terms) 第 6 條只禁止「서비스에 과도한 부하를 주는 자동화 접근, 크롤링, 스크립트 실행 행위」；robots 允許 `/topic`、`/show`，只擋 `/api/`；robots 開頭宣告 `Content-Signal: ai-train=no, search=yes, ai-input=yes`，餵給模型做抽取符合宣告，不能拿來訓練。
- **兩個 demo 類別**：本週樣本以 SaaS、App 為主，CLI 1/10，本地 AI 0/10。韓文，需要模型讀韓文（Muse Spark 的韓文能力未驗證）。

### 2.5 Zenn topic feed（日本）

- **作者專區**：沒有。`cli` 主題本週有兩個作者自製 CLI：`takakix2/berthd`（Rust PTY 常駐程式，tmux 替代，有預編譯檔，2★）、`yutayamate/kcx`（macOS Keychain 注入密鑰的 CLI，1★）。這兩個正是 brief 要的「品質不錯、沒人知道」。
- **取得**：官方說明三種 feed（[ZennをRSSフィードで購読する](https://zenn.dev/zenn/articles/zenn-feed-rss)）：趨勢、使用者、topic。「デフォルトではフィードに出力される投稿（記事・本）の数は20ほどに制限」，`?all=1` 只對使用者 feed 有效（實測 topic feed 加了仍是 20 篇）。`個人開発` 20 篇只涵蓋 9 小時，要每小時輪詢。
- **限制**：feed 只有摘要，GitHub 連結要讀文章頁。沒有官方公開 API（`zenn.dev/api/...` 是網站內部用，沒有文件，不建議用）。
- **條款**：[利用規約](https://zenn.dev/terms)（2025-06-05 改定）第 6 條第 3 項「利用者または第三者は、利用者コンテンツについて、権利者の許可を得ることなく、無断で転載または二次配布等を行うことはできません」；第 4 條禁止妨害伺服器。robots 只擋 `/search`。
- **為什麼不在黑客松接**：要「feed 輪詢＋讀文章頁」兩段，量又跟 Qiita 重疊。之後擴充時優先接 `cli` topic。

### 2.6 Hatena Bookmark（日本）

- **不是作者專區**，是日本使用者的收藏。`https://b.hatena.ne.jp/site/github.com/?mode=rss&sort=new` 回最新 30 筆 GitHub 頁面（頁面 `<link rel=alternate>` 也有官方 RSS 連結）。實測 `page`、`of` 參數都被忽略，**只能拿到最新 30 筆**（約 4.5 天），要定期輪詢累積。
- **品質**：30 筆中 18 筆 ≤3 users。抽樣有 0–2★ 的新作（`azu/chizu`），也有本地 AI 工具 `KrushnaVardhanReddy/PaperPilot`（649★）。還有 `impacifist/Windows-GPU-UNLOCK`：一週前建立，剛好 1,000★、100 forks，**疑似灌星**，正好說明 brief 13 節「品質判斷會被灌水」。
- **條款**：[Hatena Developer Center 規約](https://developer.hatena.ne.jp/license/) 第 4 條禁止開發「宣伝や商用を目的とした内容」，禁止「本サービスを利用して得られる本サイト上の情報を、第三者に開示・提供する行為」。[はてな利用規約](https://policies.hatena.ne.jp/rule) 第 8 條把「APIやRSSフィードとしての公開、配信」列為官方的發布方式；robots 對一般 UA 設 `Crawl-delay: 5`。
- **含意**：只能把 GitHub URL 當內部線索，**不能在 MCP 回應或展示頁顯示收藏數、留言**。之後擴充。

### 2.7 HelloGitHub 月刊（中國）

- 每月 28 日一期（第 126 期 2026-09-28；第 127 期預計 10-28，也就是今天）。第 126 期 39 個專案全部是 GitHub repo，14 個標「来自 @xxx 的分享」（含自薦）。
- 但混有老牌專案：`rakyll/hey` 20,739★（2016）、`Canop/broot` 13,105★（2018）。「沒人知道」的訊號弱。
- 授權：README 與每期文末「本作品采用 署名-非商业性使用-禁止演绎 4.0 国际 进行许可」。只取 repo URL。
- 格式：`content/HelloGitHubN.md`，按語言分小節，另有「人工智能」小節（第 126 期 5 個）。連結包在 `hellogithub.com/periodical/statistics/click?target=` 裡，要解開。
- 之後擴充：一次性灌入當「已被策展」的弱品質訊號，比當新作品來源合適。

### 2.8 Gitee、OSChina（中國）

- **Gitee**：[OpenAPI v5](https://gitee.com/api/v5/swagger) 的 `search/repositories` 文件寫 `access_token` 非必填，但實測未帶 token 回 `total_count: 0`。`sort` 只有 `last_push_at`、`stars_count` 等，不能依建立時間找新 repo。未登入 `X-RateLimit-Limit: 60`。[用户协议](https://gitee.com/terms) 沒有爬取條款，只說「上传的内容的版权均归上传者所有」。沒有作者發表專區；repo 不在 GitHub，沙盒從海外拉可能慢（未驗證）。之後擴充。
- **OSChina**：`/news/rss` 50 篇涵蓋 5 天，21 篇是「XX vN 发布」軟體更新稿（多是國內企業軟體、作者自投），摘要裡 0 個 GitHub、2 個 Gitee 連結。連線常被 reset（本次 3 次有 2 次失敗）。用戶協議沒找到（未驗證）。黑客松避開。

### 2.9 掘金（中國）

- 沒有官方公開 API（`/rss` 回的是前端殼頁）。
- [用户服务协议](https://lf3-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/juejin/86857833-55f6-4d9e-9897-45cfe9a42be4.html)（2025-12-24 生效）10.1：「未经公司许可，任何人不得擅自使用（包括但不限于通过任何机器人、蜘蛛等程序或设备监视、复制、传播、展示、镜像、上载、下载）"稀土掘金"及相关服务中的内容」；2.6 禁止「垂直搜索、镜像」。
- 結論：條款明文禁止，**避開**。作者若想被收錄，走我們的提交入口。

### 2.10 PTT（台灣）

- 沒有官方 API。網頁版有 Atom（`https://www.ptt.cc/atom/<board>.xml`），沒有正式文件。今天約 20 次請求只有 1 次成功（Linux 版），其餘都是 Cloudflare 522。
- 成功那次：Linux 版最新 20 篇跨 8 個月，`[分享]` 自製工具只有 1–2 篇。Soft_Job 是求職與職涯討論，不是作品發表。
- [robots.txt](https://www.ptt.cc/robots.txt) 開頭：「As a condition of accessing this website, you agree to abide by the following content signals」，`User-agent: *` 設 `Content-Signal: search=yes,ai-train=no,use=reference`，並整站擋 `meta-externalagent`、`meta-externalfetcher`、`Claude-User`、`ChatGPT-User` 等 AI 代理。
- 使用者條款網頁版沒找到（未驗證）。量少、不穩、條款不明：**避開**。

### 2.11 Dcard（台灣）

- 沒有公開 API。網路上流傳的 `/service/api/v2/...` 是網站內部 API，實測回 Cloudflare「Attention Required」403。條款頁（`/service/terms` 等三個網址）也都 403，條款內容未驗證。
- 學生、年輕上班族為主，不是開發者作品發表的地方。**避開**。

### 2.12 iThome 鐵人賽（台灣）

- 2026 鐵人賽首頁寫「2026 年 iThome 鐵人賽告一段落」；有「佛心分享-SideProject30」組，但內容是 30 天教學系列，不是作品發表。
- iT 邦幫忙 RSS（`/rss/articles`）20 篇涵蓋約 17 小時，摘要 0 個 GitHub 連結。robots 全開；條款頁 404（未驗證）。黑客松避開。

### 2.13 velog（韓國）

- 全站 RSS `https://v2.velog.io/rss` 只回 20 篇。兩次抽樣：一次 20 篇全是中文色情廣告、涵蓋 1 分鐘；一次 20 篇中 7 篇。只有每位作者的 RSS 可用，GraphQL（`v2.velog.io/graphql`）沒有官方文件，`recentPosts` 實測回空陣列。
- 條款：「게시물 등……에 대한 저작권을 포함한 일체에 관한 권리는……각 회원에게 귀속됩니다」。**避開**。

### 2.14 Habr（俄語）

- `open_source` hub RSS 40 篇涵蓋 55 小時，7 篇摘要含 GitHub。俄文；作者文有，但沒有專區。
- [使用者協議](https://account.habr.com/info/agreement/)：「Пользователь не вправе воспроизводить, повторять и копировать, продавать, а также использовать для каких-либо коммерческих целей какие-либо части Приложений (включая Контент……)」，只允許「личное некоммерческое использование」。**避開**。

---

## 3. 實測

### 3.1 腳本

| 腳本 | 打哪裡 | 怎麼跑 |
|---|---|---|
| `spikes/ch_regional_authors.py` | V2EX Atom＋API v1、GeekNews RSS、Qiita API v2、Zenn topic feed、PTT Atom | `python3 spikes/ch_regional_authors.py`（可加 `--only v2ex,qiita --samples 5`） |
| `spikes/ch_regional_curated.py` | Hatena site RSS、阮一峰周刊 raw md、HelloGitHub raw md、velog／Habr／OSChina RSS | `python3 spikes/ch_regional_curated.py`（可加 `--only hatena,ruanyf --ruanyf-issues 1`） |

- 只用 Python 標準函式庫，不需要任何金鑰。全部跑完約 1 分鐘，Qiita 用掉 6–7 次（未登入額度 60 次／小時）。
- 「連 GitHub」＝內文或連結裡有 `github.com/<owner>/<repo>`（排除 `hellogithub.com`）。CLI、本地 AI 用關鍵字粗分，只當參考。
- 視窗不足 7 天的管道，用「抓到的篇數 ÷ 涵蓋小時 × 168」外推，表中標「估」。
- 星數另用 GitHub MCP 的 `search_repositories` 查（腳本本身不打 GitHub API，因為本環境的代理擋住匿名 `api.github.com`）。

### 3.2 結果（2026-10-27 20:13–20:19 UTC 執行）

| 管道 | 抓到 | 涵蓋 | 7 天內 | 連 GitHub repo | CLI 關鍵字 | 本地 AI 關鍵字 | 7 天量 |
|---|---|---|---|---|---|---|---|
| V2EX 分享创造（Atom） | 50 | 31 h | 50 | 20（40%） | 5 | 3 | 估 268 |
| GeekNews Show GN（RSS） | 10 | 17.5 h | 10 | 1（10%，RSS 沒原始連結） | 1 | 0 | 估 73 |
| Qiita tag:個人開発（API） | 236 | 7.9 天 | 198 | 58（29%） | 33 | 5 | 198（實數） |
| Zenn topic:個人開発 | 20 | 9 h | 20 | 0（只有摘要） | 0 | 0 | 估 374 |
| Zenn topic:cli | 20 | 4.3 天 | 20 | 4（20%） | 7 | 0 | 估 33 |
| Zenn topic:ollama | 20 | 5.6 天 | 20 | 0 | 0 | 16 | 估 25 |
| Zenn topic:localllm | 20 | 8.4 天 | 17 | 0 | 0 | 10 | 17 |
| Hatena site:github.com | 30 | 4.5 天 | 30 | 29 個不重複 repo | 3 | 1 | 估 45 repo |
| 阮一峰周刊 416／415／414 期「工具」 | 12／15／18 | 每週一期 | 1 期 | 11／13／16 | 5／1／2 | 0／0／1 | 12–18 |
| HelloGitHub 第 126 期 | 39 | 每月一期 | 0 期（9-28 出刊） | 39（100%） | 6 | 0 | — |
| PTT Soft_Job／Linux／Python／Programming | — | — | — | — | — | — | 全部 522 |
| velog 全站 RSS | 20 | 3.5 h | — | — | — | — | 垃圾 7/20（前一次 20/20） |
| Habr open_source hub | 40 | 55 h | 40 | 7（18%） | — | — | — |
| OSChina 资讯 RSS | 50 | 5 天 | 50 | 0（Gitee 2） | — | — | 「发布」稿 21 篇；第二次連線被 reset |

### 3.3 抽樣品質（星數於 2026-10-27 UTC 用 GitHub 搜尋查）

| 來源 | repo | ★ | 建立 | 類別 | 看法 |
|---|---|---|---|---|---|
| V2EX | `heydeer/pngdeer` | 255 | 2026-10-25 | CLI（Rust PNG 壓縮，有 CLI 與網頁） | 好候選：CLI、新、可在沙盒驗 |
| V2EX | `fulln/health-native` | 0 | 2026-10-27 | Mac 本地工具 | 太新，需要 Apple 健康資料，難驗證 |
| V2EX | `mantou132/gem` | 54 | 2019 | 前端框架 | 老專案的新版本貼文 |
| V2EX | `murray17/rovai-ai` | 220 | 2026-07 | 桌面 coding agent 工作台 | GUI，難驗證 |
| Qiita | `Morishita-mm/Yushario` | 0 | 2026-10-09 | 給 coding agent 的本地 RPG 介面 | 有趣，但非兩個 demo 類別 |
| Qiita | `cuculhart/sagbal`、`HidekiMorisaki/sph` | 0、0 | 2026-10、2026-09 | 遊戲、社內入口網站 | 雜訊 |
| Zenn cli | `takakix2/berthd` | 2 | 2026-09-11 | CLI（PTY 常駐、tmux 替代，有預編譯檔） | **很好的寶藏候選** |
| Zenn cli | `yutayamate/kcx` | 1 | 2026-10-22 | macOS CLI（Keychain 密鑰注入） | 好候選，但只限 macOS |
| Zenn oss | `tribgames/mixdog` | 205 | 2026-06 | 桌面 coding agent | GUI |
| GeekNews | `ultramancode/spring-ai-privacy-guardrails` | 22 | 2026-08 | Java 函式庫 | 不是終端使用者軟體 |
| Hatena | `azu/chizu` | 2 | 2026-10-27 | macOS 預設瀏覽器分派器 | 新，GUI |
| Hatena | `KrushnaVardhanReddy/PaperPilot` | 649 | 2026-09-28 | 本地 AI 文件助理 | 本地 AI 類候選 |
| Hatena | `impacifist/Windows-GPU-UNLOCK` | 1,000 | 2026-10-20 | GPU 解鎖 | **疑似灌星**（一週剛好 1,000★、100 forks） |
| 阮一峰 416 | `glincker/sslx` | 127 | 2026-04 | CLI（OpenSSL 替代） | 好候選 |
| 阮一峰 416 | `CLoaKY233/siltop` | 80 | 2026-10-16 | TUI（Apple Silicon 監控） | 好候選，只限 macOS |
| 阮一峰 416 | `wx4766/html-to-video` | 146 | 2026-10-11 | CLI（HTML 動畫轉 MP4） | 好候選，可在 Linux 沙盒驗 |
| 阮一峰 414 | `leemysw/yovoice` | 1,926 | 2026-09-15 | 本地 AI TTS 桌面 App | 本地 AI 類，GUI |
| HelloGitHub | `rakyll/hey`、`Canop/broot` | 20,739、13,105 | 2016、2018 | CLI | 已經很有名，不是寶藏 |

**讀法**：作者發表區（V2EX、Qiita、Zenn）抽到的是 0–255★ 的新作，真的「沒人知道」，但雜訊也多，要 Meta 模型先判斷「是不是可用的軟體」。人工精選（阮一峰）落在 57–1,926★，品質穩、CLI 多。HelloGitHub 混有萬星老專案，不適合當「新作品」來源。

---

## 4. 結論

### 4.1 黑客松期間值得接的

先寫一個共用的 adapter 介面（約 1 h）：每個來源輸出 `{source, post_url, title, published_at, text, repo_urls}`，只存這幾欄；後續一律回 GitHub 讀 README，交給 Muse Spark 判斷與抽取。

| 管道 | 理由 | 預估工時 |
|---|---|---|
| **V2EX「分享创造」Atom** | 唯一明確寫「發布自己的最新作品」的中文專區；免金鑰、有全文；40% 附 repo；每週約 270 篇 | 1–1.5 h（含 6 小時輪詢） |
| **Qiita API v2 `tag:個人開発`** | 官方 API、免金鑰就夠用；每週約 200 篇；likes 中位數 1，最符合「默默無聞」；可順便查 `tag:CLI`、`tag:ローカルLLM` 當使用者提及 | 1–1.5 h |
| **阮一峰周刊「工具」** | 每週 12–18 個人工精選、九成是 GitHub、一半以上作者投稿、CLI 多；raw md 格式固定，解析最簡單 | 0.5–1 h |
| （可選）**GeekNews Show GN** | 品質門檻最高（自製、可試用、不得重貼）；但要每篇多讀一次 topic 頁才拿得到原始連結，且是韓文 | 2 h |

合計 3.5–5 h（不含 GeekNews）。這三個來源都附原文連結，正好讓 demo 呈現「Meta 模型讀中文、日文的作者貼文，找出可用的軟體」，比只接 GitHub 更貼近「Build for Your World」。多語能力要先用 Muse Spark 實測（未驗證）。

### 4.2 之後擴充

| 管道 | 什麼時候值得接 |
|---|---|
| Zenn `cli`、`個人開発` topic feed | 有排程器可每小時輪詢、再讀文章頁時；`cli` topic 的作品品質很好 |
| Hatena `site/github.com` | 只把 URL 當內部線索；不得顯示收藏數或留言（Developer Center 規約）；也可當「日本使用者有在收藏」的品質訊號，但要先確認條款允許 |
| HelloGitHub 月刊 | 一次性匯入當「已被策展」的弱訊號；CC BY-NC-ND，只取 URL |
| Gitee | 要支援 Gitee 託管的軟體時；先申請 token 並確認沙盒下載速度 |
| V2EX API 2.0 | 需要回補 7 天以上歷史時；Personal Access Token 免審核 |

### 4.3 要避開的

| 管道 | 原因 |
|---|---|
| 掘金 | 用戶協議 10.1 明文禁止用機器人、蜘蛛取用內容；沒有公開 API |
| Dcard | 沒有公開 API；內部 API 與條款頁都被 Cloudflare 擋（403）；不是開發者作品社群 |
| PTT | 沒有 API；Atom 非正式且幾乎都 522；robots 的內容訊號 `ai-train=no`、整站擋 Meta 的 AI 代理；沒有作品專區 |
| velog | 全站 RSS 被垃圾廣告灌滿；只有每位作者的 RSS |
| iThome 鐵人賽 | 2026 賽季已結束；內容是教學系列 |
| OSChina | 以資訊為主，連線不穩；條款未確認 |
| Habr | 使用者協議禁止商業目的使用；俄文；不是兩個 demo 類別的主要來源 |

### 4.4 給主控者的提醒

- **展示頁與 MCP 回應不要轉貼社群原文**（V2EX 公平使用規則、Qiita 第 8 條、Zenn 第 6 條都指向這點）。`sources` 欄只放貼文 URL 與日期。
- **灌星要防**：Hatena 抽樣就碰到一週 1,000★ 的 repo。知名度分數不能只看星數，至少加「星數成長速度 vs. 建立天數」的異常檢查。
- **本地 AI 類**在這些社群多是教學與實測文，不是作品發表。它們適合當品質訊號（「有人寫文章實測過」），新作品還是要靠 GitHub 本身。

---

## 5. 來源

查證日期都是 2026-10-28（台北）。「實測」表示用 curl 或腳本實際打過。

| 管道 | 連結 | 內容 |
|---|---|---|
| V2EX | https://www.v2ex.com/p/7v9TEc53 | API v1 文件與公平使用規則、120 次／小時 |
| V2EX | https://www.v2ex.com/help/api | API 2.0：Personal Access Token、600 次／小時、`nodes/:node_name/topics` |
| V2EX | https://www.v2ex.com/about | 社區規則（只以連結分享、不全文轉載） |
| V2EX | https://www.v2ex.com/feed/create.xml | 實測：50 篇、全文、31 小時 |
| V2EX | https://www.v2ex.com/api/topics/show.json?node_name=create | 實測：10 篇；標頭 `X-Rate-Limit-Limit: 600` |
| V2EX | https://www.v2ex.com/api/nodes/show.json?name=create | 實測：節點說明「欢迎你在这里发布自己的最新作品！」、38,235 篇 |
| V2EX | https://www.v2ex.com/api/v2/nodes/create/topics | 實測：未帶 token 回 401 |
| V2EX | https://www.v2ex.com/robots.txt | 實測：只擋後台與登入頁 |
| Qiita | https://qiita.com/api/v2/docs | rate limit 60／1,000、per_page／page 上限、token 取得 |
| Qiita | https://qiita.com/terms | 利用規約第 7、8、11 條 |
| Qiita | https://qiita.com/api/v2/items?query=tag:個人開発%20created:>=2026-10-20 | 實測：`total-count: 236` |
| Zenn | https://zenn.dev/zenn/articles/zenn-feed-rss | 官方 feed 說明（約 20 篇、`all=1` 只限使用者 feed） |
| Zenn | https://zenn.dev/terms | 利用規約第 4、6 條（2025-06-05 改定） |
| Zenn | https://zenn.dev/topics/cli/feed | 實測：20 篇 |
| Zenn | https://zenn.dev/robots.txt | 實測：只擋 `/search` |
| Hatena | https://developer.hatena.ne.jp/license/ | Hatena Developer Center 規約第 2、4 條（2023-05-24 改定） |
| Hatena | https://developer.hatena.ne.jp/ja/documents/bookmark/misc/feed/ | 官方 feed 規格（使用者 feed 的 `page`、`tag`、`url`） |
| Hatena | https://policies.hatena.ne.jp/rule | はてな利用規約第 2、6、8 條（2023-07-01 改定） |
| Hatena | https://b.hatena.ne.jp/site/github.com/?mode=rss&sort=new | 實測：最新 30 筆、翻頁無效 |
| Hatena | https://b.hatena.ne.jp/robots.txt | 實測：`Crawl-delay: 5` |
| GeekNews | https://news.hada.io/guidelines | Show GN 規則 |
| GeekNews | https://news.hada.io/terms | 이용약관第 5、6 條 |
| GeekNews | https://news.hada.io/rss/news | 實測：50 篇、23 小時、Show GN 10 篇、無原始連結 |
| GeekNews | https://news.hada.io/show | 實測：第 1 頁 20 篇、6 篇 github.com |
| GeekNews | https://news.hada.io/robots.txt | 實測：Content-Signal、擋 `/api/` |
| velog | https://v2.velog.io/rss | 實測：垃圾廣告比例 |
| velog | https://velog.io/policy/terms | 著作權歸會員 |
| 阮一峰周刊 | https://github.com/ruanyf/weekly | 投稿方式（issues）；repo 無 LICENSE（raw 實測 404） |
| 阮一峰周刊 | https://raw.githubusercontent.com/ruanyf/weekly/master/docs/issue-416.md | 實測：「工具」12 個 |
| 阮一峰周刊 | https://www.ruanyifeng.com/blog/atom.xml | 實測：文末 CC BY-NC-ND 3.0 聲明 |
| HelloGitHub | https://github.com/521xueweihan/HelloGitHub | README：CC BY-NC-ND 4.0、每月 28 號 |
| HelloGitHub | https://raw.githubusercontent.com/521xueweihan/HelloGitHub/master/content/HelloGitHub126.md | 實測：39 個專案 |
| HelloGitHub | https://hellogithub.com/rss | 實測：只到期數層級 |
| 掘金 | https://lf3-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/juejin/86857833-55f6-4d9e-9897-45cfe9a42be4.html | 用户服务协议 2.6、6.2、10.1（`juejin.cn/terms` 轉址到此） |
| 掘金 | https://juejin.cn/robots.txt | 實測 |
| Gitee | https://gitee.com/api/v5/swagger | OpenAPI v5 文件；實測搜尋未帶 token 回 0 筆、限 60 次 |
| Gitee | https://gitee.com/terms | 用户协议（版權歸上傳者） |
| OSChina | https://www.oschina.net/news/rss | 實測：50 篇、5 天；連線時常被 reset |
| OSChina | https://www.oschina.net/robots.txt | 實測 |
| PTT | https://www.ptt.cc/robots.txt | 實測：Content-Signal、擋 AI 代理 |
| PTT | https://www.ptt.cc/atom/Soft_Job.xml | 實測：522 |
| Dcard | https://www.dcard.tw/service/api/v2/forums | 實測：Cloudflare 403 |
| Dcard | https://www.dcard.tw/service/terms | 實測：403，條款未驗證 |
| iThome | https://ithelp.ithome.com.tw/2026ironman | 實測：賽季已結束 |
| iThome | https://ithelp.ithome.com.tw/rss/articles | 實測：20 篇、0 個 GitHub |
| Habr | https://account.habr.com/info/agreement/ | 使用者協議（禁止商業使用） |
| Habr | https://habr.com/ru/rss/hubs/open_source/articles/ | 實測：40 篇、55 小時 |
