#!/usr/bin/env python3
"""q09 fixture self-test (Python 3.8+ stdlib; git needed for part 3).

1. inspect_listing.py on hand-written JSON listings of many shapes
   (none of them copies a real tool's format).
2. egress_parse.py on hand-written strace lines.
3. make_repo.sh + check_repo_data.py with a throw-away stand-in "tool" written
   here (tasks as lines of a text file), including the fresh-clone listing
   with an empty HOME.

Exit 0 when everything behaves as expected.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import egress_parse  # noqa: E402
import inspect_listing as il  # noqa: E402

with open(os.path.join(HERE, "titles.json"), encoding="utf-8") as f:
    CFG = json.load(f)
T1, T2, T3 = CFG["T1"], CFG["T2"], CFG["T3"]
failures = []
tmp = tempfile.mkdtemp(prefix="q09-selftest-")


def check(name, cond):
    print("%-64s %s" % (name, "ok" if cond else "FAILED"))
    if not cond:
        failures.append(name)


def listing(name, obj=None, text=None):
    p = os.path.join(tmp, name + ".json")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text if text is not None else json.dumps(obj, ensure_ascii=False, indent=1))
    return p


def il_verdict(*args):
    """Run inspect_listing.main(args) quietly and return its verdict word."""
    with open(os.devnull, "w") as dn:
        old = sys.stdout
        sys.stdout = dn
        try:
            code = il.main(list(args))
        finally:
            sys.stdout = old
    return {0: "PASS", 1: "FAIL", 3: "REVIEW"}[code]


# ------------------------------------------------------------ 1. listings
rec = lambda i, t, st: {"id": i, "title": t, "status": st}  # noqa: E731
cases = [
    ("array, status field", [rec(1, T1, "closed"), rec(2, T2, "open"), rec(3, T3, "open")], "PASS"),
    ("array, only open tasks", [rec(2, T2, "open"), rec(3, T3, "open")], "PASS"),
    ("object wrapper, boolean done", {"items": [{"n": 1, "name": T1, "done": True},
                                                {"n": 2, "name": T2, "done": False},
                                                {"n": 3, "name": T3, "done": False}]}, "PASS"),
    ("nested status object", [{"key": "A-1", "fields": {"summary": T1, "state": {"name": "Done"}}},
                              {"key": "A-2", "fields": {"summary": T2, "state": {"name": "Todo"}}},
                              {"key": "A-3", "fields": {"summary": T3, "state": {"name": "Todo"}}}], "PASS"),
    ("closed timestamp only on the closed task",
     [{"id": "a", "text": T1, "closedAt": "2026-10-30T10:00:00Z", "createdAt": "2026-10-30T09:00:00Z"},
      {"id": "b", "text": T2, "closedAt": None, "createdAt": "2026-10-30T09:01:00Z"},
      {"id": "c", "text": T3, "closedAt": None, "createdAt": "2026-10-30T09:02:00Z"}], "PASS"),
    ("grouped by status", {"open": [{"t": T2}, {"t": T3}], "closed": [{"t": T1}]}, "PASS"),
    ("keyed by id", {"7": {"title": T1, "status": "done"}, "8": {"title": T2, "status": "todo"},
                     "9": {"title": T3, "status": "todo"}}, "PASS"),
    ("title inside a longer string", [{"line": "[x] " + T1}, {"line": "[ ] " + T2}, {"line": "[ ] " + T3}],
     "PASS"),
    ("list of strings", ["- [x] " + T1, "- [ ] " + T2, "- [ ] " + T3], "PASS"),
    ("list of strings with ids only", ["1 " + T1, "2 " + T2, "3 " + T3], "REVIEW"),
    ("closed task listed, no status", [{"id": 1, "title": T1}, {"id": 2, "title": T2}, {"id": 3, "title": T3}],
     "REVIEW"),
    ("Chinese title altered", [rec(2, T2.replace("訊", "讯"), "open"), rec(3, T3, "open")], "FAIL"),
    ("open task missing", [rec(1, T1, "closed"), rec(2, T2, "open")], "FAIL"),
    ("extra open entry", [rec(2, T2, "open"), rec(3, T3, "open"), rec(4, "Welcome task", "open")], "REVIEW"),
]
for name, obj, want in cases:
    got = il_verdict(listing(name.replace(" ", "_"), obj))
    check("listing: %s -> %s" % (name, want), got == want)

p = listing("jsonl", text="\n".join(json.dumps(r, ensure_ascii=False) for r in
                                    [rec(1, T1, "closed"), rec(2, T2, "open"), rec(3, T3, "open")]) + "\n")
check("listing: JSON Lines -> PASS", il_verdict(p) == "PASS")
p = listing("escaped", text=json.dumps([rec(2, T2, "open"), rec(3, T3, "open")], ensure_ascii=True))
check("listing: \\u-escaped Chinese -> PASS", il_verdict(p) == "PASS")
p = listing("notjson", text="1. " + T2 + "\n2. " + T3 + "\n")
check("listing: plain text -> FAIL", il_verdict(p) == "FAIL")

a = listing("cmpA", [rec(1, T1, "closed"), rec(2, T2, "open"), rec(3, T3, "open")])
b = listing("cmpB", [rec(1, T1, "closed"), rec(2, T2, "open"), rec(3, T3, "open")])
c = listing("cmpC", [rec(1, T1, "open"), rec(2, T2, "open"), rec(3, T3, "open")])
d = listing("cmpD", [rec(2, T2, "open"), rec(3, T3, "open")])
check("compare: identical -> PASS", il_verdict("--compare", a, b) == "PASS")
check("compare: status lost in clone -> FAIL", il_verdict("--compare", a, c) == "FAIL")
check("compare: task missing in clone -> FAIL", il_verdict("--compare", a, d) == "FAIL")

# ------------------------------------------------------------ 2. strace lines
log = os.path.join(tmp, "trace.log")
with open(log, "w") as f:
    f.write('101 connect(3, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT\n'
            '101 connect(4, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            '101 sendto(5, "x", 1, 0, {sa_family=AF_NETLINK, nl_pid=0, nl_groups=00000000}, 12) = 1\n')
check("egress: unix/loopback/netlink only -> no egress", egress_parse.scan(log)[0] == [])
with open(log, "a") as f:
    f.write('102 connect(6, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.53")}, 16) = 0\n'
            '[pid 103] connect(7, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), '
            'inet_pton(AF_INET6, "2001:db8::1", &sin6_addr), sin6_scope_id=0}, 28) = -1 ENETUNREACH\n'
            '104 sendto(8, "q", 1, MSG_NOSIGNAL, {sa_family=AF_INET, sin_port=htons(123), '
            'sin_addr=inet_addr("192.0.2.7")}, 16) = 1\n')
hits = egress_parse.scan(log)[0]
check("egress: DNS to loopback, IPv6 and UDP sendto all counted", len(hits) == 3 and hits[0]["dns"])

# ------------------------------------------------------------ 3. repo + stand-in tool
git = shutil.which("git")
if not git:
    print("git not found: skipping part 3")
else:
    tool = os.path.join(tmp, "standin-tool")
    with open(tool, "w") as f:
        f.write(r'''#!/bin/sh
# throw-away stand-in for a task tool: one line per task in tasks.txt (selftest only)
set -eu
case "$1" in
  add)   printf 'open\t%s\n' "$2" >> tasks.txt ;;
  close) awk -F '\t' -v t="$2" 'BEGIN{OFS="\t"} $2==t{$1="closed"} {print}' tasks.txt > tasks.tmp && mv tasks.tmp tasks.txt ;;
  json)  python3 -c 'import json,sys; print(json.dumps([{"title": l.rstrip("\n").split("\t",1)[1], "status": l.split("\t",1)[0]} for l in open("tasks.txt", encoding="utf-8")], ensure_ascii=False))' ;;
esac
''')
    os.chmod(tool, 0o755)
    repo = os.path.join(tmp, "proj")
    env = dict(os.environ, LANG="C.UTF-8", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    out = subprocess.run(["sh", os.path.join(HERE, "make_repo.sh"), repo], env=env, check=True,
                         stdout=subprocess.PIPE).stdout.decode()
    base = out.split("base: ")[1].strip()
    check("repo: deterministic base commit", base == "56cc386237ac98db667679cfb869d19e4359950a")

    def run(*args, cwd=repo, e=env):
        return subprocess.run(list(args), cwd=cwd, env=e, check=True, stdout=subprocess.PIPE).stdout

    for t in (T1, T2, T3):
        run(tool, "add", t)
    run(tool, "close", T1)
    l1 = os.path.join(tmp, "list1.json")
    with open(l1, "wb") as f:
        f.write(run(tool, "json"))
    check("stand-in: L2-2 listing -> PASS", il_verdict(l1) == "PASS")
    run(git, "add", "-A")
    run(git, "commit", "-q", "-m", "Add tasks")
    empty = tempfile.mkdtemp(prefix="emptyhome-", dir=tmp)
    clone = os.path.join(tmp, "clone")
    cenv = {"PATH": os.environ["PATH"], "HOME": empty, "LANG": "C.UTF-8"}
    run(git, "clone", "-q", "file://" + repo, clone, cwd=tmp, e=cenv)
    check("clone: no untracked or ignored files",
          run(git, "status", "--porcelain", "--ignored", cwd=clone, e=cenv) == b"")
    l2 = os.path.join(tmp, "list2.json")
    with open(l2, "wb") as f:
        f.write(run(tool, "json", cwd=clone, e=cenv))
    check("stand-in: L2-3 compare -> PASS", il_verdict("--compare", l1, l2) == "PASS")
    with open(os.devnull, "w") as dn:
        r_text = subprocess.run([sys.executable, os.path.join(HERE, "check_repo_data.py"), "text", repo, base],
                                stdout=dn).returncode
    check("stand-in: L2-4 text -> PASS", r_text == 0)
    before = run(git, "rev-parse", "HEAD").decode().strip()
    run(tool, "close", T3)
    with open(os.devnull, "w") as dn:
        r_diff = subprocess.run([sys.executable, os.path.join(HERE, "check_repo_data.py"), "diffsize", repo, before],
                                stdout=dn).returncode
    check("stand-in: L2-4 diff (2 lines) -> PASS", r_diff == 0)
    # negative: binary data and a large rewrite
    with open(os.path.join(repo, "state.bin"), "wb") as f:
        f.write(b"\x00\x01\x02" * 10)
    run(git, "add", "-A")
    run(git, "commit", "-q", "-m", "binary")
    with open(os.devnull, "w") as dn:
        r_text2 = subprocess.run([sys.executable, os.path.join(HERE, "check_repo_data.py"), "text", repo, base],
                                 stdout=dn).returncode
    check("negative: binary file -> L2-4 text FAIL", r_text2 == 1)
    before = run(git, "rev-parse", "HEAD").decode().strip()
    with open(os.path.join(repo, "tasks.txt"), "a", encoding="utf-8") as f:
        f.write("".join("open\tfiller %d\n" % k for k in range(6)))
    with open(os.devnull, "w") as dn:
        r_diff2 = subprocess.run([sys.executable, os.path.join(HERE, "check_repo_data.py"), "diffsize", repo, before],
                                 stdout=dn).returncode
    check("negative: 6 changed lines -> L2-4 diff FAIL", r_diff2 == 1)

shutil.rmtree(tmp, ignore_errors=True)
print()
print("ALL OK" if not failures else "FAILED: %d check(s)" % len(failures))
sys.exit(1 if failures else 0)
