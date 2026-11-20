"""`pickfit sbom-replay`: an installed-tree SBOM for records verified before the sandbox image could take one.

Security coverage stays partial for many records whose only gaps are ones the installed artifact's SBOM closes
(pickfit/sbom.py; security.installed_of reads it as the installed_artifact target): no lockfile, a lockfile it cannot
read, a registry or pyproject resolve that failed, a prebuilt binary without build data, or a Maven, NuGet, pub,
RubyGems or Packagist tree with no adapter. Their passed Linux runs predate syft in the image. This replays each
one's recorded install steps in a fresh box of the current image and takes the SBOM there. No model call, ever:
no verification agent, no judge, no operator; the steps are rerun as the record keeps them.

Which records (eligible()):

- listed, security coverage not "complete", and at least one gap;
- every gap's code is one an installed-tree SBOM can close (SBOM_GAPS), adapter.missing only for an ecosystem OSV.dev
  covers and syft reads installed (ADAPTER_ECOSYSTEMS). advisory_db.no_ecosystem (C/C++), source.none (web apps),
  platform.sbom_unsupported, source.clone_failed and tool.sbom_error are not;
- its latest passed run (security.latest_passed_run, the run installed_of ties an SBOM to) is a Linux sandbox run
  with install steps (a web app's browser run installs nothing). A record whose latest pass is macOS or Windows is left out even if Linux passed earlier:
  installed_of would look for that other run's SBOM, and a Linux tree saved under a macOS run would be mislabelled;
- no sbom.json for that run is on this machine yet (security._sbom_paths); one that is needs only
  `pickfit security --slug X --write`.

For each record (replay_one()), one fresh box (a build box when a step compiles Rust or Go, as sized_for_build
sizes it): the steps in order, online, with the full install time (Replayer.rerun(install=True)); the first that
fails ends it. Then the record's Linux install check, when it has one: an exit other than 0 ends it without an
SBOM (the tree is not what the record says installs); an output without the recorded version is kept as a version
drift, and the SBOM then carries the version the check printed, not the recorded one. Then sbom.collect, saved as
~/.pickfit/evidence/<run_id>/sbom.json (the last place _sbom_paths looks, shared by every checkout and worktree),
with a `replay` block saying it came from this later replay, not from the run's own replay box. The box is closed
however the record ends.

--rescan then runs security.check on each record that got an SBOM (OSV.dev, deps.dev, CISA KEV, FIRST EPSS; no
model) and reports coverage before and after; --write also stores it (security.write_security), as
`pickfit security --slug X --write` would.

Cost: Modal sandbox time only. The estimate is boxes x minutes x the box's rate from modal_box.py's
CORE_USD_PER_S and GIB_USD_PER_S at its core and memory limits (an upper bound: Modal bills max(request, use) and
the request is lower). EST_MINUTES is an estimate, not a measurement: 183 Modal replay boxes in runs/verify (11/20)
were up a median 23 s, mean 76 s, p90 155 s, before any SBOM; syft, npm ls and govulncheck add a minute or more.
"""

from __future__ import annotations

import argparse
import json
import secrets
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pickfit import security
from pickfit.ledger import taipei_now
from pickfit.sbom import collect as collect_sbom
from pickfit.verify.box import COMPILES, TOOLCHAIN_LIMITS, Box, BoxError, BoxLimits

SBOM_GAPS = frozenset({"lockfile.missing", "lockfile.none_found", "lockfile.unsupported_format", "lockfile.parse_error",
                       "resolve.pyproject_failed", "resolve.registry_failed", "binary.prebuilt_package",
                       "binary.no_build_info"})
ADAPTER_ECOSYSTEMS = frozenset({"maven", "nuget", "pub", "rubygems", "packagist"})
EST_MINUTES = 5.0  # a plain box: start, install steps, the install check, the SBOM (see the module docstring)
EST_MINUTES_BUILD = 12.0  # a build box: a cargo or go build from source
LIFETIME_S = 45 * 60  # a cap only; each step still has the replay's own command limit
BUILD_CPUS = 8.0  # ModalBox.build_cpus: a build box's cores, as sized_for_build gives them
EVIDENCE_ROOT = Path.home() / ".pickfit" / "evidence"
REPORT_DIR = security.REPO_ROOT / "runs" / "sbom-replay"

