/**
 * One tool, for a person deciding whether to use it: what it looks like (pickfit's clip of it running),
 * how far pickfit got with it, what it does (each advertised feature, ticked when a run checked it, with
 * how to use it), and how to install it. How pickfit tested it sits folded at the bottom, for anyone who
 * wants the evidence. Read from the catalog only; nothing here calls a model. The plain feature titles,
 * steps and open hint come from the record's usage_guide, which names the model that wrote them.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type InstallGuide, type OS, type RunVideo } from '../catalog.ts';
import { featuresOut, type FeaturesOut } from '../features.ts';
import { installGuide, type InstallOutput } from '../install.ts';
import { EMPTY_FORM, installSection, levelLine, webFactList } from '../page.ts';
import { day, guiSentence, KIND, KIND_PLURAL, levelLabel, OS_NAME, PRICE, PROCESSING, passed, webLevelLabel } from '../ui/facts.ts';
import { esc, link, listOf, safeUrl } from '../ui/html.ts';
import { icon, osMark, type IconName } from '../ui/icons.ts';
import { age, badge, compareToggle, coverage, fitz, kindTag, levelIcon, osList, runFacts, SEAM, tape, type FitzName } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
import { posterOf, videoPath } from '../video.ts';
import { NO_INSTALL_LABEL, webRanSentence } from '../webapp.ts';

const MATURITY: Record<string, string> = { stable: 'Stable', beta: 'Beta', alpha: 'Alpha', prototype: 'Prototype' };

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
  const unknown = '<span class="unknown">not stated</span>';
  const web = isWebApp(entry);
  const check = webCheck(entry);
  const verifiedCell = web
    ? check
      ? `In a browser, ${esc(day(check.checked_at))}`
      : '<span class="no">Not verified yet</span>'
    : verifiedOn(entry).length
      ? osList(verifiedOn(entry), { tone: 'pass' })
      : '<span class="no">Not verified yet</span>';
  const rows: [string, string][] = [
    ['Kind', kindTag(entry)],
    ['Verified on', verifiedCell],
    web
      ? ['Runs in', 'Any modern browser, nothing to install']
      : ['Claims to run on', entry.platforms.length ? osList(entry.platforms, { tone: 'quiet' }) : unknown],
    ['Price', entry.pricing ? esc(PRICE[entry.pricing]) + (entry.pricing_note ? `<div class="small quiet">${esc(entry.pricing_note)}</div>` : '') : unknown],
    ['Runs', entry.processing ? esc(PROCESSING[entry.processing]) : unknown],
    ['Licence', entry.license ? `<code>${esc(entry.license)}</code>${entry.open_source ? ' <span class="small quiet">open source</span>' : ''}` : unknown],
    ['Last release', entry.last_release ? `${esc(day(entry.last_release))} <span class="small quiet">(${esc(age(entry.last_release, now) ?? '')})</span>` : unknown],
  ].filter(([k]) => !web || (k !== 'Runs' && k !== 'Last release')) as [string, string][];
  if (entry.maturity) rows.push(['Maturity', esc(MATURITY[entry.maturity] ?? entry.maturity)]);
  return `<dl class="facts-dl">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
}

/** What the README says you need first; nothing when it lists nothing. */
function prerequisites(entry: Entry): string {
  const p = entry.prerequisites;
  const items: string[] = [];
  if (p.runtimes.length) items.push(`Runtimes: ${p.runtimes.map((r) => `<code>${esc(r)}</code>`).join(', ')}`);
  if (p.system_packages.length) items.push(`System packages: ${p.system_packages.map((r) => `<code>${esc(r)}</code>`).join(', ')}`);
  if (p.gpu === 'required') items.push('A GPU is required');
  else if (p.gpu === 'optional') items.push('A GPU is optional');
  if (p.min_ram_gb) items.push(`At least ${p.min_ram_gb} GB of RAM`);
  if (p.apple_silicon_only) items.push('Apple silicon only');
  if (p.network === 'required') items.push('Needs the network');
  if (p.api_keys.length) items.push(`Keys or accounts: ${p.api_keys.map(esc).join(', ')}`);
  return items.length ? `<div class="prereq"><h3>You need first</h3><ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul></div>` : '';
}

