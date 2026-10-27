#!/usr/bin/env python3
"""套件生態系的「新作品」數量與「是不是可執行軟體」訊號，各打一次官方 API。

每個生態系輸出：時間窗內新套件數、連到 GitHub 的比例、抽樣中可執行（CLI）的比例、前 5 筆抽樣。
- PyPI ：數量用 ecosyste.ms（created_after）；可執行 = wheel 的 entry_points.txt 有 console_scripts（HTTP Range 只讀 zip 目錄）
- npm  ：數量用 ecosyste.ms；可執行 = packument 最新版的 bin 欄位
- crates：數量用 ecosyste.ms；可執行 = crates.io 版本的 bin_names（遵守 1 req/s）
- Go   ：index.golang.org 最近 N 小時；可執行 = pkg.go.dev v1 API 的 packages filter name == "main"
- AUR  ：packages-meta-v1.json.gz 的 FirstSubmitted

執行：
    python3 spikes/ch_packages_registries.py                    # 全部，預設 7 天、每個生態系抽 30 筆
    python3 spikes/ch_packages_registries.py --only pypi,crates --sample 20 --days 3
環境變數（選填）：PICKFIT_CONTACT=<email>，放進 User-Agent（crates.io 要求可聯絡、ecosyste.ms polite pool）。
只用標準函式庫；不需要任何金鑰。
"""
import argparse
import datetime as dt
import gzip
import io
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

CONTACT = os.environ.get("PICKFIT_CONTACT")
UA = "pickfit-spike/0.1" + (f" (mailto:{CONTACT})" if CONTACT else " (+https://github.com/ncchen99/pickfit)")
NOW = dt.datetime.now(dt.timezone.utc)


def get(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    return body if raw else json.loads(body)


def gh(url):
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+)", url or "")
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}" if m else None


def eco_new(registry, days, max_pages):
    """ecosyste.ms 在時間窗內新收錄的套件（created_at 是 ecosyste.ms 收錄時間）。"""
    since = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, capped = [], False
    for page in range(1, max_pages + 1):
        q = urllib.parse.urlencode({"created_after": since, "per_page": 1000, "page": page,
                                    "sort": "created_at", "order": "desc"})
        batch = get(f"https://packages.ecosyste.ms/api/v1/registries/{registry}/packages?{q}") or []
        out += batch
        if len(batch) < 1000:
            break
    else:
        capped = True
    return out, capped


class RangeFile(io.RawIOBase):
    """讓 zipfile 只用 HTTP Range 讀 wheel 的中央目錄與單一檔案，不下載整個 wheel。"""

    def __init__(self, url, size):
        self.url, self.size, self.pos = url, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size or len(b) == 0:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        data = get(self.url, {"Range": f"bytes={self.pos}-{end}"}, raw=True) or b""
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def pypi_exec(name):
    d = get(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if not d:
        return None, None
    urls = list((d["info"].get("project_urls") or {}).values()) + [d["info"].get("home_page") or ""]
    repo = next((gh(u) for u in urls if gh(u)), None)
    wheels = [u for u in d.get("urls", []) if u["packagetype"] == "bdist_wheel"]
    if not wheels:
        return repo, None  # 只有 sdist：要解 pyproject.toml 才知道
    w = wheels[0]
    try:
        zf = zipfile.ZipFile(io.BufferedReader(RangeFile(w["url"], w["size"]), 65536))
        ep = next((n for n in zf.namelist() if n.endswith(".dist-info/entry_points.txt")), None)
        text = zf.read(ep).decode() if ep else ""
    except (zipfile.BadZipFile, OSError):
        return repo, None
    return repo, bool(re.search(r"^\[(console_scripts|gui_scripts)\]\s*\n\s*\S", text, re.M))


def npm_exec(name):
    d = get(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}",
            {"Accept": "application/vnd.npm.install-v1+json"})
    if not d or "dist-tags" not in d:
        return None
    v = d["versions"].get(d["dist-tags"].get("latest"), {})
    return bool(v.get("bin"))


def crates_exec(name):
    time.sleep(1.05)  # crates.io 資料存取政策：最多 1 req/s
    d = get(f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}")
    if not d:
        return None
    ver = d["crate"].get("default_version") or d["crate"].get("max_version")
    time.sleep(1.05)
    v = get(f"https://crates.io/api/v1/crates/{urllib.parse.quote(name)}/{ver}")
    return bool(v and v["version"].get("bin_names"))


