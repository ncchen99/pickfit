"""Write verified runs back into data/software only when the record loses nothing (P3.13).

For each run (runs/verify/<run_id>/verification_run.json, the slug taken from its report.json), the run is written
with result.write_back only when it passed and was replayed, and against the record's run on the same OS, arch and
method: its level is not weaker, every feature that run checked is checked again, a feature that run set aside for a
limit of the box (needs_gpu, needs_hardware, needs_more_resources, ...) is not now set aside for another reason (the
page would stop saying the limit is pickfit's environment), and a GUI app's tier is not lower.
Every other OS's run stays as it is (write_back replaces only the same OS). Prints one line per run and, with
--dry-run, writes nothing.

    uv run python scripts/guarded_write_back.py runs/verify/voxclip-20261102-... [more run dirs] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pickfit.schema import PASSED_LEVELS, SoftwareRecord, VerificationRun, is_passed
from pickfit.verify.result import DATA_DIR, write_back

GUI_ORDER = ("window", "ui_rendered", "action_checked")
# Reasons that say the limit is pickfit's box, not the software.
ENVIRONMENT = ("needs_gpu", "needs_hardware", "needs_display", "needs_desktop", "needs_more_resources", "needs_account",
               "needs_service", "needs_container", "needs_root", "needs_toolchain", "other_os")


def checked(run: VerificationRun) -> set[str]:
    return {f.feature for f in run.features if f.status == "checked"}


def why_not(run: VerificationRun, record: SoftwareRecord) -> str | None:
    """Why writing this run would cost the record something; None when it would not."""
    if not is_passed(run.level) or not run.replayed:
        return f"the run is {run.level}{'' if run.replayed else ', not replayed'}"
    same = next((r for r in record.verification.runs if (r.os, r.arch, r.method) == (run.os, run.arch, run.method)),
                None)
    if same is None:
        return None
    if is_passed(same.level) and PASSED_LEVELS.index(run.level) > PASSED_LEVELS.index(same.level):
        return f"{run.level} is weaker than the {same.os} run's {same.level}"
    lost = sorted(checked(same) - checked(run))
    if lost:
        return f"the {same.os} run checked {len(lost)} feature(s) this one does not: {', '.join(lost)[:200]}"
    reasons = {f.feature: f.reason for f in run.features if f.status == "not_checked"}
    blamed = sorted(f.feature for f in same.features if f.status == "not_checked" and f.reason in ENVIRONMENT
                    and f.feature in reasons and reasons[f.feature] not in ENVIRONMENT)
    if blamed:
        return f"{', '.join(blamed)[:160]} would lose its reason that the limit is the box"
    if same.gui and (run.gui is None or GUI_ORDER.index(run.gui.tier) < GUI_ORDER.index(same.gui.tier)):
        return f"the GUI tier would drop from {same.gui.tier} to {run.gui.tier if run.gui else 'none'}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path, help="run directories under runs/verify")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for run_dir in args.runs:
        run = VerificationRun.model_validate_json((run_dir / "verification_run.json").read_text(encoding="utf-8"))
        slug = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))["slug"]
        path = args.data_dir / f"{slug}.json"
        record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        before = (record.verification.level, {r.os: r.level for r in record.verification.runs})
        refused = why_not(run, record)
        if refused or args.dry_run:
            print(f"{slug}: {'not written: ' + refused if refused else 'would write'} ({run.id}, {run.level}, "
                  f"{len(checked(run))} checked)")
            continue
        written, note = write_back(run, slug, args.data_dir)
        after = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        print(f"{slug}: {note} · level {before[0]} -> {after.verification.level} · runs {before[1]} -> "
              f"{ {r.os: r.level for r in after.verification.runs} } · {len(checked(run))} checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
