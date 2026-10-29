/**
 * Step F: code checks the model's answer before anyone sees it. A pick must
 * be one of this request's candidates, and every reason must match the card
 * field it cites and must not contradict the card (offline, free, open
 * source, an OS). Reasons that fail are dropped; a pick with no reason left is
 * dropped. The well-known option, the one tool named from outside the
 * candidates, gets the few checks code can make about it.
 */
import { CARD_FIELDS, type Card, type CardValue } from './cards.ts';
import type { Entry } from './catalog.ts';
import type { ModelAnswer, ModelPick, ModelReason } from './prompt.ts';
import { nameKey } from './rules.ts';

const norm = (text: string) => text.trim().toLowerCase().replace(/\s+/g, ' ');

/** Does `value` appear in the card value (whole value, a list item, or a quoted part of text)? */
export function valueMatches(cardValue: CardValue, value: string): boolean {
  const want = norm(value);
  if (cardValue === null || want === '') return false;
  if (typeof cardValue === 'number') {
    const n = Number.parseFloat(want);
    return Number.isFinite(n) && Math.abs(n - cardValue) <= 0.5;
  }
  if (typeof cardValue === 'boolean') return want === String(cardValue);
  const items = Array.isArray(cardValue) ? cardValue : [cardValue];
  return items.some((item) => {
    const have = norm(item);
    return have === want || (want.length >= 3 && have.includes(want));
  });
}

const OS_WORDS: [RegExp, string][] = [
  [/\bmac ?os\b|\bmac\b|\bapple silicon\b/i, 'macos'],
  [/\blinux\b/i, 'linux'],
  [/\bwindows\b/i, 'windows'],
];

/** Why a free-text claim contradicts the card, or null when it does not. */
export function contradiction(card: Card, text: string): string | null {
  const t = text.toLowerCase();
  if (/\b(offline|no internet|no network|no cloud|on[- ]device|fully local|runs locally|local[- ]only|private)\b/.test(t)) {
    const local = card.processing === 'local' && card.network !== 'required' && (card.api_keys as string[]).length === 0;
    if (!local) return 'claims it runs locally/offline';
  }
  if (/\bfree\b/.test(t) && !/\bfree (tier|plan|trial)\b/.test(t) && card.pricing !== 'free') {
    return 'claims it is free';
  }
  if (/\bopen[- ]source\b/.test(t) && card.open_source !== true) return 'claims it is open source';
  if (/\b(no|without an?) (api key|account|sign[- ]?up)\b/.test(t) && (card.api_keys as string[]).length > 0) {
    return 'claims it needs no key or account';
  }
  if (/\b(no gpu|without a gpu|cpu[- ]only)\b/.test(t) && card.gpu === 'required') return 'claims it needs no GPU';
  const verifiedText = (card.verified_on as string[]).join(' ');
  for (const [pattern, os] of OS_WORDS) {
    if (!pattern.test(t)) continue;
    const tested = /\b(verified|tested|installed|checked|confirmed)\b/.test(t);
    if (tested && !verifiedText.includes(os)) return `claims it was verified on ${os}`;
    if (!tested && !(card.platforms as string[]).includes(os) && !verifiedText.includes(os)) {
      return `claims ${os} support`;
    }
  }
  return null;
}

export function reasonHolds(card: Card, reason: ModelReason): boolean {
  if (!(CARD_FIELDS as readonly string[]).includes(reason.field)) return false;
  const value = card[reason.field as keyof Card] as CardValue;
  return valueMatches(value, reason.value) && contradiction(card, reason.claim) === null;
}

export interface GuardedPick {
  slug: string;
  fit: string;
  reasons: ModelReason[];
  tradeoffs: string[];
  vs_well_known: string | null;
}

export interface GuardResult {
  picks: GuardedPick[];
  droppedPicks: number;
  droppedReasons: number;
}

export const clip = (text: string | null | undefined, max: number): string | null =>
  typeof text === 'string' && text.trim() ? text.trim().slice(0, max) : null;