/** The first run with a clip: install guides first (they are what a reader follows), then other passed runs. */
function firstVideo(entry: Entry): { slug: string; video: RunVideo } | null {
  const runs = [...OSES.flatMap((os) => (entry.install[os] ? [entry.install[os].run] : [])), ...entry.verification.passed_runs];
  const run = runs.find((r) => r.video);
  return run?.video ? { slug: entry.slug, video: run.video } : null;
}

/** The app itself, first: pickfit's own clip of it running. */
function showcase(entry: Entry): string {
  const found = firstVideo(entry);
  if (!found) return '';
  const { slug, video } = found;
  return (
    `<figure class="showcase">` +
    `<video controls preload="metadata" playsinline poster="${esc(videoPath(slug, posterOf(video.clip)))}" aria-describedby="showcase-cap">` +
    `<source src="${esc(videoPath(slug, video.clip))}" type="video/mp4">` +
    `<a href="${esc(videoPath(slug, video.clip))}">Download the clip</a></video>` +
    `<figcaption id="showcase-cap">${esc(entry.name)} running, recorded by pickfit on ${esc(day(video.recorded_at))} · ${Math.round(video.seconds)} s</figcaption>` +
    `</figure>`
  );
}

// ---------------------------------------------------------------- how far pickfit got

type StageState = 'done' | 'open' | 'warn';
interface Stage {
  label: string;
  state: StageState;
  tip: string;
}

/** A run's progress in four stages a reader can scan: installed, started, used, offline. */
function stagesFor(entry: Entry, g: InstallGuide): Stage[] {
  const r = g.run;
  const gui = r.gui ?? null;
  const f = featuresOut(entry, g);
  const total = f.checked.length + f.not_checked.length;
  const deep = r.level !== 'install' || f.checked.length > 0;
  const started: Stage = gui
    ? passed(gui)
      ? { label: gui.screen === 'main_ui' ? 'Opens' : 'Opens to its setup screen', state: 'done', tip: 'Its window came up on a clean machine' }
      : { label: 'Window shows a problem', state: 'warn', tip: 'Its window showed an error or stayed blank' }
    : g.mcp
      ? { label: 'Connects', state: 'done', tip: 'An MCP client connected and listed its tools' }
      : { label: 'Starts', state: 'done', tip: 'It ran on a clean machine' };
  const used: Stage =
    f.recorded && total
      ? { label: `${f.checked.length} of ${total} features work`, state: f.checked.length ? 'done' : 'open', tip: 'Features pickfit used and checked' }
      : deep
        ? {
            label: g.mcp ? 'A tool call works' : r.level === 'inference' ? 'Produces output' : r.level === 'service' ? 'Answers requests' : 'Main function works',
            state: 'done',
            tip: 'pickfit used it, not just started it',
          }
        : { label: 'Not used yet', state: 'open', tip: 'pickfit started it but did not use a feature' };
  const offline = gui ? gui.launch_offline : g.works_offline;
  const net: Stage =
    offline === true
      ? { label: 'Works offline', state: 'done', tip: 'It passed again with the network off' }
      : offline === false
        ? { label: 'Needs the network', state: 'open', tip: 'It needed the network to work' }
        : { label: 'Offline not checked', state: 'open', tip: 'pickfit did not try it without the network' };
  return [{ label: 'Installs', state: 'done', tip: 'Its install steps worked on a clean machine' }, started, used, net];
}

function stageRow(stages: Stage[]): string {
  const mark: Record<StageState, IconName> = { done: 'check', open: 'circle-dashed', warn: 'triangle-alert' };
  return (
    `<ol class="stages">` +
    stages.map((s) => `<li class="stage stage-${s.state}" data-tip="${esc(s.tip)}"><span class="stage-bar"></span><span class="stage-label">${icon(mark[s.state])}${esc(s.label)}</span></li>`).join('') +
    `</ol>`
  );
}

