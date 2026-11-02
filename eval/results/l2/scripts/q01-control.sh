#!/bin/bash
# L2 for q01 (eval/fixtures/q01/README.md sections 4-5), run 1, control: the answer's steps verbatim.
# Environment = q01 calibration step 1 (pinned Node.js and the three agent CLIs, eval/fixtures/PINS.md).
set -u
FIX=$F/q01; ST=/opt/eval/state; SRV=$FIX/server/fixture_mcp_server.py
mkdir -p "$ST" /work/proj "$OUT"
pin() { python3 -c "import json,sys; i={x['id']:x for x in json.load(open('$F/pins.json'))['items']}[sys.argv[1]]; print(i[sys.argv[2]])" "$1" "$2"; }
NODE_URL=$(pin nodejs url); NODE_SHA=$(pin nodejs verified_sha256); NODE_VER=$(pin nodejs version)
curl -fsSL -o /tmp/node.tar.xz "$NODE_URL" && echo "$NODE_SHA  /tmp/node.tar.xz" | sha256sum -c - || exit 1
python3 -c "import tarfile; tarfile.open('/tmp/node.tar.xz').extractall('/usr/local', filter='tar')" || exit 1
mv "/usr/local/node-$NODE_VER-linux-x64" /usr/local/node || exit 1
export PATH=/usr/local/node/bin:$PATH
apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libatomic1 > /dev/null || exit 1
npm install -g --no-fund --no-audit "@anthropic-ai/claude-code@$(pin claude-code version)" \
  "@openai/codex@$(pin codex-cli version)" "@google/gemini-cli@$(pin gemini-cli version)" > "$OUT/env-npm.txt" 2>&1 || exit 1
{ node --version; claude --version; codex --version; gemini --version; } > "$OUT/env-versions.txt" 2>&1
python3 "$FIX/server/selftest.py" > "$OUT/env-selftest.txt" 2>&1; tail -1 "$OUT/env-selftest.txt"
grep -q "RESULT PASS" "$OUT/env-selftest.txt" || { echo "environment problem: selftest"; exit 1; }
git -C /work/proj init -q
python3 "$FIX/seed/seed_configs.py" seed --home "$HOME" --project /work/proj --fixture "$FIX" --state "$ST/q01-seeded.json" > "$OUT/seed.txt" 2>&1
echo "seed exit $?"
cd /work/proj
# item 1: install lines verbatim (not traced; downloads allowed)
inst() { n=$1; shift; echo "== install $n: $*"; bash -c "$*" > "$OUT/install-$n.txt" 2>&1 < /dev/null; rc=$?
         echo "install $n exit $rc" | tee -a "$OUT/steps.txt"; tail -4 "$OUT/install-$n.txt"; return $rc; }
# items 2 and 4: the answer's init/import, add and sync lines, each traced
eg() { n=$1; shift; echo "== step $n: $*"; python3 "$SHARED/egress.py" run --out "$ST/q01-egress" --label "$n" --cwd /work/proj --timeout 300 --sh "$*" < /dev/null
       rc=$?; echo "step $n exit $rc" | tee -a "$OUT/steps.txt"; tail -4 "$ST/q01-egress/$n.stdout" "$ST/q01-egress/$n.stderr" 2>/dev/null; }
finish() {
  python3 "$FIX/seed/seed_configs.py" check --state "$ST/q01-seeded.json" --report "$ST/q01-check.json" > "$OUT/item2-check.txt" 2>&1
  echo "item 2 check exit $?: $(tail -1 "$OUT/item2-check.txt")" | tee -a "$OUT/steps.txt"
  for a in claude codex gemini; do
    python3 "$SHARED/egress.py" run --out "$ST/q01-list" --label "$a" --block-network --cwd /work/proj \
      --sh "env -i HOME=\"$HOME\" PATH=\"$PATH\" timeout 120 $a mcp list" > /dev/null 2>&1
    echo "item 3 $a list exit $? fixture-echo=$(grep -F -w -c fixture-echo "$ST/q01-list/$a.stdout" "$ST/q01-list/$a.stderr" | awk -F: '{s+=$2} END{print s+0}')" | tee -a "$OUT/steps.txt"
  done
  python3 "$SHARED/egress.py" stop --out "$ST/q01-egress" > /dev/null 2>&1
  python3 "$SHARED/egress.py" report --out "$ST/q01-egress" --json "$ST/q01-egress.json" > "$OUT/item4-report.txt" 2>&1
  echo "item 4 egress report exit $?: $(tail -1 "$OUT/item4-report.txt")" | tee -a "$OUT/steps.txt"
}
save() { for f in "$HOME/.claude.json" /work/proj/.mcp.json "$HOME/.codex/config.toml" /work/proj/.codex/config.toml \
                  "$HOME/.gemini/settings.json" /work/proj/.gemini/settings.json; do
           [ -f "$f" ] && cp "$f" "$OUT/final-$(echo "$f" | tr '/' '_')"; done
         cp -r "$ST" "$OUT/state" 2>/dev/null; echo "== done"; cat "$OUT/steps.txt"; }

inst 1 'npm install -g sync-agents-settings'
# First run, as the answer lists it, then "each time you add a server: claude mcp add ..., then run the two sync
# commands again". The placeholder is the fixture server (README section 3); scope left at its default.
eg 01 'sync-agents list'
eg 02 'sync-agents diff --target gemini codex'
eg 03 'sync-agents sync --target gemini --dry-run'
eg 04 'sync-agents sync --target codex --dry-run'
eg 05 'sync-agents sync --target gemini'
eg 06 'sync-agents sync --target codex'
eg 07 'sync-agents doctor --target gemini codex'
eg 08 "claude mcp add fixture-echo -- python3 $SRV"
eg 09 'sync-agents sync --target gemini'
eg 10 'sync-agents sync --target codex'
finish
save
