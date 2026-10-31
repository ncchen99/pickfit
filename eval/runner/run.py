"""pickfit evaluation runner (eval/README.md sections 4 and 9.1).

Every run is a new `claude -p` process in a new empty working directory with a
new empty HOME, so nothing from this Mac's user config (CLAUDE.md, plugins,
hooks, skills, other MCP servers) reaches the agent. The agent gets only the
built-in WebSearch and WebFetch tools, plus the pickfit MCP for the
experimental and rules-only groups (--strict-mcp-config). `--bare` is not used:
it drops WebSearch and WebFetch (checked 10/29 with Claude Code 2.1.304).

Commands:
  snapshot --label before|after   A3 version record -> eval/results/versions-<label>.json
  run1                            first run, all three groups, order per B1
  reruns                          runs 2 and 3, control and experimental, per B3
  check --round run1              B2 check of every attempt's version, model and tools
  status                          what has run, what it cost

Run with: uv run --with pyyaml==6.0.2 python eval/runner/run.py <command>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
RESULTS = EVAL / "results"
RUNS = RESULTS / "runs"
CONFIG_PATH = EVAL / "runner" / "config.json"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
GROUPS = ("control", "experimental", "rules_only")
# B2: only these Anthropic errors make a run invalid (retried). Server errors can arrive mid-stream with no status code.
API_ERROR = re.compile(r"API Error[^\n]{0,60}\b(5\d\d|429)\b|overloaded|API Error: Server error|Internal server error", re.I)
API_ERROR_KINDS = {"server_error", "overloaded_error", "rate_limit_error", "api_error"}
# Not a run at all: the key, the account or the credit balance is wrong. Stop and fix; never count it.
SETUP_ERROR = re.compile(r"invalid (x-)?api[ -]key|authentication_error|credit balance is too low|"
                         r"billing|permission_error|API Error[^\n]{0,60}\b(401|403)\b", re.I)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def load_questions() -> list[dict[str, Any]]:
    import yaml  # uv run --with pyyaml; not a pickfit dependency

    data = yaml.safe_load((EVAL / "questions.yaml").read_text(encoding="utf-8"))
    questions = sorted(data["questions"], key=lambda q: q["id"])
    return questions


# --- order (B1, B3) -------------------------------------------------------------


def run1_order(qid: str) -> list[str]:
    """B1: odd questions start with control, even with experimental; rules-only last."""
    number = int(qid.lstrip("q"))
    pair = ["control", "experimental"] if number % 2 else ["experimental", "control"]
    return [*pair, "rules_only"]


def rerun_order(rounds: list[int]) -> list[tuple[str, int]]:
    """B3: per question C2, E2, E3, C3; with only run 2 planned, C2 then E2."""
    if rounds == [2]:
        return [("control", 2), ("experimental", 2)]
    return [("control", 2), ("experimental", 2), ("experimental", 3), ("control", 3)]


# --- one run ----------------------------------------------------------------------


def round_name(number: int) -> str:
    return f"run{number}"


def attempt_dir(rnd: str, qid: str, group: str, attempt: int, base: Path | None = None) -> Path:
    return (base or RUNS) / rnd / qid / group / f"attempt-{attempt}"


def build_prompt(config: dict[str, Any], question: dict[str, Any]) -> str:
    """Section 4: only the question's prompt, after the same opening for every question."""
    return f"{config['preamble']}\n\n{question['prompt'].strip()}"


def build_cmd(config: dict[str, Any], group: str, mcp_path: Path, prompt: str) -> list[str]:
    spec = config["groups"][group]
    allowed = [*spec["tools"], *(f"mcp__{name}" for name in spec["mcp"])]
    return [
        os.path.expanduser(config["claude_bin"]), "-p",
        "--tools", ",".join(spec["tools"]),
        "--allowedTools", *allowed,
        "--strict-mcp-config", "--mcp-config", str(mcp_path),
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
        "--max-budget-usd", str(config["per_run_budget_usd"]),
        "--model", config["model"],
        prompt,
    ]


