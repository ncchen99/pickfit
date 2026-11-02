/**
 * Verification clips: /video/<slug>/<file> serves only the files a record names (clip, raw recordings, the
 * clip's poster) from R2 with Range support, answers 404 without the VIDEOS binding, and the tool page and the
 * install guide point at the clip.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureIndex, makeD1 } from './helpers.ts';

const SLUG = 'fixture-chat-tui';
const CLIP = 'fixture-chat-tui-20261102-1220.mp4';
const RAW = 'fixture-chat-tui-20261102-1220-raw-1.mp4';
const VIDEO = {
  clip: CLIP,
  clip_sha256: 'a'.repeat(64),
  seconds: 20.25,
  recorded_at: '2026-11-02T04:20:45Z',
  features: ['chat with a local model'],
  raw: [{ file: RAW, sha256: 'b'.repeat(64), seconds: 33 }],
};

/** The fixture index with a clip on the chat TUI's Linux run (as index.py writes it). */
function index(): unknown {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = data.entries.find((e: any) => e.slug === SLUG);
  entry.install.linux.run.video = VIDEO;
  for (const run of entry.verification.passed_runs) if (run.id === entry.install.linux.run.id) run.video = VIDEO;
  return data;
}

/** An R2 bucket in memory, with get's range and onlyIf the way R2 reads them from request headers. */
function bucket(files: Record<string, Uint8Array>) {
  const calls: string[] = [];
  const meta = (key: string) => ({ key, size: files[key].length, httpEtag: `"etag-${key.length}"`, uploaded: new Date('2026-11-02T05:00:00Z') });
  const r2 = {
    async head(key: string) {
      calls.push(`head ${key}`);
      return files[key] ? meta(key) : null;
    },
    async get(key: string, opts: { range?: Headers; onlyIf?: Headers } = {}) {
      calls.push(`get ${key}`);
      if (!files[key]) return null;
      const m = meta(key);
      const inm = opts.onlyIf?.get('if-none-match');
      if (inm && inm === m.httpEtag) return m; // no body: the precondition did not hold
      const header = opts.range?.get('range');
      let start = 0;
      let end = m.size - 1;
      let range: any;
      if (header) {
        const r = /^bytes=(\d*)-(\d*)$/.exec(header);
        if (!r || (!r[1] && !r[2])) throw new Error('InvalidRange');
        if (r[1]) {
          start = Number(r[1]);
          end = r[2] ? Math.min(Number(r[2]), m.size - 1) : m.size - 1;
          if (start >= m.size) throw new Error('InvalidRange');
          range = { offset: start, length: end - start + 1 };
        } else {
          range = { suffix: Number(r[2]) };
          start = Math.max(0, m.size - Number(r[2]));
        }
      }
      const bytes = files[key].slice(start, end + 1);
      // The real bucket's object.range did not hold numeric offsets for a header range (the Worker sent NaN):
      // hand back the request headers, so Content-Range must come from the Range header itself.
      return { ...m, range: range ? opts.range : undefined, body: new Response(bytes).body };
    },
  };
  return { r2: r2 as unknown as R2Bucket, calls };
}

const BYTES = Uint8Array.from({ length: 100 }, (_, i) => i);
const FILES = { [`${SLUG}/${CLIP}`]: BYTES, [`${SLUG}/${RAW}`]: BYTES, [`${SLUG}/${CLIP.replace('.mp4', '.jpg')}`]: BYTES.slice(0, 10) };

