"""Install documentation a README points to.

Many READMEs hold no install command; they say "see the install guide" and link to the project's
own site (rclone, restic, chezmoi, pandoc, mitmproxy, trivy and fourteen more of the 93 repositories
read on 11/16). Extraction reads only what pickfit fetched, so such a tool had no install path the
sandbox could run and was listed unverified without ever being tried. For a candidate whose
extraction finds no such path, pickfit now reads one install page, the first of these it can read:

1. a documentation file in the repository (INSTALL.md, docs/install*.md, docs/getting-started.md),
   whether the README links to it or the file tree shows it: from the GitHub API, like the README;
2. a page on the project's own site that the README links to, whose link text or address says
   install, getting started, quick start, download or setup;
3. failing those, the pages the project names as its home (the repository's homepage on GitHub, a
   "documentation" link in the README) and the one install page such a page links to on its own site.

"Install" outranks "getting started", and at the same rank a file of the repository comes before a
web page. The project's own site is the site of the homepage GitHub lists for the repository, or a
host named after the repository or its owner (restic.readthedocs.io): a README also links to the
install pages of what it needs (Rust's, Docker's), and those are not read. Never a search. Pages are
fetched as pickfit, one request a second, at most MAX_REQUESTS per candidate, and only where
robots.txt lets pickfit read the page for a model (pickfit.discover.webapps.robots_verdict, the rule
the hosted web apps go by). A page that needs JavaScript to show its text is not rendered: it is
noted and skipped. What was looked at and why a page was not read is kept with the page (`tried`).

The text reaches the model inside a <source> block like the README: data, never instructions.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from pickfit.discover.webapps import Fetcher, _PageParser, fetch_robots, host_of, robots_verdict
from pickfit.ledger import taipei_now

RULE = "install-docs.v1"
MAX_TRIES = 4  # install links tried, best first, until one page is read
MAX_REQUESTS = 8  # robots.txt files, hub pages and install pages together
DOC_MAX_CHARS = 20_000
THIN_BELOW = 200  # characters of text: less is a page that draws itself with JavaScript

# What a link's words or address must say to be an install page, strongest first.
_SCORES: tuple[tuple[int, re.Pattern[str]], ...] = (
    (3, re.compile(r"install", re.I)),
    (2, re.compile(r"getting[-_ ]?started|get[-_ ]started|quick[-_ ]?start|download|set[-_ ]?up\b|setup", re.I)),
)
# A hub: a page to look for an install link on, never an install page by itself. Only the link's words
# count ("Documentation", "Website"), not its address: a README links to many pages with docs or wiki in
# their address that are not the project's (pandoc's to Wikipedia and DokuWiki).
_HUB_WORDS = re.compile(r"\bdocs?\b|documentation|user guide|manual|handbook|website|home ?page", re.I)
INSTALL, HUB = 2, 1

_MD_LINK = re.compile(r"(?<!!)\[([^\[\]]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)")  # not ![alt](image), nor a badge's link
_HTML_LINK = re.compile(r"<a\s[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?(?:\s|$)", re.M)
_REF_USE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
_BARE_URL = re.compile(r"(?<![(\[<\"'=])https?://[^\s<>)\]\[\"']+")  # AsciiDoc writes url[words]
_TAGS = re.compile(r"<[^>]+>")
_REPO_DOC = re.compile(
    r"^(?:(?:docs?|documentation|website/docs)/(?:[^/]+/){0,2})?"
    r"(?:install(?:ation|ing)?|getting[-_]started|quick[-_]?start|setup)[^/]*\.(?:md|mdx|rst|txt|adoc)$", re.I)
_NOT_PAGES = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|ico|zip|gz|tgz|xz|bz2|deb|rpm|dmg|exe|msi|pkg|apk|whl|"
                        r"pdf|mp4|webm|mov)(?:$|[?#])", re.I)
# Sites that are not a project's documentation: badges, social, stores and registries (extraction has
# the registries' facts from elsewhere, and a store page is not an install guide a box can follow).
_OTHER_SITES = frozenset({
    "shields.io", "badge.fury.io", "badgen.net", "youtube.com", "youtu.be", "twitter.com", "x.com", "discord.gg",
    "discord.com", "slack.com", "reddit.com", "linkedin.com", "facebook.com", "t.me", "matrix.to", "gitter.im",
    "npmjs.com", "pypi.org", "crates.io", "hub.docker.com", "apps.apple.com", "play.google.com",
    "opencollective.com", "patreon.com", "ko-fi.com", "buymeacoffee.com", "paypal.com", "codecov.io",
    "coveralls.io", "travis-ci.org", "travis-ci.com", "circleci.com", "goreportcard.com", "pkg.go.dev",
    "repology.org", "snapcraft.io", "flathub.org", "formulae.brew.sh", "gitpod.io", "stackoverflow.com",
})


@dataclass(frozen=True)
class Link:
    """One place install documentation may be: a file of the repository (`path`) or a web page (`url`)."""

    score: int
    why: str
    url: str | None = None
    path: str | None = None

    @property
    def where(self) -> str:
        return self.path or self.url or ""


def _score(*texts: str) -> int:
    return max((score for score, pattern in _SCORES for t in texts if t and pattern.search(t)), default=0)


def _other_site(url: str) -> bool:
    """True for an address that is not a project's documentation: no site, or a badge, social or store site."""
    host = host_of(url) or ""
    return "." not in host or any(host == s or host.endswith("." + s) for s in _OTHER_SITES) \
        or host.startswith(("shields.", "badge.", "badges.", "img."))


