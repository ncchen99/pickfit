"""Verification videos: the recorders' commands and copies, action stamps in the recording's clock, the edit
list's honesty rules, the clip's cards, and the record's video field."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pickfit.meta import IMAGE_TOKENS, VIDEO_TOKENS, estimate_input_tokens
from pickfit.schema import RunVideo, SoftwareRecord
from pickfit.verify import gui, record, video
from pickfit.verify import gui_operate as op
from pickfit.verify.box import ExecResult

REPO = Path(__file__).resolve().parents[1]
CONCESSIO = REPO / "data" / "software" / "concessio.json"
FFMPEG = shutil.which("ffmpeg")


def test_nothing_is_recorded_unless_told(monkeypatch: pytest.MonkeyPatch):
    # brief §15.7 (11/22): no new tutorial recordings. Unset, PICKFIT_RECORD is off, a replay's operations too.
    monkeypatch.delenv("PICKFIT_RECORD", raising=False)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    assert not record.wanted("replay-x") and not record.wanted("replay-6-2") and not record.wanted(6)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "replay")
    assert record.wanted("replay-6-2") and not record.wanted(6)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "all")
    assert record.wanted(6)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "off")
    assert not record.wanted("replay-6-2")
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "bogus")
    assert not record.wanted("replay-6-2")


def test_no_recorder_is_made_when_recording_is_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    box = SimpleNamespace(os="linux", display=":99", xvfb_pid=7)
    assert record.for_box(box, "replay-1", tmp_path) is None  # type: ignore[arg-type]


def test_a_video_only_command_needs_its_own_allowance(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    assert not record.allowed()
    monkeypatch.setattr("pickfit.verify.record.get_env",
                        lambda name, default=None: "1" if name == record.ALLOW_ENV else None)
    assert record.allowed()


def test_a_video_replay_refuses_while_recording_is_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    with pytest.raises(SystemExit, match="PICKFIT_RECORD is off"):
        video.record_run("tool", editor=video.EDITORS["rules"], log=lambda s: None)


def test_the_display_uid_records_pickfits_own_xvfb_and_never_the_box_user():
    script = record.start_script(["/usr/bin/nsenter", "--target=7", "--net", "--"], [], f"{gui.EVIDENCE_DIR}/t.mp4",
                                 f"{gui.EVIDENCE_DIR}/t.rec.log")
    assert f"--reuid={gui.DISPLAY_UID}" in script and "--reuid=1000" not in script
    assert "x11grab" in script and f"-i {gui.DISPLAY}" in script and "--no-new-privs" in script
    assert "< /dev/null >" in script and 'echo "rec_pid $!"' in script  # detached, so the command returns
    assert script.index("/usr/bin/nsenter") < script.index("/usr/bin/setpriv") < script.index("/usr/bin/ffmpeg")
    assert record.ffmpeg_argv("x")[record.ffmpeg_argv("x").index("-framerate") + 1] == str(record.RECORD_FPS)


def test_a_recording_keeps_enough_to_be_cut_again_and_shows_the_arrow_pointer():
    argv = record.ffmpeg_argv("x")
    assert argv[argv.index("-framerate") + 1] == "10" and argv[argv.index("-crf") + 1] == "22"
    assert argv[argv.index("-g") + 1] == "20" and argv[argv.index("-fs") + 1] == str(record.MAX_BYTES)
    assert record.Recording(path=None, sha256=None).crf == 22
    script = record.start_script([], [], f"{gui.EVIDENCE_DIR}/t.mp4", f"{gui.EVIDENCE_DIR}/t.rec.log")
    # the display uid sets the root window's pointer to the arrow before ffmpeg starts, and says whether it took
    assert script.index("XCreateFontCursor") < script.index('echo "cursor $?"') < script.index("x11grab")
    assert script.count(f"--reuid={gui.DISPLAY_UID}") == 2 and f"DISPLAY={gui.DISPLAY}" in script
    compile(record.CURSOR_PY, "cursor", "exec")
    assert f"XCreateFontCursor(d, {record.XC_LEFT_PTR})" in record.CURSOR_PY and record.XC_LEFT_PTR == 68

    class Box:
        def __init__(self) -> None:
            self.calls = 0

        def display_enter(self) -> list[str]:
            return []

        def seccomp(self) -> list[str]:
            return []

        def harness_exec(self, argv: list[str], timeout_s: int, **_: Any) -> ExecResult:
            self.calls += 1
            out = "cursor 0\nrec_pid 42\n" if self.calls == 1 else \
                "Input #0, x11grab, from ':99':\n  Duration: N/A, start: 1762052345.5, bitrate: 1 kb/s\n"
            return ExecResult(command="x", exit_code=0, stdout=out, stderr="", seconds=0.1)

    rec = record.XvfbRecorder(Box(), "replay-1", Path("/nonexistent/x.mp4"))
    rec.start()
    assert rec.pid == 42 and rec.rec.pointer == "arrow" and rec.rec.started_at == pytest.approx(1762052345.5)


def test_the_first_frames_time_comes_from_ffmpegs_input_line():
    log = ("[x11grab @ 0x5] stream 0: ...\nInput #0, x11grab, from ':99':\n"
           "  Duration: N/A, start: 1762052345.123456, bitrate: 393216 kb/s\n  Stream #0:0: Video: rawvideo\n")
    assert record.first_frame_at(log) == pytest.approx(1762052345.123456)
    assert record.first_frame_at("Output #0, mp4") is None


class CopyBox:
    """Root's reads of a file in the box: a short read first, as a slow output stream gives."""

    def __init__(self, data: bytes) -> None:
        self.data, self.files, self.reads = data, {}, 0

    def harness_exec(self, argv: list[str], timeout_s: int, **_: Any) -> ExecResult:
        assert argv[0] == "/usr/bin/split"
        size, prefix = int(argv[2]), argv[-1]
        for i in range(0, len(self.data), size):
            self.files[f"{prefix}{i // size:03d}"] = self.data[i:i + size]
        return ExecResult(command="split", exit_code=0, stdout="", stderr="", seconds=0.1)

    def harness_read(self, path: str, max_bytes: int) -> bytes:
        self.reads += 1
        data = self.files.get(path, self.data)[:max_bytes]
        return data[: len(data) // 2] if self.reads == 1 else data


def test_a_recording_is_copied_out_in_parts_and_must_match_roots_hash(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(record, "PART_BYTES", 10)
    data = bytes(range(35))
    box = CopyBox(data)
    assert record.copy_out(box, "/var/lib/pickfit-gui/r.mp4", len(data), hashlib.sha256(data).hexdigest()) == data
    assert len(box.files) == 4 and box.reads == 5  # one short read retried
    with pytest.raises(RuntimeError, match="hash"):
        record.copy_out(CopyBox(data), "/var/lib/pickfit-gui/r.mp4", len(data), "0" * 64)


class StampDisplay:
    """A display that keeps its own clock (as XvfbDisplay does with the box's)."""

    width, height = 1280, 800

    def __init__(self) -> None:
        self.acted: list[float] | None = None

    def click(self, x: int, y: int, count: int = 1) -> None:
        self.acted = [100.0, 100.2]

    def key(self, name: str) -> None:
        self.acted = [101.0, 101.1]


class HostDisplay:
    width, height = 1280, 800

    def click(self, x: int, y: int, count: int = 1) -> None:
        pass


def test_each_action_is_stamped_in_its_recordings_clock():
    own = StampDisplay()
    assert op.timed_perform(own, {"kind": "click", "x": 1, "y": 2}) == [100.0, 100.2]
    assert op.timed_perform(own, {"kind": "wait", "seconds": 0}, sleep=lambda s: None) is None  # never reached the box
    host = op.timed_perform(HostDisplay(), {"kind": "click", "x": 1, "y": 2})
    assert host is not None and host[0] <= host[1] and host[0] > 1.7e9  # the host's wall clock (a VNC recording)


def test_the_hands_stamp_input_with_the_boxs_clock():
    source = op.hands_source({"kind": "click", "x": 1, "y": 2}, xvfb_pid=5, nonce="n")
    assert 'out["t0"] = time.time()' in source and 'out["t1"] = time.time()' in source
    compile(source, "<hands>", "exec")


def test_a_video_counts_as_its_worst_case_when_the_budget_is_reserved():
    image = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}]}
    clip = {"messages": [{"role": "user", "content": [
        {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + "A" * 3_000_000}}]}]}
    assert estimate_input_tokens(image) < IMAGE_TOKENS + 100
    assert VIDEO_TOKENS <= estimate_input_tokens(clip) < VIDEO_TOKENS + 100  # not the base64's length


