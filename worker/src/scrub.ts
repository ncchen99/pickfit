/**
 * Free text from agents (error excerpts, notes) is stored only after this
 * pass: home-directory user names, e-mail addresses and anything that looks
 * like a secret are replaced. The tool descriptions ask agents to do this
 * first; this is the server's own check, not a guarantee.
 */

const RULES: [RegExp, string][] = [
  // /Users/alice, /home/alice, C:\Users\alice
  [/(\/Users\/|\/home\/|\b[A-Za-z]:\\Users\\)[^/\\\s'"]+/g, '$1<user>'],
  [/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, '<email>'],
  // "Bearer x", and key=value / key: value for secret-sounding keys
  [/\b(bearer)\s+[^\s"',;)\]}]+/gi, '$1 <redacted>'],
  [/\b(token|api[_-]?key|apikey|password|passwd|secret|authorization)(["']?\s*[:=]\s*["']?)(?!bearer\b)[^\s"',;)\]}]+/gi, '$1$2<redacted>'],
  // Well-known token prefixes, then any long opaque run of characters
  [/\b(sk|pk|rk|ghp|gho|ghu|ghs|ghr|github_pat|xox[abpr]|AKIA|hf)[-_][A-Za-z0-9_-]{8,}/g, '<token>'],
  [/[A-Za-z0-9+/_-]{32,}={0,2}/g, '<token>'],
];

export function scrub(text: string): string {
  return RULES.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text);
}

/** Scrubbed, trimmed and cut to `max` characters (keeping the end, where errors say what failed). */
export function scrubTail(text: string | undefined, max: number): string | null {
  if (!text) return null;
  const clean = scrub(text).trim();
  if (!clean) return null;
  return clean.length > max ? clean.slice(clean.length - max) : clean;
}

/** Scrubbed, trimmed and cut to `max` characters from the start. */
export function scrubHead(text: string | undefined, max: number): string | null {
  if (!text) return null;
  const clean = scrub(text).trim();
  return clean ? clean.slice(0, max) : null;
}
