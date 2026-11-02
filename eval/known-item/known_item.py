"""Known-item test (eval/known-item/README.md): does find_software return a catalog tool that fits?

Steps, run from the repo root in this order:
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py sample   # draw targets, fetch READMEs, write questions
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py rewrite  # questions over find_software's 500 chars
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py run      # call the live Worker's find_software
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py cost     # settle Worker spend from its D1 events
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py l1       # blind L1 on top picks, then on targets
  uv run --with anthropic==2.3.0 python eval/known-item/known_item.py report   # results table

README texts are cached outside the repo (KI_CACHE, default ~/.pickfit/known-item); the repo keeps
the commit SHA, path and sha256 of each one (README section 9).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from pickfit.env import read_env  # noqa: E402
from pickfit.ledger import DEFAULT_PATH, Caps, Ledger  # noqa: E402

SNAPSHOT_COMMIT = "4e0dd4b"
DATA_SHA256 = "acb3891c32173105a6521ed0a93b047500363b547c07db8a4e7b3e0d3b6cb3e2"
SEED = "20261102"
STRATA = [("dev_cli", "dev_cli", 4), ("local_ai", "local_ai", 4), ("mcp_server", "mcp_server", 4), ("gui", "other", 3)]
PASSED_LEVELS = ("inference", "service", "function", "install")
WORKER = "https://pickfit-mcp.ncchen99.workers.dev"
MODEL = "claude-opus-5-5"
WRITER_EFFORT, L1_EFFORT = "medium", "high"
MAX_OUTPUT_TOKENS = 8000
README_MAX_CHARS = 40_000
README_MIN_CHARS = 400
WRITER_ATTEMPTS = 3
NEED_MAX_CHARS = 500  # find_software's limit on need (README change log, 11/2 17:18)
# USD per million tokens (input, output, cached input): the table eval/runner/grade.py uses.
PRICE = (4.00, 20.00, 0.20)
WORKER_RESERVE_USD = 0.10

TAIPEI = dt.timezone(dt.timedelta(hours=8))
CACHE = Path(os.environ.get("KI_CACHE", Path.home() / ".pickfit" / "known-item"))
SAMPLE = HERE / "sample.json"
INPUTS = HERE / "inputs.json"
QUESTIONS = HERE / "questions.jsonl"
RESPONSES = HERE / "responses"
L1_OUT = HERE / "l1.jsonl"
SPEND = HERE / "spend.json"
RESULTS = HERE / "results.md"


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def section(path: Path, start: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split(f"<!-- {start} -->", 1)[1].split(f"<!-- {end} -->", 1)[0].strip()


WRITER_PROMPT = section(HERE / "prompts" / "writer.md", "WRITER START", "WRITER END")
RETRY_NOTE = section(HERE / "prompts" / "writer.md", "RETRY START", "RETRY END")
LENGTH_NOTE = section(HERE / "prompts" / "writer.md", "LENGTH START", "LENGTH END")
L1_PROMPT = section(HERE / "prompts" / "l1.md", "RUBRIC START", "RUBRIC END")

WRITER_SCHEMA = {
    "type": "object",
    "properties": {
        "request": {"type": "string"},
        "core_job": {"type": "string"},
        "hard_conditions": {"type": "array", "items": {
            "type": "object",
            "properties": {"condition": {"type": "string"}, "readme_quote": {"type": "string"}},
            "required": ["condition", "readme_quote"], "additionalProperties": False}},
    },
    "required": ["request", "core_job", "hard_conditions"],
    "additionalProperties": False,
}
L1_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {"type": "array", "items": {
            "type": "object",
            "properties": {"check": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "fail", "unknown"]},
                           "reason": {"type": "string"}},
            "required": ["check", "verdict", "reason"], "additionalProperties": False}},
        "overall": {"type": "string", "enum": ["pass", "fail", "unknown"]},
    },
    "required": ["checks", "overall"],
    "additionalProperties": False,
}


# --- ledger -----------------------------------------------------------------------------------


def ledger(name: str, total: float) -> Ledger:
    return Ledger(os.environ.get("PICKFIT_LEDGER") or DEFAULT_PATH, budget=name,
                  caps=Caps(total_usd=total, daily_usd=lambda day: total))


ANTHROPIC_LEDGER = ledger("known-item-anthropic", 8.0)
WORKER_LEDGER = ledger("known-item-worker", 3.0)


# --- snapshot ---------------------------------------------------------------------------------


def snapshot() -> dict[str, dict[str, Any]]:
    """The records at SNAPSHOT_COMMIT, checked against the live Worker's data_sha256."""
    tar = subprocess.run(["git", "archive", "--format=tar", SNAPSHOT_COMMIT, "data/software"],
                         cwd=ROOT, check=True, capture_output=True).stdout
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.endswith(".json"):
                files[member.name.rsplit("/", 1)[-1]] = archive.extractfile(member).read()
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode() + b"\0" + files[name] + b"\0")
    if digest.hexdigest() != DATA_SHA256:
        raise SystemExit(f"snapshot {SNAPSHOT_COMMIT} does not match the live data_sha256")
    return {name[:-5]: json.loads(raw) for name, raw in files.items()}


