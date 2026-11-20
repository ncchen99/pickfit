"""Move records filed under the old catch-alls into the subject category CATEGORY_GUIDE puts them in (11/20).

The five subject categories (infra_devops, security_net, data_db, productivity_docs, media_files) were added on
2026-11-15; records extracted before that sat in `other` or `dev_cli`. MOVES lists, by hand, only the records the
guide places without argument (pickfit/schema.py CATEGORY_GUIDE, first that fits): Kubernetes and system monitors,
JSON/CSV/SQL tools and database clients, network diagnostics and encryption, notes and diagrams, media conversion and
editing, PDF tools and file transfer. Players, viewers, screen recorders, AI tools with a subject, MCP servers and
anything borderline stay where they are.

Per record it changes `category`, re-dates the `/category` evidence as a rule (method "rule", model none: the move is
this table's, not the model that first read the README) and sets `updated_at`. Scores, security, capabilities,
verification, slug (so /tool/<slug>) and every other field are kept byte for byte. A record whose category is no
longer the expected `from` is left alone and reported. No model call, no network.

Popularity: dev_cli has its own popularity references; `other` and the subject categories share the pooled ones (R8).
Scores are not recomputed here; the next `pickfit score --refresh` moves the popularity, and so the treasure value, of
the records that leave dev_cli. Run it right after, as `--refresh` below does.

    uv run python scripts/reclassify_categories.py --dry-run
    uv run python scripts/reclassify_categories.py && uv run pickfit score --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# slug -> (from, to). Grouped by target; reviewed one by one against the record's summary on 11/20.
MOVES: dict[str, tuple[str, str]] = {
    # infra_devops: containers, Kubernetes, system monitoring
    "k9s": ("dev_cli", "infra_devops"),
    "kx": ("dev_cli", "infra_devops"),
    "k8shark": ("dev_cli", "infra_devops"),
    "dive": ("dev_cli", "infra_devops"),
    "bottom": ("dev_cli", "infra_devops"),
    "btop": ("dev_cli", "infra_devops"),
    "hw-smi": ("dev_cli", "infra_devops"),
    "system-monitoring-center": ("other", "infra_devops"),
    "iglance": ("other", "infra_devops"),
    "stats": ("other", "infra_devops"),
    "mac-performance-monitor": ("other", "infra_devops"),
    # security_net: network diagnostics, encryption, secrets and vulnerability scanning
    "bandwhich": ("dev_cli", "security_net"),
    "dog": ("dev_cli", "security_net"),
    "nerva": ("dev_cli", "security_net"),
    "subnetlens": ("dev_cli", "security_net"),
    "wtfi2": ("dev_cli", "security_net"),
    "nadzoring": ("dev_cli", "security_net"),
    "julius": ("dev_cli", "security_net"),
    "mcp-audit": ("dev_cli", "security_net"),
    "vulners-cli": ("dev_cli", "security_net"),
    "nox": ("dev_cli", "security_net"),
    "gpgfrontend": ("other", "security_net"),
    "keepassxc": ("other", "security_net"),
    "revelation": ("other", "security_net"),
    "clients": ("other", "security_net"),
    "lulu": ("other", "security_net"),
    "encrypt-a-lotta": ("other", "security_net"),
    "xipher": ("other", "security_net"),
    # data_db: SQL engines, database clients, JSON/CSV/log tools
    "jq": ("dev_cli", "data_db"),
    "yq": ("dev_cli", "data_db"),
    "miller": ("dev_cli", "data_db"),
    "visidata": ("dev_cli", "data_db"),
    "harlequin": ("dev_cli", "data_db"),
    "lazydb": ("dev_cli", "data_db"),
    "masume": ("dev_cli", "data_db"),
    "sqlmux": ("dev_cli", "data_db"),
    "agent-database-cli": ("dev_cli", "data_db"),
    "llmschema": ("dev_cli", "data_db"),
    "duckdb-web-shell": ("other", "data_db"),
    "tabularis": ("other", "data_db"),
    "dlt-viewer": ("other", "data_db"),
    # productivity_docs: notes, knowledge bases, whiteboards and diagrams, document conversion
    "gote": ("dev_cli", "productivity_docs"),
    "excalidraw-cli": ("dev_cli", "productivity_docs"),
    "marker": ("dev_cli", "productivity_docs"),
    "appflowy": ("other", "productivity_docs"),
    "joplin": ("other", "productivity_docs"),
    "memos": ("other", "productivity_docs"),
    "folio": ("other", "productivity_docs"),
    "lemma": ("other", "productivity_docs"),
    "collaborative-whiteboard": ("other", "productivity_docs"),
    "pardus-pen": ("other", "productivity_docs"),
    "pdf-to-epub": ("other", "productivity_docs"),
    # media_files: media conversion and editing, image compression, PDF tools, file transfer
    "audacity": ("other", "media_files"),
    "yadaw": ("other", "media_files"),
    "handbrake": ("other", "media_files"),
    "lossless-cut": ("other", "media_files"),
    "flacon": ("other", "media_files"),
    "gifski": ("other", "media_files"),
    "imageflow": ("other", "media_files"),
    "converseen": ("other", "media_files"),
    "optipress": ("other", "media_files"),
    "image-tools": ("other", "media_files"),
    "supmover": ("other", "media_files"),
    "free-online-tools-for-video-audio-pdfs-images-and-ai": ("other", "media_files"),
    "stirling-pdf": ("other", "media_files"),
    "pdfkind": ("other", "media_files"),
    "djpdf": ("other", "media_files"),
    "word-sys-pdf-editor": ("other", "media_files"),
    "localsend": ("other", "media_files"),
    "transmission": ("other", "media_files"),
    "biglybt": ("other", "media_files"),
}


def reclassify(raw: dict[str, Any], to: str, now: str) -> dict[str, Any]:
    """The record with its category moved: category, the /category evidence's provenance, updated_at. Pure."""
    out = dict(raw)
    out["category"] = to
    out["evidence"] = [({**e, "method": "rule", "model": None, "checked_at": now} if e.get("field") == "/category"
                        else e) for e in raw.get("evidence") or []]
    out["updated_at"] = now
    return out


