"""Translate the web page's tool sentences into Traditional Chinese (Taiwan) with Claude.

Usage:
    uv run --with anthropic python scripts/translate_zh.py --dry-run      # count what is missing
    uv run --with anthropic python scripts/translate_zh.py [--slug S]... [--limit N]

Reads data/software through the index builder, collects each listed tool's prose
(pickfit/i18n.py: summaries, features, step purposes, run notes; never commands,
names or URLs) and asks Claude for the sentences data/i18n/zh-TW/<slug>.json does
not have yet. Only those files are written; the records are never touched, and a
sentence is only used on the page while the record still says exactly that.

Translation is page copy, not part of matching or verification: find_software,
the MCP tools and every pipeline step still run on the English records and Meta's
models. The key is ANTHROPIC_API_KEY from the environment or --env.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pickfit.env import read_env
from pickfit.i18n import i18n_dir, load, prose, save
from pickfit.index import DEFAULT_DATA_DIR, REPO_ROOT, IndexBuildError, build_index

MODEL = "claude-opus-5-5"
BATCH_CHARS = 9000  # English characters per request
PRICE_IN, PRICE_OUT = 4.0 / 1e6, 20.0 / 1e6

SYSTEM = """You translate short English text from a software catalog website into Traditional Chinese as used in Taiwan (zh-TW).

The text describes developer tools, desktop apps, web apps and MCP servers: summaries, feature names, use cases, the purpose of an install step, and notes from an automated sandbox test.

Rules:
- Natural, concise Taiwanese usage: 軟體, 程式, 檔案, 資料, 伺服器, 網路, 預設, 設定, 執行, 介面, 外掛, 指令, 終端機, 資料夾, 原始碼, 下載, 登入. Never Simplified Chinese characters or mainland terms (no 软件, 文件 for file, 默认, 服务器, 网络, 运行, 视频 → use 影片).
- Keep verbatim, exactly as written: commands, code, flags, file names and paths, environment variables, package names, product and tool names, model names, URLs, version numbers, error messages quoted from output, and text inside quotes or backticks.
- Put one half-width space between Chinese characters and adjacent Latin letters or digits (例如：用 Python 3.12 執行).
- Use full-width Chinese punctuation (，。：；（）) in Chinese sentences; keep punctuation inside code as is.
- Short feature names and use cases stay short noun or verb phrases; do not add explanations or a trailing period the English lacks.
- Translate meaning, not word by word; never add or drop facts.
Return every item, with the same index."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"i": {"type": "integer"}, "zh": {"type": "string"}},
                "required": ["i", "zh"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def batches(todo: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """(slug, text) pairs in groups of about BATCH_CHARS characters, a tool's sentences kept together where possible."""
    out: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for pair in todo:
        if current and size + len(pair[1]) > BATCH_CHARS:
            out.append(current)
            current, size = [], 0
        current.append(pair)
        size += len(pair[1])
    if current:
        out.append(current)
    return out


def translate(client, batch: list[tuple[str, str]]) -> tuple[dict[int, str], int, int]:
    lines = [{"i": i, "tool": slug, "en": text} for i, (slug, text) in enumerate(batch)]
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "Translate each item's \"en\" into zh-TW.\n\n" + json.dumps(lines, ensure_ascii=False)}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason {response.stop_reason}")
    text = next(block.text for block in response.content if block.type == "text")
    items = json.loads(text)["items"]
    got = {item["i"]: item["zh"].strip() for item in items if 0 <= item["i"] < len(batch) and item["zh"].strip()}
    return got, response.usage.input_tokens, response.usage.output_tokens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--slug", action="append", help="only this tool (repeatable)")
    parser.add_argument("--limit", type=int, help="at most N requests")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--env", type=Path, default=REPO_ROOT / ".env", help="dotenv file with ANTHROPIC_API_KEY")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        index = build_index(args.data).index
    except IndexBuildError as err:
        print(f"translate_zh: {len(err.problems)} invalid record(s)", file=sys.stderr)
        return 1
    directory = i18n_dir(args.data)
    known = {e["slug"]: load(directory, e["slug"]) for e in index["entries"]}
    todo = [
        (e["slug"], text)
        for e in index["entries"]
        if not args.slug or e["slug"] in args.slug
        for text in prose(e)
        if text not in known[e["slug"]]
    ]
    groups = batches(todo)
    if args.limit is not None:
        groups = groups[: args.limit]
    chars = sum(len(t) for g in groups for _, t in g)
    print(f"translate_zh: {sum(map(len, groups))} sentences ({chars:,} chars) missing, {len(groups)} requests")
    if args.dry_run or not groups:
        return 0

    import anthropic

    key = read_env(["ANTHROPIC_API_KEY"], args.env).get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    lock = threading.Lock()
    totals = {"in": 0, "out": 0, "done": 0, "failed": 0}

    def run(batch: list[tuple[str, str]]) -> None:
        try:
            got, tin, tout = translate(client, batch)
        except Exception as err:  # one failed batch must not lose the others; a rerun picks it up
            with lock:
                totals["failed"] += 1
            print(f"  batch failed ({len(batch)} sentences): {err}", file=sys.stderr)
            return
        with lock:
            totals["in"] += tin
            totals["out"] += tout
            touched: set[str] = set()
            for i, zh in got.items():
                slug, en = batch[i]
                known[slug][en] = zh
                touched.add(slug)
            for slug in touched:
                save(directory, slug, known[slug])
            totals["done"] += 1
            cost = totals["in"] * PRICE_IN + totals["out"] * PRICE_OUT
            print(f"  {totals['done']}/{len(groups)} requests · {len(got)}/{len(batch)} sentences · ${cost:.2f} so far")

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for future in as_completed([pool.submit(run, g) for g in groups]):
            future.result()
    cost = totals["in"] * PRICE_IN + totals["out"] * PRICE_OUT
    print(f"translate_zh: {totals['done']} requests done, {totals['failed']} failed; "
          f"{totals['in']:,} in / {totals['out']:,} out tokens ≈ ${cost:.2f} ({MODEL})")
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
