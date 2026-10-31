#!/usr/bin/env python3
"""q09: read a task tool's JSON listing and judge it against the fixture titles
(Python 3.8+ stdlib only). Works for any JSON shape; it never assumes field
names of a particular tool.

  python3 inspect_listing.py LIST.json            # L2-2 (T1 closed, T2/T3 open)
  python3 inspect_listing.py --compare A.json B.json   # L2-3 (same tasks, same statuses)

How a listing is read:
  * The file must be one JSON document or JSON Lines (one document per line),
    i.e. what `jq .` accepts.
  * A task "record" is found by its title: the largest object/array element
    that contains that title (as a whole string or inside a longer string) and
    no other fixture title.
  * Status evidence in a record: fields whose name contains a status word
    (status, state, done, closed, completed, resolved, open, checked, archived,
    column, stage, ...) or whose value is a status word (open, closed, done,
    todo, completed, ...); timestamp-like fields count as set / not set; the
    names of the containers above the record (e.g. a "closed" group).

Verdicts (exit status): PASS 0, FAIL 1, REVIEW 3 (the grader decides by
reading the JSON with the rule printed), usage error 2.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

STATUS_TOKENS = {
    "status", "state", "done", "closed", "close", "completed", "complete", "finished",
    "resolved", "open", "opened", "checked", "archived", "column", "stage", "lane",
    "bucket", "phase", "active", "progress", "todo", "pending",
}
STATUS_VALUES = {
    "open", "opened", "closed", "close", "done", "todo", "to-do", "to_do", "to do",
    "doing", "in progress", "in_progress", "in-progress", "inprogress", "wip",
    "complete", "completed", "finished", "resolved", "pending", "active", "inactive",
    "archived", "cancelled", "canceled", "wontfix", "won't fix", "backlog", "ready",
    "blocked", "new", "x", "[x]", "[ ]", "✓", "✔", "☐", "☑", "☒",
}
TIME_TOKENS = {"at", "date", "time", "timestamp", "on", "when", "ts"}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$")


def key_tokens(key):
    key = str(key)
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", key)
    return [p.lower() for p in parts] or [key.lower()]


def load(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")  # strict: a listing that is not UTF-8 fails here
    text = text.lstrip("﻿")
    try:
        return json.loads(text), "json", text
    except ValueError:
        pass
    docs = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                docs.append(json.loads(line))
            except ValueError as e:
                raise ValueError("line %d is not JSON: %s" % (n, e))
    if not docs:
        raise ValueError("empty listing")
    return docs, "jsonl", text


def walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            for item in walk(v, path + (k,)):
                yield item
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            for item in walk(v, path + (i,)):
                yield item
    else:
        yield path, obj


def get(obj, path):
    for p in path:
        obj = obj[p]
    return obj


def titles_in(obj, titles):
    found = set()
    for _, v in walk(obj):
        if isinstance(v, str):
            for name, t in titles.items():
                if t in v:
                    found.add(name)
    return found


def locate(root, titles):
    """name -> {'path': record path, 'record': obj} for each title found."""
    occ = {}
    for path, v in walk(root):
        if isinstance(v, str):
            for name, t in titles.items():
                if t in v and name not in occ:
                    occ[name] = path
    out = {}
    for name, path in occ.items():
        rec_path = path
        for d in range(len(path) + 1):
            node = get(root, path[:d])
            if titles_in(node, titles) == {name}:
                rec_path = path[:d]
                break
        out[name] = {"path": rec_path, "record": get(root, rec_path), "title_path": path}
    return out


def normalise(key, value):
    toks = set(key_tokens(key))
    if isinstance(value, str) and ISO_RE.match(value.strip()):
        return "<set>"
    if toks & TIME_TOKENS and not isinstance(value, bool):
        return "<set>" if value not in (None, "", 0) else "<unset>"
    if isinstance(value, str):
        return value.strip().lower()
    return value


def status_signature(rec, rec_path, title):
    sig = {}
    if isinstance(rec, (dict, list)):
        for path, v in walk(rec):
            if isinstance(v, str) and title in v:
                # e.g. "[x] <title>": what surrounds the title can carry the status
                rest = v.replace(title, "\u2026").strip()
                if rest != "\u2026":
                    sig["around-title:" + "/".join(str(p) for p in path)] = rest
                continue
            last = path[-1] if path else ""
            names = [p for p in path if isinstance(p, str)]
            is_status_key = any(set(key_tokens(n)) & STATUS_TOKENS for n in names[-2:])
            is_status_val = isinstance(v, str) and v.strip().lower() in STATUS_VALUES
            if is_status_key or is_status_val:
                sig["field:" + "/".join(str(p) for p in path)] = normalise(last, v)
    elif isinstance(rec, str):
        rest = rec.replace(title, "…").strip()
        sig["text"] = rest
    groups = [p for p in rec_path if isinstance(p, str)]
    for g in groups:
        if set(key_tokens(g)) & STATUS_TOKENS or g.strip().lower() in STATUS_VALUES:
            sig["group:" + g] = True
    sig["__group_path__"] = "/".join(groups)
    return sig


def sibling_count(root, recs):
    """Number of entries in the container that holds the records, if they share one."""
    parents = {tuple(r["path"][:-1]) for r in recs.values() if r["path"]}
    if len(parents) != 1:
        return None
    parent = get(root, list(parents)[0])
    return len(parent) if isinstance(parent, (list, dict)) else None


def judge_l2_2(path, titles, closed, open_):
    root, kind, text = load(path)
    out = {"file": path, "format": kind, "verdict": None, "reasons": [], "notes": []}
    if "�" in text:
        out["reasons"].append("listing contains U+FFFD (a character was lost)")
    recs = locate(root, titles)
    out["found"] = sorted(recs)
    out["records"] = {k: {"path": "/".join(str(p) for p in v["path"]),
                          "status": status_signature(v["record"], v["path"], titles[k])}
                      for k, v in recs.items()}
    # Chinese title round trip
    zh = [k for k, t in titles.items() if any(ord(c) > 0x2E7F for c in t)]
    for k in zh:
        if k not in recs:
            out["reasons"].append("%s (Chinese title) not found intact in the listing" % k)
    missing_open = [k for k in open_ if k not in recs]
    if missing_open:
        out["reasons"].append("open task(s) missing: %s" % ", ".join(missing_open))
    n_sib = sibling_count(root, recs)
    out["entries_in_container"] = n_sib
    if out["reasons"]:
        out["verdict"] = "FAIL"
        return out

    if all(k not in recs for k in closed):
        out["mode"] = "only open tasks listed"
        if n_sib is not None and n_sib > len(recs):
            out["verdict"] = "REVIEW"
            out["notes"].append("%d other entries next to the tasks: pass only if none of them is an open task"
                                % (n_sib - len(recs)))
        else:
            out["verdict"] = "PASS"
        return out

    # closed task listed: need a status difference
    sigs = {k: out["records"][k]["status"] for k in recs}
    keys = set()
    for s in sigs.values():
        keys |= set(s)
    keys.discard("__group_path__")
    disc = []
    for f in sorted(keys):
        vals_closed = {json.dumps(sigs[k].get(f), ensure_ascii=False) for k in closed}
        vals_open = {json.dumps(sigs[k].get(f), ensure_ascii=False) for k in open_}
        if len(vals_open) == 1 and not (vals_closed & vals_open):
            disc.append(f)
    out["mode"] = "all tasks listed with status"
    out["discriminating_fields"] = ["%s (%s: %s / %s: %s)" % (
        f, "/".join(closed), json.dumps(sigs[closed[0]].get(f), ensure_ascii=False),
        "/".join(open_), json.dumps(sigs[open_[0]].get(f), ensure_ascii=False)) for f in disc]
    if disc:
        if n_sib is not None and n_sib > len(recs):
            out["verdict"] = "REVIEW"
            out["notes"].append("%d other entries next to the tasks: pass only if none of them is an open task"
                                % (n_sib - len(recs)))
        else:
            out["verdict"] = "PASS"
    else:
        # No recognisable status field. Do not guess: list every scalar that sets the
        # closed task apart and let the grader read the JSON.
        def flat(k):
            r = recs[k]["record"]
            if not isinstance(r, (dict, list)):
                return {"text": str(r).replace(titles[k], "\u2026")}
            return {"/".join(str(p) for p in pth): json.dumps(v, ensure_ascii=False)
                    for pth, v in walk(r) if not (isinstance(v, str) and titles[k] in v)}
        fl = {k: flat(k) for k in recs}
        cand = sorted(f for f in set().union(*fl.values())
                      if len({fl[k].get(f) for k in open_}) == 1
                      and all(fl[c].get(f) != fl[open_[0]].get(f) for c in closed))
        out["candidate_fields"] = cand
        out["verdict"] = "REVIEW"
        out["notes"].append(
            "no recognised status field marks %s differently from %s; pass only if a field or "
            "grouping that the tool documents as status does (candidates: %s)"
            % ("/".join(closed), "/".join(open_), ", ".join(cand) or "none"))
    return out


def compare(a_path, b_path, titles):
    res = {}
    for label, p in (("A", a_path), ("B", b_path)):
        root, _, _ = load(p)
        recs = locate(root, titles)
        # The group path is left out: container names such as ids or file paths may
        # legitimately differ; status-like group names are already "group:" fields.
        res[label] = {k: {f: v for f, v in status_signature(r["record"], r["path"], titles[k]).items()
                          if f != "__group_path__"}
                      for k, r in recs.items()}
    diffs = []
    if set(res["A"]) != set(res["B"]):
        diffs.append("different tasks: %s vs %s" % (sorted(res["A"]), sorted(res["B"])))
    for k in sorted(set(res["A"]) & set(res["B"])):
        if res["A"][k] != res["B"][k]:
            diffs.append("%s status differs: %s vs %s" % (k, json.dumps(res["A"][k], ensure_ascii=False),
                                                       json.dumps(res["B"][k], ensure_ascii=False)))
    return {"A": a_path, "B": b_path, "tasks": sorted(res["A"]), "differences": diffs,
            "verdict": "PASS" if not diffs and res["A"] else "FAIL"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="q09 JSON listing checks")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--compare", action="store_true", help="L2-3: compare two listings")
    ap.add_argument("--titles", default=os.path.join(HERE, "titles.json"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(a.titles, encoding="utf-8") as f:
        cfg = json.load(f)
    titles = {k: cfg[k] for k in cfg["create_order"]}
    try:
        if a.compare:
            if len(a.files) != 2:
                ap.error("--compare needs two files")
            rep = compare(a.files[0], a.files[1], titles)
        else:
            rep = judge_l2_2(a.files[0], titles, [cfg["close_in_L2-2"]], cfg["open_after_L2-2"])
    except (ValueError, UnicodeDecodeError) as e:
        rep = {"verdict": "FAIL", "reasons": ["not a JSON listing: %s" % e]}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for k in ("mode", "found", "entries_in_container", "discriminating_fields", "candidate_fields", "tasks"):
            if k in rep:
                print("%s: %s" % (k, rep[k]))
        for r in rep.get("reasons", []) + rep.get("differences", []):
            print("  - " + r)
        for r in rep.get("notes", []):
            print("  note: " + r)
        print("verdict: %s" % rep["verdict"])
    return {"PASS": 0, "FAIL": 1, "REVIEW": 3}[rep["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
