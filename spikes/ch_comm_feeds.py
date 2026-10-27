#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=13"]
# ///
"""dev.to / Mastodon / Bluesky：作者自己發表作品的貼文有多少（只打無需金鑰的公開 API）。

- dev.to（Forem API v1）：GET https://dev.to/api/articles?tag=showdev
- Mastodon：GET https://<instance>/api/v1/timelines/tag/<tag>
- Bluesky AppView：GET https://api.bsky.app/xrpc/app.bsky.feed.searchPosts（未登入只能拿第一頁）
- Bluesky Jetstream v2 live tail（WebSocket，官方文件寫明不需認證）

用法：
  uv run --script spikes/ch_comm_feeds.py                  # 全部
  uv run --script spikes/ch_comm_feeds.py --only devto,mastodon --jetstream-seconds 60

Lobsters 刻意不抓：robots.txt 對一般 User-agent 寫 `Disallow: /`（見調研筆記）。
不需要任何金鑰。
"""
import argparse
import asyncio
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "pickfit-research/0.1 (hackathon spike)"
GH = re.compile(r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.I)
CLI = re.compile(r"\b(cli|tui|command[- ]line|terminal|shell|zsh|bash)\b", re.I)
LOCAL_AI = re.compile(r"\b(ollama|llama\.cpp|gguf|mlx|local (llm|ai|model)s?|offline|on[- ]device|self[- ]hosted)\b", re.I)
AUTHOR = re.compile(r"\b(i|we) (just )?(built|made|wrote|created|released|launched|shipped|open[- ]sourced)\b|"
                    r"\bmy (new |first |side )?(project|tool|app|cli|library)\b|\bshow ?(hn|dev)\b", re.I)


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or ""))


def devto(since, body_sample):
    # 列表不是嚴格按發布時間排序（2026-10-27 實測第 1 頁有 462 處倒序，第 2、3 頁仍各有 86 篇落在 7 天內），
    # 所以不能看最後一筆的時間就停；改成翻到某一頁完全沒有新的 7 天內文章為止（最多 10 頁）。
    arts, seen, page = [], set(), 1
    while page <= 10:
        batch = get_json(f"https://dev.to/api/articles?tag=showdev&per_page=1000&page={page}")
        if not batch:
            break
        new = [a for a in batch if iso(a["published_at"]) >= since and a["id"] not in seen]
        if not new:
            break
        seen.update(a["id"] for a in new)
        arts += new
        page += 1
        time.sleep(1)
    tags = lambda a: set(a.get("tag_list") or [])
    cli = [a for a in arts if CLI.search(a["title"] + " " + (a.get("description") or "")) or tags(a) & {"cli", "terminal", "bash", "shell"}]
    lai = [a for a in arts if LOCAL_AI.search(a["title"] + " " + (a.get("description") or "")) or tags(a) & {"ollama", "localllm", "llama", "selfhosted"}]
    gh = 0
    sample = arts[:body_sample]
    for a in sample:  # 列表不含內文，抽樣抓單篇看有沒有 GitHub 連結
        body = get_json(f"https://dev.to/api/articles/{a['id']}").get("body_markdown") or ""
        gh += bool(GH.search(body))
        time.sleep(0.5)
    days = (datetime.now(timezone.utc) - since).days
    print(f"\n== dev.to #showdev 最近 {days} 天")
    print(f"文章數: {len(arts)}（每天約 {len(arts) / days:.0f}）")
    print(f"標題/摘要/標籤判為 CLI: {len(cli)}；判為本地 AI: {len(lai)}")
    if sample:
        print(f"抽 {len(sample)} 篇讀內文，含 GitHub repo 連結: {gh}（{gh / len(sample):.0%}）")
    rx = [a["positive_reactions_count"] for a in arts]
    if rx:
        print(f"reactions 中位數: {sorted(rx)[len(rx) // 2]}；0 個 reaction: {sum(r == 0 for r in rx)}")
    for a in (cli + lai)[:5]:
        print(f"- {a['title'][:90]}\n  {a['url']}  tags={a['tag_list']}")


