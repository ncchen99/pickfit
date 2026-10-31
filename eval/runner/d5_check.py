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
      get_install_guide's mcp_client_config (MCP servers) claims the handshake
      listed `tools` (tool_count of them), that `called_tool` returned a result,
      and with works_offline=true that the handshake also passed offline.
  (a, d) GUI: picks[].verification.gui and get_install_guide's verification.gui
      claim a launch of that tool on that os/arch: tier window = a passing gui
      check in the replay; tier ui_rendered and `screen` = the screen judge of
      that run (judge.json `screen`) said that screen; launch_offline=true = the
      gui check also passed offline. The level stays as claimed (install).
  (a, d) features (the feature-coverage branch; fields as it is merged into
      main): every features.checked[] {feature, check} on a pick or an install
      guide claims that `check` passed in that run's replay and exercised the
      feature: the replay must have a passing check with that exact command, and
      feature_judge.json, when the run has one, must say shows_it_working.
      features.not_checked[] (reasons, test_failed, test_failed_in_sandbox) and
      recorded=false claim nothing verified and are only listed.
  (c) how_we_know (code-written from the run, on picks and install guides):
      "installed it in a fresh OS/ARCH sandbox ... on DATE; <level text>"
      claims that os/arch at that level ("by hand on OS/ARCH" names a human run,
      which has no sandbox record); its MCP sentence ("handshake over T listed
      its N tools[ with the network off][, and a call to X returned a result]")
      and GUI sentence ("judged that <screen>[, and the launch passed again with
      the network off]") claim the same as the structured fields above.
  Labels, not verification claims: the rules path's picks[].match {quality,
      covers, missing} and match_quality describe how a profile's words cover
      the request; no sandbox record can back or refute them. They are checked
      for consistency only (present only when matched_by is "rules"; covers and
      missing disjoint; match_quality is the best pick's label, or none) and
      listed under `labels`, never counted as violations.
  (e) model-written text: picks[].fit, picks[].tradeoffs[], picks[].vs_well_known
      and picks[].why[].claim (for that pick); best_free.reason (for
      best_free.slug); well_known_option.why (for that outside tool, which
      pickfit never ran, so any such claim has no record); no_install_option,
      keep_current.reason and coverage_note (for every pick the clause names,
      else unattributed).
      A clause is split only at sentence ends and contrasts (but, while,
      however), never at commas, so an os list stays whole. A clause with a
      verification word (verified, tested, installed, checked, confirmed, ran,
      replayed, 驗證, 實測, 測試過, 安裝過, 跑過) claims each os it names
      (macOS also as Mac, Apple Silicon, M1-M5 Macs, OS X; Linux also as Ubuntu,
      Debian), with the arch when the clause names one, except an os that a
      negation (not, no, never, without, untested, 未, 沒有, 不) directly precedes.

Only sandbox records count (method sandbox, with report.json or replay.json);
their files must match the manifest's sha256, and the manifest must be the one
the A3 before-record names. A record's level is the lower of its
verification_run.json level and its replay's level, when it was replayed.

A claim is found when a raw record in the snapshot (runs/eval-evidence/verify/<id>/
with report.json or replay.json, listed in eval/results/evidence-manifest.json)
has: the same tool; the same os; the same arch when the claim gives one; a time
earlier than the eval attempt's start; a level not below the claimed one; and,
for (d), every step line among its commands verbatim. A data-file field with no
raw record is not found. A human run (method human) has no sandbox raw record
and is listed as not found with that reason.

One violation = one response x one tool x one os. The total must be 0. The
B question set (round bset) and the Haiku round are reported separately
(9.2 E.7; `--rounds bset`).
Clause-level (e) matching is a heuristic: every claim is written out with its
text so a person can audit it; the script never drops a claim it is unsure of.

Run with: uv run python eval/runner/d5_check.py [--rounds run1 run2 run3]
          uv run python eval/runner/d5_check.py --rounds bset     (9.2 E.7: listed separately)
          uv run python eval/runner/d5_check.py --rounds haiku
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
# how_we_know is written by code (worker/src/evidence.ts); these read it back.
LEVEL_TEXTS = {
    "the install finished and the tool started": "install",
    "a smoke test of its main function passed": "function",
    "its service answered a test request": "service",
    "it produced model output in a test run": "inference",
}
SCREEN_TEXTS = {
    "its main screen rendered": "main_ui",
    "its first-run (setup) screen rendered": "first_run",
    "it showed a sign-in screen": "sign_in_wall",
    "it showed an error": "crash_or_error",
    "the window was still blank or loading": "blank_or_loading",
    "it showed something other than its own UI": "other",
}
RAN_RE = re.compile(r"pickfit (?:installed it in a fresh (?P<os>\w+)/(?P<arch>\w+) sandbox|installed it by hand on "
                    r"(?P<hos>\w+)/(?P<harch>\w+))")
MCP_RE = re.compile(r"MCP client handshake over (?P<transport>\S+) listed its (?P<count>\d+) tools?(?P<offline> with the "
                    r"network off)?(?:, and a call to (?P<called>\S+) returned a result)?")
GUI_RE = re.compile(r"judged that (?P<screen>.+?)(?P<offline>, and the launch passed again with the network off)?\. That "
                    r"shows it installs and starts")
MCP_LIST_RE = re.compile(r"tools/list: ok count=(\d+)")
MCP_TOOL_RE = re.compile(r"^tool: (\S+)", re.M)
MCP_CALL_RE = re.compile(r"--call\s+(\S+)")


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
    kind: str = "level"  # level, gui, mcp, feature
    detail: dict[str, Any] = field(default_factory=dict)
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
        level = run.get("level")
        replay = replay_evidence({})
        if replay_path.exists():
            result = (json.loads(replay_path.read_text(encoding="utf-8")).get("result") or {})
            for key in ("steps", "setups", "checks"):
                for cmd in result.get(key) or []:
                    if cmd.get("command"):
                        commands.add(str(cmd["command"]))
            replay = replay_evidence(result)
            if result.get("level") in LEVEL_RANK and LEVEL_RANK[result["level"]] < LEVEL_RANK.get(level, 0):
                level = result["level"]  # the lower of the two: a claim needs the replay to back it too
        judge = read_json(folder / "judge.json") or {}
        feature_judge = read_json(folder / "feature_judge.json")
        by_slug.setdefault(entry["slug"], []).append({
            "id": run_id, "os": run.get("os"), "arch": run.get("arch"), "level": level,
            "method": run.get("method"), "checked_at": run.get("checked_at"), "commands": commands, **replay,
            "screen": judge.get("screen"),
            "feature_verdicts": {k: v[0] for k, v in ((feature_judge or {}).get("verdicts") or {}).items()}
            if feature_judge else None,
        })
    return by_slug


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def replay_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """What a replay's passing checks show: GUI launches, the MCP handshake and calls, every passing command."""
    passed = [c for c in result.get("checks") or [] if c.get("passed")]
    out: dict[str, Any] = {"passed_checks": {str(c["command"]) for c in passed if c.get("command")},
                           "gui_launches": [], "mcp_tools": set(), "mcp_count": None, "mcp_called": set(),
                           "mcp_offline": False}
    for c in passed:
        stdout = str((c.get("run") or {}).get("stdout") or "")
        if c.get("kind") == "gui":
            out["gui_launches"].append({"window": "gui tier: window" in stdout, "offline": c.get("offline") is True})
        elif c.get("kind") in ("mcp", "mcp_call"):
            out["mcp_tools"] |= set(MCP_TOOL_RE.findall(stdout))
            count = MCP_LIST_RE.search(stdout)
            if count:
                out["mcp_count"] = int(count.group(1))
            if c.get("kind") == "mcp":
                out["mcp_offline"] = out["mcp_offline"] or c.get("offline") is True
            else:
                out["mcp_called"] |= set(MCP_CALL_RE.findall(str(c.get("command") or "")))
    return out


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

    def add(slug, os_name, arch, level, source, text, steps=None, kind="level", detail=None):
        out.append(Claim(**ctx, tool_name=call["name"], slug=slug, os=os_name, arch=arch, level=level,
                         source=source, text=text[:400], steps=steps or [], kind=kind, detail=detail or {}))

    def how_we_know(slug, text):
        """(c) the code-written sentence about the run: os/arch and level, plus its MCP or GUI part."""
        text = str(text or "")
        ran = RAN_RE.search(text)
        if not ran:
            return
        os_name, arch = ran.group("os") or ran.group("hos"), ran.group("arch") or ran.group("harch")
        level = next((lv for phrase, lv in LEVEL_TEXTS.items() if phrase in text), "install")
        add(slug, os_name, arch, level, "c", text)
        mcp = MCP_RE.search(text)
        if mcp:
            add(slug, os_name, arch, "install", "c", mcp.group(0), kind="mcp",
                detail={"tool_count": int(mcp.group("count")), "called_tool": mcp.group("called"),
                        "works_offline": bool(mcp.group("offline"))})
        gui = GUI_RE.search(text)
        if gui:
            screen = next((v for phrase, v in SCREEN_TEXTS.items() if gui.group("screen").startswith(phrase)), None)
            add(slug, os_name, arch, "install", "c", gui.group(0), kind="gui",
                detail={"screen": screen or "unrecognised: " + gui.group("screen")[:60],
                        "launch_offline": bool(gui.group("offline"))})

    def gui(slug, ver, source):
        if ver.get("gui") and ver.get("os"):
            add(slug, ver["os"], ver.get("arch"), "install", source, json.dumps(ver["gui"], ensure_ascii=False),
                kind="gui", detail=dict(ver["gui"]))

    def features(slug, ver, coverage, source):
        for item in (coverage or {}).get("checked") or []:
            if ver.get("os"):
                add(slug, ver["os"], ver.get("arch"), "install", source, json.dumps(item, ensure_ascii=False),
                    kind="feature", detail={"feature": item.get("feature"), "check": item.get("check")})

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
            gui(pick["slug"], ver, "a")
            features(pick["slug"], ver, pick.get("features"), "a")
            how_we_know(pick["slug"], pick.get("how_we_know"))
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
        for text in (body.get("no_install_option"), (body.get("keep_current") or {}).get("reason"),
                     body.get("coverage_note")):
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
            slug = body.get("slug") or args.get("slug")
            add(slug, ver["os"], ver.get("arch"),
                ver.get("level") if ver.get("level") in LEVEL_RANK else "install", "d",
                json.dumps(ver, ensure_ascii=False), steps)
            gui(slug, ver, "d")
            features(slug, ver, body.get("features"), "d")
            mcp = body.get("mcp_client_config")
            if mcp:
                add(slug, ver["os"], ver.get("arch"), "install", "d", json.dumps(mcp, ensure_ascii=False)[:400],
                    kind="mcp", detail={"tools": mcp.get("tools") or [], "tool_count": mcp.get("tool_count"),
                                        "called_tool": mcp.get("called_tool"),
                                        "works_offline": mcp.get("works_offline") is True})
        how_we_know(body.get("slug") or args.get("slug"), body.get("how_we_know"))
    return out


def label_problems(body: dict[str, Any]) -> list[str]:
    """The rules path's match labels: not verification claims, only checked for consistency."""
    problems = []
    picks = body.get("picks") or []
    rules = body.get("matched_by") == "rules"
    labels = [p.get("match") for p in picks if p.get("match")]
    if (labels or body.get("match_quality")) and not rules:
        problems.append(f"match labels on an answer matched by {body.get('matched_by')!r}, not rules")
    for p in picks:
        m = p.get("match") or {}
        if set(m.get("covers") or []) & set(m.get("missing") or []):
            problems.append(f"{p.get('slug')}: words both covered and missing")
    if rules and labels and body.get("match_quality"):
        order = {"good": 2, "partial": 1, "weak": 0}
        best = max(labels, key=lambda m: order.get(m.get("quality"), -1)).get("quality")
        expect = best if best in ("good", "partial") else "none"
        if body["match_quality"] != expect:
            problems.append(f"match_quality {body['match_quality']} but the best pick is {best}")
    return problems


def detail_problem(claim: Claim, record: dict[str, Any]) -> str | None:
    """Why this record does not back a GUI, MCP or feature claim; None when it does."""
    d = claim.detail
    if claim.kind == "gui":
        launches = record.get("gui_launches") or []
        if not launches:
            return "no passing GUI launch in the replay"
        if d.get("tier") == "window" and not any(l["window"] for l in launches):
            return "no window of the app's own process in the replay"
        if d.get("screen") and record.get("screen") != d["screen"]:
            return f"the screen judge said {record.get('screen')}, not {d['screen']}"
        if d.get("launch_offline") and not any(l["offline"] for l in launches):
            return "the GUI launch did not pass offline"
    elif claim.kind == "mcp":
        listed = record.get("mcp_tools") or set()
        if record.get("mcp_count") is None:
            return "no passing MCP handshake in the replay"
        if d.get("tool_count") is not None and d["tool_count"] != record["mcp_count"]:
            return f"the handshake listed {record['mcp_count']} tools, not {d['tool_count']}"
        missing = [t for t in d.get("tools") or [] if t not in listed]
        if missing:
            return f"tools not in the handshake: {missing[:3]}"
        if d.get("called_tool") and d["called_tool"] not in (record.get("mcp_called") or set()):
            return f"no passing call to {d['called_tool']}"
        if d.get("works_offline") and not record.get("mcp_offline"):
            return "the handshake did not pass offline"
    elif claim.kind == "feature":
        if d.get("check") not in (record.get("passed_checks") or set()):
            return f"no passing check with that command: {str(d.get('check'))[:80]}"
        verdicts = record.get("feature_verdicts")
        if verdicts is not None and verdicts.get(d.get("feature")) != "shows_it_working":
            return f"the feature judge said {verdicts.get(d.get('feature'))!r} for {d.get('feature')!r}"
    return None


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
        problem = detail_problem(claim, record)
        if problem:
            reasons.append(f"{record['id']}: {problem}")
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
    labels: list[dict[str, Any]] = []
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
                if call["name"] in ("find_software", "find_alternatives"):
                    labels.append({**ctx, "tool_name": call["name"], "matched_by": body.get("matched_by"),
                                   "match_quality": body.get("match_quality"),
                                   "picks": [{"slug": p.get("slug"), "match": p.get("match")} for p in body.get("picks") or []],
                                   "problems": label_problems(body)})
    violations = {(c.round, c.question, c.group, c.attempt, c.response_index, c.slug, c.os)
                  for c in claims if c.status == "not_found"}
    return {
        "rounds": rounds,
        "evidence_problems": integrity,
        "claims": [asdict(c) for c in claims],
        "unreadable_responses": unreadable,
        "labels": labels,
        "label_problems": sum(len(x["problems"]) for x in labels),
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
          f"{report['cannot_check']} cannot check, {report['label_problems']} rules-label problem(s) "
          f"(not violations) -> {path.relative_to(ROOT)}")
    for problem in report["evidence_problems"][:10]:
        print(f"evidence problem: {problem}")
    return 1 if report["violations"] or report["evidence_problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
