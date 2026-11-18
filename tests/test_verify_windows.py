"""The Windows box over SSH (win_machine.py, windows_box.py) and its EC2 half (ec2_windows.py), against a fake
EC2 API and a fake ssh that reads the scripts the harness sends. Nothing leaves the process."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
from test_verify_ec2 import CONTROL, AwsError, Clock, FakeEc2

from pickfit.verify import ec2_machine as e
from pickfit.verify import ec2_windows as ew
from pickfit.verify import gui_win, vnc
from pickfit.verify import ssh_machine as s
from pickfit.verify import vbox_box as vb
from pickfit.verify import win_machine as wm
from pickfit.verify import windows_box as wb
from pickfit.verify.box import BoxError, BoxLimits

PASSWORD = "Pf1-made-on-the-instance"
BASE = {"ImageId": "ami-win-base", "Name": "Windows_Server-2025-English-Full-Base-2026.11.11", "State": "available",
        "RootDeviceName": "/dev/sda1", "CreationDate": "2026-11-11"}
TOOLS = "pwsh=7.7.0;python=3.12.10;uv=0.13.8;pipx=1.18.16;node=v26.13.1;npm=11.20.0;git=2.56.0.windows.4;winget=v1.29.380"
BAKED = {"ImageId": "ami-win", "Name": ew.win_image_name(), "State": "available", "RootDeviceName": "/dev/sda1",
         "Tags": [{"Key": "pickfit:product", "Value": "Windows Server 2025 Datacenter"},
                  {"Key": "pickfit:windows", "Value": "24H2 (build 26100.33822)"},
                  {"Key": "pickfit:tools", "Value": TOOLS}]}


class WinEc2(FakeEc2):
    """The fake EC2 with Amazon's Windows image and tags kept on images made here."""

    def __init__(self, images: list[dict[str, Any]] | None = None) -> None:
        super().__init__(images if images is not None else [BAKED])

    def describe_images(self, **kw: Any) -> dict[str, Any]:
        self._call("describe_images", kw)
        names = next((f["Values"] for f in kw.get("Filters", []) if f["Name"] == "name"), None)
        ids = kw.get("ImageIds")
        base = kw.get("Owners") == [ew.WIN_BASE_OWNER]
        return {"Images": [i for i in self.images if (ids is None or i["ImageId"] in ids)
                           and (i["ImageId"] == "ami-win-base") == base
                           and (base or names is None or i["Name"] in names)]}

    def create_image(self, **kw: Any) -> dict[str, Any]:
        self._call("create_image", kw)
        tags = next(t["Tags"] for t in kw["TagSpecifications"] if t["ResourceType"] == "image")
        self.images.append({"ImageId": "ami-baked", "Name": kw["Name"], "State": "available",
                            "RootDeviceName": "/dev/sda1", "Tags": tags})
        return {"ImageId": "ami-baked"}


class Stdin:
    def __init__(self, done: threading.Event) -> None:
        self.data, self.closed, self.done = b"", False, done

    def write(self, data: bytes) -> None:
        self.data += data

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self.done.set()


class Late:
    """A stream whose content is known only once the command's stdin was closed."""

    def __init__(self, done: threading.Event, content: Any) -> None:
        self.done, self.content, self.sent = done, content, False

    def read1(self, n: int) -> bytes:
        self.done.wait(5)
        if self.sent:
            return b""
        self.sent = True
        return self.content()


SBX_SID = "S-1-5-21-1-2-3-1000"


