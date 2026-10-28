/**
 * submit_software (architecture E.3): queue a GitHub repository for the
 * pipeline (`pickfit watch` reads D1 submissions, P5.2). The Worker only
 * checks and normalizes the URL; it fetches nothing. One row per repository,
 * so submitting again reads the status. New submissions are capped per hour
 * across everyone (there is no per-user key: pickfit stores no IP).
 */
import type { Catalog } from './catalog.ts';
import { logEvent, logFailure, newId } from './events.ts';
import { scrubHead } from './scrub.ts';

export interface SubmitInput {
  url: string;
  submitter_role?: 'author' | 'user' | 'unknown';
  note?: string;
}

export type SubmissionStatus = 'queued' | 'reading' | 'verifying' | 'listed' | 'listed_unverified' | 'rejected';

export interface SubmitOutput {
  submission_id: string | null;
  url: string;
  status: SubmissionStatus;
  slug: string | null;
  reason: string | null;
  already_submitted: boolean;
  check_again_after_s: number | null;
  next: string;
}

export class SubmitError extends Error {}

export const NOTE_MAX = 300;

/** First path segments of github.com that are not user or organization names. */
const NOT_OWNERS = new Set(
  'about apps blog collections contact customer-stories enterprise events explore features github-copilot issues login marketplace new notifications orgs organizations pricing pulls readme search security settings site sponsors topics trending users'.split(
    ' ',
  ),
);

const GITHUB_REPO = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]{1,100})(?:[/?#].*)?$/i;

/** https://github.com/<owner>/<repo>, lower case, or null when the URL is not a repository on github.com. */
export function normalizeRepoUrl(url: string): string | null {
  const match = GITHUB_REPO.exec(url.trim());
  if (!match) return null;
  const owner = match[1].toLowerCase();
  const repo = match[2].replace(/\.git$/i, '').toLowerCase();
  if (NOT_OWNERS.has(owner) || repo === '' || /^\.+$/.test(repo)) return null;
  return `https://github.com/${owner}/${repo}`;
}

const WAIT_S: Partial<Record<SubmissionStatus, number>> = { queued: 120, reading: 120, verifying: 300 };

const NEXT: Record<SubmissionStatus, string> = {
  queued: 'Queued. pickfit will read the README with Muse Spark, then try the install in a sandbox. Call again with the same url to check.',
  reading: 'Muse Spark is reading the repository. Call again with the same url to check.',
  verifying: 'pickfit is installing it in a sandbox. Call again with the same url to check.',
  listed: 'Listed: find_software can recommend it when it fits a request.',
  listed_unverified: 'Listed without a verified install: pickfit could not finish its install, so find_software does not recommend it yet.',
  rejected: 'Not listed; reason says why. Submitting the same url again only reads this status.',
};

interface Row {
  id: string;
  status: SubmissionStatus;
  slug: string | null;
  reason: string | null;
}

function output(row: Row, url: string, already: boolean): SubmitOutput {
  return {
    submission_id: row.id,
    url,
    status: row.status,
    slug: row.slug,
    reason: row.reason,
    already_submitted: already,
    check_again_after_s: WAIT_S[row.status] ?? null,
    next: NEXT[row.status],
  };
}

export interface SubmitDeps {
  catalog: Catalog;
  db: D1Database;
  now: () => Date;
  hourlyCap: number;
  client?: string | null;
}

export async function submitSoftware(input: SubmitInput, deps: SubmitDeps): Promise<SubmitOutput> {
  const url = normalizeRepoUrl(input.url);
  if (!url) {
    throw new SubmitError('pickfit accepts only GitHub repository URLs, like https://github.com/owner/repo.');
  }
  const now = deps.now();
  const log = (status: string, slug: string | null) =>
    logEvent(deps.db, now, { type: 'submit', slug, results: [status], client: deps.client ?? null }).catch(logFailure('submit'));

  const listed = deps.catalog.entries.find((entry) => normalizeRepoUrl(entry.repo_url) === url);
  if (listed) {
    await log('listed', listed.slug);
    return {
      submission_id: null,
      url,
      status: 'listed',
      slug: listed.slug,
      reason: null,
      already_submitted: true,
      check_again_after_s: null,
      next: NEXT.listed,
    };
  }

  const existing = await deps.db
    .prepare('SELECT id, status, slug, reason FROM submissions WHERE url = ?1')
    .bind(url)
    .first<Row>();
  if (existing) {
    await log(existing.status, existing.slug);
    return output(existing, url, true);
  }

  const hourAgo = new Date(now.getTime() - 3_600_000).toISOString();
  const recent = await deps.db
    .prepare('SELECT count(*) AS n FROM submissions WHERE submitted_at >= ?1')
    .bind(hourAgo)
    .first<{ n: number }>();
  if ((recent?.n ?? 0) >= deps.hourlyCap) {
    throw new SubmitError('pickfit has taken as many new submissions as it can this hour. Try again in an hour.');
  }

  const row: Row = { id: newId('sub'), status: 'queued', slug: null, reason: null };
  try {
    await deps.db
      .prepare(
        `INSERT INTO submissions (id, url, status, submitter_role, note, submitted_at, updated_at)
         VALUES (?1, ?2, 'queued', ?3, ?4, ?5, ?5)`,
      )
      // The note is untrusted: stored for people to read, never echoed or fed to a model.
      .bind(row.id, url, input.submitter_role ?? 'unknown', scrubHead(input.note, NOTE_MAX), now.toISOString())
      .run();
  } catch (err) {
    if (!/UNIQUE/i.test(String(err))) throw err;
    // Someone submitted the same repository a moment ago.
    const raced = await deps.db.prepare('SELECT id, status, slug, reason FROM submissions WHERE url = ?1').bind(url).first<Row>();
    if (raced) return output(raced, url, true);
    throw err;
  }
  await log('queued', null);
  return output(row, url, false);
}
