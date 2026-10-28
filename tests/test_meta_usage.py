"""scripts/meta_usage.py: ledger + traces + verification runs -> Markdown; no network."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pickfit.ledger import Ledger
from scripts.meta_usage import main

ROWS = [
    # day, stage, model, status, cost, input, cached, output, reasoning, cache_hit, response_id
    ("2026-10-28", "extract", "muse-spark-1.3", "settled", 0.02, 4000, 1000, 900, 500, 0, "resp_a"),
    ("2026-10-29", "verify", "muse-spark-1.3", "settled", 0.01, 6000, 5000, 100, 20, 0, "resp_b"),
    ("2026-10-29", "verify", "muse-spark-1.3", "error", 0.0, 0, 0, 0, 0, 0, None),
    ("2026-10-29", "verify", "muse-spark-1.3-contributor", "cache", 0.0, 6000, 5000, 100, 20, 1, "resp_c"),
    ("2026-10-29", "score-rubric", "muse-spark-1.3", "settled", 0.02, 4000, 0, 3000, 2800, 0, "resp_d"),
]


def make_ledger(path: Path) -> Path:
    Ledger(path)  # creates the schema
    conn = sqlite3.connect(path)
    with conn:
        conn.executemany(
            "INSERT INTO calls (ts, day, budget, stage, model, status, cost_usd, input_tokens, cached_tokens, "
            "output_tokens, reasoning_tokens, cache_hit, response_id) "
            "VALUES (?, ?, 'pipeline', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(f"{r[0]}T10:00:00+08:00", *r) for r in ROWS])
        conn.execute("INSERT INTO calls (ts, day, budget, status, cost_usd) "
                     "VALUES ('2026-10-29T10:00:00+08:00', '2026-10-29', 'worker', 'settled', 5.0)")
    conn.close()
    return path


def make_runs(runs: Path) -> None:
    traces = runs / "traces"
    traces.mkdir(parents=True)
    lines = [{"ts": "a", "request_hash": "h1", "attempt": 1, "response_id": "resp_a", "stage": "extract",
              "model": "muse-spark-1.3", "status": "ok", "latency_s": 6.0, "finish": "completed"},
             {"ts": "b", "request_hash": "h2", "attempt": 1, "response_id": "resp_b", "stage": "verify",
              "model": "muse-spark-1.3", "status": "ok", "latency_s": 2.0, "finish": "completed"},
             {"ts": "c", "request_hash": "h3", "attempt": 1, "response_id": "resp_d", "stage": "score-rubric",
              "model": "muse-spark-1.3", "status": "ok", "latency_s": 20.0, "finish": "incomplete"},
             # a unit test that wrote into a real runs/ directory: not in the ledger, left out
             {"ts": "d", "request_hash": "h4", "attempt": 1, "response_id": "judge", "stage": "verify-judge",
              "model": "muse-spark-1.3", "status": "ok", "latency_s": 0.001, "finish": "completed"}]
    (traces / "2026-10-29.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    (traces / "github-2026-10-29.jsonl").write_text('{"query": "topic:cli"}\n')
    for name, level, replayed, seconds in (("verify-a-1", "function", True, 60.0), ("verify-b-1", "unverified", True, 100.0),
                                           ("verify-a-2", "service", True, 80.0), ("verify-c-1", "function", False, 200.0)):
        d = runs / "verify" / name
        d.mkdir(parents=True)
        (d / "outcome.json").write_text(json.dumps({
            "run_id": name, "slug": name.split("-")[1], "level": level, "replayed": replayed, "seconds": seconds,
            "cost_usd": 0.05, "box_usd": 0.003, "runner": "modal-gvisor",
            "phases": {"agent": seconds - 20, "replay": 10.0, "judge": 5.0, "agent_box_s": seconds}}))
        (d / "report.json").write_text(json.dumps({"model": "muse-spark-1.3"}))


def make_records(data: Path) -> None:
    data.mkdir()
    for slug, level, reason in (("a", "function", None), ("b", "unverified", "not_run"), ("c", "unverified", "gui_only")):
        (data / f"{slug}.json").write_text(json.dumps({"verification": {"level": level, "unverified_reason": reason}}))


def test_report_numbers(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path / "ledger.sqlite")
    make_runs(tmp_path / "runs")
    make_records(tmp_path / "data")
    out = tmp_path / "usage.md"
    assert main(["--ledger", str(ledger), "--runs", str(tmp_path / "runs"), "--data", str(tmp_path / "data"),
                 "--out", str(out)]) == 0
    md = out.read_text()
    # 3 billed requests (the 4xx and the local cache hit are not), pipeline budget only
    assert "**3 Meta API requests**" in md and "**$0.0500** in total" in md
    assert "**14,000 input tokens**, 6,000 of them" in md and "**43% cache hit**" in md
    assert "1 more calls were answered from pickfit's local response cache" in md
    # runs: a-1 and a-2 pass; b is unverified; c did not replay
    assert "**Verification: 2 of 4 sandbox runs passed and replayed (50%)**" in md
    assert "1 of 3 tools passed at least once" in md and "Median **90 s per run**" in md
    assert "Records: 1 of 3 in data/software carry a passed, replayed run." in md
    assert "| unverified (gui_only) | 1 |" in md
    assert "over 3 traced requests" in md and "finished incomplete (ran out of output tokens): 1 of 3" in md
    assert "| `score-rubric` | `muse-spark-1.3` | 1 | 4,000 | 0 | 0% | 3,000 | 2,800 | $0.0200 | 20 s |" in md
    assert "agent_box_s" not in md and "credit" not in md.lower().replace("credit balances are not reported", "")


def test_since_limits_days(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path / "ledger.sqlite")
    make_runs(tmp_path / "runs")
    make_records(tmp_path / "data")
    out = tmp_path / "usage.md"
    main(["--ledger", str(ledger), "--runs", str(tmp_path / "runs"), "--data", str(tmp_path / "data"),
          "--since", "2026-10-29", "--out", str(out)])
    md = out.read_text()
    assert "**2 Meta API requests**" in md and "2026-10-28 |" not in md
