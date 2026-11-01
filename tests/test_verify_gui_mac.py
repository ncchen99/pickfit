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

    def screenshot(self) -> bytes:
        self.shots += 1
        return PNG


class FakeMacBox:
    """Answers gui_mac's root commands by what they run; records them."""

    os, display = "macos", "vnc"

    def __init__(self, *, report: dict[str, Any] | None = None, stop_out: str = "PICKFIT_KILLED 1\n",
                 approve: list[dict[str, Any]] | None = None, started: str = "started\n") -> None:
        self.session = SESSION
        self.report = report
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
        elif argv[-1] == "watch":
            if self.report is not None:
                out = f"{gui.MARK}{payload['nonce']} {json.dumps(self.report)}\n"
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
    names = [argv[-1] if argv[-1] in ("procs", "approve", "watch", "stop") else "start" for argv, _ in box.calls]
    assert names == ["approve", "procs", "start", "watch", "stop"]  # approve, snapshot, start, watch, then stop
    watch_argv, cfg = box.calls[3]
    assert watch_argv[:3] == ["/bin/launchctl", "asuser", "1001"]  # the watcher sits in the desktop session
    assert cfg["before"] == SESSION and cfg["user"] == "sbx" and cfg["min_w"] == gui.MIN_WIDTH
    assert box.calls[4][1] == {"baseline": SESSION}  # the stop leaves only the login session


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
    assert "stop" not in [argv[-1] for argv, _ in box.calls]
    assert result.stdout.rstrip().endswith("left the app running, to operate it.")
    assert gui_mac.stop(box) == (True, "PICKFIT_KILLED 1")
    assert box.calls[-1][1] == {"baseline": SESSION}