class FakeWindows:
    """The local ssh and ssh-keygen, and behind them a Windows that answers the harness's scripts: the machine's
    own (boot check, rules, the logon secret, probes) and the box's (the administrator's through run.ps1 with
    the command in $env:PF_ENC; the box user's through relay.exe, which hands the command to job.exe)."""

    def __init__(self, ec2: FakeEc2) -> None:
        self.ec2 = ec2
        self.local: list[tuple[list[str], dict[str, Any]]] = []
        self.scripts: list[tuple[str, str]] = []  # (user, the script as the machine ran it), in order
        self.commands: list[tuple[str, str]] = []  # (user, the command run.ps1 or job.exe was given)
        self.jobs: list[dict[str, str]] = []  # what each relay read to send down its pipe, decoded
        self.job_check, self.desk = "job-ok", True  # the image's task as the start finds it; whether it starts
        self.lines: list[str] = []  # the remote command line of every command
        self.offline_rules = 0
        self.armed, self.script_left, self.console = True, 0, True
        self.replies: dict[str, tuple[int, str]] = {}  # a word in a command or script -> (exit code, stdout)
        self.reached: dict[tuple[str, str], str] = {}  # (user, probe target) -> what the probe sees there
        self.files: dict[str, bytes] = {}

    # -- local

    def run(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.local.append((list(argv), kw))
        if argv[0] == s.SSH_KEYGEN:
            path = Path(argv[argv.index("-f") + 1])
            path.write_text(f"-----PRIVATE {path.name}-----\n")
            Path(f"{path}.pub").write_text(f"ssh-ed25519 PUBLIC{path.name} pickfit\n")
        elif "ControlMaster=yes" in argv:
            Path(next(a for a in argv if a.startswith("ControlPath=")).split("=", 1)[1]).write_text("")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def popen(self, argv: list[str], **kw: Any) -> Any:
        user = argv[-3].split("@")[0]
        self.lines.append(argv[-1])
        done = threading.Event()
        fake = self
        result: dict[str, Any] = {}

        def answer() -> None:
            if "code" not in result and argv[-1] == wb.RELAY_EXE:  # a program of the image's: its stdin is its own
                result["code"], result["out"] = fake.relay(user, proc.stdin.data.decode())
            elif "code" not in result and argv[-1] != wm.PS_STDIN:
                result["code"], result["out"] = 0, proc.stdin.data.decode()
            if "code" not in result:
                line = proc.stdin.data.decode()
                script = base64.b64decode(re.search(r"FromBase64String\('([^']*)'\)", line).group(1)).decode()
                assert script.startswith(wm.PRELUDE) and line.endswith("\n") and line.count("\n") == 1
                result["code"], result["out"] = fake.reply(user, script[len(wm.PRELUDE):])

        class Proc:
            stdin = Stdin(done)

            def __init__(self) -> None:
                self.stdout = Late(done, lambda: (answer(), result["out"].encode())[1])
                self.stderr = Late(done, lambda: b"")

            def wait(self) -> int:
                done.wait(5)
                answer()
                return result["code"]

            def poll(self) -> int | None:
                return result.get("code")

            def kill(self) -> None:
                pass

        proc = Proc()
        return proc

    # -- the machine

    def online(self) -> bool:
        groups = {g["GroupId"] for g in self.ec2.groups.values() if g["GroupName"] == e.GROUPS["online"]}
        instance = next(i for i in self.ec2.instances.values() if i["State"]["Name"] == "running")
        return bool(set(instance["Groups"]) & groups)

    def probe(self, user: str, command: str) -> str:
        targets = dict(pair.split("=", 1) for pair in re.search(r"-Targets '([^']*)'", command).group(1).split(","))
        box_user_cut = user == wm.BOX_USER and self.offline_rules > 0
        lines = []
        for name, target in targets.items():
            if (user, name) in self.reached:
                seen = self.reached[(user, name)]
            elif target.startswith("169.254."):
                seen = "unreachable:AccessDenied" if user == wm.BOX_USER else "open"
            elif target.startswith("10."):
                seen = "timeout"
            else:
                seen = "open" if self.online() and not box_user_cut else "timeout"
            lines.append(f"probe {name}={seen}")
        if "-Url" in command:
            lines.append(f"probe public=curl{0 if self.online() and not box_user_cut else 7}")
        if "-Dns" in command:
            lines.append(f"probe dns={'resolved' if self.offline_rules == 0 and self.online() else 'failed'}")
        return "\n".join(lines) + "\n"

    def answer(self, user: str, command: str) -> tuple[int, str]:
        """What a command of the box's says and exits with."""
        self.commands.append((user, command))
        code, out = next((r for word, r in self.replies.items() if word in command), (0, ""))
        if command.endswith(vb.HARDENED_CHECK):
            out = "hardened\n"
        elif "setup-ok" in command:
            out = (f"setup-ok\nsid={SBX_SID}\n{self.job_check}\n" + ("console-logon\n" if self.console else ""))
        elif wb.PROBE_PS1 in command:
            out = self.probe(user, command)
        elif ".held" in command and "Test-Path" in command:
            out = "held\n"
        elif ".go" in command:
            out = "nothing\n" if self.offline_rules else "answered 256\n"
        elif "PFB64" in command:
            path = re.search(r"OpenRead\('([^']*)'\)", command).group(1)
            most = int(re.search(r"New-Object byte\[\] (\d+)", command).group(1))
            out = "PFB64:" + base64.b64encode(self.files.get(path, b"")[:most]).decode()
        return code, out

    @staticmethod
    def unwrap(enc: str) -> str:
        """The command inside with_exit_code, from $env:PF_ENC."""
        return base64.b64decode(enc).decode("utf-16-le").split("\n", 1)[1].rsplit("\n$__pf_ok = $?", 1)[0]

    def run_ps1(self, user: str, script: str) -> tuple[int, str]:
        nonce = re.search(r"-Nonce (\w+)", script).group(1)
        code, out = self.answer(user, self.unwrap(re.search(r"\$env:PF_ENC = '([^']*)'", script).group(1)))
        return code & 0xFF, f"{out}\n{vb.SENTINEL}{nonce}={code}\n"

    def relay(self, user: str, sent: str) -> tuple[int, str]:
        """relay.exe as sbx: job.exe takes what it reads and the relay ends with the exit code that comes back."""
        self.scripts.append((user, sent))
        if not self.desk:
            return wb.NOT_STARTED_EXIT, ""
        lines = sent.split("\n")
        assert lines[0].startswith("nonce=") and lines[-2:] == ["go", ""]
        job = {name: base64.b64decode(value).decode() for name, value in (line.split("=", 1) for line in lines[1:-2])}
        self.jobs.append(job)
        code, out = self.answer(user, self.unwrap(job["enc"]))
        return code & 0xFF, f"{out}\n{vb.SENTINEL}{lines[0][len('nonce='):]}={code}\n"

    def reply(self, user: str, script: str) -> tuple[int, str]:
        self.scripts.append((user, script))
        if f"& '{wb.RUN_PS1}' -Timeout" in script:
            return self.run_ps1(user, script)
        for word, (code, out) in self.replies.items():
            if word in script:
                return code, out
        if "scripts=$(" in script:
            return 0, f"shutdown={1190 if self.armed else 0}\nscripts={self.script_left}\n"
        if script.startswith("Enable-NetFirewallRule"):
            self.offline_rules = 3
        elif script.startswith("Disable-NetFirewallRule"):
            self.offline_rules = 0
        if "offline_rules=$on" in script:
            return 0, f"offline_rules={self.offline_rules} guard=1\n"
        if "PfLsaRead" in script:
            return 0, "PFPW:" + base64.b64encode(PASSWORD.encode()).decode() + "\n"
        if script == wm.EGRESS_PROBE:
            return 0, "open\nopen\n" if self.online() else ""
        if script == ew.IMDS_PROBE:
            return 0, "HTTP/1.1 200" if self.ec2.imds == "enabled" else "HTTP/1.1 403"
        if "WriteAllBytes" in script or "'Append'" in script:
            path = re.search(r"\[IO\.File\]::(?:WriteAllBytes|Open)\('([^']*)'", script).group(1)
            data = base64.b64decode(re.search(r"FromBase64String\('([^']*)'\)", script).group(1))
            self.files[path] = (self.files.get(path, b"") if "'Append'" in script else b"") + data
            return 0, "written\n"
        return 0, ""


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "0")
    clock = Clock()
    for module in (e, s):
        monkeypatch.setattr(module, "_now", clock.now)
        monkeypatch.setattr(module, "_sleep", clock.sleep)
    monkeypatch.setattr(ew, "_sleep", clock.sleep)


def machine(ec2: FakeEc2 | None = None, **kw: Any) -> tuple[ew.Ec2WinMachine, FakeEc2, FakeWindows]:
    ec2 = ec2 or WinEc2()
    win = FakeWindows(ec2)
    made = ew.Ec2WinMachine(**{"lifetime_s": 1200, "ec2": ec2, "control": CONTROL, "popen": win.popen,
                               "run": win.run, "log": lambda line: None, **kw})
    return made, ec2, win


def box(**kw: Any) -> tuple[ew.Ec2WindowsBox, FakeEc2, FakeWindows]:
    ec2 = WinEc2()
    win = FakeWindows(ec2)
    made = ew.Ec2WindowsBox(ec2=ec2, control=CONTROL, log=lambda line: None, **kw)
    made.machine.popen, made.machine.run_local = win.popen, win.run
    return made, ec2, win


