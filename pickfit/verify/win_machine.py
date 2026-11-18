"""WinSshMachine: a rented Windows VM, driven over SSH. What every cloud's Windows box shares.

The Windows counterpart of ssh_machine.SshMachine: a provider (ec2_windows.Ec2WinMachine) creates the VM, opens
and closes its egress from outside it, seals what only that cloud has, and destroys it. windows_box.WindowsBox
turns the machine into a box. Measured 2026-11-16 on EC2's Windows Server 2025 (OpenSSH 9.5):

- Keys made for this one machine, handed over in the boot script (the provider's user data): the administrator's
  login key and the host key the harness pins. The script arms the lifetime's shutdown first and starts sshd
  last; boot() checks the shutdown, and removes the script itself, which the provider's boot agent leaves on
  disk with the host key in it (in SYSTEM's own temp folder). sshd does not start by itself in pickfit's image,
  so a machine that answers has been through the script.
- Two logins. The administrator logs in with the key and gets a full token (High integrity, SeDebug): the
  harness's own checks and rules. The box user logs in with its password, which the administrator reads from
  the LSA secret Windows keeps it in for the auto logon, where the box user is denied. A key would do for the
  login but not for the session: Windows makes a key login without the user's credentials (S4U), and DPAPI then
  refuses the user ("Access is denied" from ProtectedData.Protect), which a tool that stores a token would hit.
  With the password the same call works. Each user's commands share one connection.
- A command is a PowerShell script. sshd starts `powershell -Command -`, the same line every time, and the script
  arrives on its stdin as one line that decodes and runs it: no script or secret is ever on a command line,
  which Windows PowerShell logs where users can read it. Reading stdin from the script itself hangs: with
  `-Command <text>` PowerShell also reads stdin for the command's input, and a script that read it to its end and
  then ran a cmdlet which loads a module never returned (Get-Acl, Get-Process; fifteen minutes, three times).
- A command the local client gives up on still runs on the machine; the box's own commands go through run.ps1,
  which ends their process tree at the timeout.
- The cut has two halves, as on Linux. Windows Firewall rules made with the image and switched on here: the box
  user's every outbound packet is dropped (measured: a new connection fails at once and one held open before
  the rule is reset; the administrator's still open), and port 53 is closed for everyone, because names are
  resolved by a system service, not by the user's process, and a cloud's resolver may answer with egress closed.
  Then the provider closes egress outside the VM, and the administrator sees a new connection fail. A rule that
  is always on keeps the box user from link-local addresses (cloud metadata and what else a cloud serves there).

Needs the system's ssh and ssh-keygen (OpenSSH 8.4 or later, for SSH_ASKPASS_REQUIRE).
"""

from __future__ import annotations

import base64
import os
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pickfit.verify.box import OUTPUT_HEAD_BYTES, OUTPUT_TAIL_BYTES, BoxError
from pickfit.verify.machine import collect
from pickfit.verify.ssh_machine import CONNECT_TIMEOUT_S, SSH, SshLink, SshProcess

ADMIN_USER = "Administrator"
BOX_USER = "sbx"
BOOT_WAIT_S = 600  # from "the provider says it runs" to sshd answering with this machine's keys
# What sshd runs for every command, whoever asks and whatever the script is.
PS_STDIN = "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command -"
# First in every script: output as UTF-8 (the console's code page otherwise), and no progress records on stderr.
PRELUDE = "[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false\n$ProgressPreference = 'SilentlyContinue'\n"
LIFETIME_NOTE = "pickfit-lifetime"