OP = {
    "goal": "In Numeric, type 755 and read Symbolic ({nonce}).", "nonce": "kiwi42", "passed": True,
    "check": {"kind": "screen_text", "expected": ["rwxr-xr-x"]}, "inputs": [],
    "video": {"started_at": 1000.0},
    "steps": [
        {"action": {"kind": "click", "x": 142, "y": 257, "count": 1}, "at": [1003.25, 1003.4]},
        {"action": {"kind": "type", "text": "755"}, "at": [1005.0, 1005.2]},
        {"action": {"kind": "wait", "seconds": 1}, "at": None},
        {"action": {"kind": "key", "name": "Return"}, "at": [1009.5, 1009.6]},
        {"action": {"kind": "done"}},
    ],
    "result": {"line": "on screen: \"rwxr-xr-x\": yes", "seen": {"read": ["rwxr-xr-x"]}},
}


def test_the_action_log_gives_times_in_the_recording():
    lines, typed = video.action_log(OP)
    assert lines[1] == "0:03.2 click at (142, 257)" and lines[2] == '0:05.0 type "755"'
    assert lines[3].startswith("     -") and lines[4] == "0:09.5 press Return" and typed == ["755"]
    assert lines[-1].startswith("end: pickfit's check passed")


def test_a_caption_may_name_only_numbers_and_words_from_pickfits_log():
    evidence = video.evidence_text(OP, "convert between symbolic and numeric permissions")
    assert video.caption_problem("Type 755 in Numeric", evidence) is None
    assert video.caption_problem("Symbolic now reads rwxr-xr-x", evidence) is None
    assert video.caption_problem("Type 777 to allow everything", evidence) == "'777' is not in pickfit's log"
    assert video.caption_problem('Pick "Read only"', evidence) == "'Read only' is not in pickfit's log"
    assert video.caption_problem("x" * 91, evidence) == "too long"


CHANGES = [(3.5, 0.05), (5.3, 0.02), (9.75, 0.3), (14.0, 0.01)]


def test_events_come_from_pickfits_log_and_its_change_points():
    events = video.events_of(OP, CHANGES, 20.0)
    assert [(e.number, e.t, e.kind) for e in events] == [
        (1, 0.0, "start"), (2, 3.25, "click"), (3, 3.5, "change"), (4, 5.0, "type"), (5, 5.3, "change"),
        (6, 9.5, "key"), (7, 9.75, "change"), (8, 14.0, "change")]
    assert events[3].what == 'pickfit types "755"' and events[3].end == 5.2


def test_a_segments_times_come_from_its_events_never_from_the_model():
    events = video.events_of(OP, CHANGES, 20.0)
    assert video.span(events, 2, 2, 20.0, False) == (2.65, 4.9)  # until the answer, not into pickfit's next action
    assert video.span(events, 6, 7, 20.0, True) == (8.9, 12.75)  # the checked result stays 3 s
    assert video.span(events, 1, 1, 20.0, False) == (0.0, 1.5)


def S(first: int, last: int, caption: str, result: bool = False, faster: bool = False):
    return video.Segment(first=first, last=last, caption=caption, result_visible=result, faster=faster)


def test_the_edit_list_keeps_whole_segments_in_order_and_only_checked_features():
    label = "convert between symbolic and numeric permissions"
    events = video.events_of(OP, CHANGES, 20.0)
    answer = video.EditList(segments=[
        S(6, 7, "Symbolic now reads rwxr-xr-x", result=True), S(1, 3, "Click Numeric", faster=True),
        S(4, 5, "Type 777 instead"), S(5, 6, "Again"), S(9, 9, "Nothing"), S(8, 8, "All 777 bits set", result=True)],
        notes="")
    cuts, dropped = video.checked_cuts(answer, 0, 20.0, events, label, video.evidence_text(OP, label))
    assert [(c.start, c.end) for c in cuts] == [(0.0, 4.9), (4.9, 6.8), (8.9, 12.75), (13.4, 17.0)]  # never overlapping
    assert cuts[1].caption == 'Type "755"' and "777" in cuts[1].note  # pickfit's own log, not the model's claim
    assert cuts[3].caption == "Convert between symbolic and numeric permissions"  # shows the checked result
    assert cuts[0].seconds == pytest.approx(2.45)  # 2x counts half
    assert any("overlaps" in d for d in dropped)
    assert any("not events" in d for d in dropped)
    short, why = video.checked_cuts(video.EditList(segments=[S(1, 1, "Wait")], notes=""), 0, 1.0, events, label, label)
    assert not short and "shorter" in why[0]


