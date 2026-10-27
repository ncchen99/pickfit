#!/usr/bin/env python3
"""各地區「作者自己發表作品」的專區：最近 7 天有幾篇、幾篇連到 GitHub repo。

只打無需金鑰的官方 API 或 RSS／Atom（Python 標準函式庫，不需任何金鑰）：
- V2EX「分享创造」(create)：Atom /feed/create.xml（約 50 篇）＋ API v1 /api/topics/show.json（10 篇）
- GeekNews：Atom /rss/news，挑標題含「Show GN」的
- Qiita：API v2 /api/v2/items?query=tag:個人開発 created:>=...（未登入 60 次／小時／IP）
- Zenn：主題 RSS /topics/<topic>/feed（官方說明每個 feed 約 20 篇）
- PTT：網頁版 Atom /atom/<board>.xml（非正式文件，見調研筆記）

用法：
  python3 spikes/ch_regional_authors.py
  python3 spikes/ch_regional_authors.py --only v2ex,qiita --samples 5
"""
import argparse
import email.utils
import json
import random
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = "pickfit-research/0.1 (hackathon spike; contact via GitHub)"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
GH = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)
GH_SKIP = {"features", "orgs", "topics", "sponsors", "marketplace", "settings", "apps", "login", "about"}
CLI = re.compile(r"\b(cli|tui|terminal|shell|command[- ]line)\b|命令行|命令列|终端|終端|コマンドライン|ターミナル|터미널|커맨드", re.I)
LOCAL_AI = re.compile(r"ollama|llama\.cpp|gguf|\bmlx\b|lm ?studio|local (llm|model|ai)|本地(大)?模型|本地 ?llm|离线|離線|"
                      r"ローカル ?llm|ローカルモデル|오프라인|로컬 ?llm|on[- ]device", re.I)
AUTHOR = re.compile(r"我(做|写|寫|开发|開發)了|做了(一个|一個|个|個)|自荐|作った|作りました|開発しました|作ってみた|"
                    r"만들었|개발했|Show GN|\bI (built|made|wrote)\b", re.I)


def fetch(url, accept="*/*", timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers)


def repos(text):
    out = []
    for o, n in GH.findall(text or ""):
        n = re.sub(r"\.git$", "", n)
        if o.lower() in GH_SKIP:
            continue
        key = f"{o}/{n}".lower()
        if key not in [x.lower() for x in out]:
            out.append(f"{o}/{n}")
    return out


def tag(text):
    t = []
    if CLI.search(text or ""):
        t.append("cli")
    if LOCAL_AI.search(text or ""):
        t.append("local-ai")
    if AUTHOR.search(text or ""):
        t.append("author")
    return t


def summarize(name, posts, since, now, note=""):
    """posts: list of dict(title, url, date, text)."""
    in7 = [p for p in posts if p["date"] >= since]
    dates = [p["date"] for p in posts]
    span_h = (max(dates) - min(dates)).total_seconds() / 3600 if len(dates) > 1 else 0
    gh = [p for p in in7 if repos(p["text"]) or repos(p["url"])]
    for p in in7:
        p["repos"] = repos(p["text"]) or repos(p["url"])
        p["tags"] = tag(p["title"] + " " + p["text"])
    res = {
        "channel": name,
        "fetched": len(posts),
        "covers_hours": round(span_h, 1),
        "in_7d": len(in7),
        "with_github_repo": len(gh),
        "github_ratio": round(len(gh) / len(in7), 2) if in7 else None,
        "cli_kw": sum("cli" in p["tags"] for p in in7),
        "local_ai_kw": sum("local-ai" in p["tags"] for p in in7),
        "note": note,
    }
    # 視窗不到 7 天時，用每小時篇數外推（標明是估計）
    if posts and min(dates) > since and span_h > 0:
        res["est_7d"] = round(len(posts) / span_h * 24 * 7)
    return res, in7


def v2ex(since, now):
    raw, _ = fetch("https://www.v2ex.com/feed/create.xml")
    root = ET.fromstring(raw)
    posts = []
    for e in root.findall("a:entry", ATOM):
        posts.append({
            "title": e.findtext("a:title", "", ATOM),
            "url": e.find("a:link", ATOM).get("href"),
            "date": datetime.fromisoformat(e.findtext("a:published", "", ATOM).replace("Z", "+00:00")),
            "text": e.findtext("a:content", "", ATOM),
        })
    raw, hdr = fetch("https://www.v2ex.com/api/topics/show.json?node_name=create", "application/json")
    api = json.loads(raw)
    node = json.loads(fetch("https://www.v2ex.com/api/nodes/show.json?name=create")[0])
    note = (f"API v1 只回 {len(api)} 篇且不能翻頁；Atom 約 50 篇。節點累計 {node.get('topics')} 篇。"
            f"v1 rate limit 標頭：{hdr.get('X-Rate-Limit-Limit') or hdr.get('x-rate-limit-limit')}")
    return summarize("V2EX 分享创造", posts, since, now, note)


