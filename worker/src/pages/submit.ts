/**
 * The web door to submit_software: a form, and a status page for one submission that follows it through the
 * pipeline. The steps are the states `pickfit watch` really writes to D1; nothing here estimates a percentage.
 * No account and no email: the status page's own link is how you come back.
 */
import type { SubmissionStatus } from '../submit.ts';
import { L } from '../i18n.ts';
import { esc } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { fitz, type FitzName } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
import { head } from './info.ts';

/** A row still `queued` this long means no watcher is taking rows: say so rather than promise minutes. */
const QUEUE_LOOKS_PAUSED_MS = 20 * 60_000;

const isRepo = (url: string) => url.startsWith('https://github.com/');
/** owner/repo, or the site's host and path. */
export const shortUrl = (url: string) => url.replace(/^https:\/\/(github\.com\/)?/, '').replace(/\/$/, '');

/** What happens to a submission, one line a step; the status page marks how far it has got. */
const STEPS = (repo: boolean): { name: string; line: string }[] => [
  { name: L('In line', '排隊'), line: L('Submissions run in the order they came in.', '依送出的順序處理。') },
  {
    name: L('Read', '閱讀'),
    line: repo
      ? L('Muse Spark reads the README and writes down what the software claims, with the quotes.', 'Muse Spark 讀 README，記下軟體宣稱能做什麼，並保留原文引述。')
      : L('Muse Spark reads the site and writes down what it says it does.', 'Muse Spark 讀網站，記下它說自己能做什麼。'),
  },
  {
    name: L('Try', '試用'),
    line: repo
      ? L('Installed in a clean sandbox, installed again from scratch, and its main features tried.', '在乾淨的沙盒裡安裝，再從頭重裝一次，並試用主要功能。')
      : L('Opened in a sandboxed browser and its main features tried.', '在沙盒瀏覽器裡開啟，並試用主要功能。'),
  },
  { name: L('List', '收錄'), line: L('It joins the catalog, so people and agents can find it when it fits.', '收進目錄，符合需求時大家和 agent 就找得到。') },
];

export interface SubmitFormInput {
  url?: string;
  error?: string | null;
}

export function renderSubmitForm(nonce: string, input: SubmitFormInput = {}): string {
  const error = input.error ?? null;
  const form =
    `<form id="submit-form" class="ask-card sub-form${error ? ' is-invalid' : ''}" method="post" action="/submit">` +
    `<div class="ask"><label for="sub-url">${L('Recommend', '推薦')}</label>` +
    `<input id="sub-url" name="url" type="text" inputmode="url" required maxlength="300" autocomplete="off" autocapitalize="off" spellcheck="false" ` +
    `placeholder="github.com/you/your-app"${input.url ? ` value="${esc(input.url)}"` : ''}${error ? ' aria-invalid="true" aria-describedby="sub-err"' : ''}></div>` +
    (error ? `<p class="sub-err" id="sub-err" role="alert">${esc(error)}</p>` : '') +
    `<div class="ask-meta"><div class="ask-go"><button type="submit" class="btn btn-primary go"><span class="btn-label">${L('Send it to Fitz', '交給 Fitz')}</span></button></div></div>` +
    `</form>`;
  const steps = STEPS(true)
    .slice(1)
    .map((s) => `<li><b>${esc(s.name)}</b><span>${esc(s.line)}</span></li>`)
    .join('');
  const main =
    head(
      L('Recommend software to pickfit', '推薦軟體給 pickfit'),
      L('Paste a link. Fitz tries it in a clean sandbox and lists it if it works', '貼上連結。Fitz 會在乾淨的沙盒裡試用，能用就收進來'),
      'hello',
    ) +
    `<div class="wrap sub-page"><div class="sub-main">${form}</div>` +
    `<aside class="sub-side"><h2 class="sub-h">${L('What happens next', '接下來會發生什麼事')}</h2><ol class="sub-next">${steps}</ol></aside></div>`;
  return renderShell({
    nonce,
    title: L('Recommend software · pickfit', '推薦軟體 · pickfit'),
    description: L('Recommend a GitHub project or a web app. pickfit tries it in a sandbox and lists it if it works.', '推薦 GitHub 專案或網頁應用。pickfit 會在沙盒裡試用，能用就收錄。'),
    active: 'submit',
    main,
    tray: false,
  });
}

export interface SubmissionView {
  /** null when the software was already in the catalog and no submission row exists. */
  id: string | null;
  url: string;
  status: SubmissionStatus;
  reason: string | null;
  submitted_at: string | null;
  /** Its page, when the catalog has it. */
  toolHref: string | null;
}

