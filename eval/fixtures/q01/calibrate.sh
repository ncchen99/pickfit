#!/bin/bash
# q01 calibration steps 1, 3, 4 and 8 (calibration.md), in a fresh dev-image sandbox.
# Run through eval/runner/calibrate_box.py with --fixtures q01 _shared pins.json; F, SHARED, OUT are set.
# Installs the pinned Node.js and the three agent CLIs (versions and sha256 in eval/fixtures/PINS.md),
# seeds every config location, and runs each agent's own `mcp list` with the network blocked
# (egress.py --block-network), first without and then with the fixture server added.
set -u
FIX=$F/q01
ST=/opt/eval/state
mkdir -p "$ST" /work/proj "$OUT"
pin() { python3 -c "import json,sys; i={x['id']:x for x in json.load(open('$F/pins.json'))['items']}[sys.argv[1]]; print(i[sys.argv[2]])" "$1" "$2"; }
log() { echo "== $*"; }

log "step 1: Node.js and the agent CLIs"
NODE_URL=$(pin nodejs url); NODE_SHA=$(pin nodejs verified_sha256); NODE_VER=$(pin nodejs version)
curl -fsSL -o /tmp/node.tar.xz "$NODE_URL" && echo "$NODE_SHA  /tmp/node.tar.xz" | sha256sum -c - || exit 1
# The dev image has no xz; Python's tarfile reads .tar.xz.
python3 -c "import tarfile; tarfile.open('/tmp/node.tar.xz').extractall('/usr/local', filter='tar')" || exit 1
mv "/usr/local/node-$NODE_VER-linux-x64" /usr/local/node || exit 1
export PATH=/usr/local/node/bin:$PATH
# Node's official Linux build needs libatomic1, which the minimal image lacks. The user of q01 already
# runs these three agents, so their runtime is part of the pre-installed setup, like the agents.
apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libatomic1 > /dev/null || exit 1
dpkg-query -W libatomic1 | tee "$OUT/libatomic1.txt"
node --version || exit 1
npm install -g --no-fund --no-audit "@anthropic-ai/claude-code@$(pin claude-code version)" \
  "@openai/codex@$(pin codex-cli version)" "@google/gemini-cli@$(pin gemini-cli version)" > "$OUT/npm-install.txt" 2>&1
rc=$?; echo "npm install exit $rc"; [ $rc -eq 0 ] || { tail -20 "$OUT/npm-install.txt"; exit 1; }
{ node --version; npm --version; claude --version; codex --version; gemini --version; python3 --version; strace -V | head -1; } > "$OUT/versions.txt" 2>&1
cat "$OUT/versions.txt"
npm ls -g --json > "$OUT/npm-ls.json" 2>/dev/null
for a in claude codex gemini; do $a mcp --help > "$OUT/help-$a-mcp.txt" 2>&1; $a mcp add --help > "$OUT/help-$a-mcp-add.txt" 2>&1; done

log "step 8: fixture server selftest"
python3 "$FIX/server/selftest.py" > "$OUT/server-selftest.txt" 2>&1; echo "selftest exit $?"; tail -1 "$OUT/server-selftest.txt"

log "README section 5 steps 1-3: project and seeded configs"
git -C /work/proj init -q
python3 "$FIX/seed/seed_configs.py" seed --home "$HOME" --project /work/proj --fixture "$FIX" --state "$ST/q01-seeded.json" > "$OUT/seed.txt" 2>&1
echo "seed exit $?"
snap() { for f in "$HOME/.claude.json" /work/proj/.mcp.json "$HOME/.codex/config.toml" /work/proj/.codex/config.toml \
                 "$HOME/.gemini/settings.json" /work/proj/.gemini/settings.json; do
           [ -f "$f" ] && sha256sum "$f" || echo "missing $f"; done; }
snap > "$OUT/configs-after-seed.txt"

# Each list runs with the network blocked, without login: env -i keeps only HOME and PATH.
list_all() {  # $1 = label prefix
  for a in claude codex gemini; do
    t0=$(date +%s.%N)
    python3 "$SHARED/egress.py" run --out "$OUT/eg-$1" --label "$a" --block-network --cwd /work/proj \
      --sh "env -i HOME=\"$HOME\" PATH=\"$PATH\" timeout 120 $a mcp list" > /dev/null 2>&1
    rc=$?
    t1=$(date +%s.%N)
    out="$OUT/eg-$1/$a.stdout"; err="$OUT/eg-$1/$a.stderr"
    login=$(grep -ciE "log ?in|sign ?in|authenticat|api key" "$out" "$err" | awk -F: '{s+=$2} END{print s+0}')
    echo "$1 $a exit=$rc seconds=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.1f", b-a}') login_lines=$login fixture-echo=$(grep -F -w -c fixture-echo "$out" "$err" | awk -F: '{s+=$2} END{print s+0}') keep-existing=$(grep -F -w -c keep-existing "$out" "$err" | awk -F: '{s+=$2} END{print s+0}')"
  done
}

log "step 3: negative control (nothing added)"
list_all neg | tee "$OUT/step3.txt"
python3 "$FIX/seed/seed_configs.py" check --state "$ST/q01-seeded.json" --report "$OUT/step3-check.json" > "$OUT/step3-check.txt" 2>&1
echo "check after lists: exit $?"; tail -1 "$OUT/step3-check.txt"
snap > "$OUT/configs-after-step3.txt"

log "step 4: positive control (each agent's own add, user scope)"
SRV="$FIX/server/fixture_mcp_server.py"
( cd /work/proj
  claude mcp add --scope user fixture-echo -- python3 "$SRV"; echo "claude add exit $?"
  codex mcp add fixture-echo -- python3 "$SRV"; echo "codex add exit $?"
  gemini mcp add -s user fixture-echo python3 "$SRV"; echo "gemini add exit $?" ) > "$OUT/step4-add.txt" 2>&1
cat "$OUT/step4-add.txt"
snap > "$OUT/configs-after-add.txt"
diff "$OUT/configs-after-step3.txt" "$OUT/configs-after-add.txt" > "$OUT/configs-changed-by-add.txt"
cat "$OUT/configs-changed-by-add.txt"
list_all pos | tee "$OUT/step4.txt"
for agent in claude-code codex-cli gemini-cli; do
  python3 "$FIX/seed/validate_shape.py" --agent "$agent" --state "$ST/q01-seeded.json" > "$OUT/step4-validate-$agent.txt" 2>&1
  echo "validate_shape $agent exit $? $(tail -1 "$OUT/step4-validate-$agent.txt")"
done
for f in "$HOME/.claude.json" "$HOME/.codex/config.toml" "$HOME/.gemini/settings.json"; do
  cp "$f" "$OUT/final-$(echo "$f" | tr / _)" 2>/dev/null
done
python3 "$SHARED/egress.py" report --out "$OUT/eg-pos" --json "$OUT/eg-pos-report.json" | tail -1
