#!/usr/bin/env python3
"""驗證 agent 設計依賴、但文件沒講清楚的 Responses API 行為（未實測：撰寫時沒有 API key）。

設計文件：docs/research/notes/meta-usage-design.md 第 4.3 節與第 8 節。
四個測試，全部走 POST /v1/responses，工具輸出都是寫死的假資料，不會在本機執行任何指令：

  loop           function tools + previous_response_id + reasoning.summary 的多輪迴圈，
                 模型要讀 README、遇到安裝錯誤、改指令、跑 smoke test，最後呼叫 finish。
                 觀察：finish 參數是否合法、每輪 cached_tokens 是否 > 0（快取能否跨 previous_response_id）。
  image_tool     截圖放在 function_call_output 的 content list（schema 允許，但圖片指南說只看 user 訊息）
                 vs. 放在緊接著的 user 訊息。觀察：哪一種 HTTP 200、模型是否說得出圖中方塊的顏色。
  schema_tools   同一個請求同時帶 tools 和 text.format json_schema。觀察：是否 400、最後輸出是否合 schema。
  search_probe   內建 web_search + include web_search_call.results。觀察：拿不拿得到原始結果 URL
                 （「搜尋可見度」訊號要用）。會產生 1–2 次搜尋費用（$2.50 / 1,000 次）。

只用 Python 標準函式庫。

用法：
  export MODEL_API_KEY="LLM_..."                       # 也接受 META_API_KEY
  python3 spikes/meta_responses_agent_probe.py          # 跑全部
  python3 spikes/meta_responses_agent_probe.py loop image_tool

可選環境變數：META_MODEL（預設 muse-spark-1.3）、META_BASE_URL（預設 https://api.meta.ai/v1）

文件來源（2026-10-28 查證）：
  https://dev.meta.ai/docs/protocols/responses.md
  https://dev.meta.ai/docs/tool-calling.md
  https://dev.meta.ai/docs/reasoning.md
  https://dev.meta.ai/docs/image-understanding.md
  https://dev.meta.ai/docs/api-reference/responses/schemas.md   （FunctionCallOutputContentListParam）
  https://dev.meta.ai/docs/search-grounding.md
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
API_KEY = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")

# 美元 / 每百萬 token（https://dev.meta.ai/docs/pricing-rate-limits.md，2026-10-28）
PRICE = {"in": 1.25, "cached": 0.15, "out": 4.25} if "contributor" not in MODEL else \
        {"in": 0.10, "cached": 0.002, "out": 0.20}
MAX_TURNS = 8

NO_KEY_HELP = """\
沒有找到 API key（MODEL_API_KEY 或 META_API_KEY），不送出任何請求。
申請步驟見 docs/research/notes/meta-model-api.md 第 5 節；拿到 key 後：
  export MODEL_API_KEY="LLM_..."
  python3 spikes/meta_responses_agent_probe.py
