"""RootVmBox (root_box.py): the full-privilege VM box on any provider, against an in-memory machine. The capability
flags, the cost cap, the outside probe, and how a run made in it is marked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import box_ledger
from pickfit.verify import root_box as rb
from pickfit.verify.box import (
    Box,
    BoxBudgetError,
    BoxCapabilities,
    BoxError,
    DockerBox,
    _Capture,
    stop_reason,
)

READY = "sudo_uid 0\ninit systemd\nsystemd running\ndocker 26.1.5\n"
RATE = 0.36  # USD an hour: a cent every hundred seconds


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(rb, "_now", clock.now)
    monkeypatch.setattr(rb, "_sleep", clock.sleep)
    return clock


class FakeMachine(rb.PrivilegedMachine):
    """A provider's full-privilege VM, in memory: a script of answers to root's commands and a record of calls."""

    provider = "fake"
    image = "fake-rootvm:1"

    def __init__(self, script: dict[str, tuple[int, str, str]] | None = None, usd_per_hour: float = RATE) -> None:
        self.script = {"sudo_uid": (0, READY, ""), **(script or {})}
        self.usd_per_hour = usd_per_hour
        self.machine_id: str | None = None
        self.address: str | None = None
        self.ran: list[tuple[list[str], int, bytes | None]] = []
        self.calls: list[tuple[str, Any]] = []
        self.rules: set[int] = set()
        self.status = "never started"
        self.fail: dict[str, Exception] = {}

    def _call(self, name: str, arg: Any = None) -> None:
        self.calls.append((name, arg))
        if name in self.fail:
            raise self.fail[name]

    def start(self) -> None:
        self._call("start")
        self.machine_id, self.address, self.status = "vm-1", "198.51.100.9", "running"

    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> Any:
        raise AssertionError("the fake answers run() itself")

    def run(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None, head: int = 8000,
            tail: int = 24000) -> tuple[int, _Capture, _Capture, bool]:
        self.ran.append((argv, timeout_s, stdin))
        text = " ".join(argv)
        code, out, err = next((answer for needle, answer in self.script.items() if needle in text), (0, "", ""))
        captured = _Capture(head, tail), _Capture(head, tail)
        captured[0].feed(out.encode())
        captured[1].feed(err.encode())
        return code, captured[0], captured[1], False

    def set_egress(self, enabled: bool) -> None:
        self._call("set_egress", enabled)

    def close(self) -> None:
        self._call("close")
        self.status = "terminated"

    def usd_per_second(self) -> float:
        return self.usd_per_hour / 3600

    def probe_ingress(self, port: int, enabled: bool) -> None:
        self._call("probe_ingress", (port, enabled))
        self.rules.add(port) if enabled else self.rules.discard(port)

    def probed_ports(self) -> list[int]:
        return sorted(self.rules)

    def state(self) -> str:
        return self.status

    def outside_view(self) -> dict[str, Any]:
        return {"metadata_endpoint": "disabled", "instance_profile": None, "key_pair": None}


class Server:
    """What the harness's own connection to the VM finds: nothing, an open port, or an HTTP answer."""

    def __init__(self, answer: bytes | None = b"", refuse: int = 0) -> None:
        self.answer, self.refuse, self.tried, self.sent = answer, refuse, [], b""

    def __call__(self, where: tuple[str, int], timeout: float) -> Any:
        self.tried.append(where)
        if self.answer is None or len(self.tried) <= self.refuse:
            raise ConnectionRefusedError("nothing answers")
        return self

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *exc: Any) -> None:
        pass

    def settimeout(self, seconds: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, n: int) -> bytes:
        chunk, self.answer = (self.answer or b"")[:n], b""
        return chunk


def box(machine: FakeMachine | None = None, **kw: Any) -> tuple[rb.RootVmBox, FakeMachine]:
    machine = machine or FakeMachine()
    return rb.RootVmBox(machine, **{"log": lambda line: None, "connect": Server(None), **kw}), machine


