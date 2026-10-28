/** The Worker's Meta spending caps, kept in D1 meta_budget (per UTC day). */

export interface BudgetCheck {
  ok: boolean;
  todayUsd: number;
  totalUsd: number;
}

export function utcDay(now: Date): string {
  return now.toISOString().slice(0, 10);
}

/** Would a call costing up to estimateUsd stay under both caps? */
export async function checkBudget(
  db: D1Database,
  now: Date,
  estimateUsd: number,
  caps: { dailyCapUsd: number; totalCapUsd: number },
): Promise<BudgetCheck> {
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
    ok: todayUsd + estimateUsd <= caps.dailyCapUsd && totalUsd + estimateUsd <= caps.totalCapUsd,
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
