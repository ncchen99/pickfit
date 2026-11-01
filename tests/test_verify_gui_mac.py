"""macOS GUI launches (gui_mac) on a scripted fake TartBox: who starts what, what counts, what is kept."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from pickfit.verify import gui, gui_mac
from pickfit.verify.box import ExecResult

PNG = b"\x89PNG fake frame"
SESSION = {"401": ["Sun Nov  1 08:00:00 2026", "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock"]}
WINDOW = {"id": "54", "title": "", "width": 640, "height": 680, "x": 192, "y": 30, "pid": 1532,
          "client": "CotEditor"}


class FakeScreen:
    size = (1280, 800)

    def __init__(self) -> None:
        self.shots = 0
        self.clicks: list[tuple[int, int]] = []
        self.keys: list[str] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def key(self, name: str) -> None:
        self.keys.append(name)

    def screenshot(self) -> bytes:
        self.shots += 1
        return PNG


class FakeMacBox:
    """Answers gui_mac's root commands by what they run; records them."""

    os, display = "macos", "vnc"

    def __init__(self, *, report: dict[str, Any] | None = None, stop_out: str = "PICKFIT_KILLED 1\n",
                 approve: list[dict[str, Any]] | None = None, started: str = "started\n",
                 reports: list[dict[str, Any]] | None = None) -> None:
        self.session = SESSION
        self.sparkle: list[dict[str, str]] = []
        self.reports = reports if reports is not None else ([report] if report is not None else [])
        self.stop_out = stop_out
        self.approve = approve or []
        self.started = started
        self.calls: list[tuple[list[str], Any]] = []
        self._screen = FakeScreen()

    def screen(self) -> FakeScreen:
        return self._screen

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        payload = json.loads(stdin) if stdin else None
        self.calls.append((argv, payload))
        out = ""
        if argv[-1] == "procs":
            out = json.dumps(SESSION)
        elif argv[-1] == "approve":
            out = json.dumps(self.approve)
        elif argv[-1] == "items":
            out = json.dumps(["11", "12"])
        elif argv[-1] == "sparkle":
            out = json.dumps(self.sparkle)
        elif argv[-1] == "watch":
            if self.reports:
                out = f"{gui.MARK}{payload['nonce']} {json.dumps(self.reports.pop(0))}\n"
        elif argv[-1] == "stop":
            out = self.stop_out
        elif "/bin/bash" in argv:
            out = self.started
        return ExecResult(command=" ".join(argv), exit_code=0, stdout=out, stderr="", seconds=1.0, timed_out=False)

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        return ExecResult(command=command, exit_code=0, stdout="exit_code 0\n", stderr="", seconds=0.1,
                          timed_out=False)


def _report(**kw: Any) -> dict[str, Any]:
    base = {"seconds_to_window": 1.2, "alive": 1, "processes": ["CotEditor"], "windows": [WINDOW],
            "other_windows": [], "shot_bytes": None, "shot_sha256": None, "problems": [], "screen": [1280, 800],
            "watched_s": 7.2}
    return {**base, **kw}


def test_helper_is_valid_python_with_pickfits_constants_filled_in():
    compile(gui_mac.HELPER, "gui", "exec")
    assert "@" not in gui_mac.HELPER.split("JXA")[0]  # every placeholder replaced
    assert 'BOX_UID = "1001"' in gui_mac.HELPER and "/Applications/" in gui_mac.HELPER


def test_the_app_starts_as_sbx_in_its_desktop_session_detached():
    argv = gui_mac.start_argv('open -a "CotEditor"', 3)
    assert argv[:3] == ["/bin/launchctl", "asuser", "1001"]
    assert argv[3:8] == ["/usr/bin/sudo", "-n", "-u", "sbx", "-H"]
    script = argv[-1]
    assert "open -a \"CotEditor\"" in script and "/Users/sbx/.pickfit-gui/3.log" in script
    assert "pickfit/detach /bin/bash -c" in script and script.endswith("& echo started")


