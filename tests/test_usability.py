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
    COMFORT_CHECKS,
    FIND_CHECKS,
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


OK = {"ok": True, "cause": None, "problem": None, "evidence": None}
UNSEEN = {"ok": None, "cause": None, "problem": None, "evidence": None}


def bad(image: int, quote: str, cause: str = "app", problem: str = "the toolbar is cramped") -> dict[str, Any]:
    return {"ok": False, "cause": cause, "problem": problem, "evidence": cite(image, quote)}


def first_answer(ready: int | None = 2, *, comfort: dict[str, Any] | None = None, seen: str | None = "New message",
                 findings: list[dict[str, Any]] | None = None, broken: bool = False,
                 every: dict[str, Any] = OK) -> FirstLookAnswer:
    return FirstLookAnswer.model_validate({
        "observed": "a chat window", "screen_broken": broken, "findings": findings or [],
        "ready": {"score": ready, "evidence": cite(1, "Chats") if ready is not None else None},
        "comfort_seen": cite(1, seen) if seen else None,
        "comfort": dict.fromkeys(COMFORT_CHECKS, every) | (comfort or {})})


def finding(item: str, cause: str, image: int, quote: str, operation: int | None = None,
            problem: str = "the button has no label") -> dict[str, Any]:
    return {"item": item, "operation": operation, "cause": cause, "problem": problem, "evidence": cite(image, quote)}


def op(n: int, seen: tuple[int, str] | None, find: dict[str, Any] | None = None,
       respond: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"operation": n, "seen": cite(*seen) if seen else None,
            "findable": dict.fromkeys(FIND_CHECKS, OK) | (find or {}),
            "responsive": {"result_shown": OK, "errors_explain": UNSEEN} | (respond or {})}


def in_use_answer(*ops: dict[str, Any], findings: list[dict[str, Any]] | None = None) -> InUseAnswer:
    return InUseAnswer.model_validate({"operations": list(ops), "findings": findings or []})


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


def test_comfort_comes_from_checks_with_found_text_and_measured_small_text(bundle: Bundle) -> None:
    finder = TextFinder(fake_ocr)

    def comfort(**kw: Any) -> tuple[int | None, str]:
        return check_first_look(first_answer(**kw), bundle, finder).first["comfortable"]

    assert comfort() == (2, "scored")
    assert comfort(seen="Made up") == (None, "unquoted")
    assert comfort(every=UNSEEN) == (None, "not_seen")
    assert comfort(broken=True) == (None, "sandbox_broken")
    # One app problem 1, two 0; its text may be the label next to it, but it must be on the screen.
    assert comfort(comfort={"spacing_even": bad(1, "New message")}) == (1, "scored")
    assert comfort(comfort={"spacing_even": bad(1, "New message"), "layout_intact": bad(1, "Chats")}) == (0, "scored")
    assert comfort(comfort={"layout_intact": bad(1, "Broken banner")}) == (None, "unquoted")
    # The sandbox's problems are listed, never counted.
    checked = check_first_look(first_answer(comfort={"layout_intact": bad(1, "Chats", cause="sandbox")}), bundle, finder)
    assert checked.first["comfortable"] == (2, "scored") and checked.findings[0]["cause"] == "sandbox"
    # "Too small" holds only for text OCR measures under 11 px.
    assert comfort(comfort={"text_readable": bad(1, "v1.2 beta", problem="tiny version text")}) == (1, "scored")
    checked = check_first_look(first_answer(comfort={"text_readable": bad(1, "New message")}), bundle, finder)
    assert checked.first["comfortable"] == (None, "unquoted") and checked.findings[0]["cause"] == "unconfirmed"


def test_in_use_scores_come_from_each_operations_own_checks_and_pickfits_check(bundle: Bundle) -> None:
    finder = TextFinder(fake_ocr)
    checked = check_in_use(in_use_answer(op(1, (2, "pickfit1 sent")), op(2, (4, "No menu"))), bundle, finder)
    assert checked.ops[1] == {"findable": (2, "scored"), "responsive": (2, "scored")}
    assert checked.ops[2]["responsive"] == (1, "scored")  # a file check whose screen did not change: at most 1
    failing = {"result_shown": bad(2, "pickfit1 sent"), "errors_explain": bad(2, "pickfit1 sent")}
    checked = check_in_use(in_use_answer(op(1, (2, "pickfit1 sent"), respond=failing),
                                         op(2, (4, "No menu"), find={"visible": bad(4, "No menu")})), bundle, finder)
    assert checked.ops[1]["responsive"] == (1, "scored")  # pickfit read the result on the screen: at least 1
    assert checked.ops[2]["findable"] == (1, "scored")
    # Text from another operation's image counts for nothing; the operator's misses never count.
    checked = check_in_use(in_use_answer(op(1, (4, "No menu")),
                                         op(2, (4, "No menu"), find={"visible": bad(4, "No menu", cause="operator")})),
                           bundle, finder)
    assert checked.ops[1]["findable"] == (None, "unquoted")
    assert checked.ops[2]["findable"] == (2, "scored") and checked.findings[0]["cause"] == "operator"


