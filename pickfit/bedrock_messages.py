"""Claude on Amazon Bedrock behind call_meta's request and response shapes.

Bedrock serves the same Claude models as Anthropic's API, billed by AWS. pickfit reaches them through the
Anthropic SDK's Bedrock client (InvokeModel on the `bedrock-runtime` endpoint, signed with an IAM key), so a
request is the Messages request pickfit.anthropic_messages builds and the answer is the same Message. This
module holds what differs, as AWS's and Anthropic's pages had it on 2026-11-21
(docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html,
platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy); no call had been made yet:

- The model is named by an inference profile. `global.anthropic.claude-opus-5-5` routes to any commercial
  Region at Anthropic's list price; a geographic profile (us., eu., jp., au.) or a single Region costs 10% more.
  Only the global profile can be called from Taipei (ap-east-2). A model without an entry in MODELS is refused:
  pickfit never moves a call to another model because of where it is sent.
- Automatic caching (a top-level `cache_control`) is not taken by InvokeModel, so the breakpoint
  anthropic_messages asks for there is put on the last block of the request, which is where automatic caching
  puts it. The system prompt's own breakpoint goes through as it is.
- Image blocks must carry their bytes: an image URL is refused here rather than sent to be refused there.
- No server-side `fallbacks` and no Message Batches. A request Claude declines on Bedrock is sent again on the
  direct API (pickfit.meta), which retries it on Anthropic's fallback model; batches stay on the direct API
  (pickfit.msg_batch), and Bedrock's own batch tier does not offer these models.
- Usage arrives in Anthropic's fields (input, cache_creation_input_tokens, cache_read_input_tokens), and is read
  by anthropic_messages as the direct API's is. One case is filled in here: a response that reports cache writes
  without saying how many were written for an hour, to a request that asked for an hour, has them all counted at
  the hour's price (2x input), so the ledger is never under what AWS bills.
"""

from __future__ import annotations

from typing import Any

import anthropic

from pickfit import anthropic_messages
from pickfit.anthropic_messages import Plan

# pickfit's model id -> Bedrock's. The same model on both sides, or no entry.
MODELS = {"claude-opus-5-5": "anthropic.claude-opus-5-5", "claude-haiku-5-5": "anthropic.claude-haiku-5-5"}
PROFILE = "global"  # cross-Region routing with no price premium; PRICES in pickfit.meta are this profile's
DEFAULT_REGION = "ap-east-2"  # where the request is signed for and sent; the profile decides where it runs
_MARKABLE = frozenset({"text", "image", "document", "tool_use", "tool_result"})  # blocks that take cache_control


class NotOnBedrock(ValueError):
    """Bedrock has no entry for this model (pickfit.meta raises its own ModelRefused from it)."""


def offers(model: str) -> bool:
    return model in MODELS


def wire_model(model: str) -> str:
    """The inference profile id a pickfit model id is sent as; NotOnBedrock when Bedrock is not known to
    serve that model."""
    try:
        return f"{PROFILE}.{MODELS[model]}"
    except KeyError:
        raise NotOnBedrock(f"{model} has no Amazon Bedrock model id in pickfit.bedrock_messages.MODELS; "
                           "it is not sent as another model") from None


# ---------------------------------------------------------------- request


def _refuse_image_urls(blocks: Any) -> None:
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image" and (block.get("source") or {}).get("type") == "url":
            raise ValueError("Amazon Bedrock takes no image URLs: send the image as a data: URL, "
                             "or call with provider='anthropic'")
        _refuse_image_urls(block.get("content"))  # a tool result's own blocks


def _mark_last_block(messages: list[dict[str, Any]], control: dict[str, Any]) -> list[dict[str, Any]]:
    """The messages with `control` as the cache breakpoint of the last block that can take one. Only the
    message and block it lands on are copied: a replayed block is never changed in the caller's history."""
    for at in range(len(messages) - 1, -1, -1):
        content = messages[at]["content"]
        for index in range(len(content) - 1, -1, -1):
            if content[index].get("type") in _MARKABLE:
                marked = [*content[:index], {**content[index], "cache_control": dict(control)}, *content[index + 1:]]
                return [*messages[:at], {**messages[at], "content": marked}, *messages[at + 1:]]
    return messages


