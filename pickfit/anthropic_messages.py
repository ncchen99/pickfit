"""Anthropic's Messages API behind call_meta's request and response shapes.

pickfit's callers build Chat Completions or Responses requests (messages or instructions + input, function
tools, a JSON schema, image parts) and read the answer in the same shapes. Rather than rewrite every caller,
call_meta sends those requests to Claude through this module:

- to_request(): one Chat or Responses request -> keyword arguments for `client.messages.create`.
  - System and developer messages, and Responses `instructions`, become the top-level `system`, marked as a
    cache breakpoint: the instructions are the part many calls share, the sources after them differ.
  - Image parts (data URLs or https URLs) become image blocks; a video part is refused (Claude takes none).
  - Function tools become tools with `input_schema`; tool calls and their outputs become tool_use and
    tool_result blocks, with every tool_result first in its user message as the API requires.
  - A JSON schema (`response_format` or `text.format`) becomes `output_config.format`, with nullable type
    lists rewritten as anyOf (claude_schema). A schema Claude cannot compile, such as the extraction's with
    its 49 nullable fields against a limit of 16, goes in the system prompt instead, and the JSON object is
    cut out of the answer; the caller's own validation is then the only check.
  - A forced tool call is not sent as one (current Claude models refuse a forced `tool_choice`): its
    parameters become the output schema, and from_message() hands the JSON back as that tool call.
  - Reasoning effort becomes `output_config.effort`; thinking is adaptive and cannot be switched off.
  - A conversation with earlier assistant turns also gets automatic caching, so a loop reads its history
    from the cache and writes only what the last turn added.
- from_message(): the Message -> the raw response the endpoint would have returned (a chat.completion or a
  Responses object), with usage in that endpoint's field names.

Thinking blocks must go back unchanged in the conversation that produced them. Every Responses output item
and every Chat assistant message therefore carries its original block(s) (`anthropic_block`,
`anthropic_content`), and to_request() sends those back verbatim when the caller replays its history.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic

EFFORT = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}

# A classifier decline is retried on the model Anthropic recommends for its category, inside the same call
# (beta). Haiku has no server-side fallback: there a decline stays a decline.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"})

# Above this many output tokens a request is streamed: a long generation can outlast an HTTP timeout.
STREAM_ABOVE_TOKENS = 16_000

# Request keys with no counterpart that are safe to leave out: server-side storage and cache hints.
_IGNORED_KEYS = frozenset({"store", "include", "prompt_cache_key", "user", "metadata", "truncation"})
_CHAT_KEYS = frozenset({"model", "messages", "tools", "tool_choice", "response_format", "max_completion_tokens",
                        "reasoning_effort", "parallel_tool_calls", "n"})
_RESPONSES_KEYS = frozenset({"model", "instructions", "input", "tools", "tool_choice", "text", "reasoning",
                             "max_output_tokens", "parallel_tool_calls"})

_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "tool_calls", "max_tokens": "length",
           "model_context_window_exceeded": "length", "refusal": "content_filter", "pause_turn": "length"}
_INCOMPLETE = {"max_tokens": "max_output_tokens", "model_context_window_exceeded": "max_output_tokens",
               "refusal": "content_filter", "pause_turn": "pause_turn"}


# Claude compiles an output schema into a grammar and refuses one with more union-typed parameters than
# this (nullable fields count). pickfit's extraction schema has 49, so it is asked for in the prompt instead.
UNION_LIMIT = 16
SCHEMA_NOTE = ("Reply with one JSON object that is valid against the JSON Schema below, and nothing else: no "
               "words before or after it, no code fence. Every required property must be present; use null "
               "where the schema allows null and you have no value, and never put null where the schema asks "
               "for an object: write the object with its own properties null.\n"
               "<json_schema>\n{schema}\n</json_schema>")
# Schemas the API refused as an output format in this process (by hash): asked for in the prompt from then on.
_refused_schemas: set[str] = set()


@dataclass(frozen=True)
class Plan:
    """What to_request() changed that from_message() has to undo."""

    endpoint: str
    forced_tool: str | None = None  # the tool whose call the JSON answer stands for
    prompted_schema: bool = False  # the schema went in the prompt, so the JSON is cut out of the answer


# ---------------------------------------------------------------- request


def _image_block(url: str) -> dict[str, Any]:
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _blocks(content: Any) -> list[dict[str, Any]]:
    """Chat or Responses message content as content blocks; empty text is dropped (the API refuses it)."""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content.strip() else []
    blocks: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            blocks += _blocks(part)
            continue
        kind = part.get("type")
        if kind in ("text", "input_text", "output_text"):
            blocks += _blocks(part.get("text"))
        elif kind in ("image_url", "input_image"):
            image = part.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
            if not isinstance(url, str) or not url:
                raise ValueError("an image part needs a data: or https: URL (file ids are not supported)")
            blocks.append(_image_block(url))
        elif kind in ("video_url", "input_video"):
            raise ValueError("Claude models take no video input; send video to model 'open-modal'")
        elif kind == "refusal":
            continue
        else:
            raise ValueError(f"content part {kind!r} has no Anthropic counterpart")
    return blocks


def _text(content: Any) -> str:
    return "\n".join(b["text"] for b in _blocks(content) if b["type"] == "text")


def _tool_input(arguments: Any) -> dict[str, Any]:
    """A tool call's arguments as the object the API wants; text that is not a JSON object is kept under a key."""
    if isinstance(arguments, dict):
        return arguments
    try:
        value = json.loads(arguments or "{}")
    except (TypeError, json.JSONDecodeError):
        return {"_raw": str(arguments)}
    return value if isinstance(value, dict) else {"_raw": value}


