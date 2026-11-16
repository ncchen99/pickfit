"""The build box (`pickfit verify --toolchain`, H-002): compilers, Rust and Go in the image, more cores, memory and
time per command, and an agent that is told it may build from source there. Nothing leaves the process."""

from __future__ import annotations

from pathlib import Path

import pytest

import pickfit.env
from pickfit import meta
from pickfit.ledger import Caps, Ledger
from pickfit.verify import modal_box as mb
from pickfit.verify.agent import AgentLimits, VerifyAgent, render_task
from pickfit.verify.box import BoxLimits
from pickfit.verify.cli import TOOLCHAIN_AGENT_S, box_factory
from pickfit.verify.plan import plan_for
from pickfit.verify.task import VerifyTask, load_fixture
from verify_fakes import FakeBox, FakeServer

FIXTURES = Path(__file__).parent / "fixtures" / "verify"
NO_BUILD = "Do not install language toolchains (Rust, Go); pick another candidate."


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


@pytest.fixture
def task() -> VerifyTask:  # evnx: pipx and npm first, then a script, then `cargo install evnx`
    return load_fixture(FIXTURES / "evnx.json", fetch=lambda url: "# evnx\n\nInstall: `cargo install evnx`\n")


def instructions(task: VerifyTask, box: FakeBox, tmp_path: Path) -> str:
    ledger = Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    return VerifyAgent(task, box, client=FakeServer().client(), ledger=ledger, runs_dir=tmp_path / "runs",
                       log=lambda line: None, run_id="verify-evnx-test").instructions


def test_the_build_box_has_its_own_image_with_compilers_and_pinned_rust_and_go():
    plain, none = mb.image_layers("gvisor")
    name, packages = mb.image_layers("gvisor", toolchain=True)
    assert none == () and name != plain and name.startswith("pickfit-sbx-build:")
    assert {"build-essential", "cmake", "pkg-config", "libssl-dev"} <= set(packages)
    assert mb.image_layers("gvisor", display=True, toolchain=True)[0].startswith("pickfit-sbx-gui-build:")
    assert mb.image_layers("vm", toolchain=True)[0].startswith("pickfit-sbx-vm-build:")
    # Rust and Go are their projects' releases, each checked against a pinned SHA-256 before it is unpacked.
    for version, sha in ((mb.RUST_VERSION, mb.RUST_SHA256), (mb.GO_VERSION, mb.GO_SHA256)):
        assert version in mb.TOOLCHAIN_INSTALL and len(sha) == 64 and sha in mb.TOOLCHAIN_INSTALL
    assert mb.TOOLCHAIN_INSTALL.count("sha256sum -c") == 2
    box = mb.ModalBox(toolchain=True)
    assert box.toolchain and box.image == name
    assert not mb.ModalBox().toolchain and mb.ModalBox().image == plain


def test_the_build_box_has_room_for_a_build_and_keeps_the_user_limits():
    plain = box_factory("modal", 900)("run", "agent")
    build = box_factory("modal", 900, toolchain=True)("run", "agent")
    assert (plain.limits.cpus, plain.limits.memory_mb, plain.limits.max_command_s) == (2.0, 2048, 600)
    assert (build.limits.cpus, build.limits.memory_mb, build.limits.max_command_s) == (4.0, 6144, 1800)
    kept = ("pids", "home_mb", "tmp_mb", "nofile", "lifetime_s")
    assert [getattr(build.limits, k) for k in kept] == [getattr(plain.limits, k) for k in kept]
    assert build.create_kwargs()["cpu"] == (2.0, 2.0) and build.create_kwargs()["memory"] == (6144, 6144)
    assert build.create_kwargs()["outbound_cidr_allowlist"] == plain.create_kwargs()["outbound_cidr_allowlist"]
    assert box_factory("modal", 900, toolchain=True, memory_mb=16384)("r", "a").limits.memory_mb == 16384
    assert box_factory("modal", 900, toolchain=True, memory_mb=4096)("r", "a").limits.memory_mb == 4096
    assert TOOLCHAIN_AGENT_S > AgentLimits().max_seconds
    with pytest.raises(ValueError, match="--toolchain"):
        box_factory("docker", 900, toolchain=True)


def test_the_agent_may_build_from_source_only_in_a_build_box(task: VerifyTask, tmp_path: Path):
    plain, build = FakeBox(), FakeBox()
    build.toolchain = True
    told = instructions(task, plain, tmp_path)
    assert NO_BUILD in told and "you must not install (Rust, Go" in told
    told = instructions(task, build, tmp_path)
    assert NO_BUILD not in told and "you must not install (Rust, Go" not in told
    assert "cargo" in told and "build" in told and "pitfall" in told
    # The rest of the rules are the same text: only the two toolchain sentences differ.
    assert told.count("\n") == instructions(task, plain, tmp_path).count("\n")
    assert "no sudo, no apt-get" in told and "Do not fake a system command" in told

    plan = plan_for(task.extraction)
    shown = render_task(task, plan, plain, AgentLimits())
    assert "needs a Rust toolchain, which the box does not have" in shown and "gcc" not in shown
    shown = render_task(task, plan, build, AgentLimits())
    assert "which the box does not have" not in shown
    assert "gcc" in shown and f"Rust {mb.RUST_VERSION}" in shown and f"Go {mb.GO_VERSION}" in shown


def test_a_build_box_is_not_taken_for_one_sized_for_model_weights(task: VerifyTask):
    build = FakeBox()
    build.toolchain = True
    build.limits = BoxLimits(cpus=4.0, memory_mb=6144, max_command_s=1800)
    assert "sized for model weights" not in render_task(task, plan_for(task.extraction), build, AgentLimits())
    build.limits = BoxLimits(cpus=4.0, memory_mb=16384, home_mb=8192, max_command_s=1800)  # asked for: --memory-mb
    assert "sized for model weights" in render_task(task, plan_for(task.extraction), build, AgentLimits())
