"""TartBox with a fake `tart`: clone, boot, hardening, host-side softnet policy, containment. No real VM."""

from __future__ import annotations

import json
import re
import socket
import stat
import subprocess
import sys
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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
        return int(env("FAKE_POSCONTROL_HOST", "0")) if phase == "poscontrol" else int(env("FAKE_REACH_HOST", "28"))
    if name in ("github", "ghcr"):  # where installs come from: reachable unless a test cuts them
        return 28 if phase == "offline" else int(env("FAKE_REACH_" + name.upper(), "0"))
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
    if "--vnc-experimental" in args:
        print("VNC server is running at vnc://:fake-pw@127.0.0.1:5999", flush=True)
    end = time.time() + 30
    while not os.path.exists(os.path.join(here, "stopped")) and time.time() < end:
        time.sleep(0.05)
    sys.exit(0)
if cmd == "stop":
    open(os.path.join(here, "stopped"), "w").close()
if cmd == "delete" and env("FAKE_DELETE_FAIL"):
    sys.stderr.write("Error: cannot delete\n"); sys.exit(1)
if cmd == "get":
    if env("FAKE_BASE_EXISTS"):
        print(env("FAKE_GET", ""))
    sys.exit(0 if env("FAKE_BASE_EXISTS") else 1)
if cmd == "list":
    print(env("FAKE_LIST", "[]"))
