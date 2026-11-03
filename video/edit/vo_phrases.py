"""Split each narration take into phrases at its pauses and write audio/vo/phrases.json.

    python3 edit/vo_phrases.py

A phrase is speech between silences of at least MIN_GAP seconds (-40 dB). The timeline
(edit/timeline.json) places phrases by id, e.g. "s02.3", so the picture decides how long
each pause is.
"""
import json, re, subprocess, sys
from pathlib import Path

VO = Path(__file__).resolve().parent.parent / "audio" / "vo"
MIN_GAP = 0.28
PAD = 0.04  # keep a breath of room on each side of a phrase


def duration(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


def silences(f):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(f), "-af", f"silencedetect=noise=-40dB:d={MIN_GAP}", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


out = {}
for f in sorted(VO.glob("s[0-9][0-9].mp3")):
    d = duration(f)
    cuts, cursor, phrases = silences(f), 0.0, []
    for s, e in cuts:
        if s > cursor + 0.05:
            phrases.append((max(0, cursor - PAD), min(d, s + PAD)))
        cursor = e if e is not None else d
    if cursor < d - 0.05:
        phrases.append((max(0, cursor - PAD), d))
    out[f.stem] = {"duration": round(d, 3), "phrases": [{"id": f"{f.stem}.{i + 1}", "start": round(a, 3), "end": round(b, 3), "len": round(b - a, 3)} for i, (a, b) in enumerate(phrases)]}

(VO / "phrases.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, v["duration"], " ".join(f'{p["id"]}={p["len"]:.2f}' for p in v["phrases"]))
print("speech total", round(sum(p["len"] for v in out.values() for p in v["phrases"]), 2))