def isolated_env(home: Path, api_key: str) -> dict[str, str]:
    """Nothing from this shell or this Mac's Claude config: a fresh HOME and a bare PATH.

    MCP_TIMEOUT gives the pickfit Worker time to answer before the first turn, so a cold
    start does not look like a missing tool list.
    """
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "ANTHROPIC_API_KEY": api_key,
        "DISABLE_AUTOUPDATER": "1",
        "LANG": "en_US.UTF-8",
        "MCP_TIMEOUT": "30000",
    }


def read_api_key() -> str:
    sys.path.insert(0, str(ROOT))
    from pickfit.env import read_env

    return read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"]


@dataclass
class Execution:
    exit_code: int | None
    timed_out: bool
    started_at: str
    ended_at: str
    duration_s: float


def execute(cmd: list[str], env: dict[str, str], cwd: Path, out: Path, err: Path, timeout_s: int) -> Execution:
    started, t0 = now(), time.monotonic()
    with out.open("wb") as fo, err.open("wb") as fe:
        proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                                start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    return Execution(proc.returncode, timed_out, started, now(), round(time.monotonic() - t0, 1))


@dataclass
class Parsed:
    init: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    last_assistant_text: str | None = None
    api_error_texts: list[str] = field(default_factory=list)
    setup_error_texts: list[str] = field(default_factory=list)
    pickfit_calls: list[str] = field(default_factory=list)
    models_seen: set[str] = field(default_factory=set)
    usage: dict[str, int] = field(default_factory=dict)
    ended_on_error: bool = False  # the last assistant message was an API error notice, not text
    lines: int = 0
    bad_lines: int = 0


def parse_stream(path: Path) -> Parsed:
    parsed = Parsed()
    if not path.exists():
        return parsed
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        parsed.lines += 1
        try:
            event = json.loads(raw)
        except ValueError:
            parsed.bad_lines += 1
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            parsed.init = event
        elif kind == "result":
            parsed.result = event
        elif kind == "assistant":
            message = event.get("message") or {}
            if message.get("model") and message.get("model") != "<synthetic>":
                parsed.models_seen.add(message["model"])
            for key, value in (message.get("usage") or {}).items():
                if isinstance(value, int):
                    parsed.usage[key] = parsed.usage.get(key, 0) + value
            texts = []
            for block in message.get("content") or []:
                if block.get("type") == "text":
                    texts.append(block.get("text") or "")
                elif block.get("type") == "tool_use" and str(block.get("name", "")).startswith("mcp__pickfit__"):
                    parsed.pickfit_calls.append(block["name"])
            text = "\n".join(t for t in texts if t)
            error_kind = event.get("error") or message.get("error")
            is_error_notice = text.lstrip().startswith("API Error") or bool(error_kind)
            if text and is_error_notice:
                if SETUP_ERROR.search(text) or error_kind in ("authentication_error", "permission_error", "billing_error"):
                    parsed.setup_error_texts.append(text[:300])
                elif API_ERROR.search(text) or error_kind in API_ERROR_KINDS:
                    parsed.api_error_texts.append(text[:300])
                parsed.ended_on_error = True
            elif text:
                parsed.last_assistant_text = text  # an error notice is never the agent's answer
                parsed.ended_on_error = False
    return parsed


class SetupError(Exception):
    """The key, account or balance is wrong: not a run under B2. Stop the whole command."""


def classify(parsed: Parsed, execution: Execution) -> tuple[bool, str | None]:
    """B2: invalid only for an Anthropic API error or a runner crash with no final answer.

    A timeout, a budget stop, an empty answer, a refusal, or a pickfit error is a valid run.
    An authentication or billing error is not a run at all (SetupError).
    """
    result = parsed.result
    text = str((result or {}).get("result") or "")
    errors = " ".join(str(e) for e in (result or {}).get("errors") or [])
    if parsed.setup_error_texts or ((result or {}).get("is_error") and SETUP_ERROR.search(text + " " + errors)):
        raise SetupError((parsed.setup_error_texts or [text or errors])[-1][:300])
    if parsed.api_error_texts and parsed.ended_on_error:
        # The run ended on an Anthropic error; one Claude Code recovered from is not an error.
        return False, f"api_error: {parsed.api_error_texts[-1]}"
    if result is not None:
        if result.get("is_error") and API_ERROR.search(text + " " + errors):
            return False, f"api_error: {(text or errors)[:200]}"
        if result.get("subtype") == "error_during_execution" and not text and not parsed.last_assistant_text:
            return False, f"runner_crash: error_during_execution, no final answer {errors[:150]}"
        return True, None
    if execution.timed_out:
        return True, None  # scored on the last assistant message
    return False, f"runner_crash: exit {execution.exit_code}, no result event"


