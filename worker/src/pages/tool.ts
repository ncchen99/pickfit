/**
 * One tool, everything pickfit knows about it, so nobody has to open the
 * README to decide: the profile Muse Spark wrote, every run on every OS with
 * its steps, the features checked one by one, and the scores. Read from the
 * catalog only; nothing here calls a model. A tool without a run says so and
 * shows no steps.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type OS } from '../catalog.ts';
import { featuresOut } from '../features.ts';
import { installGuide } from '../install.ts';
import { EMPTY_FORM, installSection, levelLine, webFactList } from '../page.ts';
import { day, guiSentence, howRan, KIND, KIND_PLURAL, levelLabel, OS_NAME, osName, PRICE, PROCESSING, passed, system, kindLine, webLevelLabel } from '../ui/facts.ts';
import { esc, link, listOf, safeUrl } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { age, badge, compareToggle, coverage, fitz, SEAM, tape, type FitzName } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
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
      ? esc(listOf(verifiedOn(entry).map((os) => osName(os))))
      : '<span class="no">Not verified yet</span>';
  const rows: [string, string][] = [
    ['Kind', esc(kindLine(entry))],
    ['Verified on', verifiedCell],
    web
      ? ['Runs in', 'Any modern browser, nothing to install']
      : ['Claims to run on', entry.platforms.length ? esc(listOf(entry.platforms.map((os) => osName(os)))) : unknown],
    ['Price', entry.pricing ? esc(PRICE[entry.pricing]) + (entry.pricing_note ? `<div class="small quiet">${esc(entry.pricing_note)}</div>` : '') : unknown],
    ['Runs', entry.processing ? esc(PROCESSING[entry.processing]) : unknown],
    ['Licence', entry.license ? `<code>${esc(entry.license)}</code>${entry.open_source ? ' <span class="small quiet">open source</span>' : ''}` : unknown],
    ['Last release', entry.last_release ? `${esc(day(entry.last_release))} <span class="small quiet">(${esc(age(entry.last_release, now) ?? '')})</span>` : unknown],
  ].filter(([k]) => !web || (k !== 'Runs' && k !== 'Last release')) as [string, string][];
  if (entry.maturity) rows.push(['Maturity', esc(MATURITY[entry.maturity] ?? entry.maturity)]);
  return `<dl class="facts-dl">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join('')}</dl>`;
}

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
  return items.length
    ? `<ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul>`
    : '<p class="quiet">The README lists nothing you need first.</p>';
}

/** features.ts writes "<reason>: <the run's note>"; a person needs only the note when there is one. */
const featureWhy = (detail: string) => {
  const at = detail.indexOf(': ');
  return (at > 0 ? detail.slice(at + 2) : detail).replace(/^not checked:?\s*/i, '');
};

/** Every advertised feature with what the run did about it. */
function featureList(entry: Entry): string {
  const guide = bestGuide(entry);
  const f = featuresOut(entry, guide);
  if (!f.checked.length && !f.not_checked.length) return '';
  const items = [
    ...f.checked.map(
      (c) => `<li class="feat-ok">${icon('check')}<div>${esc(c.feature)}<details class="feat-check"><summary>Checked</summary><code>${esc(c.check)}</code></details></div></li>`,
    ),
    ...f.not_checked.map((n) => {
      const failed = n.reason === 'test_failed';
      return `<li class="${failed ? 'feat-fail' : 'feat-open'}">${icon(failed ? 'x' : 'circle-dashed')}<div>${esc(n.feature)}<small>${failed ? 'Failed: ' : 'Not checked: '}${esc(featureWhy(n.detail))}</small></div></li>`;
    }),
  ];
  return (
    `<section class="block" aria-labelledby="features-title"><h2 id="features-title">What it does, feature by feature</h2>` +
    (f.recorded ? '' : '<p class="quiet">This run came before pickfit checked features one by one, so these come from the README only.</p>') +
    `<ul class="feat-list">${items.join('')}</ul></section>`
  );
}

/** A web app: open it, and what pickfit's browser saw when it did. */
function webRun(entry: Entry): string {
  const check = webCheck(entry);
  const url = entry.web!.url;
  const open = link(url, `${icon('external-link')}Open ${esc(entry.name)}`, 'btn btn-primary btn-sm');
  if (!check) {
    return (
      `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">Open it</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p><b>pickfit hasn’t checked ${esc(entry.name)} in its browser yet</b>, so it never suggests it.</p>` +
      `<p class="quiet">The profile above comes from its own site only.</p></div></div></section>`
    );
  }
  const evidence = safeUrl(check.evidence_url);
  return (
    `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">Open it</h2>` +
    `<article class="run-card" id="run-web"><div class="run-head"><h3>${esc(NO_INSTALL_LABEL)}</h3>` +
    `<span class="badges">${badge('pass', 'Checked in a browser', { icon: 'check' })}</span></div>` +
    SEAM +
    levelLine(webLevelLabel(check), true) +
    `<p>${esc(webRanSentence(check))}</p>` +
    webFactList(entry) +
    (open ? `<p class="t-open">${open}<span class="quiet small" translate="no">${esc(url)}</span></p>` : '') +
    (evidence ? `<p>${link(evidence, `${icon('external-link')} Run record`)}</p>` : '') +
    `</article></section>`
  );
}

