"""Rerun recorded replays in fresh Modal boxes, with no model, and compare what passed offline.

Usage:
    uv run python scripts/rereplay.py RUN_ID ... [--jobs 8] [--out runs/rereplay/NAME.json]
    uv run python scripts/rereplay.py --gvisor-offline [--sample N] [--jobs 8]

Each run's plan is its replay.json (the steps, setups and checks the agent ran, as the
replay ran them); the README comes from the pipeline databases and the category from
the record, as the batch built the task. A fresh box of the run's own runtime (gVisor
unless the replay ran in a VM) runs the plan with the pipeline's Replayer. Nothing
under data/ is written: the output lists, per check, whether it passed and whether it
passed offline, then and now. --gvisor-offline picks each record's latest modal-gvisor
run when one of its smoke tests passed offline (a later Tart, VM or Windows run does not
hide it); --skip-checked leaves out the runs an earlier output file already reran.

replay.json files are looked up under runs/verify of this checkout, the main checkout
and its worktrees (runs/ is not in git).
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.verify.batch import load_candidates
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.modal_box import ModalBox
from pickfit.verify.replay import ReplayCheck, ReplayCommand, Replayer, ReplayPlan

LIFETIME_S = 1800


def main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


def roots() -> list[Path]:
    main = main_checkout()
    return list(dict.fromkeys([REPO_ROOT, main, *sorted(Path(p) for p in glob.glob(f"{main}/.claude/worktrees/*"))]))


def find_replays(run_ids: set[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in roots():
        for run_id in run_ids - found.keys():
            path = root / "runs" / "verify" / run_id / "replay.json"
            if path.is_file():
                found[run_id] = path
    return found


def records() -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted((REPO_ROOT / "data" / "software").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for run in record["verification"].get("runs") or []:
            out[run["id"]] = record
    return out


def gvisor_offline(by_run: dict[str, dict[str, Any]]) -> list[str]:
    """Run ids: each record's latest modal-gvisor run, when some smoke test of it passed offline."""
    picked = []
    for run_id, record in by_run.items():
        gvisor = [r for r in record["verification"]["runs"] if r["runner"] == "modal-gvisor"]
        if gvisor and gvisor[-1]["id"] == run_id and \
                any(t.get("offline") is True for t in gvisor[-1].get("smoke_tests", [])):
            picked.append(run_id)
    return sorted(picked)


def tasks(wanted: list[dict[str, Any]]) -> dict[str, Any]:
    """repo_id -> VerifyTask, from the first pipeline database that has the README."""
    slugs = {r["repo_id"]: r["slug"] for r in wanted}
    categories = {r["repo_id"]: r["category"] for r in wanted}
    out: dict[str, Any] = {}
    for root in roots():
        db = root / "runs" / "pipeline.db"
        missing = [repo for repo in slugs if repo not in out]
        if not missing or not db.is_file():
            continue
        items, _ = load_candidates(db, limit=10**6, repos=missing, known_slugs=slugs, known_categories=categories,
                                   gpu=True, display=True)
        out.update({item.repo_id: item.task for item in items})
    return out


def plan_of(data: dict[str, Any]) -> ReplayPlan:
    def cmd(c: dict[str, Any]) -> ReplayCommand:
        return ReplayCommand(**c)

    return ReplayPlan(steps=tuple(cmd(c) for c in data["steps"]), setups=tuple(cmd(c) for c in data["setups"]),
                      checks=tuple(ReplayCheck(cmd(k["run"]), tuple(k["setup_ids"]), k["expected_exit_code"],
                                               k["expected_signal"], k["kind"]) for k in data["checks"]))


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    before = {c["command_id"]: c for c in old["checks"]}
    rows = []
    for c in new["checks"]:
        was = before.get(c["command_id"], {})
        rows.append({"command_id": c["command_id"], "command": c["command"][:200], "kind": c["kind"],
                     "was_passed": was.get("passed"), "was_offline": was.get("offline"),
                     "passed": c["passed"], "offline": c["offline"],
                     "offline_problems": c["offline_problems"][:3], "problems": c["problems"][:3],
                     "offline_tail": ((c.get("run") or {}).get("stdout") or "")[-600:] if not c["offline"] else ""})
    return rows


