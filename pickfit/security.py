"""Known vulnerabilities in what a fresh install brings (record field security, sec.v1; 念誠 11/3).

No model call and no paid API. Per record:

1. Resolve the dependencies the way a person installing it today gets them:
   - a registry package (npm, PyPI, crates: from pickfit's own install steps, else the packages that link back to the
     repository): `npm install --package-lock-only --ignore-scripts` and `uv pip compile --no-build` (neither runs
     package code), crates through deps.dev's dependency graph;
   - otherwise the repository (a shallow clone, only read as data): package-lock.json without dev entries, Cargo.lock,
     go.mod, and Python re-resolved from pyproject.toml (pip and uv do not read uv.lock), else uv.lock's non-dev
     closure, poetry.lock or pinned requirements. Lockfiles of parts the person does not install (docs sites, editor
     extensions, CI actions, examples, tests) are skipped.
2. Look every resolved version up on OSV.dev. Any high or critical advisory counts, fixed or not, denial of service
   included (念誠: rather drop a treasure by mistake than recommend a known hole); so does a malicious-package report.
   Severity is GHSA's; an advisory without one (RUSTSEC, GO, PYSEC) takes its GHSA alias's, else its CVSS v3 base
   score. RUSTSEC's informational notes (unmaintained, unsound) are not vulnerabilities.

The check bounds quality (QUALITY_CAPS["known_vulnerability"], 79): a vulnerable record cannot be a treasure. A record
pickfit cannot check keeps its score and says so (status unchecked). `pickfit security --write` stores the check,
hides a record with a malicious package, and refreshes scores.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now

VERSION = "sec.v1"
OSV = "https://api.osv.dev/v1"
DEPS_DEV = "https://api.deps.dev/v3"
CLONES = Path.home() / ".pickfit" / "security-clones"
ECOSYSTEM = {"npm": "npm", "pypi": "PyPI", "crates": "crates.io", "go": "Go"}
COUNTED = ("CRITICAL", "HIGH")
# Parts of a repository a person installing the software does not get.
PERIPHERAL = re.compile(r"(^|/)(website|site|docs?|landing|www|demo|examples?|bench(mark)?s?|playground|e2e|tests?|"
                        r"__tests__|fixtures?|scripts|editors?|action|vscode|node_modules|vendor|tools|external|"
                        r"third_party|reference|mockups|spikes?|eval|fuzz|testdata|experiments?|skill_assets|skills|qa|"
                        r"labs?|probes?|\.[^/]+)/", re.I)
UNSUPPORTED_LOCKS = ("pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
MAX_FINDINGS = 60
TIMEOUT = 300

type Node = tuple[str, str, str]  # ecosystem key, name, version


# --- HTTP -------------------------------------------------------------------------------------------------------------


def _http(url: str, body: Any = None, tries: int = 4) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                                 "User-Agent": "pickfit-security"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise
            if attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


class Advisories:
    """OSV advisory details, fetched once per id (thread-safe enough: a duplicate fetch only costs a request)."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, vid: str) -> dict[str, Any]:
        with self._lock:
            hit = self._cache.get(vid)
        if hit is None:
            hit = _http(f"{OSV}/vulns/{urllib.parse.quote(vid)}")
            with self._lock:
                self._cache[vid] = hit
        return hit

    def severity(self, v: dict[str, Any]) -> str:
        """CRITICAL, HIGH, MODERATE, LOW or UNKNOWN."""
        own = (v.get("database_specific") or {}).get("severity")
        if own:
            return str(own).upper()
        for alias in v.get("aliases", []):
            if alias.startswith("GHSA-"):
                try:
                    sev = (self.get(alias).get("database_specific") or {}).get("severity")
                except urllib.error.HTTPError:
                    continue
                if sev:
                    return str(sev).upper()
        for s in v.get("severity", []):
            if s.get("type") == "CVSS_V3":
                score = cvss3_base(s.get("score", ""))
                if score is not None:
                    return ("CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MODERATE" if score >= 4
                            else "LOW" if score > 0 else "NONE")
        return "UNKNOWN"


