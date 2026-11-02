/**
 * One tool, everything pickfit knows about it, so nobody has to open the
 * README to decide: the profile Muse Spark wrote, every run on every OS with
 * its steps, the features checked one by one, and the scores. Read from the
 * catalog only; nothing here calls a model. A tool without a run says so and
 * shows no steps.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type OS, type RunVideo } from '../catalog.ts';
import { featuresOut } from '../features.ts';
import { L } from '../i18n.ts';
import { installGuide } from '../install.ts';
import { EMPTY_FORM, installSection, levelLine, webFactList } from '../page.ts';
import { day, guiSentence, KIND, KIND_PLURAL, levelLabel, OS_NAME, PRICE, PROCESSING, passed, webLevelLabel } from '../ui/facts.ts';
import { esc, link, listOf, safeUrl } from '../ui/html.ts';
import { icon, osMark } from '../ui/icons.ts';
import { age, badge, compareToggle, coverage, fitz, kindTag, levelIcon, osList, runFacts, SEAM, tape, type FitzName } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
import { posterOf, videoPath } from '../video.ts';
import { NO_INSTALL_LABEL, noInstallLabel, webRanSentence } from '../webapp.ts';

const MATURITY: Record<string, string> = {
  get stable() { return L('Stable', '穩定版'); },
  get beta() { return L('Beta', 'Beta 版'); },
  get alpha() { return L('Alpha', 'Alpha 版'); },
  get prototype() { return L('Prototype', '原型'); },
};

/** Fitz looks pleased only when a run reached the tool's main function and passed. */
function faceFor(entry: Entry): FitzName {
  const web = webCheck(entry);
  if (isWebApp(entry)) return web ? (web.level === 'install' ? 'testing' : 'success') : 'thinking';
  const guide = bestGuide(entry);
  if (!guide) return entry.verification.level === 'failed' ? 'test-failed' : 'thinking';
  if (!passed(guide.run.gui)) return 'neutral';
  return guide.run.level === 'install' ? 'testing' : 'success';
}