/** One row per verified system, and the systems the project claims that pickfit has not tried. */
function progress(entry: Entry): string {
  if (isWebApp(entry)) {
    const check = webCheck(entry);
    if (!check) return '';
    const f = featuresOut(entry, null);
    const total = f.checked.length + f.not_checked.length;
    const stages: Stage[] = [
      { label: 'Opens in a browser', state: 'done', tip: 'Its main screen loaded in pickfit’s browser' },
      total
        ? { label: `${f.checked.length} of ${total} features work`, state: f.checked.length ? 'done' : 'open', tip: 'Features pickfit used and checked' }
        : { label: check.level === 'function' ? 'Used in a browser' : 'Not used yet', state: check.level === 'function' ? 'done' : 'open', tip: webLevelLabel(check) },
    ];
    return `<section class="block progress" aria-labelledby="progress-title"><h2 id="progress-title">How far pickfit got</h2>${stageRow(stages)}</section>`;
  }
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    return (
      `<section class="block" aria-labelledby="progress-title"><h2 id="progress-title">How far pickfit got</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p><b>pickfit hasn’t verified ${esc(entry.name)} yet</b>, so it gives no install steps and never suggests it.</p>` +
      `<p class="quiet">${entry.verification.level === 'failed' ? 'A verification run did not pass. ' : ''}What follows comes from its README only.</p></div></div></section>`
    );
  }
  const rows = oses.map((os) => {
    const g = entry.install[os]!;
    return `<div class="progress-row"><p class="progress-sys">${osMark(os)}${esc(OS_NAME[os])}${g.run.arch ? ` <span class="arch">${esc(g.run.arch)}</span>` : ''}</p>${stageRow(stagesFor(entry, g))}</div>`;
  });
  const untried = entry.platforms.filter((os) => !entry.install[os]);
  const note = untried.length ? `<p class="small quiet">${esc(listOf(untried.map((os) => OS_NAME[os])))}: the project says it runs there; pickfit hasn’t tried it.</p>` : '';
  return `<section class="block progress" aria-labelledby="progress-title"><h2 id="progress-title">How far pickfit got</h2>${rows.join('')}${note}</section>`;
}

// ---------------------------------------------------------------- what it does

/** features.ts writes "<reason>: <the run's note>"; a person needs only the note when there is one. */
const featureWhy = (detail: string) => {
  const at = detail.indexOf(': ');
  return (at > 0 ? detail.slice(at + 2) : detail).replace(/^not checked:?\s*/i, '');
};

/** The raw recording that shows one feature, from the run behind the steps. */
function featureClip(entry: Entry, feature: string): string {
  const found = firstVideo(entry);
  const raw = found?.video.raw.find((r) => r.feature === feature);
  return raw ? `<a class="watch" href="${esc(videoPath(entry.slug, raw.file))}">${icon('play')}Watch it (${Math.round(raw.seconds)} s)</a>` : '';
}

