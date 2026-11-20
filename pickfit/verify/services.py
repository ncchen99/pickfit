"""Backend services in a Linux box, for tools that need one to show they work: PostgreSQL, Redis and an HTTP mock.

A box of the "services" kind (image_recipe(services=True)) has the PostgreSQL and Redis server packages and one
helper, `pickfit-services`. Nothing runs at start. The agent (or a replayed install step) starts what the tool
needs, and the helper starts it as the user who called it, on 127.0.0.1 only, with its data in that user's home:

    pickfit-services start postgres     postgresql://pickfit@127.0.0.1:5432/pickfit (trust auth, a throwaway cluster)
    pickfit-services start redis        redis://127.0.0.1:6379/0 (no persistence)
    pickfit-services start http-mock    http://127.0.0.1:8080/ (answers every request with a JSON echo of it)
    pickfit-services env                the same as DATABASE_URL=..., REDIS_URL=..., MOCK_URL=... lines
    pickfit-services stop [name ...]

Why this keeps the box's limits (limits.py, unchanged): the services run as the box user, with the box user's limits,
in the box user's own network namespace (loopback inside it; the uplink is the box's, and the network cut closes it
as for anything else the user runs). No package adds a setuid binary or a root daemon; the packages' own init scripts
never run (no init system in the box), and the clusters they create are not used. A replay box is fresh, so a
replayed `pickfit-services start postgres` gives the same empty database again.

A tool that needs a SaaS account or a database pickfit does not run (MySQL, MongoDB, Kafka) is not helped here.
"""

from __future__ import annotations

import base64
import re
from typing import Any

SERVICE_PACKAGES = ("postgresql", "redis-server")
HELPER_PATH = "/usr/local/bin/pickfit-services"
MOCK_PATH = "/usr/local/lib/pickfit/http_mock.py"
PG_URL = "postgresql://pickfit@127.0.0.1:5432/pickfit"
REDIS_URL = "redis://127.0.0.1:6379/0"
MOCK_URL = "http://127.0.0.1:8080/"

HTTP_MOCK = '''"""pickfit's HTTP mock: answers every request with 200 and a JSON echo of it (127.0.0.1 only)."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Echo(BaseHTTPRequestHandler):
    def _answer(self):
        length = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        out = json.dumps({"ok": True, "method": self.command, "path": self.path,
                          "headers": {k: v for k, v in self.headers.items()}, "body": body, "json": parsed},
                         indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(out)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _answer

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\\n" % (self.command, self.path))


host, port = sys.argv[1], int(sys.argv[2])
if host != "127.0.0.1":
    sys.exit("the mock listens on 127.0.0.1 only")
ThreadingHTTPServer((host, port), Echo).serve_forever()
'''

HELPER = f'''#!/bin/sh
# pickfit-services: throwaway PostgreSQL, Redis or an HTTP mock for the calling user, on 127.0.0.1 only.
set -eu
base="${{PICKFIT_SERVICES_DIR:-$HOME/.pickfit-services}}"
usage() {{ echo "usage: pickfit-services start|stop [postgres] [redis] [http-mock] | env | status" >&2; exit 2; }}
wait_port() {{ i=0; while [ $i -lt 60 ]; do
  python3 -c "import socket,sys; socket.create_connection(('127.0.0.1', $1), 1)" 2>/dev/null && return 0
  i=$((i+1)); sleep 0.5; done; echo "$2 did not start; its log: $3" >&2; return 1; }}
pg_bin() {{ ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -n 1; }}
start() {{ case "$1" in
  postgres)
    pg="$(pg_bin)"; d="$base/postgres"; mkdir -p "$d"
    [ -d "$d/data" ] || "$pg/initdb" -D "$d/data" -U pickfit --auth=trust -E UTF8 >"$d/initdb.log" 2>&1
    "$pg/pg_ctl" -D "$d/data" -l "$d/log" -w -t 60 \\
      -o "-h 127.0.0.1 -p 5432 -k $d -c dynamic_shared_memory_type=mmap -c shared_buffers=16MB" start >/dev/null
    "$pg/createdb" -h 127.0.0.1 -p 5432 -U pickfit pickfit 2>/dev/null || true
    echo "postgres: {PG_URL}" ;;
  redis)
    d="$base/redis"; mkdir -p "$d"
    redis-server --bind 127.0.0.1 --port 6379 --protected-mode yes --dir "$d" --save "" --appendonly no \\
      --daemonize yes --pidfile "$d/pid" --logfile "$d/log"
    wait_port 6379 redis "$d/log"; echo "redis: {REDIS_URL}" ;;
  http-mock)
    d="$base/http-mock"; mkdir -p "$d"
    nohup python3 {MOCK_PATH} 127.0.0.1 8080 >"$d/log" 2>&1 &
    echo $! >"$d/pid"; wait_port 8080 http-mock "$d/log"; echo "http-mock: {MOCK_URL}" ;;
  *) echo "unknown service: $1 (postgres, redis, http-mock)" >&2; exit 2 ;;
esac; }}
stop() {{ case "$1" in
  postgres) [ -d "$base/postgres/data" ] && "$(pg_bin)/pg_ctl" -D "$base/postgres/data" -m fast stop >/dev/null || true ;;
  redis|http-mock) [ -f "$base/$1/pid" ] && kill "$(cat "$base/$1/pid")" 2>/dev/null || true ;;
  *) echo "unknown service: $1" >&2; exit 2 ;;
esac; }}
cmd="${{1:-}}"; [ $# -gt 0 ] && shift
case "$cmd" in
  start) [ $# -gt 0 ] || usage; for s in "$@"; do start "$s"; done ;;
  stop) [ $# -gt 0 ] || set -- postgres redis http-mock; for s in "$@"; do stop "$s"; done ;;
  env) printf 'DATABASE_URL={PG_URL}\\nREDIS_URL={REDIS_URL}\\nMOCK_URL={MOCK_URL}\\n' ;;
  status) for p in 5432:postgres 6379:redis 8080:http-mock; do
      python3 -c "import socket; socket.create_connection(('127.0.0.1', ${{p%%:*}}), 1)" 2>/dev/null \\
        && echo "${{p#*:}}: running" || echo "${{p#*:}}: stopped"; done ;;
  *) usage ;;
esac
'''


