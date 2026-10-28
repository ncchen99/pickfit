-- report_outcome is idempotent per (rec_id, slug, stage, success): a failed
-- install followed by a working one under the same rec_id are two reports.
-- 0001 left success out, so the second report was dropped as a duplicate.
DROP INDEX events_outcome_once;
CREATE UNIQUE INDEX events_outcome_once ON events(rec_id, slug, stage, success) WHERE type = 'outcome';
