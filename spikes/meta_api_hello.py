#!/usr/bin/env python3
"""Meta Model API 最小呼叫 spike（未實測：撰寫時沒有 API key）。

測四件事，全部走 OpenAI 相容的 POST /v1/chat/completions：
  1. text         純文字
  2. json_schema  結構化輸出（response_format.type = json_schema）
  3. tools        tool calling：模型回 tool_calls -> 本地執行 -> 回傳結果 -> 模型給最終答案
  4. image        圖片輸入：base64 data URL（本機產生的 PNG）與公開 URL 各一次

只用 Python 標準函式庫，不需要 pip install。

用法：
  export MODEL_API_KEY="LLM_..."          # 官方文件用的變數名；也接受 META_API_KEY
  python3 spikes/meta_api_hello.py         # 跑全部
  python3 spikes/meta_api_hello.py text tools   # 只跑指定的測試

可選環境變數：
  META_MODEL      預設 muse-spark-1.3；便宜的 Contributor 版是 muse-spark-1.3-contributor
  META_BASE_URL   預設 https://api.meta.ai/v1
  META_REASONING  預設 low（可填 minimal/low/medium/high/xhigh；Muse Spark 不接受 none）

文件來源（2026-10-28 查證）：
  https://dev.meta.ai/docs/protocols/chat-completions.md
  https://dev.meta.ai/docs/structured-output.md
  https://dev.meta.ai/docs/tool-calling.md
  https://dev.meta.ai/docs/image-understanding.md
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

BASE_URL = os.environ.get("META_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
MODEL = os.environ.get("META_MODEL", "muse-spark-1.3")
REASONING = os.environ.get("META_REASONING", "low")
API_KEY = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")

# 推理 token 和可見輸出共用這個上限；設太小會拿到空字串 + finish_reason=length。
MAX_COMPLETION_TOKENS = 4000

# 官方 image-understanding 文件 curl 範例用的公開圖片。
PUBLIC_IMAGE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/"
    "Avocado_Hass_-_single_and_halved.jpg/1280px-Avocado_Hass_-_single_and_halved.jpg"
)

NO_KEY_HELP = """\
沒有找到 API key（MODEL_API_KEY 或 META_API_KEY），不送出任何請求。

申請步驟（見 docs/research/notes/meta-model-api.md 第 5 節）：
  1. 到 https://dev.meta.ai/ 選 Start building，建立帳號（Individual）。
  2. Billing -> Add payment method，填卡片與姓名、地址。
  3. API keys -> Create API key，複製（只顯示一次）。
  4. 依比賽 Participant Guide 的表單領 $150 credits；在 Billing -> Spend Limits 設提醒。
  5. 把 key 放進 repo 根目錄的 .env（已在 .gitignore；本腳本不會自動讀 .env）：
       echo 'MODEL_API_KEY=LLM_...' >> .env
       set -a; . ./.env; set +a
     再跑一次：python3 spikes/meta_api_hello.py

