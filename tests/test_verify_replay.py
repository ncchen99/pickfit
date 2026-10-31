"""Replay in a fresh box: steps online, smoke tests offline, online retry for the rest."""

from __future__ import annotations

from typing import Any

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.box import ExecResult
from pickfit.verify.replay import Replayer, plan_from
from pickfit.verify.task import VerifyTask
from pickfit.verify.verdict import log_verdict
from verify_fakes import FakeBox


class NetBox(FakeBox):
    """A FakeBox whose commands containing an `online_only` needle fail with the network off."""

    def __init__(self, script: dict[str, tuple[int, str, str]], online_only: tuple[str, ...] = ()) -> None:
        super().__init__(script)
        self.online_only = online_only
        self.network_log: list[bool] = []

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self.network_log.append(self.network_enabled)
        if not self.network_enabled and any(n in command for n in self.online_only):
            self.ran.append((command, timeout_s))
            return ExecResult(command, 6, "", "curl: (6) Could not resolve host", 0.1)
        return super().exec(command, timeout_s, cwd=cwd)


def rec(cid: int, command: str, code: int, out: str = "", tool: str = "run_command", **kw: Any) -> CommandRecord:
    return CommandRecord(turn=cid, tool=tool, command=command, exit_code=code, seconds=0.1, stdout=out,
                         command_id=cid, **kw)


LOG = [
    rec(1, "uv tool install graphtty", 0, "Installed 1 executable: graphtty"),
    rec(2, "graphtty --version", 0, "graphtty 0.4.1"),
    rec(3, "cat > graph.json <<'EOF'\n{\"nodes\": [\"a\", \"b\"]}\nEOF", 0, ""),
    rec(4, "graphtty graph.json", 0, "a ──▶ b"),
    rec(5, "graphtty --theme-url https://example.invalid/t.json graph.json", 0, "a ══▶ b"),
]

TASK = VerifyTask(slug="graphtty", repo_url="https://github.com/uipath/graphtty", readme="# graphtty\n",
                  extraction=None, files={"sample/notes.txt": "x"})  # type: ignore[arg-type]


def verdict(tests: list[dict[str, Any]]):
    finish = FinishArgs.model_validate({
        "level": "function", "steps": [{"command_id": 1, "purpose": "install"}],
        "smoke_tests": [{"setup_ids": [], "expected_exit_code": 0, **t} for t in tests]})
    return log_verdict(finish, LOG)


def box_for_log(**kw: Any) -> NetBox:
    return NetBox({r.command: (r.exit_code or 0, r.stdout, "") for r in reversed(LOG)}, **kw)


def test_plan_takes_the_cited_steps_and_passing_checks_once():
    v = verdict([{"command_id": 2, "expected_signal": "0.4.1"},
                 {"command_id": 4, "setup_ids": [3], "expected_signal": "a ──▶ b"},
                 {"command_id": 4, "setup_ids": [3, 1], "expected_signal": "nope"}])  # fails: no signal
    plan = plan_from(v, LOG)
    assert [s.command_id for s in plan.steps] == [1]
    assert [s.command_id for s in plan.setups] == [3]  # step 1 is not run again as setup
    assert [(c.run.command_id, c.kind) for c in plan.checks] == [(2, "version"), (4, "example")]


def test_steps_online_then_checks_offline():
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"},
                              {"command_id": 4, "setup_ids": [3], "expected_signal": "──▶"}]), LOG)
    box = box_for_log()
    lines: list[str] = []
    result = Replayer(box, log=lines.append).run(plan, TASK)
    assert result.passed and result.level == "function" and result.offline
    assert [c for c, _ in box.ran] == ["uv tool install graphtty", LOG[2].command, "graphtty --version",
                                       "graphtty graph.json"]
    assert box.network_log == [True, True, False, False]
    assert box.network_enabled  # left on for whoever uses the box next
    assert box.files["README.md"] == b"# graphtty\n" and box.files["sample/notes.txt"] == b"x"
    assert all(c.offline and c.run.network is False for c in result.checks)
    assert "  replay [4] graphtty graph.json → exit 0 · 0.1s · offline" in lines


def test_a_check_that_needs_the_network_is_retried_online():
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"},
                              {"command_id": 5, "setup_ids": [3], "expected_signal": "══▶"}]), LOG)
    result = Replayer(box_for_log(online_only=("example.invalid",)), log=lambda s: None).run(plan, TASK)
    assert result.passed and result.level == "function" and not result.offline
    online = result.checks[1]
    assert online.passed and not online.offline and online.run.network is True
    assert online.offline_problems == ["expected exit 0, log shows 6", "expected_signal not in the output: '══▶'"]


