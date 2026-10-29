"""Whose failure it is, whether it repeats, and commands that only work around the box."""

from __future__ import annotations

import pytest

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.failure import (
    WRITTEN_REASONS,
    box_reason,
    cited_workarounds,
    failure_limit,
    failure_plan,
    output_limit,
    sandbox_only,
)
from pickfit.verify.verdict import log_verdict


@pytest.mark.parametrize(("output", "reason"), [
    ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
     "needs_container"),
    ("bash: line 1: docker: command not found", "needs_container"),
    ("error: neither docker nor podman found", "needs_container"),
    ("Building wheel for tokenizers (pyproject.toml) ... error\n  error: can't find Rust compiler", "needs_toolchain"),
    ("bash: line 1: cargo: command not found", "needs_toolchain"),
    ("bash: go: command not found", "needs_toolchain"),
    ("error: command 'gcc' failed: No such file or directory", "needs_toolchain"),
    ("evdev/input.c:10:10: fatal error: linux/input.h: No such file or directory", "needs_root"),
    ("npm ERR! Error: EACCES: permission denied, mkdir '/usr/lib/node_modules/foo'", "needs_root"),
    ("System has not been booted with systemd as init system (PID 1). Can't operate.", "needs_root"),
    ("ImportError: libcuda.so.1: cannot open shared object file: No such file or directory", "needs_gpu"),
    ("RuntimeError: CUDA driver version is insufficient for CUDA runtime version", "needs_gpu"),
    ("FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory", "needs_more_resources"),
    ("OSError: [Errno 28] No space left on device", "needs_more_resources"),
])
def test_box_limits_in_a_failing_commands_output(output: str, reason: str):
    assert output_limit(output, 1, False) == reason


def test_a_kill_or_a_timeout_is_the_boxs_limit():
    assert output_limit("", 137, False) == "needs_more_resources"
    assert output_limit("", None, True) == "needs_more_resources"


@pytest.mark.parametrize("output", [
    "ModuleNotFoundError: No module named 'docker'",
    "ImportError: No module named nvidia",
    "KeyError: 'HOME'",
    "Let's go! config.toml not found",
    "error[E0425]: cannot find value `x` in this scope",
])
def test_the_tools_own_errors_are_not_the_boxs(output: str):
    assert output_limit(output, 1, False) is None


@pytest.mark.parametrize(("text", "reason"), [
    # The blocking errors of failed runs before this check existed (2026-10-29).
    ("No container engine in box (neither docker nor podman) so packaging/linux/run_oci.sh cannot run",
     "needs_container"),
    ("Editable install failed: evdev needs kernel headers (linux/input.h missing, no root to install "
     "linux-headers)", "needs_root"),
    ("scripts/install.sh requires Rust 1.91+ (absent, forbidden to install)", "needs_toolchain"),
    ("the hatch web-build step `npm run build` aborts in Node/V8 (exit 134)", "needs_more_resources"),
    ("the build needs root access to write /etc/udev", "needs_root"),
    ("requires CUDA 12 and an NVIDIA driver", "needs_gpu"),
])
def test_box_limits_in_the_agents_words(text: str, reason: str):
    assert box_reason(text) == reason


@pytest.mark.parametrize("text", [
    "PyPI wheel ships no code (RECORD has only dist-info), so `tool --help` fails with ModuleNotFoundError",
    "`tool --help` crashes: ModuleNotFoundError: No module named 'docker'",
    "ImportError: No module named nvidia when importing tool.gpu",
    "Release v2.0 asset foo-linux-amd64.tar.gz returns 404; README also mentions `apt install foo`",
    "config.toml not found at the project root",
    None,
])
def test_mentions_are_not_needs(text: str | None):
    assert box_reason(text) is None


def rec(cid: int, command: str, code: int, out: str = "", seconds: float = 1.0, purpose: str | None = None,
        timed_out: bool = False) -> CommandRecord:
    return CommandRecord(turn=cid, tool="run_command", command=command, exit_code=code, seconds=seconds,
                         stdout=out, stderr="", timed_out=timed_out, command_id=cid, purpose=purpose)


def test_the_failing_commands_output_outweighs_the_agents_words():
    words = "foo --help crashes with KeyError 'HOME'; the README's docker route was not tried (no docker in box)"
    assert box_reason(words) == "needs_container"  # a side note, read alone
    crash = rec(4, "foo --help", 1, "KeyError: 'HOME'")
    assert failure_limit(words, crash, check_passed=False) is None
    # No failing command: the words decide, unless a check passed (the tool ran).
    assert failure_limit("needs Rust 1.91+, absent here", None, check_passed=False) == "needs_toolchain"
    assert failure_limit("needs Rust 1.91+, absent here", None, check_passed=True) is None


def test_written_reasons_leave_out_the_uninformative_ones():
    assert {"needs_toolchain", "needs_root", "needs_container", "needs_more_resources", "needs_gpu",
            "gui_only"} <= WRITTEN_REASONS
    assert not {"not_run", "budget_exceeded", "other"} & WRITTEN_REASONS