def cvss3_base(vector: str) -> float | None:
    """CVSS v3.x base score from its vector, as the FIRST specification computes it; None if the vector is unreadable."""
    m = dict(p.split(":", 1) for p in vector.split("/")[1:] if ":" in p)
    try:
        scope_changed = m["S"] == "C"
        av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}[m["AV"]]
        ac = {"L": 0.77, "H": 0.44}[m["AC"]]
        pr = {"N": 0.85, "L": 0.68 if scope_changed else 0.62, "H": 0.5 if scope_changed else 0.27}[m["PR"]]
        ui = {"N": 0.85, "R": 0.62}[m["UI"]]
        cia = [{"H": 0.56, "L": 0.22, "N": 0.0}[m[k]] for k in ("C", "I", "A")]
    except KeyError:
        return None
    iss = 1 - (1 - cia[0]) * (1 - cia[1]) * (1 - cia[2])
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    raw = min((1.08 if scope_changed else 1) * (impact + exploitability), 10)
    whole = round(raw * 100000)
    return whole / 100000 if whole % 10000 == 0 else (math.floor(whole / 10000) + 1) / 10


# --- resolving what a fresh install brings ----------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=TIMEOUT)


def npm_lock_nodes(lock: dict[str, Any], *, platform: bool = True) -> list[Node]:
    """Non-dev packages of a package-lock.json (v2/v3) from the registry: the root project and workspace members (local
    code, entries outside node_modules/) are left out, so a local name is never looked up as someone else's package.
    platform=False also leaves out per-platform binaries (entries with os or cpu, as `@x/tool-darwin-arm64`)."""
    out = []
    for path, p in (lock.get("packages") or {}).items():
        if "node_modules/" not in path or "version" not in p or p.get("dev") or p.get("link"):
            continue
        if not platform and (p.get("os") or p.get("cpu")):
            continue
        out.append(("npm", p.get("name") or path.rsplit("node_modules/", 1)[-1], p["version"]))
    return out


# A resolver returns every package a fresh install brings and how many of them are real dependencies: neither the
# package itself nor a per-platform build of it. None means a wrapper whose dependencies are compiled in.
type Resolved = tuple[list[Node], int]


def resolve_npm(name: str) -> Resolved:
    with tempfile.TemporaryDirectory(prefix="pickfit-sec-npm-") as tmp:
        Path(tmp, "package.json").write_text('{"name":"pickfit-security-probe","version":"0.0.0","private":true}')
        r = _run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund", name], cwd=Path(tmp))
        if r.returncode:
            raise RuntimeError(f"npm resolve failed: {r.stderr.strip()[-200:]}")
        lock = json.loads(Path(tmp, "package-lock.json").read_text())
    deps = [n for n in npm_lock_nodes(lock, platform=False) if n[1] != name]
    return npm_lock_nodes(lock), len(deps)


def _pins(text: str) -> list[Node]:
    return [("pypi", m.group(1), m.group(2)) for m in re.finditer(r"(?m)^([A-Za-z0-9_.\-]+)==([^\s;#\\]+)", text)]


def _compile(target: list[str], stdin: str | None) -> list[Node]:
    err = ""
    for py in ("3.12", "3.13"):
        r = _run(["uv", "pip", "compile", "--no-build", "--no-header", "--no-annotate", "--quiet", "--python-version",
                  py, "--python-platform", "linux", *target], stdin=stdin)
        if r.returncode == 0:
            return _pins(r.stdout)
        err = r.stderr.strip()[-200:]
    raise RuntimeError(f"uv resolve failed: {err}")


def resolve_pypi(name: str) -> Resolved:
    """A package name resolved for Linux without building anything."""
    nodes = _compile(["-"], name + "\n")
    return nodes, len([n for n in nodes if _norm(n[1]) != _norm(name)])


