"""Whose failure it is, and steps that only work around the box."""

from __future__ import annotations

import pytest

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.failure import WRITTEN_REASONS, box_reason, failure_plan, sandbox_only
from pickfit.verify.verdict import log_verdict


@pytest.mark.parametrize(("text", "reason"), [
    # The blocking errors of the four failed runs before this check existed (2026-10-29).
    ("No container engine in box (neither docker nor podman) so packaging/linux/run_oci.sh cannot run; "
     "full requirements.txt needs a GPU stack", "needs_container"),
    ("Editable install failed: evdev needs kernel headers (linux/input.h missing, no root to install "
     "linux-headers)", "needs_root"),
    ("scripts/install.sh requires Rust 1.91+ (absent, forbidden to install) and the v1.0.0 asset 404s",
     "needs_toolchain"),
    ("docker: command not found", "needs_container"),
    ("the build needs root access to write /etc/udev", "needs_root"),
    ("cargo is not installed and the release has no Linux binary", "needs_toolchain"),
    ("requires CUDA 12 and an NVIDIA driver", "needs_gpu"),
])
def test_box_limits_are_named(text: str, reason: str):
    assert box_reason(text) == reason


@pytest.mark.parametrize("text", [
    "PyPI wheel ships no code (RECORD has only dist-info), so `tool --help` fails with ModuleNotFoundError",
    "config.toml not found at the project root",
    "cargo build fails: error[E0425] in src/main.rs",
    "the CPU test suite ends 21/22 with one leak",
    None,
])
def test_software_failures_are_not_the_boxs(text: str | None):
    assert box_reason(text) is None


def test_written_reasons_leave_out_the_uninformative_ones():
    assert {"needs_toolchain", "needs_root", "needs_container", "needs_gpu", "gui_only"} <= WRITTEN_REASONS
    assert not {"not_run", "budget_exceeded", "other"} & WRITTEN_REASONS


@pytest.mark.parametrize(("command", "purpose"), [
    ("printf '#!/bin/bash\\nexec /bin/nvidia-smi \"$@\"\\n' > ~/.local/bin/nvidia-smi && chmod +x "
     "~/.local/bin/nvidia-smi", "Install PCI workaround shim cleanly"),
    ("ln -sf /bin/true $HOME/.local/bin/docker", None),
    ("cat > /home/sbx/.local/bin/sudo <<'EOF'\n#!/bin/sh\nexec \"$@\"\nEOF", None),
    ("export BERTH_PCI=0", "sandbox-only PCI workaround so the daemon can start"),
])
def test_steps_that_work_around_the_box(command: str, purpose: str | None):
    assert sandbox_only(command, purpose)


@pytest.mark.parametrize(("command", "purpose"), [
    ("curl -fL -o ~/.local/bin/berth https://example.invalid/berth-linux-amd64 && chmod +x ~/.local/bin/berth",
     "Download and install berth binary"),
    ("install -Dm755 berth-linux-amd64 ~/.local/bin/berth", "install into the box's ~/.local/bin"),
    ("ln -s ~/.local/share/ggrun/ggrun ~/.local/bin/ggrun", "put ggrun on PATH"),
    ("echo 'export PATH=$HOME/.cargo/bin:$PATH' >> ~/.bashrc", None),
])
def test_ordinary_install_steps_are_not_workarounds(command: str, purpose: str | None):
    assert sandbox_only(command, purpose) is None


def rec(cid: int, command: str, code: int, seconds: float = 1.0) -> CommandRecord:
    return CommandRecord(turn=cid, tool="run_command", command=command, exit_code=code, seconds=seconds,
                         stdout="", stderr="", timed_out=False, command_id=cid)


def test_failure_plan_reruns_the_steps_before_the_failing_command():
    log = [rec(1, "git clone https://example.invalid/t.git src", 0), rec(2, "ls src", 0),
           rec(3, "pip install -e ./src", 0), rec(4, "tool --help", 1, 0.4), rec(5, "pip list", 0)]
    finish = FinishArgs.model_validate({
        "level": "failed", "steps": [{"command_id": 1}, {"command_id": 3}, {"command_id": 5}],
        "blocking_error": "the console script is broken", "failing_command_id": 4})
    plan = failure_plan(log_verdict(finish, log), log)
    assert [s.command_id for s in plan.steps] == [1, 3] and plan.setups == ()
    assert (plan.failing.command, plan.exit_code, plan.timed_out) == ("tool --help", 1, False)
    finish = finish.model_copy(update={"failing_command_id": None})
    assert failure_plan(log_verdict(finish, log), log) is None  # nothing cited, no failing check
