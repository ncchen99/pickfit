"""DockerBox against a real Docker daemon (opt-in: PICKFIT_DOCKER_TESTS=1).

Starts real containers from the sandbox image, so it is slow the first time
(the image build) and is skipped by default. The model is still mocked.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import pickfit.env
from pickfit import meta
from pickfit.ledger import Caps, Ledger
from pickfit.verify.agent import VerifyAgent
from pickfit.verify.box import DockerBox
from pickfit.verify.task import load_fixture
from verify_fakes import FakeServer, finish, response, run_cmd

pytestmark = pytest.mark.skipif(os.environ.get("PICKFIT_DOCKER_TESTS") != "1",
                                reason="set PICKFIT_DOCKER_TESTS=1 to run against Docker")

FIXTURES = Path(__file__).parent / "fixtures" / "verify"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


@pytest.fixture
def box():
    b = DockerBox(labels={"pickfit.test": "1"}, log=lambda line: None)
    b.start()
    yield b
    b.close()


def test_cloud_metadata_is_unreachable_and_routes_are_root_only(box: DockerBox):
    result = box.exec("curl -sS -m 5 http://169.254.169.254/latest/meta-data/", 20)
    assert result.exit_code == 7 and result.seconds < 3  # refused at once, not a 5 s timeout
    assert "unreachable 169.254.0.0/16" in box.exec("ip route show", 10).stdout
    change = box.exec("ip route del unreachable 169.254.0.0/16", 10)
    assert change.exit_code != 0  # the box user cannot lift the block


def test_network_off_keeps_localhost(box: DockerBox):
    box.exec("python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 & sleep 1", 10)
    box.set_network(False)
    assert box.exec("curl -sS -m 5 https://pypi.org/simple/ -o /dev/null", 15).exit_code != 0
    assert box.exec("curl -sS -m 5 http://127.0.0.1:8765/ -o /dev/null", 15).exit_code == 0
    box.set_network(True)
    blocked = box.exec("curl -sS -m 5 http://169.254.169.254/", 15)
    assert blocked.exit_code == 7 and blocked.seconds < 3  # still blocked after reconnecting


def test_run_background_starts_a_real_server_the_agent_can_query(box: DockerBox, tmp_path: Path):
    task = load_fixture(FIXTURES / "graphtty.json", fetch=lambda url: "# demo\n")
    server = FakeServer(
        response("r1", run_cmd("printf 'hello from the box\\n' > index.txt")),
        response("r2", ("run_background", {"command": "python3 -m http.server 8765 --bind 127.0.0.1",
                                           "port": 8765, "wait_s": 30})),
        response("r3", run_cmd("curl -sS http://127.0.0.1:8765/index.txt")),
        response("r4", finish(level="service", steps=[1], smoke=[
            {"command_id": 3, "setup_ids": [2], "expected_signal": "hello from the box",
             "expected_exit_code": 0, "observed_excerpt": "hello from the box"}])),
    )
    ledger = Ledger(tmp_path / "l.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    report = VerifyAgent(task, box, client=server.client(), ledger=ledger, runs_dir=tmp_path / "runs",
                         log=lambda line: None, run_id="verify-docker-test").run()
    background = report.commands[1]
    assert background.tool == "run_background" and background.exit_code == 0
    assert "port 8765 open after" in background.stdout and background.port == 8765
    assert report.commands[2].stdout.strip() == "hello from the box"
    assert report.verdict["level"] == "service" and report.verdict["agrees"]
    # The background server keeps running after its run_background call returned.
    assert box.exec("curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/", 10).stdout == "200"
