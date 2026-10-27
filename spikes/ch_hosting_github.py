#!/usr/bin/env python3
"""調研 spike：GitHub 當「發現新軟體」的管道，實際量最近 7/14 天的結果數與抽樣。

只用 Python 標準函式庫。GitHub 金鑰從環境變數 GH_TOKEN（或 GITHUB_TOKEN）讀，不寫在檔案裡。

    GH_TOKEN=... python3 spikes/ch_hosting_github.py counts      # 兩個 demo 類別的 query 與 7/14 天筆數（約 60 次 search）
    GH_TOKEN=... python3 spikes/ch_hosting_github.py sample      # 7 天聯集、低星抽樣 5 筆，查 latest release
    GH_TOKEN=... python3 spikes/ch_hosting_github.py slice 2026-10-26   # 示範用時間分片繞過 1000 筆上限
    python3 spikes/ch_hosting_github.py queries                  # 只印出 q 字串，不打 API
    python3 spikes/ch_hosting_github.py gharchive 2026-10-26-15 2025-06-16-15   # GH Archive 每小時檔的事件組成

search API 限制 30 次/分鐘（已登入），所以每次 search 之間固定等 2.1 秒。
"""
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

API = os.environ.get("GH_API", "https://api.github.com")  # 測試時可指向本機 mock
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
UA = "pickfit-research-spike/0.1 (+https://github.com/ncchen99/pickfit)"
TODAY = datetime.now(timezone.utc).date()
D7 = (TODAY - timedelta(days=7)).isoformat()
D14 = (TODAY - timedelta(days=14)).isoformat()
YEAR = f"{TODAY.year}-01-01"

# 兩個 demo 類別的 query。{d} 會換成 7 天或 14 天前的日期。
QUERIES = {
    "cli": [
        "topic:cli created:>={d} fork:false",
        "topic:command-line created:>={d} fork:false",
        "topic:terminal created:>={d} fork:false",
        "topic:tui created:>={d} fork:false",
        "cli in:name,description created:>={d} fork:false",
        '"command-line tool" in:description created:>={d} fork:false',
    ],
    "local_ai": [
        "topic:local-llm created:>={d} fork:false",
        "topic:ollama created:>={d} fork:false",
        "topic:llama-cpp created:>={d} fork:false",
        "topic:gguf created:>={d} fork:false",
        "topic:local-ai created:>={d} fork:false",
        "topic:mlx created:>={d} fork:false",
        '"local llm" in:name,description created:>={d} fork:false',
        "ollama in:name,description created:>={d} fork:false",
    ],
}
# 「今年才出現、最近有在動、還沒什麼人知道」：寶藏候選的主力 query
GEM = {
    "cli": "topic:cli created:>={y} pushed:>={d} stars:5..300 fork:false archived:false",
    "local_ai": "topic:local-llm created:>={y} pushed:>={d} stars:5..300 fork:false archived:false",
}


def call(path, params=None):
    if not TOKEN:
        sys.exit("需要環境變數 GH_TOKEN（GitHub personal access token，public 資料只需 read-only，不用勾任何 scope）")
    url = f"{API}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, dict(r.headers), json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (403, 429) and ("rate limit" in body.lower()):
                reset = int(e.headers.get("x-ratelimit-reset", time.time() + 60))
                wait = int(e.headers.get("retry-after") or max(reset - time.time(), 5))
                print(f"  ...rate limited，等 {wait} 秒", file=sys.stderr)
                time.sleep(min(wait, 120))
                continue
            return e.code, dict(e.headers), {"message": body[:300]}
    return 599, {}, {"message": "retry exhausted"}


def search(q, per_page=1, page=1, sort=None):
    params = {"q": q, "per_page": per_page, "page": page}
    if sort:
        params.update(sort=sort, order="desc")
    st, hd, js = call("/search/repositories", params)
    time.sleep(2.1)
    if st != 200:
        raise SystemExit(f"HTTP {st} for q={q!r}: {js.get('message')}")
    return js, hd


