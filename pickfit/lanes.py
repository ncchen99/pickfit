"""Where a submission is verified (its lane), and when a lane that needs machines starts.

- linux: verified as soon as its record is read, in a box made for the run (Modal, EC2 or docker). It is the
  first choice: CLI tools, MCP servers and most desktop apps run there, and a run costs cents.
- windows: an EC2 Windows box made for the run. A job waits (parks) only until the lane can start, which is as
  soon as AWS answers.
- macos: a Mac host (tart) that is rented for at least a day (Scaleway: 24 h). Jobs park until a batch is due,
  MIN_BATCH of them waiting or the oldest waiting MAX_WAIT; while a host is up, a newly parked job runs at once.
  pickfit.verify.mac_batch holds the host.
- web: a hosted web app (a website submission), visited once in a Modal microVM (pickfit.web_intake).

A record goes to the first of linux, windows, macos whose box can run it (batch.not_in_box). What none of them
can run is listed unverified, as before.

A parked job's D1 row stays `verifying`, with a reason that starts with PARKED_PREFIX (the submission page shows
it), so `requeue_stale` leaves it alone.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

BOX_LANES = ("linux", "windows", "macos")
ALL_LANES = (*BOX_LANES, "web")
PARKED_PREFIX = "Waiting for pickfit's "


@dataclass(frozen=True)
class Policy:
    """When a parked lane starts: `min_batch` jobs waiting, or the oldest waiting `max_wait`."""

    min_batch: int = 1
    max_wait: timedelta = timedelta(0)

    def due(self, parked_at: list[datetime], now: datetime) -> str | None:
        """Why a batch should start now, or None."""
        if not parked_at:
            return None
        if len(parked_at) >= self.min_batch:
            return f"{len(parked_at)} waiting (a batch is {self.min_batch})"
        waited = now - min(parked_at)
        if waited >= self.max_wait:
            return f"the oldest has waited {waited.total_seconds() / 3600:.1f} h (at most {self.hours:g} h)"
        return None

    @property
    def hours(self) -> float:
        return self.max_wait.total_seconds() / 3600

    def describe(self) -> str:
        if self.min_batch <= 1:
            return "at once"
        return f"when {self.min_batch} wait or the oldest has waited {self.hours:g} h"


AT_ONCE = Policy()
MAC_POLICY = Policy(min_batch=10, max_wait=timedelta(hours=24))


def parked_reason(lane: str, policy: Policy) -> str:
    """What the submission page says while a job waits in `lane` (written by pickfit, never by a model)."""
    if lane == "macos":
        if policy.min_batch <= 1:
            return f"{PARKED_PREFIX}macOS sandbox; it is verified as soon as a Mac is ready."
        return (f"{PARKED_PREFIX}next macOS batch: pickfit rents a Mac once {policy.min_batch} Mac apps are waiting "
                f"or the oldest has waited {policy.hours:g} hours.")
    if lane == "windows":
        return f"{PARKED_PREFIX}Windows sandbox; it is verified as soon as one is free."
    return f"{PARKED_PREFIX}{lane} sandbox."


class Lane(Protocol):
    """A lane whose jobs park: watch.Watcher starts it when its policy says so, or at once while it is live."""

    name: str
    os: str  # batch.not_in_box's os
    display: bool  # its boxes can have a desktop
    policy: Policy
    concurrency: int

    def live(self) -> bool: ...  # holds a machine now: parked jobs run without waiting for the policy

    def available(self, log: Callable[[str], None]) -> str | None: ...  # None: ready (may rent and set up first)

    def verify(self, task: Any, data_dir: Path, log: Callable[[str], None]) -> Any: ...  # pipeline.Outcome

    def idle(self, log: Callable[[str], None]) -> None: ...  # nothing parked or running: let go of machines

    def status(self) -> dict[str, Any]: ...


class BoxLane:
    """A lane of boxes made per run (EC2 Windows): starts at once, whenever its provider answers."""

    def __init__(self, name: str, os: str, make_box: Callable[[bool], Any], *,
                 check: Callable[[], str | None] | None = None, ensure: Callable[[bool], Any] | None = None,
                 policy: Policy = AT_ONCE, concurrency: int = 1, display: bool = True, model: str | None = None,
                 limits: Any = None) -> None:
        self.name, self.os, self.display, self.policy, self.concurrency = name, os, display, policy, concurrency
        self.make_box, self.check, self.ensure, self.model, self.limits = make_box, check, ensure, model, limits
        self._boxes: dict[bool, Any] = {}
        self._ensured: set[bool] = set()
        self._lock = threading.Lock()

    def live(self) -> bool:
        return False

    def available(self, log: Callable[[str], None]) -> str | None:
        return self.check() if self.check else None

    def verify(self, task: Any, data_dir: Path, log: Callable[[str], None]) -> Any:
        from pickfit.verify.agent import AgentLimits
        from pickfit.verify.pipeline import verify_task

        gui = self.display and task.extraction.kind.value == "desktop_app"
        with self._lock:  # bake or find the image once, not in every thread
            if self.ensure and gui not in self._ensured:
                self.ensure(gui)
                self._ensured.add(gui)
            if gui not in self._boxes:
                self._boxes[gui] = self.make_box(gui)
        return verify_task(task, self._boxes[gui], model=self.model, limits=self.limits or AgentLimits(), log=log,
                           write=True, data_dir=data_dir)

    def idle(self, log: Callable[[str], None]) -> None:
        return None

    def status(self) -> dict[str, Any]:
        return {"policy": self.policy.describe()}


def windows_lane(*, model: str | None, limits: Any = None) -> BoxLane:
    """EC2 Windows boxes (ec2_windows), one per run; the lane is up while AWS answers this machine's session."""
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, box_factory

    limits = limits or AgentLimits()
    lifetime = int(limits.max_seconds) + LIFETIME_MARGIN_S

    def check() -> str | None:
        try:
            import boto3

            from pickfit.verify.ec2_machine import region_name

            boto3.client("sts", region_name=region_name()).get_caller_identity()
        except Exception as err:  # noqa: BLE001 - expired login, no credentials, no network: the lane waits
            return f"AWS does not answer ({type(err).__name__}); the Windows lane waits until `aws login` is renewed"
        return None

    def ensure(gui: bool) -> Any:
        from pickfit.verify.ec2_windows import ensure_win_image

        return ensure_win_image(display=gui)

    return BoxLane("windows", "windows", lambda gui: box_factory("ec2-windows", lifetime, display=gui), check=check,
                   ensure=ensure, model=model, limits=limits)


