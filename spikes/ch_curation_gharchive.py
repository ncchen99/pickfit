#!/usr/bin/env python3
"""GH Archive 實測：每小時 dump 還能不能拿來找「剛出現、星數剛開始長」的 repo。

只用 Python 標準函式庫。不需要金鑰。

  python3 spikes/ch_curation_gharchive.py                  # 最近 3 個小時 + 30 天前 1 小時當 ID 錨點
  python3 spikes/ch_curation_gharchive.py --hours 6 --young-days 30
  python3 spikes/ch_curation_gharchive.py --baseline 2024-10-15-15   # 另外下載一個舊小時做對照（約 120 MB）
  python3 spikes/ch_curation_gharchive.py --no-external              # 不查 ClickHouse playground 與 OSS Insight

做法：
1. 下載 data.gharchive.org/YYYY-MM-DD-H.json.gz，統計事件種類。
2. 2025-10 之後 CreateEvent 只剩 branch，沒有 ref_type=repository，所以「新 repo」改用 repo ID 判斷：
   GitHub 的 repo ID 是遞增的。下載 N 天前的一個小時，取其中 ForkEvent 的 forkee.id 最大值當門檻，
   ID 大於門檻的 repo 就是「N 天內建立」的。
3. 算這些年輕 repo 在最近幾小時拿到多少 WatchEvent（加星）與 ReleaseEvent。
檔案快取在 $PICKFIT_CACHE（預設 ~/.cache/pickfit-spikes/gharchive）。
"""
import argparse, collections, datetime as dt, gzip, json, os, sys, urllib.error, urllib.request

CACHE = os.path.join(os.environ.get("PICKFIT_CACHE", os.path.expanduser("~/.cache/pickfit-spikes")), "gharchive")
UA = "pickfit-spike/0.1 (hackathon research)"


def hour_key(t):
    return f"{t:%Y-%m-%d}-{t.hour}"


def download(key):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{key}.json.gz")
    if not os.path.exists(path):
        req = urllib.request.Request(f"https://data.gharchive.org/{key}.json.gz", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r, open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


def latest_hours(n):
    """從現在往回找 n 個已經發布的小時檔（GH Archive 通常延遲 1 小時以上）。"""
    t = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for _ in range(n + 12):
        t -= dt.timedelta(hours=1)
        req = urllib.request.Request(f"https://data.gharchive.org/{hour_key(t)}.json.gz", method="HEAD",
                                     headers={"User-Agent": UA})
        try:
            urllib.request.urlopen(req, timeout=30)
            out.append(hour_key(t))
        except urllib.error.HTTPError:
            continue
        if len(out) == n:
            break
    return out


def events(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def summarize(path):
    types, refs, fork_ids = collections.Counter(), collections.Counter(), []
    for e in events(path):
        types[e["type"]] += 1
        if e["type"] == "CreateEvent":
            refs[e["payload"].get("ref_type")] += 1
        if e["type"] == "ForkEvent" and isinstance(e["payload"].get("forkee"), dict):
            fork_ids.append(e["payload"]["forkee"]["id"])
    return types, refs, fork_ids


def query(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def external_checks():
    print("\n## 其他用 GitHub 事件流算出來的服務（同一天實測）\n")
    try:
        sql = b"SELECT max(created_at), countIf(event_type='WatchEvent' AND created_at >= now() - INTERVAL 30 DAY) FROM github_events FORMAT TSV"
        print("- ClickHouse playground github_events：最新事件、近 30 天 WatchEvent =",
              query("https://play.clickhouse.com/?user=play", sql).strip().replace("\t", "、"))
    except Exception as e:  # noqa: BLE001
        print("- ClickHouse playground：錯誤", e)
    try:
        d = json.loads(query("https://api.ossinsight.io/v1/trends/repos/?period=past_week&language=All"))
        q = d.get("data_quality", {})
        print(f"- OSS Insight trends：rows={d['data']['result'].get('row_count')}、status={q.get('status')}、"
              f"unavailable_since={q.get('unavailable_since')}")
        print(f"  原因（API 原文）：{q.get('reason')}")
    except Exception as e:  # noqa: BLE001
        print("- OSS Insight：錯誤", e)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hours", type=int, default=3, help="分析最近幾個小時（預設 3）")
    p.add_argument("--young-days", type=int, default=30, help="「年輕 repo」的天數（預設 30）")
    p.add_argument("--baseline", help="另外統計一個舊小時做對照，例如 2024-10-15-15")
    p.add_argument("--no-external", action="store_true")
    args = p.parse_args()

    recent = latest_hours(args.hours)
    anchor_t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.young_days)
    anchor_key = hour_key(anchor_t.replace(hour=15))
    keys = recent + [anchor_key] + ([args.baseline] if args.baseline else [])
    print(f"# GH Archive 實測（{dt.date.today()}）\n")
    print("| 小時（UTC） | 檔案 MB | 事件數 | WatchEvent | ReleaseEvent | PushEvent | CreateEvent（repository／branch） | ForkEvent |")
    print("|---|---|---|---|---|---|---|---|")
    stats = {}
    for k in keys:
        path = download(k)
        types, refs, fork_ids = summarize(path)
        stats[k] = fork_ids
        print(f"| {k} | {os.path.getsize(path) / 1e6:.1f} | {sum(types.values()):,} | {types['WatchEvent']:,} | "
              f"{types['ReleaseEvent']:,} | {types['PushEvent']:,} | {refs['repository']:,}／{refs['branch']:,} | "
              f"{types['ForkEvent']:,} |")

    if not stats[anchor_key]:
        print(f"\n{anchor_key} 沒有 ForkEvent，無法定 ID 門檻"); return 1
    threshold = max(stats[anchor_key])
    print(f"\nID 門檻：{anchor_key} 的 forkee.id 最大值 = {threshold:,}（大於它 ≈ {args.young_days} 天內建立）")

    stars, releases, young_any = collections.Counter(), collections.Counter(), set()
    total_watch = 0
    for k in recent:
        for e in events(download(k)):
            rid = e["repo"].get("id") or 0
            if e["type"] == "WatchEvent":
                total_watch += 1
            if rid > threshold:
                young_any.add(e["repo"]["name"])
                if e["type"] == "WatchEvent":
                    stars[e["repo"]["name"]] += 1
                elif e["type"] == "ReleaseEvent":
                    releases[e["repo"]["name"]] += 1
    print(f"\n最近 {len(recent)} 小時：年輕 repo 有任何事件 {len(young_any):,} 個；"
          f"WatchEvent 共 {total_watch:,} 筆，其中落在年輕 repo {sum(stars.values()):,} 筆（{len(stars):,} 個 repo）；"
          f"年輕 repo 的 ReleaseEvent {sum(releases.values()):,} 筆（{len(releases):,} 個 repo）")
    print("\n年輕 repo 依加星事件排序（前 10）：\n")
    for name, n in stars.most_common(10):
        print(f"- {name}：WatchEvent {n}、ReleaseEvent {releases.get(name, 0)}")
    if not args.no_external:
        external_checks()


if __name__ == "__main__":
    sys.exit(main())
