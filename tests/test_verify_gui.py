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
                data = report(alive=1)
            if data["windows"]:
                self.files[shot] = png()
                data.update(shot_bytes=len(png()), shot_sha256=hashlib.sha256(png()).hexdigest())
            return ExecResult("watch", 0, f"{gui.MARK}{nonce} {json.dumps(data)}\n", "", 7.0)
        if source.endswith("print(json.dumps(procs()))\n"):
            return ExecResult("snapshot", 0, "{}\n", "", 0.1)
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


def test_a_window_of_the_apps_own_is_tier_window_and_the_apps_output_stays_out_of_stdout():
    result, shown, _ = gui.launch(GuiBox(), LAUNCH, 2, 20)
    assert result.stdout.startswith("gui tier: window")
    assert 'window: "Demo App" 1100x760 at 90,20 (pid 42)' in result.stdout
    assert "app started" not in result.stdout and result.stderr.endswith("app started")
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


def test_survivors_of_the_stop_are_reported():
    result, shown, _ = gui.launch(GuiBox(survivors=True), LAUNCH, 2, 20)
    assert "box-user processes survived the stop" in shown.error and "note:" in result.stdout


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
    launch = ReplayCheck(ReplayCommand(2, "launch_gui", LAUNCH, wait_s=20), (), 0, "Demo App", "gui")
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


def gui_turns(claim: str = "function", signal: str = "Demo App") -> list[dict[str, Any]]:
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


def test_a_signal_from_the_apps_own_output_does_not_pass(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns("install", signal="app started")), Boxes())
    assert outcome.run.level == "unverified" and outcome.run.judge is None


def test_a_crash_dialog_or_a_missing_window_keeps_it_unverified(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns("install"), gui_judge_answer("crash_or_error")), Boxes())
    assert outcome.run.level == "unverified" and outcome.run.judge.verdict == "error_visible"
    assert outcome.run.gui.tier == "window" and outcome.run.gui.screen == "crash_or_error"
    outcome = verify(tmp_path, FakeServer(*gui_turns("install")), Boxes(replay_shown=report()))
    assert outcome.run.level == "unverified" and not outcome.run.replayed and outcome.run.judge is None
    assert outcome.run.gui.tier == "process_alive" and outcome.run.gui.screen is None


def test_a_sign_in_wall_is_install_at_tier_window(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns(), gui_judge_answer("sign_in_wall")), Boxes())
    assert outcome.run.level == "install"
    assert (outcome.run.gui.tier, outcome.run.gui.screen) == ("window", "sign_in_wall")


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
                         ("window", "main_ui"), ("process_alive", "first_run"), ("action_state", None),
                         ("accessibility", None)):
        with pytest.raises(ValueError):
            VerificationRun.model_validate(run_with("install", tier, screen))
    with pytest.raises(ValueError, match="must reach a window"):
        VerificationRun.model_validate(run_with("install", "process_alive", None))
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
    assert not_in_box(ex, display=True, os="macos") == "GUI app"


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
    assert {"no_userns", "vsock_closed", "display_server_uid", "display_server_held", "evidence_dir_closed",
            "display_window", "display_report_unforgeable", "internet_ip", "offline_internet_ip", "ipv6_blocked",
            "multicast_no_answer", "gateway_ports_closed"} <= set(results)
    assert [name for name, r in results.items() if not r.ok] == ["offline_dns"]  # a resolver that answers fails
    assert results["display_report_unforgeable"].detail.startswith("tier process_alive")


def test_vm_and_display_boxes_pick_their_image_and_runtime():
    assert mb.image_layers() == (mb.sandbox_image_tag(), ())
    name, packages = mb.image_layers("vm", True)
    assert name.startswith("pickfit-sbx-vm-gui:") and packages == (*mb.VM_PACKAGES, *gui.GUI_PACKAGES)
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
    vm = mb.ModalBox(runtime="vm", client=object()).user_argv("true", 10, "/home/sbx/work")
    assert vm[7:11] == ["/usr/local/bin/python3", "-I", "-S", mb.NO_VSOCK] and vm[11] == "/usr/bin/env"
    assert mb.ModalBox(client=object()).user_argv("true", 10, "/home/sbx/work")[7] == "/usr/bin/env"


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

    sandbox = FakeSandbox([(0, [b""], []), (0, [b""], []), (0, [b""], []), (0, [b"xvfb_pid 785\n"], [])])
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    box = mb.ModalBox(runtime="vm", display=True, client="client", log=lambda s: None)
    box.start()
    harden, _, _, xvfb = (argv for argv, _ in sandbox.calls)
    assert harden[0] == "/usr/bin/bash" and "user.max_user_namespaces=0" in harden[-1]
    assert sandbox.procs[0].stdin.data == mb.NO_VSOCK_SOURCE.encode()  # the filter goes in as root
    assert xvfb[0] == "/usr/bin/bash" and f"--reuid={gui.DISPLAY_UID}" in xvfb[-1]  # root starts it, as uid 1001
    assert "-nolisten tcp" in xvfb[-1] and f"-m 0700 -o {gui.DISPLAY_UID}" in xvfb[-1]
    assert box.xvfb_pid == 785


def test_a_display_box_that_cannot_start_its_server_fails(monkeypatch: pytest.MonkeyPatch):
    import modal

    from pickfit.verify.box import BoxError
    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox([(0, [b""], []), (0, [b""], []), (1, [b"no display\n"], [])])
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    with pytest.raises(BoxError, match="the virtual display failed: no display"):
        mb.ModalBox(display=True, client="client", log=lambda s: None).start()
    assert sandbox.terminated
