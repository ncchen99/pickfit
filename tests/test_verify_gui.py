"""GUI launch check: the window watcher, launch_gui in the agent and the replay, the GUI judge, the record."""

from __future__ import annotations

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
from pickfit.verify.judge import JudgeResult, merge
from pickfit.verify.limits import run_limits_test
from pickfit.verify.pipeline import verify_task
from pickfit.verify.result import install_guide
from pickfit.verify.task import load_fixture
from pickfit.verify.verdict import ResolvedCheck, check_kind, supported_level
from verify_fakes import FakeBox, FakeServer, finish, response, run_cmd

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data" / "software"
LAUNCH = "./demo.AppImage --appimage-extract-and-run"
INSTALL = "curl -fsSL -o demo.AppImage https://example.com/demo.AppImage && chmod +x demo.AppImage"


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


def watcher_output(windows: list[dict[str, Any]] | None = None, alive: list[int] | None = None,
                   exit_code: str = "", shot: bool = True, log: str = "app started") -> str:
    data = {"seconds_to_window": 1.1 if windows else None, "alive": [41, 42] if alive is None else alive,
            "processes": ["bash", "demo"], "windows": windows or [], "other_windows": [], "screenshot": shot,
            "watched_s": 7.2, "shot_bytes": len(png()) if shot else 0,
            "shot_sha256": hashlib.sha256(png() if shot else b"").hexdigest()}
    return f"{gui.MARK}{json.dumps(data)}\nexit_code {exit_code}\n--- app log tail ---\n{log}\n"


DEMO_WINDOW = {"id": "0x200003", "title": "Demo App", "width": 1100, "height": 760, "pid": 42, "client": "demo"}


class GuiBox(FakeBox):
    """A FakeBox with a display: the watcher script answers `launch_out`, and leaves a PNG behind."""

    display = ":99"

    def __init__(self, script: dict[str, tuple[int, str, str]] | None = None, launch_out: str | None = None) -> None:
        super().__init__(script)
        self.launch_out = watcher_output([DEMO_WINDOW]) if launch_out is None else launch_out

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        if "PICKFIT_GUI_PY" in command:
            self.ran.append((command, timeout_s))
            shot = re.search(r"(/tmp/pickfit-gui/\S+\.png)", command)
            if shot and gui.MARK in self.launch_out and '"screenshot": true' in self.launch_out:
                self.files[shot.group(1)] = png()
            return ExecResult(command, 0, self.launch_out, "", 7.5)
        return super().exec(command, timeout_s, cwd=cwd)


# ---------------------------------------------------------------- the watcher


def test_launch_script_detaches_the_app_and_watches_it_with_the_image_python():
    script = gui.launch_script("./demo --flag 'a b'", 3, 90, workdir="/home/sbx/work")
    assert "export DISPLAY=:99" in script and "setsid nohup bash -c" in script
    assert "/usr/local/bin/python3 -I - $P 60 " in script  # wait capped at WAIT_MAX_S
    assert "echo $? > /tmp/pickfit-gui/3.exit" in script and "/tmp/pickfit-gui/3.png" in script
    assert "xrestop -b -m 1" in script  # window owners come from the X server, not _NET_WM_PID


def test_a_window_of_the_apps_own_is_tier_window():
    shown = gui.parse_launch(watcher_output([DEMO_WINDOW]))
    assert shown.tier == "window" and shown.title == "Demo App" and shown.alive
    text = gui.observation(shown)
    assert text.startswith("gui tier: window") and 'window: "Demo App" 1100x760 (pid 42)' in text
    assert text.endswith("app started")


def test_no_window_is_process_alive_and_an_exit_is_none():
    assert gui.parse_launch(watcher_output()).tier == "process_alive"
    gone = gui.parse_launch(watcher_output(alive=[], exit_code="3", log="boom"))
    assert gone.tier == "none" and gone.exit_code == 3
    assert "the app exited with code 3" in gui.observation(gone)
    broken = gui.parse_launch("bash: Xvfb: command not found\n")
    assert broken.tier == "none" and "watcher printed nothing" in broken.error


