#!/usr/bin/env python3
"""F 節 spike：檔案 schema 與事件表。

從 docs/research/notes/storage-matching.md 抽出三段（以 <!-- sm:... --> 標記）：
  profile-schema（JSON Schema 2020-12）、profile-example（虛構範例）、events-ddl（D1 的 SQL）
然後：
  1. 範例要通過 schema；幾種壞資料要被擋下
  2. schema 表達不了的程式端規則（evidence 指向、事實欄位要有出處、verified 要有重播）
  3. DDL 在 SQLite 上跑：outcome 去重、CHECK、budget upsert + RETURNING、重驗佇列、彙總
  4. （有 Homebrew 快取時）SQLite + FTS5 當索引的檔案大小，和 JSON 索引比較

用法：python3 spikes/sm_schema_events.py   （需要 jsonschema；不需要金鑰）
"""
import copy
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from importlib.metadata import version

from jsonschema import Draft202012Validator, FormatChecker

DOC = Path(__file__).resolve().parent.parent / "docs/research/notes/storage-matching.md"


def block(md: str, marker: str) -> str:
    m = re.search(r"<!-- sm:" + re.escape(marker) + r" -->\s*```\w*\n(.*?)\n```", md, re.S)
    if not m:
        sys.exit(f"找不到區塊 {marker}")
    return m.group(1)


md = DOC.read_text(encoding="utf-8")
schema = json.loads(block(md, "profile-schema"))
example = json.loads(block(md, "profile-example"))
ddl = block(md, "events-ddl")

# ---------- 1. schema ----------
Draft202012Validator.check_schema(schema)
fc = FormatChecker()
v = Draft202012Validator(schema, format_checker=fc)
print(f"jsonschema {version('jsonschema')}；有檢查的 format：{sorted(f for f in ('uri', 'date-time') if f in fc.checkers)}"
      "（空的＝沒裝 rfc3987／rfc3339-validator，format 只當註解）")
errs = list(v.iter_errors(example))
print(f"[1] 範例過 schema：{'OK' if not errs else 'FAIL'}")
for e in errs:
    print("    ", list(e.absolute_path), e.message[:120])


def mutate(f):
    p = copy.deepcopy(example)
    f(p)
    return p


bad = {
    "少了 sources": mutate(lambda p: p.pop("sources")),
    "slug 有空白": mutate(lambda p: p.__setitem__("slug", "Bad Slug")),
    "install 多了 android": mutate(lambda p: p["install"].__setitem__("android", p["install"]["linux"])),
    "verified 但 verified_at 是 null": mutate(lambda p: p["install"]["linux"].__setitem__("verified_at", None)),
    "引用超過 200 字": mutate(lambda p: p["evidence"][0].__setitem__("quote", "x" * 201)),
    "pricing.model 不在列舉": mutate(lambda p: p["pricing"].__setitem__("model", "cheap")),
    "截圖 sha256 格式錯": mutate(lambda p: p["verification"]["runs"][0]["screenshots"][0].__setitem__("sha256", "abc")),
}
for name, p in bad.items():
    n = len(list(v.iter_errors(p)))
    print(f"    壞資料「{name}」：{'擋下' if n else '沒擋下！'}（{n} 個錯誤）")


# ---------- 2. 程式端規則 ----------
def resolve(doc, pointer):
    cur = doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(pointer)
    return cur


FACT_FIELDS = ["/summary", "/platforms", "/pricing", "/license", "/processing", "/last_release", "/homepage"]


