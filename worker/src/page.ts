/**
 * The product web page's HTML: the search page, the results of one search and
 * short notices. Pure functions over find_software's and get_install_guide's
 * own outputs (and, before a search, the catalog itself), so the page shows
 * what an agent gets. Every value that comes from the data or the model goes
 * through esc(); links must be http(s). Styles and the small script are inline
 * and run under a per-response CSP nonce; without the script the form still
 * posts and the server renders.
 *
 * Design (notes: web-page-design-brief.md): the run record pickfit writes when
 * it installs a tool is the slip every recommendation is printed on. A pick's
 * claim sits on the left, its evidence on the right; a tool pickfit has not
 * verified gets no slip at all.
 */
import { toCard } from './cards.ts';
import { bestGuide, verifiedOnUserSystem, type Arch, type Catalog, type Entry, type InstallGuide, type OS } from './catalog.ts';
import type { FindOutput, PickOut } from './find.ts';
import { PIPE_TO_SHELL, type InstallOutput } from './install.ts';
import { templateReasons } from './rules.ts';

export interface FormValues {
  need: string;
  os: OS | '';
  arch: Arch | '';
  free_only: boolean;
  offline: boolean;
}

export const EMPTY_FORM: FormValues = { need: '', os: '', arch: '', free_only: false, offline: false };

/** Why the web page did not ask the model: its daily share, the total cap, or no way to count spend. */
export type BudgetStop = 'web_daily' | 'total' | 'unavailable';

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

const runsOf = (entry: Entry) => Object.values(entry.install).map((guide) => guide!.run);

export function catalogStats(catalog: Catalog): CatalogStats {
  return {
    listed: catalog.count,
    replayed: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'sandbox' && r.replayed)).length,
    byHand: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'human')).length,
    gems: catalog.entries.filter((e) => e.scores?.treasure).length,
  };
}

/** What the page shows before any search, all read from the catalog: no model call, nothing invented. */
export interface Showcase {
  stats: CatalogStats;
  /** The newest hidden gem whose run found something the README got wrong (else the newest run). */
  featured: { entry: Entry; guide: InstallGuide } | null;
  /** Another hidden gem whose README the run corrected, for the runs section. */
  fix: { entry: Entry; guide: InstallGuide } | null;
  /** The newest runs, one per tool. */
  recent: { entry: Entry; guide: InstallGuide }[];
}

/** Pitfalls that matter to a reader: not the ones only the sandbox hit or the tool fixed itself. */
const readerIssues = <T extends { kind?: string | null }>(issues: T[]) =>
  issues.filter((i) => i.kind === 'readme_wrong' || i.kind === 'note' || !i.kind);

export function catalogShowcase(catalog: Catalog, recentCount = 6): Showcase {
  const runs = catalog.entries
    .flatMap((entry) => {
      const guide = bestGuide(entry);
      return guide ? [{ entry, guide }] : [];
    })
    .sort((a, b) => b.guide.run.checked_at.localeCompare(a.guide.run.checked_at) || a.entry.slug.localeCompare(b.entry.slug));
  const corrected = runs.filter((r) => r.entry.scores?.treasure && readerIssues(r.guide.pitfalls).length > 0 && r.guide.steps.length > 0);
  const featured = corrected[0] ?? runs[0] ?? null;
  const fix = corrected.find((r) => r !== featured) ?? null;
  return { stats: catalogStats(catalog), featured, fix, recent: runs.slice(0, recentCount) };
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
const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const SHORT_DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });

export const osName = (os: OS | null | undefined) => (os ? OS_NAME[os] : 'an unknown OS');
const system = (os: OS | null, arch: Arch | null) => `${osName(os)}${arch ? ` ${arch}` : ''}`;

function day(iso: string | null, format = DAY): string {
  const date = new Date(iso ?? '');
  return Number.isNaN(date.getTime()) ? '' : format.format(date);
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

const CHECK = '<svg class="check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 8.6l3 3 6.6-7.2"/></svg>';

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
  return `<div class="cmd"><pre translate="no"><code>${esc(text)}</code></pre><button type="button" class="copy">Copy</button></div>`;
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
  const issues = readerIssues(guide.known_issues);
  if (issues.length) {
    parts.push(
      `<h5>Where the README and reality differ</h5><ul class="issues" data-ui>${issues
        .map((i) => `<li><span class="quiet">README:</span> ${esc(i.readme_said)}<br><span class="quiet">What worked:</span> ${esc(i.actually_needed)}</li>`)
        .join('')}</ul>`,
    );
  }
  return (
    `<details class="install"${open ? ' open' : ''}><summary>Install steps that worked on ${esc(system(v.os, v.arch))}</summary>` +
    `<div class="install-body">${parts.join('')}</div></details>`
  );
}