def test_launch_passes_only_with_a_window_and_returns_the_screenshot():
    result, shown, shot = gui.launch(GuiBox(), LAUNCH, 2, 20)
    assert result.exit_code == 0 and result.command == LAUNCH and shown.tier == "window"
    assert shot and shot.startswith(b"\x89PNG")
    result, shown, shot = gui.launch(GuiBox(launch_out=watcher_output()), LAUNCH, 2, 20)
    assert result.exit_code == 1 and shown.tier == "process_alive"


def test_a_short_copy_of_the_screenshot_is_read_again_then_refused():
    class ShortReads(GuiBox):
        def __init__(self, short: int) -> None:
            super().__init__()
            self.short, self.reads = short, 0

        def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
            self.reads += 1
            data = super().read_file(path, max_bytes)
            return data[:172_032 % len(data)] if self.reads <= self.short else data

    box = ShortReads(short=1)
    result, shown, shot = gui.launch(box, LAUNCH, 2, 20)
    assert shot == png() and box.reads == 2 and shown.error is None
    box = ShortReads(short=gui.SHOT_READS)
    result, shown, shot = gui.launch(box, LAUNCH, 2, 20)
    assert shot is None and "copy incomplete after 3 reads" in shown.error
    assert result.exit_code == 0  # the window was there; the judge just has nothing to read, so it cannot pass


# ---------------------------------------------------------------- verdict and replay


def test_a_gui_launch_supports_install_only_even_beside_a_server():
    assert check_kind(LAUNCH, "launch_gui") == "gui" and check_kind(LAUNCH) == "example"
    launch = ResolvedCheck(2, LAUNCH, "launch_gui", [], "Demo App", 0, 0, True, "gui")
    assert supported_level(True, [launch], has_service=False) == "install"
    assert supported_level(True, [launch], has_service=True) == "install"


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


def gui_turns(claim: str = "function") -> list[dict[str, Any]]:
    smoke = [{"command_id": 2, "setup_ids": [], "expected_signal": "Demo App", "expected_exit_code": 0,
              "observed_excerpt": 'window: "Demo App"'}]
    return [response("r1", run_cmd(INSTALL)),
            response("r2", ("launch_gui", {"command": LAUNCH, "wait_s": 20})),
            response("r3", finish(level=claim, steps=[1], smoke=smoke, install_method="binary",
                                  tool_version=None))]


class Boxes:
    def __init__(self, replay_out: str | None = None) -> None:
        self.replay_out = replay_out
        self.made: list[tuple[str, GuiBox]] = []

    def __call__(self, run_id: str, role: str) -> GuiBox:
        box = GuiBox(launch_out=self.replay_out if role == "replay" else None)
        self.made.append((role, box))
        return box


def verify(tmp_path: Path, server: FakeServer, boxes: Boxes):
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    ledger = Ledger(tmp_path / "l.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    return verify_task(task, boxes, client=server.client(), ledger=ledger, runs_dir=tmp_path / "runs",
                       log=lambda s: None, run_id="verify-demo-20261031-000000-abcd")