# -- the machine over SSH


def test_the_boot_script_arms_the_shutdown_first_starts_sshd_last_and_deletes_itself():
    m, ec2, _ = machine()
    m.start()
    data = next(k for n, k in ec2.calls if n == "run_instances")["UserData"]
    assert data.startswith("<powershell>\n") and data.rstrip().endswith("</powershell>")
    lines = [line for line in data.splitlines() if line.strip()]
    assert lines[2].startswith("shutdown.exe /s /f /t 1200 ")  # after the tag and the error preference
    assert lines[-3] == "Start-Service sshd" and "Remove-Item -LiteralPath $PSCommandPath" in lines[-2]
    host = base64.b64encode(b"-----PRIVATE host-----\n").decode()
    login = base64.b64encode(b"ssh-ed25519 PUBLIClogin pickfit\n").decode()
    assert f"ssh_host_ed25519_key\", [Convert]::FromBase64String('{host}')" in data
    assert f"administrators_authorized_keys\", [Convert]::FromBase64String('{login}')" in data
    assert "sbx" not in data  # the box user gets no key: it logs in with its password


def test_a_machine_whose_shutdown_is_not_armed_or_whose_boot_script_is_left_does_not_start():
    m, ec2, win = machine()
    win.armed = False
    with pytest.raises(BoxError, match="not armed"):
        m.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    m2, ec2, win = machine()
    win.script_left = 1
    with pytest.raises(BoxError, match="host key"):
        m2.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_no_script_is_ever_on_a_command_line():
    m, _, win = machine()
    m.start()
    m.admin("'a secret thing'", 30)
    assert set(win.lines) == {wm.PS_STDIN} and "EncodedCommand" not in wm.PS_STDIN
    assert win.scripts[-1] == (wm.ADMIN_USER, "'a secret thing'")
    code, out, _, _ = m.run_exe(wm.ADMIN_USER, r"C:\Windows\System32\findstr.exe", b"what it is to do", 30)
    assert (code, out) == (0, "what it is to do") and win.lines[-1].endswith("findstr.exe")  # a program gets its work on stdin too
    line = wm.ps_line("line one\nline two").decode()
    assert line.count("\n") == 1 and "line one" not in line and line.startswith("Invoke-Expression (")


def test_the_administrator_logs_in_with_the_key_and_the_box_user_with_its_password():
    m, _, win = machine()
    m.start()
    masters = [(argv, kw) for argv, kw in win.local if "ControlMaster=yes" in argv]
    admin, sbx = masters[0], masters[-1]
    assert admin[0][-1] == "Administrator@198.51.100.9" and "-i" in admin[0] and "BatchMode=yes" in admin[0]
    assert sbx[0][-1] == "sbx@198.51.100.9" and "PreferredAuthentications=password" in sbx[0]
    assert "PubkeyAuthentication=no" in sbx[0] and "-i" not in sbx[0]
    assert PASSWORD not in " ".join(sbx[0])  # in the one process's environment, never an argument
    assert sbx[1]["env"]["PF_SSH_PASS"] == PASSWORD and sbx[1]["env"]["SSH_ASKPASS_REQUIRE"] == "force"
    assert Path(sbx[1]["env"]["SSH_ASKPASS"]).read_text() == wm.ASKPASS
    assert next(i for i, (user, script) in enumerate(win.scripts) if "PfLsaRead" in script) > 0  # read as the administrator
    assert {user for user, script in win.scripts} == {wm.ADMIN_USER}
    assert "StrictHostKeyChecking=yes" in sbx[0] and any(a.startswith("UserKnownHostsFile=") for a in sbx[0])
    keys = m.keys_dir
    m.close()
    assert m._box_password is None and not keys.exists()


def test_the_metadata_service_is_off_and_the_rules_are_as_the_image_made_them_before_the_box_user_logs_in():
    m, ec2, win = machine()
    m.start()
    assert ("modify_instance_metadata_options", {"InstanceId": "i-1", "HttpEndpoint": "disabled"}) in ec2.calls
    order = [script for _, script in win.scripts]
    assert order.index(ew.IMDS_PROBE) < order.index(wm.RULE_STATE) < order.index(wm.LSA_READ)
    assert m.metadata_answer == "HTTP/1.1 403"
    m2, ec2, win = machine()
    win.offline_rules = 3  # an image whose offline rules are on would start a box offline
    with pytest.raises(BoxError, match="firewall rules"):
        m2.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_the_cut_ends_the_box_users_connections_on_the_machine_then_closes_the_security_group():
    m, ec2, win = machine()
    m.start()
    before = len(win.scripts)
    ec2.calls.clear()
    m.set_egress(False)
    ran = [script for _, script in win.scripts[before:]]
    assert ran[0] == wm.CUT_ON and ran[-1] == wm.EGRESS_PROBE  # the rules first, then the administrator sees it closed
    offline = next(g["GroupId"] for g in ec2.groups.values() if g["GroupName"] == e.GROUPS["offline"])
    assert ec2.calls[0][0] == "modify_instance_attribute" and ec2.calls[0][1]["Groups"][1] == offline
    assert "Clear-DnsClientCache" in wm.CUT_ON and wm.CUT_RULE in wm.CUT_ON and all(r in wm.CUT_ON for r in wm.DNS_RULES)
    before = len(win.scripts)
    m.set_egress(True)
    ran = [script for _, script in win.scripts[before:]]
    assert ran[0] == wm.EGRESS_PROBE and ran[-1] == wm.CUT_OFF  # open outside first
    assert "LocalUser" in wm.MAKE_RULES and "169.254.0.0/16" in wm.MAKE_RULES and "-RemotePort 53" in wm.MAKE_RULES
    win.replies["Enable-NetFirewallRule"] = (0, "offline_rules=1 guard=1\n")  # a rule that did not switch on
    with pytest.raises(BoxError, match="offline rules"):
        m.set_egress(False)


def test_a_command_the_host_gives_up_on_reports_no_exit_code(monkeypatch):
    m, _, win = machine()
    m.start()

    class Hung:
        killed = True
        stdout, stderr = [b"partial"], []

        def wait(self) -> int:
            return 124

    monkeypatch.setattr(m, "spawn", lambda user, script, timeout_s: Hung())
    assert m.run_ps(wm.ADMIN_USER, "Start-Sleep 99", 1)[:2] == (None, "partial")


