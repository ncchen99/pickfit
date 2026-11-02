"""Fill blind.py's picks.csv from the de-identified answers (eval/README.md 9.1 C2, C4).

C4 starts from "each answer's first pick, with the install method it names". The answers are
de-identified and shuffled (blind.py answers), so this sees no group, round or model. One call
per answer to the grader model (config grader_model) records what the answer recommends; it
does not judge it. The replies are kept next to picks.csv (picks-extract.jsonl) and the filled
picks.csv is reviewed by hand before blind.py l1-batch; corrections are listed in the run log.
Spend counts toward caps_usd.grading in eval/results/grading-spend.json.

  extract_picks.py --answers DIR [--workers 6]

Run with: uv run --with pyyaml==6.0.2 --with anthropic==2.3.0 python eval/runner/extract_picks.py ...
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blind  # noqa: E402
import grade  # noqa: E402

EFFORT = "low"  # recording what an answer says, not grading it
MAX_TOKENS = 2000
SYSTEM = """You record which recommendation an answer makes, for a blind evaluation. You see one user question and one answer to it. Do not judge whether the recommendation is right, and do not guess who wrote the answer.

Record:
- pick_kind:
  - "tool": the answer's first recommendation, or the one it explicitly calls its top pick, is an existing software tool.
  - "keep_current": a find_alternatives question, and the main recommendation is to keep using the tool the user already uses (configured or used differently).
  - "custom_script": the main recommendation is a script or program the answer writes itself rather than an existing tool.
  - "no_fit": the main conclusion is that no tool meets all the requirements, even if it then names the closest option.
  - "none": no identifiable recommendation (a refusal, only questions back, or an empty answer).
  For a builtin_enough question (the user asks whether an extra tool is needed): if the main recommendation is a built-in way with no additional tool, use "tool" and name that way in pick_tool, starting with "built-in: ".
- pick_tool: for "tool", the tool's name as the answer writes it; for "keep_current", the current tool's name; otherwise empty.
- install_method: the install method the answer gives for that pick, as one short command or channel without versions, flags or paths (for example "cargo install leakguard", "brew install foo", "pipx install foo", "npm install -g foo", "GitHub release binary", "build from source", "docker image owner/name"); empty if it gives none.
- repo_url: the official repository or homepage URL the answer gives for the pick; otherwise empty.
- closest: for "no_fit", the closest option the answer names; otherwise empty.
- note: one short sentence if the pick is ambiguous (for example two options presented as equal); otherwise empty.

Reply with JSON only."""
SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("pick_tool", "install_method", "repo_url", "closest", "note")}
    | {"pick_kind": {"type": "string", "enum": list(blind.PICK_KINDS)}},
    "required": ["pick_kind", "pick_tool", "install_method", "repo_url", "closest", "note"],
    "additionalProperties": False,
}


def user_message(row: dict[str, Any], question: dict[str, Any]) -> str:
    return "\n".join([f"Question {question['id']} ({question.get('kind', 'find_software')}):",
                      question["prompt"].strip(), "", "Answer:", row["text"].strip()])


def call(config: dict[str, Any], user: str) -> dict[str, Any]:
    import anthropic  # uv run --with anthropic==2.3.0

    sys.path.insert(0, str(grade.ROOT))
    from pickfit.env import read_env

    client = anthropic.Anthropic(api_key=read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=config["grader_model"], max_tokens=MAX_TOKENS, system=SYSTEM, messages=[{"role": "user", "content": user}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    u = response.usage
    usage = {"input_tokens": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
             "cached_input_tokens": u.cache_read_input_tokens or 0, "output_tokens": u.output_tokens}
    return {"model": response.model, "request_id": response._request_id, "stop_reason": response.stop_reason,
            "reply": json.loads(text), "usage": usage, "cost_usd": round(grade.cost(config["grader_model"], usage), 6)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    config = grade.load_config()
    rows = [json.loads(line) for line in (args.answers / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    key_rounds = json.loads((args.answers / "answers-key.json").read_text(encoding="utf-8"))["rounds"]
    questions = blind.questions_by_id(key_rounds)
    out = args.answers / "picks-extract.jsonl"
    done = {json.loads(line)["answer_id"]: json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()} \
        if out.exists() else {}
    cap = float(config["caps_usd"]["grading"])
    todo = [r for r in rows if r["answer_id"] not in done]
    rate_in, rate_out, _ = grade.PRICES[config["grader_model"]]
    worst = sum(((len(SYSTEM) + len(user_message(r, questions[r["question"]]))) / 3 * rate_in + MAX_TOKENS * rate_out)
                / 1_000_000 for r in todo)
    spent = grade.read_ledger().get("spent_usd", {}).get("grading", 0.0)
    print(f"{len(todo)} to extract; worst case ${worst:.2f}; grading spent ${spent:.2f} of ${cap}")
    if spent + worst > cap:
        raise SystemExit("could pass the grading cap; stopping before any call")
    with cf.ThreadPoolExecutor(args.workers) as pool, out.open("a", encoding="utf-8") as fh:
        futures = {pool.submit(call, config, user_message(r, questions[r["question"]])): r for r in todo}
        for fut in cf.as_completed(futures):
            r = futures[fut]
            res = fut.result()
            entry = {"answer_id": r["answer_id"], "question": r["question"], "at": grade.now(), **res,
                     "system_sha256": hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest(), "effort": EFFORT}
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            grade.record({"use": "extract_picks", "answer_id": r["answer_id"], "at": entry["at"], "model": res["model"],
                          "request_id": res["request_id"], "usage": res["usage"], "cost_usd": res["cost_usd"]}, "grading")
            done[r["answer_id"]] = entry
    with (args.answers / "picks.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["answer_id", "question", "pick_kind", "pick_tool", "install_method", "note"])
        for r in rows:
            p = done[r["answer_id"]]["reply"]
            note = "; ".join(x for x in (p["repo_url"], f"closest: {p['closest']}" if p["closest"] else "", p["note"]) if x)
            w.writerow([r["answer_id"], r["question"], p["pick_kind"], p["pick_tool"], p["install_method"], note])
    print(f"picks.csv written: {len(rows)} rows; grading spent ${grade.read_ledger()['spent_usd'].get('grading', 0):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