function factSheet(entry: Entry, now: Date): string {
  const unknown = `<span class="unknown">${L('not stated', '未說明')}</span>`;
  const web = isWebApp(entry);
  const check = webCheck(entry);
  const verifiedCell = web
    ? check
      ? L(`In a browser, ${esc(day(check.checked_at))}`, `在瀏覽器中，${esc(day(check.checked_at))}`)
      : `<span class="no">${L('Not verified yet', '尚未驗證')}</span>`
    : verifiedOn(entry).length
      ? osList(verifiedOn(entry), { tone: 'pass' })
      : `<span class="no">${L('Not verified yet', '尚未驗證')}</span>`;
  const runsLabel = L('Runs', '執行位置');
  const lastReleaseLabel = L('Last release', '最新版本');
  const rows: [string, string][] = [
    [L('Kind', '類型'), kindTag(entry)],
    [L('Verified on', '已驗證於'), verifiedCell],
    web
      ? [L('Runs in', '執行環境'), L('Any modern browser, nothing to install', '任何現代瀏覽器，免安裝')]
      : [L('Claims to run on', '宣稱支援'), entry.platforms.length ? osList(entry.platforms, { tone: 'quiet' }) : unknown],
    [L('Price', '價格'), entry.pricing ? esc(PRICE[entry.pricing]) + (entry.pricing_note ? `<div class="small quiet">${esc(entry.pricing_note)}</div>` : '') : unknown],
    [runsLabel, entry.processing ? esc(PROCESSING[entry.processing]) : unknown],
    [L('Licence', '授權'), entry.license ? `<code>${esc(entry.license)}</code>${entry.open_source ? ` <span class="small quiet">${L('open source', '開源')}</span>` : ''}` : unknown],
    [lastReleaseLabel, entry.last_release ? `${esc(day(entry.last_release))} <span class="small quiet">(${esc(age(entry.last_release, now) ?? '')})</span>` : unknown],
  ].filter(([k]) => !web || (k !== runsLabel && k !== lastReleaseLabel)) as [string, string][];
  if (entry.maturity) rows.push([L('Maturity', '成熟度'), esc(MATURITY[entry.maturity] ?? entry.maturity)]);
  return `<dl class="facts-dl">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
}

function prerequisites(entry: Entry): string {
  const p = entry.prerequisites;
  const items: string[] = [];
  if (p.runtimes.length) {
    const list = p.runtimes.map((r) => `<code>${esc(r)}</code>`).join(', ');
    items.push(L(`Runtimes: ${list}`, `執行環境：${list}`));
  }
  if (p.system_packages.length) {
    const list = p.system_packages.map((r) => `<code>${esc(r)}</code>`).join(', ');
    items.push(L(`System packages: ${list}`, `系統套件：${list}`));
  }
  if (p.gpu === 'required') items.push(L('A GPU is required', '需要 GPU'));
  else if (p.gpu === 'optional') items.push(L('A GPU is optional', '可選用 GPU'));
  if (p.min_ram_gb) items.push(L(`At least ${p.min_ram_gb} GB of RAM`, `至少 ${p.min_ram_gb} GB 記憶體`));
  if (p.apple_silicon_only) items.push(L('Apple silicon only', '僅支援 Apple 晶片'));
  if (p.network === 'required') items.push(L('Needs the network', '需要網路'));
  if (p.api_keys.length) {
    const list = p.api_keys.map(esc).join(', ');
    items.push(L(`Keys or accounts: ${list}`, `金鑰或帳號：${list}`));
  }
  return items.length
    ? `<ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul>`
    : `<p class="quiet">${L('The README lists nothing you need first.', 'README 沒有列出需要先準備的東西。')}</p>`;
}

/** features.ts writes "<reason>: <the run's note>"; a person needs only the note when there is one. */
const featureWhy = (detail: string) => {
  const at = detail.indexOf(': ');
  return (at > 0 ? detail.slice(at + 2) : detail).replace(/^not checked:?\s*/i, '');
};

/** Why the features come from the profile alone: a run from before feature checks, or no run at all. */
const notRecorded = (entry: Entry, ran: boolean) =>
  ran
    ? L(
        'This run came before pickfit checked features one by one, so these come from the README only.',
        '這次測試早於 pickfit 開始逐項檢查功能，所以以下只依據 README。',
      )
    : L(
        `pickfit hasn’t run it yet, so these come from ${isWebApp(entry) ? 'its own site' : 'the README'} only.`,
        `pickfit 還沒測過它，所以以下只依據${isWebApp(entry) ? '它自己的網站' : ' README'}。`,
      );

/** Every advertised feature with what the run did about it. */
function featureList(entry: Entry): string {
  const guide = bestGuide(entry);
  const f = featuresOut(entry, guide);
  if (!f.checked.length && !f.not_checked.length) return '';
  const items = [
    ...f.checked.map(
      (c) => `<li class="feat-ok">${icon('check')}<div>${esc(c.feature)}<details class="feat-check"><summary>${L('Checked', '已檢查')}</summary><code>${esc(c.check)}</code></details></div></li>`,
    ),
    ...f.not_checked.map((n) => {
      const failed = n.reason === 'test_failed';
      return `<li class="${failed ? 'feat-fail' : 'feat-open'}">${icon(failed ? 'x' : 'circle-dashed')}<div>${esc(n.feature)}<small>${failed ? L('Failed: ', '失敗：') : L('Not checked: ', '未檢查：')}${esc(featureWhy(n.detail))}</small></div></li>`;
    }),
  ];
  return (
    `<section class="block" aria-labelledby="features-title"><h2 id="features-title">${L('What it does, feature by feature', '逐項功能')}</h2>` +
    (f.recorded ? '' : `<p class="quiet">${notRecorded(entry, guide !== null || webCheck(entry) !== null)}</p>`) +
    `<ul class="feat-list">${items.join('')}</ul></section>`
  );
}

/** A web app: open it, and what pickfit's browser saw when it did. */
function webRun(entry: Entry): string {
  const check = webCheck(entry);
  const url = entry.web!.url;
  const open = link(url, `${icon('external-link')}${L(`Open ${esc(entry.name)}`, `開啟 ${esc(entry.name)}`)}`, 'btn btn-primary btn-sm');
  if (!check) {
    return (
      `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">${L('Open it', '開啟')}</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p>` +
      L(
        `<b>pickfit hasn’t checked ${esc(entry.name)} in its browser yet</b>, so it never suggests it.`,
        `<b>pickfit 還沒在瀏覽器中檢查過 ${esc(entry.name)}</b>，所以不會推薦它。`,
      ) +
      `</p>` +
      `<p class="quiet">${L('The profile above comes from its own site only.', '上方簡介只依據它自己的網站。')}</p></div></div></section>`
    );
  }
  const evidence = safeUrl(check.evidence_url);
  return (
    `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">${L('Open it', '開啟')}</h2>` +
    `<article class="run-card" id="run-web"><div class="run-head"><h3>${esc(noInstallLabel())}</h3>` +
    `<span class="badges">${badge('pass', L('Checked in a browser', '已在瀏覽器實測'), { icon: 'check' })}</span></div>` +
    SEAM +
    levelLine(webLevelLabel(check), true) +
    `<p>${esc(webRanSentence(check))}</p>` +
    webFactList(entry) +
    (open ? `<p class="t-open">${open}<span class="quiet small" translate="no">${esc(url)}</span></p>` : '') +
    (evidence ? `<p>${link(evidence, `${icon('external-link')} ${L('Run record', '測試紀錄')}`)}</p>` : '') +
    `</article></section>`
  );
}

