"""Where Tart runs for a TartBox: this Mac, or another Mac reached over SSH (a rented Mac mini, a spare Mac).

The macOS sandbox stays provider-neutral (loop/issues.md H-012): a host is any Apple silicon Mac with Tart, softnet
set up setuid-root, the source image pulled, and SSH. Nothing here knows who rents the Mac. Everything a TartBox does
outside the guest goes through its host:

- commands (`tart clone/set/exec/stop/delete/list`) as argv: LocalHost runs them as they are; SshHost runs them over
  one SSH connection (ControlMaster), with Homebrew on the PATH;
- `tart run` with softnet's control channel: locally an inherited AF_UNIX socket; remotely RELAY, a small Python
  program on the host, holds that socket and passes softnet's JSON-RPC lines over the SSH session's stdin and
  stdout, and stops the VM when the session ends, so a dead harness does not leave a VM running;
- the VM's log, which holds the VNC address and password: created 0600 on the host;
- the reaper, a detached shell on the host that stops and deletes a clone nobody else does;
- the VNC server, on the host's loopback: SshHost forwards a local port to it.

Select a remote host with PICKFIT_TART_HOST=user@host (and PICKFIT_TART_SSH_KEY, PICKFIT_TART_SSH_PORT); unset,
boxes run on this Mac. The host's base manifests are kept here, under ~/.pickfit/tart/hosts/<host>/.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shlex
import signal
import socket
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import IO, Any

from pickfit.env import get_env

STATE_DIR = Path.home() / ".pickfit" / "tart"  # base manifests and VM logs, outside the repo
FD = "{control-fd}"  # where the run argv names softnet's control fd; each host fills in its own
# $HOME/.local/bin first: a rented Mac without Homebrew gets tart and softnet there with no sudo (softnet's setuid bit
# still needs root once). The remote shell expands $HOME: wrap() puts this before the quoted command.
REMOTE_PATH = "$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REMOTE_STATE = PurePosixPath(".pickfit/tart")  # on the host, under the SSH user's home
HOST_PYTHON = "/usr/bin/python3"  # the Command Line Tools' Python (Homebrew needs the CLT, so a Tart host has it)
CONTROL_TIMEOUT_S = 20

# On the host: `python3 -c RELAY <log> <tart run argv...>`. Holds softnet's control socket, relays newline-delimited
# JSON-RPC between it and stdin/stdout, writes tart's own output to <log> (0600), and stops `tart run` (SIGINT, as
# Ctrl-C would) when stdin closes: the SSH session, and so the harness, is gone.
RELAY = r"""
import os, signal, socket, subprocess, sys, threading
log, argv = sys.argv[1], sys.argv[2:]
os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
fd = child.fileno()
os.set_inheritable(fd, True)
argv = [a.replace("{control-fd}", str(fd)) for a in argv]
try:
    os.unlink(log)
except FileNotFoundError:
    pass
out = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
proc = subprocess.Popen(argv, stdout=out, stderr=out, stdin=subprocess.DEVNULL, pass_fds=(fd,), start_new_session=True)
child.close()
os.close(out)

def up():
    for line in sys.stdin.buffer:
        try:
            parent.sendall(line)
        except OSError:
            break
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)

def down():
    while True:
        try:
            data = parent.recv(65536)
        except OSError:
            break
        if not data:
            break
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

