"""GUI launch check: evidence made apart from the box user, launch_gui in the agent and the replay, the GUI
judge on a crop of the app's windows, the record, the limits probes and the hardened ModalBox."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import pickfit.env
from pickfit import meta
from pickfit.ledger import Caps, Ledger
from pickfit.schema import GuiCheck, SoftwareRecord, VerificationRun
from pickfit.verify import gui
from pickfit.verify import modal_box as mb
from pickfit.verify.box import ExecResult
from pickfit.verify.judge import JudgeResult, app_area, merge
from pickfit.verify.limits import run_limits_test
from pickfit.verify.pipeline import verify_task
from pickfit.verify.replay import ReplayCheck, ReplayCommand, Replayer, ReplayPlan
from pickfit.verify.result import install_guide
from pickfit.verify.task import load_fixture
from pickfit.verify.verdict import ResolvedCheck, check_kind, evaluate_check, supported_level
from verify_fakes import FakeBox, FakeServer, finish, response, run_cmd

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data" / "software"
LAUNCH = "./demo.AppImage --appimage-extract-and-run"
INSTALL = "curl -fsSL -o demo.AppImage https://example.com/demo.AppImage && chmod +x demo.AppImage"
DEMO_WINDOW = {"id": "0x200003", "title": "Demo App", "width": 1100, "height": 760, "x": 90, "y": 20, "pid": 42,
               "client": "demo"}


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


PNG = None


def png() -> bytes:
    global PNG
    if PNG is None:
        out = io.BytesIO()
        Image.new("RGB", (1280, 800), (240, 240, 230)).save(out, "PNG")
        PNG = out.getvalue()
    return PNG


def report(windows: list[dict[str, Any]] | None = None, alive: int = 2, problems: list[str] | None = None
           ) -> dict[str, Any]:
    return {"seconds_to_window": 1.1 if windows else None, "alive": alive, "processes": ["bash", "demo"],
            "windows": windows or [], "other_windows": [], "problems": problems or [], "watched_s": 7.2}


class GuiBox(FakeBox):
    """A FakeBox with pickfit's display: harness_exec plays the snapshot, the watcher and the stop."""

    display = ":99"
    xvfb_pid = 785

    def __init__(self, script: dict[str, tuple[int, str, str]] | None = None, shown: dict[str, Any] | None = None,
                 *, short_reads: int = 0, survivors: bool = False) -> None:
        super().__init__({"/usr/bin/tail -c 3000": (0, "app started\n", ""), **(script or {})})
        self.shown = report([DEMO_WINDOW]) if shown is None else shown
        self.short_reads, self.reads, self.survivors = short_reads, 0, survivors
        self.harness: list[tuple[list[str], int | None, str]] = []
        self.last_start = ""

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        if command.endswith("& echo started"):
            self.last_start = command
        return super().exec(command, timeout_s, cwd=cwd)

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        source = (stdin or b"").decode()
        self.harness.append((argv, as_uid, source))
        if "PICKFIT_KILLED" in source:
            out = "PICKFIT_KILL_FAILED ['77']\n" if self.survivors else "PICKFIT_KILLED 0\n"
            return ExecResult("stop", 1 if self.survivors else 0, out, "", 0.2)
        if "MARK = " in source:
            nonce, shot = re.search(r'\d+, "([0-9a-f]{24})", "([^"]+)"\n', source).groups()
            data = dict(self.shown)
            if "forged" in self.last_start:
                data = {**report(alive=1), "processes": ["bash", "sleep"]}
            if data["windows"]:
                self.files[shot] = png()
                data.update(shot_bytes=len(png()), shot_sha256=hashlib.sha256(png()).hexdigest())
            return ExecResult("watch", 0, f"{gui.MARK}{nonce} {json.dumps(data)}\n", "", 7.0)
        if source.endswith("print(json.dumps(procs()))\n"):
            return ExecResult("snapshot", 0, "{}\n", "", 0.1)
        if "AF_VSOCK" in " ".join(argv):  # root's unfiltered try: the host's port answers
            return ExecResult("vsock", 0, "OPEN 2 52\nclosed 2 1024 ConnectionResetError 104\n", "", 0.5)
        if argv[-1:] == ["/proc/sys/user/max_user_namespaces"]:
            return ExecResult("cat", 0, "0\n", "", 0.1)
        if argv[:1] == ["/usr/bin/ps"] and "Xvfb" in argv:  # root's view of the display server
            return ExecResult("ps", 0, " 1001 Xvfb\n", "", 0.1)
        if argv[:1] == ["/usr/bin/readlink"]:  # Xvfb's network namespace, then the box's own
            return ExecResult("readlink", 0, "net:[11]\nnet:[2]\n", "", 0.1)
        if source.startswith("import os, socket, sys") and as_uid:  # the X ports, from Xvfb's namespace
            return ExecResult("xports", 0, "ns net:[11] net:[11]\nclosed 127.0.0.1 6000 111\nclosed ::1 6000 111\n", "", 0.1)
        if source.startswith("import os, random, socket"):  # DNS: from the display's namespace, or root's control
            out = ("ns net:[11]\nno answer 172.21.0.1 OSError\nunresolved 127.0.0.1.nip.io [Errno -3]\n" if as_uid else
                   "ns net:[2]\nanswered 172.21.0.1\nresolved 127.0.0.1.nip.io 127.0.0.1\n")
            return ExecResult("names", 0, out, "", 0.1)
        if "/proc/net/route" in " ".join(argv):  # root's view of the gateway and the resolver
            return ExecResult("hosts", 0, "172.20.0.1 172.21.0.1\n", "", 0.1)
        return ExecResult(" ".join(argv), 0, "", "", 0.1)

    def harness_read(self, path: str, max_bytes: int) -> bytes:
        self.reads += 1
        data = self.files[path][:max_bytes]
        return data[: len(data) // 4] if self.reads <= self.short_reads else data


# ---------------------------------------------------------------- the launch


def test_evidence_is_made_by_the_display_uid_and_root_never_the_box_user():
    box = GuiBox()
    result, shown, shot = gui.launch(box, LAUNCH, 2, 20)
    assert result.exit_code == 0 and shown.tier == "window" and shot == png()
    (snap_argv, snap_uid, _), (watch_argv, watch_uid, watcher), (stop_argv, stop_uid, stopper) = box.harness
    assert snap_uid == watch_uid == gui.DISPLAY_UID and stop_uid is None  # the stop runs as root
    assert snap_argv == watch_argv == stop_argv == ["/usr/local/bin/python3", "-I", "-S", "-"]
    assert "PICKFIT_KILLED" in stopper
    # The watcher: absolute paths, no shell; its nonce travels on stdin only, never in an argv.
    assert "shell=True" not in watcher
    assert set(re.findall(r'\["(/[\w/]+)"', watcher)) == {"/usr/bin/xrestop", "/usr/bin/xwininfo", "/usr/bin/xwd",
                                                         "/usr/bin/convert"}
    nonce = re.search(r'"([0-9a-f]{24})"', watcher).group(1)
    assert all(nonce not in " ".join(argv) for argv, _, _ in box.harness)
    assert all(nonce not in command for command, _ in box.ran)
    # The box user ran only the start and the read of its own log.
    assert len(box.ran) == 2 and box.ran[0][0].endswith("& echo started") and "/usr/bin/tail" in box.ran[1][0]
    assert f"{gui.EVIDENCE_DIR}/2.png" in watcher


def test_the_report_is_the_one_line_with_this_launchs_nonce():
    good = json.dumps(report([DEMO_WINDOW]))
    assert gui.parse_report(f"{gui.MARK}abc {good}\n", "abc").tier == "window"
    assert gui.parse_report(f"{gui.MARK}xyz {good}\n", "abc").tier == "none"  # someone else's line
    twice = gui.parse_report(f"{gui.MARK}abc {good}\n{gui.MARK}abc {good}\n", "abc")
    assert twice.tier == "none" and "2 report lines" in twice.error
    gone = gui.parse_report(f"{gui.MARK}abc {json.dumps(report([DEMO_WINDOW], problems=['x server gone']))}", "abc")
    assert gone.tier == "none" and gone.windows == [] and gone.error == "x server gone"


def test_a_window_of_the_apps_own_is_tier_window_and_what_the_app_set_stays_out_of_stdout():
    result, shown, _ = gui.launch(GuiBox(), LAUNCH, 2, 20)
    assert result.stdout.startswith("gui tier: window")
    assert "window 1: 1100x760 at 90,20 (pid 42)" in result.stdout
    for app_set in ("Demo App", "demo", "app started"):  # title, process name, output: all the app's
        assert app_set not in result.stdout
    assert "window 1 title: 'Demo App'" in result.stderr and result.stderr.endswith("app started")
    assert result.stderr.index("set by the app") < result.stderr.index("app output")
    assert shown.log_tail == "app started\n"


def test_no_window_is_process_alive_and_a_short_copy_is_refused():
    result, shown, shot = gui.launch(GuiBox(shown=report()), LAUNCH, 2, 20)
    assert (result.exit_code, shown.tier, shot) == (1, "process_alive", None)
    box = GuiBox(short_reads=1)
    result, shown, shot = gui.launch(box, LAUNCH, 2, 20)
    assert result.exit_code == 0 and shot == png() and box.reads == 2
    box = GuiBox(short_reads=gui.SHOT_READS)
    result, shown, shot = gui.launch(box, LAUNCH, 2, 20)
    assert result.exit_code == 1 and shot is None and "copy incomplete after 3 reads" in shown.error


def test_survivors_of_the_stop_fail_the_launch():
    result, shown, shot = gui.launch(GuiBox(survivors=True), LAUNCH, 2, 20)
    assert result.exit_code == 1 and shot is None
    assert "box-user processes survived the stop" in shown.error and "note:" in result.stdout


def _fake_proc(files: dict[str, bytes]) -> dict[str, Any]:
    """The watcher's procs() against a fake /proc."""
    import types

    ns: dict[str, Any] = {"__name__": "pickfit_test"}
    exec(gui._PROCS, ns)  # our own constant
    pids = sorted({path.split("/")[2] for path in files})
    ns["os"] = types.SimpleNamespace(listdir=lambda d: [*pids, "self", "net"])

    def fake_open(path: str, mode: str = "r") -> io.BytesIO:
        if path not in files:
            raise FileNotFoundError(path)
        return io.BytesIO(files[path])

    ns["open"] = fake_open
    return ns["procs"]()


def test_process_names_cannot_break_the_process_list():
    status = "Name:\t{n}\nState:\t{s} (x)\nUid:\t{u}\t{u}\t{u}\t{u}\n"
    files = {
        "/proc/101/status": status.format(n="x", s="S", u=1000).encode(),  # a name set to b"\xff\xfe)"
        "/proc/101/stat": b"101 (\xff\xfe)) S 1 101 101 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0 5551 0 0",
        "/proc/102/status": status.format(n="root", s="S", u=0).encode(),
        "/proc/102/stat": b"102 (sshd) S 1 102 102 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 42 0 0",
        "/proc/103/status": status.format(n="gone", s="Z", u=1000).encode(),
        "/proc/104/status": status.format(n="nostat", s="R", u=1000).encode(),  # its stat vanished
    }
    assert _fake_proc(files) == {"101": ["5551", "\ufffd\ufffd)"], "104": ["?", "?"]}


def test_a_launch_needs_pickfits_display():
    with pytest.raises(ValueError, match="pickfit's display"):
        gui.launch(FakeBox(), LAUNCH, 2, 20)


# ---------------------------------------------------------------- verdict and replay


def test_a_gui_launch_supports_install_only_and_its_signal_must_be_pickfits():
    assert check_kind(LAUNCH, "launch_gui") == "gui" and check_kind(LAUNCH) == "example"
    launch = ResolvedCheck(2, LAUNCH, "launch_gui", [], "Demo App", 0, 0, True, "gui")
    assert supported_level(True, [launch], has_service=False) == "install"
    assert supported_level(True, [launch], has_service=True) == "install"
    record = ExecResult(LAUNCH, 0, "gui tier: window\nwindow: \"Demo\" 900x700", "Welcome to Demo", 1.0)
    assert evaluate_check(record, 0, "Welcome to Demo")[0]
    ok, problems = evaluate_check(record, 0, "Welcome to Demo", trusted_only=True)
    assert not ok and "pickfit's own lines" in problems[0]


def test_the_replay_runs_gui_launches_after_every_other_check(tmp_path: Path):
    launch = ReplayCheck(ReplayCommand(2, "launch_gui", LAUNCH, wait_s=20), (), 0, "gui tier: window", "gui")
    version = ReplayCheck(ReplayCommand(3, "run_command", "demo --version"), (), 0, "demo 1.0", "version")
    plan = ReplayPlan(steps=(ReplayCommand(1, "run_command", INSTALL),), setups=(), checks=(launch, version))
    box = GuiBox({"demo --version": (0, "demo 1.0", "")})
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    result = Replayer(box, log=lambda s: None, evidence_dir=tmp_path).run(plan, task)
    assert result.passed and [c.kind for c in result.checks] == ["version", "gui"]
    order = [c for c, _ in box.ran if c == "demo --version" or c.endswith("& echo started")]
    assert order[0] == "demo --version"
    assert result.checks[1].run.screenshot == str(tmp_path / "replay-2-1.png")


# ---------------------------------------------------------------- the pipeline end to end


def gui_judge_answer(screen: str) -> dict[str, Any]:
    text = json.dumps({"screen": screen, "observed": "The app's window is drawn.", "error_text": None,
                       "evidence_regions": [{"image": 1, "label": "app", "box": {
                           "x_min": 70, "y_min": 25, "x_max": 930, "y_max": 975}}]})
    return {"id": "judge", "object": "response", "created_at": 0, "model": "muse-spark-1.3-contributor",
            "status": "completed", "output": [{"type": "message", "id": "m", "role": "assistant",
                                               "status": "completed",
                                               "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "usage": {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 200,
                      "output_tokens_details": {"reasoning_tokens": 100}, "total_tokens": 2200}}


def gui_turns(claim: str = "function", signal: str = "gui tier: window") -> list[dict[str, Any]]:
    smoke = [{"command_id": 2, "setup_ids": [], "expected_signal": signal, "expected_exit_code": 0,
              "observed_excerpt": 'window: "Demo App"'}]
    return [response("r1", run_cmd(INSTALL)),
            response("r2", ("launch_gui", {"command": LAUNCH, "wait_s": 20})),
            response("r3", finish(level=claim, steps=[1], smoke=smoke, install_method="binary",
                                  tool_version=None))]


class Boxes:
    def __init__(self, replay_shown: dict[str, Any] | None = None) -> None:
        self.replay_shown = replay_shown
        self.made: list[tuple[str, GuiBox]] = []

    def __call__(self, run_id: str, role: str) -> GuiBox:
        box = GuiBox(shown=self.replay_shown if role == "replay" else None)
        self.made.append((role, box))
        return box


def verify(tmp_path: Path, server: FakeServer, boxes: Boxes):
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    ledger = Ledger(tmp_path / "l.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    return verify_task(task, boxes, client=server.client(), ledger=ledger, runs_dir=tmp_path / "runs",
                       log=lambda s: None, run_id="verify-demo-20261031-000000-abcd")


def test_a_gvisor_display_box_tells_the_agent_that_a_flatpak_needs_its_remote_added_as_a_cited_step(tmp_path: Path):
    from pickfit.verify.agent import VerifyAgent
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    gvisor, vm = GuiBox(), GuiBox()
    gvisor.runtime, vm.runtime = "gvisor", "vm"
    rule = "flatpak remote-add --user --if-not-exists flathub"
    assert rule in VerifyAgent(task, gvisor, runs_dir=tmp_path).instructions
    # A VM box has no user namespaces for flatpak's sandbox, and a box without a runtime is not Modal's.
    assert rule not in VerifyAgent(task, vm, runs_dir=tmp_path).instructions
    assert rule not in VerifyAgent(task, GuiBox(), runs_dir=tmp_path).instructions


def test_a_rendered_gui_launch_is_install_with_tier_ui_rendered_judged_on_a_crop(tmp_path: Path):
    server = FakeServer(*gui_turns(), gui_judge_answer("main_ui"))
    boxes = Boxes()
    outcome = verify(tmp_path, server, boxes)
    run = outcome.run
    assert run.level == "install" and run.replayed and run.judge.verdict == "working"
    assert run.gui == GuiCheck(tier="ui_rendered", screen="main_ui", command=LAUNCH, window_title="Demo App",
                               display=gui.DISPLAY_NOTE)
    assert [t.command for t in run.smoke_tests] == [LAUNCH] and run.smoke_tests[0].offline is True
    tools = [t["name"] for t in server.requests[0]["tools"]]
    assert "launch_gui" in tools and "GUI apps: this box has a virtual display" in server.requests[0]["instructions"]
    # The judge saw only the part of the screen the app's own window covers.
    images = [c for c in server.requests[-1]["input"][0]["content"] if c["type"] == "input_image"]
    assert len(images) == 1
    crop = Image.open(io.BytesIO(base64.b64decode(images[0]["image_url"].split(",", 1)[1])))
    assert crop.size == (1100, 760)
    for name in ("gui-2.png", "replay-2-1.png", "replay-2-1.app.png", "replay-2-1.app.judged.png"):
        assert (outcome.evidence_dir / name).exists(), name
    guide = install_guide(run)
    assert guide.check is None and guide.first_task == LAUNCH
    # A desktop app's first task is its launch, even beside an example that ran offline first.
    other = run.smoke_tests[0].model_copy(update={"command": "demo selftest", "offline": True})
    with_example = run.model_copy(update={"smoke_tests": [other, *run.smoke_tests]})
    assert install_guide(with_example).first_task == LAUNCH


@pytest.mark.parametrize("signal", ["app started", "Demo App"])  # the app's output, and its window title
def test_a_signal_the_app_set_does_not_pass(tmp_path: Path, signal: str):
    outcome = verify(tmp_path, FakeServer(*gui_turns("install", signal=signal)), Boxes())
    assert outcome.run.level == "unverified" and outcome.run.judge is None and outcome.run.gui is None


def test_a_crash_dialog_or_a_missing_window_keeps_it_unverified(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns("install"), gui_judge_answer("crash_or_error")), Boxes())
    assert outcome.run.level == "unverified" and outcome.run.judge.verdict == "error_visible"
    assert outcome.run.gui.tier == "window" and outcome.run.gui.screen == "crash_or_error"
    outcome = verify(tmp_path, FakeServer(*gui_turns("install")), Boxes(replay_shown=report()))
    assert outcome.run.level == "unverified" and not outcome.run.replayed and outcome.run.judge is None
    assert outcome.run.gui is None  # no window, nothing judged: no GUI tier is recorded


def test_a_sign_in_wall_is_install_at_tier_window(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns(), gui_judge_answer("sign_in_wall")), Boxes())
    assert outcome.run.level == "install"
    assert (outcome.run.gui.tier, outcome.run.gui.screen) == ("window", "sign_in_wall")


