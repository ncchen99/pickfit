"""Translate the web page's tool sentences into Traditional Chinese (Taiwan), only those not yet translated.

Used by scripts/translate_zh.py and by `pickfit publish` (before it builds the index). Reads
each listed tool's prose (pickfit/i18n.py: summaries, features, step purposes, run notes;
never commands, names or URLs) and asks the model for the sentences data/i18n/zh-TW/<slug>.json
does not have yet. Only those files are written; the records are never touched, and the page
uses a sentence only while the record still says exactly that, so a failed or skipped
translation just leaves that sentence in English.

Translation is page copy, not part of matching or verification: find_software, the MCP tools
and every pipeline step run on the English records. The default model is Muse Spark Open on
Modal's endpoint through call_meta (the modal-llm budget in the shared ledger, Modal credits).
On 11/2 a blind comparison on 20 held-out tools (246 sentences, judged by Claude) found meaning
errors in about 1-2% of its sentences at effort medium, against under 1% for Claude Opus 5.5,
at about $0.0045 a tool. The first full translation (856 tools) was made with claude-opus-5-5,
which stays available as the fallback (`--model claude`, key ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pickfit.i18n import load, prose, save

MODELS = ("open-modal", "claude")
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_PRICE_IN, CLAUDE_PRICE_OUT = 4.0 / 1e6, 20.0 / 1e6
# English characters per request: Muse Spark Open gets smaller batches, so one bad answer costs less to redo.
BATCH_CHARS = {"open-modal": 4000, "claude": 9000}
STAGE = "translate"

SYSTEM = """You translate short English text from a software catalog website into Traditional Chinese as used in Taiwan (zh-TW).

The text describes developer tools, desktop apps, web apps and MCP servers: summaries, feature names, use cases, the purpose of an install step, and notes from an automated sandbox test.

Rules:
- Natural, concise Taiwanese usage: 軟體, 程式, 檔案, 資料, 伺服器, 網路, 預設, 設定, 執行, 介面, 外掛, 指令, 終端機, 資料夾, 原始碼, 下載, 登入. Never Simplified Chinese characters or mainland terms (no 软件, 文件 for file, 默认, 服务器, 网络, 运行, 视频 → use 影片).
- Keep verbatim, exactly as written: commands, code, flags, file names and paths, environment variables, package names, product and tool names, model names, URLs, version numbers, error messages quoted from output, and text inside quotes or backticks.
- Put one half-width space between Chinese characters and adjacent Latin letters or digits (例如：用 Python 3.12 執行).
- Use full-width Chinese punctuation (，。：；（）) in Chinese sentences; keep punctuation inside code as is.
- Short feature names and use cases stay short noun or verb phrases; do not add explanations or a trailing period the English lacks.
- Translate meaning, not word by word; never add or drop facts. Keep a full stop (。) when the English sentence ends with a period, and none when it does not.
- Write like Taiwanese product copy, as short as the English or shorter. A summary says what the tool is first, then what it does, with at most two 的 per sentence (not "用於…的…工具。"; write "輕量的網頁密碼管理工具，用來整理 Windows AD 帳密。"). In test notes, drop pronouns (其, 它) and the passive 被, and lead with the result.

Terms from pickfit's test notes (they have fixed meanings):
- "box", "the agent's box", "a fresh box" = the test sandbox: 沙盒, agent 的沙盒, 全新的沙盒 (not 機器, not 此環境).
- "exercised" / "not exercised" = actually tried in the test / not tried: 實際測試過 / 沒有實際測試 (it never means the tool cannot run).
- "check passed / did not pass", "smoke test", "replay" = 檢查通過／未通過, 冒煙測試, 重跑 (re-running the recorded steps from scratch; never 重播).
- "too long for the record" = the check's output was too long to keep in the record, not that the record is too long.
- transcribe = 轉錄 / 語音轉文字 (never 轉譯 or 翻譯); local = 本機 (not 本地); script = 腳本; prompt = 提示詞; agent, subagent, coding agent, AI agent stay in English (agent, subagent, coding agent, AI agent; never 代理); profile = 簡介; repo / repository = 儲存庫; open source = 開源; API key = API 金鑰; client = 用戶端 (not 客戶端); call / invoke = 呼叫 (not 調用).
- Technical domain terms keep their field's established meaning (e.g. "variant calls" in genomics = 變異位點檢出結果; "open a circuit" = 斷開電路); when unsure, keep the English term.
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


