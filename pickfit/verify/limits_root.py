"""The limits test of a full-privilege VM box (root_box.RootVmBox): `pickfit verify --runtime rootvm --limits-test`.

limits.py checks that a box user is held inside limits root sets. In this box the box user is root, so those
probes would all read wrong, and what has to be checked is the other side: that everything holding the machine is
outside it. Every probe here runs its commands as root (the box user's sudo), because root is what the software
under test may be. No model is called.

What is checked, and what each reading rests on:

- The box is what it says: sudo gives uid 0, systemd is PID 1 and starts a unit, the container engine runs a
  container, a kernel module loads, /dev/net/tun and /dev/fuse are there, a raw socket opens (and the extra disk,
  when one was asked for, can be formatted and mounted and is not the system's).
- No identity. Root gets no answer from the metadata service on any of its addresses, and still none after doing
  what root can do to the VM's own network settings. The provider says the same from outside: endpoint off, no
  instance profile, no key pair, every volume deleted with the instance.
- No credentials on disk: root's scan of the places a secret would be finds no cloud key, no private key but the
  VM's own SSH host key, and no secret-looking variable in root's, PID 1's or the box user's environment. The
  control plants a key id in this throwaway VM and the same scan finds it.
- Only the allowed egress: as root, TCP 80 and 443 open to public addresses and the listed resolver answers, while
  SMTP (25, 465, 587), SSH (22), DNS over TLS (853) and another resolver time out. A refused connection would
  mean the packet got out, so only a timeout counts as closed.
- Nothing private: no private range, no address of the VPC's own, no Amazon DNS server (which no AWS firewall
  filters, so the lane's network has it turned off), and not another box of the lane: a second box is started
  and the first cannot reach its SSH port on its private or its public address, while the harness can.
- The cut is real. Root holds a connection open and sends on it once a second: answers before the cut, none after
  (the half a security group alone would not do). New connections and DNS fail. Root then flushes the VM's own
  firewall and routes, and they still fail. The provider describes the machine differently than online.
  Localhost still answers, and so does the harness's channel. Back online, a connection opens again.
- The outside probe sees from outside: a server on all addresses answers the harness with HTTP 200, one on
  loopback does not (though it answers inside), and no probe rule is left open afterwards.
- The instance is gone after the run: the provider's own word, asked after close(), for both boxes.

limits.py is a guarded file. The hook that makes `limits.limits_test` hand a full-privilege box to this module is
loop/proposals/limits-root-vm-hook.patch; until it is applied the CLI calls root_limits_test itself.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now
from pickfit.verify.box import Box, BoxError, ExecResult
from pickfit.verify.limits import ProbeResult, _detail

PYTHON = "/usr/bin/python3"
SUDO = "/usr/bin/sudo -n"
# As root: one TCP connection to each host:port given. A name is resolved first and its failure is said apart, so
# a broken resolver never reads as a closed port. The error's class is printed: only a timeout is the firewall.
CONNECT_PY = r"""import socket, sys
for target in sys.argv[1:]:
    host, port = target.rsplit(":", 1)
    try:
        address = socket.getaddrinfo(host, int(port), socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except OSError as e:
        print("unresolved", target, type(e).__name__)
        continue
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((address, int(port)))
        print("open", target)
    except OSError as e:
        print("closed", target, type(e).__name__)
    finally:
        s.close()
"""
# As root: an A query for pypi.org over UDP to each server given; the answer's code and count, or silence.
DNS_PY = r"""import random, socket, struct, sys
q = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0) + b"\x04pypi\x03org\x00" + struct.pack(">HH", 1, 1)
for server in sys.argv[1:]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    try:
        s.sendto(q, (server, 53))
        reply = s.recv(512)
        flags, _, answers = struct.unpack(">HHH", reply[2:8])
        print("dns", server, "answered", f"rcode={flags & 15}", f"answers={answers}")
    except OSError as e:
        print("dns", server, "silent", type(e).__name__)
    finally:
        s.close()
