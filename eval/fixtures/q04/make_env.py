#!/usr/bin/env python3
"""Write the q04 sample .env (fake secrets, generated at test time).

  python3 make_env.py OUT_ENV VALUES_FILE [--version 1|2] [--seed q04-v1]

OUT_ENV      the plaintext .env to create (normally /work/team-app/.env in
             developer A's sandbox)
VALUES_FILE  one secret value per line, for check_history.sh and
             check_values.sh. It must live outside every git work tree (for
             example /opt/eval/state/q04/values-v1.txt), or a `git add .`
             in the team repo could commit it.
--version 2  the rotated values used after developer B is removed (same keys,
             different values)

Five KEY=VALUE lines, no comments, no quotes; every value is a secret,
starts with a letter and uses only [A-Za-z0-9], 24 to 40 characters, with no
vendor-specific prefix. The same seed and version always give the same file
(SHA-256 counter stream, independent of the Python version). Nothing here is
ever committed.

Python 3.9+ standard library only. Exit 0 ok, 2 refused or usage error.
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ["DB_PASSWORD", "API_TOKEN", "SESSION_SECRET", "SMTP_PASSWORD", "WEBHOOK_SIGNING_KEY"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ALNUM = LETTERS + "0123456789"


class DetRNG:
    def __init__(self, seed):
        self.seed = seed.encode("utf-8")
        self.counter = 0
        self.buf = b""

    def _take(self, n):
        while len(self.buf) < n:
            self.buf += hashlib.sha256(self.seed + b":" + str(self.counter).encode()).digest()
            self.counter += 1
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def below(self, n):
        limit = (1 << 32) - ((1 << 32) % n)
        while True:
            x = int.from_bytes(self._take(4), "big")
            if x < limit:
                return x % n


def git_root(path):
    cur = os.path.realpath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_env")
    ap.add_argument("values_file")
    ap.add_argument("--version", type=int, choices=[1, 2], default=1)
    ap.add_argument("--seed", default="q04-v1")
    a = ap.parse_args()

    own_repo = git_root(HERE)
    env_dir = os.path.dirname(os.path.abspath(a.out_env)) or "."
    if own_repo and git_root(env_dir) == own_repo:
        print("error: OUT_ENV is inside the pickfit repository; write it in the team repo",
              file=sys.stderr)
        return 2
    vals_dir = os.path.dirname(os.path.abspath(a.values_file)) or "."
    os.makedirs(vals_dir, exist_ok=True)
    if git_root(vals_dir):
        print("error: VALUES_FILE is inside a git work tree (%s); keep it outside every repo"
              % git_root(vals_dir), file=sys.stderr)
        return 2

    rng = DetRNG("%s#v%d" % (a.seed, a.version))
    values = []
    for _ in KEYS:
        n = 24 + rng.below(17)
        values.append(LETTERS[rng.below(len(LETTERS))]
                      + "".join(ALNUM[rng.below(len(ALNUM))] for _ in range(n - 1)))
    text = "".join("%s=%s\n" % (k, v) for k, v in zip(KEYS, values))
    with open(a.out_env, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
    with open(a.values_file, "w", encoding="ascii", newline="\n") as f:
        f.write("".join(v + "\n" for v in values))
    print("wrote %s (%d keys, version %d) and %s" % (a.out_env, len(KEYS), a.version,
                                                     a.values_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
