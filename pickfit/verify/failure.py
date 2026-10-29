"""Runs that did not pass: whose fault it is. No model call.

A sandbox run is failed only on structural evidence about the installed package itself, which no
limit of the box can produce (structural_defect): a fresh box reruns the cited install steps, then a
probe reads the package's own metadata and finds that its console script's module is not installed
(Python: entry_points and RECORD, plus the import system's finders), or that its npm bin file is not
in a package with no install scripts. The probe runs only when the agent claims failed, every cited
install step succeeded, and the failing command is the tool's own (tool_command), with no box limit
in its error tail.

Runtime errors alone do not make a run failed: a box limit can look like any exception. When the
failing command shows an error of the tool's code (own_error) but no structural defect, the run is
unverified "suspected_tool_fault", with the command, its exit code and its error tail as evidence
for a human check or another environment. A specific box reason comes from the error tail
(output_limit: no compiler, root, Docker, CUDA, memory, disk, an account) or, when the log names no
failing command and no check passed, from the agent's description (box_reason); "other" otherwise.

- sandbox_only() and cited_workarounds(): a command that only works around the box (a shim for
  nvidia-smi, a fake docker) is not part of a user's install, so a run that cites one, as a step,
  a setup, a check or the failing command, neither passes nor fails.
- WRITTEN_REASONS: the unverified reasons worth writing back to a record; "other",
  "budget_exceeded" and "not_run" say nothing about the software.
"""

from __future__ import annotations

import json
import re
import shlex
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, get_args

from pickfit.schema import UnverifiedReason
from pickfit.verify.box import Box, BoxError
from pickfit.verify.replay import RanCommand, ReplayCommand, Replayer
from pickfit.verify.verdict import masked_exit

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord
    from pickfit.verify.task import VerifyTask
    from pickfit.verify.verdict import LogVerdict

WRITTEN_REASONS: frozenset[str] = frozenset(get_args(UnverifiedReason.__value__)) - {
    "not_run", "budget_exceeded", "other"}

# What a box limit prints at the end of a failing command. The box has no compiler, Rust or Go, no
# root, no Docker daemon, no system packages beyond its image, 2 GiB of memory (Node's heap stops
# near 1 GiB) and a time limit per command. Only the error tail is read (error_tail), so a warning
# early in the output ("No GPU detected, falling back to CPU") does not decide.
_TOOLCHAIN = r"(?:rustc|rustup|cargo|go|gcc|cc|g\+\+|c\+\+|clang|make|cmake|javac|java|mvn|gradle|dotnet|zig|pkg-config)"
_ENGINE = r"(?:docker|podman)"


def _missing(names: str) -> str:
    """The ways a missing executable shows up: shell, Python, Node, Go, node-gyp."""
    return (rf"\b{names}(?::| is)? (?:command )?not (?:found|installed)|\b{names}\b[^\n]{{0,60}}\bis not installed"
            rf"|not found: {names}\b|spawn {names} ENOENT|exec: \"{names}\": executable file not found"
            rf"|no such file or directory: '{names}'")


_OUTPUT_LIMITS: list[tuple[str, re.Pattern[str]]] = [
    ("needs_container", re.compile(
        rf"cannot connect to the docker daemon|docker\.sock|neither docker nor podman|no container (?:engine|runtime)"
        rf"|{_missing(_ENGINE)}", re.I)),
    ("needs_gpu", re.compile(
        r"libcuda\.so[^\n]{0,60}(?:cannot open|not found)|cuda driver version is insufficient|no cuda-capable device"
        r"|found no nvidia driver|nvidia-smi has failed|not compiled with cuda|" + _missing(r"nvidia-smi"), re.I)),
    ("needs_root", re.compile(
        r"are you root\?|must be run as root|requires? root|run (?:it )?with sudo|\bsudo: |system has not been booted"
        r" with systemd|failed to connect to bus|read-only file system|kernel[- ]header|linux/\w+\.h: no such file"
        r"|permission denied[^\n]{0,60}['\"\s]/(?:usr|etc|var|opt|lib|boot|sys)/"
        r"|['\"]/(?:usr|etc|var|opt|lib)/[^'\"\n]*['\"]: permission denied"
        r"|lib[\w.+-]+\.so(?:\.\d+)*: cannot open shared object file", re.I)),
    ("needs_toolchain", re.compile(
        rf"{_missing(_TOOLCHAIN)}|can't find rust compiler|command '(?:[\w-]*-)?(?:gcc|cc|g\+\+|c\+\+)' failed"
        r"|unable to execute '(?:gcc|cc)'|(?:linker|compiler) [`'\"]?(?:cc|gcc)[`'\"]? not found"
        r"|please install (?:rust|go|a c compiler|gcc)"
        r"|\b(?:rust|rustc|cargo|golang|go toolchain|go 1\.\d+)\b[^\n]{0,30}\b(?:is )?(?:required|not found|missing)",
        re.I)),
    ("needs_account", re.compile(
        r"(?:api[_ -]?key|access token|auth token|credentials?)\b[^\n]{0,40}\b(?:missing|not set|not found"
        r"|required|invalid)|\b401\b[^\n]{0,20}unauthori[sz]ed|\b403\b[^\n]{0,20}forbidden|not logged in"
        r"|please (?:log ?in|sign in)|KeyError: '[A-Z_]*(?:API_KEY|TOKEN|SECRET)[A-Z_]*'", re.I)),
    ("needs_more_resources", re.compile(
        r"heap out of memory|reached heap limit|cannot allocate memory|\bmemoryerror\b|out of memory"
        r"|no space left on device|disk quota exceeded|file size limit exceeded", re.I)),
]

