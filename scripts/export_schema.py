"""Write the JSON Schema files under schema/ from pickfit.schema.

Usage:
    uv run python scripts/export_schema.py          # (re)write the files
    uv run python scripts/export_schema.py --check  # exit 1 if a file is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pickfit.schema import render_schema_files

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only report stale files")
    args = parser.parse_args(argv)

    stale = []
    for name, text in render_schema_files().items():
        path = SCHEMA_DIR / name
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(name)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote schema/{name}")

    if args.check and stale:
        print(f"stale: {', '.join(stale)}; run scripts/export_schema.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
