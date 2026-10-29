"""Package-registry and Hacker News signals for popularity (B.3), from free public APIs, no keys.

- npm: the package document (repository, homepage, bugs) and last-month downloads (api.npmjs.org).
- PyPI: the JSON API (project_urls, home_page); last-month downloads from pypistats.org, which
  B.3 allows only a few calls of, so callers can turn it off.
- crates.io: crate repository and homepage; recent_downloads covers 90 days, so a third per month.
- Homebrew core: formula homepage and source URLs; 30-day install analytics.
- Hacker News, through the Algolia search API: the best story score whose URL is the repository
  or the project's own homepage.

A package counts only when its registry entry links back to the repository (owner/name or an
earlier name), so a same-named package of someone else never counts. Names to try come from the
install commands pickfit saw (README claims and replayed steps) and the root manifests.
dependents stays uncounted: the only free source for it has not agreed to this use (arch G.4).
"""

from __future__ import annotations

import configparser
import json
import re
import shlex
import threading
import time
import tomllib
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx2

from pickfit.discover.github import USER_AGENT

REGISTRIES = ("npm", "pypi", "crates", "homebrew")
# crates.io asks crawlers for at most one request a second; pypistats is a small free service.
MIN_INTERVAL_S = {"crates.io": 1.0, "pypistats.org": 1.0}
TRIES = 3
# Shared hosts whose stories are not about one project.
SHARED_HOSTS = frozenset({
    "github.com", "gitlab.com", "codeberg.org", "npmjs.com", "pypi.org", "crates.io", "x.com",
    "twitter.com", "youtube.com", "discord.gg", "discord.com", "medium.com", "huggingface.co",
    "linkedin.com", "reddit.com", "t.me", "docs.rs", "pkg.go.dev",
})


class RegistryError(Exception):
    """A registry or HN lookup failed after retries (not a 404)."""


# --- names to look up --------------------------------------------------------------------------

_SEGMENT = re.compile(r"&&|\|\||[;|\n]")
_COMMANDS = {
    "npm": re.compile(r"^(?:sudo\s+)?(?:npm|pnpm)\s+(?:i|install|add)\s+(.*)$|^(?:bun|pnpm)\s+add\s+(.*)$"
                      r"|^yarn\s+global\s+add\s+(.*)$|^npx\s+(.*)$|^bunx\s+(.*)$"),
    "pypi": re.compile(r"^(?:sudo\s+)?(?:pip3?|python3?\s+-m\s+pip|uv\s+pip|pipx|uv\s+tool)\s+install\s+(.*)$"
                       r"|^uvx\s+(.*)$|^pipx\s+run\s+(.*)$"),
    "crates": re.compile(r"^cargo\s+(?:binstall|install)\s+(.*)$"),
    "homebrew": re.compile(r"^brew\s+install\s+(.*)$"),
}
_SKIP_WITH = {"crates": ("--git", "--path"), "npm": (), "pypi": ("-r", "--requirement", "-e", "--editable"),
              "homebrew": ("--cask",)}
# Options that take a value, so the next word is not a package.
_VALUED = frozenset({"--python", "--index-url", "-i", "--extra-index-url", "--with", "--registry", "--prefix",
                     "--root", "--version", "--tag", "--features", "-p", "--package", "--from"})


def _bare(name: str, registry: str) -> str | None:
    """A registry package name without version, extras or tag; None for paths and URLs."""
    if not name or name.startswith((".", "/", "~", "$", "-")) or "://" in name or name.startswith("git+"):
        return None
    if registry == "npm":
        at = name.rfind("@")
        name = name[:at] if at > 0 else name
        if name.count("/") > (1 if name.startswith("@") else 0) or name.endswith((".tgz", ".git")):
            return None
        return name.lower() if re.fullmatch(r"(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*", name, re.I) else None
    if registry == "pypi":
        name = re.split(r"[\[=<>!~;@ ]", name, maxsplit=1)[0]
        if name.endswith((".whl", ".tar.gz", ".zip")) or "/" in name:
            return None
        return re.sub(r"[-_.]+", "-", name).lower() if re.fullmatch(r"[A-Za-z0-9][\w.-]*", name) else None
    if registry == "crates":
        name = name.split("@", 1)[0]
        return name.lower() if re.fullmatch(r"[A-Za-z0-9][\w-]*", name) else None
    if "/" in name:  # homebrew: user/tap/name is a tap, not homebrew-core
        return None
    return name.lower() if re.fullmatch(r"[a-z0-9][\w@.+-]*", name, re.I) else None


