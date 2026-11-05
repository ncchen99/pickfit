// The status page in each state a submission goes through, for the finale: the Worker's own renderer in-process with a
// throwaway SQLite D1, so the pages are the site's real markup and CSS. Each page is shot with the tape empty, and the tape
// once on its own, so the scene can run it. The 12 min at the end is charmbracelet/glow's real run on pickfit.app (11/5); the earlier stamps are rough.
//
// From worker/: node --experimental-strip-types ../video/capture/submit-states.mts ../video/scenes/finale
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { extname, join, resolve } from 'node:path';
import { createRequire } from 'node:module';

const worker = resolve('.');
const { makeWorker } = await import(join(worker, 'src/worker.ts'));
const { fixtureIndex, makeD1 } = await import(join(worker, 'test/helpers.ts'));
const require = createRequire(join(worker, '../video/package.json'));
const { chromium } = require('playwright');

const out = process.argv[2];
const d1 = makeD1();
const app = makeWorker(fixtureIndex(), { now: () => new Date() });
const ctx = { waitUntil() {}, passThroughOnException() {} };
const TYPES: Record<string, string> = { '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.js': 'text/javascript', '.css': 'text/css' };

const server = createServer(async (req, res) => {
  const url = `http://127.0.0.1:${(server.address() as any).port}${req.url}`;
  const path = req.url!.split('?')[0];
  if (path.startsWith('/assets/')) {
    try {
      const body = await readFile(join(worker, 'public', path));
      res.writeHead(200, { 'content-type': TYPES[extname(path)] ?? 'application/octet-stream' });
      res.end(body);
    } catch { res.writeHead(404).end(); }
    return;
  }
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers.set(k, v);
  const response = await app.fetch(
    new Request(url, { method: req.method, headers, body: chunks.length ? Buffer.concat(chunks) : undefined }),
    { DB: d1.db, MODEL_API_KEY: 'x' } as any,
    ctx as any,
  );
  const h: Record<string, string> = {};
  response.headers.forEach((v: string, k: string) => { h[k] = v; });
  res.writeHead(response.status, h);
  res.end(Buffer.from(await response.arrayBuffer()));
});
await new Promise<void>((ok) => server.listen(0, '127.0.0.1', () => ok()));
const base = `http://127.0.0.1:${(server.address() as any).port}`;

const browser = await chromium.launch({ channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, locale: 'en-US', colorScheme: 'light', bypassCSP: true });
const page = await context.newPage();
await page.goto(`${base}/submit`);
await page.fill('#sub-url', 'github.com/charmbracelet/glow');
await page.click('#submit-form button');
await page.waitForURL(/\/submit\/sub_/);
const statusUrl = page.url();

const STATES: { name: string; status: string; reason: string | null; ago: number }[] = [
  { name: 'queued', status: 'queued', reason: null, ago: 0 },
  { name: 'reading', status: 'reading', reason: null, ago: 1 },
  { name: 'trying', status: 'verifying', reason: null, ago: 2 },
  { name: 'passed', status: 'verifying', reason: 'passed', ago: 11 },
  { name: 'listed', status: 'listed', reason: null, ago: 12 },
];
const EMPTY = '.unroll::after{animation:none!important;clip-path:inset(0 100% 0 0)!important}';
const FULL = '.unroll::after{animation:none!important;clip-path:inset(0 0 0 0)!important}';
const tape: Record<string, { x: number; y: number; w: number; h: number }> = {};

for (const s of STATES) {
  d1.sqlite
    .prepare('UPDATE submissions SET status = ?, reason = ?, submitted_at = ?')
    .run(s.status, s.reason, new Date(Date.now() - s.ago * 60_000).toISOString());
  await page.goto(statusUrl);
  await page.waitForLoadState('networkidle');
  await page.addStyleTag({ content: EMPTY });
  if (s.name === 'listed') {
    // The live page has glow's own page to link to; the fixture catalog here does not have glow.
    await page.evaluate(() => {
      const go = document.querySelector('.sub-go');
      if (go) go.insertAdjacentHTML('afterbegin', '<a class="btn btn-primary" href="#">See its page</a>');
    });
  }
  await page.screenshot({ path: join(out, `submit-${s.name}.png`) });
  const box = await page.locator('.unroll').first().boundingBox().catch(() => null);
  if (box && (await page.locator('.unroll').count())) {
    tape[s.name] = box;
    if (s.name === 'trying') {
      await page.addStyleTag({ content: FULL });
      await page.screenshot({ path: join(out, 'submit-tape.png'), clip: box });
    }
  }
}
await writeFile(join(out, 'submit-tape.json'), JSON.stringify(tape, null, 1) + '\n');
console.log(tape);
await browser.close();
server.close();