def test_needing_no_sandbox_is_never_the_readmes_fault():
    from pickfit.verify.result import _pitfall_kind

    needed = {"readme_said": "./app", "actually_needed": "./app --no-sandbox"}
    assert _pitfall_kind({**needed, "kind": "readme_wrong"}) == "sandbox"
    assert _pitfall_kind({**needed, "kind": None}) == "sandbox"
    assert _pitfall_kind({**needed, "kind": "tool_handled"}) == "tool_handled"  # its own launcher passes it
    assert _pitfall_kind({"readme_said": "x", "actually_needed": "y", "kind": "readme_wrong"}) == "readme_wrong"


def test_the_worse_verdict_wins_when_a_run_is_judged_in_parts():
    ok = JudgeResult("working", "version printed", None, True, "m", cost_usd=0.01)
    bad = JudgeResult("inconclusive", "a blank window", None, False, "m", cost_usd=0.02, screen="blank_or_loading")
    merged = merge([ok, bad])
    assert merged.verdict == "inconclusive" and merged.screen == "blank_or_loading" and merged.cost_usd == 0.03
    assert merge([]) is None and merge([ok]) is ok


def test_the_judged_area_is_the_apps_windows_on_screen():
    assert app_area([DEMO_WINDOW]) == (90, 20, 1190, 780)
    offscreen = {**DEMO_WINDOW, "x": 1200, "y": 700}  # 80x100 of it on screen: too small to judge
    assert app_area([offscreen]) is None
    small = {**DEMO_WINDOW, "width": 120, "height": 90}
    assert app_area([small, {**DEMO_WINDOW, "x": -50, "y": 0}]) == (0, 0, 1050, 760)