def test_a_segment_with_a_long_still_stretch_plays_at_2x_and_says_so():
    label = "convert between symbolic and numeric permissions"
    events = video.events_of(OP, CHANGES, 30.0)
    answer = video.EditList(segments=[S(8, 8, "Symbolic still reads rwxr-xr-x", result=True)], notes="")
    long_hold = [*events, video.Event(9, 25.0, 25.0, "change", "the screen changes (1% of it)")]
    cuts, _ = video.checked_cuts(answer, 0, 30.0, long_hold, label, video.evidence_text(OP, label))
    assert not cuts[0].faster  # 14.0 -> 17.0: three seconds of the result, not more
    late = video.EditList(segments=[S(8, 9, "Symbolic still reads rwxr-xr-x", result=True)], notes="")
    cuts, _ = video.checked_cuts(late, 0, 30.0, long_hold, label, video.evidence_text(OP, label))
    assert cuts[0].faster and "no change on screen" in cuts[0].note  # 14.0 -> 25.0 with nothing happening


def test_a_long_caption_is_cut_to_its_first_clause_or_told_from_pickfits_log():
    long = "Clicking in the editor and typing two lines creates a heading; the document now shows it with the word"
    assert video.shorten(long) == "Clicking in the editor and typing two lines creates a heading"
    events = video.events_of(OP, CHANGES, 20.0)
    assert video.logged_caption(events[1:4]) == 'Click, then type "755"'
    assert video.logged_caption(events[2:3]) is None
    marked = [replace(e, what=e.what + "; the screen changes after it") for e in events[1:4]]
    assert video.logged_caption(marked) == 'Click, then type "755"'  # what events_of says after an action


def _video(**over: Any) -> dict[str, Any]:
    data = {"clip": "concessio-20261102-1200.mp4", "clip_sha256": "a" * 64, "seconds": 42.5,
            "raw": [{"file": "concessio-20261102-1200-raw-1.mp4", "sha256": "b" * 64, "seconds": 61.0, "smoke_test": 2}],
            "recorded_at": "2026-11-02T12:00:00+08:00", "recording_run": "video-concessio-20261102-120000-ab12",
            "model": "meta-models/Muse-Spark-Open-816B-A42B",
            "features": ["convert between symbolic and numeric permissions"]}
    return data | over


def _plain_concessio() -> dict[str, Any]:
    """concessio's record without the clip data/ may already carry on its run."""
    data = json.loads(CONCESSIO.read_text(encoding="utf-8"))
    for run in data["verification"]["runs"]:
        run.pop("video", None)
    return data