def to_request(endpoint: str, request: dict[str, Any], *, prompt_schema: bool = False,
               conversation: bool = False) -> tuple[dict[str, Any], Plan]:
    """Keyword arguments for the Bedrock client's `messages.create` from one Chat or Responses request, and
    the plan to read the answer back: anthropic_messages.to_request's, without `fallbacks`, with the
    automatic cache breakpoint made explicit."""
    kwargs, plan = anthropic_messages.to_request(endpoint, request, fallbacks=False, prompt_schema=prompt_schema,
                                                 conversation=conversation)
    for message in kwargs["messages"]:
        _refuse_image_urls(message["content"])
    control = kwargs.pop("cache_control", None)
    if control:
        kwargs["messages"] = _mark_last_block(kwargs["messages"], control)
    return kwargs, plan


# ---------------------------------------------------------------- response


def _asked_for_an_hour(kwargs: dict[str, Any]) -> bool:
    blocks = [*(kwargs.get("system") or []), *(b for m in kwargs["messages"] for b in m["content"])]
    return any(isinstance(b, dict) and (b.get("cache_control") or {}).get("ttl") == "1h" for b in blocks)


def with_usage(message: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    """The Message with its cache writes split by lifetime, as anthropic_messages reads them. Bedrock is not
    documented to return the split (`cache_creation`): without it, writes to a request with an hour's
    breakpoint are all an hour's, the dearer of the two."""
    usage = message.get("usage") or {}
    written = usage.get("cache_creation_input_tokens") or 0
    if not written or usage.get("cache_creation") or not _asked_for_an_hour(kwargs):
        return message
    split = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": written}
    return {**message, "usage": {**usage, "cache_creation": split}}


# ---------------------------------------------------------------- send


def send(client: Any, endpoint: str, request: dict[str, Any], stream: bool = False, *,
         conversation: bool = False) -> dict[str, Any]:
    """Send one Chat or Responses request to Claude on Bedrock and return the raw response in that endpoint's
    shape. As on the direct API, an output schema the model refuses to compile (a 400, nothing billed) is
    remembered and sent again at once in the prompt."""
    kwargs, plan = to_request(endpoint, request, conversation=conversation)
    try:
        message = anthropic_messages._post(client, kwargs, stream)
    except anthropic.BadRequestError as err:
        schema = anthropic_messages._schema(request, endpoint)[0]
        if schema is None or plan.prompted_schema or "schema" not in str(err).lower():
            raise
        anthropic_messages._refused_schemas.add(anthropic_messages._schema_key(schema))
        kwargs, plan = to_request(endpoint, request, prompt_schema=True, conversation=conversation)
        message = anthropic_messages._post(client, kwargs, stream)
    return anthropic_messages.from_message(with_usage(anthropic_messages._to_dict(message), kwargs), plan)


class _Endpoint:
    def __init__(self, owner: Client, endpoint: str) -> None:
        self._owner, self._endpoint = owner, endpoint

    def create(self, *, stream: bool = False, conversation: bool = False, **request: Any) -> dict[str, Any]:
        return send(self._owner.bedrock, self._endpoint, request, stream, conversation=conversation)


class _Chat:
    def __init__(self, owner: Client) -> None:
        self.completions = _Endpoint(owner, "chat")


class Client:
    """The SDK's Bedrock client behind the two methods call_meta calls on any provider's client, as
    anthropic_messages.Client is for the direct API. `secret` is the signing key, kept only so that
    call_meta can scrub it from a trace or an error should it ever appear in one."""

    returns_whole_response = True

    def __init__(self, client: Any, *, secret: str | None = None) -> None:
        self.bedrock = client
        self.api_key = secret
        self.chat = _Chat(self)
        self.responses = _Endpoint(self, "responses")


def make_client(*, access_key: str, secret_key: str, region: str, base_url: str, timeout: float,
                http_client: Any = None) -> Client:
    """A Client that signs with one IAM access key (SigV4), with the SDK's retries off (call_meta retries
    itself). Nothing comes from AWS's ambient credential chain: not a profile, not a login session."""
    sdk = anthropic.AnthropicBedrock(aws_access_key=access_key, aws_secret_key=secret_key, aws_region=region,
                                     base_url=base_url, max_retries=0, timeout=timeout, http_client=http_client)
    return Client(sdk, secret=secret_key)
