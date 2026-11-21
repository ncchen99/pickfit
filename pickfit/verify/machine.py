"""Machine: one fresh Linux machine from one provider, driven as root. The seam under LinuxBox and WebBox.

A provider (modal_box.ModalMachine; ec2_machine.Ec2Machine, on ssh_machine.SshMachine, which any cloud that
rents plain VMs can share) implements this class and nothing else. What turns a machine
into a sandbox, the box user and its limits, the namespaces, the offline cut, the evidence root keeps, is
LinuxBox (linux_box.py) and WebBox (web_box.py). Both are written against this interface only, so they are the
same code on every provider.

What a provider has to give:

1. A fresh machine for every start(), gone at close(), with a lifetime cap of the provider's own: a harness
   that dies must not leave a machine running.
2. Root commands (spawn, run) over a channel that is not the machine's own network, or that the egress rules
   never close. Commands still have to run while the network is off: the replay's smoke tests run offline.
3. `runtime`, which tells the box how to harden the machine. "gvisor": no netfilter and a root without
   CAP_NET_ADMIN, so LinuxBox gives the box user a network namespace of its own. "vm": a kernel of its own, so
   LinuxBox uses sysctl, seccomp and nftables.
4. set_egress(): outbound traffic limited to ONLINE_CIDRS (never cloud metadata, never private ranges) or to
   nothing, decided outside the machine, where root inside it cannot widen it.
5. The image: sandbox.Dockerfile plus what linux_box.image_recipe() lists for the kind of box.
6. usd_per_second(), for the ledger, and a row in the ledger's boxes table (meter.BoxMeter) opened once the machine
   exists and closed when it is destroyed.

A new provider takes real runs only after `pickfit verify --limits-test` passes on it.

One kind of machine is handed to the software under test whole: root_box.PrivilegedMachine adds to this class what
a full-privilege VM box needs (root_box.RootVmBox; EC2's is ec2_root.Ec2RootMachine). Its root is the box user's
too, so there set_egress, the missing identity and the machine's end are all the provider's to keep, from outside.

A Windows machine is not one of these: nothing of LinuxBox applies to it. win_machine.WinSshMachine is the same
seam for Windows (create, two logins over SSH, egress, destroy), under windows_box.WindowsBox.
"""

from __future__ import annotations

import ipaddress
import threading
from abc import ABC, abstractmethod
from typing import Any, Protocol

from pickfit.verify.box import HOST_GRACE_S, OUTPUT_HEAD_BYTES, OUTPUT_TAIL_BYTES, BoxError, _Capture

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


class Process(Protocol):
    """A command running in a machine. stdin has write(bytes), write_eof() and drain(); stdout and stderr yield
    chunks (bytes or str) until the command ends; wait() returns its exit code."""

    stdin: Any
    stdout: Any
    stderr: Any

    def wait(self) -> int: ...


class Machine(ABC):
    """A fresh Linux machine, as root. See the module docstring for what a provider must give."""

    provider: str = "machine"  # the first half of a run's `runner`, e.g. modal
    runtime: str = "vm"  # one of RUNTIMES
    image: str = ""  # the image the machine started from, as the provider names it
    machine_id: str | None = None  # the provider's id for the started machine
    gpu: str | None = None  # e.g. "T4" when the machine has an NVIDIA card
    grace_s: int = HOST_GRACE_S  # how long run() waits past a command's own timeout before it gives up
    # The ledger's row for the machine (meter.BoxMeter), which the provider opens and closes: the lane it is counted
    # in, and its purpose when its tags do not name a role (a web box sets both to "web").
    lane: str = "linux"
    purpose: str | None = None
    meter: Any = None

    @abstractmethod
    def start(self) -> None:
        """Create the machine with outbound traffic limited to ONLINE_CIDRS; BoxError if it cannot."""

    @abstractmethod
    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> Process:
        """Start argv as root; the provider stops it after `timeout_s`."""

    @abstractmethod
    def set_egress(self, enabled: bool) -> None:
        """Outbound traffic: ONLINE_CIDRS, or nothing. BoxError if the change was not made."""

    @abstractmethod
    def close(self) -> None:
        """Destroy the machine and everything in it. Safe to call twice, and never raises."""

    def usd_per_second(self) -> float:
        """What the machine costs per second it exists."""
        return 0.0

    def explain(self, error: Exception) -> str:
        """What a failed spawn or wait says in the BoxError (a provider knows what its errors mean)."""
        return f"{self.provider} exec failed: {type(error).__name__}: {error}"[:400]

    def run(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
            head: int = OUTPUT_HEAD_BYTES, tail: int = OUTPUT_TAIL_BYTES) -> tuple[int, _Capture, _Capture, bool]:
        """Run argv as root to its end; (exit code, stdout, stderr, host gave up).

        The host waits at most timeout_s + grace_s. Measured 2026-10-29 on Modal: a command whose child keeps
        stdout open (a daemon it started) never returned from proc.wait(), even after the in-box `timeout`
        killed it, so the wait runs in a thread with a deadline.
        """
        grace = self.grace_s
        try:
            proc = self.spawn(argv, timeout_s + grace)
            if stdin is not None:
                proc.stdin.write(stdin)
                proc.stdin.write_eof()
                proc.stdin.drain()
        except BoxError:
            raise
        except Exception as error:
            raise BoxError(self.explain(error)) from error
        try:
            code, out, err = collect(proc, timeout_s + grace, head, tail)
        except Exception as error:
            raise BoxError(self.explain(error)) from error
        if code is None:
            return 124, out, err, True
        return code, out, err, False


def collect(proc: Process, wait_s: float, head: int = OUTPUT_HEAD_BYTES,
            tail: int = OUTPUT_TAIL_BYTES) -> tuple[int | None, _Capture, _Capture]:
    """Read a started command to its end, waiting at most wait_s: (exit code or None when the wait ran out, stdout,
    stderr). The wait runs in a thread with a deadline, and the output is read while it runs. What wait() raises
    is raised here."""
    out, err = _Capture(head, tail), _Capture(head, tail)
    codes: list[int] = []
    errors: list[Exception] = []

    def pump(stream: Any, capture: _Capture) -> None:
        try:
            for chunk in stream:
                capture.feed(chunk if isinstance(chunk, bytes) else str(chunk).encode())
        except Exception:  # the stream died with the process or the machine
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
    waiter.join(wait_s)
    if errors:
        raise errors[0]
    for t in threads:
        t.join(timeout=5 if codes else 0.5)
    return (codes[0] if codes else None), out, err
