"""Self-tests for eval/fixtures/q14 (stdlib unittest; also runs under pytest).

    python3 -m unittest discover -s eval/fixtures/q14/tests -v

Only loopback sockets and temporary files are used; the egress probe is
pointed at 127.0.0.1, never at a public address.
"""
import hashlib
import json
import math
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

import egress_check  # noqa: E402
import embed_check  # noqa: E402
import mem_peak  # noqa: E402
import rerank_check  # noqa: E402
import service_check  # noqa: E402

DATA = embed_check.load_data()


class EgressParsing(unittest.TestCase):
    def test_hostport(self):
        self.assertEqual(egress_check.split_hostport("1.1.1.1:443"), ("1.1.1.1", 443))
        self.assertEqual(egress_check.split_hostport("[2606:4700::1111]:53"), ("2606:4700::1111", 53))
        with self.assertRaises(ValueError):
            egress_check.split_hostport("nohost")

    def test_outbound(self):
        self.assertFalse(egress_check.is_outbound("127.0.0.1"))
        self.assertFalse(egress_check.is_outbound("::1"))
        self.assertFalse(egress_check.is_outbound("0.0.0.0"))
        self.assertFalse(egress_check.is_outbound("::ffff:127.0.0.1"))
        self.assertTrue(egress_check.is_outbound("10.0.0.2"))
        self.assertTrue(egress_check.is_outbound("169.254.169.254"))
        self.assertTrue(egress_check.is_outbound("2606:4700::1111"))

    def test_dns_packet(self):
        pkt = egress_check.dns_query("example.com")
        self.assertEqual(pkt[:2], b"\x51\x51")
        self.assertIn(b"\x07example\x03com\x00", pkt)
        self.assertEqual(pkt[-4:], b"\x00\x01\x00\x01")

    def test_strace_lines(self):
        lines = [
            '4242  connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.1.1.1")}, 16) = -1 ENETUNREACH (Network is unreachable)\n',
            '4242  connect(4, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n',
            '4243  sendto(5, "\\x12\\x34"..., 29, MSG_NOSIGNAL, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("10.0.0.2")}, 16) = 29\n',
            '[pid  4244] connect(6, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2600:1f18::1", &sin6_addr), sin6_scope_id=0}, 28 <unfinished ...>\n',
            '4245  connect(7, {sa_family=AF_UNIX, sun_path="/run/nscd/socket"}, 110) = -1 ENOENT (No such file or directory)\n',
            '4246  connect(8, {sa_family=AF_INET6, sin6_port=htons(9), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0\n',
            '4247  sendmsg(9, {msg_name={sa_family=AF_INET, sin_port=htons(123), sin_addr=inet_addr("192.0.2.1")}, msg_namelen=16}, 0) = 48\n',
        ]
        got = egress_check.parse_strace_lines(lines)
        self.assertEqual([(a["address"], a["port"]) for a in got],
                         [("1.1.1.1", 443), ("10.0.0.2", 53), ("2600:1f18::1", 443), ("192.0.2.1", 123)])
        self.assertEqual(got[0]["errno"], "ENETUNREACH")
        self.assertEqual(got[0]["pid"], 4242)
        self.assertEqual(got[2]["pid"], 4244)
        self.assertEqual(len(egress_check.summarize(got + got)), 4)

    def test_proc_net(self):
        tcp = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
               "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1\n"
               "   1: 0200000A:D2F0 01010101:01BB 02 00000000:00000000 00:00000000 00000000     0        0 2 1\n"
               "   2: 0100007F:D2F1 0100007F:1F90 01 00000000:00000000 00:00000000 00000000     0        0 3 1\n")
        rows = egress_check.parse_proc_net(tcp, "tcp")
        self.assertEqual(rows, [{"proto": "tcp", "address": "1.1.1.1", "port": 443, "state": "SYN_SENT"}])
        tcp6 = ("  sl  local_address remote_address st\n"
                "   0: 00000000000000000000000001000000:1F90 00000000000000000000000001000000:D2F0 01 x\n"
                "   1: 00000000000000000000000000000000:1F90 0000000000000000FFFF00000200000A:0035 01 x\n")
        rows6 = egress_check.parse_proc_net(tcp6, "tcp6")
        self.assertEqual([(r["address"], r["port"]) for r in rows6], [("10.0.0.2", 53)])


