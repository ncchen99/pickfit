"""TartBox with a fake `tart` executable: clone, boot, user switch, firewall, cleanup. No real VM."""

from __future__ import annotations

import json
import stat
import time
from pathlib import Path

import pytest

from pickfit.verify import tart_box as tb
from pickfit.verify.agent import INSTRUCTIONS, AgentLimits, render_task
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.limits import run_limits_test
from pickfit.verify.plan import plan_for
from pickfit.verify.tart_box import MAC_ENV, TartBox, image_label, pf_rules, prune_stale
from pickfit.verify.task import load_fixture
from verify_fakes import FakeBox

FIXTURES = Path(__file__).parent / "fixtures" / "verify"
MANIFEST = {"base": "pickfit-macos-26", "source": "ghcr.io/cirruslabs/macos-tahoe-base:latest",
            "source_digest": "sha256:0123456789abcdef0123", "macos": "26.6.2 (25G83)", "arch": "arm64",
            "brew": "5.0.1", "python3": "3.9.6", "uv": "0.9.5", "pipx": "1.8.0", "node": "v25.1.0", "npm": "11.6.2"}

FAKE_TART = """\
#!/usr/bin/env python3
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
open(os.path.join(here, "calls.jsonl"), "a").write(json.dumps(args) + "\\n")
cmd = args[0]
if cmd == "run":
    if os.environ.get("FAKE_RUN_FAIL"):
        print(os.environ["FAKE_RUN_FAIL"]); sys.exit(1)
    while not os.path.exists(os.path.join(here, "stopped")):
        time.sleep(0.05)
    sys.exit(0)
if cmd == "stop":
    open(os.path.join(here, "stopped"), "w").close()
if cmd == "list":
    print(os.environ.get("FAKE_LIST", "[]"))
if cmd == "exec":
    if os.environ.get("FAKE_RUN_FAIL"):
        sys.stderr.write('Error: VM "%s" is not running\\n' % args[1]); sys.exit(1)
    if "-i" in args:
        open(os.path.join(here, "stdin.bin"), "wb").write(sys.stdin.buffer.read())
    script = args[-1]
    if "networksetup -setdnsservers" in script:
        print("192.168.64.1")
    elif "pfctl -s info" in script:
        print("Status: Enabled for 0 days 00:00:01")
    elif os.environ.get("FAKE_STDERR"):
        sys.stderr.write(os.environ["FAKE_STDERR"])
        sys.exit(int(os.environ.get("FAKE_EXIT", "1")))
    else:
        print("ok")
    sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
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


def _calls(fake: Path) -> list[list[str]]:
    return [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text().splitlines()]


def _box(fake: Path, state: Path, **kw) -> TartBox:
    return TartBox(tart=str(fake), state_dir=state, name="pf-verify-1-abc", log=lambda s: None, **kw)


def test_start_clones_boots_sets_up_as_root_and_close_deletes(fake_tart: Path, state_dir: Path):
    box = _box(fake_tart, state_dir)
    box.start()
    calls = _calls(fake_tart)
    assert ["clone", "pickfit-macos-26", "pf-verify-1-abc"] in calls
    assert ["set", "pf-verify-1-abc", "--cpu", "4", "--memory", "8192"] in calls
    assert ["run", "--no-graphics", "--no-audio", "--no-clipboard", "pf-verify-1-abc"] in calls
    root = [c for c in calls if c[:5] == ["exec", "pf-verify-1-abc", "sudo", "-n", "/bin/sh"]]
    setup = root[-1][-1]
    assert "pfctl -q -f /usr/local/libexec/pickfit/pf-online.conf" in setup
    assert "192.168.64.1" in setup and "block drop out quick inet to" in setup  # resolver allowed, LAN not
    assert "os.killpg" in setup and "os.setsid()" in setup and "SIG_IGN" in setup  # timeout and detach helpers
    assert box.started and box.image.startswith("cirruslabs/macos-tahoe-base@sha256:0123456789ab macOS 26.6.2")
    box.close()
    assert _calls(fake_tart)[-2:] == [["stop", "pf-verify-1-abc", "--timeout", "10"], ["delete", "pf-verify-1-abc"]]
    assert not box.started
    with pytest.raises(BoxError):
        box.exec("echo again", 5)


def test_model_commands_run_as_the_box_user_with_limits_and_no_host_env(
        fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_API_KEY", "LLM_123_should_never_leak")
    box = _box(fake_tart, state_dir, limits=BoxLimits(max_command_s=100))
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
    box.close()


def test_network_cut_swaps_pf_rules_and_drops_open_connections(fake_tart: Path, state_dir: Path):
    box = _box(fake_tart, state_dir)
    box.start()
    box.set_network(False)
    assert _calls(fake_tart)[-1][-1] == (f"{tb.ROOT_PATH}\npfctl -q -f /usr/local/libexec/pickfit/pf-offline.conf"
                                         " && pfctl -q -F states")
    assert box.network_enabled is False
    box.set_network(True)
    assert "pf-online.conf" in _calls(fake_tart)[-1][-1] and box.network_enabled
    box.close()


def test_tart_failure_is_a_box_error_but_a_command_failure_is_not(
        fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    box = _box(fake_tart, state_dir)
    box.start()
    monkeypatch.setenv("FAKE_STDERR", "Error: the Docker daemon is not running\n")
    result = box.exec("docker ps", 10)
    assert result.exit_code == 1 and "daemon is not running" in result.stderr
    monkeypatch.setenv("FAKE_STDERR", 'Error: VM "pf-verify-1-abc" is not running\n')
    with pytest.raises(BoxError, match="guest agent is gone"):
        box.exec("true", 10)
    monkeypatch.delenv("FAKE_STDERR")
    box.close()


def test_in_guest_kill_is_a_timeout(fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    box = _box(fake_tart, state_dir)
    box.start()
    monkeypatch.setenv("FAKE_EXIT", "137")
    clock = iter([0.0, 5.0])
    monkeypatch.setattr(tb.time, "monotonic", lambda: next(clock))
    result = box.exec("sleep 99", 5)
    assert result.timed_out and result.exit_code == 137
    monkeypatch.setattr(tb.time, "monotonic", time.monotonic)
    monkeypatch.delenv("FAKE_EXIT")
    box.close()


def test_vm_limit_failure_names_the_reboot_and_cleans_up(
        fake_tart: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_RUN_FAIL", "Error: VZErrorVirtualMachineLimitExceeded")
    box = _box(fake_tart, state_dir)
    with pytest.raises(BoxError, match="reboot the Mac"):
        box.start()
    assert _calls(fake_tart)[-1] == ["delete", "pf-verify-1-abc"] and not box.started


def test_missing_base_says_how_to_prepare_it(fake_tart: Path, tmp_path: Path):
    box = TartBox(tart=str(fake_tart), state_dir=tmp_path, log=lambda s: None)
    with pytest.raises(BoxError, match="--prepare-base"):
        box.start()


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
    assert "pass out quick inet proto { tcp, udp } to { 192.168.64.1 } port 53" in online
    assert "169.254.0.0/16" in online and "192.168.0.0/16" in online and "block return out quick inet6 all" in online
    assert online.rstrip().endswith("pass out inet all")
    assert pf_rules(False, ["192.168.64.1"]) == "set skip on lo0\nblock drop all\n"


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


def test_macos_limits_probes_check_admin_firewall_and_host():
    box = MacFakeBox({"id -u": (0, "1001\nstaff everyone\nsudo: a password is required\nsudo=1\n", ""),
                      "pfctl -d": (1, "", "pfctl: /dev/pf: Permission denied"),
                      "route -n get default": (28, "", "curl: (28) Connection timed out"),
                      "curl -sS -I": (0, "200", "")})
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    assert results["non_admin"].ok and results["firewall_locked"].ok and results["host_blocked"].ok
    assert "memory_cap" not in results and "non_root" not in results
    assert any(cmd.startswith(f"{tb.DETACH_CMD} python3 -m http.server") for cmd, _ in box.ran)
