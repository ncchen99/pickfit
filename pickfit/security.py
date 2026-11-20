"""Known vulnerabilities in what the software brings (record field security; sec.v1 念誠 11/3, sec.v2 11/19).

No model call and no paid API. sec.v2 (docs/proposals/security.md) keeps what was seen apart from how it was judged.

Observation, per record:

1. What it brings, the way a person gets it:
   - the installed artifact, when the verification's replay box left an SBOM (pickfit/sbom.py; target
     installed_artifact). A lockfile package the SBOM does not have is marked not in the artifact;
   - else its own registry packages (npm, PyPI, crates: from pickfit's own install steps, else the packages that link
     back to the repository) resolved as a fresh install: `npm install --package-lock-only --ignore-scripts` and
     `uv pip compile --no-build` (neither runs package code), crates through deps.dev (target registry_resolve);
   - else the repository (a shallow clone, only read as data; target repo_lockfile): package-lock.json and
     pnpm-lock.yaml (v6 to v9) as graphs, Cargo.lock with the members' Cargo.toml, go.mod, and Python re-resolved
     from pyproject.toml (pip and uv do not read uv.lock), else uv.lock's non-dev closure, poetry.lock or pinned
     requirements. Lockfiles of parts the person does not install (docs sites, editor extensions, CI actions,
     examples, tests) are skipped.
   Every package keeps where it sits (S4): runtime; dev; build (native-build tooling such as node-gyp, and bundlers
   in web and desktop apps); peer; optional (a Cargo optional dependency no default feature turns on); platform (only
   on an OS the software does not support); workspace (a member of the repository the software does not ship: pnpm
   and npm importers, Cargo members, chosen by the software's own package names, its Electron app or its binaries).
2. Every version is looked up on OSV.dev and every advisory is kept, any severity (sec.v1 kept high and critical),
   with what it says (aliases, dates, CVSS vectors, CWE), CISA KEV, FIRST EPSS and when the fix came out (deps.dev).
   RUSTSEC's informational notes (unmaintained, unsound) are not vulnerabilities. Severity is GHSA's; an advisory
   without one takes its GHSA alias's, else its CVSS v3 base score's band.
3. Whether the vulnerable code runs, by program only: an MCP SDK whose HTTP transports the project never imports, an
   option or function the advisory names that the project's source never uses (grep, conclusive only when the project
   is the package's only user), a Go package the project never imports, govulncheck's symbol results on the
   installed Go binaries, a Next.js app built as a static export (no server).

Assessment (policy sec.v2) is about known findings only. A finding is blocked (a malicious package, or a KEV entry the
code is shown to reach), exposed (reachable by evidence and over the network), conditional (anything not settled: the
default), present_unreachable (shipped, vulnerable code not used) or not_shipped (not in what the person gets). Only
high and critical findings, malicious packages and KEV entries count; the rest are observed. security.assessment.level
is the worst counted finding's level, or `none` when no counted finding is known (level_of() below). It says nothing
about what could not be checked: an unknown is never a vulnerability (念誠 11/19).

Coverage (security.coverage) says how much could be checked, apart from the level: the target read, packages found
against packages checked, each component (a lockfile, a resolved package, the SBOM) as scanned, partial or not_scanned,
and every gap in the fixed taxonomy below. Its state is complete (something checked, no gap), partial (something
checked, a gap) or unchecked (nothing checked). gaps_of() lists a record's gaps; gap_report() groups them (`pickfit
security --gaps`, scripts/security_gaps.py) for the work that will close them.

`status` keeps sec.v1's readers working: vulnerable when the level warns (blocked, exposed, conditional), else clean
when coverage is complete, else unchecked ("not checked", never "safe"). Scoring reads the level; a record still on
sec.v1 keeps its rule (status vulnerable caps quality at 79). Treasure eligibility is not decided here.

Gap taxonomy (stable codes; a gap is {code, category, ecosystem, component, detail, capability, found, first_seen,
last_seen}; `capability` names the harness capability that would close it, `found` the packages it hides when known):

| code                        | category             | when                                                           | capability              |
|-----------------------------|----------------------|----------------------------------------------------------------|-------------------------|
| advisory_db.no_ecosystem    | advisory_db          | packages in an ecosystem OSV.dev has no data for (C/C++, deb)  | advisory_source:<eco>   |
| lockfile.missing            | lockfile_missing     | a manifest (package.json, Cargo.toml, requirements) without a  | lockfile_from_manifest: |
|                             |                      | lockfile or pins pickfit reads                                 | <eco>                   |
| lockfile.none_found         | lockfile_missing     | no manifest or lockfile pickfit recognizes in the repository   | manifest_detection      |
| lockfile.unsupported_format | lockfile_unreadable  | bun.lockb (binary), pnpm-lock before v6                        | read_lockfile:<format>  |
| lockfile.parse_error        | lockfile_unreadable  | a lockfile pickfit reads failed to parse                       | fix_lockfile_reader     |
| resolve.registry_failed     | resolve_failed       | the software's own registry package did not resolve            | resolve_in_sandbox      |
| resolve.pyproject_failed    | resolve_failed       | pyproject.toml did not resolve (uv pip compile --no-build)     | resolve_in_sandbox      |
| adapter.missing             | no_adapter           | an ecosystem pickfit has no reader for (Gemfile.lock,          | adapter:<eco>           |
|                             |                      | composer.lock, Maven, Gradle, NuGet, SwiftPM, pub, Hex)        |                         |
| binary.prebuilt_package     | binary_no_metadata   | a registry package that wraps a compiled binary, no lockfile   | sbom_binary             |
| binary.no_build_info        | binary_no_metadata   | installed executables list no dependencies (Rust without       | binary_analysis         |
|                             |                      | cargo-auditable, stripped Go, C/C++)                           |                         |
| source.none                 | no_source            | no repository and no package to read                           | locate_source           |
| source.clone_failed         | tool_error           | the repository could not be cloned                             | retry                   |
| tool.sbom_error             | tool_error           | a tool in the replay box failed (syft, npm ls, govulncheck)    | fix_sbom_tool           |
| platform.sbom_unsupported   | platform_unsupported | only macOS or Windows runs, where no SBOM is taken yet, and    | sbom:<os>               |
|                             |                      | nothing else covered it                                        |                         |

sec.v1's unchecked_reason maps onto it (legacy_gaps()): no_lockfile -> lockfile.missing, resolve_failed ->
resolve.registry_failed, no_source -> source.none, lockfile_not_supported -> lockfile.unsupported_format, each with
ecosystem "unknown"; a rescan replaces them with what the repository actually holds. A sec.v2 check that is unchecked
writes the legacy reason too (unchecked_reason), from its first gap's category.

The record keeps a summary and the findings that matter; data/security/<slug>.json keeps the full observation (every
finding, the SBOM's packages) so a new policy can be applied offline. `pickfit security --write` stores the check,
hides a blocked record, and refreshes scores.
"""

from __future__ import annotations

import hashlib
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
from collections import Counter, deque
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pickfit.ledger import taipei_now

VERSION = "sec.v2"
POLICY = "sec.v2"
OSV = "https://api.osv.dev/v1"
DEPS_DEV = "https://api.deps.dev/v3"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
CLONES = Path.home() / ".pickfit" / "security-clones"
CACHE = Path.home() / ".pickfit" / "cache" / "security"
REPO_ROOT = Path(__file__).resolve().parent.parent
ECOSYSTEM = {"npm": "npm", "pypi": "PyPI", "crates": "crates.io", "go": "Go"}
DEPS_DEV_SYSTEM = {"npm": "npm", "pypi": "pypi", "crates": "cargo", "go": "go"}
COUNTED = ("CRITICAL", "HIGH")
SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3, "NONE": 4, "UNKNOWN": 5}
# Parts of a repository a person installing the software does not get.
PERIPHERAL = re.compile(r"(^|/)(website|site|docs?|landing|www|demo|examples?|bench(mark)?s?|playground|e2e|tests?|"
                        r"__tests__|fixtures?|scripts|editors?|action|vscode|node_modules|vendor|tools|external|"
                        r"third_party|reference|mockups|spikes?|eval|fuzz|testdata|experiments?|skill_assets|skills|qa|"
                        r"labs?|probes?|\.[^/]+)/", re.I)
UNSUPPORTED_LOCKS = ("bun.lockb",)  # yarn.lock and bun.lock are read since 11/20
MAX_FINDINGS = 60  # sec.v1's record list
RECORD_WARN = 20  # sec.v2: findings that warn kept in the record (all are in data/security/<slug>.json)
RECORD_UNREACHABLE = 10  # and the ones present but unreachable
RECORD_COVERAGE = 30  # components and gaps kept in the record (all are in data/security/<slug>.json)
TIMEOUT = 300
ALL_OS = frozenset({"macos", "linux", "windows"})
OS_NAMES = {"darwin": "macos", "macos": "macos", "linux": "linux", "win32": "windows", "windows": "windows"}

# The levels, worst first (pickfit/schema.py's SECURITY_* in loop/proposals/security-schema.patch mirror these). A
# finding has one of the first five; the record the worst counted one, or none. Coverage is apart (COVERAGE_STATES).
LEVELS = ("blocked", "exposed", "conditional", "present_unreachable", "not_shipped", "none")
FINDING_LEVELS = ("blocked", "exposed", "conditional", "present_unreachable", "not_shipped")
WARN_LEVELS = frozenset({"blocked", "exposed", "conditional"})
COVERAGE_STATES = ("complete", "partial", "unchecked")
# Where a dependency sits, most shipped first; only runtime reaches the person.
SCOPES = ("runtime", "optional", "platform", "peer", "build", "test", "dev", "workspace")

# The gap taxonomy (see the module docstring): code -> (category, capability; `{eco}` and `{detail}` filled in).
GAP_CATEGORIES = ("advisory_db", "lockfile_missing", "lockfile_unreadable", "resolve_failed", "no_adapter",
                  "binary_no_metadata", "no_source", "tool_error", "platform_unsupported")
GAP_CODES: dict[str, tuple[str, str]] = {
    "advisory_db.no_ecosystem": ("advisory_db", "advisory_source:{eco}"),
    "lockfile.missing": ("lockfile_missing", "lockfile_from_manifest:{eco}"),
    "lockfile.none_found": ("lockfile_missing", "manifest_detection"),
    "lockfile.unsupported_format": ("lockfile_unreadable", "read_lockfile:{detail}"),
    "lockfile.parse_error": ("lockfile_unreadable", "fix_lockfile_reader"),
    "resolve.registry_failed": ("resolve_failed", "resolve_in_sandbox"),
    "resolve.pyproject_failed": ("resolve_failed", "resolve_in_sandbox"),
    "adapter.missing": ("no_adapter", "adapter:{eco}"),
    "binary.prebuilt_package": ("binary_no_metadata", "sbom_binary"),
    "binary.no_build_info": ("binary_no_metadata", "binary_analysis"),
    "source.none": ("no_source", "locate_source"),
    "source.clone_failed": ("tool_error", "retry"),
    "tool.sbom_error": ("tool_error", "fix_sbom_tool"),
    "platform.sbom_unsupported": ("platform_unsupported", "sbom:{detail}"),
}
assert {c for c, _ in GAP_CODES.values()} == set(GAP_CATEGORIES)
# sec.v1's unchecked_reason, as the gap it stands for; and back, for a sec.v2 check that is unchecked.
LEGACY_GAP = {"no_lockfile": "lockfile.missing", "resolve_failed": "resolve.registry_failed", "no_source": "source.none",
              "lockfile_not_supported": "lockfile.unsupported_format"}
LEGACY_REASON = {"lockfile_missing": "no_lockfile", "lockfile_unreadable": "lockfile_not_supported",
                 "no_source": "no_source", "no_adapter": "lockfile_not_supported"}

type Node = tuple[str, str, str]  # ecosystem key, name, version


