#!/usr/bin/env python3
"""策展管道實測：awesome 清單的新增項目、開發者週報 RSS 的 GitHub 連結。

只用 Python 標準函式庫與 git。不需要金鑰。

  python3 spikes/ch_curation_lists.py awesome [--days 90]   # 每份清單近 N 天新增了哪些連結
  python3 spikes/ch_curation_lists.py feeds   [--days 7]    # 每個 RSS 近 N 天幾筆、幾筆連到 GitHub repo
  awesome 加 --enrich N、feeds 加 --enrich：用 ecosyste.ms 補星數與建立日期
  （匿名 5,000 次／時，資料 CC BY-SA 4.0；GitHub API 在部分雲端環境被擋，所以改用它）

awesome 用 blobless clone（只抓 commit 與需要的兩個版本的檔案），快取在 $PICKFIT_CACHE
（預設 ~/.cache/pickfit-spikes）。比較「N 天前最後一個 commit」與 HEAD 的清單檔，算出新出現的 URL。
"""
import argparse, csv, datetime as dt, email.utils, io, json, os, re, shutil, subprocess, sys
import urllib.request, xml.etree.ElementTree as ET

CACHE = os.environ.get("PICKFIT_CACHE", os.path.expanduser("~/.cache/pickfit-spikes"))
UA = "pickfit-spike/0.1 (hackathon research)"

# (repo, 清單檔路徑；以 / 結尾代表「一個檔案一筆」的資料夾, 類別)
LISTS = [
    ("agarrharr/awesome-cli-apps", "readme.md", "cli"),
    ("alebcay/awesome-shell", "README.md", "cli"),
    ("k4m4/terminals-are-sexy", "readme.md", "cli"),
    ("rothgar/awesome-tuis", "README.md", "cli"),
    ("toolleeo/awesome-cli-apps-in-a-csv", "data/apps.csv", "cli"),
    ("sindresorhus/awesome", "readme.md", "meta"),
    ("awesome-selfhosted/awesome-selfhosted-data", "software/", "selfhosted"),
    ("rafska/awesome-local-llm", "README.md", "local-ai"),
    ("vince-lam/awesome-local-llms", "README.md", "local-ai"),
    ("EndoTheDev/awesome-ollama", "README.md", "local-ai"),
    ("janhq/awesome-local-ai", "README.md", "local-ai"),
    ("Shubhamsaboo/awesome-llm-apps", "README.md", "local-ai"),
    ("ollama/ollama", "README.md", "local-ai"),  # 只算 README 的 Community Integrations 段
]
SECTION = {"ollama/ollama": "## Community Integrations"}

FEEDS = [
    ("console-tools", "https://console.dev/tools/rss.xml"),
    ("console-betas", "https://console.dev/betas/rss.xml"),
    ("console-reviews", "https://console.dev/reviews/feed.xml"),
    ("changelog-news", "https://changelog.com/news/feed"),
    ("tldr-dev", "https://tldr.tech/api/rss/dev"),
    ("tldr-ai", "https://tldr.tech/api/rss/ai"),
    ("this-week-in-rust", "https://this-week-in-rust.org/atom.xml"),
    ("golang-weekly", "https://golangweekly.com/rss/"),
    ("hellogithub", "https://hellogithub.com/rss"),
    ("terminaltrove-blog", "https://terminaltrove.com/blog.xml"),
    ("python-weekly", "https://www.pythonweekly.com/feed"),
]

URL_RE = re.compile(r"https?://[^\s)\]>\"'<,|]+")
GH_RE = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
# 週報自己的 repo（例如 This Week in Rust 每期都連 rust-lang/*）不算發現訊號
SKIP_OWNERS = {"rust-lang", "thechangelog", "521xueweihan", "hellogithub-team"}
GH_NOT_OWNER = {"sponsors", "orgs", "features", "topics", "collections", "marketplace", "settings",
                "apps", "login", "about", "pricing", "site", "trending", "readme", "enterprise", "users"}


def gh_repo(url):
    m = GH_RE.match(url)
    if not m or m.group(1).lower() in GH_NOT_OWNER:
        return None
    name = re.sub(r"(\.git|#.*|\?.*)$", "", m.group(2))
    return f"{m.group(1)}/{name}".lower() if name else None


def git(repo_dir, *args):
    return subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True).stdout


def ensure_clone(repo):
    d = os.path.join(CACHE, repo.replace("/", "__"))
    if os.path.isdir(d):
        subprocess.run(["git", "-C", d, "fetch", "-q", "origin"], capture_output=True)
        subprocess.run(["git", "-C", d, "update-ref", "HEAD", "FETCH_HEAD"], capture_output=True)
    else:
        os.makedirs(CACHE, exist_ok=True)
        since = (dt.date.today() - dt.timedelta(days=400)).isoformat()
        base = ["git", "clone", "-q", "--filter=blob:none", "--no-checkout"]
        url = f"https://github.com/{repo}"
        # 一年多沒動的 repo，--shallow-since 會失敗；改抓最後一個 commit 就好
        if subprocess.run(base + [f"--shallow-since={since}", url, d], capture_output=True).returncode:
            shutil.rmtree(d, ignore_errors=True)
            subprocess.run(base + ["--depth=1", url, d], check=True)
    return d