def resolve_pyproject(path: Path) -> list[Node]:
    return _compile([str(path)], None)


def resolve_crate(name: str) -> Resolved:
    q = urllib.parse.quote(name, safe="")
    info = _http(f"{DEPS_DEV}/systems/cargo/packages/{q}")
    default = [v for v in info.get("versions", []) if v.get("isDefault")]
    if not default:
        raise RuntimeError("crate has no default version on deps.dev")
    ver = default[0]["versionKey"]["version"]
    graph = _http(f"{DEPS_DEV}/systems/cargo/packages/{q}/versions/{urllib.parse.quote(ver, safe='')}:dependencies")
    nodes = graph.get("nodes", [])
    if not any(n.get("relation") == "SELF" for n in nodes):  # deps.dev has not resolved this version
        raise RuntimeError("deps.dev has no dependency graph for this crate")
    return ([("crates", n["versionKey"]["name"], n["versionKey"]["version"]) for n in nodes],
            len([n for n in nodes if n.get("relation") != "SELF"]))


RESOLVERS = {"npm": resolve_npm, "pypi": resolve_pypi, "crates": resolve_crate}


def _uv_lock_nodes(lock: dict[str, Any]) -> list[Node]:
    """uv.lock: what the project's own packages need at run time (dev groups left out); poetry.lock: everything."""
    packages = lock.get("package", [])
    by_name = {p["name"]: p for p in packages}
    roots = [p for p in packages if (p.get("source") or {}).get("editable") or (p.get("source") or {}).get("virtual")]
    if not roots:
        return [("pypi", p["name"], p["version"]) for p in packages if "version" in p]
    keep: set[str] = set()
    stack = [d["name"] for r in roots for d in r.get("dependencies", [])]
    while stack:
        n = stack.pop()
        if n in keep or n not in by_name:
            continue
        keep.add(n)
        stack += [d["name"] for d in by_name[n].get("dependencies", []) if isinstance(d, dict)]
    return [("pypi", n, by_name[n]["version"]) for n in sorted(keep) if "version" in by_name[n]]


@dataclass
class RepoRead:
    """What a repository's lockfiles gave. complete: a main lockfile (at the root or one folder down) yielded packages,
    and nothing at the root was left unread; otherwise `reason` says why the read is not the whole software."""

    nodes: list[Node]
    read: list[str]
    complete: bool
    reason: str | None


def _main(rel: str) -> bool:
    return rel.count("/") <= 1


