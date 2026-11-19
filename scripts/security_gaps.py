"""What pickfit's security check could not check, across the listed records: gaps grouped by code, category,
ecosystem, software category and platform (pickfit/security.py's gap taxonomy). Reads the records only.

Usage:
    uv run python scripts/security_gaps.py [--data data/software] [--out report.json]

The same report as `uv run pickfit security --gaps`. A sec.v1 record's gap is the one its unchecked_reason stands for
(ecosystem "unknown") until it is scanned again.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pickfit.index import DEFAULT_DATA_DIR
from pickfit.security import main_gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, help="also write the report here")
    args = parser.parse_args(argv)
    report = main_gaps(args.data)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
