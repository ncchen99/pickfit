"""OLLAMA_NO_CLOUD reaches only the Ollama server the graders' start scripts launch (9.3 C.5).

For q18, q19 and q20 the start script sets OLLAMA_NO_CLOUD=1 as a prefix of its one
`"$OLLAMA" serve` command, never with export, so an Ollama or any other server an answer's
own steps start runs without it. This runs each script's real serve line with a stand-in
`ollama` that records its environment, then starts the stand-in the way an answer would.
Offline, no Ollama needed: python3 test_ollama_scope.py
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = {q: os.path.join(HERE, "..", q, name) for q, name in
           (("q18", "start_fixture_servers.sh"), ("q19", "start_fixture_servers.sh"), ("q20", "start_ollama.sh"))}


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def commands(path):
    """The script's commands with backslash continuations joined, comments dropped."""
    out, cur = [], ""
    for line in read(path).splitlines():
        if not cur and line.lstrip().startswith("#"):
            continue
        cur += line.rstrip("\\").rstrip() + " " if line.rstrip().endswith("\\") else line
        if not line.rstrip().endswith("\\"):
            out.append(cur.strip())
            cur = ""
    return out


class NoCloudScope(unittest.TestCase):
    def test_only_the_graders_serve_command_carries_it(self):
        for q, path in SCRIPTS.items():
            with self.subTest(q=q):
                hits = [c for c in commands(path) if "OLLAMA_NO_CLOUD" in c]
                self.assertEqual(len(hits), 1, hits)
                self.assertTrue(hits[0].startswith("OLLAMA_NO_CLOUD=1 "), hits[0])
                self.assertIn('"$OLLAMA" serve', hits[0])
                self.assertNotRegex(read(path), r"export\s+[^\n]*OLLAMA_NO_CLOUD")

    def test_nothing_else_in_the_fixtures_sets_it(self):
        root = os.path.join(HERE, "..")
        setters = []
        for dirpath, _, files in os.walk(root):
            for name in files:
                if not name.endswith((".sh", ".py", ".env", ".json")) or name == os.path.basename(__file__):
                    continue
                path = os.path.join(dirpath, name)
                text = "\n".join(x for x in read(path).splitlines() if not x.lstrip().startswith("#"))
                if re.search(r"OLLAMA_NO_CLOUD\s*=|OLLAMA_NO_CLOUD\"\s*:|disable_ollama_cloud", text):
                    setters.append(os.path.relpath(path, root))
        self.assertEqual(sorted(setters), sorted(os.path.relpath(p, root) for p in SCRIPTS.values()))

    def test_an_answers_own_server_runs_without_it(self):
        for q, path in SCRIPTS.items():
            with self.subTest(q=q), tempfile.TemporaryDirectory() as tmp:
                line = next(c for c in commands(path) if '"$OLLAMA" serve' in c)
                fake = os.path.join(tmp, "ollama")
                with open(fake, "w") as fh:
                    fh.write('#!/bin/sh\nenv > "$FAKE_ENV_DIR/$1.env"\n')
                os.chmod(fake, 0o755)
                script = "\n".join([
                    "set -e", 'export FAKE_ENV_DIR="%s"' % tmp,
                    'OLLAMA="%s"; STATE="%s"; OLLAMA_MODELS=/m; OLLAMA_CONTEXT_LENGTH=1' % (fake, tmp),
                    line, "wait",
                    '"$OLLAMA" answer-serve',  # an answer starting its own server from the same shell
                    'env > "$FAKE_ENV_DIR/shell.env"'])
                env = {k: v for k, v in os.environ.items() if k != "OLLAMA_NO_CLOUD"}
                subprocess.run(["sh", "-c", script], check=True, env=env, timeout=30)
                seen = lambda n: read(os.path.join(tmp, n + ".env")).splitlines()
                self.assertIn("OLLAMA_NO_CLOUD=1", seen("serve"))
                self.assertFalse([x for x in seen("answer-serve") if x.startswith("OLLAMA_NO_CLOUD=")])
                self.assertFalse([x for x in seen("shell") if x.startswith("OLLAMA_NO_CLOUD=")])


if __name__ == "__main__":
    unittest.main()
