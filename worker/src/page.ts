/**
 * The product web page's HTML: the search page, the results of one search and
 * short notices. Pure functions over find_software's and get_install_guide's
 * own outputs, so the page shows what an agent gets. Every value that comes
 * from the data or the model goes through esc(); links must be http(s).
 * Styles and the small script are inline and run under a per-response CSP
 * nonce; without the script the form still posts and the server renders.
 */
import type { Arch, Catalog, OS } from './catalog.ts';
import type { FindOutput, PickOut } from './find.ts';
import { PIPE_TO_SHELL, type InstallOutput } from './install.ts';

export interface FormValues {
  need: string;
  os: OS | '';
  arch: Arch | '';
  free_only: boolean;
  offline: boolean;
}

export const EMPTY_FORM: FormValues = { need: '', os: '', arch: '', free_only: false, offline: false };

/** One search: find_software's output and get_install_guide's for each pick (by slug). */
export interface SearchResult {
  out: FindOutput;
  guides: Record<string, InstallOutput>;
}

export interface CatalogStats {
  listed: number;
  replayed: number;
  byHand: number;
  gems: number;
}

export function catalogStats(catalog: Catalog): CatalogStats {
  const runs = (slug: string) => Object.values(catalog.bySlug.get(slug)!.install).map((guide) => guide!.run);
  return {
    listed: catalog.count,
    replayed: catalog.entries.filter((e) => runs(e.slug).some((r) => r.method === 'sandbox' && r.replayed)).length,
    byHand: catalog.entries.filter((e) => runs(e.slug).some((r) => r.method === 'human')).length,
    gems: catalog.entries.filter((e) => e.scores?.treasure).length,
  };
}

const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
}

