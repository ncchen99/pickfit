/**
 * Browse the catalog: verified tools by kind and OS, hidden gems first or
 * newest runs first. The filters are plain GET links (kind, os, gem, sort,
 * all), never free text: a typed filter runs in the page only, so what someone
 * types never reaches a request URL or a log.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type OS } from '../catalog.ts';
import { formOf, KIND, KIND_PLURAL, levelLabel, OS_NAME, osName, PRICE, kindLine, webLevelLabel } from '../ui/facts.ts';
import { esc, listOf } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { badge, compareToggle, fitz } from '../ui/kit.ts';
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

const chipLink = (on: boolean, to: string, text: string) =>
  `<a class="chip${on ? ' on' : ''}" href="${to}"${on ? ' aria-current="true"' : ''}>${on ? icon('check') : ''}${esc(text)}</a>`;

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
  return (
    `<li class="cat-card${verified ? '' : ' unverified'}${i >= FIRST ? ' later' : ''}" data-text="${esc(text)}">` +
    `<h3><a href="/tool/${esc(entry.slug)}">${esc(entry.name)}</a></h3>` +
    `<p class="small quiet">${esc(kindLine(entry))}</p>` +
    `<p>${esc(entry.summary)}</p>` +
    (verified ? '<div class="seam" aria-hidden="true"></div>' : '') +
    `<div class="row">` +
    (web
      ? badge('pass', 'In a browser', { icon: 'globe', title: webLevelLabel(web) })
      : verified
        ? badge('pass', listOf(oses.map((os) => osName(os))), { icon: 'check', title: guide ? levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp }) : undefined })
        : badge('quiet', 'Not verified', { icon: 'circle-dashed' })) +
    (entry.scores?.treasure ? badge('gem', 'Hidden gem', { icon: 'gem' }) : '') +
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
    `<form class="filters" method="get" action="/browse" role="search" aria-label="Filter the catalog">` +
    `<label class="find-in">${icon('search')}<span class="sr">Filter these tools</span><input type="search" data-filter placeholder="Filter by name or task" autocomplete="off"></label>` +
    `<fieldset><legend>Kind</legend><div class="chips">${chipLink(!q.kind, href(q, { kind: '' }), 'All')}${KINDS.map((k) => chipLink(q.kind === k, href(q, { kind: k }), KIND_PLURAL[k])).join('')}</div></fieldset>` +
    `<fieldset><legend>Verified on</legend><div class="chips">${chipLink(!q.os, href(q, { os: '' }), 'Any OS')}${OSES.map((o) => chipLink(q.os === o, href(q, { os: o }), OS_NAME[o])).join('')}</div></fieldset>` +
    `<details class="more-filters"${q.gem || q.all || q.sort !== 'gems' ? ' open' : ''}><summary>More filters</summary>` +
    `<fieldset><legend>Show</legend><div class="chips">${chipLink(q.gem, href(q, { gem: !q.gem }), 'Hidden gems only')}${chipLink(q.all, href(q, { all: !q.all }), `Include ${unverified} not yet verified`)}</div></fieldset>` +
    `<fieldset><legend>Order</legend><div class="chips">${chipLink(q.sort === 'gems', href(q, { sort: 'gems' }), 'Hidden gems first')}${chipLink(q.sort === 'newest', href(q, { sort: 'newest' }), 'Newest runs')}${chipLink(q.sort === 'name', href(q, { sort: 'name' }), 'A to Z')}</div></fieldset></details>` +
    `</form>`;
  const main =
    `<section class="head mat after-top"><div class="wrap head-row"><div><h1>Browse verified tools</h1>` +
    `<p class="lede">Every tool here was installed by pickfit in a fresh sandbox; every web app was opened and used in a sandboxed browser.</p></div>` +
    `${fitz('idle', 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap layout layout-browse"><aside class="side side-left">${filters}</aside><div>` +
    `<p class="cat-count"><span data-shown>${list.length}</span> of ${list.length} ${q.all ? 'tools' : 'verified tools'}${q.kind ? ` · ${esc(KIND_PLURAL[q.kind])}` : ''}${q.os ? ` · verified on ${esc(OS_NAME[q.os])}` : ''}</p>` +
    `<h2 class="sr">Tools</h2>` +
    (list.length
      ? `<ul class="cat-grid" data-grid>${list.map(card).join('')}</ul>` +
        (list.length > FIRST ? `<p class="pager js-only"><button type="button" class="btn btn-quiet" data-more>Show ${Math.min(FIRST, list.length - FIRST)} more</button></p>` : '')
      : '') +
    `<div class="empty"${list.length ? ' hidden' : ''} data-filter-empty>${fitz('sorry', 80)}<div><p><b>Nothing here fits that filter.</b></p><p class="quiet">Try fewer filters, or <a href="/">describe the job</a> and let Fitz look.</p></div></div>` +
    `</div></div>`;
  return renderShell({
    nonce,
    title: 'Browse verified tools · pickfit',
    description: 'Developer CLIs, local AI tools and MCP servers that pickfit installed and tested in a fresh sandbox.',
    active: 'browse',
    main,
  });
}
