"""VBoxBox with a fake VBoxManage: reset order, network modes, containment, exit codes. No real VM.

The fake is a Python script run as [python, fake.py] (VBox takes an argv prefix), so these tests run on
Windows and macOS alike. It keeps VM state in a JSON file, writes the router's ready line to its serial
log on startvm, and answers guestcontrol runs by decoding the PowerShell the box sends in $env:PF_ENC.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pickfit.verify import vbox_box as vb
from pickfit.verify.agent import AgentLimits, render_task, tools_for
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.plan import plan_for
from pickfit.verify.task import load_fixture
from pickfit.verify.vbox_box import (
    HARDENED_CHECK,
    ROUTER_IP,
    VBoxBox,
    encode_ps,
    expected_vbm_code,
    parse_sentinel,
    with_exit_code,
)

FIXTURES = Path(__file__).parent / "fixtures" / "verify"
RULES = "71124c9d010096a2"

FAKE = r'''
import base64, json, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\n")
env = os.environ.get
state_path = os.path.join(here, "state.json")
state = json.load(open(state_path)) if os.path.exists(state_path) else {}
def save():
    json.dump(state, open(state_path, "w"))
def vm(name):
    return state.setdefault(name, {"VMState": "poweroff", "nic1": "intnet", "link": "on", "extra": {}})
def mapped(code):
    return 0 if code == 0 else code + 32 if 1 <= code <= 93 else 126

cmd = args[0]
if cmd == "showvminfo":
    v = vm(args[1]); save()
    nics = {"1": v["nic1"], "2": "nat" if args[1] == "pickfit-router" else "none"}
    nics.update(json.loads(env("FAKE_NICS_" + args[1].replace("-", "_").upper(), "{}")))
    print(f'VMState="{v["VMState"]}"')
    for slot in range(1, 9):
        print(f'nic{slot}="{nics.get(str(slot), "none")}"')
    print(f'intnet1="{env("FAKE_INTNET", "pickfit-net")}"')
    settings = dict(json.loads(env("FAKE_FEATURES", "{}"))) if args[1] == "pickfit-win11" else {}
    settings.update(json.loads(env("FAKE_SETTINGS", "{}")))
    for key, value in settings.items():
        if key != env("FAKE_DROP_KEY"):
            print(f'{key}="{value}"')
elif cmd == "controlvm":
    v = vm(args[1]); what = args[2]
    if what == "poweroff":
        v["VMState"] = "poweroff"
    elif what == "nic1":
        v["nic1"] = args[3]
    elif what == "setlinkstate1":
        v["link"] = args[3]
    save()
elif cmd == "startvm":
    v = vm(args[1]); v["VMState"] = "running"; save()
    if args[1] == "pickfit-router":
        serial = v["extra"].get("VBoxInternal/Devices/pcbios/0/Config/DmiSystemSerial", "pf:")
        extra = serial[3:] or "none"
        if env("FAKE_ROUTER_EXTRA"):
            extra = env("FAKE_ROUTER_EXTRA")
        if env("FAKE_ROUTER_SILENT"):
            sys.exit(0)
        mode = "r+" if env("FAKE_ROUTER_OVERWRITE") and os.path.exists(env("FAKE_SERIAL")) else "a"
        with open(env("FAKE_SERIAL"), mode) as f:  # r+: rewrite from the start without truncating, as VirtualBox can
            f.write(f"PICKFIT_ROUTER_READY rules={env('FAKE_RULES', 'RULES')} extra={extra} forward=1 "
                    f"ipv6_off=1 dnsmasq=up uplink=1\n")
elif cmd == "snapshot":
    vm(args[1])["restored"] = vm(args[1]).get("restored", 0) + 1; save()
elif cmd == "setextradata":
    vm(args[1])["extra"][args[2]] = args[3]; save()
elif cmd == "getextradata":
    if env("FAKE_EXTRADATA_FAIL") and args[2] == "pickfit/session":
        sys.stderr.write("VBoxManage: error: Could not find a registered machine\n"); sys.exit(1)
    val = vm(args[1])["extra"].get(args[2]); print(f"Value: {val}" if val else "No value set!")
elif cmd == "modifyvm":
    v = vm(args[1])
    if "--nic1" in args:
        v["nic1"] = args[args.index("--nic1") + 1]
    save()
elif cmd == "guestproperty":
    if "LoggedInUsersList" in args[-1]:
        print("Value: " + env("FAKE_LOGGED_IN", "sbx") if env("FAKE_LOGGED_IN", "sbx") else "No value set!")
    else:
        print("Value: 7.2.22r175245")
elif cmd == "guestcontrol" and args[2] in ("mkdir", "copyto"):
    if args[2] == "copyto":
        open(os.path.join(here, "copied.bin"), "wb").write(open(args[-2], "rb").read())
elif cmd == "guestcontrol" and args[2] == "run":
    v = vm(args[1])
    rest = args[args.index("--") + 1:]
    user = args[args.index("--username") + 1]
    puts = dict(args[i + 1].split("=", 1) for i, a in enumerate(args) if a == "--putenv")
    script = base64.b64decode(puts["PF_ENC"]).decode("utf-16-le")
    nonce = rest[rest.index("-Nonce") + 1]
    online = v["nic1"] == "intnet" and v["link"] == "on"
    nat = v["nic1"] == "nat"
    out, code = "", 0
    if "Write-Output ready" in script:
        out = "ready"
    elif "$bad = @()" in script:
        out, code = (env("FAKE_UNHARDENED"), 1) if env("FAKE_UNHARDENED") else ("hardened", 0)
    elif "setup-ok" in script:
        out = "setup-ok"
    elif "Get-NetRoute" in script:
        out = "10.99.0.1" if online else ""
    elif "probe.ps1" in script:
        targets = re.search(r"-Targets '([^']*)'", script).group(1)
        lines = []
        for t in filter(None, targets.split(",")):
            name = t.split("=")[0]
            if nat and name.startswith(("hostlan", "vboxnathost")):
                r = "open"
            elif name == "routerdns":
                r = "open" if online else "unreachable:NetworkUnreachable"
            else:
                r = "timeout" if online else "unreachable:NetworkUnreachable"
            r = env("FAKE_REACH_" + name.upper(), r) if online else env("FAKE_OFFLINE_" + name.upper(), r)
            lines.append(f"probe {name}={r}")
        if "-Url" in script:
            lines.append("probe public=" + ("curl0" if online or nat or env("FAKE_OFFLINE_LEAK") else "curl6"))
        out = "\n".join(lines)
    elif m := re.search(r"cmd /c exit (\d+)", script):
        code = int(m.group(1))
    elif "FAKE_GRANDCHILD" in script:  # a real exit 5, then something prints a fake success line
        sys.stdout.write(f"__PF_RC_{nonce}=5\n__PF_RC_{nonce}=0\n"); sys.stdout.flush(); sys.exit(mapped(5))
    elif "FAKE_LIES" in script:  # the command prints a fake sentinel; the wrapper's real one comes last
        out, code = f"__PF_RC_{nonce}=0", 7
    elif "PFB64:" in script:
        out = "PFB64:" + base64.b64encode(b"hello file").decode()
    else:
        out = f"ran as {user}"
    sys.stdout.write(out + f"\n__PF_RC_{nonce}={code}\n")
    sys.exit(mapped(code))
'''


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    script = tmp_path / "fake_vbm.py"
    script.write_text(FAKE, encoding="utf-8")
    state_dir = tmp_path / "state"
    (state_dir / "logs").mkdir(parents=True)
    serial = state_dir / "logs" / "pickfit-router-serial.log"
    monkeypatch.setenv("FAKE_SERIAL", str(serial))
    monkeypatch.setenv("FAKE_RULES", RULES)
    monkeypatch.setenv("FAKE_FEATURES", json.dumps(vb.GUEST_FEATURES_OFF))
    for name, data in (("pickfit-win11", {"base": "pickfit-win11", "windows": "26H2 (build 28000.1)",
                                          "virtualbox": "7.2.22r175245", "build_id": "b1", "hardened": True,
                                          "pwsh": "7.5.4", "python": "3.12.10"}),
                       ("pickfit-router", {"name": "pickfit-router", "rules": RULES, "build_id": "r1"})):
        (state_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(VBoxBox, "_start_reaper", lambda self: None)
    monkeypatch.setattr(vb, "host_lan_targets", lambda: {"hostlan": "192.168.1.20", "gateway": "192.168.1.1"})
    monkeypatch.setattr(vb, "host_public_ipv4", lambda: [])
    monkeypatch.setattr(vb, "host_egress_ipv4", lambda: [])
    monkeypatch.setattr(vb.time, "sleep", lambda s: None)

    class Fake:
        dir = tmp_path
        argv0 = [sys.executable, str(script)]

        def box(self, **kw) -> VBoxBox:
            return VBoxBox(vboxmanage=self.argv0, state_dir=state_dir, log=lambda m: None,
                           limits=BoxLimits(lifetime_s=600), **kw)

        def calls(self) -> list[list[str]]:
            path = tmp_path / "calls.jsonl"
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

        def state(self) -> dict:
            return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))

    return Fake()


# -- exit codes


@pytest.mark.parametrize("code,vbm", [(0, 0), (1, 33), (3, 35), (93, 125), (94, 126), (1603, 126), (137, 126)])
def test_vboxmanage_exit_code_mapping(code: int, vbm: int) -> None:
    assert expected_vbm_code(code) == vbm


def test_last_sentinel_wins_and_is_removed_from_stdout() -> None:
    out = "hello\n__PF_RC_abc=0\nmore\n__PF_RC_abc=1603\n"
    cleaned, code, warning = parse_sentinel(out, "abc", 126)
    assert (code, warning) == (1603, None)
    assert "1603" not in cleaned and "hello" in cleaned


def test_sentinel_that_disagrees_with_vboxmanage_is_not_trusted() -> None:
    _, code, warning = parse_sentinel("__PF_RC_n=5\n__PF_RC_n=0\n", "n", 37)
    assert code is None and "not trusted" in warning


def test_output_without_a_final_newline_keeps_its_last_line() -> None:
    # curl -w '%{http_code}' prints "200" with no newline; run.ps1 puts the sentinel on a line of its own
    assert parse_sentinel("200\n__PF_RC_n=0\n", "n", 0)[:2] == ("200", 0)
    assert parse_sentinel("line\r\n\r\n__PF_RC_n=0\r\n", "n", 0)[:2] == ("line\r\n", 0)
    assert "`n__PF_RC_" in vb.RUN_SCRIPT


def test_other_nonce_is_ignored() -> None:
    assert parse_sentinel("__PF_RC_other=0\n", "mine", 0)[1] is None


def test_pwsh_wrapper_exits_like_bash() -> None:
    wrapped = with_exit_code("cmd /c exit 1603")
    assert wrapped.index("cmd /c exit 1603") < wrapped.index("$__pf_ok = $?")
    assert "exit $LASTEXITCODE" in wrapped and wrapped.startswith("$global:LASTEXITCODE = 0")


def test_encoded_command_is_utf16le_base64() -> None:
    assert base64.b64decode(encode_ps("Write-Output 'ü'")).decode("utf-16-le") == "Write-Output 'ü'"


# -- the guestcontrol command line


def test_run_argv_puts_no_password_or_argv0_after_the_separator(fake) -> None:
    box = fake.box()
    argv = box.run_argv("sbx", "python --version", 30, r"C:\Users\sbx\work", "n0nce")
    rest = argv[argv.index("--") + 1:]
    assert argv[argv.index("--exe") + 1] == vb.WINPS
    assert rest[0] == "-NoLogo" and vb.WINPS not in rest  # program comes from --exe, not argv[0]
    assert "--passwordfile" in argv and "--password" not in argv
    assert argv[argv.index("--username") + 1] == "sbx"
    assert rest[rest.index("-File") + 1] == vb.RUN_PS1
    assert rest[rest.index("-Timeout") + 1] == "30"
    puts = [argv[i + 1] for i, a in enumerate(argv) if a == "--putenv"]
    assert "CI=1" in puts and not any(re.search(r"KEY|TOKEN|SECRET", p) for p in puts)
    # the command is in the environment, never on the command line Windows PowerShell logs
    enc = next(p for p in puts if p.startswith("PF_ENC="))[len("PF_ENC="):]
    assert "python --version" in base64.b64decode(enc).decode("utf-16-le")
    assert "-Enc" not in rest and "-EncodedCommand" not in rest and enc not in rest
    assert "-EncodedCommand" not in vb.RUN_SCRIPT and "-Command" in vb.RUN_SCRIPT and vb.PS_BOOT in vb.RUN_SCRIPT


# -- lifecycle


def test_start_resets_router_then_guest_and_checks_containment(fake) -> None:
    box = fake.box()
    box.start()
    calls = fake.calls()
    names = [" ".join(c[:3]) for c in calls]

    def first(prefix: str) -> int:
        return next(i for i, n in enumerate(names) if n.startswith(prefix))

    assert first("snapshot pickfit-win11 restore") < first("startvm pickfit-win11")
    assert first("snapshot pickfit-router restore") < first("startvm pickfit-router") < first("startvm pickfit-win11")
    nic = next(c for c in calls if c[0] == "modifyvm" and "--nic1" in c)
    assert nic[nic.index("--nic1") + 1] == "intnet" and nic[nic.index("--intnet1") + 1] == vb.INTNET
    scripts = [base64.b64decode(c[i + 1][len("PF_ENC="):]).decode("utf-16-le")
               for c in calls for i, a in enumerate(c) if a == "--putenv" and c[i + 1].startswith("PF_ENC=")]
    assert any("probe.ps1" in s for s in scripts)
    assert box.started and box.network_enabled and box.image.startswith("Windows 11 Enterprise Eval 26H2 (28000.1)")
    real = vb.image_label({"product": "Windows 11 Enterprise LTSC Evaluation", "windows": "24H2 (build 26100.1742)",
                           "virtualbox": "7.2.22r175245", "base": "pickfit-win11", "build_id": "42796005b373"},
                          {"build_id": "292c103299f8"})
    assert real.endswith("router@292c103299f8") and len(real) <= 120, real
    box.close()
    st = fake.state()
    assert st["pickfit-win11"]["VMState"] == "poweroff" and st["pickfit-router"]["VMState"] == "poweroff"
    assert st["pickfit-win11"]["restored"] == 2  # once before the run, once at close


@pytest.mark.parametrize("logged_in", ["", "Administrator"])
def test_no_command_runs_before_sbx_is_on_the_desktop(fake, monkeypatch, logged_in: str) -> None:
    monkeypatch.setenv("FAKE_LOGGED_IN", logged_in)
    monkeypatch.setattr(vb, "LOGON_WAIT_S", 0)
    with pytest.raises(BoxError, match="did not log on"):
        fake.box().start()
    assert not any(c[0] == "guestcontrol" and "--username" in c and c[c.index("--username") + 1] == "sbx"
                   for c in fake.calls())


def test_admin_checks_use_windows_powershell_and_model_commands_pwsh(fake) -> None:
    box = fake.box()
    for user, shell in (("Administrator", "powershell"), ("sbx", "pwsh")):
        rest = box.run_argv(user, "x", 30, r"C:\Users\sbx\work", "n")
        assert rest[rest.index("-Shell") + 1] == shell
    assert "WindowsPowerShell" in vb.RUN_SCRIPT and "pwsh.path" in vb.RUN_SCRIPT


def test_admin_commands_start_in_the_harness_directory_not_a_temp_dir_sbx_can_write(fake) -> None:
    box = fake.box()
    box.start()
    admin_runs = [c for c in fake.calls() if c[:1] == ["guestcontrol"] and "run" in c
                  and c[c.index("--username") + 1] == "Administrator"]
    assert admin_runs and all(c[c.index("--cwd") + 1] == vb.HARNESS_DIR for c in admin_runs)
    assert all(c[c.index("-Cwd") + 1] == vb.HARNESS_DIR for c in admin_runs)
    box.close()


def test_logon_passwords_reach_the_guest_only_through_the_environment() -> None:
    for script in (vb.SBX_AUTOLOGON, vb.ADMIN_AUTOLOGON, vb.ADMIN_SECRET_SCAN, vb.PROVISION_USERS):
        assert "$env:PF_SECRET" in script and "{pw}" not in script
    assert "[PfLsa]::Store('DefaultPassword'" in vb.SBX_AUTOLOGON
    assert "Remove-ItemProperty $wl DefaultPassword" in vb.SBX_AUTOLOGON
    assert "Set-LocalUser sbx -Password" in vb.PROVISION_USERS  # a resumed build gives sbx a new one too
    for log in ("Windows PowerShell", "Microsoft-Windows-PowerShell/Operational"):
        assert f"wevtutil cl '{log}'" in vb.HARDEN
    assert "$env:PF_SECRET2" in vb.ADMIN_SECRET_SCAN and "Get-WinEvent" in vb.ADMIN_SECRET_SCAN


def test_raw_ps_puts_the_script_and_secrets_in_the_environment_not_the_command_line(tmp_path) -> None:
    seen: list[list[str]] = []

    class Rec(vb.VBox):
        def __call__(self, *args, **kw):
            seen.append(list(args))
            return subprocess.CompletedProcess(args, 0, "ok", "")

    vb._raw_ps(Rec([sys.executable]), "vm", "Administrator", tmp_path / "pw", "'x-script'", 10,
               env={"PF_SECRET": "s3cret-value"})
    argv = seen[0]
    puts = dict(argv[i + 1].split("=", 1) for i, a in enumerate(argv) if a == "--putenv")
    assert puts["PF_SECRET"] == "s3cret-value"
    assert base64.b64decode(puts["PF_ENC"]).decode("utf-16-le") == "'x-script'"
    rest = argv[argv.index("--") + 1:]
    assert rest[rest.index("-Command") + 1] == vb.PS_BOOT and "-EncodedCommand" not in rest
    assert not any("s3cret-value" in a or "x-script" in a for a in rest)


def test_ps_quote_escapes_every_quote_powershell_honours() -> None:
    nasty = "a’; Write-Output INJECTED; ‘ b' ‚‛ $(Write-Output INJECTED) end"
    quoted = vb.ps_quote(nasty)
    for q in vb.PS_QUOTES:
        assert q in quoted
    if sys.platform == "win32":  # the real parser decides
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                              vb.encode_ps("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Write-Output "
                                           + quoted)],
                             capture_output=True, timeout=60)
        assert out.stdout.decode("utf-8").strip() == nasty


def test_logon_secret_probe_accepts_only_the_exact_clean_state() -> None:
    from pickfit.verify.box import ExecResult
    from pickfit.verify.limits import WIN_LOGON_EXPECT, _no_logon_secret, win_logon_secrets

    def result(lines: list[str], code: int = 0) -> ExecResult:
        return ExecResult(command="", exit_code=code, stdout="\n".join(lines) + "\n", stderr="", seconds=0.1,
                          timed_out=False, truncated=False)

    assert _no_logon_secret(result(WIN_LOGON_EXPECT))
    for i, bad in enumerate(["autologon=1 user=Administrator", "hklm_password=True", "hkcu_password=True",
                             "lsa=readable len=24", "answer_files=C:\\unattend.xml", "cdrom=1"]):
        lines = list(WIN_LOGON_EXPECT)
        lines[i] = bad
        assert not _no_logon_secret(result(lines)), bad
    assert not _no_logon_secret(result(["autologon=0 user=", *WIN_LOGON_EXPECT[1:]]))
    assert not _no_logon_secret(result(WIN_LOGON_EXPECT[:-1]))  # a line missing is a failure, not a pass
    assert not _no_logon_secret(result(WIN_LOGON_EXPECT, code=1))
    probe = win_logon_secrets()
    for needle in ("HKCU:", "[PfLsa]::Probe('DefaultPassword')", "Win32_CDROMDrive", "autounattend.xml",
                   "Panther\\Unattend", "Sysprep\\unattend.xml"):
        assert needle in probe


def test_standard_user_check_wants_users_only_medium_integrity_and_no_dangerous_privilege() -> None:
    from pickfit.verify.box import ExecResult
    from pickfit.verify.limits import _win_standard_user

    def token(**kw: str) -> ExecResult:
        t = {"admin": "False", "builtin": "S-1-5-32-545", "integrity": "S-1-16-8192",
             "privileges": "SeChangeNotifyPrivilege,SeShutdownPrivilege"} | kw
        return ExecResult(command="", exit_code=0, stdout="\n".join(f"{k}={v}" for k, v in t.items()) + "\n",
                          stderr="", seconds=0.1, timed_out=False, truncated=False)

    assert _win_standard_user(token())
    assert _win_standard_user(token(privileges="SeChangeNotifyPrivilege,SeShutdownPrivilege,SeUndockPrivilege,"
                                               "SeIncreaseWorkingSetPrivilege,SeTimeZonePrivilege"))
    for bad in ({"admin": "True"}, {"builtin": "S-1-5-32-545,S-1-5-32-551"}, {"builtin": "S-1-5-32-544,S-1-5-32-545"},
                {"integrity": "S-1-16-12288"}, {"privileges": "SeChangeNotifyPrivilege,SeBackupPrivilege"},
                {"privileges": "SeChangeNotifyPrivilege,SeTcbPrivilege"},
                {"privileges": "SeChangeNotifyPrivilege,SeManageVolumePrivilege"},
                {"privileges": "SeChangeNotifyPrivilege,SeRelabelPrivilege"},
                {"privileges": "SeShutdownPrivilege"},  # SeChangeNotify missing: the parse is suspect
                {"privileges": ""}):  # nothing parsed is a failure, not a pass
        assert not _win_standard_user(token(**bad)), bad


def test_encoded_command_probe_needs_a_readable_log_with_none_in_it() -> None:
    from pickfit.verify.box import ExecResult
    from pickfit.verify.limits import _no_encoded

    def out(text: str) -> ExecResult:
        return ExecResult(command="", exit_code=0, stdout=text, stderr="", seconds=0.1, timed_out=False,
                          truncated=False)

    assert _no_encoded(out("events=42 encoded=0"))
    assert not _no_encoded(out("events=42 encoded=1"))
    assert not _no_encoded(out("events=0 encoded=0"))  # an empty or unreadable log proves nothing


def test_unhardened_base_is_refused(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_UNHARDENED", "sbx is an administrator")
    with pytest.raises(BoxError, match="not hardened"):
        fake.box().start()
    assert fake.state()["pickfit-win11"]["VMState"] == "poweroff"


def test_router_with_other_rules_is_refused(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_RULES", "0000000000000000")
    with pytest.raises(BoxError, match="rule set"):
        fake.box().start()


def test_router_must_carry_the_hosts_public_addresses(fake, monkeypatch) -> None:
    monkeypatch.setattr(vb, "host_public_ipv4", lambda: ["203.0.113.9"])
    monkeypatch.setenv("FAKE_ROUTER_EXTRA", "none")
    with pytest.raises(BoxError, match="extra blocks"):
        fake.box().start()


@pytest.mark.parametrize("leak,value", [("HOSTLAN445", "refused"), ("GATEWAY80", "open"),
                                        ("VBOXNATHOST135", "refused"), ("METADATA", "open"),
                                        ("HOSTONLY445", "refused")])
def test_a_reached_host_or_lan_port_fails_closed(fake, monkeypatch, leak: str, value: str) -> None:
    monkeypatch.setenv(f"FAKE_REACH_{leak}", value)
    with pytest.raises(BoxError, match="containment check \\(online\\) failed"):
        fake.box().start()


@pytest.mark.parametrize("vm,nics", [("PICKFIT_WIN11", {"2": "bridged"}), ("PICKFIT_WIN11", {"1": "hostonly"}),
                                     ("PICKFIT_WIN11", {"1": "nat"}), ("PICKFIT_ROUTER", {"3": "bridged"}),
                                     ("PICKFIT_ROUTER", {"2": "hostonly"})])
def test_a_bridged_hostonly_or_extra_adapter_is_refused_before_boot(fake, monkeypatch, vm: str, nics: dict) -> None:
    monkeypatch.setenv(f"FAKE_NICS_{vm}", json.dumps(nics))
    with pytest.raises(BoxError, match="unexpected network adapters"):
        fake.box().start()
    assert not any(c[:2] == ["startvm", "pickfit-win11"] for c in fake.calls())


def test_an_internal_network_other_than_pickfits_is_refused(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_INTNET", "intnet")
    with pytest.raises(BoxError, match="intnet1=intnet"):
        fake.box().start()


@pytest.mark.parametrize("setting", [{"clipboard": "bidirectional"}, {"draganddrop": "hosttoguest"},
                                     {"vrde": "on"}, {"usb": "on"}, {"audio": "hda"}, {"uart1": "0x3f8,4"},
                                     {"accelerate3d": "on"}, {"SharedFolderNameMachineMapping1": "host"}])
def test_a_guest_with_a_host_channel_is_refused_before_boot(fake, monkeypatch, setting: dict) -> None:
    monkeypatch.setenv("FAKE_SETTINGS", json.dumps(setting))
    with pytest.raises(BoxError, match="host channels"):
        fake.box().start()
    assert not any(c[:2] == ["startvm", "pickfit-win11"] for c in fake.calls())


@pytest.mark.parametrize("key", ["vrde", "clipboard", "accelerate3d", "uart1"])
def test_a_setting_virtualbox_did_not_print_is_refused(fake, monkeypatch, key: str) -> None:
    monkeypatch.setenv("FAKE_DROP_KEY", key)
    with pytest.raises(BoxError, match=rf"{key}=\(not shown\)"):
        fake.box().start()


def test_clipboard_file_transfers_may_be_missing(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_DROP_KEY", "clipboard_file_transfers")  # absent where VirtualBox lacks the feature
    box = fake.box()
    box.start()
    box.close()


def test_a_timed_out_vboxmanage_does_not_carry_its_argv_into_the_traceback() -> None:
    import traceback

    slow = vb.VBox([sys.executable, "-c", "import time; time.sleep(30)"])
    secret = "s" + __import__("secrets").token_hex(12)  # built at run time: the traceback's source lines lack it
    try:
        slow("guestcontrol", "vm", "run", "--putenv", f"PF_SECRET={secret}", timeout_s=0.5)
    except BoxError:
        text = traceback.format_exc()
    else:
        pytest.fail("no timeout")
    assert "timed out" in text and secret not in text and "TimeoutExpired" not in text


def test_close_leaves_everything_in_place_when_the_owner_cannot_be_read(fake, monkeypatch) -> None:
    box = fake.box()
    box.start()
    monkeypatch.setenv("FAKE_EXTRADATA_FAIL", "1")
    box.close()
    st = fake.state()["pickfit-win11"]
    assert st["VMState"] == "running" and st["extra"]["pickfit/session"] == box.session
    assert not vb.HostLock(box._host_lock.path).acquire()  # the lock is still held
    monkeypatch.delenv("FAKE_EXTRADATA_FAIL")
    box.close()
    assert fake.state()["pickfit-win11"]["VMState"] == "poweroff"


def test_close_keeps_session_and_lock_when_the_vm_does_not_power_off(fake, monkeypatch) -> None:
    box = fake.box()
    box.start()

    def stuck(vm: str, wait_s: float = 60) -> None:
        raise BoxError(f"{vm} did not power off within {wait_s:.0f}s")

    monkeypatch.setattr(box.vbox, "poweroff", stuck)
    box.close()
    st = fake.state()["pickfit-win11"]
    assert st["VMState"] == "running" and st["extra"]["pickfit/session"] == box.session
    assert not vb.HostLock(box._host_lock.path).acquire()


def test_one_box_at_a_time_through_the_host_lock(fake) -> None:
    first = fake.box()
    first.start()
    second = fake.box()
    with pytest.raises(BoxError, match="lock"):
        second.start()
    assert fake.state()["pickfit-win11"]["extra"]["pickfit/session"] == first.session  # not overwritten
    first.close()
    second.start()  # free again once the first box has closed
    second.close()


def test_network_and_files_refuse_a_vm_that_is_no_longer_ours(fake) -> None:
    box = fake.box()
    box.start()
    box.vbox("setextradata", box.base, "pickfit/session", "someone-else")
    with pytest.raises(BoxError, match="no longer this box's"):
        box.write_file("x.txt", "x")
    with pytest.raises(BoxError, match="no longer this box's"):
        box.set_network(False)
    with pytest.raises(BoxError, match="no longer this box's"):
        box.validate_containment()
    box.vbox("setextradata", box.base, "pickfit/session", box.session)
    box.close()


def test_egress_lookup_never_goes_through_a_proxy(monkeypatch) -> None:
    seen: list[list[str]] = []

    def run(argv, **kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "ip=93.184.216.34\n", "")

    monkeypatch.setattr(vb.subprocess, "run", run)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    assert vb.host_egress_ipv4() == ["93.184.216.34"]
    argv = seen[0]
    assert argv[argv.index("--noproxy") + 1] == "*"


def test_password_scan_needs_its_canary_files_and_events() -> None:
    good = {"scanned": "543", "events": "27215", "canary_hits": "event:Windows PowerShell#12", "pw_hits": ""}
    assert vb.scan_ok(good)
    for bad in ({"scanned": "0"}, {"events": "0"}, {"canary_hits": ""}, {"canary_hits": "event:Security#3"},
                {"pw_hits": "C:\\Windows\\Panther\\unattend.xml"}):
        assert not vb.scan_ok(good | bad), bad
    assert not vb.scan_ok({k: v for k, v in good.items() if k != "pw_hits"})
    assert "$env:PF_CANARY" in vb.ADMIN_SECRET_SCAN


def test_the_networks_egress_address_is_blocked_and_probed(fake, monkeypatch) -> None:
    monkeypatch.setattr(vb, "host_egress_ipv4", lambda: ["198.51.200.7"])
    monkeypatch.setenv("FAKE_ROUTER_EXTRA", "198.51.200.7")
    box = fake.box()
    box.start()
    assert box.extra == ["198.51.200.7"]
    assert {f"wan198_51_200_7_{p}" for p in (80, 443, 445)} <= set(box.probe_targets())
    serial = fake.state()["pickfit-router"]["extra"]["VBoxInternal/Devices/pcbios/0/Config/DmiSystemSerial"]
    assert serial == "pf:198.51.200.7"
    box.close()


def test_egress_address_comes_from_the_trace_and_fails_closed(monkeypatch) -> None:
    def fake_run(out: str):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, out, "")

    monkeypatch.setattr(vb.subprocess, "run", fake_run("fl=1\nip=93.184.216.34\nts=1\n"))
    assert vb.host_egress_ipv4() == ["93.184.216.34"]
    monkeypatch.setattr(vb.subprocess, "run", fake_run("ip=10.1.2.3\n"))
    assert vb.host_egress_ipv4() == []  # already in a blocked range
    monkeypatch.setattr(vb.subprocess, "run", fake_run("<html>captive portal</html>"))
    with pytest.raises(BoxError, match="public address"):
        vb.host_egress_ipv4()


def test_a_refused_start_leaves_the_other_boxs_vm_alone(fake) -> None:
    other = fake.box()
    other.start()
    with pytest.raises(BoxError, match="already running for another box"):
        fake.box().start()
    st = fake.state()["pickfit-win11"]
    assert st["VMState"] == "running" and st["extra"]["pickfit/session"] == other.session
    other.close()


def test_a_box_that_lost_its_vm_neither_runs_commands_nor_tears_it_down(fake) -> None:
    box = fake.box()
    box.start()
    box.vbox("setextradata", box.base, "pickfit/session", "someone-else")
    with pytest.raises(BoxError, match="no longer this box's"):
        box.exec("Get-Location", 30)
    restored = fake.state()["pickfit-win11"]["restored"]
    box.close()
    st = fake.state()["pickfit-win11"]
    assert st["VMState"] == "running" and st["restored"] == restored


def test_guest_text_that_looks_like_a_vboxmanage_error_is_just_output(fake) -> None:
    box = fake.box()
    box.start()
    result = box.exec("Write-Error 'VBoxManage.exe: error: fake'; cmd /c exit 3", 30)
    assert result.exit_code == 3  # no BoxError: the VM is still running, so this is the command's own output
    box.close()


def test_an_old_ready_line_never_counts_for_a_new_boot(fake, monkeypatch) -> None:
    box = fake.box()
    box.start()
    box.close()
    serial = Path(fake.dir / "state" / "logs" / "pickfit-router-serial.log")
    old = serial.read_text()
    assert "PICKFIT_ROUTER_READY" in old
    monkeypatch.setenv("FAKE_ROUTER_SILENT", "1")  # this boot never reports
    monkeypatch.setattr(vb, "ROUTER_WAIT_S", 0.5)
    with pytest.raises(BoxError, match="did not report ready"):
        fake.box().start()


def test_a_ready_line_rewritten_in_place_is_still_seen(fake, monkeypatch) -> None:
    box = fake.box()
    box.start()
    box.close()
    monkeypatch.setenv("FAKE_ROUTER_OVERWRITE", "1")  # same length, same place: the old size-based read missed it
    monkeypatch.setattr(vb, "ROUTER_WAIT_S", 2)
    again = fake.box()
    again.start()
    again.close()


def test_router_hashes_its_whole_rule_set_before_the_box_adds_anything() -> None:
    start = vb.ROUTER_START
    assert "sed '/elements" not in start
    assert start.index("sum=$(nft -s list table inet pf | sha256sum") < start.index("nft add element")


def test_probe_that_sees_nothing_open_fails(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_REACH_ROUTERDNS", "timeout")  # a no-op probe would also say timeout everywhere
    with pytest.raises(BoxError, match="router DNS port"):
        fake.box().start()


def test_network_cut_detaches_the_nic_and_is_checked_both_ways(fake) -> None:
    box = fake.box()
    box.start()
    box.set_network(False)
    assert fake.state()["pickfit-win11"]["nic1"] == "null" and fake.state()["pickfit-win11"]["link"] == "off"
    assert box.network_enabled is False
    box.set_network(True)
    assert fake.state()["pickfit-win11"]["nic1"] == "intnet" and box.network_enabled
    box.close()


def test_offline_leak_is_caught(fake, monkeypatch) -> None:
    box = fake.box()
    box.start()
    monkeypatch.setenv("FAKE_OFFLINE_LEAK", "1")
    with pytest.raises(BoxError, match="offline"):
        box.set_network(False)
    box.close()


# -- commands


@pytest.mark.parametrize("code", [0, 1, 3, 93, 94, 1603])
def test_exit_code_survives_vboxmanage(fake, code: int) -> None:
    box = fake.box()
    box.start()
    result = box.exec(f"cmd /c exit {code}", 30)
    assert result.exit_code == code and "__PF_RC_" not in result.stdout
    box.close()


def test_command_printing_a_fake_sentinel_does_not_change_the_code(fake) -> None:
    box = fake.box()
    box.start()
    assert box.exec("FAKE_LIES", 30).exit_code == 7
    late = box.exec("FAKE_GRANDCHILD", 30)
    assert late.exit_code == 1 and "not trusted" in late.stderr
    box.close()


def test_model_commands_run_as_sbx_and_harness_as_administrator(fake) -> None:
    box = fake.box()
    box.start()
    assert box.exec("Get-Location", 30).stdout.strip() == "ran as sbx"
    users = {c[c.index("--username") + 1] for c in fake.calls() if c[:1] == ["guestcontrol"] and "run" in c}
    assert users == {"sbx", "Administrator"}
    box.close()


def test_files_go_in_by_copy_and_come_back_capped(fake) -> None:
    box = fake.box()
    box.start()
    box.write_file("README.md", "# hi")
    assert (fake.dir / "copied.bin").read_bytes() == b"# hi"
    copy = next(c for c in fake.calls() if c[2:3] == ["copyto"])
    assert copy[-1] == r"C:\Users\sbx\work\README.md" and copy[copy.index("--username") + 1] == "sbx"
    assert box.read_file("README.md", 5) == b"hello"
    box.close()


def test_exec_before_start_is_refused(fake) -> None:
    with pytest.raises(BoxError, match="not started"):
        fake.box().exec("whoami", 5)


def test_background_is_powershell_and_waits_for_the_port() -> None:
    box = VBoxBox.__new__(VBoxBox)
    script = box.background("python -m http.server 8000", 8000, 20, 3)
    assert "Start-Process" in script and "Connect('127.0.0.1', 8000)" in script and "exit 1" in script
    assert "setsid" not in script and "nohup" not in script


# -- agent integration


def test_agent_tools_and_task_name_powershell(fake) -> None:
    box = fake.box()
    box.manifest = {"windows": "26H2 (build 28000.1)", "pwsh": "7.5.4", "python": "3.12.10"}
    run_command = next(t for t in tools_for(box) if t["name"] == "run_command")
    assert "pwsh (PowerShell 7) command" in run_command["description"] and "bash" not in run_command["description"]
    task = load_fixture(FIXTURES / "evnx.json")
    text = render_task(task, plan_for(task.extraction, "windows"), box, AgentLimits())
    assert "Windows 11 Enterprise" in text and "PowerShell 7" in text and "standard user" in text


def test_windows_runs_check_features_under_the_same_rules(fake) -> None:
    """tools_for rewrites run_command for pwsh and leaves finish as it is, features included, and the task
    lists the README's features with the same guide, so a Windows run records coverage like any other."""
    import dataclasses

    from pickfit.schema import Cited
    from pickfit.verify.agent import FINISH_TOOL

    box = fake.box()
    box.manifest = {"windows": "26H2 (build 28000.1)", "pwsh": "7.5.4", "python": "3.12.10"}
    finish = next(t for t in tools_for(box) if t["name"] == "finish")
    assert finish == FINISH_TOOL and "features" in finish["parameters"]["required"]
    task = load_fixture(FIXTURES / "evnx.json")
    ex = task.extraction.model_copy(update={"features": [Cited(value="validate .env files", quote="Validate .env")]})
    text = render_task(dataclasses.replace(task, extraction=ex), plan_for(ex, "windows"), box, AgentLimits())
    assert 'F1. validate .env files (README: "Validate .env")' in text and "Feature checks:" in text


