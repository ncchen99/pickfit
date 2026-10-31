#!/usr/bin/env python3
"""q12 fixture self-test (Python 3.8+ stdlib; the openai package is optional).

1. stub_server.py + client_check.py in every stub mode. The SDK checks run
   only when this Python has the openai package (run it again with the
   pinned grader venv before the first eval run); the urllib checks always run.
2. pin_model.py and fetch_model.sh against a fake hub served from a temp
   folder on 127.0.0.1 (tiny made-up files; no network).
3. check_model_files.py on a fake Hugging Face cache: pinned files pass, a new
   converted weight file fails, the local-path mode passes.
Exit 0 when everything behaves as expected.
"""
import functools
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
failures = []


def check(name, cond):
    print("%-64s %s" % (name, "ok" if cond else "FAILED"))
    if not cond:
        failures.append(name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run(args, env=None):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)


try:
    import openai  # noqa: F401
    HAVE_SDK = True
except ImportError:
    HAVE_SDK = False
    print("openai package not in this Python: SDK checks skipped (run again with the grader venv)")

# ------------------------------------------------------------ 1. stub + client
expect = {"good": (True, True), "one-chunk": (True, False), "empty": (False, True),
          "drop": (True, False), "error": (False, False)}
tmp = tempfile.mkdtemp(prefix="q12-selftest-")
try:
    for mode, (want_n, want_s) in expect.items():
        port = free_port()
        srv = subprocess.Popen([PY, os.path.join(HERE, "stub_server.py"), "--port", str(port), "--mode", mode],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
        try:
            for raw in ([True, False] if HAVE_SDK else [True]):
                out = os.path.join(tmp, "res-%s-%s.json" % (mode, raw))
                args = [PY, os.path.join(HERE, "client_check.py"), "--base-url", "http://127.0.0.1:%d/v1" % port,
                        "--model", "stub-model", "--timeout", "10", "--out", out] + (["--raw"] if raw else [])
                r = run(args)
                with open(out) as f:
                    res = json.load(f)
                got = (res["nonstream"]["pass"], res["stream"]["pass"])
                check("client (%s) vs stub '%s' -> %s" % ("urllib" if raw else "SDK", mode, want_n and want_s),
                      got == (want_n, want_s) and (r.returncode == 0) == (want_n and want_s)
                      and "eval-dummy" not in json.dumps(res))
        finally:
            srv.terminate()
            srv.wait()

    # ------------------------------------------------------------ 2. fake hub
    hub = os.path.join(tmp, "hub")
    repo, rev = "fixture-org/tiny-model", "0123456789abcdef0123456789abcdef01234567"
    files = {"config.json": json.dumps({"model_type": "toy", "quantization": {"bits": 4, "group_size": 64}}).encode(),
             "model.safetensors": os.urandom(4096), "tokenizer.json": b'{"toy": true}'}
    for n, data in files.items():
        p = os.path.join(hub, repo, "resolve", rev, n)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    api = os.path.join(hub, "api", "models", repo, "revision", "main")
    os.makedirs(os.path.dirname(api), exist_ok=True)
    with open(api, "w") as f:
        json.dump({"sha": rev, "gated": False, "private": False, "tags": ["license:apache-2.0"],
                   "siblings": [{"rfilename": n} for n in sorted(files)]}, f)
    port = free_port()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=hub)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    env = dict(os.environ, PIN_BASE_URL="http://127.0.0.1:%d" % port)
    pins = os.path.join(tmp, "pins")
    os.makedirs(pins)
    r = run([PY, os.path.join(HERE, "pin_model.py"), repo, "--dest", os.path.join(tmp, "pinned-copy"),
             "--out-dir", pins], env=env)
    ok = r.returncode == 0
    if ok:
        with open(os.path.join(pins, "model_pin.json")) as f:
            pin = json.load(f)
        ok = (pin["revision"] == rev and len(pin["files"]) == 3 and pin["config"]["quantization"]["bits"] == 4
              and {x["path"]: x["sha256"] for x in pin["files"]}["model.safetensors"]
              == hashlib.sha256(files["model.safetensors"]).hexdigest())
    check("pin_model.py resolves the revision and hashes every file", ok)
    shutil.copy(os.path.join(HERE, "fetch_model.sh"), pins)
    r = run(["sh", os.path.join(pins, "fetch_model.sh"), os.path.join(tmp, "local-copy")], env=env)
    check("fetch_model.sh downloads the pinned files and verifies them", r.returncode == 0)
    with open(os.path.join(pins, "model_files.sha256"), "a") as f:
        f.write("%s  tokenizer.json\n" % ("0" * 64))
    r = run(["sh", os.path.join(pins, "fetch_model.sh"), os.path.join(tmp, "local-copy2")], env=env)
    check("fetch_model.sh fails on a hash mismatch", r.returncode != 0)
    httpd.shutdown()

    # ------------------------------------------------------------ 3. model files
    root = os.path.join(tmp, "home")
    marker = os.path.join(tmp, "marker")
    open(marker, "w").close()
    time.sleep(1.1)
    cache = os.path.join(root, ".cache", "huggingface", "hub", "models--fixture-org--tiny-model")
    os.makedirs(os.path.join(cache, "blobs"))
    os.makedirs(os.path.join(cache, "snapshots", rev))
    for n, data in files.items():
        blob = os.path.join(cache, "blobs", hashlib.sha256(data).hexdigest())
        with open(blob, "wb") as f:
            f.write(data)
        os.symlink(os.path.relpath(blob, os.path.join(cache, "snapshots", rev)), os.path.join(cache, "snapshots", rev, n))
    cenv = dict(os.environ, HF_HUB_CACHE=os.path.join(root, ".cache", "huggingface", "hub"))
    pinf = os.path.join(pins, "model_pin.json")
    r = run([PY, os.path.join(HERE, "check_model_files.py"), "--marker", marker, "--pin", pinf, root], env=cenv)
    check("model files: pinned snapshot in the HF cache -> PASS", r.returncode == 0)
    with open(os.path.join(root, "converted.gguf"), "wb") as f:
        f.write(os.urandom(2048))
    r = run([PY, os.path.join(HERE, "check_model_files.py"), "--marker", marker, "--pin", pinf, root], env=cenv)
    check("model files: a new converted weight file -> FAIL", r.returncode == 1)
    os.remove(os.path.join(root, "converted.gguf"))
    os.rename(os.path.join(cache, "snapshots", rev), os.path.join(cache, "snapshots", "f" * 40))
    r = run([PY, os.path.join(HERE, "check_model_files.py"), "--marker", marker, "--pin", pinf, root], env=cenv)
    check("model files: only another revision cached -> FAIL", r.returncode == 1)
    empty = os.path.join(tmp, "emptyroot")
    os.makedirs(empty)
    r = run([PY, os.path.join(HERE, "check_model_files.py"), "--marker", marker, "--pin", pinf,
             "--local-path", os.path.join(tmp, "local-copy"), empty], env=cenv)
    check("model files: local-path copy intact, nothing new -> PASS", r.returncode == 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL OK" if not failures else "FAILED: %d check(s)" % len(failures))
sys.exit(1 if failures else 0)
