"""SshMachine: a rented Linux VM as a Machine, driven over SSH. What every plain-VM provider shares.

A provider that rents VMs (EC2: ec2_machine.Ec2Machine) adds four things: create a VM from an image that holds
Docker and the sandbox image, close and open its egress from outside it, seal what only that cloud has (its
metadata service), destroy it. The rest is here and is the same on all of them.

- Keys made for this one machine. The harness makes a login key and the VM's host key, hands the public login
  key and the host key over in the cloud-init user data, and pins the host key: the first connection is already
  verified, and no key outlives the machine.
- The box is a container of the sandbox image on the VM: privileged, on the VM's own network, with the box's
  memory and CPU as its cgroup. The container is only how sandbox.Dockerfile's image gets onto a VM unchanged.
  Root in it is root on the VM, with a kernel of its own under it, so `runtime` is "vm" and LinuxBox hardens it
  the way it hardens any VM. Going over the memory limit kills the process that did, not the machine.
- Root commands are `ssh root@vm docker exec`, over one multiplexed connection. The connection comes in from
  the harness, so no egress rule closes it.
- The VM powers itself off after its lifetime: cloud-init arms a systemd timer early in the boot, before sshd
  answers, and boot() checks it is armed; the provider makes poweroff mean destroyed. boot() does not wait for
  the rest of cloud-init (measured on EC2 2026-11-16: its last stage ends about 30 s after sshd answers, behind
  dockerd's start).
- The VM's kernel has no vsock: the image keeps the modules from loading and start() checks. Nothing on a rented
  VM needs it. Measured on EC2's stock Debian 2026-11-16: the modules load at boot (systemd's ssh generator asks
  for a vsock address), the loopback transport then resets root's every connection, and the limits test's
  control, which wants a port root can open or no vsock at all, decides nothing.
- Rules on the VM itself, for every uid but root (HOST_GUARD): link-local addresses (cloud metadata, a cloud's
  link-local resolver and time service) are dropped whatever the provider's own switch says, and the VM's sshd
  is closed to the box.
- The cut has two halves. Outside the VM the provider closes egress, where root inside cannot widen it. That
  alone is not enough on a stateful firewall: AWS documents that a security group "continues to allow packets
  until existing connections time out", so a connection the box user opened online would live on. So root also
  drops every non-loopback packet of every uid but root on the VM (CUT_ON), before the provider's cut. A
  connection root itself opened before the cut is the one thing neither half ends at once; pickfit's root opens
  none.

Needs the system's ssh and ssh-keygen (OpenSSH); nothing else is installed.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pickfit.verify.box import BoxError
from pickfit.verify.machine import Machine

SSH = "/usr/bin/ssh"
SSH_KEYGEN = "/usr/bin/ssh-keygen"
DOCKER = "/usr/bin/docker"
NFT = "/usr/sbin/nft"
CONTAINER = "pickfit-box"
BOOT_WAIT_S = 240  # from "the provider says it runs" to sshd answering with this machine's keys
CONNECT_TIMEOUT_S = 5  # one try at the port; a machine still booting drops the packets
CONNECT_RETRY_S = 1
SSH_GRACE_S = 10  # the local ssh client is killed this long after the in-machine timeout
SHM_MB = 1024  # /dev/shm: browsers and Electron apps need more than Docker's 64 MB
# The resolvers the VM got from its network, as systemd-resolved lists them. A container on the VM's network
# would otherwise be given the VM's stub (127.0.0.53), and every lookup in the box would be made by the stub's
# own uid: the offline rule stops that uid with every other, so root in the box resolved nothing offline
# (measured on EC2 2026-11-17), and limits.py's display probe, whose control is root's lookup, decided nothing.
# Asked directly, the provider's resolver answers root offline and the box user's query never leaves.
RESOLV_CONF = "/run/systemd/resolve/resolv.conf"

GUARD_TABLE = "pickfit_vm"
# Loaded once, before the box exists. fd00:ec2::/32 holds AWS's IPv6 metadata address; the rule costs nothing
# elsewhere. `fib daddr type local`: any of the VM's own addresses, so its sshd is closed on all of them.
HOST_GUARD = f"""table inet {GUARD_TABLE} {{
  chain out {{
    type filter hook output priority -10; policy accept;
    meta skuid != 0 ip daddr 169.254.0.0/16 drop
    meta skuid != 0 ip6 daddr {{ fe80::/10, fd00:ec2::/32 }} drop
    meta skuid != 0 fib daddr type local tcp dport 22 reject with tcp reset
  }}
}}
"""
LIFETIME_UNIT = "pickfit-lifetime"
# Lines for /etc/modprobe.d of a VM image: no vsock family module loads, on request or as a dependency.
NO_VSOCK_MODULES = tuple(f"install {name} /bin/false" for name in (
    "vsock", "vsock_loopback", "vsock_diag", "vmw_vsock_vmci_transport", "vmw_vsock_virtio_transport",
    "vmw_vsock_virtio_transport_common", "hv_sock", "vhost_vsock"))
VSOCK_ABSENT = "! /usr/bin/test -e /sys/module/vsock"
CUT_TABLE = "pickfit_vm_cut"
_CUT_RULES = (f"add table inet {CUT_TABLE}; add chain inet {CUT_TABLE} out "
              "{ type filter hook output priority -5; policy accept; }; "
              f'add rule inet {CUT_TABLE} out meta skuid != 0 oifname != "lo" drop')
# Both leave the table in the state asked for whatever it was before, and fail if it is not.
CUT_ON = (f"{NFT} list table inet {CUT_TABLE} > /dev/null 2>&1 || {NFT} {shlex.quote(_CUT_RULES)}; "
          f"{NFT} list table inet {CUT_TABLE} | /usr/bin/grep -q 'oifname != \"lo\" drop'")
CUT_OFF = (f"{NFT} list table inet {CUT_TABLE} > /dev/null 2>&1 && {NFT} delete table inet {CUT_TABLE}; "
           f"! {NFT} list table inet {CUT_TABLE} > /dev/null 2>&1")


_sleep = time.sleep  # patched in tests
_now = time.monotonic


def lifetime_bootcmd(lifetime_s: int) -> list[str]:
    """The cloud-init bootcmd that powers the machine off after its lifetime. DefaultDependencies=no: a timer
    otherwise starts after sysinit.target, Debian runs this stage before it, and systemd-run waits for the timer,
    so the boot waited for itself (measured 2026-11-16: sshd never came up, with --no-block too). The timeout keeps
    a systemd-run that hangs anyway from holding the boot: the machine then answers with no timer and is closed."""
    return ["/usr/bin/timeout", "20", "/usr/bin/systemd-run", "--unit", LIFETIME_UNIT, "--on-active",
            f"{int(lifetime_s)}s", "--timer-property", "AccuracySec=1s", "--timer-property",
            "DefaultDependencies=no", "--property", "DefaultDependencies=no", "/usr/bin/systemctl", "poweroff"]


def cloud_config(login_public: str, host_private: str, host_public: str, lifetime_s: int) -> str:
    """The cloud-init user data of a machine: root logs in with this machine's key only, sshd answers with the
    host key the harness already knows, no default user is made (its uid would be the box user's), and the
    machine powers off after its lifetime. bootcmd runs before the keys are written, so a machine that answers
    with them has been through it; boot() checks the timer. JSON, which is YAML."""
    config = {"disable_root": False, "ssh_pwauth": False,
              "users": [{"name": "root", "ssh_authorized_keys": [login_public]}],
              "ssh_deletekeys": True,
              "ssh_keys": {"ed25519_private": host_private, "ed25519_public": host_public},
              "bootcmd": [lifetime_bootcmd(lifetime_s)]}
    return "#cloud-config\n" + json.dumps(config, indent=1) + "\n"


class _Stdin:
    """A local pipe with the three calls machine.Process promises; a write to a command that has ended raises."""

    def __init__(self, pipe: Any) -> None:
        self.pipe = pipe

    def write(self, data: bytes) -> None:
        self.pipe.write(data)

    def drain(self) -> None:
        if not self.pipe.closed:
            self.pipe.flush()

    def write_eof(self) -> None:
        try:
            self.pipe.close()
        except BrokenPipeError:  # the command ended before reading it all
            pass


class _Stream:
    """One output stream, read as it comes into a queue: a caller may read stdout to its end before it looks at
    stderr (WebBox.root does) without the command blocking on a full pipe."""

    def __init__(self, pipe: Any) -> None:
        self.chunks: queue.Queue[bytes | None] = queue.Queue()
        self.done = False
        threading.Thread(target=self._pump, args=(pipe,), daemon=True).start()

    def _pump(self, pipe: Any) -> None:
        try:
            while chunk := pipe.read1(65536):
                self.chunks.put(chunk)
        except (OSError, ValueError):  # closed under us: the client was killed
            pass
        self.chunks.put(None)

    def __iter__(self) -> Any:
        while not self.done:
            chunk = self.chunks.get()
            if chunk is None:
                self.done = True
                return
            yield chunk


class SshProcess:
    """A command on the machine, as machine.Process. The local client is killed `kill_after_s` after it starts
    (the command has its own timeout inside the machine; this ends a client whose command left something holding
    its output open), and wait() then returns 124."""

    def __init__(self, popen: Any, kill_after_s: float, lost: Callable[[], bool] = lambda: False) -> None:
        self.popen = popen
        self.stdin = _Stdin(popen.stdin)
        self.stdout = _Stream(popen.stdout)
        self.stderr = _Stream(popen.stderr)
        self.lost = lost
        self.killed = False
        self.timer = threading.Timer(kill_after_s, self._kill)
        self.timer.daemon = True
        self.timer.start()

    def _kill(self) -> None:
        if self.popen.poll() is None:
            self.killed = True
            self.popen.kill()
            # A client on a shared connection hands its pipes to the connection's own process, which keeps them
            # open for as long as the command runs on the machine: the streams end here, not at their EOF.
            for stream in (self.stdout, self.stderr):
                stream.chunks.put(None)

    def wait(self) -> int:
        code = self.popen.wait()
        self.timer.cancel()
        if self.killed:
            return 124
        if code == 255 and self.lost():  # ssh's own failure code, and the connection is gone
            raise ConnectionError("the ssh connection to the machine was lost")
        return code


class SshLink:
    """One machine reached over SSH with keys made for it: a login key, the machine's pinned host key, and one
    shared connection per login user. The half of SshMachine a Windows machine shares (win_machine.py)."""

    provider: str = "machine"
    machine_id: str | None = None
    login_user = "root"  # the user every call logs in as unless it names another

    def _init_link(self, popen: Callable[..., Any], run: Callable[..., Any]) -> None:
        self.popen = popen  # starts the ssh client of a command on the machine
        self.run_local = run  # runs ssh-keygen and ssh's own control commands to their end
        self._last_ssh_error = ""
        self.address: str | None = None
        self.keys_dir: Path | None = None

    def _make_keys(self) -> tuple[str, str, str]:
        """(login public key, host private key, host public key), new in a directory of this machine's own.
        /tmp: a unix socket's path is short (104 bytes on macOS), and the connection's socket lives here too."""
        self.keys_dir = Path(tempfile.mkdtemp(prefix="pf-", dir="/tmp"))
        for name in ("login", "host"):
            made = self.run_local([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C", "pickfit", "-f",
                                   str(self.keys_dir / name)], capture_output=True, text=True)
            if made.returncode != 0:
                raise BoxError(f"ssh-keygen failed: {made.stderr.strip()[-200:]}")
        return ((self.keys_dir / "login.pub").read_text().strip(), (self.keys_dir / "host").read_text(),
                (self.keys_dir / "host.pub").read_text().strip())

    def _control_path(self, user: str | None = None) -> Path:
        assert self.keys_dir is not None
        user = user or self.login_user
        return self.keys_dir / ("cm" if user == self.login_user else f"cm-{user}")

    def ssh_argv(self, *extra: str, user: str | None = None) -> list[str]:
        """ssh to the machine with nothing of the user's own: no config, no agent, no known hosts but this
        machine's pinned key."""
        assert self.keys_dir is not None and self.address is not None
        d = self.keys_dir
        return [SSH, "-F", "/dev/null", "-i", str(d / "login"), "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
                "-o", f"UserKnownHostsFile={d / 'known_hosts'}", "-o", "GlobalKnownHostsFile=/dev/null",
                "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={CONNECT_TIMEOUT_S}", "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=4", "-o", "LogLevel=ERROR", "-o", f"ControlPath={self._control_path(user)}",
                *extra, "-T", f"{user or self.login_user}@{self.address}"]

    def _master(self, user: str | None = None) -> bool:
        """Open the one connection every command of that user shares; False if sshd does not answer yet."""
        try:
            opened = self.run_local([*self.ssh_argv("-o", "ControlMaster=yes", "-o", "ControlPersist=yes", "-N", "-f",
                                                    user=user)],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            self._last_ssh_error = "ssh did not return in 30s"
            return False
        self._last_ssh_error = opened.stderr.strip()[-200:]
        return opened.returncode == 0

    def _connected(self, user: str | None = None) -> bool:
        return self._control_path(user).exists()

    def forward(self, remote_port: int) -> int:
        """A port on this host's loopback that reaches the machine's own loopback port `remote_port`, through the
        login user's shared connection (the forward ends with it)."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        done = self.run_local([*self.ssh_argv("-O", "forward", "-L", f"127.0.0.1:{port}:127.0.0.1:{remote_port}")],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        if done.returncode != 0:
            raise BoxError(f"no forward to the machine's port {remote_port}: {done.stderr.strip()[-200:]}")
        return port

    def cancel_forward(self, port: int, remote_port: int) -> None:
        self.run_local([*self.ssh_argv("-O", "cancel", "-L", f"127.0.0.1:{port}:127.0.0.1:{remote_port}")],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)

    def _lost(self, user: str | None = None) -> bool:
        if self.keys_dir is None or self.address is None:
            return True
        try:
            check = self.run_local([*self.ssh_argv("-O", "check", user=user)], stdin=subprocess.DEVNULL,
                                   capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return True
        return check.returncode != 0

    def _pin_host_key(self) -> None:
        assert self.keys_dir is not None and self.address is not None
        host_public = " ".join((self.keys_dir / "host.pub").read_text().split()[:2])
        (self.keys_dir / "known_hosts").write_text(f"{self.address} {host_public}\n")

    def _connect(self, user: str | None = None, wait_s: float = BOOT_WAIT_S) -> None:
        self._pin_host_key()
        deadline = _now() + wait_s
        while not self._master(user):
            if _now() > deadline:
                raise BoxError(f"sshd on {self.provider} machine {self.machine_id} did not answer in {wait_s:.0f}s: "
                               f"{self._last_ssh_error}")
            _sleep(CONNECT_RETRY_S)

    def _ssh_spawn(self, command: str, kill_after_s: float, user: str | None = None) -> SshProcess:
        """Start a command line on the machine as that user; the machine's own shell reads it."""
        if not self._connected(user):
            self._master(user)  # the shared connection died; without it each command opens its own
        proc = self.popen([*self.ssh_argv("-o", "ControlMaster=no", user=user), "--", command],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return SshProcess(proc, kill_after_s, lambda: self._lost(user))

    def _drop_connections(self, users: tuple[str, ...] = ()) -> None:
        """End the shared connections (the login user's and those users'); the keys stay."""
        if self.keys_dir is None or self.address is None:
            return
        for user in (None, *users):
            try:
                self.run_local([*self.ssh_argv("-O", "exit", user=user)], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
            self._control_path(user).unlink(missing_ok=True)

    def _close_link(self, users: tuple[str, ...] = ()) -> None:
        """End the shared connections and delete this machine's keys."""
        if self.keys_dir is None:
            return
        self._drop_connections(users)
        shutil.rmtree(self.keys_dir, ignore_errors=True)


class SshMachine(SshLink, Machine):
    """A VM over SSH with the box as a container on it. A provider implements _create, _provider_egress and
    _destroy, and _seal if its cloud has something to close."""

    runtime = "vm"
    container_image = ""  # the sandbox image's tag inside the VM image (start() runs it; boot() alone does not)
    # Directories of the container read once before start() returns, for what must start within a deadline on a
    # volume that fetches its blocks on first read (WebBox's Chromium has 30 s to open its DevTools port; measured
    # on EC2 2026-11-17, on a new volume it did not). Many readers at once: such a volume answers each first read
    # slowly and many of them no slower. A machine whose disk was read before (warm) skips it.
    preread: tuple[str, ...] = ()
    warm = False  # a provider sets it for a machine that booted once already and read its disk (EC2's pool)

    def __init__(self, *, cores: float, memory_mb: int, lifetime_s: int, log: Callable[[str], None] = print,
                 popen: Callable[..., Any] = subprocess.Popen, run: Callable[..., Any] = subprocess.run) -> None:
        self.cores = cores
        self.memory_mb = memory_mb
        self.lifetime_s = lifetime_s
        self.log = log
        self._init_link(popen, run)
        self.timings: dict[str, float] = {}  # seconds each part of start() took
        self._closed = False

    # -- what a provider gives

    @abstractmethod
    def _create(self, user_data: str) -> str:
        """Create the VM with this cloud-init user data and egress limited to ONLINE_CIDRS; set machine_id and
        return the address the harness reaches it on."""

    @abstractmethod
    def _provider_egress(self, enabled: bool) -> None:
        """Open egress to ONLINE_CIDRS or close it, outside the VM; return once it is so, BoxError if not."""

    @abstractmethod
    def _destroy(self) -> None:
        """Destroy the VM and what was made for it."""

    def _seal(self) -> None:
        """Close what only this cloud has (its metadata service), after boot and before the box exists."""

    # -- commands on the VM itself

    def _host_spawn(self, argv: list[str], kill_after_s: float) -> SshProcess:
        """Start argv as root on the VM itself (not in the box)."""
        return self._ssh_spawn(shlex.join(argv), kill_after_s)

    def host(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None) -> tuple[int, str, str]:
        """Run argv as root on the VM itself to its end; (exit code, stdout, stderr)."""
        proc = self._host_spawn(["/usr/bin/timeout", "--signal=KILL", str(int(timeout_s)), *argv],
                                timeout_s + SSH_GRACE_S)
        try:
            if stdin is not None:
                proc.stdin.write(stdin)
            proc.stdin.write_eof()
        except BrokenPipeError:
            pass
        out = b"".join(proc.stdout)
        err = b"".join(proc.stderr)
        return proc.wait(), out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    def _host_checked(self, argv: list[str], timeout_s: int, what: str, *, stdin: bytes | None = None,
                      ok: tuple[int, ...] = (0,)) -> str:
        try:
            code, out, err = self.host(argv, timeout_s, stdin=stdin)
        except (OSError, ConnectionError) as error:
            raise BoxError(f"{what} failed: {type(error).__name__}: {error}") from error
        if code not in ok:
            raise BoxError(f"{what} failed (exit {code}): {(out + err).strip()[-400:]}")
        return out

    # -- lifecycle

    def user_data(self) -> str:
        login_public, host_private, host_public = self._make_keys()
        return cloud_config(login_public, host_private, host_public, self.lifetime_s)

    def _recreate(self) -> str | None:
        """The address of a second machine in place of one that did not answer, or None when the provider has no
        other way to make one (a pool member that booted with someone else's keys is replaced by a new machine)."""
        return None

    def boot(self) -> None:
        """Create the VM and wait until it is up and ours: sshd answers with the pinned host key, and the
        lifetime's poweroff is armed. Closes the machine and raises BoxError if not."""
        try:
            began = time.monotonic()
            self.address = self._create(self.user_data())
            self.timings["create_s"] = round(time.monotonic() - began, 1)
            began = time.monotonic()
            try:
                self._connect(wait_s=getattr(self, "boot_wait_s", BOOT_WAIT_S))
            except BoxError:
                again = self._recreate()
                if again is None:
                    raise
                self.address = again
                self._connect(wait_s=getattr(self, "boot_wait_s", BOOT_WAIT_S))
            self.timings["ssh_s"] = round(time.monotonic() - began, 1)
            self._host_checked(["/usr/bin/systemctl", "is-active", f"{LIFETIME_UNIT}.timer"], 20,
                               "the lifetime's poweroff is not armed; checking it")
        except BaseException as error:
            self.close()
            if isinstance(error, BoxError) or not isinstance(error, Exception):
                raise
            raise BoxError(f"{self.provider} machine start failed: {type(error).__name__}: {error}") from error

    def container_argv(self) -> list[str]:
        """docker run for the box (separate so tests can check it). No swap, so the memory limit is the limit. The
        box asks the provider's resolver itself (RESOLV_CONF), not the VM's local stub."""
        return [DOCKER, "run", "--detach", "--name", CONTAINER, "--init", "--privileged", "--network", "host",
                "--memory", f"{self.memory_mb}m", "--memory-swap", f"{self.memory_mb}m", "--cpus", f"{self.cores:g}",
                "--shm-size", f"{SHM_MB}m", "--volume", f"{RESOLV_CONF}:/etc/resolv.conf:ro", "--workdir", "/",
                self.container_image, "/usr/bin/sleep", "infinity"]

    def start(self) -> None:
        self.boot()
        try:
            began = time.monotonic()
            self._seal()
            self._host_checked(["/usr/bin/bash", "-c", VSOCK_ABSENT], 20,
                               "the VM's kernel has vsock loaded; checking it")
            self._host_checked([NFT, "-f", "-"], 30, "the VM's own rules", stdin=HOST_GUARD.encode())
            self._host_checked(self.container_argv(), 120, "starting the box's container")
            self.timings["box_s"] = round(time.monotonic() - began, 1)
            if self.preread and not self.warm:
                began = time.monotonic()
                read = (f"/usr/bin/find {shlex.join(self.preread)} -xdev -type f -print0 2> /dev/null | "
                        "/usr/bin/xargs -0 -P 32 -n 16 /usr/bin/cat > /dev/null 2>&1; true")
                self._host_checked([DOCKER, "exec", CONTAINER, "/bin/sh", "-c", read], 600,
                                   "reading the container's programs")
                self.timings["read_s"] = round(time.monotonic() - began, 1)
        except BaseException as error:
            self.close()
            if isinstance(error, BoxError) or not isinstance(error, Exception):
                raise
            raise BoxError(f"{self.provider} machine start failed: {type(error).__name__}: {error}") from error
        self.log(f"{self.provider} machine {self.machine_id} up: " +
                 ", ".join(f"{name[:-2]} {seconds}s" for name, seconds in self.timings.items()))

    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> SshProcess:
        where = ["--workdir", workdir] if workdir is not None else []
        return self._host_spawn([DOCKER, "exec", "--interactive", *where, CONTAINER, "/usr/bin/timeout",
                                 "--signal=KILL", str(int(timeout_s)), *argv], timeout_s + SSH_GRACE_S)

    def set_egress(self, enabled: bool) -> None:
        if enabled:  # the provider first: while its cut holds, the box user's rule changes nothing
            self._provider_egress(True)
            self._host_checked(["/usr/bin/bash", "-c", CUT_OFF], 30, "removing the VM's offline rule")
        else:  # the rule first: it ends what the box user already has open, which a stateful firewall would not
            self._host_checked(["/usr/bin/bash", "-c", CUT_ON], 30, "the VM's offline rule")
            self._provider_egress(False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._destroy()
        except Exception as error:  # the lifetime's poweroff ends it anyway
            self.log(f"{self.provider} destroy: {type(error).__name__}: {error}")
        self._close_link()

    def explain(self, error: Exception) -> str:
        if isinstance(error, ConnectionError):
            return (f"the {self.provider} machine stopped answering during this command (it was destroyed, or it "
                    f"reached its {self.lifetime_s}s lifetime): {error}")
        return f"{self.provider} exec failed: {type(error).__name__}: {error}"[:400]


def have_ssh() -> bool:
    return os.access(SSH, os.X_OK) and os.access(SSH_KEYGEN, os.X_OK)
