"""ModalBox: the Box interface on a Modal Sandbox under gVisor (P3.6).

- Runtime gVisor, CPU and memory as request = limit (1 physical core is 2
  vCPU), a lifetime timeout; every command also runs under an in-box
  `timeout -s KILL`.
- Commands run as uid 1000 through `setpriv` (no capabilities, no new
  privileges), with an empty environment except BOX_ENV, and `ulimit` caps on
  processes, open files and file size: Modal has no pids or disk parameter.
- Network: created with an allowlist of public IPv4 ranges, so it can be
  tightened later; cloud metadata (169.254.0.0/16) and private ranges are
  never on it. set_network(False) replaces it with an empty allowlist
  (`_experimental_set_outbound_network_policy`, Alpha). Modal's resolver
  172.21.0.1 still answers with an empty allowlist (both runtimes), and a
  running box cannot be switched to Modal's blocked mode, so each runtime
  closes DNS itself (below).
- gVisor (measured 2026-10-31): root has neither CAP_NET_ADMIN nor CAP_SYS_ADMIN and gVisor has no netfilter, so
  no rule, route or link change can close the resolver. Instead the box user never touches the box's own network:
  NET_UID makes a user and network namespace at start (root writes its maps: NET_UID is root inside it, the box user
  is itself, nothing else is mapped, so NET_UID has no power over root's or the display uid's files and processes),
  and every box-user command runs in it. Its only way out is slirp4netns, run as NET_UID (seccomp on, no route to
  the box's loopback, MTU 65520 on both ends: a tap left at 1500 stalls TCP); it carries the box user's traffic, DNS included, through the box's network and
  Modal's allowlist. set_network(False) kills every NET_UID process except the namespace's holder and checks that
  the uplink's device is gone and the holder holds nothing but its standard streams: the box user then has loopback
  only, so localhost servers, including ones started
  online, still answer. The box user cannot enter another network namespace, change a route or signal NET_UID's
  processes. Downloads through it ran at the box's direct speed (CDNs 80-190 MB/s, a slow far server 1.2 MB/s
  either way). Xvfb and the watcher stay outside (display uid):
  the box user's apps reach Xvfb by its socket file, which a network namespace does not hide.
- Image: built once from sandbox.Dockerfile and published as
  `pickfit-sbx:<Dockerfile hash>`; boxes start from that name, and only a
  missing name triggers the build. (`Image.from_name(...).hydrate()` is not
  supported by the client, so the name is resolved by Sandbox.create.)

- runtime="vm" (a microVM with its own kernel) is the same box otherwise, hardened by root before the box
  user runs anything (measured 2026-10-31): unprivileged user namespaces and io_uring are switched off; every
  box-user command runs under a seccomp filter that refuses AF_VSOCK sockets (the host's vsock port 52
  accepted the box user's connection); and while the network is off, an nftables rule drops the box user's
  DNS (a VM has netfilter; with user namespaces off, the gVisor way is closed to it). A VM gives 1 vCPU per
  requested core.
- display=True adds GUI_PACKAGES to the image; root starts Xvfb as a separate uid (DISPLAY_UID), which the box
  user can draw on but cannot kill or replace. Evidence (window list, screenshot, its hash and copy) is made by
  root and DISPLAY_UID through harness_exec, by absolute path, in a directory the box user cannot open.
- Commands name their programs by absolute path: the box user's ~/.local/bin comes first on its PATH.

Credentials come from MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in .env and go to
an explicit modal.Client; nothing is put into the process environment, and the
sandbox gets no secrets.
"""

from __future__ import annotations

import hashlib
import ipaddress
import shlex
import threading
import time
from collections.abc import Callable
from typing import Any

from pickfit.env import require_env
from pickfit.verify.box import (
    BOX_ENV,
    BOX_HOME,
    BOX_WORKDIR,
    HOST_GRACE_S,
    OUTPUT_HEAD_BYTES,
    OUTPUT_TAIL_BYTES,
    SANDBOX_DOCKERFILE,
    Box,
    BoxError,
    BoxLimits,
    ExecResult,
    _Capture,
    sandbox_image_tag,
)
from pickfit.verify.gui import DISPLAY, DISPLAY_UID, EVIDENCE_DIR, GUI_PACKAGES, HARNESS_PATH, PYTHON, xvfb_script

