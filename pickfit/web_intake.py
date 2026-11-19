"""One submitted website (submit_software with a hosted web app's URL) into a verified web_app record.

`pickfit watch` hands a D1 submission whose url is not a GitHub repository to read_site, then to
verify_site_record. The steps are the batch funnel's (pickfit.discover.webapps, pickfit.webrecords,
pickfit.verify.web_verify) for one site:

  the address: https, public (no local name, no private address), rule 1 (not a code host, platform or
  download) -> not already a record in data_dir (same record id or same web.url) -> rules 5-7 (robots.txt,
  the home page loads, the terms do not forbid automated access: webapps.check_site) -> rule 8 (the screen:
  a web app used in the browser, its core use needs no account and can be tried free) -> extraction (Claude
  Opus) -> <record_dir>/<slug>.json (webrecords.build_web_record) -> one browser visit (verify_site, in a
  microVM through web_guard) -> a passed visit written back into that record.

The batch's rules 2-4 (licence, the popularity band, a live post) choose among found sites; a submission was
asked for, so they do not apply, as the GitHub path takes any star count.

Refused: for good. str(err) goes back to the submitter, so it is written here, never by a model, in a short
plain sentence (at most 300 characters). AlreadyListed (a Refused) also carries the existing record's slug and
status. TryLater: a temporary problem (the site did not answer, a model call failed); the same submission may
be tried again.

The site is a row of `web_sites` in runs/pipeline.db (source "submission", item_id the submission id) with
what each check found and the outcome it stopped at. Its page text stays there only until the record is
written. Extraction rows go to the `extractions` table under the site's web: id, as the batch's do, so a later
try that reads the same page reuses them; a passed screen is reused the same way (checks.screen_sha).
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

from pydantic import ValidationError

from pickfit.discover.store import PipelineDB
from pickfit.discover.webapps import RENDER_BELOW, WebSites, check_site, host_of, screen_sources, site_key, site_outcome
from pickfit.extract import FEATURES_STATUS, extraction_is_current, same_tier, sources_sha
from pickfit.ledger import taipei_now
from pickfit.meta import PROD_MODEL
from pickfit.profiles import render, slugify
from pickfit.schema import SoftwareRecord
from pickfit.webrecords import build_web_record, site_id, web_candidate

SOURCE = "submission"  # web_sites.source of a submitted site
MODEL = PROD_MODEL  # extraction, as pickfit watch reads a repository
EXTRACT_EFFORT = "minimal"
DONE_EXTRACTIONS = ("ok", "quotes_dropped")
REASON_MAX = 300  # D1 submissions.reason CHECK
# Room one site needs before it starts, on Claude's prices: screen $0.30 + review $0.30 (SCREEN_SCOPE_CAP_USD each)
# + extraction $1.50 (extract.SCOPE_CAP_USD) + the visit $4.00 (web_verify.WORST_SITE_USD: operator $3.00, judges
# $0.50, the VM $0.50), rounded up. A usual site costs far less.
WORST_CASE_USD = 6.10

# The Worker's normalizeWebUrl (worker/src/submit.ts), checked again here: a row did not have to come from it.
_NOT_PUBLIC = re.compile(r"(^|\.)(localhost|local|internal|intranet|lan|home|corp|invalid|test|example|onion)$")
_IP_HOST = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

NOT_A_SITE = ("pickfit accepts a GitHub repository URL, like https://github.com/owner/repo, or the https URL of a "
              "public web app, like https://example.com/tool.")
RULE_1 = {
    "no_link": "pickfit could not read this as a website address.",
    "code_host": "A page on a code host, not a web app's own site; pickfit takes GitHub repositories as "
                 "https://github.com/owner/repo.",
    "platform": "A page on a store, social, content or documents platform, not a web app's own site.",
    "download": "A file download, not a web app people use in the browser.",
}
NOT_PUBLIC = "pickfit opens public websites only; this address is not on the public internet."
NO_SUCH_HOST = "The site's domain name does not resolve to an address."
ROBOTS = "robots.txt does not let pickfit open this site."
AI_INPUT = "The site's robots.txt asks AI tools not to use its pages (Content-Signal ai-input=no)."
NOT_HTML = "The address does not serve a web page."
REDIRECT_PLATFORM = "The address leads to a store, code host, social or content platform, not the app's own site."
TERMS = "The site's terms forbid automated access."
NEEDS_ACCOUNT = "It needs an account for its main use."
NOT_FREE = "Its main use needs payment before it can be tried."
# The screen's page_kind (a closed list) in pickfit's words; the model's own reason is never shown.
KIND_WORDS = {
    "landing_for_installed_software": "a page for software to download or install",
    "content": "a site to read or watch",
    "docs": "documentation",
    "platform": "a platform or marketplace",
    "company_or_portfolio": "a company or personal page",
    "developer_service": "a service used from code",
    "parked_or_error": "a placeholder or error page",
}
RECORD_SKIPS = {
    "not_web_app": "pickfit's reading of the site found something other than a web app people use in the browser.",
    "no_summary": "pickfit could not tell from the site what the app does.",
    "no_name": "pickfit could not find the app's name on the site.",
    "no_https": "pickfit lists web apps served over https.",
    "not_a_tool": "pickfit lists apps people use; this reads as something else.",
}
NO_RECORD = "pickfit could not build a valid record from what the site says."
VISITED = "pickfit visits each site once, and it visited this site before"
VERIFIER_ROBOTS = "robots.txt does not let pickfit's test browser open this site."


class Refused(Exception):
    """The site is refused for good; str(err) goes back to the submitter (written here, never by a model)."""


class AlreadyListed(Refused):
    """The site already has a record in data_dir: `slug`, its `status` (listed, hidden...) and verification `level`."""

    def __init__(self, message: str, *, slug: str, status: str | None, level: str | None) -> None:
        super().__init__(message)
        self.slug, self.status, self.level = slug, status, level


class TryLater(Exception):
    """A temporary problem: the same submission may be tried again later."""


def resolve_host(host: str) -> list[str]:
    """The addresses a host name resolves to (socket.gaierror when it does not)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})


