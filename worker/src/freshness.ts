/**
 * How old a check is (D1, D2): the days since pickfit ran the shown steps, and a warning when they may be out of date,
 * because the project released a version after the check or the check is over STALE_DAYS old. The MCP answer and the
 * tool page say the same thing; neither claims the steps broke, only that pickfit has not run them since.
 */
import { L } from './i18n.ts';

export const STALE_DAYS = 90;

export interface Freshness {
  /** Whole days from the check to `now`; null without a check. */
  age_days: number | null;
  /** The project's last release, as the profile has it. */
  last_release: string | null;
  /** One line when the check may be out of date; null otherwise. */
  warning: string | null;
}

const dayOf = (iso: string) => iso.slice(0, 10);

/** The project released after the check: the steps may have changed. Null otherwise. */
export function releasedAfter(checkedAt: string | null, lastRelease: string | null): string | null {
  if (!checkedAt || !lastRelease || dayOf(lastRelease) <= dayOf(checkedAt)) return null;
  return L(
    `A new release came out on ${dayOf(lastRelease)}, after pickfit's check on ${dayOf(checkedAt)}; the steps may have changed.`,
    `${dayOf(lastRelease)} 出了新版本，比 pickfit ${dayOf(checkedAt)} 的檢查還新，步驟可能已經不同。`,
  );
}

export function freshness(checkedAt: string | null, lastRelease: string | null, now: Date): Freshness {
  if (!checkedAt || Number.isNaN(Date.parse(checkedAt))) return { age_days: null, last_release: lastRelease, warning: null };
  const ageDays = Math.max(0, Math.floor((now.getTime() - Date.parse(checkedAt)) / 86_400_000));
  const checked = dayOf(checkedAt);
  let warning = releasedAfter(checkedAt, lastRelease);
  if (!warning && ageDays > STALE_DAYS) {
    warning = L(`pickfit checked these steps ${ageDays} days ago, on ${checked}.`, `pickfit 在 ${ageDays} 天前（${checked}）檢查過這些步驟。`);
  }
  return { age_days: ageDays, last_release: lastRelease, warning };
}
