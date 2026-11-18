"""Rented or spare Macs as tart hosts: create, prepare, check, test end to end, delete (`pickfit mac-host ...`).

The sandbox layer must not depend on one provider (loop/issues.md H-012), so this is two separate parts:

- a provider that only creates, describes and deletes a machine: Scaleway Apple silicon through the `scw` CLI
  today, or `ssh` for a Mac that already exists (yours, MacStadium, an EC2 mac1/mac2 host). Another renter is
  one more Provider subclass;
- everything else over plain SSH, the same for every provider: tart and the softnet that runs on the host's
  macOS (0.24+ needs macOS 26's vmnet; macOS 15 gets 0.23.0), the source image for that macOS, the one root step,
  a readiness check that boots a VM, and the end-to-end test that drives `pickfit verify --runner tart` with
  PICKFIT_TART_HOST set.

The root step is the only part a person does: softnet needs a setuid-root bit, and Virtualization.framework only
starts a macOS guest from an SSH session once the user is logged in at the console (auto-login; without it the VM
fails with "Internal Virtualization error"). `pickfit mac-host root NAME` runs ~/.pickfit/rootsetup.py on the host
over `ssh -t`, so the person types the sudo password there once; it is never stored or printed here. An unattended
pipeline can pipe it in instead (`--password-stdin`), from its own secret store. Scaleway's server JSON carries
sudo_password, and every reply is scrubbed of password fields before it is kept or logged. Only the macOS lane of
`pickfit watch`, when told to (`--mac-root-from-provider`), reads it for a Mac it rented itself
(Provider.root_password) and pipes it straight into the root step (root_unattended).

Measured 2026-11-17/18 on a Scaleway M4-SP in fr-par-1 (H-012): a macOS 26 host with Scaleway's MDM could not start
any macOS guest ("Failed to create new HostKey"); reinstalled as macOS 15 with auto-login, a macOS 15 guest answers
`tart exec` 8 s after `tart run`, and the pickfit-macos-15 base builds in 108 s. So the default macOS is 15.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pickfit.verify.box import BoxError
from pickfit.verify.tart_host import HOST_PYTHON, STATE_DIR, SshHost

HOSTS_DIR = Path.home() / ".pickfit" / "mac-hosts"  # one JSON per host: provider ids, the SSH target, never a password
DEFAULT_KEY = Path.home() / ".pickfit" / "ssh" / "mac-host"
TART_VERSION = "2.41.1"
TART_URL = "https://github.com/openai/tart/releases/download/{v}/{f}"  # moved from cirruslabs/ (redirects), 11/2026
SOFTNET_URL = "https://github.com/openai/softnet/releases/download/{v}/{f}"


@dataclass(frozen=True)
class MacOS:
    major: int
    softnet: str  # the newest softnet that loads there
    source: str  # the OCI image prepare_base starts from
    base: str  # the base VM pickfit builds from it


# softnet 0.24.0+ links _vmnet_interface_start_with_network, which macOS 15 lacks ("Symbol not found"); 0.23.0 has
# the control channel and the same policy semantics. A guest cannot be newer than its host, so a macOS 15 host
# runs macOS 15 guests.
MACOS = {15: MacOS(15, "0.23.0", "ghcr.io/cirruslabs/macos-sequoia-base:latest", "pickfit-macos-15"),
         26: MacOS(26, "0.24.1", "ghcr.io/cirruslabs/macos-tahoe-base:latest", "pickfit-macos-26")}
DEFAULT_MACOS = 15


def macos_for(major: int | None) -> MacOS:
    if major is None:
        raise BoxError("the host's macOS version is not known yet; run `pickfit mac-host check` first")
    if major in MACOS:
        return MACOS[major]
    newest = max(MACOS)
    if major > newest:  # a newer macOS still has 26's vmnet; run what was measured on 26 until told otherwise
        return MACOS[newest]
    raise BoxError(f"macOS {major} hosts are not supported (tart needs macOS 15 or newer here)")


def scrub(value: Any) -> Any:
    """Drop every key that names a password, at any depth, before anything is kept, compared or logged."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if "password" not in str(k).lower()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