def test_a_desktop_app_on_a_display_box_is_told_to_launch_the_app_itself():
    from pickfit.verify.agent import AgentLimits, render_task
    from pickfit.verify.plan import plan_for

    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    plan = plan_for(task.extraction, "linux")
    assert "This is a desktop (GUI) app" not in render_task(task, plan, GuiBox(), AgentLimits())
    task.extraction.kind.value = "desktop_app"
    text = render_task(task, plan_for(task.extraction, "linux"), GuiBox(), AgentLimits())
    assert "This is a desktop (GUI) app" in text and "--appimage-extract-and-run" in text
    assert "This is a desktop (GUI) app" not in render_task(task, plan, FakeBox(), AgentLimits())


# ---------------------------------------------------------------- the record


def run_with(level: str, tier: str, screen: str | None = "main_ui") -> dict[str, Any]:
    return {"id": "verify-demo-20261031-000000-abcd", "level": level, "unverified_reason": None, "os": "linux",
            "arch": "x86_64", "method": "sandbox", "checked_at": "2026-10-31T12:00:00+08:00", "replayed": True,
            "steps": [{"command": INSTALL}],
            "smoke_tests": [{"command": LAUNCH, "expected_signal": "Demo App", "exit_code": 0, "passed": True}],
            "evidence": {"trace_path": None},
            "gui": {"tier": tier, "screen": screen, "command": LAUNCH, "display": gui.DISPLAY_NOTE}}


