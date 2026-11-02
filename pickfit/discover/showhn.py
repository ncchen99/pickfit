"""Show HN discovery (P3.9): recent Show HN posts that point to a GitHub repository.

Two public APIs, no key:
- Algolia HN Search, the search behind the "Search" link on news.ycombinator.com:
  `search_by_date?tags=show_hn` with a created_at_i window, fetched one day at a time
  so no slice reaches its 1,000-hit page limit. Its API page limits each IP to 10,000
  requests an hour; a 60-day window takes 60.
- The HN Firebase API (MIT, no rate limit): `item/<id>.json` for each post that passes
  the filters, to drop posts deleted or killed after Algolia indexed them.

A post counts when its link, or failing that its text, names a GitHub repository, and
its title or text has words of one of pickfit's categories (CATEGORY_WORDS, written
from the category definitions: developer tools used from a terminal, software that
runs AI models on the user's own machine, Model Context Protocol servers). The repo
is then read through the GitHub REST API, which follows renames, so the candidate key
is `gh:<id>` and a repo already in the pool, under its current or an earlier name,
is the same candidate. A repo above the GitHub queries' star bound (STAR_MAX) is
left out, as the GitHub queries leave it out (submissions take any star count). The post only says where to look: a profile's facts still come
from the repository. What is kept of a post: its id and HN URL, title, link, points,
comment count and time; never its text or comments, which belong to their authors.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

from pickfit.discover.github import STARS, USER_AGENT, GitHub, GitHubError, normalize_repo, runs_dir
from pickfit.discover.store import CATEGORY_PRIORITY, PipelineDB, repo_key
from pickfit.ledger import taipei_date, taipei_now

CHANNEL = "show_hn"
ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"
FIREBASE = "https://hacker-news.firebaseio.com/v0"
HN_ITEM = "https://news.ycombinator.com/item?id={}"
DEFAULT_DAYS = 30
SLICE_S = 86_400
HITS_MAX = 1000  # Algolia returns at most this many hits for one query
TRIES = 3
REQUEST_INTERVAL_S = 0.2
FILTERS_VERSION = "show_hn.v1"
# The GitHub queries' default upper bound: discovery starts with newer tools few people know yet,
# to show such tools can be tested too. Submissions have no star limit.
# No lower bound: being shown on HN is the signal a star count gives the GitHub queries.
STAR_MAX = int(STARS.split("..")[1])

sleep = time.sleep  # tests replace this to skip waits

# --- Category filters ------------------------------------------------------------

# Written from the category definitions (schema.py, prescreen.py), not from any eval
# question: words a post uses to say it is that kind of software. Loose on purpose; the
# rules, the prescreen and extraction decide what the repo really is.
_MCP = re.compile(r"\bmcps?\b|model[- ]context[- ]protocol", re.I)
# Runs AI models on the user's own machine: a model word together with a local word, or a
# local runner, model file format or inference server named outright.
_MODEL = re.compile(r"\b(llms?|slms?|vlms?|language models?|models?|inference|embeddings?|"
                    r"speech[- ]to[- ]text|text[- ]to[- ]speech|tts|stt|asr|transcri(be|bes|bing|ption)|"
                    r"whisper|diffusion|open[- ]weights?)\b", re.I)
_LOCAL = re.compile(r"\b(local(ly)?|offline|on[- ]device|self[- ]host(ed|able)?|on[- ]prem(ise)?s?|"
                    r"air[- ]gapped|no cloud|without (the )?cloud|private|"
                    r"(on|from) (your|my) (own )?(machine|laptop|mac|pc|computer|gpu|hardware|phone|desktop|"
                    r"server|device)|(host|run) your own|apple silicon|cpu[- ]only|"
                    r"runs? on (a |the |your )?(cpu|gpu|raspberry pi|mac|laptop|phone))\b", re.I)
_RUNNER = re.compile(r"\b(ollama|llama\.?cpp|llama-server|llamafile|gguf|mlx|vllm|whisper\.cpp|onnx ?runtime|"
                     r"inference (servers?|engines?|runtimes?)|local[- ](llms?|models?|ai|inference))\b", re.I)
# Developer tools used from a terminal.
_CLI = re.compile(r"\b(cli|clis|tui|command[- ]line|terminal|shell|repl|"
                  r"(brew|cargo|pipx|go|uv tool) install|npm (i|install) -g)\b", re.I)


def post_categories(title: str, text: str = "") -> list[str]:
    """The categories a post's own words put it in, most specific first (CATEGORY_PRIORITY)."""
    words = f"{title}\n{text}"
    found = set()
    if _MCP.search(words):
        found.add("mcp_server")
    if _RUNNER.search(words) or (_MODEL.search(words) and _LOCAL.search(words)):
        found.add("local_ai")
    if _CLI.search(words):
        found.add("dev_cli")
    return [c for c in CATEGORY_PRIORITY if c in found]


