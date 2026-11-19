"""The replay's box started while the agent works, on a lane whose boxes boot slowly (pickfit.verify.early_box,
docs/proposals/machines-cost.md M3): the agent passes, the agent does not, no room for it, its start fails. The
replay box is always a fresh one the agent never touched. Fake boxes and a mocked model only."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from test_verify_pipeline import SCRIPT, agent_turns, failed_turns, judge_answer, verify
from verify_fakes import FakeBox, FakeServer

from pickfit.verify import early_box, pipeline
from pickfit.verify.box import BoxError
from pickfit.verify.early_box import EarlyBox


class Lane:
    """A slow-booting lane's box factory: every box notes when it is made, started, reserved and closed."""

    def __init__(self, scripts: dict[str, dict[str, tuple[int, str, str]]] | None = None, *, room: bool = True,
                 fail_start: str | None = None) -> None:
        self.scripts = scripts or {}
        self.room, self.fail_start = room, fail_start
        self.events: list[tuple[str, str]] = []
        self.made: list[tuple[str, SlowBox]] = []
        self.agent_ran = threading.Event()
        self.lock = threading.Lock()

    def note(self, what: str, role: str) -> None:
        with self.lock:
            self.events.append((what, role))

    def __call__(self, run_id: str, role: str) -> SlowBox:
        box = SlowBox(self, role, dict(self.scripts.get(role, SCRIPT)))
        self.made.append((role, box))
        self.note("make", role)
        return box


class SlowBox(FakeBox):
    early_replay = True

    def __init__(self, lane: Lane, role: str, script: dict[str, tuple[int, str, str]]) -> None:
        super().__init__(script)
        self.lane, self.role = lane, role
        self.started = False
        self.agent_was_working = False  # the agent had run a command and its box was open when this one started

    def start(self) -> None:
        if self.role == "replay":  # booting while the agent works: wait until it has run something
            self.lane.agent_ran.wait(5)
            agent = next(box for role, box in self.lane.made if role == "agent")
            self.agent_was_working = self.lane.agent_ran.is_set() and not agent.closed
        self.lane.note("start", self.role)
        if self.fail_start_here():
            raise BoxError(f"{self.role} box did not boot")
        self.started = True

    def fail_start_here(self) -> bool:
        return self.lane.fail_start == self.role

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None):
        if self.role == "agent":
            self.lane.agent_ran.set()
        return super().exec(command, timeout_s, cwd=cwd)

    def close(self) -> None:
        self.lane.note("close", self.role)
        super().close()

    def reserve(self) -> bool:
        self.lane.note("reserve", self.role)
        return self.lane.room

    def unreserve(self) -> None:
        self.lane.note("unreserve", self.role)

    def usd_per_second(self) -> float:
        return 0.001


def boxes(lane: Lane, role: str) -> list[SlowBox]:
    return [box for r, box in lane.made if r == role]


def test_a_passed_agent_replays_in_the_fresh_box_that_booted_while_it_worked(tmp_path: Path):
    lane = Lane()
    outcome, lines = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), lane)
    assert outcome.passed and outcome.run.replayed
    [agent], [replay] = boxes(lane, "agent"), boxes(lane, "replay")
    assert replay is not agent and replay.agent_was_working  # made and started before the agent's box closed
    assert lane.events.index(("make", "replay")) < lane.events.index(("close", "agent"))
    assert lane.events.index(("start", "agent")) < lane.events.index(("reserve", "replay"))  # the agent's place first
    # A fresh box: none of the agent's commands ran in it, only the replay's.
    assert [c for c, _ in replay.ran] == ["uv tool install graphtty", "cat > graph.json <<'EOF'\n{\"nodes\": "
                                          "[\"a\", \"b\"], \"edges\": [[\"a\", \"b\"]]}\nEOF",
                                          "graphtty --version", "graphtty graph.json"]
    assert agent.closed and replay.closed
    assert "replay box starting while the agent works" in lines
    # It is billed from its start: before the agent finished.
    assert outcome.phases["replay_box_s"] >= outcome.phases["replay"]
    assert outcome.box_usd == pytest.approx(0.001 * (outcome.phases["agent_box_s"] + outcome.phases["replay_box_s"]))