@dataclass
class SiteSteps:
    """The networked and paid parts; tests replace them with fakes.

    fetch: .get(kind, url) -> {status, url, type, text, error} (webapps.Fetcher)
    screen(site row, page text, README or None, run_id) -> webapps.screen_site's decision
    extract(candidate, run_id) -> extraction rows, one per attempt (extract.extract_with_retries)
    verify(WebTarget, log) -> web_verify.verify_site's result (one visit, in a microVM)
    visited(registrable site) -> the verifier's earlier visit of it, or None (web_verify.past_visit)
    resolve(host) -> its addresses (resolve_host), to keep private networks out
    render(url) -> {text, links, error}: a page drawn by script, loaded once in a browser (webapps.render_page)
    clock: the time a record is stamped with
    with_visits(path) -> the same steps, reading and claiming visits in `path` instead of runs/web/visits.jsonl
      (pickfit's end-to-end test: its visits never count against a real submission of the site)
    """

    fetch: Any
    screen: Callable[[dict[str, Any], str, str | None, str], dict[str, Any]]
    extract: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    verify: Callable[[Any, Callable[[str], None]], dict[str, Any]]
    visited: Callable[[str], dict[str, Any] | None]
    resolve: Callable[[str], list[str]]
    render: Callable[[str], dict[str, Any]] | None = None
    clock: Callable[[], datetime] = taipei_now
    with_visits: Callable[[Path], SiteSteps] | None = None


def live_site_steps(*, runner: str = "modal") -> SiteSteps:
    """The real steps: pickfit's fetches, the screen (Claude Haiku, reviewed by Claude Opus when unsure), extraction
    by Claude Opus, and a visit in a Modal (or EC2) VM. Rendering a page drawn by script needs playwright
    (`uv run --with playwright`); without it such a page is a TryLater, not a refusal."""
    from pickfit.discover.webapps import Fetcher, render_page, screen_site
    from pickfit.extract import extract_with_retries
    from pickfit.verify.web_verify import past_visit, verify_site

    if runner not in ("modal", "ec2"):
        raise ValueError(f"a web app is visited in a Modal or EC2 VM, not {runner!r}")
    box_factory = None
    if runner == "ec2":
        from pickfit.verify.web_box import on_ec2 as box_factory

    def steps(visits: Path | None = None) -> SiteSteps:
        return SiteSteps(
            fetch=Fetcher(), render=render_page,
            screen=lambda row, page, readme, run_id: screen_site(row, page, readme, run_id=run_id),
            extract=lambda c, run_id: extract_with_retries(c, model=MODEL, run_id=run_id,
                                                           reasoning_effort=EXTRACT_EFFORT),
            verify=lambda target, log: verify_site(target, log=log, box_factory=box_factory, visits=visits),
            visited=lambda site: past_visit(site, visits), resolve=resolve_host, with_visits=steps)

    return steps()


