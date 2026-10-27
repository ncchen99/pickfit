#!/usr/bin/env python3
"""Show HN 近 N 天的量與品質抽樣（只用無需金鑰的官方 API）。

資料來源：
- Algolia HN Search API（HN 官方站上 "Search" 連結用的服務）：
  https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=created_at_i>T
- HN 官方 Firebase API：https://hacker-news.firebaseio.com/v0/showstories.json

用法：
  python3 spikes/ch_comm_hn_showhn.py            # 最近 7 天
  python3 spikes/ch_comm_hn_showhn.py --days 3 --sample 8 --seed 1

只用 Python 標準函式庫；不需要任何金鑰。
"""
import argparse
import json
import random
import re
import statistics
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "pickfit-research/0.1 (hackathon spike)"
ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
FIREBASE = "https://hacker-news.firebaseio.com/v0"

GH_REPO = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)
# 粗略的關鍵字分類；只拿來估量，不是產品邏輯。
CLI = re.compile(
    r"\b(cli|tui|command[- ]line|terminal|shell|bash|zsh|fish|repl|"
    r"cargo install|brew install|pipx|npx|go install|uvx)\b", re.I)
AI = re.compile(r"\b(llms?|ai|gpt|models?|agents?|inference|rag|embeddings?|whisper|"
                r"transcri\w+|ollama|llama(\.cpp)?|gguf|mlx|vllm|onnx|diffusion)\b", re.I)
LOCAL = re.compile(r"\b(local(ly)?|offline|on[- ]device|self[- ]hosted|private|"
                   r"on your (own )?(machine|laptop|mac|computer|gpu)|ollama|llama\.cpp|"
                   r"gguf|mlx|no cloud|air[- ]gapped)\b", re.I)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_show_hn(since, until):
    """依時間切片抓，避開 Algolia 每次查詢最多 1000 筆的分頁上限。"""
    hits, step = [], 86400
    t = since
    while t < until:
        t2 = min(t + step, until)
        q = urllib.parse.urlencode({
            "tags": "show_hn",
            "numericFilters": f"created_at_i>{t},created_at_i<={t2}",
            "hitsPerPage": 1000,
        })
        d = get_json(f"{ALGOLIA}?{q}")
        if d["nbHits"] > 1000:
            raise SystemExit("單一切片超過 1000 筆，請縮小 step")
        hits += d["hits"]
        t = t2
        time.sleep(0.2)
    return hits


def repo_of(h):
    for text in (h.get("url") or "", h.get("story_text") or ""):
        m = GH_REPO.search(text)
        if m:
            return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    return None


def classify(h):
    text = " ".join([h.get("title") or "", h.get("url") or "", h.get("story_text") or ""])
    text = re.sub(r"<[^>]+>", " ", text)
    is_cli = bool(CLI.search(text))
    is_local_ai = bool(AI.search(text)) and bool(LOCAL.search(text))
    return is_cli, is_local_ai


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20261028)
    a = ap.parse_args()

    now = int(time.time())
    since = now - a.days * 86400
    hits = fetch_show_hn(since, now)
    n = len(hits)
    with_url = [h for h in hits if h.get("url")]
    gh = [h for h in hits if repo_of(h)]
    gh_in_url = [h for h in hits if GH_REPO.search(h.get("url") or "")]
    cls = {h["objectID"]: classify(h) for h in hits}
    cli = [h for h in hits if cls[h["objectID"]][0]]
    lai = [h for h in hits if cls[h["objectID"]][1]]
    pts = [h.get("points") or 0 for h in hits]

    # 官方 Firebase：/show 頁（過了 points 門檻的 Show HN）
    show_ids = get_json(f"{FIREBASE}/showstories.json")
    with ThreadPoolExecutor(8) as ex:
        items = [i for i in ex.map(lambda i: get_json(f"{FIREBASE}/item/{i}.json"), show_ids) if i]
    fb_show = [i for i in items if (i.get("title") or "").lower().startswith("show hn")]
    fb_recent = [i for i in fb_show if i.get("time", 0) > since]
    alg_ids = {int(h["objectID"]) for h in hits}

    def pct(x):
        return f"{x}/{n} ({x / n:.0%})" if n else "0"

    print(f"== Show HN 最近 {a.days} 天（Algolia，{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}）")
    print(f"總數: {n}（每天約 {n / a.days:.0f} 筆）")
    print(f"有外部連結: {pct(len(with_url))}")
    print(f"連到 GitHub repo（url 或內文）: {pct(len(gh))}；只看 url: {pct(len(gh_in_url))}")
    print(f"關鍵字判為 CLI/終端工具: {pct(len(cli))}；其中連 GitHub: {sum(1 for h in cli if repo_of(h))}")
    print(f"關鍵字判為本地 AI/LLM 工具: {pct(len(lai))}；其中連 GitHub: {sum(1 for h in lai if repo_of(h))}")
    print(f"points 中位數: {statistics.median(pts) if pts else 0}；<=3 分: {pct(sum(p <= 3 for p in pts))}；"
          f">=50 分: {pct(sum(p >= 50 for p in pts))}；>=100 分: {pct(sum(p >= 100 for p in pts))}")
    print(f"\n== 官方 Firebase /v0/showstories（/show 頁，最多 200 筆）")
    print(f"回傳 {len(show_ids)} 筆，其中 Show HN {len(fb_show)} 筆；落在最近 {a.days} 天: {len(fb_recent)} 筆"
          f"（Algolia 同期 {n} 筆 → Firebase 只涵蓋 {len(fb_recent) / n:.0%}）" if n else "")
    print(f"Firebase 近期項目都在 Algolia 結果內: {all(i['id'] in alg_ids for i in fb_recent)}")

    pool = [h for h in hits if repo_of(h) and (cls[h["objectID"]][0] or cls[h["objectID"]][1])]
    random.Random(a.seed).shuffle(pool)
    print(f"\n== 抽樣 {a.sample} 筆（CLI 或本地 AI，且連到 GitHub；候選 {len(pool)} 筆，seed={a.seed}）")
    for h in pool[: a.sample]:
        tag = "+".join(k for k, v in zip(("CLI", "localAI"), cls[h["objectID"]]) if v)
        print(f"- [{tag}] {h['title']}\n  {h.get('url')}\n  points={h.get('points')} comments={h.get('num_comments')} "
              f"created={h['created_at'][:16]} hn=https://news.ycombinator.com/item?id={h['objectID']}")


if __name__ == "__main__":
    main()
