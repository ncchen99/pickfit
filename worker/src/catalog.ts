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
  run: RunSummary;
}

export interface Entry {
  slug: string;
  name: string;
  summary: string;
  why_worth_it: string | null;
  category: 'dev_cli' | 'local_ai' | 'other';
  kind: string;
  maturity: string | null;
  tags: string[];
  use_cases: string[];
  alternatives_to: string[];
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
  scores: {
    quality: number | null;
    popularity: number | null;
    treasure: boolean;
    treasure_value: number | null;
    formula_version: string;
  } | null;
  sources: string[];
  /** A reference record of a well-known tool, chosen by Homebrew install rank; null (or absent in older indexes) for the long tail. */
  well_known?: { package: string; rank: number; count: number; period_end: string } | null;
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

/** OSes with install steps that were actually run (replayed in a sandbox or done by hand). */
export function verifiedOn(entry: Entry): OS[] {
  return OSES.filter((os) => entry.install[os] !== undefined);
}