threading.Thread(target=up, daemon=True).start()
threading.Thread(target=down, daemon=True).start()
sys.exit(proc.wait())
"""

# On the host: how softnet is set up, as JSON (tart_box.softnet_ready's checks, made there).
SOFTNET_PROBE = r"""
import json, os, shutil
path = shutil.which("softnet")
real = os.path.realpath(path) if path else None
info = os.stat(real) if real else None
print(json.dumps({"real": real, "uid": info.st_uid if info else None, "mode": info.st_mode if info else None}))
"""


class LocalHost:
    """Tart on this Mac, as pickfit always ran it."""

    remote = False

    def __init__(self, state_dir: Path | None = None) -> None:
        self.name = "local"
        self.state_dir = state_dir or STATE_DIR

    def wrap(self, argv: list[str]) -> list[str]:
        """The argv that runs `argv` on the host, from here."""
        return list(argv)

    def run(self, argv: list[str], *, timeout: float, text: bool = True, input: Any = None  # noqa: A002
            ) -> subprocess.CompletedProcess[Any]:
        return subprocess.run(self.wrap(argv), capture_output=True, text=text, timeout=timeout, input=input)

    def which(self, program: str) -> bool:
        import shutil

        return shutil.which(program) is not None

    def softnet_ready(self) -> str | None:
        from pickfit.verify import tart_box

        return tart_box.softnet_ready()

    def wait_bridge_down(self, tart: str, timeout_s: float = 15.0) -> None:
        """Wait for vmnet to finish tearing down bridge100 from a just-stopped VM before softnet starts again."""
        import time

        from pickfit.verify.tart_box import TART

        if tart != TART or not os.path.exists("/sbin/ifconfig"):
            return
        deadline = time.monotonic() + timeout_s
        saw_up = False
        while time.monotonic() < deadline:
            res = subprocess.run(["/sbin/ifconfig", "bridge100"], capture_output=True, timeout=5)
            if res.returncode != 0:
                if saw_up:
                    time.sleep(1.0)
                return
            saw_up = True
            time.sleep(0.5)

    def log_path(self, name: str) -> Any:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        return self.state_dir / f"{name}.log"

    def start_vm(self, run_args: list[str], log: Any) -> tuple[subprocess.Popen[bytes], Any]:
        """`tart run` (its argv naming softnet's control fd as FD), its output to `log` (0600): (process, control)."""
        from pickfit.verify.tart_box import SoftnetControl

        control = SoftnetControl()
        argv = [a.replace(FD, str(control.control_fd)) for a in run_args]
        Path(log).unlink(missing_ok=True)  # created 0600: a GUI box's log holds the VNC password
        with open(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as out:
            proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    start_new_session=True, pass_fds=(control.control_fd,))
        control.close_child()  # Tart has inherited it; keep only the host end
        return proc, control

    def read_log(self, log: Any) -> str:
        path = Path(log)
        return path.read_text(errors="replace") if path.exists() else ""

    def start_reaper(self, script: str) -> Any:
        return subprocess.Popen(["/bin/sh", "-c", script], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)

    def stop_reaper(self, reaper: Any) -> None:
        if reaper is not None and reaper.poll() is None:
            try:
                os.killpg(reaper.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            reaper.wait()

    def vnc_url(self, url: str) -> str:
        """The VNC address as reached from here (the server listens on the host's loopback)."""
        return url

    def close_forwards(self) -> None:
        pass


class StreamControl:
    """softnet's control channel through RELAY: the same JSON-RPC as tart_box.SoftnetControl, over the SSH session's
    stdin (requests) and stdout (replies)."""

    def __init__(self, requests: IO[bytes], replies: IO[bytes]) -> None:
        self.requests, self.replies = requests, replies
        self._id = 0
        self._buf = b""

    def set_policy(self, online: bool) -> dict[str, Any]:
        from pickfit.verify.tart_box import SOFTNET_POLICY

        return self.set_rules(**SOFTNET_POLICY[online])

    def set_rules(self, *, allow: list[str], block: list[str]) -> dict[str, Any]:
        from pickfit.verify.box import BoxError

        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": "softnet.policy.set",
               "params": {"allow": allow, "block": block}}
        try:
            self.requests.write((json.dumps(req) + "\n").encode())
            self.requests.flush()
            reply = json.loads(self._readline())
        except (OSError, ValueError) as err:
            raise BoxError(f"softnet control channel (over SSH) failed: {type(err).__name__}: {err}") from err
        if reply.get("error") is not None:
            raise BoxError(f"softnet rejected the policy: {reply['error']}")
        return reply.get("result") or {}

    def _readline(self) -> bytes:
        from pickfit.verify.box import BoxError

        fd = self.replies.fileno()
        while b"\n" not in self._buf:
            ready, _, _ = select.select([fd], [], [], CONTROL_TIMEOUT_S)
            if not ready:
                raise BoxError(f"softnet did not answer within {CONTROL_TIMEOUT_S}s")
            chunk = os.read(fd, 65536)
            if not chunk:
                raise BoxError("softnet control channel closed before replying")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line

    def close(self) -> None:
        for stream in (self.requests, self.replies):
            try:
                stream.close()
            except OSError:
                pass


class RemoteReaper:
    """The reaper's shell on the host, by its pid there."""

    def __init__(self, host: SshHost, pid: int) -> None:
        self.host, self.pid = host, pid

    def poll(self) -> int | None:
        alive = self.host.run(["/bin/kill", "-0", str(self.pid)], timeout=30).returncode == 0
        return None if alive else 0


class SshHost(LocalHost):
    """Tart on another Mac, over SSH: one master connection (ControlMaster) carries every command."""

    remote = True

    def __init__(self, target: str, *, key: str | None = None, port: int | None = None, name: str | None = None,
                 state_dir: Path | None = None, ssh: str = "ssh", remote_state: str | PurePosixPath = REMOTE_STATE
                 ) -> None:
        self.target = target
        self.remote_state = PurePosixPath(remote_state)
        self.name = name or re.sub(r"[^A-Za-z0-9_.-]", "_", target.split("@")[-1])
        self.state_dir = (state_dir or STATE_DIR) / "hosts" / self.name
        self.key, self.port, self.ssh = key, port, ssh
        digest = hashlib.sha256(f"{target}:{port}".encode()).hexdigest()[:12]
        self.control_path = Path(tempfile.gettempdir()) / f"pf-tart-{digest}.sock"  # sun_path is short: keep it so
        self.forwards: list[tuple[int, int]] = []  # (local port, the host's port)

    def options(self) -> list[str]:
        opts = ["-o", "BatchMode=yes", "-o", "ControlMaster=auto", "-o", f"ControlPath={self.control_path}",
                "-o", "ControlPersist=600", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
                "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20"]
        if self.key:
            opts += ["-i", self.key, "-o", "IdentitiesOnly=yes"]
        if self.port:
            opts += ["-p", str(self.port)]
        return opts

    def wrap(self, argv: list[str]) -> list[str]:
        """ssh ... target -- 'PATH=...; export PATH; exec <argv>': the remote shell sees one quoted command."""
        return [self.ssh, *self.options(), self.target, "--",
                f"PATH={REMOTE_PATH}; export PATH; exec {shlex.join(argv)}"]

    def which(self, program: str) -> bool:
        return self.run(["/bin/sh", "-c", f"command -v {shlex.quote(program)} >/dev/null"], timeout=60).returncode == 0

    def softnet_ready(self) -> str | None:
        import stat

        probe = self.run([HOST_PYTHON, "-I", "-c", SOFTNET_PROBE], timeout=60)
        try:
            found = json.loads(probe.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return f"could not check softnet on {self.target}: {(probe.stdout + probe.stderr).strip()[-200:]}"
        if not found.get("real"):
            return f"softnet is not installed on {self.target}; `brew install cirruslabs/cli/tart` pulls it"
        if found.get("uid") != 0 or not (found.get("mode") or 0) & stat.S_ISUID:
            real = found["real"]
            return (f"softnet on {self.target} needs a one-time setuid-root bit (it drops back to the user after "
                    f"setting up the network); run there: sudo chown root:wheel {real} && sudo chmod u+s {real}")
        return None

    def wait_bridge_down(self, tart: str, timeout_s: float = 15.0) -> None:
        rounds = int(timeout_s / 0.5)
        script = (f"up=0; for i in $(seq 1 {rounds}); do /sbin/ifconfig bridge100 >/dev/null 2>&1 || "
                  "{ [ $up = 1 ] && sleep 1; exit 0; }; up=1; sleep 0.5; done")
        self.run(["/bin/sh", "-c", script], timeout=timeout_s + 30)

    def log_path(self, name: str) -> Any:
        return self.remote_state / f"{name}.log"

    def start_vm(self, run_args: list[str], log: Any) -> tuple[subprocess.Popen[bytes], Any]:
        proc = subprocess.Popen(self.wrap([HOST_PYTHON, "-I", "-c", RELAY, str(log), *run_args]),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        assert proc.stdin is not None and proc.stdout is not None
        return proc, StreamControl(proc.stdin, proc.stdout)

    def read_log(self, log: Any) -> str:
        return self.run(["/bin/cat", str(log)], timeout=60).stdout or ""

    def start_reaper(self, script: str) -> Any:
        started = self.run(["/bin/sh", "-c", f"nohup /bin/sh -c {shlex.quote(script)} </dev/null >/dev/null 2>&1 & "
                            "echo $!"], timeout=60)
        pid = started.stdout.strip().splitlines()[-1] if started.stdout.strip() else ""
        return RemoteReaper(self, int(pid)) if pid.isdigit() else None

    def stop_reaper(self, reaper: Any) -> None:
        if isinstance(reaper, RemoteReaper):
            self.run(["/bin/kill", "-9", str(reaper.pid)], timeout=30)

    def vnc_url(self, url: str) -> str:
        """The host's VNC server (on its loopback) through a forwarded local port of this machine."""
        from pickfit.verify.box import BoxError

        m = re.match(r"(vnc://[^@]*@)([^:/]+):(\d+)(.*)", url)
        if not m:
            raise BoxError("tart printed a VNC address pickfit cannot read")
        remote = int(m.group(3))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            local = probe.getsockname()[1]
        done = subprocess.run([self.ssh, *self.options(), "-O", "forward", "-L", f"127.0.0.1:{local}:127.0.0.1:{remote}",
                               self.target], capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise BoxError(f"could not forward the VNC port from {self.target}: {done.stderr.strip()[-200:]}")
        self.forwards.append((local, remote))
        return f"{m.group(1)}127.0.0.1:{local}{m.group(4)}"

    def close_forwards(self) -> None:
        for local, remote in self.forwards:
            subprocess.run([self.ssh, *self.options(), "-O", "cancel", "-L", f"127.0.0.1:{local}:127.0.0.1:{remote}",
                            self.target], capture_output=True, timeout=60)
        self.forwards = []


def host_from_env(state_dir: Path | None = None) -> LocalHost:
    """PICKFIT_TART_HOST's Mac over SSH, else this one."""
    target = (get_env("PICKFIT_TART_HOST") or "").strip()
    if not target:
        return LocalHost(state_dir)
    port = (get_env("PICKFIT_TART_SSH_PORT") or "").strip()
    return SshHost(target, key=(get_env("PICKFIT_TART_SSH_KEY") or "").strip() or None,
                   port=int(port) if port.isdigit() else None, state_dir=state_dir)
