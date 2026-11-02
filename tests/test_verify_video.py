"""Verification videos: the recorders' commands and copies, action stamps in the recording's clock, the edit
list's honesty rules, the clip's cards, and the record's video field."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pickfit.meta import IMAGE_TOKENS, VIDEO_TOKENS, estimate_input_tokens
from pickfit.schema import SoftwareRecord
from pickfit.verify import gui, record, video
from pickfit.verify import gui_operate as op
from pickfit.verify.box import ExecResult

REPO = Path(__file__).resolve().parents[1]
CONCESSIO = REPO / "data" / "software" / "concessio.json"
FFMPEG = shutil.which("ffmpeg")


def test_only_a_replays_operations_are_recorded_unless_told(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PICKFIT_RECORD", raising=False)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: None)
    assert record.wanted("replay-6-2") and not record.wanted(6)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "all")
    assert record.wanted(6)
    monkeypatch.setattr("pickfit.verify.record.get_env", lambda name, default=None: "off")
    assert not record.wanted("replay-6-2")


def test_the_display_uid_records_pickfits_own_xvfb_and_never_the_box_user():
    script = record.start_script(["/usr/bin/nsenter", "--target=7", "--net", "--"], [], f"{gui.EVIDENCE_DIR}/t.mp4",
                                 f"{gui.EVIDENCE_DIR}/t.rec.log")
    assert f"--reuid={gui.DISPLAY_UID}" in script and "--reuid=1000" not in script
    assert "x11grab" in script and f"-i {gui.DISPLAY}" in script and "--no-new-privs" in script
    assert "< /dev/null >" in script and 'echo "rec_pid $!"' in script  # detached, so the command returns
    assert script.index("/usr/bin/nsenter") < script.index("/usr/bin/setpriv") < script.index("/usr/bin/ffmpeg")
    assert record.ffmpeg_argv("x")[record.ffmpeg_argv("x").index("-framerate") + 1] == str(record.RECORD_FPS)


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


def _video(**over: Any) -> dict[str, Any]:
    data = {"clip": "concessio-20261102-1200.mp4", "clip_sha256": "a" * 64, "seconds": 42.5,
            "raw": [{"file": "concessio-20261102-1200-raw-1.mp4", "sha256": "b" * 64, "seconds": 61.0, "smoke_test": 2}],
            "recorded_at": "2026-11-02T12:00:00+08:00", "recording_run": "video-concessio-20261102-120000-ab12",
            "model": "meta-models/Muse-Spark-Open-816B-A42B",
            "features": ["convert between symbolic and numeric permissions"]}
    return data | over


def _with_video(value: dict[str, Any]) -> SoftwareRecord:
    data = json.loads(CONCESSIO.read_text(encoding="utf-8"))
    data["verification"]["runs"][0]["video"] = value
    return SoftwareRecord.model_validate(data)


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_runs_video_shows_only_what_the_run_checked():
    rec = _with_video(_video())
    assert rec.verification.runs[0].video.raw[0].smoke_test == 2
    plain = json.loads(CONCESSIO.read_text(encoding="utf-8"))
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


def test_the_cards_and_captions_are_drawn_at_the_clips_size():
    from PIL import Image
    import io

    first = Image.open(io.BytesIO(video.card_png("Recorded by pickfit in a sandbox on 2026-11-02", ["a", "b"], ["c"])))
    over = Image.open(io.BytesIO(video.overlay_png("Recorded by pickfit · 2026-11-02", "Type 755 in Numeric")))
    assert first.size == over.size == (video.W, video.H) and over.mode == "RGBA"
    assert over.getpixel((video.W // 2, video.H // 2))[3] == 0  # the app shows through the middle


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_piece_is_cut_whole_from_its_recording_and_framed(tmp_path: Path):
    raw = tmp_path / "raw.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x800:rate=4:duration=6",
                    "-pix_fmt", "yuv420p", str(raw)], check=True)
    cut = video.Cut(raw=0, start=1.0, end=4.0, feature="f", caption="c", result_visible=True, faster=True)
    piece = tmp_path / "p.mp4"
    (tmp_path / "o.png").write_bytes(video.overlay_png("label", "caption"))
    video.render_piece(raw, cut, (100, 50, 400, 300), (1280, 800), tmp_path / "o.png", piece)
    assert record.probe_seconds(piece) == pytest.approx(1.5, abs=0.3)
    png = record.png_frame(piece, 0.5)
    assert png.startswith(b"\x89PNG")


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
