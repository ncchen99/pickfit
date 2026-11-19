"""Verification videos since 11/19: pickfit's action log beside the raw recordings (actions.json), the rules' edit
and its review by frame match, the honesty marks, ripples and keycaps from the log, and the clip's captions and
chapters as the record keeps them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pickfit.schema import RunVideo
from pickfit.verify import video
from pickfit.verify.video import Event

T0 = 1000.0
NEW_SCHEMA = "captions" in RunVideo.model_fields  # loop/proposals/video-captions.patch applied


def _op(**over: Any) -> dict[str, Any]:
    """A recorded operation: click the password field, type into it, press cmd+s, done."""
    steps = [
        {"action": {"kind": "click", "x": 300, "y": 200, "count": 1}, "at": [T0 + 2.0, T0 + 2.1], "why": "",
         "observation": "", "target": {"name": "Password", "source": "ocr"}, "screenshot": None},
        {"action": {"kind": "type", "text": "hunter2-x7"}, "at": [T0 + 3.0, T0 + 3.6], "why": "", "observation": ""},
        {"action": {"kind": "key", "name": "cmd+s"}, "at": [T0 + 5.0, T0 + 5.1], "why": "save it",
         "observation": "the database is open"},
        {"action": {"kind": "done"}, "why": "saved"},
    ]
    return {"goal": "Create a database", "nonce": "n0", "steps": steps, "video": {"started_at": T0}, "passed": True,
            "result": {"line": "file saved"}, "check": {"kind": "file"}} | over


def _events() -> list[Event]:
    return [Event(1, 0.5, 0.5, "start", "the recording starts"),
            Event(2, 1.0, 1.0, "change", "the screen changes"),
            Event(3, 2.0, 2.1, "click", "pickfit clicks", True, (300, 200), 2.3, step=0),
            Event(4, 3.0, 3.6, "type", 'pickfit types "hunter2-x7"', True, None, 3.8, step=1),
            Event(5, 5.0, 5.1, "key", "pickfit presses cmd+s", True, None, 5.5, step=2),
            Event(6, 5.4, 5.4, "change", "the screen changes")]


def test_the_action_log_keeps_each_action_with_its_time_target_and_why_and_masks_a_password():
    rows, secrets = video.action_rows(_op(), _events(), os="macos")
    assert [r["step"] for r in rows] == [1, 2, 3] and [r["kind"] for r in rows] == ["click", "type", "key"]
    assert rows[0] == {"step": 1, "kind": "click", "start_s": 2.0, "end_s": 2.1, "x": 300, "y": 200, "count": 1,
                       "target": {"name": "Password", "source": "ocr"}, "why": "", "saw": "", "changed": True,
                       "shown_s": 2.3}
    assert rows[1]["text"] is None and rows[1]["masked"] and rows[1]["chars"] == 10 and rows[1]["secret"] == "password"
    assert secrets == ["hunter2-x7"]
    assert rows[2]["key"] == "cmd+s" and rows[2]["why"] == "save it" and rows[2]["saw"] == "the database is open"
    assert "window" not in rows[0]  # a Mac's screenshot is the whole desktop: no window from it
    text = video.redact(json.dumps({"events": ['pickfit types "hunter2-x7"'], "goal": "x"}), secrets)
    assert "hunter2" not in text and video.MASK in text


def test_a_replays_actions_take_the_operators_notes_from_the_operated_run(tmp_path: Path):
    actions = [{"kind": "click", "x": 300, "y": 200, "count": 1}, {"kind": "type", "text": "{nonce}"}]
    operated = {"actions": actions, "steps": [
        {"action": {"kind": "click", "x": 300, "y": 200, "count": 1}, "why": "open the name field",
         "observation": "a form", "target": {"name": "Name", "source": "operator"}},
        {"action": None, "refused": "no mark 9"},
        {"action": {"kind": "type", "text": "abc"}, "why": "name it", "observation": "the field has focus"},
        {"action": {"kind": "done"}, "why": "done"}]}
    (tmp_path / "report.json").write_text(json.dumps({"commands": [{"operate": {"actions": [], "steps": []}},
                                                                   {"operate": operated}]}))
    notes = video.operator_notes(tmp_path, actions)
    assert notes == [{"why": "open the name field", "saw": "a form", "target": {"name": "Name", "source": "operator"}},
                     {"why": "name it", "saw": "the field has focus", "target": None}]
    assert video.operator_notes(tmp_path, actions[:1]) == [None]  # no operated run with exactly these actions
    assert video.operator_notes(None, actions) == [None, None]
    op = _op()
    for step in op["steps"]:
        step.pop("target", None)
    rows, _ = video.action_rows(op, notes=[{"why": "w", "saw": "s", "target": {"name": "Field", "source": "operator"}}])
    assert rows[0]["target"] == {"name": "Field", "source": "operator"} and rows[0]["why"] == "w"


def test_a_linux_action_keeps_the_part_of_the_screen_the_app_drew_on(tmp_path: Path):
    from PIL import Image

    shot = tmp_path / "op-1.png"
    img = Image.new("RGB", (1280, 800), (0, 0, 0))
    img.paste((200, 200, 200), (100, 50, 700, 450))
    img.save(shot)
    op = _op()
    op["steps"][0]["screenshot"] = str(shot)
    rows, _ = video.action_rows(op, os="linux")
    assert rows[0]["window"] == [100, 50, 600, 400] and rows[1]["window"] is None


def test_a_web_inputs_field_is_a_textbox_named_by_the_page():
    op = {"web": True, "video": {"started_at": T0}, "steps": [
        {"action": {"kind": "click", "x": 250, "y": 220, "label": "Job link"}, "at": [T0 + 1, T0 + 1]},
        {"action": {"kind": "type", "text": "https://example.com/x"}, "at": [T0 + 1, T0 + 2]}]}
    rows, secrets = video.action_rows(op)
    assert rows[0]["target"] == {"name": "Job link", "source": "dom", "role": "textbox"}
    assert rows[1]["text"] == "https://example.com/x" and not secrets


def test_the_rules_cut_the_opening_and_each_action_that_changed_the_screen():
    events = [Event(1, 0.5, 0.5, "start", "s"), Event(2, 1.0, 1.0, "change", "c"),
              Event(3, 6.0, 6.1, "click", "pickfit clicks", True, (10, 10), 6.3, step=0),
              Event(4, 6.6, 6.6, "change", "c"),
              Event(5, 12.0, 12.1, "click", "pickfit clicks", False, (20, 20), None, step=1),  # changed nothing
              Event(6, 20.0, 20.5, "type", "pickfit types", True, None, 20.7, step=2),
              Event(7, 21.0, 21.0, "change", "c")]
    rows = [{"step": 1, "kind": "click", "target": {"name": "New", "source": "ocr"}},
            {"step": 2, "kind": "click"}, {"step": 3, "kind": "type", "text": "hello"}]
    cuts = video.rule_cuts(events, rows, 30.0, 0, "write a note", "Start Notes")
    assert [(c.start, c.end) for c in cuts] == [(0.5, 2.5), (5.4, 8.1), (19.4, 23.7)]
    assert [c.caption for c in cuts] == ["Start Notes", "Click “New”", 'Type "hello"']
    assert [c.result_visible for c in cuts] == [False, False, True] and not any(c.faster for c in cuts)
    assert all(c.feature == "write a note" and c.raw == 0 for c in cuts)
    video.gaps_before(cuts, {0: 0.5})
    assert [c.gap_before for c in cuts] == [0.0, 2.9, 11.3]  # left out before each: marked "−3 s", "−11 s"
    # close together, two actions are one segment, captioned with both
    near = [Event(1, 0.0, 0.0, "start", "s"), Event(2, 0.2, 0.2, "change", "c"),
            Event(3, 1.0, 1.1, "click", "c", True, (1, 1), 1.3, step=0),
            Event(4, 2.5, 2.6, "key", "k", True, None, 2.8, step=1)]
    one = video.rule_cuts(near, [{"step": 1, "kind": "click"}, {"step": 2, "kind": "key", "key": "Return"}], 6.0, 0,
                          "f", "Start App")
    assert len(one) == 1 and one[0].caption == "Start App, then click, then press Enter" and one[0].result_visible


def test_a_long_rules_segment_is_captioned_action_by_action():
    events = [Event(1, 0.0, 0.0, "start", "s"), Event(2, 0.3, 0.3, "change", "c"),
              Event(3, 1.0, 1.1, "click", "c", True, (1, 1), 1.3, step=0),
              Event(4, 2.5, 2.6, "key", "k", True, None, 2.8, step=1),
              Event(5, 3.5, 4.0, "type", "t", True, None, 4.2, step=2)]
    rows = [{"step": 1, "kind": "click", "target": {"name": "Open", "source": "ocr"}},
            {"step": 2, "kind": "key", "key": "cmd+shift+g"}, {"step": 3, "kind": "type", "text": "~/in"}]
    [cut] = video.rule_cuts(events, rows, 9.0, 0, "f", "Start App", "macos")
    assert cut.caption == 'Start App, then click “Open”, then press ⇧⌘G, then type "~/in"'  # for its review
    assert cut.cues == [(0.0, "Start App"), (0.7, "Click “Open”"), (2.2, "Press ⇧⌘G"), (3.2, 'Type "~/in"')]
    cues = video.caption_cues([cut], [10.0], [cut.seconds])
    assert [(c["start_s"], c["text"]) for c in cues] == [(10.0, "Start App"), (10.7, "Click “Open”"),
                                                          (12.2, "Press ⇧⌘G"), (13.2, 'Type "~/in"')]
    assert cues[-1]["end_s"] == pytest.approx(10.0 + cut.seconds) and cues[0]["end_s"] == 10.7


def test_a_rules_segment_passes_when_the_recording_shows_pickfits_screenshot_after_each_action():
    events = _events()
    cut = video.Cut(0, 1.4, 6.5, "f", "c", True, False)
    row = video.frame_review(cut, events)
    assert row["ok"] and row["how"] == "frames" and (row["matched"], row["of"]) == (3, 3)
    assert row["first_seen_s"] == pytest.approx(0.9)
    late = [replace_shown(e, None) if e.number == 4 else e for e in events]  # the typing never shows as pickfit saw it
    row = video.frame_review(cut, late)
    assert not row["ok"] and "1 of its 3 actions" in row["why"]
    opening = video.frame_review(video.Cut(0, 0.5, 1.9, "f", "Start App", False, False), events)
    assert opening["ok"] and opening["of"] == 1  # the app appearing: a change on screen in it
    assert video.review_sampled("video-x-1", 100) and not video.review_sampled("video-x-1", 0)
    assert video.review_sampled("video-x-1", 50) == video.review_sampled("video-x-1", 50)


def replace_shown(event: Event, shown: float | None) -> Event:
    from dataclasses import replace

    return replace(event, shown=shown)


def test_a_rules_clip_sends_opus_only_what_the_frame_match_cannot_settle(monkeypatch: pytest.MonkeyPatch,
                                                                        tmp_path: Path):
    """_make_clip's review step, as review_cuts sees it: unmatched segments only, unless the clip is sampled."""
    asked: list[list[str]] = []

    def fake_review(pieces: Any, cuts: Any, scope: Any, log: Any, editor: Any, frames: Any) -> Any:
        asked.append([c.caption for c in cuts])
        return [{"caption": c.caption, "ok": True, "seen": True, "first_seen_s": 0.2, "segment_s": c.seconds,
                 "why": "w", "unmentioned": ""} for c in cuts], [], 0.01

    monkeypatch.setattr(video, "review_cuts", fake_review)
    events = _events()
    good = video.Cut(0, 1.4, 6.5, "f", "good", True, False)
    bad = video.Cut(0, 1.4, 6.5, "f", "bad", True, False)
    rows = [video.frame_review(good, events), video.frame_review(bad, [replace_shown(e, None) for e in events])]
    assert [r["ok"] for r in rows] == [True, False]
    assert [i for i, r in enumerate(rows) if not r["ok"]] == [1]  # what _make_clip asks Opus about, unsampled


