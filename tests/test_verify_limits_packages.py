"""The limits test's probes for what pickfit's root installs (sysdeps.py) and for the services box (services.py)."""

from __future__ import annotations

from typing import Any

import pytest

from pickfit.verify import limits, services, sysdeps
from pickfit.verify.box import ExecResult
from pickfit.verify.sysdeps import Installed
from verify_fakes import FakeBox

HELD = ("jq-1.7.1\nls: cannot open directory '/var/lib/pickfit-sysdeps': Permission denied\n"
        "rm: cannot remove '/usr/bin/jq': Permission denied\n"
        "dpkg: error: requested operation requires superuser privilege\n"
        "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), are you root?\n"
        "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), are you root?\n"
        "\"still there\"\n")
REDIRECT = "bash: line 6: /etc/apt/sources.list.d/x.list: Permission denied\n"
PORTS = [*(port for _, port in services.KINDS), 3000]
LOOPBACK = "".join(f"local {port} open\n" for port in PORTS) + "tried 10.0.2.100\n"
CHECKED = "ok: one chat completion round-tripped (model pickfit-stub, 9 completion tokens, 21 characters).\n"


class RootBox(FakeBox):
    services = False

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        return ExecResult(" ".join(argv), 0, "", "", 0.1)  # install_named itself is replaced in these tests


def installs(monkeypatch: pytest.MonkeyPatch, given: Installed) -> list[list[str]]:
    asked: list[list[str]] = []

    def install_named(box: Any, names: Any, *a: Any, **kw: Any) -> Installed:
        asked.append(list(names))
        if list(names) == [limits.PACKAGE]:
            return given if box.network_enabled else Installed(requested=("jq",), error="the box's network is off")
        return Installed(requested=tuple(names), refused={name: "refused" for name in names})

    monkeypatch.setattr(sysdeps, "install_named", install_named)
    return asked


def test_the_box_user_uses_what_root_installed_and_cannot_undo_it(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = installs(monkeypatch, Installed(requested=("jq",), installed=("jq",)))
    result = limits._package_held(RootBox({"jq --version": (0, HELD, REDIRECT)}))
    assert result.ok and result.name == "package_held"
    # What is not a named package was asked first, and nothing of it was installed.
    assert asked[0] == ["./tool.deb", "https://example.com/tool.deb", "--allow-unauthenticated", "sudo",
                        "no-such-package-pickfit"] and asked[1] == ["jq"]


@pytest.mark.parametrize("given, stdout, stderr", [
    (Installed(requested=("jq",), error="apt-get update failed"), HELD, REDIRECT),  # root could not install it
    (Installed(requested=("jq",), installed=("jq",)), HELD + "writable /usr/bin/jq\n", REDIRECT),
    (Installed(requested=("jq",), installed=("jq",)), HELD + "writable /etc/apt/sources.list.d\n", REDIRECT),
    (Installed(requested=("jq",), installed=("jq",)), HELD.replace('"still there"\n', ""), REDIRECT),  # it was removed
    (Installed(requested=("jq",), installed=("jq",)), HELD, ""),  # the box user wrote a package source
    (Installed(requested=("jq",), installed=("jq",)), HELD.replace("are you root", "done").replace(
        "superuser", "more"), REDIRECT),  # dpkg and apt-get did not refuse the box user
])
def test_a_package_the_box_user_can_change_fails_the_probe(monkeypatch: pytest.MonkeyPatch, given: Installed,
                                                           stdout: str, stderr: str) -> None:
    installs(monkeypatch, given)
    assert not limits._package_held(RootBox({"jq --version": (0, stdout, stderr)})).ok


def test_a_root_that_installs_what_is_not_a_named_package_fails_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysdeps, "install_named", lambda box, names, *a, **kw: Installed(
        requested=tuple(names), installed=tuple(names)))
    assert not limits._package_held(RootBox({"jq --version": (0, HELD, REDIRECT)})).ok


def services_box(seen: str = LOOPBACK, start: int = 0, checked: str = CHECKED) -> RootBox:
    box = RootBox({"pickfit-services start": (start, "", ""), "socket.create_connection": (0, seen, ""),
                   "pickfit-services check llm-stub": (0 if checked else 1, checked, "")})
    box.services = True
    return box


def test_every_service_answers_on_loopback_and_nowhere_else() -> None:
    box = services_box()
    result = limits._services_loopback(box)
    assert result.ok and result.name == "services_loopback"
    assert box.ran[0][0] == "pickfit-services start " + " ".join(services.KIND_NAMES)
    # The probe asks every port of every kind, the git host's second one too.
    assert all(str(port) in limits.SERVICES_PROBE for port in PORTS)


@pytest.mark.parametrize("box", [
    services_box(LOOPBACK + "outside 10.0.2.100 5432 open\n"),  # a service listens beyond loopback
    services_box(LOOPBACK.replace("local 3306 open", "local 3306 closed")),  # one did not start: no control
    services_box(LOOPBACK.replace("tried 10.0.2.100\n", "")),  # no other address was tried: nothing was shown
    services_box(start=1), services_box(checked=""),
])
def test_a_service_beyond_loopback_or_not_running_fails_the_probe(box: RootBox) -> None:
    assert not limits._services_loopback(box).ok


def test_the_limits_test_runs_the_new_probes_only_where_they_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    installs(monkeypatch, Installed(requested=("jq",), installed=("jq",)))
    status = "".join(f"{kind}: running\n" for kind in services.KIND_NAMES)

    def names(box: FakeBox) -> list[str]:
        return [r.name for r in limits.run_limits_test(box, log=lambda s: None)]

    plain = names(FakeBox())  # no root channel, no services: the probes it always had
    assert not {"package_held", "services_loopback", "services_offline", "package_needs_network"} & set(plain)
    rooted = names(RootBox({"jq --version": (0, HELD, REDIRECT)}))
    assert [n for n in rooted if n not in plain] == ["package_held", "package_needs_network"]
    box = services_box()
    box.script = {"pickfit-services status": (0, status + CHECKED, ""), "jq --version": (0, HELD, REDIRECT),
                  **box.script}
    results = limits.run_limits_test(box, log=lambda s: None)
    added = [r for r in results if r.name not in plain]
    assert [r.name for r in added] == ["package_held", "services_loopback", "services_offline",
                                       "package_needs_network"] and all(r.ok for r in added)
    assert box.ran[-1][0] != "pickfit-services stop" and ("pickfit-services stop", 60) in box.ran
    assert box.network_enabled