/** A run's clip: pickfit's own recording, the line that says what it is, and the raw recordings it was cut from. */
function runVideo(slug: string, runId: string, video: RunVideo): string {
  const id = `video-${runId}`;
  const seconds = Math.round(video.seconds);
  const raw = video.raw
    .map(
      (r) =>
        `<li><a href="${esc(videoPath(slug, r.file))}" download>${esc(r.file)}</a> <span class="quiet">${L(`(${Math.round(r.seconds)} s)`, `（${Math.round(r.seconds)} 秒）`)}</span>` +
        `<br><span class="quiet small">sha256</span> <code class="hash" translate="no">${esc(r.sha256)}</code></li>`,
    )
    .join('');
  return (
    `<figure class="run-video">` +
    `<video controls preload="metadata" playsinline poster="${esc(videoPath(slug, posterOf(video.clip)))}" aria-describedby="${esc(id)}">` +
    `<source src="${esc(videoPath(slug, video.clip))}" type="video/mp4">` +
    `<a href="${esc(videoPath(slug, video.clip))}">${L('Download the clip', '下載影片')}</a></video>` +
    `<figcaption id="${esc(id)}">${L(
      `Recorded by pickfit in a sandbox on ${esc(day(video.recorded_at))} · ${seconds} s · shows ${esc(listOf(video.features))}.`,
      `由 pickfit 於 ${esc(day(video.recorded_at))} 在沙盒中錄製 · ${seconds} 秒 · 展示 ${esc(listOf(video.features))}。`,
    )}</figcaption>` +
    `<details class="raw"><summary class="small">${L(`Unedited recordings (${video.raw.length})`, `原始錄影（${video.raw.length}）`)}</summary><ul class="small">${raw}</ul></details>` +
    `</figure>`
  );
}