def plan(data_dir: Path) -> tuple[list[tuple[str, str, str]], dict[str, str]]:
    """(slug, from, to) for each record to move now, and why the others are skipped."""
    moves, skipped = [], {}
    for slug, (frm, to) in MOVES.items():
        path = data_dir / f"{slug}.json"
        if not path.exists():
            skipped[slug] = "no such record"
            continue
        current = json.loads(path.read_text(encoding="utf-8")).get("category")
        if current == to:
            skipped[slug] = f"already {to}"
        elif current != frm:
            skipped[slug] = f"is {current}, expected {frm}: left alone"
        else:
            moves.append((slug, frm, to))
    return moves, skipped


def counts(data_dir: Path) -> Counter[str]:
    return Counter(json.loads(p.read_text(encoding="utf-8")).get("category") for p in sorted(data_dir.glob("*.json"))
                   if json.loads(p.read_text(encoding="utf-8")).get("status") == "listed")


def apply(data_dir: Path, moves: list[tuple[str, str, str]], now: str) -> None:
    from pickfit.schema import SoftwareRecord

    for slug, _frm, to in moves:
        path = data_dir / f"{slug}.json"
        new = reclassify(json.loads(path.read_text(encoding="utf-8")), to, now)
        SoftwareRecord.model_validate(new)  # refuse before writing anything the schema would not take
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-dir", type=Path, default=ROOT / "data" / "software")
    p.add_argument("--dry-run", action="store_true", help="print the moves and the counts; write nothing")
    p.add_argument("--now", default=None, help="updated_at to stamp (ISO; default: now in Taipei)")
    args = p.parse_args(argv)
    from pickfit.ledger import taipei_now

    now = args.now or taipei_now().isoformat(timespec="seconds")
    before = counts(args.data_dir)
    moves, skipped = plan(args.data_dir)
    after = before.copy()
    for _slug, frm, to in moves:
        after[frm] -= 1
        after[to] += 1
    if not args.dry_run:
        apply(args.data_dir, moves, now)
    by_target: dict[str, list[str]] = {}
    for slug, frm, to in moves:
        by_target.setdefault(to, []).append(f"{slug} ({frm})")
    print(json.dumps({"dry_run": args.dry_run, "moved": len(moves), "skipped": skipped,
                      "listed_before": dict(sorted(before.items())), "listed_after": dict(sorted(after.items())),
                      "by_target": by_target}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
