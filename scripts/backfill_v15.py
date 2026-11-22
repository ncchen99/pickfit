"""Rule backfill of the brief section 15 fields (docs/proposals/brief-v15-gap-audit.md 2.2, 3.2; task P1-05).

No model call, no network: every value comes from what a record already holds.

- `track`, `used_by`, `track_basis = "rule"`, from kind and category (TRACK_RULES below). A track a model or a
  person set (track_basis model/human) is left alone, and so is its used_by; a used_by set without a track too.
- `verification.last_passed_at`: the latest passed run's checked_at (schema.Verification requires one passed run and
  no earlier than the latest); none without a passed run. Never moved backwards.
- `verification.reverify_cycle_days`: 30 for MCP servers, web apps and anything needing a third-party API key (their
  dependencies change monthly), 90 for the rest; a cycle already set stays. `verification.reverify_due_at`: the last
  pass plus the cycle; none without a pass.
- `standing = "new"` when first_seen_at is within NEW_DAYS of now and no standing is set.

`updated_at` is left as it is: these are pickfit's own labels derived from the record, not news about the software,
and freshness on the site must not claim otherwise. Every other field dumps exactly as before (checked per record).
Every changed record passes SoftwareRecord.model_validate before anything is written.

    uv run python scripts/backfill_v15.py             # dry run (default): what would change, per track
    uv run python scripts/backfill_v15.py --write     # write data/software/*.json
    uv run python scripts/backfill_v15.py --dir PATH --now 2026-11-22T12:00:00+08:00
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pickfit.ledger import taipei_now  # noqa: E402
from pickfit.schema import PASSED_LEVELS, SoftwareRecord  # noqa: E402

DATA_DIR = ROOT / "data" / "software"
NEW_DAYS = 60
FAST_CYCLE_DAYS = 30  # external APIs, MCP protocol, other people's sites
SLOW_CYCLE_DAYS = 90  # local CLI and the rest
FAST_KINDS = {"mcp_server_or_agent_plugin", "web_app"}
CREATIVE_CATEGORIES = {"media_files", "productivity_docs"}
# Fields this script may add or change; the check in backfill() holds every other field byte for byte.
TOP_FIELDS = {"track", "track_basis", "used_by", "standing"}
VERIFICATION_FIELDS = {"last_passed_at", "reverify_cycle_days", "reverify_due_at"}


def track_rule(kind: str, category: str) -> tuple[str, str]:
    """(track, used_by) by the audit's 2.2 rule. Who queries is an agent either way; used_by is who runs it.

    Track A, agent capabilities:
      - mcp_server_or_agent_plugin, server_daemon -> agent (made to be driven by software);
      - cli_tool -> agent: a command line is what an agent drives, and people who use it are served the same way;
      - tui -> both: the full screen is made for a person, its arguments and output are what an agent can use;
        one rule for every TUI, so no record is judged by hand here;
      - self_hosted_web_app -> agent, except human in media_files / productivity_docs (Trilium, BookStack: the
        UI people work in is the point, the service is how it is hosted).
    Track B: web_app -> human. Track C: desktop_app in media_files / productivity_docs -> both (a person's
    creative or document tool an agent works alongside). Every other desktop_app, and browser_extension -> none,
    human (outside the three tracks; plan.md section 8 defers them).
    """
    if kind in ("mcp_server_or_agent_plugin", "server_daemon", "cli_tool"):
        return "A", "agent"
    if kind == "tui":
        return "A", "both"
    if kind == "self_hosted_web_app":
        return "A", "human" if category in CREATIVE_CATEGORIES else "agent"
    if kind == "web_app":
        return "B", "human"
    if kind == "desktop_app":
        return ("C", "both") if category in CREATIVE_CATEGORIES else ("none", "human")
    if kind == "browser_extension":
        return "none", "human"
    raise ValueError(f"no track rule for kind {kind!r}")


def cycle_days(raw: dict[str, Any]) -> int:
    needs_key = bool((raw.get("prerequisites") or {}).get("api_keys"))
    return FAST_CYCLE_DAYS if raw["kind"] in FAST_KINDS or needs_key else SLOW_CYCLE_DAYS


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def last_passed(runs: list[dict[str, Any]]) -> datetime | None:
    """The latest checked_at among passed runs (schema.Verification's last_passed_at rule), or None."""
    return max((_when(r["checked_at"]) for r in runs if r.get("level") in PASSED_LEVELS), default=None)


def backfill(raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    """The record with the section 15 fields filled by rule, as SoftwareRecord dumps it. Pure; raises when the
    result does not validate or something besides those fields would change."""
    record = SoftwareRecord.model_validate(raw)
    before = record.model_dump(mode="json")
    out = json.loads(json.dumps(before))
    track, used_by = track_rule(out["kind"], out["category"])
    if out.get("track") is None or out.get("track_basis") == "rule":
        out.update(track=track, track_basis="rule")
        out["used_by"] = used_by
    elif out.get("used_by") is None and out["track"] == track:
        out["used_by"] = used_by  # a person's or model's track that agrees with the rule: its used_by follows too

    v = out["verification"]
    passed = last_passed(v.get("runs") or [])
    if passed is not None:
        current = _when(v.get("last_passed_at"))
        latest = max(passed, current) if current else passed
        v["last_passed_at"] = latest.isoformat() if latest != current else v["last_passed_at"]
    if v.get("reverify_cycle_days") is None:
        v["reverify_cycle_days"] = cycle_days(out)
    if v.get("last_passed_at"):
        due = _when(v["last_passed_at"]) + timedelta(days=v["reverify_cycle_days"])
        v["reverify_due_at"] = due.isoformat()

    if out.get("standing") is None and now - _when(out["first_seen_at"]) <= timedelta(days=NEW_DAYS):
        out["standing"] = "new"

    dumped = SoftwareRecord.model_validate(out).model_dump(mode="json")
    strip = lambda d: {k: v for k, v in d.items() if k not in TOP_FIELDS | {"verification"}}  # noqa: E731
    vstrip = lambda d: {k: v for k, v in d.items() if k not in VERIFICATION_FIELDS}  # noqa: E731
    if strip(dumped) != strip(before) or vstrip(dumped["verification"]) != vstrip(before["verification"]):
        raise ValueError("backfill would change a field outside its own")
    return dumped


def _text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def run(data_dir: Path, now: datetime, *, write: bool) -> dict[str, Any]:
    """Backfill every record in data_dir; write only with write and only when nothing failed."""
    tracks: Counter[str] = Counter()
    used: Counter[str] = Counter()
    by_kind: Counter[tuple[str, str]] = Counter()
    cycles: Counter[int] = Counter()
    standing: Counter[str] = Counter()
    changed: dict[Path, str] = {}
    errors: dict[str, str] = {}
    passed = 0
    paths = sorted(data_dir.glob("*.json"))
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            out = backfill(raw, now)
        except Exception as err:  # noqa: BLE001 - report every bad record, write none
            errors[path.stem] = f"{type(err).__name__}: {str(err)[:300]}"
            continue
        tracks[out["track"]] += 1
        used[out.get("used_by") or "-"] += 1
        by_kind[(out["track"], out["kind"])] += 1
        cycles[out["verification"].get("reverify_cycle_days")] += 1
        standing[out.get("standing") or "-"] += 1
        passed += out["verification"].get("last_passed_at") is not None
        text = _text(out)
        if text != path.read_text(encoding="utf-8"):
            changed[path] = text
    if write and not errors:
        for path, text in changed.items():
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
    return {"records": len(paths), "errors": errors, "changed": len(changed), "written": write and not errors,
            "tracks": dict(tracks), "used_by": dict(used), "by_kind": {f"{t} {k}": n for (t, k), n in
                                                                        sorted(by_kind.items())},
            "reverify_cycle_days": dict(cycles), "standing": dict(standing), "last_passed_at": passed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show what would change (the default)")
    mode.add_argument("--write", action="store_true", help="write the records")
    parser.add_argument("--dir", type=Path, default=DATA_DIR, help="records directory (default data/software)")
    parser.add_argument("--now", type=datetime.fromisoformat, default=None,
                        help="the time 'new' is measured from (ISO 8601 with offset; default now in Taipei)")
    args = parser.parse_args(argv)
    now = args.now or taipei_now()
    if now.tzinfo is None:
        parser.error("--now needs a UTC offset")
    summary = run(args.dir, now, write=args.write)
    print(f"{'write' if args.write else 'dry run'} · {summary['records']} records · {len(summary['errors'])} errors "
          f"· {summary['changed']} would change" + (" (written)" if summary["written"] else ""))
    print("tracks: " + ", ".join(f"{t} {n}" for t, n in sorted(summary["tracks"].items())))
    print("used_by: " + ", ".join(f"{u} {n}" for u, n in sorted(summary["used_by"].items())))
    for key, n in summary["by_kind"].items():
        print(f"  {key}: {n}")
    print("reverify_cycle_days: " + ", ".join(f"{d} days {n}" for d, n in sorted(summary["reverify_cycle_days"]
                                                                                  .items())))
    print(f"last_passed_at set: {summary['last_passed_at']}")
    print("standing: " + ", ".join(f"{s} {n}" for s, n in sorted(summary["standing"].items())))
    for slug, why in summary["errors"].items():
        print(f"error {slug}: {why}")
    if summary["errors"] and args.write:
        print("nothing written: fix the errors first")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
