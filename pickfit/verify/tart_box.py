"""TartBox: the Box interface on a real macOS VM on this Mac (Tart, Apple Virtualization.framework).

- One box is one VM cloned from a prepared base (`pickfit verify --runner tart
  --prepare-base`): `tart clone` is an APFS copy-on-write clone, so it takes a
  second and only changes use disk. `close()` stops and deletes the clone.
- Commands reach the guest through `tart exec`, which talks to the Tart Guest
  Agent over a virtio socket, not the network: cutting the guest's network
  leaves control intact, so the replay's offline smoke tests work.
- Model commands run as `sbx`, a standard macOS user (not an admin, no sudo)
  that owns the Homebrew prefix, so `brew install` works without root. Each
  command runs under `ulimit` caps and an in-guest timeout that kills its
  process group (macOS has no `timeout` or `setsid`, and its `nohup` fails
  outside a console session; small helpers in a root-owned directory stand in). The VM's own CPU, memory and disk are the
  outer caps; macOS enforces no per-process memory limit.
- Network: the guest's pf firewall, loaded as root by the harness, blocks
  private ranges, link-local (cloud metadata) and the host (only DNS to the
  resolver is allowed), and IPv6. DNS is pinned to the IPv4 resolver (the
  VM's gateway): vmnet also hands out an IPv6 link-local resolver first, and
  with IPv6 blocked every lookup waited 3 s for it (measured 2026-10-29).
  set_network(False) blocks everything but loopback and drops existing
  connections. sbx cannot change pf.
- Apple allows at most two macOS VMs at once per Mac, and an open bug
  (FB22967193, reported on macOS 26.5) can leave the limit "used up" until the
  host reboots: run one box at a time, and stop when start() reports it.

Licences (docs/research/notes/macos-windows-verify.md): macOS SLA 2B(iii) allows
two extra macOS instances in VMs for software development and testing; Tart is
FSL-1.1-ALv2, free for any use other than a competing product.
"""

from __future__ import annotations

import json
import re
import secrets
import shlex
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now
from pickfit.verify.box import Box, BoxError, BoxLimits, ExecResult, HOST_GRACE_S, run_captured

TART = "tart"
SOURCE_IMAGE = "ghcr.io/cirruslabs/macos-tahoe-base:latest"  # macOS 26 with Homebrew and the guest agent
BASE_VM = "pickfit-macos-26"
VM_PREFIX = "pf-verify-"
STATE_DIR = Path.home() / ".pickfit" / "tart"  # base manifests and VM logs, outside the repo
MAC_USER = "sbx"
MAC_UID = 1001
MAC_HOME = f"/Users/{MAC_USER}"
MAC_WORKDIR = f"{MAC_HOME}/work"
BREW_PREFIX = "/opt/homebrew"
MAC_PATH = (f"{MAC_HOME}/.local/bin:{BREW_PREFIX}/bin:{BREW_PREFIX}/sbin:/usr/local/bin:/usr/bin:/bin:"
            "/usr/sbin:/sbin")