def geeknews(since, now):
    raw, _ = fetch("https://news.hada.io/rss/news")
    root = ET.fromstring(raw)
    allp, show = [], []
    for e in root.findall("a:entry", ATOM):
        p = {
            "title": e.findtext("a:title", "", ATOM),
            "url": e.find("a:link", ATOM).get("href"),
            "date": datetime.fromisoformat(e.findtext("a:published", "", ATOM)),
            "text": e.findtext("a:content", "", ATOM),
        }
        allp.append(p)
        if p["title"].startswith("Show GN"):
            show.append(p)
    span = (max(p["date"] for p in allp) - min(p["date"] for p in allp)).total_seconds() / 3600
    note = f"RSS 共 {len(allp)} 篇（約 {span:.0f} 小時），其中 Show GN {len(show)} 篇；Show GN 沒有獨立 RSS"
    res, in7 = summarize("GeekNews Show GN", show, since, now, note)
    if span > 0:
        res["est_7d"] = round(len(show) / span * 24 * 7)
    return res, in7


def qiita(since, now, max_pages=3):
    day = since.strftime("%Y-%m-%d")
    q = f"tag:個人開発 created:>={day}"
    posts, page, total, remaining = [], 1, None, None
    while page <= max_pages:
        url = "https://qiita.com/api/v2/items?" + urllib.parse.urlencode({"query": q, "per_page": 100, "page": page})
        raw, hdr = fetch(url, "application/json")
        h = {k.lower(): v for k, v in hdr.items()}
        total, remaining = int(h.get("total-count", 0)), h.get("rate-remaining")
        items = json.loads(raw)
        for it in items:
            posts.append({
                "title": it["title"], "url": it["url"],
                "date": datetime.fromisoformat(it["created_at"]),
                "text": it.get("body", ""),
                "likes": it.get("likes_count"), "stocks": it.get("stocks_count"),
                "tags_q": [t["name"] for t in it.get("tags", [])],
            })
        if len(items) < 100 or len(posts) >= total:
            break
        page += 1
        time.sleep(1)
    counts = {}
    for extra in ["tag:CLI", "tag:ローカルLLM", "tag:Ollama", "tag:OSS"]:
        url = "https://qiita.com/api/v2/items?" + urllib.parse.urlencode(
            {"query": f"{extra} created:>={day}", "per_page": 1})
        _, hdr = fetch(url, "application/json")
        counts[extra] = int({k.lower(): v for k, v in hdr.items()}.get("total-count", 0))
        time.sleep(1)
    res, in7 = summarize("Qiita tag:個人開発", posts, since, now,
                         f"total-count={total}；同期間其他 tag 篇數 {counts}；rate-remaining={remaining}")
    likes = sorted(p["likes"] or 0 for p in in7)
    if likes:
        res["likes_median"] = likes[len(likes) // 2]
    return res, in7


def zenn(since, now, topics=("個人開発", "cli", "ollama", "localllm", "oss")):
    out = []
    for t in topics:
        raw, _ = fetch(f"https://zenn.dev/topics/{urllib.parse.quote(t)}/feed")
        root = ET.fromstring(raw)
        posts = []
        for it in root.iter("item"):
            posts.append({
                "title": it.findtext("title", ""), "url": it.findtext("link", ""),
                "date": email.utils.parsedate_to_datetime(it.findtext("pubDate")),
                "text": it.findtext("description", ""),
            })
        res, in7 = summarize(f"Zenn topic:{t}", posts, since, now,
                             "feed 上限約 20 篇、description 只有摘要（GitHub 比例會低估）")
        out.append((res, in7))
        time.sleep(1)
    return out


def ptt(since, now, boards=("Soft_Job", "Linux", "Python", "Programming")):
    out = []
    for b in boards:
        try:
            raw, _ = fetch(f"https://www.ptt.cc/atom/{b}.xml")
        except Exception as ex:  # 常見 522（Cloudflare 連不到源站）
            out.append(({"channel": f"PTT {b}", "error": str(ex)}, []))
            continue
        root = ET.fromstring(raw)
        posts = [{
            "title": e.findtext("a:title", "", ATOM),
            "url": e.find("a:link", ATOM).get("href"),
            "date": datetime.fromisoformat(e.findtext("a:published", "", ATOM)),
            "text": e.findtext("a:content", "", ATOM),
        } for e in root.findall("a:entry", ATOM)]
        res, in7 = summarize(f"PTT {b}", posts, since, now, "Atom 只給最新 20 篇")
        res["share_tag_in_7d"] = sum("[分享]" in p["title"] for p in in7)
        out.append((res, in7))
        time.sleep(2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="v2ex,geeknews,qiita,zenn,ptt")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    random.seed(args.seed)
    print(f"# now={now:%Y-%m-%d %H:%M} UTC, window=7d (since {since:%Y-%m-%d %H:%M})\n")
    runs = {"v2ex": lambda: [v2ex(since, now)], "geeknews": lambda: [geeknews(since, now)],
            "qiita": lambda: [qiita(since, now)], "zenn": lambda: zenn(since, now), "ptt": lambda: ptt(since, now)}
    for key in args.only.split(","):
        try:
            results = runs[key]()
        except Exception as ex:
            print(f"## {key}: ERROR {ex}\n")
            continue
        for res, in7 in results:
            print("## " + res["channel"])
            print(json.dumps({k: v for k, v in res.items() if k != "channel"}, ensure_ascii=False))
            with_repo = [p for p in in7 if p.get("repos")]
            for p in random.sample(with_repo, min(args.samples, len(with_repo))):
                print(f"  - {p['date']:%m-%d} {p['title'][:70]} | {', '.join(p['repos'][:2])} | {','.join(p['tags'])}")
            print()


if __name__ == "__main__":
    main()
