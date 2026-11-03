// Things printed on paper and on the laptop screen, as canvas drawings. All fictional and
// generic: no real brands. Ink only; the one colour is the red of the disk-full bar.

import { text, cardPath } from '../../kit/props.js';
import { site, fonts } from '../../kit/tokens.js';

const GREY = { wall: '#D6D6D0', win: '#FFFFFF', bar: '#ECECE7', line: '#D2D2CC', soft: '#B9B9B2' };

function rr(ctx, x, y, w, h, r, fill, stroke, lw = 2) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
}

// ------------------------------------------------------------------ the laptop screen
// state: { mode: 'desk' | 'search' | 'tabs' | 'code', typed, tabs, lines, alert }
export const CODE = [
  'import os, shutil',
  '',
  'def scan(root):',
  '    sizes = {}',
  '    for d, _, files in os.walk(root):',
  '        for f in files:',
  '            p = os.path.join(d, f)',
  '            try:',
  '                sizes[p] = os.path.getsize(p)',
  '            except OSError:',
  '                pass  # TODO',
  '    return sizes',
  '',
  'def largest(sizes, n=50):',
  '    return sorted(sizes.items(),',
  '        key=lambda kv: -kv[1])[:n]',
  '',
  'def clean(paths, dry_run=True):',
  '    for p in paths:',
  '        if dry_run: print("would delete", p)',
  '        else: os.remove(p)   # careful',
  '',
  'if __name__ == "__main__":',
  '    s = scan(os.path.expanduser("~"))',
  '    clean([p for p, _ in largest(s)])',
];

export function drawScreen(ctx, w, h, s) {
  ctx.fillStyle = GREY.wall; ctx.fillRect(0, 0, w, h);
  // menu bar
  ctx.fillStyle = '#F4F4F1'; ctx.fillRect(0, 0, w, 30);
  ctx.fillStyle = site.ink;
  ctx.beginPath(); ctx.arc(26, 15, 7, 0, Math.PI * 2); ctx.fill();
  ['File', 'Edit', 'View', 'Window'].forEach((m, i) => text(ctx, m, 52 + i * 70, 21, { size: 16, weight: 500 }));
  text(ctx, s.clock || '', w - 20, 21, { size: 16, weight: 500, align: 'right' });

  if (s.mode === 'desk') {
    // a desktop cluttered with big files
    const names = ['IMG_2041.mov', 'backup_old.zip', 'render_v3.mp4', 'photos 2019', 'installer.dmg', 'archive (2).zip', 'VM disk.img', 'export_final.mov', 'Downloads old'];
    names.forEach((n, i) => {
      const cx = w - 90 - Math.floor(i / 5) * 150, cy = 90 + (i % 5) * 108;
      rr(ctx, cx - 26, cy - 34, 52, 60, 6, '#F7F7F4', '#9C9C95', 2);
      text(ctx, n, cx, cy + 50, { size: 14, align: 'center', color: site.ink2 });
    });
  } else if (s.mode === 'search' || s.mode === 'tabs') {
    browser(ctx, w, h, s);
  } else if (s.mode === 'code') {
    editor(ctx, w, h, s);
  }
  // the dock strip at the bottom of the desktop
  rr(ctx, w / 2 - 190, h - 44, 380, 36, 10, 'rgba(255,255,255,0.7)');
  for (let i = 0; i < 7; i++) rr(ctx, w / 2 - 170 + i * 50, h - 38, 28, 24, 6, '#C7C7C0');
  if (s.alert) alertDialog(ctx, w / 2 - 260, 110, 520, 220);
}

