"""scripts/capability_opus_report.py: it names the run's model and lists where two runs differ."""

from scripts.capability_opus_report import differences, model_of


def _row(qid, slug, model, picks, matched="claude-opus-5-5"):
    return {"id": qid, "lang": "en", "slug": slug, "model": model, "modelPicks": picks, "matchedBy": matched}


def test_model_of_prefers_model_id_then_the_most_common_match() -> None:
    assert model_of({"summary": {"model_id": "claude-sonnet-5-5"}, "rows": []}) == "claude-sonnet-5-5"
    rows = [_row("a", None, None, []), _row("b", None, None, [], matched="rules")]
    assert model_of({"summary": {}, "rows": rows}) == "claude-opus-5-5"


def test_differences_lists_a_lost_target_and_changed_dev_picks() -> None:
    def graded(qid, picks):
        return ", ".join(picks) or "(none)"

    here = [_row("c1", "rustcode", False, ["fuigo"]), _row("c2", "glow", True, ["glow"]), _row("dev-q10", None, None, ["x"])]
    there = [_row("c1", "rustcode", True, ["rustcode"]), _row("c2", "glow", True, ["glow", "shine"]), _row("dev-q10", None, None, [])]
    out = differences(here, there, graded)
    assert out == ["c1 rustcode: missed here, found there · here ['fuigo'] · there ['rustcode']", "dev-q10: here x · there (none)"]
