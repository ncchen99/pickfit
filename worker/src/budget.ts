/**
 * The Worker's model spend, kept in D1 meta_budget (per UTC day; the table keeps its first name).
 * Every call's cost is recorded. Stopping at a cap is opt-in: with no cap set (the default) nothing
 * here blocks a call, and the table is only a record of what was spent.
 */

/** USD per UTC day and in all; null = no stop. */
export interface Caps {
  dailyCapUsd: number | null;
  totalCapUsd: number | null;
}

export interface BudgetCheck {
  ok: boolean;
  /** Spend so far; null when no cap is set, so D1 was not read. */
  todayUsd: number | null;
  totalUsd: number | null;
}

/** Whether any hard stop is set. */
export const capped = (caps: Caps) => caps.dailyCapUsd !== null || caps.totalCapUsd !== null;

export function utcDay(now: Date): string {
  return now.toISOString().slice(0, 10);
}

/**
 * Would a call costing up to estimateUsd stay under the caps that are set? With none set the answer is
 * yes without reading D1, so a D1 outage cannot turn the model off when nobody asked for a stop.
 */
export async function checkBudget(db: D1Database, now: Date, estimateUsd: number, caps: Caps): Promise<BudgetCheck> {
  if (!capped(caps)) return { ok: true, todayUsd: null, totalUsd: null };
  const row = await db
    .prepare(
      `SELECT COALESCE(SUM(cost_usd), 0) AS total,
              COALESCE(SUM(CASE WHEN day = ?1 THEN cost_usd END), 0) AS today
         FROM meta_budget`,
    )
    .bind(utcDay(now))
    .first<{ total: number; today: number }>();
  const todayUsd = row?.today ?? 0;
  const totalUsd = row?.total ?? 0;
  return {
    ok:
      (caps.dailyCapUsd === null || todayUsd + estimateUsd <= caps.dailyCapUsd) &&
      (caps.totalCapUsd === null || totalUsd + estimateUsd <= caps.totalCapUsd),
    todayUsd,
    totalUsd,
  };
}

export async function recordSpend(db: D1Database, now: Date, costUsd: number): Promise<void> {
  await db
    .prepare(
      `INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?1, 1, ?2)
       ON CONFLICT(day) DO UPDATE SET calls = calls + 1, cost_usd = cost_usd + excluded.cost_usd`,
    )
    .bind(utcDay(now), costUsd)
    .run();
}

/**
 * Hold `amountUsd` against the caps that are set, in one statement, so concurrent callers
 * cannot all pass a check before any of them records spend. True when held.
 * The holder releases it after its call (releaseSpend); the call's real cost
 * is recorded as usual. Used by the web page when a cap is set; the MCP path does not reserve.
 */
export async function reserveSpend(db: D1Database, now: Date, amountUsd: number, caps: Caps): Promise<boolean> {
  const result = await db
    .prepare(
      `INSERT INTO meta_budget (day, calls, cost_usd)
       SELECT ?1, 0, ?2
        WHERE (?3 IS NULL OR (SELECT COALESCE(SUM(CASE WHEN day = ?1 THEN cost_usd END), 0) FROM meta_budget) + ?2 <= ?3)
          AND (?4 IS NULL OR (SELECT COALESCE(SUM(cost_usd), 0) FROM meta_budget) + ?2 <= ?4)
       ON CONFLICT(day) DO UPDATE SET cost_usd = cost_usd + excluded.cost_usd`,
    )
    .bind(utcDay(now), amountUsd, caps.dailyCapUsd, caps.totalCapUsd)
    .run();
  return (result.meta.changes ?? 0) > 0;
}

export async function releaseSpend(db: D1Database, day: string, amountUsd: number): Promise<void> {
  await db.prepare('UPDATE meta_budget SET cost_usd = cost_usd - ?2 WHERE day = ?1').bind(day, amountUsd).run();
}
