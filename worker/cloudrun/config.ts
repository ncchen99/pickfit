/**
 * wrangler.jsonc, read the way Cloud Run uses it. wrangler.jsonc is the one place the settings live:
 * server.ts reads its top-level "vars", and deploy.sh asks this file for the ALLOWED_HOSTS to deploy with.
 *
 *   node cloudrun/config.ts allowed-hosts <run.app host>
 *
 * prints the top-level ALLOWED_HOSTS with the Cloud Run service's own host name added.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/** wrangler.jsonc without its comments and trailing commas. */
export function parseJsonc(text: string): unknown {
  let out = '';
  let inString = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inString) {
      out += c;
      if (c === '\\') out += text[++i];
      else if (c === '"') inString = false;
    } else if (c === '"') {
      inString = true;
      out += c;
    } else if (c === '/' && text[i + 1] === '/') {
      while (i < text.length && text[i] !== '\n') i++;
      out += '\n';
    } else if (c === '/' && text[i + 1] === '*') {
      i = text.indexOf('*/', i + 2) + 1;
    } else out += c;
  }
  return JSON.parse(out.replace(/,(\s*[}\]])/g, '$1'));
}

/** The top-level ALLOWED_HOSTS of wrangler.jsonc plus the extra hosts (the run.app name), without repeats. */
export function cloudRunAllowedHosts(wranglerText: string, ...extra: string[]): string {
  const config = parseJsonc(wranglerText) as { vars?: Record<string, string> };
  const hosts = [...(config.vars?.ALLOWED_HOSTS ?? '').split(','), ...extra]
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  if (!hosts.length) throw new Error('wrangler.jsonc has no top-level ALLOWED_HOSTS');
  return [...new Set(hosts)].join(',');
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [command, ...extra] = process.argv.slice(2);
  if (command !== 'allowed-hosts') {
    console.error('usage: node cloudrun/config.ts allowed-hosts [extra host ...]');
    process.exit(2);
  }
  const root = fileURLToPath(new URL('..', import.meta.url).href);
  console.log(cloudRunAllowedHosts(readFileSync(join(root, 'wrangler.jsonc'), 'utf8'), ...extra));
}
