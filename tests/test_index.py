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
                                      "screenshots": ["runs/verify/x/replay-3-1-op-1.png"]}]}

    edit(data_dir / "fixture-chat-tui.json", operated)
    chat = {e["slug"]: e for e in build_index(data_dir).index["entries"]}["fixture-chat-tui"]
    assert chat["install"]["linux"]["run"]["gui"]["operations"] == [
        {"feature": "chat", "check": "file", "passed": False, "replay": "operated", "goal": "Type {nonce} and press Return.",
         "observed": "no file under /home/sbx/: not found"}]
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
        "clip", "clip_sha256", "seconds", "recorded_at", "features", "raw", "chapters"}
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
    assert visual["status"] == "defect" and visual["factor"] == 0.95 and visual["worst"] == "minor"
    assert visual["defects"] == [{"kind": "overlap", "problem": "A button covers the title.", "quote": "Sketch",
                                  "major": False}]
    # A major both judges agree on: 10% off, listed first and marked.
    major = defect | {"kind": "text_cut_off", "problem": "The status is cut off.", "severity": "major",
                      "second_severity": "major"}
    guard = {"version": "guard.v1", "model": "muse-spark-1.3", "effort": "medium", "asked": 1, "answered": 1,
             "checked_at": "2026-11-03T22:00:00+08:00", "cost_usd": 0.01}
    edit(data_dir / "fixture-web-sketch.json",
         lambda r: r["visual_check"].update(score=0, defects=[defect, major, sandbox], guard=guard) or scored(r))
    visual = visual_of()
    assert visual["worst"] == "major" and visual["factor"] == 0.9
    assert [(d["kind"], d["major"]) for d in visual["defects"]] == [("text_cut_off", True), ("overlap", False)]
    edit(data_dir / "fixture-web-sketch.json", lambda r: r["visual_check"].pop("guard") or r["visual_check"].update(
        score=1, defects=[defect, sandbox]) or scored(r))
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