def test_the_schema_ties_each_tier_to_its_evidence_and_keeps_launches_at_install():
    assert VerificationRun.model_validate(run_with("install", "ui_rendered")).gui.tier == "ui_rendered"
    assert VerificationRun.model_validate(run_with("install", "window", "sign_in_wall")).gui.tier == "window"
    for tier, screen in (("ui_rendered", None), ("ui_rendered", "sign_in_wall"), ("ui_rendered", "crash_or_error"),
                         ("window", "main_ui"), ("window", None), ("process_alive", None), ("none", None),
                         ("action_state", "main_ui"), ("accessibility", "main_ui")):
        with pytest.raises(ValueError):  # a recorded tier rests on a judged screen that fits it
            VerificationRun.model_validate(run_with("install", tier, screen))
    with pytest.raises(ValueError, match="cannot show"):
        VerificationRun.model_validate(run_with("install", "window", "blank_or_loading"))
    with pytest.raises(ValueError, match="supports install only"):
        VerificationRun.model_validate(run_with("function", "ui_rendered"))
    plain = VerificationRun.model_validate({**run_with("install", "window"), "gui": None})
    assert "gui" not in plain.model_dump(mode="json")  # records without a GUI launch are unchanged


def test_a_desktop_app_record_is_never_above_install():
    data = json.loads((DATA / "hilbertraum.json").read_text())
    run = {**run_with("function", "window"), "gui": None,
           "smoke_tests": [{"command": "hr --version", "expected_signal": "0.1", "exit_code": 0, "passed": True}]}
    data["verification"] = {"level": "function", "unverified_reason": None,
                            "checked_at": run["checked_at"], "runs": [run]}
    with pytest.raises(ValueError, match="a desktop app is not function"):
        SoftwareRecord.model_validate(data)


