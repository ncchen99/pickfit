"""scripts/backfill_v15.py: the brief 15 fields filled by rule, dry run by default, every record validated."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import TAIPEI
from pickfit.schema import SoftwareRecord
from scripts.backfill_v15 import backfill, cycle_days, last_passed, main, run, track_rule

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = json.loads((FIXTURES / "software_example.json").read_text(encoding="utf-8"))
MCP = json.loads((FIXTURES / "record_mcp.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=TAIPEI)


def record(**fields: Any) -> dict[str, Any]:
    data = copy.deepcopy(EXAMPLE)
    data.update(fields)
    return data


@pytest.mark.parametrize(("kind", "category", "expected"), [
    ("cli_tool", "dev_cli", ("A", "agent")),
    ("cli_tool", "media_files", ("A", "agent")),
    ("tui", "dev_cli", ("A", "both")),
    ("mcp_server_or_agent_plugin", "mcp_server", ("A", "agent")),
    ("server_daemon", "infra_devops", ("A", "agent")),
    ("self_hosted_web_app", "infra_devops", ("A", "agent")),
    ("self_hosted_web_app", "productivity_docs", ("A", "human")),
    ("self_hosted_web_app", "media_files", ("A", "human")),
    ("web_app", "other", ("B", "human")),
    ("desktop_app", "media_files", ("C", "both")),
    ("desktop_app", "productivity_docs", ("C", "both")),
    ("desktop_app", "local_ai", ("none", "human")),
    ("browser_extension", "other", ("none", "human")),
])
def test_track_rule(kind: str, category: str, expected: tuple[str, str]) -> None:
    assert track_rule(kind, category) == expected


def test_unknown_kind_is_an_error() -> None:
    with pytest.raises(ValueError, match="no track rule"):
        track_rule("spaceship", "other")


def test_cycle_days() -> None:
    assert cycle_days({"kind": "cli_tool", "prerequisites": {"api_keys": []}}) == 90
    assert cycle_days({"kind": "cli_tool", "prerequisites": {"api_keys": ["OPENAI_API_KEY"]}}) == 30
    assert cycle_days({"kind": "mcp_server_or_agent_plugin", "prerequisites": {}}) == 30
    assert cycle_days({"kind": "web_app", "prerequisites": {}}) == 30
    assert cycle_days({"kind": "desktop_app", "prerequisites": {}}) == 90


def test_a_cli_record_gets_track_last_pass_cycle_and_new() -> None:
    raw = record(first_seen_at=(NOW - timedelta(days=10)).isoformat())
    out = backfill(raw, NOW)
    assert (out["track"], out["track_basis"], out["used_by"]) == ("A", "rule", raw_used_by(raw))
    v = out["verification"]
    passed = max(datetime.fromisoformat(r["checked_at"].replace("Z", "+00:00"))
                 for r in raw["verification"]["runs"] if r["level"] in ("inference", "service", "function", "install"))
    assert datetime.fromisoformat(v["last_passed_at"].replace("Z", "+00:00")) == passed
    assert v["reverify_cycle_days"] == cycle_days(raw)
    assert datetime.fromisoformat(v["reverify_due_at"].replace("Z", "+00:00")) == passed + timedelta(
        days=v["reverify_cycle_days"])
    assert out["standing"] == "new"
    # Everything else, updated_at included, is as it was; and the result is a valid record.
    assert out["updated_at"] == SoftwareRecord.model_validate(raw).model_dump(mode="json")["updated_at"]
    SoftwareRecord.model_validate(out)


def raw_used_by(raw: dict[str, Any]) -> str:
    return track_rule(raw["kind"], raw["category"])[1]


def test_old_records_are_not_new_and_a_set_standing_stays() -> None:
    old = backfill(record(first_seen_at=(NOW - timedelta(days=61)).isoformat()), NOW)
    assert "standing" not in old
    kept = backfill(record(first_seen_at=NOW.isoformat(), standing="broken", standing_note="failed 11/20"), NOW)
    assert (kept["standing"], kept["standing_note"]) == ("broken", "failed 11/20")


def test_last_passed_counts_passed_runs_only() -> None:
    assert last_passed([]) is None
    assert last_passed([{"level": "unverified", "checked_at": "2026-11-01T00:00:00Z"},
                        {"level": "failed", "checked_at": "2026-11-02T00:00:00Z"}]) is None
    assert last_passed([{"level": "install", "checked_at": "2026-11-01T00:00:00Z"},
                        {"level": "function", "checked_at": "2026-10-01T00:00:00+08:00"},
                        {"level": "unverified", "checked_at": "2026-11-05T00:00:00Z"}]) == datetime.fromisoformat(
        "2026-11-01T00:00:00+00:00")


def test_the_catalogs_unpassed_records_get_a_cycle_but_no_due_date() -> None:
    """A real record without a passed run (the fixture's scores need one, so take one from data/software)."""
    data = Path(__file__).resolve().parent.parent / "data" / "software"
    raw = next((r for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(data.glob("*.json")))
                if r["verification"]["level"] == "unverified"), None)
    if raw is None:
        pytest.skip("no unverified record in data/software")
    out = backfill(raw, NOW)
    assert "last_passed_at" not in out["verification"] and "reverify_due_at" not in out["verification"]
    assert out["verification"]["reverify_cycle_days"] == cycle_days(raw)


