"""Self-tests for eval/fixtures/q14 (stdlib unittest; also runs under pytest).

    python3 -m unittest discover -s eval/fixtures/q14/tests -v

Only loopback sockets and temporary files are used; the egress probe is
pointed at 127.0.0.1, never at a public address.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

import embed_check  # noqa: E402
import rerank_check  # noqa: E402
import service_check  # noqa: E402

DATA = embed_check.load_data()


# The egress and memory checks moved to eval/fixtures/_shared (tests in _shared/test_shared.py).


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
