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
    assert index["count"] == 5
    slugs = [e["slug"] for e in index["entries"]]
    assert slugs == sorted(slugs)
    assert all(e["repo_url"].startswith("https://example.invalid/") for e in index["entries"])


def test_only_run_install_guides_are_indexed(data_dir: Path) -> None:
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    # macOS is only a README claim for fixture-transcribe: no steps reach the Worker.
    assert set(entries["fixture-transcribe"]["install"]) == {"linux"}
    runner = entries["fixture-llm-runner"]["install"]
    assert {os: g["basis"] for os, g in runner.items()} == {"macos": "human", "linux": "replayed"}
    assert runner["linux"]["run"]["replayed"] is True
    assert runner["linux"]["run"]["evidence_url"].startswith("https://example.invalid/runs/")
    assert runner["linux"]["works_offline"] is True and runner["macos"]["works_offline"] is None
    assert runner["linux"]["first_task_setup"] == [{"command": "fixture-llm-runner pull tiny-test",
                                                   "background": False}]


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
    assert json.loads(out.read_text(encoding="utf-8"))["count"] == 5


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