# (replay id, role, build box?) -> an unstarted box
BoxFactory = Callable[[str, str, bool], Box]


@dataclass
class Candidate:
    slug: str
    path: Path
    run_id: str
    steps: tuple[str, ...]
    gaps: tuple[str, ...]
    coverage: str
    toolchain: bool
    tool_version: str | None = None
    check: dict[str, Any] | None = None  # install.linux.check: command, expected_signal

    def summary(self) -> dict[str, Any]:
        return {"slug": self.slug, "run_id": self.run_id, "gaps": list(self.gaps), "steps": len(self.steps),
                "build_box": self.toolchain, "coverage_before": self.coverage}


@dataclass
class Selection:
    eligible: list[Candidate] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # slug -> reason

    def reasons(self) -> dict[str, int]:
        return dict(Counter(r.split(":", 1)[0] if r.startswith(("gap:", "adapter:")) else r
                            for r in self.skipped.values()).most_common())


def gap_closable(g: dict[str, Any]) -> str | None:
    """None when an installed-tree SBOM can close this gap, else the reason it cannot."""
    code = str(g.get("code"))
    if code in SBOM_GAPS:
        return None
    if code == "adapter.missing":
        eco = str(g.get("ecosystem") or "unknown")
        return None if eco in ADAPTER_ECOSYSTEMS else f"adapter:{eco}"
    return f"gap:{code}"


