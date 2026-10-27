#!/usr/bin/env python3
"""ch_meta_threads_hn: 作者有多常把「Threads 貼文」當作品發表的主連結？拿到連結後 oEmbed 能給什麼？

做法（都不需要金鑰）：
1. 用 HN 的 Algolia 搜尋 API（HN 頁尾連結的官方搜尋服務）找最近 N 天、URL 指向
   threads.com / threads.net 的 story，並和 x.com / twitter.com 比較數量。只數「主機名稱完全相符」的。
2. 對最近的 5 筆 Threads 連結呼叫 Threads oEmbed（2026-03-03 起不需 token），
   記錄回傳的 html 裡有沒有貼文文字或 GitHub 連結。

注意：這裡只是量 Threads 作為「作品發表管道」的旁證，不是爬 Threads。
oEmbed 只拿來確認「能給什麼」，依官方條款不得把 oEmbed 內容拿去做前端顯示以外的用途。

執行：python3 spikes/ch_meta_threads_hn.py [--days 365]
"""
import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "pickfit-spike/0.1"
ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
HOSTS = {
    "threads": {"threads.com", "www.threads.com", "threads.net", "www.threads.net"},
    "x/twitter": {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"},
}
QUERY_TERMS = {"threads": ["threads.com", "threads.net"], "x/twitter": ["x.com", "twitter.com"]}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def hn_hits(term, since_ts, max_pages=10):
    hits = []
    for page in range(max_pages):
        params = {
            "query": term,
            "restrictSearchableAttributes": "url",
            "tags": "story",
            "numericFilters": f"created_at_i>{since_ts}",
            "hitsPerPage": 1000,
            "page": page,
        }
        _, d = get_json(ALGOLIA + "?" + urllib.parse.urlencode(params))
        hits += d.get("hits", [])
        if page + 1 >= d.get("nbPages", 0):
            break
    return hits


def host(url):
    return (urllib.parse.urlparse(url or "").hostname or "").lower()


def oembed(url):
    status, d = get_json("https://graph.threads.com/v1.0/oembed?" + urllib.parse.urlencode({"url": url}))
    h = d.get("html", "")
    h2 = re.sub(r"<svg.*?</svg>", "", h, flags=re.S)
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h2))).strip()
    err = d.get("error", {}).get("error_user_title")
    return status, len(h), text, "github.com" in h.lower(), err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()
    now = int(time.time())
    since = now - args.days * 86400

    rows, capped = {}, set()
    for name, terms in QUERY_TERMS.items():
        seen = {}
        for t in terms:
            raw = hn_hits(t, since)
            if len(raw) >= 1000:  # Algolia 每個查詢最多回 1000 筆，超過就只是下限
                capped.add(name)
            for h in raw:
                if host(h.get("url")) in HOSTS[name]:
                    seen[h["objectID"]] = h
        rows[name] = sorted(seen.values(), key=lambda h: -h["created_at_i"])

    print(f"## HN story 連到 Threads 與 X 的數量（主機名稱完全相符，最近 {args.days} 天）\n")
    print("| 主機 | 7 天 | 30 天 | {0} 天 | 其中 Show HN（{0} 天） |\n|---|---|---|---|---|".format(args.days))
    for name, hits in rows.items():
        c7 = sum(h["created_at_i"] > now - 7 * 86400 for h in hits)
        c30 = sum(h["created_at_i"] > now - 30 * 86400 for h in hits)
        show = sum("show_hn" in h.get("_tags", []) for h in hits)
        mark = "≥" if name in capped else ""
        print(f"| {name} | {c7} | {c30} | {mark}{len(hits)} | {mark}{show} |")
    if capped:
        print("\n「≥」：原始查詢碰到 Algolia 1000 筆上限，長區間的數字只是下限。")

    print("\n## 最近 5 筆 Threads 連結的 oEmbed 結果（無 token）\n")
    print("| 日期 | HN 標題 | oEmbed | html bytes | 可見文字 | 含 github.com |\n|---|---|---|---|---|---|")
    for h in rows["threads"][:5]:
        status, n, text, has_gh, err = oembed(h["url"])
        title = h["title"][:60].replace("|", "/")
        print(f"| {h['created_at'][:10]} | {title} | HTTP {status}{' ' + err if err else ''} | {n} | {text[:30]!r} | {has_gh} |")


if __name__ == "__main__":
    main()
