"""Verification Coverage (pickfit/coverage.py, docs/proposals/coverage.md): the model, the gap taxonomy, the
capability registry and the report, tasks and requeue commands; read only, no network, no model call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from test_score import NOW, fake_grade, feature, run, setup_records, with_features
from test_profiles import MODEL

from pickfit import coverage, security
from pickfit.cli import main
from pickfit.schema import UnverifiedReason
from pickfit.score import score_records

DATA = Path(__file__).resolve().parent.parent / "data" / "software"


def record(slug: str = "tool", *, kind: str = "cli_tool", category: str = "dev_cli", runs: list[dict] | None = None,
           platforms: tuple[str, ...] = ("linux", "macos", "windows"), reason: str | None = None,
           security_check: dict | None = None, rubric: bool = True, **extra: Any) -> dict[str, Any]:
    """A record as JSON with what coverage reads; not schema-valid on purpose (coverage needs no more)."""
    runs = runs or []
    passed = [r for r in runs if r["level"] in coverage.PASSED]
    level = min((r["level"] for r in passed), key=coverage.PASSED.index) if passed else (
        "failed" if any(r["level"] == "failed" for r in runs) else "unverified")
    return {"slug": slug, "kind": kind, "category": category, "status": "listed", "platforms": list(platforms),
            "repo": {"full_name": f"a/{slug}"}, "sources": [{"kind": "readme", "id": "readme"}],
            "first_seen_at": "2026-10-29T10:00:00+08:00", "updated_at": "2026-11-05T10:00:00+08:00",
            "verification": {"level": level, "unverified_reason": reason if level == "unverified" else None,
                             "checked_at": max((r["checked_at"] for r in runs), default=None), "runs": runs},
            "security": security_check if security_check is not None else {"version": "sec.v1", "status": "clean",
                                                                            "packages_checked": 12,
                                                                            "checked_at": "2026-11-03T10:00:00+08:00",
                                                                            "sources": ["Cargo.lock"]},
            "scores": {"formula_version": "b3.v6", "computed_at": "2026-11-05T10:00:00+08:00",
                       "quality": {"total": 80.0, "confidence": 0.7, "cap": None, "cap_reason": None,
                                   "components": {"maintenance": {"score": 1.0, "weight": 10},
                                                  "engineering_hygiene": {"score": 0.8, "weight": 5},
                                                  "responsiveness": {"score": None, "weight": 10}}},
                       "popularity": {"score": 20.0, "signals": {"stars": 12}},
                       "treasure": {"is_treasure": True, "value": 64.0},
                       "docs_rubric": {"model": "m", "checked_at": "2026-11-05T10:00:00+08:00"} if rubric else None},
            **extra}


def unverified_run(reason: str, os: str = "linux", checked_at: str = "2026-11-01T10:00:00+08:00") -> dict[str, Any]:
    return run(f"verify-{os}-{reason}", level="unverified", checked_at=checked_at) | {
        "unverified_reason": reason, "os": os, "blocking_error": f"stopped: {reason}"}


def dims(rec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return coverage.compute_coverage(rec)["dimensions"]


def codes(dim: dict[str, Any]) -> list[str]:
    return sorted(g["code"] for g in dim["gaps"])


# --- the taxonomy and the registry ----------------------------------------------------------------------------------


def test_every_code_has_a_category_a_dimension_and_a_capability_in_the_registry() -> None:
    for code, kind in coverage.GAP_CODES.items():
        assert kind.category in coverage.CATEGORIES and kind.dimension in coverage.DIMENSIONS
        assert coverage.registry_entry(kind.capability.format(platform="macos")) is not None, code
        assert any(code in cap.closes for cap in coverage.CAPABILITIES.values()), code
    for cap in coverage.CAPABILITIES.values():
        assert cap.version == max(cap.versions, default=0) and all(c in coverage.GAP_CODES or c in security.GAP_CODES
                                                                   for c in cap.closes)


def test_security_keeps_its_own_codes_and_capabilities() -> None:
    assert not set(coverage.GAP_CODES) & set(security.GAP_CODES)  # nothing redefined
    closed = {c for cap in coverage.CAPABILITIES.values() for c in cap.closes if c in security.GAP_CODES}
    assert closed == set(security.GAP_CODES)
    for code, (category, capability) in security.GAP_CODES.items():  # a security gap reads as security.py wrote it
        g = coverage._security_gap(security.gap(code, "maven", detail="pom.xml"))
        assert (g["code"], g["category"], g["dimension"]) == (code, category, "security")
        assert coverage.registry_entry(g["capability"]) is not None
        assert g["capability"].split(":")[0] == capability.split(":")[0]


def test_capability_specs_parse_and_match_by_base() -> None:
    assert coverage.parse_capability("box_toolchain") == ("box_toolchain", None)
    assert coverage.parse_capability("adapter@2") == ("adapter", 2)
    assert coverage.parse_capability("host:macos@v1") == ("host:macos", 1)
    with pytest.raises(ValueError, match="unknown capability"):
        coverage.parse_capability("teleport")
    with pytest.raises(ValueError, match="a number"):
        coverage.parse_capability("adapter@latest")
    assert coverage.matches_capability("adapter:maven", "adapter") and coverage.matches_capability("adapter:maven",
                                                                                                    "adapter:maven")
    assert not coverage.matches_capability("adapter:maven", "adapter:nuget")
    assert coverage.task_capability({"adapter:maven": 3, "adapter:nuget": 2}) == "adapter"
    assert coverage.task_capability({"host:macos": 3, "host:windows": 2}) == "host"
    assert coverage.task_capability({"test_accounts": 3}) == "test_accounts"


def test_whose_fault_is_failure_py_split_read_as_it_is() -> None:
    from pickfit.verify import failure

    split = coverage.fault_split()
    every = set(get_args(UnverifiedReason.__value__))
    assert split["box"] == {n for n, _ in failure._OUTPUT_LIMITS} | {n for n, _ in failure._PROSE_LIMITS}
    assert split["software"] == {"suspected_tool_fault"}
    assert split["silent"] == every - failure.WRITTEN_REASONS == {"not_run", "budget_exceeded", "other"}
    parts = [split[k] for k in ("box", "software", "placed", "silent")]
    assert set().union(*parts) == every and sum(map(len, parts)) == len(every)  # each reason in exactly one
    # Every reason that is not the software's names an install code (not_run is placed by the claimed platforms).
    assert every - split["software"] - {"not_run"} <= set(coverage._INSTALL_REASONS)


# --- the dimensions ---------------------------------------------------------------------------------------------------


def test_a_software_failure_is_a_quality_result_never_a_gap() -> None:
    install = dims(record(runs=[unverified_run("suspected_tool_fault")]))["install"]
    assert install["status"] == "verified" and install["gaps"] == []
    assert install["measure"]["outcome"] == "tool_fault" and install["measure"]["by_platform"]["macos"] == "proxy"
    root = dims(record(runs=[unverified_run("needs_root")]))["install"]
    assert root["measure"]["by_platform"] == {"linux": "unverified", "macos": "not_run", "windows": "not_run"}
    failed = dims(record(runs=[run(level="failed")]))["install"]
    assert failed["status"] == "verified" and failed["measure"]["outcome"] == "failed"
    function = dims(record(runs=[with_features(feature("a", "checked"), feature("b", "test_failed", "tool"))]))[
        "function"]
    assert function["status"] == "verified" and function["measure"]["judged"] == 2 and function["gaps"] == []
    assert function["measure"]["failed_by_tool"] == 1


@pytest.mark.parametrize(("reason", "code", "platform"), [
    ("needs_root", "install.needs_root", "linux"), ("needs_toolchain", "install.needs_toolchain", "linux"),
    ("needs_container", "install.needs_container", "linux"), ("macos_only", "install.no_host", "macos"),
    ("budget_exceeded", "install.budget_exceeded", "linux"), ("other", "install.unclassified", "linux"),
])
def test_what_the_box_could_not_do_is_a_gap_with_its_capability(reason: str, code: str, platform: str) -> None:
    install = dims(record(runs=[unverified_run(reason)]))["install"]
    assert install["status"] == "unverified" and codes(install) == [code]
    gap = install["gaps"][0]
    assert gap["platform"] == platform and gap["first_seen"] == "2026-11-01" and gap["component"]
    assert coverage.registry_entry(gap["capability"]) is not None


def test_a_record_never_run_is_backlog_where_pickfit_hosts_it_and_no_host_elsewhere() -> None:
    linux = dims(record(reason="not_run"))["install"]
    assert codes(linux) == ["install.not_run"] and linux["gaps"][0]["capability"] == "verify_backlog"
    mac = dims(record(platforms=("macos", "windows"), reason="not_run"))["install"]
    assert codes(mac) == ["install.no_host", "install.no_host"]
    assert {g["capability"] for g in mac["gaps"]} == {"host:macos", "host:windows"}
    rest = dims(record(platforms=("macos",), reason="not_run"))
    assert rest["function"]["blocked_by"] == "install" and rest["function"]["gaps"] == []


def test_one_pass_stands_for_the_other_platforms_except_for_an_app_with_its_own_interface() -> None:
    cli = dims(record(runs=[run()]))["install"]
    assert cli["status"] == "verified" and cli["measure"]["by_platform"] == {"linux": "verified", "macos": "proxy",
                                                                            "windows": "proxy"}
    app = dims(record(kind="desktop_app", runs=[run()]))["install"]
    assert app["status"] == "partial" and app["measure"]["share"] == round(1 / 3, 4)
    assert codes(app) == ["install.platform_not_run", "install.platform_not_run"]
    assert {g["capability"] for g in app["gaps"]} == {"host:macos", "host:windows"}


def test_features_are_measured_and_each_one_not_reached_is_filed() -> None:
    other = {"feature": "e", "status": "not_checked", "reason": "other", "note": "install-only run"}
    replay = {"feature": "f", "status": "not_checked", "reason": "other",
              "note": "its check passed in the agent's box but did not pass again in a fresh box"}
    account = {"feature": "c", "status": "not_checked", "reason": "needs_account"}
    box = feature("d", "test_failed", "sandbox")
    rec = record(runs=[with_features(feature("a", "checked"), feature("b", "test_failed", "tool"), account, box)
                       | {"features": [feature("a", "checked") | {"smoke_tests": [1]},
                                       feature("b", "test_failed", "tool") | {"smoke_tests": [2]},
                                       account, box | {"smoke_tests": [3]}, other, replay]}])
    function = dims(rec)["function"]
    assert function["status"] == "partial" and function["measure"]["judged"] == 2 and function["measure"]["of"] == 6
    assert function["measure"]["reliability"] == round(2 / 3, 4) and function["measure"]["depth"] == "function"
    assert codes(function) == ["function.install_only_run", "function.needs_account", "function.replay_failed",
                               "function.sandbox_unknown"]
    assert {g["component"] for g in function["gaps"]} == {"c", "d", "e", "f"}


def test_without_a_feature_list_depth_decides_whether_function_was_verified() -> None:
    assert dims(record(runs=[run(level="function")]))["function"]["status"] == "verified"
    install_only = dims(record(runs=[run(level="install")]))["function"]
    assert install_only["status"] == "unverified" and codes(install_only) == ["function.no_feature_check"]


def mcp_run(called: str | None = None, **features: Any) -> dict[str, Any]:
    return run(level="service" if called else "function") | {
        "mcp": {"transport": "stdio", "launch": ["srv"], "tools": ["t"], "tool_count": 1, "called_tool": called},
        "features": [{"feature": name, "status": "not_checked", "reason": reason} for name, reason in features.items()]}


def test_an_mcp_server_needs_its_handshake_and_a_tool_call() -> None:
    kind = {"kind": "mcp_server_or_agent_plugin", "category": "mcp_server"}
    handshake = dims(record(runs=[mcp_run(read="needs_account")], **kind))["service"]
    assert handshake["status"] == "partial" and codes(handshake) == ["service.needs_account"]
    assert {"handshake": True, "tool_call": False, "done": 1, "of": 2}.items() <= handshake["measure"].items()
    assert dims(record(runs=[mcp_run("list")], **kind))["service"]["status"] == "verified"
    assert codes(dims(record(runs=[mcp_run()], **kind))["service"]) == ["service.no_tool_call"]
    assert dims(record(runs=[run()]))["service"]["status"] == "not_applicable"  # a CLI tool runs no service


def test_gui_dimensions_apply_to_apps_and_wait_for_what_comes_before() -> None:
    cli = dims(record(runs=[run()]))
    assert cli["usability"]["status"] == cli["preview"]["status"] == "not_applicable"
    nothing = dims(record(kind="desktop_app", platforms=("linux",), reason="not_run"))
    assert nothing["usability"]["blocked_by"] == "install"
    gui = {"tier": "action_checked", "screen": "main_ui", "command": "app", "display": "Xvfb",
           "operations": [{"goal": "save", "passed": True}]}
    operated = dims(record(kind="desktop_app", platforms=("linux",), runs=[run() | {"gui": gui}]))
    assert codes(operated["usability"]) == ["usability.not_judged"]
    recorded = dims(record(kind="desktop_app", platforms=("linux",), runs=[
        run() | {"gui": gui, "video": {"recorded_at": "2026-11-12T10:00:00+08:00", "model": "claude-opus"}}]))
    assert recorded["preview"]["status"] == "verified" and recorded["preview"]["harness_version"] == "claude-opus"
    web = dims(record(kind="web_app", runs=[run() | {"web": {"operations": []}}]))
    assert web["docs"]["status"] == "not_applicable" and web["install"]["measure"]["by_platform"] == {"web": "verified"}


def test_no_preview_is_never_a_gap_since_new_recordings_stopped() -> None:
    # brief §15.7 (11/22): no new tutorial recordings. A GUI or web record without a clip has no preview dimension at
    # all (not a gap, not in the share); the clips made before stay and count.
    gui = {"tier": "action_checked", "screen": "main_ui", "command": "app", "display": "Xvfb",
           "operations": [{"goal": "save", "passed": True}]}
    for rec in (record(kind="desktop_app", platforms=("linux",), reason="not_run"),
                record(kind="desktop_app", platforms=("linux",), runs=[run() | {"gui": gui}]),
                record(kind="desktop_app", platforms=("linux",), runs=[run() | {"gui": gui | {"operations": []}}]),
                record(kind="web_app", runs=[run() | {"web": {"operations": [{"goal": "go", "passed": True}]}}])):
        cov = coverage.compute_coverage(rec)
        preview = cov["dimensions"]["preview"]
        assert preview["status"] == "not_applicable" and preview["gaps"] == [] and not preview.get("blocked_by")
        assert not any(c.startswith("video.") or c.startswith("preview.") for c in coverage.GAP_CODES)
    old = record(kind="desktop_app", platforms=("linux",), runs=[run() | {"gui": gui, "video": {"recorded_at": "x"}}])
    assert dims(old)["preview"]["status"] == "verified"
    assert "video" not in coverage.DIMENSIONS and "preview" in coverage.DIMENSIONS


def test_the_security_dimension_is_security_py_coverage_and_never_its_level() -> None:
    clean = dims(record())["security"]
    assert clean["status"] == "verified" and clean["measure"]["done"] == 12 and clean["harness_version"] == "sec.v1"
    vulnerable = dims(record(security_check={"version": "sec.v1", "status": "vulnerable", "packages_checked": 40,
                                             "findings": [{"package": "npm:zod"}]}))["security"]
    assert vulnerable["status"] == "partial" and codes(vulnerable) == ["security.v1_scope_unknown"]
    unchecked = dims(record(security_check={"version": "sec.v1", "status": "unchecked", "unchecked_reason":
                                            "no_lockfile", "packages_checked": 0}))["security"]
    assert unchecked["status"] == "unverified" and codes(unchecked) == ["lockfile.missing"]  # security.py's own code
    v2 = {"version": "sec.v2", "status": "vulnerable", "assessment": {"level": "exposed", "policy_version": "sec.v2"},
          "coverage": {"state": "partial", "target": "installed_artifact", "packages_found": 300,
                       "packages_checked": 120, "gaps": [security.gap("binary.no_build_info", "crates", "bin/x")]}}
    partial = dims(record(security_check=v2))["security"]
    assert partial["status"] == "partial"
    assert {"done": 120, "of": 300, "share": 0.4, "target": "installed_artifact"}.items() <= partial["measure"].items()
    assert codes(partial) == ["binary.no_build_info"] and partial["harness_version"] == "sec.v2/sec.v2"
    assert "level" not in json.dumps(partial)  # the known findings are not coverage
    assert codes(dims(record(security_check={}) | {"security": None})["security"]) == ["security.not_run"]


def test_docs_and_repository_signals() -> None:
    assert dims(record())["docs"]["status"] == "verified"
    assert codes(dims(record(rubric=False))["docs"]) == ["docs.not_graded"]
    assert codes(dims(record(rubric=False, sources=[{"kind": "github_api"}]))["docs"]) == ["docs.no_readme"]
    repo = dims(record())["repo_signals"]
    assert repo["status"] == "verified" and repo["measure"]["parts"]["responsiveness"] == "thin"
    assert repo["measure"]["reliability"] == {"responsiveness": 0.0}
    rec = record()
    rec["scores"]["inputs"] = {"version": "inputs.v1", "github": {"fetched_at": "2026-11-05T10:00:00+08:00"},
                               "issues": None}
    fetched_nothing = dims(rec)["repo_signals"]
    assert fetched_nothing["status"] == "partial" and codes(fetched_nothing) == ["repo_signals.issues_not_fetched"]
    assert dims(record(repo=None))["repo_signals"]["status"] == "not_applicable"


def test_the_summary_is_the_mean_share_over_applicable_dimensions() -> None:
    cov = coverage.compute_coverage(record(runs=[run()]))
    summary = cov["summary"]
    shares = [coverage.dimension_share(d) for d in cov["dimensions"].values()]
    applicable = [s for s in shares if s is not None]
    assert summary["verified_share"] == round(sum(applicable) / len(applicable), 4)
    assert summary["not_applicable"] == 3 and cov["platforms"] == ["linux", "macos", "windows"]
    assert cov["ecosystems"] == ["crates"]


# --- quality.confidence, derived from the coverage --------------------------------------------------------------------


def test_confidence_from_the_coverage_is_the_formulas_share_of_weight_with_data(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade())
    rec = json.loads((out / "tinyq.json").read_text(encoding="utf-8"))
    q = rec["scores"]["quality"]
    weights = {k: c["weight"] for k, c in q["components"].items()}
    assert coverage.quality_confidence(coverage.compute_coverage(rec), weights) == q["confidence"]
    inputs = coverage.quality_inputs(coverage.compute_coverage(rec))
    assert inputs["sandbox_verification"] and inputs["install_docs"] and not inputs["usage_outcomes"]
    rec["security"] = None  # what a scan could not read never moves it
    assert coverage.quality_confidence(coverage.compute_coverage(rec), weights) == q["confidence"]


@pytest.mark.skipif(not DATA.is_dir(), reason="no data/software here")
def test_confidence_from_the_coverage_matches_every_stored_record() -> None:
    for rec in coverage.load_records(DATA, None):
        q = (rec.get("scores") or {}).get("quality")
        if not q:
            continue
        weights = {k: c["weight"] for k, c in q["components"].items()}
        external = sum(v for v in ((rec.get("outcomes") or {}).get("external") or {}).values() if isinstance(v, int))
        assert coverage.quality_confidence(coverage.compute_coverage(rec), weights, external) == q["confidence"], \
            rec["slug"]


# --- many records: report, tasks, requeue -----------------------------------------------------------------------------


def corpus() -> list[dict[str, Any]]:
    account = {"feature": "c", "status": "not_checked", "reason": "needs_account"}
    return [
        record("a", runs=[unverified_run("needs_toolchain", checked_at="2026-11-01T10:00:00+08:00")]),
        record("b", runs=[unverified_run("needs_toolchain", checked_at="2026-11-17T10:00:00+08:00")]),
        record("c", runs=[run() | {"features": [account]}], category="mcp_server"),
        record("d", runs=[run() | {"features": [account]}], kind="desktop_app", category="other"),
        record("e", platforms=("macos",), reason="not_run", security_check={
            "version": "sec.v1", "status": "unchecked", "unchecked_reason": "no_lockfile", "packages_checked": 0}),
    ]


def write_corpus(tmp_path: Path) -> Path:
    data = tmp_path / "software"
    data.mkdir()
    for rec in corpus():
        (data / f"{rec['slug']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return data


def test_the_report_groups_coverage_and_ranks_gap_codes_by_records_blocked() -> None:
    rep = coverage.report(corpus(), as_of="2026-11-19")
    assert rep["records"] == 5 and set(rep["by_dimension"]) == set(coverage.DIMENSIONS)
    ranked = list(rep["gap_codes"].values())
    assert [r["records"] for r in ranked] == sorted((r["records"] for r in ranked), reverse=True)
    top = rep["gap_codes"]["install.needs_toolchain"]
    assert top["records"] == 2 and top["examples"] == ["a", "b"] and top["capabilities"] == {"box_toolchain": 2}
    assert rep["gap_codes"]["function.needs_account"]["categories"] == {"mcp_server": 1, "other": 1}
    assert rep["gap_codes"]["lockfile.missing"]["dimension"] == "security"
    assert set(rep["by_platform"]) == {"linux", "macos", "windows"} and "dev_cli" in rep["by_category"]
    assert rep["unknown_by_dimension_and_category"]["function:blocked_by_install"] == 3
    text = coverage.render_report(rep)
    assert "## Gap codes by records blocked" in text and "install.needs_toolchain" in text


def test_report_reads_the_records_and_writes_only_its_dated_snapshot(tmp_path: Path, capsys: Any) -> None:
    data = write_corpus(tmp_path)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    (snaps / "2026-11-12.json").write_text(json.dumps({"as_of": "2026-11-12", "verified_share": 0.5}))
    target = snaps / "2026-11-19.json"
    assert main(["coverage", "report", "--data-dir", str(data), "--snapshot", str(target), "--date",
                 "2026-11-19"]) == 0
    out = capsys.readouterr().out
    assert "previous snapshot 2026-11-12: 50%" in out
    assert json.loads(target.read_text())["records"] == 5
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before
    assert main(["coverage", "report", "--data-dir", str(data), "--no-snapshot", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "cov.v1"


def test_tasks_rank_harness_work_and_print_jsonl(tmp_path: Path, capsys: Any) -> None:
    rows = coverage.tasks(corpus())
    assert rows[0]["records_blocked"] >= rows[-1]["records_blocked"] and rows[0]["rank"] == 1
    toolchain = next(r for r in rows if r["code"] == "install.needs_toolchain")
    assert toolchain["capability"] == "box_toolchain" and toolchain["capability_version"] == 1
    assert toolchain["issue"] == "H-002" and "rerun" in toolchain["task"]
    accounts = next(r for r in rows if r["code"] == "function.needs_account")
    assert accounts["capability_version"] == 0 and accounts["task"].startswith("build test_accounts")
    assert [r["code"] for r in coverage.tasks(corpus(), dimension="security")] == ["lockfile.missing"]
    assert main(["coverage", "tasks", "--data-dir", str(write_corpus(tmp_path)), "--format", "jsonl"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {"code", "records_blocked", "categories", "platforms", "ecosystems", "examples", "capability"} <= set(lines[0])


def test_requeue_lists_what_a_shipped_capability_can_now_verify_and_writes_nothing(tmp_path: Path,
                                                                                   capsys: Any) -> None:
    result = coverage.requeue(corpus(), "box_toolchain")
    assert result["since"] == "2026-11-16" and result["built"] and result["dry_run"]
    assert [(r["slug"], r["dimension"]) for r in result["rows"]] == [("a", "install")]  # b was checked since
    assert result["rows"][0]["codes"] == ["install.needs_toolchain"] and "loop_state.py add" in result["rows"][0][
        "rerun"]
    waiting = coverage.requeue(corpus(), "test_accounts")
    assert not waiting["built"] and {r["slug"] for r in waiting["rows"]} == {"c", "d"}
    assert {r["dimension"] for r in waiting["rows"]} == {"function"}
    assert coverage.requeue(corpus(), "box_toolchain@2")["built"] is False  # a version not built yet: all wait
    assert len(coverage.requeue(corpus(), "box_toolchain@2")["rows"]) == 2
    host = coverage.requeue(corpus(), "host:macos@1")  # d: a desktop app run on Linux before; e: never run
    assert [(r["slug"], r["codes"]) for r in host["rows"]] == [("d", ["install.platform_not_run"]),
                                                              ("e", ["install.no_host"])]
    data = write_corpus(tmp_path)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    assert main(["coverage", "requeue", "--data-dir", str(data), "--capability", "lockfile_from_manifest"]) == 0
    assert "dry run, nothing written" in capsys.readouterr().out
    assert main(["coverage", "requeue", "--data-dir", str(data), "--capability", "warp_drive"]) == 2
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before


def test_a_security_estimate_is_read_in_memory_with_security_py_codes() -> None:
    estimate = {"rows": {"e": {"level": "none", "coverage": "partial", "status": "unchecked", "checked": 40,
                               "found": 90, "gaps": [{"code": "adapter.missing", "category": "no_adapter",
                                                      "ecosystem": "maven", "component": "pom.xml", "found": 50}]}}}
    records = corpus()
    estimated = coverage.with_security_estimate(records, estimate)
    assert records[4]["security"]["version"] == "sec.v1"  # the records themselves are not changed
    dim = coverage.compute_coverage(estimated[4])["dimensions"]["security"]
    assert dim["status"] == "partial" and dim["measure"]["share"] == round(40 / 90, 4)
    assert dim["gaps"][0]["capability"] == "adapter:maven" and dim["gaps"][0]["found"] == 50
    assert estimated[0] is records[0]  # not in the estimate: kept


def test_the_distribution_counts_unknowns_by_dimension_reason_category_and_platform(tmp_path: Path,
                                                                                     capsys: Any) -> None:
    rows = coverage.distribution(corpus())["rows"]
    key = {(r["dimension"], r["gap_category"], r["category"], r["platform"]): r["records"] for r in rows}
    assert key[("install", "sandbox_missing", "dev_cli", "linux")] == 2
    assert key[("install", "no_host", "dev_cli", "macos")] == 1
    assert key[("function", "needs_account", "other", "linux")] == 1
    if coverage.rules_available():
        pytest.skip("with the scoring patch applied its own tests cover the rules")
    assert main(["coverage", "rules", "--data-dir", str(write_corpus(tmp_path))]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["rules"] is None and "coverage-scoring-b3v7.patch" in captured.err


def test_capabilities_lists_the_registry_and_the_taxonomy(capsys: Any) -> None:
    assert main(["coverage", "capabilities"]) == 0
    out = capsys.readouterr().out
    assert "| box_toolchain | 1 | 2026-11-16 |" in out and "| function.not_shown | function | check_unconfirmed |" in out
