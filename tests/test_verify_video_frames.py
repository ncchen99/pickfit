"""Verification videos edited from still frames (Claude takes no video): which frames, how they merge, numbers and
rings, the review's frame numbers turned back into clip time, and the clip's sources and sandboxes."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pickfit.meta import PROD_MODEL
from pickfit.schema import SoftwareRecord
from pickfit.verify import record, video

REPO = Path(__file__).resolve().parents[1]
CONCESSIO = REPO / "data" / "software" / "concessio.json"
FFMPEG = shutil.which("ffmpeg")


def test_the_editor_comes_from_the_flag_then_the_environment_then_the_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(video, "get_env", lambda name, default=None: None)
    assert video.editor_for().key == video.DEFAULT_EDITOR
    assert video.editor_for("claude").model == PROD_MODEL and video.editor_for("claude").frames
    monkeypatch.setattr(video, "get_env", lambda name, default=None: "Claude" if name == "PICKFIT_VIDEO_EDITOR" else None)
    assert video.editor_for().key == "claude" and video.editor_for("muse").key == "muse"
    assert not video.editor_for("muse").frames and video.editor_for("muse").model == video.EDIT_MODEL
    with pytest.raises(SystemExit, match="unknown video editor"):
        video.editor_for("gpt")


def _events() -> list[video.Event]:
    return [video.Event(1, 0.0, 0.0, "start", "the recording starts"),
            video.Event(2, 2.0, 2.1, "click", "pickfit clicks at (100, 120); the screen changes after it", True, (100, 120)),
            video.Event(3, 2.6, 2.6, "change", "the screen changes (8% of it)"),
            video.Event(4, 5.0, 5.4, "type", 'pickfit types "hi"; the screen changes after it', True)]


def test_each_action_gets_a_frame_before_it_with_its_click_ringed_and_one_after():
    shots = video.edit_shots(_events(), 9.0)
    labels = [s.label for s in shots]
    assert labels == ["event 1 (the recording starts)", "just before event 2", "event 3 (a change on screen)",
                      "after event 2", "just before event 4", "after event 4"]
    before = shots[1]
    assert before.at == pytest.approx(1.75) and before.points == [(100, 120)] and before.action
    assert shots[3].at == pytest.approx(4.1)  # until the screen answered, as action_changed looks: end + 2 s
    assert shots[4].points == [] and shots[-1].at == pytest.approx(7.4)
    assert all(a.at <= b.at for a, b in zip(shots, shots[1:]))


def test_encoding_noise_does_not_make_the_whole_screen_the_apps():
    from PIL import Image

    noise = Image.new("L", (1280, 800))
    for x, y in ((34, 61), (600, 400), (1137, 430), (44, 675), (900, 100), (300, 700), (1000, 600)):
        noise.putpixel((x, y), 255)  # 11/17: seven pixels of a keyframe spread over Windows' wallpaper
    assert noise.getbbox() is not None and video.dense_bbox(noise) is None
    noise.paste(255, (400, 300, 440, 340))
    x0, y0, x1, y1 = video.dense_bbox(noise)
    assert 400 - video.DENSE_BLOCK <= x0 <= 400 and 300 - video.DENSE_BLOCK <= y0 <= 300  # block-aligned, around it
    assert 440 <= x1 <= 440 + video.DENSE_BLOCK and 340 <= y1 <= 340 + video.DENSE_BLOCK


def test_the_oss_own_bar_is_never_the_apps():
    assert video.chrome_bar("windows", 1280, 800) == (0, 800 - video.WIN_TASKBAR, 1280, 800)
    assert video.chrome_bar("macos", 1280, 800) == (0, 0, 1280, video.MAC_MENU_BAR)
    assert video.chrome_bar("linux", 1280, 800) is None


def _write_video(path: Path, frames: list[Any], fps: int = 4) -> None:
    from PIL import Image  # noqa: F401  (the frames are PIL images)

    proc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-video_size",
                             f"{frames[0].size[0]}x{frames[0].size[1]}", "-framerate", str(fps), "-i", "-",
                             "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_frame_that_looks_like_the_one_before_joins_it_but_a_typed_letter_does_not(tmp_path: Path):
    from PIL import Image

    plain = Image.new("RGB", (320, 200), (200, 200, 200))
    dialog = plain.copy()
    dialog.paste((40, 90, 160), (60, 40, 260, 160))
    letter = dialog.copy()
    letter.paste((0, 0, 0), (100, 100, 108, 112))  # a typed letter: 96 pixels, a block's worth
    pointer = letter.copy()
    pointer.paste((255, 255, 255), (20, 180, 30, 195))  # only where pickfit's pointer is: not a new frame
    raw = tmp_path / "raw.mp4"
    _write_video(raw, [plain] * 8 + [dialog] * 8 + [letter] * 8 + [pointer] * 8)  # 2 s each at 4 fps
    shots = [video.Shot(0.5, "a"), video.Shot(1.5, "b", [(50, 50)], True), video.Shot(2.5, "c"),
             video.Shot(4.5, "d"), video.Shot(6.5, "e")]
    frames = video.framed(raw, shots, None, 10, pointers=[(6.0, (25, 187))])
    assert [(k, s.label) for k, s, _ in frames] == [(1, "a; b"), (2, "c"), (3, "d; e")]
    first = frames[0][1]
    assert first.at == 0.5 and first.points == [(50, 50)] and first.action  # the earlier time; the ring kept
    img = frames[0][2]
    assert img.getpixel((2, 2)) == (0, 0, 0)  # the number's box in the corner
    assert img.getpixel((50 + video.RING_R, 50))[0] > 200  # the red ring where pickfit clicked
    cropped = video.framed(raw, shots[:1], (40, 20, 100, 80), 10)[0][2]
    assert cropped.size == (100, 80)


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_too_many_frames_lose_the_ones_with_no_action_first(tmp_path: Path):
    from PIL import Image

    frames = [Image.new("RGB", (64, 48), (i * 53 % 256, i * 53 % 256, 30)) for i in range(24)]  # each one different
    raw = tmp_path / "raw.mp4"
    _write_video(raw, frames)
    shots = [video.Shot(i / 4 + 0.1, f"s{i}", action=i % 3 == 0) for i in range(24)]
    kept = video.framed(raw, shots, None, 8)
    assert len(kept) == 8 and [k for k, _, _ in kept] == list(range(1, 9))
    assert all(s.action for _, s, _ in kept[1:])  # the first frame stays; the quiet ones went first


class Answer:
    def __init__(self, parsed: Any, cost: float = 0.01) -> None:
        self.parsed, self.cost_usd, self.parse_error = parsed, cost, None
        self.usage = None


def test_claude_edits_from_labelled_frames_set_before_the_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from PIL import Image

    sent: dict[str, Any] = {}
    shots = [video.Shot(0.5, "event 1 (the recording starts)"), video.Shot(1.75, "just before event 2", [(1, 2)], True)]
    monkeypatch.setattr(video, "framed", lambda path, s, crop, limit, **kw: [
        (k, shot, Image.new("RGB", (40, 30))) for k, shot in enumerate(shots, start=1)])

    def call_meta(endpoint: str, body: dict[str, Any], **kw: Any) -> Answer:
        sent.update(body=body, kw=kw)
        return Answer(video.EditList(segments=[], notes=""))

    monkeypatch.setattr(video, "call_meta", call_meta)
    op = {"goal": "Open it ({nonce})", "nonce": "n1", "check": {"kind": "screen_text", "expected": ["x"]},
          "result": {"line": "ok"}}
    answer, cost, _ = video.ask_edit(tmp_path / "r.mp4", 9.0, "App", op, _events(), "a feature", {"run_id": "t"},
                                     log=lambda *_: None, editor=video.EDITORS["claude"], crop=(0, 0, 40, 30))
    content = sent["body"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Frame 1 at 0:00.5: event 1 (the recording starts)"}
    assert content[1]["type"] == "image_url" and content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[3]["type"] == "image_url" and "<events" in content[-1]["text"]
    assert not any(p.get("type") == "video_url" for p in content)
    assert video.FRAMES_NOTE.strip()[:40] in sent["body"]["messages"][0]["content"]
    assert sent["kw"]["model"] == PROD_MODEL and "video_seconds" not in sent["kw"]
    assert sent["kw"]["reasoning_effort"] == "medium" and sent["kw"]["max_output_tokens"] == 16_000
    assert answer is not None and cost == 0.01


def test_the_review_answers_with_a_frame_whose_clip_time_pickfit_knows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    frames = video.SeenFrames(parts=[{"type": "text", "text": "Frame 1 at 0:00.0: 0.0 s into this clip"}],
                              clip_s={1: 0.0, 2: 1.5, 3: 3.0})
    answers = iter([video.SeenFrame(seen=True, first_seen_frame=2, why="shows", unmentioned=""),
                    video.SeenFrame(seen=True, first_seen_frame=9, why="?", unmentioned="")])
    bodies = []

    def call_meta(endpoint: str, body: dict[str, Any], **kw: Any) -> Answer:
        bodies.append((body, kw))
        return Answer(next(answers))

    monkeypatch.setattr(video, "call_meta", call_meta)
    claude = video.EDITORS["claude"]
    seen, _ = video.ask_seen(tmp_path / "p.mp4", "Click OK", 4.0, {}, claude, frames)
    assert seen.seen and seen.first_seen_s == 1.5
    seen, _ = video.ask_seen(tmp_path / "p.mp4", "Click OK", 4.0, {}, claude, frames)
    assert not seen.seen and seen.first_seen_s == -1.0  # a frame it was never shown
    body, kw = bodies[0]
    assert body["response_format"]["json_schema"]["name"] == "video_review" and "video_seconds" not in kw
    assert "first_seen_frame" in body["messages"][0]["content"]
    assert body["messages"][1]["content"][-1]["text"] == 'Caption: "Click OK"'
    with pytest.raises(ValueError, match="takes no video"):
        video.ask_seen(tmp_path / "p.mp4", "Click OK", 4.0, {}, claude, None)


@pytest.mark.skipif(not CONCESSIO.exists(), reason="needs data/software/concessio.json")
def test_a_verifications_evidence_directory_is_a_source_of_a_clip(tmp_path: Path):
    rec = SoftwareRecord.model_validate_json(CONCESSIO.read_text(encoding="utf-8"))
    run = next(r for r in rec.verification.runs if video.passed_operations(r))
    (tmp_path / "verification_run.json").write_text(run.model_dump_json(), encoding="utf-8")
    (tmp_path / "report.json").write_text(json.dumps({"slug": "concessio"}), encoding="utf-8")
    meta, name, got = video.clip_source(tmp_path, {"result": {}}, REPO / "data" / "software")
    assert name == rec.name and got.id == run.id
    assert meta == {"slug": "concessio", "run": run.id, "os": run.os, "runner": run.runner, "source": str(tmp_path)}
    _, name, _ = video.clip_source(tmp_path, {"result": {}}, tmp_path / "no-records")
    assert name == "concessio"  # a run not written to a record yet: the slug names it
    with pytest.raises(SystemExit, match="neither a recorded replay"):
        video.clip_source(tmp_path / "missing", {"result": {}})


def test_the_box_and_the_card_name_the_runs_own_sandbox():
    class Run:
        def __init__(self, os: str, runner: str | None) -> None:
            self.os, self.runner = os, runner

    assert video.box_runner(Run("macos", "tart-vz")) == "tart"
    assert video.box_runner(Run("windows", "ec2-windows")) == "ec2-windows"
    assert video.box_runner(Run("linux", "ec2-vm")) == "ec2"
    assert video.box_runner(Run("linux", "modal-gvisor")) == video.box_runner(Run("linux", None)) == "modal"
    assert video.sandbox_label("linux", "ec2-vm") == video.SANDBOXES["linux-ec2"]
    assert video.sandbox_label("linux", "modal-gvisor") == video.SANDBOXES["linux"]
    assert "Windows" in video.sandbox_label("windows", "ec2-windows") and "tart" in video.sandbox_label("macos")


@pytest.mark.parametrize("os, keys", [("windows", ["Ctrl", "S"]), ("macos", ["⌘", "S"])])
def test_a_clip_is_its_segments_alone_with_its_raw_recordings_in_its_metadata(monkeypatch: pytest.MonkeyPatch,
                                                                             tmp_path: Path, os: str, keys: list[str]):
    pieces, joined, drawn = [], [], []
    monkeypatch.setattr(video, "render_piece", lambda raw, cut, crop, screen, overlay, out, overlays=(): pieces.append(
        (cut.caption, overlay, list(overlays))))
    monkeypatch.setattr(video, "concat", lambda parts, dest, comment="": joined.append((parts, comment)))
    monkeypatch.setattr(video.recording, "probe_seconds", lambda path: None)
    import pickfit.verify.video_marks as marks

    real = marks.key_caps
    monkeypatch.setattr(marks, "key_caps", lambda name, os: drawn.append(real(name, os)) or real(name, os))
    rows = [{"file": "r.mp4", "sha256": "a" * 64, "seconds": 5.0, "feature": "f"}]
    actions = [[{"kind": "key", "key": "ctrl+s" if os != "macos" else "cmd+s", "start_s": 1.5},
                {"kind": "click", "x": 640, "y": 400, "start_s": 2.0}]]
    seconds, chapters, captions, problem = video.render_clip(
        [video.Cut(0, 1.0, 3.0, "f", "Save the file", True, False)], rows, tmp_path / "c.mp4", os=os,
        raws=[(tmp_path / "r.mp4",)], crops=[None], screen=(1280, 800), work=tmp_path, actions=actions)
    assert [p[0] for p in pieces] == ["Save the file"]  # one piece: no first card, no last card
    assert pieces[0][1] is None  # neither sped up nor shortened: no marks
    assert drawn == [keys] and len(pieces[0][2]) == 1 + len(marks.RIPPLE_STAGES)  # its keys, and a ripple's frames
    assert "r.mp4 sha256 " + "a" * 64 in joined[0][1]
    assert seconds == 2.0 and problem is None and captions == [{"start_s": 0.0, "end_s": 2.0, "text": "Save the file"}]
    assert chapters == [{"start_s": 0.0, "title": "F", "feature": "f", "raw": 0, "raw_s": 1.0}]


# ---------------------------------------------------------------- a recording that shows an action seconds late
# 11/18, alacritty on a Mac in Paris recorded from Taipei: each frame took 10 s and more across the link, the last
# digit typed showed 9.8 s after the typing, and the segment (its end 3 s after the typing, at 2x) stopped before it.


def _late_events() -> list[video.Event]:
    return [video.Event(1, 0.0, 0.0, "start", "the recording starts"),
            video.Event(2, 1.0, 1.3, "type", 'pickfit types "hi"; the screen changes after it; the recording shows '
                                             "its effect only from 0:04.0", True, None, 4.0),
            video.Event(3, 6.0, 6.2, "click", "pickfit clicks at (200, 50); nothing on screen changes", False,
                        (200, 50), 6.0),
            video.Event(4, 9.0, 9.1, "key", "pickfit presses Return; the screen changes after it", True, None, 9.75)]


def test_a_segment_holds_until_the_recording_shows_what_its_actions_did():
    events = _late_events()
    assert video.span(events, 2, 2, 12.0, False) == (0.4, 5.5)  # not 1.3 + 1.5: the frame with "hi" comes at 4.0
    assert video.span(events, 2, 2, 12.0, False, faster=True) == (0.4, 5.9)  # 4.0 + 3.0, but not into the click
    assert video.span(events, 4, 4, 12.0, True) == (8.4, 12.0)  # the result stays 3 s from when it shows
    assert video.span(events, 3, 3, 12.0, False) == (5.4, 7.7)  # shown at once: as before
    plain = [video.Event(e.number, e.t, e.end, e.kind, e.what, e.changed, e.point) for e in events]
    assert video.span(plain, 2, 2, 12.0, False) == (0.4, 2.8)  # nothing known: a fixed hold after the action
    assert video.static_stretch(events, 0.4, 5.5) == pytest.approx(2.7)  # 1.3 -> 4.0: the frame with "hi" ends it
    after = [s for s in video.edit_shots(events, 12.0) if s.label == "after event 2"][0]
    assert after.at == pytest.approx(4.1)  # Claude sees the frame that shows it, not the stale one at 3.3
    assert video.logged_caption(events[1:4]) == 'Type "hi", then click, then press Return'  # the notes left out


class _Sink:
    """ffmpeg's stdin, as the recorder writes it: the frames, in order."""

    def __init__(self, path: Path) -> None:
        self.frames: list[bytes] = []
        self.returncode: int | None = None
        self.path, self.stdin = path, self

    def write(self, data: bytes) -> None:
        self.frames.append(data)

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.returncode = 0
        self.path.write_bytes(b"mp4")
        return b"", b""

    def kill(self) -> None:
        pass