def test_windows_plan_keeps_brew_aside() -> None:
    from pickfit.schema import InstallClaim

    plan = vb_plan([InstallClaim(method="brew", command="brew install x", platforms=[]),
                    InstallClaim(method="npm", command="npm install -g x", platforms=[])])
    assert [c.method for c in plan.candidates] == ["npm"]
    assert plan.skipped[0].method == "brew"


def vb_plan(claims):
    from pickfit.verify.plan import rank_install_methods

    return rank_install_methods(claims, "windows")


def test_needs_store_is_a_reason_the_agent_can_give_and_the_record_keeps() -> None:
    from typing import get_args

    from pickfit.schema import UnverifiedReason
    from pickfit.verify.agent import FINISH_TOOL, FinishArgs
    from pickfit.verify.failure import WRITTEN_REASONS

    assert "needs_store" in get_args(UnverifiedReason.__value__)
    enum = FINISH_TOOL["parameters"]["properties"]["unverified_reason"]
    assert "needs_store" in json.dumps(enum)
    assert FinishArgs.model_validate({"level": "unverified", "unverified_reason": "needs_store"}).unverified_reason \
        == "needs_store"
    assert "needs_store" in WRITTEN_REASONS  # it says something about the software on Windows
    assert "reason needs_store" in VBoxBox.user_rule and "do not switch to another source" in VBoxBox.user_rule
    schema = json.loads((Path(__file__).parents[1] / "schema" / "software.v1.json").read_text(encoding="utf-8"))
    assert "needs_store" in schema["$defs"]["UnverifiedReason"]["enum"]


def test_hardened_check_covers_the_ways_to_admin() -> None:
    for needle in ("Get-LocalGroup)", "-ne 'S-1-5-32-545'", "cannot list the members", "EnableLUA", "AutoAdminLogon",
                   "pwsh.path",
                   "DefaultUserName -ne 'sbx'", "DefaultPassword", "HKEY_USERS", "[PfLsa]::Probe('DefaultPassword')",
                   "Panther\\Unattend", "autounattend.xml", "Win32_CDROMDrive", "fDenyTSConnections", "WinRM",
                   "pickfit\\run.ps1"):
        assert needle in HARDENED_CHECK


def test_router_rules_drop_every_private_range_and_keep_dns_local() -> None:
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10",
                "127.0.0.0/8", "224.0.0.0/4", "240.0.0.0/4"):
        assert net in vb.ROUTER_NFT
    assert "policy drop" in vb.ROUTER_NFT and f"ip daddr {ROUTER_IP} udp dport 53 accept" in vb.ROUTER_NFT
    assert "stop-dns-rebind" in vb.ROUTER_CONFIG and "disable_ipv6 = 1" in vb.ROUTER_CONFIG
    assert "\t" not in vb.ROUTER_CONFIG  # typed into a console, where a tab would complete
