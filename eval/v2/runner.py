"""pickfit eval v2 runner: the same tasks with and without pickfit (brief 15.8, P2-10).

    uv run python eval/v2/runner.py --dry-run          # free: validate tasks, print the plan and estimate
    uv run python eval/v2/runner.py --execute --group control --box-cmd "<prefix>" --run run1

--dry-run never calls a model, never opens a sandbox and never reads .env.
--execute refuses until the task set is frozen, every fixture has a sha256, the Claude Code
version is pinned, and ANTHROPIC_API_KEY is in the environment (the operator exports it; this
file does not look for key files). The sandbox is reached only through --box-cmd, a command
prefix such as `docker exec -i <box>`; the runner does not depend on any one provider.

Each record carries the fields score.py needs: first_try_working, tokens_in, tokens_out,
cost_usd, elapsed_s, decision_honest (see RECORD_FIELDS).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks.json"
CONFIG = HERE / "config.json"
RESULTS = HERE / "results"

TRACKS = {"A", "B", "C", "H"}
KINDS = {
    "A": {"find_and_use"},
    "B": {"web_for_human"},
    "C": {"human_agent_creative"},
    "H": {"build_it_yourself", "builtin_enough"},
}
USERS = {"agent", "human"}
LANGUAGES = {"en", "zh-TW"}
DIFFICULTIES = {"easy", "medium", "hard"}
CHECK_KINDS = {"shell", "web_probe"}
GROUPS = ("control", "treatment")

RECORD_FIELDS = {
    "task_id": str,
    "group": str,
    "track": str,
    "kind": str,
    "honesty_trap": bool,
    "valid": bool,
    "first_try_working": (bool, type(None)),
    "tokens_in": int,
    "tokens_out": int,
    "cost_usd": (int, float),
    "elapsed_s": (int, float),
    "decision": (str, type(None)),
    "decision_honest": (bool, type(None)),
}

INSTALL_PATTERNS = [
    r"\bapt(-get)?\s+(-\S+\s+)*install\b",
    r"\bpip3?\s+install\b",
    r"\buv\s+(pip\s+install|tool\s+install|add)\b",
    r"\bpipx\s+install\b",
    r"\bnpm\s+(i|install)\b",
    r"\bnpx\s+",
    r"\bpnpm\s+(add|install|dlx)\b",
    r"\bcargo\s+install\b",
    r"\bgo\s+install\b",
    r"\bbrew\s+install\b",
    r"\bsnap\s+install\b",
    r"\bdocker\s+(run|pull)\b",
    r"curl[^|]*\|\s*(sudo\s+)?(ba)?sh\b",
    r"wget[^|]*\|\s*(sudo\s+)?(ba)?sh\b",
]
DECISION_RE = re.compile(r"^\s*DECISION:\s*([a-z_]+)\s*$", re.MULTILINE)
TOOL_RE = re.compile(r"^\s*TOOL:\s*(.+?)\s*$", re.MULTILINE)
URL_RE = re.compile(r"^\s*URL:\s*(\S+)\s*$", re.MULTILINE)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- task set


def validate_tasks(doc: dict[str, Any]) -> list[str]:
    """Return every problem in the task set; empty means it is well formed."""
    problems: list[str] = []
    decisions = set(doc.get("decisions") or [])
    if not decisions:
        problems.append("top-level 'decisions' missing")
    tasks = doc.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return problems + ["'tasks' must be a non-empty list"]
    if not 18 <= len(tasks) <= 20:
        problems.append(f"expected 18-20 tasks, found {len(tasks)}")
    seen: set[str] = set()
    for i, task in enumerate(tasks):
        where = task.get("id") or f"tasks[{i}]"
        for key in ("id", "track", "kind", "user_of_result", "language", "difficulty", "prompt",
                    "acceptable_decisions", "fixtures", "check"):
            if key not in task:
                problems.append(f"{where}: missing '{key}'")
        if "id" in task:
            if not re.fullmatch(r"v2-[abch]\d{2}", task["id"]):
                problems.append(f"{where}: id must look like v2-a01")
            elif task["id"][3].upper() != task.get("track"):
                problems.append(f"{where}: id letter does not match track")
            if task["id"] in seen:
                problems.append(f"{where}: duplicate id")
            seen.add(task["id"])
        track = task.get("track")
        if track not in TRACKS:
            problems.append(f"{where}: unknown track {track!r}")
        elif task.get("kind") not in KINDS[track]:
            problems.append(f"{where}: kind {task.get('kind')!r} not allowed on track {track}")
        if task.get("user_of_result") not in USERS:
            problems.append(f"{where}: user_of_result must be agent or human")
        if task.get("language") not in LANGUAGES:
            problems.append(f"{where}: unknown language {task.get('language')!r}")
        if task.get("difficulty") not in DIFFICULTIES:
            problems.append(f"{where}: unknown difficulty {task.get('difficulty')!r}")
        if not str(task.get("prompt", "")).strip():
            problems.append(f"{where}: empty prompt")
        acceptable = task.get("acceptable_decisions") or []
        if not acceptable or not set(acceptable) <= decisions:
            problems.append(f"{where}: acceptable_decisions must be a non-empty subset of decisions")
        trap = bool(task.get("honesty_trap"))
        if track == "H":
            if not trap:
                problems.append(f"{where}: track H tasks must set honesty_trap")
            if "use_existing" in acceptable:
                problems.append(f"{where}: honesty task cannot accept use_existing")
        elif trap:
            problems.append(f"{where}: honesty_trap only belongs on track H")
        for fx in task.get("fixtures") or []:
            if not fx.get("path") or not fx.get("make"):
                problems.append(f"{where}: fixture needs path and make")
            if str(fx.get("path", "")).startswith(("/", "..")):
                problems.append(f"{where}: fixture path must be relative to /work")
        check = task.get("check") or {}
        kind = check.get("kind")
        if kind not in CHECK_KINDS:
            problems.append(f"{where}: check.kind must be one of {sorted(CHECK_KINDS)}")
        elif kind == "shell" and not str(check.get("script", "")).strip():
            problems.append(f"{where}: shell check needs a script")
        elif kind == "web_probe":
            if not check.get("steps") or not check.get("viewport"):
                problems.append(f"{where}: web_probe needs steps and viewport")
        if track == "B" and kind != "web_probe":
            problems.append(f"{where}: track B is checked by web_probe")
        if track == "C" and not check.get("gui_spot"):
            problems.append(f"{where}: track C needs a gui_spot check")
        # Tasks describe needs, never the answer.
        for banned in ("expected_tool", "answer", "expected_answer"):
            if banned in task:
                problems.append(f"{where}: tasks must not carry '{banned}'")
    return problems


def distribution(tasks: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"track": {}, "kind": {}, "language": {}, "user_of_result": {},
                                      "difficulty": {}}
    for task in tasks:
        for key in out:
            value = task.get(key, "?")
            out[key][value] = out[key].get(value, 0) + 1
    return out


def fixture_readiness(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Fixtures without a sha256 are only planned; paid runs need all of them frozen."""
    pending: dict[str, list[str]] = {}
    for task in tasks:
        missing = [fx["path"] for fx in task.get("fixtures") or [] if not fx.get("sha256")]
        if missing:
            pending[task["id"]] = missing
    return pending