"""


# ---------------------------------------------------------------- HTTP

def post(body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:600]}")
        raise
    u = data.get("usage") or {}
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens") or 0
    reasoning = (u.get("output_tokens_details") or {}).get("reasoning_tokens")
    tin, tout = u.get("input_tokens") or 0, u.get("output_tokens") or 0
    cost = ((tin - cached) * PRICE["in"] + cached * PRICE["cached"] + tout * PRICE["out"]) / 1e6
    print(f"  usage: in={tin} cached={cached} out={tout} reasoning={reasoning} "
          f"≈${cost:.4f} | {time.monotonic() - t0:.1f}s status={data.get('status')}")
    return data


def items(data: dict, kind: str) -> list[dict]:
    return [it for it in data.get("output", []) if it.get("type") == kind]


def output_text(data: dict) -> str:
    return "".join(c.get("text", "") for m in items(data, "message")
                   for c in m.get("content", []) if c.get("type") == "output_text")


def summaries(data: dict) -> list[str]:
    return [s.get("text", "") for r in items(data, "reasoning") for s in r.get("summary") or []]


def png(rgb: tuple[int, int, int], size: int = 128) -> str:
    """白底、中間一塊指定顏色方塊的 PNG，回傳 data URL。"""
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            inside = size // 4 <= x < 3 * size // 4 and size // 4 <= y < 3 * size // 4
            row += bytes(rgb if inside else (255, 255, 255))
        rows.append(bytes(row))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    raw = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required,
                           "additionalProperties": False}}


# ---------------------------------------------------------------- 1. loop

README = """# tinyq
A tiny jq alternative. Install: `pip install tinyq-cli`. Usage: `echo '{"a":1}' | tinyq .a`"""

AGENT_TOOLS = [
    fn("read_file", "Read a text file in the sandbox repo checkout.",
       {"path": {"type": "string"}}, ["path"]),
    fn("run_command", "Run a non-interactive shell command in the sandbox. Returns exit code and output tail.",
       {"command": {"type": "string"}, "timeout_s": {"type": "integer"}}, ["command", "timeout_s"]),
    fn("finish", "Report the verification result. Call exactly once, at the end.",
       {"outcome": {"type": "string", "enum": ["verified", "partial", "failed", "unsupported_env"]},
        "install_steps": {"type": "array", "items": {"type": "string"}},
        "smoke_test": {"type": "string"},
        "deviations_from_readme": {"type": "array", "items": {"type": "string"}}},
       ["outcome", "install_steps", "smoke_test", "deviations_from_readme"]),
]


def fake_tool(name: str, args: dict) -> str:
    """寫死的沙盒：README 的套件名是錯的，正確的是 tinyq。"""
    if name == "read_file":
        return README if "readme" in args.get("path", "").lower() else "error: file not found"
    cmd = args.get("command", "")
    if "tinyq-cli" in cmd:
        out = {"exit_code": 1, "stderr_tail": "ERROR: No matching distribution found for tinyq-cli"}
    elif "install" in cmd and "tinyq" in cmd:
        out = {"exit_code": 0, "stdout_tail": "Successfully installed tinyq-0.4.1"}
    elif "tinyq" in cmd:
        out = {"exit_code": 0, "stdout_tail": "1" if ".a" in cmd else "tinyq 0.4.1"}
    else:
        out = {"exit_code": 0, "stdout_tail": ""}
    return json.dumps(out)


def test_loop() -> None:
    instructions = (
        "You verify that a CLI tool installs and runs, inside a disposable Linux sandbox. "
        "Read the README, install it, fix install errors yourself, run one smoke test, "
        "then call finish. Never claim success without command output that shows it.")
    body = {"model": MODEL, "instructions": instructions, "tools": AGENT_TOOLS,
            "reasoning": {"effort": "low", "summary": "auto"}, "max_output_tokens": 4000,
            "input": "Verify the repo checked out at /repo (README at /repo/README.md)."}
    data = post(body)
    for turn in range(1, MAX_TURNS + 1):
        for s in summaries(data):
            print(f"  [reasoning summary] {s}")
        calls = items(data, "function_call")
        if not calls:
            print(f"  turn {turn}: 沒有 function_call，模型直接回文字：{output_text(data)[:300]!r}")
            return
        outputs = []
        for c in calls:
            args = json.loads(c.get("arguments") or "{}")
            print(f"  turn {turn}: {c['name']}({json.dumps(args, ensure_ascii=False)})")
            if c["name"] == "finish":
                missing = [k for k in AGENT_TOOLS[2]["parameters"]["required"] if k not in args]
                print(f"  finish 參數缺少：{missing or '無'}；outcome={args.get('outcome')}")
                return
            outputs.append({"type": "function_call_output", "call_id": c["call_id"],
                            "output": fake_tool(c["name"], args)})
        # instructions、tools、reasoning 不會跟著 previous_response_id 延續，每輪都要重送
        data = post({**body, "input": outputs, "previous_response_id": data["id"]})
    print(f"  {MAX_TURNS} 輪內沒有呼叫 finish（步數上限）")


# ---------------------------------------------------------------- 2. image_tool

SHOT_TOOL = [fn("take_screenshot", "Capture the sandbox terminal as an image.", {}, [])]


def image_round(variant: str, rgb: tuple[int, int, int], color: str) -> None:
    body = {"model": MODEL, "tools": SHOT_TOOL, "reasoning": {"effort": "low"},
            "max_output_tokens": 2000,
            "input": "Take a screenshot of the terminal, then tell me the color of the square in it. One word."}
    data = post(body)
    calls = items(data, "function_call")
    if not calls:
        print(f"  [{variant}] 模型沒有呼叫 take_screenshot：{output_text(data)[:200]!r}")
        return
    url = png(rgb)
    if variant == "in_tool_output":
        new_input = [{"type": "function_call_output", "call_id": calls[0]["call_id"],
                      "output": [{"type": "input_text", "text": "screenshot:"},
                                 {"type": "input_image", "image_url": url}]}]
    else:
        new_input = [{"type": "function_call_output", "call_id": calls[0]["call_id"],
                      "output": "Screenshot captured; attached in the next user message."},
                     {"role": "user", "content": [{"type": "input_text", "text": "Screenshot:"},
                                                  {"type": "input_image", "image_url": url}]}]
    try:
        data = post({**body, "input": new_input, "previous_response_id": data["id"]})
    except urllib.error.HTTPError:
        print(f"  [{variant}] 請求被拒（見上方 HTTP 錯誤）")
        return
    answer = output_text(data)
    print(f"  [{variant}] 回答：{answer[:200]!r} → 看得到圖：{color in answer.lower()}")


def test_image_tool() -> None:
    image_round("in_tool_output", (30, 60, 220), "blue")
    image_round("user_message", (20, 170, 60), "green")


# ---------------------------------------------------------------- 3. schema_tools

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"stars": {"type": "integer"}, "verdict": {"type": "string", "enum": ["popular", "obscure"]}},
    "required": ["stars", "verdict"],
    "additionalProperties": False,
}


def test_schema_tools() -> None:
    tools = [fn("get_repo_stats", "Return GitHub stars for owner/name.",
                {"repo": {"type": "string"}}, ["repo"])]
    body = {"model": MODEL, "tools": tools, "reasoning": {"effort": "low"}, "max_output_tokens": 2000,
            "text": {"format": {"type": "json_schema", "name": "verdict", "schema": VERDICT_SCHEMA,
                                "strict": True}},
            "input": "Look up someone/tinyq with the tool. Under 1000 stars is obscure."}
    data = post(body)
    calls = items(data, "function_call")
    if calls:
        print(f"  第一輪呼叫：{[(c['name'], c.get('arguments')) for c in calls]}")
        outs = [{"type": "function_call_output", "call_id": c["call_id"],
                 "output": json.dumps({"repo": "someone/tinyq", "stars": 312})} for c in calls]
        data = post({**body, "input": outs, "previous_response_id": data["id"]})
    else:
        print("  第一輪沒有呼叫工具（tool_choice 只能 auto）")
    text = output_text(data)
    try:
        parsed = json.loads(text)
        ok = set(VERDICT_SCHEMA["required"]) <= set(parsed)
        print(f"  最終輸出：{parsed} → 合 schema：{ok}")
    except json.JSONDecodeError:
        print(f"  最終輸出不是 JSON：{text[:300]!r}")


# ---------------------------------------------------------------- 4. search_probe

def test_search_probe() -> None:
    data = post({
        "model": MODEL, "reasoning": {"effort": "low"}, "max_output_tokens": 3000,
        "tools": [{"type": "web_search", "search_context_size": "low"}], "max_tool_calls": 2,
        "include": ["web_search_call.results"],
        "input": "List open-source command-line tools that convert JSON to CSV. Name 5 with links.",
    })
    calls = items(data, "web_search_call")
    urls = [r.get("url") for c in calls for r in c.get("results") or []]
    print(f"  web_search_call 次數：{len(calls)}；原始結果 {len(urls)} 筆")
    for u in urls[:10]:
        print(f"    {u}")
    cited = [a.get("url") for m in items(data, "message") for c in m.get("content", [])
             for a in c.get("annotations") or [] if a.get("type") == "url_citation"]
    print(f"  引用（url_citation）{len(cited)} 筆；github.com 結果：{sum('github.com' in (u or '') for u in urls)}")


TESTS = {"loop": test_loop, "image_tool": test_image_tool,
         "schema_tools": test_schema_tools, "search_probe": test_search_probe}


def main(argv: list[str]) -> int:
    if not API_KEY:
        print(NO_KEY_HELP)
        return 2
    names = argv or list(TESTS)
    unknown = [n for n in names if n not in TESTS]
    if unknown:
        print(f"未知的測試：{unknown}；可用：{list(TESTS)}")
        return 2
    print(f"base_url={BASE_URL} model={MODEL}")
    failed = []
    for name in names:
        print(f"\n== {name}")
        try:
            TESTS[name]()
        except Exception as e:  # spike：記錄後繼續
            print(f"  FAILED: {type(e).__name__}: {e}")
            failed.append(name)
    print(f"\n結果：{len(names) - len(failed)}/{len(names)} 跑完" + (f"；失敗：{failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
