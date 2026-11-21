"""RootVmBox: a full-privilege VM as a Box (docs/proposals/privileges.md, P6). The one box whose user has root.

For software that no other box can install: an installer that needs root and systemd, one whose only path is
`docker run` or compose, one that loads a kernel module or opens TUN, FUSE or a raw socket. Every other box keeps
the software under test a plain user inside limits that root sets. Here the software gets the whole machine, so
nothing inside the machine can be a limit. What holds instead:

- One VM for one verification, destroyed afterwards. The agent's run and the replay each get a VM of their own,
  as with every box; no second tool ever runs on one, and nothing is carried from one to the next.
- The VM has no identity and holds no secret: no credentials of the cloud it runs in, no metadata service, no key
  of pickfit's but the public half of a login key made for this one machine.
- Its network is decided outside it, by the provider: what may leave (DNS, HTTP, HTTPS), that nothing private and
  no other machine is reachable, and the offline cut. Root inside cannot widen any of it.
- Its lifetime is decided outside it too. The poweroff timer every machine arms is only a convenience here (root
  can stop it); the provider's reaper ends a machine by the tags and age the provider holds.
- What is read inside the VM is evidence a root process could have forged: the command log, a file's content, a
  port that "answers" on loopback. So the box also looks from outside where it can (probe_port: the harness
  connects to the VM's own address and asks over HTTP), keeps both readings apart, and says so in evidence():
  `full_privilege` is true, `inside_evidence` says it is forgeable, and `outside` lists what the harness saw
  itself. A run made here is marked by its runner (`<provider>-rootvm`) wherever a run's runner is recorded.

Nothing here knows a provider. A provider implements PrivilegedMachine (EC2: ec2_root.Ec2RootMachine) and says in
`capabilities` what its machine gives; another cloud that rents VMs with a firewall outside them can do the same.

The record's machine cost has a cap (COST_CAP_USD, docs/proposals/aws.md A3). The box counts what the record's
other machines cost by the ledger's boxes table and its own time at its own rate; over the cap it closes itself
and raises BoxBudgetError, which ends the run as `budget_exceeded`. A box that could not even pay its first minute
does not start.

Takes real runs only after its own limits test passes on the provider (limits_root.py).
"""

from __future__ import annotations

import os
import shlex
import socket
import time
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.verify.box import (
    BOX_ENV,
    BOX_HOME,
    BOX_PATH,
    BOX_USER,
    BOX_WORKDIR,
    OUTPUT_HEAD_BYTES,
    OUTPUT_TAIL_BYTES,
    Box,
    BoxBudgetError,
    BoxCapabilities,
    BoxError,
    BoxLimits,
    ExecResult,
    _Capture,
)
from pickfit.verify.machine import Machine

# What a full-privilege VM gives. A provider whose machine gives less says so in its own `capabilities`.
FULL = BoxCapabilities(root=True, systemd=True, container_engine="docker", kernel_modules=True)
ROOT_PATH = f"{BOX_PATH}:/usr/local/sbin:/usr/sbin:/sbin"
RUNUSER = "/usr/sbin/runuser"
BOX_UID = 1000
READ_TIMEOUT_S = 20
# The record's machines may cost this much (agent, replay and any other box of the run together): about five hours
# of a 2-vCPU Linux instance. The environment may lower it, never raise it.
COST_CAP_USD = 0.50
COST_CAP_ENV = "PICKFIT_ROOT_VM_CAP_USD"
MIN_BILLED_S = 60  # a provider bills a machine for a minute at least
# An outside probe: how long the harness keeps trying the port (a firewall rule made a moment ago takes a moment),
# and how long one try may take.
PROBE_WAIT_S = 6.0
PROBE_TRY_S = 2.0
PROBE_HTTP_BYTES = 2048
# Root, at start: the box user can become root, systemd is PID 1 and up, the container engine answers the box
# user. One line each, so a machine that lacks one of them fails to start instead of failing a tool. A machine is
# handed over as soon as its sshd answers, while its boot is still going on (the container engine starts late in
# it), so the box waits here for systemd to say the boot is over, BOOT_END_WAIT_S at most.
BOOT_END_WAIT_S = 150
READY = (f"{RUNUSER} -u {BOX_USER} -- /usr/bin/sudo -n /usr/bin/id -u | /usr/bin/sed 's/^/sudo_uid /'; "
         "echo \"init $(/usr/bin/cat /proc/1/comm)\"; "
         f"echo \"systemd $(/usr/bin/timeout {BOOT_END_WAIT_S} /usr/bin/systemctl is-system-running --wait "
         "2>/dev/null)\"; "
         f"{RUNUSER} -u {BOX_USER} -- /usr/bin/docker info --format 'docker {{{{.ServerVersion}}}}' 2>&1 | "
         "/usr/bin/tail -n 1")