def test_a_rendered_gui_launch_is_install_with_tier_ui_rendered(tmp_path: Path):
    server = FakeServer(*gui_turns(), gui_judge_answer("main_ui"))
    boxes = Boxes()
    outcome = verify(tmp_path, server, boxes)
    run = outcome.run
    assert run.level == "install" and run.replayed and run.judge.verdict == "working"
    assert run.gui == GuiCheck(tier="ui_rendered", screen="main_ui", command=LAUNCH, window_title="Demo App",
                               display=gui.DISPLAY_NOTE)
    assert [t.command for t in run.smoke_tests] == [LAUNCH] and run.smoke_tests[0].offline is True
    # The agent was offered launch_gui (a display box), and saw only text: the judge reads the replay's PNG.
    tools = [t["name"] for t in server.requests[0]["tools"]]
    assert "launch_gui" in tools and "GUI apps: this box has a virtual display" in server.requests[0]["instructions"]
    judge_request = server.requests[-1]
    images = [c for c in judge_request["input"][0]["content"] if c["type"] == "input_image"]
    assert len(images) == 1 and images[0]["image_url"].startswith("data:image/png;base64,")
    for name in ("gui-2.png", "replay-2-1.png", "replay-2-1.judged.png"):
        assert (outcome.evidence_dir / name).exists(), name
    replay_launches = [c for c, _ in boxes.made[1][1].ran if "PICKFIT_GUI_PY" in c]
    assert len(replay_launches) == 1
    # The guide keeps the launch as the first task, never as a check that prints text.
    guide = install_guide(run)
    assert guide.check is None and guide.first_task == LAUNCH


def test_a_desktop_app_on_a_display_box_is_told_to_launch_the_app_itself():
    from pickfit.verify.agent import AgentLimits, render_task
    from pickfit.verify.plan import plan_for

    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    assert "This is a desktop (GUI) app" not in render_task(task, plan_for(task.extraction, "linux"), GuiBox(),
                                                             AgentLimits())
    task.extraction.kind.value = "desktop_app"
    text = render_task(task, plan_for(task.extraction, "linux"), GuiBox(), AgentLimits())
    assert "This is a desktop (GUI) app" in text and "--appimage-extract-and-run" in text
    assert "This is a desktop (GUI) app" not in render_task(task, plan_for(task.extraction, "linux"), FakeBox(),
                                                             AgentLimits())


def test_a_crash_dialog_or_a_missing_window_keeps_it_unverified(tmp_path: Path):
    outcome = verify(tmp_path, FakeServer(*gui_turns("install"), gui_judge_answer("crash_or_error")), Boxes())
    assert outcome.run.level == "unverified" and outcome.run.judge.verdict == "error_visible"
    assert outcome.run.gui.tier == "window" and outcome.run.gui.screen == "crash_or_error"
    outcome = verify(tmp_path, FakeServer(*gui_turns("install")), Boxes(replay_out=watcher_output()))
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


# ---------------------------------------------------------------- the record


def run_with(level: str, tier: str) -> dict[str, Any]:
    return {"id": "verify-demo-20261031-000000-abcd", "level": level, "unverified_reason": None, "os": "linux",
            "arch": "x86_64", "method": "sandbox", "checked_at": "2026-10-31T12:00:00+08:00", "replayed": True,
            "steps": [{"command": INSTALL}],
            "smoke_tests": [{"command": LAUNCH, "expected_signal": "Demo App", "exit_code": 0, "passed": True}],
            "evidence": {"trace_path": None},
            "gui": {"tier": tier, "screen": "main_ui", "command": LAUNCH, "display": gui.DISPLAY_NOTE}}


def test_the_schema_keeps_gui_launches_at_install():
    assert VerificationRun.model_validate(run_with("install", "ui_rendered")).gui.tier == "ui_rendered"
    with pytest.raises(ValueError, match="must reach a window"):
        VerificationRun.model_validate(run_with("install", "process_alive"))
    with pytest.raises(ValueError, match="supports install only"):
        VerificationRun.model_validate(run_with("function", "ui_rendered"))
    assert VerificationRun.model_validate(run_with("function", "action_state")).level == "function"
    plain = VerificationRun.model_validate({**run_with("install", "window"), "gui": None})
    assert "gui" not in plain.model_dump(mode="json")  # records without a GUI launch are unchanged


def test_a_desktop_app_record_is_never_function_from_a_cli_check():
    data = json.loads((DATA / "hilbertraum.json").read_text())
    run = {**run_with("function", "window"), "gui": None,
           "smoke_tests": [{"command": "hr --version", "expected_signal": "0.1", "exit_code": 0, "passed": True}]}
    data["verification"] = {"level": "function", "unverified_reason": None,
                            "checked_at": run["checked_at"], "runs": [run]}
    with pytest.raises(ValueError, match="a desktop app is function only once"):
        SoftwareRecord.model_validate(data)