@pytest.mark.parametrize(("command", "purpose"), [
    ("printf '#!/bin/bash\\nexec /bin/nvidia-smi \"$@\"\\n' > ~/.local/bin/nvidia-smi && chmod +x "
     "~/.local/bin/nvidia-smi", "Install PCI workaround cleanly"),
    ("ln -sf /bin/true $HOME/.local/bin/docker", None),
    ("ln -s -f /bin/true ~/.local/bin/sudo", None),
    ("cat > /home/sbx/.local/bin/sudo <<'EOF'\n#!/bin/sh\nexec \"$@\"\nEOF", None),
    ("cp /bin/true ~/.local/bin/nvidia-smi", None),
    ("install -m755 /dev/stdin ~/.local/bin/nvidia-smi <<'EOF'\n#!/bin/sh\necho GPU0\nEOF", None),
    ("curl -fsSL -o ~/.local/bin/nvidia-smi https://example.invalid/fake", None),
    ("mkdir -p ~/.cargo/bin && printf '#!/bin/sh\\necho GPU0' > ~/.cargo/bin/nvidia-smi", None),
    ("mkdir -p ~/go/bin && ln -sf /bin/true ~/go/bin/docker", None),
    ("export BERTH_PCI=0", "sandbox-only PCI workaround so the daemon can start"),
    ("export X=1", "fake nvidia-smi output for gVisor"),
])
def test_commands_that_work_around_the_box(command: str, purpose: str | None):
    assert sandbox_only(command, purpose)


@pytest.mark.parametrize(("command", "purpose"), [
    ("curl -fL -o ~/.local/bin/berth https://example.invalid/berth-linux-amd64 && chmod +x ~/.local/bin/berth",
     "Download and install berth binary"),
    ("install -Dm755 berth-linux-amd64 ~/.local/bin/berth", "install into the box's ~/.local/bin"),
    ("ln -s ~/.local/share/ggrun/ggrun ~/.local/bin/ggrun", "put ggrun on PATH"),
    ("echo 'export PATH=$HOME/.cargo/bin:$PATH' >> ~/.bashrc", None),
    ("tar xzf st.tgz -C /tmp/st && ln -sf /tmp/st/systemctl-tui ~/.local/bin/systemctl-tui", None),
    ("ln -s /tmp/podman-tui/podman-tui ~/.local/bin/podman-tui", None),
    ("ln -s ~/src/apt-fast/apt-fast ~/.local/bin/apt-fast", None),
    ("curl -fsSL https://example.invalid/compose > ~/.local/bin/docker-compose", None),
    ("printf 'x' | tee ~/.local/bin/docker-credential-pass", None),
    ("mise use node@22", "activate the node shim via mise"),
    ("pyenv rehash", "rebuild the pyenv shim"),
    ("uv tool install foo", "install foo from PyPI (the npm package is only a stub)"),
    ("printf 'a = 1' > foo.toml", "write a stub config so foo starts"),
])
def test_ordinary_install_steps_are_not_workarounds(command: str, purpose: str | None):
    assert sandbox_only(command, purpose) is None


def test_workarounds_are_found_in_steps_setups_and_checks():
    shim = "printf '#!/bin/sh\\necho 0' > ~/.local/bin/nvidia-smi && chmod +x ~/.local/bin/nvidia-smi"
    log = [rec(1, "uv tool install tool", 0), rec(2, shim, 0), rec(3, "tool --version", 0, "tool 1.0"),
           rec(4, f"{shim} && tool gpu", 0, "GPU0 ok"), rec(5, "tool serve", 0, "ok", purpose="box-only port fix")]
    verdict = {"step_ids": [1], "checks": [{"command_id": 3, "setup_ids": [2]}, {"command_id": 4, "setup_ids": []},
                                           {"command_id": 5, "setup_ids": []}]}
    assert cited_workarounds(verdict, log) == [
        "setup 2 only works around the box: it replaces the system command nvidia-smi",
        "check 4 only works around the box: it replaces the system command nvidia-smi",
        "check 5 only works around the box: its purpose says so (box-only port fix)"]
    assert cited_workarounds({"step_ids": [1], "checks": [{"command_id": 3, "setup_ids": []}]}, log) == []
    assert cited_workarounds({"step_ids": [1]}, log, {1: "sandbox-only: skip the GPU probe"}) == [
        "step 1 only works around the box: its purpose says so (sandbox-only: skip the GPU probe)"]


def test_failure_plan_reruns_the_steps_before_the_failing_command():
    log = [rec(1, "git clone https://example.invalid/t.git src", 0), rec(2, "ls src", 0),
           rec(3, "pip install -e ./src", 0), rec(4, "tool --help", 1, seconds=0.4), rec(5, "pip list", 0)]
    finish = FinishArgs.model_validate({
        "level": "failed", "steps": [{"command_id": 1}, {"command_id": 3}, {"command_id": 5}],
        "blocking_error": "the console script is broken", "failing_command_id": 4})
    plan = failure_plan(log_verdict(finish, log), log)
    assert [s.command_id for s in plan.steps] == [1, 3] and plan.setups == ()
    assert (plan.failing.command, plan.exit_code, plan.timed_out) == ("tool --help", 1, False)
    finish = finish.model_copy(update={"failing_command_id": None})
    assert failure_plan(log_verdict(finish, log), log) is None  # nothing cited, no failing check