type StepState = 'done' | 'now' | 'todo' | 'stopped';

/** How far the row has got, from its status alone. A `verifying` row with a reason has passed and waits for a publish. */
function stepStates(view: SubmissionView): StepState[] {
  const ready = view.status === 'verifying' && view.reason !== null;
  switch (view.status) {
    case 'queued':
      return ['now', 'todo', 'todo', 'todo'];
    case 'reading':
      return ['done', 'now', 'todo', 'todo'];
    case 'verifying':
      return ready ? ['done', 'done', 'done', 'now'] : ['done', 'done', 'now', 'todo'];
    case 'listed':
      return ['done', 'done', 'done', 'done'];
    case 'listed_unverified':
      return ['done', 'done', 'stopped', 'done'];
    case 'rejected':
      return ['done', 'stopped', 'todo', 'todo'];
  }
}

function saying(view: SubmissionView, now: Date): { who: FitzName; title: string; line: string; tab: string } {
  const repo = isRepo(view.url);
  const ready = view.status === 'verifying' && view.reason !== null;
  const waited = view.submitted_at ? now.getTime() - Date.parse(view.submitted_at) : 0;
  switch (view.status) {
    case 'queued':
      if (!repo)
        return {
          who: 'idle',
          title: L('You’re in line.', '排進隊伍了。'),
          line: L('Websites are tested in batches, so this one can take a while. Your place is kept.', '網站是分批測試的，可能要等一陣子。你的位置會保留。'),
          tab: L('In line', '排隊中'),
        };
      if (waited > QUEUE_LOOKS_PAUSED_MS)
        return {
          who: 'resting',
          title: L('Still in line.', '還在排隊。'),
          line: L('The test line looks paused right now. Your place is kept, and this page moves on its own when it starts.', '測試線目前看起來暫停了。你的位置會保留，開始時這一頁會自己更新。'),
          tab: L('In line', '排隊中'),
        };
      return { who: 'idle', title: L('You’re in line.', '排進隊伍了。'), line: L('It should start within a minute or so.', '應該一分鐘左右就會開始。'), tab: L('In line', '排隊中') };
    case 'reading':
      return { who: 'thinking', title: L('Fitz is reading it.', 'Fitz 正在讀。'), line: L('This part usually takes under a minute.', '這一步通常不到一分鐘。'), tab: L('Reading', '閱讀中') };
    case 'verifying':
      if (ready)
        return { who: 'success', title: L('It passed.', '通過了。'), line: L('It goes live the next time pickfit publishes.', '下次 pickfit 發布時就會上線。'), tab: L('Passed', '已通過') };
      return {
        who: 'testing',
        title: L('Fitz is trying it.', 'Fitz 正在試用。'),
        line: repo ? L('A few minutes for most software. Keep this page open, or come back later.', '大多數軟體要幾分鐘。可以開著這一頁，也可以晚點再回來。') : L('A few minutes. Keep this page open, or come back later.', '要幾分鐘。可以開著這一頁，也可以晚點再回來。'),
        tab: L('Trying it', '試用中'),
      };
    case 'listed':
      return view.id
        ? { who: 'success', title: L('It’s listed.', '收錄了。'), line: L('It passed, and pickfit can now recommend it when it fits.', '它通過了測試，符合需求時 pickfit 就會推薦。'), tab: L('Listed', '已收錄') }
        : { who: 'neutral', title: L('It’s already in pickfit.', '它已經在 pickfit 裡了。'), line: L('There is nothing to do. Its page shows what the run found.', '不用再做什麼。它的頁面有這次測試的結果。'), tab: L('Already listed', '已收錄') };
    case 'listed_unverified':
      return {
        who: 'sorry',
        title: L('Listed, but not verified.', '收錄了，但還沒驗證。'),
        line: view.reason ?? L('Fitz could not finish trying it, so it won’t be recommended yet.', 'Fitz 沒能試完，所以暫時不會推薦。'),
        tab: L('Not verified', '未驗證'),
      };
    case 'rejected':
      return { who: 'sorry', title: L('Not listed.', '沒有收錄。'), line: view.reason ?? L('It doesn’t fit what pickfit takes.', '它不在 pickfit 收錄的範圍內。'), tab: L('Not listed', '未收錄') };
  }
}

export const isFinal = (status: SubmissionStatus) => status === 'listed' || status === 'listed_unverified' || status === 'rejected';

const STEP_MARK: Record<StepState, string> = {
  done: icon('check'),
  now: '',
  todo: icon('circle-dashed'),
  stopped: icon('x'),
};
const stateWord = (state: StepState) =>
  ({ done: L('Done', '完成'), now: L('Now', '進行中'), todo: L('Not yet', '尚未開始'), stopped: L('Stopped here', '停在這裡') })[state];

