"""scripts/rubric_calibration_set.py: the fixed README set a rubric prompt change is compared on (R2); no network."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.rubric_calibration_set import band, pick

ROOT = Path(__file__).resolve().parent.parent


def member(slug: str, category: str = "dev_cli", docs: float = 0.6, grader: str = "muse") -> dict:
    return {"slug": slug, "repo_id": f"gh:{abs(hash(slug)) % 10**6 + 1}", "category": category,
            "install_docs": docs, "band": band(docs), "grader": grader}


def test_the_pick_spreads_over_groups_and_does_not_depend_on_order() -> None:
    pool = [member(f"cli{i}") for i in range(10)] + [member("ai", "local_ai"), member("low", docs=0.2),
                                                     member("claude", grader="claude")]
    chosen = pick(pool, 4)
    assert {m["slug"] for m in chosen} >= {"ai", "low", "claude"}  # one from each small group first
    assert pick(list(reversed(pool)), 4) == chosen
    assert band(0.49) == "low" and band(0.8) == "high" and band(0.5) == "mid"


def test_the_committed_set_is_fifty_records_with_no_repeats() -> None:
    data = json.loads((ROOT / "scripts" / "rubric_calibration_set.json").read_text(encoding="utf-8"))
    slugs = [m["slug"] for m in data["records"]]
    assert len(slugs) == 50 and len(set(slugs)) == 50 and slugs == sorted(slugs)
    assert {m["category"] for m in data["records"]} >= {"dev_cli", "local_ai", "mcp_server", "other"}