def linux_run(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The record's latest passed run when it is a Linux sandbox run, else why not."""
    from pickfit.schema import is_passed

    latest = security.latest_passed_run(raw)
    if latest is None:
        return None, "no_linux_pass"
    if latest.get("os") != "linux" or latest.get("method") not in (None, "sandbox"):
        linux = [r for r in (raw.get("verification") or {}).get("runs") or []
                 if r.get("os") == "linux" and is_passed(str(r.get("level")))]
        return None, "latest_pass_not_linux" if linux else "no_linux_pass"
    if latest.get("web") or "chromium" in str(latest.get("runner") or ""):
        return None, "web_run"  # a web app's browser run installs nothing
    return latest, None


def install_steps(raw: dict[str, Any], run: dict[str, Any]) -> tuple[tuple[str, ...], dict[str, Any] | None]:
    """The run's install steps (the Linux install guide's when it is that run's) and the guide's check."""
    guide = (raw.get("install") or {}).get("linux") or {}
    own = guide.get("run_id") == run.get("id")
    steps = (guide.get("steps") if own and guide.get("steps") else run.get("steps")) or []
    commands = tuple(str(s.get("command")).strip() for s in steps if isinstance(s, dict) and s.get("command"))
    check = guide.get("check") if own and isinstance(guide.get("check"), dict) and \
        (guide.get("check") or {}).get("command") else None
    return tuple(c for c in commands if c), check


def classify(raw: dict[str, Any], path: Path, *, sbom_on_disk: Callable[[str], bool] | None = None
             ) -> tuple[Candidate | None, str | None]:
    """A candidate for an SBOM replay, or the reason the record is not one. Reads only the record (and whether an
    sbom.json for its run is on disk)."""
    if raw.get("status") != "listed":
        return None, "not_listed"
    state = security.coverage_of(raw)
    if state == "complete":
        return None, "complete"
    gaps = security.gaps_of(raw)
    if not gaps:
        return None, "no_gaps"
    for g in gaps:
        why = gap_closable(g)
        if why:
            return None, why
    run, why = linux_run(raw)
    if run is None:
        return None, why
    steps, check = install_steps(raw, run)
    if not steps:
        return None, "no_steps"
    run_id = str(run["id"])
    on_disk = sbom_on_disk or (lambda rid: any(p.exists() for p in security._sbom_paths(rid)))
    if on_disk(run_id):
        return None, "sbom_on_disk"
    return Candidate(slug=str(raw.get("slug") or path.stem), path=path, run_id=run_id, steps=steps,
                     gaps=tuple(sorted({str(g.get("code")) for g in gaps})), coverage=state,
                     toolchain=any(COMPILES.search(s) for s in steps), tool_version=run.get("tool_version"),
                     check=check), None


def select(paths: Iterable[Path], *, slugs: Iterable[str] | None = None, limit: int | None = None,
           sbom_on_disk: Callable[[str], bool] | None = None) -> Selection:
    wanted = set(slugs or ())
    out = Selection()
    for path in sorted(paths):
        if wanted and path.stem not in wanted:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            out.skipped[path.stem] = f"unreadable: {type(err).__name__}"
            continue
        cand, why = classify(raw, path, sbom_on_disk=sbom_on_disk)
        if cand is None:
            out.skipped[path.stem] = str(why)
        elif limit is not None and len(out.eligible) >= limit:
            out.skipped[path.stem] = "over_limit"
        else:
            out.eligible.append(cand)
    return out


def box_usd_per_second(toolchain: bool) -> float:
    """The Modal rate of the box a record gets, at its core and memory limits (ModalMachine.usd_per_second)."""
    from pickfit.verify.modal_box import CORE_USD_PER_S, GIB_USD_PER_S

    limits = BoxLimits(**TOOLCHAIN_LIMITS) if toolchain else BoxLimits()
    cpus = max(limits.cpus, BUILD_CPUS) if toolchain else limits.cpus
    return cpus / 2 * CORE_USD_PER_S + limits.memory_mb / 1024 * GIB_USD_PER_S


def estimate(cands: list[Candidate]) -> dict[str, Any]:
    plain = sum(1 for c in cands if not c.toolchain)
    build = len(cands) - plain
    usd = plain * EST_MINUTES * 60 * box_usd_per_second(False) + build * EST_MINUTES_BUILD * 60 * box_usd_per_second(True)
    return {"boxes": len(cands), "plain_boxes": plain, "build_boxes": build,
            "minutes_per_box": {"plain": EST_MINUTES, "build": EST_MINUTES_BUILD},
            "usd_per_hour": {"plain": round(box_usd_per_second(False) * 3600, 4),
                             "build": round(box_usd_per_second(True) * 3600, 4)},
            "usd": round(usd, 2),
            "formula": "plain boxes x 5 min x plain rate + build boxes x 12 min x build rate; rates from "
                       "modal_box.CORE_USD_PER_S and GIB_USD_PER_S at the limits (an upper bound); minutes are an "
                       "estimate, not a measurement",
            "model_calls": 0}


def _excerpt(text: str, limit: int = 300) -> str:
    return text.strip()[-limit:]


def replay_one(cand: Candidate, make_box: BoxFactory, *, evidence_root: Path = EVIDENCE_ROOT,
               log: Callable[[str], None] = print) -> dict[str, Any]:
    """Replay one record's install steps in a fresh box and save its SBOM; the box is closed however it ends."""
    from pickfit.verify.replay import ReplayCommand, Replayer
    from pickfit.verify.verdict import evaluate_check

    replay_id = f"sbomreplay-{cand.slug}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    row: dict[str, Any] = {**cand.summary(), "replay_id": replay_id, "steps_ran": [], "check": None,
                           "sbom": None, "error": None}
    box = make_box(replay_id, "sbom-replay", cand.toolchain)
    began = time.monotonic()
    try:
        box.start()
        box.set_network(True)
        replayer = Replayer(box, log=log)
        for i, command in enumerate(cand.steps, start=1):
            ran = replayer.rerun(ReplayCommand(i, "run_command", command), install=True)
            row["steps_ran"].append({"command": command, "exit_code": ran.exit_code, "timed_out": ran.timed_out,
                                     "seconds": ran.seconds})
            if not ran.ok:
                row["error"] = f"step {i} exited {ran.exit_code}{' (timed out)' if ran.timed_out else ''}: " \
                               f"{_excerpt(ran.stderr or ran.stdout)}"
                return row
        tool_version, drift = cand.tool_version, False
        if cand.check:
            ran = replayer.rerun(ReplayCommand(len(cand.steps) + 1, "run_command", str(cand.check["command"])))
            signal = str(cand.check.get("expected_signal") or "")
            _ok, problems = evaluate_check(ran, 0, signal)  # type: ignore[arg-type]
            output = f"{ran.stdout}\n{ran.stderr}".strip()
            row["check"] = {"command": cand.check["command"], "exit_code": ran.exit_code, "problems": problems}
            if ran.exit_code != 0 or ran.timed_out:
                row["error"] = f"install check exited {ran.exit_code}: {_excerpt(output)}"
                return row
            drift = any(p.startswith("expected_signal") for p in problems)
            if drift:  # the steps install a newer release now: say what this tree is, not what the run had
                tool_version = (output.splitlines() or [""])[0][:80] or None
        doc = collect_sbom(box, None, run_id=cand.run_id, tool_version=tool_version, log=log)
        if doc is None:
            row["error"] = "not a Linux box: no SBOM"
            return row
        doc["replay"] = {"by": "pickfit sbom-replay", "replay_id": replay_id, "of_run": cand.run_id,
                         "replayed_at": taipei_now().isoformat(timespec="seconds"), "steps": list(cand.steps),
                         "recorded_tool_version": cand.tool_version, "version_drift": drift,
                         "note": "a later replay of the run's recorded steps in a fresh box, not the run's own "
                                 "replay box"}
        target = evidence_root / cand.run_id / "sbom.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(target)
        row["sbom"] = {"path": str(target), "packages": len(doc["packages"]), "artifacts": len(doc["artifacts"]),
                       "errors": doc["errors"][:5], "version_drift": drift}
    except BoxError as err:
        row["error"] = f"box error: {str(err)[:300]}"
    except Exception as err:  # noqa: BLE001 - one record's trouble must not stop the others
        row["error"] = f"{type(err).__name__}: {str(err)[:300]}"
    finally:
        try:
            box.close()
        except Exception as err:  # noqa: BLE001
            log(f"  {cand.slug}: box close failed: {err}")
        seconds = round(time.monotonic() - began, 1)
        row["box_s"] = seconds
        row["box_usd"] = round(box.usd_per_second() * seconds, 5)
    return row


