#!/usr/bin/env python3
"""q15 calibration: build the frozen 60-second Mandarin clip and its reference.

Run once by 念誠 before the first eval run, after the source recording(s) are
chosen (needs.json) and decoded to 16 kHz mono 16-bit PCM WAV with the pinned
ffmpeg:
    ffmpeg -nostdin -i IN -ac 1 -ar 16000 -c:a pcm_s16le OUT.wav

  concat  many short clips with their transcripts (e.g. a CC0 speech corpus):
          each clip's leading and trailing silence is trimmed (20 ms frames,
          threshold 35 dB below the clip's loudest frame, 100 ms kept on each
          side), clips are taken in manifest order, a clip that would push the
          total past 60 s is skipped, clips are joined with 0.30 s of silence,
          and the end is padded with silence to exactly 60.000 s (at most
          2.5 s of padding, else the build stops: choose other clips).
  cut     one continuous recording: 60.000 s starting at --start; the
          reference text is written by hand for exactly that window.
  squeeze one continuous recording from --start, with every pause longer
          than 0.50 s shortened to 0.30 s (its first and last 0.15 s kept,
          the middle dropped; shorter pauses and all speech untouched), cut
          inside a pause and padded with silence to exactly 60.000 s
          (calibration.md, "縮短長停頓"). Pauses are found with the same
          20 ms frames and threshold as speech seconds, over the whole
          source, frames aligned to its first sample.
  stats   duration, speech seconds (frames above the threshold), Han
          character count and, with the pinned OpenCC, the script-differing
          count the item needs (>= 60).

Outputs in --out-dir: clip.wav (60.000 s), warmup.wav (its first 10 s, used
to trigger model downloads during setup), reference.txt (one line per clip or
the hand-written text), SOURCE.json (provenance, every input's SHA-256,
offsets, output SHA-256s).

Python 3.9+ standard library (wave, array); no audio library needed.
"""
from __future__ import annotations

import argparse
import array
import datetime
import hashlib
import json
import math
import os
import sys
import wave

