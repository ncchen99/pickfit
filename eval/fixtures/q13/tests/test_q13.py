"""Self-tests for eval/fixtures/q13 (stdlib unittest; also runs under pytest).

    python3 -m unittest discover -s eval/fixtures/q13/tests -v

Only loopback sockets and temporary files are used.
"""
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bench  # noqa: E402
import disk_usage  # noqa: E402
import gguf_info  # noqa: E402


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def make_handler(mode):
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, doc):
            body = json.dumps(doc).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": "fixture-model"}]})
            else:
                self._send(404, {"error": "no"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            tokens = req.get("max_tokens", 16)
            if tokens > 1:
                if mode == "serial":
                    with lock:
                        time.sleep(0.15)
                else:
                    time.sleep(0.15)
            doc = {"choices": [{"message": {"role": "assistant", "content": "water " * tokens},
                                "finish_reason": "length"}]}
            if mode != "nousage":
                doc["usage"] = {"prompt_tokens": 20, "completion_tokens": tokens, "total_tokens": tokens + 20}
            self._send(200, doc)

    return H


class BenchTest(unittest.TestCase):
    def _run(self, mode):
        srv = _Server(("127.0.0.1", 0), make_handler(mode))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "bench.json")
                rc = bench.main(["--base-url", "http://127.0.0.1:%d/v1" % srv.server_address[1],
                                 "--rounds", "2", "--wait", "10", "--out", out])
                with open(out) as fh:
                    return rc, json.load(fh)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_parallel_server_passes(self):
        rc, out = self._run("parallel")
        self.assertEqual(rc, 0)
        self.assertEqual(out["model"], "fixture-model")
        self.assertTrue(out["items"]["concurrent_ok"]["passed"])
        self.assertGreater(out["items"]["throughput"]["ratio"], 2.5)

    def test_serial_server_fails_throughput(self):
        rc, out = self._run("serial")
        self.assertEqual(rc, 1)
        self.assertTrue(out["items"]["concurrent_ok"]["passed"])
        self.assertFalse(out["items"]["throughput"]["passed"])
        self.assertLess(out["items"]["throughput"]["ratio"], 1.5)

    def test_missing_usage_fails(self):
        rc, out = self._run("nousage")
        self.assertEqual(rc, 1)
        self.assertIn("usage missing", out["items"]["throughput"]["reason"])

    def test_unreachable_server(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "b.json")
            rc = bench.main(["--base-url", "http://127.0.0.1:9/v1", "--wait", "1", "--out", out])
            self.assertEqual(rc, 1)

    def test_prompt_is_frozen_shape(self):
        with open(os.path.join(ROOT, "prompt.json")) as fh:
            p = json.load(fh)
        self.assertEqual((p["max_tokens"], p["temperature"], p["concurrency"]), (128, 0, 4))


class DiskTest(unittest.TestCase):
    def test_growth_rule(self):
        with tempfile.TemporaryDirectory() as d:
            before, after = os.path.join(d, "b.json"), os.path.join(d, "a.json")
            area = os.path.join(d, "area")
            os.mkdir(area)
            disk_usage.main(["snapshot", "--mount", area, "--out", before])
            with open(os.path.join(area, "blob"), "wb") as fh:
                fh.write(os.urandom(1 << 20))
            disk_usage.main(["snapshot", "--mount", area, "--out", after])
            self.assertEqual(disk_usage.main(["compare", before, after, "--model-bytes", str(100 << 20)]), 0)
            self.assertEqual(disk_usage.main(["compare", before, after, "--model-bytes", str(10 << 20)]), 1)

    def test_mount_selection(self):
        text = "\n".join([
            "overlay / overlay rw,relatime 0 0",
            "proc /proc proc rw,nosuid 0 0",
            "tmpfs /dev/shm tmpfs rw,nosuid 0 0",
            "/dev/vdb /models ext4 ro,relatime 0 0",
            "/dev/vdc /models/sub ext4 rw 0 0",
            "cgroup2 /sys/fs/cgroup cgroup2 rw 0 0",
            "/dev/vdd /data\\040dir ext4 rw 0 0",
        ])
        rows = disk_usage.parse_mounts(text)
        self.assertEqual(rows[-1]["mountpoint"], "/data dir")
        keep = [r for r in rows if "rw" in r["options"] and r["fstype"] not in disk_usage.PSEUDO
                and not any(disk_usage._under(r["mountpoint"], ex) for ex in ["/models"])]
        self.assertEqual([r["mountpoint"] for r in keep], ["/", "/dev/shm", "/data dir"])


def _gguf_string(s):
    b = s.encode()
    return struct.pack("<Q", len(b)) + b


def write_gguf(path):
    kv = []
    kv.append(_gguf_string("general.architecture") + struct.pack("<I", 8) + _gguf_string("llama"))
    kv.append(_gguf_string("general.name") + struct.pack("<I", 8) + _gguf_string("Tiny Fixture"))
    kv.append(_gguf_string("general.file_type") + struct.pack("<I", 4) + struct.pack("<I", 15))
    kv.append(_gguf_string("llama.context_length") + struct.pack("<I", 4) + struct.pack("<I", 2048))
    toks = b"".join(_gguf_string(t) for t in ["<s>", "</s>", "a"] * 10)
    kv.append(_gguf_string("tokenizer.ggml.tokens") + struct.pack("<I", 9) + struct.pack("<IQ", 8, 30) + toks)
    kv.append(_gguf_string("tokenizer.ggml.scores") + struct.pack("<I", 9) + struct.pack("<IQ", 6, 3)
              + struct.pack("<fff", 0.0, 0.5, 1.0))
    kv.append(_gguf_string("tokenizer.chat_template") + struct.pack("<I", 8) + _gguf_string("{{ messages }}"))
    with open(path, "wb") as fh:
        fh.write(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv)) + b"".join(kv) + b"\0" * 64)


class GgufTest(unittest.TestCase):
    def test_header(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.gguf")
            write_gguf(p)
            info = gguf_info.read_header(p)
            self.assertEqual(info["general.architecture"], "llama")
            self.assertEqual(info["llama.context_length"], 2048)
            self.assertEqual(info["vocab_size"], 30)
            self.assertTrue(info["has_chat_template"])
            self.assertEqual(len(gguf_info.sha256_file(p)), 64)

    def test_rejects_non_gguf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.bin")
            with open(p, "wb") as fh:
                fh.write(b"NOPE" + b"\0" * 32)
            with self.assertRaises(ValueError):
                gguf_info.read_header(p)


if __name__ == "__main__":
    unittest.main()
