"""Build the secondary-capability check set: requests for things a tool's README documents
but its record does not list.

Usage:
    uv run python scripts/capability_queries.py [--tools 70] [--seed 1119] [--out worker/bench/capability/queries.json]
    uv run python scripts/capability_queries.py --control [--out worker/bench/capability/control.json]

The record's profile (summary, tags, use_cases, features, MCP tool names) is what the
matcher reads. For a sample of verified records whose README pipeline.db holds, a
Claude model (prod) reads the README and the profile and names up to two capabilities
the README clearly documents that the profile does not mention, each with a verbatim
quote, the distinguishing English key terms, and the request a person would type for
it (English and Traditional Chinese). Code then keeps only items whose quote is in the
README and whose key terms are absent from the profile. worker/bench/capability.ts
measures whether the tool is found for those requests.

--control writes the comparison set: for the same tools, one request for the main thing
the profile already lists (its first feature, else its first use case). The gap between
the two sets is what a missing capability costs, apart from how hard the catalog is.

Only data/software and pipeline.db are read (never eval/). Public data only. The run
prints its cost; it is recorded in the shared ledger by call_meta.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from pickfit.discover.run import pipeline_db_path
from pickfit.discover.store import PipelineDB
from pickfit.env import REPO_ROOT
from pickfit.extract import README_MAX_CHARS, normalize_for_match
from pickfit.index import DEFAULT_DATA_DIR, build_index
from pickfit.meta import call_meta
from pickfit.schema import meta_strict_schema

STAGE = "capability-check"
MODEL = "prod"
MAX_OUTPUT_TOKENS = 4_000
DEFAULT_OUT = REPO_ROOT / "worker" / "bench" / "capability" / "queries.json"

INSTRUCTIONS = """You write test requests for a software recommender. The input has one tool: the profile the recommender reads (summary, tags, use_cases, features, mcp_tools) and the tool's README.

Find up to 2 capabilities the README clearly documents that the profile does not mention. Good ones are concrete jobs a person might search for: a file format it reads or writes, a subcommand, an integration, an output mode, a service it talks to. Skip:
- anything the profile already says, even in other words;
- install methods, platforms, license, speed, configuration options with no job of their own;
- capabilities the README only plans ("coming soon", roadmap) or mentions in passing without saying the tool does it.
Return an empty list when the README documents nothing beyond the profile.

For each capability:
- capability: a short English label (at most 8 words), e.g. "convert docx files to EPUB".
- quote: a verbatim passage of at most 200 characters from the README that shows the tool does it. Copy it exactly: no "...", no joining passages, no fixing typos.
- key_terms: 1 to 3 lowercase English words that a request for this job would contain and that distinguish it, e.g. ["epub"]. Not the tool's name, not words in the profile.
- en: the request a person would type to an AI assistant when they need this job done, before they know the tool. One or two plain sentences, at most 30 words. Never use the tool's name or words from its name. Use the key terms the way a user would.
- zh: the same need in Traditional Chinese as a Taiwanese developer would type it, phrased on its own. Keep product names, file formats and technical terms in English when that is natural (EPUB, Docker, JSON)."""


class Capability(BaseModel):
    capability: str
    quote: str
    key_terms: list[str]
    en: str
    zh: str


class Capabilities(BaseModel):
    items: list[Capability]


CONTROL_INSTRUCTIONS = """You write test requests for a software recommender. The input has one tool's profile and one job from it (main).

- key_terms: 1 to 3 lowercase English words from the main job that a request for it would contain and that distinguish it. Not the tool's name.
- en: the request a person would type to an AI assistant when they need the main job done, before they know the tool. One or two plain sentences, at most 30 words. Never use the tool's name or words from its name.
- zh: the same need in Traditional Chinese as a Taiwanese developer would type it, phrased on its own. Keep product names, file formats and technical terms in English when that is natural."""


class ControlRequest(BaseModel):
    key_terms: list[str]
    en: str
    zh: str


def profile_text(entry: dict) -> str:
    tools = [t for inst in (entry.get("install") or {}).values() for t in ((inst or {}).get("mcp") or {}).get("tools") or []]
    parts = [entry["name"], entry["slug"], entry["summary"] or "", *entry["tags"], *entry["use_cases"],
             *(entry.get("features") or []), *tools]
    return " ".join(parts)


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def stems(text: str) -> set[str]:
    # Loose: a key term counts as present when the profile has it, its plural or its singular.
    out = set()
    for w in words(text):
        out |= {w, w.rstrip("s"), w + "s"}
    return out


def _flat(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def names_tool(entry: dict, request: str) -> bool:
    """The tool's name or slug appears in the request as a whole phrase."""
    return any(_flat(n) in _flat(request) for n in (entry["name"], entry["slug"]) if _flat(n).strip())