# --- Which repository a post is about -----------------------------------------------

_GITHUB = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", re.I)
# github.com/<first segment> pages that are not an account.
_NOT_OWNERS = frozenset({
    "about", "apps", "blog", "collections", "contact", "customer-stories", "enterprise", "events",
    "explore", "features", "github-copilot", "issues", "join", "login", "marketplace", "new",
    "notifications", "orgs", "pricing", "pulls", "readme", "resources", "search", "security",
    "settings", "site", "solutions", "sponsors", "team", "topics", "trending",
})
_WORD = re.compile(r"[a-z0-9]+")


def _repos_in(text: str) -> list[str]:
    out = []
    for m in _GITHUB.finditer(text):
        owner, name = m.group(1), m.group(2).rstrip(".")
        name = name[:-4] if name.lower().endswith(".git") else name
        if owner.lower() in _NOT_OWNERS or not name:
            continue
        full = f"{owner}/{name}"
        if full.lower() not in (r.lower() for r in out):
            out.append(full)
    return out


def _squash(text: str) -> str:
    return "".join(_WORD.findall(text.lower()))


def linked_repo(title: str, url: str | None, text: str | None) -> str | None:
    """owner/name of the repository a post is about, or None.

    The post's link wins. A repo named only in the text counts when it is the only one
    there, or when its owner or name appears in the title: a text naming several repos
    may be pointing at what the project is built on.
    """
    in_url = _repos_in(url or "")
    if in_url:
        return in_url[0]
    in_text = _repos_in(text or "")
    if len(in_text) == 1:
        return in_text[0]
    squashed_title = _squash(title)
    for full in in_text:
        owner, name = full.split("/")
        if (len(_squash(name)) >= 3 and _squash(name) in squashed_title) or \
                (len(_squash(owner)) >= 3 and _squash(owner) in squashed_title):
            return full
    return None


def plain_text(story_text: str | None) -> str:
    """A post's HTML text as plain text (links keep their href, which holds the URL)."""
    text = html.unescape(story_text or "")
    text = re.sub(r"<a\s[^>]*href=\"([^\"]*)\"[^>]*>", r" \1 ", text)
    return re.sub(r"<[^>]+>", " ", text)


# --- Client ------------------------------------------------------------------------


class HNError(RuntimeError):
    """An HN API request failed after retries."""