export function guardPicks(answer: ModelAnswer, cards: Map<string, Card>, limit: number): GuardResult {
  const picks: GuardedPick[] = [];
  let droppedPicks = 0;
  let droppedReasons = 0;
  const seen = new Set<string>();
  let wellKnown = 0;
  for (const pick of answer.picks as ModelPick[]) {
    const card = cards.get(pick.slug);
    // At most one well-known reference record, so lesser-known tools that fit keep the other places.
    if (!card || seen.has(pick.slug) || picks.length >= limit || (card.well_known === true && wellKnown > 0)) {
      droppedPicks++;
      continue;
    }
    const reasons = (pick.reasons ?? []).filter((r) => reasonHolds(card, r)).slice(0, 4);
    droppedReasons += (pick.reasons ?? []).length - reasons.length;
    if (reasons.length === 0) {
      droppedPicks++;
      continue;
    }
    seen.add(pick.slug);
    if (card.well_known === true) wellKnown++;
    const fit = clip(pick.fit, 300);
    picks.push({
      slug: pick.slug,
      // A fit sentence that contradicts the card is replaced by the card's own summary.
      fit: fit && contradiction(card, fit) === null ? fit : String(card.summary),
      reasons: reasons.map((r) => ({ claim: r.claim.trim().slice(0, 200), field: r.field, value: r.value.slice(0, 200) })),
      tradeoffs: (pick.tradeoffs ?? []).map((t) => t.trim().slice(0, 200)).filter(Boolean).slice(0, 3),
      vs_well_known: clip(pick.vs_well_known, 300),
    });
  }
  return { picks, droppedPicks, droppedReasons };
}

export interface WellKnown {
  name: string;
  why: string;
}

export interface GuardedWellKnown {
  option: WellKnown | null;
  /** The name the model gave, kept or not; for the event log. */
  name: string | null;
  /** Why the option was dropped, when it was. */
  dropped: string | null;
}

export const NO_WELL_KNOWN: GuardedWellKnown = { option: null, name: null, dropped: null };

const CLAIMS_CHECKED = /\bpickfit\b|\b(verified|tested|vetted|checked)\b/i;

/**
 * Code cannot tell whether the named tool exists, is free or fits; the
 * response says so. It checks what it can: a plain name that is neither a
 * pickfit entry (that would be a pick, or was filtered out for a reason) nor
 * the current tool, and one sentence that says it is free and does not claim
 * anyone checked it.
 */
export function guardWellKnown(answer: ModelAnswer, entries: Entry[], current?: string): GuardedWellKnown {
  const raw = typeof answer.well_known_name === 'string' ? answer.well_known_name.trim() : '';
  if (!raw) return NO_WELL_KNOWN;
  const name = raw.slice(0, 60);
  const drop = (dropped: string): GuardedWellKnown => ({ option: null, name, dropped });
  const key = nameKey(raw);
  if (raw.length > 60 || !key || /[\n<>]|:\/\//.test(raw)) return drop('not_a_name');
  if (entries.some((entry) => nameKey(entry.slug) === key || nameKey(entry.name) === key)) return drop('listed_in_pickfit');
  if (current && nameKey(current) === key) return drop('current_tool');
  const text = clip(answer.well_known_why, 1000);
  // One sentence: cut at the first sentence end ("llama.cpp" has no space after its dot).
  const why = text ? (text.match(/^.*?[.!?](?=\s|$)/s)?.[0] ?? text).slice(0, 240) : null;
  if (!why) return drop('no_reason');
  if (!/\bfree\b/i.test(why)) return drop('not_said_free');
  if (CLAIMS_CHECKED.test(why)) return drop('claims_checked');
  return { option: { name, why }, name, dropped: null };
}

/** Minimal shape check; strict decoding should guarantee it, but code does not assume. */
export function parseAnswer(text: string): ModelAnswer | null {
  let data: any;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  const ok =
    data &&
    typeof data === 'object' &&
    data.need &&
    typeof data.need === 'object' &&
    Array.isArray(data.picks) &&
    data.picks.every(
      (p: any) =>
        p &&
        typeof p.slug === 'string' &&
        typeof p.fit === 'string' &&
        Array.isArray(p.reasons) &&
        p.reasons.every(
          (r: any) => r && typeof r.claim === 'string' && typeof r.field === 'string' && typeof r.value === 'string',
        ) &&
        Array.isArray(p.tradeoffs) &&
        p.tradeoffs.every((t: any) => typeof t === 'string'),
    );
  return ok ? (data as ModelAnswer) : null;
}