# The boot script, as SYSTEM, before anything else of pickfit's runs. In this order: a machine that never gets
# as far as sshd still shuts down, and one that answers has its shutdown armed.
BOOT_SCRIPT = r"""$ErrorActionPreference = 'Stop'
shutdown.exe /s /f /t @LIFETIME@ /d p:0:0 /c pickfit-lifetime
$ssh = 'C:\ProgramData\ssh'
New-Item -ItemType Directory -Force $ssh | Out-Null
[IO.File]::WriteAllBytes("$ssh\ssh_host_ed25519_key", [Convert]::FromBase64String('@HOST@'))
[IO.File]::WriteAllBytes("$ssh\ssh_host_ed25519_key.pub", [Convert]::FromBase64String('@HOSTPUB@'))
[IO.File]::WriteAllBytes("$ssh\administrators_authorized_keys", [Convert]::FromBase64String('@LOGIN@'))
foreach ($f in 'ssh_host_ed25519_key', 'administrators_authorized_keys') {
  icacls.exe "$ssh\$f" /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null }
netsh.exe advfirewall firewall show rule name=pickfit-ssh | Out-Null
if ($LASTEXITCODE -ne 0) {
  netsh.exe advfirewall firewall add rule name=pickfit-ssh dir=in action=allow protocol=TCP localport=22 profile=any | Out-Null }
Start-Service sshd
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
# As the administrator. A second shutdown while one is pending is refused with 1190: that refusal is the proof.
# The boot script must be gone from the temp folders a boot agent runs it from. It cannot delete itself there
# (measured 2026-11-17 on EC2: the agent holds the file while it runs, and leaves it), so this removes it, in
# the moment after the agent lets go, and counts what is left.
BOOT_CHECK = r"""shutdown.exe /s /f /t @LIFETIME@ /d p:0:0 /c pickfit-lifetime 2> $null
"shutdown=$LASTEXITCODE"
$dirs = "$env:SystemRoot\System32\config\systemprofile\AppData\Local\Temp", "$env:SystemRoot\Temp"
foreach ($try in 1..20) {
  $left = @(Get-ChildItem $dirs -Filter UserScript.ps1 -Recurse -Force -ErrorAction SilentlyContinue)
  if (-not $left) { break }
  $left | Remove-Item -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 500 }
"scripts=$(@(Get-ChildItem $dirs -Filter UserScript.ps1 -Recurse -Force -ErrorAction SilentlyContinue).Count)"
"""
ALREADY_SCHEDULED = 1190

# The firewall rules of the image (rules(), made once as the administrator), by name.
GUARD_RULE = "pickfit-guard"  # always on: the box user never reaches link-local addresses
CUT_RULE = "pickfit-cut"  # offline: every outbound packet of the box user
DNS_RULES = ("pickfit-cut-dns-udp", "pickfit-cut-dns-tcp")  # offline: port 53, for everyone
LINK_LOCAL = "169.254.0.0/16, fe80::/10, fd00:ec2::/32"
MAKE_RULES = rf"""$ErrorActionPreference = 'Stop'
$who = "D:(A;;CC;;;$((Get-LocalUser {BOX_USER}).SID.Value))"
Get-NetFirewallRule -Name 'pickfit-guard', 'pickfit-cut*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name {GUARD_RULE} -DisplayName 'pickfit: the box user never reaches link-local addresses' `
  -Direction Outbound -Action Block -LocalUser $who -RemoteAddress {LINK_LOCAL} -Profile Any -Enabled True | Out-Null
New-NetFirewallRule -Name {CUT_RULE} -DisplayName 'pickfit: the box user offline' -Direction Outbound -Action Block `
  -LocalUser $who -Profile Any -Enabled False | Out-Null
New-NetFirewallRule -Name {DNS_RULES[0]} -DisplayName 'pickfit: no names offline (UDP)' -Direction Outbound `
  -Action Block -Protocol UDP -RemotePort 53 -Profile Any -Enabled False | Out-Null
