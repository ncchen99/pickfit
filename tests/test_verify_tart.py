"""TartBox with a fake `tart`: clone, boot, hardening, host-side softnet policy, containment. No real VM."""

from __future__ import annotations

import json
import socket
import stat
import sys
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pickfit.verify import tart_box as tb
from pickfit.verify.agent import INSTRUCTIONS, AgentLimits, render_task
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.limits import run_limits_test
from pickfit.verify.plan import plan_for
from pickfit.verify.tart_box import (
    MAC_ENV,
    SOFTNET_POLICY,
    SoftnetControl,
    TartBox,
    image_label,
    prune_stale,
    softnet_ready,
)
from pickfit.verify.task import load_fixture
from verify_fakes import FakeBox

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the fake tart is a #! script and softnet's "
                                "control channel is an AF_UNIX socketpair; POSIX only")


FIXTURES = Path(__file__).parent / "fixtures" / "verify"
MANIFEST = {"base": "pickfit-macos-26", "source": "ghcr.io/cirruslabs/macos-tahoe-base:latest",
            "source_digest": "sha256:0123456789abcdef0123", "macos": "26.6.2 (25G83)", "arch": "arm64",
            "brew": "5.0.1", "python3": "3.9.6", "uv": "0.9.5", "pipx": "1.8.0", "node": "v25.1.0", "npm": "11.6.2",
            "build_id": "abc123def456", "hardened": True}

# Records calls; `run` serves softnet's JSON-RPC on the inherited fd and tracks the live phase in a file the
# exec firewall-probe reads back. Phase: online (block @host), offline (block 0/0), poscontrol (allow @host).
# FAKE_* env vars inject leaks. The probe answers curl exit codes: 0 reached, 28 dropped.
FAKE_TART = r'''#!/usr/bin/env python3
import json, os, re, socket, sys, threading, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
open(os.path.join(here, "calls.jsonl"), "a").write(json.dumps(args) + "\n")
env = os.environ.get
cmd = args[0]
phase_path = os.path.join(here, "phase")
phases_log = os.path.join(here, "phases.log")

def classify(p):
    if p.get("block") == ["0.0.0.0/0"]:
        return "offline"
    if p.get("allow") == ["@host"] and p.get("block") == []:
        return "poscontrol"
    return "online"

def serve(fd):
    sock = socket.socket(fileno=fd)
    buf = b""
    try:
        while True:
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    return
                buf += chunk
            line, _, buf = buf.partition(b"\n")
            req = json.loads(line)
            p = req.get("params", {})
            phase = classify(p)
            open(phase_path, "w").write(phase)
            open(phases_log, "a").write(phase + "\n")
            sock.sendall((json.dumps({"jsonrpc": "2.0", "id": req["id"],
                "result": {"allow": p.get("allow", []), "block": p.get("block", []), "ruleCount": 1}}) + "\n").encode())
    except OSError:
        return

def code_for(name, phase):
    if env("FAKE_OFFLINE_LEAK"):
        return 0
    if name == "public":
        return 0 if phase in ("online", "poscontrol") else 28
    if name == "resolver":
        return 28 if phase == "offline" else 0
    if name.startswith("host"):
        return 0 if phase == "poscontrol" else int(env("FAKE_REACH_HOST", "28"))
    return int(env("FAKE_REACH_" + name.upper(), "28"))

if cmd == "run":
    if env("FAKE_RUN_FAIL"):
        print(env("FAKE_RUN_FAIL")); sys.exit(1)
    fd = None
    for a in args:
        m = re.match(r"--net-softnet-control-fd=(\d+)", a)
        if m:
            fd = int(m.group(1))
    if fd is not None:
        threading.Thread(target=serve, args=(fd,), daemon=True).start()
    end = time.time() + 30
    while not os.path.exists(os.path.join(here, "stopped")) and time.time() < end:
        time.sleep(0.05)
    sys.exit(0)
if cmd == "stop":
    open(os.path.join(here, "stopped"), "w").close()
if cmd == "delete" and env("FAKE_DELETE_FAIL"):
    sys.stderr.write("Error: cannot delete\n"); sys.exit(1)
if cmd == "get":
    sys.exit(0 if env("FAKE_BASE_EXISTS") else 1)
if cmd == "list":
    print(env("FAKE_LIST", "[]"))
if cmd == "exec":
    if env("FAKE_RUN_FAIL"):
        sys.stderr.write('Error: VM "%s" is not running\n' % args[1]); sys.exit(1)
    if "-i" in args:
        open(os.path.join(here, "stdin.bin"), "wb").write(sys.stdin.buffer.read())
    script = args[-1]
    if env("FAKE_FAIL_MATCH") and env("FAKE_FAIL_MATCH") in script:
        print("injected failure"); sys.exit(1)
    if "dscl . -authonly admin admin" in script and "fail()" in script:  # the hardened check
        if env("FAKE_UNHARDENED"):
            print("admin still has the default password"); sys.exit(1)
        sys.exit(0)
    if "networksetup" in script:
        print("gw=192.168.64.1"); sys.exit(0)
    if script.rstrip().endswith("/mdns"):
        phase = open(phase_path).read().strip() if os.path.exists(phase_path) else "online"
        answered = phase == "poscontrol" or env("FAKE_MDNS_LEAK")
        print("mdns=answered 10.0.0.1 100" if answered else "mdns=no-answer")
        sys.exit(0 if answered else 1)
    names = re.findall(r"echo (\w+)=\$\?", script)
    if names and "curl" in script:
        phase = open(phase_path).read().strip() if os.path.exists(phase_path) else "online"
        for n in names:
            print("%s=%d" % (n, code_for(n, phase)))
        sys.exit(0)
    if env("FAKE_STDERR"):
        sys.stderr.write(env("FAKE_STDERR"))
        sys.exit(int(env("FAKE_EXIT", "1")))
    print("ok")
    sys.exit(int(env("FAKE_EXIT", "0")))
'''