def test_the_overlays_land_where_pickfit_clicked_and_show_the_keys_it_pressed():
    from pickfit.verify import video_marks

    cut = video.Cut(0, 10.0, 20.0, "f", "c", True, True, waits=[(12.0, 15.0)])
    actions = [{"kind": "click", "x": 300, "y": 200, "start_s": 11.0},
               {"kind": "click", "x": 50, "y": 50, "start_s": 16.0},  # outside the part of the screen the clip shows
               {"kind": "key", "key": "cmd+shift+g", "start_s": 16.0}, {"kind": "key", "key": "Return", "start_s": 16.5},
               {"kind": "click", "x": 300, "y": 200, "start_s": 25.0}]  # after the segment
    ovs = video.piece_overlays(cut, actions, (200, 100, 640, 400), (1280, 800), "macos")
    rings = [o for o in ovs if o.y < video.H - 120]
    keys = [o for o in ovs if o.y >= video.H - 120]
    stages = len(video_marks.RIPPLE_STAGES)
    assert len(rings) == stages and rings[0].start == pytest.approx(0.5)  # 1 s in, at 2x
    _, r = video_marks.ripple_pngs()[0]
    assert (rings[0].x + r, rings[0].y + r) == (200, 200)  # (300-200)*2, (200-100)*2: the crop at twice its size
    assert [k.start for k in keys] == [pytest.approx(cut.clip_at(16.0)), pytest.approx(cut.clip_at(16.5))]
    assert keys[0].end == pytest.approx(keys[1].start)  # the next keys replace them
    assert video.piece_overlays(cut, actions, None, (1280, 800), "macos", ripples=False)[0].y >= video.H - 120
    assert video_marks.key_caps("cmd+shift+g", "macos") == ["⇧", "⌘", "G"]
    assert video_marks.key_caps("ctrl+alt+Delete", "linux") == ["Ctrl", "Alt", "Del"]


