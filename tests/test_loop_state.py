"""scripts/loop_state.py: the loop's queue and issue list keep their shape whatever a session does."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "loop_state", Path(__file__).resolve().parent.parent / "scripts" / "loop_state.py")
loop_state = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(loop_state)


def run(loop_dir: Path, *argv: str) -> int:
    return loop_state.main(["--loop-dir", str(loop_dir), *argv])


def queue(loop_dir: Path) -> dict[str, dict]:
    return {item["id"]: item for item in loop_state.read_queue(loop_dir)}


def test_next_claims_in_order_and_resumes_an_item_left_doing(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "new", "--target", "owner/First")
    run(tmp_path, "add", "--kind", "new", "--target", "owner/second")
    capsys.readouterr()

    assert run(tmp_path, "next") == 0
    first = json.loads(capsys.readouterr().out)
    assert first["id"] == "new:owner/first" and first["status"] == "doing" and first["tries"] == 1

    # A session that ended mid-item: the next one gets the same item back, not a second one.
    assert run(tmp_path, "next") == 0
    again = json.loads(capsys.readouterr().out)
    assert again["id"] == first["id"] and again["tries"] == 1
    assert queue(tmp_path)["new:owner/second"]["status"] == "todo"


def test_add_refuses_a_duplicate_whatever_its_status(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "reverify", "--target", "ferro")
    run(tmp_path, "next")
    run(tmp_path, "finish", "reverify:ferro", "--result", "verified")
    run(tmp_path, "add", "--kind", "reverify", "--target", "Ferro")
    assert "already queued" in capsys.readouterr().out
    assert len(loop_state.read_queue(tmp_path)) == 1


def test_finish_needs_a_claimed_item(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "new", "--target", "a/b")
    assert run(tmp_path, "finish", "new:a/b", "--result", "verified") == 2
    assert "claim it with `next` first" in capsys.readouterr().err
    assert queue(tmp_path)["new:a/b"]["status"] == "todo"


def test_status_line_and_exit_code_when_nothing_is_left(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "new", "--target", "a/b")
    assert run(tmp_path, "status", "--exit-code") == 0
    run(tmp_path, "next")
    run(tmp_path, "finish", "new:a/b", "--result", "unverified", "--note", "needs an account")
    capsys.readouterr()
    assert run(tmp_path, "status", "--exit-code") == 3
    line = capsys.readouterr().out.strip()
    assert line.startswith("LOOP_STATUS todo=0 doing=0 done=1 parked=0 | results verified=0 unverified=1")
    assert run(tmp_path, "next") == 3


def test_park_names_an_issue_and_fixing_it_puts_the_items_back(tmp_path, capsys):
    assert run(tmp_path, "issue-new", "the box has no compiler", "--reason", "needs_toolchain") == 0
    assert capsys.readouterr().out.strip() == "H-001"
    run(tmp_path, "add", "--kind", "reverify", "--target", "ferro")
    run(tmp_path, "next")

    assert run(tmp_path, "park", "reverify:ferro", "--issue", "H-009") == 2  # no such issue
    assert run(tmp_path, "park", "reverify:ferro", "--issue", "H-001", "--note", "cargo not found") == 0
    assert queue(tmp_path)["reverify:ferro"]["status"] == "parked"

    capsys.readouterr()
    assert run(tmp_path, "issue-status", "H-001", "fixed") == 0
    assert "back in line: reverify:ferro" in capsys.readouterr().out
    item = queue(tmp_path)["reverify:ferro"]
    assert item["status"] == "todo" and item["tries"] == 0
    assert loop_state.read_issues(tmp_path) == {"H-001": "fixed"}


def test_an_item_whose_issue_waits_for_a_person_is_parked_not_retried(tmp_path, capsys):
    run(tmp_path, "issue-new", "the judge reads a dialog as the app")
    run(tmp_path, "add", "--kind", "reverify", "--target", "blocked", "--issue", "H-001")
    run(tmp_path, "add", "--kind", "reverify", "--target", "free")
    run(tmp_path, "issue-status", "H-001", "review")
    capsys.readouterr()

    assert run(tmp_path, "next") == 0
    assert json.loads(capsys.readouterr().out)["id"] == "reverify:free"
    assert queue(tmp_path)["reverify:blocked"]["status"] == "parked"


def test_an_item_claimed_too_often_is_parked(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "new", "--target", "a/b")
    items = loop_state.read_queue(tmp_path)
    items[0]["tries"] = loop_state.MAX_TRIES
    loop_state.write_queue(tmp_path, items)
    assert run(tmp_path, "next") == 3
    assert queue(tmp_path)["new:a/b"]["status"] == "parked"


def test_issue_ids_count_up_and_headings_keep_their_notes(tmp_path, capsys):
    run(tmp_path, "issue-new", "first")
    run(tmp_path, "issue-new", "second   issue")
    issues = tmp_path / "issues.md"
    issues.write_text(issues.read_text().replace("- symptom:", "- symptom: scroll does nothing", 1))
    run(tmp_path, "issue-status", "H-001", "fixing")
    text = issues.read_text()
    assert "## H-001 [fixing] first" in text and "## H-002 [open] second issue" in text
    assert "scroll does nothing" in text
    assert run(tmp_path, "issue-status", "H-007", "fixed") == 2


def test_seed_takes_only_the_box_reasons_and_links_the_issue(tmp_path, capsys):
    data = tmp_path / "software"
    data.mkdir()
    for slug, reason in [("ferro", "needs_toolchain"), ("dog", "needs_root"), ("acct", "needs_account"),
                         ("fine", None)]:
        (data / f"{slug}.json").write_text(json.dumps(
            {"slug": slug, "verification": {"level": "unverified" if reason else "function",
                                            "unverified_reason": reason}}))
    loop = tmp_path / "loop"
    run(loop, "issue-new", "the box has no compiler", "--reason", "needs_toolchain")
    assert run(loop, "seed-unverified", "--data-dir", str(data)) == 0
    items = queue(loop)
    assert set(items) == {"reverify:ferro", "reverify:dog"}
    assert items["reverify:ferro"]["issue"] == "H-001" and items["reverify:dog"]["issue"] is None
    # Seeding twice adds nothing.
    run(loop, "seed-unverified", "--data-dir", str(data))
    assert len(loop_state.read_queue(loop)) == 2


@pytest.mark.parametrize("argv", [["add", "--kind", "new", "--target", "a/b", "--issue", "H-404"]])
def test_an_unknown_issue_is_refused(tmp_path, argv):
    assert run(tmp_path, *argv) == 2
    assert loop_state.read_queue(tmp_path) == []


def test_a_done_item_recorded_by_mistake_can_be_reopened_with_a_reason(tmp_path, capsys):
    run(tmp_path, "add", "--kind", "reverify", "--target", "tool")
    run(tmp_path, "next")
    run(tmp_path, "finish", "reverify:tool", "--result", "verified", "--note", "written back")
    capsys.readouterr()

    assert run(tmp_path, "reopen", "reverify:tool", "--note", "the write-back was refused") == 0
    item = queue(tmp_path)["reverify:tool"]
    assert (item["status"], item["result"], item["note"]) == ("todo", None, "the write-back was refused")
    assert item["tries"] == 1  # the claim that went wrong still counts
    capsys.readouterr()
    # Only a closed item: a todo, doing or parked one is not reopened, and a reason is required.
    assert run(tmp_path, "reopen", "reverify:tool", "--note", "again") == 2
    assert "only a done item" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run(tmp_path, "reopen", "reverify:tool")
