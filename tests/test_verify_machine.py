"""The provider seam (machine.py): LinuxBox and WebBox on a machine that is not Modal's, and ModalBox as one
provider of the same box. Nothing leaves the process."""

from __future__ import annotations

from typing import Any

import pytest

from pickfit.verify import linux_box as lb
from pickfit.verify import machine as m
from pickfit.verify import modal_box as mb
from pickfit.verify import web_box
from pickfit.verify.box import BoxError, BoxLimits


class Stdin:
    def __init__(self) -> None:
        self.data, self.eof = b"", False

    def write(self, data: bytes) -> None:
        self.data += data

    def write_eof(self) -> None:
        self.eof = True

    def drain(self) -> None:
        pass


class Proc:
    def __init__(self, code: int, out: list[bytes], err: list[bytes]) -> None:
        self.code, self.stdout, self.stderr, self.stdin = code, out, err, Stdin()

    def wait(self) -> int:
        return self.code


class FakeMachine(m.Machine):
    """A provider with nothing of Modal's: no sandbox object, no client, no allowlist arguments."""

    provider = "fake"
    image = "fake-image:1"

    def __init__(self, runtime: str = "vm", replies: list[Any] | None = None) -> None:
        self.runtime = runtime
        self.replies = list(replies or [])
        self.spawned: list[tuple[list[str], int, str | None]] = []
        self.procs: list[Proc] = []
        self.egress: list[bool] = []
        self.starts = self.closes = 0
        self.fail_egress = False

    def start(self) -> None:
        self.starts += 1
        self.machine_id = "m-1"

    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> Proc:
        self.spawned.append((list(argv), timeout_s, workdir))
        default = (0, [b"netns_pid 4242\n"], []) if "/usr/bin/unshare " in argv[-1] else (0, [b"ok"], [])
        reply = self.replies.pop(0) if self.replies else default
        if isinstance(reply, Exception):
            raise reply
        self.procs.append(Proc(*reply))
        return self.procs[-1]

    def set_egress(self, enabled: bool) -> None:
        if self.fail_egress:
            raise BoxError("fake egress failed")
        self.egress.append(enabled)

    def close(self) -> None:
        self.closes += 1

    def usd_per_second(self) -> float:
        return 0.001


def test_a_linux_box_runs_on_a_machine_that_is_not_modal():
    machine = FakeMachine("gvisor")
    box = lb.LinuxBox(machine, limits=BoxLimits(), log=lambda s: None)
    box.start()
    assert machine.starts == 1 and box.runner == "fake-gvisor" and box.image == "fake-image:1"
    netns, uplink, mkdir, chown = (argv for argv, _, _ in machine.spawned[:4])
    assert netns[-1] == lb.netns_script() and uplink[-1] == lb.uplink_script(4242, True) and box.netns_pid == 4242
    assert mkdir[:2] == ["/usr/bin/mkdir", "-p"] and chown[:3] == ["/usr/bin/chown", "-R", "1000:1000"]
    result = box.exec("echo hi", 30)
    argv, timeout_s, _ = machine.spawned[-1]
    # The box user's command: into its network namespace as NET_UID, then down to the box user, under the limits.
    assert argv[:7] == lb._drop_to(lb.NET_UID) and "--target=4242" in argv and argv[-3:-1] == ["/usr/bin/bash", "-c"]
    assert argv[-1].startswith("ulimit -u 256 -n 1024 ") and "timeout -s KILL 30 " in argv[-1]
    assert timeout_s == 30 + machine.grace_s  # the host's backstop sits past the in-box kill
    assert (result.exit_code, result.stdout, result.command) == (0, "ok", "echo hi")
    assert box.usd_per_second() == 0.001
    box.close()
    box.close()
    assert machine.closes == 1 and not box.started
    with pytest.raises(BoxError, match="not started"):
        box.exec("true", 5)