def final_answer(parsed: Parsed) -> str:
    if parsed.result is not None and parsed.result.get("result"):
        return str(parsed.result["result"])
    return parsed.last_assistant_text or ""


def run_cost(parsed: Parsed, config: dict[str, Any]) -> tuple[float, bool]:
    """(USD, exact). Without a result event the cost is unknown; count the per-run budget cap."""
    if parsed.result is not None and parsed.result.get("total_cost_usd") is not None:
        return float(parsed.result["total_cost_usd"]), True
    return float(config["per_run_budget_usd"]), False


def config_problems(parsed: Parsed, group: str, config: dict[str, Any]) -> list[str]:
    """B2: the version, model and tool list each attempt actually ran with.

    A pickfit server that is configured but not connected is pickfit failing (a valid run,
    E's tool_error), not a misconfigured group; `pickfit_unavailable` reports it.
    """
    init = parsed.init
    if init is None:
        return ["no init event"]
    spec = config["groups"][group]
    problems = []
    if init.get("claude_code_version") != config["claude_code_version"]:
        problems.append(f"claude_code_version {init.get('claude_code_version')} != {config['claude_code_version']}")
    if init.get("model") != config["model"]:
        problems.append(f"model {init.get('model')} != {config['model']}")
    other_models = sorted(parsed.models_seen - {config["model"]})
    if other_models:
        problems.append(f"the run switched to other models {other_models}")
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    if set(servers) != set(spec["mcp"]):
        problems.append(f"mcp servers {sorted(servers)} != {sorted(spec['mcp'])}")
    tools = sorted(init.get("tools") or [])
    builtin = sorted(t for t in tools if not t.startswith("mcp__"))
    if builtin != sorted(spec["tools"]):
        problems.append(f"built-in tools {builtin} != {sorted(spec['tools'])}")
    mcp_tools = sorted(t for t in tools if t.startswith("mcp__"))
    connected = all(status == "connected" for status in servers.values())
    if connected and mcp_tools != sorted(spec["expected_mcp_tools"]):
        problems.append(f"mcp tools {mcp_tools} != {sorted(spec['expected_mcp_tools'])}")
    if not connected and any(not t.startswith("mcp__pickfit__") for t in mcp_tools):
        problems.append(f"unexpected mcp tools {mcp_tools}")
    return problems


def pickfit_unavailable(parsed: Parsed) -> list[str]:
    servers = (parsed.init or {}).get("mcp_servers") or []
    return [f"{s.get('name')}: {s.get('status')}" for s in servers if s.get("status") != "connected"]


def run_once(config: dict[str, Any], question: dict[str, Any], group: str, rnd: str, attempt: int,
             api_key: str, base: Path | None = None) -> dict[str, Any]:
    folder = attempt_dir(rnd, question["id"], group, attempt, base)
    folder.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix=f"pickfit-eval-{question['id']}-{group}-"))
    try:
        home, work = scratch / "home", scratch / "work"
        home.mkdir()
        work.mkdir()
        mcp_path = scratch / "mcp.json"
        mcp_path.write_text(json.dumps({"mcpServers": config["groups"][group]["mcp"]}), encoding="utf-8")
        prompt = build_prompt(config, question)
        cmd = build_cmd(config, group, mcp_path, prompt)
        execution = execute(cmd, isolated_env(home, api_key), work, folder / "stream.jsonl",
                            folder / "stderr.txt", int(config["timeout_s"]))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    parsed = parse_stream(folder / "stream.jsonl")
    setup_error = None
    try:
        valid, invalid_reason = classify(parsed, execution)
    except SetupError as err:
        setup_error = err
        valid, invalid_reason = False, f"setup_error: {err}"
    cost, exact = run_cost(parsed, config)
    meta = {
        "question": question["id"], "group": group, "round": rnd, "attempt": attempt,
        "started_at": execution.started_at, "ended_at": execution.ended_at, "duration_s": execution.duration_s,
        "exit_code": execution.exit_code, "timed_out": execution.timed_out,
        "valid": valid, "invalid_reason": invalid_reason,
        "cost_usd": cost, "cost_exact": exact,
        "model": (parsed.init or {}).get("model"),
        "claude_code_version": (parsed.init or {}).get("claude_code_version"),
        "tools": (parsed.init or {}).get("tools"),
        "mcp_servers": (parsed.init or {}).get("mcp_servers"),
        "result_subtype": (parsed.result or {}).get("subtype"),
        "num_turns": (parsed.result or {}).get("num_turns"),
        "pickfit_calls": parsed.pickfit_calls,
        "pickfit_unavailable": pickfit_unavailable(parsed),
        # Only an attempt that counts can show a misconfigured group; an invalid one is retried (B2).
        "config_problems": config_problems(parsed, group, config) if valid else [],
        "usage": parsed.usage,
        "argv": [a if a != prompt else "<prompt>" for a in cmd],
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "answer.md").write_text(final_answer(parsed), encoding="utf-8")
    if setup_error is not None:
        raise setup_error
    return meta