def license_of(d, path):
    files = git(d, "ls-tree", "--name-only", "HEAD").split()
    lic = next((f for f in files if re.match(r"(?i)^(licen[cs]e|copying)", f)), None)
    if lic:
        head = git(d, "show", f"HEAD:{lic}")[:200]
        for key in ("CC0", "Attribution-ShareAlike", "MIT License", "Apache License"):
            if key.lower() in head.lower():
                return {"CC0": "CC0", "Attribution-ShareAlike": "CC BY-SA", "MIT License": "MIT",
                        "Apache License": "Apache-2.0"}[key] + f" ({lic})"
        return f"? ({lic})"
    if not path.endswith("/"):
        body = git(d, "show", f"HEAD:{path}")
        m = re.search(r"(?ims)^#+\s*licen[cs]e\s*$.{0,400}", body)
        if m and "publicdomain/zero" in m.group(0):
            return "CC0 (README 段落)"
    return "無"


def urls_in(text, path, section=None):
    if section and section in text:
        text = text.split(section, 1)[1]
    if path.endswith(".csv"):
        return {row.get("git") or row.get("homepage") for row in csv.DictReader(io.StringIO(text))} - {None, ""}
    return {u.rstrip(".") for u in URL_RE.findall(text)}


def cmd_awesome(args):
    today = dt.date.today()
    since = today - dt.timedelta(days=args.days)
    print(f"# awesome 清單：{since} 之後新增的連結（查證 {today}）\n")
    print("| 清單 | 授權 | 最後 commit | commits 30/90/365 天 | 現有項目 | 近 {0} 天新增 | 其中 GitHub repo |".format(args.days))
    print("|---|---|---|---|---|---|---|")
    samples = {}
    for repo, path, cat in LISTS:
        try:
            d = ensure_clone(repo)
        except subprocess.CalledProcessError:
            print(f"| {repo} | clone 失敗 | | | | | |"); continue
        last = git(d, "log", "-1", "--format=%cd", "--date=short").strip()  # committer date，與 rev-list --since 一致
        counts = [git(d, "rev-list", "--count", f"--since={today - dt.timedelta(days=n)}", "HEAD").strip()
                  for n in (30, 90, 365)]
        base = git(d, "rev-list", "-1", f"--before={since}", "HEAD").strip()
        lic = license_of(d, path)
        if path.endswith("/"):
            now = [f for f in git(d, "ls-tree", "--name-only", f"HEAD:{path}").split()]
            added = sorted(set(l for l in git(d, "log", f"--since={since}", "--diff-filter=A",
                                              "--format=", "--name-only", "--", path).split() if l.startswith(path)))
            new = []
            for f in added[:max(5, args.enrich)]:
                m = re.search(r"source_code_url:\s*(\S+)", git(d, "show", f"HEAD:{f}"))
                new.append(m.group(1) if m else f)
            n_now, n_new = len(now), len(added)
            n_gh = sum(1 for u in new if gh_repo(u))
            gh_note = f"{n_gh}/{len(new)}（抽樣）"
        else:
            sec = SECTION.get(repo)
            cur = urls_in(git(d, "show", f"HEAD:{path}"), path, sec)
            old = urls_in(git(d, "show", f"{base}:{path}"), path, sec) if base else set()
            new = sorted(cur - old) if base else []
            # 沒有 since 之前的 commit：要嘛整份清單都在期間內出現，要嘛最後 commit 早於 since（新增 0）
            n_now = len(cur)
            n_new = len(new) if base else (0 if last < since.isoformat() else "（歷史不足）")
            n_gh = sum(1 for u in new if gh_repo(u))
            gh_note = str(n_gh)
        samples[repo] = new
        print(f"| {repo} | {lic} | {last} | {'/'.join(counts)} | {n_now} | {n_new} | {gh_note} |")
    print("\n## 抽樣：每份清單近期新增的前 5 筆\n")
    for repo, new in samples.items():
        if new:
            print(f"- {repo}: " + ", ".join(new[:5]))
    if args.enrich:
        print(f"\n## 近期新增的 GitHub repo 有多「新」、多「沒人知道」（每份清單最多查 {args.enrich} 筆，ecosyste.ms）\n")
        print("| 清單 | 查到 | 星數中位數 | 一年內建立 | <100 星 | <1,000 星 |")
        print("|---|---|---|---|---|---|")
        for repo, new in samples.items():
            rs = [r for r in dict.fromkeys(gh_repo(u) for u in new) if r][:args.enrich]
            meta = [m for m in (repo_meta(r) for r in rs) if m]
            if not meta:
                continue
            stars = sorted(m["stars"] for m in meta)
            year_ago = (dt.date.today() - dt.timedelta(days=365)).isoformat()
            pct = lambda n: f"{n}/{len(meta)}"
            print(f"| {repo} | {len(meta)} | {stars[len(stars) // 2]} | {pct(sum(m['created'] >= year_ago for m in meta))}"
                  f" | {pct(sum(x < 100 for x in stars))} | {pct(sum(x < 1000 for x in stars))} |")