if cmd == "exec":
    vm = args[2] if args[1] == "-i" else args[1]
    if env("FAKE_RUN_FAIL") or os.path.exists(os.path.join(here, "stopped")):
        sys.stderr.write('VM "%s" is not running\n' % vm); sys.exit(2)
    if env("FAKE_AGENT_GONE"):
        sys.stderr.write("Error: failed to connect to the VM, is the Tart Guest Agent running?\n"); sys.exit(1)
    if args[2:] == ["true"]:  # the agent probe
        sys.exit(0)
    if "-i" in args:
        open(os.path.join(here, "stdin.bin"), "wb").write(sys.stdin.buffer.read())
    if args[-1] == "procs":  # gui_mac's helper: sbx's login session
        print(json.dumps({"401": ["Sun Nov  1 08:00:00 2026", "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock"]}))
        sys.exit(0)
    script = args[-1]
    if env("FAKE_FAIL_MATCH") and env("FAKE_FAIL_MATCH") in script:
        print("injected failure"); sys.exit(1)
    if "dscl . -authonly admin admin" in script and "fail()" in script:  # the hardened check
        if env("FAKE_UNHARDENED"):
            print("admin still has the default password"); sys.exit(1)
        sys.exit(0)
    if "networksetup" in script:
        print("gw=192.168.64.1"); print("dns=" + env("FAKE_DNS", "1.1.1.1")); sys.exit(0)
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
    return [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def _phases(fake: Path) -> list[str]:
    log = fake.parent / "phases.log"
    return log.read_text(encoding="utf-8").split() if log.exists() else []


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
    # self-shutdown with no wall broadcasts (11/18: `shutdown -h +N` printed into a GUI terminal), no guest firewall
    assert "detach /bin/sh -c 'sleep 1320; /sbin/shutdown -h now'" in setup and "shutdown -h +" not in setup
    assert "pfctl" not in setup
    assert _phases(fake_tart) == ["online"]  # the online policy (block @host) was set over the control channel
    assert box.gateway == "192.168.64.1" and box.network_enabled
    assert box.image.endswith("+pickfit-macos-26@abc123def456")  # the run names the base build id
    box.close()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and box.control is None


def test_online_policy_blocks_the_host():
    assert SOFTNET_POLICY[True]["block"] == ["@host", "224.0.0.0/4", "255.255.255.255/32"]  # host + multicast
    assert SOFTNET_POLICY[False] == {"allow": [], "block": ["0.0.0.0/0"]}


@POSIX_ONLY
def test_dns_is_pinned_on_every_service_not_the_first(make_box, fake_tart: Path):
    # 11/18: the sequoia base lists com.redhat.spice.0 before Ethernet; pinning only the first service left DNS
    # on the blocked gateway, so every name timed out and the firewall check read "internet unreachable".
    make_box().start()
    pin = next(c[-1] for c in _calls(fake_tart) if c and c[0] == "exec" and "setdnsservers" in c[-1])
    assert "sed -n 2p" not in pin and "while IFS= read -r svc" in pin and "scutil --dns" in pin


@POSIX_ONLY
def test_dns_that_did_not_move_is_a_clear_error(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_DNS", "192.168.64.1")
    with pytest.raises(BoxError, match=r"DNS did not move to 1\.1\.1\.1 \(resolver 192\.168\.64\.1\)"):
        make_box().start()


def test_mdns_probe_does_not_hear_the_guest_answer_itself():
    # 11/18: the sequoia base advertises SSH, so its own mDNSResponder answered the looped-back query.
    assert "IP_MULTICAST_LOOP, 0" in tb.HELPER_MDNS and "addr[0] not in own" in tb.HELPER_MDNS
    compile(tb.HELPER_MDNS, "mdns", "exec")


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
@pytest.mark.parametrize("text", ['VM "pf-verify-1-abc" is not running',
                                  'the specified VM "pf-verify-1-abc" does not exist',
                                  "Error: failed to connect to the VM, is the Tart Guest Agent running?"])
def test_a_command_that_prints_tarts_own_errors_has_only_failed(make_box, fake_tart: Path,
                                                                monkeypatch: pytest.MonkeyPatch, text: str):
    box = make_box()
    box.start()
    assert box.exec("echo hi", 30).ok and _calls(fake_tart)[-1][2:4] == ["sudo", "-n"]  # success: no probe
    monkeypatch.setenv("FAKE_STDERR", text + "\n")
    monkeypatch.setenv("FAKE_EXIT", "2")
    result = box.exec("my-tool --check", 30)
    assert result.exit_code == 2 and text in result.stderr and not result.timed_out
    assert _calls(fake_tart)[-1] == ["exec", "pf-verify-1-abc", "true"]  # the host's probe decided it


@POSIX_ONLY
def test_a_vm_that_is_gone_is_a_box_error(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    (fake_tart.parent / "stopped").touch()  # the fake `tart run` exits, as the real one does when its VM stops
    box.vm_proc.wait(timeout=10)
    with pytest.raises(BoxError, match=r"guest agent is gone: tart run exited with 0\): VM .* is not running"):
        box.exec("echo hi", 30)


@POSIX_ONLY
def test_a_guest_agent_that_is_gone_is_a_box_error(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    monkeypatch.setenv("FAKE_AGENT_GONE", "1")
    with pytest.raises(BoxError, match=r"gone: `tart exec pf-verify-1-abc true` exited 1: .*Guest Agent running"):
        box.exec("echo hi", 30)
    assert box.vm_proc.poll() is None  # the VM still runs; the agent probe is what failed


@POSIX_ONLY
def test_read_file_turns_a_hung_agent_into_a_box_error(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()

    def hangs(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    with monkeypatch.context() as m:
        m.setattr(tb.subprocess, "run", hangs)
        with pytest.raises(BoxError, match="cannot read notes.txt: tart exec did not return within 35s"):
            box.read_file("notes.txt")


@POSIX_ONLY
def test_an_mdns_probe_that_cannot_run_fails_closed(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    monkeypatch.setenv("FAKE_FAIL_MATCH", f"{tb.HELPER_DIR}/mdns")  # exits 1 with no mdns= line
    with pytest.raises(BoxError, match="mDNS probe could not run: injected failure"):
        box._check_firewall(online=True)


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
@pytest.mark.parametrize(("code", "ok"), [("7", True), ("1", True), ("52", True), ("28", False), ("6", False)])
def test_positive_control_counts_any_reply_from_the_host(make_box, monkeypatch: pytest.MonkeyPatch, code: str,
                                                         ok: bool):
    # 11/18: a headless Mac mini has nothing on 5000/7000; its ports refuse (7), sshd sends a banner (1) and the KDC
    # closes (52). Each needs a reply from the host; a timeout (28) or a name failure (6) does not.
    monkeypatch.setenv("FAKE_POSCONTROL_HOST", code)
    box = make_box()
    box.start()
    results = {name: (passed, detail) for name, passed, _, detail in box.validate_containment()}
    assert results["probe_sees_open_host_port"][0] is ok
    if ok:
        assert f"(exit {code})" in results["probe_sees_open_host_port"][1]
        assert results["host_3000_blocked_online"][0]  # the ports that replied must drop once @host is blocked


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
    rules = INSTRUCTIONS.format(max_commands=15, max_turns=25, minutes=20, stdout_chars="6,000", command_max=500,
                                setup_max=4000,
                                box_kind=MacFakeBox.kind, box_rule=MacFakeBox.user_rule)
    assert 'disposable macOS virtual machine ("the box")' in rules and "not an admin" in rules


def test_linux_prompt_is_unchanged():
    rules = INSTRUCTIONS.format(max_commands=15, max_turns=25, minutes=20, stdout_chars="6,000", command_max=500,
                                setup_max=4000,
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


GUI_MANIFEST = {**MANIFEST, "base": "pickfit-macos-26-gui", "parent": "pickfit-macos-26", "build_id": "0a1b2c3d4e5f",
                "display": "1280x800px", "gui": True}


@POSIX_ONLY
def test_display_box_clones_the_gui_base_boots_with_vnc_and_keeps_its_port_from_the_guest(
        make_box, fake_tart: Path, state_dir: Path):
    (state_dir / "pickfit-macos-26-gui.json").write_text(json.dumps(GUI_MANIFEST))
    box = make_box(display=True)
    box.start()
    calls = _calls(fake_tart)
    assert ["clone", "pickfit-macos-26-gui", "pf-verify-1-abc"] in calls
    run = next(c for c in calls if c[0] == "run")
    assert "--vnc-experimental" in run and "--no-graphics" in run
    assert box.vnc_url == "vnc://:fake-pw@127.0.0.1:5999" and box.display == "vnc"
    assert stat.S_IMODE(box.vm_log.stat().st_mode) == 0o600  # the log holds the VNC password
    scripts = [c[-1] for c in calls if c[0] == "exec"]
    assert any("pgrep -u sbx -x Dock" in s for s in scripts)  # waited for sbx's desktop
    assert any("--run-rpc" in s and "admin is logged in" in s for s in scripts)  # GUI_CHECK, not HARDENED_CHECK
    assert any("http://$gw:5999/" in s or ":5999/" in s for s in scripts)  # the guest must not reach the VNC port
    assert box.session == {"401": ["Sun Nov  1 08:00:00 2026", "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock"]}
    assert "desktop (1280x800) where sbx is logged in" in box.describe()
    assert box.image.endswith("+pickfit-macos-26-gui@0a1b2c3d4e5f")


@POSIX_ONLY
def test_headless_box_has_no_vnc(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    assert box.display is None and box.vnc_url is None and box.session is None
    assert "--vnc-experimental" not in next(c for c in _calls(fake_tart) if c[0] == "run")
    assert "No display (the VM is headless)." in box.describe()
    with pytest.raises(BoxError, match="no display"):
        box.screen()


@POSIX_ONLY
def test_harness_exec_runs_as_root_or_a_uid_and_passes_stdin(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    result = box.harness_exec(["/bin/echo", "hi"], 10, stdin=b"payload")
    assert result.exit_code == 0 and result.stdout.strip() == "ok"
    assert _calls(fake_tart)[-1] == ["exec", "-i", "pf-verify-1-abc", "sudo", "-n", "/bin/echo", "hi"]
    assert (fake_tart.parent / "stdin.bin").read_bytes() == b"payload"
    box.harness_exec(["/usr/bin/true"], 10, as_uid=1001)
    assert _calls(fake_tart)[-1] == ["exec", "pf-verify-1-abc", "sudo", "-n", "-u", "#1001", "/usr/bin/true"]


def test_gui_base_script_logs_sbx_in_and_moves_exec_to_the_root_daemon():
    script = tb.GUI_ROOT
    assert 'PICKFIT_LOGIN_PW="$(openssl rand' in script and "unset PICKFIT_LOGIN_PW" in script
    assert "dscl . -passwd /Users/sbx" in script and "chmod 600 /etc/kcpassword" in script
    assert "autoLoginUser sbx" in script
    assert "Add :ProgramArguments:2 string --run-rpc" in script and f"rm -f {tb.AGENT_PLISTS[1]}" in script
    assert "com.apple.SetupAssistant.plist" in script
    check = tb.GUI_CHECK
    assert tb.AGENT_PLISTS[1] not in check.split("for plist in", 1)[1].split("\n", 1)[0]  # only the daemon is pinned
    assert 'fail "admin is logged in"' in check and '[ "$(id -u)" = 0 ]' in check
    assert "dscl . -authonly admin admin" in check and "pam_deny.so" in check  # the hardened checks still run
    assert all(p in tb.HARDENED_CHECK for p in tb.AGENT_PLISTS)  # the headless base's check is unchanged


@POSIX_ONLY
def test_failed_gui_base_build_deletes_it(fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "softnet_ready", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_FAIL_MATCH", "autoLoginUser")
    try:
        with pytest.raises(BoxError, match="GUI setup failed"):
            tb.prepare_gui_base(tart=str(fake_tart), state_dir=state_dir, log=lambda s: None)
    finally:
        (fake_tart.parent / "stopped").touch()
    calls = _calls(fake_tart)
    assert ["clone", "pickfit-macos-26", "pickfit-macos-26-gui"] in calls
    assert ["set", "pickfit-macos-26-gui", "--display", "1280x800px"] in calls
    assert calls[-1] == ["delete", "pickfit-macos-26-gui"]
    assert not (state_dir / "pickfit-macos-26-gui.json").exists()


@POSIX_ONLY
def test_gui_base_needs_a_hardened_parent_and_no_existing_copy(fake_tart: Path, state_dir: Path,
                                                               monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_BASE_EXISTS", "1")
    with pytest.raises(BoxError, match="already exists"):
        tb.prepare_gui_base(tart=str(fake_tart), state_dir=state_dir, log=lambda s: None)
    (state_dir / "pickfit-macos-26.json").write_text(json.dumps({**MANIFEST, "hardened": False}))
    with pytest.raises(BoxError, match="not hardened"):
        tb.prepare_gui_base(tart=str(fake_tart), state_dir=state_dir, log=lambda s: None)


@POSIX_ONLY
def test_read_result_reads_as_the_box_user_and_decodes(make_box, fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    with pytest.raises(BoxError, match="cannot read"):  # the fake answers "ok", which is not base64 of a file
        box.read_result("/Users/sbx/Documents/x.txt")
    call = _calls(fake_tart)[-1]
    assert call[2:6] == ["sudo", "-n", "-u", "#1001"] and call[-1] == "/Users/sbx/Documents/x.txt"
    assert "set -o pipefail" in call[8]


@POSIX_ONLY
def test_a_box_that_cannot_reach_github_says_so_from_the_start(make_box, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_REACH_GITHUB", "28")
    monkeypatch.setenv("FAKE_REACH_GHCR", "28")
    box = make_box()
    box.start()
    assert box.unreachable == ["github.com", "ghcr.io"] and box.network_enabled
    assert "github.com and ghcr.io do not answer" in box.describe() and "do not hunt for mirrors" in box.describe()


@POSIX_ONLY
def test_a_box_that_reaches_github_says_nothing_about_it(make_box):
    box = make_box()
    box.start()
    assert box.unreachable == [] and "do not answer" not in box.describe()


# ---------------------------------------------------------------- the macOS GUI box's limits test (limits_mac, H-014)


@POSIX_ONLY
def test_display_box_scopes_tcc_before_any_box_user_code(
        make_box, fake_tart: Path, state_dir: Path):
    (state_dir / "pickfit-macos-26-gui.json").write_text(json.dumps(GUI_MANIFEST))
    make_box(display=True).start()
    scripts = [c[-1] for c in _calls(fake_tart) if c[0] == "exec"]
    setup = next(s for s in scripts if f"mkdir -p {tb.HELPER_DIR}" in s)
    assert tb.TCC_SCOPE in setup  # in the root setup, before start() returns and any model command runs


@POSIX_ONLY
def test_headless_box_leaves_tcc_alone(make_box, fake_tart: Path):
    make_box().start()
    assert not any(tb.TCC_SCOPE in c[-1] for c in _calls(fake_tart) if c[0] == "exec")


# The source image's grants (measured 11/18 in pickfit-macos-15-gui) and what TCC_SCOPE leaves of them.
IMAGE_TCC = [("kTCCServicePostEvent", "com.apple.screensharing.agent", 0),
             ("kTCCServiceScreenCapture", "com.apple.screensharing.agent", 0),
             ("kTCCServiceSystemPolicyAllFiles", "/usr/libexec/sshd-keygen-wrapper", 1),
             ("kTCCServiceDeveloperTool", "com.apple.Terminal", 0)] + [
    (f"kTCCService{s}", client, kind) for client, kind, services in (
        ("/usr/libexec/sshd-keygen-wrapper", 1, ("Accessibility", "ScreenCapture", "PostEvent", "AppleEvents")),
        ("/usr/bin/osascript", 1, ("Accessibility", "ScreenCapture", "PostEvent", "AppleEvents")),
        ("org.python.python", 0, ("Accessibility", "ScreenCapture", "Microphone", "PostEvent")),
        ("/opt/homebrew/Cellar/tart-guest-agent/0.15.0/bin/tart-guest-agent", 1,
         ("Accessibility", "ScreenCapture", "Microphone", "PostEvent"))) for s in services]


def _tcc_db(path: Path, rows) -> Path:
    import sqlite3

    db = sqlite3.connect(path)
    db.execute("CREATE TABLE access (service TEXT NOT NULL, client TEXT NOT NULL, client_type INTEGER NOT NULL, "
               "auth_value INTEGER NOT NULL, auth_reason INTEGER NOT NULL, auth_version INTEGER NOT NULL, csreq BLOB, "
               "indirect_object_identifier TEXT NOT NULL DEFAULT 'UNUSED')")
    db.executemany("INSERT INTO access (service, client, client_type, auth_value, auth_reason, auth_version) "
                   "VALUES (?, ?, ?, ?, 0, 1)", [(s, c, k, v) for s, c, k, v in rows])
    db.commit()
    db.close()
    return path


def test_tcc_scope_keeps_only_osascripts_grants_for_pickfits_scroll(tmp_path: Path):
    import sqlite3

    path = _tcc_db(tmp_path / "TCC.db", [(s, c, k, 0 if "DeveloperTool" in s else 2) for s, c, k in IMAGE_TCC])
    sql = tb.TCC_SCOPE.split('"', 1)[1].rsplit('"', 1)[0]
    with sqlite3.connect(path) as db:
        db.execute(sql)
        left = sorted(db.execute("SELECT service, client FROM access").fetchall())
    assert left == [("kTCCServiceAccessibility", "/usr/bin/osascript"),
                    ("kTCCServiceDeveloperTool", "com.apple.Terminal"),  # denied, and not a service it covers
                    ("kTCCServicePostEvent", "/usr/bin/osascript")]
    assert ("kTCCServiceScreenCapture", "/usr/bin/osascript") not in left  # pickfit's screenshots are VNC's


@POSIX_ONLY
def test_tcc_check_flags_grants_a_program_of_sbxs_could_use(tmp_path: Path):
    from pickfit.verify import limits_mac as lm

    mine = tmp_path / "planted"
    mine.write_text("x")
    path = _tcc_db(tmp_path / "TCC.db", [("kTCCServicePostEvent", "/bin/sh", 1, 2),  # root's, nothing writable above
                                         ("kTCCServiceScreenCapture", str(mine), 1, 2),  # a path the user owns
                                         ("kTCCServiceAccessibility", "org.example.app", 0, 2),  # no code requirement
                                         ("kTCCServiceMicrophone", str(mine), 1, 0),  # denied: not a grant
                                         ("kTCCServiceLiverpool", str(mine), 1, 2)])  # not a service the check covers
    done = subprocess.run([sys.executable, "-I", "-c", lm.TCC_PY, str(path)], capture_output=True, text=True,
                          input=json.dumps({"services": list(tb.TCC_SERVICES)}), timeout=60, check=True)
    data = json.loads(done.stdout)
    assert data[str(path)]["kept"] == ["PostEvent /bin/sh"]
    assert lm.tcc_bad(data, str(path)) == [f"ScreenCapture {mine}", "Accessibility org.example.app"]
    assert lm.tcc_bad({str(path): {"rows": 0, "bad": []}}, str(path)) is None  # an empty read is no pass


@POSIX_ONLY
def test_secret_scan_returns_hashes_of_the_shape_and_never_the_strings(tmp_path: Path):
    from pickfit.verify import limits_mac as lm

    planted = lm.decoy()
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "note.txt").write_text(f"x {planted} y\nnot-four-words here\n")
    cfg = {"shape": lm.SECRET_SHAPE.decode(), "roots": [str(tmp_path)], "budget_s": 30, "ps": False}  # not this Mac's
    done = subprocess.run([sys.executable, "-I", "-c", lm.SCAN_PY], capture_output=True, text=True,
                          input=json.dumps(cfg), timeout=60, check=True)
    data = json.loads(done.stdout.strip().splitlines()[-1])
    assert data["files"] == 1 and not data["timed_out"] and lm._short(planted) in data["hashes"]
    assert planted not in done.stdout and len(data["hashes"]) == 1
    assert re.fullmatch(lm.SECRET_SHAPE, b"wxyz-abcd-efgh-ijkl") and not re.fullmatch(lm.SECRET_SHAPE, b"ab-cd-ef")


def test_limits_mac_parsers():
    from PIL import Image

    from pickfit.verify import limits_mac as lm

    sbx = "user is not a member of the group\nuser is not a member of the group\nGroupMembership: root admin\n"
    assert lm.standard_user(sbx, "sbx") and not lm.standard_user(sbx.replace("admin\n", "admin sbx\n"), "sbx")
    assert not lm.standard_user("user is a member of the group\n" + sbx.split("\n", 1)[1], "admin")
    assert not lm.standard_user("", "sbx")  # nothing read is no pass
    assert lm.owner_only("m1 600\nm1\n1\n") and not lm.owner_only("root 644\nm1\n0\n")
    assert not lm.owner_only("m1 640\nm1\n") and not lm.owner_only("other 600\nm1\n") and not lm.owner_only("")
    seen = lm.window_server("88 159 /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer\n"
                            "1001 152 /System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow\n"
                            "1001 774 /System/Library/CoreServices/Dock.app/Contents/MacOS/Dock\n")
    assert seen == {"WindowServer": ("88", "159"), "loginwindow": ("1001", "152"), "Dock": ("1001", "774")}
    row = [1124, 0, 118, 54, 601, 491, lm.TEXTEDIT, True]
    assert lm.app_window({"windows": [[1, 25, 0, 0, 30, 24, lm.TEXTEDIT, True], row]}) == row
    assert lm.app_window({"windows": [[*row[:7], False]]}) is None  # not an sbx process
    assert lm.app_window({"windows": [[*row[:4], 100, 50, *row[6:]]]}) is None  # too small to count
    assert lm.app_window(None) is None
    before = Image.new("L", (100, 80), 40)
    after = before.copy()
    after.paste(255, (10, 10, 60, 50))
    assert lm.changed_share(before, after, (10, 10, 50, 40)) == 1.0
    assert lm.changed_share(before, before, (10, 10, 50, 40)) == 0.0
    assert lm.changed_share(before, after, (200, 200, 10, 10)) == 0.0  # off screen
    assert lm.preflight('noise\n{"screen":false,"ax":true,"post":true,"listen":false}') == \
        {"screen": False, "ax": True, "post": True, "listen": False}
    assert lm.preflight("execution error") is None
    assert lm.screen_size() == (1280, 800)


class FakeGuiHost:
    name = "scw1"

    def __init__(self, box):
        self.box = box

    def run(self, argv, *, timeout, **kw):
        if self.box.host_error:
            raise OSError("ssh: connection refused")
        script = " ".join(argv)
        if "netstat" in script:
            out = "tcp46 0 0 *.5999 *.* LISTEN\n"
        elif argv[-1] == "/etc/hosts":
            out = "root 644\nm1\n0\n"
        else:
            out = f"m1 {self.box.log_mode}\nm1\n1\n"
        return subprocess.CompletedProcess(argv, 0, out, "")


class FakeGuiScreen:
    size = (1280, 800)

    def __init__(self, box):
        self.box = box

    def screenshot(self) -> bytes:
        import io

        from PIL import Image

        img = Image.linear_gradient("L").resize(self.size)
        if self.box.textedit:
            img.paste(255, (118, 54, 719, 545))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def click(self, *a):
        pass

    def key(self, *a):
        pass


class FakeControl:
    def __init__(self):
        self.allowed = False

    def set_rules(self, *, allow, block):
        self.allowed = "@host" in allow

    def set_policy(self, online):
        self.allowed = False


class FakeGuiBox:
    """What limits_mac's GUI checks ask of a TartBox with display=True, answered as the real one answered (11/18)."""

    os, runner, image, display, workdir = "macos", "tart-vz", "fake-gui", "vnc", "/Users/sbx/work"
    vnc_url = "vnc://:abcde-fghi-jklmn-opqrst@127.0.0.1:5999"
    vnc_host_port = 5999
    vm_log = ".pickfit/tart/pf-verify-1-abc.log"

    def __init__(self, **kw):
        self.session = {"774": ["Wed Nov 18 05:08:00 2026", "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock"]}
        self.textedit = False
        self.network_enabled = True
        self.control = FakeControl()
        self.files: dict[str, str] = {}
        self.jobs: dict[str, str] = {}
        self.log_mode, self.leak, self.bad_tcc, self.admin, self.host_error = "600", False, [], False, False
        self.__dict__.update(kw)
        self.host = FakeGuiHost(self)
        self._screen = FakeGuiScreen(self)
        self.calls: list[str] = []

    def screen(self):
        return self._screen

    def write_file(self, path, content):
        self.files[path] = content

    def _r(self, out="", code=0):
        return tb.ExecResult("x", code, out, "", 0.1)

    def exec(self, command, timeout_s, *, cwd=None):
        self.calls.append(f"sbx: {command}")
        if "test -w" in command:
            return self._r("own /Users/sbx/.pickfit-gui\n")
        if "cp /usr/bin/osascript" in command:
            return self._r("planted\n")
        if command.startswith("/usr/bin/osascript"):
            return self._r('{"screen":false,"ax":false,"post":false,"listen":false}\n')
        if "kill -0" in command:
            return self._r("bash: kill: (159) - Operation not permitted\nws=1\ndock=0\n")
        if "tail -c 3000" in command:
            return self._r('PICKFIT_GUI_0 {"windows": [{"title": "forged"}]}\n')
        return self._r()

    def harness_exec(self, argv, timeout_s, *, as_uid=None, stdin=None):
        from pickfit.verify import gui_mac
        from pickfit.verify import limits_mac as lm

        script = " ".join(argv)
        self.calls.append(f"root: {script[:200]}")
        if argv[-1] in ("stop", "approve", "sparkle", "procs", "items", "watch") and gui_mac.HELPER_PATH in argv:
            cmd = argv[-1]
            if cmd == "stop":
                return self._r("PICKFIT_KILLED 0 found 1\n")
            if cmd == "procs":
                return self._r(json.dumps(self.session) + "\n")
            if cmd == "watch":
                cfg = json.loads(stdin)
                report = {"alive": 1, "processes": ["pf-sleeper"], "windows": [], "screen": [1280, 800], "problems": []}
                return self._r(f"{cfg['mark']}{cfg['nonce']} {json.dumps(report)}\n")
            return self._r("[]\n")
        if lm.WINDOWS_PY in argv:
            rows = [[1124, 0, 118, 54, 601, 491, lm.TEXTEDIT, True]] if self.textedit else []
            return self._r(json.dumps({"screen": [1280, 800], "windows": rows}) + "\n")
        if lm.SCAN_PY in argv:
            found = [lm._short(m.group(0).decode()) for text in self.files.values()
                     for m in re.finditer(lm.SECRET_SHAPE, text.encode())]
            if self.leak:
                found.append(lm._short("abcde-fghi-jklmn-opqrst"))
            return self._r(json.dumps({"files": 70000, "too_big": 80, "timed_out": False, "hashes": found,
                                       "processes": 500, "vnc_urls": 0}) + "\n")
        if lm.TCC_PY in argv:
            db = argv[-1]
            bad = list(self.bad_tcc) + (["ScreenCapture /opt/homebrew/bin/pf-planted",
                                         "Accessibility org.example.pf-planted"] if db.startswith("/var/root") else [])
            return self._r(json.dumps({db: {"rows": 3, "kept": ["PostEvent /usr/bin/osascript"], "bad": bad}}) + "\n")
        if "submit" in argv:
            out, program = argv[argv.index("-o") + 1], argv[argv.index("--") + 1]
            self.jobs[out] = '{"screen":false,"ax":true,"post":true,"listen":true}' if program == "/usr/bin/osascript" \
                else '{"screen":false,"ax":false,"post":false,"listen":false}'
            return self._r()
        if argv[0] == "/bin/cat":
            return self._r(self.jobs.get(argv[1], "") + "\n")
        if "open -a TextEdit" in script:
            self.textedit = True
            return self._r("started\n")
        if "PICKFIT_GUI_0" in script:
            return self._r("started\n")
        if "pgrep -u 1001 -x TextEdit" in script:
            self.textedit = False
            return self._r("stopped\n")
        if "dsmemberutil" in script:
            member = "admin" in script.split("-U ")[1].split()[0] or self.admin
            return self._r(("user is a member of the group\n" if member else "user is not a member of the group\n")
                           + "user is not a member of the group\nGroupMembership: root admin\n")
        if "ps -axo uid=,pid=,comm=" in script:
            return self._r("88 159 /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer\n"
                           "1001 152 /System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow\n"
                           "1001 774 /System/Library/CoreServices/Dock.app/Contents/MacOS/Dock\n")
        return self._r()

    def _curl_codes(self, targets, timeout=4):
        return {name: 1 if self.control.allowed else 28 for name in targets}, ""

    def _check_firewall(self, *, online):
        pass

    def set_network(self, enabled):
        self.network_enabled = enabled


@pytest.fixture
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake answers at once: no polling sleeps (limits_mac and gui_mac wait for real windows and jobs)."""
    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)


def _gui_results(box) -> dict[str, Any]:
    from pickfit.verify import limits_mac

    results: list = []
    limits_mac.gui_probes(box, results.append)
    return {r.name: r for r in results}


GUI_CHECKS = ["desktop_screenshot", "app_window_seen", "report_unforgeable", "sbx_standard_user",
              "sbx_standard_user_control", "helper_locked", "helper_locked_control", "vnc_log_owner_only",
              "vnc_log_owner_only_control", "vnc_password_not_in_guest", "vnc_password_not_in_guest_control",
              "tcc_grants_scoped", "tcc_grants_scoped_control", "tcc_box_user_none", "tcc_box_user_none_control",
              "window_server_not_box_user", "window_server_not_box_user_control", "vnc_port_unreachable",
              "vnc_port_unreachable_control"]


def test_gui_checks_hold_on_a_box_set_up_as_the_harness_expects(no_wait):
    box = FakeGuiBox()
    results = _gui_results(box)
    assert list(results) == GUI_CHECKS
    assert all(r.ok for r in results.values()), [(r.name, r.detail) for r in results.values() if not r.ok]
    assert "abcde-fghi-jklmn-opqrst" not in json.dumps([r.detail for r in results.values()])  # the password stays out
    assert not any("abcde-fghi" in c for c in box.calls)  # and never goes into the guest
    assert box.network_enabled and not box.control.allowed


@pytest.mark.parametrize("setting, failed", [
    ({"leak": True}, "vnc_password_not_in_guest"),
    ({"log_mode": "644"}, "vnc_log_owner_only"),
    ({"bad_tcc": ["PostEvent /opt/homebrew/Cellar/tart-guest-agent/0.15.0/bin/tart-guest-agent"]}, "tcc_grants_scoped"),
    ({"admin": True}, "sbx_standard_user"),
])
def test_each_gui_check_fails_when_its_setting_is_different(setting, failed, no_wait):
    results = _gui_results(FakeGuiBox(**setting))
    assert [n for n, r in results.items() if not r.ok] == [failed]


def test_a_gui_check_that_cannot_run_fails_and_the_rest_still_run(no_wait):
    results = _gui_results(FakeGuiBox(host_error=True))
    assert not results["vnc_log_owner_only"].ok and "connection refused" in results["vnc_log_owner_only"].detail
    assert results["vnc_port_unreachable"].ok and results["tcc_grants_scoped"].ok


def test_gui_limits_test_runs_limits_py_without_its_xvfb_checks_then_the_gui_ones(monkeypatch: pytest.MonkeyPatch,
                                                                                  no_wait):
    from pickfit.verify import limits_mac

    seen = []

    def fake_limits(box, log=print):
        seen.append(box.display)
        assert box.os == "macos" and box.vnc_host_port == 5999  # everything else is the box's own
        return []

    monkeypatch.setattr(limits_mac, "run_limits_test", fake_limits)
    results = limits_mac.run_gui_limits_test(FakeGuiBox(), log=lambda s: None)
    assert seen == [None] and [r.name for r in results] == GUI_CHECKS


def test_the_gui_limits_test_needs_a_gui_tartbox(tmp_path: Path):
    from pickfit.verify import limits_mac

    with pytest.raises(ValueError, match="display=True"):
        limits_mac.gui_limits_test(lambda run_id, role: MacFakeBox(), tmp_path)
