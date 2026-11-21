"""Distribution packages pickfit installs for a tool, as root: `sudo apt-get install <names>` without giving the box
user root (docs/proposals/privileges.md P3, loop/issues.md H-003).

A tool whose docs say "sudo apt-get install libwebkit2gtk-4.1-dev" cannot be verified by a box user who is not root.
Here pickfit runs that one step itself, with its own root identity in the box (Box.harness_exec), and nothing else:

    install_named(box, names, timeout_s) -> Installed   what was installed, what was refused and why, the command

What is accepted is a *named package of the distribution's own repository*, and only that:

- A name is checked before anything reaches the box (check_names): Debian's own syntax (lowercase letters, digits,
  + - .), so no option, no version or release or architecture suffix, no pattern, no path, no .deb, no URL and
  nothing a shell would read. Packages that only make sense with root, an init system, a kernel or a container
  engine (sudo, systemd, docker.io, linux-headers-*, ...) are refused with that reason: they belong to the
  full-machine box, not here.
- In the box, root's script (IN_BOX) refreshes the package lists, then confirms where things come from in two ways:
  every package source configured in the box is one of the distribution's own hosts (`apt-cache policy`), and every
  package apt would install for a name, dependencies included, carries the distribution's label on a signed release
  (`apt-get -s install`: "Inst name (version Debian:13.8/stable [amd64])"). A name apt does not know, one it would
  read as a pattern, a virtual name with several providers, and one whose install would remove something are each
  refused on their own; the others still install.
- The install itself is `apt-get install -y --no-remove -- <names>` with the box's own sources. No source is added,
  no key, no file. A request whose packages unpack to more than MAX_INSTALL_MB is refused.

The box user gains nothing but the packages' files: they are root's, the box user's commands keep no-new-privileges
(a setuid program in a package gives it nothing), no daemon starts (no init system, and policy-rc.d refuses the
packages' own start scripts), and root's script runs with its own PATH, HOME and a temporary directory the box user
cannot enter. limits.py is unchanged; loop/proposals/limits-sysdeps-services.patch adds the check that the box user
cannot remove, replace or reconfigure what was installed.

Which boxes can do it (read from the code; nothing here started a box):

- LinuxBox on Modal (gVisor or VM) and on EC2: root's commands run in the machine's writable root filesystem, with
  the machine's own network while the box is online. install_named works at any time the network is on, so an
  agent's request can be answered in the same box.
- DockerBox (local development): the root filesystem is read-only and the box has no root channel, so nothing can
  be installed in a running box. docker_variant() runs the same checked install in a throwaway root container of
  the base image and commits it as `pickfit-sbx-pkg:<hash>`; a DockerBox started from that image has the packages.
- macOS and Windows boxes: refused (apt is Debian's).

Every verification still uses a fresh box. PackagedBoxes wraps a box factory so that each box of one run (the
agent's, the replay's, the one that confirms a failure) gets the packages right after it starts: the replay box
installs exactly what the agent's box got, and fails to start if it cannot. record() then puts
`sudo apt-get install -y <names>` first in the run's steps, which become the install guide.

Until the agent can ask for a package itself (privileges.md P2), planned_names() picks the names from what is
already known, the way box_needs picks a box: the extraction's system packages, and after an attempt that ended
`needs_root`, the README's own `apt-get install` lines and what that attempt's error names.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pickfit.schema import COMMAND_MAX, InstallStep, VerificationRun
from pickfit.verify.box import Box, BoxError, DockerBox, ensure_docker, ensure_image, sandbox_image_tag
from pickfit.verify.gui import PYTHON

INSTALL_TIMEOUT_S = 300
MAX_NAMES = 16  # in one request; a tool that needs more is not a "few named packages" case
MAX_INSTALL_MB = 2048  # what one request's packages, dependencies included, may unpack to
MAX_PLANNED = 8  # names planned_names() proposes for one record
ENABLED_ENV = "PICKFIT_SYSDEPS"  # "0" turns the plan-side installs off (watch.routed_verify)
MARK = "PICKFIT_SYSDEPS "
# Where a Debian box's packages may come from: the hosts of its configured sources, and the label its releases carry.
DISTRO_HOSTS = ("deb.debian.org", "security.debian.org")
DISTRO_LABELS = ("Debian", "Debian-Security")
GUIDE_PREFIX = "sudo apt-get install -y "
GUIDE_PURPOSE = "System packages the tool needs (pickfit installed them as root, before the steps below)"

# Debian policy 5.6.1: lowercase letters, digits, plus, minus and full stop; at least two characters; starts
# with a letter or a digit.
NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,62}$")
_PACKAGE_FILE = re.compile(r"\.(?:deb|udeb|ddeb|dsc|changes|buildinfo|tar(?:\.\w+)?|tgz|zip|sh|run)$", re.I)
_SHELL = re.compile(r"[\s;&|<>$`(){}\[\]!\\'\"#]")
_SELECTOR = re.compile(r"[=:*?~^,@%]")
# Not a package install's job: these need root at run time, an init system, a kernel of their own or a container
# engine, so installing the package here would not make the tool work (privileges.md P6, the full-machine box).
FULL_MACHINE = re.compile(
    r"^(?:sudo|sudo-ldap|doas|opendoas|policykit-1|polkitd|pkexec|systemd|systemd-.*|init|sysvinit-.*|openrc|runit.*|"
    r"dkms|.*-dkms|linux-(?:image|headers|modules|source|kbuild)-?.*|kmod|docker|docker\.io|docker-.*|podman.*|"
    r"containerd.*|runc|crun|buildah|lxc.*|lxd.*|incus.*|snapd|openssh-server|qemu-system.*|libvirt-daemon.*|"
    r"virtualbox.*)$")
FULL_MACHINE_REASON = ("needs the full-machine box (root at run time, an init system, a kernel or a container "
                       "engine): installing the package here would not make it work")


@dataclass(frozen=True)
class Installed:
    """What one request came to. `installed` is what the guide's `sudo apt-get install -y` step lists."""

    requested: tuple[str, ...] = ()
    installed: tuple[str, ...] = ()  # the requested names apt installed now
    present: tuple[str, ...] = ()  # requested names the box already had (nothing to do, nothing for the guide)
    refused: dict[str, str] = field(default_factory=dict)  # name -> why
    added: tuple[str, ...] = ()  # every package apt added, dependencies included, as name=version
    command: str | None = None  # the exact command root ran, None when nothing was installed
    error: str | None = None  # why nothing could be installed at all (the box, its network, apt itself)
    megabytes: float | None = None  # what the added packages unpack to, by their Installed-Size
    seconds: float = 0.0
    image: str | None = None  # docker_variant: the image that holds the packages

    @property
    def ok(self) -> bool:
        """Every requested name is in the box now."""
        return self.error is None and not self.refused

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def describe(self) -> str:
        parts = []
        if self.installed:
            parts.append(f"installed {', '.join(self.installed)}")
        if self.present:
            parts.append(f"already there: {', '.join(self.present)}")
        parts += [f"refused {name} ({why})" for name, why in self.refused.items()]
        if self.error:
            parts.append(f"nothing installed: {self.error}")
        return "; ".join(parts) or "nothing asked"


