"""pickfit maintenance (D3, F3, F4, 11/20): upkeep in a worktree of its own, pushed to main or to a review branch."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from pickfit import maintenance
from pickfit.ledger import TAIPEI

NOW = datetime(2026, 11, 22, 4, 30, tzinfo=TAIPEI)


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, capture_output=True)
    (seed / "data" / "software").mkdir(parents=True)
    (seed / "data" / "software" / "a.json").write_text('{"slug": "a"}\n')
    sh(seed, "add", "-A")
    sh(seed, "commit", "-qm", "seed")
    sh(seed, "push", "-q", "origin", "HEAD:main")
    watch = tmp_path / "pickfit"
    subprocess.run(["git", "clone", "-q", str(origin), str(watch)], check=True, capture_output=True)
    for repo in (watch,):
        sh(repo, "config", "user.name", "pickfit watch")
        sh(repo, "config", "user.email", "watch@pickfit.app")
    return {"origin": origin, "seed": seed, "watch": watch, "maint": tmp_path / "maint"}


def writer(repos: dict[str, Path], calls: list[list[str]], text: str | None = '{"slug": "a", "security": 2}\n'):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        if text is not None and argv[0] in ("security", "outcomes"):
            (repos["maint"] / "data" / "software" / "a.json").write_text(text)
        return 0
    return run


def origin_log(repos: dict[str, Path], ref: str = "main") -> list[str]:
    sh(repos["seed"], "fetch", "-q", "origin")
    return sh(repos["seed"], "log", "--format=%s", f"origin/{ref}").splitlines()


def test_security_rescans_in_its_own_worktree_and_pushes_to_main(repos: dict[str, Path]) -> None:
    calls: list[list[str]] = []
    watch_head = sh(repos["watch"], "rev-parse", "HEAD")
    out = maintenance.task_security(repos["watch"], repos["maint"], writer(repos, calls), stale_days=7, now=NOW,
                                    push=True)
    data = str(repos["maint"] / "data" / "software")
    assert calls == [["security", "--stale-days", "7", "--write", "--data-dir", data],
                     ["score", "--refresh", "--data-dir", data]]
    assert out.committed and out.pushed == out.committed
    assert origin_log(repos)[0].startswith("Weekly sec.v2 rescan")
    # The watch's checkout is untouched: same HEAD, nothing changed in its tree.
    assert sh(repos["watch"], "rev-parse", "HEAD") == watch_head and not sh(repos["watch"], "status", "--short")


def test_nothing_changed_commits_and_pushes_nothing(repos: dict[str, Path]) -> None:
    out = maintenance.task_outcomes(repos["watch"], repos["maint"], writer(repos, [], text=None), now=NOW, push=True)
    assert (out.committed, out.pushed) == (None, None)
    assert origin_log(repos) == ["seed"]


def test_a_push_the_watch_beat_is_rebased_and_sent_again(repos: dict[str, Path]) -> None:
    def run(argv: list[str]) -> int:
        (repos["maint"] / "data" / "software" / "a.json").write_text('{"slug": "a", "outcomes": 1}\n')
        # Meanwhile the watch lands a new record and pushes it first.
        (repos["seed"] / "data" / "software" / "b.json").write_text('{"slug": "b"}\n')
        sh(repos["seed"], "add", "-A")
        sh(repos["seed"], "commit", "-qm", "Add b")
        sh(repos["seed"], "push", "-q", "origin", "HEAD:main")
        return 0

    out = maintenance.task_outcomes(repos["watch"], repos["maint"], run, now=NOW, push=True)
    assert out.pushed
    log = origin_log(repos)
    assert log[0].startswith("Sync usage outcomes") and log[1:] == ["Add b", "seed"]


def test_the_worktree_starts_clean_from_origin_main_every_run(repos: dict[str, Path]) -> None:
    maintenance.task_security(repos["watch"], repos["maint"], writer(repos, []), stale_days=7, now=NOW, push=False)
    (repos["maint"] / "data" / "software" / "stray.json").write_text("{}")  # a crashed run's leftovers
    out = maintenance.task_outcomes(repos["watch"], repos["maint"], writer(repos, [], text=None), now=NOW, push=False)
    assert out.committed is None and not (repos["maint"] / "data" / "software" / "stray.json").exists()
    assert sh(repos["maint"], "rev-parse", "HEAD") == sh(repos["watch"], "rev-parse", "origin/main")


def test_reverify_commits_to_a_review_branch_and_never_to_main(repos: dict[str, Path]) -> None:
    def run(argv: list[str]) -> int:
        assert argv[:3] == ["reverify", "--limit", "2"]
        (repos["maint"] / "data" / "software" / "a.json").write_text('{"slug": "a", "steps": "fixed"}\n')
        sh(repos["maint"], "commit", "-qam", "Reverify a: steps from a report")  # Reverifier commits itself
        return 0

    out = maintenance.task_reverify(repos["watch"], repos["maint"], run, limit=2, now=NOW, push=True)
    assert out.pushed == "maint/reverify-20261122" and "never pushed to main" in out.note
    assert origin_log(repos) == ["seed"]  # main unchanged
    assert origin_log(repos, "maint/reverify-20261122")[0] == "Reverify a: steps from a report"


def test_a_reverify_that_changed_nothing_pushes_no_branch(repos: dict[str, Path]) -> None:
    out = maintenance.task_reverify(repos["watch"], repos["maint"], lambda argv: 0, limit=3, now=NOW, push=True)
    assert out.pushed is None and out.committed is None


def test_the_command_runs_a_task_and_reports_it(repos: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    args = maintenance._argv(["security", "--repo", str(repos["watch"]), "--maint", str(repos["maint"]),
                              "--no-push"])
    assert maintenance.main(args, run=writer(repos, []), now=NOW) == 0
    assert '"task": "security"' in capsys.readouterr().out
    from pickfit.cli import main as cli

    with pytest.raises(SystemExit) as exit_:
        cli(["maintenance", "--help"])
    assert exit_.value.code == 0


DEPLOY = Path(__file__).resolve().parent.parent / "deploy" / "watch"
UNITS = {"pickfit-security-weekly": "security", "pickfit-outcomes": "outcomes", "pickfit-reverify": "reverify"}


@pytest.mark.parametrize(("unit", "task"), UNITS.items())
def test_each_timer_runs_its_maintenance_task_as_the_pickfit_user(unit: str, task: str) -> None:
    service = (DEPLOY / f"{unit}.service").read_text()
    assert f"pickfit maintenance {task}" in service and "User=pickfit" in service and "Type=oneshot" in service
    assert "EnvironmentFile=/etc/pickfit/watch.env" in service
    timer = (DEPLOY / f"{unit}.timer").read_text()
    assert "OnCalendar=" in timer and "Persistent=true" in timer and "WantedBy=timers.target" in timer


def test_bootstrap_installs_the_maintenance_units_and_enables_none() -> None:
    bootstrap = (DEPLOY / "bootstrap.sh").read_text()
    for unit in UNITS:
        assert f"{unit}.service" in bootstrap and f"{unit}.timer" in bootstrap
    assert "systemctl enable" not in bootstrap  # a person enables them (the README says how)
    readme = (DEPLOY / "README.md").read_text()
    assert all(f"{unit}.timer" in readme for unit in UNITS) and "不進 main" in readme
