/**
 * get_install_guide: only steps pickfit actually ran (replayed in a fresh
 * sandbox, or done by hand on a real machine). No model call. README claims
 * that were never run are not in the index, so they cannot leak out here.
 */
import { bestGuide, type Arch, type Catalog, type OS } from './catalog.ts';
import { ranSentence } from './evidence.ts';
import { newId, REC_ID } from './events.ts';
import { clientConfig, type McpClientConfig } from './mcpconfig.ts';

export interface InstallInput {
  slug: string;
  os: OS;
  arch?: Arch;
  rec_id?: string;
}

/** readme_wrong: following the README hits it; sandbox: only the sandbox needed it; tool_handled: the tool did it itself; note: nothing to fix. */
export const PITFALL_KINDS = ['readme_wrong', 'sandbox', 'tool_handled', 'note'] as const;
export type PitfallKind = (typeof PITFALL_KINDS)[number];

export interface InstallOutput {
  rec_id: string;
  matched_by: 'rules';
  slug: string;
  name: string;
  how_we_know: string;
  evidence_url: string | null;
  verification: {
    status: 'verified' | 'unverified';
    level: string | null;
    os: OS | null;
    arch: Arch | null;
    method: 'sandbox' | 'human' | null;
    replayed: boolean;
    runner: string | null;
    checked_at: string | null;
    tool_version: string | null;
    evidence_url: string | null;
    /** true: its checks passed again with the network off after install; false: they needed it. */
    works_offline: boolean | null;
  };
  applies_to_user_system: {
    match: 'exact' | 'same_os_other_arch' | 'other_os' | 'none';
    note: string | null;
  };
  steps: {
    order: number;
    command: string;
    purpose: string | null;
    run_by: 'agent';
    needs_sudo: boolean;
  }[];
  manual_steps: { title: string; run_by: 'user' }[];
  verify: { command: string; expected_contains: string } | null;
  first_task: string | null;
  first_task_setup: { command: string; run_in_background: boolean }[];
  known_issues: { readme_said: string; actually_needed: string; kind: PitfallKind | null }[];
  /** MCP servers: how to add it to an MCP client, from the launch command the run started; null otherwise. */
  mcp_client_config: McpClientConfig | null;
  warnings: string[];
  sources: string[];
}

export class UnknownSlugError extends Error {}

const PIPE_TO_SHELL = /\|\s*(sudo\s+)?(ba|z)?sh\b/;

export function installGuide(catalog: Catalog, input: InstallInput): InstallOutput {
  const entry = catalog.bySlug.get(input.slug);
  if (!entry) {
    throw new UnknownSlugError(`Unknown slug "${input.slug}". Call find_software first and use a slug it returned.`);
  }
  const guide = bestGuide(entry, input.os);
  const run = guide?.run ?? null;
  let match: InstallOutput['applies_to_user_system']['match'] = 'none';
  let note: string | null = null;
  if (!run) {
    note = `pickfit has not run ${entry.name}'s install steps on any system yet, so it gives no steps. Do not guess them.`;
  } else if (run.os !== input.os) {
    match = 'other_os';
    note = `pickfit has not run ${entry.name}'s install steps on ${input.os}; these steps were checked on ${run.os}. Tell the user before running them, and expect differences.`;
  } else if (input.arch && run.arch !== input.arch) {
    match = 'same_os_other_arch';
    note = `Checked on ${run.os}/${run.arch}, not ${input.arch}.`;
  } else {
    match = 'exact';
    // No arch given: exact for the OS only, so say which CPU the run was on.
    if (!input.arch) note = `Checked on ${run.os}/${run.arch}; the request did not say this machine's CPU architecture.`;
  }
  const steps = (guide?.steps ?? []).map((step, i) => ({
    order: i + 1,
    command: step.command,
    purpose: step.purpose,
    run_by: 'agent' as const,
    needs_sudo: /(^|[\s;&|])sudo\s/.test(step.command),
  }));
  const howWeKnow = guide
    ? `${ranSentence(guide)} These are the recorded steps of that run; no model wrote or changed them.`
    : `pickfit has not run ${entry.name}'s install steps on any system yet.`;
  const warnings: string[] = [];
  if (steps.some((s) => PIPE_TO_SHELL.test(s.command))) {
    warnings.push('A step pipes a downloaded script into a shell. Show it to the user and get consent before running it.');
  }
  if (steps.some((s) => s.needs_sudo)) {
    warnings.push('A step uses sudo. Ask the user before running it.');
  }
  return {
    // A rec_id from find_* is kept; otherwise this guide issues one, so report_outcome can cite it.
    rec_id: input.rec_id && REC_ID.test(input.rec_id) ? input.rec_id : newId('rec'),
    matched_by: 'rules',
    slug: entry.slug,
    name: entry.name,
    how_we_know: howWeKnow,
    evidence_url: run?.evidence_url ?? null,
    verification: {
      status: run ? 'verified' : 'unverified',
      level: run?.level ?? null,
      os: run?.os ?? null,
      arch: run?.arch ?? null,
      method: run?.method ?? null,
      replayed: run?.replayed ?? false,
      runner: run?.runner ?? null,
      checked_at: run?.checked_at ?? null,
      tool_version: run?.tool_version ?? null,
      evidence_url: run?.evidence_url ?? null,
      works_offline: guide?.works_offline ?? null,
    },
    applies_to_user_system: { match, note },
    steps,
    manual_steps: (guide?.manual_steps ?? []).map((title) => ({ title, run_by: 'user' as const })),
    verify: guide?.check ? { command: guide.check.command, expected_contains: guide.check.expected_signal } : null,
    first_task: guide?.first_task ?? null,
    first_task_setup: (guide?.first_task_setup ?? []).map((s) => ({ command: s.command, run_in_background: s.background })),
    // Field by field, so whatever else the index carries never reaches the response.
    known_issues: (guide?.pitfalls ?? []).map((p) => ({
      readme_said: p.readme_said,
      actually_needed: p.actually_needed,
      kind: PITFALL_KINDS.includes(p.kind as PitfallKind) ? (p.kind as PitfallKind) : null,
    })),
    mcp_client_config: clientConfig(entry, guide),
    warnings,
    sources: entry.sources,
  };
}
