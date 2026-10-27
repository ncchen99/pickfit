#!/usr/bin/env python3
"""URL 正規化、GitHub 改名偵測、套件 → repo 映射（pickfit 調研 spike，不是產品程式碼）。

子命令：
  selftest   離線單元測試：各種 URL 寫法 → canonical key（不連網）
  github     GitHub 改名／轉移／大小寫實測。先試 REST API（不自動跟 redirect，
             直接看 301 與 Location）；API 被擋時改用 git ls-remote（比對 HEAD）
             與 ecosyste.ms（previous_names）
  packages   PyPI／npm／Homebrew 套件 → repo：宣告的欄位 vs 簽章 provenance
  short      真實短網址逐跳展開
  recent     PyPI 最新 40 個專案（RSS）→ 有幾個對得到 repo、幾個有 provenance
  all        以上全部

用法：
  python3 spikes/ch_integration_normalize.py all
  GH_TOKEN=... python3 spikes/ch_integration_normalize.py github   # 有 token 時看 API 的 301

環境變數（都選填）：GH_TOKEN（GitHub API）、PICKFIT_CONTACT（放進 User-Agent）。
只用 Python 標準函式庫；不含任何金鑰。
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CONTACT = os.environ.get("PICKFIT_CONTACT", "")
UA = "pickfit-research/0.1" + (f" (mailto:{CONTACT})" if CONTACT else "")
TIMEOUT = 25

# ---------------------------------------------------------------- HTTP

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http(url, headers=None, method="GET", follow=True):
    """回傳 (status, headers（key 小寫）, body_bytes)。follow=False 時看得到 3xx 本身。"""
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, method=method)
    opener = urllib.request.build_opener() if follow else _OPENER
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() if e.fp else b""
    except Exception as e:  # 連線錯誤
        return 0, {}, str(e).encode()


def jget(url, headers=None):
    st, _, b = http(url, headers)
    if st != 200:
        return None
    try:
        return json.loads(b)
    except ValueError:
        return None

# ---------------------------------------------------------------- 正規化

FORGES = {"github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "sr.ht", "git.sr.ht"}
# github.com/<這些>/... 不是 repo
GH_RESERVED = {
    "about", "apps", "collections", "codespaces", "contact", "customer-stories", "enterprise",
    "events", "explore", "features", "issues", "login", "marketplace", "new", "notifications",
    "orgs", "organizations", "pricing", "pulls", "search", "security", "settings", "site",
    "sponsors", "topics", "trending", "users", "join", "readme", "solutions", "resources"}
GH_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
GH_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SHORTENERS = {"t.co", "bit.ly", "tinyurl.com", "lnkd.in", "buff.ly", "ow.ly", "is.gd", "goo.gl",
              "git.io", "rebrand.ly", "cutt.ly", "shorturl.at", "dub.sh", "t.ly", "s.id",
              "rb.gy", "tiny.cc", "shorturl.com", "bl.ink"}
# 連結轉址殼：目標網址就在 query 裡，不必發請求
LINK_SHIMS = {"l.threads.com": "u", "l.facebook.com": "u", "lm.facebook.com": "u",
              "l.instagram.com": "u", "www.google.com": "q", "href.li": None,
              "out.reddit.com": "url", "l.messenger.com": "u"}
TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|igshid|mc_cid|mc_eid|ref|ref_src|si|s|source)$", re.I)


def _unshim(u):
    p = urllib.parse.urlsplit(u)
    host = p.netloc.lower()
    if host in LINK_SHIMS:
        if host == "href.li":
            return p.query or u
        q = urllib.parse.parse_qs(p.query).get(LINK_SHIMS[host])
        if q:
            return q[0]
    return u


def canon(raw, npm_shorthand=False):
    """把各種寫法轉成 dict(kind, key, url, owner, repo, subpath, rules)。

    kind: repo（程式碼託管 repo）、hn_item、threads_post、pages（github.io）、
          short（短網址，需展開）、web（一般網站）、invalid
    key:  合併用主鍵。repo 一律小寫 host/owner/repo（GitHub 大小寫不敏感，已實測）。
    """
    rules = []
    s = (raw or "").strip().strip("<>\"'")
    s2 = s.rstrip(").,;:!?]")
    if s2 != s:
        rules.append("strip_trailing_punct")
    s = s2
    if not s:
        return {"kind": "invalid", "key": None, "url": raw, "rules": rules}
    # npm 簡寫：github:o/r、gitlab:o/r、bitbucket:o/r、o/r
    m = re.match(r"^(github|gitlab|bitbucket):([^/\s]+)/([^/\s#]+)", s)
    if m:
        host = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}[m[1]]
        s = f"https://{host}/{m[2]}/{m[3]}"
        rules.append("npm_shorthand")
    elif npm_shorthand and re.match(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$", s):
        s = "https://github.com/" + s
        rules.append("npm_shorthand")
    # git 協定
    m = re.match(r"^(?:git\+)?(?:ssh://)?git@([^:/]+)[:/](.+)$", s)
    if m:
        s = f"https://{m[1]}/{m[2]}"
        rules.append("scp_or_ssh")
    if s.startswith("git+"):
        s = s[4:]
        rules.append("git+")
    if s.startswith("git://"):
        s = "https://" + s[6:]
        rules.append("git_scheme")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I):
        s = "https://" + s
        rules.append("add_scheme")
    un = _unshim(s)
    if un != s:
        s = un
        rules.append("unshim")
    p = urllib.parse.urlsplit(s)
    if p.scheme.lower() == "http":
        rules.append("http_to_https")
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
        rules.append("strip_www")
    path = urllib.parse.unquote(p.path)
    segs = [x for x in path.split("/") if x]

    if host in SHORTENERS:
        return {"kind": "short", "key": f"short:{host}{p.path}", "url": f"https://{host}{p.path}", "rules": rules}

    if host in ("news.ycombinator.com",):
        q = urllib.parse.parse_qs(p.query).get("id")
        if q and q[0].isdigit():
            return {"kind": "hn_item", "key": f"hn:{q[0]}", "url": f"https://news.ycombinator.com/item?id={q[0]}", "rules": rules}

    if host in ("threads.com", "threads.net"):
        m = re.match(r"^@([\w.]+)/post/([\w-]+)", "/".join(segs))
        if m:
            if host == "threads.net":
                rules.append("threads_net_to_com")
            return {"kind": "threads_post", "key": f"threads:{m[2]}",
                    "url": f"https://www.threads.com/@{m[1]}/post/{m[2]}", "rules": rules}

    # GitHub 的其他網域 → repo
    if host in ("raw.githubusercontent.com", "codeload.github.com") and len(segs) >= 2:
        rules.append(host.split(".")[0] + "_to_repo")
        host, segs = "github.com", segs[:2] + (["tree"] + segs[2:] if len(segs) > 2 else [])
    if host == "api.github.com" and len(segs) >= 3 and segs[0] == "repos":
        rules.append("api_to_repo")
        host, segs = "github.com", segs[1:3]
    if host.endswith(".github.io"):
        user = host[: -len(".github.io")]
        repo = segs[0] if segs else f"{user}.github.io"
        return {"kind": "pages", "key": f"github.com/{user.lower()}/{repo.lower()}",
                "url": f"https://github.com/{user}/{repo}", "owner": user, "repo": repo,
                "rules": rules + ["pages_hint(待確認)"]}

    if host in FORGES or host.startswith("gitlab."):
        if host == "gitlab.com" or host.startswith("gitlab."):
            # GitLab 有巢狀 group，以 "/-/" 為界
            if "-" in segs:
                i = segs.index("-")
                proj, sub = segs[:i], segs[i + 1:]
                rules.append("gitlab_dash_path")
            else:
                proj, sub = segs, []
            if len(proj) < 2:
                return {"kind": "web", "key": f"web:{host}/{'/'.join(segs)}".lower(), "url": s, "rules": rules}
            if proj[-1].endswith(".git"):
                proj[-1] = proj[-1][:-4]
                rules.append("strip_.git")
            owner, repo = "/".join(proj[:-1]), proj[-1]
            subpath = "/".join(sub[2:]) if len(sub) > 2 and sub[0] in ("tree", "blob") else None
        else:
            if len(segs) < 2 or (host == "github.com" and segs[0].lower() in GH_RESERVED):
                kind = "forge_user" if len(segs) == 1 else "web"
                return {"kind": kind, "key": f"web:{host}/{'/'.join(segs)}".lower(), "url": s, "rules": rules}
            owner, repo = segs[0], segs[1]
            if repo.endswith(".git"):
                repo = repo[:-4]
                rules.append("strip_.git")
            subpath = None
            frag = urllib.parse.parse_qs(p.fragment).get("subdirectory")
            if frag:   # pip 風格：...#subdirectory=crates/foo
                subpath = frag[0]
                rules.append("pip_subdirectory")
            if len(segs) > 2:
                rules.append("drop_subpage:" + segs[2])
                if segs[2] in ("tree", "blob") and len(segs) > 4:
                    subpath = "/".join(segs[4:])   # monorepo 子目錄
            if host == "github.com" and not (GH_OWNER.match(owner) and GH_REPO.match(repo)):
                return {"kind": "invalid", "key": None, "url": raw, "rules": rules + ["bad_gh_name"]}
        if p.fragment or p.query:
            rules.append("drop_query_fragment")
        if path.endswith("/") and len(segs) == 2:
            rules.append("strip_trailing_slash")
        if (owner + repo) != (owner + repo).lower():
            rules.append("lowercase_key")
        return {"kind": "repo", "key": f"{host}/{owner.lower()}/{repo.lower()}",
                "url": f"https://{host}/{owner}/{repo}", "owner": owner, "repo": repo,
                "subpath": subpath, "rules": rules}

    # 一般網站：去追蹤參數、尾斜線，小寫 host
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    if len(q) != len(urllib.parse.parse_qsl(p.query, keep_blank_values=True)):
        rules.append("drop_tracking")
    clean_path = p.path.rstrip("/") or ""
    url = urllib.parse.urlunsplit(("https", host, clean_path, urllib.parse.urlencode(q), ""))
    return {"kind": "web", "key": f"web:{host}{clean_path}".lower(), "url": url, "rules": rules}


URL_IN_TEXT = re.compile(r"(?:https?://|git@|github\.com/)[^\s<>\"'`]+", re.I)


def extract_urls(text):
    """從貼文、README、表單文字裡抓網址；去掉句尾標點與不成對的右括號。"""
    out = []
    for m in URL_IN_TEXT.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?'\"")
        while u.endswith(")") and u.count("(") < u.count(")"):
            u = u[:-1]
        out.append(u)
    return out


def expand_short(url, max_hops=5):
    """手動逐跳展開短網址（HEAD，不行再 GET）。產品版要加 SSRF 防護：擋私有 IP、只允許 https。"""
    hops = [url]
    for _ in range(max_hops):
        st, hd, _ = http(hops[-1], method="HEAD", follow=False)
        if st in (405, 403, 400) or st == 0:
            st, hd, _ = http(hops[-1], method="GET", follow=False)
        loc = hd.get("location")
        if st in (301, 302, 303, 307, 308) and loc:
            hops.append(urllib.parse.urljoin(hops[-1], loc))
            if urllib.parse.urlsplit(hops[-1]).hostname not in SHORTENERS:
                break
        else:
            break
    return hops

# ---------------------------------------------------------------- selftest

CASES = [
    ("https://github.com/BurntSushi/ripgrep", "github.com/burntsushi/ripgrep"),
    ("http://www.github.com/BurntSushi/ripgrep/", "github.com/burntsushi/ripgrep"),
    ("https://github.com/BurntSushi/ripgrep.git", "github.com/burntsushi/ripgrep"),
    ("git+https://github.com/vitejs/vite.git", "github.com/vitejs/vite"),
    ("git+ssh://git@github.com/vitejs/vite.git", "github.com/vitejs/vite"),
    ("git@github.com:vitejs/vite.git", "github.com/vitejs/vite"),
    ("git://github.com/vitejs/vite.git", "github.com/vitejs/vite"),
    ("github:vitejs/vite", "github.com/vitejs/vite"),
    ("github.com/simonw/llm#readme", "github.com/simonw/llm"),
    ("https://github.com/vitejs/vite/tree/main/packages/vite", "github.com/vitejs/vite"),
    ("https://github.com/simonw/llm/releases/download/0.1/x.tar.gz", "github.com/simonw/llm"),
    ("https://github.com/simonw/llm?utm_source=hn", "github.com/simonw/llm"),
    ("https://raw.githubusercontent.com/simonw/llm/main/README.md", "github.com/simonw/llm"),
    ("https://api.github.com/repos/simonw/llm", "github.com/simonw/llm"),
    ("https://simonw.github.io/llm/", "github.com/simonw/llm"),
    ("https://gitlab.com/group/sub/proj/-/tree/main/cli", "gitlab.com/group/sub/proj"),
    ("https://codeberg.org/Forgejo/forgejo.git", "codeberg.org/forgejo/forgejo"),
    ("https://github.com/charliermarsh/ruff#subdirectory=crates/flake8_to_ruff", "github.com/charliermarsh/ruff"),
    ("https://l.threads.com/?u=https%3A%2F%2Fgithub.com%2Fsimonw%2Fllm&e=AT0", "github.com/simonw/llm"),
    ("https://www.threads.net/@someone/post/C8abcDEF", "threads:C8abcDEF"),
    ("https://news.ycombinator.com/item?id=42000000", "hn:42000000"),
    ("https://example.com/tool/?utm_source=x&id=3", "web:example.com/tool"),
    ("https://github.com/topics/cli", "web:github.com/topics/cli"),
    ("https://github.com/simonw", "web:github.com/simonw"),
    ("https://bit.ly/abc", "short:bit.ly/abc"),
]


def selftest():
    bad = 0
    for raw, want in CASES:
        got = canon(raw)
        ok = got["key"] == want
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {raw[:62]:62} -> {got['key']}  {','.join(got['rules'])}")
    ex = extract_urls("I built it (see https://github.com/simonw/llm). Also github.com/BurntSushi/ripgrep!")
    print("extract_urls:", ex)
    assert [canon(u)["key"] for u in ex] == ["github.com/simonw/llm", "github.com/burntsushi/ripgrep"]
    # npm 的 "owner/repo" 簡寫只在 npm repository 欄位內成立
    assert canon("vitejs/vite", npm_shorthand=True)["key"] == "github.com/vitejs/vite"
    print(f"\nselftest: {len(CASES) - bad}/{len(CASES)} 通過")
    return bad == 0

# ---------------------------------------------------------------- GitHub

def gh_api(path):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    url = path if path.startswith("http") else "https://api.github.com" + path
    return http(url, h, follow=False)


def git_head(url):
    try:
        out = subprocess.run(["git", "ls-remote", "--symref", url, "HEAD"], capture_output=True,
                             text=True, timeout=40, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except Exception as e:
        return None, None, str(e)
    if out.returncode != 0:
        return None, None, (out.stderr.strip().splitlines() or ["?"])[-1][:80]
    branch = sha = None
    for line in out.stdout.splitlines():
        if line.startswith("ref:"):
            branch = line.split()[1].rsplit("/", 1)[-1]
        elif line.endswith("\tHEAD"):
            sha = line.split()[0]
    return sha, branch, None


def eco_repo(owner, repo):
    d = jget("https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/" + urllib.parse.quote(f"{owner}/{repo}", safe=""))
    if not d:
        return None
    return {k: d.get(k) for k in ("full_name", "uuid", "previous_names", "fork", "archived", "template", "stargazers_count")}


def resolve_github(owner, repo):
    """回傳 dict：method、status、full_name、id、fork、archived、renamed…"""
    st, hd, body = gh_api(f"/repos/{owner}/{repo}")
    r = {"input": f"{owner}/{repo}", "api_status": st}
    if st in (301, 302, 307, 308):
        loc = hd.get("location")
        r["api_location"] = loc
        st2, _, body = gh_api(loc)
        st = st2
    if st == 200:
        d = json.loads(body)
        r.update(method="api", id=d["id"], full_name=d["full_name"], fork=d["fork"],
                 parent=(d.get("parent") or {}).get("full_name"), archived=d["archived"],
                 is_template=d.get("is_template"),
                 renamed=d["full_name"].lower() != f"{owner}/{repo}".lower())
        return r
    if st == 404:
        r.update(method="api", full_name=None, note="404：不存在或私有")
        return r
    # API 不可用（本調研環境的代理只放行本專案 repo）→ 退而求其次
    r["api_note"] = (body[:90].decode(errors="ignore") if body else "") or "no response"
    sha, branch, err = git_head(f"https://github.com/{owner}/{repo}")
    r.update(method="fallback", git_head=sha, default_branch=branch, git_err=err)
    eco = eco_repo(owner, repo)
    r["ecosystems"] = eco
    if eco:
        r["full_name"] = eco["full_name"]
        r["renamed"] = eco["full_name"].lower() != f"{owner}/{repo}".lower()
    return r


GH_PAIRS = [  # (舊名或變體, 現名)。改名／轉移的例子是公開已知的
    ("charliermarsh/ruff", "astral-sh/ruff"),
    ("jmorganca/ollama", "ollama/ollama"),
    ("ggerganov/llama.cpp", "ggml-org/llama.cpp"),
    ("ggerganov/whisper.cpp", "ggml-org/whisper.cpp"),
    ("twitter/bootstrap", "twbs/bootstrap"),
    ("BURNTSUSHI/RIPGREP", "BurntSushi/ripgrep"),
    ("simonw/llm", "simonw/llm"),
]


def github_cmd():
    print("== GitHub 改名／大小寫：舊名 vs 現名 ==")
    print("欄位：API 狀態｜git HEAD 是否相同｜ecosyste.ms 對舊名／現名的回應\n")
    rows = []
    for old, new in GH_PAIRS:
        a = resolve_github(*old.split("/"))
        b = resolve_github(*new.split("/"))
        same = (a.get("git_head") and a.get("git_head") == b.get("git_head"))
        line = {
            "old": old, "new": new, "api_old": a["api_status"], "api_loc": a.get("api_location"),
            "api_full_name": a.get("full_name") if a["method"] == "api" else None,
            "git_same_head": bool(same) if a["method"] == "fallback" else None,
            "eco_old": (a.get("ecosystems") or {}).get("full_name"),
            "eco_new": (b.get("ecosystems") or {}).get("full_name"),
            "eco_prev": (b.get("ecosystems") or {}).get("previous_names"),
            "eco_id": (b.get("ecosystems") or {}).get("uuid"),
        }
        rows.append(line)
        print(json.dumps(line, ensure_ascii=False))
    # deps.dev 對舊名與現名是否當成兩個專案
    print("\n== deps.dev 對舊名／現名 ==")
    for old, new in GH_PAIRS[:4]:
        out = []
        for n in (old, new):
            st, _, b = http("https://api.deps.dev/v3/projects/" + urllib.parse.quote(f"github.com/{n}", safe=""))
            key = json.loads(b)["projectKey"]["id"] if st == 200 else None
            stars = json.loads(b).get("starsCount") if st == 200 else None
            out.append(f"{n} → {st} {key} stars={stars}")
        print(" | ".join(out))
    print("\n== 不存在的 repo ==")
    print(json.dumps(resolve_github("pickfit-nonexistent-zz9", "nope"), ensure_ascii=False))
    return rows

# ---------------------------------------------------------------- 套件 → repo

def norm_label(label):  # PEP 753 / well-known project URLs 的正規化
    return re.sub(r"[\s!-/:-@\[-`{-~]", "", label).lower()


SOURCE_LABELS = ["source", "repository", "sourcecode", "github", "code", "sources", "git", "gitlab"]


def pypi_map(name):
    d = jget(f"https://pypi.org/pypi/{name}/json")
    if not d:
        return {"pkg": f"pypi:{name}", "error": "not found"}
    info = d["info"]
    urls = {norm_label(k): v for k, v in (info.get("project_urls") or {}).items()}
    declared, how = None, None
    for lab in SOURCE_LABELS:
        if lab in urls and canon(urls[lab])["kind"] == "repo":
            declared, how = canon(urls[lab]), f"project_urls[{lab}]"
            break
    if not declared:  # 退而求其次：任何一個看起來是 repo 的 URL
        order = sorted(urls.items(), key=lambda kv: kv[0] != "homepage")  # homepage 優先
        for k, v in order + [("home_page", info.get("home_page")), ("download_url", info.get("download_url"))]:
            if v and canon(v)["kind"] == "repo":
                declared, how = canon(v), f"fallback[{k}]"
                break
    # 簽章 provenance（Trusted Publishing）：PyPI Integrity API
    prov = None
    ver = info["version"]
    files = d.get("urls") or []
    if files:
        fn = files[0]["filename"]
        p = jget(f"https://pypi.org/integrity/{name}/{ver}/{urllib.parse.quote(fn)}/provenance",
                 {"Accept": "application/vnd.pypi.integrity.v1+json"})
        if p:
            try:
                pub = p["attestation_bundles"][0]["publisher"]
                if pub.get("kind") == "GitHub":
                    prov = canon("https://github.com/" + pub["repository"])
                elif pub.get("kind") == "GitLab":
                    prov = canon("https://gitlab.com/" + pub["repository"])
            except (KeyError, IndexError):
                pass
    row = _row(f"pypi:{name}", declared, how, prov)
    if declared and declared.get("subpath"):
        row["subpath"] = declared["subpath"]
    return row


def npm_map(name):
    d = jget("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@") + "/latest")
    if not d:
        return {"pkg": f"npm:{name}", "error": "not found"}
    rep = d.get("repository")
    declared, how, sub = None, None, None
    if isinstance(rep, str):
        declared, how = canon(rep, npm_shorthand=True), "repository(string)"
    elif isinstance(rep, dict) and rep.get("url"):
        declared, how, sub = canon(rep["url"], npm_shorthand=True), "repository.url", rep.get("directory")
    if (not declared or declared["kind"] != "repo") and d.get("homepage"):
        declared, how = canon(d["homepage"]), "homepage"
    prov = None
    att = (d.get("dist") or {}).get("attestations")
    if att and att.get("url"):
        a = jget(att["url"])
        for x in (a or {}).get("attestations", []):
            if "slsa.dev/provenance" not in x.get("predicateType", ""):
                continue
            try:
                payload = json.loads(base64.b64decode(x["bundle"]["dsseEnvelope"]["payload"]))
                wf = payload["predicate"]["buildDefinition"]["externalParameters"]["workflow"]
                prov = canon(wf["repository"])
            except (KeyError, ValueError):
                pass
    row = _row(f"npm:{name}", declared, how, prov)
    if sub:
        row["subpath"] = sub
    return row


def brew_map(name):
    d = jget(f"https://formulae.brew.sh/api/formula/{name}.json")
    if not d:
        return {"pkg": f"brew:{name}", "error": "not found"}
    cands = [("urls.head", ((d.get("urls") or {}).get("head") or {}).get("url")),
             ("urls.stable", ((d.get("urls") or {}).get("stable") or {}).get("url")),
             ("homepage", d.get("homepage"))]
    for how, u in cands:
        if u and canon(u)["kind"] == "repo":
            return _row(f"brew:{name}", canon(u), how, None)
    return _row(f"brew:{name}", canon(d.get("homepage") or ""), "homepage(非 repo)", None)


def _row(pkg, declared, how, prov):
    dk = declared["key"] if declared and declared["kind"] == "repo" else None
    pk = prov["key"] if prov else None
    return {"pkg": pkg, "declared": dk, "via": how, "provenance": pk,
            "agree": (dk == pk) if (dk and pk) else None,
            "rules": declared.get("rules") if declared else None}


PKGS = {
    "pypi": ["llm", "ruff", "aider-chat", "open-webui", "mlx-lm", "llama-cpp-python", "ollama", "httpie", "vllm", "pip",
             "flake8-to-ruff"],  # 最後一個：宣告的是改名前的 repo＋#subdirectory
    "npm": ["vite", "ollama", "@modelcontextprotocol/inspector", "npm-check-updates", "@openai/codex", "@google/gemini-cli", "zx", "tldr",
            "whisper.cpp"],  # 宣告的是轉移前的 ggerganov/whisper.cpp
    "brew": ["ripgrep", "llama.cpp", "ollama", "fzf", "gh", "lazygit", "aider", "whisper.cpp"],
}


def packages_cmd():
    rows = []
    for eco, names in PKGS.items():
        fn = {"pypi": pypi_map, "npm": npm_map, "brew": brew_map}[eco]
        for n in names:
            r = fn(n)
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False))
    # 宣告的 repo 是否已改名：對 GitHub 再解析一次
    print("\n== 宣告的 repo 指向舊名？（ecosyste.ms／API 解析） ==")
    seen = set()
    for r in rows:
        k = r.get("declared")
        if not k or not k.startswith("github.com/") or k in seen:
            continue
        seen.add(k)
        _, o, n = k.split("/")
        g = resolve_github(o, n)
        if g.get("renamed"):
            print(f"{r['pkg']}: {k} → 現名 {g.get('full_name')}（{g['method']}）")
        elif g["method"] == "fallback" and not g.get("ecosystems"):
            print(f"{r['pkg']}: {k} → 無法判定（ecosyste.ms 查無此名；git HEAD={str(g.get('git_head'))[:10]}）。需要 GitHub API 的 301 才能拿到現名")
    return rows


def recent_cmd():
    """PyPI 最新 40 個專案：對得到 repo 的比例、provenance 比例。"""
    st, hd, b = http("https://pypi.org/rss/packages.xml")
    items = ET.fromstring(b).findall("./channel/item")
    names = []
    for it in items:
        link = it.findtext("link") or ""
        m = re.search(r"/project/([^/]+)/", link)
        if m:
            names.append(m[1])
    rows = [pypi_map(n) for n in names]
    n = len(rows)
    has_repo = sum(1 for r in rows if r.get("declared"))
    gh = sum(1 for r in rows if (r.get("declared") or "").startswith("github.com/"))
    prov = sum(1 for r in rows if r.get("provenance"))
    agree = sum(1 for r in rows if r.get("agree"))
    fixed = sum(1 for r in rows if r.get("rules"))
    prov_only = sum(1 for r in rows if r.get("provenance") and not r.get("declared"))
    disagree = [r for r in rows if r.get("agree") is False]
    keys = [r.get("declared") or r.get("provenance") for r in rows]
    uniq = {k for k in keys if k}
    multi = {k: keys.count(k) for k in uniq if keys.count(k) > 1}
    print(f"PyPI RSS（etag {hd.get('etag')}）：{n} 個新專案")
    print(f"  宣告了 repo：{has_repo}（GitHub {gh}）")
    print(f"  有 Trusted Publishing provenance：{prov}；與宣告一致 {agree}；只有 provenance、沒宣告 {prov_only}；不一致 {len(disagree)}")
    print(f"  宣告或 provenance 任一對得到 repo：{sum(1 for k in keys if k)}／{n}；去重後 {len(uniq)} 個 repo；一個 repo 多個套件：{multi}")
    print(f"  宣告的 URL 需要正規化規則的：{fixed}")
    for r in disagree:
        print("  不一致：", json.dumps(r, ensure_ascii=False))
    for r in rows[:8]:
        print("  ", json.dumps(r, ensure_ascii=False))
    return rows


SHORT_SAMPLES = [  # 從 HN Algolia 撈到的真實短網址（2026-10-28）
    "https://t.co/GST3iLv3Zn", "http://lnkd.in/P9b4kD", "http://tinyurl.com/snakesonahyperplane",
    "https://git.io/JvoOi", "https://buff.ly/2iHXJNm"]


def short_cmd():
    print("== 短網址展開（手動逐跳，不自動 follow） ==")
    for u in SHORT_SAMPLES:
        hops = expand_short(canon(u)["url"])
        print(f"{' → '.join(hops)}  =>  {canon(hops[-1])['key']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("selftest", "all"):
        selftest()
        print()
    if cmd in ("github", "all"):
        github_cmd()
        print()
    if cmd in ("packages", "all"):
        packages_cmd()
        print()
    if cmd in ("short", "all"):
        short_cmd()
        print()
    if cmd in ("recent", "all"):
        recent_cmd()
