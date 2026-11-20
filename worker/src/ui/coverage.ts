/**
 * The tool page's "What pickfit could check" (U8): Verification Coverage in plain words. Each dimension that applies
 * says whether pickfit checked it (all, part or not yet), how much, and why not, by gap category; the ones that do not
 * apply to this kind of tool are named in one line. Not checked is never a fault of the tool: it is what pickfit's
 * test machines could not do yet. No script needed.
 */
import { COVERAGE_DIMENSIONS, type CoverageDimension, type CoverageSummary } from '../catalog.ts';
import { L } from '../i18n.ts';
import { esc } from './html.ts';
import { icon } from './icons.ts';

const LABEL: Record<CoverageDimension, () => string> = {
  install: () => L('Install', '安裝'),
  function: () => L('Features', '功能'),
  service: () => L('Service starts and answers', '服務啟動與回應'),
  security: () => L('Known vulnerabilities', '已知漏洞'),
  docs: () => L('Install docs', '安裝文件'),
  usability: () => L('Ease of use', '好不好上手'),
  video: () => L('Video of it in use', '操作影片'),
  repo_signals: () => L('Project activity', '專案活躍度'),
};

/** A dimension's count in words; a one-off check (docs, usability, video) has none, its status says it. */
const COUNT: Partial<Record<CoverageDimension, (done: number, of: number) => string>> = {
  install: (d, o) => L(`${d} of ${o} ${o === 1 ? 'system it claims' : 'systems it claims'} installed and checked`, `宣稱支援的 ${o} 個系統中，${d} 個已安裝並檢查`),
  function: (d, o) => L(`${d} of ${o} ${o === 1 ? 'feature' : 'features'} reached a verdict`, `${o} 項功能中 ${d} 項有結論`),
  service: (d, o) => L(`${d} of ${o} ${o === 1 ? 'step' : 'steps'} passed`, `${o} 個步驟中 ${d} 個通過`),
  security: (d, o) => L(`${d} of ${o} ${o === 1 ? 'package' : 'packages'} checked against OSV.dev`, `${o} 個套件中 ${d} 個已比對 OSV.dev`),
  repo_signals: (d, o) => L(`${d} of ${o} GitHub signals read`, `${o} 項 GitHub 指標中 ${d} 項已讀取`),
};

/** Why pickfit could not check something: coverage.py's CATEGORIES and security.py's GAP_CATEGORIES. */
const GAP: Record<string, () => string> = {
  not_attempted: () => L('not tried yet', '還沒試'),
  sandbox_missing: () => L('the test machine lacks something it needs (root, a GPU, a display, a service)', '測試機器缺少需要的東西（root、GPU、螢幕、某項服務）'),
  no_host: () => L('pickfit has no test machine for that system yet', 'pickfit 還沒有那個系統的測試機器'),
  needs_account: () => L('needs an account, a key or a paid plan', '需要帳號、金鑰或付費方案'),
  needs_hardware: () => L('needs hardware pickfit doesn’t have', '需要 pickfit 沒有的硬體'),
  harness_operation: () => L('pickfit couldn’t get through the app', 'pickfit 沒能在應用程式裡操作完'),
  check_unconfirmed: () => L('tried, but the result didn’t hold up on a second look', '試過了，但結果經不起複查'),
  docs_missing: () => L('no README to read', '沒有 README 可讀'),
  timeout: () => L('the run ran out of time', '測試時間用完了'),
  tool_error: () => L('a service pickfit relies on failed', 'pickfit 依賴的服務出錯'),
  unclassified: () => L('a reason pickfit hasn’t sorted yet', 'pickfit 還沒歸類的原因'),
  advisory_db: () => L('no vulnerability database covers its packages', '沒有漏洞資料庫涵蓋它的套件'),
  lockfile_missing: () => L('no lockfile to read its exact packages from', '沒有 lockfile 可以讀出確切的套件'),
  lockfile_unreadable: () => L('its lockfile couldn’t be read', '它的 lockfile 讀不了'),
  resolve_failed: () => L('its packages couldn’t be resolved', '解析不出它的套件'),
  no_adapter: () => L('pickfit can’t read that kind of package list yet', 'pickfit 還讀不了這種套件清單'),
  binary_no_metadata: () => L('a prebuilt binary that doesn’t list its parts', '預先編譯的程式沒有列出組成套件'),
  no_source: () => L('no source code to read', '沒有原始碼可讀'),
  platform_unsupported: () => L('built for a system pickfit can’t check', '是為 pickfit 檢查不了的系統打包的'),
};

