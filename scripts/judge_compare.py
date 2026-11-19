"""Ask Claude Opus and Claude Haiku 5.5 the same judge questions on saved evidence, and compare their answers.

The judges (pickfit/verify/judge.py, web_verify.py) run on Claude Opus, and stay there: on 11/17 念誠 decided
against cheaper models. This only measures how far Claude Haiku 5.5 would agree, offline, on what earlier runs
saved (docs/proposals/tokens.md, T5.3). The questions are the judges' own code with only the model changed:

- cli: judge_checks on a replay's passed checks (verdict: working / error_visible / inconclusive);
- gui: judge_gui on a replay's GUI launch screenshot (the six screens, mapped to a verdict);
- web: judge_function on a web visit's before and after screenshots (feature shown or not), for a visit whose
  record is still in data/software (read only, for its features).

Video review ("is the caption visible") is not here yet: its frames come from video.py's cutting and pointer
code, which the video work is changing; add it once that lands.

For each kind the output gives the cases, the agreement, and the count that decides a switch: the cases where
Haiku says it works (or shows) and Opus does not. A switch needs that count to be 0, and 念誠's agreement.

    uv run python scripts/judge_compare.py --dry-run                     # count cases, estimate the cost
    uv run python scripts/judge_compare.py --limit 30 --max-usd 3       # paid: about US$1.5 for 30 cases of each

Each call goes through call_meta (stage judge-compare). Screenshots are drawn and cropped in a scratch directory,
never next to a run's evidence.
"""

from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import BudgetExceeded, taipei_now
from pickfit.meta import BULK_MODEL, PROD_MODEL, call_meta

STAGE = "judge-compare"
KINDS = ("cli", "gui", "web")
MODELS = (PROD_MODEL, BULK_MODEL)
DEFAULT_MAX_USD = 3.0
# Rough cost of one case on Opus (input tokens with its images, output), for the dry run's estimate only.
OPUS_CASE_USD = {"cli": 0.025, "gui": 0.015, "web": 0.025}
HAIKU_SHARE = 0.03  # Haiku 5.5 is $0.10/$0.50 per 1M tokens against Opus 5.5's $4/$20 (2.5%), plus thinking


@dataclass
class Case:
    kind: str
    key: str  # run id (and check) or visit id
    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Answer:
    label: str | None  # cli: verdict; gui: screen; web: "shown" / "not_shown"
    positive: bool  # it works / it shows
    cost_usd: float = 0.0
    error: str | None = None


def _runs_dirs(roots: Iterable[Path]) -> list[Path]:
    return [r / "runs" for r in roots]


def _check(row: dict[str, Any], run_dir: Path) -> Any:
    """A saved replay check as the CheckResult the judges take; a screenshot path is looked up beside replay.json
    when the one saved points into a worktree that is gone."""
    from pickfit.verify.replay import CheckResult, RanCommand

    ran = dict(row.get("run") or {}) or None
    if ran and ran.get("screenshot") and not Path(ran["screenshot"]).exists():
        near = run_dir / Path(ran["screenshot"]).name
        ran["screenshot"] = str(near) if near.exists() else None
    fields = {k: row[k] for k in ("command_id", "command", "kind", "expected_exit_code", "expected_signal", "passed",
                                  "offline")}
    return CheckResult(**fields, run=RanCommand(**ran) if ran else None, problems=list(row.get("problems") or []))


def replay_cases(runs_dirs: Iterable[Path]) -> tuple[list[Case], list[Case]]:
    """(cli cases, gui cases) from every replay.json under runs/verify that passed."""
    from pickfit.verify.judge import pick_checks
    from pickfit.verify.replay import judged_launch

    cli, gui = [], []
    seen: set[str] = set()
    for runs in runs_dirs:
        for path in sorted(glob.glob(str(runs / "verify" / "verify-*" / "replay.json"))):
            run_dir = Path(path).parent
            if run_dir.name in seen:
                continue
            seen.add(run_dir.name)
            try:
                saved = json.loads(Path(path).read_text(encoding="utf-8"))
                checks = [_check(row, run_dir) for row in (saved.get("result") or {}).get("checks") or []]
            except (OSError, json.JSONDecodeError, TypeError, KeyError):
                continue
            if not (saved.get("result") or {}).get("passed"):
                continue
            name = run_dir.name.removeprefix("verify-").rsplit("-", 3)[0]
            if pick_checks(checks):
                cli.append(Case("cli", run_dir.name, name, {"checks": checks}))
            launch = judged_launch(checks)
            if launch is not None and launch.passed and launch.run and launch.run.screenshot:
                gui.append(Case("gui", run_dir.name, name, {"check": launch}))
    return cli, gui