@pytest.fixture
def fake_tart(tmp_path: Path) -> Path:
    script = tmp_path / "tart"
    script.write_text(FAKE_TART)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    (state / "pickfit-macos-26.json").write_text(json.dumps(MANIFEST))
    return state


@pytest.fixture
def make_box(fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TartBox]]:
    """TartBoxes on the fake, with softnet treated as set up; each is closed (and its reaper killed) at teardown."""
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: None)
    made: list[TartBox] = []

    def make(**kw) -> TartBox:
        box = TartBox(tart=str(fake_tart), state_dir=state_dir, name="pf-verify-1-abc", log=lambda s: None, **kw)
        made.append(box)
        return box

    yield make
    (fake_tart.parent / "stopped").touch()
    for box in made:
        box.cloned = False
        box.close()


def _calls(fake: Path) -> list[list[str]]:
    return [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text().splitlines()]


def _phases(fake: Path) -> list[str]:
    log = fake.parent / "phases.log"
    return log.read_text().split() if log.exists() else []


@POSIX_ONLY
def test_start_clones_boots_with_softnet_blocks_host_and_close_deletes(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    calls = _calls(fake_tart)
    run = next(c for c in calls if c and c[0] == "run")
    assert "--net-softnet" in run and any(a.startswith("--net-softnet-control-fd=") for a in run)
    root = [c[-1] for c in calls if c[:5] == ["exec", "pf-verify-1-abc", "sudo", "-n", "/bin/sh"]]
    assert any("dscl . -authonly admin admin" in r and "pam_deny.so" in r for r in root)  # hardened check first
    assert any("setdnsservers" in r and "1.1.1.1" in r for r in root)  # DNS pinned to a public resolver
    setup = next(r for r in root if "PICKFIT_EOF" in r)
    assert "shutdown -h +22 " in setup and "pfctl" not in setup  # self-shutdown, no guest firewall
    assert _phases(fake_tart) == ["online"]  # the online policy (block @host) was set over the control channel
    assert box.gateway == "192.168.64.1" and box.network_enabled
    assert box.image.endswith("+pickfit-macos-26@abc123def456")  # the run names the base build id
    box.close()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and box.control is None


def test_online_policy_blocks_the_host():
    assert SOFTNET_POLICY[True]["block"] == ["@host", "224.0.0.0/4", "255.255.255.255/32"]  # host + multicast
    assert SOFTNET_POLICY[False] == {"allow": [], "block": ["0.0.0.0/0"]}


@POSIX_ONLY
def test_boot_refuses_when_softnet_is_not_set_up(make_box, fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: "softnet needs a one-time setuid-root bit: sudo ...")
    box = make_box()
    with pytest.raises(BoxError, match="setuid-root bit"):
        box.start()
    assert not any(c and c[0] == "run" for c in _calls(fake_tart))


@POSIX_ONLY
def test_an_unhardened_base_is_refused_before_any_model_command(make_box, fake_tart: Path,
                                                                 monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_UNHARDENED", "1")
    box = make_box()
    with pytest.raises(BoxError, match="not hardened.*default password"):
        box.start()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and not box.started


def test_a_manifest_from_before_hardening_is_refused(make_box, state_dir: Path):
    (state_dir / "pickfit-macos-26.json").write_text(json.dumps({**MANIFEST, "hardened": False}))
    with pytest.raises(BoxError, match="predates hardening"):
        make_box().start()


@POSIX_ONLY
def test_model_commands_run_as_the_box_user_with_limits_and_no_host_env(
        make_box, fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_API_KEY", "LLM_123_should_never_leak")
    box = make_box(limits=BoxLimits(max_command_s=100))
    box.start()
    result = box.exec("echo hi", 999)
    assert result.ok and result.stdout.strip() == "ok"
    argv = _calls(fake_tart)[-1]
    assert argv[:8] == ["exec", "pf-verify-1-abc", "sudo", "-n", "-u", "sbx", "-H", "/usr/bin/env"]
    env = [a for a in argv if "=" in a.split(" ")[0] and not a.startswith("ulimit")]
    assert {e.split("=", 1)[0] for e in env} == set(MAC_ENV)
    guard = argv[-1]
    assert guard.startswith("ulimit -u 256 -n 1024 -f 1572864 && cd /Users/sbx/work && exec ")
    assert f"{tb.TIMEOUT_CMD} 100 /bin/bash -c 'echo hi'" in guard  # clamped to max_command_s
    assert "LLM_123" not in json.dumps(argv)
    box.write_file("dir/a.txt", "data")
    write = _calls(fake_tart)[-1]
    assert write[:2] == ["exec", "-i"] and write[-1].endswith("sh dir/a.txt'")  # path is an argument
    assert (fake_tart.parent / "stdin.bin").read_bytes() == b"data"


@POSIX_ONLY
def test_network_cut_sets_softnet_policy_and_is_checked_as_root(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    box.set_network(False)
    assert _phases(fake_tart) == ["online", "offline"] and box.network_enabled is False
    box.set_network(True)
    assert _phases(fake_tart) == ["online", "offline", "online"] and box.network_enabled is True


@POSIX_ONLY
def test_online_check_fails_if_the_host_or_metadata_is_reachable(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_REACH_METADATA", "0")  # metadata answers despite softnet -> containment broken
    box = make_box()
    with pytest.raises(BoxError, match="online.*metadata reachable"):
        box.start()
    assert not box.started


@POSIX_ONLY
def test_online_check_fails_if_multicast_mdns_reaches_the_host(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_MDNS_LEAK", "1")  # the host answers mDNS despite the block
    box = make_box()
    with pytest.raises(BoxError, match="multicast mDNS was answered"):
        box.start()


@POSIX_ONLY
def test_a_refusal_is_not_accepted_as_blocked(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_REACH_HOST", "7")  # host refuses (reached) rather than dropping
    box = make_box()
    with pytest.raises(BoxError, match="host.*not dropped .reached"):
        box.start()


@POSIX_ONLY
def test_an_offline_cut_that_leaks_is_a_box_error(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    monkeypatch.setenv("FAKE_OFFLINE_LEAK", "1")  # policy set to offline, but egress still works
    with pytest.raises(BoxError, match="offline.*public not dropped"):
        box.set_network(False)
    assert box.network_enabled


@POSIX_ONLY
def test_turning_the_network_back_on_fails_if_the_cut_was_undone(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    box.set_network(False)
    monkeypatch.setenv("FAKE_OFFLINE_LEAK", "1")  # something re-opened egress while the box said offline
    with pytest.raises(BoxError, match="offline.*not dropped"):
        box.set_network(True)


@POSIX_ONLY
def test_validate_containment_runs_the_positive_and_negative_controls(make_box):
    box = make_box()
    box.start()
    results = {name: (ok, detail) for name, ok, _, detail in box.validate_containment()}
    assert results["gateway_found"][0]
    assert results["probe_sees_open_host_port"][0]  # an open host port answered with the block off
    assert results["internet_online"][0]
    assert any(n.startswith("host_") and n.endswith("_blocked_online") and ok for n, (ok, _) in results.items())
    assert results["mdns_answered_without_block"][0] and results["mdns_blocked_online"][0]
    assert results["metadata_unreachable_online"][0] and results["ipv6_unreachable_online"][0]
    assert results["public_blocked_offline"][0] and results["resolver_blocked_offline"][0]
    assert box.network_enabled  # restored online


@POSIX_ONLY
def test_softnet_control_speaks_policy_set_over_the_socket():
    ctrl = SoftnetControl()
    seen: list[dict] = []

    def softnet() -> None:
        buf = b""
        while b"\n" not in buf:
            buf += ctrl.child.recv(4096)
        req = json.loads(buf.split(b"\n")[0])
        seen.append(req)
        ctrl.child.sendall((json.dumps({"jsonrpc": "2.0", "id": req["id"],
                                        "result": {"allow": [], "block": req["params"]["block"], "ruleCount": 1}}) +
                            "\n").encode())

    t = threading.Thread(target=softnet, daemon=True)
    t.start()
    result = ctrl.set_policy(False)
    t.join(timeout=5)
    assert seen[0]["method"] == "softnet.policy.set" and seen[0]["params"] == SOFTNET_POLICY[False]
    assert "vmId" not in seen[0]["params"] and result["block"] == ["0.0.0.0/0"]
    ctrl.close()


@POSIX_ONLY
def test_softnet_control_errors_on_a_closed_channel():
    ctrl = SoftnetControl()
    ctrl.child.close()
    with pytest.raises(BoxError, match="softnet control channel"):
        ctrl.set_policy(True)
    ctrl.close()


def test_softnet_ready_reports_how_to_fix_each_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb.shutil, "which", lambda name: None)
    assert "not installed" in softnet_ready()
    binary = tmp_path / "softnet"
    binary.write_text("#!/bin/sh\n")
    monkeypatch.setattr(tb.shutil, "which", lambda name: str(binary))
    msg = softnet_ready()
    assert msg and "setuid-root" in msg and str(binary) in msg
    monkeypatch.setattr(tb.os, "stat", lambda p: types.SimpleNamespace(st_uid=0, st_mode=stat.S_ISUID | 0o755))
    assert softnet_ready() is None


@POSIX_ONLY
def test_close_never_raises_and_leaves_an_undeletable_clone_to_the_reaper(
        make_box, fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    real = box._tart

    def stop_hangs(*args, **kw):
        if args[0] == "stop":
            raise BoxError("tart stop timed out after 90s")
        return real(*args, **kw)

    monkeypatch.setattr(box, "_tart", stop_hangs)
    monkeypatch.setenv("FAKE_DELETE_FAIL", "1")
    (fake_tart.parent / "stopped").touch()
    box.close()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"]
    assert box.cloned and box._reaper is not None and box._reaper.poll() is None
    monkeypatch.delenv("FAKE_DELETE_FAIL")
    box.close()
    assert not box.cloned and box._reaper is None


@POSIX_ONLY
def test_vm_limit_failure_names_the_reboot_and_cleans_up(make_box, fake_tart: Path,
                                                         monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_RUN_FAIL", "Error: VZErrorVirtualMachineLimitExceeded")
    box = make_box()
    with pytest.raises(BoxError, match="reboot the Mac"):
        box.start()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and not box.started


def test_missing_base_says_how_to_prepare_it(fake_tart: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: None)
    box = TartBox(tart=str(fake_tart), state_dir=tmp_path, log=lambda s: None)
    with pytest.raises(BoxError, match="--prepare-base"):
        box.start()


@POSIX_ONLY
def test_failed_base_build_deletes_the_base_and_its_old_manifest(fake_tart: Path, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: None)
    monkeypatch.setattr(tb, "STATE_DIR", tmp_path)
    (tmp_path / "pickfit-macos-26.json").write_text(json.dumps(MANIFEST))
    monkeypatch.setenv("FAKE_FAIL_MATCH", "sysadminctl")
    with pytest.raises(BoxError, match="base setup failed"):
        tb.prepare_base(tart=str(fake_tart), log=lambda s: None)
    calls = _calls(fake_tart)
    assert ["clone", tb.SOURCE_IMAGE, "pickfit-macos-26"] in calls and calls[-1] == ["delete", "pickfit-macos-26"]
    assert not (tmp_path / "pickfit-macos-26.json").exists()


@POSIX_ONLY
def test_prepare_refuses_to_overwrite_an_existing_base(fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_BASE_EXISTS", "1")
    with pytest.raises(BoxError, match="already exists"):
        tb.prepare_base(tart=str(fake_tart), log=lambda s: None)


def test_prepare_pins_the_agent_before_brew_and_hardens():
    assert "install -o root -g wheel -m 755" in tb.PREPARE_ROOT  # agent pinned in PREPARE_ROOT (pre-brew)
    assert tb.PREPARE_ROOT.index("tart-guest-agent") < tb.PREPARE_ROOT.index("chown -R")  # before chowning brew
    script = tb.HARDEN_ROOT
    assert 'PICKFIT_ADMIN_PW="$(openssl rand' in script and "unset PICKFIT_ADMIN_PW" in script
    assert "chmod 600 /etc/kcpassword" in script and "launchctl disable system/$svc" in script
    assert "com.openssh.sshd com.apple.screensharing" in script and "pam_deny.so" in script
    assert "EnvironmentVariables:PATH" in script


@POSIX_ONLY
def test_prune_removes_stopped_and_stale_running_vms(fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    now = 1_800_000_000
    vms = [{"Name": f"pf-verify-{now - 10}-aaa", "Running": True, "State": "running"},
           {"Name": f"pf-verify-{now - 4 * 3600}-bbb", "Running": True, "State": "running"},
           {"Name": f"pf-verify-{now - 10}-ccc", "Running": False, "State": "stopped"},
           {"Name": "pickfit-macos-26", "Running": False, "State": "stopped"}]
    monkeypatch.setenv("FAKE_LIST", json.dumps(vms))
    removed = prune_stale(str(fake_tart), now=now, log=lambda s: None)
    assert removed == [f"pf-verify-{now - 4 * 3600}-bbb", f"pf-verify-{now - 10}-ccc"]
    assert ["delete", "pickfit-macos-26"] not in _calls(fake_tart)


def test_image_label_names_source_digest_guest_and_build():
    label = image_label(MANIFEST)
    assert label == ("cirruslabs/macos-tahoe-base@sha256:0123456789ab macOS 26.6.2 (25G83) "
                     "+pickfit-macos-26@abc123def456")
    assert len(image_label({**MANIFEST, "macos": "x" * 200})) == 120


class MacFakeBox(FakeBox):
    os, arch, runner = "macos", "arm64", "tart-vz"
    kind, user_rule, detach = TartBox.kind, TartBox.user_rule, TartBox.detach
    home, workdir = "/Users/sbx", "/Users/sbx/work"

    def __init__(self, *a, containment=None, **k):
        super().__init__(*a, **k)
        self._containment = containment

    def describe(self) -> str:
        box = TartBox(log=lambda s: None)
        box.manifest = MANIFEST
        return box.describe()

    def validate_containment(self, timeout: int = 4):
        return self._containment if self._containment is not None else [
            ("gateway_found", True, "gateway", "192.168.64.1"),
            ("probe_sees_open_host_port", True, "open port answers with block off", "reachable: [5000]"),
            ("host_5000_blocked_online", True, "host drops online", "exit 28"),
            ("internet_online", True, "internet reachable online", "exit 0"),
            ("public_blocked_offline", True, "public drops offline", "exit 28")]


def test_prompt_names_the_macos_box_and_its_rule():
    task = load_fixture(FIXTURES / "evnx.json", fetch=lambda url: "# evnx\n\nInstall: `brew install evnx`\n")
    text = render_task(task, plan_for(task.extraction, "macos"), MacFakeBox(), AgentLimits())
    assert "Box: macOS 26.6.2 (25G83) arm64 virtual machine" in text and "Debian" not in text
    assert "1. [brew, readme]" in text
    rules = INSTRUCTIONS.format(max_commands=15, max_turns=25, minutes=20, stdout_chars="6,000",
                                box_kind=MacFakeBox.kind, box_rule=MacFakeBox.user_rule)
    assert 'disposable macOS virtual machine ("the box")' in rules and "not an admin" in rules


def test_linux_prompt_is_unchanged():
    rules = INSTRUCTIONS.format(max_commands=15, max_turns=25, minutes=20, stdout_chars="6,000",
                                box_kind=FakeBox.kind, box_rule=FakeBox.user_rule)
    assert 'disposable Linux sandbox ("the box")' in rules
    assert "- You are not root: no sudo, no apt-get, nothing written outside $HOME and /tmp. Do not install" in rules


def test_macos_limits_records_root_containment_and_escalation_probes():
    box = MacFakeBox({"id -u": (0, "1001\nstaff everyone\nsudo: a password is required\nsudo=1\n", ""),
                      "dscl . -authonly": (1, "", "Authentication failed"),
                      "pty.fork": (0, "Password:\r\nsu: Sorry\r\n", ""),
                      "cat /etc/kcpassword": (1, "", "Permission denied"),
                      "http://127.0.0.1:8765": (0, "200", "")})
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    # escalation surface (defence in depth)
    for name in ("non_admin", "admin_password", "su_admin", "remote_login_closed",
                 "kcpassword_unreadable", "agent_binary_locked"):
        assert results[name].ok, name
    # host-side containment, recorded from the root positive/negative control
    for name in ("gateway_found", "probe_sees_open_host_port", "internet_online", "host_5000_blocked_online",
                 "public_blocked_offline"):
        assert results[name].ok, name
    assert results["offline_localhost"].ok  # loopback survives the cut
    assert "firewall_locked" not in results and "non_root" not in results


def test_macos_limits_fails_closed_when_containment_cannot_run():
    box = MacFakeBox({"http://127.0.0.1:8765": (0, "200", "")},
                     containment=None)
    box.validate_containment = lambda timeout=4: (_ for _ in ()).throw(BoxError("no result for host5000"))
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    assert not results["containment_check_ran"].ok and "no result" in results["containment_check_ran"].detail
