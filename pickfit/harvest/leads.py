"""Leads: one row per GitHub repository or web address, one source row per place that named it.

Keys: `gh:<owner>/<name>` (lower case) for a repository, `web:<normalized https URL>` for a site.
Only facts are kept from a source: its item id, the link back, a short title and one number that
says how much attention the item has (stars, points, installs, downloads). Never post text.
"""

from __future__ import annotations

import bisect
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pickfit.discover.listings import github_repo
from pickfit.ledger import taipei_now
from pickfit.web_intake import normalize_web_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  key          TEXT PRIMARY KEY,
  url          TEXT NOT NULL,
  kind_hint    TEXT NOT NULL DEFAULT 'unknown',
  platforms    TEXT NOT NULL DEFAULT '[]',
  status       TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'known', 'fed', 'skipped')),
  status_note  TEXT,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_status ON leads(status);
CREATE TABLE IF NOT EXISTS lead_sources (
  key       TEXT NOT NULL,
  source    TEXT NOT NULL,
  item_id   TEXT NOT NULL,
  title     TEXT,
  link      TEXT,
  signal    REAL,
  seen_at   TEXT NOT NULL,
  PRIMARY KEY (key, source, item_id)
);
CREATE TABLE IF NOT EXISTS runs (
  run_id   TEXT NOT NULL,
  source   TEXT NOT NULL,
  started  TEXT NOT NULL,
  finished TEXT,
  hits     INTEGER,
  new      INTEGER,
  requests INTEGER,
  error    TEXT,
  PRIMARY KEY (run_id, source)
);
CREATE TABLE IF NOT EXISTS state (
  name  TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

# What the 11/15 strategy puts first (CLAUDE.md): Linux, CLI, MCP and web; desktop GUI on macOS or
# Windows only after them. A lead's base priority; attention and agreeing sources add to it.
KIND_PRIORITY = {"mcp_server": 3.0, "cli_tool": 3.0, "tui": 3.0, "web_app": 3.0, "self_hosted_web_app": 2.5,
                 "server_daemon": 2.0, "local_ai": 2.5, "desktop_app": 1.5, "unknown": 1.0}
KINDS = tuple(KIND_PRIORITY)
PLATFORMS = ("linux", "macos", "windows", "web")
TITLE_MAX = 160


@dataclass
class Hit:
    """One source naming one piece of software."""
    source: str
    item_id: str
    urls: list[str]  # where to look for a GitHub repository or a site, best first
    title: str | None = None
    link: str | None = None  # back to the source's page for the item
    signal: float | None = None
    kind_hint: str = "unknown"
    platforms: list[str] = field(default_factory=list)
    allow_web: bool = False  # take a site when no repository is named (web app sources only)

    def key_url(self) -> tuple[str, str] | None:
        """(lead key, URL to submit) or None when the hit names neither a repository nor a site."""
        repo = github_repo(*(_https(u) for u in self.urls))
        if repo:
            return f"gh:{repo.lower()}", f"https://github.com/{repo}"
        if self.allow_web:
            for url in self.urls:
                normal = normalize_web_url(url or "")
                if normal and "github.com" not in normal:
                    return f"web:{normal}", normal
        return None


_GIT_FORMS = re.compile(r"^(?:git\+)?(?:ssh://)?git@github\.com[:/]|^git://github\.com/|^github:", re.I)


def _https(url: str | None) -> str:
    """git@github.com:o/n, git+ssh://git@github.com/o/n, git://… and github:o/n as https://github.com/o/n."""
    return _GIT_FORMS.sub("https://github.com/", (url or "").strip())


# Package registries list libraries next to tools; a lead only they know about is often a library, which the
# watch's rules then reject. Curated or software-only sources do not have that problem.
REGISTRY_ONLY = frozenset({"npm", "crates"})


def priority(kind_hint: str, platforms: list[str], percentiles: list[float], sources: list[str]) -> float:
    """Kind first; then attention as the best percentile within any one source (so a million npm downloads and a
    hundred stars are not compared raw), two points per extra source, and less for registry-only leads."""
    linux_or_web = 0.5 if not platforms or {"linux", "web"} & set(platforms) else 0.0
    best = max(percentiles, default=0.0)
    score = KIND_PRIORITY.get(kind_hint, 1.0) + linux_or_web + 2.0 * best + 2.0 * (len(set(sources)) - 1)
    if sources and set(sources) <= REGISTRY_ONLY:
        score -= 2.0
    return round(score, 3)


class LeadsDB:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- state (checkpoints of incremental sources)

    def get_state(self, name: str) -> str | None:
        row = self.conn.execute("SELECT value FROM state WHERE name = ?", (name,)).fetchone()
        return row["value"] if row else None

    def set_state(self, name: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO state(name, value) VALUES (?, ?) "
                              "ON CONFLICT(name) DO UPDATE SET value = excluded.value", (name, value))

    # -- writing

    def add(self, hits: Iterable[Hit], *, now: str | None = None) -> tuple[int, int]:
        """Store hits; return (hits that named something, leads that are new)."""
        now = now or taipei_now().isoformat(timespec="seconds")
        named = new = 0
        with self.conn:
            for hit in hits:
                ku = hit.key_url()
                if ku is None:
                    continue
                key, url = ku
                named += 1
                row = self.conn.execute("SELECT kind_hint, platforms FROM leads WHERE key = ?", (key,)).fetchone()
                if row is None:
                    new += 1
                    self.conn.execute("INSERT INTO leads(key, url, kind_hint, platforms, first_seen, last_seen) "
                                      "VALUES (?, ?, ?, ?, ?, ?)",
                                      (key, url, hit.kind_hint, json.dumps(sorted(set(hit.platforms))), now, now))
                else:
                    kind = row["kind_hint"]
                    # A specific kind beats "unknown"; otherwise the first source's word stands.
                    if kind == "unknown" and hit.kind_hint != "unknown":
                        kind = hit.kind_hint
                    platforms = sorted(set(json.loads(row["platforms"])) | set(hit.platforms))
                    self.conn.execute("UPDATE leads SET kind_hint = ?, platforms = ?, last_seen = ? WHERE key = ?",
                                      (kind, json.dumps(platforms), now, key))
                title = (hit.title or "").strip()[:TITLE_MAX] or None
                self.conn.execute(
                    "INSERT INTO lead_sources(key, source, item_id, title, link, signal, seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(key, source, item_id) DO UPDATE SET "
                    "title = excluded.title, link = excluded.link, signal = excluded.signal, seen_at = excluded.seen_at",
                    (key, hit.source, hit.item_id, title, hit.link, hit.signal, now))
        return named, new

    def log_run(self, run_id: str, source: str, *, started: str, finished: str, hits: int, new: int,
                requests: int, error: str | None) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (run_id, source, started, finished, hits, new, requests, error))

    def mark_known(self, known: dict[str, str]) -> int:
        """Leads whose key is in `known` (key -> why: the record slug or `candidate`) become `known`."""
        changed = 0
        with self.conn:
            for row in self.conn.execute("SELECT key FROM leads WHERE status = 'new'").fetchall():
                why = known.get(row["key"])
                if why:
                    self.conn.execute("UPDATE leads SET status = 'known', status_note = ? WHERE key = ?",
                                      (why, row["key"]))
                    changed += 1
        return changed

    def set_status(self, key: str, status: str, note: str | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE leads SET status = ?, status_note = ? WHERE key = ?", (status, note, key))

    # -- reading

    def ranked(self, *, status: str = "new", kinds: set[str] | None = None,
               platforms: set[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Leads with `status`, best first, each with its sources."""
        rows = self.conn.execute("SELECT * FROM leads WHERE status = ?", (status,)).fetchall()
        sources: dict[str, list[dict[str, Any]]] = {}
        by_source: dict[str, list[float]] = {}
        for s in self.conn.execute("SELECT * FROM lead_sources"):
            sources.setdefault(s["key"], []).append(dict(s))
            if s["signal"] is not None:
                by_source.setdefault(s["source"], []).append(s["signal"])
        for values in by_source.values():
            values.sort()

        def percentile(source: str, signal: float | None) -> float:
            values = by_source.get(source)
            if signal is None or not values:
                return 0.0
            return bisect.bisect_right(values, signal) / len(values)

        out = []
        for row in rows:
            lead = dict(row)
            lead["platforms"] = json.loads(lead["platforms"])
            if kinds and lead["kind_hint"] not in kinds:
                continue
            if platforms and lead["platforms"] and not platforms & set(lead["platforms"]):
                continue
            src = sources.get(lead["key"], [])
            lead["sources"] = sorted({s["source"] for s in src})
            lead["best_signal"] = max((s["signal"] for s in src if s["signal"] is not None), default=None)
            lead["priority"] = priority(lead["kind_hint"], lead["platforms"],
                                        [percentile(s["source"], s["signal"]) for s in src], lead["sources"])
            out.append(lead)
        out.sort(key=lambda x: (-x["priority"], x["first_seen"], x["key"]))
        return out[:limit] if limit else out

    def summary(self) -> dict[str, Any]:
        q = self.conn.execute
        return {
            "leads": q("SELECT count(*) FROM leads").fetchone()[0],
            "by_status": dict(q("SELECT status, count(*) FROM leads GROUP BY 1").fetchall()),
            "new_by_kind": dict(q("SELECT kind_hint, count(*) FROM leads WHERE status = 'new' "
                                  "GROUP BY 1 ORDER BY 2 DESC").fetchall()),
            "by_source": {r[0]: {"leads": r[1], "new": r[2]} for r in q(
                "SELECT s.source, count(DISTINCT s.key), count(DISTINCT CASE WHEN l.status = 'new' THEN s.key END) "
                "FROM lead_sources s JOIN leads l USING (key) GROUP BY 1 ORDER BY 2 DESC").fetchall()},
            "web_leads": q("SELECT count(*) FROM leads WHERE key LIKE 'web:%'").fetchone()[0],
        }


def known_keys(data_dir: Path, pipeline_db: Path | None) -> dict[str, str]:
    """Lead keys pickfit already has: records under data_dir (repository or site) and pipeline candidates."""
    known: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        repo = (data.get("repo") or {}).get("full_name")
        if repo:
            known[f"gh:{repo.lower()}"] = f"record:{data.get('slug')}"
        web = (data.get("web") or {}).get("url")
        normal = normalize_web_url(web) if web else None
        if normal:
            known[f"web:{normal}"] = f"record:{data.get('slug')}"
    if pipeline_db and pipeline_db.exists():
        conn = sqlite3.connect(pipeline_db)
        try:
            for name, aliases in conn.execute("SELECT full_name, aliases FROM candidates"):
                try:
                    names = [name, *(json.loads(aliases or "[]") or [])]
                except (TypeError, ValueError):
                    names = [name]
                for n in names:
                    if isinstance(n, str) and "/" in n:
                        known.setdefault(f"gh:{n.lower()}", "candidate")
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return known
