import json
import shutil
from pathlib import Path

import pytest

from pickfit.index import INDEX_VERSION, IndexBuildError, build_index, write_index
from scripts.build_index import main as build_index_main

FIXTURES = Path(__file__).resolve().parent.parent / "worker" / "test" / "fixtures" / "software"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    target = tmp_path / "software"
    shutil.copytree(FIXTURES, target)
    return target


def edit(path: Path, change) -> None:
    record = json.loads(path.read_text(encoding="utf-8"))
    change(record)
    path.write_text(json.dumps(record), encoding="utf-8")


def test_fixtures_build(data_dir: Path) -> None:
    index = build_index(data_dir).index
    assert index["index_version"] == INDEX_VERSION
    assert index["count"] == 7
    slugs = [e["slug"] for e in index["entries"]]
    assert slugs == sorted(slugs)
    # A web app with no repository is on the reserved .invalid host too.
    assert all((e["repo_url"] or e["web"]["url"]).startswith(("https://example.invalid/", "https://fixture-sketch.example.invalid/"))
               for e in index["entries"])


def test_only_run_install_guides_are_indexed(data_dir: Path) -> None:
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    # macOS is only a README claim for fixture-transcribe: no steps reach the Worker.
    assert set(entries["fixture-transcribe"]["install"]) == {"linux"}
    runner = entries["fixture-llm-runner"]["install"]
    assert {os: g["basis"] for os, g in runner.items()} == {"macos": "human", "linux": "replayed"}
    assert runner["linux"]["run"]["replayed"] is True
    assert runner["linux"]["run"]["evidence_url"].startswith("https://example.invalid/runs/")
    # The box's GPU and simulated microphone reach the page; a box without them says null.
    assert runner["linux"]["run"]["gpu"] is None and runner["linux"]["run"]["microphone"] is None
    transcribe = entries["fixture-transcribe"]["install"]["linux"]["run"]
    assert transcribe["gpu"] == "Tesla T4" and transcribe["microphone"].startswith("simulated:")
    assert runner["linux"]["works_offline"] is True and runner["macos"]["works_offline"] is None
    assert runner["linux"]["first_task_setup"] == [{"command": "fixture-llm-runner pull tiny-test",
                                                   "background": False}]


def test_guides_carry_feature_coverage_with_the_checks_behind_it(data_dir: Path) -> None:
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    transcribe = entries["fixture-transcribe"]
    assert transcribe["features"] == ["transcribe audio files offline", "write SRT subtitles",
                                      "dictate from a microphone"]
    coverage = {f["feature"]: f for f in transcribe["install"]["linux"]["features"]}
    assert coverage["transcribe audio files offline"]["checks"] == [
        {"command": "fixture-transcribe sample.wav", "passed": True}]
    assert (coverage["write SRT subtitles"]["status"], coverage["write SRT subtitles"]["failure"]) == (
        "test_failed", "tool")
    assert coverage["dictate from a microphone"]["reason"] == "needs_hardware"
    runner = entries["fixture-llm-runner"]["install"]
    assert runner["macos"]["features"] == []  # verified before features were checked
    assert entries["fixture-json-query"]["features"] == []


def _set_fidelity(record: dict, feature: str, fidelity: str) -> None:
    for run in record["verification"]["runs"]:
        for f in run.get("features", []):
            if f["feature"] == feature:
                f["fidelity"] = fidelity