/** Only http(s) URLs become links; anything else (javascript:, data:, garbage) is dropped. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
  } catch {
    return null;
  }
}

/** `text` must already be escaped. */
function link(url: string | null | undefined, text: string): string {
  const href = safeUrl(url);
  return href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>` : '';
}

const OS_NAME: Record<OS, string> = { macos: 'macOS', linux: 'Linux', windows: 'Windows' };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const osName = (os: OS | null | undefined) => (os ? OS_NAME[os] : 'an unknown OS');
const system = (os: OS | null, arch: Arch | null) => `${osName(os)}${arch ? ` ${arch}` : ''}`;

function day(iso: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : '';
}

/** What the verification level proves, as a short headline. */
export const LEVEL_LABEL: Record<string, string> = {
  install: 'Installs and starts',
  function: 'Its main function works',
  service: 'Its service answers requests',
  inference: 'It produces model output',
};

/** "pickfit installed it in a fresh Linux x86_64 sandbox and replayed the steps from scratch on 29 Oct 2026." */
export function ranSentence(v: PickOut['verification']): string {
  if (!v.os) return 'pickfit has no recorded run of its install steps.';
  const when = v.checked_at ? ` on ${day(v.checked_at)}` : '';
  const where = system(v.os, v.arch);
  if (v.method === 'human') return `pickfit installed it by hand on ${where}${when}.`;
  return v.replayed
    ? `pickfit installed it in a fresh ${where} sandbox and replayed the steps from scratch${when}.`
    : `pickfit installed it in a ${where} sandbox${when}.`;
}

/** The "your system" line: verified_on_user_os in words, including when it is not true. */
export function yourSystem(v: PickOut['verification'], form: FormValues): { state: 'yes' | 'no' | 'unknown'; text: string } {
  if (v.verified_on_user_os === true) {
    return {
      state: 'yes',
      text: form.arch
        ? `Verified on your system: it ran on ${system(v.os, v.arch)}.`
        : `Verified on your OS: it ran on ${system(v.os, v.arch)}.`,
    };
  }
  if (v.verified_on_user_os === false) {
    return {
      state: 'no',
      text:
        v.os === form.os && form.arch
          ? `Not verified on your system: it ran on ${system(v.os, v.arch)}, not ${form.arch}.`
          : `Not verified on your system: it ran on ${system(v.os, v.arch)}, and pickfit hasn’t run it on ${osName(form.os || null)} yet.`,
    };
  }
  return { state: 'unknown', text: 'Choose your OS above to see whether it ran on your system.' };
}

function facts(pick: PickOut): string {
  const items: string[] = [];
  items.push({ free: 'Free', freemium: 'Free tier, paid plans', paid: 'Paid', unknown: 'Price not known' }[pick.pricing]);
  if (pick.open_source === true) items.push(pick.license ? `Open source (${esc(pick.license)})` : 'Open source');
  if (pick.open_source === false) items.push('Not open source');
  const where = { local: 'Runs on your machine', cloud: 'Uses a cloud service', hybrid: 'Local and cloud', unknown: '' }[pick.processing];
  if (where) items.push(where);
  if (pick.platforms.length) items.push(`For ${listOf(pick.platforms.map((os) => OS_NAME[os]))}`);
  return `<ul class="facts">${items.map((item) => `<li>${item}</li>`).join('')}</ul>`;
}

function listOf(items: string[]): string {
  return items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

function command(text: string): string {
  return `<div class="cmd"><pre><code>${esc(text)}</code></pre><button type="button" class="copy">Copy</button></div>`;
}

/** The steps get_install_guide returns, for a person instead of an agent. */
export function installSection(guide: InstallOutput, form: FormValues, open: boolean): string {
  const v = guide.verification;
  if (guide.steps.length === 0) return '';
  const parts: string[] = [];
  const match = guide.applies_to_user_system.match;
  if (match === 'other_os' && form.os) {
    parts.push(
      `<p class="caution">These steps ran on ${esc(system(v.os, v.arch))}. pickfit hasn’t run them on ${esc(osName(form.os))}, so expect differences.</p>`,
    );
  } else if (match === 'same_os_other_arch' && form.arch) {
    parts.push(`<p class="caution">These steps ran on ${esc(system(v.os, v.arch))}, not ${esc(form.arch)}. A download may need the other build.</p>`);
  }
  const steps = guide.steps.map((step) => {
    const notes: string[] = [];
    if (step.needs_sudo) notes.push('Uses sudo.');
    if (PIPE_TO_SHELL.test(step.command)) notes.push('Runs a downloaded script: read it before you run it.');
    return (
      `<li>${step.purpose ? `<p>${esc(step.purpose)}</p>` : ''}${command(step.command)}` +
      `${notes.length ? `<p class="caution">${notes.join(' ')}</p>` : ''}</li>`
    );
  });
  parts.push(`<ol class="steps">${steps.join('')}</ol>`);
  if (guide.manual_steps.length) {
    parts.push(`<h5>You do these yourself</h5><ul>${guide.manual_steps.map((s) => `<li>${esc(s.title)}</li>`).join('')}</ul>`);
  }
  if (guide.verify) {
    parts.push(
      `<h5>Check that it works</h5>${command(guide.verify.command)}` +
        `<p class="quiet">The output should contain “${esc(guide.verify.expected_contains)}”.</p>`,
    );
  }
  if (guide.first_task) {
    const setup = guide.first_task_setup.map((s) => command(s.command)).join('');
    parts.push(`<h5>First thing to try</h5>${setup}${command(guide.first_task)}`);
  }
  // Pitfalls only the sandbox hit, or that the tool handled itself, are not the reader's problem.
  const issues = guide.known_issues.filter((i) => i.kind === 'readme_wrong' || i.kind === 'note' || !i.kind);
  if (issues.length) {
    parts.push(
      `<h5>Where the README and reality differ</h5><ul class="issues">${issues
        .map((i) => `<li><span class="quiet">README:</span> ${esc(i.readme_said)}<br><span class="quiet">What worked:</span> ${esc(i.actually_needed)}</li>`)
        .join('')}</ul>`,
    );
  }
  return (
    `<details class="install"${open ? ' open' : ''}><summary>Install steps that worked on ${esc(system(v.os, v.arch))}</summary>` +
    `<div class="install-body">${parts.join('')}</div></details>`
  );
}

function record(pick: PickOut, guide: InstallOutput | undefined, form: FormValues): string {
  const v = pick.verification;
  const mine = yourSystem(v, form);
  const offline = guide?.verification.works_offline;
  const q = pick.scores.quality === null ? 'not scored' : `${Math.round(pick.scores.quality)}/100`;
  const p = pick.scores.popularity === null ? 'not scored' : `${Math.round(pick.scores.popularity)}/100`;
  return (
    `<section class="record" aria-label="Test record">` +
    `<p class="level"><span class="tick" aria-hidden="true">✓</span> ${esc(LEVEL_LABEL[v.level] ?? v.level)}</p>` +
    `<p>${esc(ranSentence(v))}${offline === true ? ' Its checks passed again with the network off.' : ''}</p>` +
    `<p class="mine mine-${mine.state}">${mine.state === 'no' ? '<span aria-hidden="true">! </span>' : ''}${esc(mine.text)}</p>` +
    `<p class="quiet">Quality ${q}, popularity ${p}, scored separately.</p>` +
    `<details class="how"><summary>How we know</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

/** find.ts adds this tradeoff for agents when the run was on another system; the test record says it in full. */
const RAN_ELSEWHERE = /^Verified on \S+(?: \S+)? only; pickfit has not run its /;

function pickHtml(pick: PickOut, rank: number, result: SearchResult, form: FormValues): string {
  const { out } = result;
  const best = out.best_free?.slug === pick.slug ? out.best_free : null;
  const badges = [
    best ? '<span class="badge free">Best free option</span>' : '',
    pick.scores.treasure ? '<span class="badge gem" title="High quality, little known">Hidden gem</span>' : '',
  ].join('');
  const why = pick.why
    .map((r) => `<li>${esc(r.claim)}<span class="cite">From its profile: ${esc(r.field)} is “${esc(r.value)}”</span></li>`)
    .join('');
  const tradeoffs = pick.tradeoffs
    .filter((t) => !RAN_ELSEWHERE.test(t))
    .map((t) => `<li>${esc(t)}</li>`)
    .join('');
  const links = [
    link(pick.repo, 'Source code'),
    pick.homepage && pick.homepage !== pick.repo ? link(pick.homepage, 'Homepage') : '',
    link(pick.verification.os ? pick.evidence_url : null, 'Run record'),
  ].filter(Boolean);
  const guide = result.guides[pick.slug];
  return (
    `<article class="pick" id="pick-${esc(pick.slug)}">` +
    `<p class="rank" aria-hidden="true">${rank}</p>` +
    `<div class="pick-body">` +
    `<h3>${link(pick.repo, esc(pick.name)) || esc(pick.name)}</h3>${badges ? `<p class="badges">${badges}</p>` : ''}` +
    `<p class="summary">${esc(pick.summary)}</p>` +
    `<p class="fit">${esc(pick.fit)}</p>` +
    (why ? `<h4>Why it fits</h4><ul class="why">${why}</ul>` : '') +
    (tradeoffs ? `<h4>Tradeoffs</h4><ul class="tradeoffs">${tradeoffs}</ul>` : '') +
    (pick.vs_well_known ? `<p><span class="lead-in">Compared with better-known tools:</span> ${esc(pick.vs_well_known)}</p>` : '') +
    (best ? `<p><span class="lead-in">Best free option:</span> ${esc(best.reason)}</p>` : '') +
    facts(pick) +
    record(pick, guide, form) +
    (guide ? installSection(guide, form, rank === 1) : '') +
    (links.length ? `<p class="links">${links.join('')}</p>` : '') +
    `</div></article>`
  );
}

const DEGRADED: Record<string, { title: string; text: string }> = {
  over_budget: {
    title: 'Model matching is paused for today',
    text: "Today’s budget for Meta model calls from this page is used up, so these results are ranked by rules (words in your request, verification on your OS, treasure score) without Muse Spark. It resets at 00:00 UTC.",
  },
  budget_unavailable: {
    title: 'Ranked without the model this time',
    text: "pickfit couldn’t check its model budget, so it didn’t call Muse Spark and ranked these by rules. Search again in a minute.",
  },
  model_off: {
    title: 'Model matching is off on this server',
    text: 'These results are ranked by rules (words in your request, verification on your OS, treasure score).',
  },
};
DEGRADED.no_api_key = DEGRADED.model_off;
const MODEL_FAILED = {
  title: 'Ranked without the model this time',
  text: "Muse Spark didn’t return a usable answer, so these results are ranked by rules. Search again to retry.",
};

function matchLine(out: FindOutput): string {
  const n = out.picks.length;
  const chose = n === 0 ? 'found none that fits' : `picked ${n === 1 ? 'one' : n}`;
  if (out.matched_by === 'rules') {
    return `Ranked by rules among the ${out.considered} verified tools that meet your conditions; no model was used.`;
  }
  return (
    `Meta’s ${esc(out.matched_by)} compared the ${out.considered} verified tools that meet your conditions and ${chose}. ` +
    'Code checked every reason against the tool’s profile.'
  );
}

/** The results area for one search. `catalog` names a best free option that is not among the picks. */
export function renderResults(result: SearchResult, form: FormValues, catalog: Catalog, opts: { cached?: boolean } = {}): string {
  const { out } = result;
  const parts: string[] = [];
  if (out.degraded) {
    const d = DEGRADED[out.degraded_reason ?? ''] ?? MODEL_FAILED;
    parts.push(`<div class="notice busy" role="status"><h2>${esc(d.title)}</h2><p>${esc(d.text)}</p></div>`);
  }
  if (out.considered > 0) parts.push(`<p class="match-line">${matchLine(out)}</p>`);
  if (out.clarifying_question) {
    parts.push(`<p class="ask"><span class="lead-in">To narrow it down:</span> ${esc(out.clarifying_question)} Set it above and search again.</p>`);
  }
  if (out.picks.length === 0) {
    parts.push(
      `<div class="empty"><h2>No verified tool fits this yet</h2><p>${esc(
        out.coverage_note ?? 'pickfit covers developer CLI tools and local AI tools today.',
      )}</p></div>`,
    );
  } else {
    parts.push(`<div class="picks">${out.picks.map((pick, i) => pickHtml(pick, i + 1, result, form)).join('')}</div>`);
    if (out.coverage_note) parts.push(`<p class="quiet">${esc(out.coverage_note)}</p>`);
  }
  const free = out.best_free && !out.picks.some((p) => p.slug === out.best_free!.slug) ? catalog.bySlug.get(out.best_free.slug) : undefined;
  if (free && out.best_free) {
    parts.push(
      `<p class="aside"><span class="lead-in">Best free option among the verified tools:</span> ` +
        `${link(free.repo_url, esc(free.name)) || esc(free.name)}. ${esc(out.best_free.reason)}</p>`,
    );
  }
  if (out.no_install_option) {
    parts.push(
      `<div class="aside"><h3>You may not need to install anything</h3><p>${esc(out.no_install_option)}</p>` +
        `<p class="quiet">From Muse Spark’s general knowledge; pickfit hasn’t checked it.</p></div>`,
    );
  }
  const wk = out.well_known_option;
  if (wk) {
    parts.push(
      `<aside class="outside" aria-label="Not verified by pickfit"><p class="unverified">Not verified by pickfit</p>` +
        `<h3>Also consider ${esc(wk.name)}</h3><p>${esc(wk.why)}</p><p class="quiet">${esc(wk.how_we_know)}</p></aside>`,
    );
  }
  if (opts.cached) parts.push('<p class="quiet small">Shown from the same search made in the last few minutes.</p>');
  return parts.join('');
}

export function renderNotice(kind: 'busy' | 'error', title: string, text: string): string {
  return `<div class="notice ${kind}" role="${kind === 'error' ? 'alert' : 'status'}"><h2>${esc(title)}</h2><p>${esc(text)}</p></div>`;
}

/** Examples on the page: tasks the catalog covers, written for this page. */
export const EXAMPLES = [
  'Turn a folder of interview recordings into subtitles, offline',
  'Check my MCP server configs for risky permissions before I install one',
  'Find the fastest GGUF quantization that still works well on my GPU',
  'See which process holds port 3000 and stop it',
];

const SELECT = {
  os: [
    ['', 'Any OS'],
    ['macos', 'macOS'],
    ['linux', 'Linux'],
    ['windows', 'Windows'],
  ],
  arch: [
    ['', 'Any CPU'],
    ['arm64', 'arm64 (Apple silicon, ARM)'],
    ['x86_64', 'x86_64 (Intel, AMD)'],
  ],
} as const;

function select(name: 'os' | 'arch', value: string, label: string): string {
  const options = SELECT[name].map(([v, text]) => `<option value="${v}"${v === value ? ' selected' : ''}>${text}</option>`).join('');
  return `<select name="${name}" aria-label="${label}">${options}</select>`;
}

export interface PageInput {
  nonce: string;
  /** This deployment's origin, for the MCP URL. */
  origin: string;
  stats: CatalogStats;
  form: FormValues;
  /** Rendered results or a notice; empty before the first search. */
  results: string;
}

const MARK =
  '<svg class="mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="2" width="28" height="28" rx="9"/>' +
  '<path d="M9.5 16.5l4.4 4.4L22.5 11.5"/></svg>';
const ICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='2' y='2' width='28' height='28' rx='9' fill='%2316213A'/%3E" +
  "%3Cpath d='M9.5 16.5l4.4 4.4L22.5 11.5' fill='none' stroke='%23F2C12E' stroke-width='3.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E";

export function renderPage(input: PageInput): string {
  const { form, stats, nonce } = input;
  const mcp = `${input.origin}/mcp`;
  const byHand = stats.byHand ? ` ${stats.byHand} were installed by hand on a real machine.` : '';
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pickfit: software that fits, installed and tested first</title>
<meta name="description" content="Describe what you need. pickfit suggests lesser-known developer CLI tools and local AI tools it has installed and tested, with the evidence and the steps that worked.">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="${ICON}">
<style nonce="${nonce}">${CSS}</style>
</head>
<body>
<header class="top wrap">
<a class="brand" href="/">${MARK}<span>pickfit</span></a>
<nav aria-label="Page"><a href="#how">How it works</a><a href="#agents">For agents</a></nav>
</header>
<main>
<section class="hero wrap">
<h1>Software that fits your job, installed and tested before we suggest it.</h1>
<p class="lede">Describe what you need in one sentence. pickfit looks through lesser-known developer CLI tools and local AI tools it has installed itself, asks Meta’s Muse Spark which ones fit you, and shows the evidence and the exact steps that worked.</p>
<form id="search" class="search" method="post" action="/search">
<div class="need">
<label for="need">I need</label>
<textarea id="need" name="need" rows="1" minlength="3" maxlength="500" required autocomplete="off" spellcheck="true" placeholder="a free way to transcribe meeting recordings offline">${esc(form.need)}</textarea>
</div>
<div class="filters">
<span class="filters-label">Runs on</span>
${select('os', form.os, 'Operating system')}
${select('arch', form.arch, 'CPU architecture')}
<label class="check"><input type="checkbox" name="free_only" value="1"${form.free_only ? ' checked' : ''}> Free only</label>
<label class="check"><input type="checkbox" name="offline" value="1"${form.offline ? ' checked' : ''}> Works offline</label>
<button type="submit" class="go">Find software</button>
</div>
</form>
<div class="examples"><span class="quiet">Try one:</span>${EXAMPLES.map((e) => `<button type="button" data-need="${esc(e)}">${esc(e)}</button>`).join('')}</div>
</section>
<p id="status" class="sr" aria-live="polite"></p>
<section id="results" class="results wrap" tabindex="-1" aria-label="Results">${input.results}</section>
<section id="how" class="how-it-works wrap">
<h2>How pickfit knows</h2>
<ol class="flow">
<li><h3>Find</h3><p>Agents scan new GitHub projects. Meta’s Muse Spark reads each README and writes a profile: what the tool does, where it runs, what it costs, whether it works offline.</p></li>
<li><h3>Install</h3><p>A verification agent installs each tool in a fresh sandbox, fixes what the README got wrong, checks that the tool really works, then replays the steps from scratch.</p></li>
<li><h3>Match</h3><p>Your sentence and every profile that meets your conditions go to Muse Spark in one call. Code then checks each reason against the profile and drops the ones that don’t hold.</p></li>
<li><h3>Hand over</h3><p>You get the steps that worked, where they ran, and what you’ll have to do by hand.</p></li>
</ol>
<p class="stats">pickfit lists ${stats.listed} tools today. ${stats.replayed} of them were installed and replayed in a fresh sandbox, and ${stats.gems} are hidden gems: high quality, little known.${byHand} Only verified tools are suggested.</p>
</section>
<section id="agents" class="agents wrap">
<h2>The same answers inside your coding agent</h2>
<p>Agents get the same data and the same matching through MCP. Add pickfit to Claude Code:</p>
${command(`claude mcp add --transport http pickfit ${mcp}`)}
<p class="quiet">Any MCP client that speaks streamable HTTP can connect to <code>${esc(mcp)}</code>.</p>
</section>
</main>
<footer class="foot wrap">
<p>pickfit ranks by fit, not stars. No ads, no paid placement, no referral links, and it doesn’t make any of the software it suggests.</p>
<p>No account and no IP address stored. Your sentence goes to Meta’s Muse Spark with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS.</p>
</footer>
<template id="loading"><div class="loading" role="status"><div class="bar" aria-hidden="true"></div><h2>Matching your need</h2><ol><li>Keep the verified tools that meet your OS, price and offline conditions</li><li>Muse Spark reads every remaining profile and picks the best fits</li><li>Code checks each reason against the profile</li></ol><p class="quiet">Usually 5 to 15 seconds.</p></div></template>
<template id="offline"><div class="notice error" role="alert"><h2>Couldn’t reach pickfit</h2><p>Check your connection and search again.</p></div></template>
<script nonce="${nonce}">${SCRIPT}</script>
</body>
</html>`;
}

const CSS = `
:root{--paper:#F3F5F7;--sheet:#FFFFFF;--ink:#16213A;--quiet:#56627A;--rule:#D3DAE4;--tape:#F2C12E;--tape-ink:#16213A;
--pass:#17754A;--pass-soft:#E3F2EA;--caution:#8A4B08;--caution-soft:#FCF0DC;--code:#111A2E;--code-ink:#E8EDF5;
--serif:Charter,"Bitstream Charter","Iowan Old Style","Sitka Text",Cambria,Georgia,serif;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){:root{--paper:#0E1525;--sheet:#152036;--ink:#E7ECF4;--quiet:#9CA8BE;--rule:#2B3754;
--pass:#62CC98;--pass-soft:#123020;--caution:#F0B45A;--caution-soft:#33260E;--code:#0A1020;--code-ink:#E8EDF5}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 var(--sans);overflow-wrap:break-word}
.wrap{max-width:780px;margin:0 auto;padding:0 20px}
a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{text-decoration-color:var(--tape);text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--tape);outline-offset:2px;border-radius:4px}
h1,h2,h3,.need label,.need textarea,.rank{font-family:var(--serif);font-weight:600;letter-spacing:-.01em}
h1{font-size:clamp(30px,5.4vw,44px);line-height:1.12;margin:0 0 16px;max-width:22ch}
h2{font-size:24px;line-height:1.25;margin:0 0 10px}
h3{font-size:21px;line-height:1.3;margin:0}
h4{font:600 15px/1.4 var(--sans);margin:18px 0 6px}
h5{font:600 14px/1.4 var(--sans);margin:16px 0 6px}
p{margin:0 0 10px}
ul,ol{margin:0 0 10px;padding-left:20px}
code{font-family:var(--mono);font-size:.92em}
.quiet{color:var(--quiet)}.small{font-size:14px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:18px;padding-bottom:18px}
.brand{display:inline-flex;align-items:center;gap:9px;text-decoration:none;font:700 21px/1 var(--sans);letter-spacing:-.02em}
.mark{width:28px;height:28px}.mark rect{fill:var(--ink)}.mark path{fill:none;stroke:var(--tape);stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}
.top nav{display:flex;gap:18px;font-size:15px}.top nav a{text-decoration:none;color:var(--quiet)}.top nav a:hover{color:var(--ink)}
.hero{padding-top:36px;padding-bottom:28px}
.lede{font-size:18px;color:var(--quiet);max-width:62ch;margin-bottom:28px}
.need{display:flex;align-items:baseline;gap:14px;border-bottom:4px solid var(--tape);padding-bottom:6px}
.need label{font-size:clamp(23px,3.6vw,30px);color:var(--quiet);white-space:nowrap}
.need textarea{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font-size:clamp(23px,3.6vw,30px);line-height:1.3;resize:none;padding:0;overflow:hidden;font-weight:500}
.need textarea::placeholder{color:var(--quiet);opacity:.55}
.need textarea:focus-visible{outline:none}
.need:focus-within{border-bottom-color:var(--ink)}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin-top:16px;font-size:15px}
.filters-label{color:var(--quiet)}
select{font:inherit;color:var(--ink);background:var(--sheet);border:1px solid var(--rule);border-radius:8px;padding:7px 10px;max-width:100%}
.check{display:inline-flex;align-items:center;gap:7px;cursor:pointer;min-height:36px}
.check input{width:18px;height:18px;accent-color:var(--ink);margin:0}
.go{margin-left:auto;font:600 16px/1 var(--sans);color:var(--paper);background:var(--ink);border:0;border-radius:10px;padding:13px 20px;cursor:pointer;touch-action:manipulation}
.go:hover{background:color-mix(in srgb,var(--ink) 86%,var(--tape))}
.go:disabled{opacity:.6;cursor:progress}
.examples{display:none;flex-wrap:wrap;align-items:baseline;gap:6px 14px;margin-top:22px;font-size:15px}
.js .examples{display:flex}
.examples button{font:inherit;color:var(--ink);background:none;border:0;padding:2px 0;cursor:pointer;text-align:left;text-decoration:underline;text-decoration-color:var(--rule);text-underline-offset:4px}
.examples button:hover{text-decoration-color:var(--tape)}
.results{scroll-margin-top:12px;padding-bottom:12px}
.results:focus{outline:none}
.match-line{color:var(--quiet);border-top:1px solid var(--rule);padding-top:22px;margin-top:8px}
.ask,.aside{background:var(--sheet);border-radius:12px;padding:14px 18px;margin:16px 0}
.aside h3{font-size:18px;margin-bottom:6px}
.lead-in{font-weight:600}
.pick{display:grid;grid-template-columns:52px minmax(0,1fr);gap:0 8px;padding:26px 0 22px;border-bottom:1px solid var(--rule)}
.rank{font-size:40px;line-height:1;color:var(--quiet);margin:0}
.pick h3{font-size:26px}
.pick h3 a{text-decoration-color:var(--rule)}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 0}
.badge{font:600 13px/1 var(--sans);padding:6px 10px;border-radius:999px}
.badge.free{background:var(--pass-soft);color:var(--pass)}
.badge.gem{background:var(--tape);color:var(--tape-ink)}
.summary{color:var(--quiet);margin-top:8px}
.fit{font-size:19px;line-height:1.5;margin:12px 0 4px;max-width:62ch}
.why{list-style:none;padding:0}
.why li{position:relative;padding-left:22px;margin-bottom:8px}
.why li::before{content:"✓";position:absolute;left:0;color:var(--pass);font-weight:700}
.cite{display:block;font-size:13.5px;color:var(--quiet)}
.tradeoffs li{margin-bottom:4px}
.facts{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0;margin:14px 0}
.facts li{font-size:14px;border:1px solid var(--rule);border-radius:999px;padding:3px 10px}
.record{background:var(--sheet);border:1px solid var(--rule);border-radius:14px;padding:16px 18px;margin:16px 0 12px}
.record p{margin-bottom:6px}
.level{font-weight:600;font-size:17px}
.tick{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--pass);color:var(--sheet);font-size:13px;margin-right:4px;vertical-align:1px}
.mine{padding:8px 12px;border-radius:8px;font-weight:500}
.mine-yes{background:var(--pass-soft);color:var(--pass)}
.mine-no{background:var(--caution-soft);color:var(--caution)}
.mine-unknown{border:1px dashed var(--rule);color:var(--quiet)}
.how summary,.install summary{cursor:pointer;font-weight:600}
.how summary{font-size:14px;color:var(--quiet);font-weight:500}
.how p{font-size:14px;color:var(--quiet);margin-top:6px}
.install{margin:10px 0 6px}
.install summary{padding:6px 0}
.install-body{padding:4px 0 2px}
.steps{padding-left:22px}.steps li{margin-bottom:12px}.steps li p{margin-bottom:6px}
.caution{color:var(--caution);font-size:14.5px}
.cmd{display:flex;align-items:flex-start;background:var(--code);color:var(--code-ink);border-radius:10px;margin:6px 0 8px;min-width:0}
.cmd pre{flex:1;min-width:0;margin:0;padding:11px 14px;overflow-x:auto;font:13.5px/1.55 var(--mono);white-space:pre}
.cmd code{font-size:inherit}
.copy{display:none;flex:none;font:600 13px/1 var(--sans);color:var(--code-ink);background:transparent;border:1px solid color-mix(in srgb,var(--code-ink) 30%,transparent);border-radius:7px;padding:6px 9px;margin:7px 7px 0 0;cursor:pointer}
.js .copy{display:inline-block}
.copy:hover{border-color:var(--tape);color:var(--tape)}
.issues li{margin-bottom:8px}
.links{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:15px;margin-top:8px}
.outside{border:1.5px dashed var(--rule);border-radius:14px;padding:16px 18px;margin:22px 0;color:var(--quiet)}
.outside h3{font-size:19px;color:var(--ink);margin-bottom:6px}
.unverified{display:inline-block;font:600 13px/1 var(--sans);color:var(--caution);border:1px solid currentColor;border-radius:999px;padding:5px 10px;margin-bottom:10px}
.notice,.empty,.loading{border-radius:14px;padding:18px 20px;margin:20px 0;background:var(--sheet)}
.notice h2,.empty h2,.loading h2{font-size:21px}
.notice.busy{background:var(--caution-soft)}
.notice.busy h2,.notice.error h2{color:var(--caution)}
.loading ol{color:var(--quiet);padding-left:20px}
.bar{height:4px;border-radius:2px;background:var(--rule);overflow:hidden;margin-bottom:14px;position:relative}
.bar::after{content:"";position:absolute;inset:0;width:35%;background:var(--tape);border-radius:2px;animation:slide 1.3s ease-in-out infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(290%)}}
@media (prefers-reduced-motion:reduce){.bar::after{animation:none;width:100%}}
.how-it-works{padding-top:48px}
.flow{list-style:none;padding:0;counter-reset:step;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px 28px;margin:18px 0}
.flow li{counter-increment:step}
.flow h3{font-size:19px;margin-bottom:4px}
.flow h3::before{content:counter(step) ". ";color:var(--quiet)}
.flow p{color:var(--quiet);font-size:15px}
.stats{border-left:4px solid var(--tape);padding-left:14px;max-width:62ch}
.agents{padding-top:36px}
.foot{padding-top:40px;padding-bottom:48px;color:var(--quiet);font-size:14.5px}
.foot p{max-width:68ch}
@media (max-width:640px){
.wrap{padding:0 16px}
.top nav{gap:14px;font-size:14px}
.hero{padding-top:20px}
.lede{font-size:16.5px}
.need{flex-direction:column;gap:2px}
.go{margin-left:0;width:100%}
.filters select{flex:1 1 40%}
.pick{grid-template-columns:32px minmax(0,1fr)}
.rank{font-size:28px}
.pick h3{font-size:23px}
.flow{grid-template-columns:minmax(0,1fr)}
}
`;

const SCRIPT = `
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const form = document.getElementById('search');
  const need = form.elements.need;
  const go = form.querySelector('.go');
  const out = document.getElementById('results');
  const status = document.getElementById('status');
  const grow = () => { need.style.height = 'auto'; need.style.height = need.scrollHeight + 'px'; };
  grow();
  need.addEventListener('input', grow);
  addEventListener('resize', grow);
  // Enter searches; Shift+Enter is a new line; never while an IME is composing.
  need.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  // Before the first search, preselect the visitor's desktop OS.
  if (!out.firstElementChild && !form.elements.os.value) {
    const ua = navigator.userAgent;
    const os = /Android|iPhone|iPad/.test(ua) ? '' : /Mac/.test(ua) ? 'macos' : /Windows/.test(ua) ? 'windows' : /Linux/.test(ua) ? 'linux' : '';
    form.elements.os.value = os;
  }
  let busy = false;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    go.disabled = true;
    go.textContent = 'Finding…';
    status.textContent = 'Searching';
    out.setAttribute('aria-busy', 'true');
    out.replaceChildren(document.getElementById('loading').content.cloneNode(true));
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (out.getBoundingClientRect().top > innerHeight * 0.6) out.scrollIntoView({ behavior: still ? 'auto' : 'smooth' });
    try {
      const res = await fetch(form.action, { method: 'POST', body: new URLSearchParams(new FormData(form)), headers: { 'x-pickfit-fragment': '1' } });
      if (!(res.headers.get('content-type') || '').startsWith('text/html') || res.status >= 500) throw new Error(String(res.status));
      out.innerHTML = await res.text();
      const n = out.querySelectorAll('.pick').length;
      status.textContent = n ? n + (n === 1 ? ' result' : ' results') : 'No results';
    } catch {
      out.replaceChildren(document.getElementById('offline').content.cloneNode(true));
      status.textContent = 'Search failed';
    } finally {
      busy = false;
      go.disabled = false;
      go.textContent = 'Find software';
      out.removeAttribute('aria-busy');
      out.focus({ preventScroll: true });
    }
  });
  for (const b of document.querySelectorAll('[data-need]')) {
    b.addEventListener('click', () => { need.value = b.dataset.need; grow(); form.requestSubmit(); });
  }
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('.copy');
    if (!b) return;
    try { await navigator.clipboard.writeText(b.parentElement.querySelector('code').textContent); b.textContent = 'Copied'; }
    catch { b.textContent = 'Select to copy'; }
    setTimeout(() => { b.textContent = 'Copy'; }, 1600);
  });
})();
`;
