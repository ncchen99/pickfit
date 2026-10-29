"""Whose failure it is, whether it repeats, and commands that only work around the box."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pickfit.verify.agent import CommandRecord, FinishArgs
from pickfit.verify.failure import (
    _PROBE,
    WRITTEN_REASONS,
    box_reason,
    cited_workarounds,
    executable,
    failure_plan,
    failure_reason,
    output_limit,
    own_error,
    parse_structure,
    sandbox_only,
    structural_defect,
    structure_probe,
    tool_command,
)
from pickfit.verify.verdict import log_verdict


@pytest.mark.parametrize(("output", "reason"), [
    ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
     "needs_container"),
    ("bash: line 1: docker: command not found", "needs_container"),
    ("error: neither docker nor podman found", "needs_container"),
    ("FileNotFoundError: [Errno 2] No such file or directory: 'docker'", "needs_container"),
    ("Error: spawn docker ENOENT", "needs_container"),
    ("Building wheel for tokenizers (pyproject.toml) ... error\n  error: can't find Rust compiler", "needs_toolchain"),
    ("Cargo, the Rust package manager, is not installed or is not on PATH.", "needs_toolchain"),
    ("gyp ERR! stack Error: not found: make", "needs_toolchain"),
    ("bash: line 1: cargo: command not found", "needs_toolchain"),
    ("bash: go: command not found", "needs_toolchain"),
    ('exec: "go": executable file not found in $PATH', "needs_toolchain"),
    ("FileNotFoundError: [Errno 2] No such file or directory: 'gcc'", "needs_toolchain"),
    ("error: command 'gcc' failed: No such file or directory", "needs_toolchain"),
    ("evdev/input.c:10:10: fatal error: linux/input.h: No such file or directory", "needs_root"),
    ("The 'linux/input.h' and 'linux/input-event-codes.h' include files are missing. You will have to install "
     "the kernel header files in order to continue:", "needs_root"),
    ("npm ERR! Error: EACCES: permission denied, mkdir '/usr/lib/node_modules/foo'", "needs_root"),
    ("install: cannot create regular file '/usr/local/bin/foo': Permission denied", "needs_root"),
    ("PermissionError: [Errno 13] Permission denied: '/usr/local/lib/python3.12/site-packages/foo'", "needs_root"),
    ("OSError: [Errno 30] Read-only file system: '/opt/foo'", "needs_root"),
    ("ImportError: libGL.so.1: cannot open shared object file: No such file or directory", "needs_root"),
    ("System has not been booted with systemd as init system (PID 1). Can't operate.", "needs_root"),
    ("ImportError: libcuda.so.1: cannot open shared object file: No such file or directory", "needs_gpu"),
    ("RuntimeError: CUDA driver version is insufficient for CUDA runtime version", "needs_gpu"),
    ("AssertionError: Torch not compiled with CUDA enabled", "needs_gpu"),
    ("FileNotFoundError: [Errno 2] No such file or directory: 'nvidia-smi'", "needs_gpu"),
    ("Error: OPENAI_API_KEY is not set", "needs_account"),
    ("FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory", "needs_more_resources"),
    ("OSError: [Errno 28] No space left on device", "needs_more_resources"),
])
def test_box_limits_in_a_failing_commands_error_tail(output: str, reason: str):
    assert output_limit("", output, 1, False) == reason


def test_a_kill_is_the_boxs_limit_but_a_timeout_says_nothing():
    assert output_limit("", "", 137, False) == "needs_more_resources"
    assert output_limit("", "", None, True) is None  # a foreground server, a TUI waiting on stdin


@pytest.mark.parametrize("output", [
    "ModuleNotFoundError: No module named 'docker'",
    "ImportError: No module named nvidia",
    "KeyError: 'HOME'",
    "Let's go! config.toml not found",
    "error[E0425]: cannot find value `x` in this scope",
    "WARNING: No GPU detected, falling back to CPU.\nTypeError: run() missing 1 required positional argument",
])
def test_the_tools_own_errors_are_not_the_boxs(output: str):
    assert output_limit("", output, 1, False) is None


def test_only_the_error_tail_is_read_and_warnings_do_not_count():
    crash = "TypeError: 'NoneType' object is not callable"
    early = "\n".join(["ImportError: libcuda.so.1: cannot open shared object file", *(f"step {i}" for i in range(70)),
                       crash])
    assert output_limit("", early, 1, False) is None
    for warning in ("2026-10-29 01:02:03.4: W tensorflow/dso_loader.cc:64] Could not load dynamic library "
                    "'libcuda.so.1'; dlerror: libcuda.so.1: cannot open shared object file",
                    "WARNING: libcuda.so.1 not found, falling back to CPU"):
        assert output_limit("", f"{warning}\n{crash}", 1, False) is None
    assert output_limit("", f"ImportError: libcuda.so.1: cannot open shared object file\n{crash}", 1,
                        False) == "needs_gpu"


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
    ("the tool's installer can't build here: it needs Rust 1.91+", "needs_toolchain"),
])
def test_box_limits_in_the_agents_words(text: str, reason: str):
    assert box_reason(text) == reason


@pytest.mark.parametrize("text", [
    "PyPI wheel ships no code (RECORD has only dist-info), so `tool --help` fails with ModuleNotFoundError",
    "`tool --help` crashes: ModuleNotFoundError: No module named 'docker'",
    "ImportError: No module named nvidia when importing tool.gpu",
    "Release v2.0 asset foo-linux-amd64.tar.gz returns 404; README also mentions `apt install foo`",
    "config.toml not found at the project root",
    "CPU mode (no GPU needed) crashes with TypeError",
    "works without Docker; its CLI exits 2",
    "no sudo or root involved; the server exits 1 on start",
    "it does not need a GPU, but crashes on load",
    None,
])
def test_mentions_and_denied_needs_are_not_needs(text: str | None):
    assert box_reason(text) is None


def rec(cid: int, command: str, code: int, out: str = "", seconds: float = 1.0, purpose: str | None = None,
        timed_out: bool = False, err: str = "") -> CommandRecord:
    return CommandRecord(turn=cid, tool="run_command", command=command, exit_code=code, seconds=seconds,
                         stdout=out, stderr=err, timed_out=timed_out, command_id=cid, purpose=purpose)


TRACE = "Traceback (most recent call last):\n  File \"/tmp/hv/bin/hillock\", line 5\nModuleNotFoundError: No module named 'main'"
HILLOCK = [rec(6, "git clone https://example.invalid/hillock.git src", 0),
           rec(8, "python3 -m venv /tmp/hv && /tmp/hv/bin/pip install -U pip", 0),
           rec(9, "/tmp/hv/bin/pip install -e ./src", 0), rec(10, "/tmp/hv/bin/hillock --help", 1, err=TRACE)]


def test_the_tools_own_command_needs_every_install_step_first():
    verdict = {"step_ids": [6, 8, 9], "failing_id": 10, "checks": []}
    assert tool_command(verdict, HILLOCK) == (HILLOCK[3], "")
    cases = [
        ({**verdict, "failing_id": None}, HILLOCK, "the log names no failing command"),
        ({**verdict, "step_ids": []}, HILLOCK, "no install step ran before it"),
        (verdict, [*HILLOCK[:2], rec(9, "/tmp/hv/bin/pip install -e ./src", 1), HILLOCK[3]],
         "install step 9 did not succeed"),
        (verdict, [*HILLOCK[:2], rec(9, "/tmp/hv/bin/pip install -e ./src | tail -3", 0), HILLOCK[3]],
         "install step 9 did not succeed"),
        ({**verdict, "step_ids": [6, 8, 9, 11]}, [*HILLOCK, rec(11, "pip list", 0)],
         "command 10 ran before the install finished"),
        ({**verdict, "step_ids": [6, 8], "failing_id": 9},
         [*HILLOCK[:2], rec(9, "/tmp/hv/bin/pip install -e ./src", 1, err="error: can't find Rust compiler")],
         "command 9 installs or fetches; it is not the tool's own command"),
        ({**verdict, "failing_id": 11}, [*HILLOCK, rec(11, "python3 -m pip install hillock", 1)],
         "command 11 installs or fetches; it is not the tool's own command"),
    ]
    for case, log, why in cases:
        assert tool_command(case, log) == (None, why)


def test_an_error_of_the_tools_code_is_only_a_suspicion():
    assert own_error(HILLOCK[3]) == ("ModuleNotFoundError: No module named 'main'", "")
    assert own_error(rec(10, "hillock --help", 1, err="ImportError: libGL.so.1: cannot open shared object file: "
                         "No such file or directory")) == (None, "command 10 hit a limit of the box (needs_root)")
    assert own_error(rec(10, "hillock check", 1, out="21/22 checks passed; 1 FAIL")) == (
        None, "command 10 shows no error of the tool's own code")


def test_the_program_a_failing_command_runs():
    assert executable("/tmp/hv/bin/hillock --help") == "/tmp/hv/bin/hillock"
    assert executable("cd src && FOO=1 env tool run --x | head -3") == "tool"
    assert executable("") is None
    assert "PICKFIT_PROBE" in structure_probe("hillock --help") and structure_probe("") is None


@pytest.mark.parametrize(("structure", "defect"), [
    ({"kind": "python", "dist": "hillock", "version": "1.0.0", "entry_point": "main:main", "module": "main",
      "in_files": False, "importable": False, "source": "direct"},
     "the installed hillock 1.0.0 (from a local or VCS source) declares the console script main:main, and no "
     "module main is installed"),
    ({"kind": "python", "dist": "hillock", "module": "main", "in_files": False, "importable": True}, None),
    ({"kind": "python", "dist": "hillock", "module": "main", "in_files": True, "importable": False}, None),
    ({"kind": "python", "dist": None}, None),
    ({"kind": "npm", "package": "foo", "version": "1.2.0", "bin": "dist/cli.js", "exists": False,
      "install_scripts": []},
     "the installed npm package foo 1.2.0 names bin dist/cli.js, and the package has no such file"),
    # A postinstall may have been meant to make it (and may have been skipped or blocked here).
    ({"kind": "npm", "package": "foo", "bin": "bin/foo", "exists": False, "install_scripts": ["postinstall"]}, None),
    ({"kind": "unknown"}, None),
    (None, None),
])
def test_a_structural_defect_needs_the_packages_own_metadata(structure, defect):
    assert structural_defect(structure) == defect


def fake_install(root: Path, *, ships_module: bool) -> Path:
    """A distribution `fakepkg` with console script `fakecli` -> fakemod:main, installed under root."""
    site = root / "site"
    info = site / "fakepkg-0.1.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: fakepkg\nVersion: 0.1\n")
    (info / "entry_points.txt").write_text("[console_scripts]\nfakecli = fakemod:main\n")
    record = ["fakepkg-0.1.dist-info/METADATA,,", "fakepkg-0.1.dist-info/RECORD,,"]
    if ships_module:
        (site / "fakemod.py").write_text("def main():\n    pass\n")
        record.append("fakemod.py,,")
    (info / "RECORD").write_text("\n".join(record) + "\n")
    script = root / "bin" / "fakecli"
    script.parent.mkdir()
    script.write_text(f"#!{sys.executable}\nfrom fakemod import main\nmain()\n")
    script.chmod(0o755)
    return script


@pytest.mark.parametrize(("ships_module", "missing"), [(False, True), (True, False)])
def test_the_probe_reads_the_installed_metadata(tmp_path: Path, ships_module: bool, missing: bool):
    script = fake_install(tmp_path, ships_module=ships_module)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "site")}
    result = subprocess.run([sys.executable, "-", str(script)], input=_PROBE, capture_output=True, text=True,
                            env=env, timeout=60, check=True)
    structure = parse_structure(result.stdout)
    assert structure["dist"] == "fakepkg" and structure["entry_point"] == "fakemod:main"
    assert (structure["in_files"], structure["importable"]) == (not missing, not missing)
    assert bool(structural_defect(structure)) == missing


def test_the_reason_for_a_failure_that_is_not_the_tools():
    holdspeak = [rec(2, "git clone --depth 1 https://example.invalid/holdspeak.git repo", 0),
                 rec(5, "cd repo && uv pip install -e '.[linux]'", 1,
                     err="You will have to install the kernel header files in order to continue")]
    assert failure_reason({"step_ids": [2], "failing_id": 5, "checks": []}, holdspeak, "it broke") == "needs_root"
    # No failing command: the words decide, unless a check passed (the tool ran).
    assert failure_reason({"checks": []}, [], "needs Rust 1.91+, absent here") == "needs_toolchain"
    assert failure_reason({"checks": [{"passed": True}]}, [], "needs Rust 1.91+, absent here") is None


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
    ("cd ~/.local/bin && printf '#!/bin/sh\nexit 0\n' > sudo && chmod +x sudo", None),
    ("mkdir -p /tmp/shim && printf '#!/bin/sh\necho 0' > /tmp/shim/nvidia-smi && chmod +x /tmp/shim/nvidia-smi "
     "&& PATH=/tmp/shim:$PATH tool --gpu", None),
    ("wget -qO ~/.local/bin/nvidia-smi https://example.invalid/fake && chmod +x ~/.local/bin/nvidia-smi", None),
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
    ("ls -l ~/.local/bin/docker > /dev/null 2>&1 && tool --version", None),
    ("cd ~/.local/bin && ls && tool --version > out.txt", None),
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