def test_a_features_fidelity_reaches_the_index_only_when_the_run_recorded_it(data_dir: Path) -> None:
    """privileges.md P1: what a feature's check ran against (real, compatible, stand_in) goes to the Worker, which
    never shows a stand_in one as plainly verified. A run that recorded none keeps its entry exactly as it was."""
    before = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    assert '"fidelity"' not in json.dumps(before) and '"stand_in"' not in json.dumps(before)

    served = "serve an OpenAI-compatible API"
    edit(data_dir / "fixture-llm-runner.json", lambda r: _set_fidelity(r, served, "stand_in"))
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    coverage = {f["feature"]: f for f in entries["fixture-llm-runner"]["install"]["linux"]["features"]}
    assert coverage[served]["fidelity"] == "stand_in" and coverage[served]["status"] == "checked"
    assert "fidelity" not in coverage["pull models from a registry"]  # none recorded: no key, not a null
    # The coverage's function count still includes it (it reached a verdict), and says how many were a stand-in.
    assert entries["fixture-llm-runner"]["coverage"]["dimensions"]["function"] == {
        "status": "partial", "done": 1, "of": 2, "unit": "feature", "gaps": ["sandbox_missing"], "stand_in": 1}
    # Every other entry is byte for byte what it was.
    assert {slug: e for slug, e in entries.items() if slug != "fixture-llm-runner"} == {
        slug: e for slug, e in before.items() if slug != "fixture-llm-runner"}

    for fidelity in ("compatible", "real"):
        edit(data_dir / "fixture-llm-runner.json", lambda r, fidelity=fidelity: _set_fidelity(r, served, fidelity))
        runner = {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-llm-runner"]
        assert runner["install"]["linux"]["features"][0]["fidelity"] == fidelity
        assert "stand_in" not in runner["coverage"]["dimensions"]["function"]


def test_a_feature_another_passed_run_checked_for_real_is_not_counted_as_a_stand_in(data_dir: Path) -> None:
    def two_runs(record: dict) -> None:
        linux, macos = record["verification"]["runs"]
        _set_fidelity(record, "serve an OpenAI-compatible API", "stand_in")
        macos["features"] = [{"feature": "serve an OpenAI-compatible API", "status": "checked", "smoke_tests": [0]}]

    edit(data_dir / "fixture-llm-runner.json", two_runs)
    runner = {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-llm-runner"]
    assert runner["install"]["linux"]["features"][0]["fidelity"] == "stand_in"  # that run's own guide still says so
    assert "fidelity" not in runner["install"]["macos"]["features"][0]
    assert "stand_in" not in runner["coverage"]["dimensions"]["function"]


def test_unlisted_records_are_skipped(data_dir: Path) -> None:
    edit(data_dir / "fixture-chat-tui.json", lambda r: r.update(status="hidden"))
    result = build_index(data_dir)
    assert result.skipped == ["fixture-chat-tui"]
    assert "fixture-chat-tui" not in [e["slug"] for e in result.index["entries"]]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda r: r.update(pricing={"model": "cheap", "note": None}), "pricing"),
        (lambda r: r.pop("verification"), "verification"),
        # A cross-field rule the JSON Schema alone cannot express.
        (lambda r: r["install"]["linux"].update(run_id="run-missing"), "unknown run"),
    ],
)
def test_bad_record_fails_the_build(data_dir: Path, change, message: str) -> None:
    edit(data_dir / "fixture-json-query.json", change)
    with pytest.raises(IndexBuildError) as err:
        build_index(data_dir)
    assert "fixture-json-query.json" in str(err.value)
    assert message in str(err.value)


def test_slug_must_match_file_name(data_dir: Path) -> None:
    (data_dir / "fixture-json-query.json").rename(data_dir / "other-name.json")
    with pytest.raises(IndexBuildError, match="does not match the file name"):
        build_index(data_dir)


def test_duplicate_repo_id_fails(data_dir: Path) -> None:
    edit(data_dir / "fixture-json-query.json", lambda r: r.update(repo_id="gh:900000101"))
    with pytest.raises(IndexBuildError, match="duplicate repo_id"):
        build_index(data_dir)


def test_empty_data_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(IndexBuildError, match="no \\*.json records"):
        build_index(tmp_path)


