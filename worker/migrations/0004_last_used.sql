-- report_outcome's coarse last_used for still_using, replaced and abandoned:
-- roughly when the tool was last used, from an agent-run local check (macOS
-- kMDItemLastUsedDate for an app) or the user's own answer. Never an exact
-- time and never anything about other software; null for the earlier stages.
ALTER TABLE events ADD COLUMN last_used TEXT
  CHECK (last_used IN ('this_week', 'this_month', 'older', 'unknown') OR last_used IS NULL);