def _copy_concessio(data_dir: Path) -> None:
    (data_dir / "concessio.json").write_text(json.dumps(_plain_concessio(), ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")


def _with_video(value: dict[str, Any]) -> SoftwareRecord:
    data = _plain_concessio()
    data["verification"]["runs"][0]["video"] = value
    return SoftwareRecord.model_validate(data)


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_runs_video_shows_only_what_the_run_checked():
    rec = _with_video(_video())
    assert rec.verification.runs[0].video.raw[0].smoke_test == 2
    plain = _plain_concessio()
    assert "video" not in SoftwareRecord.model_validate(plain).model_dump(mode="json")["verification"]["runs"][0]
    with pytest.raises(ValueError, match="only features this run checked"):
        _with_video(_video(features=["open a file to read its permissions"]))
    with pytest.raises(ValueError, match="operation that passed"):
        _with_video(_video(raw=[{"file": "r.mp4", "sha256": "b" * 64, "seconds": 3.0, "smoke_test": 1}]))
    with pytest.raises(ValueError):
        _with_video(_video(clip="../escape.mp4"))


def test_the_plan_keeps_the_install_steps_and_only_the_passed_operations():
    saved = {"steps": [{"command_id": 4, "tool": "run_command", "command": "flatpak install -y x", "port": None,
                        "wait_s": None, "seconds": 40.0, "operate": None}],
             "setups": [{"command_id": 5, "tool": "run_command", "command": "mkdir -p ~/d", "port": None,
                         "wait_s": None, "seconds": 0.1, "operate": None}],
             "checks": [
                 {"run": {"command_id": 1, "tool": "run_command", "command": "x --help", "port": None, "wait_s": None,
                          "seconds": 0.5, "operate": None}, "setup_ids": [], "expected_exit_code": 0,
                  "expected_signal": "Usage", "kind": "example"},
                 {"run": {"command_id": 6, "tool": "operate_gui", "command": "flatpak run x", "port": None,
                          "wait_s": 30, "seconds": 90.0, "operate": {"spec": {"goal": "G1"}, "actions": [], "model": None}},
                  "setup_ids": [5], "expected_exit_code": 0, "expected_signal": "gui check: passed", "kind": "gui_op"},
                 {"run": {"command_id": 7, "tool": "operate_gui", "command": "flatpak run x", "port": None,
                          "wait_s": 30, "seconds": 90.0, "operate": {"spec": {"goal": "G2"}, "actions": [], "model": None}},
                  "setup_ids": [], "expected_exit_code": 0, "expected_signal": "gui check: passed", "kind": "gui_op"}]}
    plan = video.operations_plan(video.load_plan(saved), {"G1"})
    assert [s.command_id for s in plan.steps] == [4] and [s.command_id for s in plan.setups] == [5]
    assert [c.run.command_id for c in plan.checks] == [6]


def test_the_marks_are_drawn_at_the_clips_size_and_say_only_a_speed_and_seconds():
    from PIL import Image
    import io

    from pickfit.verify import video_marks

    cut = video.Cut(raw=0, start=0.0, end=20.0, feature="f", caption="c", result_visible=True, faster=True,
                    waits=[(2.0, 9.0)], gap_before=4.4)
    assert video_marks.honesty_marks(True, 11.4) == ["2×", "−11 s"]  # no words: nothing to translate
    assert video_marks.honesty_marks(False, 0.2) == [] and video_marks.honesty_marks(False, 0.6) == ["−1 s"]
    over = Image.open(io.BytesIO(video.marks_overlay(cut)))
    assert over.size == (video.W, video.H) == (1280, 800) and over.mode == "RGBA"
    assert over.getpixel((video.W // 2, video.H // 2))[3] == 0  # the app shows through everywhere else
    assert over.getpixel((video.W - 40, 40))[3] > 0  # the marks: the top right corner
    plain = video.Cut(raw=0, start=0.0, end=5.0, feature="f", caption="c", result_visible=True, faster=False)
    assert video.marks_overlay(plain) is None


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_piece_is_cut_whole_from_its_recording_and_framed(tmp_path: Path):
    from PIL import Image
    import io

    from pickfit.verify.video_marks import Overlay

    raw = tmp_path / "raw.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=gray:size=1280x800:rate=4:duration=6",
                    "-pix_fmt", "yuv420p", str(raw)], check=True)
    cut = video.Cut(raw=0, start=1.0, end=4.0, feature="f", caption="c", result_visible=True, faster=True)
    piece = tmp_path / "p.mp4"
    (tmp_path / "o.png").write_bytes(video.marks_overlay(cut))
    dot = io.BytesIO()
    Image.new("RGBA", (20, 20), (255, 0, 0, 255)).save(dot, "PNG")
    video.render_piece(raw, cut, None, (1280, 800), tmp_path / "o.png", piece,
                       [Overlay(dot.getvalue(), 600, 400, 0.5, 0.9)])
    assert record.probe_seconds(piece) == pytest.approx(1.5, abs=0.3)

    def pixel(at: float, xy: tuple[int, int]) -> tuple[int, ...]:
        return Image.open(io.BytesIO(record.png_frame(piece, at))).convert("RGB").getpixel(xy)

    assert pixel(0.7, (610, 410))[0] > 200 and pixel(0.7, (610, 410))[1] < 60  # the overlay, while it applies
    assert abs(pixel(1.2, (610, 410))[0] - pixel(1.2, (610, 410))[1]) < 20  # and gone after
    assert not list(tmp_path.glob("p-ov*.png"))  # its pictures are not left behind


class FakeVnc:
    sock = None
    captures = 0

    def capture(self) -> tuple[int, int, bytes]:
        FakeVnc.captures += 1
        if FakeVnc.captures == 1:  # a new connection's first frame at another size, black (seen 11/2)
            return 64, 36, bytes(64 * 36 * 4)
        shade = FakeVnc.captures * 40 % 256
        return 64, 48, bytes([shade, 90, 30, 0]) * (64 * 48)


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_the_mac_recorder_writes_frames_at_its_rate_and_ends_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import time

    from pickfit.verify import vnc

    monkeypatch.setattr(vnc.VncClient, "from_url", classmethod(lambda cls, url, **kw: FakeVnc()))

    class Screen:
        size = (64, 48)

    class Box:
        os, vnc_url, _screen = "macos", "vnc://:pw@127.0.0.1:5900", None

        def screen(self) -> Screen:
            return Screen()

    rec = record.VncRecorder(Box(), tmp_path / "r.mp4")
    rec.start()
    time.sleep(2.2)
    got = rec.stop()
    assert got.error is None and got.clock == "host" and (got.width, got.height) == (64, 48)
    assert got.sha256 == record.sha256_file(tmp_path / "r.mp4") and got.seconds == pytest.approx(2.25, abs=0.5)
    assert rec.frames >= 8 and FakeVnc.captures >= 3
    last = record.png_frame(tmp_path / "r.mp4", 2.0)
    from PIL import Image
    import io

    assert Image.open(io.BytesIO(last)).convert("L").getextrema()[1] > 20  # later frames are kept, not the black first


def test_a_video_of_known_length_is_reserved_by_its_length():
    clip = {"messages": [{"role": "user", "content": [
        {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AAAA"}}]}]}
    assert 6 * 250 < estimate_input_tokens(clip, video_seconds=6.0) < 3_000


def test_a_caption_may_also_name_what_pickfits_ocr_reads_on_the_segment():
    label = "customize break length and frequency"
    events = video.events_of(OP, CHANGES, 20.0)
    answer = video.EditList(segments=[S(6, 7, "Length now shows 00 h 07 m", result=True)], notes="")
    cuts, _ = video.checked_cuts(answer, 0, 20.0, events, label, video.evidence_text(OP, label),
                                 lambda start, end: "Length\n00 h : 07 m : 00 s")
    assert cuts[0].caption == "Length now shows 00 h 07 m" and not cuts[0].note
    cuts, _ = video.checked_cuts(answer, 0, 20.0, events, label, video.evidence_text(OP, label))
    assert cuts[0].caption != "Length now shows 00 h 07 m"  # without the screen's word for it, not kept


def test_an_action_that_changed_the_screen_is_never_left_in_a_cut_gap():
    label = "convert between symbolic and numeric permissions"
    did = lambda start, end, points, following: start < 4.0  # the click at 3.25 changed the screen; the rest not
    events = video.events_of(OP, CHANGES, 20.0, changed=did)
    assert events[1].changed and events[1].what.endswith("the screen changes after it")
    assert events[3].changed is False and events[3].what.endswith("nothing on screen changes")
    answer = video.EditList(segments=[S(1, 1, "The app opens"), S(6, 7, "Symbolic now reads rwxr-xr-x", result=True)],
                            notes="")
    cuts, _ = video.checked_cuts(answer, 0, 20.0, events, label, video.evidence_text(OP, label))
    cuts, notes = video.bridge_gaps(cuts, events, 20.0, 0, label)
    assert [c.caption for c in cuts] == ["The app opens", "Click", "Symbolic now reads rwxr-xr-x"]
    assert (cuts[1].start, cuts[1].end) == (2.65, 4.9) and "cut gap" in cuts[1].note and notes


def test_the_first_segment_starts_just_before_the_screen_shows_anything():
    events = video.events_of(OP, CHANGES, 20.0, first_shown=2.0)
    assert events[0].kind == "start" and events[0].t == 1.5 and "black until 2.0 s" in events[0].what
    assert video.span(events, 1, 1, 20.0, False)[0] == 1.5


def test_an_opening_segment_ends_before_the_first_action_that_changed_the_screen():
    label = "convert between symbolic and numeric permissions"
    did = lambda start, end, points, following: start < 4.0
    events = video.events_of(OP, CHANGES, 20.0, first_shown=1.0, changed=did)
    answer = video.EditList(segments=[S(1, 3, "The app opens", faster=True)], notes="")
    cuts, _ = video.checked_cuts(answer, 0, 20.0, events, label, video.evidence_text(OP, label))
    cuts, notes = video.split_openings(cuts, events)
    assert [(c.start, c.end, c.caption, c.needs_caption) for c in cuts] == [
        (0.5, 2.65, "The app opens", False), (2.65, cuts[1].end, "Click", True)]
    assert cuts[1].events[0] == 2 and notes


def _saved_clip(tmp_path: Path, **over: Any) -> Path:
    """A clip result as make_clip saves it, with its files under a videos folder."""
    videos = tmp_path / "videos" / "concessio"
    videos.mkdir(parents=True)
    files = {}
    for name in ("c.mp4", "c.passed-only.mp4", "r1.mp4", "r2.mp4"):
        (videos / name).write_bytes(name.encode() * 50)
        files[name] = hashlib.sha256(name.encode() * 50).hexdigest()
    clip = {"slug": "concessio", "run": "verify-concessio-20261102-000538-0b61",
            "recording_run": "video-concessio-20261102-113357-1a86", "clip": "c.mp4", "clip_sha256": files["c.mp4"],
            "seconds": 48.9, "recorded_at": "2026-11-02T11:34:00+08:00", "model": "meta-models/Muse-Spark-Open-816B-A42B",
            "raw": [{"file": "r1.mp4", "sha256": files["r1.mp4"], "seconds": 41.8, "smoke_test": 2,
                     "feature": "convert between symbolic and numeric permissions"},
                    {"file": "r2.mp4", "sha256": files["r2.mp4"], "seconds": 36.5, "smoke_test": 3,
                     "feature": "calculate umask and resulting permissions"}],
            "features": ["convert between symbolic and numeric permissions", "calculate umask and resulting permissions"],
            "flags": [], "passed_only": None, "events": [], "cuts": []} | over
    path = tmp_path / "clip.json"
    path.write_text(json.dumps(clip), encoding="utf-8")
    return path


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_reviewed_clip_is_written_onto_its_run_and_nothing_else(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    _copy_concessio(data)
    clip = video.load_clip(_saved_clip(tmp_path))
    assert video.write_back(clip, data, videos=tmp_path / "videos").startswith("written")
    rec = SoftwareRecord.model_validate_json((data / "concessio.json").read_text(encoding="utf-8"))
    run = rec.verification.runs[0]
    assert run.video.clip == "c.mp4" and [r.smoke_test for r in run.video.raw] == [2, 3]
    before = _plain_concessio()
    after = json.loads((data / "concessio.json").read_text(encoding="utf-8"))
    del after["verification"]["runs"][0]["video"]
    assert {k: v for k, v in after.items() if k != "updated_at"} == {k: v for k, v in before.items() if k != "updated_at"}


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_flagged_or_altered_clip_is_never_written(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    _copy_concessio(data)
    original = (data / "concessio.json").read_text(encoding="utf-8")
    flagged = video.load_clip(_saved_clip(tmp_path, flags=["segment 2 'x': not seen"], passed_only={
        "clip": "c.passed-only.mp4", "clip_sha256": hashlib.sha256(b"c.passed-only.mp4" * 50).hexdigest(),
        "seconds": 30.0, "features": ["convert between symbolic and numeric permissions"],
        "left_out": ["calculate umask and resulting permissions"]}))
    assert video.write_back(flagged, data, videos=tmp_path / "videos").startswith("not written: flagged")
    (tmp_path / "videos" / "concessio" / "r1.mp4").write_bytes(b"changed")
    assert "does not match" in video.write_back(flagged, data, passed_only=True, videos=tmp_path / "videos")
    assert (data / "concessio.json").read_text(encoding="utf-8") == original


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_passed_only_cut_carries_only_its_recordings(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    _copy_concessio(data)
    clip = video.load_clip(_saved_clip(tmp_path, flags=["segment 4 'y': not seen"], passed_only={
        "clip": "c.passed-only.mp4", "clip_sha256": hashlib.sha256(b"c.passed-only.mp4" * 50).hexdigest(),
        "seconds": 30.0, "features": ["convert between symbolic and numeric permissions"],
        "left_out": ["calculate umask and resulting permissions"]}))
    assert video.write_back(clip, data, passed_only=True, videos=tmp_path / "videos").startswith("written")
    run = SoftwareRecord.model_validate_json((data / "concessio.json").read_text(encoding="utf-8")).verification.runs[0]
    assert run.video.clip == "c.passed-only.mp4" and [r.file for r in run.video.raw] == ["r1.mp4"]
    assert run.video.features == ["convert between symbolic and numeric permissions"]


def _cut(raw: int, start: float, end: float, result: bool, faster: bool = False) -> dict[str, Any]:
    return {"raw": raw, "start": start, "end": end, "result_visible": result, "faster": faster, "caption": "c"}


def test_the_poster_is_the_first_shown_result_past_the_first_card():
    clip = video.ClipResult(slug="s", run="r", recording_run="v", cuts=[
        _cut(0, 0.0, 4.0, False), _cut(0, 10.0, 18.0, False, faster=True), _cut(0, 20.0, 23.0, True),
        _cut(1, 0.0, 6.0, True)], review=[{"ok": True}, {"ok": True}, {"ok": False}, {"ok": True}])
    # first card 3.5 + 4 + 8/2 (2x) + 3 - 0.5: the end of the third segment, its result held on screen
    assert video.poster_at(clip) == (14.0, 2)
    # the passed-only cut leaves recording 0 out (its third segment was refused): recording 1's result
    assert video.poster_at(clip, passed_only=True) == (video.CARD_S + 5.5, 3)
    clip.cuts = [_cut(0, 0.0, 0.6, False)]
    assert video.poster_at(clip) == (video.CARD_S + 0.3, 0)  # no result shown: the last segment, never the card


class _FakeR2:
    def __init__(self, corrupt: str | None = None):
        self.objects: dict[str, bytes] = {}
        self.calls: list[list[str]] = []
        self.corrupt = corrupt

    def __call__(self, args: list[str]) -> bytes:
        self.calls.append(args)
        key = args[3]
        if args[2] == "put":
            assert args[args.index("--remote") - 2] == "--content-type"
            self.objects[key] = Path(args[args.index("--file") + 1]).read_bytes()
            return b""
        return b"x" if self.corrupt and key.endswith(self.corrupt) else self.objects[key]


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_an_uploaded_clip_goes_up_with_its_raws_and_poster_and_is_read_back(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    _copy_concessio(data)
    clip = video.load_clip(_saved_clip(tmp_path))
    (tmp_path / "videos" / "concessio" / "c.jpg").write_bytes(b"poster")  # made by make_poster when missing
    r2 = _FakeR2()
    note = video.write_back(clip, data, videos=tmp_path / "videos", upload_to_r2=True, wrangler=r2)
    assert note.startswith("written") and "concessio/c.jpg (6 bytes)" in note
    assert sorted(r2.objects) == ["pickfit-videos/concessio/c.jpg", "pickfit-videos/concessio/c.mp4",
                                  "pickfit-videos/concessio/r1.mp4", "pickfit-videos/concessio/r2.mp4"]
    kinds = {c[3]: c[c.index("--content-type") + 1] for c in r2.calls if c[2] == "put"}
    assert kinds["pickfit-videos/concessio/c.jpg"] == "image/jpeg" and kinds["pickfit-videos/concessio/c.mp4"] == "video/mp4"
    assert all("--remote" in c for c in r2.calls)


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_clip_that_does_not_read_back_whole_is_not_written(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    _copy_concessio(data)
    original = (data / "concessio.json").read_text(encoding="utf-8")
    clip = video.load_clip(_saved_clip(tmp_path))
    (tmp_path / "videos" / "concessio" / "c.jpg").write_bytes(b"poster")
    note = video.write_back(clip, data, videos=tmp_path / "videos", upload_to_r2=True, wrangler=_FakeR2("r2.mp4"))
    assert note == "not written: upload failed: pickfit-videos/concessio/r2.mp4 read back does not match its sha256"
    assert (data / "concessio.json").read_text(encoding="utf-8") == original


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_poster_is_a_1280_wide_jpeg(tmp_path: Path):
    clip = tmp_path / "c.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x472:rate=8:duration=3",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    video.make_poster(clip, 1.5, tmp_path / "c.jpg")
    from PIL import Image

    with Image.open(tmp_path / "c.jpg") as im:
        assert im.format == "JPEG" and im.size == (1280, 944)


def test_chapters_join_one_features_segments_between_the_cards():
    starts = [0.0, 3.75, 8.0, 12.25, 20.5]
    assert video.chapters_of(["edit a file", "edit a file", "save it"], starts) == [
        {"start_s": 0.0, "title": "Recorded by pickfit", "feature": None},
        {"start_s": 3.75, "title": "Edit a file", "feature": "edit a file"},
        {"start_s": 12.25, "title": "Save it", "feature": "save it"},
        {"start_s": 20.5, "title": "Unedited recordings", "feature": None}]
    # the boundaries found in the clip, matched to the cuts' nominal starts (a piece runs a frame or two long)
    assert video.piece_starts([0.0, 3.5, 7.75, 11.9, 19.8], [3.75, 8.0, 12.25, 20.5]) == starts
    with pytest.raises(ValueError, match="pieces"):
        video.piece_starts([0.0, 3.5, 7.75, 11.9, 19.8], [3.75, 8.0, 20.5])
    with pytest.raises(ValueError, match="starts at"):
        video.piece_starts([0.0, 3.5, 7.75, 11.9, 19.8], [3.75, 9.5, 12.25, 20.5])


def test_a_videos_chapters_cover_the_clip_in_order_and_name_its_features():
    two = ["convert between symbolic and numeric permissions", "calculate umask and resulting permissions"]
    good = [{"start_s": 0.0, "title": "Recorded by pickfit", "feature": None},
            {"start_s": 3.75, "title": "Convert", "feature": two[0]},
            {"start_s": 30.9, "title": "Umask", "feature": two[1]},
            {"start_s": 45.1, "title": "Unedited recordings", "feature": None}]
    base = _video(seconds=48.9, features=two)
    assert len(RunVideo.model_validate(base | {"chapters": good}).chapters) == 4
    assert "chapters" not in RunVideo.model_validate(base).model_dump(mode="json")
    bad = {
        "rise": [good[0], good[2], good[1], good[3]],
        "start at 0": [good[0] | {"start_s": 0.5}, *good[1:]],
        "before the clip ends": [*good[:3], good[3] | {"start_s": 48.9}],
        "close on the last": good[:3],
        "each at least once": [good[0], good[1], good[3]],
        "one chapter": [good[0], good[1], good[1] | {"start_s": 10.0}, good[2], good[3]],
    }
    for why, chapters in bad.items():
        with pytest.raises(ValueError, match=why):
            RunVideo.model_validate(base | {"chapters": chapters})
    with pytest.raises(ValueError):
        RunVideo.model_validate(base | {"chapters": [*good[:2], good[2] | {"feature": "not in the clip"}, good[3]]})
    with pytest.raises(ValueError):
        RunVideo.model_validate(base | {"chapters": [good[0] | {"title": "x" * 81}, *good[1:]]})


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_rendered_clip_has_chapters_where_its_pieces_meet(tmp_path: Path):
    raws = []
    for k in range(2):
        raw = tmp_path / f"raw-{k}.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=1280x800:rate=4:duration={8 + k}",
                        "-pix_fmt", "yuv420p", str(raw)], check=True)
        raws.append((raw,))
    cuts = [video.Cut(raw=0, start=0.5, end=2.6, feature="open it", caption="a", result_visible=False, faster=False),
            video.Cut(raw=0, start=3.0, end=7.1, feature="open it", caption="b", result_visible=True, faster=True),
            video.Cut(raw=1, start=1.0, end=4.3, feature="save it", caption="c", result_visible=True, faster=False)]
    rows = [{"file": f"r{k}.mp4", "sha256": "b" * 64, "seconds": 8.0 + k} for k in range(2)]
    work = tmp_path / "work"
    work.mkdir()
    seconds, chapters, captions, problem = video.render_clip(
        cuts, rows, tmp_path / "c.mp4", os="linux", raws=raws, crops=[None, None], screen=(1280, 800), work=work)
    assert problem is None
    # no cards: the features alone, the first at 0, each naming the raw recording and where in it the chapter starts
    assert chapters == [{"start_s": 0.0, "title": "Open it", "feature": "open it", "raw": 0, "raw_s": 0.5},
                        {"start_s": pytest.approx(2.1 + 2.05, abs=0.25), "title": "Save it", "feature": "save it",
                         "raw": 1, "raw_s": 1.0}]
    assert seconds == pytest.approx(2.1 + 2.05 + 3.3, abs=0.6) and chapters[-1]["start_s"] < seconds  # a frame or two
    # long a piece, at 10 frames a second from a 4-frame recording
    assert [c["text"] for c in captions] == ["a", "b", "c"]
    assert captions[0]["start_s"] == 0.0 and captions[-1]["end_s"] == pytest.approx(seconds, abs=0.15)
    assert all(a["end_s"] == pytest.approx(b["start_s"], abs=0.01) for a, b in zip(captions, captions[1:]))
    from PIL import Image
    import io

    frame = Image.open(io.BytesIO(record.png_frame(tmp_path / "c.mp4", 1.0)))
    assert frame.size == (1280, 800)  # no label bar, no caption bar
    comment = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "format_tags=comment", "-of",
                              "csv=p=0", str(tmp_path / "c.mp4")], capture_output=True, text=True).stdout
    assert "r0.mp4 sha256 " + "b" * 64 in comment and "r1.mp4" in comment  # the last card's facts, in the file


def test_the_captions_say_what_pickfit_did_and_mask_a_password():
    rows = [{"step": 1, "kind": "click", "start_s": 1.0, "target": {"name": "Open", "source": "ocr"}},
            {"step": 2, "kind": "key", "start_s": 2.0, "key": "cmd+shift+g"},
            {"step": 3, "kind": "type", "start_s": 3.0, "text": "~/pickfit-in"},
            {"step": 4, "kind": "click", "start_s": 4.0, "count": 2, "target": {"name": "row of sample.mp4",
                                                                                "source": "operator"}},
            {"step": 5, "kind": "type", "start_s": 5.0, "text": None, "masked": True, "secret": "password"}]
    assert video.action_caption(rows[:3], "macos") == 'Click “Open”, then press ⇧⌘G, then type "~/pickfit-in"'
    assert video.action_caption(rows[3:], "macos") == "Double-click the row of sample.mp4, then type a password"
    assert video.action_caption([{"kind": "key", "key": "ctrl+s"}], "linux") == "Press Ctrl+S"
    assert video.action_caption([{"kind": "key", "key": "Return"}], "linux") == "Press Enter"
    assert video.action_caption([{"kind": "click"}] * 3) == "Click (x3)"
    assert video.action_caption([]) is None


def test_the_recorded_box_is_given_what_the_runs_boxes_were_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The plan comes from replay.json, which knows nothing of grants: they come from the grants.json beside it."""
    from types import SimpleNamespace

    import pickfit.verify.cli as cli_mod
    import pickfit.verify.judge as judge_mod
    import pickfit.verify.replay as replay_mod
    from pickfit.verify.grants import Grant, package_grants, parse_policy
    from test_verify_grants import KindBox, table
    from test_verify_sysdeps import RootBox

    monkeypatch.setattr("pickfit.verify.record.get_env",
                        lambda name, default=None: "replay" if name == "PICKFIT_RECORD" else None)

    held = parse_policy(table())
    run_id = "verify-tool-20261121-000000-abcd"
    source = tmp_path / "runs" / "verify" / run_id
    source.mkdir(parents=True)
    step = {"command_id": 4, "tool": "run_command", "command": "flatpak install -y x", "port": None, "wait_s": None,
            "seconds": 40.0, "operate": None}
    operation = {"run": {"command_id": 6, "tool": "operate_gui", "command": "flatpak run x", "port": None,
                         "wait_s": 30, "seconds": 90.0, "operate": {"spec": {"goal": "G1"}, "actions": [],
                                                                    "model": None}},
                 "setup_ids": [], "expected_exit_code": 0, "expected_signal": "gui check: passed", "kind": "gui_op"}
    (source / "replay.json").write_text(json.dumps({"plan": {"steps": [step], "setups": [], "checks": [operation]}}))
    asked = Grant("service", "postgres", 3, "agent", True, fidelity="real", after_command=2)
    given = [asked, *package_grants(["libxcb1"], held), Grant("virtual_device", "microphone", 3, "plan", False)]
    (source / "grants.json").write_text(json.dumps({"grants": [g.to_dict() for g in given]}))

    # What given_again reads: the agent's request to give again, the plan's packages, and the kinds of box.
    assert video.given_again(source, "modal") == ([asked], ("libxcb1",), {"services": True, "audio": True})
    assert video.given_again(source, "tart")[2] == {}  # a Mac has no services box and no simulated microphone
    assert video.given_again(tmp_path, "modal") == ([], (), {})  # a run from before grants: a plain display box

    class VideoBox(RootBox, KindBox):
        """A box pickfit's root can install in (the stand-in apt), of the kind the factory was asked for."""

        def __init__(self, root: Path, world: dict[str, Any] | None = None, **has: bool) -> None:
            RootBox.__init__(self, root, world, {"pickfit-services start postgres": (0, "postgres: up", "")})
            for name, value in has.items():
                setattr(self, name, value)

    made: list[tuple[dict[str, Any], VideoBox]] = []
    worlds: list[dict[str, Any] | None] = [None, {"install": "fails"}]

    def box_factory(runner: str, lifetime_s: int, **kinds: Any):
        def make(vid: str, role: str) -> VideoBox:
            made.append(({"runner": runner, "role": role, **kinds},
                         VideoBox(tmp_path / f"box{len(made)}", worlds[len(made)],
                                  **{k: v for k, v in kinds.items() if k != "display"})))
            return made[-1][1]
        return make

    replayed: list[tuple[Any, list[Any]]] = []

    class Replayer:
        def __init__(self, box: Any, *, grants: Any = (), give: Any = None, **kw: Any) -> None:
            self.box, self.grants, self.give = box, list(grants), give

        def run(self, plan: Any, task: Any) -> Any:
            replayed.append((plan, [(g.kind, g.name, self.give(self.box, g).granted) for g in self.grants]))
            return SimpleNamespace(passed=True, to_dict=lambda: {"passed": True})

    run = SimpleNamespace(id=run_id, os="linux", runner="modal-gvisor")
    monkeypatch.setattr(video, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(video, "load_record", lambda slug, data_dir: SimpleNamespace(
        slug=slug, name="Tool", repo=None, category="other"))
    monkeypatch.setattr(video, "pick_run", lambda rec, run_id=None: run)
    monkeypatch.setattr(video, "passed_operations", lambda r: [SimpleNamespace(goal="G1")])
    monkeypatch.setattr(video, "find_evidence", lambda rid: source)
    monkeypatch.setattr(cli_mod, "box_factory", box_factory)
    monkeypatch.setattr(replay_mod, "Replayer", Replayer)
    monkeypatch.setattr(judge_mod, "read_screen_text", lambda *a, **kw: (lambda *x, **y: ""))
    out = video.record_run("tool", editor=video.EDITORS["rules"], log=lambda s: None)
    kinds, box = made[0]
    # A fresh box of the run's kind, with a display, the services and the microphone the run's boxes had.
    assert kinds == {"runner": "modal", "role": "video", "display": True, "services": True, "audio": True}
    # pickfit's root installed the plan's package before anything was replayed; the box user ran no apt.
    assert box.state["installed"] == ["libxau6", "libxcb1"] and len(box.harness) == 1 and box.closed
    # The replay was handed the agent's grant and how to give it again: the box user's own helper started it.
    plan, regranted = replayed[0]
    assert [c.run.command_id for c in plan.checks] == [6] and regranted == [("service", "postgres", True)]
    assert [c for c, _ in box.ran] == ["pickfit-services start postgres"]
    assert json.loads((out / "replay.json").read_text(encoding="utf-8"))["video"]["run"] == run_id
    # A box that does not get the packages records nothing: the steps would not be the run's.
    with pytest.raises(SystemExit, match="did not get the packages .* \\(libxcb1\\)"):
        video.record_run("tool", editor=video.EDITORS["rules"], log=lambda s: None)
    assert len(replayed) == 1 and made[1][1].closed


# P2-06 (brief 15.7): a preview is one screenshot made a JPEG the way a poster is, put in R2 beside the clips.
WEB_SKETCH = REPO / "worker" / "test" / "fixtures" / "software" / "fixture-web-sketch.json"


def _fake_poster(calls: list[tuple[Path, float, Path]]) -> Any:
    def poster(src: Path, at: float, dest: Path) -> None:
        calls.append((src, at, dest))
        dest.write_bytes(b"jpeg of " + src.read_bytes())
    return poster


def _sketch_with_shots(tmp_path: Path, shots: list[str], on_disk: list[str]) -> tuple[Path, Path]:
    """The web fixture's record in tmp_path/data with its run's screenshot_paths set; the named ones on disk under
    tmp_path/root (the repo root the paths are relative to)."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    record = json.loads(WEB_SKETCH.read_text(encoding="utf-8"))
    record["verification"]["runs"][0]["evidence"]["screenshot_paths"] = [f"runs/web-1/{s}" for s in shots]
    (data / "fixture-web-sketch.json").write_text(json.dumps(record), encoding="utf-8")
    root = tmp_path / "root"
    (root / "runs" / "web-1").mkdir(parents=True)
    for name in on_disk:
        (root / "runs" / "web-1" / name).write_bytes(name.encode())
    return data, root


def test_a_preview_is_made_from_the_runs_screenshot_after_use_first(tmp_path: Path):
    data, root = _sketch_with_shots(tmp_path, ["install.png", "offline.png", "after.png"],
                                    ["install.png", "offline.png", "after.png"])
    run = SoftwareRecord.model_validate_json((data / "fixture-web-sketch.json").read_text()).verification.runs[0]
    calls: list[tuple[Path, float, Path]] = []
    image, preview = video.prepare_preview(run, tmp_path / "out", root=root, poster=_fake_poster(calls))
    # after.png (the app once used) over install.png; the poster's own maker, at the image's only frame.
    assert calls == [(root / "runs/web-1/after.png", 0.0, tmp_path / "out" / f"preview-{run.id}.jpg")]
    assert image.read_bytes() == b"jpeg of after.png"
    assert preview.model_dump(mode="json") == {"image": f"preview-{run.id}.jpg",
                                               "captured_at": run.checked_at.isoformat().replace("+00:00", "Z"),
                                               "run_id": run.id}
    # Without after.png on disk, install.png; with no screenshot on disk at all, no preview.
    (root / "runs/web-1/after.png").unlink()
    assert video.preview_source(run, root) == root / "runs/web-1/install.png"
    (root / "runs/web-1/install.png").unlink()
    assert video.preview_source(run, root) == root / "runs/web-1/offline.png"
    (root / "runs/web-1/offline.png").unlink()
    with pytest.raises(ValueError, match="no screenshot on disk"):
        video.prepare_preview(run, tmp_path / "out", root=root, poster=_fake_poster(calls))


def test_a_preview_goes_up_to_r2_and_is_read_back_before_the_record_names_it(tmp_path: Path):
    data, root = _sketch_with_shots(tmp_path, ["install.png"], ["install.png"])
    r2 = _FakeR2()
    note = video.write_preview("fixture-web-sketch", data_dir=data, folder=tmp_path / "out", root=root,
                               upload_to_r2=True, poster=_fake_poster([]), wrangler=r2)
    name = "preview-run-20261102-web-1.jpg"
    assert note.startswith("written") and f"fixture-web-sketch/{name}" in note
    assert r2.objects == {f"{video.BUCKET}/fixture-web-sketch/{name}": b"jpeg of install.png"}
    put = r2.calls[0]
    assert put[2] == "put" and put[put.index("--content-type") + 1] == "image/jpeg"
    saved = json.loads((data / "fixture-web-sketch.json").read_text(encoding="utf-8"))
    assert saved["preview"]["image"] == name and saved["preview"]["run_id"] == "run-20261102-web-1"
    SoftwareRecord.model_validate(saved)


def test_a_preview_that_does_not_read_back_leaves_the_record_alone(tmp_path: Path):
    data, root = _sketch_with_shots(tmp_path, ["after.png"], ["after.png"])
    before = (data / "fixture-web-sketch.json").read_text(encoding="utf-8")
    note = video.write_preview("fixture-web-sketch", data_dir=data, folder=tmp_path / "out", root=root,
                               upload_to_r2=True, poster=_fake_poster([]), wrangler=_FakeR2(corrupt=".jpg"))
    assert note.startswith("not written: upload failed") and "sha256" in note
    assert (data / "fixture-web-sketch.json").read_text(encoding="utf-8") == before
    # A run with no screenshot on disk writes nothing either, and never calls R2.
    data2, root2 = _sketch_with_shots(tmp_path / "b", ["after.png"], [])
    r2 = _FakeR2()
    note = video.write_preview("fixture-web-sketch", data_dir=data2, folder=tmp_path / "out", root=root2,
                               upload_to_r2=True, poster=_fake_poster([]), wrangler=r2)
    assert note.startswith("not written: no passed run") and r2.calls == []