def web_cases(runs_dirs: Iterable[Path], data_dir: Path) -> list[Case]:
    """Web visits whose own check passed, with before and after screenshots, and their record still listed."""
    from pickfit.schema import SoftwareRecord
    from pickfit.verify.web_record import target_from_record

    cases = []
    seen: set[str] = set()
    for runs in runs_dirs:
        for path in sorted(glob.glob(str(runs / "web" / "*" / "*" / "web_result.json"))):
            visit = Path(path).parent
            if visit.name in seen:
                continue
            seen.add(visit.name)
            try:
                result = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            function = result.get("function") or {}
            record_path = data_dir / f"{result.get('slug')}.json"
            if not ((function.get("check") or {}).get("passed") and (visit / "before.png").exists()
                    and (visit / "after.png").exists() and record_path.exists()):
                continue
            try:
                target = target_from_record(SoftwareRecord.model_validate_json(record_path.read_text(encoding="utf-8")))
            except ValueError:
                continue
            cases.append(Case("web", visit.name, target.name, {
                "target": target, "before": visit / "before.png", "after": visit / "after.png",
                "outcome": function.get("outcome"), "check": function.get("check")}))
    return cases


def _jpeg_b64(png: Path) -> str:
    """The judge takes JPEG, as the harness sends it; a saved PNG is converted."""
    from PIL import Image

    out = io.BytesIO()
    with Image.open(png) as image:
        image.convert("RGB").save(out, "JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode("ascii")


def ask(case: Case, model: str, work: Path, *, run_id: str, max_usd: float, **call_kwargs: Any) -> Answer:
    """One judge question, on `model`, with scratch output in `work`."""
    from pickfit.verify import judge, web_verify

    scope = f"{STAGE}:{run_id}"
    common = dict(model=model, run_id=run_id, scope=scope, scope_cap_usd=max_usd, log=lambda line: None)
    try:
        if case.kind == "cli":
            out = judge.judge_checks(case.name, case.data["checks"], work, **common, **call_kwargs)
            if out is None:
                return Answer(None, False, error="nothing to judge")
            return Answer(out.verdict, out.verdict == "working", out.cost_usd,
                          "unreadable answer" if out.problems and out.problems[0].startswith("parse") else None)
        if case.kind == "gui":
            check = case.data["check"]
            copy = work / Path(check.run.screenshot).name
            shutil.copy(check.run.screenshot, copy)  # judge_gui writes its crop beside the screenshot
            from dataclasses import replace

            moved = replace(check, run=replace(check.run, screenshot=str(copy)))
            out = judge.judge_gui(case.name, moved, work, **common, **call_kwargs)
            if out is None:
                return Answer(None, False, error="no screenshot of the app's windows")
            return Answer(out.screen, out.verdict == "working", out.cost_usd)

        def caller(endpoint: str, body: dict[str, Any], **kw: Any) -> Any:
            return call_meta(endpoint, body, **{**kw, "model": model, "scope_cap_usd": max_usd}, **call_kwargs)

        verdict, cost = web_verify.judge_function(
            case.data["target"], _jpeg_b64(case.data["before"]), _jpeg_b64(case.data["after"]),
            case.data["outcome"], case.data["check"], run_id=run_id, scope=scope, caller=caller)
        if verdict is None:
            return Answer(None, False, cost, "unreadable answer")
        return Answer("shown" if verdict.feature_shown else "not_shown", verdict.feature_shown, cost)
    except BudgetExceeded:
        raise
    except Exception as err:  # noqa: BLE001 - one case's failure is reported, the rest are asked
        return Answer(None, False, error=f"{type(err).__name__}: {str(err)[:300]}")


def compare(cases: list[Case], answers: dict[str, list[Answer]], models: tuple[str, str] = MODELS
            ) -> dict[str, Any]:
    """Per kind: the agreement, and the cases the cheaper model passes that the prod model does not."""
    prod, cheap = models
    out: dict[str, Any] = {}
    for kind in KINDS:
        rows = [(c, answers[prod][i], answers[cheap][i]) for i, c in enumerate(cases) if c.kind == kind]
        usable = [(c, a, b) for c, a, b in rows if not a.error and not b.error]
        out[kind] = {
            "cases": len(rows), "answered": len(usable),
            "same_label": sum(1 for _, a, b in usable if a.label == b.label),
            "same_verdict": sum(1 for _, a, b in usable if a.positive == b.positive),
            "cheap_passes_prod_does_not": [c.key for c, a, b in usable if b.positive and not a.positive],
            "prod_passes_cheap_does_not": [c.key for c, a, b in usable if a.positive and not b.positive],
            "differences": [{"case": c.key, prod: a.label, cheap: b.label} for c, a, b in usable if a.label != b.label],
            "errors": [{"case": c.key, prod: a.error, cheap: b.error} for c, a, b in rows if a.error or b.error],
            "cost_usd": {m: round(sum(x.cost_usd for (c, x) in zip(cases, answers[m]) if c.kind == kind), 4)
                         for m in models},
        }
    out["switch_condition"] = {"cheap_passes_prod_does_not": sum(len(out[k]["cheap_passes_prod_does_not"])
                                                                 for k in KINDS), "needs": 0}
    return out


def estimate_usd(cases: list[Case]) -> float:
    opus = sum(OPUS_CASE_USD[c.kind] for c in cases)
    return round(opus * (1 + HAIKU_SHARE), 2)


def main(argv: list[str] | None = None,
         ask_one: Callable[..., Answer] = ask) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="*", type=Path, help="checkouts whose runs/ to read (default: this one and "
                                                            "the main checkout)")
    parser.add_argument("--kind", action="append", choices=KINDS, help="only this kind (repeatable)")
    parser.add_argument("--limit", type=int, default=30, help="at most this many cases of each kind")
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data" / "software")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    parser.add_argument("--out", type=Path, help="write the comparison as JSON here")
    parser.add_argument("--dry-run", action="store_true", help="count cases and estimate the cost; no call")
    args = parser.parse_args(argv)
    main_checkout = Path(str(REPO_ROOT).split("/.claude/worktrees/")[0])
    runs = _runs_dirs(args.roots or list(dict.fromkeys([REPO_ROOT, main_checkout])))
    cli, gui = replay_cases(runs)
    found = {"cli": cli, "gui": gui, "web": web_cases(runs, args.data_dir)}
    kinds = args.kind or list(KINDS)
    cases = [c for k in kinds for c in found[k][-args.limit:]]  # the latest runs of each kind
    print(f"judge_compare: {', '.join(f'{len(found[k])} {k}' for k in KINDS)} cases saved; asking "
          f"{len(cases)} on {' and '.join(MODELS)}: about ${estimate_usd(cases):.2f}", file=sys.stderr)
    if args.dry_run or not cases:
        return 0
    run_id = f"{STAGE}-{taipei_now():%Y%m%d-%H%M%S}"
    answers: dict[str, list[Answer]] = {m: [] for m in MODELS}
    with tempfile.TemporaryDirectory(prefix="pickfit-judge-compare-") as tmp:
        for i, case in enumerate(cases):
            for model in MODELS:
                work = Path(tmp) / f"{i}-{model}"
                work.mkdir()
                try:
                    answers[model].append(ask_one(case, model, work, run_id=run_id, max_usd=args.max_usd))
                except BudgetExceeded as err:
                    print(f"judge_compare: stopped, {err}", file=sys.stderr)
                    return 1
    report = compare(cases, answers)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
