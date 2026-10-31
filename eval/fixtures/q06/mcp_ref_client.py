#!/usr/bin/env python3
"""q06 reference MCP client (Python 3.8+ stdlib only). Frozen with the fixtures; its sha256
goes into calibration.md, which is what "pinned" means for this client.

    mcp_ref_client.py --stdio [--env K=V]... [--cwd DIR] -- SERVER_CMD [ARG...]
    mcp_ref_client.py --http URL [--header "K: V"]... [--spawn "SHELL CMD"] [--ready-timeout 120]
    mcp_ref_client.py --sse URL  [--header "K: V"]... [--spawn "SHELL CMD"]

Session: initialize -> notifications/initialized -> tools/list (all pages) -> pick the tool
for each operation -> tools/call GET with id 42 -> tools/call POST with post_body.json ->
close. --list-only stops after tools/list. Writes a JSON report (--report).

Which tool is which: --get-tool / --post-tool name them; otherwise the client matches on
tool name, title and description (operationId getItem/createItem, the summaries, or the
method and path) and then on the input schema (a property "id" vs the body properties).
Arguments: --get-args / --post-args give them as JSON; otherwise they are built from the
tool's input schema ("id": 42 at the top level or inside one object property; the body
spread at the top level or placed in the one object property that takes it).

Transports follow the MCP specification: stdio is newline-delimited JSON-RPC on the
server's stdin/stdout; streamable HTTP POSTs each message and reads either a JSON body or
an SSE stream (Mcp-Session-Id and MCP-Protocol-Version headers are honoured); --sse is the
older HTTP+SSE transport. Requests the server sends to the client are answered: ping with
{}, roots/list with an empty list, anything else with "method not found".
"""

import argparse
import datetime
import hashlib
import http.client
import json
import os
import queue
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urljoin, urlsplit

CLIENT_INFO = {"name": "eval-q06-ref-client", "version": "1.0.0"}
PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
HERE = os.path.dirname(os.path.abspath(__file__))


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Closed(Exception):
    pass


class StdioTransport:
    name = "stdio"

    def __init__(self, cmd, env, cwd, stderr_path):
        full_env = dict(os.environ)
        full_env.update(env)
        self.stderr_fh = open(stderr_path, "wb")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr_fh, env=full_env, cwd=cwd)
        self.q = queue.Queue()
        self.warnings = []
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                self.q.put(json.loads(line))
            except ValueError:
                self.warnings.append("non-JSON line on stdout: " + line[:200])
        self.q.put(Closed())

    def send(self, msg):
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise Closed("server stdin closed: %r" % exc)

    def recv(self, timeout):
        try:
            m = self.q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no message within %ss" % timeout)
        if isinstance(m, Closed):
            self.q.put(m)
            raise Closed("server closed stdout (exit code %s)" % self.proc.poll())
        return m

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.stderr_fh.close()
        return self.proc.returncode


def _conn(url, timeout):
    u = urlsplit(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    return cls(u.hostname, u.port, timeout=timeout), path


def _sse_events(resp):
    event, data = "message", []
    while True:
        raw = resp.readline()
        if not raw:
            if data:
                yield event, "\n".join(data)
            return
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:][1:] if line[5:6] == " " else line[5:])


