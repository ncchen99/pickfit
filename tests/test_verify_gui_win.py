"""gui_win: a Windows box's desktop. Launches, the window and process rules, the stop, the display's start and
its scripts, and the screen over VNC, against fakes of the box and of the server."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import pytest

from pickfit.verify import gui, gui_operate, gui_win
from pickfit.verify.box import ExecResult
from pickfit.verify.vnc import vnc_stored_password
from tests.test_verify_vnc import PASSWORD, FakeServer

SBX = "S-1-5-21-9-9-9-1000"
OTHER = "S-1-5-21-9-9-9-500"
DESK = re.compile(r"^& '" + re.escape(gui_win.DESK_EXE) + r"' (\w+)$")


class FakeDeskBox:
    """A Windows box with a display as gui_win sees it: the administrator's desk.exe and Stop-Process, the box
    user's commands, and a screen."""

    os = "windows"
    display = "vnc"
    home = r"C:\Users\sbx"

    def __init__(self) -> None:
        self.user_sid = SBX
        self.procs: dict[int, dict[str, Any]] = {}
        self.windows: list[dict[str, Any]] = []
        self.stubborn: set[int] = set()  # never stop
        self.respawn: dict[int, dict[str, Any]] = {}  # come back under a new pid once stopped
        self.on_start: list[tuple[dict[str, Any], dict[str, Any] | None]] = []  # what a launch starts
        self.admin_scripts: list[str] = []
        self.commands: list[str] = []
        self.clip: str | None = "copied"
        self.next_pid = 5000
        self.proc(100, r"C:\Windows\explorer.exe")
        self.window(100, "", "Shell_TrayWnd", 0, 752, 1280, 48)
        self.session = gui_win.session_procs(self)

    def proc(self, pid: int, exe: str, sid: str = SBX, start: str | None = None, ppid: int = 1) -> dict[str, Any]:
        self.procs[pid] = {"pid": pid, "exe": exe, "sid": sid, "start": start or str(pid * 10), "ppid": ppid}
        return self.procs[pid]

    def window(self, pid: int, title: str, cls: str, x: int, y: int, w: int, h: int, **kw: Any) -> None:
        self.windows.append({"hwnd": str(len(self.windows) + 1), "pid": pid, "title": title, "class": cls,
                             "cloaked": False, "iconic": False, "owned": False, "x": x, "y": y, "width": w,
                             "height": h, **kw})

    def _admin(self, script: str, timeout_s: int = 60) -> tuple[int, str, str]:
        self.admin_scripts.append(script)
        m = DESK.match(script)
        if m:
            op = m.group(1)
            data: dict[str, Any] = {"session": 1, "sid": "S-1-5-18"}
            live = [p for p in self.procs.values()]
            if op in ("look", "procs"):
                data["procs"] = live
            if op == "look":
                data["windows"] = [w for w in self.windows if w["pid"] in self.procs]
            if op == "clipboard":
                data["clipboard"] = self.clip
            return 0, json.dumps(data) + "\n", ""
        if script.startswith("Stop-Process"):
            for pid in (int(p) for p in script.rsplit("-Id ", 1)[1].split(",")):
                if pid in self.stubborn:
                    continue
                gone = self.procs.pop(pid, None)
                again = self.respawn.pop(pid, None)
                if gone and again:
                    self.next_pid += 1
                    self.proc(self.next_pid, again["exe"])
            return 0, "", ""
        return 0, "", ""

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self.commands.append(command)
        if "-EncodedCommand" in command:
            for proc, window in self.on_start:
                self.next_pid += 1
                self.proc(self.next_pid, proc["exe"], proc.get("sid", SBX))
                if window:
                    self.window(self.next_pid, **window)
            return ExecResult(command, 0, f"started {self.next_pid}\n", "", 0.1)
        if "Get-Content" in command:
            return ExecResult(command, 0, "the app's own output\n", "", 0.1)
        return ExecResult(command, 0, "", "", 0.1)

    def screen(self) -> Any:
        box = self

        class Screen:
            def screenshot(self) -> bytes:
                return b"\x89PNG fake screen"

            def clipboard(self) -> bytes | None:
                return gui_win.WinVncDisplay.clipboard(self)  # type: ignore[arg-type]

        screen = Screen()
        screen._box = box  # type: ignore[attr-defined]
        return screen


def app_window(**kw: Any) -> dict[str, Any]:
    return {"title": "My App", "cls": "MyAppWindow", "x": 40, "y": 30, "w": 900, "h": 600, **kw}


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui_win, "POLL_S", 0)
    monkeypatch.setattr(gui_win, "_sleep", lambda s: None)


