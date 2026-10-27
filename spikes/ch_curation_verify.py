#!/usr/bin/env python3
"""查核 channels-curation.md 的幾個數字（2026-10-28 查核用）。只用標準函式庫與 git，不需要金鑰。

  python3 spikes/ch_curation_verify.py            # 全部
  python3 spikes/ch_curation_verify.py ollama     # awesome-ollama：依「項目名稱」比對，扣掉只是換連結的舊項目
  python3 spikes/ch_curation_verify.py clickhouse # ClickHouse playground：2025-10 逐日 CreateEvent(repository)
  python3 spikes/ch_curation_verify.py golang     # Golang Weekly RSS：每期 /link/ 轉址數與 title="github.com" 的數量

快取沿用 ch_curation_lists.py 的 $PICKFIT_CACHE。
"""
import json, re, statistics, sys, urllib.request
import xml.etree.ElementTree as ET

from ch_curation_lists import UA, ensure_clone, fetch, git  # 同一資料夾


def entries(d, rev, path="README.md"):
    text = git(d, "show", f"{rev}:{path}")
    return {m.group(1).strip().lower(): m.group(2) for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)}


def ollama(days=90):
    import datetime as dt
    d = ensure_clone("EndoTheDev/awesome-ollama")
    since = dt.date.today() - dt.timedelta(days=days)
    base = git(d, "rev-list", "-1", f"--before={since}", "HEAD").strip()
    old, new = entries(d, base), entries(d, "HEAD")
    added = sorted(set(new) - set(old))
    relinked = sorted(k for k in set(new) & set(old) if new[k].rstrip("/") != old[k].rstrip("/"))
    url_new = {u.rstrip("/") for u in new.values()} - {u.rstrip("/") for u in old.values()}
    print(f"## awesome-ollama（{base[:7]} → HEAD）")
    print(f"- 新 URL {len(url_new)} 個；其中真正新項目（名稱沒出現過）{len(added)} 個；舊項目換連結 {len(relinked)} 個")
    print("- 換連結的舊項目：" + ", ".join(relinked))
    stars, young = [], 0
    cut = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    for k in added:
        m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", new[k])
        if not m:
            continue
        try:
            r = json.loads(fetch(f"https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{m.group(1)}/{m.group(2)}"))
        except Exception:  # noqa: BLE001
            continue
        stars.append(r.get("stargazers_count") or 0)
        young += str(r.get("created_at"))[:10] >= cut
    if stars:
        print(f"- 真正新項目查到 {len(stars)} 筆：星數中位數 {statistics.median(stars):g}、<100 星 {sum(s < 100 for s in stars)}、"
              f"<1,000 星 {sum(s < 1000 for s in stars)}、一年內建立 {young}")


def clickhouse():
    sql = (b"SELECT toDate(created_at) d, count(), countIf(event_type='CreateEvent' AND ref_type='repository') "
           b"FROM github_events WHERE created_at >= '2025-10-05' AND created_at < '2025-10-16' GROUP BY d ORDER BY d FORMAT TSV")
    req = urllib.request.Request("https://play.clickhouse.com/?user=play", data=sql, headers={"User-Agent": UA})
    print("## ClickHouse playground：日期、事件數、CreateEvent(repository)")
    print(urllib.request.urlopen(req, timeout=60).read().decode())


def golang():
    root = ET.fromstring(fetch("https://golangweekly.com/rss/"))
    print("## Golang Weekly RSS：每期 /link/ 轉址數、其中 title=\"github.com\" 的數量（只有網域，沒有 owner/repo）")
    for it in root.iter("item"):
        body = it.findtext("description") or ""
        links = set(re.findall(r"https://golangweekly\.com/link/\d+/rss", body))
        gh = re.findall(r'href="https://golangweekly\.com/link/\d+/rss" title="github\.com"', body)
        print(f"- {it.findtext('pubDate')[:16]}：/link/ {len(links)}、title=github.com {len(gh)}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["ollama", "clickhouse", "golang"]
    for w in which:
        {"ollama": ollama, "clickhouse": clickhouse, "golang": golang}[w]()
        print()