# -- the capability flags


def test_a_box_gives_none_of_the_capabilities_unless_it_says_so():
    assert Box.capabilities == BoxCapabilities() and not Box.capabilities.full_privilege
    assert Box.capabilities.granted() == []
    assert DockerBox(build=False).capabilities == BoxCapabilities()  # every box that is not this one
    from pickfit.verify.linux_box import LinuxBox

    assert LinuxBox.capabilities == BoxCapabilities()
    b, _ = box()
    assert b.capabilities == BoxCapabilities(root=True, systemd=True, container_engine="docker", kernel_modules=True)
    assert b.capabilities.full_privilege and b.runner == "fake-rootvm"  # the provider's name, never a fixed one
    assert b.capabilities.granted() == ["root", "systemd", "container_engine", "kernel_modules"]
    assert BoxCapabilities(container_engine="podman").granted() == ["container_engine"]


def test_only_a_machine_that_gives_root_makes_a_root_box_and_a_lesser_one_says_what_it_gives():
    plain = FakeMachine()
    plain.capabilities = BoxCapabilities()
    with pytest.raises(ValueError, match="LinuxBox"):
        rb.RootVmBox(plain)
    lesser = FakeMachine({"sudo_uid": (0, "sudo_uid 0\ninit sh\nsystemd \n", "")})
    lesser.capabilities = BoxCapabilities(root=True)  # another provider: root on a machine with no init or engine
    b, _ = box(lesser)
    b.start()
    assert "No container engine" in b.describe() and "systemd" not in b.describe()
    assert b.evidence()["capabilities"] == ["root"]


# -- the box user


def test_the_box_user_runs_with_its_groups_and_can_sudo():
    b, m = box()
    b.start()
    assert m.calls[0] == ("start", None)
    assert any("/usr/bin/install" in argv and "/home/sbx/work" in argv for argv, _, _ in m.ran)
    b.exec("sudo apt-get install -y nginx", 120, cwd="/tmp")
    argv, timeout_s, _ = m.ran[-1]
    assert argv[:6] == [rb.RUNUSER, "-u", "sbx", "--", "/usr/bin/env", "-i"]
    text = " ".join(argv)
    assert "setpriv" not in text and "no-new-privs" not in text and "ulimit" not in text  # nothing sudo would trip on
    assert "HOME=/home/sbx" in argv and "XDG_RUNTIME_DIR=/run/user/1000" in argv
    assert next(a for a in argv if a.startswith("PATH=")).endswith("/usr/sbin:/sbin")
    assert not any(a.split("=")[0].endswith(("KEY", "TOKEN", "SECRET")) for a in argv if "=" in a)
    assert argv[-1] == "cd /tmp && exec /usr/bin/timeout -s KILL 120 /usr/bin/bash -c 'sudo apt-get install -y nginx'"
    assert timeout_s == 120
    b.write_file("notes/a.txt", "hi")
    argv, _, stdin = m.ran[-1]
    assert stdin == b"hi" and argv[:3] == [rb.RUNUSER, "-u", "sbx"] and "notes/a.txt" in argv[-1]
    m.script["head -c"] = (0, "file body", "")
    assert b.read_file("notes/a.txt") == b"file body" and m.ran[-1][0][:3] == [rb.RUNUSER, "-u", "sbx"]
    assert b.harness_read("/etc/os-release", 100) == b"file body" and m.ran[-1][0][0] == "/usr/bin/head"  # as root
    assert b.harness_exec(["/usr/bin/id", "-u"], 10).command == "/usr/bin/id -u"
    with pytest.raises(BoxError, match="no uid of pickfit's own"):
        b.harness_exec(["/usr/bin/id"], 10, as_uid=1001)  # no uid there is out of the box user's reach


