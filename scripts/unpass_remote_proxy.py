"""Apply the remote-proxy rule to recorded MCP passes: a handshake through a generic proxy to a hosted URL ($0).

The rule (pickfit.verify.mcp.remote_proxy, checked in verdict.mcp_problems) came after these runs, so
this replays it over each passed run's recorded launch argv. Without --apply it only lists matches.
With --apply, a match listed in REASONS becomes unverified with that reason and a blocking_error saying
what happened; the record's level, install guide and scores follow (refresh_scores, no model call).

    uv run python scripts/unpass_remote_proxy.py [--apply]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pickfit.ledger import taipei_now
from pickfit.score import refresh_scores
from pickfit.schema import SoftwareRecord, VerificationRun, best_level, is_passed
from pickfit.verify.mcp import remote_proxy

DATA = Path(__file__).resolve().parents[1] / "data" / "software"
# slug -> (closest UnverifiedReason, what else the run should say)
REASONS = {
    "opencaselaw": ("needs_more_resources",
                    "The README's local MCP server needs ~65 GB of disk (Option B), which the box does not have."),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="downgrade the matches listed in REASONS")
    args = parser.parse_args(argv)
    now = taipei_now().isoformat(timespec="seconds")
    checked = 0
    for path in sorted(DATA.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for run in data["verification"]["runs"]:
            if not is_passed(run["level"]) or not run.get("mcp"):
                continue
            checked += 1
            found = remote_proxy(run["mcp"].get("launch") or [])
            if found is None:
                continue
            proxy, url = found
            print(f"{data['slug']}: run {run['id']} ({run['level']}) handshake via {proxy} to {url}")
            if not args.apply or data["slug"] not in REASONS:
                continue
            reason, detail = REASONS[data["slug"]]
            run["level"], run["unverified_reason"] = "unverified", reason
            run["blocking_error"] = (f"The handshake went to the hosted {url} through {proxy}; no MCP server ran in "
                                     f"the box, so the run does not pass. {detail}")[:500]
            if (data["install"].get(run["os"]) or {}).get("run_id") == run["id"]:
                data["install"][run["os"]] = None
            changed = True
        if changed:
            runs = data["verification"]["runs"]
            level = best_level([VerificationRun.model_validate(r) for r in runs])
            newest = max((r for r in runs if r["level"] == "unverified"), key=lambda r: r["checked_at"], default=None)
            data["verification"]["level"] = level
            data["verification"]["unverified_reason"] = newest["unverified_reason"] if level == "unverified" \
                and newest else None
            data["updated_at"] = now
            refresh_scores(data, taipei_now())  # the sandbox score and the unverified cap follow the level ($0)
            SoftwareRecord.model_validate(data)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  -> {data['slug']}: now {level}")
    print(f"{checked} passed MCP runs checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
