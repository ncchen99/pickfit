#!/usr/bin/env python3
"""q11 fixture self-test (Python 3.8+ stdlib).

Uses only the synthetic replies in samples/ and the hand-written TEST-ONLY
character tables in ../_shared/selftest_dict/ (not OpenCC data), so it runs without the
pinned OpenCC dictionaries. With --mac on macOS it also runs a 10-second
footprint_watch.py check on a child process.

Exit 0 when everything behaves as expected.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "mac"))
sys.path.insert(0, os.path.join(HERE, "..", "_shared"))
import zh_script  # noqa: E402
import scan_transcript  # noqa: E402
import score_replies as sr  # noqa: E402

failures = []
TD = os.path.join(HERE, "..", "_shared", "selftest_dict")
S = os.path.join(HERE, "samples")


def check(name, cond):
    print("%-62s %s" % (name, "ok" if cond else "FAILED"))
    if not cond:
        failures.append(name)


def quiet(fn, *a):
    with open(os.devnull, "w") as dn:
        old = sys.stdout
        sys.stdout = dn
        try:
            return fn(*a)
        finally:
            sys.stdout = old


# ---------------------------------------------------------------- prompts frozen?
qy = os.path.join(HERE, "..", "..", "questions.yaml")
if os.path.exists(qy):
    with open(qy, encoding="utf-8") as f:
        y = f.read()
    block = y[y.index("- id: q11"):y.index("- id: q12")]
    folded = re.sub(r"\n\s+", " ", block)
    for p in sr.PROMPTS:
        with open(os.path.join(HERE, "prompts", p + ".txt"), encoding="utf-8") as f:
            t = f.read().strip()
        check("prompt %s matches questions.yaml (%d chars)" % (p, len(t)), ("%s: %s" % (p, t)) in folded)
else:
    print("questions.yaml not found: skipping prompt check")

# ---------------------------------------------------------------- OpenCC scorer logic
sc = zh_script.OpenCCTables(TD)
check("scorer: neutral characters stay neutral (台后里干只内)",
      all(sc.classify(c) is None for c in "台后里干只内"))
check("scorer: Traditional-only / Simplified-only", sc.classify("軟") == "traditional" and sc.classify("软") == "simplified")
r = sc.ratio("軟體" * 10)
check("scorer: < 30 differing characters fails even at ratio 1.0", r["differing"] == 10 and not r["pass"])
r = sc.ratio("網" * 95 + "网" * 5)
check("scorer: ratio exactly 0.95 passes", r["ratio"] == 0.95 and r["pass"])
r = sc.ratio("網" * 94 + "网" * 6)
check("scorer: ratio 0.94 fails", not r["pass"])

# ---------------------------------------------------------------- reply checks on samples
def run(*dirs):
    rep = []
    for d in dirs:
        replies, judge = sr.read_run(os.path.join(S, d))
        rep.append({"coh": sr.coherence(replies, judge), "scr": sr.script(replies, TD), "voc": sr.vocabulary(replies)})
    return rep


g = run("good")[0]
check("good: coherence PASS", g["coh"]["pass"])
check("good: script PASS", g["scr"]["pass"])
check("good: vocabulary PASS (P4 8/8, P5 >= 2)", g["voc"]["pass"] and len(g["voc"]["P4"]["terms_found"]) == 8)
s_ = run("simplified")[0]
check("simplified: script FAIL", s_["scr"]["pass"] is False)
check("simplified: vocabulary FAIL", not s_["voc"]["pass"] and "程序" in s_["voc"]["P4"]["forbidden_found"])
check("simplified: 文件 for 'file' caught", any("文件" in x for x in s_["voc"]["P4"]["reasons"]))
m = run("mainland_vocab")[0]
check("mainland vocabulary in Traditional script: script PASS", m["scr"]["pass"])
check("mainland vocabulary in Traditional script: vocabulary FAIL", not m["voc"]["P4"]["pass"] and not m["voc"]["P5"]["pass"])
lo = run("loop")[0]
check("loop: P1 repetition caught", not lo["coh"]["per_prompt"]["P1"]["pass"]
      and lo["coh"]["per_prompt"]["P1"]["max_repeat"] > 3)
of = run("offtopic")[0]
check("offtopic: judge false makes P2 fail", not of["coh"]["per_prompt"]["P2"]["pass"])

tmp = tempfile.mkdtemp(prefix="q11-selftest-")
try:
    # P4 lines without English words -> mapped by order
    d = os.path.join(tmp, "order")
    shutil.copytree(os.path.join(S, "good"), d)
    with open(os.path.join(d, "P4.txt"), "w", encoding="utf-8") as f:
        f.write("1. 軟體\n2. 影片\n3. 網路\n4. 程式\n5. 資訊\n6. 預設\n7. 檔案\n8. 記憶體\n")
    rr, _ = sr.read_run(d)
    v = sr.vocabulary(rr)
    check("P4 without English words: mapped by line order", v["P4"]["pass"] and "order" in v["P4"]["mapping_method"])
    with open(os.path.join(d, "P4.txt"), "w", encoding="utf-8") as f:
        f.write("Software: 軟體\nVideo: 影片\nNetwork: 網路\nProgram: 程式\nInformation: 資訊\n"
                "Default: 默認\nFile: 檔案\nMemory: 內存\n")
    rr, _ = sr.read_run(d)
    v = sr.vocabulary(rr)
    check("P4 with 6/8 terms but forbidden 默認/內存: FAIL", not v["P4"]["pass"] and len(v["P4"]["terms_found"]) == 6)
    # missing judge verdicts -> not a pass
    d2 = os.path.join(tmp, "nojudge")
    shutil.copytree(os.path.join(S, "good"), d2)
    os.remove(os.path.join(d2, "judge.json"))
    rr, jj = sr.read_run(d2)
    c = sr.coherence(rr, jj)
    check("missing judge.json: coherence not passed, marked pending", not c["pass"] and c["pending_judge"])
    # 2-of-3 aggregation
    code = quiet(sr.main, [os.path.join(S, "good"), os.path.join(S, "good"), os.path.join(S, "simplified"),
                           "--dict-dir", TD])
    check("3 runs good/good/simplified: 2 of 3 -> PASS", code == 0)
    code = quiet(sr.main, [os.path.join(S, "good"), os.path.join(S, "simplified"), os.path.join(S, "simplified"),
                           "--dict-dir", TD])
    check("3 runs good/simplified/simplified: FAIL", code == 1)
    code = quiet(sr.main, [os.path.join(S, "good")])
    check("no --dict-dir: script NOT RUN, overall not PASS", code == 1)
    # judge requests
    out = os.path.join(tmp, "req.jsonl")
    quiet(sr.main, [os.path.join(S, "good"), "--write-judge-requests", out])
    with open(out, encoding="utf-8") as f:
        reqs = [json.loads(l) for l in f]
    check("judge requests: 4 per run, rubric as system prompt, no group info",
          len(reqs) == 4 and all("answers_prompt" in q["system"] for q in reqs)
          and all("pickfit" not in json.dumps(q, ensure_ascii=False).lower() for q in reqs))
    # transcript scanner
    tr = os.path.join(tmp, "t.txt")
    with open(tr, "wb") as f:
        f.write("Downloading 10%\r\x1b[32mDownloading 100%\x1b[0m\r\n載入完成\r\n請先登入帳號\r\nEnter your token:\r\n".encode())
    hits = []
    old = sys.stdout
    with open(os.devnull, "w") as dn:
        sys.stdout = dn
        try:
            rc = scan_transcript.main([tr])
        finally:
            sys.stdout = old
    check("transcript scanner flags login/token lines", rc == 1)
    if "--mac" in sys.argv and sys.platform == "darwin":
        import time
        fw = os.path.join(tmp, "fw")
        watcher = subprocess.Popen([sys.executable, os.path.join(HERE, "mac", "footprint_watch.py"), "--uid", "99999",
                                    "--shell-pid", str(os.getpid()), "--out", fw, "--duration", "7",
                                    "--interval", "0.25"], stdout=subprocess.DEVNULL)
        time.sleep(1.5)  # the watcher's baseline must not include the child
        child = subprocess.Popen([sys.executable, "-c",
                                  "import time; b=bytearray(256*1024*1024); b[::4096]=b'x'*len(b[::4096]); time.sleep(3)"])
        child.wait()
        watcher.wait()
        with open(os.path.join(fw, "footprint.json")) as f:
            res = json.load(f)
        gib = res["peak_concurrent_sum_bytes"] / float(1 << 30)
        check("footprint_watch sees a 256 MiB child (got %.3f GiB)" % gib, 0.24 <= gib <= 0.40)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL OK" if not failures else "FAILED: %d check(s)" % len(failures))
sys.exit(1 if failures else 0)