const MARK = {
  verified: { cls: 'mark-pass', icon: 'check', word: () => L('Checked', '已檢查') },
  partial: { cls: 'mark-caution', icon: 'circle-dashed', word: () => L('Partly', '部分') },
  unverified: { cls: 'mark-open', icon: 'circle-dashed', word: () => L('Not yet', '尚未') },
} as const;

function count(dim: CoverageDimension, done: number, of: number, unit?: string): string {
  if (dim === 'function' && unit === 'check') {
    return done ? L('A check beyond --version passed', '超過 --version 的檢查通過了') : L('No check beyond --version passed yet', '還沒有超過 --version 的檢查通過');
  }
  return COUNT[dim]?.(done, of) ?? '';
}

export function coverageSection(coverage: CoverageSummary | null | undefined): string {
  if (!coverage) return '';
  const applies = COVERAGE_DIMENSIONS.filter((d) => coverage.dimensions[d]);
  if (!applies.length) return '';
  const rows = applies.map((d) => {
    const dim = coverage.dimensions[d]!;
    const mark = MARK[dim.status];
    const how = dim.done !== undefined && dim.of !== undefined ? count(d, dim.done, dim.of, dim.unit) : '';
    const waits = dim.blocked_by ? L(`Waits for ${LABEL[dim.blocked_by]().toLowerCase()} to pass`, `要先通過「${LABEL[dim.blocked_by]()}」`) : '';
    const why = (dim.gaps ?? []).map((g) => GAP[g]?.() ?? g);
    const gaps = why.length ? L(`Not covered: ${why.join('; ')}`, `沒涵蓋到：${why.join('；')}`) : '';
    const detail = [how, waits, gaps].filter(Boolean);
    return (
      `<li class="cov-row"><span class="cov-mark ${mark.cls}">${icon(mark.icon)}<span>${esc(mark.word())}</span></span>` +
      `<span class="cov-what"><b>${esc(LABEL[d]())}</b>${detail.length ? `<span class="cov-detail">${detail.map(esc).join(L('. ', '。'))}</span>` : ''}</span></li>`
    );
  });
  const skipped = COVERAGE_DIMENSIONS.filter((d) => !coverage.dimensions[d]).map((d) => LABEL[d]());
  const share = coverage.share === null ? null : Math.round(coverage.share * 100);
  return (
    `<section class="block coverage" id="coverage" aria-labelledby="coverage-title"><h2 id="coverage-title">${L('What pickfit could check', 'pickfit 檢查到哪些部分')}</h2>` +
    `<p>${share === null ? '' : L(`About ${share}% of what applies to this tool. `, `大約是適用項目的 ${share}%。`)}${L(
      'Not checked doesn’t mean it fails: it is what pickfit’s test machines couldn’t do yet, and it lowers no score.',
      '沒檢查到不代表它有問題，只是 pickfit 的測試機器還做不到，也不會因此扣分。',
    )}</p>` +
    `<ul class="cov-list">${rows.join('')}</ul>` +
    (skipped.length ? `<p class="small quiet">${L(`Doesn’t apply to this kind of tool: ${skipped.join(', ').toLowerCase()}.`, `這類工具不適用：${skipped.join('、')}。`)}</p>` : '') +
    `</section>`
  );
}
