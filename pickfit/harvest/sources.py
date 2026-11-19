"""Harvest sources. Each is a function (ctx) -> iterator of Hit, bounded by ctx.limit.

Only APIs a source offers for this use, with pickfit's User-Agent; terms are in
docs/research/harvest-sources.md. Keyless sources run by default; the social ones (Bluesky, X)
run only when their keys are set, and X only within ctx.x_max_reads paid reads.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2

from pickfit.discover.github import USER_AGENT, GitHub, GitHubError, Query
from pickfit.harvest.leads import Hit, LeadsDB

sleep = time.sleep  # tests replace this


class SourceError(RuntimeError):
    """A source could not be read; the run records it and goes on with the others."""


@dataclass
class Ctx:
    db: LeadsDB
    http: httpx2.Client
    gh: GitHub | None
    now: datetime
    log: Callable[[str], None]
    env: dict[str, str] = field(default_factory=dict)
    limit: int = 5000  # hits per source per run
    days: int = 7  # look-back window of the time-sliced sources
    x_max_reads: int = 100  # paid X post reads per run ($0.005 each)
    requests: Counter[str] = field(default_factory=Counter)

    def get(self, source: str, url: str, *, params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None, tries: int = 3, interval_s: float = 0.0) -> httpx2.Response:
        """GET with retries on 429/5xx; raises SourceError on anything else that is not 200."""
        for attempt in range(1, tries + 1):
            if interval_s:
                sleep(interval_s)
            self.requests[source] += 1
            try:
                resp = self.http.get(url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})},
                                     follow_redirects=True)
            except httpx2.TransportError as err:
                if attempt == tries:
                    raise SourceError(f"{source}: GET {url}: {type(err).__name__}") from None
                sleep(2.0 * attempt)
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < tries:
                retry = resp.headers.get("retry-after")
                sleep(min(60.0, float(retry)) if retry and retry.isdigit() else 5.0 * attempt)
                continue
            raise SourceError(f"{source}: GET {url}: HTTP {resp.status_code}")
        raise SourceError(f"{source}: GET {url}: no response")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Official MCP Registry ---------------------------------------------------------------------
# registry.modelcontextprotocol.io: an unauthenticated read-only API meant for aggregators, who are
# expected to sync about hourly and use updated_since after the first full download.

MCP_REGISTRY = "https://registry.modelcontextprotocol.io/v0.1/servers"


def mcp_registry(ctx: Ctx) -> Iterator[Hit]:
    checkpoint = ctx.db.get_state("mcp_registry.updated_since")
    started = _iso(ctx.now - timedelta(minutes=10))  # small overlap with the next window
    cursor = None
    n = 0
    while n < ctx.limit:
        params: dict[str, Any] = {"limit": 100, "version": "latest"}
        if checkpoint:
            params["updated_since"] = checkpoint
        if cursor:
            params["cursor"] = cursor
        data = ctx.get("mcp_registry", MCP_REGISTRY, params=params, headers={"Accept-Encoding": "gzip"}).json()
        for entry in data.get("servers") or []:
            server = entry.get("server") or {}
            official = (entry.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
            if official.get("status") in ("deleted", "deprecated"):
                continue
            name = server.get("name") or ""
            repo = (server.get("repository") or {}).get("url")
            n += 1
            yield Hit("mcp_registry", name, [repo, server.get("websiteUrl")], title=server.get("title") or name,
                      link=f"{MCP_REGISTRY}/{urllib.parse.quote(name, safe='')}/versions/latest",
                      kind_hint="mcp_server")
        cursor = (data.get("metadata") or {}).get("nextCursor")
        if not cursor:
            ctx.db.set_state("mcp_registry.updated_since", started)
            return


# --- npm registry search -----------------------------------------------------------------------
# The registry's search endpoint (what `npm search` calls), not the npmjs.com website.

NPM_SEARCH = "https://registry.npmjs.org/-/v1/search"
NPM_QUERIES = (("keywords:mcp-server", "mcp_server"), ("keywords:mcp", "mcp_server"),
               ("keywords:modelcontextprotocol", "mcp_server"), ("keywords:cli keywords:tool", "cli_tool"),
               ("keywords:tui", "tui"))
NPM_PAGE = 250
NPM_MAX_FROM = 5000


def npm(ctx: Ctx) -> Iterator[Hit]:
    n = 0
    for text, kind in NPM_QUERIES:
        start = 0
        while start < NPM_MAX_FROM and n < ctx.limit:
            data = ctx.get("npm", NPM_SEARCH, params={"text": text, "size": NPM_PAGE, "from": start},
                           interval_s=0.5).json()
            objects = data.get("objects") or []
            for obj in objects:
                pkg = obj.get("package") or {}
                links = pkg.get("links") or {}
                downloads = (obj.get("downloads") or {}).get("monthly")
                n += 1
                yield Hit("npm", pkg.get("name", ""), [links.get("repository"), links.get("homepage")],
                          title=pkg.get("description") or pkg.get("name"), link=links.get("npm"),
                          signal=float(downloads) if isinstance(downloads, (int, float)) else None, kind_hint=kind)
            if len(objects) < NPM_PAGE:
                break
            start += NPM_PAGE


# --- crates.io ---------------------------------------------------------------------------------
# crates.io's crawler policy: at most one request a second, with a User-Agent that names the client.

CRATES = "https://crates.io/api/v1/crates"
CRATES_QUERIES = (({"category": "command-line-utilities", "sort": "new"}, "cli_tool"),
                  ({"category": "command-line-utilities", "sort": "recent-downloads"}, "cli_tool"),
                  ({"keyword": "tui", "sort": "recent-downloads"}, "tui"),
                  ({"keyword": "mcp", "sort": "new"}, "mcp_server"),
                  ({"keyword": "mcp-server", "sort": "new"}, "mcp_server"))
CRATES_PAGES = 10


def crates(ctx: Ctx) -> Iterator[Hit]:
    n = 0
    for params, kind in CRATES_QUERIES:
        for page in range(1, CRATES_PAGES + 1):
            if n >= ctx.limit:
                return
            data = ctx.get("crates", CRATES, params={**params, "per_page": 100, "page": page}, interval_s=1.0).json()
            items = data.get("crates") or []
            for c in items:
                n += 1
                yield Hit("crates", c["id"], [c.get("repository"), c.get("homepage")],
                          title=c.get("description") or c["id"], link=f"https://crates.io/crates/{c['id']}",
                          signal=float(c.get("recent_downloads") or 0), kind_hint=kind)
            if len(items) < 100:
                break


# --- Homebrew formulae -------------------------------------------------------------------------
# formulae.brew.sh JSON API (BSD-2-Clause, no key); installs only rank the leads.

BREW_FORMULA = "https://formulae.brew.sh/api/formula.json"
BREW_INSTALLS = "https://formulae.brew.sh/api/analytics/install-on-request/30d.json"


def homebrew(ctx: Ctx) -> Iterator[Hit]:
    formulae = ctx.get("homebrew", BREW_FORMULA).json()
    installs: dict[str, float] = {}
    try:
        for item in (ctx.get("homebrew", BREW_INSTALLS).json().get("items") or []):
            installs[item.get("formula", "")] = float(str(item.get("count", "0")).replace(",", "") or 0)
    except (SourceError, ValueError):
        pass
    for n, f in enumerate(formulae):
        if n >= ctx.limit:
            return
        if f.get("deprecated") or f.get("disabled"):
            continue
        urls = f.get("urls") or {}
        yield Hit("homebrew", f["name"], [(urls.get("head") or {}).get("url"), (urls.get("stable") or {}).get("url"),
                                          f.get("homepage")],
                  title=f.get("desc") or f["name"], link=f"https://formulae.brew.sh/formula/{f['name']}",
                  signal=installs.get(f["name"]), kind_hint="cli_tool", platforms=["macos", "linux"])


# --- winget (Windows) --------------------------------------------------------------------------
# microsoft/winget-pkgs (MIT) through the GitHub API: "New package" commits, then the package's
# default-locale manifest for the URLs it names.

WINGET_REPO = "microsoft/winget-pkgs"
_WINGET_NEW = re.compile(r"New package:\s+([A-Za-z0-9][\w.+-]*?)\s+version\s+(\S+?)(?:\s|$)")
_YAML_URL = re.compile(r"^(PackageUrl|PublisherUrl|LicenseUrl|ReleaseNotesUrl|PublisherSupportUrl):\s*(\S+)", re.M)
_YAML_DESC = re.compile(r"^ShortDescription:\s*(.+)$", re.M)


def winget(ctx: Ctx) -> Iterator[Hit]:
    if ctx.gh is None:
        raise SourceError("winget: needs GH_TOKEN")
    since = (ctx.now - timedelta(days=ctx.days)).date().isoformat()
    q = f'repo:{WINGET_REPO} "New package" committer-date:>={since}'
    seen: set[str] = set()
    for page in range(1, 11):
        resp = ctx.gh._get("search", "/search/commits", {"q": q, "per_page": 100, "page": page,
                                                          "sort": "committer-date", "order": "desc"})
        items = (resp.json().get("items") if resp is not None else None) or []
        for item in items:
            if len(seen) >= ctx.limit:
                return
            m = _WINGET_NEW.search((item.get("commit") or {}).get("message") or "")
            if not m or m.group(1) in seen:
                continue
            pkg, version = m.group(1), m.group(2)
            seen.add(pkg)
            path = f"manifests/{pkg[0].lower()}/{pkg.replace('.', '/')}/{version}/{pkg}.locale.en-US.yaml"
            try:
                text = ctx.get("winget", f"https://raw.githubusercontent.com/{WINGET_REPO}/master/{path}").text
            except SourceError:
                continue
            urls = [u for _, u in _YAML_URL.findall(text)]
            desc = _YAML_DESC.search(text)
            yield Hit("winget", pkg, urls, title=desc.group(1).strip() if desc else pkg,
                      link=f"https://github.com/{WINGET_REPO}/tree/master/{path.rsplit('/', 1)[0]}",
                      platforms=["windows"])
        if len(items) < 100:
            return
        sleep(2.0)


# --- Awesome lists ----------------------------------------------------------------------------
# Only the GitHub links a list names (facts); never its descriptions. (repo, kind, platforms)

AWESOME_LISTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("punkpeye/awesome-mcp-servers", "mcp_server", ()),
    ("appcypher/awesome-mcp-servers", "mcp_server", ()),
    ("wong2/awesome-mcp-servers", "mcp_server", ()),
    ("hesreallyhim/awesome-claude-code", "unknown", ()),
    ("rothgar/awesome-tuis", "tui", ()),
    ("agarrharr/awesome-cli-apps", "cli_tool", ()),
    ("toolleeo/awesome-cli-apps-in-a-csv", "cli_tool", ()),
    ("awesome-selfhosted/awesome-selfhosted", "self_hosted_web_app", ()),
    ("luong-komorebi/Awesome-Linux-Software", "desktop_app", ("linux",)),
    ("jaywcjlove/awesome-mac", "desktop_app", ("macos",)),
    ("serhii-londar/open-source-mac-os-apps", "desktop_app", ("macos",)),
    ("Awesome-Windows/Awesome", "desktop_app", ("windows",)),
    ("tauri-apps/awesome-tauri", "desktop_app", ()),
    ("RunaCapital/awesome-oss-alternatives", "unknown", ()),
    ("EndoTheDev/awesome-ollama", "local_ai", ()),
    ("vince-lam/awesome-local-llms", "local_ai", ()),
)


def awesome(ctx: Ctx) -> Iterator[Hit]:
    from pickfit.discover.showhn import _repos_in
    if ctx.gh is None:
        raise SourceError("awesome: needs GH_TOKEN")
    n = 0
    for repo, kind, platforms in AWESOME_LISTS:
        try:
            resp = ctx.gh._get("readme", f"/repos/{repo}/readme", accept="application/vnd.github.raw")
        except GitHubError as err:
            ctx.log(f"  awesome {repo}: {err}")
            continue
        if resp is None:
            ctx.log(f"  awesome {repo}: no README")
            continue
        for full in _repos_in(resp.text):
            if full.lower() == repo.lower() or full.split("/")[1].lower().startswith("awesome"):
                continue
            n += 1
            if n > ctx.limit:
                return
            yield Hit("awesome", f"{repo}:{full}", [f"https://github.com/{full}"], title=None,
                      link=f"https://github.com/{repo}", kind_hint=kind, platforms=list(platforms))


# --- GitHub: new and rising -------------------------------------------------------------------
# What a trending page shows, computed from the search API: created in the window, already starred.

RISING_TOPICS = (("mcp", "mcp_server"), ("mcp-server", "mcp_server"), ("model-context-protocol", "mcp_server"),
                 ("cli", "cli_tool"), ("command-line", "cli_tool"), ("tui", "tui"), ("terminal", "cli_tool"),
                 ("self-hosted", "self_hosted_web_app"), ("web-app", "web_app"), ("pwa", "web_app"),
                 ("browser-extension", "unknown"), ("desktop-app", "desktop_app"), ("tauri", "desktop_app"),
                 ("electron", "desktop_app"), ("linux", "unknown"), ("macos", "desktop_app"),
                 ("windows", "desktop_app"), ("local-llm", "local_ai"), ("ollama", "local_ai"),
                 ("ai-agent", "unknown"), ("claude-code", "unknown"), ("agentic", "unknown"),
                 ("developer-tools", "cli_tool"), ("productivity", "unknown"), ("open-source-alternative", "unknown"))
RISING_MIN_STARS = 50
RISING_DAYS = 45
_PLATFORM_TOPICS = {"linux": "linux", "macos": "macos", "windows": "windows"}


def github_rising(ctx: Ctx) -> Iterator[Hit]:
    if ctx.gh is None:
        raise SourceError("github_rising: needs GH_TOKEN")
    created = (ctx.now - timedelta(days=RISING_DAYS)).date().isoformat()
    n = 0
    for topic, kind in RISING_TOPICS:
        q = f"topic:{topic} created:>={created} stars:>={RISING_MIN_STARS} fork:false archived:false"
        data = ctx.gh.search_repositories(Query("harvest", topic, q), per_page=100, sort="stars")
        for item in data.get("items") or []:
            n += 1
            if n > ctx.limit:
                return
            platform = _PLATFORM_TOPICS.get(topic)
            yield Hit("github_rising", item["full_name"], [item["html_url"]], title=item.get("description"),
                      link=item["html_url"], signal=float(item.get("stargazers_count") or 0), kind_hint=kind,
                      platforms=[platform] if platform else [])


# --- Hacker News (all stories, not only Show HN) ----------------------------------------------

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
HN_MIN_POINTS = 20


def hacker_news(ctx: Ctx) -> Iterator[Hit]:
    end = int(ctx.now.timestamp())
    n = 0
    for day in range(ctx.days):
        hi, lo = end - day * 86_400, end - (day + 1) * 86_400
        data = ctx.get("hn", ALGOLIA, params={"tags": "story", "hitsPerPage": 1000,
                                              "numericFilters": f"created_at_i>{lo},created_at_i<={hi},"
                                                                f"points>={HN_MIN_POINTS}"},
                       interval_s=0.2).json()
        for hit in data.get("hits") or []:
            url = hit.get("url") or ""
            show = "show_hn" in (hit.get("_tags") or [])
            if "github.com" not in url and not show:
                continue
            n += 1
            if n > ctx.limit:
                return
            # A Show HN post that links a site (not a repository) may be a web app; the web lane decides.
            yield Hit("hn", str(hit["objectID"]), [url], title=hit.get("title"),
                      link=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                      signal=float(hit.get("points") or 0), kind_hint="web_app" if show and "github.com" not in url
                      else "unknown", allow_web=show)


# --- Bluesky (needs BSKY_HANDLE and BSKY_APP_PASSWORD) -----------------------------------------
# searchPosts through the account's PDS. Kept: the post's URI, its link and like count; not its text.

BSKY = "https://bsky.social/xrpc"
BSKY_QUERIES = ("github.com mcp", "github.com cli", "github.com tui", "github.com self-hosted",
                "github.com open source", "github.com \"built with claude\"", "#buildinpublic github.com",
                "github.com \"alternative to\"", "github.com local llm", "github.com web app")


def _bsky_links(post: dict[str, Any]) -> list[str]:
    record = post.get("record") or {}
    links = [f.get("uri") for facet in record.get("facets") or [] for f in facet.get("features") or []
             if f.get("$type") == "app.bsky.richtext.facet#link"]
    external = ((post.get("embed") or {}).get("external") or {}).get("uri")
    return [u for u in [*links, external] if u]


def bluesky(ctx: Ctx) -> Iterator[Hit]:
    handle, password = ctx.env.get("BSKY_HANDLE"), ctx.env.get("BSKY_APP_PASSWORD")
    if not handle or not password:
        raise SourceError("bluesky: BSKY_HANDLE and BSKY_APP_PASSWORD are not set")
    ctx.requests["bluesky"] += 1
    resp = ctx.http.post(f"{BSKY}/com.atproto.server.createSession",
                         json={"identifier": handle, "password": password}, headers={"User-Agent": USER_AGENT})
    if resp.status_code != 200:
        raise SourceError(f"bluesky: sign-in failed: HTTP {resp.status_code}")
    auth = {"Authorization": f"Bearer {resp.json()['accessJwt']}"}
    since = _iso(ctx.now - timedelta(days=ctx.days))
    n = 0
    for q in BSKY_QUERIES:
        cursor = None
        for _ in range(5):
            params = {"q": q, "sort": "top", "since": since, "limit": 100, **({"cursor": cursor} if cursor else {})}
            data = ctx.get("bluesky", f"{BSKY}/app.bsky.feed.searchPosts", params=params, headers=auth,
                           interval_s=0.5).json()
            for post in data.get("posts") or []:
                urls = _bsky_links(post)
                if not any("github.com" in u for u in urls):
                    continue
                n += 1
                if n > ctx.limit:
                    return
                rkey = post["uri"].rsplit("/", 1)[-1]
                author = (post.get("author") or {}).get("handle", "")
                yield Hit("bluesky", post["uri"], urls, link=f"https://bsky.app/profile/{author}/post/{rkey}",
                          signal=float((post.get("likeCount") or 0) + (post.get("repostCount") or 0)))
            cursor = data.get("cursor")
            if not cursor:
                break


# --- X (needs X_BEARER_TOKEN; pay per read) ---------------------------------------------------
# Recent search (last 7 days). Each returned post is a paid read, so the run stops at x_max_reads. The API has no
# min_faves, and sorted by recency almost every post is minutes old with no likes yet (11/19: 100 reads, 2 kept),
# so the search is sorted by relevancy, which puts posts people engaged with first.
# Kept: the post id, its link and like count; not its text (X's developer terms limit storing it).

X_SEARCH = "https://api.x.com/2/tweets/search/recent"
X_QUERIES = ('url:"github.com" (mcp OR "mcp server") -is:retweet lang:en',
             'url:"github.com" ("open source" OR "open-source") ("alternative to" OR alternative) -is:retweet',
             'url:"github.com" ("built with claude" OR "claude code" OR agentic) -is:retweet',
             'url:"github.com" (cli OR tui OR terminal) -is:retweet lang:en',
             'url:"github.com" #buildinpublic -is:retweet')
X_MIN_LIKES = 10


def x_posts(ctx: Ctx) -> Iterator[Hit]:
    token = ctx.env.get("X_BEARER_TOKEN")
    if not token:
        raise SourceError("x: X_BEARER_TOKEN is not set")
    reads = 0
    per_query = max(10, ctx.x_max_reads // len(X_QUERIES))
    for q in X_QUERIES:
        if reads >= ctx.x_max_reads:
            break
        take = min(100, per_query, ctx.x_max_reads - reads)
        if take < 10:  # the API's minimum page
            break
        data = ctx.get("x", X_SEARCH, params={"query": q, "max_results": take, "sort_order": "relevancy",
                                              "tweet.fields": "public_metrics,entities,created_at"},
                       headers={"Authorization": f"Bearer {token}"}).json()
        posts = data.get("data") or []
        reads += len(posts)
        for post in posts:
            likes = (post.get("public_metrics") or {}).get("like_count") or 0
            if likes < X_MIN_LIKES:
                continue
            urls = [u.get("unwound_url") or u.get("expanded_url")
                    for u in (post.get("entities") or {}).get("urls") or []]
            yield Hit("x", post["id"], [u for u in urls if u], link=f"https://x.com/i/web/status/{post['id']}",
                      signal=float(likes))
    ctx.log(f"  x: {reads} paid reads (about ${reads * 0.005:.2f})")


SOURCES: dict[str, Callable[[Ctx], Iterator[Hit]]] = {
    "mcp_registry": mcp_registry,
    "npm": npm,
    "crates": crates,
    "homebrew": homebrew,
    "winget": winget,
    "awesome": awesome,
    "github_rising": github_rising,
    "hn": hacker_news,
    "bluesky": bluesky,
    "x": x_posts,
}
# Run by default: keyless, or only GH_TOKEN. The social ones need their own keys.
DEFAULT_SOURCES = ("mcp_registry", "npm", "crates", "homebrew", "winget", "awesome", "github_rising", "hn")