def seal_interrupted(rnd: str, qid: str, group: str, config: dict[str, Any], base: Path | None = None) -> None:
    """An attempt folder with no meta.json is a runner crash (B2): record it as invalid, keep its log."""
    for folder in sorted(((base or RUNS) / rnd / qid / group).glob("attempt-*")):
        if (folder / "meta.json").exists():
            continue
        parsed = parse_stream(folder / "stream.jsonl")
        stat = folder.stat()
        born = dt.datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime), TAIPEI)
        meta = {
            "question": qid, "group": group, "round": rnd, "attempt": int(folder.name.split("-")[1]),
            "started_at": born.isoformat(timespec="seconds"), "ended_at": None, "valid": False,
            "invalid_reason": "runner_crash: interrupted before meta.json was written",
            "cost_usd": float(config["per_run_budget_usd"]), "cost_exact": False,
            "model": (parsed.init or {}).get("model"), "pickfit_calls": parsed.pickfit_calls,
            "config_problems": [], "usage": parsed.usage, "sealed_at": now(),
        }
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --- bookkeeping -----------------------------------------------------------------


def attempts(rnd: str, qid: str, group: str, base: Path | None = None) -> list[dict[str, Any]]:
    folder = (base or RUNS) / rnd / qid / group
    metas = []
    for meta_path in sorted(folder.glob("attempt-*/meta.json"), key=lambda p: int(p.parent.name.split("-")[1])):
        metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
    return metas


def next_attempt(rnd: str, qid: str, group: str, base: Path | None = None) -> int:
    folders = [int(p.name.split("-")[1]) for p in ((base or RUNS) / rnd / qid / group).glob("attempt-*")]
    return max(folders, default=0) + 1


def settled(metas: list[dict[str, Any]], config: dict[str, Any]) -> bool:
    """Done: a valid attempt, or every allowed attempt was invalid (recorded as not run)."""
    return any(m["valid"] for m in metas) or len(metas) >= 1 + int(config["invalid_retries"])


def all_metas(rounds: list[str], base: Path | None = None) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for rnd in rounds
            for p in ((base or RUNS) / rnd).glob("*/*/attempt-*/meta.json")]


def spent(rounds: list[str], base: Path | None = None) -> float:
    """B4 spend: exact costs, and the per-run cap for a run whose cost is unknown (conservative)."""
    return round(sum(float(m["cost_usd"]) for m in all_metas(rounds, base)), 4)


def expected_run_cost(rounds: list[str], config: dict[str, Any], base: Path | None = None) -> float:
    """Mean exact cost of the runs so far in these rounds; the per-run budget before any."""
    exact = [m["cost_usd"] for m in all_metas(rounds, base) if m["cost_exact"]]
    return sum(exact) / len(exact) if exact else float(config["per_run_budget_usd"])


def projected(rounds: list[str], slots_done: int, slots_total: int, config: dict[str, Any], base: Path | None = None) -> float:
    """B4 estimate: unknown-cost runs counted at the mean exact cost, not at the cap."""
    metas = all_metas(rounds, base)
    mean = expected_run_cost(rounds, config, base)
    estimate = sum(m["cost_usd"] if m["cost_exact"] else mean for m in metas)
    return estimate / max(slots_done, 1) * slots_total


