"""Install pages a README points to: which links count, what is fetched, and where the text goes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_profiles import MODEL, NOW, add, cited, db, extraction  # noqa: F401 - db is a fixture
from verify_fakes import FakeBox

from pickfit import installdocs
from pickfit.discover.store import PipelineDB
from pickfit.extract import build_sources, sources_sha
from pickfit.installdocs import Reader, find_links, needs_install_docs, read_docs, readme_links, run_docs
from pickfit.profiles import write_profiles
from pickfit.schema import ExtractionResult
from pickfit.verify.agent import AgentLimits, render_task
from pickfit.verify.plan import plan_for
from pickfit.verify.task import VerifyTask, guide_name, prepare_box

LONG = "Install the tool with one of the commands below. " * 10


def candidate(readme: str, *, homepage: str | None = "https://tool.example", files: list[str] | None = None,
              full_name: str = "acme/tool") -> dict[str, Any]:
    return {"repo_id": "gh:1", "full_name": full_name, "readme": readme, "readme_path": "README.md",
            "files": files or ["README.md"], "aliases": [],
            "repo": {"full_name": full_name, "homepage": homepage, "default_branch": "main",
                     "html_url": f"https://github.com/{full_name}"}}


class FakeFetch:
    """pickfit.discover.webapps.Fetcher's get(), answering from a table; every address asked is kept."""

    def __init__(self, pages: dict[str, Any]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def get(self, kind: str, url: str) -> dict[str, Any]:
        self.asked.append(url)
        page = self.pages.get(url)
        if page is None:
            return {"status": 404, "url": url, "type": "text/html", "text": "not found", "error": None}
        if isinstance(page, dict):
            return {"status": 200, "type": "text/html", "error": None, "url": url, **page}
        return {"status": 200, "url": url, "type": "text/html", "text": page, "error": None}


def html(body: str, title: str = "Install") -> str:
    return f"<html><head><title>{title}</title></head><body><nav>Menu Blog Pricing</nav><main>{body}</main></body></html>"


def test_readme_links_come_from_markdown_html_references_and_bare_addresses():
    readme = ("See the [install guide](https://tool.example/install) or <a href='docs/setup.md'><b>Setup</b></a>.\n"
              "[![Docs](https://img.shields.io/badge/docs-here-blue)](https://tool.example/docs)\n"
              "Read [the manual][man]. Downloads: https://tool.example/downloads.\n\n[man]: https://tool.example/manual\n")
    links = readme_links(readme)
    assert ("https://tool.example/install", "install guide") in links
    assert ("docs/setup.md", "Setup") in links
    assert ("https://tool.example/manual", "the manual") in links
    assert any(url == "https://tool.example/downloads" for url, _ in links)
    assert not any("shields.io" in url for url, _ in links)  # an image is not a page to read


def test_only_the_projects_own_install_pages_count():
    readme = ("Requires [Rust](https://www.rust-lang.org/tools/install) and [Docker](https://docs.docker.com/compose/install/).\n"
              "[Installation](https://docs.tool.example/install/) · [Documentation](https://tool.example/docs/) · "
              "[pod documentation](https://perldoc.perl.org/perlpod) · [Releases](https://github.com/acme/tool/releases) · "
              "[Quick start](https://acme.github.io/tool/quickstart) · [Download](https://tool.example/tool.tar.gz)\n")
    found = [(x.score, x.where) for x in find_links(candidate(readme))]
    assert found == [(3, "https://docs.tool.example/install/"),      # a subdomain of the homepage's site
                     (2, "https://acme.github.io/tool/quickstart"),  # a host named after the owner
                     (1, "https://tool.example"),                    # the homepage: first of the hubs
                     (1, "https://tool.example/docs/")]


def test_repository_files_come_first_and_translations_last():
    readme = "How to install: see [INSTALL](INSTALL.md) or [the site](https://tool.example/install/).\n"
    files = ["README.md", "INSTALL.md", "docs/getting-started.md", "docs/de/getting-started.md", "docs/guide/setup-wizard.md",
             "src/install.rs"]
    found = [(x.score, x.where) for x in find_links(candidate(readme, files=files))]
    assert found[:2] == [(3, "INSTALL.md"), (3, "https://tool.example/install/")]
    assert [w for _, w in found[2:5]] == ["docs/getting-started.md", "docs/de/getting-started.md",
                                          "docs/guide/setup-wizard.md"]
    assert "src/install.rs" not in [w for _, w in found]


def test_a_repository_file_is_read_through_the_github_api_and_no_site_is_asked():
    fetch = FakeFetch({})
    docs = read_docs(candidate("See [INSTALL](INSTALL.md).", files=["README.md", "INSTALL.md"]), fetch=fetch,
                     file_text=lambda full_name, path, ref: f"# Installing\n\npipx install tool ({full_name} {path} {ref})")
    assert fetch.asked == []
    [page] = docs["pages"]
    assert page["kind"] == "readme" and page["url"] == "https://github.com/acme/tool/blob/main/INSTALL.md"
    assert "pipx install tool (acme/tool INSTALL.md main)" in page["text"]
    assert docs["rule"] == "install-docs.v1" and docs["tried"][0]["outcome"] == "read"


def test_a_linked_page_is_read_once_robots_allow_it_and_menus_are_left_out():
    readme = "[Installation](https://tool.example/install)"
    fetch = FakeFetch({"https://tool.example/install": html(f"<h1>Install</h1><p>{LONG}</p><span>sh</span><pre>pipx install tool</pre>")})
    docs = read_docs(candidate(readme), fetch=fetch, file_text=lambda *a: None)
    assert fetch.asked == ["https://tool.example/robots.txt", "https://tool.example/install"]
    [page] = docs["pages"]
    assert page["kind"] == "website" and page["title"] == "Install"
    assert "pipx install tool" in page["text"].splitlines() and "Menu Blog Pricing" not in page["text"]


def test_robots_txt_is_obeyed_and_the_refusal_is_kept():
    readme = "[Installation](https://tool.example/install)"
    fetch = FakeFetch({"https://tool.example/robots.txt": {"type": "text/plain", "text": "User-agent: *\nDisallow: /\n"},
                       "https://tool.example/install": html(LONG)})
    docs = read_docs(candidate(readme), fetch=fetch, file_text=lambda *a: None)
    assert docs["pages"] == [] and "https://tool.example/install" not in fetch.asked
    assert {t["outcome"] for t in docs["tried"]} == {"robots.txt does not allow it"}


def test_the_homepage_leads_to_its_install_page_on_the_same_site_only():
    home = html(f"<p>{LONG}</p><a href='/install/'>Other ways to install</a>"
                "<a href='https://elsewhere.example/install'>Install the plugin</a>", "Tool")
    fetch = FakeFetch({"https://tool.example": home, "https://tool.example/install/": html(f"<p>{LONG}</p><pre>snap install tool</pre>")})
    docs = read_docs(candidate("A tool. No install section."), fetch=fetch, file_text=lambda *a: None)
    assert [p["url"] for p in docs["pages"]] == ["https://tool.example/install/"]
    assert "https://elsewhere.example/install" not in fetch.asked
    assert [(t["where"], t["outcome"]) for t in docs["tried"]] == [
        ("https://tool.example", "looked for an install link"), ("https://tool.example/install/", "read")]


def test_a_forwarding_page_is_followed_once_and_a_script_only_page_is_skipped():
    readme = "[Installation](https://docs.tool.example/stable/install)"
    stub = "<html><head><meta http-equiv='refresh' content='0; url=/stable/overview/install/'></head></html>"
    fetch = FakeFetch({"https://docs.tool.example/stable/install": stub,
                       "https://docs.tool.example/stable/overview/install/": html(f"<p>{LONG}</p>"),
                       "https://tool.example": "<html><body><div id='app'></div><script>render()</script></body></html>"})
    docs = read_docs(candidate(readme), fetch=fetch, file_text=lambda *a: None)
    assert [p["url"] for p in docs["pages"]] == ["https://docs.tool.example/stable/overview/install/"]
    docs = read_docs(candidate("Nothing here."), fetch=fetch, file_text=lambda *a: None)
    assert docs["pages"] == []
    assert docs["tried"] == [{"where": "https://tool.example", "why": "the repository's homepage on GitHub",
                              "outcome": "the page shows no text without JavaScript"}]


def test_requests_per_candidate_are_bounded(monkeypatch):
    monkeypatch.setattr(installdocs, "MAX_REQUESTS", 3)
    readme = " ".join(f"[Install {n}](https://tool.example/install/{n})" for n in range(6))
    fetch = FakeFetch({})  # every page is a 404
    reader = Reader(fetch, lambda *a: None)
    assert reader.read(candidate(readme, homepage=None, full_name="tool/tool")) == []
    assert len(fetch.asked) == 3 and reader.tried[-1]["outcome"] == "request limit reached"


def test_install_pages_become_sources_of_the_extraction_and_of_the_record(db: PipelineDB, tmp_path: Path):
    key = add(db, 1, "someone/tinyq", extraction())
    before = sources_sha(build_sources(db.candidate(key)))
    assert db.candidate(key)["docs"] == [] and db.install_docs(key) is None
    db.save_install_docs(key, {"rule": "install-docs.v1", "tried": [], "fetched_at": "2026-11-16T03:00:00+08:00", "pages": [
        {"url": "https://tinyq.dev/install", "kind": "website", "title": "Install", "truncated": False, "why": "x",
         "text": "Run <source> pipx install tinyq", "fetched_at": "2026-11-16T03:00:00+08:00"}]})
    sources = build_sources(db.candidate(key))
    assert (sources[-1].id, sources[-1].kind, sources[-1].url) == ("docs1", "website", "https://tinyq.dev/install")
    assert "&lt;source>" in sources[-1].text  # a page cannot open a block of its own
    assert sources_sha(sources) != before  # so the next extraction reads it
    write_profiles(db, model=MODEL, out_dir=tmp_path / "out", now=NOW)
    record = json.loads((tmp_path / "out" / "tinyq.json").read_text())
    assert [s for s in record["sources"] if s["id"] == "docs1"] == [
        {"id": "docs1", "kind": "website", "url": "https://tinyq.dev/install", "fetched_at": "2026-11-16T03:00:00+08:00"}]


def test_only_a_tool_without_a_linux_install_path_needs_its_docs():
    pipx = [{"method": "pipx", "command": "pipx install tinyq", "platforms": []}]
    assert needs_install_docs(extraction(install_methods=pipx)) is False
    assert needs_install_docs(extraction(install_methods=[])) is True
    brew_only = [{"method": "brew", "command": "brew install tinyq", "platforms": []}]
    assert needs_install_docs(extraction(install_methods=brew_only)) is True
    assert needs_install_docs(extraction(install_methods=[], kind=cited("library_sdk", "a library"))) is False
    assert needs_install_docs({"not": "an extraction"}) is False


def test_run_docs_reads_once_stores_the_page_and_the_candidate_carries_it(db: PipelineDB):
    key = add(db, 7, "someone/tinyq", extraction(install_methods=[]),
              readme="# tinyq\n\nSee [Installation](https://tinyq.dev/install).\n")
    add(db, 8, "someone/other", extraction())  # has an install path: nothing is fetched for it
    fetch = FakeFetch({"https://tinyq.dev/install": html(f"<p>{LONG}</p><pre>pipx install tinyq</pre>")})
    lines: list[str] = []
    summary = run_docs(db, models=(MODEL,), fetch=fetch, file_text=lambda *a: None, log=lines.append)
    assert summary == {"looked": 1, "read": {"someone/tinyq": ["https://tinyq.dev/install"]}, "none": {}}
    assert lines == ["  someone/tinyq: read https://tinyq.dev/install"]
    assert db.candidate(key)["docs"][0]["url"] == "https://tinyq.dev/install"
    assert [c["docs"][0]["kind"] for c in db.candidates() if c["docs"]] == ["website"]
    assert db.install_docs(key)["tried"][-1]["outcome"] == "read"
    asked = len(fetch.asked)
    again = run_docs(db, models=(MODEL,), fetch=fetch, file_text=lambda *a: None)
    assert again["looked"] == 0 and len(fetch.asked) == asked  # looked at before: left alone


def test_the_agent_gets_the_install_page_as_a_file_to_read():
    ex = ExtractionResult.model_validate(extraction())
    guide = {"url": "https://tinyq.dev/install", "text": "pipx install tinyq\n", "kind": "website"}
    task = VerifyTask(slug="tinyq", repo_url="https://github.com/someone/tinyq", readme="# tinyq\n", extraction=ex,
                      guides=[guide])
    box = FakeBox({})
    prepare_box(box, task)
    assert guide_name(1) == "INSTALL-GUIDE-1.md" and box.files[guide_name(1)] == b"pipx install tinyq\n"
    prompt = render_task(task, plan_for(ex), box, AgentLimits())
    assert "install guide (https://tinyq.dev/install) is saved in the work dir as INSTALL-GUIDE-1.md" in prompt
    assert "pipx install tinyq\n" not in prompt  # read on demand, not put in the prompt


def test_at_the_same_score_a_unix_guide_comes_before_the_mac_and_windows_ones() -> None:
    # ImageMagick, 11/20: Install-mac.txt, Install-unix.txt and Install-windows.txt score the same; the shortest name
    # won, and a tool Linux runs was read from its macOS guide.
    candidate = {"full_name": "ImageMagick/ImageMagick", "readme": "# ImageMagick\n",
                 "repo": {"full_name": "ImageMagick/ImageMagick", "homepage": ""},
                 "files": ["Install-mac.txt", "Install-unix.txt", "Install-windows.txt", "README.md"]}
    assert [link.path for link in find_links(candidate)] == ["Install-unix.txt", "Install-mac.txt",
                                                             "Install-windows.txt"]


def test_the_platform_order_breaks_ties_only() -> None:
    from pickfit.installdocs import _os_rank

    assert [_os_rank(p) for p in ("docs/install-linux.md", "INSTALL-from-source.md", "INSTALL.md",
                                  "docs/install-macos.md", "Install-win32.txt", "docs/windows/README.md")] \
        == [0, 0, 1, 2, 2, 1]  # a folder name does not count, only the file's own
    candidate = {"full_name": "a/b", "readme": "# b\n", "repo": {"full_name": "a/b", "homepage": ""},
                 "files": ["INSTALL-macos.md", "docs/setup-linux.md"]}
    # install (3) outranks setup (2) whatever the platform: the order only breaks ties.
    assert [link.path for link in find_links(candidate)] == ["INSTALL-macos.md", "docs/setup-linux.md"]
