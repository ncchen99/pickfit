#!/usr/bin/env python3
"""對給定的 GitHub repo 拉「是不是可用軟體」與「品質／知名度」訊號，算出草案分數。

資料來源（依序嘗試，全部是公開 API）：
- GitHub REST API（GH_TOKEN）：repo、檔案樹、releases。拿不到（例如 403）就改用下面的鏡像。
- ecosyste.ms：repos（repo 中繼資料、releases 含資產與下載數、檔案）、issues（關閉時間）、
  commits（committer 分布）、packages（各登錄處下載量、dependents）、archives（檔案列表）。
- raw.githubusercontent.com：README 與 package.json / pyproject.toml / Cargo.toml / setup.cfg。
- OpenSSF Scorecard REST API（api.scorecard.dev），只有被掃描或自己發布結果的 repo 才有資料。
- deps.dev v3 projects：交叉核對 stars/forks。
- Hacker News Algolia API：repo 網址被貼過幾次、最高分數。

分數是 docs/research/notes/quality-scoring.md 的草案；沙盒驗證結果在這裡一律是「未驗證」。

執行：
    python3 spikes/quality_signals.py                           # 跑預設的 7 個 repo
    python3 spikes/quality_signals.py owner/repo:cli owner/repo:local-ai --json out.json
環境變數：GH_TOKEN（選填）、PICKFIT_CONTACT=<email>（選填，ecosyste.ms polite pool）。
只用標準函式庫；不寫入任何金鑰。
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

CONTACT = os.environ.get("PICKFIT_CONTACT")
UA = "pickfit-spike/0.1" + (f" (mailto:{CONTACT})" if CONTACT else " (+https://github.com/ncchen99/pickfit)")
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
NOW = dt.datetime.now(dt.timezone.utc)
ECO = "https://{svc}.ecosyste.ms/api/v1/hosts/GitHub/repositories/{r}"

DEFAULT = ["derekwisong/datui:cli", "shdwfruit/convkit:cli", "ahmetomerv/photoc:cli",
           "sawfwair/mere-run:local-ai", "sharkdp/bat:cli",
           "okunix/gollama:local-ai", "agarrharr/awesome-cli-apps:cli"]

# 知名度的參考上限（達到就算 100 分），依類別校正。本地 AI 類的星數普遍較高。
POP_REF = {
    "cli":      {"stars": 20000, "forks": 1500, "dl_month": 200000, "dependents": 2000, "rel_dl": 200000, "hn": 500, "packagers": 8},
    "local-ai": {"stars": 60000, "forks": 6000, "dl_month": 500000, "dependents": 2000, "rel_dl": 500000, "hn": 800, "packagers": 6},
}
POP_W = {"stars": 0.35, "forks": 0.10, "dl_month": 0.15, "dependents": 0.10, "rel_dl": 0.10, "hn": 0.10, "packagers": 0.10}
# 品質權重：沙盒驗證最重；工程衛生（CI、測試、changelog）用 AI 很容易做出來，權重壓低。
QUAL_W = {"verification": 35, "install_docs": 20, "maintenance": 15, "hygiene": 10, "responsiveness": 10, "outcomes": 10}
DISTROS = {"homebrew", "debian", "ubuntu", "alpine", "nixpkgs", "guix", "spack", "conda", "aur", "fedora",
           "archlinux", "macports", "freebsd", "winget", "scoop", "chocolatey", "flathub", "snapcraft"}


def http(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, (body.decode("utf-8", "replace") if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, None


def gh(path):
    if not GH_TOKEN:
        return 0, None
    return http("https://api.github.com/" + path, {"Authorization": f"Bearer {GH_TOKEN}",
                                                   "Accept": "application/vnd.github+json"})


def days_since(ts):
    if not ts:
        return None
    return (NOW - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).days


def lognorm(x, ref):
    if x is None:
        return None
    return round(min(100.0, 100 * math.log10(1 + max(x, 0)) / math.log10(1 + ref)), 1)


def recency(days, full=90, half=180, low=365):
    if days is None:
        return 0.0
    return 1.0 if days <= full else 0.6 if days <= half else 0.3 if days <= low else 0.0


# ---------------------------------------------------------------- 收集訊號
def collect(repo):
    enc = urllib.parse.quote(repo, safe="")
    s = {"repo": repo, "sources": {}}

    st, g = gh(f"repos/{repo}")
    s["sources"]["github_api"] = st
    st, e = http(ECO.format(svc="repos", r=enc))
    s["sources"]["ecosystems_repos"] = st
    if not (g or e):
        return s
    if g:  # GitHub 為主，ecosyste.ms 補
        base = {k: g.get(k) for k in ("stargazers_count", "forks_count", "open_issues_count", "created_at",
                                       "pushed_at", "archived", "fork", "topics", "description", "language",
                                       "default_branch")}
        base["license"] = (g.get("license") or {}).get("spdx_id")
        base["template"] = g.get("is_template")
    else:
        base = {k: e.get(k) for k in ("stargazers_count", "forks_count", "open_issues_count", "created_at",
                                       "pushed_at", "archived", "fork", "topics", "description", "language",
                                       "default_branch", "license", "template")}
    s.update(base)
    s["eco_synced"] = ((e or {}).get("last_synced_at") or "")[:10]
    s["readme_name"] = ((e or {}).get("metadata") or {}).get("files", {}).get("readme") or "README.md"
    s["eco_files"] = ((e or {}).get("metadata") or {}).get("files", {})

    # 檔案樹
    files = None
    if g:
        st, t = gh(f"repos/{repo}/git/trees/{s['default_branch']}?recursive=1")
        if t:
            files = [x["path"] for x in t.get("tree", [])]
    if files is None:
        url = f"https://codeload.github.com/{repo}/tar.gz/HEAD"
        st, a = http("https://archives.ecosyste.ms/api/v1/archives/list?url=" + urllib.parse.quote(url, safe=""))
        s["sources"]["ecosystems_archives"] = st
        if isinstance(a, list):
            files = [p.split("/", 1)[1] for p in a if "/" in p]
    s["files"] = files or []

    # releases（含資產與下載數）
    rels = None
    if g:
        st, rels = gh(f"repos/{repo}/releases?per_page=30")
    if rels is None:
        st, rels = http(ECO.format(svc="repos", r=enc) + "/releases?per_page=30")
        s["sources"]["ecosystems_releases"] = st
    s["releases"] = [{"tag": r.get("tag_name"), "published_at": r.get("published_at"), "prerelease": r.get("prerelease"),
                      "body_len": len(r.get("body") or ""),
                      "assets": [(a.get("name"), a.get("download_count") or 0) for a in (r.get("assets") or [])]}
                     for r in (rels or []) if not r.get("draft")]

    # README 與套件中繼資料
    raw = f"https://raw.githubusercontent.com/{repo}/HEAD/"
    st, s["readme"] = http(raw + s["readme_name"], raw=True)
    s["sources"]["raw_readme"] = st
    fs = set(s["files"])
    for f in ("package.json", "pyproject.toml", "Cargo.toml", "setup.cfg"):
        s[f] = http(raw + f, raw=True)[1] if (f in fs or not fs) else None

    st, s["issues"] = http(ECO.format(svc="issues", r=enc))
    s["sources"]["ecosystems_issues"] = st
    st, s["commits"] = http(ECO.format(svc="commits", r=enc))
    s["sources"]["ecosystems_commits"] = st
    st, pk = http("https://packages.ecosyste.ms/api/v1/packages/lookup?repository_url="
                  + urllib.parse.quote(f"https://github.com/{repo}", safe=""))
    s["sources"]["ecosystems_packages"] = st
    s["packages"] = [{k: p.get(k) for k in ("ecosystem", "name", "downloads", "downloads_period", "dependent_repos_count",
                                            "dependent_packages_count", "first_release_published_at")}
                     for p in (pk or [])]
    st, s["scorecard"] = http(f"https://api.scorecard.dev/projects/github.com/{repo}")
    s["sources"]["scorecard_api"] = st
    st, dd = http("https://api.deps.dev/v3/projects/" + urllib.parse.quote(f"github.com/{repo}", safe=""))
    s["sources"]["depsdev"] = st
    s["depsdev_stars"] = (dd or {}).get("starsCount")
    st, hn = http("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": f"github.com/{repo}", "restrictSearchableAttributes": "url", "hitsPerPage": 50}))
    s["sources"]["hn_algolia"] = st
    hits = [h for h in (hn or {}).get("hits", []) if repo.lower() in (h.get("url") or "").lower()]
    s["hn_posts"], s["hn_max_points"] = len(hits), max([h.get("points") or 0 for h in hits], default=0)
    return s


# ---------------------------------------------------------------- 是不是可用的軟體（規則）
INSTALL_H = re.compile(r"^#{1,4}\s*.*\b(install|installation|getting started|quick ?start|setup|download)\b|^#{1,4}.*(安裝|下載)", re.I | re.M)
USAGE_H = re.compile(r"^#{1,4}\s*.*\b(usage|how to use|examples?|commands?|features)\b|^#{1,4}.*(使用|用法)", re.I | re.M)
INSTALL_CMD = re.compile(r"\b(brew install|cargo (b)?install|pipx install|uv tool install|pip3? install|npm (i|install) -g|"
                         r"npx |go install|winget install|scoop install|apt(-get)? install|yay -S|paru -S|nix (profile install|run)|"
                         r"docker (run|compose)|curl [^\n|]*\|\s*(ba|z)?sh|make install|cmake --build)", re.I)
NEG = [("awesome_list", re.compile(r"^awesome[-_]|\bawesome[- ]list\b|curated list", re.I)),
       ("homework", re.compile(r"homework|assignment|coursework|\bcourse\b|exercises?\b|leetcode|bootcamp|作業|\blab\d", re.I)),
       ("tutorial", re.compile(r"tutorial|learning[- ]|\blearn[- ]|教學|cheat ?sheet|interview", re.I)),
       ("template", re.compile(r"template|starter|boilerplate|scaffold|skeleton", re.I)),
       ("dotfiles", re.compile(r"dotfiles|my (neo)?vim config|\.config\b", re.I)),
       ("demo", re.compile(r"\bdemo\b|proof[- ]of[- ]concept|\bpoc\b|\bexample(s)?\b|sample", re.I))]
BIN_ASSET = re.compile(r"(darwin|macos|apple|linux|windows|win64|x86_64|amd64|aarch64|arm64|\.dmg$|\.exe$|\.msi$|\.deb$|"
                       r"\.rpm$|\.appimage$|\.pkg$|\.apk$)", re.I)
TOOL_TOPICS = {"cli", "command-line", "command-line-tool", "terminal", "tui", "app", "desktop-app", "macos-app",
               "self-hosted", "local-ai", "local-llm", "developer-tools", "devtools"}


def classify(s):
    files, readme = s["files"], s["readme"] or ""
    text = " ".join([s["repo"].split("/")[1], s.get("description") or "", " ".join(s.get("topics") or [])])
    pos, neg = [], []
    if INSTALL_H.search(readme): pos.append(("readme_install_section", 2))
    if USAGE_H.search(readme): pos.append(("readme_usage_section", 1))
    if INSTALL_CMD.search(readme): pos.append(("readme_install_command", 2))
    assets = [a for r in s["releases"] for a, _ in r["assets"]]
    if any(BIN_ASSET.search(a) for a in assets): pos.append(("release_binaries", 3))
    pj = s.get("package.json")
    entry = []
    if pj:
        try:
            p = json.loads(pj)
            if p.get("bin"): entry.append("package.json bin")
            elif p.get("main") or p.get("exports"): neg.append(("npm_library_no_bin", 2))
        except json.JSONDecodeError:
            pass
    pyt = s.get("pyproject.toml") or ""
    if re.search(r"^\[project\.(scripts|gui-scripts)\]|^\[tool\.poetry\.scripts\]", pyt, re.M): entry.append("pyproject scripts")
    if re.search(r"console_scripts", s.get("setup.cfg") or ""): entry.append("setup.cfg console_scripts")
    if "src/main.rs" in files or any(f.startswith("src/bin/") for f in files) or "[[bin]]" in (s.get("Cargo.toml") or ""):
        entry.append("cargo bin")
    go_main = "main.go" in files or any(re.match(r"cmd/[^/]+/main\.go$", f) for f in files)  # examples/ 不算
    if go_main: entry.append("go main")
    if any(f.endswith((".xcodeproj/project.pbxproj", "tauri.conf.json", "Package.swift")) for f in files): entry.append("app project")
    if entry: pos.append(("entry_point:" + ",".join(entry), 3))
    elif pyt and "[project]" in pyt: neg.append(("python_library_no_scripts", 2))
    elif s.get("Cargo.toml") and "src/lib.rs" in files and "src/main.rs" not in files: neg.append(("cargo_lib_only", 2))
    elif "go.mod" in files and not go_main: neg.append(("go_no_main", 2))
    if re.search(r"\bgo get (-u )?[\w.]+/|^\s*(from \w+ import|import \w+$)|require\(['\"]", readme, re.M) \
            and "readme_install_command" not in dict(pos):
        neg.append(("readme_shows_library_usage", 2))
    if any(p["ecosystem"] in DISTROS for p in s["packages"]): pos.append(("packaged_in_distro", 2))
    if TOOL_TOPICS & set(s.get("topics") or []): pos.append(("tool_topic", 1))
    for name, rx in NEG:
        if rx.search(text): neg.append((name, 4 if name != "demo" else 2))
    if s.get("template"): neg.append(("github_template_flag", 4))
    code = [f for f in files if re.search(r"\.(go|rs|py|ts|js|swift|c|cc|cpp|zig|java|kt|rb|sh)$", f)]
    if files and not code: neg.append(("no_source_files", 4))
    links = len(re.findall(r"^\s*[-*] \[.+?\]\(http", readme, re.M))
    if links > 40: neg.append((f"readme_is_link_list({links})", 3))
    is_lib = lambda n: n.endswith(("library_no_bin", "no_scripts", "lib_only", "no_main", "library_usage"))
    P = sum(w for _, w in pos)
    N = sum(w for n, w in neg if not is_lib(n))  # 非軟體（清單、作業、模板…）
    L = sum(w for n, w in neg if is_lib(n))      # 函式庫
    if N >= 4 and N >= P: label = "non_software"
    elif L >= 2 and P < 5: label = "library"
    elif P >= 5 and N < 4: label = "tool"
    else: label = "uncertain(交給模型)"
    return {"label": label, "pos": pos, "neg": neg, "P": P, "N": N, "L": L}


# ---------------------------------------------------------------- 品質
SC_FAIR = ["Dangerous-Workflow", "Token-Permissions", "Binary-Artifacts", "Vulnerabilities", "Pinned-Dependencies",
           "License", "Security-Policy", "Packaging", "Signed-Releases", "CI-Tests"]


def quality(s, cls, verification=None):
    files, readme = s["files"], s["readme"] or ""
    age = days_since(s.get("created_at"))
    comp, notes = {}, []
    # 1 沙盒驗證：spike 不跑沙盒
    comp["verification"] = verification  # None=未驗證, 0..1
    comp["outcomes"] = None  # report_outcome 的成功率；黑客松初期沒有資料
    # 2 安裝與文件（規則版；正式版由模型依 rubric 打分）
    pos = dict(cls["pos"])
    has_bin = "release_binaries" in pos or "packaged_in_distro" in pos or any(
        p["ecosystem"] in ("cargo", "pypi", "npm", "go", "homebrew") for p in s["packages"])
    comp["install_docs"] = round(0.25 * ("readme_install_section" in pos) + 0.2 * ("readme_usage_section" in pos)
                                 + 0.15 * ("readme_install_command" in pos) + 0.25 * has_bin
                                 + 0.15 * min(1, len(readme) / 3000), 3) if s["readme"] else 0.0
    # 3 維護（只看「有沒有」，不獎勵數量：防刷 release/commit）
    rel = [r for r in s["releases"] if not r["prerelease"]] or s["releases"]
    last_rel = days_since(rel[0]["published_at"]) if rel else None
    rel_365 = sum(1 for r in rel if (days_since(r["published_at"]) or 9999) <= 365)
    cadence = 1.0 if rel_365 >= 2 else 0.5 if rel_365 == 1 else 0.0
    if age is not None and age < 180 and rel_365 >= 1: cadence = 1.0  # 新 repo 不要求節奏
    comp["maintenance"] = round(0.35 * recency(days_since(s.get("pushed_at"))) + 0.35 * recency(last_rel, 180, 365, 730)
                                + 0.30 * cadence, 3)
    # 4 工程衛生
    ci = any(f.startswith(".github/workflows/") or f in (".gitlab-ci.yml", ".circleci/config.yml", ".travis.yml")
             for f in files)
    tests = any(re.search(r"(^|/)(tests?|spec|__tests__)/|_test\.(go|py)$|(^|/)test_[^/]+\.py$|\.(test|spec)\.[jt]sx?$|"
                          r"Tests/.+\.swift$", f) for f in files) or bool(re.search(r"#\[(cfg\()?test", readme))
    lic = bool(s.get("license")) and str(s.get("license")).lower() not in ("other", "noassertion", "none")
    changelog = bool(s["eco_files"].get("changelog")) or any(re.match(r"(?i)changelog|changes|history", f) for f in files) \
        or any(r["body_len"] > 80 for r in rel[:3])
    lock = any(f.split("/")[-1] in ("Cargo.lock", "go.sum", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock",
                                    "poetry.lock", "Package.resolved", "bun.lockb") for f in files)
    own = 0.25 * ci + 0.25 * tests + 0.2 * lic + 0.15 * changelog + 0.15 * lock
    sc = None
    if s.get("scorecard"):
        vals = [c["score"] for c in s["scorecard"].get("checks", []) if c["name"] in SC_FAIR and c["score"] >= 0]
        sc = sum(vals) / (10 * len(vals)) if vals else None
    comp["hygiene"] = round(own if sc is None else 0.8 * own + 0.2 * sc, 3)
    s["_hyg"] = {"ci": ci, "tests": tests, "license": lic, "changelog": changelog, "lockfile": lock,
                 "scorecard_fair_avg": None if sc is None else round(sc * 10, 1)}
    # 5 回應（CHAOSS 的 issue 關閉時間／change request closure ratio 的近似；資料太少就不算）
    iss = s.get("issues") or {}
    ext_issues = sum(v for k, v in (iss.get("issue_author_associations_count") or {}).items()
                     if k not in ("OWNER", "MEMBER", "COLLABORATOR"))
    if (iss.get("issues_count") or 0) >= 3 and ext_issues >= 2:
        ratio = (iss.get("issues_closed_count") or 0) / max(1, iss.get("issues_count"))
        t = (iss.get("avg_time_to_close_issue") or 0) / 86400
        speed = 1.0 if t <= 7 else 0.6 if t <= 30 else 0.3 if t <= 90 else 0.1
        prs = iss.get("pull_requests_count") or 0
        pr_ratio = (iss.get("merged_pull_requests_count") or 0) / prs if prs >= 3 else None
        parts = [0.4 * ratio, 0.4 * speed] + ([0.2 * pr_ratio] if pr_ratio is not None else [])
        comp["responsiveness"] = round(sum(parts) / (1.0 if pr_ratio is not None else 0.8), 3)
    else:
        comp["responsiveness"] = None
        notes.append("issue 太少，回應分不計")
    avail = {k: v for k, v in comp.items() if v is not None}
    wsum = sum(QUAL_W[k] for k in avail)
    q = sum(QUAL_W[k] * v for k, v in avail.items()) / wsum * 100 if wsum else 0
    conf = wsum / sum(QUAL_W.values())
    cap = None
    caps = []
    if s.get("archived"): caps.append((30, "archived → 上限 30"))
    if verification is None: caps.append((69, "未驗證 → 上限 69（不能當寶藏）"))
    elif verification == 0: caps.append((40, "驗證失敗 → 上限 40"))
    if cls["label"] != "tool": caps.append((50, f"分類={cls['label']} → 上限 50"))
    notes += [n for _, n in caps]
    cap = min([c for c, _ in caps], default=None)
    q_final = min(q, cap) if cap else q
    q_if = (sum(QUAL_W[k] * v for k, v in avail.items()) + QUAL_W["verification"]) / (wsum + QUAL_W["verification"]) * 100 \
        if verification is None else q
    return {"components": comp, "quality_pre_cap": round(q, 1), "quality": round(q_final, 1),
            "quality_if_verified": round(min(q_if, 30 if s.get("archived") else 100, 50 if cls["label"] != "tool" else 100), 1),
            "confidence": round(conf, 2), "notes": notes}


# ---------------------------------------------------------------- 知名度
def popularity(s, cat):
    ref = POP_REF[cat]
    pk = s["packages"]
    by_eco = {}
    for p in pk:
        d = p.get("downloads")
        if not d: continue
        if p.get("downloads_period") == "total":
            months = max(1, (days_since(p.get("first_release_published_at")) or 30) / 30)
            d = d / months
        by_eco[p["ecosystem"]] = max(by_eco.get(p["ecosystem"], 0), d)
    dl = sum(by_eco.values()) if by_eco else None
    dep = sum(max([p.get("dependent_repos_count") or 0 for p in pk if p["ecosystem"] == e] or [0])
              for e in {p["ecosystem"] for p in pk}) if pk else None
    rel_dl = sum(n for r in s["releases"] for _, n in r["assets"]) if any(r["assets"] for r in s["releases"]) else None
    packagers = len({p["ecosystem"] for p in pk} & DISTROS)
    raw = {"stars": s.get("stargazers_count"), "forks": s.get("forks_count"), "dl_month": dl, "dependents": dep,
           "rel_dl": rel_dl, "hn": s.get("hn_max_points"), "packagers": packagers}
    norm = {k: lognorm(v, ref[k]) for k, v in raw.items()}
    avail = {k: v for k, v in norm.items() if v is not None}
    absolute = sum(POP_W[k] * v for k, v in avail.items()) / sum(POP_W[k] for k in avail)
    age_m = max(1.0, (days_since(s.get("created_at")) or 30) / 30.4)
    velocity = lognorm((s.get("stargazers_count") or 0) / age_m, ref["stars"] / 24)  # 兩年達到參考值 = 100
    pop = absolute if age_m < 3 else 0.75 * absolute + 0.25 * velocity
    return {"raw": raw, "norm": norm, "absolute": round(absolute, 1), "stars_per_month": round((s.get("stargazers_count") or 0) / age_m, 1),
            "velocity": velocity, "popularity": round(pop, 1)}


# ---------------------------------------------------------------- 防灌水旗標
def gaming_flags(s):
    f = []
    stars, forks = s.get("stargazers_count") or 0, s.get("forks_count") or 0
    iss = s.get("issues") or {}
    if stars >= 300 and forks / stars < 0.005: f.append("forks/stars < 0.5%")
    if stars >= 300 and (iss.get("issues_count") or 0) == 0 and (iss.get("pull_requests_count") or 0) == 0:
        f.append("星多但零 issue/PR")
    age = max(1, days_since(s.get("created_at")) or 1)
    if len(s["releases"]) >= 30 and age < 120: f.append(f"{len(s['releases'])}+ releases / {age} 天（release 不加分，只記錄）")
    c = s.get("commits") or {}
    if (c.get("past_year_total_commits") or 0) > 3000 and (c.get("past_year_total_committers") or 0) <= 2:
        f.append("單人一年 >3000 commits")
    if s.get("depsdev_stars") and stars and abs(s["depsdev_stars"] - stars) > max(50, 0.2 * stars):
        f.append(f"deps.dev 星數 {s['depsdev_stars']} 與來源差 >20%")
    return f


def absence_factor(s):
    """CHAOSS Contributor Absence Factor：貢獻 50% commits 的最少人數（排除 bot）。"""
    cm = [c["count"] for c in (s.get("commits") or {}).get("committers") or [] if "[bot]" not in (c.get("login") or c.get("name") or "")]
    if not cm: return None
    cm.sort(reverse=True)
    tot, acc = sum(cm), 0
    for i, n in enumerate(cm, 1):
        acc += n
        if acc * 2 >= tot: return i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*", default=DEFAULT, help="owner/repo[:cli|local-ai]")
    ap.add_argument("--json", help="把完整結果寫到這個路徑")
    a = ap.parse_args()
    out = []
    for spec in a.repos:
        repo, _, cat = spec.partition(":")
        cat = cat or "cli"
        s = collect(repo)
        if "created_at" not in s:
            print(f"## {repo}: 拿不到資料 {s['sources']}")
            continue
        cls = classify(s)
        q, p = quality(s, cls), popularity(s, cat)
        gap = round(q["quality_if_verified"] - p["popularity"], 1)
        treasure = ("寶藏候選（待沙盒驗證）" if cls["label"] == "tool" and q["quality_if_verified"] >= 70
                    and p["popularity"] <= 45 else "否")
        r = {"repo": repo, "category": cat, "created": (s["created_at"] or "")[:10], "stars": s.get("stargazers_count"),
             "classify": cls, "quality": q, "hygiene": s["_hyg"], "popularity": p, "gap": gap, "treasure": treasure,
             "absence_factor": absence_factor(s), "gaming_flags": gaming_flags(s), "sources": s["sources"],
             "scorecard_api": (s["scorecard"] or {}).get("score"), "hn_posts": s["hn_posts"]}
        out.append(r)
        print(f"## {repo} [{cat}] created={r['created']} stars={r['stars']} 分類={cls['label']} (P={cls['P']} N={cls['N']} L={cls['L']})")
        print(f"   正向={[n for n, _ in cls['pos']]} 負向={[n for n, _ in cls['neg']]}")
        print(f"   品質：未封頂={q['quality_pre_cap']} 封頂後={q['quality']} 若驗證通過={q['quality_if_verified']} "
              f"信心={q['confidence']} 分項={q['components']} {q['notes']}")
        print(f"   衛生={s['_hyg']} Scorecard API={r['scorecard_api']} absence_factor={r['absence_factor']}")
        print(f"   知名度={p['popularity']} (絕對 {p['absolute']}, 星/月 {p['stars_per_month']}, 速度分 {p['velocity']}) 原始={p['raw']}")
        print(f"   (若驗證通過的品質)-知名度={gap} → {treasure}；防灌水旗標={r['gaming_flags']}")
        print(f"   來源 HTTP 狀態={s['sources']} ecosyste.ms 同步日={s['eco_synced']}")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
