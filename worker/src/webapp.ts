/**
 * Hosted web apps (kind web_app): what find_software, get_install_guide and the page say about one, built by code
 * from the browser run in the index (never by the model). A web app is opened at its URL, never installed.
 */
import { webCheck, type Entry, type WebCheck, type WebOperation } from './catalog.ts';

export const NO_INSTALL_LABEL = 'No install, just open it';

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
  page_text: 'text pickfit read on the page',
  element: 'what pickfit found on the page',
  url: 'the address the page went to',
  download: 'a file it downloaded, which pickfit read itself',
  clipboard: 'what it put on the clipboard, which pickfit read itself',
};

/** The operations that passed, in words, or null. */
function operatedText(check: WebCheck): string | null {
  const passed = check.operations.filter((o) => o.passed);
  if (check.level !== 'function' || passed.length === 0) return null;
  const what = passed.map((o) => `${o.feature ?? 'a task'} (checked by ${CHECK_TEXT[o.check]})`).join('; ');
  return `a model (Muse Spark) then used it in the page and the result passed pickfit's own check: ${what}`;
}

/** "pickfit opened it in a sandboxed browser (...) on 2026-11-02; the page loaded to its main screen, ..." */
export function webRanSentence(check: WebCheck): string {
  const operated = operatedText(check);
  return (
    `pickfit opened it in a sandboxed browser (${check.browser}) on ${check.checked_at.slice(0, 10)}; the page loaded to its main screen` +
    (operated ? `, and ${operated}.` : ', and pickfit did not use any of its features.') +
    ' Each site is visited once, so there is no replay.'
  );
}

/** What the browser's own records showed, one short fact each, in a fixed order. */
export function webFacts(check: WebCheck): { text: string; tone: 'pass' | 'caution' | 'plain' }[] {
  const facts: { text: string; tone: 'pass' | 'caution' | 'plain' }[] = [];
  if (check.account_needed === false) facts.push({ text: 'No account needed', tone: 'pass' });
  else if (check.account_needed === true) facts.push({ text: 'Needs an account for its main use', tone: 'caution' });
  if (check.ads_seen === false) facts.push({ text: 'No ads seen', tone: 'pass' });
  else if (check.ads_seen === true) facts.push({ text: 'Shows ads', tone: 'caution' });
  const n = check.third_party_domains;
  if (n !== null) facts.push({ text: n === 0 ? 'Contacted no other sites' : `Contacted ${n} other site${n === 1 ? '' : 's'}`, tone: n === 0 ? 'pass' : 'plain' });
  if (check.data_sent === 'none') facts.push({ text: 'What pickfit typed in stayed on the device', tone: 'pass' });
  else if (check.data_sent === 'observed') facts.push({ text: 'What pickfit typed in was sent to a server', tone: 'caution' });
  else facts.push({ text: 'Not checked whether what you type leaves your device', tone: 'plain' });
  if (check.offline === 'verified') facts.push({ text: 'Works offline once loaded (checked)', tone: 'pass' });
  else if (check.offline === 'not_offline') facts.push({ text: 'Did not work offline', tone: 'plain' });
  return facts;
}

/** Things to tell the user before they open it, from the same facts. */
export function webWarnings(check: WebCheck | null): string[] {
  if (!check) return [];
  const warnings: string[] = [];
  if (check.data_sent === 'observed') warnings.push('pickfit saw what it typed in sent to a server. Tell the user before they enter anything private.');
  if (check.data_sent === 'unknown') warnings.push('pickfit did not check whether what the user types leaves their device.');
  if (check.account_needed === true) warnings.push('It needs an account for its main use.');
  if (check.ads_seen === true) warnings.push('It shows ads.');
  return warnings;
}
