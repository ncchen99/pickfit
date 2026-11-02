"""Gather the raw sandbox records D5 checks against (eval/README.md 9.1 A3, D5).

Every verification run in data/software has an id; its raw record (commands,
exit codes, image, times) lives in runs/verify/<id>/ of whichever worktree ran
it (found from the main checkout, also when this runs in a worktree; records
from another machine come in with --extra-root). This copies each one into
runs/eval-evidence/verify/<id>/ of this checkout (gitignored, like all of
runs/; d5_check.py reads the same folder) and writes
eval/results/evidence-manifest.json: every file's sha256 and where it came
from. The A3 snapshot records the manifest's sha256, so D5 can only use these
exact files. A run with no raw record is listed as missing: per D5 it does not
count as found.

Run with: uv run python eval/runner/collect_evidence.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "runs" / "eval-evidence" / "verify"
MANIFEST = ROOT / "eval" / "results" / "evidence-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def referenced_runs(data_dir: Path) -> list[tuple[str, str]]:
    pairs = []
    for path in sorted(data_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for run in (record.get("verification") or {}).get("runs") or []:
            pairs.append((record["slug"], run["id"]))
    return pairs


def main_checkout(root: Path) -> Path:
    """The main checkout, also when this runs in a worktree: the other worktrees sit under it."""
    out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                         capture_output=True, text=True)
    return Path(out.stdout.strip()).parent if out.returncode == 0 else root


def source_roots(root: Path, extra: list[Path] = ()) -> list[Path]:
    main = main_checkout(root)
    roots = [root / "runs" / "verify", main / "runs" / "verify"]
    roots += sorted((main / ".claude" / "worktrees").glob("*/runs/verify"))
    roots += list(extra)  # e.g. runs/verify copied from another machine (the Windows host)
    unique = list(dict.fromkeys(r.resolve() for r in roots))
    return [r for r in unique if r.is_dir()]


def collect(root: Path = ROOT, evidence: Path = EVIDENCE, manifest: Path = MANIFEST, extra: list[Path] = ()) -> dict:
    runs, missing = {}, []
    roots = source_roots(root, extra)
    for slug, run_id in referenced_runs(root / "data" / "software"):
        source = next((r / run_id for r in roots if (r / run_id).is_dir()), None)
        if source is None:
            missing.append({"slug": slug, "run_id": run_id})
            continue
        target = evidence / run_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        files = {str(p.relative_to(target)): sha256(p) for p in sorted(target.rglob("*")) if p.is_file()}
        runs[run_id] = {"slug": slug, "source": str(source), "files": files}
    result = {"runs": runs, "missing": missing, "run_count": len(runs)}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/collect_evidence.py")
    parser.add_argument("--extra-root", action="append", default=[], type=Path,
                        help="another runs/verify folder, e.g. one copied from the Windows host")
    args = parser.parse_args()
    result = collect(extra=args.extra_root)
    print(f"collected {result['run_count']} run(s) into {EVIDENCE.relative_to(ROOT)}; "
          f"missing {len(result['missing'])}; manifest {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