def slot_order(task_id: str) -> list[str]:
    """Which group runs first for a task: fixed by a hash so neither group always goes first."""
    first = int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % 2
    return list(GROUPS) if first == 0 else list(reversed(GROUPS))


def plan(tasks: list[dict[str, Any]], groups: list[str], runs: int = 1) -> list[dict[str, Any]]:
    slots = []
    for task in tasks:
        for group in slot_order(task["id"]):
            if group in groups:
                for attempt in range(1, runs + 1):
                    slots.append({"task_id": task["id"], "group": group, "run": attempt})
    return slots


def token_cost(usage: dict[str, int], prices: dict[str, float]) -> float:
    per = 1_000_000
    return (usage.get("input_tokens", 0) * prices["input"]
            + usage.get("output_tokens", 0) * prices["output"]
            + usage.get("cache_read_input_tokens", 0) * prices["cache_read"]
            + usage.get("cache_creation_input_tokens", 0) * prices["cache_write"]) / per


def estimate(config: dict[str, Any], slots: int) -> float:
    guess = config["dry_run_estimate_tokens"]
    usage = {"input_tokens": guess["input"], "output_tokens": guess["output"],
             "cache_read_input_tokens": guess.get("cache_read", 0)}
    return round(token_cost(usage, config["price_per_mtok_usd"]) * slots, 2)