def write_marker(name: str, payload: dict[str, Any], base: Path | None = None) -> None:
    path = (base or RUNS) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": now(), **payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Stop(Exception):
    """A pre-registered stop: cap, projection over cap, a misconfigured group, a setup error."""


class OverCap(Stop):
    """The next run would pass the cap."""


def run_one_slot(config, question, group, rnd, api_key, cap, rounds_for_cap, base=None, log=print) -> None:
    """Run one question-group slot until it is settled (B2 retries)."""
    seal_interrupted(rnd, question["id"], group, config, base)
    while not settled(attempts(rnd, question["id"], group, base), config):
        if spent(rounds_for_cap, base) + expected_run_cost(rounds_for_cap, config, base) > cap:
            raise OverCap(f"cap ${cap} would be exceeded before {rnd} {question['id']} {group}")
        try:
            meta = run_once(config, question, group, rnd, next_attempt(rnd, question["id"], group, base), api_key, base)
        except SetupError as err:
            raise Stop(f"setup error (not a run under B2; fix the key, account or balance, then rerun): {err}")
        log(f"{rnd} {question['id']} {group} attempt {meta['attempt']}: valid={meta['valid']} "
            f"cost=${meta['cost_usd']:.3f} {meta['invalid_reason'] or ''}")
        if meta["config_problems"]:
            write_marker(f"{rnd}-{group}-misconfigured", {"question": question["id"], "problems": meta["config_problems"]}, base)
            raise Stop(f"{group} misconfigured in {rnd} {question['id']}: {meta['config_problems']}. "
                       f"B2: that group's whole {rnd} is void; fix the cause, then `void --round {rnd} --group {group}` and rerun.")


def blocked_by_markers(rnd: str, base: Path | None = None) -> list[str]:
    return sorted(p.name for p in (base or RUNS).glob(f"{rnd}-*-misconfigured.json"))


def snapshot_problems() -> list[str] | None:
    path = RESULTS / "versions-before.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("problems", [])


def cmd_run1(args, config=None, questions=None, api_key=None, base=None, log=print) -> int:
    config = config or load_config()
    questions = questions or load_questions()
    if base is None:
        problems = snapshot_problems()
        if problems is None:
            log("versions-before.json is missing: run `snapshot --label before` first (A3).")
            return 2
        if problems:
            log(f"versions-before.json lists problems; fix them and take the snapshot again: {problems}")
            return 2
    blocked = blocked_by_markers("run1", base)
    if blocked:
        log(f"a group is misconfigured ({blocked}); void its run first (B2).")
        return 2
    api_key = api_key or read_api_key()
    cap = float(config["caps_usd"]["run1"])
    estimate = list(config["estimate_questions"])
    total_slots = len(questions) * len(GROUPS)
    rules_only_cut = ((base or RUNS) / "run1-rules-only-cut.json").exists()
    try:
        for question in questions:
            for group in run1_order(question["id"]):
                if group == "rules_only" and rules_only_cut:
                    continue
                try:
                    run_one_slot(config, question, group, "run1", api_key, cap, ["run1"], base, log)
                except OverCap:
                    if group == "rules_only" or rules_only_cut:
                        raise
                    # G: cut rules-only (item 6) before the primary groups (item 1).
                    rules_only_cut = True
                    write_marker("run1-rules-only-cut", {"from_question": question["id"],
                                                         "reason": "cap pressure; G cuts rules-only first"}, base)
                    log(f"cap pressure at {question['id']}: rules-only cut from here (G)")
                    run_one_slot(config, question, group, "run1", api_key, cap, ["run1"], base, log)
            if question["id"] == estimate[-1]:
                done = len(estimate) * len(GROUPS)
                projection = projected(["run1"], done, total_slots, config, base)
                write_marker("run1-estimate", {"spent_usd": spent(["run1"], base), "projected_usd": round(projection, 2), "cap_usd": cap}, base)
                log(f"estimate after {', '.join(estimate)}: projected run 1 ${projection:.2f} (cap ${cap})")
                if projection > cap:
                    raise Stop(f"projected ${projection:.2f} > cap ${cap}: B4 requires a 9.2 section with a new cap, "
                               f"committed before the next question; then raise caps_usd.run1 and rerun this command")
    except Stop as stop:
        log(f"stopped: {stop}")
        write_marker("run1-stopped", {"reason": str(stop)}, base)
        return 1
    starts = [dt.datetime.fromisoformat(m["started_at"]) for m in all_metas(["run1"], base) if m.get("started_at")]
    ends = [dt.datetime.fromisoformat(m["ended_at"]) for m in all_metas(["run1"], base) if m.get("ended_at")]
    within = bool(starts and ends) and max(ends) - min(starts) <= dt.timedelta(hours=24)
    write_marker("run1-complete", {"spent_usd": spent(["run1"], base), "within_24_hours": within,
                                   "first_start": min(starts).isoformat() if starts else None,
                                   "last_end": max(ends).isoformat() if ends else None}, base)
    log(f"run 1 complete: ${spent(['run1'], base):.2f}" + ("" if within else "; NOT within 24 hours (section 4): report it"))
    return 0