def gap(code: str, ecosystem: str = "unknown", component: str | None = None, detail: str = "", *,
        found: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    """One gap in the taxonomy. Pure."""
    category, capability = GAP_CODES[code]
    day = (now or taipei_now()).date().isoformat()
    return {"code": code, "category": category, "ecosystem": ecosystem, "component": component,
            "detail": detail[:300], "capability": capability.format(eco=ecosystem, detail=detail.split(" ", 1)[0] or
                                                                    ecosystem),
            "found": found, "first_seen": day, "last_seen": day}


def status_for(level: str, coverage: str = "complete") -> str:
    """The sec.v1 status a level and a coverage state read as: vulnerable only for a level that warns; an unknown is
    unchecked, never vulnerable and never clean."""
    if level in WARN_LEVELS:
        return "vulnerable"
    return "clean" if coverage == "complete" else "unchecked"


def legacy_level(check: dict[str, Any] | None) -> str:
    """A sec.v1 check's known findings in sec.v2's words, read the way sec.v1 judged them: a malicious package blocked,
    any other finding conditional (sec.v1 could not tell more), else none."""
    if not check or check.get("status") != "vulnerable":
        return "none"
    return "blocked" if any(f.get("malicious") for f in check.get("findings") or []) else "conditional"


def _security_of(record: Any) -> Any:
    return record.get("security") if isinstance(record, dict) else getattr(record, "security", None)


def _get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def level_of(record: Any) -> str | None:
    """security.assessment.level of a record (a dict or a SoftwareRecord): the worst known finding's level, or none.
    None when the record has no sec.v2 assessment: a caller then keeps sec.v1's rule (status vulnerable caps quality at
    79). Never partial or unchecked: what could not be checked is coverage_of()'s. Pure: no I/O."""
    assessment = _get(_security_of(record), "assessment") if _security_of(record) is not None else None
    return None if assessment is None else _get(assessment, "level")


def coverage_of(record: Any) -> str:
    """How much of a record could be checked: complete, partial or unchecked. A sec.v1 record reads as its status did
    (clean: complete; vulnerable: partial, since sec.v1 did not say; else unchecked). Pure."""
    security = _security_of(record)
    if security is None:
        return "unchecked"
    coverage = _get(security, "coverage")
    if coverage is not None:
        return str(_get(coverage, "state"))
    status = _get(security, "status")
    return "complete" if status == "clean" else "partial" if status == "vulnerable" else "unchecked"


def legacy_gaps(check: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The gap a sec.v1 check stands for (from its unchecked_reason), dated by its check. Pure."""
    if not check:
        return []
    reason = check.get("unchecked_reason")
    if check.get("status") != "unchecked" or reason not in LEGACY_GAP:
        return []
    day = str(check.get("checked_at") or "")[:10] or None
    # sec.v1 never said which format it could not read, so the capability is the unnamed one (read_lockfile:unknown);
    # its note goes in detail only, after the capability is filled in, or "sec.v1:" would be read as the format.
    return [gap(LEGACY_GAP[reason]) | {"detail": f"sec.v1: {reason}", "first_seen": day, "last_seen": day}]


def gaps_of(record: Any) -> list[dict[str, Any]]:
    """Every gap of a record's security check: sec.v2's coverage gaps, or the one a sec.v1 reason stands for. A record
    never checked has none (gap_report() counts it as not run). Pure."""
    security = _security_of(record)
    if security is None:
        return []
    coverage = _get(security, "coverage")
    if coverage is not None:
        return [g if isinstance(g, dict) else g.model_dump() for g in _get(coverage, "gaps") or []]
    return legacy_gaps(security if isinstance(security, dict) else security.model_dump(mode="json"))


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
    """OSV advisory details, fetched once per id (thread-safe enough: a duplicate fetch only costs a request).
    cache_dir keeps them on disk too (offline re-assessment); a scan leaves it None so advisories are fresh."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._dir = cache_dir

    def get(self, vid: str) -> dict[str, Any]:
        with self._lock:
            hit = self._cache.get(vid)
        disk = self._dir / f"{re.sub(r'[^A-Za-z0-9._-]', '_', vid)}.json" if self._dir else None
        if hit is None and disk is not None and disk.exists():
            hit = json.loads(disk.read_text(encoding="utf-8"))
        if hit is None:
            hit = _http(f"{OSV}/vulns/{urllib.parse.quote(vid)}")
            if disk is not None:
                disk.parent.mkdir(parents=True, exist_ok=True)
                disk.write_text(json.dumps(hit), encoding="utf-8")
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


def cvss_metrics(vector: str | None) -> dict[str, str]:
    """A CVSS v3 or v4 vector's metrics, e.g. {'AV': 'N', 'UI': 'R', 'C': 'H'}."""
    return dict(p.split(":", 1) for p in (vector or "").split("/")[1:] if ":" in p)


_AV = {"N": "network", "A": "adjacent", "L": "local", "P": "physical"}
_DOS_CWES = frozenset({"CWE-400", "CWE-401", "CWE-404", "CWE-407", "CWE-674", "CWE-770", "CWE-772", "CWE-789",
                       "CWE-834", "CWE-835", "CWE-1050", "CWE-1325", "CWE-1333", "CWE-606", "CWE-776"})
_DOS_WORDS = re.compile(r"denial[- ]of[- ]service|\bDoS\b|exhaust|infinite loop|\bReDoS\b|unbounded|quadratic|"
                        r"exponential|uncontrolled recursion|stack overflow|\bpanic|\bhang|\bcrash|\bOOM\b|"
                        r"out[- ]of[- ]memory|can loop", re.I)
_NOT_DOS_WORDS = re.compile(r"code execution|\bRCE\b|arbitrary|bypass|disclos|injection|traversal|overwrite|"
                            r"spoof|leak|forg|XSS|cross-site|privilege|escalat|credential|undefined behavior|"
                            r"out[- ]of[- ]bounds write|use[- ]after[- ]free", re.I)


def advisory_facts(v: dict[str, Any]) -> dict[str, Any]:
    """What an OSV advisory says, for a finding: aliases, dates, CVSS vectors, attack vector, CWE, DoS only."""
    vectors: dict[str, str] = {}
    for s in v.get("severity") or []:
        if isinstance(s, dict) and s.get("type") in ("CVSS_V3", "CVSS_V4") and s.get("score"):
            vectors.setdefault(s["type"], str(s["score"]))
    v3, v4 = vectors.get("CVSS_V3"), vectors.get("CVSS_V4")
    metrics = cvss_metrics(v3 or v4)
    cwes = sorted({str(c) for c in (v.get("database_specific") or {}).get("cwe_ids") or []})[:10]
    text = f"{v.get('summary') or ''} {(v.get('details') or '')[:600]}"
    if v3 and {"C", "I", "A"} <= set(metrics):
        dos: bool | None = metrics["C"] == "N" and metrics["I"] == "N" and metrics["A"] != "N"
    elif v4 and {"VC", "VI", "VA"} <= set(metrics):
        dos = metrics["VC"] == "N" and metrics["VI"] == "N" and metrics.get("SC", "N") == "N" \
            and metrics.get("SI", "N") == "N" and metrics["VA"] != "N"
    elif cwes:
        dos = set(cwes) <= _DOS_CWES
    elif _DOS_WORDS.search(text):
        dos = not _NOT_DOS_WORDS.search(text)
    else:
        dos = None
    return {"aliases": sorted(set(v.get("aliases") or []))[:20], "published": v.get("published"),
            "modified": v.get("modified"), "cvss_v3": v3, "cvss_v4": v4, "attack_vector": _AV.get(metrics.get("AV")),
            "cwes": cwes, "dos_only": dos}


def purl(eco: str, name: str, version: str) -> str:
    """The package URL (purl) of a package version."""
    q = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
    if eco == "npm":
        return f"pkg:npm/{'/'.join(q(p) for p in name.split('/'))}@{q(version)}"
    if eco == "pypi":
        return f"pkg:pypi/{_norm(name)}@{q(version)}"
    if eco == "crates":
        return f"pkg:cargo/{q(name)}@{q(version)}"
    return f"pkg:golang/{name}@{q(version)}"


# --- threat intelligence: CISA KEV, FIRST EPSS, fix dates ---------------------------------------------------------------


class Intel:
    """CISA's Known Exploited Vulnerabilities catalog and FIRST's EPSS scores, read once a day (cached on disk under
    ~/.pickfit/cache/security). Intel.offline() knows nothing: a finding's kev and epss then stay null."""

    def __init__(self, kev: dict[str, str] | None = None, *, kev_catalog: str | None = None,
                 epss: dict[str, tuple[float, float]] | None = None, epss_date: str | None = None,
                 day: str | None = None, fetch_epss: bool = False, cache: Path | None = None) -> None:
        self.kev = kev  # CVE -> dateAdded; None: not read
        self.kev_catalog = kev_catalog
        self.epss = epss  # CVE -> (score, percentile); None: not read
        self.epss_date = epss_date
        self.day = day
        self._fetch_epss = fetch_epss
        self._cache = cache
        self._lock = threading.Lock()

    @classmethod
    def offline(cls) -> Intel:
        return cls()

    @classmethod
    def fetch(cls, cache: Path = CACHE, *, today: str | None = None) -> Intel:
        """Today's KEV catalog (one download a day) and EPSS scores looked up as findings need them."""
        day = today or taipei_now().date().isoformat()
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"kev-{day}.json"
        if path.exists():
            catalog = json.loads(path.read_text(encoding="utf-8"))
        else:
            catalog = _http(KEV_URL)
            path.write_text(json.dumps(catalog), encoding="utf-8")
        kev = {str(v.get("cveID")): str(v.get("dateAdded")) for v in catalog.get("vulnerabilities") or []}
        epss_path = cache / f"epss-{day}.json"
        epss = {k: tuple(v) for k, v in json.loads(epss_path.read_text(encoding="utf-8")).items()} \
            if epss_path.exists() else {}
        return cls(kev, kev_catalog=str(catalog.get("catalogVersion") or catalog.get("dateReleased") or "")[:40] or None,
                   epss=epss, epss_date=day, day=day, fetch_epss=True, cache=cache)  # type: ignore[arg-type]

    def kev_of(self, cves: Iterable[str]) -> bool | None:
        return None if self.kev is None else any(c in self.kev for c in cves)

    def prefetch(self, cves: Iterable[str]) -> None:
        """Look up the EPSS scores not known yet, 100 CVEs a request."""
        if not self._fetch_epss or self.epss is None:
            return
        with self._lock:
            todo = sorted({c for c in cves if c.startswith("CVE-") and c not in self.epss})
        for i in range(0, len(todo), 100):
            chunk = todo[i:i + 100]
            try:
                got = _http(f"{EPSS_URL}?cve={','.join(chunk)}")
            except (urllib.error.URLError, TimeoutError, ValueError):
                return
            with self._lock:
                for row in got.get("data") or []:
                    self.epss[str(row.get("cve"))] = (float(row.get("epss") or 0), float(row.get("percentile") or 0))
                for c in chunk:
                    self.epss.setdefault(c, (-1.0, -1.0))  # asked, none published
                if self._cache is not None and self.day:
                    (self._cache / f"epss-{self.day}.json").write_text(json.dumps(self.epss), encoding="utf-8")

    def epss_of(self, cves: Iterable[str]) -> tuple[float, float] | None:
        if self.epss is None:
            return None
        known = [self.epss[c] for c in cves if c in self.epss and self.epss[c][0] >= 0]
        return max(known) if known else None


_SHARED: dict[str, Intel] = {}
_SHARED_LOCK = threading.Lock()


def shared_intel() -> Intel:
    """One Intel per process and day (the watch's checks); offline when CISA or FIRST cannot be reached."""
    day = taipei_now().date().isoformat()
    with _SHARED_LOCK:
        if day not in _SHARED:
            try:
                _SHARED[day] = Intel.fetch(today=day)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                _SHARED[day] = Intel.offline()
        return _SHARED[day]


class FixDates:
    """When a fixed version came out (deps.dev publishedAt), looked up once per package version."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._cache: dict[tuple[str, str, str], str | None] = {}
        self._lock = threading.Lock()

    def published(self, eco: str, name: str, version: str) -> str | None:
        if not self.enabled or eco not in DEPS_DEV_SYSTEM:
            return None
        key = (eco, name, version)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        ver = version if eco != "go" or version.startswith("v") else f"v{version}"
        url = (f"{DEPS_DEV}/systems/{DEPS_DEV_SYSTEM[eco]}/packages/{urllib.parse.quote(name, safe='')}"
               f"/versions/{urllib.parse.quote(ver, safe='')}")
        try:
            got = _http(url, tries=2).get("publishedAt")
        except (urllib.error.URLError, TimeoutError, ValueError):
            got = None
        with self._lock:
            self._cache[key] = got
        return got


# --- resolving what a fresh install brings ----------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=TIMEOUT)


@dataclass(frozen=True)
class Dep:
    """One package version the software may bring, and where it sits.

    direct: only the project's own members depend on it, so a grep of the project's source is conclusive about how it
    is called; gate: it is reached only through an optional entry point of that package (ENTRY_GATES)."""

    eco: str
    name: str
    version: str
    scope: str = "runtime"
    path: tuple[str, ...] = ()
    workspace: str | None = None
    platform: tuple[str, ...] = ()
    found_in: str | None = None
    direct: bool | None = None
    gate: str | None = None
    in_artifact: bool | None = None

    @property
    def node(self) -> Node:
        return (self.eco, self.name, self.version)


def as_dep(n: Node | Dep, **over: Any) -> Dep:
    if isinstance(n, Dep):
        return replace(n, **{k: v for k, v in over.items() if getattr(n, k) in (None, ())}) if over else n
    return Dep(n[0], n[1], n[2], **over)


def merge_deps(deps: Iterable[Dep]) -> list[Dep]:
    """One entry per package version: the most shipped scope wins (and its path); in_artifact true wins. Two reads
    in the same scope must agree for it to stay gated or depended on by the project only."""
    best: dict[Node, Dep] = {}
    for d in deps:
        have = best.get(d.node)
        if have is None:
            best[d.node] = d
            continue
        keep = d if SCOPES.index(d.scope) < SCOPES.index(have.scope) else have
        other = have if keep is d else d
        same = keep.scope == other.scope
        best[d.node] = replace(
            keep, path=keep.path or other.path, found_in=keep.found_in or other.found_in,
            in_artifact=True if True in (keep.in_artifact, other.in_artifact) else keep.in_artifact,
            direct=(bool(keep.direct and other.direct) if same and None not in (keep.direct, other.direct)
                    else keep.direct if keep.direct is not None or not same else other.direct),
            gate=(keep.gate if keep.gate == other.gate else None) if same else keep.gate)
    return list(best.values())


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


# A resolver returns every package a fresh install brings (nodes or Deps) and how many of them are real dependencies:
# neither the package itself nor a per-platform build of it. 0 means a wrapper whose dependencies are compiled in.
type Resolved = tuple[list[Any], int]


def resolve_npm(name: str) -> Resolved:
    with tempfile.TemporaryDirectory(prefix="pickfit-sec-npm-") as tmp:
        Path(tmp, "package.json").write_text('{"name":"pickfit-security-probe","version":"0.0.0","private":true}')
        r = _run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund", name], cwd=Path(tmp))
        if r.returncode:
            raise RuntimeError(f"npm resolve failed: {r.stderr.strip()[-200:]}")
        lock = json.loads(Path(tmp, "package-lock.json").read_text())
    deps = [n for n in npm_lock_nodes(lock, platform=False) if n[1] != name]
    graph = npm_graph(lock, found_in=f"registry:npm:{name}", root_label=f"npm:{name}")
    return graph.deps(ALL_OS), len(deps)


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


# --- dependency graphs: where each package sits (S4) -------------------------------------------------------------------

# Native-addon build tooling: what it pulls in builds the software, it does not run in it (OpenPets: tar under
# node-gyp). Packaging tools for Electron apps likewise.
NATIVE_BUILD_TOOLS = frozenset({
    "node-gyp", "@mapbox/node-pre-gyp", "node-pre-gyp", "prebuild-install", "prebuild", "cmake-js",
    "@electron/rebuild", "electron-rebuild", "@electron/get", "electron-builder", "electron-packager",
    "@electron/packager", "electron-winstaller", "app-builder-lib", "dmg-builder", "@electron/notarize",
    "@electron/osx-sign", "@electron/universal", "@electron-forge/cli", "@electron-forge/core"})
# Bundlers and CSS tools: build-only in a web app or a desktop app (what they emit ships, not they). A CLI may run one
# at run time, so there they stay runtime.
BUNDLERS = frozenset({
    "vite", "webpack", "rollup", "esbuild", "postcss", "autoprefixer", "tailwindcss", "@tailwindcss/postcss",
    "@tailwindcss/vite", "@tailwindcss/node", "@tailwindcss/oxide", "typescript", "terser", "@babel/core", "sass",
    "less", "parcel", "@vitejs/plugin-react", "@vitejs/plugin-vue", "lightningcss", "@swc/core", "turbo",
    "@sveltejs/kit", "@sveltejs/vite-plugin-svelte", "svelte-check", "@angular/cli", "@angular-devkit/build-angular",
    "@nuxt/kit", "electron-vite", "tsup", "unbuild"})
BUNDLER_KINDS = frozenset({"web_app", "self_hosted_web_app", "desktop_app", "browser_extension"})
# Edges into build-time code of a runtime package: Next.js processes CSS with postcss at build time.
BUILD_EDGES = frozenset({("next", "postcss")})


@dataclass(frozen=True)
class Gate:
    """A package whose code behind some entry points pulls in more than its core: what only those entries load is not
    reached when the project never imports them. `advisory` picks the package's own advisories about that code."""

    name: str
    package: str
    label: str
    entries: re.Pattern[str]
    deps: frozenset[str]
    advisory: re.Pattern[str]


# 11/19 (OpenPets): an MCP server on stdio never loads the MCP SDK's HTTP server transports, so express, hono and the
# rest (proxy-addr, body-parser...) and the SDK's own HTTP server and session advisories are present but unreachable;
# likewise its HTTP client side (SSE, OAuth) for a project that never imports it. Client advisories are matched first.
ENTRY_GATES = (
    Gate(name="mcp-sdk-http-client", package="@modelcontextprotocol/sdk",
         label="the MCP SDK's HTTP client and OAuth",
         entries=re.compile(r"""["']@modelcontextprotocol/sdk(?:["']|/client/(?:streamableHttp|sse|auth|websocket)\b)"""),
         deps=frozenset({"eventsource", "eventsource-parser"}),
         advisory=re.compile(r"\b(OAuth|client|authori[sz]ation server)\b", re.I)),
    Gate(name="mcp-sdk-http-server", package="@modelcontextprotocol/sdk", label="the MCP SDK's HTTP server transports",
         entries=re.compile(r"""["']@modelcontextprotocol/sdk(?:["']|/server/(?:streamableHttp|sse|express|auth|"""
                            r"""webStandardStreamableHttp)\b)"""),
         deps=frozenset({"express", "cors", "express-rate-limit", "raw-body", "content-type", "hono",
                         "@hono/node-server", "body-parser"}),
         advisory=re.compile(r"\b(HTTP|transports?|handlers?|DNS rebinding|SSE|Streamable|sessions?|request body|"
                             r"CORS)\b", re.I)),
)
GATES = {g.name: g for g in ENTRY_GATES}


@dataclass
class Graph:
    """A lockfile's packages and edges. roots are (label, child id, scope); edges are (child id, normal | peer)."""

    found_in: str
    eco: str
    nodes: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (name, version)
    edges: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    roots: list[tuple[str, str, str]] = field(default_factory=list)
    platform: dict[str, tuple[str, ...]] = field(default_factory=dict)
    build_tools: frozenset[str] = NATIVE_BUILD_TOOLS
    workspace_of: dict[str, str] = field(default_factory=dict)  # root label -> the folder it lives in

    def deps(self, supported: Iterable[str] = ALL_OS) -> list[Dep]:
        """Every node with its scope and shortest path. Passes run from the most shipped to the least; a node keeps
        the first one that reaches it. Never reached: runtime (an orphan entry is not proof it does not ship)."""
        supported = frozenset(supported) or ALL_OS
        best: dict[str, tuple[str, tuple[str, ...], str | None]] = {}
        parents: dict[str, set[str]] = {}
        for nid, kids in self.edges.items():
            for kid, _ in kids:
                parents.setdefault(kid, set()).add(nid)

        def walk(starts: list[tuple[str, str]], *, build: bool, peer: bool, off: bool = False,
                 cut: frozenset[tuple[str, str]] = frozenset()) -> dict[str, tuple[tuple[str, ...], str]]:
            seen: dict[str, tuple[tuple[str, ...], str]] = {}
            queue: deque[tuple[str, tuple[str, ...], str]] = deque()
            for label, kid in starts:
                if kid in self.nodes and (build or self.nodes[kid][0] not in self.build_tools):
                    queue.append((kid, (label, self.nodes[kid][0]), label))
            while queue:
                nid, path, label = queue.popleft()
                if nid in seen:
                    continue
                seen[nid] = (path, label)
                name = self.nodes[nid][0]
                for kid, kind in self.edges.get(nid, []):
                    if kid not in self.nodes or kid in seen:
                        continue
                    kname = self.nodes[kid][0]
                    if (kind == "peer" and not peer) or (kind == "off" and not off):
                        continue
                    if not build and (kname in self.build_tools or (name, kname) in BUILD_EDGES):
                        continue
                    if (name, kname) in cut:
                        continue
                    queue.append((kid, (*path, kname), label))
            return seen

        def roots(*scopes: str) -> list[tuple[str, str]]:
            return [(label, kid) for label, kid, s in self.roots if s in scopes]

        # (scope, starts, through build tools, through peer edges, through optional dependencies left off)
        passes = [("runtime", roots("runtime"), False, False, False),
                  ("build", roots("runtime", "build"), True, False, False),
                  ("peer", roots("runtime", "build", "peer"), True, True, False),
                  ("optional", roots("runtime", "build", "peer", "optional"), True, True, True),
                  ("platform", roots("platform"), True, True, True), ("test", roots("test"), True, True, True),
                  ("dev", roots("dev"), True, True, True), ("workspace", roots("workspace"), True, True, True)]
        runtime_seen: dict[str, tuple[tuple[str, ...], str]] = {}
        for scope, starts, build, peer, off in passes:
            seen = walk(starts, build=build, peer=peer, off=off)
            if scope == "runtime":
                runtime_seen = seen
            for nid, (path, label) in seen.items():
                best.setdefault(nid, (scope, path, label))
        gated: dict[str, str] = {}
        for gate in ENTRY_GATES:
            if not any(name == gate.package for name, _ in self.nodes.values()):
                continue
            cut = frozenset((gate.package, d) for d in gate.deps)
            without = walk(roots("runtime"), build=False, peer=False, cut=cut)
            for nid in runtime_seen:
                if nid not in without:
                    gated[nid] = gate.name
        out = []
        for nid, (name, version) in self.nodes.items():
            scope, path, label = best.get(nid, ("runtime", (), None))
            plat = self.platform.get(nid, ())
            if scope == "runtime" and plat and not (set(plat) & supported):
                scope = "platform"
            direct = not (parents.get(nid, set()) - {nid}) if nid in parents or path else None
            out.append(Dep(self.eco, name, version, scope, path, self.workspace_of.get(label or "", label), plat,
                           self.found_in, direct, gated.get(nid)))
        return out


def _os_list(raw: Any) -> tuple[str, ...]:
    """An os field (npm's list, pnpm's '[darwin, linux]') as pickfit's OS names; negations ('!win32') invert."""
    items = raw if isinstance(raw, list) else re.findall(r"[!\w-]+", str(raw or ""))
    plus = {OS_NAMES[i] for i in items if i in OS_NAMES}
    minus = {OS_NAMES[i[1:]] for i in items if i.startswith("!") and i[1:] in OS_NAMES}
    if plus:
        return tuple(sorted(plus))
    if minus:
        return tuple(sorted(ALL_OS - minus))
    return ()


@dataclass
class Importer:
    """A workspace member of an npm or pnpm lockfile: what it is called, whether it has a binary, its links."""

    path: str
    name: str | None = None
    bin: bool = False
    electron: bool = False
    links: list[str] = field(default_factory=list)  # other importers it depends on at run time
    runtime: bool = False  # it has dependencies of its own (not only dev ones)
    peers: frozenset[str] = frozenset()


def shipped_importers(importers: dict[str, Importer], own: set[str], kind: str | None) -> set[str]:
    """The members the software ships: those published under its own package names, and in a desktop app those with
    Electron; else the ones with a binary, or the root with dependencies; then what they link to. If none can be
    told apart, every member ships (as sec.v1 read it)."""
    picked = {p for p, i in importers.items() if i.name and _norm(i.name) in own}
    if kind == "desktop_app":
        picked |= {p for p, i in importers.items() if i.electron}
    if not picked:
        picked = {p for p, i in importers.items() if i.bin} | ({"."} if "." in importers and importers["."].runtime
                                                               else set())
    if not picked:
        return set(importers)
    stack = list(picked)
    while stack:
        for link in importers[stack.pop()].links:
            if link in importers and link not in picked:
                picked.add(link)
                stack.append(link)
    return picked


def _package_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def npm_graph(lock: dict[str, Any], *, found_in: str, root_label: str = ".", own: set[str] | None = None,
              kind: str | None = None) -> Graph:
    """A package-lock.json (v2/v3) as a graph: the root project and its workspace members are the importers."""
    packages = lock.get("packages") or {}
    graph = Graph(found_in, "npm", build_tools=NATIVE_BUILD_TOOLS | (BUNDLERS if kind in BUNDLER_KINDS else frozenset()))
    links = {path: p.get("resolved") for path, p in packages.items() if p.get("link")}

    def resolve(frm: str, name: str) -> tuple[str | None, str | None]:
        """(node id, linked importer) of `name` as Node resolves it from the folder `frm`."""
        base = frm
        while True:
            cand = f"{base}/node_modules/{name}" if base else f"node_modules/{name}"
            if cand in links:
                return None, links[cand]
            if cand in packages:
                return cand, None
            if not base:
                return None, None
            cut = base.rfind("/node_modules/")
            base = base[:cut] if cut >= 0 else ""

    for path, p in packages.items():
        if "node_modules/" in path and "version" in p and not p.get("link"):
            graph.nodes[path] = (p.get("name") or path.rsplit("node_modules/", 1)[-1], p["version"])
            if p.get("os"):
                graph.platform[path] = _os_list(p["os"])
    for path in graph.nodes:
        p = packages[path]
        for group, kind_ in (("dependencies", "normal"), ("optionalDependencies", "normal"), ("peerDependencies", "peer")):
            for name in p.get(group) or {}:
                kid, _ = resolve(path, name)
                if kid:
                    graph.edges.setdefault(path, []).append((kid, kind_))
    importers: dict[str, Importer] = {}
    roots: dict[str, list[tuple[str, str]]] = {}
    for path, p in packages.items():
        if "node_modules/" in path or p.get("link"):
            continue
        label = path or "."
        imp = Importer(label, p.get("name"), bool(p.get("bin")), False, [], bool(p.get("dependencies")),
                       frozenset(p.get("peerDependencies") or {}))
        for group, scope in (("dependencies", "runtime"), ("optionalDependencies", "runtime"),
                             ("devDependencies", "dev"), ("peerDependencies", "peer")):
            for name in p.get(group) or {}:
                if name in ("electron", "electron-nightly"):
                    imp.electron = True
                kid, linked = resolve(path, name)
                if linked is not None and scope == "runtime":
                    imp.links.append(linked)
                if kid:
                    real = "runtime" if scope == "dev" and name in ("electron", "electron-nightly") else scope
                    roots.setdefault(label, []).append((kid, real))
        importers[label] = imp
    shipped = shipped_importers(importers, own or set(), kind)
    for label, kids in roots.items():
        name = root_label if label == "." else label
        graph.workspace_of[name] = label
        for kid, scope in kids:
            graph.roots.append((name, kid, scope if label in shipped else "workspace"))
    return graph


def _pnpm_version(raw: str) -> str | None:
    """'1.3.1(peer@2)' -> '1.3.1'; workspace links, local files and git sources are not registry versions."""
    v = raw.split("(", 1)[0].strip()
    return None if not v or v.startswith(("link:", "file:", "workspace:", "git", "http")) else v


def _yaml_maps(text: str) -> dict[str, Any]:
    """The nested maps of a pnpm-lock.yaml: `key: value` and `key:` lines nested by indentation. List items and the
    body of flow values ({...}) are kept as plain strings; that is all pnpm-lock needs here. Not a YAML parser."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line in text.splitlines():
        body = line.lstrip(" ")
        if not body or body.startswith(("#", "- ")):
            continue
        indent = len(line) - len(body)
        m = re.match(r"""^('(?:[^']|'')*'|"[^"]*"|[^:'"][^:]*?|[^:]+?):(?:\s+(.*))?$""", body)
        if not m:
            continue
        key = m.group(1)
        if key[:1] in "'\"":
            key = key[1:-1].replace("''", "'")
        value = (m.group(2) or "").strip()
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if value and value != "{}":
            parent[key] = value.strip("'\"")
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def pnpm_graph(text: str, *, found_in: str = "pnpm-lock.yaml", repo: Path | None = None, base: str = "",
               own: set[str] | None = None, kind: str | None = None, skip: re.Pattern[str] = PERIPHERAL) -> Graph:
    """A pnpm-lock.yaml (lockfile v6 to v9) as a graph. Importers outside the parts a user does not install are the
    roots; a dependency an importer's package.json lists as a peer, and a package's declared peers, are peer edges;
    devDependencies are dev, except `electron`, whose runtime is packaged into the app it builds. `repo` and `base`
    (the lockfile's folder in it) let the importers' package.json files be read."""
    lock = _yaml_maps(text)
    version = str(lock.get("lockfileVersion", "")).strip("'\"")
    if not re.match(r"^(6|7|8|9)(\.|$)", version):
        raise ValueError(f"pnpm lockfile version {version or 'unknown'} is not supported")
    entries: dict[str, dict[str, Any]] = {}
    for section in ("packages", "snapshots"):  # v6 keeps edges in packages, v9 in snapshots
        for key, entry in (lock.get(section) or {}).items():
            if isinstance(entry, dict):
                entries.setdefault(key.lstrip("/"), {}).update(entry)
    graph = Graph(found_in, "npm", build_tools=NATIVE_BUILD_TOOLS | (BUNDLERS if kind in BUNDLER_KINDS else frozenset()))

    def add(name: str, ver: str) -> str | None:
        plain = _pnpm_version(ver)
        if plain is None:
            return None
        start = f"{name}@{ver}"
        if start in graph.nodes:
            return start
        work = [(start, name, ver, plain)]
        graph.nodes[start] = (name, plain)
        while work:
            nid, n, v, pl = work.pop()
            entry = entries.get(nid) or entries.get(f"{n}@{pl}") or {}
            decl = entries.get(f"{n}@{pl}") or entry
            peers = set(decl.get("peerDependencies") or {}) if isinstance(decl.get("peerDependencies"), dict) else set()
            if decl.get("os"):
                graph.platform[nid] = _os_list(decl["os"])
            for group in ("dependencies", "optionalDependencies"):
                deps = entry.get(group)
                for dep, dep_ver in (deps.items() if isinstance(deps, dict) else []):
                    dplain = _pnpm_version(str(dep_ver))
                    if dplain is None:
                        continue
                    kid = f"{dep}@{dep_ver}"
                    if kid not in graph.nodes:
                        graph.nodes[kid] = (dep, dplain)
                        work.append((kid, dep, str(dep_ver), dplain))
                    graph.edges.setdefault(nid, []).append((kid, "peer" if dep in peers else "normal"))
        return start

    importers_raw = lock.get("importers") or {".": lock}  # a lockfile without workspaces lists them at the top
    importers: dict[str, Importer] = {}
    roots: dict[str, list[tuple[str, str]]] = {}
    for path, importer in importers_raw.items():
        if not isinstance(importer, dict) or (path != "." and skip.search(path.strip("./") + "/")):
            continue
        pkg = _package_json(repo / base / path / "package.json") if repo is not None else {}
        peers = frozenset(pkg.get("peerDependencies") or {})
        imp = Importer(path, pkg.get("name"), bool(pkg.get("bin")), False, [],
                       bool(importer.get("dependencies") or importer.get("optionalDependencies")), peers)
        for group in ("dependencies", "optionalDependencies", "devDependencies"):
            for name, spec in (importer.get(group) or {}).items():
                ver = spec.get("version", "") if isinstance(spec, dict) else str(spec)
                if name in ("electron", "electron-nightly"):
                    imp.electron = True
                if ver.startswith("link:"):
                    if group != "devDependencies":
                        imp.links.append(os.path.normpath(os.path.join(path, ver[5:])).replace("\\", "/"))
                    continue
                kid = add(name, ver)
                if kid is None:
                    continue
                if group == "devDependencies":
                    scope = "runtime" if name in ("electron", "electron-nightly") else "dev"
                else:
                    scope = "peer" if name in peers else "runtime"
                roots.setdefault(path, []).append((kid, scope))
        importers[path] = imp
    shipped = shipped_importers(importers, own or set(), kind)
    for path, kids in roots.items():
        label = path if not base else f"{base}/{path}".rstrip("/.") or "."
        graph.workspace_of[label] = path
        for kid, scope in kids:
            graph.roots.append((label, kid, scope if path in shipped else "workspace"))
    return graph


