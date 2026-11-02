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
           {"t0": 17.0, "t1": 17.1, "actions": {"navigate": {"url": "https://example.com"}}}]
    steps = web_video.steps_of(log, (1280, 900))
    assert [s["action"] for s in steps] == [
        {"kind": "click", "x": 250, "y": 220, "label": "Job link"},
        {"kind": "type", "text": "https://example.com/x"},
        {"kind": "click", "x": 960, "y": 115, "label": "Download PNG"},
        {"kind": "key", "name": "Enter"},
        {"kind": "scroll", "direction": "up", "x": 640, "y": 450}]
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
