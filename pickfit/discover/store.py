"""The candidate store: runs/pipeline.db (SQLite, not in git).

One row per repository, keyed by `gh:<GitHub numeric repo id>` so a rename does
not create a second candidate; earlier owner/name pairs go to `aliases`
(architecture A.4). Each stage of the funnel writes its own columns or table:
discovery (repo snapshot, which queries found it; for a channel other than GitHub
search, such as Show HN, one `channel_hits` row per post), details (README,
releases, files), rules (label and reasons), extraction (one row per model call).
Nothing here is the canonical data; data/software/ is written later from these rows.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now

# A repo found by queries of several categories goes to the most specific one: an MCP server
# that also has a CLI mode is listed as an MCP server.
CATEGORY_PRIORITY = ("mcp_server", "local_ai", "dev_cli")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    repo_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL,
    categories TEXT NOT NULL DEFAULT '[]',
    queries TEXT NOT NULL DEFAULT '[]',
    repo TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    readme TEXT,
    readme_path TEXT,
    releases TEXT,
    files TEXT,
    files_truncated INTEGER,
    manifests TEXT,
    details_at TEXT,
    details_pushed_at TEXT,
    details_error TEXT,
    rule_label TEXT,
    rule_passed INTEGER,
    rule_reasons TEXT,
    rules_version TEXT,
    rules_at TEXT
);
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    category TEXT NOT NULL,
    q TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    total_count INTEGER,
    returned INTEGER NOT NULL,
    new INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id TEXT NOT NULL REFERENCES candidates (repo_id),
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    status TEXT NOT NULL,
    sources_sha TEXT NOT NULL,
    result TEXT,
    quote_failures TEXT NOT NULL DEFAULT '[]',
    quotes_checked INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    usage TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    response_id TEXT,
    latency_s REAL
);
CREATE INDEX IF NOT EXISTS extractions_repo ON extractions (repo_id, id);
CREATE TABLE IF NOT EXISTS prescreens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id TEXT NOT NULL REFERENCES candidates (repo_id),
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    status TEXT NOT NULL,
    sources_sha TEXT NOT NULL,
    result TEXT,
    keep INTEGER,
    review_reason TEXT,
    error TEXT,
    usage TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_s REAL
);
CREATE INDEX IF NOT EXISTS prescreens_repo ON prescreens (repo_id, role, id);
CREATE TABLE IF NOT EXISTS channel_hits (
    channel TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_url TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT,
    points INTEGER,
    comments INTEGER,
    posted_at TEXT NOT NULL,
    linked_repo TEXT,
    repo_id TEXT,
    categories TEXT NOT NULL DEFAULT '[]',
    outcome TEXT NOT NULL,
    known_before INTEGER,
    run_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (channel, item_id)
);
CREATE INDEX IF NOT EXISTS channel_hits_repo ON channel_hits (repo_id);
"""


def _loads(text: str | None, default: Any = None) -> Any:
    return json.loads(text) if text else default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def repo_key(repo_id: int) -> str:
    """Primary key for a GitHub repository; the URL is only a temporary key (A.4)."""
    if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
        raise ValueError(f"GitHub repo id must be a positive int, got {repo_id!r}")
    return f"gh:{repo_id}"


