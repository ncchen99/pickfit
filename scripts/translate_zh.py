"""Translate the web page's tool sentences into Traditional Chinese (Taiwan); see pickfit/translate.py.

Usage:
    uv run python scripts/translate_zh.py --dry-run                      # count what is missing
    uv run python scripts/translate_zh.py [--slug S]... [--limit N]      # Muse Spark Open on Modal
    uv run --with anthropic python scripts/translate_zh.py --model claude    # Claude, the fallback

`pickfit publish` runs the same step before it builds the index, so this script is for
backfills, comparisons (--out, --retranslate) and the Claude fallback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pickfit.env import read_env
from pickfit.i18n import i18n_dir
from pickfit.index import DEFAULT_DATA_DIR, REPO_ROOT, IndexBuildError, build_index
from pickfit.translate import BATCH_CHARS, MODELS, batches, missing, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--slug", action="append", help="only this tool (repeatable)")
    parser.add_argument("--limit", type=int, help="at most N requests")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--model", choices=MODELS, default="open-modal",
                        help="open-modal: Muse Spark Open on Modal (default); claude: claude-opus-5-5")
    parser.add_argument("--effort", default="medium", help="open-modal: reasoning effort (default medium)")
    parser.add_argument("--max-usd", type=float, default=2.0, help="open-modal: stop spending past this for one run")
    parser.add_argument("--out", type=Path, help="write here instead of data/i18n/zh-TW (e.g. for a comparison)")
    parser.add_argument("--retranslate", action="store_true",
                        help="ask for the selected tools' sentences even if translated (with --out, for a comparison)")
    parser.add_argument("--env", type=Path, default=REPO_ROOT / ".env", help="claude: dotenv file with ANTHROPIC_API_KEY")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        index = build_index(args.data).index
    except IndexBuildError as err:
        print(f"translate_zh: {len(err.problems)} invalid record(s)", file=sys.stderr)
        return 1
    directory = args.out or i18n_dir(args.data)
    entries = [e for e in index["entries"] if not args.slug or e["slug"] in args.slug]
    known, todo = missing(entries, directory, args.retranslate)
    groups = batches(todo, BATCH_CHARS[args.model])
    if args.limit is not None:
        groups = groups[: args.limit]
    chars = sum(len(t) for g in groups for _, t in g)
    print(f"translate_zh: {sum(map(len, groups))} sentences ({chars:,} chars) missing, {len(groups)} requests")
    if args.dry_run or not groups:
        return 0
    key = read_env(["ANTHROPIC_API_KEY"], args.env).get("ANTHROPIC_API_KEY") if args.model == "claude" else None
    totals = run(groups, known, directory, model=args.model, effort=args.effort, max_usd=args.max_usd,
                 concurrency=args.concurrency, anthropic_key=key, out=lambda line: print(line, flush=True))
    print(f"translate_zh: {totals.requests} requests done, {totals.failed} failed; ≈ ${totals.usd:.2f} ({args.model})")
    return 1 if totals.failed else 0


if __name__ == "__main__":
    sys.exit(main())
