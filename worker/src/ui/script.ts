import { L } from '../i18n.ts';

/** A visible client-side string as a JS string literal, in the render's language. */
const J = (en: string, zh: string): string => JSON.stringify(L(en, zh));

/**
 * The page script. Everything works without it (the form posts, links link);
 * it adds results in place, copy buttons, the compare tray (kept in this
 * browser's localStorage only), popover placement, the legend dialog and the
 * browse filter. Event delegation, so fragments inserted later just work.
 */
export const script = () => `
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const toasts = $('[data-toasts]');
  const toast = (text) => {
    if (!toasts) return;
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = text;
    toasts.append(t);
    setTimeout(() => t.remove(), 2600);
  };

  // ---------------------------------------------------------------- language: keep this page's other query parameters
  for (const a of $$('a[data-lang]')) {
    const q = new URLSearchParams(location.search);
    q.set('lang', a.dataset.lang);
    a.href = location.pathname + '?' + q + location.hash;
  }

  // ---------------------------------------------------------------- search
  const form = $('#search');
  if (form) {
    const need = form.elements.need;
    const go = $('.go', form);
    const label = $('.btn-label', go);
    const out = $('#results');
    const status = $('#status');
    const counter = $('[data-counter]', form);
    const grow = () => { need.style.height = 'auto'; need.style.height = need.scrollHeight + 'px'; };
    const count = () => {
      if (!counter) return;
      const n = [...need.value].length;
      counter.textContent = n > 400 ? n + ' / 500' : '';
      counter.classList.toggle('over', n > 500);
    };
    grow(); count();
    need.addEventListener('input', () => { grow(); count(); });
    addEventListener('resize', grow);
    need.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
    });
    for (const a of $$('a[href="#need"]')) {
      a.addEventListener('click', (e) => { e.preventDefault(); need.focus(); need.scrollIntoView({ block: 'center', behavior: still() ? 'auto' : 'smooth' }); });
    }
    const mode = (on) => {
      const flip = () => document.body.classList.toggle('is-results', on);
      if (document.startViewTransition && !still()) document.startViewTransition(flip); else flip();
    };
    let busy = false;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (busy || !form.reportValidity()) return;
      busy = true;
      go.disabled = true;
      go.setAttribute('aria-busy', 'true');
      label.textContent = ${J('Measuring', '量身中')};
      status.textContent = ${J('Searching', '搜尋中')};
      out.setAttribute('aria-busy', 'true');
      out.replaceChildren($('#loading').content.cloneNode(true));
      if (!document.body.classList.contains('is-results')) {
        mode(true);
        history.pushState({ results: true }, '', '#results');
      }
      out.scrollIntoView({ block: 'start', behavior: still() ? 'auto' : 'smooth' });
      try {
        const res = await fetch(form.action, { method: 'POST', body: new URLSearchParams(new FormData(form)), headers: { 'x-pickfit-fragment': '1' } });
        if (!(res.headers.get('content-type') || '').startsWith('text/html') || res.status >= 500) throw new Error(String(res.status));
        out.innerHTML = await res.text();
        const n = $$('.pick', out).length;
        status.textContent = n ? n + (n === 1 ? ${J(' result', ' 個結果')} : ${J(' results', ' 個結果')}) : ${J('No results', '沒有結果')};
        syncChecks();
      } catch {
        out.replaceChildren($('#offline').content.cloneNode(true));
        status.textContent = ${J('Search failed', '搜尋失敗')};
      } finally {
        busy = false;
        go.disabled = false;
        go.removeAttribute('aria-busy');
        label.textContent = ${J('Find my fit', '幫我找合身的')};
        out.removeAttribute('aria-busy');
        out.focus({ preventScroll: true });
      }
    });
    addEventListener('popstate', () => {
      if (!location.hash && document.body.classList.contains('is-results') && !document.body.dataset.served) {
        mode(false);
        out.replaceChildren();
      }
    });
    for (const b of $$('[data-need]')) {
      b.addEventListener('click', () => { need.value = b.dataset.need; grow(); count(); form.requestSubmit(); });
    }
  }

  // ---------------------------------------------------------------- copy
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('.copy');
    if (!b) return;
    const text = b.parentElement.querySelector('code').textContent;
    const span = b.querySelector('span');
    try {
      await navigator.clipboard.writeText(text);
      b.classList.add('done'); span.textContent = ${J('Copied', '已複製')}; toast(${J('Copied to the clipboard', '已複製到剪貼簿')});
    } catch { span.textContent = ${J('Select to copy', '請選取文字後複製')}; }
    setTimeout(() => { b.classList.remove('done'); span.textContent = ${J('Copy', '複製')}; }, 1800);
  });

  // ---------------------------------------------------------------- compare tray
  const KEY = 'pickfit.compare';
  const MAX = 4;
  const read = () => { try { const v = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(v) ? v.slice(0, MAX) : []; } catch { return []; } };
  const write = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch {} };
  const tray = $('#tray');
  const list = $('[data-tray-list]');
  const note = $('[data-tray-note]');
  const goCmp = $('[data-tray-go]');
  const href = (items) => '/compare?tools=' + items.map((i) => encodeURIComponent(i.slug)).join(',');
  function syncChecks() {
    const items = read();
    for (const c of $$('[data-compare]')) c.checked = items.some((i) => i.slug === c.dataset.compare);
  }
  function render() {
    const items = read();
    for (const n of $$('[data-tray-count]')) { n.hidden = !items.length; n.textContent = String(items.length); }
    for (const a of $$('[data-tray-link]')) a.href = items.length ? href(items) : '/compare';
    if (!tray) return;
    const onCompare = location.pathname === '/compare';
    tray.hidden = !items.length || onCompare || document.body.dataset.tray === 'off';
    document.body.classList.toggle('has-tray', !tray.hidden);
    list.replaceChildren(...items.map((i) => {
      const li = document.createElement('li');
      li.textContent = i.name;
      const x = document.createElement('button');
      x.type = 'button'; x.dataset.trayRemove = i.slug; x.setAttribute('aria-label', ${J('Remove ', '移除 ')} + i.name);
      x.innerHTML = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
      li.append(x);
      return li;
    }));
    note.textContent = items.length < 2 ? ${J('Add one more to compare', '再加一款即可比較')} : items.length + ${J(' of ', ' / ')} + MAX;
    goCmp.href = href(items);
    goCmp.setAttribute('aria-disabled', String(items.length < 2));
    syncChecks();
  }
  document.addEventListener('change', (e) => {
    const c = e.target.closest('[data-compare]');
    if (!c) return;
    let items = read();
    if (c.checked) {
      if (items.length >= MAX) { c.checked = false; toast(${J('Compare holds ', '最多比較 ')} + MAX + ${J(' tools. Remove one first.', ' 款工具，請先移除一款。')}); return; }
      if (!items.some((i) => i.slug === c.dataset.compare)) items.push({ slug: c.dataset.compare, name: c.dataset.name });
      toast(c.dataset.name + ${J(' added to compare', ' 已加入比較')});
    } else {
      items = items.filter((i) => i.slug !== c.dataset.compare);
    }
    write(items); render();
  });
  document.addEventListener('click', (e) => {
    const x = e.target.closest('[data-tray-remove]');
    if (x) { write(read().filter((i) => i.slug !== x.dataset.trayRemove)); render(); return; }
    if (e.target.closest('[data-tray-clear]')) { write([]); render(); return; }
    const g = e.target.closest('[data-tray-go]');
    if (g && read().length < 2) { e.preventDefault(); toast(${J('Pick at least two tools to compare', '請至少選兩款工具來比較')}); }
  });
  // The compare page says what it shows; keep the tray in step with it.
  const shown = $('[data-compare-shown]');
  if (shown) {
    try { const v = JSON.parse(shown.textContent); if (Array.isArray(v) && v.length) write(v.slice(0, MAX)); } catch {}
  }
  addEventListener('storage', (e) => { if (e.key === KEY) render(); });
  render();

  // ---------------------------------------------------------------- popovers next to their button
  let invoker = null;
  document.addEventListener('click', (e) => { const b = e.target.closest('[popovertarget]'); if (b) invoker = b; }, true);
  document.addEventListener('toggle', (e) => {
    const p = e.target;
    if (!(p instanceof HTMLElement) || !p.matches('.pop') || e.newState !== 'open' || !invoker) return;
    if (innerWidth < 640) { p.style.left = '16px'; p.style.top = 'auto'; p.style.bottom = '16px'; return; }
    const r = invoker.getBoundingClientRect();
    const w = p.offsetWidth, h = p.offsetHeight;
    const left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), innerWidth - w - 12);
    const below = r.bottom + 10 + h < innerHeight;
    p.style.left = left + 'px';
    p.style.bottom = 'auto';
    p.style.top = (below ? r.bottom + 10 : Math.max(12, r.top - h - 10)) + 'px';
  }, true);

  // ---------------------------------------------------------------- legend dialog
  document.addEventListener('click', (e) => {
    if (!e.target.closest('[data-open-legend]')) return;
    const d = $('#legend');
    if (d && d.showModal) d.showModal();
  });

  // ---------------------------------------------------------------- browse filter (in this page, no request)
  const grid = $('[data-grid]');
  const more = $('[data-more]');
  if (grid && more) {
    more.addEventListener('click', () => {
      const later = $$('.cat-card.later', grid);
      later.slice(0, 30).forEach((c) => c.classList.remove('later'));
      const left = later.length - 30;
      if (left > 0) more.textContent = ${J('Show ', '再顯示 ')} + Math.min(30, left) + ${J(' more', ' 款')}; else more.parentElement.remove();
    });
  }
  const filter = $('[data-filter]');
  if (filter) {
    const cards = $$('[data-text]');
    const shownCount = $('[data-shown]');
    const empty = $('[data-filter-empty]');
    filter.addEventListener('input', () => {
      const q = filter.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
      let n = 0;
      for (const c of cards) {
        const hit = q.every((w) => c.dataset.text.includes(w));
        c.hidden = !hit;
        if (hit) n++;
      }
      if (shownCount) shownCount.textContent = String(n);
      if (grid) grid.classList.toggle('filtering', q.length > 0);
      if (empty) empty.hidden = n > 0;
    });
  }

  // Close the small-screen menu after following one of its links.
  for (const a of $$('.menu-nav a')) a.addEventListener('click', () => a.closest('details').removeAttribute('open'));
})();
`;