def test_a_window_of_its_own_passes_with_pickfits_screenshot():
    box = FakeMacBox(report=_report(), approve=[{"bundle": "/Users/sbx/Applications/CotEditor.app",
                                                 "gatekeeper": "accepted", "source": "Notarized Developer ID",
                                                 "approved": True}])
    result, shown, png = gui_mac.launch(box, 'open -a "CotEditor"', 1, 20)
    assert result.exit_code == 0 and shown.tier == "window" and png == PNG
    assert shown.shot_bytes == len(PNG) and shown.shot_sha256 == hashlib.sha256(PNG).hexdigest()
    assert result.stdout.startswith("gui tier: window (a window of the app's own process is shown)")
    assert "window 1: 640x680 at 192,30 (pid 1532)" in result.stdout
    assert "first-launch prompt with Open for 1 app bundle(s)" in result.stdout
    assert "CotEditor" not in result.stdout  # the app's names are data, not pickfit's lines
    assert "window 1 owner: 'CotEditor'" in result.stderr and "CotEditor.app" in result.stderr
    names = [argv[-1] if argv[-1] in ("procs", "approve", "sparkle", "items", "watch", "stop") else "start"
             for argv, _ in box.calls]
    assert names == ["stop", "approve", "sparkle", "procs", "items", "start", "watch", "stop"]  # all before the start
    assert box.calls[0][1] == {"baseline": SESSION, "bundles_only": True}  # a running copy would take the launch
    watch_argv, cfg = box.calls[6]
    assert watch_argv[:3] == ["/bin/launchctl", "asuser", "1001"]  # the watcher sits in the desktop session
    assert cfg["before"] == SESSION and cfg["user"] == "sbx" and cfg["min_w"] == gui.MIN_WIDTH
    assert cfg["items_before"] == ["11", "12"] and not cfg.get("any_layer")
    assert box.calls[7][1] == {"baseline": SESSION, "bundles_only": False}  # then only the login session is left
    assert "already running" not in result.stdout
    assert box.screen().clicks == []  # a window of its own: pickfit clicks nothing
    assert shown.to_dict()["display"] == gui_mac.DISPLAY_NOTE and len(gui_mac.DISPLAY_NOTE) <= 120  # not Xvfb


def test_a_survivor_makes_the_launch_count_for_nothing():
    box = FakeMacBox(report=_report(), stop_out='PICKFIT_KILL_FAILED ["/bin/bash"]\n')
    result, shown, png = gui_mac.launch(box, 'open -a "CotEditor"', 1, 20)
    assert png is None and result.exit_code == 1 and "survived the stop" in (shown.error or "")


def test_no_report_or_a_failed_start_is_tier_none():
    result, shown, png = gui_mac.launch(FakeMacBox(report=None), "open -a X", 1, 20)
    assert shown.tier == "none" and png is None and result.exit_code == 1
    assert "no report" in (shown.error or "")
    result, shown, png = gui_mac.launch(FakeMacBox(report=_report(), started="sudo: refused\n"), "open -a X", 2, 20)
    assert shown.tier == "none" and "could not start" in (shown.error or "")


def test_a_hidpi_screen_scales_window_bounds_to_pixels():
    box = FakeMacBox(report=_report(screen=[640, 400]))
    _, shown, _ = gui_mac.launch(box, "open -a X", 1, 20)
    w = shown.windows[0]
    assert (w.x, w.y, w.width, w.height) == (384, 60, 1280, 1360)


def test_a_launch_needs_the_gui_box():
    box = FakeMacBox(report=_report())
    box.session = None
    with pytest.raises(ValueError, match="display=True"):
        gui_mac.launch(box, "open -a X", 1, 20)


def test_keep_running_leaves_the_app_up_for_an_operating_loop():
    box = FakeMacBox(report=_report())
    result, shown, png = gui_mac.launch(box, "open ~/Applications/X.app", 1, 20, keep_running=True)
    assert result.exit_code == 0 and png == PNG
    assert [cfg for argv, cfg in box.calls if argv[-1] == "stop"] == [{"baseline": SESSION, "bundles_only": True}]
    assert result.stdout.rstrip().endswith("left the app running, to operate it.")
    assert gui_mac.stop(box) == (True, "PICKFIT_KILLED 1")
    assert box.calls[-1][1] == {"baseline": SESSION, "bundles_only": False}


MENU = {"id": "80", "title": "", "width": 267, "height": 246, "x": 1007, "y": 31, "pid": 1796,
        "client": "Meeting Transcriber"}
ITEM = {"id": "13", "x": 1027, "y": 0, "width": 34, "height": 30}


def test_a_menu_bar_app_gets_one_click_on_its_new_item_and_its_own_menu_counts():
    box = FakeMacBox(reports=[_report(windows=[], new_items=[ITEM], seconds_to_window=None),
                              _report(windows=[MENU])])
    result, shown, png = gui_mac.launch(box, "open ~/Applications/MeetingTranscriber.app", 1, 30)
    assert box.screen().clicks == [(1044, 15)] and shown.tier == "window" and png == PNG
    assert result.exit_code == 0
    assert "pickfit clicked it at 1044,15" in result.stdout and "window 1: 267x246 at 1007,31" in result.stdout
    watches = [cfg for argv, cfg in box.calls if argv[-1] == "watch"]
    assert [w.get("any_layer", False) for w in watches] == [False, True]  # the menu is a layer-101 window