class _SlowVnc:
    """A Mac across the world: a frame takes `took` seconds, its answer begins to arrive `answer` seconds in."""

    sock = None

    def __init__(self, took: float, answer: float) -> None:
        self.took, self.answer, self.n, self.answered_at = took, answer, 0, 0.0

    def capture(self) -> tuple[int, int, bytes]:
        import time

        asked = time.time()
        time.sleep(self.took)
        self.n += 1
        self.answered_at = asked + self.answer
        return 8, 6, bytes([self.n * 40 % 256, 0, 0, 0]) * 48


def test_a_slow_capture_shows_from_when_its_answer_began_to_arrive(tmp_path: Path):
    import threading
    import time

    from pickfit.verify import record

    class Box:
        os, _screen = "macos", None

    rec = record.VncRecorder(Box(), tmp_path / "r.mp4", fps=10)
    rec.rec.width, rec.rec.height = 8, 6
    sink = _Sink(tmp_path / "r.mp4")
    rec._proc = sink  # type: ignore[assignment]
    rec.rec.started_at = time.time()
    rec._thread = threading.Thread(target=rec._run, args=(_SlowVnc(0.5, 0.2), bytes(8 * 6 * 4)), daemon=True)
    rec._thread.start()
    time.sleep(2.0)
    got = rec.stop()
    assert got.error is None and got.captures == rec.captures >= 2 and len(rec.shown) == rec.captures
    shades = [frame[0] for frame in sink.frames]
    for n, shown in enumerate(rec.shown, start=1):
        first = shades.index(n * 40 % 256) / 10  # the first frame with capture n
        assert shown - 0.02 <= first <= shown + 0.1 + 0.02  # from its answer on: never before, nor when it ended
    assert 0.4 <= got.frame_gap_s <= 1.2  # a fresh frame each ~0.6 s, not each 0.1 s the fps says