Checker = Callable[[dict[str, Any]], dict[str, Any]]


def rescan(cand: Candidate, *, write: bool, checker: Checker, now: Any) -> dict[str, Any]:
    """security.check on the record (it now finds the SBOM), coverage before and after; --write stores it."""
    raw = json.loads(cand.path.read_text(encoding="utf-8"))
    before = security.coverage_of(raw), sorted({str(g.get("code")) for g in security.gaps_of(raw)})
    result = checker(raw)
    cover = result["coverage"]
    out = {"coverage_before": before[0], "gaps_before": before[1], "coverage_after": cover["state"],
           "gaps_after": sorted({g["code"] for g in cover["gaps"]}), "target": result["observation"]["target"],
           "level": result["assessment"]["level"], "written": False}
    if write:
        security.write_security(cand.path, result, now)
        out["written"] = True
    return out


def live_factory(log: Callable[[str], None] = print) -> BoxFactory:
    """Modal boxes of the current sandbox image (syft, govulncheck, cargo-audit); a build box when steps compile."""
    from pickfit.verify.cli import box_factory

    plain = box_factory("modal", LIFETIME_S)
    build = box_factory("modal", LIFETIME_S, toolchain=True)

    def make(replay_id: str, role: str, toolchain: bool) -> Box:
        box = (build if toolchain else plain)(replay_id, role)
        cpus = getattr(box, "build_cpus", None)
        if toolchain and cpus and box.limits.cpus < cpus:
            box.limits = replace(box.limits, cpus=cpus)
        return box

    return make


def live_checker(now: Any, details_dir: Path) -> Checker:
    advisories, intel, fix_dates = security.Advisories(), security.shared_intel(), security.FixDates()
    return lambda raw: security.check(raw, advisories, now=now, intel=intel, fix_dates=fix_dates,
                                      details_dir=details_dir)