@dataclass
class HostRecord:
    name: str
    provider: str
    target: str = ""  # user@address, once known
    key: str = ""
    port: int | None = None
    macos: int | None = None
    server_id: str = ""
    zone: str = ""
    server_type: str = ""
    created_at: str = ""
    deletable_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return HOSTS_DIR / f"{self.name}.json"

    def save(self, hosts_dir: Path | None = None) -> Path:
        path = (hosts_dir or HOSTS_DIR) / f"{self.name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(scrub(asdict(self)), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, name: str, hosts_dir: Path | None = None) -> HostRecord:
        path = (hosts_dir or HOSTS_DIR) / f"{name}.json"
        if not path.exists():
            known = ", ".join(sorted(p.stem for p in (hosts_dir or HOSTS_DIR).glob("*.json"))) or "none"
            raise BoxError(f"no mac host named {name!r} (known: {known}); `pickfit mac-host up` or `add` makes one")
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def ssh_host(self, ssh: str = "ssh") -> SshHost:
        if not self.target:
            raise BoxError(f"{self.name} has no SSH address yet")
        return SshHost(self.target, key=self.key or None, port=self.port, ssh=ssh)

    def env(self) -> dict[str, str]:
        """What `pickfit verify --runner tart` needs to run on this host."""
        mac = macos_for(self.macos)
        env = {"PICKFIT_TART_HOST": self.target, "PICKFIT_TART_SOURCE": mac.source, "PICKFIT_TART_BASE": mac.base}
        if self.key:
            env["PICKFIT_TART_SSH_KEY"] = self.key
        if self.port:
            env["PICKFIT_TART_SSH_PORT"] = str(self.port)
        return env


# ---------------------------------------------------------------- providers


class Provider(ABC):
    key: str

    @abstractmethod
    def create(self, name: str, macos: int, public_key: str, log: Callable[[str], None]) -> HostRecord: ...

    def refresh(self, rec: HostRecord) -> HostRecord:
        return rec

    @abstractmethod
    def delete(self, rec: HostRecord, log: Callable[[str], None]) -> None: ...

    def root_password(self, rec: HostRecord) -> str | None:
        """The SSH user's sudo password from the provider, for the root step only (mac_batch, when told to): never
        logged, saved or put in argv. None when the provider has none to give."""
        return None


class SshProvider(Provider):
    """A Mac that already exists: nothing to create, and `down` only forgets it."""

    key = "ssh"

    def create(self, name: str, macos: int, public_key: str, log: Callable[[str], None]) -> HostRecord:
        raise BoxError("an ssh host already exists; add it with `pickfit mac-host add NAME --target user@host`")

    def delete(self, rec: HostRecord, log: Callable[[str], None]) -> None:
        log(f"{rec.name}: forgetting {rec.target} (an ssh host is not deleted)")