def test_the_recorder_draws_a_pointer_move_only_on_frames_after_it(tmp_path: Path):
    from types import SimpleNamespace

    from pickfit.verify import record

    client = SimpleNamespace(sock=object(), pointer=(5, 5), pointer_at=100.0)
    rec = record.VncRecorder(SimpleNamespace(_screen=SimpleNamespace(_client=client)), tmp_path / "r.mp4")
    assert rec._pointer(99.0) is None  # moved at 100.0: a frame due at 99.0, written later, does not show it there
    assert rec._pointer(100.25) == (5, 5)
    client.pointer, client.pointer_at = (7, 7), 101.0
    assert rec._pointer(100.5) == (5, 5) and rec._pointer(101.0) == (7, 7)
    client.sock = None
    assert rec._pointer(102.0) is None  # no connection of pickfit's: no pointer, as before


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_the_recording_shows_an_action_from_the_first_frame_that_matches_pickfits_screenshot_after_it(tmp_path: Path):
    from PIL import Image

    plain = Image.new("RGB", (320, 200), (200, 200, 200))
    plain.paste((40, 90, 160), (60, 40, 260, 160))
    half, typed = plain.copy(), plain.copy()
    half.paste((0, 0, 0), (100, 100, 104, 112))  # the first letter: the stale frames of a slow link
    typed.paste((0, 0, 0), (100, 100, 108, 112))
    pointer = typed.copy()
    pointer.paste((255, 255, 255), (200, 50, 210, 65))  # the recorder's pointer, where pickfit clicked
    raw = tmp_path / "replay-1-1.mp4"
    _write_video(raw, [plain] * 8 + [half] * 8 + [typed] * 8 + [pointer] * 8)  # 2 s each at 4 fps
    for i, img in ((1, plain), (2, typed), (3, typed)):  # pickfit's screenshots: before each action, and the last
        img.save(tmp_path / f"replay-1-1-op-{i}.png")
    elsewhere = "/runs/moved/replay-1-1-op-{}.png"  # the run's folder moved: found by name beside the recording
    op = {"video": {"started_at": 1000.0}, "steps": [
        {"screenshot": elsewhere.format(1), "action": {"kind": "type", "text": "hi"}, "at": [1001.0, 1001.3]},
        {"screenshot": elsewhere.format(2), "action": {"kind": "click", "x": 200, "y": 50, "count": 1},
         "at": [1006.0, 1006.2]}]}
    assert video.after_shots(op, tmp_path) == [tmp_path / "replay-1-1-op-2.png", tmp_path / "replay-1-1-op-3.png"]
    assert video.after_shots(op) == [None, None]
    shown = video.shown_times(raw, op, 8.0)
    assert shown == {0: 4.0, 1: 6.0}  # "hi" whole only from 4.0; the click changed nothing (its pointer left out)
    events = video.events_of(op, [], 8.0, shown=shown)
    typing = events[1]
    assert typing.shown == 4.0 and typing.what.endswith("the recording shows its effect only from 0:04.0")
    assert video.span(events, 2, 2, 8.0, False) == (0.4, 5.5)
    assert video.shown_times(raw, {**op, "steps": [{**s, "screenshot": None} for s in op["steps"]]}, 8.0) == {}