def pnpm_lock_nodes(text: str, *, skip: re.Pattern[str] = PERIPHERAL) -> list[Node]:
    """What a pnpm-lock.yaml (lockfile v6 or v9) installs, as sec.v1 counted it: everything but development
    dependencies (electron excepted), of every importer outside the parts a user does not install."""
    return list(dict.fromkeys(d.node for d in pnpm_graph(text, skip=skip).deps() if d.scope != "dev"))


# Cargo: the members' Cargo.toml say which dependencies are normal, dev or build, optional (and whether a default
# feature turns them on) and target-specific; Cargo.lock gives the rest of the graph (over-approximated: every edge
# counts, since Cargo.lock does not say which features of a registry crate are on).


def cfg_matches(expr: str, os_name: str) -> bool:
    """Whether a Cargo target (`cfg(...)` or a triple) can hold on an OS; predicates it cannot tell hold."""
    expr = expr.strip().strip("'\"")
    if not expr.startswith("cfg("):
        t = expr.lower()
        return (("windows" in t and os_name == "windows") or (("apple" in t or "darwin" in t) and os_name == "macos")
                or ("linux" in t and os_name == "linux"))
    tokens = re.findall(r'[A-Za-z_][\w]*|"[^"]*"|[(),=]', expr[4:-1] if expr.endswith(")") else expr[4:])
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def take() -> str:
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def pred() -> bool:
        word = take()
        if word in ("all", "any", "not") and peek() == "(":
            take()
            items = []
            while peek() not in (")", None):
                items.append(pred())
                if peek() == ",":
                    take()
            take() if peek() == ")" else None
            return all(items) if word == "all" else any(items) if word == "any" else not (items[0] if items else True)
        if peek() == "=":
            take()
            value = take().strip('"') if peek() else ""
            if word == "target_os":
                return {"macos": "macos", "linux": "linux", "windows": "windows"}.get(value) == os_name
            if word == "target_family":
                return (value == "windows") == (os_name == "windows") if value in ("windows", "unix") else False
            if word == "target_vendor":
                return os_name == "macos" if value == "apple" else True
            if word == "target_arch":
                return not value.startswith("wasm")
            return True
        if word == "windows":
            return os_name == "windows"
        if word == "unix":
            return os_name != "windows"
        return True

    try:
        return pred()
    except IndexError:
        return True


def _features_on(features: dict[str, Any], optional: set[str], start: Iterable[str]
                 ) -> tuple[set[str], dict[str, set[str]]]:
    """(the optional dependencies turned on, the features asked of each dependency) when `start` features are on."""
    on: set[str] = set()
    asked: dict[str, set[str]] = {}
    seen: set[str] = set()
    stack = [str(s) for s in start]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        if f.startswith("dep:"):
            on.add(f[4:])
        elif "/" in f:
            dep, feat = f.split("/", 1)
            weak = dep.endswith("?")
            dep = dep.rstrip("?")
            asked.setdefault(dep, set()).add(feat)
            if not weak and dep in optional:
                on.add(dep)
        elif f in features:
            stack.extend(str(x) for x in features[f] or [])
        elif f in optional:
            on.add(f)
    return on, asked


def _default_optional(manifest: dict[str, Any], optional: set[str]) -> set[str]:
    """The optional dependencies the default features turn on."""
    features = manifest.get("features") or {}
    return _features_on(features, optional, features.get("default") or [])[0]


@dataclass(frozen=True)
class CargoDep:
    """One dependency a member's Cargo.toml declares, with the features it asks of it."""

    name: str
    scope: str
    path: bool
    features: frozenset[str] = frozenset()
    default_features: bool = True


def _cargo_member_deps(manifest: dict[str, Any], workspace: dict[str, Any], supported: frozenset[str]
                       ) -> list[CargoDep]:
    """Each dependency a member's Cargo.toml declares: crate name, scope, whether it is a path dependency, and the
    features asked of it (its own `features`, and those the member's default features turn on)."""
    sections: list[tuple[str, str | None, dict[str, Any]]] = []
    for key, scope in (("dependencies", "runtime"), ("dev-dependencies", "dev"), ("build-dependencies", "build")):
        sections.append((scope, None, manifest.get(key) or {}))
        for target, body in (manifest.get("target") or {}).items():
            if isinstance(body, dict):
                sections.append((scope, target, body.get(key) or {}))
    optional = {k for _, _, deps in sections for k, spec in deps.items() if isinstance(spec, dict) and spec.get("optional")}
    features = manifest.get("features") or {}
    enabled, asked = _features_on(features, optional, features.get("default") or [])
    out = []
    for scope, target, deps in sections:
        for key, spec in deps.items():
            spec = spec if isinstance(spec, dict) else {"version": spec}
            if spec.get("workspace"):
                base = workspace.get(key) if isinstance(workspace.get(key), dict) else {}
                spec = {**base, **spec, "features": [*(base.get("features") or []), *(spec.get("features") or [])]}
            real = str(spec.get("package") or key)
            s = scope
            if s == "runtime" and spec.get("optional") and key not in enabled:
                s = "optional"
            if s == "runtime" and target is not None and not any(cfg_matches(target, o) for o in supported):
                s = "platform"
            out.append(CargoDep(real, s, "path" in spec, frozenset([*(spec.get("features") or []),
                                                                     *asked.get(key, ())]),
                                spec.get("default-features", spec.get("default_features", True)) is not False))
    return out


