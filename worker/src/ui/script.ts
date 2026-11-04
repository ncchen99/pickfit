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

  // ---------------------------------------------------------------- a submission: follow it until it ends
  const subLive = $('[data-sub-live]');
  if (subLive) {
    const since = $('[data-sub-since]');
    const offline = $('[data-sub-offline]');
    const showAgo = () => {
      if (!since) return;
      const min = Math.floor((Date.now() - Date.parse(since.dateTime)) / 60000);
      since.textContent = min < 1 ? ${J('just now', '剛剛')} : min < 60 ? min + ${J(' min ago', ' 分鐘前')} : Math.floor(min / 60) + ${J(' h ago', ' 小時前')};
    };
    let timer = 0;
    const current = () => $('[data-sub-state]', subLive);
    const running = () => current().dataset.subState === 'running';
    const next = () => { clearTimeout(timer); if (running()) timer = setTimeout(poll, 6000); };
    const poll = async () => {
      if (document.hidden) return; // picked up again when the tab comes back
      showAgo();
      try {
        const res = await fetch(location.pathname, { headers: { accept: 'text/html', 'x-pickfit-fragment': '1' } });
        if (!res.ok) throw new Error(String(res.status));
        const fresh = document.createElement('template');
        fresh.innerHTML = await res.text();
        const row = fresh.content.firstElementChild;
        if (offline) offline.hidden = true;
        if (row && row.dataset.subKey !== current().dataset.subKey) {
          subLive.setAttribute('aria-live', 'polite'); // only a change is news; not the page as it loads
          subLive.replaceChildren(row);
          document.title = row.dataset.subTab;
          if (!running() && offline) offline.remove();
        }
      } catch {
        if (offline) offline.hidden = false;
      }
      next();
    };
    document.addEventListener('visibilitychange', () => { if (!document.hidden && running()) poll(); });
    next();
  }
  // Delegated: the status part, with this button in it, is replaced as the submission moves on.
  document.addEventListener('click', async (e) => {
    if (!e.target.closest || !e.target.closest('[data-copy-page]')) return;
    try { await navigator.clipboard.writeText(location.href); toast(${J('Link copied', '已複製連結')}); }
    catch { toast(${J('Couldn’t copy. The link is in the address bar.', '無法複製，連結就在網址列。')}); }
  });
  const subForm = $('#submit-form');
  if (subForm) subForm.addEventListener('submit', () => {
    const go = $('.go', subForm);
    go.setAttribute('aria-busy', 'true');
    go.disabled = true;
  });

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
        label.textContent = ${J('Find tools', '幫我挑')};
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
    } catch { b.classList.add('fail'); span.textContent = ${J('Select to copy', '請選取文字後複製')}; }
    setTimeout(() => { b.classList.remove('done', 'fail'); span.textContent = ${J('Copy', '複製')}; }, 1800);
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
    // The nav names Compare only while the tray holds tools (and always on /compare itself).
    for (const a of $$('[data-tray-nav]')) a.hidden = !items.length && a.getAttribute('aria-current') !== 'page';
    if (!tray) return;
    const onCompare = location.pathname === '/compare';
    tray.hidden = !items.length || onCompare || document.body.dataset.tray === 'off';
    document.body.classList.toggle('has-tray', !tray.hidden);
    list.replaceChildren(...items.map((i) => {
      const li = document.createElement('li');
      li.textContent = i.name;
      // Each tool in the tray is pinned: it carries the tray's own pin (shell.ts), cloned, so the drawing lives in one place.
      const pin = tray.querySelector('.tray-mark .i');
      if (pin) li.prepend(pin.cloneNode(true));
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

  // ---------------------------------------------------------------- dropdowns
  // A select marked data-dropdown keeps posting the form; the script hides it behind a button and a list
  // drawn like the rest of the page. Arrow keys, Home/End, Enter or Space, Escape and typing a letter work.
  const CHECK = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
  let ddCount = 0;
  const place = (list, anchor) => {
    list.classList.remove('up');
    const r = anchor.getBoundingClientRect();
    if (r.bottom + 6 + list.offsetHeight > innerHeight && r.top - 6 - list.offsetHeight > 0) list.classList.add('up');
  };
  // Scrolls the list only: scrollIntoView and a bare focus() also scroll every clipped ancestor, which slid the whole search card up.
  const reveal = (list, li) => {
    if (li.offsetTop < list.scrollTop) list.scrollTop = li.offsetTop;
    else if (li.offsetTop + li.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = li.offsetTop + li.offsetHeight - list.clientHeight;
  };
  const activate = (list, li) => {
    for (const o of $$('li', list)) o.classList.toggle('active', o === li);
    if (li) { list.setAttribute('aria-activedescendant', li.id); reveal(list, li); }
  };
  for (const sel of $$('select[data-dropdown]')) {
    const id = 'dd' + ++ddCount;
    const box = document.createElement('div');
    box.className = 'dd';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'select dd-btn';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-controls', id);
    const name = document.createElement('span');
    name.className = 'sr';
    name.textContent = (sel.getAttribute('aria-label') || '') + ': ';
    const shown = document.createElement('span');
    btn.append(name, shown);
    const list = document.createElement('ul');
    list.className = 'dd-list';
    list.id = id;
    list.setAttribute('role', 'listbox');
    list.setAttribute('aria-label', sel.getAttribute('aria-label') || '');
    list.tabIndex = -1;
    list.hidden = true;
    const opts = [...sel.options].map((o, i) => {
      const li = document.createElement('li');
      li.id = id + '-' + i;
      li.setAttribute('role', 'option');
      li.dataset.value = o.value;
      li.innerHTML = CHECK;
      li.append(o.textContent);
      list.append(li);
      return li;
    });
    const sync = () => {
      shown.textContent = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent : '';
      opts.forEach((li, i) => li.setAttribute('aria-selected', String(i === sel.selectedIndex)));
    };
    const open = () => {
      list.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      place(list, btn);
      activate(list, opts[sel.selectedIndex] || opts[0]);
      list.focus({ preventScroll: true });
    };
    const close = (refocus) => {
      if (list.hidden) return;
      list.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
      if (refocus) btn.focus();
    };
    const choose = (li) => {
      const i = opts.indexOf(li);
      if (i >= 0 && i !== sel.selectedIndex) { sel.selectedIndex = i; sel.dispatchEvent(new Event('change', { bubbles: true })); }
      sync();
      close(true);
    };
    sel.hidden = true;
    sel.tabIndex = -1;
    sel.before(box);
    box.append(sel, btn, list);
    sync();
    sel.form && sel.form.addEventListener('reset', () => setTimeout(sync));
    btn.addEventListener('click', () => (list.hidden ? open() : close(true)));
    btn.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); }
    });
    list.addEventListener('click', (e) => { const li = e.target.closest('li'); if (li) choose(li); });
    list.addEventListener('mousemove', (e) => { const li = e.target.closest('li'); if (li && !li.classList.contains('active')) activate(list, li); });
    list.addEventListener('keydown', (e) => {
      const cur = opts.findIndex((li) => li.classList.contains('active'));
      const to = { ArrowDown: Math.min(cur + 1, opts.length - 1), ArrowUp: Math.max(cur - 1, 0), Home: 0, End: opts.length - 1 }[e.key];
      if (to !== undefined) { e.preventDefault(); activate(list, opts[to]); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(opts[cur]); }
      else if (e.key === 'Escape') { e.preventDefault(); close(true); }
      else if (e.key === 'Tab') close(false);
      else if (e.key.length === 1) {
        const k = e.key.toLowerCase();
        const hit = opts.find((li, i) => i > cur && li.textContent.toLowerCase().startsWith(k)) || opts.find((li) => li.textContent.toLowerCase().startsWith(k));
        if (hit) activate(list, hit);
      }
    });
    list.addEventListener('focusout', (e) => { if (!box.contains(e.relatedTarget)) close(false); });
    document.addEventListener('pointerdown', (e) => { if (!box.contains(e.target)) close(false); });
  }

  // The compare page's name picker: an input that suggests verified tools as you type, from the
  // server's datalist, in a list like the dropdown's. Picking one adds it.
  for (const input of $$('input[data-combo]')) {
    const data = input.list;
    if (!data) continue;
    const tools = [...data.options].map((o) => ({ slug: o.value, name: o.textContent }));
    const id = 'combo' + ++ddCount;
    input.removeAttribute('list');
    data.remove();
    const box = document.createElement('div');
    box.className = 'combo';
    input.before(box);
    const list = document.createElement('ul');
    list.className = 'dd-list';
    list.id = id;
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    box.append(input, list);
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id);
    let items = [];
    const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); };
    const mark = (li) => {
      for (const o of items) o.classList.toggle('active', o === li);
      if (li) { input.setAttribute('aria-activedescendant', li.id); reveal(list, li); }
      else input.removeAttribute('aria-activedescendant');
    };
    const show = () => {
      const q = input.value.trim().toLowerCase();
      const hits = tools.filter((t) => !q || t.name.toLowerCase().includes(q) || t.slug.includes(q)).slice(0, 60);
      items = hits.map((t, i) => {
        const li = document.createElement('li');
        li.id = id + '-' + i;
        li.setAttribute('role', 'option');
        li.dataset.name = t.name;
        const at = q ? t.name.toLowerCase().indexOf(q) : -1;
        if (at >= 0) {
          const m = document.createElement('mark');
          m.textContent = t.name.slice(at, at + q.length);
          li.append(t.name.slice(0, at), m, t.name.slice(at + q.length));
        } else li.textContent = t.name;
        return li;
      });
      if (!items.length) {
        const li = document.createElement('li');
        li.className = 'dd-empty';
        li.textContent = ${J('No verified tool by that name', '沒有這個名稱的已驗證工具')};
        list.replaceChildren(li);
      } else list.replaceChildren(...items);
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      place(list, input);
    };
    const pick = (li) => {
      input.value = li.dataset.name;
      close();
      if (input.form) input.form.requestSubmit();
    };
    input.addEventListener('input', () => { show(); mark(input.value.trim() ? items[0] : null); });
    input.addEventListener('focus', show);
    input.addEventListener('keydown', (e) => {
      const cur = items.findIndex((li) => li.classList.contains('active'));
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (list.hidden) show();
        if (items.length) mark(items[e.key === 'ArrowDown' ? Math.min(cur + 1, items.length - 1) : Math.max(cur - 1, 0)]);
      } else if (e.key === 'Enter' && !list.hidden && cur >= 0) { e.preventDefault(); pick(items[cur]); }
      else if (e.key === 'Escape' && !list.hidden) { e.preventDefault(); close(); }
    });
    // pointerdown, not click: the input keeps focus, so its blur doesn't close the list first.
    list.addEventListener('pointerdown', (e) => { e.preventDefault(); const li = e.target.closest('li[role=option]'); if (li) pick(li); });
    input.addEventListener('blur', close);
  }

  // ---------------------------------------------------------------- install steps per system
  // Tabs, opened on the system this browser runs on when pickfit has steps for it.
  const mySystem = (() => {
    const p = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || navigator.userAgent || '').toLowerCase();
    if (/mac|iphone|ipad/.test(p)) return 'macos';
    if (/win/.test(p)) return 'windows';
    if (/linux|x11|cros/.test(p)) return 'linux';
    return '';
  })();
  // How far pickfit got: the reader's own system (or the first) in view, the others folded under "Other systems".
  for (const more of $$('[data-progress-more]')) {
    const rows = $$('.progress-row[data-os]', more.parentElement);
    const keep = rows.find((r) => r.dataset.os === mySystem) || rows[0];
    rows[0].before(keep);
    for (const r of rows) if (r !== keep) more.append(r);
    const label = more.querySelector('summary');
    for (const r of rows) if (r !== keep) label.lastElementChild.before(r.querySelector('.os').cloneNode(true));
    more.hidden = false;
  }
  for (const bar of $$('[data-os-tabs]')) {
    const tabs = $$('[role=tab]', bar);
    const panel = (t) => document.getElementById(t.getAttribute('aria-controls'));
    const show = (tab, focus) => {
      for (const t of tabs) {
        const on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        panel(t).hidden = !on;
      }
      if (focus) tab.focus();
    };
    const mine = tabs.find((t) => t.dataset.os === mySystem);
    if (mine) {
      const tag = document.createElement('span');
      tag.className = 'os-mine';
      tag.textContent = ${J('yours', '你的系統')};
      mine.append(tag);
    }
    // A link to one system's steps (#install-linux) opens that tab.
    const linked = tabs.find((t) => '#' + t.getAttribute('aria-controls') === location.hash);
    bar.hidden = false;
    show(linked || mine || tabs[0], false);
    bar.addEventListener('click', (e) => { const t = e.target.closest('[role=tab]'); if (t) show(t, false); });
    bar.addEventListener('keydown', (e) => {
      const i = tabs.indexOf(document.activeElement);
      const to = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key];
      if (to !== undefined) { e.preventDefault(); show(tabs[to], true); }
    });
  }

  // ---------------------------------------------------------------- install, check, use: one stage at a time
  for (const box of $$('[data-stepper]')) {
    const stages = $$('[data-stage]', box);
    const tabs = $$('.stage-tabs [data-goto]', box);
    const go = (i, scroll) => {
      stages.forEach((s, j) => (s.hidden = j !== i));
      tabs.forEach((t, j) => {
        if (j === i) t.setAttribute('aria-current', 'step'); else t.removeAttribute('aria-current');
        t.classList.toggle('done', j < i);
      });
      // A long stage leaves Next far below the tabs: bring the start of the next one back into view.
      if (scroll && box.getBoundingClientRect().top < 80) box.scrollIntoView({ block: 'start', behavior: still() ? 'auto' : 'smooth' });
    };
    box.addEventListener('click', (e) => {
      const b = e.target.closest('[data-goto]');
      if (!b) return;
      go(+b.dataset.goto, !b.closest('.stage-tabs'));
      if (!b.closest('.stage-tabs')) { const t = tabs[+b.dataset.goto]; if (t) t.focus({ preventScroll: true }); }
    });
    go(0, false);
  }

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

  // ---------------------------------------------------------------- the clip's chapter player
  // Server-rendered as the browser's own player plus a hidden bar; with chapters, the bar takes over:
  // one segment per chapter, its name on hover and while dragging, arrow keys and Page Up/Down to move.
  const clockOf = (t) => Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0');
  for (const fig of $$('[data-player]')) {
    const video = $('video', fig);
    const track = $('[data-track]', fig);
    const tip = $('[data-tip-box]', fig);
    const time = $('[data-time]', fig);
    const play = $('[data-play]', fig);
    const items = $$('.chapters [data-seek]', fig);
    const segs = $$('.chap-seg', track).map((el) => ({ el, start: +el.dataset.start, end: +el.dataset.end, title: el.dataset.title, fill: $('.chap-fill', el) }));
    if (!video || !segs.length) continue;
    for (const s of segs) s.el.style.flexGrow = String(Math.max(s.end - s.start, 0.1));
    video.controls = false;
    $('[data-bar]', fig).hidden = false;
    const total = () => (isFinite(video.duration) && video.duration > 0 ? video.duration : segs[segs.length - 1].end);
    const at = (t) => { let cur = segs[0]; for (const s of segs) if (t >= s.start) cur = s; return cur; };
    const paint = () => {
      const t = video.currentTime;
      const cur = at(t);
      for (const s of segs) s.fill.style.transform = 'scaleX(' + Math.min(1, Math.max(0, (t - s.start) / (s.end - s.start))) + ')';
      time.textContent = clockOf(t) + ' / ' + clockOf(total());
      track.setAttribute('aria-valuenow', String(Math.round(t)));
      track.setAttribute('aria-valuetext', clockOf(t) + ', ' + cur.title);
      items.forEach((b, i) => (segs[i] === cur ? b.setAttribute('aria-current', 'true') : b.removeAttribute('aria-current')));
      play.classList.toggle('is-playing', !video.paused);
      play.setAttribute('aria-label', video.paused ? play.dataset.labelPlay : play.dataset.labelPause);
    };
    const seek = (t) => { video.currentTime = Math.max(0, Math.min(total() - 0.05, t)); paint(); };
    // Segments have gaps between them, so a point maps to time through the segment it is over.
    const timeAt = (x) => {
      for (const s of segs) {
        const r = s.el.getBoundingClientRect();
        if (x <= r.right + 1.5) return s.start + Math.min(1, Math.max(0, (x - r.left) / r.width)) * (s.end - s.start);
      }
      return total();
    };
    const showTip = (x) => {
      const t = timeAt(x);
      const r = track.getBoundingClientRect();
      tip.textContent = at(t).title + ' · ' + clockOf(t);
      tip.hidden = false;
      tip.style.left = Math.min(Math.max(x - r.left, 60), r.width - 60) + 'px';
    };
    let dragging = false;
    track.addEventListener('pointerdown', (e) => { dragging = true; track.setPointerCapture(e.pointerId); seek(timeAt(e.clientX)); showTip(e.clientX); });
    track.addEventListener('pointermove', (e) => { showTip(e.clientX); if (dragging) seek(timeAt(e.clientX)); });
    const stop = (e) => { dragging = false; if (e.pointerType !== 'mouse') tip.hidden = true; };
    track.addEventListener('pointerup', stop);
    track.addEventListener('pointercancel', stop);
    track.addEventListener('pointerleave', () => { if (!dragging) tip.hidden = true; });
    const toggle = () => (video.paused ? video.play() : video.pause());
    track.addEventListener('keydown', (e) => {
      const t = video.currentTime;
      const i = segs.indexOf(at(t));
      const to = {
        ArrowRight: t + 5, ArrowUp: t + 5, ArrowLeft: t - 5, ArrowDown: t - 5, Home: 0, End: total(),
        PageDown: segs[i + 1] ? segs[i + 1].start : total(),
        PageUp: t - segs[i].start > 2 ? segs[i].start : (segs[i - 1] || segs[0]).start,
      };
      if (e.key in to) { e.preventDefault(); seek(to[e.key]); }
      else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(); }
    });
    play.addEventListener('click', toggle);
    video.addEventListener('click', toggle);
    $('[data-mute]', fig).addEventListener('click', (e) => { video.muted = !video.muted; e.currentTarget.classList.toggle('is-muted', video.muted); });
    $('[data-full]', fig).addEventListener('click', () => {
      const box = $('.player', fig);
      if (document.fullscreenElement) document.exitFullscreen();
      else if (box.requestFullscreen) box.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
    });
    for (const ev of ['timeupdate', 'play', 'pause', 'loadedmetadata', 'seeked']) video.addEventListener(ev, paint);
    paint();
  }
  // The chapter list and each feature's "Watch it at" are links to the clip at that time; with the
  // script they play it in the page instead.
  for (const b of $$('[data-seek]')) {
    b.addEventListener('click', (e) => {
      const fig = $('[data-player]');
      const video = fig && $('video', fig);
      if (!video) return;
      e.preventDefault();
      video.currentTime = +b.dataset.seek;
      video.play();
      fig.scrollIntoView({ block: 'nearest', behavior: still() ? 'auto' : 'smooth' });
    });
  }

  // Close the small-screen menu after following one of its links.
  for (const a of $$('.menu-nav a')) a.addEventListener('click', () => a.closest('details').removeAttribute('open'));
})();
`;