/** One run per verified OS: the record, then the steps that worked there. */
function runs(catalog: Catalog, entry: Entry): string {
  if (isWebApp(entry) && entry.web) return webRun(entry);
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    return (
      `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">${L('Install', '安裝')}</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p>` +
      L(
        `<b>pickfit hasn’t verified ${esc(entry.name)} yet</b>, so it gives no install steps and never suggests it.`,
        `<b>pickfit 還沒驗證過 ${esc(entry.name)}</b>，所以不提供安裝步驟，也不會推薦它。`,
      ) +
      `</p>` +
      `<p class="quiet">${entry.verification.level === 'failed' ? L('A verification run did not pass. ', '有一次驗證測試沒通過。') : ''}${L('The profile above comes from its README only.', '上方簡介只依據它的 README。')}</p></div></div></section>`
    );
  }
  const cards = oses.map((os: OS, i) => {
    const g = entry.install[os]!;
    const out = installGuide(catalog, { slug: entry.slug, os });
    const r = g.run;
    const evidence = { gui: r.gui, mcp: g.mcp };
    const recordUrl = safeUrl(r.evidence_url);
    let mcpLine = '';
    if (g.mcp) {
      const transport = g.mcp.transport === 'stdio' ? 'stdio' : 'HTTP';
      mcpLine = `<p>${L(
        `An MCP client handshake over ${transport} listed ${g.mcp.tool_count} tool${g.mcp.tool_count === 1 ? '' : 's'}${g.mcp.called_tool ? `, and a call to <code>${esc(g.mcp.called_tool)}</code> returned a result` : ''}.`,
        `MCP 用戶端透過 ${transport} 連線，列出 ${g.mcp.tool_count} 個工具${g.mcp.called_tool ? `，呼叫 <code>${esc(g.mcp.called_tool)}</code> 也回傳了結果` : ''}。`,
      )}</p>`;
    }
    return (
      `<article class="run-card" id="run-${os}"><div class="run-head"><h3>${osMark(os)}${esc(OS_NAME[os])}${r.arch ? ` <span class="arch">${esc(r.arch)}</span>` : ''}</h3></div>` +
      SEAM +
      levelLine(levelLabel(r.level, evidence), passed(r.gui), levelIcon(r.level, evidence)) +
      runFacts(r, { offline: r.gui ? null : g.works_offline, named: true }) +
      (r.gui ? `<p>${esc(guiSentence(r.gui))}</p>` : '') +
      (r.video ? runVideo(entry.slug, r.id, r.video) : '') +
      mcpLine +
      (recordUrl ? `<p>${link(recordUrl, `${icon('external-link')} ${L('Run record', '測試紀錄')}`)}</p>` : '') +
      installSection(out, { ...EMPTY_FORM, os }, i === 0, true) +
      `</article>`
    );
  });
  return `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">${L('Install steps that worked', '可行的安裝步驟')}</h2>${cards.join('')}</section>`;
}

/** The kind a profile sits under in Browse: web apps have their own shelf. */
const crumb = (entry: Entry) => {
  const kind = isWebApp(entry) ? 'web_app' : entry.category;
  return `<a href="/browse?kind=${esc(kind)}">${esc(KIND_PLURAL[kind] ?? KIND[kind] ?? '')}</a>`;
};