def counts():
    print(f"今天 {TODAY}（UTC）；7 天 = created:>={D7}；14 天 = created:>={D14}\n")
    print("| 類別 | q（{d} 為起始日） | 7 天 | 7 天且 stars≥5 | 14 天 | 14 天且 stars≥5 |\n|---|---|---|---|---|---|")
    for cat, qs in QUERIES.items():
        for q in qs:
            row = []
            for d in (D7, D14):
                base = q.format(d=d)
                row += [search(base)[0]["total_count"], search(base + " stars:>=5")[0]["total_count"]]
            print(f"| {cat} | `{q}` | {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    print("\n今年新建、最近 7 天有 push、stars 5..300（寶藏候選）：")
    for cat, q in GEM.items():
        qq = q.format(y=YEAR, d=D7)
        js, hd = search(qq)
        print(f"- {cat}: `{qq}` → {js['total_count']} 筆")
    print(f"\nsearch rate limit 剩餘：{hd.get('x-ratelimit-remaining') or hd.get('X-RateLimit-Remaining')}/{hd.get('x-ratelimit-limit') or hd.get('X-RateLimit-Limit')}")


def sample():
    for cat, qs in QUERIES.items():
        pool = {}
        for q in qs:
            js, _ = search(q.format(d=D7) + " stars:>=1", per_page=100, sort="stars")
            for it in js["items"]:
                pool[it["full_name"]] = it
        items = list(pool.values())
        homepage = sum(1 for x in items if x.get("homepage"))
        lic = sum(1 for x in items if x.get("license"))
        print(f"\n## {cat}：7 天內、stars≥1 的聯集 {len(items)} 筆（每個 query 最多取 100）")
        print(f"有 license：{lic}；有 homepage：{homepage}；stars 中位數：{sorted(x['stargazers_count'] for x in items)[len(items) // 2] if items else '-'}")
        # 抽樣：stars 3..300（排除已經爆紅的），依 stars 排，每位作者 1 筆
        seen, picks = set(), []
        for x in sorted(items, key=lambda x: -x["stargazers_count"]):
            if 3 <= x["stargazers_count"] <= 300 and x["owner"]["login"] not in seen:
                seen.add(x["owner"]["login"])
                picks.append(x)
        for x in picks[:5]:
            st, _, rel = call(f"/repos/{x['full_name']}/releases/latest")
            tag = rel.get("tag_name") if st == 200 else "無 release"
            print(f"- {x['full_name']} · 建立 {x['created_at'][:10]} · ★{x['stargazers_count']} · {x.get('language')} · "
                  f"license {((x.get('license') or {}).get('spdx_id'))} · release {tag} · topics {x.get('topics', [])[:5]} · {(x.get('description') or '')[:90]}")


def slice_day(day):
    """search 每個 query 最多只給 1000 筆：把時間範圍切小，直到每片 total_count ≤ 1000。"""
    base = "fork:false stars:>=1"
    out = []

    def rec(t0, t1):
        q = f"{base} created:{t0:%Y-%m-%dT%H:%M:%SZ}..{t1:%Y-%m-%dT%H:%M:%SZ}"
        n = search(q)[0]["total_count"]
        if n > 1000 and (t1 - t0) > timedelta(minutes=10):
            mid = t0 + (t1 - t0) / 2
            rec(t0, mid)
            rec(mid + timedelta(seconds=1), t1)
        else:
            out.append((q, n))

    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    rec(d, d + timedelta(days=1) - timedelta(seconds=1))
    print(f"`{base}` 在 {day} 一天被切成 {len(out)} 片，合計 {sum(n for _, n in out)} 筆：")
    for q, n in out:
        print(f"- {n:>5}  {q}")


def gharchive(hours):
    print("| 小時檔（UTC） | 事件數 | 新 repo（CreateEvent ref_type=repository） | PushEvent | ReleaseEvent | WatchEvent |\n|---|---|---|---|---|---|")
    for h in hours:
        req = urllib.request.Request(f"https://data.gharchive.org/{h}.json.gz", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
        c = Counter()
        with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8") as f:
            for line in f:
                e = json.loads(line)
                c[e["type"]] += 1
                if e["type"] == "CreateEvent" and (e.get("payload") or {}).get("ref_type") == "repository":
                    c["_new_repo"] += 1
        print(f"| {h} | {sum(v for k, v in c.items() if not k.startswith('_'))} | {c['_new_repo']} | {c['PushEvent']} | {c['ReleaseEvent']} | {c['WatchEvent']} |")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "counts"
    if cmd == "queries":
        for cat, qs in QUERIES.items():
            print(cat, *[q.format(d=D7) for q in qs], GEM[cat].format(y=YEAR, d=D7), sep="\n  ")
    elif cmd == "counts":
        counts()
    elif cmd == "sample":
        sample()
    elif cmd == "slice":
        slice_day(sys.argv[2] if len(sys.argv) > 2 else (TODAY - timedelta(days=1)).isoformat())
    elif cmd == "gharchive":
        gharchive(sys.argv[2:] or [(datetime.now(timezone.utc) - timedelta(hours=26)).strftime("%Y-%m-%d-%-H")])
    else:
        sys.exit(__doc__)
