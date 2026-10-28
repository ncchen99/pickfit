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
  client?: string | null;
  matched_by?: string | null;
  degraded?: boolean | null;
  meta_cost_usd?: number | null;
  latency_ms?: number | null;
}

export function newId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`;
}

export async function logEvent(db: D1Database, now: Date, row: EventRow): Promise<string> {
  const id = newId('evt');
  await db
    .prepare(
      `INSERT INTO events (id, ts, type, rec_id, slug, os, arch, category, need, results, client,
                           matched_by, degraded, meta_cost_usd, latency_ms)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)`,
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
      row.client ?? null,
      row.matched_by ?? null,
      row.degraded === undefined || row.degraded === null ? null : row.degraded ? 1 : 0,
      row.meta_cost_usd ?? null,
      row.latency_ms ?? null,
    )
    .run();
  return id;
}