/** One run per verified OS: the record, then the steps that worked there. */
function runs(catalog: Catalog, entry: Entry): string {
  if (isWebApp(entry) && entry.web) return webRun(entry);
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    return (
      `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">Install</h2>` +
      `<div class="empty">${fitz('thinking', 80)}<div><p><b>pickfit hasn’t verified ${esc(entry.name)} yet</b>, so it gives no install steps and never suggests it.</p>` +
      `<p class="quiet">${entry.verification.level === 'failed' ? 'A verification run did not pass. ' : ''}The profile above comes from its README only.</p></div></div></section>`
    );
  }
  const cards = oses.map((os: OS, i) => {
    const g = entry.install[os]!;
    const out = installGuide(catalog, { slug: entry.slug, os });
    const r = g.run;
    const label = levelLabel(r.level, { gui: r.gui, mcp: g.mcp });
    const extra = [
      g.works_offline === true ? 'Its checks passed again with the network off.' : g.works_offline === false ? 'Its checks failed with the network off.' : '',
      r.tool_version ? `Version ${r.tool_version}.` : '',
    ].filter(Boolean);
    const evidence = safeUrl(r.evidence_url);
    return (
      `<article class="run-card" id="run-${os}"><div class="run-head"><h3>${esc(OS_NAME[os])}</h3>` +
      `<span class="badges">${badge('pass', `Ran on ${system(r.os, r.arch)}`, { icon: 'check' })}${r.replayed ? badge('info', 'Replayed from scratch', { icon: 'refresh-cw' }) : ''}</span></div>` +
      SEAM +
      levelLine(label, passed(r.gui)) +
      `<p>${esc(howRan(r))}, ${esc(day(r.checked_at))}. ${esc(extra.join(' '))}</p>` +
      (r.gui ? `<p>${esc(guiSentence(r.gui))}</p>` : '') +
      (g.mcp ? `<p>An MCP client handshake over ${g.mcp.transport === 'stdio' ? 'stdio' : 'HTTP'} listed ${g.mcp.tool_count} tool${g.mcp.tool_count === 1 ? '' : 's'}${g.mcp.called_tool ? `, and a call to <code>${esc(g.mcp.called_tool)}</code> returned a result` : ''}.</p>` : '') +
      (evidence ? `<p>${link(evidence, `${icon('external-link')} Run record`)}</p>` : '') +
      installSection(out, { ...EMPTY_FORM, os }, i === 0) +
      `</article>`
    );
  });
  return `<section class="block" aria-labelledby="runs-title"><h2 id="runs-title">Install steps that worked</h2>${cards.join('')}</section>`;
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
    web ? badge('info', NO_INSTALL_LABEL, { icon: 'globe' }) : '',
    web
      ? badge('pass', `Verified: ${webLevelLabel(web)}`, { icon: 'badge-check' })
      : verified && guide
        ? badge('pass', `Verified: ${levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp })}`, { icon: 'badge-check' })
        : badge('quiet', 'Not verified yet', { icon: 'circle-dashed' }),
    entry.scores?.treasure ? badge('gem', 'Hidden gem', { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  const webUrl = entry.web?.url ?? null;
  const links = [
    webUrl ? link(webUrl, `${icon('external-link')}Open it`, 'btn btn-on-mat btn-sm') : '',
    link(entry.repo_url, `${icon('external-link')}Source code`, 'btn btn-on-mat btn-sm'),
    entry.homepage && entry.homepage !== entry.repo_url && entry.homepage !== webUrl ? link(entry.homepage, `${icon('external-link')}Homepage`, 'btn btn-on-mat btn-sm') : '',
  ].join('');
  const about = [
    entry.why_worth_it ? `<p class="fit">${esc(entry.why_worth_it)}</p>` : '',
    entry.use_cases.length ? `<h3>Good for</h3><ul class="uses">${entry.use_cases.map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : '',
    entry.alternatives_to.length ? `<p><span class="lead-in">An alternative to</span> ${esc(listOf(entry.alternatives_to))}.</p>` : '',
    isWebApp(entry) ? '' : `<h3>Before you install</h3>${prerequisites(entry)}`,
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
    `<section class="block" aria-labelledby="about-title"><h2 id="about-title">What it is</h2>${about}</section>` +
    runs(catalog, entry) +
    featureList(entry) +
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
