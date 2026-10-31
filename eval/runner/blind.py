"""Blind review: de-identified answers, 念誠's A/B preference form, and the blind L1 batch.

eval/README.md section 5 (blind preference) and 9.1 C4 (blind L1), 9.2 B, C.3, E.7.

  blind.py prefer  --round run1 --out DIR                     preference form, one A/B pair per question
  blind.py answers --rounds run1 run2 run3 haiku --out DIR
                                                              every counted answer, de-identified and
                                                              shuffled, plus picks.csv to fill in
  blind.py l1-batch --answers DIR --picks picks.csv --set A|B --out DIR
                                                              unique (question, pick) items, shuffled:
                                                              l1-batch.jsonl (graders) + l1-form.csv (念誠)
  blind.py unblind-prefer --form DIR --choices choices.json   join 念誠's choices to the key
  blind.py unblind-l1 --batch DIR --answers DIR --verdicts l1-form.csv
                                                              every answer's L1 from the item verdicts

De-identification (section 5: "pickfit, tool names -> [source]"): the words pickfit /
pick-fit, pickfit's MCP tool names (find_software, find_alternatives, get_install_guide,
report_outcome, submit_software, with or without the mcp__pickfit__ prefix), its record
ids (rec_...), and any URL or host naming pickfit become [source]. Nothing else is
changed; phrases that may still hint at the group (sandbox, verified/replayed,
how_we_know, treasure score) are listed per answer as `tells` for 念誠 to see, not edited.

Randomness (9.3 F.2): one integer, EVAL_SEED = 20261102, fixed when 9.3 was committed and
never changed. Each use draws from its own seed, sha256("<EVAL_SEED>:<use>") cut to 64 bits,
with a fixed use name: prefer:<round>, answers:<rounds joined by commas>, l1-batch:<set>.
--seed exists only for the tests; every output records the seed, the use and the derived
seed, and the key files are written next to the form with their own sha256 printed in the
form, so the key cannot change unseen.
The forms carry no group, round, attempt or model; only the key files do. Do not open a
key file before the matching form is filled in.

Run with: uv run --with pyyaml==6.0.2 python eval/runner/blind.py ...
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as runner  # noqa: E402

PICKFIT_TOOLS = ("find_software", "find_alternatives", "get_install_guide", "report_outcome", "submit_software")
DEID = [
    (re.compile(r"https?://[^\s)\]>\"']*pick-?fit[^\s)\]>\"']*", re.I), "[source]"),
    (re.compile(r"\b[\w.-]*pick-?fit[\w.-]*\.(?:workers\.dev|dev|app|com|net|io)\b", re.I), "[source]"),
    (re.compile(r"\bmcp__pickfit__\w+", re.I), "[source]"),
    (re.compile(r"\b(?:%s)\b" % "|".join(PICKFIT_TOOLS)), "[source]"),
    (re.compile(r"\brec_[0-9a-f]{8,}\b"), "[source]"),
    (re.compile(r"\bpick-?fit\b", re.I), "[source]"),
]
TELLS = re.compile(r"\b(sandbox(?:ed)?|verified|verification|replayed|how_we_know|treasure|evidence_url|"
                   r"matched_by|install guide|lesser-known)\b|沙盒|驗證過|實測", re.I)
PICK_KINDS = ("tool", "keep_current", "custom_script", "no_fit", "none")


def deidentify(text: str) -> tuple[str, list[str]]:
    for pattern, repl in DEID:
        text = pattern.sub(repl, text)
    tells = sorted({m.group(0).lower() for m in TELLS.finditer(text)})
    return text, tells


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def counted_answer(rnd: str, qid: str, group: str, base: Path | None = None) -> dict[str, Any] | None:
    """The valid attempt of a slot (B2: an invalid attempt is retried, never scored)."""
    for meta in runner.attempts(rnd, qid, group, base):
        if meta["valid"]:
            folder = runner.attempt_dir(rnd, qid, group, meta["attempt"], base)
            text = (folder / "answer.md").read_text(encoding="utf-8")
            return {"round": rnd, "question": qid, "group": group, "attempt": meta["attempt"],
                    "model": meta.get("model"), "text": text, "sha256": sha256_bytes(text.encode("utf-8"))}
    return None


def questions_by_id(rounds: list[str]) -> dict[str, dict[str, Any]]:
    path = runner.QUESTIONS_B if rounds == ["bset"] else runner.QUESTIONS_A
    return {q["id"]: q for q in runner.load_questions(path)}


def write_json(path: Path, data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_bytes(text.encode("utf-8"))


EVAL_SEED = 20261102  # eval/README.md 9.3 F.2


def use_seed(seed: int, use: str) -> int:
    """The seed one use draws from: the first 16 hex digits of sha256("<seed>:<use>")."""
    return int(sha256_bytes(f"{seed}:{use}".encode("utf-8"))[:16], 16)


def seed_record(seed: int, use: str) -> dict[str, Any]:
    return {"seed": seed, "use": use, "use_seed": use_seed(seed, use)}


# --- section 5: the preference form -------------------------------------------------------


def prefer(rnd: str, seed: int, out: Path, base: Path | None = None, questions: dict | None = None) -> dict[str, Any]:
    """One pair per question: control and experimental, de-identified, in random A/B order."""
    questions = questions or questions_by_id([rnd])
    seeds = seed_record(seed, f"prefer:{rnd}")
    rng = random.Random(seeds["use_seed"])
    pairs, key = [], {}
    for qid in sorted(questions):
        answers = [counted_answer(rnd, qid, g, base) for g in ("control", "experimental")]
        if any(a is None for a in answers):
            key[qid] = {"missing": [g for g, a in zip(("control", "experimental"), answers) if a is None]}
            continue
        order = answers[:]
        rng.shuffle(order)
        texts = [deidentify(a["text"]) for a in order]
        pairs.append({"question": qid, "prompt": questions[qid]["prompt"].strip(),
                      "A": texts[0][0], "B": texts[1][0], "tells_A": texts[0][1], "tells_B": texts[1][1]})
        key[qid] = {"A": {k: order[0][k] for k in ("group", "attempt", "sha256")},
                    "B": {k: order[1][k] for k in ("group", "attempt", "sha256")}}
    out.mkdir(parents=True, exist_ok=True)
    key_sha = write_json(out / "prefer-key.json", {"round": rnd, **seeds, "pairs": key})
    form = {"round_label": "blind", **seeds, "key_sha256": key_sha, "pairs": pairs,
            "instructions": "For each question choose A, B or tie and give one sentence why, before seeing any "
                            "check result (eval/README.md section 5). Do not open prefer-key.json until done."}
    form_sha = write_json(out / "prefer-form.json", form)
    (out / "prefer-form.html").write_text(form_html(form, form_sha), encoding="utf-8")
    return {"pairs": len(pairs), "missing": [q for q, v in key.items() if "missing" in v], "form_sha256": form_sha,
            "key_sha256": key_sha}


def form_html(form: dict[str, Any], form_sha: str) -> str:
    """A self-contained page: read each pair, choose, export choices.json. Works offline."""
    blocks = []
    for i, p in enumerate(form["pairs"]):
        qid = html.escape(p["question"])
        tells = "".join(f"<li>{side}: {html.escape(', '.join(p['tells_' + side]) or '-')}</li>" for side in ("A", "B"))
        blocks.append(f"""
