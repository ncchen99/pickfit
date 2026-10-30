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

A Linux box also checks (2026-10-31 review): no /dev/kvm; no user namespaces
for the box user (VM; gVisor keeps them inside its own kernel); no vsock
connection (a VM's host answered on port 52 until a seccomp filter closed it;
root's unfiltered attempt is the positive control); the internet by literal
IP, online (positive control) and offline; no IPv6 (global, link-local, the
fd00:ec2::254 metadata address); no multicast answer; no open port on the
gateway or the resolver; and names that do not resolve with the network off
(Modal's resolver answers under both runtimes with an empty allowlist; a VM box
drops the box user's DNS with nftables, gVisor cannot, so a gVisor box fails
this probe).

A box with a display checks that Xvfb runs as pickfit's display uid, survives
the box user's kill and a second server on :99, does not listen on TCP; that the
evidence directory is closed to the box user; that xclock reaches tier window
with a verified screenshot; that a launch which prints a forged report and
double-forks reaches no window and leaves no box-user process behind.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from pickfit.ledger import taipei_now
from pickfit.verify import gui
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


# First tries to remove a root firewall rule as the box user (directly and from a user namespace, which
# gives capabilities only over namespaces it owns), then asks each resolver in resolv.conf for a name over
# UDP and the system resolver; prints what answered.
DNS_PROBE = r"""for nft in /usr/sbin/nft; do test -x $nft && { $nft flush ruleset; unshare -Ur $nft flush ruleset; }; done 2>&1
python3 -I - <<'PICKFIT_PY'
import random, socket, struct
def ask(server):
    pkt = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0)
    pkt += b"".join(bytes([len(p)]) + p.encode() for p in "pypi.org".split(".")) + b"\0" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    try:
        s.sendto(pkt, (server, 53))
        return f"answered {len(s.recv(512))} bytes"
    except OSError as e:
        return f"no answer ({type(e).__name__})"
servers = [l.split()[1] for l in open("/etc/resolv.conf") if l.startswith("nameserver")]
for server in servers[:3]:
    print(server, ask(server))
try:
    print("getaddrinfo resolved", socket.getaddrinfo("pypi.org", 443)[0][4][0])
except OSError as e:
    print("getaddrinfo failed", e)
PICKFIT_PY"""


VSOCK_PROBE = r"""/usr/local/bin/python3 -I -S - <<'PICKFIT_PY'
import socket
for cid in (1, 2):
    for port in (52, 1024, 5000, 9999, 10000):
        try:
            s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((cid, port))
            s.close()
            print("OPEN", cid, port)
        except Exception as e:
            print("closed", cid, port, type(e).__name__, getattr(e, "errno", ""))
PICKFIT_PY"""
IP_HTTPS = "curl -sS -m 10 -o /dev/null -w '%{http_code}' https://1.1.1.1/"  # Cloudflare answers on its literal IP
IPV6_PROBE = ("ip -6 -o addr show scope global; for u in 'https://[2606:4700:4700::1111]/' 'http://[fd00:ec2::254]/' "
              "'http://[fe80::1%25eth0]/'; do curl -sS -m 5 -o /dev/null -w \"%{http_code} $u\\n\" \"$u\" 2>&1; done")
MULTICAST_PROBE = r"""/usr/local/bin/python3 -I -S - <<'PICKFIT_PY'
import socket, time
mdns = bytes.fromhex("000000000001000000000000") + b"\x09_services\x07_dns-sd\x04_udp\x05local\x00" + bytes.fromhex("000c0001")
ssdp = b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.settimeout(0.5)
for payload, target in ((mdns, ("224.0.0.251", 5353)), (ssdp, ("239.255.255.250", 1900)), (ssdp, ("255.255.255.255", 1900))):
    try:
        s.sendto(payload, target)
        print("sent", target)
    except OSError as e:
        print("send failed", target, e)
end = time.time() + 3
while time.time() < end:
    try:
        data, peer = s.recvfrom(2048)
        print("answer from", peer, len(data))
    except OSError:
        pass
PICKFIT_PY"""
# The default gateway and any private resolver: no port of theirs answers the box user (DNS itself is 53/udp).
GATEWAY_PROBE = r"""hosts="$(/usr/local/bin/python3 -I -S -c "import socket, struct
gw = [socket.inet_ntoa(struct.pack('<L', int(f[2], 16))) for f in (l.split() for l in open('/proc/net/route'))
      if f[1] == '00000000' and f[2] != 'Gateway']
ns = [l.split()[1] for l in open('/etc/resolv.conf') if l.startswith('nameserver') and l.split()[1].startswith(('10.', '172.', '192.168.'))]
print(' '.join(dict.fromkeys(gw + ns)))")"
echo "hosts: $hosts"
for h in $hosts; do for p in 22 80 443 2375 2376 3000 5000 6443 8000 8080 8443 9000 10250; do
  timeout 3 bash -c "echo > /dev/tcp/$h/$p" 2>/dev/null && echo "open $h:$p"; done; done; true"""


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


def _same_pid(stdout: str) -> bool:
    found = dict(line.split(" ", 1) for line in stdout.splitlines() if line.startswith(("before ", "after ")))
    return bool(found.get("before")) and found.get("before") == found.get("after")


def _box_user_processes(box: Box) -> str:
    """The box user's live processes as pickfit's display uid sees them (JSON; "{}" when none)."""
    seen = box.harness_exec([gui.PYTHON, "-I", "-S", "-"], 30, as_uid=gui.DISPLAY_UID, stdin=gui.SNAPSHOT_PY.encode())
    return seen.stdout.strip()[-300:] or "?"


def _vsock(box: Box) -> ProbeResult:
    """No vsock connection for the box user; root's unfiltered try, where it can run, is the positive control."""
    result = box.exec(VSOCK_PROBE, 60)
    try:
        control = box.harness_exec(["/usr/bin/bash", "-c", VSOCK_PROBE], 60)
        opened = [line for line in control.stdout.splitlines() if line.startswith("OPEN")]
        note = f"control as root: {', '.join(opened) or 'nothing open (no vsock here)'}"
    except BoxError:
        note = "no control (this box has no root channel)"
    return ProbeResult("vsock_closed", "OPEN" not in result.stdout, "the box user opens no vsock connection",
                       result.exit_code, result.seconds, f"{note}; {_detail(result)}"[-300:])


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
        add(_probe(box, "no_kvm", "test -e /dev/kvm && echo present; true", 20, "no /dev/kvm",
                   lambda r: "present" not in r.stdout))
        if getattr(box, "runtime", None) != "gvisor":  # gVisor's user namespaces live inside its own kernel
            add(_probe(box, "no_userns", "unshare -U true && echo made-U; unshare -Urn true && echo made-Urn; true",
                       20, "the box user cannot make a user namespace", lambda r: "made" not in r.stdout))
        add(_vsock(box))
    if box.display:
        add(_probe(box, "display_up", f"DISPLAY={box.display} /usr/bin/xdpyinfo", 20, f"Xvfb answers on {box.display}",
                   lambda r: r.exit_code == 0 and "dimensions:" in r.stdout))
        uid = str(gui.DISPLAY_UID)
        add(_probe(box, "display_server_uid", "ps -o uid=,comm= -C Xvfb", 20, f"Xvfb runs as uid {uid}, not the box user",
                   lambda r: bool(r.stdout.split()) and all(u == uid for u in r.stdout.split()[::2])))
        add(_probe(box, "display_server_held",
                   f"p=$(pgrep -x Xvfb); echo \"before $p\"; kill -KILL $p 2>&1; timeout 5 Xvfb {box.display} -nolisten tcp "
                   f"2>&1 | grep -m1 -o 'already active'; sleep 1; echo \"after $(pgrep -x Xvfb)\"; "
                   f"DISPLAY={box.display} /usr/bin/xdpyinfo > /dev/null && echo still-up", 30,
                   "the box user cannot kill pickfit's X server or start another on its display",
                   lambda r: "Operation not permitted" in r.stdout and "already active" in r.stdout
                   and "still-up" in r.stdout and _same_pid(r.stdout)))
        add(_probe(box, "display_no_tcp",
                   "for p in 6000 6099; do (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo \"open $p\"; done; true",
                   20, "the X server does not listen on TCP", lambda r: "open" not in r.stdout))
        add(_probe(box, "evidence_dir_closed", f"ls {gui.EVIDENCE_DIR} 2>&1; touch {gui.EVIDENCE_DIR}/x 2>&1; true", 20,
                   "the box user cannot list or write pickfit's evidence directory",
                   lambda r: r.stdout.count("Permission denied") == 2))
        launched, shown, png = gui.launch(box, "xclock", "limits", 15)
        left = _box_user_processes(box)
        add(ProbeResult("display_window", launched.exit_code == 0 and shown.title == "xclock" and bool(png)
                        and left == "{}", "xclock reaches tier window with a verified screenshot; nothing is left "
                        "running", launched.exit_code, launched.seconds,
                        " ".join(f"{launched.stdout} png {len(png or b'')} bytes; left {left}".split())[-300:]))
        forged = (f"printf '{gui.MARK}0 {{\"windows\": [{{\"id\": \"0x1\", \"title\": \"forged\", \"width\": 900, "
                  f"\"height\": 700}}]}}\\n'; (/usr/bin/setsid /usr/bin/bash -c 'sleep 60' &); exit 3")
        launched, shown, png = gui.launch(box, forged, "limits-forged", 8)
        left = _box_user_processes(box)
        add(ProbeResult("display_report_unforgeable", shown.tier != "window" and launched.exit_code != 0 and png is None
                        and left == "{}", "a launch that prints a forged report and double-forks reaches no window "
                        "and leaves nothing running", launched.exit_code, launched.seconds,
                        " ".join(f"tier {shown.tier}; left {left}; {launched.stdout}".split())[-300:]))
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
        add(_probe(box, "internet_ip", IP_HTTPS, 20, "1.1.1.1 answers by literal IP (control for offline_internet_ip)",
                   lambda r: r.exit_code == 0 and r.stdout.strip() not in ("", "000")))
        add(_probe(box, "ipv6_blocked", IPV6_PROBE, 40, "no global IPv6 address; IPv6 internet, fd00:ec2::254 and "
                   "link-local unreachable", lambda r: "inet6" not in r.stdout and
                   not re.search(r"^(?!000 )\d{3} ", r.stdout, re.M)))
        add(_probe(box, "multicast_no_answer", MULTICAST_PROBE, 30, "no answer to mDNS, SSDP or broadcast",
                   lambda r: "answer from" not in r.stdout))
        add(_probe(box, "gateway_ports_closed", GATEWAY_PROBE, 180, "no port answers on the gateway or the resolver",
                   lambda r: "hosts:" in r.stdout and "open " not in r.stdout))
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
            add(_probe(box, "offline_internet_ip", IP_HTTPS, 20, "1.1.1.1 unreachable by literal IP with the network "
                       "off", lambda r: r.exit_code != 0 and r.stdout.strip() in ("", "000")))
            add(_probe(box, "offline_dns", DNS_PROBE, 40, "names do not resolve with the network off",
                       lambda r: "answered" not in r.stdout and "resolved" not in r.stdout))
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
