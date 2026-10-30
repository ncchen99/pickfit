"""Install-method ranking and the error rule table."""

from __future__ import annotations

import json
from pathlib import Path

from pickfit.schema import ExtractionResult, InstallClaim
from pickfit.verify.plan import plan_for, rank_install_methods
from pickfit.verify.rules import RULES, error_signature, match_rules

FIXTURES = Path(__file__).parent / "fixtures" / "verify"


def claim(method: str, command: str, platforms: list[str] | None = None) -> InstallClaim:
    return InstallClaim(method=method, command=command, platforms=platforms or [])


def extraction(slug: str) -> ExtractionResult:
    data = json.loads((FIXTURES / f"{slug}.json").read_text(encoding="utf-8"))
    return ExtractionResult.model_validate(data["extraction"])


# ---------------------------------------------------------------- ranking


def test_evnx_ranks_package_managers_then_script_then_toolchains():
    plan = plan_for(extraction("evnx"))
    assert [(c.rank, c.method, c.origin) for c in plan.candidates] == [
        (1, "pipx", "readme"), (2, "npm", "readme"), (3, "script", "readme"), (4, "cargo", "readme")]
    assert {s.method for s in plan.skipped} == {"brew", "other"}
    assert all("windows" in s.reason for s in plan.skipped if s.method == "other")


def test_macos_box_ranks_brew_first_and_keeps_windows_aside():
    plan = plan_for(extraction("evnx"), "macos")
    assert [c.method for c in plan.candidates] == ["brew", "pipx", "npm", "script", "cargo"]
    assert "owns /opt/homebrew" in plan.candidates[0].note and "Homebrew" in plan.candidates[2].note
    assert [s.method for s in plan.skipped] == ["other", "other"]
    docker = rank_install_methods([claim("docker", "docker run x/y")], "macos")
    assert not docker.candidates and docker.skipped[0].method == "docker"


def test_pip_gets_isolated_alternatives_first():
    plan = plan_for(extraction("graphtty"))
    assert [c.command for c in plan.candidates] == [
        "uv tool install graphtty", "pipx install graphtty", "pip install graphtty"]
    assert [c.origin for c in plan.candidates] == ["derived", "derived", "readme"]


def test_pip_derivation_handles_flags_and_versions_but_not_requirement_files():
    plan = rank_install_methods([claim("pip", "python3 -m pip install --user foo==1.2")])
    assert [c.command for c in plan.candidates][:2] == ["uv tool install foo==1.2", "pipx install foo==1.2"]
    plan = rank_install_methods([claim("pip", "pip install -r requirements.txt")])
    assert [c.command for c in plan.candidates] == ["pip install -r requirements.txt"]


def test_duplicates_and_box_incompatible_methods():
    plan = rank_install_methods([
        claim("pip", "pip install tool"),
        claim("pipx", "pipx  install tool"),  # same as the derived one, modulo spaces
        claim("docker", "docker run tool"),
        claim("binary", "curl -LO https://example.com/tool-linux-x86_64.tar.gz"),
        claim("source", "make install"),
    ])
    assert [c.method for c in plan.candidates] == ["uv", "pipx", "pip", "binary", "source"]
    assert [s.method for s in plan.skipped] == ["docker"]


def test_linux_only_claims_skip_on_macos():
    plan = rank_install_methods([claim("binary", "./install-linux.sh", ["linux"])], os="macos")
    assert plan.candidates == [] and "linux only" in plan.skipped[0].reason


# ---------------------------------------------------------------- rules


def hits(stderr: str, exit_code: int = 1, command: str = "x", stdout: str = "") -> dict[str, str | None]:
    return {h.rule: h.suggested_command for h in match_rules(command, exit_code, stdout, stderr)}


def test_rule_table_size():
    assert 6 <= len(RULES) <= 8


def test_missing_shared_library_names_the_package():
    found = match_rules("llama-server --version", 127, "",
                        "llama-server: error while loading shared libraries: libgomp.so.1: cannot open")
    assert [h.rule for h in found] == ["missing_shared_library"]
    assert "libgomp1" in found[0].hint


def test_pep668_suggests_an_isolated_install():
    found = hits("error: externally-managed-environment\n\n× This environment is externally managed",
                 command="pip install evnx")
    assert found == {"externally_managed_python": "uv tool install evnx"}


def test_missing_toolchain_is_not_reported_as_path():
    assert set(hits("bash: line 1: cargo: command not found", 127)) == {"missing_toolchain"}
    assert set(hits("bash: line 1: graphtty: command not found", 127)) == {"not_on_path"}
    assert hits("bash: line 1: graphtty: command not found", 1) == {}  # PATH needs exit 127


def test_python_version_and_flags():
    assert "python_version" in hits("ERROR: No matching distribution found for tinyq-cli")
    assert "flag_unsupported" in hits("graphtty: error: unrecognized arguments: --version", 2)
    assert "flag_unsupported" in hits("error: unexpected argument '--version' found", 2)


def test_error_message_that_names_its_fix():
    stderr = "Error: .env.example does not exist. Create it with `evnx sync`."
    assert hits(stderr, 2) == {"error_names_fix": "evnx sync"}


def test_needs_root():
    assert "needs_root" in hits("mkdir: cannot create directory '/usr/local/lib/x': Permission denied")
    assert "needs_root" in hits("touch: cannot touch '/usr/bin/x': Read-only file system")


def test_success_has_no_hints():
    assert match_rules("pipx install evnx", 0, "", "Permission denied") == []


def test_error_signature_ignores_numbers_and_paths():
    a = error_signature(2, "", "warn\nError: lock held by pid 4242 at /tmp/x1/lock")
    b = error_signature(2, "", "Error: lock held by pid 77 at /tmp/zz/lock")
    assert a == b and a.startswith("exit 2:")
    assert error_signature(0, "fine", "") is None
    assert error_signature(1, "", "a") != error_signature(2, "", "a")