APP_NAME = "pickfit-verify"
READ_TIMEOUT_S = 20  # read_file: a FIFO or a device would block `head` forever
# Sandbox prices (3x the function rates), docs/research/notes/sandbox-compare.md, read 2026-10-28.
# Billed on max(request, use); request = limit here, so this is the cost per second alive.
CORE_USD_PER_S = 0.00003942
GIB_USD_PER_S = 0.00000667
# GPU sandboxes run only under gVisor, can be preempted, and bill GPUs at the
# plain rate (same note, read 2026-10-28). Only the small cards: a local AI
# tool's smoke test runs the smallest model it supports.
GPU_USD_PER_S = {"T4": 0.59 / 3600, "L4": 0.80 / 3600, "A10": 1.10 / 3600}
BOX_UID = 1000
NET_UID = 1002  # gVisor: owns the box user's network namespace and runs its uplink; root only inside that namespace
UPLINK = "/usr/bin/slirp4netns"
TAP = "tap0"
# slirp4netns's defaults: the namespace is 10.0.2.100/24, the gateway (slirp itself) 10.0.2.2.
UPLINK_MTU = 65520
TAP_CONFIG = (f"/usr/bin/ip link set {TAP} mtu {UPLINK_MTU} up && /usr/bin/ip addr add 10.0.2.100/24 dev {TAP} && "
              f"/usr/bin/ip route add default via 10.0.2.2 dev {TAP}")
UPLINK_LOG = "/var/log/pickfit-uplink.log"
# Never reachable from a box: cloud metadata and link-local, private and shared address space.
BLOCKED_NETS = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12",
                "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4")


def public_cidrs(blocked: tuple[str, ...] = BLOCKED_NETS) -> list[str]:
    """0.0.0.0/0 minus `blocked`, as the fewest CIDRs."""
    nets = [ipaddress.ip_network("0.0.0.0/0")]
    for block in map(ipaddress.ip_network, blocked):
        nets = [part for net in nets
                for part in (net.address_exclude(block) if block.subnet_of(net) else
                             ([] if net.subnet_of(block) else [net]))]
    return [str(n) for n in ipaddress.collapse_addresses(nets)]


ONLINE_CIDRS = public_cidrs()
RUNTIMES = ("gvisor", "vm")
VM_PACKAGES = ("nftables",)  # root's offline DNS rule (VM only: gVisor has no netfilter)
# Drops the box user's DNS (to Modal's resolver or anywhere) while the network is off; root sets it.
DNS_TABLE = "pickfit_offline"
DNS_BLOCK = (f"/usr/sbin/nft add table inet {DNS_TABLE} && /usr/sbin/nft add chain inet {DNS_TABLE} out "
             "'{ type filter hook output priority 0; policy accept; }' && "
             f"/usr/sbin/nft add rule inet {DNS_TABLE} out meta skuid {BOX_UID} udp dport 53 drop && "
             f"/usr/sbin/nft add rule inet {DNS_TABLE} out meta skuid {BOX_UID} tcp dport 53 drop")
DNS_UNBLOCK = f"/usr/sbin/nft delete table inet {DNS_TABLE}"
# Root, before the box user runs anything in a VM (gVisor keeps user namespaces inside its own kernel).
VM_HARDEN = ("/usr/sbin/sysctl -qw user.max_user_namespaces=0 && "
             "{ /usr/sbin/sysctl -qw kernel.io_uring_disabled=2 2>/dev/null || true; } && "
             "/usr/bin/install -d -m 0755 /usr/local/lib/pickfit && "
             "/usr/bin/install -m 0644 /dev/stdin /usr/local/lib/pickfit/no_vsock.py")
