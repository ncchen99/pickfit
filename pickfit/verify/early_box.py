"""EarlyBox: a run's replay box, started while the agent works (docs/proposals/machines-cost.md, M3).

A Windows box on EC2 takes two minutes or more to start, a third of a run's time, and the replay used to wait for
the agent's box to close before its own started. For a box class that says it boots slowly (Box.early_replay), the
pipeline makes the replay's box as soon as the agent's has started and starts it in a thread:

- it is a box the factory made fresh for the replay, never the agent's and never touched by the agent; nothing
  about the replay changes but when its box started, and the fresh-box rule stands;
- when the agent passed, the replay takes it (wait(): the start's own error, if it had one, is raised there, as a
  start in the replay's place would raise it), and the replay's own `finally` closes it from then on;
- when the agent did not pass, it is closed (discard()); its time is billed and recorded all the same (the ledger's
  boxes table, and the run's box_usd);
- when the run ends any other way before the replay took it (the agent's model call raised, something after the
  agent did, an interrupt), `discarding` around verify_task closes it (abandon()): at once if its start is over,
  else as soon as the start ends, without making the error wait for a boot.

It starts only when the box's provider has room for it now (Box.reserve: EC2's lane limit, two machines in a
region). The agent's box holds its own place already, so an early box never makes a box that is running wait, and
two runs cannot hold each other's places; without room the replay's box is made after the agent, as before.
PICKFIT_EARLY_REPLAY=0 turns it off.
"""

from __future__ import annotations

import contextvars
import functools
import os
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pickfit.verify.box import Box

ENV = "PICKFIT_EARLY_REPLAY"
F = TypeVar("F", bound=Callable[..., Any])
# The early boxes begun in the current call of a `discarding` function (each thread has its own).
_BEGUN: contextvars.ContextVar[list[EarlyBox] | None] = contextvars.ContextVar("pickfit_early_boxes", default=None)


def wanted(agent_box: Box) -> bool:
    """Should this run start its replay box early: the box class boots slowly and it is not turned off."""
    off = os.environ.get(ENV, "").strip().lower() in ("0", "no", "off", "false")
    return bool(getattr(agent_box, "early_replay", False)) and not off


def discarding(func: F) -> F:
    """Around a function that begins early boxes (pipeline.verify_task): however it ends, a box it began and neither
    handed to the replay nor discarded is closed (EarlyBox.abandon), so it never runs on, holding a machine's place,
    after the run is gone."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = _BEGUN.set([])
        try:
            return func(*args, **kwargs)
        finally:
            begun = _BEGUN.get() or []
            _BEGUN.reset(token)
            for early in begun:
                early.abandon()

    return wrapper  # type: ignore[return-value]


class EarlyBox:
    """A fresh box starting in a thread, for the replay. See the module docstring."""

    def __init__(self, box: Box, *, log: Callable[[str], None] = print) -> None:
        self.box = box
        self.log = log
        self.began = time.monotonic()  # the box is billed from here
        self.start_s: float | None = None
        self.taken = False  # the replay has it, and closes it
        self._error: BaseException | None = None
        self._lock = threading.Lock()
        self._start_over = False
        self._abandoned = False
        self._closed = False
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
        begun = _BEGUN.get()
        if begun is not None:
            begun.append(early)
        log("replay box starting while the agent works")
        return early

    def _start(self) -> None:
        began = time.monotonic()
        try:
            self.box.start()
        except BaseException as err:  # raised again by wait(), as a start there would raise it
            self._error = err
        self.start_s = round(time.monotonic() - began, 1)
        with self._lock:
            self._start_over = True
            abandoned = self._abandoned
        if abandoned:  # the run ended while this box was starting: close it now that it can be
            self._close("the run ended before the replay")

    def _close(self, why: str) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self.box.close()
        except Exception as err:  # noqa: BLE001 - its provider's lifetime cap ends it anyway
            self.log(f"replay box close: {type(err).__name__}: {err}")
        try:
            self.box.unreserve()
        except Exception as err:  # noqa: BLE001 - a slot also goes back when its machine's lifetime is over
            self.log(f"replay box unreserve: {type(err).__name__}: {err}")
        self.log(f"replay box closed unused after {time.monotonic() - self.began:.0f}s ({why})")

    def wait(self) -> float:
        """Hand the box to the replay: wait for its start to end and return the seconds that took (0 when the box was
        up before the agent finished). Raises what the start raised. From here the replay closes the box."""
        self.taken = True
        began = time.monotonic()
        self._thread.join()
        if self._error is not None:
            raise self._error
        return round(time.monotonic() - began, 1)

    def discard(self) -> float:
        """Close the box unused (the agent did not pass); what its time cost by its rate."""
        self._thread.join()
        self._close("the agent did not pass")
        try:
            return self.box.usd_per_second() * (time.monotonic() - self.began)
        except Exception:  # noqa: BLE001 - a box with no price on file
            return 0.0

    def abandon(self) -> None:
        """The run ended before the replay took the box: close it, at once when its start is over, else from the start's
        thread as soon as the start ends. Never waits; nothing to do for a box the replay took."""
        if self.taken:
            return
        with self._lock:
            self._abandoned = True
            over = self._start_over
        if over:
            self._close("the run ended before the replay")
