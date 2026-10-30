#!/usr/bin/env python3
"""pickfit's MCP probe: start an MCP server over stdio and complete initialize + tools/list.

Written into each verification box (stdlib only, Python 3.8+) and run there:

    python3 ~/.pickfit/mcp_probe.py [--timeout S] [--call TOOL --args JSON] -- COMMAND [ARG ...]

What it prints is all a model or a person sees of the server. Tool, argument and server names
are cut down to safe characters. Tool descriptions never leave the box: the probe checks them
for instruction-like text aimed at the calling agent ("tool poisoning") and prints only the
names of the patterns that matched. The last line is `pickfit-mcp: <JSON>`, which pickfit
parses; every value in it is one of those reduced names, a count or a version string.

Exit codes: 0 the handshake completed (and the tool call, when asked, returned no error);
1 usage; 2 the server exited or closed stdout first; 3 it timed out; 4 a protocol error, or
no tools; 5 the tool call returned an error.
"""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time

PROTOCOL_VERSION = "2025-06-18"
MARKER = "pickfit-mcp: "
NAME_MAX = 64
MAX_TOOLS_SHOWN = 200
MAX_ARGS_SHOWN = 12
MAX_PAGES = 20
STDERR_KEEP = 4000
RESULT_SHOWN = 200

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_.:/-]")
_UNSAFE_VERSION = re.compile(r"[^A-Za-z0-9_.+-]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤﻿]")

# Instruction-like text aimed at the agent that reads the tool list, as published tool-poisoning
# examples write it. Each pattern needs wording a plain description of a tool does not use.
FLAGS = (
    ("instruction_tag", re.compile(r"<\s*/?\s*(important|system|instructions?|secret|hidden|admin)\b[^>]*>"
                                   r"|\[\s*(important|system|instructions?)\s*\]", re.I)),
    ("override", re.compile(r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|other|all)\b"
                            r".{0,20}\b(instructions?|prompts?|rules|messages)\b", re.I | re.S)),
    ("conceal_from_user", re.compile(r"\b(do not|don't|never|without)\b.{0,20}\b(tell|telling|inform|informing|"
                                     r"mention|mentioning|notify|notifying|alert|alerting|reveal|revealing|show|"
                                     r"showing)\b.{0,20}\b(the )?user\b", re.I | re.S)),
    ("side_channel", re.compile(r"\bas a side ?note\b|\bsidenote\b|\bpass (its|the|their) (content|contents)\b", re.I)),
    ("sensitive_files", re.compile(r"\b(read|cat|open|include|send|pass|upload|attach)\b.{0,60}"
                                   r"(~/\.ssh|id_rsa|id_ed25519|\.aws/credentials|/etc/passwd|\.netrc|"
                                   r"mcp\.json|claude_desktop_config|\.cursor/|\.env\b)", re.I | re.S)),
    ("other_tools", re.compile(r"\b(before|after|instead of|when) (calling|using|you (call|use)) (any|another|"
                               r"other|the \w+|every)\b.{0,15}\btools?\b", re.I)),
    ("hidden_unicode", re.compile("[​-‏‪-‮⁠-⁤﻿\U000e0000-\U000e007f]")),
)


def safe_name(value: object) -> str:
    text = value if isinstance(value, str) else ""
    return (_UNSAFE_NAME.sub("?", text)[:NAME_MAX]) or "?"


def safe_version(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return _UNSAFE_VERSION.sub("?", value)[:40]


def _strings(node: object, depth: int = 0) -> list[str]:
    """Every string in a JSON value (descriptions, titles, enum labels), not too deep."""
    if depth > 8:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value, depth + 1)]
    if isinstance(node, list):
        return [s for value in node for s in _strings(value, depth + 1)]
    return []


def flags_for(tool: dict) -> list[str]:
    """Pattern names that match a tool's description, title, annotations or input schema text."""
    texts = _strings({k: v for k, v in tool.items() if k != "name"})
    raw_name = tool.get("name") if isinstance(tool.get("name"), str) else ""
    text = "\n".join(texts)
    found = [label for label, pattern in FLAGS if pattern.search(text)]
    if "hidden_unicode" not in found and FLAGS[-1][1].search(raw_name):
        found.append("hidden_unicode")
    return found


def arg_names(tool: dict) -> list[str]:
    schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
    return [safe_name(name) + ("*" if name in required else "") for name in list(props)[:MAX_ARGS_SHOWN]]