NO_VSOCK = "/usr/local/lib/pickfit/no_vsock.py"
# A seccomp filter (x86_64): socket(AF_VSOCK, ...) fails with EAFNOSUPPORT, io_uring_setup/enter/register
# (425-427) with EPERM, other ABIs are killed; then exec. Inherited by every child and cannot be removed;
# setpriv has already set no_new_privs. The box user's commands, Xvfb and the watcher all run under it.
NO_VSOCK_SOURCE = r"""import ctypes, os, struct, sys
LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06
ALLOW, ERRNO, KILL = 0x7FFF0000, 0x00050000, 0x80000000
prog = [(LD, 0, 0, 4), (JEQ, 0, 10, 0xC000003E), (LD, 0, 0, 0), (JGE, 8, 0, 0x40000000), (JEQ, 0, 2, 41),
        (LD, 0, 0, 16), (JEQ, 3, 2, 40), (JGE, 0, 1, 425), (JGE, 0, 2, 428), (RET, 0, 0, ALLOW),
        (RET, 0, 0, ERRNO | 97), (RET, 0, 0, ERRNO | 1), (RET, 0, 0, KILL)]
raw = b"".join(struct.pack("HBBI", *ins) for ins in prog)
buf = ctypes.create_string_buffer(raw, len(raw))
class Prog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(Prog(len(prog), ctypes.addressof(buf))), 0, 0):
    sys.exit(f"pickfit: seccomp failed: {os.strerror(ctypes.get_errno())}")
os.execv(sys.argv[1], sys.argv[1:])
"""


def image_layers(runtime: str = "gvisor", display: bool = False) -> tuple[str, tuple[str, ...]]:
    """(published image name, apt packages added on top of sandbox.Dockerfile) for a kind of box.

    The plain box keeps `pickfit-sbx:<Dockerfile hash>`; a variant hashes the Dockerfile and its packages.
    """
    packages = (*(VM_PACKAGES if runtime == "vm" else ()), *(GUI_PACKAGES if display else ()))
    if not packages:
        return sandbox_image_tag(), ()
    digest = hashlib.sha256(SANDBOX_DOCKERFILE.read_bytes() + "\n".join(packages).encode()).hexdigest()[:12]
    kinds = "-".join(k for k, on in (("vm", runtime == "vm"), ("gui", display)) if on)
    return f"pickfit-sbx-{kinds}:{digest}", packages


def modal_client() -> Any:
    import modal

    return modal.Client.from_credentials(require_env("MODAL_TOKEN_ID"), require_env("MODAL_TOKEN_SECRET"))


def publish_image(client: Any, app: Any, *, log: Callable[[str], None] = print, runtime: str = "gvisor",
                  display: bool = False) -> str:
    """Build the sandbox image from sandbox.Dockerfile (plus the variant's packages) and publish it.

    Modal caches the build, so an unchanged Dockerfile takes a few seconds.
    """
    import modal

    name, packages = image_layers(runtime, display)
    began = time.monotonic()
    image = modal.Image.from_dockerfile(SANDBOX_DOCKERFILE, context_dir=SANDBOX_DOCKERFILE.parent,
                                        ignore=lambda path: True)
    if packages:
        image = image.apt_install(*packages)
    image.build(app)
    image.publish(name, client=client)
    log(f"Modal image {name} built and published in {time.monotonic() - began:.0f}s")
    return name


def ensure_published_image(log: Callable[[str], None] = print, *, runtime: str = "gvisor",
                           display: bool = False) -> str:
    """Publish the image for the current Dockerfile before parallel boxes start; returns its name."""
    import modal

    client = modal_client()
    app = modal.App.lookup(APP_NAME, create_if_missing=True, client=client)
    return publish_image(client, app, log=log, runtime=runtime, display=display)


def _missing_image(err: Exception) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return "notfound" in text.replace(" ", "") or "not found" in text


def _drop_to(uid: int) -> list[str]:
    return ["/usr/bin/setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", "--inh-caps=-all",
            "--no-new-privs", "--"]


# The maps go in one write each: the kernel takes a map from a single write, and bash's printf writes per line.
_MAP_PY = ("import sys\nfor name in ('uid_map', 'gid_map'):\n    with open(f'/proc/{sys.argv[1]}/{name}', 'w') as f:\n"
           f"        f.write('0 {NET_UID} 1\\n{BOX_UID} {BOX_UID} 1\\n')\n")


def netns_script() -> str:
    """Root (gVisor): NET_UID makes the box user's user and network namespace, kept by a holder process; root maps
    NET_UID to root inside it and the box user to itself. Prints `netns_pid N`."""
    drop = " ".join(_drop_to(NET_UID))
    return (f"{{ /usr/bin/setsid {drop} /usr/bin/unshare --user --net -- /usr/bin/sleep infinity "
            "> /dev/null 2>&1 < /dev/null & }; P=$!; "
            "for i in $(/usr/bin/seq 1 50); do "
            "[ \"$(/usr/bin/readlink /proc/$P/ns/net)\" != \"$(/usr/bin/readlink /proc/self/ns/net)\" ] && break; "
            "/usr/bin/sleep 0.1; done; "
            f"{PYTHON} -I -S -c {shlex.quote(_MAP_PY)} $P && echo \"netns_pid $P\"")


