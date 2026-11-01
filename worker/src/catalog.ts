/** The index written by scripts/build_index.py ("pickfit-index.v1"). */

export type OS = 'macos' | 'linux' | 'windows';
export type Arch = 'arm64' | 'x86_64';
export type Need = 'required' | 'optional' | 'none';
export const OSES: readonly OS[] = ['macos', 'linux', 'windows'];

export interface RunSummary {
  id: string;
  level: 'inference' | 'service' | 'function' | 'install';
  os: OS;
  arch: Arch;
  method: 'sandbox' | 'human';
  runner: string | null;
  replayed: boolean;
  checked_at: string;
  tool_version: string | null;
  evidence_url: string | null;
  /** A GUI app's launch on pickfit's virtual display; absent or null for anything else. */
  gui?: GuiEvidence | null;
  /** The sandbox's GPU as its driver named it (e.g. Tesla T4); absent or null: no GPU. */
  gpu?: string | null;
  /** The sandbox's simulated microphone (it played words pickfit spoke for each check); absent or null: none. */
  microphone?: string | null;
}

/**
 * What pickfit saw when a GUI app launched on a virtual display (verification.runs[].gui). The window
 * title is the app's own text and is not in the index. A launch supports level install; an operation
 * pickfit checked (tier action_checked) supports function.
 */
export interface GuiEvidence {
  /**
   * window: a window of the app's own process (per the X server); ui_rendered: the screen judge saw the app's own UI;
   * action_checked: also, Muse Spark Open operated it from screenshots and pickfit's own check of the result passed.
   */
  tier: 'window' | 'ui_rendered' | 'action_checked';
  /** What a separate model saw in a screenshot of the app's own windows. */
  screen: 'main_ui' | 'first_run' | 'sign_in_wall' | 'crash_or_error' | 'blank_or_loading' | 'other';
  display: string;
  /** The launch passed again with the network off in the fresh-sandbox replay. */
  launch_offline: boolean | null;
  /** Goals pickfit operated the app toward in the fresh-sandbox replay; absent when none ran. */
  operations?: GuiOperation[];
}

/** One goal pickfit operated a GUI app toward (gui_operate.py), and what its own check found. */
export interface GuiOperation {
  feature: string | null;
  /** file: a file the app wrote, read by root; clipboard: read by pickfit's display user; screen_text: read off pickfit's screenshot. */
  check: 'file' | 'clipboard' | 'screen_text';
  passed: boolean;
  /** actions: the recorded clicks and keys passed again; operated: the operator reached the goal again. */
  replay: 'actions' | 'operated';
  goal: string;
  /** pickfit's own line about what the check found. */
  observed: string;
}

/** One advertised feature as the run behind a guide covered it (index.py _feature_coverage). */
export interface FeatureCoverage {
  feature: string;
  status: 'checked' | 'not_checked' | 'test_failed';
  reason: string | null;
  failure: 'sandbox' | 'tool' | null;
  note: string | null;
  /** The run's smoke tests behind it; a feature counts as checked only when one passed. */
  checks: { command: string; passed: boolean }[];
}

/** What a fresh sandbox saw when pickfit's MCP probe started the server (verification.runs[].mcp). */
export interface McpHandshake {
  transport: 'stdio' | 'streamable_http' | 'sse';
  /** argv that started the server, as the replay ran it. */
  launch: string[];
  /** streamable_http: the local URL the probe posted to. */
  url?: string | null;
  protocol_version: string | null;
  server_name: string | null;
  server_version: string | null;
  /** Tool names from tools/list, reduced to safe characters by the probe. */
  tools: string[];
  tool_count: number;
  /** A tool tools/call ran without an error (level service). */
  called_tool: string | null;
  offline: boolean | null;
}

/** The README's MCP facts (record.mcp): claims, not run. */
export interface McpFacts {
  transports: string[];
  launch_command: string | null;
  client_configs: { client: string; snippet: string }[];
  env_vars: { name: string; required: boolean | null; purpose: string | null }[];
  tools: string[];
}