@dataclass
class SiteRead:
    slug: str
    record_path: Path
    record_id: str  # the record's repo_id: web:<host>[/path]
    url: str  # the record's web.url
    cost_usd: float  # model spend of this call (screen, extraction)
    notes: list[str] = field(default_factory=list)


@dataclass
class SiteVisit:
    level: str | None  # the record's verification level after the write-back (install, function); None: not passed
    cost_usd: float  # model calls of the visit (terms judge, operator, judges)
    box_usd: float  # the VM
    why: str | None  # why it did not pass, for the submitter: pickfit's words, lower case, no full stop; None: passed
    detail: str | None = None  # the verifier's own reason (it may quote a judge or the page): logs only
    run_id: str | None = None


def normalize_web_url(url: str) -> str | None:
    """https://<host>/<path> of a public web app as the Worker writes it (lower-case host, no query, fragment,
    credentials or port, no trailing slash past the root), or None."""
    text = (url or "").strip()
    if not re.match(r"https://", text, re.I):
        return None
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or port is not None:
        return None
    if "." not in host or ":" in host or len(host) > 253 or _IP_HOST.match(host) or _NOT_PUBLIC.search(host):
        return None
    path = parts.path.rstrip("/")
    return f"https://{host}{path or '/'}"


def site_record_id(url: str) -> str | None:
    """The record id (web:<host>[/path]) a submitted address gets, before anything is fetched: what two
    submissions in flight are compared by. None when it is not an address read_site takes."""
    normal = normalize_web_url(url)
    key = site_key(normal) if normal else None
    return site_id({"site_key": key}) if key else None


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= REASON_MAX else text[:REASON_MAX - 1] + "…"


def _public(host: str, resolve: Callable[[str], list[str]]) -> str | None:
    """None when every address of `host` is on the public internet, else the refusal. TryLater when DNS fails
    for a reason other than a name that does not exist."""
    try:
        addresses = resolve(host)
    except socket.gaierror as err:
        if err.errno in {socket.EAI_NONAME, getattr(socket, "EAI_NODATA", socket.EAI_NONAME)}:
            return NO_SUCH_HOST
        raise TryLater(f"DNS lookup of {host} failed: {err}") from None
    except OSError as err:
        raise TryLater(f"DNS lookup of {host} failed: {err}") from None
    if not addresses:
        return NO_SUCH_HOST
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            return NOT_PUBLIC
        if not ip.is_global:
            return NOT_PUBLIC
    return None


def listed_record(data_dir: Path, ids: set[str], keys: set[str]) -> dict[str, Any] | None:
    """The record in data_dir with one of these record ids, or whose web.url has one of these site keys."""
    for path in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        url = (data.get("web") or {}).get("url")
        if data.get("repo_id") in ids or (url and site_key(url) in keys):
            return {**data, "slug": data.get("slug") or path.stem}
    return None


def _refuse_listed(data_dir: Path, ids: set[str], keys: set[str]) -> None:
    data = listed_record(data_dir, ids, keys)
    if data is None:
        return
    status = data.get("status")
    message = f"Already in pickfit's directory as {data['slug']}." if status == "listed" else \
        "Reviewed before and not listed."
    raise AlreadyListed(message, slug=data["slug"], status=status,
                        level=(data.get("verification") or {}).get("level"))


def _site_stop(outcome: str, checks: dict[str, Any]) -> Exception:
    """What a failed check_site outcome means for a submission."""
    home = checks.get("home") or {}
    status = home.get("status")
    if outcome == "robots_unreachable" or (outcome == "robots_disallow" and (checks.get("robots_final") or {})
                                           .get("unreachable")):
        robots = checks.get("robots_final") or checks.get("robots") or {}
        return TryLater(f"robots.txt did not answer ({robots.get('status') or robots.get('error')})")
    if outcome == "robots_disallow":
        signal = ((checks.get("robots_final") or checks.get("robots") or {}).get("content_signal") or {})
        return Refused(AI_INPUT if signal.get("ai-input") == "no" else ROBOTS)
    if outcome == "site_down":
        if status is None or status >= 500 or status in (408, 425, 429):
            return TryLater(f"the home page did not load ({status or home.get('error')})")
        return Refused(f"The home page did not load (HTTP {int(status)}).")
    if outcome == "not_html":
        return Refused(NOT_HTML)
    if outcome == "redirect_platform":
        return Refused(REDIRECT_PLATFORM)
    if outcome == "terms_disallow":
        return Refused(TERMS)
    return TryLater(f"site check: {outcome}")