# -- the box


def test_a_box_users_command_runs_at_its_desktop_and_the_ssh_side_only_relays():
    b, _, win = box(tags={"pickfit.run": "r1"}, limits=BoxLimits(lifetime_s=900))
    assert b.runner == "ec2-windows" and b.os == "windows" and b.shell == "pwsh"
    b.start()
    win.replies["Get-Thing"] = (0, "a thing\n")
    result = b.exec("Get-Thing -Name 'x'", 20, cwd=r"C:\Users\sbx\it's here")
    assert result.ok and result.stdout == "a thing\n"
    user, sent = win.scripts[-1]
    assert user == "sbx" and win.commands[-1] == ("sbx", "Get-Thing -Name 'x'")
    job = win.jobs[-1]
    assert job["cwd"] == r"C:\Users\sbx\it's here" and job["timeout"] == "20"
    assert job["env:CI"] == "1" and job["env:PYTHONIOENCODING"] == "utf-8" and len(job["id"]) == 16
    # sshd starts the relay by its path, the same line every time; the command is on its stdin, in base64, and
    # none of it is on a command line or in a file
    assert win.lines[-1] == wb.RELAY_EXE and set(win.lines) == {wm.PS_STDIN, wb.RELAY_EXE}
    assert "Get-Thing" not in sent and sent.startswith("nonce=") and sent.endswith("\ngo\n")
    assert b.job_input("x", 5, "C:\\", "aa", "bb") == wb.relay_input("x", 5, "C:\\", "aa", "bb")
    relay = wb.RELAY_SOURCE
    # the relay takes a job.exe that waits; only when none does it ask the Task Scheduler for one
    assert relay.index("c.Connect(1)") < relay.index("StartJob(); asked = true")
    assert f"long until = {wb.JOB_FIRST_MS};" in relay and f"until = {wb.JOB_START_S}000;" in relay
    assert "po.CopyToAsync(stdout" in relay and "pe.CopyToAsync(stderr" in relay
    assert f"return {wb.NOT_STARTED_EXIT};" in relay and relay.rstrip().endswith("return rc; }\n}")
    assert f'Say(stdout, "\\n{vb.SENTINEL}" + nonce + "=" + rc)' in relay
    # its stdin, stdout and stderr are the handles sshd gave it: through .NET's Console one start in six lost stdin
    assert "Console." not in relay and relay.count("Std(-1") == 3
    code, _, _ = b._admin("'checked'", 30)  # the administrator's go straight over SSH, through run.ps1
    assert code == 0 and win.scripts[-1][0] == "Administrator" and "-Shell powershell" in win.scripts[-1][1]
    assert f"-Cwd '{wb.HARNESS_DIR}'" in win.scripts[-1][1]  # where sbx cannot plant a file
    assert f"& '{wb.RUN_PS1}' -Timeout 30" in win.scripts[-1][1] and win.lines[-1] == wm.PS_STDIN


def test_job_exe_waits_for_one_command_with_its_shell_started_and_starts_the_next():
    job = wb.JOB_SOURCE
    assert (f'NamedPipeServerStream("{wb.JOB_PIPE}", PipeDirection.InOut, 254, PipeTransmissionMode.Byte, '
            "PipeOptions.Asynchronous") in job
    assert f".Wait({wb.JOB_IDLE_S}000)) {{ EndTree(p); return 0; }}" in job  # one nobody came for ends, with its shell
    # the shell starts at once, with the environment Windows gives a new process of this user now; if that has
    # changed by the time the command comes, or the shell is gone, the job says so and is not used
    assert job.index("var env = FreshEnv()") < job.index("Process.Start(psi)") < job.index("WaitForConnectionAsync().Wait(")
    assert "CreateEnvironmentBlock(out env, me.Token, false)" in job and "psi.Environment[pair.Key] = pair.Value" in job
    assert (job.index("Flat(FreshEnv()) != made") < job.index('Tell(writer, ctl, "stale")')
            < job.index('writer.Write("ready\\n")') < job.index("reader.ReadLine()"))
    assert '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \\"' + wb.JOB_BOOT + '\\""' in job
    assert "p.StandardInput.Close()" in job and "pwsh.path" in job  # an empty stdin; PowerShell 7
    assert "psi.CreateNoWindow = true" in job  # nothing of pickfit's shows on the box user's desktop
    assert "rc = 137" in job and job.count("EndTree(p); rc = ") == 2 and "gone.IsCompleted" in job  # timeout; relay gone
    assert '"taskkill.exe", "/T /F /PID " + p.Id' in job
    # the exit code goes back before the next job.exe is asked for: that one starts after all this command did
    assert job.index('Tell(writer, ctl, "rc=" + rc)') < job.rindex("StartJob()")
    assert job.count("PipeOptions.Asynchronous") == 4 and "catch (Exception) { return 1; }" in job
    boot = wb.JOB_BOOT  # what the shell runs first: one argument of a command line
    assert '"' not in boot and boot.startswith("[Console]::OutputEncoding=")
    assert boot.index("Remove-Item env:PF_BOOT") < boot.index("ReadLine()") < boot.index("Invoke-Expression $__pf")
    assert "Set-Location -LiteralPath $__pf_v" in boot and "exit 127" in boot and "Remove-Variable __pf_c" in boot
    xml = wb.JOB_TASK_XML
    assert "<LogonType>InteractiveToken</LogonType>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert "<MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<Priority>4</Priority>" in xml and xml.rstrip().endswith("</Task>")
    assert f"<Command>{wb.JOB_EXE}</Command>" in xml and "<Arguments>" not in xml
    made = wb.make_job()
    for part in (job, wb.RELAY_SOURCE, xml):
        assert base64.b64encode(part.encode()).decode() in made
    assert "'WindowsApplication'" in made and "'ConsoleApplication'" in made and "-ReferencedAssemblies System.Core" in made
    assert '"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;$sid)"' in made and "icacls.exe" in made  # read and run, no more
    assert "the task's access is" in wb.JOB_CHECK and "can change $(Split-Path -Leaf $f)" in wb.JOB_CHECK
    assert wb.JOB_EXE in wb.JOB_CHECK and wb.RELAY_EXE in wb.JOB_CHECK and "$exec.Command -ne" in wb.JOB_CHECK


