"""Track C's round trip (brief 15.3 C, 15.10-5): an MCP tool call or script makes a file, the GUI edits and saves
it, pickfit checks the saved file. No box, no model: the GUI step is a callable here."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path

import pytest

from pickfit.verify import gui_operate as op
from pickfit.verify.box import BOX_HOME
from pickfit.verify.gui_operate import GuiInput, OperateArgs
from test_verify_gui_operate import FILE_CHECK, LAUNCH, NOTE_GOAL, NonceServer, OperateBox, no_aim, note_session  # noqa: F401

DOCS = ("docx", "pptx", "xlsx")


def rezip(data: bytes, edit: dict[str, bytes | None]) -> bytes:
    """The OOXML zip with parts replaced (bytes) or removed (None)."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as book:
        for name in src.namelist():
            if name in edit:
                if edit[name] is not None:
                    book.writestr(name, edit[name])
            else:
                book.writestr(name, src.read(name))
    return out.getvalue()


def main_part(kind: str) -> str:
    return {"docx": "word/document.xml", "pptx": "ppt/slides/slide1.xml", "xlsx": "xl/worksheets/sheet1.xml"}[kind]


# ---------------------------------------------------------------- samples and formats


@pytest.mark.parametrize("kind", [*DOCS, "svg"])
def test_pickfits_document_samples_are_well_formed_and_the_same_every_time(kind: str):
    data = op.sample_file(kind)
    assert data == op.sample_file(kind)
    assert op.format_problem(data, kind) is None
    assert op.SAMPLE_TEXT in op.document_text(data, kind)
    if kind in DOCS:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert names[:2] == ["[Content_Types].xml", "_rels/.rels"] and main_part(kind) in names
        assert op._box_fmt()(data, kind)  # root's in-box check agrees with the host's
    assert kind in op.SAMPLES and kind in op.FORMATS


