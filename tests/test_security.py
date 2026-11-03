"""pickfit.security (sec.v1): resolving what a fresh install brings, OSV findings, and the known_vulnerability cap."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pickfit import security
from pickfit.index import _security
from pickfit.ledger import TAIPEI
from pickfit.schema import QUALITY_CAPS, TREASURE_MIN_QUALITY, SecurityCheck, SoftwareRecord, binding_cap
from pickfit.score import build_web_scores, refresh_scores

ROOT = Path(__file__).resolve().parents[1]
WEB_FIXTURE = ROOT / "worker" / "test" / "fixtures" / "software" / "fixture-web-sketch.json"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=TAIPEI)

FINDING = {"package": "npm:undici", "version": "8.9.0", "advisory": "GHSA-2m5v-pch6-74hx", "cves": [],
           "severity": "HIGH", "fixed_in": "8.12.2", "summary": "TLS certificate validation bypass", "malicious": False}


def check(status: str = "vulnerable", **over: Any) -> dict[str, Any]:
    base = {"version": "sec.v1", "status": status, "unchecked_reason": None, "sources": ["npm:x (fresh install, 3 packages)"],
            "packages_checked": 3, "findings": [FINDING] if status == "vulnerable" else [], "database": "OSV.dev",
            "checked_at": NOW.isoformat()}
    if status == "unchecked":
        base.update(unchecked_reason="no_source", sources=[], packages_checked=0)
    base |= over
    return base | {"findings_total": over.get("findings_total", len(base["findings"]))}


def scored_web(security_check: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.loads(WEB_FIXTURE.read_text(encoding="utf-8"))
    if security_check is not None:
        data["security"] = security_check
    data["scores"] = build_web_scores(SoftwareRecord.model_validate(data), stars=None, hn=4, now=NOW)
    return data


# --- schema and cap ---------------------------------------------------------------------------------------------------


def test_the_cap_sits_just_below_treasure() -> None:
    assert QUALITY_CAPS["known_vulnerability"] == TREASURE_MIN_QUALITY - 1
    assert binding_cap("cli_tool", False, "function", check()) == "known_vulnerability"
    assert binding_cap("cli_tool", False, "function", check("clean")) is None
    assert binding_cap("cli_tool", False, "function", check("unchecked")) is None
    assert binding_cap("cli_tool", False, "unverified", check()) == "unverified"  # the lowest cap wins
    assert binding_cap("cli_tool", False, "function", None) is None


@pytest.mark.parametrize("bad", [
    {"status": "vulnerable", "findings": []},
    {"status": "clean", "findings": [FINDING]},
    {"status": "unchecked", "unchecked_reason": None},
    {"status": "unchecked", "unchecked_reason": "no_source", "packages_checked": 4},
    {"status": "vulnerable", "findings_total": 0},
])
def test_status_follows_findings(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SecurityCheck.model_validate(check(**bad))


def test_a_vulnerable_record_is_capped_and_loses_treasure() -> None:
    clean = scored_web(check("clean"))
    assert clean["scores"]["treasure"]["is_treasure"] and clean["scores"]["quality"]["total"] > 79
    vulnerable = scored_web(check())
    q = vulnerable["scores"]["quality"]
    assert (q["total"], q["cap"], q["cap_reason"]) == (79, 79, "known_vulnerability")
    assert vulnerable["scores"]["treasure"]["is_treasure"] is False
    SoftwareRecord.model_validate(vulnerable)


def test_unchecked_keeps_the_score() -> None:
    assert scored_web(check("unchecked"))["scores"]["quality"] == scored_web()["scores"]["quality"]


def test_refresh_applies_and_lifts_the_cap() -> None:
    data = scored_web(check("clean"))
    data["security"] = check()
    assert refresh_scores(data, NOW) == "scores refreshed from the record"
    assert data["scores"]["quality"]["cap_reason"] == "known_vulnerability"
    with pytest.raises(ValidationError):  # a stored score that ignores the check does not validate
        SoftwareRecord.model_validate(scored_web(check("clean")) | {"security": check()})
    data["security"] = check("clean")
    refresh_scores(data, NOW)
    assert data["scores"]["quality"]["cap_reason"] is None and data["scores"]["treasure"]["is_treasure"]


def test_write_security_stores_caps_and_hides_a_malicious_package(tmp_path: Path) -> None:
    path = tmp_path / "fixture-web-sketch.json"
    path.write_text(json.dumps(scored_web()), encoding="utf-8")
    bad = FINDING | {"package": "npm:evil", "advisory": "MAL-2026-1", "severity": "CRITICAL", "malicious": True}
    written = security.write_security(path, check(findings=[bad]), NOW)
    assert written["status"] == "hidden" and "MAL-2026-1" in written["status_reason"]
    assert list(written).index("security") == list(written).index("scores") - 1
    stored = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    assert stored.security.status == "vulnerable" and stored.scores.quality.cap_reason == "known_vulnerability"


def test_index_entry_says_what_the_page_shows() -> None:
    assert _security(SoftwareRecord.model_validate(scored_web())) == {"status": "unchecked", "reason": "not_run"}
    entry = _security(SoftwareRecord.model_validate(scored_web(check(findings_total=75))))
    assert entry["status"] == "vulnerable" and entry["count"] == 75 and entry["findings"][0]["fixed_in"] == "8.12.2"
    entry = _security(SoftwareRecord.model_validate(scored_web(check("unchecked"))))
    assert entry == {"status": "unchecked", "checked_at": "2026-11-03", "reason": "no_source"}


# --- resolving --------------------------------------------------------------------------------------------------------


def test_cvss3_base_matches_the_specification() -> None:
    assert security.cvss3_base("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == 9.8
    assert security.cvss3_base("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    assert security.cvss3_base("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N") == 5.5
    assert security.cvss3_base("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N") == 0.0
    assert security.cvss3_base("not a vector") is None


def test_npm_lock_leaves_out_dev_the_root_and_workspace_members() -> None:
    lock = {"packages": {"": {"name": "app", "version": "1.0.0"},
                         "packages/core": {"name": "evil-name-on-npm", "version": "0.1.0"},
                         "node_modules/undici": {"version": "8.9.0"},
                         "node_modules/vite": {"version": "6.0.0", "dev": True},
                         "node_modules/a/node_modules/@s/b": {"version": "2.0.0"}}}
    assert security.npm_lock_nodes(lock) == [("npm", "undici", "8.9.0"), ("npm", "@s/b", "2.0.0")]


def test_uv_lock_keeps_the_run_time_closure() -> None:
    lock = {"package": [
        {"name": "tool", "version": "0.1.0", "source": {"editable": "."}, "dependencies": [{"name": "httpx"}],
         "dev-dependencies": {"dev": [{"name": "pytest"}]}},
        {"name": "httpx", "version": "0.28.0", "dependencies": [{"name": "certifi"}]},
        {"name": "certifi", "version": "2026.1.1"},
        {"name": "pytest", "version": "9.0.0"},
    ]}
    assert security._uv_lock_nodes(lock) == [("pypi", "certifi", "2026.1.1"), ("pypi", "httpx", "0.28.0")]


CARGO = '[[package]]\nname = "zip"\nversion = "8.6.0"\nsource = "registry+x"\n\n[[package]]\nname = "mytool"\nversion = "0.1.0"\n'


def test_repo_nodes_skip_parts_a_user_does_not_install(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text(CARGO)
    (tmp_path / "website").mkdir()
    (tmp_path / "website" / "package-lock.json").write_text(json.dumps(
        {"packages": {"node_modules/next": {"version": "16.0.0"}}}))
    (tmp_path / "go.mod").write_text("module example.com/t\n\ngo 1.22\n\nrequire (\n\tgithub.com/a/b v1.2.3 // indirect\n)\n")
    for part in (".claude/skills/x", "tools", "third_party/lib", "spikes", "fuzz", "testdata", "skills/y", "probes"):
        (tmp_path / part).mkdir(parents=True)
        (tmp_path / part / "Cargo.lock").write_text('[[package]]\nname = "old"\nversion = "0.1.0"\nsource = "registry+x"\n')
    repo = security.repo_nodes(tmp_path)
    assert repo.nodes == [("crates", "zip", "8.6.0"), ("go", "github.com/a/b", "v1.2.3")]
    assert repo.read == ["Cargo.lock", "go.mod"] and repo.complete and repo.reason is None


def test_repo_with_only_an_unsupported_lockfile_says_so(tmp_path: Path) -> None:
    (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")
    repo = security.repo_nodes(tmp_path)
    assert (repo.nodes, repo.complete, repo.reason) == ([], False, "lockfile_not_supported")


def test_an_unreadable_root_lockfile_leaves_the_read_incomplete(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("not toml [[[")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/a": {"version": "1.0.0"}}}))
    repo = security.repo_nodes(tmp_path)
    assert repo.nodes == [("npm", "a", "1.0.0")] and (repo.complete, repo.reason) == (False, "lockfile_not_supported")


def test_a_lockfile_counts_only_when_it_yields_packages(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests\nrich>=13\n")  # nothing pinned
    repo = security.repo_nodes(tmp_path)
    assert (repo.read, repo.complete, repo.reason) == ([], False, "no_lockfile")


def test_each_pyproject_resolves_on_its_own_and_a_failing_root_one_is_unresolved(monkeypatch: pytest.MonkeyPatch,
                                                                               tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='root'\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "pyproject.toml").write_text("[project]\nname='sub'\n")

    def fake(path: Path) -> list[Any]:
        if path.parent == tmp_path:
            raise RuntimeError("no")
        return [("pypi", "rich", "13.0.0")]

    monkeypatch.setattr(security, "resolve_pyproject", fake)
    repo = security.repo_nodes(tmp_path)
    assert repo.read == ["sub/pyproject.toml (resolved today)"] and (repo.complete, repo.reason) == (False, "resolve_failed")


PNPM_V9 = """lockfileVersion: '9.0'