<section id="{qid}"><h2>{i + 1}. {qid}</h2><p class="prompt">{html.escape(p['prompt'])}</p>
<div class="pair"><div><h3>A</h3><pre>{html.escape(p['A'])}</pre></div><div><h3>B</h3><pre>{html.escape(p['B'])}</pre></div></div>
<details><summary>Words that may hint at the source (not removed)</summary><ul>{tells}</ul></details>
<fieldset><label><input type="radio" name="{qid}" value="A"> A</label>
<label><input type="radio" name="{qid}" value="B"> B</label>
<label><input type="radio" name="{qid}" value="tie"> tie</label>
<input class="why" data-q="{qid}" placeholder="one sentence: why" size="80"></fieldset></section>""")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blind preference</title><style>
:root {{ --bg: #fff; --fg: #1d1d1f; --muted: #6e6e73; --line: #d2d2d7; --panel: #f5f5f7; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1d1f; --fg: #f5f5f7; --muted: #a1a1a6; --line: #424245; --panel: #2c2c2e; }} }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 0 auto; max-width: 1400px; padding: 16px; }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }} @media (max-width: 800px) {{ .pair {{ grid-template-columns: 1fr; }} }}
pre {{ white-space: pre-wrap; background: var(--panel); border: 1px solid var(--line); padding: 10px; border-radius: 6px; max-height: 70vh; overflow: auto; }}
.prompt {{ color: var(--muted); }} section {{ border-bottom: 1px solid var(--line); padding-bottom: 16px; }}
fieldset {{ border: 0; padding: 8px 0; }} button {{ font-size: 16px; padding: 8px 16px; }}
</style></head><body>
<h1>Blind preference</h1><p>{html.escape(form['instructions'])}</p>
<p>form sha256 <code>{form_sha}</code> · key sha256 <code>{form['key_sha256']}</code> · seed {form['seed']} ({html.escape(form['use'])}: {form['use_seed']})</p>
{''.join(blocks)}
<p><button id="export">Export choices.json</button> <span id="left"></span></p>
<script>
const FORM = {json.dumps(form_sha)};
const KEY = "blind-prefer-" + FORM;
function collect() {{
  const out = {{form_sha256: FORM, choices: {{}}}};
  document.querySelectorAll("section").forEach(s => {{
    const q = s.id, c = s.querySelector("input[type=radio]:checked"), why = s.querySelector(".why").value.trim();
    out.choices[q] = {{choice: c ? c.value : null, reason: why}};
  }});
  return out;
}}
function save() {{ try {{ localStorage.setItem(KEY, JSON.stringify(collect())); }} catch (e) {{}} count(); }}
function count() {{ const c = collect().choices; const left = Object.values(c).filter(x => !x.choice || !x.reason).length;
  document.getElementById("left").textContent = left ? left + " left" : "all answered"; }}
try {{ const saved = JSON.parse(localStorage.getItem(KEY) || "null");
  if (saved) for (const [q, v] of Object.entries(saved.choices)) {{
    const r = document.querySelector(`input[name="${{q}}"][value="${{v.choice}}"]`); if (r) r.checked = true;
    const w = document.querySelector(`.why[data-q="${{q}}"]`); if (w) w.value = v.reason || ""; }} }} catch (e) {{}}
document.addEventListener("input", save); count();
document.getElementById("export").onclick = () => {{
  const blob = new Blob([JSON.stringify(collect(), null, 2)], {{type: "application/json"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "choices.json"; a.click(); }};
</script></body></html>
"""


