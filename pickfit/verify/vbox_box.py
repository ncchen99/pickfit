"""VBoxBox: the Box interface on a real Windows 11 VM on this Windows PC (Oracle VirtualBox).

- One prepared Windows guest (`pickfit-win11`) with a powered-off snapshot `clean`. Every box restores
  that snapshot and cold-boots it, and `close()` powers it off and restores the snapshot again, so
  nothing a run did survives it. One box at a time (a single base, and this PC has 16 GB of RAM).
- Commands reach the guest through `VBoxManage guestcontrol run`, which talks to the Guest Additions
  service over the hypervisor's HGCM channel, not the network: cutting the guest's network leaves control
  intact, so the replay's offline smoke tests work.
- Model commands run as `sbx`, a standard Windows user (not an administrator), in PowerShell 7 (pwsh),
  started by a harness script in an admin-owned directory that sbx can read but not change. VBoxManage
  maps the guest exit code (1..93 -> 33..125, anything larger -> 126), so the harness script prints
  `__PF_RC_<nonce>=<code>` last and exits with the code; the host takes the last sentinel and cross-checks
  it against VBoxManage's own exit code, so a grandchild that prints a fake sentinel cannot change the code.
  Guest output is untrusted data: it is size-capped (head and tail) and never evaluated.
- Network, decided OUTSIDE the guest so nothing in it, not even an administrator, can change it:
  online, the guest's only NIC is on a VirtualBox internal network whose only other member is a small
  Alpine router VM (`pickfit-router`, also reset from a snapshot every box). The router forwards to the
  public internet through its own NAT NIC (localhost not reachable) and drops, in nftables, every
  private, shared, link-local, loopback, multicast and reserved IPv4 range plus the host's own public
  addresses; IPv6 is off; DNS is dnsmasq forwarding to public resolvers with rebind protection.
  Offline, the guest's NIC is detached (`nic1 null`, link down). After every change the harness probes
  from inside the guest AS ADMINISTRATOR that the host, its LAN, its gateway, VirtualBox's NAT host
  address, metadata and multicast are silently dropped (a TCP connect times out; a refusal means the
  packet arrived and fails the check), that the internet answers only online, and before going back
  online that the cut held. `offline` is never claimed on a word. The limits test adds positive
  controls: the same probe sees the host's ports open when the guest is put on plain NAT (no router),
  and sees the router's own DNS port open.
- Clipboard, drag and drop, shared folders, USB, audio and 3D are off; VRDE is off.
- Lifetime: besides the harness's timer, the guest schedules its own shutdown and a detached host
  process powers both VMs off, so a dead harness does not leave a VM running.

Licences (docs/research/notes/macos-windows-verify.md): VirtualBox base package GPLv3 (no Extension Pack,
which is PUEL); the guest is Windows 11 Enterprise Evaluation (90 days, Microsoft Evaluation Center),
activated online once before the clean snapshot; the router is Alpine Linux (open source).
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now
from pickfit.verify.box import Box, BoxError, BoxLimits, ExecResult, HOST_GRACE_S, run_captured

STATE_DIR = Path.home() / ".pickfit" / "vbox"  # manifests, password files, VMs, logs; outside the repo
BASE_VM = "pickfit-win11"
ROUTER_VM = "pickfit-router"
SNAPSHOT = "clean"
INTNET = "pickfit-net"
ROUTER_IP = "10.99.0.1"
WIN_USER = "sbx"
ADMIN_USER = "pfadmin"
WIN_HOME = r"C:\Users\sbx"
WIN_WORKDIR = r"C:\Users\sbx\work"
HARNESS_DIR = r"C:\ProgramData\pickfit"  # Administrators and SYSTEM may write; sbx may only read and run
RUN_PS1 = HARNESS_DIR + r"\run.ps1"
PROBE_PS1 = HARNESS_DIR + r"\probe.ps1"
WINPS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
PWSH = r"C:\Program Files\PowerShell\7\pwsh.exe"
# Only non-secret settings; nothing from the host environment is passed through (guestcontrol builds the
# rest from the sbx profile: USERPROFILE, APPDATA, the machine and user PATH).
WIN_ENV = {
    "CI": "1",
    "PIP_NO_INPUT": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PYTHONUNBUFFERED": "1",
    "PYTHONIOENCODING": "utf-8",
    "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    "POWERSHELL_TELEMETRY_OPTOUT": "1",
    "POWERSHELL_UPDATECHECK": "Off",
    "COLUMNS": "100",
}
TIMEOUT_EXIT = 137  # what run.ps1 exits with when it kills the command tree at the deadline
ADDITIONS_WAIT_S = 600  # cold boot of Windows 11 on Hyper-V (NEM) is slow
ROUTER_WAIT_S = 90
NETWORK_WAIT_S = 90
REAP_GRACE_S = 300
STALE_S = 3 * 3600
SENTINEL = "__PF_RC_"

# The router drops these for traffic it forwards from the guest; the host's own public addresses are
# added per boot (DMI serial, see ROUTER_START). 240.0.0.0/4 includes 255.255.255.255.
BLOCKED_V4 = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
              "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
              "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4")
PUBLIC_URL = "https://pypi.org/simple/pip/"
# Ports a Windows host listens on by default (RPC, SMB, delivery optimization, connected devices) and a
# few a home router or LAN device tends to answer; with the router dropping them every one must time out.
HOST_PORTS = (135, 445, 5040, 7680)
LAN_PORTS = (53, 80, 443)
VBOX_NAT_HOST = "10.0.2.2"  # VirtualBox NAT's alias for the host
VBOX_NAT_DNS = "10.0.2.3"


def find_vboxmanage() -> str:
    found = shutil.which("VBoxManage")
    if found:
        return found
    root = os.environ.get("VBOX_MSI_INSTALL_PATH") or r"C:\Program Files\Oracle\VirtualBox"
    path = Path(root) / "VBoxManage.exe"
    if path.exists():
        return str(path)
    raise BoxError("VBoxManage not found; install Oracle VirtualBox 7.2 (base package only)")


def expected_vbm_code(code: int) -> int:
    """What `guestcontrol run` exits with for a guest exit code (VBoxManage's RTEXITCODE mapping)."""
    if code == 0:
        return 0
    if 1 <= code <= 93:
        return code + 32
    return 126


def parse_sentinel(stdout: str, nonce: str, vbm_code: int) -> tuple[str, int | None, str | None]:
    """(stdout without the sentinel, guest exit code or None, a warning or None).

    Takes the LAST sentinel line for this nonce. If its code does not match VBoxManage's own exit code
    (something in the guest printed a fake one), the sentinel is not trusted.
    """
    pat = re.compile(rf"^{SENTINEL}{re.escape(nonce)}=(-?\d+)\r?$", re.M)
    matches = list(pat.finditer(stdout))
    if not matches:
        return stdout, None, None
    last = matches[-1]
    code = int(last.group(1))
    cleaned = stdout[:last.start()] + stdout[last.end():].lstrip("\r\n")
    if expected_vbm_code(code) != vbm_code:
        return cleaned, None, (f"[pickfit: the exit-code line said {code} but VBoxManage exited {vbm_code}; "
                               "not trusted]")
    return cleaned, code, None


def encode_ps(command: str) -> str:
    """PowerShell -EncodedCommand: base64 of UTF-16LE."""
    return base64.b64encode(command.encode("utf-16-le")).decode("ascii")


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


# ---------------------------------------------------------------- guest-side harness scripts

# Runs as the calling user (sbx for model commands). Starts pwsh with the command, kills its process tree
# at the deadline, prints the sentinel last and exits with the same code.
RUN_SCRIPT = r"""param([int]$Timeout, [string]$Cwd, [string]$Nonce, [string]$Enc)
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'C:\Program Files\PowerShell\7\pwsh.exe'
$psi.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand ' + $Enc
$psi.WorkingDirectory = $Cwd
$psi.UseShellExecute = $false
try { $p = [System.Diagnostics.Process]::Start($psi) } catch {
  [Console]::Error.WriteLine("pickfit: cannot start pwsh: $_"); [Console]::Out.WriteLine("__PF_RC_${Nonce}=127"); exit 127 }
$null = $p.Handle
if ($p.WaitForExit($Timeout * 1000)) { $p.WaitForExit(); $rc = $p.ExitCode }
else { & taskkill.exe /T /F /PID $p.Id *> $null; $rc = 137 }
[Console]::Out.Flush()
[Console]::Out.WriteLine("__PF_RC_${Nonce}=$rc")
[Console]::Out.Flush()
exit $rc
"""

# Containment probe, run as the administrator. Each target is name=host:port (TCP connect) and the result
# is open (connected), refused (the packet arrived: RST), timeout (silently dropped) or unreachable (no
# route / network down). Also: an HTTPS GET to the public URL, an mDNS and an SSDP query (answered or not).
PROBE_SCRIPT = r"""param([string]$Targets, [int]$Ms = 3000, [string]$Url = '', [switch]$Multicast)
$ErrorActionPreference = 'Continue'
$jobs = @()
foreach ($t in ($Targets -split ',')) {
  if (-not $t) { continue }
  $name, $hp = $t -split '=', 2
  $h, $port = $hp -split ':(?=\d+$)'
  $c = New-Object System.Net.Sockets.TcpClient
  $jobs += ,@($name, $c, $c.ConnectAsync($h.Trim('[',']'), [int]$port))
}
$deadline = [DateTime]::UtcNow.AddMilliseconds($Ms)
foreach ($j in $jobs) {
  $left = [int][Math]::Max(0, ($deadline - [DateTime]::UtcNow).TotalMilliseconds)
  $task = $j[2]
  $done = $false
  try { $done = $task.Wait($left) } catch { $done = $true }
  if (-not $done) { $r = 'timeout' }
  elseif ($task.Status -eq 'RanToCompletion') { $r = 'open' }
  else {
    $e = $task.Exception.InnerException
    while ($e -and -not ($e -is [System.Net.Sockets.SocketException])) { $e = $e.InnerException }
    if ($e -and $e.SocketErrorCode -eq 'ConnectionRefused') { $r = 'refused' }
    elseif ($e -and $e.SocketErrorCode -eq 'TimedOut') { $r = 'timeout' }
    elseif ($e) { $r = 'unreachable:' + $e.SocketErrorCode } else { $r = 'error' }
  }
  try { $j[1].Close() } catch {}
  "probe $($j[0])=$r"
}
if ($Url) {
  & "$env:SystemRoot\System32\curl.exe" -sS -m 15 -o NUL $Url 2>$null
  "probe public=curl$LASTEXITCODE"
}
if ($Multicast) {
  foreach ($m in @(@('mdns', '224.0.0.251', 5353), @('ssdp', '239.255.255.250', 1900))) {
    $u = New-Object System.Net.Sockets.UdpClient 0
    $u.Client.ReceiveTimeout = 2500
    if ($m[0] -eq 'mdns') {
      $q = [byte[]](0,0,0,0,0,1,0,0,0,0,0,0) + [Text.Encoding]::ASCII.GetBytes("`t_services`a_dns-sd`u{4}_udp`u{5}local") + [byte[]](0,0,12,0,1)
    } else {
      $q = [Text.Encoding]::ASCII.GetBytes("M-SEARCH * HTTP/1.1`r`nHOST: 239.255.255.250:1900`r`nMAN: `"ssdp:discover`"`r`nMX: 1`r`nST: ssdp:all`r`n`r`n")
    }
    try {
      $null = $u.Send($q, $q.Length, $m[1], $m[2])
      $ep = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), 0
      $null = $u.Receive([ref]$ep)
      "probe $($m[0])=answered:$($ep.Address)"
    } catch { "probe $($m[0])=no-answer" }
    $u.Close()
  }
}
"""

PROBE_LINE = re.compile(r"^probe (\w+)=(\S+)\s*$", re.M)


# ---------------------------------------------------------------- the router VM

ROUTER_INSTALL = """\
set -e
setup-keymap us us >/dev/null 2>&1 || true
setup-hostname pickfit-router
printf 'auto lo\\niface lo inet loopback\\n\\nauto eth1\\niface eth1 inet dhcp\\n' > /etc/network/interfaces
rc-service networking restart >/dev/null 2>&1 || ifup eth1
echo 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' > /etc/apk/repositories
apk update -q
ERASE_DISKS=/dev/sda setup-disk -m sys -s 0 -k virt /dev/sda > /tmp/setup-disk.log 2>&1 || { tail -20 /tmp/setup-disk.log; exit 1; }
echo setup-disk done
"""

ROUTER_NFT = """\
#!/usr/sbin/nft -f
# pickfit router: the Windows guest (eth0, intnet) reaches only the public internet through eth1 (NAT).
flush ruleset
table inet pf {
    set blocked4 {
        type ipv4_addr; flags interval
        elements = { %s }
    }
    set extra4 {
        type ipv4_addr; flags interval
    }
    chain input {
        type filter hook input priority 0; policy drop;
        iif "lo" accept
        ct state established,related accept
        iifname "eth1" ct state new drop
        iifname "eth0" udp sport 68 udp dport 67 accept
        iifname "eth0" ip daddr 10.99.0.1 udp dport 53 accept
        iifname "eth0" ip daddr 10.99.0.1 tcp dport 53 accept
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
        iifname "eth0" oifname "eth1" ip daddr @blocked4 counter drop
        iifname "eth0" oifname "eth1" ip daddr @extra4 counter drop
        iifname "eth0" oifname "eth1" meta nfproto ipv4 counter accept
        iifname "eth1" oifname "eth0" ct state established,related accept
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
    chain postrouting {
        type nat hook postrouting priority 100;
        oifname "eth1" masquerade
    }
}
""" % ", ".join(BLOCKED_V4)

# At every boot: add the host's public addresses (passed in the DMI system serial as pf:a.b.c.d,...), then
# report the rule set's hash and the router's state on the serial port, the only thing it says to the host.
ROUTER_START = r"""#!/bin/sh
s=$(cat /sys/class/dmi/id/product_serial 2>/dev/null)
case "$s" in
  pf:*) for ip in $(echo "${s#pf:}" | tr ',' ' '); do nft add element inet pf extra4 "{ $ip }" || echo "PF_BAD_EXTRA $ip" > /dev/ttyS0; done ;;
esac
sum=$(nft -s list table inet pf | sed '/elements = /d' | sha256sum | cut -c1-16)
extra=$(nft list set inet pf extra4 | tr -d '\n\t ' | sed -n 's/.*elements={\([^}]*\)}.*/\1/p')
fwd=$(cat /proc/sys/net/ipv4/ip_forward)
v6=$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6)
dns=$(pidof dnsmasq >/dev/null && echo up || echo down)
up=$(ip -4 route show default | grep -c eth1)
echo "PICKFIT_ROUTER_READY rules=$sum extra=${extra:-none} forward=$fwd ipv6_off=$v6 dnsmasq=$dns uplink=$up" > /dev/ttyS0
"""

ROUTER_CONFIG = f"""\
set -e
mount /dev/sda2 /mnt
R=/mnt
apk --root $R --no-cache -q add nftables dnsmasq
cat > $R/etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address {ROUTER_IP}
    netmask 255.255.255.0

auto eth1
iface eth1 inet dhcp
EOF
cat > $R/etc/sysctl.d/90-pickfit.conf <<'EOF'
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.all.forwarding = 0
EOF
cat > $R/etc/nftables.nft <<'EOF'
{ROUTER_NFT}EOF
cat > $R/etc/dnsmasq.conf <<'EOF'
interface=eth0
bind-interfaces
no-resolv
no-hosts
no-poll
domain-needed
bogus-priv
stop-dns-rebind
server=1.1.1.1
server=8.8.8.8
dhcp-range=10.99.0.100,10.99.0.150,255.255.255.0,12h
dhcp-option=option:router,{ROUTER_IP}
dhcp-option=option:dns-server,{ROUTER_IP}
dhcp-authoritative
EOF
cat > $R/etc/local.d/pickfit.start <<'EOF'
{ROUTER_START}EOF
chmod 755 $R/etc/local.d/pickfit.start
for s in nftables:boot sysctl:boot networking:boot dnsmasq:default local:default; do
  ln -sf /etc/init.d/${{s%%:*}} $R/etc/runlevels/${{s##*:}}/${{s%%:*}}
done
# No login on the serial port (it only carries the ready line) and none for root on the console either.
sed -i 's/^ttyS0::/#ttyS0::/' $R/etc/inittab
sed -i 's/^root:[^:]*:/root:*:/' $R/etc/shadow
umount /mnt
echo pickfit router installed
"""

READY = re.compile(r"PICKFIT_ROUTER_READY rules=(\w+) extra=(\S+) forward=(\d) ipv6_off=(\d) dnsmasq=(\w+) "
                   r"uplink=(\d+)")


def host_public_ipv4() -> list[str]:
    """This PC's own IPv4 addresses that are NOT in the router's blocked ranges (normally none)."""
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 53))
            found.add(s.getsockname()[0])
    except OSError:
        pass
    nets = [ipaddress.ip_network(n) for n in BLOCKED_V4]
    return sorted(ip for ip in found if not any(ipaddress.ip_address(ip) in n for n in nets))