# ---------------------------------------------------------------- batch, limits, ModalBox


def test_desktop_apps_are_set_aside_only_without_a_display():
    from pickfit.schema import ExtractionResult
    from pickfit.verify.batch import not_in_box

    extraction = json.loads((FIXTURES / "verify" / "graphtty.json").read_text())["extraction"]
    extraction["kind"]["value"] = "desktop_app"
    ex = ExtractionResult.model_validate(extraction)
    assert not_in_box(ex) == "GUI app"
    assert not_in_box(ex, display=True) is None
    assert not_in_box(ex, display=True, os="macos") is None  # tart's GUI base (gui_mac.py)
    assert not_in_box(ex, display=True, os="windows") == "GUI app"


def test_limits_test_on_a_display_box():
    script = {
        "id -u": (0, "1000\nCapEff:\t0000000000000000\n", ""),
        "pypi.org": (0, "200", ""),
        "https://1.1.1.1/": (0, "301", ""),
        "/proc/net/route": (0, "hosts: 172.20.0.1 172.21.0.1\n", ""),
        "169.254.169.254": (28, "", "timed out"),
        "10.0.0.1": (28, "", "timed out"),
        "127.0.0.1:8765": (0, "200", ""),
        "sleep 30": (137, "", ""),
        "head -c 1700M": (153, "", "File size limit exceeded"),
        "os.fork": (0, "blocked after 254 [Errno 11]", ""),
        "bytearray": (137, "", ""),
        "kill -KILL": (0, "before 785\nkill: (785) - Operation not permitted\nalready active\nafter 785\nstill-up\n", ""),
        "/usr/bin/xdpyinfo": (0, "name of display:    :99\n  dimensions:    1280x800 pixels", ""),
        "-C Xvfb": (0, " 1001 Xvfb\n", ""),
        f"ls {gui.EVIDENCE_DIR}": (0, "ls: Permission denied\ntouch: Permission denied\n", ""),
        "AF_VSOCK": (0, "closed 1 52 OSError 97\nclosed 2 52 OSError 97\n", ""),
        "io_uring": (0, "io_uring refused errno 1\n", ""),
        "readlink /proc/self/ns/net": (0, "net:[9]\n", ""),
        "font path": (0, "font path tcp/127.0.0.1.nip.io:7100 error 2\nfont path reset accepted\n", ""),
        "org.freedesktop.Flatpak.SystemHelper": (0, "Error org.freedesktop.DBus.Error.ServiceUnknown: x\n"
                                                    "Error org.freedesktop.DBus.Error.ServiceUnknown: y\n"
                                                    "Error org.freedesktop.DBus.Error.AccessDenied: z\n", ""),
    }

    class Box(GuiBox):
        def exec(self, command, timeout_s, *, cwd=None):
            result = super().exec(command, timeout_s, cwd=cwd)
            if "PICKFIT_PY" in command and "getaddrinfo" in command:  # the DNS probe, offline
                result.stdout = "172.21.0.1 answered 90 bytes\ngetaddrinfo resolved 151.101.0.223"
            elif not self.network_enabled and ("pypi.org" in command or "1.1.1.1" in command):
                result.stdout, result.exit_code = "000", 28
            result.timed_out = result.exit_code == 137 and "sleep" in command
            return result

    box = Box(script, shown=report([{**DEMO_WINDOW, "title": "xclock", "width": 164, "height": 164}]))
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    assert {"no_userns", "no_io_uring", "vsock_closed", "display_server_uid", "display_server_held", "evidence_dir_closed",
            "display_window", "display_report_unforgeable", "internet_ip", "offline_internet_ip", "ipv6_blocked",
            "multicast_no_answer", "gateway_ports_closed", "display_no_tcp", "display_no_network",
            "system_bus_inert"} <= set(results)
    assert "root sees 172.20.0.1 172.21.0.1" in results["gateway_ports_closed"].detail
    assert [name for name, r in results.items() if not r.ok] == ["offline_dns"]  # a resolver that answers fails
    assert results["display_report_unforgeable"].detail.startswith("tier process_alive; child running True")
    assert "control as root: OPEN 2 52" in results["vsock_closed"].detail
    assert results["no_userns"].detail.startswith("max_user_namespaces 0")


