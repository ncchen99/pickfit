/** D1 events. Never an IP address, never the user's own words (only parsed conditions). */

export interface EventRow {
  type: 'find' | 'alternatives' | 'install_guide' | 'outcome' | 'submit';
  rec_id?: string | null;
  slug?: string | null;
  os?: string | null;
  arch?: string | null;
  category?: string | null;
  need?: Record<string, unknown> | null;
  results?: string[] | null;
  stage?: 'installed' | 'first_run' | 'still_using' | null;
  success?: boolean | null;
  satisfied?: -1 | 0 | 1 | null;
  error_excerpt?: string | null;
  replaced_by?: string | null;
  note?: string | null;
  /** Coarse, for still_using / replaced / abandoned only: never an exact time. */
  last_used?: 'this_week' | 'this_month' | 'older' | 'unknown' | null;
  reporter?: Reporter | null;
  client?: string | null;
  matched_by?: string | null;
  degraded?: boolean | null;
  degraded_reason?: string | null;
  /** Requests sent to Meta (2 = retried) and their HTTP statuses, null where none came back. */
  model_attempts?: number | null;
  model_statuses?: (number | null)[] | null;
  meta_cost_usd?: number | null;
  latency_ms?: number | null;
}

/** Who sent a report: set by the X-Pickfit-Reporter header for our own runs, else external. */
export type Reporter = 'external' | 'eval' | 'demo' | 'dev';

export function reporterFrom(header: string | null): Reporter {
  const value = header?.trim().toLowerCase();
  return value === 'eval' || value === 'demo' || value === 'dev' ? value : 'external';
}

/** rec_id handles are `rec_` + 32 hex; anything else is not ours. */
export const REC_ID = /^rec_[0-9a-f]{32}$/;
/** installed and first_run reports cite a rec_id from the last 7 days. */
export const REC_TTL_DAYS = 7;
/** still_using, replaced and abandoned come weeks later, so their rec_id counts for 120 days. */
export const REC_TTL_LATER_DAYS = 120;

/**
 * For waitUntil: a failed D1 write never fails the response, but it is logged
 * (Workers logs), so a response whose rec_id is missing from events can be found.
 */
export function logFailure(what: string, recId: string | null = null) {
  return (err: unknown) => console.error(JSON.stringify({ event: 'd1_write_failed', what, rec_id: recId, error: String(err) }));
}

export function newId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`;
}

const flag = (value: boolean | null | undefined) => (value === undefined || value === null ? null : value ? 1 : 0);

export async function logEvent(db: D1Database, now: Date, row: EventRow, id = newId('evt')): Promise<string> {
  await db
    .prepare(
      `INSERT INTO events (id, ts, type, rec_id, slug, os, arch, category, need, results, stage, success,
                           satisfied, error_excerpt, replaced_by, note, reporter, client, matched_by, degraded,
                           degraded_reason, model_attempts, model_statuses, meta_cost_usd, latency_ms, last_used)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20, ?21, ?22,
               ?23, ?24, ?25, ?26)`,
    )
    .bind(
      id,
      now.toISOString(),
      row.type,
      row.rec_id ?? null,
      row.slug ?? null,
      row.os ?? null,
      row.arch ?? null,
      row.category ?? null,
      row.need ? JSON.stringify(row.need) : null,
      row.results ? JSON.stringify(row.results) : null,
      row.stage ?? null,
      flag(row.success),
      row.satisfied ?? null,
      row.error_excerpt ?? null,
      row.replaced_by ?? null,
      row.note ?? null,
      row.reporter ?? null,
      row.client ?? null,
      row.matched_by ?? null,
      flag(row.degraded),
      row.degraded_reason ?? null,
      row.model_attempts ?? null,
      row.model_statuses ? JSON.stringify(row.model_statuses) : null,
      row.meta_cost_usd ?? null,
      row.latency_ms ?? null,
      row.last_used ?? null,
    )
    .run();
  return id;
}

export interface IssuedRec {
  type: 'find' | 'alternatives' | 'install_guide';
  os: string | null;
  arch: string | null;
}

/**
 * Did pickfit hand out `slug` under `recId` in the last `ttlDays` days? Either
 * a find_* call that recommended it, or a get_install_guide call for it.
 */
export async function issuedRec(
  db: D1Database,
  now: Date,
  recId: string,
  slug: string,
  ttlDays = REC_TTL_DAYS,
): Promise<IssuedRec | null> {
  if (!REC_ID.test(recId)) return null;
  const since = new Date(now.getTime() - ttlDays * 86_400_000).toISOString();
  const { results } = await db
    .prepare(
      `SELECT type, slug, os, arch, results FROM events
        WHERE rec_id = ?1 AND type IN ('find', 'alternatives', 'install_guide') AND ts >= ?2
        ORDER BY ts DESC`,
    )
    .bind(recId, since)
    .all<{ type: IssuedRec['type']; slug: string | null; os: string | null; arch: string | null; results: string | null }>();
  // Prefer the install guide row: its OS is the one the user installed on.
  const rows = [...results].sort((a, b) => Number(b.type === 'install_guide') - Number(a.type === 'install_guide'));
  for (const row of rows) {
    const gave = row.type === 'install_guide' ? row.slug === slug : (JSON.parse(row.results ?? '[]') as string[]).includes(slug);
    if (gave) return { type: row.type, os: row.os, arch: row.arch };
  }
  return null;
}
