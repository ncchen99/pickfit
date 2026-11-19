"""The macOS lane of `pickfit watch` (pickfit.lanes): one Mac host for a batch of parked jobs, kept while it is paid.

A Mac is rented for a day at least (Scaleway: 24 h), so Mac jobs park until a batch is due (lanes.MAC_POLICY:
10 waiting, or the oldest waiting 24 h), and then the lane gets a host:

1. A host pickfit already knows (~/.pickfit/mac-hosts) that passes `mac-host check` (tart, softnet setuid,
   auto-login, the source image) is used as it is, nothing rented. Its bases are built and the limits test run
   first when they are missing (mac_host.plan_steps and run_test, as `pickfit mac-host test` does).
2. Else, only with renting on (`--mac-rent`) and under the rental cap (`max_rentals` in `rental_window`), a Mac is
   rented through the provider, set up (tart, softnet, the image), given the root step, checked by booting a VM,
   and its bases and limits test pass before any job runs. The root step needs the Mac's sudo password. With
   `root_from_provider` (`--mac-root-from-provider`) the lane reads it from the provider for a Mac it rented itself
   and pipes it into the host's root-step script (mac_host.root_unattended); it is never logged, saved or shown.
   Without it the lane says which command to run and waits, and the host is used once a person has run it.

While the lane holds a host (`live`), a newly parked Mac job runs at once, `concurrency` at a time (2: Apple's
licence allows two macOS VMs on one Mac). `idle()`: a host the lane rented is deleted once nothing is parked or
running and its first 24 h are over (Scaleway bills every hour after that). A host someone added is never deleted.
Rentals are logged in ~/.pickfit/mac-hosts/rentals.jsonl, and their cost in the ledger's boxes table (mac_host).

The same configuration error twice in a row (no usable host with renting off, a host not set up, its bases or
limits test failing, a rental refused for a quota) is not retried every time watch retries the lane: `available()`
says the lane needs an operator, `status()` shows it under `needs_operator`, and it stays so until the host records
or the lane's settings change or `pickfit mac-host clear` is run (mac_host.operator_hold).
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pickfit.lanes import MAC_POLICY, Policy
from pickfit.verify import mac_host
from pickfit.verify.box import BoxError, BoxLimits
from pickfit.verify.mac_host import HostOps, HostRecord, macos_for, plan_steps, ready, run_test

RENTALS = "rentals.jsonl"
DEFAULT_PROVIDER = "scaleway"


def _when(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


class MacLane:
    name = "macos"
    os = "macos"
    display = True

    def __init__(self, *, model: str | None = None, limits: Any = None, policy: Policy = MAC_POLICY,
                 concurrency: int = 2, rent: bool = False, provider: str = DEFAULT_PROVIDER, zone: str | None = None,
                 macos: int = mac_host.DEFAULT_MACOS, root_from_provider: bool = False, max_rentals: int = 1,
                 rental_window: timedelta = timedelta(days=7), hosts_dir: Path | None = None,
                 runs_dir: Path = Path("runs"), key: Path | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 ops: Callable[..., Any] = HostOps, providers: Callable[..., Any] = mac_host.provider_for,
                 test: Callable[..., dict[str, Any]] = run_test, sleep: Callable[[float], None] = time.sleep,
                 verify_task: Callable[..., Any] | None = None, make_box: Callable[..., Any] | None = None) -> None:
        self.model, self.limits, self.policy, self.concurrency = model, limits, policy, concurrency
        self.rent, self.provider, self.zone, self.macos = rent, provider, zone, macos
        self.root_from_provider, self.max_rentals, self.rental_window = root_from_provider, max_rentals, rental_window
        self.hosts_dir = hosts_dir or mac_host.HOSTS_DIR
        self.runs_dir, self.key, self.clock = runs_dir, key, clock
        self._ops, self._providers, self._test, self._sleep = ops, providers, test, sleep
        self._verify_task, self._make_box = verify_task, make_box
        self.host: HostRecord | None = None
        self.waiting_for_root: str | None = None  # a rented host that needs a person's root step
        self._unusable: dict[str, str] = {}  # host -> why it was not used, in the last available()
        self._lock = threading.Lock()

    # -- the lane protocol

    def live(self) -> bool:
        return self.host is not None

    def available(self, log: Callable[[str], None]) -> str | None:
        """None when a host is ready. Otherwise why not; the same configuration error a second time in a row is
        reported as needing an operator and not tried again until something changes (mac_host.operator_hold)."""
        with self._lock:
            hold = mac_host.operator_hold(self.hosts_dir, self._context())
            if hold is not None:
                self.host = None
                return mac_host.hold_message(hold)
            why, key = self._find_host(log)
            if why is None:
                mac_host.clear_hold(self.hosts_dir)
                return None
            if key is None:  # it passes by itself (no answer, no stock, the rental cap): tried again as before
                return why
            hold = mac_host.note_failure(self.hosts_dir, key, why, context=self._context(), now=self.clock())
            return mac_host.hold_message(hold) if hold["count"] >= mac_host.OPERATOR_AFTER else why

    def _context(self) -> str:
        return mac_host.lane_context(self.hosts_dir, rent=self.rent, root_from_provider=self.root_from_provider,
                                     provider=self.provider, zone=self.zone, macos=self.macos)

    def _find_host(self, log: Callable[[str], None]) -> tuple[str | None, str | None]:
        """(why no host is ready, or None; the configuration error's key, or None for one that passes by itself)."""
        self._unusable = {}
        if self.host is not None and self._usable(self.host, log):
            return None, None
        self.host = None
        for rec in self._known():
            if self._usable(rec, log):
                self.host, self.waiting_for_root = rec, None
                log(f"using {rec.name} ({rec.target}, macOS {rec.macos})")
                return None, None
        kinds = sorted(set(self._unusable.values()))
        passing = kinds == ["unreachable"]  # only hosts that did not answer: they may next time
        if not self.rent:
            seen = "; ".join(f"{name}: {kind}" for name, kind in sorted(self._unusable.items()))
            why = "no Mac host is ready and renting is off (`pickfit watch --mac-rent`)" + (f" ({seen})" if seen else "")
            return why, None if passing else f"renting-off:{','.join(kinds)}"
        capped = self._rental_cap()
        if capped:
            return capped, None
        try:
            rec = self._rent_one(log)
        except BoxError as err:
            text = str(err)
            return f"renting a Mac failed: {text}", None if "stock" in text.lower() else \
                "rent-failed:" + re.sub(r"\d+", "#", text)[:200]
        if rec is None:  # already says a person must act, and the check that sees the root step done costs nothing
            return self.waiting_for_root, None
        if self._usable(rec, log):
            self.host = rec
            return None, None
        return (f"{rec.name} was rented and set up but did not pass its checks; see `pickfit mac-host check {rec.name}`",
                f"rented-unusable:{self._unusable.get(rec.name, '')}")

    def verify(self, task: Any, data_dir: Path, log: Callable[[str], None]) -> Any:
        rec = self.host
        if rec is None:
            raise BoxError("the macOS lane has no host")
        gui = task.extraction.kind.value == "desktop_app"
        make_box = (self._make_box or self.box_factory)(rec, gui)
        run = self._verify_task
        if run is None:
            from pickfit.verify.pipeline import verify_task as run
        limits = self.limits
        if limits is None:
            from pickfit.verify.agent import AgentLimits

            limits = AgentLimits()
        return run(task, make_box, model=self.model, limits=limits, log=log, write=True, data_dir=data_dir)

    def box_factory(self, rec: HostRecord, gui: bool) -> Callable[[str, str], Any]:
        from pickfit.verify.agent import AgentLimits
        from pickfit.verify.cli import LIFETIME_MARGIN_S
        from pickfit.verify.tart_box import GUI_COMMAND_S, TartBox

        lifetime = int((self.limits or AgentLimits()).max_seconds) + LIFETIME_MARGIN_S
        mac = macos_for(rec.macos)
        base = f"{mac.base}-gui" if gui else mac.base
        longer = {"max_command_s": GUI_COMMAND_S} if gui else {}
        return lambda run_id, role: TartBox(base=base, limits=BoxLimits(lifetime_s=lifetime, **longer), display=gui,
                                            host=rec.ssh_host(), tags={"pickfit.run": run_id, "pickfit.role": role})

    def idle(self, log: Callable[[str], None]) -> None:
        """Nothing parked or running: a host this lane rented goes once its paid first day is over."""
        with self._lock:
            for rec in [r for r in self._known(every=True) if r.extra.get("rented_by") == "watch"]:
                when = _when(rec.deletable_at)
                if when is None or self.clock() < when:
                    continue
                try:
                    self._providers(rec).delete(rec, log)
                except BoxError as err:
                    log(f"could not delete {rec.name}: {err}")
                    continue
                (self.hosts_dir / f"{rec.name}.json").unlink(missing_ok=True)
                log(f"deleted {rec.name} ({rec.server_id}): idle after its first {self._paid_hours(rec)} h")
                if self.host is not None and self.host.name == rec.name:
                    self.host = None

    def status(self) -> dict[str, Any]:
        hosts = []
        for rec in self._known(every=True):
            hosts.append({"name": rec.name, "provider": rec.provider, "target": rec.target, "macos": rec.macos,
                          "deletable_at": rec.deletable_at or None, "rented_by_watch": rec.extra.get("rented_by") == "watch"})
        hold = mac_host.operator_hold(self.hosts_dir, self._context())
        return {"policy": self.policy.describe(), "rent": self.rent, "root_from_provider": self.root_from_provider,
                "in_use": self.host.name if self.host else None, "hosts": hosts,
                "rentals_in_window": len(self._rentals()), "max_rentals": self.max_rentals,
                "waiting_for_root": self.waiting_for_root,
                "needs_operator": mac_host.hold_message(hold) if hold else None}

    # -- hosts

    def _known(self, *, every: bool = False) -> list[HostRecord]:
        out = []
        for path in sorted(self.hosts_dir.glob("*.json")):
            try:
                rec = HostRecord(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if every or rec.target:
                out.append(rec)
        return out

    def _usable(self, rec: HostRecord, log: Callable[[str], None]) -> bool:
        """Ready by `mac-host check`, and its bases built and its limits test passed (run now when missing)."""
        unusable = self._unusable  # why each host was not used, this round
        try:
            ops = self._ops(rec, log=log)
            checks = ops.checks()
        except (BoxError, OSError, ValueError) as err:
            log(f"{rec.name}: not reachable ({type(err).__name__}: {str(err)[:200]})")
            unusable[rec.name] = "unreachable"
            return False
        except Exception as err:  # noqa: BLE001 - an SSH timeout, a host that went away
            log(f"{rec.name}: not reachable ({type(err).__name__}: {str(err)[:200]})")
            unusable[rec.name] = "unreachable"
            return False
        if not ready(checks):
            failing = [c.name for c in checks if not c.ok and not c.name.startswith('base:')]
            log(f"{rec.name}: not ready ({', '.join(failing)})")
            unusable[rec.name] = f"not ready ({', '.join(failing)})"
            return False
        by = {c.name: c.ok for c in checks}
        mac = macos_for(rec.macos)
        has_base, has_gui = by.get(f"base:{mac.base}", False), by.get(f"base:{mac.base}-gui", False)
        if has_base and has_gui and rec.extra.get("limits_passed"):
            return True
        steps = plan_steps(rebuild=False, has_base=has_base, has_gui_base=has_gui, verify=None, record=None)
        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        log(f"{rec.name}: {', '.join(s.name for s in steps)} before the batch")
        report = self._test(rec, steps, self.runs_dir / "mac-host" / f"{rec.name}-{stamp}", log=log)
        if not report.get("passed"):
            failed = ", ".join(f"{s['step']}={s['exit']}" for s in report.get("steps", []))
            log(f"{rec.name}: its bases or limits test failed: {failed}")
            unusable[rec.name] = f"bases or limits test failed ({failed})"
            return False
        rec.extra["limits_passed"] = stamp
        rec.save(self.hosts_dir)
        return True

    def _rentals(self) -> list[dict[str, Any]]:
        path = self.hosts_dir / RENTALS
        since = self.clock() - self.rental_window
        out = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            when = _when(row.get("at", ""))
            if when and when >= since:
                out.append(row)
        return out

    def _rental_cap(self) -> str | None:
        rented = self._rentals()
        if len(rented) >= self.max_rentals:
            return (f"{len(rented)} Mac rental(s) in the last {self.rental_window.days} days, the cap is "
                    f"{self.max_rentals} (`--mac-max-rentals`)")
        return None

    def _paid_hours(self, rec: HostRecord) -> int:
        made, until = _when(rec.created_at), _when(rec.deletable_at)
        return round((until - made).total_seconds() / 3600) if made and until else 24

    def _rent_one(self, log: Callable[[str], None]) -> HostRecord | None:
        """Rent, set up and (when allowed) root a Mac. None while it waits for a person's root step."""
        if self.waiting_for_root:
            pending = [r for r in self._known(every=True) if r.extra.get("rented_by") == "watch"]
            if pending:  # rented earlier and still not rooted: renting again would pay twice
                return None
        key = mac_host._key(str(self.key) if self.key else None)
        name = f"watch-{self.clock().strftime('%Y%m%d-%H%M')}"
        kw = {"zone": self.zone} if self.provider == "scaleway" and self.zone else {}
        provider = self._providers(self.provider, **kw)
        rec = provider.create(name, self.macos, key.with_suffix(".pub").read_text(encoding="utf-8"), log)
        rec.key = str(key)
        rec.extra["rented_by"] = "watch"
        rec.save(self.hosts_dir)
        with (self.hosts_dir / RENTALS).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": self.clock().isoformat(timespec="seconds"), "name": rec.name,
                                 "provider": rec.provider, "server_id": rec.server_id,
                                 "server_type": rec.server_type, "deletable_at": rec.deletable_at}) + "\n")
        log(f"rented {rec.name}: {rec.target} ({rec.server_type}); deletable after {rec.deletable_at or '-'}")
        ops = self._ops(rec, log=log)
        ops.wait_ssh()
        ops.prepare()
        rec.save(self.hosts_dir)
        if ready(ops.checks()):
            return rec
        if not self.root_from_provider:
            self.waiting_for_root = (f"{rec.name} is rented and set up; it needs its root step once: "
                                     f"`pickfit mac-host root {rec.name}` (types the sudo password)")
            log(self.waiting_for_root)
            return None
        password = provider.root_password(rec)
        if not password:
            self.waiting_for_root = (f"{rec.provider} gave no password for {rec.name}; run "
                                     f"`pickfit mac-host root {rec.name}`")
            log(self.waiting_for_root)
            return None
        code = mac_host.root_unattended(rec, password)
        del password
        if code not in (0, 255):
            raise BoxError(f"the root step on {rec.name} exited {code}")
        log(f"{rec.name}: root step done, rebooting")
        self._sleep(30)
        ops = self._ops(rec, log=log)
        ops.wait_ssh()
        checks = ops.checks(boot=True)
        if not ready(checks):
            raise BoxError(f"{rec.name} is not ready after its root step: "
                           + ", ".join(f"{c.name} ({c.detail})" for c in checks if not c.ok))
        self.waiting_for_root = None
        return rec