export interface InstallGuide {
  basis: 'replayed' | 'human';
  method: string;
  steps: { command: string; purpose: string | null }[];
  manual_steps: string[];
  check: { command: string; expected_signal: string } | null;
  first_task: string | null;
  /** Commands the first task needs first (an input file, a server), from the same run. */
  first_task_setup: { command: string; background: boolean }[];
  /** true: every passing check also passed with the network off; null: not checked offline. */
  works_offline: boolean | null;
  /** kind arrives with the P3 pitfall tags; older runs have none. */
  pitfalls: { readme_said: string; actually_needed: string; kind?: string | null }[];
  /** Empty for runs from before features were checked; older indexes lack it. */
  features?: FeatureCoverage[];
  run: RunSummary;
  /** MCP servers: the handshake of this run; null or absent for other software. */
  mcp?: McpHandshake | null;
}

export interface Entry {
  slug: string;
  name: string;
  summary: string;
  why_worth_it: string | null;
  category: 'dev_cli' | 'local_ai' | 'mcp_server' | 'other';
  kind: string;
  maturity: string | null;
  tags: string[];
  use_cases: string[];
  alternatives_to: string[];
  /** The main features the README advertises; older indexes lack it. */
  features?: string[];
  homepage: string | null;
  repo_url: string;
  platforms: OS[];
  prerequisites: {
    runtimes: string[];
    system_packages: string[];
    gpu: Need | null;
    apple_silicon_only: boolean | null;
    min_ram_gb: number | null;
    network: Need | null;
    api_keys: string[];
  };
  pricing: 'free' | 'freemium' | 'paid' | null;
  pricing_note: string | null;
  open_source: boolean | null;
  license: string | null;
  processing: 'local' | 'cloud' | 'hybrid' | null;
  last_release: string | null;
  verification: {
    level: string;
    checked_at: string | null;
    passed_runs: RunSummary[];
  };
  install: Partial<Record<OS, InstallGuide>>;
  /** MCP servers only: what the README says about using it from an MCP client. */
  mcp?: McpFacts | null;
  scores: {
    quality: number | null;
    popularity: number | null;
    treasure: boolean;
    treasure_value: number | null;
    formula_version: string;
  } | null;
  sources: string[];
}

export interface Catalog {
  index_version: 'pickfit-index.v1';
  built_at: string;
  data_dir: string;
  /** sha256 over every data file (scripts/build_index.py); equal hashes mean the same data. */
  data_sha256?: string;
  count: number;
  entries: Entry[];
  bySlug: Map<string, Entry>;
}

export function loadCatalog(data: unknown): Catalog {
  const raw = data as Omit<Catalog, 'bySlug'>;
  if (raw?.index_version !== 'pickfit-index.v1' || !Array.isArray(raw.entries)) {
    throw new Error('index.json is not a pickfit-index.v1 file; run scripts/build_index.py');
  }
  return { ...raw, bySlug: new Map(raw.entries.map((entry) => [entry.slug, entry])) };
}

/** Tool names compared without case, spaces or punctuation ("LM Studio" = "lm-studio"). */
export const nameKey = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, '');

const LEVEL_ORDER = ['inference', 'service', 'function', 'install'];

/** The install guide to show: the given OS if verified there, else the strongest run's. */
export function bestGuide(entry: Entry, os?: OS): InstallGuide | null {
  const guides = OSES.flatMap((name) => (entry.install[name] ? [entry.install[name]] : [])).sort(
    (a, b) =>
      Number(b.run.os === os) - Number(a.run.os === os) ||
      LEVEL_ORDER.indexOf(a.run.level) - LEVEL_ORDER.indexOf(b.run.level) ||
      b.run.checked_at.localeCompare(a.run.checked_at),
  );
  return guides[0] ?? null;
}

/**
 * Did pickfit run the install steps on the user's system: their OS, and their
 * CPU architecture when they gave one? An arm64-only macOS run is not an Intel
 * Mac. Without an arch this answers for the OS only. null without an OS.
 */
export function verifiedOnUserSystem(entry: Entry, os?: OS, arch?: Arch): boolean | null {
  if (!os) return null;
  const guide = entry.install[os];
  return guide !== undefined && (arch === undefined || guide.run.arch === arch);
}

/** OSes with install steps that were actually run (replayed in a sandbox or done by hand). */
export function verifiedOn(entry: Entry): OS[] {
  return OSES.filter((os) => entry.install[os] !== undefined);
}