/** The run-record slip: the evidence half of a pick. */
function record(pick: PickOut, guide: InstallOutput | undefined, form: FormValues): string {
  const v = pick.verification;
  const mine = yourSystem(v, form);
  const offline = guide?.verification.works_offline;
  const offlineLine =
    offline === true
      ? ' Its checks passed again with the network off.'
      : offline === false
        ? ' Its checks failed with the network off: it needed the network in pickfit’s run.'
        : form.offline
          ? ' pickfit hasn’t checked it with the network off.'
          : '';
  const q = pick.scores.quality === null ? 'not scored' : `${Math.round(pick.scores.quality)}/100`;
  const p = pick.scores.popularity === null ? 'not scored' : `${Math.round(pick.scores.popularity)}/100`;
  return (
    `<section class="record" aria-label="Test record" data-ui>` +
    `<p class="level">${CHECK}${esc(LEVEL_LABEL[v.level] ?? v.level)}</p>` +
    `<p>${esc(ranSentence(v) + offlineLine)}</p>` +
    `<p class="mine mine-${mine.state}">${esc(mine.text)}</p>` +
    `<p class="quiet">Quality ${q}, popularity ${p}, scored separately.</p>` +
    `<details class="how"><summary>How we know</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

/** find.ts adds this tradeoff for agents when the run was on another system; the test record says it in full. */
const RAN_ELSEWHERE = /^Verified on \S+(?: \S+)? only; pickfit has not run its /;

function pickHtml(pick: PickOut, first: boolean, result: SearchResult, form: FormValues): string {
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
    `<div class="claim">` +
    `<h3>${link(pick.repo, esc(pick.name)) || esc(pick.name)}</h3>${badges ? `<p class="badges">${badges}</p>` : ''}` +
    `<p class="summary">${esc(pick.summary)}</p>` +
    `<p class="fit">${esc(pick.fit)}</p>` +
    (why ? `<h4>Why it fits</h4><ul class="why">${why}</ul>` : '') +
    (tradeoffs ? `<h4>Tradeoffs</h4><ul class="tradeoffs">${tradeoffs}</ul>` : '') +
    (pick.vs_well_known ? `<p><span class="lead-in">Compared with better-known tools:</span> ${esc(pick.vs_well_known)}</p>` : '') +
    (best ? `<p><span class="lead-in">Best free option:</span> ${esc(best.reason)}</p>` : '') +
    facts(pick) +
    `</div><div class="evidence">` +
    record(pick, guide, form) +
    (guide ? installSection(guide, form, first) : '') +
    (links.length ? `<p class="links">${links.join('')}</p>` : '') +
    `</div></article>`
  );
}

const BY_RULES = 'these results are ranked by rules (words in your request, verification on your OS, treasure score) without Muse Spark';
const BUDGET: Record<BudgetStop | 'other', { title: string; text: string }> = {
  web_daily: {
    title: 'Model matching paused until 00:00 UTC',
    text: `Today’s Meta spend, by this page and by agents together, has reached the share this page may use, so ${BY_RULES}.`,
  },
  total: {
    title: 'Model matching is paused',
    text: `pickfit’s overall budget for Meta model calls is used up, so ${BY_RULES}.`,
  },
  unavailable: {
    title: 'Ranked without the model this time',
    text: `pickfit couldn’t check its model budget, so it didn’t call Muse Spark: ${BY_RULES}. Search again in a minute.`,
  },
  other: {
    title: 'Model matching is paused for now',
    text: `pickfit’s budget for Meta model calls is used up for now, so ${BY_RULES}.`,
  },
};

const DEGRADED: Record<string, { title: string; text: string }> = {
  budget_unavailable: {
    title: 'Ranked without the model this time',
    text: 'pickfit couldn’t check its model budget, so it didn’t call Muse Spark and ranked these by rules. Search again in a minute.',
  },
  model_off: {
    title: 'Model matching is off on this server',
    text: 'These results are ranked by rules (words in your request, verification on your OS, treasure score).',
  },
};
DEGRADED.no_api_key = DEGRADED.model_off;
const MODEL_FAILED = {
  title: 'Ranked without the model this time',
  text: 'Muse Spark didn’t return a usable answer, so these results are ranked by rules. Search again to retry.',
};

/** The results heading says what came back, in words. */
function resultsTitle(out: FindOutput): string {
  const n = out.picks.length;
  if (n === 0) return 'Nothing fits yet';
  const tools = `${n} ${n === 1 ? 'tool' : 'tools'}`;
  return out.matched_by === 'rules' ? `${tools} ranked by rules` : `${tools} ${n === 1 ? 'fits' : 'fit'} your need`;
}

function matchLine(out: FindOutput): string {
  const n = out.picks.length;
  const meet = `${out.considered} verified ${out.considered === 1 ? 'tool meets' : 'tools meet'} your conditions`;
  if (out.matched_by === 'rules') return `${meet}; these are ranked by rules, without a model.`;
  // When more than the card limit meet them, coverage_note says how many the model compared.
  return (
    `${meet}; Meta’s ${esc(out.matched_by)} ${n === 0 ? 'found none that fits' : `picked ${n === 1 ? 'one' : n}`}.` +
    (n ? ' Code checked every reason against the tool’s profile.' : '')
  );
}

/** The results area for one search. `catalog` names a best free option that is not among the picks. */
export function renderResults(
  result: SearchResult,
  form: FormValues,
  catalog: Catalog,
  opts: { cached?: boolean; budget?: BudgetStop | null } = {},
): string {
  const { out } = result;
  const parts: string[] = [];
  if (out.degraded) {
    const d = out.degraded_reason === 'over_budget' ? BUDGET[opts.budget ?? 'other'] : (DEGRADED[out.degraded_reason ?? ''] ?? MODEL_FAILED);
    parts.push(`<div class="notice busy" role="status"><h2>${esc(d.title)}</h2><p>${esc(d.text)}</p></div>`);
  }
  const head: string[] = [`<h2 class="results-title">${esc(resultsTitle(out))}</h2>`];
  if (out.considered > 0) head.push(`<p class="match-line">${matchLine(out)}</p>`);
  if (out.picks.length === 0) {
    head.push(`<p class="match-line">${esc(out.coverage_note ?? 'pickfit covers developer CLI tools and local AI tools today.')}</p>`);
  }
  if (out.clarifying_question) {
    parts.push(`<p class="ask"><span class="lead-in">To narrow it down:</span> ${esc(out.clarifying_question)} Set it above and search again.</p>`);
  }
  // "Built-in is enough" is said before anything is sold.
  if (out.no_install_option) {
    parts.push(
      `<div class="aside"><h3>You may not need to install anything</h3><p>${esc(out.no_install_option)}</p>` +
        `<p class="quiet">From Muse Spark’s general knowledge; pickfit hasn’t checked it.</p></div>`,
    );
  }
  if (out.picks.length) {
    parts.push(`<div class="picks">${out.picks.map((pick, i) => pickHtml(pick, i === 0, result, form)).join('')}</div>`);
    if (out.coverage_note) parts.push(`<p class="quiet">${esc(out.coverage_note)}</p>`);
  }
  const free = out.best_free && !out.picks.some((p) => p.slug === out.best_free!.slug) ? catalog.bySlug.get(out.best_free.slug) : undefined;
  if (free && out.best_free) {
    const guide = bestGuide(free, form.os || undefined);
    const v: PickOut['verification'] = {
      level: guide?.run.level ?? free.verification.level,
      os: guide?.run.os ?? null,
      arch: guide?.run.arch ?? null,
      method: guide?.run.method ?? null,
      replayed: guide?.run.replayed ?? false,
      checked_at: guide?.run.checked_at ?? null,
      verified_on_user_os: verifiedOnUserSystem(free, form.os || undefined, form.arch || undefined),
    };
    const mine = yourSystem(v, form);
    parts.push(
      `<div class="aside best-free"><p><span class="lead-in">Best free option:</span> ` +
        `${link(free.repo_url, esc(free.name)) || esc(free.name)}. ${esc(out.best_free.reason)}</p>` +
        `<p class="quiet">${esc(ranSentence(v))}</p><p class="mine mine-${mine.state}">${esc(mine.text)}</p></div>`,
    );
  }
  // Not verified: no slip, no badge, no steps, no link. The missing record is the label.
  const wk = out.well_known_option;
  const outside = wk
    ? `<aside class="outside" aria-label="Not verified by pickfit">` +
      `<h3>Also consider ${esc(wk.name)}, not verified by pickfit</h3>` +
      `<p class="unchecked">pickfit has not installed or tested it. There is no run record and no install guide.</p>` +
      `<p>${esc(wk.why)}</p><p class="quiet">${esc(wk.how_we_know)}</p></aside>`
    : '';
  if (outside && out.picks.length === 0) {
    // Nothing fits: the note on the left, the unverified option beside it.
    parts.splice(out.degraded ? 1 : 0, 0, `<div class="nofit"><div>${head.join('')}</div>${outside}</div>`);
  } else {
    parts.splice(out.degraded ? 1 : 0, 0, ...head);
    if (outside) parts.push(outside);
  }
  if (opts.cached) parts.push('<p class="quiet">Shown from the same search made in the last few minutes.</p>');
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
    ['arm64', 'ARM64, Apple silicon'],
    ['x86_64', 'x86-64, Intel or AMD'],
  ],
} as const;

function select(name: 'os' | 'arch', value: string, label: string): string {
  const options = SELECT[name].map(([v, text]) => `<option value="${v}"${v === value ? ' selected' : ''}>${text}</option>`).join('');
  return `<select name="${name}" aria-label="${label}">${options}</select>`;
}

const KIND: Record<string, string> = { dev_cli: 'Developer CLI', local_ai: 'Local AI', other: 'Other' };

/** The hero's frame: one real run record, as the slip pickfit prints. */
function heroRecord(featured: Showcase['featured']): string {
  if (!featured) return '';
  const { entry, guide } = featured;
  const r = guide.run;
  const how = r.method === 'human' ? `Installed by hand on ${system(r.os, r.arch)}` : `Installed in a fresh ${system(r.os, r.arch)} sandbox${r.replayed ? ', replayed from scratch' : ''}`;
  const issue = readerIssues(guide.pitfalls)[0];
  return (
    `<figure class="frame"><div class="slip" data-ui>` +
    `<p class="slip-name"><strong>${link(entry.repo_url, esc(entry.name)) || esc(entry.name)}</strong>` +
    `${entry.scores?.treasure ? '<span class="badge gem">Hidden gem</span>' : ''}</p>` +
    `<p class="level">${CHECK}${esc(LEVEL_LABEL[r.level] ?? r.level)}</p>` +
    `<p>${esc(how)}, ${esc(day(r.checked_at))}.</p>` +
    (issue
      ? `<p class="diff"><span class="quiet">README:</span> ${esc(issue.readme_said)}<br><span class="quiet">What worked:</span> ${esc(issue.actually_needed)}</p>`
      : '') +
    (guide.steps[0] ? `<pre translate="no"><code>${esc(guide.steps[0].command)}</code></pre>` : '') +
    `</div><figcaption>A run record from pickfit’s catalog.</figcaption></figure>`
  );
}

/** "Installed before it is suggested": the newest runs as a table, the counts beside it. */
function recentSection(showcase: Showcase): string {
  const { stats, recent, fix } = showcase;
  if (!recent.length) return '';
  const issue = fix ? readerIssues(fix.guide.pitfalls)[0] : null;
  const fixSlip =
    fix && issue
      ? `<figure class="fix"><div class="slip" data-ui><p class="slip-name"><strong>${link(fix.entry.repo_url, esc(fix.entry.name)) || esc(fix.entry.name)}</strong></p>` +
        `<p class="level">${CHECK}${esc(LEVEL_LABEL[fix.guide.run.level] ?? fix.guide.run.level)}</p>` +
        `<p class="diff"><span class="quiet">README:</span> ${esc(issue.readme_said)}<br><span class="quiet">What worked:</span> ${esc(issue.actually_needed)}</p>` +
        (fix.guide.steps[0] ? `<pre translate="no"><code>${esc(fix.guide.steps[0].command)}</code></pre>` : '') +
        `</div><figcaption>Found while installing it on ${esc(system(fix.guide.run.os, fix.guide.run.arch))}, ${esc(day(fix.guide.run.checked_at))}.</figcaption></figure>`
      : '';
  const were = (n: number) => `${n} ${n === 1 ? 'was' : 'were'}`;
  const byHand = stats.byHand ? ` ${were(stats.byHand)} installed by hand on a real machine.` : '';
  const rows = recent
    .map(({ entry, guide }) => {
      const r = guide.run;
      return (
        `<tr><td class="kind">${esc(KIND[entry.category] ?? entry.category)}</td>` +
        `<td class="tool">${link(entry.repo_url, esc(entry.name)) || esc(entry.name)}<span>${esc(entry.summary)}</span></td>` +
        `<td class="where">${esc(system(r.os, r.arch))}, ${esc(day(r.checked_at, SHORT_DAY))}<span>${esc(LEVEL_LABEL[r.level] ?? r.level)}</span></td></tr>`
      );
    })
    .join('');
  return (
    `<section id="recent" class="recent wrap" aria-labelledby="recent-title">` +
    `<h2 id="recent-title">Installed before it is suggested</h2>` +
    `<div class="recent-grid"><div class="recent-side">` +
    `<p class="recent-note">pickfit lists ${stats.listed} tools. ${were(stats.replayed)} installed and replayed in a fresh sandbox, ` +
    `and ${stats.gems === 1 ? '1 is a hidden gem' : `${stats.gems} are hidden gems`}: high quality, little known.${byHand} Only verified tools are ever suggested.</p>${fixSlip}</div>` +
    `<table class="runs" data-ui><caption>The newest runs</caption>` +
    `<thead><tr><th scope="col">Kind</th><th scope="col">Tool</th><th scope="col">Where it ran</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div></section>`
  );
}

/** "How pickfit knows": one tool through the four stages, each a fragment built from its real data. */
function stagesSection(showcase: Showcase): string {
  const f = showcase.featured;
  if (!f) return '';
  const { entry, guide } = f;
  const r = guide.run;
  const profile: [string, string][] = [
    ['What it does', entry.summary],
    ['Runs on', entry.platforms.length ? listOf(entry.platforms.map((os) => OS_NAME[os])) : 'not stated in the README'],
    ['Price', entry.pricing ?? 'not stated'],
    ['Runs where', entry.processing ?? 'not stated'],
    ['Licence', entry.license ?? 'not stated'],
    ['Use case', entry.use_cases[0] ?? ''],
  ];
  const issue = readerIssues(guide.pitfalls)[0];
  const reasons = templateReasons(entry, toCard(entry), r.os).slice(0, 3);
  const dl = (rows: [string, string][]) =>
    `<dl>${rows
      .filter(([, v]) => v)
      .map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`)
      .join('')}</dl>`;
  const stages = [
    {
      name: 'Read',
      clause: 'Muse Spark reads the README.',
      text: 'Agents scan new GitHub projects. Meta’s Muse Spark reads each README and writes a profile: what the tool does, where it runs, what it costs, whether it works offline.',
      ui: `<p class="ui-title">${esc(entry.name)}: profile</p>${dl(profile)}`,
    },
    {
      name: 'Install',
      clause: 'pickfit installs it, twice.',
      text: 'A verification agent installs each tool in a fresh sandbox, fixes what the README got wrong, checks that it really works, then replays the steps in a new sandbox.',
      ui:
        `<p class="ui-title">${esc(entry.name)}: run on ${esc(system(r.os, r.arch))}</p>` +
        guide.steps.map((s) => `<pre translate="no"><code>${esc(s.command)}</code></pre>`).join('') +
        (issue ? `<p class="diff"><span class="quiet">README:</span> ${esc(issue.readme_said)}<br><span class="quiet">What worked:</span> ${esc(issue.actually_needed)}</p>` : '') +
        `<p class="level">${CHECK}${esc(LEVEL_LABEL[r.level] ?? r.level)}${r.replayed ? ', and again on replay' : ''}</p>`,
    },
    {
      name: 'Match',
      clause: 'Muse Spark matches your need.',
      text: 'Your sentence and every profile that meets your conditions go to Muse Spark in one call. Each reason must name the profile field it rests on; code checks the value and drops what doesn’t hold.',
      ui:
        `<p class="ui-title">${esc(entry.name)}: reasons, each checked against its field</p>` +
        `<ul class="why">${reasons.map((x) => `<li>${esc(x.claim)}<span class="cite">From its profile: ${esc(x.field)} is “${esc(x.value)}”</span></li>`).join('')}</ul>`,
    },
    {
      name: 'Hand over',
      clause: 'You get the steps that worked.',
      text: 'You get the exact commands from the run, where they ran, how to check the install, and what you’ll have to do by hand.',
      ui:
        `<p class="ui-title">${esc(entry.name)}: install steps</p>` +
        guide.steps.map((s) => command(s.command)).join('') +
        (guide.check ? `<p class="quiet">Check: <code>${esc(guide.check.command)}</code> prints “${esc(guide.check.expected_signal)}”.</p>` : ''),
    },
  ];
  const items = stages
    .map(
      (s, i) =>
        `<li class="stage" data-stage="${i}"><div class="clause-field"><h3>${esc(s.clause)}</h3><p>${esc(s.text)}</p></div>` +
        `<div class="ui-field"><div class="stage-ui" data-ui>${s.ui}</div></div></li>`,
    )
    .join('');
  const names = stages.map((s, i) => `<li><button type="button" data-stop="${i}">${esc(s.name)}</button></li>`).join('');
  return (
    `<section id="how" class="stages" aria-labelledby="how-title">` +
    `<h2 id="how-title" class="sr">How pickfit knows</h2>` +
    `<ol class="stage-list">${items}</ol>` +
    `<div class="stage-control wrap"><input type="range" id="stage" min="0" max="3" step="1" value="0" aria-label="Stage" aria-valuetext="${esc(stages[0].name)}">` +
    `<ol class="stage-names">${names}</ol></div></section>`
  );
}

export interface PageInput {
  nonce: string;
  /** This deployment's origin, for the MCP URL. */
  origin: string;
  showcase: Showcase;
  form: FormValues;
  /** Rendered results or a notice; empty before the first search. */
  results: string;
}

const MARK =
  '<svg class="mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="2" width="28" height="28" rx="4"/>' +
  '<path d="M9.5 16.5l4.4 4.4L22.5 11.5"/></svg>';
const ICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='2' y='2' width='28' height='28' rx='4' fill='%231F2B4D'/%3E" +
  "%3Cpath d='M9.5 16.5l4.4 4.4L22.5 11.5' fill='none' stroke='%23F2C12E' stroke-width='3.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E";

export function renderPage(input: PageInput): string {
  const { form, showcase, nonce } = input;
  const mcp = `${input.origin}/mcp`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pickfit: tools that fit, tested first</title>
<meta name="description" content="Describe the job in one sentence. pickfit suggests lesser-known developer CLI tools and local AI tools it has installed and tested, with the evidence and the steps that worked.">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0F1626" media="(prefers-color-scheme: dark)">
<link rel="icon" href="${ICON}">
<style nonce="${nonce}">${CSS}</style>
</head>
<body>
<a class="skip" href="#need">Skip to the search box</a>
<header class="top wrap">
<a class="brand" href="/" translate="no">${MARK}<span>pickfit</span></a>
<nav aria-label="Page"><a href="#how">How it works</a><a href="#agents">For agents</a></nav>
</header>
<main>
<section class="hero wrap" aria-labelledby="title">
<div class="hero-row">
<h1 id="title"><span class="half first">Tools that fit,</span> <span class="half second">tested first.</span></h1>
${heroRecord(showcase.featured)}
</div>
<p class="lede">Describe the job in one sentence. pickfit suggests lesser-known developer CLI tools and local AI tools that it has installed in a fresh sandbox, matched to you by Meta’s Muse Spark.</p>
<form id="search" class="search" method="post" action="/search#results">
<div class="need">
<label for="need">I need</label>
<textarea id="need" name="need" rows="1" minlength="3" maxlength="500" required autocomplete="off" spellcheck="true" placeholder="a free way to transcribe meeting recordings offline…">${esc(form.need)}</textarea>
</div>
<div class="filters">
<span class="filters-label">Runs on</span>
${select('os', form.os, 'Operating system')}
${select('arch', form.arch, 'CPU architecture')}
<label class="check-label"><input type="checkbox" name="free_only" value="1"${form.free_only ? ' checked' : ''}> Free only</label>
<label class="check-label"><input type="checkbox" name="offline" value="1"${form.offline ? ' checked' : ''}> Works offline</label>
<button type="submit" class="go">Find software</button>
</div>
</form>
<div class="examples"><span class="quiet">Or try</span>${EXAMPLES.map((e) => `<button type="button" data-need="${esc(e)}">${esc(e)}</button>`).join('')}</div>
</section>
<p id="status" class="sr" aria-live="polite"></p>
<section id="results" class="results wrap" tabindex="-1" aria-label="Results">${input.results}</section>
${recentSection(showcase)}
${stagesSection(showcase)}
<section id="agents" class="agents wrap" aria-labelledby="agents-title">
<h2 id="agents-title">Same answers, in your agent.</h2>
<p>Coding agents get the same data and the same matching through MCP. Any client that speaks streamable HTTP can connect to <code translate="no">${esc(mcp)}</code>; for Claude Code:</p>
<div class="blank" data-ui>${command(`claude mcp add --transport http pickfit ${mcp}`)}</div>
</section>
</main>
<footer class="foot">
<div class="wrap foot-top">
<div class="invite"><h2>Find the tool that fits.</h2><a class="btn" href="#need">Describe your job</a></div>
<ul class="foot-links"><li><a href="#recent">Recently verified</a></li><li><a href="#how">How it works</a></li><li><a href="#agents">For agents</a></li></ul>
</div>
<div class="wrap foot-notes">
<p>pickfit ranks by fit, not stars. No ads, no paid placement, no referral links, and it doesn’t make any of the software it suggests.</p>
<p>No account and no IP address stored. Your sentence goes to Meta’s Muse Spark with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS.</p>
</div>
<p class="wordmark" aria-hidden="true" translate="no">pickfit</p>
</footer>
<template id="loading"><div class="loading" role="status"><div class="bar" aria-hidden="true"></div><h2>Matching your need…</h2><ol><li>Keep the verified tools that meet your OS, price and offline conditions</li><li>Muse Spark reads every remaining profile and picks the best fits</li><li>Code checks each reason against the profile</li></ol><p class="quiet">Usually 5 to 15 seconds.</p></div></template>
<template id="offline"><div class="notice error" role="alert"><h2>Couldn’t reach pickfit</h2><p>Check your connection and search again.</p></div></template>
<script nonce="${nonce}">${SCRIPT}</script>
</body>
</html>`;
}

const CSS = `
:root{--bg:#FFFFFF;--surface:#F2F4F7;--field:#E4E8EF;--ink:#1F2B4D;--muted:#5A6480;--accent:#F2C12E;--accent-ink:#1F2B4D;
--pass:#17754A;--pass-soft:#E2F2E9;--caution:#8A4B08;--caution-soft:#FBEFD9;--code:#1A2440;--code-ink:#E8EDF5;--radius:4px;
--t-display:clamp(40px,4.4vw,68px);--t-statement:clamp(24px,2.2vw,32px);--t-lead:20px;--t-body:17px;--t-small:15px;
--serif:Charter,"Bitstream Charter","Iowan Old Style","Sitka Text",Cambria,Georgia,serif;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; /* taste-skill-ignore: only pre and code use it */
--gap:clamp(96px,12vw,176px)}
@media (prefers-color-scheme:dark){:root{--bg:#0F1626;--surface:#172137;--field:#202C47;--ink:#E8ECF4;--muted:#A6B0C6;
--pass:#62CC98;--pass-soft:#12301F;--caution:#F0B45A;--caution-soft:#33260E;--code:#0A1020}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:var(--t-body)/1.55 var(--sans);overflow-wrap:break-word}
.wrap{max-width:1280px;margin:0 auto;padding:0 32px}
a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{text-decoration-color:var(--accent);text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
h1,h2,h3,.need label,.need textarea,.wordmark{font-family:var(--serif);font-weight:600;letter-spacing:-.02em}
h1,h2,h3{text-wrap:balance;margin:0}
h1{font-size:var(--t-display);line-height:1}
h2{font-size:var(--t-display);line-height:1.02}
h3{font-size:var(--t-statement);line-height:1.15}
h4,h5{font:600 var(--t-body)/1.4 var(--sans);margin:22px 0 8px}
p{margin:0 0 12px;max-width:62ch}
ul,ol{margin:0 0 12px;padding-left:22px}
code,pre{font-family:var(--mono);font-size:var(--t-small)}
.quiet{color:var(--muted)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
button{touch-action:manipulation;-webkit-tap-highlight-color:transparent;font:inherit}
.skip{position:absolute;left:-9999px;top:12px;background:var(--ink);color:var(--bg);padding:10px 14px;border-radius:var(--radius);z-index:1}
.skip:focus{left:12px}
section[id]{scroll-margin-top:16px}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:22px;padding-bottom:22px}
.brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font:700 var(--t-lead)/1 var(--sans);letter-spacing:-.02em}
.mark{width:28px;height:28px}.mark rect{fill:var(--ink)}.mark path{fill:none;stroke:var(--accent);stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}
.top nav{display:flex;gap:24px}.top nav a{text-decoration:none}.top nav a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.check{width:20px;height:20px;flex:none;border-radius:50%;background:var(--pass);vertical-align:-4px;margin-right:8px}
.check path{fill:none;stroke:var(--bg);stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}

.hero{padding-top:48px;padding-bottom:24px}
.hero-row{--frame:min(30vw,430px);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,var(--frame)) minmax(0,1fr);align-items:center;margin-bottom:40px}
.hero-row h1{grid-row:1;grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;gap:calc(var(--frame) + 32px);font-size:clamp(40px,4vw,60px)}
.half{display:block;animation:settle .7s cubic-bezier(.2,.7,.2,1) both}
.half.first{--from:-28px}.half.second{--from:28px;text-align:right}
.frame{grid-row:1;grid-column:2;margin:0;animation:rise .7s .12s cubic-bezier(.2,.7,.2,1) both}
.frame figcaption{font-size:var(--t-small);color:var(--muted);margin-top:8px}
.slip{background:var(--surface);border-radius:var(--radius);padding:18px 20px;line-height:1.5}
.slip p{margin:0 0 8px}
.slip-name{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:var(--t-lead)}
.slip-name a{text-decoration:none}
.slip .level,.stage-ui .level{font-size:var(--t-body);font-weight:600}
.slip pre,.stage-ui pre{background:var(--code);color:var(--code-ink);border-radius:var(--radius);padding:9px 12px;margin:10px 0 0;overflow-x:auto;white-space:pre}
.diff{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.lede{font-size:var(--t-lead);line-height:1.5;margin-bottom:28px;animation:rise .7s .2s both}
.search{animation:rise .7s .28s both}
.need{display:flex;align-items:baseline;gap:16px;background:var(--surface);border-radius:var(--radius);padding:14px 18px;border-bottom:4px solid var(--field)}
.need:focus-within{border-bottom-color:var(--accent)}
.need label{font-size:var(--t-statement);color:var(--muted);white-space:nowrap}
.need textarea{flex:1;min-width:0;border:0;background:transparent;color:var(--ink);font-size:var(--t-statement);line-height:1.3;resize:none;padding:0;overflow:hidden;font-weight:500}
.need textarea::placeholder{color:var(--muted);opacity:.7}
.need textarea:focus-visible{outline:none}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;margin-top:16px}
.filters-label{color:var(--muted)}
select{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--field);border-radius:var(--radius);padding:8px 10px;max-width:100%}
.check-label{display:inline-flex;align-items:center;gap:8px;cursor:pointer;min-height:40px}
.check-label input{width:20px;height:20px;accent-color:var(--ink);margin:0}
.go,.btn{margin-left:auto;display:inline-block;font:600 var(--t-body)/1 var(--sans);color:var(--accent-ink);background:var(--accent);border:0;border-radius:var(--radius);padding:15px 24px;cursor:pointer;text-decoration:none;transition:transform .12s}
.go:hover,.btn:hover{background:color-mix(in srgb,var(--accent) 85%,var(--ink))}
.go:active,.btn:active{transform:translateY(1px)}
.go:disabled{opacity:.6;cursor:progress}
.examples{display:none;flex-wrap:wrap;align-items:baseline;gap:8px 20px;margin-top:24px;animation:rise .7s .36s both}
.js .examples{display:flex}
.examples button{color:var(--ink);background:none;border:0;padding:4px 0;cursor:pointer;text-align:left;text-decoration:underline;text-decoration-color:var(--field);text-decoration-thickness:2px;text-underline-offset:5px}
.examples button:hover{text-decoration-color:var(--accent)}

.results{padding-top:24px}
.results:focus{outline:none}
.results-title{margin-top:var(--gap);margin-bottom:12px}
.match-line{font-size:var(--t-lead);color:var(--muted)}
.ask,.aside{background:var(--surface);border-radius:var(--radius);padding:18px 22px;margin:28px 0;max-width:none}
.aside h3{margin-bottom:8px}
.lead-in{font-weight:600}
.pick{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px 56px;padding-top:72px;animation:rise .6s cubic-bezier(.2,.7,.2,1) both}
.pick:nth-child(2){animation-delay:.08s}.pick:nth-child(3){animation-delay:.16s}
.pick h3 a{text-decoration-color:var(--field)}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
.badge{font:600 var(--t-small)/1 var(--sans);padding:7px 10px;border-radius:var(--radius)}
.badge.free{background:var(--pass-soft);color:var(--pass)}
.badge.gem{background:var(--accent);color:var(--accent-ink)}
.summary{color:var(--muted);margin-top:12px}
.fit{font-size:var(--t-lead);line-height:1.5;margin:16px 0 4px}
.why{list-style:none;padding:0}
.why li{position:relative;padding-left:28px;margin-bottom:10px}
.why li::before{content:"";position:absolute;left:5px;top:5px;width:6px;height:11px;border:solid var(--pass);border-width:0 2.5px 2.5px 0;transform:rotate(45deg)}
.cite{display:block;font-size:var(--t-small);color:var(--muted)}
.tradeoffs li{margin-bottom:6px}
.facts{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:18px 0 0}
.facts li{font-size:var(--t-small);background:var(--surface);border-radius:var(--radius);padding:5px 10px}
.evidence{align-self:start}
.claim{align-self:start;position:sticky;top:24px}
@media (max-height:820px){.claim{position:static}}
.best-free{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px 40px;align-items:start}
.best-free>p:first-child{grid-row:span 2}
.record{background:var(--surface);border-radius:var(--radius);padding:20px 22px}
.record p{margin-bottom:8px}
.level{font-weight:600;font-size:var(--t-lead)}
.mine{padding:10px 14px;border-radius:var(--radius);font-weight:500;max-width:none}
.mine-yes{background:var(--pass-soft);color:var(--pass)}
.mine-no{background:var(--caution-soft);color:var(--caution)}
.mine-unknown{background:var(--field);color:var(--ink)}
.how summary,.install summary{cursor:pointer;font-weight:600}
.how summary{font-size:var(--t-small);color:var(--muted);font-weight:500}
.how p{font-size:var(--t-small);color:var(--muted);margin-top:8px}
.install{margin:20px 0 8px}
.install summary{padding:6px 0}
.install-body{padding:4px 0 2px}
details:not([open])>:not(summary){display:none}
.steps{padding-left:22px}.steps li{margin-bottom:14px}.steps li p{margin-bottom:6px}
.caution{color:var(--caution)}
.cmd{display:flex;align-items:flex-start;background:var(--code);color:var(--code-ink);border-radius:var(--radius);margin:6px 0 10px;min-width:0}
.cmd pre{flex:1;min-width:0;margin:0;padding:12px 14px;overflow-x:auto;line-height:1.55;white-space:pre}
.copy{display:none;flex:none;font:600 var(--t-small)/1 var(--sans);color:var(--code-ink);background:color-mix(in srgb,var(--code-ink) 14%,transparent);border:0;border-radius:var(--radius);padding:8px 10px;margin:6px 6px 0 0;cursor:pointer}
.js .copy{display:inline-block}
.copy:hover{background:var(--accent);color:var(--accent-ink)}
.issues li{margin-bottom:10px}
.links{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:12px}
.outside{margin:72px 0 0;padding-top:0;color:var(--muted);max-width:62ch}
.outside h3{font:600 var(--t-lead)/1.35 var(--sans);letter-spacing:0;color:var(--ink);margin-bottom:10px}
.unchecked{background:var(--caution-soft);color:var(--caution);border-radius:var(--radius);padding:10px 14px;font-weight:500;max-width:none}
.nofit{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:56px;align-items:end}
.nofit .outside{margin:0}
.notice,.loading{border-radius:var(--radius);padding:20px 24px;margin:var(--gap) 0 0;background:var(--surface)}
.notice h2,.loading h2{font-size:var(--t-statement);margin-bottom:8px}
.notice.busy{background:var(--caution-soft)}
.notice.busy h2,.notice.error h2{color:var(--caution)}
.notice + .results-title{margin-top:48px}
.loading ol{color:var(--muted);padding-left:22px}
.bar{height:6px;border-radius:3px;background:var(--field);overflow:hidden;margin-bottom:16px;position:relative}
.bar::after{content:"";position:absolute;inset:0;width:35%;background:var(--accent);animation:slide 1.3s ease-in-out infinite}

.recent{padding-top:var(--gap)}
.recent h2{max-width:19ch;padding-left:3vw}
.recent-grid{display:grid;grid-template-columns:minmax(0,4fr) minmax(0,8fr);gap:56px;margin-top:72px;align-items:start}
.recent-side{display:flex;flex-direction:column;gap:40px}
.recent-note{font-size:var(--t-lead);line-height:1.5;margin:0}
.fix{margin:0}.fix .level{font-size:var(--t-body);font-weight:600}.fix pre{background:var(--code);color:var(--code-ink);border-radius:var(--radius);padding:9px 12px;margin:10px 0 0;overflow-x:auto;white-space:pre}.fix figcaption{font-size:var(--t-small);color:var(--muted);margin-top:8px}
.runs{width:100%;border-collapse:collapse}
.runs caption{text-align:left;font-size:var(--t-small);color:var(--muted);padding-bottom:12px}
.runs thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.runs td{vertical-align:top;padding:12px 16px 12px 0}
.runs tr:nth-child(3n) td{padding-bottom:36px}
.runs .kind{color:var(--muted);font-size:var(--t-small);white-space:nowrap;padding-top:15px}
.runs .tool a{font-weight:600}
.runs .tool span{display:block;color:var(--muted)}
.runs .where span{display:block;color:var(--muted);font-size:var(--t-small)}
.runs .where{text-align:right;white-space:nowrap;padding-right:0;font-variant-numeric:tabular-nums}

.stages{margin-top:var(--gap);display:flex;flex-direction:column}
.stage-list{list-style:none;padding:0;margin:0}
.stage{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);min-height:min(64svh,640px)}
.clause-field{background:var(--surface);padding:clamp(32px,5vw,72px) 32px clamp(32px,5vw,72px) max(32px,calc((100vw - 1280px)/2 + 32px))}
.clause-field h3{font-size:var(--t-display);line-height:1.02;max-width:16ch;margin-bottom:24px}
.clause-field p{font-size:var(--t-lead);line-height:1.5}
.ui-field{background:var(--field);display:flex;align-items:center;justify-content:center;padding:48px 32px}
.stage-ui{background:var(--bg);border-radius:var(--radius);padding:22px 24px;width:min(100%,520px)}
.stage-ui .ui-title{font-weight:600;font-size:var(--t-body);margin-bottom:14px}
.stage-ui dl{margin:0}.stage-ui dl div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:12px;padding:6px 0}
.stage-ui dt{color:var(--muted)}.stage-ui dd{margin:0}
.stage-ui .diff{margin-top:12px}
.stage-ui .why{margin:0}
.stage-control{display:none;width:100%;padding-top:28px}
.js .stage-control{display:block}
.js .stage{display:none}.js .stage.on{display:grid;animation:fade .2s both}
.stage-control input{width:100%;margin:0;accent-color:var(--ink);height:32px;cursor:pointer}
.stage-names{list-style:none;padding:0;margin:8px 0 0;position:relative;height:2.2em;color:var(--muted)}
.stage-names li{position:absolute;top:0;white-space:nowrap}
.stage-names li:nth-child(1){left:0}.stage-names li:nth-child(2){left:33.33%;transform:translateX(-50%)}.stage-names li:nth-child(3){left:66.67%;transform:translateX(-50%)}.stage-names li:nth-child(4){right:0}
.stage-names button{font:inherit;color:inherit;background:none;border:0;padding:4px 0;cursor:pointer}
.stage-names button:hover{color:var(--ink);text-decoration:underline;text-decoration-color:var(--accent);text-underline-offset:4px}
.stage-names button.on{color:var(--ink);font-weight:600}

.agents{padding-top:var(--gap);padding-bottom:var(--gap)}
.agents h2{max-width:16ch;margin-bottom:24px}
.agents p{font-size:var(--t-lead)}
.blank{max-width:900px}
.blank .cmd{font-size:var(--t-body)}
.blank .cmd pre{font-size:var(--t-body);padding:16px 18px}
.blank .copy{display:inline-block;background:var(--accent);color:var(--accent-ink);padding:12px 16px;margin:7px 7px 0 0}

.foot{background:var(--accent);color:var(--accent-ink);overflow:hidden;min-height:min(80svh,760px);display:flex;flex-direction:column}
.foot a{color:var(--accent-ink)}
.foot-top{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:32px;padding-top:clamp(64px,8vw,120px);width:100%}
.invite h2{margin-bottom:28px;max-width:11ch}
.foot .btn{margin:0;background:var(--accent-ink);color:var(--accent)}
.foot .btn:hover{background:color-mix(in srgb,var(--accent-ink) 85%,var(--accent))}
.foot-links{list-style:none;padding:0;margin:0;justify-self:end;font-size:var(--t-body);line-height:2}
.foot-notes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:32px;margin-top:auto;padding-top:56px;width:100%}
.foot-notes p{font-size:var(--t-small);margin:0}
.wordmark{font-size:28vw;line-height:.8;white-space:nowrap;margin:24px 0 0;padding-left:16px;transform:translateY(22%);max-width:none;animation:lift linear both;animation-timeline:view();animation-range:entry 0% cover 60%}