# An error of the tool's own code: what a fresh box cannot blame on itself once every install step
# succeeded (a wheel with no code, a module the package forgot, a typo in the tool).
_TOOL_ERROR = re.compile(
    r"^\s*(?:ModuleNotFoundError|ImportError|AttributeError|NameError|SyntaxError|IndentationError|TabError"
    r"|UnboundLocalError|TypeError|KeyError|IndexError|RecursionError|NotImplementedError|ZeroDivisionError)\b"
    r"|^\s*(?:Uncaught )?(?:ReferenceError|RangeError): |Error: Cannot find module|ERR_MODULE_NOT_FOUND"
    r"|ERR_PACKAGE_PATH_NOT_EXPORTED|ERR_REQUIRE_ESM", re.M)

# A command that installs or fetches, rather than runs the tool.
_INSTALLS = re.compile(
    r"\b(?:pip3?|pipx|uv|npm|pnpm|yarn|bun|cargo|go|gem|brew|apt(?:-get)?|conda|mamba|poetry|hatch|maturin)\s+"
    r"(?:\S+\s+)?(?:install|add|i|build|sync|global|get|binstall)\b|\bgit\s+clone\b|\bc?make\b"
    r"|\b(?:install|setup|bootstrap)\.(?:sh|py|ps1)\b|setup\.py|-m (?:pip|venv|ensurepip)\b|\bnpx\b"
    r"|\b(?:curl|wget)\b|\btar\s+-?\w*x|\bunzip\b|\bdeno\s+install\b")


_WARNING = re.compile(r"(?i:\bwarn(?:ing)?s?\b)|(?:^|:\s)W(?:\d{4}\b|\s+[\w.]+/)")  # WARNING, glog's W1029, TF's W x/