def test_what_the_agent_is_told():
    b, m = box()
    text = b.describe()
    for said in ("passwordless sudo", "systemd is PID 1", "Docker is installed", "Kernel modules load",
                 "only DNS, HTTP (port 80) and HTTPS (port 443) leave", "No API keys", "destroyed after this run"):
        assert said in text
    assert "sudo" in b.user_rule and b.kind == "Linux virtual machine" and "blank" not in text
    m.extra_disk_gb = 8
    assert "A blank 8 GB disk" in b.describe() and "never touch the system disk" in b.describe()


def test_a_vm_that_lacks_what_it_promises_does_not_start():
    for lacking, script in (("the box user's sudo", "sudo_uid 1000\ninit systemd\nsystemd running\ndocker 26\n"),
                            ("systemd as PID 1", "sudo_uid 0\ninit sh\nsystemd offline\ndocker 26\n"),
                            ("systemd as PID 1", "sudo_uid 0\ninit systemd\nsystemd starting\ndocker 26\n"),
                            ("the container engine", "sudo_uid 0\ninit systemd\nsystemd degraded\npermission denied\n")):
        b, m = box(FakeMachine({"sudo_uid": (0, script, "")}))
        with pytest.raises(BoxError, match=lacking):
            b.start()
        assert m.calls[-1] == ("close", None) and not b.started and b.ended == "terminated"
    b, _ = box(FakeMachine({"sudo_uid": (0, "sudo_uid 0\ninit systemd\nsystemd degraded\ndocker 26\n", "")}))
    b.start()  # a failed unit of the image's is not a missing init
    assert b.facts["systemd"] == "degraded"


def test_the_network_is_the_providers_to_cut_and_nothing_is_asked_of_the_vm():
    b, m = box()
    b.start()
    before = len(m.ran)
    b.set_network(False)
    b.set_network(False)  # already off
    assert m.calls.count(("set_egress", False)) == 1 and not b.network_enabled and len(m.ran) == before
    m.fail["set_egress"] = BoxError("EC2 does not describe vm-1 as online")
    with pytest.raises(BoxError):
        b.set_network(True)
    assert not b.network_enabled  # it stays what it really is


# -- the cost cap


def run_ledger(run_id: str, *rows: dict[str, Any]) -> None:
    for n, row in enumerate(rows):
        ended = row.pop("ended", True)
        box_ledger().open_box(box_id=f"b{n}", provider="fake", run_id=run_id, lane="linux-root",
                              started_at="2026-11-21T10:00:00+08:00", **row)
        if ended:
            box_ledger().close_box(f"b{n}", ended_at="2026-11-21T11:00:00+08:00")


def test_the_records_machines_stop_at_their_cap_and_the_run_ends_as_budget_exceeded(clock: Clock):
    lines: list[str] = []
    b, m = box(run_id="verify-hal0-20261121-101500-ab12", log=lines.append)
    assert b.cap_usd == rb.COST_CAP_USD == 0.50
    b.start()
    assert b.spent_usd() == pytest.approx(RATE / 60)  # a minute at least, as the provider bills it
    clock.t += 3600  # US$0.36 of this box
    assert b.exec("true", 10).ok and b.spent_usd() == pytest.approx(0.36)
    clock.t += 1500  # US$0.51
    with pytest.raises(BoxBudgetError, match="budget_exceeded: the record's machines cost US\\$0.51") as stopped:
        b.exec("make install", 600)
    assert m.calls[-1] == ("close", None) and not b.started and b.stopped_for == "budget_exceeded"
    assert stop_reason(stopped.value) == "budget" and stop_reason(BoxError("ssh lost")) == "box_error"
    assert isinstance(stopped.value, BoxError)  # so every place that survives a failed box survives this
    assert not any(argv[-1].endswith("'make install'") for argv, _, _ in m.ran)  # the command never ran
    assert any("closing vm-1" in line for line in lines)
    for call in (lambda: b.exec("true", 10), lambda: b.read_file("x"), lambda: b.write_file("x", "y")):
        with pytest.raises(BoxBudgetError, match="budget_exceeded"):
            call()  # nothing runs in it afterwards, and every call says why
    assert b.evidence()["cost"]["spent_usd"] == pytest.approx(0.51)  # a closed box costs nothing more
    clock.t += 3600
    assert b.evidence()["cost"]["spent_usd"] == pytest.approx(0.51)
    assert b.evidence()["stopped_for"] == "budget_exceeded" and b.evidence()["cost"]["cap_usd"] == 0.50