def test_a_failing_step_stops_the_replay():
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"}]), LOG)
    box = NetBox({"uv tool install": (2, "", "error: network unreachable")})
    result = Replayer(box, log=lambda s: None).run(plan, TASK)
    assert not result.passed and result.level is None
    assert result.error == "step 1 exited 2: uv tool install graphtty"
    assert len(box.ran) == 1


def test_checks_that_no_longer_pass_lower_the_level():
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"},
                              {"command_id": 4, "setup_ids": [3], "expected_signal": "──▶"}]), LOG)
    box = box_for_log()
    box.script["graphtty graph.json"] = (1, "", "KeyError: 'edges'")
    result = Replayer(box, log=lambda s: None).run(plan, TASK)
    assert result.passed and result.level == "install"
    assert result.checks[1].problems[0] == "expected exit 0, log shows 1"


def test_background_setup_is_restarted_with_the_same_script():
    log = [rec(1, "pipx install tinyserve", 0, "installed"),
           rec(2, "tinyserve --port 8080", 0, "pid 9\nport 8080 open after 1s", tool="run_background",
               port=8080, wait_s=30),
           rec(3, "curl -s localhost:8080/health", 0, '{"ok":true}')]
    finish = FinishArgs.model_validate({
        "level": "service", "steps": [{"command_id": 1}],
        "smoke_tests": [{"command_id": 3, "setup_ids": [2], "expected_signal": '"ok":true'}]})
    plan = plan_from(log_verdict(finish, log), log)
    box = NetBox({"setsid nohup bash -c 'tinyserve --port 8080'": (0, "pid 3\nport 8080 open after 1s", ""),
                  "curl -s localhost:8080/health": (0, '{"ok":true}', ""),
                  "pipx install": (0, "installed", "")})
    result = Replayer(box, log=lambda s: None).run(plan, TASK)
    assert result.passed and result.level == "service" and result.offline
    script, timeout = box.ran[1]
    assert "/dev/tcp/127.0.0.1/8080" in script and "replay-2.log" in script and timeout == 45


def test_rerun_timeouts_follow_the_recorded_time():
    from pickfit.verify.replay import replay_timeout

    assert replay_timeout(0.5) == 60 and replay_timeout(40) == 190 and replay_timeout(300) == 600
    assert replay_timeout(None) == 600
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"}]), LOG)
    box = box_for_log()
    Replayer(box, log=lambda s: None).run(plan, TASK)
    assert [t for _, t in box.ran] == [60, 60]  # LOG records 0.1 s for each


def test_steps_cited_as_setup_are_not_run_twice():
    plan = plan_from(verdict([{"command_id": 4, "setup_ids": [1, 3], "expected_signal": "──▶"}]), LOG)
    assert [s.command_id for s in plan.setups] == [3]
    assert plan.checks[0].setup_ids == (3,)


def test_a_setup_that_fails_fails_only_the_checks_that_need_it():
    plan = plan_from(verdict([{"command_id": 2, "expected_signal": "0.4.1"},
                              {"command_id": 4, "setup_ids": [3], "expected_signal": "──▶"}]), LOG)
    box = box_for_log()
    box.script = {"cat > graph.json": (1, "", "disk full"), **box.script}
    result = Replayer(box, log=lambda s: None).run(plan, TASK)
    assert result.passed and result.level == "install"  # the version check still holds
    graph = result.checks[1]
    assert not graph.passed and graph.run is None and graph.problems[0].startswith("setup 3 exited 1")
    assert "graphtty graph.json" not in [c for c, _ in box.ran]  # not run without its input


def test_failed_feature_checks_are_rerun_once_online_after_their_setup():
    log = [*LOG, rec(6, "graphtty graph.json --svg out.svg", 1, "", stderr="unknown flag --svg")]
    finish = FinishArgs.model_validate({
        "level": "function", "steps": [{"command_id": 1, "purpose": "install"}],
        "smoke_tests": [{"command_id": 2, "setup_ids": [], "expected_signal": "0.4.1", "expected_exit_code": 0},
                        {"command_id": 6, "setup_ids": [3], "expected_signal": "<svg", "expected_exit_code": 0}]})
    plan = plan_from(log_verdict(finish, log), log, rerun_failed=[6])
    assert [c.run.command_id for c in plan.failed] == [6] and [s.command_id for s in plan.failed_setups] == [3]
    box = NetBox({"--svg": (1, "", "unknown flag --svg"), **box_for_log().script})
    result = Replayer(box, log=lambda s: None).run(plan, TASK)
    assert result.level == "install" and [(f.command_id, f.reproduced) for f in result.failed] == [(6, True)]
    assert [c for c, _ in box.ran][-2:] == [LOG[2].command, "graphtty graph.json --svg out.svg"]
    assert box.network_log[-1] is True  # online, after the offline checks
