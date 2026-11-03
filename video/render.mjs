// Render an animated scene to video, one frame at a time.
//
//   node render.mjs <scene> [--from 0] [--to <duration>] [--still 3.5] [--out out/<scene>.mp4]
//
// Serves video/ (and the site's font) over http, opens scenes/<scene>.html?render in Chrome,
// and for every frame calls window.__scene.seek(t), screenshots the canvas and pipes it to
// ffmpeg. --still writes one PNG instead.

import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { extname, join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.mp4': 'video/mp4', '.webm': 'video/webm' };

export function serve() {
  const server = createServer(async (req, res) => {
    const url = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const file = url.startsWith('/repo/') ? join(REPO, url.slice(6)) : join(HERE, url);
    if (!file.startsWith(REPO)) { res.writeHead(403).end(); return; }
    try {
      const body = await readFile(file);
      res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' });
      res.end(body);
    } catch { res.writeHead(404).end(); }
  });
  return new Promise((ok) => server.listen(0, '127.0.0.1', () => ok(server)));
}

function args() {
  const a = process.argv.slice(2);
  const o = { scene: a[0] };
  for (let i = 1; i < a.length; i += 2) o[a[i].replace(/^--/, '')] = a[i + 1];
  return o;
}

async function main() {
  const o = args();
  if (!o.scene) throw new Error('usage: node render.mjs <scene> [--from s] [--to s] [--still s] [--out file]');
  const server = await serve();
  const port = server.address().port;
  const browser = await chromium.launch({
    channel: 'chrome',
    args: ['--use-angle=metal', '--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
  });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.error('[page]', m.text()); });
  page.on('pageerror', (e) => console.error('[page error]', e.message));
  await page.goto(`http://127.0.0.1:${port}/scenes/${o.scene}.html?render`);
  await page.waitForFunction(() => window.__scene);
  await page.evaluate(() => window.__scene.ready);
  const { duration, fps } = await page.evaluate(() => ({ duration: window.__scene.duration, fps: window.__scene.fps }));
  const canvas = await page.$('canvas');

  if (o.still !== undefined) {
    await page.evaluate((t) => window.__scene.seek(t), Number(o.still));
    const out = o.out || join(HERE, 'out', `${o.scene}-${o.still}.png`);
    await mkdir(dirname(out), { recursive: true });
    await writeFile(out, await canvas.screenshot({ type: 'png' }));
    console.log(out);
  } else {
    const from = Number(o.from ?? 0), to = Number(o.to ?? duration);
    const out = o.out || join(HERE, 'out', `${o.scene}.mp4`);
    await mkdir(dirname(out), { recursive: true });
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '12', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const frames = Math.round((to - from) * fps);
    const t0 = Date.now();
    for (let i = 0; i < frames; i++) {
      await page.evaluate((t) => window.__scene.seek(t), from + i / fps);
      const jpg = await canvas.screenshot({ type: 'jpeg', quality: 96 });
      if (!ff.stdin.write(jpg)) await new Promise((r) => ff.stdin.once('drain', r));
      if (i % 30 === 0) process.stderr.write(`\r${o.scene}: frame ${i}/${frames}  ${((Date.now() - t0) / (i + 1)).toFixed(0)} ms/frame`);
    }
    ff.stdin.end();
    await new Promise((r) => ff.on('close', r));
    console.log(`\n${out}`);
  }
  await browser.close();
  server.close();
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main().catch((e) => { console.error(e); process.exit(1); });
