#!/usr/bin/env python3
"""q11: score the model's replies to the five frozen prompts (Python 3.8+ stdlib).

A run directory holds the replies exactly as printed in the terminal, one file
per prompt: P1.txt .. P5.txt (UTF-8). Optionally judge.json holds the blind
grader's verdicts for P1, P2, P3, P5: {"P1": true, ...} (see judge_rubric.md).

  python3 score_replies.py --dict-dir OPENCC_DIR RUN_DIR [RUN_DIR RUN_DIR]
  python3 score_replies.py --write-judge-requests OUT.jsonl RUN_DIR ...

With one run directory each check is judged on that run. With three (no way to
fix seed or temperature, README section 5), each check passes when at least 2
of the 3 runs pass it.

Checks (q11 [L2] items 3-5 in questions.yaml; the item numbers below are
L2-3 .. L2-5 of this folder's README):
  L2-3 coherence: P1, P2, P3, P5 each have >= 50 CJK (Han) characters, no
       10-character substring containing a Han character occurs more than 3
       times (non-overlapping, whitespace removed), and the blind grader says
       the reply answers the prompt.
  L2-4 script: the shared OpenCC scorer over all five replies: ratio >= 0.95
       with >= 30 script-differing characters.
  L2-5 vocabulary: P4 gives >= 6 of the 8 Taiwan terms on the matching lines,
       none of the listed mainland terms anywhere in P4, and no 文件 for
       'file'; P5 has >= 2 Taiwan terms and none of its listed terms.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROMPTS = ["P1", "P2", "P3", "P4", "P5"]
COHERENCE_PROMPTS = ["P1", "P2", "P3", "P5"]
MIN_HAN = 50
REPEAT_LEN = 10
MAX_REPEATS = 3

P4_WORDS = ["software", "video", "network", "program", "information", "default", "file", "memory"]
TAIWAN_TERMS = ["軟體", "影片", "網路", "程式", "資訊", "預設", "檔案", "記憶體"]
P4_FORBIDDEN = ["软件", "軟件", "视频", "視頻", "网络", "網絡", "程序", "信息", "默认", "默認", "内存", "內存"]
P4_FILE_FORBIDDEN = "文件"
P5_FORBIDDEN = ["软件", "軟件", "视频", "視頻", "网络", "網絡", "默认", "默認", "内存", "內存"]
P4_MIN, P5_MIN = 6, 2


def is_han(c):
    o = ord(c)
    return (0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF
            or 0x20000 <= o <= 0x2A6DF or 0x2A700 <= o <= 0x2EBEF or 0x2F800 <= o <= 0x2FA1F
            or 0x30000 <= o <= 0x323AF)


def read_run(d):
    rep = {}
    for p in PROMPTS:
        path = os.path.join(d, p + ".txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rep[p] = f.read()
        else:
            rep[p] = None
    j = os.path.join(d, "judge.json")
    judge = None
    if os.path.exists(j):
        with open(j, encoding="utf-8") as f:
            judge = json.load(f)
    return rep, judge


def max_repeat(text):
    t = re.sub(r"\s+", "", text)
    best, best_s = 0, ""
    seen = set()
    for i in range(len(t) - REPEAT_LEN + 1):
        s = t[i:i + REPEAT_LEN]
        if s in seen or not any(is_han(c) for c in s):
            continue
        seen.add(s)
        n = t.count(s)  # non-overlapping occurrences
        if n > best:
            best, best_s = n, s
    return best, best_s


def coherence(replies, judge):
    out = {}
    ok_all = True
    for p in COHERENCE_PROMPTS:
        r = replies.get(p)
        if r is None:
            out[p] = {"pass": False, "reason": "no reply"}
            ok_all = False
            continue
        han = sum(1 for c in r if is_han(c))
        rep_n, rep_s = max_repeat(r)
        j = None if judge is None else judge.get(p)
        reasons = []
        if han < MIN_HAN:
            reasons.append("%d Han characters < %d" % (han, MIN_HAN))
        if rep_n > MAX_REPEATS:
            reasons.append("'%s' occurs %d times" % (rep_s, rep_n))
        if j is None:
            reasons.append("blind grader verdict missing")
        elif not j:
            reasons.append("blind grader: does not answer the prompt")
        ok = not reasons
        ok_all = ok_all and ok
        out[p] = {"han": han, "max_repeat": rep_n, "max_repeat_substring": rep_s,
                  "judge": j, "pass": ok, "reasons": reasons}
    pending = judge is None or any((judge or {}).get(p) is None for p in COHERENCE_PROMPTS)
    return {"pass": ok_all, "pending_judge": pending, "per_prompt": out}


def p4_lines(text):
    """Map each English word to the reply line that translates it."""
    lines = [l for l in text.splitlines() if l.strip()]
    mapping, method = {}, "english word on the line"
    for w in P4_WORDS:
        rx = re.compile(r"(?<![A-Za-z])%s(?![A-Za-z])" % w, re.I)
        hit = [l for l in lines if rx.search(l)]
        if hit:
            mapping[w] = hit[0]
    if len(mapping) < len(P4_WORDS):
        han_lines = [l for l in lines if any(is_han(c) for c in l)]
        if len(han_lines) == len(P4_WORDS) and not mapping:
            mapping = dict(zip(P4_WORDS, han_lines))
            method = "line order (no English words in the reply)"
        elif mapping:
            method = "english word on the line (%d of 8 found)" % len(mapping)
        else:
            method = "unmapped (grader maps lines by hand)"
    return mapping, method


def vocabulary(replies):
    p4, p5 = replies.get("P4"), replies.get("P5")
    res = {"P4": {}, "P5": {}}
    ok = True
    if p4 is None:
        res["P4"] = {"pass": False, "reasons": ["no reply"]}
        ok = False
    else:
        mapping, method = p4_lines(p4)
        hits = [w for w, term in zip(P4_WORDS, TAIWAN_TERMS) if w in mapping and term in mapping[w]]
        forb = [t for t in P4_FORBIDDEN if t in p4]
        file_line = mapping.get("file")
        file_bad = P4_FILE_FORBIDDEN in (file_line if file_line is not None else p4)
        reasons = []
        if len(hits) < P4_MIN:
            reasons.append("%d of 8 Taiwan terms on the matching lines (< %d)" % (len(hits), P4_MIN))
        if forb:
            reasons.append("forbidden terms: %s" % ", ".join(forb))
        if file_bad:
            reasons.append("文件 used for 'file'%s" % ("" if file_line is not None else " (file line not identified; searched whole reply)"))
        res["P4"] = {"mapping_method": method, "terms_found": hits, "forbidden_found": forb,
                     "file_line": file_line, "pass": not reasons, "reasons": reasons}
        ok = ok and not reasons
    if p5 is None:
        res["P5"] = {"pass": False, "reasons": ["no reply"]}
        ok = False
    else:
        terms = [t for t in TAIWAN_TERMS if t in p5]
        forb = [t for t in P5_FORBIDDEN if t in p5]
        reasons = []
        if len(terms) < P5_MIN:
            reasons.append("%d Taiwan terms (< %d)" % (len(terms), P5_MIN))
        if forb:
            reasons.append("forbidden terms: %s" % ", ".join(forb))
        res["P5"] = {"terms_found": terms, "forbidden_found": forb, "pass": not reasons, "reasons": reasons}
        ok = ok and not reasons
    res["pass"] = ok
    return res


def script(replies, dict_dir):
    if not dict_dir:
        return {"pass": None, "reason": "not run: --dict-dir (pinned OpenCC dictionaries) not given"}
    from opencc_scorer import Scorer
    text = "\n".join(replies[p] for p in PROMPTS if replies.get(p) is not None)
    return Scorer(dict_dir).score(text)


def judge_requests(run_dirs, out_path):
    with open(os.path.join(HERE, "judge_rubric.md"), encoding="utf-8") as f:
        rubric = f.read().split("<!-- RUBRIC START -->", 1)[1].split("<!-- RUBRIC END -->", 1)[0].strip()
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for d in run_dirs:
            replies, _ = read_run(d)
            for p in COHERENCE_PROMPTS:
                with open(os.path.join(HERE, "prompts", p + ".txt"), encoding="utf-8") as f:
                    prompt = f.read().strip()
                if replies.get(p) is None:
                    continue
                req = {"id": "%s:%s" % (os.path.basename(os.path.normpath(d)), p),
                       "model": "PINNED_JUDGE_MODEL", "temperature": 0, "max_tokens": 300,
                       "system": rubric,
                       "messages": [{"role": "user", "content":
                                     "<prompt>\n%s\n</prompt>\n\n<reply>\n%s\n</reply>" % (prompt, replies[p].strip())}]}
                out.write(json.dumps(req, ensure_ascii=False) + "\n")
                n += 1
    print("wrote %d judge requests to %s (fill in the pinned model id before sending)" % (n, out_path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="q11 reply checks")
    ap.add_argument("runs", nargs="+", help="1 or 3 run directories")
    ap.add_argument("--dict-dir", help="pinned OpenCC dictionary folder (STCharacters.txt, TSCharacters.txt)")
    ap.add_argument("--write-judge-requests", metavar="OUT.jsonl")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.write_judge_requests:
        return judge_requests(a.runs, a.write_judge_requests)
    if len(a.runs) not in (1, 3):
        ap.error("give 1 run, or 3 runs when seed and temperature cannot be fixed")
    per_run = []
    for d in a.runs:
        replies, judge = read_run(d)
        per_run.append({"run": d,
                        "L2-3 coherence": coherence(replies, judge),
                        "L2-4 script": script(replies, a.dict_dir),
                        "L2-5 vocabulary": vocabulary(replies)})
    need = 1 if len(per_run) == 1 else 2
    summary = {}
    for k in ("L2-3 coherence", "L2-4 script", "L2-5 vocabulary"):
        vals = [r[k]["pass"] for r in per_run]
        if any(v is None for v in vals):
            summary[k] = "NOT RUN"
        else:
            summary[k] = "PASS" if sum(1 for v in vals if v) >= need else "FAIL"
        if k == "L2-3 coherence" and any(r[k]["pending_judge"] for r in per_run):
            summary[k] += " (blind grader verdicts missing)"
    rep = {"runs": per_run, "summary": summary, "rule": "%d of %d runs" % (need, len(per_run))}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for r in per_run:
            print("== %s" % r["run"])
            c = r["L2-3 coherence"]
            for p, v in c["per_prompt"].items():
                print("  coherence %s: %s%s" % (p, "PASS" if v["pass"] else "FAIL",
                                               "" if v["pass"] else " - " + "; ".join(v.get("reasons", [v.get("reason", "")]))))
            s = r["L2-4 script"]
            if s["pass"] is None:
                print("  script: NOT RUN (%s)" % s["reason"])
            else:
                print("  script: %s (ratio %.4f, differing %d, simplified-only: %s)"
                      % ("PASS" if s["pass"] else "FAIL", s["ratio"], s["differing"], s["simplified_chars"] or "-"))
            v = r["L2-5 vocabulary"]
            for p in ("P4", "P5"):
                print("  vocabulary %s: %s%s" % (p, "PASS" if v[p]["pass"] else "FAIL",
                                                "" if v[p]["pass"] else " - " + "; ".join(v[p]["reasons"])))
        print("== result (%s)" % rep["rule"])
        for k, v in summary.items():
            print("  %s: %s" % (k, v))
    return 0 if all(v == "PASS" for v in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
