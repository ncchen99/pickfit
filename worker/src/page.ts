/**
 * The home page and the results of one search. Pure functions over
 * find_software's and get_install_guide's own outputs (and, before a search,
 * the catalog itself), so the page shows what an agent gets. Every value that
 * comes from the data or the model goes through esc(); links must be http(s).
 *
 * Design (DESIGN.md): the fitting room. A pick is a fitting ticket: the claim
 * on top, then a seam of stitches, then the run record it rests on. A tool
 * pickfit has not verified gets no stitches, no badge, no steps and no link.
 */
import { bestGuide, isVerified, isWebApp, verifiedOn, verifiedOnUserSystem, webCheck, type Arch, type Catalog, type Entry, type InstallGuide, type OS } from './catalog.ts';
import type { FindOutput, PickOut } from './find.ts';
import { fitNote } from './fit.ts';
import { PIPE_TO_SHELL, type InstallOutput } from './install.ts';
import { compareTable } from './pages/compare.ts';
import { day, guiSentence, howRan, KIND, levelLabel, osName, PRICE, PROCESSING, passed, readerIssues, setupWords, SHORT_DAY, system, kindLine, webLevelLabel } from './ui/facts.ts';
import { esc, link, listOf } from './ui/html.ts';
import { icon } from './ui/icons.ts';
import { badge, command, compareToggle, coverage, fitz, glance, notice, says, SEAM, tape, type FitzName } from './ui/kit.ts';
import { renderShell } from './ui/shell.ts';
import { NO_INSTALL_LABEL, webFacts, webRanSentence } from './webapp.ts';

export { esc, safeUrl } from './ui/html.ts';
export { guiSentence, LEVEL_LABEL, levelLabel, osName } from './ui/facts.ts';

export interface FormValues {
  need: string;
  os: OS | '';
  arch: Arch | '';
  free_only: boolean;
  offline: boolean;
  /** What the person types must not leave their machine. */
  private: boolean;
}

export const EMPTY_FORM: FormValues = { need: '', os: '', arch: '', free_only: false, offline: false, private: false };

/** Why the web page did not ask the model: its daily share, the total cap, or no way to count spend. */
export type BudgetStop = 'web_daily' | 'total' | 'unavailable';

/** One search: find_software's output and get_install_guide's for each pick (by slug). */
export interface SearchResult {
  out: FindOutput;
  guides: Record<string, InstallOutput>;
}

export interface CatalogStats {
  listed: number;
  verified: number;
  replayed: number;
  byHand: number;
  gems: number;
  /** Web apps a sandboxed browser run passed on (they have no install steps to replay). */
  web: number;
}

const runsOf = (entry: Entry) => Object.values(entry.install).map((guide) => guide!.run);

export function catalogStats(catalog: Catalog): CatalogStats {
  return {
    listed: catalog.count,
    verified: catalog.entries.filter(isVerified).length,
    replayed: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'sandbox' && r.replayed)).length,
    byHand: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'human')).length,
    gems: catalog.entries.filter((e) => e.scores?.treasure).length,
    web: catalog.entries.filter((e) => isWebApp(e) && webCheck(e) !== null).length,
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

export function catalogShowcase(catalog: Catalog, recentCount = 3): Showcase {
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

// ---------------------------------------------------------------- the run record in words

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
export const levelLine = (label: string, ok: boolean) => `<p class="level${ok ? '' : ' level-caution'}">${ok ? CHECK : icon('triangle-alert')}${esc(label)}</p>`;

function facts(pick: PickOut): string {
  const items: string[] = [];
  if (pick.open_source === true) items.push(pick.license ? `Open source (${esc(pick.license)})` : 'Open source');
  if (pick.open_source === false) items.push('Not open source');
  // A web app's own facts (where data goes, which OS) are in its test record.
  const where = pick.web_app ? '' : PROCESSING[pick.processing];
  if (where) items.push(where);
  if (pick.web_app) items.push('In any modern browser');
  else if (pick.platforms.length) items.push(`For ${listOf(pick.platforms.map((os) => osName(os)))}`);
  return items.length ? `<p class="small quiet facts">${items.join(' · ')}</p>` : '';
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
      `${notes.length ? `<p class="caution small">${notes.join(' ')}</p>` : ''}</li>`
    );
  });
  parts.push(`<ol class="steps">${steps.join('')}</ol>`);
  if (guide.manual_steps.length) {
    parts.push(`<h4>You do these yourself</h4><ul><li>${guide.manual_steps.map((s) => esc(s.title)).join('</li><li>')}</li></ul>`);
  }
  if (guide.verify) {
    parts.push(
      `<h4>Check that it works</h4>${command(guide.verify.command)}` +
        `<p class="quiet small">The output should contain “${esc(guide.verify.expected_contains)}”.</p>`,
    );
  }
  if (guide.first_task) {
    const setup = guide.first_task_setup.map((s) => command(s.command)).join('');
    parts.push(`<h4>First thing to try</h4>${setup}${command(guide.first_task)}`);
  }
  const cfg = guide.mcp_client_config;
  if (cfg) {
    const env = cfg.env.length
      ? `<h4>You fill in</h4><ul>${cfg.env
          .map((e) => `<li><code translate="no">${esc(e.name)}</code>${e.purpose ? `: ${esc(e.purpose)}` : ''}${e.required ? ' (required)' : ''}</li>`)
          .join('')}</ul>`
      : '';
    parts.push(
      `<h4>Add it to your agent</h4>${command(cfg.claude_code)}` +
        `<details class="json"><summary class="small">JSON for Claude Desktop, Cursor and other clients</summary>${command(cfg.json)}</details>` +
        env +
        (cfg.note ? `<p class="quiet small">${esc(cfg.note)}</p>` : ''),
    );
  }
  const issues = readerIssues(guide.known_issues);
  if (issues.length) {
    parts.push(
      `<h4>Where the README and reality differ</h4><ul class="issues">${issues
        .map((i) => `<li><span class="quiet">README:</span> ${esc(i.readme_said)}<br><span class="quiet">What worked:</span> ${esc(i.actually_needed)}</li>`)
        .join('')}</ul>`,
    );
  }
  return (
    `<details class="install"${open ? ' open' : ''}><summary>Install steps that worked on ${esc(system(v.os, v.arch))}${icon('chevron-down')}</summary>` +
    `<div class="install-body">${parts.join('')}</div></details>`
  );
}

