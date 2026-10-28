"""GitHub discovery: topic searches per category, then README, releases and files per repo.

The search API allows 30 requests a minute, so searches run one at a time, at
least SEARCH_INTERVAL_S apart, and each one is logged with its query string and
time to runs/traces/github-<Taipei date>.jsonl. Everything else uses the REST
API (5,000 requests an hour). The token comes from GH_TOKEN or GITHUB_TOKEN,
e.g. `GH_TOKEN=$(gh auth token) uv run pickfit discover`; it is sent only in the
Authorization header and never reaches a trace or an error message.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.parse
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx2

from pickfit.env import REPO_ROOT, get_env, read_env
from pickfit.ledger import taipei_date, taipei_now

API = "https://api.github.com"
USER_AGENT = "pickfit/0.1 (+https://github.com/ncchen99/pickfit)"
SEARCH_INTERVAL_S = 2.1
SEARCH_PAGE_MAX = 100  # per_page limit of the search API
SEARCH_RESULTS_MAX = 1000  # the search API never returns more than this per query
RELEASES_PER_REPO = 10
README_MAX_CHARS = 200_000
# Root files that show whether a repo installs an executable (rules.py reads them).
MANIFESTS = ("package.json", "pyproject.toml", "Cargo.toml", "setup.cfg")

# Waits (seconds) for rate limits and server errors; a reset further away than
# RATE_LIMIT_MAX_WAIT_S fails the run instead of stalling it.
RATE_LIMIT_MAX_WAIT_S = 900.0
SECONDARY_LIMIT_WAIT_S = 60.0
SERVER_ERROR_TRIES = 3
# 404: missing; 409: empty repository; 451: blocked for legal reasons.
_ABSENT = {404, 409, 451}

sleep = time.sleep  # tests replace these to skip waits
monotonic = time.monotonic

# --- Queries -----------------------------------------------------------------

# Topics per demo category (brief section 14). Written from the category
# definitions alone, not from the eval questions (eval/README.md section 3).
# "a+b" means a repo must carry both topics.
TOPICS: dict[str, tuple[str, ...]] = {
    "dev_cli": ("cli", "tui", "terminal"),
    "local_ai": (
        "local-llm", "ollama", "llama-cpp",
        # Added 2026-10-29 from the same definition ("local model runners, inference
        # servers, offline AI tools"); the first three found few CLI or server tools.
        # Model runners and their file format:
        "gguf", "llamacpp", "local-inference", "llm-inference",
        # Inference servers:
        "inference-server", "inference-engine",
        # Offline AI tools, including offline speech:
        "local-ai", "offline-ai", "llm+offline", "whisper-cpp", "speech-to-text+offline",
        "text-to-speech+offline",
        # Command-line front ends to a local runner:
        "ollama+cli",
    ),
}
STARS = "5..300"
PUSHED_DAYS = 14
# Created this year, pushed recently, a few stars but not famous, not a fork, not archived.
QUERY_TEMPLATE = ("{topics} created:>={created} pushed:>={pushed} stars:{stars} "
                  "fork:false archived:false")
# Most recently updated first: recent activity says something about maintenance;
# sorting by stars would rank by popularity, which is what pickfit tries not to do.
SORT = "updated"


@dataclass(frozen=True)
class Query:
    category: str
    topic: str
    q: str

    @property
    def id(self) -> str:
        return f"{self.category}:{self.topic}"


def build_queries(today: date, *, pushed_days: int = PUSHED_DAYS,
                  categories: list[str] | None = None) -> list[Query]:
    """The search queries for `today` (UTC date), with concrete dates filled in."""
    created = date(today.year, 1, 1).isoformat()
    pushed = (today - timedelta(days=pushed_days)).isoformat()
    unknown = set(categories or []) - TOPICS.keys()
    if unknown:
        raise ValueError(f"unknown categories {sorted(unknown)}; expected {sorted(TOPICS)}")
    return [Query(category, topic, QUERY_TEMPLATE.format(
                topics=" ".join(f"topic:{t}" for t in topic.split("+")), created=created,
                pushed=pushed, stars=STARS))
            for category, topics in TOPICS.items() if categories is None or category in categories
            for topic in topics]


# --- Client --------------------------------------------------------------------


class GitHubError(RuntimeError):
    """A GitHub request failed in a way retrying will not fix."""


def github_token() -> str:
    token = read_env(["GH_TOKEN", "GITHUB_TOKEN"])
    value = token.get("GH_TOKEN") or token.get("GITHUB_TOKEN")
    if not value:
        raise GitHubError("GH_TOKEN is not set; run with GH_TOKEN=$(gh auth token)")
    return value


def runs_dir() -> Path:
    """runs/ (PICKFIT_RUNS_DIR overrides), the same directory call_meta traces to."""
    return Path(get_env("PICKFIT_RUNS_DIR") or REPO_ROOT / "runs")


class GitHub:
    """A small GitHub REST client: throttled search, retries, request counts, search trace."""

    def __init__(self, token: str, *, http: httpx2.Client | None = None,
                 trace_dir: Path | None = None, search_interval_s: float = SEARCH_INTERVAL_S) -> None:
        self._http = http or httpx2.Client(base_url=API, timeout=30.0)
        self._headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT,
                         "X-GitHub-Api-Version": "2022-11-28"}
        self._token = token
        self._trace_dir = trace_dir or runs_dir() / "traces"
        self._interval = search_interval_s
        self._search_lock = threading.Lock()
        self._last_search: float | None = None
        self._count_lock = threading.Lock()
        self.requests: Counter[str] = Counter()

    def close(self) -> None:
        self._http.close()

    # -- transport

    def _get(self, kind: str, path: str, params: dict[str, Any] | None = None,
             accept: str = "application/vnd.github+json") -> httpx2.Response | None:
        """GET with retries; None when the resource does not exist (404, 409, 451)."""
        server_errors = 0
        while True:
            with self._count_lock:
                self.requests[kind] += 1
            try:
                # A renamed or transferred repo answers 301 to its old owner/name.
                resp = self._http.get(path, params=params, headers={**self._headers, "Accept": accept},
                                      follow_redirects=True)
            except httpx2.TransportError as err:
                server_errors += 1
                if server_errors >= SERVER_ERROR_TRIES:
                    raise GitHubError(f"GET {path}: {type(err).__name__}") from None
                sleep(2.0 * server_errors)
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code in _ABSENT:
                return None
            wait = self._rate_limit_wait(resp)
            if wait is not None:
                if wait > RATE_LIMIT_MAX_WAIT_S:
                    raise GitHubError(f"GET {path}: rate limited for {wait:.0f}s more")
                sleep(wait)
                continue
            if resp.status_code >= 500:
                server_errors += 1
                if server_errors < SERVER_ERROR_TRIES:
                    sleep(2.0 * server_errors)
                    continue
            message = self._message(resp)
            raise GitHubError(f"GET {path}: HTTP {resp.status_code} {message}")

    @staticmethod
    def _message(resp: httpx2.Response) -> str:
        try:
            return str(resp.json().get("message", ""))[:200]
        except (ValueError, AttributeError):
            return resp.text[:200]

    def _rate_limit_wait(self, resp: httpx2.Response) -> float | None:
        """Seconds to wait before retrying a rate-limited response; None if it was not one."""
        if resp.status_code not in (403, 429):
            return None
        headers = resp.headers
        if headers.get("retry-after"):
            try:
                return max(1.0, float(headers["retry-after"]))
            except ValueError:
                return SECONDARY_LIMIT_WAIT_S
        if headers.get("x-ratelimit-remaining") == "0" and headers.get("x-ratelimit-reset"):
            return max(1.0, float(headers["x-ratelimit-reset"]) - time.time() + 1)
        if "rate limit" in self._message(resp).lower():
            return SECONDARY_LIMIT_WAIT_S
        return None

    # -- search

    def search_repositories(self, query: Query, *, page: int = 1, per_page: int = SEARCH_PAGE_MAX,
                            sort: str = SORT) -> dict[str, Any]:
        """One page of repository search; waits so searches stay SEARCH_INTERVAL_S apart."""
        with self._search_lock:
            if self._last_search is not None:
                wait = self._last_search + self._interval - monotonic()
                if wait > 0:
                    sleep(wait)
            started = monotonic()
            ran_at = taipei_now().isoformat(timespec="seconds")
            params = {"q": query.q, "per_page": per_page, "page": page, "sort": sort, "order": "desc"}
            try:
                resp = self._get("search", "/search/repositories", params)
            except GitHubError as err:
                self._trace({"ts": ran_at, "kind": "search", "query_id": query.id, "q": query.q,
                             "page": page, "sort": sort, "status": "error", "error": str(err)})
                raise
            finally:
                self._last_search = monotonic()
            data = resp.json() if resp is not None else {"total_count": 0, "items": []}
            self._trace({"ts": ran_at, "kind": "search", "query_id": query.id, "q": query.q,
                         "page": page, "per_page": per_page, "sort": sort, "status": "ok",
                         "total_count": data.get("total_count"),
                         "incomplete_results": data.get("incomplete_results"),
                         "items": len(data.get("items") or []),
                         "rate_remaining": resp.headers.get("x-ratelimit-remaining") if resp else None,
                         "latency_s": round(monotonic() - started, 3)})
            return data

    def search_all(self, query: Query, max_results: int) -> Iterator[tuple[int, dict[str, Any], int]]:
        """Yield (rank, item, total_count) for up to `max_results` results of one query."""
        max_results = min(max_results, SEARCH_RESULTS_MAX)
        per_page = min(SEARCH_PAGE_MAX, max_results)
        rank = 0
        page = 1
        while rank < max_results:
            data = self.search_repositories(query, page=page, per_page=per_page)
            items = data.get("items") or []
            for item in items:
                rank += 1
                yield rank, item, data.get("total_count") or 0
                if rank >= max_results:
                    return
            if len(items) < per_page:
                return
            page += 1

    # -- per-repo details

    def readme(self, full_name: str) -> tuple[str | None, str | None]:
        """(text, path) of the README GitHub shows on the repo page, or (None, None)."""
        resp = self._get("readme", f"/repos/{full_name}/readme")
        if resp is None:
            return None, None
        data = resp.json()
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            return None, data.get("path")
        text = base64.b64decode(data["content"]).decode("utf-8", "replace")
        return text[:README_MAX_CHARS], data.get("path")

    def releases(self, full_name: str, per_page: int = RELEASES_PER_REPO) -> list[dict[str, Any]]:
        """The newest releases (drafts are only visible to owners), newest first."""
        resp = self._get("releases", f"/repos/{full_name}/releases", {"per_page": per_page})
        return resp.json() if resp is not None else []

    def tree(self, full_name: str, ref: str) -> tuple[list[str], bool]:
        """(file paths, truncated) of the whole tree at `ref`; ([], False) for an empty repo."""
        resp = self._get("tree", f"/repos/{full_name}/git/trees/{urllib.parse.quote(ref, safe='')}",
                         {"recursive": "1"})
        if resp is None:
            return [], False
        data = resp.json()
        paths = [entry["path"] for entry in data.get("tree") or [] if entry.get("type") == "blob"]
        return paths, bool(data.get("truncated"))

    def file_text(self, full_name: str, path: str, ref: str) -> str | None:
        resp = self._get("file", f"/repos/{full_name}/contents/{urllib.parse.quote(path)}",
                         {"ref": ref}, accept="application/vnd.github.raw+json")
        return resp.text if resp is not None else None

    def details(self, repo: dict[str, Any]) -> dict[str, Any]:
        """README, newest releases, file tree and root manifests for a normalized repo."""
        full_name, ref = repo["full_name"], repo["default_branch"] or "HEAD"
        readme, readme_path = self.readme(full_name)
        releases = [normalize_release(r) for r in self.releases(full_name) if not r.get("draft")]
        files, truncated = self.tree(full_name, ref)
        present = set(files)
        manifests = {name: self.file_text(full_name, name, ref) for name in MANIFESTS
                     if name in present}
        return {"readme": readme, "readme_path": readme_path, "releases": releases,
                "files": files, "files_truncated": truncated,
                "manifests": {k: v for k, v in manifests.items() if v is not None}}

    # -- trace

    def _trace(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str).replace(self._token, "[redacted]")
        path = self._trace_dir / f"github-{taipei_date()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)


# --- Normalization ---------------------------------------------------------------

REPO_FIELDS = (
    "id", "full_name", "name", "html_url", "description", "homepage", "language", "topics",
    "stargazers_count", "forks_count", "open_issues_count", "created_at", "updated_at",
    "pushed_at", "archived", "disabled", "fork", "is_template", "default_branch", "size",
    "has_issues",
)


def _blank_to_none(value: Any) -> Any:
    return value.strip() or None if isinstance(value, str) else value


def normalize_repo(item: dict[str, Any]) -> dict[str, Any]:
    """The repo facts pickfit keeps from a search item (search items are full repo objects)."""
    repo = {key: _blank_to_none(item.get(key)) for key in REPO_FIELDS}
    repo["owner"] = (item.get("owner") or {}).get("login")
    repo["topics"] = sorted({t.lower() for t in item.get("topics") or []})
    spdx = (item.get("license") or {}).get("spdx_id")
    repo["license"] = None if spdx in (None, "NOASSERTION") else spdx
    for flag in ("archived", "disabled", "fork", "is_template"):
        repo[flag] = bool(repo[flag])
    return repo


def normalize_release(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": release.get("tag_name"),
        "name": _blank_to_none(release.get("name")),
        "published_at": release.get("published_at"),
        "prerelease": bool(release.get("prerelease")),
        "url": release.get("html_url"),
        "body": (release.get("body") or "")[:4000],
        "assets": [{"name": a.get("name"), "downloads": a.get("download_count") or 0}
                   for a in release.get("assets") or []],
    }