class CrateIndex:
    """crates.io's sparse index (index.crates.io): each version of a crate with its dependencies (optional or not,
    by target) and its features. One request per crate, kept on disk; None when it cannot be read."""

    def __init__(self, cache: Path | None = CACHE / "crates-index", *, fetch: bool = True) -> None:
        self.cache = cache
        self.fetch = fetch
        self._mem: dict[str, list[dict[str, Any]] | None] = {}
        self._lock = threading.Lock()

    @staticmethod
    def path_of(name: str) -> str:
        n = name.lower()
        return f"{len(n)}/{n}" if len(n) <= 2 else f"3/{n[0]}/{n}" if len(n) == 3 else f"{n[:2]}/{n[2:4]}/{n}"

    def versions(self, name: str) -> list[dict[str, Any]] | None:
        with self._lock:
            if name in self._mem:
                return self._mem[name]
        disk = self.cache / f"{name.lower()}.jsonl" if self.cache else None
        text = disk.read_text(encoding="utf-8") if disk is not None and disk.exists() else None
        if text is None and self.fetch:
            try:
                req = urllib.request.Request(f"https://index.crates.io/{self.path_of(name)}",
                                             headers={"User-Agent": "pickfit-security"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    text = resp.read().decode("utf-8")
            except (urllib.error.URLError, TimeoutError, ValueError):
                text = None
            if text is not None and disk is not None:
                disk.parent.mkdir(parents=True, exist_ok=True)
                disk.write_text(text, encoding="utf-8")
        rows = None
        if text is not None:
            rows = []
            for line in text.splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        with self._lock:
            self._mem[name] = rows
        return rows

    def entry(self, name: str, version: str) -> dict[str, Any] | None:
        return next((v for v in self.versions(name) or [] if v.get("vers") == version), None)


SHARED_CRATE_INDEX = CrateIndex()


def crate_optional_off(entry: dict[str, Any], features: Iterable[str], default: bool) -> set[str]:
    """The crates a crate version depends on only optionally and that the asked features leave off."""
    feats = {**(entry.get("features") or {}), **(entry.get("features2") or {})}
    deps = [d for d in entry.get("deps") or [] if (d.get("kind") or "normal") == "normal"]
    optional = {d["name"] for d in deps if d.get("optional")}
    start = [*features, *(["default"] if default and "default" in feats else [])]
    on, _ = _features_on(feats, optional, start)
    real = lambda d: str(d.get("package") or d["name"])  # noqa: E731
    always = {real(d) for d in deps if not d.get("optional") or d["name"] in on}
    return {real(d) for d in deps if d.get("optional") and d["name"] not in on} - always


def _has_binary(folder: Path, manifest: dict[str, Any]) -> bool:
    return bool(manifest.get("bin")) or (folder / "src" / "main.rs").exists() or (folder / "src" / "bin").is_dir()


def cargo_graph(text: str, *, found_in: str = "Cargo.lock", repo: Path | None = None, base: str = "",
                supported: Iterable[str] = ALL_OS, index: CrateIndex | None = None) -> Graph:
    """Cargo.lock as a graph, its roots the workspace members' dependencies as their Cargo.toml declare them. The
    members with a binary ship (with the members they depend on); a member whose Cargo.toml is not found keeps every
    dependency Cargo.lock gives it, as runtime.

    With `index` (crates.io's), a crate only the members depend on has its optional dependencies that the asked
    features leave off marked so (edge `off`): what is reached only through them is optional, not shipped. 11/19:
    quinn-proto sits in Cargo.lock under reqwest > quinn, which only reqwest's http3 feature turns on. A crate other
    crates also depend on is left as it is, since one of them may turn the feature on."""
    supported = frozenset(supported) or ALL_OS
    packages = [p for p in tomllib.loads(text).get("package", []) if "name" in p and "version" in p]
    versions: dict[str, list[str]] = {}
    for p in packages:
        versions.setdefault(p["name"], []).append(p["version"])
    graph = Graph(found_in, "crates")

    def ref(dep: str) -> str | None:
        parts = dep.split(" ")
        name = parts[0]
        if len(parts) > 1:
            return f"{name}@{parts[1]}"
        found = versions.get(name) or []
        return f"{name}@{found[0]}" if len(found) == 1 else None

    members = {}
    for p in packages:
        nid = f"{p['name']}@{p['version']}"
        if "source" in p:
            graph.nodes[nid] = (p["name"], p["version"])
        else:
            members[p["name"]] = p
    for p in packages:
        if "source" not in p:
            continue
        nid = f"{p['name']}@{p['version']}"
        for dep in p.get("dependencies") or []:
            kid = ref(str(dep))
            if kid and kid in graph.nodes:
                graph.edges.setdefault(nid, []).append((kid, "normal"))
    manifests: dict[str, tuple[Path, dict[str, Any]]] = {}
    workspace_deps: dict[str, Any] = {}
    if repo is not None:
        folder = repo / base if base else repo
        for path in sorted(folder.rglob("Cargo.toml")):
            rel = path.relative_to(folder).as_posix()
            if rel.count("/") > 3 or "/target/" in f"/{rel}" or PERIPHERAL.search(rel):
                continue
            try:
                manifest = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
            name = (manifest.get("package") or {}).get("name")
            if name in members and name not in manifests:
                manifests[name] = (path.parent, manifest)
            workspace_deps.update(((manifest.get("workspace") or {}).get("dependencies")) or {})
    member_deps: dict[str, list[CargoDep]] = {}
    for name in members:
        if name in manifests:
            member_deps[name] = _cargo_member_deps(manifests[name][1], workspace_deps, supported)
    with_bin = {n for n, (folder, m) in manifests.items() if _has_binary(folder, m)}
    shipped = set(with_bin) if with_bin else set(members)
    stack = list(shipped)
    while stack:
        for dep in member_deps.get(stack.pop(), []):
            if dep.path and dep.scope == "runtime" and dep.name in members and dep.name not in shipped:
                shipped.add(dep.name)
                stack.append(dep.name)
    asked: dict[str, tuple[set[str], bool]] = {}  # node id -> features the shipped members ask of it, default on
    for name, p in members.items():
        lock_refs = {str(d).split(" ")[0]: ref(str(d)) for d in p.get("dependencies") or []}
        if name in member_deps:
            kids = [(lock_refs.get(dep.name), dep.scope, dep) for dep in member_deps[name]]
        else:
            kids = [(kid, "runtime", None) for kid in lock_refs.values()]
        label = (manifests[name][0].relative_to(repo).as_posix() if repo is not None and name in manifests else name) or "."
        graph.workspace_of[name] = label
        for kid, scope, dep in kids:
            if kid and kid in graph.nodes:
                graph.roots.append((name, kid, scope if name in shipped else "workspace"))
                if name in shipped and scope == "runtime":
                    feats, default = asked.get(kid, (set(), False))
                    asked[kid] = (feats | set(dep.features if dep else ()), default or (dep.default_features if dep
                                                                                       else True))
    if index is not None:
        has_parent = {kid for kids in graph.edges.values() for kid, _ in kids}
        for nid, (feats, default) in asked.items():
            if nid in has_parent:
                continue  # another crate depends on it too and may turn the feature on
            entry = index.entry(*graph.nodes[nid])
            if entry is None:
                continue
            off = crate_optional_off(entry, feats, default)
            graph.edges[nid] = [(kid, "off" if graph.nodes[kid][0] in off else kind)
                                for kid, kind in graph.edges.get(nid, [])]
    return graph


def go_deps(text: str, *, found_in: str = "go.mod") -> list[Dep]:
    """go.mod's requirements; `// indirect` ones are not imported by the module's own code."""
    out = []
    for m in re.finditer(r"(?m)^\s*(?:require\s+)?([\w.\-]+\.[\w./\-]+)\s+(v[\w.\-+]+)([^\n]*)", text):
        indirect = "// indirect" in m.group(3)
        out.append(Dep("go", m.group(1), m.group(2), "runtime", (found_in, m.group(1)), found_in.rsplit("/", 1)[0]
                       if "/" in found_in else ".", (), found_in, not indirect))
    return out


@dataclass
class RepoRead:
    """What a repository's lockfiles gave. complete: a main lockfile (at the root or one folder down) yielded packages,
    and nothing at the root was left unread; otherwise `reason` says why the read is not the whole software."""

    nodes: list[Node]
    read: list[str]
    complete: bool
    reason: str | None


@dataclass
class RepoDeps:
    """repo_deps(): every package with where it sits, what was read, and whether that is the whole software (sec.v1's
    complete and reason); the components read and the gaps (sec.v2's coverage)."""

    deps: list[Dep]
    read: list[str]
    complete: bool
    reason: str | None
    components: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ReadContext:
    """What a lockfile read needs to know about the software: its own package names, its kind, its OSes; and
    crates.io's index for which optional dependencies a crate's features turn on (None: Cargo.lock as it is)."""

    own: frozenset[str] = frozenset()
    kind: str | None = None
    supported: frozenset[str] = ALL_OS
    crate_index: CrateIndex | None = None


def _main(rel: str) -> bool:
    return rel.count("/") <= 1


# Manifests of ecosystems pickfit has no reader for (OSV.dev has their advisories): file -> ecosystem, and how to count
# the packages they list when it is cheap to (a lower bound: `found` on the gap).
ADAPTER_MANIFESTS: dict[str, tuple[str, str | None]] = {
    "Gemfile.lock": ("rubygems", r"(?m)^    \S+ \("), "composer.lock": ("packagist", r'"name"\s*:'),
    "pom.xml": ("maven", r"<dependency>"), "build.gradle": ("maven", r"(?m)^\s*(?:implementation|api|compile|runtimeOnly)\b"),
    "build.gradle.kts": ("maven", r"(?m)^\s*(?:implementation|api|compile|runtimeOnly)\b"),
    "packages.lock.json": ("nuget", r'"resolved"\s*:'), "Directory.Packages.props": ("nuget", r"<PackageVersion\b"),
    "Package.resolved": ("swift", r'"identity"\s*:'), "pubspec.lock": ("pub", r"(?m)^  \S+:$"),
    "mix.lock": ("hex", r'(?m)^  "'),
}
# The manifest that goes with a lockfile pickfit has no reader for: seen alone, it counts as that ecosystem's gap.
ADAPTER_SOURCES = {"Gemfile": "rubygems", "composer.json": "packagist", "Package.swift": "swift",
                   "pubspec.yaml": "pub", "mix.exs": "hex"}
# C and C++ build files: OSV.dev has no package ecosystem for what they pull in.
C_BUILD_FILES = ("CMakeLists.txt", "meson.build", "conanfile.txt", "conanfile.py", "vcpkg.json", "configure.ac")
NPM_LOCKS = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")


def _count(pattern: str | None, text: str) -> int | None:
    return len(re.findall(pattern, text)) if pattern else None


def _yarn_entries(text: str) -> int:
    return len(re.findall(r'(?m)^"?(?:@[^@\s"/]+/)?[^@\s"]+@[^\n]*:\s*$', text))


def _npm_name(spec: str) -> str:
    """'@scope/a@^1' -> '@scope/a'; 'a@npm:1.2.3' -> 'a'."""
    at = spec.find("@", 1)
    return spec[:at] if at > 0 else spec


_YARN_KV = re.compile(r'^("(?:[^"\\]|\\.)*"|[^\s"]+?):?\s+(.+)$')


def _yarn_kv(line: str) -> tuple[str, str] | None:
    """`version "1.3.0"` (v1) and `version: 1.3.0` (berry) alike."""
    m = _YARN_KV.match(line)
    if not m:
        return None
    return m.group(1).strip('"').rstrip(":"), m.group(2).strip().strip('"')


def _yarn_blocks(text: str) -> list[dict[str, Any]]:
    """The entries of a yarn.lock, v1 or berry (v2+): each {keys, version, resolution, deps: {group: {name: range}}}."""
    blocks: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    group: str | None = None
    for line in text.splitlines():
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            cur, group = None, None
            if body.endswith(":") and body != "__metadata:":
                keys = [k.strip() for k in body[:-1].replace('"', "").split(",")]
                cur = {"keys": [k for k in keys if k], "version": None, "resolution": None, "deps": {}}
                blocks.append(cur)
            continue
        if cur is None:
            continue
        if indent == 2:
            group = None
            if body.endswith(":") and " " not in body:
                group = body[:-1].strip('"')
                cur["deps"].setdefault(group, {})
                continue
            kv = _yarn_kv(body)
            if kv and kv[0] in ("version", "resolution"):
                cur[kv[0]] = kv[1]
        elif group is not None:
            kv = _yarn_kv(body)
            if kv:
                cur["deps"][group][kv[0]] = kv[1]
    return blocks


_DEP_GROUPS = (("dependencies", "normal"), ("optionalDependencies", "normal"), ("peerDependencies", "peer"))
_ROOT_GROUPS = (("dependencies", "runtime"), ("optionalDependencies", "runtime"), ("devDependencies", "dev"),
                ("peerDependencies", "peer"))


def _root_importer(graph: Graph, manifest: dict[str, Any], resolve: Callable[[str, str], str | None], *,
                   root_label: str, own: set[str] | None, kind: str | None) -> None:
    """The lockfile's own package.json as the graph's one importer (yarn.lock and bun.lock name no importers)."""
    imp = Importer(".", manifest.get("name"), bool(manifest.get("bin")), False, [], bool(manifest.get("dependencies")),
                   frozenset(manifest.get("peerDependencies") or {}))
    kids: list[tuple[str, str]] = []
    for group, scope in _ROOT_GROUPS:
        for name, rng in (manifest.get(group) or {}).items():
            if name in ("electron", "electron-nightly"):
                imp.electron = True
            kid = resolve(name, str(rng))
            if kid:
                real = "runtime" if scope == "dev" and name in ("electron", "electron-nightly") else scope
                kids.append((kid, real))
    shipped = shipped_importers({".": imp}, own or set(), kind)
    graph.workspace_of[root_label] = "."
    for kid, scope in kids:
        graph.roots.append((root_label, kid, scope if "." in shipped else "workspace"))


def yarn_graph(text: str, *, found_in: str = "yarn.lock", manifest: dict[str, Any] | None = None,
               root_label: str = ".", own: set[str] | None = None, kind: str | None = None) -> Graph:
    """A yarn.lock (v1, or berry v2+) as a graph. Entries are keyed by descriptors (name@range); a dependency
    resolves to the entry that lists its descriptor. The package.json beside it gives the roots and their scope; an
    entry no root reaches counts as runtime, as in every graph. Workspace and link entries are not packages."""
    graph = Graph(found_in, "npm", build_tools=NATIVE_BUILD_TOOLS | (BUNDLERS if kind in BUNDLER_KINDS else frozenset()))
    by_desc: dict[str, str] = {}
    blocks = _yarn_blocks(text)
    for b in blocks:
        version = b["version"]
        if not b["keys"] or not version or "workspace:" in (b["resolution"] or "") or version.startswith("0.0.0-use"):
            continue
        nid = b["keys"][0]
        graph.nodes[nid] = (_npm_name(nid), version)
        for key in b["keys"]:
            by_desc[key] = nid

    def resolve(name: str, rng: str) -> str | None:
        for desc in (f"{name}@{rng}", f"{name}@npm:{rng}", rng if rng.startswith(name + "@") else ""):
            if desc in by_desc:
                return by_desc[desc]
        return None

    for b in blocks:
        nid = b["keys"][0] if b["keys"] else None
        if nid not in graph.nodes:
            continue
        for group, kind_ in _DEP_GROUPS:
            for name, rng in (b["deps"].get(group) or {}).items():
                kid = resolve(name, rng)
                if kid and kid != nid:
                    graph.edges.setdefault(nid, []).append((kid, kind_))
    if not graph.nodes and blocks:
        raise ValueError("no package entry with a version")
    _root_importer(graph, manifest or {}, resolve, root_label=root_label, own=own, kind=kind)
    return graph


def _bun_segments(key: str) -> list[str]:
    """'a/@s/b/c' -> ['a', '@s/b', 'c']: a bun.lock package key is the install path, one package name per level."""
    parts, out = key.split("/"), []
    i = 0
    while i < len(parts):
        if parts[i].startswith("@") and i + 1 < len(parts):
            out.append(f"{parts[i]}/{parts[i + 1]}")
            i += 2
        else:
            out.append(parts[i])
            i += 1
    return out


def bun_graph(text: str, *, found_in: str = "bun.lock", root_label: str = ".", own: set[str] | None = None,
              kind: str | None = None) -> Graph:
    """A text bun.lock (bun 1.2+, JSON with trailing commas) as a graph. `packages` is keyed by install path
    ('a', 'a/b' for a b nested under a); each value is [name@version, registry, {dependencies...}, integrity]. A
    dependency resolves from the deepest path up, as Node does. The root workspace ('') gives the roots; other
    workspaces count as workspace scope. bun.lockb (binary) is not read."""
    data = json.loads(re.sub(r",(\s*[}\]])", r"\1", text))
    if not isinstance(data, dict) or not isinstance(data.get("packages"), dict):
        raise ValueError("no packages map")
    graph = Graph(found_in, "npm", build_tools=NATIVE_BUILD_TOOLS | (BUNDLERS if kind in BUNDLER_KINDS else frozenset()))
    meta: dict[str, dict[str, Any]] = {}
    for key, value in data["packages"].items():
        if not isinstance(value, list) or not value or not isinstance(value[0], str):
            continue
        name = _npm_name(value[0])
        version = value[0][len(name) + 1:]
        if not version or ":" in version or "/" in version:  # workspace:, github:, file:, a path
            continue
        graph.nodes[key] = (name, version)
        meta[key] = next((v for v in value[1:] if isinstance(v, dict)), {})

    def resolve_from(base: str, name: str) -> str | None:
        segs = _bun_segments(base) if base else []
        for i in range(len(segs), -1, -1):
            cand = "/".join([*segs[:i], name])
            if cand in graph.nodes:
                return cand
        return None

    for key, m in meta.items():
        for group, kind_ in _DEP_GROUPS:
            for name in m.get(group) or {}:
                kid = resolve_from(key, name)
                if kid and kid != key:
                    graph.edges.setdefault(key, []).append((kid, kind_))
    workspaces = data.get("workspaces") or {}
    _root_importer(graph, workspaces.get("") or {}, lambda name, _rng: resolve_from("", name), root_label=root_label,
                   own=own, kind=kind)
    for path, ws in workspaces.items():
        if not path or not isinstance(ws, dict):
            continue
        graph.workspace_of[path] = path
        for group, _scope in _ROOT_GROUPS:
            for name in ws.get(group) or {}:
                kid = resolve_from(path, name) or resolve_from("", name)
                if kid:
                    graph.roots.append((path, kid, "workspace"))
    return graph


def _covered_by(folder: str, locks: set[str]) -> bool:
    """A lockfile in the folder or one above it covers a manifest there (a workspace's root lockfile)."""
    parts = folder.split("/") if folder else []
    return any("/".join(parts[:i]) in locks for i in range(len(parts), -1, -1))


def repo_deps(root: Path, ctx: ReadContext = ReadContext(), *, resolve_python: bool = True) -> RepoDeps:
    """Read a cloned repository's lockfiles. A lockfile counts as read only when it yields packages. Python projects are
    resolved from pyproject.toml as pip and uv do (each on its own), a lockfile beside it standing in when that fails;
    resolve_python=False reads only the lockfiles (re-assessing needs where packages sit, not a new resolve).

    Alongside the packages: each lockfile read (a scanned component) and each gap in the taxonomy: a manifest no
    lockfile covers, a lockfile pickfit cannot read or that failed to parse, an ecosystem it has no reader for, C/C++
    build files, a pyproject.toml that did not resolve, or nothing recognizable at all."""
    deps: list[Dep] = []
    read: list[str] = []
    components: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    main_read = unsupported = root_unreadable = root_unresolved = False
    pyprojects: list[Path] = []
    py_locks: dict[Path, list[Path]] = {}
    npm_lock_dirs: set[str] = set()
    cargo_lock_dirs: set[str] = set()
    manifests: list[tuple[str, str, int | None]] = []  # (ecosystem, path, packages listed) a lockfile may cover
    adapter_seen: set[tuple[str, str]] = set()
    recognized = False

    def took(rel: str, got: list[Dep], eco: str) -> None:
        nonlocal main_read
        if got:
            deps.extend(got)
            read.append(rel)
            main_read |= _main(rel.split(" (", 1)[0])
            components.append({"ecosystem": eco, "component": rel.split(" (", 1)[0][:200], "status": "scanned",
                               "packages": len({d.node for d in got}), "gaps": []})

    def missed(code: str, eco: str, rel: str, detail: str, found: int | None = None) -> None:
        gaps.append(gap(code, eco, rel[:200], detail, found=found))
        components.append({"ecosystem": eco, "component": rel[:200], "status": "not_scanned", "packages": found or 0,
                           "gaps": [code]})

    def flat(nodes: list[Node], found_in: str) -> list[Dep]:
        return [Dep(*n, path=(found_in, n[1]), found_in=found_in) for n in nodes]

    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root).as_posix()
        if not f.is_file() or ".git/" in rel or PERIPHERAL.search(rel) or rel.count("/") > 3:
            continue
        name = f.name
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        try:
            if name in ("package-lock.json", "npm-shrinkwrap.json"):
                recognized = True
                npm_lock_dirs.add(folder)
                lock = json.loads(f.read_text(encoding="utf-8"))
                took(rel, npm_graph(lock, found_in=rel, own=set(ctx.own), kind=ctx.kind).deps(ctx.supported), "npm")
            elif name == "pnpm-lock.yaml":
                recognized = True
                npm_lock_dirs.add(folder)
                text = f.read_text(encoding="utf-8")
                try:
                    graph = pnpm_graph(text, found_in=rel, repo=root, base=folder, own=set(ctx.own), kind=ctx.kind)
                except ValueError as err:
                    if "not supported" not in str(err):
                        raise
                    missed("lockfile.unsupported_format", "npm", rel, f"pnpm_lock_v5 {err}",
                           len(re.findall(r"(?m)^  /", text)))
                    root_unreadable |= "/" not in rel
                    continue
                took(rel, graph.deps(ctx.supported), "npm")
            elif name == "Cargo.lock":
                recognized = True
                cargo_lock_dirs.add(folder)
                took(rel, cargo_graph(f.read_text(encoding="utf-8"), found_in=rel, repo=root, base=folder,
                                      supported=ctx.supported, index=ctx.crate_index).deps(ctx.supported), "crates")
            elif name == "go.mod":
                recognized = True
                took(rel, go_deps(f.read_text(encoding="utf-8"), found_in=rel), "go")
            elif name == "pyproject.toml" and _main(rel):
                recognized = True
                pyprojects.append(f)
            elif name in ("uv.lock", "poetry.lock") or re.fullmatch(r"requirements(-lock)?\.txt", name):
                recognized = True
                py_locks.setdefault(f.parent, []).append(f)
            elif name in ("yarn.lock", "bun.lock"):
                recognized = True
                npm_lock_dirs.add(folder)
                text = f.read_text(encoding="utf-8", errors="replace")
                try:
                    graph = (yarn_graph(text, found_in=rel, manifest=_package_json(f.parent / "package.json"),
                                        own=set(ctx.own), kind=ctx.kind) if name == "yarn.lock" else
                             bun_graph(text, found_in=rel, own=set(ctx.own), kind=ctx.kind))
                except (ValueError, IndexError, TypeError) as err:
                    found = _yarn_entries(text) if name == "yarn.lock" else None
                    missed("lockfile.parse_error", "npm", rel, f"{name.replace('.', '_')}: {err}"[:200], found)
                    root_unreadable |= "/" not in rel
                    continue
                got = graph.deps(ctx.supported)
                if not got:
                    missed("lockfile.parse_error", "npm", rel, f"{name.replace('.', '_')}: no packages", 0)
                    root_unreadable |= "/" not in rel
                    continue
                took(rel, got, "npm")
            elif name in UNSUPPORTED_LOCKS:
                recognized = True
                unsupported = True
                root_unreadable |= "/" not in rel
                npm_lock_dirs.add(folder)
                text = f.read_text(encoding="utf-8", errors="replace") if name != "bun.lockb" else ""
                found = (_yarn_entries(text) if name == "yarn.lock" else
                         len(re.findall(r'(?m)^\s{4}"[^"]+":\s*\["', text)) if name == "bun.lock" else None)
                missed("lockfile.unsupported_format", "npm", rel, f"{name.replace('.', '_')} is not read yet", found)
            elif name == "package.json":
                pkg = _package_json(f)
                listed = len(pkg.get("dependencies") or {}) + len(pkg.get("optionalDependencies") or {})
                if listed:
                    recognized = True
                    manifests.append(("npm", rel, listed))
            elif name == "Cargo.toml":
                recognized = True
                try:
                    listed = len((tomllib.loads(f.read_text(encoding="utf-8")).get("dependencies")) or {})
                except tomllib.TOMLDecodeError:
                    listed = 0
                if listed:
                    manifests.append(("crates", rel, listed))
            elif name in ("setup.py", "setup.cfg") and _main(rel):
                recognized = True
                manifests.append(("pypi", rel, None))
            elif name in ADAPTER_MANIFESTS or name in ADAPTER_SOURCES or name.endswith(".csproj"):
                recognized = True
                eco, pattern = ADAPTER_MANIFESTS.get(name, (ADAPTER_SOURCES.get(name, "nuget"), None))
                if name.endswith(".csproj"):
                    pattern = r"<PackageReference\b"
                if (eco, folder) in adapter_seen:
                    continue
                adapter_seen.add((eco, folder))
                text = f.read_text(encoding="utf-8", errors="replace")
                missed("adapter.missing", eco, rel, f"no reader for {name}", _count(pattern, text))
            elif name in C_BUILD_FILES and _main(rel):
                recognized = True
                if ("c/c++", folder) not in adapter_seen:
                    adapter_seen.add(("c/c++", folder))
                    missed("advisory_db.no_ecosystem", "c/c++", rel, f"{name}: no advisory ecosystem for C/C++ libraries")
        except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
            root_unreadable |= "/" not in rel
            missed("lockfile.parse_error", _eco_of_file(name), rel, f"{type(err).__name__}: {str(err)[:150]}")
    for eco, rel, listed in manifests:
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        locks = npm_lock_dirs if eco == "npm" else cargo_lock_dirs if eco == "crates" else set()
        if eco == "pypi":
            if any(p.parent == (root / folder) for p in pyprojects) or (root / folder) in py_locks:
                continue
        elif _covered_by(folder, locks):
            continue
        missed("lockfile.missing", eco, rel, f"{rel.rsplit('/', 1)[-1]} without a lockfile", listed)
    py_dirs = {p.parent for p in pyprojects}
    for p in pyprojects:
        rel = p.relative_to(root).as_posix()
        try:
            got = resolve_pyproject(p) if resolve_python else []
        except (RuntimeError, subprocess.TimeoutExpired):
            got = []
        if got:
            took(f"{rel} (resolved today)", flat(got, rel), "pypi")
            continue
        fallback: list[Node] = []
        for f in py_locks.get(p.parent, []):
            try:
                text = f.read_text(encoding="utf-8")
                fallback += _uv_lock_nodes(tomllib.loads(text)) if f.suffix == ".lock" else _pins(text)
            except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
        if fallback:
            label = " + ".join(f.relative_to(root).as_posix() for f in py_locks[p.parent])
            took(label, flat(fallback, label), "pypi")
        else:
            if "/" not in rel:
                root_unresolved = True  # the Python project at the root: its dependencies could not be read
            if resolve_python:
                missed("resolve.pyproject_failed", "pypi", rel, "uv pip compile --no-build did not resolve it")
    for folder, files in py_locks.items():  # Python lockfiles with no pyproject.toml beside them
        if folder in py_dirs:
            continue
        for f in files:
            rel = f.relative_to(root).as_posix()
            try:
                text = f.read_text(encoding="utf-8")
                got = flat(_uv_lock_nodes(tomllib.loads(text)) if f.suffix == ".lock" else _pins(text), rel)
                took(rel, got, "pypi")
                listed = len([ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "-"))])
                if not got and f.suffix == ".txt" and listed:
                    missed("lockfile.missing", "pypi", rel, "requirements without pinned versions", listed)
            except (ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
                root_unreadable |= "/" not in rel
                missed("lockfile.parse_error", "pypi", rel, f"{type(err).__name__}: {str(err)[:150]}")
    if not read and not gaps:  # every unchecked read names why
        gaps.append(gap("lockfile.none_found", "unknown", None, "the manifests list no runtime dependencies" if recognized
                        else "no manifest or lockfile pickfit recognizes"))
    reason = ("lockfile_not_supported" if root_unreadable else "resolve_failed" if root_unresolved
              else None if main_read else "lockfile_not_supported" if unsupported and not read else "no_lockfile")
    return RepoDeps(merge_deps(deps), read, reason is None, reason, components, gaps)


def _eco_of_file(name: str) -> str:
    return ("npm" if name in NPM_LOCKS or name == "package.json" else "crates" if name.startswith("Cargo")
            else "go" if name == "go.mod" else "pypi" if name.endswith((".lock", ".txt", ".toml")) else "unknown")


def repo_nodes(root: Path) -> RepoRead:
    """repo_deps() as sec.v1 read it: every package but development dependencies."""
    got = repo_deps(root)
    return RepoRead([d.node for d in got.deps if d.scope != "dev"], got.read, got.complete, got.reason)


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


# --- what the project's source does (S4) -------------------------------------------------------------------------------

LANG_EXT = {"npm": (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".mts", ".cts", ".vue", ".svelte", ".astro"),
            "crates": (".rs",), "go": (".go",), "pypi": (".py",)}
_SKIP_DIRS = re.compile(r"(^|/)(node_modules|target|dist|build|out|\.next|coverage|vendor)/")
_COMMENT = re.compile(r"^(//|#(?!\[)|/\*|\*|--|<!--)")


class Sources:
    """The repository's own source files outside the parts a user does not install, read as data, for the greps.
    Capped (files, bytes per file, bytes in all) so a huge repository cannot hold the check up; past a cap a search
    that finds nothing says unknown, never unreachable (`truncated`)."""

    def __init__(self, root: Path | None, *, max_files: int = 5000, max_bytes: int = 400_000,
                 max_total: int = 80_000_000) -> None:
        self.root = root
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.max_total = max_total
        self.truncated: set[str] = set()
        self._files: dict[str, list[tuple[str, str]]] = {}
        self._lock = threading.Lock()

    def files(self, eco: str) -> list[tuple[str, str]]:
        """(relative path, text) of the source files of one ecosystem's language."""
        with self._lock:
            if eco in self._files:
                return self._files[eco]
            out: list[tuple[str, str]] = []
            total = 0
            ext = LANG_EXT.get(eco, ())
            if self.root is not None and ext:
                for f in sorted(self.root.rglob("*")):
                    rel = f.relative_to(self.root).as_posix()
                    if (not rel.endswith(ext) or rel.endswith((".d.ts", ".min.js", "_test.go")) or ".git/" in rel
                            or PERIPHERAL.search(rel) or _SKIP_DIRS.search(rel) or not f.is_file()):
                        continue
                    try:
                        size = f.stat().st_size
                        if size > self.max_bytes or len(out) >= self.max_files or total + size > self.max_total:
                            self.truncated.add(eco)
                            continue
                        out.append((rel, f.read_text(encoding="utf-8", errors="replace")))
                        total += size
                    except OSError:
                        self.truncated.add(eco)
            self._files[eco] = out
            return out

    def complete(self, eco: str) -> bool:
        """Every source file of that language was read, so finding nothing means nothing is there."""
        self.files(eco)
        return eco not in self.truncated

    def find(self, pattern: re.Pattern[str], eco: str, *, also: Any = None,
             reject: re.Pattern[str] | None = None) -> str | None:
        """'path:line: text' of the first code line matching `pattern` (in a file that also matches `also`), or None.
        A comment line, or one `reject` matches (an option set to false), is not evidence."""
        for rel, text in self.files(eco):
            if also is not None and not also.search(text):
                continue
            for m in pattern.finditer(text):
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.end())
                body = text[start:end if end >= 0 else len(text)].strip()
                if _COMMENT.match(body) or (reject is not None and reject.search(body)):
                    continue
                return f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {body[:200]}"
        return None

    @property
    def available(self) -> bool:
        return self.root is not None


