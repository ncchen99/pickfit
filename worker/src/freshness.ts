/**
 * How old a check is (D1, D2; brief 15.4): the days since pickfit ran the shown steps, said for every pick, and a
 * warning when they may be out of date, because the project released a version after the check or the check is past
 * its re-verification cycle (the record's reverify_cycle_days, else STALE_DAYS). The MCP answer and the tool page say
 * the same thing; neither claims the steps broke, only that pickfit has not run them since.
 */
import type { Entry, Standing } from './catalog.ts';
import { L } from './i18n.ts';

/** The re-verification cycle when the record sets none. */
export const STALE_DAYS = 90;

export interface Freshness {
  /** Whole days from the check to `now`; null without a check. */
  age_days: number | null;
  /** One line on every pick with a check: how many days ago pickfit verified it, and the day. Null without a check. */
  verified_ago: string | null;
  /** Days between re-verifications: the record's own cycle, else STALE_DAYS. */
  cycle_days: number;
  /** The check is past its cycle (or due date), or the record's standing is stale. */
  overdue: boolean;
  /** The project's last release, as the profile has it. */
  last_release: string | null;
  /** One line when the check may be out of date; null otherwise. */
  warning: string | null;
  /** Short note for new work (standing new): lower confidence until it passes more re-verifications; null otherwise. */
  note: string | null;
}

/** What a record says about its own re-verification (pickfit/index.py _verification_cycle, _standing). */
export interface Cycle {
  cycleDays?: number | null;
  dueAt?: string | null;
  standing?: Standing | null;
  /** When a check last passed; counts when later than the shown check (a re-verification with the same steps). */
  lastPassedAt?: string | null;
}

export const cycleOf = (entry: Entry): Cycle => ({
  cycleDays: entry.verification.reverify_cycle_days ?? null,
  dueAt: entry.verification.reverify_due_at ?? null,
  standing: entry.standing ?? null,
  lastPassedAt: entry.verification.last_passed_at ?? null,
});

const dayOf = (iso: string) => iso.slice(0, 10);
const valid = (iso: string | null | undefined): iso is string => !!iso && !Number.isNaN(Date.parse(iso));
const daysBetween = (iso: string, now: Date) => Math.max(0, Math.floor((now.getTime() - Date.parse(iso)) / 86_400_000));

/** When the record last passed a check: last_passed_at, else checked_at (brief 15.4); null without either. */
export function lastPassed(entry: Entry): string | null {
  const passed = entry.verification.last_passed_at;
  if (valid(passed)) return passed;
  return valid(entry.verification.checked_at) ? entry.verification.checked_at : null;
}

/** Whole days since the record last passed a check, for the card; null without a check. */
export function verifiedDaysAgo(entry: Entry, now: Date): number | null {
  const at = lastPassed(entry);
  return at ? daysBetween(at, now) : null;
}

/** The project released after the check: the steps may have changed. Null otherwise. */
export function releasedAfter(checkedAt: string | null, lastRelease: string | null): string | null {
  if (!checkedAt || !lastRelease || dayOf(lastRelease) <= dayOf(checkedAt)) return null;
  return L(
    `A new release came out on ${dayOf(lastRelease)}, after pickfit's check on ${dayOf(checkedAt)}; the steps may have changed.`,
    `${dayOf(lastRelease)} 出了新版本，比 pickfit ${dayOf(checkedAt)} 的檢查還新，步驟可能已經不同。`,
  );
}

function agoLine(ageDays: number, day: string): string {
  if (ageDays === 0) return L(`pickfit verified it today (${day}).`, `pickfit 今天（${day}）驗證過。`);
  const unit = ageDays === 1 ? 'day' : 'days';
  return L(`pickfit verified it ${ageDays} ${unit} ago (${day}).`, `pickfit 在 ${ageDays} 天前（${day}）驗證過。`);
}

export function freshness(checkedAt: string | null, lastRelease: string | null, now: Date, cycle: Cycle = {}): Freshness {
  const cycleDays = cycle.cycleDays && cycle.cycleDays > 0 ? cycle.cycleDays : STALE_DAYS;
  // A re-verification that passed with the same steps moves last_passed_at, not the shown run's time.
  const at = valid(cycle.lastPassedAt) && (!valid(checkedAt) || Date.parse(cycle.lastPassedAt) > Date.parse(checkedAt))
    ? cycle.lastPassedAt
    : checkedAt;
  const note = cycle.standing === 'new'
    ? L('New work: confidence is lower until it passes more re-verifications.', '新作：還沒經過幾次重驗，信心較低。')
    : null;
  if (!valid(at)) {
    return { age_days: null, verified_ago: null, cycle_days: cycleDays, overdue: false, last_release: lastRelease, warning: null, note };
  }
  const ageDays = daysBetween(at, now);
  const day = dayOf(at);
  const pastDue = valid(cycle.dueAt) && now.getTime() >= Date.parse(cycle.dueAt);
  const overdue = ageDays > cycleDays || pastDue || cycle.standing === 'stale';
  let warning = releasedAfter(at, lastRelease);
  if (!warning && overdue) {
    const base = L(`pickfit checked these steps ${ageDays} days ago, on ${day}`, `pickfit 在 ${ageDays} 天前（${day}）檢查過這些步驟`);
    // The record's own cycle is named; past the default one the sentence stays as it was. Stale by standing alone
    // says a re-verification is due without claiming a cycle ran out.
    const why = ageDays <= cycleDays && !pastDue
      ? L('; a re-verification is due.', '；該重驗了。')
      : cycle.cycleDays
        ? L(`; it is re-verified every ${cycleDays} days.`, `；這類工具每 ${cycleDays} 天重驗一次。`)
        : L('.', '。');
    warning = base + why;
  }
  return { age_days: ageDays, verified_ago: agoLine(ageDays, day), cycle_days: cycleDays, overdue, last_release: lastRelease, warning, note };
}