def test_an_agent_that_did_not_pass_closes_the_early_box_unused_and_it_is_still_billed(tmp_path: Path):
    from test_verify_pipeline import BROKEN, INTACT

    lane = Lane({"agent": BROKEN, "confirm": INTACT})
    outcome, lines = verify(tmp_path, FakeServer(*failed_turns()), lane)
    assert not outcome.passed and not outcome.run.replayed
    [replay] = boxes(lane, "replay")
    assert replay.closed and replay.ran == []  # nothing ran in it
    assert ("unreserve", "replay") in lane.events
    # Closed before the confirm box was made: it holds no place the confirm needs.
    assert lane.events.index(("close", "replay")) < lane.events.index(("make", "confirm"))
    assert not (outcome.evidence_dir / "replay.json").exists()
    agent_and_confirm = 0.001 * (outcome.phases["agent_box_s"] + outcome.phases["confirm_box_s"])
    assert outcome.box_usd > agent_and_confirm  # the unused box's time is in it
    assert any("closed unused" in line for line in lines)


def test_with_no_room_for_another_machine_the_replay_box_is_made_after_the_agent(tmp_path: Path):
    lane = Lane(room=False)
    outcome, lines = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), lane)
    assert outcome.passed and outcome.run.replayed
    unused, used = boxes(lane, "replay")
    assert not unused.started and unused.ran == []  # asked for room, had none, never started
    assert used.ran and lane.events.index(("make", "replay"), lane.events.index(("close", "agent"))) > 0
    assert any("no room for another machine" in line for line in lines)


def test_an_early_box_that_does_not_boot_fails_the_replay_as_a_late_one_would(tmp_path: Path):
    lane = Lane(fail_start="replay")
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns()), lane)  # no judge: the replay never passed
    assert not outcome.run.replayed and outcome.run.level == "unverified"
    result = json.loads((outcome.evidence_dir / "replay.json").read_text())["result"]
    assert result["error"] == "box error: replay box did not boot"
    assert boxes(lane, "replay")[0].closed


def test_early_replay_is_only_for_slow_boxes_and_can_be_turned_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from pickfit.verify.ec2_machine import Ec2Box
    from pickfit.verify.ec2_windows import Ec2WindowsBox
    from pickfit.verify.modal_box import ModalBox
    from pickfit.verify.tart_box import TartBox

    assert Ec2WindowsBox.early_replay and not Ec2Box.early_replay and not ModalBox.early_replay
    assert not TartBox.early_replay and not FakeBox.early_replay
    monkeypatch.setenv(early_box.ENV, "0")
    lane = Lane()
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), lane)
    assert outcome.passed and ("reserve", "replay") not in lane.events
    assert lane.events.index(("make", "replay")) > lane.events.index(("close", "agent"))


def test_the_ec2_lane_limit_keeps_an_early_box_from_being_a_third_machine(monkeypatch: pytest.MonkeyPatch):
    from test_verify_ec2 import CONTROL, FakeEc2

    from pickfit.verify import ec2_machine as e
    from pickfit.verify.ec2_windows import Ec2WindowsBox

    def windows(run_id: str, role: str) -> Ec2WindowsBox:
        return Ec2WindowsBox(ec2=FakeEc2(), control=CONTROL, log=lambda line: None,
                             tags={"pickfit.run": run_id, "pickfit.role": role})

    agent = windows("r1", "agent")
    assert agent.reserve()  # the agent's box holds one of the two
    other = e.take_slot(e.region_name())  # another run's box holds the other
    assert other is not None
    lines: list[str] = []
    assert EarlyBox.begin(agent, windows, "r1", log=lines.append) is None
    assert "no room for another machine" in lines[-1]
    other.release()
    started: list[str] = []
    monkeypatch.setattr(Ec2WindowsBox, "start", lambda self: started.append(self.machine.tags["pickfit.role"]))
    early = EarlyBox.begin(agent, windows, "r1", log=lines.append)
    assert early is not None and early.wait() >= 0 and started == ["replay"]
    assert e.take_slot(e.region_name()) is None  # two machines' worth: the agent's and the early replay's
    early.box.unreserve()  # never really started here, so its place goes back this way
    agent.unreserve()
    assert e.take_slot(e.region_name()) is not None


