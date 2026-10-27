// Rough per-request cost of the per-request factory (no network): calls handler.fetch in-process.
// Purpose: compare against Cloudflare Workers Free plan's 10 ms CPU limit per request.
// Node wall time on a warm process is only a proxy for workerd CPU time.
import { handler } from './worker.mjs';

const meta = {
  'io.modelcontextprotocol/protocolVersion': '2026-07-28',
  'io.modelcontextprotocol/clientInfo': { name: 'bench', version: '0' },
  'io.modelcontextprotocol/clientCapabilities': {}
};
const args = { need: 'run an LLM offline on my laptop', os: 'macos', offline_required: true };
const cases = {
  'modern tools/list': () => req('tools/list', {}, null),
  'modern tools/call': () => req('tools/call', { name: 'find_software', arguments: args }, 'find_software'),
  'legacy tools/call': () =>
    new Request('http://127.0.0.1/mcp', {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'find_software', arguments: args } })
    })
};
function req(method, params, name) {
  const headers = {
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
    'mcp-protocol-version': '2026-07-28',
    'mcp-method': method
  };
  if (name) headers['mcp-name'] = name;
  return new Request('http://127.0.0.1/mcp', {
    method: 'POST',
    headers,
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params: { ...params, _meta: meta } })
  });
}

for (const [label, make] of Object.entries(cases)) {
  const first0 = performance.now();
  await (await handler.fetch(make())).text();
  const first = performance.now() - first0;
  const n = 300;
  const t0 = performance.now();
  for (let i = 0; i < n; i++) await (await handler.fetch(make())).text();
  const avg = (performance.now() - t0) / n;
  console.log(`${label.padEnd(18)} first=${first.toFixed(1)}ms  warm_avg=${avg.toFixed(2)}ms  (n=${n})`);
}
await handler.close();
