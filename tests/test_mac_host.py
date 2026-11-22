"""pickfit mac-host: a fake `scw` for the provider, a fake host for the checks, a fake runner for the end-to-end
test. Nothing here reaches Scaleway or a Mac."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pickfit.verify import mac_host as mh
from pickfit.verify.box import BoxError

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the fake scw is a #! script")

SERVER = {"id": "srv-1", "ip": "203.0.113.7", "ssh_username": "m1", "status": "ready", "type": "M4-SP",
          "created_at": "2026-11-17T15:42:26Z", "deletable_at": "2026-11-18T15:42:26Z",
          "os": {"name": "macos-sequoia-15", "version": "15"}, "sudo_password": "NEVER-KEEP-ME",
          "nested": {"vnc_password": "NOR-ME", "ok": 1}}

FAKE_SCW = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
open(os.path.join(here, "scw.jsonl"), "a").write(json.dumps(args) + "\n")
server = json.loads(os.environ["FAKE_SERVER"])
def out(v): print(json.dumps(v)); sys.exit(0)
if args[:3] == ["apple-silicon", "os", "list"]:
    out([{"id": "os-26", "version": "26", "is_beta": False}, {"id": "os-15", "version": "15", "is_beta": False},
         {"id": "os-15b", "version": "15", "is_beta": True}])
if args[:3] == ["apple-silicon", "server-type", "list"]:
    zone = next((a.split("=", 1)[1] for a in args if a.startswith("zone=")), "")
    by_zone = json.loads(os.environ.get("FAKE_STOCK_BY_ZONE", "{}"))
    stock = by_zone[zone] if zone in by_zone else json.loads(
        os.environ.get("FAKE_STOCK", '{"M4-S": "available", "M4-SP": "low_stock"}'))
    out([{"name": k, "stock": v} for k, v in stock.items()])
if args[:3] == ["apple-silicon", "server", "create"]:
    if "type=" + os.environ.get("FAKE_CREATE_FAILS", "-") in args:
        sys.stderr.write("out of stock\n"); sys.exit(1)
    out({**server, "status": "starting"})
if args[:3] in (["apple-silicon", "server", "wait"], ["apple-silicon", "server", "get"]):
    out(server)
if args[:3] == ["apple-silicon", "server", "delete"]:
    out(None)
if args[:3] == ["iam", "ssh-key", "list"] and os.environ.get("FAKE_IAM_ERROR"):
    sys.stderr.write(os.environ["FAKE_IAM_ERROR"] + "\n"); sys.exit(1)
if args[:3] == ["iam", "ssh-key", "list"]:
    out(json.loads(os.environ.get("FAKE_KEYS", "[]")))
if args[:3] == ["iam", "ssh-key", "create"]:
    out({"id": "key-1"})
sys.stderr.write("unexpected scw call\n"); sys.exit(9)
'''
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaFAKE pickfit-mac-host"


@pytest.fixture
def scw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "scw"
    path.write_text(FAKE_SCW)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_SERVER", json.dumps(SERVER))
    return path


def _scw_calls(scw: Path) -> list[list[str]]:
    log = scw.parent / "scw.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_scrub_drops_password_fields_at_any_depth():
    assert mh.scrub(SERVER)["nested"] == {"ok": 1}
    assert "sudo_password" not in mh.scrub(SERVER) and "NEVER" not in json.dumps(mh.scrub([SERVER]))


def test_macos_table_and_newer_hosts():
    assert mh.macos_for(15).softnet == "0.23.0" and mh.macos_for(15).base == "pickfit-macos-15"
    assert mh.macos_for(26).softnet == "0.24.1" and "tahoe" in mh.macos_for(26).source
    assert mh.macos_for(27) == mh.MACOS[26]  # a newer macOS still has 26's vmnet
    with pytest.raises(BoxError, match="macOS 14"):
        mh.macos_for(14)
    with pytest.raises(BoxError, match="not known"):
        mh.macos_for(None)


@POSIX_ONLY
def test_scaleway_create_falls_back_past_a_type_that_sold_out_and_keeps_no_password(scw: Path, tmp_path: Path,
                                                                                    monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_CREATE_FAILS", "M4-S")
    logs: list[str] = []
    rec = mh.ScalewayProvider(scw=str(scw)).create("mac1", 15, PUBLIC_KEY, logs.append)
    calls = _scw_calls(scw)
    creates = [c for c in calls if c[:3] == ["apple-silicon", "server", "create"]]
    assert [next(a for a in c if a.startswith("type=")) for c in creates] == ["type=M4-S", "type=M4-SP"]
    assert all("os-id=os-15" in c and "zone=fr-par-1" in c for c in creates)  # not the beta, not 26
    assert ["iam", "ssh-key", "create", "name=pickfit-mac1", f"public-key={PUBLIC_KEY}", "-o", "json"] in calls
    assert rec.target == "m1@203.0.113.7" and rec.macos == 15 and rec.server_id == "srv-1"
    saved = rec.save(tmp_path / "hosts").read_text()
    assert "NEVER-KEEP-ME" not in saved and "NOR-ME" not in saved and "password" not in saved
    assert any("24 h" in line for line in logs)


@POSIX_ONLY
def test_scaleway_reuses_a_registered_key_and_refuses_when_nothing_is_in_stock(scw: Path,
                                                                             monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_KEYS", json.dumps([{"public_key": "ssh-ed25519 AAAAC3NzaFAKE other-comment"}]))
    monkeypatch.setenv("FAKE_STOCK", json.dumps({"M4-S": "no_stock", "M4-SP": "no_stock"}))
    with pytest.raises(BoxError, match="in stock"):
        mh.ScalewayProvider(scw=str(scw)).create("mac1", 15, PUBLIC_KEY, print)
    calls = _scw_calls(scw)
    assert not any(c[:3] == ["iam", "ssh-key", "create"] for c in calls)
    assert not any(c[:3] == ["apple-silicon", "server", "create"] for c in calls)


@POSIX_ONLY
def test_scaleway_delete_waits_for_the_24_hours(scw: Path):
    rec = mh.HostRecord(name="mac1", provider="scaleway", target="m1@203.0.113.7", server_id="srv-1",
                        zone="fr-par-1")
    provider = mh.ScalewayProvider(scw=str(scw))
    with pytest.raises(BoxError, match="after 2026-11-18T15:42:26Z"):
        provider.delete(rec, print, now=datetime(2026, 11, 18, 12, 0, tzinfo=UTC))
    assert not any(c[:3] == ["apple-silicon", "server", "delete"] for c in _scw_calls(scw))
    provider.delete(rec, print, now=datetime(2026, 11, 18, 16, 0, tzinfo=UTC))
    assert ["apple-silicon", "server", "delete", "srv-1", "zone=fr-par-1", "-o", "json"] in _scw_calls(scw)


class FakeHost:
    """Stands in for SshHost: answers the FACTS script with canned key=value lines and records everything else."""

    name = "203.0.113.7"

    def __init__(self, facts: dict[str, str], boot: str = "ok 9s") -> None:
        self.facts, self.boot, self.calls = facts, boot, []

    def run(self, argv, *, timeout, text=True, input=None):  # noqa: A002
        self.calls.append((argv, input))
        script = argv[2] if argv[:2] == ["/bin/bash", "-c"] else ""
        if script == mh.FACTS:
            out = "".join(f"{k}={v}\n" for k, v in self.facts.items())
        elif script == mh.BOOT_PROBE:
            out = f"boot={self.boot}\n"
        else:
            out = ""
        return subprocess.CompletedProcess(argv, 0, out, "")


READY = {"macos": "15.8.3", "arch": "arm64", "user": "m1", "console": "m1", "tart": mh.TART_VERSION,
         "softnet": "softnet 0.23.0-e5fd48c", "softnet_mode": "0 104755",
         "images": "pickfit-macos-15 ghcr.io/cirruslabs/macos-sequoia-base:latest", "rootsetup": "yes"}


def _ops(facts: dict[str, str], tmp_path: Path, **kw) -> mh.HostOps:
    rec = mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7", macos=15)
    return mh.HostOps(rec, host=FakeHost(facts, **kw), log=lambda s: None, state_dir=tmp_path / "state")


def test_checks_pass_on_a_ready_host_and_boot_a_vm(tmp_path: Path):
    ops = _ops(READY, tmp_path)
    checks = {c.name: c for c in ops.checks(boot=True)}
    assert mh.ready(list(checks.values()))
    assert checks["vm_boots"].ok and "ok 9s" in checks["vm_boots"].detail
    assert not checks["base:pickfit-macos-15"].ok  # informational: no manifest yet, and ready() ignores it
    boot = next(argv for argv, _ in ops.host.calls if argv[2] == mh.BOOT_PROBE)
    assert boot[-1] == "ghcr.io/cirruslabs/macos-sequoia-base:latest"


@pytest.mark.parametrize(("change", "failing"), [
    ({"softnet_mode": "501 100755"}, "softnet_setuid"),
    ({"console": "root"}, "auto_login"),
    ({"softnet": "softnet 0.24.1"}, "softnet"),  # 0.24 does not load on macOS 15
    ({"tart": "2.30.0"}, "tart"),
    ({"images": ""}, "source_image"),
])
def test_checks_name_what_is_missing(tmp_path: Path, change: dict[str, str], failing: str):
    checks = _ops({**READY, **change}, tmp_path).checks(boot=True)
    bad = [c.name for c in checks if not c.ok and not c.name.startswith("base:")]
    assert bad == [failing] and not mh.ready(checks)
    assert not any(c.name == "vm_boots" for c in checks)  # no boot probe on a host that is not ready


def test_a_vm_that_does_not_boot_fails_the_check(tmp_path: Path):
    checks = _ops(READY, tmp_path, boot="failed Failed to create new HostKey").checks(boot=True)
    assert not mh.ready(checks) and "HostKey" in next(c.detail for c in checks if c.name == "vm_boots")


def test_prepare_installs_writes_the_root_step_and_pulls_once(tmp_path: Path):
    ops = _ops({**READY, "images": ""}, tmp_path)
    assert ops.prepare() == mh.MACOS[15]
    scripts = [(argv, stdin) for argv, stdin in ops.host.calls]
    install = next(a[2] for a, _ in scripts if a[:2] == ["/bin/bash", "-c"] and "fetch tart" in a[2])
    assert "openai/softnet/releases/download/0.23.0/softnet.tar.gz" in install and "shasum -a 256" in install
    assert any(stdin == mh.ROOT_SETUP for _, stdin in scripts)
    assert ["tart", "pull", mh.MACOS[15].source] in [a for a, _ in scripts]
    ops2 = _ops(READY, tmp_path)
    ops2.prepare()
    assert not any(a[:2] == ["tart", "pull"] for a, _ in ops2.host.calls)  # the image is there already


def test_root_step_is_typed_by_a_person_or_piped():
    rec = mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7", key="/k/mac", port=2222)
    argv = mh.root_command(rec)
    assert argv[:2] == ["ssh", "-t"] and "-i" in argv and "2222" in argv and argv[-2] == "m1@203.0.113.7"
    assert argv[-1] == f"{mh.HOST_PYTHON} -I .pickfit/rootsetup.py"
    piped = mh.root_command(rec, password_stdin=True)
    assert "-t" not in piped and piped[-1].endswith("--password-stdin")
    compile(mh.ROOT_SETUP, "rootsetup", "exec")
    assert "--password-stdin" in mh.ROOT_SETUP and "sudo\", \"-S\", \"-p\", \"\", \"-v\"" in mh.ROOT_SETUP.replace(
        "\"/usr/bin/sudo\"", "\"sudo\"")


def test_kcpassword_encoding_round_trips():
    # The same transform rootsetup.py applies: password + NUL, padded to 12, XOR Apple's key.
    ns: dict = {}
    exec(mh.ROOT_SETUP.split("user = ")[0], ns)  # imports and KEY only
    key = ns["KEY"]
    pw = b"correct horse"
    data = pw + b"\0" + os.urandom(-(len(pw) + 1) % 12)
    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    dec = bytes(b ^ key[i % len(key)] for i, b in enumerate(enc))
    assert len(enc) % 12 == 0 and dec.split(b"\0")[0] == pw


def test_plan_runs_free_steps_and_paid_ones_only_when_asked():
    steps = mh.plan_steps(rebuild=False, has_base=True, has_gui_base=False, verify=None, record=None)
    assert [s.name for s in steps] == ["limits", "gui-base", "gui-limits"] and not any(s.paid for s in steps)
    gui_limits = next(s for s in steps if s.name == "gui-limits").argv
    assert "--display" in gui_limits and "--limits-test" in gui_limits and "--prepare-base" not in gui_limits
    steps = mh.plan_steps(rebuild=False, has_base=True, has_gui_base=True, verify=None, record=None)
    assert [s.name for s in steps] == ["limits", "gui-limits"]  # the GUI box's checks run even with its base built
    steps = mh.plan_steps(rebuild=True, has_base=True, has_gui_base=True, verify="oraios/serena", record="gifski")
    assert [s.name for s in steps] == ["base", "limits", "gui-base", "gui-limits", "verify", "record"]
    assert [s.name for s in steps if s.paid] == ["verify", "record"]
    record = next(s for s in steps if s.name == "record")
    # PICKFIT_RECORD is off by default (brief §15.7): only the video step turns it on, for its own process.
    assert "--editor" in record.argv and dict(record.env) == {"PICKFIT_RECORD": "replay"}
    assert not any(s.env for s in steps if s.name != "record")


def test_record_needs_an_explicit_allowance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(mh, "HOSTS_DIR", tmp_path)
    mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7").save()
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    monkeypatch.setattr(mh, "HostOps", lambda *a, **k: pytest.fail("the host was touched without the allowance"))
    args = SimpleNamespace(mac_command="test", name="mac1", record="gifski", verify=None, rebuild=False,
                           keep_going=False)
    assert mh.main_command(args) == 2
    assert "PICKFIT_ALLOW_RECORD=1" in capsys.readouterr().err


def test_a_steps_own_env_reaches_only_its_process(tmp_path: Path):
    rec = mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7", key="/k/mac", macos=15)
    seen: dict[str, dict[str, str]] = {}

    def runner(argv, *, env, stdout, stderr, text):
        seen[argv[-1]] = env
        return subprocess.CompletedProcess(argv, 0)

    steps = [mh.Step("a", ("x", "a")), mh.Step("b", ("x", "b"), env=(("PICKFIT_RECORD", "replay"),))]
    mh.run_test(rec, steps, tmp_path / "out", log=lambda s: None, python="py", runner=runner)
    assert seen["b"]["PICKFIT_RECORD"] == "replay" and seen["a"].get("PICKFIT_RECORD") != "replay"


def test_run_test_uses_the_hosts_env_and_stops_at_the_first_failure(tmp_path: Path):
    rec = mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7", key="/k/mac", macos=15)
    seen: list[tuple[list[str], dict[str, str]]] = []

    def runner(argv, *, env, stdout, stderr, text):
        seen.append((argv, env))
        stdout.write("line\n")
        return subprocess.CompletedProcess(argv, 1 if "--display" in argv else 0)

    steps = mh.plan_steps(rebuild=False, has_base=True, has_gui_base=False, verify="o/r", record=None)
    report = mh.run_test(rec, steps, tmp_path / "out", log=lambda s: None, python="py", runner=runner)
    assert [s["step"] for s in report["steps"]] == ["limits", "gui-base"] and not report["passed"]
    assert all(env["PICKFIT_TART_HOST"] == "m1@203.0.113.7" and env["PICKFIT_TART_BASE"] == "pickfit-macos-15"
               and env["PICKFIT_TART_SSH_KEY"] == "/k/mac" for _, env in seen)
    assert json.loads((tmp_path / "out" / "report.json").read_text())["steps"][1]["exit"] == 1
    kept = mh.run_test(rec, steps, tmp_path / "out2", log=lambda s: None, python="py", runner=runner,
                       keep_going=True)
    assert [s["step"] for s in kept["steps"]] == ["limits", "gui-base", "gui-limits", "verify"] and not kept["passed"]


def test_down_needs_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(mh, "HOSTS_DIR", tmp_path)
    mh.HostRecord(name="mac1", provider="scaleway", target="m1@203.0.113.7", server_id="srv-1").save()
    monkeypatch.setattr(mh, "provider_for", lambda *a, **k: pytest.fail("deleted without --yes"))
    assert mh.main_command(SimpleNamespace(mac_command="down", name="mac1", yes=False)) == 2
    assert "--yes" in capsys.readouterr().out and (tmp_path / "mac1.json").exists()


def test_cli_parses_every_command():
    from pickfit.cli import main

    with pytest.raises(SystemExit) as done:
        main(["mac-host", "--help"])
    assert done.value.code == 0


def test_tart_gui_limits_test_runs_the_macos_checks_not_the_xvfb_ones(monkeypatch: pytest.MonkeyPatch):
    # limits.py's display probes are Xvfb's; in a macOS guest they could only fail (11/18). Until H-014 the CLI
    # refused; now it runs limits_mac (limits.py's other checks, then the macOS GUI box's own) on a GUI TartBox.
    from pickfit.cli import main
    from pickfit.verify import limits, limits_mac
    from pickfit.verify.limits import ProbeResult

    monkeypatch.setattr(limits, "limits_test", lambda *a, **k: pytest.fail("ran the Linux display probes"))
    boxes = []

    def fake(make_box, runs_dir, log=print):
        boxes.append(make_box("limits-x", "limits"))
        return [ProbeResult("desktop_screenshot", True, "", 0, 0.0, "")], runs_dir / "limits.json"

    monkeypatch.setattr(limits_mac, "gui_limits_test", fake)
    assert main(["verify", "--runner", "tart", "--display", "--limits-test"]) == 0
    assert boxes[0].display == "vnc" and boxes[0].base.endswith("-gui")
    monkeypatch.setattr(limits_mac, "gui_limits_test",
                        lambda *a, **k: ([ProbeResult("tcc_grants_scoped", False, "", 0, 0.0, "")], None))
    assert main(["verify", "--runner", "tart", "--display", "--limits-test"]) == 1  # one check failed


def test_a_base_built_by_another_harness_counts_by_the_manifest_on_the_host(tmp_path: Path):
    # 11/18: the watch saw the bases a laptop had built, without their manifests (kept on the laptop), and kept
    # retrying. The host lists the manifests it keeps beside its VMs; a copy cached here still counts.
    listed = {**READY, "images": f"{READY['images']} pickfit-macos-15-gui",
              "manifests": "pickfit-macos-15.json pickfit-macos-15-gui.json"}
    checks = {c.name: c.ok for c in _ops(listed, tmp_path).checks()}
    assert checks["base:pickfit-macos-15"] and checks["base:pickfit-macos-15-gui"]
    no_manifest = {**listed, "manifests": ""}
    checks = {c.name: c.ok for c in _ops(no_manifest, tmp_path).checks()}
    assert not checks["base:pickfit-macos-15"]  # a VM nobody vouches for
    cached = tmp_path / "state" / "hosts" / "203.0.113.7"
    cached.mkdir(parents=True)
    (cached / "pickfit-macos-15.json").write_text("{}")
    checks = {c.name: c.ok for c in _ops(no_manifest, tmp_path).checks()}
    assert checks["base:pickfit-macos-15"] and not checks["base:pickfit-macos-15-gui"]
    assert "manifests=" in mh.FACTS and ".pickfit/tart" in mh.FACTS


def test_the_same_configuration_error_twice_needs_an_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                             capsys: pytest.CaptureFixture[str]):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    context = mh.lane_context(tmp_path, rent=False)
    assert mh.operator_hold(tmp_path) is None
    first = mh.note_failure(tmp_path, "renting-off:", "no Mac host is ready", context=context, now=now)
    assert first["count"] == 1 and mh.operator_hold(tmp_path, context) is None  # once is not yet a pattern
    second = mh.note_failure(tmp_path, "renting-off:", "no Mac host is ready", context=context, now=now)
    assert second["count"] == 2 and mh.operator_hold(tmp_path, context)["first_at"] == "2026-11-19T12:00:00+00:00"
    assert "needs an operator: no Mac host is ready" in mh.hold_message(second)
    other = mh.note_failure(tmp_path, "rent-failed:quota", "quota", context=context, now=now)
    assert other["count"] == 1  # another error starts counting again
    mh.note_failure(tmp_path, "rent-failed:quota", "quota", context=context, now=now)
    assert mh.operator_hold(tmp_path, mh.lane_context(tmp_path, rent=True)) is None  # other settings: tried again
    mh.HostRecord(name="mac1", provider="ssh", target="m1@203.0.113.7").save(tmp_path)
    assert mh.operator_hold(tmp_path, mh.lane_context(tmp_path, rent=False)) is None  # a host was added
    assert not list(tmp_path.glob(mh.OPERATOR_FILE.replace(".txt", ".json")))  # never read as a host record
    monkeypatch.setattr(mh, "HOSTS_DIR", tmp_path)
    assert mh.main_command(SimpleNamespace(mac_command="list")) == 0
    assert "needs an operator: quota" in capsys.readouterr().out
    assert mh.main_command(SimpleNamespace(mac_command="clear")) == 0
    assert "try its hosts again" in capsys.readouterr().out and mh.operator_hold(tmp_path) is None
    assert mh.main_command(SimpleNamespace(mac_command="clear")) == 0
    assert "holds nothing" in capsys.readouterr().out


@POSIX_ONLY
def test_an_api_key_that_may_not_list_ssh_keys_still_rents_with_a_registered_key(scw: Path,
                                                                                monkeypatch: pytest.MonkeyPatch):
    # 11/20: the watch's IAM application has Apple silicon rights only, so `scw iam ssh-key list` is refused; the
    # rental used to stop there. Now it goes on with the key as one already in the project (--mac-key).
    monkeypatch.setenv("FAKE_IAM_ERROR", '{"error":"scaleway-sdk-go: insufficient permissions: list ssh_key"}')
    logs: list[str] = []
    rec = mh.ScalewayProvider(scw=str(scw)).create("mac1", 15, PUBLIC_KEY, logs.append)
    calls = _scw_calls(scw)
    assert rec.server_id == "srv-1"
    assert not any(c[:3] == ["iam", "ssh-key", "create"] for c in calls)
    assert any("may not list the project's SSH keys" in line for line in logs)
    # Any other failure to list keys still stops the rental.
    monkeypatch.setenv("FAKE_IAM_ERROR", "connection refused")
    with pytest.raises(BoxError, match="connection refused"):
        mh.ScalewayProvider(scw=str(scw)).create("mac2", 15, PUBLIC_KEY, print)


@POSIX_ONLY
def test_out_of_stock_in_paris_1_rents_in_paris_3_and_keeps_that_zone(scw: Path, tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch):
    # 11/20 evening: every type in fr-par-1 was out of stock for hours. The rental goes on to fr-par-3, and the host
    # remembers fr-par-3 for SSH, refresh and delete.
    monkeypatch.setenv("FAKE_STOCK_BY_ZONE", json.dumps({"fr-par-1": {"M4-S": "no_stock", "M4-SP": "no_stock"},
                                                         "fr-par-3": {"M2-M": "available"}}))
    logs: list[str] = []
    rec = mh.ScalewayProvider(scw=str(scw)).create("mac1", 15, PUBLIC_KEY, logs.append)
    creates = [c for c in _scw_calls(scw) if c[:3] == ["apple-silicon", "server", "create"]]
    assert len(creates) == 1 and "zone=fr-par-3" in creates[0] and "type=M2-M" in creates[0]
    assert rec.zone == "fr-par-3" and any("trying fr-par-3" in line for line in logs)
    later = mh.provider_for(rec, scw=str(scw))  # what refresh and delete use
    assert later.zones == ("fr-par-3",)
    later.delete(rec, print, now=mh.datetime(2026, 11, 19, tzinfo=mh.UTC))
    assert ["apple-silicon", "server", "delete", "srv-1", "zone=fr-par-3", "-o", "json"] in _scw_calls(scw)


@POSIX_ONLY
def test_out_of_stock_everywhere_says_so_and_rents_nothing(scw: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_STOCK_BY_ZONE", json.dumps({"fr-par-1": {"M4-S": "no_stock", "M2-M": "no_stock"},
                                                         "fr-par-3": {"M1-M": "available"}}))
    with pytest.raises(BoxError) as err:
        mh.ScalewayProvider(scw=str(scw)).create("mac1", 15, PUBLIC_KEY, print)
    text = str(err.value)
    assert "no Scaleway Mac mini is in stock in fr-par-1, fr-par-3" in text
    assert "M1-M (8 GB, too little for an 8 GiB macOS VM)" in text  # what fr-par-3 has, and why it is not rented
    assert not any(c[:3] == ["apple-silicon", "server", "create"] for c in _scw_calls(scw))


def test_zones_come_from_a_comma_list_or_the_default():
    assert mh.ScalewayProvider().zones == ("fr-par-1", "fr-par-3")
    assert mh.ScalewayProvider(zone="fr-par-3").zones == ("fr-par-3",)
    assert mh.ScalewayProvider(zone="fr-par-3, fr-par-1").zones == ("fr-par-3", "fr-par-1")
