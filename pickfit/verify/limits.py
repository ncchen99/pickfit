"""`pickfit verify --limits-test`: check a box's guard rails with real commands.

Each probe runs in one fresh box and says whether the limit held: the box
user has no capabilities, cloud metadata and private ranges are unreachable,
the network cut blocks the internet but not localhost and can be undone, a
command is killed at its timeout, and file size, process count and memory are
capped. No model is called. Measured 2026-10-29: Docker kills only the process
that goes over the memory limit; Modal kills the whole sandbox. A macOS box has
no /proc and no per-process memory cap (the VM's RAM is the cap), so it checks
instead that the box user is not an admin, cannot sudo or change the firewall,
and cannot reach the host. A Windows box checks the same kind of things in
PowerShell, plus that exit codes survive VBoxManage's mapping.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from pickfit.ledger import taipei_now
from pickfit.verify.box import Box, BoxError, ExecResult

PYPI = "curl -sS -I -m 15 -o /dev/null -w '%{http_code}' https://pypi.org/simple/pip/"
# su admin in a pseudo-terminal, answering the password prompt with the image's default password.
SU_ADMIN = """python3 - <<'PICKFIT_PY'
import os, pty, select, time
pid, fd = pty.fork()
if pid == 0:
    os.execv("/usr/bin/su", ["su", "admin", "-c", "echo PICKFIT_SU_OK"])
out, sent, end = b"", False, time.time() + 15
while time.time() < end:
    if not select.select([fd], [], [], 0.5)[0]:
        continue
    try:
        data = os.read(fd, 1024)
    except OSError:
        break
    if not data:
        break
    out += data
    if not sent and b"assword" in out:
        os.write(fd, b"admin\\n")
        sent = True