def test_a_vm_machine_is_hardened_by_root_then_cut_by_the_provider_and_nftables():
    machine = FakeMachine("vm")
    box = lb.LinuxBox(machine, log=lambda s: None)
    box.start()
    harden = machine.spawned[0][0]
    assert harden[0] == "/usr/bin/bash" and harden[-1] == lb.VM_HARDEN
    assert machine.procs[0].stdin.data == lb.NO_VSOCK_SOURCE.encode() and machine.procs[0].stdin.eof
    assert box.user_argv("true", 5, "/w")[7:11] == [lb.PYTHON, "-I", "-S", lb.NO_VSOCK]  # the seccomp filter
    before = len(machine.spawned)
    box.set_network(False)
    box.set_network(False)  # no-op
    box.set_network(True)
    assert machine.egress == [False, True]
    assert [argv[-1] for argv, _, _ in machine.spawned[before:]] == [lb.DNS_BLOCK, lb.DNS_UNBLOCK]


def test_a_gvisor_cut_kills_the_uplink_before_the_provider_closes_egress():
    machine = FakeMachine("gvisor")
    box = lb.LinuxBox(machine, log=lambda s: None)
    box.start()
    machine.replies = [(1, [b"tap0 is still there\n"], [])]
    with pytest.raises(BoxError, match="cutting the network uplink failed: tap0 is still there"):
        box.set_network(False)
    assert box.network_enabled and machine.egress == []
    box.set_network(False)
    assert machine.egress == [False] and machine.spawned[-1][0][-1] == lb.uplink_script(4242, False)
    box.set_network(True)
    assert machine.egress == [False, True] and machine.spawned[-1][0][-1] == lb.uplink_script(4242, True)


def test_a_provider_that_cannot_close_egress_stops_the_box_from_claiming_offline():
    machine = FakeMachine("vm")
    box = lb.LinuxBox(machine, log=lambda s: None)
    box.start()
    machine.fail_egress = True
    before = len(machine.spawned)
    with pytest.raises(BoxError, match="fake egress failed"):
        box.set_network(False)
    assert box.network_enabled and len(machine.spawned) == before  # no offline rule on a box that is still online


def test_a_machine_whose_start_fails_leaves_nothing_to_close():
    class Dead(FakeMachine):
        def start(self) -> None:
            raise BoxError("fake create failed")

    machine = Dead("vm")
    box = lb.LinuxBox(machine, log=lambda s: None)
    with pytest.raises(BoxError, match="fake create failed"):
        box.start()
    box.close()
    assert not box.started and machine.closes == 0 and machine.spawned == []


def test_a_setup_step_that_fails_closes_the_machine():
    machine = FakeMachine("vm", replies=[(1, [], [b"sysctl: permission denied\n"])])
    with pytest.raises(BoxError, match="VM hardening failed: sysctl: permission denied"):
        lb.LinuxBox(machine, log=lambda s: None).start()
    assert machine.closes == 1


def test_a_machine_with_an_unknown_runtime_is_refused():
    assert m.RUNTIMES == ("gvisor", "vm")
    with pytest.raises(ValueError, match="runtime must be one of"):
        lb.LinuxBox(FakeMachine("firecracker"))


def test_machine_run_keeps_output_feeds_stdin_and_explains_a_failure():
    machine = FakeMachine(replies=[(3, [b"ou", b"t"], [b"err"])])
    code, out, err, gave_up = machine.run(["/usr/bin/cat"], 10, stdin=b"data")
    assert (code, out.text(), err.text(), gave_up) == (3, "out", "err", False)
    assert machine.procs[0].stdin.data == b"data" and machine.procs[0].stdin.eof
    assert machine.spawned[0][1] == 10 + machine.grace_s
    machine.replies = [RuntimeError("gone")]
    with pytest.raises(BoxError, match="fake exec failed: RuntimeError: gone"):
        machine.run(["/usr/bin/true"], 5)


def test_a_command_the_machine_never_returns_from_is_given_up_on():
    import threading

    class Hanging(Proc):
        def wait(self) -> int:
            threading.Event().wait()
            return 0

    class Stuck(FakeMachine):
        grace_s = 0

        def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> Proc:
            return Hanging(0, [b"partial"], [])

    code, out, _, gave_up = Stuck().run(["/usr/bin/sleep", "9"], 1)
    assert (code, out.text(), gave_up) == (124, "partial", True)


