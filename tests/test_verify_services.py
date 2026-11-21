"""pickfit.verify.services: what the services box starts, on loopback only, as the user who asks.

The helper is run here for real (/bin/sh), with its ports moved to free ones. pickfit's own servers (the HTTP
mock, the mail sink, the git relay, the model endpoint's check) are the real ones; the servers of other projects
(PostgreSQL, Redis, MariaDB, moto, llama.cpp) are stand-ins that record how they were started, since what is
checked is the helper's own logic: what it starts, where it binds, what it prints, how it stops."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import smtplib
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from pickfit.schema import ExtractionResult
from pickfit.verify import services as sv
from pickfit.verify.box_needs import box_needs
from pickfit.verify.linux_box import image_recipe
from pickfit.verify.services import KIND_NAMES, KINDS, needs_services, service_kinds
from test_profiles import cited, extraction
from verify_fakes import FakeBox

PORTS = (5432, 6379, 8080, 3306, 1025, 4566, 9418, 3000, 8081)

# A stand-in for another project's server: it records how it was started and listens where it was told to.
FAKE_SERVER = r'''
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
seen = []


def record():
    env = {k: os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION")}
    with open(os.path.join(os.environ["FAKE_LOG"], name + ".json"), "w") as f:
        json.dump({"argv": args, "env": env, "requests": seen}, f)


def option(*names):
    for i, arg in enumerate(args):
        for n in names:
            if arg == n and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith(n + "="):
                return arg.split("=", 1)[1]
    return None


class Handler(BaseHTTPRequestHandler):
    def reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        seen.append({"method": self.command, "path": self.path, "authorization": self.headers.get("Authorization"),
                     "body": self.rfile.read(length).decode() if length else ""})
        record()
        out = {"status": "ok"}
        if self.path.endswith("/chat/completions"):
            out = {"id": "c1", "object": "chat.completion", "model": "pickfit-stub", "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = reply

    def log_message(self, *a):
        pass


record()
if option("--daemonize") == "yes":
    if os.fork():
        sys.exit(0)
    os.setsid()
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
pidfile = option("--pidfile", "--pid-file")
if pidfile:
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
ThreadingHTTPServer((option("--host", "-H", "--bind", "--bind-address") or "127.0.0.1",
                     int(option("--port", "-p"))), Handler).serve_forever()
'''

# A stand-in for a program that only has to be called: it records its arguments.
RECORDER = r'''
import json, os, sys
name = os.path.basename(sys.argv[0])
env = {k: os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION")}
with open(os.path.join(os.environ["FAKE_LOG"], name + ".json"), "w") as f:
    json.dump({"argv": sys.argv[1:], "env": env}, f)
for arg in sys.argv[1:]:
    if arg.startswith("--datadir="):
        os.makedirs(os.path.join(arg.split("=", 1)[1], "mysql"), exist_ok=True)
if name == "initdb":
    os.makedirs(sys.argv[sys.argv.index("-D") + 1], exist_ok=True)
'''

PG_CTL = r'''
import json, os, re, signal, socket, subprocess, sys, time
args = sys.argv[1:]
data = args[args.index("-D") + 1]
with open(os.path.join(os.environ["FAKE_LOG"], "pg_ctl-%s.json" % args[-1]), "w") as f:
    json.dump({"argv": args}, f)
if args[-1] == "start":
    options = args[args.index("-o") + 1]
    host, port = re.search(r"-h (\S+)", options).group(1), re.search(r"-p (\d+)", options).group(1)
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postgres")
    subprocess.Popen([server, "--host", host, "--port", port, "--pidfile", os.path.join(data, "postmaster.pid")],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(100):
        try:
            socket.create_connection((host, int(port)), 1).close()
            break
        except OSError:
            time.sleep(0.1)
elif args[-1] == "stop":
    os.kill(int(open(os.path.join(data, "postmaster.pid")).read()), signal.SIGTERM)
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_open(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 1).close()
        return True
    except OSError:
        return False


def program(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
    path.chmod(0o755)


class World:
    """The helper in a directory of its own: its ports moved to free ones, other projects' servers replaced."""

    def __init__(self, root: Path) -> None:
        self.root, self.lib, self.log, self.home = root, root / "lib", root / "log", root / "home"
        for d in (self.lib, self.log, self.home, root / "bin"):
            d.mkdir(parents=True)
        self.ports = {port: free_port() for port in PORTS}
        text = sv.HELPER.replace(sv.LIB, str(self.lib)).replace("/usr/sbin/mariadbd", str(root / "bin" / "mariadbd"))
        text = text.replace("/usr/lib/postgresql", str(root / "pg"))
        text = re.sub(r"(?<![\d.])(%s)(?!\d)" % "|".join(map(str, PORTS)), lambda m: str(self.ports[int(m.group(1))]),
                      text)
        self.helper = root / "pickfit-services"
        self.helper.write_text(text, encoding="utf-8")
        for name, source in (("http_mock.py", sv.HTTP_MOCK), ("smtp_sink.py", sv.SMTP_SINK),
                             ("git_http.py", sv.GIT_HTTP), ("llm_check.py", sv.LLM_CHECK)):
            (self.lib / name).write_text(source, encoding="utf-8")
        (root / "bin" / "python3").write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n', encoding="utf-8")
        (root / "bin" / "python3").chmod(0o755)
        for name in ("redis-server", "mariadbd"):
            program(root / "bin" / name, FAKE_SERVER)
        for name in ("mariadb-install-db", "mariadb"):
            program(root / "bin" / name, RECORDER)
        program(root / "pg" / "17" / "bin" / "postgres", FAKE_SERVER)
        program(root / "pg" / "17" / "bin" / "pg_ctl", PG_CTL)
        for name in ("initdb", "createdb"):
            program(root / "pg" / "17" / "bin" / name, RECORDER)
        program(self.lib / "moto" / "bin" / "moto_server", FAKE_SERVER)
        program(self.lib / "moto" / "bin" / "python", RECORDER)
        program(self.lib / "llama" / "llama-server", FAKE_SERVER)
        self.env = {"PATH": f"{root / 'bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": str(self.home),
                    "FAKE_LOG": str(self.log), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                    "LANG": "C.UTF-8"}

    def run(self, *args: str, timeout: int = 90) -> subprocess.CompletedProcess:
        return subprocess.run(["/bin/sh", str(self.helper), *args], env=self.env, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)

    def port(self, kind: str) -> int:
        return self.ports[dict(KINDS)[kind]]

    def seen(self, name: str) -> dict[str, Any]:
        return json.loads((self.log / f"{name}.json").read_text(encoding="utf-8"))

    def status(self) -> dict[str, str]:
        return dict(line.split(": ") for line in self.run("status").stdout.splitlines())

    def closed(self, port: int) -> bool:
        for _ in range(50):
            if not is_open(port):
                return True
            time.sleep(0.1)
        return False

    def stop_all(self) -> None:
        self.run("stop")
        for pid_file in self.home.rglob("*pid"):
            try:
                os.kill(int(pid_file.read_text().split()[0]), signal.SIGKILL)
            except (OSError, ValueError, IndexError):
                pass


