// Frames of the recording clips (rec/clips/<id>/00001.jpg …, 30 fps): a small cache of decoded
// images, keyed by URL. Frame i (1-based) shows clip time (i - 1) / 30.

const LIMIT = 20;
const cache = new Map(); // url -> { promise, img }

export function frameUrl(id, n) {
  return new URL(`../../rec/clips/${id}/${String(n).padStart(5, '0')}.jpg`, import.meta.url).href;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchImage(url) {
  // The clips may be rebuilt while we render: retry a few times before giving up.
  for (let attempt = 0; ; attempt++) {
    const img = new Image();
    img.decoding = 'async';
    img.src = url;
    try {
      await img.decode();
      return img;
    } catch (e) {
      if (attempt >= 5) { console.error(`frame failed to load: ${url}`); return null; }
      await wait(250 * (attempt + 1));
    }
  }
}

// Load (or reuse) a frame; resolves to the decoded HTMLImageElement (or null).
export function load(url) {
  let e = cache.get(url);
  if (e) {
    cache.delete(url);
    cache.set(url, e);
    return e.promise;
  }
  e = { img: null, promise: null };
  e.promise = fetchImage(url).then((img) => {
    if (!img) cache.delete(url);
    e.img = img;
    return img;
  });
  cache.set(url, e);
  while (cache.size > LIMIT) cache.delete(cache.keys().next().value);
  return e.promise;
}

// The decoded image if it is already in the cache, else null (for the real-time preview).
export function peek(url) {
  return cache.get(url)?.img || null;
}
