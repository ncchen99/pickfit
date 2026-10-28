"""Render one verification run as a static HTML page for the demo video (P5.4).

Usage:
    uv run python scripts/run_page.py verify-mcp-audit-20261029-011619-86aa
    uv run python scripts/run_page.py <run_id> --runs ../<worktree>/runs --out page.html

Reads runs/verify/<run_id>/ (report.json, replay.json, judge.json, outcome.json,
verification_run.json and the redrawn screenshots) and the run's lines in
runs/traces/*.jsonl (one per model call: stage, model, tokens, cost, latency). Writes
one self-contained file, screenshots inlined, to runs/pages/<run_id>.html by default.
runs/ is not in git and the page is not published anywhere.

In the browser, arrow keys, space or j/k step through the sections (for recording).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS = REPO_ROOT / "runs"
OUTPUT_LINES = 24
OUTPUT_CHARS = 2_400
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# --- loading ----------------------------------------------------------------------------------


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def trace_calls(traces_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Every traced model call of this run (the ok or cached attempt of each), in time order."""
    calls = []
    for path in sorted(traces_dir.glob("*.jsonl")):
        if path.name.startswith("github-"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if run_id not in line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("run_id") == run_id:
                calls.append(record)
    return sorted(calls, key=lambda c: c.get("ts") or "")


def load_run(runs_dir: Path, run_id: str) -> dict[str, Any]:
    run_dir = runs_dir / "verify" / run_id
    report = _json(run_dir / "report.json")
    if report is None:
        raise SystemExit(f"run_page: no report.json in {run_dir}")
    return {
        "run_id": run_id,
        "dir": run_dir,
        "report": report,
        "replay": _json(run_dir / "replay.json"),
        "judge": _json(run_dir / "judge.json"),
        "outcome": _json(run_dir / "outcome.json") or {},
        "run": _json(run_dir / "verification_run.json"),
        "calls": trace_calls(runs_dir / "traces", run_id),
    }


# --- small helpers ----------------------------------------------------------------------------


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def usd(value: float | None) -> str:
    if value is None:
        return "–"
    return f"${value:.4f}" if value < 0.1 else f"${value:.3f}"


def secs(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:.1f} s" if value < 120 else f"{value / 60:.1f} min"


def tokens(n: int | None) -> str:
    return "–" if n is None else f"{n:,}"


def tail(text: str | None, lines: int = OUTPUT_LINES, chars: int = OUTPUT_CHARS) -> str:
    text = _ANSI.sub("", text or "").rstrip()
    kept = text.splitlines()[-lines:]
    out = "\n".join(kept)[-chars:]
    return ("…\n" if len(out) < len(text) else "") + out


def exit_badge(code: int | None, expected: int | None = 0) -> str:
    if code is None:
        return '<span class="badge muted">no exit</span>'
    ok = code == (expected if expected is not None else 0)
    return f'<span class="badge {"ok" if ok else "bad"}">exit {code}</span>'


def level_badge(level: str | None) -> str:
    good = level in ("inference", "service", "function", "install")
    return f'<span class="badge big {"ok" if good else "bad"}">{e(level or "unknown")}</span>'


def _image(path: Path) -> str | None:
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _usage(u: dict[str, Any] | None) -> str:
    if not u:
        return ""
    return (f'<span class="tok">in {tokens(u.get("input_tokens"))} · cached {tokens(u.get("cached_tokens"))}'
            f' · out {tokens(u.get("output_tokens"))} · reasoning {tokens(u.get("reasoning_tokens"))}</span>')


def _output(command: dict[str, Any], open_: bool) -> str:
    out = tail(command.get("stdout"))
    err = tail(command.get("stderr"))
    if not out and not err:
        return '<div class="muted small">no output</div>'
    body = e(out) + (f'\n<span class="stderr">{e(err)}</span>' if err else "")
    return (f'<details{" open" if open_ else ""}><summary>output</summary>'
            f'<pre class="term">{body}</pre></details>')


def _tool_args(call: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}


# --- sections ---------------------------------------------------------------------------------


def section(title: str, body: str, *, kicker: str, cls: str = "") -> str:
    return (f'<section class="step {cls}"><div class="kicker">{e(kicker)}</div>'
            f'<h2>{e(title)}</h2>{body}</section>')


def hero(data: dict[str, Any]) -> str:
    report, outcome, run = data["report"], data["outcome"], data["run"] or {}
    box = report.get("box") or {}
    calls = data["calls"]
    meta_cost = sum(c.get("cost_usd") or 0 for c in calls) if calls else outcome.get("cost_usd")
    commands = [c for c in report.get("commands") or [] if c.get("tool") in ("run_command", "run_background")]
    failed = sum(1 for c in commands if c.get("exit_code") not in (0, None))
    level = run.get("level") or outcome.get("level")
    stats = [
        ("result", level_badge(level)),
        ("wall time", e(secs(outcome.get("seconds") or report.get("seconds")))),
        ("Meta cost", e(usd(meta_cost))),
        ("sandbox cost", e(usd(outcome.get("box_usd")))),
        ("model calls", e(len(calls) or len(report.get("turns") or []))),
        ("commands", f'{len(commands)} <span class="muted">({failed} failed)</span>'),
        ("replay", e("passed" if outcome.get("replayed") else "not passed")
         + (' <span class="muted">· offline</span>' if outcome.get("offline") else "")),
        ("judge", e(outcome.get("judge") or (data["judge"] or {}).get("verdict") or "–")),
    ]
    tiles = "".join(f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div></div>'
                    for label, value in stats)
    repo = report.get("repo_url")
    return (
        '<header class="step hero">'
        f'<div class="kicker">pickfit verification run · {e(data["run_id"])}</div>'
        f'<h1>{e(report.get("slug"))}</h1>'
        f'<p class="lede">{e(report.get("model"))} installs and smoke-tests it in a fresh '
        f'{e(box.get("runner") or "sandbox")} box ({e(box.get("os"))}/{e(box.get("arch"))}), '
        'then a second box replays the recorded steps with the network off, '
        'and a separate model call judges the redrawn screenshots.</p>'
        + (f'<p class="muted">repo: <a href="{e(repo)}">{e(repo)}</a> · started {e(report.get("started_at"))}'
           f' · image {e(box.get("image"))}</p>' if repo else "")
        + f'<div class="tiles">{tiles}</div>{_timeline(outcome.get("phases") or {})}</header>'
    )


def _timeline(phases: dict[str, float]) -> str:
    parts = [("agent box start", phases.get("agent_box_start")), ("agent", phases.get("agent")),
             ("replay box start", phases.get("replay_box_start")), ("replay", phases.get("replay")),
             ("judge", phases.get("judge"))]
    parts = [(name, s) for name, s in parts if s]
    total = sum(s for _, s in parts)
    if not total:
        return ""
    bars = "".join(f'<div class="seg seg-{i}" style="flex:{s / total:.4f}" title="{e(name)} {s:.1f}s">'
                   f'<span>{e(name)} · {s:.1f}s</span></div>' for i, (name, s) in enumerate(parts))
    return f'<div class="timeline">{bars}</div>'


def plan_section(report: dict[str, Any]) -> str:
    candidates = (report.get("plan") or {}).get("candidates") or []
    if not candidates:
        return ""
    rows = "".join(f'<tr><td>{e(c.get("rank"))}</td><td>{e(c.get("method"))}</td>'
                   f'<td><code>{e(c.get("command"))}</code></td><td class="muted">{e(c.get("origin"))}'
                   f'{" · " + e(c.get("note")) if c.get("note") else ""}</td></tr>' for c in candidates)
    body = ('<p>Before any model call, the program lists install methods from the README and package '
            'metadata, best first. The model may only pick among them or fix what fails.</p>'
            f'<table><tr><th>#</th><th>method</th><th>command</th><th>from</th></tr>{rows}</table>')
    return section("Install candidates", body, kicker="step 1 · program")


def agent_sections(report: dict[str, Any]) -> list[str]:
    commands_by_turn: dict[int, list[dict[str, Any]]] = {}
    for c in report.get("commands") or []:
        commands_by_turn.setdefault(c.get("turn"), []).append(c)
    out = []
    for turn in report.get("turns") or []:
        n = turn.get("turn")
        head = (f'<div class="meta"><span class="pill">{e(turn.get("model"))}</span>'
                f'<span>{e(secs(turn.get("latency_s")))}</span><span>{e(usd(turn.get("cost_usd")))}</span>'
                f'{_usage(turn.get("usage"))}</div>')
        parts = [head]
        if turn.get("reasoning_summary"):
            parts.append(f'<blockquote class="reasoning"><b>reasoning summary</b><br>'
                         f'{e(turn["reasoning_summary"]).replace(chr(10), "<br>")}</blockquote>')
        if turn.get("text"):
            parts.append(f'<p class="say">“{e(turn["text"])}”</p>')
        for call in turn.get("tool_calls") or []:
            if call.get("name") == "finish":
                parts.append(_finish(_tool_args(call)))
        for c in commands_by_turn.get(n, []):
            parts.append(_command(c))
        failed = any(c.get("exit_code") not in (0, None) for c in commands_by_turn.get(n, []))
        title = _turn_title(turn, commands_by_turn.get(n, []))
        out.append(section(title, "".join(parts), kicker=f"step 2 · agent turn {n}",
                           cls="failed" if failed else ""))
    return out


def _turn_title(turn: dict[str, Any], commands: list[dict[str, Any]]) -> str:
    names = [c.get("name") for c in turn.get("tool_calls") or []]
    if "finish" in names:
        return "The agent reports what worked"
    if not commands:
        return "Think"
    c = next((c for c in commands if c.get("exit_code") not in (0, None)), commands[0])
    what = c.get("purpose") or c.get("command") or ""
    what = what[:1].upper() + what[1:]
    if c.get("exit_code") not in (0, None):
        return f"Fails: {what}"
    return {"list_dir": "Look around", "read_file": "Read the README"}.get(c.get("tool"), what)


def _command(c: dict[str, Any]) -> str:
    tool = c.get("tool")
    failed = c.get("exit_code") not in (0, None)
    prompt = {"run_command": "$", "run_background": "$ (background)", "list_dir": "ls", "read_file": "read"}.get(tool, tool)
    hints = "".join(f'<div class="hint"><b>rule · {e(h.get("rule"))}</b> {e(h.get("hint"))}'
                    + (f' <code>{e(h["suggested_command"])}</code>' if h.get("suggested_command") else "")
                    + '</div>' for h in c.get("hints") or [])
    cid = f'<span class="muted small">command_id {e(c["command_id"])}</span>' if c.get("command_id") else ""
    purpose = f'<div class="muted small">{e(c["purpose"])}</div>' if c.get("purpose") else ""
    show_output = tool in ("run_command", "run_background")
    return (f'<div class="cmd{" cmd-bad" if failed else ""}">'
            f'<div class="cmdline"><span class="prompt">{e(prompt)}</span> <code>{e(c.get("command"))}</code></div>'
            f'<div class="meta">{exit_badge(c.get("exit_code"))}<span>{e(secs(c.get("seconds")))}</span>'
            f'{"<span class=badge>timed out</span>" if c.get("timed_out") else ""}{cid}</div>'
            f'{purpose}{hints}{_output(c, failed) if show_output else ""}</div>')


def _finish(args: dict[str, Any]) -> str:
    pitfalls = args.get("pitfalls") or []
    rows = "".join(f'<tr><td>{e(p.get("readme_said"))}</td><td>{e(p.get("actually_needed"))}</td></tr>'
                   for p in pitfalls)
    table = (f'<table><tr><th>README said</th><th>actually needed</th></tr>{rows}</table>' if rows else "")
    steps = ", ".join(str(s.get("command_id")) for s in args.get("steps") or [])
    smoke = ", ".join(str(s.get("command_id")) for s in args.get("smoke_tests") or [])
    return (f'<div class="finish"><div>claimed level {level_badge(args.get("level"))} · install method '
            f'<code>{e(args.get("install_method"))}</code></div>'
            f'<div class="muted small">cites install steps [{e(steps)}] and checks [{e(smoke)}] by command_id; '
            'the program checks each against the command log</div>{table}</div>')


def verdict_section(report: dict[str, Any]) -> str:
    verdict = report.get("verdict") or {}
    if not verdict:
        return ""
    rows = "".join(
        f'<tr><td><code>{e(c.get("command"))}</code></td><td>{e(c.get("kind"))}</td>'
        f'<td>{exit_badge(c.get("exit_code"), c.get("expected_exit_code"))}</td>'
        f'<td><code>{e(c.get("expected_signal"))}</code></td>'
        f'<td>{"✓" if c.get("passed") else "✗"}{" · " + e("; ".join(c["problems"])) if c.get("problems") else ""}</td></tr>'
        for c in verdict.get("checks") or [])
    body = (f'<p>The model claimed {level_badge(verdict.get("claimed_level"))}; the command log supports '
            f'{level_badge(verdict.get("level"))}. A step must exit 0 without masking its exit code; a check '
            'needs its expected exit code and its signal in the output.</p>'
            f'<table><tr><th>check</th><th>kind</th><th>exit</th><th>expected signal</th><th>log</th></tr>{rows}</table>')
    return section("The program checks the claim against the log", body, kicker="step 3 · program")


def replay_section(replay: dict[str, Any] | None) -> str:
    if not replay:
        return section("Replay", '<p class="muted">no replay ran</p>', kicker="step 4 · fresh box")
    result = replay.get("result") or {}
    def row(kind: str, item: dict[str, Any], expected: int | None = 0) -> str:
        run = item.get("run") or item
        net = "on" if run.get("network", item.get("network", True)) else "off"
        if kind == "check":
            net = "off" if item.get("offline") else "on (needed)"
        return (f'<tr><td>{e(kind)}</td><td><code>{e(run.get("command"))}</code></td>'
                f'<td>{exit_badge(run.get("exit_code"), expected)}</td><td>{e(secs(run.get("seconds")))}</td>'
                f'<td>{e(net)}</td><td>{"✓" if item.get("passed", run.get("exit_code") == 0) else "✗"}</td></tr>')
    rows = "".join(row("step", s) for s in result.get("steps") or [])
    rows += "".join(row("setup", s) for s in result.get("setups") or [])
    rows += "".join(row("check", c, c.get("expected_exit_code")) for c in result.get("checks") or [])
    status = level_badge(result.get("level")) if result.get("passed") else '<span class="badge big bad">failed</span>'
    error = f'<p class="bad-text">{e(result["error"])}</p>' if result.get("error") else ""
    body = (f'<p>A brand-new box reruns only the recorded steps, then cuts the network and reruns the checks. '
            f'Only steps that pass here are written to the install guide. Result: {status}'
            f'{" · works offline" if result.get("offline") else ""}</p>{error}'
            f'<table><tr><th></th><th>command</th><th>exit</th><th>time</th><th>network</th><th>ok</th></tr>{rows}</table>')
    return section("Replay in a fresh box, network off", body, kicker="step 4 · program, new sandbox")


def judge_section(judge: dict[str, Any] | None, run_dir: Path) -> str:
    if not judge:
        return ""
    regions_by_image: dict[int, list[dict[str, Any]]] = {}
    for region in judge.get("regions") or []:
        regions_by_image.setdefault(region.get("image"), []).append(region)
    shots = []
    for i, shot in enumerate(judge.get("screenshots") or [], start=1):
        src = _image(run_dir / Path(shot).name)
        if src is None:
            continue
        boxes, notes = [], []
        for k, region in enumerate(regions_by_image.get(i, []), start=1):
            x0, y0, x1, y1 = region.get("box") or (0, 0, 0, 0)
            boxes.append(f'<div class="ebox" style="left:{x0 / 10}%;top:{y0 / 10}%;width:{(x1 - x0) / 10}%;'
                         f'height:{(y1 - y0) / 10}%"><span>{k}</span></div>')
            read_back = region.get("text") or ""
            notes.append(f'<li><span class="num">{k}</span> <b>{e(region.get("label"))}</b>'
                         + (f'<pre class="term small">{e(tail(read_back, 4, 400))}</pre>' if read_back
                            else ' <span class="badge bad">box covers no text</span>') + '</li>')
        shots.append(f'<figure class="shot"><div class="frame"><img src="{src}" alt="redrawn screenshot {i}">'
                     f'{"".join(boxes)}</div><figcaption><ul class="regions">{"".join(notes)}</ul></figcaption></figure>')
    problems = "".join(f"<li>{e(p)}</li>" for p in judge.get("problems") or [])
    body = (f'<div class="meta"><span class="pill">{e(judge.get("model"))}</span><span>{e(secs(judge.get("latency_s")))}</span>'
            f'<span>{e(usd(judge.get("cost_usd")))}</span>{_usage(judge.get("usage"))}</div>'
            f'<p>A separate call sees only what the replay ran: each check\'s command, exit code and output, '
            f'and a screenshot redrawn from that output. It does not see the agent\'s narrative. '
            f'Verdict: <span class="badge big {"ok" if judge.get("verdict") == "working" else "bad"}">{e(judge.get("verdict"))}</span></p>'
            f'<p class="say">“{e(judge.get("observed"))}”</p>'
            '<p class="muted small">Boxes are the judge\'s evidence regions (0–1000 coordinates). Under each '
            'label is the text the program read back from that region of the grid.</p>'
            f'<div class="shots">{"".join(shots)}</div>'
            + (f'<p class="muted small">program notes:</p><ul class="small">{problems}</ul>' if problems else ""))
    return section("A second model judges the screenshots", body, kicker="step 5 · screen judge")


def result_section(run: dict[str, Any] | None, outcome: dict[str, Any]) -> str:
    if not run:
        return ""
    steps = "".join(f'<li><code>{e(s.get("command"))}</code></li>' for s in run.get("steps") or [])
    checks = "".join(f'<li><code>{e(t.get("command"))}</code> → <code>{e(t.get("expected_signal"))}</code>'
                     f'{" · offline" if t.get("offline") else ""}</li>' for t in run.get("smoke_tests") or [] if t.get("passed"))
    pitfalls = "".join(f'<tr><td>{e(p.get("readme_said"))}</td><td>{e(p.get("actually_needed"))}</td></tr>'
                       for p in run.get("pitfalls") or [])
    written = outcome.get("written")
    body = (f'<p>Level {level_badge(run.get("level"))} · method <code>{e(run.get("install_method"))}</code>'
            f' · version {e(run.get("tool_version") or "–")} · {e(run.get("runner"))} {e(run.get("os"))}/{e(run.get("arch"))}'
            f' · {"written to the record" if written else "not written to the record"}</p>'
            f'<div class="cols"><div><h3>install steps (replayed)</h3><ol>{steps}</ol></div>'
            f'<div><h3>checks that passed</h3><ul>{checks}</ul></div></div>'
            + (f'<h3>where the README was not enough</h3><table><tr><th>README said</th><th>actually needed</th></tr>{pitfalls}</table>'
               if pitfalls else "")
            + (f'<p class="bad-text">{e(run["blocking_error"])}</p>' if run.get("blocking_error") else ""))
    return section("What get_install_guide will serve", body, kicker="step 6 · result")


def calls_section(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return ""
    rows, total = [], {"cost": 0.0, "in": 0, "cached": 0, "out": 0, "reasoning": 0, "latency": 0.0}
    for i, c in enumerate(calls, start=1):
        u = c.get("usage") or {}
        total["cost"] += c.get("cost_usd") or 0
        total["latency"] += c.get("latency_s") or 0
        for key, name in (("in", "input_tokens"), ("cached", "cached_tokens"), ("out", "output_tokens"),
                          ("reasoning", "reasoning_tokens")):
            total[key] += u.get(name) or 0
        rows.append(f'<tr><td>{i}</td><td>{e(c.get("stage"))}</td><td>{e(c.get("model"))}</td>'
                    f'<td>{e(c.get("reasoning_effort"))}</td><td>{e(c.get("status"))}{" (cache)" if c.get("cache_hit") else ""}</td>'
                    f'<td class="num">{e(secs(c.get("latency_s")))}</td><td class="num">{tokens(u.get("input_tokens"))}</td>'
                    f'<td class="num">{tokens(u.get("cached_tokens"))}</td><td class="num">{tokens(u.get("output_tokens"))}</td>'
                    f'<td class="num">{tokens(u.get("reasoning_tokens"))}</td><td class="num">{e(usd(c.get("cost_usd")))}</td></tr>')
    hit = total["cached"] / total["in"] if total["in"] else 0
    rows.append(f'<tr class="total"><td></td><td colspan="4">total · prompt cache hit {hit:.0%}</td>'
                f'<td class="num">{e(secs(total["latency"]))}</td><td class="num">{tokens(total["in"])}</td>'
                f'<td class="num">{tokens(total["cached"])}</td><td class="num">{tokens(total["out"])}</td>'
                f'<td class="num">{tokens(total["reasoning"])}</td><td class="num">{e(usd(total["cost"]))}</td></tr>')
    body = ('<p>Every call went through <code>call_meta</code>, which priced it from the API\'s own usage '
            'numbers and wrote it to the shared ledger and this trace.</p>'
            '<table class="calls"><tr><th>#</th><th>stage</th><th>model</th><th>effort</th><th>status</th>'
            '<th>latency</th><th>input</th><th>cached</th><th>output</th><th>reasoning</th><th>cost</th></tr>'
            f'{"".join(rows)}</table>')
    return section("Every Meta model call in this run", body, kicker="appendix · traces")


CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--ok:#3fb950;--bad:#f85149;
--accent:#58a6ff;--warn:#d29922;--box:#ffcc00}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:17px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",
Helvetica,Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:32px 24px 120px}
a{color:var(--accent)}
code,pre,.term{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:14.5px}
code{background:#1f2630;padding:1px 6px;border-radius:5px;word-break:break-word}
h1{font-size:44px;margin:4px 0 10px}h2{font-size:26px;margin:4px 0 14px}h3{font-size:16px;color:var(--muted);margin:14px 0 6px}
.kicker{color:var(--accent);font-size:13px;letter-spacing:.08em;text-transform:uppercase}
.lede{font-size:19px;max-width:900px}
.step{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 26px;margin:18px 0;
transition:box-shadow .2s,border-color .2s}
.step.current{border-color:var(--accent);box-shadow:0 0 0 3px rgba(88,166,255,.25)}
.step.failed{border-left:5px solid var(--bad)}
.hero{background:linear-gradient(180deg,#14213a,#161b22)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:18px 0}
.tile{background:#0f141b;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tile .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.tile .value{font-size:20px;font-weight:600;margin-top:2px}
.timeline{display:flex;height:34px;border-radius:8px;overflow:hidden;margin-top:6px;font-size:12px}
.seg{display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden;color:#0d1117;font-weight:600;min-width:4px}
.seg-0,.seg-2{background:#6e7681}.seg-1{background:var(--accent)}.seg-3{background:var(--ok)}.seg-4{background:var(--warn)}
.meta{display:flex;flex-wrap:wrap;gap:12px;align-items:center;color:var(--muted);font-size:14px;margin:4px 0 10px}
.pill{background:#1f2a3a;color:var(--accent);border-radius:999px;padding:2px 10px;font-weight:600}
.tok{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.badge{display:inline-block;border-radius:6px;padding:1px 8px;font-size:13px;font-weight:700;background:#30363d;color:var(--text)}
.badge.ok{background:rgba(63,185,80,.18);color:var(--ok)}.badge.bad{background:rgba(248,81,73,.18);color:var(--bad)}
.badge.big{font-size:16px;padding:2px 10px}.badge.muted{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:13px}.bad-text{color:var(--bad)}
.cmd{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0;background:#0f141b}
.cmd-bad{border-color:rgba(248,81,73,.6)}
.cmdline{font-size:16px}.prompt{color:var(--ok);font-family:ui-monospace,Menlo,monospace;font-weight:700}
.cmdline code{background:none;padding:0;font-size:15.5px}
.hint{margin:8px 0;padding:8px 12px;border-left:4px solid var(--warn);background:rgba(210,153,34,.1);border-radius:6px}
.term{background:#010409;border:1px solid var(--line);border-radius:8px;padding:10px 12px;white-space:pre-wrap;
word-break:break-word;max-height:420px;overflow:auto;margin:6px 0}
.stderr{color:#ff9b93}
details summary{cursor:pointer;color:var(--muted);font-size:13px}
.reasoning{margin:8px 0;padding:10px 14px;border-left:4px solid var(--accent);background:rgba(88,166,255,.08);border-radius:6px;font-size:15px}
.say{font-size:17px;font-style:italic}
.finish{margin:10px 0;padding:12px 14px;border:1px dashed var(--accent);border-radius:10px}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14.5px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}
td.num{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
tr.total td{font-weight:700;border-top:2px solid var(--line)}
.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
.shot{margin:0}.frame{position:relative;border-radius:8px;overflow:hidden;border:1px solid var(--line)}
.frame img{display:block;width:100%;height:auto}
.ebox{position:absolute;border:3px solid var(--box);border-radius:4px;box-shadow:0 0 0 2px rgba(0,0,0,.5)}
.ebox span{position:absolute;left:-3px;top:-24px;background:var(--box);color:#000;font-weight:800;font-size:13px;
padding:1px 7px;border-radius:4px 4px 4px 0}
.regions{list-style:none;padding:0;margin:8px 0}.regions li{margin:6px 0}
.num{background:var(--box);color:#000;font-weight:800;font-size:13px;padding:1px 7px;border-radius:4px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
footer{color:var(--muted);font-size:13px;margin-top:30px}
.nav{position:fixed;right:18px;bottom:16px;background:var(--panel);border:1px solid var(--line);border-radius:999px;
padding:6px 14px;color:var(--muted);font-size:13px}
@media (max-width:720px){.cols{grid-template-columns:1fr}h1{font-size:32px}}
"""

JS = """
const steps=[...document.querySelectorAll('.step')];let i=-1;const nav=document.querySelector('.nav');
function go(n){i=Math.max(0,Math.min(steps.length-1,n));steps.forEach((s,k)=>s.classList.toggle('current',k===i));
steps[i].scrollIntoView({behavior:'smooth',block:'start'});nav.textContent=`${i+1} / ${steps.length} · ← →`;}
document.addEventListener('keydown',ev=>{if(['ArrowRight','ArrowDown','j',' '].includes(ev.key)){ev.preventDefault();go(i+1);}
else if(['ArrowLeft','ArrowUp','k'].includes(ev.key)){ev.preventDefault();go(i-1);}});
nav.textContent=`${steps.length} steps · ← →`;
"""


def render(data: dict[str, Any]) -> str:
    report = data["report"]
    parts = [hero(data), plan_section(report), *agent_sections(report), verdict_section(report),
             replay_section(data["replay"]), judge_section(data["judge"], data["dir"]),
             result_section(data["run"], data["outcome"]), calls_section(data["calls"])]
    footer = ('<footer>Generated by scripts/run_page.py from runs/verify/'
              f'{e(data["run_id"])}/ and runs/traces/. Screenshots are redrawn from captured terminal output '
              '(Pillow), not screen captures; the text log is what decides the result. Not published.</footer>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>pickfit run · {e(report.get("slug"))}</title><style>{CSS}</style></head><body><main>'
            + "".join(p for p in parts if p) + footer
            + f'</main><div class="nav"></div><script>{JS}</script></body></html>\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="a directory name under <runs>/verify/")
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS,
                        help="runs directory with verify/ and traces/ (default runs/)")
    parser.add_argument("--out", type=Path, default=None, help="HTML file (default <runs>/pages/<run_id>.html)")
    args = parser.parse_args(argv)
    data = load_run(args.runs, args.run_id)
    out = args.out or args.runs / "pages" / f"{args.run_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"run_page: {out} ({len(data['calls'])} traced calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