def test_the_cap_counts_the_records_other_machines_and_a_box_that_cannot_pay_its_first_minute_never_starts():
    run_id = "verify-hal0-20261121-101500-ab12"
    run_ledger(run_id, {"rate_usd_per_hour": 0.30, "provider_ref": "vm-agent"},  # an hour: US$0.30
               {"rate_usd_per_hour": 0.15, "provider_ref": "vm-confirm"})  # US$0.15
    box_ledger().open_box(box_id="other-run", provider="fake", run_id="verify-other-20261121-101500-ab12",
                          rate_usd_per_hour=9.0, started_at="2026-11-21T10:00:00+08:00")
    b, m = box(run_id=run_id)
    b.start()
    assert b.evidence()["cost"]["other_machines_usd"] == pytest.approx(0.45)  # this record's only
    assert b.spent_usd() == pytest.approx(0.45 + RATE / 60)
    late, m2 = box(run_id=run_id, cap_usd=0.45)
    with pytest.raises(BoxBudgetError, match="budget_exceeded"):
        late.start()
    assert m2.calls == [] and late.stopped_for == "budget_exceeded"  # nothing was launched
    unread, m3 = box(run_id=run_id, ledger=lambda: (_ for _ in ()).throw(OSError("disk")))
    unread.start()  # a ledger that cannot be read never stops a box: the cap counts this box alone
    assert unread.spent_usd() == pytest.approx(RATE / 60)


def test_a_command_never_runs_past_what_the_cap_still_pays_for(clock: Clock):
    b, m = box(cap_usd=0.10)  # 1000 seconds at this rate
    b.start()
    clock.t += 900
    b.exec("cargo build", 600)
    assert m.ran[-1][1] == 100 and "KILL 100 " in m.ran[-1][0][-1]
    free, m = box(FakeMachine(usd_per_hour=0.0))
    free.start()
    free.exec("true", 30)
    assert m.ran[-1][1] == 30  # a machine with no price has no cap to reach


def test_the_cap_can_be_lowered_from_the_environment_and_never_raised(monkeypatch):
    monkeypatch.setenv(rb.COST_CAP_ENV, "0.2")
    assert rb.cost_cap_usd() == 0.2 and box()[0].cap_usd == 0.2
    monkeypatch.setenv(rb.COST_CAP_ENV, "5")
    assert rb.cost_cap_usd() == 0.50
    monkeypatch.setenv(rb.COST_CAP_ENV, "a lot")
    assert rb.cost_cap_usd() == 0.50


# -- evidence from outside


def test_an_outside_probe_is_the_harnesss_own_connection_through_a_rule_made_for_it():
    server = Server(b"HTTP/1.0 200 OK\r\nServer: SimpleHTTP\r\n\r\n")
    b, m = box(FakeMachine({"ss -H": (0, "0.0.0.0:8080\n", "")}), connect=server)
    b.start()
    seen = b.probe_port(8080, path="/health")
    assert seen["outside"] == "open" and seen["status"] == 200 and seen["inside_listen"] == ["0.0.0.0:8080"]
    assert server.tried == [("198.51.100.9", 8080)] and server.sent.startswith(b"GET /health HTTP/1.0\r\n")
    probes = [c for c in m.calls if c[0] == "probe_ingress"]
    assert probes == [("probe_ingress", (8080, True)), ("probe_ingress", (8080, False))] and m.rules == set()
    assert b.outside == [seen] and b.evidence()["outside"] == [seen]
    plain = Server(b"")  # a port that opens and is not asked anything
    b.outside.clear()
    b._connect = plain
    assert b.probe_port(5432)["outside"] == "open" and b.outside[0]["status"] is None and plain.sent == b""


