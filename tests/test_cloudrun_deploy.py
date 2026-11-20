"""scripts/cloudrun_deploy.py: which pushes deploy, and the after-deploy check and rollback, without network."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from scripts import cloudrun_deploy as cd

SHA = "ab" * 32
OLD = "cd" * 32


def service(latest: str, traffic: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": {"latestReadyRevisionName": latest, "latestCreatedRevisionName": latest, "traffic": traffic}}


class FakeGcloud:
    def __init__(self, described: dict[str, Any]) -> None:
        self.described = described
        self.routes: list[tuple[str, ...]] = []

    def describe(self) -> dict[str, Any]:
        return self.described

    def route(self, *traffic: str) -> None:
        self.routes.append(traffic)


class Site:
    """Answers / with each health payload in turn (the last one repeats) and /mcp with one answer."""

    def __init__(self, health: list[Any], mcp: tuple[int, str, str] | None = None) -> None:
        self.health = health
        self.mcp = mcp or (200, "text/event-stream", "event: message\ndata: " + json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "find_software"}, {"name": "get_install_guide"}]}}
        ) + "\n\n")
        self.calls: list[str] = []

    def __call__(self, url: str, *, data: bytes | None = None, headers: dict[str, str], timeout: float = 30):
        self.calls.append(url)
        if url.endswith("/mcp"):
            assert json.loads(data or b"{}")["method"] == "tools/list"
            return self.mcp
        payload = self.health.pop(0) if len(self.health) > 1 else self.health[0]
        if isinstance(payload, Exception):
            raise payload
        return 200, "application/json", json.dumps(payload)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def run_verify(gcloud: FakeGcloud, site: Site, prev: str | None = "pickfit-00006-old", **kwargs) -> tuple[int, list[str]]:
    lines: list[str] = []
    clock = Clock()
    code = cd.verify(prev, expect_sha=SHA, site="https://x.test", min_entries=1000, timeout=60, interval=10,
                     gcloud=gcloud, fetch=site, clock=clock, sleep=clock.sleep, out=lines.append, **kwargs)
    return code, lines


GOOD = {"entries": 1211, "data_sha256": SHA}
NEW_SERVING = service("pickfit-00007-new", [{"latestRevision": True, "percent": 100, "revisionName": "pickfit-00007-new"}])


@pytest.mark.parametrize(("paths", "deploy"), [
    (["data/software/ripgrep.json"], True),
    (["data/i18n/zh-TW/ripgrep.json"], True),
    (["worker/src/page.ts"], True),
    (["worker/wrangler.jsonc"], True),
    (["worker/cloudrun/deploy.sh"], True),
    (["pickfit/index.py"], True),
    (["uv.lock"], True),
    ([".github/workflows/worker.yml"], True),
    (["worker/bench/capability/x.json", "worker/test/find.test.ts", "worker/README.md", "worker/cloudrun/README.md"], False),
    (["pickfit/watch.py", "docs/plan.md", "tests/test_index.py"], False),
    ([], False),
])
def test_only_paths_that_change_the_site_deploy(paths: list[str], deploy: bool) -> None:
    assert cd.needs_deploy(paths) is deploy


def test_changed_paths_without_a_base_is_unknown() -> None:
    assert cd.changed_paths("0" * 40, "HEAD") is None
    assert cd.changed_paths("", "HEAD") is None
    failed = lambda *a, **k: subprocess.CompletedProcess(a, 128, "", "bad object")  # noqa: E731
    assert cd.changed_paths("abc", "def", run=failed) is None
    ok = lambda *a, **k: subprocess.CompletedProcess(a, 0, "worker/src/a.ts\ndata/software/b.json\n", "")  # noqa: E731
    assert cd.changed_paths("abc", "def", run=ok) == ["worker/src/a.ts", "data/software/b.json"]


def test_serving_revision_reads_latest_and_pinned_traffic() -> None:
    assert cd.serving_revision(service("r2", [{"latestRevision": True, "percent": 100}])) == "r2"
    assert cd.serving_revision(service("r2", [{"revisionName": "r1", "percent": 100}, {"latestRevision": True, "percent": 0}])) == "r1"
    assert cd.serving_revision(service("r3", [{"revisionName": "r1", "percent": 10}, {"revisionName": "r2", "percent": 90}])) == "r2"
    assert cd.serving_revision({}) is None


def test_health_problem() -> None:
    assert cd.health_problem(GOOD, SHA, 1000) is None
    assert "not abababababab" in cd.health_problem({"entries": 1211, "data_sha256": OLD}, SHA, 1000)
    assert "fewer than 1000" in cd.health_problem({"entries": 12, "data_sha256": SHA}, SHA, 1000)
    assert "JSON object" in cd.health_problem("<html>", SHA, 1000)


def test_parse_mcp_body_reads_sse_and_json() -> None:
    sse = 'event: message\r\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\r\n\r\n'
    assert cd.parse_mcp_body("text/event-stream", sse) == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    assert cd.parse_mcp_body("application/json", '{"id":1}') == [{"id": 1}]
    assert cd.parse_mcp_body("application/json", '[{"id":1},{"id":2}]') == [{"id": 1}, {"id": 2}]


def test_tools_problem() -> None:
    good = [{"id": 1, "result": {"tools": [{"name": "find_software"}, {"name": "get_install_guide"}]}}]
    assert cd.tools_problem(good) is None
    assert "lacks get_install_guide" in cd.tools_problem([{"id": 1, "result": {"tools": [{"name": "find_software"}]}}])
    assert "failed" in cd.tools_problem([{"id": 1, "error": {"code": -32000, "message": "Forbidden"}}])
    assert "no JSON-RPC answer" in cd.tools_problem([{"id": 7, "result": {}}])


def test_a_good_deploy_passes_after_waiting_for_the_new_data() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    site = Site([{"entries": 1200, "data_sha256": OLD}, GOOD])
    code, lines = run_verify(gcloud, site)
    assert code == 0
    assert gcloud.routes == []
    assert site.calls == ["https://x.test/", "https://x.test/", "https://x.test/mcp"]
    assert any("waiting" in line for line in lines)


def test_data_that_never_arrives_rolls_back() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    code, lines = run_verify(gcloud, Site([{"entries": 1200, "data_sha256": OLD}]))
    assert code == 1
    assert gcloud.routes == [("--to-revisions=pickfit-00006-old=100",)]
    assert any("not abababababab" in line for line in lines)


def test_too_few_entries_roll_back() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    code, _ = run_verify(gcloud, Site([{"entries": 3, "data_sha256": SHA}]))
    assert code == 1 and gcloud.routes == [("--to-revisions=pickfit-00006-old=100",)]


def test_network_errors_are_retried_until_the_timeout() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    code, _ = run_verify(gcloud, Site([OSError("connection reset"), GOOD]))
    assert code == 0 and gcloud.routes == []


def test_a_broken_mcp_rolls_back() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    site = Site([GOOD], mcp=(403, "application/json", '{"jsonrpc":"2.0","id":null,"error":{"message":"Invalid Host"}}'))
    code, lines = run_verify(gcloud, site)
    assert code == 1
    assert gcloud.routes == [("--to-revisions=pickfit-00006-old=100",)]
    assert any("/mcp answered 403" in line for line in lines)


def test_no_new_revision_fails_without_touching_traffic() -> None:
    gcloud = FakeGcloud(service("pickfit-00006-old", [{"latestRevision": True, "percent": 100}]))
    code, lines = run_verify(gcloud, Site([GOOD]))
    assert code == 1 and gcloud.routes == []
    assert any("did not take" in line for line in lines)


def test_traffic_pinned_by_an_earlier_rollback_moves_to_the_new_revision() -> None:
    pinned = service("pickfit-00008-new", [{"revisionName": "pickfit-00006-old", "percent": 100}])
    gcloud = FakeGcloud(pinned)
    code, _ = run_verify(gcloud, Site([GOOD]))
    assert code == 0
    assert gcloud.routes == [("--to-latest",)]


def test_a_failure_without_a_previous_revision_fails_without_rollback() -> None:
    gcloud = FakeGcloud(NEW_SERVING)
    code, lines = run_verify(gcloud, Site([{"entries": 3, "data_sha256": SHA}]), prev=None)
    assert code == 1 and gcloud.routes == []
    assert any("nothing to roll back" in line for line in lines)


def test_changed_command_prints_a_github_output_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert cd.main(["changed", "--base", "0" * 40]) == 0
    assert capsys.readouterr().out.strip() == "deploy=true"