settings:
  autoInstallPeers: true

importers:

  .:
    devDependencies:
      wrangler:
        specifier: ^4.0.0
        version: 4.120.0

  apps/desktop:
    dependencies:
      '@me/sdk':
        specifier: workspace:*
        version: link:../../packages/sdk
      '@ai-sdk/provider-utils':
        specifier: ^5.0.0
        version: 5.0.23(zod@4.4.3)
    devDependencies:
      electron:
        specifier: ^42.0.0
        version: 42.0.0
      vite:
        specifier: ^8.0.0
        version: 8.0.14

  docs:
    dependencies:
      next:
        specifier: ^16.0.0
        version: 16.0.10

packages:

  '@ai-sdk/provider-utils@5.0.23':
    resolution: {integrity: sha512-x}
    peerDependencies:
      zod: ^4.0.0

snapshots:

  '@ai-sdk/provider-utils@5.0.23(zod@4.4.3)':
    dependencies:
      undici: 7.29.0
      zod: 4.4.3
    optionalDependencies:
      fsevents: 2.3.3

  undici@7.29.0: {}

  zod@4.4.3: {}

  fsevents@2.3.3: {}
"""

PNPM_V6 = """lockfileVersion: '6.0'

dependencies:
  chalk:
    specifier: ^5.0.0
    version: 5.3.0

