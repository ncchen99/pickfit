"""Command-line entry point: `uv run pickfit <command>`."""

from __future__ import annotations

import argparse
import json
import sys

from pickfit import __version__


def _ping(args: argparse.Namespace) -> int:
    from pickfit.meta import ping

    result = ping(provider=args.provider, model=args.model)
    print(json.dumps({
        "model": result.model,
        "text": result.text,
        "cost_usd": result.cost_usd,
        "cache_hit": result.cache_hit,
        "usage": vars(result.usage) if result.usage else None,
    }, ensure_ascii=False, indent=2))
    return 0


def _spend(args: argparse.Namespace) -> int:
    from pickfit.ledger import default_ledger

    print(json.dumps(default_ledger().spend_summary(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pickfit")
    parser.add_argument("--version", action="version", version=f"pickfit {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ping", help="make the smallest possible model call through call_meta")
    p.add_argument("--provider", default="meta", choices=["meta", "baseten"])
    p.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE)')
    p.set_defaults(func=_ping)

    s = sub.add_parser("spend", help="show spending from the shared ledger")
    s.set_defaults(func=_spend)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