class PipelineDB:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- discovery

    def upsert_repo(self, repo: dict[str, Any], *, category: str, query_id: str,
                    seen_at: str | None = None) -> bool:
        """Insert or refresh one repo; True when it is new. A changed owner/name becomes an alias."""
        key = repo_key(repo["id"])
        now = seen_at or taipei_now().isoformat(timespec="seconds")
        with self._write() as conn:
            row = conn.execute("SELECT full_name, aliases, categories, queries FROM candidates "
                               "WHERE repo_id = ?", (key,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO candidates (repo_id, full_name, category, categories, queries, repo, "
                    "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, repo["full_name"], category, _dumps([category]), _dumps([query_id]),
                     _dumps(repo), now, now))
                return True
            aliases = _loads(row["aliases"], [])
            if row["full_name"] != repo["full_name"] and row["full_name"] not in aliases:
                aliases.append(row["full_name"])
            categories = _loads(row["categories"], [])
            if category not in categories:
                categories.append(category)
            queries = _loads(row["queries"], [])
            if query_id not in queries:
                queries.append(query_id)
            conn.execute(
                "UPDATE candidates SET full_name = ?, aliases = ?, category = ?, categories = ?, "
                "queries = ?, repo = ?, last_seen_at = ? WHERE repo_id = ?",
                (repo["full_name"], _dumps([a for a in aliases if a != repo["full_name"]]),
                 _preferred(categories), _dumps(categories), _dumps(queries), _dumps(repo), now, key))
            return False

    def names_index(self) -> dict[str, str]:
        """Lowercased current and earlier owner/name of every candidate -> its repo_id."""
        with self._connect() as conn:
            rows = conn.execute("SELECT repo_id, full_name, aliases FROM candidates").fetchall()
        out: dict[str, str] = {}
        for row in rows:
            for name in _loads(row["aliases"], []):
                out.setdefault(name.lower(), row["repo_id"])
        for row in rows:  # a current name wins over someone's earlier name
            out[row["full_name"].lower()] = row["repo_id"]
        return out

    def save_channel_hit(self, *, channel: str, post: Any, repo_id: str | None, outcome: str,
                         known_before: bool | None, run_id: str, seen_at: str | None = None) -> None:
        """Record one post of a channel (Show HN) and what became of it; a post seen again is
        refreshed (points, comments, outcome) but keeps whether its repo was known at first sight."""
        now = seen_at or taipei_now().isoformat(timespec="seconds")
        with self._write() as conn:
            conn.execute(
                "INSERT INTO channel_hits (channel, item_id, item_url, title, link, points, comments, posted_at, "
                "linked_repo, repo_id, categories, outcome, known_before, run_id, first_seen_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (channel, item_id) DO UPDATE SET points = excluded.points, "
                "comments = excluded.comments, linked_repo = excluded.linked_repo, repo_id = excluded.repo_id, "
                "categories = excluded.categories, outcome = excluded.outcome, run_id = excluded.run_id, "
                "last_seen_at = excluded.last_seen_at",
                (channel, post.item_id, post.hn_url, post.title, post.link, post.points, post.comments,
                 post.posted_at, post.repo, repo_id, _dumps(post.categories), outcome,
                 None if known_before is None else int(known_before), run_id, now, now))

    def channel_hits(self, channel: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM channel_hits WHERE ? IS NULL OR channel = ? "
                                "ORDER BY posted_at, item_id", (channel, channel)).fetchall()
        out = []
        for row in rows:
            hit = dict(row)
            hit["categories"] = _loads(hit["categories"], [])
            if hit["known_before"] is not None:
                hit["known_before"] = bool(hit["known_before"])
            out.append(hit)
        return out

    def log_query(self, *, run_id: str, query_id: str, category: str, q: str, ran_at: str,
                  total_count: int | None, returned: int, new: int) -> None:
        with self._write() as conn:
            conn.execute(
                "INSERT INTO queries (run_id, query_id, category, q, ran_at, total_count, returned, new) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, query_id, category, q, ran_at, total_count, returned, new))

    # -- details

    def needs_details(self) -> list[dict[str, Any]]:
        """Repos never fetched, fetched with an error, or pushed since the last fetch."""
        with self._connect() as conn:
            rows = conn.execute("SELECT repo_id, repo, details_at, details_pushed_at, details_error "
                                "FROM candidates ORDER BY first_seen_at, repo_id").fetchall()
        out = []
        for row in rows:
            repo = _loads(row["repo"])
            if (row["details_at"] is None or row["details_error"]
                    or row["details_pushed_at"] != repo.get("pushed_at")):
                out.append({"repo_id": row["repo_id"], **repo})
        return out

    def save_details(self, repo_id: str, details: dict[str, Any] | None, *, pushed_at: str | None,
                     error: str | None = None) -> None:
        now = taipei_now().isoformat(timespec="seconds")
        with self._write() as conn:
            if details is None:
                conn.execute("UPDATE candidates SET details_at = ?, details_error = ? WHERE repo_id = ?",
                             (now, error or "unknown error", repo_id))
                return
            conn.execute(
                "UPDATE candidates SET readme = ?, readme_path = ?, releases = ?, files = ?, "
                "files_truncated = ?, manifests = ?, details_at = ?, details_pushed_at = ?, "
                "details_error = NULL WHERE repo_id = ?",
                (details["readme"], details["readme_path"], _dumps(details["releases"]),
                 _dumps(details["files"]), int(details["files_truncated"]),
                 _dumps(details["manifests"]), now, pushed_at, repo_id))

    # -- rules

    def save_rules(self, repo_id: str, *, label: str, passed: bool, reasons: list[str],
                   version: str) -> None:
        with self._write() as conn:
            conn.execute(
                "UPDATE candidates SET rule_label = ?, rule_passed = ?, rule_reasons = ?, "
                "rules_version = ?, rules_at = ? WHERE repo_id = ?",
                (label, int(passed), _dumps(reasons), version,
                 taipei_now().isoformat(timespec="seconds"), repo_id))

    # -- reading candidates

    def candidate(self, repo_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM candidates WHERE repo_id = ?", (repo_id,)).fetchone()
        return _row_to_candidate(row) if row else None

    def candidates(self, where: str = "", params: tuple = ()) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM candidates {where} ORDER BY first_seen_at, repo_id",
                                params).fetchall()
        return [_row_to_candidate(row) for row in rows]

    # -- extraction

    def last_extraction(self, repo_id: str, model: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM extractions WHERE repo_id = ? AND model = ? "
                               "ORDER BY id DESC LIMIT 1", (repo_id, model)).fetchone()
        return _row_to_extraction(row) if row else None

    def save_extraction(self, *, repo_id: str, run_id: str, model: str, reasoning_effort: str,
                        status: str, sources_sha: str, result: dict[str, Any] | None,
                        quote_failures: list[dict[str, Any]], quotes_checked: int,
                        error: str | None, usage: dict[str, Any] | None, cost_usd: float,
                        cache_hit: bool, response_id: str | None, latency_s: float | None) -> int:
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO extractions (repo_id, run_id, created_at, model, reasoning_effort, status, "
                "sources_sha, result, quote_failures, quotes_checked, error, usage, cost_usd, cache_hit, "
                "response_id, latency_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (repo_id, run_id, taipei_now().isoformat(timespec="seconds"), model, reasoning_effort,
                 status, sources_sha, _dumps(result) if result is not None else None,
                 _dumps(quote_failures), quotes_checked, error,
                 _dumps(usage) if usage is not None else None, cost_usd, int(cache_hit),
                 response_id, latency_s))
            return int(cur.lastrowid)

    def extractions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM extractions ORDER BY id").fetchall()
        return [_row_to_extraction(row) for row in rows]

    # -- prescreen

    def save_prescreen(self, *, repo_id: str, run_id: str, role: str, provider: str, model: str,
                       reasoning_effort: str, status: str, sources_sha: str,
                       result: dict[str, Any] | None, keep: bool | None, review_reason: str | None,
                       error: str | None, usage: dict[str, Any] | None, cost_usd: float,
                       latency_s: float | None) -> int:
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO prescreens (repo_id, run_id, created_at, role, provider, model, "
                "reasoning_effort, status, sources_sha, result, keep, review_reason, error, usage, "
                "cost_usd, latency_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (repo_id, run_id, taipei_now().isoformat(timespec="seconds"), role, provider, model,
                 reasoning_effort, status, sources_sha, _dumps(result) if result is not None else None,
                 None if keep is None else int(keep), review_reason, error,
                 _dumps(usage) if usage is not None else None, cost_usd, latency_s))
            return int(cur.lastrowid)

    def prescreens(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM prescreens ORDER BY id").fetchall()
        return [_row_to_prescreen(row) for row in rows]

    def prescreen_decisions(self) -> dict[str, dict[str, Any]]:
        """Latest usable screen and review per repo, and the decision they add up to.

        A review overrides the screen. Only rows with a parsed answer count; a repo whose
        calls all failed has no decision and is treated as not screened.
        """
        latest: dict[str, dict[str, dict[str, Any]]] = {}
        for p in self.prescreens():
            if p["status"] == "ok":
                latest.setdefault(p["repo_id"], {})[p["role"]] = p
        out = {}
        for repo_id, roles in latest.items():
            final = roles.get("review") or roles.get("screen")
            out[repo_id] = {"screen": roles.get("screen"), "review": roles.get("review"),
                            "keep": final["keep"], "decided_by": final["role"],
                            "sources_sha": final["sources_sha"]}
        return out

    # -- funnel

    def funnel(self, prescreen: dict[str, Any] | None = None) -> dict[str, Any]:
        """Counts, models and cost per funnel stage (discover -> rules -> prescreen -> extract).

        With no prescreen rows, `prescreen` (from the caller) says why it did not run.
        """
        cands = self.candidates()
        with self._connect() as conn:
            queries = [dict(r) for r in conn.execute(
                "SELECT query_id, q, ran_at, total_count, returned, new FROM queries "
                "WHERE id IN (SELECT MAX(id) FROM queries GROUP BY query_id) ORDER BY query_id")]
        detailed = [c for c in cands if c["details_at"] and not c["details_error"]]
        ruled = [c for c in cands if c["rule_label"] is not None]
        reasons: Counter[str] = Counter()
        for c in ruled:
            if not c["rule_passed"]:
                reasons.update(r.split("(")[0] for r in c["rule_reasons"] if r.startswith("reject:"))
        latest: dict[str, dict[str, Any]] = {}
        all_extractions = self.extractions()
        for e in all_extractions:
            latest[e["repo_id"]] = e
        tokens: Counter[str] = Counter()  # billed only: a cache hit replays an old usage block
        cost_by_model: Counter[str] = Counter()
        for e in all_extractions:
            cost_by_model[e["model"]] += e["cost_usd"]
            if not e["cache_hit"]:
                tokens.update({k: v for k, v in (e["usage"] or {}).items() if isinstance(v, int)})
        latest_by_model: dict[str, dict[str, dict[str, Any]]] = {}
        for e in all_extractions:
            latest_by_model.setdefault(e["model"], {})[e["repo_id"]] = e
        hits = [h for h in self.channel_hits() if h["outcome"] == "candidate"]
        return {
            "discover": {
                "candidates": len(cands),
                "by_category": dict(Counter(c["category"] for c in cands)),
                # A candidate found by any query of a channel; GitHub search ids are <category>:<topic>.
                "by_channel": dict(Counter(ch for c in cands for ch in sorted(_channels(c["queries"])))),
                "channel_posts": {ch: {"posts": sum(1 for h in hits if h["channel"] == ch),
                                       "repos": len({h["repo_id"] for h in hits if h["channel"] == ch}),
                                       "repos_new": len({h["repo_id"] for h in hits
                                                         if h["channel"] == ch and h["known_before"] is False})}
                                  for ch in sorted({h["channel"] for h in hits})},
                "in_both_categories": sum(1 for c in cands if len(c["categories"]) > 1),
                "renamed": sum(1 for c in cands if c["aliases"]),
                "queries": queries,
                "model": None,
                "cost_usd": 0.0,
            },
            "details": {
                "fetched": len(detailed),
                "errors": sum(1 for c in cands if c["details_error"]),
                "with_readme": sum(1 for c in detailed if c["readme"]),
                "with_release": sum(1 for c in detailed if c["releases"]),
                "model": None,
                "cost_usd": 0.0,
            },
            "rules": {
                "checked": len(ruled),
                "passed": sum(1 for c in ruled if c["rule_passed"]),
                "by_label": dict(Counter(c["rule_label"] for c in ruled)),
                "reject_reasons": dict(reasons.most_common()),
                "passed_by_category": dict(Counter(c["category"] for c in ruled if c["rule_passed"])),
                "model": None,
                "cost_usd": 0.0,
            },
            "prescreen": self._prescreen_funnel() or prescreen
                         or {"status": "not_run", "model": None, "cost_usd": 0.0},
            "extract": {
                "candidates": len(latest),
                "calls": len(all_extractions),
                "by_status": dict(Counter(e["status"] for e in latest.values())),
                "models": dict(Counter(e["model"] for e in all_extractions)),
                "cache_hits": sum(1 for e in all_extractions if e["cache_hit"]),
                "tokens": dict(tokens),
                "cost_usd": round(sum(e["cost_usd"] for e in all_extractions), 6),
                "by_model": {model: {"candidates": len(rows),
                                     "by_status": dict(Counter(e["status"] for e in rows.values())),
                                     "cost_usd": round(cost_by_model[model], 6)}
                             for model, rows in sorted(latest_by_model.items())},
            },
        }


    def _prescreen_funnel(self) -> dict[str, Any] | None:
        rows = self.prescreens()
        if not rows:
            return None
        decisions = self.prescreen_decisions()
        cost_by_model: Counter[str] = Counter()
        tokens: Counter[str] = Counter()
        for p in rows:
            cost_by_model[p["model"]] += p["cost_usd"]
            tokens.update({k: v for k, v in (p["usage"] or {}).items() if isinstance(v, int)})
        both = [d for d in decisions.values() if d["screen"] and d["review"]]
        agree = sum(1 for d in both if d["screen"]["keep"] == d["review"]["keep"])
        sampled = [d for d in both if d["review"]["review_reason"] == "sample"]
        sample_agree = sum(1 for d in sampled if d["screen"]["keep"] == d["review"]["keep"])
        return {
            "status": "ran",
            "screened": sum(1 for d in decisions.values() if d["screen"]),
            "kept": sum(1 for d in decisions.values() if d["keep"]),
            "rejected": sum(1 for d in decisions.values() if not d["keep"]),
            "decided_by": dict(Counter(d["decided_by"] for d in decisions.values())),
            "reviewed": len(both),
            "review_reasons": dict(Counter(d["review"]["review_reason"] for d in both)),
            "review_overturned": len(both) - agree,
            # The random sample is the unbiased agreement figure; reviews of low-confidence
            # screens disagree more by design.
            "sample_agreement": {"n": len(sampled), "agree": sample_agree,
                                 "rate": round(sample_agree / len(sampled), 3) if sampled else None},
            "calls": len(rows),
            "by_status": dict(Counter(p["status"] for p in rows)),
            "models": dict(Counter(p["model"] for p in rows)),
            "tokens": dict(tokens),
            "cost_by_model": {m: round(c, 6) for m, c in sorted(cost_by_model.items())},
            "cost_usd": round(sum(p["cost_usd"] for p in rows), 6),
        }


_CHANNEL_PREFIXES = ("show_hn", "submission", "reverify")


def _channels(query_ids: list[str]) -> set[str]:
    """Which channels found a candidate, from its query ids: `show_hn:<category>`,
    `submission:<id>`, `reverify:<id>`, or GitHub search's `<category>:<topic>`."""
    return {q.split(":", 1)[0] if q.split(":", 1)[0] in _CHANNEL_PREFIXES else "github_search"
            for q in query_ids}


def _preferred(categories: list[str]) -> str:
    ranked = [c for c in CATEGORY_PRIORITY if c in categories]
    return ranked[0] if ranked else categories[0]


def _row_to_candidate(row: sqlite3.Row) -> dict[str, Any]:
    c = dict(row)
    for key, default in (("aliases", []), ("categories", []), ("queries", []), ("repo", {}),
                         ("releases", []), ("files", []), ("manifests", {}), ("rule_reasons", [])):
        c[key] = _loads(c[key], default)
    if c["rule_passed"] is not None:
        c["rule_passed"] = bool(c["rule_passed"])
    return c


def _row_to_extraction(row: sqlite3.Row) -> dict[str, Any]:
    e = dict(row)
    e["result"] = _loads(e["result"])
    e["quote_failures"] = _loads(e["quote_failures"], [])
    e["usage"] = _loads(e["usage"])
    e["cache_hit"] = bool(e["cache_hit"])
    return e


def _row_to_prescreen(row: sqlite3.Row) -> dict[str, Any]:
    p = dict(row)
    p["result"] = _loads(p["result"])
    p["usage"] = _loads(p["usage"])
    if p["keep"] is not None:
        p["keep"] = bool(p["keep"])
    return p
