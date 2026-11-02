/**
 * Browse the catalog: verified tools by kind and OS, hidden gems first or
 * newest runs first. The filters are plain GET links (kind, os, gem, sort,
 * all), never free text: a typed filter runs in the page only, so what someone
 * types never reaches a request URL or a log.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type OS } from '../catalog.ts';
import { L } from '../i18n.ts';
import { formOf, KIND, KIND_PLURAL, levelLabel, OS_NAME, osName, PRICE, webLevelLabel } from '../ui/facts.ts';
import { esc, listOf } from '../ui/html.ts';
import { icon, osMark } from '../ui/icons.ts';
import { badge, compareToggle, fitz, kindIcon, kindTag } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';

/** The three categories, and web apps (a kind, across categories). */
const KINDS = ['dev_cli', 'local_ai', 'mcp_server', 'web_app'] as const;
type Kind = (typeof KINDS)[number];
type Sort = 'gems' | 'newest' | 'name';

export interface BrowseQuery {
  kind: Kind | '';
  os: OS | '';
  gem: boolean;
  all: boolean;
  sort: Sort;
}

export function browseQuery(params: URLSearchParams): BrowseQuery {
  const kind = params.get('kind') ?? '';
  const os = params.get('os') ?? '';
  const sort = params.get('sort') ?? '';
  return {
    kind: (KINDS as readonly string[]).includes(kind) ? (kind as Kind) : '',
    os: (OSES as readonly string[]).includes(os) ? (os as OS) : '',
    gem: params.get('gem') === '1',
    all: params.get('all') === '1',
    sort: sort === 'newest' || sort === 'name' ? sort : 'gems',
  };
}

function href(q: BrowseQuery, change: Partial<BrowseQuery>): string {
  const n = { ...q, ...change };
  const p = new URLSearchParams();
  if (n.kind) p.set('kind', n.kind);
  if (n.os) p.set('os', n.os);
  if (n.gem) p.set('gem', '1');
  if (n.all) p.set('all', '1');
  if (n.sort !== 'gems') p.set('sort', n.sort);
  const s = p.toString();
  return `/browse${s ? `?${s.replace(/&/g, '&amp;')}` : ''}`;
}

const chipLink = (on: boolean, to: string, text: string, mark = '') =>
  `<a class="chip${on ? ' on' : ''}" href="${to}"${on ? ' aria-current="true"' : ''}>${on ? icon('check') : mark}${esc(text)}</a>`;

/** Cards shown before "Show more" (with the script; without it, all of them). */
const FIRST = 30;

const ofKind = (entry: Entry, kind: Kind) => (kind === 'web_app' ? isWebApp(entry) : entry.category === kind);

/** Newest run first: a web app's browser run counts like an install run. */
const lastRun = (entry: Entry) => bestGuide(entry)?.run.checked_at ?? webCheck(entry)?.checked_at ?? '';

function card(entry: Entry, i: number): string {
  const oses = verifiedOn(entry);
  const guide = bestGuide(entry);
  const web = webCheck(entry);
  const verified = isVerified(entry);
  const text = [entry.name, entry.summary, entry.tags.join(' '), entry.use_cases.join(' '), KIND[entry.category] ?? '', formOf(entry)].join(' ').toLowerCase();
  const osList = listOf(oses.map((os) => osName(os)));
  return (
    `<li class="cat-card${verified ? '' : ' unverified'}${i >= FIRST ? ' later' : ''}" data-text="${esc(text)}">` +
    `<h3><a href="/tool/${esc(entry.slug)}">${esc(entry.name)}</a></h3>` +
    `<p class="small quiet">${kindTag(entry)}</p>` +
    `<p>${esc(entry.summary)}</p>` +
    (verified ? '<div class="seam" aria-hidden="true"></div>' : '') +
    `<div class="row">` +
    (web
      ? badge('pass', L('Checked in a browser, any OS', '已在瀏覽器實測，不限系統'), { marks: icon('globe'), title: webLevelLabel(web) })
      : verified
        ? badge('pass', L(`Verified on ${osList}`, `已在 ${osList} 驗證`), {
            marks: oses.map(osMark).join(''),
            title: guide ? levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp }) : undefined,
          })
        : badge('quiet', L('Not verified', '未驗證'), { icon: 'circle-dashed' })) +
    (entry.scores?.treasure ? badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem', marks: '', pop: 'pop-gem' }) : '') +
    (entry.pricing === 'free' ? badge('free', PRICE.free) : '') +
    (verified ? compareToggle(entry.slug, entry.name) : '') +
    `</div></li>`
  );
}

