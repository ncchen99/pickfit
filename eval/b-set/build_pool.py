#!/usr/bin/env python3
"""Fetch and classify the B question set candidate pool (eval/README.md 9.2 E).

Everything that decides what is fetched or kept is read from queries.json, which
was committed before this script was run.

  python3 eval/b-set/build_pool.py fetch    --cache DIR
  python3 eval/b-set/build_pool.py classify --cache DIR
  python3 eval/b-set/build_pool.py order    --cache DIR --category mcp --start 0 --count 10

The raw fetched posts (Stack Exchange text is CC BY-SA 4.0) stay in DIR and are not committed;
pool.json keeps links, dates, titles and a SHA-256 of each body so the cache can be checked.
Python 3.9, standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERIES = json.loads((HERE / "queries.json").read_text(encoding="utf-8"))
UTC = dt.timezone.utc
FROM = dt.datetime.strptime(QUERIES["date_range"]["from"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
TO = dt.datetime.strptime(QUERIES["date_range"]["to"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
CATEGORIES = QUERIES["category_rules"]["precedence"]
UA = "pickfit-eval-bset/1.0 (read-only research; ncchen99@gmail.com)"


def now() -> str:
    return dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, tries: int = 4) -> dict:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def quarters() -> list[tuple[dt.datetime, dt.datetime]]:
    out = []
    cur = FROM
    while cur <= TO:
        month = ((cur.month - 1) // 3) * 3 + 3  # last month of the quarter
        nxt = dt.datetime(cur.year + (month // 12), (month % 12) + 1, 1, tzinfo=UTC)
        end = min(nxt - dt.timedelta(seconds=1), TO)
        out.append((cur, end))
        cur = nxt
    return out


# ---------------------------------------------------------------- Stack Exchange

def fetch_se(cache: Path, log: dict) -> None:
    out = cache / "se.jsonl"
    items = []
    page = 1
    requests = 0
    quota = None
    while True:
        params = {"site": "softwarerecs", "sort": "creation", "order": "asc", "pagesize": 100, "page": page,
                  "filter": "withbody", "fromdate": int(FROM.timestamp()), "todate": int(TO.timestamp())}
        url = "https://api.stackexchange.com/2.3/questions?" + urllib.parse.urlencode(params)
        data = http_get(url)
        requests += 1
        items.extend(data.get("items", []))
        quota = data.get("quota_remaining")
        if data.get("backoff"):
            time.sleep(int(data["backoff"]) + 1)
        if not data.get("has_more"):
            break
        page += 1
        time.sleep(0.5)
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    log["stackexchange"] = {"requests": requests, "questions_fetched": len(items), "quota_remaining_after": quota,
                            "finished": now()}
    print("SE", len(items), "questions in", requests, "requests")


# ---------------------------------------------------------------- Hacker News

def hn_window(term: str, s: int, e: int, windows_log: list) -> list[dict]:
    params = {"query": term, "tags": "ask_hn", "restrictSearchableAttributes": "title,story_text",
              "numericFilters": f"created_at_i>={s},created_at_i<={e}", "hitsPerPage": 1000, "page": 0}
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(params)
    data = http_get(url)
    nb = data.get("nbHits", 0)
    windows_log.append({"term": term, "from": s, "to": e, "nbHits": nb})
    if nb > 1000 and e > s:
        mid = (s + e) // 2
        return hn_window(term, s, mid, windows_log) + hn_window(term, mid + 1, e, windows_log)
    hits = list(data.get("hits", []))
    page = 1
    while page < data.get("nbPages", 0):
        params["page"] = page
        more = http_get("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(params))
        hits.extend(more.get("hits", []))
        page += 1
    time.sleep(0.2)
    return hits


def fetch_hn(cache: Path, log: dict) -> None:
    found: dict[str, dict] = {}
    windows_log: list = []
    cfg = QUERIES["sources"]["hackernews"]["queries_per_category"]
    for cat, terms in cfg.items():
        for term in terms:
            for ws, we in quarters():
                for hit in hn_window(term, int(ws.timestamp()), int(we.timestamp()), windows_log):
                    rec = found.setdefault(hit["objectID"], {"hit": hit, "matched_queries": []})
                    q = f"{cat}:{term}"
                    if q not in rec["matched_queries"]:
                        rec["matched_queries"].append(q)
    with (cache / "hn.jsonl").open("w", encoding="utf-8") as fh:
        for rec in found.values():
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log["hackernews"] = {"requests_windows": len(windows_log), "unique_posts_fetched": len(found),
                         "windows_over_1000_split": sum(1 for w in windows_log if w["nbHits"] > 1000),
                         "windows": windows_log, "finished": now()}
    print("HN", len(found), "unique posts,", len(windows_log), "windows")


# ---------------------------------------------------------------- GitHub Discussions

GQL = """
query($q:String!,$after:String){
  search(query:$q,type:DISCUSSION,first:50,after:$after){
    discussionCount
    pageInfo{hasNextPage endCursor}
    nodes{... on Discussion{
      url title body createdAt
      category{name}
      answer{id}
      repository{nameWithOwner stargazerCount}
      author{login}
    }}
  }
}
"""


def gh_graphql(q: str, after: str | None) -> dict:
    last = ""
    for attempt in range(5):
        cmd = ["gh", "api", "graphql", "-f", f"query={GQL}", "-f", f"q={q}"]
        if after:
            cmd += ["-f", f"after={after}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return json.loads(res.stdout)
        last = (res.stderr or res.stdout)[:300]
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"gh graphql failed for {q!r}: {last}")


def gh_window(kw: str, intent: str, s: dt.date, e: dt.date, wlog: list) -> list[dict]:
    q = f"{kw} {intent} in:title,body created:{s.isoformat()}..{e.isoformat()} sort:created-asc"
    data = gh_graphql(q, None)
    count = data["data"]["search"]["discussionCount"]
    wlog.append({"keyword": kw, "intent": intent, "from": s.isoformat(), "to": e.isoformat(), "discussionCount": count})
    if count > 1000 and e > s:
        mid = s + (e - s) // 2
        return gh_window(kw, intent, s, mid, wlog) + gh_window(kw, intent, mid + dt.timedelta(days=1), e, wlog)
    nodes = [n for n in data["data"]["search"]["nodes"] if n]
    info = data["data"]["search"]["pageInfo"]
    while info["hasNextPage"]:
        time.sleep(1.5)
        data = gh_graphql(q, info["endCursor"])
        nodes.extend(n for n in data["data"]["search"]["nodes"] if n)
        info = data["data"]["search"]["pageInfo"]
    time.sleep(1.5)
    return nodes


def fetch_gh(cache: Path, log: dict) -> None:
    cfg = QUERIES["sources"]["github_discussions"]
    found: dict[str, dict] = {}
    wlog: list = []
    for cat, kws in cfg["keywords_per_category"].items():
        for kw in kws:
            for intent in cfg["intent_words"]:
                for ws, we in quarters():
                    for node in gh_window(kw, intent, ws.date(), we.date(), wlog):
                        rec = found.setdefault(node["url"], {"node": node, "matched_queries": []})
                        q = f"{cat}:{kw}+{intent}"
                        if q not in rec["matched_queries"]:
                            rec["matched_queries"].append(q)
            print("GH done", cat, kw, "unique so far", len(found), flush=True)
    with (cache / "gh.jsonl").open("w", encoding="utf-8") as fh:
        for rec in found.values():
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log["github_discussions"] = {"search_windows": len(wlog), "unique_discussions_fetched": len(found),
                                 "windows_over_1000_split": sum(1 for w in wlog if w["discussionCount"] > 1000),
                                 "windows": wlog, "finished": now()}
    print("GH", len(found), "unique discussions")


def cmd_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    log_path = HERE / "fetch-log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    log["started_" + args.only] = now()
    log["queries_json_sha256"] = hashlib.sha256((HERE / "queries.json").read_bytes()).hexdigest()
    todo = ["stackexchange", "hackernews", "github_discussions"] if args.only == "all" else [args.only]
    for src in todo:
        {"stackexchange": fetch_se, "hackernews": fetch_hn, "github_discussions": fetch_gh}[src](cache, log)
        log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- classify

class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("p", "br", "li", "pre", "h1", "h2", "h3", "blockquote"):
            self.parts.append("\n")


def strip_html(s: str) -> str:
    p = _Strip()
    p.feed(s or "")
    return html.unescape("".join(p.parts)).strip()


def any_match(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def categorize(text: str) -> tuple[str | None, list[str]]:
    rules = QUERIES["category_rules"]
    hit = any_match(rules["mcp"]["any_of"], text)
    if hit:
        return "mcp", ["mcp"]
    for group in rules["local_ai"]["any_of_groups"]:
        if "any_of" in group:
            if any_match(group["any_of"], text):
                return "local_ai", [group["name"]]
        else:
            if all(any_match(part["any_of"], text) for part in group["all_of"]):
                return "local_ai", [group["name"]]
    names = []
    ok = True
    for part in rules["dev_cli"]["all_of"]:
        if any_match(part["any_of"], text):
            names.append(part["name"])
        else:
            ok = False
    if ok:
        return "dev_cli", names
    return None, []


def seed_key(url: str) -> str:
    return hashlib.sha256(f"{QUERIES['sampling']['seed']}|{url}".encode("utf-8")).hexdigest()


def load_records(cache: Path) -> list[dict]:
    recs = []
    se = cache / "se.jsonl"
    if se.exists():
        for line in se.read_text(encoding="utf-8").splitlines():
            it = json.loads(line)
            recs.append({
                "source": "stackexchange", "url": f"https://softwarerecs.stackexchange.com/questions/{it['question_id']}",
                "title": html.unescape(it["title"]), "body": strip_html(it.get("body", "")),
                "created": dt.datetime.fromtimestamp(it["creation_date"], UTC),
                "tags": it.get("tags", []), "matched_queries": ["all questions in range"],
                "extras": {"tags": it.get("tags", []), "closed": bool(it.get("closed_date")),
                           "closed_reason": it.get("closed_reason"),
                           "has_accepted_answer": bool(it.get("accepted_answer_id")),
                           "answer_count": it.get("answer_count"),
                           "author": (it.get("owner") or {}).get("display_name")},
                "conflict_text": ""})
    hn = cache / "hn.jsonl"
    if hn.exists():
        for line in hn.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            h = rec["hit"]
            recs.append({
                "source": "hackernews", "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
                "title": html.unescape(h.get("title") or ""), "body": strip_html(h.get("story_text") or ""),
                "created": dt.datetime.fromtimestamp(h["created_at_i"], UTC), "tags": [],
                "matched_queries": rec["matched_queries"],
                "extras": {"points": h.get("points"), "num_comments": h.get("num_comments")},
                "conflict_text": (h.get("author") or "")})
    gh = cache / "gh.jsonl"
    if gh.exists():
        for line in gh.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            n = rec["node"]
            recs.append({
                "source": "github_discussions", "url": n["url"],
                "title": n.get("title") or "", "body": n.get("body") or "",
                "created": dt.datetime.strptime(n["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC), "tags": [],
                "matched_queries": rec["matched_queries"],
                "extras": {"repository": n["repository"]["nameWithOwner"], "stars": n["repository"]["stargazerCount"],
                           "discussion_category": (n.get("category") or {}).get("name"),
                           "has_answer": bool(n.get("answer"))},
                "conflict_text": ((n.get("author") or {}).get("login") or "") + " " + n["repository"]["nameWithOwner"]})
    return recs


def cmd_classify(args: argparse.Namespace) -> None:
    cache = Path(args.cache)
    recs = load_records(cache)
    intent_pat = QUERIES["request_intent"]["pattern"]
    seen: set[str] = set()
    pool, dropped = [], []
    for r in recs:
        url = r["url"]
        body = r["body"]
        long_body = body if r["source"] == "stackexchange" else body[:4000]
        text = r["title"] + "\n" + long_body
        if r["tags"]:
            text += "\n" + "\n".join(f"tag:{t}" for t in r["tags"])
        reason = None
        cat, matched = (None, [])
        if not (FROM <= r["created"] <= TO):
            reason = "date"
        if reason is None:
            cat, matched = categorize(text)
            if cat is None:
                reason = "category"
        if reason is None and r["source"] != "stackexchange":
            if not re.search(intent_pat, r["title"] + "\n" + body[:1500], re.IGNORECASE):
                reason = "request_intent"
        if reason is None and len(r["title"]) + len(body) < 300:
            reason = "min_length"
        if reason is None and re.search(r"ncchen99|pickfit", r["conflict_text"], re.IGNORECASE):
            reason = "no_conflict"
        if reason is None and url in seen:
            reason = "dedupe"
        if reason:
            dropped.append({"source": r["source"], "url": url, "failed": reason})
            continue
        seen.add(url)
        pool.append({"source": r["source"], "url": url, "created": r["created"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "title": r["title"], "category": cat, "category_rule_matched": matched,
                     "seed_key": seed_key(url), "body_chars": len(body),
                     "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                     "matched_queries": r["matched_queries"], "extras": r["extras"]})
    pool.sort(key=lambda p: (p["category"], p["seed_key"], p["url"]))
    counts: dict = {}
    for p in pool:
        counts.setdefault(p["source"], {}).setdefault(p["category"], 0)
        counts[p["source"]][p["category"]] += 1
    dropped_counts: dict = {}
    for d in dropped:
        dropped_counts.setdefault(d["source"], {}).setdefault(d["failed"], 0)
        dropped_counts[d["source"]][d["failed"]] += 1
    fetched = {}
    for r in recs:
        fetched[r["source"]] = fetched.get(r["source"], 0) + 1
    out = {"built": now(), "queries_json_sha256": hashlib.sha256((HERE / "queries.json").read_bytes()).hexdigest(),
           "seed": QUERIES["sampling"]["seed"],
           "note": "Sorted by category then seed_key ascending: this is the draw order. Bodies are not stored here; body_sha256 checks the local cache.",
           "fetched_per_source": fetched, "pool_per_source_and_category": counts, "dropped_per_source_and_reason": dropped_counts,
           "pool": pool}
    (HERE / "pool.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "pool-dropped.json").write_text(json.dumps(dropped, ensure_ascii=False, separators=(",", ":")) + "\n",
                                            encoding="utf-8")
    print(json.dumps({"fetched": fetched, "pool": counts, "dropped": dropped_counts}, indent=1))


def cmd_order(args: argparse.Namespace) -> None:
    """Print the draw order for one category, with the question text from the local cache."""
    cache = Path(args.cache)
    pool = [p for p in json.loads((HERE / "pool.json").read_text())["pool"] if p["category"] == args.category]
    recs = {r["url"]: r for r in load_records(cache)}
    for i, p in enumerate(pool[args.start:args.start + args.count], start=args.start):
        r = recs[p["url"]]
        body = r["body"]
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != p["body_sha256"]:
            print("WARNING body hash mismatch", p["url"])
        print(f"===== [{args.category} #{i}] {p['source']} {p['created'][:10]} {p['url']}")
        print("TITLE:", p["title"])
        if r["tags"]:
            print("TAGS:", ",".join(r["tags"]))
        print(body[: args.chars])
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--cache", required=True)
    f.add_argument("--only", default="all", choices=["all", "stackexchange", "hackernews", "github_discussions"])
    c = sub.add_parser("classify")
    c.add_argument("--cache", required=True)
    o = sub.add_parser("order")
    o.add_argument("--cache", required=True)
    o.add_argument("--category", required=True, choices=CATEGORIES)
    o.add_argument("--start", type=int, default=0)
    o.add_argument("--count", type=int, default=5)
    o.add_argument("--chars", type=int, default=2500)
    args = ap.parse_args()
    {"fetch": cmd_fetch, "classify": cmd_classify, "order": cmd_order}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
