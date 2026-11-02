"""Verification videos of web apps: a second visit, recorded, that replays the first visit's actions.

A web app's run is one visit (web_verify): browser-use, driven by Muse Spark Open, used one feature and pickfit
checked the result. For its clip, pickfit visits the site once more (claim_visit with a reason, after robots.txt
and the terms are read again) in the same kind of Modal VM, through the same guard, nothing relaxed:

- the browser records itself: Chromium's screencast (CDP Page.startScreencast) sends a JPEG of each paint of the
  page's viewport, nothing outside it; the harness keeps one per 0.2 s with its time (web_harness.Screencast);
- the first visit's actions are replayed without a model (browser-use's rerun_history, the replay the offline phase
  uses), through the same guarded tools; each action is logged with its time and the box of the element it touched;
- pickfit checks the result again with the first visit's own check (web_verify.check_result): a clip is cut only
  when it passes again.

The host turns the frames into the raw recording at record.RECORD_FPS, each frame held until the next paint, with
an arrow drawn where pickfit's action went (a headless browser has no pointer; the macOS recorder draws one the same
way). From there video.py edits it like any recording: `python -m pickfit.verify.video edit runs/video/<run>`.

Why the screencast and not Xvfb with ffmpeg: it needs nothing new in the web image (no X server, no ffmpeg in the
VM), records the viewport only, and keeps the browser headless, as every web visit is. What it gives up: frames
come on paint (an animation is sampled, not filmed) and a new tab is not followed.

`python -m pickfit.verify.web_video record <slug> [--run <run id>]`.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.verify import record as recording
from pickfit.verify import web_verify as wv
from pickfit.verify.video import DATA_DIR, load_record, passed_operations, pick_run, runs_roots

REVISIT = "verification video: the first visit's actions replayed and recorded (念誠, 11/2)"
HISTORY = "/home/web/history.json"
FRAMES = "/home/web/evidence/frames"
FRAMES_TAR = "/tmp/pickfit-frames.tar"
PART_BYTES = 8_000_000
TASK = "Replay a saved visit"  # the replay's agent has no model; the task is only its label
HARNESS_TIMEOUT_S = 900
CLICK_RING_S, CLICK_RING_R = 0.6, 20  # a headless browser shows no click: a ring where it landed, this long


def find_visit(slug: str, run_id: str) -> Path | None:
    """The first visit's evidence (runs/web/<slug>/<run id>/) in this checkout, the main one or a worktree."""
    for root in runs_roots():
        path = root / "web" / slug / run_id
        if (path / "web_result.json").is_file() and (path / "agent_history.json").is_file():
            return path
    return None


