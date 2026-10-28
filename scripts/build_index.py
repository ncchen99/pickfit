"""Validate data/software/*.json against software.v1 and write the Worker's index.

Usage:
    uv run python scripts/build_index.py                     # data/software -> worker/src/generated/index.json
    uv run python scripts/build_index.py --data DIR --out FILE

Exits 1 without writing anything when any record is invalid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pickfit.index import DEFAULT_DATA_DIR, DEFAULT_OUT, IndexBuildError, build_index, write_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="directory of <slug>.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="index file to write")
    args = parser.parse_args(argv)

    try:
        result = build_index(args.data)
    except IndexBuildError as err:
        print(f"build_index: {len(err.problems)} problem(s); index not written", file=sys.stderr)
        for problem in err.problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    write_index(result.index, args.out)
    skipped = f", skipped {len(result.skipped)} not listed" if result.skipped else ""
    print(f"build_index: {result.index['count']} entries -> {args.out}{skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