def rule_errors(p):
    out = []
    src_ids = {s["id"] for s in p["sources"]}
    covered = set()
    for ev in p["evidence"]:
        if ev["source_id"] not in src_ids:
            out.append(f"evidence {ev['field']} 指向不存在的來源 {ev['source_id']}")
        try:
            resolve(p, ev["field"])
        except (KeyError, IndexError, ValueError):
            out.append(f"evidence 指向不存在的欄位 {ev['field']}")
        covered.add(ev["field"])
    facts = FACT_FIELDS + [f"/install/{os_}" for os_ in p["install"]]
    for f in facts:
        try:
            val = resolve(p, f)
        except KeyError:
            val = None
        if val not in (None, "unknown", []) and f not in covered:
            out.append(f"事實欄位 {f} 沒有 evidence")
        if val in (None, "unknown") and f not in p["unknown_fields"] and f not in covered:
            out.append(f"{f} 是空的，卻沒列在 unknown_fields")
    runs = {r["id"]: r for r in p["verification"]["runs"]}
    for os_, inst in p["install"].items():
        if inst["status"] == "verified":
            r = runs.get(inst["sandbox_ref"])
            if not r or r["os"] != os_ or r["reproducible"] is not True:
                out.append(f"install/{os_} 標 verified，但對應的 run 不存在、OS 不符或沒有重播通過")
    q, pct, t = p["scores"]["quality"]["total"], p["scores"]["popularity"]["percentile"], p["scores"]["treasure"]
    if None not in (q, pct, t) and abs(q * (1 - pct / 100) - t) > 0.1:
        out.append(f"treasure {t} ≠ quality × (1 − percentile/100) = {q * (1 - pct / 100):.2f}")
    return out


print(f"[2] 程式端規則（範例）：{rule_errors(example) or 'OK'}")
rule_bad = {
    "拿掉 /license 的 evidence": mutate(lambda p: p.__setitem__("evidence", [e for e in p["evidence"] if e["field"] != "/license"])),
    "evidence 指到不存在的來源": mutate(lambda p: p["evidence"][0].__setitem__("source_id", "readme-v2")),
    "重播沒通過卻標 verified": mutate(lambda p: p["verification"]["runs"][0].__setitem__("reproducible", False)),
    "treasure 算錯": mutate(lambda p: p["scores"].__setitem__("treasure", 90)),
}
for name, p in rule_bad.items():
    print(f"    「{name}」：{rule_errors(p)}")

pretty = json.dumps(example, indent=2, ensure_ascii=False) + "\n"
compact = json.dumps(example, ensure_ascii=False, separators=(",", ":"))
print(f"    範例大小：indent=2 {len(pretty.encode())} bytes、{pretty.count(chr(10))} 行；壓縮 {len(compact.encode())} bytes"
      f" → 3,000 筆完整檔案約 {len(compact.encode()) * 3000 / 1e6:.1f} MB（未壓縮）")

# ---------- 3. 事件表 ----------
db = sqlite3.connect(":memory:")
db.executescript(ddl)
print(f"[3] DDL 在 SQLite {sqlite3.sqlite_version} 上建立：OK")
COLS = "(id, ts, type, rec_id, slug, os, category, need, results, stage, success, satisfied, error_excerpt, client, generated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
# 注意：INSERT OR IGNORE 會連 CHECK 失敗也默默略過。去重改用只針對 partial unique index 的 upsert。
ins = "INSERT INTO events " + COLS + " ON CONFLICT (rec_id, slug, stage) WHERE type = 'outcome' DO NOTHING"
ins_or_ignore = "INSERT OR IGNORE INTO events " + COLS
need = json.dumps({"os": "linux", "budget": "free_only", "privacy": "local_only", "category": "local_ai"})
db.execute(ins, ("e1", "2026-11-01T10:00:00Z", "find", "r1", None, "linux", "local_ai", need, '["example-whisper-cli"]', None, None, None, None, "claude-code", "model"))
rows = [
    ("e2", "installed", 1, None, None),
    ("e3", "first_run", 0, None, "error: libsndfile.so.1: cannot open shared object file"),
    ("e4", "first_run", 0, None, "duplicate report"),            # 同 rec_id+slug+stage → 忽略
]
for eid, stage, ok, sat, err in rows:
    cur = db.execute(ins, (eid, "2026-11-01T10:05:00Z", "outcome", "r1", "example-whisper-cli", "linux", None, None, None, stage, ok, sat, err, "claude-code", None))
    print(f"    outcome {eid} {stage}：{'寫入' if cur.rowcount else '重複，忽略'}")
bad_row = ("e5", "2026-11-01T10:06:00Z", "outcome", None, "example-whisper-cli", "linux", None, None, None, "installed", 1, None, None, None, None)
cur = db.execute(ins_or_ignore, bad_row)
print(f"    對照：用 INSERT OR IGNORE 寫沒有 rec_id 的 outcome → 不報錯、寫入 {cur.rowcount} 列（錯誤被吞掉）")
try:
    db.execute(ins, bad_row)
    print("    沒有 rec_id 的 outcome：沒擋下！")