# Only non-secret settings; nothing from the host environment is passed through. No npm prefix:
# Homebrew's npm installs -g under /opt/homebrew, as it does on a developer's Mac.
MAC_ENV = {
    "HOME": MAC_HOME,
    "USER": MAC_USER,
    "LOGNAME": MAC_USER,
    "PATH": MAC_PATH,
    "LANG": "en_US.UTF-8",
    "TERM": "xterm-256color",
    "COLUMNS": "100",
    "CI": "1",
    "PIP_NO_INPUT": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PYTHONUNBUFFERED": "1",
    "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    "HOMEBREW_NO_ANALYTICS": "1",
    "HOMEBREW_NO_ENV_HINTS": "1",
}
# The Command Line Tools' Python (Homebrew needs the CLT, so it is there), called directly: the /usr/bin/python3
# shim goes through xcrun, which adds SDKROOT, CPATH, LIBRARY_PATH and MANPATH that every command would inherit.
GUEST_PYTHON = "/Library/Developer/CommandLineTools/usr/bin/python3"
HELPER_DIR = "/usr/local/libexec/pickfit"  # root-owned: the box user cannot replace the helpers
# timeout <seconds> <argv...>: runs argv in its own session, kills that process group at the deadline
# and exits 137 like `timeout -s KILL`; a signal death exits 128+N like bash.
HELPER_TIMEOUT = """\
import os, signal, subprocess, sys
limit, argv = int(sys.argv[1]), sys.argv[2:]
proc = subprocess.Popen(argv, start_new_session=True)
try:
    code = proc.wait(timeout=limit)
except subprocess.TimeoutExpired:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()
    sys.exit(137)
sys.exit(128 - code if code < 0 else code)
"""
# detach <argv...>: `setsid nohup` for macOS. util-linux setsid without the fork, then SIGHUP ignored;
# macOS's own nohup exits with "can't detach from console" outside a GUI session (measured 2026-10-29).
HELPER_DETACH = """\
import os, signal, sys
try:
    os.setsid()
except OSError as err:
    print(f"detach: {err}; running in the current session", file=sys.stderr)
signal.signal(signal.SIGHUP, signal.SIG_IGN)
os.execvp(sys.argv[1], sys.argv[1:])
"""
TIMEOUT_CMD = f"{GUEST_PYTHON} -I {HELPER_DIR}/timeout"
DETACH_CMD = f"{GUEST_PYTHON} -I {HELPER_DIR}/detach"
# Never reachable from the box: the same ranges as ModalBox, plus all of IPv6 (vmnet gives the guest none
# that it needs). The host sits on 192.168.64.0/24, so it is covered.
BLOCKED_NETS = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12",
                "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4")
ROOT_PATH = "PATH=/usr/bin:/bin:/usr/sbin:/sbin; export PATH"
AGENT_WAIT_S = 240
NETWORK_WAIT_S = 60
STALE_S = 3 * 3600  # a running pf-verify VM older than this was left by a dead process
VM_LIMIT_HINT = ("macOS refused to start another VM (Apple allows two at once; bug FB22967193 can keep the "
                 "slots used after VMs stop). Check `tart list`; if no other macOS VM is running, reboot the Mac.")


def pf_rules(online: bool, resolvers: list[str]) -> str:
    """The guest's pf ruleset: online blocks local networks and the host; offline blocks everything."""
    if not online:
        return "set skip on lo0\nblock drop all\n"
    lines = ["set skip on lo0",
             "block drop in all",
             "pass in quick inet proto udp from any port 67 to any port 68",  # DHCP replies
             "block return out quick inet6 all"]  # fail fast, so clients fall back to IPv4 at once
    if resolvers:
        lines.append(f"pass out quick inet proto {{ tcp, udp }} to {{ {', '.join(resolvers)} }} port 53")
    lines += ["pass out quick inet proto udp from any port 68 to any port 67",
              f"block drop out quick inet to {{ {', '.join(BLOCKED_NETS)} }}",
              "pass out inet all"]
    return "\n".join(lines) + "\n"


