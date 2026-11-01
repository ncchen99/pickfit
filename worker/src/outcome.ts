/**
 * report_outcome (architecture E.3): one events row per (rec_id, slug, stage).
 * A report counts toward the score only when it cites a rec_id pickfit issued
 * for that slug in the last 7 days (installed, first_run), or 120 days for the
 * later stages (still_using, replaced, abandoned); then the row keeps the rec_id (so
 * `rec_id IS NOT NULL` means counted), otherwise it is stored once with
 * rec_id null. A failed install or first run with an error excerpt queues a
 * fresh sandbox re-run for that slug and OS. No model call.
 */
import type { Catalog, OS } from './catalog.ts';
import { issuedRec, logEvent, newId, REC_TTL_DAYS, REC_TTL_LATER_DAYS, type Reporter } from './events.ts';
import { scrubHead, scrubTail } from './scrub.ts';

export const STAGES = [
  'installed',
  'install_failed',
  'first_run_ok',
  'first_run_failed',
  'still_using',
  'replaced',
  'abandoned',
] as const;
export type Stage = (typeof STAGES)[number];

/** The seven reported stages as stored (stage, success); see migrations/0001_init.sql. */
export const STORED: Record<Stage, ['installed' | 'first_run' | 'still_using', boolean]> = {
  installed: ['installed', true],
  install_failed: ['installed', false],
  first_run_ok: ['first_run', true],
  first_run_failed: ['first_run', false],
  still_using: ['still_using', true],
  replaced: ['still_using', false],
  abandoned: ['still_using', false],
};

/** Stages reported weeks after install; their rec_id counts for REC_TTL_LATER_DAYS. */
export const LATER_STAGES: readonly Stage[] = ['still_using', 'replaced', 'abandoned'];

const SATISFIED = { satisfied: 1, neutral: 0, dissatisfied: -1, unknown: null } as const;

/** Roughly when the tool was last used; never an exact time. */
export const LAST_USED = ['this_week', 'this_month', 'older', 'unknown'] as const;
export type LastUsed = (typeof LAST_USED)[number];

export const ERROR_EXCERPT_MAX = 500;
export const NOTE_MAX = 280;

export interface OutcomeInput {
  slug: string;
  stage: Stage;
  rec_id?: string;
  satisfaction?: keyof typeof SATISFIED;
  os?: OS;
  arch?: 'arm64' | 'x86_64';
  error_excerpt?: string;
  replaced_by?: string;
  note?: string;
  /** still_using, replaced and abandoned only; ignored for the earlier stages. */
  last_used?: LastUsed;
}

export interface OutcomeOutput {
  accepted: true;
  report_id: string;
  rec_id: string | null;
  deduplicated: boolean;
  counted_in_score: boolean;
  not_counted_reason: 'no_rec_id' | 'unknown_or_expired_rec_id' | null;
  reverify: 'queued' | 'already_queued' | 'none';
  next: string | null;
}

export class UnknownToolError extends Error {}

export interface OutcomeDeps {
  catalog: Catalog;
  db: D1Database;
  now: () => Date;
  reporter: Reporter;
  client?: string | null;
}

async function queueReverify(db: D1Database, now: Date, slug: string, os: string, reason: string, eventId: string) {
  // A pending re-run stays as it is; a finished one is queued again.
  const result = await db
    .prepare(
      `INSERT INTO reverify_queue (slug, os, reason, first_event_id, queued_at) VALUES (?1, ?2, ?3, ?4, ?5)
       ON CONFLICT(slug, os) DO UPDATE SET reason = excluded.reason, first_event_id = excluded.first_event_id,
                                           queued_at = excluded.queued_at, done_at = NULL
       WHERE reverify_queue.done_at IS NOT NULL`,
    )
    .bind(slug, os, reason, eventId, now.toISOString())
    .run();
  return (result.meta.changes ?? 0) > 0 ? 'queued' : 'already_queued';
}

function nextHint(input: OutcomeInput, failed: boolean): string | null {
  if (failed || input.stage === 'abandoned' || input.stage === 'replaced') {
    return `If the user still needs a tool for this job, call find_software or find_alternatives with exclude: ["${input.slug}"].`;
  }
  if (input.stage === 'installed') return 'After the first real use, report first_run_ok or first_run_failed.';
  return null;
}

export async function reportOutcome(input: OutcomeInput, deps: OutcomeDeps): Promise<OutcomeOutput> {
  if (!deps.catalog.bySlug.has(input.slug)) {
    throw new UnknownToolError(`Unknown slug "${input.slug}". Report only tools pickfit returned.`);
  }
  const now = deps.now();
  const [stage, success] = STORED[input.stage];
  const failed = input.stage === 'install_failed' || input.stage === 'first_run_failed';

  const later = LATER_STAGES.includes(input.stage);
  const ttl = later ? REC_TTL_LATER_DAYS : REC_TTL_DAYS;
  const rec = input.rec_id ? await issuedRec(deps.db, now, input.rec_id, input.slug, ttl) : null;
  const recId = rec ? input.rec_id! : null;
  if (recId) {
    const existing = await deps.db
      .prepare(`SELECT id FROM events WHERE type = 'outcome' AND rec_id = ?1 AND slug = ?2 AND stage = ?3 AND success = ?4`)
      .bind(recId, input.slug, stage, success ? 1 : 0)
      .first<{ id: string }>();
    if (existing) return dedupe(existing.id, recId, input, failed);
  }

  const os = input.os ?? (rec?.os as OS | null) ?? null;
  const errorExcerpt = scrubTail(input.error_excerpt, ERROR_EXCERPT_MAX);
  const id = newId('evt');
  try {
    await logEvent(
      deps.db,
      now,
      {
        type: 'outcome',
        rec_id: recId,
        slug: input.slug,
        os,
        arch: input.arch ?? rec?.arch ?? null,
        stage,
        success,
        satisfied: SATISFIED[input.satisfaction ?? 'unknown'],
        error_excerpt: errorExcerpt,
        replaced_by: input.stage === 'replaced' ? scrubHead(input.replaced_by, 100) : null,
        // Untrusted text: stored for people to read, never echoed or fed to a model.
        note: scrubHead(input.note, NOTE_MAX),
        last_used: later ? (input.last_used ?? null) : null,
        reporter: deps.reporter,
        client: deps.client ?? null,
      },
      id,
    );
  } catch (err) {
    // Two identical reports racing: the unique index kept the first one.
    if (recId && /UNIQUE/i.test(String(err))) return dedupe(null, recId, input, failed);
    throw err;
  }

  let reverify: OutcomeOutput['reverify'] = 'none';
  if (failed && recId && os && errorExcerpt) {
    reverify = await queueReverify(deps.db, now, input.slug, os, input.stage, id);
  }
  return {
    accepted: true,
    report_id: id,
    rec_id: recId,
    deduplicated: false,
    counted_in_score: recId !== null,
    not_counted_reason: recId ? null : input.rec_id ? 'unknown_or_expired_rec_id' : 'no_rec_id',
    reverify,
    next: nextHint(input, failed),
  };
}

function dedupe(id: string | null, recId: string, input: OutcomeInput, failed: boolean): OutcomeOutput {
  return {
    accepted: true,
    report_id: id ?? 'duplicate',
    rec_id: recId,
    deduplicated: true,
    counted_in_score: true, // the first report of this stage counts, once
    not_counted_reason: null,
    reverify: 'none',
    next: nextHint(input, failed),
  };
}
