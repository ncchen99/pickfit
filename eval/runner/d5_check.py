"""D5: pickfit itself must not overstate verification (eval/README.md 9.1 D5).

Reads every pickfit response in the experimental and rules-only groups, all
rounds, from the tested agent's stream-json log, extracts every claim marked as
verified, and looks for a raw sandbox record in the A3 snapshot that backs it.

Field mapping (A4 requires it here). Response fields are those of the Worker
version recorded in A3 (worker/src/server.ts):

  (a) find_software / find_alternatives: picks[].verification {level, os, arch,
      method}. A level other than unverified/failed claims that tool at that
      level on that os (and arch when not null).
  (b) picks[].verification.verified_on_user_os == true claims the tool on the
      os (and arch, when given) in the tool call's own arguments.
  (c) picks[].why[] items whose field is verified_on or verified_on_user_os
      claim the tool on each os (and the arch, when one is named) in their value.
  (d) get_install_guide: verification.status == "verified" claims the tool at
      verification.level on verification.os/arch, and every steps[].command,
      first_task_setup[].command and verify.command must equal, character for
      character, a command the backing record ran.
  (e) model-written text: picks[].fit, picks[].tradeoffs[], picks[].vs_well_known
      and picks[].why[].claim (for that pick); best_free.reason (for
      best_free.slug); well_known_option.why (for that outside tool, which
      pickfit never ran, so any such claim has no record); no_install_option and
      keep_current.reason (for every pick the clause names, else unattributed).
      A clause is split only at sentence ends and contrasts (but, while,
      however), never at commas, so an os list stays whole. A clause with a
      verification word (verified, tested, installed, checked, confirmed, ran,
      replayed, 驗證, 實測, 測試過, 安裝過, 跑過) claims each os it names
      (macOS also as Mac, Apple Silicon, M1-M5 Macs, OS X; Linux also as Ubuntu,
      Debian), with the arch when the clause names one, except an os that a
      negation (not, no, never, without, untested, 未, 沒有, 不) directly precedes.

Only sandbox records count (method sandbox, with report.json or replay.json);
their files must match the manifest's sha256, and the manifest must be the one
the A3 before-record names.

A claim is found when a raw record in the snapshot (runs/eval-evidence/verify/<id>/
with report.json or replay.json, listed in eval/results/evidence-manifest.json)
has: the same tool; the same os; the same arch when the claim gives one; a time
earlier than the eval attempt's start; a level not below the claimed one; and,
for (d), every step line among its commands verbatim. A data-file field with no
raw record is not found. A human run (method human) has no sandbox raw record
and is listed as not found with that reason.

One violation = one response x one tool x one os. The total must be 0.
Clause-level (e) matching is a heuristic: every claim is written out with its
text so a person can audit it; the script never drops a claim it is unsure of.

Run with: uv run python eval/runner/d5_check.py [--rounds run1 run2 run3]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "eval" / "results" / "runs"
EVIDENCE = ROOT / "runs" / "eval-evidence" / "verify"
MANIFEST = ROOT / "eval" / "results" / "evidence-manifest.json"
OUT = ROOT / "eval" / "results"

LEVEL_RANK = {"install": 1, "function": 2, "service": 3, "inference": 4}
OS_PATTERNS = [
    (r"apple silicon|apple-silicon|m[1-5] macs?|intel macs?|macbooks?|macos|mac os|os ?x|macs?\b|mac(?=\s)", "macos"),
    (r"linux|ubuntu|debian", "linux"),
    (r"windows|win11|win10", "windows"),
]
OS_RE = re.compile("|".join(f"(?P<{name}{i}>{pattern})" for i, (pattern, name) in enumerate(OS_PATTERNS)), re.I)
ARCH_RE = re.compile(r"\b(arm64|aarch64|apple silicon|x86[_-]64|amd64|intel)\b", re.I)
ARCH_WORDS = {"arm64": "arm64", "aarch64": "arm64", "apple silicon": "arm64", "x86_64": "x86_64", "x86-64": "x86_64",
              "amd64": "x86_64", "intel": "x86_64"}
VERIFY_RE = re.compile(r"\b(verified|verify|verifies|tested|installed|checked|confirmed|ran|run on|replayed)\b|驗證|實測|測試過|安裝過|跑過", re.I)
# A negation counts only just before the os it denies: "not on Windows", "no macOS run".
NEGATION_BEFORE = re.compile(r"(\bnot\b|\bnever\b|\bno\b|n't\b|\bwithout\b|\bunverified\b|\buntested\b|\byet to\b|未|沒有|尚未|不)[^.;:()]{0,30}$", re.I)
# Split at sentence ends and contrasts only: a comma-separated os list stays in one clause.
CLAUSE_SPLIT = re.compile(r"[.;；。!?！？]\s|\bbut\b|\bwhile\b|\bhowever\b|\bwhereas\b|但|而|然而", re.I)
MODEL_TEXT_PICK_FIELDS = ("fit", "vs_well_known")


@dataclass
class Claim:
    round: str
    question: str
    group: str
    attempt: int
    response_index: int
    tool_name: str
    slug: str
    os: str
    arch: str | None
    level: str | None
    source: str  # a, b, c, d, e
    text: str
    steps: list[str] = field(default_factory=list)
    status: str = "unchecked"  # found, not_found, cannot_check
    reason: str | None = None
    record: str | None = None


def load_records(evidence: Path = EVIDENCE, manifest: Path = MANIFEST) -> dict[str, list[dict[str, Any]]]:
    """slug -> raw sandbox records with their os, arch, level, time and every command."""
    listed = json.loads(manifest.read_text(encoding="utf-8"))["runs"] if manifest.exists() else {}
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for run_id, entry in listed.items():
        folder = evidence / run_id
        run_path, report_path, replay_path = folder / "verification_run.json", folder / "report.json", folder / "replay.json"
        if not run_path.exists() or not (report_path.exists() or replay_path.exists()):
            continue
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if run.get("method") != "sandbox":
            continue  # D5 counts only a sandbox run's raw record
        commands: set[str] = set()
        if report_path.exists():
            for cmd in json.loads(report_path.read_text(encoding="utf-8")).get("commands") or []:
                if cmd.get("command") and cmd.get("tool") in (None, "run_command", "run_background"):
                    commands.add(str(cmd["command"]))
        if replay_path.exists():
            result = (json.loads(replay_path.read_text(encoding="utf-8")).get("result") or {})
            for key in ("steps", "setups", "checks"):
                for cmd in result.get(key) or []:
                    if cmd.get("command"):
                        commands.add(str(cmd["command"]))
        by_slug.setdefault(entry["slug"], []).append({
            "id": run_id, "os": run.get("os"), "arch": run.get("arch"), "level": run.get("level"),
            "method": run.get("method"), "checked_at": run.get("checked_at"), "commands": commands,
        })
    return by_slug


def evidence_integrity(evidence: Path = EVIDENCE, manifest: Path = MANIFEST,
                       before: Path = OUT / "versions-before.json") -> list[str]:
    """The raw records must be the files the A3 snapshot recorded, byte for byte."""
    problems = []
    if not manifest.exists():
        return ["no evidence manifest"]
    import hashlib

    if before.exists():
        recorded = json.loads(before.read_text(encoding="utf-8")).get("evidence_manifest_sha256")
        actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
        if recorded != actual:
            problems.append(f"evidence manifest {actual[:12]} is not the one A3 recorded ({str(recorded)[:12]})")
    for run_id, entry in json.loads(manifest.read_text(encoding="utf-8"))["runs"].items():
        for name, digest in entry.get("files", {}).items():
            path = evidence / run_id / name
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                problems.append(f"{run_id}/{name} differs from the manifest")
    return problems


def tool_calls(stream: Path) -> list[dict[str, Any]]:
    """Every pickfit tool call in a stream-json log, with its input and raw result text."""
    uses: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for raw in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        content = (event.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use" and str(block.get("name", "")).startswith("mcp__pickfit__"):
                call = {"id": block.get("id"), "name": block["name"].removeprefix("mcp__pickfit__"),
                        "input": block.get("input") or {}, "result_text": None, "is_error": None}
                uses[call["id"]] = call
                ordered.append(call)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in uses:
                body = block.get("content")
                if isinstance(body, list):
                    body = "".join(part.get("text", "") for part in body if isinstance(part, dict))
                uses[block["tool_use_id"]]["result_text"] = body
                uses[block["tool_use_id"]]["is_error"] = block.get("is_error")
    return ordered


def parse_result(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        start = text.find("{")
        try:
            return json.loads(text[start:]) if start >= 0 else None
        except ValueError:
            return None


def os_mentions(text: str) -> list[tuple[str, int]]:
    out = []
    for match in OS_RE.finditer(text or ""):
        name = next(k for k, v in match.groupdict().items() if v)
        out.append((re.sub(r"\d+$", "", name), match.start()))
    return out


def os_in(text: str) -> list[str]:
    return sorted({name for name, _ in os_mentions(text)})


def arch_in(text: str) -> str | None:
    found = {ARCH_WORDS[m.group(1).lower()] for m in ARCH_RE.finditer(text or "")}
    return found.pop() if len(found) == 1 else None


def text_claims(text: str) -> list[tuple[str, str | None, str]]:
    """(os, arch, clause) for each os a clause says the tool was verified on, unless that os is negated."""
    found = []
    for clause in CLAUSE_SPLIT.split(text or ""):
        if not VERIFY_RE.search(clause):
            continue
        for os_name, start in os_mentions(clause):
            if NEGATION_BEFORE.search(clause[max(0, start - 40):start]):
                continue
            found.append((os_name, arch_in(clause), clause.strip()))
    return found


def claims_from(call: dict[str, Any], body: dict[str, Any], ctx: dict[str, Any]) -> list[Claim]:
    out: list[Claim] = []

    def add(slug, os_name, arch, level, source, text, steps=None):
        out.append(Claim(**ctx, tool_name=call["name"], slug=slug, os=os_name, arch=arch, level=level,
                         source=source, text=text[:400], steps=steps or []))

    def scan(slug, text, source="e"):
        for os_name, arch, clause in text_claims(str(text or "")):
            add(slug, os_name, arch, "install", source, clause)

    args = call["input"]
    if call["name"] in ("find_software", "find_alternatives"):
        picks = body.get("picks") or []
        names = {p.get("slug"): {p.get("slug", "").lower(), str(p.get("name", "")).lower()} for p in picks}
        for pick in picks:
            ver = pick.get("verification") or {}
            level = ver.get("level")
            if level in LEVEL_RANK and ver.get("os"):
                add(pick["slug"], ver["os"], ver.get("arch"), level, "a", json.dumps(ver, ensure_ascii=False))
            if ver.get("verified_on_user_os") is True and args.get("os"):
                add(pick["slug"], args["os"], args.get("arch"), level if level in LEVEL_RANK else "install", "b",
                    f"verified_on_user_os=true for os={args.get('os')} arch={args.get('arch')}")
            for reason in pick.get("why") or []:
                if reason.get("field") in ("verified_on", "verified_on_user_os"):
                    for os_name in os_in(str(reason.get("value", ""))):
                        add(pick["slug"], os_name, arch_in(str(reason.get("value", ""))), "install", "c",
                            json.dumps(reason, ensure_ascii=False))
                scan(pick["slug"], reason.get("claim"))  # the model's own sentence for the reason
            for key in MODEL_TEXT_PICK_FIELDS:
                scan(pick["slug"], pick.get(key))
            for tradeoff in pick.get("tradeoffs") or []:
                scan(pick["slug"], tradeoff)
        best_free = body.get("best_free") or {}
        if best_free.get("slug"):
            scan(best_free["slug"], best_free.get("reason"))
        well_known = body.get("well_known_option") or {}
        if well_known.get("name"):
            # pickfit never ran it: any verification claim about it has no record by definition.
            scan(f"well_known:{well_known['name']}", well_known.get("why"))
        for text in (body.get("no_install_option"), (body.get("keep_current") or {}).get("reason")):
            for os_name, arch, clause in text_claims(str(text or "")):
                named = [slug for slug, keys in names.items() if any(k and k in clause.lower() for k in keys)]
                for slug in named or ["(unattributed)"]:
                    add(slug, os_name, arch, "install", "e", clause)
    elif call["name"] == "get_install_guide":
        ver = body.get("verification") or {}
        if ver.get("status") == "verified" and ver.get("os"):
            steps = [str(s.get("command")) for s in body.get("steps") or []]
            steps += [str(s.get("command")) for s in body.get("first_task_setup") or []]
            if (body.get("verify") or {}).get("command"):
                steps.append(str(body["verify"]["command"]))
            add(body.get("slug") or args.get("slug"), ver["os"], ver.get("arch"),
                ver.get("level") if ver.get("level") in LEVEL_RANK else "install", "d",
                json.dumps(ver, ensure_ascii=False), steps)
    return out


def check(claim: Claim, records: dict[str, list[dict[str, Any]]], attempt_start: dt.datetime) -> Claim:
    if claim.slug == "(unattributed)":
        claim.status, claim.reason = "cannot_check", "answer-level sentence names no pick"
        return claim
    candidates = records.get(claim.slug) or []
    reasons = []
    for record in candidates:
        if record["os"] != claim.os:
            continue
        if claim.arch and record["arch"] != claim.arch:
            reasons.append(f"{record['id']}: arch {record['arch']}")
            continue
        when = dt.datetime.fromisoformat(record["checked_at"]) if record.get("checked_at") else None
        if when is None or when >= attempt_start:
            reasons.append(f"{record['id']}: not earlier than the attempt")
            continue
        if LEVEL_RANK.get(record["level"], 0) < LEVEL_RANK.get(claim.level or "install", 1):
            reasons.append(f"{record['id']}: level {record['level']} < {claim.level}")
            continue
        if claim.steps and not all(step in record["commands"] for step in claim.steps):
            missing = [s for s in claim.steps if s not in record["commands"]]
            reasons.append(f"{record['id']}: step not in the record: {missing[0][:80]}")
            continue
        claim.status, claim.record = "found", record["id"]
        return claim
    claim.status = "not_found"
    claim.reason = "; ".join(reasons) or f"no raw sandbox record for {claim.slug} on {claim.os}"
    return claim


def run(rounds: list[str], runs: Path = RUNS, evidence: Path = EVIDENCE, manifest: Path = MANIFEST) -> dict[str, Any]:
    records = load_records(evidence, manifest)
    integrity = evidence_integrity(evidence, manifest, manifest.parent / "versions-before.json") if manifest.exists() else ["no evidence manifest"]
    claims: list[Claim] = []
    unreadable: list[dict[str, Any]] = []
    for rnd in rounds:
        for meta_path in sorted((runs / rnd).glob("*/*/attempt-*/meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["group"] not in ("experimental", "rules_only"):
                continue
            start = dt.datetime.fromisoformat(meta["started_at"])
            for index, call in enumerate(tool_calls(meta_path.parent / "stream.jsonl")):
                ctx = {"round": rnd, "question": meta["question"], "group": meta["group"],
                       "attempt": meta["attempt"], "response_index": index}
                body = parse_result(call["result_text"])
                if body is None:
                    rec = re.search(r"rec_[0-9a-f]{8,}", call["result_text"] or "")
                    unreadable.append({**ctx, "tool_name": call["name"], "is_error": call["is_error"],
                                       "rec_id": rec.group(0) if rec else None,
                                       "note": "response not parseable (error, empty or truncated): look it up by rec_id in the Worker events, else cannot check"})
                    continue
                for claim in claims_from(call, body, ctx):
                    claims.append(check(claim, records, start))
    violations = {(c.round, c.question, c.group, c.attempt, c.response_index, c.slug, c.os)
                  for c in claims if c.status == "not_found"}
    return {
        "rounds": rounds,
        "evidence_problems": integrity,
        "claims": [asdict(c) for c in claims],
        "unreadable_responses": unreadable,
        "violations": len(violations),
        "cannot_check": sum(1 for c in claims if c.status == "cannot_check") + len(unreadable),
        "found": sum(1 for c in claims if c.status == "found"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/d5_check.py")
    parser.add_argument("--rounds", nargs="+", default=["run1", "run2", "run3"])
    args = parser.parse_args(argv)
    report = run([r for r in args.rounds if (RUNS / r).exists()])
    path = OUT / f"d5-{'-'.join(report['rounds']) or 'none'}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n", encoding="utf-8")
    print(f"D5: {report['violations']} violation(s), {report['found']} claim(s) found, "
          f"{report['cannot_check']} cannot check -> {path.relative_to(ROOT)}")
    for problem in report["evidence_problems"][:10]:
        print(f"evidence problem: {problem}")
    return 1 if report["violations"] or report["evidence_problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