def test_a_person_or_model_track_and_a_set_cycle_are_kept() -> None:
    raw = record(track="C", track_basis="human", used_by="both")
    raw["verification"] = {**raw["verification"], "reverify_cycle_days": 14}
    out = backfill(raw, NOW)
    assert (out["track"], out["track_basis"], out["used_by"]) == ("C", "human", "both")
    assert out["verification"]["reverify_cycle_days"] == 14
    # A rule's own earlier answer is recomputed (the rule may have changed).
    again = backfill(record(track="B", track_basis="rule", used_by="human"), NOW)
    assert (again["track"], again["used_by"]) == track_rule(EXAMPLE["kind"], EXAMPLE["category"])


def test_backfill_is_idempotent() -> None:
    once = backfill(record(), NOW)
    assert backfill(once, NOW) == once


def test_an_mcp_record_is_on_the_fast_cycle() -> None:
    out = backfill(copy.deepcopy(MCP), NOW)
    assert (out["track"], out["used_by"]) == ("A", "agent")
    assert out["verification"]["reverify_cycle_days"] == 30


def _catalog(tmp_path: Path) -> Path:
    data = tmp_path / "software"
    data.mkdir()
    for slug, raw in {"frobtail": EXAMPLE, "mcpish": MCP}.items():
        (data / f"{slug}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def test_dry_run_writes_nothing_and_write_writes_valid_records(tmp_path: Path) -> None:
    data = _catalog(tmp_path)
    before = {p.name: p.read_text() for p in data.glob("*.json")}
    summary = run(data, NOW, write=False)
    assert (summary["records"], summary["errors"], summary["changed"], summary["written"]) == (2, {}, 2, False)
    assert summary["tracks"] == {"A": 2}
    assert {p.name: p.read_text() for p in data.glob("*.json")} == before
    summary = run(data, NOW, write=True)
    assert summary["written"] is True
    for path in data.glob("*.json"):
        rec = SoftwareRecord.model_validate_json(path.read_text())
        assert rec.track == "A" and rec.track_basis == "rule" and rec.verification.reverify_cycle_days
    assert not list(data.glob("*.tmp"))
    # A second run finds nothing to change.
    assert run(data, NOW, write=False)["changed"] == 0


def test_one_bad_record_blocks_every_write(tmp_path: Path) -> None:
    data = _catalog(tmp_path)
    (data / "broken.json").write_text(json.dumps({**EXAMPLE, "kind": "spaceship"}), encoding="utf-8")
    before = (data / "frobtail.json").read_text()
    summary = run(data, NOW, write=True)
    assert "broken" in summary["errors"] and summary["written"] is False
    assert (data / "frobtail.json").read_text() == before


def test_main_defaults_to_a_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = _catalog(tmp_path)
    before = (data / "frobtail.json").read_text()
    assert main(["--dir", str(data), "--now", NOW.isoformat()]) == 0
    out = capsys.readouterr().out
    assert out.startswith("dry run · 2 records · 0 errors · 2 would change") and "tracks: A 2" in out
    assert (data / "frobtail.json").read_text() == before
    assert main(["--dir", str(data), "--now", NOW.isoformat(), "--write"]) == 0
    assert (data / "frobtail.json").read_text() != before