def test_the_exit_code_is_the_one_the_last_line_carries_only_when_ssh_agrees():
    b, _, win = box()
    b.start()
    for code in (0, 1, 3, 93, 94, 1603):
        win.replies["cmd /c exit"] = (code, "")
        assert b.exec(f"cmd /c exit {code}", 30).exit_code == code
    assert wb.read_sentinel(f"out\r\n\r\n{vb.SENTINEL}ab=1603\r\n", "ab", 1603 & 0xFF) == ("out\r\n", 1603, None)
    forged = wb.read_sentinel(f"{vb.SENTINEL}ab=0\n", "ab", 1)  # the box printed a 0; the session ended with 1
    assert forged[1] is None and "not trusted" in forged[2]
    assert wb.read_sentinel("no line at all", "ab", 0) == ("no line at all", None, None)
    win.replies["forge"] = (1, f"{vb.SENTINEL}0000=0\n")  # another nonce's line changes nothing
    assert b.exec("forge", 30).exit_code == 1


def test_a_start_fails_closed_when_the_box_user_reaches_what_it_must_not():
    b, ec2, win = box()
    win.reached[("sbx", "metadata")] = "open"
    with pytest.raises(BoxError, match="metadata open"):
        b.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated" and not b.started
    b2, ec2, win = box()
    win.replies[vb.HARDENED_CHECK[-40:]] = (1, "sbx is in Administrators\n")
    with pytest.raises(BoxError, match="not hardened"):
        b2.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    b3, ec2, win = box()
    win.console = False  # the box user's commands run in its session at the console: without it, no box
    with pytest.raises(BoxError, match="console"):
        b3.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    b4, ec2, win = box()
    win.job_check = "job-bad: sbx can change job.exe"
    with pytest.raises(BoxError, match="(?s)task for the box user's commands.*sbx can change job.exe"):
        b4.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    b5, ec2, win = box()
    win.desk = False  # the task does not start: the first command of the box user's says so, and the box ends
    with pytest.raises(BoxError, match="did not start"):
        b5.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_the_network_cut_is_checked_from_the_box_users_side_both_ways():
    b, ec2, win = box()
    b.start()
    before = len(win.commands)
    b.set_network(False)
    assert not b.network_enabled and win.offline_rules == 3
    probe = win.commands[-1]
    assert probe[0] == "sbx" and wb.PROBE_PS1 in probe[1] and f"-Dns '{wb.PROBE_NAME}'" in probe[1]
    assert all(target in probe[1] for target in wb.MUST_NOT_OPEN.values())
    b.set_network(True)
    assert b.network_enabled and win.offline_rules == 0
    probes = [c for c in win.commands[before:] if wb.PROBE_PS1 in c[1]]
    assert len(probes) == 3  # offline; still offline before it goes back; online again
    win.reached[("sbx", "internet")] = "open"  # the cut that does not hold for the box user
    with pytest.raises(BoxError, match="internet reachable with the network cut"):
        b.set_network(False)
    assert b.network_enabled  # never claimed on a word


def test_the_limits_tests_controls_pass_on_a_box_that_holds_and_see_one_that_does_not():
    b, _, win = box()
    b.start()
    rows = b.validate_containment()
    assert [name for name, ok, _, _ in rows if not ok] == []
    names = [name for name, _, _, _ in rows]
    assert {"link_local_control_admin", "held_connection_control", "held_connection_ended", "names_do_not_resolve_offline",
            "internet_offline_for_admin"} <= set(names)
    assert b.network_enabled and win.offline_rules == 0  # left online
    held = next(c for user, c in win.commands if "limits-held.go" in c)
    assert "Set-Content" in held and wb.HOLD_SCRIPT.count("@TAG@") == 3
    # the probe script is VBoxBox's with one more question
    assert wb.WIN_PROBE_SCRIPT.startswith("param([string]$Targets, [int]$Ms = 3000, [string]$Url = '', [string]$Dns = '')")
    assert "probe dns=resolved" in wb.WIN_PROBE_SCRIPT and vb.PROBE_SCRIPT.splitlines()[5] in wb.WIN_PROBE_SCRIPT


def test_files_are_written_as_the_box_user_a_chunk_per_command_and_read_back():
    b, _, win = box()
    b.start()
    data = bytes(range(256)) * 1000  # 256 kB: three chunks
    b.write_file("out/data.bin", data)
    path = r"C:\Users\sbx\work\out\data.bin"
    assert win.files[path] == data
    writes = [(user, script) for user, script in win.scripts if "WriteAllBytes" in script or "'Append'" in script]
    assert len(writes) == 3 and {user for user, _ in writes} == {"sbx"}
    assert "New-Item -ItemType Directory" in writes[0][1] and "'Append'" in writes[1][1]
    assert b.read_file("out/data.bin", 1000) == data[:1000]
    win.replies["WriteAllBytes"] = (1, "")
    with pytest.raises(BoxError, match="cannot write"):
        b.write_file("x.txt", "hi")


def test_the_box_describes_the_windows_it_is_and_its_run_names_it():
    b, _, _ = box()
    b.start()
    said = b.describe()
    assert "Windows Server 2025 Datacenter 24H2 (build 26100.33822)" in said and "not Windows 11" in said
    assert "python 3.12.10" in said and "pwsh 7.7.0" in said and "standard user" in said
    assert b.image == f"Windows Server 2025 Datacenter 24H2 (build 26100.33822), EC2 {ew.win_image_name()}"
    assert len(b.image) <= 120
    assert "Get-ChildItem" in b.list_command("x")
    assert "desktop session" in said and "nobody sees the screen" in said
    started = b.background("python -m http.server 8765", 8765, 20, "t7")
    # the command that runs it is already in sbx's own session, where what it starts stays: VBoxBox's own
    assert started == vb.VBoxBox.background(b, "python -m http.server 8765", 8765, 20, "t7") and "schtasks" not in started
    assert "Start-Process" in started and vb.encode_ps("python -m http.server 8765") in started
    assert "port 8765 open after" in started and started.rstrip().endswith("if ($ok) { exit 0 } else { exit 1 }")
    assert "'still running'" in b.background("x", None, 3, 1)
    assert b._guest_path("~/x") == r"C:\Users\sbx\x"
    hourly = b.usd_per_second() * 3600
    assert 0.19872 < hourly < 0.215  # Windows' licence is in the instance's price (Taipei's)


# -- the image


