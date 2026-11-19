"""`pickfit harvest probe`: is every source still answering in the shape harvest reads, and does the chain after it work?

Each source runs against its real API with a small limit into a throwaway database (runs/harvest.db is not
touched). A source passes when it answers without an error and names at least MIN_NAMED[source] pieces of
software. Bluesky and X are skipped, not failed, when their keys are not set; X reads at most X_READS paid
posts (US$0.005 each).

Then the chain on the same throwaway leads: `check` on the best few (GitHub GraphQL), `screen` of one (the
real prescreen, Claude Haiku, about US$0.001, into a throwaway pipeline database) and a dry-run `feed`
against D1, which reads but writes nothing. Each step must give an answer; what it answers is not judged.

The report goes to runs/harvest/probe.json. The CLI exits 1 when anything failed, so the daily unit on the
watch machine (deploy/watch/pickfit-harvest-probe.timer) shows up in `systemctl --failed`.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

from pickfit.discover.github import GitHub, GitHubError
from pickfit.harvest.leads import LeadsDB
from pickfit.harvest.sources import SOURCES, Ctx, SourceError

PROBE_LIMIT = 30
PROBE_DAYS = 2  # winget and HN look back this far; one day can be empty
X_READS = 10
MIN_NAMED = {"x": 0}  # ten X posts may hold none over the like threshold; the call itself must work
NEEDS_KEYS = {"bluesky": ("BSKY_HANDLE", "BSKY_APP_PASSWORD"), "x": ("X_BEARER_TOKEN",)}
SAMPLE = 3


def probe_source(name: str, ctx: Ctx) -> dict[str, Any]:
    started = time.monotonic()
    before = sum(ctx.requests.values()) + (sum(ctx.gh.requests.values()) if ctx.gh else 0)
    hits, error = [], None
    try:
        for hit in SOURCES[name](ctx):
            hits.append(hit)
            if len(hits) >= PROBE_LIMIT:
                break
    except (SourceError, GitHubError, httpx2.HTTPError, ValueError, KeyError, TypeError) as err:
        error = f"{type(err).__name__}: {str(err)[:300]}"
    named = [h for h in hits if h.key_url()]
    if named:
        ctx.db.add(named)
    need = MIN_NAMED.get(name, 1)
    if error is None and len(named) < need:
        error = f"named {len(named)} pieces of software, expected at least {need} (did the API's format change?)"
    return {"status": "failed" if error else "ok", "hits": len(hits), "named": len(named),
            "sample": [h.key_url()[0] for h in named[:SAMPLE]], "error": error,
            "requests": sum(ctx.requests.values()) + (sum(ctx.gh.requests.values()) if ctx.gh else 0) - before,
            "seconds": round(time.monotonic() - started, 1)}


def probe(names: list[str] | None = None, *, env: dict[str, str], http: httpx2.Client | None = None,
          gh: GitHub | None = None, d1: Any = None, screen: bool = True, chain: bool = True,
          known: dict[str, str] | None = None, data_dir: Path | None = None, now: datetime | None = None,
          screen_fn: Callable[..., dict[str, Any]] | None = None,
          log: Callable[[str], None] = print) -> dict[str, Any]:
    """Probe the sources (default: all of them) and the chain; returns the report with ok true or false."""
    from pickfit.harvest import check

    now = now or datetime.now(UTC)
    names = list(names or SOURCES)
    own_http = http is None
    http = http or httpx2.Client(timeout=60.0)
    report: dict[str, Any] = {"at": now.isoformat(timespec="seconds"), "sources": {}, "chain": {}}
    with tempfile.TemporaryDirectory(prefix="harvest-probe-") as tmp:
        db = LeadsDB(Path(tmp) / "harvest.db")
        try:
            ctx = Ctx(db=db, http=http, gh=gh, now=now, log=lambda s: None, env=env, limit=PROBE_LIMIT,
                      days=PROBE_DAYS, x_max_reads=X_READS)
            for name in names:
                missing = [k for k in NEEDS_KEYS.get(name, ()) if not env.get(k)]
                if missing:
                    result = {"status": "skipped", "error": None, "why": f"{', '.join(missing)} not set"}
                else:
                    result = probe_source(name, ctx)
                report["sources"][name] = result
                log(f"{name}: {result['status']}"
                    + (f" · {result['named']}/{result['hits']} named · {result['requests']} requests · "
                       f"{result['seconds']}s · e.g. {', '.join(result['sample']) or '-'}" if "hits" in result else
                       f" · {result['why']}")
                    + (f" · {result['error']}" if result.get("error") else ""))
            if chain:
                report["chain"] = _chain(db, Path(tmp), gh=gh, d1=d1, screen=screen, known=known or {},
                                         data_dir=data_dir or Path(tmp), now=now, screen_fn=screen_fn, log=log,
                                         check=check)
        finally:
            db.close()
            if own_http:
                http.close()
    report["ok"] = (all(r["status"] != "failed" for r in report["sources"].values())
                    and all(r["status"] != "failed" for r in report["chain"].values()))
    log("probe: " + ("ok" if report["ok"] else "FAILED"))
    return report


def _chain(db: LeadsDB, tmp: Path, *, gh: GitHub | None, d1: Any, screen: bool, known: dict[str, str],
           data_dir: Path, now: datetime, screen_fn: Callable[..., dict[str, Any]] | None,
           log: Callable[[str], None], check: Any) -> dict[str, Any]:
    from pickfit.harvest.run import feed

    out: dict[str, Any] = {}

    def step(name: str, fn: Callable[[], Any], judge: Callable[[Any], str | None]) -> None:
        try:
            value = fn()
            error = judge(value)
        except Exception as err:  # noqa: BLE001 - a probe reports whatever broke
            value, error = None, f"{type(err).__name__}: {str(err)[:300]}"
        out[name] = {"status": "failed" if error else "ok", "error": error,
                     "result": value if isinstance(value, (dict, list)) else None}
        log(f"chain {name}: {out[name]['status']}" + (f" · {error}" if error else ""))

    if gh is None:
        out["check"] = {"status": "skipped", "error": None, "why": "no GitHub token"}
        return out
    step("check", lambda: dict(check.check(db, n=5, gh=gh, known=known, now=now, log=lambda s: None)),
         lambda r: None if sum(r.values()) else "checked nothing (no repository leads?)")
    if screen:
        run = screen_fn or check.screen
        step("screen", lambda: run(db, n=1, gh=gh, known=known, pipeline_db=tmp / "pipeline.db",
                                   data_dir=data_dir, review=False, concurrency=1, now=now, log=lambda s: None),
             lambda r: None if set(r["screened"]) & {"kept", "dropped", "rules", "known"}
             else f"the screen decided nothing: {r['screened']}")
    if d1 is not None:
        step("feed", lambda: feed(d1, n=1, hourly_cap=20, apply=False, db_path=tmp / "harvest.db",
                                  screened_only=screen, now=now, log=lambda s: None),
             lambda r: None if isinstance(r, list) else "no answer")
    return out