def mastodon(since, instances, tags_):
    seen, rows, blocked = set(), [], []
    for inst in instances:
        for tag in tags_:
            max_id, pages = None, 0
            while pages < 8:
                q = {"limit": 40}
                if max_id:
                    q["max_id"] = max_id
                try:
                    batch = get_json(f"https://{inst}/api/v1/timelines/tag/{tag}?{urllib.parse.urlencode(q)}")
                except Exception as e:  # 422 = 該站關閉未登入預覽
                    blocked.append(f"{inst}#{tag}: {e}")
                    break
                if not batch:
                    break
                for s in batch:
                    if iso(s["created_at"]) >= since and s["uri"] not in seen:
                        seen.add(s["uri"])
                        rows.append((inst, tag, s))
                if iso(batch[-1]["created_at"]) < since:
                    break
                max_id, pages = batch[-1]["id"], pages + 1
                time.sleep(0.5)
    print(f"\n== Mastodon hashtag timeline 最近 {(datetime.now(timezone.utc) - since).days} 天（{', '.join(instances)}）")
    if blocked:
        print("需要登入:", "; ".join(blocked[:3]))
    by_tag = {}
    for _, tag, _s in rows:
        by_tag[tag] = by_tag.get(tag, 0) + 1
    print(f"去重後貼文: {len(rows)}；各 tag: {by_tag}")
    gh = [r for r in rows if GH.search(r[2]["content"])]
    auth = [r for r in gh if AUTHOR.search(strip(r[2]["content"]))]
    acc = lambda s: s["account"]
    print(f"含 GitHub repo 連結: {len(gh)}；其中像作者自介作品: {len(auth)}")
    print(f"含 GitHub 的貼文中 bot 帳號: {sum(1 for r in gh if acc(r[2]).get('bot'))}；"
          f"indexable=false: {sum(1 for r in gh if acc(r[2]).get('indexable') is False)}；"
          f"noindex=true: {sum(1 for r in gh if acc(r[2]).get('noindex') is True)}；"
          f"bio 含 #nobot: {sum(1 for r in gh if '#nobot' in strip(acc(r[2]).get('note')).lower())}")
    for _, tag, s in auth[:5]:
        print(f"- #{tag} @{s['account']['acct']}: {strip(s['content'])[:120].strip()}\n  {s['url']}")


def bsky_search(since):
    print(f"\n== Bluesky searchPosts（api.bsky.app，未登入，只取第一頁 ≤100）")
    s = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    for phrase in ['"I built"', '"I made"', '"just released"', '"I wrote"', '"open source"']:
        q = urllib.parse.urlencode({"q": phrase, "domain": "github.com", "sort": "latest",
                                    "since": s, "limit": 100, "lang": "en"})
        try:
            d = get_json(f"https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?{q}")
            posts = d.get("posts", [])
            cli = sum(1 for p in posts if CLI.search(p["record"].get("text", "")))
            lai = sum(1 for p in posts if LOCAL_AI.search(p["record"].get("text", "")))
            print(f"{phrase:18} + domain=github.com：hitsTotal={d.get('hitsTotal')} 本頁={len(posts)} CLI={cli} 本地AI={lai}")
        except Exception as e:
            print(f"{phrase}: {e}")
        time.sleep(0.5)
    try:
        get_json("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=github&limit=1")
        print("public.api.bsky.app searchPosts: 200")
    except Exception as e:
        print(f"public.api.bsky.app searchPosts: {e}（官方建議的快取主機目前擋搜尋）")


async def jetstream(seconds):
    import websockets
    url = ("wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents"
           "?collections=app.bsky.feed.post&kinds=commit")
    n = gh = gh_author = 0
    samples, gh_dids = [], set()
    t0 = time.time()
    async with websockets.connect(url, subprotocols=["xrpc.v1.json"], proxy=True, open_timeout=20,
                                  max_size=2**22) as ws:
        while time.time() - t0 < seconds:
            ev = json.loads(await ws.recv()).get("payload", {})
            if ev.get("operation") != "create":
                continue
            n += 1
            rec = ev.get("record") or {}
            uris = [f.get("uri") or "" for fa in rec.get("facets") or [] for f in fa.get("features") or []]
            emb = rec.get("embed") or {}
            ext = emb.get("external") or (emb.get("media") or {}).get("external") or {}
            uris.append(ext.get("uri") or "")
            if any(GH.search(u) for u in uris):
                gh += 1
                gh_dids.add(ev.get("did"))
                if AUTHOR.search(rec.get("text", "")):
                    gh_author += 1
                    samples.append(rec.get("text", "")[:110].replace("\n", " "))
    el = time.time() - t0
    per_day = lambda x: x / el * 86400
    print(f"\n== Bluesky Jetstream v2 live tail（不需認證）取樣 {el:.0f} 秒")
    print(f"新貼文: {n}（≈{per_day(n):,.0f}/天）；連到 GitHub repo: {gh}（≈{per_day(gh):,.0f}/天）；"
          f"其中像作者自介: {gh_author}（≈{per_day(gh_author):,.0f}/天）；發 GitHub 連結的不同帳號: {len(gh_dids)}")
    for s in samples[:5]:
        print(f"- {s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--only", default="devto,mastodon,bsky,jetstream")
    ap.add_argument("--devto-body-sample", type=int, default=40)
    ap.add_argument("--mastodon-instances", default="mastodon.social,fosstodon.org,hachyderm.io")
    ap.add_argument("--mastodon-tags", default="showdev,opensource,selfhosted,cli,ollama,localllm")
    ap.add_argument("--jetstream-seconds", type=int, default=120)
    a = ap.parse_args()
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    only = set(a.only.split(","))
    print(f"執行時間 {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    if "devto" in only:
        devto(since, a.devto_body_sample)
    if "mastodon" in only:
        mastodon(since, a.mastodon_instances.split(","), a.mastodon_tags.split(","))
    if "bsky" in only:
        bsky_search(since)
    if "jetstream" in only:
        asyncio.run(jetstream(a.jetstream_seconds))


if __name__ == "__main__":
    main()