def test_the_image_is_named_after_its_scripts_and_says_what_it_holds(monkeypatch):
    name = ew.win_image_name()
    assert name.startswith("pickfit-win-server2025-") and ew.image_manifest(BAKED)["python"] == "3.12.10"
    assert ew.image_manifest(BAKED)["product"] == "Windows Server 2025 Datacenter"
    monkeypatch.setattr(ew, "WIN_TOOLS", ew.WIN_TOOLS + "\n# changed")
    assert ew.win_image_name() != name
    users = ew.users_script()
    assert "RandomNumberGenerator" in users and "[PfLsa]::Store('DefaultPassword', $__pf_secret)" in users
    assert "AutoAdminLogon '1'" in users and "DefaultUserName 'sbx'" in users
    assert base64.b64encode(vb.RUN_SCRIPT.encode()).decode() in users  # run.ps1 as VBoxBox's base has it
    assert base64.b64encode(wb.WIN_PROBE_SCRIPT.encode()).decode() in users
    config = ew.SSHD_CONFIG
    assert "AllowUsers administrator sbx" in config and config.index("Match User sbx") < config.index("Match Group administrators")
    assert "PasswordAuthentication no" in config.split("Match")[0] and "PubkeyAuthentication no" in config.split("Match")[1]
    assert "startSsm" not in ew.AGENT_CONFIG and "type: random" in ew.AGENT_CONFIG
    assert "EC2Launch.exe' reset" in ew.WIN_SEAL and "StartupType Manual" in ew.WIN_SEAL
    assert "administrators_authorized_keys" in ew.WIN_SEAL and "ssh_host_" in ew.WIN_SEAL
    steps = ew.bake_steps()
    assert steps["job"] == wb.make_job() and list(steps).index("users") < list(steps).index("job")
    monkeypatch.setattr(wb, "JOB_SOURCE", wb.JOB_SOURCE + "\n// changed")  # job.exe is the image's
    assert ew.win_image_name() != name
    # the image gets the current App Installer the way Microsoft documents for a Windows without the Store, for
    # all users; the PowerShell log keeps Windows' own access
    assert "WindowsStore" not in ew.WIN_SYSTEM and "wevtutil" not in ew.WIN_SYSTEM
    assert "Repair-WinGetPackageManager -AllUsers -Latest" in ew.WIN_REPAIR and ew.WIN_REPAIR.rstrip().endswith("'repaired'")
    assert base64.b64encode(ew.WIN_REPAIR.encode()).decode() in steps["apps"]  # in a PowerShell of its own, on its stdin
    assert "-Command - 2>&1" in steps["apps"] and "EncodedCommand" not in steps["apps"]
    assert steps["apps"].index("exit 1 }") < steps["apps"].index("Uninstall-Module Microsoft.WinGet.Client")
    # and what replaces it is then off, so a newer one does not arrive in the middle of a run
    assert steps["apps"].index("apps=$(Mine)") < steps["apps"].index("Set-Service InstallService -StartupType Disabled")
    assert "--source winget" in ew.WIN_DESK and "winget_search=$LASTEXITCODE" in ew.WIN_DESK
    assert list(steps).index("sbx") < list(steps).index("apps") < list(steps).index("desk")


def bake_fake(win: FakeWindows) -> None:
    steps = ew.bake_steps()
    # what sbx finds before Windows has updated the App Installer: Amazon's image has winget 1.9
    versions = "".join(f"{pair}\n" for pair in TOOLS.split(";")).replace("v1.29.380", "v1.9.25200")
    win.replies.update({
        steps["system"][-60:]: (0, "system-ok\n"), "logon-set": (0, "users-ok\nlogon-set\n"),
        "rules-made": (0, "rules-made\n"), "job-made": (0, "job-made\n"),
        steps["winget"][-40:]: (0, "winget=v1.9.25200\n"),
        "function Mine": (0, "module=1.29.380\nrepaired\napps=1.29.380.0 was=1.24.25200.0 top=1.29.380.0 module_left=0\nstore=Disabled\n"),
        "desk=": (0, "desk=1 interactive=True wmi=True\nwinget=v1.29.380\nwinget_search=0\n"),
        "pwsh_path=": (0, "pip uv pipx -> 0\npwsh_sha256=abc\npwsh_path=C:\\Program Files\\PowerShell\\7\\pwsh.exe\n"),
        "sshd-ok": (0, "sshd-ok\n"), "winget_source": (0, versions + "winget_source=0\n"),
        "restarting": (0, "restarting\n"), "LastBootUpTime": (0, "boot=40\n"), "console=sbx": (0, "console=sbx\n"),
        "hardened-ok": (0, "hardened-ok\n"), steps["check"][-40:]: (0, "hardened\n"),
        "license=": (0, "product=Windows Server 2025 Datacenter\nbuild=26100.33822\ndisplay=24H2\nlicense=Licensed\n"
                        "wu=Disabled/1\nfree_gb=14\n"),
        "sealed": (0, "reset=0\nsealed\n")})


def test_baking_runs_every_step_on_a_throwaway_instance_and_seals_it_last():
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    image = ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run)
    assert image["Name"] == ew.win_image_name() and image["ImageId"] == "ami-baked"
    launch = next(k for n, k in ec2.calls if n == "run_instances")
    assert launch["ImageId"] == "ami-win-base" and launch["InstanceType"] == ew.WIN_BAKE_TYPE
    assert launch["BlockDeviceMappings"][0] == {"DeviceName": "/dev/sda1", "Ebs": {
        "VolumeSize": ew.WIN_DISK_GB, "VolumeType": "gp3", "DeleteOnTermination": True}}
    steps = ew.bake_steps()
    ran = [script for _, script in win.scripts]
    order = [ran.index(steps[name]) for name in ("system", "users", "rules", "job", "winget", "tools", "sshd", "sbx",
                                                 "apps", "harden", "check", "final", "seal")]
    assert order == sorted(order) and ran[-1] == steps["seal"]
    # once sbx is logged on at the console, a command of its own goes through the image's task: the proof
    desk = next(i for i, (user, script) in enumerate(win.scripts) if user == "sbx" and script.startswith("nonce=bake\n"))
    assert next(i for i, r in enumerate(ran) if "shutdown.exe /r" in r) < desk < ran.index(steps["harden"])
    # before that, Windows' own update of the App Installer is waited for: the image has the winget a PC has
    assert next(i for i, r in enumerate(ran) if "shutdown.exe /r" in r) < ran.index(steps["apps"]) < desk
    assert ("sbx", ew.WIN_DESK) in win.commands and win.jobs[-1]["cwd"] == wb.WIN_HOME
    assert next(user for user, script in win.scripts if script == steps["sbx"]) == "sbx"
    assert ran.index(steps["sbx"]) < next(i for i, r in enumerate(ran) if "shutdown.exe /r" in r) < ran.index(steps["harden"])
    calls = [n for n in ec2.names() if n in ("run_instances", "stop_instances", "create_image", "terminate_instances")]
    assert calls == ["run_instances", "stop_instances", "create_image", "terminate_instances"]
    assert ew.image_manifest(image) == ew.image_manifest(BAKED)
    assert ew.ensure_win_image(ec2, control=CONTROL)["ImageId"] == "ami-baked" and ec2.names().count("create_image") == 1