NEXT_CONFIGS = ("next.config.js", "next.config.mjs", "next.config.ts", "next.config.cjs", "next.config.mts")
NEXT_SERVER = frozenset({"next", "react-server-dom-webpack", "react-server-dom-turbopack", "react-server-dom-parcel"})
_CLIENT_SIDE = re.compile(r"\b(XSS|cross[- ]site scripting|client[- ]side|in the browser|open redirect|"
                          r"prototype pollution)\b", re.I)


def next_static_export(root: Path | None) -> str | None:
    """The config that makes every Next.js app in the repository a static export (`output: 'export'`: HTML and
    assets, no Next.js server), or None when there is none or one app keeps a server."""
    if root is None:
        return None
    configs = [p for p in sorted(root.rglob("next.config.*")) if p.name in NEXT_CONFIGS
               and not PERIPHERAL.search(p.relative_to(root).as_posix()) and "node_modules" not in p.parts]
    if not configs:
        return None
    for p in configs:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if not re.search(r"""\boutput\s*:\s*["']export["']""", text):
            return None
    return configs[0].relative_to(root).as_posix()


# Advisories whose precondition the summary does not name: what to grep for (S6 will extract these with a model,
# cached per advisory; until then, a few by hand). Symbols are Type::method, a plain identifier or a module path.
PRECONDITIONS: dict[str, dict[str, list[str]]] = {
    "GHSA-2v37-7h3g-55p8": {"symbols": ["customAlphabet", "customRandom"]},  # nanoid: custom generators, size 0
    "GHSA-28wg-ghj8-5hjv": {"symbols": ["nanoid/non-secure"]},  # nanoid: non-secure generators, negative size
}
_OPTION = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
# ALL_CAPS words that are not options a caller turns on: environment variables (the person sets them, not the code),
# ids and protocol names.
_NOT_OPTION = re.compile(r"^(?:\w*_PROXY|\w*_ENV|PATH|HOME|TMPDIR|NODE_\w+|NPM_\w+|RUST_\w+|CARGO_\w+|PYTHON\w*|GO\w*|"
                         r"LD_\w+|DYLD_\w+|CVE_\w+|CVSS_\w+|GHSA_\w+|HTTP_\d\w*|TLS_\w+|SSL_\w+|X509_\w+)$")
_BACKTICK = re.compile(r"`([^`\s]{3,80})`")
_PATHSYM = re.compile(r"\b([A-Z][A-Za-z0-9]+)::([a-z_][a-z0-9_]+)\b")


