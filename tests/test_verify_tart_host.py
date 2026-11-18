"""A TartBox on another Mac over SSH (tart_host.SshHost), with a fake `ssh` that runs the host's side right here and
the fake `tart` of test_verify_tart: the relay carries softnet's policy, the VNC port is forwarded, nothing is left."""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pickfit.verify import tart_host as th
from pickfit.verify.box import BoxError
from pickfit.verify.tart_box import TartBox
from test_verify_tart import FAKE_TART, GUI_MANIFEST, MANIFEST, _calls, _phases

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32" or not os.path.exists(th.HOST_PYTHON),
                                reason="the fakes are #! scripts and the relay runs on the host's /usr/bin/python3")

# Records every call; `-O` (forward, cancel, exit through the master) does nothing; anything else runs the remote
# command, the single argument after `--`, with /bin/sh here, as sshd would on the host.
FAKE_SSH = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
open(os.path.join(here, "ssh.jsonl"), "a").write(json.dumps(args) + "\n")
if "-O" in args:
    sys.exit(int(os.environ.get("FAKE_FORWARD_EXIT", "0")) if "forward" in args else 0)
os.execv("/bin/sh", ["/bin/sh", "-c", args[args.index("--") + 1]])
'''

TARGET = "m1@mac-mini.example"


@pytest.fixture
def fakes(tmp_path: Path) -> tuple[Path, Path]:
    tart, ssh = tmp_path / "tart", tmp_path / "ssh"
    for path, text in ((tart, FAKE_TART), (ssh, FAKE_SSH)):
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return tart, ssh


@pytest.fixture
def make_host(fakes: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., th.SshHost]:
    monkeypatch.setattr(th.SshHost, "softnet_ready", lambda self: None)
    monkeypatch.setattr(th.SshHost, "wait_bridge_down", lambda self, tart, timeout_s=15.0: None)

    def make() -> th.SshHost:
        host = th.SshHost(TARGET, ssh=str(fakes[1]), state_dir=tmp_path / "state", remote_state=tmp_path / "remote")
        host.state_dir.mkdir(parents=True)
        (host.state_dir / "pickfit-macos-26.json").write_text(json.dumps(MANIFEST))
        (host.state_dir / "pickfit-macos-26-gui.json").write_text(json.dumps(GUI_MANIFEST))
        return host

    return make


@pytest.fixture
def make_box(fakes: tuple[Path, Path], make_host: Callable[..., th.SshHost]) -> Iterator[Callable[..., TartBox]]:
    made: list[TartBox] = []

    def make(**kw) -> TartBox:
        box = TartBox(tart=str(fakes[0]), host=make_host(), name="pf-verify-1-abc", log=lambda s: None, **kw)
        made.append(box)
        return box

    yield make
    (fakes[0].parent / "stopped").touch()
    for box in made:
        box.cloned = False
        box.close()


def _ssh(fake_ssh: Path) -> list[list[str]]:
    path = fake_ssh.parent / "ssh.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_every_host_command_is_one_quoted_command_over_the_shared_connection():
    host = th.SshHost(TARGET, key="/k/id", port=2222)
    argv = host.wrap(["/opt/homebrew/bin/tart", "exec", "vm", "/bin/sh", "-c", "echo 'a b'; rm -rf $HOME"])
    assert argv[0] == "ssh" and argv[argv.index("--") - 1] == TARGET and len(argv) == argv.index("--") + 2
    assert f"ControlPath={host.control_path}" in argv and "ControlMaster=auto" in argv and "BatchMode=yes" in argv
    assert argv[argv.index("-i") + 1] == "/k/id" and argv[argv.index("-p") + 1] == "2222"
    remote = argv[-1]
    assert remote.startswith(f"PATH={th.REMOTE_PATH}; export PATH; exec /opt/homebrew/bin/tart exec vm")
    assert "'echo '\"'\"'a b'\"'\"'; rm -rf $HOME'" in remote  # the box's script stays one quoted word
    assert len(str(host.control_path)) < 100  # a UNIX socket's path must be short
    assert host.state_dir.parts[-2:] == ("hosts", "mac-mini.example") and host.name == "mac-mini.example"


def test_the_host_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    env: dict[str, str] = {}
    monkeypatch.setattr(th, "get_env", lambda name, default=None: env.get(name, default))
    local = th.host_from_env(tmp_path)
    assert not local.remote and local.state_dir == tmp_path and local.wrap(["tart", "list"]) == ["tart", "list"]
    env.update(PICKFIT_TART_HOST=TARGET, PICKFIT_TART_SSH_KEY="/k/id", PICKFIT_TART_SSH_PORT="2200")
    remote = th.host_from_env(tmp_path)
    assert remote.remote and remote.target == TARGET and remote.key == "/k/id" and remote.port == 2200
    assert remote.state_dir == tmp_path / "hosts" / "mac-mini.example"


@POSIX_ONLY
def test_a_box_on_a_remote_mac_sets_softnets_policy_through_the_relay_and_cleans_up(make_box, fakes):
    tart, ssh = fakes
    box = make_box()
    box.start()
    calls = _calls(tart)
    run = next(c for c in calls if c and c[0] == "run")
    fd = next(a for a in run if a.startswith("--net-softnet-control-fd="))
    assert fd.split("=")[1].isdigit()  # the relay filled in the socket it holds on the host
    assert _phases(tart) == ["online"]  # the online policy reached softnet over the SSH session
    assert box.gateway == "192.168.64.1" and box.network_enabled and box.image.endswith("+pickfit-macos-26@abc123def456")
    assert all(c[c.index("--") - 1] == TARGET for c in _ssh(ssh) if "--" in c)  # every command went to the host
    log = Path(str(box.vm_log))
    assert log.parent == tart.parent / "remote" and stat.S_IMODE(log.stat().st_mode) == 0o600  # made on the host
    assert isinstance(box._reaper, th.RemoteReaper) and box._reaper.poll() is None  # the host's reaper waits
    reaper = box._reaper.pid
    box.set_network(False)
    assert _phases(tart)[-1] == "offline"
    box.close()
    assert _calls(tart)[-1] == ["delete", "pf-verify-1-abc"] and box.control is None and box._reaper is None
    assert any(c[-1].endswith(f"exec /bin/kill -9 {reaper}") for c in _ssh(ssh) if "--" in c)


@POSIX_ONLY
def test_a_remote_display_is_reached_through_a_forwarded_port_and_the_guest_is_kept_from_the_hosts(make_box, fakes):
    tart, ssh = fakes
    box = make_box(display=True)
    box.start()
    forward = next(c for c in _ssh(ssh) if "-O" in c and "forward" in c)
    local = int(forward[forward.index("-L") + 1].split(":")[1])
    assert forward[forward.index("-L") + 1] == f"127.0.0.1:{local}:127.0.0.1:5999"
    assert box.vnc_url == f"vnc://:fake-pw@127.0.0.1:{local}" and box.vnc_host_port == 5999
    scripts = [c[-1] for c in _calls(tart) if c[0] == "exec"]
    assert any("http://192.168.64.1:5999/" in s for s in scripts)  # the host's own port, not the forwarded one
    assert not any(f":{local}/" in s for s in scripts)
    box.close()
    assert any("-O" in c and "cancel" in c for c in _ssh(ssh)) and box.host.forwards == []


@POSIX_ONLY
def test_a_vnc_port_that_cannot_be_forwarded_fails_the_box(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_FORWARD_EXIT", "255")
    box = make_box(display=True)
    with pytest.raises(BoxError, match="could not forward the VNC port"):
        box.start()


@POSIX_ONLY
def test_the_relay_stops_the_vm_when_the_session_ends(make_box, fakes):
    tart, _ = fakes
    box = make_box()
    box.start()
    vm = box.vm_proc
    box.control.requests.close()  # the harness is gone: the SSH session's stdin closes
    assert vm.wait(timeout=20) is not None  # the relay stopped `tart run`, and with it the session


def test_softnet_on_the_host_is_checked_there(monkeypatch: pytest.MonkeyPatch):
    host = th.SshHost(TARGET)
    answers = iter([json.dumps({"real": None, "uid": None, "mode": None}),
                    json.dumps({"real": "/opt/homebrew/Cellar/softnet/0.18/bin/softnet", "uid": 501, "mode": 0o100755}),
                    json.dumps({"real": "/opt/homebrew/Cellar/softnet/0.18/bin/softnet", "uid": 0, "mode": 0o104755}),
                    "not json"])

    class Done:
        def __init__(self, out: str) -> None:
            self.stdout, self.stderr, self.returncode = out + "\n", "", 0

    monkeypatch.setattr(th.SshHost, "run", lambda self, argv, **kw: Done(next(answers)))
    assert "not installed on m1@mac-mini.example" in host.softnet_ready()
    assert "sudo chown root:wheel /opt/homebrew/Cellar/softnet/0.18/bin/softnet" in host.softnet_ready()
    assert host.softnet_ready() is None
    assert "could not check softnet" in host.softnet_ready()