def test_a_server_on_loopback_reads_closed_from_outside_and_that_is_not_an_error(clock: Clock):
    b, m = box(FakeMachine({"ss -H": (0, "127.0.0.1:8765\n", "")}), connect=Server(None))
    b.start()
    began = clock.t
    seen = b.probe_port(8765)
    assert seen["outside"] == "closed" and seen["inside_listen"] == ["127.0.0.1:8765"] and "error" not in seen
    assert rb.PROBE_WAIT_S <= clock.t - began < rb.PROBE_WAIT_S + 2  # it kept trying while the rule took effect
    assert m.rules == set()
    late = Server(b"", refuse=3)  # the rule took a moment: the fourth try opens
    b._connect = late
    assert b.probe_port(8766)["outside"] == "open" and len(late.tried) == 4


def test_a_probe_never_raises_and_always_takes_its_rule_back():
    b, m = box(connect=Server(b""))
    assert b.probe_port(8080)["outside"] == "error"  # not started
    b.start()
    m.fail["probe_ingress"] = BoxError("port 22 is not one an outside probe may open")
    seen = b.probe_port(22)
    assert seen["outside"] == "error" and "not one an outside probe may open" in seen["error"]

    def broken(where: tuple[str, int], timeout: float) -> Any:
        raise RuntimeError("the socket library broke")

    del m.fail["probe_ingress"]
    b._connect = broken
    seen = b.probe_port(8081)
    assert seen["outside"] == "error" and ("probe_ingress", (8081, False)) in m.calls and m.rules == set()


def test_a_background_server_the_box_waited_for_is_also_looked_at_from_outside():
    server = Server(b"")
    b, m = box(FakeMachine({"ss -H": (0, "*:8000\n", "")}), connect=server)
    b.start()
    script = b.background("python3 -m http.server 8000", 8000, 20, "bg1")
    assert "nohup" in script and "/dev/tcp/127.0.0.1/8000" in script  # the same script every box runs
    result = b.exec(script, 40)
    assert result.ok and [p["port"] for p in b.outside] == [8000] and b.outside[0]["outside"] == "open"
    assert server.tried == [("198.51.100.9", 8000)]
    b.exec(script, 40)  # only the run it was written for
    b.exec(b.background("sleep 100", None, 5, "bg2"), 20)  # no port: nothing to look at
    assert len(b.outside) == 1
    m.script["nohup"] = (1, "process exited", "")
    b.exec(b.background("python3 -m http.server 8001", 8001, 20, "bg3"), 40)
    assert len(b.outside) == 1  # a server that did not come up is not probed


# -- how the run is marked


def test_the_boxs_evidence_says_it_was_a_full_privilege_box_and_what_was_seen_from_where(tmp_path: Path):
    b, m = box(run_id="verify-hal0-20261121-101500-ab12")
    b.start()
    b.close()
    b.close()  # twice is fine
    assert m.calls.count(("close", None)) == 1 and b.ended == "terminated"  # the provider's word, asked after
    seen = b.evidence()
    assert seen["runner"] == "fake-rootvm" and seen["full_privilege"] is True
    assert seen["capabilities"] == ["root", "systemd", "container_engine", "kernel_modules"]
    assert seen["inside_evidence"].startswith("forgeable") and seen["offline_cut"] == "stateless"
    assert seen["provider_view"] == {"metadata_endpoint": "disabled", "instance_profile": None, "key_pair": None}
    assert seen["inside_facts"] == {"sudo_uid": "0", "init": "systemd", "systemd": "running", "docker": "26.1.5"}
    assert seen["ended"] == "terminated" and seen["machine"] == "vm-1"
    path = rb.save_box_evidence(b, tmp_path, "agent")
    assert path == tmp_path / "box_agent.json" and json.loads(path.read_text())["full_privilege"] is True
    from verify_fakes import FakeBox

    assert rb.save_box_evidence(FakeBox(), tmp_path, "replay") is None and not (tmp_path / "box_replay.json").exists()
    m.fail["close"] = RuntimeError("the API is down")
    b2, m2 = box(m)
    b2.started = True
    b2.close()  # never raises: the provider's reaper ends the machine by its tags