@pytest.mark.parametrize("kind", DOCS)
def test_a_damaged_or_mislabelled_office_file_is_not_well_formed(kind: str):
    good = op.sample_file(kind)
    other = {"docx": "xlsx", "pptx": "docx", "xlsx": "pptx"}[kind]
    assert "not a" in (op.format_problem(good, other) or "")  # a docx is not an xlsx
    assert op.format_problem(good[: len(good) // 2], kind)  # cut short
    assert op.format_problem(b"plain text", kind) == "not a zip (an OOXML file is one)"
    assert op.format_problem(rezip(good, {"_rels/.rels": None}), kind) == "no _rels/.rels"
    for part in {main_part(kind), "[Content_Types].xml"}:  # any part that does not parse (a sheet, a slide)
        broken = rezip(good, {part: b"<oops"})
        assert "unreadable" in (op.format_problem(broken, kind) or ""), part
        assert not box_ok(broken, kind)
    assert not box_ok(rezip(good, {"_rels/.rels": b"<Relationships/>"}), kind)


def box_ok(data: bytes, kind: str) -> bool:
    """Root's in-box format test as its judge() reads it: an exception is format_ok False."""
    try:
        return bool(op._box_fmt()(data, kind))
    except Exception:  # noqa: BLE001
        return False


def test_an_svg_must_parse_with_an_svg_root():
    assert op.format_problem(b'<svg xmlns="http://www.w3.org/2000/svg"/>', "svg") is None
    assert op.format_problem(b"<svg><rect></svg>", "svg").startswith("not well-formed XML")
    assert op.format_problem(b"<html/>", "svg") == "the root is html, not <svg>"
    assert op.format_problem(op.sample_file("png"), "png") is None  # the other formats: root's own test
    assert op.format_problem(b"nope", "png") == "not a png file"


def test_root_checks_an_office_file_the_app_saves_in_the_box(tmp_path: Path):
    """The in-box file check (_FILE_PY) takes docx, pptx and xlsx as formats."""
    box = OperateBox(tmp_path / "home")
    out = tmp_path / "home" / "pickfit-out"
    out.mkdir(parents=True)
    (out / "a.docx").write_bytes(op.sample_file("docx"))
    (out / "b.docx").write_bytes(b"PK\x03\x04 not really")
    params = {"mode": "after", "since": 0, "format": "docx"}
    good = op.file_probe(box, {**params, "target": f"{BOX_HOME}/pickfit-out/a.docx"})
    bad = op.file_probe(box, {**params, "target": f"{BOX_HOME}/pickfit-out/b.docx"})
    assert good["found"]["format_ok"] is True and bad["found"]["format_ok"] is False


# ---------------------------------------------------------------- mcp_output as a GUI input


def args_with(inputs: list[dict]) -> OperateArgs:
    return OperateArgs.model_validate({"command": LAUNCH, "wait_s": 20, "feature": 1, "goal": NOTE_GOAL,
                                       "inputs": inputs, "check": FILE_CHECK})


def test_an_mcp_output_input_names_the_upstream_file_and_nothing_else():
    ok = GuiInput.model_validate({"path": "~/pickfit-in/deck.pptx", "source": "mcp_output",
                                  "from_path": "~/work/deck.pptx", "text": None, "sample": "null"})
    assert ok.kind == "mcp_output" and ok.sample is None
    assert GuiInput(path="~/pickfit-in/a.txt", text="x").kind == "text"  # the older shapes, unchanged
    assert GuiInput(path="~/pickfit-in/a.docx", sample="docx").kind == "sample"
    assert op.spec_problems(args_with([ok.model_dump()])) == []
    cases = {
        "takes from_path and nothing else": {"source": "mcp_output", "from_path": "~/w/a.docx", "text": "x"},
        "of source mcp_output takes from_path": {"source": "mcp_output"},
        "must be a file in the box user's home": {"from_path": "/etc/passwd"},
        "the upstream step saves elsewhere": {"from_path": "~/pickfit-out/a.docx"},
        "no .. in paths": {"from_path": "~/../root/a.docx"},
        "of source text takes text": {"source": "text", "sample": "png"},
        "needs exactly one of text or sample": {"text": "x", "sample": "png"},
    }
    for why, extra in cases.items():
        problems = op.spec_problems(args_with([{"path": "~/pickfit-in/a.docx", **extra}]))
        assert any(why in p for p in problems), (why, problems)


def test_an_operation_copies_the_upstream_file_into_pickfit_in_and_records_its_hash(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    deck = op.sample_file("pptx")
    box.write_file(f"{BOX_HOME}/work/deck.pptx", deck)  # what the MCP tool call saved
    args = args_with([{"path": "~/pickfit-in/deck.pptx", "source": "mcp_output", "from_path": "~/work/deck.pptx"}])
    result, operation, _ = op.run_operation(box, args, 5, log=lambda s: None,
                                            client=NonceServer(*note_session()).client(), sleep=lambda s: None)
    assert (tmp_path / "home" / "pickfit-in" / "deck.pptx").read_bytes() == deck
    assert operation.inputs[0]["staged"] == {"from": f"{BOX_HOME}/work/deck.pptx", "bytes": len(deck),
                                             "sha256": hashlib.sha256(deck).hexdigest()}
    assert operation.passed, result.stdout  # the note app still saves its note: the input changed nothing else


def test_an_operation_whose_upstream_file_is_missing_is_not_operated(tmp_path: Path):
    box = OperateBox(tmp_path / "home")
    args = args_with([{"path": "~/pickfit-in/deck.pptx", "source": "mcp_output", "from_path": "~/work/deck.pptx"}])
    result, operation, _ = op.run_operation(box, args, 6, log=lambda s: None,
                                            client=NonceServer(*note_session()).client(), sleep=lambda s: None)
    assert not operation.passed and operation.stop == "no_window"
    assert "the upstream step's file /home/sbx/work/deck.pptx cannot be read" in result.stdout


# ---------------------------------------------------------------- verify_coedit_roundtrip


def upstream_file(tmp_path: Path, kind: str) -> Path:
    path = tmp_path / "mcp" / f"made.{kind}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(op.sample_file(kind))
    return path


def edit_text(kind: str, new: str):
    """A GUI that replaces the sample's text with `new` and saves over the file."""
    def operate(path: Path) -> None:
        data = path.read_bytes()
        if kind == "svg":
            path.write_bytes(data.replace(op.SAMPLE_TEXT.encode(), new.encode()))
        else:
            part = main_part(kind)
            xml = zipfile.ZipFile(io.BytesIO(data)).read(part).replace(op.SAMPLE_TEXT.encode(), new.encode())
            path.write_bytes(rezip(data, {part: xml}))
    return operate


@pytest.mark.parametrize("kind", [*DOCS, "svg"])
def test_a_gui_edit_that_saves_a_changed_well_formed_file_passes(tmp_path: Path, kind: str):
    upstream = upstream_file(tmp_path, kind)
    result = op.verify_coedit_roundtrip(upstream, tmp_path / "gui", edit_text(kind, "edited in the GUI"),
                                        format=kind, contains=["edited in the GUI"])
    assert result.passed and result.why is None, result.why
    assert result.checks == {"exists": True, "sha256_changed": True, "mtime_changed": result.checks["mtime_changed"],
                             "format_ok": True}
    assert result.before.sha256 == result.upstream.sha256 == hashlib.sha256(upstream.read_bytes()).hexdigest()
    assert result.after.sha256 != result.before.sha256 and result.contains == {"edited in the GUI": True}
    assert Path(result.before.path) == tmp_path / "gui" / "pickfit-in" / upstream.name
    assert upstream.read_bytes() == op.sample_file(kind)  # the upstream file itself is never touched
    assert result.to_dict()["after"]["exists"] is True


def test_a_save_that_changes_only_the_mtime_fails(tmp_path: Path):
    upstream = upstream_file(tmp_path, "docx")

    def resave(path: Path) -> None:
        path.write_bytes(path.read_bytes())
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 30))

    result = op.verify_coedit_roundtrip(upstream, tmp_path / "gui", resave, format="docx")
    assert not result.passed and result.checks["mtime_changed"] and not result.checks["sha256_changed"]
    assert result.why == "the saved file has the same sha256 as the input: nothing was edited"


def test_a_gui_that_saves_a_damaged_file_fails(tmp_path: Path):
    upstream = upstream_file(tmp_path, "xlsx")

    def damage(path: Path) -> None:
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])

    result = op.verify_coedit_roundtrip(upstream, tmp_path / "gui", damage, format="xlsx")
    assert not result.passed and result.checks["sha256_changed"] and not result.checks["format_ok"]
    assert result.why.startswith("the saved file is not a well-formed xlsx")
    svg = op.verify_coedit_roundtrip(upstream_file(tmp_path, "svg"), tmp_path / "gui2",
                                     lambda p: p.write_bytes(p.read_bytes()[:-20]), format="svg")
    assert not svg.passed and "not well-formed XML" in svg.why


