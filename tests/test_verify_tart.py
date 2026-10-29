"""TartBox with a fake `tart` executable: clone, boot, user switch, hardening, firewall, cleanup. No real VM."""

from __future__ import annotations

import json
import stat
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pickfit.verify import tart_box as tb
from pickfit.verify.agent import INSTRUCTIONS, AgentLimits, render_task
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.limits import run_limits_test
from pickfit.verify.plan import plan_for
from pickfit.verify.tart_box import MAC_ENV, TartBox, firewall_holds, image_label, pf_rules, prune_stale
from pickfit.verify.task import load_fixture
from verify_fakes import FakeBox

FIXTURES = Path(__file__).parent / "fixtures" / "verify"
MANIFEST = {"base": "pickfit-macos-26", "source": "ghcr.io/cirruslabs/macos-tahoe-base:latest",
            "source_digest": "sha256:0123456789abcdef0123", "macos": "26.6.2 (25G83)", "arch": "arm64",
            "brew": "5.0.1", "python3": "3.9.6", "uv": "0.9.5", "pipx": "1.8.0", "node": "v25.1.0", "npm": "11.6.2",
            "hardened": True}

# Records its calls; `run` lasts until `stop` (30 s at most, so a failed test leaves nothing running).
# The firewall state follows the rules file the harness loads; FAKE_* variables inject failures.
FAKE_TART = """\
#!/usr/bin/env python3
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
open(os.path.join(here, "calls.jsonl"), "a").write(json.dumps(args) + "\\n")
env = os.environ.get
cmd = args[0]
if cmd == "run":
    if env("FAKE_RUN_FAIL"):
        print(env("FAKE_RUN_FAIL")); sys.exit(1)
    end = time.time() + 30
    while not os.path.exists(os.path.join(here, "stopped")) and time.time() < end:
        time.sleep(0.05)
    sys.exit(0)
if cmd == "stop":
    open(os.path.join(here, "stopped"), "w").close()
if cmd == "delete" and env("FAKE_DELETE_FAIL"):
    sys.stderr.write("Error: cannot delete\\n"); sys.exit(1)
if cmd == "get":
    sys.exit(0 if env("FAKE_BASE_EXISTS") else 1)
if cmd == "list":
    print(env("FAKE_LIST", "[]"))
if cmd == "exec":
    if env("FAKE_RUN_FAIL"):
        sys.stderr.write('Error: VM "%s" is not running\\n' % args[1]); sys.exit(1)
    if "-i" in args:
        open(os.path.join(here, "stdin.bin"), "wb").write(sys.stdin.buffer.read())
    script = args[-1]
    state = os.path.join(here, "pf-state")
    if env("FAKE_FAIL_MATCH") and env("FAKE_FAIL_MATCH") in script:
        print("injected failure"); sys.exit(1)
    if "dscl . -authonly admin admin" in script and "fail()" in script:  # the hardened check
        if env("FAKE_UNHARDENED"):
            print("admin still has the default password"); sys.exit(1)
        sys.exit(0)
    if "networksetup -setdnsservers" in script:
        print("192.168.64.1"); sys.exit(0)
    if "pf-offline.conf &&" in script:
        open(state, "w").write("offline")
    elif "pf-online.conf" in script:
        open(state, "w").write("online")
    if "pfctl -s info" in script:
        mode = open(state).read() if os.path.exists(state) else "online"
        print("Status: Disabled" if env("FAKE_PF_DISABLED") else "Status: Enabled for 0 days 00:00:01")
        print("---")
        print('block drop all label "pickfit-%s"' % mode)
        print("---")
        if "curl" in script:
            print("egress=%s" % env("FAKE_EGRESS", "28"))
        sys.exit(0)
    if env("FAKE_STDERR"):
        sys.stderr.write(env("FAKE_STDERR"))
        sys.exit(int(env("FAKE_EXIT", "1")))
    print("ok")
    sys.exit(int(env("FAKE_EXIT", "0")))
"""


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
def make_box(fake_tart: Path, state_dir: Path) -> Iterator[Callable[..., TartBox]]:
    """TartBoxes on the fake; every one is closed and its reaper killed when the test ends."""
    made: list[TartBox] = []

    def make(**kw) -> TartBox:
        box = TartBox(tart=str(fake_tart), state_dir=state_dir, name="pf-verify-1-abc", log=lambda s: None, **kw)
        made.append(box)
        return box

    yield make
    (fake_tart.parent / "stopped").touch()
    for box in made:
        box.cloned = False  # the fake may refuse to delete; the reaper still has to go
        box.close()