def run(args: argparse.Namespace, *, make_box: BoxFactory | None = None, checker: Checker | None = None,
        evidence_root: Path = EVIDENCE_ROOT, log: Callable[[str], None] = print) -> dict[str, Any]:
    data_dir = Path(args.data_dir)
    sel = select(data_dir.glob("*.json"), slugs=args.slug, limit=args.limit)
    now = taipei_now()
    report: dict[str, Any] = {
        "generated_at": now.isoformat(timespec="seconds"), "mode": "run" if args.run else "dry_run",
        "eligible": len(sel.eligible), "estimate": estimate(sel.eligible), "not_eligible": sel.reasons(),
        "candidates": [c.summary() for c in sel.eligible]}
    if not args.run:
        return report
    if make_box is None:
        from pickfit.verify.modal_box import ensure_published_image

        for toolchain in sorted({c.toolchain for c in sel.eligible}):  # before parallel boxes start
            ensure_published_image(log, toolchain=toolchain)
        make_box = live_factory(log)
    if (args.rescan or args.write) and checker is None:
        checker = live_checker(now, data_dir.parent / "security")
    rows: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()

    def one(cand: Candidate) -> None:
        row = replay_one(cand, make_box, evidence_root=evidence_root, log=lambda line: log(f"[{cand.slug}] {line}"))
        if row["sbom"] is not None and checker is not None:
            try:
                row["rescan"] = rescan(cand, write=args.write, checker=checker, now=now)
            except Exception as err:  # noqa: BLE001
                row["rescan"] = {"error": f"{type(err).__name__}: {str(err)[:300]}"}
        with lock:
            rows[cand.slug] = row

    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        list(pool.map(one, sel.eligible))
    rescanned = [r["rescan"] for r in rows.values() if "error" not in (r.get("rescan") or {"error": 1})]
    report.update({
        "replayed": sum(1 for r in rows.values() if r["steps_ran"]),
        "sbom_collected": sum(1 for r in rows.values() if r["sbom"]),
        "box_usd": round(sum(r.get("box_usd") or 0.0 for r in rows.values()), 4),
        "coverage": {"rescanned": len(rescanned),
                     "before": dict(Counter(r["coverage_before"] for r in rescanned)),
                     "after": dict(Counter(r["coverage_after"] for r in rescanned)),
                     "written": sum(1 for r in rescanned if r["written"])},
        "errors": {s: r["error"] for s, r in rows.items() if r["error"]} |
                  {s: r["rescan"]["error"] for s, r in rows.items() if "error" in (r.get("rescan") or {})},
        "rows": [rows[c.slug] for c in sel.eligible if c.slug in rows]})
    return report


def main(args: argparse.Namespace) -> int:
    if args.write:
        args.rescan = True
    report = run(args)
    path = Path(args.report) if args.report else \
        REPORT_DIR / f"{report['mode']}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shown = {k: v for k, v in report.items() if k not in ("candidates", "rows")}
    print(json.dumps(shown, ensure_ascii=False, indent=1))
    if not args.run:
        for c in report["candidates"]:
            print(f"  {c['slug']:<32} {c['run_id']:<48} steps {c['steps']:>2}  "
                  f"{'build ' if c['build_box'] else ''}{','.join(c['gaps'])}")
        print(f"dry run: {report['eligible']} records, about ${report['estimate']['usd']:.2f} of Modal box time; "
              f"--run to replay them (no model call)")
    elif not args.rescan:
        print("SBOMs saved; `pickfit security --slug X --write` (or --rescan/--write here) reads them")
    print(f"report: {path}")
    return 0


def add_parser(sub: Any) -> None:
    p = sub.add_parser("sbom-replay", help="replay passed Linux installs in a fresh box of the current image and take "
                                           "their SBOM, for records whose security gaps an installed tree closes "
                                           "(no model call; --run pays for Modal box time only)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="list eligible records and the cost estimate (default)")
    mode.add_argument("--run", action="store_true", help="replay them: one fresh Modal box per record (paid)")
    p.add_argument("--slug", action="append", help="only this record (repeatable)")
    p.add_argument("--limit", type=int, default=None, metavar="N", help="at most N records")
    p.add_argument("--workers", type=int, default=4, help="boxes at once (default 4)")
    p.add_argument("--rescan", action="store_true",
                   help="after the SBOM, run the security check (OSV.dev, deps.dev, KEV, EPSS; no model) and report "
                        "coverage before and after; writes nothing")
    p.add_argument("--write", action="store_true", help="--rescan, and store the check as `pickfit security --write`")
    p.add_argument("--data-dir", default="data/software", help="records (default data/software)")
    p.add_argument("--report", default=None, help=f"the JSON report (default {REPORT_DIR}/<mode>-<time>.json)")
    p.set_defaults(func=main)