@pytest.mark.parametrize("user, root, ok", [
    ("closed 2 52 OSError 97", "OPEN 2 52", True),
    ("closed 2 52 OSError 97", "closed 2 52 OSError 97", True),  # no vsock in this kernel (gVisor)
    ("closed 2 52 OSError 97", "closed 2 52 TimeoutError 110", False),  # root opened nothing: undecided
    ("OPEN 2 52", "OPEN 2 52", False),
    ("closed 2 52 TimeoutError 110", "OPEN 2 52", False),  # refused some other way: not the filter
    ("inherited vsock fd 3\nclosed 2 52 OSError 97", "OPEN 2 52", False),
    ("", "OPEN 2 52", False),  # tried nothing
])
def test_the_vsock_probe_is_decided_by_roots_control(user: str, root: str, ok: bool):
    from pickfit.verify.limits import _vsock

    class Box(GuiBox):
        def harness_exec(self, argv, timeout_s, *, as_uid=None, stdin=None):
            return ExecResult("vsock", 0, root, "", 0.1)

    assert _vsock(Box({"AF_VSOCK": (0, user, "")})).ok is ok


def test_the_watcher_reads_window_facts_by_label_not_from_titles():
    source = gui.watcher_source(before={}, xvfb_pid=785, nonce="ab" * 12, shot="/x.png", wait_s=5)
    ns: dict[str, Any] = {"__name__": "pickfit_test"}
    exec(source, ns)  # our own script; main() does not run
    info = "\n".join(["", "xwininfo: Window id: {id} \"{title}\"", "", "  Absolute upper-left X:  {x}",
                      "  Absolute upper-left Y:  20", "  Width: {w}", "  Height: 760", "  Map State: {state}", ""])
    outputs = {
        ("-root", "-children"): "\n".join([
            "  Root window id: 0x1e5 (the root window) (has no name)", "     3 children:",
            '     0x200003 "Demo": ("demo" "Demo")  1100x760+90+20  +90+20',
            '     0x400001 "x\" 9999x9999+0+0 \"": ("a" "b")  10x10+0+0  +0+0',
            '     0x600001 "IsViewable": ("c" "d")  900x700+0+0  +0+0']),
        ("-id", "0x200003"): info.format(id="0x200003", title="Demo", x=90, w=1100, state="IsViewable"),
        # A title with forged lines: its labels appear twice, so the window does not count.
        ("-id", "0x400001"): info.format(id="0x400001", title="x\n  Map State: IsViewable\n  Width: 9999", x=0,
                                          w=10, state="IsViewable"),
        # Titled "IsViewable" but not mapped.
        ("-id", "0x600001"): info.format(id="0x600001", title="IsViewable", x=0, w=900, state="IsUnMapped"),
    }
    ns["run"] = lambda argv: outputs[tuple(argv[1:])]
    assert ns["windows"]() == [{"id": "0x200003", "title": "Demo", "width": 1100, "height": 760, "x": 90, "y": 20,
                                "visible": True}]


def test_vm_and_display_boxes_pick_their_image_and_runtime():
    assert mb.image_layers() == (mb.sandbox_image_tag(), ())
    name, packages = mb.image_layers("vm", True)
    assert name.startswith("pickfit-sbx-vm-gui:") and packages == (*mb.VM_PACKAGES, *gui.GUI_PACKAGES,
                                                                   *mb.FLATPAK_PACKAGES)
    box = mb.ModalBox(runtime="vm", display=True, client=object(), log=lambda s: None)
    assert box.runner == "modal-vm" and box.display == ":99" and box.image == name
    assert box.create_kwargs()["runtime"] == "vm"
    assert "A virtual display (X server :99" in box.describe()
    assert "No GUI." in mb.ModalBox(client=object()).describe()
    with pytest.raises(ValueError, match="only under gVisor"):
        mb.ModalBox(runtime="vm", gpu="T4")
    with pytest.raises(ValueError, match="runtime must be"):
        mb.ModalBox(runtime="firecracker")


def test_vm_commands_run_under_the_no_vsock_filter():
    from test_verify_modal import FakeSandbox

    vm = mb.ModalBox(runtime="vm", client=object()).user_argv("true", 10, "/home/sbx/work")
    assert vm[7:11] == ["/usr/local/bin/python3", "-I", "-S", mb.NO_VSOCK] and vm[11] == "/usr/bin/env"
    gvisor = mb.ModalBox(client=object())
    gvisor.netns_pid = 4242
    assert gvisor.user_argv("true", 10, "/home/sbx/work")[19] == "/usr/bin/env"  # no filter, in the namespace
    # The display uid's commands (the watcher) too; root's are not filtered.
    box = mb.ModalBox(runtime="vm", client=object(), log=lambda s: None)
    box.sandbox, box.started, box.display_netns_pid = FakeSandbox(), True, 4343
    box.harness_exec(["/usr/local/bin/python3", "-I", "-S", "-"], 10, as_uid=gui.DISPLAY_UID)
    box.harness_exec(["/usr/bin/true"], 10)
    as_display, as_root = (argv for argv, _ in box.sandbox.calls)
    assert as_display[:4] == ("/usr/bin/nsenter", "--target=4343", "--net", "--")  # the display's namespace
    assert as_display[11:15] == ("/usr/local/bin/python3", "-I", "-S", mb.NO_VSOCK) and as_root == ("/usr/bin/true",)


