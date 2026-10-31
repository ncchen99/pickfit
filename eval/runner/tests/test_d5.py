"""Tests for eval/runner/d5_check.py on synthetic logs and records (no model calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import d5_check  # noqa: E402


def record(evidence: Path, run_id: str, *, os="linux", arch="x86_64", level="function",
           checked_at="2026-10-29T01:00:00+08:00", commands=("uv tool install demo 2>&1", "demo --help")):
    folder = evidence / run_id
    folder.mkdir(parents=True)
    (folder / "verification_run.json").write_text(json.dumps(
        {"id": run_id, "os": os, "arch": arch, "level": level, "method": "sandbox", "checked_at": checked_at}))
    (folder / "report.json").write_text(json.dumps({"commands": [{"command": c, "exit_code": 0} for c in commands]}))


def stream_with(calls: list[tuple[str, dict, dict]]) -> str:
    lines = []
    for i, (name, args, body) in enumerate(calls):
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{i}", "name": f"mcp__pickfit__{name}", "input": args}]}}))
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": [{"type": "text", "text": json.dumps(body)}]}]}}))
    return "\n".join(lines) + "\n"


def setup(tmp_path: Path, calls, started="2026-11-02T10:00:00+08:00"):
    runs, evidence, manifest = tmp_path / "runs", tmp_path / "evidence", tmp_path / "manifest.json"
    record(evidence, "verify-demo-1")
    manifest.write_text(json.dumps({"runs": {"verify-demo-1": {"slug": "demo"}}}))
    folder = runs / "run1" / "q01" / "experimental" / "attempt-1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"question": "q01", "group": "experimental", "attempt": 1,
                                                  "started_at": started}))
    (folder / "stream.jsonl").write_text(stream_with(calls))
    return d5_check.run(["run1"], runs, evidence, manifest)


def pick(**over):
    base = {"slug": "demo", "name": "Demo", "fit": "Fits.", "tradeoffs": [], "vs_well_known": None, "why": [],
            "verification": {"level": "function", "os": "linux", "arch": "x86_64", "method": "sandbox",
                             "verified_on_user_os": True}}
    base.update(over)
    return base


def test_backed_claims_are_found(tmp_path: Path) -> None:
    report = setup(tmp_path, [("find_software", {"need": "x", "os": "linux"}, {"picks": [pick()]})])
    assert report["violations"] == 0 and report["found"] == 2  # (a) and (b)


def test_wrong_os_or_higher_level_is_a_violation(tmp_path: Path) -> None:
    bad = pick(verification={"level": "service", "os": "macos", "arch": "arm64", "method": "sandbox",
                             "verified_on_user_os": True})
    report = setup(tmp_path, [("find_software", {"need": "x", "os": "macos"}, {"picks": [bad]})])
    assert report["violations"] == 1  # one response x one tool x one os, though (a) and (b) both fail
    assert {c["status"] for c in report["claims"]} == {"not_found"}


def test_install_guide_steps_must_match_verbatim(tmp_path: Path) -> None:
    good = {"slug": "demo", "verification": {"status": "verified", "level": "function", "os": "linux", "arch": "x86_64"},
            "steps": [{"command": "uv tool install demo 2>&1"}]}
    edited = dict(good, steps=[{"command": "uv tool install demo"}])
    assert setup(tmp_path / "a", [("get_install_guide", {"slug": "demo", "os": "linux"}, good)])["violations"] == 0
    assert setup(tmp_path / "b", [("get_install_guide", {"slug": "demo", "os": "linux"}, edited)])["violations"] == 1


def test_record_must_be_earlier_than_the_attempt(tmp_path: Path) -> None:
    report = setup(tmp_path, [("find_software", {"need": "x"}, {"picks": [pick()]})], started="2026-10-29T00:30:00+08:00")
    assert report["violations"] == 1


def test_model_text_claims_and_negations(tmp_path: Path) -> None:
    text = pick(tradeoffs=["Not verified on macOS, only verified on linux x86_64."],
                fit="pickfit tested it on Windows.")
    report = setup(tmp_path, [("find_software", {"need": "x"}, {"picks": [text]})])
    e_claims = [c for c in report["claims"] if c["source"] == "e"]
    assert sorted(c["os"] for c in e_claims) == ["linux", "windows"]
    assert {c["os"]: c["status"] for c in e_claims} == {"linux": "found", "windows": "not_found"}


def test_unparseable_response_is_listed_not_dropped(tmp_path: Path) -> None:
    runs, evidence, manifest = tmp_path / "runs", tmp_path / "evidence", tmp_path / "m.json"
    manifest.write_text(json.dumps({"runs": {}}))
    folder = runs / "run1" / "q02" / "rules_only" / "attempt-1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"question": "q02", "group": "rules_only", "attempt": 1,
                                                  "started_at": "2026-11-02T10:00:00+08:00"}))
    (folder / "stream.jsonl").write_text(
        json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "mcp__pickfit__find_software", "input": {}}]}}) + "\n" +
        json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "rec_0123abcd4567 ... [truncated"}]}}) + "\n")
    report = d5_check.run(["run1"], runs, evidence, manifest)
    assert report["unreadable_responses"][0]["rec_id"] == "rec_0123abcd4567"
    assert report["cannot_check"] == 1


def claims_for(tmp_path: Path, pick_over=None, body_over=None, args=None):
    body = {"picks": [pick(**(pick_over or {}))]}
    body.update(body_over or {})
    return setup(tmp_path, [("find_software", args or {"need": "x"}, body)])


def test_an_os_list_is_not_cut_at_commas(tmp_path: Path) -> None:
    report = claims_for(tmp_path, {"fit": "pickfit tested it on Linux, macOS and Windows."})
    assert sorted(c["os"] for c in report["claims"] if c["source"] == "e") == ["linux", "macos", "windows"]
    assert report["violations"] == 2


def test_negation_only_removes_the_os_it_precedes(tmp_path: Path) -> None:
    report = claims_for(tmp_path, {"tradeoffs": ["Verified on Linux and macOS (not Windows).",
                                                 "Tested on macOS with no GPU required."]})
    e = sorted((c["os"], c["text"][:12]) for c in report["claims"] if c["source"] == "e")
    assert [os for os, _ in e] == ["linux", "macos", "macos"]


def test_apple_silicon_and_mac_words_are_macos_with_arch(tmp_path: Path) -> None:
    report = claims_for(tmp_path, {"vs_well_known": "Checked on Apple Silicon Macs by pickfit."})
    claim = next(c for c in report["claims"] if c["source"] == "e")
    assert (claim["os"], claim["arch"]) == ("macos", "arm64") and claim["status"] == "not_found"


def test_reason_sentences_and_answer_level_fields_are_scanned(tmp_path: Path) -> None:
    report = claims_for(
        tmp_path,
        {"why": [{"claim": "Confirmed on Windows.", "field": "summary", "value": "a tool"}]},
        {"best_free": {"slug": "demo", "reason": "Free, and verified on macOS."},
         "well_known_option": {"name": "Other", "why": "It is free and tested on Linux."}})
    by = {(c["slug"], c["os"]): c["status"] for c in report["claims"] if c["source"] == "e"}
    assert by == {("demo", "windows"): "not_found", ("demo", "macos"): "not_found",
                  ("well_known:Other", "linux"): "not_found"}


def test_human_records_do_not_back_a_claim(tmp_path: Path) -> None:
    runs, evidence, manifest = tmp_path / "runs", tmp_path / "evidence", tmp_path / "manifest.json"
    record(evidence, "human-1")
    run_path = evidence / "human-1" / "verification_run.json"
    run_path.write_text(json.dumps({**json.loads(run_path.read_text()), "method": "human"}))
    manifest.write_text(json.dumps({"runs": {"human-1": {"slug": "demo"}}}))
    folder = runs / "run1" / "q01" / "experimental" / "attempt-1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"question": "q01", "group": "experimental", "attempt": 1,
                                                  "started_at": "2026-11-02T10:00:00+08:00"}))
    (folder / "stream.jsonl").write_text(stream_with([("find_software", {"need": "x"}, {"picks": [pick()]})]))
    assert d5_check.run(["run1"], runs, evidence, manifest)["violations"] == 1


def test_install_guide_verify_and_setup_commands_must_match_too(tmp_path: Path) -> None:
    guide = {"slug": "demo", "verification": {"status": "verified", "level": "function", "os": "linux", "arch": "x86_64"},
             "steps": [{"command": "uv tool install demo 2>&1"}], "verify": {"command": "demo --version"}}
    assert setup(tmp_path, [("get_install_guide", {"slug": "demo", "os": "linux"}, guide)])["violations"] == 1


def test_evidence_that_differs_from_the_manifest_is_reported(tmp_path: Path) -> None:
    evidence, manifest = tmp_path / "evidence", tmp_path / "manifest.json"
    record(evidence, "verify-demo-1")
    manifest.write_text(json.dumps({"runs": {"verify-demo-1": {"slug": "demo", "files": {"report.json": "0" * 64}}}}))
    problems = d5_check.evidence_integrity(evidence, manifest, tmp_path / "versions-before.json")
    assert problems == ["verify-demo-1/report.json differs from the manifest"]


# --- GUI, MCP, features, how_we_know, rules labels (added 10/31) -------------------------


def replay(evidence: Path, run_id: str, checks: list[dict], level: str = "function", judge: dict | None = None,
           feature_judge: dict | None = None) -> None:
    folder = evidence / run_id
    (folder / "replay.json").write_text(json.dumps({"result": {"level": level, "passed": True, "checks": checks}}))
    if judge is not None:
        (folder / "judge.json").write_text(json.dumps(judge))
    if feature_judge is not None:
        (folder / "feature_judge.json").write_text(json.dumps({"verdicts": feature_judge}))


def run_with(tmp_path: Path, calls, prepare) -> dict:
    runs, evidence, manifest = tmp_path / "runs", tmp_path / "evidence", tmp_path / "manifest.json"
    record(evidence, "verify-demo-1", level="service")
    prepare(evidence)
    manifest.write_text(json.dumps({"runs": {"verify-demo-1": {"slug": "demo"}}}))
    folder = runs / "run1" / "q01" / "experimental" / "attempt-1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"question": "q01", "group": "experimental", "attempt": 1,
                                                  "started_at": "2026-11-02T10:00:00+08:00"}))
    (folder / "stream.jsonl").write_text(stream_with(calls))
    return d5_check.run(["run1"], runs, evidence, manifest)


GUI_CHECK = {"command": "demo-app", "kind": "gui", "passed": True, "offline": True,
             "run": {"stdout": "gui tier: window (a window of the app's own process is shown)"}}


def by_kind(report: dict) -> dict:
    return {(c["kind"], c["source"]): c["status"] for c in report["claims"]}


def test_gui_claims_need_the_launch_the_screen_and_the_offline_pass(tmp_path: Path) -> None:
    gui = {"tier": "ui_rendered", "screen": "main_ui", "display": "Xvfb", "launch_offline": True}
    body = {"picks": [pick(verification={"level": "install", "os": "linux", "arch": "x86_64", "method": "sandbox",
                                         "verified_on_user_os": None, "gui": gui})]}
    calls = [("find_software", {"need": "x"}, body)]
    ok = run_with(tmp_path / "a", calls, lambda ev: replay(ev, "verify-demo-1", [GUI_CHECK], judge={"screen": "main_ui"}))
    assert by_kind(ok)[("gui", "a")] == "found" and ok["violations"] == 0
    bad = run_with(tmp_path / "b", calls, lambda ev: replay(ev, "verify-demo-1", [GUI_CHECK], judge={"screen": "sign_in_wall"}))
    assert by_kind(bad)[("gui", "a")] == "not_found" and bad["violations"] == 1
    assert "sign_in_wall" in next(c["reason"] for c in bad["claims"] if c["kind"] == "gui")
    online_only = dict(GUI_CHECK, offline=False)
    off = run_with(tmp_path / "c", calls, lambda ev: replay(ev, "verify-demo-1", [online_only], judge={"screen": "main_ui"}))
    assert off["violations"] == 1


MCP_STDOUT = "initialize: ok\ntools/list: ok count=2\ntool: alpha args=x*\ntool: beta args=\n"


def mcp_checks(offline: bool = True) -> list[dict]:
    return [{"command": "python3 probe.py -- demo", "kind": "mcp", "passed": True, "offline": offline,
             "run": {"stdout": MCP_STDOUT}},
            {"command": "python3 probe.py --call alpha --args '{}' -- demo", "kind": "mcp_call", "passed": True,
             "offline": offline, "run": {"stdout": MCP_STDOUT + "tools/call: ok"}}]


def guide(**mcp_over) -> dict:
    mcp = {"tools": ["alpha", "beta"], "tool_count": 2, "called_tool": "alpha", "works_offline": True}
    mcp.update(mcp_over)
    return {"slug": "demo", "verification": {"status": "verified", "level": "service", "os": "linux", "arch": "x86_64"},
            "steps": [{"command": "uv tool install demo 2>&1"}], "mcp_client_config": mcp,
            "how_we_know": "pickfit installed it in a fresh linux/x86_64 sandbox (modal) and replayed the steps from "
                           "scratch on 2026-10-28; an MCP client handshake over stdio listed its 2 tools with the "
                           "network off, and a call to alpha returned a result."}


def test_mcp_claims_are_the_handshake_and_the_calls_of_the_replay(tmp_path: Path) -> None:
    calls = [("get_install_guide", {"slug": "demo", "os": "linux"}, guide())]
    ok = run_with(tmp_path / "a", calls, lambda ev: replay(ev, "verify-demo-1", mcp_checks(), level="service"))
    kinds = by_kind(ok)
    assert kinds[("mcp", "d")] == "found" and kinds[("mcp", "c")] == "found" and kinds[("level", "c")] == "found"
    assert ok["violations"] == 0
    wrong_call = [("get_install_guide", {"slug": "demo", "os": "linux"}, guide(called_tool="gamma"))]
    assert run_with(tmp_path / "b", wrong_call, lambda ev: replay(ev, "verify-demo-1", mcp_checks(), level="service"))["violations"] == 1
    online = run_with(tmp_path / "c", calls, lambda ev: replay(ev, "verify-demo-1", mcp_checks(offline=False), level="service"))
    assert {c["kind"] for c in online["claims"] if c["status"] == "not_found"} == {"mcp"}
    extra_tool = [("get_install_guide", {"slug": "demo", "os": "linux"}, guide(tools=["alpha", "beta", "delta"], tool_count=3))]
    assert run_with(tmp_path / "d", extra_tool, lambda ev: replay(ev, "verify-demo-1", mcp_checks(), level="service"))["violations"] == 1


def test_a_checked_feature_needs_its_passing_check_and_the_judge(tmp_path: Path) -> None:
    feats = {"recorded": True, "checked": [{"feature": "Convert files", "check": "demo convert in.txt"}],
             "not_checked": [{"feature": "Sync", "reason": "test_failed", "detail": "its test failed"}]}
    body = {"picks": [pick(features=feats)]}
    calls = [("find_software", {"need": "x"}, body)]
    check = [{"command": "demo convert in.txt", "kind": "function", "passed": True, "run": {"stdout": "ok"}}]
    ok = run_with(tmp_path / "a", calls, lambda ev: replay(ev, "verify-demo-1", check,
                                                           feature_judge={"Convert files": ["shows_it_working", "ok"]}))
    assert by_kind(ok)[("feature", "a")] == "found" and ok["violations"] == 0
    assert sum(1 for c in ok["claims"] if c["kind"] == "feature") == 1  # not_checked claims nothing
    lowered = run_with(tmp_path / "b", calls, lambda ev: replay(ev, "verify-demo-1", check,
                                                                feature_judge={"Convert files": ["does_not_show", "no"]}))
    assert lowered["violations"] == 1
    failed = [dict(check[0], passed=False)]
    assert run_with(tmp_path / "c", calls, lambda ev: replay(ev, "verify-demo-1", failed))["violations"] == 1


def test_the_replay_level_bounds_the_record_level(tmp_path: Path) -> None:
    hwk = ("pickfit installed it in a fresh linux/x86_64 sandbox (modal) and replayed the steps from scratch on "
           "2026-10-28; its service answered a test request.")
    body = {"picks": [pick(verification={"level": "service", "os": "linux", "arch": "x86_64", "method": "sandbox",
                                         "verified_on_user_os": None}, how_we_know=hwk)]}
    calls = [("find_software", {"need": "x"}, body)]
    ok = run_with(tmp_path / "a", calls, lambda ev: replay(ev, "verify-demo-1", [], level="service"))
    assert ok["violations"] == 0 and by_kind(ok)[("level", "c")] == "found"
    lower = run_with(tmp_path / "b", calls, lambda ev: replay(ev, "verify-demo-1", [], level="function"))
    assert lower["violations"] == 1 and "level function < service" in lower["claims"][0]["reason"]


def test_by_hand_how_we_know_is_a_human_run_and_not_found(tmp_path: Path) -> None:
    hwk = "pickfit installed it by hand on macos/arm64 (mac mini) on 2026-10-30; the install finished and the tool started."
    report = run_with(tmp_path, [("find_software", {"need": "x"}, {"picks": [pick(how_we_know=hwk)]})], lambda ev: None)
    claim = next(c for c in report["claims"] if c["source"] == "c")
    assert (claim["os"], claim["arch"], claim["status"]) == ("macos", "arm64", "not_found")


def test_rules_labels_are_listed_and_checked_but_never_violations(tmp_path: Path) -> None:
    good = {"matched_by": "rules", "match_quality": "partial",
            "picks": [pick(match={"quality": "partial", "covers": ["pdf"], "missing": ["ocr"]}),
                      pick(slug="demo2", match={"quality": "weak", "covers": [], "missing": ["pdf", "ocr"]},
                           verification={"level": "unverified", "os": None, "arch": None, "method": None,
                                         "verified_on_user_os": None})]}
    report = run_with(tmp_path / "a", [("find_software", {"need": "x"}, good)], lambda ev: None)
    assert report["label_problems"] == 0 and report["labels"][0]["match_quality"] == "partial"
    bad = dict(good, matched_by="muse-spark-1.3", match_quality="good")
    report = run_with(tmp_path / "b", [("find_software", {"need": "x"}, bad)], lambda ev: None)
    assert report["label_problems"] == 1 and report["violations"] == 0
    wrong = dict(good, match_quality="good")
    assert run_with(tmp_path / "c", [("find_software", {"need": "x"}, wrong)], lambda ev: None)["label_problems"] == 1


def test_coverage_note_is_scanned_as_model_text(tmp_path: Path) -> None:
    body = {"picks": [pick()], "coverage_note": "Demo was tested on Windows."}
    report = run_with(tmp_path, [("find_software", {"need": "x"}, body)], lambda ev: None)
    e = [c for c in report["claims"] if c["source"] == "e"]
    assert [(c["slug"], c["os"], c["status"]) for c in e] == [("demo", "windows", "not_found")]