def error_tail(stdout: str, stderr: str, lines: int = 30) -> str:
    """The last lines a failing command printed, warnings left out: the end of stderr, then of stdout."""
    def last(text: str, n: int) -> list[str]:
        return [line for line in text.splitlines() if line.strip() and not _WARNING.search(line)][-n:]
    return "\n".join(last(stderr, lines) + last(stdout, lines // 3))


def output_limit(stdout: str, stderr: str, exit_code: int | None, timed_out: bool) -> str | None:
    """The UnverifiedReason when the end of a failing command's output shows a limit of the box.

    60 lines: a build failure prints its error, then a traceback or a page of hints (pip, uv, npm).
    """
    if exit_code == 137 and not timed_out:  # killed: out of memory (a timeout alone says nothing)
        return "needs_more_resources"
    tail = error_tail(stdout, stderr, 60)
    return next((reason for reason, pattern in _OUTPUT_LIMITS if pattern.search(tail)), None)


def own_error(failing: CommandRecord | RanCommand) -> tuple[str | None, str]:
    """(the tool's own error, "") when the failing command's error tail shows one and no box limit,
    else (None, why not)."""
    cid = failing.command_id
    limit = output_limit(failing.stdout, failing.stderr, failing.exit_code, failing.timed_out)
    if limit:
        return None, f"command {cid} hit a limit of the box ({limit})"
    tail = error_tail(failing.stdout, failing.stderr)
    found = _TOOL_ERROR.search(tail)
    if not found:
        return None, f"command {cid} shows no error of the tool's own code"
    line = tail[tail.rfind("\n", 0, found.start()) + 1:].split("\n", 1)[0]
    return " ".join(line.split())[:160], ""


def tool_command(verdict: dict[str, Any], commands: list[CommandRecord]) -> tuple[CommandRecord | None, str]:
    """The failing command when it is the tool's own, run after every cited install step succeeded;
    else (None, why not)."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    fid = verdict.get("failing_id")
    failing = by_id.get(fid) if fid is not None else None
    if failing is None:
        return None, "the log names no failing command"
    if failing.tool != "run_command":
        return None, f"command {fid} is not a run_command"
    steps = [by_id[i] for i in verdict.get("step_ids") or [] if i in by_id]
    if not steps:
        return None, "no install step ran before it"
    for step in steps:
        if step.exit_code != 0 or step.timed_out or masked_exit(step.command):
            return None, f"install step {step.command_id} did not succeed"
    if fid <= max(step.command_id for step in steps):
        return None, f"command {fid} ran before the install finished"
    if _INSTALLS.search(failing.command):
        return None, f"command {fid} installs or fetches; it is not the tool's own command"
    return failing, ""


# How an agent describes a box limit: a need, not a mention ("needs Rust 1.91+", "no root to install
# linux-headers", "neither docker nor podman", "aborts in V8 (exit 134)").
_NEED = r"(?:no|neither|nor|without|needs?|requires?|required|absent|missing|forbidden|unavailable)"
_PROSE_LIMITS: list[tuple[str, re.Pattern[str]]] = [
    ("needs_container", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,30}}\b(?:docker|podman|container (?:engine|runtime))\b"
        r"|\b(?:docker|podman)\b[^.;]{0,20}\b(?:not (?:available|installed|present)|unavailable|missing|absent)\b",
        re.I)),
    ("needs_root", re.compile(
        r"\bkernel[- ]headers?\b|\blinux-headers\b|\b(?:no|without|needs?|requires?|requiring)\s+(?:root|sudo"
        r"|superuser)\b|\bas root\b|\broot (?:access|privileges?|permissions?)\b"
        rf"|\b{_NEED}\b[^.;]{{0,20}}\b(?:apt(?:-get)? install|dpkg|systemd)\b", re.I)),
    ("needs_toolchain", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,25}}\b(?:rust(?:c|up)?|cargo|go(?:lang)? ?(?:1\.\d+|toolchain)|toolchain"
        r"|jdk|dotnet|\.net sdk|zig|a c compiler|gcc)\b"
        r"|\b(?:rust(?:c|up)?|cargo|golang|toolchain)\b[^.;]{0,40}\b(?:absent|missing|not (?:available|installed)"
        r"|forbidden)\b", re.I)),
    ("needs_gpu", re.compile(rf"\b{_NEED}\b[^.;]{{0,30}}\b(?:a |an )?(?:gpu|cuda|nvidia)\b", re.I)),
    ("needs_more_resources", re.compile(
        r"heap (?:limit|out of memory)|out of memory|\boom\b|\bv8\b[^.;]{0,30}\babort|abort[^.;]{0,30}\bv8\b"
        r"|no space left|disk (?:is )?full|ran out of (?:memory|disk)", re.I)),
]
# Quoted text, code spans and import errors name things; they are not the box's limits. An apostrophe
# inside a word ("tool's", "can't") is not a quote.
_MENTIONS = re.compile(r"`[^`\n]*`|(?<!\w)'[^'\n]{1,120}'(?!\w)|\"[^\"\n]{0,120}\""
                       r"|(?:ModuleNotFoundError|ImportError)[^.;]*", re.I)
# A need denied is no need: "no GPU needed", "works without Docker", "does not require root".
_NEGATED = re.compile(r"\b(?:no|not|without|never)\b[^.;,()]{0,30}\b(?:needed|required|necessary|involved|used)\b"
                      r"|\b(?:does|do|did|is|are)(?: not|n't) (?:need|require|use)s?\b[^.;,()]{0,30}"
                      r"|\bworks? (?:fine )?without\b[^.;,()]{0,30}", re.I)


def box_reason(text: str | None) -> str | None:
    """The UnverifiedReason when an agent's description of a failure states a need the box cannot meet."""
    plain = _NEGATED.sub(" ", _MENTIONS.sub(" ", text or ""))
    return next((reason for reason, pattern in _PROSE_LIMITS if pattern.search(plain)), None)


def failure_reason(verdict: dict[str, Any], commands: list[CommandRecord], blocking_error: str | None
                   ) -> str | None:
    """The specific UnverifiedReason for a failed claim that is not the tool's proven fault, or None.

    The failing command's error tail in the agent's log decides when the log names one. Without one, the agent's description does, unless a check passed: then the tool ran, and no
    box limit stopped it.
    """
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    fid = verdict.get("failing_id")
    failing = by_id.get(fid) if fid is not None else None
    if failing is not None:
        return output_limit(failing.stdout, failing.stderr, failing.exit_code, failing.timed_out)
    if any(c.get("passed") for c in verdict.get("checks") or []):
        return None
    return box_reason(blocking_error)


# A file named like a system command, written or linked into a directory on PATH: a user bin
# directory of the box, or one the command itself puts on PATH.
_FAKED = re.compile(r"(?:nvidia-smi|rocm-smi|nvcc|lspci|docker|podman|sudo|systemctl|journalctl|uname"
                    r"|lsb_release|apt-get|apt|dpkg)")
_USER_BIN = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/home/[^/\s'\"]+)/(?:\.local/bin|\.cargo/bin|go/bin|bin)/?")
_REDIRECT = re.compile(r"(?:^|[^<&\d])(?:\d?>>?|&>)\s*(?P<path>[^\s;&|<>]+)")
_TEE = re.compile(r"\btee\s+(?:-a\s+)?(?P<path>[^\s;&|<>]+)")
_DOWNLOAD = re.compile(r"(?:^|\s)(?:-\w*[oO]|--output(?:-document)?)(?:\s+|=)(?P<path>[^\s;&|<>]+)")
_COPY = re.compile(r"(?:^|[;&|(]\s*|\n)\s*(?:ln|cp|mv|install)\b(?P<args>[^;&|\n<>]*)")
_PATH_DIR = re.compile(r"\bPATH=[\"']?(?P<dir>[^\s:\"']+):")
_CD = re.compile(r"\bcd\s+(?P<dir>[^\s;&|]+)")
_SANDBOX_PURPOSE = re.compile(
    rf"\b(?:sandbox|box)[- ]only\b|\bonly (?:for|in|inside) (?:the |this )?(?:sandbox|box)\b|\bgvisor\b"
    rf"|\bwork(?:s|ed|ing)?[- ]?around (?:the |this )?(?:box|sandbox)\b"
    rf"|\b(?:shim|fake|stub|mock)\b[^.;]{{0,30}}\b{_FAKED.pattern}\b"
    rf"|\b{_FAKED.pattern}\b[^.;]{{0,30}}\b(?:shim|fake|stub|mock)\b", re.I)


def _written(command: str) -> list[str]:
    """Paths the command writes: redirects, tee, curl/wget output, the destination of ln/cp/mv/install."""
    paths = [m.group("path") for pattern in (_REDIRECT, _TEE, _DOWNLOAD) for m in pattern.finditer(command)]
    for m in _COPY.finditer(command):
        args = [a for a in m.group("args").split() if not a.startswith("-")]
        if len(args) >= 2:
            paths.append(args[-1])
    return [p.strip("'\"") for p in paths]


def sandbox_only(command: str, purpose: str | None = None) -> str | None:
    """Why a command only works around the box (it fakes a system command, or says so), else None."""
    on_path = {d.rstrip("/") for d in _PATH_DIR.findall(command)}
    in_bin = any(_USER_BIN.fullmatch(d) for d in _CD.findall(command))
    for path in _written(command):
        folder, _, name = path.rpartition("/")
        if not _FAKED.fullmatch(name):
            continue
        if (folder and (_USER_BIN.fullmatch(folder) or folder.rstrip("/") in on_path)) or (not folder and in_bin):
            return f"it replaces the system command {name}"
    if purpose and _SANDBOX_PURPOSE.search(purpose):
        return f"its purpose says so ({' '.join(purpose.split())[:80]})"
    return None


def cited_workarounds(verdict: dict[str, Any], commands: list[CommandRecord],
                      step_purposes: dict[int, str | None] | None = None) -> list[str]:
    """Every cited command (step, check setup, check, failing command) that only works around the box."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    roles: dict[int, str] = {}
    for check in verdict.get("checks") or []:
        roles.setdefault(check["command_id"], "check")
        for sid in check.get("setup_ids") or []:
            roles.setdefault(sid, "setup")
    for sid in verdict.get("step_ids") or []:
        roles[sid] = "step"
    if verdict.get("failing_id") is not None:
        roles.setdefault(verdict["failing_id"], "failing command")
    found = []
    for cid, role in sorted(roles.items()):
        record = by_id.get(cid)
        cited = (step_purposes or {}).get(cid) if role == "step" else None
        purpose = " / ".join(p for p in (cited, record.purpose if record else None) if p) or None
        why = sandbox_only(record.command, purpose) if record else None
        if why:
            found.append(f"{role} {cid} only works around the box: {why}")
    return found


# ---------------------------------------------------------------- the package's own structure

# Run in the box by its python3 after the install steps: which installed package provides the
# failing executable, and does that package hold what its metadata names? It reads metadata and the
# import system's finders, and runs none of the tool's code.
_PROBE = r'''
import glob, json, os, re, shutil, subprocess, sys, tempfile
INNER = """
import importlib.metadata as md, importlib.util, json, sys
name = sys.argv[1]
for dist in md.distributions():
    for ep in dist.entry_points:
        if ep.group in ("console_scripts", "gui_scripts") and ep.name == name:
            top = ep.value.split(":")[0].split(".")[0].strip()
            files = [str(f).replace(chr(92), "/") for f in dist.files or []]
            print(json.dumps({"kind": "python", "dist": dist.metadata["Name"], "version": dist.version,
                              "entry_point": ep.value, "module": top,
                              "in_files": any(f == top + ".py" or f.startswith(top + "/") or (f.startswith(top + ".")
                                              and f.endswith((".so", ".pyd"))) for f in files),
                              "importable": importlib.util.find_spec(top) is not None,
                              "source": "direct" if dist.read_text("direct_url.json") else "index"}))
            sys.exit(0)
print(json.dumps({"kind": "python", "dist": None}))
"""
name = sys.argv[1]
exe = os.path.expanduser(name) if "/" in name else shutil.which(name)
if exe and os.path.isfile(exe):
    head = open(exe, "rb").read(512).decode("utf-8", "replace")
    m = re.search(r"exec' \"([^\"]+)\"", head) or re.match(r"#!\s*(?:\S*/env\s+)?(\S+)", head)
    interp = m.group(1) if m else ""
    if "python" in os.path.basename(interp):
        r = subprocess.run([interp, "-c", INNER, os.path.basename(exe)], cwd=tempfile.mkdtemp(),
                           capture_output=True, text=True, timeout=60)
        lines = r.stdout.strip().splitlines()
        print(lines[-1] if lines else json.dumps({"kind": "python", "error": r.stderr[-200:]}))
        sys.exit(0)
base = os.path.basename(name)
root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
for pj in sorted(glob.glob(os.path.join(root, "*", "package.json")) + glob.glob(os.path.join(root, "@*", "*", "package.json"))) if root else []:
    try:
        data = json.load(open(pj))
    except Exception:
        continue
    bins = data.get("bin") or {}
    if isinstance(bins, str):
        bins = {str(data.get("name", "")).split("/")[-1]: bins}
    if base in bins:
        scripts = data.get("scripts") or {}
        print(json.dumps({"kind": "npm", "package": data.get("name"), "version": data.get("version"), "bin": bins[base],
                          "exists": os.path.exists(os.path.join(os.path.dirname(pj), bins[base])),
                          "install_scripts": sorted(k for k in scripts if k in ("preinstall", "install", "postinstall"))}))
        sys.exit(0)
print(json.dumps({"kind": "unknown", "exe": exe}))
'''


def executable(command: str) -> str | None:
    """The program a command runs last: the first word of its last `&&`/`;` part, before any pipe."""
    part = re.split(r"&&|\|\||;|\n", command)[-1].split("|")[0].strip()
    try:
        words = shlex.split(part)
    except ValueError:
        words = part.split()
    words = [w for w in words if not re.match(r"^\w+=", w)]
    while words and words[0] in ("env", "exec", "command", "time", "nohup"):
        words = words[1:]
    return words[0] if words else None


def structure_probe(command: str) -> str | None:
    """The box command that reads the structure of the package behind a failing command, or None."""
    program = executable(command)
    return f"python3 - {shlex.quote(program)} <<'PICKFIT_PROBE'\n{_PROBE}\nPICKFIT_PROBE" if program else None


def parse_structure(stdout: str) -> dict[str, Any] | None:
    lines = [line for line in stdout.splitlines() if line.startswith("{")]
    try:
        return json.loads(lines[-1]) if lines else None
    except ValueError:
        return None


def structural_defect(structure: dict[str, Any] | None) -> str | None:
    """Evidence that the installed package lacks what its own metadata names, or None."""
    if not structure:
        return None
    if structure.get("kind") == "python" and structure.get("dist") and not structure.get("in_files") \
            and not structure.get("importable"):
        source = "a local or VCS source" if structure.get("source") == "direct" else "the package index"
        return (f"the installed {structure['dist']} {structure.get('version')} (from {source}) declares the console "
                f"script {structure.get('entry_point')}, and no module {structure.get('module')} is installed")
    if structure.get("kind") == "npm" and structure.get("exists") is False and not structure.get("install_scripts"):
        return (f"the installed npm package {structure.get('package')} {structure.get('version')} names bin "
                f"{structure.get('bin')}, and the package has no such file")
    return None


# ---------------------------------------------------------------- confirming a failure


@dataclass(frozen=True)
class FailurePlan:
    steps: tuple[ReplayCommand, ...]  # the cited steps that ran before the failure
    setups: tuple[ReplayCommand, ...]  # what the failing check needed first
    failing: ReplayCommand
    exit_code: int | None  # as the agent saw it
    timed_out: bool
    probe: str | None = None  # structure_probe() for the failing command

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def failure_plan(verdict: LogVerdict, commands: list[CommandRecord]) -> FailurePlan | None:
    """What to rerun to see the failure again, or None when the log names no failing command."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    failing = by_id.get(verdict.failing_id) if verdict.failing_id is not None else None
    if failing is None:
        return None

    def command(cid: int) -> ReplayCommand:
        c = by_id[cid]
        return ReplayCommand(cid, c.tool, c.command, c.port, c.wait_s, c.seconds)

    fid = failing.command_id
    steps = [i for i in verdict.step_ids if i < fid]
    check = next((c for c in verdict.checks if c.command_id == fid), None)
    setups = [i for i in (check.setup_ids if check else []) if i < fid and i not in steps and i in by_id]
    return FailurePlan(steps=tuple(command(i) for i in steps), setups=tuple(command(i) for i in setups),
                       failing=command(fid), exit_code=failing.exit_code, timed_out=failing.timed_out,
                       probe=structure_probe(failing.command))


@dataclass
class FailureCheck:
    reproduced: bool
    steps: list[RanCommand] = field(default_factory=list)
    failing: RanCommand | None = None
    error: str | None = None  # why it did not reproduce
    structure: dict[str, Any] | None = None  # parse_structure() of the probe, run after every step succeeded
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confirm_failure(box: Box, plan: FailurePlan, task: VerifyTask, *,
                    log: Callable[[str], None] = print) -> FailureCheck:
    """Rerun the plan in one fresh, started box, with the network on: the steps, the failing command
    (exit codes decide whether it repeated), then the structure probe."""
    began = time.monotonic()
    result = FailureCheck(reproduced=False)
    replayer = Replayer(box, log=log)
    try:
        box.set_network(True)
        box.write_file("README.md", task.readme)
        for name, content in task.files.items():
            box.write_file(name, content)
        for step in (*plan.steps, *plan.setups):
            ran = replayer.rerun(step)
            result.steps.append(ran)
            if not ran.ok:
                result.error = f"command {step.command_id} exited {ran.exit_code} before the failing command"
                break
        else:
            ran = replayer.rerun(plan.failing)
            result.failing = ran
            if plan.timed_out and ran.timed_out:
                result.reproduced = True
            elif ran.ok:
                result.error = f"command {plan.failing.command_id} passed in a fresh box"
            elif (ran.exit_code, ran.timed_out) != (plan.exit_code, plan.timed_out):
                was = "a timeout" if plan.timed_out else f"exit {plan.exit_code}"
                now = "a timeout" if ran.timed_out else f"exit {ran.exit_code}"
                result.error = f"command {plan.failing.command_id} failed differently ({now}, was {was})"
            else:
                result.reproduced = True
            if plan.probe:
                probe = box.exec(plan.probe, 120)
                result.structure = parse_structure(probe.stdout) or {"kind": "error", "exit": probe.exit_code,
                                                                     "stderr": probe.stderr[-300:]}
                log(f"  structure: {result.structure}")
    except BoxError as err:
        result.error = f"box error: {err}"
    result.seconds = round(time.monotonic() - began, 1)
    said = "repeated" if result.reproduced else f"not repeated ({result.error})"
    log(f"  failure {said} · {result.seconds:.0f}s")
    return result
