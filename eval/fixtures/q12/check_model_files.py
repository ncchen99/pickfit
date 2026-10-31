#!/usr/bin/env python3
"""q12 L2-2: after the server has started, confirm it uses the frozen fixture
model as published (pinned revision, no conversion step). Python 3.8+ stdlib.

  python3 check_model_files.py --marker MARKER [--pin model_pin.json] [ROOT ...]
  python3 check_model_files.py --marker MARKER --local-path DIR   # answer loads a local folder

MARKER is a file the grader touched right before the answer's first step.
Under each ROOT (default: $HOME, /Users/Shared, /opt/homebrew, /usr/local,
/private/tmp and $TMPDIR) it looks at every file or symlink with a weight-like
extension (.safetensors .gguf .ggml .bin .npz .npy .pt .pth .onnx .ckpt
.weights .mlmodel) modified after MARKER, resolves symlinks, and hashes it.

  * PASS when every such file is byte-identical (size and SHA-256) to a file of
    the pinned model, and the Hugging Face cache, if the model came through
    it, holds the pinned revision.
  * FAIL when a new weight file matches no pinned file (a conversion,
    re-quantisation or a different model) or only another revision is cached.
With --local-path (the answer loads the model from a folder; the grader made
it with fetch_model.sh before MARKER), DIR must still match the pins exactly
and no unknown new weight file may appear; no new weight file at all is then
expected. Other large new files (>= 20 MB, e.g. package downloads) are listed
for the record but not judged.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHT_EXT = (".safetensors", ".gguf", ".ggml", ".bin", ".npz", ".npy", ".pt", ".pth", ".onnx", ".ckpt",
              ".weights", ".mlmodel")
BIG = 20 * 1024 * 1024


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def hub_dirs():
    out = []
    for env in ("HF_HUB_CACHE",):
        if os.environ.get(env):
            out.append(os.environ[env])
    if os.environ.get("HF_HOME"):
        out.append(os.path.join(os.environ["HF_HOME"], "hub"))
    out.append(os.path.expanduser("~/.cache/huggingface/hub"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="q12 fixture-model file check")
    ap.add_argument("--marker", required=True)
    ap.add_argument("--pin", default=os.path.join(HERE, "model_pin.json"))
    ap.add_argument("--local-path", help="the fixture folder the answer's command was given")
    ap.add_argument("roots", nargs="*")
    a = ap.parse_args(argv)
    with open(a.pin, encoding="utf-8") as f:
        pin = json.load(f)
    pinned = {(x["size"], x["sha256"]): x["path"] for x in pin["files"]}
    since = os.stat(a.marker).st_mtime
    roots = a.roots or [os.path.expanduser("~"), "/Users/Shared", "/opt/homebrew", "/usr/local", "/private/tmp",
                        os.environ.get("TMPDIR", "/private/tmp")]
    seen, weights, others = set(), [], []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if not os.path.islink(os.path.join(d, x))]
            for n in files:
                p = os.path.join(d, n)
                try:
                    st = os.stat(p)  # follows symlinks
                    lst = os.lstat(p)
                except OSError:
                    continue
                if max(st.st_mtime, lst.st_mtime) <= since:
                    continue
                real = os.path.realpath(p)
                if n.lower().endswith(WEIGHT_EXT):
                    if real in seen:
                        continue
                    seen.add(real)
                    weights.append((p, real, st.st_size))
                elif st.st_size >= BIG and not os.path.islink(p):
                    others.append((p, st.st_size))
    bad = []
    print("pinned model: %s @ %s (%d files)" % (pin["repo_id"], pin["revision"], len(pin["files"])))
    print("new weight-like files: %d" % len(weights))
    for p, real, size in weights:
        h = sha256(real)
        match = pinned.get((size, h))
        print("  %-8s %s%s" % ("pinned" if match else "UNKNOWN", p, "" if real == p else " -> " + real))
        if not match:
            bad.append(p)
    org, name = pin["repo_id"].split("/", 1)
    revs = []
    for hub in hub_dirs():
        snap = os.path.join(hub, "models--%s--%s" % (org, name), "snapshots")
        if os.path.isdir(snap):
            revs += sorted(os.listdir(snap))
    if revs:
        print("cached revisions of the pinned repo: %s" % ", ".join(revs))
    else:
        print("the pinned repo is not in the Hugging Face cache (local path, or another store)")
    rev_ok = (not revs) or (pin["revision"] in revs)
    if not rev_ok:
        print("  the pinned revision %s is not among them" % pin["revision"])
    if others:
        print("other new files >= 20 MB (not judged):")
        for p, size in others[:30]:
            print("  %8.1f MB  %s" % (size / 1048576.0, p))
    local_ok = None
    if a.local_path:
        local_ok = True
        for x in pin["files"]:
            fp = os.path.join(a.local_path, x["path"])
            good = os.path.isfile(fp) and os.path.getsize(fp) == x["size"] and sha256(fp) == x["sha256"]
            if not good:
                print("  local copy differs from the pin: %s" % x["path"])
                local_ok = False
        print("local path %s matches the pins: %s" % (a.local_path, "yes" if local_ok else "NO"))
        ok = not bad and local_ok
        print("L2-2 model files: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    ok = not bad and rev_ok and bool(weights)
    if not weights:
        print("no new weight file found: check where the server read the model from (local path fetched "
              "before the marker is fine: then judge by the server's own log)")
    print("L2-2 model files: %s" % ("PASS" if ok else ("REVIEW" if not weights else "FAIL")))
    return 0 if ok else (3 if not weights else 1)


if __name__ == "__main__":
    sys.exit(main())