/**
 * The part that changes. The page script fetches this same URL and swaps this in only when it differs, so it has
 * nothing time-based in it (the elapsed line sits outside and the script keeps it current).
 */
export function renderSubmissionLive(view: SubmissionView, now: Date): string {
  const say = saying(view, now);
  const states = stepStates(view);
  const steps = STEPS(isRepo(view.url))
    .map((step, i) => {
      const state = states[i];
      return (
        `<li class="sub-step is-${state}"${state === 'now' ? ' aria-current="step"' : ''}>` +
        `<span class="sub-mark" aria-hidden="true">${STEP_MARK[state]}</span>` +
        `<div><h3>${esc(step.name)}<span class="sr"> (${esc(stateWord(state))})</span></h3><p>${esc(step.line)}</p>` +
        (state === 'now' ? `<div class="unroll" aria-hidden="true"></div>` : '') +
        `</div></li>`
      );
    })
    .join('');
  const passed = view.status === 'listed' && view.id !== null;
  const go = view.toolHref
    ? `<a class="btn ${view.status === 'rejected' ? 'btn-quiet' : 'btn-primary'}" href="${esc(view.toolHref)}">${view.status === 'listed' ? L('See its page', '看它的頁面') : L('See what the run found', '看測試結果')}</a>`
    : '';
  const again = isFinal(view.status) ? `<a class="btn btn-quiet" href="/submit">${L('Recommend another', '再推薦一款')}</a>` : '';
  const keep =
    view.id && !isFinal(view.status)
      ? `<p class="sub-keep"><span>${L('You can close this page. This link keeps the result.', '可以關掉這一頁，這個連結會保留結果。')}</span> ` +
        `<button type="button" class="btn btn-ghost btn-sm js-only" data-copy-page>${L('Copy link', '複製連結')}</button>` +
        `<noscript><a href="">${L('Check again', '重新整理')}</a></noscript></p>`
      : '';
  return (
    `<div class="sub-grid" data-sub-state="${isFinal(view.status) ? 'final' : 'running'}" data-sub-key="${esc(`${view.status}|${say.title}|${say.line}`)}" data-sub-tab="${esc(`${say.tab} · ${shortUrl(view.url)}`)}">` +
    `<div class="sub-main"><div class="says sub-says" role="status">${fitz(say.who, 104, { eager: true })}<div class="bubble"><h2>${esc(say.title)}</h2><p>${esc(say.line)}</p></div></div>` +
    (passed ? `<div class="seam" aria-hidden="true"></div>` : '') +
    (go || again ? `<div class="sub-go">${go}${again}</div>` : '') +
    keep +
    `</div><ol class="sub-steps sub-side">${steps}</ol></div>`
  );
}

/** "3 min ago", the server's first reading of what the page script keeps current. */
function ago(iso: string, now: Date): string {
  const min = Math.floor((now.getTime() - Date.parse(iso)) / 60_000);
  if (min < 1) return L('just now', '剛剛');
  if (min < 60) return L(`${min} min ago`, `${min} 分鐘前`);
  const hours = Math.floor(min / 60);
  if (hours < 48) return L(`${hours} h ago`, `${hours} 小時前`);
  return L(`${Math.floor(hours / 24)} days ago`, `${Math.floor(hours / 24)} 天前`);
}

export function renderSubmissionPage(view: SubmissionView, now: Date, nonce: string): string {
  const say = saying(view, now);
  const name = shortUrl(view.url);
  const when = view.submitted_at
    ? `<p class="lede">${L('Submitted', '送出於')} <time datetime="${esc(view.submitted_at)}" data-sub-since>${esc(ago(view.submitted_at, now))}</time></p>`
    : '';
  const offline = view.id && !isFinal(view.status) ? `<p class="sub-offline" data-sub-offline hidden>${L('Can’t reach pickfit right now. Still trying.', '暫時連不上 pickfit，會繼續重試。')}</p>` : '';
  const main =
    `<section class="head mat after-top"><div class="wrap head-row"><div><h1 translate="no">${esc(name)}</h1>${when}</div></div><div class="ruler" aria-hidden="true"></div></section>` +
    `<div class="wrap sub-status"><div data-sub-live aria-live="off">${renderSubmissionLive(view, now)}</div>${offline}</div>`;
  return renderShell({
    nonce,
    title: `${say.tab} · ${name}`,
    description: L('The progress of one recommendation to pickfit.', '一筆 pickfit 推薦的進度。'),
    active: 'submit',
    main,
    tray: false,
  });
}