class HttpTransport:
    name = "streamable-http"

    def __init__(self, url, headers, timeout):
        self.url, self.headers, self.timeout = url, headers, timeout
        self.session = None
        self.protocol = None
        self.q = queue.Queue()
        self.warnings = []
        self.http_log = []

    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        h.update(self.headers)
        if self.session:
            h["Mcp-Session-Id"] = self.session
        if self.protocol:
            h["MCP-Protocol-Version"] = self.protocol
        return h

    def send(self, msg):
        conn, path = _conn(self.url, self.timeout)
        try:
            conn.request("POST", path, body=json.dumps(msg).encode("utf-8"), headers=self._headers())
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            raise Closed("HTTP POST failed: %r" % exc)
        sid = resp.getheader("Mcp-Session-Id")
        if sid:
            self.session = sid
        ctype = (resp.getheader("Content-Type") or "").lower()
        self.http_log.append({"method": msg.get("method"), "status": resp.status, "content_type": ctype})
        if resp.status in (202, 204):
            resp.read()
            conn.close()
            return
        if resp.status >= 400:
            body = resp.read()[:500].decode("utf-8", errors="replace")
            conn.close()
            if "id" in msg and "method" in msg:
                self.q.put({"jsonrpc": "2.0", "id": msg["id"],
                            "error": {"code": -32000, "message": "HTTP %d: %s" % (resp.status, body)}})
            return
        if "text/event-stream" in ctype:
            want = msg.get("id") if "method" in msg else None
            for _event, data in _sse_events(resp):
                try:
                    obj = json.loads(data)
                except ValueError:
                    self.warnings.append("non-JSON SSE data: " + data[:200])
                    continue
                for m in (obj if isinstance(obj, list) else [obj]):
                    self.q.put(m)
                    if want is not None and m.get("id") == want and "method" not in m:
                        conn.close()
                        return
            conn.close()
            return
        body = resp.read()
        conn.close()
        if body.strip():
            try:
                obj = json.loads(body)
            except ValueError:
                self.warnings.append("non-JSON HTTP body: " + body[:200].decode("utf-8", "replace"))
                return
            for m in (obj if isinstance(obj, list) else [obj]):
                self.q.put(m)

    def recv(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no message within %ss" % timeout)

    def close(self):
        if self.session:
            try:
                conn, path = _conn(self.url, 10)
                conn.request("DELETE", path, headers=self._headers())
                conn.getresponse().read()
                conn.close()
            except (OSError, http.client.HTTPException):
                pass
        return None


class SseTransport:
    name = "http+sse"

    def __init__(self, url, headers, timeout):
        self.url, self.headers, self.timeout = url, headers, timeout
        self.q = queue.Queue()
        self.warnings = []
        self.endpoint = None
        self.ready = threading.Event()
        conn, path = _conn(url, None)
        h = {"Accept": "text/event-stream"}
        h.update(headers)
        conn.request("GET", path, headers=h)
        self.resp = conn.getresponse()
        if self.resp.status != 200:
            raise Closed("SSE GET returned HTTP %d" % self.resp.status)
        threading.Thread(target=self._reader, daemon=True).start()
        if not self.ready.wait(timeout):
            raise Closed("no endpoint event on the SSE stream")

    def _reader(self):
        for event, data in _sse_events(self.resp):
            if event == "endpoint":
                self.endpoint = urljoin(self.url, data.strip())
                self.ready.set()
                continue
            try:
                obj = json.loads(data)
            except ValueError:
                self.warnings.append("non-JSON SSE data: " + data[:200])
                continue
            for m in (obj if isinstance(obj, list) else [obj]):
                self.q.put(m)
        self.q.put(Closed())

    def send(self, msg):
        conn, path = _conn(self.endpoint, self.timeout)
        h = {"Content-Type": "application/json"}
        h.update(self.headers)
        try:
            conn.request("POST", path, body=json.dumps(msg).encode("utf-8"), headers=h)
            conn.getresponse().read()
        except (OSError, http.client.HTTPException) as exc:
            raise Closed("SSE POST failed: %r" % exc)
        finally:
            conn.close()

    def recv(self, timeout):
        try:
            m = self.q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no message within %ss" % timeout)
        if isinstance(m, Closed):
            self.q.put(m)
            raise Closed("SSE stream closed")
        return m

    def close(self):
        return None


class Client:
    def __init__(self, transport):
        self.t = transport
        self.next_id = 1
        self.notifications = {}
        self.server_requests = []

    def rpc(self, method, params, timeout):
        rid = self.next_id
        self.next_id += 1
        self.t.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("%s: no response within %ss" % (method, timeout))
            m = self.t.recv(left)
            if "method" in m and "id" in m:
                self._answer(m)
            elif "method" in m:
                self.notifications[m["method"]] = self.notifications.get(m["method"], 0) + 1
            elif m.get("id") == rid:
                return m
            else:
                self.t.warnings.append("unexpected message: " + json.dumps(m)[:200])

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.t.send(msg)

    def _answer(self, req):
        self.server_requests.append(req["method"])
        if req["method"] == "ping":
            res = {"jsonrpc": "2.0", "id": req["id"], "result": {}}
        elif req["method"] == "roots/list":
            res = {"jsonrpc": "2.0", "id": req["id"], "result": {"roots": []}}
        else:
            res = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "method not found"}}
        self.t.send(res)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _props(schema):
    return (schema or {}).get("properties") or {}


def _has_id(schema):
    p = _props(schema)
    if "id" in p:
        return True
    return any(isinstance(v, dict) and "id" in _props(v) for v in p.values())


BODY_KEYS = ("name", "quantity", "tags")


def _has_body(schema):
    p = _props(schema)
    if all(k in p for k in BODY_KEYS):
        return True
    return any(isinstance(v, dict) and (all(k in _props(v) for k in BODY_KEYS)
                                        or norm(k) in ("body", "requestbody", "data", "json", "payload"))
               for k, v in p.items())