except sqlite3.IntegrityError as e:
    print(f"    沒有 rec_id 的 outcome（upsert 寫法）：擋下（{e}）")
try:
    db.execute(ins, ("e6", "2026-11-01T10:06:00Z", "find", "r2", None, None, None, "{not json", None, None, None, None, None, None, None))
    print("    need 不是 JSON：沒擋下！")
except sqlite3.IntegrityError as e:
    print(f"    need 不是 JSON：擋下（{e}）")

upsert = ("INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, ?) "
          "ON CONFLICT(day) DO UPDATE SET calls = calls + 1, cost_usd = cost_usd + excluded.cost_usd RETURNING calls, cost_usd")
for c in (0.024, 0.021):
    calls, cost = db.execute(upsert, ("2026-11-01", c)).fetchone()
print(f"    meta_budget upsert + RETURNING：calls={calls}, cost_usd={cost:.3f}")

requeue = ("INSERT INTO reverify_queue (slug, os, reason, first_event_id, queued_at) VALUES (?,?,?,?,?) "
           "ON CONFLICT(slug, os) DO UPDATE SET reason = excluded.reason, queued_at = excluded.queued_at, done_at = NULL "
           "WHERE reverify_queue.done_at IS NOT NULL")
db.execute(requeue, ("example-whisper-cli", "linux", "first_run failed", "e3", "2026-11-01T10:05:00Z"))
db.execute("UPDATE reverify_queue SET done_at = '2026-11-01T11:00:00Z'")
db.execute(requeue, ("example-whisper-cli", "linux", "first_run failed again", "e9", "2026-11-02T09:00:00Z"))
print(f"    reverify_queue 完成後再失敗會重新排入：{db.execute('SELECT reason, done_at FROM reverify_queue').fetchone()}")
agg = db.execute("""
  SELECT slug, os, COUNT(*) AS reports,
         SUM(stage = 'installed' AND success = 1) AS install_ok,
         SUM(stage = 'first_run' AND success = 1) AS first_run_ok,
         SUM(satisfied = 1) AS satisfied, MAX(ts) AS last_report_at
  FROM events WHERE type = 'outcome' GROUP BY slug, os""").fetchall()
print(f"    sync_outcomes 彙總：{agg}")
plan = db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*) FROM events WHERE slug = ? AND type = 'outcome'", ("x",)).fetchall()
print(f"    查詢計畫（slug+type）：{plan[0][-1]}")

# ---------- 4. SQLite + FTS5 當索引 ----------
cache = Path(tempfile.gettempdir()) / "pickfit-sm" / "formula.json"
if cache.exists():
    brew = [f for f in json.loads(cache.read_text()) if f.get("desc") and not f.get("deprecated") and not f.get("disabled")]
    for n in (3000, len(brew)):
        path = Path(tempfile.mkdtemp()) / "idx.sqlite"
        con = sqlite3.connect(path)
        con.executescript("CREATE TABLE cards (slug TEXT PRIMARY KEY, card TEXT NOT NULL);"
                          "CREATE VIRTUAL TABLE fts USING fts5(slug UNINDEXED, name, summary, tokenize='porter');")
        for f in brew[:n]:
            card = {"slug": f["name"], "name": f["name"], "summary": f["desc"], "license": f.get("license")}
            con.execute("INSERT INTO cards VALUES (?, ?)", (f["name"], json.dumps(card)))
            con.execute("INSERT INTO fts VALUES (?, ?, ?)", (f["name"], f["name"].replace("-", " "), f["desc"]))
        con.commit()
        con.execute("VACUUM")
        t0 = time.perf_counter()
        hits = con.execute("SELECT slug FROM fts WHERE fts MATCH ? ORDER BY bm25(fts, 0, 3.0, 1.0) LIMIT 25",
                           ("speech OR recognition OR transcription OR whisper",)).fetchall()
        ms = (time.perf_counter() - t0) * 1000
        con.close()
        print(f"[4] SQLite+FTS5 {n} 筆：檔案 {os.path.getsize(path) / 1024:.0f} KiB；一次 MATCH 查詢 {ms:.2f} ms；前 3 名 {[h[0] for h in hits[:3]]}")
else:
    print("[4] 略過：先跑 node spikes/sm_index_bench.mjs 下載 Homebrew 資料")