def command_names(commands: Iterable[str]) -> dict[str, set[str]]:
    """Package names named by install commands, per registry."""
    out: dict[str, set[str]] = {r: set() for r in REGISTRIES}
    for command in commands:
        for segment in _SEGMENT.split(command):
            segment = re.sub(r"^\s*(?:\w+=\S*\s+)*", "", segment).strip()
            for registry, pattern in _COMMANDS.items():
                m = pattern.match(segment)
                if not m:
                    continue
                rest = next(g for g in m.groups() if g is not None)
                try:
                    words = shlex.split(rest)
                except ValueError:
                    words = rest.split()
                if any(w in _SKIP_WITH[registry] for w in words):
                    continue
                runner = segment.startswith(("npx", "bunx", "uvx", "pipx run"))
                skip_next = False
                for word in words:
                    if skip_next:
                        skip_next = False
                        continue
                    if word.startswith("-"):
                        skip_next = word in _VALUED
                        continue
                    if re.match(r"\d*[<>]", word):  # a redirection such as 2>&1
                        continue
                    if (name := _bare(word, registry)) is not None:
                        out[registry].add(name)
                    if runner:
                        break  # npx, uvx: the first word is the package, the rest are its arguments
    return out


def manifest_names(manifests: dict[str, str] | None) -> dict[str, set[str]]:
    """Package names declared by root manifests (package.json, pyproject.toml, Cargo.toml, setup.cfg)."""
    out: dict[str, set[str]] = {r: set() for r in REGISTRIES}
    manifests = manifests or {}
    try:
        pkg = json.loads(manifests.get("package.json") or "{}")
        if isinstance(pkg, dict) and not pkg.get("private") and (name := _bare(str(pkg.get("name") or ""), "npm")):
            out["npm"].add(name)
    except ValueError:
        pass
    for key, path in (("pyproject.toml", ("project", "name")), ("pyproject.toml", ("tool", "poetry", "name")),
                      ("Cargo.toml", ("package", "name"))):
        try:
            value: Any = tomllib.loads(manifests.get(key) or "")
        except tomllib.TOMLDecodeError:
            continue
        for part in path:
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str):
            registry = "crates" if key == "Cargo.toml" else "pypi"
            if (name := _bare(value, registry)) is not None:
                out[registry].add(name)
    if manifests.get("setup.cfg"):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(manifests["setup.cfg"])
            if (name := _bare(parser.get("metadata", "name", fallback=""), "pypi")) is not None:
                out["pypi"].add(name)
        except configparser.Error:
            pass
    return out


def merge_names(*parts: dict[str, set[str]]) -> dict[str, set[str]]:
    return {r: set().union(*(p.get(r, set()) for p in parts)) for r in REGISTRIES}


# --- does an entry point at this repo? ---------------------------------------------------------


def _norm_url(url: str) -> str:
    url = url.strip().lower()
    url = re.sub(r"^(?:git\+)?(?:https?|git|ssh)://(?:git@)?", "", url)
    url = re.sub(r"^git@github\.com:", "github.com/", url)
    url = url.removeprefix("www.")
    return re.sub(r"(?:\.git)?/*$", "", url)


def links_repo(urls: Iterable[Any], repos: Iterable[str]) -> bool:
    """True when any URL is github.com/<owner>/<name> (or a page under it) for one of repos."""
    targets = [f"github.com/{r.lower()}" for r in repos]
    for url in urls:
        if not isinstance(url, str) or not url:
            continue
        u = _norm_url(url)
        if any(u == t or u.startswith(t + "/") or u.startswith(t + "#") or u.startswith(t + "?") for t in targets):
            return True
    return False


# --- the lookups --------------------------------------------------------------------------------


@dataclass
class Package:
    registry: str
    name: str
    monthly_downloads: int | None