RATE = 16000
CLIP_SECONDS = 60.0
WARMUP_SECONDS = 10.0
GAP_SECONDS = 0.30
MAX_PAD_SECONDS = 2.5
FRAME = 320  # 20 ms
KEEP_FRAMES = 5  # 100 ms
THRESHOLD_DB = 35.0
LONG_PAUSE_FRAMES = 26  # more than 0.50 s
PAUSE_TO = 4800  # 0.30 s: the first and last 0.15 s of a long pause are kept
CUT_PAUSE_FRAMES = 5  # an untouched pause of at least 0.10 s may hold the end cut


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_wav(path: str) -> array.array:
    with wave.open(path, "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
            raise SystemExit("%s: need 16 kHz mono 16-bit PCM, got %d ch, %d bytes, %d Hz (convert with ffmpeg)" % (
                path, w.getnchannels(), w.getsampwidth(), w.getframerate()))
        frames = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def write_wav(path: str, samples: array.array) -> None:
    data = array.array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def frame_rms(samples: array.array) -> list:
    out = []
    for i in range(0, len(samples) - FRAME + 1, FRAME):
        chunk = samples[i:i + FRAME]
        out.append(math.sqrt(sum(s * s for s in chunk) / FRAME))
    return out


def voiced(rms: list) -> list:
    if not rms:
        return []
    peak = max(rms)
    thr = max(peak * 10 ** (-THRESHOLD_DB / 20.0), 30.0)
    return [r >= thr for r in rms]


def trim(samples: array.array):
    flags = voiced(frame_rms(samples))
    if not any(flags):
        raise SystemExit("clip is silent")
    first = flags.index(True)
    last = len(flags) - 1 - flags[::-1].index(True)
    a = max(0, (first - KEEP_FRAMES) * FRAME)
    b = min(len(samples), (last + 1 + KEEP_FRAMES) * FRAME)
    return samples[a:b], a, b


def speech_seconds(samples: array.array) -> float:
    return sum(voiced(frame_rms(samples))) * FRAME / RATE


def write_outputs(out_dir: str, clip: array.array, ref_lines: list, source: dict) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    clip_path = os.path.join(out_dir, "clip.wav")
    warm_path = os.path.join(out_dir, "warmup.wav")
    ref_path = os.path.join(out_dir, "reference.txt")
    write_wav(clip_path, clip)
    write_wav(warm_path, clip[:int(WARMUP_SECONDS * RATE)])
    with open(ref_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(line.strip() for line in ref_lines) + "\n")
    source = dict(source)
    source["built_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    source["builder"] = "build_clip.py"
    source["outputs"] = {name: {"sha256": sha256_file(os.path.join(out_dir, name)),
                                "bytes": os.path.getsize(os.path.join(out_dir, name))}
                         for name in ("clip.wav", "warmup.wav", "reference.txt")}
    source["stats"] = {"seconds": len(clip) / RATE, "speech_seconds": round(speech_seconds(clip), 2)}
    with open(os.path.join(out_dir, "SOURCE.json"), "w", encoding="utf-8") as fh:
        json.dump(source, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return source


def cmd_concat(args) -> int:
    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    base = os.path.dirname(os.path.abspath(args.manifest))
    total_n = int(CLIP_SECONDS * RATE)
    gap = array.array("h", [0] * int(GAP_SECONDS * RATE))
    out = array.array("h")
    used, skipped, lines = [], [], []
    for clip in manifest["clips"]:
        path = os.path.join(base, clip["wav"])
        samples, a, b = trim(read_wav(path))
        need = len(samples) + (len(gap) if out else 0)
        if len(out) + need > total_n:
            skipped.append(clip["id"])
            continue
        if out:
            out.extend(gap)
        offset = len(out) / RATE
        out.extend(samples)
        used.append({"id": clip["id"], "wav_sha256": sha256_file(path), "original_file": clip.get("original_file"),
                     "original_sha256": clip.get("original_sha256"), "trim_samples": [a, b],
                     "offset_seconds": round(offset, 3), "seconds": round(len(samples) / RATE, 3),
                     "text": clip["text"]})
        lines.append(clip["text"])
        if total_n - len(out) < RATE:  # less than 1 s left
            break
    pad = total_n - len(out)
    if pad / RATE > MAX_PAD_SECONDS and not args.allow_pad:
        raise SystemExit("only %.2f s of speech fits; %.2f s of padding is more than %.1f s: add clips" % (
            len(out) / RATE, pad / RATE, MAX_PAD_SECONDS))
    out.extend([0] * pad)
    src = {"mode": "concat", "source": manifest.get("source", {}), "gap_seconds": GAP_SECONDS,
           "threshold_db": THRESHOLD_DB, "padding_seconds": round(pad / RATE, 3), "used": used, "skipped": skipped}
    res = write_outputs(args.out_dir, out, lines, src)
    sys.stderr.write("build_clip: %d clips used, %d skipped, %.2f s padding, speech %.1f s\n" % (
        len(used), len(skipped), pad / RATE, res["stats"]["speech_seconds"]))
    return 0


def cmd_cut(args) -> int:
    samples = read_wav(args.wav)
    a = int(round(args.start * RATE))
    b = a + int(CLIP_SECONDS * RATE)
    if b > len(samples):
        raise SystemExit("recording ends before start + 60 s")
    with open(args.text_file, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    source = {}
    if args.source_json:
        with open(args.source_json, encoding="utf-8") as fh:
            source = json.load(fh)
    src = {"mode": "cut", "source": source, "input_sha256": sha256_file(args.wav),
           "start_seconds": args.start, "window_samples": [a, b]}
    write_outputs(args.out_dir, samples[a:b], lines, src)
    return 0


def pauses(flags: list) -> list:
    """Runs of silent frames as (first, end) frame indices."""
    out, start = [], None
    for i, voice in enumerate(flags + [True]):
        if not voice and start is None:
            start = i
        elif voice and start is not None:
            out.append((start, i))
            start = None
    return out


def squeeze(samples: array.array, start: int):
    """The calibration.md rule: returns the 60.000 s clip and what was done to make it."""
    rms = frame_rms(samples)
    peak = max(rms)
    thr = max(peak * 10 ** (-THRESHOLD_DB / 20.0), 30.0)
    out, shortened, cuts = array.array("h"), [], []
    cursor = start
    for a, b in pauses([r >= thr for r in rms]):
        a, b = max(a * FRAME, start), b * FRAME
        if b <= start:
            continue
        if b - a > LONG_PAUSE_FRAMES * FRAME - FRAME:  # longer than 0.50 s
            half = PAUSE_TO // 2
            out.extend(samples[cursor:a + half])
            cuts.append((len(out), "long"))
            shortened.append({"source_start": round(a / RATE, 3), "source_end": round(b / RATE, 3),
                              "seconds": round((b - a) / RATE, 3), "new_seconds": PAUSE_TO / RATE,
                              "clip_at": round((len(out) - half) / RATE, 3)})
            cursor = b - half
        elif b - a >= CUT_PAUSE_FRAMES * FRAME:
            cuts.append((len(out) + (a + b) // 2 - cursor, "short"))
        if len(out) + (a - cursor) > int(CLIP_SECONDS * RATE) + RATE:
            break
    total = int(CLIP_SECONDS * RATE)
    fits = [(c, kind) for c, kind in cuts if c <= total and (kind == "short" or c <= len(out))]
    long_cuts = [c for c, kind in fits if kind == "long" and total - c <= MAX_PAD_SECONDS * RATE]
    if long_cuts:
        cut, kind = long_cuts[-1], "long"
    else:
        cut, kind = max(c for c, k in fits if k == "short"), "short"
    if cut > len(out):
        out.extend(samples[cursor:cursor + cut - len(out)])
    clip = out[:cut]
    clip.extend([0] * (total - cut))
    done = [p for p in shortened if p["clip_at"] * RATE < cut]
    info = {"threshold_dbfs": round(20 * math.log10(thr / 32768.0), 2), "frame_ms": FRAME * 1000 // RATE,
            "long_pause_over_seconds": (LONG_PAUSE_FRAMES - 1) * FRAME / RATE, "pause_to_seconds": PAUSE_TO / RATE,
            "shortened": done, "removed_seconds": round(sum(p["seconds"] - p["new_seconds"] for p in done), 3),
            "cut_kind": kind, "cut_clip_seconds": round(cut / RATE, 3), "padding_seconds": round((total - cut) / RATE, 3)}
    return clip, info


def cmd_squeeze(args) -> int:
    samples = read_wav(args.wav)
    start = int(round(args.start * RATE))
    clip, info = squeeze(samples, start)
    with open(args.text_file, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    source = {}
    if args.source_json:
        with open(args.source_json, encoding="utf-8") as fh:
            source = json.load(fh)
    src = {"mode": "squeeze", "source": source, "input_sha256": sha256_file(args.wav), "start_seconds": args.start,
           "squeeze": info}
    res = write_outputs(args.out_dir, clip, lines, src)
    sys.stderr.write("build_clip: %d pauses shortened (%.2f s removed), cut in a %s pause at %.3f s, %.3f s padding, "
                     "speech %.2f s\n" % (len(info["shortened"]), info["removed_seconds"], info["cut_kind"],
                                           info["cut_clip_seconds"], info["padding_seconds"],
                                           res["stats"]["speech_seconds"]))
    return 0


def cmd_stats(args) -> int:
    clip = read_wav(args.clip)
    with open(args.ref, encoding="utf-8") as fh:
        ref = fh.read()
    out = {"seconds": len(clip) / RATE, "speech_seconds": round(speech_seconds(clip), 2)}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import zh_score

        out["reference"] = zh_score.reference_stats(ref, zh_score.zh_script.OpenCCTables(args.dict_dir))
    except SystemExit as exc:
        out["reference"] = {"error": str(exc)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("concat")
    sp.add_argument("--manifest", required=True, help="JSON: source{...}, clips[{id, wav, text, original_file, original_sha256}]")
    sp.add_argument("--out-dir", required=True)
    sp.add_argument("--allow-pad", action="store_true")
    sp.set_defaults(func=cmd_concat)
    sp = sub.add_parser("cut")
    sp.add_argument("--wav", required=True)
    sp.add_argument("--start", type=float, required=True)
    sp.add_argument("--text-file", required=True)
    sp.add_argument("--source-json")
    sp.add_argument("--out-dir", required=True)
    sp.set_defaults(func=cmd_cut)
    sp = sub.add_parser("squeeze")
    sp.add_argument("--wav", required=True)
    sp.add_argument("--start", type=float, required=True)
    sp.add_argument("--text-file", required=True)
    sp.add_argument("--source-json")
    sp.add_argument("--out-dir", required=True)
    sp.set_defaults(func=cmd_squeeze)
    sp = sub.add_parser("stats")
    sp.add_argument("--clip", required=True)
    sp.add_argument("--ref", required=True)
    sp.add_argument("--dict-dir", required=True, help="pinned OpenCC dictionary files (_shared/needs.json)")
    sp.set_defaults(func=cmd_stats)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