def read_site(url: str, *, submission_id: str, run_id: str, record_dir: Path, data_dir: Path, db_path: Path,
              taken_slugs: set[str], steps: SiteSteps, log: Callable[[str], None],
              claim_slug: Callable[[str], bool] | None = None,
              spend: Callable[[str, float], None] | None = None) -> SiteRead:
    """Rules, the screen and extraction for one submitted site, and its record in record_dir/<slug>.json
    (record_dir is made fresh). Raises Refused (AlreadyListed for a site data_dir already has), TryLater, or
    BudgetExceeded from a model call.

    taken_slugs: slugs other jobs hold (read_site adds data_dir's own). claim_slug(slug) -> bool, when given, is
    asked for the chosen slug just before the record is written; False (another job took it) tries the next one.
    spend(kind, usd) is told each model cost as it is paid ("model"), so a refusal after a paid step loses none."""
    notes: list[str] = []
    spent = [0.0]

    def paid(usd: float | None) -> None:
        spent[0] += usd or 0.0
        if spend is not None and usd:
            spend("model", usd)

    normal = normalize_web_url(url)
    if normal is None:
        raise Refused(NOT_A_SITE)
    key = site_key(normal)
    host = host_of(normal)
    if key is None or host is None:
        raise Refused(RULE_1["no_link"])
    record_id = site_id({"site_key": key})
    sites = WebSites(db_path)
    earlier = next((r for r in sites.rows(SOURCE) if r["item_id"] == submission_id), None)
    rule_1 = site_outcome(normal)
    sites.save({"source": SOURCE, "item_id": submission_id, "item_url": normal, "title": host, "link": normal,
                "site_url": normal, "site_key": key, "repo_id": None, "repo": None, "popularity": None,
                "signals": {}, "outcome": rule_1 or "site"}, run_id)
    checks: dict[str, Any] = {}

    def stop(outcome: str, err: Exception) -> NoReturn:
        sites.save_check(SOURCE, submission_id, outcome=outcome, checks=checks)
        log(f"{outcome}: {err}")
        raise err

    if rule_1:
        stop(rule_1, Refused(RULE_1.get(rule_1, RULE_1["no_link"])))
    try:
        _refuse_listed(data_dir, {record_id}, {key})
    except AlreadyListed as err:
        stop("has_record", err)
    why = _public(host, steps.resolve)
    if why:
        stop("not_public", Refused(why))

    outcome, checks, page = check_site({"site_url": normal}, steps.fetch, steps.render)
    rendered = (checks.get("page") or {}).get("rendered")
    if rendered:
        notes.append(f"page drawn by script: rendered ({rendered.get('chars')} characters"
                     + (f", {rendered['error']}" if rendered.get("error") else "") + ")")
    log(f"site check: {outcome}")
    if outcome != "checked":
        stop(outcome, _site_stop(outcome, checks))
    if (checks["page"].get("text_chars") or 0) < RENDER_BELOW and (rendered is None or rendered.get("error")):
        # A page drawn by script that could not be drawn: the screen would judge an empty page.
        stop("not_rendered", TryLater("the page is drawn by script and could not be rendered ("
                                      + ((rendered or {}).get("error") or "no renderer") + ")"))
    if (checks.get("terms") or {}).get("unreadable"):
        notes.append("terms page not readable as text")
    final = (checks.get("home") or {}).get("final_url") or normal
    final_key, final_host = site_key(final), host_of(final)
    if final_host and final_host != host:
        why = _public(final_host, steps.resolve)
        if why:
            stop("not_public", Refused(why))
    if final_key and final_key != key:
        try:
            _refuse_listed(data_dir, {site_id({"site_key": final_key})}, {final_key})
        except AlreadyListed as err:
            stop("has_record", err)

    row = {"source": SOURCE, "item_id": submission_id, "item_url": normal, "title": host, "site_url": normal,
           "site_key": key, "repo": None, "checks": checks}
    screen_sha = sources_sha(screen_sources(row, page or "", None))
    before = (earlier or {}).get("checks") or {}
    if before.get("screen_sha") == screen_sha and (before.get("screen") or {}).get("keep") is True:
        decision = before["screen"]
        notes.append("screen reused")
    else:
        decision = steps.screen(row, page or "", None, run_id)
        paid(sum(call.get("cost_usd") or 0.0 for call in decision.get("calls") or []))
    checks.update(screen=decision, screen_sha=screen_sha)
    answer = decision.get("result") or {}
    log(f"screen ({decision.get('decided_by')}): keep {decision.get('keep')} · {answer.get('page_kind')} · "
        f"account {answer.get('account_for_core_use')} · free {answer.get('free_to_try')}")
    if decision.get("keep") is None:
        stop("screen_failed", TryLater("the screen gave no answer"))
    if not decision["keep"]:
        kind = answer.get("page_kind")
        if kind != "web_app":
            stop(f"not_web_app:{kind}", Refused(f"pickfit's check read it as {KIND_WORDS.get(kind, 'something else')}, "
                                                "not a web app people use in the browser."))
        if answer.get("account_for_core_use") == "needed":
            stop("needs_account", Refused(NEEDS_ACCOUNT))
        if answer.get("free_to_try") == "no":
            stop("not_free", Refused(NOT_FREE))
        stop("screen_unclear", TryLater("the screen's answer did not hold together"))
    if decision.get("decided_by") == "review":
        notes.append("screen decided by the review")

    sites.save_check(SOURCE, submission_id, outcome="passed", checks=checks, page=page)
    site = next(r for r in sites.rows(SOURCE) if r["item_id"] == submission_id)
    try:
        try:
            extraction = _extract(web_candidate(site), PipelineDB(db_path), steps, run_id, notes, paid)
        except TryLater as err:
            stop("extraction_failed", err)
        try:
            record = _build(site, extraction, record_id, data_dir, taken_slugs, claim_slug, steps.clock())
        except (Refused, TryLater) as err:
            stop("record_skipped" if isinstance(err, Refused) else "slug_taken", err)
    finally:
        sites.purge_pages([(SOURCE, submission_id)])  # what the page said lives on as the record's quotes
    if record_dir.exists():
        shutil.rmtree(record_dir)
    record_dir.mkdir(parents=True)
    path = record_dir / f"{record.slug}.json"
    path.write_text(render(record), encoding="utf-8")
    log(f"record {record.slug} [{record.category}/{record.kind}] {record.web.url}")
    return SiteRead(slug=record.slug, record_path=path, record_id=record.repo_id, url=str(record.web.url),
                    cost_usd=round(spent[0], 6), notes=notes)


