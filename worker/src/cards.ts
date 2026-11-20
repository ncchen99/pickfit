/**
 * Candidate cards: the only facts the matching model sees about a tool.
 * Values are flat (string, number, boolean, string list) so the guard can
 * check every reason against the field it cites.
 */
import { bestGuide, isWebApp, OSES, verifiedOn, verifiedOnUserSystem, webCheck, type Arch, type Entry, type InstallGuide, type OS } from './catalog.ts';
import { matchedCapabilities } from './capabilities.ts';
import { featuresOut } from './features.ts';
import { runDay } from './evidence.ts';

const MCP_TOOLS_SHOWN = 40;

export type CardValue = string | number | boolean | string[] | null;
export type Card = Record<CoreField, CardValue> &
  Partial<Record<WebField | MatchedField, CardValue>> & { slug: string };

/** A web app's card only: what pickfit's browser saw. Other cards leave them out (60 cards, fewer tokens). */
export const WEB_FIELDS = [
  'no_install',
  'account_needed',
  'ads_seen',
  'third_party_domains',
  'data_sent',
  'works_offline',
] as const;
export type WebField = (typeof WEB_FIELDS)[number];

/** Only when the request's words name some: the tool's documented capabilities they name (capabilities.ts).
 * The docs claim them; pickfit did not check them one by one. Other cards leave the field out. */
export const MATCHED_FIELDS = ['capabilities_matched'] as const;
export type MatchedField = (typeof MATCHED_FIELDS)[number];

const CORE_FIELDS = [
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
type CoreField = (typeof CORE_FIELDS)[number];

/** Fields a reason may cite. The model's schema enumerates exactly these. */
export const CARD_FIELDS = [...CORE_FIELDS, ...WEB_FIELDS, ...MATCHED_FIELDS] as const;
export type CardField = (typeof CARD_FIELDS)[number];

/** "linux x86_64: function check passed 2026-10-28, sandbox, replayed": the OS first (rules and the guard read it). */
function runLabel(entry: Entry, os: OS): string {
  const guide = entry.install[os]!;
  const how = guide.basis === 'replayed' ? 'sandbox, replayed' : 'by hand';
  return `${os} ${guide.run.arch}: ${guide.run.level} check passed ${runDay(guide.run.checked_at)}, ${how}`;
}

/** A web app's browser run, as verified_on says it: no OS, any browser. */
function webLabel(entry: Entry): string[] {
  const check = webCheck(entry);
  return check ? [`any OS, in a browser: ${check.level} check passed ${check.checked_at.slice(0, 10)}, sandboxed browser`] : [];
}

function webFields(entry: Entry): Partial<Record<WebField, CardValue>> {
  const check = webCheck(entry);
  if (!isWebApp(entry) || !check) return {};
  return {
    no_install: true,
    account_needed: check.account_needed,
    ads_seen: check.ads_seen,
    third_party_domains: check.third_party_domains,
    data_sent: check.data_sent,
    works_offline: check.offline,
  };
}

/** query: the request's terms (relevance.ts), which choose the capabilities the card shows; none without it. */
export function toCard(entry: Entry, os?: OS, arch?: Arch, query: readonly string[] = []): Card {
  const userGuide = os ? entry.install[os] : undefined;
  const pre = entry.prerequisites;
  const features = featuresOut(entry, bestGuide(entry, os));
  const web = isWebApp(entry);
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
    // The reason only when it says something about the tool (needs a GPU, failed its test); not that the run did not
    // get to it, checked only four, or predates feature checks.
    features_not_checked: features.not_checked.map((f) => (SILENT_REASONS.has(f.reason) ? f.feature : `${f.feature} (${f.reason})`)),
    alternatives_to: entry.alternatives_to,
    platforms: entry.platforms,
    verified_on: web ? webLabel(entry) : verifiedOn(entry).map((name) => runLabel(entry, name)),
    // A web app runs in any browser: there are no install steps to have run on the user's OS.
    verified_on_user_os: web ? null : verifiedOnUserSystem(entry, os, arch),
    install_method_user_os: userGuide ? userGuide.method : null,
    manual_steps: userGuide ? userGuide.manual_steps : [],
    pricing: entry.pricing,
    pricing_note: entry.pricing_note,
    open_source: entry.open_source,
    license: entry.license,
    processing: entry.processing,
    gpu: pre.gpu,
    // A web app needs the network to load; a PWA pickfit reloaded offline needs it only for that first load.
    network: web && webCheck(entry) ? (webCheck(entry)!.offline === 'verified' ? 'optional' : 'required') : pre.network,
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
    ...webFields(entry),
    ...matchedFields(entry, query),
  };
}

/** Why a feature was not checked, when it says nothing about the tool itself. */
const SILENT_REASONS = new Set<string>(['not_attempted', 'beyond_budget', 'not_recorded', 'other']);

/** Card fields the prompt never carries: popularity is never a reason (prompt rule 3). */
const NOT_SENT = new Set<string>(['popularity']);
/** Fields whose false is their default, sent only when true. Every other false says something (open_source false). */
const FALSE_IS_DEFAULT = new Set<string>(['apple_silicon_only']);

/**
 * The card as the matcher reads it: the same values, less what says nothing (null, an empty list or string, a false
 * that is the default, popularity). The guard and the rules still read the whole card, and every value sent is the
 * card's own, so a reason the model copies from it holds against the card. About a third smaller.
 */
export function promptCard(card: Card): Record<string, CardValue> {
  const out: Record<string, CardValue> = {};
  for (const [key, value] of Object.entries(card) as [string, CardValue][]) {
    if (NOT_SENT.has(key) || value === null || value === '' || (Array.isArray(value) && value.length === 0)) continue;
    if (value === false && FALSE_IS_DEFAULT.has(key)) continue;
    out[key] = value;
  }
  return out;
}

function matchedFields(entry: Entry, query: readonly string[]): Partial<Record<MatchedField, CardValue>> {
  const matched = matchedCapabilities(entry, query);
  return matched.length ? { capabilities_matched: matched } : {};
}

/** Tool names a sandbox handshake listed (the user's OS first), else none: README tool lists are not shown. */
function mcpTools(entry: Entry, userGuide: InstallGuide | undefined): string[] {
  const guide = userGuide?.mcp ? userGuide : OSES.map((os) => entry.install[os]).find((g) => g?.mcp);
  return (guide?.mcp?.tools ?? []).slice(0, MCP_TOOLS_SHOWN);
}
