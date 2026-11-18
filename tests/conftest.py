"""Every test gets its own ledger and runs directory.

The shared ledger (~/.pickfit/ledger.sqlite) is the record of what model calls cost, and runs/traces is the
record of the calls themselves. A test that reaches call_meta without passing a ledger or a runs directory
would write its test double's made-up tokens into both: tests/test_verify_gui_operate.py did, a few rows on
every run (priced as Muse Spark Open during the hackathon, as Claude Opus on 11/15 and 11/16). A test that
sets PICKFIT_LEDGER or PICKFIT_RUNS_DIR itself, or passes its own ledger, still gets what it asked for.

Tart's state directory (~/.pickfit/tart: the base VMs' manifests and logs) is a test's own too, and no test runs
against a remote Mac. On 11/17 a test of prepare_base's failure path ran while the default state directory had
moved to tart_host, deleted the real pickfit-macos-26.json and emptied its log; the manifest was written back from
a copy. A test that wants a state directory passes its own, as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_shared_ledger_or_traces(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    scratch: Path = tmp_path_factory.mktemp("pickfit")
    monkeypatch.setenv("PICKFIT_LEDGER", str(scratch / "ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(scratch / "runs"))
    monkeypatch.delenv("PICKFIT_TART_HOST", raising=False)
    from pickfit.verify import tart_box, tart_host

    monkeypatch.setattr(tart_box, "STATE_DIR", scratch / "tart")
    monkeypatch.setattr(tart_host, "STATE_DIR", scratch / "tart")
