"""`pickfit verify --batch N --concurrency 5`: verify extracted candidates in parallel (P3.7).

Candidates come from the pipeline database (runs/pipeline.db, or --db), opened
read-only: a candidate that passed the rules and has a finished extraction
(muse-spark-1.3 preferred over the contributor model), with the features of a
newer features-only extraction merged in. Before any box starts,
the program sets aside what the box cannot verify (GUI apps unless the boxes
have a display, browser extensions, GPU only, another OS only, Apple Silicon
only in a Linux box, no install path the box can run) with the reason, and skips slugs that already
have a run on the same runner unless --force.

The rest are ranked demo-first: tools a user runs (CLI, TUI, local server)
that process locally, need no API key and are free come first. Each runs the
full pipeline (agent, replay, judge) in its own boxes; up to `concurrency` run
at once. The summary lands in runs/verify/batch-<time>.json.

A record whose runs did not pass is verified again once a newer release appears
(recheck_slugs): `pickfit profiles` copies the latest release into the record, so
the next batch picks it up even though it already has a run. An attempt after the
release (under runs/verify/, written back or not) settles it. No scheduler.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pickfit.ledger import TAIPEI, taipei_now
from pickfit.schema import TOOL_KINDS, ExtractedFeatures, ExtractionResult, is_passed
from pickfit.verify.plan import plan_for
from pickfit.verify.task import VerifyTask

DONE_STATUSES = ("ok", "quotes_dropped")
FEATURES_STATUS = "features"  # a features-only extraction (extract.py)
MODEL_PREFERENCE = ("muse-spark-1.3", "muse-spark-1.3-contributor")
NOT_IN_BOX_KINDS = {"desktop_app": "GUI app", "browser_extension": "browser extension"}


@dataclass
class BatchItem:
    task: VerifyTask
    repo_id: str
    full_name: str
    category: str
    kind: str | None
    priority: int
    extraction_model: str


def slug_for(full_name: str, taken: set[str]) -> str:
    owner, _, name = full_name.partition("/")
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "tool"
    slug = base
    if slug in taken:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{owner}-{name}".lower()).strip("-")[:64]
    taken.add(slug)
    return slug


def demo_priority(ex: ExtractionResult) -> int:
    """Higher first: tools a user runs locally, free, with an example, no key."""
    score = 0
    if ex.kind.value in ("cli_tool", "tui"):
        score += 2
    elif ex.kind.value == "server_daemon":
        score += 1
    if ex.processing.value == "local":
        score += 2
    if ex.pricing.value in (None, "free"):
        score += 1
    if ex.smoke_test_candidates:
        score += 1
    if ex.prerequisites.api_keys:
        score -= 3
    if ex.maturity.value == "prototype":
        score -= 1
    return score


def not_in_box(ex: ExtractionResult, *, gpu: bool = False, os: str = "linux", display: bool = False) -> str | None:
    """Why a box running `os` (with an NVIDIA GPU when `gpu`, a virtual display when `display`) cannot verify
    this at all, or None."""
    kind = ex.kind.value
    if kind == "desktop_app" and display and os == "linux":
        pass
    elif kind in NOT_IN_BOX_KINDS:
        return NOT_IN_BOX_KINDS[kind]
    if kind is not None and kind not in TOOL_KINDS:
        return f"not a tool ({kind})"
    pre = ex.prerequisites
    if pre.gpu.value == "required" and not gpu:
        return "needs a GPU"
    if pre.apple_silicon_only.value and os != "macos":
        return "Apple Silicon only"
    platforms = ex.platforms.value
    if platforms and os not in platforms:
        return f"platforms {'/'.join(platforms)} only"
    if not plan_for(ex, os).candidates:
        return f"no install path the {({'macos': 'macOS', 'windows': 'Windows'}).get(os, 'Linux')} box can run"
    return None


def _model_rank(model: str) -> int:
    return MODEL_PREFERENCE.index(model) if model in MODEL_PREFERENCE else len(MODEL_PREFERENCE)


def _connect_ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def record_categories(data_dir: Path) -> dict[str, str]:
    """repo_id -> category of the records already in data/software: a record's category wins."""
    found: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            found[data["repo_id"]] = data["category"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def record_slugs(data_dir: Path) -> dict[str, str]:
    """repo_id -> slug of the records already in data/software, so write-back finds its file."""
    slugs: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            slugs[data["repo_id"]] = data["slug"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return slugs


def recheck_slugs(data_dir: Path, runs_dir: Path) -> set[str]:
    """Slugs of records that have runs, none passed, and a release newer than the newest attempt.

    The newest attempt is the later of the record's newest run and the newest run under
    runs_dir/verify/, so a recheck that was not written back still counts.
    """
    attempts = last_attempts(runs_dir)
    slugs: set[str] = set()
    for path in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            verification, release = data["verification"], data.get("last_release")
            if not verification["runs"] or is_passed(verification["level"]) or not release:
                continue
            tried = max(datetime.fromisoformat(verification["checked_at"]),
                        attempts.get(data["slug"], datetime.min.replace(tzinfo=TAIPEI)))
            if datetime.fromisoformat(release["published_at"]) > tried:
                slugs.add(data["slug"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return slugs


def load_candidates(db: Path, *, limit: int, repos: list[str] | None = None,
                    categories: list[str] | None = None, skip_slugs: set[str] | None = None,
                    known_slugs: dict[str, str] | None = None, known_categories: dict[str, str] | None = None,
                    gpu: bool = False, os: str = "linux", display: bool = False
                    ) -> tuple[list[BatchItem], list[dict[str, Any]]]:
    """Ranked batch items (at most `limit`) and the candidates set aside, with reasons.

    known_slugs (repo_id -> slug, from record_slugs) wins over a slug made from the name, and
    known_categories (from record_categories) over the extraction's category.
    gpu: the boxes have an NVIDIA GPU, so tools that require one are not set aside.
    os: what the boxes run (linux, or macos for TartBox).
    display: the boxes have a virtual display, so GUI apps are not set aside (Linux).
    """
    skip_slugs = skip_slugs or set()
    known_slugs = known_slugs or {}
    with _connect_ro(db) as conn:
        rows = conn.execute(
            "SELECT c.repo_id, c.full_name, c.category, c.repo, c.readme, e.model, e.result, e.id "
            "FROM candidates c JOIN extractions e ON e.repo_id = c.repo_id "
            f"WHERE c.rule_passed = 1 AND e.status IN ({','.join('?' * len(DONE_STATUSES))}) "
            "ORDER BY e.id", DONE_STATUSES).fetchall()
        feature_rows = conn.execute("SELECT repo_id, model, result, id FROM extractions WHERE status = ? "
                                    "ORDER BY id", (FEATURES_STATUS,)).fetchall()
    features: dict[str, sqlite3.Row] = {}
    for row in feature_rows:
        held = features.get(row["repo_id"])
        if held is None or _model_rank(row["model"]) <= _model_rank(held["model"]):
            features[row["repo_id"]] = row
    best: dict[str, sqlite3.Row] = {}
    for row in rows:  # ordered by id: a later extraction of an equally preferred model wins
        held = best.get(row["repo_id"])
        if held is None or _model_rank(row["model"]) <= _model_rank(held["model"]):
            best[row["repo_id"]] = row
    wanted = {r.lower() for r in repos or []}
    items: list[BatchItem] = []
    skipped: list[dict[str, Any]] = []
    taken: set[str] = set(known_slugs.values())
    for row in sorted(best.values(), key=lambda r: r["full_name"].lower()):
        if wanted and row["repo_id"].lower() not in wanted and row["full_name"].lower() not in wanted:
            continue
        try:
            ex = ExtractionResult.model_validate_json(row["result"])
            extra = features.get(row["repo_id"])
            if extra is not None and (not ex.features or extra["id"] > row["id"]):
                listed = json.loads(extra["result"] or "{}").get("features") or []
                ex = ex.model_copy(update={"features": ExtractedFeatures.model_validate({"features": listed}).features})
        except ValidationError as err:
            ex = None
            invalid = f"extraction does not validate: {str(err)[:120]}"
        # The record's category: the record's own, else the extraction's, else the discovery query's (as
        # profiles.py decides). A record verified as a CLI tool is not checked as an MCP server.
        category = (known_categories or {}).get(row["repo_id"]) or (ex.category.value if ex else None) \
            or row["category"]
        recorded = row["repo_id"] in (known_categories or {})
        if categories and category not in categories and (recorded or row["category"] not in categories):
            continue  # a record's own category decides; without one, the query's may match too
        slug = known_slugs.get(row["repo_id"]) or slug_for(row["full_name"], taken)
        note = {"repo_id": row["repo_id"], "full_name": row["full_name"], "slug": slug}
        if ex is None:
            skipped.append({**note, "reason": invalid})
            continue
        why = not_in_box(ex, gpu=gpu, os=os, display=display)
        if why:
            skipped.append({**note, "reason": why})
            continue
        if not row["readme"]:
            skipped.append({**note, "reason": "no README stored"})
            continue
        if slug in skip_slugs:
            skipped.append({**note, "reason": "already has a run (use --force)"})
            continue
        repo = json.loads(row["repo"] or "{}")
        url = repo.get("html_url") or f"https://github.com/{row['full_name']}"
        task = VerifyTask(slug=slug, repo_url=url, readme=row["readme"], extraction=ex, category=category)
        items.append(BatchItem(task, row["repo_id"], row["full_name"], category, ex.kind.value,
                               demo_priority(ex), row["model"]))
    items.sort(key=lambda i: (-i.priority, i.full_name.lower()))
    return items[:limit], skipped


_RUN_TIME = re.compile(r"-(\d{8}-\d{6})-[0-9a-f]{4}$")


NEVER_RAN = ("model_error", "box_error")  # the agent's stop reasons when the model or the box failed it


def last_attempts(runs_dir: Path) -> dict[str, datetime]:
    """Slug -> start time of its newest run under runs/verify/ (from the run id, Taipei time).

    A run the model or the box stopped before the agent could work (model_error, box_error, or no
    report at all) is not an attempt.
    """
    latest: dict[str, datetime] = {}
    for path in (runs_dir / "verify").glob("*/outcome.json"):
        m = _RUN_TIME.search(path.parent.name)
        try:
            slug = json.loads(path.read_text(encoding="utf-8"))["slug"]
            stop = json.loads((path.parent / "report.json").read_text(encoding="utf-8")).get("stop_reason")
        except (OSError, ValueError, KeyError, AttributeError):
            continue
        if stop in NEVER_RAN:
            continue
        if m:
            started = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=TAIPEI)
            latest[slug] = max(started, latest.get(slug, started))
    return latest


def verified_slugs(runs_dir: Path, since: str | None = None, runner: str | None = None) -> set[str]:
    """Slugs that already have an outcome under runs/verify/, from runs started at `since` or later.

    `since` is Taipei time as in run ids, YYYYmmdd-HHMMSS (a prefix such as 20261029-01 works).
    `runner` (e.g. tart-vz) keeps only outcomes from that runner, so a Linux run does not stand in
    for a macOS one.
    """
    slugs = set()
    for path in (runs_dir / "verify").glob("*/outcome.json"):
        m = _RUN_TIME.search(path.parent.name)
        if since and (not m or m.group(1) < since):
            continue
        try:
            outcome = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "slug" not in outcome or (runner and outcome.get("runner") != runner):
            continue
        slugs.add(outcome["slug"])
    return slugs


def _prefixed(slug: str, lock: threading.Lock, log: Callable[[str], None]) -> Callable[[str], None]:
    def say(line: str) -> None:
        with lock:
            log(f"[{slug}] {line}")
    return say


def run_batch(items: list[BatchItem], verify: Callable[[VerifyTask, Callable[[str], None]], Any], *,
              concurrency: int, runs_dir: Path, log: Callable[[str], None] = print,
              meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify every item, `concurrency` at a time; `verify(task, log)` returns an Outcome."""
    began = time.monotonic()
    lock = threading.Lock()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(verify, item.task, _prefixed(item.task.slug, lock, log)): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            base = {"slug": item.task.slug, "repo_id": item.repo_id, "full_name": item.full_name,
                    "category": item.category, "kind": item.kind, "priority": item.priority,
                    "extraction_model": item.extraction_model}
            try:
                outcome = future.result()
                rows.append({**base, **outcome.summary(), "notes": outcome.notes})
            except Exception as err:  # one broken tool must not stop the batch
                rows.append({**base, "level": None, "error": f"{type(err).__name__}: {err}"})
            with lock:
                last = rows[-1]
                log(f"== {len(rows)}/{len(items)} · {last['slug']} · level {last.get('level')} · "
                    f"{last.get('seconds', '-')}s · model ${last.get('cost_usd') or 0:.4f} · "
                    f"box ${last.get('box_usd') or 0:.4f}")
    order = {item.task.slug: i for i, item in enumerate(items)}
    rows.sort(key=lambda r: order[r["slug"]])
    summary = summarize(rows, wall_s=round(time.monotonic() - began, 1), concurrency=concurrency)
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    path = runs_dir / "verify" / f"batch-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**(meta or {}), "summary": summary, "items": rows}, ensure_ascii=False,
                               indent=2) + "\n", encoding="utf-8")
    summary["path"] = str(path)
    return summary


def summarize(rows: list[dict[str, Any]], *, wall_s: float, concurrency: int) -> dict[str, Any]:
    passed = [r for r in rows if r.get("level") and is_passed(r["level"])]
    seconds = [r["seconds"] for r in rows if r.get("seconds") is not None]
    levels: dict[str, int] = {}
    for r in rows:
        levels[str(r.get("level"))] = levels.get(str(r.get("level")), 0) + 1
    return {"tools": len(rows), "passed": len(passed), "replayed": sum(bool(r.get("replayed")) for r in rows),
            "levels": levels, "errors": sum(1 for r in rows if r.get("error")),
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
            "box_usd": round(sum(r.get("box_usd") or 0 for r in rows), 4),
            "seconds_median": round(statistics.median(seconds), 1) if seconds else None,
            "seconds_max": max(seconds) if seconds else None, "wall_s": wall_s, "concurrency": concurrency}
