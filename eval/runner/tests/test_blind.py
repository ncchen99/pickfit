"""Tests for eval/runner/blind.py on synthetic answers (no model calls)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blind  # noqa: E402

QUESTIONS = {
    "q01": {"id": "q01", "kind": "find_software", "prompt": "Need an MCP sync tool.", "constraints": {"os": "any"},
            "success_checklist": ["[L1] exists and free", "[L2] installs"]},
    "q02": {"id": "q02", "kind": "find_software", "prompt": "Need a log scrubber.", "constraints": {"os": "linux"},
            "success_checklist": ["[L1] OSI license", "[L2] masks"]},
    "q10": {"id": "q10", "kind": "builtin_enough", "prompt": "Character diff.", "constraints": {},
            "success_checklist": ["[L2] uses git", "[L3] says built-in is enough"]},
}
ANSWERS = {
    ("q01", "control"): "Use **mcpsync**. Install: `npm i -g mcpsync`.",
    ("q01", "experimental"): "pickfit's find_software suggests **mcpsync** (rec_0123456789ab, verified in a sandbox). "
                             "See https://pickfit-mcp-eval.ncchen99.workers.dev/mcp. Install: `npm i -g mcpsync`.",
    ("q02", "control"): "Use scrubby.",
    ("q02", "experimental"): "Per PickFit (mcp__pickfit__get_install_guide), use scrubby.",
    ("q10", "control"): "git diff --word-diff-regex=.",
}


def make_runs(base: Path, rnd: str = "run1") -> None:
    for (qid, group), text in ANSWERS.items():
        folder = base / rnd / qid / group / "attempt-1"
        folder.mkdir(parents=True)
        (folder / "meta.json").write_text(json.dumps({"attempt": 1, "valid": True, "model": "claude-opus-5-5"}))
        (folder / "answer.md").write_text(text)


def test_deidentify_removes_pickfit_and_lists_tells() -> None:
    text, tells = blind.deidentify(ANSWERS[("q01", "experimental")])
    assert "pickfit" not in text.lower() and "rec_" not in text and "find_software" not in text
    assert "workers.dev" not in text and text.count("[source]") >= 4
    assert "mcpsync" in text and "npm i -g mcpsync" in text
    assert "verified" in tells and "sandbox" in tells
    plain, none = blind.deidentify("Pick the one that fits; I picked fit-for-purpose tools.")
    assert plain == "Pick the one that fits; I picked fit-for-purpose tools." and none == []


def test_preference_form_is_blind_reproducible_and_unblinds(tmp_path: Path) -> None:
    base = tmp_path / "runs"
    make_runs(base)
    out = tmp_path / "form"
    result = blind.prefer("run1", 7, out, base, QUESTIONS)
    assert result["pairs"] == 2 and result["missing"] == ["q10"]
    form_text = (out / "prefer-form.json").read_text()
    page = (out / "prefer-form.html").read_text()
    for word in ("control", "experimental", "pickfit", "attempt", "claude-opus"):
        assert word not in form_text.lower() and word not in page.lower()
    again = blind.prefer("run1", 7, tmp_path / "form2", base, QUESTIONS)
    assert again["form_sha256"] == result["form_sha256"]
    form = json.loads(form_text)
    key = json.loads((out / "prefer-key.json").read_text())
    exp_side = {q: ("A" if v["A"]["group"] == "experimental" else "B") for q, v in key["pairs"].items() if "A" in v}
    choices = {"form_sha256": result["form_sha256"],
               "choices": {"q01": {"choice": exp_side["q01"], "reason": "clearer"}, "q02": {"choice": "tie", "reason": "same"}}}
    (tmp_path / "c.json").write_text(json.dumps(choices))
    report = blind.unblind_prefer(out, tmp_path / "c.json")
    assert report["tally"] == {"control": 0, "experimental": 1, "tie": 1, "unanswered": 0}
    assert form["key_sha256"] == blind.sha256_bytes((out / "prefer-key.json").read_bytes())
    (tmp_path / "other.json").write_text(json.dumps(dict(choices, form_sha256="0" * 64)))
    with pytest.raises(SystemExit):
        blind.unblind_prefer(out, tmp_path / "other.json")


def test_answers_batch_and_unblind(tmp_path: Path) -> None:
    base = tmp_path / "runs"
    make_runs(base)
    adir, bdir = tmp_path / "answers", tmp_path / "batch"
    assert blind.answers(["run1"], 3, adir, base, QUESTIONS)["answers"] == 5
    rows = [json.loads(line) for line in (adir / "answers.jsonl").read_text().splitlines()]
    assert all("pickfit" not in r["text"].lower() for r in rows)
    assert "group" not in rows[0] and "round" not in rows[0]
    by_q = {}
    for r in rows:
        by_q.setdefault(r["question"], []).append(r["answer_id"])
    with (adir / "picks.csv").open() as fh:
        picks = list(csv.DictReader(fh))
    for p in picks:
        p.update({"q01": {"pick_kind": "tool", "pick_tool": "mcpsync", "install_method": "npm i -g mcpsync"},
                  "q02": {"pick_kind": "tool", "pick_tool": "Scrubby", "install_method": ""},
                  "q10": {"pick_kind": "none", "pick_tool": "", "install_method": ""}}[p["question"]])
    with (adir / "picks.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(picks[0]))
        w.writeheader()
        w.writerows(picks)
    result = blind.l1_batch(adir, adir / "picks.csv", "A", 5, bdir, QUESTIONS)
    assert result == {"items": 2, "answers_without_item": 1, "key_sha256": result["key_sha256"]}  # same pick merged
    items = [json.loads(line) for line in (bdir / "l1-batch.jsonl").read_text().splitlines()]
    assert {i["question"]["id"] for i in items} == {"q01", "q02"}
    assert all(c.startswith("[L1]") for i in items for c in i["question"]["l1_checks"])
    with (bdir / "l1-form.csv").open() as fh:
        form = list(csv.DictReader(fh))
    for row in form:
        row["overall"] = "pass" if row["question"] == "q01" else "fail"
    with (bdir / "verdicts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(form[0]))
        w.writeheader()
        w.writerows(form)
    out = blind.unblind_l1(bdir, adir, bdir / "verdicts.csv")["rows"]
    got = {(r["question"], r["group"]): r["l1"] for r in out}
    assert got == {("q01", "control"): "pass", ("q01", "experimental"): "pass", ("q02", "control"): "fail",
                   ("q02", "experimental"): "fail", ("q10", "control"): "none"}


def test_q10_and_q20_items_use_their_l3_checks() -> None:
    assert blind.checks_for(QUESTIONS["q10"]) == ["[L3] says built-in is enough"]


def test_an_unfilled_pick_stops_the_batch(tmp_path: Path) -> None:
    base = tmp_path / "runs"
    make_runs(base)
    blind.answers(["run1"], 3, tmp_path / "a", base, QUESTIONS)
    with pytest.raises(SystemExit):
        blind.l1_batch(tmp_path / "a", tmp_path / "a" / "picks.csv", "A", 5, tmp_path / "b", QUESTIONS)


def test_the_real_question_files_give_every_item_checks() -> None:
    for rounds in (["run1"], ["bset"]):
        qs = blind.questions_by_id(rounds)
        assert qs and all(blind.checks_for(q) for q in qs.values())


def test_each_use_draws_from_its_own_seed_derived_from_the_fixed_integer(tmp_path: Path) -> None:
    assert blind.EVAL_SEED == 20261102
    # sha256("20261102:prefer:run1"), first 16 hex digits; fixed, so a changed rule shows up here
    assert blind.use_seed(20261102, "prefer:run1") == int(blind.sha256_bytes(b"20261102:prefer:run1")[:16], 16)
    assert len({blind.use_seed(20261102, u) for u in ("prefer:run1", "answers:run1", "l1-batch:A", "l1-batch:B")}) == 4
    base = tmp_path / "runs"
    make_runs(base)
    blind.prefer("run1", blind.EVAL_SEED, tmp_path / "form", base, QUESTIONS)
    key = json.loads((tmp_path / "form" / "prefer-key.json").read_text(encoding="utf-8"))
    form = json.loads((tmp_path / "form" / "prefer-form.json").read_text(encoding="utf-8"))
    for record in (key, form):
        assert (record["seed"], record["use"]) == (20261102, "prefer:run1")
        assert record["use_seed"] == blind.use_seed(20261102, "prefer:run1")
    assert "seed 20261102 (prefer:run1: " in (tmp_path / "form" / "prefer-form.html").read_text(encoding="utf-8")
    blind.answers(["run1"], blind.EVAL_SEED, tmp_path / "a", base, QUESTIONS)
    assert json.loads((tmp_path / "a" / "answers-key.json").read_text(encoding="utf-8"))["use"] == "answers:run1"
