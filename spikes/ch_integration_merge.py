#!/usr/bin/env python3
"""多管道 → 統一候選格式 → 去重合併 → 規則初篩（pickfit 調研 spike，不是產品程式碼）。

示範的事：
1. 增量抓取：Show HN（Algolia，cursor = 已看過的最大 created_at_i）、PyPI RSS（ETag）。
   狀態檔記 cursor／ETag，重跑只抓新的。
2. 正規化：每個網址走 ch_integration_normalize.canon()；短網址實際展開。
3. 合併：以 canonical key 合併成一筆候選，每個來源留出處與時間（sources[]）。
4. 補資料：ecosyste.ms repos（fork／archived／template／README／license）與
   packages lookup（這個 repo 在哪些套件庫有套件）→ 跨管道合併的實例。
5. 規則初篩：算每條規則刷掉多少。

用法：
  python3 spikes/ch_integration_merge.py                  # 最近 7 天 Show HN＋PyPI RSS
  python3 spikes/ch_integration_merge.py --days 3 --enrich 60
  python3 spikes/ch_integration_merge.py --reset          # 清掉狀態檔，從頭抓
輸出：候選 JSONL 寫到 --out（預設系統暫存目錄），不寫進 repo。
環境變數（選填）：PICKFIT_CONTACT（放進 User-Agent；ecosyste.ms 進 polite pool）。
只用 Python 標準函式庫；不含任何金鑰。
"""
import argparse
import collections
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ch_integration_normalize import canon, expand_short, extract_urls, http, jget, pypi_map  # noqa: E402

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
ECO_REPO = "https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/"
ECO_PKG = "https://packages.ecosyste.ms/api/v1/packages/lookup?repository_url="
NOW = datetime.now(timezone.utc)
TMP = tempfile.gettempdir()

# 規則初篩：只看 metadata，不讀 README 內文。名稱規則只當「疑似」，正式版交給模型。
NAME_SUSPECT = re.compile(r"(homework|assignment|coursework|tutorial|bootcamp|boilerplate|starter|"
                          r"template|dotfiles|awesome-|hello-?world|playground|example|demo|test)", re.I)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def load_state(path, reset):
    if reset or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def fetch_show_hn(since_ts, until_ts):
    """依天切片（Algolia 單次最多 1,000 筆），回傳 hits。"""
    hits, a = [], since_ts
    while a < until_ts:
        b = min(a + 86400, until_ts)
        q = urllib.parse.urlencode({"tags": "show_hn", "hitsPerPage": 1000,
                                    "numericFilters": f"created_at_i>{a},created_at_i<={b}"})
        d = jget(f"{ALGOLIA}?{q}") or {}
        hits += d.get("hits", [])
        if d.get("nbHits", 0) > 1000:
            print(f"  警告：{iso(a)} 這天超過 1,000 筆，要再切細", file=sys.stderr)
        a = b
    return hits


def hn_sources(hit):
    """一則 Show HN → 多個 (網址, 角色)。"""
    out = []
    if hit.get("url"):
        out.append((hit["url"], "story_url"))
    text = html.unescape(re.sub(r"<[^>]+>", " ", hit.get("story_text") or ""))
    for u in extract_urls(text):
        out.append((u, "story_text"))
    return out


def eco_repo(key):
    _, owner, repo = key.split("/", 2)
    d = jget(ECO_REPO + urllib.parse.quote(f"{owner}/{repo}", safe=""))
    if not d:
        return None
    files = (d.get("metadata") or {}).get("files") or {}
    return {"full_name": d.get("full_name"), "repo_id": d.get("uuid"), "fork": d.get("fork"),
            "archived": d.get("archived"), "template": d.get("template"), "readme": files.get("readme"),
            "license": d.get("license"), "stars": d.get("stargazers_count"), "topics": d.get("topics") or [],
            "created_at": d.get("created_at"), "pushed_at": d.get("pushed_at"),
            "description": d.get("description"), "previous_names": d.get("previous_names") or []}