def steps_of(actions: list[dict[str, Any]], viewport: tuple[int, int]) -> list[dict[str, Any]]:
    """The harness's action log as video.py's steps: clicks at the element's centre (with its words), typed text,
    keys and scrolls, each with its times."""
    steps: list[dict[str, Any]] = []
    for entry in actions:
        at = [entry["t0"], entry.get("t1", entry["t0"])]
        box = entry.get("box")
        point = {"x": int(box[0] + box[2] / 2), "y": int(box[1] + box[3] / 2)} if box else {}
        label = {"label": entry["label"]} if entry.get("label") else {}
        for name, params in (entry.get("actions") or {}).items():
            params = params if isinstance(params, dict) else {}
            if name in ("click", "select_dropdown", "upload_file"):
                if not point and params.get("coordinate_x") is not None:
                    point = {"x": int(params["coordinate_x"]), "y": int(params["coordinate_y"])}
                if name == "upload_file":  # the file chooser: pickfit picks one of its own sample files
                    chosen = Path(str(params.get("path", ""))).name
                    label = {"label": f"{entry.get('label') or 'the file input'}, choosing pickfit's {chosen}"}
                steps.append({"action": {"kind": "click", **point, **label}, "at": at})
            elif name == "input":
                if point:
                    steps.append({"action": {"kind": "click", **point, **label}, "at": [at[0], at[0]]})
                steps.append({"action": {"kind": "type", "text": str(params.get("text", ""))}, "at": at})
            elif name == "send_keys":
                steps.append({"action": {"kind": "key", "name": str(params.get("keys", ""))}, "at": at})
            elif name == "scroll":
                steps.append({"action": {"kind": "scroll", "direction": "down" if params.get("down", True) else "up",
                                         "x": viewport[0] // 2, "y": viewport[1] // 2}, "at": at})
    return steps


def encode_raw(frames_dir: Path, index: dict[str, Any], t0: float, points: list[tuple[float, int, int]], out: Path,
               fps: int = recording.RECORD_FPS) -> float:
    """The raw recording: from t0 to the screencast's end at `fps`, each paint held until the next, an arrow where
    pickfit's last action went and a ring for CLICK_RING_S where it clicked (points: (time, x, y)). Returns its
    length in seconds."""
    from PIL import Image, ImageDraw

    width, height = index["viewport"]
    frames = sorted(index["frames"], key=lambda f: f["t"])
    count = int((index["stopped_at"] - t0) * fps) + 1
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    proc = subprocess.Popen([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                             "-pix_fmt", "rgb0", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
                             *recording.ENCODE, "-f", "mp4", str(out)], stdin=subprocess.PIPE)
    shown = -1
    current = Image.new("RGBX", (width, height), (255, 255, 255, 0)).tobytes()  # about:blank, before the first paint
    for i in range(count):
        t = t0 + i / fps
        latest = shown
        while latest + 1 < len(frames) and frames[latest + 1]["t"] <= t:
            latest += 1
        if latest != shown:
            shown = latest
            with Image.open(frames_dir / frames[shown]["file"]) as image:
                current = image.convert("RGBX").resize((width, height)).tobytes()
        point = next(((at, x, y) for at, x, y in reversed(points) if at <= t), None)
        frame = current
        if point and t - point[0] < CLICK_RING_S:
            ring = Image.frombytes("RGBX", (width, height), current)
            x, y, r = point[1], point[2], CLICK_RING_R
            ImageDraw.Draw(ring).ellipse((x - r, y - r, x + r, y + r), outline=(230, 40, 40, 0), width=4)
            frame = ring.tobytes()
        proc.stdin.write(recording.draw_pointer(frame, width, height, *point[1:]) if point else frame)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed encoding {out.name}")
    return round(count / fps, 2)


def reencode(video_dir: Path, log: Any = print) -> Path:
    """The raw recording made again from its saved frames and action log (replay.json updated with its new hash)."""
    path = video_dir / "replay.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    op = saved["result"]["checks"][0]["run"]["operate"]
    index = json.loads((video_dir / "frames" / "frames.json").read_text(encoding="utf-8"))
    raw = Path(op["video"]["path"])
    points = [(s["at"][0], s["action"]["x"], s["action"]["y"]) for s in op["steps"]
              if s["action"]["kind"] == "click" and "x" in s["action"]]
    seconds = encode_raw(video_dir / "frames", index, op["video"]["started_at"], points, raw)
    op["video"].update(sha256=recording.sha256_file(raw), bytes=raw.stat().st_size, seconds=seconds)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log(f"{raw}: {seconds:.1f} s, {op['video']['bytes']} bytes, sha256 {op['video']['sha256'][:12]}")
    return raw


def read_file(box: Any, path: str) -> bytes:
    """A file from the VM, in parts, checked against its sha256 there."""
    import hashlib

    code, out, err = box.root(["/usr/bin/bash", "-c", f"/usr/bin/stat -c %s {path} && /usr/bin/sha256sum {path}"], 60)
    if code != 0:
        raise RuntimeError(f"{path}: {err[-200:]}")
    size, digest = int(out.split()[0]), out.split()[1]
    data = b""
    while len(data) < size:
        proc = box.sandbox.exec("/usr/bin/bash", "-c", f"/usr/bin/tail -c +{len(data) + 1} {path} | "
                                f"/usr/bin/head -c {PART_BYTES}", timeout=180, text=False)
        part = b"".join(c if isinstance(c, bytes) else str(c).encode() for c in proc.stdout)
        proc.wait()
        if not part:
            break
        data += part
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f"{path} came out of the VM changed ({len(data)} of {size} bytes)")
    return data


def record_web(slug: str, run_id: str | None = None, *, data_dir: Path = DATA_DIR, log: Any = print,
               box_factory: Any = None) -> Path:
    """Visit a web app's site again, replaying and recording its run's operation; returns the evidence directory
    (runs/video/<video run>/, with replay.json in the shape video.py edits)."""
    rec = load_record(slug, data_dir)
    run = pick_run(rec, run_id)
    if run.web is None:
        raise SystemExit(f"{slug}: {run.id} is not a web app's run")
    theirs = passed_operations(run)[0]  # the visit's own operation (an offline one replays the same actions)
    visit = find_visit(slug, run.id)
    if visit is None:
        raise SystemExit(f"{slug}: the first visit's evidence (runs/web/{slug}/{run.id}/) is not on this machine")
    first = json.loads((visit / "web_result.json").read_text(encoding="utf-8"))
    function = first.get("function") or {}
    outcome, typed = function.get("outcome"), [t for t in function.get("typed") or [] if t]
    nonce = first.get("nonce") or ""
    video_run = f"video-{slug[:40].strip('-')}-{taipei_now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    out = REPO_ROOT / "runs" / "video" / video_run
    out.mkdir(parents=True, exist_ok=True)
    target = wv.WebTarget(slug=slug, name=rec.name, url=first["url"], use_case="", features=[theirs.feature or ""])
    site = wv.site_of(target.url)
    log(f"video {video_run}: a second visit to {site}, replaying {run.id} ({function.get('steps')} steps)")
    pre = wv.preflight(target, run_id=video_run)
    if not pre.allowed:
        raise SystemExit(f"{slug}: not visited again: {pre.reason}")
    wait = min(max(wv.WAIT_BETWEEN_ACTIONS, pre.crawl_delay or 0.0), wv.CRAWL_DELAY_MAX)
    from pickfit.verify.web_box import EVIDENCE, SAMPLES, WEB_UID, WebBox

    seen: dict[str, Any] = {}
    meta: dict[str, Any] = {"slug": slug, "run": run.id, "os": "web", "url": target.url, "visit": visit.name,
                            "terms_usd": round(pre.cost_usd, 5)}
    box = (box_factory or WebBox)(site=site, log=log, tags={"pickfit": "web-video", "run": video_run[:60]})
    try:
        box.start({"site": site, "nonce": nonce, "robots_txt": pre.robots_txt, "robots_status": pre.robots_status})
        samples = wv.sample_files(nonce)
        for name, data in samples.items():
            box.write(f"{SAMPLES}/{name}", data, mode="0644", owner=WEB_UID)
        box.write(HISTORY, (visit / "agent_history.json").read_bytes(), mode="0644", owner=WEB_UID)
        wv.claim_visit(site, slug, video_run, revisit=REVISIT)
        version = next((w for w in box.root(["/usr/bin/chromium", "--version"], 30)[1].split()
                        if w[:1].isdigit()), "")
        start = {"url": target.url, "site": site, "user_agent": wv.user_agent(version), "max_steps": 0,
                 "wait_between_actions": wait, "sample_files": [f"{SAMPLES}/{n}" for n in samples], "settle_s": 6,
                 "record": True, "history_path": HISTORY}

        def handle(message: dict[str, Any]) -> dict[str, Any] | None:
            kind = message.get("type")
            if kind == "llm":  # the replay has no model: a step it cannot match fails, and is not asked about
                return {"type": "llm_error", "id": message.get("id"), "error": "no model in a recording visit"}
            if kind == "observe" and message.get("phase") == "install":
                seen["install"] = message.get("state") or {}
                seen["install_problem"] = wv.page_problem(seen["install"])
                return {"type": "continue", "replay": seen["install_problem"] is None, "task": TASK}
            if kind == "observe" and message.get("phase") == "replay":
                seen["replay"] = message
                return {"type": "continue"}
            return None

        messages = box.run_harness(start, handle, timeout_s=HARNESS_TIMEOUT_S, stderr_path=out / "harness.log")
        meta["harness"] = next((m for m in reversed(messages) if m.get("type") in ("done", "error")), None) or {}
        (out / "flows.jsonl").write_bytes(box.read("/var/lib/pickfit-guard/flows.jsonl"))
        for name in box.list_evidence():
            data = box.read(f"{EVIDENCE}/{name}", 20_000_000)
            if data:
                (out / name).write_bytes(data)
        code, _, err = box.root(["/usr/bin/tar", "-C", FRAMES, "-cf", FRAMES_TAR, "."], 120)
        if code != 0:
            raise RuntimeError(f"the frames could not be packed: {err[-200:]}")
        (out / "frames.tar").write_bytes(read_file(box, FRAMES_TAR))
    finally:
        meta["box_usd"] = round(box.seconds_alive() * box.usd_per_second(), 5) if hasattr(box, "seconds_alive") else 0
        box.close()
    return finish(out, meta, seen, theirs, outcome, typed, nonce, video_run, log)


def check_line(check: dict[str, Any]) -> str:
    """pickfit's check of the replay in one line."""
    if check.get("file"):
        return f"{check['file']['name']} ({check['file']['size']} bytes) arrived"
    if check.get("text"):
        return f"the page shows {check['text']!r}"
    if check.get("visual") is not None and check.get("passed"):
        return f"{check['visual']:.0%} of the page changed"
    return check.get("why") or ""


def finish(out: Path, meta: dict[str, Any], seen: dict[str, Any], theirs: Any, outcome: dict[str, Any] | None,
           typed: list[str], nonce: str, video_run: str, log: Any) -> Path:
    """Check the replay's result, encode the raw recording and save replay.json for video.py."""
    replayed = (seen.get("replay") or {}).get("result") or {}
    after = replayed.get("after") or {}
    if seen.get("install_problem"):
        check: dict[str, Any] = {"passed": False, "why": f"the page did not load: {seen['install_problem']}"}
    elif not replayed:
        check = {"passed": False, "why": "the replay did not finish"}
    else:
        changed = wv.visual_change(out / "install.png", out / "after.png")
        check = wv.check_result(outcome, seen["replay"].get("before_text") or "", after,
                                replayed.get("downloads") or [], typed, pixels_changed=changed,
                                before_static=seen["replay"].get("before_static"))
        check, cost = wv.screenshot_check(check, outcome, out / "install.png", out / "after.png", typed,
                                          run_id=video_run, scope=f"video:{meta['slug']}")
        meta["read_usd"] = round(cost, 5)
    line = check_line(check)
    log(f"  replay check {'passed' if check.get('passed') else 'failed'}: {line}"
        + (f" · replay errors {replayed.get('errors')}" if replayed.get("errors") else ""))
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    if (out / "frames.tar").is_file():
        with tarfile.open(out / "frames.tar") as tar:
            tar.extractall(frames_dir, filter="data")
    index = json.loads((frames_dir / "frames.json").read_text(encoding="utf-8")) if (frames_dir / "frames.json").is_file() else {}
    t0 = (meta.get("harness") or {}).get("recording_started_at")
    video: dict[str, Any] = {"error": None}
    viewport = tuple(index.get("viewport") or (1280, 900))
    steps = steps_of(replayed.get("actions") or [], viewport)
    if not index.get("frames") or not t0:
        video["error"] = "no frames were recorded"
    else:
        raw = out / "raw-1.mp4"
        points = [(s["at"][0], s["action"]["x"], s["action"]["y"]) for s in steps
                  if s["action"]["kind"] == "click" and "x" in s["action"]]
        seconds = encode_raw(frames_dir, index, t0, points, raw)
        video = {"path": str(raw), "sha256": recording.sha256_file(raw), "bytes": raw.stat().st_size,
                 "started_at": t0, "seconds": seconds, "fps": recording.RECORD_FPS, "width": viewport[0],
                 "height": viewport[1], "recorder": "chromium-screencast", "frames": len(index["frames"]),
                 "error": None}
        log(f"  recording {raw.name}: {seconds:.1f} s from {len(index['frames'])} frames, {video['bytes']} bytes")
    op = {"web": True, "goal": theirs.goal, "nonce": nonce, "passed": bool(check.get("passed")),
          "check": {"kind": theirs.check, "expected": list(theirs.expected)}, "result": {"line": line, "seen": check},
          "steps": steps, "video": video, "replay_errors": replayed.get("errors") or replayed.get("error")}
    saved = {"video": meta, "plan": {}, "result": {"checks": [{"run": {"operate": op}}]}}
    (out / "replay.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log(f"video {out.name}: box ${meta.get('box_usd', 0):.4f}, terms ${meta.get('terms_usd', 0):.4f}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pickfit.verify.web_video", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="visit a web app's site again, replaying and recording its operation")
    rec.add_argument("slug")
    rec.add_argument("--run", default=None)
    enc = sub.add_parser("encode", help="make a recording's raw mp4 again from its saved frames")
    enc.add_argument("video_dir", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "encode":
        reencode(args.video_dir)
        return 0
    began = time.monotonic()
    out = record_web(args.slug, args.run)
    print(f"{out} ({time.monotonic() - began:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