def repo_nodes(root: Path) -> RepoRead:
    """Read a cloned repository's lockfiles. A lockfile counts as read only when it yields packages. Python projects are
    resolved from pyproject.toml as pip and uv do (each on its own), a lockfile beside it standing in when that fails."""
    nodes: list[Node] = []
    read: list[str] = []
    main_read = unsupported = root_unreadable = root_unresolved = False
    pyprojects: list[Path] = []
    py_locks: dict[Path, list[Path]] = {}

    def took(rel: str, got: list[Node]) -> None:
        nonlocal main_read
        if got:
            nodes.extend(got)
            read.append(rel)
            main_read |= _main(rel.split(" (", 1)[0])

    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root).as_posix()
        if not f.is_file() or ".git/" in rel or PERIPHERAL.search(rel) or rel.count("/") > 3:
            continue
        name = f.name
        try:
            if name == "package-lock.json":
                took(rel, npm_lock_nodes(json.loads(f.read_text(encoding="utf-8"))))
            elif name == "Cargo.lock":
                took(rel, [("crates", p["name"], p["version"]) for p in tomllib.loads(f.read_text(encoding="utf-8"))
                           .get("package", []) if "source" in p])
            elif name == "go.mod":
                body = f.read_text(encoding="utf-8")
                took(rel, [("go", m.group(1), m.group(2)) for m in
                           re.finditer(r"(?m)^\s*(?:require\s+)?([\w.\-]+\.[\w./\-]+)\s+(v[\w.\-+]+)", body)])
            elif name == "pyproject.toml" and _main(rel):
                pyprojects.append(f)
            elif name in ("uv.lock", "poetry.lock") or re.fullmatch(r"requirements(-lock)?\.txt", name):
                py_locks.setdefault(f.parent, []).append(f)
            elif name in UNSUPPORTED_LOCKS:
                unsupported = True
                root_unreadable |= "/" not in rel
        except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            root_unreadable |= "/" not in rel
    py_dirs = {p.parent for p in pyprojects}
    for p in pyprojects:
        rel = p.relative_to(root).as_posix()
        try:
            got = resolve_pyproject(p)
        except (RuntimeError, subprocess.TimeoutExpired):
            got = []
        if got:
            took(f"{rel} (resolved today)", got)
            continue
        fallback: list[Node] = []
        for f in py_locks.get(p.parent, []):
            try:
                text = f.read_text(encoding="utf-8")
                fallback += _uv_lock_nodes(tomllib.loads(text)) if f.suffix == ".lock" else _pins(text)
            except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
        if fallback:
            took(" + ".join(f.relative_to(root).as_posix() for f in py_locks[p.parent]), fallback)
        elif "/" not in rel:
            root_unresolved = True  # the Python project at the root: its dependencies could not be read
    for folder, files in py_locks.items():  # Python lockfiles with no pyproject.toml beside them
        if folder in py_dirs:
            continue
        for f in files:
            rel = f.relative_to(root).as_posix()
            try:
                text = f.read_text(encoding="utf-8")
                took(rel, _uv_lock_nodes(tomllib.loads(text)) if f.suffix == ".lock" else _pins(text))
            except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                root_unreadable |= "/" not in rel
    reason = ("lockfile_not_supported" if root_unreadable else "resolve_failed" if root_unresolved
              else None if main_read else "lockfile_not_supported" if unsupported and not read else "no_lockfile")
    return RepoRead(list(dict.fromkeys(nodes)), read, reason is None, reason)


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=900,
                          env=os.environ | {"GIT_TERMINAL_PROMPT": "0"})


def clone(url: str, slug: str, clones: Path = CLONES) -> tuple[Path, str]:
    """A shallow clone of the default branch as it is now, and its commit. A cached clone is fetched and reset to the
    latest commit (cloned again if that fails); files over 20 MB are left out. Only read as data, never run."""
    dest = clones / slug
    if (dest / ".git").is_dir():
        fetched = _git("fetch", "--depth", "1", "--quiet", "--filter=blob:limit=20m", "origin", "HEAD", cwd=dest)
        if fetched.returncode or _git("reset", "--hard", "--quiet", "FETCH_HEAD", cwd=dest).returncode:
            subprocess.run(["rm", "-rf", str(dest)])
    if not (dest / ".git").is_dir():
        clones.mkdir(parents=True, exist_ok=True)
        r = _git("clone", "--depth", "1", "--quiet", "--filter=blob:limit=20m", url, str(dest))
        if r.returncode:
            subprocess.run(["rm", "-rf", str(dest)])
            raise RuntimeError(f"clone failed: {r.stderr.strip()[-200:]}")
    return dest, _git("rev-parse", "HEAD", cwd=dest).stdout.strip()


# --- what to check for a record ---------------------------------------------------------------------------------------

