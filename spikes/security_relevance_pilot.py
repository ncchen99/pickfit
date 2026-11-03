"""Security relevance pilot (念誠 11/3): does a known vulnerability in a treasure's dependencies reach the person who
uses it? muse-spark-1.3 reads what pickfit knows about the software and the OSV advisories, and says per package
exposed, conditional or not_exposed. Compared against data/calibration/security-relevance-labels.json, written
before any model output. Nothing here touches records or scores.

    uv run python spikes/security_relevance_pilot.py --limit 1      # one treasure first
    uv run python spikes/security_relevance_pilot.py                # all of them
    uv run python spikes/security_relevance_pilot.py --compare      # agreement with the labels, no calls
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pickfit.ledger import BudgetExceeded, taipei_now  # noqa: E402
from pickfit.meta import call_meta  # noqa: E402
from pickfit.schema import meta_strict_schema  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data/calibration/security-relevance-items.json"
LABELS = ROOT / "data/calibration/security-relevance-labels.json"
OUT = ROOT / "data/calibration/security-relevance-pilot.json"
MODEL = "muse-spark-1.3"
STAGE = "security-relevance-pilot"
SCOPE_CAP_USD = 0.10

INSTRUCTIONS = """\
You decide whether known vulnerabilities in a piece of software's dependencies reach the person who uses it. \
pickfit recommends this software to people and installed it in a sandbox; you get what pickfit knows about it \
(what it is, its features, how it is installed) and, per vulnerable package, where the package was found and the \
advisories from OSV.