function browser(ctx, w, h, s) {
  const x = 40, y = 52, W = w - 80, H = h - 110;
  rr(ctx, x, y, W, H, 12, GREY.win);
  // the tab strip: tabs squeeze as there are more
  ctx.save(); ctx.beginPath(); ctx.roundRect(x, y, W, H, 12); ctx.clip();
  ctx.fillStyle = GREY.bar; ctx.fillRect(x, y, W, 44);
  const n = Math.max(1, s.tabs || 1);
  const tw = Math.min(220, (W - 120) / n);
  for (let i = 0; i < n; i++) {
    const tx = x + 70 + i * tw;
    rr(ctx, tx + 2, y + 8, tw - 4, 36, 8, i === n - 1 ? GREY.win : '#DEDED8');
    if (tw > 60) {
      ctx.save(); ctx.beginPath(); ctx.rect(tx + 8, y + 8, tw - 20, 36); ctx.clip();
      text(ctx, i === 0 && n === 1 ? 'New tab' : TAB_TITLES[i % TAB_TITLES.length], tx + 12, y + 32, { size: 14, color: site.ink2 });
      ctx.restore();
    }
  }
  for (let i = 0; i < 3; i++) { ctx.fillStyle = '#BDBDB6'; ctx.beginPath(); ctx.arc(x + 18 + i * 16, y + 22, 5, 0, Math.PI * 2); ctx.fill(); }
  ctx.restore();
  // address bar
  rr(ctx, x + 70, y + 54, W - 140, 34, 17, '#F1F1EE');
  if (s.mode === 'search') {
    // a plain search page: one big field
    const fx = x + W / 2 - 300, fy = y + H / 2 - 40;
    text(ctx, 'Search', x + W / 2, fy - 40, { size: 44, weight: 700, family: fonts.display, align: 'center', color: site.ink2 });
    rr(ctx, fx, fy, 600, 64, 32, '#FFFFFF', '#8E8E87', 2.5);
    ctx.strokeStyle = site.ink3; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(fx + 36, fy + 30, 11, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(fx + 44, fy + 38); ctx.lineTo(fx + 52, fy + 46); ctx.stroke();
    const tw2 = text(ctx, s.typed || '', fx + 66, fy + 41, { size: 26, color: site.ink });
    if (s.caret) { ctx.fillStyle = site.ink; ctx.fillRect(fx + 70 + tw2, fy + 16, 2.5, 32); }
  } else {
    // results: a heading and grey lines
    const rx = x + 90;
    for (let i = 0; i < 4; i++) {
      const ry = y + 130 + i * 112;
      text(ctx, RESULTS[i], rx, ry, { size: 26, weight: 600, color: site.ink });
      for (let j = 0; j < 2; j++) rr(ctx, rx, ry + 18 + j * 22, (W - 240) * (j ? 0.62 : 0.9), 10, 5, GREY.line);
    }
  }
}

const RESULTS = ['Best free disk cleaner 2026', 'Top 10 Mac cleaners, ranked', 'Do you even need a cleaner?', 'Cleaner A vs Cleaner B'];

function editor(ctx, w, h, s) {
  const x = 40, y = 52, W = w - 80, H = h - 110;
  rr(ctx, x, y, W, H, 12, GREY.win);
  ctx.save(); ctx.beginPath(); ctx.roundRect(x, y, W, H, 12); ctx.clip();
  ctx.fillStyle = GREY.bar; ctx.fillRect(x, y, W, 40);
  text(ctx, `cleaner.py — ${s.version || 'v1'}`, x + W / 2, y + 27, { size: 16, weight: 600, align: 'center', color: site.ink2 });
  for (let i = 0; i < 3; i++) { ctx.fillStyle = '#BDBDB6'; ctx.beginPath(); ctx.arc(x + 20 + i * 18, y + 20, 6, 0, Math.PI * 2); ctx.fill(); }
  const lh = 24, top = y + 70;
  const shown = Math.min(CODE.length, s.lines || 0);
  const scroll = Math.max(0, shown - 19) * lh;
  for (let i = 0; i < shown; i++) {
    const ly = top + i * lh - scroll;
    if (ly < y + 50) continue;
    text(ctx, String(i + 1).padStart(2, ' '), x + 46, ly, { size: 16, family: fonts.mono, color: GREY.soft, align: 'right' });
    let line = CODE[i];
    if (i === shown - 1 && s.partial != null) line = line.slice(0, Math.floor(line.length * s.partial));
    text(ctx, line, x + 70, ly, { size: 17, family: fonts.mono, color: site.ink });
  }
  ctx.restore();
}

export const TAB_TITLES = ['Best free disk cleaner 2026', 'Top 10 Mac cleaners', 'Disk cleaner review', 'Cleaner A vs Cleaner B', 'Free? Read this first', 'Forum: what do you use?', 'Video: clean your Mac', '12 best cleaners, ranked', 'Is it safe to use?', 'Top 7 free cleaners'];

// ------------------------------------------------------------------ alert (paper card, and on screen)
export function alertDialog(ctx, x, y, w, h, k = 1) {
  rr(ctx, x, y, w, h, 16 * k, '#FFFFFF', '#A9A9A2', 2 * k);
  // a disk glyph
  rr(ctx, x + 30 * k, y + 34 * k, 54 * k, 66 * k, 8 * k, '#EDEDE8', site.ink2, 3 * k);
  ctx.fillStyle = site.ink2; ctx.fillRect(x + 42 * k, y + 82 * k, 30 * k, 5 * k);
  text(ctx, 'Your disk is almost full', x + 106 * k, y + 62 * k, { size: 30 * k, weight: 700, family: fonts.display, color: site.ink });
  text(ctx, 'Startup disk · 1.9 GB of 494 GB free', x + 106 * k, y + 96 * k, { size: 19 * k, color: site.ink2 });
  // the capacity bar: the only colour of the night
  const bx = x + 30 * k, by = y + 128 * k, bw = w - 60 * k, bh = 18 * k;
  rr(ctx, bx, by, bw, bh, bh / 2, '#E4E4DF');
  rr(ctx, bx, by, bw * 0.985, bh, bh / 2, site.fail);
  rr(ctx, x + w - 250 * k, y + h - 54 * k, 100 * k, 36 * k, 9 * k, '#FFFFFF', '#8E8E87', 2 * k);
  text(ctx, 'Later', x + w - 200 * k, y + h - 30 * k, { size: 17 * k, align: 'center', color: site.ink });
  rr(ctx, x + w - 138 * k, y + h - 54 * k, 108 * k, 36 * k, 9 * k, site.ink);
  text(ctx, 'Manage…', x + w - 84 * k, y + h - 30 * k, { size: 17 * k, align: 'center', color: '#FFFFFF', weight: 600 });
}

// ------------------------------------------------------------------ paper props
export function drawTab(title) {
  return (ctx, w, h) => {
    text(ctx, title, 26, h / 2 + 12, { size: 34, weight: 600, color: site.ink });
  };
}

function star(ctx, cx, cy, r, filled) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, rr2 = i % 2 ? r * 0.45 : r;
    ctx.lineTo(cx + Math.cos(a) * rr2, cy + Math.sin(a) * rr2);
  }
  ctx.closePath();
  ctx.lineWidth = 3; ctx.strokeStyle = site.ink; ctx.fillStyle = site.ink;
  if (filled) ctx.fill(); else ctx.stroke();
}