_FLAGS = r"((?:\s+-{1,2}[\w=-]+)*)\s+"
_INSTALLED = [
    (re.compile(r"\bnpm\s+(?:install|i)" + _FLAGS + r"((?:@[\w.-]+/)?[\w.-]+)"), "npm"),
    (re.compile(r"\b(?:uv\s+tool\s+install|pipx\s+install)" + _FLAGS + r"\"?([A-Za-z][\w.-]*)(?=[\s\"\[=<>]|$)"), "pypi"),
    (re.compile(r"\bpip3?\s+install" + _FLAGS + r"\"?([A-Za-z][\w.-]*)(?=[\s\"\[=<>]|$)"), "pypi"),
    (re.compile(r"\bcargo\s+install" + _FLAGS + r"([A-Za-z][\w-]*)(?=\s|$)"), "crates"),
]


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def own_names(raw: dict[str, Any]) -> set[str]:
    """What the software itself may be published as: its slug, name, repository name and aliases."""
    repo = raw.get("repo") if isinstance(raw.get("repo"), dict) else {}
    names = [raw.get("slug") or "", raw.get("name") or "", (repo.get("full_name") or "").rsplit("/", 1)[-1],
             *[a.rsplit("/", 1)[-1] for a in raw.get("aliases") or []]]
    return {_norm(n) for n in names if n}


def packages_of(raw: dict[str, Any]) -> list[str]:
    """The software's own registry packages: those that link back to its repository, and those pickfit's steps
    installed under the software's own name (a global npm install, uv tool, pipx, pip, cargo install). A package a step
    installed for something else (a prerequisite, a test tool) is not the software, so the repository decides then."""
    linked = [p for p in (((raw.get("scores") or {}).get("popularity") or {}).get("packages") or [])
              if p.split(":", 1)[0] in RESOLVERS]
    own = own_names(raw) | {_norm(p.split(":", 1)[1].rsplit("/", 1)[-1]) for p in linked}
    found: list[str] = []
    for run in (raw.get("verification") or {}).get("runs", []):
        for step in run.get("steps", []):
            for pattern, eco in _INSTALLED:
                for m in pattern.finditer(step.get("command", "")):
                    flags, name = m.group(1), m.group(2)
                    if eco == "npm" and not re.search(r"(^|\s)(-g|--global)(\s|$)", flags):
                        continue  # a local npm install is a project's dependency, not the tool
                    # @scope/name: the scope or the name may be the software's own (@agenticschema/server)
                    if {_norm(part) for part in name.lstrip("@").split("/")} & own:
                        found.append(f"{eco}:{name}")
    return list(dict.fromkeys(linked + found))


def _repo_url(raw: dict[str, Any]) -> str | None:
    repo = raw.get("repo")
    url = repo.get("url") if isinstance(repo, dict) else repo
    return url if url and url.startswith("https://github.com/") else None


def _fixed_above(v: dict[str, Any], eco: str, name: str, current: str) -> str | None:
    def key(s: str) -> tuple[int, ...]:
        return tuple(int(x) if x.isdigit() else -1 for x in re.split(r"[.\-+]", s.lstrip("v")) if x)[:6]

    norm = lambda s: s.lower().replace("_", "-")  # noqa: E731
    best = None
    for a in v.get("affected", []):
        pkg = a.get("package") or {}
        if pkg.get("ecosystem") != ECOSYSTEM[eco] or norm(pkg.get("name", "")) != norm(name):
            continue
        for rng in a.get("ranges", []):
            for ev in rng.get("events", []):
                f = ev.get("fixed")
                if f and key(f) > key(current) and (best is None or key(f) < key(best)):
                    best = f
    return best


def informational(v: dict[str, Any]) -> bool:
    """A RUSTSEC note that is not a vulnerability (unmaintained, unsound, notice); RustSec puts it per affected entry."""
    blocks = [v.get("database_specific") or {}] + [a.get("database_specific") or {} for a in v.get("affected", [])]
    return any(b.get("informational") for b in blocks)