SYSTEMD_UP = ("running", "degraded")  # degraded: a unit of the image's failed; the manager itself is up
# Root: the disks that are not the system's (no mounted partition, not the root disk's parent), one per line.
SPARE_DISKS = ("root=$(/usr/bin/findmnt -n -o SOURCE /); parent=$(/usr/bin/lsblk -n -o PKNAME \"$root\" | "
               "/usr/bin/head -n 1); /usr/bin/lsblk -d -n -p -b -o NAME,SIZE,TYPE,MOUNTPOINTS | "
               "/usr/bin/awk -v parent=\"/dev/$parent\" '$3 == \"disk\" && $1 != parent && NF == 3 {print $1, $2}'")
# Root: the addresses a TCP port listens on, as the VM says (inside evidence; it explains an outside "closed").
LISTENERS = "/usr/bin/ss -H -l -t -n 'sport = :{port}' | /usr/bin/awk '{{print $4}}'"

_now = time.monotonic
_sleep = time.sleep


def cost_cap_usd() -> float:
    """COST_CAP_USD, or less when COST_CAP_ENV says so."""
    given = os.environ.get(COST_CAP_ENV, "").strip()
    try:
        return min(COST_CAP_USD, max(0.0, float(given))) if given else COST_CAP_USD
    except ValueError:
        return COST_CAP_USD


class PrivilegedMachine(Machine):
    """A fresh VM handed over whole. What a provider gives on top of Machine:

    1. `capabilities`: what the box user gets there (FULL, or less).
    2. No identity: the VM has no credentials of its cloud and cannot ask for any (no instance role, the metadata
       service off where root inside cannot turn it on). outside_view() says how the provider sees it.
    3. set_egress() decided wholly outside the VM. Online: DNS and TCP 80 and 443 to public addresses, nothing
       else (no SMTP), no private range, no other machine of the lane. Offline: nothing but the harness's own
       channel. `cut` says what the cut does to a connection that was already open: "stateless" ends it at once,
       "stateful" only refuses new ones (and the box must say so in its evidence).
    4. probe_ingress(): let the harness, and only the harness, connect to one port of the VM, for an outside probe.
    5. state(): the machine as the provider describes it now, so "gone" is the provider's word, not the VM's.
    6. spawn() runs as root on the VM itself: there is no container between root and the machine.
    7. An extra blank disk when asked for (extra_disk_gb), deleted with the machine.
    """

    capabilities: BoxCapabilities = FULL
    cut: str = "stateless"
    extra_disk_gb: int = 0
    address: str | None = None

    @abstractmethod
    def probe_ingress(self, port: int, enabled: bool) -> None:
        """Allow (or stop allowing) the harness's address in on that TCP port; BoxError if it was not done."""

    @abstractmethod
    def probed_ports(self) -> list[int]:
        """The ports the provider's firewall lets the harness in on now, beyond the harness's own channel."""

    @abstractmethod
    def state(self) -> str:
        """The machine as the provider describes it now: "running", "shutting-down", "terminated", "gone"..."""

    @abstractmethod
    def outside_view(self) -> dict[str, Any]:
        """What the provider says of the machine, read outside it: its identity (none), its metadata service
        (off) and the firewall it is behind."""


def _text(result: ExecResult) -> str:
    return " ".join(f"{result.stdout.strip()} {result.stderr.strip()}".split())[-400:]