def uplink_script(netns_pid: int, enabled: bool) -> str:
    """Root (gVisor): start slirp4netns as NET_UID and route the namespace through it; or kill every NET_UID process
    but the holder and check that the device is gone, nothing else of NET_UID's runs and the holder holds only its
    standard streams (no socket handed to it from outside the namespace)."""
    drop = " ".join(_drop_to(NET_UID))
    inside = f"{drop} /usr/bin/nsenter --target={netns_pid} --user --net --"
    if enabled:
        return (f"{{ /usr/bin/setsid {drop} {UPLINK} --mtu={UPLINK_MTU} --disable-host-loopback --enable-seccomp "
                f"{netns_pid} {TAP} >> {UPLINK_LOG} 2>&1 < /dev/null & }}; "
                f"for i in $(/usr/bin/seq 1 50); do {inside} /usr/bin/ip link show {TAP} > /dev/null 2>&1 && break; "
                f"/usr/bin/sleep 0.1; done; {inside} /usr/bin/bash -c {shlex.quote(TAP_CONFIG)} || "
                f"{{ /usr/bin/tail -5 {UPLINK_LOG}; exit 1; }}")
    return (f"for p in $(/usr/bin/pgrep -u {NET_UID}); do [ \"$p\" = {netns_pid} ] || kill -KILL \"$p\"; done; "
            f"for i in $(/usr/bin/seq 1 50); do {inside} /usr/bin/ip link show {TAP} > /dev/null 2>&1 || break; "
            f"/usr/bin/sleep 0.1; done; {inside} /usr/bin/ip link show {TAP} > /dev/null 2>&1 && "
            f"{{ echo '{TAP} is still there'; exit 1; }}; left=\"$(/usr/bin/pgrep -u {NET_UID})\"; "
            f"[ \"$left\" = {netns_pid} ] || {{ echo \"NET_UID processes left: $left\"; exit 1; }}; "
            f"fds=\"$(/usr/bin/ls /proc/{netns_pid}/fd)\"; [ \"$(echo $fds)\" = '0 1 2' ] || "
            f"{{ echo \"the holder holds fds $(echo $fds)\"; exit 1; }}")


