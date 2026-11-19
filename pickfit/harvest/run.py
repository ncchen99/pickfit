"""Run harvest sources into runs/harvest.db, mark what pickfit already has, and feed the watch."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

from pickfit.d1 import Database, sql, timestamp
from pickfit.discover.github import GitHub, GitHubError, runs_dir
from pickfit.env import read_env
from pickfit.harvest.check import quiet_before
from pickfit.harvest.leads import LeadsDB, known_keys
from pickfit.harvest.sources import DEFAULT_SOURCES, SOURCES, Ctx, SourceError
from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.watch import harvest_submission_id

ENV_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "BSKY_HANDLE", "BSKY_APP_PASSWORD", "X_BEARER_TOKEN")
FEED_RESERVE = 5  # submit_software rows per hour left for people
NOTE_MAX = 300


def harvest_db_path() -> Path:
    return runs_dir() / "harvest.db"


def pickfit_known() -> dict[str, str]:
    """Lead keys of the records in data/software and the candidates in runs/pipeline.db."""
    return known_keys(REPO_ROOT / "data" / "software", runs_dir() / "pipeline.db")


def default_sources(env: dict[str, str]) -> list[str]:
    """The keyless sources, plus Bluesky and X when their keys are set."""
    names = list(DEFAULT_SOURCES)
    if env.get("BSKY_HANDLE") and env.get("BSKY_APP_PASSWORD"):
        names.append("bluesky")
    if env.get("X_BEARER_TOKEN"):
        names.append("x")
    return names


def run_harvest(sources: list[str] | None = None, *, db_path: Path | None = None, limit: int = 5000,
                days: int = 7, x_max_reads: int = 100, data_dir: Path | None = None,
                pipeline_db: Path | None = None, now: datetime | None = None,
                http: httpx2.Client | None = None, gh: GitHub | None = None,
                env: dict[str, str] | None = None, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Run each source (a failing one is logged and skipped), then mark known leads; return the summary."""
    env = env if env is not None else read_env(ENV_NAMES)
    names = list(sources or default_sources(env))
    unknown = set(names) - SOURCES.keys()
    if unknown:
        raise ValueError(f"unknown sources {sorted(unknown)}; expected {sorted(SOURCES)}")
    db = LeadsDB(db_path or harvest_db_path())
    own_http = http is None
    http = http or httpx2.Client(timeout=60.0)
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    own_gh = gh is None and bool(token)
    gh = gh or (GitHub(token) if token else None)
    run_id = "harvest-" + taipei_now().strftime("%Y%m%d-%H%M%S")
    ctx = Ctx(db=db, http=http, gh=gh, now=now or datetime.now(UTC), log=log, env=env, limit=limit, days=days,
              x_max_reads=x_max_reads)
    report: dict[str, Any] = {"run_id": run_id, "sources": {}}
    try:
        for name in names:
            started = taipei_now().isoformat(timespec="seconds")
            before = sum(ctx.requests.values()) + (sum(gh.requests.values()) if gh else 0)
            error = None
            hits = new = 0
            batch = []
            try:
                for hit in SOURCES[name](ctx):
                    batch.append(hit)
                    if len(batch) >= 500:
                        h, n = db.add(batch)
                        hits, new, batch = hits + h, new + n, []
            except (SourceError, GitHubError, httpx2.HTTPError, ValueError, KeyError) as err:
                error = str(err)[:500]
            if batch:
                h, n = db.add(batch)
                hits, new = hits + h, new + n
            requests = sum(ctx.requests.values()) + (sum(gh.requests.values()) if gh else 0) - before
            db.log_run(run_id, name, started=started, finished=taipei_now().isoformat(timespec="seconds"),
                       hits=hits, new=new, requests=requests, error=error)
            report["sources"][name] = {"hits": hits, "new_leads": new, "requests": requests, "error": error}
            log(f"{name}: {hits} hits, {new} new leads, {requests} requests" + (f"  ERROR {error}" if error else ""))
        known = known_keys(data_dir or REPO_ROOT / "data" / "software",
                           pipeline_db if pipeline_db is not None else runs_dir() / "pipeline.db")
        report["marked_known"] = db.mark_known(known)
        report["summary"] = db.summary()
    finally:
        if own_http:
            http.close()
        if own_gh and gh is not None:
            gh.close()
        db.close()
    return report


def feed(d1: Database, *, n: int, hourly_cap: int, apply: bool, db_path: Path | None = None,
         kinds: set[str] | None = None, platforms: set[str] | None = None, reserve: int = FEED_RESERVE,
         screened_only: bool = True, now: datetime | None = None,
         log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Queue the best `n` new leads as submit_software rows for `pickfit watch`.

    Never more than the hour has room for, keeping `reserve` of SUBMIT_HOURLY_CAP for people. Only leads the
    prescreen kept (`harvest screen`) unless screened_only is off. Without `apply` nothing is written
    anywhere; the rows that would be queued are returned.
    """
    now = now or datetime.now(UTC)
    db = LeadsDB(db_path or harvest_db_path())
    try:
        recent = d1.query(sql("SELECT count(*) AS n FROM submissions WHERE submitted_at >= ?1",
                              timestamp(datetime.fromtimestamp(now.timestamp() - 3600, UTC))))
        room = max(0, hourly_cap - reserve - int((recent[0] if recent else {}).get("n") or 0))
        take = min(n, room)
        log(f"feed: hour has room for {room} (cap {hourly_cap}, reserve {reserve}); taking {take}")
        out = []
        for lead in db.ranked(kinds=kinds, platforms=platforms, quiet_before=quiet_before(now)):
            if len(out) >= take:
                break
            if screened_only and not (lead["check"] or {}).get("screen_keep"):
                continue
            url = lead["url"].lower() if lead["key"].startswith("gh:") else lead["url"]
            existing = d1.query(sql("SELECT id, status FROM submissions WHERE url = ?1", url))
            if existing:
                if apply:
                    db.set_status(lead["key"], "known", f"submission:{existing[0]['id']}:{existing[0]['status']}")
                continue
            # sub_harvest<hex>: the watch takes it after people's rows and within harvest's own slots.
            row = {"id": harvest_submission_id(), "url": url, "key": lead["key"], "kind_hint": lead["kind_hint"],
                   "priority": lead["priority"], "sources": lead["sources"]}
            note = ("harvest: " + ", ".join(lead["sources"]))[:NOTE_MAX]
            if apply:
                d1.execute(sql("INSERT OR IGNORE INTO submissions (id, url, status, submitter_role, note, "
                               "submitted_at, updated_at) VALUES (?1, ?2, 'queued', 'unknown', ?3, ?4, ?4)",
                               row["id"], url, note, timestamp(now)))
                db.set_status(lead["key"], "fed", row["id"])
            out.append(row)
            log(f"  {'queued' if apply else 'would queue'} {url}  [{lead['kind_hint']}, {lead['priority']}, "
                f"{'+'.join(lead['sources'])}]")
        return out
    finally:
        db.close()


def export(path: Path, *, db_path: Path | None = None, status: str = "new", limit: int | None = None) -> int:
    """Write ranked leads as JSON lines (for review, or to hand to `pickfit discover --repo`)."""
    db = LeadsDB(db_path or harvest_db_path())
    try:
        rows = db.ranked(status=status, limit=limit, quiet_before=quiet_before(datetime.now(UTC)))
    finally:
        db.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({k: row[k] for k in ("key", "url", "kind_hint", "platforms", "priority",
                                                     "best_signal", "sources", "first_seen", "check")},
                                ensure_ascii=False) + "\n")
    return len(rows)
