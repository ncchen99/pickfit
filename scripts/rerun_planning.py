"""Rerun the verify agent on chosen Linux desktop apps, limited to chosen features, without writing anything back.

    uv run python scripts/rerun_planning.py prepare --features features.json --out tasks/
    PICKFIT_OPERATOR_MODEL=open-modal uv run --project <checkout> python scripts/rerun_planning.py run \\
        --tasks tasks/ --features features.json --runs-dir <dir> [--concurrency 10]

For the planning-goals-and-checks comparison (docs/research/notes/planning-goals-checks.md): `run` goes from a
checkout of main (the old planning agent) and of this branch (the new one), in the same window, on the same tasks.

features.json maps each slug to the feature labels to keep and the Modal runtime its last Linux run used
({"slug": {"runtime": "gvisor", "features": [...]}}). `prepare` builds each task once, as a fixture file: the
repository and README from GitHub, a fresh extraction (muse-spark-1.3, as the pipeline extracts), and as its
features only the chosen labels, each with the README quote its record cites. `run` loads those fixtures and
verifies them: the agent on muse-spark-1.3, each run's Meta spend capped at SCOPE_CAP_USD, write=False.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT

AGENT_MODEL = "muse-spark-1.3"
SCOPE_CAP_USD = 0.65


def prepare(features: dict[str, Any], out: Path) -> None:
    from pickfit.discover.github import GitHub, github_token, normalize_repo
    from pickfit.discover.store import PipelineDB
    from pickfit.extract import extract_with_retries
    from pickfit.schema import ExtractionResult
    from pickfit.watch import EXTRACT_EFFORT

    out.mkdir(parents=True, exist_ok=True)
    gh = GitHub(github_token())
    db = PipelineDB(out / "tasks.db")
    for slug, want in features.items():
        record = json.loads((REPO_ROOT / "data" / "software" / f"{slug}.json").read_text())
        item = gh.repo(record["repo"]["full_name"])
        repo = normalize_repo(item)
        db.upsert_repo(repo, category=record["category"], query_id="planning-rerun")
        db.save_details(record["repo_id"], gh.details(repo), pushed_at=repo.get("pushed_at"))
        candidate = db.candidate(record["repo_id"])
        rows = extract_with_retries(candidate, model=AGENT_MODEL, run_id=f"planning-rerun-{slug}",
                                    reasoning_effort=EXTRACT_EFFORT)
        done = [r for r in rows if r["status"] in ("ok", "quotes_dropped")]
        if not done:
            print(f"{slug}: extraction failed: {rows[-1].get('error')}", flush=True)
            continue
        extraction = dict(done[-1]["result"])
        quotes = {int(e["field"].split("/")[2]): e["quote"] for e in record["evidence"]
                  if e["field"].startswith("/features/")}
        extraction["features"] = [{"value": label, "quote": quotes.get(record["features"].index(label), label)}
                                  for label in want["features"] if label in record["features"]]
        ExtractionResult.model_validate(extraction)
        task = {"slug": slug, "repo_url": record["repo"]["url"], "readme": candidate["readme"] or "",
                "category": record["category"], "extraction": extraction}
        (out / f"{slug}.json").write_text(json.dumps(task, ensure_ascii=False, indent=1) + "\n")
        print(f"{slug}: kind {extraction['kind']['value']}, {len(extraction['features'])} features, "
              f"${sum(r['cost_usd'] for r in rows):.4f}", flush=True)


def run(features: dict[str, Any], tasks_dir: Path, runs_dir: Path, concurrency: int) -> None:
    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.cli import GUI_LIMITS, LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    limits = replace(AgentLimits(), **{**GUI_LIMITS, "scope_cap_usd": SCOPE_CAP_USD})
    slugs = sorted(s for s in features if (tasks_dir / f"{s}.json").exists())
    runs_dir.mkdir(parents=True, exist_ok=True)

    def one(slug: str) -> dict[str, Any]:
        make_box = box_factory("modal", int(limits.max_seconds) + LIFETIME_MARGIN_S,
                               runtime=features[slug].get("runtime", "gvisor"), display=True)
        with (runs_dir / f"{slug}.log").open("a") as fh:
            def log(line: str) -> None:
                fh.write(line + "\n")
                fh.flush()
            began = time.monotonic()
            try:
                outcome = verify_task(load_fixture(tasks_dir / f"{slug}.json"), make_box, model=AGENT_MODEL,
                                      mode=DEFAULT_MODE, limits=limits, runs_dir=runs_dir, log=log, write=False)
                summary = {"slug": slug, **outcome.summary()}
            except Exception as err:  # one app's failure is reported, never stops the others
                summary = {"slug": slug, "error": f"{type(err).__name__}: {err}"[:500],
                           "seconds": round(time.monotonic() - began)}
        print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
        return summary

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, slugs))
    (runs_dir / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--features", required=True)
    p.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--features", required=True)
    r.add_argument("--tasks", required=True)
    r.add_argument("--runs-dir", required=True)
    r.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args()
    features = json.loads(Path(args.features).read_text())
    if args.cmd == "prepare":
        prepare(features, Path(args.out))
    else:
        run(features, Path(args.tasks), Path(args.runs_dir), args.concurrency)
    return 0


if __name__ == "__main__":
    sys.exit(main())
