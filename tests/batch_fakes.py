"""A fake Message Batches client, shared by the tests of pickfit.msg_batch and of its callers."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable

from pickfit.meta import PROD_MODEL

USAGE = {"input_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 50}


def message(text: str, *, stop: str = "end_turn", mid: str = "msg_1") -> dict[str, Any]:
    return {"id": mid, "type": "message", "role": "assistant", "model": PROD_MODEL,
            "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
            "usage": USAGE}


def succeeded(text: str, **kw: Any) -> dict[str, Any]:
    return {"type": "succeeded", "message": message(text, **kw)}


def user_text(params: dict[str, Any]) -> str:
    """The text of a Messages request's first user turn."""
    return params["messages"][0]["content"][0]["text"]


class FakeBatches:
    """Answers each request from `answer(params)`; `statuses` is what retrieve() says, in turn."""

    def __init__(self, answer: Callable[[dict[str, Any]], dict[str, Any]], statuses: list[str] | None = None,
                 fail_create: bool = False) -> None:
        self.answer = answer
        self.statuses = statuses or ["in_progress", "ended"]
        self.fail_create = fail_create
        self.created: list[list[dict[str, Any]]] = []
        self.canceled: list[str] = []
        self.polls = 0

    def create(self, *, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if self.fail_create:
            raise RuntimeError("the API refused the batch")
        self.created.append(json.loads(json.dumps(requests)))
        return {"id": f"msgbatch_{len(self.created)}", "processing_status": "in_progress"}

    def retrieve(self, batch_id: str) -> dict[str, Any]:
        self.polls += 1
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"id": batch_id, "processing_status": status}

    def cancel(self, batch_id: str) -> dict[str, Any]:
        self.canceled.append(batch_id)
        self.statuses = ["canceling", "ended"]
        return {"id": batch_id, "processing_status": "canceling"}

    def results(self, batch_id: str) -> list[dict[str, Any]]:
        sent = self.created[int(batch_id.rsplit("_", 1)[1]) - 1]
        # Results come back in any order: reversed here.
        return [{"custom_id": r["custom_id"], "result": self.answer(r["params"])} for r in reversed(sent)]


def fake_client(batches: FakeBatches) -> Any:
    return SimpleNamespace(messages=SimpleNamespace(batches=batches))


class PlainClient:
    """call_meta's client for the requests sent again: whole chat.completion objects."""

    returns_whole_response = True
    api_key = None

    def __init__(self, text: str = "again") -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, *, stream: bool = False, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {"id": f"msg_plain_{len(self.calls)}", "object": "chat.completion", "model": PROD_MODEL,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": self.text}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250,
                          "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}}}