def base_manifest_path(base: str = BASE_VM, state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"{base}.json"


def load_manifest(base: str = BASE_VM, state_dir: Path | None = None) -> dict[str, Any]:
    path = base_manifest_path(base, state_dir)
    if not path.exists():
        raise BoxError(f"no prepared base VM {base!r} ({path} is missing); run "
                       "`pickfit verify --runner tart --prepare-base` first")
    return json.loads(path.read_text(encoding="utf-8"))


def image_label(manifest: dict[str, Any]) -> str:
    """What `VerificationRun.image` records: source image digest, guest macOS, pickfit's base."""
    digest = (manifest.get("source_digest") or "").removeprefix("sha256:")[:12] or "unknown"
    source = manifest.get("source", SOURCE_IMAGE).split(":")[0].removeprefix("ghcr.io/")
    return f"{source}@sha256:{digest} macOS {manifest.get('macos', '?')} +{manifest.get('base', BASE_VM)}"[:120]


def _tart_json(tart: str, *args: str) -> Any:
    proc = subprocess.run([tart, *args, "--format", "json"], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise BoxError(f"tart {' '.join(args)} failed: {proc.stderr.strip()[-300:]}")
    return json.loads(proc.stdout or "[]")


def prune_stale(tart: str = TART, *, now: float | None = None, log: Callable[[str], None] = print) -> list[str]:
    """Delete pf-verify VMs a dead process left: stopped ones, and running ones older than STALE_S."""
    now = time.time() if now is None else now
    removed = []
    for vm in _tart_json(tart, "list", "--source", "local"):
        name = vm.get("Name", "")
        if not name.startswith(VM_PREFIX):
            continue
        m = re.match(rf"{re.escape(VM_PREFIX)}(\d+)-", name)
        old = m is not None and now - int(m.group(1)) > STALE_S
        running = vm.get("Running") is True or vm.get("State") == "running"
        if running and not old:
            continue
        if running:
            subprocess.run([tart, "stop", name, "--timeout", "5"], capture_output=True, timeout=60)
        subprocess.run([tart, "delete", name], capture_output=True, timeout=60)
        removed.append(name)
    if removed:
        log(f"tart: removed {len(removed)} stale VM(s): {', '.join(removed)}")
    return removed


class TartBox(Box):
    """A throwaway macOS VM driven like a DockerBox."""

    runner = "tart-vz"
    os = "macos"
    arch = "arm64"
    home = MAC_HOME
    workdir = MAC_WORKDIR
    kind = "macOS virtual machine"
    user_rule = ("You are a standard macOS user, not an admin: no sudo, nothing written outside $HOME, /tmp and "
                 "the Homebrew prefix /opt/homebrew (yours, so brew install needs no sudo).")
    detach = DETACH_CMD

    def __init__(self, *, base: str = BASE_VM, limits: BoxLimits = BoxLimits(), cpus: int = 4,
                 memory_mb: int = 8192, name: str | None = None, tart: str = TART,
                 state_dir: Path | None = None, log: Callable[[str], None] = print) -> None:
        self.base = base
        self.limits = limits
        self.cpus = cpus
        self.memory_mb = memory_mb
        self.name = name or f"{VM_PREFIX}{int(time.time())}-{secrets.token_hex(3)}"
        self.tart = tart
        self.state_dir = state_dir or STATE_DIR
        self.log = log
        self.manifest: dict[str, Any] = {}
        self.image = base
        self.started = False
        self.cloned = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.resolvers: list[str] = []
        self.vm_proc: subprocess.Popen[bytes] | None = None
        self.vm_log: Path | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def describe(self) -> str:
        m = self.manifest
        tools = ", ".join(f"{k} {m[k]}" for k in ("uv", "pipx", "node", "npm") if m.get(k))
        return (f"Box: macOS {m.get('macos', '26')} {self.arch} virtual machine (Apple silicon), user {MAC_USER} "
                f"(standard user, not an admin, no sudo), HOME={self.home}, work dir {self.workdir}. Commands run "
                "in /bin/bash 3.2 (macOS's own bash: no mapfile, no ${var,,}). PATH starts with ~/.local/bin, "
                f"then Homebrew (/opt/homebrew/bin; {MAC_USER} owns /opt/homebrew, so brew install works without "
                f"sudo). Installed: Homebrew {m.get('brew', '')}, Xcode Command Line Tools (git, clang, make, "
                f"python3 {m.get('python3', '')}), {tools}; curl, unzip, tar. npm -g installs under /opt/homebrew. "
                "Network: on. No API keys, no accounts, no GUI session.")

    # -- lifecycle

    def _tart(self, *args: str, timeout_s: float = 120) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run([self.tart, *args], capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as err:
            raise BoxError(f"tart {args[0]} timed out after {timeout_s:.0f}s") from err

    def start(self) -> None:
        if self.started:
            return
        if shutil.which(self.tart) is None:
            raise BoxError("tart not found; install it with `brew install openai/tools/tart`")
        self.manifest = load_manifest(self.base, self.state_dir)
        self.image = image_label(self.manifest)
        began = time.monotonic()
        try:
            prune_stale(self.tart, log=self.log)
            clone = self._tart("clone", self.base, self.name, timeout_s=300)
            if clone.returncode != 0:
                raise BoxError(f"tart clone {self.base} failed: {clone.stderr.strip()[-500:]}")
            self.cloned = True
            sized = self._tart("set", self.name, "--cpu", str(self.cpus), "--memory", str(self.memory_mb))
            if sized.returncode != 0:
                raise BoxError(f"tart set failed: {sized.stderr.strip()[-300:]}")
            self._boot()
            self._setup()
        except BaseException:
            self.close()
            raise
        self.started = True
        self.start_s = round(time.monotonic() - began, 2)
        self._timer = threading.Timer(self.limits.lifetime_s, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def _boot(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.vm_log = self.state_dir / f"{self.name}.log"
        with self.vm_log.open("wb") as out:
            self.vm_proc = subprocess.Popen([self.tart, "run", "--no-graphics", "--no-audio", "--no-clipboard",
                                             self.name], stdout=out, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + AGENT_WAIT_S
        while time.monotonic() < deadline:
            if self.vm_proc.poll() is not None:
                text = self.vm_log.read_text(errors="replace")[-800:]
                hint = f" {VM_LIMIT_HINT}" if re.search(r"LimitExceeded|maximum number|limit", text, re.I) else ""
                raise BoxError(f"tart run exited with {self.vm_proc.returncode}: {text.strip()}{hint}")
            try:
                probe = self._tart("exec", self.name, "true", timeout_s=20)
            except BoxError:  # measured: early in boot, exec can hang instead of failing
                continue
            if probe.returncode == 0:
                return
            time.sleep(2)
        raise BoxError(f"the guest agent did not answer within {AGENT_WAIT_S}s")

    def _root(self, script: str, timeout_s: int = 60) -> subprocess.CompletedProcess[str]:
        """Harness-only root command (helpers, firewall); never used for model commands.

        The guest agent runs as `admin` (passwordless sudo) with a PATH that lacks /sbin and /usr/sbin.
        """
        return self._tart("exec", self.name, "sudo", "-n", "/bin/sh", "-c", f"{ROOT_PATH}\n{script}",
                          timeout_s=timeout_s + 15)

    def _setup(self) -> None:
        """Helpers, the firewall and the work dir, as root, before any model command."""
        pin = (f"for i in $(seq 1 {NETWORK_WAIT_S}); do route -n get default >/dev/null 2>&1 && break; "
               "sleep 1; done; gw=$(route -n get default | awk '/gateway:/ {print $2}'); "
               "svc=$(networksetup -listallnetworkservices | sed -n 2p); "
               "networksetup -setdnsservers \"$svc\" \"$gw\" && echo \"$gw\"")
        net = self._root(pin, NETWORK_WAIT_S + 20)
        self.resolvers = [ip for ip in net.stdout.split() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip)]
        if net.returncode != 0 or not self.resolvers:
            raise BoxError(f"guest network did not come up: {(net.stdout + net.stderr).strip()[-300:]}")
        files = {"timeout": HELPER_TIMEOUT, "detach": HELPER_DETACH,
                 "pf-online.conf": pf_rules(True, self.resolvers), "pf-offline.conf": pf_rules(False, [])}
        script = [f"set -e; mkdir -p {HELPER_DIR}"]
        for name, text in files.items():
            script.append(f"cat > {HELPER_DIR}/{name} <<'PICKFIT_EOF'\n{text}PICKFIT_EOF")
        script += [f"chown -R root:wheel {HELPER_DIR}; chmod 755 {HELPER_DIR}; chmod 644 {HELPER_DIR}/*",
                   f"mkdir -p {MAC_WORKDIR} {MAC_HOME}/.local/bin; chown -R {MAC_USER} {MAC_WORKDIR} {MAC_HOME}/.local",
                   "pfctl -E >/dev/null 2>&1 || true",
                   f"pfctl -q -f {HELPER_DIR}/pf-online.conf",
                   "pfctl -s info 2>/dev/null | head -1"]
        proc = self._root("\n".join(script), 60)
        if proc.returncode != 0 or "Status: Enabled" not in proc.stdout:
            raise BoxError(f"box setup failed (firewall or helpers): {(proc.stdout + proc.stderr).strip()[-500:]}")

    def _expire(self) -> None:
        self.log(f"tart: {self.name} reached its {self.limits.lifetime_s}s lifetime; stopping it")
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self.vm_proc is not None and self.vm_proc.poll() is None:
                self._tart("stop", self.name, "--timeout", "10", timeout_s=90)
                try:
                    self.vm_proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.vm_proc.kill()
                    self.vm_proc.wait()
            self.vm_proc = None
            if self.cloned:
                self._tart("delete", self.name, timeout_s=120)
                self.cloned = False
            self.started = False

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def user_argv(self, command: str, timeout_s: int, cwd: str, *, stdin: bool = False) -> list[str]:
        """`tart exec` argv that runs `command` as the box user with the limits (tests check it)."""
        lim = self.limits
        guard = (f"ulimit -u {lim.pids} -n {lim.nofile} -f {lim.home_mb * 1024} && cd {shlex.quote(cwd)} && "
                 f"exec {TIMEOUT_CMD} {int(timeout_s)} /bin/bash -c {shlex.quote(command)}")
        env = [f"{key}={value}" for key, value in MAC_ENV.items()]
        return [self.tart, "exec", *(["-i"] if stdin else []), self.name, "sudo", "-n", "-u", MAC_USER, "-H",
                "/usr/bin/env", "-i", *env, "/bin/bash", "-c", guard]

    def _agent_failed(self, code: int, err: str) -> bool:
        """tart's own failure (no VM, no agent), told apart from the command's exit code."""
        return code != 0 and ("is the Tart Guest Agent running?" in err or f'"{self.name}" is not running' in err
                              or f"VM \"{self.name}\" does not exist" in err)

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        began = time.monotonic()
        code, out, err, host_timeout, truncated = run_captured(
            self.user_argv(command, timeout_s, cwd or self.workdir), timeout_s + HOST_GRACE_S)
        seconds = round(time.monotonic() - began, 2)
        if self._agent_failed(code, err):
            raise BoxError(f"tart exec failed (the VM or its guest agent is gone): {err.strip()[-300:]}")
        timed_out = host_timeout or (code == 137 and seconds >= timeout_s - 0.5)
        if host_timeout:
            code = 124
            err += (f"\n[pickfit stopped waiting after {seconds:.0f}s: the command did not exit, or something "
                    "it started still holds its output open; start servers and daemons with run_background]")
        return ExecResult(command=command, exit_code=code, stdout=out, stderr=err, seconds=seconds,
                          timed_out=timed_out, truncated=truncated)

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        # The path is passed as $1, never spliced into the script.
        script = 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"'
        argv = self.user_argv(f"sh -c {shlex.quote(script)} sh {shlex.quote(path)}", 60, self.workdir, stdin=True)
        code, _, err, _, _ = run_captured(argv, 60 + HOST_GRACE_S, stdin=data)
        if code != 0:
            raise BoxError(f"cannot write {path}: {err.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        argv = self.user_argv(f"head -c {int(max_bytes)} -- {shlex.quote(path)}", 20, self.workdir)
        proc = subprocess.run(argv, capture_output=True, timeout=20 + HOST_GRACE_S)
        if proc.returncode != 0:
            raise BoxError(f"cannot read {path}: {proc.stderr.decode(errors='replace').strip()[-300:]}")
        return proc.stdout[:max_bytes]

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        rules = f"{HELPER_DIR}/pf-{'online' if enabled else 'offline'}.conf"
        # Flushing states drops connections that are already open, so nothing outlives the cut.
        proc = self._root(f"pfctl -q -f {rules} && pfctl -q -F states", 30)
        if proc.returncode != 0:
            raise BoxError(f"pfctl failed: {(proc.stdout + proc.stderr).strip()[-300:]}")
        self.network_enabled = enabled


# ---------------------------------------------------------------- the base VM


PREPARE_ROOT = f"""\
set -e
if ! id {MAC_USER} >/dev/null 2>&1; then
  sysadminctl -addUser {MAC_USER} -fullName "pickfit sandbox" -UID {MAC_UID} -shell /bin/bash \
-home {MAC_HOME} -password "$(openssl rand -hex 16)" 2>&1
  createhomedir -c -u {MAC_USER} >/dev/null
fi
if dseditgroup -o checkmember -m {MAC_USER} admin >/dev/null 2>&1; then echo "{MAC_USER} is an admin"; exit 3; fi
chown -R {MAC_USER} {BREW_PREFIX}
mdutil -a -i off >/dev/null 2>&1 || true
softwareupdate --schedule off >/dev/null 2>&1 || true
"""
PREPARE_USER = ("brew analytics off && brew install uv pipx node && brew cleanup -s --prune=all && "
                "rm -rf ~/Library/Caches/Homebrew ~/Library/Logs/Homebrew")
VERSIONS = {
    "macos": "echo \"$(sw_vers -productVersion) ($(sw_vers -buildVersion))\"",
    "brew": "brew --version | head -1 | awk '{print $2}'",
    "python3": f"{GUEST_PYTHON} -c 'import platform; print(platform.python_version())'",
    "uv": "uv --version | awk '{print $2}'",
    "pipx": "pipx --version",
    "node": "node --version",
    "npm": "npm --version",
}


def source_digest(tart: str = TART, source: str = SOURCE_IMAGE) -> str | None:
    """The pulled image's digest: tart lists an OCI image under its tag and under repo@sha256:<digest>."""
    repo = source.rsplit(":", 1)[0]
    for image in _tart_json(tart, "list", "--source", "oci"):
        name = image.get("Name", "")
        if name.startswith(f"{repo}@sha256:"):
            return name.split("@", 1)[1]
    return None


def prepare_base(*, source: str = SOURCE_IMAGE, base: str = BASE_VM, tart: str = TART,
                 log: Callable[[str], None] = print) -> dict[str, Any]:
    """Build the base VM every box clones: the box user, Homebrew owned by it, uv, pipx and node.

    Needs `tart pull <source>` first (about 25 GB). Writes ~/.pickfit/tart/<base>.json.
    """
    if subprocess.run([tart, "get", base], capture_output=True).returncode == 0:
        raise BoxError(f"base VM {base!r} already exists; `tart delete {base}` to rebuild it")
    began = time.monotonic()
    proc = subprocess.run([tart, "clone", source, base], capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise BoxError(f"tart clone {source} failed: {proc.stderr.strip()[-500:]}")
    box = TartBox(base=base, name=base, tart=tart, limits=BoxLimits(lifetime_s=3600, max_command_s=1800), log=log)
    box.cloned = False  # never delete the base on close
    try:
        box.manifest = {"macos": "26"}
        box._boot()
        log(f"tart: {base} booted in {time.monotonic() - began:.0f}s; creating {MAC_USER}")
        root = box._root(PREPARE_ROOT, 300)
        if root.returncode != 0:
            raise BoxError(f"base setup failed: {(root.stdout + root.stderr).strip()[-800:]}")
        box._setup()
        box.started = True
        log("tart: brew install uv pipx node (as the box user)")
        user = box.exec(PREPARE_USER, 1800)
        if not user.ok:
            raise BoxError(f"brew install failed: {(user.stdout + user.stderr).strip()[-800:]}")
        manifest: dict[str, Any] = {"base": base, "source": source, "source_digest": source_digest(tart, source),
                                    "arch": "arm64", "user": MAC_USER,
                                    "prepared_at": taipei_now().isoformat(timespec="seconds")}
        for key, command in VERSIONS.items():
            result = box.exec(command, 60)
            manifest[key] = result.stdout.strip().splitlines()[-1] if result.ok and result.stdout.strip() else None
        # The firewall and helpers are written again by every clone; the base keeps none of them.
        box._root(f"rm -rf {HELPER_DIR} {MAC_WORKDIR}; pfctl -d >/dev/null 2>&1 || true", 30)
        box._root("shutdown -h now", 30)  # a clean shutdown, so clones boot from a consistent disk
        if box.vm_proc is not None:
            try:
                box.vm_proc.wait(timeout=180)
            except subprocess.TimeoutExpired:
                log("tart: the base did not shut down within 180s; stopping it")
    finally:
        box.started = False
        box.close()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    base_manifest_path(base).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"tart: base {base} ready in {time.monotonic() - began:.0f}s · {image_label(manifest)}")
    return manifest