export function drawBubble(line, stars, who) {
  return (ctx, w, h) => {
    text(ctx, who, 40, 62, { size: 26, color: site.ink3, weight: 500 });
    for (let i = 0; i < 5; i++) star(ctx, w - 200 + i * 36, 52, 15, i < stars);
    text(ctx, line, 40, 146, { size: 66, weight: 700, family: fonts.display, color: site.ink, tracking: -1 });
  };
}

export function drawTrial(ctx, w, h) {
  text(ctx, 'Premium', 40, 66, { size: 28, weight: 600, color: site.ink3 });
  text(ctx, 'Free trial · $39.99/yr', 40, 150, { size: 64, weight: 700, family: fonts.display, color: site.ink, tracking: -1 });
  text(ctx, 'Renews automatically. Cancel anytime.', 40, 200, { size: 26, color: site.ink2 });
  rr(ctx, 40, h - 92, 260, 58, 12, site.ink);
  text(ctx, 'Start free trial', 170, h - 54, { size: 26, weight: 600, align: 'center', color: '#FFFFFF' });
}

export function drawAccess(ctx, w, h) {
  // a padlock
  ctx.strokeStyle = site.ink; ctx.lineWidth = 7;
  ctx.beginPath(); ctx.arc(66, 70, 18, Math.PI, 0); ctx.stroke();
  rr(ctx, 40, 68, 52, 44, 7, site.ink);
  text(ctx, 'Allow Full Disk Access?', 112, 106, { size: 50, weight: 700, family: fonts.display, color: site.ink, tracking: -1 });
  text(ctx, 'This app wants to read every file', 40, 172, { size: 28, color: site.ink2 });
  text(ctx, 'on your disk, including Mail and Photos.', 40, 210, { size: 28, color: site.ink2 });
  rr(ctx, w - 470, h - 96, 210, 60, 12, '#FFFFFF', '#8E8E87', 3);
  text(ctx, 'Don’t Allow', w - 365, h - 56, { size: 26, align: 'center', color: site.ink });
  rr(ctx, w - 240, h - 96, 200, 60, 12, site.ink);
  text(ctx, 'Allow', w - 140, h - 56, { size: 26, align: 'center', weight: 600, color: '#FFFFFF' });
}