def advisory_tokens(v: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(options, symbols) an advisory names: ALL_CAPS options a caller turns on (ENABLE_WIKILINKS, SAFE_FOR_TEMPLATES),
    and code it names in backticks or as Type::method, or in RustSec's affected functions."""
    text = v.get("summary") or ""
    options = [t for t in _OPTION.findall(text) if not _NOT_OPTION.match(t)]
    symbols: list[str] = []
    for token in _BACKTICK.findall(text):
        token = token.rstrip("()").rstrip(":")
        if _OPTION.fullmatch(token):
            if not _NOT_OPTION.match(token):
                options.append(token)
        elif re.fullmatch(r"[A-Za-z_][\w:]*", token) and ("::" in token or "_" in token
                                                          or re.search(r"[a-z][A-Z]", token) or token[0].isupper()):
            symbols.append(token)
    symbols += [f"{m.group(1)}::{m.group(2)}" for m in _PATHSYM.finditer(text)]
    for a in v.get("affected") or []:
        for fn in ((a.get("ecosystem_specific") or {}).get("affects") or {}).get("functions") or []:
            parts = str(fn).split("::")
            symbols.append("::".join(parts[-2:]) if len(parts) > 1 else parts[0])
    for vid in (v.get("id"), *(v.get("aliases") or [])):
        extra = PRECONDITIONS.get(str(vid)) or {}
        options += extra.get("options", [])
        symbols += extra.get("symbols", [])
    return list(dict.fromkeys(options)), list(dict.fromkeys(symbols))


def _symbol_search(symbol: str) -> tuple[re.Pattern[str], re.Pattern[str] | None]:
    """(line pattern, file pattern) for a symbol: Type::method looks for `.method(` in a file naming Type."""
    if "::" in symbol:
        owner, method = symbol.rsplit("::", 1)
        owner = owner.rsplit("::", 1)[-1]
        if method[:1].islower():
            return re.compile(rf"(?:\.|::){re.escape(method)}\s*[(<]"), re.compile(rf"\b{re.escape(owner)}\b")
        return re.compile(rf"\b{re.escape(method)}\b"), None
    if "/" in symbol:
        return re.compile(re.escape(symbol)), None
    return re.compile(rf"\b{re.escape(symbol)}\b"), None


def go_imports(v: dict[str, Any], advisories: Advisories | None) -> dict[str, list[str]]:
    """The Go packages a Go advisory names (ecosystem_specific.imports) and their vulnerable symbols, read from its
    GO- record when it is a GHSA."""
    records = [v]
    if advisories is not None:
        for alias in v.get("aliases") or []:
            if str(alias).startswith("GO-"):
                try:
                    records.append(advisories.get(alias))
                except (urllib.error.URLError, TimeoutError, ValueError):
                    continue
    out: dict[str, list[str]] = {}
    for record in records:
        for a in record.get("affected") or []:
            for imp in (a.get("ecosystem_specific") or {}).get("imports") or []:
                if imp.get("path"):
                    out.setdefault(str(imp["path"]), []).extend(str(s) for s in imp.get("symbols") or [])
    return {p: list(dict.fromkeys(s)) for p, s in out.items()}


def go_import_paths(v: dict[str, Any], advisories: Advisories | None) -> list[str]:
    return list(go_imports(v, advisories))


def _go_package_name(path: str) -> str:
    """The name a Go import path is used by: its last element, without a major-version suffix (echo/v4 -> echo,
    gopkg.in/yaml.v3 -> yaml)."""
    parts = path.split("/")
    last = parts[-1] if not re.fullmatch(r"v\d+", parts[-1]) or len(parts) == 1 else parts[-2]
    return re.sub(r"\.v\d+$", "", last).replace("-", "_")


def _imports_package(eco: str, name: str) -> re.Pattern[str]:
    """A source file that imports the package: positive evidence must sit in one."""
    if eco == "npm":
        return re.compile(rf"""["']{re.escape(name)}(?:/[^"']*)?["']""")
    if eco == "pypi":
        module = re.escape(_norm(name).replace("-", "_"))
        return re.compile(rf"(?m)^\s*(?:import|from)\s+{module}\b")
    crate = re.escape(name.replace("-", "_"))
    return re.compile(rf"\b{crate}::|\buse\s+{crate}\b|\bextern\s+crate\s+{crate}\b")


class _both:
    """Two file patterns that must both match (Sources.find's `also`)."""

    def __init__(self, *patterns: re.Pattern[str]) -> None:
        self.patterns = patterns

    def search(self, text: str) -> bool:
        return all(p.search(text) for p in self.patterns)


def _off(token: str) -> re.Pattern[str]:
    """A line that names an option only to set it off (`trust_remote_code=False`): not evidence it is used."""
    return re.compile(rf"(?i)\b{re.escape(token)}\b['\"]?\s*[:=]\s*(?:false|0|none|null|off|nil)\b")


@dataclass
class Reach:
    """What the program knows about the shipped code, for the reachability of each finding."""

    sources: Sources = field(default_factory=lambda: Sources(None))
    static_export: str | None = None
    govuln: dict[str, tuple[str, str]] = field(default_factory=dict)  # OSV id -> (symbol | package | module, evidence)
    govuln_ran: bool = False
    vendor: frozenset[str] | None = None  # Go packages in vendor/modules.txt


_GO_IMPORT = re.compile(r'(?m)^\s*(?:import\s+)?(?:([A-Za-z_]\w*|\.)\s+)?"([^"\s]+)"')


def go_call(sources: Sources, path: str, symbol: str) -> str | None:
    """'file:line: text' of a call to a Go advisory's symbol in a file that imports `path`, or None. A function
    (StaticFS) is called through the name the file imports the package by; a method (Echo.StaticFS) on a value, so a
    call qualified by another package the file imports (detent.StaticFS) is not it."""
    name = symbol.rsplit(".", 1)[-1]
    call = re.compile(rf"(?:\b(\w+)|[)\]])\.{re.escape(name)}\s*\(")  # x.Name( or a chained f().Name(
    for rel, text in sources.files("go"):
        imports = {p: alias or _go_package_name(p) for alias, p in _GO_IMPORT.findall(text)}
        if path not in imports:
            continue
        own = imports[path]
        others = {a for p, a in imports.items() if p != path}
        for m in call.finditer(text):
            qualifier = m.group(1)
            if ("." in symbol and qualifier in others) or ("." not in symbol and qualifier != own):
                continue
            start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.end())
            body = text[start:end if end >= 0 else len(text)].strip()
            if not _COMMENT.match(body):
                return f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {body[:200]}"
    return None


def _go_vendor(root: Path | None) -> frozenset[str] | None:
    if root is None or not (root / "vendor" / "modules.txt").exists():
        return None
    lines = (root / "vendor" / "modules.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def reachability(f: dict[str, Any], dep: Dep, v: dict[str, Any], reach: Reach,
                 advisories: Advisories | None) -> tuple[dict[str, Any] | None, list[str]]:
    """(reachability, extra preconditions) of one finding, by program. None: nothing to go on."""
    eco = dep.eco
    pre: list[str] = []
    text = f"{v.get('summary') or ''}"
    if dep.name in NEXT_SERVER and reach.static_export and not _CLIENT_SIDE.search(text):
        return ({"method": "next_static_export", "result": "not_reachable",
                 "evidence": [f"{reach.static_export}: output 'export' (static HTML, no Next.js server)"]}, ["server_side"])
    gate = GATES.get(dep.gate or "") or next((g for g in ENTRY_GATES if g.package == dep.name
                                               and g.advisory.search(text)), None)
    if gate is not None and reach.sources.available:
        pre.append(f"entry:{gate.label}")
        hit = reach.sources.find(gate.entries, "npm")
        if hit:
            return {"method": "entry_point_grep", "result": "reachable", "evidence": [hit]}, pre
        if reach.sources.complete("npm") and reach.sources.files("npm"):
            return ({"method": "entry_point_grep", "result": "not_reachable",
                     "evidence": [f"no source file imports {gate.label} ({gate.package} entry points)"]}, pre)
    if eco == "go":
        ids = [f["advisory"], *f.get("aliases", [])]
        known = [reach.govuln[i] for i in ids if i in reach.govuln]
        if known:
            level, evidence = min(known, key=lambda k: ("symbol", "package", "module").index(k[0]))
            return ({"method": "govulncheck_binary", "result": "reachable" if level == "symbol" else "not_reachable",
                     "evidence": [evidence]}, pre)
        imports = go_imports(v, advisories)
        paths = list(imports)
        if paths:
            symbols = [s for p in paths for s in imports[p]]
            pre += [f"symbol:{p}" for p in (symbols or paths)[:3]]
            if reach.vendor is not None and not any(p in reach.vendor for p in paths):
                return ({"method": "import_grep", "result": "not_reachable",
                         "evidence": [f"vendor/modules.txt does not list {', '.join(paths[:3])}"]}, pre)
            if reach.sources.available:
                pattern = re.compile("\"(" + "|".join(re.escape(p) for p in paths) + ")\"")
                hit = reach.sources.find(pattern, "go")
                if hit:
                    # Imported: a call to a vulnerable symbol is the evidence; the import alone settles nothing. A
                    # function is called through its package's name (echo's StaticFS as middleware.StaticFS), a
                    # method on any value.
                    for path in paths:
                        for symbol in imports[path]:
                            call = go_call(reach.sources, path, symbol)
                            if call:
                                return {"method": "symbol_grep", "result": "reachable", "evidence": [call]}, pre
                    return ({"method": "import_grep", "result": "unknown",
                             "evidence": [hit, f"no call to {', '.join(symbols[:3])} found" if symbols
                                          else "the advisory names no function"]}, pre)
                if dep.direct and reach.sources.complete("go") and reach.sources.files("go"):
                    return ({"method": "import_grep", "result": "not_reachable",
                             "evidence": [f"no .go file imports {', '.join(paths[:3])}; go.mod requires "
                                          f"{dep.name} directly"]}, pre)
        return None, pre
    options, symbols = advisory_tokens(v)
    pre += [f"option:{o}" for o in options[:3]] + [f"symbol:{s}" for s in symbols[:3]]
    if not (options or symbols) or not reach.sources.available or not reach.sources.files(eco):
        return None, pre
    # Evidence that it is used sits in a file that imports the package; named only elsewhere, it is not settled.
    uses = _imports_package(eco, dep.name)
    named_elsewhere = None
    for method, token, line, also in [("option_grep", o, re.compile(rf"(?i)\b{re.escape(o)}"), None) for o in options] + \
            [("symbol_grep", s, *_symbol_search(s)) for s in symbols]:
        reject = _off(token.rsplit("::", 1)[-1])
        hit = reach.sources.find(line, eco, also=uses if also is None else _both(uses, also), reject=reject)
        if hit:
            return {"method": method, "result": "reachable", "evidence": [hit]}, pre
        named_elsewhere = named_elsewhere or reach.sources.find(line, eco, also=also, reject=reject)
    if named_elsewhere:
        return ({"method": "option_grep" if options else "symbol_grep", "result": "unknown",
                 "evidence": [named_elsewhere, f"named only in files that do not import {dep.name}"]}, pre)
    if dep.direct and reach.sources.complete(eco):
        what = ", ".join([*options, *symbols][:4])
        return ({"method": "option_grep" if options else "symbol_grep", "result": "not_reachable",
                 "evidence": [f"no source file uses {what}; only the project depends on {dep.name}"]}, pre)
    return ({"method": "option_grep" if options else "symbol_grep", "result": "unknown",
             "evidence": [f"the project's source does not use {', '.join([*options, *symbols][:4])}, but other "
                          f"packages depend on {dep.name}"]}, pre)


def cvss_preconditions(f: dict[str, Any]) -> list[str]:
    """What the CVSS vector says must hold: local access, user interaction, high privileges, high complexity."""
    m = cvss_metrics(f.get("cvss_v3") or f.get("cvss_v4"))
    out = []
    if m.get("AV") == "L":
        out.append("local_access")
    if m.get("AV") == "A":
        out.append("adjacent_network")
    if m.get("AV") == "P":
        out.append("physical_access")
    if m.get("UI") in ("R", "P", "A"):
        out.append("user_interaction")
    if m.get("PR") == "H":
        out.append("high_privileges")
    if m.get("AC") == "H" or m.get("AT") == "P":
        out.append("high_complexity")
    if f.get("dos_only"):
        out.append("denial_of_service")
    return out


# --- the policy (S5) ---------------------------------------------------------------------------------------------------


def finding_level(f: dict[str, Any]) -> str:
    """A finding's level under sec.v2. Pure."""
    if f.get("malicious"):
        return "blocked"
    if f.get("scope") not in (None, "runtime") or f.get("in_artifact") is False:
        return "not_shipped"
    r = f.get("reachability") or {}
    if r.get("method") == "next_static_export" and r.get("result") == "not_reachable":
        return "not_shipped"
    if r.get("result") == "not_reachable":
        return "present_unreachable"
    if r.get("result") == "reachable" and f.get("kev"):
        return "blocked"
    if r.get("result") == "reachable" and f.get("attack_vector") in (None, "network", "adjacent"):
        return "exposed"
    # A KEV entry with nothing to show the code reaches it stays conditional, kev true and named first in the
    # assessment's reasons (11/19 dry-run: one KEV CVE on Google's Brotli, aliased by OSV onto the Go port
    # andybalholm/brotli, would otherwise have hidden gitleaks, glance, doggo and usql).
    return "conditional"


def counted(f: dict[str, Any]) -> bool:
    """Whether a finding counts toward the record's level: high or critical, malicious, or on KEV."""
    return bool(f.get("malicious") or f.get("kev") or f.get("severity") in COUNTED)


def vex_of(f: dict[str, Any]) -> dict[str, Any]:
    level = f["level"]
    if level in ("blocked", "exposed"):
        return {"status": "affected"}
    if level == "conditional":
        return {"status": "under_investigation"}
    if level == "present_unreachable":
        return {"status": "not_affected", "justification": "vulnerable_code_not_in_execute_path"}
    return {"status": "not_affected", "justification": "component_not_present"}


def _rank(f: dict[str, Any]) -> tuple[Any, ...]:
    return (FINDING_LEVELS.index(f["level"]), not f.get("malicious"), not f.get("kev"),
            SEVERITY_RANK.get(f.get("severity", "UNKNOWN"), 5), f["package"], f["version"], f["advisory"])