def test_a_clips_saved_events_give_its_actions_for_a_later_cut():
    saved = [{"kind": "start", "t": 0.5, "what": "s"},
             {"kind": "click", "t": 2.0, "end": 2.1, "what": "pickfit double-clicks at (5, 6)", "point": [5, 6]},
             {"kind": "key", "t": 3.0, "end": 3.1, "what": "pickfit presses cmd+shift+g; the screen changes after it"},
             {"kind": "change", "t": 3.2, "what": "c"}]
    assert video.legacy_actions(saved) == [
        {"kind": "click", "start_s": 2.0, "end_s": 2.1, "x": 5, "y": 6, "button": None, "count": 2},
        {"kind": "key", "start_s": 3.0, "end_s": 3.1, "key": "cmd+shift+g"}]


def test_a_clip_cut_before_the_action_log_masks_what_it_typed_into_a_password_field():
    clip = video.ClipResult(slug="s", run="r", recording_run="v", raw=[{"file": "r.mp4"}],
                            cuts=[{"raw": 0, "start": 0.0, "end": 5.0, "caption": "Type the same password in Confirm"},
                                  {"raw": 0, "start": 5.0, "end": 9.0, "caption": "Name the file vault.kdbx"}],
                            events=[{"raw": "r.mp4", "events": [
                                {"kind": "type", "t": 1.0, "what": 'pickfit types "s3cret-Pass!"; the screen changes'},
                                {"kind": "type", "t": 6.0, "what": 'pickfit types "vault.kdbx"'}]}])
    assert video.typed_secrets(clip) == ["s3cret-Pass!"]