export function drawNote(line) {
  return (ctx, w, h) => {
    ctx.fillStyle = 'rgba(0,0,0,0.06)'; ctx.fillRect(0, 0, w, 26);
    const words = line.split(' ');
    const size = words.length > 2 ? 44 : 50;
    words.forEach((wd, i) => text(ctx, wd, 26, 84 + i * size * 1.08, { size, weight: 700, family: fonts.display, color: site.ink, tracking: -1 }));
  };
}

export function drawVersion(v) {
  return (ctx, w, h) => {
    ctx.fillStyle = site.ink;
    ctx.beginPath(); ctx.arc(34, h / 2, 9, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(34, h / 2, 5, 0, Math.PI * 2); ctx.fill();
    text(ctx, v, w / 2 + 16, h / 2 + 30, { size: 92, weight: 800, family: fonts.display, color: site.ink, align: 'center', tracking: -3 });
  };
}

export function drawQuestion(ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  text(ctx, '?', w / 2, h * 0.86, { size: h * 0.95, weight: 800, family: fonts.display, color: site.ink, align: 'center' });
}

// ------------------------------------------------------------------ the disclosure
export function drawDisclosureLine(lead, rest) {
  return (ctx, w, h) => {
    ctx.clearRect(0, 0, w, h);
    const size = 84;
    const lw = text(ctx, lead, 0, h * 0.74, { size, weight: 700, family: fonts.display, color: site.ink, tracking: -1.5 });
    text(ctx, rest, lw + 26, h * 0.74, { size, weight: 400, family: fonts.display, color: site.ink, tracking: -1 });
  };
}

// ------------------------------------------------------------------ the request card and the wordmark
export function drawAsk(ctx, w, h) {
  text(ctx, 'I need', 56, 118, { size: 64, weight: 700, family: fonts.display, color: site.ink2, tracking: -1.3 });
}

// The wordmark; with sewn = true the ink dot of its second i is cleared (with a paper ring,
// as on the site) for the rufous dot. Returns where that dot goes (canvas px).
export function drawWordmark(ctx, w, h, size, sewn = false) {
  ctx.clearRect(0, 0, w, h);
  const track = -0.03 * size;
  const opts = { size, weight: 800, family: fonts.display, color: site.ink, tracking: track };
  ctx.font = `800 ${size}px ${fonts.display}`;
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${track}px`;
  const total = ctx.measureText('pickf').width + ctx.measureText('i').width + ctx.measureText('t').width;
  let x = (w - total) / 2;
  const base = h * 0.78;
  x += text(ctx, 'pickf', x, base, opts);
  const ix = x;
  const iw = text(ctx, 'i', x, base, opts);
  x += iw;
  text(ctx, 't', x, base, opts);
  // find the dot of that i: draw it alone and scan for its first ink rows
  const dot = findTittle(size, opts);
  const cx = ix + dot.cx, cy = base + dot.cy;
  // the site's dot: .26em across with a .07em paper ring
  if (sewn) {
    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath(); ctx.arc(cx, cy, 0.2 * size, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
  return { cx, cy, r: 0.13 * size, em: size };
}

function findTittle(size, opts) {
  const c = document.createElement('canvas');
  c.width = Math.ceil(size * 1.2); c.height = Math.ceil(size * 1.6);
  const ctx = c.getContext('2d');
  const base = Math.round(size * 1.2);
  text(ctx, 'i', Math.round(size * 0.2), base, opts);
  const { data, width, height } = ctx.getImageData(0, 0, c.width, c.height);
  const ink = (x, y) => data[(y * width + x) * 4 + 3] > 100;
  let top = -1, bottom = -1, minX = width, maxX = 0;
  for (let y = 0; y < height; y++) {
    let any = false;
    for (let x = 0; x < width; x++) if (ink(x, y)) { any = true; if (top >= 0 && bottom < 0) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); } }
    if (any && top < 0) { top = y; }
    if (top >= 0 && bottom < 0) {
      if (!any) { bottom = y; break; }
      for (let x = 0; x < width; x++) if (ink(x, y)) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); }
    }
  }
  const cx = (minX + maxX) / 2 - Math.round(size * 0.2);
  const cy = (top + bottom) / 2 - base;
  return { cx, cy, r: Math.max((maxX - minX) / 2, (bottom - top) / 2) };
}
