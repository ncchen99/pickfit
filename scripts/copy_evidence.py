"""Copy the run folders behind GUI and web runs to ~/.pickfit/evidence/<run_id>/, with a sha256 manifest.

The screenshots, action logs and reports of GUI and web runs sit in runs/ folders inside the worktrees that ran
them (gitignored). A worktree that is cleaned up takes them along, and the usability score must cite them, so this
copies every run folder a record in data/software points to (evidence paths and operation screenshots) to a place
outside the repo. The originals stay where they are: other sessions still use those worktrees.

Each copy gets MANIFEST.sha256 (`sha256  name` lines, as shasum -a 256 writes them) and source.json (where it was
copied from, and when). A folder already copied whose files hash the same is left alone; one that differs is
reported, never overwritten. When the same folder sits in two worktrees the one with more files is copied and
the other is named in source.json.

    uv run python scripts/copy_evidence.py [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO.parents[2] if REPO.parent.name == "worktrees" else REPO
EVIDENCE = Path.home() / ".pickfit" / "evidence"


def run_dirs(data_dir: Path) -> list[dict]:
    """Every GUI or web run in the records, with the run folders its evidence points to."""
    out = []
    for path in sorted(data_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for run in record["verification"]["runs"]:
            if not (run.get("gui") or run.get("web")):
                continue
            ev = run["evidence"]
            paths = {p for p in (ev.get("trace_path"), ev.get("log_path")) if p}
            paths |= set(ev.get("screenshot_paths") or [])
            for op in (run.get("gui") or {}).get("operations", []):
                paths |= set(op.get("screenshots") or [])
            out.append({"slug": record["slug"], "run_id": run["id"], "kind": "gui" if run.get("gui") else "web",
                        "os": run["os"], "dirs": sorted({os.path.dirname(p) for p in paths})})
    return out


def checkouts() -> list[Path]:
    return [MAIN] + sorted(p for p in (MAIN / ".claude" / "worktrees").iterdir() if p.is_dir())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_of(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file())


def manifest(folder: Path) -> dict[str, str]:
    return {str(p.relative_to(folder)): sha256(p) for p in files_of(folder)
            if p.name not in ("MANIFEST.sha256", "source.json")}


def copy_run(run: dict, roots: list[Path], *, dry_run: bool) -> dict:
    found = [(root, rel) for rel in run["dirs"] for root in roots if (root / rel).is_dir()]
    if not found:
        return {"run_id": run["run_id"], "status": "missing", "dirs": run["dirs"]}
    if len(run["dirs"]) != 1:
        return {"run_id": run["run_id"], "status": "several_dirs", "dirs": run["dirs"]}
    found.sort(key=lambda f: -len(files_of(f[0] / f[1])))
    root, rel = found[0]
    src = root / rel
    dest = EVIDENCE / run["run_id"]
    want = manifest(src)
    if (dest / "MANIFEST.sha256").exists():
        have = manifest(dest)
        status = "unchanged" if have == want else "differs"
        return {"run_id": run["run_id"], "status": status, "source": str(src)}
    if dry_run:
        return {"run_id": run["run_id"], "status": "would_copy", "source": str(src), "files": len(want)}
    dest.mkdir(parents=True, exist_ok=True)
    for name in want:
        (dest / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / name, dest / name)
    copied = manifest(dest)
    if copied != want:
        return {"run_id": run["run_id"], "status": "copy_mismatch", "source": str(src)}
    (dest / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in sorted(copied.items())))
    (dest / "source.json").write_text(json.dumps({
        "run_id": run["run_id"], "slug": run["slug"], "kind": run["kind"], "os": run["os"],
        "copied_from": str(src), "relative_path": rel,
        "also_in": [str(r / p) for r, p in found[1:]],
        "copied_at": datetime.now().astimezone().isoformat(timespec="seconds"), "files": len(copied),
    }, indent=2) + "\n")
    return {"run_id": run["run_id"], "status": "copied", "source": str(src), "files": len(copied)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(REPO / "data" / "software"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    runs = run_dirs(Path(args.data_dir))
    roots = checkouts()
    rows = [copy_run(run, roots, dry_run=args.dry_run) for run in runs]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if row["status"] not in ("copied", "unchanged", "would_copy"):
            print(json.dumps(row), file=sys.stderr)
    if not args.dry_run:
        index = {row["run_id"]: {k: v for k, v in row.items() if k != "run_id"} for row in rows}
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"runs": len(runs), **counts}))
    return 0 if all(r["status"] in ("copied", "unchanged", "would_copy") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