def test_the_box_of_an_early_start_is_given_back_when_it_is_discarded():
    events: list[str] = []

    class Box(FakeBox):
        early_replay = True

        def start(self) -> None:
            events.append("start")

        def unreserve(self) -> None:
            events.append("unreserve")

        def usd_per_second(self) -> float:
            return 0.5

    agent = Box()
    early = EarlyBox.begin(agent, lambda run_id, role: Box(), "r1", log=lambda line: None)
    assert early is not None
    cost: Any = early.discard()
    assert events == ["start", "unreserve"] and early.box.closed and cost >= 0
    early.abandon()  # once closed, closed: nothing more
    assert events == ["start", "unreserve"]


# -- a run that ends some other way before the replay takes its box (review 11/19): the box is never left running


def closed_soon(box: FakeBox, seconds: float = 5.0) -> bool:
    """The box gets closed within `seconds` (an abandoned box still starting is closed from its start's thread)."""
    deadline = time.monotonic() + seconds
    while not box.closed and time.monotonic() < deadline:
        time.sleep(0.01)
    return box.closed


def test_an_agent_that_raises_leaves_no_early_box_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    lane = Lane()

    def broken(self: Any) -> Any:
        lane.agent_ran.set()  # the agent got as far as working (so the early box's start goes on)
        raise RuntimeError("the model API answered 529")

    monkeypatch.setattr(pipeline.VerifyAgent, "run", broken)
    with pytest.raises(RuntimeError, match="529"):  # the error still reaches the caller (watch's guard)
        verify(tmp_path, FakeServer(), lane)
    [agent], [replay] = boxes(lane, "agent"), boxes(lane, "replay")
    assert agent.closed and closed_soon(replay)
    assert replay.ran == [] and ("unreserve", "replay") in lane.events  # its place goes back


@pytest.mark.parametrize("where", ["plan_from", "read_screen_text"])
def test_something_that_raises_after_a_passed_agent_leaves_no_early_box_running(tmp_path: Path, where: str,
                                                                               monkeypatch: pytest.MonkeyPatch):
    lane = Lane()

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError(f"{where} broke")

    monkeypatch.setattr(pipeline, where, broken)  # before the replay box is taken, and between taking and starting
    with pytest.raises(ValueError, match=f"{where} broke"):
        verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), lane)
    [replay] = boxes(lane, "replay")
    assert closed_soon(replay) and replay.ran == [] and ("unreserve", "replay") in lane.events


def test_an_interrupt_does_not_wait_for_the_early_box_to_boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class Interrupted(BaseException):  # as KeyboardInterrupt is: not an Exception
        pass

    booting = threading.Event()
    lane = Lane()
    original = SlowBox.start

    def slow_start(self: SlowBox) -> None:
        if self.role == "replay":
            booting.wait(10)  # a Windows instance still booting
        original(self)

    def interrupted(self: Any) -> Any:
        lane.agent_ran.set()
        raise Interrupted()

    monkeypatch.setattr(SlowBox, "start", slow_start)
    monkeypatch.setattr(pipeline.VerifyAgent, "run", interrupted)
    began = time.monotonic()
    with pytest.raises(Interrupted):
        verify(tmp_path, FakeServer(), lane)
    assert time.monotonic() - began < 5  # the interrupt is not held up by the boot
    [replay] = boxes(lane, "replay")
    assert not replay.closed  # still starting: it cannot be closed yet
    booting.set()
    assert closed_soon(replay) and ("unreserve", "replay") in lane.events  # closed as soon as its start ended


def test_a_run_that_ends_normally_leaves_nothing_to_abandon(tmp_path: Path):
    lane = Lane()
    outcome, _ = verify(tmp_path, FakeServer(*agent_turns(), judge_answer("working")), lane)
    [replay] = boxes(lane, "replay")
    assert outcome.run.replayed and replay.closed
    assert lane.events.count(("close", "replay")) == 1 and ("unreserve", "replay") not in lane.events