def cmd_void(args, base=None, log=print) -> int:
    """B2: a misconfigured group's whole round is void; keep it aside (reported), then rerun."""
    root = base or RUNS
    marker = root / f"{args.round}-{args.group}-misconfigured.json"
    stamp = dt.datetime.now(TAIPEI).strftime("%Y%m%d-%H%M%S")
    target = root / "voided" / f"{args.round}-{args.group}-{stamp}"
    moved = 0
    for folder in sorted((root / args.round).glob(f"*/{args.group}")):
        dest = target / folder.parent.name / args.group
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder), str(dest))
        moved += 1
    if marker.exists():
        shutil.move(str(marker), str(target / marker.name))
    write_marker(f"voided-{args.round}-{args.group}-{stamp}", {"questions_moved": moved, "to": str(target)}, base)
    log(f"voided {moved} question(s) of {args.round} {args.group} -> {target}")
    return 0


def first_start(base: Path | None = None) -> dt.datetime:
    metas = [m for g in GROUPS for m in attempts("run1", "q01", g, base) if m.get("started_at")]
    if not metas:
        raise Stop("run 1 has not started")
    return min(dt.datetime.fromisoformat(m["started_at"]) for m in metas)


def plan_reruns(config: dict[str, Any], base: Path | None = None) -> list[int]:
    """B4: estimate from run 1's control and experimental costs; run 2 only, or 2 and 3."""
    metas = [m for m in all_metas(["run1"], base) if m["group"] in ("control", "experimental") and m["valid"] and m["cost_exact"]]
    per_run = sum(m["cost_usd"] for m in metas) / len(metas) if metas else float(config["per_run_budget_usd"])
    questions = len({p.name for p in ((base or RUNS) / "run1").iterdir() if p.is_dir()})
    cap = float(config["caps_usd"]["reruns"])
    return [2, 3] if per_run * questions * 4 <= cap else [2]


def cmd_reruns(args, config=None, questions=None, api_key=None, base=None, clock=None, log=print) -> int:
    config = config or load_config()
    questions = questions or load_questions()
    if not ((base or RUNS) / "run1-complete.json").exists():
        log("run 1 is not complete; B3 reruns start after every group's run 1.")
        return 2
    for rnd in ("run2", "run3"):
        if blocked_by_markers(rnd, base):
            log(f"a group is misconfigured in {rnd}; void it first (B2).")
            return 2
    api_key = api_key or read_api_key()
    clock = clock or (lambda: dt.datetime.now(TAIPEI))
    deadline = first_start(base) + dt.timedelta(hours=float(config["rerun_window_hours"]))
    cap = float(config["caps_usd"]["reruns"])
    rounds = plan_reruns(config, base)
    log(f"reruns: rounds {rounds}, cap ${cap}, deadline {deadline.isoformat()}")
    for question in questions:
        try:
            for group, number in rerun_order(rounds):
                if clock() >= deadline:
                    raise Stop(f"24-hour window ended ({deadline.isoformat()})")
                run_one_slot(config, question, group, round_name(number), api_key, cap, ["run2", "run3"], base, log)
            if clock() >= deadline:
                # B3: the window ended while this question was running, so it is not run for both groups.
                raise Stop(f"24-hour window ended during {question['id']} ({deadline.isoformat()})")
        except Stop as stop:
            write_marker("reruns-stopped", {"reason": str(stop), "question": question["id"],
                                             "not_run": [question["id"]], "rounds": rounds}, base)
            log(f"stopped at {question['id']}: {stop}")
            return 1
    write_marker("reruns-complete", {"spent_usd": spent(["run2", "run3"], base), "rounds": rounds}, base)
    return 0