def test_a_click_that_opens_nothing_of_the_apps_stays_process_alive():
    box = FakeMacBox(reports=[_report(windows=[], new_items=[ITEM], seconds_to_window=None),
                              _report(windows=[], seconds_to_window=None)])
    result, shown, png = gui_mac.launch(box, "open ~/Applications/X.app", 1, 30)
    assert shown.tier == "process_alive" and png == PNG and result.exit_code == 1
    assert box.screen().keys == ["Escape"] and "opened no window of the app's own" in (shown.error or "")


def test_no_new_menu_bar_item_means_no_click():
    box = FakeMacBox(report=_report(windows=[], new_items=[], seconds_to_window=None))
    result, shown, png = gui_mac.launch(box, "open ~/Applications/X.app", 1, 30)
    assert shown.tier == "process_alive" and box.screen().clicks == []
    assert png == PNG and result.exit_code == 1  # a picture of the failure, which does not pass


def test_the_judge_reads_a_macos_launch_in_macos_terms_with_pickfits_menu_bar_note(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from PIL import Image

    from pickfit.verify import judge
    from pickfit.verify.replay import CheckResult, RanCommand

    shot = tmp_path / "replay-1.png"
    Image.new("RGB", (1280, 800)).save(shot)
    shown = gui_mac.MacGuiLaunch(tier="window", windows=[gui.GuiWindow(**MENU)])
    stdout = gui_mac.observation(shown, [], clicked=(1044, 15))
    run = RanCommand(1, "open ~/Applications/X.app", 0, 9.0, False, stdout, "", False, screenshot=str(shot),
                     gui=shown.to_dict())
    check = CheckResult(1, run.command, "gui", 0, "gui tier: window", passed=True, offline=True, run=run)
    seen: dict[str, Any] = {}

    def fake_call(kind: str, body: dict[str, Any], **kw: Any) -> Any:
        seen["body"] = body
        out = judge.GuiJudgeOutput(screen="main_ui", observed="the app's menu", error_text=None, evidence_regions=[])
        return SimpleNamespace(parsed=out, usage=None, cost_usd=0.0, model="m", reasoning_summary=None,
                               parse_error=None)

    monkeypatch.setattr(judge, "call_meta", fake_call)
    result = judge.judge_gui("X", check, tmp_path, model="dev", log=lambda s: None,
                             about="Local push-to-talk voice typing that types at the cursor.")
    assert result is not None and result.verdict == "working"
    assert ('<source kind="what the software is, from its README">\nLocal push-to-talk voice typing'
            in seen["body"]["input"][0]["content"][0]["text"])
    assert seen["body"]["instructions"] == judge.MAC_GUI_INSTRUCTIONS and "macOS" in judge.MAC_GUI_INSTRUCTIONS
    text = seen["body"]["input"][0]["content"][0]["text"]
    assert "pickfit's note: the app showed no window but a menu bar item: pickfit clicked it at 1044,15" in text
    linux = RanCommand(1, "x", 0, 1.0, False, "gui tier: window", "", False, screenshot=str(shot),
                       gui={"windows": [MENU], "display": gui.DISPLAY_NOTE})
    judge.judge_gui("X", CheckResult(1, "x", "gui", 0, "gui tier: window", True, True, run=linux), tmp_path,
                    model="dev", log=lambda s: None)
    assert seen["body"]["instructions"] == judge.GUI_INSTRUCTIONS
    assert "pickfit's note" not in seen["body"]["input"][0]["content"][0]["text"]


def test_a_macos_gui_box_allows_long_downloads_and_its_replay_follows():
    from types import SimpleNamespace

    from pickfit.verify.cli import box_factory
    from pickfit.verify.replay import COMMAND_TIMEOUT_S, Replayer
    from pickfit.verify.tart_box import GUI_COMMAND_S

    gui_box = box_factory("tart", 3000, display=True)("run", "agent")
    cli_box = box_factory("tart", 3000)("run", "agent")
    assert gui_box.limits.max_command_s == GUI_COMMAND_S == 1800 and cli_box.limits.max_command_s == 600
    assert Replayer(gui_box, log=lambda s: None).timeout == GUI_COMMAND_S
    assert Replayer(SimpleNamespace(limits=SimpleNamespace(max_command_s=600)), log=lambda s: None).timeout == \
        COMMAND_TIMEOUT_S


def test_a_copy_already_running_is_stopped_first_and_said():
    box = FakeMacBox(report=_report(), stop_out="PICKFIT_KILLED 1 found 2\n")
    result, shown, png = gui_mac.launch(box, "open ~/Applications/Transcriber.app", 1, 30)
    assert result.exit_code == 0
    assert "pickfit first stopped 2 app process(es) already running" in result.stdout


class FakeVncDisplay:
    os = "macos"
    width, height = 1280, 800

    def __init__(self) -> None:
        self.done: list[tuple[str, Any]] = []
        self.typed = ""

    def screenshot(self) -> bytes:
        return PNG

    def click(self, x: int, y: int, count: int = 1) -> None:
        self.done.append(("click", (x, y, count)))

    def type_text(self, text: str) -> None:
        self.done.append(("type", text))
        self.typed += text

    def key(self, name: str) -> None:
        self.done.append(("key", name))

    def clipboard(self) -> bytes | None:
        return self.typed.encode() if ("key", "cmd+c") in self.done else None


def test_an_operation_on_a_mac_uses_its_desktop_its_vnc_display_and_its_home(monkeypatch):
    from pickfit.verify import gui_operate

    display = FakeVncDisplay()
    calls: list[str] = []
    written: dict[str, bytes] = {}
    box = type("MacOpBox", (), {})()  # only what run_operation reads
    box.os, box.home, box.display = "macos", "/Users/sbx", "vnc"
    box.screen = lambda: display
    box.exec = lambda command, timeout_s, **kw: ExecResult(command, 0, "", "", 0.1, False)
    box.write_file = lambda path, content: written.__setitem__(path, content)
    opened = gui_mac.MacOpened(shown=gui_mac.MacGuiLaunch(tier="window", windows=[gui.GuiWindow(**WINDOW)]),
                               png=PNG, seconds=2.0, timed_out=False, approved=[])
    monkeypatch.setattr(gui_mac, "stop_box_user", lambda b: (calls.append("stop"), ExecResult(
        "stop", 0, "PICKFIT_KILLED 0 found 0", "", 0.0, False))[1])
    monkeypatch.setattr(gui_mac, "open_app", lambda b, *a, **k: (calls.append("open"), opened)[1])
    monkeypatch.setattr(gui_mac, "close_app", lambda b, o, tag: (calls.append("close"), (PNG, False))[1])
    monkeypatch.setattr(gui_operate, "file_probe", lambda b, params: {"now": 0.0, "before": None})
    args = gui_operate.OperateArgs(command="open ~/Applications/CotEditor.app", goal="type {nonce} and copy it",
                                   inputs=[{"path": "~/pickfit-in/a.txt", "text": "x {nonce}"}],
                                   check={"kind": "clipboard", "contains": ["{nonce}"]})
    actions = [{"kind": "type", "text": "{nonce}"}, {"kind": "key", "name": "cmd+a"}, {"kind": "key", "name": "cmd+c"}]
    result, op, png = gui_operate.run_operation(box, args, 1, actions=actions, log=lambda s: None,
                                                sleep=lambda s: None)
    assert calls == ["stop", "open", "close"] and png == PNG
    assert list(written) == ["/Users/sbx/pickfit-in/a.txt"]
    assert display.done[1:] == [("key", "cmd+a"), ("key", "cmd+c")] and display.done[0][1] == op.nonce
    assert op.passed and result.exit_code == 0 and "gui check: passed" in result.stdout


def test_the_operator_on_a_mac_keeps_command_apart_from_control():
    from pickfit.verify import gui_operate

    assert gui_operate.normalize_key("cmd+s", mac=True) == "cmd+s" and gui_operate.normalize_key("cmd+s") == "ctrl+s"
    assert gui_operate.normalize_key("Command+Shift+G", mac=True) == "cmd+shift+g"
    assert gui_operate.normalize_key("ctrl+a", mac=True) == "ctrl+a"
    assert gui_operate.normalize_key("option+Left", mac=True) == "alt+Left"
    assert gui_operate.normalize_key("hyper+x", mac=True) is None
    assert "cmd+shift+g" in gui_operate.MAC_OPERATOR_INSTRUCTIONS and "no window manager" not in \
        gui_operate.MAC_OPERATOR_INSTRUCTIONS
    assert gui_mac.VncDisplay.os == "macos"


def test_sparkles_update_prompt_is_answered_before_the_launch_and_said():
    box = FakeMacBox(report=_report())
    box.sparkle = [{"bundle": "/Users/sbx/Applications/Neon.app", "id": "com.example.neon"},
                   {"bundle": "/Users/sbx/Applications/Bad.app", "id": "bad id; rm -rf"}]
    result, shown, png = gui_mac.launch(box, "open ~/Applications/Neon.app", 1, 30)
    writes = [argv for argv, _ in box.calls if "defaults" in " ".join(argv)]
    assert writes == [["/bin/launchctl", "asuser", "1001", "/usr/bin/sudo", "-n", "-u", "sbx", "/usr/bin/defaults",
                       "write", "com.example.neon", "SUEnableAutomaticChecks", "-bool", "false"]]
    assert "with Don't Check for 1 app bundle(s) that use Sparkle" in result.stdout
