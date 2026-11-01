-- still_using, replaced and abandoned (stage 'still_using') can change back and
-- forth under one rec_id: still_using, then abandoned, then still_using again is
-- three reports, and the latest is the user's state. 0002's index dropped the
-- third as a duplicate of the first, so this stage leaves the index; the Worker
-- dedupes it against the latest report instead (same success and replaced_by).
-- Earlier stages stay once per (rec_id, slug, stage, success).
DROP INDEX events_outcome_once;
CREATE UNIQUE INDEX events_outcome_once ON events(rec_id, slug, stage, success)
  WHERE type = 'outcome' AND stage <> 'still_using';
