/**
 * Side by side: the same facts for two to four tools, straight from the
 * catalog (no model call). A row marks the best value only where "best" is a
 * plain comparison of recorded numbers or dates: fewest setup commands, most
 * features checked, highest quality score, newest release. Nothing else is
 * ranked.
 */
import { bestGuide, nameKey, OSES, verifiedOn, type Arch, type Catalog, type Entry, type OS } from '../catalog.ts';
import { featuresOut } from '../features.ts';
import { day, levelLabel, OS_NAME, osName, PRICE, PROCESSING, passed, readerIssues, setupWords, system, kindLine } from '../ui/facts.ts';
import { esc, link, listOf, SLUG } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { age, badge, coverage, fitz, tape } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';

export const COMPARE_MAX = 4;

interface Opts {
  os?: OS;
  arch?: Arch;
  now: Date;
  /** Show a remove link per column (the compare page). */
  removable?: string[];
}

const BEST = `<span class="best">${icon('check')}best here</span>`;

/** The compare table for these entries; `os` decides which run each column shows. */
export function compareTable(entries: Entry[], opts: Opts): string {
  const guides = entries.map((e) => bestGuide(e, opts.os));
  const feats = entries.map((e, i) => featuresOut(e, guides[i]));
  const cols = entries.length;
  const unknown = '<span class="unknown">not stated</span>';

  /** Index of the single best value, or -1 when it is tied or missing. */
  const bestOf = (values: (number | null)[], low = false): number => {
    const known = values.map((v, i) => [v, i] as const).filter(([v]) => v !== null) as [number, number][];
    if (known.length < 2) return -1;
    const top = known.reduce((a, b) => ((low ? b[0] < a[0] : b[0] > a[0]) ? b : a));
    return known.filter(([v]) => v === top[0]).length === 1 ? top[1] : -1;
  };
  /** Rows where every tool says the same thing leave the table for one "same for all" line: only differences compete. */
  const same: string[] = [];
  const row = (label: string, cells: string[], best = -1) => {
    if (cols > 1 && cells.every((c) => c === cells[0])) {
      same.push(`<div><dt>${esc(label)}</dt><dd>${cells[0]}</dd></div>`);
      return '';
    }
    return `<tr><th scope="row">${esc(label)}</th>${cells.map((c, i) => `<td>${c}${i === best ? BEST : ''}</td>`).join('')}</tr>`;
  };
  const group = (label: string) => `<tr class="grp"><th colspan="${cols + 1}" scope="colgroup">${esc(label)}</th></tr>`;

  const head = entries
    .map((e) => {
      const remove = opts.removable
        ? `<a class="cmp-remove" href="/compare?tools=${opts.removable.filter((s) => s !== e.slug).join(',')}${opts.os ? `&amp;os=${opts.os}` : ''}">${icon('x')}Remove</a>`
        : '';
      return (
        `<th scope="col"><a href="/tool/${esc(e.slug)}">${esc(e.name)}</a>` +
        `<div class="small quiet">${esc(kindLine(e))}</div>` +
        (e.scores?.treasure ? `<div>${badge('gem', 'Hidden gem', { icon: 'gem' })}</div>` : '') +
        `${remove}</th>`
      );
    })
    .join('');

  const rows: string[] = [];
  rows.push(group('What it is'));
  rows.push(row('Does', entries.map((e) => esc(e.summary))));
  rows.push(row('Good for', entries.map((e) => (e.use_cases.length ? `<ul class="small">${e.use_cases.slice(0, 3).map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : unknown))));

  rows.push(group(opts.os ? `On ${OS_NAME[opts.os]}${opts.arch ? ` ${opts.arch}` : ''}` : 'Where it ran'));
  rows.push(
    row(
      'Verified on',
      entries.map((e) => {
        const oses = verifiedOn(e);
        if (!oses.length) return '<span class="no">Not verified yet</span>';
        const mine = opts.os ? oses.includes(opts.os) : null;
        const words = esc(listOf(oses.map((os) => osName(os))));
        return mine === true ? `<span class="yes">${icon('check')} ${words}</span>` : mine === false ? `<span class="no">${words} only</span>` : words;
      }),
    ),
  );
  rows.push(row('Claims to run on', entries.map((e) => (e.platforms.length ? esc(listOf(e.platforms.map((os) => osName(os)))) : unknown))));
  rows.push(
    row(
      'Proof',
      entries.map((e, i) => {
        const g = guides[i];
        if (!g) return '<span class="unknown">no run</span>';
        const label = levelLabel(g.run.level, { gui: g.run.gui, mcp: g.mcp });
        return `<span class="${passed(g.run.gui) ? 'yes' : 'no'}">${esc(label)}</span><div class="small quiet">${esc(system(g.run.os, g.run.arch))}, ${esc(day(g.run.checked_at))}${g.run.replayed ? ', replayed' : ''}</div>`;
      }),
    ),
  );
  rows.push(
    row(
      'Works offline',
      guides.map((g) => (g?.works_offline === true ? '<span class="yes">Yes, checked</span>' : g?.works_offline === false ? '<span class="no">Needed the network</span>' : '<span class="unknown">not checked</span>')),
    ),
  );

  rows.push(group('Setup'));
  const stepCounts = guides.map((g) => (g && g.steps.length ? g.steps.length : null));
  rows.push(row('Install', guides.map((g) => (g && g.steps.length ? `${esc(setupWords(g.steps.length, g.manual_steps.length))}<div class="small quiet">${esc(g.method)}</div>` : '<span class="unknown">no recorded steps</span>')), bestOf(stepCounts, true)));
  rows.push(
    row(
      'Needs first',
      entries.map((e) => {
        const p = e.prerequisites;
        const needs = [
          ...p.runtimes,
          ...p.system_packages,
          p.gpu === 'required' ? 'a GPU' : '',
          p.min_ram_gb ? `${p.min_ram_gb} GB RAM` : '',
          p.apple_silicon_only ? 'Apple silicon' : '',
          ...p.api_keys.map((k) => `${k} (key)`),
          p.network === 'required' ? 'the network' : '',
        ].filter(Boolean);
        return needs.length ? esc(needs.join(', ')) : '<span class="quiet">Nothing listed</span>';
      }),
    ),
  );
  rows.push(row('README fixes', guides.map((g) => (g ? String(readerIssues(g.pitfalls).length) : '<span class="unknown">no run</span>'))));

  rows.push(group('Measures'));
  rows.push(row('Quality', entries.map((e) => tape('Quality', e.scores?.quality ?? null)), bestOf(entries.map((e) => e.scores?.quality ?? null))));
  rows.push(row('Popularity', entries.map((e) => tape('Popularity', e.scores?.popularity ?? null, { tone: 'quiet' }))));
  rows.push(row('Features', feats.map((f) => coverage(f)), bestOf(feats.map((f) => (f.recorded && f.checked.length + f.not_checked.length ? f.checked.length : null)))));

  rows.push(group('Cost, licence, upkeep'));
  rows.push(row('Price', entries.map((e) => (e.pricing ? esc(PRICE[e.pricing]) : unknown) + (e.pricing_note ? `<div class="small quiet">${esc(e.pricing_note)}</div>` : ''))));
  rows.push(row('Runs', entries.map((e) => (e.processing ? esc(PROCESSING[e.processing]) : unknown))));
  rows.push(row('Licence', entries.map((e) => (e.license ? `<code>${esc(e.license)}</code>` : unknown) + (e.open_source === true ? ' <span class="small quiet">open source</span>' : ''))));
  const releases = entries.map((e) => (e.last_release ? new Date(e.last_release).getTime() : null)).map((t) => (t !== null && Number.isNaN(t) ? null : t));
  rows.push(row('Last release', entries.map((e) => (e.last_release ? `${esc(day(e.last_release))}<div class="small quiet">${esc(age(e.last_release, opts.now) ?? '')}</div>` : unknown)), bestOf(releases)));
  rows.push(row('Links', entries.map((e) => [link(e.repo_url, 'Source'), e.homepage && e.homepage !== e.repo_url ? link(e.homepage, 'Homepage') : '', `<a href="/tool/${esc(e.slug)}">Profile</a>`].filter(Boolean).join(' · '))));

  // A group heading with no rows left under it goes too.
  const body = rows.filter(Boolean).filter((r, i, all) => !(r.startsWith('<tr class="grp">') && (i === all.length - 1 || all[i + 1].startsWith('<tr class="grp">'))));
  return (
    `<div class="table-wrap"><table class="dt cmp-table"><caption class="sr">Side-by-side comparison</caption>` +
    `<thead><tr><td></td>${head}</tr></thead><tbody>${body.join('')}</tbody></table></div>` +
    (same.length ? `<div class="cmp-same"><p class="cmp-same-title">Same for all of them</p><dl class="facts-dl">${same.join('')}</dl></div>` : '')
  );
}

/** The slugs in ?tools=, known and unique, at most four. */
export function slugsFrom(params: URLSearchParams, catalog: Catalog): string[] {
  // ?add= is the "Add a verified tool" form on the page itself.
  // ?add= may be a slug (a suggestion was picked) or a name typed in full.
  const add = (params.get('add') ?? '').trim();
  const named = add ? catalog.entries.find((e) => nameKey(e.name) === nameKey(add))?.slug ?? add : '';
  const raw = [...(params.get('tools') ?? '').split(','), named].map((s) => s.trim().toLowerCase());
  const out: string[] = [];
  for (const s of raw) if (SLUG.test(s) && catalog.bySlug.has(s) && !out.includes(s)) out.push(s);
  return out.slice(0, COMPARE_MAX);
}

export function renderCompare(catalog: Catalog, params: URLSearchParams, nonce: string): string {
  const slugs = slugsFrom(params, catalog);
  const osParam = params.get('os') ?? '';
  const os = (OSES as readonly string[]).includes(osParam) ? (osParam as OS) : undefined;
  const archParam = params.get('arch') ?? '';
  const arch = archParam === 'arm64' || archParam === 'x86_64' ? (archParam as Arch) : undefined;
  const entries = slugs.map((s) => catalog.bySlug.get(s)!);
  const verified = catalog.entries.filter((e) => verifiedOn(e).length).sort((a, b) => a.name.localeCompare(b.name));
  // Typed, not picked from a 420-item list: the datalist suggests names, and the slug is what gets sent.
  const options = verified.map((e) => `<option value="${esc(e.slug)}">${esc(e.name)}</option>`).join('');
  const osLinks = [['', 'Any OS'], ...OSES.map((o) => [o, OS_NAME[o]])]
    .map(([v, t]) => {
      const href = `/compare?tools=${slugs.join(',')}${v ? `&amp;os=${v}` : ''}`;
      return `<a class="chip${(os ?? '') === v ? ' on' : ''}" href="${href}"${(os ?? '') === v ? ' aria-current="true"' : ''}>${esc(t)}</a>`;
    })
    .join('');
  const add =
    slugs.length < COMPARE_MAX
      ? `<form class="cmp-pick" method="get" action="/compare">` +
        `<input type="hidden" name="tools" value="${esc(slugs.join(','))}">` +
        (os ? `<input type="hidden" name="os" value="${os}">` : '') +
        `<label class="sr" for="add-tool">Add a verified tool</label>` +
        `<input id="add-tool" name="add" list="tool-names" required autocomplete="off" placeholder="Add a verified tool by name…"><datalist id="tool-names">${options}</datalist>` +
        `<button class="btn btn-quiet" type="submit">${icon('plus')}Add</button></form>`
      : '';
  const body =
    entries.length >= 2
      ? `<div class="sec-head"><div class="chips" role="group" aria-label="Show the runs for">${osLinks}</div>` +
        `<button type="button" class="btn btn-quiet btn-sm js-only" data-open-legend>${icon('circle-help')}How to read this</button></div>` +
        compareTable(entries, { os, arch, now: new Date(catalog.built_at), removable: slugs }) +
        `<p class="small quiet">“Best here” marks only a plain comparison of recorded values: fewest install commands, highest quality score, most features checked, newest release. Everything comes from pickfit’s run records and profiles; nothing was asked of a model.</p>`
      : `<div class="empty">${fitz('comparing', 96)}<div><h2>${entries.length ? `Add one more to compare with ${esc(entries[0].name)}` : 'Pick two to four tools'}</h2>` +
        `<p class="quiet">Tick <b>Compare</b> on a result or in <a href="/browse">Browse</a>, or add tools here.</p></div></div>`;
  const main =
    `<section class="head mat after-top"><div class="wrap head-row"><div>` +
    `<h1>Compare tools</h1><p class="lede">Only the differences, from pickfit’s own runs.</p>` +
    `${add}</div>${fitz('comparing', 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap sec-tight">${body}</div>` +
    `<script type="application/json" data-compare-shown>${JSON.stringify(entries.map((e) => ({ slug: e.slug, name: e.name }))).replace(/</g, '\\u003c')}</script>`;
  return renderShell({
    nonce,
    title: entries.length ? `Compare ${entries.map((e) => e.name).join(', ')} · pickfit` : 'Compare tools · pickfit',
    description: 'Compare verified tools side by side: where they ran, setup, features checked, quality, price and licence.',
    active: 'compare',
    main,
  });
}
