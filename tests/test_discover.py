"""Discovery with a mocked GitHub: no request ever leaves the process."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest

from pickfit.discover import github as gh_module
from pickfit.discover.github import (
    GitHub,
    GitHubError,
    Query,
    build_queries,
    normalize_release,
    normalize_repo,
)
from pickfit.discover.rules import classify
from pickfit.discover.run import apply_rules, run_discover
from pickfit.discover.store import PipelineDB, repo_key

TOKEN = "gho_test0123456789SECRET"


def repo_item(repo_id: int, full_name: str = "someone/tinyq", **extra: Any) -> dict[str, Any]:
    owner, name = full_name.split("/")
    item = {
        "id": repo_id, "full_name": full_name, "name": name, "owner": {"login": owner},
        "html_url": f"https://github.com/{full_name}", "description": "A tiny query tool",
        "homepage": "", "language": "Rust", "topics": ["CLI", "rust"], "stargazers_count": 42,
        "forks_count": 3, "open_issues_count": 1, "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-10-20T00:00:00Z", "pushed_at": "2026-10-20T00:00:00Z",
        "archived": False, "disabled": False, "fork": False, "is_template": False,
        "default_branch": "main", "size": 120, "has_issues": True,
        "license": {"spdx_id": "MIT"},
    }
    item.update(extra)
    return item


class FakeGitHub:
    """Answers GitHub REST paths from a routing function and records every request."""

    def __init__(self, route: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.route = route
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.route(request)

    def client(self, tmp_path: Path, **kwargs: Any) -> GitHub:
        http = httpx2.Client(base_url=gh_module.API, transport=httpx2.MockTransport(self))
        return GitHub(TOKEN, http=http, trace_dir=tmp_path / "traces", **kwargs)


def json_response(payload: Any, status: int = 200, headers: dict[str, str] | None = None) -> httpx2.Response:
    return httpx2.Response(status, json=payload, headers=headers or {})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(gh_module, "sleep", slept.append)
    return slept


# --- queries --------------------------------------------------------------------


def test_build_queries_fills_dates_per_category() -> None:
    queries = build_queries(date(2026, 10, 28), pushed_days=14)
    assert [q.id for q in queries] == [
        "dev_cli:cli", "dev_cli:tui", "dev_cli:terminal",
        "local_ai:local-llm", "local_ai:ollama", "local_ai:llama-cpp",
    ]
    assert queries[0].q == ("topic:cli created:>=2026-01-01 pushed:>=2026-10-14 stars:5..300 "
                            "fork:false archived:false")


def test_build_queries_filters_and_rejects_unknown_categories() -> None:
    assert {q.category for q in build_queries(date(2026, 10, 28), categories=["local_ai"])} == {"local_ai"}
    with pytest.raises(ValueError, match="unknown categories"):
        build_queries(date(2026, 10, 28), categories=["voice"])


# --- client -----------------------------------------------------------------------


def test_searches_are_spaced_and_traced_without_the_token(tmp_path: Path, no_sleep: list[float],
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 0.0, 0.5, 0.5, 0.6, 0.6, 3.0, 3.0])
    monkeypatch.setattr(gh_module, "monotonic", lambda: next(clock))
    fake = FakeGitHub(lambda r: json_response({"total_count": 1, "items": [repo_item(1)]}))
    gh = fake.client(tmp_path)
    query = Query("dev_cli", "cli", "topic:cli")
    gh.search_repositories(query)
    gh.search_repositories(query)
    assert no_sleep == [pytest.approx(2.1 - 0.5)]
    assert fake.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert fake.requests[0].url.params["q"] == "topic:cli"
    assert fake.requests[0].url.params["sort"] == "updated"
    lines = [json.loads(line) for path in (tmp_path / "traces").iterdir()
             for line in path.read_text().splitlines()]
    assert [line["query_id"] for line in lines] == ["dev_cli:cli", "dev_cli:cli"]
    assert lines[0]["q"] == "topic:cli" and lines[0]["total_count"] == 1 and lines[0]["ts"]
    assert TOKEN not in (tmp_path / "traces").iterdir().__next__().read_text()


def test_search_all_pages_until_max_results(tmp_path: Path) -> None:
    def route(request: httpx2.Request) -> httpx2.Response:
        page = int(request.url.params["page"])
        start = (page - 1) * 100
        return json_response({"total_count": 500, "items": [repo_item(start + i + 1) for i in range(100)]})

    fake = FakeGitHub(route)
    results = list(fake.client(tmp_path, search_interval_s=0).search_all(Query("c", "t", "q"), 150))
    assert len(results) == 150
    assert [r.url.params["page"] for r in fake.requests] == ["1", "2"]
    assert results[-1][0] == 150 and results[-1][2] == 500


def test_search_all_stops_on_a_short_page(tmp_path: Path) -> None:
    fake = FakeGitHub(lambda r: json_response({"total_count": 2, "items": [repo_item(1), repo_item(2)]}))
    assert len(list(fake.client(tmp_path).search_all(Query("c", "t", "q"), 100))) == 2
    assert len(fake.requests) == 1


def test_rate_limit_waits_for_reset_then_retries(tmp_path: Path, no_sleep: list[float],
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh_module.time, "time", lambda: 1000.0)
    replies = [
        json_response({"message": "API rate limit exceeded"}, 403,
                      {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"}),
        json_response({"message": "secondary rate limit"}, 429, {"retry-after": "7"}),
        json_response([]),
    ]
    fake = FakeGitHub(lambda r: replies.pop(0))
    assert fake.client(tmp_path).releases("someone/tinyq") == []
    assert no_sleep == [31.0, 7.0]


def test_rate_limit_too_far_away_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh_module.time, "time", lambda: 1000.0)
    fake = FakeGitHub(lambda r: json_response({"message": "API rate limit exceeded"}, 403,
                                              {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "5000"}))
    with pytest.raises(GitHubError, match="rate limited"):
        fake.client(tmp_path).releases("someone/tinyq")


def test_server_errors_retry_then_raise_without_token(tmp_path: Path) -> None:
    fake = FakeGitHub(lambda r: json_response({"message": "boom"}, 502))
    with pytest.raises(GitHubError) as err:
        fake.client(tmp_path).releases("someone/tinyq")
    assert len(fake.requests) == gh_module.SERVER_ERROR_TRIES
    assert TOKEN not in str(err.value)


def test_readme_decodes_base64_and_missing_readme_is_none(tmp_path: Path) -> None:
    content = base64.b64encode("# tinyq\n\n`brew install tinyq`\n".encode()).decode()

    def route(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/repos/someone/tinyq/readme":
            return json_response({"path": "README.md", "encoding": "base64", "content": content})
        return json_response({"message": "Not Found"}, 404)

    gh = FakeGitHub(route).client(tmp_path)
    assert gh.readme("someone/tinyq") == ("# tinyq\n\n`brew install tinyq`\n", "README.md")
    assert gh.readme("someone/empty") == (None, None)


def test_details_fetch_only_manifests_present_in_tree(tmp_path: Path) -> None:
    def route(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path.endswith("/readme"):
            return json_response({"path": "README.md", "encoding": "base64",
                                  "content": base64.b64encode(b"# hi").decode()})
        if path.endswith("/releases"):
            return json_response([
                {"tag_name": "v0.2.0", "name": "", "published_at": "2026-10-01T00:00:00Z",
                 "html_url": "https://github.com/someone/tinyq/releases/tag/v0.2.0", "draft": False,
                 "prerelease": False, "body": "notes",
                 "assets": [{"name": "tinyq-aarch64-apple-darwin.tar.gz", "download_count": 9}]},
                {"tag_name": "v0.3.0-draft", "draft": True},
            ])
        if "/git/trees/" in path:
            assert request.url.params["recursive"] == "1"
            return json_response({"tree": [{"path": "Cargo.toml", "type": "blob"},
                                           {"path": "src", "type": "tree"},
                                           {"path": "src/main.rs", "type": "blob"}],
                                  "truncated": False})
        if path == "/repos/someone/tinyq/contents/Cargo.toml":
            assert request.headers["accept"] == "application/vnd.github.raw+json"
            return httpx2.Response(200, text='[package]\nname = "tinyq"\n')
        raise AssertionError(f"unexpected request {path}")

    fake = FakeGitHub(route)
    details = fake.client(tmp_path).details(normalize_repo(repo_item(1)))
    assert details["readme"] == "# hi"
    assert details["files"] == ["Cargo.toml", "src/main.rs"]
    assert list(details["manifests"]) == ["Cargo.toml"]
    assert [r["tag"] for r in details["releases"]] == ["v0.2.0"]
    assert details["releases"][0]["name"] is None
    assert details["releases"][0]["assets"] == [{"name": "tinyq-aarch64-apple-darwin.tar.gz", "downloads": 9}]


def test_normalize_repo() -> None:
    repo = normalize_repo(repo_item(7, homepage="  ", license={"spdx_id": "NOASSERTION"}, description=" x "))
    assert repo["id"] == 7 and repo["owner"] == "someone"
    assert repo["homepage"] is None and repo["license"] is None and repo["description"] == "x"
    assert repo["topics"] == ["cli", "rust"]
    assert normalize_repo(repo_item(8, license=None))["license"] is None


def test_normalize_release_clips_body() -> None:
    release = normalize_release({"tag_name": "v1", "body": "x" * 10_000, "assets": None})
    assert len(release["body"]) == 4000 and release["assets"] == []


# --- store ------------------------------------------------------------------------


def test_repo_key() -> None:
    assert repo_key(123) == "gh:123"
    for bad in (0, -1, True, "123"):
        with pytest.raises(ValueError):
            repo_key(bad)  # type: ignore[arg-type]


def test_upsert_dedupes_by_repo_id_and_keeps_old_names(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    assert db.upsert_repo(normalize_repo(repo_item(1, "someone/tinyq")), category="dev_cli",
                          query_id="dev_cli:cli") is True
    assert db.upsert_repo(normalize_repo(repo_item(1, "someone/tinyq")), category="dev_cli",
                          query_id="dev_cli:tui") is False
    assert db.upsert_repo(normalize_repo(repo_item(1, "neworg/tinyq")), category="local_ai",
                          query_id="local_ai:ollama") is False
    (c,) = db.candidates()
    assert c["repo_id"] == "gh:1" and c["full_name"] == "neworg/tinyq"
    assert c["aliases"] == ["someone/tinyq"]
    assert c["queries"] == ["dev_cli:cli", "dev_cli:tui", "local_ai:ollama"]
    assert c["categories"] == ["dev_cli", "local_ai"] and c["category"] == "local_ai"
    db.upsert_repo(normalize_repo(repo_item(1, "someone/tinyq")), category="dev_cli", query_id="dev_cli:cli")
    assert db.candidate("gh:1")["aliases"] == ["neworg/tinyq"]


def test_needs_details_until_saved_and_again_after_a_push(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    db.upsert_repo(normalize_repo(repo_item(1)), category="dev_cli", query_id="q")
    assert [r["repo_id"] for r in db.needs_details()] == ["gh:1"]
    details = {"readme": "# hi", "readme_path": "README.md", "releases": [], "files": [],
               "files_truncated": False, "manifests": {}}
    db.save_details("gh:1", details, pushed_at="2026-10-20T00:00:00Z")
    assert db.needs_details() == []
    db.upsert_repo(normalize_repo(repo_item(1, pushed_at="2026-10-27T00:00:00Z")), category="dev_cli",
                   query_id="q")
    assert [r["repo_id"] for r in db.needs_details()] == ["gh:1"]
    db.save_details("gh:1", None, pushed_at="2026-10-27T00:00:00Z", error="HTTP 500")
    assert [r["repo_id"] for r in db.needs_details()] == ["gh:1"]


# --- rules ------------------------------------------------------------------------


def candidate(readme: str | None = "# tool", files: list[str] | None = None,
              manifests: dict[str, str] | None = None, releases: list[dict[str, Any]] | None = None,
              **repo: Any) -> dict[str, Any]:
    return {"repo": normalize_repo(repo_item(1, **repo)), "readme": readme,
            "files": files if files is not None else ["src/main.py"], "files_truncated": False,
            "manifests": manifests or {}, "releases": releases or []}


@pytest.mark.parametrize(("repo", "reason"), [
    ({"fork": True}, "reject:fork"),
    ({"archived": True}, "reject:archived"),
    ({"is_template": True}, "reject:github_template"),
    ({"description": "Bulk-create accounts in seconds"}, "reject:abuse_keywords"),
])
def test_hard_rejects(repo: dict[str, Any], reason: str) -> None:
    result = classify(candidate(**repo))
    assert (result.label, result.passed) == ("rejected", False)
    assert reason in result.reasons


def test_no_readme_is_rejected() -> None:
    assert "reject:no_readme" in classify(candidate(readme="  ")).reasons


def test_tool_with_entry_point_and_install_command() -> None:
    readme = "# tinyq\n\n## Installation\n\n```\ncargo install tinyq\n```\n\n## Usage\n\ntinyq '.a'\n"
    result = classify(candidate(readme, files=["Cargo.toml", "src/main.rs"]))
    assert (result.label, result.passed) == ("tool", True)
    assert "+entry_point:cargo bin" in result.reasons and "+readme_install_command" in result.reasons


def test_release_binaries_are_a_strong_tool_signal() -> None:
    releases = [{"assets": [{"name": "tinyq-x86_64-unknown-linux-gnu.tar.gz", "downloads": 1}]}]
    assert classify(candidate("# tinyq", releases=releases, topics=[])).label == "tool"


def test_awesome_list_is_not_software() -> None:
    readme = "# Awesome local AI\n" + "".join(f"- [x{i}](https://x{i}.dev)\n" for i in range(50))
    result = classify(candidate(readme, files=["README.md"], name="awesome-local-ai",
                                full_name="someone/awesome-local-ai", topics=["awesome-list"]))
    assert (result.label, result.passed) == ("non_software", False)
    assert "reject:non_software" in result.reasons


def test_library_without_entry_point() -> None:
    readme = "# tinyq\n\n```python\nfrom tinyq import Query\n```\n"
    result = classify(candidate(readme, files=["pyproject.toml", "tinyq/__init__.py"],
                                manifests={"pyproject.toml": "[project]\nname = 'tinyq'\n"},
                                description="A Python library for queries", topics=[]))
    assert (result.label, result.passed) == ("library", False)


def test_unclear_repo_goes_to_the_model() -> None:
    result = classify(candidate("# tinyq\n\nSome words.", topics=[]))
    assert (result.label, result.passed) == ("uncertain", True)


def test_owner_burst_is_flagged_not_rejected() -> None:
    result = classify(candidate("# tinyq\n\n## Install\n\n`pipx install tinyq`"), {"someone": 6})
    assert result.passed and "flag:owner_burst(6)" in result.reasons


# --- whole discover run -----------------------------------------------------------


def test_run_discover_end_to_end(tmp_path: Path) -> None:
    readme = base64.b64encode(b"# tinyq\n\n## Install\n\n`brew install tinyq`\n").decode()

    def route(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/search/repositories":
            q = request.url.params["q"]
            if q.startswith("topic:cli "):
                return json_response({"total_count": 2, "items": [repo_item(1), repo_item(2, "a/b", fork=True)]})
            if q.startswith("topic:ollama "):
                return json_response({"total_count": 1, "items": [repo_item(1)]})
            return json_response({"total_count": 0, "items": []})
        if path.endswith("/readme"):
            return json_response({"path": "README.md", "encoding": "base64", "content": readme})
        if path.endswith("/releases"):
            return json_response([])
        if "/git/trees/" in path:
            return json_response({"tree": [{"path": "main.go", "type": "blob"}], "truncated": False})
        raise AssertionError(path)

    fake = FakeGitHub(route)
    lines: list[str] = []
    funnel = run_discover(token=TOKEN, db_path=tmp_path / "pipeline.db", per_query=10,
                          today=date(2026, 10, 28), gh=fake.client(tmp_path, search_interval_s=0),
                          log=lines.append)
    assert funnel["discover"]["candidates"] == 2
    assert funnel["discover"]["by_category"] == {"local_ai": 1, "dev_cli": 1}
    assert funnel["discover"]["in_both_categories"] == 1
    assert len(funnel["discover"]["queries"]) == 6
    assert funnel["rules"] == {**funnel["rules"], "checked": 2, "passed": 1,
                               "by_label": {"tool": 1, "rejected": 1}}
    assert funnel["rules"]["reject_reasons"] == {"reject:fork": 1}
    assert funnel["prescreen"]["status"] in ("skipped", "not_built")
    assert any(line.startswith("github requests:") for line in lines)
    # A second run fetches no details again: nothing was pushed in between.
    before = len(fake.requests)
    run_discover(token=TOKEN, db_path=tmp_path / "pipeline.db", per_query=10, today=date(2026, 10, 28),
                 gh=fake.client(tmp_path, search_interval_s=0), log=lines.append)
    assert len(fake.requests) - before == 6


def test_apply_rules_skips_repos_without_details(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    db.upsert_repo(normalize_repo(repo_item(1)), category="dev_cli", query_id="q")
    assert apply_rules(db) == {}
