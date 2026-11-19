/** The index written by scripts/build_index.py ("pickfit-index.v1"). */

export type OS = 'macos' | 'linux' | 'windows';
export type Arch = 'arm64' | 'x86_64';
export type Need = 'required' | 'optional' | 'none';
export const OSES: readonly OS[] = ['macos', 'linux', 'windows'];

/**
 * The categories a request, a filter or a shelf can name, in the order pages list them. The one list the
 * Worker's types, tool schemas, match schema, labels and icons are built from; pickfit/schema.py's Category
 * has the same values. infra_devops: containers, Kubernetes, CI/CD, IaC, monitoring and backup; security_net:
 * network diagnostics, packet analysis, TLS/PKI, encryption, secret scanning; data_db: local SQL engines,
 * database clients, JSON/CSV/log processing; productivity_docs: notes, knowledge bases, whiteboards and
 * diagrams, document conversion, slides; media_files: media download and transcoding, image compression,
 * PDF tools, file transfer.
 */
export const NAMED_CATEGORIES = ['dev_cli', 'local_ai', 'mcp_server', 'infra_devops', 'security_net', 'data_db', 'productivity_docs', 'media_files'] as const;
/** Every category a record can have: the named ones, then "other" for what fits none of them. */
export const CATEGORIES = [...NAMED_CATEGORIES, 'other'] as const;
export type NamedCategory = (typeof NAMED_CATEGORIES)[number];
export type Category = (typeof CATEGORIES)[number];

/** A run's verification clip (index.py _video): served at /video/<slug>/<file>, the poster at <clip stem>.jpg. */
export interface RunVideo {
  clip: string;
  clip_sha256: string;
  seconds: number;
  recorded_at: string;
  /** The run's checked features the clip shows. */
  features: string[];
  /** The unedited recordings the clip was cut from; feature_index: which of `features` each one shows (older indexes lack it). */
  raw: { file: string; sha256: string; seconds: number; feature_index?: number | null }[];
  /** The clip's segments in time order, covering it from 0 s: one per feature (a clip cut before 11/19 also opens
   * and closes on a card, feature null). */
  chapters?: VideoChapter[] | null;
  /** The clip's captions (it has no words on its picture since 11/19), served as WebVTT at captionsPath(). */
  captions?: VideoCaption[] | null;
}

export interface VideoChapter {
  start_s: number;
  title: string;
  /** Exactly one of the clip's `features`; null for the opening and closing cards. */
  feature: string | null;
  /** Index into `raw`: the unedited recording the chapter's first segment comes from, and where in it (seconds). */
  raw?: number | null;
  raw_s?: number | null;
}

export interface VideoCaption {
  start_s: number;
  end_s: number;
  /** English in the index; the zh-TW page's catalog has it translated. */
  text: string;
}

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
  /** A clip of pickfit operating it in this run; absent or null when none was recorded. */
  video?: RunVideo | null;
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
   * action_checked: also, a model operated it from screenshots and pickfit's own check of the result passed.
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
  /**
   * file: a file the app wrote, read by root; clipboard: read by pickfit's display user; screen_text: read off pickfit's
   * screenshot; gone: a file root read before the app started and found gone after it stopped (the app deleted it).
   */
  check: 'file' | 'clipboard' | 'screen_text' | 'gone';
  passed: boolean;
  /** actions: the recorded clicks and keys passed again; operated: the operator reached the goal again. */
  replay: 'actions' | 'operated';
  goal: string;
  /** pickfit's own line about what the check found. */
  observed: string;
  /** The model that chose the clicks and keys (record field operator_model); absent in an index built before it was written out. */
  operator_model?: string | null;
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
  /**
   * The same commands as a user runs them (pickfit/userpaths.py): pickfit's sandbox home written as $HOME. The
   * fields above stay exactly as the run executed them. Absent from older indexes.
   */
  user?: UserGuide;
}

export interface UserGuide {
  steps: { command: string; purpose: string | null }[];
  first_task_setup: { command: string; background: boolean }[];
  first_task: string | null;
  check: { command: string; expected_signal: string } | null;
  /** Some command named the sandbox home and was rewritten. */
  changed: boolean;
  /** Commands still naming the sandbox home (inside single quotes): "step 4", "first task", "check". */
  not_portable: string[];
  /** A command names the sandbox's work folder, which existed before any step ran. */
  needs_workdir: boolean;
  /** The sandbox home the verified commands name (/Users/sbx, /home/sbx); null when none does. */
  sandbox_home: string | null;
}