def _clip(tmp_path: Path) -> tuple[video.ClipResult, Path]:
    folder = tmp_path / "videos" / "app"
    folder.mkdir(parents=True)
    files = {}
    for name in ("app-20261119-1000.mp4", "app-20261119-1000-raw-1.mp4", "app-20261119-1000.jpg",
                 "app-20261119-1000.actions.json"):
        (folder / name).write_bytes(name.encode() * 20)
        files[name] = hashlib.sha256(name.encode() * 20).hexdigest()
    clip = video.ClipResult(
        slug="app", run="verify-app-20261119-000000-0000", recording_run="video-app-20261119-000000-0000",
        clip="app-20261119-1000.mp4", clip_sha256=files["app-20261119-1000.mp4"], seconds=12.0,
        raw=[{"file": "app-20261119-1000-raw-1.mp4", "sha256": files["app-20261119-1000-raw-1.mp4"], "seconds": 30.0,
              "smoke_test": 1, "feature": "write a note"}],
        cuts=[{"raw": 0, "start": 1.0, "end": 13.0, "result_visible": True, "faster": False, "caption": "c"}],
        features=["write a note"], model=video.RULES_MODEL, recorded_at="2026-11-19T10:00:00+08:00", cards=False,
        chapters=[{"start_s": 0.0, "title": "Write a note", "feature": "write a note", "raw": 0, "raw_s": 1.0}],
        captions=[{"start_s": 0.0, "end_s": 12.0, "text": "Type \"hello\""}], actions="app-20261119-1000.actions.json")
    video.save_clip(clip, tmp_path / "clip.json")  # beside it in PICKFIT_VIDEOS too
    return clip, folder