def _run_bpf(prog: list[tuple[int, int, int, int]], arch: int, nr: int, arg0: int) -> int:
    data = {0: nr, 4: arch, 16: arg0}
    acc, pc = 0, 0
    while True:
        code, jt, jf, k = prog[pc]
        if code == 0x20:
            acc, pc = data[k], pc + 1
        elif code in (0x15, 0x35):
            hit = acc == k if code == 0x15 else acc >= k
            pc = pc + 1 + (jt if hit else jf)
        else:
            return k


def test_the_no_vsock_filter_refuses_vsock_and_other_abis_only():
    ns: dict[str, Any] = {}
    exec(mb.NO_VSOCK_SOURCE.split("raw = ")[0], ns)  # our own constant: only the program list
    prog, x86_64, i386 = ns["prog"], 0xC000003E, 0x40000003
    assert _run_bpf(prog, x86_64, 41, 40) == 0x00050000 | 97  # socket(AF_VSOCK): EAFNOSUPPORT
    assert _run_bpf(prog, x86_64, 41, 2) == 0x7FFF0000  # socket(AF_INET): allowed
    assert _run_bpf(prog, x86_64, 0, 40) == 0x7FFF0000  # read(): allowed whatever its first argument
    assert _run_bpf(prog, x86_64, 0x40000000 | 41, 40) == 0x80000000  # the x32 ABI: killed
    assert _run_bpf(prog, i386, 102, 1) == 0x80000000  # i386 socketcall: killed
    for nr in (425, 426, 427):  # io_uring_setup, io_uring_enter, io_uring_register: EPERM
        assert _run_bpf(prog, x86_64, nr, 0) == 0x00050000 | 1
    assert _run_bpf(prog, x86_64, 424, 0) == _run_bpf(prog, x86_64, 428, 0) == 0x7FFF0000


def test_a_vm_box_drops_the_box_users_dns_while_offline():
    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox()
    box = mb.ModalBox(runtime="vm", client=object(), log=lambda s: None)
    box.sandbox, box.started = sandbox, True
    box.set_network(False)
    box.set_network(True)
    assert [argv[-1] for argv, _ in sandbox.calls] == [mb.DNS_BLOCK, mb.DNS_UNBLOCK]
    assert "meta skuid 1000 udp dport 53 drop" in mb.DNS_BLOCK and mb.DNS_BLOCK.startswith("/usr/sbin/nft ")
    assert [argv[0] for argv, _ in sandbox.calls] == ["/usr/bin/bash", "/usr/bin/bash"]  # root: no setpriv
    assert [p["outbound_cidr_allowlist"] for p in sandbox.policies] == [[], mb.ONLINE_CIDRS]


def test_a_vm_display_box_hardens_the_kernel_then_starts_xvfb_as_the_display_uid(monkeypatch: pytest.MonkeyPatch):
    import modal

    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox([(0, [b""], []), (0, [b""], []), (0, [b""], []), (0, [b"netns_pid 4343\n"], []),
                           (0, [b"xvfb_pid 785\n"], []), (0, [b"system_bus_up\n"], [])])
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    box = mb.ModalBox(runtime="vm", display=True, client="client", log=lambda s: None)
    box.start()
    harden, _, _, held, xvfb, bus = (argv for argv, _ in sandbox.calls)  # a VM has no bubblewrap shim
    assert bus[-1] == mb.SYSTEM_BUS
    assert held[-1] == mb.display_netns_script("vm") and box.display_netns_pid == 4343
    assert "/usr/bin/nsenter --target=4343 --net -- /usr/bin/setpriv" in xvfb[-1]  # Xvfb has no network
    assert harden[0] == "/usr/bin/bash" and "user.max_user_namespaces=0" in harden[-1]
    assert sandbox.procs[0].stdin.data == mb.NO_VSOCK_SOURCE.encode()  # the filter goes in as root
    assert xvfb[0] == "/usr/bin/bash" and f"--reuid={gui.DISPLAY_UID}" in xvfb[-1]  # root starts it, as uid 1001
    assert f"--no-new-privs -- /usr/local/bin/python3 -I -S {mb.NO_VSOCK} /usr/bin/env" in xvfb[-1]  # filtered
    assert "-nolisten tcp" in xvfb[-1] and f"-m 0700 -o {gui.DISPLAY_UID}" in xvfb[-1]
    assert box.xvfb_pid == 785


def test_a_display_box_that_cannot_start_its_server_fails(monkeypatch: pytest.MonkeyPatch):
    import modal

    from pickfit.verify.box import BoxError
    from test_verify_modal import FakeSandbox

    # gVisor: the box user's namespace, its uplink, the box setup, the display's namespace, then Xvfb fails.
    sandbox = FakeSandbox([(0, [b"netns_pid 4242\n"], []), (0, [b""], []), (0, [b""], []), (0, [b""], []),
                           (0, [b"netns_pid 4343\n"], []), (1, [b"no display\n"], [])])
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    with pytest.raises(BoxError, match="the virtual display failed: no display"):
        mb.ModalBox(display=True, client="client", log=lambda s: None).start()
    assert sandbox.terminated
    xvfb = sandbox.calls[-1][0][-1]
    # In the display's own namespace (no network), not the box user's.
    assert "/usr/bin/nsenter --target=4343 --user --net -- /usr/bin/setpriv --reuid=1001" in xvfb
    assert "--target=4242" not in xvfb