/** One goal pickfit operated a hosted web app toward in its browser, and what its own check found. */
export interface WebOperation {
  feature: string | null;
  /** page_text, element, url: read off the page by pickfit; download: a file pickfit read; clipboard: read by pickfit. */
  check: 'page_text' | 'element' | 'url' | 'download' | 'clipboard';
  passed: boolean;
  goal: string;
  /** pickfit's own line about what the check found. */
  observed: string;
  /** The model that chose the actions (record field operator_model); absent in an index built before it was written out. */
  operator_model?: string | null;
}

/**
 * What a sandboxed browser saw of a hosted web app (the strongest passed run; index.py _web). One session per
 * site, so no replay. The page loaded to its main screen = install; an operation pickfit checked = function.
 */
export interface WebCheck {
  run_id: string;
  level: 'function' | 'install';
  checked_at: string;
  evidence_url: string | null;
  browser: string;
  account_needed: boolean | null;
  ads_seen: boolean | null;
  third_party_domains: number | null;
  third_party_hosts: string[];
  /** none: what pickfit typed in or chose stayed on the device; observed: a request carried it off; unknown: not checked. */
  data_sent: 'none' | 'observed' | 'unknown';
  data_sent_note: string | null;
  pwa: boolean | null;
  /** verified: a PWA reloaded with the network off and still worked. */
  offline: 'verified' | 'not_offline' | 'not_tested';
  operations: WebOperation[];
  features: FeatureCoverage[];
}

/** A hosted web app (kind web_app): the URL to open, and what pickfit's browser saw (null until a run passed). */
export interface WebApp {
  url: string;
  check: WebCheck | null;
}

/** One advertised feature in plain words, with steps only when the guide's run checked it. */
export interface FeatureGuide {
  feature: string;
  title: string;
  steps: string[];
}

/** Reader-facing text a model wrote from the record and its run (pickfit/usage_guide.py); model names who wrote it. */
export interface UsageGuide {
  model: string;
  generated_at: string;
  run_id: string | null;
  open_hint: string | null;
  features: FeatureGuide[];
}

export interface Entry {
  slug: string;
  name: string;
  summary: string;
  why_worth_it: string | null;
  /** Plain feature titles and how-to steps for the tool page; older indexes lack it. */
  usage_guide?: UsageGuide | null;
  category: Category;
  kind: string;
  maturity: string | null;
  tags: string[];
  use_cases: string[];
  alternatives_to: string[];
  /** The main features the README advertises; older indexes lack it. */
  features?: string[];
  homepage: string | null;
  /** null for a hosted web app with no public repository. */
  repo_url: string | null;
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
  /** Hosted web apps only (kind web_app): no install guides, a URL to open instead. */
  web?: WebApp | null;
  /** Desktop and web apps only: what pickfit's visual check of its own screenshots found (pickfit/index.py _visual). */
  visual?: VisualCheck | null;
  /** Known high or critical vulnerabilities (OSV.dev) in what a fresh install brings (pickfit/index.py _security).
   * Older indexes lack it: read a missing one as unchecked, reason not_run (securityOf). */
  security?: SecurityCheck | null;
  scores: {
    quality: number | null;
    popularity: number | null;
    treasure: boolean;
    treasure_value: number | null;
    formula_version: string;
    /** Share of the quality score's weight that had data, 0-1. Older indexes lack it. */
    confidence?: number;
    /** The parts with weight but no data, so they dropped out: why confidence is below 1. */
    unmeasured?: string[];
  } | null;
  sources: string[];
}

/** A desktop or web app's visual check, as the quality score applied it: "defect" took 5% off, "clean" changed nothing,
 * "not_checked" means no current check (nothing is taken off for that). */
export interface VisualCheck {
  status: 'defect' | 'clean' | 'not_checked';
  factor?: number;
  defects?: { kind: string; problem: string; quote: string }[];
  checked_at?: string;
  model?: string;
}

/** Why pickfit could not check a tool for known vulnerabilities; not_run = no check yet. */
export type SecurityReason = 'no_source' | 'no_lockfile' | 'lockfile_not_supported' | 'resolve_failed' | 'not_run';

/** A sec.v2 check's level (pickfit/security.py): its worst known finding's, or none. It says nothing about what could
 * not be checked (SecurityCoverage). blocked, exposed and conditional read as status vulnerable. */
