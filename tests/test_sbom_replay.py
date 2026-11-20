"""pickfit sbom-replay: which records get an installed-tree SBOM, the dry run's estimate, and the replay with a fake
box (no Modal, no model, no network)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from verify_fakes import FakeBox

from pickfit import sbom_replay, security
from pickfit.sbom_replay import Candidate, classify, estimate, replay_one, select
from pickfit.verify.box import BoxError, ExecResult

RUN = "verify-tool-20261101-000000-abcd"


def gap(code: str, eco: str = "npm") -> dict[str, Any]:
    return security.gap(code, eco)


def record(slug: str = "tool", *, gaps: list[dict[str, Any]] | None = None, state: str = "partial",
           runs: list[dict[str, Any]] | None = None, status: str = "listed", check: bool = True) -> dict[str, Any]:
    runs = runs if runs is not None else [linux_run()]
    linux = next((r for r in runs if r.get("os") == "linux"), None)
    return {
        "slug": slug, "status": status,
        "verification": {"runs": runs},
        "install": {"linux": {"run_id": linux["id"], "steps": linux["steps"],
                              "check": {"command": "tool --version", "expected_signal": "tool 1.2.3"} if check else None}
                    if linux else None, "macos": None, "windows": None},
        "security": {"version": "sec.v2", "coverage": {"state": state, "gaps": gaps if gaps is not None else
                                                       [gap("binary.prebuilt_package")]}},
    }


def linux_run(run_id: str = RUN, *, os_name: str = "linux", level: str = "function",
              checked_at: str = "2026-11-01T00:00:00+08:00", steps: list[str] | None = None,
              **extra: Any) -> dict[str, Any]:
    return {"id": run_id, "level": level, "os": os_name, "method": "sandbox", "runner": "modal-gvisor",
            "checked_at": checked_at, "tool_version": "tool 1.2.3",
            "steps": [{"command": c, "purpose": ""} for c in (steps if steps is not None else
                                                              ["npm install -g tool", "tool --init"])], **extra}


def none_on_disk(run_id: str) -> bool:
    return False


def cls(raw: dict[str, Any]) -> tuple[Candidate | None, str | None]:
    return classify(raw, Path(f"{raw['slug']}.json"), sbom_on_disk=none_on_disk)


# --- eligibility --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(sbom_replay.SBOM_GAPS))
def test_each_sbom_closable_gap_is_eligible(code: str) -> None:
    cand, why = cls(record(gaps=[gap(code)]))
    assert why is None and cand is not None
    assert cand.gaps == (code,) and cand.run_id == RUN
    assert cand.steps == ("npm install -g tool", "tool --init") and not cand.toolchain


@pytest.mark.parametrize("eco", sorted(sbom_replay.ADAPTER_ECOSYSTEMS))
def test_adapter_missing_is_eligible_for_installed_ecosystems(eco: str) -> None:
    assert cls(record(gaps=[gap("adapter.missing", eco)]))[1] is None


@pytest.mark.parametrize("eco", ["swift", "cocoapods", "unknown"])
def test_adapter_missing_elsewhere_is_not(eco: str) -> None:
    assert cls(record(gaps=[gap("adapter.missing", eco)])) == (None, f"adapter:{eco}")


@pytest.mark.parametrize("code", ["advisory_db.no_ecosystem", "source.none", "platform.sbom_unsupported",
                                  "source.clone_failed", "tool.sbom_error"])
def test_gaps_an_sbom_cannot_close_make_it_ineligible(code: str) -> None:
    # One such gap is enough, even beside closable ones.
    assert cls(record(gaps=[gap("lockfile.missing"), gap(code, "c")])) == (None, f"gap:{code}")


def test_complete_unlisted_and_gapless_records_are_skipped() -> None:
    assert cls(record(state="complete", gaps=[]))[1] == "complete"
    assert cls(record(status="hidden"))[1] == "not_listed"
    assert cls(record(gaps=[]))[1] == "no_gaps"


def test_no_linux_pass() -> None:
    assert cls(record(runs=[]))[1] == "no_linux_pass"
    assert cls(record(runs=[linux_run(level="failed")]))[1] == "no_linux_pass"
    assert cls(record(runs=[linux_run(os_name="macos")]))[1] == "no_linux_pass"


def test_latest_pass_on_another_os_is_skipped() -> None:
    # installed_of ties an SBOM to the latest passed run: a Linux tree must not be saved under a macOS run.
    runs = [linux_run(), linux_run("verify-tool-mac", os_name="macos", checked_at="2026-11-02T00:00:00+08:00")]
    assert cls(record(runs=runs))[1] == "latest_pass_not_linux"


def test_web_runs_and_empty_steps_are_skipped() -> None:
    assert cls(record(runs=[linux_run(runner="modal-vm-chromium", web={"url": "x"})]))[1] == "web_run"
    assert cls(record(runs=[linux_run(steps=[])]))[1] == "no_steps"


def test_an_sbom_already_on_disk_is_skipped() -> None:
    raw = record()
    assert classify(raw, Path("tool.json"), sbom_on_disk=lambda rid: rid == RUN) == (None, "sbom_on_disk")


def test_a_compiling_step_gets_a_build_box() -> None:
    cand, _ = cls(record(runs=[linux_run(steps=["cargo install tool"])]))
    assert cand is not None and cand.toolchain


def test_legacy_sec_v1_record_reads_its_reason_as_the_gap() -> None:
    raw = record()
    raw["security"] = {"status": "unchecked", "unchecked_reason": "no_lockfile", "checked_at": "2026-11-01"}
    cand, why = cls(raw)
    assert why is None and cand is not None and cand.gaps == ("lockfile.missing",) and cand.coverage == "unchecked"


# --- dry run --------------------------------------------------------------------------------------------------------


def write_records(tmp_path: Path, *raws: dict[str, Any]) -> Path:
    d = tmp_path / "software"
    d.mkdir()
    for raw in raws:
        (d / f"{raw['slug']}.json").write_text(json.dumps(raw), encoding="utf-8")
    return d


def args(data_dir: Path, **over: Any) -> argparse.Namespace:
    base = dict(data_dir=str(data_dir), slug=None, limit=None, workers=2, run=False, dry_run=False, rescan=False,
                write=False, report=None)
    return argparse.Namespace(**{**base, **over})


def test_select_honours_slug_and_limit(tmp_path: Path) -> None:
    d = write_records(tmp_path, record("a"), record("b"), record("c", state="complete", gaps=[]))
    sel = select(d.glob("*.json"), sbom_on_disk=none_on_disk)
    assert [c.slug for c in sel.eligible] == ["a", "b"] and sel.skipped == {"c": "complete"}
    assert [c.slug for c in select(d.glob("*.json"), slugs=["b"], sbom_on_disk=none_on_disk).eligible] == ["b"]
    sel = select(d.glob("*.json"), limit=1, sbom_on_disk=none_on_disk)
    assert [c.slug for c in sel.eligible] == ["a"] and sel.skipped["b"] == "over_limit"


def test_estimate_is_boxes_times_minutes_times_the_modal_rate() -> None:
    from pickfit.verify.modal_box import CORE_USD_PER_S, GIB_USD_PER_S

    plain_rate = 1 * CORE_USD_PER_S + 2 * GIB_USD_PER_S  # 2 vCPU = 1 Modal core, 2 GiB
    build_rate = 4 * CORE_USD_PER_S + 6 * GIB_USD_PER_S  # 8 vCPU, 6 GiB
    assert sbom_replay.box_usd_per_second(False) == pytest.approx(plain_rate)
    assert sbom_replay.box_usd_per_second(True) == pytest.approx(build_rate)
    c = Candidate("a", Path("a.json"), RUN, ("x",), ("lockfile.missing",), "partial", False)
    est = estimate([c] * 150 + [Candidate("b", Path("b.json"), RUN, ("cargo install b",), (), "partial", True)] * 5)
    want = 150 * 5 * 60 * plain_rate + 5 * 12 * 60 * build_rate
    assert est["usd"] == round(want, 2) and est["boxes"] == 155 and est["build_boxes"] == 5
    assert 2 <= est["usd"] <= 5 and est["model_calls"] == 0


def test_dry_run_makes_no_box_and_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_sbom_paths", lambda rid: [tmp_path / "none" / rid / "sbom.json"])
    d = write_records(tmp_path, record("a"), record("b", gaps=[gap("source.none")]))

    def no_box(*_: Any) -> Any:
        raise AssertionError("a dry run makes no box")

    report = sbom_replay.run(args(d), make_box=no_box)
    assert report["mode"] == "dry_run" and report["eligible"] == 1
    assert report["candidates"] == [{"slug": "a", "run_id": RUN, "gaps": ["binary.prebuilt_package"], "steps": 2,
                                     "build_box": False, "coverage_before": "partial"}]
    assert report["not_eligible"] == {"gap": 1} and report["estimate"]["boxes"] == 1
    out = tmp_path / "r.json"
    monkeypatch.setattr(sbom_replay, "run", lambda a: report)
    assert sbom_replay.main(args(d, report=str(out))) == 0
    assert json.loads(out.read_text())["eligible"] == 1


def test_cli_registers_the_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pickfit import cli

    seen: dict[str, Any] = {}
    monkeypatch.setattr(sbom_replay, "run", lambda a: seen.setdefault("args", a) and {
        "mode": "dry_run", "eligible": 0, "estimate": {"usd": 0.0}, "candidates": []})
    assert cli.main(["sbom-replay", "--slug", "x", "--slug", "y", "--limit", "3", "--workers", "2",
                     "--report", str(tmp_path / "r.json")]) == 0
    a = seen["args"]
    assert (a.slug, a.limit, a.workers, a.run) == (["x", "y"], 3, 2, False)
    with pytest.raises(SystemExit):
        cli.main(["sbom-replay", "--run", "--dry-run"])


# --- the replay with a fake box --------------------------------------------------------------------------------------


INVENTORY = {"packages": [{"ecosystem": "npm", "name": "tool", "version": "1.2.3", "found_by": "npm-ls",
                           "locations": ["tool"]}],
             "go_binaries": [], "rust_binaries": [], "syft_version": "1.56.0",
             "artifacts": [{"sha256": "a" * 64, "path": "/home/sbx/.local/bin/tool"}], "status": {"syft": "0",
                                                                                                "npm": "0"},
             "errors": {}}


class ReplayBox(FakeBox):
    usd = 0.001

    def __init__(self, script: dict[str, tuple[int, str, str]] | None = None, *, fail_start: bool = False) -> None:
        super().__init__(script)
        self.fail_start = fail_start
        self.files["/tmp/pickfit-sbom/inventory.json"] = json.dumps(INVENTORY).encode()

    def start(self) -> None:
        if self.fail_start:
            raise BoxError("no capacity")

    def usd_per_second(self) -> float:
        return self.usd


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import pickfit.meta

    def boom(*_: Any, **__: Any) -> Any:
        raise AssertionError("sbom-replay must never call a model")

    monkeypatch.setattr(pickfit.meta, "call_meta", boom)


def factory(*boxes: ReplayBox) -> tuple[Any, list[tuple[str, str, bool]]]:
    made: list[tuple[str, str, bool]] = []
    queue = list(boxes)

    def make(replay_id: str, role: str, toolchain: bool) -> ReplayBox:
        made.append((replay_id, role, toolchain))
        return queue.pop(0)

    return make, made


def candidate(**over: Any) -> Candidate:
    base = dict(slug="tool", path=Path("tool.json"), run_id=RUN, steps=("npm install -g tool", "tool --init"),
                gaps=("binary.prebuilt_package",), coverage="partial", toolchain=False, tool_version="tool 1.2.3",
                check={"command": "tool --version", "expected_signal": "tool 1.2.3"})
    return Candidate(**{**base, **over})


def test_replay_runs_steps_in_order_and_saves_the_sbom(tmp_path: Path, no_model: None) -> None:
    box = ReplayBox({"tool --version": (0, "tool 1.2.3\n", "")})
    make, made = factory(box)
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    assert row["error"] is None and made[0][1:] == ("sbom-replay", False)
    commands = [c for c, _ in box.ran]
    assert commands[:3] == ["npm install -g tool", "tool --init", "tool --version"]
    assert commands[3].startswith("mkdir -p /tmp/pickfit-sbom")  # then the SBOM, before the box closes
    assert box.closed and row["box_usd"] >= 0
    doc = json.loads((tmp_path / RUN / "sbom.json").read_text(encoding="utf-8"))
    assert (doc["run_id"], doc["tool_version"]) == (RUN, "tool 1.2.3")
    assert doc["replay"]["of_run"] == RUN and doc["replay"]["version_drift"] is False
    assert [p["name"] for p in doc["packages"]] == ["tool"]
    assert row["sbom"]["packages"] == 1 and row["sbom"]["path"] == str(tmp_path / RUN / "sbom.json")


def test_the_saved_sbom_is_where_installed_of_reads_it(tmp_path: Path, no_model: None,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    make, _ = factory(ReplayBox({"tool --version": (0, "tool 1.2.3\n", "")}))
    replay_one(candidate(), make, evidence_root=home / ".pickfit" / "evidence", log=lambda _: None)
    raw = record()
    raw["prerequisites"] = []
    inv = security.installed_of(raw)
    assert inv is not None and inv.run_id == RUN and [p["name"] for p in inv.packages] == ["tool"]
    assert cls(raw)[1] is None  # the classifier was told nothing is on disk; the real check sees it:
    assert classify(raw, Path("tool.json"))[1] == "sbom_on_disk"


def test_a_failing_step_stops_without_an_sbom_and_closes_the_box(tmp_path: Path, no_model: None) -> None:
    box = ReplayBox({"npm install": (1, "", "E404 not found")})
    make, _ = factory(box)
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    assert row["error"].startswith("step 1 exited 1") and "E404" in row["error"]
    assert [c for c, _ in box.ran] == ["npm install -g tool"]
    assert box.closed and row["sbom"] is None and not (tmp_path / RUN).exists()


def test_a_failed_install_check_saves_no_sbom(tmp_path: Path, no_model: None) -> None:
    box = ReplayBox({"tool --version": (127, "", "tool: not found")})
    make, _ = factory(box)
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    assert row["error"].startswith("install check exited 127") and box.closed and row["sbom"] is None


def test_a_newer_release_is_kept_as_version_drift(tmp_path: Path, no_model: None) -> None:
    make, _ = factory(ReplayBox({"tool --version": (0, "tool 2.0.0\n", "")}))
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    doc = json.loads((tmp_path / RUN / "sbom.json").read_text(encoding="utf-8"))
    assert row["sbom"]["version_drift"] and doc["tool_version"] == "tool 2.0.0"
    assert doc["replay"]["recorded_tool_version"] == "tool 1.2.3"


def test_box_errors_and_crashes_still_close_the_box(tmp_path: Path, no_model: None) -> None:
    box = ReplayBox(fail_start=True)
    make, _ = factory(box)
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    assert row["error"] == "box error: no capacity" and box.closed

    class Crashing(ReplayBox):
        def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
            raise RuntimeError("boom")

    crashing = Crashing()
    make, _ = factory(crashing)
    row = replay_one(candidate(), make, evidence_root=tmp_path, log=lambda _: None)
    assert row["error"] == "RuntimeError: boom" and crashing.closed and not (tmp_path / RUN).exists()


def test_a_build_box_is_asked_for_compiling_steps(tmp_path: Path, no_model: None) -> None:
    make, made = factory(ReplayBox())
    replay_one(candidate(steps=("cargo install tool",), toolchain=True, check=None), make, evidence_root=tmp_path,
               log=lambda _: None)
    assert made[0][2] is True


def test_run_replays_each_record_in_its_own_box_and_rescans(tmp_path: Path, no_model: None,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_sbom_paths", lambda rid: [tmp_path / "none" / rid / "sbom.json"])
    d = write_records(tmp_path, record("a"), record("b"))
    boxes = [ReplayBox({"tool --version": (0, "tool 1.2.3\n", "")}),
             ReplayBox({"npm install": (1, "", "boom")})]
    made: list[str] = []

    def make(replay_id: str, role: str, toolchain: bool) -> ReplayBox:
        made.append(replay_id)
        return boxes[0] if "-a-" in replay_id else boxes[1]

    checked: list[str] = []

    def checker(raw: dict[str, Any]) -> dict[str, Any]:
        checked.append(raw["slug"])
        return {"coverage": {"state": "complete", "gaps": []}, "observation": {"target": "installed_artifact"},
                "assessment": {"level": "none"}}

    report = sbom_replay.run(args(d, run=True, rescan=True), make_box=make, checker=checker,
                             evidence_root=tmp_path / "ev", log=lambda _: None)
    assert len(made) == 2 and all(b.closed for b in boxes)
    assert (report["replayed"], report["sbom_collected"]) == (2, 1)
    assert checked == ["a"]  # only a record that got its SBOM is rescanned
    assert report["coverage"] == {"rescanned": 1, "before": {"partial": 1}, "after": {"complete": 1}, "written": 0}
    assert list(report["errors"]) == ["b"]
    row = next(r for r in report["rows"] if r["slug"] == "a")
    assert row["rescan"]["gaps_before"] == ["binary.prebuilt_package"] and row["rescan"]["written"] is False


def test_write_stores_the_check(tmp_path: Path, no_model: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_sbom_paths", lambda rid: [tmp_path / "none" / rid / "sbom.json"])
    d = write_records(tmp_path, record("a"))
    written: list[Path] = []
    monkeypatch.setattr(security, "write_security", lambda path, result, now: written.append(path))
    make, _ = factory(ReplayBox({"tool --version": (0, "tool 1.2.3\n", "")}))
    result = {"coverage": {"state": "complete", "gaps": []}, "observation": {"target": "installed_artifact"},
              "assessment": {"level": "none"}}
    report = sbom_replay.run(args(d, run=True, rescan=True, write=True), make_box=make, checker=lambda raw: result,
                             evidence_root=tmp_path / "ev", log=lambda _: None)
    assert written == [d / "a.json"] and report["coverage"]["written"] == 1
