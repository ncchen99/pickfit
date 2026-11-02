"""Rerun the verify agent on chosen Linux desktop apps, limited to chosen features, without writing anything back.

    uv run python scripts/rerun_planning.py prepare --features features.json --out tasks/
    uv run python scripts/rerun_planning.py tally --features features.json --arm old=<dir> --arm new=<dir>
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


def run(features: dict[str, Any], tasks_dir: Path, runs_dir: Path, concurrency: int, *, agent_model: str = AGENT_MODEL,
        scope_cap_usd: float = SCOPE_CAP_USD) -> None:
    from pickfit.meta import is_open_model
    from pickfit.verify import judge
    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.cli import GUI_LIMITS, LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    if is_open_model(agent_model):  # the judges too, on the same endpoint (Meta's API was refusing calls, 11/3)
        judge.OPEN_JUDGE_MODEL = agent_model
    limits = replace(AgentLimits(), **{**GUI_LIMITS, "scope_cap_usd": scope_cap_usd})
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
                outcome = verify_task(load_fixture(tasks_dir / f"{slug}.json"), make_box, model=agent_model,
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


def _runs(runs_dir: Path) -> dict[str, Path]:
    """Each slug's latest run directory under runs_dir/verify."""
    found: dict[str, Path] = {}
    for d in sorted((runs_dir / "verify").glob("verify-*")):
        slug = d.name.removeprefix("verify-").rsplit("-", 3)[0]
        found[slug] = d
    return found


CHECK_DESIGN = ("typed by the operator", "before the first action")


def feature_rows(slug: str, labels: list[str], run_dir: Path | None) -> list[dict[str, Any]]:
    """Per feature: the record's status and reason, the operations spent and their steps, specs pickfit refused
    before running, and whether the failure lies in the check or the goal (its own check refused an echo or text
    already on screen, or the feature judge saw no proof)."""
    report = json.loads((run_dir / "report.json").read_text()) if run_dir and (run_dir / "report.json").exists() else {}
    record = (json.loads((run_dir / "verification_run.json").read_text())
              if run_dir and (run_dir / "verification_run.json").exists() else {})
    final = {f["feature"]: f for f in record.get("features") or []}
    numbers = {f["feature"]: f.get("number") for f in report.get("features") or []}
    ops = [c["operate"] for c in report.get("commands") or [] if c.get("operate")]
    rows = []
    for i, label in enumerate(labels, 1):
        number = numbers.get(label, i)
        mine = [op for op in ops if (op.get("spec") or {}).get("feature") == number]
        refused = [r for r in report.get("refused_specs") or [] if r.get("feature") == number]
        f = final.get(label) or {}
        whys = " ".join(str((op.get("result") or {}).get("why") or "") for op in mine)
        rows.append({
            "slug": slug, "feature": label, "status": f.get("status") or ("no record" if report else "no run"),
            "reason": f.get("reason"), "note": (f.get("note") or "")[:160], "operations": len(mine),
            "passed_ops": sum(bool(op.get("passed")) for op in mine),
            "steps": sum(len(op.get("steps") or []) for op in mine), "refused": len(refused),
            "check_design": f.get("reason") == "not_shown" or any(k in whys for k in CHECK_DESIGN),
            "level": record.get("level"), "cost_usd": report.get("cost_usd")})
    return rows


def tally(features: dict[str, Any], arms: dict[str, Path]) -> list[dict[str, Any]]:
    rows = []
    for arm, runs_dir in arms.items():
        runs = _runs(runs_dir)
        for slug, want in sorted(features.items()):
            for row in feature_rows(slug, want["features"], runs.get(slug)):
                rows.append({"arm": arm, **row})
    return rows


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
    r.add_argument("--agent-model", default=AGENT_MODEL, help="e.g. open-modal: the agent and the judges")
    r.add_argument("--scope-cap", type=float, default=SCOPE_CAP_USD, help="each run's model spend cap (USD)")
    t = sub.add_parser("tally")
    t.add_argument("--features", required=True)
    t.add_argument("--arm", action="append", required=True, help="name=runs dir")
    t.add_argument("--json", default=None)
    args = ap.parse_args()
    features = json.loads(Path(args.features).read_text())
    if args.cmd == "tally":
        rows = tally(features, {a.split("=", 1)[0]: Path(a.split("=", 1)[1]) for a in args.arm})
        if args.json:
            Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
        for arm, runs_dir in ((a.split("=", 1)[0], Path(a.split("=", 1)[1])) for a in args.arm):
            part = [r for r in rows if r["arm"] == arm]
            summary = runs_dir / "summary.json"
            runs = json.loads(summary.read_text()) if summary.exists() else []
            print(f"{arm}: runs {len(runs)}, model ${sum(r.get('cost_usd') or 0 for r in runs):.2f}, boxes "
                  f"${sum(r.get('box_usd') or 0 for r in runs):.2f}, levels "
                  + ", ".join(f"{r['slug']} {r.get('level') or r.get('error', '')[:30]}" for r in runs))
            print(f"{arm}: checked {sum(r['status'] == 'checked' for r in part)}/{len(part)}, check or goal failures "
                  f"{sum(r['check_design'] and r['status'] != 'checked' for r in part)}, operations "
                  f"{sum(r['operations'] for r in part)}, refused at spec time {sum(r['refused'] for r in part)}, "
                  f"steps {sum(r['steps'] for r in part)}")
        return 0
    if args.cmd == "prepare":
        prepare(features, Path(args.out))
    else:
        run(features, Path(args.tasks), Path(args.runs_dir), args.concurrency, agent_model=args.agent_model,
            scope_cap_usd=args.scope_cap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
