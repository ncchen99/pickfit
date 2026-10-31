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

A Linux box also checks (2026-10-31 review): no /dev/kvm; no user namespaces
for the box user (VM; gVisor keeps them inside its own kernel); no vsock
connection (a VM's host answered on port 52 until a seccomp filter closed it;
root's unfiltered attempt is the positive control); the internet by literal
IP, online (positive control) and offline; no IPv6 (global, link-local, the
fd00:ec2::254 metadata address); no multicast answer; no open port on the
gateway or the resolver; and names that resolve online (positive control) but
not with the network off (Modal's resolver answers under both runtimes with an
empty allowlist: a VM box drops the box user's DNS with nftables; a gVisor box
runs the box user in its own network namespace and cuts that namespace's only
uplink, measured 2026-10-31). A gVisor box also checks, offline, that the box
user cannot enter the box's own network namespace or the uplink's, signal the
uplink's uid or add a route, and that only the namespace's holder is left of
that uid (no uplink runs).

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


# The box user tries to leave its network namespace, signal NET_UID's processes (the namespace's holder, and the
# uplink while online) and add a route; lists NET_UID's processes as "net_uid PID COMM". Inside the namespace
# NET_UID is uid 0 (the box's real root is unmapped there and shows as 65534).
NETNS_PROBE = r"""ip route add 1.1.1.1/32 dev lo 2>/dev/null && echo ROUTED
nsenter --net=/proc/1/ns/net true 2>/dev/null && echo "ENTERED the box's own namespace"
for p in $(pgrep -u 0); do echo "net_uid $p $(cat /proc/$p/comm 2>/dev/null)"
  kill -0 "$p" 2>/dev/null && echo "SIGNALS $p"
  nsenter --target="$p" --net true 2>/dev/null && echo "ENTERED net of $p"
  nsenter --target="$p" --user --net true 2>/dev/null && echo "ENTERED user and net of $p"; done; true"""


# The X server's TCP ports from its own network namespace (the display uid's commands run there); prints the
# namespace it ran in and Xvfb's.
XPORTS_PY = r"""import os, socket, sys
print("ns", os.readlink("/proc/self/ns/net"), os.readlink(f"/proc/{sys.argv[1]}/ns/net"))
for host, family in (("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)):
    for port in (6000, 6099):
        s = socket.socket(family)
        s.settimeout(3)
        try:
            s.connect((host, port))
            print("open", host, port)
        except OSError as e:
            print("closed", host, port, e.errno)
        finally:
            s.close()
"""
# Asks each resolver in resolv.conf for a name over UDP and resolves argv's names; prints its network namespace.
NAMES_PY = r"""import os, random, socket, struct, sys
print("ns", os.readlink("/proc/self/ns/net"))
q = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0) + b"\x04pypi\x03org\x00" + struct.pack(">HH", 1, 1)
for server in [l.split()[1] for l in open("/etc/resolv.conf") if l.startswith("nameserver")][:3]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(q, (server, 53))
        s.recv(512)
        print("answered", server)
    except OSError as e:
        print("no answer", server, type(e).__name__)
for name in sys.argv[1:]:
    try:
        print("resolved", name, socket.getaddrinfo(name, 7100, socket.AF_INET)[0][4][0])
    except OSError as e:
        print("unresolved", name, e)
"""
# Names only DNS resolves (to 127.0.0.1): a font server's name the box user can hand to Xvfb.
FONT_NAMES = ("127.0.0.1.nip.io", "127.0.0.1.sslip.io")
# The box user, as a raw X client: SetFontPath (opcode 51) with each argv element, then a round trip to read the
# answer ("accepted" or "error N"), then the default path back. No xset in the image, and none needed. Xvfb refuses
# an unreachable font server whether or not it resolved the name, so the answer is recorded, not judged.
SET_FONT_PATH = r"""python3 -I - "$@" <<'PICKFIT_PY'
import socket, struct, sys
def exact(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise SystemExit("the X server closed the connection")
        b += c
    return b
s = None
for addr in ("\0/tmp/.X11-unix/X99", "/tmp/.X11-unix/X99"):
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(60)
        s.connect(addr)
        break
    except OSError:
        s = None
if s is None:
    raise SystemExit("no X connection")
s.sendall(struct.pack("<BxHHHHxx", 0x6C, 11, 0, 0, 0))
head = exact(s, 8)
if head[0] != 1:
    raise SystemExit(f"X refused the connection ({head[0]})")
exact(s, 4 * struct.unpack("<H", head[6:8])[0])
def font_path(elements):
    body = b"".join(bytes([len(e)]) + e.encode() for e in elements)
    body += b"\0" * (-len(body) % 4)
    s.sendall(struct.pack("<BxHHxx", 51, 2 + len(body) // 4, len(elements)) + body + struct.pack("<BxH", 43, 1))
    error = None
    while True:  # up to the round trip's reply, so an error does not leave it for the next request
        packet = exact(s, 32)
        if packet[0] == 0 and error is None:
            error = f"error {packet[1]}"
        elif packet[0] == 1:
            exact(s, 4 * struct.unpack("<I", packet[4:8])[0])
            return error or "accepted"
for element in sys.argv[1:]:
    print("font path", element, font_path([element]), flush=True)
print("font path reset", font_path([]))
PICKFIT_PY"""


VSOCK_PROBE = r"""/usr/local/bin/python3 -I -S - <<'PICKFIT_PY'
import os, socket
for fd in sorted(os.listdir("/proc/self/fd"), key=int):
    try:
        s = socket.socket(fileno=int(fd))
    except OSError:
        continue
    if s.family == getattr(socket, "AF_VSOCK", 40):
        print("inherited vsock fd", fd)
    s.detach()
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
IO_URING_PROBE = r"""/usr/local/bin/python3 -I -S - <<'PICKFIT_PY'
import ctypes
libc = ctypes.CDLL(None, use_errno=True)
params = ctypes.create_string_buffer(120)
fd = libc.syscall(425, 4, params)
print("io_uring fd", fd) if fd >= 0 else print("io_uring refused errno", ctypes.get_errno())
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
# The default gateway and any private resolver, as whoever runs it sees them.
HOSTS_PY = """import socket, struct
gw = [socket.inet_ntoa(struct.pack('<L', int(f[2], 16))) for f in (l.split() for l in open('/proc/net/route'))
      if f[1] == '00000000' and f[2] != 'Gateway']
ns = [l.split()[1] for l in open('/etc/resolv.conf') if l.startswith('nameserver') and l.split()[1].startswith(('10.', '172.', '192.168.'))]
print(' '.join(dict.fromkeys(gw + ns)))"""
# Those the box user sees, plus {extra} (the box's real ones as root reads them: a gVisor box user sees its uplink's
# 10.0.2.2, and reaches the real gateway through the uplink while online).
GATEWAY_PROBE = r"""hosts="$(/usr/local/bin/python3 -I -S -c "{hosts_py}") {extra}"
hosts="$(echo $hosts | tr ' ' '\n' | awk '!seen[$0]++' | tr '\n' ' ')"
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


def _hosts(stdout: str) -> list[str]:
    line = next((line for line in stdout.splitlines() if line.startswith("hosts:")), "")
    return line.split()[1:]


def _refused_97(stdout: str) -> bool:
    """Every connection the vsock probe tried failed with EAFNOSUPPORT (97), and it tried some."""
    tries = [line.split() for line in stdout.splitlines() if line.startswith(("OPEN", "closed"))]
    return bool(tries) and all(t[0] == "closed" and t[-1] == "97" for t in tries)


def _vsock(box: Box) -> ProbeResult:
    """The box user gets EAFNOSUPPORT for every vsock connection and inherits no vsock fd. Decided by root's
    unfiltered try: a port root can open (the filter is what stops the box user), or EAFNOSUPPORT for root too
    (the kernel has no vsock, as in gVisor). Without that control the probe fails."""
    result = box.exec(VSOCK_PROBE, 60)
    user_ok = _refused_97(result.stdout) and "inherited vsock" not in result.stdout
    try:
        control = box.harness_exec(["/usr/bin/bash", "-c", VSOCK_PROBE], 60)
        opened = [line for line in control.stdout.splitlines() if line.startswith("OPEN")]
        decisive = bool(opened) or _refused_97(control.stdout)
        note = f"control as root: {', '.join(opened) or ('no vsock in this kernel' if decisive else 'inconclusive')}"
    except BoxError:
        decisive, note = False, "no control (this box has no root channel)"
    return ProbeResult("vsock_closed", user_ok and decisive, "the box user opens no vsock connection (EAFNOSUPPORT) "
                       "and inherits none; root's try decides", result.exit_code, result.seconds,
                       f"{note}; {_detail(result)}"[-300:])


def _userns(box: Box) -> ProbeResult:
    """The box user cannot make a user namespace; the control is the sysctl root set (0)."""
    result = box.exec("unshare -U true && echo made-U; unshare -Urn true && echo made-Urn; true", 20)
    try:
        limit = box.harness_exec(["/usr/bin/cat", "/proc/sys/user/max_user_namespaces"], 20).stdout.strip()
    except BoxError:
        limit = "unknown (no root channel)"
    return ProbeResult("no_userns", "made" not in result.stdout and limit == "0",
                       "the box user cannot make a user namespace; user.max_user_namespaces reads 0",
                       result.exit_code, result.seconds, f"max_user_namespaces {limit}; {_detail(result)}"[-300:])


def _netns_held(result: ExecResult) -> bool:
    """Nothing of the box user's got out, and NET_UID's only process is the namespace's holder (sleep): there was
    something to try, and no uplink runs."""
    held = [line.split(None, 2) for line in result.stdout.splitlines() if line.startswith("net_uid ")]
    return (bool(held) and all(h[2:] == ["sleep"] for h in held)
            and not re.search(r"^(ROUTED|ENTERED|SIGNALS)", result.stdout, re.M))


def _display_uid(box: Box) -> ProbeResult:
    """Xvfb runs as the display uid as root sees it, and not as the box user as the box user sees it (a gVisor box's
    namespace does not map the display uid: the box user sees 65534 there)."""
    uid = str(gui.DISPLAY_UID)
    result = box.exec("ps -o uid=,comm= -C Xvfb", 20)
    try:
        seen = box.harness_exec(["/usr/bin/ps", "-o", "uid=,comm=", "-C", "Xvfb"], 20).stdout.split()[::2]
    except BoxError:
        seen = []
    ok = bool(seen) and all(u == uid for u in seen) and "1000" not in result.stdout.split()[::2]
    return ProbeResult("display_server_uid", ok, f"Xvfb runs as uid {uid} (root's view), not the box user",
                       result.exit_code, result.seconds, f"root sees uids {' '.join(seen) or 'none'}; {_detail(result)}")


def _display_no_tcp(box: Box) -> ProbeResult:
    """The X server listens on no TCP port: neither on the box user's loopback nor on its own (from its own network
    namespace, where the display uid's commands run)."""
    user = box.exec("for p in 6000 6099; do (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo \"open $p\"; done; true",
                    20)
    own = box.harness_exec([gui.PYTHON, "-I", "-S", "-", str(box.xvfb_pid)], 30, as_uid=gui.DISPLAY_UID,
                           stdin=XPORTS_PY.encode())
    ns = next((line.split()[1:] for line in own.stdout.splitlines() if line.startswith("ns ")), [])
    ok = ("open" not in user.stdout and len(ns) == 2 and ns[0] == ns[1] and "closed" in own.stdout
          and "open" not in own.stdout)
    return ProbeResult("display_no_tcp", ok, "the X server does not listen on TCP (from the box user's loopback and "
                       "from its own network namespace)", user.exit_code, user.seconds,
                       f"box user: {_detail(user) or 'nothing open'}; Xvfb's view: {_detail(own)}"[-300:])


def _display_no_network(box: Box) -> ProbeResult:
    """Offline: the display has no network, so the box user cannot use Xvfb to resolve a name (a font server's, by
    SetFontPath, which the box user sends). Decided by root: Xvfb's network namespace is neither the box's nor the
    box user's, and from it the display uid gets no DNS answer and resolves no name, while root's same lookups
    answer (the control). Xvfb's answer to SetFontPath is kept in the detail: it refuses an unreachable font
    server whether or not it resolved the name."""
    names = " ".join(FONT_NAMES)
    control = box.harness_exec([gui.PYTHON, "-I", "-S", "-", *FONT_NAMES], 40, stdin=NAMES_PY.encode())
    name = next((line.split()[1] for line in control.stdout.splitlines()
                 if line.startswith("resolved ") and line.split()[2:3] == ["127.0.0.1"]), None)
    own = box.harness_exec([gui.PYTHON, "-I", "-S", "-", *FONT_NAMES], 40, as_uid=gui.DISPLAY_UID,
                           stdin=NAMES_PY.encode())
    xvfb_ns = box.harness_exec(["/usr/bin/readlink", f"/proc/{box.xvfb_pid}/ns/net", "/proc/1/ns/net"],
                               20).stdout.split()
    user_ns = box.exec("readlink /proc/self/ns/net", 20).stdout.strip()
    own_ns = next((line.split()[1] for line in own.stdout.splitlines() if line.startswith("ns ")), "")
    asked = box.exec(f"set -- {' '.join(f'tcp/{n}:7100' for n in FONT_NAMES)}\n{SET_FONT_PATH}", 90)
    apart = len(xvfb_ns) == 2 and xvfb_ns[0] != xvfb_ns[1] and xvfb_ns[0] != user_ns and own_ns == xvfb_ns[0]
    decisive = bool(re.search(r"^answered ", control.stdout, re.M)) and name is not None
    closed = (not re.search(r"^(answered|resolved) ", own.stdout, re.M)
              and bool(re.search(r"^unresolved ", own.stdout, re.M)))
    ran = "font path tcp/" in asked.stdout
    detail = (f"Xvfb ns {xvfb_ns[:1]} box {xvfb_ns[1:]} box user {user_ns}; control (root): {_detail(control)}; "
              f"display: {_detail(own)}; box user's SetFontPath: {_detail(asked)}")
    return ProbeResult("display_no_network", apart and decisive and closed and ran,
                       f"offline, after the box user's SetFontPath for those names, Xvfb's namespace has no network: no "
                       f"DNS answer or name ({names}) from it, root's control answers", asked.exit_code, asked.seconds,
                       detail[-300:])


def _gateway(box: Box) -> ProbeResult:
    """No port answers the box user on the gateway or a private resolver: the ones it sees and the box's real ones as
    root reads them. A box with no root channel checks only its own view."""
    try:
        real = box.harness_exec([gui.PYTHON, "-I", "-S", "-c", HOSTS_PY], 20).stdout.split()
        note, rooted = f"root sees {' '.join(real) or 'none'}", True
    except BoxError:
        real, note, rooted = [], "no root view", False
    result = box.exec(GATEWAY_PROBE.format(hosts_py=HOSTS_PY, extra=" ".join(real)), 180)
    hosts = _hosts(result.stdout)
    ok = bool(hosts) and "open " not in result.stdout and (not rooted or (bool(real) and set(real) <= set(hosts)))
    return ProbeResult("gateway_ports_closed", ok, "no port answers on the gateway or the resolver, as the box user "
                       "sees them and as root does (at least one found)", result.exit_code, result.seconds,
                       f"{note}; {_detail(result)}"[-300:])


def _not_admin(result: ExecResult) -> bool:
    lines = result.stdout.splitlines()
    groups = lines[1].split() if len(lines) > 1 else ["?"]
    return lines[:1] != ["0"] and "admin" not in groups and "sudo=0" not in result.stdout


# The token, as whoami sees it: administrator role, every BUILTIN group (S-1-5-32-*), every privilege, and the
# integrity level. The box user must be in BUILTIN\Users only (Backup Operators and the like can read the
# SECURITY hive), hold none of the privileges that lead to SYSTEM, and run at Medium integrity.
WIN_IS_ADMIN = (
    "$g = whoami /groups /fo csv | ConvertFrom-Csv\n"
    "\"admin=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())"
    ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))\"\n"
    "\"builtin=$(($g | Where-Object SID -like 'S-1-5-32-*' | ForEach-Object SID | Sort-Object) -join ',')\"\n"
    "\"integrity=$(($g | Where-Object SID -like 'S-1-16-*' | ForEach-Object SID) -join ',')\"\n"
    "\"privileges=$((whoami /priv /fo csv | ConvertFrom-Csv | ForEach-Object 'Privilege Name' | Sort-Object) "
    "-join ',')\"\n")
