"""q08 note (not L2): how each run 1 answer's install and first-run steps differ from the official docs.

q08's L2 could not run (a macOS guest has no nested virtualization; results/l2/mac-gate/gate.json). 念誠 asked
on 2026-11-02 for this comparison instead, as a separate note: one blind call per answer (the de-identified
text from blind/answers-A, no group, no tool lookup by the model), the same fixed docs for both, the C4
grader's model and effort. Spend goes to the grading cap.

  uv run --with anthropic==2.3.0 python eval/runner/q08_docs_note.py --out eval/results/l2/q08-docs-note
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402

ROOT = grade.ROOT
ANSWERS = ["A0107", "A0033"]  # run 1 q08, the two groups (answers-key.json); order fixed, the model sees one at a time
DOCS = [
    ("https://raw.githubusercontent.com/abiosoft/colima/main/README.md", "Colima README"),
    ("https://raw.githubusercontent.com/abiosoft/colima/main/docs/FAQ.md", "Colima FAQ"),
    ("https://formulae.brew.sh/api/formula/colima.json", "Homebrew formula colima"),
    ("https://formulae.brew.sh/api/formula/docker.json", "Homebrew formula docker"),
    ("https://formulae.brew.sh/api/formula/docker-compose.json", "Homebrew formula docker-compose"),
    ("https://formulae.brew.sh/api/formula/docker-buildx.json", "Homebrew formula docker-buildx"),
]
SYSTEM = """You compare one set of install and first-run instructions for a tool with that tool's official documentation. You see only the instructions and the documentation excerpts.

List every difference that matters to someone who follows the instructions verbatim on an Apple silicon Mac: a command, flag, path, file content or order that the documentation contradicts, does not support, or describes differently, and any step the documentation requires that the instructions leave out. For each, say whether following the instructions would make that step fail, make it do something different from what the instructions claim, or is only a difference of wording or optional settings. Do not judge the choice of tool or how well the instructions are written. If the documentation does not cover a step, say so instead of guessing.

Reply with JSON only."""
SCHEMA = {"type": "object", "properties": {
    "differences": {"type": "array", "items": {"type": "object", "properties": {
        "step": {"type": "string"}, "docs_say": {"type": "string"},
        "effect": {"type": "string", "enum": ["fails", "behaves_differently", "cosmetic", "not_covered"]},
        "source": {"type": "string"}}, "required": ["step", "docs_say", "effect", "source"], "additionalProperties": False}},
    "summary": {"type": "string"}}, "required": ["differences", "summary"], "additionalProperties": False}


def fetch(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "p6-eval"}), timeout=60) as r:
        text = r.read().decode("utf-8", "replace")
    if url.endswith(".json"):  # the formula's own words: description, caveats, dependencies, service
        d = json.loads(text)
        text = json.dumps({k: d.get(k) for k in ("name", "desc", "homepage", "versions", "caveats", "dependencies", "service", "conflicts_with")},
                          ensure_ascii=False, indent=1)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    docs = [(url, name, fetch(url)) for url, name in DOCS]
    doc_block = "\n\n".join(f"<doc name=\"{n}\" source=\"{u}\" fetched=\"{at}\">\n{t}\n</doc>" for u, n, t in docs)
    answers = {json.loads(line)["answer_id"]: json.loads(line)["text"]
               for line in (ROOT / "eval/results/blind/answers-A/answers.jsonl").open(encoding="utf-8")}
    (a.out / "docs-sources.json").write_text(json.dumps([{"source": u, "name": n, "fetched_at": at, "chars": len(t)} for u, n, t in docs],
                                                        indent=1) + "\n", encoding="utf-8")
    import anthropic
    sys.path.insert(0, str(ROOT))
    from pickfit.env import read_env

    client = anthropic.Anthropic(api_key=read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"])
    for aid in ANSWERS:
        user = f"{doc_block}\n\n<instructions>\n{answers[aid]}\n</instructions>"
        r = client.messages.create(model="claude-opus-5-5", max_tokens=8000, system=SYSTEM, messages=[{"role": "user", "content": user}],
                                   output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}})
        u = r.usage
        usage = {"input_tokens": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                 "cached_input_tokens": u.cache_read_input_tokens or 0, "output_tokens": u.output_tokens}
        cost = round(grade.cost("claude-opus-5-5", usage), 6)
        grade.record({"use": "q08_docs_note", "answer_id": aid, "at": grade.now(), "model": r.model, "request_id": r._request_id,
                      "usage": usage, "cost_usd": cost}, "grading")
        text = next((b.text for b in r.content if b.type == "text"), "")
        (a.out / f"{aid}.json").write_text(json.dumps({"answer_id": aid, "model": r.model, "effort": "high", "request_id": r._request_id,
                                                        "note": json.loads(text)}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(aid, "done", cost)
    return 0


if __name__ == "__main__":
    sys.exit(main())