def needs_network(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Checks that passed offline then, and now pass only online: what the network cut changed."""
    return [c for c in checks if c["was_offline"] and c["passed"] and not c["offline"]]


def fails_now(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Checks that passed then and fail even online now (the project changed, or the box did)."""
    return [c for c in checks if c["was_passed"] and not c["passed"]]


def rerun(run_id: str, path: Path, task: Any, evidence: Path, lock: threading.Lock) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    old, runner = data["result"], data["result"].get("box", {}).get("runner", "modal-gvisor")
    display = any(k["kind"] == "gui" for k in data["plan"]["checks"])
    box = ModalBox(limits=BoxLimits(lifetime_s=LIFETIME_S), runtime=runner.removeprefix("modal-"), display=display,
                   tags={"pickfit": "rereplay", "run": run_id}, log=lambda s: None)
    lines: list[str] = []
    began = time.monotonic()
    try:
        box.start()
        new = Replayer(box, log=lines.append, evidence_dir=evidence / run_id).run(plan_of(data["plan"]), task).to_dict()
    except BoxError as err:
        new = {"passed": False, "level": None, "offline": False, "checks": [], "error": f"box error: {err}",
               "seconds": 0.0, "box": {}}
    finally:
        box.close()
    alive = time.monotonic() - began
    out = {"run_id": run_id, "slug": task.slug, "runner": box.runner, "image": box.image, "alive_s": round(alive, 1),
           "usd": round(alive * box.usd_per_second(), 5),
           "was": {"passed": old["passed"], "level": old["level"], "offline": old["offline"], "error": old.get("error")},
           "now": {"passed": new["passed"], "level": new["level"], "offline": new["offline"], "error": new.get("error")},
           "checks": compare(old, new), "log": lines[-60:]}
    with lock:
        flips, fails = needs_network(out["checks"]), fails_now(out["checks"])
        print(f"{task.slug}: was {out['was']['level']}/offline {out['was']['offline']} -> now {out['now']['level']}/"
              f"offline {out['now']['offline']} · {len(flips)} need the network now · {len(fails)} fail now · {alive:.0f}s"
              f"{' · ' + str(new.get('error'))[:120] if new.get('error') else ''}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_ids", nargs="*")
    ap.add_argument("--gvisor-offline", action="store_true", help="every gVisor run with a smoke test passed offline")
    ap.add_argument("--skip-checked", type=Path, action="append", default=[],
                    help="an earlier output file: leave out the runs it reran")
    ap.add_argument("--sample", type=int, default=0, help="a random sample of that many (seed 7)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    by_run = records()
    run_ids = list(args.run_ids) + (gvisor_offline(by_run) if args.gvisor_offline else [])
    run_ids = list(dict.fromkeys(run_ids))
    done = {r["run_id"] for path in args.skip_checked for r in json.loads(path.read_text(encoding="utf-8"))["results"]}
    run_ids = [r for r in run_ids if r not in done]
    if args.sample and len(run_ids) > args.sample:
        run_ids = sorted(random.Random(7).sample(run_ids, args.sample))
    unknown = [r for r in run_ids if r not in by_run]
    if unknown:
        print(f"not a run of any record: {unknown}")
        return 2
    replays = find_replays(set(run_ids))
    found = tasks([by_run[r] for r in run_ids])
    jobs = [(r, replays.get(r), found.get(by_run[r]["repo_id"])) for r in run_ids]
    for r, path, task in jobs:
        if path is None or task is None:
            print(f"{by_run[r]['slug']}: skipped ({'no replay.json' if path is None else 'no README in any pipeline db'})")
    jobs = [j for j in jobs if j[1] is not None and j[2] is not None]
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    out = args.out or REPO_ROOT / "runs" / "rereplay" / f"rereplay-{stamp}.json"
    evidence = out.parent / out.stem
    print(f"rereplay · {len(jobs)} runs · {args.jobs} at a time · {out}", flush=True)
    lock = threading.Lock()
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda j: rerun(*j, evidence, lock), jobs))
    summary = {"runs": len(results), "usd": round(sum(r["usd"] for r in results), 4),
               "seconds": round(time.monotonic() - began),
               "need_the_network_now": {r["slug"]: [c["command"][:100] for c in needs_network(r["checks"])]
                                        for r in results if needs_network(r["checks"])},
               "fail_now": {r["slug"]: [c["command"][:100] for c in fails_now(r["checks"])]
                            for r in results if fails_now(r["checks"])},
               "replay_failed_now": {r["slug"]: str(r["now"]["error"])[:200] for r in results if not r["now"]["passed"]},
               "replay_offline_was_true_now_false": sorted(r["slug"] for r in results
                                                           if r["was"]["offline"] and not r["now"]["offline"])}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
