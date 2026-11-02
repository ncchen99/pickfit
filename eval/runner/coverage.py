"""Post-hoc coverage check (README 9.1 F: after seeing the results; descriptive only, no model calls).

Questions in scope: those with an empty pickfit response (results/e-tags/empty-responses.json) plus those whose
run 1 E tag (Claude) is tool_error or not_in_data. Correct answers: every pick that passed L1 for that question in
any group and round (results/final/answers-l1.json), plus C6's for q01. Each is looked up in the current
data/software by repo (from the GitHub links in the answers that named it; case-insensitive, no trailing / or
.git), then by name or alias. Composite picks (tool + model) are split into their parts; built-in ways are noted.

  python3 eval/runner/coverage.py --out eval/results/final
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "eval" / "results"
GH = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
LEVELS_INSTALL_UP = {"install", "service", "function", "inference"}
# tools the answers named without a GitHub link: their canonical repo (checked with the GitHub API, 2026-11-02)
REPO_OVERRIDES = {"git-spice": "abhinav/git-spice", "@ivotoby/openapi-mcp-server": "ivo-toby/mcp-openapi-server",
                  "openapi-mcp-generator": "harsha-iiiv/openapi-mcp-generator", "Bruno": "usebruno/bruno",
                  "Hurl": "Orange-OpenSource/hurl", "ollmcp": "jonigl/mcp-client-for-ollama",
                  "faster-whisper": "SYSTRAN/faster-whisper", "OpenCC": "BYVoid/OpenCC", "Ollama": "ollama/ollama",
                  "mdpo": "mondeja/mdpo", "Atlas": "ariga/atlas", "Beads": "gastownhall/beads",
                  "llama.cpp": "ggml-org/llama.cpp", "llama.cpp llama-server": "ggml-org/llama.cpp"}
NOT_SOFTWARE = re.compile(r"(EuroLLM|TranslateGemma|Qwen[\d.]|Llama-\d|Gemma \d|glue script)")  # models and the answers' own scripts
FALSE_NAME_MATCHES = {"Atlas"}  # pickfit's 'atlas' is Atlas-Inf/atlas (LLM engine), not ariga/atlas
DISCOVERY_PUSHED_SINCE = "2026-10-19"  # the well-known run's pushed:>= (docs/discovery/github-well-known-v1.json)


_GH: dict[str, dict] = {}


def github(full: str) -> dict:
    """Repo facts from the GitHub API (through the gh CLI's login, so the anonymous rate limit does not apply)."""
    import subprocess
    if full not in _GH:
        r = subprocess.run(["gh", "api", f"repos/{full}"], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            _GH[full] = {"full_name": d["full_name"], "stars": d["stargazers_count"], "created_at": d["created_at"][:10], "pushed_at": d["pushed_at"][:10]}
        except (ValueError, KeyError):
            _GH[full] = {"error": (r.stderr or r.stdout)[:100]}
    return _GH[full]


def reasons(g: dict) -> list[str]:
    """Why discovery's rules would not pick it up (pickfit/discover/github.py: created this year, pushed in the last
    14 days, stars 5..300, or 301..5000 under github-well-known.v1)."""
    if "stars" not in g:
        return ["repo not found on GitHub"]
    out = []
    if g["stars"] > 5000:
        out.append("over 5000 stars")
    if g["created_at"] < "2026-01-01":
        out.append("created before 2026")
    if g["stars"] < 5:
        out.append("under 5 stars")
    if g["pushed_at"] < DISCOVERY_PUSHED_SINCE:
        out.append("not pushed in the 14 days before discovery")
    return out or ["inside the rules' ranges but not picked (topics, cap)"]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def repo_key(full: str) -> str:
    return re.sub(r"(\.git)?/*$", "", full.strip().lower())


def parts(name: str) -> list[str]:
    return [p.strip() for p in re.split(r"\s\+\s", re.sub(r"\s*\(.*?\)", "", name)) if p.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    records = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(str(ROOT / "data/software/*.json")))]
    wk = json.loads((ROOT / "docs/discovery/github-well-known-v1.json").read_text(encoding="utf-8"))
    wk_ids = {p["repo_id"] for p in wk["picked"]}
    by_repo, by_name = {}, {}
    for r in records:
        by_repo[repo_key((r.get("repo") or {}).get("full_name") or "")] = r
        for k in [r.get("slug"), r.get("name"), ((r.get("repo") or {}).get("full_name") or "").split("/")[-1]] + list(r.get("aliases") or []):
            if k:
                by_name.setdefault(norm(k), r)

    empty = json.loads((RES / "e-tags" / "empty-responses.json").read_text(encoding="utf-8"))
    tags = [json.loads(x) for x in (RES / "e-tags" / "claude-run1.jsonl").read_text(encoding="utf-8").splitlines()]
    scope: dict[str, list[str]] = {}
    for x in empty["rows"]:
        scope.setdefault(x["question"], []).append(f"empty response ({x['round']})")
    for t in tags:
        hit = {t["tag"]["primary"], *t["tag"]["secondary"]} & {"tool_error", "not_in_data"}
        if hit:
            scope.setdefault(t["question"], []).append("E: " + ", ".join(sorted(hit)))

    rows = json.loads((RES / "final" / "answers-l1.json").read_text(encoding="utf-8"))
    texts = {}
    for s in ("A", "B"):
        for line in (RES / "blind" / f"answers-{s}" / "answers.jsonl").read_text(encoding="utf-8").splitlines():
            x = json.loads(line)
            texts[x["answer_id"]] = x["text"]
    final = json.loads((RES / "final" / "results.json").read_text(encoding="utf-8"))
    c6 = {k["tool"]: k["repo"] for k in json.loads((RES / "blind" / "l1-C6" / "l1-items-key.json").read_text(encoding="utf-8"))["items"]}

    answers: dict[str, dict[str, set[str]]] = {}
    for r in rows:
        if r["question"] in scope and r["l1"] == "pass" and r["item_id"]:
            answers.setdefault(r["question"], {}).setdefault(r["pick"], set()).add(r["answer_id"])
    for t in final["c6"]["q01_candidates_passing"]:
        answers.setdefault("q01", {}).setdefault(t, set())

    out = []
    for q in sorted(scope):
        for pick, aids in sorted(answers.get(q, {}).items()):
            if pick.lower().startswith("built-in"):
                out.append({"question": q, "pick": pick, "part": pick, "repo": None, "found": None, "note": "built-in way, not a software record"})
                continue
            links = [m.group(1) + "/" + m.group(2) for aid in aids for m in GH.finditer(texts.get(aid, ""))]
            for part in parts(pick):
                if NOT_SOFTWARE.search(part):
                    out.append({"question": q, "pick": pick, "part": part, "repo": None, "found": None, "note": "a model or the answer's own script, not a software record"})
                    continue
                repo = None
                if pick in c6:
                    repo = c6[pick]
                elif part in REPO_OVERRIDES:
                    repo = REPO_OVERRIDES[part]
                else:  # the linked repo whose name is closest to this part
                    cands = sorted({repo_key(link) for link in links}, key=lambda rp: (norm(part) not in norm(rp.split("/")[-1]) and norm(rp.split("/")[-1]) not in norm(part), len(rp)))
                    good = [rp for rp in cands if norm(rp.split("/")[-1]) and (norm(rp.split("/")[-1]) in norm(part) or norm(part) in norm(rp.split("/")[-1]))]
                    repo = good[0] if good else None
                rec = by_repo.get(repo_key(repo)) if repo else None
                how = "repo" if rec else None
                if not rec and part not in FALSE_NAME_MATCHES:
                    rec = by_name.get(norm(part))
                    how = "name" if rec else None
                gh = github(repo) if repo else {}
                v = (rec or {}).get("verification") or {}
                out.append({"question": q, "pick": pick, "part": part, "repo": repo, "found": bool(rec), "matched_by": how,
                            "slug": (rec or {}).get("slug"), "record_repo": ((rec or {}).get("repo") or {}).get("full_name"),
                            "status": (rec or {}).get("status"), "level": v.get("level"),
                            "rule": ("github-well-known.v1" if (rec or {}).get("repo_id") in wk_ids else "earlier discovery") if rec else None,
                            "first_seen_at": (rec or {}).get("first_seen_at"), "github": gh,
                            "why_not": None if rec else (reasons(gh) if repo else ["no repo resolved"])})
    (a.out / "post-hoc-coverage.json").write_text(json.dumps({"scope": scope, "rows": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in out:
        print(x["question"], "|", x["part"][:30], "|", x["repo"], "|", x["found"], x.get("matched_by"), x.get("slug"), x.get("status"), x.get("level"), x.get("rule"), (x.get("github") or {}).get("stars"), x.get("why_not"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