export type SecurityLevel = 'blocked' | 'exposed' | 'conditional' | 'present_unreachable' | 'not_shipped' | 'none';
export const SECURITY_LEVELS = ['blocked', 'exposed', 'conditional', 'present_unreachable', 'not_shipped', 'none'] as const;
/** A finding's level: the first five. */
export type FindingLevel = 'blocked' | 'exposed' | 'conditional' | 'present_unreachable' | 'not_shipped';
/** Why something could not be checked: the gap taxonomy's categories (pickfit/security.py). */
export type GapCategory =
  | 'advisory_db'
  | 'lockfile_missing'
  | 'lockfile_unreadable'
  | 'resolve_failed'
  | 'no_adapter'
  | 'binary_no_metadata'
  | 'no_source'
  | 'tool_error'
  | 'platform_unsupported';

/** How much of a sec.v2 check could be checked, apart from what it found: an unknown is never a vulnerability. */
export interface SecurityCoverage {
  state: 'complete' | 'partial' | 'unchecked';
  packages_checked: number;
  /** Checked plus what the gaps are known to hide (a lower bound). */
  packages_found: number;
  /** The first gaps: a stable code, its category, the ecosystem. */
  gaps: { code: string; category: GapCategory; ecosystem: string }[];
}

/** One known vulnerability in a package the tool brings. */
export interface SecurityFinding {
  /** Ecosystem and name, e.g. npm:undici. */
  package: string;
  version: string;
  /** GHSA-…, RUSTSEC-…, MAL-…: its page is https://osv.dev/vulnerability/<advisory>. */
  advisory: string;
  /** sec.v1 lists only CRITICAL and HIGH; sec.v2 also lists a lower one on CISA's exploited list. */
  severity: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW' | 'UNKNOWN';
  fixed_in: string | null;
  summary: string;
  malicious: boolean;
  /** sec.v2 only: the finding's level, where the package sits, whether CISA lists it as exploited. */
  level?: FindingLevel;
  scope?: string | null;
  kev?: boolean | null;
  /** sec.v2 only: what must hold for it to matter, as codes (user_interaction, local_access, option:NAME, ...). */
  preconditions?: string[];
}

/** A sec.v2 finding present in what installs but not reached, and how pickfit knows (method, the first evidence). */
export interface UnreachableFinding {
  package: string;
  version: string;
  advisory: string;
  severity: SecurityFinding['severity'];
  method: string | null;
  evidence: string[];
}

/** The vulnerability check. sec.v1: "vulnerable" capped quality at 79 (so never a hidden gem), "clean" changed nothing,
 * "unchecked" changed nothing and says why. sec.v2 adds the level the scoring reads and the counts per level. */
export interface SecurityCheck {
  status: 'vulnerable' | 'clean' | 'unchecked';
  /** Only when unchecked. */
  reason?: SecurityReason;
  /** YYYY-MM-DD; absent when reason is not_run. */
  checked_at?: string;
  packages_checked?: number;
  /** vulnerable: how many findings in all, one per advisory on each package version (findings lists at most 10). */
  count?: number;
  /** vulnerable: distinct vulnerabilities among the findings (one advisory on several packages or versions counts once);
   * absent on a check from before 11/3 evening, which reads as count. */
  advisories?: number;
  findings?: SecurityFinding[];
  /** sec.v2 only (absent on an older check). */
  level?: SecurityLevel;
  policy_version?: string;
  /** Counted findings (high, critical, malicious or exploited) per finding level. */
  counts?: Partial<Record<FindingLevel, number>>;
  /** What was scanned: the installed artifact's SBOM, a fresh registry install, or the repository's lockfiles. */
  target?: 'installed_artifact' | 'registry_resolve' | 'repo_lockfile';
  unreachable?: UnreachableFinding[];
  coverage?: SecurityCoverage;
}

/** An entry's security check; an index from before the check has none, which reads as not checked yet. */
export function securityOf(entry: Entry): SecurityCheck {
  return entry.security ?? { status: 'unchecked', reason: 'not_run' };
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

/** A hosted web app: opened at a URL, never installed. */
export const isWebApp = (entry: Pick<Entry, 'kind'>) => entry.kind === 'web_app';

/** What pickfit's browser saw of a web app, or null (not a web app, or no run passed yet). */
export const webCheck = (entry: Entry): WebCheck | null => entry.web?.check ?? null;

/** pickfit ran it: install steps on some OS, or, for a web app, a passed browser run. Only these are ever suggested. */
export const isVerified = (entry: Entry) => verifiedOn(entry).length > 0 || webCheck(entry) !== null;
