"""The simulated microphone (audio.py): the words, the server pickfit starts, listen in the agent and the replay,
{spoken} in a GUI operation, the limits test's audio and GPU probes, and what a run records."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from pickfit.verify import audio, gui
from pickfit.verify import gui_operate as op
from pickfit.verify import limits
from pickfit.verify import modal_box as mb
from pickfit.verify.agent import LISTEN_TOOL, MIC_RULES, VerifyAgent, tools_for
from pickfit.verify.audio import ListenArgs, run_listen
from pickfit.verify.box import BOX_HOME, ExecResult
from pickfit.verify.replay import ReplayCommand, Replayer
from pickfit.verify.verdict import check_kind, mic_problems, supported_level, ResolvedCheck
from test_verify_gui_operate import NonceServer, OperateBox, note_session, operate_args
from verify_fakes import FakeBox


class MicBox(FakeBox):
    """A FakeBox with the simulated microphone: the harness's flite and paplay are played, and a fake transcriber
    (`hears`) prints or writes what was spoken while it ran."""

    audio = True

    def __init__(self, home: Path | None = None, *, hears: bool = True, script: dict | None = None) -> None:
        super().__init__(script)
        self.home, self.hears = home, hears
        self.spoken: list[str] = []
        self.playing = False
        self.harness: list[tuple[list[str], int | None, str]] = []

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        script, source = argv[-1], (stdin or b"").decode()
        self.harness.append((argv, as_uid, source))
        if "/usr/bin/flite" in script:
            assert as_uid == gui.DISPLAY_UID and source.startswith("I saw ")  # the words travel on stdin only
            self.spoken = re.findall(r"an? (\w+)", source)
            assert not any(w in script for w in self.spoken)
            return ExecResult("flite", 0, "wav_bytes 64000\n", "", 0.5)
        if "/usr/bin/paplay" in script:
            assert as_uid == gui.DISPLAY_UID and not any(w in script for w in self.spoken)
            self.playing = True
            return ExecResult("play", 0, "player 4321\n", "", 0.1)
        if "/usr/bin/kill -KILL -- -4321" in script:
            self.playing = False
            return ExecResult("stop", 0, "", "", 0.1)
        if "def walk_to(path):" in source:  # root's file check, run for real on the temp home
            import os
            import subprocess
            import sys

            local = source.replace(BOX_HOME, str(self.home)).replace('"uid": 1000', f'"uid": {os.getuid()}')
            done = subprocess.run([sys.executable, "-I", "-S", "-"], input=local.encode(), capture_output=True)
            return ExecResult("files", done.returncode, done.stdout.decode().replace(str(self.home), BOX_HOME),
                              done.stderr.decode(), 0.3)
        return ExecResult(" ".join(argv), 0, "", "", 0.1)

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        if command.startswith("transcribe"):
            self.ran.append((command, timeout_s))
            text = f"I saw a {', a '.join(self.spoken)}." if self.hears and self.playing else "(silence)"
            if "--out" in command and self.home is not None:
                out = self.home / "pickfit-out" / "t.txt"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text.title())
                return ExecResult(command, 0, "saved\n", "", 9.0)
            return ExecResult(command, 0, text.upper() + "\n", "", 9.0)
        return super().exec(command, timeout_s, cwd=cwd)


def listen_args(**check: Any) -> ListenArgs:
    return ListenArgs.model_validate({"command": "transcribe --seconds 10", "timeout_s": 60, "feature": 1,
                                      "check": {"kind": "output", "path": None, **check}})


# ---------------------------------------------------------------- words


def test_the_words_are_fresh_distinct_and_checked_as_whole_words_in_any_case():
    words = audio.new_words()
    assert len(set(words)) == 3 and all(w in audio.WORDS for w in words)
    assert len(set(audio.WORDS)) == len(audio.WORDS) >= 150
    assert audio.sentence(["apple", "tiger", "oven"]) == "I saw an apple, a tiger, and an oven.\n"
    assert audio.heard("I saw an Apple, a TIGER and an oven.", ["apple", "tiger", "oven"]) == [True, True, True]
    assert audio.heard("pineapples and tigers", ["apple", "tiger"]) == [False, False]  # whole words only
    assert audio.typed_words(["apple", "tiger"], ["my Tiger"]) == ["tiger"]


def test_the_server_refuses_reconfiguration_and_keeps_the_words_off_command_lines():
    script = audio.pulse_script(("/usr/bin/setpriv", "--reuid=1001"))
    assert "--disallow-module-loading" in script and "--disallow-exit" in script and " -n " in script
    assert "protocol-tcp" not in script and "auth-anonymous=1" in script and audio.PULSE_SOCKET in script
    assert f"set-default-source {audio.MIC}" in script and "autospawn = no" in script
    assert "pcm.!default { type pulse }" in script  # ALSA apps record from it too
    box = MicBox()
    wav, why = audio.speak(box, ["apple", "tiger", "oven"], 3)
    argv, uid, stdin = box.harness[-1]
    assert wav and why is None and wav.startswith(gui.EVIDENCE_DIR + "/") and uid == gui.DISPLAY_UID
    assert stdin == "I saw an apple, a tiger, and an oven.\n" and "tiger" not in " ".join(argv) + wav


# ---------------------------------------------------------------- listen


def test_listen_passes_only_when_the_tool_prints_every_spoken_word_while_they_play():
    box = MicBox()
    result, heard = run_listen(box, listen_args(), 4, log=lambda s: None)
    assert heard.passed and result.exit_code == 0 and audio.MIC_PASSED_LINE in result.stdout.splitlines()
    assert result.stdout.startswith("mic: pickfit spoke 3 fresh words") and "--- the command's own output" in result.stderr
    assert not box.playing  # stopped after the command
    assert all(f'"{w}": yes' in result.stdout for w in heard.words)
    deaf = MicBox(hears=False)
    result, heard = run_listen(deaf, listen_args(), 5, log=lambda s: None)
    assert not heard.passed and result.exit_code == 1
    assert "mic check: failed (the output does not hold every spoken word)" in result.stdout
    # No microphone, or a command that tries to name the words: nothing runs.
    plain = FakeBox()
    result, heard = run_listen(plain, listen_args(), 6, log=lambda s: None)
    assert not heard.passed and "no simulated microphone" in result.stdout and not plain.ran
    _, heard = run_listen(MicBox(), listen_args().model_copy(update={"command": "echo {spoken}"}), 7,
                          log=lambda s: None)
    assert not heard.passed and "cannot name the words" in (heard.error or "")


def test_listen_checks_a_file_the_tool_wrote_after_it_started(tmp_path: Path):
    box = MicBox(tmp_path / "home")
    args = ListenArgs.model_validate({"command": "transcribe --out ~/pickfit-out/t.txt", "timeout_s": 60,
                                      "feature": None, "check": {"kind": "file", "path": "~/pickfit-out/t.txt"}})
    result, heard = run_listen(box, args, 8, log=lambda s: None)
    assert heard.passed, result.stdout
    assert "file /home/sbx/pickfit-out/t.txt" in result.stdout and "written after the command started" in result.stdout


def test_a_listen_is_a_trusted_check_that_supports_function_and_replays_with_fresh_words():
    assert check_kind("transcribe", "listen") == "mic"
    assert mic_problems(0, "mic: ...\nmic check: passed") == []
    assert mic_problems(0, "the tool printed mic check: passed") != []  # only pickfit's own line counts
    passing = ResolvedCheck(1, "transcribe", "listen", [], "mic check: passed", 0, 0, True, "mic")
    assert supported_level(True, [passing], False) == "function"
    box = MicBox()
    spec = listen_args().model_dump()
    replayer = Replayer(box, log=lambda s: None)
    first = replayer.rerun(ReplayCommand(3, "listen", "transcribe --seconds 10", listen=spec))
    words = list(box.spoken)
    second = replayer.rerun(ReplayCommand(3, "listen", "transcribe --seconds 10", listen=spec))
    assert first.ok and second.ok and first.listen["passed"] and box.spoken != words


def test_the_agent_gets_listen_and_the_microphone_rules_only_in_a_box_with_one():
    from pickfit.verify.task import load_fixture
    from test_verify_gui import FIXTURES

    assert LISTEN_TOOL not in tools_for(FakeBox())
    assert LISTEN_TOOL in tools_for(MicBox()) and tools_for(MicBox())[-1]["name"] == "finish"
    task = load_fixture(FIXTURES / "verify" / "graphtty.json", fetch=lambda url: "# demo\n")
    agent = VerifyAgent(task, MicBox(), log=lambda s: None)
    assert MIC_RULES in agent.instructions and "{spoken}" in agent.instructions
    plain = VerifyAgent(task, FakeBox(), log=lambda s: None)
    assert MIC_RULES not in plain.instructions


# ---------------------------------------------------------------- {spoken} in a GUI operation


class MicOperateBox(OperateBox):
    """OperateBox whose app, on ctrl+s, saves what it heard from the microphone (or what was typed)."""

    audio = True

    def __init__(self, home: Path, **kwargs: Any) -> None:
        super().__init__(home, **kwargs)
        self.mic = MicBox(home)

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        if "/usr/bin/flite" in argv[-1] or "paplay" in argv[-1] or "kill -KILL --" in argv[-1]:
            return self.mic.harness_exec(argv, timeout_s, as_uid=as_uid, stdin=stdin)
        result = super().harness_exec(argv, timeout_s, as_uid=as_uid, stdin=stdin)
        source = (stdin or b"").decode()
        if "ACT = json.loads(" in source and '"ctrl+s"' in source and self.mic.playing:
            note = self.home / "pickfit-out" / "note.txt"
            note.write_text(note.read_text() + " heard: " + ", ".join(self.mic.spoken))
        return result


def test_spoken_words_play_through_an_operation_and_count_only_when_the_app_heard_them(tmp_path: Path):
    check = {"kind": "file", "path": "~/pickfit-out/note.txt", "contains": ["{spoken}"], "format": "text"}
    goal = "Click Record, wait 10 seconds, click Stop, then press ctrl+s to save it as ~/pickfit-out/note.txt."
    box = MicOperateBox(tmp_path / "home")
    result, operation, _ = op.run_operation(box, operate_args(goal=goal, check=check), 3, log=lambda s: None,
                                            client=NonceServer(*note_session("recording")).client(),
                                            sleep=lambda s: None)
    assert operation.passed, result.stdout
    assert operation.words == box.mic.spoken and not box.mic.playing
    assert "mic: pickfit spoke 3 fresh words" in result.stdout
    assert all(w not in json.dumps(operation.goal) for w in operation.words)
    # The words in no goal or input, {spoken} only as an item of its own, and never without a microphone.
    assert op.spec_problems(operate_args(goal="Type {spoken}", check=check))
    assert op.spec_problems(operate_args(check={**check, "contains": ["heard {spoken}"]}))
    plain = OperateBox(tmp_path / "plain")
    result, operation, _ = op.run_operation(plain, operate_args(goal=goal, check=check), 4, log=lambda s: None,
                                            sleep=lambda s: None)
    assert not operation.passed and "no simulated microphone" in result.stdout


def test_a_spoken_word_the_operator_typed_shows_nothing():
    passed, part = op.spoken_part(["apple", "tiger"], [True, True], ["Apple pie"])
    assert not passed and "typed by the operator: apple" in part
    spec = op.GuiCheckSpec(kind="screen_text", contains=["{spoken}"])
    seen = op.check_screen(b"png", spec, "n", [], lambda png, exp: (["I saw an APPLE and a tiger"], 0.0, "judge"),
                           before=None, words=["apple", "tiger"])
    assert seen["passed"] and '"apple": yes' in seen["line"]


# ---------------------------------------------------------------- limits: the GPU and the microphone


GPU_OK = ("Tesla T4, 15360 MiB\nsmi_exit 0\nkernel 4.19.0-gvisor\n" + "".join(
    f"dev c {d}\n" for d in (*limits.PLAIN_DEVICES, "nvidiactl", "nvidia3", "nvidia-uvm", "nvidia-uvm-tools")))


@pytest.mark.parametrize("stdout, ok", [
    (GPU_OK, True),
    (GPU_OK.replace("4.19.0-gvisor", "6.8.0-generic"), False),  # the host's kernel: not nvproxy's nodes
    (GPU_OK + "dev b vda\n", False),  # a block device
    (GPU_OK + "dev c dri/card0\n", False),  # DRM
    (GPU_OK + "dev c kvm\n", False),
    (GPU_OK + "app 4242, python\n", False),  # someone else's process on the card
    (GPU_OK.replace("smi_exit 0", "smi_exit 9"), False),
    (GPU_OK.replace("dev c nvidiactl\ndev c nvidia3\ndev c nvidia-uvm\ndev c nvidia-uvm-tools\n", ""), False),
])
def test_the_gpu_probe_needs_the_card_gvisors_kernel_and_only_nvidias_devices(stdout: str, ok: bool):
    assert limits.gpu_contained(ExecResult("probe", 0, stdout, "", 0.5)) is ok


def test_a_gpu_box_names_its_card_or_does_not_start(monkeypatch: pytest.MonkeyPatch):
    from test_verify_modal import FakeSandbox

    box = mb.ModalBox(gpu="T4", client=object(), log=lambda s: None)
    replies = [(0, [b"netns_pid 4242\n"], []), (0, [b"ok"], []), (0, [b"ok"], []), (0, [b"ok"], []),
               (0, [b"Tesla T4\n"], [])]
    monkeypatch.setattr("modal.App.lookup", lambda *a, **k: object())
    monkeypatch.setattr("modal.Image.from_name", lambda name: name)
    monkeypatch.setattr("modal.Sandbox.create", lambda *a, **k: FakeSandbox(list(replies)))
    box.start()
    assert box.gpu_name == "Tesla T4" and "NVIDIA GPU" not in box.describe()  # no display: the agent's task says
    nocard = mb.ModalBox(gpu="T4", client=object(), log=lambda s: None)
    monkeypatch.setattr("modal.Sandbox.create", lambda *a, **k: FakeSandbox([*replies[:4], (9, [], [b"no device"])]))
    with pytest.raises(Exception, match="the GPU failed"):
        nocard.start()


def test_an_audio_box_starts_pickfits_server_and_points_the_box_user_at_it(monkeypatch: pytest.MonkeyPatch):
    from test_verify_modal import FakeSandbox

    name, packages = mb.image_layers("gvisor", False, True)
    assert name.startswith("pickfit-sbx-audio:") and set(audio.AUDIO_PACKAGES) <= set(packages)
    box = mb.ModalBox(audio=True, client=object(), log=lambda s: None)
    sandbox = FakeSandbox([(0, [b"netns_pid 4242\n"], []), (0, [b"ok"], []), (0, [b"ok"], []), (0, [b"ok"], []),
                           (0, [b"netns_pid 4343\n"], []), (0, [b"pulse_pid 39\n"], [])])
    monkeypatch.setattr("modal.App.lookup", lambda *a, **k: object())
    monkeypatch.setattr("modal.Image.from_name", lambda name: name)
    monkeypatch.setattr("modal.Sandbox.create", lambda *a, **k: sandbox)
    box.start()
    assert box.pulse_pid == 39 and box.display_netns_pid == 4343 and box.xvfb_pid is None
    pulse = sandbox.calls[-1][0][-1]
    assert "/usr/bin/nsenter --target=4343" in pulse and "--reuid=1001" in pulse  # the harness's namespace and uid
    assert f"PULSE_SERVER={audio.PULSE_SERVER}" in box.user_argv("true", 10, "/home/sbx/work")
    assert "simulated microphone" in box.describe()