def test_modal_is_one_provider_of_the_same_box():
    box = mb.ModalBox(runtime="vm", client=object(), log=lambda s: None)
    assert isinstance(box, lb.LinuxBox) and isinstance(box.machine, m.Machine)
    assert box.machine.provider == "modal" and box.machine.runtime == "vm" and box.runner == "modal-vm"
    assert box.create_kwargs()["outbound_cidr_allowlist"] == m.ONLINE_CIDRS == mb.ONLINE_CIDRS
    # What the box does inside the machine is not Modal's: one object under both names.
    assert mb.DNS_BLOCK is lb.DNS_BLOCK and mb.netns_script is lb.netns_script
    assert mb.NO_VSOCK_SOURCE is lb.NO_VSOCK_SOURCE and mb.public_cidrs is m.public_cidrs


def test_the_image_recipe_is_the_same_for_every_provider():
    recipe = lb.image_recipe("vm", display=True, toolchain=True)
    assert recipe.kinds == ("vm", "gui", "build") and recipe.commands == (lb.VGL_INSTALL, lb.TOOLCHAIN_INSTALL)
    name, packages = mb.image_layers("vm", True, False, True)
    assert recipe.packages == packages and recipe.tag(mb.sandbox_image_tag()) == name
    plain = lb.image_recipe()
    assert plain.packages == () and plain.commands == () and plain.tag("plain:1") == "plain:1"


def started_web(machine: FakeMachine) -> web_box.WebBox:
    box = web_box.WebBox(site="example.com", machine=machine, log=lambda s: None)
    box.start({"site": "example.com"})
    return box


def test_the_web_box_sets_up_any_machine():
    # The rules, four files, the guard's start, then the probe that sees its port.
    machine = FakeMachine("vm", replies=[(0, [b"2\n"], []), *[(0, [], [])] * 5, (0, [b"up\n"], [])])
    box = started_web(machine)
    assert machine.starts == 1 and box.sandbox_id == "m-1" and box.usd_per_second() == 0.001
    assert machine.spawned[0][0][-1] == web_box.RULES
    assert machine.procs[1].stdin.data == mb.NO_VSOCK_SOURCE.encode()  # the seccomp filter goes in as root
    assert "/opt/guard/bin/mitmdump" in machine.spawned[5][0][-1]
    assert machine.spawned[0][1] == 60 + 15
    box.set_offline(True)
    assert machine.spawned[-1][0][-1] == web_box.OFFLINE_ON
    assert box.read("/home/web/evidence/a.png") == b"ok"
    assert machine.spawned[-1][0][:3] == ["/usr/bin/head", "-c", "50000000"]
    box.close()
    box.close()
    assert machine.closes == 1


def test_a_web_box_whose_rules_do_not_load_closes_the_machine():
    machine = FakeMachine("vm", replies=[(0, [b"0\n"], [b"nft: no such table\n"])])
    with pytest.raises(BoxError, match="network rules failed"):
        started_web(machine)
    assert machine.closes == 1


def test_the_web_harness_talks_over_the_machines_process(tmp_path):
    machine = FakeMachine("vm", replies=[(0, [b"2\n"], []), *[(0, [], [])] * 5, (0, [b"up\n"], [])])
    box = started_web(machine)
    machine.replies = [(0, [b'{"type": "hello"}\n{"type": "do', b'ne"}\n'], [b"log line\n"])]
    seen = box.run_harness({"site": "example.com"}, lambda message: None, timeout_s=30,
                           stderr_path=tmp_path / "harness.log")
    argv, timeout_s, workdir = machine.spawned[-1]
    assert [s["type"] for s in seen] == ["hello", "done"]
    assert (timeout_s, workdir) == (30, "/home/web") and argv[-1] == "/opt/pickfit/web_harness.py"
    assert machine.procs[-1].stdin.data.startswith(b'{"type": "start", "site": "example.com"}\n')