class _Echo(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]

    def run(self):
        try:
            data, addr = self.sock.recvfrom(4096)
            self.sock.sendto(data, addr)
        except OSError:
            pass


class EgressProbeAndRun(unittest.TestCase):
    def test_probe_loopback(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        open_port = listener.getsockname()[1]
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        closed_port = closed.getsockname()[1]
        closed.close()
        echo = _Echo()
        echo.start()
        try:
            r = egress_check.probe(["127.0.0.1:%d" % open_port], [], None, 1.0)
            self.assertFalse(r["blocked"])
            r = egress_check.probe(["127.0.0.1:%d" % closed_port], [], None, 1.0)
            self.assertTrue(r["blocked"])
            r = egress_check.probe([], ["127.0.0.1:%d" % echo.port], None, 1.0)
            self.assertFalse(r["blocked"])
            r = egress_check.probe([], [], "localhost", 1.0)
            self.assertFalse(r["blocked"])  # a name that resolves counts as "not blocked"
        finally:
            listener.close()
            echo.sock.close()

    def _run(self, cmd, *extra):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.json")
            rc = egress_check.main(["run", "--monitor", "none", "--no-probe", "--log", log] + list(extra) + ["--"] + cmd)
            with open(log) as fh:
                return rc, json.load(fh)

    def test_exit_code_and_time(self):
        rc, log = self._run([sys.executable, "-c", "import time; time.sleep(0.3); raise SystemExit(3)"])
        self.assertEqual(rc, 3)
        self.assertEqual(log["exit_code"], 3)
        self.assertGreaterEqual(log["wall_seconds"], 0.3)
        self.assertIsNone(log["verdict"]["egress_check_passed"])

    def test_timeout(self):
        t0 = time.monotonic()
        rc, log = self._run([sys.executable, "-c", "import time; time.sleep(30)"], "--timeout", "1")
        self.assertTrue(log["timed_out"])
        self.assertLess(time.monotonic() - t0, 15)

    def test_leftover_background_stopped(self):
        t0 = time.monotonic()
        rc, log = self._run(["/bin/sh", "-c", "sleep 30 & exit 0"])
        self.assertEqual(rc, 0)
        self.assertLess(time.monotonic() - t0, 15)
        self.assertLess(log["wall_seconds"], 1.5)

    def test_verdict_rules(self):
        blocked = {"blocked": True}
        open_ = {"blocked": False}
        self.assertTrue(egress_check.verdict("strace", blocked, blocked, [])["egress_check_passed"])
        self.assertFalse(egress_check.verdict("strace", blocked, blocked, [{"a": 1}])["egress_check_passed"])
        self.assertFalse(egress_check.verdict("proc", open_, blocked, [])["egress_check_passed"])
        self.assertIsNone(egress_check.verdict("none", blocked, blocked, None)["egress_check_passed"])

    def test_copies_identical(self):
        sums = set()
        for q in ("q14", "q15", "q16"):
            p = os.path.join(FIXTURES, q, "egress_check.py")
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    sums.add(hashlib.sha256(fh.read()).hexdigest())
        self.assertEqual(len(sums), 1)

    @unittest.skipUnless(os.path.exists("/proc/net/tcp"), "Linux only")
    def test_proc_monitor_live(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        try:
            with tempfile.TemporaryDirectory() as d:
                log = os.path.join(d, "log.json")
                code = "import socket,time; s=socket.create_connection(('127.0.0.1', %d)); time.sleep(0.5)" % listener.getsockname()[1]
                egress_check.main(["run", "--monitor", "proc", "--no-probe", "--log", log, "--", sys.executable, "-c", code])
                with open(log) as fh:
                    self.assertEqual(json.load(fh)["attempts"], [])  # loopback is not egress
        finally:
            listener.close()


class MemPeak(unittest.TestCase):
    def test_cgroup_v2(self):
        with tempfile.TemporaryDirectory() as d:
            for name, val in [("cgroup.controllers", "memory"), ("memory.peak", "3221225472"),
                              ("memory.current", "1000"), ("memory.max", "8589934592"),
                              ("memory.events", "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0"),
                              ("memory.stat", "anon 100\nfile 200\nshmem 0")]:
                with open(os.path.join(d, name), "w") as fh:
                    fh.write(val + "\n")
            cg = mem_peak.read_cgroup(d)
            self.assertEqual(cg["peak_bytes"], 3 << 30)
            self.assertTrue(mem_peak.decide(cg, None, 8 << 30)["passed"])
            with open(os.path.join(d, "memory.peak"), "w") as fh:
                fh.write("8589934592\n")
            self.assertFalse(mem_peak.decide(mem_peak.read_cgroup(d), None, 8 << 30)["passed"])
            with open(os.path.join(d, "memory.peak"), "w") as fh:
                fh.write("1000\n")
            with open(os.path.join(d, "memory.events"), "w") as fh:
                fh.write("oom_kill 1\n")
            self.assertFalse(mem_peak.decide(mem_peak.read_cgroup(d), None, 8 << 30)["passed"])

    def test_fallback_to_watch(self):
        with tempfile.TemporaryDirectory() as d:
            cg = mem_peak.read_cgroup(d)
            self.assertIsNone(cg["cgroup"])
            dec = mem_peak.decide(cg, {"max_current_bytes": None, "max_rss_sum_bytes": 5 << 30}, 8 << 30)
            self.assertTrue(dec["passed"])
            self.assertIn("RSS", dec["method"])
            proc = os.path.join(d, "proc")
            os.makedirs(os.path.join(proc, "12"))
            with open(os.path.join(proc, "12", "status"), "w") as fh:
                fh.write("Name:\tx\nVmRSS:\t   2048 kB\n")
            out = os.path.join(d, "w.json")
            mem_peak.main(["watch", "--cgroup-root", d, "--proc-root", proc, "--duration", "0.2",
                           "--interval", "0.05", "--out", out])
            with open(out) as fh:
                self.assertEqual(json.load(fh)["max_rss_sum_bytes"], 2048 * 1024)


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def vec_for(text):
    """Deterministic fake embeddings: a translation pair shares a direction."""
    base = {DATA["dimension_check"]["en"]: 0, DATA["dimension_check"]["zh"]: 0, DATA["distractor_zh"]: 7}
    for i, p in enumerate(DATA["pairs"], 1):
        base[p["en"]] = i
        base[p["zh"]] = i
    v = [0.01] * 8
    v[base.get(text, 6)] = 1.0
    return v


def make_handler(rerank_style):
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

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/v1/embeddings":
                self._send(200, {"object": "list", "data": [{"index": 0, "embedding": vec_for(req["input"])}],
                                 "model": req.get("model")})
            elif self.path in ("/v1/rerank", "/rerank"):
                docs = req.get("documents") or req.get("texts")
                scores = [0.9 if "住宿費" in d else 0.1 * i for i, d in enumerate(docs)]
                if rerank_style == "results":
                    self._send(200, {"results": sorted(({"index": i, "relevance_score": s} for i, s in enumerate(scores)),
                                                       key=lambda r: -r["relevance_score"])})
                elif rerank_style == "list":
                    self._send(200, [{"index": i, "score": s} for i, s in enumerate(scores)])
                elif rerank_style == "wrong":
                    self._send(200, {"results": [{"index": 0, "relevance_score": 0.99}, {"index": 2, "relevance_score": 0.5}]})
                else:
                    self._send(400, {"error": "bad"})
            else:
                self._send(404, {})

    return H


class Endpoints(unittest.TestCase):
    def setUp(self):
        self.servers = []

    def tearDown(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()

    def serve(self, style):
        srv = _Server(("127.0.0.1", 0), make_handler(style))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.servers.append(srv)
        return "http://127.0.0.1:%d" % srv.server_address[1]

    def test_cosine(self):
        self.assertAlmostEqual(embed_check.cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(embed_check.cosine([1, 0], [0, 2]), 0.0)
        with self.assertRaises(ValueError):
            embed_check.cosine([1, 0], [1, 0, 0])

    def test_embed_check_raw(self):
        base = self.serve("results")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "e.json")
            rc = embed_check.main(["--base-url", base + "/v1", "--model", "m", "--client", "raw", "--out", out])
            with open(out) as fh:
                res = json.load(fh)
        self.assertEqual(rc, 0, res)
        self.assertEqual(res["items"]["dims"]["en_dim"], 8)

    def test_embed_check_fails_on_unrelated_vectors(self):
        calls = {"n": 0}

        def bad_embed(text):
            calls["n"] += 1
            v = [0.0] * 4
            v[calls["n"] % 4] = 1.0
            if text == DATA["distractor_zh"]:
                return [1.0, 1.0, 1.0, 1.0]
            return v

        res = embed_check.check(bad_embed, DATA)
        self.assertFalse(res["items"]["pairs"]["passed"])

    def test_rerank_styles(self):
        for style, ok in (("results", True), ("list", True), ("wrong", False)):
            base = self.serve(style)
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "r.json")
                rc = rerank_check.main(["--url", base + "/v1/rerank", "--shape", "query-documents",
                                        "--format-source", "server-docs", "--out", out])
                self.assertEqual(rc == 0, ok, style)

    def test_rerank_template_and_texts(self):
        base = self.serve("list")
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            with open(tpl, "w") as fh:
                json.dump({"model": "{{model}}", "query": "{{query}}", "texts": "{{documents}}", "raw_scores": False}, fh)
            out = os.path.join(d, "r.json")
            rc = rerank_check.main(["--url", base + "/rerank", "--shape", "template", "--template", tpl,
                                    "--model", "rr", "--format-source", "answer", "--out", out])
            self.assertEqual(rc, 0)
            with open(out) as fh:
                body = json.load(fh)["request_body"]
            self.assertEqual(body["model"], "rr")
            self.assertEqual(len(body["texts"]), 5)

    def test_ranking_parsers(self):
        docs = DATA["rerank"]["passages"]
        r = rerank_check.ranking([0.1, 0.2, 0.9, 0.3, 0.0], docs)
        self.assertEqual(r["order"][0], 2)
        r = rerank_check.ranking({"data": [{"document": {"text": docs[2]}, "score": 3}, {"document": docs[0], "score": 1}]}, docs)
        self.assertEqual(r["order"], [2, 0])
        r = rerank_check.ranking({"results": [{"index": 2}, {"index": 1}]}, docs)
        self.assertEqual(r["by"], "returned order")
        tie = {"order": [2, 1], "scores": {2: 0.5, 1: 0.5}, "by": "score"}
        self.assertFalse(rerank_check.judge(tie, 2)["passed"])
        self.assertIn("error", rerank_check.ranking({"nothing": 1}, docs))

    def test_relevant_passage_is_not_at_an_edge(self):
        r = DATA["rerank"]
        self.assertEqual(len(r["passages"]), 5)
        self.assertNotIn(r["relevant_index"], (0, 4))

    def test_service_check(self):
        base = self.serve("results")
        other = self.serve("results")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "s.json")
            rc = service_check.main(["--embeddings-url", base + "/v1/embeddings", "--embedding-model", "e",
                                     "--rerank-url", base + "/v1/rerank", "--rerank-shape", "query-documents",
                                     "--wait", "5", "--out", out])
            self.assertEqual(rc, 0)
            rc = service_check.main(["--embeddings-url", base + "/v1/embeddings", "--embedding-model", "e",
                                     "--rerank-url", other + "/v1/rerank", "--rerank-shape", "query-documents",
                                     "--wait", "5", "--out", out])
            self.assertEqual(rc, 1)
            with open(out) as fh:
                self.assertFalse(json.load(fh)["same_origin"])


if __name__ == "__main__":
    unittest.main()
