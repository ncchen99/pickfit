"""The C6 L1 batch for q01 (eval/README.md 9.1 C6): every candidate the two "nothing fits" searches turned up,
blind and in a seeded order, with evidence fetched from each project's own repository.

  uv run python eval/runner/c6_batch.py --out eval/results/blind/l1-C6

Candidates: cc-switch-cli (the agent search, runs/c6/q01) and mcpfold, sync-agents-settings, agentlink (念誠's
search, ChatGPT's suggestions, 2026-11-02). Names were resolved to repositories in the run log. The item format is
blind.py's L1 batch (grade.py reads it); the form adds the evidence links for 念誠.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import json
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blind  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = [  # (tool name as suggested, GitHub repo, where it came from)
    ("cc-switch-cli", "SaladDay/cc-switch-cli", "C6 agent search (runs/c6/q01)"),
    ("mcpfold", "dj-pearson/MCPFold", "念誠's search: ChatGPT, 1st suggestion (npm mcpfold links this repo)"),
    ("sync-agents-settings", "Leoyang183/sync-agents-settings", "念誠's search: ChatGPT (npm sync-agents-settings links this repo)"),
    ("agentlink", "martinmose/agentlink", "念誠's search: ChatGPT (the GitHub project of that name about syncing agent configs)"),
]
README_CHARS = 24000


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "p6-eval"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def evidence(repo: str) -> list[dict]:
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    meta = get(f"https://api.github.com/repos/{repo}")
    lic = (meta.get("license") or {}).get("spdx_id")
    head = (f"Repository {meta['html_url']}; description: {meta.get('description')}; language: {meta.get('language')}; "
            f"license (GitHub): {lic}; last push: {meta.get('pushed_at')}; archived: {meta.get('archived')}")
    out = [{"source": f"https://api.github.com/repos/{repo}", "fetched_at": at, "text": head}]
    readme = get(f"https://api.github.com/repos/{repo}/readme")
    text = base64.b64decode(readme["content"]).decode("utf-8", "replace")
    cut = len(text) > README_CHARS
    out.append({"source": readme["html_url"], "fetched_at": at,
                "text": text[:README_CHARS] + ("\n[README cut at %d characters]" % README_CHARS if cut else "")})
    try:
        lf = get(f"https://api.github.com/repos/{repo}/license")
        out.append({"source": lf["html_url"], "fetched_at": at,
                    "text": base64.b64decode(lf["content"]).decode("utf-8", "replace")[:1500]})
    except Exception as e:  # no LICENSE file is evidence too
        out.append({"source": f"https://api.github.com/repos/{repo}/license", "fetched_at": at, "text": f"No license file found ({e})."})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=blind.EVAL_SEED)
    a = ap.parse_args()
    q01 = next(json.loads(line)["question"] for line in (ROOT / "eval/results/blind/l1-A/l1-batch.jsonl").open()
               if json.loads(line)["question"]["id"] == "q01")
    seeds = blind.seed_record(a.seed, "l1-c6:q01")
    order = list(range(len(CANDIDATES)))
    random.Random(seeds["use_seed"]).shuffle(order)
    a.out.mkdir(parents=True, exist_ok=True)
    items, key, rows = [], [], []
    for n, i in enumerate(order, 1):
        tool, repo, src = CANDIDATES[i]
        iid = f"C6-L1-{n:04d}"
        ev = evidence(repo)
        items.append({"item_id": iid, "question": q01, "pick": {"tool": tool, "install": None, "kind": "tool"}, "evidence": ev})
        key.append({"item_id": iid, "tool": tool, "repo": repo, "found_by": src})
        rows.append({"item_id": iid, "question": "q01", "pick": tool, "evidence": " ".join(e["source"] for e in ev[1:]),
                     "checks": " | ".join(q01["l1_checks"]), "overall": "", "notes": ""})
    batch = a.out / "l1-batch.jsonl"
    batch.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items), encoding="utf-8")
    keyf = a.out / "l1-items-key.json"
    keyf.write_text(json.dumps({"seeds": seeds, "items": key}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (a.out / "l1-form.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("batch", blind.sha256_bytes(batch.read_bytes())[:8], "key", blind.sha256_bytes(keyf.read_bytes())[:8], len(items), "items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