def test_the_round_trip_fails_on_a_bad_upstream_file_a_missing_save_text_or_a_gui_error(tmp_path: Path):
    bad = tmp_path / "mcp" / "bad.docx"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not a docx")
    result = op.verify_coedit_roundtrip(bad, tmp_path / "g1", edit_text("docx", "x"), format="docx")
    assert not result.passed and result.why.startswith("the upstream file is not a well-formed docx")
    missing = op.verify_coedit_roundtrip(tmp_path / "none.docx", tmp_path / "g2", edit_text("docx", "x"),
                                         format="docx")
    assert missing.why == "the upstream step left no file"
    upstream = upstream_file(tmp_path, "docx")
    elsewhere = op.verify_coedit_roundtrip(upstream, tmp_path / "g3", edit_text("docx", "x"), format="docx",
                                           output="pickfit-out/saved.docx")
    assert not elsewhere.passed and elsewhere.why.startswith("no file at")
    lacking = op.verify_coedit_roundtrip(upstream, tmp_path / "g4", edit_text("docx", "other"), format="docx",
                                         contains=["expected words"])
    assert not lacking.passed and lacking.contains == {"expected words": False}

    def crash(path: Path) -> None:
        raise RuntimeError("the window never opened")

    crashed = op.verify_coedit_roundtrip(upstream, tmp_path / "g5", crash, format="docx")
    assert not crashed.passed and crashed.operate_error == "RuntimeError: the window never opened"
    assert crashed.why == "the GUI step failed: RuntimeError: the window never opened"


def test_a_gui_that_saves_as_a_new_file_is_checked_there(tmp_path: Path):
    upstream = upstream_file(tmp_path, "pptx")

    def save_as(path: Path) -> None:
        target = path.parent.parent / "pickfit-out" / "deck.pptx"
        target.parent.mkdir(parents=True, exist_ok=True)
        edit_text("pptx", "slide edited")(path)
        target.write_bytes(path.read_bytes())

    result = op.verify_coedit_roundtrip(upstream, tmp_path / "gui", save_as, format="pptx",
                                        output="pickfit-out/deck.pptx", contains=["slide edited"])
    assert result.passed and result.after.path.endswith("pickfit-out/deck.pptx")
    with pytest.raises(ValueError):
        op.verify_coedit_roundtrip(upstream, tmp_path / "gui", save_as, format="odt")