def report(label, window, items, repo_of, exec_of, desc_of, sample, seed, note=""):
    n = len(items)
    with_gh = sum(1 for p in items if gh(repo_of(p)))
    print(f"\n## {label}（{window}）{note}")
    print(f"新套件 {n}；repo 連到 GitHub {with_gh}（{with_gh / max(n, 1):.0%}）")
    if not exec_of or not items:
        return
    picks = random.Random(seed).sample(items, min(sample, n))
    res = [(p, exec_of(p)) for p in picks]
    known = [r for _, r in res if r is not None]
    print(f"抽樣 {len(res)} 筆：可判斷 {len(known)}，其中可執行（CLI）{sum(known)}")
    for p, r in res[:5]:
        print(f"- {desc_of(p)} | exec={r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--go-hours", type=float, default=6, help="Go index 量大，預設只看最近 6 小時")
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-pages", type=int, default=60, help="ecosyste.ms 每頁 1000 筆的頁數上限")
    ap.add_argument("--only", default="pypi,npm,crates,go,aur")
    a = ap.parse_args()
    only = set(a.only.split(","))
    win = f"最近 {a.days:g} 天"
    eco_desc = lambda p: f"{p['name']} {gh(p.get('repository_url'))} — {(p.get('description') or '')[:70]}"

    if "pypi" in only:
        items, capped = eco_new("pypi.org", a.days, a.max_pages)
        report("PyPI", win, items, lambda p: p.get("repository_url"), lambda p: pypi_exec(p["name"])[1],
               eco_desc, a.sample, a.seed,
               "（數量來源 ecosyste.ms" + ("，已達頁數上限" if capped else "") + "）")
        rss = get("https://pypi.org/rss/packages.xml", raw=True).decode()
        dates = re.findall(r"<pubDate>([^<]+)</pubDate>", rss)
        if dates:
            span = (dt.datetime.strptime(dates[0], "%a, %d %b %Y %H:%M:%S %Z")
                    - dt.datetime.strptime(dates[-1], "%a, %d %b %Y %H:%M:%S %Z")).total_seconds() / 60
            print(f"對照：PyPI 官方 RSS packages.xml 有 {len(dates)} 筆，只涵蓋最近 {span:.0f} 分鐘")

    if "npm" in only:
        items, capped = eco_new("npmjs.org", a.days, a.max_pages)
        hrs = (NOW - dt.datetime.fromisoformat(items[-1]["created_at"].replace("Z", "+00:00"))).total_seconds() / 3600 if items else 0
        note = f"（數量來源 ecosyste.ms；涵蓋 {hrs:.0f} 小時" + ("，已達頁數上限" if capped else "") + "）"
        report("npm", win, items, lambda p: p.get("repository_url"), lambda p: npm_exec(p["name"]), eco_desc,
               a.sample, a.seed, note)

    if "crates" in only:
        items, capped = eco_new("crates.io", a.days, a.max_pages)
        report("crates.io", win, items, lambda p: p.get("repository_url"), lambda p: crates_exec(p["name"]),
               eco_desc, a.sample, a.seed, "（數量來源 ecosyste.ms" + ("，已達頁數上限" if capped else "") + "）")

    if "go" in only:
        since = NOW - dt.timedelta(hours=a.go_hours)
        cur, rows = since.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), []
        while True:
            body = get(f"https://index.golang.org/index?since={cur}&limit=2000", raw=True).decode()
            batch = [json.loads(line) for line in body.splitlines() if line.strip()]
            rows += batch
            if len(batch) < 2000:
                break
            cur = batch[-1]["Timestamp"]
        tagged = {}
        for r in rows:  # 只留正式 tag（排除 v0.0.0-2026... 這類 pseudo-version）
            if not re.search(r"-\d{14}-[0-9a-f]{12}$", r["Version"]):
                tagged.setdefault(r["Path"], r["Version"])
        print(f"\n## Go（index.golang.org 最近 {a.go_hours:g} 小時）")
        print(f"版本事件 {len(rows)}；不同 module {len({r['Path'] for r in rows})}；"
              f"有正式 tag 的 module {len(tagged)}（github.com 開頭 {sum(p.startswith('github.com/') for p in tagged)}）")
        mods = sorted(tagged)
        picks = random.Random(a.seed).sample(mods, min(a.sample, len(mods)))
        res = []
        for m in picks:
            q = urllib.parse.urlencode({"filter": 'name == "main"'})
            d = get(f"https://pkg.go.dev/v1/packages/{m}?{q}")
            res.append((m, None if d is None else d.get("packages", {}).get("total", 0) > 0))
        known = [r for _, r in res if r is not None]
        print(f"抽樣 {len(res)} 個 module：pkg.go.dev 查得到 {len(known)}，其中含 main package {sum(known)}")
        for m, r in res[:5]:
            print(f"- {m}@{tagged[m]} | main={r}")

    if "aur" in only:
        d = json.load(gzip.open(io.BytesIO(get("https://aur.archlinux.org/packages-meta-v1.json.gz", raw=True))))
        cut = (NOW - dt.timedelta(days=a.days)).timestamp()
        items = [p for p in d if p["FirstSubmitted"] >= cut]
        report("AUR", win, items, lambda p: p.get("URL"), None, None, a.sample, a.seed,
               f"（packages-meta-v1 全部 {len(d)} 筆）")
        kind = lambda p: "-bin" if p["Name"].endswith("-bin") else "-git" if p["Name"].endswith("-git") else "其他"
        print("名稱後綴：", {k: sum(1 for p in items if kind(p) == k) for k in ("-bin", "-git", "其他")})
        for p in random.Random(a.seed).sample(items, min(5, len(items))):
            print(f"- {p['Name']} votes={p['NumVotes']} {gh(p.get('URL'))} — {(p.get('Description') or '')[:70]}")


if __name__ == "__main__":
    main()