print(out.decode(errors="replace"))
PICKFIT_PY"""


@dataclass
class ProbeResult:
    name: str
    ok: bool
    expect: str
    exit_code: int | None
    seconds: float
    detail: str


def _detail(result: ExecResult) -> str:
    text = f"{result.stdout.strip()} {result.stderr.strip()}".strip()
    return " ".join(text.split())[-300:]


def _probe(box: Box, name: str, command: str, timeout_s: int, expect: str,
           check: Callable[[ExecResult], bool]) -> ProbeResult:
    result = box.exec(command, timeout_s)
    return ProbeResult(name, bool(check(result)), expect, result.exit_code, result.seconds, _detail(result))


def _not_admin(result: ExecResult) -> bool:
    lines = result.stdout.splitlines()
    groups = lines[1].split() if len(lines) > 1 else ["?"]
    return lines[:1] != ["0"] and "admin" not in groups and "sudo=0" not in result.stdout


WIN_IS_ADMIN = ("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())"
                ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator); whoami /groups /fo csv | "
                "Select-String 'S-1-5-32-544|S-1-16-12288'")
WIN_HARNESS_WRITE = ("foreach ($p in 'C:\\ProgramData\\pickfit\\run.ps1','C:\\ProgramData\\pickfit\\probe.ps1') { "
                     "try { [IO.File]::AppendAllText($p, '#'); \"writable $p\" } catch { \"locked $p\" } }; "
                     "try { New-Item -ItemType File C:\\ProgramData\\pickfit\\x.ps1 -ErrorAction Stop | Out-Null; "
                     "'writable dir' } catch { 'locked dir' }")
def win_logon_secrets() -> str:
    """sbx logs on by itself (winget and the MSIX pwsh need a desktop session), so the probe is: the auto
    logon is sbx's and nobody else's; no password in Winlogon (HKLM or sbx's HKCU); the LSA secret that holds
    it is refused to sbx; no answer file at any drive root or under Panther/Sysprep; no optical drive."""
    from pickfit.verify.vbox_box import ANSWER_SCAN, LSA_TYPE

    return LSA_TYPE + ANSWER_SCAN + (
        "$w = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'\n"
        "\"autologon=$($w.AutoAdminLogon) user=$($w.DefaultUserName)\"\n"
        "\"hklm_password=$($w.PSObject.Properties.Name -contains 'DefaultPassword')\"\n"
        "$u = Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon' -ErrorAction SilentlyContinue\n"
        "\"hkcu_password=$([bool]($u -and $u.PSObject.Properties.Name -contains 'DefaultPassword'))\"\n"
        "\"lsa=$([PfLsa]::Probe('DefaultPassword'))\"\n"
        "\"answer_files=$($found -join ';')\"\n"
        "\"cdrom=$(@(Get-CimInstance Win32_CDROMDrive -ErrorAction SilentlyContinue).Count)\"\n")


WIN_LOGON_EXPECT = ["autologon=1 user=sbx", "hklm_password=False", "hkcu_password=False", "lsa=denied",
                    "answer_files=", "cdrom=0"]


def _no_logon_secret(r: ExecResult) -> bool:
    lines = [line.strip() for line in r.stdout.strip().splitlines()]
    return r.exit_code == 0 and lines == WIN_LOGON_EXPECT


def _as_admin(box: Box, name: str, script: str, expect: str, ok: Callable[[ExecResult], bool]) -> ProbeResult:
    """A control run by the harness's administrator (Windows PowerShell), never by the box user."""
    began = time.monotonic()
    code, out, err = box._admin(script, 120)  # type: ignore[attr-defined]
    result = ExecResult(command=script, exit_code=code, stdout=out, stderr=err,
                        seconds=round(time.monotonic() - began, 2), timed_out=False, truncated=False)
    return ProbeResult(name, bool(ok(result)), expect, code, result.seconds, _detail(result))


WIN_NEGATIVE_PASSWORD = "pickfit-negative-control"
WIN_WINLOGON = "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"


def _windows_probes(box: Box, add: Callable[[ProbeResult], None]) -> None:
    """A Windows box: the user is not an administrator, cannot change the harness, finds no logon password
    it can read, and the network policy (outside the guest) holds. Every probe has a control that shows it
    can see what it looks for (run as the administrator, or with the thing planted in this throwaway box).
    Windows has no per-user process, file-size or memory cap; the VM's own RAM and disk are the caps."""
    is_user = lambda r: r.stdout.strip().splitlines()[:1] == ["False"] and "S-1-" not in r.stdout  # noqa: E731
    add(_probe(box, "non_admin", WIN_IS_ADMIN, 60, "not an administrator, not elevated", is_user))
    add(_as_admin(box, "non_admin_control", WIN_IS_ADMIN, "the same check flags the administrator",
                  lambda r: r.exit_code == 0 and r.stdout.strip().splitlines()[:1] == ["True"] and not is_user(r)))
    add(_probe(box, "harness_locked", WIN_HARNESS_WRITE, 60, "the box user cannot change the harness scripts",
               lambda r: "writable" not in r.stdout and r.stdout.count("locked") == 3))
    add(_probe(box, "no_logon_secret", win_logon_secrets(), 90,
               "auto logon only for sbx; no Winlogon password; LSA secret denied to sbx; no answer file; no "
               "optical drive", _no_logon_secret))
    add(_as_admin(box, "no_logon_secret_control_admin", win_logon_secrets(),
                  "the administrator can read the LSA secret the box user is denied",
                  lambda r: re.search(r"^lsa=readable len=[1-9]\d*$", r.stdout, re.M) is not None))
    _as_admin(box, "plant", f"Set-ItemProperty {WIN_WINLOGON} DefaultPassword '{WIN_NEGATIVE_PASSWORD}'",
              "", lambda r: True)
    try:
        planted = box.exec(win_logon_secrets(), 90)
    finally:
        _as_admin(box, "unplant", f"Remove-ItemProperty {WIN_WINLOGON} DefaultPassword", "", lambda r: True)
    add(ProbeResult("no_logon_secret_control_planted", "hklm_password=True" in planted.stdout
                    and not _no_logon_secret(planted),
                    "with a DefaultPassword planted in Winlogon (this box only), the probe fails",
                    planted.exit_code, planted.seconds, _detail(planted)))
    no_secret_env = lambda r: not re.search(r"API_KEY|TOKEN|SECRET|PASSWORD", r.stdout)  # noqa: E731
    add(_probe(box, "no_secrets_in_env", "(Get-ChildItem env:).Name -join ' '", 60,
               "no API_KEY/TOKEN/SECRET/PASSWORD variables", no_secret_env))
    add(_probe(box, "no_secrets_in_env_control", "$env:PF_CONTROL_TOKEN = 'x'; (Get-ChildItem env:).Name -join ' '",
               60, "a planted *_TOKEN variable is seen", lambda r: not no_secret_env(r)))
    try:
        for name, ok, expect, detail in box.validate_containment():
            add(ProbeResult(name, ok, expect, None, 0.0, detail))
    except BoxError as err:
        add(ProbeResult("containment_check_ran", False, "the containment check completes", None, 0.0, str(err)))
    box.exec(box.background("python -m http.server 8765 --bind 127.0.0.1", 8765, 20, "limits-http"), 40)
    box.set_network(False)
    try:
        add(_probe(box, "offline_localhost",
                   "curl.exe -sS -m 5 -o NUL -w '%{http_code}' http://127.0.0.1:8765/", 30,
                   "localhost still answers with the network off", lambda r: r.stdout.strip() == "200"))
    finally:
        box.set_network(True)
    add(_probe(box, "online_again", "curl.exe -sS -I -m 15 -o NUL -w '%{http_code}' https://pypi.org/simple/pip/",
               40, "PyPI answers again after the network is back", lambda r: r.stdout.strip() == "200"))
    timed = box.exec("Start-Sleep 30", 3)
    add(ProbeResult("command_timeout", timed.timed_out and timed.seconds < 25, "Start-Sleep 30 killed at 3 s",
                    timed.exit_code, timed.seconds, _detail(timed)))
    quick = box.exec("Start-Sleep 1; 'done'", 15)
    add(ProbeResult("command_timeout_control", not quick.timed_out and quick.exit_code == 0 and "done" in quick.stdout,
                    "Start-Sleep 1 under a 15 s timeout finishes", quick.exit_code, quick.seconds, _detail(quick)))
    for code in (0, 1, 3, 93, 94, 1603):  # VBoxManage maps codes; the harness must report the real one
        add(_probe(box, f"exit_code_{code}", f"cmd /c exit {code}", 30, f"exit code {code} comes back as {code}",
                   lambda r, code=code: r.exit_code == code))
    # Last, since it changes the harness in this throwaway box: the same write test as the administrator.
    add(_as_admin(box, "harness_locked_control", WIN_HARNESS_WRITE, "the same write test succeeds for the administrator",
                  lambda r: r.stdout.count("writable") == 3))


def run_limits_test(box: Box, log: Callable[[str], None] = print) -> list[ProbeResult]:
    """Run every probe in a started box; restores the network before returning."""
    results: list[ProbeResult] = []

    def add(result: ProbeResult) -> None:
        results.append(result)
        log(f"  {'ok  ' if result.ok else 'FAIL'} {result.name}: {result.expect} · exit {result.exit_code} · "
            f"{result.seconds:.1f}s · {result.detail[:140]}")

    if box.os == "windows":
        _windows_probes(box, add)
        return results
    macos = box.os == "macos"
    if macos:
        add(_probe(box, "non_admin", "id -u; id -Gn; sudo -n true 2>&1; echo sudo=$?", 20,
                   "not root, not in admin, sudo refused", _not_admin))
        # The network policy is host-side (softnet); the box's own start checks containment holds even for
        # in-guest root. These probes keep the escalation surface small as defence in depth: the ways to
        # root the review found (2026-10-29) -- the image's admin/admin, su in a pty, sshd or VNC on
        # localhost, the auto-login password file, and the guest agent's binary.
        add(_probe(box, "admin_password", "dscl . -authonly admin admin", 20,
                   "admin's default password is gone", lambda r: r.exit_code != 0))
        add(_probe(box, "su_admin", SU_ADMIN, 30, "su admin with the default password fails",
                   lambda r: "PICKFIT_SU_OK" not in r.stdout.replace("echo PICKFIT_SU_OK", "")))
        add(_probe(box, "remote_login_closed",
                   "for p in 22 5900; do (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo \"open $p\"; done; true",
                   20, "nothing listens on localhost 22 or 5900", lambda r: "open" not in r.stdout))
        add(_probe(box, "kcpassword_unreadable", "cat /etc/kcpassword", 20,
                   "the auto-login password file is root-only", lambda r: r.exit_code != 0))
        add(_probe(box, "agent_binary_locked",
                   "for f in /usr/local/libexec/pickfit-agent /usr/local/libexec/pickfit-agent/tart-guest-agent "
                   "/Library/LaunchDaemons /Library/LaunchAgents; do test -w $f && echo \"writable $f\"; done; true",
                   20, "the box user cannot replace the guest agent or its launchd plists",
                   lambda r: "writable" not in r.stdout))
    else:
        add(_probe(box, "non_root", "id -u; grep CapEff /proc/self/status", 20,
                   "uid 1000, no effective capabilities",
                   lambda r: r.stdout.split()[:1] == ["1000"] and "CapEff:\t0000000000000000" in r.stdout))
    # The base image sets GPG_KEY (the public Python release key id); real secrets look like these.
    add(_probe(box, "no_secrets_in_env", "env | cut -d= -f1 | sort | tr '\\n' ' '", 20,
               "no API_KEY/TOKEN/SECRET/PASSWORD variables",
               lambda r: not re.search(r"API_KEY|TOKEN|SECRET|PASSWORD", r.stdout)))
    if macos:
        # Containment is host-side (softnet); prove it AS ROOT with a positive control (an open host port
        # answers with the block off, then drops with it on) and strict drops online and offline.
        try:
            for name, ok, expect, detail in box.validate_containment():
                add(ProbeResult(name, ok, expect, None, 0.0, detail))
        except BoxError as err:  # fail closed, loudly, if the containment check could not run
            add(ProbeResult("containment_check_ran", False, "the containment check completes", None, 0.0, str(err)))
    else:
        add(_probe(box, "internet", PYPI, 30, "PyPI answers 200", lambda r: r.stdout.strip() == "200"))
        add(_probe(box, "metadata_blocked", "curl -sS -m 5 http://169.254.169.254/latest/meta-data/", 20,
                   "169.254.169.254 unreachable", lambda r: r.exit_code != 0))
        add(_probe(box, "private_blocked", "curl -sS -m 5 http://10.0.0.1/", 20,
                   "10.0.0.1 unreachable", lambda r: r.exit_code != 0))
    box.exec(f"{box.detach} python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 < /dev/null & "
             "sleep 2", 20)
    box.set_network(False)
    try:
        if not macos:
            add(_probe(box, "offline_internet", PYPI, 30, "PyPI unreachable with the network off",
                       lambda r: r.stdout.strip() != "200"))
        add(_probe(box, "offline_localhost", "curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/",
                   20, "localhost still answers with the network off", lambda r: r.stdout.strip() == "200"))
    finally:
        box.set_network(True)
    if not macos:
        add(_probe(box, "online_again", PYPI, 30, "PyPI answers again after the network is back",
                   lambda r: r.stdout.strip() == "200"))
    timed = box.exec("sleep 30", 3)
    add(ProbeResult("command_timeout", timed.timed_out and timed.seconds < 15, "sleep 30 killed at 3 s",
                    timed.exit_code, timed.seconds, _detail(timed)))
    big = "dd if=/dev/zero of=big.bin bs=1m count=1700" if macos else "head -c 1700M /dev/zero > big.bin"
    add(_probe(box, "file_size_cap", f"{big}; code=$?; ls -l big.bin; rm -f big.bin; "
               "exit $code", 180, "a 1.7 GB file is cut off", lambda r: r.exit_code != 0))
    add(_probe(box, "process_cap",
               "python3 -c \"\nimport os, time\nn = 0\ntry:\n    while n < 2000:\n        if os.fork() == 0:\n"
               "            time.sleep(15); os._exit(0)\n        n += 1\nexcept OSError as e:\n"
               "    print('blocked after', n, e)\nelse:\n    print('forked', n)\n\"", 60,
               "fork stops before 2000 processes", lambda r: "blocked after" in r.stdout))
    if macos:
        return results
    # Last: on Modal the memory limit kills the whole sandbox, not just the process.
    expect = "3 GiB allocation fails"
    try:
        add(_probe(box, "memory_cap", "python3 -c \"b = bytearray(3 * 1024**3); print('allocated 3 GiB')\"", 90,
                   expect, lambda r: r.exit_code != 0 and "allocated" not in r.stdout))
    except BoxError as err:
        add(ProbeResult("memory_cap", True, expect, None, 0.0, f"the box itself was killed: {err}"))
    return results


def save_limits(results: list[ProbeResult], box: Box, runs_dir: Path) -> Path:
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    path = runs_dir / "verify" / f"limits-{box.runner}-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"runner": box.runner, "image": box.image, "start_s": getattr(box, "start_s", None),
               "checked_at": taipei_now().isoformat(timespec="seconds"),
               "passed": sum(r.ok for r in results), "total": len(results),
               "probes": [asdict(r) for r in results]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def limits_test(make_box: Callable[[str, str], Box], runs_dir: Path, log: Callable[[str], None] = print
                ) -> tuple[list[ProbeResult], Path]:
    began = time.monotonic()
    box = make_box(f"limits-{taipei_now().strftime('%Y%m%d-%H%M%S')}", "limits")
    try:
        box.start()
        log(f"limits test · {box.runner} · {box.image} · started in {getattr(box, 'start_s', None)}s")
        results = run_limits_test(box, log)
    finally:
        box.close()
    path = save_limits(results, box, runs_dir)
    log(f"limits test · {sum(r.ok for r in results)}/{len(results)} held · {time.monotonic() - began:.0f}s · {path}")
    return results, path