def test_a_launch_counts_only_a_window_of_the_apps_own_process(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gui, "SETTLE_S", 0)
    box = FakeDeskBox()
    box.on_start = [({"exe": r"C:\Users\sbx\AppData\Local\Programs\MyApp\MyApp.exe"}, app_window()),
                    ({"exe": r"C:\Windows\System32\conhost.exe"}, app_window(title="console", cls="ConsoleWindowClass")),
                    ({"exe": r"C:\Users\sbx\Apps\helper.exe"}, app_window(title="tiny", w=40, h=20))]
    result, shown, png = gui_win.launch(box, r"& $env:LOCALAPPDATA\Programs\MyApp\MyApp.exe", 3, 10)
    assert result.exit_code == 0 and shown.tier == "window" and png == b"\x89PNG fake screen"
    assert [w.title for w in shown.windows] == ["My App"] and shown.windows[0].client == "MyApp.exe"
    assert sorted(w.title for w in shown.other_windows) == ["console", "tiny"]  # Windows' own; too small
    assert "Shell_TrayWnd" not in json.dumps([w.__dict__ for w in shown.other_windows])  # the taskbar is not listed
    assert result.stdout.startswith("gui tier: window (a window of the app's own process is shown)")
    assert "window 1: 900x600 at 40,30" in result.stdout and "My App" not in result.stdout  # titles are the app's
    assert "window 1 title: 'My App'" in result.stderr and "the app's own output" in result.stderr
    assert shown.display == gui_win.DISPLAY_NOTE and shown.to_dict()["display"] == gui_win.DISPLAY_NOTE
    # the app and its helpers were stopped after the screenshot; Explorer, the box user's session, stays
    assert set(box.procs) == {100}
    started = next(c for c in box.commands if "-EncodedCommand" in c)
    assert "-RedirectStandardOutput \"$HOME\\.pickfit-gui\\3.log\"" in started and "MyApp" not in started


def test_no_window_of_its_own_is_process_alive_or_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gui_win, "EARLY_EXIT_S", 0)
    box = FakeDeskBox()
    box.on_start = [({"exe": r"C:\Users\sbx\Apps\server.exe"}, None)]
    result, shown, _ = gui_win.launch(box, "server.exe", 4, 1)
    assert shown.tier == "process_alive" and result.exit_code == 1 and shown.processes == ["server.exe"]
    box = FakeDeskBox()  # Windows' own program, started by the box user: not the app
    box.on_start = [({"exe": r"C:\Windows\System32\notepad.exe"}, app_window(title="Untitled - Notepad"))]
    _, shown, _ = gui_win.launch(box, "notepad.exe", 5, 1)
    assert shown.tier == "none" and [w.title for w in shown.other_windows] == ["Untitled - Notepad"]
    box = FakeDeskBox()  # another user's process with a window
    box.on_start = [({"exe": r"C:\Users\sbx\Apps\app.exe", "sid": OTHER}, app_window())]
    _, shown, _ = gui_win.launch(box, "app.exe", 6, 1)
    assert shown.tier == "none"


def test_a_window_kept_out_of_screen_captures_is_said(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gui, "SETTLE_S", 0)
    box = FakeDeskBox()
    box.on_start = [({"exe": r"C:\Users\sbx\Apps\KeePassXC\KeePassXC.exe"}, app_window(affinity=17))]
    result, shown, _ = gui_win.launch(box, "KeePassXC.exe", 8, 5)
    assert shown.tier == "window" and "left out of every screen capture" in (shown.error or "")
    assert "note: the app asks Windows to keep its window out of screenshots" in result.stdout
    assert "launch it with that" in result.stdout


def test_a_window_that_is_cloaked_minimized_or_off_screen_does_not_count(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gui_win, "EARLY_EXIT_S", 0)
    for extra in ({"cloaked": True}, {"iconic": True}, {"x": -32000, "y": -32000}):
        box = FakeDeskBox()
        box.on_start = [({"exe": r"C:\Users\sbx\Apps\app.exe"}, app_window(**extra))]
        _, shown, _ = gui_win.launch(box, "app.exe", 7, 1)
        assert shown.tier == "process_alive", extra


def test_a_stop_leaves_the_session_and_windows_shell_and_names_what_survives():
    box = FakeDeskBox()
    box.proc(200, r"C:\Users\sbx\Apps\app.exe")
    box.proc(201, r"C:\Windows\System32\rundll32.exe")  # Windows' own, carrying who knows what: stopped
    box.proc(202, r"C:\Windows\System32\RuntimeBroker.exe")  # Windows' shell part, started by Windows: left
    box.proc(203, r"C:\Windows\SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe")
    box.proc(204, r"C:\Users\other\x.exe", sid=OTHER)  # not the box user's
    ok, line = gui_win.stop(box)
    assert ok and line == "PICKFIT_KILLED 1 found 2" and set(box.procs) == {100, 202, 203, 204}
    assert gui_win.stop_box_user(box).stdout.startswith("PICKFIT_KILLED")
    box.proc(300, r"C:\Users\sbx\Apps\daemon.exe")
    box.stubborn.add(300)
    ok, line = gui_win.stop(box)
    assert not ok and line == 'PICKFIT_KILL_FAILED ["C:\\\\Users\\\\sbx\\\\Apps\\\\daemon.exe"]'
    box.stubborn.clear()
    box.proc(100, r"C:\Windows\explorer.exe", start="999")  # Explorer restarted: a new process, still the shell
    assert gui_win.stop(box)[0] and 100 in box.procs