/** `code` spans in generated steps; everything else escaped. */
const stepText = (s: string) => esc(s).replace(/`([^`]+)`/g, '<code translate="no">$1</code>');

function featureList(entry: Entry, f: FeaturesOut): string {
  const guide = entry.usage_guide ?? null;
  const titles = new Map((guide?.features ?? []).map((g) => [g.feature, g]));
  const title = (feature: string) => esc(titles.get(feature)?.title ?? feature.charAt(0).toUpperCase() + feature.slice(1));
  const items = [
    ...f.checked.map(({ feature }) => {
      const steps = titles.get(feature)?.steps ?? [];
      const clip = featureClip(entry, feature);
      const how = steps.length || clip
        ? `<details class="how-to"><summary>How to use it</summary>${steps.length ? `<ol>${steps.map((s) => `<li>${stepText(s)}</li>`).join('')}</ol>` : ''}${clip}</details>`
        : '';
      return `<li class="feat-ok">${icon('check')}<div><span class="feat-title">${title(feature)}</span> <span class="feat-tag">Tested</span>${how}</div></li>`;
    }),
    ...f.not_checked.map((n) => {
      const failed = n.reason === 'test_failed';
      return (
        `<li class="${failed ? 'feat-fail' : 'feat-open'}">${icon(failed ? 'x' : 'circle-dashed')}<div><span class="feat-title">${title(n.feature)}</span>` +
        `<small>${failed ? 'Its test failed: ' : 'Not tested: '}${esc(featureWhy(n.detail))}</small></div></li>`
      );
    }),
  ];
  if (!items.length) return '';
  const ran = bestGuide(entry) !== null || webCheck(entry) !== null;
  const from = f.recorded ? '' : `<p class="quiet">${notRecorded(entry, ran)}</p>`;
  const by = guide ? `<p class="small quiet">Feature names and steps written by ${esc(guide.model)} from what pickfit’s run did.</p>` : '';
  return `${from}<ul class="feat-list">${items.join('')}</ul>${by}`;
}

/** Why the features come from the profile alone: a run from before feature checks, or no run at all. */
const notRecorded = (entry: Entry, ran: boolean) =>
  ran
    ? 'This run came before pickfit checked features one by one, so these come from the README only.'
    : `pickfit hasn’t run it yet, so these come from ${isWebApp(entry) ? 'its own site' : 'the README'} only.`;

function about(entry: Entry, f: FeaturesOut): string {
  const parts = [
    entry.why_worth_it ? `<p class="fit">${esc(entry.why_worth_it)}</p>` : '',
    featureList(entry, f),
    entry.use_cases.length ? `<h3>Good for</h3><ul class="uses">${entry.use_cases.map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : '',
    entry.alternatives_to.length ? `<p><span class="lead-in">An alternative to</span> ${esc(listOf(entry.alternatives_to))}.</p>` : '',
  ].join('');
  return parts ? `<section class="block" aria-labelledby="about-title"><h2 id="about-title">What it does</h2>${parts}</section>` : '';
}

// ---------------------------------------------------------------- install

/** The guide as a reader follows it: README mistakes only, no trailing stderr redirect, and for a GUI app where to find it instead of a shell command. */
function readerGuide(out: InstallOutput, hint: string | null, gui: boolean): InstallOutput {
  return {
    ...out,
    steps: out.steps.map((s) => ({ ...s, command: s.command.replace(/\s+2>&1$/, '') })),
    known_issues: out.known_issues.filter((k) => k.kind === 'readme_wrong' || !k.kind),
    first_task: gui && hint ? null : out.first_task,
    first_task_setup: gui && hint ? [] : out.first_task_setup,
  };
}

function install(catalog: Catalog, entry: Entry): string {
  if (isWebApp(entry) && entry.web) return webRun(entry);
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) return prerequisites(entry) ? `<section class="block" aria-labelledby="install-title"><h2 id="install-title">Install</h2>${prerequisites(entry)}</section>` : '';
  const hint = entry.usage_guide?.open_hint ?? null;
  const cards = oses.map((os: OS, i) => {
    const g = entry.install[os]!;
    const gui = !!g.run.gui;
    const out = readerGuide(installGuide(catalog, { slug: entry.slug, os }), hint, gui);
    return (
      `<article class="run-card" id="install-${os}"><div class="run-head"><h3>${osMark(os)}${esc(OS_NAME[os])}${g.run.arch ? ` <span class="arch">${esc(g.run.arch)}</span>` : ''}</h3></div>` +
      installSection(out, { ...EMPTY_FORM, os }, i === 0, true) +
      (hint ? `<p class="open-hint">${icon('arrow-right')}${stepText(hint)}</p>` : '') +
      `</article>`
    );
  });
  return `<section class="block" aria-labelledby="install-title"><h2 id="install-title">Install</h2>${prerequisites(entry)}${cards.join('')}</section>`;
}

