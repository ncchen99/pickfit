"""A web app visit (web_verify's web_result.json) as a verification run, and its write-back (P3.12, P5.8).

The run follows the web_app format (schema WebCheck, tests/fixtures/record_web_app.json): smoke test 0 is
`open <url>` (the page judge's main screen), then one `browser: <goal>` test per operation pickfit checked,
and one more when the operation was repeated with the network off. An operation passed only when pickfit's
own check passed and the function judge saw an advertised feature produce the result. A site is visited
once, so the run is not replayed. Only passed runs (install, function) are written, and a web app's
`install` stays empty: it is opened at its URL.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.schema import (
    PASSED_LEVELS,
    FeatureCheck,
    InstallStep,
    Judge,
    RunEvidence,
    SmokeTest,
    SoftwareRecord,
    Verification,
    VerificationRun,
    WebCheck,
    WebOperation,
    best_level,
    is_passed,
)
from pickfit.score import refresh_scores
from pickfit.verify import web_guard as guard
from pickfit.verify.web_box import BROWSER_USE, image_name
from pickfit.verify.web_verify import JUDGE_MODEL, WebTarget, site_of

DATA_DIR = REPO_ROOT / "data" / "software"
RUNNER = "modal-vm-chromium"
SCREENS = {"main_ui": "main_ui", "landing_page": "main_ui", "sign_in_wall": "sign_in_wall", "paywall": "sign_in_wall",
           "error_page": "error_page", "parked_domain": "parked_or_gone", "blank_or_loading": "blank_or_loading",
           "bot_check": "other", "other": "other"}
CHECKS = {"text_on_page": "page_text", "downloaded_file": "download", "page_state": "element"}
_HOST = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")


def target_from_record(record: SoftwareRecord) -> WebTarget:
    """What the verifier needs from a web_app record: its URL, what it is for and its listed features."""
    if record.kind != "web_app" or record.web is None:
        raise ValueError(f"{record.slug} is not a web app")
    uses = "; ".join(record.use_cases[:3])
    return WebTarget(slug=record.slug, name=record.name, url=str(record.web.url),
                     use_case=f"{record.summary}" + (f" Typical uses: {uses}." if uses else ""),
                     features=list(record.features))


def record_targets(slugs: list[str], data_dir: Path | None = None) -> list[WebTarget]:
    """Targets for the named web_app records, or for every web_app record without a browser run when none named."""
    data_dir = data_dir or DATA_DIR
    paths = [data_dir / f"{s}.json" for s in slugs] if slugs else sorted(data_dir.glob("*.json"))
    targets = []
    for path in paths:
        record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.kind != "web_app" or record.web is None or record.status != "listed":
            continue  # a hidden or removed record is never visited
        if not slugs and any(r.web is not None for r in record.verification.runs):
            continue
        targets.append(target_from_record(record))
    return targets


def _rel(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _https(url: str | None) -> str | None:
    return url if url and url.startswith("https://") else None


def match_feature(label: str | None, features: list[str]) -> str | None:
    """The record's own feature label the judge named, by words in common (the judge answers in the list's words)."""
    if not label:
        return None
    words = set(re.findall(r"[a-z0-9]+", label.lower()))
    best, score = None, 0.0
    for feature in features:
        theirs = set(re.findall(r"[a-z0-9]+", feature.lower()))
        if feature.lower() == label.lower():
            return feature
        overlap = len(words & theirs) / max(1, len(words | theirs))
        if overlap > score:
            best, score = feature, overlap
    return best if score >= 0.5 else None


def _browser(result: dict[str, Any]) -> str:
    version = re.search(r"HeadlessChrome/(\d+)", result.get("user_agent") or "")
    return f"Chromium {version.group(1) if version else '?'} headless via {BROWSER_USE.replace('==', ' ')}"


def _data_sent(result: dict[str, Any], operated: bool) -> tuple[str, str | None]:
    network = result.get("network") or {}
    left = network.get("data_left_device")
    leaks = network.get("leaks") or []
    if left is True:
        hosts = sorted({h["host"] for h in leaks if h.get("sent")})
        return "observed", f"What pickfit typed or chose reached {', '.join(hosts[:4])} in a request."[:300]
    traced = network.get("traced") or []
    if left is False and operated and traced:
        return "none", ("No request carried what pickfit typed or chose (checked in addresses, bodies and WebSocket "
                        "messages, plain and encoded).")
    if operated and not traced:
        return "unknown", "pickfit typed only short values, too short to trace in requests."
    return "unknown", None


def web_run(result: dict[str, Any], features: list[str], run_dir: Path) -> VerificationRun | None:
    """The VerificationRun for a passed visit; None for anything else (only passed runs are written)."""
    level = result.get("level")
    if level not in ("install", "function"):
        return None
    url = result["url"]
    install = result.get("install") or {}
    page = result.get("install_judge") or {}
    function = result.get("function") or {}
    outcome = function.get("outcome") or {}
    check = function.get("check") or {}
    judge = result.get("function_judge") or {}
    operated = bool(function)
    smoke = [SmokeTest(command=f"open {url}", expected_signal="the app's main screen", exit_code=None, passed=True,
                       observed_excerpt=(page.get("observed") or "")[:300] or None)]
    operations: list[WebOperation] = []
    feature = match_feature(judge.get("feature") or outcome.get("feature"), features)
    operator = Counter((result.get("operator") or {}).get("models") or {}).most_common(1)
    operator_model = operator[0][0][:80] if operator else None
    if operated and outcome:
        goal = f"Use {outcome.get('feature') or 'one core feature'} and get a visible result"[:600]
        passed = bool(check.get("passed")) and bool(judge.get("feature_shown"))
        expected = [e for e in [check.get("text") or (check.get("file") or {}).get("name")
                                or (outcome.get("result_text") or "")[:200]] if e]
        observed = _operation_line(check, judge)
        smoke.append(SmokeTest(command=f"browser: {goal}"[:400], expected_signal=_signal(outcome), exit_code=None,
                               passed=passed, observed_excerpt=observed[:300]))
        operations.append(WebOperation(feature=feature, goal=goal, check=CHECKS.get(outcome.get("result_kind"), "element"),
                                       expected=[e[:200] for e in expected][:4], passed=passed, observed=observed[:500],
                                       smoke_test=len(smoke) - 1, actions=int(function.get("steps") or 0),
                                       operator_model=operator_model))
    offline = "not_tested"
    online_passed = bool(operations) and operations[0].passed  # offline is tested only on a feature that worked online
    if result.get("pwa") and result.get("works_offline") is not None and online_passed:
        offline_check = result.get("offline_check") or {}
        works = result.get("works_offline") == "works"
        offline = "verified" if works else ("not_offline" if offline_check else "not_tested")
        if offline_check:
            line = _operation_line(offline_check, result.get("offline_function_judge") or {}, offline=True)
            goal = f"With the network off, use {outcome.get('feature') or 'the same feature'} again"[:600]
            smoke.append(SmokeTest(command=f"browser offline: {goal}"[:400], expected_signal=_signal(outcome),
                                   exit_code=None, passed=works, observed_excerpt=line[:300], offline=works or None))
            operations.append(WebOperation(feature=feature, goal=goal,
                                           check=CHECKS.get(offline_check.get("kind"), "element"),
                                           expected=[offline_check["text"][:200]] if offline_check.get("text") else [],
                                           passed=works, observed=line[:500], smoke_test=len(smoke) - 1,
                                           actions=int(offline_check.get("steps") or 0), operator_model=operator_model))
    if level == "function" and not any(op.passed for op in operations):
        level = "install"
    data_sent, note = _data_sent(result, operated)
    if data_sent == "none" and not operations:
        data_sent, note = "unknown", None
    network = result.get("network") or {}
    hosts = [h for h in network.get("third_party_sites") or [] if _HOST.match(h)][:50]
    web = WebCheck(url=url, final_url=_https(install.get("url")) if install.get("url") != url else None,
                   screen=SCREENS.get(page.get("screen"), "other"), browser=_browser(result),
                   account_needed=result.get("account_required"), ads_seen=network.get("ads"),
                   third_party_domains=max(len(hosts), network.get("third_party_count") or 0)
                   if network else None, third_party_hosts=hosts, data_sent=data_sent, data_sent_note=note,
                   pwa=result.get("pwa"), offline=offline, operations=operations)
    checked = {i for i, op in enumerate(operations) if op.passed and op.feature}
    feature_checks = []
    for label in features:
        cites = [operations[i].smoke_test for i in checked if operations[i].feature == label]
        if cites:
            feature_checks.append(FeatureCheck(feature=label, status="checked", smoke_tests=sorted(set(cites))))
        else:
            gap = "needs_account" if result.get("account_required") else "not_attempted"
            feature_checks.append(FeatureCheck(feature=label, status="not_checked", reason=gap))
    shots = [p for name in ("install.png", "after.png", "offline.png", "offline_agent_after.png", "offline_replay.png")
             if (run_dir / name).exists() and (p := _rel(run_dir / name))]
    costs = result.get("costs") or {}
    return VerificationRun(
        id=result["run_id"], level=level, os="linux", arch="x86_64", method="sandbox", runner=RUNNER,
        image=image_name(), checked_at=datetime.fromisoformat(result["checked_at"]), install_method=None,
        replayed=False, steps=[InstallStep(command=f"open {url}", purpose="Open the app in a browser")],
        smoke_tests=smoke, judge=Judge(verdict="working", observed=(page.get("observed") or "main screen")[:300],
                                       model="muse-spark-1.3" if JUDGE_MODEL == "prod" else JUDGE_MODEL),
        evidence=RunEvidence(trace_path=_rel(run_dir / "messages.jsonl"), log_path=_rel(run_dir / "harness.log"),
                             screenshot_paths=shots),
        actor_model=operator_model, cost_usd=round(sum(float(v or 0) for v in costs.values()), 4),
        web=web, features=feature_checks)


def _signal(outcome: dict[str, Any]) -> str:
    kind = outcome.get("result_kind")
    if kind == "downloaded_file":
        return "a file the site produced was downloaded"
    if kind == "page_state":
        return "the page visibly changed the way the feature should"
    return "the result text appears on the page"


def _operation_line(check: dict[str, Any], judge: dict[str, Any], offline: bool = False) -> str:
    where = "offline: " if offline else ""
    if not check.get("passed"):
        return f"{where}pickfit's check failed: {check.get('why', '?')}"
    if check.get("file"):
        found = f"{check['file']['name']} ({check['file']['size']} bytes) arrived"
    elif check.get("text"):
        found = f"'{check['text'][:120]}' appeared on the page"
    else:
        found = f"pickfit's screenshots changed in {check.get('visual', 0) * 100:.1f}% of the page"
    seen = judge.get("observed") or ""
    verdict = "the judge saw the feature work" if judge.get("feature_shown") else "the judge did not see the feature work"
    return f"{where}{found}; {verdict}: {seen}"


# ---------------------------------------------------------------- write-back


def web_write_back(run: VerificationRun, slug: str, data_dir: Path = DATA_DIR) -> tuple[bool, str]:
    """Record a passed web run in data/software/<slug>.json; (written, why). install stays empty."""
    if not is_passed(run.level) or run.web is None:
        return False, f"not written: only a passed web run is ({run.level})"
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return False, f"not written: {path.name} does not exist yet"
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if record.kind != "web_app" or record.web is None:
        return False, f"not written: {slug} is kind {record.kind}, not web_app"
    if record.status != "listed":
        return False, f"not written: {slug} is {record.status} ({record.status_reason or 'no reason given'})"
    if guard.registrable(site_of(str(record.web.url))) != guard.registrable(site_of(str(run.web.url))):
        return False, f"not written: the run opened {run.web.url}, the record's URL is {record.web.url}"
    same = next((r for r in record.verification.runs if (r.os, r.arch, r.method) == (run.os, run.arch, run.method)
                 and is_passed(r.level)), None)
    if same and same.id != run.id and PASSED_LEVELS.index(run.level) > PASSED_LEVELS.index(same.level):  # same id: re-judged
        return False, f"not written: {run.level} would replace the stronger {same.level} run {same.id}"
    runs = [r for r in record.verification.runs if (r.os, r.arch, r.method) != (run.os, run.arch, run.method)]
    runs.append(run)
    level = best_level(runs)
    verification = Verification(level=level, unverified_reason=None if is_passed(level) else
                                record.verification.unverified_reason, checked_at=max(r.checked_at for r in runs),
                                runs=runs)
    data: dict[str, Any] = record.model_dump(mode="json")
    data["verification"] = verification.model_dump(mode="json")
    now = taipei_now()
    data["updated_at"] = now.isoformat()
    scores_note = refresh_scores(data, now)
    updated = SoftwareRecord.model_validate(data)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return True, f"written; {scores_note}" if scores_note else "written"


def write_back_saved(slug: str, run_dir: Path, data_dir: Path = DATA_DIR) -> tuple[bool, str]:
    """Write back a saved visit (web_result.json in run_dir) to its record, if it passed."""
    result = json.loads((run_dir / "web_result.json").read_text(encoding="utf-8"))
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return False, f"not written: {path.name} does not exist yet"
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    run = web_run(result, list(record.features), run_dir)
    if run is None:
        return False, f"not written: level {result.get('level')} ({result.get('reason')})"
    return web_write_back(run, slug, data_dir)
