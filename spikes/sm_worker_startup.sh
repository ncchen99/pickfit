#!/usr/bin/env bash
# F 節 spike：把建置時產生的 JSON 索引「打包進 Worker」時，bundle 多大、啟動要多少 CPU。
# 只在本機跑 wrangler（dry-run 與 check startup），不登入、不部署、不需要金鑰。
# 用法：bash spikes/sm_worker_startup.sh [筆數，預設 3000]
set -euo pipefail
N="${1:-3000}"
WRANGLER="npx --yes wrangler@4.153.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

node "$HERE/sm_index_bench.mjs" --n "$N" --out "$WORK/index.json" > /dev/null
COUNT="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).cards.length)' "$WORK/index.json")"
echo "index.json：$(wc -c < "$WORK/index.json") bytes（$COUNT 筆）"

cat > "$WORK/worker.mjs" <<'EOF'
import ix from "./index.json"; // 在 global scope 解析：算在啟動時間（上限 1 秒）
export default {
  async fetch(req) {
    const q = new URL(req.url).searchParams.get("q") ?? "";
    const terms = q.toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
    const score = new Float64Array(ix.cards.length);
    for (const t of terms) {
      const p = ix.postings[t]; if (!p) continue;
      for (let j = 0; j < p.length; j += 2) score[p[j]] += p[j + 1];
    }
    const top = [...score.keys()].filter((d) => score[d] > 0).sort((a, b) => score[b] - score[a]).slice(0, 25);
    return Response.json(top.map((d) => ix.cards[d].slug));
  },
};
EOF
cat > "$WORK/wrangler.toml" <<'EOF'
name = "sm-index-startup"
main = "worker.mjs"
compatibility_date = "2026-10-01"
EOF

cd "$WORK"
echo "--- wrangler deploy --dry-run"
$WRANGLER deploy --dry-run --outdir dist 2>&1 | grep -E "Total Upload|error|Error" || true
echo "--- wrangler check startup"
$WRANGLER check startup --outfile startup.cpuprofile 2>&1 | grep -v -i "proxy" | tail -4 || true
if [ -f startup.cpuprofile ]; then
  node -e '
    const p = JSON.parse(require("fs").readFileSync("startup.cpuprofile", "utf8"));
    const total = (p.endTime - p.startTime) / 1000;
    const byId = new Map(p.nodes.map((n) => [n.id, n]));
    const self = new Map();
    p.samples.forEach((id, i) => { const n = byId.get(id); const k = n.callFrame.functionName || "(anonymous)"; self.set(k, (self.get(k) ?? 0) + (p.timeDeltas[i] ?? 0) / 1000); });
    const top = [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => `${k} ${v.toFixed(1)}ms`).join("; ");
    console.log(`profile 涵蓋 ${total.toFixed(1)} ms；self time 前 5：${top}`);
  '
fi