def eligible(record: dict[str, Any]) -> bool:
    repo = record.get("repo") or {}
    return (record["status"] == "listed"
            and (record.get("verification") or {}).get("level") in PASSED_LEVELS
            and "github.com/" in (repo.get("url") or "") and not repo.get("archived"))


def target_os(record: dict[str, Any]) -> str:
    """The OS of the run that set the record's level: that level, newest first."""
    level = record["verification"]["level"]
    runs = [r for r in record["verification"]["runs"] if r.get("level") == level]
    return max(runs, key=lambda r: r["checked_at"])["os"]


def owner_repo(url: str) -> tuple[str, str]:
    path = url.split("github.com/", 1)[1].strip("/").split("/")
    return path[0], path[1].removesuffix(".git")


# --- GitHub -----------------------------------------------------------------------------------


def gh(path: str) -> dict[str, Any]:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise LookupError(f"gh api {path}: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def fetch_readme(url: str) -> dict[str, Any]:
    """README at the default branch's current commit; text cached outside the repo."""
    owner, repo = owner_repo(url)
    meta = gh(f"repos/{owner}/{repo}")
    full = meta["full_name"]
    sha = gh(f"repos/{full}/commits/{meta['default_branch']}")["sha"]
    readme = gh(f"repos/{full}/readme?ref={sha}")
    text = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{full.replace('/', '__')}@{sha}.txt").write_text(text, encoding="utf-8")
    return {"repo": full, "commit": sha, "path": readme["path"], "fetched_at": now(),
            "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "license": (meta.get("license") or {}).get("spdx_id"), "description": meta.get("description"),
            "text": text}


def plain_length(text: str) -> int:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return len(re.sub(r"\s+", " ", text).strip())


# --- Claude -----------------------------------------------------------------------------------


def main_dotenv() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    return Path(common).parent / ".env"


def claude(system: str, user: str, effort: str, schema: dict[str, Any], stage: str, scope: str) -> dict[str, Any]:
    import anthropic  # uv run --with anthropic==2.3.0

    estimate = ((len(system) + len(user)) / 3 * PRICE[0] + MAX_OUTPUT_TOKENS * PRICE[1]) / 1_000_000
    row = ANTHROPIC_LEDGER.reserve(estimate, run_id="known-item", stage=stage, scope=scope,
                                   provider="anthropic", model=MODEL)
    key = read_env(["ANTHROPIC_API_KEY"], path=main_dotenv())["ANTHROPIC_API_KEY"]
    try:
        response = anthropic.Anthropic(api_key=key).messages.create(
            model=MODEL, max_tokens=MAX_OUTPUT_TOKENS, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
    except Exception:
        ANTHROPIC_LEDGER.release(row)
        raise
    u = response.usage
    cached = u.cache_read_input_tokens or 0
    total_in = u.input_tokens + cached + (u.cache_creation_input_tokens or 0)
    usd = round(((total_in - cached) * PRICE[0] + cached * PRICE[2] + u.output_tokens * PRICE[1]) / 1_000_000, 6)
    ANTHROPIC_LEDGER.settle(row, usd, tokens={"input_tokens": total_in, "cached_tokens": cached,
                                              "output_tokens": u.output_tokens}, response_id=response.id)
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {"model": response.model, "effort": effort, "stop_reason": response.stop_reason, "text": text,
            "parsed": parsed, "cost_usd": usd, "usage": {"input_tokens": total_in, "cached_input_tokens": cached,
                                                           "output_tokens": u.output_tokens}}


# --- question checks --------------------------------------------------------------------------


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", text.lower())).strip()


def name_terms(record: dict[str, Any]) -> list[str]:
    owner, repo = owner_repo(record["repo"]["url"])
    terms = [record["name"], record["slug"], owner, repo, *(record.get("aliases") or [])]
    return sorted({norm(t) for t in terms if t and norm(t)})


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def grams(text: str, n: int = 5) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def check_question(request: str, record: dict[str, Any]) -> dict[str, Any]:
    body = norm(request)
    names = [t for t in name_terms(record)
             if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", body)]
    sources = [record.get("summary") or "", *(record.get("use_cases") or [])]
    shared = sorted({" ".join(g) for s in sources for g in grams(s) & grams(request)})
    too_long = len(request) > NEED_MAX_CHARS
    return {"name_hits": names, "shared_5grams": shared, "too_long": too_long,
            "passed": not names and not shared and not too_long}


def well_formed(parsed: Any) -> bool:
    return (isinstance(parsed, dict) and isinstance(parsed.get("request"), str) and parsed["request"].strip()
            and isinstance(parsed.get("hard_conditions"), list) and 2 <= len(parsed["hard_conditions"]) <= 4)


def readme_message(readme: dict[str, Any]) -> str:
    return f"{readme['path']} at commit {readme['commit']}:\n\n{readme['text'][:README_MAX_CHARS]}"


def write_question(record: dict[str, Any], readme: dict[str, Any], log: io.TextIOBase,
                   first: int = 1, too_long: bool = False) -> dict[str, Any] | None:
    for attempt in range(first, WRITER_ATTEMPTS + 1):
        note = LENGTH_NOTE if too_long else RETRY_NOTE
        user = readme_message(readme) + ("" if attempt == 1 else "\n\n" + note)
        reply = claude(WRITER_PROMPT, user, WRITER_EFFORT, WRITER_SCHEMA, "writer", record["slug"])
        parsed = reply["parsed"]
        check = (check_question(parsed["request"], record) if well_formed(parsed)
                 else {"name_hits": [], "shared_5grams": [], "passed": False, "malformed": True})
        row = {"slug": record["slug"], "attempt": attempt, "at": now(), "readme_commit": readme["commit"],
               "readme_sha256": readme["sha256"], "reply": reply, "check": check}
        log.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.flush()
        print(f"  writer {record['slug']} attempt {attempt}: {'ok' if check['passed'] else check} ${reply['cost_usd']}")
        if check["passed"]:
            return row
        too_long = bool(check.get("too_long"))
    return None


# --- steps ------------------------------------------------------------------------------------


def step_sample() -> None:
    records = snapshot()
    inputs: dict[str, Any] = {}
    sample: dict[str, Any] = {"seed": SEED, "snapshot_commit": SNAPSHOT_COMMIT, "data_sha256": DATA_SHA256,
                              "drawn_at": now(), "strata": {}, "targets": []}
    with QUESTIONS.open("a", encoding="utf-8") as log:
        for name, category, n in STRATA:
            pool = sorted(s for s, r in records.items() if r["category"] == category and eligible(r))
            order = pool[:]
            random.Random(f"{SEED}:{name}").shuffle(order)
            taken, skipped = [], []
            for slug in order:
                if len(taken) == n:
                    break
                record = records[slug]
                try:
                    readme = fetch_readme(record["repo"]["url"])
                except (LookupError, KeyError, ValueError) as err:
                    skipped.append({"slug": slug, "reason": f"readme: {err}"})
                    continue
                inputs[slug] = {k: v for k, v in readme.items() if k != "text"}
                if plain_length(readme["text"]) < README_MIN_CHARS:
                    skipped.append({"slug": slug, "reason": f"readme under {README_MIN_CHARS} chars"})
                    continue
                print(f"{name}: {slug}")
                if write_question(record, readme, log) is None:
                    skipped.append({"slug": slug, "reason": f"writer failed the checks {WRITER_ATTEMPTS} times"})
                    continue
                taken.append(slug)
                sample["targets"].append({"slug": slug, "stratum": name, "category": category,
                                          "level": record["verification"]["level"], "os": target_os(record)})
            sample["strata"][name] = {"eligible": len(pool), "order_head": order[:len(taken) + len(skipped)],
                                      "taken": taken, "skipped": skipped}
    SAMPLE.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INPUTS.write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def accepted_questions() -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["slug"]: r for r in rows
            if r["check"]["passed"] and len(r["reply"]["parsed"]["request"]) <= NEED_MAX_CHARS}


def step_rewrite() -> None:
    """Targets whose question find_software rejected as too long: rewrite with the length note."""
    records = snapshot()
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    accepted = accepted_questions()
    with QUESTIONS.open("a", encoding="utf-8") as log:
        for target in sample["targets"]:
            slug = target["slug"]
            if slug in accepted:
                continue
            source = inputs[slug]
            text = (CACHE / f"{source['repo'].replace('/', '__')}@{source['commit']}.txt").read_text(encoding="utf-8")
            if hashlib.sha256(text.encode()).hexdigest() != source["sha256"]:
                raise SystemExit(f"{slug}: cached README does not match inputs.json")
            done = max(r["attempt"] for r in rows if r["slug"] == slug)
            print(f"rewrite {slug} from attempt {done + 1}")
            if write_question(records[slug], {**source, "text": text}, log, first=done + 1, too_long=True) is None:
                print(f"  {slug}: no question passed; draw the next target in {target['stratum']} (README 2)")


def call_find(need: str, os_name: str) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "find_software", "arguments": {"need": need, "os": os_name}}}).encode()
    request = urllib.request.Request(f"{WORKER}/mcp", data=body, method="POST", headers={
        "content-type": "application/json", "accept": "application/json, text/event-stream",
        "x-pickfit-reporter": "eval", "user-agent": "pickfit-known-item/1"})
    started = time.time()
    row = WORKER_LEDGER.reserve(WORKER_RESERVE_USD, run_id="known-item", stage="find_software",
                                provider="pickfit-worker", model="worker")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status, raw = response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read().decode("utf-8", errors="replace")
    except Exception as err:  # timeout or network: nothing came back
        status, raw = None, repr(err)
    message = next((json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")), None)
    if message is None and raw.lstrip().startswith("{"):
        message = json.loads(raw)
    result = (message or {}).get("result") or {}
    content = result.get("structuredContent")
    if content is None and result.get("content"):
        try:
            content = json.loads(result["content"][0]["text"])
        except (ValueError, KeyError, TypeError):
            content = None
    return {"at": now(), "latency_s": round(time.time() - started, 1), "http_status": status,
            "ledger_row": row, "is_error": bool(result.get("isError")) or content is None,
            "find": content, "raw": message if message is not None else raw}


MAX_FIND_ATTEMPTS = 4
RETRY_WAIT_S = 90


def sound(attempt: dict[str, Any]) -> bool:
    """The model chose the picks: no error and not degraded to rules."""
    return not attempt["is_error"] and not (attempt["find"] or {}).get("degraded")


def step_run() -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    questions = accepted_questions()
    RESPONSES.mkdir(exist_ok=True)
    for i, target in enumerate(sample["targets"], 1):
        out = RESPONSES / f"{i:02d}-{target['slug']}.json"
        attempts = json.loads(out.read_text(encoding="utf-8"))["attempts"] if out.exists() else []
        if any(sound(a) for a in attempts) or len(attempts) >= MAX_FIND_ATTEMPTS:
            continue
        need = questions[target["slug"]]["reply"]["parsed"]["request"]
        while len(attempts) < MAX_FIND_ATTEMPTS:  # README change log 11/2 17:14: retry degraded answers, outcome-blind
            if attempts:
                print(f"  {target['slug']}: degraded or error, retrying in {RETRY_WAIT_S} s")
                time.sleep(RETRY_WAIT_S)
            attempts.append(call_find(need, target["os"]))
            used = next((j for j, a in enumerate(attempts) if sound(a)), len(attempts) - 1)
            out.write_text(json.dumps({"n": i, "target": target, "arguments": {"need": need, "os": target["os"]},
                                       "used_attempt": used, "attempts": attempts}, ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")
            if sound(attempts[-1]):
                break
        picks = [p["slug"] for p in ((attempts[used]["find"] or {}).get("picks") or [])]
        print(f"{i:02d} {target['slug']}: picks {picks} ({attempts[used]['latency_s']} s)")


def responses() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESPONSES.glob("*.json"))]


def step_cost() -> None:
    """Settle each Worker reservation with events.meta_cost_usd for its rec_id (read-only D1 query)."""
    rows: dict[str, int] = {}
    for r in responses():
        for a in r["attempts"]:
            rec = (a["find"] or {}).get("rec_id")
            if rec:
                rows[rec] = a["ledger_row"]
            else:
                WORKER_LEDGER.settle(a["ledger_row"], 0.0, status="no_rec_id")
    ids = ", ".join(f"'{rec}'" for rec in rows if re.fullmatch(r"rec_[0-9a-f]{32}", rec))
    wrangler = main_dotenv().parent / "worker" / "node_modules" / ".bin" / "wrangler"
    out = subprocess.run([str(wrangler), "d1", "execute", "pickfit", "--remote", "--json", "--command",
                          f"SELECT rec_id, meta_cost_usd, matched_by, degraded FROM events WHERE rec_id IN ({ids})"],
                         cwd=wrangler.parent.parent.parent, check=True, capture_output=True, text=True).stdout
    found = {e["rec_id"]: e for e in json.loads(out)[0]["results"]}
    spend = []
    for rec, row in rows.items():
        usd = float((found.get(rec) or {}).get("meta_cost_usd") or 0.0)
        WORKER_LEDGER.settle(row, usd, status="settled" if rec in found else "not_found")
        spend.append({"rec_id": rec, "meta_cost_usd": usd, "found": rec in found})
    SPEND.write_text(json.dumps({"worker": spend, "worker_total_usd": round(sum(s["meta_cost_usd"] for s in spend), 6),
                                 "anthropic": ANTHROPIC_LEDGER.spend_summary(),
                                 "worker_ledger": WORKER_LEDGER.spend_summary()},
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"worker_total_usd": round(sum(s["meta_cost_usd"] for s in spend), 6),
                      "anthropic_total_usd": ANTHROPIC_LEDGER.spend_summary()["total_usd"]}))


def used(r: dict[str, Any]) -> dict[str, Any]:
    return r["attempts"][r["used_attempt"]]["find"] or {}


def l1_message(question: dict[str, Any], os_name: str, evidence: dict[str, Any]) -> str:
    parsed = question["reply"]["parsed"]
    checks = [parsed["core_job"], *(c["condition"] for c in parsed["hard_conditions"])]
    lines = ["The user's request:", parsed["request"], "", f"The user's operating system: {os_name}", "", "Checks:"]
    lines += [f"{i}. {c}" for i, c in enumerate(checks, 1)]
    lines += ["", "Evidence about the tool:", f"Repository: github.com/{evidence['repo']} (commit {evidence.get('commit')})",
              f"License reported by GitHub: {evidence.get('license')}",
              f"Repository description: {evidence.get('description')}"]
    if evidence.get("text"):
        lines += [f"README ({evidence['path']}):", evidence["text"][:README_MAX_CHARS]]
    else:
        lines += ["README: not available"]
    return "\n".join(lines)


def evidence_for(url: str | None) -> dict[str, Any] | None:
    if not url or "github.com/" not in url:
        return None
    try:
        return fetch_readme(url)
    except LookupError:
        owner, repo = owner_repo(url)
        try:
            meta = gh(f"repos/{owner}/{repo}")
        except LookupError:
            return None
        return {"repo": meta["full_name"], "commit": None, "license": (meta.get("license") or {}).get("spdx_id"),
                "description": meta.get("description"), "text": None}


def step_l1() -> None:
    records = snapshot()
    questions = accepted_questions()
    done = set()
    if L1_OUT.exists():
        done = {(r["n"], r["role"]) for r in map(json.loads, L1_OUT.read_text(encoding="utf-8").splitlines())}
    rs = responses()
    jobs = []
    for r in rs:  # top picks first: acceptable@1 needs them; target checks are the secondary validity check
        picks = used(r).get("picks") or []
        if picks and picks[0]["slug"] != r["target"]["slug"]:
            jobs.append((r, "top_pick", picks[0]["slug"], picks[0].get("repo")))
    for r in rs:
        jobs.append((r, "target", r["target"]["slug"], records[r["target"]["slug"]]["repo"]["url"]))
    with L1_OUT.open("a", encoding="utf-8") as log:
        for r, role, slug, url in jobs:
            if (r["n"], role) in done:
                continue
            evidence = evidence_for(url)
            row = {"n": r["n"], "target": r["target"]["slug"], "role": role, "tool": slug, "at": now()}
            if evidence is None:
                row.update({"evidence": None, "reply": None, "overall": "unknown", "note": "no GitHub evidence"})
            else:
                message = l1_message(questions[r["target"]["slug"]], r["target"]["os"], evidence)
                reply = claude(L1_PROMPT, message, L1_EFFORT, L1_SCHEMA, f"l1:{role}", slug)
                row.update({"evidence": {k: v for k, v in evidence.items() if k != "text"}, "reply": reply,
                            "overall": (reply["parsed"] or {}).get("overall", "unknown")})
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            print(f"{r['n']:02d} {role} {slug}: {row['overall']}")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def step_report() -> None:
    records = snapshot()
    listed = {}
    for r in records.values():
        if r["status"] == "listed":
            listed[r["category"]] = listed.get(r["category"], 0) + 1
    l1 = {(r["n"], r["role"]): r for r in map(json.loads, L1_OUT.read_text(encoding="utf-8").splitlines())}
    rows = []
    for r in responses():
        find = used(r)
        picks = [p["slug"] for p in (find.get("picks") or [])]
        slug = r["target"]["slug"]
        hit1 = bool(picks) and picks[0] == slug
        top = l1.get((r["n"], "top_pick"))
        own = l1.get((r["n"], "target"))
        rows.append({"n": r["n"], "slug": slug, "stratum": r["target"]["stratum"], "os": r["target"]["os"],
                     "level": r["target"]["level"], "picks": picks, "hit1": hit1, "hit3": slug in picks,
                     "rank": picks.index(slug) + 1 if slug in picks else None,
                     "top_l1": top["overall"] if top else None,
                     "acceptable1": hit1 or bool(top and top["overall"] == "pass"),
                     "target_l1": own["overall"] if own else None,
                     "considered": find.get("considered"), "matched_by": find.get("matched_by"),
                     "degraded": find.get("degraded"), "attempts": len(r["attempts"]),
                     "listed_in_category": listed.get(r["target"]["category"], 0)})
    (HERE / "results.json").write_text(json.dumps({"catalog_entries": len(records), "rows": rows},
                                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def line(label: str, subset: list[dict[str, Any]], key: str) -> str:
        k, n = sum(r[key] for r in subset), len(subset)
        lo, hi = wilson(k, n)
        return f"| {label} | {k}/{n} | {lo:.0%}–{hi:.0%} |"

    valid = [r for r in rows if r["target_l1"] == "pass"]
    out = ["| 指標 | 全部 | Wilson 95% |", "|---|---|---|",
           line("hit@1", rows, "hit1"), line("hit@3", rows, "hit3"), line("acceptable@1", rows, "acceptable1"),
           "", f"目標本身通過 L1 的題（{len(valid)} 題）：", "", "| 指標 | 命中 | Wilson 95% |", "|---|---|---|",
           line("hit@1", valid, "hit1"), line("hit@3", valid, "hit3"), line("acceptable@1", valid, "acceptable1"),
           "", "| # | 層 | 目標 | OS | 等級 | 名次 | 第一名 | 第一名 L1 | 目標 L1 | considered | 同類 listed | 目錄 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['n']} | {r['stratum']} | `{r['slug']}` | {r['os']} | {r['level']} | "
                   f"{r['rank'] or '—'} | `{r['picks'][0] if r['picks'] else '—'}` | {r['top_l1'] or '—'} | "
                   f"{r['target_l1'] or '—'} | {r['considered']} | {r['listed_in_category']} | {len(records)} |")
    print("\n".join(out))


STEPS = {"sample": step_sample, "rewrite": step_rewrite, "run": step_run, "cost": step_cost, "l1": step_l1, "report": step_report}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        raise SystemExit(__doc__)
    STEPS[sys.argv[1]]()
