"""Fakes shared by the verify tests: a scripted Box and a mocked Responses API."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import openai

from pickfit.verify.box import Box, BoxError, ExecResult

FAKE_KEY = "sk-test-0123456789abcdef-SECRET"


class FakeBox(Box):
    """Answers commands from a script: the first matching substring wins."""

    runner = "fake"
    image = "fake:1"

    def __init__(self, script: dict[str, tuple[int, str, str]] | None = None) -> None:
        self.script = script or {}
        self.files: dict[str, bytes] = {}
        self.ran: list[tuple[str, int]] = []
        self.closed = False

    def start(self) -> None:
        pass

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self.ran.append((command, timeout_s))
        for needle, (code, out, err) in self.script.items():
            if needle in command:
                return ExecResult(command, code, out, err, 0.1)
        return ExecResult(command, 0, "", "", 0.1)

    def write_file(self, path: str, content: str | bytes) -> None:
        self.files[path] = content.encode() if isinstance(content, str) else content

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        if path not in self.files:
            raise BoxError(f"cannot read {path}: No such file or directory")
        return self.files[path][:max_bytes]

    def set_network(self, enabled: bool) -> None:
        self.network_enabled = enabled

    def close(self) -> None:
        self.closed = True


def response(rid: str, *calls: tuple[str, dict[str, Any]], summary: str = "Thinking.",
             text: str | None = None, tokens: tuple[int, int] = (3000, 400)) -> dict[str, Any]:
    output: list[dict[str, Any]] = [{"type": "reasoning", "id": f"rs_{rid}",
                                     "summary": [{"type": "summary_text", "text": summary}],
                                     "encrypted_content": f"enc-{rid}"}]
    if text:
        output.append({"type": "message", "id": f"msg_{rid}", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": text, "annotations": []}]})
    for i, (name, args) in enumerate(calls):
        output.append({"type": "function_call", "id": f"fc_{rid}_{i}", "call_id": f"call_{rid}_{i}",
                       "name": name, "arguments": json.dumps(args), "status": "completed"})
    return {"id": rid, "object": "response", "created_at": 0, "model": "muse-spark-1.3-contributor",
            "status": "completed", "output": output,
            "usage": {"input_tokens": tokens[0], "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens": tokens[1], "output_tokens_details": {"reasoning_tokens": 300},
                      "total_tokens": sum(tokens)}}


class FakeServer:
    def __init__(self, *replies: dict[str, Any]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        if not self.replies:
            raise AssertionError("unexpected extra request")
        return httpx2.Response(200, json=self.replies.pop(0))

    def client(self) -> openai.OpenAI:
        return openai.OpenAI(api_key=FAKE_KEY, base_url="https://api.meta.ai/v1", max_retries=0,
                             http_client=httpx2.Client(transport=httpx2.MockTransport(self)))


def run_cmd(command: str, timeout_s: int = 120, purpose: str = "") -> tuple[str, dict[str, Any]]:
    return "run_command", {"command": command, "timeout_s": timeout_s, "purpose": purpose}


def finish(level: str = "function", steps: list[int] | None = None,
           smoke: list[dict[str, Any]] | None = None, **extra: Any) -> tuple[str, dict[str, Any]]:
    args = {"level": level, "unverified_reason": None, "tool_version": "0.10.18", "install_method": "pipx",
            "steps": [{"command_id": c, "purpose": "install"} for c in steps or []],
            "smoke_tests": smoke or [], "pitfalls": [], "blocking_error": None, "summary": "Done.", **extra}
    return "finish", args