不需要 key 的健康檢查：curl https://api.meta.ai/v1/status
"""


# ---------------------------------------------------------------- HTTP

def post_chat(body: dict) -> tuple[dict, dict]:
    """POST /chat/completions，回傳 (json, 相關 headers)。失敗時印出錯誤並丟例外。"""
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {detail}")
        raise
    elapsed = time.monotonic() - t0
    rl = {k: v for k, v in headers.items() if k.startswith("x-ratelimit") or k == "x-request-id"}
    rl["elapsed_s"] = f"{elapsed:.1f}"
    return data, rl


def base_body(messages: list[dict]) -> dict:
    return {
        "model": MODEL,
        "messages": messages,
        "reasoning_effort": REASONING,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }


def show_usage(data: dict, meta: dict) -> None:
    u = data.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    print(
        f"  usage: prompt={u.get('prompt_tokens')} cached={cached} "
        f"completion={u.get('completion_tokens')} reasoning={reasoning} | {meta}"
    )


def first_choice(data: dict) -> dict:
    choice = data["choices"][0]
    print(f"  finish_reason={choice.get('finish_reason')}")
    return choice


# ---------------------------------------------------------------- tests

def test_text() -> None:
    data, meta = post_chat(base_body([
        {"role": "developer", "content": "Answer in one short sentence."},
        {"role": "user", "content": "What does a package manager do?"},
    ]))
    choice = first_choice(data)
    print(f"  answer: {choice['message'].get('content')!r}")
    show_usage(data, meta)


README_SNIPPET = """\
# tinyq
A tiny, fast jq alternative written in Rust. Single static binary, no runtime deps.
Install: `brew install someone/tap/tinyq` or `cargo install tinyq`.
Works on macOS and Linux. MIT licensed.
Usage: `cat data.json | tinyq '.items[].name'`
"""

SOFTWARE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_usable_software": {"type": "boolean"},
        "name": {"type": "string"},
        "summary": {"type": "string"},
        "category": {"type": "string", "enum": ["dev_cli", "local_ai", "other"]},
        "platforms": {
            "type": "array",
            "items": {"type": "string", "enum": ["macos", "linux", "windows"]},
        },
        "install_commands": {"type": "array", "items": {"type": "string"}},
        "license": {"type": ["string", "null"]},
        "runs_locally": {"type": "boolean"},
    },
    "required": [
        "is_usable_software", "name", "summary", "category",
        "platforms", "install_commands", "license", "runs_locally",
    ],
    "additionalProperties": False,
}


def test_json_schema() -> None:
    body = base_body([
        {"role": "developer", "content": "Extract a software profile from the README. Use null when unknown."},
        {"role": "user", "content": README_SNIPPET},
    ])
    body["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": "software_profile", "schema": SOFTWARE_SCHEMA, "strict": True},
    }
    data, meta = post_chat(body)
    choice = first_choice(data)
    content = choice["message"].get("content") or ""
    parsed = json.loads(content)  # 文件說輸出受 schema 約束，這裡應該一定能 parse
    missing = [k for k in SOFTWARE_SCHEMA["required"] if k not in parsed]
    print(f"  parsed: {json.dumps(parsed, ensure_ascii=False)}")
    print(f"  missing required keys: {missing or 'none'}")
    show_usage(data, meta)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_repo_stats",
        "description": "Return GitHub stars and last release date for a repository.",
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "owner/name"}},
            "required": ["repo"],
        },
    },
}]


def fake_get_repo_stats(repo: str) -> dict:
    return {"repo": repo, "stars": 312, "last_release": "2026-10-20"}


def test_tools() -> None:
    messages = [
        {"role": "developer", "content": "Use the tool to look up facts before answering."},
        {"role": "user", "content": "How many stars does someone/tinyq have, and when was its last release?"},
    ]
    body = base_body(messages)
    body["tools"] = TOOLS  # tool_choice 只支援 "auto"（預設），不設
    data, meta = post_chat(body)
    choice = first_choice(data)
    msg = choice["message"]
    calls = msg.get("tool_calls") or []
    print(f"  tool_calls: {[(c['function']['name'], c['function']['arguments']) for c in calls]}")
    show_usage(data, meta)
    if not calls:
        print("  模型沒有呼叫工具（tool_choice=auto 時允許）；略過第二輪。")
        return

    # 第二輪：完整回放 assistant 訊息（含 tool_calls），每個 call 回一個 tool 訊息。
    messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
    for c in calls:
        args = json.loads(c["function"]["arguments"] or "{}")
        result = fake_get_repo_stats(args.get("repo", ""))
        messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
    body = base_body(messages)
    body["tools"] = TOOLS
    data, meta = post_chat(body)
    choice = first_choice(data)
    print(f"  final answer: {choice['message'].get('content')!r}")
    show_usage(data, meta)


def make_png(width: int = 96, height: int = 96) -> bytes:
    """產生白底、中間紅色方塊的 PNG（只用標準函式庫）。"""
    rows = []
    for y in range(height):
        row = bytearray([0])  # filter type 0
        for x in range(width):
            inside = width // 4 <= x < 3 * width // 4 and height // 4 <= y < 3 * height // 4
            row += bytes((220, 30, 30) if inside else (255, 255, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def ask_image(url: str, question: str) -> None:
    data, meta = post_chat(base_body([{
        "role": "user",  # 圖片只能放在 user 訊息
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": url}},
        ],
    }]))
    choice = first_choice(data)
    print(f"  answer: {choice['message'].get('content')!r}")
    show_usage(data, meta)


def test_image() -> None:
    b64 = base64.b64encode(make_png()).decode("ascii")
    print("  [base64 data URL]")
    ask_image(f"data:image/png;base64,{b64}",
              "What shape and color is in the center of this image? One short sentence.")
    print("  [public URL]")
    ask_image(PUBLIC_IMAGE_URL, "What fruit is this? One short sentence.")


TESTS = {
    "text": test_text,
    "json_schema": test_json_schema,
    "tools": test_tools,
    "image": test_image,
}


def main(argv: list[str]) -> int:
    if not API_KEY:
        print(NO_KEY_HELP)
        return 2
    names = argv or list(TESTS)
    unknown = [n for n in names if n not in TESTS]
    if unknown:
        print(f"未知的測試：{unknown}；可用：{list(TESTS)}")
        return 2
    print(f"base_url={BASE_URL} model={MODEL} reasoning_effort={REASONING}")
    failed = []
    for name in names:
        print(f"\n== {name}")
        try:
            TESTS[name]()
        except Exception as e:  # spike：記錄後繼續跑下一個
            print(f"  FAILED: {type(e).__name__}: {e}")
            failed.append(name)
    print(f"\n結果：{len(names) - len(failed)}/{len(names)} 通過" + (f"；失敗：{failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
