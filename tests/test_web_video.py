"""Web app verification videos: the action log as steps, the raw recording from screencast frames, the harness's
frame thinning, the schema on a web run."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from pickfit.schema import SoftwareRecord
from pickfit.verify import record, web_harness, web_video

FFMPEG = shutil.which("ffmpeg")
REPO = Path(__file__).resolve().parents[1]
TESSERA = REPO / "data" / "software" / "tessera.json"


def test_the_action_log_becomes_clicks_typing_keys_and_scrolls():
    log = [{"t0": 10.0, "t1": 11.0, "actions": {"input": {"index": 15, "text": "https://example.com/x", "clear": True}},
            "box": [100, 200, 300, 40], "label": "Job link"},
           {"t0": 13.0, "t1": 13.5, "actions": {"click": {"index": 57}}, "box": [900, 100, 120, 30],
            "label": "Download PNG"},
           {"t0": 15.0, "t1": 15.2, "actions": {"send_keys": {"keys": "Enter"}}},
           {"t0": 16.0, "t1": 16.4, "actions": {"scroll": {"down": False}}},
           {"t0": 17.0, "t1": 17.1, "actions": {"navigate": {"url": "https://example.com"}}},
           {"t0": 18.0, "t1": 18.5, "actions": {"upload_file": {"index": 3, "path": "/home/web/samples/sample.txt"}},
            "label": "Select files"}]
    steps = web_video.steps_of(log, (1280, 900))
    assert [s["action"] for s in steps] == [
        {"kind": "click", "x": 250, "y": 220, "label": "Job link"},
        {"kind": "type", "text": "https://example.com/x"},
        {"kind": "click", "x": 960, "y": 115, "label": "Download PNG"},
        {"kind": "key", "name": "Enter"},
        {"kind": "scroll", "direction": "up", "x": 640, "y": 450},
        {"kind": "click", "label": "Select files, choosing pickfit's sample.txt"}]
    assert steps[0]["at"] == [10.0, 10.0] and steps[1]["at"] == [10.0, 11.0]


def test_a_web_action_is_logged_with_its_place_and_the_controls_words():
    from pickfit.verify import video

    op = {"web": True, "video": {"started_at": 100.0},
          "steps": [{"action": {"kind": "click", "x": 960, "y": 115, "label": "Download PNG"}, "at": [103.0, 103.5]},
                    {"action": {"kind": "click", "label": "Menu"}, "at": [104.0, 104.2]}],
          "result": {"line": "tessera-url.png (100 bytes) arrived"}, "passed": True}
    lines, _ = video.action_log(op)
    assert lines[0] == "0:00.0 recording starts; the browser opens the page"
    assert lines[1] == '0:03.0 click at (960, 115) on "Download PNG"' and lines[2] == '0:04.0 click on "Menu"'
    events = video.events_of(op, [], 10.0)
    assert "the browser is about to open the page" in events[0].what
    assert [e.what for e in events if e.kind == "click"] == ['pickfit clicks at (960, 115) on "Download PNG"',
                                                             'pickfit clicks on "Menu"']


def test_the_harness_keeps_one_frame_per_gap_and_a_bursts_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web_harness, "FRAMES", tmp_path)
    acks: list[int] = []

    class Send:
        class Page:
            @staticmethod
            async def screencastFrameAck(params: dict[str, Any], session_id: str | None = None) -> None:
                acks.append(params["sessionId"])

    class Session:
        class cdp_client:
            send = Send

    async def go() -> None:
        cast = web_harness.Screencast(Session())
        for n, t in enumerate([0.0, 0.05, 0.1, 1.0, 1.05]):
            cast.on_frame({"data": "aGk=", "metadata": {"timestamp": 100 + t}, "sessionId": n}, "s")
        await asyncio.sleep(0)
        assert [round(f["t"] - 100, 2) for f in cast.frames] == [0.0, 0.1, 1.0]  # 0.05 gave way to 0.1
        assert cast.pending is not None and round(cast.pending[0] - 100, 2) == 1.05
        assert acks == [0, 1, 2, 3, 4]  # every frame acknowledged, kept or not

    asyncio.run(go())
    assert (tmp_path / "f00000.jpg").read_bytes() == b"hi"


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_the_raw_recording_holds_each_paint_and_draws_the_pointer(tmp_path: Path):
    from PIL import Image

    for name, color in (("a.jpg", (255, 255, 255)), ("b.jpg", (20, 120, 200))):
        Image.new("RGB", (320, 240), color).save(tmp_path / name)
    index = {"viewport": [320, 240], "stopped_at": 103.0,
             "frames": [{"t": 100.4, "file": "a.jpg"}, {"t": 101.6, "file": "b.jpg"}]}
    out = tmp_path / "raw.mp4"
    seconds = web_video.encode_raw(tmp_path, index, 100.0, [(102.0, 160, 120)], out)
    assert seconds == pytest.approx(3.25)
    assert record.probe_seconds(out) == pytest.approx(3.25, abs=0.3)
    import io

    def pixel(at: float, xy: tuple[int, int]) -> tuple[int, ...]:
        return Image.open(io.BytesIO(record.png_frame(out, at))).convert("RGB").getpixel(xy)

    assert pixel(1.0, (10, 10))[0] > 200  # the first paint, held
    assert pixel(2.5, (10, 10))[2] > 150 and pixel(2.5, (10, 10))[0] < 80  # the second
    assert min(pixel(2.5, (162, 130))) > 180  # the arrow's white inside, drawn from the click at 2.0 s on


@pytest.mark.skipif(not TESSERA.exists(), reason="needs data/software/tessera.json")
def test_a_web_runs_video_must_show_one_of_its_passed_operations():
    data = json.loads(TESSERA.read_text(encoding="utf-8"))
    run = data["verification"]["runs"][0]
    video = {"clip": "tessera-20261102-2200.mp4", "clip_sha256": "a" * 64, "seconds": 30.0,
             "raw": [{"file": "tessera-20261102-2200-raw-1.mp4", "sha256": "b" * 64, "seconds": 40.0, "smoke_test": 1}],
             "recorded_at": "2026-11-02T22:00:00+08:00", "recording_run": "video-tessera-20261102-220000-ab12",
             "model": "meta-models/Muse-Spark-Open-816B-A42B", "features": ["generate QR codes for nine content types"]}
    run["video"] = video
    assert SoftwareRecord.model_validate(data).verification.runs[0].video.raw[0].smoke_test == 1
    run["video"] = {**video, "raw": [{**video["raw"][0], "smoke_test": 0}]}  # the page load, not an operation
    with pytest.raises(ValueError, match="operation that passed"):
        SoftwareRecord.model_validate(data)


def test_frames_json_is_the_vms_word_and_only_harness_names_and_a_bounded_end_are_used(tmp_path: Path):
    (tmp_path / "f00000.jpg").write_bytes(b"x")
    (tmp_path / "f00001.jpg").write_bytes(b"x")
    index = {"frames": [{"t": 100.5, "file": "f00000.jpg"}, {"t": 101.0, "file": "../../etc/passwd"},
                        {"t": 101.5, "file": "/etc/hosts"}, {"t": "soon", "file": "f00001.jpg"},
                        {"t": 102.0, "file": "f00001.jpg"}, {"t": 103.0, "file": "f00002.jpg"}],
             "stopped_at": 1e12, "viewport": [100000, "tall"]}
    safe = web_video.safe_index(tmp_path, index, 100.0)
    assert [f["file"] for f in safe["frames"]] == ["f00000.jpg", "f00001.jpg"]
    assert safe["stopped_at"] == 100.0 + record.MAX_SECONDS and safe["viewport"] == [4096, 900]


def _history(*names: str) -> dict[str, Any]:
    return {"history": [{"model_output": {"action": [{n: {}}]}} for n in names] + [{"model_output": None}]}


def test_every_page_action_of_the_first_visit_must_be_replayed():
    history = _history("input", "click", "upload_file", "wait", "done")
    steps = web_video.steps_of([
        {"t0": 1.0, "t1": 2.0, "actions": {"input": {"index": 1, "text": "abc"}}, "box": [0, 0, 10, 10]},
        {"t0": 3.0, "t1": 3.5, "actions": {"click": {"index": 2}}, "box": [0, 0, 10, 10]},
        {"t0": 4.0, "t1": 4.5, "actions": {"upload_file": {"index": 3, "path": "/home/web/samples/sample.txt"}}}],
        (1280, 900))
    assert not web_video.history_actions(history) - web_video.replayed_actions(steps)
    missing = web_video.history_actions(history) - web_video.replayed_actions(steps[:3])  # an input is two steps
    assert dict(missing) == {"upload_file": 1}


class _Verdict:
    def __init__(self, shown: bool) -> None:
        self.feature_shown, self.observed = shown, "the board shows a placed tile"

    def model_dump(self) -> dict[str, Any]:
        return {"feature_shown": self.feature_shown, "observed": self.observed}


def _judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, shown: bool = True, errors: list[str] = (),
           flows: list[dict[str, Any]] = (), steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from pickfit.verify import web_verify as wv

    monkeypatch.setattr(wv, "visual_change", lambda a, b: 0.12)
    monkeypatch.setattr(wv, "screenshot_check", lambda check, *a, **k: (check, 0.0))
    monkeypatch.setattr(wv, "judge_function", lambda *a, **k: (_Verdict(shown), 0.001))
    (tmp_path / "flows.jsonl").write_text("".join(json.dumps(f) + "\n" for f in flows), encoding="utf-8")
    steps = steps if steps is not None else [{"action": {"kind": "click", "x": 5, "y": 5}, "at": [1.0, 1.0]},
                                             {"action": {"kind": "type", "text": "pickfitab12 note"}, "at": [1.0, 2.0]}]
    outcome = {"result_kind": "text_on_page", "result_text": "Encoded!"}
    after = {"text": "Your note is Encoded! now", "screenshot_jpeg_b64": "QQ=="}
    return web_video.judge_replay(tmp_path, object(), outcome, ["pickfitab12 note"], "pickfitab12", _history("input"),
                                  steps, {"after": after, "errors": list(errors)},
                                  {"text": "Type a note", "screenshot_jpeg_b64": "QQ=="}, run_id="video-x", scope="video:x")


def test_a_replay_passes_only_as_the_first_visit_did(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    good = _judge(tmp_path, monkeypatch)
    assert good["passed"] and good["data_sent"] == "none" and good["why"] is None
    assert not _judge(tmp_path, monkeypatch, shown=False)["passed"]  # the function judge, as on the first visit
    failed = _judge(tmp_path, monkeypatch, errors=["No action to replay", "Element 7 not found"])
    assert not failed["passed"] and "Element 7 not found" in failed["why"]
    assert "did not run" in _judge(tmp_path, monkeypatch, steps=[])["why"]
    sent = _judge(tmp_path, monkeypatch, flows=[{"url": "https://collector.example/c?q=pickfitab12%20note",
                                                "host": "collector.example", "method": "GET", "allowed": True}])
    assert sent["data_sent"] == "observed" and not sent["passed"]


def test_nothing_is_replayed_on_a_sign_in_wall_or_terms_that_forbid_bots(monkeypatch: pytest.MonkeyPatch):
    from pickfit.verify import web_verify as wv

    class Page:
        def __init__(self, screen: str) -> None:
            self.screen = screen

        def model_dump(self) -> dict[str, Any]:
            return {"screen": self.screen}

    target = wv.WebTarget(slug="s", name="S", url="https://s.example/", use_case="", features=[])
    pre = wv.Preflight(allowed=True, reason=None, robots_status=404, robots_txt=None, crawl_delay=None)
    state = {"url": "https://s.example/", "text": "Welcome " * 80, "links": [{"text": "Terms", "href": "/terms"}]}
    monkeypatch.setattr(wv, "judge_page", lambda *a, **k: (Page("sign_in_wall"), 0.001))
    ok, why, _, _ = web_video.check_install(target, state, pre, run_id="video-x", scope="video:x")
    assert not ok and "sign_in_wall" in why
    monkeypatch.setattr(wv, "judge_page", lambda *a, **k: (Page("main_ui"), 0.001))
    monkeypatch.setattr(wv, "check_terms", lambda urls, *a, **k: (True, "No bots.", urls, 0.002))
    ok, why, info, _ = web_video.check_install(target, state, pre, run_id="video-x", scope="video:x")
    assert not ok and why == "the terms forbid automated access" and info["terms_rendered"]["checked"]


def test_a_recording_visit_is_logged_as_the_sites_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from pickfit.verify import web_verify as wv

    other, mine = tmp_path / "other" / "runs", tmp_path / "mine" / "runs"
    (other / "web").mkdir(parents=True)
    (other / "web" / "visits.jsonl").write_text(json.dumps(
        {"site": "s.example", "slug": "s", "run_id": "web-s-20261102-000000-0001", "at": "x", "revisit": None}) + "\n")
    monkeypatch.setattr(web_video, "runs_roots", lambda: [mine, other])
    monkeypatch.setattr(wv, "visits_path", lambda: mine / "web" / "visits.jsonl")
    reason = web_video.log_revisit("s.example", "s", "video-s-20261102-220000-ab12", "web-s-20261102-010000-0002")
    line = json.loads((mine / "web" / "visits.jsonl").read_text())
    assert line["revisit"] == reason and reason.endswith("first visit web-s-20261102-000000-0001")


def test_frame_times_that_are_not_finite_are_refused(tmp_path: Path):
    (tmp_path / "f00000.jpg").write_bytes(b"x")
    (tmp_path / "f00001.jpg").write_bytes(b"x")
    index = json.loads('{"frames": [{"t": NaN, "file": "f00000.jpg"}, {"t": 101.0, "file": "f00001.jpg"}, '
                       '{"t": Infinity, "file": "f00001.jpg"}], "stopped_at": NaN, "viewport": [1280, 900]}')
    safe = web_video.safe_index(tmp_path, index, 100.0)
    assert safe["frames"] == [{"t": 101.0, "file": "f00001.jpg"}] and safe["stopped_at"] == 101.0


@pytest.mark.skipif(not TESSERA.exists(), reason="needs data/software/tessera.json")
def test_a_recording_visit_that_sent_data_away_says_so_in_the_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from types import SimpleNamespace

    shutil.copy(TESSERA, tmp_path / "tessera.json")
    run_id = json.loads(TESSERA.read_text(encoding="utf-8"))["verification"]["runs"][0]["id"]
    judged = {"passed": False, "why": "data pickfit entered left the device", "check": {}, "data_sent": "observed",
              "leaks": [{"sent": True, "host": "collector.example"}], "cost_usd": 0.0}
    monkeypatch.setattr(web_video, "judge_replay", lambda *a, **k: judged)
    out = tmp_path / "video-tessera-20261102-230000-ab12"
    out.mkdir()
    web_video.finish(out, {"slug": "tessera", "run": run_id, "harness": {}}, {"install": {}, "replay": {"result": {"after": {}}}},
                     SimpleNamespace(goal="g", check="download", expected=[]), None, [], "", out.name, lambda *_: None,
                     target=None, history={}, data_dir=tmp_path)
    run = json.loads((tmp_path / "tessera.json").read_text(encoding="utf-8"))["verification"]["runs"][0]
    assert run["web"]["data_sent"] == "observed" and "collector.example" in run["web"]["data_sent_note"]
    saved = json.loads((out / "replay.json").read_text(encoding="utf-8"))
    assert saved["result"]["checks"][0]["run"]["operate"]["passed"] is False
    assert saved["video"]["data_sent_update"].startswith("tessera: data_sent observed")