def _extract(candidate: dict[str, Any], db: PipelineDB, steps: SiteSteps, run_id: str, notes: list[str],
             paid: Callable[[float | None], None]) -> dict[str, Any]:
    """The newest finished extraction of the same raw text, or a new one (rows stored as the batch stores them)."""
    for model in same_tier(MODEL):
        last = db.last_extraction(candidate["repo_id"], model, exclude=(FEATURES_STATUS,))
        if last and last["status"] in DONE_EXTRACTIONS and extraction_is_current(last, candidate):
            notes.append("extraction reused")
            return last
    rows = steps.extract(candidate, run_id)
    for row in rows:
        db.save_extraction(**row)
        paid(row.get("cost_usd"))
    final = rows[-1] if rows else None
    if final is None or final["status"] not in DONE_EXTRACTIONS:
        raise TryLater(f"extraction {final['status'] if final else 'did not run'}")
    last = db.last_extraction(candidate["repo_id"], final["model"], DONE_EXTRACTIONS)
    assert last is not None
    return last


def _build(site: dict[str, Any], extraction: dict[str, Any], record_id: str, data_dir: Path, taken_slugs: set[str],
           claim_slug: Callable[[str], bool] | None, now: datetime) -> SoftwareRecord:
    """The record under the first free slug: the app's name, else its address."""
    taken = set(taken_slugs) | {p.stem for p in data_dir.glob("*.json")}
    name = ((extraction["result"] or {}).get("name") or {}).get("value") or ""
    choices = [s for s in dict.fromkeys((slugify(name), slugify(record_id.removeprefix("web:").replace("/", "-"))))
               if s and s not in taken]
    if not choices:
        raise TryLater("every slug for it is taken")
    try:
        record = build_web_record(site, extraction, slug=choices[0], now=now)
    except (ValueError, ValidationError) as err:
        reason = str(err).splitlines()[0].split(":")[0].strip()
        raise Refused(RECORD_SKIPS.get(reason, NO_RECORD)) from None
    for slug in choices:
        if claim_slug is None or claim_slug(slug):
            return record if slug == record.slug else build_web_record(site, extraction, slug=slug, now=now)
    raise TryLater(f"slug {choices[0]} is taken")