export function renderTool(catalog: Catalog, entry: Entry, nonce: string): string {
  const now = new Date(catalog.built_at);
  const guide = bestGuide(entry);
  const features = featuresOut(entry, guide);
  const verified = isVerified(entry);
  const web = isWebApp(entry) ? webCheck(entry) : null;
  const badges = [
    web ? badge('info', L(NO_INSTALL_LABEL, '免安裝'), { icon: 'globe' }) : '',
    web
      ? badge('pass', L(`Verified: ${webLevelLabel(web)}`, `已驗證：${webLevelLabel(web)}`), { icon: levelIcon(web.level) })
      : verified && guide
        ? badge(
            'pass',
            L(
              `Verified: ${levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp })}`,
              `已驗證：${levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp })}`,
            ),
            { icon: levelIcon(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp }) },
          )
        : badge('quiet', L('Not verified yet', '尚未驗證'), { icon: 'circle-dashed' }),
    entry.scores?.treasure ? badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  const webUrl = entry.web?.url ?? null;
  const links = [
    webUrl ? link(webUrl, `${icon('external-link')}${L('Open it', '開啟')}`, 'btn btn-on-mat btn-sm') : '',
    link(entry.repo_url, `${icon('external-link')}${L('Source code', '原始碼')}`, 'btn btn-on-mat btn-sm'),
    entry.homepage && entry.homepage !== entry.repo_url && entry.homepage !== webUrl ? link(entry.homepage, `${icon('external-link')}${L('Homepage', '首頁')}`, 'btn btn-on-mat btn-sm') : '',
  ].join('');
  const about = [
    entry.why_worth_it ? `<p class="fit">${esc(entry.why_worth_it)}</p>` : '',
    entry.use_cases.length ? `<h3>${L('Good for', '適合用來')}</h3><ul class="uses">${entry.use_cases.map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : '',
    entry.alternatives_to.length ? `<p><span class="lead-in">${L('An alternative to', '可替代')}</span> ${esc(listOf(entry.alternatives_to))}${L('.', '。')}</p>` : '',
    isWebApp(entry) ? '' : `<h3>${L('Before you install', '安裝前須知')}</h3>${prerequisites(entry)}`,
  ].join('');
  const sources = entry.sources
    .map((s) => safeUrl(s))
    .filter((s): s is string => !!s)
    .map((s) => `<li>${link(s, esc(s.replace(/^https?:\/\//, '').replace(/^api\.github\.com\/repos\//, 'github.com/')))}</li>`)
    .join('');
  const main =
    `<section class="head mat after-top"><div class="wrap">` +
    `<p class="crumbs"><a href="/browse">${L('Browse', '瀏覽')}</a>${icon('arrow-right')}${crumb(entry)}</p>` +
    `<div class="head-row"><div><h1>${esc(entry.name)}</h1><p class="lede">${esc(entry.summary)}</p>` +
    `<p class="badges">${badges}</p><p class="badges">${links}${verified ? compareToggle(entry.slug, entry.name) : ''}</p></div>` +
    `${fitz(faceFor(entry), 150, { eager: true })}</div></div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap layout"><div>` +
    `<section class="block" aria-labelledby="about-title"><h2 id="about-title">${L('What it is', '這是什麼')}</h2>${about}</section>` +
    runs(catalog, entry) +
    featureList(entry) +
    `</div><aside class="side" aria-label="${L('At a glance', '一覽')}">` +
    `<div class="panel"><h2>${L('At a glance', '一覽')}</h2>${factSheet(entry, now)}<div class="t-measure panel-measure">` +
    tape(L('Quality', '品質'), entry.scores?.quality ?? null, { pop: 'pop-quality' }) +
    tape(L('Popularity', '知名度'), entry.scores?.popularity ?? null, { pop: 'pop-popularity', tone: 'quiet' }) +
    coverage(features, { pop: 'pop-features' }) +
    `</div><p class="small quiet">${L('Scored apart; ranked by neither.', '兩項分開計分，排序不看分數。')} <a href="/how#scores">${L('How scores work', '評分方式')}</a></p></div>` +
    (sources ? `<details class="panel sources"><summary>${L('Sources', '來源')}</summary><ul class="small">${sources}</ul><p class="small quiet">${L('Every field in the profile cites one of these.', '簡介裡的每個欄位都引用下列其中一個來源。')}</p></details>` : '') +
    `</aside></div>`;
  return renderShell({
    nonce,
    title: `${entry.name}: ${web ? L('checked in a browser', '瀏覽器實測') : verified ? L('verified install steps', '已驗證的安裝步驟') : L('profile', '簡介')} · pickfit`,
    description: entry.summary,
    active: 'browse',
    main,
  });
}