# ---------------------------------------------------------------- names


def refusal(name: Any) -> str | None:
    """Why `name` is not a named distribution package pickfit installs, or None when it may be asked of apt."""
    if not isinstance(name, str) or not name:
        return "not a package name"
    if name.startswith("-"):
        return "an option, not a package name"
    if re.match(r"^(?:ppa|cdrom|copy|mirror):|^deb(?:-src)?\s", name, re.I):
        return "a package source, not a named package: no source is ever added"
    if re.match(r"^[a-z][a-z0-9+.-]*:/", name, re.I) or "://" in name:
        return "a URL, not a named package of the distribution"
    if "/" in name or _PACKAGE_FILE.search(name):
        return "a file or a path, not a named package of the distribution"
    if _SHELL.search(name):
        return "not a package name (a command or several words)"
    if _SELECTOR.search(name):
        return "a name only: no version, release, architecture or pattern"
    if name.endswith("-"):
        return "a name only: apt reads a trailing - as a removal"
    if not NAME.match(name):
        return "not a Debian package name (lowercase letters, digits, + - . only)"
    if FULL_MACHINE.match(name):
        return FULL_MACHINE_REASON
    return None


def check_names(names: Iterable[Any], limit: int = MAX_NAMES) -> tuple[tuple[str, ...], dict[str, str]]:
    """(the names that may be asked of apt, in order and once each; the others with why). Nothing is run."""
    accepted: list[str] = []
    refused: dict[str, str] = {}
    for name in names:
        key = name if isinstance(name, str) and name else repr(name)
        if key in accepted or key in refused:
            continue
        why = refusal(name)
        if why is None and len(accepted) >= limit:
            why = f"more than {limit} names in one request"
        if why is None:
            accepted.append(key)
        else:
            refused[key[:80]] = why
    return tuple(accepted), refused


# ---------------------------------------------------------------- root's script, in the box

