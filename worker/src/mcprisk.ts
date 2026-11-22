/**
 * An MCP server's safety facts as an agent reads them before connecting it (brief 15.7, gap audit 4.1 item 4): what
 * pickfit's probe matched in its tool list, what its tools say about themselves, and where the sandbox saw it connect.
 * All from entry.mcp_safety (pickfit/index.py _mcp_safety); nothing is inferred here.
 */
import type { Entry, McpSafety } from './catalog.ts';

/** Hosts named in an answer; the count covers the rest. */
export const EGRESS_SHOWN = 5;
/** Hosts a card carries for the matcher. */
export const CARD_EGRESS_SHOWN = 10;

export interface McpRisk {
  /** true: the tool list or server instructions carry instruction-like text aimed at the agent; null: not checked. */
  prompt_injection: boolean | null;
  /** The probe's pattern codes (pickfit/verify/mcp.py FLAG_TEXT); empty when none matched or not checked. */
  injection_patterns: string[];
  tool_count: number;
  /** Tools that declare destructiveHint / openWorldHint / readOnlyHint (the server's own claims); null: not counted. */
  destructive_tools: number | null;
  open_world_tools: number | null;
  read_only_tools: number | null;
  /** Public hosts the sandbox saw it reach while it ran; null: not logged. */
  egress_hosts: number | null;
  /** Up to EGRESS_SHOWN of them. */
  egress_examples: string[];
  /** One line to tell the user before they add it to a client; null when there is nothing to say. */
  warning: string | null;
}

const PATTERN_TEXT: Record<string, string> = {
  instruction_tag: 'a hidden <IMPORTANT>-style tag',
  override: 'text telling the model to ignore its instructions',
  conceal_from_user: 'text telling the model to keep something from the user',
  side_channel: 'a request to pass data along as a side note',
  sensitive_files: 'a request to read or send credential files',
  other_tools: 'text about how to use other tools',
  hidden_unicode: 'invisible Unicode characters',
};

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;

function warningLine(safety: McpSafety): string | null {
  const parts: string[] = [];
  const flags = safety.description_flags ?? [];
  if (flags.length) {
    parts.push(`its tool list carries instruction-like text aimed at the agent (${flags.map((f) => PATTERN_TEXT[f] ?? f).join(', ')})`);
  }
  const notes = safety.tool_annotations;
  if (notes?.destructive) parts.push(`${notes.destructive} of ${plural(safety.tool_count, 'tool')} say they can delete or overwrite things`);
  const hosts = safety.egress_hosts ?? [];
  if (hosts.length) {
    const shown = hosts.slice(0, EGRESS_SHOWN).join(', ');
    parts.push(`in pickfit's sandbox it connected to ${plural(hosts.length, 'outside host')} (${shown}${hosts.length > EGRESS_SHOWN ? ', …' : ''})`);
  }
  if (!parts.length) return null;
  const line = parts.join('; ');
  return `Before adding it to a client: ${line}.`;
}

/** The pick's mcp_risk; null when the entry's run recorded none of the facts (other software, older runs). */
export function mcpRisk(entry: Entry): McpRisk | null {
  const safety = entry.mcp_safety;
  if (!safety) return null;
  const notes = safety.tool_annotations;
  const flags = safety.description_flags;
  return {
    prompt_injection: flags ? flags.length > 0 : null,
    injection_patterns: flags ?? [],
    tool_count: safety.tool_count,
    destructive_tools: notes ? notes.destructive : null,
    open_world_tools: notes ? notes.open_world : null,
    read_only_tools: notes ? notes.read_only : null,
    egress_hosts: safety.egress_hosts ? safety.egress_hosts.length : null,
    egress_examples: (safety.egress_hosts ?? []).slice(0, EGRESS_SHOWN),
    warning: warningLine(safety),
  };
}
