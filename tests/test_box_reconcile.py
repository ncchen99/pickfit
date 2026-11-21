"""scripts/box_reconcile.py: the ledger's machine estimates beside the providers' bills, by UTC day and provider.
Fixture files only (tests/fixtures/box_reconcile); no provider is called."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pickfit.ledger import BoxLedger, Ledger

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "box_reconcile"
_SPEC = importlib.util.spec_from_file_location("box_reconcile", ROOT / "scripts" / "box_reconcile.py")
box_reconcile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(box_reconcile)

NOW = datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def utc(day: int, hour: float) -> datetime:
    return datetime(2026, 11, day, tzinfo=UTC) + hour * HOUR


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.sqlite"
    boxes = BoxLedger(path)

    def box(box_id: str, provider: str, start: datetime, end: datetime | None, rate: float | None, **kw) -> None:
        boxes.open_box(box_id=box_id, provider=provider, started_at=start, rate_usd_per_hour=rate, **kw)
        if end is not None:
            boxes.close_box(box_id, ended_at=end)

    box("m-agent", "modal", utc(19, 10), utc(19, 11), 0.36, purpose="agent")
    box("m-midnight", "modal", utc(19, 23.5), utc(20, 0.5), 0.36, purpose="replay")  # half on each day
    box("e-agent", "ec2", utc(19, 5), utc(19, 5.5), 0.21, min_billed_s=60, purpose="agent")
    box("e-short", "ec2", utc(19, 6), utc(19, 6) + timedelta(seconds=30), 0.21, min_billed_s=60, purpose="replay")
    box("mac", "scaleway", utc(19, 0), None, 0.2448, min_billed_s=24 * 3600, purpose="host", host="203.0.113.9")
    box("vm", "tart", utc(19, 3), utc(19, 4), None, purpose="agent", host="203.0.113.9")
    boxes.update_box("vm", share_of="mac", est_usd=1.5)  # a share: counted as the host's, not again
    box("lost", "modal", utc(18, 1), None, 0.36)
    boxes.update_box("lost", end_note="unknown")
    return path


def test_estimates_split_by_day_and_count_a_rented_host_once(ledger: Path):
    estimated, notes = box_reconcile.estimates(BoxLedger(ledger).boxes(), NOW)
    assert estimated[("2026-11-19", "modal")] == pytest.approx(0.36 + 0.18)
    assert estimated[("2026-11-20", "modal")] == pytest.approx(0.18)
    assert estimated[("2026-11-19", "ec2")] == pytest.approx(0.105 + 0.21 / 60)  # a minute at least
    # The open rental to now (26 h): 24 h on the 19th, 2 h on the 20th.
    assert estimated[("2026-11-19", "scaleway")] == pytest.approx(24 * 0.2448)
    assert estimated[("2026-11-20", "scaleway")] == pytest.approx(2 * 0.2448)
    assert ("2026-11-19", "tart") not in estimated
    assert notes == {"open": 1, "unknown_end": 1, "unpriced": 0, "shares_skipped": 1, "boxes": 5}


def test_bills_from_each_provider_are_read_from_their_own_formats():
    modal, other = box_reconcile.modal_actual((FIXTURES / "modal_report.json").read_text())
    assert modal == {("2026-11-19", "modal"): pytest.approx(0.41), ("2026-11-20", "modal"): pytest.approx(0.19)}
    assert other == {"2026-11-19": pytest.approx(1.25)}  # the workspace's other app, shown apart
    csv_report = ("Object ID,Description,Environment,Interval Start,Cost\n"
                  "ap-1,pickfit-verify,main,2026-11-19,0.41\nap-2,muse-spark-open,main,2026-11-19,1.25\n")
    assert box_reconcile.modal_actual(csv_report)[0] == {("2026-11-19", "modal"): pytest.approx(0.41)}
    ec2, purposes = box_reconcile.aws_actual((FIXTURES / "aws_cost.json").read_text())
    assert ec2 == {("2026-11-19", "ec2"): pytest.approx(0.125), ("2026-11-20", "ec2"): 0.0}
    assert purposes["2026-11-19"] == {"agent": pytest.approx(0.07), "replay": pytest.approx(0.045),
                                      "(untagged)": pytest.approx(0.01)}
    ungrouped = json.dumps({"ResultsByTime": [{"TimePeriod": {"Start": "2026-11-19"},
                                               "Total": {"UnblendedCost": {"Amount": "0.3"}}}]})
    assert box_reconcile.aws_actual(ungrouped)[0] == {("2026-11-19", "ec2"): pytest.approx(0.3)}
    assert box_reconcile.generic_actual((FIXTURES / "scaleway.csv").read_text()) == {
        ("2026-11-19", "scaleway"): pytest.approx(4.1), ("2026-11-20", "scaleway"): pytest.approx(1.9)}


def test_the_report_gives_each_day_and_provider_its_difference(ledger: Path, capsys: pytest.CaptureFixture[str]):
    code = box_reconcile.main(["--ledger", str(ledger), "--since", "2026-11-19", "--until", "2026-11-21",
                               "--modal-report", str(FIXTURES / "modal_report.json"),
                               "--aws-cost", str(FIXTURES / "aws_cost.json"),
                               "--actual", str(FIXTURES / "scaleway.csv"), "--json"], now=NOW)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    days = {(d["day"], d["provider"]): d for d in out["days"]}
    assert days[("2026-11-19", "modal")]["diff_usd"] == pytest.approx(0.41 - 0.54, abs=1e-4)
    assert days[("2026-11-19", "ec2")]["ratio"] == pytest.approx(0.125 / (0.105 + 0.0035), abs=1e-3)
    assert days[("2026-11-20", "ec2")]["actual_usd"] == 0.0  # billed nothing that day, and estimated nothing
    assert ("2026-11-18", "modal") not in days  # before --since
    totals = {t["provider"]: t for t in out["totals"]}
    assert totals["scaleway"]["actual_usd"] == pytest.approx(6.0)
    assert totals["scaleway"]["estimated_usd"] == pytest.approx(26 * 0.2448, abs=1e-3)
    assert out["aws_by_purpose"]["2026-11-19"]["agent"] == pytest.approx(0.07)
    # Without a bill for a provider, its estimate stands alone.
    box_reconcile.main(["--ledger", str(ledger), "--since", "2026-11-19"], now=NOW)
    table = capsys.readouterr().out
    assert "2026-11-19  modal" in table and "1 VM shares of a rented host counted once" in table
    line = next(row for row in table.splitlines() if row.startswith("2026-11-19  modal"))
    assert line.split()[-3:] == ["-", "-", "-"]


def test_it_prints_the_commands_that_make_the_bill_files(capsys: pytest.CaptureFixture[str]):
    box_reconcile.main(["--print-commands", "--since", "2026-11-19", "--until", "2026-11-26"], now=NOW)
    modal, aws, account = capsys.readouterr().out.strip().splitlines()
    assert modal.startswith("modal billing report --start 2026-11-19 --end 2026-11-26 --json")
    assert "aws ce get-cost-and-usage" in aws and "Start=2026-11-19,End=2026-11-26" in aws
    assert "Key=pickfit:purpose" in aws and '"Key": "pickfit"' in aws
    # The whole account by tag and service, with credits left out so that a day they paid for is not read as free.
    assert "Start=2026-11-19,End=2026-11-26" in account and account.endswith("> aws-account.json")
    assert "Type=TAG,Key=pickfit Type=DIMENSION,Key=SERVICE" in account and '"Tags"' not in account
    assert '{"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}}' in account


def test_the_account_bill_shows_pickfits_part_claude_on_bedrock_and_what_is_not_tagged(
        ledger: Path, capsys: pytest.CaptureFixture[str]):
    """The AWS account is shared with other work. The fixture's service name for Claude is made up: no bill with
    one had been seen when this was written."""
    text = (FIXTURES / "aws_account.json").read_text()
    parts = box_reconcile.aws_account(text)
    assert parts["tagged"] == {"2026-11-19": {"Amazon Elastic Compute Cloud - Compute": pytest.approx(0.12),
                                              "EC2 - Other": pytest.approx(0.01)}}
    assert parts["model"] == {"2026-11-19": {"Claude Opus 5.5 (Amazon Bedrock Edition)": pytest.approx(0.42)}}
    assert parts["untagged"]["2026-11-20"] == {"Amazon Elastic Compute Cloud - Compute": pytest.approx(1.5)}
    # Another wording for the service: nothing is taken for Claude that the pattern does not name.
    assert box_reconcile.aws_account(text, "no-such-service")["untagged"]["2026-11-19"][
        "Claude Opus 5.5 (Amazon Bedrock Edition)"] == pytest.approx(0.42)

    # The ledger's own count of what Bedrock served, by UTC day; the direct API's calls are not AWS's bill.
    on_bedrock = Ledger(ledger, budget="bedrock", clock=lambda: utc(19, 22))  # 06:00 on the 20th in Taipei
    on_bedrock.settle(on_bedrock.reserve(1.0, provider="bedrock", model="claude-opus-5-5", stage="verify"), 0.40)
    on_bedrock.reserve(0.05, provider="bedrock", model="claude-opus-5-5", stage="verify")  # still open
    direct = Ledger(ledger, clock=lambda: utc(19, 10))
    direct.settle(direct.reserve(1.0, provider="anthropic", model="claude-opus-5-5", stage="verify"), 0.9)
    assert box_reconcile.model_estimates(ledger) == {("2026-11-19", "bedrock"): pytest.approx(0.45)}

    args = ["--ledger", str(ledger), "--since", "2026-11-19", "--until", "2026-11-20",
            "--aws-account", str(FIXTURES / "aws_account.json")]
    assert box_reconcile.main([*args, "--json"], now=NOW) == 0
    out = json.loads(capsys.readouterr().out)
    days = {(d["day"], d["provider"]): d for d in out["days"]}
    assert days[("2026-11-19", "bedrock")]["estimated_usd"] == pytest.approx(0.45)
    assert days[("2026-11-19", "bedrock")]["actual_usd"] == pytest.approx(0.42)
    assert days[("2026-11-19", "bedrock")]["diff_usd"] == pytest.approx(-0.03)
    assert days[("2026-11-19", "ec2")]["actual_usd"] == pytest.approx(0.13)  # the tagged part, with no --aws-cost
    assert out["aws_account"]["untagged"] == {"2026-11-19": {"Amazon Elastic Compute Cloud - Compute": 1.5,
                                                             "Amazon Simple Storage Service": 0.4}}  # --until
    # Beside the tag-filtered answer, that one stays the machines' bill.
    box_reconcile.main([*args, "--aws-cost", str(FIXTURES / "aws_cost.json"), "--json"], now=NOW)
    again = {(d["day"], d["provider"]): d for d in json.loads(capsys.readouterr().out)["days"]}
    assert again[("2026-11-19", "ec2")]["actual_usd"] == pytest.approx(0.125)

    box_reconcile.main(args, now=NOW)
    table = capsys.readouterr().out
    assert ("aws, 2026-11-19: US$0.1300 tagged pickfit · US$0.4200 Claude on Bedrock · US$1.9000 not tagged pickfit "
            "(Amazon Elastic Compute Cloud - Compute 1.5000, Amazon Simple Storage Service 0.4000)") in table
    assert "aws, 2026-11-20" not in table and "other work in the account" in table


def test_a_ledger_with_no_model_calls_has_no_bedrock_line(ledger: Path, capsys: pytest.CaptureFixture[str]):
    assert box_reconcile.model_estimates(ledger) == {}  # the boxes table alone: no calls table yet
    box_reconcile.main(["--ledger", str(ledger), "--since", "2026-11-19"], now=NOW)
    assert "bedrock" not in capsys.readouterr().out
