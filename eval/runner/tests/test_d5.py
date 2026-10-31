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
