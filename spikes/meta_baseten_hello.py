#!/usr/bin/env python3
"""Spike：透過 Baseten Model APIs 呼叫 Muse Spark Open（OpenAI 相容端點）。

驗證什麼：
  1. 金鑰與 base URL 是否可用；目標 model slug 是否在 /v1/models 裡。
  2. 用「候選 repo 初篩」的提示詞跑一次，看輸出能不能解析成 JSON、
     用了多少 token（含推理 token）、延遲多少、rate limit header 是多少。
  3. （--tools）用強制 tool calling 取得結構化結果，當作 JSON schema 的替代。
     Baseten 文件寫明 Muse Spark Open 不強制 json_schema / json_object。

怎麼跑：
  export BASETEN_API_KEY=...        # https://app.baseten.co/settings/api_keys
  export BASETEN_MODEL=meta-models/muse-spark-open-1026   # 選填；預設就是這個
  python3 spikes/meta_baseten_hello.py
  python3 spikes/meta_baseten_hello.py --tools

只用 Python 標準函式庫。沒有 BASETEN_API_KEY 時只印說明、不發任何請求。
狀態：2026-10-29 實測通過（一般模式與 --tools；限額 100 RPM、2M TPM）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASETEN_BASE_URL", "https://inference.baseten.co/v1")
# 比賽規則（docs/hackathon-rules.md 第 6 節）要求用 -1026；Baseten 公開文件只列 meta-models/muse-spark-open。
MODEL = os.environ.get("BASETEN_MODEL", "meta-models/muse-spark-open-1026")
FALLBACK_MODEL = "meta-models/muse-spark-open"

# Baseten 公開牌價（meta-models/muse-spark-open，USD / 1M tokens，2026-10-28 查）。-1026 的價格未驗證。
PRICE_IN, PRICE_CACHED, PRICE_OUT = 1.25, 0.15, 4.25

HELP = """\
沒有設定 BASETEN_API_KEY，不發請求。

1. 到 https://app.baseten.co/ 註冊，Settings → API Keys 建立金鑰。
2. 比賽的 $100 credits + 2M TPM 要另外申請（審核制、限量），
   入口在比賽 Participant Guide（cerebralvalley.ai，需登入）。
3. export BASETEN_API_KEY=...  （放 .env，不要 commit）
4. 選填：export BASETEN_MODEL=meta-models/muse-spark-open-1026
5. python3 spikes/meta_baseten_hello.py [--tools]
"""

SYSTEM_PROMPT = """\
You triage GitHub repositories for a software directory.
Decide whether the repository is installable, usable software (not a tutorial,
list, dataset, homework, or config dump) and pick one category.
Reply with ONE JSON object and nothing else, using exactly these keys:
{"is_software": bool, "category": "dev_cli" | "local_ai" | "other" | "not_software",
 "confidence": number between 0 and 1, "reason": string under 30 words}"""

# 測試用的假資料（虛構 repo），不是真實專案。
SAMPLE_REPO = """\
repo: example-user/tinyfind
description: A fast, single-binary file finder with fuzzy matching
topics: cli, rust, search
stars: 41
latest_release: v0.4.2 (2026-10-12)
README (truncated):
# tinyfind
Install: `cargo install tinyfind` or `brew install example-user/tap/tinyfind`.
Usage: `tf <pattern> [path]` searches file names with fuzzy matching and respects .gitignore.
Works on macOS, Linux and Windows. MIT license.
"""

TRIAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "record_triage",
        "description": "Record the triage decision for one repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "is_software": {"type": "boolean"},
                "category": {
                    "type": "string",
                    "enum": ["dev_cli", "local_ai", "other", "not_software"],
                },
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["is_software", "category", "confidence", "reason"],
            "additionalProperties": False,
        },
    },
}

REQUIRED_KEYS = {"is_software", "category", "confidence", "reason"}


def request(method: str, path: str, api_key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode())
            return payload, dict(resp.headers), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode(errors="replace")[:500]
        except Exception as read_err:  # 例如 proxy 截斷 body
            detail = f"（讀不到錯誤內容：{type(read_err).__name__}）"
        print(f"HTTP {e.code} on {method} {path}: {detail}")
        if e.code == 401:
            print("→ 401：沒帶 Authorization header。")
        elif e.code == 403:
            print("→ 403：金鑰無效（Baseten 回 'please check the api-key you provided'）。")
        elif e.code == 404:
            print(f"→ 404：找不到 model。可試 BASETEN_MODEL={FALLBACK_MODEL}")
        elif e.code == 429:
            print("→ 429：超過 RPM/TPM。看 x-ratelimit-* header，退避後重試。")
        sys.exit(1)


def print_rate_limits(headers: dict) -> None:
    keys = [k for k in headers if k.lower().startswith("x-ratelimit")]
    for k in sorted(keys):
        print(f"  {k}: {headers[k]}")
    if not keys:
        print("  （回應沒有 x-ratelimit-* header）")


def print_usage(usage: dict) -> None:
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    cost = ((prompt - cached) * PRICE_IN + cached * PRICE_CACHED + completion * PRICE_OUT) / 1e6
    print(f"  usage: {json.dumps(usage)}")
    print(f"  估算費用（牌價）: ${cost:.5f}")


def parse_json_text(text: str) -> dict | None:
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        obj = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def main() -> None:
    api_key = os.environ.get("BASETEN_API_KEY", "").strip()
    if not api_key:
        print(HELP)
        return

    use_tools = "--tools" in sys.argv[1:]
    print(f"base_url={BASE_URL}  model={MODEL}")

    # 1. 列出可用 model
    models, _, _ = request("GET", "/models", api_key)
    ids = [m.get("id", "") for m in models.get("data", [])]
    muse = [i for i in ids if "muse" in i.lower()]
    print(f"[models] 共 {len(ids)} 個；含 muse 的：{muse or '無'}")
    if MODEL not in ids:
        print(f"  注意：{MODEL} 不在 /v1/models 清單（清單不一定完整，仍會嘗試呼叫）。")

    # 2. 初篩分類（prompt 要求 JSON；Baseten 不強制 JSON，所以自己驗證）
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": SAMPLE_REPO},
        ],
        # Muse Spark Open 一定會推理；預設 xhigh，批次工作務必設 low。
        "reasoning_effort": "low",
        "max_tokens": 4096,
        "temperature": 1.0,
        "top_p": 1.0,
    }
    if use_tools:
        body["tools"] = [TRIAGE_TOOL]
        body["tool_choice"] = {"type": "function", "function": {"name": "record_triage"}}

    resp, headers, elapsed = request("POST", "/chat/completions", api_key, body)
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    print(f"[chat] {elapsed:.1f}s  finish_reason={choice.get('finish_reason')}  "
          f"reasoning={len(reasoning)} chars")
    print_usage(resp.get("usage") or {})
    print("[rate limits]")
    print_rate_limits(headers)

    if use_tools:
        calls = msg.get("tool_calls") or []
        print(f"[tool_calls] {len(calls)} 個")
        for c in calls:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = None
            ok = isinstance(args, dict) and REQUIRED_KEYS <= set(args)
            print(f"  {fn.get('name')}: {fn.get('arguments')}  schema_ok={ok}")
        if not calls:
            print(f"  沒有 tool call；content={msg.get('content')!r}")
    else:
        content = msg.get("content") or ""
        obj = parse_json_text(content)
        ok = obj is not None and REQUIRED_KEYS <= set(obj)
        print(f"[content] {content!r}")
        print(f"  json_ok={obj is not None}  schema_ok={ok}")


if __name__ == "__main__":
    main()