def control(queries_path: Path, out: Path) -> int:
    """One request per tool in the check set for the main job its profile lists."""
    slugs = sorted({q["slug"] for q in json.loads(queries_path.read_text())["queries"]})
    entries = {e["slug"]: e for e in build_index(DEFAULT_DATA_DIR).index["entries"]}
    schema = meta_strict_schema(ControlRequest)
    rows, cost = [], 0.0
    for slug in slugs:
        e = entries.get(slug)
        main_job = e and ((e.get("features") or []) + e["use_cases"])[:1]
        if not main_job:
            continue
        profile = {"name": e["name"], "summary": e["summary"], "tags": e["tags"], "use_cases": e["use_cases"],
                   "features": e.get("features") or []}
        text = f"<profile>\n{json.dumps(profile, ensure_ascii=False)}\n</profile>\n<main>{main_job[0]}</main>"
        body = {
            "instructions": CONTROL_INSTRUCTIONS,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
            "text": {"format": {"type": "json_schema", "name": "request", "schema": schema, "strict": True}},
            "store": False,
        }
        result = call_meta("responses", body, stage=STAGE, public_data_only=True, model=MODEL,
                           max_output_tokens=1_000, reasoning_effort="low", output_model=ControlRequest)
        cost += result.cost_usd
        r = result.parsed
        if r and not names_tool(e, r.en):
            rows.append({"slug": slug, "category": e["category"], "capability": main_job[0], "quote": None,
                         "key_terms": [t.lower().strip() for t in r.key_terms if t.strip()], "en": r.en, "zh": r.zh})
        print(f"{slug}: ${result.cost_usd:.4f}", file=sys.stderr)
    out.write_text(json.dumps({"model": MODEL, "control_for": str(queries_path.relative_to(REPO_ROOT)),
                               "queries": [dict(q, id=f"m{i:03d}") for i, q in enumerate(rows)]},
                              ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"tools": len(slugs), "queries": len(rows), "cost_usd": round(cost, 4)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tools", type=int, default=70, help="how many tools to sample")
    parser.add_argument("--seed", type=int, default=1119)
    parser.add_argument("--control", action="store_true", help="write the main-job comparison set instead")
    args = parser.parse_args(argv)
    if args.control:
        out = args.out if args.out != DEFAULT_OUT else DEFAULT_OUT.with_name("control.json")
        return control(DEFAULT_OUT, out)

    db = PipelineDB(pipeline_db_path())
    repo_ids = {json.loads(p.read_text())["slug"]: json.loads(p.read_text()).get("repo_id")
                for p in DEFAULT_DATA_DIR.glob("*.json")}
    entries = [e for e in build_index(DEFAULT_DATA_DIR).index["entries"] if e["install"] or e.get("web")]
    readmes: dict[str, str] = {}
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in sorted(entries, key=lambda e: e["slug"]):
        cand = db.candidate(repo_ids.get(e["slug"]) or "")
        readme = ((cand or {}).get("readme") or "")[:README_MAX_CHARS]
        if len(readme) >= 3_000:  # a short README documents little beyond the profile
            readmes[e["slug"]] = readme
            by_cat[e["category"]].append(e)

    # Every category gets a share; small ones are taken whole.
    rng = random.Random(args.seed)
    for items in by_cat.values():
        rng.shuffle(items)
    sample: list[dict] = []
    while len(sample) < args.tools and any(by_cat.values()):
        for cat in sorted(by_cat):
            if by_cat[cat] and len(sample) < args.tools:
                sample.append(by_cat[cat].pop())

    done: dict[str, list[dict]] = {}
    if args.out.exists():
        for q in json.loads(args.out.read_text())["queries"]:
            done.setdefault(q["slug"], []).append(q)
        done.update({s: [] for s in json.loads(args.out.read_text()).get("no_capability", [])})
    schema = meta_strict_schema(Capabilities)
    cost = 0.0
    dropped: list[dict] = []
    for e in sample:
        if e["slug"] in done:
            continue
        readme = readmes[e["slug"]]
        profile = {"name": e["name"], "summary": e["summary"], "tags": e["tags"], "use_cases": e["use_cases"],
                   "features": e.get("features") or [],
                   "mcp_tools": sorted({t for inst in (e.get("install") or {}).values()
                                        for t in ((inst or {}).get("mcp") or {}).get("tools") or []})}
        text = f"<profile>\n{json.dumps(profile, ensure_ascii=False)}\n</profile>\n<readme>\n{readme}\n</readme>"
        body = {
            "instructions": INSTRUCTIONS,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
            "text": {"format": {"type": "json_schema", "name": "capabilities", "schema": schema, "strict": True}},
            "store": False,
        }
        result = call_meta("responses", body, stage=STAGE, public_data_only=True, model=MODEL,
                           max_output_tokens=MAX_OUTPUT_TOKENS, reasoning_effort="low", output_model=Capabilities)
        cost += result.cost_usd
        have = stems(profile_text(e))
        source = normalize_for_match(readme)
        kept = []
        for c in (result.parsed.items if result.parsed else [])[:2]:
            # Only the key terms the profile lacks count; a capability needs at least one.
            terms = [t.lower().strip() for t in c.key_terms if t.strip() and not words(t) <= have]
            why = None
            if normalize_for_match(c.quote) not in source:
                why = "quote not in README"
            elif not c.en.strip() or not c.zh.strip():
                why = "empty request"
            elif not terms:
                why = "every key term already in profile"
            elif names_tool(e, c.en):
                why = "request names the tool"
            if why:
                dropped.append({"slug": e["slug"], "capability": c.capability, "why": why})
                continue
            kept.append({"slug": e["slug"], "category": e["category"], "capability": c.capability,
                         "quote": c.quote, "key_terms": terms, "en": c.en, "zh": c.zh})
        done[e["slug"]] = kept
        print(f"{e['slug']}: {len(kept)} kept, ${result.cost_usd:.4f}", file=sys.stderr)

        queries = [dict(q, id=f"c{i:03d}") for i, q in enumerate(q for s in sorted(done) for q in done[s])]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "model": MODEL, "seed": args.seed, "tools": len(done),
            "no_capability": sorted(s for s, qs in done.items() if not qs),
            "queries": queries,
        }, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"tools": len(done), "queries": sum(len(q) for q in done.values()),
                      "dropped": dropped, "cost_usd": round(cost, 4)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