GET_TEXT = ("getitem", "getitemsid", "itemsidget", "getanitembyid", "getitemsbyid")
POST_TEXT = ("createitem", "postitems", "itemspost", "createanitem", "postitem")


def map_tools(tools):
    notes = []

    def text_hits(keys):
        out = []
        for t in tools:
            blob = norm(t.get("name")) + " " + norm(t.get("title")) + " " + norm(t.get("description"))
            if any(k in blob for k in keys):
                out.append(t["name"])
        return out

    g, p = text_hits(GET_TEXT), text_hits(POST_TEXT)
    method = "name/title/description"
    if not (len(g) == 1 and len(p) == 1 and g != p):
        g = [t["name"] for t in tools if _has_id(t.get("inputSchema")) and not _has_body(t.get("inputSchema"))]
        p = [t["name"] for t in tools if _has_body(t.get("inputSchema"))]
        method = "input schema"
    if len(g) == 1 and len(p) == 1 and g != p:
        return {"get": g[0], "post": p[0], "method": method, "bijection": True, "notes": notes}
    notes.append("could not map tools to operations uniquely (get candidates %r, post candidates %r)" % (g, p))
    return {"get": g[0] if len(g) == 1 else None, "post": p[0] if len(p) == 1 else None,
            "method": method, "bijection": False, "notes": notes}


def _coerce_id(prop, value):
    t = (prop or {}).get("type")
    if t == "string" or (isinstance(t, list) and "string" in t and "integer" not in t):
        return str(value)
    return value


def build_get_args(schema, value):
    p = _props(schema)
    if "id" in p:
        return {"id": _coerce_id(p["id"], value)}
    for k, v in p.items():
        if isinstance(v, dict) and "id" in _props(v):
            return {k: {"id": _coerce_id(_props(v)["id"], value)}}
    if len(p) == 1:
        k = next(iter(p))
        return {k: _coerce_id(p[k], value)}
    return None


def build_post_args(schema, body):
    p = _props(schema)
    if all(k in p for k in body):
        return dict(body)
    for k, v in p.items():
        if isinstance(v, dict) and all(b in _props(v) for b in body):
            return {k: dict(body)}
    for k in p:
        if norm(k) in ("body", "requestbody", "data", "json", "payload"):
            return {k: dict(body)}
    if len(p) == 1:
        return {next(iter(p)): dict(body)}
    return None


