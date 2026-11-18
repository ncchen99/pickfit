"""Join the rendered segments into the final cut and add the soundtrack.

    python3 edit/assemble.py  → out/pickfit-demo.mp4

Segments must already be rendered (node render.mjs <scene>) and the mix made (edit/mix.py).
Each segment's length is checked against the timeline before joining.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SEGMENTS = [  # file, expected seconds
    ("out/night.mp4", 38.0),
    ("out/screens-main.mp4", 48.0),
    ("out/agents.mp4", 4.2),
    ("out/screens-agents.mp4", 19.8),
    ("out/thread.mp4", 36.5),
    ("out/finale.mp4", 32.1),
]


def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


bad = False
for f, want in SEGMENTS:
    p = HERE / f
    if not p.exists():
        print(f"missing {f}"); bad = True; continue
    got = duration(p)
    flag = "" if abs(got - want) < 0.05 else "  <-- length differs"
    print(f"{f}: {got:.2f}s (want {want}){flag}")
    bad |= bool(flag)
if bad and "--force" not in sys.argv:
    sys.exit("fix the segments first (or pass --force)")

lst = HERE / "out" / "segments.txt"
lst.write_text("".join(f"file '{HERE / f}'\n" for f, _ in SEGMENTS))
video = HERE / "out" / "video-only.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)], check=True)
final = HERE / "out" / "pickfit-demo.mp4"
# The product-intro cut (11/18) starts after the old disclosure card: both picture and mix from trim.from,
# with the first frame held for trim.lead_in (fading up from black) so the first line has a breath before it.
trim = json.loads((HERE / "edit" / "timeline.json").read_text()).get("trim", {"from": 0.0, "lead_in": 0.0})
t0, lead = trim["from"], trim["lead_in"]
ms = int(round(lead * 1000))
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(HERE / "audio" / "mix.wav"),
                "-filter_complex",
                f"[0:v]trim=start={t0},setpts=PTS-STARTPTS,tpad=start_duration={lead}:start_mode=clone,fade=t=in:st=0:d={max(lead - 0.1, 0.01)}[v];"
                f"[1:a]atrim=start={t0},asetpts=PTS-STARTPTS,adelay={ms}|{ms}[a]",
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
print(f"{final}: {duration(final):.2f}s")
