"""deploy/watch/send_secrets.py with fake config files and a fake ssh: values go only to the remote's stdin."""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "watch" / "send_secrets.py"
spec = importlib.util.spec_from_file_location("send_secrets", SCRIPT)
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

SECRETS = {"ANTHROPIC_API_KEY": "sk-fake-anthropic", "CLOUDFLARE_API_TOKEN": "cf-fake-token",
           "MODAL_TOKEN_ID": "ak-fake", "MODAL_TOKEN_SECRET": "as-fake-secret", "GH_PUSH_TOKEN": "gh-fake-push",
           "SCW_SECRET_KEY": "scw-fake-secret", "AWS_SECRET_ACCESS_KEY": "aws-fake-secret"}


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    for name in ("ANTHROPIC_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "CLOUDFLARE_API_TOKEN",
                 "CLOUDFLARE_ACCOUNT_ID", "GH_PUSH_TOKEN", "GH_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "dotenv"
    env.write_text("export ANTHROPIC_API_KEY='sk-fake-anthropic'\nCLOUDFLARE_ACCOUNT_ID=acct123 # mine\n"
                   "BASETEN_API_KEY=not-wanted\n")
    modal = tmp_path / "modal.toml"
    modal.write_text('[old]\ntoken_id = "ak-old"\ntoken_secret = "as-old"\n\n'
                     '[pickfit-local]\ntoken_id = "ak-fake"\ntoken_secret = "as-fake-secret"\nactive = true\n')
    scw = tmp_path / "scw.yaml"
    scw.write_text("access_key: SCWFAKE\nsecret_key: scw-fake-secret\ndefault_organization_id: org-1\n"
                   "default_project_id: proj-1\ndefault_zone: fr-par-1\nprofiles:\n  other:\n    access_key: NO\n")
    runs = tmp_path / "runs"
    (runs / "watch" / "jobs").mkdir(parents=True)
    (runs / "watch" / "jobs" / "sub_1.json").write_text("{}")
    (runs / "web").mkdir()
    (runs / "web" / "visits.jsonl").write_text('{"site": "example.com"}\n')
    (runs / "verify").mkdir()  # not sent
    hosts = tmp_path / "mac-hosts"  # none: no Mac hosts question
    hosts.mkdir()
    return {"env": env, "modal": modal, "scw": scw, "runs": runs, "hosts": hosts, "aws": tmp_path / "no-aws-cli"}


def argv(files: dict[str, Path], *extra: str) -> list[str]:
    return ["root@203.0.113.5", "--env-file", str(files["env"]), "--modal-config", str(files["modal"]),
            "--scw-config", str(files["scw"]), "--runs", str(files["runs"]), "--mac-hosts", str(files["hosts"]),
            "--aws", str(files["aws"]), *extra]


class Remote:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[tuple[list[str], bytes]] = []
        self.fail = fail

    def __call__(self, cmd: list[str], *, input: bytes, capture_output: bool) -> Any:  # noqa: A002
        self.calls.append((cmd, input))
        failed = self.fail is not None and self.fail in cmd[-1]
        return SimpleNamespace(returncode=1 if failed else 0, stderr=b"no such file" if failed else b"")


def answers(*replies: str):
    queue = list(replies)
    return lambda prompt: queue.pop(0)


def test_everything_reaches_the_remote_on_stdin_and_nowhere_else(files, capsys) -> None:
    remote = Remote()
    ask = answers("cf-fake-token", "gh-fake-push", "aws-fake-secret")
    confirm = answers("AKIAFAKE", "", "y")
    assert ss.main(argv(files), ask=ask, confirm=confirm, run=remote) == 0
    [secrets, state, main, start] = remote.calls
    text = secrets[1].decode()
    for value in SECRETS.values():
        assert value in text  # on stdin
        assert all(value not in part for cmd, _ in remote.calls for part in cmd)  # never in a command line
    out = capsys.readouterr().out
    assert not any(value in out for value in SECRETS.values())
    assert "GH_TOKEN=gh-fake-push" in text and "CLOUDFLARE_ACCOUNT_ID=acct123" in text
    assert "SCW_ACCESS_KEY=SCWFAKE" in text and "SCW_DEFAULT_PROJECT_ID=proj-1" in text
    assert "BASETEN" not in text and "ak-old" not in text
    assert secrets[0][-1] == "install -m 640 -o root -g pickfit /dev/stdin /etc/pickfit/watch.env"
    with tarfile.open(fileobj=io.BytesIO(state[1]), mode="r:gz") as tar:
        assert sorted(tar.getnames()) == ["watch/jobs", "watch/jobs/sub_1.json", "web/visits.jsonl"]
    assert "cat-file -e origin/main:pickfit/lanes.py" in main[0][-1]
    assert start[0][-1].startswith("systemctl enable --now pickfit-watch")


def test_skipping_the_optional_parts(files) -> None:
    remote = Remote()
    assert ss.main(argv(files, "--no-start"), ask=answers("cf-fake-token", "gh-fake-push"),
                   confirm=answers("", "", "n"), run=remote) == 0
    text = remote.calls[0][1].decode()
    assert "AWS_" not in text and "SCW_ACCESS_KEY" not in text and "SCW_DEFAULT_ZONE=fr-par-1" in text
    assert len(remote.calls) == 3  # no start


def test_a_missing_required_value_sends_nothing(files, capsys) -> None:
    files["env"].write_text("")
    remote = Remote()
    assert ss.main(argv(files), ask=answers("", "", ""), confirm=answers("", "", "", "n"), run=remote) == 1
    assert remote.calls == [] and "missing: ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_main_without_the_watch_code_does_not_start(files, capsys) -> None:
    remote = Remote(fail="cat-file")
    assert ss.main(argv(files), ask=answers("cf-fake-token", "gh-fake-push"), confirm=answers("", "", "n"),
                   run=remote) == 1
    assert len(remote.calls) == 3 and "Merge the watch work into main" in capsys.readouterr().out


def test_dry_run_names_but_never_shows_or_sends(files, capsys) -> None:
    remote = Remote()
    assert ss.main(argv(files, "--dry-run"), ask=answers(), confirm=answers(), run=remote) == 0
    out = capsys.readouterr().out
    assert remote.calls == [] and "ANTHROPIC_API_KEY" in out and "would run on root@203.0.113.5" in out
    assert not any(value in out for value in SECRETS.values())


def test_a_value_with_a_line_break_is_refused() -> None:
    with pytest.raises(SystemExit):
        ss.env_text({"X": "a\nB=evil"})


def fake_aws(tmp_path: Path, payload: str, code: int = 0) -> Path:
    cli = tmp_path / "aws"
    cli.write_text(f"#!/bin/sh\ncat <<'EOF'\n{payload}\nEOF\nexit {code}\n")
    cli.chmod(0o755)
    return cli


def test_this_macs_aws_sign_in_is_offered_when_no_key_is_typed(files, tmp_path) -> None:
    files["aws"] = fake_aws(tmp_path, '{"Version": 1, "AccessKeyId": "ASIAFAKE", "SecretAccessKey": "aws-temp-secret", '
                                      '"SessionToken": "aws-temp-token", "Expiration": "2026-11-19T06:00:00Z"}')
    remote = Remote()
    assert ss.main(argv(files, "--no-start"), ask=answers("cf-fake-token", "gh-fake-push"),
                   confirm=answers("", "y", "", "n"), run=remote) == 0
    [secrets, *_] = remote.calls
    text = secrets[1].decode()
    assert "AWS_ACCESS_KEY_ID=ASIAFAKE" in text and "AWS_SESSION_TOKEN=aws-temp-token" in text
    assert all("aws-temp" not in part for cmd, _ in remote.calls for part in cmd)


def test_the_mac_hosts_go_with_their_key_re_pointed(files, tmp_path) -> None:
    key = tmp_path / "keys" / "scaleway-mac"
    key.parent.mkdir()
    key.write_text("PRIVATE KEY FAKE\n")
    (files["hosts"] / "scw1.json").write_text(json.dumps({"name": "scw1", "provider": "scaleway", "key": str(key),
                                                          "server_id": "srv-1"}))
    remote = Remote()
    assert ss.main(argv(files, "--no-start"), ask=answers("cf-fake-token", "gh-fake-push"),
                   confirm=answers("", "", "n", "y"), run=remote) == 0
    hosts = next(data for cmd, data in remote.calls if "mac-hosts" in cmd[-1])
    with tarfile.open(fileobj=io.BytesIO(hosts), mode="r:gz") as tar:
        assert sorted(tar.getnames()) == ["mac-hosts/scw1.json", "ssh/scaleway-mac"]
        host = json.loads(tar.extractfile("mac-hosts/scw1.json").read())
        assert tar.getmember("ssh/scaleway-mac").mode == 0o600
    assert host["key"] == "/var/lib/pickfit/.pickfit/ssh/scaleway-mac" and host["server_id"] == "srv-1"
    assert all("PRIVATE KEY" not in part for cmd, _ in remote.calls for part in cmd)


def test_watchs_own_scaleway_key_is_taken_in_place_of_this_macs(files) -> None:
    remote = Remote()
    assert ss.main(argv(files, "--no-start"), ask=answers("cf-fake-token", "gh-fake-push", "scw-app-secret"),
                   confirm=answers("", "SCWAPPKEY"), run=remote) == 0
    text = remote.calls[0][1].decode()
    assert "SCW_ACCESS_KEY=SCWAPPKEY" in text and "SCW_SECRET_KEY=scw-app-secret" in text
    assert "SCWFAKE" not in text and "scw-fake-secret" not in text  # not this Mac's own key
    assert "SCW_DEFAULT_PROJECT_ID=proj-1" in text and "SCW_DEFAULT_ORGANIZATION_ID=org-1" in text