@pytest.fixture
def world(tmp_path: Path):
    w = World(tmp_path)
    yield w
    w.stop_all()


# ---------------------------------------------------------------- the helper


def test_the_helper_parses_and_knows_every_kind(world: World) -> None:
    assert subprocess.run(["/bin/sh", "-n", str(world.helper)], capture_output=True).returncode == 0
    for name in ("HTTP_MOCK", "SMTP_SINK", "GIT_HTTP", "LLM_CHECK"):
        compile(getattr(sv, name), name, "exec")
    assert not re.findall(r"@[A-Z_0-9]+@", sv.HELPER), "every placeholder is filled"
    assert world.status() == {kind: "stopped" for kind in KIND_NAMES}
    usage = world.run()
    assert usage.returncode == 2 and all(kind in usage.stderr for kind in KIND_NAMES)
    unknown = world.run("start", "mongodb")
    assert unknown.returncode == 2 and "unknown service: mongodb" in unknown.stderr
    assert world.run("stop").returncode == 0  # nothing runs: nothing to stop, no error
    assert world.run("mail").stdout == "" and world.run("check", "postgres").returncode == 2


def test_env_prints_every_address_and_no_secret() -> None:
    w_env = subprocess.run(["/bin/sh", "-c", sv.HELPER, "pickfit-services", "env"], capture_output=True, text=True)
    lines = dict(line.split("=", 1) for line in w_env.stdout.splitlines())
    assert lines == sv.ENV
    assert lines["DATABASE_URL"] == sv.PG_URL and lines["MYSQL_URL"].startswith("mysql://pickfit:pickfit@127.0.0.1:3306")
    assert (lines["SMTP_HOST"], lines["SMTP_PORT"]) == ("127.0.0.1", "1025")
    assert lines["AWS_ENDPOINT_URL"] == lines["S3_ENDPOINT"] == "http://127.0.0.1:4566"
    # The model endpoint: a base URL and a key that is nobody's.
    assert lines["OPENAI_BASE_URL"] == "http://127.0.0.1:8081/v1" and lines["OPENAI_API_KEY"] == "sk-pickfit-stand-in"
    assert lines["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8081"
    # Every address is the box's own loopback.
    for value in lines.values():
        host = re.search(r"//(?:[^@/]*@)?([^:/]+)", value)
        assert host is None or host.group(1) == "127.0.0.1", value


def test_every_kind_binds_to_loopback_and_nothing_asks_for_root() -> None:
    h = sv.HELPER
    for flag in ("--bind 127.0.0.1", "-h 127.0.0.1", "127.0.0.1 8080", "--bind-address=127.0.0.1", "127.0.0.1 1025",
                 "-H 127.0.0.1", "--listen=127.0.0.1", "127.0.0.1 3000", "--host 127.0.0.1"):
        assert flag in h, flag
    assert "sudo" not in h and "su " not in h and "0.0.0.0" not in h and "setpriv" not in h
    # Nothing is fetched when a service starts: the model and every server are in the image.
    assert "curl" not in h and "wget" not in h and "--offline" in h and "pip " not in h
    assert not re.findall(r"https?://(?!127\.0\.0\.1)", h)
    # pickfit's own servers refuse any other address.
    for source in (sv.HTTP_MOCK, sv.SMTP_SINK, sv.GIT_HTTP):
        ran = subprocess.run([sys.executable, "-c", source, "0.0.0.0", "1", "/tmp"], capture_output=True, text=True)
        assert ran.returncode != 0 and "127.0.0.1 only" in ran.stderr


@pytest.mark.parametrize("kind", KIND_NAMES)
def test_a_kind_starts_says_where_it_is_and_stops(world: World, kind: str) -> None:
    if kind == "git" and shutil.which("git") is None:
        pytest.skip("no git here")
    port = world.port(kind)
    started = world.run("start", kind)
    assert started.returncode == 0, started.stderr
    assert started.stdout.startswith(f"{kind}: ") and f"127.0.0.1:{port}" in started.stdout
    assert world.status()[kind] == "running" and is_open(port)
    others = [k for k in KIND_NAMES if k != kind]
    assert all(world.status()[k] == "stopped" for k in others), "only what was asked for runs"
    if kind == "postgres":
        assert f"-h 127.0.0.1 -p {port}" in world.seen("pg_ctl-start")["argv"][-2]
        assert world.seen("createdb")["argv"][:4] == ["-h", "127.0.0.1", "-p", str(port)]
        assert "--auth=trust" in world.seen("initdb")["argv"]
    if kind == "redis":
        argv = world.seen("redis-server")["argv"]
        assert argv[:4] == ["--bind", "127.0.0.1", "--port", str(port)] and argv[argv.index("--save") + 1] == ""
    if kind == "http-mock":
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/hello?x=1", timeout=5) as answer:
            assert json.load(answer)["path"] == "/hello?x=1"
    if kind == "mysql":
        assert world.seen("mariadb-install-db")["argv"][0] == "--no-defaults"  # the system's config is never read
        assert "--auth-root-authentication-method=normal" in world.seen("mariadb-install-db")["argv"]
        argv = world.seen("mariadbd")["argv"]
        assert argv[0] == "--no-defaults" and "--bind-address=127.0.0.1" in argv and f"--port={port}" in argv
        assert all(a.split("=", 1)[1].startswith(str(world.home)) for a in argv
                   if a.startswith(("--datadir=", "--socket=", "--pid-file=")))
        client = world.seen("mariadb")["argv"]
        assert client[0] == "--no-defaults" and "CREATE DATABASE IF NOT EXISTS pickfit" in client[-1]
        assert "(MariaDB)" in started.stdout
    if kind == "smtp":
        with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
            smtp.sendmail("tool@example.com", ["someone@example.org"], "Subject: hello\r\n\r\nbody\r\n")
        assert json.loads(world.run("mail").stdout)["subject"] == "hello"
    if kind == "aws":
        assert world.seen("moto_server") == {"argv": ["-H", "127.0.0.1", "-p", str(port)], "requests": [], "env": {
            "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_DEFAULT_REGION": "us-east-1"}}
        made = world.seen("python")
        assert made["argv"][0] == "-c" and "create_bucket(Bucket='pickfit')" in made["argv"][1]
        assert f"endpoint_url='http://127.0.0.1:{port}'" in made["argv"][1] and "s3://pickfit" in started.stdout
        world.run("stop", "s3")  # the other name for it
        assert world.closed(port)
        assert world.run("start", "s3").stdout.startswith("aws: ")
    if kind == "git":
        http = world.ports[3000]
        assert is_open(http) and f"http://127.0.0.1:{http}/pickfit.git" in started.stdout
    if kind == "llm-stub":
        argv = world.seen("llama-server")["argv"]
        assert argv[argv.index("--host") + 1] == "127.0.0.1" and argv[argv.index("--port") + 1] == str(port)
        assert "--offline" in argv and "--no-webui" in argv, "the server fetches nothing and serves no page"
        assert argv[argv.index("--model") + 1] == str(world.lib / "llama" / sv.MODEL_FILE)
        assert argv[argv.index("--alias") + 1] == sv.LLM_MODEL
        checked = world.run("check", "llm-stub")
        assert checked.returncode == 0 and checked.stdout.startswith("ok: one chat completion round-tripped")
        sent = world.seen("llama-server")["requests"][-1]
        assert (sent["method"], sent["path"]) == ("POST", "/v1/chat/completions")
        assert sent["authorization"] == "Bearer sk-pickfit-stand-in" and json.loads(sent["body"]) == sv.LLM_REQUEST
    # Asking again starts no second server; stopping closes the port.
    again = world.run("start", kind)
    assert again.returncode == 0 and world.status()[kind] == "running"
    assert world.run("stop", kind).returncode == 0
    assert world.closed(port) and world.status()[kind] == "stopped"
    if kind == "git":
        assert world.closed(world.ports[3000])


def test_several_kinds_start_in_one_call_and_stop_together(world: World) -> None:
    started = world.run("start", "http-mock", "smtp", "redis")
    assert started.returncode == 0 and [line.split(":")[0] for line in started.stdout.splitlines()] == [
        "http-mock", "smtp", "redis"]
    assert world.run("stop").returncode == 0
    assert all(world.closed(world.port(kind)) for kind in ("http-mock", "smtp", "redis"))


def test_a_service_that_does_not_come_up_fails_the_step(world: World) -> None:
    (world.lib / "llama" / "llama-server").write_text("#!/bin/sh\necho 'error: failed to load model' >&2; exit 1\n")
    helper = world.helper.read_text(encoding="utf-8").replace('wait_port %d llm-stub "$d/log" 120' % world.port("llm-stub"),
                                                              'wait_port %d llm-stub "$d/log" 4' % world.port("llm-stub"))
    world.helper.write_text(helper, encoding="utf-8")
    failed = world.run("start", "llm-stub")
    assert failed.returncode != 0 and "llm-stub did not start" in failed.stderr
    assert "failed to load model" in failed.stderr  # the log's last lines, so the agent sees why


# ---------------------------------------------------------------- the mail sink


@pytest.fixture
def sink(tmp_path: Path):
    port, store = free_port(), tmp_path / "mail"
    proc = subprocess.Popen([sys.executable, "-c", sv.SMTP_SINK, "127.0.0.1", str(port), str(store)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if is_open(port):
            break
        time.sleep(0.05)
    yield port, store
    proc.kill()
    proc.wait()


def test_the_mail_sink_keeps_what_arrives_and_delivers_nothing(sink: tuple[int, Path]) -> None:
    port, store = sink
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "tool@example.com", "a@example.org, b@example.org", \
        "Report pickfit-7f3a"
    message.set_content("line one\n.a line that starts with a dot\nline three\n")
    with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
        assert smtp.ehlo()[0] == 250 and smtp.has_extn("auth") and not smtp.has_extn("starttls")
        smtp.login("anyone", "any password")  # a tool configured with a login still gets through
        smtp.send_message(message)
        smtp.sendmail("second@example.com", ["c@example.org"], "Subject: two\r\n\r\nhi\r\n")
        assert smtp.docmd("RCPT", "TO:<x@example.org>")[0] == 503  # no MAIL first
        assert smtp.docmd("STARTTLS")[0] == 454 and smtp.docmd("EXPN", "list")[0] == 502
    rows = [json.loads(line) for line in (store / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["n"], r["from"], r["to"], r["subject"], r["file"]) for r in rows] == [
        (1, "tool@example.com", ["a@example.org", "b@example.org"], "Report pickfit-7f3a", "0001.eml"),
        (2, "second@example.com", ["c@example.org"], "two", "0002.eml")]
    kept = (store / "0001.eml").read_bytes()
    assert b"\r\n.a line that starts with a dot\r\n" in kept and rows[0]["bytes"] == len(kept)
    # What the harness reads back, through the box user's own command.
    box = FakeBox({"pickfit-services mail": (0, (store / "index.jsonl").read_text(encoding="utf-8") + "not json\n", "")})
    mail = sv.read_mail(box)
    assert [m["n"] for m in mail] == [1, 2] and box.ran == [("pickfit-services mail", 20)]
    assert [m["n"] for m in sv.mail_with(mail, "pickfit-7f3a")] == [1]
    assert sv.mail_with(mail, "pickfit-7f3a", to="c@example.org") == [] and sv.mail_with(mail, "") == []
    assert sv.read_mail(FakeBox()) == []  # nothing arrived


# ---------------------------------------------------------------- the git host


def test_the_git_host_takes_a_clone_and_a_push_over_http(world: World, tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("no git here")
    started = world.run("start", "git")
    assert started.returncode == 0, started.stderr
    http, daemon = world.ports[3000], world.ports[9418]

    def git(*args: str, cwd: Path = tmp_path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args], cwd=cwd,
                              env={**world.env, "GIT_TERMINAL_PROMPT": "0"}, capture_output=True, text=True, timeout=60)

    cloned = git("clone", f"http://127.0.0.1:{http}/pickfit.git", "one")
    assert cloned.returncode == 0, cloned.stderr
    assert (tmp_path / "one" / "README.md").read_text(encoding="utf-8") == "# pickfit\n"
    (tmp_path / "one" / "new.txt").write_text("pushed over http\n", encoding="utf-8")
    assert git("add", "new.txt", cwd=tmp_path / "one").returncode == 0
    assert git("commit", "-q", "-m", "add a file", cwd=tmp_path / "one").returncode == 0
    pushed = git("push", "origin", "main", cwd=tmp_path / "one")
    assert pushed.returncode == 0, pushed.stderr
    # The same repository through git's own protocol holds the pushed commit.
    again = git("clone", f"git://127.0.0.1:{daemon}/pickfit.git", "two")
    assert again.returncode == 0, again.stderr
    assert (tmp_path / "two" / "new.txt").read_text(encoding="utf-8") == "pushed over http\n"
    missing = git("clone", f"http://127.0.0.1:{http}/nothing.git", "three")
    assert missing.returncode != 0


# ---------------------------------------------------------------- the stand-in model endpoint


class OpenAIShaped(BaseHTTPRequestHandler):
    """An endpoint that takes what an OpenAI client sends and nothing else."""

    answer: dict[str, Any] = {}
    seen: list[dict[str, Any]] = []

    def do_GET(self) -> None:
        self._send(200 if self.path == "/health" else 404, {"status": "ok"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append({"path": self.path, "authorization": self.headers.get("Authorization"), "body": body})
        ok = (self.path == "/v1/chat/completions" and self.headers.get("Content-Type") == "application/json"
              and (self.headers.get("Authorization") or "").startswith("Bearer ") and isinstance(body.get("model"), str)
              and all(m.get("role") in ("system", "user", "assistant") and isinstance(m.get("content"), str)
                      for m in body.get("messages") or [None]) and isinstance(body.get("max_tokens"), int))
        self._send(200 if ok else 400, type(self).answer if ok else {"error": {"message": "not a chat completion"}})

    def _send(self, status: int, out: dict[str, Any]) -> None:
        data = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


COMPLETION = {"id": "chatcmpl-1", "object": "chat.completion", "model": "pickfit-stub", "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "Hello there."}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}}


@pytest.fixture
def endpoint():
    OpenAIShaped.answer, OpenAIShaped.seen = COMPLETION, []
    server = ThreadingHTTPServer(("127.0.0.1", 0), OpenAIShaped)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


def check(base: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", sv.LLM_CHECK, base, *args], capture_output=True, text=True, timeout=30)


def test_the_stubs_request_is_an_openai_chat_completion(endpoint: str) -> None:
    ran = check(endpoint)
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith("ok: one chat completion round-tripped (model pickfit-stub, 4 completion tokens, 12 "
                                 "characters)") and "wiring check only" in ran.stdout
    sent = OpenAIShaped.seen[-1]
    assert sent == {"path": "/v1/chat/completions", "authorization": "Bearer sk-pickfit-stand-in",
                    "body": {"model": "pickfit-stub", "messages": [{"role": "user", "content": "Say hello."}],
                             "max_tokens": 16, "temperature": 0}}
    # The harness's own request has the same shape, and the same endpoint takes it.
    asked = sv.llm_request("What is 2+2?", max_tokens=8, base_url=endpoint)
    assert asked["url"] == f"{endpoint}/chat/completions" and asked["json"]["messages"][0]["content"] == "What is 2+2?"
    request = urllib.request.Request(asked["url"], data=json.dumps(asked["json"]).encode(), headers=asked["headers"])
    with urllib.request.urlopen(request, timeout=10) as answer:
        assert sv.chat_completion_shape(json.load(answer))
    assert sv.llm_request()["url"] == "http://127.0.0.1:8081/v1/chat/completions"
    assert check(endpoint, "--health", "5").returncode == 0  # the server says its model is loaded


@pytest.mark.parametrize("answer", [
    {}, {"choices": []}, {"choices": [{"message": {"role": "assistant", "content": None}}], "usage": {"completion_tokens": 1}},
    {"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": {"completion_tokens": 0}},
    {"choices": [{"message": {"role": "user", "content": "hi"}}], "usage": {"completion_tokens": 2}},
    {"error": {"message": "model not loaded"}},
])
def test_an_answer_that_is_not_a_chat_completion_fails_the_check(endpoint: str, answer: dict[str, Any]) -> None:
    OpenAIShaped.answer = answer
    ran = check(endpoint)
    assert ran.returncode != 0 and "llm-stub check failed" in ran.stderr
    assert not sv.chat_completion_shape(answer)


def test_a_dead_endpoint_fails_the_check_and_the_wait() -> None:
    dead = f"http://127.0.0.1:{free_port()}/v1"
    assert check(dead).returncode != 0
    waited = check(dead, "--health", "1")
    assert waited.returncode != 0 and "did not load its model" in waited.stderr


# ---------------------------------------------------------------- the image


def test_the_image_brings_everything_so_nothing_is_fetched_at_run_time() -> None:
    recipe = image_recipe(services=True)
    assert {"postgresql", "redis-server", "mariadb-server"} <= set(recipe.packages)
    llm, moto, files = recipe.commands
    assert (llm, moto, files) == (sv.LLM_INSTALL, sv.MOTO_INSTALL, sv.SERVICES_INSTALL)
    # The server and the model are each one named release, checked against a pinned SHA-256 before use.
    assert sv.LLAMA_URL in llm and f"echo '{sv.LLAMA_SHA256}  /tmp/llama.tgz' | sha256sum -c -" in llm
    assert sv.MODEL_URL in llm and f"echo '{sv.MODEL_SHA256}  {sv.LLAMA_DIR}/{sv.MODEL_FILE}' | sha256sum -c -" in llm
    assert "/resolve/main/" not in sv.MODEL_URL and re.search(r"/resolve/[0-9a-f]{40}/", sv.MODEL_URL)
    assert re.fullmatch(r"[0-9a-f]{64}", sv.LLAMA_SHA256) and re.fullmatch(r"[0-9a-f]{64}", sv.MODEL_SHA256)
    assert llm.endswith(f"{sv.LLAMA_DIR}/llama-server --version")  # a build whose server does not run fails
    assert f"'moto[server]=={sv.MOTO_VERSION}'" in moto and moto.endswith("moto_server --help > /dev/null")
    # The box user cannot rewrite what it runs: root owns the files, and they are not writable by others.
    assert f"chown -R root:root {sv.LLAMA_DIR}" in llm and "go-w" in llm
    for path in (sv.HELPER_PATH, sv.MOCK_PATH, sv.SMTP_PATH, sv.GIT_HTTP_PATH, sv.LLM_CHECK_PATH):
        assert path.startswith("/usr/local/") and path in files
    # A plain box is the image it was.
    assert image_recipe().commands == () and image_recipe().packages == ()


def test_the_agent_is_told_what_each_stand_in_shows() -> None:
    for kind in KIND_NAMES:
        assert f"`pickfit-services start {kind}`" in sv.PROMPT, kind
    assert "as its own install step" in sv.PROMPT and "pickfit-services mail" in sv.PROMPT
    assert "never for what the answer says" in sv.PROMPT and "a stand-in model answered" in sv.PROMPT
    assert sv.STAND_INS == {"http-mock", "smtp", "aws", "git", "llm-stub"}


# ---------------------------------------------------------------- which records get the services box


def ex(**over: Any) -> ExtractionResult:
    data = extraction(install_methods=[{"method": "pipx", "command": "pipx install tool", "platforms": []}])
    pre = over.pop("pre", None)
    if pre:
        data["prerequisites"] = {**data["prerequisites"], **pre}
    data.update(over)
    return ExtractionResult.model_validate(data)


@pytest.mark.parametrize("over, kinds", [
    ({"summary": cited("A MySQL schema diff tool.", "diff two MySQL schemas")}, ("mysql",)),
    ({"pre": {"runtimes": [cited("MariaDB 10.6+", "requires MariaDB 10.6 or newer")]}}, ("mysql",)),
    ({"features": [cited("Sends e-mail through any SMTP server", "SMTP delivery")]}, ("smtp",)),
    ({"summary": cited("Send emails from the command line.", "a CLI that sends emails")}, ("smtp",)),
    ({"summary": cited("Sync a directory to S3.", "sync files to an S3 bucket")}, ("aws",)),
    ({"use_cases": [cited("Browse DynamoDB tables", "a TUI for DynamoDB")]}, ("aws",)),
    ({"features": [cited("Mirrors every branch to a second remote", "push to a git remote on every commit")]}, ("git",)),
    ({"pre": {"api_keys": [cited("OPENAI_API_KEY", "export OPENAI_API_KEY=...")]}}, ("llm-stub",)),
    ({"summary": cited("A chat client for any OpenAI-compatible server.", "works with OpenAI-compatible APIs")},
     ("llm-stub",)),
    ({"summary": cited("Copy tables from PostgreSQL to MySQL and cache in Redis.", "Postgres to MySQL")},
     ("postgres", "redis", "mysql")),
])
def test_what_the_sources_say_picks_the_kinds(over: dict[str, Any], kinds: tuple[str, ...]) -> None:
    assert service_kinds(ex(**over)) == kinds and needs_services(ex(**over))
    need = box_needs(ex(**over))
    assert need.services and f"needs a server to talk to ({', '.join(kinds)}) -> the services box" in need.why


@pytest.mark.parametrize("over, readme", [
    ({}, None),
    ({"summary": cited("A terminal UI for git.", "stage, commit and browse history")}, "git clone https://example.com/x && cd x"),
    ({"summary": cited("A static site generator.", "builds a site")}, "Questions? Send an email to the maintainers."),
    ({"summary": cited("A CSV viewer.", "view CSV files")}, "Can also read from S3 if you ask it to."),
    ({"summary": cited("A note-taking TUI.", "notes")}, "Stores notes in SQLite. An OpenAI integration is planned."),
    ({"summary": cited("A fuzzy finder.", "find files")}, "Deploy on AWS or anywhere. AWS is optional."),
    ({"summary": cited("An image optimiser.", "shrinks PNG files")}, "Push your changes and open a pull request."),
    ({"summary": cited("A mailbox format converter.", "converts mbox to Maildir")}, None),
    ({"summary": cited("A Markdown linter.", "lint Markdown")}, "Inspired by MySQL Workbench's look."),
])
def test_a_passing_mention_does_not_pick_the_services_box(over: dict[str, Any], readme: str | None) -> None:
    assert service_kinds(ex(**over), readme) == () and not needs_services(ex(**over), readme)
    assert not box_needs(ex(**over), readme=readme).services


def test_a_readme_that_means_it_counts() -> None:
    assert service_kinds(ex(), "Configure SMTP_HOST. The SMTP server must allow relaying. SMTP auth is optional.") == (
        "smtp",)
    assert service_kinds(ex(), "Needs OPENAI_API_KEY. Set OPENAI_BASE_URL for an OpenAI-compatible server.") == (
        "llm-stub",)
    assert service_kinds(ex(), "Upload to S3. Set the S3 bucket. S3 credentials come from AWS.") == ("aws",)
    # Databases count together, as they did when there were two.
    assert service_kinds(ex(), "Works with Postgres, MySQL and Redis.") == ("postgres", "redis", "mysql")
    assert service_kinds(ex(), "Exports to Postgres if you want.") == ()
    # A README never decides that a tool needs a git remote: every README says `git clone`.
    assert service_kinds(ex(), "git remote add origin x; push to the remote; git mirror; git server") == ()
