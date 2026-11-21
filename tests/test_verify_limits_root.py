"""The full-privilege VM box's own limits test (limits_root.py): every probe's passing reading and its failing
ones, against a scripted box. No machine is started."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pickfit.verify import limits_root as lr
from pickfit.verify import root_box as rb
from pickfit.verify.box import BoxCapabilities, BoxError, ExecResult

T = "TimeoutError"
CUT_CLOSED = f"closed 1.1.1.1:443 {T}\nclosed 1.1.1.1:80 {T}\n"
IMDS_OFF = "imds 403\nimds 403\nimds 403\nimds 403\nimds 000\n"
# What a box that is as it should be prints for each of the probes' commands.
GOOD = {
    "root_given": "1000\n0\n",
    "systemd": "systemd\nrunning\nunit-ran\n",
    "container": "1\n",
    "kernel": "module-ok dummy\ntun-ok\nfuse-ok\nraw-ok\n",
    "disk": "wrote ok\nmounted /dev/nvme1n1\nroot /dev/nvme0n1p1\n",
    "imds": IMDS_OFF,
    "imds_undo": "undo-tried\n" + IMDS_OFF,
    "scan": "own private-key /etc/ssh/ssh_host_ed25519_key\nown private-key /var/lib/cloud/instance/user-data.txt\n"
            "scanned 812\n",
    "scan_planted": "planted\nfound aws-dir /root/.aws\nfound key-id /root/.aws/credentials\nscanned 813\n",
    "env": "HOME LANG PATH TERM USER XDG_RUNTIME_DIR ",
    "open": "open 1.1.1.1:80\nopen 1.1.1.1:443\nopen 9.9.9.9:443\ndns 1.1.1.1 answered rcode=0 answers=2\n",
    "closed": "".join(f"closed {t} {T}\n" for t in lr.CLOSED_TARGETS) + f"dns 9.9.9.9 silent {T}\n",
    "private": "".join(f"closed {t} {T}\n" for t in lr.PRIVATE_TARGETS)
               + f"closed 10.213.0.1:80 {T}\nclosed 10.213.0.2:80 OSError\n"
               + f"dns 169.254.169.253 silent {T}\ndns 10.213.0.2 answered rcode=5 answers=0\n",
    "peer": f"closed 10.213.0.5:22 {T}\nclosed 198.51.100.10:22 {T}\n",
    "servers": "",
    "inside_8765": "200",
    "hold_start": "",
    "hold_mark": "",
    "hold_log": f"answer\nanswer\nanswer\nCUT\nsilent {T}\nsilent {T}\nsilent {T}\n",
    "cut_new": CUT_CLOSED + f"dns 1.1.1.1 silent {T}\ndns 169.254.169.253 silent {T}\n",
    "cut_undo": "undo-tried\n" + CUT_CLOSED,
    "online_again": "open 1.1.1.1:443\nopen 1.1.1.1:80\n",
}
VIEW = {"metadata_endpoint": "disabled", "instance_profile": None, "key_pair": None, "volumes_deleted_with_it": True,
        "vpc_router": "10.213.0.1", "vpc_resolver": "10.213.0.2", "address": "198.51.100.9",
        "private_address": "10.213.0.4", "groups": ["sg-control", "sg-http", "sg-https"], "acl": "acl-default"}
OFFLINE_VIEW = {"groups": ["sg-control", "sg-offline"], "acl": "acl-offline"}
EXPECTED = ["root_given", "systemd_runs", "container_runs", "kernel_reachable", "extra_disk", "metadata_off_for_root",
            "metadata_stays_off", "no_identity_outside", "no_credentials_on_disk", "no_credentials_control",
            "no_secrets_in_env", "egress_allowed", "egress_only_allowed_ports", "private_unreachable",
            "peer_unreachable", "outside_probe_sees", "outside_probe_is_outside", "probe_rule_removed",
            "cut_ends_open_connections", "cut_refuses_new_connections", "cut_root_cannot_undo", "cut_seen_outside",
            "offline_localhost", "online_again", "command_timeout"]


class Machine:
    extra_disk_gb = 8

    def __init__(self, box: FakeBox) -> None:
        self.box = box
        self.status = "running"
        self.left: list[int] = []

    def outside_view(self) -> dict[str, Any]:
        return {**self.box.view, **({} if self.box.network_enabled else self.box.offline_view)}

    def probed_ports(self) -> list[int]:
        return list(self.left)

    def state(self) -> str:
        return self.status


class FakeBox:
    """A full-privilege box whose commands print what `out` says for the probe they belong to."""

    runner = "fake-rootvm"
    image = "fake-rootvm:1"
    detach = "/usr/bin/setsid /usr/bin/nohup"
    capabilities = rb.FULL
    extra_disk: str | None = "/dev/nvme1n1"
    start_s = 61.0

    def __init__(self, **over: str) -> None:
        self.out = {**GOOD, **over}
        self.view = dict(VIEW)
        self.offline_view = dict(OFFLINE_VIEW)
        self.network_enabled = True
        self.network: list[bool] = []
        self.ran: list[str] = []
        self.probes = {8766: {"outside": "open", "status": 200, "seconds": 0.4},
                       8765: {"outside": "closed", "status": None, "seconds": 6.0}}
        self.machine = Machine(self)
        self.started = self.closed = False
        self.timeout_kills = True

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True
        self.machine.status = "terminated"

    def evidence(self) -> dict[str, Any]:
        return {"full_privilege": True}

    def set_network(self, enabled: bool) -> None:
        self.network.append(enabled)
        self.network_enabled = enabled

    def probe_port(self, port: int, *, path: str | None = None) -> dict[str, Any]:
        return {"kind": "port", "port": port, "path": path, **self.probes[port]}

    def which(self, command: str) -> str:
        """The probe a command belongs to, by what only that command holds."""
        marks = (("root_given", command.startswith("id -u;")), ("systemd", "systemd-run" in command),
                 ("container", "hello-world" in command), ("kernel", "modprobe" in command),
                 ("disk", "mkfs.ext4" in command),
                 ("imds_undo", "undo-tried" in command and "/latest/api/token" in command),
                 ("imds", "/latest/api/token" in command),
                 ("scan_planted", "planted" in command), ("scan", "print(\"scanned\"" in command),
                 ("env", command.startswith("env | cut")),
                 ("peer", "10.213.0.5:22" in command), ("closed", "aspmx.l.google.com:25" in command),
                 ("private", "172.16.0.1:80" in command), ("open", "9.9.9.9:443" in command),
                 ("servers", "http.server" in command), ("inside_8765", "http://127.0.0.1:8765/" in command),
                 ("hold_start", "sys.argv[2]" in command and lr.HOLD_HOST in command),
                 ("hold_mark", "echo CUT" in command), ("hold_log", f"cat {lr.HOLD_LOG}" in command),
                 ("cut_undo", "undo-tried" in command), ("cut_new", " 1.1.1.1 169.254.169.253 " in command),
                 ("online_again", " 1.1.1.1:443 1.1.1.1:80 " in command), ("sleep", command == "sleep 30"))
        return next((name for name, hit in marks if hit), "?")

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        name = self.which(command)
        self.ran.append(name)
        if name == "sleep":
            killed = self.timeout_kills
            return ExecResult(command, 137 if killed else 0, "", "", 3.1 if killed else 30.0, timed_out=killed)
        assert name != "?", f"a command no probe is known for: {command[:200]}"
        return ExecResult(command, 0, self.out[name], "", 0.2)


class Peer(FakeBox):
    def __init__(self) -> None:
        super().__init__()
        self.view = {**VIEW, "address": "198.51.100.10", "private_address": "10.213.0.5"}

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        return ExecResult(command, 0, "peer-answers-the-harness\n", "", 0.2)


def run(box: FakeBox, peer: Any = "a peer") -> dict[str, bool]:
    results = lr.run_root_limits_test(box, lambda line: None, Peer() if peer == "a peer" else peer)
    assert [r.name for r in results] == EXPECTED
    return {r.name: r.ok for r in results}


def failing(box: FakeBox, peer: Any = "a peer") -> list[str]:
    return [name for name, ok in run(box, peer).items() if not ok]


def test_every_probe_holds_on_a_box_that_is_as_it_should_be():
    box = FakeBox()
    assert failing(box) == []
    assert box.network == [False, True] and box.network_enabled  # the network is back on when it returns
    assert "?" not in box.ran
    # Every reading of the VM is taken as root: root is what the software under test may be.
    assert lr._root("x").startswith("/usr/bin/sudo -n ") and lr._py("x").startswith("/usr/bin/sudo -n /usr/bin/python3")


FAILING = [
    # (the probe that must fail, what the box prints instead)
    ("root_given", {"root_given": "1000\n1000\n"}),  # sudo gave nothing
    ("systemd_runs", {"systemd": "systemd\nrunning\n"}),  # the unit did not run
    ("systemd_runs", {"systemd": "sh\nunit-ran\n"}),  # no init
    ("container_runs", {"container": "0\n"}),
    ("kernel_reachable", {"kernel": "module-ok dummy\ntun-ok\nraw-ok\n"}),  # no /dev/fuse
    ("kernel_reachable", {"kernel": "tun-ok\nfuse-ok\nraw-ok\n"}),  # no module loaded
    ("extra_disk", {"disk": "wrote ok\nmounted /dev/nvme0n1p1\nroot /dev/nvme0n1p1\n"}),  # the system's own disk
    ("extra_disk", {"disk": "mounted /dev/nvme1n1\nroot /dev/nvme0n1p1\n"}),  # nothing was written
    ("extra_disk", {"disk": "wrote ok\nmounted /dev/nvme1n1\nroot /dev/nvme1n1p1\n"}),  # / lives on it
    ("metadata_off_for_root", {"imds": IMDS_OFF.replace("imds 000", "imds 200")}),  # one address still answers
    ("metadata_off_for_root", {"imds": "imds 403\nimds 403\n"}),  # not every way was asked
    ("metadata_stays_off", {"imds_undo": "undo-tried\n" + IMDS_OFF.replace("imds 403", "imds 200", 1)}),
    ("metadata_stays_off", {"imds_undo": IMDS_OFF}),  # root's undo was never tried
    ("no_credentials_on_disk", {"scan": "found private-key /home/sbx/.ssh/id_ed25519\nscanned 812\n"}),
    ("no_credentials_on_disk", {"scan": "found env 1:AWS_SECRET_ACCESS_KEY\nscanned 812\n"}),
    ("no_credentials_on_disk", {"scan": "scanned 0\n"}),  # a scan that read nothing found nothing
    ("no_credentials_control", {"scan_planted": "planted\nscanned 813\n"}),  # the scan is blind to a planted key
    ("no_credentials_control", {"scan_planted": "found key-id /root/.aws/credentials\nscanned 813\n"}),  # not planted
    ("no_secrets_in_env", {"env": "AWS_ACCESS_KEY_ID HOME PATH "}),
    ("no_secrets_in_env", {"env": "HOME OPENAI_API_KEY PATH "}),
    ("egress_allowed", {"open": GOOD["open"].replace("open 1.1.1.1:443", f"closed 1.1.1.1:443 {T}")}),
    ("egress_allowed", {"open": GOOD["open"].replace("answered rcode=0 answers=2", f"silent {T}")}),
    ("egress_only_allowed_ports", {"closed": GOOD["closed"].replace(f"closed smtp.gmail.com:587 {T}",
                                                                   "open smtp.gmail.com:587")}),
    ("egress_only_allowed_ports", {"closed": GOOD["closed"].replace(f"closed aspmx.l.google.com:25 {T}",
                                                                   "open aspmx.l.google.com:25")}),  # SMTP
    # A refusal means the packet left and an answer came back; an unresolved name means nothing was tried.
    ("egress_only_allowed_ports", {"closed": GOOD["closed"].replace(f"github.com:22 {T}",
                                                                   "github.com:22 ConnectionRefusedError")}),
    ("egress_only_allowed_ports", {"closed": GOOD["closed"].replace(f"closed github.com:22 {T}",
                                                                   "unresolved github.com:22 gaierror")}),
    ("egress_only_allowed_ports", {"closed": GOOD["closed"].replace(f"dns 9.9.9.9 silent {T}",
                                                                   "dns 9.9.9.9 answered rcode=0 answers=1")}),
    ("egress_only_allowed_ports", {"closed": f"closed 1.1.1.1:853 {T}\ndns 9.9.9.9 silent {T}\n"}),  # not all tried
    ("private_unreachable", {"private": GOOD["private"].replace(f"closed 10.0.0.1:80 {T}", "open 10.0.0.1:80")}),
    ("private_unreachable", {"private": GOOD["private"].replace(f"10.213.0.1:80 {T}",
                                                               "10.213.0.1:80 ConnectionRefusedError")}),
    ("private_unreachable", {"private": GOOD["private"].replace(f"dns 169.254.169.253 silent {T}",
                                                               "dns 169.254.169.253 answered rcode=0 answers=3")}),
    ("peer_unreachable", {"peer": GOOD["peer"].replace(f"closed 10.213.0.5:22 {T}", "open 10.213.0.5:22")}),
    ("peer_unreachable", {"peer": GOOD["peer"].replace(f"closed 198.51.100.10:22 {T}", "open 198.51.100.10:22")}),
    ("cut_ends_open_connections", {"hold_log": f"answer\nanswer\nCUT\nsilent {T}\nanswer\nsilent {T}\n"}),
    ("cut_ends_open_connections", {"hold_log": f"answer\nanswer\nclosed-by-peer\nCUT\n"}),  # decides nothing
    ("cut_ends_open_connections", {"hold_log": f"answer\nCUT\nsilent {T}\nsilent {T}\n"}),  # too little before
    ("cut_ends_open_connections", {"hold_log": "answer\nanswer\nanswer\nCUT\n"}),  # nothing tried after
    ("cut_ends_open_connections", {"hold_log": f"no-connection {T}\nCUT\n"}),
    ("cut_ends_open_connections", {"hold_log": f"answer\nanswer\nsilent {T}\nsilent {T}\n"}),  # no cut mark
    ("cut_refuses_new_connections", {"cut_new": GOOD["cut_new"].replace(f"closed 1.1.1.1:443 {T}", "open 1.1.1.1:443")}),
    ("cut_refuses_new_connections", {"cut_new": GOOD["cut_new"].replace(f"dns 1.1.1.1 silent {T}",
                                                                       "dns 1.1.1.1 answered rcode=0 answers=1")}),
    ("cut_refuses_new_connections", {"cut_new": GOOD["cut_new"].replace(
        f"dns 169.254.169.253 silent {T}", "dns 169.254.169.253 answered rcode=0 answers=1")}),  # Amazon's resolver
    ("cut_root_cannot_undo", {"cut_undo": "undo-tried\nopen 1.1.1.1:443\nopen 1.1.1.1:80\n"}),
    ("cut_root_cannot_undo", {"cut_undo": CUT_CLOSED}),  # the undo was never tried
    ("offline_localhost", {"inside_8765": "000"}),
    ("online_again", {"online_again": CUT_CLOSED}),
]


@pytest.mark.parametrize("probe,over", FAILING, ids=[f"{p}-{n}" for n, (p, _) in enumerate(FAILING)])
def test_each_probe_fails_on_its_failing_reading(probe: str, over: dict[str, str]):
    also = {"offline_localhost": ["outside_probe_is_outside"]}.get(probe, [])  # both read the loopback server
    assert sorted(failing(FakeBox(**over))) == sorted([probe, *also])


def test_the_probes_that_read_the_provider_fail_on_what_it_says():
    for change in ({"metadata_endpoint": "enabled"}, {"instance_profile": {"Arn": "arn:aws:iam::1:instance-profile/x"}},
                   {"key_pair": "laptop"}, {"volumes_deleted_with_it": False}):
        box = FakeBox()
        box.view.update(change)
        assert failing(box) == ["no_identity_outside"], change
    box = FakeBox()
    box.offline_view = {}  # the provider describes the machine the same, cut or not
    assert failing(box) == ["cut_seen_outside"]
    box = FakeBox()
    box.machine.left = [8766]  # a probe's rule was left open
    assert failing(box) == ["probe_rule_removed"]
    box = FakeBox()
    box.machine.outside_view = lambda: (_ for _ in ()).throw(BoxError("the API is down"))  # type: ignore[method-assign]
    assert failing(box) == ["no_identity_outside", "cut_seen_outside"]  # no word from outside is not a good word


def test_the_outside_probes_fail_when_the_probe_does_not_come_from_outside_or_sees_nothing():
    box = FakeBox()
    box.probes[8766] = {"outside": "closed", "status": None, "seconds": 6.0}  # the harness cannot get in
    assert failing(box) == ["outside_probe_sees"]
    box = FakeBox()
    box.probes[8766] = {"outside": "open", "status": 404, "seconds": 0.3}
    assert failing(box) == ["outside_probe_sees"]
    box = FakeBox()
    box.probes[8765] = {"outside": "open", "status": 200, "seconds": 0.3}  # a loopback server seen: not from outside
    assert failing(box) == ["outside_probe_is_outside"]


def test_the_peer_probe_needs_a_peer_the_harness_reaches():
    assert failing(FakeBox(), peer=None) == ["peer_unreachable"]  # not checked is not passed
    silent = Peer()
    silent.exec = lambda command, timeout_s, cwd=None: ExecResult(command, 255, "", "", 0.1)  # type: ignore[method-assign]
    assert failing(FakeBox(), peer=silent) == ["peer_unreachable"]  # no control: its port may not even listen
    nowhere = Peer()
    nowhere.view = {**VIEW, "address": None, "private_address": None}
    assert failing(FakeBox(), peer=nowhere) == ["peer_unreachable"]


def test_a_command_that_is_not_killed_at_its_timeout_fails():
    box = FakeBox()
    box.timeout_kills = False
    assert failing(box) == ["command_timeout"]


def test_the_network_comes_back_even_when_a_probe_raises():
    box = FakeBox()
    real = box.exec

    def breaks(command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        if box.which(command) == "cut_new":
            raise BoxError("the machine stopped answering")
        return real(command, timeout_s, cwd=cwd)

    box.exec = breaks  # type: ignore[method-assign]
    with pytest.raises(BoxError):
        lr.run_root_limits_test(box, lambda line: None, Peer())
    assert box.network == [False, True]


def test_the_gone_probe_takes_the_providers_word():
    box = FakeBox()
    assert not lr.gone_probe(box).ok  # still running
    for state in ("shutting-down", "terminated", "gone"):
        box.machine.status = state
        assert lr.gone_probe(box).ok
    box.machine.status = "stopped"  # stopped is not gone: its disk is still there
    assert not lr.gone_probe(box).ok
    box.machine.state = lambda: (_ for _ in ()).throw(RuntimeError("the API is down"))  # type: ignore[method-assign]
    assert not lr.gone_probe(box).ok


def test_the_readers_tell_a_timeout_from_an_answer():
    out = f"open a:1\nclosed b:2 {T}\nclosed c:3 ConnectionRefusedError\nunresolved d:4 gaierror\nclosed e:5 OSError\n"
    assert lr.connects(out)["b:2"] == ("closed", T) and lr.connects(out)["d:4"][0] == "unresolved"
    assert lr.all_open(out, ("a:1",)) and not lr.all_open(out, ("a:1", "b:2"))
    assert lr.all_timed_out(out, ("b:2",)) and not lr.all_timed_out(out, ("b:2", "c:3"))
    assert not lr.all_timed_out(out, ("d:4",)) and not lr.all_timed_out(out, ("e:5",)) and not lr.all_timed_out(out, ())
    assert lr.all_unreachable(out, ("b:2", "e:5")) and not lr.all_unreachable(out, ("c:3",))
    assert not lr.all_unreachable(out, ("zz:9",))  # a target that was never tried
    seen = lr.dns(f"dns 1.1.1.1 answered rcode=0 answers=2\ndns 9.9.9.9 silent {T}\ndns 10.0.0.2 answered rcode=5 answers=0\n")
    assert seen == {"1.1.1.1": "resolved", "9.9.9.9": "silent", "10.0.0.2": "empty"}
    assert lr.no_identity(VIEW) and not lr.no_identity({}) and not lr.no_identity({**VIEW, "key_pair": "k"})
    assert lr.capabilities_work(GOOD["kernel"]) and lr.scan_clean(GOOD["scan"]) and not lr.scan_clean("")


def test_the_scan_never_carries_a_key_shaped_string_and_the_plant_is_made_from_halves():
    import re

    source = Path(lr.__file__).read_text(encoding="utf-8")
    assert not re.search(r"(AKIA|ASIA)[0-9A-Z]{16}", source)  # nothing a secret scanner would stop a push for
    assert "AKIA%s" in lr.PLANT and "QQQQQQQQQQQQQQQQ" in lr.PLANT and lr.UNPLANT.endswith("/root/.aws")
    assert re.search(rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b", b"aws_access_key_id = AKIA" + b"Q" * 16)  # what the VM then holds


def test_the_whole_test_starts_two_boxes_closes_both_and_asks_whether_they_are_gone(tmp_path: Path):
    made: list[tuple[str, FakeBox]] = []

    def make_box(run_id: str, role: str) -> Any:
        box = FakeBox() if role == "limits" else Peer()
        made.append((role, box))
        return box

    lines: list[str] = []
    results, path = lr.root_limits_test(make_box, tmp_path, lines.append)
    assert [role for role, _ in made] == ["limits", "limits-peer"]  # the lane's two
    assert all(box.started and box.closed for _, box in made)
    assert [r.name for r in results] == [*EXPECTED, "instance_gone", "peer_instance_gone"] and all(r.ok for r in results)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path.name.startswith("limits-fake-rootvm-") and saved["full_privilege"] is True
    assert saved["passed"] == saved["total"] == len(EXPECTED) + 2
    assert saved["capabilities"] == ["root", "systemd", "container_engine", "kernel_modules"]
    assert any(f"{len(EXPECTED) + 2}/{len(EXPECTED) + 2} held" in line for line in lines)


def test_a_machine_that_is_still_there_after_the_run_fails_the_test(tmp_path: Path):
    class Stays(FakeBox):
        def close(self) -> None:
            self.closed = True  # closed, and the provider still says running

    results, _ = lr.root_limits_test(lambda run_id, role: Stays() if role == "limits" else Peer(), tmp_path,
                                     lambda line: None)
    assert [r.name for r in results if not r.ok] == ["instance_gone"]


def test_without_a_second_box_the_peer_probe_fails_and_the_first_box_is_still_closed(tmp_path: Path):
    class NoRoom(Peer):
        def start(self) -> None:
            raise BoxError("no room for another EC2 machine in ap-east-2")

    made: list[FakeBox] = []

    def make_box(run_id: str, role: str) -> Any:
        made.append(FakeBox() if role == "limits" else NoRoom())
        return made[-1]

    results, _ = lr.root_limits_test(make_box, tmp_path, lambda line: None)
    assert [r.name for r in results if not r.ok] == ["peer_unreachable"] and made[0].closed
    assert "peer_instance_gone" not in [r.name for r in results]


def test_it_is_not_the_limits_test_of_a_box_whose_user_is_not_root():
    plain = FakeBox()
    plain.capabilities = BoxCapabilities()  # type: ignore[misc]
    with pytest.raises(BoxError, match="limits.py's"):
        lr.run_root_limits_test(plain, lambda line: None)
