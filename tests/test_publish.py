"""pickfit publish, dry run only: every refusal, and the plan when the data is good."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pickfit import publish as publish_mod
from pickfit.cli import main as cli_main
from pickfit.publish import publish, strip_jsonc

FIXTURES = Path(__file__).resolve().parent.parent / "worker" / "test" / "fixtures" / "software"
WORKER = Path(__file__).resolve().parent.parent / "worker"
REAL_DB_ID = "3f2b8c1e-5d4a-4e6f-9a1b-2c3d4e5f6a7b"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with committed, non-fixture records and a deployable wrangler.jsonc."""
    data = tmp_path / "data" / "software"
    data.mkdir(parents=True)
    for path in FIXTURES.glob("*.json"):
        slug = path.stem.removeprefix("fixture-") + "-tool"
        text = (
            path.read_text(encoding="utf-8")
            .replace(path.stem, slug)
            .replace("https://example.invalid/fixture/", "https://github.com/someone/")
        )
        (data / f"{slug}.json").write_text(text, encoding="utf-8")
    worker = tmp_path / "worker"
    worker.mkdir()
    config = (WORKER / "wrangler.jsonc").read_text(encoding="utf-8")
    config = config.replace("00000000-0000-0000-0000-000000000000", REAL_DB_ID)
    config = config.replace('"ALLOWED_HOSTS": ""', '"ALLOWED_HOSTS": "pickfit-mcp.someone.workers.dev"')
    (worker / "wrangler.jsonc").write_text(config, encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "data")
    return tmp_path


@pytest.fixture(autouse=True)
def no_wrangler(monkeypatch: pytest.MonkeyPatch):
    """A dry run must never call wrangler; git is still allowed."""
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        assert cmd[0] == "git", f"unexpected command: {cmd}"
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(publish_mod.subprocess, "run", run)


def dry_run(repo: Path, **kwargs) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = publish(repo / "data" / "software", repo / "worker", dry_run=True, out=lines.append, **kwargs)
    return code, lines


def test_good_data_plans_the_deploy_and_writes_nothing(repo: Path) -> None:
    code, lines = dry_run(repo)
    assert code == 0, lines
    assert lines[0].startswith("publish: 5 listed entries from ")
    assert "commit " in lines[0] and "commit none" not in lines[0]
    assert lines[-1].endswith(f"would run `npx wrangler deploy` in {repo / 'worker'}")
    assert not (repo / "worker" / "src").exists()


def test_a_bad_record_refuses(repo: Path) -> None:
    path = next((repo / "data" / "software").glob("json-query-tool.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["pricing"] = {"model": "cheap", "note": None}
    path.write_text(json.dumps(record), encoding="utf-8")
    code, lines = dry_run(repo, allow_dirty=True)
    assert code == 1
    assert lines[0] == "publish: refusing to deploy, 1 problem(s):"
    assert "json-query-tool.json" in lines[1] and "pricing" in lines[1]


def test_test_fixtures_are_never_deployed(repo: Path) -> None:
    data = repo / "data" / "software"
    shutil.rmtree(data)
    shutil.copytree(FIXTURES, data)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixtures")
    code, lines = dry_run(repo)
    assert code == 1
    assert any("test fixtures must not be deployed: fixture-chat-tui" in line for line in lines)


def test_nothing_listed_refuses(repo: Path) -> None:
    for path in (repo / "data" / "software").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["status"] = "hidden"
        path.write_text(json.dumps(record), encoding="utf-8")
    code, lines = dry_run(repo, allow_dirty=True)
    assert code == 1
    assert any(line.startswith("- no listed records") for line in lines)


def test_uncommitted_data_refuses_unless_allowed(repo: Path) -> None:
    path = repo / "data" / "software" / "chat-tui-tool.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    code, lines = dry_run(repo)
    assert code == 1
    assert any("1 uncommitted file(s)" in line and "chat-tui-tool.json" in line for line in lines)
    assert dry_run(repo, allow_dirty=True)[0] == 0


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda c: c.replace(REAL_DB_ID, "00000000-0000-0000-0000-000000000000"), "database_id is still the placeholder"),
        (lambda c: c.replace('"pickfit-mcp.someone.workers.dev"', '""'), "ALLOWED_HOSTS is empty"),
    ],
)
def test_an_undeployable_wrangler_config_refuses(repo: Path, change, message: str) -> None:
    config = repo / "worker" / "wrangler.jsonc"
    config.write_text(change(config.read_text(encoding="utf-8")), encoding="utf-8")
    code, lines = dry_run(repo)
    assert code == 1
    assert any(message in line for line in lines)


def test_strip_jsonc_keeps_urls_and_comment_marks_inside_strings() -> None:
    text = '{\n  // comment\n  "a": "https://x.example/y", /* block */ "b": "/* not a comment */",\n  "c": [1, 2,],\n}'
    assert json.loads(strip_jsonc(text)) == {"a": "https://x.example/y", "b": "/* not a comment */", "c": [1, 2]}


def test_cli_dry_run(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_main(["publish", "--dry-run", "--data", str(repo / "data" / "software"), "--worker", str(repo / "worker")])
    assert code == 0
    assert "would run `npx wrangler deploy`" in capsys.readouterr().out


def test_an_env_is_checked_and_deployed_with_its_own_settings(repo: Path) -> None:
    code, lines = dry_run(repo, env="eval")
    assert code == 0, lines
    assert "publish: env eval settings: TOOLS=readonly, MATCH_MODE=model, META_DAILY_CAP_USD=3, META_TOTAL_CAP_USD=10" in lines
    assert lines[-1].endswith(f"would run `npx wrangler deploy --env eval` in {repo / 'worker'}")

    code, lines = dry_run(repo, env="eval-rules")
    assert code == 0, lines
    assert any("TOOLS=readonly, MATCH_MODE=off" in line for line in lines)

    code, lines = dry_run(repo)
    assert any(line.startswith("publish: top-level settings: TOOLS=all, MATCH_MODE=model") for line in lines)


def test_an_env_needs_its_own_d1_and_hosts(repo: Path) -> None:
    path = repo / "worker" / "wrangler.jsonc"
    config = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    config["env"]["eval"]["d1_databases"][0]["database_id"] = "00000000-0000-0000-0000-000000000000"
    config["env"]["eval"]["vars"]["ALLOWED_HOSTS"] = ""
    path.write_text(json.dumps(config), encoding="utf-8")
    git(repo, "commit", "-qam", "eval env not set up")
    code, lines = dry_run(repo, env="eval")
    assert code == 1
    assert any("wrangler.jsonc env.eval: database_id is still the placeholder" in line for line in lines)
    assert any("wrangler.jsonc env.eval: ALLOWED_HOSTS is empty" in line for line in lines)
    # The top level is still deployable.
    assert dry_run(repo)[0] == 0


def test_an_unknown_env_refuses(repo: Path) -> None:
    code, lines = dry_run(repo, env="nope")
    assert code == 1
    assert "- wrangler.jsonc: no env.nope section" in lines
