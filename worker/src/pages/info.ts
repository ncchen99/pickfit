/** The reading pages: how pickfit works (and what its labels mean), connecting an agent, and not found. */
import type { Catalog } from '../catalog.ts';
import { L } from '../i18n.ts';
import { catalogStats, rulesLabel } from '../page.ts';
import { LEVEL_LABEL } from '../ui/facts.ts';
import { esc } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { badge, command, fitz, levelIcon, marksLegend, tape } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';

const head = (title: string, lede: string, who: Parameters<typeof fitz>[0]) =>
  `<section class="head mat after-top"><div class="wrap head-row"><div><h1>${esc(title)}</h1><p class="lede">${esc(lede)}</p></div>` +
  `${fitz(who, 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>`;

export function renderHow(catalog: Catalog, nonce: string): string {
  const s = catalogStats(catalog);
  const levels: [string, string][] = [
    ['install', L('The command runs and prints its version or help. A GUI app opened its own window.', '指令能執行，並印出版本或說明。GUI 應用程式能開啟自己的視窗。')],
    ['function', L('The run gave it real input and checked the output: a file converted, a query answered.', '測試時給它真實輸入並檢查輸出，例如檔案成功轉換、查詢得到回答。')],
    ['service', L('A local server came up and answered. For an MCP server, a client called one of its tools.', '本機伺服器成功啟動並有回應；若是 MCP 伺服器，則有用戶端成功呼叫它的工具。')],
    ['inference', L('A local AI tool loaded a model and generated text, speech or an image.', '本機 AI 工具載入模型，並生成了文字、語音或圖片。')],
  ];
  const main =
    head(
      L('How Fitz checks a tool', 'Fitz 怎麼檢查工具'),
      L('Every suggestion rests on a run pickfit did itself, and every reason points at the field it came from. Here is the whole method, and what each label on a tool card means.', '每個推薦都來自 pickfit 親自做的測試，每個理由都指得出依據的欄位。以下是完整方法，以及工具卡上各個標籤的意思。'),
      'testing',
    ) +
    `<div class="wrap"><article class="prose">` +
    `<h2>${L('Four steps, one tool at a time', '四個步驟，一款一款來')}</h2>` +
    `<ol><li>${L(`<b>Find.</b> Agents scan new GitHub projects and Show HN posts. For now they start with newer tools few people know yet, to show that such tools can be tested and trusted too. Anyone can also submit a public repo or a website. So far pickfit has read ${s.listed} READMEs.`, `<b>發掘。</b>agent 掃描 GitHub 上的新專案和 Show HN 貼文。現階段先從還少有人知道的新工具找起，證明這類軟體也能被實測、有保障。任何人也都能投稿公開的 repo 或網站。到目前為止，pickfit 已讀過 ${s.listed} 份 README。`)}</li>` +
    `<li>${L('<b>Read.</b> Meta’s Muse Spark reads each README and writes a profile: what it does, where it runs, what it costs, whether it works offline. Every field quotes its source; a field with no source is left empty, not guessed.', '<b>閱讀。</b>Meta 的 Muse Spark 閱讀每份 README 並整理成簡介：它做什麼、在哪裡執行、費用多少、能否離線使用。每個欄位都引用出處；沒有出處的欄位就留空，不靠猜測。')}</li>` +
    `<li>${L(`<b>Install.</b> A verification agent installs the tool in a fresh sandbox (Linux in gVisor; some by hand on a real Mac), fixes what the README got wrong, checks the main features one by one, then replays the working steps in a brand-new sandbox. ${s.replayed} tools passed a replay.`, `<b>試裝。</b>驗證 agent 在全新沙盒裡安裝工具（gVisor 裡的 Linux；部分在實體 Mac 上手動安裝），修正 README 寫錯的地方，逐一檢查主要功能，再到另一個全新沙盒重跑可行的步驟。已有 ${s.replayed} 款工具通過重跑。`)}</li>` +
    `<li>${L('<b>Match.</b> Your sentence and every verified profile that meets your conditions go to Muse Spark in one call. Each reason it gives must name a profile field; code checks the value and drops any reason that doesn’t hold. If the model is unavailable, pickfit ranks by rules and says so.', '<b>比對。</b>你的描述和所有符合條件的已驗證簡介，會在一次呼叫中送給 Muse Spark。它給的每個理由都必須指名簡介裡的一個欄位；程式會核對數值，刪掉站不住腳的理由。如果模型無法使用，pickfit 會改用規則排序，並明白告知。')}</li></ol>` +
    `<h2 id="levels">${L('What “verified” means', '「已驗證」代表什麼')}</h2><p>${L('A tool card says how far the run got. Higher is stronger evidence:', '工具卡會標明測試進行到哪一步。層級越高，證據越有力：')}</p>` +
    `<ul class="levels">${levels.map(([k, t]) => `<li><b><span class="level-i">${icon(levelIcon(k))}</span>${esc(LEVEL_LABEL[k])}</b>${esc(t)}</li>`).join('')}</ul>` +
    `<p>${L('A run says where it happened (OS and CPU) and when. Its OS mark is green when the steps ran on the system you chose; otherwise the card says in words where they did run.', '每次測試都會標明地點（作業系統和 CPU）與時間。步驟若在你選的系統上跑過，系統標記就是綠色；否則工具卡會寫明實際在哪裡跑的。')}</p>` +
    `<h3 id="web">${L('Web apps: no install, just open it', '網頁應用：免安裝，打開就能用')}</h3><p>${L('A web app runs on its makers’ site, so there is nothing to install. pickfit opens it once in a sandboxed browser: it counts as installed when the page loads to its own main screen (not an error page, a parked domain or a sign-in wall), and as working when Muse Spark uses it for what it claims and pickfit checks the result itself. It never posts, mails, signs up or orders on a real site. The browser’s own records say whether an account was needed, whether ads showed, how many other sites the page contacted, and whether what pickfit typed in left the device. Only an installable web app (a PWA) that pickfit reloaded with the network off counts as working offline', '網頁應用跑在開發者的網站上，不用安裝。pickfit 會在沙盒瀏覽器裡打開一次：頁面能載入到自己的主畫面（不是錯誤頁、停放網域或登入牆）就算「裝好」；Muse Spark 用它完成它宣稱的功能，且 pickfit 親自核對結果，就算「能用」。過程中絕不會在真實網站上發文、寄信、註冊或下單。瀏覽器本身的紀錄會說明是否需要帳號、是否出現廣告、頁面連到多少其他網站，以及 pickfit 輸入的內容是否離開了裝置。只有 pickfit 在斷網狀態下重新載入過的可安裝網頁應用（PWA），才算能離線使用')}${s.web ? L(`. ${s.web} web ${s.web === 1 ? 'app' : 'apps'} passed so far`, `。目前已有 ${s.web} 款網頁應用通過`) : ''}${L('.', '。')}</p>` +
    `<p>${L('When a web app and a tool to install fit your need about equally, the web app comes first. A job that runs for long or in the background, ties into the system or works through many local files leans to the tool you install. If you ask for offline use or for your data to stay on your device, a web app qualifies only when its run showed exactly that.', '當網頁應用和需要安裝的工具同樣符合你的需求時，網頁應用優先。需要長時間或在背景執行、與系統整合，或要處理大量本機檔案的工作，則偏向需要安裝的工具。如果你要求離線使用或資料留在自己的裝置上，網頁應用只有在測試確實證明這點時才符合資格。')}</p>` +
    `<h2 id="labels">${L('What the labels mean', '標籤怎麼看')}</h2>` +
    `<h3>${L('Stitching', '縫線')}</h3><p>${L('The rufous running stitch on a tool card separates the claim from the run record. pickfit draws it only under evidence from its own run. A tool pickfit has not run, such as a well-known option Fitz mentions from general knowledge, never gets stitches, a badge, steps or a link.', '工具卡上的紅褐色平針縫線，把宣稱和測試紀錄分隔開來。pickfit 只在自己測試得到的證據下方畫上縫線。pickfit 沒有測試過的工具，例如 Fitz 憑一般知識提到的知名工具，永遠不會有縫線、徽章、步驟或連結。')}</p>` +
    `<h3 id="marks">${L('Marks on a tool card', '工具卡上的標記')}</h3><p>${L('Facts every card repeats are shown as marks, each named on hover and for screen readers:', '每張工具卡都有的資訊以圖示標記呈現，滑鼠移過去或用螢幕閱讀器時會顯示名稱：')}</p><dl class="legend">${marksLegend()}</dl>` +
    `<h3 id="scores">${L('Quality and popularity', '品質與知名度')}</h3><div class="levels">${tape(L('Quality', '品質'), 84)}${tape(L('Popularity', '知名度'), 22, { tone: 'quiet' })}</div>` +
    `<p>${L('Two scores out of 100, computed apart. <b>Quality</b> is a weighted mean: whether it installed (how many install actions, how many README fixes it needed) 20%, feature results (of the features with a verdict, the share that worked) 20%, how complete the install docs are 25% (Muse Spark grades them, quoting the README), maintenance 10%, issue responsiveness 10%, engineering hygiene 5%; reports from real use join as they accumulate. A part with no data drops out instead of counting as zero: a feature pickfit could not try does not lower the score, and only a failure caused by the tool itself does. What drops out lowers <b>confidence</b>, the share of the score that had data, shown beside it with what is missing. <b>Popularity</b> compares stars, forks, downloads and Hacker News points with other tools of the same kind. The example tapes above are illustrative.', '兩個滿分 100 的分數，分開計算。<b>品質</b>是加權平均：能否安裝（需要多少安裝動作、需要幾處 README 修正）占 20%，功能結果（有結論的功能裡，能用的比例）占 20%，安裝文件的完整度占 25%（由 Muse Spark 引用 README 評分），維護狀況占 10%，issue 回應速度占 10%，工程品質占 5%；實際使用的回報累積後也會納入。沒有資料的項目不計入，而不是算零分：pickfit 測不到的功能不會讓分數變低，只有軟體本身造成的失敗才會。不計入的項目會降低<b>信心度</b>，也就是分數裡有資料的比例，它顯示在分數旁邊，並寫出缺了什麼。<b>知名度</b>則把星數、fork 數、下載數和 Hacker News 分數與同類工具比較。上方的範例量尺僅供示意。')}</p>` +
    `<p>${L('A web app has no README to install from, so its quality is the browser run 50% (it loaded, or it worked when used) and what the browser saw 40% (no account needed, nothing you type sent off your device, no ads, works offline), with real use joining the same way. Its popularity is its GitHub stars, or the points of its Show HN post when it has no public code.', '網頁應用沒有用來安裝的 README，所以它的品質由瀏覽器測試占 50%（能載入，或實際使用時能用），以及瀏覽器觀察到的情況占 40%（不需帳號、輸入內容不會離開裝置、沒有廣告、能離線使用），實際使用的回報也以同樣方式納入。它的知名度是 GitHub 星數；沒有公開原始碼時，則是它 Show HN 貼文的分數。')}</p>` +
    `<p>${L('Desktop and web apps that pickfit opened also get a visual check: Muse Wonder looks at pickfit’s own screenshots and lists defects you could point to, such as text cut off, something covering content, a clipped control, a word broken mid-word, low contrast, tiny text, raw code like &amp;gt;, a broken image, misalignment or crowding. Taste and style don’t count. If it finds a defect the app causes, the quality score drops by 5%; finding none adds nothing. An app not checked yet is shown as not visually checked and keeps its score. How serious each defect is doesn’t count yet: in a review by two independent checkers, about one listed defect in four was not real, and most defects called serious were minor.', 'pickfit 打開過的桌面和網頁應用，還會做一次視覺檢查：Muse Wonder 看 pickfit 自己拍的截圖，列出指得出來的缺陷，例如文字被截斷、有東西蓋住內容、控制項被切掉、字在中間斷行、對比太低、字太小、顯示原始碼（像 &amp;gt;）、圖片壞掉、沒對齊或太擠，不評品味和風格。只要找到應用本身造成的缺陷，品質分就扣 5%；沒找到不加分。還沒做視覺檢查的應用會標示「尚未做視覺檢查」，分數不變。缺陷的嚴重程度暫時不算：兩位獨立複查者的檢查中，大約每四個列出的缺陷就有一個不是真的，標成嚴重的大多其實是輕微。')}</p>` +
    `<p>${L('pickfit also checks every package a fresh install brings against OSV.dev, the public database of known vulnerabilities. A known high or critical vulnerability in any of them caps quality at 79, so the tool can’t be a hidden gem: we would rather miss a gem than recommend software with a known hole. Software pickfit could not check (no lockfile to read, for example) keeps its score, and its page says it was not checked.', 'pickfit 也會拿全新安裝帶進來的每個套件，比對公開的已知漏洞資料庫 OSV.dev。只要其中有已知的高風險或嚴重漏洞，品質最高只算 79 分，因此不會列為寶藏：寧可錯過寶藏，也不推薦有已知漏洞的軟體。pickfit 無法檢查的軟體（例如沒有可讀取的 lockfile）分數不變，頁面上會標明沒有檢查。')}</p>` +
    `<p>${badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem' })}${L(` marks a verified tool with quality 80 or more and popularity 45 or less: ${s.gems} tools today. Fitz ranks by fit to your need, not by either score.`, ` 標示品質 80 以上、知名度 45 以下的已驗證工具：目前共 ${s.gems} 款。Fitz 看合不合你的需求排序，不看分數。`)}</p>` +
    `<h3>${L('Features checked', '已檢查的功能')}</h3><p>${L('The run tries each main feature the README advertises. Some need an account, a GPU, a display or hardware the sandbox doesn’t have; those stay unchecked, and the card gives the reason. A feature whose test failed with the tool’s own error is marked as failed.', '測試會試用 README 宣傳的每項主要功能。有些功能需要帳號、GPU、螢幕或沙盒沒有的硬體；這些就保持未檢查，工具卡會說明原因。測試時出現工具本身錯誤的功能，會標示為失敗。')}</p>` +
    `<h3>${L('Match labels', '符合度標籤')}</h3><p>${L('When the model is paused, pickfit ranks by rules and labels each pick ', '模型暫停時，pickfit 改用規則排序，並看簡介提到你的哪些字詞，把每個選項標為 ')}${badge('pass', L('Good match', '高度符合'))} ${badge('caution', L('Partial match', '部分符合'))}${L(' or ', ' 或 ')}${badge('caution', L('Weak match', '勉強符合'))}${L(' by which of your words its profile mentions. With the model, Muse Spark writes the fit sentence and code checks each of its reasons.', '。使用模型時，由 Muse Spark 寫出符合原因，再由程式核對每個理由。')}</p>` +
    `<h2 id="rules">${L('Fitz’s rules', 'Fitz 的原則')}</h2><div class="care"><div><p>${L('pickfit is neutral on purpose. It belongs to no agent maker and no software vendor, takes no money for placement, and doesn’t make any of the software it suggests. That is what lets it say a little-known tool fits better, or that what you already have is enough.', 'pickfit 刻意保持中立。它不屬於任何 agent 開發商或軟體廠商，不收取排名費用，也不開發它推薦的任何軟體。正因如此，它才能直說某款冷門工具更適合你，或是你現有的已經夠用。')}</p>` +
    `<p>${L('Privacy: no account, no IP address stored. Your sentence goes to Meta’s Muse Spark (served by Meta, reached directly or through OpenRouter) with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS. Compare picks stay in your own browser.', '隱私：免帳號，也不記錄 IP。你的描述會送到 Meta 的 Muse Spark（由 Meta 提供，直接或經 OpenRouter 轉送；已關閉資料保存）；pickfit 只保留從中解析出的條件，例如任務和作業系統。比較清單只存在你自己的瀏覽器裡。')}</p></div>${rulesLabel()}</div>` +
    `<div class="tip">${fitz('peek', 52)}<h3>${L('Found a tool that should be here?', '有好工具想推薦？')}</h3><p>${L('Authors and users can submit a GitHub project, or the address of a web app, through the MCP <code>submit_software</code> tool. It gets the same review: read, tried in a sandbox, scored. Submitting never earns a better rank.', '作者和使用者都可以透過 MCP 的 <code>submit_software</code> 工具提交 GitHub 專案或網頁應用的網址。它會經過同樣的審查：閱讀、在沙盒中試裝、評分。提交不會換來更好的排名。')}</p><p><a class="more" href="/agents">${L('Connect an agent', '接上 agent')}${icon('arrow-right')}</a></p></div>` +
    `</article></div>`;
  return renderShell({ nonce, title: L('How pickfit works · pickfit', 'pickfit 的運作方式 · pickfit'), description: L('How pickfit finds, reads, installs, verifies and matches software, and what each label means.', 'pickfit 如何搜尋、閱讀、安裝、驗證與比對軟體，以及每個標籤的意思。'), active: 'how', tray: false, main });
}

