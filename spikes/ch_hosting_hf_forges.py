#!/usr/bin/env python3
"""調研 spike：Hugging Face Spaces、Codeberg、GitLab.com 最近 7/14 天的新作品量與抽樣。

只用 Python 標準函式庫，不需要金鑰（HF_TOKEN 若有設就帶上，可提高 HF rate limit）。
請求量刻意壓低（HF API 約 12 次＋讀約 70 份 README、Codeberg 6 次、GitLab 5 次），不是爬蟲。

    python3 spikes/ch_hosting_hf_forges.py            # 全部
    python3 spikes/ch_hosting_hf_forges.py hf         # 只跑 Hugging Face
    python3 spikes/ch_hosting_hf_forges.py codeberg gitlab
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "pickfit-research-spike/0.1 (+https://github.com/ncchen99/pickfit)"
NOW = datetime.now(timezone.utc)
D7 = (NOW - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
D14 = (NOW - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
GH_LINK = re.compile(r"github\.com/[\w.-]+/[\w.-]+")


def get(url, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def window(items, key):
    # 各平台時間格式不同（Z 或 +01:00），統一轉成 UTC 再比
    def utc(s):
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    n7 = sum(1 for x in items if utc(x[key]) >= D7)
    n14 = sum(1 for x in items if utc(x[key]) >= D14)
    return n7, n14


# ---------------------------------------------------------------- Hugging Face
HF_QUERIES = [  # 本地 AI／LLM 工具在 HF Spaces 上的樣子
    ("filter", "webgpu"), ("filter", "transformers.js"), ("filter", "mcp-server"),
    ("search", "ollama"), ("search", "gguf"), ("search", "local"), ("search", "offline"), ("search", "cli"),
]


def hf():
    tok = os.environ.get("HF_TOKEN")
    hdr = {"Authorization": f"Bearer {tok}"} if tok else {}
    base = "https://huggingface.co/api/spaces"
    exp = "".join(f"&expand[]={f}" for f in ["createdAt", "likes", "sdk", "cardData", "runtime"])
    print("\n## Hugging Face Spaces（sort=createdAt，每個查詢取最新 1000 筆）")
    print("| 查詢 | 7 天 | 14 天 |\n|---|---|---|")
    pool = {}
    for kind, val in HF_QUERIES:
        st, hd, body = get(f"{base}?{kind}={urllib.parse.quote(val)}&sort=createdAt&direction=-1&limit=1000{exp}", hdr)
        if st != 200:
            print(f"| {kind}={val} | HTTP {st} | |")
            continue
        items = json.loads(body)
        n7, n14 = window(items, "createdAt")
        print(f"| {kind}={val} | {n7} | {n14} |")
        if val not in ("mcp-server", "cli"):  # 這兩個不算「本地 AI」，只計數（search=cli 也會比對到 client 等字）
            for x in items:
                if x["createdAt"] >= D7:
                    pool[x["id"]] = x
    print(f"\nRateLimit 標頭（最後一次）：{hd.get('RateLimit') or hd.get('ratelimit')}")
    # 全站新 Space / model 量（估每天幾筆）
    for kind in ("spaces", "models"):
        st, _, body = get(f"https://huggingface.co/api/{kind}?sort=createdAt&direction=-1&limit=1000&expand[]=createdAt", hdr)
        items = json.loads(body)
        t0 = datetime.fromisoformat(items[0]["createdAt"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(items[-1]["createdAt"].replace("Z", "+00:00"))
        print(f"全站最新 1000 個 {kind} 橫跨 {(t0 - t1).total_seconds() / 3600:.1f} 小時 ≈ {1000 / max((t0 - t1).total_seconds() / 86400, 1e-6):.0f} 個/天")
    # 7 天內、本地 AI 相關的 Space：README 有沒有連到 GitHub、執行狀態、likes
    items = list(pool.values())
    gh = 0
    for x in items:
        st, _, readme = get(f"https://huggingface.co/spaces/{x['id']}/raw/main/README.md")
        x["_gh"] = GH_LINK.findall(readme) if st == 200 else []
        gh += bool(x["_gh"])
    running = sum(1 for x in items if (x.get("runtime") or {}).get("stage") == "RUNNING")
    liked = sum(1 for x in items if x.get("likes", 0) >= 1)
    print(f"\n7 天內本地 AI 相關 Space（去重）：{len(items)} 筆；README 連到 GitHub repo：{gh}；RUNNING：{running}；likes≥1：{liked}")
    print("\n抽樣（likes 高者優先，取 5 筆）：")
    for x in sorted(items, key=lambda x: (-x.get("likes", 0), x["id"]))[:5]:
        desc = (x.get("cardData") or {}).get("short_description", "")
        print(f"- {x['id']} · {x['createdAt'][:10]} · likes {x.get('likes', 0)} · {x.get('sdk')} · "
              f"{(x.get('runtime') or {}).get('stage')} · {desc} · GitHub: {x['_gh'][:1]}")
    # 換個角度：trending 前 1000 名裡「14 天內才建立」且看起來是本地／瀏覽器端 AI 的
    st, _, body = get(f"{base}?sort=trendingScore&direction=-1&limit=1000{exp}&expand[]=trendingScore", hdr)
    tr = json.loads(body)
    new = [x for x in tr if x["createdAt"] >= D14]
    kw = re.compile(r"local|offline|webgpu|in[- ]browser|your browser|on-device|gguf|ollama|llama\.cpp|mlx", re.I)
    hits = [x for x in new if kw.search(json.dumps(x.get("cardData") or {}) + x["id"])]
    print(f"\ntrending 前 1000 名：14 天內建立 {len(new)} 個（7 天內 {sum(1 for x in new if x['createdAt'] >= D7)}）；其中描述像本地／瀏覽器端 AI：{len(hits)}")
    for x in hits[:8]:
        print(f"- {x['id']} · {x['createdAt'][:10]} · likes {x.get('likes', 0)} · trending {x.get('trendingScore')} · {(x.get('cardData') or {}).get('short_description', '')}")


# ---------------------------------------------------------------- Codeberg (Forgejo)
CB_QUERIES = ["cli", "terminal", "tui", "llm", "ollama", "local-llm"]  # 以 topic 搜尋


def codeberg():
    print("\n## Codeberg（/api/v1/repos/search，topic=true，mode=source，sort=created desc，取第 1 頁 50 筆）")
    print("| topic | 7 天 | 14 天 | 該 topic 總數 |\n|---|---|---|---|")
    pool = {}
    for q in CB_QUERIES:
        url = f"https://codeberg.org/api/v1/repos/search?q={q}&topic=true&mode=source&sort=created&order=desc&limit=50"
        st, hd, body = get(url)
        if st != 200:
            print(f"| {q} | HTTP {st} | | |")
            continue
        items = json.loads(body)["data"]
        n7, n14 = window(items, "created_at")
        print(f"| {q} | {n7}{'+' if n7 == 50 else ''} | {n14}{'+' if n14 == 50 else ''} | {hd.get('X-Total-Count') or hd.get('x-total-count')} |")
        for x in items:
            if x["created_at"] >= D7[:10]:
                pool[x["full_name"]] = x
        time.sleep(1)
    print(f"\nRateLimit 標頭（最後一次）：{hd.get('RateLimit') or hd.get('ratelimit')} / {hd.get('RateLimit-Policy') or hd.get('ratelimit-policy')}")
    items = list(pool.values())
    print(f"7 天內（去重）：{len(items)} 筆；stars≥1：{sum(1 for x in items if x['stars_count'] >= 1)}；有描述：{sum(1 for x in items if x['description'])}；有 release：{sum(1 for x in items if x.get('release_counter', 0) > 0)}")
    owners = {}
    for x in items:
        owners[x["owner"]["login"]] = owners.get(x["owner"]["login"], 0) + 1
    print(f"同一作者 7 天內建 ≥3 個 repo 的帳號：{ {k: v for k, v in owners.items() if v >= 3} }")
    print("抽樣 5 筆（每位作者最多 1 筆，stars 高者優先）：")
    seen, picks = set(), []
    for x in sorted(items, key=lambda x: (-x["stars_count"], x["full_name"])):
        if x["owner"]["login"] not in seen:
            seen.add(x["owner"]["login"])
            picks.append(x)
    for x in picks[:5]:
        print(f"- {x['full_name']} · {x['created_at'][:10]} · ★{x['stars_count']} · {x['language']} · {x['description'][:80]}")


# ---------------------------------------------------------------- GitLab.com
GL_TOPICS = ["cli", "command-line", "llm", "ollama"]


def gitlab():
    print("\n## GitLab.com（/api/v4/projects?topic=…&order_by=created_at，未登入，取第 1 頁 100 筆）")
    print("| topic | 7 天 | 14 天 | 7 天內 stars≥1 |\n|---|---|---|---|")
    for t in GL_TOPICS:
        url = f"https://gitlab.com/api/v4/projects?topic={t}&visibility=public&order_by=created_at&sort=desc&per_page=100&simple=true"
        st, hd, body = get(url)
        if st == 429:  # 依 Retry-After 等一次再試
            time.sleep(min(int(hd.get("Retry-After") or hd.get("retry-after") or 60), 120))
            st, hd, body = get(url)
        if st != 200:
            print(f"| {t} | HTTP {st}（{body[:60]}） | | |")
        else:
            items = json.loads(body)
            n7, n14 = window(items, "created_at")
            s1 = sum(1 for x in items if x["created_at"] >= D7 and x.get("star_count", 0) >= 1)
            print(f"| {t} | {n7} | {n14} | {s1} |")
        time.sleep(5)  # 未登入的 /projects 有 400 次/10 分鐘/IP 的限制，共用出口 IP 時很容易 429
    st, _, body = get("https://gitlab.com/api/v4/projects?visibility=public&order_by=created_at&sort=desc&per_page=100&simple=true")
    if st == 200:
        items = json.loads(body)
        t0 = datetime.fromisoformat(items[0]["created_at"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(items[-1]["created_at"].replace("Z", "+00:00"))
        print(f"\n全站最新 100 個 public project 橫跨 {(t0 - t1).total_seconds() / 60:.0f} 分鐘 ≈ {100 / max((t0 - t1).total_seconds() / 86400, 1e-6):.0f} 個/天")


if __name__ == "__main__":
    print(f"# ch_hosting_hf_forges · 執行時間 {NOW.isoformat(timespec='seconds')} · 7 天界線 {D7}Z · 14 天界線 {D14}Z")
    which = sys.argv[1:] or ["hf", "codeberg", "gitlab"]
    for name in which:
        {"hf": hf, "codeberg": codeberg, "gitlab": gitlab}[name]()