def _calls(fake: Path) -> list[list[str]]:
    return [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text().splitlines()]


def test_start_clones_boots_checks_hardening_and_close_deletes(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    calls = _calls(fake_tart)
    assert ["clone", "pickfit-macos-26", "pf-verify-1-abc"] in calls
    assert ["set", "pf-verify-1-abc", "--cpu", "4", "--memory", "8192"] in calls
    assert ["run", "--no-graphics", "--no-audio", "--no-clipboard", "pf-verify-1-abc"] in calls
    root = [c[-1] for c in calls if c[:5] == ["exec", "pf-verify-1-abc", "sudo", "-n", "/bin/sh"]]
    assert any("dscl . -authonly admin admin" in r and "pam_deny.so" in r for r in root)  # hardened check first
    setup = next(r for r in root if "pf-online.conf" in r and "PICKFIT_EOF" in r)
    assert "192.168.64.1" in setup and "block drop out quick inet to" in setup  # resolver allowed, LAN not
    assert "os.killpg" in setup and "os.setsid()" in setup and "SIG_IGN" in setup  # timeout and detach helpers
    assert "shutdown -h +22 " in setup  # the guest stops itself a minute after the 20-minute lifetime
    assert box._reaper is not None and box._reaper.poll() is None  # the host-side reaper waits
    assert box.started and box.image.startswith("cirruslabs/macos-tahoe-base@sha256:0123456789ab macOS 26.6.2")
    reaper = box._reaper
    box.close()
    assert _calls(fake_tart)[-2:] == [["stop", "pf-verify-1-abc", "--timeout", "10"], ["delete", "pf-verify-1-abc"]]
    assert not box.started and reaper.poll() is not None and box._reaper is None
    with pytest.raises(BoxError):
        box.exec("echo again", 5)


def test_an_unhardened_base_is_refused_before_any_model_command(make_box, fake_tart: Path,
                                                                 monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_UNHARDENED", "1")
    box = make_box()
    with pytest.raises(BoxError, match="not hardened.*default password"):
        box.start()
    assert not any("sudo" in c and "-u" in c for c in _calls(fake_tart))  # no box-user command ran
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and not box.started


def test_a_manifest_from_before_hardening_is_refused(make_box, state_dir: Path):
    (state_dir / "pickfit-macos-26.json").write_text(json.dumps({**MANIFEST, "hardened": False}))
    with pytest.raises(BoxError, match="predates hardening"):
        make_box().start()


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


def test_network_cut_is_checked_with_pf_state_and_an_egress_probe(make_box, fake_tart: Path):
    box = make_box()
    box.start()
    box.set_network(False)
    calls = [c[-1] for c in _calls(fake_tart)]
    load = next(c for c in calls if "pfctl -q -f /usr/local/libexec/pickfit/pf-offline.conf" in c)
    assert load.endswith("pfctl -q -f /usr/local/libexec/pickfit/pf-offline.conf && pfctl -q -F states")
    assert tb.EGRESS_PROBE in calls[-1] and box.network_enabled is False
    box.set_network(True)
    calls = [c[-1] for c in _calls(fake_tart)]
    assert tb.EGRESS_PROBE in calls[-3]  # the cut is checked again before the network comes back
    assert "pf-online.conf" in calls[-2] and box.network_enabled


@pytest.mark.parametrize(("env", "match"), [("FAKE_PF_DISABLED", "pf is not enabled"),
                                            ("FAKE_EGRESS", "did not stop a connection")])
def test_a_cut_that_does_not_hold_is_a_box_error(make_box, monkeypatch: pytest.MonkeyPatch, env: str, match: str):
    box = make_box()
    box.start()
    monkeypatch.setenv(env, "0" if env == "FAKE_EGRESS" else "1")
    with pytest.raises(BoxError, match=match):
        box.set_network(False)
    assert box.network_enabled  # never marked offline


def test_turning_the_network_back_on_fails_if_the_cut_was_undone(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    box.set_network(False)
    monkeypatch.setenv("FAKE_PF_DISABLED", "1")  # something turned pf off while the box said offline
    with pytest.raises(BoxError, match="offline.*pf is not enabled"):
        box.set_network(True)


def test_firewall_holds_needs_pf_enabled_and_only_pickfit_rules():
    rules_on = pf_rules(True, ["192.168.64.1"]).split("\n", 1)[1]
    assert firewall_holds("Status: Enabled", rules_on, True) is None
    assert firewall_holds("Status: Enabled", rules_on, False).startswith("unexpected pf rule")
    assert firewall_holds("Status: Disabled", rules_on, True) == "pf is not enabled"
    assert firewall_holds("Status: Enabled", "No ALTQ support in kernel\n", True) == "no pf rules are loaded"
    extra = rules_on + 'pass out all label "someone-else"\n'
    assert "someone-else" in firewall_holds("Status: Enabled", extra, True)


def test_tart_failure_is_a_box_error_but_a_command_failure_is_not(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    monkeypatch.setenv("FAKE_STDERR", "Error: the Docker daemon is not running\n")
    result = box.exec("docker ps", 10)
    assert result.exit_code == 1 and "daemon is not running" in result.stderr
    monkeypatch.setenv("FAKE_STDERR", 'Error: VM "pf-verify-1-abc" is not running\n')
    with pytest.raises(BoxError, match="guest agent is gone"):
        box.exec("true", 10)


def test_in_guest_kill_is_a_timeout(make_box, monkeypatch: pytest.MonkeyPatch):
    box = make_box()
    box.start()
    monkeypatch.setenv("FAKE_EXIT", "137")
    clock = iter([0.0, 5.0])
    monkeypatch.setattr(tb.time, "monotonic", lambda: next(clock))
    result = box.exec("sleep 99", 5)
    assert result.timed_out and result.exit_code == 137
    monkeypatch.setattr(tb.time, "monotonic", time.monotonic)


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
    (fake_tart.parent / "stopped").touch()  # the VM process still ends
    box.close()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"]  # tried despite the stop error
    assert box.cloned and box._reaper is not None and box._reaper.poll() is None  # the reaper stays on it
    monkeypatch.delenv("FAKE_DELETE_FAIL")
    box.close()  # a second close deletes it and retires the reaper
    assert not box.cloned and box._reaper is None


def test_vm_limit_failure_names_the_reboot_and_cleans_up(make_box, fake_tart: Path,
                                                         monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_RUN_FAIL", "Error: VZErrorVirtualMachineLimitExceeded")
    box = make_box()
    with pytest.raises(BoxError, match="reboot the Mac"):
        box.start()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and not box.started


def test_missing_base_says_how_to_prepare_it(fake_tart: Path, tmp_path: Path):
    box = TartBox(tart=str(fake_tart), state_dir=tmp_path, log=lambda s: None)
    with pytest.raises(BoxError, match="--prepare-base"):
        box.start()


def test_failed_base_build_deletes_the_base_and_its_old_manifest(fake_tart: Path, tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tb, "STATE_DIR", tmp_path)
    (tmp_path / "pickfit-macos-26.json").write_text(json.dumps(MANIFEST))  # from an earlier build
    monkeypatch.setenv("FAKE_FAIL_MATCH", "sysadminctl")
    with pytest.raises(BoxError, match="base setup failed"):
        tb.prepare_base(tart=str(fake_tart), log=lambda s: None)
    calls = _calls(fake_tart)
    assert ["clone", tb.SOURCE_IMAGE, "pickfit-macos-26"] in calls and calls[-1] == ["delete", "pickfit-macos-26"]
    assert not (tmp_path / "pickfit-macos-26.json").exists()


def test_prepare_refuses_to_overwrite_an_existing_base(fake_tart: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_BASE_EXISTS", "1")
    with pytest.raises(BoxError, match="already exists"):
        tb.prepare_base(tart=str(fake_tart), log=lambda s: None)


def test_hardening_keeps_the_password_inside_the_guest():
    script = tb.HARDEN_ROOT
    assert 'PICKFIT_ADMIN_PW="$(openssl rand' in script and "unset PICKFIT_ADMIN_PW" in script
    assert "chmod 600 /etc/kcpassword" in script and "launchctl disable system/$svc" in script
    assert "com.openssh.sshd com.apple.screensharing" in script and "pam_deny.so" in script
    assert f"Set :ProgramArguments:0 {tb.AGENT_DIR}/tart-guest-agent" in script


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


def test_pf_rules_block_local_networks_online_and_everything_offline():
    online = pf_rules(True, ["192.168.64.1"])
    assert online.startswith("set skip on lo0\n")
    assert ('pass out quick inet proto { tcp, udp } to { 192.168.64.1 } port 53 label "pickfit-online"' in online)
    assert "port 68 to { 255.255.255.255, 192.168.64.1 } port 67" in online  # DHCP to the gateway only
    assert "169.254.0.0/16" in online and "192.168.0.0/16" in online and "block return out quick inet6 all" in online
    assert online.rstrip().endswith('pass out inet all label "pickfit-online"')
    assert pf_rules(False, ["192.168.64.1"]) == 'set skip on lo0\nblock drop all label "pickfit-offline"\n'


def test_image_label_names_source_digest_and_guest():
    label = image_label(MANIFEST)
    assert label == "cirruslabs/macos-tahoe-base@sha256:0123456789ab macOS 26.6.2 (25G83) +pickfit-macos-26"
    assert len(image_label({**MANIFEST, "macos": "x" * 200})) == 120


class MacFakeBox(FakeBox):
    os, arch, runner = "macos", "arm64", "tart-vz"
    kind, user_rule, detach = TartBox.kind, TartBox.user_rule, TartBox.detach
    home, workdir = "/Users/sbx", "/Users/sbx/work"

    def describe(self) -> str:
        box = TartBox(log=lambda s: None)
        box.manifest = MANIFEST
        return box.describe()


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


def test_macos_limits_probes_try_every_way_to_root():
    box = MacFakeBox({"id -u": (0, "1001\nstaff everyone\nsudo: a password is required\nsudo=1\n", ""),
                      "pfctl -d": (1, "", "pfctl: /dev/pf: Permission denied"),
                      "dscl . -authonly": (1, "", "Authentication failed"),
                      "pty.fork": (0, "Password:\r\nsu: Sorry\r\n", ""),
                      "cat /etc/kcpassword": (1, "", "Permission denied"),
                      "route -n get default": (28, "", "curl: (28) Connection timed out"),
                      "curl -sS -I": (0, "200", "")})
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    for name in ("non_admin", "firewall_locked", "admin_password", "su_admin", "remote_login_closed",
                 "kcpassword_unreadable", "agent_binary_locked", "host_blocked"):
        assert results[name].ok, name
    assert "memory_cap" not in results and "non_root" not in results
    assert any(cmd.startswith(f"{tb.DETACH_CMD} python3 -m http.server") for cmd, _ in box.ran)
    broken = MacFakeBox({"pty.fork": (0, "Password:\r\nPICKFIT_SU_OK\r\n", "")})
    assert not {r.name: r for r in run_limits_test(broken, log=lambda s: None)}["su_admin"].ok