# ---------------------------------------------------------------- the visit


def _visit_why(result: dict[str, Any]) -> str:
    """Why a visit did not pass, in pickfit's words (the verifier's own reason may quote a judge or the page)."""
    screen = (result.get("install_judge") or {}).get("screen")
    if result.get("account_required") is True or screen in ("sign_in_wall", "paywall"):
        return "pickfit's browser met a sign-in or payment screen before it could use the app"
    if screen == "bot_check":
        return "the site showed pickfit's browser a bot check"
    if screen in ("error_page", "parked_domain", "blank_or_loading"):
        return "pickfit's browser did not reach a working page"
    if result.get("error") and not result.get("install"):
        return "pickfit's browser visit did not finish"
    return "pickfit's browser check did not pass"


def verify_site_record(record_dir: Path, slug: str, *, steps: SiteSteps, log: Callable[[str], None],
                       spend: Callable[[str, float], None] | None = None) -> SiteVisit:
    """Visit the site of record_dir/<slug>.json once and write a passed visit into that record (never into
    data/software). A site the verifier visited before is not visited again: the visit's why says so.

    Raises Refused when the verifier's own look before the browser (robots.txt for pickfit-verifier, the terms
    with a judge) or the terms the page draws forbid the visit; TryLater when robots.txt did not answer, or the
    visit never started (no visit was claimed, so trying again does not break the one-visit rule).
    spend(kind, usd) gets "model" and "box" costs."""
    from pickfit.verify.web_record import target_from_record, web_run, web_write_back
    from pickfit.verify.web_verify import runs_dir, site_of

    path = record_dir / f"{slug}.json"
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    target = target_from_record(record)
    site = site_of(target.url)
    earlier = steps.visited(site)
    if earlier:
        log(f"not visited: {site} was visited by run {earlier.get('run_id')} ({earlier.get('slug')}); "
            "pickfit visits a site once")
        return SiteVisit(level=None, cost_usd=0.0, box_usd=0.0, why=VISITED,
                         detail=f"visited by {earlier.get('run_id')} at {earlier.get('at')}")
    result = steps.verify(target, log)
    costs = result.get("costs") or {}
    model = round(sum(float(costs.get(k) or 0.0) for k in ("terms_usd", "operator_usd", "judge_usd")), 6)
    box = round(float(costs.get("sandbox_usd") or 0.0), 6)
    if spend is not None:
        spend("model", model)
        spend("box", box)
    level, run_id = result.get("level"), result.get("run_id")
    detail = result.get("reason") or result.get("error")
    visit = SiteVisit(level=None, cost_usd=model, box_usd=box, why=None, detail=detail, run_id=run_id)
    if level in ("install", "function"):
        run = web_run(result, list(record.features), runs_dir() / slug / run_id)
        written, note = web_write_back(run, slug, data_dir=record_dir) if run else (False, "no run")
        log(f"write-back: {note}")
        if not written:
            visit.why, visit.detail = "pickfit could not record its browser check", note
            return visit
        visit.level = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8")).verification.level
        return visit
    preflight = result.get("preflight") or {}
    if level == "skipped" and preflight.get("allowed") is False:
        if (preflight.get("reason") or "").startswith("robots.txt"):
            status = preflight.get("robots_status")
            if status is None or status >= 500 or status == 429:
                raise TryLater(f"robots.txt did not answer the verifier ({status})")
            raise Refused(VERIFIER_ROBOTS)
        raise Refused(TERMS)
    if level == "unverified" and result.get("reason") == "the terms forbid automated access":
        raise Refused(TERMS)  # the terms a script drew on the page, read once it rendered
    if "AlreadyVisited" in (result.get("error") or "") or (level == "skipped" and "already visited" in (detail or "")):
        visit.why = VISITED
        return visit
    if steps.visited(site) is None:  # the VM never started, so no visit was claimed
        raise TryLater(f"the browser visit did not start ({detail})")
    visit.why = _visit_why(result)
    return visit