/** A web app: open it, and what pickfit's browser saw when it did. */
function webRun(entry: Entry): string {
  const check = webCheck(entry);
  const url = entry.web!.url;
  const open = link(url, `${icon('external-link')}Open ${esc(entry.name)}`, 'btn btn-primary btn-sm');
  if (!check) {
    return (
      `<section class="block" aria-labelledby="install-title"><h2 id="install-title">Open it</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p><b>pickfit hasn’t checked ${esc(entry.name)} in its browser yet</b>, so it never suggests it.</p>` +
      `<p class="quiet">The profile above comes from its own site only.</p></div></div></section>`
    );
  }
  return (
    `<section class="block" aria-labelledby="install-title"><h2 id="install-title">Open it</h2>` +
    `<article class="run-card" id="run-web"><div class="run-head"><h3>${esc(NO_INSTALL_LABEL)}</h3></div>` +
    webFactList(entry) +
    (open ? `<p class="t-open">${open}<span class="quiet small" translate="no">${esc(url)}</span></p>` : '') +
    `</article></section>`
  );
}

// ---------------------------------------------------------------- how pickfit tested it

function rawList(slug: string, video: RunVideo): string {
  const raw = video.raw
    .map(
      (r) =>
        `<li><a href="${esc(videoPath(slug, r.file))}" download>${esc(r.file)}</a> <span class="quiet">(${Math.round(r.seconds)} s${r.feature ? `, ${esc(r.feature)}` : ''})</span>` +
        `<br><span class="quiet small">sha256</span> <code class="hash" translate="no">${esc(r.sha256)}</code></li>`,
    )
    .join('');
  return (
    `<p class="small">Clip <code class="hash" translate="no">${esc(video.clip)}</code>, sha256 <code class="hash" translate="no">${esc(video.clip_sha256)}</code>. It was cut from these unedited recordings:</p>` +
    `<ul class="small raw-list">${raw}</ul>`
  );
}