New-NetFirewallRule -Name {DNS_RULES[1]} -DisplayName 'pickfit: no names offline (TCP)' -Direction Outbound `
  -Action Block -Protocol TCP -RemotePort 53 -Profile Any -Enabled False | Out-Null
'rules-made'
"""
_OFFLINE = ", ".join((CUT_RULE, *DNS_RULES))
RULE_STATE = (f"$on = @(Get-NetFirewallRule -Name {_OFFLINE} | Where-Object {{ $_.Enabled -eq 'True' }}).Count\n"
              f"$guard = @(Get-NetFirewallRule -Name {GUARD_RULE} | Where-Object {{ $_.Enabled -eq 'True' -and "
              "$_.Action -eq 'Block' }).Count\n"
              "\"offline_rules=$on guard=$guard\"\n")
CUT_ON = f"Enable-NetFirewallRule -Name {_OFFLINE}\nClear-DnsClientCache\n" + RULE_STATE
CUT_OFF = f"Disable-NetFirewallRule -Name {_OFFLINE}\n" + RULE_STATE
RULES_ONLINE = "offline_rules=0 guard=1"
RULES_OFFLINE = f"offline_rules={1 + len(DNS_RULES)} guard=1"

# Where Winlogon reads the auto-logon password, and how the administrator reads it there. Only SYSTEM and
# administrators may open LSA secrets; limits.py's no_logon_secret probe checks the box user is refused.
LSA_READ = r"""Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class PfLsaRead {
  [StructLayout(LayoutKind.Sequential)] struct U { public ushort Length; public ushort MaximumLength; public IntPtr Buffer; }
  [StructLayout(LayoutKind.Sequential)] struct A { public int Length; public IntPtr Root; public IntPtr Name; public uint Attributes; public IntPtr Sd; public IntPtr Qos; }
  [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr system, ref A attrs, uint access, out IntPtr policy);
  [DllImport("advapi32.dll")] static extern uint LsaRetrievePrivateData(IntPtr policy, ref U key, out IntPtr data);
  [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr policy);
  [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr p);
  public static string Read(string name) {
    A a = new A(); a.Length = Marshal.SizeOf(a); IntPtr p;
    if (LsaOpenPolicy(IntPtr.Zero, ref a, 0x4, out p) != 0) return null;
    U k; k.Buffer = Marshal.StringToHGlobalUni(name); k.Length = (ushort)(name.Length * 2); k.MaximumLength = (ushort)(name.Length * 2 + 2);
    IntPtr d; uint st = LsaRetrievePrivateData(p, ref k, out d); LsaClose(p); Marshal.FreeHGlobal(k.Buffer);
    if (st != 0 || d == IntPtr.Zero) return null;
    U v = (U)Marshal.PtrToStructure(d, typeof(U)); string s = Marshal.PtrToStringUni(v.Buffer, v.Length / 2); LsaFreeMemory(d); return s; }
}
'@
'PFPW:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([PfLsaRead]::Read('DefaultPassword')))
"""
# As the administrator: does a new connection to the internet open? One "open" per address that answers.
EGRESS_PROBE = ("foreach ($a in '1.1.1.1', '8.8.8.8') { $c = New-Object Net.Sockets.TcpClient\n"
                "  try { if ($c.ConnectAsync($a, 443).Wait(2000) -and $c.Connected) { 'open' } } catch { } "
                "finally { $c.Close() } }\n")
# The box user's password prompt, answered from the environment of the one ssh process that opens its connection.
ASKPASS = '#!/bin/sh\nprintf \'%s\\n\' "$PF_SSH_PASS"\n'


def ps_line(script: str) -> bytes:
    """The one line `powershell -Command -` reads from stdin to run `script`: any script, however many lines."""
    encoded = base64.b64encode((PRELUDE + script).encode()).decode()
    return ("Invoke-Expression ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded
            + "')))\n").encode()


def boot_script(login_public: str, host_private: str, host_public: str, lifetime_s: int) -> str:
    def b64(text: str) -> str:
        return base64.b64encode(text.encode()).decode()

    return (BOOT_SCRIPT.replace("@LIFETIME@", str(int(lifetime_s))).replace("@HOST@", b64(host_private))
            .replace("@HOSTPUB@", b64(host_public + "\n")).replace("@LOGIN@", b64(login_public + "\n")))


class WinSshMachine(SshLink, ABC):
    """A Windows VM over SSH. A provider implements _create, _provider_egress and _destroy, _seal if its cloud has
    something to close, and wrap_user_data if its boot agent wants the script in an envelope."""

    login_user = ADMIN_USER
    os = "windows"
    boot_wait_s: float = BOOT_WAIT_S

    def __init__(self, *, cores: float, memory_mb: int, lifetime_s: int, log: Callable[[str], None] = print,
                 popen: Callable[..., Any] = subprocess.Popen, run: Callable[..., Any] = subprocess.run) -> None:
        self.cores = cores
        self.memory_mb = memory_mb
        self.lifetime_s = lifetime_s
        self.log = log
        self._init_link(popen, run)
        self.timings: dict[str, float] = {}  # seconds each part of start() took
        self._box_password: str | None = None
        self._closed = False

    # -- what a provider gives

    @abstractmethod
    def _create(self, user_data: str) -> str:
        """Create the VM with this user data and egress limited to ONLINE_CIDRS; set machine_id and return the
        address the harness reaches it on."""

    @abstractmethod
    def _provider_egress(self, enabled: bool) -> None:
        """Open egress to ONLINE_CIDRS or close it, outside the VM; return once it is so, BoxError if not."""

    @abstractmethod
    def _destroy(self) -> None:
        """Destroy the VM and what was made for it."""

    def _seal(self) -> None:
        """Close what only this cloud has (its metadata service), after boot and before the box user runs."""

    def _recreate(self) -> str | None:
        """The address of a second machine in place of one that did not answer, or None (see SshMachine)."""
        return None

    def wrap_user_data(self, script: str) -> str:
        """The boot script as this cloud's boot agent takes it."""
        return script

    # -- commands

    def _master(self, user: str | None = None) -> bool:
        """The box user's shared connection is opened with its password; the administrator's with the key."""
        if (user or self.login_user) != BOX_USER:
            return super()._master(user)
        assert self.keys_dir is not None and self.address is not None
        if self._box_password is None:
            self._last_ssh_error = "the box user's password has not been read yet"
            return False
        d = self.keys_dir
        ask = d / "askpass"
        if not ask.exists():
            ask.write_text(ASKPASS)
            ask.chmod(0o700)
        argv = [SSH, "-F", "/dev/null", "-o", f"UserKnownHostsFile={d / 'known_hosts'}",
                "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
                "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "PreferredAuthentications=password",
                "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
                "-o", f"ConnectTimeout={CONNECT_TIMEOUT_S}", "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=4", "-o", "LogLevel=ERROR",
                "-o", f"ControlPath={self._control_path(BOX_USER)}", "-o", "ControlMaster=yes",
                "-o", "ControlPersist=yes", "-N", "-f", "-T", f"{BOX_USER}@{self.address}"]
        env = {**os.environ, "SSH_ASKPASS": str(ask), "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": "none",
               "PF_SSH_PASS": self._box_password}
        try:
            opened = self.run_local(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=40, env=env)
        except subprocess.TimeoutExpired:
            self._last_ssh_error = "ssh did not return in 40s"
            return False
        self._last_ssh_error = opened.stderr.strip()[-200:]
        return opened.returncode == 0

    def spawn(self, user: str, script: str, timeout_s: float) -> SshProcess:
        """Start a PowerShell script as that user (Windows PowerShell 5.1 runs it); the local client is killed
        after timeout_s."""
        proc = self._ssh_spawn(PS_STDIN, timeout_s, user)
        try:
            proc.stdin.write(ps_line(script))
            proc.stdin.write_eof()
        except BrokenPipeError:  # the connection is gone; wait() says so
            pass
        return proc

    def spawn_exe(self, user: str, path: str, data: bytes, timeout_s: float) -> SshProcess:
        """Start a program of the image's as that user, by its path alone, with `data` as its stdin: what it is to
        do is never on a command line."""
        proc = self._ssh_spawn(path, timeout_s, user)
        try:
            proc.stdin.write(data)
            proc.stdin.write_eof()
        except BrokenPipeError:
            pass
        return proc

    def _collected(self, start: Callable[[], SshProcess], timeout_s: float, head: int,
                   tail: int) -> tuple[int | None, str, str, bool]:
        try:
            proc = start()
            code, out, err = collect(proc, timeout_s + 5, head, tail)
        except BoxError:
            raise
        except Exception as error:
            raise BoxError(self.explain(error)) from error
        if proc.killed:
            code = None
        return code, out.text(), err.text(), bool(out.dropped or err.dropped)

    def run_ps(self, user: str, script: str, timeout_s: float, *, head: int = OUTPUT_HEAD_BYTES,
               tail: int = OUTPUT_TAIL_BYTES) -> tuple[int | None, str, str, bool]:
        """Run a script as that user to its end; (exit code or None when the host gave up, stdout, stderr,
        output was dropped). The exit code is the script's own, modulo 256 as SSH carries it."""
        return self._collected(lambda: self.spawn(user, script, timeout_s), timeout_s, head, tail)

    def run_exe(self, user: str, path: str, data: bytes, timeout_s: float, *, head: int = OUTPUT_HEAD_BYTES,
                tail: int = OUTPUT_TAIL_BYTES) -> tuple[int | None, str, str, bool]:
        """Run a program of the image's as that user to its end, `data` on its stdin; what run_ps returns."""
        return self._collected(lambda: self.spawn_exe(user, path, data, timeout_s), timeout_s, head, tail)

    def admin(self, script: str, timeout_s: float = 60) -> tuple[int | None, str, str]:
        """A script as the administrator; (exit code, stdout, stderr). pickfit's own checks, rules and probes."""
        code, out, err, _ = self.run_ps(ADMIN_USER, script, timeout_s)
        return code, out, err

    def admin_checked(self, script: str, timeout_s: float, what: str, *, expect: str = "") -> str:
        code, out, err = self.admin(script, timeout_s)
        if code != 0 or expect not in out:
            raise BoxError(f"{what} failed (exit {code}): {(out + err).strip()[-400:]}")
        return out

    # -- lifecycle

    def user_data(self) -> str:
        login_public, host_private, host_public = self._make_keys()
        return self.wrap_user_data(boot_script(login_public, host_private, host_public, self.lifetime_s))

    def boot(self) -> None:
        """Create the VM and wait until it is up and ours: sshd answers the administrator with the pinned host
        key, the lifetime's shutdown is armed, and the boot script is gone. Closes the machine and raises
        BoxError if not."""
        try:
            began = time.monotonic()
            self.address = self._create(self.user_data())
            self.timings["create_s"] = round(time.monotonic() - began, 1)
            began = time.monotonic()
            try:
                self._connect(wait_s=self.boot_wait_s)
            except BoxError:
                again = self._recreate()
                if again is None:
                    raise
                self.address = again
                self._connect(wait_s=self.boot_wait_s)
            self.timings["ssh_s"] = round(time.monotonic() - began, 1)
            out = self.admin_checked(BOOT_CHECK.replace("@LIFETIME@", str(int(self.lifetime_s))), 60,
                                     "checking the machine's boot")
            if f"shutdown={ALREADY_SCHEDULED}" not in out:
                raise BoxError(f"the lifetime's shutdown was not armed by the boot script ({out.strip()[-120:]})")
            if "scripts=0" not in out:
                raise BoxError("the boot script, which holds the host key, is still on the machine's disk")
        except BaseException as error:
            self.close()
            if isinstance(error, BoxError) or not isinstance(error, Exception):
                raise
            raise BoxError(f"{self.provider} machine start failed: {type(error).__name__}: {error}") from error

    def box_password(self) -> str:
        """The box user's password, as the administrator reads it from the LSA secret of the auto logon."""
        out = self.admin_checked(LSA_READ, 90, "reading the box user's logon secret", expect="PFPW:")
        encoded = out.split("PFPW:", 1)[1].split()
        password = base64.b64decode(encoded[0]).decode() if encoded else ""
        if not password:
            raise BoxError("the image has no logon secret for the box user")
        return password

    def start(self) -> None:
        self.boot()
        try:
            began = time.monotonic()
            self._seal()
            state = self.admin_checked(RULE_STATE, 60, "reading the machine's firewall rules")
            if RULES_ONLINE not in state:
                raise BoxError(f"the machine's firewall rules are not as the image makes them ({state.strip()[-80:]})")
            self._box_password = self.box_password()
            self._connect(BOX_USER, wait_s=60)
            self.timings["box_s"] = round(time.monotonic() - began, 1)
        except BaseException as error:
            self.close()
            if isinstance(error, BoxError) or not isinstance(error, Exception):
                raise
            raise BoxError(f"{self.provider} machine start failed: {type(error).__name__}: {error}") from error
        self.log(f"{self.provider} machine {self.machine_id} up: " +
                 ", ".join(f"{name[:-2]} {seconds}s" for name, seconds in self.timings.items()))

    def egress_open(self) -> bool:
        """As the administrator, whom the machine's own rules do not stop: does a new connection open?"""
        return "open" in self.admin(EGRESS_PROBE, 20)[1]

    def set_egress(self, enabled: bool) -> None:
        if enabled:  # the provider first: while its cut holds, the machine's rules change nothing
            self._provider_egress(True)
            state = self.admin_checked(CUT_OFF, 60, "switching off the machine's offline rules")
            if RULES_ONLINE not in state:
                raise BoxError(f"the machine's offline rules are still on ({state.strip()[-80:]})")
        else:  # the rules first: they end what the box user already has open, which a stateful firewall would not
            state = self.admin_checked(CUT_ON, 60, "the machine's offline rules")
            if RULES_OFFLINE not in state:
                raise BoxError(f"the machine's offline rules are not on ({state.strip()[-80:]})")
            self._provider_egress(False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._destroy()
        except Exception as error:  # the lifetime's shutdown ends it anyway
            self.log(f"{self.provider} destroy: {type(error).__name__}: {error}")
        self._box_password = None
        self._close_link((BOX_USER,))

    def usd_per_second(self) -> float:
        return 0.0

    def explain(self, error: Exception) -> str:
        if isinstance(error, ConnectionError):
            return (f"the {self.provider} machine stopped answering during this command (it was destroyed, or it "
                    f"reached its {self.lifetime_s}s lifetime): {error}")
        return f"{self.provider} exec failed: {type(error).__name__}: {error}"[:400]
