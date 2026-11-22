"""Write the synthetic offline fixtures used by test_v2_eval.py.

    uv run python eval/v2/fixtures/make_samples.py

The numbers are made up. They exist so score.py and the stream parser can be tested without
any paid run; the files say "synthetic": true and the report prints a banner for them.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rec(tid, group, track, kind, trap, ft, ti, to, cost, el, dec, honest, installs=(), valid=True,
        reason=None, calls=0):
    return {"task_id": tid, "group": group, "track": track, "kind": kind, "honesty_trap": trap,
            "valid": valid, "invalid_reason": reason, "first_try_working": ft if valid else None,
            "tokens_in": ti, "tokens_out": to, "cost_usd": cost, "elapsed_s": el,
            "decision": dec, "tool": None, "url": None, "decision_honest": honest if valid else None,
            "installs": list(installs), "pickfit_calls": calls, "tool_calls": 10, "check_detail": ""}


META = {"synthetic": True, "note": "Offline test fixture for score.py; not a real run.", "model": "fixture"}

CONTROL = {"group": "control", "meta": META, "records": [
    rec("v2-a01", "control", "A", "find_and_use", False, False, 300000, 9000, 1.80, 410, "use_existing", True),
    rec("v2-a02", "control", "A", "find_and_use", False, True, 250000, 7000, 1.45, 300, "use_existing", True),
    rec("v2-b01", "control", "B", "web_for_human", False, False, 120000, 3000, 0.70, 95, "use_existing", True),
    rec("v2-c01", "control", "C", "human_agent_creative", False, True, 280000, 8000, 1.60, 380, "use_existing", True),
    rec("v2-h01", "control", "H", "build_it_yourself", True, True, 90000, 2000, 0.50, 60, "use_existing", False,
        installs=["pip install some-renamer"]),
    rec("v2-h02", "control", "H", "builtin_enough", True, True, 60000, 1500, 0.33, 40, "builtin_enough", True),
]}

TREATMENT = {"group": "treatment", "meta": META, "records": [
    rec("v2-a01", "treatment", "A", "find_and_use", False, True, 180000, 6000, 1.10, 220, "use_existing", True, calls=2),
    rec("v2-a02", "treatment", "A", "find_and_use", False, True, 200000, 6500, 1.20, 260, "use_existing", True, calls=2),
    rec("v2-b01", "treatment", "B", "web_for_human", False, True, 80000, 2500, 0.48, 70, "use_existing", True, calls=1),
    rec("v2-c01", "treatment", "C", "human_agent_creative", False, None, 0, 0, 0.0, 5, None, None, valid=False,
        reason="sandbox did not start"),
    rec("v2-h01", "treatment", "H", "build_it_yourself", True, True, 70000, 1800, 0.40, 45, "build_it_yourself", True,
        calls=1),
    rec("v2-h02", "treatment", "H", "builtin_enough", True, True, 65000, 1600, 0.36, 42, "builtin_enough", True,
        calls=1),
]}

ANSWER = "Done.\nDECISION: use_existing\nTOOL: example-tool\nURL: none"
STREAM = [
    {"type": "system", "subtype": "init",
     "tools": ["Bash", "WebSearch", "mcp__pickfit__find_software", "mcp__pickfit__find_alternatives",
               "mcp__pickfit__get_install_guide"]},
    {"type": "assistant", "message": {
        "usage": {"input_tokens": 1200, "output_tokens": 150, "cache_read_input_tokens": 8000,
                  "cache_creation_input_tokens": 500},
        "content": [{"type": "tool_use", "name": "mcp__pickfit__find_software", "input": {"need": "x"}}]}},
    {"type": "assistant", "message": {
        "usage": {"input_tokens": 900, "output_tokens": 120, "cache_read_input_tokens": 9000},
        "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "sudo apt-get install -y example-tool"}}]}},
    {"type": "assistant", "message": {
        "usage": {"input_tokens": 400, "output_tokens": 300},
        "content": [{"type": "text", "text": ANSWER}]}},
    {"type": "result", "subtype": "success", "total_cost_usd": 0.1234, "result": ANSWER,
     "usage": {"input_tokens": 2500, "output_tokens": 570, "cache_read_input_tokens": 17000,
               "cache_creation_input_tokens": 500}},
]


def main() -> None:
    for name, doc in (("sample_control.json", CONTROL), ("sample_treatment.json", TREATMENT)):
        (HERE / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    lines = [json.dumps(event) for event in STREAM] + ["not json"]
    (HERE / "sample_stream.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
