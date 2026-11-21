"""Backend services in a Linux box, for tools that need one to show they work: databases, an HTTP mock, a mail sink,
an AWS emulator, a git host and a stand-in model endpoint.

A box of the "services" kind (image_recipe(services=True)) has the servers and one helper, `pickfit-services`.
Nothing runs at start. The agent (or a replayed install step) starts what the tool needs, and the helper starts it
as the user who called it, on 127.0.0.1 only, with its data in that user's home:

    pickfit-services start postgres     postgresql://pickfit@127.0.0.1:5432/pickfit (trust auth, a throwaway cluster)
    pickfit-services start redis        redis://127.0.0.1:6379/0 (no persistence)
    pickfit-services start http-mock    http://127.0.0.1:8080/ (answers every request with a JSON echo of it)
    pickfit-services start mysql        mysql://pickfit:pickfit@127.0.0.1:3306/pickfit (MariaDB, a throwaway data dir)
    pickfit-services start smtp         smtp://127.0.0.1:1025 (accepts any mail, delivers none, keeps what arrived)
    pickfit-services start aws          http://127.0.0.1:4566 (moto: S3 and the AWS APIs it emulates; bucket pickfit)
    pickfit-services start git          git://127.0.0.1:9418/pickfit.git and http://127.0.0.1:3000/pickfit.git
    pickfit-services start llm-stub     http://127.0.0.1:8081/v1 (OpenAI-compatible, a 135M model: wiring only)
    pickfit-services env                the same as DATABASE_URL=..., MYSQL_URL=..., OPENAI_BASE_URL=... lines
    pickfit-services mail [N]           what the mail sink received, one JSON line each (or message N itself)
    pickfit-services check llm-stub     one chat completion, round trip
    pickfit-services status | stop [name ...]

Why this keeps the box's limits (limits.py, unchanged): the services run as the box user, with the box user's limits,
in the box user's own network namespace (loopback inside it; the uplink is the box's, and the network cut closes it
as for anything else the user runs). No package adds a setuid binary or a root daemon; the packages' own init scripts
never run (no init system in the box), and the clusters they create are not used. A replay box is fresh, so a
replayed `pickfit-services start postgres` gives the same empty database again.

What each stand-in can show (privileges.md P4, P8):

- llm-stub is llama.cpp's server with SmolLM2-135M-Instruct, both in the image (no download at run time, and the
  server runs with --offline). It answers /v1/chat/completions, /v1/completions, /v1/models and Anthropic's
  /v1/messages with any key. A 135M model's answers are not evidence of anything: the stub shows that a tool's
  requests reach a server and come back in the shape the API has. What is verified with it is "stand_in", never
  "it works with OpenAI".
- smtp is a sink written here (SMTP_SINK): it accepts mail for any address, with any login, and delivers nothing.
  read_mail() gives the harness what arrived. The files are the box user's, so mail is evidence only together with
  something the tool could not know beforehand (a fresh word in the subject pickfit asks for).
- aws is moto's server: S3 with a bucket `pickfit`, and the other services moto implements in one process. What
  needs Docker behind it (Lambda, Batch, ECS tasks) does not run.
- git is `git daemon` plus GIT_HTTP, a relay to `git http-backend`: one bare repository with one commit, push and
  pull without a login. It is a remote, not a forge: no issues, pull requests or API.

A tool that needs a SaaS account or a server pickfit does not run (MongoDB, Kafka, a GitHub-compatible API) is not
helped here.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

SERVICE_PACKAGES = ("postgresql", "redis-server", "mariadb-server")
LIB = "/usr/local/lib/pickfit"
HELPER_PATH = "/usr/local/bin/pickfit-services"
MOCK_PATH = f"{LIB}/http_mock.py"
SMTP_PATH = f"{LIB}/smtp_sink.py"
GIT_HTTP_PATH = f"{LIB}/git_http.py"
LLM_CHECK_PATH = f"{LIB}/llm_check.py"
MOTO_DIR = f"{LIB}/moto"
LLAMA_DIR = f"{LIB}/llama"
PG_URL = "postgresql://pickfit@127.0.0.1:5432/pickfit"
REDIS_URL = "redis://127.0.0.1:6379/0"
MOCK_URL = "http://127.0.0.1:8080/"
MYSQL_URL = "mysql://pickfit:pickfit@127.0.0.1:3306/pickfit"
SMTP_URL = "smtp://127.0.0.1:1025"
AWS_URL = "http://127.0.0.1:4566"
AWS_KEY = "testing"  # moto's documented dummy credentials; nothing checks them
S3_BUCKET = "pickfit"
GIT_URL = "git://127.0.0.1:9418/pickfit.git"
GIT_HTTP_URL = "http://127.0.0.1:3000/pickfit.git"
LLM_URL = "http://127.0.0.1:8081/v1"
LLM_KEY = "sk-pickfit-stand-in"  # not a key of anyone's: the stub takes any
LLM_MODEL = "pickfit-stub"
# (name, the port that says it runs). `s3` is another name for `aws`.
KINDS = (("postgres", 5432), ("redis", 6379), ("http-mock", 8080), ("mysql", 3306), ("smtp", 1025), ("aws", 4566),
         ("git", 9418), ("llm-stub", 8081))
KIND_NAMES = tuple(name for name, _ in KINDS)
# What a stand-in proves is narrower than what the real service would (privileges.md P1: fidelity "stand_in").
STAND_INS = frozenset({"http-mock", "smtp", "aws", "git", "llm-stub"})

# moto (Apache-2.0), from PyPI into its own virtual environment: the documented way to run its server.
MOTO_VERSION = "5.2.5"
# llama.cpp's server (MIT): the project's own Linux x64 CPU build, pinned by SHA-256. It links the image's libssl3
# and libgomp1 and picks its CPU back end at run time. Only the server and its libraries are kept.
LLAMA_BUILD = "b12603"
LLAMA_URL = (f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/"
             f"llama-{LLAMA_BUILD}-bin-ubuntu-x64.tar.gz")
LLAMA_SHA256 = "1bb44c7887cbef0bacdd17d6c074526e7e772fa6026459b1c05b9a5cc96396a8"
# SmolLM2-135M-Instruct (Apache-2.0, HuggingFaceTB), the Q8_0 GGUF agent.TINY_MODELS names, at one commit.
MODEL_FILE = "SmolLM2-135M-Instruct-Q8_0.gguf"
MODEL_URL = ("https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF/resolve/"
             f"09816acd5d99df7be770d85ea30822623dab342c/{MODEL_FILE}")
MODEL_SHA256 = "5a1395716f7913741cc51d98581b9b1228d80987a9f7d3664106742eb06bba83"
MODEL_BYTES = 144_811_360

# What `pickfit-services env` prints. The names are the ones tools read; nothing here is a secret.
ENV = {
    "DATABASE_URL": PG_URL, "REDIS_URL": REDIS_URL, "MOCK_URL": MOCK_URL, "MYSQL_URL": MYSQL_URL,
    "MYSQL_HOST": "127.0.0.1", "MYSQL_TCP_PORT": "3306", "MYSQL_USER": "pickfit", "MYSQL_PASSWORD": "pickfit",
    "MYSQL_DATABASE": "pickfit", "SMTP_URL": SMTP_URL, "SMTP_HOST": "127.0.0.1", "SMTP_PORT": "1025",
    "AWS_ENDPOINT_URL": AWS_URL, "AWS_ACCESS_KEY_ID": AWS_KEY, "AWS_SECRET_ACCESS_KEY": AWS_KEY,
    "AWS_DEFAULT_REGION": "us-east-1", "S3_ENDPOINT": AWS_URL, "S3_BUCKET": S3_BUCKET, "GIT_URL": GIT_URL,
    "GIT_HTTP_URL": GIT_HTTP_URL, "OPENAI_BASE_URL": LLM_URL, "OPENAI_API_BASE": LLM_URL, "OPENAI_API_KEY": LLM_KEY,
    "OPENAI_MODEL": LLM_MODEL, "ANTHROPIC_BASE_URL": LLM_URL[:-len("/v1")], "ANTHROPIC_API_KEY": LLM_KEY,
}

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

SMTP_SINK = r'''"""pickfit's mail sink: accepts any mail on 127.0.0.1, with any login, and keeps it in a directory.
Nothing is delivered anywhere. Each message is NNNN.eml as it arrived, with one JSON line in index.jsonl."""
import email
import json
import os
import socketserver
import sys
import threading
import time
from email import policy

host, port, store = sys.argv[1], int(sys.argv[2]), sys.argv[3]
if host != "127.0.0.1":
    sys.exit("the sink listens on 127.0.0.1 only")
MAX = 10_000_000
lock = threading.Lock()


def keep(sender, recipients, data):
    with lock:
        n = len([f for f in os.listdir(store) if f.endswith(".eml")]) + 1
        name = "%04d.eml" % n
        with open(os.path.join(store, name), "wb") as f:
            f.write(data)
        try:
            subject = str(email.message_from_bytes(data, policy=policy.default).get("subject") or "")
        except Exception:
            subject = ""
        row = {"n": n, "from": sender, "to": recipients, "subject": subject[:300], "bytes": len(data), "file": name,
               "received_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with open(os.path.join(store, "index.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    return n


def address(arg):
    """MAIL FROM:<a@b> SIZE=1 -> a@b"""
    arg = arg.split(":", 1)[1].strip() if ":" in arg else arg.strip()
    if arg.startswith("<"):
        return arg[1:].split(">", 1)[0].strip()
    return arg.split()[0] if arg.split() else ""


class Session(socketserver.StreamRequestHandler):
    def say(self, *lines):
        self.wfile.write("".join(line + "\r\n" for line in lines).encode())
        self.wfile.flush()

    def handle(self):
        self.say("220 pickfit-smtp ESMTP (a sink: mail is kept, never delivered)")
        sender, recipients = None, []
        while True:
            raw = self.rfile.readline(8192)
            if not raw:
                return
            verb, _, arg = raw.decode("utf-8", "replace").rstrip("\r\n").partition(" ")
            verb = verb.upper()
            if verb == "EHLO":
                self.say("250-pickfit-smtp", "250-8BITMIME", "250-SMTPUTF8", "250-SIZE %d" % MAX,
                         "250 AUTH PLAIN LOGIN")
            elif verb == "HELO":
                self.say("250 pickfit-smtp")
            elif verb == "AUTH":
                parts = arg.split()
                if parts and parts[0].upper() == "LOGIN":
                    if len(parts) < 2:
                        self.say("334 VXNlcm5hbWU6")
                        self.rfile.readline(8192)
                    self.say("334 UGFzc3dvcmQ6")
                    self.rfile.readline(8192)
                elif len(parts) < 2:
                    self.say("334 ")
                    self.rfile.readline(8192)
                self.say("235 2.7.0 accepted (any name and password are)")
            elif verb == "MAIL":
                sender, recipients = address(arg), []
                self.say("250 2.1.0 ok")
            elif verb == "RCPT":
                if sender is None:
                    self.say("503 5.5.1 MAIL first")
                else:
                    recipients.append(address(arg))
                    self.say("250 2.1.5 ok")
            elif verb == "DATA":
                if not recipients:
                    self.say("503 5.5.1 RCPT first")
                    continue
                self.say("354 end with <CRLF>.<CRLF>")
                lines, size = [], 0
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    if line in (b".\r\n", b".\n"):
                        break
                    if line.startswith(b"."):
                        line = line[1:]
                    size += len(line)
                    if size <= MAX:
                        lines.append(line)
                if size > MAX:
                    self.say("552 5.3.4 message too large")
                else:
                    self.say("250 2.0.0 kept as message %d" % keep(sender, recipients, b"".join(lines)))
                sender, recipients = None, []
            elif verb == "RSET":
                sender, recipients = None, []
                self.say("250 2.0.0 ok")
            elif verb == "NOOP":
                self.say("250 2.0.0 ok")
            elif verb == "VRFY":
                self.say("252 2.5.2 cannot verify, will take the mail")
            elif verb == "QUIT":
                self.say("221 2.0.0 bye")
                return
            elif verb == "STARTTLS":
                self.say("454 4.7.0 no TLS here")
            else:
                self.say("502 5.5.2 not implemented")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


os.makedirs(store, exist_ok=True)
Server((host, port), Session).serve_forever()
'''

GIT_HTTP = r'''"""pickfit's git host over HTTP: a relay to `git http-backend` for the bare repositories in one directory.
127.0.0.1 only, no login, push allowed. A remote to clone from and push to, not a forge."""
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

host, port, root = sys.argv[1], int(sys.argv[2]), os.path.abspath(sys.argv[3])
if host != "127.0.0.1":
    sys.exit("the git host listens on 127.0.0.1 only")
MAX = 200_000_000


class Relay(BaseHTTPRequestHandler):
    def body(self):
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            data = b""
            while len(data) <= MAX:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline().strip():
                        pass
                    break
                data += self.rfile.read(size)
                self.rfile.readline()
            return data
        return self.rfile.read(min(int(self.headers.get("Content-Length") or 0), MAX))

    def relay(self):
        path, _, query = self.path.partition("?")
        body = self.body() if self.command == "POST" else b""
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"),
               "GIT_PROJECT_ROOT": root, "GIT_HTTP_EXPORT_ALL": "1", "REQUEST_METHOD": self.command,
               "PATH_INFO": path, "QUERY_STRING": query, "CONTENT_TYPE": self.headers.get("Content-Type") or "",
               "CONTENT_LENGTH": str(len(body)), "REMOTE_USER": "pickfit", "REMOTE_ADDR": "127.0.0.1"}
        for header, name in (("Content-Encoding", "HTTP_CONTENT_ENCODING"), ("Git-Protocol", "GIT_PROTOCOL")):
            if self.headers.get(header):
                env[name] = self.headers[header]
        done = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True)
        head, _, rest = done.stdout.partition(b"\r\n\r\n")
        status, headers = 200, []
        for line in head.decode("latin-1").split("\r\n"):
            name, _, value = line.partition(":")
            if name.lower() == "status":
                status = int(value.split()[0])
            elif value:
                headers.append((name, value.strip()))
        if done.returncode != 0 and not done.stdout:
            status, headers, rest = 500, [("Content-Type", "text/plain")], done.stderr[-500:]
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(rest)))
        self.end_headers()
        self.wfile.write(rest)

    do_GET = do_POST = relay

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))


ThreadingHTTPServer((host, port), Relay).serve_forever()
'''

# The one request the stub's check sends: OpenAI's chat completions, as small as it gets.
LLM_REQUEST = {"model": LLM_MODEL, "messages": [{"role": "user", "content": "Say hello."}], "max_tokens": 16,
               "temperature": 0}

LLM_CHECK = r'''"""pickfit's check of an OpenAI-compatible endpoint: `llm_check.py BASE_URL` sends one chat completion and
reads the answer's shape; `llm_check.py BASE_URL --health SECONDS` waits until the server has its model loaded.
It shows that requests round-trip. It says nothing about the answers."""
import json
import sys
import time
import urllib.request

base, args = sys.argv[1].rstrip("/"), sys.argv[2:]
KEY = @KEY@
REQUEST = @REQUEST@


def call(url, data=None, timeout=120):
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return answer.status, json.loads(answer.read() or b"null")


if args[:1] == ["--health"]:
    deadline = time.time() + float(args[1])
    root = base[:-len("/v1")] if base.endswith("/v1") else base
    while time.time() < deadline:
        try:
            if call(root + "/health", timeout=5)[0] == 200:
                sys.exit(0)
        except Exception:
            pass
        time.sleep(1)
    sys.exit("the server did not load its model in time")
try:
    status, answer = call(base + "/chat/completions", REQUEST)
    message = answer["choices"][0]["message"]
    text, tokens = message.get("content"), answer["usage"]["completion_tokens"]
except Exception as err:
    sys.exit("llm-stub check failed: %s: %s" % (type(err).__name__, err))
if status != 200 or message.get("role") != "assistant" or not isinstance(text, str) or not isinstance(tokens, int) \
        or tokens < 1:
    sys.exit("llm-stub check failed: the answer is not a chat completion: %s" % json.dumps(answer)[:300])
print("ok: one chat completion round-tripped (model %s, %d completion tokens, %d characters). A wiring check only: "
      "this model is too small for its answers to mean anything." % (answer.get("model"), tokens, len(text)))
'''.replace("@KEY@", json.dumps(LLM_KEY)).replace("@REQUEST@", json.dumps(LLM_REQUEST))

MYSQL_SETUP = ("CREATE DATABASE IF NOT EXISTS pickfit; "
               "CREATE USER IF NOT EXISTS 'pickfit'@'%' IDENTIFIED BY 'pickfit'; "
               "CREATE USER IF NOT EXISTS 'pickfit'@'localhost' IDENTIFIED BY 'pickfit'; "
               "GRANT ALL PRIVILEGES ON *.* TO 'pickfit'@'%' WITH GRANT OPTION; "
               "GRANT ALL PRIVILEGES ON *.* TO 'pickfit'@'localhost' WITH GRANT OPTION; FLUSH PRIVILEGES;")
S3_SETUP = (f"import boto3; s3 = boto3.client('s3', endpoint_url='{AWS_URL}'); "
            f"'{S3_BUCKET}' in [b['Name'] for b in s3.list_buckets()['Buckets']] or s3.create_bucket(Bucket='{S3_BUCKET}')")
_AWS_ENV = f"AWS_ACCESS_KEY_ID={AWS_KEY} AWS_SECRET_ACCESS_KEY={AWS_KEY} AWS_DEFAULT_REGION=us-east-1"

HELPER = r'''#!/bin/sh
# pickfit-services: throwaway services for the calling user, on 127.0.0.1 only (pickfit/verify/services.py).
set -eu
base="${PICKFIT_SERVICES_DIR:-$HOME/.pickfit-services}"
lib=@LIB@
kinds="@KINDS@"
usage() { echo "usage: pickfit-services start|stop [$kinds] | env | status | mail [N] | check llm-stub" >&2; exit 2; }
open() { python3 -c "import socket,sys; socket.create_connection(('127.0.0.1', int(sys.argv[1])), 1)" "$1" 2>/dev/null; }
wait_port() { i=0; while [ $i -lt "${4:-60}" ]; do open "$1" && return 0; i=$((i+1)); sleep 0.5; done
  echo "$2 did not start; its log: $3" >&2; tail -n 15 "$3" >&2 2>/dev/null || true; return 1; }
kill_pid() { [ -f "$1" ] && kill "$(cat "$1")" 2>/dev/null || true; }
pg_bin() { ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -n 1; }
start() { case "$1" in
  postgres)
    pg="$(pg_bin)"; d="$base/postgres"; mkdir -p "$d"
    [ -d "$d/data" ] || "$pg/initdb" -D "$d/data" -U pickfit --auth=trust -E UTF8 >"$d/initdb.log" 2>&1
    open 5432 || "$pg/pg_ctl" -D "$d/data" -l "$d/log" -w -t 60 \
      -o "-h 127.0.0.1 -p 5432 -k $d -c dynamic_shared_memory_type=mmap -c shared_buffers=16MB" start >/dev/null
    "$pg/createdb" -h 127.0.0.1 -p 5432 -U pickfit pickfit 2>/dev/null || true
    echo "postgres: @PG_URL@" ;;
  redis)
    d="$base/redis"; mkdir -p "$d"
    open 6379 || redis-server --bind 127.0.0.1 --port 6379 --protected-mode yes --dir "$d" --save "" \
      --appendonly no --daemonize yes --pidfile "$d/pid" --logfile "$d/log"
    wait_port 6379 redis "$d/log"; echo "redis: @REDIS_URL@" ;;
  http-mock)
    d="$base/http-mock"; mkdir -p "$d"
    open 8080 || { nohup python3 @MOCK_PATH@ 127.0.0.1 8080 >"$d/log" 2>&1 &
      echo $! >"$d/pid"; }
    wait_port 8080 http-mock "$d/log"; echo "http-mock: @MOCK_URL@" ;;
  mysql)
    d="$base/mysql"; mkdir -p "$d"
    [ -d "$d/data/mysql" ] || mariadb-install-db --no-defaults --datadir="$d/data" --force --skip-name-resolve \
      --auth-root-authentication-method=normal --skip-test-db >"$d/install.log" 2>&1 \
      || { echo "mysql: no data directory; its log: $d/install.log" >&2; tail -n 15 "$d/install.log" >&2; return 1; }
    open 3306 || { nohup /usr/sbin/mariadbd --no-defaults --datadir="$d/data" --bind-address=127.0.0.1 --port=3306 \
      --socket="$d/sock" --pid-file="$d/pid" --skip-name-resolve --innodb-use-native-aio=0 \
      --loose-innodb-data-file-buffering=ON --loose-innodb-log-file-buffering=ON \
      --innodb-buffer-pool-size=64M --performance-schema=OFF >"$d/log" 2>&1 &
      }
    wait_port 3306 mysql "$d/log" 120
    mariadb --no-defaults --socket="$d/sock" -u root -e "@MYSQL_SETUP@"
    echo "mysql: @MYSQL_URL@ (MariaDB)" ;;
  smtp)
    d="$base/smtp"; mkdir -p "$d/mail"
    open 1025 || { nohup python3 @SMTP_PATH@ 127.0.0.1 1025 "$d/mail" >"$d/log" 2>&1 &
      echo $! >"$d/pid"; }
    wait_port 1025 smtp "$d/log"
    echo "smtp: @SMTP_URL@ (any sender, recipient and login; nothing is delivered; pickfit-services mail lists it)" ;;
  aws|s3)
    d="$base/aws"; mkdir -p "$d"
    open 4566 || { nohup env @AWS_ENV@ $lib/moto/bin/moto_server -H 127.0.0.1 -p 4566 >"$d/log" 2>&1 &
      echo $! >"$d/pid"; }
    wait_port 4566 aws "$d/log" 120
    env @AWS_ENV@ $lib/moto/bin/python -c "@S3_SETUP@" >>"$d/log" 2>&1 \
      || echo "aws: the bucket @S3_BUCKET@ was not made; see $d/log" >&2
    echo "aws: @AWS_URL@ (moto: S3 with the bucket s3://@S3_BUCKET@, and the other AWS APIs it emulates)" ;;
  git)
    d="$base/git"; mkdir -p "$d/repos"
    if [ ! -d "$d/repos/pickfit.git" ]; then
      git init -q --bare -b main "$d/repos/pickfit.git"
      rm -rf "$d/seed"; git init -q -b main "$d/seed"; echo "# pickfit" >"$d/seed/README.md"
      git -C "$d/seed" add README.md
      git -C "$d/seed" -c user.name=pickfit -c user.email=pickfit@localhost commit -q -m "Initial commit"
      git -C "$d/seed" push -q "$d/repos/pickfit.git" main; rm -rf "$d/seed"
    fi
    open 9418 || git daemon --detach --reuseaddr --listen=127.0.0.1 --port=9418 --base-path="$d/repos" \
      --export-all --enable=receive-pack --pid-file="$d/pid" "$d/repos"
    open 3000 || { nohup python3 @GIT_HTTP_PATH@ 127.0.0.1 3000 "$d/repos" >"$d/log" 2>&1 &
      echo $! >"$d/http.pid"; }
    wait_port 9418 git "$d/log"; wait_port 3000 git "$d/log"
    echo "git: @GIT_URL@ and @GIT_HTTP_URL@ (clone and push, no login)"
    echo "git: for another repository, git init --bare $d/repos/NAME.git" ;;
  llm-stub)
    d="$base/llm-stub"; mkdir -p "$d"
    open 8081 || { nohup $lib/llama/llama-server --model $lib/llama/@MODEL_FILE@ --alias @LLM_MODEL@ \
      --host 127.0.0.1 --port 8081 --ctx-size 4096 --parallel 1 --threads 2 --no-webui --offline >"$d/log" 2>&1 &
      echo $! >"$d/pid"; }
    wait_port 8081 llm-stub "$d/log" 120
    python3 @LLM_CHECK_PATH@ @LLM_URL@ --health 120 \
      || { echo "llm-stub did not load its model; its log: $d/log" >&2; tail -n 15 "$d/log" >&2; return 1; }
    echo "llm-stub: @LLM_URL@ (OpenAI-compatible; any key, e.g. @LLM_KEY@; model @LLM_MODEL@, 135M: a stand-in)" ;;
  *) echo "unknown service: $1 ($kinds)" >&2; exit 2 ;;
esac; }
stop() { case "$1" in
  postgres) [ -d "$base/postgres/data" ] && "$(pg_bin)/pg_ctl" -D "$base/postgres/data" -m fast stop >/dev/null || true ;;
  redis|http-mock|mysql|smtp|llm-stub) kill_pid "$base/$1/pid" ;;
  aws|s3) kill_pid "$base/aws/pid" ;;
  git) kill_pid "$base/git/pid"; kill_pid "$base/git/http.pid" ;;
  *) echo "unknown service: $1" >&2; exit 2 ;;
esac; }
cmd="${1:-}"; [ $# -gt 0 ] && shift
case "$cmd" in
  start) [ $# -gt 0 ] || usage; for s in "$@"; do start "$s"; done ;;
  stop) [ $# -gt 0 ] || set -- $kinds; for s in "$@"; do stop "$s"; done ;;
  env) cat <<'PICKFIT_ENV'
@ENV@
PICKFIT_ENV
    ;;
  status) for p in @PORTS@; do
      open "${p%%:*}" && echo "${p#*:}: running" || echo "${p#*:}: stopped"; done ;;
  mail) if [ $# -gt 0 ]; then cat "$base/smtp/mail/$(printf '%04d' "$1").eml"
    elif [ -f "$base/smtp/mail/index.jsonl" ]; then cat "$base/smtp/mail/index.jsonl"; fi ;;
  check) [ "${1:-}" = llm-stub ] || usage; python3 @LLM_CHECK_PATH@ @LLM_URL@ ;;
  *) usage ;;
esac
'''
for _name, _value in (("LIB", LIB), ("KINDS", " ".join(KIND_NAMES)), ("PG_URL", PG_URL), ("REDIS_URL", REDIS_URL),
                      ("MOCK_PATH", MOCK_PATH), ("MOCK_URL", MOCK_URL), ("MYSQL_SETUP", MYSQL_SETUP),
                      ("MYSQL_URL", MYSQL_URL), ("SMTP_PATH", SMTP_PATH), ("SMTP_URL", SMTP_URL),
                      ("AWS_ENV", _AWS_ENV), ("S3_SETUP", S3_SETUP), ("S3_BUCKET", S3_BUCKET), ("AWS_URL", AWS_URL),
                      ("GIT_HTTP_PATH", GIT_HTTP_PATH), ("GIT_URL", GIT_URL), ("GIT_HTTP_URL", GIT_HTTP_URL),
                      ("MODEL_FILE", MODEL_FILE), ("LLM_MODEL", LLM_MODEL), ("LLM_CHECK_PATH", LLM_CHECK_PATH),
                      ("LLM_URL", LLM_URL), ("LLM_KEY", LLM_KEY),
                      ("ENV", "\n".join(f"{key}={value}" for key, value in ENV.items())),
                      ("PORTS", " ".join(f"{port}:{name}" for name, port in KINDS))):
    HELPER = HELPER.replace(f"@{_name}@", _value)


def _install_file(path: str, text: str, mode: str) -> str:
    data = base64.b64encode(text.encode()).decode()
    return (f"/usr/bin/install -d -m 0755 {path.rsplit('/', 1)[0]} && echo {data} | base64 -d > {path} "
            f"&& chmod {mode} {path}")


# Root, at image build: the helper and pickfit's own servers, root-owned and not writable by the box user.
SERVICES_INSTALL = " && ".join((
    _install_file(MOCK_PATH, HTTP_MOCK, "0644"), _install_file(SMTP_PATH, SMTP_SINK, "0644"),
    _install_file(GIT_HTTP_PATH, GIT_HTTP, "0644"), _install_file(LLM_CHECK_PATH, LLM_CHECK, "0644"),
    _install_file(HELPER_PATH, HELPER, "0755")))
# Root, at image build: moto in its own virtual environment. The last command fails the build when it does not run.
MOTO_INSTALL = (f"/usr/local/bin/python3 -m venv {MOTO_DIR} && {MOTO_DIR}/bin/pip install --no-cache-dir "
                f"--disable-pip-version-check 'moto[server]=={MOTO_VERSION}' && {MOTO_DIR}/bin/moto_server --help "
                "> /dev/null")
# Root, at image build: llama.cpp's server and the model, each checked against its SHA-256. No download at run time.
LLM_INSTALL = (
    f"mkdir -p {LLAMA_DIR} /tmp/llama && curl -fsSL -o /tmp/llama.tgz {LLAMA_URL} "
    f"&& echo '{LLAMA_SHA256}  /tmp/llama.tgz' | sha256sum -c - "
    "&& tar -xzf /tmp/llama.tgz -C /tmp/llama --strip-components=1 "
    f"&& cp -a /tmp/llama/llama-server /tmp/llama/LICENSE /tmp/llama/lib*.so* {LLAMA_DIR}/ "
    "&& rm -rf /tmp/llama /tmp/llama.tgz "
    f"&& curl -fsSL -o {LLAMA_DIR}/{MODEL_FILE} {MODEL_URL} "
    f"&& echo '{MODEL_SHA256}  {LLAMA_DIR}/{MODEL_FILE}' | sha256sum -c - "
    f"&& chown -R root:root {LLAMA_DIR} && chmod -R a+rX,go-w {LLAMA_DIR} && {LLAMA_DIR}/llama-server --version")
# In this order: the two downloads change rarely, so an edit to the helper rebuilds only the last layer.
SERVICES_COMMANDS = (LLM_INSTALL, MOTO_INSTALL, SERVICES_INSTALL)

PROMPT = (
    "Services: this box can start throwaway servers for you, on 127.0.0.1 only. Run "
    f"`pickfit-services start postgres` ({PG_URL}), `pickfit-services start redis` ({REDIS_URL}), "
    f"`pickfit-services start mysql` (MariaDB, {MYSQL_URL}), `pickfit-services start http-mock` ({MOCK_URL}, answers "
    f"any request with a JSON echo of it), `pickfit-services start smtp` ({SMTP_URL}: takes any mail with any login "
    "and delivers none; `pickfit-services mail` lists what arrived), "
    f"`pickfit-services start aws` ({AWS_URL}: an AWS emulator with S3 and a bucket {S3_BUCKET}; keys "
    f"{AWS_KEY}/{AWS_KEY}, region us-east-1), `pickfit-services start git` ({GIT_URL} and {GIT_HTTP_URL}: a remote to "
    f"clone from and push to, no login) or `pickfit-services start llm-stub` ({LLM_URL}: an OpenAI-compatible "
    f"endpoint, also Anthropic's /v1/messages, any key such as {LLM_KEY}, model {LLM_MODEL}). "
    "`pickfit-services env` prints them as DATABASE_URL, REDIS_URL, "
    "MYSQL_URL, MOCK_URL, SMTP_HOST and SMTP_PORT, AWS_ENDPOINT_URL, GIT_URL, OPENAI_BASE_URL and OPENAI_API_KEY. "
    "Start a service as its own install step (so the replay starts it too) before the tool's step that needs it, "
    "and point the tool at these URLs. llm-stub is a 135M model: it shows that the tool's requests go out and an "
    "answer comes back, so check for that (a reply arrived, tokens were counted), never for what the answer says, "
    "and say in the feature's note that a stand-in model answered. There is no MongoDB, Kafka or outside server, "
    "and no real account.")

# What tells that a tool needs a kind. A database or an API word in the extraction's own text is enough; a README
# mentions the same words in passing, so it needs several (README_COUNT; 0: a README never decides).
_KIND_WORDS = {
    "postgres": re.compile(r"\bpostgres(?:ql)?\b|\bpsql\b|\bDATABASE_URL\b|\bpgvector\b", re.I),
    "redis": re.compile(r"\bredis\b|\bREDIS_URL\b", re.I),
    "mysql": re.compile(r"\bmysql\b|\bmariadb\b|\bMYSQL_(?:URL|HOST|PWD|DATABASE)\b", re.I),
    "http-mock": re.compile(r"\b(?:HTTP|REST|GraphQL|API)\s+client\b|\bcurl\s+(?:alternative|replacement)\b|"
                            r"\bpostman\b|\bload[- ]test\w*\b|\bhttp\s+benchmark\w*\b|"
                            r"\bwebhook\s+(?:tester|inspector)\b", re.I),
    "smtp": re.compile(r"\bSMTP\b|\bSMTP_(?:HOST|SERVER|PORT|URL)\b|\bsendmail\b|"
                       r"\bsend(?:s|ing)?\s+(?:an?\s+|test\s+|transactional\s+)?e-?mails?\b|"
                       r"\be-?mail\s+(?:sender|sending|delivery|testing)\b|\bmail\s+(?:server|relay)\b", re.I),
    "aws": re.compile(r"\bS3\b|\bs3://|\bobject\s+storage\b|\bminio\b|\bAWS\b|\bDynamoDB\b|\bSQS\b|\bSNS\b|"
                      r"\bCloudFormation\b|\blocalstack\b"),
    "git": re.compile(r"\bgit://|\bgit\s+(?:remote|server|host|hosting|mirror)s?\b|\bself-hosted\s+git\b|"
                      r"\b(?:push(?:es|ing)?|mirror(?:s|ing)?)\b[^.\n]{0,40}\b(?:remotes?|upstream|origin)\b", re.I),
    "llm-stub": re.compile(r"\bOPENAI_API_KEY\b|\bOPENAI_(?:BASE_URL|API_BASE)\b|\bOpenAI[- ]compatible\b|"
                           r"\bOpenAI\s+API\b|\bANTHROPIC_API_KEY\b", re.I),
}
_DATABASES = ("postgres", "redis", "mysql")
README_COUNT = {"http-mock": 2, "smtp": 3, "aws": 4, "git": 0, "llm-stub": 3}
_DATABASE_COUNT = 3  # across the databases together, as before the others were added


def _cited_texts(ex: Any) -> list[str]:
    out: list[str] = []
    for name in ("name", "summary"):
        cited = getattr(ex, name, None)
        out += [p for p in (getattr(cited, "value", None), getattr(cited, "quote", None)) if isinstance(p, str)]
    pre = getattr(ex, "prerequisites", None)
    for name in ("runtimes", "system_packages", "api_keys"):
        for item in getattr(pre, name, None) or []:
            out += [p for p in (item.value, item.quote) if isinstance(p, str)]
    for name in ("features", "use_cases", "manual_steps"):
        for item in getattr(ex, name, None) or []:
            out += [p for p in (item.value, item.quote) if isinstance(p, str)]
    return out


def service_kinds(ex: Any, readme: str | None = None) -> tuple[str, ...]:
    """The kinds of service the sources say the tool needs, in KINDS' order: a database it stores in, a server an
    HTTP client talks to, a mail server, AWS or S3, a git remote, a model endpoint."""
    own = _cited_texts(ex)
    found = {kind for kind, words in _KIND_WORDS.items() if any(words.search(text) for text in own)}
    if readme:
        counts = {kind: len(words.findall(readme)) for kind, words in _KIND_WORDS.items()}
        if sum(counts[kind] for kind in _DATABASES) >= _DATABASE_COUNT:
            found |= {kind for kind in _DATABASES if counts[kind]}
        found |= {kind for kind, least in README_COUNT.items() if least and counts[kind] >= least}
    return tuple(kind for kind in KIND_NAMES if kind in found)


def needs_services(ex: Any, readme: str | None = None) -> bool:
    """Does the tool need one of the services to run: a database, a server to talk to, a mail server, AWS, a git
    remote or a model endpoint?"""
    return bool(service_kinds(ex, readme))


# ---------------------------------------------------------------- what the harness reads back


def read_mail(box: Any, timeout_s: int = 20) -> list[dict[str, Any]]:
    """What the mail sink received so far in this box, oldest first: n, from, to, subject, bytes, file.

    The sink's files are the box user's own, so a message is evidence that the tool sent mail only when it holds
    something the tool could not have known before pickfit asked (mail_with's fresh word)."""
    ran = box.exec("pickfit-services mail", timeout_s)
    rows: list[dict[str, Any]] = []
    for line in ran.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("n"), int):
            rows.append(row)
    return rows


def mail_with(messages: list[dict[str, Any]], word: str, *, to: str | None = None) -> list[dict[str, Any]]:
    """The messages whose subject holds `word` (and that went to `to`, when given)."""
    return [m for m in messages if word and word in str(m.get("subject") or "")
            and (to is None or to in (m.get("to") or []))]


def llm_request(prompt: str = "Say hello.", *, max_tokens: int = 16, base_url: str = LLM_URL) -> dict[str, Any]:
    """One chat completion request for the stub, as an OpenAI client would send it: url, headers and JSON body."""
    return {"url": f"{base_url.rstrip('/')}/chat/completions",
            "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {LLM_KEY}"},
            "json": {**LLM_REQUEST, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}}


def chat_completion_shape(answer: Any) -> bool:
    """Is `answer` an OpenAI chat completion: an assistant message with text, and a count of completion tokens?
    The shape is all a stand-in model can show."""
    try:
        message = answer["choices"][0]["message"]
        return (message["role"] == "assistant" and isinstance(message["content"], str)
                and isinstance(answer["usage"]["completion_tokens"], int) and answer["usage"]["completion_tokens"] >= 1)
    except (KeyError, IndexError, TypeError):
        return False
