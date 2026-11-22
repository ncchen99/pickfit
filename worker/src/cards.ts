/**
 * Candidate cards: the only facts the matching model sees about a tool.
 * Values are flat (string, number, boolean, string list) so the guard can
 * check every reason against the field it cites.
 */
import { bestGuide, isWebApp, OSES, verifiedOn, verifiedOnUserSystem, webCheck, type Arch, type Entry, type InstallGuide, type OS } from './catalog.ts';
import { matchedCapabilities } from './capabilities.ts';
import { featuresOut, shownWorking, standInOnly } from './features.ts';
import { runDay } from './evidence.ts';
import { verifiedDaysAgo } from './freshness.ts';
import { CARD_EGRESS_SHOWN } from './mcprisk.ts';

const MCP_TOOLS_SHOWN = 40;

export type CardValue = string | number | boolean | string[] | null;
export type Card = Record<CoreField, CardValue> &
  Partial<Record<WebField | MatchedField | StandingField | McpSafetyField, CardValue>> & { slug: string };

/** Brief 15 facts, each only when the record has it: its track, who uses it, its standing (new, stale; broken never
 * reaches a card, filter.ts), and whole days since it last passed a check, counted here so the model never works out
 * dates. Records not yet assessed leave them out, so their cards stay as they were. */
export const STANDING_FIELDS = ['track', 'used_by', 'standing', 'verified_days_ago'] as const;
export type StandingField = (typeof STANDING_FIELDS)[number];

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

/** An MCP server's safety facts (entry.mcp_safety), each only when its run recorded it: the probe's injection pattern
 * codes, how many tools declare destructive / open-world hints, and the public hosts the sandbox saw it reach. */
export const MCP_SAFETY_FIELDS = ['mcp_injection_flags', 'mcp_destructive_tools', 'mcp_open_world_tools', 'mcp_egress_hosts'] as const;
export type McpSafetyField = (typeof MCP_SAFETY_FIELDS)[number];

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
export const CARD_FIELDS = [...CORE_FIELDS, ...WEB_FIELDS, ...MATCHED_FIELDS, ...STANDING_FIELDS, ...MCP_SAFETY_FIELDS] as const;
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

function standingFields(entry: Entry, now: Date | undefined): Partial<Record<StandingField, CardValue>> {
  const out: Partial<Record<StandingField, CardValue>> = {};
  if (entry.track) out.track = entry.track;
  if (entry.used_by) out.used_by = entry.used_by;
  if (entry.standing) out.standing = entry.standing;
  const days = now ? verifiedDaysAgo(entry, now) : null;
  if (days !== null) out.verified_days_ago = days;
  return out;
}

/** query: the request's terms (relevance.ts), which choose the capabilities the card shows; none without it.
 * now: the request's clock, for verified_days_ago; without it the card leaves that field out. */
export function toCard(entry: Entry, os?: OS, arch?: Arch, query: readonly string[] = [], now?: Date): Card {
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
    // A feature checked only against a stand-in is not one pickfit saw work (privileges.md P1): the matcher may not
    // cite it as checked, and reads it with the others it did not see work (prompt rule 6), with why.
    features_checked: shownWorking(features).map((f) => f.feature),
    // The reason only when it says something about the tool (needs a GPU, failed its test); not that the run did not
    // get to it, checked only four, or predates feature checks.
    features_not_checked: [
      ...standInOnly(features).map((f) => `${f.feature} (${STAND_IN_ONLY})`),
      ...features.not_checked.map((f) => (SILENT_REASONS.has(f.reason) ? f.feature : `${f.feature} (${f.reason})`)),
    ],
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
    ...standingFields(entry, now),
    ...mcpSafetyFields(entry),
  };
}

function mcpSafetyFields(entry: Entry): Partial<Record<McpSafetyField, CardValue>> {
  const safety = entry.mcp_safety;
  const out: Partial<Record<McpSafetyField, CardValue>> = {};
  if (!safety) return out;
  if (safety.description_flags) out.mcp_injection_flags = safety.description_flags;
  if (safety.tool_annotations) {
    out.mcp_destructive_tools = safety.tool_annotations.destructive;
    out.mcp_open_world_tools = safety.tool_annotations.open_world;
  }
  if (safety.egress_hosts) out.mcp_egress_hosts = safety.egress_hosts.slice(0, CARD_EGRESS_SHOWN);
  return out;
}

/** On a card, beside a feature whose check ran only against a stand-in: it connected, the real service was not tried. */
export const STAND_IN_ONLY = 'stand_in_only';

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