# Root, in the box. argv[1] is JSON: names (already checked on the host; checked again here), hosts, labels,
# max_mb. Prints one line: MARK + JSON. Never raises: what goes wrong is the result's "error".
IN_BOX = r'''import json, os, re, subprocess, sys

MARK = "PICKFIT_SYSDEPS "
APT_GET = "/usr/bin/apt-get"
APT_CACHE = "/usr/bin/apt-cache"
TMP = "/var/lib/pickfit-sysdeps"  # root's, mode 0700: maintainer scripts get no temporary file the box user can reach
POLICY = "/usr/sbin/policy-rc.d"
ROOT = 0
ENV = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root", "LANG": "C.UTF-8",
       "LC_ALL": "C.UTF-8", "DEBIAN_FRONTEND": "noninteractive", "TMPDIR": TMP}
APT = [APT_GET, "-o", "DPkg::Lock::Timeout=60", "-o", "Acquire::Retries=2",
       "-o", "APT::Get::AllowUnauthenticated=false", "-o", "Acquire::AllowInsecureRepositories=false",
       "-o", "Dpkg::Options::=--force-confold"]
NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]{1,62}$")
INST = re.compile(r"^Inst (\S+)(?: \[[^\]]*\])? \((\S+) ([^)]*)\)", re.M)
out = {"installed": [], "present": [], "refused": {}, "added": [], "command": None, "error": None, "megabytes": None}


def done(error=None):
    if error:
        out["error"] = " ".join(str(error).split())[-400:]
    print(MARK + json.dumps(out), flush=True)
    sys.exit(0)


def run(argv, timeout):
    try:
        p = subprocess.run(argv, env=ENV, cwd="/", stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "E: timed out after %ds" % timeout
    except OSError as err:
        return 127, "", "E: %s" % err


def errors(text):
    lines = [line[3:].strip() for line in text.splitlines() if line.startswith("E: ")]
    return "; ".join(lines)[:300] or " ".join(text.split())[-300:]


def outside(release, labels):
    """The sources in an Inst line's release part that do not carry the distribution's label."""
    sources = [s.strip() for s in re.sub(r"\s*\[[^\]]*\]\s*$", "", release).split(",")]
    return [s or "?" for s in sources if s.split(":", 1)[0] not in labels or ":" not in s]


def simulate(names, labels):
    """(what apt would install as (name, version) pairs, or None; why not)."""
    code, stdout, stderr = run([*APT, "-s", "install", "--no-remove", "--", *names], 120)
    if code != 0:
        text = errors(stderr)
        if "Unable to locate package" in text or "Couldn't find any package" in text:
            return None, "not a package in the distribution's repository"
        if "virtual package" in text or "no installation candidate" in text:
            return None, "no single installable package of that name: " + text[:160]
        return None, "apt cannot install it here: " + text[:200]
    if re.search(r"for (?:regex|glob) ", stdout) or re.search(r"for (?:regex|glob) ", stderr):
        return None, "not an exact package name (apt would read it as a pattern)"
    if re.search(r"^Remv ", stdout, re.M):
        return None, "installing it would remove a package the box has"
    found = INST.findall(stdout)
    for name, version, release in found:
        bad = outside(release, labels)
        if bad:
            return None, "would install %s from outside the distribution's repository (%s)" % (
                name, ", ".join(bad)[:120])
    return [(name, version) for name, version, _ in found], None


def main():
    try:
        asked = json.loads(sys.argv[1])
        names, hosts, labels = list(asked["names"]), set(asked["hosts"]), set(asked["labels"])
        max_mb = float(asked["max_mb"])
    except Exception as err:
        done("bad request: %s" % err)
    if os.geteuid() != ROOT:
        done("not run as root")
    if any(not isinstance(n, str) or not NAME.match(n) for n in names):
        done("a name is not a package name")
    os.makedirs(TMP, mode=0o700, exist_ok=True)
    os.chown(TMP, ROOT, -1)
    os.chmod(TMP, 0o700)
    if not os.path.exists(POLICY):  # no package starts a daemon: there is no init system here
        with open(POLICY, "w") as f:
            f.write("#!/bin/sh\nexit 101\n")
        os.chmod(POLICY, 0o755)
    update = [*APT, "-o", "APT::Update::Error-Mode=any", "update", "-q"]
    code, stdout, stderr = run(update, 120)
    if code != 0:  # apt's download user is not root: where a rule treats every other uid as the box, stay root
        APT[1:1] = ["-o", "APT::Sandbox::User=root"]
        code, stdout, stderr = run([*APT, "-o", "APT::Update::Error-Mode=any", "update", "-q"], 120)
    if code != 0:
        done("apt-get update failed: " + errors(stderr or stdout))
    code, stdout, stderr = run([APT_CACHE, "policy"], 60)
    sites = set(re.findall(r"^\s+origin[ \t]*(\S*)[ \t]*$", stdout, re.M))
    if code != 0 or not sites:
        done("the box's package sources could not be read: " + errors(stderr or stdout))
    foreign = sorted(s or "a local source" for s in sites - hosts)
    if foreign:
        done("the box has a package source outside the distribution's own: " + ", ".join(foreign))
    wanted = []
    for name in names:
        would, why = simulate([name], labels)
        if why:
            out["refused"][name] = why
        elif would:
            wanted.append(name)
        else:
            out["present"].append(name)
    if not wanted:
        done()
    would, why = simulate(wanted, labels)
    if why or not would:
        for name in wanted:
            out["refused"][name] = "together with the others asked: " + (why or "nothing to install")
        done()
    # What the packages unpack to, from the lists' own Installed-Size (kB). Not asked of `apt-get install
    # --assume-no`: with nothing but the named packages to install, apt-get does not ask and installs.
    code, stdout, stderr = run([APT_CACHE, "show", "--no-all-versions",
                                *["%s=%s" % pair for pair in would]], 120)
    sizes = [int(kb) for kb in re.findall(r"^Installed-Size: (\d+)\s*$", stdout, re.M)]
    if code == 0 and len(sizes) >= len(would):
        mb = sum(sizes) / 1024.0
        out["megabytes"] = round(mb, 1)
        if mb > max_mb:
            for name in wanted:
                out["refused"][name] = "the request would add %.0f MB, over the %.0f MB one may add" % (mb, max_mb)
            done()
    install = [*APT, "install", "-y", "--no-remove", "--", *wanted]
    code, stdout, stderr = run(install, int(asked.get("install_s") or 900))
    run([*APT, "clean"], 60)
    if code != 0:
        done("apt-get install failed: " + errors(stderr or stdout))
    out["installed"] = wanted
    out["added"] = ["%s=%s" % pair for pair in would]
    out["command"] = " ".join(install)
    done()


try:
    main()
except SystemExit:
    raise
except BaseException as err:
    done("%s: %s" % (type(err).__name__, err))
'''