# ---------------------------------------------------------------- batch, limits, ModalBox


def test_desktop_apps_are_set_aside_only_without_a_display():
    from pickfit.schema import ExtractionResult
    from pickfit.verify.batch import not_in_box

    fixture = json.loads((FIXTURES / "verify" / "graphtty.json").read_text())
    extraction = fixture["extraction"]
    extraction["kind"]["value"] = "desktop_app"
    ex = ExtractionResult.model_validate(extraction)
    assert not_in_box(ex) == "GUI app"
    assert not_in_box(ex, display=True) is None
    assert not_in_box(ex, display=True, os="macos") == "GUI app"


def test_limits_test_on_a_display_box_checks_the_x_server_and_a_real_window():
    script = {
        "id -u": (0, "1000\nCapEff:\t0000000000000000\n", ""),
        "pypi.org": (0, "200", ""),
        "169.254.169.254": (28, "", "timed out"),
        "10.0.0.1": (28, "", "timed out"),
        "127.0.0.1:8765": (0, "200", ""),
        "sleep 30": (137, "", ""),
        "head -c 1700M": (153, "", "File size limit exceeded"),
        "os.fork": (0, "blocked after 254 [Errno 11]", ""),
        "bytearray": (137, "", ""),
        "xdpyinfo": (0, "name of display:    :99\n  dimensions:    1280x800 pixels", ""),
        "-C Xvfb": (0, " 1000 Xvfb\n", ""),
    }

    class Box(GuiBox):
        def exec(self, command, timeout_s, *, cwd=None):
            result = super().exec(command, timeout_s, cwd=cwd)
            if "PICKFIT_PY" in command and "getaddrinfo" in command:  # the DNS probe, offline
                result.stdout = "172.21.0.1 answered 90 bytes\ngetaddrinfo resolved 151.101.0.223"
            elif not self.network_enabled and "pypi.org" in command:
                result.stdout, result.exit_code = "000", 28
            result.timed_out = result.exit_code == 137 and "sleep" in command
            return result

    box = Box(script, launch_out=watcher_output([{**DEMO_WINDOW, "title": "xclock", "width": 164, "height": 164}]))
    results = {r.name: r for r in run_limits_test(box, log=lambda s: None)}
    assert {"no_kvm", "display_up", "display_as_box_user", "display_no_tcp", "display_window"} <= set(results)
    assert [name for name, r in results.items() if not r.ok] == ["offline_dns"]  # a resolver that answers fails


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


def test_a_vm_box_drops_the_box_users_dns_while_offline():
    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox()
    box = mb.ModalBox(runtime="vm", client=object(), log=lambda s: None)
    box.sandbox, box.started = sandbox, True
    box.set_network(False)
    box.set_network(True)
    rules = [argv[-1] for argv, _ in sandbox.calls]
    assert rules == [mb.DNS_BLOCK, mb.DNS_UNBLOCK]
    assert "meta skuid 1000 udp dport 53 drop" in mb.DNS_BLOCK
    assert [argv[0] for argv, _ in sandbox.calls] == ["bash", "bash"]  # as root: not through setpriv
    assert [p["outbound_cidr_allowlist"] for p in sandbox.policies] == [[], mb.ONLINE_CIDRS]


def test_a_display_box_starts_xvfb_as_the_box_user(monkeypatch: pytest.MonkeyPatch):
    import modal

    from test_verify_modal import FakeSandbox

    sandbox = FakeSandbox()
    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", lambda *a, **kw: sandbox)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    mb.ModalBox(display=True, client="client", log=lambda s: None).start()
    xvfb = [argv for argv, _ in sandbox.calls if "Xvfb" in argv[-1]]
    assert len(xvfb) == 1 and xvfb[0][0] == "setpriv" and "--reuid=1000" in xvfb[0]
    assert "-nolisten tcp" in xvfb[0][-1]