# ---------------------------------------------------------------- one run


def build_prompt(config: dict[str, Any], task: dict[str, Any]) -> str:
    return f"{config['preamble']}\n\n---\n\n{task['prompt']}"


def mcp_config(config: dict[str, Any], group: str) -> dict[str, Any]:
    return {"mcpServers": config["groups"][group]["mcp"]}


def build_cmd(config: dict[str, Any], group: str, mcp_path: str, prompt: str) -> list[str]:
    g = config["groups"][group]
    tools = list(g["tools"]) + list(g["expected_mcp_tools"])
    return [
        config["claude_bin"], "-p", prompt,
        "--model", config["model"],
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--mcp-config", mcp_path,
        "--allowedTools", ",".join(tools),
        "--permission-mode", "bypassPermissions",
        "--max-budget-usd", str(config["per_run_budget_usd"]),
    ]


@dataclass
class Parsed:
    usage: dict[str, int] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    text: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    bash_commands: list[str] = field(default_factory=list)
    mcp_tools_seen: list[str] = field(default_factory=list)
    bad_lines: int = 0


def parse_stream(lines: list[str]) -> Parsed:
    """Read Claude Code stream-json output (one JSON object per line)."""
    parsed = Parsed()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parsed.bad_lines += 1
            continue
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            parsed.mcp_tools_seen = [t for t in event.get("tools", []) if str(t).startswith("mcp__")]
        elif etype == "assistant":
            message = event.get("message") or {}
            for key, value in (message.get("usage") or {}).items():
                if isinstance(value, int):
                    parsed.usage[key] = parsed.usage.get(key, 0) + value
            for block in message.get("content") or []:
                if block.get("type") == "text":
                    parsed.text.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    parsed.tool_calls.append(name)
                    if name == "Bash":
                        parsed.bash_commands.append(str((block.get("input") or {}).get("command", "")))
        elif etype == "result":
            parsed.result = event
    return parsed


def final_text(parsed: Parsed) -> str:
    if parsed.result and isinstance(parsed.result.get("result"), str):
        return parsed.result["result"]
    return parsed.text[-1] if parsed.text else ""


def parse_decision(text: str) -> dict[str, str | None]:
    def last(regex: re.Pattern[str]) -> str | None:
        found = regex.findall(text)
        if not found:
            return None
        value = found[-1].strip()
        return None if value.lower() == "none" else value

    return {"decision": last(DECISION_RE), "tool": last(TOOL_RE), "url": last(URL_RE)}


def detect_installs(commands: list[str]) -> list[str]:
    hits = []
    for command in commands:
        if any(re.search(p, command) for p in INSTALL_PATTERNS):
            hits.append(command.strip()[:200])
    return hits


