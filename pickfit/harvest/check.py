"""Check leads against GitHub, then prescreen the best of them before they reach the feed.

`check`: GitHub's facts for each repository (one GraphQL query per 25 or so). A repository that is gone,
archived, a fork or a template is skipped, as the watch's rules would reject it anyway; one with no push
for STALE_DAYS is skipped as unmaintained; a renamed one is merged into its current name, which may turn
out to be something pickfit already has.

`screen`: the checked leads at the top are stored as candidates in their own pipeline database
(runs/harvest-pipeline.db, so the laptop's runs/pipeline.db is not touched; README, files, rule label by
`add_repos`, no model) and screened by the prescreen (Claude Haiku, a review by Claude Opus when it is
unsure). A kept lead ranks above every unscreened one; a dropped one is skipped with the reason. The
screen costs about a tenth of a cent a lead, and the feed's hourly room goes to leads that will pass.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pickfit.harvest.leads import LeadsDB

STALE_DAYS = 730  # no push for two years: skipped
QUIET_DAYS = 365  # no push for a year: ranked lower (leads.QUIET_PENALTY)
ADDED = ("added", "refreshed")


def quiet_before(now: datetime) -> str:
    return (now - timedelta(days=QUIET_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_keys(db: LeadsDB, keys: list[str], *, gh: Any, known: dict[str, str], now: datetime,
               log: Callable[[str], None] = print) -> Counter[str]:
    """Check these `gh:` leads; return how many ended up each way."""
    stale_before = (now - timedelta(days=STALE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    names = [k[3:] for k in keys if k.startswith("gh:")]
    meta = gh.repos(names) if names else {}
    out: Counter[str] = Counter()
    for name in names:
        key = f"gh:{name}"
        repo = meta.get(name)
        db.save_check(key, repo)
        if repo is None:
            db.set_status(key, "skipped", "gone")
            out["gone"] += 1
            continue
        flag = next((f for f in ("archived", "disabled", "fork", "is_template") if repo.get(f)), None)
        if flag:
            db.set_status(key, "skipped", flag)
            out[flag] += 1
            continue
        current = f"gh:{(repo.get('full_name') or name).lower()}"
        if current != key:
            db.merge_into(key, current, repo.get("html_url") or f"https://github.com/{repo['full_name']}")
            db.save_check(current, repo)
            out["renamed"] += 1
            key = current
            lead = db.conn.execute("SELECT status FROM leads WHERE key = ?", (key,)).fetchone()
            if known.get(key) and lead and lead["status"] == "new":
                db.set_status(key, "known", known[key])
                out["renamed_known"] += 1
                continue
        if (repo.get("pushed_at") or "9999") < stale_before:
            db.set_status(key, "skipped", f"stale:pushed {repo['pushed_at'][:10]}")
            out["stale"] += 1
            continue
        out["ok"] += 1
    log("check: " + ", ".join(f"{k} {v}" for k, v in sorted(out.items())))
    return out


def check(db: LeadsDB, *, n: int, gh: Any, known: dict[str, str], now: datetime | None = None,
          kinds: set[str] | None = None, platforms: set[str] | None = None,
          log: Callable[[str], None] = print) -> Counter[str]:
    """Check the best `n` new repository leads that have no check yet."""
    now = now or datetime.now(UTC)
    todo = [lead["key"] for lead in db.ranked(kinds=kinds, platforms=platforms, quiet_before=quiet_before(now))
            if lead["key"].startswith("gh:") and not lead["check"]][:n]
    return check_keys(db, todo, gh=gh, known=known, now=now, log=log)


def _top_unscreened(db: LeadsDB, n: int, now: datetime, kinds: set[str] | None,
                    platforms: set[str] | None) -> list[dict[str, Any]]:
    return [lead for lead in db.ranked(kinds=kinds, platforms=platforms, quiet_before=quiet_before(now))
            if lead["key"].startswith("gh:") and not (lead["check"] or {}).get("screened_at")][:n]


def screen(db: LeadsDB, *, n: int, gh: Any, known: dict[str, str], pipeline_db: Path, data_dir: Path,
           review: bool = True, concurrency: int = 2, now: datetime | None = None,
           kinds: set[str] | None = None, platforms: set[str] | None = None,
           add: Callable[..., list[dict[str, Any]]] | None = None,
           prescreen: Callable[..., dict[str, Any]] | None = None,
           log: Callable[[str], None] = print) -> dict[str, Any]:
    """Check, store and prescreen the best `n` new repository leads that have not been screened."""
    from pickfit.discover.store import PipelineDB

    if add is None:
        from pickfit.discover.run import add_repos as add
    if prescreen is None:
        from pickfit.prescreen import run_prescreen as prescreen
    now = now or datetime.now(UTC)
    checked: Counter[str] = Counter()
    for _ in range(20):  # checking skips some leads, which lets others up; a few rounds settle it
        top = _top_unscreened(db, n, now, kinds, platforms)
        todo = [lead["key"] for lead in top if not lead["check"]]
        if not todo:
            break
        checked += check_keys(db, todo, gh=gh, known=known, now=now, log=log)
    top = _top_unscreened(db, n, now, kinds, platforms)
    out: Counter[str] = Counter()
    by_name = {lead["check"]["full_name"]: lead["key"] for lead in top}
    pdb = PipelineDB(pipeline_db)
    rows = add(gh, pdb, list(by_name), data_dir=data_dir, log=log) if by_name else []
    passed: dict[str, str] = {}  # repo_id -> lead key
    for row in rows:
        key = by_name[row["name"]]
        if row.get("record"):
            db.set_status(key, "known", f"record:{row['record']}")
            out["known"] += 1
        elif row["outcome"] not in ADDED:
            db.save_screen(key, keep=None, kind=None, reason=row["outcome"])
            db.set_status(key, "skipped", f"screen:{row['outcome']}")
            out[row["outcome"]] += 1
        elif not row.get("rule_passed"):
            db.save_screen(key, keep=False, kind=None, reason=row.get("rule_label"))
            db.set_status(key, "skipped", f"rules:{row.get('rule_label')}")
            out["rules"] += 1
        else:
            passed[row["repo_id"]] = key
    summary = prescreen(limit=len(passed), repo_ids=list(passed), review=review, concurrency=concurrency,
                        db_path=pipeline_db, log=log) if passed else None
    decisions = pdb.prescreen_decisions()
    for repo_id, key in passed.items():
        decision = decisions.get(repo_id)
        if decision is None:  # the screen failed or the budget stopped it: try again next time
            out["unscreened"] += 1
            continue
        final = decision["review"] or decision["screen"]
        result = final.get("result") or {}
        keep = bool(decision["keep"])
        db.save_screen(key, keep=keep, kind=result.get("kind"), reason=result.get("reason"))
        if keep:
            out["kept"] += 1
        else:
            db.set_status(key, "skipped", f"prescreen:{result.get('kind')}")
            out["dropped"] += 1
    log("screen: " + ", ".join(f"{k} {v}" for k, v in sorted(out.items())))
    return {"checked": dict(checked), "screened": dict(out), "prescreen": summary}