/** Everything a skeptic wants and a user doesn't: where each run ran, who looked, the raw recordings, the sandbox-only differences. */
function tested(catalog: Catalog, entry: Entry): string {
  const parts: string[] = [];
  if (isWebApp(entry)) {
    const check = webCheck(entry);
    if (!check) return '';
    const evidence = safeUrl(check.evidence_url);
    parts.push(
      levelLine(webLevelLabel(check), true) +
        `<p>${esc(webRanSentence(check))}</p>` +
        (evidence ? `<p>${link(evidence, `${icon('external-link')} Run record`)}</p>` : ''),
    );
  }
  for (const os of OSES.filter((o) => entry.install[o])) {
    const g = entry.install[os]!;
    const r = g.run;
    const evidence = { gui: r.gui, mcp: g.mcp };
    const recordUrl = safeUrl(r.evidence_url);
    const box = installGuide(catalog, { slug: entry.slug, os }).known_issues.filter((k) => k.kind && k.kind !== 'readme_wrong');
    parts.push(
      `<div class="tested-run"><h3>${osMark(os)}${esc(OS_NAME[os])}${r.arch ? ` <span class="arch">${esc(r.arch)}</span>` : ''}</h3>` +
        levelLine(levelLabel(r.level, evidence), passed(r.gui), levelIcon(r.level, evidence)) +
        runFacts(r, { offline: r.gui ? null : g.works_offline, named: true }) +
        (r.gui ? `<p>${esc(guiSentence(r.gui))}</p>` : '') +
        (g.mcp ? `<p>An MCP client handshake over ${g.mcp.transport === 'stdio' ? 'stdio' : 'HTTP'} listed ${g.mcp.tool_count} tool${g.mcp.tool_count === 1 ? '' : 's'}${g.mcp.called_tool ? `, and a call to <code>${esc(g.mcp.called_tool)}</code> returned a result` : ''}.</p>` : '') +
        (r.video ? rawList(entry.slug, r.video) : '') +
        (box.length
          ? `<h4>Differences the test machine hit</h4><ul class="issues">${box.map((i) => `<li><span class="quiet">README:</span> ${esc(i.readme_said)}<br><span class="quiet">In the test:</span> ${esc(i.actually_needed)}</li>`).join('')}</ul>`
          : '') +
        (recordUrl ? `<p>${link(recordUrl, `${icon('external-link')} Run record`)}</p>` : '') +
        `</div>`,
    );
  }
  if (!parts.length) return '';
  return (
    `<details class="block tested"><summary><h2>How pickfit tested it</h2>${icon('chevron-down')}</summary>` +
    `<p class="quiet">Each run starts from a clean machine, follows the steps above, and checks the result itself. <a href="/how">How pickfit verifies</a></p>` +
    `${parts.join('')}</details>`
  );
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
  const on = verifiedOn(entry);
  const badges = [
    web ? badge('info', NO_INSTALL_LABEL, { icon: 'globe' }) : '',
    web
      ? badge('pass', 'Tested in a browser', { icon: 'badge-check' })
      : verified && on.length
        ? badge('pass', `Tested on ${listOf(on.map((os) => OS_NAME[os]))}`, { icon: 'badge-check' })
        : badge('quiet', 'Not verified yet', { icon: 'circle-dashed' }),
    entry.scores?.treasure ? badge('gem', 'Hidden gem', { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  const webUrl = entry.web?.url ?? null;
  const links = [
    webUrl ? link(webUrl, `${icon('external-link')}Open it`, 'btn btn-on-mat btn-sm') : '',
    !web && OSES.some((os) => entry.install[os]) ? `<a class="btn btn-on-mat btn-sm" href="#install-title">${icon('arrow-right')}Install</a>` : '',
    link(entry.repo_url, `${icon('external-link')}Source code`, 'btn btn-on-mat btn-sm'),
    entry.homepage && entry.homepage !== entry.repo_url && entry.homepage !== webUrl ? link(entry.homepage, `${icon('external-link')}Homepage`, 'btn btn-on-mat btn-sm') : '',
  ].join('');
  const sources = entry.sources
    .map((s) => safeUrl(s))
    .filter((s): s is string => !!s)
    .map((s) => `<li>${link(s, esc(s.replace(/^https?:\/\//, '').replace(/^api\.github\.com\/repos\//, 'github.com/')))}</li>`)
    .join('');
  const main =
    `<section class="head mat after-top"><div class="wrap">` +
    `<p class="crumbs"><a href="/browse">Browse</a>${icon('arrow-right')}${crumb(entry)}</p>` +
    `<div class="head-row"><div><h1>${esc(entry.name)}</h1><p class="lede">${esc(entry.summary)}</p>` +
    `<p class="badges">${badges}</p><p class="badges">${links}${verified ? compareToggle(entry.slug, entry.name) : ''}</p></div>` +
    `${fitz(faceFor(entry), 150, { eager: true })}</div></div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap layout"><div>` +
    showcase(entry) +
    progress(entry) +
    about(entry, features) +
    install(catalog, entry) +
    tested(catalog, entry) +
    `</div><aside class="side" aria-label="At a glance">` +
    `<div class="panel"><h2>At a glance</h2>${factSheet(entry, now)}<div class="t-measure panel-measure">` +
    tape('Quality', entry.scores?.quality ?? null, { pop: 'pop-quality' }) +
    tape('Popularity', entry.scores?.popularity ?? null, { pop: 'pop-popularity', tone: 'quiet' }) +
    coverage(features, { pop: 'pop-features' }) +
    `</div><p class="small quiet">Scored apart; ranked by neither. <a href="/how#scores">How scores work</a></p></div>` +
    (sources ? `<details class="panel sources"><summary>Sources</summary><ul class="small">${sources}</ul><p class="small quiet">Every field in the profile cites one of these.</p></details>` : '') +
    `</aside></div>`;
  return renderShell({
    nonce,
    title: `${entry.name}: ${web ? 'checked in a browser' : verified ? 'verified install steps' : 'profile'} · pickfit`,
    description: entry.summary,
    active: 'browse',
    main,
  });
}
