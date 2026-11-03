// Record the real pickfit.app for the main line: search on the home page, the results,
// MangoDisk's tool page and its chapter player.
//
//   node capture/web.mjs [--need "..."]  → rec/web/frames/*.jpg, rec/web/frames.json, rec/web/markers.json
//   then: node capture/frames2mp4.mjs rec/web → rec/web/web.mp4 (constant 30 fps)
//
// Chrome (headless) at 1440x810 CSS pixels, 2x device pixels, light scheme, English. Frames come
// from the DevTools screencast with their own timestamps. The cursor is drawn by a small overlay
// that follows the real mouse events. Requests carry X-Pickfit-Reporter: demo so this run is not
// counted as outside use.

import { chromium } from 'playwright';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', 'rec', 'web');
const SITE = 'https://pickfit.app';
const argv = process.argv.slice(2);
const NEED = argv.includes('--need') ? argv[argv.indexOf('--need') + 1] : "My Mac's disk is full. I want a free, safe app to find and clean large files.";
const SEEK = argv.includes('--seek') ? Number(argv[argv.indexOf('--seek') + 1]) : 12; // where the chapter's results show

const CURSOR = `
(() => {
  if (window.__cursor) return;
  const c = document.createElement('div');
  c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M5 3 L5 22 L10 17 L13.5 25 L17 23.5 L13.5 15.8 L20.5 15.8 Z" fill="#1A1D17" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, { position: 'fixed', left: '0', top: '0', zIndex: 2147483647, pointerEvents: 'none', transform: 'translate(-100px,-100px)', transition: 'none' });
  const ring = document.createElement('div');
  Object.assign(ring.style, { position: 'fixed', width: '34px', height: '34px', marginLeft: '-12px', marginTop: '-12px', borderRadius: '50%', border: '2px solid #C4552D', opacity: '0', zIndex: 2147483646, pointerEvents: 'none' });
  const add = () => { document.documentElement.append(c, ring); };
  if (document.documentElement) add(); else addEventListener('DOMContentLoaded', add);
  addEventListener('mousemove', (e) => { c.style.transform = 'translate(' + (e.clientX - 5) + 'px,' + (e.clientY - 3) + 'px)'; ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { ring.animate([{ opacity: 0.9, transform: 'scale(.6)' }, { opacity: 0, transform: 'scale(1.4)' }], { duration: 420, easing: 'cubic-bezier(.16,1,.3,1)' }); }, true);
  window.__cursor = c;
})();`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  await rm(OUT, { recursive: true, force: true });
  await mkdir(join(OUT, 'frames'), { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', args: ['--hide-scrollbars', '--autoplay-policy=no-user-gesture-required'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 2, colorScheme: 'light', locale: 'en-US', extraHTTPHeaders: { 'X-Pickfit-Reporter': 'demo' } });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  const markers = [];
  let t0 = null;
  cdp.on('Page.screencastFrame', async (f) => {
    const ts = f.metadata.timestamp;
    if (t0 === null) t0 = ts;
    const name = `${String(frames.length).padStart(6, '0')}.jpg`;
    frames.push({ name, t: ts - t0 });
    writeFile(join(OUT, 'frames', name), Buffer.from(f.data, 'base64'));
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  const mark = (label) => { const t = t0 === null ? 0 : Date.now() / 1000 - t0; markers.push({ label, t: Number(t.toFixed(3)) }); console.log(`${t.toFixed(2)}s ${label}`); };

  // a human-ish mouse path to an element's centre, then a click
  let mx = 1100, my = 700;
  async function moveTo(locator, { click = true, dx = 0, dy = 0 } = {}) {
    await locator.scrollIntoViewIfNeeded();
    const b = await locator.boundingBox();
    const x = b.x + b.width / 2 + dx, y = b.y + b.height / 2 + dy;
    const steps = 26;
    for (let i = 1; i <= steps; i++) {
      const k = i / steps, e = 1 - Math.pow(1 - k, 3);
      await page.mouse.move(mx + (x - mx) * e, my + (y - my) * e);
      await sleep(14);
    }
    mx = x; my = y;
    if (click) { await sleep(120); await page.mouse.down(); await sleep(70); await page.mouse.up(); }
  }

  await page.goto(`${SITE}/?lang=en`, { waitUntil: 'networkidle' });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 2880, maxHeight: 1620, everyNthFrame: 1 });
  await page.mouse.move(mx, my);
  await sleep(1200);
  mark('home');

  const field = page.locator('textarea[name="need"]');
  await moveTo(field);
  await field.fill('');
  mark('type');
  await page.keyboard.type(NEED, { delay: 42 });
  await sleep(500);
  await moveTo(page.locator('input[name="os"][value="macos"]').locator('xpath=..'));
  mark('macos');
  await sleep(350);
  await moveTo(page.locator('input[name="free_only"]').locator('xpath=..'));
  mark('free');
  await sleep(500);
  const find = page.locator('#search button[type="submit"]').first();
  await moveTo(find, { click: false });
  await sleep(250);
  mark('find');
  await find.click();
  mark('results-loading');
  await page.waitForSelector('.pick', { timeout: 120000 });
  mark('results');
  await sleep(2600);
  // the first pick (Fitz's answer)
  const first = page.locator('.pick').first();
  await first.scrollIntoViewIfNeeded();
  await page.evaluate(() => { const el = document.querySelector('.pick'); const y = el.getBoundingClientRect().top + scrollY - 90; scrollTo({ top: y, behavior: 'smooth' }); });
  await sleep(1400);
  mark('first-pick');
  await sleep(2200);
  const warn = first.locator('text=/known vulnerabilit/').first();
  if (await warn.count()) { await moveTo(warn, { click: false }); mark('security'); await sleep(1800); }
  const link = first.locator('a', { hasText: 'MangoDisk' }).first();
  await moveTo(link, { click: false });
  await sleep(300);
  mark('open-tool');
  await Promise.all([page.waitForURL(/\/tool\/mangodisk/, { timeout: 60000 }), link.click()]);
  await page.waitForLoadState('networkidle').catch(() => {});
  mark('tool-page');
  await sleep(1800);
  const video = page.locator('video').first();
  if (await video.count()) {
    await page.evaluate(() => { document.querySelector('video').muted = true; });
    const chapter = page.locator('text=Find and clean largest files').first();
    if (await chapter.count()) { await moveTo(chapter); mark('chapter-largest'); }
    await sleep(900);
    await page.evaluate((s) => { const v = document.querySelector('video'); v.currentTime = s; v.play().catch(() => {}); }, SEEK);
    mark('seek');
    await sleep(17000);
  }
  mark('end');
  await cdp.send('Page.stopScreencast');
  await sleep(300);
  await writeFile(join(OUT, 'frames.json'), JSON.stringify(frames));
  await writeFile(join(OUT, 'markers.json'), JSON.stringify(markers, null, 1));
  await browser.close();
  console.log(`${frames.length} frames → ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