function site(videos: R2Bucket | undefined, data: unknown = index()) {
  const worker = makeWorker(data as any, { now: () => new Date('2026-11-02T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const env = { DB: makeD1().db, ...(videos ? { VIDEOS: videos } : {}) } as Env;
  return (path: string, init: RequestInit = {}) => worker.fetch(new Request(`http://127.0.0.1:8787${path}`, init), env, ctx);
}

test('only the files a record names are served: its clip, the poster beside it and the raw recordings', async () => {
  const { r2, calls } = bucket(FILES);
  const get = site(r2);
  for (const file of [CLIP, RAW, CLIP.replace('.mp4', '.jpg')]) assert.equal((await get(`/video/${SLUG}/${file}`)).status, 200, file);
  const poster = await get(`/video/${SLUG}/${CLIP.replace('.mp4', '.jpg')}`);
  assert.equal(poster.headers.get('content-type'), 'image/jpeg');
  calls.length = 0;
  for (const path of [
    `/video/${SLUG}/other.mp4`,
    `/video/fixture-json-query/${CLIP}`,
    `/video/no-such-tool/${CLIP}`,
    `/video/${SLUG}/${CLIP.replace('.mp4', '.webm')}`,
    `/video/${SLUG}/%2e%2e%2f${CLIP}`,
    `/video/${SLUG}/`,
    `/video/${SLUG}/${CLIP}/x`,
  ]) {
    const res = await get(path);
    assert.equal(res.status, 404, path);
  }
  assert.deepEqual(calls, [], 'nothing outside the allowlist reaches the bucket');
  assert.equal((await get(`/video/${SLUG}/${CLIP}`, { method: 'POST' })).status, 405);
});

test('a whole clip streams with its type, length, ETag and an immutable cache line', async () => {
  const res = await site(bucket(FILES).r2)(`/video/${SLUG}/${CLIP}`);
  assert.equal(res.status, 200);
  assert.deepEqual(
    ['content-type', 'content-length', 'accept-ranges', 'etag', 'cache-control'].map((h) => res.headers.get(h)),
    ['video/mp4', '100', 'bytes', `"etag-${`${SLUG}/${CLIP}`.length}"`, 'public, max-age=31536000, immutable'],
  );
  assert.equal((await res.arrayBuffer()).byteLength, 100);
});

test('Range gets 206 with Content-Range; a suffix range too; past the end is 416; a matching ETag is 304', async () => {
  const get = site(bucket(FILES).r2);
  const part = await get(`/video/${SLUG}/${CLIP}`, { headers: { range: 'bytes=10-19' } });
  assert.equal(part.status, 206);
  assert.deepEqual([part.headers.get('content-range'), part.headers.get('content-length')], ['bytes 10-19/100', '10']);
  assert.deepEqual([...new Uint8Array(await part.arrayBuffer())], [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
  const open = await get(`/video/${SLUG}/${CLIP}`, { headers: { range: 'bytes=90-' } });
  assert.deepEqual([open.status, open.headers.get('content-range')], [206, 'bytes 90-99/100']);
  const tail = await get(`/video/${SLUG}/${CLIP}`, { headers: { range: 'bytes=-5' } });
  assert.deepEqual([tail.status, tail.headers.get('content-range'), (await tail.arrayBuffer()).byteLength], [206, 'bytes 95-99/100', 5]);
  const past = await get(`/video/${SLUG}/${CLIP}`, { headers: { range: 'bytes=500-' } });
  assert.deepEqual([past.status, past.headers.get('content-range')], [416, 'bytes */100']);
  const etag = (await get(`/video/${SLUG}/${CLIP}`)).headers.get('etag')!;
  const same = await get(`/video/${SLUG}/${CLIP}`, { headers: { 'if-none-match': etag } });
  assert.deepEqual([same.status, await same.text()], [304, '']);
  const head = await get(`/video/${SLUG}/${CLIP}`, { method: 'HEAD' });
  assert.deepEqual([head.status, head.headers.get('content-length'), await head.text()], [200, '100', '']);
});

test('without the VIDEOS binding, or with the file not uploaded yet, /video/ is 404 and nothing breaks', async () => {
  assert.equal((await site(undefined)(`/video/${SLUG}/${CLIP}`)).status, 404);
  assert.equal((await site(bucket({}).r2)(`/video/${SLUG}/${CLIP}`)).status, 404);
  assert.equal((await site(undefined)('/tool/fixture-json-query', { headers: { accept: 'text/html' } })).status, 200);
});

test('the tool page plays the clip first with its poster, and links the raw recordings with their sha256', async () => {
  const res = await site(undefined)(`/tool/${SLUG}`, { headers: { accept: 'text/html' } });
  const html = await res.text();
  assert.match(res.headers.get('content-security-policy') ?? '', /media-src 'self'/);
  assert.match(html, new RegExp(`<video controls preload="metadata" playsinline poster="/video/${SLUG}/${CLIP.replace('.mp4', '.jpg')}" aria-describedby="showcase-cap">`));
  assert.match(html, new RegExp(`<source src="/video/${SLUG}/${CLIP}" type="video/mp4">`));
  assert.match(html, /Fixture Chat TUI running, recorded by pickfit on 2 Nov 2026 · 20 s/);
  assert.ok(html.indexOf('<figure class="showcase">') < html.indexOf('id="progress-title"'), 'the clip comes before everything else');
  assert.match(html, new RegExp(`href="/video/${SLUG}/${RAW}" download>${RAW}</a>`));
  assert.ok(html.includes('b'.repeat(64)));
  // Other tools have no video element.
  const other = await (await site(undefined)('/tool/fixture-json-query', { headers: { accept: 'text/html' } })).text();
  assert.ok(!other.includes('<video'));
});

/** The index with chapters on the clip: an opening card, the feature, a closing card (as the video step writes them). */
function chaptered(): unknown {
  const data = index() as any;
  const entry = data.entries.find((e: any) => e.slug === SLUG);
  entry.usage_guide = {
    model: 'fixture-model', generated_at: '2026-11-02T12:00:00Z', run_id: entry.install.linux.run.id, open_hint: null,
    features: [{ feature: 'chat with a local model', title: 'Chat with a model on your machine', steps: [] }],
  };
  const chapters = [
    { start_s: 0, title: 'Recorded by pickfit', feature: null },
    { start_s: 3.5, title: 'chat with a local model', feature: 'chat with a local model' },
    { start_s: 17, title: 'Unedited recordings', feature: null },
  ];
  entry.features = ['chat with a local model'];
  entry.install.linux.features = [
    { feature: 'chat with a local model', status: 'checked', reason: null, failure: null, note: null, checks: [{ command: 'fixture-chat-tui --once hi', passed: true }] },
  ];
  entry.install.linux.run.video = { ...VIDEO, chapters };
  for (const run of entry.verification.passed_runs) if (run.id === entry.install.linux.run.id) run.video = { ...VIDEO, chapters };
  return data;
}

test('a clip with chapters gets a seek bar cut into them and a chapter list, named in plain words', async () => {
  const html = await (await site(undefined, chaptered())(`/tool/${SLUG}`, { headers: { accept: 'text/html' } })).text();
  assert.match(html, /<figure class="showcase" data-player>/);
  // The native player stays in the page for anyone without the script; the bar starts hidden.
  assert.match(html, /<video controls preload="metadata"/);
  assert.match(html, /<div class="player-bar" data-bar hidden>/);
  assert.match(html, /role="slider" tabindex="0" aria-label="Seek by chapter" aria-valuemin="0" aria-valuemax="20"/);
  const segs = [...html.matchAll(/<span class="chap-seg" data-start="([\d.]+)" data-end="([\d.]+)" data-title="([^"]+)">/g)].map((m) => m.slice(1));
  assert.deepEqual(segs, [
    ['0', '3.5', 'Recorded by pickfit'],
    ['3.5', '17', 'Chat with a model on your machine'],
    ['17', '20.25', 'Unedited recordings'],
  ]);
  assert.match(html, /<ol class="chapters" aria-label="Chapters"><li><button type="button" data-seek="0" aria-current="true"><span class="chap-time">0:00<\/span><span class="chap-title">Recorded by pickfit<\/span>/);
  assert.match(html, /data-seek="3.5"><span class="chap-time">0:03<\/span><span class="chap-title">Chat with a model on your machine<\/span>/);
  // The feature's "how to use it" jumps to its chapter.
  assert.match(html, /<button type="button" class="watch" data-seek="3.5">.*?Watch it at 0:03<\/button>/);
  // In Chinese the two cards use fixed words.
  const zh = await (await site(undefined, chaptered())(`/tool/${SLUG}?lang=zh-TW`, { headers: { accept: 'text/html' } })).text();
  assert.match(zh, /data-title="pickfit 錄製"/);
  assert.match(zh, /data-title="未剪輯的原始錄影"/);
});

test('a clip without chapters keeps the browser’s own player and no chapter list', async () => {
  const html = await (await site(undefined)(`/tool/${SLUG}`, { headers: { accept: 'text/html' } })).text();
  assert.match(html, /<figure class="showcase"><div class="player"><video controls/);
  assert.ok(!html.includes('<figure class="showcase" data-player>') && !html.includes('class="chapters"') && !html.includes('class="chap-seg"'));
});

async function guide(videos: R2Bucket | undefined) {
  const res = await site(videos)('/mcp', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_install_guide', arguments: { slug: SLUG, os: 'linux' } } }),
  });
  const text = await res.text();
  const body = JSON.parse(text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6));
  return body.result.structuredContent;
}

test('get_install_guide gives the clip\'s absolute URL and length where this deployment serves it', async () => {
  const served = await guide(bucket(FILES).r2);
  assert.deepEqual(served.verification.video, {
    url: `http://127.0.0.1:8787/video/${SLUG}/${CLIP}`,
    seconds: 20,
    shows: ['chat with a local model'],
    recorded_at: '2026-11-02T04:20:45Z',
  });
  assert.match(served.how_we_know, new RegExp(`A 20 s video recorded in that run shows pickfit using it \\(chat with a local model\\): http://127\\.0\\.0\\.1:8787/video/${SLUG}/${CLIP}`));
  const unserved = await guide(undefined);
  assert.equal(unserved.verification.video, null);
  assert.ok(!unserved.how_we_know.includes('/video/'));
});
