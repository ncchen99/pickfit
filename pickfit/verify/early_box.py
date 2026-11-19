"""EarlyBox: a run's replay box, started while the agent works (docs/proposals/machines-cost.md, M3).

A Windows box on EC2 takes two minutes or more to start, a third of a run's time, and the replay used to wait for
the agent's box to close before its own started. For a box class that says it boots slowly (Box.early_replay), the
pipeline makes the replay's box as soon as the agent's has started and starts it in a thread:

- it is a box the factory made fresh for the replay, never the agent's and never touched by the agent; nothing
  about the replay changes but when its box started, and the fresh-box rule stands;
- when the agent passed, the replay takes it (wait(): the start's own error, if it had one, is raised there, as a
  start in the replay's place would raise it);
- when the agent did not pass, it is closed (discard()); its time is billed and recorded all the same (the ledger's
  boxes table, and the run's box_usd).

It starts only when the box's provider has room for it now (Box.reserve: EC2's lane limit, two machines in a
region). The agent's box holds its own place already, so an early box never makes a box that is running wait, and
two runs cannot hold each other's places; without room the replay's box is made after the agent, as before.
PICKFIT_EARLY_REPLAY=0 turns it off.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

from pickfit.verify.box import Box

ENV = "PICKFIT_EARLY_REPLAY"


def wanted(agent_box: Box) -> bool:
    """Should this run start its replay box early: the box class boots slowly and it is not turned off."""
    off = os.environ.get(ENV, "").strip().lower() in ("0", "no", "off", "false")
    return bool(getattr(agent_box, "early_replay", False)) and not off


class EarlyBox:
    """A fresh box starting in a thread, for the replay. See the module docstring."""

    def __init__(self, box: Box, *, log: Callable[[str], None] = print) -> None:
        self.box = box
        self.log = log
        self.began = time.monotonic()  # the box is billed from here
        self.start_s: float | None = None
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._start, name="early-replay-box", daemon=True)

    @classmethod
    def begin(cls, agent_box: Box, make_box: Callable[[str, str], Box], run_id: str, *, role: str = "replay",
              log: Callable[[str], None] = print) -> EarlyBox | None:
        """Make and start the replay's box now, or None: not wanted for this box, or no room for it now."""
        if not wanted(agent_box):
            return None
        box = make_box(run_id, role)
        try:
            room = box.reserve()
        except Exception as err:  # noqa: BLE001 - the replay's box is made after the agent instead
            log(f"replay box not started early: {type(err).__name__}: {err}")
            return None
        if not room:
            log("replay box not started early: its provider has no room for another machine now")
            return None
        early = cls(box, log=log)
        try:
            early._thread.start()
        except RuntimeError as err:  # no thread to be had: nothing was started
            box.unreserve()
            log(f"replay box not started early: {err}")
            return None
        log("replay box starting while the agent works")
        return early

    def _start(self) -> None:
        began = time.monotonic()
        try:
            self.box.start()
        except BaseException as err:  # raised again by wait(), as a start there would raise it
            self._error = err
        self.start_s = round(time.monotonic() - began, 1)

    def wait(self) -> float:
        """Wait for the start to end; the seconds that took (0 when the box was up before the agent finished). Raises
        what the start raised."""
        began = time.monotonic()
        self._thread.join()
        if self._error is not None:
            raise self._error
        return round(time.monotonic() - began, 1)

    def discard(self) -> float:
        """Close the box unused (the agent did not pass); what its time cost by its rate."""
        self._thread.join()
        try:
            self.box.close()
        except Exception as err:  # noqa: BLE001 - its provider's lifetime cap ends it anyway
            self.log(f"replay box close: {type(err).__name__}: {err}")
        self.box.unreserve()
        seconds = time.monotonic() - self.began
        self.log(f"replay box closed unused after {seconds:.0f}s (the agent did not pass)")
        try:
            return self.box.usd_per_second() * seconds
        except Exception:  # noqa: BLE001 - a box with no price on file
            return 0.0
