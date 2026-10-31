/**
 * Wall-clock latency of find_software against a running Worker (`npm run dev`),
 * one request at a time. Paid when the Worker has MODEL_API_KEY: about $0.04
 * a request; the Worker logs each Meta call's tokens and cost (meta_call).
 *
 *   node bench/latency.ts <url> <requests.json>
 *
 * requests.json: [{ "label": "...", "target": "<slug or null>", "args": { find_software arguments } }]
 */
import { readFileSync } from 'node:fs';

const [url, requestsPath] = process.argv.slice(2);
const requests: { label: string; target: string | null; args: Record<string, unknown> }[] = JSON.parse(readFileSync(requestsPath, 'utf8'));

let id = 0;
for (const req of requests) {
  const started = Date.now();
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      'mcp-protocol-version': '2025-11-25',
      'x-pickfit-reporter': 'dev',
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method: 'tools/call', params: { name: 'find_software', arguments: req.args } }),
  });
  const text = await response.text();
  const ms = Date.now() - started;
  const line = text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6);
  const out = JSON.parse(line).result?.structuredContent;
  const picks: string[] = out?.picks?.map((p: { slug: string }) => p.slug) ?? [];
  console.log(
    JSON.stringify({
      label: req.label,
      ms,
      matched_by: out?.matched_by,
      degraded_reason: out?.degraded_reason,
      considered: out?.considered,
      picks,
      target_picked: req.target ? picks.includes(req.target) : null,
    }),
  );
}
