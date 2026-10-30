"""Box: a disposable, limited sandbox the verification agent drives.

One Box per verification run, closed when the run ends. Code under test runs
only inside a Box, as a non-root user, with no API keys in its environment;
model calls happen outside.

DockerBox is for local development (Docker or OrbStack on this Mac). It keeps
the limits measured in spikes/sandbox_docker_install.py: uid 1000, all
capabilities dropped, no-new-privileges, CPU/memory/pids caps, a read-only
root with size-limited tmpfs for HOME and /tmp (the disk cap), a per-command
`timeout -s KILL` inside the container, and a container lifetime cap. Cloud
metadata (169.254.0.0/16) is routed to `unreachable` inside the container by a
one-off root exec before the agent runs; the box user cannot change routes.
ModalBox (P3.6) implements the same interface on Modal gVisor.
"""

from __future__ import annotations

import hashlib
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

SANDBOX_DOCKERFILE = Path(__file__).with_name("sandbox.Dockerfile")
BOX_USER = "sbx"
BOX_HOME = "/home/sbx"
BOX_WORKDIR = f"{BOX_HOME}/work"
# Where user-level installs land: uv tool, pipx, `pip --user`, npm (prefix below), cargo, go.
BOX_PATH = f"{BOX_HOME}/.local/bin:{BOX_HOME}/.cargo/bin:{BOX_HOME}/go/bin:/usr/local/bin:/usr/bin:/bin"
# Only non-secret settings; nothing from the host environment is passed through.
BOX_ENV = {
    "HOME": BOX_HOME,
    "USER": BOX_USER,
    "PATH": BOX_PATH,
    "LANG": "C.UTF-8",
    "TERM": "xterm-256color",
    "COLUMNS": "100",
    "CI": "1",
    "PIP_NO_INPUT": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PYTHONUNBUFFERED": "1",
    "NPM_CONFIG_PREFIX": f"{BOX_HOME}/.local",
    "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    "DEBIAN_FRONTEND": "noninteractive",
}

# Output kept per stream: the first HEAD bytes and the last TAIL bytes.
OUTPUT_HEAD_BYTES = 8_000
OUTPUT_TAIL_BYTES = 24_000
HOST_GRACE_S = 15  # the host waits this long past the in-box timeout before giving up
DOCKER_WAIT_S = 120
# Cloud instance metadata (169.254.169.254 and the rest of link-local) answers with
# credentials on many hosts; boxes never need it.
METADATA_CIDR = "169.254.0.0/16"
METADATA_CIDR6 = "fd00:ec2::254/128"


class BoxError(RuntimeError):
    """The sandbox itself failed (not the command running inside it)."""


@dataclass(frozen=True)
class BoxLimits:
    """Hard limits the model cannot change."""

    cpus: float = 2.0
    memory_mb: int = 2048
    pids: int = 256
    home_mb: int = 1536  # tmpfs for HOME: installs, downloads, the work dir
    tmp_mb: int = 256
    lifetime_s: int = 20 * 60
    max_command_s: int = 600
    nofile: int = 1024