/** The run record: the evidence half of a pick, under the seam. */
function record(pick: PickOut, guide: InstallOutput | undefined, form: FormValues): string {
  const v = pick.verification;
  const mine = yourSystem(v, form);
  const offline = guide?.verification.works_offline;
  // A GUI app's launch sentence already says whether the launch passed offline.
  const offlineLine =
    offline === true
      ? v.gui
        ? ''
        : ' Its checks passed again with the network off.'
      : offline === false
        ? ' Its checks failed with the network off: it needed the network in pickfit’s run.'
        : form.offline
          ? ' pickfit hasn’t checked it with the network off.'
          : '';
  const mcp = guide?.mcp_client_config ?? null;
  const shown = (tools: string[]) => tools.slice(0, 6).join(', ') + (tools.length > 6 ? ', …' : '');
  const mcpLine = mcp
    ? `An MCP client handshake over ${mcp.transport === 'stdio' ? 'stdio' : 'HTTP'} listed its ${mcp.tool_count} tool${mcp.tool_count === 1 ? '' : 's'}` +
      `${mcp.tools.length ? ` (${shown(mcp.tools)})` : ''}${mcp.called_tool ? `, and a call to ${mcp.called_tool} returned a result` : ''}.`
    : '';
  return (
    `<section class="record" aria-label="Test record">` +
    `<p class="record-title">${icon('badge-check')}Test record</p>` +
    levelLine(levelLabel(v.level, { gui: v.gui, mcp }), passed(v.gui)) +
    `<p>${esc(ranSentence(v) + offlineLine)}</p>` +
    (mcpLine ? `<p>${esc(mcpLine)}</p>` : '') +
    (v.gui ? `<p>${esc(guiSentence(v.gui))}</p>` : '') +
    `<p class="mine mine-${mine.state}">${esc(mine.text)}</p>` +
    `<details class="how"><summary>How we know</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

const MATCH_LABEL = { good: 'Good match', partial: 'Partial match', weak: 'Weak match' } as const;
const MATCH_TONE = { good: 'pass', partial: 'caution', weak: 'caution' } as const;

/** Rules only: which of the request's words the profile mentions, and which it does not. */
function matchCoverage(match: NonNullable<PickOut['match']>): string {
  const list = (words: string[]) => words.slice(0, 6).map((w) => `“${esc(w)}”`).join(', ');
  const parts = [
    match.covers.length ? `Its profile mentions ${list(match.covers)}.` : '',
    match.missing.length ? `It does not mention ${list(match.missing)}.` : '',
  ].filter(Boolean);
  return parts.length ? `<p class="coverage">${parts.join(' ')}</p>` : '';
}

/** find.ts adds this tradeoff for agents when the run was on another system; the test record says it in full. */
const RAN_ELSEWHERE = /^Verified on \S+(?: \S+)? only; pickfit has not run its /;

/** The verdict strip: the four things people decide on first, each from a field or the run. */
function glanceStrip(pick: PickOut, guide: InstallOutput | undefined, form: FormValues): string {
  const v = pick.verification;
  const where = system(v.os, v.arch);
  const cells: string[] = [];
  if (v.verified_on_user_os === true) cells.push(glance('monitor', 'Your system', `Ran on ${esc(where)}`, 'pass'));
  else if (v.verified_on_user_os === false) cells.push(glance('monitor', 'Your system', `Ran on ${esc(where)} only`, 'caution'));
  else cells.push(glance('monitor', 'Ran on', v.os ? esc(where) : 'No run', 'plain'));
  const off = guide?.verification.works_offline;
  const offline = off === true ? '<small>Works offline</small>' : off === false && form.offline ? '<small>Needed the network</small>' : '';
  cells.push(glance('badge-check', 'Proof', esc(levelLabel(v.level, { gui: v.gui, mcp: guide?.mcp_client_config ?? null })) + offline, passed(v.gui) ? 'pass' : 'caution'));
  if (guide && guide.steps.length) cells.push(glance('terminal', 'Setup', esc(setupWords(guide.steps.length, guide.manual_steps.length)), 'plain'));
  cells.push(glance('tag', 'Price', esc(PRICE[pick.pricing]), pick.pricing === 'unknown' ? 'quiet' : 'plain'));
  return `<div class="glance t-glance">${cells.join('')}</div>`;
}

/** The evidence no one else has, in one line: what the README got wrong and what worked. */
function readmeFix(guide: InstallOutput): string {
  const issues = readerIssues(guide.known_issues);
  const fix = issues.find((i) => i.kind === 'readme_wrong') ?? issues[0];
  return fix
    ? `<p class="t-fix">${icon('scissors')}<span><b>README fix:</b> ${esc(fix.actually_needed)}</span></p>`
    : '';
}

/** The one action on a ticket: the first command of the run that worked, ready to copy. */
function quickInstall(guide: InstallOutput | undefined, form: FormValues): string {
  const first = guide?.steps[0];
  if (!guide || !first) return '';
  const v = guide.verification;
  const elsewhere = guide.applies_to_user_system.match === 'other_os' && form.os;
  const more = guide.steps.length - 1 + guide.manual_steps.length;
  return (
    `<div class="t-install"><p class="t-install-label">${icon('terminal')}Install${elsewhere ? `, as it ran on ${esc(system(v.os, v.arch))}` : ''}` +
    `${more ? `<span class="quiet"> · step 1 of ${guide.steps.length + guide.manual_steps.length}</span>` : ''}</p>${command(first.command)}` +
    readmeFix(guide) +
    `</div>`
  );
}

// ---------------------------------------------------------------- a web app's ticket

/** A web app's facts as a short list, each with its tone; the same words on the ticket and the profile. */
export function webFactList(entry: Entry): string {
  const check = webCheck(entry);
  if (!check) return '';
  const tone = { pass: 'yes', caution: 'no', plain: '' } as const;
  return `<ul class="web-facts">${webFacts(check)
    .map((f) => `<li${tone[f.tone] ? ` class="${tone[f.tone]}"` : ''}>${f.tone === 'pass' ? icon('check') : f.tone === 'caution' ? icon('triangle-alert') : icon('info')}${esc(f.text)}</li>`)
    .join('')}</ul>`;
}

/** The run record of a web app: what pickfit's browser saw, under the seam. */
function webRecord(pick: PickOut, entry: Entry | undefined): string {
  const check = entry ? webCheck(entry) : null;
  if (!check || !entry) return '';
  return (
    `<section class="record" aria-label="Test record">` +
    `<p class="record-title">${icon('badge-check')}Test record</p>` +
    levelLine(webLevelLabel(check), true) +
    `<p>${esc(webRanSentence(check))}</p>` +
    webFactList(entry) +
    `<p class="mine mine-yes">${esc('Nothing to install: it opens in a browser on any OS.')}</p>` +
    `<details class="how"><summary>How we know</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

/** A web app's verdict strip: where it runs, the proof, the setup (none) and the price. */
function webGlance(pick: PickOut, entry: Entry | undefined): string {
  const check = entry ? webCheck(entry) : null;
  const web = pick.web_app!;
  const offline = web.works_offline === 'verified' ? '<small>Works offline</small>' : '';
  return (
    `<div class="glance t-glance">` +
    glance('globe', 'Runs in', 'Any browser', 'pass') +
    glance('badge-check', 'Proof', (check ? esc(webLevelLabel(check)) : 'No run') + offline, check ? 'pass' : 'caution') +
    glance('terminal', 'Setup', 'Nothing to install', 'plain') +
    glance('tag', 'Price', esc(PRICE[pick.pricing]), pick.pricing === 'unknown' ? 'quiet' : 'plain') +
    `</div>`
  );
}

/** The one action on a web app's ticket: open it. */
function webOpen(pick: PickOut): string {
  const web = pick.web_app!;
  const open = link(web.url, `${icon('external-link')}Open ${esc(pick.name)}`, 'btn btn-primary btn-sm');
  return open
    ? `<div class="t-install"><p class="t-install-label">${icon('globe')}${esc(NO_INSTALL_LABEL)}</p><p class="t-open">${open}<span class="quiet small" translate="no">${esc(web.url)}</span></p></div>`
    : '';
}

function pickHtml(pick: PickOut, index: number, result: SearchResult, form: FormValues, catalog: Catalog): string {
  const { out } = result;
  const entry = catalog.bySlug.get(pick.slug);
  const best = out.best_free?.slug === pick.slug ? out.best_free : null;
  const web = pick.web_app;
  const badges = [
    web ? badge('info', NO_INSTALL_LABEL, { icon: 'globe' }) : '',
    pick.match ? badge(MATCH_TONE[pick.match.quality], MATCH_LABEL[pick.match.quality], { cls: `match-${pick.match.quality}` }) : '',
    best ? badge('free', 'Best free option', { icon: 'leaf' }) : '',
    pick.scores.treasure ? badge('gem', 'Hidden gem', { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  const why = pick.why
    .map((r) => `<li>${esc(r.claim)}<span class="cite">From its profile: ${esc(r.field)} is “${esc(r.value)}”</span></li>`)
    .join('');
  const fitSaid = pick.match ? fitNote(pick.match) : null;
  const tradeoffs = pick.tradeoffs
    .filter((t) => !RAN_ELSEWHERE.test(t) && t !== fitSaid)
    .map((t) => `<li>${esc(t)}</li>`)
    .join('');
  const guide = result.guides[pick.slug];
  const kind = entry ? kindLine(entry) : '';
  const links = [
    web ? link(web.url, `${icon('external-link')}Open it`) : '',
    link(pick.repo, `${icon('external-link')}Source code`),
    pick.homepage && pick.homepage !== pick.repo && pick.homepage !== web?.url ? link(pick.homepage, `${icon('external-link')}Homepage`) : '',
    link(pick.verification.os || web?.checked_at ? pick.evidence_url : null, `${icon('external-link')}Run record`),
  ].filter(Boolean);
  const gemNote = pick.scores.treasure ? 'little known' : undefined;
  // At a glance: who it is, why it fits in one sentence, the verdict, and the command. The rest waits behind one expander.
  return (
    `<article class="pick" id="pick-${esc(pick.slug)}" aria-labelledby="name-${esc(pick.slug)}">` +
    `<div class="t-top"><div>` +
    `<h3 class="t-name" id="name-${esc(pick.slug)}"><a href="/tool/${esc(pick.slug)}">${esc(pick.name)}</a></h3>` +
    (kind ? `<p class="t-kind">${esc(kind)}</p>` : '') +
    `</div>` +
    (badges ? `<p class="badges">${badges}</p>` : '') +
    `</div>` +
    `<p class="fit">${esc(pick.fit)}</p>` +
    (web ? webGlance(pick, entry) : glanceStrip(pick, guide, form)) +
    SEAM +
    (web ? webOpen(pick) : quickInstall(guide, form)) +
    `<details class="t-more"><summary>${icon('chevron-down')}Why it fits and how we know</summary><div class="t-more-body">` +
    `<div class="t-body"><div class="t-claim">` +
    // On the rules path the fit sentence is the summary: say it once.
    (pick.fit === pick.summary ? '' : `<p class="summary">${esc(pick.summary)}</p>`) +
    (pick.match ? matchCoverage(pick.match) : '') +
    (why ? `<h4>Why it fits</h4><ul class="why">${why}</ul>` : '') +
    (tradeoffs ? `<h4>Tradeoffs</h4><ul class="tradeoffs">${tradeoffs}</ul>` : '') +
    (pick.vs_well_known ? `<p class="vs"><span class="lead-in">Compared with better-known tools:</span> ${esc(pick.vs_well_known)}</p>` : '') +
    (best ? `<p><span class="lead-in">Best free option:</span> ${esc(best.reason)}</p>` : '') +
    facts(pick) +
    `</div><div class="t-measure">` +
    tape('Quality', pick.scores.quality, { pop: 'pop-quality' }) +
    tape('Popularity', pick.scores.popularity, { pop: 'pop-popularity', tone: 'quiet', note: gemNote }) +
    coverage(pick.features, { pop: 'pop-features' }) +
    `</div></div>` +
    (web ? webRecord(pick, entry) : record(pick, guide, form)) +
    (guide && !web ? installSection(guide, form, index === 0) : '') +
    (links.length ? `<p class="t-links">${links.join('')}</p>` : '') +
    `</div></details>` +
    `<div class="t-foot"><a class="more" href="/tool/${esc(pick.slug)}">Full profile${icon('arrow-right')}</a><span class="grow"></span>${compareToggle(pick.slug, pick.name)}</div>` +
    `</article>`
  );
}

const BY_RULES = 'these results are ranked by rules (the words in your request, then verification on your OS, then the hidden-gem score) without Muse Spark';
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
    text: 'These results are ranked by rules: the words in your request, then verification on your OS, then the hidden-gem score.',
  },
};
DEGRADED.no_api_key = DEGRADED.model_off;
DEGRADED.model_timeout = {
  title: 'Ranked without the model this time',
  text: 'Muse Spark didn’t answer in time, so these results are ranked by rules. Search again to retry.',
};
const MODEL_FAILED = {
  title: 'Ranked without the model this time',
  text: 'Muse Spark didn’t return a usable answer, so these results are ranked by rules. Search again to retry.',
};

/** The results heading says what came back, in words. */
function resultsTitle(out: FindOutput): string {
  const n = out.picks.length;
  if (n === 0) return 'Nothing fits yet';
  const tools = `${n} ${n === 1 ? 'tool' : 'tools'}`;
  if (out.matched_by === 'rules') {
    if (out.match_quality === 'none') return 'No clear fit, ranked by rules';
    if (out.match_quality === 'partial') return 'Partial fits, ranked by rules';
    return `${tools} ranked by rules`;
  }
  return `${tools} ${n === 1 ? 'fits' : 'fit'} your need`;
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

/** Fitz's face for a result: it only looks pleased when it has verified picks that fit. */
function resultsFitz(out: FindOutput): FitzName {
  if (out.picks.length === 0) return 'sorry';
  if (out.matched_by === 'rules') return out.match_quality === 'good' ? 'neutral' : 'thinking';
  return 'recommending';
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
  const said: string[] = [`<h2 class="results-title">${esc(resultsTitle(out))}</h2>`];
  if (out.considered > 0) said.push(`<p class="match-line">${matchLine(out)}</p>`);
  if (out.picks.length === 0) {
    said.push(`<p class="match-line">${esc(out.coverage_note ?? 'pickfit covers developer CLI tools, local AI tools and MCP servers today.')}</p>`);
  }
  // A partial or missing fit is said before the picks, not after them.
  const fitFirst = out.picks.length > 0 && (out.match_quality === 'partial' || out.match_quality === 'none') && out.coverage_note;
  const slugs = out.picks.map((p) => p.slug);
  const cmpHref = `/compare?tools=${slugs.map(encodeURIComponent).join(',')}${form.os ? `&amp;os=${form.os}` : ''}${form.arch ? `&amp;arch=${form.arch}` : ''}`;
  const tools = out.picks.length
    ? `<div class="res-tools"><button type="button" class="btn btn-quiet btn-sm js-only" data-open-legend>${icon('circle-help')}How to read a ticket</button>` +
      (out.picks.length > 1 ? `<a class="btn btn-quiet btn-sm" href="${cmpHref}">${icon('scale')}Compare these</a>` : '') +
      `</div>`
    : '';
  // Everything else the search has to say goes in one quiet status list under Fitz: one Fitz per screen.
  const status: string[] = [];
  if (out.degraded) {
    const d = out.degraded_reason === 'over_budget' ? BUDGET[opts.budget ?? 'other'] : (DEGRADED[out.degraded_reason ?? ''] ?? MODEL_FAILED);
    status.push(`<li class="st st-busy" role="status">${icon('clock')}<span><strong>${esc(d.title)}.</strong> ${esc(d.text)}</span></li>`);
  }
  if (fitFirst) {
    const note = out.coverage_note!;
    const cut = note.indexOf('. ');
    status.push(
      cut > 0 && cut < note.length - 2
        ? `<li class="st st-caution">${icon('triangle-alert')}<details><summary>${esc(note.slice(0, cut + 1))}</summary>${esc(note.slice(cut + 2))}</details></li>`
        : `<li class="st st-caution">${icon('triangle-alert')}<span>${esc(note)}</span></li>`,
    );
  }
  if (out.clarifying_question) {
    status.push(`<li class="st st-info">${icon('circle-help')}<span><strong>To narrow it down:</strong> ${esc(out.clarifying_question)} Set it above and search again.</span></li>`);
  }
  const head =
    `<div class="res-head">${says(resultsFitz(out), said.join(''), { size: 104 })}${tools}</div>` +
    (status.length ? `<ul class="res-status">${status.join('')}</ul>` : '');
  // "Built-in is enough" is said before anything is sold.
  if (out.no_install_option) {
    parts.push(
      `<div class="aside ask-note">${fitz('surprised', 64)}<div><h3>You may not need to install anything</h3><p>${esc(out.no_install_option)}</p>` +
        `<p class="quiet small">From Muse Spark’s general knowledge; pickfit hasn’t checked it.</p></div></div>`,
    );
  }
  if (out.picks.length) {
    parts.push(`<div class="picks">${out.picks.map((pick, i) => pickHtml(pick, i, result, form, catalog)).join('')}</div>`);
    if (out.coverage_note && !fitFirst) parts.push(`<p class="quiet small">${esc(out.coverage_note)}</p>`);
    const entries = slugs.map((s) => catalog.bySlug.get(s)).filter((e): e is Entry => !!e);
    if (entries.length > 1) {
      parts.push(
        `<details class="sbs"><summary>${icon('columns-3')}See these side by side</summary>` +
          compareTable(entries, { os: form.os || undefined, arch: form.arch || undefined, now: new Date(catalog.built_at) }) +
          `</details>`,
      );
    }
  }
  const free = out.best_free && !out.picks.some((p) => p.slug === out.best_free!.slug) ? catalog.bySlug.get(out.best_free.slug) : undefined;
  const freeWeb = free ? webCheck(free) : null;
  if (free && out.best_free && isWebApp(free)) {
    parts.push(
      `<div class="aside best-free"><p><span class="lead-in">Best free option:</span> ` +
        `<a href="/tool/${esc(free.slug)}">${esc(free.name)}</a>. ${esc(out.best_free.reason)}</p>` +
        (freeWeb ? `<p class="quiet">${esc(webRanSentence(freeWeb))}</p>` : '') +
        `<p class="mine mine-yes">${esc(NO_INSTALL_LABEL)}: it opens in a browser.</p></div>`,
    );
  } else if (free && out.best_free) {
    const guide = bestGuide(free, form.os || undefined);
    const v: PickOut['verification'] = {
      level: guide?.run.level ?? free.verification.level,
      os: guide?.run.os ?? null,
      arch: guide?.run.arch ?? null,
      method: guide?.run.method ?? null,
      replayed: guide?.run.replayed ?? false,
      checked_at: guide?.run.checked_at ?? null,
      verified_on_user_os: verifiedOnUserSystem(free, form.os || undefined, form.arch || undefined),
      gui: guide?.run.gui ?? null,
    };
    const mine = yourSystem(v, form);
    parts.push(
      `<div class="aside best-free"><p><span class="lead-in">Best free option:</span> ` +
        `<a href="/tool/${esc(free.slug)}">${esc(free.name)}</a>. ${esc(out.best_free.reason)}</p>` +
        `<p class="quiet">${esc(ranSentence(v))}</p><p class="mine mine-${mine.state}">${esc(mine.text)}</p></div>`,
    );
  }
  // Not verified: no stitches, no badge, no steps, no link. The missing record is the label.
  const wk = out.well_known_option;
  const outside = wk
    ? `<aside class="outside" aria-label="Not verified by pickfit">` +
      `<h3>Also consider ${esc(wk.name)}, not verified by pickfit</h3>${icon('circle-dashed')}` +
      `<p class="unchecked">pickfit has not installed or tested it. There is no run record and no install guide.</p>` +
      `<p>${esc(wk.why)}</p><p class="quiet small">${esc(wk.how_we_know)}</p></aside>`
    : '';
  if (outside && out.picks.length === 0) {
    // Nothing fits: Fitz's note on the left, the unverified option beside it.
    parts.unshift(`<div class="nofit"><div>${head}</div>${outside}</div>`);
  } else {
    parts.unshift(head);
    if (outside) parts.push(outside);
  }
  if (opts.cached) parts.push('<p class="quiet small">Shown from the same search made in the last few minutes.</p>');
  return parts.join('');
}

export function renderNotice(kind: 'busy' | 'error', title: string, text: string): string {
  return notice(kind, title, text, kind === 'busy' ? 'resting' : 'sorry');
}

// ---------------------------------------------------------------- home page

/** Examples on the page: tasks the catalog covers, written for this page. */
export const EXAMPLES: [string, string][] = [
  ['Subtitles from recordings, offline', 'Turn a folder of interview recordings into subtitles, offline'],
  ['Audit my MCP configs', 'Check my MCP server configs for risky permissions before I install one'],
  ['A codebase map for my agent', 'An MCP server that gives my coding agent a map of my codebase'],
  ['Free up port 3000', 'See which process holds port 3000 and stop it'],
];

const OS_CHOICES: [OS | '', string][] = [
  ['', 'Any OS'],
  ['macos', 'macOS'],
  ['linux', 'Linux'],
  ['windows', 'Windows'],
];
const ARCH_CHOICES: [Arch | '', string][] = [
  ['', 'Any CPU'],
  ['arm64', 'ARM64, Apple silicon'],
  ['x86_64', 'x86-64, Intel or AMD'],
];

/** The request: the need in the person's words, and their measurements. */
export function searchForm(form: FormValues): string {
  const os = OS_CHOICES.map(
    ([v, text]) => `<label><input type="radio" name="os" value="${v}"${v === form.os ? ' checked' : ''}>${text}</label>`,
  ).join('');
  const arch = ARCH_CHOICES.map(([v, text]) => `<option value="${v}"${v === form.arch ? ' selected' : ''}>${text}</option>`).join('');
  const tick = icon('check').replace('class="i', 'class="i chip-tick');
  return (
    `<form id="search" class="ask-card" method="post" action="/search#results">` +
    `<div class="ask"><label for="need">I need</label>` +
    `<textarea id="need" name="need" rows="1" minlength="3" maxlength="500" required autocomplete="off" spellcheck="true" ` +
    `placeholder="a free way to transcribe meeting recordings offline…">${esc(form.need)}</textarea></div>` +
    `<div class="ask-meta"><div class="ask-opts"><span class="label" id="os-label">Runs on</span>` +
    `<div class="seg" role="radiogroup" aria-labelledby="os-label">${os}</div>` +
    `<select class="select" name="arch" aria-label="CPU architecture">${arch}</select>` +
    `<label class="chip"><input type="checkbox" name="free_only" value="1"${form.free_only ? ' checked' : ''}>${tick}Free only</label>` +
    `<label class="chip"><input type="checkbox" name="offline" value="1"${form.offline ? ' checked' : ''}>${tick}Works offline</label>` +
    `<label class="chip"><input type="checkbox" name="private" value="1"${form.private ? ' checked' : ''}>${tick}Data stays on my device</label></div>` +
    `<div class="ask-go"><span class="counter" data-counter aria-live="polite"></span>` +
    `<button type="submit" class="btn btn-primary go"><span class="btn-label">Find my fit</span>${icon('arrow-right')}</button></div>` +
    `</div></form>`
  );
}

/** "How Fitz picks": the four steps, one line each; Fitz's own state shows what happens. */
function stagesSection(): string {
  const stages: { name: string; who: FitzName; text: string }[] = [
    { name: 'Read', who: 'thinking', text: 'Muse Spark reads the README and writes a profile.' },
    { name: 'Try it on', who: 'testing', text: 'Installed in a fresh sandbox, then replayed from scratch.' },
    { name: 'Match', who: 'searching', text: 'Your sentence meets every verified profile. Each reason is checked.' },
    { name: 'Hand over', who: 'recommending', text: 'You get the commands that worked.' },
  ];
  return (
    `<section id="how" class="sec wrap" aria-labelledby="how-title">` +
    `<div class="sec-head"><h2 id="how-title">How Fitz picks a tool</h2><a class="more" href="/how">The whole method${icon('arrow-right')}</a></div>` +
    `<ol class="stages">${stages
      .map((s) => `<li class="stage"><div class="stage-fitz">${fitz(s.who, 130)}</div><h3>${esc(s.name)}</h3><p>${esc(s.text)}</p></li>`)
      .join('')}</ol></section>`
  );
}

/** "Fresh off the fitting table": the newest runs, and one README the run corrected. */
function freshSection(showcase: Showcase): string {
  const { stats, recent, fix } = showcase;
  if (!recent.length) return '';
  const issue = fix ?? showcase.featured;
  const fixIssue = issue ? readerIssues(issue.guide.pitfalls)[0] : null;
  const fixCard =
    issue && fixIssue
      ? `<figure class="fix-card"><p class="fix-kicker">${icon('scissors')}A README the run corrected</p>` +
        `<h3><a href="/tool/${esc(issue.entry.slug)}">${esc(issue.entry.name)}</a></h3>` +
        `<ul class="readme-vs"><li class="was"><b>README said</b><span>${esc(fixIssue.readme_said)}</span></li>` +
        `<li class="now"><b>What worked</b><span>${esc(fixIssue.actually_needed)}</span></li></ul>` +
        `<figcaption>${esc(system(issue.guide.run.os, issue.guide.run.arch))}, ${esc(day(issue.guide.run.checked_at))}</figcaption></figure>`
      : '';
  const rows = recent
    .map(({ entry, guide }) => {
      const r = guide.run;
      return (
        `<li class="run-row"><a class="name" href="/tool/${esc(entry.slug)}">${esc(entry.name)}</a>` +
        (entry.scores?.treasure ? badge('gem', 'Hidden gem', { icon: 'gem' }) : '<span></span>') +
        `<p class="sum">${esc(entry.summary)}</p>` +
        `<p class="meta"><span>${esc(KIND[entry.category] ?? entry.category)}</span><span>${icon('badge-check')}${esc(system(r.os, r.arch))}, ${esc(day(r.checked_at, SHORT_DAY))}</span></p></li>`
      );
    })
    .join('');
  return (
    `<section id="recent" class="sec wrap home-only" aria-labelledby="recent-title">` +
    `<div class="sec-head"><div><h2 id="recent-title">Fresh off the fitting table</h2>` +
    `<p>${stats.replayed} of ${stats.listed} tools installed and replayed${stats.web ? `, and ${stats.web} web ${stats.web === 1 ? 'app' : 'apps'} used in a browser` : ''}. Only those are ever suggested.</p></div>` +
    `<a class="more" href="/browse">Browse all ${stats.verified}${icon('arrow-right')}</a></div>` +
    `<div class="fresh"><div>${fixCard}</div><ul class="runs-list">${rows}</ul></div></section>`
  );
}

const RULES: [Parameters<typeof icon>[0], string, string][] = [
  ['shield-check', 'Tried on before it’s suggested', 'Only tools pickfit installed in a sandbox are ever suggested, with the steps that worked.'],
  ['scale', 'Ranked by fit, not stars', 'Quality and popularity are scored apart. Nobody can pay to rank.'],
  ['circle-dashed', 'Unverified is said out loud', 'A well-known option Fitz hasn’t run is marked as such: no stitches, no steps.'],
  ['leaf', 'Built-in is enough, if it is', 'When you don’t need to install anything, Fitz says so first.'],
  ['tag', 'No ads, no referral links', 'pickfit doesn’t make any of the software it suggests, and keeps no account of you.'],
];

export function rulesLabel(): string {
  return (
    `<div class="label-tag"><ul class="rules" aria-label="Fitz’s rules">` +
    RULES.map(([ico, title]) => `<li>${icon(ico)}<b>${esc(title)}</b></li>`).join('') +
    `</ul></div>`
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

export function renderPage(input: PageInput): string {
  const { form, showcase } = input;
  const { stats } = showcase;
  const mcp = `${input.origin}/mcp`;
  const served = input.results !== '';
  const main =
    `<section class="hero mat after-top" aria-labelledby="title"><div class="wrap hero-grid"><div>` +
    `<h1 id="title">Software that <em>fits</em>, tried on first.</h1>` +
    `<p class="lede">Describe the job. Get little-known tools pickfit has already installed and tested, with the commands that worked.</p>` +
    `<div class="hero-form">${searchForm(form)}</div>` +
    `<div class="tries js-only"><span class="label">Or try</span>${EXAMPLES.map(([label, need]) => `<button type="button" class="try" data-need="${esc(need)}" title="${esc(need)}">${esc(label)}</button>`).join('')}</div>` +
    `<ul class="proof"><li>${icon('book-open')}<span><strong>${stats.listed}</strong> READMEs read</span></li>` +
    `<li>${icon('shield-check')}<span><strong>${stats.replayed}</strong> installed and replayed in a sandbox</span></li>` +
    (stats.web ? `<li>${icon('globe')}<span><strong>${stats.web}</strong> web ${stats.web === 1 ? 'app' : 'apps'} used in a browser</span></li>` : '') +
    `<li>${icon('gem')}<span><strong>${stats.gems}</strong> hidden gems</span></li></ul>` +
    `</div><div class="hero-fitz">${fitz('hello', 320, { eager: true })}</div></div>` +
    `<div class="ruler" aria-hidden="true"></div></section>` +
    `<p id="status" class="sr" aria-live="polite"></p>` +
    `<section id="results" class="results wrap" tabindex="-1" aria-label="Results">${input.results}</section>` +
    `<div class="home-only">` +
    stagesSection() +
    freshSection(showcase) +
    `<section id="rules" class="sec wrap" aria-labelledby="rules-title"><div class="care"><div>` +
    `<h2 id="rules-title">Fitz works for you, not for the tools.</h2>` +
    `<p class="quiet">No ads, no paid placement, no cut from anyone.</p>` +
    `<a class="more" href="/how#rules">Why you can trust a pick${icon('arrow-right')}</a></div>${rulesLabel()}</div></section>` +
    `<section id="agents" class="sec wrap" aria-labelledby="agents-title"><div class="agents-band mat"><div>` +
    `<h2 id="agents-title">Same answers, in your agent.</h2>` +
    `<p>The same picks over MCP, for Claude Code and any MCP client.</p>` +
    command(`claude mcp add --transport http pickfit ${mcp}`) +
    `</div><a class="btn btn-primary" href="/agents">${icon('bot')}Connect your agent</a></div></section>` +
    `</div>` +
    `<template id="loading"><div class="loading" role="status">` +
    says(
      'searching',
      `<h2>Measuring your request against ${stats.verified} verified tools…</h2>` +
        `<ol><li>Keep the tools that meet your OS, price, offline and privacy conditions</li><li>Muse Spark reads every remaining profile and picks the best fits</li><li>Code checks each reason against the profile</li></ol>` +
        `<p class="quiet small">Usually 5 to 15 seconds.</p><div class="unroll" aria-hidden="true"></div>`,
      { size: 104 },
    ) +
    `<div class="skel" aria-hidden="true"><i></i><i></i><i></i><i></i></div><div class="skel" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div></template>` +
    `<template id="offline">${notice('error', 'Couldn’t reach pickfit', 'Check your connection and search again.', 'test-failed')}</template>`;
  return renderShell({
    nonce: input.nonce,
    title: 'pickfit: software that fits, tried on first',
    description:
      'Describe the job in one sentence. pickfit suggests lesser-known developer CLI tools, local AI tools and MCP servers it has installed and tested, with the evidence and the steps that worked.',
    active: 'find',
    bodyClass: served ? 'is-results' : '',
    main,
  }).replace('<body class="is-results">', '<body class="is-results" data-served="1">');
}

/** Used by the browse and tool pages: verified OSes as a short phrase. */
export const verifiedOnWords = (entry: Entry) => {
  if (isWebApp(entry)) return webCheck(entry) ? 'Checked in a browser, any OS' : 'Not verified yet';
  const oses = verifiedOn(entry);
  return oses.length ? `Verified on ${listOf(oses.map((os) => osName(os)))}` : 'Not verified yet';
};

export { howRan, PRICE };