export function renderBrowse(catalog: Catalog, params: URLSearchParams, nonce: string): string {
  const q = browseQuery(params);
  const pool = catalog.entries.filter((e) => q.all || isVerified(e));
  const list = pool
    .filter((e) => !q.kind || ofKind(e, q.kind))
    // A web app checked in a browser runs on any OS.
    .filter((e) => !q.os || verifiedOn(e).includes(q.os) || (isWebApp(e) && webCheck(e) !== null))
    .filter((e) => !q.gem || e.scores?.treasure)
    .sort((a, b) => {
      if (q.sort === 'name') return a.name.localeCompare(b.name);
      if (q.sort === 'newest') return lastRun(b).localeCompare(lastRun(a)) || a.name.localeCompare(b.name);
      return (b.scores?.treasure_value ?? -1) - (a.scores?.treasure_value ?? -1) || (b.scores?.quality ?? -1) - (a.scores?.quality ?? -1) || a.name.localeCompare(b.name);
    });
  const unverified = catalog.entries.length - catalog.entries.filter(isVerified).length;
  const filters =
    `<form class="filters" method="get" action="/browse" role="search" aria-label="${L('Filter the catalog', '篩選目錄')}">` +
    `<label class="find-in">${icon('search')}<span class="sr">${L('Filter these tools', '篩選這些工具')}</span><input type="search" data-filter placeholder="${L('Filter by name or task', '依名稱或任務篩選')}" autocomplete="off"></label>` +
    `<fieldset><legend>${L('Kind', '類型')}</legend><div class="chips">${chipLink(!q.kind, href(q, { kind: '' }), L('All', '全部'))}${KINDS.map((k) => chipLink(q.kind === k, href(q, { kind: k }), KIND_PLURAL[k], icon(kindIcon(k)))).join('')}</div></fieldset>` +
    `<fieldset><legend>${L('Verified on', '已驗證於')}</legend><div class="chips">${chipLink(!q.os, href(q, { os: '' }), L('Any OS', '不限'))}${OSES.map((o) => chipLink(q.os === o, href(q, { os: o }), OS_NAME[o], osMark(o))).join('')}</div></fieldset>` +
    `<details class="more-filters"${q.gem || q.all || q.sort !== 'gems' ? ' open' : ''}><summary>${L('More filters', '更多篩選')}</summary>` +
    `<fieldset><legend>${L('Show', '顯示')}</legend><div class="chips">${chipLink(q.gem, href(q, { gem: !q.gem }), L('Hidden gems only', '只看寶藏'))}${chipLink(q.all, href(q, { all: !q.all }), L(`Include ${unverified} not yet verified`, `含 ${unverified} 款未驗證工具`))}</div></fieldset>` +
    `<fieldset><legend>${L('Order', '排序')}</legend><div class="chips">${chipLink(q.sort === 'gems', href(q, { sort: 'gems' }), L('Hidden gems first', '寶藏優先'))}${chipLink(q.sort === 'newest', href(q, { sort: 'newest' }), L('Newest runs', '最新測試'))}${chipLink(q.sort === 'name', href(q, { sort: 'name' }), L('A to Z', 'A 到 Z'))}</div></fieldset></details>` +
    `</form>`;
  const kindPart = q.kind ? ` · ${esc(KIND_PLURAL[q.kind])}` : '';
  const osPart = q.os ? L(` · verified on ${esc(OS_NAME[q.os])}`, ` · 已在 ${esc(OS_NAME[q.os])} 驗證`) : '';
  const main =
    `<section class="head mat after-top"><div class="wrap head-row"><div><h1>${L('Browse verified tools', '所有驗證過的工具')}</h1>` +
    `<p class="lede">${L('Every tool here was installed by pickfit in a fresh sandbox; every web app was opened and used in a sandboxed browser', '這裡的每款工具，pickfit 都在全新沙盒裡裝過；網頁應用也都在瀏覽器裡實際用過')}</p></div>` +
    `${fitz('idle', 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap layout layout-browse"><aside class="side side-left">${filters}</aside><div>` +
    `<p class="cat-count">${L(
      `<span data-shown>${list.length}</span> of ${list.length} ${q.all ? 'tools' : 'verified tools'}`,
      `顯示 <span data-shown>${list.length}</span> / ${list.length} 款${q.all ? '工具' : '已驗證的工具'}`,
    )}${kindPart}${osPart}</p>` +
    `<h2 class="sr">${L('Tools', '工具')}</h2>` +
    (list.length
      ? `<ul class="cat-grid" data-grid>${list.map(card).join('')}</ul>` +
        (list.length > FIRST ? `<p class="pager js-only"><button type="button" class="btn btn-quiet" data-more>${L(`Show ${Math.min(FIRST, list.length - FIRST)} more`, `再顯示 ${Math.min(FIRST, list.length - FIRST)} 款`)}</button></p>` : '')
      : '') +
    `<div class="empty"${list.length ? ' hidden' : ''} data-filter-empty>${fitz('sorry', 80)}<div><p><b>${L('Nothing here fits that filter.', '沒有符合這個篩選條件的工具。')}</b></p><p class="quiet">${L('Try fewer filters, or <a href="/">describe the job</a> and let Fitz look.', '試著減少篩選條件，或<a href="/">描述你要做的事</a>，讓 Fitz 幫你找。')}</p></div></div>` +
    `</div></div>`;
  return renderShell({
    nonce,
    title: L('Browse verified tools · pickfit', '瀏覽已驗證的工具 · pickfit'),
    description: L(
      'Developer CLIs, local AI tools, MCP servers and web apps that pickfit tried itself: installed in a fresh sandbox, or used in a sandboxed browser.',
      'pickfit 親自試穿過的開發者 CLI、本機 AI 工具、MCP 伺服器與網頁應用：在全新的沙盒中安裝，或在沙盒瀏覽器中實際使用。',
    ),
    active: 'browse',
    main,
  });
}
