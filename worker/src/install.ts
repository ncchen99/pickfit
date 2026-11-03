/**
 * get_install_guide: only steps pickfit actually ran (replayed in a fresh
 * sandbox, or done by hand on a real machine). No model call. README claims
 * that were never run are not in the index, so they cannot leak out here.
 */
import { bestGuide, isWebApp, webCheck, type Arch, type Catalog, type Entry, type GuiEvidence, type OS } from './catalog.ts';
import { checkIn, webCheckIn, type CheckIn } from './checkin.ts';
import { ranSentence, videoOut, videoSentence } from './evidence.ts';
import { featureSentence, featuresOut, type FeaturesOut } from './features.ts';
import { newId, REC_ID } from './events.ts';
import { clientConfig, type McpClientConfig } from './mcpconfig.ts';
import { securityOut, securityWarnings, type SecurityOut } from './security.ts';
import { webAppOut, webRanSentence, webWarnings, type WebAppOut } from './webapp.ts';

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
    /** A GUI app's launch as pickfit saw it (level stays install); null for anything else. */
    gui: GuiEvidence | null;
    /** A clip pickfit recorded of this run: its URL, length and the checked features it shows; null when none. */
    video?: { url: string; seconds: number; shows: string[]; recorded_at: string } | null;
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
  /** Advertised features these steps' run exercised (with the check that did), and the ones it did not. */
  features: FeaturesOut;
  known_issues: { readme_said: string; actually_needed: string; kind: PitfallKind | null }[];
  /** MCP servers: how to add it to an MCP client, from the launch command the run started; null otherwise. */
  mcp_client_config: McpClientConfig | null;
  /** How to ask, weeks later and only with the user's consent, whether they still use it; null without a guide. */
  check_in: CheckIn | null;
  /** A hosted web app: the URL to open instead of steps, and what pickfit's browser saw; null for anything else. */
  web_app: WebAppOut | null;
  /** Known high or critical vulnerabilities (OSV.dev) in what a fresh install brings; unchecked says why not. */
  security: SecurityOut;
  warnings: string[];
  sources: string[];
}

export class UnknownSlugError extends Error {}

export const PIPE_TO_SHELL = /\|\s*(sudo\s+)?(ba|z)?sh\b/;

/** A web app's guide: open the URL. The checked facts and the date stand where steps would; nothing runs on the machine. */
function webGuide(entry: Entry, input: InstallInput, now: Date): InstallOutput {
  const check = webCheck(entry);
  const web = webAppOut(entry)!;
  const covered = featureSentence(featuresOut(entry, null));
  const security = securityOut(entry);
  return {
    rec_id: input.rec_id && REC_ID.test(input.rec_id) ? input.rec_id : newId('rec'),
    matched_by: 'rules',
    slug: entry.slug,
    name: entry.name,
    how_we_know: check
      ? `${webRanSentence(check)} Nothing to install: open ${web.url} in a browser.${covered ? ` ${covered}` : ''}`
      : `pickfit has not checked ${entry.name} in its browser yet.`,
    evidence_url: check?.evidence_url ?? null,
    verification: {
      status: check ? 'verified' : 'unverified',
      level: check?.level ?? null,
      os: null,
      arch: null,
      method: check ? 'sandbox' : null,
      replayed: false,
      runner: null,
      checked_at: check?.checked_at ?? null,
      tool_version: null,
      evidence_url: check?.evidence_url ?? null,
      works_offline: check?.offline === 'verified' ? true : check?.offline === 'not_offline' ? false : null,
      gui: null,
    },
    applies_to_user_system: check
      ? { match: 'exact', note: `A web app: it opens in a browser on any OS. pickfit checked it in a sandboxed browser (${check.browser}).` }
      : { match: 'none', note: `pickfit has not checked ${entry.name} in its browser yet. Do not present it as verified.` },
    steps: [],
    manual_steps: [{ title: `Open ${web.url} in a browser. Nothing to install.`, run_by: 'user' }],
    verify: null,
    first_task: null,
    first_task_setup: [],
    features: featuresOut(entry, null),
    known_issues: [],
    mcp_client_config: null,
    check_in: check ? webCheckIn(entry, web.url, now) : null,
    web_app: web,
    security,
    warnings: [...securityWarnings(security, true), ...webWarnings(check)],
    sources: entry.sources,
  };
}

export function installGuide(catalog: Catalog, input: InstallInput, now = new Date(), videoBase: string | null = null): InstallOutput {
  const entry = catalog.bySlug.get(input.slug);
  if (!entry) {
    throw new UnknownSlugError(`Unknown slug "${input.slug}". Call find_software first and use a slug it returned.`);
  }
  if (isWebApp(entry) && entry.web) return webGuide(entry, input, now);
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
  const features = featuresOut(entry, guide);
  const covered = featureSentence(features);
  const clip = guide ? videoSentence(entry.slug, guide.run.video, videoBase) : null;
  const howWeKnow = guide
    ? `${ranSentence(guide)} These are the recorded steps of that run; no model wrote or changed them.${covered ? ` ${covered}` : ''}${clip ? ` ${clip}` : ''}`
    : `pickfit has not run ${entry.name}'s install steps on any system yet.`;
  const security = securityOut(entry);
  // First, so the agent reads it before the steps.
  const warnings: string[] = securityWarnings(security);
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
      gui: run?.gui ?? null,
      video: videoOut(entry.slug, run?.video, videoBase),
    },
    applies_to_user_system: { match, note },
    steps,
    manual_steps: (guide?.manual_steps ?? []).map((title) => ({ title, run_by: 'user' as const })),
    verify: guide?.check ? { command: guide.check.command, expected_contains: guide.check.expected_signal } : null,
    first_task: guide?.first_task ?? null,
    first_task_setup: (guide?.first_task_setup ?? []).map((s) => ({ command: s.command, run_in_background: s.background })),
    features,
    // Field by field, so whatever else the index carries never reaches the response.
    known_issues: (guide?.pitfalls ?? []).map((p) => ({
      readme_said: p.readme_said,
      actually_needed: p.actually_needed,
      kind: PITFALL_KINDS.includes(p.kind as PitfallKind) ? (p.kind as PitfallKind) : null,
    })),
    mcp_client_config: clientConfig(entry, guide),
    check_in: guide ? checkIn(entry, guide, input.os, now) : null,
    web_app: null,
    security,
    warnings,
    sources: entry.sources,
  };
}
