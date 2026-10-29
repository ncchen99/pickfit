"""`pickfit verify --limits-test`: check a box's guard rails with real commands.

Each probe runs in one fresh box and says whether the limit held: the box
user has no capabilities, cloud metadata and private ranges are unreachable,
the network cut blocks the internet but not localhost and can be undone, a
command is killed at its timeout, and file size, process count and memory are
capped. No model is called. Measured 2026-10-29: Docker kills only the process
that goes over the memory limit; Modal kills the whole sandbox. A macOS box has
no /proc and no per-process memory cap (the VM's RAM is the cap), so it checks
instead that the box user is not an admin, cannot sudo or change the firewall,
and cannot reach the host.
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


def run_limits_test(box: Box, log: Callable[[str], None] = print) -> list[ProbeResult]:
    """Run every probe in a started box; restores the network before returning."""
    results: list[ProbeResult] = []

    def add(result: ProbeResult) -> None:
        results.append(result)
        log(f"  {'ok  ' if result.ok else 'FAIL'} {result.name}: {result.expect} · exit {result.exit_code} · "
            f"{result.seconds:.1f}s · {result.detail[:140]}")

    macos = box.os == "macos"
    if macos:
        add(_probe(box, "non_admin", "id -u; id -Gn; sudo -n true 2>&1; echo sudo=$?", 20,
                   "not root, not in admin, sudo refused", _not_admin))
        add(_probe(box, "firewall_locked", "pfctl -d", 20, "the box user cannot turn pf off",
                   lambda r: r.exit_code != 0))
        # The ways to root the review found (2026-10-29): the image's admin/admin, su in a pty, sshd or
        # VNC on localhost (pf skips lo0), the auto-login password file, and the guest agent's binary.
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
    add(_probe(box, "internet", PYPI, 30, "PyPI answers 200", lambda r: r.stdout.strip() == "200"))
    add(_probe(box, "metadata_blocked", "curl -sS -m 5 http://169.254.169.254/latest/meta-data/", 20,
               "169.254.169.254 unreachable", lambda r: r.exit_code != 0))
    add(_probe(box, "private_blocked", "curl -sS -m 5 http://10.0.0.1/", 20,
               "10.0.0.1 unreachable", lambda r: r.exit_code != 0))
    if macos:  # dropped, not refused: a refusal would mean the packet reached the host
        add(_probe(box, "host_blocked", "curl -sS -m 5 http://$(route -n get default | awk '/gateway/ {print $2}'):22/",
                   20, "the host (the VM's gateway) times out", lambda r: r.exit_code == 28))
    box.exec(f"{box.detach} python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 < /dev/null & "
             "sleep 2", 20)
    box.set_network(False)
    try:
        add(_probe(box, "offline_internet", PYPI, 30, "PyPI unreachable with the network off",
                   lambda r: r.stdout.strip() != "200"))
        add(_probe(box, "offline_localhost", "curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/",
                   20, "localhost still answers with the network off", lambda r: r.stdout.strip() == "200"))
    finally:
        box.set_network(True)
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