"""
# As root: every way to ask the metadata service, its status code each ("000": no answer).
IMDS = ("set -f; for u in '-X PUT -H X-aws-ec2-metadata-token-ttl-seconds:60 http://169.254.169.254/latest/api/token' "
        "'http://169.254.169.254/latest/meta-data/' 'http://169.254.169.254/latest/user-data' "
        "'http://169.254.169.254/latest/meta-data/iam/security-credentials/' "
        "'http://[fd00:ec2::254]/latest/meta-data/'; do "
        "echo \"imds $(/usr/bin/curl -s -m 4 -o /dev/null -w '%{http_code}' $u)\"; done")
IMDS_ASKS = 5
# As root: what root can do to the VM's own network settings to get the service back (it is not a setting of the VM).
IMDS_UNDO = ("/usr/sbin/nft flush ruleset 2>&1; /usr/sbin/iptables -F 2>&1; /usr/sbin/iptables -t nat -F 2>&1; "
             "dev=$(/usr/sbin/ip -o route show default | /usr/bin/awk '{print $5; exit}'); "
             "/usr/sbin/ip route replace 169.254.169.254/32 dev \"$dev\" 2>&1; "
             "/usr/sbin/sysctl -qw net.ipv4.conf.all.rp_filter=0 2>&1; echo undo-tried")
# As root: files where a secret would be, read for a cloud key id, a secret key's name or a private key. The VM's
# own SSH host key is not a secret of pickfit's (/etc/ssh, and cloud-init's copy of the user data that carried it,
# which holds nothing else but the public half of this machine's login key).
SCAN_PY = r"""import os, re, sys
ROOTS = ("/root", "/home", "/etc", "/opt", "/srv", "/tmp", "/var/tmp", "/run", "/var/lib/cloud", "/var/lib/docker/volumes")
OWN = re.compile(r"^(/etc/ssh/ssh_host_[a-z0-9_]+_key|/var/lib/cloud/.*)$")
PATTERNS = (("key-id", re.compile(rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
            ("secret-name", re.compile(rb"aws_secret_access_key|aws_session_token", re.I)),
            ("private-key", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")))
seen = 0
for root in ROOTS:
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(folder, d))]
        if folder.endswith("/.aws"):
            print("found aws-dir", folder)
        for name in files:
            path = os.path.join(folder, name)
            try:
                if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > 2_000_000:
                    continue
                data = open(path, "rb").read()
            except OSError:
                continue
            seen += 1
            for kind, pattern in PATTERNS:
                if pattern.search(data):
                    print("found" if not OWN.match(path) else "own", kind, path)
SECRET = re.compile(r"^(AWS_|.*(API_KEY|TOKEN|SECRET|PASSWORD))")
for who in ("self", "1"):
    try:
        names = [v.split(b"=", 1)[0].decode(errors="replace") for v in open(f"/proc/{who}/environ", "rb").read().split(b"\0") if v]
    except OSError:
        names = []
    for name in names:
        if SECRET.match(name):
            print("found env", f"{who}:{name}")
print("scanned", seen)
"""
# The control's plant, made on the VM from two halves: no key-shaped string is ever in this file.
PLANT = ("/usr/bin/install -d -m 0700 /root/.aws && /usr/bin/printf 'aws_access_key_id = AKIA%s\\n' "
         "QQQQQQQQQQQQQQQQ > /root/.aws/credentials && echo planted")
UNPLANT = "/usr/bin/rm -rf /root/.aws"
OPEN_TARGETS = ("1.1.1.1:80", "1.1.1.1:443", "9.9.9.9:443")
# Each listens where it is asked (mail submission, SSH, DNS over TLS, another resolver's TCP port).
CLOSED_TARGETS = ("aspmx.l.google.com:25", "smtp.gmail.com:465", "smtp.gmail.com:587", "github.com:22",
                  "1.1.1.1:853", "9.9.9.9:53", "9.9.9.9:853")
RESOLVER, OTHER_RESOLVER = "1.1.1.1", "9.9.9.9"
AMAZON_DNS = "169.254.169.253"
PRIVATE_TARGETS = ("10.0.0.1:80", "10.0.0.1:22", "172.16.0.1:80", "192.168.0.1:80", "192.168.1.1:443",
                   "100.64.0.1:80")
CUT_TARGETS = ("1.1.1.1:443", "1.1.1.1:80")
HOLD_HOST = "deb.debian.org"  # answers HEAD on one connection for as long as it is asked: every box's apt uses it
HOLD_LOG = "/run/pickfit-held.log"
# As root, detached: one connection, a HEAD on it every second, each answer or silence a line in HOLD_LOG. A
# connection the far end closes is said so and ends the holder: the probe then decides nothing.
HOLD_PY = r"""import os, socket, sys, time
host, log = sys.argv[1], sys.argv[2]
with open(log + ".pid", "w") as f:
    f.write(str(os.getpid()))
def say(line):
    with open(log, "a") as f:
        f.write(line + "\n")
try:
    s = socket.create_connection((host, 80), timeout=5)
except OSError as e:
    say(f"no-connection {type(e).__name__}")
    raise SystemExit
for n in range(120):
    try:
        s.settimeout(3)
        s.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
        data = s.recv(4096)
        if not data:
            say("closed-by-peer")
            break
        say("answer" if data.startswith(b"HTTP/") else "answer?")
    except OSError as e:
        say(f"silent {type(e).__name__}")
    time.sleep(1)
"""
# As root: what root can do on the VM to get out again after the cut (none of it is where the cut is).
CUT_UNDO = ("/usr/sbin/nft flush ruleset 2>&1; /usr/sbin/iptables -F 2>&1; /usr/sbin/iptables -P OUTPUT ACCEPT 2>&1; "
            "/usr/sbin/ip route flush cache 2>&1; echo undo-tried")
MODULES = ("for m in dummy wireguard nbd; do /usr/sbin/modprobe $m 2>/dev/null && /usr/bin/grep -q \"^$m \" "
           "/proc/modules && { echo \"module-ok $m\"; break; }; done; /usr/sbin/modprobe tun 2>/dev/null; "
           "/usr/sbin/modprobe fuse 2>/dev/null; test -c /dev/net/tun && echo tun-ok; test -c /dev/fuse && echo "
           f"fuse-ok; {PYTHON} -I -c 'import socket; socket.socket(socket.AF_INET, socket.SOCK_RAW, 1); "
           "print(\"raw-ok\")'")
GONE = ("shutting-down", "terminated", "gone")


def _py(script: str, *args: str) -> str:
    """Bash that runs a Python script as root with those arguments (the script on stdin, never spliced)."""
    return f"{SUDO} {PYTHON} -I - {' '.join(args)} <<'PICKFIT_PY'\n{script}PICKFIT_PY"


def _root(command: str) -> str:
    """Bash that runs a command line as root, through the box user's own sudo."""
    return f"{SUDO} /usr/bin/bash -c {_quote(command)}"


def _quote(text: str) -> str:
    import shlex

    return shlex.quote(text)


# -- readers: what an output says. Each is a pure function, so a test can give it a passing and a failing reading.


def connects(stdout: str) -> dict[str, tuple[str, str]]:
    """CONNECT_PY's lines: target -> (open, closed or unresolved; the error's class)."""
    out = {}
    for line in stdout.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] in ("open", "closed", "unresolved"):
            out[words[1]] = (words[0], words[2] if len(words) > 2 else "")
    return out


def all_open(stdout: str, targets: tuple[str, ...]) -> bool:
    seen = connects(stdout)
    return all(seen.get(t, ("", ""))[0] == "open" for t in targets)


def all_timed_out(stdout: str, targets: tuple[str, ...]) -> bool:
    """Every target was tried and timed out. A refusal, a reset or an unresolved name is not a closed port: the
    first two mean a packet came back, the third that nothing was tried."""
    seen = connects(stdout)
    return bool(targets) and all(seen.get(t) == ("closed", "TimeoutError") for t in targets)


def all_unreachable(stdout: str, targets: tuple[str, ...]) -> bool:
    """Every target was tried and nothing came back from it: a timeout, or no route at all."""
    seen = connects(stdout)
    return bool(targets) and all(seen.get(t, ("", ""))[0] == "closed" and seen[t][1] != "ConnectionRefusedError"
                                 and seen[t][1] != "ConnectionResetError" for t in targets)


def dns(stdout: str) -> dict[str, str]:
    """DNS_PY's lines: server -> "resolved" (an answer with records), "empty" (an answer without) or "silent"."""
    out = {}
    for line in stdout.splitlines():
        words = line.split()
        if len(words) >= 3 and words[0] == "dns":
            if words[2] == "silent":
                out[words[1]] = "silent"
            else:
                fields = dict(w.split("=", 1) for w in words[3:] if "=" in w)
                count = fields.get("answers", "0")
                good = fields.get("rcode") == "0" and count.isdigit() and int(count) > 0
                out[words[1]] = "resolved" if good else "empty"
    return out


def metadata_silent(stdout: str) -> bool:
    """Every way of asking was tried and none got a 2xx (a turned-off service says 403 or nothing)."""
    codes = [line.split()[1] for line in stdout.splitlines() if line.startswith("imds ") and len(line.split()) == 2]
    return len(codes) == IMDS_ASKS and not any(code.startswith("2") for code in codes)


def scan_clean(stdout: str) -> bool:
    """The scan read files and found nothing that is not the VM's own."""
    scanned = re.search(r"^scanned (\d+)$", stdout, re.M)
    return scanned is not None and int(scanned.group(1)) > 0 and not re.search(r"^found ", stdout, re.M)


def no_identity(view: dict[str, Any]) -> bool:
    """The provider's own description: metadata endpoint off, no instance profile, no key pair, no volume that
    would outlive the instance."""
    return (view.get("metadata_endpoint") == "disabled" and not view.get("instance_profile")
            and not view.get("key_pair") and view.get("volumes_deleted_with_it") is True)


def held_cut(log: str) -> bool:
    """HOLD_LOG with the harness's CUT line in it: the connection answered at least twice before the cut, and
    after it never again and was tried (silent) at least twice. A connection its far end closed decides nothing."""
    if "closed-by-peer" in log or "no-connection" in log or log.count("CUT") != 1:
        return False
    before, after = (part.split() for part in log.split("CUT"))
    return before.count("answer") >= 2 and "answer" not in after and after.count("silent") >= 2


def capabilities_work(stdout: str) -> bool:
    return (re.search(r"^module-ok \w+$", stdout, re.M) is not None
            and all(mark in stdout.split() for mark in ("tun-ok", "fuse-ok", "raw-ok")))


def disk_usable(stdout: str, disk: str) -> bool:
    """The extra disk was formatted and mounted, a file was written on it, and it is not where / lives."""
    lines = dict(line.split(" ", 1) for line in stdout.splitlines() if " " in line)
    return (lines.get("mounted") == disk and lines.get("wrote") == "ok" and bool(lines.get("root"))
            and not lines["root"].startswith(disk))


# -- the probes


def _probe(box: Box, name: str, command: str, timeout_s: int, expect: str,
           check: Callable[[ExecResult], bool]) -> ProbeResult:
    result = box.exec(command, timeout_s)
    return ProbeResult(name, bool(check(result)), expect, result.exit_code, result.seconds, _detail(result))


def _view(box: Any) -> dict[str, Any]:
    try:
        return dict(box.machine.outside_view())
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"[:200]}


def _egress_view(box: Any) -> Any:
    view = _view(box)
    return {key: view.get(key) for key in ("groups", "acl", "error") if key in view} or view


def _is_what_it_says(box: Any, add: Callable[[ProbeResult], None]) -> None:
    add(_probe(box, "root_given", f"id -u; {SUDO} /usr/bin/id -u", 20,
               "the box user is uid 1000 and its sudo gives uid 0 (this is a full-privilege box)",
               lambda r: r.stdout.split() == ["1000", "0"]))
    add(_probe(box, "systemd_runs", f"cat /proc/1/comm; systemctl is-system-running; {SUDO} /usr/bin/systemd-run "
               "--wait --quiet --collect /usr/bin/true && echo unit-ran", 60,
               "systemd is PID 1, is up, and runs a unit to its end",
               lambda r: r.stdout.split()[:1] == ["systemd"] and "unit-ran" in r.stdout
               and any(state in r.stdout.split() for state in ("running", "degraded"))))
    add(_probe(box, "container_runs", "docker run --rm hello-world 2>&1 | grep -c 'Hello from Docker'", 180,
               "the box user's Docker pulls and runs a container", lambda r: r.stdout.strip() == "1"))
    add(_probe(box, "kernel_reachable", _root(MODULES), 60,
               "a kernel module loads, /dev/net/tun and /dev/fuse are there, a raw socket opens",
               lambda r: capabilities_work(r.stdout)))
    disk = getattr(box, "extra_disk", None)
    if getattr(box.machine, "extra_disk_gb", 0):
        command = _root(f"/usr/sbin/mkfs.ext4 -q -F {disk} && /usr/bin/mount {disk} /mnt && /usr/bin/touch /mnt/x "
                        "&& echo 'wrote ok'; echo \"mounted $(/usr/bin/findmnt -n -o SOURCE /mnt)\"; "
                        "echo \"root $(/usr/bin/findmnt -n -o SOURCE /)\"; /usr/bin/umount /mnt")
        add(_probe(box, "extra_disk", command, 120, f"the blank disk {disk} formats and mounts, and is not the "
                   "system's", lambda r: bool(disk) and disk_usable(r.stdout, str(disk))))


def _no_identity(box: Any, add: Callable[[ProbeResult], None]) -> None:
    add(_probe(box, "metadata_off_for_root", _root(IMDS), 60,
               "root gets no 2xx from the metadata service on any address or path (403 or nothing)",
               lambda r: metadata_silent(r.stdout)))
    undone = box.exec(_root(IMDS_UNDO) + "; " + _root(IMDS), 90)
    add(ProbeResult("metadata_stays_off", "undo-tried" in undone.stdout and metadata_silent(undone.stdout),
                    "after root flushes the VM's firewall and routes the service to its interface, still no 2xx",
                    undone.exit_code, undone.seconds, _detail(undone)))
    view = _view(box)
    add(ProbeResult("no_identity_outside", no_identity(view), "the provider says: metadata endpoint disabled, no "
                    "instance profile, no key pair, every volume deleted with the instance", None, 0.0,
                    json.dumps(view, default=str)[:300]))
    add(_probe(box, "no_credentials_on_disk", _py(SCAN_PY), 180,
               "root's scan finds no cloud key, no private key but the VM's own host key, no secret variable",
               lambda r: scan_clean(r.stdout)))
    planted = box.exec(_root(PLANT) + "; " + _py(SCAN_PY) + f"; {_root(UNPLANT)}", 180)
    add(ProbeResult("no_credentials_control", "planted" in planted.stdout and not scan_clean(planted.stdout)
                    and "found key-id /root/.aws/credentials" in planted.stdout,
                    "with a key id planted in /root/.aws (this box only), the same scan finds it",
                    planted.exit_code, planted.seconds, _detail(planted)))
    add(_probe(box, "no_secrets_in_env", "env | cut -d= -f1 | sort | tr '\\n' ' '", 20,
               "no API_KEY/TOKEN/SECRET/PASSWORD variables",
               lambda r: not re.search(r"API_KEY|TOKEN|SECRET|PASSWORD|AWS_", r.stdout)))


def _egress(box: Any, add: Callable[[ProbeResult], None], peer: Any = None) -> None:
    add(_probe(box, "egress_allowed", _py(CONNECT_PY, *OPEN_TARGETS) + "\n" + _py(DNS_PY, RESOLVER), 90,
               "as root: TCP 80 and 443 open to public addresses and the listed resolver answers (the control for "
               "every closed reading)",
               lambda r: all_open(r.stdout, OPEN_TARGETS) and dns(r.stdout).get(RESOLVER) == "resolved"))
    add(_probe(box, "egress_only_allowed_ports", _py(CONNECT_PY, *CLOSED_TARGETS) + "\n" + _py(DNS_PY, OTHER_RESOLVER),
               120, "as root: SMTP (25, 465, 587), SSH (22), DNS over TLS and another resolver time out",
               lambda r: all_timed_out(r.stdout, CLOSED_TARGETS) and dns(r.stdout).get(OTHER_RESOLVER) == "silent"))
    view = _view(box)
    own = [f"{address}:80" for address in (view.get("vpc_router"), view.get("vpc_resolver")) if address]
    targets = (*PRIVATE_TARGETS, *own)
    servers = [AMAZON_DNS, *([str(view["vpc_resolver"])] if view.get("vpc_resolver") else [])]
    add(_probe(box, "private_unreachable", _py(CONNECT_PY, *targets) + "\n" + _py(DNS_PY, *servers), 180,
               "as root: no private range, no address of the lane's own network and no Amazon DNS server answers",
               lambda r: all_unreachable(r.stdout, targets)
               and all(dns(r.stdout).get(server) in ("silent", "empty") for server in servers)))
    there = _view(peer) if peer is not None else {}
    addresses = [str(a) for a in (there.get("private_address"), there.get("address")) if a]
    if len(addresses) != 2:  # not checked is not passed
        add(ProbeResult("peer_unreachable", False, "a second box of the lane cannot be reached from this one", None,
                        0.0, "no second box was started" if peer is None else
                        f"the second box's addresses are not known: {json.dumps(there, default=str)[:200]}"))
        return
    targets = tuple(f"{address}:22" for address in addresses)
    control = peer.exec("echo peer-answers-the-harness", 30)  # the harness reaches the peer's sshd: the port listens
    result = box.exec(_py(CONNECT_PY, *targets), 90)
    ok = (len(addresses) == 2 and "peer-answers-the-harness" in control.stdout
          and all_timed_out(result.stdout, targets))
    add(ProbeResult("peer_unreachable", ok, "as root, this box cannot open the SSH port of another box of the lane, on "
                    "its private or its public address, while the harness can", result.exit_code, result.seconds,
                    f"peer {' '.join(addresses) or '?'}; control: {_detail(control)[:60]}; {_detail(result)}"[-300:]))


def _outside_probe(box: Any, add: Callable[[ProbeResult], None]) -> None:
    box.exec(f"{box.detach} python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 < /dev/null & "
             f"{box.detach} python3 -m http.server 8766 --bind 0.0.0.0 >/dev/null 2>&1 < /dev/null & sleep 2", 20)
    wide = box.probe_port(8766, path="/")
    add(ProbeResult("outside_probe_sees", wide.get("outside") == "open" and wide.get("status") == 200,
                    "the harness connects from outside to a server on all addresses and gets HTTP 200",
                    None, float(wide.get("seconds") or 0.0), json.dumps(wide, default=str)[:300]))
    inside = box.exec("curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/", 20)
    local = box.probe_port(8765, path="/")
    add(ProbeResult("outside_probe_is_outside", local.get("outside") == "closed" and inside.stdout.strip() == "200",
                    "a server on loopback only answers inside (200) and not the harness's probe from outside",
                    inside.exit_code, float(local.get("seconds") or 0.0),
                    f"inside {inside.stdout.strip()}; {json.dumps(local, default=str)}"[:300]))
    try:
        left = list(box.machine.probed_ports())
    except Exception as error:
        left = [f"{type(error).__name__}: {error}"[:120]]
    add(ProbeResult("probe_rule_removed", left == [], "no inbound rule of a probe is left once the probes are over",
                    None, 0.0, f"ports still open to the harness beyond SSH: {left or 'none'}"))


def _cut(box: Any, add: Callable[[ProbeResult], None]) -> None:
    online = _egress_view(box)
    box.exec(_root(f"/usr/bin/rm -f {HOLD_LOG}; {box.detach} {PYTHON} -I -c {_quote(HOLD_PY)} {HOLD_HOST} {HOLD_LOG} "
                   "> /dev/null 2>&1 < /dev/null & sleep 4"), 30)
    box.set_network(False)
    try:
        box.exec(_root(f"echo CUT >> {HOLD_LOG}; sleep 12"), 40)  # three more tries of the holder's, 4 s each
        held = box.exec(_root(f"/usr/bin/cat {HOLD_LOG}; kill $(/usr/bin/cat {HOLD_LOG}.pid) 2>/dev/null; true"), 20)
        add(ProbeResult("cut_ends_open_connections", held_cut(held.stdout),
                        "a connection root held open answered before the cut and never after it", held.exit_code,
                        held.seconds, _detail(held)))
        add(_probe(box, "cut_refuses_new_connections",
                   _py(CONNECT_PY, *CUT_TARGETS) + "\n" + _py(DNS_PY, RESOLVER, AMAZON_DNS), 90,
                   "offline, as root: no new connection opens and no resolver answers",
                   lambda r: all_timed_out(r.stdout, CUT_TARGETS) and dns(r.stdout).get(RESOLVER) == "silent"
                   and dns(r.stdout).get(AMAZON_DNS) in ("silent", "empty")))
        undone = box.exec(_root(CUT_UNDO) + "; " + _py(CONNECT_PY, *CUT_TARGETS), 120)
        add(ProbeResult("cut_root_cannot_undo", "undo-tried" in undone.stdout
                        and all_timed_out(undone.stdout, CUT_TARGETS),
                        "after root flushes the VM's firewall, routes and network service, still nothing opens",
                        undone.exit_code, undone.seconds, _detail(undone)))
        offline = _egress_view(box)
        add(ProbeResult("cut_seen_outside", bool(offline) and "error" not in offline and offline != online,
                        "the provider describes the machine's firewall differently than while online", None, 0.0,
                        f"online {json.dumps(online, default=str)}; offline {json.dumps(offline, default=str)}"[:300]))
        add(_probe(box, "offline_localhost", "curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/",
                   20, "localhost still answers with the network off (and the harness's channel carried this)",
                   lambda r: r.stdout.strip() == "200"))
    finally:
        box.set_network(True)
    add(_probe(box, "online_again", _py(CONNECT_PY, *CUT_TARGETS), 60, "a connection opens again once the network "
               "is back", lambda r: all_open(r.stdout, CUT_TARGETS)))


def gone_probe(box: Any, name: str = "instance_gone") -> ProbeResult:
    """After close(): the provider's own word that the machine is going or gone."""
    try:
        state = str(box.machine.state())
    except Exception as error:
        state = f"unknown ({type(error).__name__}: {error})"[:200]
    return ProbeResult(name, state in GONE, "after the run the provider describes the machine as shutting down, "
                       "terminated or gone", None, 0.0, f"state {state}")


def run_root_limits_test(box: Any, log: Callable[[str], None] = print, peer: Any = None) -> list[ProbeResult]:
    """Run every probe in a started full-privilege box (and against `peer`, a second started box of the lane);
    restores the network before returning. The machines' end is checked by the caller, after close()."""
    if not box.capabilities.root:
        raise BoxError("this is the limits test of a full-privilege VM box; a box whose user is not root is "
                       "limits.py's")
    results: list[ProbeResult] = []

    def add(result: ProbeResult) -> None:
        results.append(result)
        log(f"  {'ok  ' if result.ok else 'FAIL'} {result.name}: {result.expect} · exit {result.exit_code} · "
            f"{result.seconds:.1f}s · {result.detail[:140]}")

    _is_what_it_says(box, add)
    _no_identity(box, add)
    _egress(box, add, peer)
    _outside_probe(box, add)
    _cut(box, add)
    timed = box.exec("sleep 30", 3)
    add(ProbeResult("command_timeout", timed.timed_out and timed.seconds < 15, "sleep 30 killed at 3 s",
                    timed.exit_code, timed.seconds, _detail(timed)))
    return results


def save_root_limits(results: list[ProbeResult], box: Any, runs_dir: Path) -> Path:
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    path = Path(runs_dir) / "verify" / f"limits-{box.runner}-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"runner": box.runner, "image": box.image, "start_s": getattr(box, "start_s", None),
               "full_privilege": True, "capabilities": box.capabilities.granted(),
               "checked_at": taipei_now().isoformat(timespec="seconds"),
               "passed": sum(r.ok for r in results), "total": len(results),
               "probes": [asdict(r) for r in results], "box": box.evidence()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def root_limits_test(make_box: Callable[[str, str], Box], runs_dir: Path, log: Callable[[str], None] = print
                     ) -> tuple[list[ProbeResult], Path]:
    """Start a full-privilege box and a second one beside it (the lane's two), run the probes, close both and ask
    the provider whether they are gone."""
    began = time.monotonic()
    run_id = f"limits-{taipei_now().strftime('%Y%m%d-%H%M%S')}"
    box: Any = make_box(run_id, "limits")
    peer: Any = make_box(run_id, "limits-peer")
    results: list[ProbeResult] = []
    try:
        box.start()
        log(f"limits test · {box.runner} · {box.image} · started in {getattr(box, 'start_s', None)}s")
        try:
            peer.start()
        except BoxError as error:  # the probe that needs it fails, and says why
            log(f"limits test · no second box: {error}")
            peer = None
        results = run_root_limits_test(box, log, peer)
    finally:
        box.close()
        if peer is not None:
            peer.close()
    for name, closed in (("instance_gone", box), ("peer_instance_gone", peer)):
        if closed is not None:
            results.append(gone_probe(closed, name))
            log(f"  {'ok  ' if results[-1].ok else 'FAIL'} {name}: {results[-1].detail}")
    path = save_root_limits(results, box, runs_dir)
    log(f"limits test · {sum(r.ok for r in results)}/{len(results)} held · {time.monotonic() - began:.0f}s · {path}")
    return results, path
