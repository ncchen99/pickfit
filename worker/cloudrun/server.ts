/**
 * pickfit on Google Cloud Run: the same Worker (src/index.ts) behind a Node HTTP server.
 *
 * - Settings: wrangler.jsonc's top-level "vars", then the process environment over them.
 * - D1 (DB) through the Cloudflare REST API and R2 (VIDEOS) through its S3 API (bindings.ts),
 *   so the Python pipeline keeps using the same database and bucket.
 * - Static files from public/ with the rules in public/_headers, as Workers assets serves them.
 * - ctx.waitUntil: the promise runs on; the service is deployed with CPU always allocated.
 */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFileSync, statSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { Readable } from 'node:stream';
import { fileURLToPath } from 'node:url';
import worker from '../src/index.ts';
import { remoteD1, remoteR2 } from './bindings.ts';
import { parseJsonc } from './config.ts';

const root = fileURLToPath(new URL('..', import.meta.url).href);
const publicDir = join(root, 'public');

export { parseJsonc };

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is not set`);
  return value;
}

function buildEnv() {
  const config = parseJsonc(readFileSync(join(root, 'wrangler.jsonc'), 'utf8')) as {
    vars?: Record<string, string>;
    d1_databases?: { database_id: string }[];
    r2_buckets?: { bucket_name: string }[];
  };
  const env: Record<string, unknown> = { ...config.vars };
  for (const key of Object.keys(env)) if (process.env[key] !== undefined) env[key] = process.env[key];
  if (process.env.ANTHROPIC_API_KEY) env.ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
  const accountId = required('CLOUDFLARE_ACCOUNT_ID');
  const token = required('CLOUDFLARE_API_TOKEN');
  env.DB = remoteD1({ accountId, databaseId: process.env.D1_DATABASE_ID ?? config.d1_databases![0].database_id, token });
  if (process.env.R2_ACCESS_KEY_ID && process.env.R2_SECRET_ACCESS_KEY) {
    env.VIDEOS = remoteR2({
      accountId,
      bucket: process.env.R2_BUCKET ?? config.r2_buckets![0].bucket_name,
      accessKeyId: process.env.R2_ACCESS_KEY_ID,
      secretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
    });
  }
  return env;
}

const TYPES: Record<string, string> = {
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.xml': 'application/xml',
  '.webmanifest': 'application/manifest+json',
};

/** public/_headers: "/path/*" lines, each followed by indented "Name: value" lines. */
export function parseHeaders(text: string): { pattern: RegExp; headers: [string, string][] }[] {
  const rules: { pattern: RegExp; headers: [string, string][] }[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    if (!/^\s/.test(line)) {
      const glob = line.trim().replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
      rules.push({ pattern: new RegExp(`^${glob}$`), headers: [] });
    } else if (rules.length) {
      const at = line.indexOf(':');
      if (at > 0) rules[rules.length - 1].headers.push([line.slice(0, at).trim(), line.slice(at + 1).trim()]);
    }
  }
  return rules;
}

let headerRules: ReturnType<typeof parseHeaders> = [];
try {
  headerRules = parseHeaders(readFileSync(join(publicDir, '_headers'), 'utf8'));
} catch {
  /* no _headers */
}

async function staticFile(request: Request): Promise<Response | null> {
  if (request.method !== 'GET' && request.method !== 'HEAD') return null;
  let pathname: string;
  try {
    pathname = decodeURIComponent(new URL(request.url).pathname);
  } catch {
    return null;
  }
  if (pathname === '/' || pathname.endsWith('/_headers') || pathname.includes('\0')) return null;
  const file = normalize(join(publicDir, pathname));
  if (!file.startsWith(publicDir + sep)) return null;
  let size: number;
  try {
    const info = statSync(file);
    if (!info.isFile()) return null;
    size = info.size;
  } catch {
    return null;
  }
  const headers = new Headers({
    'content-type': TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream',
    'content-length': String(size),
  });
  for (const rule of headerRules) if (rule.pattern.test(pathname)) for (const [k, v] of rule.headers) headers.set(k, v);
  if (request.method === 'HEAD') return new Response(null, { status: 200, headers });
  return new Response(await readFile(file), { status: 200, headers });
}

/** The client's address: the last X-Forwarded-For entry, which Google's front end appends. */
function clientIp(req: IncomingMessage): string {
  const forwarded = String(req.headers['x-forwarded-for'] ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return forwarded.at(-1) ?? req.socket.remoteAddress ?? 'unknown';
}

function toRequest(req: IncomingMessage): Request {
  const proto = String(req.headers['x-forwarded-proto'] ?? 'http').split(',')[0].trim();
  const url = `${proto}://${req.headers.host ?? 'localhost'}${req.url ?? '/'}`;
  const headers = new Headers();
  for (const [name, value] of Object.entries(req.headers)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) for (const v of value) headers.append(name, v);
    else headers.set(name, value);
  }
  // src/web.ts keys its rate limit on the Cloudflare header; a client cannot set it here.
  headers.set('cf-connecting-ip', clientIp(req));
  const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
  return new Request(url, {
    method: req.method,
    headers,
    body: hasBody ? (Readable.toWeb(req) as unknown as ReadableStream) : undefined,
    // @ts-expect-error Node's fetch needs duplex for a streamed body.
    duplex: hasBody ? 'half' : undefined,
  });
}

async function send(res: ServerResponse, response: Response): Promise<void> {
  const headers: Record<string, string | string[]> = {};
  response.headers.forEach((value, name) => {
    if (name !== 'set-cookie') headers[name] = value;
  });
  const cookies = response.headers.getSetCookie();
  if (cookies.length) headers['set-cookie'] = cookies;
  res.writeHead(response.status, headers);
  if (!response.body) {
    res.end();
    return;
  }
  const body = Readable.fromWeb(response.body as unknown as import('node:stream/web').ReadableStream);
  await new Promise<void>((resolve) => {
    body.on('error', () => res.destroy());
    res.on('close', () => {
      body.destroy();
      resolve();
    });
    body.pipe(res);
  });
}

export function startServer(port = Number(process.env.PORT ?? 8080)) {
  const env = buildEnv();
  const pending = new Set<Promise<unknown>>();
  const ctx = {
    waitUntil(promise: Promise<unknown>) {
      const tracked = promise.catch((err) => console.error(JSON.stringify({ event: 'wait_until_failed', error: String(err) })));
      pending.add(tracked);
      tracked.finally(() => pending.delete(tracked));
    },
    passThroughOnException() {},
    props: {},
  };
  const server = createServer(async (req, res) => {
    try {
      const request = toRequest(req);
      const response = (await staticFile(request)) ?? (await worker.fetch!(request as never, env as never, ctx as never));
      await send(res, response as unknown as Response);
    } catch (err) {
      console.error(JSON.stringify({ event: 'request_failed', error: String(err), stack: (err as Error)?.stack }));
      if (!res.headersSent) res.writeHead(500, { 'content-type': 'text/plain' });
      res.end('Internal error');
    }
  });
  server.listen(port, () => console.log(JSON.stringify({ event: 'listening', port })));
  // Cloud Run sends SIGTERM before it stops an instance: finish the background writes first.
  process.on('SIGTERM', () => {
    server.close();
    void Promise.allSettled([...pending]).then(() => process.exit(0));
  });
  return server;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) startServer();
