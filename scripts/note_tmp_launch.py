"""Add a fixed note pitfall to passed runs that installed into /tmp or launch from files there ($0).

/tmp is cleared on reboot, so an install guide built from such a run would point the user's MCP
client at paths that vanish. The level stands (an unmodified clone or release counts wherever it
sits); only this note and the record's updated_at change.

    uv run python scripts/note_tmp_launch.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pickfit.ledger import taipei_now
from pickfit.schema import SoftwareRecord

DATA = Path(__file__).resolve().parents[1] / "data" / "software"
INSTALLED = {
    "readme_said": "The sandbox run installed it under /tmp, and its launch command or wrapper points there.",
    "actually_needed": "The run installed into /tmp; install into a permanent directory and point the MCP "
                       "client's launch command there.",
    "kind": "note",
}
LAUNCH_FILES = {
    "readme_said": "The sandbox run's launch command points at files it created in /tmp for the test.",
    "actually_needed": "Point the MCP client's launch command at the user's own files in a permanent "
                       "directory; /tmp is cleared on reboot.",
    "kind": "note",
}
# slug -> note, from a scan of every passed run's launch command and wrapper scripts (2026-11-01).
NOTES = {"flowstate": INSTALLED, "kotlin-lib-mcp": INSTALLED, "ctxtual": LAUNCH_FILES,
         "grooveseek": LAUNCH_FILES, "infrawise": LAUNCH_FILES, "lore": LAUNCH_FILES}


def main() -> int:
    now = taipei_now().isoformat(timespec="seconds")
    for slug, note in NOTES.items():
        path = DATA / f"{slug}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        run_ids = {guide["run_id"] for guide in data["install"].values() if guide and guide.get("run_id")}
        changed = False
        for run in data["verification"]["runs"]:
            if run["id"] in run_ids and note not in run["pitfalls"]:
                run["pitfalls"].append(dict(note))
                changed = True
        if changed:
            data["updated_at"] = now
            SoftwareRecord.model_validate(data)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{slug}: {'noted' if changed else 'already noted'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