export function renderAgents(origin: string, nonce: string): string {
  const mcp = `${origin}/mcp`;
  const tools: [string, string][] = [
    ['find_software', L('Two or three verified tools for a need and conditions (OS, CPU, free only, offline), with reasons, tradeoffs, the best free option and, when it fits, “built-in is enough”.', '依需求和條件（作業系統、CPU、僅限免費、離線）提供兩到三款已驗證工具，附上理由、取捨、最佳免費選擇，適用時也會直說「內建的就夠用」。')],
    ['find_alternatives', L('Replacements for a tool you use now, given what you don’t like about it and what you must keep.', '根據你對現用工具不滿意的地方和必須保留的功能，找出替代品。')],
    ['get_install_guide', L('The steps that worked in pickfit’s run, for your OS, with what you do by hand and how to check the install.', '針對你的作業系統，提供在 pickfit 測試中可行的步驟，包含需要手動操作的部分，以及如何確認安裝成功。')],
    ['report_outcome', L('Did it install, did it work, are you still using it. Failures queue the tool for a fresh run.', '回報是否安裝成功、是否能用、是否還在使用。失敗的回報會讓工具排入重新測試。')],
    ['submit_software', L('Send a GitHub project for review. It goes through the same read, install and replay as everything else.', '提交 GitHub 專案供審查。它會和其他工具一樣經過閱讀、安裝和重播。')],
  ];
  const main =
    head(
      L('Same answers, in your agent', '在 agent 裡也能用'),
      L('pickfit is an MCP server. Your coding agent gets the same verified data and the same matching as this page, and can install a pick for you with the steps that worked.', 'pickfit 是 MCP 伺服器。你的 coding agent 能拿到和本頁相同的驗證資料與比對結果，還能照可行的步驟幫你安裝。'),
      'recommending',
    ) +
    `<div class="wrap"><article class="prose agents-doc">` +
    `<h2>${L('Connect', '連線')}</h2><p>${L(`Any MCP client that speaks streamable HTTP can connect to <code translate="no">${esc(mcp)}</code>. For Claude Code:`, `任何支援 streamable HTTP 的 MCP 用戶端都能連到 <code translate="no">${esc(mcp)}</code>。Claude Code：`)}</p>` +
    command(`claude mcp add --transport http pickfit ${mcp}`) +
    `<p>${L('For Claude Desktop, Cursor and other clients, add it to the MCP config:', 'Claude Desktop、Cursor 等用戶端，請加進 MCP 設定：')}</p>` +
    command(JSON.stringify({ mcpServers: { pickfit: { type: 'http', url: mcp } } }, null, 2)) +
    `<h2>${L('Tools', '工具')}</h2><div class="table-wrap"><table class="dt"><thead><tr><th scope="col">${L('Tool', '工具')}</th><th scope="col">${L('What it does', '用途')}</th></tr></thead><tbody>` +
    tools.map(([n, t]) => `<tr><th scope="row"><code>${esc(n)}</code></th><td>${esc(t)}</td></tr>`).join('') +
    `</tbody></table></div>` +
    `<h2>${L('Try it', '試試看')}</h2><p>${L('Ask your agent in plain words, for example:', '用平常的話問你的 agent，例如：')}</p><div class="prompt">${command(L('Find me a free tool that works offline on my Mac to turn meeting recordings into subtitles, and install it.', '幫我找一款能在我的 Mac 上離線使用的免費工具，把會議錄音轉成字幕，並幫我安裝。'))}</div>` +
    `<div class="tip">${fitz('peek', 52)}<h3>${L('No sign-up, no ads', '不用註冊，也沒有廣告')}</h3><p>${L('The MCP needs no account and returns no referral links. Answers carry a <code>how_we_know</code> line and the run’s <code>evidence_url</code>, so your agent can tell you where each claim came from.', '這個 MCP 不需要帳號，也不會回傳推薦連結。每個答案都附有 <code>how_we_know</code> 說明和測試的 <code>evidence_url</code>，讓你的 agent 能告訴你每項說法的出處。')}</p></div>` +
    `</article></div>`;
  return renderShell({ nonce, title: L('Connect your agent · pickfit', '接上你的 agent · pickfit'), description: L('Use pickfit from Claude Code, Claude Desktop, Cursor or any MCP client.', '在 Claude Code、Claude Desktop、Cursor 或任何 MCP 用戶端中使用 pickfit。'), active: 'agents', tray: false, main });
}

export function renderNotFound(nonce: string): string {
  const main =
    `<section class="head mat after-top"><div class="wrap nf">${fitz('surprised', 160, { eager: true })}<h1>${L('Page not found', '找不到這個頁面')}</h1>` +
    `<p class="lede">${L('The address may be old, or the tool isn’t in pickfit’s catalog', '網址可能過期了，或這款工具不在 pickfit 的目錄裡')}</p>` +
    `<p class="badges"><a class="btn btn-primary" href="/">${icon('search')}${L('Find software', '搜尋軟體')}</a><a class="btn btn-quiet" href="/browse">${L('Browse verified tools', '瀏覽已驗證工具')}</a></p></div>` +
    `<div class="ruler" aria-hidden="true"></div></section>`;
  return renderShell({ nonce, title: L('Not found · pickfit', '找不到頁面 · pickfit'), description: L('This page does not exist.', '這個頁面不存在。'), active: null, main });
}