def findings_for(nodes: list[Node], advisories: Advisories, unrated: list[str] | None = None) -> list[dict[str, Any]]:
    """High and critical advisories (and malicious-package reports) on the given versions, one per vulnerability.
    Advisories with no severity anywhere (no GHSA rating, no CVSS v3) are not counted; `unrated` collects them."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i in range(0, len(nodes), 500):
        chunk = nodes[i:i + 500]
        queries = [{"package": {"name": n, "ecosystem": ECOSYSTEM[e]}, "version": v} for e, n, v in chunk]
        results = _http(f"{OSV}/querybatch", {"queries": queries}).get("results", [])
        for (eco, name, version), res in zip(chunk, results):
            for hit in res.get("vulns") or []:
                v = advisories.get(hit["id"])
                if v.get("withdrawn"):
                    continue
                ids = {v["id"], *v.get("aliases", [])}
                if f"{eco}:{name}" + "|" + v["id"] in seen or any(f"{eco}:{name}|{a}" in seen for a in ids):
                    continue
                malicious = v["id"].startswith("MAL-")
                if not malicious and informational(v):
                    continue  # RUSTSEC notes: unmaintained, unsound, notice
                severity = "CRITICAL" if malicious else advisories.severity(v)
                if severity == "UNKNOWN" and unrated is not None:
                    unrated.append(f"{eco}:{name}@{version} {v['id']}")
                if severity not in COUNTED:
                    continue
                seen |= {f"{eco}:{name}|{a}" for a in ids}
                out.append({"package": f"{eco}:{name}", "version": version, "advisory": v["id"],
                            "cves": sorted(a for a in v.get("aliases", []) if a.startswith("CVE-"))[:10],
                            "severity": severity, "fixed_in": _fixed_above(v, eco, name, version),
                            "summary": (v.get("summary") or v.get("details") or "")[:200].strip() or v["id"],
                            "malicious": malicious})
    out.sort(key=lambda f: (not f["malicious"], f["severity"] != "CRITICAL", f["package"], f["advisory"]))
    return out


def check(raw: dict[str, Any], advisories: Advisories, *, now: datetime, clones: Path = CLONES,
          unrated: list[str] | None = None) -> dict[str, Any]:
    """The security check (SecurityCheck as JSON) for one record.

    Clean only when the software's own dependency set was read in full: every one of its registry packages resolved
    with real dependencies (not a wrapper around a compiled binary), or else its repository's main lockfiles yielded
    packages with nothing at the root left unread. Anything less is unchecked with the reason, and keeps its score.
    Findings make it vulnerable whatever else could not be read."""
    base = {"version": VERSION, "database": "OSV.dev", "checked_at": now.isoformat(timespec="seconds")}

    def unchecked(reason: str) -> dict[str, Any]:
        return base | {"status": "unchecked", "unchecked_reason": reason, "sources": [], "packages_checked": 0,
                       "findings_total": 0, "findings": []}

    nodes: list[Node] = []
    sources: list[str] = []
    own = packages_of(raw)
    all_resolved, wrapper = True, False
    for pkg in own:
        eco, name = pkg.split(":", 1)
        try:
            got, deps = RESOLVERS[eco](name)
        except (RuntimeError, subprocess.TimeoutExpired, urllib.error.URLError):
            all_resolved = False
            continue
        if not got:
            all_resolved = False
            continue
        wrapper |= deps == 0
        nodes += got
        sources.append(f"{pkg} (fresh install, {len(got)} packages)")
    complete = bool(own) and all_resolved and not wrapper
    reason: str | None = None
    if not complete:
        # A package that did not resolve, or a wrapper: what installs is in the repository's lockfiles.
        url = _repo_url(raw)
        if url is None:
            reason = "resolve_failed" if own else "no_source"
        else:
            try:
                root, commit = clone(url, raw["slug"], clones)
            except (RuntimeError, subprocess.TimeoutExpired):
                reason = "resolve_failed"
            else:
                repo = repo_nodes(root)
                nodes += repo.nodes
                sources += ([f"{url.removeprefix('https://')}@{commit[:12]}"] + repo.read) if repo.read else []
                complete, reason = repo.complete, repo.reason
                if not complete and own and reason == "no_lockfile":
                    reason = "resolve_failed"  # its own package did not resolve to its dependencies either
    nodes = list(dict.fromkeys(nodes))
    findings = findings_for(nodes, advisories, unrated) if nodes else []
    if not findings and not complete:
        return unchecked(reason or "resolve_failed")
    return base | {"status": "vulnerable" if findings else "clean", "unchecked_reason": None, "sources": sources[:20],
                   "packages_checked": len(nodes), "findings_total": len(findings),
                   "findings": findings[:MAX_FINDINGS]}


# --- writing ----------------------------------------------------------------------------------------------------------


def write_security(path: Path, result: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Store the check just before scores, hide a record with a malicious package, refresh scores (the cap follows),
    validate, and replace the file atomically. Returns the record as written."""
    from pickfit.schema import SoftwareRecord
    from pickfit.score import refresh_scores

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("security", None)
    anchor = next((k for k in ("scores", "outcomes", "sources", "evidence", "first_seen_at", "updated_at") if k in raw),
                  None)
    keys = list(raw)
    at = keys.index(anchor) if anchor else len(keys)
    raw = {k: raw[k] for k in keys[:at]} | {"security": result} | {k: raw[k] for k in keys[at:]}
    bad = [f["advisory"] for f in result["findings"] if f["malicious"]]
    if bad and raw.get("status") == "listed":
        raw["status"] = "hidden"
        raw["status_reason"] = f"malicious package reported on OSV.dev: {', '.join(bad[:3])}"[:200]
    refresh_scores(raw, now)
    raw["updated_at"] = now.isoformat(timespec="seconds")
    SoftwareRecord.model_validate(raw)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return raw