devDependencies:
  vitest:
    specifier: ^1.0.0
    version: 1.0.0

packages:

  /chalk@5.3.0:
    resolution: {integrity: sha512-y}
    dependencies:
      ansi-styles: 6.2.1
    dev: false

  /ansi-styles@6.2.1:
    resolution: {integrity: sha512-z}
    dev: false
"""


def test_pnpm_v9_reads_what_installs_at_run_time() -> None:
    nodes = security.pnpm_lock_nodes(PNPM_V9)
    assert sorted(nodes) == sorted([("npm", "electron", "42.0.0"), ("npm", "@ai-sdk/provider-utils", "5.0.23"),
                                    ("npm", "undici", "7.29.0"), ("npm", "zod", "4.4.3"), ("npm", "fsevents", "2.3.3")])
    # Not wrangler (the root's dev tool), vite (a dev dependency), the docs site, or the workspace link.


def test_pnpm_v6_without_workspaces() -> None:
    assert security.pnpm_lock_nodes(PNPM_V6) == [("npm", "chalk", "5.3.0"), ("npm", "ansi-styles", "6.2.1")]


def test_pnpm_older_lockfiles_are_not_read() -> None:
    with pytest.raises(ValueError):
        security.pnpm_lock_nodes("lockfileVersion: 5.4\n")


def test_a_root_pnpm_lock_is_a_main_lockfile(tmp_path: Path) -> None:
    (tmp_path / "pnpm-lock.yaml").write_text(PNPM_V9)
    repo = security.repo_nodes(tmp_path)
    assert repo.complete and repo.read == ["pnpm-lock.yaml"] and len(repo.nodes) == 5
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n")
    repo = security.repo_nodes(tmp_path)
    assert (repo.complete, repo.reason) == (False, "lockfile_not_supported")


def test_npm_platform_builds_do_not_count_as_dependencies() -> None:
    lock = {"packages": {"": {"name": "probe"}, "node_modules/tool": {"version": "1.0.0"},
                         "node_modules/@x/tool-darwin-arm64": {"version": "1.0.0", "optional": True, "os": ["darwin"],
                                                               "cpu": ["arm64"]}}}
    assert security.npm_lock_nodes(lock, platform=False) == [("npm", "tool", "1.0.0")]
    assert len(security.npm_lock_nodes(lock)) == 2


def test_packages_of_takes_only_the_softwares_own_packages() -> None:
    raw = {"slug": "tool", "name": "Tool", "repo": {"full_name": "someone/tool-repo"}, "aliases": [],
           "verification": {"runs": [{"steps": [
               {"command": "npm install -g @scope/tool && tool --version"},
               {"command": "npm install left-pad"},  # local: a project's dependency
               {"command": "pip install --user --break-system-packages numpy gmpy2"},  # prerequisites
               {"command": "pip install --no-deps tool-repo"},  # its own, under the repository's name
               {"command": "uv tool install git+https://github.com/a/b"},
               {"command": "pipx install pytest"}]}]},
           "scores": {"popularity": {"packages": ["pypi:tool-py", "homebrew:tool"]}}}
    assert security.packages_of(raw) == ["pypi:tool-py", "npm:@scope/tool", "pypi:tool-repo"]
    raw["verification"]["runs"][0]["steps"] = [{"command": "npm i -g @tool/server"}]  # its own scope
    assert security.packages_of(raw) == ["pypi:tool-py", "npm:@tool/server"]
    raw["verification"]["runs"][0]["steps"] = [{"command": "pip install aiohttp"}]
    raw["scores"] = None
    assert security.packages_of(raw) == []  # the repository decides


def _resolving(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, graphs: dict[str, Any],
               repo: security.RepoRead | None) -> list[str]:
    """Stub the resolvers (name -> (nodes, real dependencies) or an exception), the clone and OSV (no findings)."""
    cloned: list[str] = []

    def resolver(name: str) -> Any:
        if isinstance(graphs[name], Exception):
            raise graphs[name]
        return graphs[name]

    def fake_clone(url: str, slug: str, clones: Path = tmp_path) -> tuple[Path, str]:
        cloned.append(url)
        return tmp_path, "0123456789abcdef"

    monkeypatch.setattr(security, "RESOLVERS", {"npm": resolver, "pypi": resolver, "crates": resolver})
    monkeypatch.setattr(security, "clone", fake_clone)
    monkeypatch.setattr(security, "repo_nodes", lambda root: repo)
    monkeypatch.setattr(security, "findings_for", lambda nodes, advisories, unrated=None: [])
    return cloned


RECORD = {"slug": "rtool", "name": "rtool", "repo": {"url": "https://github.com/o/rtool", "full_name": "o/rtool"},
          "verification": {"runs": []}, "scores": {"popularity": {"packages": ["crates:rtool"]}}}
FULL = security.RepoRead([("crates", "zip", "8.6.0")], ["Cargo.lock"], True, None)
NO_LOCK = security.RepoRead([], [], False, "no_lockfile")


def check_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: dict[str, Any], graphs: dict[str, Any],
               repo: security.RepoRead | None) -> tuple[dict[str, Any], list[str]]:
    cloned = _resolving(monkeypatch, tmp_path, graphs, repo)
    return security.check(raw, security.Advisories(), now=NOW), cloned


def test_every_own_package_resolved_with_dependencies_is_clean_without_the_repository(monkeypatch: pytest.MonkeyPatch,
                                                                                     tmp_path: Path) -> None:
    result, cloned = check_with(monkeypatch, tmp_path, RECORD,
                                {"rtool": ([("crates", "rtool", "1.0.0"), ("crates", "zip", "9.0.5")], 1)}, NO_LOCK)
    assert not cloned and result["status"] == "clean" and result["packages_checked"] == 2


def test_a_crate_without_a_dependency_graph_falls_back_to_the_repository(monkeypatch: pytest.MonkeyPatch,
                                                                        tmp_path: Path) -> None:
    result, cloned = check_with(monkeypatch, tmp_path, RECORD, {"rtool": RuntimeError("no graph")}, FULL)
    assert cloned == ["https://github.com/o/rtool"] and result["status"] == "clean"
    assert result["sources"] == ["github.com/o/rtool@0123456789ab", "Cargo.lock"]


def test_a_wrapper_is_clean_only_if_the_repository_is(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wrapper = {"rtool": ([("npm", "rtool", "1.0.0"), ("npm", "@r/rtool-linux-x64", "1.0.0")], 0)}
    result, cloned = check_with(monkeypatch, tmp_path, RECORD, wrapper, FULL)
    assert cloned and result["status"] == "clean" and result["packages_checked"] == 3
    result, _ = check_with(monkeypatch, tmp_path, RECORD, wrapper, NO_LOCK)
    assert (result["status"], result["unchecked_reason"]) == ("unchecked", "resolve_failed")


def test_one_own_package_failing_sends_the_check_to_the_repository(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path) -> None:
    raw = {**RECORD, "scores": {"popularity": {"packages": ["pypi:rtool", "crates:rtool-rt"]}}}
    graphs = {"rtool": ([("pypi", "rtool", "1.0"), ("pypi", "rich", "13.0")], 1), "rtool-rt": RuntimeError("no graph")}
    result, cloned = check_with(monkeypatch, tmp_path, raw, graphs, NO_LOCK)
    assert cloned and (result["status"], result["unchecked_reason"]) == ("unchecked", "resolve_failed")
    result, _ = check_with(monkeypatch, tmp_path, raw, graphs, FULL)
    assert result["status"] == "clean"


def test_without_findings_an_incomplete_read_is_unchecked_not_clean(monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    partial = security.RepoRead([("npm", "a", "1.0.0")], ["web/package-lock.json"], False, "lockfile_not_supported")
    result, _ = check_with(monkeypatch, tmp_path, RECORD, {"rtool": RuntimeError("no graph")}, partial)
    assert (result["status"], result["unchecked_reason"]) == ("unchecked", "lockfile_not_supported")
    no_repo = {**RECORD, "repo": None}
    result, _ = check_with(monkeypatch, tmp_path, no_repo, {"rtool": ([("crates", "rtool", "1.0.0")], 0)}, None)
    assert (result["status"], result["unchecked_reason"]) == ("unchecked", "resolve_failed")
    nothing = {**no_repo, "scores": None}
    result, _ = check_with(monkeypatch, tmp_path, nothing, {}, None)
    assert (result["status"], result["unchecked_reason"]) == ("unchecked", "no_source")


def test_clean_needs_what_was_read() -> None:
    with pytest.raises(ValidationError):
        SecurityCheck.model_validate(check("clean", packages_checked=0))
    with pytest.raises(ValidationError):
        SecurityCheck.model_validate(check("clean", sources=[]))


# --- OSV findings (no network) ----------------------------------------------------------------------------------------


ADVISORIES = {
    "GHSA-aaaa-bbbb-cccc": {"id": "GHSA-aaaa-bbbb-cccc", "aliases": ["CVE-2026-1"], "summary": "bad",
                            "database_specific": {"severity": "HIGH"},
                            "affected": [{"package": {"ecosystem": "npm", "name": "undici"},
                                          "ranges": [{"events": [{"introduced": "0"}, {"fixed": "7.29.1"},
                                                                 {"introduced": "8.0.0"}, {"fixed": "8.12.2"}]}]}]},
    "GHSA-mmmm-mmmm-mmmm": {"id": "GHSA-mmmm-mmmm-mmmm", "summary": "medium", "database_specific": {"severity": "MODERATE"}},
    "RUSTSEC-2026-0001": {"id": "RUSTSEC-2026-0001", "aliases": ["GHSA-rrrr-rrrr-rrrr"], "summary": "rust hole",
                          "affected": [{"package": {"ecosystem": "crates.io", "name": "zip"}, "ranges": []}]},
    "GHSA-rrrr-rrrr-rrrr": {"id": "GHSA-rrrr-rrrr-rrrr", "database_specific": {"severity": "CRITICAL"}},
    "RUSTSEC-2026-0002": {"id": "RUSTSEC-2026-0002", "summary": "Bincode is unmaintained",
                          "affected": [{"database_specific": {"informational": "unmaintained"}}]},
    "RUSTSEC-2026-0003": {"id": "RUSTSEC-2026-0003", "summary": "no rating"},
    "MAL-2026-9": {"id": "MAL-2026-9", "summary": "Malicious code in evil"},
}


def test_findings_count_high_critical_and_malicious_only(monkeypatch: pytest.MonkeyPatch) -> None:
    hits = {("undici", "8.9.0"): ["GHSA-aaaa-bbbb-cccc", "GHSA-mmmm-mmmm-mmmm"],
            ("zip", "8.6.0"): ["RUSTSEC-2026-0001", "GHSA-rrrr-rrrr-rrrr", "RUSTSEC-2026-0002", "RUSTSEC-2026-0003"],
            ("evil", "1.0.0"): ["MAL-2026-9"]}

    def fake_http(url: str, body: Any = None, tries: int = 4) -> Any:
        if url.endswith("/querybatch"):
            return {"results": [{"vulns": [{"id": i} for i in hits.get((q["package"]["name"], q["version"]), [])]}
                                for q in body["queries"]]}
        return ADVISORIES[url.rsplit("/", 1)[1]]

    monkeypatch.setattr(security, "_http", fake_http)
    unrated: list[str] = []
    found = security.findings_for([("npm", "undici", "8.9.0"), ("crates", "zip", "8.6.0"), ("npm", "evil", "1.0.0")],
                                  security.Advisories(), unrated)
    assert [(f["package"], f["advisory"], f["severity"], f["fixed_in"], f["malicious"]) for f in found] == [
        ("npm:evil", "MAL-2026-9", "CRITICAL", None, True),
        ("crates:zip", "RUSTSEC-2026-0001", "CRITICAL", None, False),  # its GHSA alias is not counted twice
        ("npm:undici", "GHSA-aaaa-bbbb-cccc", "HIGH", "8.12.2", False),
    ]
    assert unrated == ["crates:zip@8.6.0 RUSTSEC-2026-0003"]
    for f in found:
        SecurityCheck.model_validate(check(findings=[f]))


def test_a_record_with_nothing_to_read_is_unchecked() -> None:
    raw = {"slug": "x", "verification": {"runs": []}, "scores": None, "repo": None}
    result = security.check(raw, security.Advisories(), now=NOW)
    assert (result["status"], result["unchecked_reason"]) == ("unchecked", "no_source")
    SecurityCheck.model_validate(result)