def test_pickfits_own_job_and_its_shell_are_neither_the_session_nor_the_app():
    box = FakeDeskBox()
    box.proc(400, r"C:\ProgramData\pickfit\job.exe")
    box.proc(401, r"C:\Program Files\PowerShell\7\pwsh.exe", ppid=400)  # the shell job.exe holds ready
    box.proc(402, r"C:\Windows\System32\sihost.exe")
    box.proc(403, r"C:\Program Files\PowerShell\7\pwsh.exe", ppid=401)  # what a command of the box user's started
    assert set(gui_win.session_procs(box)) == {"100", "402", "403"}
    assert "400" not in gui_win.procs(box) and "401" not in gui_win.procs(box)
    del box.procs[403]
    ok, line = gui_win.stop(box)
    assert ok and line == "PICKFIT_KILLED 0 found 0" and {400, 401} <= set(box.procs)  # left waiting, not stopped


def test_the_clipboard_is_read_by_the_session_helper():
    box = FakeDeskBox()
    assert box.screen().clipboard() == b"copied"
    box.clip = None
    assert box.screen().clipboard() is None
    assert gui_win.desk(box, "clipboard")["sid"] == "S-1-5-18"


def test_the_display_start_carries_only_the_stored_password():
    script = gui_win.display_start("Ab3dEf7h")
    assert "Ab3dEf7h" not in script and base64.b64encode(vnc_stored_password("Ab3dEf7h")).decode() in script
    assert script.index("$bad += \"$($a.IdentityReference.Value) may read") < script.index("Set-ItemProperty")
    assert "if (-not $bad) {" in script.split("Set-ItemProperty")[0]  # a box that fails a check gets no password
    assert "'127.0.0.1'" in script and "LoopbackOnly" in script and "UseControlAuthentication" in script
    assert "display-ok" in script and "'S-1-5-18'" in script
    assert len(gui_win.new_vnc_password()) == 8 and gui_win.new_vnc_password() != gui_win.new_vnc_password()


def test_the_display_image_scripts():
    made = gui_win.MAKE_DISPLAY
    assert gui_win.VDD_SHA256 in made and "SignPath Foundation" in made and "TrustedPublisher" in made
    assert f"--version {gui_win.VNC_VERSION}" in made and "SERVER_ADD_FIREWALL_EXCEPTION=0" in made
    for setting in ("'LoopbackOnly', 1", "'AcceptHttpConnections', 0", "'UseVncAuthentication', 1",
                    "'UseControlAuthentication', 1", "'QueryAcceptOnConnect', 0"):
        assert setting in made
    assert "RandomNumberGenerator" in made and "VALUE_OF_PASSWORD" not in made  # no password on a command line
    assert "Set-Service tvnserver -StartupType Manual" in made  # off until a box sets its own password
    assert f"icacls.exe '{gui_win.DESK_DIR}' /inheritance:r" in made and f"icacls.exe '{gui_win.VDD_DIR}' /inheritance:r" in made
    assert "'*S-1-5-32-545:(OI)(CI)RX'" in made  # users may read the display's settings, not change them
    desk = gui_win.DESK_SOURCE
    assert base64.b64encode(desk.encode()).decode() in made and "'WindowsApplication'" in made
    assert '"winlogon"' in desk and "0x08000000 | 0x01000000" in desk  # no window; out of sshd's job object
    assert (desk.index("ImpersonateLoggedOnUser(imp)") < desk.index("CreateProcessAsUser(dup")
            < desk.index("finally { RevertToSelf(); }"))
    assert "SeAssignPrimaryTokenPrivilege" in desk and gui_win.DESK_DIR in desk and gui_win.DESKIN_EXE in desk
    screen = gui_win.SCREEN
    assert "Only('Virtual Display', 1280, 800)" in screen and "primary=$((" in screen