def cmd_check(args, config=None, base=None, log=print) -> int:
    """B2: every counted attempt's Claude Code version, model and tool list, per group."""
    config = config or load_config()
    root = (base or RUNS) / args.round
    bad = 0
    for meta_path in sorted(root.glob("*/*/attempt-*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta["valid"]:
            continue  # an invalid attempt is retried, never scored
        parsed = parse_stream(meta_path.parent / "stream.jsonl")
        problems = config_problems(parsed, meta["group"], config)
        if problems:
            bad += 1
            log(f"{meta['question']} {meta['group']} attempt {meta['attempt']}: {problems}")
    log(f"{args.round}: {bad} counted attempt(s) with configuration problems")
    return 1 if bad else 0


def cmd_status(args, base=None, log=print) -> int:
    root = base or RUNS
    for rnd in ("run1", "run2", "run3"):
        if not (root / rnd).exists():
            continue
        slots = [(q.name, g.name, attempts(rnd, q.name, g.name, base)) for q in sorted((root / rnd).iterdir()) if q.is_dir()
                 for g in sorted(q.iterdir()) if g.is_dir()]
        valid = sum(1 for _, _, metas in slots if any(m["valid"] for m in metas))
        log(f"{rnd}: {valid} valid slot(s) of {len(slots)}, spent ${spent([rnd], base):.2f}")
    return 0


# --- A3 version record -----------------------------------------------------------


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(folder: Path, pattern: str) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.glob(pattern)):
        digest.update(f"{path.relative_to(folder)}\0{sha256_file(path)}\n".encode())
    return digest.hexdigest()


def served_data_sha256(data_dir: Path) -> str:
    """The digest the Worker serves as data_sha256 (pickfit/index.py load_records)."""
    digest = hashlib.sha256()
    for path in sorted(data_dir.glob("*.json")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def deployment_status(spec: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"env": spec["env"], "host": spec["host"]}
    try:
        with urllib.request.urlopen(f"https://{spec['host']}/", timeout=20) as response:
            record["root"] = json.loads(response.read().decode("utf-8"))
    except Exception as err:  # recorded, not fatal: the record shows what could not be read
        record["root_error"] = repr(err)
    try:
        out = subprocess.run(["npx", "wrangler", "deployments", "list", "--env", spec["env"], "--json"],
                             cwd=ROOT / "worker", capture_output=True, text=True, timeout=120)
        deployments = json.loads(out.stdout) if out.returncode == 0 else None
        record["latest_deployment"] = deployments[-1] if deployments else None
        if out.returncode != 0:
            record["wrangler_error"] = out.stderr[-500:]
    except Exception as err:
        record["wrangler_error"] = repr(err)
    root = record.get("root") or {}
    expect = spec.get("expect") or {}
    record["matches_expectation"] = all(root.get(k) == v for k, v in expect.items()) if root else False
    return record


def snapshot_record(label: str, config: dict[str, Any]) -> dict[str, Any]:
    claude = os.path.expanduser(config["claude_bin"])
    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()
    funnel = subprocess.run(["uv", "run", "pickfit", "funnel"], cwd=ROOT, capture_output=True, text=True)
    data_dir = ROOT / "data" / "software"
    return {
        "label": label,
        "at": now(),
        "git_head": git("rev-parse", "HEAD"),
        "git_dirty": [line for line in git("status", "--porcelain").splitlines() if line],
        "data_software_sha256": tree_sha256(data_dir, "*.json"),
        "served_data_sha256": served_data_sha256(data_dir),
        "data_software_files": len(list(data_dir.glob("*.json"))),
        "pipeline_db_sha256": sha256_file(ROOT / "runs" / "pipeline.db"),
        "funnel_sha256": hashlib.sha256(funnel.stdout.encode()).hexdigest() if funnel.returncode == 0 else None,
        "funnel": json.loads(funnel.stdout) if funnel.returncode == 0 else {"error": funnel.stderr[-500:]},
        "evidence_manifest_sha256": sha256_file(RESULTS / "evidence-manifest.json"),
        "deployments": {group: deployment_status(spec) for group, spec in config["deployments"].items()},
        "claude_code_version": version,
        "model": config["model"],
        "config_sha256": sha256_file(CONFIG_PATH),
        "questions_sha256": sha256_file(EVAL / "questions.yaml"),
    }


def record_problems(record: dict[str, Any], config: dict[str, Any]) -> list[str]:
    problems = []
    if record["git_dirty"]:
        problems.append(f"uncommitted changes: {record['git_dirty'][:5]}")
    if not record["claude_code_version"].startswith(config["claude_code_version"]):
        problems.append(f"claude {record['claude_code_version']} != {config['claude_code_version']}")
    served = {}
    for group, dep in record["deployments"].items():
        root = dep.get("root") or {}
        if not dep.get("matches_expectation"):
            problems.append(f"{group} deployment does not match {config['deployments'][group]['expect']}")
        served[group] = root.get("data_sha256")
        if served[group] != record["served_data_sha256"]:
            problems.append(f"{group} deployment serves data {served[group]} but the repo data is {record['served_data_sha256']} (A1)")
    if len(set(served.values())) > 1:
        problems.append(f"the two deployments serve different data: {served} (A1)")
    if record["evidence_manifest_sha256"] is None:
        problems.append("no evidence manifest: run collect_evidence.py first (D5 needs the raw sandbox records)")
    return problems


def cmd_snapshot(args, log=print) -> int:
    config = load_config()
    record = snapshot_record(args.label, config)
    record["problems"] = record_problems(record, config)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"versions-{args.label}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"wrote {path.relative_to(ROOT)}")
    for problem in record["problems"]:
        log(f"problem: {problem}")
    return 1 if record["problems"] else 0


COMPARED = ("git_head", "data_software_sha256", "served_data_sha256", "pipeline_db_sha256", "funnel_sha256",
            "evidence_manifest_sha256", "claude_code_version", "model", "config_sha256", "questions_sha256")


def compare_records(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """A3: anything that differs between the before and after records."""
    diffs = [f"{key}: {before.get(key)} -> {after.get(key)}" for key in COMPARED if before.get(key) != after.get(key)]
    for group in sorted(set(before.get("deployments", {})) | set(after.get("deployments", {}))):
        b, a = before["deployments"].get(group, {}), after["deployments"].get(group, {})
        for key in ("data_sha256", "tools", "match_mode"):
            if (b.get("root") or {}).get(key) != (a.get("root") or {}).get(key):
                diffs.append(f"{group}.{key}: {(b.get('root') or {}).get(key)} -> {(a.get('root') or {}).get(key)}")
        b_id = (b.get("latest_deployment") or {}).get("id")
        a_id = (a.get("latest_deployment") or {}).get("id")
        if b_id != a_id:
            diffs.append(f"{group}.deployment: {b_id} -> {a_id}")
    return diffs


def cmd_compare(args, log=print) -> int:
    before = json.loads((RESULTS / "versions-before.json").read_text(encoding="utf-8"))
    after = json.loads((RESULTS / "versions-after.json").read_text(encoding="utf-8"))
    diffs = compare_records(before, after)
    (RESULTS / "versions-compare.json").write_text(json.dumps({"at": now(), "differences": diffs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for diff in diffs:
        log(f"differs: {diff}")
    log("A3: before and after match" if not diffs else
        "A3: they differ; every run after the change is void and is rerun from the original snapshot (B2)")
    return 1 if diffs else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/run.py")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--label", required=True, choices=["before", "after"])
    sub.add_parser("compare")
    sub.add_parser("run1")
    sub.add_parser("reruns")
    c = sub.add_parser("check")
    c.add_argument("--round", required=True, choices=["run1", "run2", "run3"])
    v = sub.add_parser("void")
    v.add_argument("--round", required=True, choices=["run1", "run2", "run3"])
    v.add_argument("--group", required=True, choices=list(GROUPS))
    sub.add_parser("status")
    args = parser.parse_args(argv)
    handlers = {"snapshot": cmd_snapshot, "compare": cmd_compare, "run1": cmd_run1, "reruns": cmd_reruns,
                "check": cmd_check, "void": cmd_void, "status": cmd_status}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
