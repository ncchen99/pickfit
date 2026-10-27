#!/usr/bin/env python3
"""各地區「策展／聚合」型管道：最近 7 天有幾筆 GitHub repo、雜訊多少。

只打無需金鑰的官方 RSS 或公開檔案（Python 標準函式庫，不需任何金鑰）：
- Hatena Bookmark：/site/github.com/?mode=rss&sort=new（日本使用者新收藏的 GitHub 頁面；只回最新 30 筆、不能翻頁）
- 阮一峰《科技爱好者周刊》：GitHub raw 的 docs/issue-N.md，解析「工具」小節（每週五一期）
- HelloGitHub 月刊：GitHub raw 的 content/HelloGitHubN.md（每月 28 號一期）
- 雜訊對照：velog 全站 RSS、Habr open_source hub RSS、OSChina 資訊 RSS

用法：
  python3 spikes/ch_regional_curated.py
  python3 spikes/ch_regional_curated.py --only hatena,ruanyf --ruanyf-issues 1
"""
import argparse
import email.utils
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = "pickfit-research/0.1 (hackathon spike)"
RAW = "https://raw.githubusercontent.com"
GH = re.compile(r"(?<![\w.-])github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)  # 排除 hellogithub.com
GH_SKIP = {"features", "orgs", "topics", "sponsors", "marketplace", "settings", "apps", "login", "about", "ruanyf"}
CLI = re.compile(r"\b(cli|tui|terminal|shell|command[- ]line)\b|命令行|终端|コマンドライン|ターミナル", re.I)
LOCAL_AI = re.compile(r"ollama|llama\.cpp|gguf|\bmlx\b|local (llm|model|ai)|本地(大)?模型|本地 ?llm|离线|ローカル ?llm", re.I)
RSS1 = {"rss": "http://purl.org/rss/1.0/", "dc": "http://purl.org/dc/elements/1.1/",
        "hatena": "http://www.hatena.ne.jp/info/xmlns#"}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def repo_of(text):
    for o, n in GH.findall(text or ""):
        if o.lower() not in GH_SKIP:
            return f"{o}/{re.sub(r'(\.git)$', '', n)}"
    return None


def hatena(since):
    # 實測（2026-10-27）：site feed 的 page／of 參數都被忽略，永遠只回最新 30 筆，所以只抓一頁
    raw = fetch("https://b.hatena.ne.jp/site/github.com/?mode=rss&sort=new")
    rows = [{
        "title": it.findtext("rss:title", "", RSS1),
        "url": it.findtext("rss:link", "", RSS1),
        "date": datetime.fromisoformat(it.findtext("dc:date", "", RSS1).replace("Z", "+00:00")),
        "users": int(it.findtext("hatena:bookmarkcount", "0", RSS1) or 0),
    } for it in ET.fromstring(raw).findall("rss:item", RSS1)]
    in7 = [r for r in rows if r["date"] >= since]
    span_h = (max(r["date"] for r in rows) - min(r["date"] for r in rows)).total_seconds() / 3600 if rows else 0
    repos = {}
    for r in in7:
        rp = repo_of(r["url"])
        if rp:
            repos.setdefault(rp, r)
    users = sorted(r["users"] for r in in7)
    res = {
        "fetched": len(rows), "covers_hours": round(span_h, 1),
        "est_repos_7d": round(len(repos) / span_h * 24 * 7) if span_h else None,
        "entries_7d": len(in7), "unique_repos_7d": len(repos),
        "users_median": users[len(users) // 2] if users else None,
        "users_le_3": sum(u <= 3 for u in users),
        "cli_kw": sum(bool(CLI.search(r["title"])) for r in repos.values()),
        "local_ai_kw": sum(bool(LOCAL_AI.search(r["title"])) for r in repos.values()),
        "oldest_fetched": min(r["date"] for r in rows).isoformat() if rows else None,
    }
    return res, list(repos.items())


def ruanyf(n_issues=1):
    readme = fetch(f"{RAW}/ruanyf/weekly/master/README.md").decode()
    latest = max(int(x) for x in re.findall(r"docs/issue-(\d+)\.md", readme))
    out = []
    for n in range(latest, latest - n_issues, -1):
        md = fetch(f"{RAW}/ruanyf/weekly/master/docs/issue-{n}.md").decode()
        m = re.search(r"\n## 工具\n(.*?)\n## ", md, re.S)
        sec = m.group(1) if m else ""
        items = re.split(r"\n(?=\d+、\[)", "\n" + sec)
        items = [i for i in items if re.match(r"\s*\d+、\[", i)]
        rows = []
        for it in items:
            name = re.match(r"\s*\d+、\[([^\]]+)\]\(([^)]+)\)", it)
            rows.append({"name": name.group(1), "url": name.group(2), "repo": repo_of(name.group(2)),
                         "submitted": "投稿" in it, "cli": bool(CLI.search(it)), "local_ai": bool(LOCAL_AI.search(it)),
                         "desc": re.sub(r"!\[\]\([^)]*\)|\s+", " ", it.split(")", 1)[-1]).strip()[:60]})
        out.append({"issue": n, "tools": len(rows), "github_repo": sum(bool(r["repo"]) for r in rows),
                    "author_submitted": sum(r["submitted"] for r in rows),
                    "cli_kw": sum(r["cli"] for r in rows), "local_ai_kw": sum(r["local_ai"] for r in rows),
                    "rows": rows})
        time.sleep(1)
    return out


def hellogithub():
    readme = fetch(f"{RAW}/521xueweihan/HelloGitHub/master/README.md").decode()
    latest = max(int(x) for x in re.findall(r"HelloGitHub(\d+)\.md", readme))
    md = fetch(f"{RAW}/521xueweihan/HelloGitHub/master/content/HelloGitHub{latest}.md").decode()
    rows, section = [], None
    for line in md.splitlines():
        if line.startswith("### "):
            section = line[4:].strip()
        m = re.match(r"(\d+)、\[([^\]]+)\]\(([^)]+)\)：(.*)", line)
        if m:
            rows.append({"name": m.group(2), "repo": repo_of(m.group(3)), "section": section,
                         "shared_by_user": "的分享" in line, "cli": bool(CLI.search(line)),
                         "local_ai": bool(LOCAL_AI.search(line)), "desc": m.group(4)[:50]})
    sections = {}
    for r in rows:
        sections[r["section"]] = sections.get(r["section"], 0) + 1
    return {"issue": latest, "projects": len(rows), "github_repo": sum(bool(r["repo"]) for r in rows),
            "shared_by_user": sum(r["shared_by_user"] for r in rows), "cli_kw": sum(r["cli"] for r in rows),
            "local_ai_kw": sum(r["local_ai"] for r in rows), "sections": sections, "rows": rows}


def rss2(url, since):
    root = ET.fromstring(fetch(url))
    items = [{"title": i.findtext("title", ""), "date": email.utils.parsedate_to_datetime(i.findtext("pubDate")),
              "desc": i.findtext("description", "")} for i in root.iter("item")]
    in7 = [i for i in items if i["date"] >= since]
    span = (max(i["date"] for i in items) - min(i["date"] for i in items)).total_seconds() / 3600 if items else 0
    return items, in7, span


def noise(since):
    spam = re.compile(r"[一-鿿].*(薇|飞机|官网|上门|外围)|点com")
    jobs = {
        "velog 全站 RSS": ("https://v2.velog.io/rss", lambda items, in7, span: {
            "items": len(items), "covers_hours": round(span, 2),
            "spam_like": sum(bool(spam.search(i["title"])) for i in items)}),
        "Habr open_source hub": ("https://habr.com/ru/rss/hubs/open_source/articles/", lambda items, in7, span: {
            "items": len(items), "in_7d": len(in7), "covers_hours": round(span),
            "github_in_desc": sum(bool(repo_of(i["desc"])) for i in in7)}),
        "OSChina 资讯 RSS": ("https://www.oschina.net/news/rss", lambda items, in7, span: {
            "items": len(items), "in_7d": len(in7), "covers_hours": round(span),
            "release_posts": sum("发布" in i["title"] for i in in7),
            "github_in_desc": sum(bool(repo_of(i["desc"])) for i in in7),
            "gitee_in_desc": sum("gitee.com/" in i["desc"] for i in in7)}),
    }
    out = {}
    for name, (url, fn) in jobs.items():
        try:
            out[name] = fn(*rss2(url, since))
        except Exception as ex:  # OSChina 偶爾 connection reset
            out[name] = {"error": str(ex)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="hatena,ruanyf,hellogithub,noise")
    ap.add_argument("--ruanyf-issues", type=int, default=3)
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    print(f"# now={now:%Y-%m-%d %H:%M} UTC, window=7d\n")
    only = args.only.split(",")
    if "hatena" in only:
        res, repos = hatena(since)
        print("## Hatena Bookmark：新收藏的 github.com 頁面\n" + json.dumps(res, ensure_ascii=False))
        for rp, r in repos[:: max(1, len(repos) // 5)][:5]:
            print(f"  - {r['date']:%m-%d} users={r['users']} {rp} | {r['title'][:60]}")
        print()
    if "ruanyf" in only:
        for iss in ruanyf(args.ruanyf_issues):
            rows = iss.pop("rows")
            print(f"## 科技爱好者周刊 第 {iss['issue']} 期「工具」\n" + json.dumps(iss, ensure_ascii=False))
            for r in rows[:5]:
                print(f"  - {r['name']} | {r['repo']} | 投稿={r['submitted']} | {r['desc']}")
        print()
    if "hellogithub" in only:
        hg = hellogithub()
        rows = hg.pop("rows")
        print(f"## HelloGitHub 第 {hg['issue']} 期\n" + json.dumps(hg, ensure_ascii=False))
        for r in [x for x in rows if x["section"] in ("人工智能", "Go 项目", "Rust 项目")][:5]:
            print(f"  - [{r['section']}] {r['name']} | {r['repo']} | {r['desc']}")
        print()
    if "noise" in only:
        for k, v in noise(since).items():
            print(f"## {k}\n" + json.dumps(v, ensure_ascii=False))


if __name__ == "__main__":
    main()