def test_a_gvisor_box_without_its_network_namespace_never_runs_the_box_user(monkeypatch: pytest.MonkeyPatch):
    import modal

    from pickfit.verify.box import BoxError
    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox([(0, [b"unshare: Operation not permitted\n"], [])])  # no holder pid
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    box = mb.ModalBox(client="client", log=lambda s: None)
    with pytest.raises(BoxError, match="network namespace failed: unshare: Operation not permitted"):
        box.start()
    assert sandbox.terminated and len(sandbox.calls) == 1
    with pytest.raises(BoxError, match="not set up"):
        box.user_argv("true", 10, "/home/sbx/work")


@pytest.mark.parametrize("root, user, ok", [
    (" 1001 Xvfb\n", " 1001 Xvfb\n", True),
    (" 1001 Xvfb\n", " 65534 Xvfb\n", True),  # a gVisor box: the display uid is not mapped in the box user's namespace
    (" 1000 Xvfb\n", " 1000 Xvfb\n", False),
    ("", " 1001 Xvfb\n", False),  # root sees no Xvfb: undecided
    (" 1001 Xvfb\n", " 1001 Xvfb\n 1000 Xvfb\n", False),  # the box user runs one too
])
def test_the_display_uid_probe_is_decided_by_roots_view(root: str, user: str, ok: bool):
    from pickfit.verify.limits import _display_uid

    class Box(GuiBox):
        def harness_exec(self, argv, timeout_s, *, as_uid=None, stdin=None):
            return ExecResult("ps", 0, root, "", 0.1)

    assert _display_uid(Box({"-C Xvfb": (0, user, "")})).ok is ok


def _display_network_box(control: str, display: str, xvfb_ns: str = "net:[11]\nnet:[2]\n",
                         font: str = "font path tcp/127.0.0.1.nip.io:7100 error 2\n") -> GuiBox:
    class Box(GuiBox):
        def harness_exec(self, argv, timeout_s, *, as_uid=None, stdin=None):
            if argv[:1] == ["/usr/bin/readlink"]:
                return ExecResult("readlink", 0, xvfb_ns, "", 0.1)
            return ExecResult("names", 0, display if as_uid else control, "", 0.1)

    return Box({"readlink /proc/self/ns/net": (0, "net:[9]\n", ""), "font path": (0, font, "")})


CONTROL = "ns net:[2]\nanswered 172.21.0.1\nresolved 127.0.0.1.nip.io 127.0.0.1\n"
CLOSED = "ns net:[11]\nno answer 172.21.0.1 OSError\nunresolved 127.0.0.1.nip.io [Errno -3]\n"


@pytest.mark.parametrize("control, display, xvfb_ns, font, ok", [
    (CONTROL, CLOSED, "net:[11]\nnet:[2]\n", "font path tcp/127.0.0.1.nip.io:7100 error 2\n", True),
    # main's code: Xvfb in the box's own namespace, where the resolver answers it offline
    (CONTROL, "ns net:[2]\nanswered 172.21.0.1\nresolved 127.0.0.1.nip.io 127.0.0.1\n", "net:[2]\nnet:[2]\n",
     "font path tcp/127.0.0.1.nip.io:7100 accepted\n", False),
    (CONTROL, CLOSED, "net:[11]\nnet:[2]\n", "font path tcp/127.0.0.1.nip.io:7100 accepted\n", True),  # not judged
    (CONTROL, CLOSED, "net:[11]\nnet:[2]\n", "no X connection\n", False),  # the box user's request never ran
    ("ns net:[2]\nno answer 172.21.0.1 OSError\n", CLOSED, "net:[11]\nnet:[2]\n",  # no control: undecided
     "font path tcp/127.0.0.1.nip.io:7100 error 2\n", False),
    (CONTROL, CLOSED, "net:[9]\nnet:[2]\n", "font path tcp/127.0.0.1.nip.io:7100 error 2\n", False),  # the box user's
])
def test_the_display_network_probe_is_decided_by_root(control: str, display: str, xvfb_ns: str, font: str, ok: bool):
    from pickfit.verify.limits import _display_no_network

    assert _display_no_network(_display_network_box(control, display, xvfb_ns, font)).ok is ok


def test_the_gateway_probe_covers_the_real_gateway_root_sees():
    from pickfit.verify.limits import _gateway

    class Box(GuiBox):
        def harness_exec(self, argv, timeout_s, *, as_uid=None, stdin=None):
            return ExecResult("hosts", 0, "172.20.0.1 172.21.0.1\n", "", 0.1)

    seen = Box({"/proc/net/route": (0, "hosts: 10.0.2.2 172.21.0.1 172.20.0.1\n", "")})
    assert _gateway(seen).ok and "172.20.0.1 172.21.0.1" in seen.ran[-1][0]  # root's hosts go to the box user
    assert not _gateway(Box({"/proc/net/route": (0, "hosts: 10.0.2.2 172.21.0.1\n", "")})).ok  # real gateway unprobed
    assert not _gateway(Box({"/proc/net/route": (0, "hosts: 10.0.2.2 172.20.0.1 172.21.0.1\nopen 172.20.0.1:80\n",
                                                  "")})).ok