class RootFake:
    """A box factory for the pipeline: FakeBox with a full-privilege box's evidence, whose replay hits the cap."""

    def __init__(self, cap_role: str | None) -> None:
        self.cap_role = cap_role
        self.made: list[tuple[str, Any]] = []

    def __call__(self, run_id: str, role: str) -> Any:
        from test_verify_pipeline import SCRIPT
        from verify_fakes import FakeBox

        capped = role == self.cap_role

        class Fake(FakeBox):
            runner = "ec2-rootvm"
            capabilities = rb.FULL

            def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> Any:
                if capped and len(self.ran) >= 1:
                    raise BoxBudgetError("budget_exceeded: the record's machines cost US$0.5012, at its US$0.50 cap")
                return super().exec(command, timeout_s, cwd=cwd)

            def evidence(self) -> dict[str, Any]:
                return {"runner": self.runner, "full_privilege": True, "outside": []}

        made = Fake(dict(SCRIPT))
        self.made.append((role, made))
        return made


def test_a_run_in_a_full_privilege_box_is_marked_by_its_runner_and_keeps_each_boxs_evidence(tmp_path: Path):
    from test_verify_pipeline import agent_turns, judge_answer, verify
    from verify_fakes import FakeServer

    boxes = RootFake(None)
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), boxes)  # type: ignore[arg-type]
    assert outcome.passed and outcome.run.runner == "ec2-rootvm"  # where a run's runner is recorded, the mark is
    assert [role for role, _ in boxes.made] == ["agent", "replay"]  # a fresh box each, as everywhere
    for role in ("agent", "replay"):
        assert json.loads((outcome.evidence_dir / f"box_{role}.json").read_text())["full_privilege"] is True


def test_a_cap_reached_in_the_agents_box_or_in_the_replays_ends_the_run_as_budget_exceeded(tmp_path: Path):
    from test_verify_pipeline import agent_turns, verify
    from verify_fakes import FakeServer

    boxes = RootFake("agent")
    outcome, _ = verify(tmp_path / "a", FakeServer(*agent_turns()), boxes)  # type: ignore[arg-type]
    assert outcome.run.level == "unverified" and outcome.run.unverified_reason == "budget_exceeded"
    assert [role for role, _ in boxes.made] == ["agent"] and boxes.made[0][1].closed
    report = json.loads((outcome.evidence_dir / "report.json").read_text())
    assert report["stop_reason"] == "budget" and "US$0.50 cap" in report["error"]
    boxes = RootFake("replay")
    outcome, _ = verify(tmp_path / "r", FakeServer(*agent_turns()), boxes)  # type: ignore[arg-type]
    assert outcome.run.level == "unverified" and outcome.run.unverified_reason == "budget_exceeded"
    assert not outcome.run.replayed and "budget_exceeded" in outcome.run.blocking_error
    assert all(made.closed for _, made in boxes.made)


def test_a_broken_box_that_is_not_the_cap_is_still_an_ordinary_box_error(tmp_path: Path):
    from test_verify_pipeline import SCRIPT, agent_turns, verify
    from verify_fakes import FakeBox, FakeServer

    class Lost(FakeBox):
        def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> Any:
            raise BoxError("the ec2 machine stopped answering during this command")

    outcome, _ = verify(tmp_path, FakeServer(*agent_turns()), lambda run_id, role: Lost(dict(SCRIPT)))  # type: ignore[arg-type]
    assert outcome.run.unverified_reason == "other"
    assert json.loads((outcome.evidence_dir / "report.json").read_text())["stop_reason"] == "box_error"
