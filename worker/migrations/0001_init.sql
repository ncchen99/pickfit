-- pickfit D1 tables (architecture E.3 and F.1).
-- No IP addresses anywhere, and no raw user requests: events.need holds only
-- the conditions parsed out of a request, never the user's words.

-- One row per tool call. find_* rows carry the rec_id that report_outcome
-- later cites (valid 7 days); outcome rows store report_outcome's seven
-- stages as (stage, success):
--   installed -> ('installed', 1)      install_failed   -> ('installed', 0)
--   first_run_ok -> ('first_run', 1)   first_run_failed -> ('first_run', 0)
--   still_using -> ('still_using', 1)  replaced, abandoned -> ('still_using', 0)
-- (replaced also sets replaced_by). An outcome without a rec_id is stored
-- once and not counted in scores.
CREATE TABLE events (
  id            TEXT PRIMARY KEY,
  ts            TEXT NOT NULL,                     -- ISO 8601 UTC
  type          TEXT NOT NULL CHECK (type IN ('find', 'alternatives', 'install_guide', 'outcome', 'submit')),
  rec_id        TEXT,
  slug          TEXT,
  os            TEXT CHECK (os IN ('macos', 'linux', 'windows') OR os IS NULL),
  arch          TEXT CHECK (arch IN ('arm64', 'x86_64') OR arch IS NULL),
  category      TEXT,
  need          TEXT CHECK (need IS NULL OR json_valid(need)),        -- parsed conditions only
  results       TEXT CHECK (results IS NULL OR json_valid(results)),  -- recommended slugs
  stage         TEXT CHECK (stage IN ('installed', 'first_run', 'still_using') OR stage IS NULL),
  success       INTEGER CHECK (success IN (0, 1) OR success IS NULL),
  satisfied     INTEGER CHECK (satisfied IN (-1, 0, 1) OR satisfied IS NULL),
  error_excerpt TEXT CHECK (error_excerpt IS NULL OR length(error_excerpt) <= 500),
  replaced_by   TEXT CHECK (replaced_by IS NULL OR length(replaced_by) <= 100),
  note          TEXT CHECK (note IS NULL OR length(note) <= 280),     -- untrusted; never echoed or fed to a model
  reporter      TEXT CHECK (reporter IN ('external', 'eval', 'demo', 'dev') OR reporter IS NULL),
  client        TEXT,                              -- MCP clientInfo.name when known
  matched_by    TEXT,                              -- model id, or 'rules'
  degraded      INTEGER CHECK (degraded IN (0, 1) OR degraded IS NULL),
  meta_cost_usd REAL,
  latency_ms    INTEGER,
  CHECK (type NOT IN ('find', 'alternatives') OR rec_id IS NOT NULL),
  CHECK (type <> 'outcome' OR (slug IS NOT NULL AND stage IS NOT NULL AND success IS NOT NULL))
);
CREATE INDEX events_ts ON events(ts);
CREATE INDEX events_slug_type ON events(slug, type);
CREATE UNIQUE INDEX events_rec ON events(rec_id) WHERE type IN ('find', 'alternatives');
-- Same recommendation, same stage: counted once (report_outcome is idempotent).
CREATE UNIQUE INDEX events_outcome_once ON events(rec_id, slug, stage) WHERE type = 'outcome';

-- submit_software: one row per normalized URL; resubmitting reads the status.
CREATE TABLE submissions (
  id             TEXT PRIMARY KEY,
  url            TEXT NOT NULL UNIQUE,
  status         TEXT NOT NULL CHECK (status IN ('queued', 'reading', 'verifying', 'listed', 'listed_unverified', 'rejected')),
  submitter_role TEXT NOT NULL DEFAULT 'unknown' CHECK (submitter_role IN ('author', 'user', 'unknown')),
  note           TEXT CHECK (note IS NULL OR length(note) <= 300),    -- untrusted; for human review only
  slug           TEXT,
  reason         TEXT CHECK (reason IS NULL OR length(reason) <= 300),
  submitted_at   TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX submissions_status ON submissions(status, submitted_at);

-- Failed installs reported with an error wait here for the verification agent.
CREATE TABLE reverify_queue (
  slug           TEXT NOT NULL,
  os             TEXT NOT NULL CHECK (os IN ('macos', 'linux', 'windows')),
  reason         TEXT NOT NULL,
  first_event_id TEXT NOT NULL,
  queued_at      TEXT NOT NULL,
  done_at        TEXT,
  PRIMARY KEY (slug, os)
);

-- The Worker's own Meta spend, per UTC day (separate from the pipeline's
-- ledger). find_* checks the daily and the total cap here before calling the
-- model and falls back to rules ranking (degraded) when either is reached.
CREATE TABLE meta_budget (
  day      TEXT PRIMARY KEY,                        -- YYYY-MM-DD (UTC)
  calls    INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0
);