def usage_totals(parsed: Parsed) -> tuple[int, int]:
    usage = dict(parsed.usage)
    if parsed.result and isinstance(parsed.result.get("usage"), dict):
        usage = parsed.result["usage"]  # the result event carries the run total when present
    tokens_in = sum(int(usage.get(k, 0) or 0) for k in
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return tokens_in, int(usage.get("output_tokens", 0) or 0)


def run_cost(parsed: Parsed, config: dict[str, Any]) -> float:
    if parsed.result and parsed.result.get("total_cost_usd") is not None:
        return float(parsed.result["total_cost_usd"])
    return token_cost(parsed.usage, config["price_per_mtok_usd"])


def judge_decision(task: dict[str, Any], decision: str | None, installs: list[str]) -> bool | None:
    """True when the agent made an acceptable call; honesty tasks also fail on any install."""
    if decision is None:
        return False
    honest = decision in task["acceptable_decisions"]
    if task.get("honesty_trap") and installs:
        honest = False
    return honest


def make_record(task: dict[str, Any], group: str, parsed: Parsed, elapsed_s: float,
                check_passed: bool | None, config: dict[str, Any], invalid_reason: str | None = None,
                check_detail: str = "") -> dict[str, Any]:
    text = final_text(parsed)
    picked = parse_decision(text)
    installs = detect_installs(parsed.bash_commands)
    tokens_in, tokens_out = usage_totals(parsed)
    valid = invalid_reason is None
    expected_mcp = set(config["groups"][group]["expected_mcp_tools"])
    pickfit_calls = [t for t in parsed.tool_calls if t.startswith("mcp__pickfit__")]
    if valid and expected_mcp and not expected_mcp & set(parsed.mcp_tools_seen):
        valid, invalid_reason = False, "pickfit MCP tools not loaded"
    if valid and group == "control" and pickfit_calls:
        valid, invalid_reason = False, "control group reached pickfit"
    return {
        "task_id": task["id"],
        "group": group,
        "track": task["track"],
        "kind": task["kind"],
        "honesty_trap": bool(task.get("honesty_trap")),
        "valid": valid,
        "invalid_reason": invalid_reason,
        "first_try_working": (bool(check_passed) if check_passed is not None else None) if valid else None,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(run_cost(parsed, config), 6),
        "elapsed_s": round(float(elapsed_s), 1),
        "decision": picked["decision"],
        "tool": picked["tool"],
        "url": picked["url"],
        "decision_honest": judge_decision(task, picked["decision"], installs) if valid else None,
        "installs": installs,
        "pickfit_calls": len(pickfit_calls),
        "tool_calls": len(parsed.tool_calls),
        "check_detail": check_detail[:2000],
    }


def validate_record(record: dict[str, Any]) -> list[str]:
    problems = []
    for key, typ in RECORD_FIELDS.items():
        if key not in record:
            problems.append(f"missing {key}")
        elif not isinstance(record[key], typ) or (typ is int and isinstance(record[key], bool)):
            problems.append(f"{key} has type {type(record[key]).__name__}")
    if record.get("group") not in GROUPS:
        problems.append("group must be control or treatment")
    return problems


# ---------------------------------------------------------------- execution (paid)


def execute_blockers(doc: dict[str, Any], config: dict[str, Any]) -> list[str]:
    blockers = []
    if not doc.get("frozen_at"):
        blockers.append("tasks.json is not frozen (frozen_at is null)")
    pending = fixture_readiness(doc["tasks"])
    if pending:
        blockers.append(f"{len(pending)} tasks have fixtures without sha256")
    if config.get("claude_code_version", "").startswith("pin"):
        blockers.append("claude_code_version is not pinned in config.json")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        blockers.append("ANTHROPIC_API_KEY is not exported by the operator")
    return blockers


def run_check(task: dict[str, Any], box: list[str], config: dict[str, Any]) -> tuple[bool, str]:
    verify = config["sandbox"]["verify_dir"]
    check = task["check"]
    if check["kind"] == "shell":
        script = check["script"]
    else:
        script = f"verify-web --task {shlex.quote(task['id'])} --url-from /work/.eval/answer.txt"
    shell = f"export PATH={verify}/bin:$PATH; cd {config['sandbox']['workdir']} && {script}"
    proc = subprocess.run(box + ["bash", "-lc", shell], capture_output=True, text=True, timeout=900)
    return proc.returncode == 0, (proc.stdout + proc.stderr)


def run_one(task: dict[str, Any], group: str, config: dict[str, Any], box: list[str]) -> dict[str, Any]:
    prompt = build_prompt(config, task)
    with tempfile.TemporaryDirectory() as tmp:
        mcp_path = Path(tmp) / "mcp.json"
        mcp_path.write_text(json.dumps(mcp_config(config, group)))
        box_mcp = "/work/.eval/mcp.json"
        subprocess.run(box + ["bash", "-lc", f"mkdir -p /work/.eval && cat > {box_mcp}"],
                       input=mcp_path.read_text(), text=True, check=True)
    cmd = box + build_cmd(config, group, box_mcp, prompt)
    started = time.monotonic()
    invalid = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=config["timeout_s"])
        lines = proc.stdout.splitlines()
        if proc.returncode != 0 and not lines:
            invalid = f"claude exited {proc.returncode}: {proc.stderr[-300:]}"
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        lines = (out.decode() if isinstance(out, bytes) else out).splitlines()
        invalid = None  # a timeout is the agent's failure, not an infrastructure one
    elapsed = time.monotonic() - started
    parsed = parse_stream(lines)
    answer = parse_decision(final_text(parsed))
    if answer["url"]:
        subprocess.run(box + ["bash", "-lc", "cat > /work/.eval/answer.txt"], input=answer["url"], text=True)
    passed, detail = (None, "") if invalid else run_check(task, box, config)
    return make_record(task, group, parsed, elapsed, passed, config, invalid, detail)


# ---------------------------------------------------------------- CLI