class HN:
    """Algolia HN Search and the HN Firebase API: retries, request counts, a request trace."""

    def __init__(self, *, http: httpx2.Client | None = None, trace_dir: Path | None = None,
                 interval_s: float = REQUEST_INTERVAL_S) -> None:
        self._http = http or httpx2.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})
        self._trace_dir = trace_dir or runs_dir() / "traces"
        self._interval = interval_s
        self.requests: Counter[str] = Counter()

    def close(self) -> None:
        self._http.close()

    def _get(self, kind: str, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(1, TRIES + 1):
            self.requests[kind] += 1
            started = time.monotonic()
            ran_at = taipei_now().isoformat(timespec="seconds")
            try:
                resp = self._http.get(url, params=params)
                status: int | str = resp.status_code
            except httpx2.TransportError as err:
                resp, status = None, type(err).__name__
            self._trace({"ts": ran_at, "kind": kind, "url": url, "params": params, "status": status,
                         "latency_s": round(time.monotonic() - started, 3)})
            if resp is not None and resp.status_code == 200:
                return resp.json()
            if resp is not None and resp.status_code < 500 and resp.status_code != 429:
                raise HNError(f"GET {url}: HTTP {resp.status_code}")
            if attempt < TRIES:
                sleep(2.0 * attempt)
        raise HNError(f"GET {url}: {status} after {TRIES} tries")

    def show_hn(self, since: int, until: int) -> Iterator[dict[str, Any]]:
        """Every Show HN post with since < created_at_i <= until, one day per request."""
        t = since
        while t < until:
            t2 = min(t + SLICE_S, until)
            yield from self._slice(t, t2)
            t = t2

    def _slice(self, t1: int, t2: int) -> Iterator[dict[str, Any]]:
        params = {"tags": "show_hn", "numericFilters": f"created_at_i>{t1},created_at_i<={t2}",
                  "hitsPerPage": HITS_MAX}
        sleep(self._interval)
        data = self._get("algolia", ALGOLIA, params)
        if (data.get("nbHits") or 0) > HITS_MAX and t2 - t1 > 60:
            mid = (t1 + t2) // 2  # a busier day than Algolia pages: split it
            yield from self._slice(t1, mid)
            yield from self._slice(mid, t2)
            return
        yield from data.get("hits") or []

    def item(self, item_id: str) -> dict[str, Any] | None:
        return self._get("firebase", f"{FIREBASE}/item/{item_id}.json")

    def _trace(self, record: dict[str, Any]) -> None:
        path = self._trace_dir / f"hn-{taipei_date()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)


# --- The channel ---------------------------------------------------------------------


@dataclass
class Post:
    item_id: str
    title: str
    link: str | None
    points: int
    comments: int
    posted_at: str
    repo: str | None
    categories: list[str]

    @property
    def hn_url(self) -> str:
        return HN_ITEM.format(self.item_id)


@dataclass
class ShowHNStats:
    posts: int = 0
    github: int = 0
    categorized: int = 0
    by_outcome: Counter[str] = field(default_factory=Counter)
    new: int = 0
    known: int = 0
    by_category: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        """Posts at each filter, then distinct repos: new to the pool or already in it."""
        return {"posts": self.posts, "github_repo": self.github, "category_words": self.categorized,
                "by_outcome": dict(self.by_outcome), "repos_new": self.new,
                "repos_known": self.known, "repos_by_category": dict(self.by_category)}


def to_post(hit: dict[str, Any]) -> Post:
    title = hit.get("title") or ""
    text = plain_text(hit.get("story_text"))
    return Post(item_id=str(hit["objectID"]), title=title, link=hit.get("url") or None,
                points=int(hit.get("points") or 0), comments=int(hit.get("num_comments") or 0),
                posted_at=datetime.fromtimestamp(int(hit["created_at_i"]), UTC).isoformat(timespec="seconds"),
                repo=linked_repo(title, hit.get("url"), text), categories=post_categories(title, text))


def window(now: datetime, days: int) -> tuple[int, int]:
    until = int(now.timestamp())
    return until - days * SLICE_S, until


def describe_query(since: int, until: int, category: str) -> str:
    """The queries-table text: the exact Algolia filter, the window in UTC, and the post filter."""
    iso = lambda t: datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%MZ")  # noqa: E731
    return (f"hn.algolia.com search_by_date tags=show_hn numericFilters=created_at_i>{since},"
            f"created_at_i<={until} ({iso(since)}..{iso(until)}); link or text names a GitHub repo; "
            f"{category} words in title or text ({FILTERS_VERSION})")


def search_show_hn(gh: GitHub, db: PipelineDB, hn: HN, *, now: datetime, days: int,
                   categories: list[str] | None, run_id: str,
                   log: Callable[[str], None]) -> ShowHNStats:
    """Fetch the window's Show HN posts, keep those that point to a repo in a wanted category,
    and add each repo to the candidate pool with the post as its provenance."""
    since, until = window(now, days)
    ran_at = taipei_now().isoformat(timespec="seconds")
    wanted = set(categories or CATEGORY_PRIORITY)
    stats = ShowHNStats()
    posts = [to_post(hit) for hit in hn.show_hn(since, until)]
    stats.posts = len(posts)
    linked = [p for p in posts if p.repo]
    stats.github = len(linked)
    for p in linked:
        p.categories = [c for c in p.categories if c in wanted]
    kept = [p for p in linked if p.categories]
    stats.categorized = len(kept)
    log(f"show_hn: {stats.posts} posts in {days} days, {stats.github} name a GitHub repo, "
        f"{stats.categorized} with category words")

    # Current and earlier names of every candidate already in the pool, lowercased.
    names = db.names_index()
    resolved: dict[str, dict[str, Any] | None] = {}
    known_before: dict[str, bool] = {}  # repo key -> was it in the pool before this run
    returned: Counter[str] = Counter()
    new_by_category: Counter[str] = Counter()
    for i, p in enumerate(sorted(kept, key=lambda p: p.posted_at), 1):
        if i % 50 == 0:
            log(f"show_hn: {i}/{len(kept)} posts checked")
        item = hn.item(p.item_id)
        if not item or item.get("dead") or item.get("deleted"):
            db.save_channel_hit(channel=CHANNEL, post=p, repo_id=None, outcome="dead_or_deleted",
                                known_before=None, run_id=run_id)
            stats.by_outcome["dead_or_deleted"] += 1
            continue
        p.points = int(item.get("score") or p.points)
        p.comments = int(item.get("descendants") or p.comments)
        lookup = p.repo.lower()
        named_id = names.get(lookup)
        if lookup not in resolved:
            try:
                resolved[lookup] = gh.repo(p.repo)  # follows a rename to the current name
            except GitHubError as err:
                log(f"show_hn: {p.repo}: {err}")
                resolved[lookup] = None
        data = resolved[lookup]
        if data is None or not data.get("id"):
            db.save_channel_hit(channel=CHANNEL, post=p, repo_id=named_id, outcome="repo_missing",
                                known_before=named_id is not None, run_id=run_id)
            stats.by_outcome["repo_missing"] += 1
            continue
        repo = normalize_repo(data)
        key = repo_key(repo["id"])
        if (repo.get("stargazers_count") or 0) > STAR_MAX:
            db.save_channel_hit(channel=CHANNEL, post=p, repo_id=key, outcome="too_popular",
                                known_before=named_id is not None or db.candidate(key) is not None,
                                run_id=run_id)
            stats.by_outcome["too_popular"] += 1
            continue
        first_time = key not in known_before
        if first_time:
            known_before[key] = named_id is not None or db.candidate(key) is not None
        for category in p.categories:
            if db.upsert_repo(repo, category=category, query_id=f"{CHANNEL}:{category}"):
                new_by_category[category] += 1
            returned[category] += 1
        names[repo["full_name"].lower()] = key
        db.save_channel_hit(channel=CHANNEL, post=p, repo_id=key, outcome="candidate",
                            known_before=known_before[key], run_id=run_id)
        stats.by_outcome["candidate"] += 1
        if first_time:
            stats.by_category[p.categories[0]] += 1
            if known_before[key]:
                stats.known += 1
            else:
                stats.new += 1
    for category in sorted(wanted, key=CATEGORY_PRIORITY.index):
        db.log_query(run_id=run_id, query_id=f"{CHANNEL}:{category}", category=category,
                     q=describe_query(since, until, category), ran_at=ran_at, total_count=stats.posts,
                     returned=returned[category], new=new_by_category[category])
        log(f"search {CHANNEL}:{category}: {returned[category]} posts with a repo, "
            f"new {new_by_category[category]}")
    log(f"show_hn: {stats.to_dict()}")
    return stats
