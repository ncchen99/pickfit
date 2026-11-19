"""Recompute every record's scores with the current formula, offline, and compare (docs/proposals/scoring.md).

Reads data/software (read only), runs pickfit.score.refresh_scores on a copy of each record (scores of a refreshable
formula, b3.v6 among them, move to the current one with no call) and writes to --out, never to the records:

- changes.md: the records whose quality or treasure changed, treasures first, then by the old quality (the layout
  of docs/security-score-changes.md);
- summary.json: the quality distribution before and after, how many records sit at exactly 69.0 and 79.0, the
  treasures gained and lost, and R9: how many treasures each option of schema.UNCHECKED_CAN_BE_TREASURE keeps;
- rows.json: every record's before and after.

With the default settings (docs/proposals/coverage.md) no quality total moves; popularity of "other" and the subject
categories does (R8). The other treasure and cap rules are compared by `pickfit coverage rules`.

The security rescan is not run here. --assume vulnerable=exposed (or conditional, present_unreachable, ...) gives
every record whose sec.v1 check is vulnerable that assessment level, in memory only, to see what the settings do
once records are assessed (sec.v2, docs/proposals/security.md). Without --assume every record is validated after
the recompute, as `pickfit score --refresh` would write it.

    uv run python scripts/recompute_scores.py --data-dir data/software --out runs/recompute
    uv run python scripts/recompute_scores.py --out runs/recompute-exposed --assume vulnerable=exposed
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit import schema
from pickfit.ledger import TAIPEI
from pickfit.score import POPULARITY_REFS, refresh_scores
from pickfit.schema import SoftwareRecord

# The categories b3.v6 scored against dev_cli's popularity refs.
OWN_REFS_BEFORE = ("dev_cli", "local_ai", "mcp_server")


@contextmanager
def unchecked_treasure(allowed: bool):
    """schema.UNCHECKED_CAN_BE_TREASURE set to `allowed` for the duration (R9)."""
    before = schema.UNCHECKED_CAN_BE_TREASURE
    schema.UNCHECKED_CAN_BE_TREASURE = allowed
    try:
        yield
    finally:
        schema.UNCHECKED_CAN_BE_TREASURE = before


def _total(scores: dict[str, Any] | None) -> float | None:
    return scores["quality"]["total"] if scores else None


def _treasure(scores: dict[str, Any] | None) -> bool:
    return bool(scores and scores["treasure"]["is_treasure"])


def reasons(record: dict[str, Any], before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str]:
    """Which b3.v7 rules moved the record: R8 refs, R5 security (a setting switched on, or an assumed level)."""
    if not after:
        return []
    out = []
    if before and record["category"] not in OWN_REFS_BEFORE and after["popularity"]["score"] != before["popularity"]["score"]:
        out.append("R8 熱門度基準")
    effect = after["quality"].get("security") or {}
    if effect.get("effect") in ("deducted", "unlisted", "capped") or after["treasure"].get("blocked_by"):
        out.append(f"R5 安全 {effect.get('level')}")
    return out


def recompute(data_dir: Path, now: datetime, *, assume: dict[str, str] | None = None,
              validate: bool = True) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        before = copy.deepcopy(raw.get("scores"))
        data = copy.deepcopy(raw)
        status = (data.get("security") or {}).get("status")
        if assume and status in assume:
            data["security"]["assessment"] = {"level": assume[status]}
        refresh_scores(data, now)
        after = data.get("scores")
        error = None
        if validate and not assume:
            try:
                SoftwareRecord.model_validate(data)
            except ValueError as err:
                error = str(err).splitlines()[0][:200]
        rows.append({
            "slug": raw["slug"], "kind": raw["kind"], "category": raw["category"],
            "security": data.get("security") and (data["security"].get("assessment") or {}).get("level", status),
            "formula_before": before and before["formula_version"], "formula_after": after and after["formula_version"],
            "quality_before": _total(before), "quality_after": _total(after),
            "raw_after": after and after["quality"].get("raw_total"),
            "popularity_before": before and before["popularity"]["score"],
            "popularity_after": after and after["popularity"]["score"],
            "treasure_before": _treasure(before), "treasure_after": _treasure(after),
            "blocked_by": after and after["treasure"].get("blocked_by"),
            "rubric_model": ((after or {}).get("docs_rubric") or {}).get("model"),
            "reasons": reasons(data, before, after), "error": error,
        })
    return rows


def histogram(values: list[float]) -> dict[str, int]:
    bins = Counter(f"{int(v // 5 * 5):>3}-{int(v // 5 * 5) + 4}" if v < 100 else "100" for v in values)
    return dict(sorted(bins.items()))


def distribution(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = sorted(r[key] for r in rows if r[key] is not None)
    ties = Counter(values)
    pct = {p: values[min(len(values) - 1, int(len(values) * p / 100))] for p in (10, 25, 50, 75, 90)} if values else {}
    return {"scored": len(values), "at_69.0": ties.get(69.0, 0), "at_79.0": ties.get(79.0, 0),
            "distinct": len(ties), "largest_ties": ties.most_common(5), "percentiles": pct,
            "histogram": histogram(values)}


def summary(rows: list[dict[str, Any]], rows_no_unchecked: list[dict[str, Any]]) -> dict[str, Any]:
    gained = [r["slug"] for r in rows if r["treasure_after"] and not r["treasure_before"]]
    lost = [r["slug"] for r in rows if r["treasure_before"] and not r["treasure_after"]]
    after = [r for r in rows if r["treasure_after"]]
    option1 = [r for r in rows_no_unchecked if r["treasure_after"]]
    lost_option1 = sorted({r["slug"] for r in after} - {r["slug"] for r in option1})
    return {
        "records": len(rows),
        "formula_after": dict(Counter(r["formula_after"] for r in rows)),
        "quality_before": distribution(rows, "quality_before"),
        "quality_after": distribution(rows, "quality_after"),
        "raw_total_after": distribution(rows, "raw_after"),
        "treasures": {"before": sum(r["treasure_before"] for r in rows), "after": len(after),
                      "gained": len(gained), "lost": len(lost), "gained_slugs": gained, "lost_slugs": lost,
                      "after_by_security": dict(Counter(r["security"] for r in after))},
        "R9": {"option_2_keep_unchecked (default)": len(after), "option_1_no_unchecked": len(option1),
               "treasures_option_1_takes_away": len(lost_option1), "slugs": lost_option1,
               "before_b3v7_unchecked_treasures": sum(1 for r in rows if r["treasure_before"]
                                                      and r["security"] in ("unchecked", None, "partial"))},
        "rubrics_by_model": dict(Counter(r["rubric_model"] for r in rows)),
        "validation_errors": [f"{r['slug']}: {r['error']}" for r in rows if r["error"]],
    }


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def changes_table(rows: list[dict[str, Any]]) -> str:
    changed = [r for r in rows if r["quality_before"] != r["quality_after"] or r["treasure_before"] != r["treasure_after"]]
    changed.sort(key=lambda r: (not (r["treasure_before"] or r["treasure_after"]), -(r["quality_before"] or 0), r["slug"]))
    lines = [f"共 {len(changed)} 款軟體的品質分數或寶藏有變化；寶藏在前，再依原本的分數由高到低排。", "",
             "| 軟體 | 類型 | 類別 | 品質 前 → 後 | 原始總分 | 熱門度 前 → 後 | 寶藏 | 原因 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in changed:
        treasure = ("是" if r["treasure_before"] else "否") + " → " + (
            ("**是**" if not r["treasure_before"] else "是") if r["treasure_after"]
            else ("**否**" if r["treasure_before"] else "否"))
        lines.append(f"| {r['slug']} | {r['kind']} | {r['category']} | {_fmt(r['quality_before'])} → "
                     f"{_fmt(r['quality_after'])} | {_fmt(r['raw_after'])} | {_fmt(r['popularity_before'])} → "
                     f"{_fmt(r['popularity_after'])} | {treasure} | {'；'.join(r['reasons']) or '—'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data/software")
    parser.add_argument("--out", default="runs/recompute", help="where to write (gitignored by default)")
    parser.add_argument("--assume", action="append", default=[], metavar="STATUS=LEVEL",
                        help="give records whose sec.v1 status is STATUS this assessment level, in memory only")
    parser.add_argument("--now", default="2026-11-19T12:00:00+08:00", help="computed_at of the recomputed scores")
    args = parser.parse_args(argv)
    assume = dict(item.split("=", 1) for item in args.assume) or None
    if assume and not set(assume.values()) <= set(schema.SECURITY_LEVELS):
        parser.error(f"levels are {', '.join(schema.SECURITY_LEVELS)}")
    now = datetime.fromisoformat(args.now).astimezone(TAIPEI)
    data_dir, out = Path(args.data_dir), Path(args.out)
    with unchecked_treasure(True):
        rows = recompute(data_dir, now, assume=assume)
    with unchecked_treasure(False):
        rows_option1 = recompute(data_dir, now, assume=assume, validate=False)
    out.mkdir(parents=True, exist_ok=True)
    result = summary(rows, rows_option1) | {"assume": assume, "popularity_refs": sorted(POPULARITY_REFS)}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "changes.md").write_text(changes_table(rows), encoding="utf-8")
    brief = {k: result[k] for k in ("records", "formula_after", "treasures", "R9")}
    brief["treasures"] = {k: v for k, v in brief["treasures"].items() if not k.endswith("_slugs")}
    brief["R9"] = {k: v for k, v in brief["R9"].items() if k != "slugs"}
    brief["at_69_79"] = {when: {k: result[f"quality_{when}"][k] for k in ("at_69.0", "at_79.0", "distinct")}
                         for when in ("before", "after")}
    brief["validation_errors"] = len(result["validation_errors"])
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0 if not result["validation_errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