def unblind_prefer(form_dir: Path, choices_path: Path) -> dict[str, Any]:
    form_sha = sha256_bytes((form_dir / "prefer-form.json").read_bytes())
    choices = json.loads(choices_path.read_text(encoding="utf-8"))
    if choices.get("form_sha256") != form_sha:
        raise SystemExit("the choices were made on another form (form_sha256 differs)")
    key = json.loads((form_dir / "prefer-key.json").read_text(encoding="utf-8"))
    rows, tally = [], {"control": 0, "experimental": 0, "tie": 0, "unanswered": 0}
    for qid, side in key["pairs"].items():
        if "missing" in side:
            continue
        pick = (choices["choices"].get(qid) or {}).get("choice")
        group = side[pick]["group"] if pick in ("A", "B") else ("tie" if pick == "tie" else "unanswered")
        tally[group] += 1
        rows.append({"question": qid, "choice": pick, "preferred": group,
                     "reason": (choices["choices"].get(qid) or {}).get("reason")})
    return {"round": key["round"], "seed": key["seed"], "rows": rows, "tally": tally,
            "note": "descriptive only: shown next to the objective results, never replacing them (section 5)"}


# --- 9.1 C4: answers, picks and the blind L1 batch ------------------------------------------


def answers(rounds: list[str], seed: int, out: Path, base: Path | None = None,
            questions: dict | None = None) -> dict[str, Any]:
    questions = questions or questions_by_id(rounds)
    found = []
    for rnd in rounds:
        for qid in sorted(questions):
            for group in runner.GROUPS:
                a = counted_answer(rnd, qid, group, base)
                if a:
                    found.append(a)
    seeds = seed_record(seed, "answers:" + ",".join(rounds))
    random.Random(seeds["use_seed"]).shuffle(found)
    out.mkdir(parents=True, exist_ok=True)
    rows, key = [], {}
    for i, a in enumerate(found, 1):
        answer_id = f"A{i:04d}"
        text, tells = deidentify(a["text"])
        rows.append({"answer_id": answer_id, "question": a["question"], "text": text, "tells": tells})
        key[answer_id] = {k: a[k] for k in ("round", "question", "group", "attempt", "model", "sha256")}
    with (out / "answers.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    key_sha = write_json(out / "answers-key.json", {"rounds": rounds, **seeds, "answers": key})
    with (out / "picks.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["answer_id", "question", "pick_kind", "pick_tool", "install_method", "note"])
        for row in rows:
            w.writerow([row["answer_id"], row["question"], "", "", "", ""])
    return {"answers": len(rows), "key_sha256": key_sha,
            "fill_in": "picks.csv: pick_kind one of %s; pick_tool and install_method as the answer names its "
                       "first or explicitly preferred recommendation (9.1 C2)" % ", ".join(PICK_KINDS)}


def norm_tool(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def checks_for(question: dict[str, Any]) -> list[str]:
    """[L1] items; q10 and q20 have none, so their [L3] items (9.1 C1)."""
    l1 = [c for c in question["success_checklist"] if c.startswith("[L1]")]
    return l1 or [c for c in question["success_checklist"] if c.startswith("[L3]")]


def l1_batch(answers_dir: Path, picks_csv: Path, set_name: str, seed: int, out: Path,
             questions: dict | None = None) -> dict[str, Any]:
    """Unique (question, pick, install) items in random order; the answers behind each stay in the key."""
    questions = questions or questions_by_id(["bset"] if set_name == "B" else ["run1"])
    with picks_csv.open(encoding="utf-8") as fh:
        picks = [r for r in csv.DictReader(fh)]
    empty = [r["answer_id"] for r in picks if r["pick_kind"] not in PICK_KINDS]
    if empty:
        raise SystemExit(f"picks.csv: {len(empty)} row(s) without a valid pick_kind, e.g. {empty[:5]}")
    groups: dict[tuple[str, str, str], list[str]] = {}
    shown: dict[tuple[str, str, str], dict[str, str]] = {}
    no_item = []
    for r in picks:
        if r["pick_kind"] in ("no_fit", "none"):
            no_item.append({"answer_id": r["answer_id"], "question": r["question"], "pick_kind": r["pick_kind"]})
            continue
        tool = r["pick_tool"] if r["pick_kind"] == "tool" else r["pick_kind"].replace("_", " ")
        k = (r["question"], r["pick_kind"], norm_tool(tool) + "|" + norm_tool(r.get("install_method") or ""))
        groups.setdefault(k, []).append(r["answer_id"])
        shown.setdefault(k, {"tool": tool, "install": r.get("install_method") or "", "kind": r["pick_kind"]})
    keys = sorted(groups)
    seeds = seed_record(seed, f"l1-batch:{set_name}")
    random.Random(seeds["use_seed"]).shuffle(keys)
    out.mkdir(parents=True, exist_ok=True)
    items, item_key = [], {}
    for i, k in enumerate(keys, 1):
        q = questions[k[0]]
        item_id = f"{set_name}-L1-{i:04d}"
        items.append({"item_id": item_id,
                      "question": {"id": q["id"], "kind": q.get("kind"), "prompt": q["prompt"],
                                   "constraints": q.get("constraints"), "l1_checks": checks_for(q)},
                      "pick": shown[k], "evidence": []})
        item_key[item_id] = groups[k]
    with (out / "l1-batch.jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    key_sha = write_json(out / "l1-items-key.json", {"set": set_name, **seeds, "items": item_key,
                                                     "no_item": no_item,
                                                     "answers_sha256": sha256_bytes((answers_dir / "answers.jsonl").read_bytes()),
                                                     "picks_sha256": sha256_bytes(picks_csv.read_bytes())})
    with (out / "l1-form.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "question", "pick", "install_method", "checks", "overall", "notes"])
        for item in items:
            w.writerow([item["item_id"], item["question"]["id"], item["pick"]["tool"], item["pick"]["install"],
                        " | ".join(item["question"]["l1_checks"]), "", ""])
    return {"items": len(items), "answers_without_item": len(no_item), "key_sha256": key_sha}


def unblind_l1(batch_dir: Path, answers_dir: Path, verdicts_csv: Path) -> dict[str, Any]:
    """Every answer's L1 from its item's verdict; answers with no item keep their pick kind for C6 and 5."""
    item_key = json.loads((batch_dir / "l1-items-key.json").read_text(encoding="utf-8"))
    answer_key = json.loads((answers_dir / "answers-key.json").read_text(encoding="utf-8"))["answers"]
    with verdicts_csv.open(encoding="utf-8") as fh:
        verdicts = {r["item_id"]: r["overall"].strip() for r in csv.DictReader(fh)}
    rows = []
    for item_id, answer_ids in item_key["items"].items():
        for answer_id in answer_ids:
            rows.append({**answer_key[answer_id], "answer_id": answer_id, "item_id": item_id,
                         "l1": verdicts.get(item_id) or "not graded"})
    for entry in item_key["no_item"]:
        rows.append({**answer_key[entry["answer_id"]], "answer_id": entry["answer_id"], "item_id": None,
                     "l1": entry["pick_kind"]})
    rows.sort(key=lambda r: (r["round"], r["question"], r["group"]))
    return {"rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/blind.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prefer")
    p.add_argument("--round", default="run1", choices=list(runner.ROUNDS))
    p.add_argument("--seed", type=int, default=EVAL_SEED, help=argparse.SUPPRESS)
    p.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("answers")
    a.add_argument("--rounds", nargs="+", required=True, choices=list(runner.ROUNDS))
    a.add_argument("--seed", type=int, default=EVAL_SEED, help=argparse.SUPPRESS)
    a.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("l1-batch")
    b.add_argument("--answers", type=Path, required=True)
    b.add_argument("--picks", type=Path, required=True)
    b.add_argument("--set", required=True, choices=["A", "B"])
    b.add_argument("--seed", type=int, default=EVAL_SEED, help=argparse.SUPPRESS)
    b.add_argument("--out", type=Path, required=True)
    u = sub.add_parser("unblind-prefer")
    u.add_argument("--form", type=Path, required=True)
    u.add_argument("--choices", type=Path, required=True)
    v = sub.add_parser("unblind-l1")
    v.add_argument("--batch", type=Path, required=True)
    v.add_argument("--answers", type=Path, required=True)
    v.add_argument("--verdicts", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prefer":
        result = prefer(args.round, args.seed, args.out)
    elif args.command == "answers":
        if "bset" in args.rounds and args.rounds != ["bset"]:
            raise SystemExit("the B set is its own batch (9.2 E.7): --rounds bset alone")
        result = answers(args.rounds, args.seed, args.out)
    elif args.command == "l1-batch":
        result = l1_batch(args.answers, args.picks, args.set, args.seed, args.out)
    elif args.command == "unblind-prefer":
        result = unblind_prefer(args.form, args.choices)
    else:
        result = unblind_l1(args.batch, args.answers, args.verdicts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
