#!/usr/bin/env node
// F 節 spike：幾千筆時，「建置時產生的 JSON 索引 + 條件篩選 + BM25」夠不夠用。
//
// 量三件事：
//   1. 索引大小（原始、gzip）與 JSON.parse、查詢的時間（Node，當作 Workers 的粗略參考）
//   2. 條件篩選後剩多少候選
//   3. 召回：使用者原話直接查 vs 模型把需求改寫成關鍵字後再查（改寫是手寫的模擬，不是模型輸出）
//
// 資料：Homebrew formula API（約 8.7K 筆 CLI 套件；desc 很短、沒有 tags／use_cases，
//       所以這裡的召回是「下限」）。只在執行時下載到暫存目錄，不進 repo。
// 驗證狀態是依名稱雜湊產生的假資料，只用來量篩選比例。
//
// 用法：node spikes/sm_index_bench.mjs [--n 3000]   （不需要金鑰、不需要 npm install）

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const N_ARG = process.argv.indexOf("--n");
const SIZES = N_ARG > 0 ? [Number(process.argv[N_ARG + 1])] : [500, 3000, 0]; // 0 = 全部
const CACHE = join(tmpdir(), "pickfit-sm");
const SRC = "https://formulae.brew.sh/api/formula.json";

async function loadBrew() {
  mkdirSync(CACHE, { recursive: true });
  const f = join(CACHE, "formula.json");
  if (!existsSync(f)) {
    const r = await fetch(SRC);
    if (!r.ok) throw new Error(`download ${r.status}`);
    writeFileSync(f, Buffer.from(await r.arrayBuffer()));
  }
  return JSON.parse(readFileSync(f, "utf8"));
}

// ---- 建置時：Homebrew formula → 候選卡（只放配對需要的欄位） ----
const STATUS = ["verified", "verified", "verified", "verified", "partial", "partial", "failed", "failed", "unsupported_env", "not_run"];
function fakeStatus(name) {
  const h = createHash("sha1").update(name).digest()[0];
  return STATUS[h % STATUS.length];
}
function platforms(f) {
  const files = Object.keys(f?.bottle?.stable?.files ?? {});
  const p = new Set();
  for (const k of files) {
    if (k === "all") { p.add("macos"); p.add("linux"); }
    else if (k.includes("linux")) p.add("linux");
    else p.add("macos");
  }
  return [...p].sort();
}
function toCard(f) {
  return {
    slug: f.name,
    name: f.name,
    summary: f.desc ?? "",
    tags: [],                 // 真實資料由 Muse Spark 抽取時產生
    use_cases: [],
    platforms: platforms(f),
    pricing: "free",
    open_source: f.license ? true : null,
    license: f.license ?? null,
    processing: "unknown",
    verification: fakeStatus(f.name),
  };
}

// ---- BM25（k1=1.2, b=0.75），欄位加權用重複 token ----
const STOP = new Set("a an and the of for to in on with by from your you my me i is are it its that this as or be at into using use via like more".split(" "));
function tokens(s) {
  return (s.toLowerCase().match(/[a-z0-9]+(?:[.+][a-z0-9]+)*/g) ?? [])
    .flatMap((t) => (t.includes(".") ? [t, ...t.split(".")] : [t]))
    .filter((t) => !STOP.has(t))
    .map((t) => (t.length > 4 && t.endsWith("s") && !t.endsWith("ss") ? t.slice(0, -1) : t));
}
function docTokens(c) {
  const name = tokens(c.name.replace(/[-_]/g, " ") + " " + c.name);
  return [...name, ...name, ...name, ...tokens(c.summary), ...tokens(c.tags.join(" ")).flatMap((t) => [t, t]), ...tokens(c.use_cases.join(" "))];
}
function buildIndex(cards) {
  const postings = {};
  const dl = [];
  cards.forEach((c, i) => {
    const toks = docTokens(c);
    dl.push(toks.length);
    const tf = {};
    for (const t of toks) tf[t] = (tf[t] ?? 0) + 1;
    for (const [t, n] of Object.entries(tf)) (postings[t] ??= []).push(i, n);
  });
  const avgdl = dl.reduce((a, b) => a + b, 0) / dl.length;
  return { v: 1, cards, dl, avgdl, postings };
}
function search(ix, query, filter, k = 25) {
  const N = ix.cards.length;
  const allowed = ix.cards.map(filter);
  const score = new Float64Array(N);
  for (const t of new Set(tokens(query))) {
    const p = ix.postings[t];
    if (!p) continue;
    const df = p.length / 2;
    const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    for (let j = 0; j < p.length; j += 2) {
      const d = p[j], tf = p[j + 1];
      if (!allowed[d]) continue;
      score[d] += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * ix.dl[d] / ix.avgdl));
    }
  }
  const hits = [];
  for (let d = 0; d < N; d++) if (score[d] > 0) hits.push([d, score[d]]);
  hits.sort((a, b) => b[1] - a[1]);
  return { allowedCount: allowed.filter(Boolean).length, top: hits.slice(0, k).map(([d, s]) => ({ slug: ix.cards[d].slug, s })) };
}