def eco_packages(url):
    d = jget(ECO_PKG + urllib.parse.quote(url, safe=""))
    if not isinstance(d, list):
        return []
    keep = []
    for p in d:
        if p.get("ecosystem") in ("pypi", "npm", "cargo", "go", "homebrew", "rubygems", "nuget"):
            keep.append({"ecosystem": p["ecosystem"], "name": p["name"], "purl": p.get("purl"),
                         "downloads": p.get("downloads"), "first_release": p.get("first_release_published_at")})
    return keep


def new_candidate(c):
    return {"schema": "pickfit.candidate/v0", "candidate_id": c["key"], "kind": c["kind"],
            "canonical_url": c["url"], "aliases": [], "subpaths": [], "status": "discovered",
            "first_seen_at": None, "last_seen_at": None, "sources": [], "repo": None,
            "packages": [], "triage": None, "history": []}


def add_source(cands, c, src):
    cand = cands.setdefault(c["key"], new_candidate(c))
    if any(s["channel"] == src["channel"] and s["ref"] == src["ref"] for s in cand["sources"]):
        return cand   # 同一來源同一則（例如貼文網址與內文都指向同一個 repo）只記一次
    cand["sources"].append(src)
    t = src["seen_at"]
    cand["first_seen_at"] = min(filter(None, [cand["first_seen_at"], t]))
    cand["last_seen_at"] = max(filter(None, [cand["last_seen_at"], t]))
    if src["url"] not in cand["aliases"] and src["url"] != cand["canonical_url"]:
        cand["aliases"].append(src["url"])
    if c.get("subpath") and c["subpath"] not in cand["subpaths"]:
        cand["subpaths"].append(c["subpath"])
    return cand


