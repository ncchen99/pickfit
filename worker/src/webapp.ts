/**
 * Hosted web apps (kind web_app): what find_software, get_install_guide and the page say about one, built by code
 * from the browser run in the index (never by the model). A web app is opened at its URL, never installed.
 */
import { webCheck, type Entry, type WebCheck, type WebOperation } from './catalog.ts';
import { L, isZh } from './i18n.ts';

export const NO_INSTALL_LABEL = 'No install, just open it';
/** The label as the page shows it; the MCP answers keep the English constant. */
export const noInstallLabel = () => L(NO_INSTALL_LABEL, '免安裝，打開就能用');

/** The web app half of a pick or a guide: where to open it and what pickfit's browser saw. */
export interface WebAppOut {
  url: string;
  label: typeof NO_INSTALL_LABEL;
  /** When pickfit's browser checked it; null when no run passed. */
  checked_at: string | null;
  account_needed: boolean | null;
  ads_seen: boolean | null;
  third_party_domains: number | null;
  /** none: what pickfit typed in stayed on the device; observed: it was sent off; unknown: not checked. */
  data_sent: WebCheck['data_sent'];
  /** verified: a PWA that pickfit reloaded with the network off still worked. */
  works_offline: WebCheck['offline'];
}

export function webAppOut(entry: Entry): WebAppOut | null {
  if (!entry.web) return null;
  const check = webCheck(entry);
  return {
    url: entry.web.url,
    label: NO_INSTALL_LABEL,
    checked_at: check?.checked_at ?? null,
    account_needed: check?.account_needed ?? null,
    ads_seen: check?.ads_seen ?? null,
    third_party_domains: check?.third_party_domains ?? null,
    data_sent: check?.data_sent ?? 'unknown',
    works_offline: check?.offline ?? 'not_tested',
  };
}

const CHECK_TEXT: Record<WebOperation['check'], string> = {
  get page_text() { return L('text pickfit read on the page', 'pickfit 在頁面上讀到的文字'); },
  get element() { return L('what pickfit found on the page', 'pickfit 在頁面上找到的內容'); },
  get url() { return L('the address the page went to', '頁面前往的網址'); },
  get download() { return L('a file it downloaded, which pickfit read itself', '它下載的檔案，由 pickfit 自行讀取'); },
  get clipboard() { return L('what it put on the clipboard, which pickfit read itself', '它放到剪貼簿的內容，由 pickfit 自行讀取'); },
};

/** The operations that passed, in words, or null. */
function operatedText(check: WebCheck): string | null {
  const passed = check.operations.filter((o) => o.passed);
  if (check.level !== 'function' || passed.length === 0) return null;
  const what = passed
    .map((o) => {
      const feature = o.feature ?? L('a task', '一項任務');
      const how = CHECK_TEXT[o.check];
      return L(`${feature} (checked by ${how})`, `${feature}（檢查依據：${how}）`);
    })
    .join(isZh() ? '；' : '; ');
  return L(
    `a model (Muse Spark) then used it in the page and the result passed pickfit's own check: ${what}`,
    `接著由模型（Muse Spark）在頁面中實際操作，結果通過了 pickfit 自己的檢查：${what}`,
  );
}

/** "pickfit opened it in a sandboxed browser (...) on 2026-11-02; the page loaded to its main screen, ..." */
export function webRanSentence(check: WebCheck): string {
  const operated = operatedText(check);
  const date = check.checked_at.slice(0, 10);
  return (
    L(
      `pickfit opened it in a sandboxed browser (${check.browser}) on ${date}; the page loaded to its main screen`,
      `pickfit 於 ${date} 在沙盒瀏覽器（${check.browser}）中開啟它；頁面成功載入到主畫面`,
    ) +
    (operated
      ? L(`, and ${operated}.`, `，${operated}。`)
      : L(', and pickfit did not use any of its features.', '，pickfit 沒有使用它的任何功能。')) +
    L(' Each site is visited once, so there is no replay.', '每個網站只造訪一次，所以沒有重跑。')
  );
}

/** What the browser's own records showed, one short fact each, in a fixed order. */
export function webFacts(check: WebCheck): { text: string; tone: 'pass' | 'caution' | 'plain' }[] {
  const facts: { text: string; tone: 'pass' | 'caution' | 'plain' }[] = [];
  if (check.account_needed === false) facts.push({ text: L('No account needed', '不需要帳號'), tone: 'pass' });
  else if (check.account_needed === true) facts.push({ text: L('Needs an account for its main use', '主要功能需要帳號'), tone: 'caution' });
  if (check.ads_seen === false) facts.push({ text: L('No ads seen', '未看到廣告'), tone: 'pass' });
  else if (check.ads_seen === true) facts.push({ text: L('Shows ads', '會顯示廣告'), tone: 'caution' });
  const n = check.third_party_domains;
  if (n !== null)
    facts.push({
      text: n === 0
        ? L('Contacted no other sites', '沒有連到其他網站')
        : L(`Contacted ${n} other site${n === 1 ? '' : 's'}`, `連到 ${n} 個其他網站`),
      tone: n === 0 ? 'pass' : 'plain',
    });
  if (check.data_sent === 'none') facts.push({ text: L('What pickfit typed in stayed on the device', '輸入的內容沒有離開裝置'), tone: 'pass' });
  else if (check.data_sent === 'observed') facts.push({ text: L('What pickfit typed in was sent to a server', '輸入的內容會傳到伺服器'), tone: 'caution' });
  else facts.push({ text: L('Not checked whether what you type leaves your device', '未檢查輸入內容是否離開裝置'), tone: 'plain' });
  if (check.offline === 'verified') facts.push({ text: L('Works offline once loaded (checked)', '載入後可離線使用（已檢查）'), tone: 'pass' });
  else if (check.offline === 'not_offline') facts.push({ text: L('Did not work offline', '無法離線使用'), tone: 'plain' });
  return facts;
}

/** Things to tell the user before they open it, from the same facts. */
export function webWarnings(check: WebCheck | null): string[] {
  if (!check) return [];
  const warnings: string[] = [];
  if (check.data_sent === 'observed')
    warnings.push(
      L(
        'pickfit saw what it typed in sent to a server. Tell the user before they enter anything private.',
        'pickfit 發現它輸入的內容被傳送到伺服器。請在使用者輸入任何私人資料前先告知。',
      ),
    );
  if (check.data_sent === 'unknown')
    warnings.push(
      L(
        'pickfit did not check whether what the user types leaves their device.',
        'pickfit 未檢查使用者輸入的內容是否會離開其裝置。',
      ),
    );
  if (check.account_needed === true) warnings.push(L('It needs an account for its main use.', '主要功能需要帳號。'));
  if (check.ads_seen === true) warnings.push(L('It shows ads.', '它會顯示廣告。'));
  return warnings;
}
