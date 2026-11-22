/**
 * GET/HEAD /video/<slug>/<file>: pickfit's verification clips, streamed from the R2 bucket pickfit-videos
 * (binding VIDEOS, key <slug>/<file>). Only files the slug's record names are served: each run's clip, the raw
 * recordings it was cut from, and the clip's poster (<clip stem>.jpg). Everything else, and every request when
 * the binding is missing, is 404. Range requests get 206; names carry a timestamp, so responses are immutable.
 *
 * The record's preview (brief 15.7: one still for a tool with no clip, tracks B and C) is served from the same bucket,
 * beside the clips: a plain file name (no folder) ending .jpg, .png or .webp, and only the one the record names.
 *
 * A clip with captions also has them as a WebVTT track per page language (<clip stem>.en.vtt, .zh-TW.vtt), made
 * here from the record (the zh-TW one from the page's translations of the same sentences), not from R2.
 */
import { OSES, type Catalog, type Entry, type RunSummary, type RunVideo, type VideoCaption } from './catalog.ts';
import { LANGS, type Lang, type Translations } from './i18n.ts';

const PATH = /^\/video\/([a-z0-9]+(?:-[a-z0-9]+)*)\/([A-Za-z0-9_][A-Za-z0-9_.-]{0,119}\.(mp4|jpg|png|webp|vtt))$/;
const TYPES: Record<string, string> = {
  mp4: 'video/mp4',
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  vtt: 'text/vtt; charset=utf-8',
};
/** A preview image this route can serve: a file name alone, of an image type the page shows in <img>. */
const PREVIEW_FILE = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,119}\.(jpg|png|webp)$/;
const IMMUTABLE = 'public, max-age=31536000, immutable';
const CAPTIONS_CACHE = 'public, max-age=3600'; // a caption's translation can change under the same name

export const posterOf = (clip: string) => clip.replace(/\.mp4$/, '.jpg');
export const videoPath = (slug: string, file: string) => `/video/${slug}/${encodeURIComponent(file)}`;
/** The clip's caption track in a page language, beside it. */
export const captionsOf = (clip: string, lang: Lang) => clip.replace(/\.mp4$/, `.${lang}.vtt`);

/** hh:mm:ss.mmm */
const cueTime = (s: number) => {
  const ms = Math.max(0, Math.round(s * 1000));
  const pad = (n: number, w = 2) => String(n).padStart(w, '0');
  return `${pad(Math.floor(ms / 3600000))}:${pad(Math.floor(ms / 60000) % 60)}:${pad(Math.floor(ms / 1000) % 60)}.${pad(ms % 1000, 3)}`;
};

/** A clip's captions as WebVTT, each cue's text from `map` when it has a translation; plain text, never markup. */
export function captionsVtt(captions: VideoCaption[], map?: Record<string, string>): string {
  const text = (t: string) => (map?.[t] ?? t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\s+/g, ' ').trim();
  const cues = captions
    .filter((c) => Number.isFinite(c.start_s) && Number.isFinite(c.end_s) && c.end_s > c.start_s && c.text)
    .map((c, i) => `${i + 1}\n${cueTime(c.start_s)} --> ${cueTime(c.end_s)}\n${text(c.text)}\n`);
  return `WEBVTT\n\n${cues.join('\n')}`;
}

/** The entry's preview image name when it is one /video/<slug>/ serves (PREVIEW_FILE), else null. */
export function previewImage(entry: Entry): string | null {
  const image = entry.preview?.image;
  return image && PREVIEW_FILE.test(image) ? image : null;
}

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
    if (video.captions?.length) for (const lang of LANGS) files.add(captionsOf(video.clip, lang));
  }
  const preview = previewImage(entry);
  if (preview) files.add(preview);
  return files;
}

/** The caption track a /video/ name asks for: its clip's captions and the language, or null. */
function captionsFor(entry: Entry, file: string): { captions: VideoCaption[]; lang: Lang } | null {
  for (const { video } of runsWithVideo(entry)) {
    const lang = LANGS.find((l) => captionsOf(video.clip, l) === file);
    if (lang && video.captions?.length) return { captions: video.captions, lang };
  }
  return null;
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
export async function serveVideo(
  request: Request,
  bucket: R2Bucket | undefined,
  catalog: Catalog,
  translations: Translations = {},
): Promise<Response | null> {
  const url = new URL(request.url);
  if (!url.pathname.startsWith('/video/')) return null;
  const match = PATH.exec(url.pathname);
  const entry = match ? catalog.bySlug.get(match[1]) : undefined;
  if (!match || !entry || !videoFiles(entry).has(match[2])) return notFound();
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method not allowed', { status: 405, headers: { allow: 'GET, HEAD' } });
  }
  if (match[3] === 'vtt') {
    const track = captionsFor(entry, match[2]);
    if (!track) return notFound();
    const body = captionsVtt(track.captions, track.lang === 'zh-TW' ? translations[entry.slug] : undefined);
    const headers = { 'content-type': TYPES.vtt, 'cache-control': CAPTIONS_CACHE, 'x-content-type-options': 'nosniff' };
    return new Response(request.method === 'HEAD' ? null : body, { status: 200, headers });
  }
  if (!bucket) return notFound();
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