def triage(cand):
    """規則初篩。回傳 (結果, 原因清單)。結果：pass / drop / suspect / unknown。"""
    r = cand["repo"]
    if cand["kind"] != "repo":
        return "unknown", ["非 repo（官網或其他）：要先找 repo 或直接交模型"]
    if not r:
        return "unknown", ["ecosyste.ms 查無（新 repo 常見）：正式版改用 GitHub API"]
    reasons = []
    if r["fork"]:
        reasons.append("fork")
    if r["archived"]:
        reasons.append("archived")
    if r["template"]:
        reasons.append("template_repo")
    if not r["readme"]:
        reasons.append("no_readme")
    if reasons:
        return "drop", reasons
    soft = []
    if not r["license"]:
        soft.append("no_license")
    text = " ".join([r["full_name"] or "", r["description"] or ""] + r["topics"])
    if NAME_SUSPECT.search(text):
        soft.append("name_suspect:" + NAME_SUSPECT.search(text).group(0).lower())
    return ("suspect" if soft else "pass"), soft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--enrich", type=int, default=1000, help="最多補幾個 GitHub repo 的 ecosyste.ms 資料")
    ap.add_argument("--state", default=os.path.join(TMP, "pickfit_ch_integration_state.json"))
    ap.add_argument("--out", default=os.path.join(TMP, "pickfit_ch_integration_candidates.jsonl"))
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    state = load_state(args.state, args.reset)
    cands = {}
    if not args.reset and os.path.exists(args.out):   # 增量：讀回上次的候選庫再合併
        with open(args.out) as f:
            for line in f:
                c = json.loads(line)
                cands[c["candidate_id"]] = c
    n_before = len(cands)
    t0 = time.time()

    # ---- 1. Show HN 增量
    until = int(NOW.timestamp())
    since = state.get("hn_cursor") or until - args.days * 86400
    hits = fetch_show_hn(since, until)
    print(f"[Show HN] cursor {iso(since)} → {iso(until)}：{len(hits)} 則（{'增量' if state.get('hn_cursor') else '首次'}）")
    if hits:
        state["hn_cursor"] = max(h["created_at_i"] for h in hits)
    kinds = collections.Counter()
    rules = collections.Counter()
    shorts = []
    no_url = 0
    for h in hits:
        srcs = hn_sources(h)
        if not srcs:
            no_url += 1
        for u, role in srcs:
            c = canon(u)
            if c["kind"] == "short":
                hops = expand_short(c["url"])
                shorts.append(hops)
                c = canon(hops[-1])
                c["rules"] = c["rules"] + ["expanded_short"]
            if c["kind"] in ("invalid", "forge_user"):
                kinds[c["kind"]] += 1
                continue
            kinds[c["kind"]] += 1
            for r_ in c["rules"]:
                rules[r_.split(":")[0]] += 1
            add_source(cands, c, {
                "channel": "hn_show", "ref": f"hn:{h['objectID']}", "role": role, "url": u,
                "seen_at": iso(h["created_at_i"]), "fetched_at": NOW.isoformat(timespec="seconds"),
                "signals": {"points": h.get("points"), "num_comments": h.get("num_comments"),
                            "title": h.get("title")}})

    # ---- 2. PyPI RSS（ETag）
    st, hd, body = http("https://pypi.org/rss/packages.xml",
                        {"If-None-Match": state["pypi_etag"]} if state.get("pypi_etag") else None)
    print(f"[PyPI RSS] HTTP {st}{'（304：沒變，不必解析）' if st == 304 else ''}，etag={hd.get('etag')}")
    pypi_n = 0
    if st == 200:
        state["pypi_etag"] = hd.get("etag")
        for it in ET.fromstring(body).findall("./channel/item"):
            m = re.search(r"/project/([^/]+)/", it.findtext("link") or "")
            if not m:
                continue
            pypi_n += 1
            row = pypi_map(m[1])
            key = row.get("provenance") or row.get("declared")
            if not key:
                continue
            c = canon("https://" + key)
            pub = it.findtext("pubDate")
            seen = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(timespec="seconds") if pub else None
            add_source(cands, c, {
                "channel": "pypi_new", "ref": f"pkg:pypi/{m[1]}", "role": "package", "url": f"https://pypi.org/project/{m[1]}/",
                "seen_at": seen, "fetched_at": NOW.isoformat(timespec="seconds"),
                "signals": {"repo_via": "provenance" if row.get("provenance") else row.get("via")}})

    # ---- 3. 補資料（ecosyste.ms）＋跨管道
    gh = [k for k, v in cands.items() if v["kind"] == "repo" and k.startswith("github.com/")
          and not v.get("enriched_at")][: args.enrich]
    with ThreadPoolExecutor(6) as ex:
        repos = dict(zip(gh, ex.map(eco_repo, gh)))
        pkgs = dict(zip(gh, ex.map(lambda k: eco_packages(cands[k]["canonical_url"]), gh)))
    for k in gh:
        cands[k]["repo"] = repos[k]
        cands[k]["packages"] = pkgs[k]
        cands[k]["enriched_at"] = NOW.isoformat(timespec="seconds")
        if repos[k] and repos[k]["full_name"] and repos[k]["full_name"].lower() != k.split("/", 1)[1]:
            cands[k]["aliases"].append("github.com/" + repos[k]["full_name"])

    # ---- 4. 規則初篩＋狀態機
    tri = collections.Counter()
    reasons = collections.Counter()
    for cand in cands.values():
        res, why = triage(cand)
        cand["triage"] = {"result": res, "reasons": why, "by": "rules-v0", "at": NOW.isoformat(timespec="seconds")}
        if not cand["history"]:
            cand["history"].append({"status": "discovered", "at": cand["first_seen_at"]})
        new = {"pass": "triaged", "suspect": "triaged", "drop": "rejected"}.get(res, "discovered")
        if new != cand["status"]:   # 狀態有變才記一筆
            cand["status"] = new
            cand["history"].append({"status": new, "at": NOW.isoformat(timespec="seconds"), "why": why or None})
        tri[res] += 1
        for w in why:
            reasons[w.split(":")[0]] += 1

    # ---- 5. 輸出
    with open(args.out, "w") as f:
        for cand in cands.values():
            f.write(json.dumps(cand, ensure_ascii=False) + "\n")
    with open(args.state, "w") as f:
        json.dump(state, f)

    repo_c = [c for c in cands.values() if c["kind"] == "repo"]
    gh_c = [c for c in repo_c if c["candidate_id"].startswith("github.com/")]
    multi_post = [c for c in cands.values() if len({s["ref"] for s in c["sources"] if s["channel"] == "hn_show"}) > 1]
    cross = [c for c in cands.values() if len({s["channel"] for s in c["sources"]}) > 1]
    with_pkg = [c for c in gh_c if c["packages"]]
    eco_tried = [c for c in gh_c if c.get("enriched_at")]
    eco_hit = sum(1 for c in eco_tried if c["repo"])
    print(f"\n== 結果（{time.time() - t0:.0f} 秒） ==")
    print(f"候選庫：上次 {n_before} 筆 → 這次 {len(cands)} 筆（新增 {len(cands) - n_before}）；本次補資料 {len(gh)} 個 repo")
    print(f"Show HN 貼文 {len(hits)}；沒有任何網址 {no_url}")
    print(f"網址種類（去重前）：{dict(kinds)}")
    print(f"觸發的正規化規則：{dict(rules.most_common(12))}")
    print(f"短網址 {len(shorts)}：{[' → '.join(h) for h in shorts[:5]]}")
    print(f"PyPI 新專案 {pypi_n}")
    print(f"合併後候選 {len(cands)}：repo {len(repo_c)}（GitHub {len(gh_c)}）、其他 {len(cands) - len(repo_c)}")
    print(f"同一個 repo 被多則 Show HN 貼文提到：{len(multi_post)}")
    print(f"跨管道（Show HN × PyPI RSS）合併：{len(cross)}")
    print(f"ecosyste.ms 查得到：{eco_hit}／{len(eco_tried)}；在套件庫有套件：{len(with_pkg)}／{len(eco_tried)}"
          f"（{collections.Counter(p['ecosystem'] for c in with_pkg for p in c['packages'])}）")
    print(f"規則初篩：{dict(tri)}；原因：{dict(reasons.most_common())}")
    print(f"候選 JSONL：{args.out}")
    print(f"狀態檔：{args.state}")

    print("\n== 抽樣 5 筆（GitHub repo、通過或疑似） ==")
    picks = [c for c in gh_c if c["triage"]["result"] in ("pass", "suspect")]
    picks.sort(key=lambda c: c["candidate_id"])
    for c in picks[:: max(1, len(picks) // 5)][:5]:
        r = c["repo"] or {}
        s0 = c["sources"][0]
        print(json.dumps({
            "id": c["candidate_id"], "status": c["status"], "triage": c["triage"]["result"],
            "why": c["triage"]["reasons"], "stars": r.get("stars"), "created": (r.get("created_at") or "")[:10],
            "license": r.get("license"), "packages": [p["purl"] for p in c["packages"]][:3],
            "hn": s0["ref"], "points": s0["signals"].get("points"), "title": (s0["signals"].get("title") or "")[:70],
        }, ensure_ascii=False))
    if multi_post:
        c = multi_post[0]
        print("\n== 合併例：同一 repo、多則貼文 ==")
        print(json.dumps({"id": c["candidate_id"], "aliases": c["aliases"][:4],
                          "sources": [{k: s[k] for k in ("channel", "ref", "role", "seen_at")} for s in c["sources"]]},
                         ensure_ascii=False, indent=1))
    if cross:
        c = cross[0]
        print("\n== 合併例：跨管道 ==")
        print(json.dumps({"id": c["candidate_id"],
                          "sources": [{k: s[k] for k in ("channel", "ref", "role", "seen_at")} for s in c["sources"]]},
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