def test_a_bake_whose_step_fails_or_whose_box_user_lacks_a_tool_ends_the_builder():
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    win.replies["pwsh_path="] = (6, "pwsh.exe is not signed by Microsoft (NotSigned)\n")
    with pytest.raises(BoxError, match="not signed by Microsoft"):
        ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run)
    assert "create_image" not in ec2.names() and ec2.instances["i-1"]["State"]["Name"] == "terminated"
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    win.replies["winget_source"] = (0, "pwsh=7.7.0\nwinget=unavailable\nwinget_source=1\n")
    with pytest.raises(BoxError, match="sbx has no"):
        ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run)
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    for said, why in (("apps=1.24.25200.0 was=1.24.25200.0 top=1.29.380.0 module_left=0\nstore=Disabled\n",
                       "newest App Installer"),  # a newer one is on the machine and not yet sbx's
                      ("apps=1.29.380.0 was=1.24.25200.0 top=1.29.380.0 module_left=1\nstore=Disabled\n",
                       "module that installed the App Installer is still there"),
                      ("the App Installer was not repaired\n", "apps failed"),  # the repair did not finish: no image
                      ("apps=1.29.380.0 was=1.24.25200.0 top=1.29.380.0 module_left=0\nstore=Manual\n",
                       "install service is still 'Manual'")):  # what replaces it later is still on
        ec2 = WinEc2(images=[BASE])
        win = FakeWindows(ec2)
        bake_fake(win)
        win.replies["function Mine"] = (0, said)
        with pytest.raises(BoxError, match=why):
            ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run)
        assert "create_image" not in ec2.names() and ec2.instances["i-1"]["State"]["Name"] == "terminated"
    for said in ("desk=0 interactive=False wmi=True\nwinget=v1.29.380\nwinget_search=0\n", "desk=1 interactive=True wmi=True\n",
                 "desk=1 interactive=True wmi=True\nwinget=v1.29.380\nwinget_search=-1978335212\n"):
        ec2 = WinEc2(images=[BASE])
        win = FakeWindows(ec2)
        bake_fake(win)
        win.replies["desk="] = (0, said)  # a session without a desktop; no winget there; winget's source not answering
        with pytest.raises(BoxError, match="do not run at its desktop"):
            ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run)
        assert "create_image" not in ec2.names() and ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_a_pool_member_boots_with_nobodys_keys_and_forgets_its_boot(monkeypatch):
    monkeypatch.setenv(e.POOL_ENV, "1")
    m, ec2, _ = machine()
    m.start()
    member = [k for n, k in ec2.calls if n == "run_instances"][1]
    data = member["UserData"]
    assert member["InstanceInitiatedShutdownBehavior"] == "stop" and member["InstanceType"] == "m7i-flex.large"
    assert data.startswith("<powershell>") and "ssh_host" not in data and "authorized_keys" not in data
    assert f"shutdown.exe /s /f /t {ew.WIN_WARM_LIFETIME_S} " in data and "Start-Service sshd" not in data
    # It reads what a box's commands read, many files at once and for a bounded time, with a reader only
    # administrators could have put there, exempt from Defender's scan while it runs and removed after.
    read = data[data.index("$exe = "):data.index("$done = ")]
    assert ew.WARM_EXE.startswith(wb.HARNESS_DIR + "\\") and f"$exe = '{ew.WARM_EXE}'" in read
    assert f'& $exe {ew.WARM_READ_S} 32 "C:\\ProgramData\\pickfit" "C:\\Program Files\\PowerShell"' in read
    assert read.index("Add-MpPreference -ExclusionProcess $exe") < read.index("& $exe ") < read.index(
        "Remove-MpPreference -ExclusionProcess $exe") < read.index("Remove-Item $exe -Force")
    assert "DisableRealtimeMonitoring" not in data  # Defender itself stays on
    assert "Parallel.ForEach" in ew.WARM_READER and "state.Stop()" in ew.WARM_READER and "ReparsePoint" in ew.WARM_READER
    assert len(data.encode()) < 16000  # EC2's limit on user data
    # The boot agent is reset by a task of its own, once the agent has ended, and that task shuts the member down.
    task = data[data.rindex("@'\n"):data.rindex("'@")]
    assert task.index("Get-Process EC2Launch") < task.index("EC2Launch.exe' reset") < task.index("shutdown.exe /s /f /t 0")
    assert "schtasks.exe /Run /TN pickfit-warm-done" in data[data.rindex("'@"):] and "/RU SYSTEM" in data


def test_the_cli_makes_windows_boxes_on_ec2():
    from pickfit.verify import cli as verify_cli
    from pickfit.verify.cli import box_factory

    made = box_factory("ec2-windows", 900)("run-1", "agent")
    assert isinstance(made, ew.Ec2WindowsBox) and isinstance(made, wb.WindowsBox)
    assert made.machine.tags == {"pickfit.run": "run-1", "pickfit.role": "agent"} and made.limits.lifetime_s == 900
    assert made.machine._price()[0] == "m7i-flex.large"
    assert verify_cli.EC2_CONCURRENCY == 2  # a batch on EC2 by default: two boxes at a time
    for flags in ({"toolchain": True}, {"audio": True}):
        with pytest.raises(ValueError):
            box_factory("ec2-windows", 900, **flags)
    shown = box_factory("ec2-windows", 900, display=True)("run-1", "agent")  # the display image, its own pool
    assert shown.display == "vnc" and shown.machine.image_name == ew.win_image_name(display=True)
    assert ew.win_image_name(display=True).startswith("pickfit-win-server2025-gui-")
    assert ew.win_image_name(display=True) != ew.win_image_name() == made.machine.image_name
    with pytest.raises(ValueError, match="gpu"):
        box_factory("ec2-windows", 900, gpu="T4")
    assert AwsError("x").response["Error"]["Code"] == "x"


