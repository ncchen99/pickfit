"""Build the recording clips listed in edit/edl.json.

    python3 edit/clips.py [clip_id ...]

For each clip: rec/clips/<id>.mp4 (30 fps, 1920 wide, exactly its length) and
rec/clips/<id>/00001.jpg ... (the same frames, for the 3D screen scene to use as textures).
Each piece is cut from its source, cropped, and sped up or slowed to fit its 'dur'.
"""
import json, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FPS = 30


def build(clip, sources):
    out = HERE / "rec" / "clips"
    out.mkdir(parents=True, exist_ok=True)
    args, filters, labels = ["ffmpeg", "-y", "-loglevel", "error"], [], []
    for i, p in enumerate(clip["pieces"]):
        src = sources[p["src"]]
        span = p["out"] - p["in"]
        args += ["-ss", f"{p['in']:.3f}", "-t", f"{span + 0.5:.3f}", "-i", str(HERE / src["file"])]
        crop = src.get("crop")
        speed = span / p["dur"]
        # The screen recorder writes no frames while nothing changes, so hold the last frame (tpad) to fill the piece.
        chain = f"[{i}:v]setpts=PTS-STARTPTS,setpts=PTS/{speed:.5f},fps={FPS},tpad=stop_mode=clone:stop_duration={p['dur'] + 1:.2f},trim=duration={p['dur']:.4f},setpts=PTS-STARTPTS"
        if crop:
            w, h, x, y = crop[2], crop[3], crop[0], crop[1]
            chain += f",crop={w}:{h}:{x}:{y}"
        chain += ",scale=1920:-2:flags=lanczos,setsar=1,format=yuv420p"
        filters.append(chain + f"[v{i}]")
        labels.append(f"[v{i}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[out]")
    mp4 = out / f"{clip['id']}.mp4"
    args += ["-filter_complex", ";".join(filters), "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", str(FPS), str(mp4)]
    subprocess.run(args, check=True)
    frames = out / clip["id"]
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-q:v", "3", str(frames / "%05d.jpg")], check=True)
    n = len(list(frames.glob("*.jpg")))
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)]))
    size = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(mp4)]).decode().strip()
    want = sum(p["dur"] for p in clip["pieces"])
    print(f"{clip['id']}: {dur:.2f}s (want {want:.2f}), {n} frames, {size}")


edl = json.loads((HERE / "edit" / "edl.json").read_text())
only = set(sys.argv[1:])
for c in edl["clips"]:
    if not only or c["id"] in only:
        build(c, edl["sources"])
