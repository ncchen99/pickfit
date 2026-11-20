-- Web searches answered by the model, shared by every instance (U4): Cloud Run scales to zero, so the in-memory cache
-- of one instance is often cold. key is a hash of the search (need, conditions, page language) and the index's
-- data_sha256, so new data never serves an old answer. result is the rendered search's JSON (picks and guides), never
-- the visitor's words in plain text beyond what find_software already returns. Rows older than 7 days are deleted on
-- write.
CREATE TABLE search_cache (
  key TEXT PRIMARY KEY,
  result TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX search_cache_created ON search_cache(created_at);