@keyframes settle{from{opacity:0;transform:translateX(var(--from))}to{opacity:1;transform:none}}
@keyframes rise{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(290%)}}
@keyframes lift{from{transform:translateY(45%)}to{transform:translateY(22%)}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}.bar::after{width:100%}}

@media (max-width:960px){
.hero{display:flex;flex-direction:column}
.hero-row{display:contents}
.hero-row h1{flex-direction:column;align-items:stretch;gap:0;margin-bottom:24px}
.lede{order:1}.search{order:2}.examples{order:3}
.frame{order:4;max-width:520px;margin-top:40px}
.pick,.nofit,.best-free{grid-template-columns:minmax(0,1fr);gap:28px}
.best-free{gap:4px}
.claim{position:static}
.recent-grid{grid-template-columns:minmax(0,1fr);margin-top:40px}
.stage{grid-template-columns:minmax(0,1fr)}
.ui-field{order:-1;min-height:min(46svh,420px)}
.clause-field{padding:32px}
.foot-top,.foot-notes{grid-template-columns:minmax(0,1fr)}
.foot-links{justify-self:start}
}
@media (max-width:640px){
:root{--gap:88px}
.wrap{padding-left:16px;padding-right:16px}
.top nav{gap:16px;font-size:var(--t-small)}
.hero{padding-top:20px}
.lede{font-size:var(--t-body)}
.need{flex-direction:column;align-items:stretch;gap:2px;padding:12px 14px}
.need textarea{flex:none}
.go{margin-left:0;width:100%}
.filters select{flex:1 1 40%}
.recent h2{padding-left:0}
.runs td{display:block;padding:0}
.runs tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 12px;padding:10px 0}
.runs .kind{grid-column:1/-1;padding-top:0}
.runs .where{white-space:normal}
.runs tr:nth-child(3n) td{padding-bottom:0}
.runs tr:nth-child(3n){padding-bottom:28px}
.clause-field{padding:24px 16px}
.ui-field{padding:24px 16px}
.stage-names{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;height:auto}
.stage-names li{position:static;transform:none!important}
.stage-control{order:-1;padding-top:0;padding-bottom:16px}
.wordmark{font-size:34vw;padding-left:8px}
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
  // Links to the search box put the cursor in it.
  for (const a of document.querySelectorAll('a[href="#need"]')) {
    a.addEventListener('click', (e) => { e.preventDefault(); need.focus(); need.scrollIntoView({ block: 'center' }); });
  }
  let busy = false;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    go.disabled = true;
    go.textContent = 'Finding…';
    status.textContent = 'Searching…';
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
  // How it works: the range input picks the stage; arrow keys work natively.
  const range = document.getElementById('stage');
  if (range) {
    const stages = document.querySelectorAll('.stage');
    const stops = document.querySelectorAll('.stage-names button');
    const show = () => {
      const i = Number(range.value);
      stages.forEach((s, k) => s.classList.toggle('on', k === i));
      stops.forEach((s, k) => s.classList.toggle('on', k === i));
      range.setAttribute('aria-valuetext', stops[i].textContent);
    };
    range.addEventListener('input', show);
    stops.forEach((s, k) => s.addEventListener('click', () => { range.value = String(k); show(); }));
    show();
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
