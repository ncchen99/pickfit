"""The macOS lane (pickfit.verify.mac_batch): reuse a ready host, rent one only when allowed and under the cap,
the root step from the provider's password without keeping it, and deleting only the hosts it rented once their
paid day is over. Fake hosts and providers only."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pickfit.lanes import Policy
from pickfit.verify import mac_batch, mac_host
from pickfit.verify.box import BoxError
from pickfit.verify.mac_batch import MacLane
from pickfit.verify.mac_host import Check, HostRecord

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
SECRET = "pw-from-the-provider"


class World:
    """What the fake hosts answer: which are ready, which bases they have; every call is logged."""

    def __init__(self) -> None:
        self.ready: dict[str, bool] = {}
        self.bases: dict[str, bool] = {}
        self.calls: list[str] = []
        self.rooted: set[str] = set()

    def ops(self, rec: HostRecord, log: Any = print) -> Any:
        world = self

        class Ops:
            def checks(self, *, boot: bool = False) -> list[Check]:
                world.calls.append(f"checks:{rec.name}{':boot' if boot else ''}")
                if rec.target.endswith("unreachable"):
                    raise BoxError("ssh: connect timed out")
                ok = world.ready.get(rec.name, False) or rec.name in world.rooted
                built = world.bases.get(rec.name, False)
                return [Check("macos", True, "15"), Check("softnet_setuid", ok, "x"), Check("auto_login", ok, "x"),
                        Check("base:pickfit-macos-15", built, "x"), Check("base:pickfit-macos-15-gui", built, "x")]

            def wait_ssh(self) -> None:
                world.calls.append(f"wait_ssh:{rec.name}")

            def prepare(self) -> Any:
                world.calls.append(f"prepare:{rec.name}")
                rec.macos = 15
                return mac_host.macos_for(15)

        return Ops()


class FakeProvider:
    def __init__(self, world: World, *, password: str | None = SECRET, fail: str | None = None) -> None:
        self.world, self.password, self.fail = world, password, fail
        self.deleted: list[str] = []

    def create(self, name: str, macos: int, public_key: str, log: Any) -> HostRecord:
        self.world.calls.append(f"create:{name}")
        if self.fail:
            raise BoxError(self.fail)
        return HostRecord(name=name, provider="scaleway", target="m1@203.0.113.9", macos=macos, server_id="srv-9",
                          server_type="M4-S", created_at="2026-11-18T12:00:00Z",
                          deletable_at="2026-11-19T12:00:00Z")

    def delete(self, rec: HostRecord, log: Any) -> None:
        self.deleted.append(rec.name)

    def root_password(self, rec: HostRecord) -> str | None:
        return self.password


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    world = World()
    provider = FakeProvider(world)
    key = tmp_path / "key"
    key.write_text("private")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA test")
    tests: list[list[str]] = []
    roots: list[tuple[str, str]] = []

    def run_test(rec: HostRecord, steps: list[Any], out_dir: Path, *, log: Any = print) -> dict[str, Any]:
        tests.append([s.name for s in steps])
        world.bases[rec.name] = True
        return {"passed": True, "steps": [{"step": s.name, "exit": 0} for s in steps]}

    def root_unattended(rec: HostRecord, password: str, **kw: Any) -> int:
        roots.append((rec.name, password))
        world.rooted.add(rec.name)
        return 255

    monkeypatch.setattr(mac_host, "root_unattended", root_unattended)
    hosts = tmp_path / "hosts"
    hosts.mkdir()
    clock = SimpleNamespace(now=NOW)
    lines: list[str] = []

    def lane(**kw: Any) -> MacLane:
        return MacLane(hosts_dir=hosts, runs_dir=tmp_path / "runs", key=key, clock=lambda: clock.now,
                       ops=world.ops, providers=lambda rec_or_key, **_: provider, test=run_test,
                       sleep=lambda s: None, **kw)

    return SimpleNamespace(world=world, provider=provider, hosts=hosts, tests=tests, roots=roots, lane=lane,
                           clock=clock, lines=lines, log=lines.append)


def add_host(hosts: Path, name: str, **kw: Any) -> HostRecord:
    rec = HostRecord(name=name, provider=kw.pop("provider", "ssh"), target=kw.pop("target", f"m1@{name}"), macos=15,
                     **kw)
    rec.save(hosts)
    return rec


def test_a_ready_known_host_is_used_and_nothing_is_rented(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "scw1", extra={"limits_passed": "earlier"})
    setup.world.ready["scw1"] = setup.world.bases["scw1"] = True
    lane = setup.lane(rent=True)
    assert lane.available(setup.log) is None and lane.live() and lane.host.name == "scw1"
    assert not [c for c in setup.world.calls if c.startswith("create")] and setup.tests == []


def test_a_host_without_bases_builds_them_and_passes_the_limits_test_first(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "scw1")
    setup.world.ready["scw1"] = True
    lane = setup.lane()
    assert lane.available(setup.log) is None
    assert setup.tests == [["base", "limits", "gui-base"]] or setup.tests[0][:2] == ["base", "limits"]
    assert json.loads((setup.hosts / "scw1.json").read_text())["extra"]["limits_passed"]
    lane.available(setup.log)  # held and still usable: no second test
    assert len(setup.tests) == 1


def test_an_unready_or_unreachable_host_is_skipped_and_renting_off_says_so(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "down", target="m1@unreachable")
    add_host(setup.hosts, "noroot")
    why = setup.lane().available(setup.log)
    assert why is not None and "--mac-rent" in why
    assert any("down: not reachable" in line for line in setup.lines)
    assert any("noroot: not ready (softnet_setuid, auto_login)" in line for line in setup.lines)


def test_renting_without_the_password_waits_for_a_person_and_does_not_rent_twice(setup: SimpleNamespace) -> None:
    lane = setup.lane(rent=True, max_rentals=3)
    why = lane.available(setup.log)
    assert why is not None and "pickfit mac-host root watch-20261118-1200" in why
    saved = json.loads((setup.hosts / "watch-20261118-1200.json").read_text())
    assert saved["extra"]["rented_by"] == "watch"
    assert [c for c in setup.world.calls if c.startswith(("create", "wait_ssh", "prepare"))] == [
        "create:watch-20261118-1200", "wait_ssh:watch-20261118-1200", "prepare:watch-20261118-1200"]
    setup.clock.now = NOW + timedelta(minutes=40)
    assert lane.available(setup.log) is not None
    assert len([c for c in setup.world.calls if c.startswith("create")]) == 1
    # Once a person ran the root step, the next try uses it.
    setup.world.rooted.add("watch-20261118-1200")
    assert lane.available(setup.log) is None and lane.host.name == "watch-20261118-1200"
    assert setup.roots == []


def test_renting_with_the_providers_password_roots_it_without_keeping_the_password(setup: SimpleNamespace) -> None:
    lane = setup.lane(rent=True, root_from_provider=True)
    assert lane.available(setup.log) is None
    assert setup.roots == [("watch-20261118-1200", SECRET)]
    assert "checks:watch-20261118-1200:boot" in setup.world.calls
    for path in setup.hosts.iterdir():
        assert SECRET not in path.read_text()
    assert not any(SECRET in line for line in setup.lines)
    rentals = [json.loads(line) for line in (setup.hosts / mac_batch.RENTALS).read_text().splitlines()]
    assert [r["name"] for r in rentals] == ["watch-20261118-1200"] and rentals[0]["server_type"] == "M4-S"


def test_the_rental_cap_holds(setup: SimpleNamespace) -> None:
    (setup.hosts / mac_batch.RENTALS).write_text(json.dumps({"at": (NOW - timedelta(days=2)).isoformat(),
                                                             "name": "watch-old"}) + "\n")
    why = setup.lane(rent=True, root_from_provider=True).available(setup.log)
    assert why is not None and "cap is 1" in why
    assert not [c for c in setup.world.calls if c.startswith("create")]
    setup.clock.now = NOW + timedelta(days=6)  # the old rental left the 7-day window
    assert setup.lane(rent=True, root_from_provider=True).available(setup.log) is None


def test_a_failed_rental_is_a_reason_not_a_crash(setup: SimpleNamespace) -> None:
    setup.provider.fail = "no Scaleway Mac mini of type M4-S is in stock"
    why = setup.lane(rent=True, root_from_provider=True).available(setup.log)
    assert why == "renting a Mac failed: no Scaleway Mac mini of type M4-S is in stock"


def test_idle_deletes_only_its_own_rentals_and_only_after_the_paid_day(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "scw1", provider="scaleway", deletable_at="2026-11-18T15:42:26Z")
    add_host(setup.hosts, "watch-a", provider="scaleway", created_at="2026-11-18T11:00:00Z",
             deletable_at="2026-11-19T11:00:00Z", extra={"rented_by": "watch"})
    lane = setup.lane()
    lane.idle(setup.log)
    assert setup.provider.deleted == []
    setup.clock.now = datetime(2026, 11, 19, 11, 0, 30, tzinfo=UTC)
    lane.idle(setup.log)
    assert setup.provider.deleted == ["watch-a"] and not (setup.hosts / "watch-a.json").exists()
    assert (setup.hosts / "scw1.json").exists()
    assert any("idle after its first 24 h" in line for line in setup.lines)


def test_verify_runs_on_the_hosts_gui_base_for_a_desktop_app(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "scw1", extra={"limits_passed": "x"})
    setup.world.ready["scw1"] = setup.world.bases["scw1"] = True
    boxes: list[tuple[str, bool]] = []
    calls: list[dict[str, Any]] = []

    def make_box(rec: HostRecord, gui: bool) -> Any:
        boxes.append((rec.name, gui))
        return "factory"

    def verify_task(task: Any, factory: Any, **kw: Any) -> str:
        calls.append({"factory": factory, **kw})
        return "outcome"

    lane = setup.lane(make_box=make_box, verify_task=verify_task, model="claude-opus-5-5", limits="limits")
    lane.available(setup.log)
    task = SimpleNamespace(extraction=SimpleNamespace(kind=SimpleNamespace(value="desktop_app")))
    assert lane.verify(task, Path("/tmp/x"), setup.log) == "outcome"
    assert boxes == [("scw1", True)] and calls[0]["factory"] == "factory" and calls[0]["write"] is True
    assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["limits"] == "limits"


def test_the_real_box_factory_uses_the_gui_base_and_the_hosts_ssh(setup: SimpleNamespace) -> None:
    rec = HostRecord(name="scw1", provider="ssh", target="m1@203.0.113.7", key="/k", macos=15)
    factory = setup.lane().box_factory(rec, True)
    box = factory("run-1", "agent")
    assert box.base == "pickfit-macos-15-gui" and box.display == "vnc" and box.host.target == "m1@203.0.113.7"
    assert setup.lane().box_factory(rec, False)("run-1", "agent").base == "pickfit-macos-15"


def test_status_reports_hosts_and_rentals(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "watch-a", extra={"rented_by": "watch"}, deletable_at="2026-11-19T11:00:00Z")
    status = setup.lane(rent=True, policy=Policy(min_batch=4, max_wait=timedelta(hours=12))).status()
    assert status["policy"] == "when 4 wait or the oldest has waited 12 h" and status["rent"] is True
    assert status["hosts"] == [{"name": "watch-a", "provider": "ssh", "target": "m1@watch-a", "macos": 15,
                                "deletable_at": "2026-11-19T11:00:00Z", "rented_by_watch": True}]
    json.dumps(status)


def test_the_same_configuration_error_twice_stops_the_retries_until_something_changes(setup: SimpleNamespace,
                                                                                     monkeypatch) -> None:
    # 11/18: a base whose build failed the same way every 30 minutes, for two hours.
    add_host(setup.hosts, "scw1")
    setup.world.ready["scw1"] = True

    def failing(rec: HostRecord, steps: list[Any], out_dir: Path, *, log: Any = print) -> dict[str, Any]:
        setup.tests.append([s.name for s in steps])
        return {"passed": False, "steps": [{"step": "base", "exit": 1}]}

    lane = setup.lane()
    monkeypatch.setattr(lane, "_test", failing)
    first = lane.available(setup.log)
    assert first is not None and "needs an operator" not in first and "bases or limits test failed" in first
    second = lane.available(setup.log)  # watch's next try, 30 minutes on
    assert second.startswith("needs an operator: no Mac host is ready") and "pickfit mac-host clear" in second
    assert len(setup.tests) == 2
    calls = list(setup.world.calls)
    assert lane.available(setup.log) == second and setup.world.calls == calls  # not tried again: nothing ran
    assert len(setup.tests) == 2 and lane.status()["needs_operator"] == second
    # Someone fixed the host (its record changed): the lane tries again.
    add_host(setup.hosts, "scw1", extra={"note": "rebuilt by hand"})
    monkeypatch.setattr(lane, "_test", setup.lane()._test)
    assert lane.available(setup.log) is None and lane.status()["needs_operator"] is None
    assert not (setup.hosts / mac_host.OPERATOR_FILE).exists()


def test_what_passes_by_itself_is_retried_as_before(setup: SimpleNamespace) -> None:
    add_host(setup.hosts, "down", target="m1@unreachable")
    lane = setup.lane()
    for _ in range(3):  # a host that does not answer may answer next time
        assert "needs an operator" not in lane.available(setup.log)
    setup.provider.fail = "no Scaleway Mac mini of type M4-S is in stock in fr-par-1"
    lane = setup.lane(rent=True, root_from_provider=True, max_rentals=9)
    for _ in range(3):
        assert lane.available(setup.log).startswith("renting a Mac failed: no Scaleway")
    setup.provider.fail = "Quota exceeded for resources 'AsServersType_M4_S' (0/0)"
    assert lane.available(setup.log).startswith("renting a Mac failed: Quota exceeded")
    assert lane.available(setup.log).startswith("needs an operator: renting a Mac failed: Quota exceeded")
    assert len([c for c in setup.world.calls if c.startswith("create")]) == 5  # the sixth was not tried
    assert lane.available(setup.log).startswith("needs an operator")
    assert len([c for c in setup.world.calls if c.startswith("create")]) == 5
    mac_host.clear_hold(setup.hosts)  # `pickfit mac-host clear`
    lane.available(setup.log)
    assert len([c for c in setup.world.calls if c.startswith("create")]) == 6


def test_scaleway_root_password_reads_only_that_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(argv: list[str], **kw: Any) -> Any:
        seen.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"id": "srv-1", "sudo_password": SECRET}), stderr="")

    monkeypatch.setattr(mac_host.subprocess, "run", run)
    rec = HostRecord(name="h", provider="scaleway", server_id="srv-1", zone="fr-par-1")
    assert mac_host.ScalewayProvider().root_password(rec) == SECRET
    assert seen == [["scw", "apple-silicon", "server", "get", "srv-1", "zone=fr-par-1", "-o", "json"]]
    assert mac_host.SshProvider().root_password(rec) is None


def test_root_unattended_pipes_the_password_on_stdin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict[str, Any] = {}

    def run(argv: list[str], **kw: Any) -> Any:
        got.update(argv=argv, **kw)
        return SimpleNamespace(returncode=255)

    rec = HostRecord(name="h", provider="scaleway", target="m1@203.0.113.7", key="/k")
    assert mac_host.root_unattended(rec, SECRET, runner=run) == 255
    assert SECRET not in " ".join(got["argv"]) and got["input"] == SECRET + "\n"
    assert got["argv"][-1].endswith("--password-stdin") and "-t" not in got["argv"]
