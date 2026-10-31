#!/usr/bin/env python3
"""Frozen seeded log generator for eval q02.

Writes, into OUT_DIR (which must be outside this git repository):
  app.log        ordinary log lines plus six lines that each carry one fake
                 sensitive value: one AWS-format access key ID, one
                 GitHub-format personal access token, two email addresses
                 (example.com, example.org) and two public unicast IPv4
                 addresses
  manifest.json  the six values, their line numbers and the ordinary line
                 numbers, for check_clean.py

The fake values exist only in OUT_DIR at test time and are never committed.
The same seed always gives byte-identical output (a SHA-256 counter stream is
used instead of the `random` module, so the Python version does not matter).

  python3 gen_log.py OUT_DIR [--seed q02-v1]

Python 3.9+ standard library only. No network.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SEED = "q02-v1"
N_ORDINARY = 240

B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # AWS access key IDs use this alphabet
B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
AWS_PREFIX = "AK" + "IA"
GH_PREFIX = "gh" + "p_"

LEVELS = ["INFO"] * 14 + ["DEBUG"] * 3 + ["WARN"] * 2 + ["ERROR"]
PATHS = ["/api/orders", "/api/orders/items", "/api/users/profile", "/api/cart",
         "/api/v1/search", "/api/v2/inventory", "/static/css/main.css",
         "/static/js/app.js", "/static/img/logo.png", "/healthz", "/login",
         "/logout", "/checkout/confirm", "/admin/reports/daily"]
FILE_PATHS = ["/var/log/app/worker.log", "/srv/app/uploads/report.pdf",
              "/var/lib/app/cache/index.db", "/etc/app/settings.yaml",
              "/home/app/exports/orders.csv", "/tmp/app/session.lock",
              "/opt/app/templates/invoice.html"]
STATUSES = ["200"] * 10 + ["201", "204", "301", "302", "304", "400", "401",
                           "403", "404", "404", "409", "429", "500", "502", "503"]
FIRST = ["maria", "kenji", "olusegun", "priya", "lars", "ana", "wei", "fatima",
         "tomas", "aiko"]
LAST = ["ortiz", "tanaka", "adeyemi", "raman", "nilsson", "costa", "zhang",
        "haddad", "novak", "fujita"]
# Redaction labels a tool might print; a random part containing a 5-gram of
# one of these could look "unmasked" by coincidence, so such draws are redone.
LABELS = ["REDACTED", "redacted", "MASKED", "masked", "HIDDEN", "hidden",
          "SECRET", "secret", "TOKEN", "token", "XXXXX", "xxxxx", "PRIVATE"]
# IPv4 ranges that are not public unicast (RFC 6890 special-purpose registry,
# including every range the question names).
EXCLUDED_V4 = [("0.0.0.0", 8), ("10.0.0.0", 8), ("100.64.0.0", 10), ("127.0.0.0", 8),
               ("169.254.0.0", 16), ("172.16.0.0", 12), ("192.0.0.0", 24),
               ("192.0.2.0", 24), ("192.88.99.0", 24), ("192.168.0.0", 16),
               ("198.18.0.0", 15), ("198.51.100.0", 24), ("203.0.113.0", 24),
               ("224.0.0.0", 4), ("240.0.0.0", 4)]
STANDALONE = r"(?<![0-9A-Za-z]){}(?![0-9A-Za-z])"


class DetRNG:
    """Deterministic byte stream: SHA-256(seed:counter) blocks."""

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

    def choice(self, seq):
        return seq[self.below(len(seq))]

    def string(self, alphabet, n):
        return "".join(self.choice(alphabet) for _ in range(n))


def ip_to_int(s):
    a, b, c, d = (int(x) for x in s.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def is_public_unicast(octets):
    v = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
    for net, plen in EXCLUDED_V4:
        mask = ((1 << 32) - 1) ^ ((1 << (32 - plen)) - 1)
        if v & mask == ip_to_int(net):
            return False
    return True


def base62_pad6(n):
    s = ""
    while n:
        n, r = divmod(n, 62)
        s = B62[r] + s
    return s.rjust(6, "0")


def has_label_5gram(s):
    for lab in LABELS:
        for i in range(len(lab) - 4):
            if lab[i:i + 5] in s:
                return True
    return False


def timestamp(ms):
    # 2026-10-27T08:00:00.000Z plus ms
    total_s, milli = divmod(ms, 1000)
    h, rem = divmod(8 * 3600 + total_s, 3600)
    m, s = divmod(rem, 60)
    return "2026-10-27T%02d:%02d:%02d.%03dZ" % (h, m, s, milli)


def ordinary_line(rng, ts):
    lvl = rng.choice(LEVELS)
    kind = rng.below(4)
    if kind == 0:
        return "%s %s path=%s status=%s duration=%dms" % (
            ts, lvl, rng.choice(PATHS), rng.choice(STATUSES), 1 + rng.below(999))
    if kind == 1:
        return "%s %s %s %s %dms" % (ts, lvl, rng.choice(PATHS), rng.choice(STATUSES),
                                     1 + rng.below(999))
    if kind == 2:
        return "%s %s file=%s duration=%dms" % (ts, lvl, rng.choice(FILE_PATHS),
                                                1 + rng.below(999))
    return "%s %s path=%s status=%s duration=%d.%02ds" % (
        ts, lvl, rng.choice(PATHS), rng.choice(STATUSES), 1 + rng.below(9), 1 + rng.below(99))


def draw_values(rng):
    aws_rand = rng.string(B32, 16)
    gh_body = rng.string(B62, 30)
    gh_rand = gh_body + base62_pad6(zlib.crc32(gh_body.encode("ascii")) & 0xFFFFFFFF)
    f1, l1 = rng.choice(FIRST), rng.choice(LAST)
    f2, l2 = rng.choice(FIRST), rng.choice(LAST)
    local1 = "%s.%s" % (f1, l1)
    local2 = "%s.%s%d" % (f2, l2, 10 + rng.below(90))
    ips = []
    banned = {200, 201, 204}  # standalone numbers >= 100 used by ordinary lines
    while len(ips) < 2:
        o = [1 + rng.below(223), rng.below(256), 100 + rng.below(155), 100 + rng.below(155)]
        if not is_public_unicast(o) or o[2] == o[3] or o[2] in banned or o[3] in banned:
            continue
        if {o[0], o[1]} & {o[2], o[3]}:
            continue  # the first two octets may survive masking; they must not equal the last two
        used = {x for ip in ips for x in ip}
        if used & set(o):
            continue  # keep all octet numbers of the two IPs distinct
        ips.append(o)
    return {
        "aws_access_key_id": AWS_PREFIX + aws_rand,
        "github_pat": GH_PREFIX + gh_rand,
        "email_1": local1 + "@example.com",
        "email_2": local2 + "@example.org",
        "ipv4_1": ".".join(str(x) for x in ips[0]),
        "ipv4_2": ".".join(str(x) for x in ips[1]),
    }


TEMPLATES = {
    "aws_access_key_id": "{ts} WARN s3 uploader credentials aws_access_key_id={v}",
    "github_pat": "{ts} DEBUG git fetch Authorization: token {v}",
    "email_1": "{ts} INFO password reset requested for {v}",
    "email_2": "{ts} INFO invoice sent to {v}",
    "ipv4_1": "{ts} INFO connection accepted from {v}",
    "ipv4_2": "{ts} WARN rate limit exceeded for {v}",
}
ORDER = ["ipv4_1", "email_1", "aws_access_key_id", "ipv4_2", "github_pat", "email_2"]


def build(seed):
    for attempt in range(1000):
        rng = DetRNG("%s#%d" % (seed, attempt))
        vals = draw_values(rng)
        n_total = N_ORDINARY + len(ORDER)
        slots = set()
        while len(slots) < len(ORDER):
            slots.add(10 + rng.below(n_total - 20))
        slots = sorted(slots)
        clock = 0
        lines, kinds = [], []
        it = iter(ORDER)
        for i in range(n_total):
            clock += rng.below(3000)
            ts = timestamp(clock)
            if i in slots:
                k = next(it)
                lines.append(TEMPLATES[k].format(ts=ts, v=vals[k]))
                kinds.append(k)
            else:
                lines.append(ordinary_line(rng, ts))
                kinds.append(None)
        text = "\n".join(lines) + "\n"
        if self_consistent(vals, text):
            return vals, lines, kinds, attempt
    raise SystemExit("could not build a self-consistent log")


def random_part(kind, v):
    if kind in ("aws_access_key_id", "github_pat"):
        return v[4:]
    return None


def self_consistent(vals, text):
    """The masking checks must only be able to fire on the planted values."""
    l1, l2 = vals["email_1"].split("@")[0], vals["email_2"].split("@")[0]
    if l1 in l2 or l2 in l1:
        return False
    for v in vals.values():
        if text.count(v) != 1:
            return False
    for k, v in vals.items():
        rest = text.replace(v, "\x00")  # everything except this value, other values included
        rp = random_part(k, v)
        if rp is not None:
            if has_label_5gram(rp):
                return False
            if any(rp[i:i + 5] in rest for i in range(len(rp) - 4)):
                return False
        if k.startswith("email"):
            if v.split("@")[0] in rest:
                return False
        if k.startswith("ipv4"):
            a, b, c, d = v.split(".")
            for num in (c, d):
                if re.search(STANDALONE.format(num), rest):
                    return False
    return True


def repo_root(start):
    cur = os.path.realpath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--allow-in-repo", action="store_true",
                    help="testing only: allow OUT_DIR inside this git repository")
    a = ap.parse_args()
    out = os.path.realpath(a.out_dir)
    root = repo_root(HERE)
    if root and (out + os.sep).startswith(root + os.sep) and not a.allow_in_repo:
        print("error: OUT_DIR is inside the git repository %s; the fake values must "
              "never be committed. Use a directory outside it." % root, file=sys.stderr)
        return 2
    vals, lines, kinds, attempt = build(a.seed)
    os.makedirs(out, exist_ok=True)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    with open(os.path.join(out, "app.log"), "wb") as f:
        f.write(data)
    manifest = {
        "generator": "eval/fixtures/q02/gen_log.py",
        "seed": a.seed,
        "attempt": attempt,
        "app_log_sha256": hashlib.sha256(data).hexdigest(),
        "line_count": len(lines),
        "values": [{"kind": k, "value": vals[k], "line": kinds.index(k) + 1,
                    "random_part": random_part(k, vals[k])} for k in ORDER],
        "ordinary_lines": [i + 1 for i, k in enumerate(kinds) if k is None],
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("wrote %s/app.log (%d lines, sha256 %s) and manifest.json"
          % (out, len(lines), manifest["app_log_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