def repo_meta(r):
    try:
        d = json.loads(fetch(f"https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{r}"))
    except Exception:  # noqa: BLE001
        return None
    return {"stars": d.get("stargazers_count") or 0, "created": str(d.get("created_at"))[:10],
            "pushed": str(d.get("pushed_at"))[:10]}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def feed_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        f = {c.tag.split("}")[-1]: c for c in el}
        dnode = next((f[k] for k in ("pubDate", "published", "updated") if k in f), None)
        date = parse_date(dnode.text if dnode is not None else None)
        link = (f["link"].get("href") or f["link"].text or "") if "link" in f else ""
        body = " ".join((c.text or "") for k, c in f.items() if k in ("description", "encoded", "content", "summary"))
        out.append({"title": (f["title"].text or "").strip() if "title" in f else "", "date": date,
                    "link": link.strip(), "body": body})
    return out


def cmd_feeds(args):
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=args.days)
    print(f"# 週報 RSS：近 {args.days} 天（{since.date()} 之後，查證 {now.date()}）\n")
    print("| 管道 | HTTP | 全部 item | 最新一筆 | 近 N 天 item | 外連（去重） | GitHub repo（去重，排除週報自己的 org） |")
    print("|---|---|---|---|---|---|---|")
    samples = {}
    for name, url in FEEDS:
        try:
            items = feed_items(fetch(url))
        except Exception as e:  # noqa: BLE001  實測腳本：把錯誤印出來就好
            why = "不是 RSS／Atom（回 HTML）" if isinstance(e, ET.ParseError) else f"{type(e).__name__} {getattr(e, 'code', '')}"
            print(f"| {name} | 錯誤：{why} | | | | | |"); continue
        dated = [i for i in items if i["date"]]
        latest = max((i["date"] for i in dated), default=None)
        recent = [i for i in dated if i["date"] >= since]
        repos, links = {}, set()
        for i in recent:
            for u in URL_RE.findall(i["link"] + " " + i["body"]):
                links.add(u)
                r = gh_repo(u)
                if r and r.split("/")[0] not in SKIP_OWNERS:
                    repos.setdefault(r, i["title"])
        samples[name] = list(repos.items())
        print(f"| {name} | 200 | {len(items)} | {latest.date() if latest else '?'} | {len(recent)} | {len(links)} | {len(repos)} |")
    print("\n## 抽樣：每個管道前 5 個 GitHub repo（括號是所在的 item 標題）\n")
    for name, rs in samples.items():
        if rs:
            print(f"- {name}: " + "; ".join(f"{r}（{t[:40]}）" for r, t in rs[:5]))
    if args.enrich:
        enrich([r for rs in samples.values() for r, _ in rs[:5]])


def enrich(repos):
    """用 ecosyste.ms 查星數與建立日期（GitHub API 在部分雲端環境被擋，這裡改用它）。"""
    print("\n## ecosyste.ms 補資料（星數、建立日期）\n")
    print("| repo | 星數 | 建立 | 最後 push |")
    print("|---|---|---|---|")
    young = 0
    for r in dict.fromkeys(repos):
        try:
            d = json.loads(fetch(f"https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{r}"))
        except Exception:  # noqa: BLE001
            print(f"| {r} | ? | ? | ? |"); continue
        created = str(d.get("created_at"))[:10]
        young += created >= (dt.date.today() - dt.timedelta(days=365)).isoformat() and (d.get("stargazers_count") or 0) < 1000
        print(f"| {r} | {d.get('stargazers_count')} | {created} | {str(d.get('pushed_at'))[:10]} |")
    print(f"\n一年內建立且 <1,000 星：{young} 筆")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("awesome"); a.add_argument("--days", type=int, default=90)
    a.add_argument("--enrich", type=int, default=0, metavar="N", help="每份清單用 ecosyste.ms 查 N 筆新增 repo 的星數")
    f = sub.add_parser("feeds"); f.add_argument("--days", type=int, default=7); f.add_argument("--enrich", action="store_true")
    args = p.parse_args()
    {"awesome": cmd_awesome, "feeds": cmd_feeds}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