class ScalewayProvider(Provider):
    """Scaleway Apple silicon through `scw` (logged in with `scw login`). A Mac mini is billed for at least 24 h."""

    key = "scaleway"
    TYPES = ("M4-S", "M4-SP", "M4-M")  # cheapest first; €0.22, €0.24, €0.29 an hour on 2026-11-17

    def __init__(self, zone: str = "fr-par-1", scw: str = "scw", types: tuple[str, ...] = TYPES) -> None:
        self.zone, self.scw, self.types = zone, scw, types

    def _call(self, *args: str, timeout: float = 120) -> Any:
        done = subprocess.run([self.scw, *args, f"zone={self.zone}", "-o", "json"], capture_output=True,
                              text=True, timeout=timeout)
        if done.returncode != 0:
            raise BoxError(f"scw {' '.join(args[:3])} failed: {(done.stderr or done.stdout).strip()[-400:]}")
        return scrub(json.loads(done.stdout or "null"))

    def _iam(self, *args: str) -> Any:
        done = subprocess.run([self.scw, "iam", *args, "-o", "json"], capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise BoxError(f"scw iam {args[0]} failed: {(done.stderr or done.stdout).strip()[-300:]}")
        return scrub(json.loads(done.stdout or "null"))

    def os_id(self, macos: int) -> str:
        for entry in self._call("apple-silicon", "os", "list"):
            if str(entry.get("version")) == str(macos) and not entry.get("is_beta"):
                return entry["id"]
        raise BoxError(f"Scaleway offers no macOS {macos} image in {self.zone}")

    def in_stock(self) -> list[str]:
        stock = {t["name"]: t.get("stock") for t in self._call("apple-silicon", "server-type", "list")}
        return [t for t in self.types if stock.get(t) in ("available", "low_stock")]

    def ensure_key(self, public_key: str, name: str) -> None:
        """Scaleway puts the project's SSH keys on a new Mac; add ours once."""
        mine = " ".join(public_key.split()[:2])
        for entry in self._iam("ssh-key", "list") or []:
            if " ".join(str(entry.get("public_key", "")).split()[:2]) == mine:
                return
        self._iam("ssh-key", "create", f"name={name}", f"public-key={public_key.strip()}")

    def create(self, name: str, macos: int, public_key: str, log: Callable[[str], None]) -> HostRecord:
        self.ensure_key(public_key, f"pickfit-{name}")
        os_id = self.os_id(macos)
        types = self.in_stock()
        if not types:
            raise BoxError(f"no Scaleway Mac mini of type {', '.join(self.types)} is in stock in {self.zone}; "
                           "try again later or another zone (--zone)")
        server, errors = None, []
        for kind in types:
            try:
                log(f"scaleway: creating a {kind} Mac mini ({self.zone}, macOS {macos}); billed for 24 h at least")
                server = self._call("apple-silicon", "server", "create", f"type={kind}", f"name={name}",
                                    f"os-id={os_id}")
                break
            except BoxError as err:  # stock moves between the list and the create
                errors.append(f"{kind}: {err}")
        if server is None:
            raise BoxError("could not create a Mac mini: " + "; ".join(errors))
        log(f"scaleway: {server['id']} created; waiting until it is ready (often 10-30 minutes)")
        server = self._call("apple-silicon", "server", "wait", server["id"], "timeout=90m", timeout=95 * 60)
        return self._record(name, server)

    def _record(self, name: str, server: dict[str, Any]) -> HostRecord:
        os_info = server.get("os") or {}
        version = str(os_info.get("version") or "")
        return HostRecord(name=name, provider=self.key, target=f"{server['ssh_username']}@{server['ip']}",
                          macos=int(version) if version.isdigit() else None, server_id=server["id"], zone=self.zone,
                          server_type=server.get("type", ""), created_at=server.get("created_at", ""),
                          deletable_at=server.get("deletable_at", ""), extra={"status": server.get("status")})

    def refresh(self, rec: HostRecord) -> HostRecord:
        server = self._call("apple-silicon", "server", "get", rec.server_id)
        fresh = self._record(rec.name, server)
        fresh.key, fresh.port, fresh.macos = rec.key, rec.port, rec.macos or fresh.macos
        return fresh

    def delete(self, rec: HostRecord, log: Callable[[str], None], now: datetime | None = None) -> None:
        server = self._call("apple-silicon", "server", "get", rec.server_id)
        when = server.get("deletable_at") or rec.deletable_at
        if when and (now or datetime.now(UTC)) < datetime.fromisoformat(when.replace("Z", "+00:00")):
            raise BoxError(f"Scaleway bills a Mac mini for 24 h; {rec.server_id} can be deleted after {when}")
        self._call("apple-silicon", "server", "delete", rec.server_id)
        log(f"scaleway: deleted {rec.server_id}")

    def root_password(self, rec: HostRecord) -> str | None:
        # Not through _call, which scrubs it; nothing of this reply but the one field leaves this function, and an
        # error carries only stderr.
        done = subprocess.run([self.scw, "apple-silicon", "server", "get", rec.server_id, f"zone={self.zone}",
                               "-o", "json"], capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise BoxError(f"scw apple-silicon server get failed: {done.stderr.strip()[-300:]}")
        try:
            value = json.loads(done.stdout or "{}").get("sudo_password")
        except (ValueError, AttributeError):
            raise BoxError("scw apple-silicon server get gave no JSON") from None
        return str(value) if value else None


PROVIDERS: dict[str, Callable[..., Provider]] = {"scaleway": ScalewayProvider, "ssh": SshProvider}


def provider_for(rec_or_key: HostRecord | str, **kw: Any) -> Provider:
    key = rec_or_key.provider if isinstance(rec_or_key, HostRecord) else rec_or_key
    if key not in PROVIDERS:
        raise BoxError(f"unknown mac host provider {key!r} (known: {', '.join(sorted(PROVIDERS))})")
    if key == "scaleway" and isinstance(rec_or_key, HostRecord) and rec_or_key.zone:
        kw.setdefault("zone", rec_or_key.zone)
    return PROVIDERS[key](**kw)


# ---------------------------------------------------------------- host preparation (any provider)

# Fetch a release tarball and its checksum list into ~/.local/dl/<tool>-<version>/, check it, unpack it. No sudo.
FETCH = r"""
fetch() {  # tool version url-of-tarball url-of-sums
  d="$HOME/.local/dl/$1-$2"; mkdir -p "$d"; cd "$d"
  curl -fsSL --retry 3 -o "$1.tar.gz" "$3" && curl -fsSL --retry 3 -o sums.txt "$4" || { echo "download failed: $1 $2"; exit 3; }
  want=$(grep " $1.tar.gz\$" sums.txt | cut -d" " -f1); got=$(shasum -a 256 "$1.tar.gz" | cut -d" " -f1)
  [ -n "$want" ] && [ "$want" = "$got" ] || { echo "checksum mismatch: $1 $2"; exit 3; }
  rm -rf x && mkdir x && tar -xzf "$1.tar.gz" -C x
}
"""


def install_script(mac: MacOS, tart: str = TART_VERSION) -> str:
    tart_tgz = TART_URL.format(v=tart, f="tart.tar.gz")
    tart_sums = TART_URL.format(v=tart, f=f"tart_{tart}_checksums.txt")
    sn_tgz = SOFTNET_URL.format(v=mac.softnet, f="softnet.tar.gz")
    sn_sums = SOFTNET_URL.format(v=mac.softnet, f=f"softnet_{mac.softnet}_checksums.txt")
    return f"""set -e
mkdir -p "$HOME/.local/bin" "$HOME/.local/dl" "$HOME/.pickfit/tart"
{FETCH}
if [ "$("$HOME/.local/bin/tart" --version 2>/dev/null)" != "{tart}" ]; then
  fetch tart {tart} {tart_tgz} {tart_sums}
  rm -rf "$HOME/.local/tart.app" && mv x/tart.app "$HOME/.local/tart.app"
  ln -sf "$HOME/.local/tart.app/Contents/MacOS/tart" "$HOME/.local/bin/tart"
  echo "installed tart {tart}"
fi
case "$("$HOME/.local/bin/softnet" --version 2>/dev/null)" in
  "softnet {mac.softnet}"*) ;;
  *) fetch softnet {mac.softnet} {sn_tgz} {sn_sums}
     ./x/softnet --version >/dev/null 2>&1 || {{ echo "softnet {mac.softnet} does not run on macOS $(sw_vers -productVersion)"; exit 4; }}
     rm -f "$HOME/.local/bin/softnet" && cp x/softnet "$HOME/.local/bin/softnet" && chmod 755 "$HOME/.local/bin/softnet"
     echo "installed softnet {mac.softnet} (its setuid bit is gone: run the root step)";;
esac
"$HOME/.local/bin/tart" --version; "$HOME/.local/bin/softnet" --version | head -1
"""


# The one root step, run on the host by a person (`ssh -t`): the password is typed once (or piped with
# --password-stdin), checked with `sudo -v` before anything changes, and never printed or put in argv.
# softnet setuid-root; auto-login for the SSH user (/etc/kcpassword the way loginwindow reads it: the password and a
# NUL, padded to a multiple of 12, XORed with Apple's fixed key; `sysadminctl -autologin set` failed with error:22 on
# Scaleway's hosts); then a reboot so the console session exists.
ROOT_SETUP = r'''"""pickfit mac-host root step: softnet setuid-root, auto-login for this user, reboot."""
import getpass, os, subprocess, sys, tempfile
KEY = bytes([0x7D, 0x89, 0x52, 0x23, 0xD2, 0xBC, 0xDD, 0xEA, 0xA3, 0xB9, 0x1F])
user = getpass.getuser()
softnet = os.path.expanduser("~/.local/bin/softnet")
def sudo(*argv):
    subprocess.run(["/usr/bin/sudo", *argv], check=True)
if "--password-stdin" in sys.argv:
    pw = sys.stdin.buffer.readline().rstrip(b"\r\n")
else:
    pw = getpass.getpass(f"{user} password (the sudo password, typed once): ").encode()
subprocess.run(["/usr/bin/sudo", "-k"], check=False)
if subprocess.run(["/usr/bin/sudo", "-S", "-p", "", "-v"], input=pw + b"\n").returncode != 0:
    sys.exit("that password did not work for sudo; nothing was changed")
sudo("/usr/sbin/chown", "root:wheel", softnet)
sudo("/bin/chmod", "u+s", softnet)
data = pw + b"\0"
data += os.urandom(-len(data) % 12)
fd, tmp = tempfile.mkstemp()
try:
    os.write(fd, bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(data)))
    os.close(fd)
    sudo("/usr/bin/install", "-m", "600", "-o", "root", "-g", "wheel", tmp, "/etc/kcpassword")
finally:
    os.unlink(tmp)
uid = subprocess.run(["/usr/bin/id", "-u", user], capture_output=True, text=True, check=True).stdout.strip()
prefs = "/Library/Preferences/com.apple.loginwindow"
sudo("/usr/bin/defaults", "write", prefs, "autoLoginUser", user)
sudo("/usr/bin/defaults", "write", prefs, "autoLoginUserUID", "-int", uid)
print("softnet is setuid-root and auto-login is on; rebooting")
if "--no-reboot" not in sys.argv:
    sudo("/sbin/shutdown", "-r", "now")
'''
ROOT_SETUP_PATH = ".pickfit/rootsetup.py"  # under the SSH user's home

# What `check` reads, one key=value per line.
FACTS = r"""
echo "macos=$(sw_vers -productVersion)"; echo "arch=$(uname -m)"; echo "user=$(id -un)"
echo "console=$(stat -f %Su /dev/console)"
echo "tart=$(tart --version 2>/dev/null)"; echo "softnet=$(softnet --version 2>/dev/null | head -1)"
s=$(command -v softnet) && echo "softnet_mode=$(stat -L -f '%u %p' "$s")"
echo "images=$(tart list --quiet 2>/dev/null | tr '\n' ' ')"
echo "rootsetup=$([ -f "$HOME/.pickfit/rootsetup.py" ] && echo yes || echo no)"
"""

# Boot a throwaway clone under softnet and wait for the guest agent: proves Virtualization.framework, softnet and
# auto-login together (a macOS 26 Scaleway host failed here with "Failed to create new HostKey").
BOOT_PROBE = r"""
src=$1; vm=pf-hostcheck-$$; log="$HOME/.pickfit/tart/$vm.log"
tart clone "$src" "$vm" >/dev/null 2>&1 || { echo "boot=clone-failed"; exit 1; }
start=$(date +%s); tart run --no-graphics --net-softnet "$vm" >"$log" 2>&1 & pid=$!
ok=0; for i in $(seq 1 60); do tart exec "$vm" true >/dev/null 2>&1 && { ok=1; break; }; kill -0 $pid 2>/dev/null || break; sleep 2; done
took=$(( $(date +%s) - start ))
tart stop "$vm" >/dev/null 2>&1; wait $pid 2>/dev/null; tart delete "$vm" >/dev/null 2>&1
if [ $ok = 1 ]; then echo "boot=ok ${took}s"; rm -f "$log"; else echo "boot=failed $(tail -c 300 "$log" | tr '\n' ' ')"; fi
"""


def _facts(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^(\w+)=(.*)$", text, re.M)}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def root_command(rec: HostRecord, *, password_stdin: bool = False, ssh: str = "ssh") -> list[str]:
    """The argv a person runs for the root step (`ssh -t` so sudo's prompt reaches their terminal)."""
    opts = ["-o", "StrictHostKeyChecking=accept-new"]
    if rec.key:
        opts += ["-i", rec.key, "-o", "IdentitiesOnly=yes"]
    if rec.port:
        opts += ["-p", str(rec.port)]
    remote = f"{HOST_PYTHON} -I {ROOT_SETUP_PATH}" + (" --password-stdin" if password_stdin else "")
    return [ssh, *([] if password_stdin else ["-t"]), *opts, rec.target, remote]


def root_unattended(rec: HostRecord, password: str, *, ssh: str = "ssh",
                    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> int:
    """The root step with the password piped to the host's script (stdin, never argv); its output is not kept, so
    nothing it prints can carry the password. 255 is the reboot dropping the connection: the success path."""
    done = runner(root_command(rec, password_stdin=True, ssh=ssh), input=password + "\n", text=True,
                  capture_output=True, timeout=600)
    return done.returncode


class HostOps:
    """Preparation, checks and the boot probe on one host, over its SshHost (one ControlMaster connection)."""

    def __init__(self, rec: HostRecord, host: Any = None, log: Callable[[str], None] = print,
                 state_dir: Path | None = None) -> None:
        self.rec, self.log = rec, log
        self.host = host or rec.ssh_host()
        self.state_dir = state_dir or STATE_DIR

    def sh(self, script: str, timeout: float, *args: str, input: str | None = None) -> subprocess.CompletedProcess[str]:  # noqa: A002
        return self.host.run(["/bin/bash", "-c", script, "pickfit", *args], timeout=timeout, input=input)

    def wait_ssh(self, timeout_s: float = 1200, every_s: float = 15) -> None:
        end = time.monotonic() + timeout_s
        while True:
            try:
                if self.sh("true", 60).returncode == 0:
                    return
            except subprocess.TimeoutExpired:
                pass
            if time.monotonic() > end:
                raise BoxError(f"{self.rec.target} did not answer SSH within {int(timeout_s)} s")
            time.sleep(every_s)

    def facts(self) -> dict[str, str]:
        done = self.sh(FACTS, 120)
        if done.returncode != 0 and "macos=" not in done.stdout:
            raise BoxError(f"could not read {self.rec.target}: {(done.stdout + done.stderr).strip()[-300:]}")
        return _facts(done.stdout)

    def prepare(self) -> MacOS:
        """tart, the right softnet, the root-step script and the source image: idempotent, no sudo."""
        facts = self.facts()
        major = int(facts.get("macos", "0").split(".")[0] or 0)
        mac = macos_for(major)
        if self.rec.macos != major:
            self.rec.macos = major
        self.log(f"{self.rec.name}: macOS {facts.get('macos')} ({facts.get('arch')}); tart {TART_VERSION}, "
                 f"softnet {mac.softnet}, source {mac.source}")
        done = self.sh(install_script(mac), 900)
        if done.returncode != 0:
            raise BoxError(f"installing tart/softnet on {self.rec.target} failed: "
                           f"{(done.stdout + done.stderr).strip()[-400:]}")
        for line in done.stdout.splitlines():
            if line.startswith("installed "):
                self.log(f"{self.rec.name}: {line}")
        wrote = self.sh(f'mkdir -p "$HOME/.pickfit" && cat > "$HOME/{ROOT_SETUP_PATH}" && '
                        f'chmod 700 "$HOME/{ROOT_SETUP_PATH}"', 60, input=ROOT_SETUP)
        if wrote.returncode != 0:
            raise BoxError(f"could not write the root step on {self.rec.target}: {wrote.stderr.strip()[-200:]}")
        if mac.source not in facts.get("images", "").split():
            self.log(f"{self.rec.name}: pulling {mac.source} (about 25 GB; 10-20 minutes in a datacenter)")
            pulled = self.host.run(["tart", "pull", mac.source], timeout=3 * 3600)  # foreground: a nohup pull died with SSH
            if pulled.returncode != 0:
                raise BoxError(f"tart pull {mac.source} failed: {(pulled.stdout + pulled.stderr).strip()[-300:]}")
        return mac

    def checks(self, *, boot: bool = False) -> list[Check]:
        facts = self.facts()
        out: list[Check] = []
        major = int(facts.get("macos", "0").split(".")[0] or 0)
        supported = major in MACOS or major > max(MACOS)
        out.append(Check("macos", supported and facts.get("arch") == "arm64",
                         f"macOS {facts.get('macos')} on {facts.get('arch')}"))
        if not supported:
            return out
        mac = macos_for(major)
        tart_ok = facts.get("tart") == TART_VERSION
        out.append(Check("tart", tart_ok, f"tart {facts.get('tart') or 'missing'}" + (
            "" if tart_ok else f" (want {TART_VERSION}; `pickfit mac-host setup` installs it)")))
        softnet = facts.get("softnet", "")
        softnet_ok = softnet.startswith(f"softnet {mac.softnet}")
        out.append(Check("softnet", softnet_ok, (softnet or "softnet missing") + (
            "" if softnet_ok else f" (want {mac.softnet} for macOS {major}; `pickfit mac-host setup` installs it)")))
        uid, _, mode = facts.get("softnet_mode", "").partition(" ")
        setuid = uid == "0" and mode.isdigit() and bool(int(mode, 8) & 0o4000)
        out.append(Check("softnet_setuid", setuid, "setuid-root" if setuid else
                         f"not setuid-root ({facts.get('softnet_mode') or 'missing'}); run `pickfit mac-host root`"))
        login = facts.get("console") == facts.get("user")
        out.append(Check("auto_login", login, f"{facts.get('console')} at the console" if login else
                         f"{facts.get('user')} is not logged in at the console ({facts.get('console')}); macOS guests "
                         "fail from SSH without it; run `pickfit mac-host root`"))
        images = facts.get("images", "").split()
        out.append(Check("source_image", mac.source in images, mac.source if mac.source in images else
                         f"{mac.source} not pulled; `pickfit mac-host setup` pulls it"))
        manifests = self.state_dir / "hosts" / self.rec.ssh_host().name
        for base in (mac.base, f"{mac.base}-gui"):
            built = base in images and (manifests / f"{base}.json").exists()
            out.append(Check(f"base:{base}", built, "built" if built else
                             "not built; `pickfit mac-host test` builds it (informational)"))
        if boot and all(c.ok for c in out if not c.name.startswith("base:")):
            probe = self.sh(BOOT_PROBE, 300, mac.source)
            found = _facts(probe.stdout).get("boot", "no answer")
            out.append(Check("vm_boots", found.startswith("ok"), f"a {mac.source.split('/')[-1]} clone under "
                             f"softnet: {found}"))
        return out


def ready(checks: list[Check]) -> bool:
    return all(c.ok for c in checks if not c.name.startswith("base:"))


# ---------------------------------------------------------------- the end-to-end test


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    paid: bool = False  # model calls: only when asked for


def plan_steps(*, rebuild: bool, has_base: bool, has_gui_base: bool, verify: str | None,
               record: str | None) -> list[Step]:
    v = ("-m", "pickfit.cli", "verify", "--runner", "tart")
    steps = []
    if rebuild or not has_base:
        steps.append(Step("base", (*v, "--prepare-base")))
    steps.append(Step("limits", (*v, "--limits-test")))
    if rebuild or not has_gui_base:
        steps.append(Step("gui-base", (*v, "--display", "--prepare-base")))
    steps.append(Step("gui-limits", (*v, "--display", "--limits-test")))  # limits_mac: the GUI box's own checks
    if verify:
        steps.append(Step("verify", ("-m", "pickfit.cli", "verify", "--batch", "1", "--repo", verify, "--force",
                                     "--runner", "tart", "--model", "prod", "--concurrency", "1"), paid=True))
    if record:
        steps.append(Step("record", ("-m", "pickfit.verify.video", "make", record, "--editor", "claude",
                                     "--runner", "tart"), paid=True))
    return steps


def run_test(rec: HostRecord, steps: list[Step], out_dir: Path, *, log: Callable[[str], None] = print,
             python: str = sys.executable, keep_going: bool = False,
             runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> dict[str, Any]:
    """Run each step as its own `pickfit` process with this host's env; stop at the first failure unless asked.
    Each step's output goes to <out_dir>/<step>.log; the summary to <out_dir>/report.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **rec.env(), "PYTHONUNBUFFERED": "1"}
    report: dict[str, Any] = {"host": rec.name, "target": rec.target, "macos": rec.macos, "steps": [],
                              "started": datetime.now(UTC).isoformat(timespec="seconds")}
    for step in steps:
        log(f"mac-host test: {step.name} ({' '.join(step.argv[2:])})")
        began = time.monotonic()
        path = out_dir / f"{step.name}.log"
        with path.open("w", encoding="utf-8") as fh:
            done = runner([python, *step.argv], env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
        tail = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
        entry = {"step": step.name, "exit": done.returncode, "seconds": round(time.monotonic() - began, 1),
                 "paid": step.paid, "log": str(path), "tail": tail}
        report["steps"].append(entry)
        log(f"mac-host test: {step.name} exit {done.returncode} in {entry['seconds']} s")
        if done.returncode != 0 and not keep_going:
            break
    report["passed"] = bool(report["steps"]) and all(s["exit"] == 0 for s in report["steps"]) and \
        len(report["steps"]) == len(steps)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------- the CLI


def _key(path: str | None) -> Path:
    key = Path(path).expanduser() if path else DEFAULT_KEY
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "pickfit-mac-host", "-f", str(key)],
                       check=True)
    return key


def _print_checks(checks: list[Check]) -> None:
    for c in checks:
        print(f"  {'ok ' if c.ok else 'NO '} {c.name:<22} {c.detail}")


def _root(rec: HostRecord, args: Any) -> int:
    argv = root_command(rec, password_stdin=args.password_stdin)
    if not args.password_stdin and not sys.stdin.isatty():
        print("the root step needs a person at a terminal (or --password-stdin); run:\n  " + shlex.join(argv))
        return 2
    print(f"root step on {rec.target}: softnet setuid-root, auto-login, reboot")
    code = subprocess.run(argv).returncode
    if code not in (0, 255):  # 255: the reboot dropped the connection, which is the success path
        return code
    ops = HostOps(rec)
    time.sleep(30)
    ops.wait_ssh()
    checks = ops.checks(boot=True)
    _print_checks(checks)
    return 0 if ready(checks) else 1


def main_command(args: Any) -> int:
    cmd = args.mac_command
    try:
        if cmd == "list":
            for path in sorted(HOSTS_DIR.glob("*.json")):
                rec = HostRecord.load(path.stem)
                print(f"{rec.name:<14} {rec.provider:<9} {rec.target:<24} macOS {rec.macos} "
                      f"{rec.server_type} deletable {rec.deletable_at or '-'}")
            return 0
        if cmd == "add":
            if not args.target and not args.scaleway_id:
                raise BoxError("add needs --target user@host, or --scaleway-id for a Scaleway Mac made elsewhere")
            rec = HostRecord(name=args.name, provider="ssh", target=args.target or "",
                             key=str(Path(args.key).expanduser()) if args.key else "", port=args.port)
            if args.scaleway_id:  # adopt a Mac rented by hand: `down` can then delete it
                rec.provider, rec.server_id, rec.zone = "scaleway", args.scaleway_id, args.zone
                rec = provider_for(rec).refresh(rec)
            rec.save()
            print(f"added {rec.name} ({rec.target}); next: pickfit mac-host setup {rec.name}")
            return 0
        if cmd == "up":
            key = _key(args.key)
            provider = provider_for(args.provider, **({"zone": args.zone} if args.provider == "scaleway" else {}))
            rec = provider.create(args.name, args.macos, key.with_suffix(".pub").read_text(), print)
            rec.key = str(key)
            rec.save()
            print(f"{rec.name}: {rec.target} ready; deletable after {rec.deletable_at or '-'}")
            ops = HostOps(rec)
            ops.wait_ssh()
            ops.prepare()
            rec.save()
            if not ready(ops.checks()):
                return _root(rec, args)
            return 0
        rec = HostRecord.load(args.name)
        if cmd == "env":
            for k, v in rec.env().items():
                print(f"export {k}={shlex.quote(v)}")
            return 0
        if cmd == "setup":
            ops = HostOps(rec)
            ops.prepare()
            rec.save()
            checks = ops.checks()
            _print_checks(checks)
            if not ready(checks):
                print(f"next: pickfit mac-host root {rec.name}   (types the sudo password once, then reboots)")
            return 0
        if cmd == "root":
            return _root(rec, args)
        if cmd == "check":
            ops = HostOps(rec)
            checks = ops.checks(boot=args.boot)
            if rec.macos is None:
                rec.macos = int(ops.facts().get("macos", "0").split(".")[0] or 0) or None
                rec.save()
            _print_checks(checks)
            return 0 if ready(checks) else 1
        if cmd == "test":
            ops = HostOps(rec)
            checks = ops.checks(boot=True)
            _print_checks(checks)
            if not ready(checks):
                print("the host is not ready; fix the NO lines first")
                return 1
            by = {c.name: c.ok for c in checks}
            mac = macos_for(rec.macos)
            steps = plan_steps(rebuild=args.rebuild, has_base=by.get(f"base:{mac.base}", False),
                               has_gui_base=by.get(f"base:{mac.base}-gui", False), verify=args.verify,
                               record=args.record)
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            report = run_test(rec, steps, Path("runs") / "mac-host" / f"{rec.name}-{stamp}", keep_going=args.keep_going)
            print(f"mac-host test {'passed' if report['passed'] else 'FAILED'}: "
                  + ", ".join(f"{s['step']}={s['exit']}" for s in report["steps"]))
            return 0 if report["passed"] else 1
        if cmd == "down":
            where = f"{rec.server_id} ({rec.server_type}, {rec.zone})" if rec.server_id else rec.target
            if not args.yes:
                print(f"this deletes {rec.name}: {where} and everything on it. Run again with --yes to do it.")
                return 2
            provider_for(rec).delete(rec, print)
            rec.path.unlink(missing_ok=True)
            return 0
    except BoxError as err:
        print(f"pickfit mac-host {cmd}: {err}", file=sys.stderr)
        return 1
    raise SystemExit(f"unknown mac-host command {cmd}")


def add_parser(sub: Any) -> None:
    m = sub.add_parser("mac-host", help="rented or spare Macs as tart hosts: up, setup, root, check, test, down")
    msub = m.add_subparsers(dest="mac_command", required=True)
    msub.add_parser("list", help="the hosts pickfit knows")
    a = msub.add_parser("add", help="a Mac that already exists, reached over SSH")
    a.add_argument("name")
    a.add_argument("--target", default=None, help="user@host")
    a.add_argument("--key", default=None)
    a.add_argument("--port", type=int, default=None)
    a.add_argument("--scaleway-id", default=None, help="a Scaleway Mac mini rented elsewhere (reads its address)")
    a.add_argument("--zone", default="fr-par-1")
    u = msub.add_parser("up", help="rent a Mac (24 h minimum on Scaleway), install tart/softnet, pull the image, "
                                   "then the root step")
    u.add_argument("name")
    u.add_argument("--provider", default="scaleway", choices=sorted(k for k in PROVIDERS if k != "ssh"))
    u.add_argument("--zone", default="fr-par-1")
    u.add_argument("--macos", type=int, default=DEFAULT_MACOS, choices=sorted(MACOS))
    u.add_argument("--key", default=None, help=f"SSH key (default {DEFAULT_KEY}, made if missing)")
    u.add_argument("--password-stdin", action="store_true", help="root step: read the sudo password from stdin")
    for name, text in (("env", "print the PICKFIT_TART_* exports for this host"),
                       ("setup", "install tart and softnet, write the root step, pull the source image (no sudo)"),
                       ("root", "the one root step over ssh -t: softnet setuid, auto-login, reboot")):
        p = msub.add_parser(name, help=text)
        p.add_argument("name")
        if name == "root":
            p.add_argument("--password-stdin", action="store_true", help="read the sudo password from stdin")
    c = msub.add_parser("check", help="is the host ready (versions, setuid, auto-login, image, bases)")
    c.add_argument("name")
    c.add_argument("--boot", action="store_true", help="also boot a throwaway VM under softnet")
    t = msub.add_parser("test", help="end to end: bases and the limits test; --verify/--record add paid steps")
    t.add_argument("name")
    t.add_argument("--rebuild", action="store_true", help="rebuild the bases even if they exist")
    t.add_argument("--verify", default=None, metavar="OWNER/REPO", help="also verify this repo (model calls)")
    t.add_argument("--record", default=None, metavar="SLUG",
                   help="also record and edit a clip (model calls); pick an app that runs on the host's macOS "
                        "(11/18: gifski's build needs macOS 26, LaunchServices -10825 in a macOS 15 guest)")
    t.add_argument("--keep-going", action="store_true")
    d = msub.add_parser("down", help="delete the machine (Scaleway: only after its 24 h); needs --yes")
    d.add_argument("name")
    d.add_argument("--yes", action="store_true")
    m.set_defaults(func=main_command)
