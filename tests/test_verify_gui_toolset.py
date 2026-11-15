"""The computer use toolset's actions on pickfit's Xvfb (H-006): the display uid's hands run each one as the xdotool
sequence of computer-use-demo's executor, the operator's answers become checked actions, recordings old and new
replay, and a zoom stays on the host. No paid API: the hands run against a fake xdotool, the operator is a fake
server."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from pickfit.schema import meta_strict_schema
from pickfit.verify import gui
from pickfit.verify import gui_operate as op
from test_verify_gui import isolated  # noqa: F401
from test_verify_gui_operate import NonceServer, OperateBox, no_aim, operate_args, operator_reply  # noqa: F401

SCREEN = op.View(0, 0, 1280, 800)


def run_hands(tmp_path: Path, act: dict[str, Any], *, fail: bool = False) -> tuple[dict[str, Any] | None,
                                                                                  list[list[str]]]:
    """The display uid's hands for one action, run for real with a fake /usr/bin/xdotool that logs its argv (and
    exits 1 when `fail`); pickfit's X server check is the only part left out. (the report, every xdotool argv)."""
    log = tmp_path / f"xdotool-{os.urandom(4).hex()}.jsonl"
    fake = tmp_path / "xdotool"
    fake.write_text(f"#!{sys.executable}\nimport json, sys\n"
                    f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\nsys.exit({int(fail)})\n")
    fake.chmod(0o755)
    source = op.hands_source(act, xvfb_pid=os.getpid(), nonce="0123abcd")
    assert source.count("if not our_server():") == 2
    source = source.replace("/usr/bin/xdotool", str(fake)).replace("if not our_server():", "if False:")
    done = subprocess.run([sys.executable, "-I", "-S", "-"], input=source.encode(), capture_output=True, timeout=60)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return op.tagged(done.stdout.decode(), "0123abcd"), calls


def answer(action: str, **fields: Any) -> op.OperatorAction:
    base = {"observation": "", "x": None, "y": None, "clicks": None, "button": None, "text": None, "key": None,
            "direction": None, "seconds": None, "why": ""}
    return op.OperatorAction.model_validate({**base, "action": action, **fields})


def png(color: tuple[int, int, int] = (230, 230, 230), size: tuple[int, int] = (1280, 800)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


# ---------------------------------------------------------------- the hands: computer-use-demo's sequences


# computer-use-demo's ComputerToolset20260801 (computer.py at anthropics/claude-quickstarts 4a4224bd) runs, per member:
#   left_click / right_click / middle_click / double_click / triple_click:
#       xdotool mousemove --sync X Y [keydown TEXT] click {1 | 3 | 2 | --repeat 2 1 | --repeat 3 1} [keyup TEXT]
#   left_click_drag: xdotool [keydown TEXT] mousemove --sync SX SY mousedown 1 mousemove --sync EX EY mouseup 1 [keyup]
#   left_mouse_down / left_mouse_up: xdotool mousedown 1 / mouseup 1
#   mouse_move: xdotool mousemove --sync X Y
#   scroll: xdotool mousemove --sync X Y [keydown TEXT] click --repeat N {4 | 5 | 6 | 7} [keyup TEXT]
#   key: xdotool key -- K K ... (repeat)       hold_key: xdotool keydown K sleep D keyup K
#   type: xdotool type --delay 12 -- TEXT (in chunks of 50)
# pickfit keeps its own delays (90 ms between clicks, 60 ms between keys and wheel steps, 35 ms between typed
# characters, as before 11/16), and moves a drag in DRAG_STEPS steps.
CLICKS = [
    ({"kind": "click", "x": 10, "y": 20, "count": 1}, ["mousemove", "--sync", "10", "20", "click", "--repeat", "1",
                                                       "--delay", "90", "1"]),
    ({"kind": "click", "x": 10, "y": 20, "count": 1, "button": "right"},
     ["mousemove", "--sync", "10", "20", "click", "--repeat", "1", "--delay", "90", "3"]),
    ({"kind": "click", "x": 10, "y": 20, "count": 1, "button": "middle"},
     ["mousemove", "--sync", "10", "20", "click", "--repeat", "1", "--delay", "90", "2"]),
    ({"kind": "click", "x": 10, "y": 20, "count": 2}, ["mousemove", "--sync", "10", "20", "click", "--repeat", "2",
                                                       "--delay", "90", "1"]),
    ({"kind": "click", "x": 10, "y": 20, "count": 3}, ["mousemove", "--sync", "10", "20", "click", "--repeat", "3",
                                                       "--delay", "90", "1"]),
    ({"kind": "click", "x": 10, "y": 20, "count": 1, "hold": "ctrl+shift"},
     ["mousemove", "--sync", "10", "20", "keydown", "ctrl+shift", "click", "--repeat", "1", "--delay", "90", "1",
      "keyup", "ctrl+shift"]),
    ({"kind": "move", "x": 300, "y": 40}, ["mousemove", "--sync", "300", "40"]),
    ({"kind": "mouse_down"}, ["mousedown", "1"]),
    ({"kind": "mouse_up"}, ["mouseup", "1"]),
    ({"kind": "scroll", "x": 5, "y": 6, "direction": "left", "amount": 7},
     ["mousemove", "--sync", "5", "6", "click", "--repeat", "7", "--delay", "60", "6"]),
    ({"kind": "scroll", "x": 5, "y": 6, "direction": "right", "amount": 1, "hold": "shift"},
     ["mousemove", "--sync", "5", "6", "keydown", "shift", "click", "--repeat", "1", "--delay", "60", "7", "keyup",
      "shift"]),
    ({"kind": "key", "name": "Down", "repeat": 3}, ["key", "--delay", "60", "--", "Down", "Down", "Down"]),
    ({"kind": "key", "name": "ctrl+shift+z"}, ["key", "--delay", "60", "--", "ctrl+shift+z"]),
    ({"kind": "hold_key", "name": "space", "seconds": 2}, ["keydown", "space", "sleep", "2", "keyup", "space"]),
    ({"kind": "type", "text": "--help; rm -rf ~"}, ["type", "--delay", "35", "--", "--help; rm -rf ~"]),
]


@pytest.mark.parametrize(("act", "argv"), CLICKS, ids=[op.describe(a) for a, _ in CLICKS])
def test_each_action_runs_the_executors_xdotool_sequence_as_one_argv(tmp_path: Path, act: dict[str, Any],
                                                                     argv: list[str]):
    report, calls = run_hands(tmp_path, act)
    assert report is not None and report["ok"], report
    assert calls == [argv]  # one xdotool process, argv only: no shell ever sees the operator's text
    assert report["t0"] <= report["t1"]  # stamped in the box's clock, for the recording


def test_a_drag_presses_moves_in_steps_and_releases_at_its_end(tmp_path: Path):
    report, calls = run_hands(tmp_path, {"kind": "drag", "x": 100, "y": 200, "to_x": 400, "to_y": 260,
                                         "hold": "shift"})
    assert report["ok"] and len(calls) == 1
    argv = calls[0]
    assert argv[:7] == ["mousemove", "--sync", "100", "200", "keydown", "shift", "mousedown"]
    assert argv[-6:] == ["sleep", "0.15", "mouseup", "1", "keyup", "shift"]
    moves = [(int(argv[i + 2]), int(argv[i + 3])) for i, a in enumerate(argv) if a == "mousemove"]
    assert moves[0] == (100, 200) and moves[-1] == (400, 260) and len(moves) == op.DRAG_STEPS + 1
    xs = [x for x, _ in moves]
    assert xs == sorted(xs) and all(b - a <= 30 for a, b in zip(xs, xs[1:]))  # small steps, never back
    assert argv.index("mousedown") < argv.index("mousemove", 4) < argv.index("mouseup")


def test_old_recordings_run_as_they_did_before_the_toolset(tmp_path: Path):
    old = [({"kind": "scroll", "x": 1, "y": 2, "direction": "down"},
            ["mousemove", "--sync", "1", "2", "click", "--repeat", "3", "--delay", "60", "5"]),
           ({"kind": "scroll", "x": 1, "y": 2, "direction": "up"},
            ["mousemove", "--sync", "1", "2", "click", "--repeat", "3", "--delay", "60", "4"]),
           ({"kind": "key", "name": "ctrl+s"}, ["key", "--delay", "60", "--", "ctrl+s"]),
           ({"kind": "click", "x": 7, "y": 8, "count": 2}, ["mousemove", "--sync", "7", "8", "click", "--repeat", "2",
                                                            "--delay", "90", "1"]),
           ({"kind": "click", "x": 7, "y": 8, "count": 1, "button": "right"},
            ["mousemove", "--sync", "7", "8", "click", "--repeat", "1", "--delay", "90", "3"])]
    for act, argv in old:
        report, calls = run_hands(tmp_path, act)
        assert report["ok"] and calls == [argv], (act, calls)


def test_a_step_that_fails_half_way_leaves_nothing_pressed(tmp_path: Path):
    report, calls = run_hands(tmp_path, {"kind": "drag", "x": 1, "y": 1, "to_x": 90, "to_y": 1, "hold": "ctrl"},
                              fail=True)
    assert not report["ok"] and "xdotool exited 1" in report["error"]
    assert calls[1:] == [["keyup", "ctrl"], ["mouseup", "1"]]
    report, calls = run_hands(tmp_path, {"kind": "hold_key", "name": "Up", "seconds": 1}, fail=True)
    assert not report["ok"] and calls[1:] == [["keyup", "Up"]]
    report, calls = run_hands(tmp_path, {"kind": "click", "x": 1, "y": 1, "count": 1}, fail=True)
    assert not report["ok"] and len(calls) == 1  # nothing was held: nothing to release


def test_the_release_after_an_operation_lifts_the_left_button(tmp_path: Path):
    report, calls = run_hands(tmp_path, {"kind": "release"})
    assert report["ok"] and calls == [["mouseup", "1"]]


# ---------------------------------------------------------------- the operator's answers


def test_the_operators_toolset_answers_become_checked_actions_in_screen_pixels():
    to = lambda a: op.to_action(a, SCREEN)  # noqa: E731
    assert to(answer("click", x=500, y=250, clicks=3)) == ({"kind": "click", "x": 640, "y": 200, "count": 3}, None)
    assert to(answer("click", x=500, y=250, button="middle", clicks=2))[0] == \
        {"kind": "click", "x": 640, "y": 200, "count": 1, "button": "middle"}
    assert to(answer("click", x=500, y=250, hold="Shift"))[0] == \
        {"kind": "click", "x": 640, "y": 200, "count": 1, "hold": "shift"}
    assert to(answer("click", x=500, y=250, hold="Control+cmd")) == \
        (None, "hold takes modifier keys only (shift, ctrl, alt, super), not 'Control+cmd'")  # both are ctrl here
    assert to(answer("click", x=500, y=250, hold="a"))[0] is None
    assert to(answer("drag", x=100, y=500, x2=900, y2=500))[0] == \
        {"kind": "drag", "x": 128, "y": 400, "to_x": 1152, "to_y": 400}
    assert to(answer("drag", x=100, y=500, x2=900, y2=500, hold="alt"))[0]["hold"] == "alt"
    assert to(answer("drag", x=100, y=500)) == (None, "drag needs x2 and y2 between 0 and 1000")
    assert to(answer("drag", x=100, y=500, x2=101, y2=501))[0] is None  # a drag that goes nowhere is a click
    assert to(answer("move", x=500, y=500))[0] == {"kind": "move", "x": 640, "y": 400}
    assert to(answer("mouse_down"))[0] == {"kind": "mouse_down"} and to(answer("mouse_up"))[0] == {"kind": "mouse_up"}
    assert to(answer("scroll", x=500, y=500, direction="left", amount=40))[0] == \
        {"kind": "scroll", "x": 640, "y": 400, "direction": "left", "amount": op.SCROLL_MAX}
    assert to(answer("scroll", x=500, y=500, direction="down", amount=3))[0] == \
        {"kind": "scroll", "x": 640, "y": 400, "direction": "down"}  # the old shape: 3 steps is what it always did
    assert to(answer("scroll", x=500, y=500, direction="up", hold="ctrl"))[0]["hold"] == "ctrl"
    assert to(answer("key", key="down", repeat=99))[0] == {"kind": "key", "name": "Down", "repeat": op.KEY_REPEAT_MAX}
    assert to(answer("key", key="Return", repeat=1))[0] == {"kind": "key", "name": "Return"}
    assert to(answer("hold_key", key="space", seconds=30))[0] == {"kind": "hold_key", "name": "space",
                                                                 "seconds": op.WAIT_MAX_S}
    assert to(answer("hold_key", key="exec sh"))[0] is None  # keys only from pickfit's list, never xdotool commands
    assert to(answer("zoom", x=600, y=0, x2=500, y2=100))[0] == {"kind": "zoom", "region": [640, 0, 768, 80]}
    assert to(answer("zoom", x=500, y=500, x2=505, y2=505))[0] is None  # too small to show anything


def test_the_new_actions_read_in_the_log_and_the_circling_note():
    acts = [{"kind": "drag", "x": 10, "y": 10, "to_x": 400, "to_y": 10},
            {"kind": "click", "x": 1, "y": 2, "count": 3, "hold": "shift"},
            {"kind": "scroll", "x": 1, "y": 2, "direction": "right", "amount": 5},
            {"kind": "key", "name": "Down", "repeat": 4}, {"kind": "hold_key", "name": "Up", "seconds": 2},
            {"kind": "zoom", "region": [0, 0, 100, 50]}, {"kind": "move", "x": 3, "y": 4}, {"kind": "mouse_down"}]
    assert [op.describe(a) for a in acts] == [
        "drag from 10,10 to 400,10", "triple-click at 1,2 holding shift", "scroll right by 5 at 1,2", "key Down x4",
        "hold Up for 2s", "zoom into 0,0-100,50", "move the pointer to 3,4", "press the left button"]
    assert op.pointer(acts[0]) == (400, 10) and op.pointer(acts[6]) == (3, 4) and op.pointer(acts[7]) is None
    steps = [op.Step(None, "", True, a) for a in ({**acts[0], "to_x": 410}, acts[0], acts[5], acts[0])]
    assert op.circling(steps).startswith("You have done drag from 10,10 to 400,10 3 times")
    other = [op.Step(None, "", True, a) for a in (acts[0], {**acts[0], "to_x": 900}, acts[0])]
    assert op.circling(other) is None  # a drag to somewhere else is another action


def test_the_mac_keeps_its_own_schema_and_actions():
    mac = meta_strict_schema(op.MacOperatorAction)["properties"]
    assert list(mac) == ["observation", "action", "x", "y", "element", "target", "clicks", "button", "text", "key",
                         "direction", "seconds", "why"]
    assert "drag" not in json.dumps(mac) and "drag:" not in op.MAC_OPERATOR_INSTRUCTIONS
    linux = meta_strict_schema(op.OperatorAction)
    assert {"x2", "y2", "hold", "repeat", "amount"} <= set(linux["properties"])
    assert "- drag:" in op.OPERATOR_INSTRUCTIONS and "- zoom:" in op.OPERATOR_INSTRUCTIONS
    assert op.OPERATOR_INSTRUCTIONS.startswith(op.BASIC_INSTRUCTIONS[:200])
    # A Mac's operator has double clicks only, as before; a 3 is a single click there.
    triple = op.MacOperatorAction.model_validate({**json.loads(answer("click", x=1, y=1).model_dump_json()),
                                                  "clicks": 3, "element": None})
    assert op.to_action(triple, SCREEN, True)[0]["count"] == 1


# ---------------------------------------------------------------- performing on a display


class Basic:
    """A display with the basic methods only (as a Mac over VNC)."""

    width, height = 1280, 800

    def __init__(self) -> None:
        self.done: list[tuple] = []

    def click(self, x: int, y: int, count: int = 1) -> None:
        self.done.append(("click", x, y, count))

    def key(self, name: str) -> None:
        self.done.append(("key", name))


def test_a_display_without_the_toolset_refuses_what_it_cannot_do():
    display = Basic()
    op.perform(display, {"kind": "click", "x": 1, "y": 2, "count": 2})
    op.perform(display, {"kind": "key", "name": "Return"})
    op.perform(display, {"kind": "zoom", "region": [0, 0, 50, 50]})  # a view on the host: nothing to send
    assert display.done == [("click", 1, 2, 2), ("key", "Return")]
    for act in ({"kind": "drag", "x": 1, "y": 1, "to_x": 9, "to_y": 9}, {"kind": "move", "x": 1, "y": 1},
                {"kind": "click", "x": 1, "y": 1, "count": 1, "button": "middle"},
                {"kind": "click", "x": 1, "y": 1, "count": 1, "hold": "shift"},
                {"kind": "key", "name": "Down", "repeat": 2}, {"kind": "hold_key", "name": "Up", "seconds": 1}):
        with pytest.raises(op.DisplayError, match="this display cannot"):
            op.perform(display, act)


def test_pickfits_xvfb_performs_every_action_as_the_display_uid(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    display = op.XvfbDisplay(box, 1)
    assert set(op.TOOLSET_ACTIONS) <= set(display.actions)
    for act in ({"kind": "drag", "x": 1, "y": 2, "to_x": 30, "to_y": 40}, {"kind": "move", "x": 5, "y": 6},
                {"kind": "mouse_down"}, {"kind": "hold_key", "name": "Up", "seconds": 1}):
        display.perform(act)  # the fake box reports no clock (the hands do: test_each_action_runs...)
    assert box.acts == [{"kind": "drag", "x": 1, "y": 2, "to_x": 30, "to_y": 40}, {"kind": "move", "x": 5, "y": 6},
                        {"kind": "mouse_down"}, {"kind": "hold_key", "name": "Up", "seconds": 1}]
    assert all(as_uid == gui.DISPLAY_UID for _, as_uid, _ in box.harness)
    assert display.pressed  # a mouse_down with nothing after it
    display.release()
    assert box.acts[-1] == {"kind": "release"} and not display.pressed
    display.release()  # nothing held: nothing sent
    assert box.acts[-1] == {"kind": "release"} and len(box.acts) == 5
    with pytest.raises(op.DisplayError):
        display.perform({"kind": "shot", "path": "/tmp/x"})  # only input reaches the box this way


# ---------------------------------------------------------------- the loop: a drag, a zoom, the replay


def test_the_operator_drags_and_the_replay_reruns_the_drag(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    server = NonceServer(operator_reply("drag", x=100, y=500, x2=600, y2=500, why="move the card"),
                         operator_reply("click", x=500, y=400), operator_reply("type", text="NONCE"),
                         operator_reply("key", key="ctrl+s"), operator_reply("done"))
    result, operation, _ = op.run_operation(box, operate_args(), 3, log=lambda s: None, client=server.client(),
                                            sleep=lambda s: None)
    assert operation.passed and operation.stop == "done"
    drag = {"kind": "drag", "x": 128, "y": 400, "to_x": 768, "to_y": 400}
    assert operation.actions()[0] == drag and box.acts[0] == drag  # on the launch's own screenshot
    first = server.requests[0]
    assert "- drag:" in first["instructions"] and "x2" in first["text"]["format"]["schema"]["properties"]
    assert "A red ring marks where the pointer is after your last action." in json.dumps(server.requests[1])
    # The replay sends the recorded drag as it is, after a screenshot of the settled screen.
    _, again, _ = op.run_operation(box, operate_args(), "replay-3-1", actions=operation.actions(), log=lambda s: None,
                                   sleep=lambda s: None)
    assert again.passed and again.mode == "actions" and again.steps[0].action == drag


def test_a_zoom_is_shown_next_turn_and_never_reaches_the_box_or_the_recording(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    server = NonceServer(operator_reply("zoom", x=0, y=0, x2=250, y2=250), *[
        operator_reply("click", x=500, y=400), operator_reply("type", text="NONCE"),
        operator_reply("key", key="ctrl+s"), operator_reply("done")])
    _, operation, _ = op.run_operation(box, operate_args(), 3, log=lambda s: None, client=server.client(),
                                       sleep=lambda s: None)
    assert operation.passed and operation.steps[0].action == {"kind": "zoom", "region": [0, 0, 320, 200]}
    assert operation.steps[0].at is None and operation.steps[0].screenshot is None  # no evidence_dir here
    assert [a["kind"] for a in operation.actions()] == ["click", "type", "key"]  # nothing to rerun for a zoom
    assert not any(a["kind"] == "zoom" for a in box.acts)
    after = server.requests[1]["input"][0]["content"]
    assert [c["type"] for c in after] == ["input_text", "input_image", "input_image"]
    assert "magnified 4.0x" in after[0]["text"] and "give x and y over the first image" in after[0]["text"]
    assert len(server.requests[2]["input"][0]["content"]) == 2  # only the turn right after the zoom
    assert "did not change the screen" not in after[0]["text"]


def test_zoom_view_fits_the_region_to_the_screen_at_most_six_times(tmp_path: Path):
    image = Image.new("RGB", (1280, 800), (0, 0, 0))
    image.paste((255, 0, 0), (100, 100, 200, 150))
    out = io.BytesIO()
    image.save(out, "PNG")
    shown, scale = op.zoom_view(out.getvalue(), [100, 100, 200, 150])
    assert scale == op.ZOOM_MAX and Image.open(io.BytesIO(shown)).size == (600, 300)
    assert Image.open(io.BytesIO(shown)).getpixel((300, 150)) == (255, 0, 0)
    shown, scale = op.zoom_view(out.getvalue(), [0, 0, 640, 200])
    assert scale == 2.0 and Image.open(io.BytesIO(shown)).size == (1280, 400)  # the width fills the frame
    shown, scale = op.zoom_view(out.getvalue(), [1200, 700, 5000, 5000])
    assert Image.open(io.BytesIO(shown)).size == (480, 600)  # kept inside the screen


def test_an_operation_that_ends_with_the_button_down_releases_it_once_the_app_is_gone(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    actions = [{"kind": "click", "x": 640, "y": 320, "count": 1}, {"kind": "type", "text": "{nonce}"},
               {"kind": "key", "name": "ctrl+s"}, {"kind": "move", "x": 50, "y": 60}, {"kind": "mouse_down"}]
    _, operation, _ = op.run_operation(box, operate_args(), 4, actions=actions, log=lambda s: None,
                                       sleep=lambda s: None)
    assert operation.passed and box.acts[-1] == {"kind": "release"}
    kinds = [a["kind"] for a in box.acts]
    assert kinds.index("release") > kinds.index("mouse_down") and kinds.count("release") == 1