def test_an_uploaded_clip_takes_its_edit_list_and_action_log_along(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_VIDEOS", str(tmp_path / "videos"))
    clip, folder = _clip(tmp_path)
    objects: dict[str, bytes] = {}

    def wrangler(args: list[str]) -> bytes:  # a fake: nothing leaves this machine
        if args[2] == "put":
            objects[args[3]] = Path(args[args.index("--file") + 1]).read_bytes()
            return b""
        return objects[args[3]]

    sent = video.upload(clip, video.run_video(clip, folder=folder), folder, wrangler=wrangler)
    assert sorted(objects) == sorted(f"pickfit-videos/app/app-20261119-1000{s}" for s in
                                     (".actions.json", ".jpg", ".json", "-raw-1.mp4", ".mp4"))
    assert ("app/app-20261119-1000.json", len((folder / "app-20261119-1000.json").read_bytes())) in sent


@pytest.mark.skipif(not NEW_SCHEMA, reason="needs loop/proposals/video-captions.patch applied to pickfit/schema.py")
def test_a_runs_video_carries_its_captions_chapters_and_where_to_cut_it_again(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_VIDEOS", str(tmp_path / "videos"))
    clip, folder = _clip(tmp_path)
    got = video.run_video(clip, folder=folder).model_dump(mode="json")
    assert got["captions"] == [{"start_s": 0.0, "end_s": 12.0, "text": 'Type "hello"'}]
    assert got["chapters"] == [{"start_s": 0.0, "title": "Write a note", "feature": "write a note", "raw": 0,
                                "raw_s": 1.0}]
    assert got["actions"] == {"key": "app/app-20261119-1000.actions.json",
                              "sha256": hashlib.sha256(b"app-20261119-1000.actions.json" * 20).hexdigest()}
    assert got["edit_list"]["key"] == "app/app-20261119-1000.json"
    with pytest.raises(ValueError, match="captions must rise"):
        RunVideo.model_validate(got | {"captions": [{"start_s": 5.0, "end_s": 4.0, "text": "x"}]})
    with pytest.raises(ValueError, match="index into video.raw"):
        RunVideo.model_validate(got | {"chapters": [got["chapters"][0] | {"raw": 3}]})
    legacy = got | {"chapters": [{"start_s": 0.0, "title": "Recorded by pickfit", "feature": None},
                                 {"start_s": 3.5, "title": "Write a note", "feature": "write a note"},
                                 {"start_s": 10.0, "title": "Unedited recordings", "feature": None}]}
    assert len(RunVideo.model_validate(legacy).chapters) == 3  # a clip cut before 11/19 keeps its cards


@pytest.mark.skipif(NEW_SCHEMA, reason="the schema before loop/proposals/video-captions.patch")
def test_before_the_schema_takes_captions_a_clip_without_cards_is_written_without_chapters(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_VIDEOS", str(tmp_path / "videos"))
    clip, folder = _clip(tmp_path)
    got = video.run_video(clip, folder=folder).model_dump(mode="json")
    assert "chapters" not in got and "captions" not in got and got["clip"] == clip.clip


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_rules_make_a_clip_with_no_model_call_and_an_action_log_beside_it(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch):
    import subprocess
    from types import SimpleNamespace

    from PIL import Image

    def screen(color: tuple[int, int, int] | None) -> Any:
        img = Image.new("RGB", (320, 200), (0, 0, 0))  # Xvfb: black until the app draws
        if color:
            img.paste((200, 200, 200), (40, 20, 280, 180))
            img.paste(color, (80, 60, 240, 140))
        return img

    # as bright as each other differently enough to show in gray, as pickfit's change measures look
    blue, red, green = screen((30, 60, 200)), screen((230, 40, 40)), screen((40, 220, 60))
    run_dir = tmp_path / "runs" / "video-app-20261119-100000-0001"
    run_dir.mkdir(parents=True)
    raw = run_dir / "replay-1.mp4"
    frames = [screen(None)] * 10 + [blue] * 40 + [red] * 40 + [green] * 30  # at 10 fps: 1 s, 4 s, 4 s, 3 s
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-video_size",
                             "320x200", "-framerate", "10", "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt",
                             "yuv420p", str(raw)], stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    for k, img in enumerate((blue, red, green, green), start=1):  # pickfit's screenshot before each step, the check's
        img.save(run_dir / f"replay-1-op-{k}.png")
    t0 = 1_794_000_000.0
    op = {"goal": "Write a note", "nonce": "n1", "passed": True, "mode": "actions", "result": {"line": "screen: green"},
          "check": {"kind": "screen_text", "expected": []}, "actions": [],
          "video": {"path": str(raw), "sha256": video.recording.sha256_file(raw), "seconds": 12.0, "started_at": t0,
                    "width": 320, "height": 200, "fps": 10, "crf": 22, "pointer": "arrow"},
          "steps": [{"action": {"kind": "click", "x": 160, "y": 100, "count": 1}, "at": [t0 + 4.9, t0 + 5.0],
                     "screenshot": str(run_dir / "replay-1-op-1.png"), "why": "", "observation": "",
                     "target": {"name": "New note", "source": "operator"}},
                    {"action": {"kind": "key", "name": "ctrl+s"}, "at": [t0 + 8.9, t0 + 9.0],
                     "screenshot": str(run_dir / "replay-1-op-2.png"), "why": "", "observation": ""},
                    {"action": {"kind": "done"}, "screenshot": str(run_dir / "replay-1-op-3.png"), "why": "saved"}]}
    (run_dir / "replay.json").write_text(json.dumps({"video": {"slug": "app"}, "result": {"checks": [
        {"run": {"operate": op}}]}}))
    theirs = SimpleNamespace(goal="Write a note", passed=True, smoke_test=2)
    run = SimpleNamespace(id="verify-app-20261119-000000-0000", gui=SimpleNamespace(operations=[theirs]), web=None,
                          features=[SimpleNamespace(feature="write a note", status="checked", smoke_tests=[2])])
    monkeypatch.setattr(video, "clip_source", lambda d, s, data_dir=None: (
        {"slug": "app", "run": run.id, "os": "linux", "runner": "modal"}, "Notes", run))
    monkeypatch.setattr(video, "call_meta", lambda *a, **k: pytest.fail("no model call"))
    settings = {"PICKFIT_VIDEOS": str(tmp_path / "videos"), "PICKFIT_VIDEO_REVIEW_SAMPLE": "0"}
    monkeypatch.setattr(video, "get_env", lambda name, default=None: settings.get(name))

    out = video.make_clip(run_dir, editor=video.EDITORS["rules"], log=lambda *a: None)
    assert not out.flags, out.flags
    assert out.model == video.RULES_MODEL and out.cost_usd == 0 and not out.cards and out.os == "linux"
    assert [c["caption"] for c in out.cuts] == ["Start Notes", "Click the New note", "Press Ctrl+S"]
    assert all(r["ok"] and r["how"] == "frames" for r in out.review)
    assert out.chapters == [{"start_s": 0.0, "title": "Write a note", "feature": "write a note", "raw": 0,
                             "raw_s": out.cuts[0]["start"]}]
    assert [c["text"] for c in out.captions] == ["Start Notes", "Click the New note", "Press Ctrl+S"]
    folder = tmp_path / "videos" / "app"
    log = json.loads((folder / out.actions).read_text())
    assert log["format"] == video.ACTIONS_FORMAT and log["recordings"][0]["pointer"] == "arrow"
    acts = log["recordings"][0]["actions"]
    assert [(a["kind"], a["start_s"]) for a in acts] == [("click", 4.9), ("key", 8.9)]
    assert [c["gap_before"] for c in out.cuts] == [0.0, pytest.approx(4.3 - 2.5), pytest.approx(8.3 - 6.5)]
    assert acts[0]["window"] == [40, 20, 240, 160] and acts[0]["changed"] and acts[0]["shown_s"] is not None
    assert (folder / out.clip).is_file() and (folder / f"{Path(out.clip).stem}.jpg").is_file()
    assert json.loads((folder / Path(out.clip).with_suffix(".json").name).read_text())["captions"] == out.captions
