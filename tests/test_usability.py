"""Usability (ease.v1): the run's evidence, the quote checks, combining two samples, and the record field; no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError
from queue_fakes import ROOT

from pickfit.schema import SoftwareRecord, Usability
from pickfit.usability import (
    Asked,
    Bundle,
    FirstLookAnswer,
    InUseAnswer,
    Line,
    Shot,
    TextFinder,
    bundle_for,
    check_first_look,
    check_in_use,
    combine,
    in_use_text,
    judge,
    record_usability,
    usability_score,
    verdict,
)
from scripts.ease_sheet import ratings_template, read_ratings

FIXTURES = ROOT / "worker" / "test" / "fixtures" / "software"
RUN = "verify-chat-1"
WEB_RUN = "run-20261102-web-1"


def png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 40), color).save(path)


def step(folder: Path, name: str, color: tuple[int, int, int], action: dict[str, Any], changed: bool = True,
         why: str = "") -> dict[str, Any]:
    png(folder / name, color)
    return {"screenshot": f"/elsewhere/runs/verify/{RUN}/{name}", "sha256": "0" * 64, "changed": changed,
            "action": action, "observation": "", "why": why, "refused": None}


def gui_record(evidence: Path, *, operated: bool = True) -> dict[str, Any]:
    """Fixture Chat TUI as a desktop app whose Linux run operated it, and the run's folder under `evidence`."""
    record = json.loads((FIXTURES / "fixture-chat-tui.json").read_text(encoding="utf-8"))
    record["kind"] = "desktop_app"
    run = record["verification"]["runs"][0]
    run["id"] = RUN
    record["install"]["linux"]["run_id"] = RUN
    run["smoke_tests"] = [{"command": "chat --gui", "expected_signal": "gui check: passed", "exit_code": 0,
                           "passed": operated, "offline": True}]
    run["evidence"] = {"trace_path": f"runs/verify/{RUN}/report.json",
                       "screenshot_paths": [f"runs/verify/{RUN}/replay-3-1.app.judged.png"]}
    run["gui"] = {"tier": "ui_rendered", "screen": "main_ui", "command": "chat --gui",
                  "display": "Xvfb 1280x800x24, no window manager, no GPU",
                  "operations": [{"goal": "In Fixture Chat TUI, send {nonce}", "check": "screen_text",
                                  "expected": ["{nonce}"], "passed": operated, "observed": "on screen: yes",
                                  "smoke_test": 0, "actions": 2, "replay": "actions"}]}
    folder = evidence / RUN
    png(folder / "replay-3-1.app.png", (240, 240, 240))
    sent = [step(folder, "3-op-1.png", (200, 200, 200), {"kind": "click", "x": 10, "y": 20, "count": 1},
                 why="click the message box"),
            step(folder, "3-op-2.png", (100, 180, 100), {"kind": "done"})]
    stuck = [step(folder, f"4-op-{i}.png", (90, 90, 90), {"kind": "key", "name": "ctrl+o"}, changed=False)
             for i in range(1, 4)]
    report = {"commands": [
        {"operate": {"goal": "In Fixture Chat TUI, send pickfit1", "check": {"kind": "screen_text"}, "passed": operated,
                     "stop": "done", "steps": sent, "result": {"line": "on screen: \"pickfit1\": yes"}}},
        {"operate": {"goal": "Open the saved chat fixture-chat-tui.log", "check": {"kind": "file"}, "passed": False,
                     "stop": "step_cap", "steps": stuck, "result": {"line": "file: missing"}}},
    ]}
    (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return record


OCR = {
    "replay-3-1.app.png": [Line("Chats", 0, 0, 30, 14), Line("New message", 0, 20, 60, 13), Line("v1.2 beta", 40, 30, 20, 8)],
    "3-op-1.png": [Line("Type a message", 0, 30, 60, 13)],
    "3-op-2.png": [Line("pickfit1 sent", 0, 30, 60, 13)],
    "4-op-1.png": [Line("Chats", 0, 0, 30, 14)],
    "4-op-3.png": [Line("Chats", 0, 0, 30, 14), Line("No menu", 0, 20, 40, 13)],
}


def fake_ocr(path: Path) -> list[Line]:
    return OCR.get(path.name, [])


def cite(image: int, quote: str) -> dict[str, Any]:
    return {"image": image, "box": {"x_min": 0, "y_min": 0, "x_max": 500, "y_max": 200}, "quote": quote}


def first_answer(ready: int | None = 2, comfortable: int | None = 2, *, quote: str = "New message",
                 findings: list[dict[str, Any]] | None = None, broken: bool = False) -> FirstLookAnswer:
    return FirstLookAnswer.model_validate({
        "observed": "a chat window", "screen_broken": broken, "findings": findings or [],
        "ready": {"score": ready, "evidence": cite(1, "Chats") if ready is not None else None},
        "comfortable": {"score": comfortable, "evidence": cite(1, quote) if comfortable is not None else None}})


def finding(item: str, cause: str, image: int, quote: str, operation: int | None = None,
            problem: str = "the button has no label") -> dict[str, Any]:
    return {"item": item, "operation": operation, "cause": cause, "problem": problem, "evidence": cite(image, quote)}


def in_use_answer(scores: dict[int, tuple[int | None, int | None]], findings: list[dict[str, Any]] | None = None,
                  quotes: dict[int, tuple[int, str]] | None = None) -> InUseAnswer:
    quotes = quotes or {1: (2, "pickfit1 sent"), 2: (4, "No menu")}
    ops = [{"operation": n, "findable": {"score": f, "evidence": cite(*quotes[n]) if f is not None else None},
            "responsive": {"score": r, "evidence": cite(*quotes[n]) if r is not None else None}}
           for n, (f, r) in scores.items()]
    return InUseAnswer.model_validate({"operations": ops, "findings": findings or []})


@pytest.fixture
def bundle(tmp_path: Path) -> Bundle:
    found = bundle_for(gui_record(tmp_path), tmp_path)
    assert found is not None
    return found


# --- the run's evidence ----------------------------------------------------------------------------


def test_the_bundle_reads_the_runs_own_screens_and_never_names_the_app(bundle: Bundle) -> None:
    assert bundle.kind == "gui" and bundle.operated and bundle.base_ready == 2
    assert [op.passed for op in bundle.operations] == [True, False]  # passed first, then the one stuck at the cap
    assert [s.path.name for s in bundle.first_look_shots()] == ["replay-3-1.app.png", "3-op-2.png"]
    assert [s.path.name for s in bundle.in_use_shots()] == ["3-op-1.png", "3-op-2.png", "4-op-1.png", "4-op-3.png"]
    text = in_use_text(bundle)
    assert "Fixture Chat TUI" not in text and "fixture-chat-tui" not in text and "the app" in text
    assert "ran out of steps" in text and "screen unchanged" in text
    assert bundle.operations[1].diff == 0.0 and bundle.operations[0].diff == 1.0
    assert bundle.measured[1] == {"goal": "Open the saved chat the app.log", "passed": False, "stop": "step_cap",
                                  "actions": 3, "unchanged": 3}


def test_a_run_with_no_passed_operation_is_judged_at_first_look_only(tmp_path: Path) -> None:
    found = bundle_for(gui_record(tmp_path, operated=False), tmp_path)
    assert found is not None and not found.operated and found.operations == []
    assert [s.path.name for s in found.first_look_shots()] == ["replay-3-1.app.png"]


def test_quotes_must_be_on_pickfits_own_screenshot_or_in_the_page(tmp_path: Path) -> None:
    png(tmp_path / "a.png", (0, 0, 0))
    shot = Shot(tmp_path / "a.png", "x", "1" * 64, dom="Plan your trip\nExport as PDF")
    finder = TextFinder(lambda p: [Line("Settings", 0, 0, 10, 10), Line("Get started", 0, 0, 10, 10),
                                   Line("Understand file permissions", 0, 0, 10, 10)])
    assert finder.find("Get started", shot)[0] == "ocr"
    assert finder.find("Get startd", shot)[0] == "ocr"  # an OCR slip
    assert finder.find("“file permissions”", shot)[0] == "ocr"
    assert finder.find("Export as PDF", shot)[0] == "dom"
    for made_up in ("Save changes", "Open file", "Welcome to the app", "", "x" * 201):
        assert finder.find(made_up, shot)[0] is None


# --- checking one sample ----------------------------------------------------------------------------


def test_ready_starts_from_the_screen_judge_and_drops_one_level_only_on_an_app_problem(bundle: Bundle) -> None:
    finder = TextFinder(fake_ocr)
    assert check_first_look(first_answer(ready=2), bundle, finder).first["ready"] == (2, "scored")
    # The model cannot raise it, and a lower score with no app problem keeps the base.
    bundle.screen = "first_run"
    assert check_first_look(first_answer(ready=2), bundle, finder).first["ready"] == (1, "scored")
    bundle.screen = "main_ui"
    assert check_first_look(first_answer(ready=0), bundle, finder).first["ready"] == (2, "scored")
    blamed = [finding("ready", "app", 1, "New message", problem="a dialog covers the chat")]
    assert check_first_look(first_answer(ready=0, findings=blamed), bundle, finder).first["ready"] == (1, "scored")
    sandbox = [finding("ready", "sandbox", 1, "New message", problem="an OS permission prompt")]
    assert check_first_look(first_answer(ready=0, findings=sandbox), bundle, finder).first["ready"] == (2, "scored")


def test_comfort_needs_found_text_an_app_problem_and_measured_small_text(bundle: Bundle) -> None:
    finder = TextFinder(fake_ocr)
    assert check_first_look(first_answer(comfortable=2, quote="Made up"), bundle, finder).first["comfortable"] == (
        None, "unquoted")
    assert check_first_look(first_answer(comfortable=1), bundle, finder).first["comfortable"] == (None, "not_app")
    assert check_first_look(first_answer(comfortable=None), bundle, finder).first["comfortable"] == (None, "not_seen")
    assert check_first_look(first_answer(broken=True), bundle, finder).first["comfortable"] == (None, "sandbox_broken")
    tiny = [finding("comfortable", "app", 1, "v1.2 beta", problem="the version text is too small")]
    checked = check_first_look(first_answer(comfortable=1, findings=tiny), bundle, finder)
    assert checked.first["comfortable"] == (1, "scored")  # OCR measures it 8 px tall
    big = [finding("comfortable", "app", 1, "New message", problem="labels are too small")]
    checked = check_first_look(first_answer(comfortable=1, findings=big), bundle, finder)
    assert checked.first["comfortable"] == (None, "not_app") and checked.findings[0]["cause"] == "unconfirmed"


def test_in_use_scores_cite_their_own_operation_and_follow_pickfits_check(bundle: Bundle) -> None:
    finder = TextFinder(fake_ocr)
    checked = check_in_use(in_use_answer({1: (2, 0), 2: (2, 2)}, findings=[
        finding("responsive", "app", 2, "pickfit1 sent", operation=1, problem="the result shows nowhere")]),
        bundle, finder)
    assert checked.ops[1]["responsive"] == (1, "scored")  # pickfit read the result on the screen: at least 1
    assert checked.ops[2]["findable"] == (2, "scored")
    # A score citing another operation's image is dropped; so is a stuck operation blamed on the operator.
    checked = check_in_use(in_use_answer({1: (2, 2), 2: (0, None)}, quotes={1: (4, "No menu"), 2: (4, "No menu")},
                                         findings=[finding("findable", "operator", 4, "No menu", operation=2)]),
                           bundle, finder)
    assert checked.ops[1]["findable"] == (None, "unquoted")
    assert checked.ops[2]["findable"] == (None, "not_app") and checked.ops[2]["responsive"] == (None, "not_seen")
    # A file check whose screen did not change shows at most 1.
    checked = check_in_use(in_use_answer({1: (2, 2), 2: (2, 2)}), bundle, finder)
    assert checked.ops[2]["responsive"] == (1, "scored")


def test_two_samples_must_agree_and_a_first_look_alone_counts_six_tenths() -> None:
    assert combine((2, "scored"), (1, "scored")) == (1.5, "scored")
    assert combine((2, "scored"), (0, "scored")) == (None, "disagree")
    assert combine((2, "scored"), (None, "unquoted")) == (None, "unquoted")
    dims = {"ready": {"score": 2}, "findable": {"score": 1}, "responsive": {"score": None}, "comfortable": {"score": 2}}
    assert usability_score(dims, operated=True) == 80.0  # (20 + 15 + 25) / 75
    assert usability_score(dims, operated=False) == 60.0  # ready and comfortable only, times 0.6
    assert usability_score({k: {"score": None} for k in dims}, operated=True) is None
    assert [verdict(s, True) for s in (70, 69.9, 40, 39.9)] == ["easy", "some_friction", "some_friction", "hard"]
    assert verdict(55, False) is None


# --- the whole judgement ----------------------------------------------------------------------------


def test_judge_makes_both_calls_twice_and_its_result_fits_the_record(bundle: Bundle, tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    answers = {"first_look": [first_answer(), first_answer(comfortable=1, findings=[
                   finding("comfortable", "app", 1, "v1.2 beta", problem="tiny version text")])],
               "in_use": [in_use_answer({1: (2, 2), 2: (1, None)}, findings=[
                   finding("findable", "app", 4, "No menu", operation=2, problem="open is in no menu")]),
                   in_use_answer({1: (1, 2), 2: (1, None)}, findings=[
                       finding("findable", "app", 4, "No menu", operation=2, problem="open is in no menu")])]}

    def ask(body: dict[str, Any], out: type, kind: str) -> Asked:
        calls.append((kind, body))
        n = sum(k == kind for k, _ in calls) - 1
        return Asked(answers[kind][n], 0.01, "muse-spark-1.3")

    result = judge(bundle, ask, TextFinder(fake_ocr))
    assert [k for k, _ in calls] == ["first_look", "in_use", "first_look", "in_use"]
    images = [sum(c["type"] == "input_image" for c in body["input"][0]["content"]) for _, body in calls]
    assert images == [2, 4, 2, 4]
    assert all("Fixture Chat TUI" not in json.dumps(body) for _, body in calls)
    dims = result["dimensions"]
    assert dims["ready"] == {"score": 2.0, "status": "scored"} and dims["comfortable"]["score"] == 1.5
    # op 1: sample 2's 1 blames nothing on the app, so op 1 has no findable score; op 2: 1 in both samples.
    assert dims["findable"] == {"score": 1.0, "status": "scored"}
    assert dims["responsive"]["score"] == 2.0  # op 2 not seen in either sample
    assert result["score"] == round(100 * (20 * 1 + 25 * 0.75 + 30 * 0.5 + 25 * 1) / 100, 1)
    assert result["verdict"] == "easy" and result["cost_usd"] == 0.04
    assert result["findings"][0]["cause"] == "app" and result["findings"][0]["samples"] == 2
    usability = Usability.model_validate(record_usability(result))
    record = gui_record(tmp_path)
    record["usability"] = usability.model_dump(mode="json")
    SoftwareRecord.model_validate(record)
    record["kind"] = "cli_tool"
    with pytest.raises(ValidationError, match="desktop_app and web_app only"):
        SoftwareRecord.model_validate(record)


def test_a_first_look_alone_has_no_verdict_and_stays_under_sixty(tmp_path: Path) -> None:
    found = bundle_for(gui_record(tmp_path, operated=False), tmp_path)
    assert found is not None
    result = judge(found, lambda body, out, kind: Asked(first_answer(), 0.005, "muse-spark-1.3"), TextFinder(fake_ocr))
    assert result["basis"] == "first_look" and result["score"] == 60.0 and result["verdict"] is None
    assert result["dimensions"]["findable"]["status"] == "no_operation"
    usability = record_usability(result)
    Usability.model_validate(usability)
    for bad in ({"verdict": "easy"}, {"score": 61.0}):
        with pytest.raises(ValidationError):
            Usability.model_validate(usability | bad)


def test_web_runs_quote_the_pages_own_text(tmp_path: Path) -> None:
    record = json.loads((FIXTURES / "fixture-web-sketch.json").read_text(encoding="utf-8"))
    folder = tmp_path / WEB_RUN
    for name, color in (("install.png", (250, 250, 250)), ("before.png", (250, 250, 250)), ("after.png", (0, 90, 0))):
        png(folder / name, color)
    (folder / "install.json").write_text(json.dumps({"text": "Sketch\nNew drawing"}))
    (folder / "before.json").write_text(json.dumps({"text": "Sketch\nNew drawing"}))
    (folder / "after.json").write_text(json.dumps({"text": "Saved drawing.png"}))
    (folder / "web_result.json").write_text(json.dumps({"install_judge": {"screen": "landing_page"},
                                                        "function": {"steps": 2, "done": True}}))
    (folder / "agent_history.json").write_text(json.dumps({"history": [
        {"model_output": {"action": [{"click": {"index": 3}}], "evaluation_previous_goal": "opened the editor"},
         "result": [{"error": None}]}]}))
    found = bundle_for(record, tmp_path)
    assert found is not None and found.kind == "web" and found.base_ready == 1 and found.operated
    assert "click {\"index\": 3}" in in_use_text(found)
    finder = TextFinder(lambda path: [])
    assert finder.find("Saved drawing.png", found.operations[0].last)[0] == "dom"
    assert finder.find("Saved drawing.png", found.launch)[0] is None


# --- the pilot's ratings file -------------------------------------------------------------------------


def test_the_ratings_template_reads_back_empty_and_a_filled_file_reads_its_values() -> None:
    blank = read_ratings(ratings_template(["concessio", "orrery"]))
    assert blank["rater"] == "念誠" and blank["rated_at"] is None
    assert blank["apps"]["orrery"] == {"ready": None, "findable": None, "responsive": None, "comfortable": None,
                                       "overall": None, "would_use": None, "note": ""}
    filled = read_ratings('rater: "念誠"\nrated_at: "2026-11-03T00:10:00Z"\napps:\n  orrery:\n    ready: 2\n'
                          '    findable: "cant_tell"\n    overall: 4\n    note: "a: \\"b\\""\n')
    assert filled["apps"]["orrery"] == {"ready": 2, "findable": "cant_tell", "overall": 4, "note": 'a: "b"'}
    committed = read_ratings((ROOT / "data" / "calibration" / "ease-ratings.yaml").read_text(encoding="utf-8"))
    pilot = json.loads((ROOT / "data" / "calibration" / "ease-pilot.json").read_text(encoding="utf-8"))
    assert list(committed["apps"]) == [a["slug"] for a in pilot["apps"]]
