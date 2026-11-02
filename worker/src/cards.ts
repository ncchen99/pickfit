/**
 * Candidate cards: the only facts the matching model sees about a tool.
 * Values are flat (string, number, boolean, string list) so the guard can
 * check every reason against the field it cites.
 */
import { bestGuide, isWebApp, OSES, verifiedOn, verifiedOnUserSystem, webCheck, type Arch, type Entry, type InstallGuide, type OS } from './catalog.ts';
import { featuresOut } from './features.ts';
import { runDay } from './evidence.ts';

const MCP_TOOLS_SHOWN = 40;

export type CardValue = string | number | boolean | string[] | null;
export type Card = Record<CoreField, CardValue> & Partial<Record<WebField, CardValue>> & { slug: string };

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
export const CARD_FIELDS = [...CORE_FIELDS, ...WEB_FIELDS] as const;
export type CardField = (typeof CARD_FIELDS)[number];

function runLabel(entry: Entry, os: OS): string {
  const guide = entry.install[os]!;
  const how = guide.basis === 'replayed' ? 'sandbox install, replayed from scratch' : 'installed by hand';
  return `${os} ${guide.run.arch}: ${how}, ${guide.run.level} check passed, ${runDay(guide.run.checked_at)}`;
}

/** A web app's browser run, as verified_on says it: no OS, any browser. */
function webLabel(entry: Entry): string[] {
  const check = webCheck(entry);
  return check ? [`any OS, in a browser: opened in pickfit's sandboxed browser, ${check.level} check passed, ${check.checked_at.slice(0, 10)}`] : [];
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

export function toCard(entry: Entry, os?: OS, arch?: Arch): Card {
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
    features_not_checked: features.not_checked.map((f) => `${f.feature} (${f.reason})`),
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
  };
}

/** Tool names a sandbox handshake listed (the user's OS first), else none: README tool lists are not shown. */
function mcpTools(entry: Entry, userGuide: InstallGuide | undefined): string[] {
  const guide = userGuide?.mcp ? userGuide : OSES.map((os) => entry.install[os]).find((g) => g?.mcp);
  return (guide?.mcp?.tools ?? []).slice(0, MCP_TOOLS_SHOWN);
}