# -- a box with a display (gui_win)


class FakeScreen:
    size = (1280, 800)

    def __init__(self, box: Any) -> None:
        self.box = box

    def close(self) -> None:
        pass


def display_box(monkeypatch: pytest.MonkeyPatch, *, start: str = "display-ok session=1\n",
                size: tuple[int, int] = (1280, 800)) -> tuple[ew.Ec2WindowsBox, FakeEc2, FakeWindows]:
    ec2 = WinEc2(images=[{**BAKED, "Name": ew.win_image_name(display=True)}])
    win = FakeWindows(ec2)
    made = ew.Ec2WindowsBox(ec2=ec2, control=CONTROL, log=lambda line: None, display=True)
    made.machine.popen, made.machine.run_local = win.popen, win.run
    procs = [{"pid": 10, "exe": r"C:\Windows\explorer.exe", "sid": SBX_SID, "start": "1"},
             {"pid": 11, "exe": r"C:\ProgramData\pickfit\job.exe", "sid": SBX_SID, "start": "2"},
             {"pid": 12, "exe": r"C:\Windows\System32\winlogon.exe", "sid": "S-1-5-18", "start": "3"}]
    win.replies.update({"display-bad: ": (0, start),
                        f"& '{gui_win.DESK_EXE}' procs": (0, json.dumps({"session": 1, "sid": "S-1-5-18",
                                                                          "procs": procs}) + "\n")})
    screen = type("Screen", (FakeScreen,), {"size": size})
    monkeypatch.setattr(gui_win, "WinVncDisplay", screen)
    return made, ec2, win


def test_a_display_box_gives_its_vnc_server_a_password_of_its_own_and_notes_the_desktop(monkeypatch):
    b, _, win = display_box(monkeypatch)
    assert b.display == "vnc" and b.machine.image_name.startswith("pickfit-win-server2025-gui-")
    b.start()
    password = b.vnc_password
    assert password and len(password) == 8
    started = next(command for user, command in win.commands if user == wm.ADMIN_USER and "display-bad: " in command)
    assert password not in started  # only its stored form went to the machine
    assert base64.b64encode(vnc.vnc_stored_password(password)).decode() in started
    assert b.session == {"10": ["1", r"C:\Windows\explorer.exe"]}  # the desktop, not pickfit's job.exe
    assert b.user_sid == SBX_SID and isinstance(b.screen(), FakeScreen)
    assert "launch_gui" in b.describe() and "1280x800" in b.describe() and "nobody sees the screen" not in b.describe()
    assert b.launch_gui.__func__ is wb.WindowsBox.launch_gui  # a box with its own display launches its way


def test_a_display_box_that_is_not_as_its_image_makes_it_ends(monkeypatch):
    b, ec2, _ = display_box(monkeypatch, start="display-bad: Users can change C:\\ProgramData\\pickfit\\desk.exe\n")
    with pytest.raises(BoxError, match="display is not as the image makes it"):
        b.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated" and b.vnc_password is None
    b, ec2, _ = display_box(monkeypatch, size=(800, 600))
    with pytest.raises(BoxError, match="800x600, not the virtual display's 1280x800"):
        b.start()
    assert ec2.instances["i-1"]["State"]["Name"] == "terminated"


def test_an_administrators_program_gets_its_stdin_through_powershell():
    b, _, win = box()
    b.start()
    win.replies["Python312"] = (0, "ran\n")
    source = ("# " + "x" * 40_000 + "\nprint('hi')\n").encode()  # the file check's script is about this long
    done = b.harness_exec([b.harness_python, "-I", "-S", "-"], 60, stdin=source)
    assert done.exit_code == 0 and "ran" in done.stdout
    user, script = win.scripts[-1]
    assert user == wm.ADMIN_USER and base64.b64encode(source).decode() in script and "print(" not in script
    assert "| & 'C:\\Program Files\\Python312\\python.exe' '-I' '-S' '-'" in script
    # straight to Windows PowerShell on the session's stdin: not through run.ps1, whose environment variable
    # Windows caps at 32,767 characters
    assert wb.RUN_PS1 not in script and f"Set-Location '{wb.HARNESS_DIR}'" in script


def test_a_display_image_bakes_its_display_and_sets_the_box_users_screen():
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    win.replies.update({"display-made": (0, "desk-made\nvdd=installed reboot=False\nvnc=2.8.89.0\ndisplay-made\n"),
                        "screen_set=": (0, "screen_set=primary=0 detach=0 apply=0\nscreens=1 primary=1280x800\n")})
    image = ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run, display=True)
    assert image["Name"] == ew.win_image_name(display=True)
    steps = ew.bake_steps(display=True)
    ran = [script for _, script in win.scripts]
    assert ran.index(steps["tools"]) < ran.index(steps["display"]) < ran.index(steps["sshd"])
    screen = next(i for i, (user, s) in enumerate(win.scripts) if user == "sbx" and s.startswith("nonce=bake\n")
                  and ("sbx", gui_win.SCREEN) in win.commands)
    assert ("sbx", gui_win.SCREEN) in win.commands  # set by the box user, at its desktop
    assert ran.index(steps["apps"]) < screen < ran.index(steps["harden"])
    made = next(k for n, k in ec2.calls if n == "create_image")
    tags = {t["Key"]: t["Value"] for t in made["TagSpecifications"][0]["Tags"]}
    assert tags["pickfit:display"] == "1280x800;vdd=25.7.23;vnc=2.8.89.0"
    assert ew.image_manifest({"Tags": made["TagSpecifications"][0]["Tags"]})["display"].startswith("1280x800")
    assert "display" not in ew.bake_steps() and "screen" not in ew.bake_steps()  # the plain image is as it was
    ec2 = WinEc2(images=[BASE])
    win = FakeWindows(ec2)
    bake_fake(win)
    win.replies.update({"display-made": (0, "display-made\n"),
                        "screen_set=": (0, "screen_set=no display matches Virtual Display\nscreens=1 primary=800x600\n")})
    with pytest.raises(BoxError, match="not the virtual display alone"):
        ew.bake_win_image(ec2, log=lambda line: None, control=CONTROL, popen=win.popen, run=win.run, display=True)
    assert "create_image" not in ec2.names() and ec2.instances["i-1"]["State"]["Name"] == "terminated"
