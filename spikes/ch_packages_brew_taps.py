#!/usr/bin/env python3
"""Homebrew 第三方 tap：用官方 analytics 找「最近 30 天才出現」的 formula，再對回 GitHub repo。

想法：formulae.brew.sh 的 install-on-request analytics 也收第三方 tap（名稱是 user/tap/formula）。
一個 formula 的 365 天安裝數 ≈ 30 天安裝數，代表它幾乎是這 30 天才開始有人裝。
tap 依慣例對到 github.com/<user>/homebrew-<tap>，formula 檔裡的 homepage/url 再對到原始 repo。

執行：
    python3 spikes/ch_packages_brew_taps.py                 # 預設：30 天安裝數 10–1000，抽 40 筆
    python3 spikes/ch_packages_brew_taps.py --min 20 --max 500 --sample 60 --seed 7
環境變數（選填）：PICKFIT_CONTACT=<email>，放進 User-Agent，走 ecosyste.ms 的 polite pool。
只用標準函式庫；不需要任何金鑰。
"""
import argparse
import json
import os
import random
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request

ANALYTICS = "https://formulae.brew.sh/api/analytics/install-on-request/{}.json"
RAW = "https://raw.githubusercontent.com/{repo}/HEAD/{path}"
ECO_REPO = "https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{}"
CONTACT = os.environ.get("PICKFIT_CONTACT")
UA = "pickfit-spike/0.1" + (f" (mailto:{CONTACT})" if CONTACT else "")


def get(url, as_json=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    return json.loads(body) if as_json else body.decode("utf-8", "replace")


def counts(window):
    d = get(ANALYTICS.format(window))
    return {i["formula"]: int(i["count"].replace(",", "")) for i in d["items"]}, d


def field(rb, key):
    m = re.search(rf'^\s*{key}\s+"([^"]+)"', rb or "", re.M)
    return m.group(1) if m else None


def gh_repo(*urls):
    for u in urls:
        m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", u or "")
        if m:
            return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=10, help="30 天安裝數下限（排除作者自己測試）")
    ap.add_argument("--max", type=int, default=1000, help="30 天安裝數上限（排除已經紅的）")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    c30, meta = counts("30d")
    c90, _ = counts("90d")
    c365, _ = counts("365d")
    taps = {k: v for k, v in c30.items() if k.count("/") == 2}
    new = {k: v for k, v in taps.items() if c365.get(k, 0) <= v * 1.15 and c90.get(k, 0) <= v * 1.15}
    band = {k: v for k, v in new.items() if args.min <= v <= args.max}
    print(f"analytics 區間 {meta['start_date']} ~ {meta['end_date']}（install-on-request）")
    print(f"30 天內有安裝紀錄的 formula：{len(c30)}；其中第三方 tap：{len(taps)}（{len({k.rsplit('/', 1)[0] for k in taps})} 個 tap）")
    print(f"第三方 tap 中「安裝幾乎都在最近 30 天」：{len(new)}；30 天安裝數 {args.min}–{args.max} 的：{len(band)}")

    names = sorted(band)
    sample = random.Random(args.seed).sample(names, min(args.sample, len(names)))
    rows = []
    for name in sample:
        user, tap, formula = name.split("/")
        tap_repo = f"{user}/homebrew-{tap}"
        rb = None
        for path in (f"Formula/{formula}.rb", f"{formula}.rb", f"HomebrewFormula/{formula}.rb",
                     f"Formula/{formula[0]}/{formula}.rb"):
            rb = get(RAW.format(repo=tap_repo, path=path), as_json=False)
            if rb:
                break
        desc, home, url, lic = (field(rb, k) for k in ("desc", "homepage", "url", "license"))
        src = gh_repo(home, url)
        info = get(ECO_REPO.format(urllib.parse.quote(src, safe=""))) if src else None
        rows.append({
            "name": name, "installs_30d": band[name], "formula_found": bool(rb), "desc": desc,
            "repo": src, "license": lic,
            "prebuilt_binary": bool(url and "/releases/download/" in url) or ("/releases/download/" in (rb or "")),
            "stars": info.get("stargazers_count") if info else None,
            "repo_created": (info.get("created_at") or "")[:10] if info else None,
            "language": info.get("language") if info else None,
        })

    n = len(rows)
    found = sum(r["formula_found"] for r in rows)
    with_repo = sum(bool(r["repo"]) for r in rows)
    binary = sum(r["prebuilt_binary"] for r in rows)
    stars = [r["stars"] for r in rows if r["stars"] is not None]
    recent = sum(1 for r in rows if (r["repo_created"] or "") >= "2026-01-01")
    print(f"\n抽樣 {n} 筆：找到 formula 檔 {found}；對到 GitHub repo {with_repo}；用 release 預編譯檔 {binary}；"
          f"repo 今年建立 {recent}")
    if stars:
        print(f"  星數：中位數 {statistics.median(stars)}，<100 星 {sum(s < 100 for s in stars)}/{len(stars)}，"
              f"最大 {max(stars)}")
    print("\n前 5 筆抽樣：")
    for r in rows[:5]:
        print(f"- {r['name']}（30d 安裝 {r['installs_30d']}）repo={r['repo']} ★{r['stars']} 建立 {r['repo_created']} "
              f"{r['language']} | {r['desc']}")
    if os.environ.get("PICKFIT_JSON"):
        print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