// ---- 評測查詢：使用者原話、模型改寫（手寫模擬）、預期的好答案 ----
const QUERIES = [
  ["search text in files really fast", "grep search regex recursive code files fast", ["ripgrep", "ugrep", "the_silver_searcher"]],
  ["count lines of code in a repo", "count lines code statistics counter", ["cloc", "tokei", "scc"]],
  ["run a large language model on my laptop", "llm inference local large language model gguf server", ["llama.cpp", "ollama", "mlx-lm", "localai", "shimmy", "rapid-mlx"]],
  ["turn my meeting recording into text offline", "speech recognition transcription whisper audio on-device", ["whisper.cpp", "whisperkit-cli", "openai-whisper", "yap", "speech"]],
  ["see what's taking space on my disk", "disk usage analyzer du space", ["ncdu", "dust", "gdu", "dua-cli"]],
  ["stress test my http api", "http load testing benchmark generator", ["hey", "wrk", "oha", "vegeta", "k6"]],
  ["nicer git diffs in the terminal", "git diff syntax highlighting pager", ["git-delta", "diff-so-fancy", "difftastic"]],
  ["browse folders from the terminal", "terminal file manager browser tui", ["yazi", "nnn", "ranger", "lf", "broot"]],
  ["slice and filter json on the command line", "json processor query viewer command-line", ["jq", "jless", "fx", "gron"]],
  ["talk to chatgpt-like models from my shell", "llm ai chat command-line cli", ["llm", "aichat", "mods"]],
];

function ms(t0) { return Number(process.hrtime.bigint() - t0) / 1e6; }
function median(a) { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; }

const brew = (await loadBrew()).filter((f) => !f.deprecated && !f.disabled && f.desc);
const pinned = new Set(QUERIES.flatMap((q) => q[2]));
console.log(`Homebrew formulae（未停用、有 desc）：${brew.length}`);

for (const size of SIZES) {
  // 固定抽樣：先放評測要用的套件，再依名稱雜湊補滿
  const pool = size === 0 ? brew : [
    ...brew.filter((f) => pinned.has(f.name)),
    ...brew.filter((f) => !pinned.has(f.name)).sort((a, b) => createHash("md5").update(a.name).digest("hex").localeCompare(createHash("md5").update(b.name).digest("hex"))),
  ].slice(0, size);
  const cards = pool.map(toCard);

  let t0 = process.hrtime.bigint();
  const ix = buildIndex(cards);
  const buildMs = ms(t0);
  const raw = JSON.stringify(ix);
  const gz = gzipSync(raw).length;
  const cardsOnly = JSON.stringify(cards);

  const parseTimes = [];
  for (let i = 0; i < 15; i++) { t0 = process.hrtime.bigint(); JSON.parse(raw); parseTimes.push(ms(t0)); }
  const cardsParse = []; const rebuild = [];
  for (let i = 0; i < 15; i++) {
    t0 = process.hrtime.bigint(); const c = JSON.parse(cardsOnly); cardsParse.push(ms(t0));
    t0 = process.hrtime.bigint(); buildIndex(c); rebuild.push(ms(t0));
  }

  const filter = (c) => c.platforms.includes("macos") && (c.verification === "verified" || c.verification === "partial");
  const qTimes = [];
  const rows = [];
  for (const [user, expanded, good] of QUERIES) {
    const rank = (res) => { const r = res.top.findIndex((h) => good.includes(h.slug)); return r < 0 ? "—" : r + 1; };
    const hitsIn = (res) => res.top.filter((h) => good.includes(h.slug)).length;
    const okGood = good.filter((g) => { const c = cards.find((x) => x.slug === g); return c && filter(c); });
    t0 = process.hrtime.bigint();
    const a = search(ix, user, filter);
    qTimes.push(ms(t0));
    const b = search(ix, expanded, filter);
    rows.push({ q: user, eligible: okGood.length, rawRank: rank(a), rawHits: hitsIn(a), expRank: rank(b), expHits: hitsIn(b), allowed: a.allowedCount, top3: b.top.slice(0, 3).map((h) => h.slug).join(", ") });
  }

  console.log(`\n=== ${cards.length} 筆 ===`);
  console.log(`索引 JSON：${(raw.length / 1024).toFixed(0)} KiB（gzip ${(gz / 1024).toFixed(0)} KiB）；只有卡片：${(cardsOnly.length / 1024).toFixed(0)} KiB；平均每張卡 ${(cardsOnly.length / cards.length).toFixed(0)} bytes`);
  console.log(`建索引 ${buildMs.toFixed(1)} ms；JSON.parse(索引) 第一次 ${parseTimes[0].toFixed(1)} ms、中位數 ${median(parseTimes).toFixed(1)} ms`);
  console.log(`只存卡片、啟動時重建：parse 中位數 ${median(cardsParse).toFixed(1)} ms + 建索引中位數 ${median(rebuild).toFixed(1)} ms`);
  console.log(`查詢（篩選＋BM25＋top25）：中位數 ${median(qTimes).toFixed(2)} ms、最大 ${Math.max(...qTimes).toFixed(2)} ms；篩選後剩 ${rows[0].allowed}/${cards.length}`);
  console.log("查詢 | 符合條件的好答案數 | 原話：第一個好答案名次／top25 命中數 | 改寫後：名次／命中數 | 改寫後前 3 名");
  for (const r of rows) console.log(`${r.q} | ${r.eligible} | ${r.rawRank}／${r.rawHits} | ${r.expRank}／${r.expHits} | ${r.top3}`);
  const solved = (k) => rows.filter((r) => r.eligible > 0 && r[k] !== "—").length;
  const total = rows.filter((r) => r.eligible > 0).length;
  console.log(`top25 內至少一個好答案：原話 ${solved("rawRank")}/${total}，改寫後 ${solved("expRank")}/${total}`);
}