def test_the_pointers_last_place_is_left_out_even_past_typed_text():
    looked: list[list[Any]] = []

    def did(start: float, end: float, points: list[Any], following: float) -> bool:
        looked.append(points)
        return False

    op = {"video": {"started_at": 100.0}, "steps": [
        {"action": {"kind": "click", "x": 441, "y": 170, "count": 1}, "at": [101.0, 101.2]},
        {"action": {"kind": "type", "text": "expr 1 + 2"}, "at": [103.0, 104.0]},
        {"action": {"kind": "click", "x": 393, "y": 165, "count": 1}, "at": [106.0, 106.2]}]}
    video.events_of(op, [], 10.0, changed=did)
    assert looked == [[(441, 170), None], [None, (441, 170)], [(393, 165), (441, 170)]]  # 11/18: not the typing's None


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_the_menu_bars_clock_is_not_an_action_changing_the_screen(tmp_path: Path):
    from PIL import Image

    base = Image.new("RGB", (320, 200), (200, 200, 200))
    base.paste((40, 90, 160), (60, 40, 260, 160))
    clock, letter, line = base.copy(), base.copy(), base.copy()
    for img in (clock, letter, line):
        img.paste((0, 0, 0), (280, 6, 290, 16))  # the clock in a Mac's menu bar turns a minute
    letter.paste((0, 0, 0), (100, 100, 108, 112))
    line.paste((0, 0, 0), (100, 100, 108, 112))
    line.paste((0, 0, 0), (10, 180, 310, 181))  # a thin line across the screen: no block's worth anywhere
    raw = tmp_path / "raw.mp4"
    _write_video(raw, [base] * 8 + [clock] * 8 + [letter] * 8 + [line] * 8)  # 2 s each at 4 fps
    mac = video.action_changed(raw, 8.0, "macos")
    assert not mac(1.0, 1.2, [None, None], 3.9)  # 0.75 against 3.2: only the menu bar differs
    assert mac(3.0, 3.2, [None, None], 5.9)  # a typed letter
    assert mac(5.0, 5.2, [None, None], 7.9)  # a change spread thin, but more than SPREAD_PIXELS of it
    assert video.action_changed(raw, 8.0)(1.0, 1.2, [None, None], 3.9)  # Linux has no bar: the same pixels count


