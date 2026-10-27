// Drive the spike server with the official MCP TypeScript SDK v2 client,
// once per negotiation mode: legacy (SDK default = 2025 initialize handshake),
// auto (probe server/discover, fall back to initialize), and pin 2026-07-28.
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const url = new URL(process.env.MCP_URL ?? 'http://127.0.0.1:8787/mcp');
const modes = [
  ['legacy (default)', undefined],
  ['auto', { mode: 'auto' }],
  ['pin 2026-07-28', { mode: { pin: '2026-07-28' } }]
];

let failed = false;
for (const [label, versionNegotiation] of modes) {
  const client = new Client({ name: 'pickfit-spike-client', version: '0.0.1' }, versionNegotiation ? { versionNegotiation } : {});
  try {
    await client.connect(new StreamableHTTPClientTransport(url));
    const { tools } = await client.listTools();
    const t = tools.find(x => x.name === 'find_software');
    const res = await client.callTool({
      name: 'find_software',
      arguments: { need: 'run an LLM offline on my laptop', os: 'macos', offline_required: true }
    });
    const sc = res.structuredContent ?? {};
    console.log(
      JSON.stringify({
        mode: label,
        era: client.getProtocolEra(),
        server: client.getServerVersion(),
        tools: tools.map(x => x.name),
        annotations: t?.annotations,
        hasOutputSchema: Boolean(t?.outputSchema),
        isError: res.isError ?? false,
        picks: sc.picks?.map(p => p.slug),
        best_free_slug: sc.best_free_slug,
        server_saw_era: sc.era
      })
    );
  } catch (e) {
    failed = true;
    console.log(JSON.stringify({ mode: label, error: String(e) }));
  } finally {
    await client.close().catch(() => {});
  }
}
process.exit(failed ? 1 : 0);
