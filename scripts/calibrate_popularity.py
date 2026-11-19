"""Popularity reference values: the in-category P95 of each signal over the collected candidates (B.3).

B.3 calls the first refs uncalibrated guesses, to be replaced by the category P95 once candidates are
collected. The population is the rule-passed candidates in runs/pipeline.db, by the category of the
query that found them. GitHub signals come from the stored snapshots; with --registries, the
registry and Hacker News signals are looked up live (free public APIs, names from root manifests;
pypistats is left out, as B.3 allows it only a few calls). Lookups are cached in --cache, so a rerun
makes no requests. Prints a POPULARITY_REFS literal for pickfit/score.py and per-signal percentiles;
a P95 below REF_FLOORS is raised to it (most candidates are on no registry and never reached HN).

The categories with no discovery queries of their own ("other", and the five subject categories of 2026-11-15,
whose tools the dev_cli queries found) are calibrated with --by extraction: a candidate counts in the category its
newest finished extraction gave it (the category its record is scored under), else in its query's. A category with
fewer than --min candidates gets no refs of its own and is scored against "_all", the P95 over every candidate the
run read (docs/proposals/scoring.md R8: not against dev_cli's). --seen-before keeps the pool of one time: the
hackathon refs were taken over the candidates first seen by 2026-10-31; later rows include named, well-known
repositories that discovery did not find.

    uv run python scripts/calibrate_popularity.py --registries
    uv run python scripts/calibrate_popularity.py --by extraction --seen-before 2026-11-01 --registries
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pickfit.score import (
    DAYS_PER_MONTH,
    REF_FLOORS,
    VELOCITY_MIN_AGE_DAYS,
    popularity_signals,
    snapshot_time,
)

SIGNALS = ("stars", "forks", "release_downloads", "monthly_downloads", "registries_count", "hn_top_score")


def percentile(values: list[float], p: float) -> float:
    """Linear interpolation between closest ranks."""
    v = sorted(values)
    k = (len(v) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


ALL = "_all"  # every candidate the run read: the refs of a category too small for its own
MIN_CANDIDATES = 40
_DONE = ("ok", "quotes_dropped")


def candidates(db: Path, *, seen_before: str | None = None, by_extraction: bool = False) -> list[dict[str, Any]]:
    """Rule-passed candidates (first seen before `seen_before`, an ISO date, when given). With by_extraction, each
    one's category is the one its newest finished extraction gave it, when it has one."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    where = "WHERE rule_passed = 1" + (" AND first_seen_at < ?" if seen_before else "")
    rows = conn.execute("SELECT repo_id, full_name, aliases, category, repo, releases, manifests, details_at, "
                        f"last_seen_at FROM candidates {where}", (seen_before,) if seen_before else ()).fetchall()
    extracted: dict[str, str] = {}
    if by_extraction:
        for row in conn.execute("SELECT repo_id, result FROM extractions WHERE status IN (?, ?) ORDER BY id", _DONE):
            category = ((json.loads(row["result"]) if row["result"] else {}).get("category") or {}).get("value")
            if category:
                extracted[row["repo_id"]] = category  # the newest wins
    conn.close()
    out = []
    for row in rows:
        snap = {k: row[k] for k in row.keys()}
        for key in ("aliases", "repo", "releases", "manifests"):
            snap[key] = json.loads(snap[key]) if snap[key] else None
        snap["category"] = extracted.get(snap["repo_id"], snap["category"])
        out.append(snap)
    return out


def github_signals(snap: dict[str, Any]) -> dict[str, float | None]:
    from datetime import datetime

    signals: dict[str, float | None] = dict(popularity_signals(snap))
    created = snap["repo"].get("created_at")
    as_of = snapshot_time(snap, datetime.now().astimezone())
    age = (as_of - datetime.fromisoformat(created)).days if created else None
    stars = signals["stars"]
    signals["star_velocity"] = (stars / (age / DAYS_PER_MONTH)
                                if stars is not None and age is not None and age >= VELOCITY_MIN_AGE_DAYS else None)
    return signals


def registry_signals(snaps: list[dict[str, Any]], cache_path: Path, workers: int) -> dict[str, dict[str, Any]]:
    from pickfit.registries import Registries, manifest_names

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, dict[str, Any]] = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [s for s in snaps if s["repo_id"] not in cache]
    reg = Registries(pypi_downloads=False)

    def one(snap: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        sig = reg.lookup(snap["full_name"], aliases=snap.get("aliases") or [],
                         homepage=snap["repo"].get("homepage"), names=manifest_names(snap.get("manifests")))
        return snap["repo_id"], {"monthly_downloads": sig.monthly_downloads, "registries_count": sig.registries_count,
                                 "hn_top_score": sig.hn_top_score, "packages": sig.packages, "errors": sig.errors}

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, (repo_id, value) in enumerate(pool.map(one, todo), 1):
                cache[repo_id] = value
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)} looked up, {reg.requests} requests", file=sys.stderr)
                    cache_path.write_text(json.dumps(cache))
    finally:
        reg.close()
        cache_path.write_text(json.dumps(cache))
    return cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="runs/pipeline.db")
    parser.add_argument("--registries", action="store_true", help="also look up registry and HN signals")
    parser.add_argument("--cache", default="runs/calibration/registries.json")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--p", type=float, default=95.0)
    parser.add_argument("--by", choices=("query", "extraction"), default="query",
                        help="a candidate's category: its discovery query's (default), or its extraction's")
    parser.add_argument("--min", type=int, default=0,
                        help=f"fewest candidates a category needs for refs of its own; smaller ones use {ALL} "
                             f"(default 0: every category; {MIN_CANDIDATES} is what R8 uses)")
    parser.add_argument("--seen-before", default=None, metavar="DATE",
                        help="only candidates first seen before this ISO date (the hackathon refs: 2026-11-01)")
    args = parser.parse_args(argv)

    snaps = candidates(Path(args.db), seen_before=args.seen_before, by_extraction=args.by == "extraction")
    extra = registry_signals(snaps, Path(args.cache), args.workers) if args.registries else {}
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for snap in snaps:
        signals = github_signals(snap)
        signals.update({k: v for k, v in extra.get(snap["repo_id"], {}).items() if k in SIGNALS})
        by_cat.setdefault(snap["category"], []).append(signals)

    def reference_values(rows: list[dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in (*SIGNALS, "star_velocity"):
            values = [r[name] for r in rows if r.get(name) is not None]
            if not values:
                continue
            qs = " ".join(f"p{q}={percentile(values, q):.1f}" for q in (25, 50, 75, 90, 95, 99))
            nonzero = sum(1 for v in values if v)
            print(f"  {name:<18} n={len(values):<4} nonzero={nonzero:<4} {qs} max={max(values):.0f}")
            out[name] = max(round(percentile(values, args.p), 1), REF_FLOORS.get(name, 0))
        return out

    refs: dict[str, dict[str, float]] = {}
    for cat, rows in sorted(by_cat.items()):
        if len(rows) < args.min:
            print(f"{cat}: {len(rows)} rule-passed candidates, fewer than {args.min}: scored against {ALL}")
            continue
        print(f"{cat}: {len(rows)} rule-passed candidates")
        refs[cat] = reference_values(rows)
    if args.min or args.by == "extraction":
        pooled = [signals for rows in by_cat.values() for signals in rows]
        print(f"{ALL}: {len(pooled)} rule-passed candidates")
        refs[ALL] = reference_values(pooled)
    print("\nPOPULARITY_REFS (P%g, raised to REF_FLOORS) =" % args.p)
    print(json.dumps(refs, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