def cmd_dry_run(doc: dict[str, Any], config: dict[str, Any], groups: list[str], log=print) -> int:
    problems = validate_tasks(doc)
    for name in groups:
        if name not in config["groups"]:
            problems.append(f"config.json has no group {name!r}")
    if problems:
        log("Task set problems:")
        for p in problems:
            log(f"  - {p}")
        return 1
    tasks = doc["tasks"]
    slots = plan(tasks, groups, config.get("runs_per_task", 1))
    dist = distribution(tasks)
    log(f"pickfit eval v2 dry run: {len(tasks)} tasks, groups {', '.join(groups)}, {len(slots)} slots")
    for key, counts in dist.items():
        log(f"  {key}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    log(f"  honesty traps: {sum(1 for t in tasks if t.get('honesty_trap'))}")
    guess = config["dry_run_estimate_tokens"]
    spend = estimate(config, len(slots))
    log(f"  estimated model spend: ~${spend} (guess per slot: {guess['input']:,} in, "
        f"{guess.get('cache_read', 0):,} cache read, {guess['output']:,} out; cap ${config['caps_usd']['run1']})")
    if spend > config["caps_usd"]["run1"]:
        log("  warning: the estimate is above the run1 cap; run the estimate tasks first")
    log("  record fields: " + ", ".join(RECORD_FIELDS))
    log("Plan (order fixed per task):")
    for slot in slots:
        log(f"  {slot['task_id']:7} {slot['group']:9} run {slot['run']}")
    pending = fixture_readiness(tasks)
    blockers = [b for b in execute_blockers(doc, config) if "ANTHROPIC_API_KEY" not in b]
    log(f"Fixtures planned but not frozen: {sum(len(v) for v in pending.values())} in {len(pending)} tasks")
    if blockers:
        log("Paid run would be blocked by:")
        for b in blockers:
            log(f"  - {b}")
    log("Dry run OK: nothing was called, nothing was written.")
    return 0


def run_spent(out_dir: Path) -> float:
    """Spend so far across every group file of this run; the cap covers both groups."""
    total = 0.0
    for path in out_dir.glob("*.json"):
        total += sum(r.get("cost_usd", 0) for r in load_json(path).get("records", []))
    return total


def cmd_execute(args, doc, config, log=print) -> int:
    blockers = execute_blockers(doc, config)
    if blockers:
        for b in blockers:
            log(f"blocked: {b}")
        return 2
    if not args.box_cmd:
        log("blocked: --box-cmd is required")
        return 2
    box = shlex.split(args.box_cmd)
    tasks = [t for t in doc["tasks"] if not args.task or t["id"] in args.task]
    out_dir = RESULTS / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.group}.json"
    result = load_json(out_path) if out_path.exists() else {
        "group": args.group, "meta": {"started_at": now(), "model": config["model"],
                                      "claude_code_version": config["claude_code_version"]},
        "records": []}
    done = {r["task_id"] for r in result["records"]}
    spent = run_spent(out_dir)
    for task in tasks:
        if task["id"] in done:
            continue
        if spent + config["per_run_budget_usd"] > config["caps_usd"]["run1"]:
            log(f"stop: next run could pass the ${config['caps_usd']['run1']} cap")
            break
        record = run_one(task, args.group, config, box)
        result["records"].append(record)
        spent += record["cost_usd"]
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        log(f"{task['id']} {args.group}: first_try={record['first_try_working']} ${record['cost_usd']:.2f}")
    result["meta"]["ended_at"] = now()
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate and print the plan; free")
    mode.add_argument("--execute", action="store_true", help="paid run inside a sandbox")
    parser.add_argument("--group", choices=GROUPS, help="group for --execute")
    parser.add_argument("--task", action="append", help="limit --execute to these task ids")
    parser.add_argument("--box-cmd", help="command prefix that runs a command inside the sandbox")
    parser.add_argument("--run", default="run1", help="results subfolder for --execute")
    parser.add_argument("--tasks", type=Path, default=TASKS)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args(argv)
    doc, config = load_json(args.tasks), load_json(args.config)
    if args.dry_run:
        return cmd_dry_run(doc, config, [args.group] if args.group else list(GROUPS))
    if not args.group:
        parser.error("--execute needs --group")
    return cmd_execute(args, doc, config)


if __name__ == "__main__":
    sys.exit(main())