def wait_port(url, timeout, proc=None):
    u = urlsplit(url)
    host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            socket.create_connection((host, port), timeout=2).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stdio", action="store_true")
    mode.add_argument("--http", metavar="URL")
    mode.add_argument("--sse", metavar="URL")
    ap.add_argument("--env", action="append", default=[], help="K=V for the stdio server")
    ap.add_argument("--cwd")
    ap.add_argument("--header", action="append", default=[])
    ap.add_argument("--spawn", help="shell command that starts the HTTP server; stopped at the end")
    ap.add_argument("--ready-timeout", type=float, default=120)
    ap.add_argument("--init-timeout", type=float, default=180)
    ap.add_argument("--timeout", type=float, default=60, help="per request after initialize")
    ap.add_argument("--get-id", type=int, default=42)
    ap.add_argument("--post-body", default=os.path.join(HERE, "post_body.json"))
    ap.add_argument("--get-tool")
    ap.add_argument("--post-tool")
    ap.add_argument("--get-args")
    ap.add_argument("--post-args")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--report", default="client_report.json")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    with open(os.path.abspath(__file__), "rb") as fh:
        self_sha = hashlib.sha256(fh.read()).hexdigest()
    with open(a.post_body, encoding="utf-8") as fh:
        body = json.load(fh)
    rep = {"client": dict(CLIENT_INFO, sha256=self_sha), "started_utc": now(), "errors": []}
    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    spawned = None
    stderr_path = os.path.splitext(a.report)[0] + ".server_stderr.log"
    transport = None
    try:
        if a.stdio:
            if not cmd:
                sys.exit("--stdio needs a server command after --")
            env = dict(e.split("=", 1) for e in a.env)
            rep.update({"transport": "stdio", "target": cmd})
            transport = StdioTransport(cmd, env, a.cwd, stderr_path)
        else:
            url = a.http or a.sse
            rep.update({"transport": "streamable-http" if a.http else "http+sse", "target": url})
            if a.spawn:
                spawned = subprocess.Popen(a.spawn, shell=True, cwd=a.cwd, stdout=open(stderr_path, "wb"),
                                           stderr=subprocess.STDOUT, start_new_session=True)
                rep["spawn"] = a.spawn
            if not wait_port(url, a.ready_timeout, spawned):
                raise Closed("server port did not open within %ss" % a.ready_timeout)
            transport = (HttpTransport if a.http else SseTransport)(url, headers, a.timeout)
        cl = Client(transport)
        init = None
        for ver in PROTOCOL_VERSIONS:
            t0 = time.monotonic()
            resp = cl.rpc("initialize", {"protocolVersion": ver, "capabilities": {},
                                         "clientInfo": CLIENT_INFO}, a.init_timeout)
            if "result" in resp:
                init = resp["result"]
                rep["initialize"] = {"ok": True, "requested": ver, "protocolVersion": init.get("protocolVersion"),
                                     "serverInfo": init.get("serverInfo"), "capabilities": init.get("capabilities"),
                                     "duration_s": round(time.monotonic() - t0, 3)}
                break
            rep["errors"].append({"step": "initialize", "requested": ver, "error": resp.get("error")})
        if init is None:
            raise Closed("initialize failed for every protocol version")
        if isinstance(transport, HttpTransport):
            transport.protocol = init.get("protocolVersion")
        cl.notify("notifications/initialized")
        tools, cursor, pages = [], None, 0
        while True:
            resp = cl.rpc("tools/list", {"cursor": cursor} if cursor else {}, a.timeout)
            if "error" in resp:
                raise Closed("tools/list error: %r" % resp["error"])
            pages += 1
            tools += resp["result"].get("tools", [])
            cursor = resp["result"].get("nextCursor")
            if not cursor or pages > 50:
                break
        rep["tools"] = [{k: t.get(k) for k in ("name", "title", "description", "inputSchema")} for t in tools]
        rep["tool_count"] = len(tools)
        mapping = map_tools(tools)
        if a.get_tool:
            mapping.update({"get": a.get_tool, "method": "named by grader"})
        if a.post_tool:
            mapping.update({"post": a.post_tool, "method": "named by grader"})
        rep["mapping"] = mapping
        rep["calls"] = {}
        if not a.list_only:
            by_name = {t["name"]: t for t in tools}
            for op in ("get", "post"):
                name = mapping.get(op)
                call = {"tool": name}
                rep["calls"][op] = call
                if not name or name not in by_name:
                    call["error"] = "no tool selected for this operation"
                    continue
                schema = by_name[name].get("inputSchema") or {}
                given = a.get_args if op == "get" else a.post_args
                args = json.loads(given) if given else (
                    build_get_args(schema, a.get_id) if op == "get" else build_post_args(schema, body))
                call["arguments"] = args
                call["arguments_from"] = "grader" if given else "input schema"
                if args is None:
                    call["error"] = "could not build arguments from the input schema; pass --%s-args" % op
                    continue
                call["started_utc"] = now()
                t0 = time.monotonic()
                resp = cl.rpc("tools/call", {"name": name, "arguments": args}, a.timeout)
                call["duration_s"] = round(time.monotonic() - t0, 3)
                call["ended_utc"] = now()
                if "error" in resp:
                    call["error"] = resp["error"]
                else:
                    call["result"] = resp["result"]
                    call["isError"] = bool(resp["result"].get("isError"))
    except (Closed, TimeoutError, OSError, ValueError, KeyError) as exc:
        rep["errors"].append({"step": "session", "error": repr(exc)})
    finally:
        if transport is not None:
            rep["protocol_warnings"] = transport.warnings[:50]
            if isinstance(transport, HttpTransport):
                rep["http_log"] = transport.http_log
            try:
                rep["server_exit_code"] = transport.close()
            except Exception as exc:  # noqa: BLE001
                rep["errors"].append({"step": "close", "error": repr(exc)})
        if spawned is not None:
            import signal
            try:
                os.killpg(spawned.pid, signal.SIGTERM)
                spawned.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(spawned.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            rep["notifications"] = cl.notifications
            rep["server_requests"] = cl.server_requests
        except NameError:
            pass
        if os.path.exists(stderr_path):
            with open(stderr_path, "rb") as fh:
                rep["server_output_tail"] = fh.read()[-4000:].decode("utf-8", errors="replace")
        rep["ended_utc"] = now()
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"tool_count": rep.get("tool_count"), "mapping": rep.get("mapping"),
                      "errors": rep["errors"], "report": a.report}, ensure_ascii=False, indent=2))
    sys.exit(0 if not rep["errors"] else 1)


if __name__ == "__main__":
    main()
