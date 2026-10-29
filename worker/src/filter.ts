/** Step B of find_software: hard conditions, applied by code before any model sees a card. */
import { verifiedOn, type Arch, type Entry, type OS } from './catalog.ts';

export interface Conditions {
  category?: 'dev_cli' | 'local_ai' | 'any';
  os?: OS;
  arch?: Arch;
  budget?: 'free_only' | 'free_or_paid';
  must_run_locally?: boolean;
  exclude?: string[];
}

/** Hard filters never relax; MAX_CARDS bounds what one model call reads (architecture F.2 C). */
export const MAX_CARDS = 60;

export function runsLocally(entry: Entry): boolean {
  const { network, api_keys } = entry.prerequisites;
  return entry.processing === 'local' && network !== 'required' && api_keys.length === 0;
}

function fits(entry: Entry, cond: Conditions): boolean {
  const verified = verifiedOn(entry);
  if (verified.length === 0) return false; // only tools whose install steps were actually run
  if (cond.exclude?.includes(entry.slug)) return false;
  if (cond.category && cond.category !== 'any' && entry.category !== cond.category) return false;
  if (cond.budget === 'free_only' && entry.pricing !== 'free') return false;
  if (cond.must_run_locally && !runsLocally(entry)) return false;
  if (cond.os && !entry.platforms.includes(cond.os) && !verified.includes(cond.os)) return false;
  if (entry.prerequisites.apple_silicon_only) {
    if (cond.os && cond.os !== 'macos') return false;
    if (cond.arch === 'x86_64') return false;
  }
  return true;
}

export interface Filtered {
  candidates: Entry[];
  /** How many passed the hard filters before MAX_CARDS. */
  passed: number;
}

/**
 * Entries that meet every hard condition, in slug order (no popularity order
 * for the model to lean on). A tool that claims the user's OS but was verified
 * only elsewhere stays in; its card and the response say so.
 * Above MAX_CARDS, the highest treasure values are kept (BM25 is the planned upgrade), and so is
 * every well-known reference record (a handful), which a treasure order would always drop.
 */
export function hardFilter(entries: Entry[], cond: Conditions): Filtered {
  const passed = entries.filter((entry) => fits(entry, cond));
  const candidates =
    passed.length <= MAX_CARDS
      ? passed
      : [...passed]
          .sort(
            (a, b) =>
              Number(Boolean(b.well_known)) - Number(Boolean(a.well_known)) ||
              (b.scores?.treasure_value ?? -1) - (a.scores?.treasure_value ?? -1),
          )
          .slice(0, MAX_CARDS)
          .sort((a, b) => a.slug.localeCompare(b.slug));
  return { candidates, passed: passed.length };
}
