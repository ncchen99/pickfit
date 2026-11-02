/**
 * GET/HEAD /video/<slug>/<file>: pickfit's verification clips, streamed from the R2 bucket pickfit-videos
 * (binding VIDEOS, key <slug>/<file>). Only files the slug's record names are served: each run's clip, the raw
 * recordings it was cut from, and the clip's poster (<clip stem>.jpg). Everything else, and every request when
 * the binding is missing, is 404. Range requests get 206; names carry a timestamp, so responses are immutable.
 */
import { OSES, type Catalog, type Entry, type RunSummary, type RunVideo } from './catalog.ts';

const PATH = /^\/video\/([a-z0-9]+(?:-[a-z0-9]+)*)\/([A-Za-z0-9_][A-Za-z0-9_.-]{0,119}\.(mp4|jpg))$/;
const TYPES: Record<string, string> = { mp4: 'video/mp4', jpg: 'image/jpeg' };
const IMMUTABLE = 'public, max-age=31536000, immutable';

export const posterOf = (clip: string) => clip.replace(/\.mp4$/, '.jpg');
export const videoPath = (slug: string, file: string) => `/video/${slug}/${encodeURIComponent(file)}`;

/** Every run with a clip: the install guides' runs and the other passed runs, once each. */
export function runsWithVideo(entry: Entry): (RunSummary & { video: RunVideo })[] {
  const runs = [...OSES.flatMap((os) => (entry.install[os] ? [entry.install[os].run] : [])), ...entry.verification.passed_runs];
  const seen = new Set<string>();
  return runs.filter((r): r is RunSummary & { video: RunVideo } => !!r.video && !seen.has(r.id) && !!seen.add(r.id));
}

/** The files /video/<slug>/ may serve for this entry. */
export function videoFiles(entry: Entry): Set<string> {
  const files = new Set<string>();
  for (const { video } of runsWithVideo(entry)) {
    files.add(video.clip).add(posterOf(video.clip));
    for (const raw of video.raw) files.add(raw.file);
  }
  return files;
}

const notFound = () => new Response('Not found', { status: 404, headers: { 'cache-control': 'no-store' } });

/** The bytes a single-range Range header asks for, against the object's size (as R2 served them); null when it is not one. */
export function byteSpan(header: string | null, size: number): [number, number] | null {
  const m = /^bytes=(\d*)-(\d*)$/.exec((header ?? '').trim());
  if (!m || (!m[1] && !m[2])) return null;
  if (!m[1]) return [Math.max(0, size - Number(m[2])), size - 1];
  const start = Number(m[1]);
  return [start, m[2] ? Math.min(Number(m[2]), size - 1) : size - 1];
}

/** The bytes an R2 range covers, when the header could not say (R2 read it from the same header). */
function span(range: R2Range, size: number): [number, number] {
  if ('suffix' in range) return [Math.max(0, size - range.suffix), size - 1];
  const start = Number(range.offset ?? 0);
  const end = range.length !== undefined ? start + Number(range.length) : size;
  return [start, Math.min(size, end) - 1];
}

/** The response for a /video/ path, or null when the path is not one (the caller routes it elsewhere). */
export async function serveVideo(request: Request, bucket: R2Bucket | undefined, catalog: Catalog): Promise<Response | null> {
  const url = new URL(request.url);
  if (!url.pathname.startsWith('/video/')) return null;
  const match = PATH.exec(url.pathname);
  const entry = match ? catalog.bySlug.get(match[1]) : undefined;
  if (!match || !entry || !videoFiles(entry).has(match[2]) || !bucket) return notFound();
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method not allowed', { status: 405, headers: { allow: 'GET, HEAD' } });
  }
  const key = `${match[1]}/${match[2]}`;
  const headers = new Headers({
    'content-type': TYPES[match[3]],
    'accept-ranges': 'bytes',
    'cache-control': IMMUTABLE,
    'x-content-type-options': 'nosniff',
  });
  let object: R2Object | R2ObjectBody | null;
  try {
    object = request.method === 'HEAD' ? await bucket.head(key) : await bucket.get(key, { range: request.headers, onlyIf: request.headers });
  } catch {
    // A range R2 cannot serve (past the end, or several ranges): say what the whole is.
    const whole = await bucket.head(key);
    if (!whole) return notFound();
    return new Response(null, { status: 416, headers: { ...Object.fromEntries(headers), 'content-range': `bytes */${whole.size}` } });
  }
  if (!object) return notFound();
  headers.set('etag', object.httpEtag);
  headers.set('last-modified', object.uploaded.toUTCString());
  if (request.method === 'HEAD') {
    headers.set('content-length', String(object.size));
    return new Response(null, { status: 200, headers });
  }
  const body = 'body' in object ? (object as R2ObjectBody).body : null;
  if (!body) {
    // onlyIf did not hold: unchanged since the client's copy (304), or If-Match / If-Unmodified-Since failed (412).
    const notModified = request.headers.has('if-none-match') || request.headers.has('if-modified-since');
    return new Response(null, { status: notModified ? 304 : 412, headers });
  }
  if (object.range && request.headers.has('range')) {
    const [start, end] = byteSpan(request.headers.get('range'), object.size) ?? span(object.range, object.size);
    headers.set('content-range', `bytes ${start}-${end}/${object.size}`);
    headers.set('content-length', String(end - start + 1));
    return new Response(body, { status: 206, headers });
  }
  headers.set('content-length', String(object.size));
  return new Response(body, { status: 200, headers });
}