def test_the_screen_over_vnc(monkeypatch: pytest.MonkeyPatch):
    srv = FakeServer(zrle=True)

    class Machine:
        def forward(self, port: int) -> int:
            assert port == gui_win.VNC_PORT
            return srv.port

        def cancel_forward(self, port: int, remote: int) -> None:
            self.cancelled = (port, remote)

    class Box:
        machine = Machine()
        vnc_password = PASSWORD

    screen = gui_win.WinVncDisplay(Box())  # type: ignore[arg-type]
    assert screen.size == (4, 2) and screen.os == "windows"
    assert screen.screenshot().startswith(b"\x89PNG") and srv.encodings[0] == 16  # ZRLE, one connection
    screen.key("alt+F4")
    screen.click(1, 1)
    for _ in range(200):
        if len(srv.events) >= 6:
            break
        __import__("time").sleep(0.01)
    assert ("key", 1, 0xFFE9) in srv.events and ("key", 1, 0xFFC1) in srv.events  # Alt_L and F4
    assert srv.connections == 1
    screen.close()
    assert Box.machine.cancelled == (srv.port, gui_win.VNC_PORT)
    srv.sock.close()


# -- the operating loop on Windows


def test_windows_paths_in_the_box_users_home():
    home = "C:/Users/sbx"
    assert gui_operate.home_path("~/pickfit-out/a.txt", home) == "C:/Users/sbx/pickfit-out/a.txt"
    assert gui_operate.home_path(r"C:\Users\sbx\pickfit-out\a.txt", home) == "C:/Users/sbx/pickfit-out/a.txt"
    assert gui_operate.home_path("c:\\Users\\sbx\\pickfit-in\\", home) == "C:/Users/sbx/pickfit-in/"
    assert gui_operate.home_path("notes/x.md", home) == "C:/Users/sbx/notes/x.md"
    for bad in (r"D:\data\x.txt", "~/../Administrator/x"):
        with pytest.raises(ValueError):
            gui_operate.home_path(bad, home)
    assert gui_operate.home_path("~/a", "/home/sbx") == "/home/sbx/a"  # Linux as before
    assert gui_operate.box_home(FakeDeskBox()) == "C:/Users/sbx"
    args = gui_operate.OperateArgs.model_validate({
        "feature": 1, "command": "app.exe", "goal": "type {nonce}, save C:\\Users\\sbx\\pickfit-out\\n.txt",
        "inputs": [{"path": "~/pickfit-in/a.txt", "text": "x"}],
        "check": {"kind": "file", "path": "~/pickfit-out/n.txt", "contains": ["{nonce}"]}})
    assert gui_operate.spec_problems(args, home=home) == []
    assert gui_operate.desk_module(FakeDeskBox()) is gui_win


def test_the_file_check_on_windows_is_the_administrators_and_knows_the_box_user_by_sid():
    ran: list[tuple[list[str], bytes]] = []

    class Box(FakeDeskBox):
        harness_python = r"C:\Program Files\Python312\python.exe"

        def harness_exec(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None) -> ExecResult:
            ran.append((argv, stdin or b""))
            nonce = re.search(r'"nonce": "(\w+)"', stdin.decode().replace('\\"', '"')).group(1)
            return ExecResult(" ".join(argv), 0, f"{nonce} " + json.dumps({"now": 1.0, "before": None}) + "\n", "", 0.1)

    report = gui_operate.file_probe(Box(), {"mode": "before", "target": "C:/Users/sbx/pickfit-out/n.txt"})
    assert report == {"now": 1.0, "before": None}
    argv, source = ran[0]
    assert argv[0] == r"C:\Program Files\Python312\python.exe" and argv[1:] == ["-I", "-S", "-"]
    text = source.decode()
    assert f'"uid": "{SBX}"' in text and '"home": "C:/Users/sbx"' in text
    assert 'if os.name == "nt":' in text and "0x00200000" in text and "GetSecurityInfo" in text


def test_the_operator_sees_a_windows_desktop():
    text = gui_operate.WIN_OPERATOR_INSTRUCTIONS
    assert "a Windows desktop" in text and "File name field" in text and "element, the number of a marked text" in text
    assert "no window manager" not in text and "GTK" not in text


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_windows_replay_is_recorded_on_a_connection_of_its_own(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import time as clock

    from pickfit.verify import record

    srv = FakeServer(zrle=True)

    class Screen:
        size = (4, 2)
        _port = srv.port
        _client = None

    class Box:
        os, display, vnc_password = "windows", "vnc", PASSWORD

        def screen(self) -> Screen:
            return Screen()

    monkeypatch.setenv("PICKFIT_RECORD", "replay")
    assert record.for_box(Box(), "11", tmp_path) is None  # the agent's own operations are not recorded by default
    rec = record.for_box(Box(), "replay-11-1", tmp_path)
    assert isinstance(rec, record.WinVncRecorder)
    rec.start()
    clock.sleep(1.2)
    got = rec.stop()
    assert got.error is None and got.path == str(tmp_path / "replay-11-1.mp4") and (got.width, got.height) == (4, 2)
    assert srv.connections == 1 and rec.captures >= 3 and 16 in srv.encodings  # one kept, compressed connection
    srv.sock.close()