class Probe:
    def __init__(self, argv: list[str], timeout: float) -> None:
        self.argv = argv
        self.timeout = timeout
        self.lines: queue.Queue = queue.Queue()
        self.noise = 0
        self.stderr_tail = b""
        self.stderr_bytes = 0
        self.next_id = 0
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            self.lines.put(raw)
        self.lines.put(None)

    def _read_stderr(self) -> None:
        for chunk in iter(lambda: self.proc.stderr.read(4096), b""):
            self.stderr_bytes += len(chunk)
            self.stderr_tail = (self.stderr_tail + chunk)[-STDERR_KEEP:]

    def send(self, message: dict) -> None:
        data = (json.dumps(message) + "\n").encode()
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise ProbeError(2, "the server closed its stdin")

    def request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        self.next_id += 1
        rid = self.next_id
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ProbeError(3, f"no answer to {method} within {timeout or self.timeout:.0f}s")
            try:
                raw = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            if raw is None:
                raise ProbeError(2, f"the server closed stdout before answering {method}")
            try:
                message = json.loads(raw)
            except ValueError:
                self.noise += 1
                continue
            if not isinstance(message, dict):
                self.noise += 1
                continue
            if "method" in message and "id" in message:  # a request from the server
                self._answer(message)
                continue
            if message.get("id") != rid:
                continue  # a notification, or a stale answer
            if "error" in message:
                error = message["error"] if isinstance(message["error"], dict) else {}
                raise ProbeError(4, f"{method} returned error {error.get('code')}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ProbeError(4, f"{method} returned no result object")
            return result

    def _answer(self, message: dict) -> None:
        method = message.get("method")
        if method == "ping":
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": {}}
        elif method == "roots/list":
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": {"roots": []}}
        else:
            reply = {"jsonrpc": "2.0", "id": message["id"],
                     "error": {"code": -32601, "message": "not supported by pickfit's probe"}}
        self.send(reply)

    def stop(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        for sig in (None, signal.SIGTERM, signal.SIGKILL):
            if sig is not None:
                try:
                    os.killpg(self.proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
            try:
                self.proc.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                continue


class ProbeError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _summary_line(summary: dict) -> str:
    return MARKER + json.dumps(summary, sort_keys=True)


def run(argv: list[str], *, timeout: float, call: str | None, call_args: dict) -> int:
    summary: dict = {"probe": 1, "launch": argv, "ok": False}
    try:
        probe = Probe(argv, timeout)
    except OSError as err:
        print(f"error: cannot start {argv[0]!r}: {err.strerror or err}")
        summary["error"] = "start"
        print(_summary_line(summary))
        return 2
    code = 0
    try:
        init = probe.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                            "clientInfo": {"name": "pickfit-mcp-probe", "version": "1"}})
        info = init.get("serverInfo") if isinstance(init.get("serverInfo"), dict) else {}
        summary.update(protocol=safe_version(init.get("protocolVersion")), server=safe_name(info.get("name")),
                       version=safe_version(info.get("version")))
        print(f"initialize: ok protocol={summary['protocol']} server={summary['server']} "
              f"version={summary['version']}")
        probe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools: list[dict] = []
        cursor = None
        for _ in range(MAX_PAGES):
            page = probe.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += [t for t in page.get("tools") or [] if isinstance(t, dict)]
            cursor = page.get("nextCursor")
            if not cursor or not isinstance(cursor, str):
                break
        print(f"tools/list: ok count={len(tools)}")
        names = [safe_name(t.get("name")) for t in tools]
        flags: dict[str, list[str]] = {}
        for tool, name in zip(tools, names):
            found = flags_for(tool)
            if found:
                flags[name] = found
        for tool, name in list(zip(tools, names))[:MAX_TOOLS_SHOWN]:
            print(f"tool: {name} args={','.join(arg_names(tool)) or '-'}")
        for name, found in flags.items():
            print(f"flag: {name} {','.join(found)}")
        summary.update(tools=names[:MAX_TOOLS_SHOWN], count=len(tools), flags=flags)
        if not tools:
            raise ProbeError(4, "tools/list returned no tools")
        if call:
            if call not in [t.get("name") for t in tools]:
                raise ProbeError(1, f"no tool named {safe_name(call)!r} in tools/list")
            result = probe.request("tools/call", {"name": call, "arguments": call_args})
            content = [c for c in result.get("content") or [] if isinstance(c, dict)]
            kinds = ",".join(f"{safe_name(c.get('type'))}" for c in content) or "-"
            text = next((c.get("text") for c in content if isinstance(c.get("text"), str)), "")
            if result.get("isError"):
                print(f"tools/call: error tool={safe_name(call)} content={kinds}")
                summary["call_error"] = safe_name(call)
                code = 5
            else:
                shown = " ".join(_CONTROL.sub(" ", text).split())[:RESULT_SHOWN]
                print(f"tools/call: ok tool={safe_name(call)} content={kinds} text_chars={len(text)}")
                if shown:
                    print(f"result: {shown}")
                summary["called"] = safe_name(call)
        if probe.noise:
            print(f"warning: {probe.noise} line(s) on the server's stdout were not JSON-RPC; strict clients may fail")
        summary["noise"] = probe.noise
        if code == 0:
            summary["ok"] = True
            print("handshake: ok" + (", tool call ok" if call else ""))
    except ProbeError as err:
        code = err.code
        print(f"error: {err}")
        summary["error"] = str(err)
        summary["noise"] = probe.noise
        tail = probe.stderr_tail.decode("utf-8", errors="replace").strip()
        if tail:
            print("server stderr (last lines):", file=sys.stderr)
            print("\n".join(tail.splitlines()[-25:]), file=sys.stderr)
    finally:
        probe.stop()
    summary["exit"] = probe.proc.returncode
    print(_summary_line(summary))
    return code


def main(args: list[str]) -> int:
    timeout, call, call_args = 60.0, None, {}
    if "--" not in args:
        print(__doc__.strip().splitlines()[2].strip())
        return 1
    split = args.index("--")
    options, command = args[:split], args[split + 1:]
    i = 0
    while i < len(options):
        if options[i] == "--timeout" and i + 1 < len(options):
            timeout = float(options[i + 1])
        elif options[i] == "--call" and i + 1 < len(options):
            call = options[i + 1]
        elif options[i] == "--args" and i + 1 < len(options):
            try:
                call_args = json.loads(options[i + 1])
            except ValueError:
                print("usage: --args takes a JSON object")
                return 1
            if not isinstance(call_args, dict):
                print("usage: --args takes a JSON object")
                return 1
        else:
            print(f"usage: unknown option {options[i]!r}")
            return 1
        i += 2
    if not command:
        print("usage: give the server's launch command after --")
        return 1
    return run(command, timeout=timeout, call=call, call_args=call_args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