# ---------------------------------------------------------------- waits cut short (a slow link repeats one picture)


def test_a_segments_waits_come_out_of_its_length_and_its_times():
    cut = video.Cut(raw=0, start=10.0, end=30.0, feature="f", caption="c", result_visible=False, faster=False,
                    waits=[(12.0, 20.0), (22.0, 25.0)])
    assert cut.kept() == [(10.0, 12.0), (20.0, 22.0), (25.0, 30.0)]
    assert cut.seconds == pytest.approx(9.0)
    assert cut.clip_at(11.0) == 1.0 and cut.clip_at(21.0) == 3.0 and cut.clip_at(26.0) == 5.0
    assert cut.clip_at(15.0) == 2.0  # a moment cut out: where the cut is
    assert [cut.raw_at(t) for t in (1.0, 2.5, 4.5, 9.0)] == [11.0, 20.5, 25.5, 30.0]
    fast = video.Cut(raw=0, start=10.0, end=30.0, feature="f", caption="c", result_visible=False, faster=True,
                     waits=[(12.0, 20.0)])
    assert fast.seconds == 6.0 and fast.clip_at(21.0) == 1.5 and fast.raw_at(1.5) == 21.0
    assert video.cut_seconds(10.0, 30.0, True, [[12.0, 20.0]]) == 6.0  # as clip.json keeps them
    before = video.Cut(raw=0, start=10.0, end=30.0, feature="f", caption="c", result_visible=True, faster=False)
    row = video.retimed_review({"caption": "c", "ok": True, "first_seen_s": 11.0, "segment_s": 20.0}, before, cut)
    assert row == {"caption": "c", "ok": True, "first_seen_s": 3.0, "segment_s": 9.0}  # 21.0 s of the recording
    assert video.retimed_review({"ok": False, "first_seen_s": -1.0}, before, cut)["first_seen_s"] == -1.0