@dataclass
class ExecResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    truncated: bool = False  # some output was dropped between the kept head and tail

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Box(ABC):
    """A fresh sandbox (Linux unless a subclass says otherwise). Relative paths resolve against `workdir`."""

    runner: str  # e.g. docker-runc, modal-gvisor, tart-vz
    image: str
    os: str = "linux"
    arch: str = "x86_64"
    home: str = BOX_HOME
    workdir: str = BOX_WORKDIR
    network_enabled: bool = True
    gpu: str | None = None  # e.g. "T4" when the box has an NVIDIA GPU
    # How the agent's instructions name the box and the box user's limits.
    kind: str = "Linux sandbox"
    user_rule: str = "You are not root: no sudo, no apt-get, nothing written outside $HOME and /tmp."
    detach: str = "setsid nohup"  # starts run_background processes in their own session, immune to SIGHUP

    def describe(self) -> str:
        """The box line of the agent's task: OS, user, paths and what is installed."""
        return (f"Box: Debian-based Linux {self.arch}, user sbx (uid 1000, not root, no sudo), HOME={self.home}, "
                f"work dir {self.workdir}. PATH starts with ~/.local/bin. Installed: python3.12 with pip, uv, pipx; "
                "node 22 with npm (global prefix ~/.local); git, curl, unzip, xz, zstd. Network: on. No API keys, "
                "no accounts, no GUI.")

    @abstractmethod
    def start(self) -> None:
        """Create the sandbox; network starts enabled (installs need it)."""

    @abstractmethod
    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        """Run `bash -c command` as the box user; killed inside the box after `timeout_s`."""

    @abstractmethod
    def write_file(self, path: str, content: str | bytes) -> None:
        """Create or replace a file, creating parent directories."""

    @abstractmethod
    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        """The first `max_bytes` of a file; BoxError if it cannot be read."""

    @abstractmethod
    def set_network(self, enabled: bool) -> None:
        """Turn outbound network on (install) or off (run examples offline)."""

    @abstractmethod
    def close(self) -> None:
        """Destroy the sandbox and everything in it. Safe to call twice."""

    def usd_per_second(self) -> float:
        """What the box costs per second it exists (0 for a local container)."""
        return 0.0

    def __enter__(self) -> Box:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def background_script(command: str, port: int | None, wait_s: int, tag: int | str, *,
                      detach: str = "setsid nohup") -> str:
    """Bash that starts `command` detached with its output in a log, then waits for it.

    With a port, it waits up to wait_s for 127.0.0.1:port to accept connections;
    without one, a few seconds to see that the process is still alive. Prints
    the pid (also the process group: setsid) and the log tail; exits 0 only if
    the process came up. The agent and the replay run the same script; `detach`
    is the box's own way to start it (macOS has no setsid, and its nohup fails
    outside a console session, so TartBox brings a helper).
    """
    log = f"$HOME/.pickfit-bg/{tag}.log"
    # `&` applies to one command, so the shell forks it straight into `detach`: with `a && b &`,
    # macOS's bash 3.2 keeps a subshell that holds the caller's stdout, and the command never
    # returns (measured 2026-10-29; bash 5 execs the last command and hid this on Linux).
    start = (f"mkdir -p $HOME/.pickfit-bg || exit 1; {detach} bash -c {shlex.quote(command)} "
             f"> {log} 2>&1 < /dev/null & P=$!; echo \"pid $P\"; ")
    if port:
        probe = (f"for i in $(seq 1 {max(wait_s, 1)}); do "
                 f"(echo > /dev/tcp/127.0.0.1/{port}) 2>/dev/null && {{ echo \"port {port} open after ${{i}}s\"; ok=1; break; }}; "
                 f"kill -0 $P 2>/dev/null || {{ echo 'process exited'; break; }}; sleep 1; done; ")
    else:
        probe = (f"sleep {min(wait_s, 5)}; kill -0 $P 2>/dev/null && {{ echo 'still running'; ok=1; }} "
                 "|| echo 'process exited'; ")
    return f"ok=0; {start}{probe}echo '--- log tail ---'; tail -n 40 {log}; test $ok = 1"


# ---------------------------------------------------------------- output capture


@dataclass
class _Capture:
    """Keeps the head and tail of a byte stream without holding all of it."""

    head_limit: int
    tail_limit: int
    head: bytearray = field(default_factory=bytearray)
    tail: bytearray = field(default_factory=bytearray)
    dropped: int = 0

    def feed(self, chunk: bytes) -> None:
        room = self.head_limit - len(self.head)
        if room > 0:
            self.head += chunk[:room]
            chunk = chunk[room:]
        self.tail += chunk
        excess = len(self.tail) - self.tail_limit
        if excess > 0:
            self.dropped += excess
            del self.tail[:excess]

    def text(self) -> str:
        if not self.dropped:
            return (self.head + self.tail).decode("utf-8", errors="replace")
        return (self.head.decode("utf-8", errors="replace")
                + f"\n[... {self.dropped} bytes omitted ...]\n"
                + self.tail.decode("utf-8", errors="replace"))


def _pump(stream: IO[bytes], capture: _Capture) -> None:
    for chunk in iter(lambda: stream.read(65536), b""):
        capture.feed(chunk)