def test_two_samples_must_agree_and_a_first_look_alone_is_not_scored() -> None:
    assert combine((2, "scored"), (1, "scored")) == (1.5, "scored")
    assert combine((2, "scored"), (0, "scored")) == (None, "disagree")
    assert combine((2, "scored"), (None, "unquoted")) == (None, "unquoted")
    dims = {"ready": {"score": 2}, "findable": {"score": 1}, "responsive": {"score": None}, "comfortable": {"score": 2}}
    assert usability_score(dims, operated=True) == 80.0  # (20 + 15 + 25) / 75
    assert usability_score(dims, operated=False) is None
    assert usability_score({k: {"score": None} for k in dims}, operated=True) is None
    assert [verdict(s, True) for s in (70, 69.9, 40, 39.9)] == ["easy", "some_friction", "some_friction", "hard"]
    assert verdict(55, False) is None


# --- the whole judgement ----------------------------------------------------------------------------


def test_judge_makes_both_calls_twice_and_its_result_fits_the_record(bundle: Bundle, tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    hidden = {"visible": bad(4, "No menu", problem="open is in no menu")}
    answers = {"first_look": [first_answer(), first_answer(comfort={"spacing_even": bad(1, "New message")})],
               "in_use": [in_use_answer(op(1, (2, "pickfit1 sent")), op(2, (4, "No menu"), find=hidden)),
                          in_use_answer(op(1, (2, "pickfit1 sent"), find={"labelled": bad(1, "Type a message")}),
                                        op(2, (4, "No menu"), find=hidden))]}

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
    assert dims["findable"] == {"score": 1.25, "status": "scored"}  # op 1: (2 + 1) / 2, op 2: 1
    assert dims["responsive"]["score"] == 1.5  # op 1: 2; op 2: a file check on an unchanged screen, at most 1
    assert result["score"] == round(100 * (20 * 1 + 30 * 0.625 + 25 * 0.75 + 25 * 0.75) / 100, 1)
    assert result["verdict"] == "easy" and result["cost_usd"] == 0.04
    top = result["findings"][0]
    assert (top["cause"], top["item"], top["operation"], top["samples"]) == ("app", "findable", 2, 2)
    usability = Usability.model_validate(record_usability(result))
    record = gui_record(tmp_path)
    record["usability"] = usability.model_dump(mode="json")
    SoftwareRecord.model_validate(record)
    record["kind"] = "cli_tool"
    with pytest.raises(ValidationError, match="desktop_app and web_app only"):
        SoftwareRecord.model_validate(record)


def test_a_first_look_alone_is_shown_but_gets_no_score_or_verdict(tmp_path: Path) -> None:
    found = bundle_for(gui_record(tmp_path, operated=False), tmp_path)
    assert found is not None
    result = judge(found, lambda body, out, kind: Asked(first_answer(), 0.005, "muse-spark-1.3"), TextFinder(fake_ocr))
    assert result["basis"] == "first_look" and result["score"] is None and result["verdict"] is None
    assert result["dimensions"]["ready"]["score"] == 2.0 and result["dimensions"]["comfortable"]["score"] == 2.0
    assert result["dimensions"]["findable"]["status"] == "no_operation"
    usability = record_usability(result)
    Usability.model_validate(usability)
    for wrong in ({"verdict": "easy"}, {"score": 50.0}):
        with pytest.raises(ValidationError):
            Usability.model_validate(usability | wrong)


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


def test_the_comparison_ranks_ties_and_maps_overall_to_verdicts() -> None:
    from scripts.ease_compare import human_verdict, ranks, spearman

    assert ranks([3, 1, 1, 2]) == [4.0, 1.5, 1.5, 3.0]
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0 and spearman([1, 2], [2, 1]) is None
    assert [human_verdict(v) for v in (5, 4, 3, 2, 1, None, "cant_tell")] == [
        "easy", "easy", "some_friction", "hard", "hard", None, None]


def test_the_contrast_runs_p2_and_sends_opus_the_same_images_and_schema(bundle: Bundle) -> None:
    from scripts.ease_contrast import P2, ComfortChecksP2, FirstLookAnswerP2, opus_messages

    from pickfit.schema import meta_strict_schema
    from pickfit.usability import P1, _body, first_look_text

    assert "Do not judge colours, style or branding." in P1.first_look
    assert "Do not judge colours" not in P2.first_look and "dated and rough" in P2.first_look
    assert P2.in_use == P1.in_use
    meta_strict_schema(FirstLookAnswerP2)
    body = _body(P2.first_look, first_look_text(bundle), bundle.first_look_shots(), "ease_first_look", FirstLookAnswerP2)
    request = opus_messages(body)
    blocks = request["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["text", "image", "image"]
    assert blocks[1]["source"]["media_type"] == "image/png"
    assert request["system"].startswith(P2.first_look) and json.dumps(body["text"]["format"]["schema"],
                                                                  separators=(",", ":")) in request["system"]
    from scripts.ease_contrast import fill_nulls, parse_json

    strict = body["text"]["format"]["schema"]
    text = "```json\n" + json.dumps({"observed": "x", "screen_broken": False, "findings": [], "ready": {"score": 2},
                                     "comfort": {name: {"ok": True} for name in ComfortChecksP2.model_fields}}) + "\n```"
    parsed = FirstLookAnswerP2.model_validate(fill_nulls(parse_json(text), strict))
    boxed = {"observed": "x", "screen_broken": False, "findings": [], "ready": {"score": 2, "evidence": {
        "image": 1, "box": [340, 710, 660, 800], "quote": "Chats"}},
             "comfort": {name: {"ok": True} for name in ComfortChecksP2.model_fields}}
    assert FirstLookAnswerP2.model_validate(fill_nulls(boxed, strict)).ready.evidence.box.y_max == 800
    assert parsed.ready.evidence is None and parsed.comfort_seen is None and parsed.comfort.layout_intact.cause is None
    assert "temperature" not in request and request["output_config"] == {"effort": "low"}
    # Six checks under P2; one app problem still scores 1.
    answer = {"observed": "x", "screen_broken": False, "findings": [],
              "ready": {"score": 2, "evidence": cite(1, "Chats")}, "comfort_seen": cite(1, "New message"),
              "comfort": dict.fromkeys(ComfortChecksP2.model_fields, OK) | {"looks_current": bad(1, "Chats")}}
    checked = check_first_look(FirstLookAnswerP2.model_validate(answer), bundle, TextFinder(fake_ocr))
    assert checked.first["comfortable"] == (1, "scored") and checked.findings[0]["check"] == "looks_current"


def test_never_the_opposite_compares_polarity_and_zero_against_two() -> None:
    from scripts.ease_compare import dimension_level, human_polarity, opposites

    assert [human_polarity(v) for v in (5, 4, 3, 2, 1, "cant_tell", None)] == [1, 1, 0, -1, -1, None, None]
    assert [dimension_level(v) for v in (2.0, 1.5, 1.25, 0.5, 0.0, None)] == [2, 2, 1, 0, 0, None]
    dims = lambda **kw: {k: {"score": kw.get(k)} for k in ("ready", "findable", "responsive", "comfortable")}  # noqa: E731
    results = {"a": {"verdict": "easy", "dimensions": dims(ready=2.0, comfortable=2.0)},
               "b": {"verdict": "some_friction", "dimensions": dims(ready=1.0, comfortable=0.5)},
               "c": {"verdict": None, "dimensions": dims(ready=2.0)}}
    ratings = {"apps": {"a": {"overall": 2, "ready": 2, "comfortable": 0},
                        "b": {"overall": 5, "ready": 0, "comfortable": "cant_tell"},
                        "c": {"overall": 1, "ready": 2}}}
    out = opposites(results, ratings)
    assert out["overall"] == {"compared": 2, "opposite": ["a"]}  # b is neutral, c has no verdict
    assert out["comfortable"] == {"compared": 1, "opposite": ["a"]} and out["ready"]["opposite"] == []
    assert out["passed"] is False


def defect(kind: str, severity: str, image: int, quote: str, cause: str = "app") -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "cause": cause, "problem": f"{kind} near {quote}",
            "evidence": cite(image, quote)}


def comfort_answer(*defects: dict[str, Any], broken: bool = False) -> Any:
    from pickfit.usability import ComfortAnswer

    return ComfortAnswer.model_validate({"observed": "a chat window", "seen": cite(1, "Chats"),
                                         "screen_broken": broken, "defects": list(defects)})


def test_comfort_counts_measurable_defects_and_keeps_unverified_ones(bundle: Bundle) -> None:
    from pickfit.usability import check_comfort

    finder, shots = TextFinder(fake_ocr), bundle.first_look_shots()
    assert check_comfort(comfort_answer(), shots, finder)[0] == {"score": 2, "status": "scored"}
    dim, found, _ = check_comfort(comfort_answer(defect("cramped", "minor", 1, "New message"),
                                                 defect("clipped", "minor", 2, "not on screen")), shots, finder)
    assert dim["score"] == 1 and [d["found_by"] for d in found] == ["ocr", "unverified"]  # trusted, marked
    assert check_comfort(comfort_answer(defect("overlap", "major", 2, "pickfit1 sent")), shots, finder)[0]["score"] == 0
    # The sandbox's flaws never count; a defect on an image that does not exist is dropped.
    dim, found, problems = check_comfort(comfort_answer(defect("overlap", "major", 1, "Chats", cause="sandbox"),
                                                        defect("overlap", "major", 9, "Chats")), shots, finder)
    assert dim["score"] == 2 and len(found) == 1 and "image 9" in problems[0]
    assert check_comfort(comfort_answer(broken=True), shots, finder)[0] == {"score": None, "status": "sandbox_broken"}


def test_judge_takes_comfortable_from_the_inspector_in_one_call(bundle: Bundle, tmp_path: Path) -> None:
    calls: list[str] = []

    def ask(body: dict[str, Any], out: type, kind: str) -> Asked:
        calls.append(kind)
        if kind == "first_look":
            return Asked(first_answer(), 0.01, "muse-spark-1.3")
        return Asked(in_use_answer(op(1, (2, "pickfit1 sent")), op(2, (4, "No menu"))), 0.01, "muse-spark-1.3")

    def inspector(body: dict[str, Any], out: type, kind: str) -> Asked:
        calls.append(kind)
        assert "visual quality inspector" in body["instructions"]
        return Asked(comfort_answer(defect("bad_wrap", "minor", 1, "New message")), 0.05, "muse-wonder-1.0")

    result = judge(bundle, ask, TextFinder(fake_ocr), comfort=inspector)
    assert calls == ["first_look", "in_use", "first_look", "in_use", "comfort"]
    assert result["dimensions"]["comfortable"] == {"score": 1, "status": "scored"}
    assert result["prompt_version"].endswith("+comfort.v1") and result["cost_usd"] == 0.09
    assert "muse-wonder-1.0" in result["model"]
    comfortable = [f for f in result["findings"] if f["item"] == "comfortable"]
    assert [(f["kind"], f["severity"], f["samples"]) for f in comfortable] == [("bad_wrap", "minor", 1)]
    usability = Usability.model_validate(record_usability(result))
    assert usability.findings[0].kind == "bad_wrap"
    record = gui_record(tmp_path)
    record["usability"] = usability.model_dump(mode="json")
    SoftwareRecord.model_validate(record)


def test_pickfit_visual_checks_once_writes_visual_check_and_skips_what_it_already_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    import pickfit.usability as usability
    from pickfit.schema import SoftwareRecord as Record

    data = tmp_path / "data"
    data.mkdir()
    record = gui_record(tmp_path / "evidence")
    (data / "fixture-chat-tui.json").write_text(json.dumps(record), encoding="utf-8")
    calls: list[str] = []

    def fake_ask(*args: Any, **kwargs: Any) -> Any:
        def ask(body: dict[str, Any], out: type, kind: str) -> Asked:
            calls.append(kind)
            return Asked(comfort_answer(defect("raw_markup", "minor", 1, "Chats")), 0.03, "muse-wonder-1.0")
        return ask

    monkeypatch.setattr(usability, "meta_ask", fake_ask)
    monkeypatch.setattr(usability, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(usability, "TextFinder", lambda: TextFinder(fake_ocr))
    real_bundle_for = usability.bundle_for
    monkeypatch.setattr(usability, "bundle_for", lambda raw: real_bundle_for(raw, tmp_path / "evidence"))
    args = argparse.Namespace(slug=["fixture-chat-tui"], pilot=False, all=False, data_dir=str(data), cap=1.0,
                              force=False, write=True, dry_run=False, verbose=True)
    assert usability.main_visual(args) == 0 and calls == ["comfort"]
    written = Record.model_validate(json.loads((data / "fixture-chat-tui.json").read_text(encoding="utf-8")))
    assert written.visual_check is not None and written.visual_check.score == 1
    assert written.visual_check.defects[0].kind == "raw_markup" and written.visual_check.effort == "medium"
    assert usability.main_visual(args) == 0 and calls == ["comfort"]  # same screens and prompt: no second call