def missing(entries: Iterable[dict[str, Any]], directory: Path, retranslate: bool = False) -> tuple[dict[str, dict[str, str]], list[tuple[str, str]]]:
    """Each tool's known translations, and the (slug, English) pairs still to translate."""
    entries = list(entries)
    known = {e["slug"]: {} if retranslate else load(directory, e["slug"]) for e in entries}
    todo = [(e["slug"], text) for e in entries for text in prose(e) if text not in known[e["slug"]]]
    return known, todo


def batches(todo: list[tuple[str, str]], limit: int) -> list[list[tuple[str, str]]]:
    """(slug, text) pairs in groups of about `limit` characters, a tool's sentences kept together where possible."""
    out: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for pair in todo:
        if current and size + len(pair[1]) > limit:
            out.append(current)
            current, size = [], 0
        current.append(pair)
        size += len(pair[1])
    if current:
        out.append(current)
    return out


def request_text(batch: list[tuple[str, str]]) -> str:
    lines = [{"i": i, "tool": slug, "en": text} for i, (slug, text) in enumerate(batch)]
    return "Translate each item's \"en\" into zh-TW.\n\n" + json.dumps(lines, ensure_ascii=False)


def answers(text: str, size: int) -> dict[int, str]:
    items = json.loads(text)["items"]
    return {item["i"]: item["zh"].strip() for item in items if 0 <= item["i"] < size and item["zh"].strip()}


def translate_open(batch: list[tuple[str, str]], run_id: str, max_usd: float, effort: str) -> tuple[dict[int, str], float]:
    """Muse Spark Open on Modal through call_meta: billed to the modal-llm budget, `max_usd` per run."""
    from pickfit.ledger import modal_llm_ledger
    from pickfit.meta import call_meta

    body = {
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request_text(batch)}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "translations", "schema": SCHEMA, "strict": True}},
    }
    result = call_meta("chat", body, stage=STAGE, public_data_only=True, max_output_tokens=16000, model="open-modal",
                       provider="modal", reasoning_effort=effort, scope=f"{STAGE}:{run_id}", scope_cap_usd=max_usd,
                       run_id=run_id, cache=False, ledger=modal_llm_ledger())
    if result.status not in (None, "stop"):
        raise RuntimeError(f"finish_reason {result.status}")
    return answers(result.text or "", len(batch)), result.cost_usd


def translate_claude(client: Any, batch: list[tuple[str, str]]) -> tuple[dict[int, str], float]:
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=32000,
        system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": request_text(batch)}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason {response.stop_reason}")
    text = next(block.text for block in response.content if block.type == "text")
    cost = response.usage.input_tokens * CLAUDE_PRICE_IN + response.usage.output_tokens * CLAUDE_PRICE_OUT
    return answers(text, len(batch)), cost


@dataclass
class Totals:
    sentences: int = 0
    requests: int = 0
    failed: int = 0
    usd: float = 0.0


def run(
    groups: list[list[tuple[str, str]]],
    known: dict[str, dict[str, str]],
    directory: Path,
    *,
    model: str = "open-modal",
    effort: str = "medium",
    max_usd: float = 2.0,
    concurrency: int = 8,
    anthropic_key: str | None = None,
    out: Callable[[str], None] = print,
) -> Totals:
    """Translate `groups` and save each tool's file as its answers arrive; a failed request is counted, not raised."""
    if model == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=anthropic_key) if anthropic_key else anthropic.Anthropic()
        translate = lambda batch: translate_claude(client, batch)  # noqa: E731
    elif model == "open-modal":
        from pickfit.ledger import taipei_now

        run_id = f"translate-{taipei_now():%Y%m%d-%H%M%S}"
        translate = lambda batch: translate_open(batch, run_id, max_usd, effort)  # noqa: E731
    else:
        raise ValueError(f"model must be one of {MODELS}")
    lock = threading.Lock()
    totals = Totals()

    def one(batch: list[tuple[str, str]]) -> None:
        try:
            got, cost = translate(batch)
        except Exception as err:  # noqa: BLE001 - one failed batch must not lose the others; a rerun picks it up
            with lock:
                totals.failed += 1
            print(f"  translate: a request failed ({len(batch)} sentences): {str(err)[:300]}", file=sys.stderr)
            return
        with lock:
            totals.usd += cost
            totals.requests += 1
            totals.sentences += len(got)
            touched: set[str] = set()
            for i, zh in got.items():
                slug, en = batch[i]
                known[slug][en] = zh
                touched.add(slug)
            for slug in touched:
                save(directory, slug, known[slug])
            out(f"  translate: {totals.requests + totals.failed}/{len(groups)} requests · "
                f"{len(got)}/{len(batch)} sentences · ${totals.usd:.2f} so far")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in as_completed([pool.submit(one, g) for g in groups]):
            future.result()
    return totals