class _Conversation:
    """Messages in the order given, with consecutive same-role turns merged into one."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def add(self, role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if self.messages and self.messages[-1]["role"] == role:
            self.messages[-1]["content"] += blocks
        else:
            self.messages.append({"role": role, "content": list(blocks)})

    def done(self) -> list[dict[str, Any]]:
        for message in self.messages:
            if message["role"] == "user":  # tool results come first in their message
                message["content"].sort(key=lambda b: b["type"] != "tool_result")
        if not self.messages or self.messages[0]["role"] != "user":
            self.messages.insert(0, {"role": "user", "content": [{"type": "text", "text": "(no input)"}]})
        return self.messages


def _tool_result(call_id: Any, output: Any) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": str(call_id), "content": _blocks(output) or "(no output)"}


def _chat_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system: list[str] = []
    talk = _Conversation()
    for m in messages:
        role = m.get("role")
        if role in ("system", "developer"):
            system.append(_text(m.get("content")))
        elif role == "user":
            talk.add("user", _blocks(m.get("content")))
        elif role == "assistant":
            carried = m.get("anthropic_content")
            if carried is not None:
                talk.add("assistant", list(carried))
                continue
            blocks = _blocks(m.get("content"))
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                blocks.append({"type": "tool_use", "id": str(call.get("id")), "name": fn.get("name", ""),
                               "input": _tool_input(fn.get("arguments"))})
            talk.add("assistant", blocks)
        elif role == "tool":
            talk.add("user", [_tool_result(m.get("tool_call_id"), m.get("content"))])
        else:
            raise ValueError(f"message role {role!r} has no Anthropic counterpart")
    return "\n\n".join(s for s in system if s), talk.done()


def _responses_messages(instructions: Any, items: Any) -> tuple[str, list[dict[str, Any]]]:
    system = [instructions] if isinstance(instructions, str) and instructions else []
    talk = _Conversation()
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    for item in items or []:
        if "anthropic_block" in item:  # our own earlier answer, replayed: the block as it came
            talk.add("assistant", [item["anthropic_block"]])
            continue
        kind = item.get("type") or "message"
        if kind == "message":
            role = item.get("role")
            if role in ("system", "developer"):
                system.append(_text(item.get("content")))
            elif role in ("user", "assistant"):
                talk.add(role, _blocks(item.get("content")))
            else:
                raise ValueError(f"message role {role!r} has no Anthropic counterpart")
        elif kind == "function_call":
            talk.add("assistant", [{"type": "tool_use", "id": str(item.get("call_id")), "name": item.get("name", ""),
                                    "input": _tool_input(item.get("arguments"))}])
        elif kind == "function_call_output":
            talk.add("user", [_tool_result(item.get("call_id"), item.get("output"))])
        elif kind == "reasoning":
            continue  # another provider's reasoning item: nothing Claude can read
        else:
            raise ValueError(f"input item {kind!r} has no Anthropic counterpart")
    return "\n\n".join(s for s in system if s), talk.done()


def _tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = []
    for tool in tools or []:
        if tool.get("type") != "function":
            raise ValueError(f"tool type {tool.get('type')!r} is not wired for Claude models")
        fn = tool.get("function") or tool  # Chat nests the definition, Responses does not
        spec: dict[str, Any] = {"name": fn["name"],
                                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}}
        if fn.get("description"):
            spec["description"] = fn["description"]
        if fn.get("strict"):
            spec["strict"] = True
            spec["input_schema"] = claude_schema(spec["input_schema"])
        out.append(spec)
    return out


def _schema(request: dict[str, Any], endpoint: str) -> tuple[dict[str, Any] | None, bool]:
    """(the JSON schema the answer must follow, whether any JSON object was asked for without one)."""
    fmt = request.get("response_format") if endpoint == "chat" else (request.get("text") or {}).get("format")
    if not fmt or fmt.get("type") == "text":
        return None, False
    if fmt.get("type") == "json_object":
        return None, True
    if fmt.get("type") != "json_schema":
        raise ValueError(f"output format {fmt.get('type')!r} has no Anthropic counterpart")
    spec = fmt.get("json_schema") if endpoint == "chat" else fmt
    return spec["schema"], False


def claude_schema(node: Any) -> Any:
    """A strict schema as Claude's structured outputs take it. pickfit's schemas say "nullable" as a type
    list (`"type": ["string", "null"]`, Meta's strict form), which Claude refuses next to an enum; here it
    becomes `anyOf` with null, at every level."""
    if not isinstance(node, dict):
        return node
    out = dict(node)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {name: claude_schema(sub) for name, sub in out["properties"].items()}
    if isinstance(out.get("items"), dict):
        out["items"] = claude_schema(out["items"])
    if isinstance(out.get("anyOf"), list):
        out["anyOf"] = [claude_schema(option) for option in out["anyOf"]]
    kinds = out.get("type")
    if not (isinstance(kinds, list) and "null" in kinds and len(kinds) == 2):
        return out
    inner = {key: value for key, value in out.items() if key != "description"}
    inner["type"] = next(kind for kind in kinds if kind != "null")
    if "enum" in inner:
        inner["enum"] = [value for value in inner["enum"] if value is not None]
    nullable: dict[str, Any] = {"anyOf": [inner, {"type": "null"}]}
    return {"description": out["description"], **nullable} if "description" in out else nullable


def union_count(node: Any) -> int:
    """Parameters of a schema with a union type (anyOf or a type list): what UNION_LIMIT counts."""
    if not isinstance(node, dict):
        return 0
    own = 1 if "anyOf" in node or isinstance(node.get("type"), list) else 0
    children = [*(node.get("properties") or {}).values(), *(node.get("anyOf") or [])]
    if isinstance(node.get("items"), dict):
        children.append(node["items"])
    return own + sum(union_count(child) for child in children)


def _schema_key(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()


def _json_text(text: str) -> str:
    """The JSON object in an answer whose schema was asked for in the prompt: a code fence or words around
    the object are dropped. What is left is still validated by the caller."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text.strip()


def _forced_tool(choice: Any) -> str | None:
    if isinstance(choice, dict) and choice.get("type") == "function":
        return (choice.get("function") or choice).get("name")
    return None


def to_request(endpoint: str, request: dict[str, Any], *, fallbacks: bool = True,
               prompt_schema: bool = False) -> tuple[dict[str, Any], Plan]:
    """Keyword arguments for `messages.create` from one Chat or Responses request, and the plan to read
    the answer back. Raises ValueError for anything that has no counterpart, rather than dropping it.

    A JSON schema is sent as the output format, which guarantees the answer follows it, unless Claude
    cannot compile it (more than UNION_LIMIT union-typed parameters, or `prompt_schema`: the API refused
    it): then the schema goes in the system prompt and the caller's own validation is the check."""
    known = _CHAT_KEYS if endpoint == "chat" else _RESPONSES_KEYS
    unknown = request.keys() - known - _IGNORED_KEYS
    if unknown:
        raise ValueError(f"request keys {sorted(unknown)} have no Anthropic counterpart")
    if endpoint == "chat":
        system, messages = _chat_messages(request.get("messages") or [])
        max_tokens, effort = request["max_completion_tokens"], request.get("reasoning_effort")
        summary = False
    else:
        system, messages = _responses_messages(request.get("instructions"), request.get("input"))
        reasoning = request.get("reasoning") or {}
        max_tokens, effort = request["max_output_tokens"], reasoning.get("effort")
        summary = bool(reasoning.get("summary"))
    tools = _tools(request.get("tools"))
    schema, any_json = _schema(request, endpoint)
    choice = request.get("tool_choice")
    forced = _forced_tool(choice)
    notes: list[str] = []
    tool_choice: dict[str, Any] | None = None
    if forced:
        match = next((t for t in tools if t["name"] == forced), None)
        if match is None:
            raise ValueError(f"tool_choice names {forced!r}, which is not among the tools")
        schema, tools = match["input_schema"], []
        notes.append(f"Your reply is passed on as the `{forced}` call: reply with the JSON object of its arguments.")
    elif choice == "required":
        notes.append("Answer by calling one of the tools.")
    elif choice == "none":
        tool_choice = {"type": "none"}
    elif choice not in (None, "auto"):
        raise ValueError(f"tool_choice {choice!r} has no Anthropic counterpart")
    if any_json:
        notes.append("Reply with one JSON object and nothing else.")
    if request.get("parallel_tool_calls") is False and tools and tool_choice is None:
        tool_choice = {"type": "auto", "disable_parallel_tool_use": True}

    output_config: dict[str, Any] = {"effort": EFFORT[effort or "low"]}
    prompted = False
    if schema is not None:
        compiled = claude_schema(schema)
        prompted = prompt_schema or _schema_key(schema) in _refused_schemas or union_count(compiled) > UNION_LIMIT
        if prompted:
            notes.append(SCHEMA_NOTE.format(schema=json.dumps(schema, ensure_ascii=False, separators=(",", ":"))))
        else:
            output_config["format"] = {"type": "json_schema", "schema": compiled}
    system = "\n\n".join(s for s in (system, *notes) if s)
    kwargs: dict[str, Any] = {"model": request["model"], "max_tokens": max_tokens, "messages": messages,
                              "output_config": output_config}
    if system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice
    if summary:
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
    if any(m["role"] == "assistant" for m in messages):
        kwargs["cache_control"] = {"type": "ephemeral"}
    if fallbacks and request["model"] in FALLBACK_MODELS:
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return kwargs, Plan(endpoint=endpoint, forced_tool=forced, prompted_schema=prompted)


# ---------------------------------------------------------------- response


def _usage(usage: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """Anthropic counts uncached, cache-written and cache-read input apart; pickfit's input includes all three."""
    written = usage.get("cache_creation_input_tokens") or 0
    read = usage.get("cache_read_input_tokens") or 0
    total_in = (usage.get("input_tokens") or 0) + written + read
    out = usage.get("output_tokens") or 0
    details = {"cached_tokens": read, "cache_write_tokens": written}
    if endpoint == "chat":
        return {"prompt_tokens": total_in, "completion_tokens": out, "total_tokens": total_in + out,
                "prompt_tokens_details": details}
    return {"input_tokens": total_in, "output_tokens": out, "total_tokens": total_in + out,
            "input_tokens_details": details}


def served_by_fallback(message: dict[str, Any]) -> bool:
    """Whether a fallback model wrote the answer (the documented signal: a fallback_message iteration)."""
    iterations = (message.get("usage") or {}).get("iterations") or []
    return any(isinstance(i, dict) and i.get("type") == "fallback_message" for i in iterations)


def from_message(message: dict[str, Any], plan: Plan) -> dict[str, Any]:
    """The Message as the raw chat.completion or Responses object the endpoint's callers read."""
    content = message.get("content") or []
    stop = message.get("stop_reason")
    texts = [b.get("text") or "" for b in content if b.get("type") == "text"]
    thoughts = [b.get("thinking") or "" for b in content if b.get("type") == "thinking"]
    calls = [b for b in content if b.get("type") == "tool_use"]
    extra: dict[str, Any] = {}
    if stop == "refusal":
        extra["stop_details"] = message.get("stop_details")
    if served_by_fallback(message):
        extra["fallback_model"] = message.get("model")
    if plan.prompted_schema:
        extra["schema_in_prompt"] = True
    answer = _json_text("".join(texts)) if plan.prompted_schema else "".join(texts)
    forced = plan.forced_tool if stop in ("end_turn", "stop_sequence") and answer else None

    if plan.endpoint == "chat":
        tool_calls = [{"id": b.get("id"), "type": "function",
                       "function": {"name": b.get("name", ""),
                                    "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}}
                      for b in calls]
        if forced:
            tool_calls = [{"id": f"forced_{message.get('id')}", "type": "function",
                           "function": {"name": forced, "arguments": answer}}]
        reply: dict[str, Any] = {"role": "assistant", "content": None if forced else (answer or None),
                                 "anthropic_content": content}
        if tool_calls:
            reply["tool_calls"] = tool_calls
        if any(thoughts):
            reply["reasoning_content"] = "\n".join(t for t in thoughts if t)
        finish = "tool_calls" if forced else _FINISH.get(stop or "", "stop")
        return {"id": message.get("id"), "object": "chat.completion", "created": int(time.time()),
                "model": message.get("model"), "choices": [{"index": 0, "message": reply, "finish_reason": finish}],
                "usage": _usage(message.get("usage") or {}, "chat"), **extra}

    items: list[dict[str, Any]] = []
    for block in content:
        kind = block.get("type")
        if kind == "thinking":
            summary = [{"type": "summary_text", "text": block["thinking"]}] if block.get("thinking") else []
            items.append({"type": "reasoning", "summary": summary, "anthropic_block": block})
        elif kind == "text" and forced:
            continue  # handed back below as the forced tool call
        elif kind == "text":
            said = _json_text(block.get("text") or "") if plan.prompted_schema else block.get("text") or ""
            items.append({"type": "message", "role": "assistant",
                          "content": [{"type": "output_text", "text": said}], "anthropic_block": block})
        elif kind == "tool_use":
            items.append({"type": "function_call", "call_id": block.get("id"), "name": block.get("name", ""),
                          "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                          "anthropic_block": block})
        else:  # e.g. a fallback switch point: kept so a replay sends it back
            items.append({"type": "anthropic_block", "anthropic_block": block})
    if forced:
        items.append({"type": "function_call", "call_id": f"forced_{message.get('id')}", "name": forced,
                      "arguments": answer})
    incomplete = _INCOMPLETE.get(stop or "")
    return {"id": message.get("id"), "object": "response", "model": message.get("model"),
            "status": "incomplete" if incomplete else "completed",
            "incomplete_details": {"reason": incomplete} if incomplete else None,
            "output": items, "usage": _usage(message.get("usage") or {}, "responses"), **extra}


# ---------------------------------------------------------------- send


def _to_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else obj.to_dict(mode="json")


def send(client: Any, endpoint: str, request: dict[str, Any], stream: bool = False, *,
         fallbacks: bool = True) -> dict[str, Any]:
    """Send one Chat or Responses request to Claude and return the raw response in that endpoint's shape.

    An output schema the API refuses (a 400 before anything is generated or billed) is remembered and
    sent again at once with the schema in the prompt instead."""
    kwargs, plan = to_request(endpoint, request, fallbacks=fallbacks)
    try:
        message = _post(client, kwargs, stream)
    except anthropic.BadRequestError as err:
        schema = _schema(request, endpoint)[0]
        if schema is None or plan.prompted_schema or "schema" not in str(err).lower():
            raise
        _refused_schemas.add(_schema_key(schema))
        kwargs, plan = to_request(endpoint, request, fallbacks=fallbacks, prompt_schema=True)
        message = _post(client, kwargs, stream)
    return from_message(_to_dict(message), plan)


def _post(client: Any, kwargs: dict[str, Any], stream: bool) -> Any:
    api = client.beta.messages if "betas" in kwargs else client.messages
    if stream or kwargs["max_tokens"] > STREAM_ABOVE_TOKENS:
        with api.stream(**kwargs) as events:
            return events.get_final_message()
    return api.create(**kwargs)


class _Endpoint:
    def __init__(self, owner: Client, endpoint: str) -> None:
        self._owner, self._endpoint = owner, endpoint

    def create(self, *, stream: bool = False, **request: Any) -> dict[str, Any]:
        return send(self._owner.anthropic, self._endpoint, request, stream, fallbacks=self._owner.fallbacks)


class _Chat:
    def __init__(self, owner: Client) -> None:
        self.completions = _Endpoint(owner, "chat")


class Client:
    """An Anthropic client behind the two methods call_meta calls on any provider's client:
    `chat.completions.create(**request)` and `responses.create(**request)`. Each takes the request
    call_meta built and returns the whole raw response in that endpoint's shape; a long generation is
    streamed inside, so the caller never collects a stream (`returns_whole_response`)."""

    returns_whole_response = True

    def __init__(self, client: Any, *, fallbacks: bool = True) -> None:
        self.anthropic = client
        self.fallbacks = fallbacks
        self.api_key = getattr(client, "api_key", None)
        self.chat = _Chat(self)
        self.responses = _Endpoint(self, "responses")