def test_encoding_noise_is_the_same_picture_and_a_typed_letter_is_not():
    from PIL import Image

    plain = Image.new("L", (320, 200), 200)
    noisy = plain.copy()
    for i in range(67):  # 11/18: 67 pixels of noise between two frames of one still screen, scattered
        noisy.putpixel(((i * 37) % 320, (i * 53) % 200), 120)
    letter = plain.copy()
    letter.paste(0, (100, 100, 108, 112))
    assert video.looks_same(plain, noisy) and not video.looks_same(plain, letter)
    assert video.looks_same(plain, letter, [(90, 90, 120, 120)])  # under pickfit's pointer


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_wait_is_cut_short_and_nothing_is_added_or_reordered(tmp_path: Path):
    from PIL import Image

    def screen(color: tuple[int, int, int]) -> Any:
        img = Image.new("RGB", (320, 200), (200, 200, 200))
        img.paste(color, (60, 40, 260, 160))
        return img

    a, b, c = screen((40, 90, 160)), screen((160, 60, 40)), screen((40, 150, 60))
    raw = tmp_path / "raw.mp4"
    _write_video(raw, [a] * 24 + [b] * 4 + [c] * 16)  # 6 s still, 1 s, then 4 s of the result
    cut = video.Cut(raw=0, start=0.0, end=11.0, feature="f", caption="c", result_visible=True, faster=False)
    cut.waits = video.still_waits(raw, cut, None)
    assert cut.waits == [(video.STILL_HOLD_S, 6.0)]  # the first 1.5 s kept; the 1 s picture and the result whole
    assert cut.seconds == pytest.approx(6.5)
    assert video.still_waits(raw, video.Cut(0, 0.0, 11.0, "f", "c", True, True), None) == [(3.0, 6.0)]  # 2x: 1.5 s
    piece = tmp_path / "piece.mp4"
    video.render_piece(raw, cut, None, (320, 200), None, piece)
    assert record.probe_seconds(piece) == pytest.approx(6.5, abs=0.3)
    seen = []
    for t in [i / video.FPS for i in range(int(6.4 * video.FPS))]:
        px = Image.open(io.BytesIO(record.png_frame(piece, t))).convert("RGB").getpixel((640, 422))
        name = min("abc", key=lambda k: sum(abs(p - q) for p, q in zip(px, {"a": (40, 90, 160), "b": (160, 60, 40),
                                                                                   "c": (40, 150, 60)}[k])))
        assert sum(abs(p - q) for p, q in zip(px, {"a": (40, 90, 160), "b": (160, 60, 40), "c": (40, 150, 60)}[name])) < 40
        seen.append(name)  # every frame one of the three pictures: no fade between them
    order = [k for i, k in enumerate(seen) if i == 0 or seen[i - 1] != k]
    assert order == ["a", "b", "c"] and seen.count("a") <= (video.STILL_HOLD_S + 0.3) * video.FPS


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_a_made_clip_is_cut_again_without_its_waits_and_keeps_its_review(tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch):
    from types import SimpleNamespace

    from PIL import Image

    def screen(color: tuple[int, int, int]) -> Any:
        img = Image.new("RGB", (320, 200), (200, 200, 200))
        img.paste(color, (60, 40, 260, 160))
        return img

    videos = tmp_path / "videos"
    monkeypatch.setenv("PICKFIT_VIDEOS", str(videos))
    monkeypatch.setattr(video, "clip_source", lambda d, s, data_dir=None: (
        {"slug": "app", "os": "macos", "runner": "tart-vz"}, "App", SimpleNamespace(id="verify-app-1")))
    monkeypatch.setattr(video, "call_meta", lambda *a, **k: pytest.fail("no model call"))
    (videos / "app").mkdir(parents=True)
    raw = videos / "app" / "app-20261118-1200-raw-1.mp4"
    _write_video(raw, [screen((40, 90, 160))] * 40 + [screen((40, 150, 60))] * 16)  # 10 s still, then 4 s
    run_dir = tmp_path / "runs" / "video-app-1"
    run_dir.mkdir(parents=True)
    (run_dir / "replay.json").write_text(json.dumps({"video": {"slug": "app", "run": "verify-app-1"}}))
    cut = video.Cut(raw=0, start=0.0, end=14.0, feature="open the app", caption="The app shows its window",
                    result_visible=True, faster=False, events=(1, 2))
    row = {"file": raw.name, "sha256": record.sha256_file(raw), "seconds": 14.0, "smoke_test": 1, "feature": "open the app"}
    review = {"caption": cut.caption, "ok": True, "seen": True, "first_seen_s": 10.5, "segment_s": 14.0, "why": "w",
              "unmentioned": ""}
    made = video.ClipResult(slug="app", run="verify-app-1", recording_run="video-app-1", clip="app-20261118-1200.mp4",
                            clip_sha256="x", seconds=21.0, raw=[row], cuts=[video.asdict(cut)], crops=[None],
                            review=[review], model=PROD_MODEL, recorded_at="2026-11-18T12:00:00+08:00")
    video.save_clip(made, run_dir / "clip.json")
    before = (run_dir / "clip.json").read_text()

    out = video.smooth_clip(run_dir, log=lambda *a: None)
    assert out.clip == "app-20261118-1200.recut.mp4" and out.retimed_from == "app-20261118-1200.mp4"
    assert [list(w) for w in out.cuts[0]["waits"]] == [[1.5, 10.0]] and "8 s of unchanged screen cut" in out.cuts[0]["note"]
    assert out.review[0]["ok"] and out.review[0]["first_seen_s"] == 2.0 and out.review[0]["segment_s"] == 5.5
    assert out.seconds == pytest.approx(5.5, abs=0.3) and not out.flags and not out.cards and out.os == "macos"
    assert out.chapters == [{"start_s": 0.0, "title": "Open the app", "feature": "open the app", "raw": 0, "raw_s": 0.0}]
    assert out.captions == [{"start_s": 0.0, "end_s": pytest.approx(out.seconds, abs=0.15),
                             "text": "The app shows its window"}]
    assert (videos / "app" / out.clip).is_file() and record.sha256_file(videos / "app" / out.clip) == out.clip_sha256
    saved = json.loads((videos / "app" / "app-20261118-1200.recut.json").read_text())
    assert saved["clip"] == out.clip and not saved["flagged"] and saved["cards"] is False
    assert (run_dir / "clip.json").read_text() == before  # the clip it came from is left as it was
    from PIL import Image

    with Image.open(videos / "app" / "app-20261118-1200.recut.jpg") as poster:  # a clean frame of the raw recording
        assert poster.size == (1280, 800) and poster.getpixel((640, 400))[1] > 120  # the result, green
    frame = Image.open(io.BytesIO(record.png_frame(videos / "app" / out.clip, 1.0))).convert("RGB")
    corner = [frame.getpixel((x, y)) for x in range(1120, 1270, 2) for y in range(16, 60, 2)]
    assert any(min(px) > 200 for px in corner)  # "−8 s", white on its pill in the top right corner
    assert not any(min(frame.getpixel((x, y))) > 200 for x in range(10, 300, 4) for y in range(16, 60, 4))
    assert (videos / "app" / "app-20261118-1200.actions.json").is_file()  # from the saved events, for a later cut