def _install_file(path: str, text: str, mode: str) -> str:
    data = base64.b64encode(text.encode()).decode()
    return (f"/usr/bin/install -d -m 0755 {path.rsplit('/', 1)[0]} && echo {data} | base64 -d > {path} "
            f"&& chmod {mode} {path}")


# Root, at image build: the helper and the mock, root-owned and not writable by the box user.
SERVICES_INSTALL = " && ".join((_install_file(MOCK_PATH, HTTP_MOCK, "0644"), _install_file(HELPER_PATH, HELPER, "0755")))

PROMPT = (f"Services: this box can start a throwaway PostgreSQL, Redis and an HTTP mock for you, on 127.0.0.1 only. "
          f"Run `pickfit-services start postgres` ({PG_URL}), `pickfit-services start redis` ({REDIS_URL}) or "
          f"`pickfit-services start http-mock` ({MOCK_URL}, answers any request with a JSON echo of it); "
          "`pickfit-services env` prints DATABASE_URL, REDIS_URL and MOCK_URL. Start a service as its own install step "
          "(so the replay starts it too) before the tool's step that needs it, and point the tool at these URLs. "
          "There is no MySQL, MongoDB or outside server.")

_DB_WORDS = re.compile(r"\bpostgres(?:ql)?\b|\bpsql\b|\bredis\b|\bDATABASE_URL\b|\bREDIS_URL\b|\bpgvector\b", re.I)
_HTTP_CLIENT = re.compile(r"\b(?:HTTP|REST|GraphQL|API)\s+client\b|\bcurl\s+(?:alternative|replacement)\b|"
                          r"\bpostman\b|\bload[- ]test\w*\b|\bhttp\s+benchmark\w*\b|\bwebhook\s+(?:tester|inspector)\b",
                          re.I)


def _cited_texts(ex: Any) -> list[str]:
    out: list[str] = []
    for name in ("name", "summary"):
        cited = getattr(ex, name, None)
        out += [p for p in (getattr(cited, "value", None), getattr(cited, "quote", None)) if isinstance(p, str)]
    pre = getattr(ex, "prerequisites", None)
    for name in ("runtimes", "system_packages"):
        for item in getattr(pre, name, None) or []:
            out += [p for p in (item.value, item.quote) if isinstance(p, str)]
    for name in ("features", "use_cases", "manual_steps"):
        for item in getattr(ex, name, None) or []:
            out += [p for p in (item.value, item.quote) if isinstance(p, str)]
    return out


def needs_services(ex: Any, readme: str | None = None) -> bool:
    """Does the tool need PostgreSQL or Redis to run, or is it an HTTP/API client that needs a server to talk to?"""
    own = _cited_texts(ex)
    if any(_DB_WORDS.search(t) or _HTTP_CLIENT.search(t) for t in own):
        return True
    return bool(readme) and (len(_DB_WORDS.findall(readme)) >= 3 or len(_HTTP_CLIENT.findall(readme)) >= 2)