class ModalBox(Box):
    """A Modal Sandbox (gVisor, or a VM) driven like a DockerBox."""

    runner = "modal-gvisor"
    image = sandbox_image_tag()
    detach = "/usr/bin/setsid /usr/bin/nohup"

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 app_name: str = APP_NAME, client: Any = None, gpu: str | None = None,
                 runtime: str = "gvisor", display: bool = False, log: Callable[[str], None] = print) -> None:
        self.xvfb_pid: int | None = None
        if gpu is not None and gpu not in GPU_USD_PER_S:
            raise ValueError(f"gpu must be one of {sorted(GPU_USD_PER_S)}, got {gpu!r}")
        if runtime not in RUNTIMES:
            raise ValueError(f"runtime must be one of {RUNTIMES}, got {runtime!r}")
        if gpu and runtime != "gvisor":
            raise ValueError("Modal GPU sandboxes run only under gVisor")
        self.limits = limits
        self.gpu = gpu
        self.runtime = runtime
        self.runner = f"modal-{runtime}"
        self.display = DISPLAY if display else None
        self.image = image_layers(runtime, display)[0]
        self.tags = {"pickfit": "verify", **(tags or {})}
        self.app_name = app_name
        self.client = client
        self.log = log
        self.sandbox: Any = None
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.sandbox_id: str | None = None
        self.netns_pid: int | None = None  # gVisor: the holder of the box user's network namespace

    # -- lifecycle

    def create_kwargs(self) -> dict[str, Any]:
        """Sandbox.create arguments other than app, image and client (separate so tests can check them)."""
        lim = self.limits
        cores = lim.cpus / 2  # Modal counts physical cores; one core is two vCPU
        kwargs = {"runtime": self.runtime, "timeout": lim.lifetime_s, "cpu": (cores, cores),
                  "memory": (lim.memory_mb, lim.memory_mb), "workdir": "/",
                  "outbound_cidr_allowlist": ONLINE_CIDRS, "outbound_domain_allowlist": [],
                  "tags": self.tags}
        if self.gpu:
            kwargs["gpu"] = self.gpu
        return kwargs

    def start(self) -> None:
        if self.started:
            return
        import modal

        began = time.monotonic()
        self.client = self.client or modal_client()
        app = modal.App.lookup(self.app_name, create_if_missing=True, client=self.client)
        self.image = image_layers(self.runtime, self.display is not None)[0]

        def create() -> Any:
            return modal.Sandbox.create("sleep", str(self.limits.lifetime_s), app=app, client=self.client,
                                        image=modal.Image.from_name(self.image), **self.create_kwargs())

        try:
            try:
                self.sandbox = create()
            except Exception as err:
                if not _missing_image(err):
                    raise
                publish_image(self.client, app, log=self.log, runtime=self.runtime,  # first box after a change
                              display=self.display is not None)
                self.sandbox = create()
        except Exception as err:
            raise BoxError(f"Modal sandbox create failed: {type(err).__name__}: {err}") from err
        self.sandbox_id = getattr(self.sandbox, "object_id", None)
        self.started = True
        steps: list[tuple[str, ExecResult]] = []
        if self.runtime == "vm":
            steps.append(("VM hardening", self._exec_raw(["/usr/bin/bash", "-c", VM_HARDEN], 60, as_root=True,
                                                         stdin=NO_VSOCK_SOURCE.encode())))
        else:  # before the box user runs anything: it never has the box's own network
            netns = self._exec_raw(["/usr/bin/bash", "-c", netns_script()], 60, as_root=True)
            pid = next((line.split()[1] for line in netns.stdout.splitlines() if line.startswith("netns_pid ")), "")
            self.netns_pid = int(pid) if pid.isdigit() else None
            steps.append(("the box user's network namespace", netns))
            self._fail_on(steps, missing=self.netns_pid is None)
            steps.append(("the network uplink", self._uplink(True)))
        self._fail_on(steps)
        steps.append(("box setup", self._exec_raw(["/usr/bin/mkdir", "-p", BOX_WORKDIR, f"{BOX_HOME}/.local/bin"], 60,
                                                  as_root=True)))
        steps.append(("box setup", self._exec_raw(["/usr/bin/chown", "-R", f"{BOX_UID}:{BOX_UID}", BOX_HOME], 60,
                                                  as_root=True)))
        if self.display:  # root starts it as DISPLAY_UID: the box user can draw on it, not kill or replace it
            xvfb = self._exec_raw(["/usr/bin/bash", "-c", xvfb_script(tuple(self.seccomp()))], 60, as_root=True)
            steps.append(("the virtual display", xvfb))
            pid = next((line.split()[1] for line in xvfb.stdout.splitlines() if line.startswith("xvfb_pid ")), "")
            self.xvfb_pid = int(pid) if pid.isdigit() else None
        self._fail_on(steps, missing=bool(self.display and self.xvfb_pid is None))
        self.start_s = round(time.monotonic() - began, 2)

    def _fail_on(self, steps: list[tuple[str, ExecResult]], *, missing: bool = False) -> None:
        """Close the box and raise if a setup step failed (or, with `missing`, if the last one gave nothing)."""
        failed = next(((what, r) for what, r in steps if r.exit_code != 0), None)
        if failed or missing:
            self.close()
            what, r = failed or steps[-1]
            raise BoxError(f"{what} failed: {(r.stdout + r.stderr).strip()[-500:]}")

    def close(self) -> None:
        if not self.started:
            return
        try:
            self.sandbox.terminate()
        except Exception as err:  # already gone; the lifetime timeout reaps it anyway
            self.log(f"modal terminate: {type(err).__name__}: {err}")
        self.started = False

    def usd_per_second(self) -> float:
        gpu = GPU_USD_PER_S[self.gpu] if self.gpu else 0.0
        return self.limits.cpus / 2 * CORE_USD_PER_S + self.limits.memory_mb / 1024 * GIB_USD_PER_S + gpu

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def user_argv(self, command: str, timeout_s: int, cwd: str) -> list[str]:
        """argv that runs `command` as the box user with the limits (separate so tests can check it)."""
        lim = self.limits
        guard = (f"ulimit -u {lim.pids} -n {lim.nofile} -f {lim.home_mb * 1024} && cd {shlex.quote(cwd)} && "
                 f"exec /usr/bin/timeout -s KILL {timeout_s} /usr/bin/bash -c {shlex.quote(command)}")
        env = [f"{key}={value}" for key, value in BOX_ENV.items()]
        return [*self.enter(), *_drop_to(BOX_UID), *self.seccomp(), "/usr/bin/env", "-i", *env, "/usr/bin/bash", "-c",
                guard]

    def seccomp(self) -> list[str]:
        """The argv prefix that runs a command under the no-vsock, no-io_uring filter (a VM box; gVisor has
        neither vsock nor these host-kernel paths)."""
        return [PYTHON, "-I", "-S", NO_VSOCK] if self.runtime == "vm" else []

    def enter(self) -> list[str]:
        """The argv prefix that puts a command in the box user's network namespace, as NET_UID (root there) until
        the next setpriv (a gVisor box; a VM closes DNS with nftables). Fails closed before the namespace exists."""
        if self.runtime != "gvisor":
            return []
        if self.netns_pid is None:
            raise BoxError("the box user's network namespace is not set up")
        return [*_drop_to(NET_UID), "/usr/bin/nsenter", f"--target={self.netns_pid}", "--user", "--net", "--"]

    def _uplink(self, enabled: bool) -> ExecResult:
        assert self.netns_pid is not None
        return self._exec_raw(["/usr/bin/bash", "-c", uplink_script(self.netns_pid, enabled)], 30, as_root=True)

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        """Run argv for pickfit itself: as root, or as `as_uid` with an empty environment (no box-user PATH)."""
        self._require_started()
        if as_uid is not None:  # outside the box user's network namespace (the display uid is not mapped there)
            argv = [*_drop_to(as_uid), *self.seccomp(), "/usr/bin/env", "-i", f"PATH={HARNESS_PATH}",
                    f"HOME={EVIDENCE_DIR}", "LANG=C.UTF-8", *argv]
        return self._exec_raw(argv, timeout_s, stdin=stdin, as_root=True)

    def harness_read(self, path: str, max_bytes: int) -> bytes:
        """A file as root reads it (pickfit's evidence), up to max_bytes; BoxError if it cannot."""
        self._require_started()
        code, out, err, gave_up = self._run(["/usr/bin/head", "-c", str(int(max_bytes)), "--", path],
                                            READ_TIMEOUT_S, head=max_bytes, tail=0)
        if code != 0 or gave_up:
            raise BoxError(f"cannot read {path}: {err.text().strip()[-300:] or 'timed out'}")
        return bytes(out.head)

    def _run(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
             head: int = OUTPUT_HEAD_BYTES, tail: int = OUTPUT_TAIL_BYTES) -> tuple[int, _Capture, _Capture, bool]:
        """Run argv in the sandbox; (exit code, stdout, stderr, host gave up).

        The host waits at most timeout_s + HOST_GRACE_S. Measured 2026-10-29: a command whose
        child keeps stdout open (a daemon it started) never returned from proc.wait(), even
        after the in-box `timeout` killed it, so the wait runs in a thread with a deadline.
        """
        try:
            proc = self.sandbox.exec(*argv, timeout=timeout_s + HOST_GRACE_S, text=False)
            if stdin is not None:
                proc.stdin.write(stdin)
                proc.stdin.write_eof()
                proc.stdin.drain()
        except Exception as error:
            raise BoxError(self._exec_error(error)) from error
        out, err = _Capture(head, tail), _Capture(head, tail)
        codes: list[int] = []
        errors: list[Exception] = []

        def pump(stream: Any, capture: _Capture) -> None:
            try:
                for chunk in stream:
                    capture.feed(chunk if isinstance(chunk, bytes) else str(chunk).encode())
            except Exception:  # the stream died with the process or the box
                pass

        def wait() -> None:
            try:
                codes.append(proc.wait())
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=pump, args=(proc.stdout, out), daemon=True),
                   threading.Thread(target=pump, args=(proc.stderr, err), daemon=True)]
        waiter = threading.Thread(target=wait, daemon=True)
        for t in (*threads, waiter):
            t.start()
        waiter.join(timeout_s + HOST_GRACE_S)
        if errors:
            raise BoxError(self._exec_error(errors[0])) from errors[0]
        for t in threads:
            t.join(timeout=5 if codes else 0.5)
        if not codes:
            return 124, out, err, True
        return codes[0], out, err, False

    def _exec_raw(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
                  as_root: bool = False) -> ExecResult:
        """Run argv in the sandbox, keeping the head and tail of its output."""
        began = time.monotonic()
        code, out, err, gave_up = self._run(argv, timeout_s, stdin=stdin)
        seconds = round(time.monotonic() - began, 2)
        stderr = err.text()
        if gave_up:
            stderr += (f"\n[pickfit stopped waiting after {seconds:.0f}s: the command did not exit, or something "
                       "it started still holds its output open; start servers and daemons with run_background]")
        return ExecResult(command=" ".join(argv) if as_root else argv[-1], exit_code=code,
                          stdout=out.text(), stderr=stderr, seconds=seconds, timed_out=gave_up,
                          truncated=bool(out.dropped or err.dropped))

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        result = self._exec_raw(self.user_argv(command, timeout_s, cwd or self.workdir), timeout_s)
        # `timeout -s KILL` exits 137; Modal's own backstop reports -1 or 124-ish codes.
        timed_out = result.timed_out or (result.exit_code in (124, 137, -1) and result.seconds >= timeout_s - 0.5)
        return ExecResult(command=command, exit_code=result.exit_code, stdout=result.stdout,
                          stderr=result.stderr, seconds=result.seconds, timed_out=timed_out,
                          truncated=result.truncated)

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        # The path is passed as $1, never spliced into the script.
        script = '/usr/bin/mkdir -p -- "$(/usr/bin/dirname -- "$1")" && /usr/bin/cat > "$1"'
        argv = self.user_argv(f"/usr/bin/bash -c {shlex.quote(script)} sh {shlex.quote(path)}", 60, self.workdir)
        result = self._exec_raw(argv, 60, stdin=data)
        if result.exit_code != 0:
            raise BoxError(f"cannot write {path}: {result.stderr.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        argv = self.user_argv(f"/usr/bin/head -c {int(max_bytes)} -- {shlex.quote(path)}", READ_TIMEOUT_S,
                              self.workdir)
        code, out, err, gave_up = self._run(argv, READ_TIMEOUT_S, head=max_bytes, tail=0)
        if code != 0 or gave_up:
            raise BoxError(f"cannot read {path}: {err.text().strip()[-300:] or 'timed out'}")
        return bytes(out.head)

    def _exec_error(self, error: Exception) -> str:
        text = f"{type(error).__name__}: {error}"
        if "NotFound" in type(error).__name__ or "WaitPID" in text or "already shut down" in text:
            # Measured: going over the memory limit kills the whole gVisor sandbox, not one process.
            return (f"the sandbox died during this command (most likely over the {self.limits.memory_mb} MiB "
                    f"memory limit, which kills the whole box on Modal): {text[:300]}")
        return f"modal exec failed: {text[:400]}"

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        if not enabled and self.runtime == "gvisor":  # the box user's only way out, DNS included
            self._check_rule(self._uplink(False), "cutting the network uplink")
        try:
            self.sandbox._experimental_set_outbound_network_policy(
                outbound_cidr_allowlist=ONLINE_CIDRS if enabled else [], outbound_domain_allowlist=[])
        except Exception as err:
            raise BoxError(f"modal network policy failed: {type(err).__name__}: {err}") from err
        self.network_enabled = enabled
        if self.runtime == "vm":  # Modal's resolver answers even with an empty allowlist; root closes it
            rule = self._exec_raw(["/usr/bin/bash", "-c", DNS_UNBLOCK if enabled else DNS_BLOCK], 30, as_root=True)
            self._check_rule(rule, "offline DNS rule")
        elif enabled:
            self._check_rule(self._uplink(True), "the network uplink")

    @staticmethod
    def _check_rule(result: ExecResult, what: str) -> None:
        if result.exit_code != 0:
            raise BoxError(f"{what} failed: {(result.stdout + result.stderr).strip()[-300:]}")