def run_captured(args: list[str], timeout_s: float, *, stdin: bytes | None = None,
                 head: int = OUTPUT_HEAD_BYTES, tail: int = OUTPUT_TAIL_BYTES) -> tuple[int, str, str, bool, bool]:
    """Run a host process, keeping head and tail of its output.

    Returns (exit_code, stdout, stderr, host_timed_out, truncated).
    """
    proc = subprocess.Popen(args, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = _Capture(head, tail), _Capture(head, tail)
    pumps = [threading.Thread(target=_pump, args=(proc.stdout, out), daemon=True),
             threading.Thread(target=_pump, args=(proc.stderr, err), daemon=True)]
    for t in pumps:
        t.start()
    if stdin is not None:
        try:
            proc.stdin.write(stdin)
            proc.stdin.close()
        except BrokenPipeError:
            pass
    timed_out = False
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = proc.wait()
        timed_out = True
    for t in pumps:
        t.join(timeout=5)
    return code, out.text(), err.text(), timed_out, bool(out.dropped or err.dropped)


# ---------------------------------------------------------------- docker daemon and image


def _docker_ok(docker: str = "docker") -> bool:
    try:
        return subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _desktop_app(docker: str = "docker") -> str:
    """The macOS app that serves the current docker context: OrbStack or Docker Desktop."""
    try:
        host = subprocess.run([docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                              capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        host = ""
    if "orbstack" in host or (not Path("/Applications/Docker.app").exists()
                              and Path("/Applications/OrbStack.app").exists()):
        return "OrbStack"
    return "Docker"


def ensure_docker(wait_s: float = DOCKER_WAIT_S, *, docker: str = "docker",
                  log: Callable[[str], None] = print) -> None:
    """Make sure the Docker daemon answers; on macOS, open the desktop app and wait for it."""
    if shutil.which(docker) is None:
        raise BoxError("docker CLI not found")
    if _docker_ok(docker):
        return
    if sys.platform != "darwin":
        raise BoxError("the Docker daemon is not running")
    app = _desktop_app(docker)
    log(f"Docker daemon is not running; opening {app} and waiting up to {wait_s:.0f}s")
    subprocess.run(["open", "-a", app], check=False)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if _docker_ok(docker):
            return
        time.sleep(2)
    raise BoxError(f"the Docker daemon did not come up within {wait_s:.0f}s after opening {app}")


def sandbox_image_tag(dockerfile: Path = SANDBOX_DOCKERFILE) -> str:
    """Tag derived from the Dockerfile, so editing it builds a new image."""
    digest = hashlib.sha256(dockerfile.read_bytes()).hexdigest()[:12]
    return f"pickfit-sbx:{digest}"


def ensure_image(tag: str, platform: str, *, dockerfile: Path = SANDBOX_DOCKERFILE,
                 docker: str = "docker", log: Callable[[str], None] = print) -> None:
    """Build the sandbox image for `platform` unless it already exists."""
    inspect = subprocess.run([docker, "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", tag],
                             capture_output=True, text=True)
    if inspect.returncode == 0 and inspect.stdout.strip() == platform:
        return
    log(f"building {tag} for {platform} (first run only)")
    started = time.monotonic()
    proc = subprocess.run([docker, "build", "--platform", platform, "-t", tag, "-"],
                          input=dockerfile.read_bytes(), capture_output=True, timeout=1800)
    if proc.returncode != 0:
        raise BoxError(f"docker build {tag} failed: {proc.stderr.decode(errors='replace')[-1500:]}")
    log(f"built {tag} in {time.monotonic() - started:.0f}s")


# ---------------------------------------------------------------- DockerBox


class DockerBox(Box):
    """A locked-down local container. Only for known tools during development."""

    runner = "docker-runc"

    def __init__(self, *, image: str | None = None, platform: str = "linux/amd64",
                 limits: BoxLimits = BoxLimits(), name: str | None = None,
                 labels: dict[str, str] | None = None, docker: str = "docker",
                 build: bool = True, log: Callable[[str], None] = print) -> None:
        self.image = image or sandbox_image_tag()
        self.platform = platform
        self.arch = {"linux/amd64": "x86_64", "linux/arm64": "arm64"}.get(platform, platform)
        self.limits = limits
        self.name = name or f"pf-verify-{secrets.token_hex(4)}"
        self.labels = {"pickfit": "verify", **(labels or {})}
        self.docker = docker
        self.build = build
        self.log = log
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True

    # -- lifecycle

    def run_args(self) -> list[str]:
        """The `docker run` command line (separate so tests can check the limits)."""
        lim = self.limits
        args = [self.docker, "run", "-d", "--rm", "--init", "--name", self.name,
                "--platform", self.platform, "--network", "bridge",
                "--user", "1000:1000", f"--cpus={lim.cpus}", f"--memory={lim.memory_mb}m",
                f"--memory-swap={lim.memory_mb}m", f"--pids-limit={lim.pids}",
                "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--ulimit", f"nofile={lim.nofile}:{lim.nofile}", "--read-only",
                "--tmpfs", f"/tmp:rw,exec,nosuid,size={lim.tmp_mb}m",
                "--tmpfs", f"{BOX_HOME}:rw,exec,nosuid,size={lim.home_mb}m,uid=1000,gid=1000,mode=0755"]
        for key, value in self.labels.items():
            args += ["--label", f"{key}={value}"]
        for key, value in BOX_ENV.items():
            args += ["-e", f"{key}={value}"]
        # PID 1 (after tini) is a timer: the box dies when its lifetime runs out.
        return [*args, self.image, "sleep", str(lim.lifetime_s)]

    def start(self) -> None:
        if self.started:
            return
        ensure_docker(docker=self.docker, log=self.log)
        if self.build:
            ensure_image(self.image, self.platform, docker=self.docker, log=self.log)
        began = time.monotonic()
        proc = subprocess.run(self.run_args(), capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            raise BoxError(f"docker run failed: {proc.stderr.strip()[-1000:]}")
        self.start_s = round(time.monotonic() - began, 2)
        self.started = True
        setup = self.exec(f"mkdir -p {BOX_WORKDIR} {BOX_HOME}/.local/bin", 30, cwd="/")
        if not setup.ok:
            self.close()
            raise BoxError(f"box setup failed: {setup.stderr.strip()[-500:]}")
        try:
            self._block_metadata()
        except BoxError:
            self.close()
            raise

    def _root(self, script: str, timeout_s: int = 30) -> subprocess.CompletedProcess[str]:
        """Harness-only root command (route setup); never used for model commands."""
        return subprocess.run([self.docker, "exec", "-u", "0", "--privileged", self.name, "sh", "-c", script],
                              capture_output=True, text=True, timeout=timeout_s)

    def _block_metadata(self) -> None:
        proc = self._root(f"ip route replace unreachable {METADATA_CIDR} && "
                          f"{{ ip -6 route replace unreachable {METADATA_CIDR6} 2>/dev/null; "
                          f"ip route show type unreachable; }}")
        if f"unreachable {METADATA_CIDR}" not in proc.stdout:
            raise BoxError(f"could not block cloud metadata: {(proc.stdout + proc.stderr).strip()[-300:]}")

    def close(self) -> None:
        if not self.started:
            return
        subprocess.run([self.docker, "rm", "-f", self.name], capture_output=True, timeout=60)
        self.started = False

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        # Killed inside the box: killing only the host-side `docker exec` would leave it running.
        args = [self.docker, "exec", "-w", cwd or self.workdir, self.name,
                "timeout", "-s", "KILL", str(timeout_s), "bash", "-c", command]
        began = time.monotonic()
        code, out, err, host_timeout, truncated = run_captured(args, timeout_s + HOST_GRACE_S)
        seconds = round(time.monotonic() - began, 2)
        # `timeout -s KILL` exits 137 (it kills its own process group too); plain timeout says 124.
        timed_out = host_timeout or (code in (124, 137) and seconds >= timeout_s - 0.5)
        if host_timeout:
            code = 124
        return ExecResult(command=command, exit_code=code, stdout=out, stderr=err,
                          seconds=seconds, timed_out=timed_out, truncated=truncated)

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        # The path is passed as $1, never spliced into the script.
        script = 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"'
        code, _, err, _, _ = run_captured(
            [self.docker, "exec", "-i", "-w", self.workdir, self.name, "sh", "-c", script, "sh", path],
            60, stdin=data)
        if code != 0:
            raise BoxError(f"cannot write {path}: {err.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        proc = subprocess.run(
            [self.docker, "exec", "-w", self.workdir, self.name, "head", "-c", str(max_bytes), "--", path],
            capture_output=True, timeout=60)
        if proc.returncode != 0:
            raise BoxError(f"cannot read {path}: {proc.stderr.decode(errors='replace').strip()[-300:]}")
        return proc.stdout

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        verb = "connect" if enabled else "disconnect"
        proc = subprocess.run([self.docker, "network", verb, "bridge", self.name],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise BoxError(f"docker network {verb} failed: {proc.stderr.strip()[-300:]}")
        self.network_enabled = enabled
        if enabled:
            self._block_metadata()  # a reconnected interface comes back with fresh routes