def assess(findings: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    """The record's assessment of its known findings: the worst counted finding's level (or none), why, and the counted
    findings per level. What could not be checked is not here (coverage()). Pure."""
    kept = sorted((f for f in findings if f.get("counted")), key=_rank)
    counts = Counter(f["level"] for f in kept)
    level = next((lvl for lvl in FINDING_LEVELS if counts[lvl]), "none")
    reasons = [f"{'malicious' if f.get('malicious') else 'kev' if f.get('kev') else 'worst'}:{f['advisory']} "
               f"{f['package']}@{f['version']} ({f['level']})"[:200] for f in kept[:3]]
    return {"level": level, "policy_version": POLICY, "reasons": reasons,
            "counts": {lvl: counts[lvl] for lvl in FINDING_LEVELS if counts[lvl]},
            "uncounted": len(findings) - len(kept), "assessed_at": now.isoformat(timespec="seconds")}


def coverage(target: str | None, checked: int, components: list[dict[str, Any]], gaps: list[dict[str, Any]], *,
             previous: list[dict[str, Any]] | None = None, now: datetime) -> dict[str, Any]:
    """How much could be checked: complete (something checked, no gap), partial (something checked, gaps) or
    unchecked (nothing checked); packages found (checked plus what each gap is known to hide) against checked. A gap
    seen before keeps its first_seen (same code, ecosystem and component; a sec.v1 reason's, by code). Pure."""
    day = now.date().isoformat()
    first = {}
    for g in previous or []:
        first.setdefault((g.get("code"), g.get("ecosystem"), g.get("component")), g.get("first_seen"))
        first.setdefault((g.get("code"), None, None), g.get("first_seen"))
    seen: set[tuple[Any, ...]] = set()
    kept = []
    for g in gaps:
        key = (g["code"], g["ecosystem"], g["component"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(g | {"first_seen": first.get(key) or first.get((g["code"], None, None)) or day, "last_seen": day})
    state = "unchecked" if checked == 0 else "partial" if kept else "complete"
    found = checked + sum(g.get("found") or 0 for g in kept)
    return {"state": state, "target": target, "packages_found": found, "packages_checked": checked,
            "components": components, "gaps": kept}


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


def read_context(raw: dict[str, Any], crate_index: CrateIndex | None = None) -> ReadContext:
    own = own_names(raw) | {_norm(p.split(":", 1)[1]) for p in packages_of(raw) if p.startswith("npm:")}
    platforms = frozenset(p for p in raw.get("platforms") or [] if p in ALL_OS)
    return ReadContext(frozenset(own), raw.get("kind"), platforms or ALL_OS, crate_index)


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


def _osv_query(nodes: list[Node]) -> list[list[str]]:
    """OSV ids that hit each node, in order."""
    out: list[list[str]] = []
    for i in range(0, len(nodes), 500):
        chunk = nodes[i:i + 500]
        queries = [{"package": {"name": n, "ecosystem": ECOSYSTEM[e]}, "version": v} for e, n, v in chunk]
        results = _http(f"{OSV}/querybatch", {"queries": queries}).get("results", [])
        out += [[hit["id"] for hit in (res.get("vulns") or [])] for res in results]
        out += [[] for _ in range(len(chunk) - len(results))]
    return out


def findings_for(nodes: list[Node], advisories: Advisories, unrated: list[str] | None = None,
                 aliases: list[set[str]] | None = None) -> list[dict[str, Any]]:
    """sec.v1's findings: high and critical advisories (and malicious-package reports) on the given versions, one per
    vulnerability on each package version: two versions of one package hit by the same advisory are two findings,
    each with its own fixed_in (11/3: zip 4.6.1 and 8.6.0 in one app). Advisories with no severity anywhere (no GHSA
    rating, no CVSS v3) are not counted; `unrated` collects them. `aliases` collects each counted finding's IDs (its
    own and its aliases), for advisory_count."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for (eco, name, version), ids_hit in zip(nodes, _osv_query(nodes)):
        node = f"{eco}:{name}@{version}"
        for vid in ids_hit:
            v = advisories.get(vid)
            if v.get("withdrawn"):
                continue
            ids = {v["id"], *v.get("aliases", [])}
            if any(f"{node}|{a}" in seen for a in ids):
                continue
            malicious = v["id"].startswith("MAL-")
            if not malicious and informational(v):
                continue  # RUSTSEC notes: unmaintained, unsound, notice
            severity = "CRITICAL" if malicious else advisories.severity(v)
            if severity == "UNKNOWN" and unrated is not None:
                unrated.append(f"{eco}:{name}@{version} {v['id']}")
            if severity not in COUNTED:
                continue
            seen |= {f"{node}|{a}" for a in ids}
            if aliases is not None:
                aliases.append(ids)
            out.append({"package": f"{eco}:{name}", "version": version, "advisory": v["id"],
                        "cves": sorted(a for a in v.get("aliases", []) if a.startswith("CVE-"))[:10],
                        "severity": severity, "fixed_in": _fixed_above(v, eco, name, version),
                        "summary": (v.get("summary") or v.get("details") or "")[:200].strip() or v["id"],
                        "malicious": malicious})
    out.sort(key=lambda f: (not f["malicious"], f["severity"] != "CRITICAL", f["package"], f["advisory"]))
    return out


def advisory_count(aliases: list[set[str]]) -> int:
    """Distinct vulnerabilities among findings: findings whose IDs or aliases overlap are one (one vue-i18n advisory
    on vue-i18n, @intlify/core-base and @intlify/shared is one vulnerability in three findings)."""
    groups: list[set[str]] = []
    for ids in aliases:
        merged = set(ids)
        for g in [g for g in groups if g & merged]:
            merged |= g
            groups.remove(g)
        groups.append(merged)
    return len(groups)


def finding(dep: Dep, v: dict[str, Any], severity: str) -> dict[str, Any]:
    """The sec.v2 observation of one advisory on one package version (no judgement yet)."""
    malicious = v["id"].startswith("MAL-")
    facts = advisory_facts(v)
    return {"package": f"{dep.eco}:{dep.name}", "version": dep.version, "advisory": v["id"],
            "cves": sorted(a for a in v.get("aliases", []) if a.startswith("CVE-"))[:10],
            "severity": "CRITICAL" if malicious else severity,
            "fixed_in": _fixed_above(v, dep.eco, dep.name, dep.version),
            "summary": (v.get("summary") or v.get("details") or "")[:200].strip() or v["id"], "malicious": malicious,
            **facts, "purl": purl(dep.eco, dep.name, dep.version), "fix_published_at": None, "scope": dep.scope,
            "paths": [" > ".join(dep.path)[:400]] if dep.path else [], "workspace": dep.workspace,
            "platform": list(dep.platform), "found_in": dep.found_in, "in_artifact": dep.in_artifact,
            "kev": None, "epss": None, "epss_percentile": None, "intel_checked_at": None, "preconditions": [],
            "reachability": None, "vex": None, "triage": None, "counted": None, "level": None,
            "policy_version": None}


def observe(deps: list[Dep], advisories: Advisories, unrated: list[str] | None = None
            ) -> list[tuple[Dep, dict[str, Any], dict[str, Any]]]:
    """Every advisory of any severity on the given packages: (dep, OSV record, finding). An advisory and its aliases on
    one package version are one finding; malicious-package reports included, RustSec's informational notes not."""
    out: list[tuple[Dep, dict[str, Any], dict[str, Any]]] = []
    by_node: dict[str, dict[str, Any]] = {}
    for dep, ids_hit in zip(deps, _osv_query([d.node for d in deps])):
        node = f"{dep.eco}:{dep.name}@{dep.version}"
        for vid in ids_hit:
            v = advisories.get(vid)
            if v.get("withdrawn"):
                continue
            ids = {v["id"], *v.get("aliases", [])}
            malicious = v["id"].startswith("MAL-")
            if not malicious and informational(v):
                continue
            severity = "CRITICAL" if malicious else advisories.severity(v)
            have = next((by_node[f"{node}|{a}"] for a in ids if f"{node}|{a}" in by_node), None)
            if have is not None:
                if SEVERITY_RANK.get(severity, 5) < SEVERITY_RANK.get(have["severity"], 5):
                    have["severity"] = severity  # an alias rated where the first record was not
                continue
            if severity == "UNKNOWN" and unrated is not None:
                unrated.append(f"{node} {v['id']}")
            f = finding(dep, v, severity)
            for a in ids:
                by_node[f"{node}|{a}"] = f
            out.append((dep, v, f))
    return out


def judge(observed: list[tuple[Dep, dict[str, Any], dict[str, Any]]], reach: Reach, *, intel: Intel,
          fix_dates: FixDates | None, advisories: Advisories | None) -> list[dict[str, Any]]:
    """Fill each finding's intel, preconditions, reachability, level and VEX under policy sec.v2."""
    intel.prefetch(c for _, _, f in observed for c in f["cves"])
    out = []
    for dep, v, f in observed:
        cves = [*f["cves"], *[a for a in f.get("aliases", []) if a.startswith("CVE-")]]
        f["kev"] = intel.kev_of(cves)
        score = intel.epss_of(cves)
        f["epss"], f["epss_percentile"] = (round(score[0], 5), round(score[1], 5)) if score else (None, None)
        f["intel_checked_at"] = intel.day
        r, pre = reachability(f, dep, v, reach, advisories)
        f["reachability"] = r
        f["preconditions"] = list(dict.fromkeys(cvss_preconditions(f) + pre))[:8]
        f["counted"] = counted(f)
        f["level"] = finding_level(f)
        f["policy_version"] = POLICY
        f["vex"] = vex_of(f)
        if f["counted"] and f["fixed_in"] and fix_dates is not None and f["level"] in WARN_LEVELS:
            f["fix_published_at"] = fix_dates.published(dep.eco, dep.name, f["fixed_in"])
        out.append(f)
    return sorted(out, key=_rank)


# --- the installed artifact (pickfit/sbom.py) --------------------------------------------------------------------------


@dataclass
class Installed:
    """An SBOM's packages, and which ecosystems it covers: a lockfile package it does not have is not installed."""

    run_id: str | None
    tool_version: str | None
    packages: list[dict[str, Any]]
    covered: frozenset[str]
    artifacts: list[str]
    govuln: dict[str, tuple[str, str]]
    govuln_ran: bool
    errors: list[str] = field(default_factory=list)
    other: int = 0  # packages in ecosystems OSV.dev has no data for (deb, binary, ...)


def latest_passed_run(raw: dict[str, Any]) -> dict[str, Any] | None:
    """The record's latest passed run (its replay box is the one an SBOM comes from)."""
    from pickfit.schema import is_passed

    passed = [r for r in (raw.get("verification") or {}).get("runs") or []
              if r.get("id") and is_passed(str(r.get("level")))]
    return max(passed, key=lambda r: str(r.get("checked_at") or ""), default=None)


def _sbom_paths(run_id: str) -> list[Path]:
    dirs = [Path(d) for d in (os.environ.get("PICKFIT_RUNS_DIR"),) if d] + [REPO_ROOT / "runs"]
    return [d / "verify" / run_id / "sbom.json" for d in dirs] + \
        [Path.home() / ".pickfit" / "evidence" / run_id / "sbom.json"]


def installed_of(raw: dict[str, Any], sbom: Any = "auto", details_dir: Path | None = None) -> Installed | None:
    """The installed artifact of the record's latest passed run: its sbom.json beside the run's report, else the
    packages a previous scan of the same run kept in data/security/<slug>.json."""
    run = latest_passed_run(raw)
    doc: dict[str, Any] | None = sbom if isinstance(sbom, dict) else None
    if sbom == "auto" and run is not None:
        for path in _sbom_paths(str(run["id"])):
            if path.exists():
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    doc = None
                break
        if doc is None and details_dir is not None:
            prev = details_dir / f"{raw.get('slug')}.json"
            if prev.exists():
                try:
                    old = json.loads(prev.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    old = {}
                if (old.get("observation") or {}).get("run_id") == run["id"] and old.get("installed"):
                    doc = {"run_id": run["id"], "tool_version": old["observation"].get("tool_version"),
                           "packages": old["installed"],
                           "artifacts": [{"sha256": s} for s in old["observation"].get("artifact_sha256") or []]}
    if not doc or not (doc.get("packages") or doc.get("errors") or doc.get("artifacts")):
        return None
    own = {_norm(n) for n in read_context(raw).own}
    packages = [p for p in doc.get("packages") or [] if p.get("ecosystem") in ECOSYSTEM and p.get("name")
                and p.get("version")]
    covered = set()
    for eco in ECOSYSTEM:
        mine = [p for p in packages if p["ecosystem"] == eco]
        if not mine:
            continue
        if eco in ("go", "crates") and any("binary" in str(p.get("found_by") or "") for p in mine):
            covered.add(eco)  # a binary's own build data lists every module or crate compiled in
        elif any(_norm(p["name"].rsplit("/", 1)[-1]) in own or _norm(p["name"]) in own for p in mine):
            covered.add(eco)  # the software's own package, with what installed beside it
    govuln: dict[str, tuple[str, str]] = {}
    for g in doc.get("govulncheck") or []:
        osv, lvl = g.get("osv"), g.get("level")
        if osv and lvl in ("symbol", "package", "module"):
            where = f"{g.get('binary', '?')}: {g.get('function') or g.get('package') or g.get('module')}"
            if osv not in govuln or ("symbol", "package", "module").index(lvl) < \
                    ("symbol", "package", "module").index(govuln[osv][0]):
                govuln[osv] = (lvl, f"govulncheck -mode=binary {lvl} level, {where}"[:300])
    return Installed(doc.get("run_id") or (run or {}).get("id"), doc.get("tool_version"), packages, frozenset(covered),
                     [a["sha256"] for a in doc.get("artifacts") or [] if re.fullmatch(r"[0-9a-f]{64}", str(a.get("sha256")))],
                     govuln, bool(doc.get("govulncheck_ran")), [str(e)[:200] for e in doc.get("errors") or []][:5],
                     sum(1 for p in doc.get("packages") or [] if p.get("ecosystem") not in (*ECOSYSTEM, "binary", None)))


def with_installed(deps: list[Dep], inv: Installed) -> list[Dep]:
    """Lockfile packages marked in or out of the artifact (for the ecosystems its SBOM covers); the SBOM's own
    packages added as runtime. A registry resolve is today's install, so its packages stay unmarked."""
    have = {(p["ecosystem"], _norm(p["name"]) if p["ecosystem"] == "pypi" else p["name"], str(p["version"]))
            for p in inv.packages}
    out = []
    for d in deps:
        key = (d.eco, _norm(d.name) if d.eco == "pypi" else d.name, d.version)
        if d.eco in inv.covered and not str(d.found_in or "").startswith("registry:"):
            out.append(replace(d, in_artifact=key in have))
        else:
            out.append(d)
    known = {(d.eco, _norm(d.name) if d.eco == "pypi" else d.name, d.version) for d in deps}
    for p in inv.packages:
        key = (p["ecosystem"], _norm(p["name"]) if p["ecosystem"] == "pypi" else p["name"], str(p["version"]))
        if key not in known:
            known.add(key)
            where = (p.get("locations") or [None])[0]
            out.append(Dep(p["ecosystem"], p["name"], str(p["version"]), "runtime",
                           ("installed", *([where] if where else []), p["name"]), None, (), f"sbom:{inv.run_id}",
                           None, None, True))
    return out


# --- the check -----------------------------------------------------------------------------------------------------------


class CheckResult(dict):  # type: ignore[type-arg]
    """The record's `security` (a plain dict), carrying the full observation for data/security/<slug>.json."""

    details: dict[str, Any] | None = None


def _compact(f: dict[str, Any]) -> dict[str, Any]:
    """A finding as the record keeps it: sec.v1's fields, the level and what explains it; the rest stays in details."""
    keep = ("package", "version", "advisory", "cves", "severity", "fixed_in", "summary", "malicious")
    out = {k: f[k] for k in keep}
    for k in ("level", "policy_version", "counted", "scope", "workspace", "found_in", "in_artifact", "kev", "epss",
              "fix_published_at", "attack_vector", "dos_only", "preconditions"):
        if f.get(k) not in (None, [], ""):
            out[k] = f[k]
    if f.get("paths"):
        out["paths"] = f["paths"][:1]
    if f.get("reachability"):
        r = f["reachability"]
        out["reachability"] = {"method": r["method"], "result": r["result"], "evidence": r.get("evidence", [])[:2]}
    return out


def _full(f: dict[str, Any]) -> dict[str, Any]:
    """A finding as data/security/<slug>.json keeps it: every field, nulls and empty lists left out."""
    return {k: v for k, v in f.items() if v not in (None, [], "")} | {k: f[k] for k in ("fixed_in", "malicious")}


def check(raw: dict[str, Any], advisories: Advisories, *, now: datetime, clones: Path = CLONES,
          unrated: list[str] | None = None, sbom: Any = "auto", intel: Intel | None = None,
          fix_dates: FixDates | None = None, details_dir: Path | None = None,
          crate_index: CrateIndex | None | str = "shared") -> CheckResult:
    """The security check (sec.v2 SecurityCheck as JSON) for one record; `.details` is data/security/<slug>.json.

    A complete read is the software's own dependency set in full: every one of its registry packages resolved with real
    dependencies (not a wrapper around a compiled binary), or its repository's main lockfiles yielded packages with
    nothing at the root left unread, or the installed artifact's SBOM covers it. intel None reads CISA KEV and FIRST
    EPSS once a day (shared_intel); fix_dates None asks deps.dev when a fix came out; crate_index "shared" reads
    crates.io's index (cached on disk), None leaves Cargo.lock's optional edges as they are."""
    ctx = read_context(raw, SHARED_CRATE_INDEX if crate_index == "shared" else crate_index)  # type: ignore[arg-type]
    deps: list[Dep] = []
    sources: list[str] = []
    own = packages_of(raw)
    all_resolved, wrapper = True, False
    commit: str | None = None
    repo_root: Path | None = None
    components: list[dict[str, Any]] = []
    registry_gaps: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for pkg in own:
        eco, name = pkg.split(":", 1)
        try:
            got, n = RESOLVERS[eco](name)
        except (RuntimeError, subprocess.TimeoutExpired, urllib.error.URLError) as err:
            all_resolved = False
            registry_gaps.append(gap("resolve.registry_failed", eco, pkg, f"{type(err).__name__}: {str(err)[:150]}"))
            continue
        if not got:
            all_resolved = False
            registry_gaps.append(gap("resolve.registry_failed", eco, pkg, "resolved to nothing"))
            continue
        wrapper |= n == 0
        deps += [as_dep(x, found_in=f"registry:{pkg}") for x in got]
        sources.append(f"{pkg} (fresh install, {len(got)} packages)")
        components.append({"ecosystem": eco, "component": f"registry:{pkg}", "status": "partial" if n == 0 else
                           "scanned", "packages": len(got), "gaps": ["binary.prebuilt_package"] if n == 0 else []})
        if n == 0:
            registry_gaps.append(gap("binary.prebuilt_package", eco, pkg, "the package wraps a compiled binary"))
    complete = bool(own) and all_resolved and not wrapper
    target = "registry_resolve" if complete else None
    reason: str | None = None
    if not complete:
        # A package that did not resolve, or a wrapper: what installs is in the repository's lockfiles.
        url = _repo_url(raw)
        if url is None:
            reason = "resolve_failed" if own else "no_source"
            gaps += registry_gaps or [gap("source.none", "unknown", None, "no repository and no package to read")]
        else:
            try:
                repo_root, commit = clone(url, raw["slug"], clones)
            except (RuntimeError, subprocess.TimeoutExpired) as err:
                reason = "resolve_failed"
                gaps += registry_gaps + [gap("source.clone_failed", "unknown", url, str(err)[:200])]
            else:
                repo = repo_deps(repo_root, ctx)
                deps += repo.deps
                sources += ([f"{url.removeprefix('https://')}@{commit[:12]}"] + repo.read) if repo.read else []
                complete, reason = repo.complete, repo.reason
                target = "repo_lockfile" if repo.read else target
                components += repo.components
                repo_gaps = repo.gaps or ([] if repo.complete else
                                          [gap(LEGACY_GAP.get(repo.reason or "", "lockfile.missing"), "unknown",
                                               None, f"sec.v1 reason: {repo.reason}")])
                # The registry's trouble is a gap only when the repository did not cover the software either.
                gaps += repo_gaps + ([] if repo.read and not repo_gaps else registry_gaps)
                if not complete and own and reason == "no_lockfile":
                    reason = "resolve_failed"  # its own package did not resolve to its dependencies either
    if target is None and deps:
        target = "registry_resolve"
    inv = installed_of(raw, sbom, details_dir)
    if inv is not None and inv.covered:
        deps = with_installed(deps, inv)
        sources.append(f"sbom:{inv.run_id} ({len(inv.packages)} packages installed)")
        target = "installed_artifact"
        complete, reason = True, None
        for eco in sorted(inv.covered):
            components.append({"ecosystem": eco, "component": f"sbom:{inv.run_id}", "status": "scanned",
                               "packages": sum(1 for p in inv.packages if p["ecosystem"] == eco), "gaps": []})
        gaps = [g for g in gaps if g["ecosystem"] not in inv.covered]  # what the installed artifact covers is read
    elif inv is not None and not deps:
        if inv.errors:
            gaps.append(gap("tool.sbom_error", "unknown", f"sbom:{inv.run_id}", "; ".join(inv.errors)[:300]))
        elif inv.artifacts:
            gaps.append(gap("binary.no_build_info", "unknown", f"sbom:{inv.run_id}",
                            f"{len(inv.artifacts)} installed executables list no dependencies"))
    if inv is not None and inv.other:
        gaps.append(gap("advisory_db.no_ecosystem", "other", f"sbom:{inv.run_id}",
                        "installed packages of ecosystems OSV.dev has no data for", found=inv.other))
    if not deps or gaps:
        gaps += platform_gaps(raw, inv)
    deps = merge_deps(deps)
    observed = observe(deps, advisories, unrated) if deps else []
    if intel is None:
        intel = shared_intel() if observed else Intel.offline()
    reach = Reach(Sources(repo_root), next_static_export(repo_root), inv.govuln if inv else {},
                  bool(inv and inv.govuln_ran), _go_vendor(repo_root))
    findings = judge(observed, reach, intel=intel, fix_dates=fix_dates if fix_dates is not None else FixDates(),
                     advisories=advisories)
    assessment = assess(findings, now=now)
    previous = gaps_of(raw)
    cover = coverage(target if deps else None, len(deps), components, gaps, previous=previous, now=now)
    return compose(raw, deps, findings, assessment, cover, sources=sources, target=target or "repo_lockfile",
                   commit=commit, inv=inv, intel=intel, now=now, reason=reason)


def platform_gaps(raw: dict[str, Any], inv: Installed | None) -> list[dict[str, Any]]:
    """platform.sbom_unsupported, when no SBOM was taken and every passed run is on macOS or Windows, where none is
    taken yet: an SBOM there would have closed the other gaps."""
    if inv is not None:
        return []
    from pickfit.schema import is_passed

    oses = {str(r.get("os")) for r in (raw.get("verification") or {}).get("runs") or []
            if is_passed(str(r.get("level"))) and r.get("os")}
    if oses and oses <= {"macos", "windows"}:
        return [gap("platform.sbom_unsupported", "unknown", None, f"{'_'.join(sorted(oses))} no SBOM is taken there yet")]
    return []


def compose(raw: dict[str, Any], deps: list[Dep], findings: list[dict[str, Any]], assessment: dict[str, Any],
            cover: dict[str, Any], *, sources: list[str], target: str, commit: str | None, inv: Installed | None,
            intel: Intel | None, now: datetime, reason: str | None = None) -> CheckResult:
    """The record's sec.v2 check and its details from judged findings and the coverage. An unchecked status keeps
    sec.v1's reason for readers of unchecked_reason: the read's own, else its first gap's category's."""
    level = assessment["level"]
    status = status_for(level, cover["state"])
    warn = [f for f in findings if f["counted"] and f["level"] in WARN_LEVELS]
    unreachable = [f for f in findings if f["counted"] and f["level"] == "present_unreachable"]
    if status == "unchecked":
        first = cover["gaps"][0]["category"] if cover["gaps"] else "resolve_failed"
        reason = reason or LEGACY_REASON.get(first, "resolve_failed")
    else:
        reason = None
    if cover["state"] == "unchecked":
        deps, sources = [], []
    observation = {
        "scanner": "pickfit-security", "scanner_version": VERSION, "target": target,
        "commit": commit if commit and re.fullmatch(r"[0-9a-f]{7,40}", commit) else None,
        "run_id": inv.run_id if inv else None, "tool_version": (inv.tool_version or None) if inv else None,
        "artifact_sha256": (inv.artifacts if inv else [])[:20],
        "packages": dict(sorted(Counter(d.eco for d in deps).items())),
        "scopes": dict(sorted(Counter(d.scope for d in deps).items(), key=lambda kv: SCOPES.index(kv[0]))),
        "advisories_fetched_at": now.isoformat(timespec="seconds"),
        "kev_catalog": intel.kev_catalog if intel else None,
        "epss_date": intel.epss_date if intel and intel.epss is not None else None,
        "findings_total": len(findings)}
    if observation["tool_version"]:
        observation["tool_version"] = str(observation["tool_version"])[:60]
    record_cover = cover | {"components": cover["components"][:RECORD_COVERAGE], "gaps": cover["gaps"][:RECORD_COVERAGE]}
    security = CheckResult({
        "version": VERSION, "status": status, "unchecked_reason": reason, "sources": sources[:20],
        "packages_checked": len(deps), "findings_total": len(warn),
        "advisories_total": advisory_count([{f["advisory"], *f.get("aliases", [])} for f in warn]),
        "findings": [_compact(f) for f in warn[:RECORD_WARN] + unreachable[:RECORD_UNREACHABLE]],
        "database": "OSV.dev", "checked_at": now.isoformat(timespec="seconds"),
        "observation": observation, "assessment": assessment, "coverage": record_cover})
    security.details = {"slug": raw["slug"], "version": VERSION, "observation": observation, "assessment": assessment,
                        "coverage": cover, "sources": sources[:200], "installed": inv.packages if inv else [],
                        "findings": [_full(f) for f in findings]}
    return security


# --- writing ----------------------------------------------------------------------------------------------------------


def details_dir_for(record_path: Path) -> Path:
    """data/software/<slug>.json -> data/security/ (a fixtures directory gets its own sibling)."""
    return record_path.parent.parent / "security"


def write_security(path: Path, result: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Store the check just before scores, hide a blocked record (a malicious package, or a KEV entry it may run),
    refresh scores (the cap follows), validate, and replace the file atomically; a sec.v2 check's full observation goes
    to data/security/<slug>.json first. Returns the record as written."""
    from pickfit.schema import SoftwareRecord
    from pickfit.score import refresh_scores

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("security", None)
    security = dict(result)
    details = getattr(result, "details", None)
    details_text = None
    if details is not None and security.get("version") == VERSION:
        details_text = json.dumps(details, ensure_ascii=False, indent=1) + "\n"
        security["observation"] = {**security["observation"], "details": f"security/{raw['slug']}.json",
                                   "details_sha256": hashlib.sha256(details_text.encode()).hexdigest()}
    anchor = next((k for k in ("scores", "outcomes", "sources", "evidence", "first_seen_at", "updated_at") if k in raw),
                  None)
    keys = list(raw)
    at = keys.index(anchor) if anchor else len(keys)
    raw = {k: raw[k] for k in keys[:at]} | {"security": security} | {k: raw[k] for k in keys[at:]}
    bad = [f["advisory"] for f in security["findings"] if f.get("malicious")]
    exploited = [f["advisory"] for f in security["findings"] if f.get("kev") and f.get("level") == "blocked"]
    if (bad or exploited) and raw.get("status") == "listed":
        raw["status"] = "hidden"
        raw["status_reason"] = (f"malicious package reported on OSV.dev: {', '.join(bad[:3])}" if bad else
                                f"known exploited vulnerability (CISA KEV) in what it runs: {', '.join(exploited[:3])}"
                                )[:200]
    refresh_scores(raw, now)
    raw["updated_at"] = now.isoformat(timespec="seconds")
    SoftwareRecord.model_validate(raw)
    if details_text is not None:
        target = details_dir_for(path) / f"{raw['slug']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_details = target.with_suffix(".json.tmp")
        tmp_details.write_text(details_text, encoding="utf-8")
        tmp_details.replace(target)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return raw


# --- offline re-assessment (no new package lookups) ---------------------------------------------------------------------


def reassess(raw: dict[str, Any], advisories: Advisories, *, now: datetime, clones: Path = CLONES,
             intel: Intel | None = None, details_dir: Path | None = None,
             crate_index: CrateIndex | None = None, resolve_python: bool = False) -> dict[str, Any]:
    """The level a record's stored check gets under sec.v2, without resolving or looking up packages again.

    A sec.v2 record is re-judged from data/security/<slug>.json. A sec.v1 record is estimated from the findings it
    kept (at most 60, high and critical only), each advisory read again from OSV.dev (advisories may cache them), the
    graph of a cached clone (read as it is, never fetched) and the record's own SBOM if one is on this machine.
    Coverage is estimated the same way: sec.v1's fresh-install sources as scanned components, the cached clone's
    lockfiles and gaps (resolve_python=True also re-resolves pyproject.toml, as a scan does), else the gap sec.v1's
    reason stands for. Returns {"level", "assessment", "coverage", "matched", "truncated", "findings"}; writes nothing."""
    sec = raw.get("security") or {}
    if sec.get("version") == VERSION and details_dir is not None and (details_dir / f"{raw['slug']}.json").exists():
        details = json.loads((details_dir / f"{raw['slug']}.json").read_text(encoding="utf-8"))
        findings = []
        for f in details.get("findings") or []:
            f = dict(f)
            f["counted"] = counted(f)
            f["level"] = finding_level(f)
            findings.append(f)
        a = assess(findings, now=now)
        return {"level": a["level"], "assessment": a, "coverage": details.get("coverage") or sec.get("coverage"),
                "matched": len(findings), "truncated": False, "findings": findings}
    stored = sec.get("findings") or []
    ctx = read_context(raw, crate_index)
    root: Path | None = clones / raw["slug"]
    sources = [str(s) for s in sec.get("sources") or []]
    from_repo = any(s.startswith("github.com/") for s in sources)
    registry = [re.match(r"^(\w+):(\S+) \(fresh install, (\d+) packages\)$", s) for s in sources]
    components = [{"ecosystem": m.group(1), "component": f"registry:{m.group(1)}:{m.group(2)}", "status": "scanned",
                   "packages": int(m.group(3)), "gaps": []} for m in registry if m]
    deps: dict[Node, Dep] = {}
    gaps: list[dict[str, Any]] = []
    checked = int(sec.get("packages_checked") or 0)
    via_registry_only = bool(components) and not from_repo and sec.get("status") != "unchecked"
    if not via_registry_only and _repo_url(raw) and root is not None and (root / ".git").is_dir():
        repo = repo_deps(root, ctx, resolve_python=resolve_python)
        deps = {d.node: d for d in repo.deps}
        components += repo.components
        if not resolve_python:  # sec.v1 resolved these then; without a resolve they count as it read them
            components += [{"ecosystem": "pypi", "component": s.split(" (", 1)[0], "status": "scanned", "packages": 0,
                            "gaps": []} for s in sources if s.endswith("(resolved today)")]
        gaps = repo.gaps
        checked = len(deps) + sum(c["packages"] for c in components if c["component"].startswith("registry:"))
        checked = checked or (int(sec.get("packages_checked") or 0) if components else 0)
    elif not via_registry_only:
        root = None
        gaps = legacy_gaps(sec) or ([] if checked else [gap("source.none", detail="nothing sec.v1 could read")])
    else:
        root = None
    if not (deps or components):
        checked = 0
    cover = coverage((("repo_lockfile" if deps else "registry_resolve") if checked else None), checked, components,
                     gaps + (platform_gaps(raw, None) if gaps or not checked else []), previous=legacy_gaps(sec),
                     now=now)
    inv = installed_of(raw, "auto", details_dir)
    reach = Reach(Sources(root), next_static_export(root), inv.govuln if inv else {}, bool(inv and inv.govuln_ran),
                  _go_vendor(root))
    observed = []
    matched = 0
    for s in stored:
        eco, name = s["package"].split(":", 1)
        dep = deps.get((eco, name, s["version"]))
        matched += dep is not None
        dep = dep or Dep(eco, name, s["version"], "runtime", (), None, (), "stored", None)
        try:
            v = advisories.get(s["advisory"])
        except (urllib.error.URLError, TimeoutError, ValueError):
            v = {"id": s["advisory"], "summary": s.get("summary"), "aliases": s.get("cves") or []}
        f = finding(dep, v, s["severity"])
        f["malicious"] = bool(s.get("malicious"))
        observed.append((dep, v, f))
    findings = judge(observed, reach, intel=intel or Intel.offline(), fix_dates=None, advisories=advisories)
    a = assess(findings, now=now)
    return {"level": a["level"], "assessment": a, "coverage": cover, "matched": matched,
            "truncated": (sec.get("findings_total") or 0) > len(stored), "findings": findings}


# --- the command ----------------------------------------------------------------------------------------------------------


def stale(raw: dict[str, Any], days: int, now: datetime) -> bool:
    """No check yet, or one older than `days`."""
    at = (raw.get("security") or {}).get("checked_at")
    if not at:
        return True
    try:
        return datetime.fromisoformat(at) < now - timedelta(days=days)
    except ValueError:
        return True


def main_security(args: Any) -> int:
    """`pickfit security` (wired in pickfit/cli.py)."""
    from pickfit.profiles import DEFAULT_OUT

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_OUT
    details_dir = data_dir.parent / "security"
    paths = sorted(data_dir.glob("*.json"))
    now = taipei_now()
    stale_days = getattr(args, "stale_days", None)
    if getattr(args, "gaps", False) and not (args.slug or args.all or args.unchecked or stale_days is not None):
        report = main_gaps(data_dir)
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    if args.slug:
        paths = [p for p in paths if p.stem in set(args.slug)]
    elif args.all or args.unchecked or stale_days is not None:
        records = {p: json.loads(p.read_text(encoding="utf-8")) for p in paths}
        paths = [p for p, d in records.items() if d.get("status") == "listed"
                 and (args.all or (args.unchecked and (d.get("security") or {}).get("status", "unchecked") == "unchecked")
                      or (stale_days is not None and stale(d, stale_days, now)))]
    else:
        print("pickfit security: name --slug, --all, --unchecked or --stale-days", file=sys.stderr)
        return 2
    if getattr(args, "gaps", False):
        report = gap_report(json.loads(p.read_text(encoding="utf-8")) for p in paths)
        if args.report:
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    if getattr(args, "reassess", False):
        return _main_reassess(args, paths, now, details_dir)
    advisories = Advisories()
    intel = Intel.offline() if getattr(args, "offline_intel", False) else shared_intel()
    fix_dates = FixDates()
    rows: dict[str, Any] = {}
    lock = threading.Lock()

    def one(path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        before = (raw.get("scores") or {}).get("quality", {}).get("total"), \
            ((raw.get("scores") or {}).get("treasure") or {}).get("is_treasure")
        level_before = level_of(raw) or legacy_level(raw.get("security"))
        unrated: list[str] = []
        try:
            result = check(raw, advisories, now=now, unrated=unrated, intel=intel, fix_dates=fix_dates,
                           details_dir=details_dir)
        except Exception as err:  # noqa: BLE001 - one record's trouble must not stop the run
            with lock:
                rows[path.stem] = {"error": f"{type(err).__name__}: {str(err)[:200]}"}
            return
        written = write_security(path, result, now) if args.write else raw
        scores = written.get("scores") or {}
        level = result["assessment"]["level"]
        cover = result["coverage"]
        row = {"status": result["status"], "level": level, "level_before": level_before,
               "coverage": cover["state"], "coverage_before": coverage_of(raw),
               "packages": [cover["packages_checked"], cover["packages_found"]],
               "gaps": [g["code"] for g in cover["gaps"]],
               "reason": result["unchecked_reason"], "findings": result["findings_total"],
               "counts": result["assessment"]["counts"], "target": result["observation"]["target"],
               "malicious": any(f["malicious"] for f in result["findings"]), "quality_before": before[0],
               "treasure_before": before[1], "quality": (scores.get("quality") or {}).get("total"),
               "treasure": (scores.get("treasure") or {}).get("is_treasure"), "kind": raw.get("kind"),
               "sources": result["sources"], "unrated": sorted(set(unrated))}
        with lock:
            rows[path.stem] = row
            if args.verbose:
                print(f"  {path.stem:<28} {level:<20} {row['findings']:>3} findings", file=sys.stderr)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, paths))
    summary = {"checked_at": now.isoformat(timespec="seconds"), "records": len(paths), "written": bool(args.write),
               "status": {s: sum(1 for r in rows.values() if r.get("status") == s)
                          for s in ("vulnerable", "clean", "unchecked")},
               "level": {lvl: sum(1 for r in rows.values() if r.get("level") == lvl) for lvl in LEVELS},
               "coverage": {s: sum(1 for r in rows.values() if r.get("coverage") == s) for s in COVERAGE_STATES},
               "gaps": dict(Counter(c for r in rows.values() for c in r.get("gaps", [])).most_common()),
               "errors": {k: r["error"] for k, r in rows.items() if "error" in r}, "rows": rows}
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0


def gap_report(records: Iterable[dict[str, Any]], gaps: Any = None) -> dict[str, Any]:
    """Every listed record's gaps, grouped by code, category, ecosystem, software category and platform, with the
    capabilities that would close them and how many records each leaves partial or unchecked. `gaps(raw)` defaults
    to gaps_of(). Pure: reads only the records given."""
    gaps = gaps or gaps_of
    out: dict[str, Any] = {"records": 0, "not_run": 0, "coverage": Counter(), "records_with_gaps": 0,
                           "by_code": Counter(), "by_category": Counter(), "by_ecosystem": Counter(),
                           "by_capability": Counter(), "by_software_category": Counter(), "by_platform": Counter(),
                           "by_code_and_ecosystem": Counter(), "packages_hidden": Counter()}
    for raw in records:
        out["records"] += 1
        if raw.get("security") is None:
            out["not_run"] += 1
            continue
        out["coverage"][coverage_of(raw)] += 1
        got = gaps(raw)
        if got:
            out["records_with_gaps"] += 1
        platforms = sorted({str(r.get("os")) for r in (raw.get("verification") or {}).get("runs") or [] if r.get("os")}
                           ) or ["none"]
        for code in {g["code"] for g in got}:  # a record counts once per code
            out["by_code"][code] += 1
            out["by_category"][GAP_CODES[code][0]] += 1
            out["by_software_category"][f"{raw.get('category') or 'unknown'}:{code}"] += 1
            for os_name in platforms:
                out["by_platform"][f"{os_name}:{code}"] += 1
        for g in got:
            out["by_ecosystem"][g.get("ecosystem") or "unknown"] += 1
            out["by_capability"][g.get("capability") or "unknown"] += 1
            out["by_code_and_ecosystem"][f"{g['code']}:{g.get('ecosystem') or 'unknown'}"] += 1
            out["packages_hidden"][g["code"]] += g.get("found") or 0
    return {k: dict(v.most_common()) if isinstance(v, Counter) else v for k, v in out.items()}


def main_gaps(data_dir: Path) -> dict[str, Any]:
    """`pickfit security --gaps` and scripts/security_gaps.py: gap_report() over the listed records. Read only."""
    records = []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("status") == "listed":
            records.append(raw)
    return gap_report(records)


def _main_reassess(args: Any, paths: list[Path], now: datetime, details_dir: Path) -> int:
    """--reassess: each record's level under sec.v2 from what it stores; never writes."""
    if args.write:
        print("pickfit security: --reassess never writes; run without it to scan and --write", file=sys.stderr)
        return 2
    advisories = Advisories(CACHE / "advisories")
    intel = Intel.offline() if getattr(args, "offline_intel", False) else shared_intel()
    rows: dict[str, Any] = {}
    lock = threading.Lock()

    def one(path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            got = reassess(raw, advisories, now=now, intel=intel, details_dir=details_dir,
                           crate_index=SHARED_CRATE_INDEX)
        except Exception as err:  # noqa: BLE001
            with lock:
                rows[path.stem] = {"error": f"{type(err).__name__}: {str(err)[:200]}"}
            return
        with lock:
            rows[path.stem] = {"before": level_of(raw) or legacy_level(raw.get("security")), "level": got["level"],
                               "coverage": (got["coverage"] or {}).get("state"),
                               "gaps": [g["code"] for g in (got["coverage"] or {}).get("gaps") or []],
                               "counts": got["assessment"]["counts"], "matched": got["matched"],
                               "stored": len((raw.get("security") or {}).get("findings") or []),
                               "truncated": got["truncated"]}

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, paths))
    summary = {"reassessed_at": now.isoformat(timespec="seconds"), "records": len(paths), "written": False,
               "level": {lvl: sum(1 for r in rows.values() if r.get("level") == lvl) for lvl in LEVELS},
               "coverage": {s: sum(1 for r in rows.values() if r.get("coverage") == s) for s in COVERAGE_STATES},
               "gaps": dict(Counter(c for r in rows.values() for c in r.get("gaps", [])).most_common()),
               "truncated": sum(1 for r in rows.values() if r.get("truncated")),
               "errors": {k: r["error"] for k, r in rows.items() if "error" in r}, "rows": rows}
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0
