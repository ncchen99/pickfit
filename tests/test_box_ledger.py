"""The ledger's boxes table (pickfit.ledger.BoxLedger) and the rows each provider writes (pickfit.verify.meter):
the migration of an older ledger, estimates, rows a dead harness left open, and a rented Mac's cost split over
its VMs. Fakes only: no provider is called."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import TAIPEI, BoxLedger, Ledger, box_cost, box_ledger, box_time
from pickfit.verify import mac_host
from pickfit.verify.mac_host import HostRecord
from pickfit.verify.meter import BoxMeter, identity, run_slug

START = datetime(2026, 11, 19, 1, 0, tzinfo=UTC)  # 09:00 in Taipei


def at(moment: datetime):
    return lambda: moment


def test_an_older_ledger_opens_as_it_was_and_only_gains_the_boxes_table(tmp_path: Path):
    path = tmp_path / "ledger.sqlite"
    old = Ledger(path, clock=at(START))
    old.settle(old.reserve(0.5, run_id="r1", stage="verify", provider="anthropic", model="m"), 0.25,
               tokens={"input_tokens": 100, "output_tokens": 10})

    def calls() -> list[tuple[Any, ...]]:
        with sqlite3.connect(path) as conn:
            return conn.execute("SELECT * FROM calls ORDER BY id").fetchall()

    def tables() -> set[str]:
        with sqlite3.connect(path) as conn:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    before = calls()
    assert "boxes" not in tables()
    BoxLedger(path)
    BoxLedger(path)  # twice is the same
    assert "boxes" in tables() and calls() == before  # nothing of `calls` was read or changed
    again = Ledger(path, clock=at(START))
    assert again.spend_summary()["total_usd"] == pytest.approx(0.25)
    again.settle(again.reserve(0.1), 0.1)
    assert len(calls()) == 2


def test_a_closed_box_costs_its_rate_for_its_time_and_a_minute_at_least(tmp_path: Path):
    clock = {"now": START}
    ledger = BoxLedger(tmp_path / "l.sqlite", clock=lambda: clock["now"])
    ledger.open_box(box_id="a", provider="modal", rate_usd_per_hour=1.8, lane="linux", purpose="agent")
    ledger.open_box(box_id="b", provider="ec2", rate_usd_per_hour=0.36, min_billed_s=60, lane="windows",
                    purpose="replay")
    ledger.open_box(box_id="c", provider="tart", rate_usd_per_hour=None, lane="macos", purpose="agent")
    clock["now"] = START + timedelta(minutes=10)
    assert ledger.close_box("a") == pytest.approx(0.30)
    assert ledger.close_box("c") is None  # no price of its own
    clock["now"] = START + timedelta(seconds=10)
    assert ledger.close_box("b") == pytest.approx(0.36 * 60 / 3600)
    clock["now"] = START + timedelta(hours=5)
    assert ledger.close_box("a") == pytest.approx(0.30)  # closed once: the first end stays
    rows = {r["box_id"]: r for r in ledger.boxes()}
    assert rows["a"]["started_at"] == "2026-11-19T09:00:00+08:00"  # Taipei time, as calls.ts is
    assert rows["a"]["ended_at"] == "2026-11-19T09:10:00+08:00" and rows["a"]["end_note"] == "closed"
    with pytest.raises(ValueError, match="not a boxes column"):
        ledger.open_box(box_id="d", provider="x", colour="red")
    assert box_time("2026-11-18T12:00:00Z") == "2026-11-18T20:00:00+08:00"
    assert box_time("2026-11-18T12:00:00") == "2026-11-18T20:00:00+08:00"  # no offset: UTC, as providers give it
    assert box_cost(None, 100) is None and box_cost(3.6, 10, 60) == pytest.approx(0.06)


def test_a_box_nobody_closed_ends_at_its_lifetime_or_is_marked_unknown(tmp_path: Path):
    ledger = BoxLedger(tmp_path / "l.sqlite", clock=at(START))
    ledger.open_box(box_id="dead", provider="modal", rate_usd_per_hour=0.72, lifetime_s=1800)
    ledger.open_box(box_id="young", provider="modal", rate_usd_per_hour=0.72, lifetime_s=1800,
                    started_at=START + timedelta(hours=2))
    ledger.open_box(box_id="nolife", provider="ec2", rate_usd_per_hour=0.2)
    ledger.open_box(box_id="mac", provider="scaleway", purpose="host", rate_usd_per_hour=0.25)
    later = START + timedelta(hours=2, minutes=5)
    assert ledger.close_stale(later) == ["dead"]
    rows = {r["box_id"]: r for r in ledger.boxes()}
    assert rows["dead"]["end_note"] == "lifetime" and rows["dead"]["ended_at"] == "2026-11-19T09:30:00+08:00"
    assert rows["dead"]["est_usd"] == pytest.approx(0.36)  # the provider's own cap ended it there at the latest
    assert rows["young"]["ended_at"] is None
    assert sorted(ledger.close_stale(START + timedelta(days=2))) == ["nolife", "young"]
    rows = {r["box_id"]: r for r in ledger.boxes()}
    assert rows["nolife"]["end_note"] == "unknown" and rows["nolife"]["ended_at"] is None
    assert rows["nolife"]["est_usd"] is None
    assert rows["mac"]["ended_at"] is None and rows["mac"]["end_note"] is None  # a rental is closed when deleted


def test_a_meter_starts_its_row_after_closing_stale_ones_and_never_raises(tmp_path: Path):
    ledger = BoxLedger(tmp_path / "l.sqlite")
    ledger.open_box(box_id="old", provider="modal", rate_usd_per_hour=1.0, lifetime_s=60,
                    started_at=datetime.now(UTC) - timedelta(days=1))
    meter = BoxMeter("modal", lane="linux", purpose="agent", run_id="verify-graphtty-20261119-090000-abcd",
                     usd_per_hour=0.72, ledger=ledger)
    meter.start("sb-1")
    meter.start("sb-1")  # once
    rows = {r["box_id"]: r for r in ledger.boxes()}
    assert rows["old"]["end_note"] == "lifetime"
    assert rows[meter.box_id]["slug"] == "graphtty" and rows[meter.box_id]["provider_ref"] == "sb-1"
    assert meter.end() is not None and meter.end() == meter.est_usd

    lines: list[str] = []

    def broken() -> BoxLedger:
        raise sqlite3.OperationalError("unable to open database file")

    lost = BoxMeter("ec2", lane="windows", purpose="replay", ledger=broken, log=lines.append)
    lost.start("i-1")
    assert lost.end() is None
    assert len(lines) == 1 and "could not record the start" in lines[0]  # said once, and the box goes on


def test_who_a_box_is_for_comes_from_the_tags_the_factories_give():
    assert identity({"pickfit.run": "r1", "pickfit.role": "replay"}) == ("r1", "replay")
    assert identity({"pickfit": "web-verify", "run": "web-x"}) == ("web-x", None)
    assert identity(None) == (None, None)
    assert run_slug("verify-graphtty-20261119-090000-abcd") == "graphtty"
    assert run_slug("verify-some-tool-20261119-090000-0f0f") == "some-tool"
    assert run_slug("limits-20261119-090000") is None and run_slug(None) is None


def test_a_rented_mac_is_split_evenly_over_the_vms_that_ran_during_the_rental(tmp_path: Path):
    ledger = BoxLedger(tmp_path / "l.sqlite")
    rec = HostRecord(name="watch-1", provider="scaleway", target="m1@203.0.113.9", server_id="srv-9",
                     server_type="M4-S", created_at="2026-11-19T01:00:00Z")
    assert mac_host.meter_rental(rec, ledger=ledger) == "scaleway-srv-9"
    assert mac_host.meter_rental(rec, ledger=ledger) == "scaleway-srv-9"  # once
    [host] = ledger.boxes()
    assert host["purpose"] == "host" and host["host"] == "203.0.113.9" and host["min_billed_s"] == 24 * 3600
    assert host["rate_usd_per_hour"] == pytest.approx(0.22 * mac_host.USD_PER_EUR, abs=1e-6)
    hour = timedelta(hours=1)

    def vm(box_id: str, when: datetime, *, run: str = "r1", where: str = "203.0.113.9", purpose: str = "agent"):
        ledger.open_box(box_id=box_id, provider="tart", lane="macos", purpose=purpose, run_id=run, host=where,
                        started_at=when, rate_usd_per_hour=None)
        ledger.close_box(box_id, ended_at=when + hour / 2)

    vm("before", START - hour)  # before the rental: another Mac at this address
    vm("agent", START + hour)
    vm("replay", START + 2 * hour, purpose="replay")
    vm("limits", START + 3 * hour, run="limits-1", purpose="limits")
    vm("build", START + 4 * hour, run="prepare", purpose="build")
    vm("elsewhere", START + hour, where="198.51.100.1")
    split = mac_host.end_rental(rec, ledger=ledger, now=START + 30 * hour)
    rate = 0.22 * mac_host.USD_PER_EUR
    assert split["vms"] == 4 and split["host_usd"] == pytest.approx(30 * rate, rel=1e-4)
    assert split["share_usd"] == pytest.approx(30 * rate / 4, rel=1e-4)
    rows = {r["box_id"]: r for r in ledger.boxes()}
    assert rows["agent"]["share_of"] == "scaleway-srv-9" and "1/4 share" in rows["agent"]["rate_source"]
    assert rows["before"]["est_usd"] is None and rows["elsewhere"]["est_usd"] is None
    assert rows["scaleway-srv-9"]["end_note"] == "deleted"
    assert ledger.run_usd("r1") == pytest.approx(30 * rate / 2, rel=1e-4)  # its agent's and its replay's shares
    # A day's minimum: a rental deleted after two hours costs 24 of them.
    short = HostRecord(name="w2", provider="scaleway", target="m1@203.0.113.10", server_id="srv-10",
                       server_type="M4-SP", created_at="2026-11-19T01:00:00Z")
    assert mac_host.end_rental(short, ledger=ledger, now=START + 2 * hour)["host_usd"] == pytest.approx(
        24 * 0.24 * mac_host.USD_PER_EUR, rel=1e-4)
    assert mac_host.meter_rental(HostRecord(name="mine", provider="ssh", target="me@mac")) is None  # lent, not rented


def test_scaleway_records_the_rental_from_its_creation_and_closes_it_at_its_deletion(monkeypatch):
    calls: list[list[str]] = []
    server = {"id": "srv-1", "type": "M4-S", "ssh_username": "m1", "ip": "203.0.113.5", "os": {"version": "15"},
              "created_at": "2026-11-19T01:00:00Z", "deletable_at": "2026-11-20T01:00:00Z", "status": "ready"}
    provider = mac_host.ScalewayProvider()

    def call(*args: str, timeout: float = 120) -> Any:
        calls.append(list(args))
        if args[:3] == ("apple-silicon", "os", "list"):
            return [{"version": "15", "id": "os-15"}]
        if args[:3] == ("apple-silicon", "server-type", "list"):
            return [{"name": "M4-S", "stock": "available"}]
        return dict(server)

    monkeypatch.setattr(provider, "_call", call)
    monkeypatch.setattr(provider, "ensure_key", lambda key, name: None)
    rec = provider.create("watch-1", 15, "ssh-ed25519 AAAA", lambda line: None)
    [row] = box_ledger().boxes()
    assert row["box_id"] == "scaleway-srv-1" and row["started_at"] == "2026-11-19T09:00:00+08:00"
    assert row["host"] == "203.0.113.5" and row["ended_at"] is None
    provider.delete(rec, lambda line: None, now=datetime(2026, 11, 20, 2, 0, tzinfo=UTC))
    [row] = box_ledger().boxes()
    assert row["end_note"] == "deleted" and row["est_usd"] == pytest.approx(25 * 0.22 * mac_host.USD_PER_EUR, rel=1e-4)


def test_a_modal_sandbox_has_a_row_from_its_create_to_its_terminate(monkeypatch: pytest.MonkeyPatch):
    import modal
    from test_verify_modal import FakeSandbox

    from pickfit.verify import modal_box as mb
    from pickfit.verify.box import BoxLimits

    sandbox = FakeSandbox()
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: f"app:{name}")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    monkeypatch.setattr(mb, "sandbox_image_tag", lambda: "pickfit-sbx:abc")
    box = mb.ModalBox(limits=BoxLimits(lifetime_s=300), client="client", log=lambda s: None,
                      tags={"pickfit.run": "verify-graphtty-20261119-090000-abcd", "pickfit.role": "agent"})
    box.start()
    [row] = box_ledger().boxes()
    assert (row["provider"], row["lane"], row["purpose"], row["provider_ref"]) == ("modal", "linux", "agent", "sb-test")
    assert row["vcpu"] == 2 and row["memory_gb"] == 2 and row["lifetime_s"] == 300 and row["slug"] == "graphtty"
    assert row["rate_usd_per_hour"] == pytest.approx(box.usd_per_second() * 3600)
    assert "upper bound" in row["rate_source"] and "2026-10-28" in row["rate_source"]
    box.close()
    [row] = box_ledger().boxes()
    assert sandbox.terminated and row["end_note"] == "closed" and row["est_usd"] is not None


def test_a_web_box_is_counted_in_the_web_lane():
    from pickfit.verify.web_box import WebBox

    box = WebBox(site="https://example.com", tags={"run": "web-1"})
    assert box.machine.lane == box.machine.purpose == "web"


def test_a_tart_vm_has_no_price_of_its_own():
    from pickfit.verify.tart_box import TartBox

    class Remote:
        remote, name, state_dir = True, "203.0.113.9", Path("/nonexistent")

    class Local:
        remote, name, state_dir = False, "local", Path("/nonexistent")

    for host, rate in ((Remote(), None), (Local(), 0.0)):
        box = TartBox(host=host, tags={"pickfit.run": "verify-graphtty-20261119-090000-abcd", "pickfit.role": "replay"},
                      log=lambda s: None)
        box._open_meter("replay")
        box.meter.end()
    rows = sorted(box_ledger().boxes(), key=lambda r: r["host"])
    assert [(r["provider"], r["lane"], r["purpose"], r["host"], r["rate_usd_per_hour"]) for r in rows] == [
        ("tart", "macos", "replay", "203.0.113.9", None), ("tart", "macos", "replay", "local", 0.0)]
    assert all(r["provider_ref"].startswith("pf-verify-") and r["end_note"] == "closed" for r in rows)
    assert "share of the rented Mac" in rows[0]["rate_source"] and rows[1]["est_usd"] == 0.0


def test_taipei_offset_is_what_the_table_sorts_by():
    assert box_time(datetime(2026, 11, 19, 16, 30, tzinfo=UTC)) == datetime(
        2026, 11, 20, 0, 30, tzinfo=TAIPEI).isoformat(timespec="seconds")
