"""BoxMeter: the ledger's row for one machine pickfit pays for (docs/proposals/machines-cost.md, M1).

Each provider's class opens the row once the machine exists and closes it when the machine is destroyed:
modal_box.ModalMachine (Modal sandboxes, the web box's microVM too), ec2_machine.Ec2Instance (EC2 boxes on Linux and
Windows, AMI bakes, pool members warming up), tart_box.TartBox (macOS VMs) and mac_host's rentals (the Mac under them).
The rows are pickfit.ledger.BoxLedger's; the comment above it says what each column means and how a row nobody closed
is closed later.

Who a machine is for comes from the tags the box factories already give (cli.box_factory: `pickfit.run` and
`pickfit.role`; the web box: `run`), so no caller changes for it. The slug is the one a run id carries
(agent.new_run_id: `verify-<slug, 40 characters at most>-<time>-<hex>`).

Nothing here may stop a box: a ledger that cannot be written is logged once per meter and the box goes on.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping
from typing import Any

from pickfit.ledger import BoxLedger, box_ledger

RUN_ID = re.compile(r"^verify-(?P<slug>.+)-\d{8}-\d{6}-[0-9a-f]{4}$")
LANES = ("linux", "windows", "macos", "web")


def run_slug(run_id: str | None) -> str | None:
    """The slug a verification run id carries (as agent.new_run_id wrote it), or None."""
    found = RUN_ID.match(run_id or "")
    return found.group("slug") if found else None


def identity(tags: Mapping[str, str] | None) -> tuple[str | None, str | None]:
    """(run id, role) from a box's tags: the box factories' `pickfit.run` and `pickfit.role`, the web box's `run`."""
    tags = tags or {}
    run_id = tags.get("pickfit.run") or tags.get("run") or tags.get("pickfit:run_id")
    role = tags.get("pickfit.role") or tags.get("pickfit:purpose")
    return run_id or None, role or None


class BoxMeter:
    """One machine's row in the ledger's boxes table: start() when the provider has made it, end() when it is gone.

    Both are safe to call more than once; the first call counts."""

    def __init__(self, provider: str, *, lane: str, purpose: str, run_id: str | None = None,
                 slug: str | None = None, vcpu: float | None = None, memory_gb: float | None = None,
                 usd_per_hour: float | None = None, rate_source: str | None = None, lifetime_s: int | None = None,
                 min_billed_s: int = 0, host: str | None = None, box_id: str | None = None,
                 ledger: Callable[[], BoxLedger] | BoxLedger | None = None,
                 log: Callable[[str], None] = print) -> None:
        self.provider, self.lane, self.purpose = provider, lane, purpose
        self.run_id, self.slug = run_id, slug or run_slug(run_id)
        self.vcpu, self.memory_gb = vcpu, memory_gb
        self.usd_per_hour, self.rate_source = usd_per_hour, rate_source
        self.lifetime_s, self.min_billed_s, self.host = lifetime_s, min_billed_s, host
        self.box_id = box_id or f"{provider}-{secrets.token_hex(6)}"
        self._ledger = ledger
        self.log = log
        self.started = False
        self.ended = False
        self.est_usd: float | None = None
        self._warned = False

    def ledger(self) -> BoxLedger:
        if isinstance(self._ledger, BoxLedger):
            return self._ledger
        return (self._ledger or box_ledger)()

    def _warn(self, what: str, err: Exception) -> None:
        if not self._warned:  # once: a ledger that is not there stays not there for the rest of the box
            self._warned = True
            self.log(f"box ledger: could not {what} {self.box_id} ({type(err).__name__}: {str(err)[:200]})")

    def start(self, provider_ref: str | None = None, *, started_at: Any = None) -> None:
        """Write the row (and close rows a dead harness left open). Never raises."""
        if self.started:
            return
        self.started = True
        try:
            ledger = self.ledger()
            try:
                ledger.close_stale()
            except Exception as err:  # never the reason this row is not written
                self._warn("close stale rows before", err)
            ledger.open_box(box_id=self.box_id, provider=self.provider, started_at=started_at, lane=self.lane,
                            purpose=self.purpose, run_id=self.run_id, slug=self.slug, vcpu=self.vcpu,
                            memory_gb=self.memory_gb, rate_usd_per_hour=self.usd_per_hour,
                            rate_source=self.rate_source, lifetime_s=self.lifetime_s,
                            min_billed_s=self.min_billed_s, provider_ref=provider_ref, host=self.host)
        except Exception as err:
            self._warn("record the start of", err)

    def end(self, note: str = "closed", *, ended_at: Any = None) -> float | None:
        """Close the row with the machine's estimated cost; returns it (None without a rate). Never raises."""
        if not self.started or self.ended:
            return self.est_usd
        self.ended = True
        try:
            self.est_usd = self.ledger().close_box(self.box_id, ended_at=ended_at, note=note)
        except Exception as err:
            self._warn("record the end of", err)
        return self.est_usd
