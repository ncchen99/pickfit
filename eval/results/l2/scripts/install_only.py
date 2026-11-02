"""Write an L2 script that runs only an answer's install lines verbatim (C7: when they fail, the
question's other [L2] items fail without being run). Usage: install_only.py Q GROUP 'line1' 'line2' ..."""
import sys
from pathlib import Path

q, group, lines = sys.argv[1], sys.argv[2], sys.argv[3:]
here = Path(__file__).resolve().parent
lib = (here / "_lib.sh").read_text()
script = f"""#!/bin/bash
# L2 for {q}, run 1, {group}: the answer's install lines verbatim in one shell (dev image).
set -u
mkdir -p "$OUT" /work/{q}
# --- _lib.sh (inlined) ---
{lib}# --- end _lib.sh ---
cd /work/{q}
cat > /tmp/install.lines <<'LINES'
""" + "\n".join(lines) + f"""
LINES
run_lines install /tmp/install.lines
all_ok install && echo "item 1: every install line exit 0" | tee -a "$OUT/steps.txt" || echo "item 1 FAIL (an install line failed)" | tee -a "$OUT/steps.txt"
for c in brew npm node cargo go pipx uv docker; do echo "image has $c: $(command -v $c || echo no)"; done | tee -a "$OUT/steps.txt"
echo "== done"; cat "$OUT/steps.txt"
"""
(here / f"{q}-{group}.sh").write_text(script)
