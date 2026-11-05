"""Mix the soundtrack: narration on the timeline, the score ducked under it, ambience and effects.

    uv run --with numpy python edit/mix.py [--music b]  → audio/mix.wav (48 kHz stereo, -14 LUFS)

Narration phrases come from audio/vo/phrases.json and are placed at edit/timeline.json's
"at" times. Effects are placed by CUES below (times on the final cut, from the scene builds).
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent.parent
SR = 48000
timeline = json.loads((HERE / "edit" / "timeline.json").read_text())
LENGTH = timeline["length"]
MUSIC = sys.argv[sys.argv.index("--music") + 1] if "--music" in sys.argv else "b"
MUSIC_AT = 29.3


def load(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"])
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def db(x):
    return 10 ** (x / 20)


def fade(a, fin=0.01, fout=0.01):
    n = len(a)
    i, o = min(n, int(fin * SR)), min(n, int(fout * SR))
    if i: a[:i] *= np.linspace(0, 1, i)[:, None]
    if o: a[n - o:] *= np.linspace(1, 0, o)[:, None]
    return a


def place(bus, clip, at, gain=1.0):
    s = int(round(at * SR))
    if s >= len(bus):
        return
    e = min(len(bus), s + len(clip))
    bus[s:e] += clip[: e - s] * gain


N = int(LENGTH * SR)
vo = np.zeros((N, 2), np.float32)
phr = json.loads((HERE / "audio" / "vo" / "phrases.json").read_text())
plen = {p["id"]: (k, p) for k, v in phr.items() for p in v["phrases"]}
cache = {}
for cue in timeline["vo"]:
    sec, p = plen[cue["id"]]
    if sec not in cache:
        cache[sec] = load(HERE / "audio" / "vo" / f"{sec}.mp3")
    src = cache[sec]
    seg = fade(src[int(p["start"] * SR): int(p["end"] * SR)].copy(), 0.012, 0.03)
    place(vo, seg, cue["at"], db(cue.get("gain_db", 0)))

# The score, ducked while the narration speaks.
music = np.zeros((N, 2), np.float32)
m = load(HERE / "audio" / "music" / f"score-{MUSIC}.mp3")
# The page's hold put 2.8 s into the picture (11/5), and the score's ending had to stay under the end card: one 2.5 s phrase
# (the period the score repeats at there) plays twice at 2:35, with a short equal-power crossfade at the seam.
REPEAT_AT, REPEAT = int((155.6 - MUSIC_AT) * SR), int(2.504 * SR)
xf = int(0.25 * SR)
ramp = np.linspace(0, np.pi / 2, xf)[:, None].astype(np.float32)
m = np.concatenate([m[:REPEAT_AT], m[REPEAT_AT:REPEAT_AT + xf] * np.cos(ramp) + m[REPEAT_AT - REPEAT:REPEAT_AT - REPEAT + xf] * np.sin(ramp), m[REPEAT_AT - REPEAT + xf:]])
place(music, fade(m, 0.02, 2.5), MUSIC_AT)
env = np.abs(vo).max(axis=1)
win = int(0.05 * SR)
active = np.convolve((env > db(-38)).astype(np.float32), np.ones(win) / win, mode="same") > 0
gain = np.where(active, db(-13.0), db(-6.5)).astype(np.float32)
# smooth: fast-ish attack, slow release
att, rel = int(0.12 * SR), int(0.45 * SR)
g = np.empty_like(gain)
cur = gain[0]
for i in range(0, N, 240):
    target = gain[i]
    step = 240 / (att if target < cur else rel)
    cur = cur + (target - cur) * min(1.0, step * 3)
    g[i:i + 240] = cur
music *= g[:, None]

amb = np.zeros((N, 2), np.float32)
sfx = np.zeros((N, 2), np.float32)
S = {n: load(HERE / "audio" / "sfx" / f"{n}.mp3") for n in ["alert", "tabs", "flip", "icons", "typing", "tick", "rewind", "flap", "stitch", "whoosh", "pop"]}
night_path = HERE / "audio" / "sfx" / "night-long.mp3"
if night_path.exists():
    night = load(night_path)
    reps = int(np.ceil(23.0 * SR / len(night)))
    bed = np.tile(night, (reps, 1))[: int(22.6 * SR)].copy()
    place(amb, fade(bed, 0.4, 1.2), 7.0, db(-20))

CUES = [
    # the night (0-38)
    ("pop", 7.2, -14), ("alert", 8.35, -9), ("tabs", 11.6, -10), ("flip", 12.65, -12), ("flip", 13.25, -13),
    ("flip", 14.7, -12), ("flip", 16.25, -12), ("icons", 19.8, -9), ("pop", 20.95, -13), ("pop", 21.3, -13), ("pop", 21.65, -13),
    ("typing", 22.1, -13), ("typing", 24.0, -15), ("tick", 26.0, -10),
    ("flap", 28.35, -8), ("pop", 28.95, -15), ("rewind", 30.2, -7), ("rewind", 31.6, -10), ("tick", 32.3, -16), ("whoosh", 32.95, -12), ("pop", 35.25, -12), ("stitch", 36.45, -6),
    # the real footage (38-110): soft moves between screens
    ("whoosh", 49.7, -18), ("whoosh", 62.3, -16), ("whoosh", 76.7, -16), ("whoosh", 82.6, -18),
    ("flip", 86.3, -13), ("pop", 88.8, -11), ("whoosh", 100.7, -16),
    # the thread (110-146.5)
    ("whoosh", 110.2, -12), ("pop", 113.1, -12), ("whoosh", 115.1, -15), ("whoosh", 118.7, -15), ("whoosh", 122.7, -15),
    ("pop", 128.3, -14), ("pop", 129.1, -14), ("pop", 129.9, -14), ("pop", 130.7, -14), ("stitch", 130.7, -9),
    ("whoosh", 132.6, -15), ("pop", 136.0, -11), ("whoosh", 138.7, -12), ("stitch", 141.6, -12),
    # the finale (146.5-178.6): the page turns in on the move, each of its steps done, it lands on the check and turns over
    ("stitch", 146.65, -9), ("flip", 150.0, -12),
    ("pop", 154.05, -15), ("pop", 154.5, -15), ("pop", 155.25, -15), ("pop", 156.15, -15), ("pop", 156.55, -13),
    ("whoosh", 157.15, -17), ("pop", 157.7, -14), ("flip", 158.3, -13), ("stitch", 158.65, -10),
    ("pop", 158.8, -12), ("stitch", 158.85, -12), ("pop", 160.85, -15), ("pop", 161.5, -15), ("pop", 162.15, -15), ("pop", 162.4, -13),
    ("flip", 164.4, -13), ("stitch", 165.5, -11), ("stitch", 166.1, -11), ("stitch", 166.7, -11), ("whoosh", 167.9, -14),
    ("pop", 169.9, -10), ("stitch", 170.2, -6),
]
for name, at, g_db in CUES:
    place(sfx, fade(S[name].copy(), 0.003, 0.08), at, db(g_db))

mix = vo + music + amb + sfx
mix[-int(1.5 * SR):] *= np.linspace(1, 0, int(1.5 * SR))[:, None]
raw = HERE / "audio" / "mix-raw.wav"
out = HERE / "audio" / "mix.wav"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", str(raw)], input=mix.astype(np.float32).tobytes(), check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), str(out)], check=True)
print(out, f"{LENGTH:.1f}s, music take {MUSIC}")