def request(names: Sequence[str], *, max_mb: float = MAX_INSTALL_MB, install_s: int | None = None,
            hosts: Sequence[str] = DISTRO_HOSTS, labels: Sequence[str] = DISTRO_LABELS) -> str:
    """The JSON root's script reads."""
    return json.dumps({"names": list(names), "hosts": list(hosts), "labels": list(labels), "max_mb": max_mb,
                       "install_s": install_s})


def read_result(stdout: str) -> dict[str, Any] | None:
    """The script's one result line (the last, should a package's own script print one that looks like it)."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(MARK):
            try:
                found = json.loads(line[len(MARK):])
            except ValueError:
                return None
            return found if isinstance(found, dict) else None
    return None


def _result(requested: tuple[str, ...], refused: dict[str, str], found: dict[str, Any] | None, *, seconds: float,
            tail: str = "", image: str | None = None) -> Installed:
    if found is None:
        return Installed(requested=requested, refused=refused, seconds=seconds, image=image,
                         error=f"root's install script gave no result: {' '.join(tail.split())[-300:] or 'no output'}")
    megabytes = found.get("megabytes")
    return Installed(
        requested=requested, installed=tuple(map(str, found.get("installed") or ())),
        present=tuple(map(str, found.get("present") or ())),
        refused={**refused, **{str(k): str(v) for k, v in (found.get("refused") or {}).items()}},
        added=tuple(map(str, found.get("added") or ())), command=found.get("command") or None,
        error=found.get("error") or None, megabytes=float(megabytes) if megabytes is not None else None,
        seconds=seconds, image=image)


def root_channel(box: Box) -> bool:
    """Can pickfit run its own root commands in this box? (DockerBox and the test fakes cannot.)"""
    return type(box).harness_exec is not Box.harness_exec


def unsupported(box: Box) -> str | None:
    """Why this box cannot get a package installed while it runs, or None."""
    if box.os != "linux":
        return f"only a Debian-based Linux box installs apt packages (this box is {box.os})"
    if not root_channel(box):
        return (f"{type(box).__name__} has no root channel for pickfit and a read-only root filesystem: nothing "
                "installs in a running box (sysdeps.docker_variant builds an image that holds the packages)")
    if not box.network_enabled:
        return "the box's network is off: packages install while it is online"
    return None


def install_named(box: Box, names: Iterable[Any], timeout_s: int = INSTALL_TIMEOUT_S, *,
                  max_mb: float = MAX_INSTALL_MB, log: Callable[[str], None] | None = None) -> Installed:
    """Install named distribution packages in a started box, as root, for the box user to use.

    Returns what was installed, what was already there, what was refused and why, and the exact command root ran.
    Never raises for a refusal or a failed install: `error` says why nothing could be installed at all. The box
    user's identity and limits do not change. Call it while the box is online.
    """
    began = time.monotonic()
    requested = tuple(n if isinstance(n, str) else repr(n) for n in names)
    accepted, refused = check_names(requested)

    def finish(result: Installed) -> Installed:
        if log is not None:
            log(f"packages · {result.describe()} · {result.seconds:.0f}s")
        return result

    if not accepted:
        return finish(Installed(requested=requested, refused=refused, seconds=round(time.monotonic() - began, 1)))
    why = unsupported(box)
    if why:
        return finish(Installed(requested=requested, refused=refused, error=why,
                                seconds=round(time.monotonic() - began, 1)))
    timeout_s = max(60, int(timeout_s))
    # apt-get update, the checks and the size question each have their own limits; the install gets the rest.
    asked = request(accepted, max_mb=max_mb, install_s=max(30, timeout_s - 45))
    try:
        ran = box.harness_exec([PYTHON, "-I", "-S", "-", asked], timeout_s, stdin=IN_BOX.encode())
    except BoxError as err:
        return finish(Installed(requested=requested, refused=refused, error=f"the box failed: {err}"[:400],
                                seconds=round(time.monotonic() - began, 1)))
    return finish(_result(requested, refused, read_result(ran.stdout), seconds=round(time.monotonic() - began, 1),
                          tail=f"{ran.stdout}\n{ran.stderr}"))


# ---------------------------------------------------------------- DockerBox: an image that holds the packages


def variant_tag(base: str, names: Sequence[str]) -> str:
    digest = hashlib.sha256(f"{base}\n{' '.join(sorted(names))}".encode()).hexdigest()[:12]
    return f"pickfit-sbx-pkg:{digest}"


def docker_variant(names: Iterable[Any], *, base: str | None = None, platform: str = "linux/amd64",
                   docker: str = "docker", timeout_s: int = INSTALL_TIMEOUT_S,
                   log: Callable[[str], None] = print) -> Installed:
    """The local image for a DockerBox that needs packages: `base` plus the names, after the same checks.

    DockerBox's root filesystem is read-only, so a running box cannot be changed. A throwaway container of `base`
    runs root's script (as root, with the default network, nothing mounted), and is committed as
    `pickfit-sbx-pkg:<hash of base and names>` when something was installed. The result's `image` is the image
    to start the box from: the new one, or `base` when nothing was added. A later call with the same base and
    names reads the result from the image's label.
    """
    began = time.monotonic()
    base = base or sandbox_image_tag()
    requested = tuple(n if isinstance(n, str) else repr(n) for n in names)
    accepted, refused = check_names(requested)
    if not accepted:
        return Installed(requested=requested, refused=refused, image=base)
    tag = variant_tag(base, accepted)
    seen = subprocess.run([docker, "image", "inspect", "--format", '{{index .Config.Labels "pickfit.sysdeps"}}', tag],
                          capture_output=True, text=True, timeout=60)
    if seen.returncode == 0 and seen.stdout.strip():
        try:
            found = json.loads(base64.b64decode(seen.stdout.strip()))
        except ValueError:
            found = None
        if isinstance(found, dict):
            return _result(requested, refused, found, seconds=round(time.monotonic() - began, 1), image=tag)
    name = f"pf-sysdeps-{hashlib.sha256(os.urandom(16)).hexdigest()[:8]}"
    try:
        ran = subprocess.run([docker, "run", "-i", "--name", name, "--platform", platform, "--user", "0", base,
                              PYTHON, "-I", "-S", "-", request(accepted, install_s=max(30, timeout_s - 45))],
                             input=IN_BOX.encode(), capture_output=True, timeout=timeout_s + 60)
        stdout, stderr = ran.stdout.decode(errors="replace"), ran.stderr.decode(errors="replace")
        found = read_result(stdout)
        result = _result(requested, refused, found, seconds=round(time.monotonic() - began, 1),
                         tail=f"{stdout}\n{stderr}", image=base)
        if not result.installed:
            return result
        label = base64.b64encode(json.dumps(found).encode()).decode()
        made = subprocess.run([docker, "commit", "--change", f"LABEL pickfit.sysdeps={label}", "--change",
                               'CMD ["python3"]', name, tag], capture_output=True, text=True, timeout=300)
        if made.returncode != 0:
            return Installed(requested=requested, refused=result.refused, image=base, seconds=result.seconds,
                             error=f"docker commit failed: {made.stderr.strip()[-300:]}")
        log(f"built {tag}: {base} + {', '.join(result.installed)}")
        return Installed(**{**asdict(result), "image": tag})
    except subprocess.TimeoutExpired:
        return Installed(requested=requested, refused=refused, image=base,
                         error=f"the install did not finish in {timeout_s + 60}s",
                         seconds=round(time.monotonic() - began, 1))
    finally:
        subprocess.run([docker, "rm", "-f", name], capture_output=True, timeout=60)


# ---------------------------------------------------------------- one run's boxes


class PackagedBoxes:
    """A box factory whose Linux boxes get the named packages from pickfit, as root, right after they start.

    The agent's box is asked for `names`; what it refuses is logged and the run goes on without it. Every later
    box of the run (the replay's, the one that confirms a failure) is a fresh box asked for exactly what the
    agent's box installed, and fails to start (BoxError) if it does not get all of it: a replay that passed ran
    with the packages the guide will list. `results` holds each role's Installed.
    """

    def __init__(self, make_box: Callable[[str, str], Box], names: Iterable[str], *,
                 timeout_s: int = INSTALL_TIMEOUT_S, log: Callable[[str], None] = print) -> None:
        self.make_box = make_box
        self.names = tuple(names)
        self.timeout_s = timeout_s
        self.log = log
        self.results: dict[str, Installed] = {}

    def wanted(self, role: str) -> tuple[str, ...]:
        first = self.results.get("agent")
        return self.names if role == "agent" or first is None else first.installed

    def __call__(self, run_id: str, role: str) -> Box:
        box = self.make_box(run_id, role)
        if not self.names or box.os != "linux":
            return box
        start = box.start

        def started() -> None:
            wanted = self.wanted(role)
            if isinstance(box, DockerBox):  # a running DockerBox cannot be changed: start it from the image
                if wanted and not box.started:
                    ensure_docker(docker=box.docker, log=box.log)
                    if box.build:
                        ensure_image(box.image, box.platform, docker=box.docker, log=box.log)
                    result = docker_variant(wanted, base=box.image, platform=box.platform, docker=box.docker,
                                            timeout_s=self.timeout_s, log=self.log)
                    box.image = result.image or box.image
                    self._settle(box, role, wanted, result, close=False)
                start()
                return
            start()
            if wanted:
                self._settle(box, role, wanted, install_named(box, wanted, self.timeout_s), close=True)

        box.start = started  # type: ignore[method-assign]
        return box

    def _settle(self, box: Box, role: str, wanted: tuple[str, ...], result: Installed, *, close: bool) -> None:
        self.results[role] = result
        self.log(f"packages ({role} box) · {result.describe()}")
        if role != "agent" and "agent" in self.results and set(result.installed) != set(wanted):
            if close:
                box.close()
            raise BoxError(f"the {role} box did not get the packages the agent's box had "
                           f"({', '.join(wanted)}): {result.describe()}")
        if result.installed:
            describe = box.describe
            note = (f" System packages pickfit installed for this tool, as root: {', '.join(result.installed)} "
                    f"(the install guide will start with `{GUIDE_PREFIX}{' '.join(result.installed)}`; do not "
                    "cite or repeat it as a step of yours).")
            box.describe = lambda: describe() + note  # type: ignore[method-assign]

    def guide_names(self) -> tuple[str, ...]:
        """What the fresh replay box installed: the packages a passed, replayed run is shown to work with."""
        replay = self.results.get("replay")
        return replay.installed if replay is not None else ()


def guide_steps(names: Sequence[str]) -> list[InstallStep]:
    """`sudo apt-get install -y <names>` as install guide steps (more than one when a line would be too long)."""
    steps: list[InstallStep] = []
    line: list[str] = []
    for name in names:
        if line and len(GUIDE_PREFIX) + len(" ".join([*line, name])) > COMMAND_MAX:
            steps.append(InstallStep(command=GUIDE_PREFIX + " ".join(line), purpose=GUIDE_PURPOSE))
            line = []
        line.append(name)
    if line:
        steps.append(InstallStep(command=GUIDE_PREFIX + " ".join(line), purpose=GUIDE_PURPOSE))
    return steps


def with_guide_steps(run: VerificationRun, names: Sequence[str]) -> VerificationRun:
    """`run` with the packages' step first in its steps (which become the install guide). Only a replayed run
    with steps gets it; notes that number an install step are moved along with the steps."""
    added = guide_steps(names)
    if not added or not run.replayed or not run.steps or any(s.command == added[0].command for s in run.steps):
        return run

    def shifted(text: str) -> str:
        return re.sub(r"^install step (\d+)\b", lambda m: f"install step {int(m.group(1)) + len(added)}", text)

    pitfalls = [p.model_copy(update={"readme_said": shifted(p.readme_said)}) for p in run.pitfalls]
    return run.model_copy(update={"steps": [*added, *run.steps], "pitfalls": pitfalls})


def record(run: VerificationRun, make_box: Any, evidence_dir: Path | None = None) -> VerificationRun:
    """After a run: save what each of its boxes was given (sysdeps.json, beside the run's other evidence) and put
    the packages' step first in the run's steps. A factory that is not a PackagedBoxes changes nothing."""
    if not isinstance(make_box, PackagedBoxes) or not make_box.results:
        return run
    if evidence_dir is not None:
        saved = {role: result.to_dict() for role, result in make_box.results.items()}
        (evidence_dir / "sysdeps.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")
    return with_guide_steps(run, make_box.guide_names())


# ---------------------------------------------------------------- which packages, from what is already known

_PROSE = frozenset("a an and are as at by for from if in is it of on or so the then to via when with you your".split())
_APT_LINE = re.compile(r"\bapt(?:-get)?\s+(?:-\S+\s+)*install\b([^\n;&|`#]*)", re.I)
# A record's "system packages" are prose more often than package names. What a word means in Debian, for the
# words records use most (counted in data/software 2026-11-21) and the usual command-line helpers.
ALIASES = {
    "ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "poppler": "poppler-utils", "pdftotext": "poppler-utils",
    "pdftoppm": "poppler-utils", "tesseract": "tesseract-ocr", "imagemagick": "imagemagick",
    "graphviz": "graphviz", "ghostscript": "ghostscript", "sqlite": "sqlite3", "sqlite3": "sqlite3", "jq": "jq",
    "fzf": "fzf", "ripgrep": "ripgrep", "rg": "ripgrep", "tmux": "tmux", "pandoc": "pandoc", "xclip": "xclip",
    "xsel": "xsel", "xdg-open": "xdg-utils", "git-lfs": "git-lfs", "rsync": "rsync", "socat": "socat",
    "bubblewrap": "bubblewrap", "bwrap": "bubblewrap", "portaudio": "libportaudio2", "libsndfile": "libsndfile1",
    "libmagic": "libmagic1", "exiftool": "libimage-exiftool-perl", "7z": "7zip", "p7zip": "7zip",
    "espeak": "espeak-ng", "espeak-ng": "espeak-ng", "mpv": "mpv", "sox": "sox", "chromium": "chromium",
    "ping": "iputils-ping", "traceroute": "traceroute", "dig": "bind9-dnsutils", "nmap": "nmap",
    "ssh": "openssh-client", "ttyd": "ttyd", "ocl-icd": "ocl-icd-opencl-dev", "opencl": "ocl-icd-opencl-dev",
}
# What the box already has by other means, or what another kind of box gives (the toolchain box, the services
# box): never worth an `apt-get install` step in a guide.
_HAVE = frozenset({"python", "python3", "python3-pip", "python3-venv", "pip", "nodejs", "node", "npm", "git", "curl",
                   "ca-certificates", "unzip", "tar", "xz-utils", "zstd", "bzip2", "uv", "pipx", "bash", "coreutils"})
_PKG_SHAPE = re.compile(r"^(?:lib[a-z0-9+.-]+|[a-z0-9][a-z0-9+.-]*-(?:dev|utils|tools|bin|data|common|runtime))$")
_SHARED_LIB = re.compile(r"\b(lib[A-Za-z0-9_+.-]+?)\.so(?:\.(\d+))?(?:[.\d]*)?:\s*cannot open shared object file")
_SONAME_ALIASES = {"libGL.so.1": "libgl1", "libEGL.so.1": "libegl1", "libglib-2.0.so.0": "libglib2.0-0",
                   "libgobject-2.0.so.0": "libglib2.0-0", "libgio-2.0.so.0": "libglib2.0-0",
                   "libgthread-2.0.so.0": "libglib2.0-0", "libasound.so.2": "libasound2", "libnss3.so": "libnss3",
                   "libgtk-3.so.0": "libgtk-3-0", "libX11.so.6": "libx11-6", "libXext.so.6": "libxext6",
                   "libSM.so.6": "libsm6", "libXrender.so.1": "libxrender1", "libstdc++.so.6": "libstdc++6",
                   "libportaudio.so.2": "libportaudio2", "libsndfile.so.1": "libsndfile1"}
_PKG_CONFIG = re.compile(r"(?:Package '?([\w+.-]+)'?,? (?:was not found|required by)|No package '([\w+.-]+)' found|"
                         r"Package ([\w+.-]+) was not found in the pkg-config search path)")
_PC_ALIASES = {"gtk+-3.0": "libgtk-3-dev", "gtk4": "libgtk-4-dev", "glib-2.0": "libglib2.0-dev",
               "webkit2gtk-4.1": "libwebkit2gtk-4.1-dev", "webkit2gtk-4.0": "libwebkit2gtk-4.0-dev",
               "javascriptcoregtk-4.1": "libjavascriptcoregtk-4.1-dev", "libsoup-3.0": "libsoup-3.0-dev",
               "alsa": "libasound2-dev", "openssl": "libssl-dev", "libudev": "libudev-dev", "dbus-1": "libdbus-1-dev",
               "librsvg-2.0": "librsvg2-dev", "ayatana-appindicator3-0.1": "libayatana-appindicator3-dev",
               "appindicator3-0.1": "libayatana-appindicator3-dev", "x11": "libx11-dev", "xcb": "libxcb1-dev",
               "xkbcommon": "libxkbcommon-dev", "fontconfig": "libfontconfig-dev", "freetype2": "libfreetype-dev",
               "libpulse": "libpulse-dev", "sqlite3": "libsqlite3-dev", "zlib": "zlib1g-dev",
               "libusb-1.0": "libusb-1.0-0-dev",
               "OpenCL": "ocl-icd-opencl-dev", "libpq": "libpq-dev", "pango": "libpango1.0-dev",
               "cairo": "libcairo2-dev", "gdk-pixbuf-2.0": "libgdk-pixbuf-2.0-dev", "atk": "libatk1.0-dev"}


def enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "").strip() != "0"


def apt_names(text: str) -> list[str]:
    """The package names of every `apt install` / `apt-get install` command line in `text`, in order."""
    names: list[str] = []
    for match in _APT_LINE.finditer(text or ""):
        for word in match.group(1).replace("\\", " ").split():
            if word.startswith("-"):
                continue
            if word.lower() in _PROSE:
                break
            if refusal(word) is None or (NAME.match(word) and FULL_MACHINE.match(word)):
                names.append(word)
            else:
                break  # the command line ended (prose, a redirect, another command)
    return names


def soname_package(soname: str) -> str | None:
    """Debian's name for the package of a shared library, by its naming rule (libfoo.so.1 -> libfoo1,
    libfoo-2.so.0 -> libfoo-2-0); apt then says whether there is one."""
    if soname in _SONAME_ALIASES:
        return _SONAME_ALIASES[soname]
    match = re.match(r"^(lib[A-Za-z0-9_+.-]+?)\.so(?:\.(\d+))?", soname)
    if not match:
        return None
    stem, major = match.group(1).lower().replace("_", "-"), match.group(2) or ""
    name = f"{stem}-{major}" if stem[-1].isdigit() and major else f"{stem}{major}"
    return name if refusal(name) is None else None


def failure_names(text: str | None) -> list[str]:
    """Package names an error names: an `apt-get install` it suggests, a shared library that did not load, a
    pkg-config module that was not found."""
    text = text or ""
    names = apt_names(text)
    for match in _SHARED_LIB.finditer(text):
        soname = match.group(0).split(":", 1)[0].strip()
        guess = soname_package(soname)
        if guess:
            names.append(guess)
    for match in _PKG_CONFIG.finditer(text):
        module = next(g for g in match.groups() if g)
        guess = _PC_ALIASES.get(module) or _PC_ALIASES.get(module.lower())
        if guess:
            names.append(guess)
    return names


def _words(value: str) -> list[str]:
    """Package names in one "system packages" entry of an extraction: an exact name, a known word, or several
    names in a row; prose gives nothing."""
    text = re.sub(r"\([^)]*\)", " ", value)
    text = re.sub(r"\s*(?:>=|<=|==|>|<|=)\s*[\w.]+\+?|\s+v?\d[\w.]*\+?(?=\s|$)", " ", text).strip()
    tokens = [t.strip(",;:") for t in text.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    if len(tokens) == 1:
        word = tokens[0].lower()
        if word in ALIASES:
            return [ALIASES[word]]
        return [word] if refusal(word) is None or FULL_MACHINE.match(word) else []
    found = []
    for token in tokens:
        word = token.lower()
        if word in ALIASES:
            found.append(ALIASES[word])
        elif token == word and _PKG_SHAPE.match(word):
            found.append(word)
    return found


def planned_names(ex: Any, *, readme: str | None = None, earlier_reason: str | None = None,
                  earlier_error: str | None = None, own_names: Iterable[str] = ()) -> tuple[str, ...]:
    """The distribution packages to give a record's boxes before the agent starts, from what is already known.

    Always: the extraction's system packages (a package name, a word ALIASES knows, or the names in the
    `apt-get install` line it quotes) and the `apt-get install` lines of its manual steps. After an attempt that
    ended needs_root (earlier_reason): also the README's own `apt-get install` lines and what that attempt's
    error names (earlier_error). Never the tool itself (own_names: its slug and name), what the box already has,
    or more than MAX_PLANNED names. Nothing here decides that a name exists: apt does, in the box.
    """
    names: list[str] = []
    pre = getattr(ex, "prerequisites", None)
    for item in getattr(pre, "system_packages", None) or []:
        quoted = apt_names(getattr(item, "quote", None) or "")
        names += quoted or _words(str(getattr(item, "value", "") or ""))
    for item in getattr(ex, "manual_steps", None) or []:
        names += apt_names(f"{getattr(item, 'value', '') or ''}\n{getattr(item, 'quote', '') or ''}")
    if earlier_reason == "needs_root":
        names += failure_names(earlier_error)
        names += apt_names(readme or "")
    own = {str(n).lower() for n in own_names if n}
    kept: list[str] = []
    for name in names:
        if name in kept or name in _HAVE or name in own:
            continue
        kept.append(name)
    return tuple(kept[:MAX_PLANNED])


def earlier_attempt(data_dir: Path | str | None, slug: str) -> tuple[str | None, str | None]:
    """(reason, error) of the record's latest Linux sandbox run when it stopped for a lack the box has: the run's
    unverified_reason, or needs_root when one of its features was not checked for that. (None, None) otherwise."""
    if data_dir is None:
        return None, None
    try:
        data = json.loads((Path(data_dir) / f"{slug}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    runs = [r for r in ((data.get("verification") or {}).get("runs") or [])
            if isinstance(r, dict) and r.get("os") == "linux" and r.get("method") == "sandbox"]
    if not runs:
        return None, None
    last = runs[-1]
    reason = last.get("unverified_reason")
    if reason is None and any(isinstance(f, dict) and f.get("reason") == "needs_root"
                              for f in last.get("features") or []):
        reason = "needs_root"
    return reason, last.get("blocking_error")


# ---------------------------------------------------------------- a probe, for a provider nobody has tried yet


def probe(make_box: Callable[[str, str], Box], names: Sequence[str], log: Callable[[str], None] = print) -> bool:
    """Start one box, install `names` as root, and show the box user what it got and what it still cannot do.
    Costs a box for about a minute. True when every name was installed and the box user could not undo it."""
    box = make_box("sysdeps-probe", "probe")
    try:
        box.start()
        result = install_named(box, names, log=log)
        log(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if not result.installed:
            return False
        checks = "; ".join(f"dpkg -s {shlex.quote(n)} 2>&1 | grep -m1 Status" for n in result.installed)
        seen = box.exec(f"id -u; {checks}; apt-get remove -y {shlex.quote(result.installed[0])} 2>&1 | tail -n 1; "
                        "touch /var/lib/dpkg/status 2>&1; echo probe-done", 60)
        log(seen.stdout.strip())
        held = seen.stdout.count("install ok installed") == len(result.installed) and "probe-done" in seen.stdout \
            and ("Permission denied" in seen.stdout or "are you root" in seen.stdout)
        log(f"probe · {box.runner} · {'held' if held and result.ok else 'NOT as expected'}")
        return held and result.ok
    finally:
        box.close()


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    from pickfit.verify.cli import box_factory

    parser = argparse.ArgumentParser(prog="python -m pickfit.verify.sysdeps",
                                     description="Start one box and have pickfit install named Debian packages in it.")
    parser.add_argument("names", nargs="+", help="package names, e.g. jq libxcb1")
    parser.add_argument("--runner", choices=["modal", "ec2"], default="modal")
    parser.add_argument("--runtime", choices=["gvisor", "vm"], default="gvisor")
    args = parser.parse_args(argv)
    return 0 if probe(box_factory(args.runner, 600, runtime=args.runtime), args.names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
