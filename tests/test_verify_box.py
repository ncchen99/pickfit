"""DockerBox without a Docker daemon: command lines, output capture, daemon start-up."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pickfit.verify import box as box_mod
from pickfit.verify.box import BOX_ENV, BoxError, BoxLimits, DockerBox, _Capture, run_captured

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32",
                                reason="the fake docker is a #! shell script, which Windows cannot execute")


SECRET_NAMES = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def test_run_args_keep_the_spike_limits():
    args = DockerBox(image="pickfit-sbx:test", build=False).run_args()
    joined = " ".join(args)
    for flag in ("--user 1000:1000", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only",
                 "--pids-limit=256", "--memory=2048m", "--memory-swap=2048m", "--cpus=2.0",
                 "--ulimit nofile=1024:1024", "--init", "--rm", "--platform linux/amd64"):
        assert flag in joined
    assert "/tmp:rw,exec,nosuid,size=256m" in args
    assert any(a.startswith("/home/sbx:rw,exec,nosuid,size=1536m") for a in args)
    assert args[-3:] == ["pickfit-sbx:test", "sleep", str(20 * 60)]


def test_run_args_pass_no_host_environment_and_no_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_API_KEY", "LLM_123_should_never_leak")
    args = DockerBox(image="img", build=False, limits=BoxLimits(lifetime_s=60)).run_args()
    env = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert {e.split("=", 1)[0] for e in env} == set(BOX_ENV)
    assert not any(word in name for e in env for name in [e.split("=", 1)[0]] for word in SECRET_NAMES)
    assert "LLM_123" not in " ".join(args)


def test_capture_keeps_head_and_tail():
    cap = _Capture(head_limit=4, tail_limit=6)
    for chunk in (b"abcdef", b"ghijkl", b"mnop"):
        cap.feed(chunk)
    assert bytes(cap.head) == b"abcd"
    assert bytes(cap.tail) == b"klmnop"
    assert cap.dropped == 6
    assert "[... 6 bytes omitted ...]" in cap.text()

    small = _Capture(head_limit=10, tail_limit=10)
    small.feed(b"hello")
    assert small.text() == "hello" and small.dropped == 0


def test_run_captured_bounds_large_output():
    code, out, err, timed_out, truncated = run_captured(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000); sys.stderr.write('oops')"], 30,
        head=1000, tail=2000)
    assert code == 0 and not timed_out and truncated
    assert out.startswith("x" * 1000) and out.endswith("x" * 2000) and "omitted" in out
    assert err == "oops"


def test_run_captured_host_timeout():
    code, _, _, timed_out, _ = run_captured([sys.executable, "-c", "import time; time.sleep(30)"], 0.5)
    assert timed_out and code != 0


@pytest.fixture
def fake_docker(tmp_path: Path) -> Path:
    """A `docker` stand-in that records its arguments and exits with $FAKE_EXIT."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "docker"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.stdin.read() if sys.argv[1:2] == ['exec'] and '-i' in sys.argv else None\n"
        "print('unreachable 169.254.0.0/16' if sys.argv[1:4] == ['exec', '-u', '0'] else 'ok')\n"
        "sys.exit(int(os.environ.get('FAKE_EXIT', '0')))\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _calls(fake: Path) -> list[list[str]]:
    return [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


@POSIX_ONLY
def test_exec_kills_inside_the_box_and_clamps_timeout(fake_docker: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(box_mod, "ensure_docker", lambda **kw: None)
    box = DockerBox(image="img", build=False, docker=str(fake_docker), name="pf-test",
                    limits=BoxLimits(max_command_s=100))
    box.start()
    result = box.exec("echo hi", 999)
    assert result.ok
    last = _calls(fake_docker)[-1]
    assert last == ["exec", "-w", "/home/sbx/work", "pf-test", "timeout", "-s", "KILL", "100",
                    "bash", "-c", "echo hi"]
    box.write_file("dir/a.txt", "data")
    write = _calls(fake_docker)[-1]
    assert write[:2] == ["exec", "-i"] and write[-1] == "dir/a.txt"  # the path is an argument, not code
    box.set_network(False)
    assert _calls(fake_docker)[-1] == ["network", "disconnect", "bridge", "pf-test"]
    assert box.network_enabled is False
    box.set_network(True)
    assert _calls(fake_docker)[-2] == ["network", "connect", "bridge", "pf-test"]
    assert _calls(fake_docker)[-1][:5] == ["exec", "-u", "0", "--privileged", "pf-test"]  # routes again
    box.close()
    assert _calls(fake_docker)[-1] == ["rm", "-f", "pf-test"]
    with pytest.raises(BoxError):
        box.exec("echo again", 5)


@POSIX_ONLY
def test_start_blocks_cloud_metadata_as_root(fake_docker: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(box_mod, "ensure_docker", lambda **kw: None)
    box = DockerBox(image="img", build=False, docker=str(fake_docker), name="pf-meta")
    box.start()
    root = [c for c in _calls(fake_docker) if c[:3] == ["exec", "-u", "0"]]
    assert len(root) == 1 and "ip route replace unreachable 169.254.0.0/16" in root[0][-1]
    # Model commands never run as root.
    box.exec("id", 5)
    assert _calls(fake_docker)[-1][:2] == ["exec", "-w"]


@POSIX_ONLY
def test_start_fails_closed_when_metadata_cannot_be_blocked(fake_docker: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(box_mod, "ensure_docker", lambda **kw: None)
    box = DockerBox(image="img", build=False, docker=str(fake_docker), name="pf-meta")
    monkeypatch.setattr(box, "_root", lambda script, timeout_s=30: subprocess.CompletedProcess(
        [], 2, "", "ip: command not found"))
    with pytest.raises(BoxError, match="could not block cloud metadata"):
        box.start()
    assert _calls(fake_docker)[-1] == ["rm", "-f", "pf-meta"] and not box.started


@POSIX_ONLY
def test_exec_marks_in_box_kill_as_timeout(fake_docker: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(box_mod, "ensure_docker", lambda **kw: None)
    box = DockerBox(image="img", build=False, docker=str(fake_docker))
    box.start()
    box.started = True
    monkeypatch.setenv("FAKE_EXIT", "137")
    clock = iter([0.0, 5.0])
    monkeypatch.setattr(box_mod.time, "monotonic", lambda: next(clock))
    result = box.exec("sleep 99", 5)
    assert result.timed_out and result.exit_code == 137 and not result.ok


def test_ensure_docker_opens_the_desktop_app_and_waits(monkeypatch: pytest.MonkeyPatch):
    states = iter([False, False, True])
    opened: list[list[str]] = []
    monkeypatch.setattr(box_mod.shutil, "which", lambda name: "/usr/local/bin/docker")
    monkeypatch.setattr(box_mod, "_docker_ok", lambda docker="docker": next(states))
    monkeypatch.setattr(box_mod, "_desktop_app", lambda docker="docker": "OrbStack")
    monkeypatch.setattr(box_mod.sys, "platform", "darwin")
    monkeypatch.setattr(box_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(box_mod.subprocess, "run", lambda args, **kw: opened.append(args))
    box_mod.ensure_docker(log=lambda line: None)
    assert opened == [["open", "-a", "OrbStack"]]


def test_ensure_docker_gives_up(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(box_mod.shutil, "which", lambda name: "/usr/local/bin/docker")
    monkeypatch.setattr(box_mod, "_docker_ok", lambda docker="docker": False)
    monkeypatch.setattr(box_mod.sys, "platform", "linux")
    with pytest.raises(BoxError, match="not running"):
        box_mod.ensure_docker(log=lambda line: None)


def test_image_tag_follows_the_dockerfile(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("FROM x\n")
    b.write_text("FROM y\n")
    assert box_mod.sandbox_image_tag(a) != box_mod.sandbox_image_tag(b)
    assert box_mod.sandbox_image_tag(a).startswith("pickfit-sbx:")