@dataclass
class RegistrySignals:
    monthly_downloads: int | None
    registries_count: int | None
    hn_top_score: int | None
    packages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Registries:
    """Lookups with retries and per-host pacing; 404 means not there."""

    def __init__(self, *, http: httpx2.Client | None = None, pypi_downloads: bool = True,
                 min_interval_s: dict[str, float] | None = None) -> None:
        self._http = http or httpx2.Client(timeout=30.0, follow_redirects=True,
                                            headers={"User-Agent": USER_AGENT})
        self.pypi_downloads = pypi_downloads
        self._interval = MIN_INTERVAL_S if min_interval_s is None else min_interval_s
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}
        self.requests = 0

    def close(self) -> None:
        self._http.close()

    def _pace(self, host: str) -> None:
        gap = self._interval.get(host)
        if not gap:
            return
        with self._lock:
            now = time.monotonic()
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + gap
        if at > now:
            time.sleep(at - now)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        host = urllib.parse.urlsplit(url).hostname or ""
        for attempt in range(1, TRIES + 1):
            self._pace(host)
            self.requests += 1
            try:
                resp = self._http.get(url, params=params)
            except httpx2.TransportError as err:
                if attempt == TRIES:
                    raise RegistryError(f"{host}: {type(err).__name__}") from None
                time.sleep(1.5 * attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    raise RegistryError(f"{host}: not JSON") from None
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < TRIES:
                time.sleep(float(resp.headers.get("retry-after") or 2.0 * attempt))
                continue
            raise RegistryError(f"{host}: HTTP {resp.status_code}")
        raise AssertionError("unreachable")

    def npm(self, name: str, repos: list[str]) -> Package | None:
        # The latest version's manifest is small; the full package document can be megabytes.
        doc = self.get_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/latest")
        if not isinstance(doc, dict):
            return None
        repo, bugs = doc.get("repository"), doc.get("bugs")
        urls = [repo.get("url") if isinstance(repo, dict) else repo, doc.get("homepage"),
                bugs.get("url") if isinstance(bugs, dict) else bugs]
        if not links_repo(urls, repos):
            return None
        counts = self.get_json(f"https://api.npmjs.org/downloads/point/last-month/{name}")
        return Package("npm", name, int(counts.get("downloads") or 0) if isinstance(counts, dict) else 0)

    def pypi(self, name: str, repos: list[str]) -> Package | None:
        doc = self.get_json(f"https://pypi.org/pypi/{name}/json")
        info = doc.get("info") if isinstance(doc, dict) else None
        if not isinstance(info, dict):
            return None
        urls = [*(info.get("project_urls") or {}).values(), info.get("home_page"), info.get("download_url")]
        if not links_repo(urls, repos):
            return None
        downloads = None
        if self.pypi_downloads:
            recent = self.get_json(f"https://pypistats.org/api/packages/{name}/recent")
            downloads = int((recent or {}).get("data", {}).get("last_month") or 0) if isinstance(recent, dict) else 0
        return Package("pypi", name, downloads)

    def crates(self, name: str, repos: list[str]) -> Package | None:
        doc = self.get_json(f"https://crates.io/api/v1/crates/{name}")
        crate = doc.get("crate") if isinstance(doc, dict) else None
        if not isinstance(crate, dict) or not links_repo([crate.get("repository"), crate.get("homepage")], repos):
            return None
        return Package("crates", name, round(int(crate.get("recent_downloads") or 0) / 3))

    def homebrew(self, name: str, repos: list[str]) -> Package | None:
        doc = self.get_json(f"https://formulae.brew.sh/api/formula/{name}.json")
        if not isinstance(doc, dict):
            return None
        urls = [doc.get("homepage"), *((u or {}).get("url") for u in (doc.get("urls") or {}).values())]
        if not links_repo(urls, repos):
            return None
        installs = (((doc.get("analytics") or {}).get("install") or {}).get("30d") or {})
        return Package("homebrew", name, int(sum(v for v in installs.values() if isinstance(v, int))))

    def hn_top_score(self, full_name: str, aliases: list[str], homepage: str | None) -> int:
        """Best points among HN stories linking to the repo or the project's homepage; 0 for none."""
        targets = [f"github.com/{r.lower()}" for r in [full_name, *aliases]]
        if homepage:
            home = _norm_url(homepage)
            host = home.split("/", 1)[0]
            if host and host not in SHARED_HOSTS and "." in host:
                targets.append(home)
        best = 0
        for target in targets:
            doc = self.get_json("https://hn.algolia.com/api/v1/search",
                                {"query": target, "restrictSearchableAttributes": "url", "tags": "story",
                                 "hitsPerPage": 50})
            for hit in (doc or {}).get("hits") or []:
                u = _norm_url(hit.get("url") or "")
                if u == target or u.startswith((target + "/", target + "#", target + "?")):
                    best = max(best, int(hit.get("points") or 0))
        return best

    def lookup(self, full_name: str, *, aliases: list[str] | None = None, homepage: str | None = None,
               names: dict[str, set[str]] | None = None) -> RegistrySignals:
        """Signals for one repo; a signal whose lookups failed is None (unknown), not 0."""
        repos = [full_name, *(aliases or [])]
        names = merge_names(names or {}, {"homebrew": {full_name.split("/")[-1].lower()}})
        found: dict[str, Package] = {}
        errors: list[str] = []
        check = {"npm": self.npm, "pypi": self.pypi, "crates": self.crates, "homebrew": self.homebrew}
        for registry in REGISTRIES:
            for name in sorted(names.get(registry, ())):
                if registry in found:
                    break
                try:
                    package = check[registry](name, repos)
                except RegistryError as err:
                    errors.append(f"{registry}:{name}: {err}")
                    continue
                if package is not None:
                    found[registry] = package
        try:
            hn: int | None = self.hn_top_score(full_name, aliases or [], homepage)
        except RegistryError as err:
            errors.append(f"hn: {err}")
            hn = None
        counted = [p.monthly_downloads for p in found.values() if p.monthly_downloads is not None]
        return RegistrySignals(
            monthly_downloads=sum(counted) if counted else None,
            registries_count=None if any(not e.startswith("hn") for e in errors) else len(found),
            hn_top_score=hn,
            packages=[f"{p.registry}:{p.name}" for p in found.values()],
            errors=errors,
        )