def _own_site(url: str, homepage: str, full_name: str) -> bool:
    """True when a page is on the project's own site: the site of the homepage GitHub lists for it, or a
    host named after the repository or its owner (restic.readthedocs.io, smallstep.com, <owner>.github.io)."""
    if homepage and _same_site(url, homepage):
        return True
    names = {re.sub(r"[^a-z0-9]", "", part.lower()) for part in full_name.split("/")} - {""}
    labels = (host_of(url) or "").split(".")[:-1]  # without the top-level domain
    return any(re.sub(r"[^a-z0-9]", "", label) in names for label in labels)


def _same_site(a: str, b: str) -> bool:
    """True when two addresses are on one host, or one host is a subdomain of the other (mitmproxy.org and
    docs.mitmproxy.org). Never by a shared ending alone: two projects on github.io are two sites."""
    x, y = host_of(a), host_of(b)
    return bool(x and y) and (x == y or x.endswith("." + y) or y.endswith("." + x))


def readme_links(readme: str) -> list[tuple[str, str]]:
    """(address, the words that link to it) for every link of a README, in reading order."""
    refs = {name.lower(): url for name, url in _REF_DEF.findall(readme)}
    found: list[tuple[int, str, str]] = []
    for m in _MD_LINK.finditer(readme):
        found.append((m.start(), m.group(2), m.group(1)))
    for m in _HTML_LINK.finditer(readme):
        found.append((m.start(), m.group(1), " ".join(_TAGS.sub(" ", m.group(2)).split())))
    for m in _REF_USE.finditer(readme):
        url = refs.get((m.group(2) or m.group(1)).lower())
        if url:
            found.append((m.start(), url, m.group(1)))
    for m in _BARE_URL.finditer(readme):
        line_start = readme.rfind("\n", 0, m.start()) + 1
        line_end = readme.find("\n", m.end())
        line = readme[line_start: line_end if line_end >= 0 else len(readme)]
        found.append((m.start(), m.group(0).rstrip(".,;:"), line.replace(m.group(0), " ")[:200]))
    return [(url, text) for _, url, text in sorted(found)]