For each package give one verdict, judged for a person who installs it the way shown and uses it as described:
- exposed: normal use passes input an attacker can influence through the flawed code (for example an HTTPS client \
whose certificate check can be bypassed, in a tool that talks to remote services).
- conditional: it matters only in a use the description makes plausible but not certain (opening files from \
others, exposing a self-hosted server on a network, a specific feature). Name that use in `condition`.
- not_exposed: any of
  * the package only builds or tests the software (bundlers, compilers, CSS tools, test runners, linters, \
dev-server helpers), even if a lockfile lists it as a regular dependency;
  * it was found in a lockfile of a part the person does not install or run (documentation site, editor \
extension, CI action, the author's own backend service, a different distribution than the one described);
  * the software is a web app hosted by its author: server-side code runs on the author's server, so the visitor \
is not the one exposed; only code that runs in the visitor's browser can reach the visitor;
  * the flaw needs a mode or feature this software does not use (for example an HTTP-transport flaw in an MCP \
server used over stdio, a flaw in an optional API the description gives no sign of);
  * it only lets an attacker slow down or crash the program (denial of service).

Use only what you are given and general knowledge of what the named packages do. Do not guess features the \
description does not show. When torn between conditional and not_exposed, choose not_exposed unless the \
description makes the triggering use plausible. reason: one or two sentences, plain words, at most 300 characters.
"""


class PackageVerdict(BaseModel):
    id: str = Field(description="The package's id from the input, e.g. p001.")
    verdict: Literal["exposed", "conditional", "not_exposed"]
    condition: str | None = Field(description="For conditional: the use in which it matters; else null.")
    reason: str


class Verdicts(BaseModel):
    packages: list[PackageVerdict]


def context(slug: str) -> dict:
    r = json.loads((ROOT / "data/software" / f"{slug}.json").read_text())
    install = {}
    for os_name, m in (r.get("install") or {}).items():
        if m:
            install[os_name] = {"method": m.get("method"), "steps": [s["command"][:200] for s in m.get("steps", [])[:3]]}
    return {"name": r["name"], "kind": r["kind"], "summary": r["summary"], "features": r.get("features", []),
            "processing": r.get("processing"), "audience": r.get("audience"), "homepage": r.get("homepage"),
            "install": install}


def judge(slug: str, pairs: list[dict], run_id: str) -> dict:
    payload = {"software": context(slug), "vulnerable_packages": [
        {"id": p["id"], "package": p["package"], "version": p["version"], "found_in": p["where"],
         "lockfile_scope": p["scope"], "advisories": [
             {k: a[k] for k in ("id", "severity", "fixed_in", "summary", "details", "cwe")} for a in p["advisories"]]}
        for p in pairs]}
    body = {
        "instructions": INSTRUCTIONS,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}]}],
        "text": {"format": {"type": "json_schema", "name": "verdicts", "schema": meta_strict_schema(Verdicts),
                            "strict": True}},
        "store": False,
    }
    meta = call_meta("responses", body, stage=STAGE, public_data_only=True, max_output_tokens=8_000, model=MODEL,
                     reasoning_effort="low", scope=f"{STAGE}:{slug}", scope_cap_usd=SCOPE_CAP_USD, run_id=run_id,
                     output_model=Verdicts)
    got = {v.id: v.model_dump() for v in meta.parsed.packages} if meta.parsed else {}
    missing = [p["id"] for p in pairs if p["id"] not in got]
    return {"slug": slug, "model": meta.model, "cost_usd": meta.cost_usd, "error": meta.parse_error,
            "missing": missing, "verdicts": got}


def compare(path: Path = OUT) -> None:
    out = json.loads(path.read_text())
    labels = json.loads(LABELS.read_text())["labels"]
    model = {pid: v for r in out["results"] for pid, v in r["verdicts"].items()}
    matters = lambda v: v != "not_exposed"  # noqa: E731
    cells = collections.Counter()
    disagree = []
    for pid, lab in labels.items():
        if pid not in model:
            cells["missing"] += 1
            continue
        m = model[pid]["verdict"]
        cells[(matters(lab["verdict"]), matters(m))] += 1
        if matters(lab["verdict"]) != matters(m) or lab["verdict"] != m:
            disagree.append((pid, lab, model[pid]))
    tp, fp, fn, tn = (cells[(True, True)], cells[(False, True)], cells[(True, False)], cells[(False, False)])
    print(f"pairs {len(labels)}  label matters/model matters: TP {tp} FP {fp} FN {fn} TN {tn}  missing {cells['missing']}")
    print(f"agreement {(tp + tn) / max(1, tp + fp + fn + tn):.1%}")
    sure = [(pid, lab) for pid, lab in labels.items() if not lab["unsure"] and pid in model]
    print(f"on sure labels: agreement "
          f"{sum(matters(l['verdict']) == matters(model[p]['verdict']) for p, l in sure) / max(1, len(sure)):.1%}"
          f" of {len(sure)}")
    for pid, lab, m in disagree:
        print(f"\n{pid} {lab['slug']} {lab['package']}: label {lab['verdict']}{' (unsure)' if lab['unsure'] else ''}"
              f" / model {m['verdict']}\n  label: {lab['reason']}\n  model: {m['reason']}"
              + (f"\n  condition: {m['condition']}" if m.get("condition") else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT, help="a second run's file, to measure how stable verdicts are")
    args = ap.parse_args()
    if args.compare:
        return compare(args.out)
    pairs = json.loads(ITEMS.read_text())["pairs"]
    by_slug = collections.OrderedDict()
    for p in pairs:
        by_slug.setdefault(p["slug"], []).append(p)
    slugs = list(by_slug)[: args.limit] if args.limit else list(by_slug)
    run_id = f"{STAGE}-{taipei_now():%Y%m%d-%H%M%S}"
    try:
        with ThreadPoolExecutor(4) as ex:
            results = list(ex.map(lambda s: judge(s, by_slug[s], run_id), slugs))
    except BudgetExceeded as err:
        sys.exit(f"budget: {err}")
    args.out.write_text(json.dumps({"run_id": run_id, "model": MODEL, "reasoning_effort": "low",
                               "cost_usd": round(sum(r["cost_usd"] for r in results), 4), "results": results},
                              indent=1, ensure_ascii=False) + "\n")
    print(f"{len(results)} treasures, ${sum(r['cost_usd'] for r in results):.4f}, "
          f"missing {sum(len(r['missing']) for r in results)}, errors {[r['slug'] for r in results if r['error']]}")


if __name__ == "__main__":
    main()
