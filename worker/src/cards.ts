/**
 * Candidate cards: the only facts the matching model sees about a tool.
 * Values are flat (string, number, boolean, string list) so the guard can
 * check every reason against the field it cites.
 */
import { bestGuide, OSES, verifiedOn, verifiedOnUserSystem, type Arch, type Entry, type InstallGuide, type OS } from './catalog.ts';
import { featuresOut } from './features.ts';
import { runDay } from './evidence.ts';

const MCP_TOOLS_SHOWN = 40;

export type CardValue = string | number | boolean | string[] | null;
export type Card = Record<CardField, CardValue> & { slug: string };

/** Fields a reason may cite. The model's schema enumerates exactly these. */
export const CARD_FIELDS = [
  'name',
  'summary',
  'why_worth_it',
  'category',
  'kind',
  'maturity',
  'tags',
  'use_cases',
  'features_checked',
  'features_not_checked',
  'alternatives_to',
  'platforms',
  'verified_on',
  'verified_on_user_os',
  'install_method_user_os',
  'manual_steps',
  'pricing',
  'pricing_note',
  'open_source',
  'license',
  'processing',
  'gpu',
  'network',
  'api_keys',
  'apple_silicon_only',
  'min_ram_gb',
  'runtimes',
  'system_packages',
  'last_release',
  'quality',
  'popularity',
  'mcp_tools',
  'mcp_env_vars',
] as const;
export type CardField = (typeof CARD_FIELDS)[number];

function runLabel(entry: Entry, os: OS): string {
  const guide = entry.install[os]!;
  const how = guide.basis === 'replayed' ? 'sandbox install, replayed from scratch' : 'installed by hand';
  return `${os} ${guide.run.arch}: ${how}, ${guide.run.level} check passed, ${runDay(guide.run.checked_at)}`;
}

export function toCard(entry: Entry, os?: OS, arch?: Arch): Card {
  const userGuide = os ? entry.install[os] : undefined;
  const pre = entry.prerequisites;
  const features = featuresOut(entry, bestGuide(entry, os));
  return {
    slug: entry.slug,
    name: entry.name,
    summary: entry.summary,
    why_worth_it: entry.why_worth_it,
    category: entry.category,
    kind: entry.kind,
    maturity: entry.maturity,
    tags: entry.tags,
    use_cases: entry.use_cases,
    features_checked: features.checked.map((f) => f.feature),
    features_not_checked: features.not_checked.map((f) => `${f.feature} (${f.reason})`),
    alternatives_to: entry.alternatives_to,
    platforms: entry.platforms,
    verified_on: verifiedOn(entry).map((name) => runLabel(entry, name)),
    verified_on_user_os: verifiedOnUserSystem(entry, os, arch),
    install_method_user_os: userGuide ? userGuide.method : null,
    manual_steps: userGuide ? userGuide.manual_steps : [],
    pricing: entry.pricing,
    pricing_note: entry.pricing_note,
    open_source: entry.open_source,
    license: entry.license,
    processing: entry.processing,
    gpu: pre.gpu,
    network: pre.network,
    api_keys: pre.api_keys,
    apple_silicon_only: pre.apple_silicon_only,
    min_ram_gb: pre.min_ram_gb,
    runtimes: pre.runtimes,
    system_packages: pre.system_packages,
    last_release: entry.last_release,
    quality: entry.scores?.quality ?? null,
    popularity: entry.scores?.popularity ?? null,
    mcp_tools: mcpTools(entry, userGuide),
    mcp_env_vars: (entry.mcp?.env_vars ?? []).map((v) => v.name),
  };
}

/** Tool names a sandbox handshake listed (the user's OS first), else none: README tool lists are not shown. */
function mcpTools(entry: Entry, userGuide: InstallGuide | undefined): string[] {
  const guide = userGuide?.mcp ? userGuide : OSES.map((os) => entry.install[os]).find((g) => g?.mcp);
  return (guide?.mcp?.tools ?? []).slice(0, MCP_TOOLS_SHOWN);
}