def main_security(args: Any) -> int:
    """`pickfit security` (wired in pickfit/cli.py)."""
    from pickfit.profiles import DEFAULT_OUT

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_OUT
    paths = sorted(data_dir.glob("*.json"))
    if args.slug:
        paths = [p for p in paths if p.stem in set(args.slug)]
    elif args.all:
        paths = [p for p in paths if json.loads(p.read_text(encoding="utf-8")).get("status") == "listed"]
    else:
        print("pickfit security: name --slug or --all", file=sys.stderr)
        return 2
    now = taipei_now()
    advisories = Advisories()
    rows: dict[str, Any] = {}
    lock = threading.Lock()

    def one(path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        before = (raw.get("scores") or {}).get("quality", {}).get("total"), \
            ((raw.get("scores") or {}).get("treasure") or {}).get("is_treasure")
        unrated: list[str] = []
        try:
            result = check(raw, advisories, now=now, unrated=unrated)
        except Exception as err:  # noqa: BLE001 - one record's trouble must not stop the run
            with lock:
                rows[path.stem] = {"error": f"{type(err).__name__}: {str(err)[:200]}"}
            return
        written = write_security(path, result, now) if args.write else raw
        scores = written.get("scores") or {}
        row = {"status": result["status"], "reason": result["unchecked_reason"], "findings": len(result["findings"]),
               "malicious": any(f["malicious"] for f in result["findings"]), "quality_before": before[0],
               "treasure_before": before[1], "quality": (scores.get("quality") or {}).get("total"),
               "treasure": (scores.get("treasure") or {}).get("is_treasure"), "kind": raw.get("kind"),
               "sources": result["sources"], "unrated": sorted(set(unrated))}
        with lock:
            rows[path.stem] = row
            if args.verbose:
                print(f"  {path.stem:<28} {result['status']:<10} {row['findings']:>3} findings", file=sys.stderr)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, paths))
    summary = {"checked_at": now.isoformat(timespec="seconds"), "records": len(paths), "written": bool(args.write),
               "status": {s: sum(1 for r in rows.values() if r.get("status") == s)
                          for s in ("vulnerable", "clean", "unchecked")},
               "errors": {k: r["error"] for k, r in rows.items() if "error" in r}, "rows": rows}
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0