ROOT_VM_LANE = "linux-root"
ROOT_VM_CONCURRENCY = 1  # one record at a time: its agent's VM and its replay's are the lane's two instances


def root_vm_lane(*, model: str | None, limits: Any = None) -> BoxLane:
    """Full-privilege VM boxes on EC2 (ec2_root), one per run, for records no other box can install: an installer
    that needs root and systemd, a `docker run` or compose install, a kernel module (docs/proposals/privileges.md
    P6, aws.md A3). One record at a time; the instances themselves share EC2's two machine slots with every other
    pickfit lane on this host, so a third instance never starts.

    Nothing routes a record here yet: pickfit.watch does not build this lane, and must not before its limits test
    (`pickfit verify --runner ec2 --runtime rootvm --limits-test`) has passed on a real instance. The name is not
    in BOX_LANES for the same reason."""
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, ROOT_VM, box_factory

    limits = limits or AgentLimits()
    lifetime = int(limits.max_seconds) + LIFETIME_MARGIN_S

    def check() -> str | None:
        try:
            import boto3

            from pickfit.verify.ec2_machine import region_name

            boto3.client("sts", region_name=region_name()).get_caller_identity()
        except Exception as err:  # noqa: BLE001 - expired login, no credentials, no network: the lane waits
            return (f"AWS does not answer ({type(err).__name__}); the full-privilege lane waits until `aws login` is "
                    "renewed")
        return None

    def ensure(gui: bool) -> Any:
        from pickfit.verify.ec2_root import ensure_root_image

        return ensure_root_image()

    return BoxLane(ROOT_VM_LANE, "linux", lambda gui: box_factory("ec2", lifetime, runtime=ROOT_VM), check=check,
                   ensure=ensure, concurrency=ROOT_VM_CONCURRENCY, display=False, model=model, limits=limits)


def due_lanes(parked: dict[str, list[datetime]], lanes: dict[str, Lane], now: datetime) -> dict[str, str]:
    """lane -> why it starts now (its policy is due, or it is live and has jobs)."""
    out: dict[str, str] = {}
    for name, when in parked.items():
        lane = lanes.get(name)
        if lane is None or not when:
            continue
        if lane.live():
            out[name] = "a machine is up"
            continue
        why = lane.policy.due(when, now)
        if why:
            out[name] = why
    return out