def _repo_path(url: str, full_name: str, readme_path: str) -> str | None:
    """The repository file an address means, or None when it is not a file of this repository."""
    url = urldefrag(url)[0]
    if not url:
        return None  # an anchor of the README itself
    m = re.match(rf"https?://github\.com/{re.escape(full_name)}/(?:blob|tree)/[^/]+/(.+)$", url, re.I)
    if m:
        return m.group(1).rstrip("/")
    if re.match(r"[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("//"):
        return None
    base = posixpath.dirname(readme_path or "README.md")
    path = posixpath.normpath(posixpath.join("/" if url.startswith("/") else base, url.lstrip("/")))
    return None if path.startswith("..") or path in (".", "") else path


def _doc_file(path: str, files: set[str]) -> str | None:
    """The documentation file `path` names: itself, or the README or index of that directory."""
    if path in files:
        return path if re.search(r"\.(?:md|mdx|rst|txt|adoc)$", path, re.I) else None
    for name in ("README.md", "index.md", "README.rst", "index.rst"):
        if f"{path}/{name}" in files:
            return f"{path}/{name}"
    return None


_LINUX_DOC = re.compile(r"linux|unix|posix|source|ubuntu|debian", re.I)
_OTHER_OS_DOC = re.compile(r"mac|osx|darwin|windows|(?:^|[^a-z])win(?:32|64)?(?:[^a-z]|$)", re.I)


def _os_rank(where: str) -> int:
    """0 for a guide that names Linux, Unix or a build from source, 2 for one that names only macOS or Windows,
    1 for one that names no platform. Only the file or page name counts, not the folders above it."""
    name = where.rstrip("/").rsplit("/", 1)[-1]
    if _LINUX_DOC.search(name):
        return 0
    return 2 if _OTHER_OS_DOC.search(name) else 1


def find_links(candidate: dict[str, Any]) -> list[Link]:
    """Where a candidate's install documentation may be, best first: repository files, then pages."""
    repo = candidate.get("repo") or {}
    full_name = repo.get("full_name") or candidate["full_name"]
    files = set(candidate.get("files") or [])
    readme_path = candidate.get("readme_path") or "README.md"
    own = re.compile(rf"https?://github\.com/{re.escape(full_name)}(?:[/?#]|$)", re.I)
    homepage = (repo.get("homepage") or "").strip()
    if not homepage.lower().startswith(("http://", "https://")) or own.match(homepage) or _other_site(homepage):
        homepage = ""
    links: list[Link] = []
    for url, text in readme_links(candidate.get("readme") or ""):
        path = _repo_path(url, full_name, readme_path)
        if path is not None:
            doc = _doc_file(path, files)
            score = _score(text, path)
            if doc and doc != readme_path and score >= INSTALL:
                links.append(Link(score, f"the README links to it as {text.strip()[:80]!r}", path=doc))
            continue
        if not url.lower().startswith(("http://", "https://")) or _NOT_PAGES.search(url):
            continue
        if own.match(url) and "/wiki" not in url.lower():
            continue  # issues, releases, actions: the release is a source already
        if _other_site(url) or not (own.match(url) or _own_site(url, homepage, full_name)):
            continue  # a README also links to the install pages of what it needs: Rust's, Docker's, Go's
        score = _score(text, urlsplit(url).path) or (HUB if _HUB_WORDS.search(text) else 0)
        if score:
            links.append(Link(score, f"the README links to it as {' '.join(text.split())[:80]!r}",
                              url=urldefrag(url)[0]))
    for path in sorted(files, key=lambda p: (p.count("/"), len(p), p)):
        if _REPO_DOC.match(path) and path != readme_path:
            links.append(Link(_score(path), "a documentation file of the repository", path=path))
    if homepage:
        # First among the hubs: it is the one page GitHub's own field calls the project's.
        links.insert(0, Link(max(HUB, _score(urlsplit(homepage).path)), "the repository's homepage on GitHub",
                             url=urldefrag(homepage)[0]))
    seen: set[str] = set()
    unique = []
    # At the same score: files before pages (no robots question, and the text is the project's own source), a
    # Linux, Unix or from-source guide before a macOS or Windows one (the sandbox is Linux: ImageMagick's
    # Install-mac.txt, the shortest name, was read instead of Install-unix.txt), and "getting started" before
    # "setup" or "download" (a setup wizard's page, a download button's).
    for link in sorted(links, key=lambda x: (-x.score, x.path is None, _os_rank(x.where),
                                             not re.search(r"getting|quick", x.where, re.I))):
        key = link.where.rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            unique.append(link)
    return unique


class _DocParser(_PageParser):
    """A page's text without its menus: a documentation site's sidebar is longer than its page."""

    _SKIP = _PageParser._SKIP | {"nav", "aside", "footer"}
    _BLOCK = _PageParser._BLOCK | {"pre"}  # a code block's command starts its own line, apart from its tab label


_REFRESH = re.compile(r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]*content=[\"'][^\"'>]*url=([^\"'>\s]+)", re.I)


def page_text(html: str) -> tuple[str, str, list[tuple[str, str]]]:
    """(title, text, links) of an HTML page."""
    parser = _DocParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - a broken page still yields what was parsed before the error
        pass
    return " ".join(parser.title.split()), parser.text(), parser.links


@dataclass
class Reader:
    """Reads one candidate's install pages. `tried` is every place looked at, with what happened."""

    fetch: Fetcher
    file_text: Callable[[str, str, str], str | None]  # (full_name, path, ref) -> text, GitHub.file_text
    tried: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    _robots: dict[str, str | None | bool] = field(default_factory=dict)

    def _note(self, link: Link, outcome: str) -> None:
        self.tried.append({"where": link.where, "why": link.why, "outcome": outcome})

    def _allowed(self, url: str) -> str | None:
        """None when pickfit may read `url`, else why not."""
        host = urlsplit(url).netloc.lower()
        if host not in self._robots:
            if self.requests >= MAX_REQUESTS:
                return "request limit reached"
            self.requests += 1
            text, info = fetch_robots(self.fetch, url)
            self._robots[host] = False if info.get("unreachable") else text
        robots = self._robots[host]
        if robots is False:
            return "robots.txt unreachable"
        verdict = robots_verdict(robots if isinstance(robots, str) else None, url)
        return None if verdict["allowed"] else "robots.txt does not allow it"

    def _get(self, link: Link, hop: bool = True) -> tuple[str, str, list[tuple[str, str]], str] | None:
        """(title, text, links, final address) of a web page, or None with the reason noted."""
        assert link.url is not None
        refused = self._allowed(link.url)
        if refused:
            self._note(link, refused)
            return None
        if self.requests >= MAX_REQUESTS:
            self._note(link, "request limit reached")
            return None
        self.requests += 1
        got = self.fetch.get("docs", link.url)
        if got["status"] != 200 or not got["text"]:
            self._note(link, f"HTTP {got['status']}" if got["status"] else f"no answer ({got['error']})")
            return None
        final = got["url"]
        if not _same_site(final, link.url):
            self._note(link, f"redirects to another site ({urlsplit(final).netloc})")
            return None
        if "html" in (got["type"] or "html"):
            title, text, links = page_text(got["text"])
        else:
            title, text, links = "", got["text"], []
        if len(text) < THIN_BELOW:
            # A versioned documentation site answers an old address with a page that only forwards.
            moved = _REFRESH.search(got["text"]) if hop else None
            target = urldefrag(urljoin(final, moved.group(1)))[0] if moved else None
            if target and _same_site(target, final) and target.rstrip("/") != final.rstrip("/"):
                self._note(link, f"forwards to {target}")
                return self._get(Link(link.score, link.why, url=target), hop=False)
            self._note(link, "the page shows no text without JavaScript")
            return None
        return title, text, links, final

    def read(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        repo = candidate.get("repo") or {}
        full_name = repo.get("full_name") or candidate["full_name"]
        ref = repo.get("default_branch") or "HEAD"
        html_url = repo.get("html_url") or f"https://github.com/{full_name}"
        pages: list[dict[str, Any]] = []
        links = find_links(candidate)
        hubs = [x for x in links if x.score < INSTALL]

        def add(link: Link, url: str, kind: str, title: str, text: str) -> None:
            pages.append({"url": url, "kind": kind, "title": title[:200], "text": text[:DOC_MAX_CHARS],
                          "truncated": len(text) > DOC_MAX_CHARS, "why": link.why,
                          "fetched_at": taipei_now().isoformat(timespec="seconds")})
            self._note(link, "read")

        for link in [x for x in links if x.score >= INSTALL][:MAX_TRIES]:
            if pages:  # one page: a repository's docs/install.md and its site's /install/ are the same text
                break
            if link.path:
                text = self.file_text(full_name, link.path, ref)
                if text and text.strip():
                    add(link, f"{html_url}/blob/{ref}/{link.path}", "readme", link.path, text)
                else:
                    self._note(link, "the file could not be read")
                continue
            got = self._get(link)
            if got:
                add(link, got[3], "website", got[0], got[1])
        # No install page named outright: look for one on the pages the project calls its home.
        for hub in hubs[:2]:
            if pages:
                break
            got = self._get(hub)
            if not got:
                continue
            title, text, page_links, final = got
            inner = [Link(_score(words, urlsplit(urljoin(final, href)).path),
                          f"linked from {final} as {words.strip()[:80]!r}", url=urldefrag(urljoin(final, href))[0])
                     for href, words in page_links if not _NOT_PAGES.search(href)]
            inner = [x for x in inner if x.score >= INSTALL and x.url and _same_site(x.url, final)
                     and x.url.rstrip("/") != final.rstrip("/")]
            self._note(hub, "looked for an install link")
            inner = list({x.url: x for x in sorted(inner, key=lambda x: x.score)}.values())  # one try per address
            for link in sorted(inner, key=lambda x: -x.score)[:2]:
                found = self._get(link)
                if found:
                    add(link, found[3], "website", found[0], found[1])
                    break
            else:
                if _score(text) >= INSTALL:  # the home page itself says how to install
                    add(hub, final, "website", title, text)
        return pages


def read_docs(candidate: dict[str, Any], *, fetch: Fetcher, file_text: Callable[[str, str, str], str | None]
              ) -> dict[str, Any]:
    """{rule, pages, tried, fetched_at}: a candidate's install pages as pickfit read them."""
    reader = Reader(fetch, file_text)
    pages = reader.read(candidate)
    return {"rule": RULE, "pages": pages, "tried": reader.tried,
            "fetched_at": taipei_now().isoformat(timespec="seconds")}


def needs_install_docs(extraction: dict[str, Any] | None) -> bool:
    """True when an extraction is of a tool and names no install path the Linux sandbox can run: the only
    case pickfit goes past the README for. A repository that is not a tool is not set aside for want of
    an install command, so nothing is fetched for it."""
    from pydantic import ValidationError

    from pickfit.schema import TOOL_KINDS, ExtractionResult
    from pickfit.verify.plan import plan_for

    try:
        ex = ExtractionResult.model_validate(extraction)
    except ValidationError:
        return False
    if ex.kind.value is not None and ex.kind.value not in TOOL_KINDS:
        return False
    return not plan_for(ex, "linux").candidates


def run_docs(db: Any, *, models: tuple[str, ...], repo_ids: list[str] | None = None, force: bool = False,
             fetch: Fetcher | None = None, file_text: Callable[[str, str, str], str | None] | None = None,
             log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Read the install pages of the candidates whose newest finished extraction (by one of `models`) names
    no install path the Linux sandbox can run, and store them with the candidate (PipelineDB). A candidate
    pickfit has looked at before is left alone unless `force`. The next extraction of a candidate that got
    pages reads them, since its sources changed.

    Returns {looked, read: {full_name: [addresses]}, none: {full_name: what was tried}}.
    """
    log = log or (lambda line: None)
    wanted = set(repo_ids or [])
    pool = [c for c in db.candidates() if not wanted or c["repo_id"] in wanted or c["full_name"] in wanted
            or set(c["aliases"]) & wanted]
    if file_text is None:
        from pickfit.discover.github import GitHub, github_token

        file_text = GitHub(github_token()).file_text
    fetch = fetch or Fetcher()
    summary: dict[str, Any] = {"looked": 0, "read": {}, "none": {}}
    for c in pool:
        if not (c.get("readme") or "").strip() or (db.install_docs(c["repo_id"]) and not force):
            continue
        rows = [r for m in models for r in [db.last_extraction(c["repo_id"], m, ("ok", "quotes_dropped"))] if r]
        last = max(rows, key=lambda r: r["id"], default=None)
        if last is None or not needs_install_docs(last["result"]):
            continue
        summary["looked"] += 1
        docs = read_docs(c, fetch=fetch, file_text=file_text)
        db.save_install_docs(c["repo_id"], docs)
        if docs["pages"]:
            summary["read"][c["full_name"]] = [p["url"] for p in docs["pages"]]
            log(f"  {c['full_name']}: read " + ", ".join(p["url"] for p in docs["pages"]))
        else:
            summary["none"][c["full_name"]] = docs["tried"]
            log(f"  {c['full_name']}: no install page read ("
                + ("; ".join(f"{t['where']}: {t['outcome']}" for t in docs["tried"]) or "the README names none") + ")")
    return summary
