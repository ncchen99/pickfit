"""Check OCR-first for the screen_text check on saved operations: no model call, nothing written.

gui_operate.check_screen asks pickfit's own OCR (pickfit/verify/marks.py) before the screen judge, and takes the
OCR's reading only when one of its lines holds every expected text. That is safe only if the OCR never reads a
text the screen judge did not see. This reads every saved screen_text operation under runs/verify (report.json
and its step screenshots: the last one, which the check reads, and step 1, the window as it opened) and counts,
per expected text, what the judge said against what the OCR reads.

    uv run python scripts/screen_ocr_check.py [ROOT ...] [--engine auto|tesseract]

ROOT is a checkout whose runs/ to read (default: this one and the main checkout). 11/19 with macOS Vision, the
main checkout and the loop worktree: 63 expected texts, 37 the OCR read too (no call), 0 the OCR read that the
judge had not; on the 40 first screenshots it agreed with the judge on all 7 already there.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import sys
from pathlib import Path

from pickfit.env import REPO_ROOT
from pickfit.verify import marks

LINE = re.compile(r'("(?:[^"\\]|\\.)*"): (yes, but already there before the first action|yes|no)')


def _norm(text: str) -> str:
    return " ".join(text.split())


def _found(text: str, lines: list[str]) -> bool:
    return any(_norm(text) in _norm(line) for line in lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--engine", choices=("auto", "tesseract"), default="auto")
    args = parser.parse_args(argv)
    main_checkout = Path(str(REPO_ROOT).split("/.claude/worktrees/")[0])
    roots = args.roots or list(dict.fromkeys([REPO_ROOT, main_checkout]))
    if (marks.ocr_tool() if args.engine == "auto" else shutil.which("tesseract")) is None:
        print(f"screen_ocr_check: no {args.engine} OCR on this host", file=sys.stderr)
        return 2
    seen: set[str] = set()
    last_rows: list[tuple[str, str, bool, bool]] = []  # run, text, judge saw it, OCR reads it
    first_rows: list[tuple[str, str, bool, bool]] = []  # run, text, judge: already there, OCR reads it there
    for root in roots:
        for path in sorted(glob.glob(f"{root}/runs/verify/*/report.json")):
            run_dir = Path(path).parent
            if run_dir.name in seen:
                continue
            seen.add(run_dir.name)
            try:
                report = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for command in report.get("commands") or []:
                op = command.get("operate") or {}
                line = (op.get("result") or {}).get("line") or ""
                steps = op.get("steps") or []
                shots = [s.get("screenshot") for s in steps if s.get("screenshot")]
                if not line.startswith("on screen (read by the screen judge") or op.get("words") or not shots:
                    continue  # read by a model, no spoken words (those always go to the judge), screenshots kept
                last = run_dir / re.sub(r"-op-\d+\.png$", f"-op-{len(steps) + 1}.png", Path(shots[-1]).name)
                first = run_dir / Path(shots[0]).name
                if not last.exists():
                    continue
                judged = {json.loads(quoted): mark for quoted, mark in LINE.findall(line)}
                lines = marks.ocr_lines(last.read_bytes(), engine=args.engine) or []
                for text, mark in judged.items():
                    last_rows.append((run_dir.name, text, mark.startswith("yes"), _found(text, lines)))
                if judged and all(m.startswith("yes") for m in judged.values()) and first.exists():
                    early = marks.ocr_lines(first.read_bytes(), engine=args.engine) or []
                    for text, mark in judged.items():
                        first_rows.append((run_dir.name, text, mark != "yes", _found(text, early)))
    flips = [r for r in last_rows if r[3] and not r[2]]
    print(f"last screenshots: {len(last_rows)} expected texts")
    print(f"  judge yes, OCR yes (no call):  {sum(r[2] and r[3] for r in last_rows)}")
    print(f"  judge yes, OCR no (call made): {sum(r[2] and not r[3] for r in last_rows)}")
    print(f"  judge no,  OCR no:             {sum(not r[2] and not r[3] for r in last_rows)}")
    print(f"  judge no,  OCR yes (a flip):   {len(flips)}")
    for run, text, _, _ in flips:
        print(f"    {run}: {json.dumps(text, ensure_ascii=False)}")
    disagree = [r for r in first_rows if r[2] != r[3]]
    print(f"first screenshots of passed reads: {len(first_rows)} texts, {sum(r[2] for r in first_rows)} already "
          f"there by the judge, {sum(r[3] for r in first_rows)} by the OCR, {len(disagree)} disagreeing")
    return 1 if flips else 0


if __name__ == "__main__":
    sys.exit(main())