def host_lan_targets() -> dict[str, str]:
    """{name: ip} for the host's own LAN addresses and its default gateway (the home router)."""
    targets: dict[str, str] = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 53))
            targets["hostlan"] = s.getsockname()[0]
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True,
                                 timeout=20).stdout
            m = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
            if m:
                targets["gateway"] = m.group(1)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return targets


class VBox:
    """Thin VBoxManage wrapper; `argv0` is a prefix so tests can point it at a fake."""

    def __init__(self, argv0: Sequence[str] | str | None = None) -> None:
        if argv0 is None:
            argv0 = [find_vboxmanage()]
        self.argv0 = [argv0] if isinstance(argv0, str) else list(argv0)

    def __call__(self, *args: str, timeout_s: float = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run([*self.argv0, *args], capture_output=True, text=True, timeout=timeout_s,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired as err:
            raise BoxError(f"VBoxManage {' '.join(args[:2])} timed out after {timeout_s:.0f}s") from err
        if check and proc.returncode != 0:
            raise BoxError(f"VBoxManage {' '.join(args[:3])} failed: {proc.stderr.strip()[-400:]}")
        return proc

    def info(self, vm: str) -> dict[str, str]:
        out = self("showvminfo", vm, "--machinereadable").stdout
        return {m.group(1): m.group(2) for m in re.finditer(r'^"?([^"=\n]+)"?="?([^"\n]*)"?\r?$', out, re.M)}

    def state(self, vm: str) -> str:
        return self.info(vm).get("VMState", "")

    def poweroff(self, vm: str, wait_s: float = 60) -> None:
        if self.state(vm) in ("running", "paused", "stuck", "starting"):
            self("controlvm", vm, "poweroff", check=False, timeout_s=90)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self.state(vm) in ("poweroff", "aborted", "saved"):
                return
            time.sleep(1)
        raise BoxError(f"{vm} did not power off within {wait_s:.0f}s")

    def restore(self, vm: str, snapshot: str = SNAPSHOT) -> None:
        self("snapshot", vm, "restore", snapshot, timeout_s=300)

    def type_text(self, vm: str, text: str) -> None:
        """Type into the VM's console; each newline is an Enter scancode (a newline inside a
        keyboardputstring argument is lost at the end of the string)."""
        lines = text.split("\n")
        for n, line in enumerate(lines):
            for i in range(0, len(line), 400):
                self("controlvm", vm, "keyboardputstring", line[i:i + 400])
            if n < len(lines) - 1:
                self("controlvm", vm, "keyboardputscancode", "1c", "9c")


def manifest_path(name: str, state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"{name}.json"


def load_manifest(name: str, state_dir: Path | None = None, hint: str = "") -> dict[str, Any]:
    path = manifest_path(name, state_dir)
    if not path.exists():
        raise BoxError(f"no prepared {name!r} ({path} is missing){hint}")
    return json.loads(path.read_text(encoding="utf-8"))


class Router:
    """The pickfit-router VM: reset from its snapshot, told the extra blocks, checked by its ready line."""

    def __init__(self, vbox: VBox, *, name: str = ROUTER_VM, state_dir: Path | None = None,
                 log: Callable[[str], None] = print) -> None:
        self.vbox = vbox
        self.name = name
        self.state_dir = state_dir or STATE_DIR
        self.log = log
        self.serial_log = self.state_dir / "logs" / f"{name}-serial.log"
        self.ready: dict[str, str] = {}

    def reset(self, extra: list[str], manifest: dict[str, Any]) -> dict[str, str]:
        """Power off, restore the snapshot, pass the extra blocks, boot, and wait for a matching ready line."""
        for ip in extra:
            ipaddress.IPv4Address(ip)  # only addresses ever reach the DMI string
        self.vbox.poweroff(self.name)
        self.vbox.restore(self.name)
        serial = "pf:" + ",".join(extra) if extra else "pf:"
        self.vbox("setextradata", self.name, "VBoxInternal/Devices/pcbios/0/Config/DmiSystemSerial", serial)
        self.serial_log.parent.mkdir(parents=True, exist_ok=True)
        start = self.serial_log.stat().st_size if self.serial_log.exists() else 0
        self.vbox("startvm", self.name, "--type", "headless", timeout_s=120)
        deadline = time.monotonic() + ROUTER_WAIT_S
        m = None
        while time.monotonic() < deadline:
            data = self.serial_log.read_bytes() if self.serial_log.exists() else b""
            if len(data) < start:  # VirtualBox truncated the log at power-on
                start = 0
            m = READY.search(data[start:].decode("utf-8", "replace"))
            if m:
                break
            time.sleep(1)
        if m is None:
            raise BoxError(f"the router did not report ready within {ROUTER_WAIT_S}s ({self.serial_log})")
        self.ready = dict(zip(("rules", "extra", "forward", "ipv6_off", "dnsmasq", "uplink"), m.groups()))
        bad = []
        if self.ready["rules"] != manifest.get("rules"):
            bad.append(f"rule set {self.ready['rules']} is not the prepared {manifest.get('rules')}")
        got_extra = set() if self.ready["extra"] == "none" else set(self.ready["extra"].replace("/32", "").split(","))
        if got_extra != set(extra):  # nft keeps the set sorted
            bad.append(f"extra blocks {self.ready['extra']} != {','.join(extra) or 'none'}")
        if self.ready["forward"] != "1" or self.ready["ipv6_off"] != "1":
            bad.append("forwarding or IPv6 state is wrong")
        if self.ready["dnsmasq"] != "up" or self.ready["uplink"] == "0":
            bad.append("dnsmasq or the uplink is down")
        if bad:
            raise BoxError(f"router check failed: {'; '.join(bad)}")
        return self.ready

    def stop(self) -> None:
        try:
            self.vbox.poweroff(self.name)
        except BoxError as err:
            self.log(f"vbox: router poweroff: {err}")


class VBoxBox(Box):
    """A Windows 11 VM reset from a snapshot, driven like the other boxes."""

    runner = "vbox"
    os = "windows"
    arch = "x86_64"
    home = WIN_HOME
    workdir = WIN_WORKDIR
    kind = "Windows virtual machine"
    shell = "pwsh"
    user_rule = (r"You are a standard Windows user, not an administrator: no UAC elevation, no per-machine "
                 r"installs into C:\Program Files, nothing written outside your profile (C:\Users\sbx) and "
                 r"the temp dir; installs need a user scope (winget --scope user, scoop, pip/uv/pipx, npm -g).")
    detach = ""  # run_background is PowerShell here; see background()

    def __init__(self, *, base: str = BASE_VM, router: str = ROUTER_VM, limits: BoxLimits = BoxLimits(),
                 vboxmanage: Sequence[str] | str | None = None, state_dir: Path | None = None,
                 log: Callable[[str], None] = print) -> None:
        self.base = base
        self.limits = limits
        self.vbox = VBox(vboxmanage)
        self.state_dir = state_dir or STATE_DIR
        self.log = log
        self.router = Router(self.vbox, name=router, state_dir=self.state_dir, log=log)
        self.manifest: dict[str, Any] = {}
        self.router_manifest: dict[str, Any] = {}
        self.image = base
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.lan: dict[str, str] = {}
        self.extra: list[str] = []
        self.session = secrets.token_hex(6)
        self._timer: threading.Timer | None = None
        self._reaper: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def describe(self) -> str:
        m = self.manifest
        tools = ", ".join(f"{k} {m[k]}" for k in ("python", "uv", "pipx", "node", "npm", "git", "winget") if m.get(k))
        return (f"Box: Windows 11 Enterprise {m.get('windows', '')} {self.arch} virtual machine, user {WIN_USER} "
                f"(standard user, not an administrator, no UAC elevation), USERPROFILE={self.home}, work dir "
                f"{self.workdir}. Commands run in PowerShell 7 (pwsh {m.get('pwsh', '7')}): use PowerShell "
                "syntax (&& and || chain as in bash; $env:NAME for variables; here-strings @' '@ for files). "
                f"Installed: {tools}; curl.exe, tar.exe. A new tool's PATH entry may need the current session "
                "refreshed: $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + "
                "[Environment]::GetEnvironmentVariable('Path','User'). Network: on. No API keys, no accounts, "
                "no display (the VM is headless).")

    # -- lifecycle

    def _pwfile(self, user: str) -> str:
        return str(self.state_dir / f"{self.base}.{user}.pw")

    def start(self) -> None:
        if self.started:
            return
        hint = "; run `pickfit verify --runner vbox --prepare-base` first"
        self.manifest = load_manifest(self.base, self.state_dir, hint)
        self.router_manifest = load_manifest(self.router.name, self.state_dir, hint)
        if not self.manifest.get("hardened"):
            raise BoxError(f"base VM {self.base!r} is not hardened; rebuild it with --prepare-base")
        self.image = image_label(self.manifest, self.router_manifest)
        began = time.monotonic()
        try:
            self._refuse_foreign_run()
            self.lan = host_lan_targets()
            self.extra = host_public_ipv4()
            self.vbox.poweroff(self.base)
            self.vbox.restore(self.base)
            self.vbox("setextradata", self.base, "pickfit/session", self.session)
            self._attach(online=True)
            self.router.reset(self.extra, self.router_manifest)
            self._start_reaper()
            self.vbox("startvm", self.base, "--type", "headless", timeout_s=180)
            self._wait_additions()
            self._setup()
        except BaseException:
            self.close()
            raise
        self.started = True
        self.start_s = round(time.monotonic() - began, 2)
        self._timer = threading.Timer(self.limits.lifetime_s, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def _refuse_foreign_run(self) -> None:
        """One box at a time: a running base that another live process started is not ours to take."""
        if self.vbox.state(self.base) != "running":
            return
        owner = self.vbox("getextradata", self.base, "pickfit/session", check=False).stdout
        started = self.vbox("getextradata", self.base, "pickfit/started", check=False).stdout
        m = re.search(r"Value: (\d+)", started)
        if m and time.time() - int(m.group(1)) < STALE_S:
            raise BoxError(f"{self.base} is already running for another box ({owner.strip()}); run one at a time")
        self.log(f"vbox: {self.base} was left running by a dead process; powering it off")

    def _attach(self, *, online: bool) -> None:
        """Offline (and before the guest is booted): NIC detached. Online: the router's internal network."""
        running = self.vbox.state(self.base) == "running"
        if running:
            if online:
                self.vbox("controlvm", self.base, "nic1", "intnet", INTNET)
                self.vbox("controlvm", self.base, "setlinkstate1", "on")
            else:
                self.vbox("controlvm", self.base, "setlinkstate1", "off")
                self.vbox("controlvm", self.base, "nic1", "null")
        else:
            args = ["--nic1", "intnet", "--intnet1", INTNET, "--cable-connected1", "on"] if online else \
                ["--nic1", "null", "--cable-connected1", "off"]
            self.vbox("modifyvm", self.base, *args)
            self.vbox("setextradata", self.base, "pickfit/started", str(int(time.time())))

    def _wait_additions(self) -> None:
        deadline = time.monotonic() + ADDITIONS_WAIT_S
        last = ""
        while time.monotonic() < deadline:
            if self.vbox.state(self.base) != "running":
                raise BoxError(f"{self.base} stopped while booting")
            run = self.vbox("guestproperty", "get", self.base, "/VirtualBox/GuestAdd/Version", check=False)
            if "Value:" in run.stdout:
                try:
                    probe = self._admin("Write-Output ready", 60)
                except BoxError as err:
                    last = str(err)
                else:
                    if "ready" in probe[1]:
                        return
                    last = probe[2][-200:]
            time.sleep(5)
        raise BoxError(f"the guest's Guest Additions did not answer within {ADDITIONS_WAIT_S}s: {last}")

    def _setup(self) -> None:
        check = self._admin(HARDENED_CHECK, 120)
        if check[0] != 0:
            raise BoxError(f"the base VM is not hardened ({(check[1] + check[2]).strip()[-300:]})")
        minutes = self.limits.lifetime_s + 120
        setup = self._admin(
            f"New-Item -ItemType Directory -Force -Path {ps_quote(WIN_WORKDIR)} | Out-Null; "
            f"icacls {ps_quote(WIN_WORKDIR)} /grant 'sbx:(OI)(CI)F' | Out-Null; "
            f"shutdown.exe /s /f /t {minutes} /d p:0:0 /c pickfit-lifetime; Write-Output setup-ok", 120)
        if "setup-ok" not in setup[1]:
            raise BoxError(f"box setup failed: {(setup[1] + setup[2]).strip()[-400:]}")
        self.network_enabled = True
        self._wait_network()
        self._check_containment(online=True)

    def _start_reaper(self) -> None:
        """A detached host process that powers both VMs off if this session still owns them later."""
        vbm = json.dumps(self.vbox.argv0)
        script = (f"import json,subprocess,time\ntime.sleep({self.limits.lifetime_s + REAP_GRACE_S})\n"
                  f"v=json.loads({vbm!r})\n"
                  f"o=subprocess.run(v+['getextradata','{self.base}','pickfit/session'],capture_output=True,text=True).stdout\n"
                  f"if '{self.session}' in o:\n"
                  f"    for vm in ('{self.base}','{self.router.name}'):\n"
                  f"        subprocess.run(v+['controlvm',vm,'poweroff'],capture_output=True)\n")
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        self._reaper = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=flags, close_fds=True)

    def _stop_reaper(self) -> None:
        if self._reaper is not None and self._reaper.poll() is None:
            self._reaper.kill()
            self._reaper.wait()
        self._reaper = None

    def _expire(self) -> None:
        self.log(f"vbox: {self.base} reached its {self.limits.lifetime_s}s lifetime; stopping it")
        self.close()

    def close(self) -> None:
        """Power off and restore the clean snapshot (guest and router). Never raises."""
        with self._lock:
            self.started = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            for step in (lambda: self.vbox.poweroff(self.base), lambda: self.vbox.restore(self.base),
                         lambda: self.vbox("setextradata", self.base, "pickfit/session", "")):
                try:
                    step()
                except BoxError as err:
                    self.log(f"vbox: close {self.base}: {err}")
            self.router.stop()
            self._stop_reaper()

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def run_argv(self, user: str, command: str, timeout_s: int, cwd: str, nonce: str) -> list[str]:
        """`guestcontrol run` argv for run.ps1 (tests check it). Arguments after `--` exclude argv[0]."""
        args = [*self.vbox.argv0, "guestcontrol", self.base, "run", "--username", user,
                "--passwordfile", self._pwfile(user), "--exe", WINPS, "--timeout", str((timeout_s + 30) * 1000),
                "--wait-stdout", "--wait-stderr"]
        for key, value in WIN_ENV.items():
            args += ["--putenv", f"{key}={value}"]
        return [*args, "--", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", RUN_PS1, "-Timeout", str(int(timeout_s)), "-Cwd", cwd, "-Nonce", nonce,
                "-Enc", encode_ps(command)]

    def _run(self, user: str, command: str, timeout_s: int, cwd: str, *,
             head: int | None = None) -> tuple[int, str, str, bool, bool, float]:
        nonce = secrets.token_hex(8)
        argv = self.run_argv(user, command, timeout_s, cwd, nonce)
        kw = {"head": head, "tail": 0} if head else {}
        began = time.monotonic()
        code, out, err, host_timeout, truncated = run_captured(argv, timeout_s + 30 + HOST_GRACE_S, **kw)
        seconds = round(time.monotonic() - began, 2)
        out, guest_code, warning = parse_sentinel(out, nonce, code)
        if guest_code is None:
            if host_timeout:
                guest_code = 124
            elif re.search(r"VBoxManage(\.exe)?: error:", err):
                raise BoxError(f"guestcontrol failed (the VM or its Guest Additions is gone): {err.strip()[-300:]}")
            else:  # no trusted sentinel: fall back to VBoxManage's own code (0 or 1)
                guest_code = 0 if code == 0 else 1
                err += "\n" + (warning or "[pickfit: the command ended without its exit-code line]")
        return guest_code, out, err, host_timeout, truncated, seconds

    def _admin(self, script: str, timeout_s: int = 60) -> tuple[int, str, str]:
        """Harness-only administrator command (checks, probes); never used for model commands."""
        code, out, err, _, _, _ = self._run(ADMIN_USER, script, timeout_s, r"C:\Windows\Temp")
        return code, out, err

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        code, out, err, host_timeout, truncated, seconds = self._run(WIN_USER, command, timeout_s,
                                                                    cwd or self.workdir)
        timed_out = host_timeout or (code == TIMEOUT_EXIT and seconds >= timeout_s - 0.5)
        if host_timeout:
            code = 124
            err += (f"\n[pickfit stopped waiting after {seconds:.0f}s: the command did not exit, or something "
                    "it started still holds its output open; start servers and daemons with run_background]")
        return ExecResult(command=command, exit_code=code, stdout=out, stderr=err, seconds=seconds,
                          timed_out=timed_out, truncated=truncated)

    def _guest_path(self, path: str) -> str:
        if re.match(r"^[A-Za-z]:[\\/]", path):
            return path.replace("/", "\\")
        if path.startswith("~"):
            return WIN_HOME + path[1:].replace("/", "\\")
        return WIN_WORKDIR + "\\" + path.replace("/", "\\")

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        target = self._guest_path(path)
        parent = target.rsplit("\\", 1)[0]
        self.vbox("guestcontrol", self.base, "mkdir", "--username", WIN_USER, "--passwordfile",
                  self._pwfile(WIN_USER), "--parents", parent, timeout_s=60, check=False)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "f"
            src.write_bytes(data)
            proc = self.vbox("guestcontrol", self.base, "copyto", "--username", WIN_USER, "--passwordfile",
                             self._pwfile(WIN_USER), str(src), target, timeout_s=120, check=False)
        if proc.returncode != 0:
            raise BoxError(f"cannot write {path}: {proc.stderr.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        target = self._guest_path(path)
        script = (f"$f = [IO.File]::OpenRead({ps_quote(target)}); $b = New-Object byte[] {int(max_bytes)}; "
                  "$n = $f.Read($b, 0, $b.Length); $f.Close(); "
                  "'PFB64:' + [Convert]::ToBase64String($b, 0, $n)")
        code, out, err, _, _, _ = self._run(WIN_USER, script, 30, WIN_WORKDIR, head=max_bytes * 2 + 4096)
        m = re.search(r"PFB64:([A-Za-z0-9+/=]*)", out)
        if code != 0 or m is None:
            raise BoxError(f"cannot read {path}: {(err or out).strip()[-300:]}")
        return base64.b64decode(m.group(1))[:max_bytes]

    def background(self, command: str, port: int | None, wait_s: int, tag: int | str) -> str:
        """PowerShell for run_background: start detached with output in a log, wait for the port or a few
        seconds, print the pid and the log tail; exit 0 only if the process came up."""
        log = f"$HOME\\.pickfit-bg\\{tag}.log"
        start = (f"New-Item -ItemType Directory -Force $HOME\\.pickfit-bg | Out-Null; "
                 f"$p = Start-Process -FilePath {ps_quote(PWSH)} -ArgumentList '-NoLogo','-NoProfile',"
                 f"'-NonInteractive','-EncodedCommand','{encode_ps(command)}' -RedirectStandardOutput \"{log}\" "
                 f"-RedirectStandardError \"{log}.err\" -WindowStyle Hidden -PassThru; \"pid $($p.Id)\"; $ok = $false; ")
        if port:
            probe = (f"foreach ($i in 1..{max(wait_s, 1)}) {{ $c = New-Object Net.Sockets.TcpClient; "
                     f"try {{ $c.Connect('127.0.0.1', {port}); \"port {port} open after ${{i}}s\"; $ok = $true; "
                     "break } catch {} finally { $c.Close() }; if ($p.HasExited) { 'process exited'; break }; "
                     "Start-Sleep 1 }; ")
        else:
            probe = (f"Start-Sleep {min(wait_s, 5)}; if (-not $p.HasExited) {{ 'still running'; $ok = $true }} "
                     "else { 'process exited' }; ")
        tail = (f"'--- log tail ---'; Get-Content \"{log}\",\"{log}.err\" -Tail 40 -ErrorAction SilentlyContinue; "
                "if ($ok) { exit 0 } else { exit 1 }")
        return start + probe + tail

    # -- network

    def _wait_network(self) -> None:
        """Wait until Windows has the router's DHCP lease (a default route via the router)."""
        deadline = time.monotonic() + NETWORK_WAIT_S
        while time.monotonic() < deadline:
            out = self._admin("(Get-NetRoute -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue)."
                              "NextHop -join ','", 30)[1]
            if ROUTER_IP in out:
                return
            time.sleep(3)
        raise BoxError(f"the guest got no route through the router within {NETWORK_WAIT_S}s")

    def probe_targets(self) -> dict[str, str]:
        """name -> host:port that must be silently dropped from the guest."""
        targets: dict[str, str] = {}
        lan = self.lan.get("hostlan")
        if lan:
            for port in HOST_PORTS:
                targets[f"hostlan{port}"] = f"{lan}:{port}"
        gw = self.lan.get("gateway")
        if gw:
            for port in LAN_PORTS:
                targets[f"gateway{port}"] = f"{gw}:{port}"
        for port in (135, 445):
            targets[f"vboxnathost{port}"] = f"{VBOX_NAT_HOST}:{port}"
        targets["vboxnatdns"] = f"{VBOX_NAT_DNS}:53"
        targets["hostonly445"] = "192.168.56.1:445"
        targets["metadata"] = "169.254.169.254:80"
        targets["private"] = "10.255.255.1:80"
        targets["routerssh"] = f"{ROUTER_IP}:22"
        for ip in self.extra:
            targets[f"hostpublic{ip.replace('.', '_')}"] = f"{ip}:445"
        return targets

    def _probe(self, targets: dict[str, str], *, url: str = "", multicast: bool = False,
               ms: int = 3000) -> dict[str, str]:
        arg = ",".join(f"{k}={v}" for k, v in targets.items())
        script = (f"& {ps_quote(PROBE_PS1)} -Targets {ps_quote(arg)} -Ms {ms}"
                  + (f" -Url {ps_quote(url)}" if url else "") + (" -Multicast" if multicast else ""))
        code, out, err = self._admin(script, 90)
        found = {m.group(1): m.group(2) for m in PROBE_LINE.finditer(out)}
        missing = [n for n in [*targets, *(["public"] if url else []), *(["mdns", "ssdp"] if multicast else [])]
                   if n not in found]
        if missing:
            raise BoxError(f"containment probe could not run (no result for {', '.join(missing)}): "
                           f"{(out + err).strip()[-200:]}")
        return found

    def _check_containment(self, *, online: bool) -> None:
        """Fail closed unless every must-drop target times out, the internet matches the mode, and (online)
        multicast is not answered and the router's DNS port answers (the probe is not a no-op)."""
        targets = self.probe_targets()
        if online:
            targets["routerdns"] = f"{ROUTER_IP}:53"
        res = self._probe(targets, url=PUBLIC_URL, multicast=online)
        bad: list[str] = []
        for name in self.probe_targets():
            got = res[name]
            if online and got != "timeout":
                bad.append(f"{name} {got}")
            if not online and got in ("open", "refused"):
                bad.append(f"{name} {got}")
        if online:
            if res["routerdns"] != "open":
                bad.append(f"router DNS port {res['routerdns']} (the probe should see it open)")
            if res["public"] != "curl0":
                bad.append(f"internet unreachable online ({res['public']})")
            for name in ("mdns", "ssdp"):
                if res[name] != "no-answer":
                    bad.append(f"{name} {res[name]}")
        elif res["public"] == "curl0":
            bad.append("internet reachable with the network cut")
        if bad:
            raise BoxError(f"containment check ({'online' if online else 'offline'}) failed: {'; '.join(bad)}")

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        if enabled:
            self._check_containment(online=False)  # the cut held for as long as the box said offline
            self._attach(online=True)
            self._admin("ipconfig /renew *> $null; Write-Output renewed", 60)
            self._wait_network()
        else:
            self._attach(online=False)
        self._check_containment(online=enabled)
        self.network_enabled = enabled

    def validate_containment(self) -> list[tuple[str, bool, str, str]]:
        """Positive/negative controls for the limits test (as administrator). Mutates the live network, so
        only the limits test (no untrusted code has run) calls it; leaves the box online behind the router."""
        results: list[tuple[str, bool, str, str]] = []

        def rec(name: str, ok: bool, expect: str, detail: str) -> None:
            results.append((name, ok, expect, detail))

        lan = self.lan.get("hostlan")
        rec("host_lan_found", bool(lan), "the host's LAN address is known", str(lan))
        # Positive control: on plain VirtualBox NAT (no router) the host's ports answer the same probe.
        self.vbox("controlvm", self.base, "nic1", "nat")
        self.vbox("controlvm", self.base, "setlinkstate1", "on")
        self._admin("ipconfig /renew *> $null", 60)
        time.sleep(3)
        host_targets = {f"hostlan{p}": f"{lan}:{p}" for p in HOST_PORTS} if lan else {}
        host_targets.update({f"vboxnathost{p}": f"{VBOX_NAT_HOST}:{p}" for p in (135, 445)})
        pos = self._probe(host_targets)
        reached = sorted(n for n, r in pos.items() if r in ("open", "refused"))
        rec("probe_sees_host_without_router", bool(reached),
            "without the router (plain NAT) the probe reaches host ports (proves it is not a no-op)",
            ", ".join(f"{n}={pos[n]}" for n in sorted(pos)))
        # Back behind the router: the same targets and the rest must drop; the router's DNS answers.
        self._attach(online=True)
        self._admin("ipconfig /renew *> $null", 60)
        self._wait_network()
        targets = {**self.probe_targets(), "routerdns": f"{ROUTER_IP}:53"}
        on = self._probe(targets, url=PUBLIC_URL, multicast=True)
        for name in self.probe_targets():
            rec(f"{name}_dropped_online", on[name] == "timeout", "dropped by the router (connect times out)",
                on[name])
        rec("router_dns_open", on["routerdns"] == "open", "the router's DNS port answers (probe sees open)",
            on["routerdns"])
        rec("internet_online", on["public"] == "curl0", "public HTTPS answers online", on["public"])
        for name in ("mdns", "ssdp"):
            rec(f"{name}_unanswered_online", on[name] == "no-answer", f"no {name} answer online", on[name])
        # Offline: the NIC is detached; nothing answers, not even the router.
        self._attach(online=False)
        self.network_enabled = False
        off = self._probe({**self.probe_targets(), "routerdns": f"{ROUTER_IP}:53"}, url=PUBLIC_URL)
        rec("internet_offline", off["public"] != "curl0", "public HTTPS fails with the NIC detached", off["public"])
        reached_off = sorted(n for n, r in off.items() if r in ("open", "refused"))
        rec("nothing_reached_offline", not reached_off, "no target answers with the NIC detached",
            ", ".join(reached_off) or "none")
        self._attach(online=True)
        self._admin("ipconfig /renew *> $null", 60)
        self._wait_network()
        self.network_enabled = True
        self._check_containment(online=True)
        return results


# ---------------------------------------------------------------- building the router


ALPINE_ISO = "alpine-virt-3.24.3-x86_64.iso"
ALPINE_SHA256 = "cdc1bc0efc64d8d611bf3733f54868172a545888dfd726f518bf279bcb0ff1af"


def console_script(vbox: VBox, vm: str, serial_log: Path, script: str, timeout_s: float = 600) -> tuple[int, str]:
    """Type `script` into the VM's root console and return (exit code, output); output comes back on the
    serial port (a host file), the only channel the router has to the host."""
    if "\t" in script:
        raise ValueError("a tab would trigger shell completion on the console")
    tag = secrets.token_hex(3)
    start = serial_log.stat().st_size if serial_log.exists() else 0
    vbox.type_text(vm, f"cat > /tmp/pf-{tag}.sh <<'PF_EOF_{tag}'\n{script.rstrip()}\nPF_EOF_{tag}\n")
    time.sleep(0.5)
    vbox.type_text(vm, f"sh /tmp/pf-{tag}.sh > /dev/ttyS0 2>&1; echo PF_DONE_{tag}=$? > /dev/ttyS0\n")
    pat = re.compile(rf"PF_DONE_{tag}=(\d+)")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = serial_log.read_bytes()[start:].decode("utf-8", "replace") if serial_log.exists() else ""
        m = pat.search(data)
        if m:
            return int(m.group(1)), data[:m.start()].replace("\r", "")
        time.sleep(1)
    raise BoxError(f"{vm}: console script timed out after {timeout_s:.0f}s")


def _wait_serial(serial_log: Path, pattern: str, timeout_s: float, start: int = 0) -> re.Match[str]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = serial_log.read_bytes()[start:].decode("utf-8", "replace") if serial_log.exists() else ""
        m = re.search(pattern, data)
        if m:
            return m
        time.sleep(1)
    raise BoxError(f"{pattern!r} did not appear on {serial_log} within {timeout_s:.0f}s")


def prepare_router(*, iso: Path | None = None, name: str = ROUTER_VM, vboxmanage: Sequence[str] | str | None = None,
                   state_dir: Path | None = None, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Build the router VM from the Alpine virt ISO, check its first boot, and take the `clean` snapshot.

    The ISO is typed into through the VM's keyboard (Alpine has no guest agent) and answers on the serial
    port, which is a host file. Writes ~/.pickfit/vbox/<name>.json with the rule-set hash every box checks.
    """
    import hashlib

    vbox = VBox(vboxmanage)
    state = state_dir or STATE_DIR
    iso = iso or state / "iso" / ALPINE_ISO
    digest = hashlib.sha256(iso.read_bytes()).hexdigest()
    if digest != ALPINE_SHA256:
        raise BoxError(f"{iso} sha256 {digest} is not the published {ALPINE_SHA256}")
    if vbox("showvminfo", name, check=False).returncode == 0:
        raise BoxError(f"{name!r} already exists; `VBoxManage unregistervm {name} --delete` to rebuild it")
    manifest_path(name, state).unlink(missing_ok=True)
    serial = state / "logs" / f"{name}-serial.log"
    serial.parent.mkdir(parents=True, exist_ok=True)
    vms = state / "vms"
    disk = vms / name / f"{name}.vdi"
    began = time.monotonic()
    vbox("createvm", "--name", name, "--ostype", "Linux26_64", "--basefolder", str(vms), "--register")
    try:
        vbox("modifyvm", name, "--memory", "256", "--cpus", "1", "--firmware", "bios", "--audio-enabled", "off",
             "--usb-ohci", "off", "--usb-ehci", "off", "--usb-xhci", "off", "--clipboard-mode", "disabled",
             "--drag-and-drop", "disabled", "--vrde", "off", "--graphicscontroller", "vmsvga", "--vram", "9",
             "--boot1", "disk", "--boot2", "dvd", "--boot3", "none", "--boot4", "none",
             "--nic1", "intnet", "--intnet1", INTNET, "--nictype1", "virtio",
             "--nic2", "nat", "--nictype2", "virtio", "--nat-localhostreachable2", "off",
             "--uart1", "0x3F8", "4", "--uart-mode1", "file", str(serial))
        vbox("createmedium", "disk", "--filename", str(disk), "--size", "1024", "--format", "VDI")
        vbox("storagectl", name, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci", "--portcount", "2")
        vbox("storageattach", name, "--storagectl", "SATA", "--port", "0", "--device", "0", "--type", "hdd",
             "--medium", str(disk))
        vbox("storageattach", name, "--storagectl", "SATA", "--port", "1", "--device", "0", "--type", "dvddrive",
             "--medium", str(iso))
        vbox("startvm", name, "--type", "headless", timeout_s=120)
        _wait_serial(serial, r"login:", 180)  # the live ISO runs a getty on ttyS0 as well as on the console
        vbox.type_text(name, "root\n")
        time.sleep(3)
        log(f"vbox: {name}: installing Alpine to disk")
        code, out = console_script(vbox, name, serial, ROUTER_INSTALL, 600)
        if code != 0 or "setup-disk done" not in out:
            raise BoxError(f"router install failed: {out.strip()[-600:]}")
        code, out = console_script(vbox, name, serial, ROUTER_CONFIG, 600)
        if code != 0 or "pickfit router installed" not in out:
            raise BoxError(f"router config failed: {out.strip()[-600:]}")
        vbox.type_text(name, "poweroff\n")
        vbox.poweroff(name, 90)
        vbox("storageattach", name, "--storagectl", "SATA", "--port", "1", "--device", "0", "--type", "dvddrive",
             "--medium", "emptydrive")
        vbox("setextradata", name, "VBoxInternal/Devices/pcbios/0/Config/DmiSystemSerial", "pf:")
        start = serial.stat().st_size if serial.exists() else 0
        vbox("startvm", name, "--type", "headless", timeout_s=120)
        m = _wait_serial(serial, READY.pattern, ROUTER_WAIT_S, start if serial.stat().st_size >= start else 0)
        rules, extra, fwd, v6, dns, up = m.groups()
        if (extra, fwd, v6, dns) != ("none", "1", "1", "up") or up == "0":
            raise BoxError(f"the router's first boot is wrong: {m.group(0)}")
        vbox.poweroff(name, 60)
        vbox("snapshot", name, "take", SNAPSHOT, "--description", "pickfit router, powered off")
    except BaseException:
        vbox.poweroff(name, 60) if vbox("showvminfo", name, check=False).returncode == 0 else None
        vbox("unregistervm", name, "--delete", check=False, timeout_s=120)
        log(f"vbox: router build failed; deleted {name}")
        raise
    manifest = {"name": name, "alpine": "3.24.3", "iso_sha256": digest, "rules": rules,
                "build_id": secrets.token_hex(6), "prepared_at": taipei_now().isoformat(timespec="seconds")}
    manifest_path(name, state).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"vbox: router {name} ready in {time.monotonic() - began:.0f}s (rules {rules})")
    return manifest


def image_label(manifest: dict[str, Any], router: dict[str, Any]) -> str:
    """What `VerificationRun.image` records: guest edition and build, base build id, router build id."""
    return (f"Windows 11 Enterprise Evaluation {manifest.get('windows', '?')} (VirtualBox "
            f"{manifest.get('virtualbox', '?')}) +{manifest.get('base', BASE_VM)}@{manifest.get('build_id', 'nobuild')}"
            f" router@{router.get('build_id', 'nobuild')}")[:120]


# Every box runs this as the administrator before any model command; non-zero refuses the base.
HARDENED_CHECK = r"""
$bad = @()
$admins = (Get-LocalGroupMember -SID S-1-5-32-544 | ForEach-Object { $_.Name.Split('\')[-1] })
if ($admins -contains 'sbx') { $bad += 'sbx is an administrator' }
$wl = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ($wl.AutoAdminLogon -eq '1') { $bad += 'auto logon is on' }
if ($wl.PSObject.Properties.Name -contains 'DefaultPassword') { $bad += 'a logon password is stored in Winlogon' }
foreach ($f in 'C:\Windows\Panther\unattend.xml','C:\Windows\Panther\Autounattend.xml','C:\Windows\System32\Sysprep\unattend.xml','C:\Unattend.xml') {
  if (Test-Path $f) { $bad += "answer file left: $f" } }
foreach ($p in 'C:\ProgramData\pickfit','C:\ProgramData\pickfit\run.ps1','C:\ProgramData\pickfit\probe.ps1') {
  if (-not (Test-Path $p)) { $bad += "$p missing"; continue }
  $acl = Get-Acl $p
  foreach ($a in $acl.Access) {
    $who = $a.IdentityReference.Value
    if ($who -match 'sbx|Users|Everyone|Authenticated' -and $a.AccessControlType -eq 'Allow' -and
        $a.FileSystemRights.ToString() -match 'Write|Modify|FullControl|ChangePermissions|TakeOwnership|Delete') {
      $bad += "$who can change $p" } } }
$rdp = (Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server').fDenyTSConnections
if ($rdp -ne 1) { $bad += 'Remote Desktop is on' }
if ((Get-Service WinRM -ErrorAction SilentlyContinue).Status -eq 'Running') { $bad += 'WinRM is running' }
if ($bad) { $bad -join '; '; exit 1 } else { 'hardened'; exit 0 }
"""
