/** how_we_know text, built by code from the verification record (never by the model). */
import type { InstallGuide } from './catalog.ts';

const LEVEL_TEXT: Record<string, string> = {
  install: 'the install finished and the tool started',
  function: 'a smoke test of its main function passed',
  service: 'its service answered a test request',
  inference: 'it produced model output in a test run',
};

/** An MCP server's checks: its handshake, and a tool call when one ran. */
function mcpText(guide: InstallGuide): string | null {
  const m = guide.mcp;
  if (!m) return null;
  const listed = `an MCP client handshake over ${m.transport} listed its ${m.tool_count} tool${m.tool_count === 1 ? '' : 's'}`;
  const offline = m.offline ? ' with the network off' : '';
  return m.called_tool ? `${listed}${offline}, and a call to ${m.called_tool} returned a result` : `${listed}${offline}`;
}

/** "pickfit installed it in a fresh linux/x86_64 sandbox (...) on 2026-10-28; a smoke test ... passed." */
export function ranSentence(guide: InstallGuide): string {
  const r = guide.run;
  const runner = r.runner ? ` (${r.runner})` : '';
  const where =
    r.method === 'sandbox'
      ? `installed it in a fresh ${r.os}/${r.arch} sandbox${runner} and replayed the steps from scratch`
      : `installed it by hand on ${r.os}/${r.arch}${runner}`;
  return `pickfit ${where} on ${r.checked_at.slice(0, 10)}; ${mcpText(guide) ?? LEVEL_TEXT[r.level] ?? r.level}.`;
}
