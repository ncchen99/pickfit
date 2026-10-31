#!/usr/bin/env python3
"""q12 calibration tool: pin the frozen fixture model (repo id + revision +
file hashes) before the first eval run. Python 3.8+ stdlib. Needs network;
sends no token (the model must be downloadable without one).

  python3 pin_model.py REPO_ID [--revision main] --dest DIR [--out-dir .]

1. Asks the Hub API for the repo at that revision (no Authorization header)
   and resolves it to a commit sha.
2. Downloads every file of that commit into DIR (this is also the local-path
   copy of the model, so keep DIR outside the test account).
3. Writes into --out-dir (default: this folder) the pins to commit:
     model_pin.json      repo id, commit sha, files with size and SHA-256,
                         gated flag and license tag reported by the API,
                         and the config fields needed to confirm "MLX-format
                         4-bit, at most 3B parameters"
     model_pin.env       REPO_ID=... and REVISION=... for fetch_model.sh
     model_files.sha256  "<sha256>  <path>" lines (shasum -c format)

PIN_BASE_URL overrides https://huggingface.co (used by selftest.py only).
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("PIN_BASE_URL", "https://huggingface.co").rstrip("/")


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "eval-fixture-pin/1"})
    return urllib.request.urlopen(req, timeout=timeout)


def main(argv=None):
    ap = argparse.ArgumentParser(description="pin the q12 fixture model")
    ap.add_argument("repo_id")
    ap.add_argument("--revision", default="main")
    ap.add_argument("--dest", required=True, help="where to download the files (local-path copy)")
    ap.add_argument("--out-dir", default=HERE)
    a = ap.parse_args(argv)

    api = "%s/api/models/%s/revision/%s" % (BASE, a.repo_id, urllib.parse.quote(a.revision, safe=""))
    with get(api) as r:
        meta = json.loads(r.read().decode("utf-8"))
    sha = meta.get("sha")
    if not sha:
        sys.exit("the API did not return a commit sha: %s" % api)
    files = sorted(s["rfilename"] for s in meta.get("siblings", []))
    tags = meta.get("tags") or []
    lic = [t.split(":", 1)[1] for t in tags if t.startswith("license:")]
    print("repo %s revision %s -> %s, %d files, gated=%r, license=%s"
          % (a.repo_id, a.revision, sha, len(files), meta.get("gated"), ",".join(lic) or "?"))

    os.makedirs(a.dest, exist_ok=True)
    out_files = []
    for name in files:
        url = "%s/%s/resolve/%s/%s" % (BASE, a.repo_id, sha, urllib.parse.quote(name))
        path = os.path.join(a.dest, name)
        os.makedirs(os.path.dirname(path) or a.dest, exist_ok=True)
        h, size = hashlib.sha256(), 0
        with get(url, timeout=600) as r, open(path, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                h.update(b)
                f.write(b)
                size += len(b)
        out_files.append({"path": name, "size": size, "sha256": h.hexdigest()})
        print("  %-40s %12d  %s" % (name, size, h.hexdigest()))

    cfg = {}
    cfg_path = os.path.join(a.dest, "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            c = json.load(f)
        for k in ("model_type", "architectures", "quantization", "quantization_config", "num_hidden_layers",
                  "hidden_size", "intermediate_size", "vocab_size", "tie_word_embeddings"):
            if k in c:
                cfg[k] = c[k]
    pin = {
        "repo_id": a.repo_id, "requested_revision": a.revision, "revision": sha,
        "gated": meta.get("gated"), "private": meta.get("private"), "license_tags": lic,
        "config": cfg, "files": out_files,
        "total_bytes": sum(f["size"] for f in out_files),
        "pinned_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parameter_count_note": "fill in from the base model card (must be at most 3B)",
    }
    with open(os.path.join(a.out_dir, "model_pin.json"), "w", encoding="utf-8") as f:
        json.dump(pin, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(a.out_dir, "model_pin.env"), "w") as f:
        f.write("REPO_ID=%s\nREVISION=%s\n" % (a.repo_id, sha))
    with open(os.path.join(a.out_dir, "model_files.sha256"), "w") as f:
        for x in out_files:
            f.write("%s  %s\n" % (x["sha256"], x["path"]))
    print("wrote model_pin.json, model_pin.env, model_files.sha256 to %s" % a.out_dir)
    print("check: gated must be false; quantization bits must be 4; record the parameter count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