# An allowlist: what a standard Windows user holds. Anything else (SeBackup, SeRestore, SeDebug, SeImpersonate,
# SeTcb, SeCreateToken, SeAssignPrimaryToken, SeManageVolume, SeRelabel, ...) fails the probe.
WIN_USER_PRIVILEGES = frozenset({"SeChangeNotifyPrivilege", "SeShutdownPrivilege", "SeUndockPrivilege",
                                 "SeIncreaseWorkingSetPrivilege", "SeTimeZonePrivilege"})


def _win_token(r: ExecResult) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^(\w+)=(.*)$", r.stdout, re.M)}


def _win_privileges(r: ExecResult) -> set[str]:
    return set(filter(None, _win_token(r).get("privileges", "").split(",")))


def _win_standard_user(r: ExecResult) -> bool:
    t = _win_token(r)
    privileges = _win_privileges(r)
    return (r.exit_code == 0 and t.get("admin") == "False" and t.get("builtin") == "S-1-5-32-545"
            and t.get("integrity") == "S-1-16-8192" and "SeChangeNotifyPrivilege" in privileges
            and privileges <= WIN_USER_PRIVILEGES)


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


# Windows PowerShell logs each command line (events 400/403) where any user can read it; the harness passes
# scripts and secrets in the environment, so no command line there carries one.
WIN_ENCODED_IN_LOG = ("$e = @(Get-WinEvent -LogName 'Windows PowerShell' -ErrorAction Stop)\n"
                      "\"events=$($e.Count) encoded=$(@($e | Where-Object Message -match "
                      "'EncodedCommand|\\s-Enc\\s').Count)\"\n")


