/**
 * Side by side: the same facts for two to four tools, straight from the
 * catalog (no model call). A row marks the best value only where "best" is a
 * plain comparison of recorded numbers or dates: fewest setup commands, most
 * features checked, highest quality score, newest release. Nothing else is
 * ranked.
 */
import { bestGuide, isWebApp, nameKey, OSES, verifiedOn, webCheck, type Arch, type Catalog, type Entry, type OS } from '../catalog.ts';
import { featuresOut } from '../features.ts';
import { isZh, L } from '../i18n.ts';
import { day, levelLabel, OS_NAME, osName, PRICE, PROCESSING, passed, readerIssues, setupWords, webLevelLabel } from '../ui/facts.ts';
import { esc, link, listOf, SLUG } from '../ui/html.ts';
import { icon, type IconName } from '../ui/icons.ts';
import { age, badge, coverage, fitz, kindTag, levelIcon, osList, sysTag, tape } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';

export const COMPARE_MAX = 4;

interface Opts {
  os?: OS;
  arch?: Arch;
  now: Date;
  /** Show a remove link per column (the compare page). */
  removable?: string[];
}

// A function so the label follows the render's language.
const BEST = () => `<span class="best">${icon('check')}${L('best here', '最佳')}</span>`;

/** The compare table for these entries; `os` decides which run each column shows. */
export function compareTable(entries: Entry[], opts: Opts): string {
  const guides = entries.map((e) => bestGuide(e, opts.os));
  const feats = entries.map((e, i) => featuresOut(e, guides[i]));
  const cols = entries.length;
  const unknown = `<span class="unknown">${L('not stated', '未說明')}</span>`;

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
    return `<tr><th scope="row">${esc(label)}</th>${cells.map((c, i) => `<td>${c}${i === best ? BEST() : ''}</td>`).join('')}</tr>`;
  };
  const group = (label: string) => `<tr class="grp"><th colspan="${cols + 1}" scope="colgroup">${esc(label)}</th></tr>`;

  const head = entries
    .map((e) => {
      const remove = opts.removable
        ? `<a class="cmp-remove" href="/compare?tools=${opts.removable.filter((s) => s !== e.slug).join(',')}${opts.os ? `&amp;os=${opts.os}` : ''}" aria-label="${L(`Remove ${esc(e.name)}`, `移除 ${esc(e.name)}`)}" data-tip="${L('Remove', '移除')}">${icon('x')}</a>`
        : '';
      return (
        `<th scope="col"><a href="/tool/${esc(e.slug)}">${esc(e.name)}</a>` +
        `<div class="small quiet">${kindTag(e)}</div>` +
        (e.scores?.treasure ? `<div>${badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem' })}</div>` : '') +
        `${remove}</th>`
      );
    })
    .join('');

  const rows: string[] = [];
  rows.push(group(L('What it is', '這是什麼')));
  rows.push(row(L('Does', '用途'), entries.map((e) => esc(e.summary))));
  rows.push(row(L('Good for', '適合用來'), entries.map((e) => (e.use_cases.length ? `<ul class="small">${e.use_cases.slice(0, 3).map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : unknown))));

  rows.push(
    group(
      opts.os
        ? L(
            `On ${OS_NAME[opts.os]}${opts.arch ? ` ${opts.arch}` : ''}`,
            `在 ${OS_NAME[opts.os]}${opts.arch ? ` ${opts.arch}` : ''} 上`,
          )
        : L('Where it ran', '測試環境'),
    ),
  );
  rows.push(
    row(
      L('Verified on', '已驗證於'),
      entries.map((e) => {
        const web = webCheck(e);
        if (web) return `<span class="yes">${icon('check')} ${L('In a browser, any OS', '瀏覽器即可，不限系統')}</span>`;
        const oses = verifiedOn(e);
        if (!oses.length) return `<span class="no">${L('Not verified yet', '尚未驗證')}</span>`;
        const mine = opts.os ? oses.includes(opts.os) : null;
        const names = listOf(oses.map((os) => osName(os)));
        return mine === false
          ? osList(oses, { tone: 'caution', say: L(`${names} only, not ${osName(opts.os)}`, `只有 ${names}，不含 ${osName(opts.os)}`) })
          : osList(oses, { tone: 'pass', say: mine ? L(`${names}, including yours`, `${names}，含你的系統`) : names });
      }),
    ),
  );
  rows.push(row(L('Claims to run on', '宣稱支援'), entries.map((e) => (e.platforms.length ? osList(e.platforms, { tone: 'quiet' }) : unknown))));
  rows.push(
    row(
      L('Proof', '證據'),
      entries.map((e, i) => {
        const g = guides[i];
        const web = webCheck(e);
        if (web) return `<span class="yes">${esc(webLevelLabel(web))}</span><div class="small quiet">${L(`In a browser, ${esc(day(web.checked_at))}`, `在瀏覽器中，${esc(day(web.checked_at))}`)}</div>`;
        if (!g) return `<span class="unknown">${L('no run', '尚未測試')}</span>`;
        const evidence = { gui: g.run.gui, mcp: g.mcp };
        const replayed = g.run.replayed ? ` · <span data-tip="${L('Replayed from scratch', '從頭重跑過')}">${icon('refresh-cw')}<span class="sr">${L('replayed', '已重跑')}</span></span>` : '';
        return (
          `<span class="${passed(g.run.gui) ? 'yes' : 'no'} cmp-level">${icon(levelIcon(g.run.level, evidence))}${esc(levelLabel(g.run.level, evidence))}</span>` +
          `<div class="small quiet run-line">${sysTag(g.run.os, g.run.arch)} · ${esc(day(g.run.checked_at))}${replayed}</div>`
        );
      }),
    ),
  );
  rows.push(
    row(
      L('Works offline', '可離線使用'),
      guides.map((g, i) => {
        const offline = g?.works_offline ?? { verified: true, not_offline: false, not_tested: null }[webCheck(entries[i])?.offline ?? 'not_tested'];
        return offline === true
          ? `<span class="yes">${icon('wifi-off')}${L('Yes, checked', '可以（已檢查）')}</span>`
          : offline === false
            ? `<span class="no">${icon('wifi')}${L('Needed the network', '需要網路')}</span>`
            : `<span class="unknown">${L('not checked', '未檢查')}</span>`;
      }),
    ),
  );

  rows.push(group(L('Setup', '安裝設定')));
  const stepCounts = guides.map((g) => (g && g.steps.length ? g.steps.length : null));
  const install = guides.map((g, i) => {
    if (isWebApp(entries[i])) return `<span class="yes">${L('Nothing to install, just open it', '免安裝，打開就能用')}</span>`;
    return g && g.steps.length
      ? `${esc(setupWords(g.steps.length, g.manual_steps.length))}<div class="small quiet">${esc(g.method)}</div>`
      : `<span class="unknown">${L('no recorded steps', '沒有步驟紀錄')}</span>`;
  });
  rows.push(row(L('Install', '安裝'), install, bestOf(stepCounts, true)));
  rows.push(
    row(
      L('Needs first', '需先準備'),
      entries.map((e) => {
        const p = e.prerequisites;
        const needs = [
          ...p.runtimes,
          ...p.system_packages,
          p.gpu === 'required' ? L('a GPU', 'GPU') : '',
          p.min_ram_gb ? L(`${p.min_ram_gb} GB RAM`, `${p.min_ram_gb} GB 記憶體`) : '',
          p.apple_silicon_only ? L('Apple silicon', 'Apple 晶片') : '',
          // A translated key often already says 金鑰; don't say it twice.
          ...p.api_keys.map((k) => L(`${k} (key)`, /金鑰|key|token|帳號/i.test(k) ? k : `${k}（金鑰）`)),
          p.network === 'required' ? L('the network', '網路') : '',
        ].filter(Boolean);
        return needs.length ? esc(needs.join(isZh() ? '、' : ', ')) : `<span class="quiet">${L('Nothing listed', '未列出')}</span>`;
      }),
    ),
  );
  rows.push(
    row(
      L('README fixes', 'README 修正'),
      guides.map((g, i) =>
        g
          ? String(readerIssues(g.pitfalls).length)
          : isWebApp(entries[i])
            ? `<span class="quiet">${L('no README to follow', '沒有 README')}</span>`
            : `<span class="unknown">${L('no run', '尚未測試')}</span>`,
      ),
    ),
  );

  rows.push(group(L('Measures', '分數')));
  rows.push(row(L('Quality', '品質'), entries.map((e) => tape(L('Quality', '品質'), e.scores?.quality ?? null)), bestOf(entries.map((e) => e.scores?.quality ?? null))));
  rows.push(row(L('Popularity', '知名度'), entries.map((e) => tape(L('Popularity', '知名度'), e.scores?.popularity ?? null, { tone: 'quiet' }))));
  rows.push(row(L('Features', '功能'), feats.map((f) => coverage(f)), bestOf(feats.map((f) => (f.recorded && f.checked.length + f.not_checked.length ? f.checked.length : null)))));

  rows.push(group(L('Cost, licence, upkeep', '費用、授權、維護')));
  rows.push(row(L('Price', '價格'), entries.map((e) => (e.pricing ? esc(PRICE[e.pricing]) : unknown) + (e.pricing_note ? `<div class="small quiet">${esc(e.pricing_note)}</div>` : ''))));
  rows.push(row(L('Runs', '執行位置'), entries.map((e) => (e.processing ? esc(PROCESSING[e.processing]) : unknown))));
  rows.push(row(L('Licence', '授權'), entries.map((e) => (e.license ? `<code>${esc(e.license)}</code>` : unknown) + (e.open_source === true ? ` <span class="small quiet">${L('open source', '開源')}</span>` : ''))));
  const releases = entries.map((e) => (e.last_release ? new Date(e.last_release).getTime() : null)).map((t) => (t !== null && Number.isNaN(t) ? null : t));
  rows.push(row(L('Last release', '最新版本'), entries.map((e) => (e.last_release ? `${esc(day(e.last_release))}<div class="small quiet">${esc(age(e.last_release, opts.now) ?? '')}</div>` : unknown)), bestOf(releases)));
  // The name at the top of each column already links to the profile; these are the outside links, as marks.
  const outLink = (url: string | null | undefined, mark: IconName, name: string) => {
    const a = link(url, `${icon(mark)}<span class="sr">${name}</span>`, 'icon-link');
    return a ? `<span data-tip="${name}">${a}</span>` : '';
  };
  rows.push(
    row(
      L('Links', '連結'),
      entries.map(
        (e) =>
          `<span class="cmp-links">${outLink(e.web?.url, 'external-link', L('Open it', '開啟'))}${outLink(e.repo_url, 'code', L('Source code', '原始碼'))}` +
          `${e.homepage && e.homepage !== e.repo_url && e.homepage !== e.web?.url ? outLink(e.homepage, 'globe', L('Homepage', '首頁')) : ''}</span>`,
      ),
    ),
  );

  // A group heading with no rows left under it goes too.
  const body = rows.filter(Boolean).filter((r, i, all) => !(r.startsWith('<tr class="grp">') && (i === all.length - 1 || all[i + 1].startsWith('<tr class="grp">'))));
  return (
    `<div class="table-wrap"><table class="dt cmp-table"><caption class="sr">${L('Side-by-side comparison', '並排比較')}</caption>` +
    `<thead><tr><td></td>${head}</tr></thead><tbody>${body.join('')}</tbody></table></div>` +
    (same.length ? `<div class="cmp-same"><p class="cmp-same-title">${L('Same for all of them', '都一樣的項目')}</p><dl class="facts-dl">${same.join('')}</dl></div>` : '')
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
  // The page script swaps the datalist for its own list (data-combo), which sends the name instead.
  const options = verified.map((e) => `<option value="${esc(e.slug)}">${esc(e.name)}</option>`).join('');
  const osLinks = [['', L('Any OS', '不限系統')], ...OSES.map((o) => [o, OS_NAME[o]])]
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
        `<label class="sr" for="add-tool">${L('Add a verified tool', '加入已驗證的工具')}</label>` +
        `<input id="add-tool" type="text" name="add" list="tool-names" data-combo required autocomplete="off" placeholder="${L('Add a verified tool by name…', '輸入名稱加入工具…')}"><datalist id="tool-names">${options}</datalist>` +
        `<button class="btn btn-quiet" type="submit">${icon('plus')}${L('Add', '加入')}</button></form>`
      : '';
  const body =
    entries.length >= 2
      ? `<div class="sec-head"><div class="chips" role="group" aria-label="${L('Show the runs for', '顯示哪個系統的測試')}">${osLinks}</div>` +
        `<button type="button" class="btn btn-quiet btn-sm js-only" data-open-legend>${icon('circle-help')}${L('How to read this', '怎麼看這張表')}</button></div>` +
        compareTable(entries, { os, arch, now: new Date(catalog.built_at), removable: slugs }) +
        `<p class="small quiet">${L(
          '“Best here” marks only a plain comparison of recorded values: fewest install commands, highest quality score, most features checked, newest release. Everything comes from pickfit’s run records and profiles; nothing was asked of a model.',
          '「最佳」只是把紀錄裡的數值直接比大小：安裝指令最少、品質分數最高、檢查過的功能最多、版本最新。所有內容都來自 pickfit 的測試紀錄與簡介，沒有問過任何模型。',
        )}</p>`
      : `<div class="empty">${fitz('comparing', 96)}<div><h2>${entries.length ? L(`Add one more to compare with ${esc(entries[0].name)}`, `再加一款來和 ${esc(entries[0].name)} 比較`) : L('Pick two to four tools', '挑兩到四款工具')}</h2>` +
        `<p class="quiet">${L(
          'Tick <b>Compare</b> on a result or in <a href="/browse">Browse</a>, or add tools here.',
          '在搜尋結果或<a href="/browse">瀏覽</a>頁勾選<b>比較</b>，或在這裡加入工具。',
        )}</p></div></div>`;
  const main =
    `<section class="head mat after-top"><div class="wrap head-row"><div>` +
    `<h1>${L('Compare tools', '比較工具')}</h1><p class="lede">${L('Only the differences, from pickfit’s own runs', '只列出差異，全部來自 pickfit 的實測')}</p>` +
    `${add}</div>${fitz('comparing', 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap sec-tight">${body}</div>` +
    `<script type="application/json" data-compare-shown>${JSON.stringify(entries.map((e) => ({ slug: e.slug, name: e.name }))).replace(/</g, '\\u003c')}</script>`;
  return renderShell({
    nonce,
    title: entries.length
      ? L(`Compare ${entries.map((e) => e.name).join(', ')} · pickfit`, `比較 ${entries.map((e) => e.name).join('、')} · pickfit`)
      : L('Compare tools · pickfit', '比較工具 · pickfit'),
    description: L(
      'Compare verified tools side by side: where they ran, setup, features checked, quality, price and licence.',
      '並排比較已驗證的工具：執行環境、安裝設定、已檢查的功能、品質、價格與授權。',
    ),
    active: 'compare',
    main,
  });
}