class RootVmBox(Box):
    """A PrivilegedMachine driven as a Box: the box user has passwordless sudo, systemd runs, Docker answers."""

    kind = "Linux virtual machine"
    user_rule = ("You are user sbx with passwordless sudo on a throwaway VM: use sudo where the software's own "
                 "install instructions need root (apt-get, a systemd unit, docker, a kernel module), and cite "
                 "those commands as steps like any other.")
    detach = "/usr/bin/setsid /usr/bin/nohup"
    read_timeout_s = READ_TIMEOUT_S

    def __init__(self, machine: PrivilegedMachine, *, limits: BoxLimits = BoxLimits(), run_id: str | None = None,
                 cap_usd: float | None = None, log: Callable[[str], None] = print,
                 connect: Callable[..., Any] = socket.create_connection,
                 ledger: Callable[[], Any] | None = None) -> None:
        if not machine.capabilities.root:
            raise ValueError("a RootVmBox needs a machine whose box user has root; any other machine is a LinuxBox's")
        self.machine = machine
        self.limits = limits
        self.capabilities = machine.capabilities
        self.runner = f"{machine.provider}-rootvm"
        self.image = machine.image
        self.run_id = run_id
        self.cap_usd = cost_cap_usd() if cap_usd is None else cap_usd
        self.log = log
        self._connect = connect
        self._ledger = ledger
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.extra_disk: str | None = None  # the blank disk's device, when one was asked for
        self.facts: dict[str, Any] = {}  # what root read at start (inside evidence)
        self.view: dict[str, Any] = {}  # what the provider said at start (outside evidence)
        self.outside: list[dict[str, Any]] = []  # every outside probe
        self.ended: str | None = None  # the machine's state as the provider gave it after close()
        self.stopped_for: str | None = None  # why the box closed itself (the cost cap)
        self._began: float | None = None
        self._ended: float | None = None
        self._prior_usd = 0.0
        self._pending: dict[str, int] = {}  # a background script the box wrote -> the port it waits for

    # -- what the agent is told

    def describe(self) -> str:
        caps = self.capabilities
        engine = (f" {caps.container_engine.capitalize()} is installed and running (sbx is in its group; compose "
                  "and buildx included).") if caps.container_engine else " No container engine."
        init = " systemd is PID 1: units can be installed, enabled and started." if caps.systemd else ""
        modules = " Kernel modules load (modprobe); /dev/net/tun and /dev/fuse work." if caps.kernel_modules else ""
        disk = (f" A blank {self.machine.extra_disk_gb} GB disk at {self.extra_disk or 'a second device (see lsblk)'} "
                "is there to partition, format or wipe; never touch the system disk.") if self.machine.extra_disk_gb \
            else ""
        return (f"Box: a whole Debian 13 VM, {self.arch}, yours alone and destroyed after this run. User sbx "
                f"(uid {BOX_UID}) with passwordless sudo, HOME={self.home}, work dir {self.workdir}.{init}{engine}"
                f"{modules}{disk} PATH starts with ~/.local/bin. Installed: python3 with pip and venv, pipx, uv; node "
                "with npm (global prefix ~/.local); git, curl, unzip, xz, zstd. Network: on, but only DNS, HTTP "
                "(port 80) and HTTPS (port 443) leave the VM: no SSH or git:// remotes, no SMTP, nothing on a private "
                "address. No API keys, no accounts. No GUI.")

    # -- the cost cap

    def _others_usd(self) -> float:
        """What the record's other machines cost so far, by the ledger's boxes table: a closed row's estimate, an
        open row's rate up to now. 0 when the ledger cannot be read (the cap then counts this box alone)."""
        if not self.run_id:
            return 0.0
        try:
            from pickfit.ledger import box_cost, box_ledger, taipei_now

            total = 0.0
            for row in (self._ledger or box_ledger)().boxes(run_id=self.run_id):
                if row.get("provider_ref") and row.get("provider_ref") == self.machine.machine_id:
                    continue  # this box: counted by its own clock
                if row.get("ended_at") or row.get("est_usd") is not None:
                    total += row.get("est_usd") or 0.0
                    continue
                age = (taipei_now() - datetime.fromisoformat(row["started_at"])).total_seconds()
                total += box_cost(row.get("rate_usd_per_hour"), max(0.0, age), row.get("min_billed_s") or 0) or 0.0
            return total
        except Exception as error:  # a ledger that cannot be read never stops a box
            self.log(f"root box: the record's other machines are not counted ({type(error).__name__}: {error})"[:300])
            return 0.0

    def spent_usd(self) -> float:
        """The record's machine cost so far: its other machines (read when this box started) and this box's own
        time at its own rate, a minute at least once it exists."""
        if self._began is None:
            return self._prior_usd
        until = _now() if self._ended is None else self._ended  # a closed box costs nothing more
        return self._prior_usd + self.machine.usd_per_second() * max(until - self._began, MIN_BILLED_S)

    def _over(self, spent: float) -> BoxBudgetError:
        return BoxBudgetError(f"budget_exceeded: the record's machines cost US${spent:.4f}, at its "
                              f"US${self.cap_usd:.2f} cap (root_box.COST_CAP_USD)")

    def _charge(self) -> float:
        """Seconds of this box the cap still pays for. Over the cap, the box closes itself and BoxBudgetError ends
        the run."""
        spent = self.spent_usd()
        if spent >= self.cap_usd:
            self.stopped_for = "budget_exceeded"
            self.log(f"root box: closing {self.machine.machine_id}: US${spent:.4f} of US${self.cap_usd:.2f} spent")
            self.close()
            raise self._over(spent)
        rate = self.machine.usd_per_second()
        return (self.cap_usd - spent) / rate if rate > 0 else float("inf")

    # -- lifecycle

    def start(self) -> None:
        if self.started:
            return
        began = time.monotonic()
        self._prior_usd = self._others_usd()
        first_minute = self._prior_usd + self.machine.usd_per_second() * MIN_BILLED_S
        if first_minute > self.cap_usd:  # before anything is launched
            self.stopped_for = "budget_exceeded"
            raise self._over(first_minute)
        self.machine.start()
        self._began = _now()
        self.image = self.machine.image
        self.started = True
        try:
            self.view = self.machine.outside_view()
            ready = self._root(["/usr/bin/bash", "-c", READY], BOOT_END_WAIT_S + 60)
            lines = dict(line.split(" ", 1) for line in ready.stdout.splitlines() if " " in line)
            self.facts = {"sudo_uid": lines.get("sudo_uid"), "init": lines.get("init"),
                          "systemd": lines.get("systemd"), "docker": lines.get("docker")}
            caps = self.capabilities
            missing = [what for what, bad in (
                ("the box user's sudo", lines.get("sudo_uid") != "0"),
                ("systemd as PID 1", caps.systemd and (lines.get("init") != "systemd"
                                                      or lines.get("systemd") not in SYSTEMD_UP)),
                ("the container engine", bool(caps.container_engine) and not lines.get("docker"))) if bad]
            if missing:
                raise BoxError(f"the VM lacks {', '.join(missing)}: {_text(ready)}")
            made = self._root(["/usr/bin/install", "-d", "-o", BOX_USER, "-g", BOX_USER, BOX_WORKDIR,
                               f"{BOX_HOME}/.local/bin"], 30)
            if made.exit_code != 0:
                raise BoxError(f"box setup failed: {_text(made)}")
            if self.machine.extra_disk_gb:
                listed = self._root(["/usr/bin/bash", "-c", SPARE_DISKS], 30)
                spare = [line.split() for line in listed.stdout.splitlines() if line.strip()]
                if len(spare) != 1:  # none, or more than the one asked for: the box cannot say which is safe to wipe
                    raise BoxError(f"the extra disk is not there as one blank disk: {spare or 'no spare disk'}")
                self.extra_disk = spare[0][0]
        except BaseException:
            self.close()
            raise
        self.start_s = round(time.monotonic() - began, 2)

    def close(self) -> None:
        if not self.started:
            return
        self.started = False
        self._ended = _now()
        try:
            self.machine.close()
        except Exception as error:  # the provider's reaper ends it by its tags anyway
            self.log(f"{self.machine.provider} close: {type(error).__name__}: {error}")
        try:
            self.ended = self.machine.state()  # the provider's word that it is going or gone
        except Exception as error:
            self.ended = f"unknown ({type(error).__name__})"

    def usd_per_second(self) -> float:
        return self.machine.usd_per_second()

    def reserve(self) -> bool:
        reserve = getattr(self.machine, "reserve", None)
        return reserve(wait=False) if reserve is not None else True

    def unreserve(self) -> None:
        release = getattr(self.machine, "release_slot", None)
        if release is not None and not self.started:
            release()

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            if self.stopped_for == "budget_exceeded":  # the same error as the call that closed it
                raise self._over(self.spent_usd())
            raise BoxError("box is not started")

    def _run(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None, head: int = OUTPUT_HEAD_BYTES,
             tail: int = OUTPUT_TAIL_BYTES) -> tuple[int, _Capture, _Capture, bool]:
        return self.machine.run(argv, timeout_s, stdin=stdin, head=head, tail=tail)

    def _exec_raw(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
                  shown: str | None = None) -> ExecResult:
        began = time.monotonic()
        code, out, err, gave_up = self._run(argv, timeout_s, stdin=stdin)
        seconds = round(time.monotonic() - began, 2)
        stderr = err.text()
        if gave_up:
            stderr += (f"\n[pickfit stopped waiting after {seconds:.0f}s: the command did not exit, or something "
                       "it started still holds its output open; start servers and daemons with run_background]")
        return ExecResult(command=shown if shown is not None else " ".join(argv), exit_code=code, stdout=out.text(),
                          stderr=stderr, seconds=seconds, timed_out=gave_up,
                          truncated=bool(out.dropped or err.dropped))

    def _root(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None) -> ExecResult:
        return self._exec_raw(argv, timeout_s, stdin=stdin)

    def user_argv(self, command: str, timeout_s: int, cwd: str) -> list[str]:
        """argv that runs `command` as the box user (separate so tests can check it): a login's groups (docker's
        among them), an environment of BOX_ENV and the user's own systemd, no limit but the timeout. No
        no_new_privs and no dropped capability: sudo must work."""
        guard = (f"cd {shlex.quote(cwd)} && exec /usr/bin/timeout -s KILL {timeout_s} /usr/bin/bash -c "
                 f"{shlex.quote(command)}")
        env = [f"{key}={value}" for key, value in {**BOX_ENV, "PATH": ROOT_PATH,
                                                   "XDG_RUNTIME_DIR": f"/run/user/{BOX_UID}"}.items()]
        return [RUNUSER, "-u", BOX_USER, "--", "/usr/bin/env", "-i", *env, "/usr/bin/bash", "-c", guard]

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        paid_s = self._charge()  # a command never runs past what the cap still pays for
        timeout_s = max(1, int(min(float(timeout_s), self.limits.max_command_s, paid_s)))
        result = self._exec_raw(self.user_argv(command, timeout_s, cwd or self.workdir), timeout_s, shown=command)
        timed_out = result.timed_out or (result.exit_code in (124, 137, -1) and result.seconds >= timeout_s - 0.5)
        result = ExecResult(command=command, exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr,
                            seconds=result.seconds, timed_out=timed_out, truncated=result.truncated)
        port = self._pending.pop(command, None)
        if port and result.ok:  # a server the box was asked to wait for: also look at it from outside
            self.probe_port(port)
        return result

    def background(self, command: str, port: int | None, wait_s: int, tag: int | str) -> str:
        script = super().background(command, port, wait_s, tag)
        if port:
            self._pending[script] = int(port)
        return script

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        script = '/usr/bin/mkdir -p -- "$(/usr/bin/dirname -- "$1")" && /usr/bin/cat > "$1"'  # the path is $1
        argv = self.user_argv(f"/usr/bin/bash -c {shlex.quote(script)} sh {shlex.quote(path)}", 60, self.workdir)
        result = self._exec_raw(argv, 60, stdin=data)
        if result.exit_code != 0:
            raise BoxError(f"cannot write {path}: {result.stderr.strip()[-300:]}")

    def _read(self, argv: list[str], path: str, max_bytes: int) -> bytes:
        code, out, err, gave_up = self._run(argv, self.read_timeout_s, head=max_bytes, tail=0)
        if code != 0 or gave_up:
            raise BoxError(f"cannot read {path}: {err.text().strip()[-300:] or 'timed out'}")
        return bytes(out.head)

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        command = f"/usr/bin/head -c {int(max_bytes)} -- {shlex.quote(path)}"
        return self._read(self.user_argv(command, self.read_timeout_s, self.workdir), path, max_bytes)

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        """Run argv as root on the VM, for pickfit itself. The box user can be root too, so what this returns is
        inside evidence: use it to set things up and to explain, not to prove."""
        self._require_started()
        if as_uid is not None:
            raise BoxError("a full-privilege VM has no uid of pickfit's own: the box user can be any of them")
        return self._root(argv, timeout_s, stdin=stdin)

    def harness_read(self, path: str, max_bytes: int) -> bytes:
        self._require_started()
        return self._read(["/usr/bin/head", "-c", str(int(max_bytes)), "--", path], path, max_bytes)

    def set_network(self, enabled: bool) -> None:
        """The provider opens or cuts the VM's network from outside; nothing is asked of the VM itself, whose root
        the software may hold."""
        self._require_started()
        if enabled == self.network_enabled:
            return
        self.machine.set_egress(enabled)  # BoxError if the provider did not make the change
        self.network_enabled = enabled

    # -- evidence from outside

    def probe_port(self, port: int, *, path: str | None = None, wait_s: float = PROBE_WAIT_S) -> dict[str, Any]:
        """Does the VM answer on that TCP port, seen from the harness: a connection to the VM's own address through
        the provider's firewall, opened for the harness's address and this port and closed again. With `path`, an
        HTTP GET's status line too. The reading is kept in `outside` and returned; it never raises.

        "closed" is not a failure of the software: a server that listens on loopback only cannot be seen from
        outside. `inside_listen` (root's own reading, forgeable) says which addresses it listens on."""
        seen: dict[str, Any] = {"kind": "port", "port": int(port), "path": path, "outside": "error", "status": None,
                                "online": self.network_enabled}
        began = _now()
        opened = False
        try:
            if not self.started or not self.machine.address:
                raise BoxError("box is not started")
            self.machine.probe_ingress(int(port), True)
            opened = True
            seen["outside"], seen["status"] = self._knock(self.machine.address, int(port), path, wait_s)
        except Exception as error:
            seen["error"] = f"{type(error).__name__}: {error}"[:200]
        finally:
            if opened:
                try:
                    self.machine.probe_ingress(int(port), False)
                except Exception as error:  # the provider's sweep removes a rule left behind
                    seen["rule_left"] = f"{type(error).__name__}: {error}"[:200]
        try:
            listen = self._root(["/usr/bin/bash", "-c", LISTENERS.format(port=int(port))], 15)
            seen["inside_listen"] = listen.stdout.split()[:8]
        except Exception:
            seen["inside_listen"] = None
        seen["seconds"] = round(_now() - began, 2)
        self.outside.append(seen)
        self.log(f"root box: outside probe of port {port}: {seen['outside']}"
                 + (f" (HTTP {seen['status']})" if seen["status"] else "")
                 + (f"; inside it listens on {' '.join(seen['inside_listen'])}" if seen.get("inside_listen") else ""))
        return seen

    def _knock(self, address: str, port: int, path: str | None, wait_s: float) -> tuple[str, int | None]:
        """("open" or "closed", the HTTP status when a path was asked for and the answer was HTTP)."""
        deadline = _now() + wait_s
        while True:
            try:
                with self._connect((address, port), timeout=PROBE_TRY_S) as conn:
                    if path is None:
                        return "open", None
                    conn.settimeout(PROBE_TRY_S)
                    conn.sendall(f"GET {path} HTTP/1.0\r\nHost: {address}\r\nConnection: close\r\n\r\n".encode())
                    head = b""
                    while b"\r\n" not in head and len(head) < PROBE_HTTP_BYTES:
                        chunk = conn.recv(PROBE_HTTP_BYTES)
                        if not chunk:
                            break
                        head += chunk
                    words = head.split(b"\r\n", 1)[0].split()
                    status = int(words[1]) if len(words) > 1 and words[0].startswith(b"HTTP/") and \
                        words[1].isdigit() else None
                    return "open", status
            except OSError:
                if _now() >= deadline:
                    return "closed", None
                _sleep(0.5)

    def evidence(self) -> dict[str, Any]:
        """What a run keeps about its box: that it was a full-privilege one, what the provider said of it, and what
        the harness saw from outside. Written next to the run's other evidence (save_box_evidence)."""
        return {"runner": self.runner, "full_privilege": True, "capabilities": self.capabilities.granted(),
                "container_engine": self.capabilities.container_engine,
                "machine": self.machine.machine_id, "image": self.image,
                "inside_evidence": "forgeable: the software under test could hold root in this VM, so command "
                                   "output, file contents and loopback probes read inside it prove less than in a "
                                   "box whose user is not root",
                "offline_cut": self.machine.cut, "provider_view": self.view, "inside_facts": self.facts,
                "extra_disk": self.extra_disk, "outside": self.outside, "ended": self.ended,
                "stopped_for": self.stopped_for,
                "cost": {"cap_usd": self.cap_usd, "spent_usd": round(self.spent_usd(), 6),
                         "other_machines_usd": round(self._prior_usd, 6)}}


def save_box_evidence(box: Any, evidence_dir: Path, role: str) -> Path | None:
    """Write a box's own evidence (a full-privilege box's: its mark, the provider's view, the outside probes) as
    box_<role>.json beside the run's; nothing for a box that has none. Never raises: it is evidence, not a result."""
    evidence = getattr(box, "evidence", None)
    if evidence is None:
        return None
    try:
        import json

        path = Path(evidence_dir) / f"box_{role}.json"
        path.write_text(json.dumps(evidence(), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        return path
    except Exception:
        return None