def _no_encoded(r: ExecResult) -> bool:
    m = re.search(r"events=(\d+) encoded=(\d+)", r.stdout)
    return r.exit_code == 0 and m is not None and int(m.group(1)) > 0 and m.group(2) == "0"


WIN_NEGATIVE_PASSWORD = "pickfit-negative-control"
WIN_WINLOGON = "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"


def _windows_probes(box: Box, add: Callable[[ProbeResult], None]) -> None:
    """A Windows box: the user is not an administrator, cannot change the harness, finds no logon password
    it can read, and the network policy (outside the guest) holds. Every probe has a control that shows it
    can see what it looks for (run as the administrator, or with the thing planted in this throwaway box).
    Windows has no per-user process, file-size or memory cap; the VM's own RAM and disk are the caps."""
    add(_probe(box, "non_admin", WIN_IS_ADMIN, 60,
               "not an administrator; BUILTIN groups exactly Users; Medium integrity; privileges only from "
               + ", ".join(sorted(WIN_USER_PRIVILEGES)) + " (SeChangeNotify present)", _win_standard_user))
    add(_as_admin(box, "non_admin_control", WIN_IS_ADMIN,
                  "the same check flags the administrator (admin=True, S-1-5-32-544, SeDebug and SeBackup parsed)",
                  lambda r: r.exit_code == 0 and _win_token(r).get("admin") == "True"
                  and "S-1-5-32-544" in _win_token(r).get("builtin", "")
                  and {"SeDebugPrivilege", "SeBackupPrivilege"} <= _win_privileges(r) and not _win_standard_user(r)))
    add(_probe(box, "harness_locked", WIN_HARNESS_WRITE, 60, "the box user cannot change the harness scripts",
               lambda r: "writable" not in r.stdout and r.stdout.count("locked") == 3))
    add(_probe(box, "no_logon_secret", win_logon_secrets(), 90,
               "auto logon only for sbx; no Winlogon password; LSA secret denied to sbx; no answer file; no "
               "optical drive", _no_logon_secret))
    add(_as_admin(box, "no_logon_secret_control_admin", win_logon_secrets(),
                  "the administrator can read the LSA secret the box user is denied",
                  lambda r: re.search(r"^lsa=readable len=[1-9]\d*\r?$", r.stdout, re.M) is not None))
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
    add(_probe(box, "no_encoded_commands_in_log", WIN_ENCODED_IN_LOG, 90,
               "the 'Windows PowerShell' log is readable and no command line in it carries a script",
               _no_encoded))
    planted_cmd = ("& \"$env:SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoProfile "
                   "-EncodedCommand VwByAGkAdABlAC0ATwB1AHQAcAB1AHQAIABwAGYALQBjAG8AbgB0AHIAbwBsAA==")
    _as_admin(box, "plant", planted_cmd, "", lambda r: True)  # Write-Output pf-control
    add(_probe(box, "no_encoded_commands_in_log_control", WIN_ENCODED_IN_LOG, 90,
               "after the administrator runs one -EncodedCommand (this box only), the probe sees it",
               lambda r: r.exit_code == 0 and not _no_encoded(r)))
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
        add(_probe(box, "no_kvm", "test -e /dev/kvm && echo present; true", 20, "no /dev/kvm",
                   lambda r: "present" not in r.stdout))
        if getattr(box, "runtime", None) != "gvisor":  # gVisor's user namespaces and io_uring are its own
            add(_userns(box))
            add(_probe(box, "no_io_uring", IO_URING_PROBE, 20, "the box user cannot set up io_uring",
                       lambda r: "io_uring refused" in r.stdout))
        add(_vsock(box))
    if box.display:
        add(_probe(box, "display_up", f"DISPLAY={box.display} /usr/bin/xdpyinfo", 20, f"Xvfb answers on {box.display}",
                   lambda r: r.exit_code == 0 and "dimensions:" in r.stdout))
        add(_display_uid(box))
        add(_probe(box, "display_server_held",
                   f"p=$(pgrep -x Xvfb); echo \"before $p\"; kill -KILL $p 2>&1; timeout 5 Xvfb {box.display} -nolisten tcp "
                   f"2>&1 | grep -m1 -o 'already active'; sleep 1; echo \"after $(pgrep -x Xvfb)\"; "
                   f"DISPLAY={box.display} /usr/bin/xdpyinfo > /dev/null && echo still-up", 30,
                   "the box user cannot kill pickfit's X server or start another on its display",
                   lambda r: "Operation not permitted" in r.stdout and "already active" in r.stdout
                   and "still-up" in r.stdout and _same_pid(r.stdout)))
        add(_display_no_tcp(box))
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
        ran = shown.alive and "sleep" in shown.processes  # the control: the double-forked child was running
        add(ProbeResult("display_report_unforgeable", ran and shown.tier != "window" and launched.exit_code != 0
                        and png is None and left == "{}", "a launch that prints a forged report and double-forks "
                        "(its child seen running) reaches no window and leaves nothing running",
                        launched.exit_code, launched.seconds,
                        " ".join(f"tier {shown.tier}; child running {ran}; left {left}; {launched.stdout}".split())[-300:]))
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
        add(_probe(box, "online_dns", DNS_PROBE, 40, "names resolve with the network on (control for offline_dns)",
                   lambda r: "answered" in r.stdout and "resolved" in r.stdout))
        add(_probe(box, "ipv6_blocked", IPV6_PROBE, 40, "no global IPv6 address; IPv6 internet, fd00:ec2::254 and "
                   "link-local unreachable", lambda r: "inet6" not in r.stdout and
                   not re.search(r"^(?!000 )\d{3} ", r.stdout, re.M)))
        add(_probe(box, "multicast_no_answer", MULTICAST_PROBE, 30, "no answer to mDNS, SSDP or broadcast",
                   lambda r: "answer from" not in r.stdout))
        add(_gateway(box))
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
        if box.display:
            add(_display_no_network(box))
        if getattr(box, "runtime", None) == "gvisor":
            add(_probe(box, "netns_held", NETNS_PROBE, 30, "offline, the box user cannot leave "
                       "its network namespace, signal the uplink's uid or add a route; only the holder runs as it",
                       _netns_held))
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