def test_invalid_json_fails(data_dir: Path) -> None:
    (data_dir / "fixture-json-query.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(IndexBuildError, match="fixture-json-query.json"):
        build_index(data_dir)


def test_script_writes_nothing_on_failure(data_dir: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "index.json"
    edit(data_dir / "fixture-json-query.json", lambda r: r.update(slug="Bad Slug"))
    assert build_index_main(["--data", str(data_dir), "--out", str(out)]) == 1
    assert not out.exists()
    assert "index not written" in capsys.readouterr().err


def test_script_writes_index(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "gen" / "index.json"
    assert build_index_main(["--data", str(data_dir), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["count"] == 7


def test_write_index_round_trips(data_dir: Path, tmp_path: Path) -> None:
    index = build_index(data_dir).index
    out = tmp_path / "index.json"
    write_index(index, out)
    assert json.loads(out.read_text(encoding="utf-8")) == index


def test_works_offline_follows_the_first_task():
    from pickfit.index import works_offline
    from pickfit.schema import VerificationRun

    record = json.loads((FIXTURES / "fixture-llm-runner.json").read_text(encoding="utf-8"))
    run = VerificationRun.model_validate(record["verification"]["runs"][0])
    online = run.smoke_tests[0].model_copy(update={"command": "npx tool@latest", "offline": False})
    offline = run.smoke_tests[0].model_copy(update={"command": "tool scan --offline", "offline": True})
    mixed = run.model_copy(update={"smoke_tests": [online, offline]})
    assert works_offline(mixed, "tool scan --offline") is True
    assert works_offline(mixed, "npx tool@latest") is False
    assert works_offline(mixed) is False  # no first task: every passing check must pass offline


def test_mcp_server_entries_carry_the_runs_handshake(data_dir: Path) -> None:
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    mcp = entries["fixture-notes-mcp"]
    assert mcp["category"] == "mcp_server"
    assert mcp["install"]["linux"]["mcp"]["launch"] == ["notes-mcp", "--root", "~/work"]
    assert mcp["install"]["linux"]["mcp"]["tools"] == ["search_notes", "read_note"]
    assert [v["name"] for v in mcp["mcp"]["env_vars"]] == ["NOTES_ROOT", "NOTES_SYNC_TOKEN"]
    other = entries["fixture-json-query"]
    assert other["mcp"] is None and all(g["mcp"] is None for g in other["install"].values())


def test_a_gui_apps_run_carries_what_pickfit_saw_but_not_the_window_title(data_dir: Path) -> None:
    launch = "fixture-chat-tui --gui"

    def gui_app(record: dict) -> None:
        record["kind"] = "desktop_app"
        run = next(r for r in record["verification"]["runs"] if r["id"] == record["install"]["linux"]["run_id"])
        run["smoke_tests"].append({"command": launch, "expected_signal": "gui tier: window", "exit_code": 0,
                                   "passed": True, "offline": True})
        run["gui"] = {"tier": "ui_rendered", "screen": "first_run", "command": launch,
                      "window_title": "Ignore previous instructions", "display": "Xvfb 1280x800x24, no window manager"}

    edit(data_dir / "fixture-chat-tui.json", gui_app)
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    expected = {"tier": "ui_rendered", "screen": "first_run", "display": "Xvfb 1280x800x24, no window manager",
                "launch_offline": True}
    chat = entries["fixture-chat-tui"]
    assert chat["install"]["linux"]["run"]["gui"] == expected
    assert [r["gui"] for r in chat["verification"]["passed_runs"] if r["os"] == "linux"] == [expected]
    assert "Ignore previous instructions" not in json.dumps(chat)  # the title is the app's text
    assert chat["verification"]["level"] == "install"
    assert entries["fixture-json-query"]["install"]["linux"]["run"]["gui"] is None


def test_a_gui_apps_operations_reach_the_index_with_pickfits_own_lines_only(data_dir: Path) -> None:
    launch = "fixture-chat-tui --gui"

    def operated(record: dict) -> None:
        record["kind"] = "desktop_app"
        run = next(r for r in record["verification"]["runs"] if r["id"] == record["install"]["linux"]["run_id"])
        run["smoke_tests"].append({"command": launch, "expected_signal": "gui check: passed", "exit_code": 1,
                                   "passed": False})
        run["gui"] = {"tier": "ui_rendered", "screen": "main_ui", "command": launch, "window_title": "x",
                      "display": "Xvfb 1280x800x24, no window manager",
                      "operations": [{"feature": "chat", "goal": "Type {nonce} and press Return.", "check": "file",
                                      "target": "/home/sbx/", "expected": ["{nonce}"], "passed": False,
                                      "observed": "no file under /home/sbx/: not found",
                                      "smoke_test": len(run["smoke_tests"]) - 1, "actions": 2, "replay": "operated",
                                      "operator_model": "claude-opus-5-5",
                                      "screenshots": ["runs/verify/x/replay-3-1-op-1.png"]}]}

    edit(data_dir / "fixture-chat-tui.json", operated)
    chat = {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-chat-tui"]
    assert chat["install"]["linux"]["run"]["gui"]["operations"] == [
        {"feature": "chat", "check": "file", "passed": False, "replay": "operated", "goal": "Type {nonce} and press Return.",
         "observed": "no file under /home/sbx/: not found", "operator_model": "claude-opus-5-5"}]  # the page names it
    assert "replay-3-1-op-1.png" not in json.dumps(chat)  # evidence paths stay in the record


def test_a_web_app_carries_its_url_and_the_facts_its_browser_run_saw(data_dir: Path) -> None:
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    sketch = entries["fixture-web-sketch"]
    assert (sketch["kind"], sketch["repo_url"], sketch["install"]) == ("web_app", None, {})
    web = sketch["web"]
    assert web["url"] == "https://fixture-sketch.example.invalid/"
    check = web["check"]
    assert (check["level"], check["checked_at"], check["run_id"]) == ("function", "2026-11-02T09:00:00Z",
                                                                      "run-20261102-web-1")
    assert (check["account_needed"], check["ads_seen"], check["third_party_domains"]) == (False, False, 1)
    assert (check["data_sent"], check["pwa"], check["offline"]) == ("none", True, "verified")
    assert [o["passed"] for o in check["operations"]] == [True]
    assert [f["status"] for f in check["features"]] == ["checked", "checked"]
    assert entries["fixture-json-query"]["web"] is None


def test_a_web_app_has_no_checked_facts_before_a_run_passed(data_dir: Path) -> None:
    def not_loaded(record: dict) -> None:
        run = record["verification"]["runs"][0]
        run.update(level="unverified", unverified_reason="needs_account", smoke_tests=[], features=[])
        run["web"].update(screen="sign_in_wall", operations=[], data_sent="unknown")
        record["verification"].update(level="unverified", unverified_reason="needs_account")

    edit(data_dir / "fixture-web-sketch.json", not_loaded)
    sketch = {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-web-sketch"]
    assert sketch["web"] == {"url": "https://fixture-sketch.example.invalid/", "check": None}


def test_a_runs_video_reaches_the_index_for_the_worker_to_serve(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parent.parent / "data" / "software" / "nip4.json"
    if not source.exists():
        pytest.skip("no record with a video in data/software")
    data_dir = tmp_path / "software"
    data_dir.mkdir()
    shutil.copy(source, data_dir / "nip4.json")
    [entry] = build_index(data_dir).index["entries"]
    videos = [r["video"] for r in entry["verification"]["passed_runs"] if r["video"]]
    assert videos, "nip4's run has a video"
    video = videos[0]
    assert {"clip", "clip_sha256", "seconds", "recorded_at", "features", "raw"} <= set(video) <= {
        "clip", "clip_sha256", "seconds", "recorded_at", "features", "raw", "chapters", "captions"}
    if video.get("chapters"):
        assert video["chapters"][0]["start_s"] == 0
    assert video["clip"].endswith(".mp4") and video["raw"] and set(video["raw"][0]) == {"file", "sha256", "seconds", "feature_index"}
    assert all(r["feature_index"] is None or 0 <= r["feature_index"] < len(video["features"]) for r in video["raw"])
    linux = entry["install"]["linux"]["run"]
    assert linux["video"] == video or linux["video"] is None


def test_desktop_and_web_apps_show_the_visual_deduction_that_is_in_the_score(data_dir: Path) -> None:
    from datetime import datetime

    from pickfit.ledger import TAIPEI
    from pickfit.schema import SoftwareRecord
    from pickfit.score import build_web_scores

    run_id = json.loads((data_dir / "fixture-web-sketch.json").read_text(encoding="utf-8"))["verification"]["runs"][0]["id"]
    defect = {"item": "comfortable", "operation": None, "cause": "app", "problem": "A button covers the title.",
              "screenshot": "after.png", "box": [0, 0, 10, 10], "quote": "Sketch", "found_by": "ocr",
              "kind": "overlap", "severity": "minor"}
    sandbox = defect | {"cause": "sandbox", "problem": "No window manager."}
    check = {"version": "comfort.v1", "run_id": run_id, "score": 1, "status": "scored", "defects": [defect, sandbox],
             "screens": 2, "model": "muse-wonder-1.0", "effort": "medium", "inputs_sha": "0" * 64,
             "checked_at": "2026-11-03T20:00:00+08:00", "cost_usd": 0.03}

    def scored(record: dict) -> None:
        record["scores"] = build_web_scores(SoftwareRecord.model_validate(record | {"scores": None}), stars=None, hn=4,
                                            now=datetime(2026, 11, 3, 21, tzinfo=TAIPEI))

    def visual_of() -> dict | None:
        return {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-web-sketch"]["visual"]

    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    assert entries["fixture-web-sketch"]["visual"] == {"status": "not_checked"}  # a web app with no check
    assert entries["fixture-json-query"]["visual"] is None  # not a desktop or web app
    # A check whose deduction is not in the score yet (scores from before it): the page says nothing was taken off.
    def unrefreshed(record: dict) -> None:
        scored(record)
        record["visual_check"] = check

    edit(data_dir / "fixture-web-sketch.json", unrefreshed)
    stored = json.loads((data_dir / "fixture-web-sketch.json").read_text(encoding="utf-8"))
    assert stored["scores"]["formula_version"] == "web.v1" and "visual" not in stored["scores"]["quality"]
    assert visual_of() == {"status": "not_checked"}
    edit(data_dir / "fixture-web-sketch.json", scored)
    visual = visual_of()
    assert visual["status"] == "defect" and visual["factor"] == 0.95
    assert visual["defects"] == [{"kind": "overlap", "problem": "A button covers the title.", "quote": "Sketch"}]
    edit(data_dir / "fixture-web-sketch.json",
         lambda r: r["visual_check"].update(score=2, defects=[sandbox]) or scored(r))
    assert visual_of()["status"] == "clean" and visual_of()["defects"] == []


def test_a_visual_deduction_that_does_not_follow_the_records_own_check_does_not_validate() -> None:
    from pickfit.schema import SoftwareRecord
    from pickfit.score import build_web_scores
    from datetime import datetime

    from pickfit.ledger import TAIPEI

    record = json.loads((FIXTURES / "fixture-web-sketch.json").read_text(encoding="utf-8"))
    run_id = record["verification"]["runs"][0]["id"]
    record["visual_check"] = {"version": "comfort.v1", "run_id": run_id, "score": 2, "status": "scored", "defects": [],
                              "screens": 2, "model": "muse-wonder-1.0", "effort": "medium", "inputs_sha": "0" * 64,
                              "checked_at": "2026-11-03T20:00:00+08:00", "cost_usd": 0.03}
    record["scores"] = build_web_scores(SoftwareRecord.model_validate(record), stars=None, hn=4,
                                        now=datetime(2026, 11, 3, 21, tzinfo=TAIPEI))
    SoftwareRecord.model_validate(record)
    record["visual_check"]["run_id"] = "web-gone"  # the check no longer reads a run of the record
    with pytest.raises(ValueError, match="must follow the record's current visual_check"):
        SoftwareRecord.model_validate(record)


def test_capabilities_reach_the_index_with_their_items(data_dir: Path) -> None:
    caps = [{"label": "convert JSON to other formats", "items": ["csv", "yaml"]}, {"label": "color output"}]
    edit(data_dir / "fixture-json-query.json", lambda r: r.update(capabilities=caps))
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    assert entries["fixture-json-query"]["capabilities"] == [
        {"label": "convert JSON to other formats", "items": ["csv", "yaml"]}, {"label": "color output"}]  # empty items left out
    assert entries["fixture-chat-tui"]["capabilities"] == []


def test_entries_carry_a_short_coverage_summary(data_dir: Path) -> None:
    """U8: the tool page's Verification Coverage, from pickfit/coverage.py, summed up small (no gap text, no
    dimension that does not apply) and agreeing with compute_coverage."""
    from pickfit.coverage import CATEGORIES, compute_coverage
    from pickfit.index import load_records
    from pickfit.security import GAP_CATEGORIES

    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    records = {r.slug: r for r in load_records(data_dir)[0]}
    for slug, entry in entries.items():
        cov = entry["coverage"]
        full = compute_coverage(records[slug])
        assert cov["version"] == "cov.v1" and cov["share"] == full["summary"]["verified_share"]
        applies = {d for d, v in full["dimensions"].items() if v["status"] != "not_applicable"}
        assert set(cov["dimensions"]) == applies, slug
        for name, dim in cov["dimensions"].items():
            assert dim["status"] == full["dimensions"][name]["status"]
            assert set(dim) <= {"status", "done", "of", "unit", "blocked_by", "gaps", "stand_in"}
            assert len(dim.get("gaps", [])) <= 3
            assert set(dim.get("gaps", [])) <= set(CATEGORIES) | set(GAP_CATEGORIES)
            assert ("unit" in dim) == (name == "function" and "done" in dim)
    runner = entries["fixture-llm-runner"]["coverage"]["dimensions"]
    assert runner["function"] == {"status": "partial", "done": 1, "of": 2, "unit": "feature", "gaps": ["sandbox_missing"]}
    assert "usability" not in runner and "preview" not in runner and "video" not in runner
    # Small: under 600 bytes a tool (about 414 on average over the real catalog, 11/21).
    assert all(len(json.dumps(e["coverage"], separators=(",", ":"))) < 600 for e in entries.values())


V15_TOP = ("used_by", "track", "standing", "standing_note")
V15_VERIFICATION = ("last_passed_at", "reverify_cycle_days", "reverify_due_at")


def test_brief_15_fields_are_left_out_while_unset(data_dir: Path) -> None:
    """Records written before brief 15's fields build the same entries as before: no key, not a null."""
    for entry in build_index(data_dir).index["entries"]:
        assert not set(V15_TOP) & set(entry), entry["slug"]
        assert not set(V15_VERIFICATION) & set(entry["verification"]), entry["slug"]


def test_brief_15_fields_reach_the_index_when_set(data_dir: Path) -> None:
    def change(record: dict) -> None:
        record.update(used_by="agent", track="A", standing="broken", standing_note="re-verification: install failed")
        record["verification"].update(last_passed_at="2026-11-01T00:00:00Z", reverify_cycle_days=30,
                                      reverify_due_at="2026-12-01T00:00:00Z")

    edit(data_dir / "fixture-llm-runner.json", change)
    edit(data_dir / "fixture-transcribe.json", lambda r: r.update(standing="new"))
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    runner = entries["fixture-llm-runner"]
    assert [runner[k] for k in V15_TOP] == ["agent", "A", "broken", "re-verification: install failed"]
    assert [runner["verification"][k] for k in V15_VERIFICATION] == [
        "2026-11-01T00:00:00Z", 30, "2026-12-01T00:00:00Z"]
    # Only what is set: a record with standing alone gets standing alone.
    transcribe = entries["fixture-transcribe"]
    assert transcribe["standing"] == "new"
    assert not {"used_by", "track", "standing_note"} & set(transcribe)
    assert not set(V15_VERIFICATION) & set(transcribe["verification"])
