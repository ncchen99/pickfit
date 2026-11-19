"""WebBox: a microVM where Chromium visits one website through pickfit's guard (P3.12).

The VM comes from a provider's machine.Machine (Modal's unless another is handed in) and is driven through that
interface only. Inside the VM (runtime "vm": a real kernel, so nftables and Chromium's own sandbox work):

- uid 1000 (`web`) runs the harness (web_harness.py: browser-use and Chromium). nftables lets it reach
  loopback only, so every byte the browser sends goes through the guard; it holds no key.
- uid 1001 (`guard`) runs mitmdump with web_guard.py on 127.0.0.1:8080: it decides every request and
  logs every flow to a directory only it and root can read. It may not open new connections to loopback.
- root sets the rules, writes the guard's config (site, robots.txt), cuts the network for the offline
  phase (an nftables table that drops the guard's traffic, plus a flag the guard kills flows on) and reads
  the evidence.

Both uids run under the same seccomp filter as ModalBox's VM boxes (no vsock, no io_uring). The VM's
outbound allowlist is ModalBox's: public IPv4 only, never cloud metadata or private ranges.

The host talks to the harness over its stdin/stdout (`run_harness`): model calls arrive as messages and
are answered by the host, so the model key never enters the VM.
"""

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pickfit.verify.box import BoxError
from pickfit.verify.linux_box import NO_VSOCK, NO_VSOCK_SOURCE, _drop_to
from pickfit.verify.machine import ONLINE_CIDRS, Machine  # noqa: F401
from pickfit.verify.modal_box import (  # noqa: F401
    CORE_USD_PER_S,
    GIB_USD_PER_S,
    ModalMachine,
    _missing_image,
    modal_client,
)

APP_NAME = "pickfit-verify"
WEB_UID = 1000
GUARD_UID = 1001
GUARD_PORT = 8080
HERE = Path(__file__).resolve().parent
GUARD_SOURCE = HERE / "web_guard.py"
HARNESS_SOURCE = HERE / "web_harness.py"
BROWSER_USE = "browser-use==0.13.14"
GUARD_PACKAGES = ("mitmproxy==12.3.1", "tldextract==5.4.0")
APT_PACKAGES = ("chromium", "nftables", "fonts-noto-core", "fonts-noto-cjk", "fonts-noto-color-emoji",
                "ca-certificates", "procps")
PYTHON = "/usr/local/bin/python3"
GUARD_CONFIG = "/etc/pickfit/guard.json"
GUARD_LOG = "/var/lib/pickfit-guard/flows.jsonl"
GUARD_STDERR = "/var/log/pickfit-guard.log"
OFFLINE_FLAG = "/run/pickfit-guard/offline"
EVIDENCE = "/home/web/evidence"
SAMPLES = "/home/web/samples"
CPUS = 2.0  # a VM gets 1 vCPU per requested core
MEMORY_MB = 4096
LIFETIME_S = 1800
# browser-use's own phone-home and cloud features stay off; the harness has no network anyway.
AGENT_ENV = ("ANONYMIZED_TELEMETRY=false", "BROWSER_USE_CLOUD_SYNC=false", "BROWSER_USE_VERSION_CHECK=false",
             "BROWSER_USE_CLOUD_HINTS=false", "BROWSER_USE_DISABLE_EXTENSIONS=1", "BROWSER_USE_LOGGING_LEVEL=info",
             "BROWSER_USE_CONFIG_DIR=/home/web/.config/browseruse", "XDG_CACHE_HOME=/home/web/.cache",
             "XDG_CONFIG_HOME=/home/web/.config", "HOME=/home/web", "PATH=/usr/bin:/bin", "LANG=C.UTF-8")

# The browser's uid reaches loopback only; the guard may answer it but not open loopback connections.
RULES = f"""
set -e
/usr/sbin/nft add table inet pickfit_web
/usr/sbin/nft add chain inet pickfit_web out '{{ type filter hook output priority 0; policy accept; }}'
/usr/sbin/nft add rule inet pickfit_web out meta skuid {WEB_UID} oifname lo accept
/usr/sbin/nft add rule inet pickfit_web out meta skuid {WEB_UID} counter drop
/usr/sbin/nft add rule inet pickfit_web out meta skuid {GUARD_UID} ct state established,related accept
/usr/sbin/nft add rule inet pickfit_web out meta skuid {GUARD_UID} ip daddr 127.0.0.0/8 drop
/usr/sbin/nft add rule inet pickfit_web out meta skuid {GUARD_UID} ip6 daddr ::1 drop
/usr/sbin/sysctl -qw kernel.io_uring_disabled=2 2>/dev/null || true
/usr/bin/install -d -m 0755 /usr/local/lib/pickfit /opt/pickfit /etc/pickfit /run/pickfit-guard
/usr/bin/install -d -o {GUARD_UID} -g {GUARD_UID} -m 0700 /var/lib/pickfit-guard
/usr/bin/install -d -o {WEB_UID} -g {WEB_UID} -m 0755 {EVIDENCE} /home/web/downloads {SAMPLES}
/usr/sbin/nft list ruleset | /usr/bin/grep -c 'skuid {WEB_UID}'
"""
OFFLINE_ON = (f"/usr/sbin/nft add table inet pickfit_offline && /usr/sbin/nft add chain inet pickfit_offline out "
              f"'{{ type filter hook output priority -10; policy accept; }}' && /usr/sbin/nft add rule inet "
              f"pickfit_offline out meta skuid {GUARD_UID} oifname != lo drop && /usr/bin/touch {OFFLINE_FLAG}")
OFFLINE_OFF = f"/usr/sbin/nft delete table inet pickfit_offline; /usr/bin/rm -f {OFFLINE_FLAG}"


def image_recipe() -> dict[str, Any]:
    return {"base": "debian_slim:3.12", "apt": APT_PACKAGES, "agent": BROWSER_USE, "guard": GUARD_PACKAGES,
            "users": [WEB_UID, GUARD_UID]}


def image_name() -> str:
    digest = hashlib.sha256(json.dumps(image_recipe(), sort_keys=True).encode()).hexdigest()[:12]
    return f"pickfit-web:{digest}"


def publish_image(client: Any, app: Any, log: Callable[[str], None] = print) -> str:
    import modal

    began = time.monotonic()
    image = (modal.Image.debian_slim(python_version="3.12")
             .apt_install(*APT_PACKAGES)
             .run_commands(f"useradd -u {WEB_UID} -m -s /usr/sbin/nologin web",
                           f"useradd -u {GUARD_UID} -m -s /usr/sbin/nologin guard",
                           f"python -m venv /opt/agent && /opt/agent/bin/pip install --no-cache-dir '{BROWSER_USE}'",
                           "python -m venv /opt/guard && /opt/guard/bin/pip install --no-cache-dir "
                           + " ".join(f"'{p}'" for p in GUARD_PACKAGES)))
    image.build(app)
    name = image_name()
    image.publish(name, client=client)
    log(f"Modal image {name} built and published in {time.monotonic() - began:.0f}s")
    return name


WEB_DISK_GB = 20  # an EC2 volume for the host, Chromium, the two virtual environments and a visit's files
# Read before a visit starts on EC2 (SshMachine.preread): the browser, its libraries and fonts, the two environments.
EC2_PREREAD = ("/usr/lib/chromium", "/usr/lib/x86_64-linux-gnu", "/usr/share/fonts", "/opt/agent", "/opt/guard",
               "/usr/local/lib/python3.12")


def dockerfile() -> str:
    """The web image as a Dockerfile, for a provider that builds from one (EC2): what publish_image() tells Modal's
    builder, line for line. python:3.12-slim is the base sandbox.Dockerfile builds on."""
    guard = " ".join(f"'{p}'" for p in GUARD_PACKAGES)
    return "\n".join((
        "FROM python:3.12-slim",
        f"RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(APT_PACKAGES)} "
        "&& rm -rf /var/lib/apt/lists/*",
        f"RUN useradd -u {WEB_UID} -m -s /usr/sbin/nologin web && useradd -u {GUARD_UID} -m -s /usr/sbin/nologin guard",
        f"RUN python -m venv /opt/agent && /opt/agent/bin/pip install --no-cache-dir '{BROWSER_USE}'",
        f"RUN python -m venv /opt/guard && /opt/guard/bin/pip install --no-cache-dir {guard}", ""))


def ec2_container() -> Any:
    """The web image for an Ec2Machine. Its tag hashes the Dockerfile too, so the AMI follows a change to either."""
    from pickfit.verify.ec2_machine import ContainerImage

    text = dockerfile()
    digest = hashlib.sha256((image_name() + text).encode()).hexdigest()[:12]
    return ContainerImage(f"pickfit-web:{digest}", text, WEB_DISK_GB)


def on_ec2(**kw: Any) -> "WebBox":
    """A WebBox on an EC2 instance instead of a Modal VM (`web_verify --runner ec2`): the same box, the same
    image contents, another provider's machine under it."""
    from pickfit.verify.ec2_machine import Ec2Machine

    box = WebBox(**kw, machine=Ec2Machine(cores=CPUS, memory_mb=MEMORY_MB, lifetime_s=LIFETIME_S,
                                          container=ec2_container(), role="web"))
    box.machine.tags = {"pickfit.kind" if k == "pickfit" else f"pickfit.{k}": v for k, v in box.tags.items()}
    box.machine.log = lambda line: box.log(line)
    box.machine.preread = EC2_PREREAD
    return box


class WebBox:
    """One VM, one site, one visit."""

    def __init__(self, *, site: str, log: Callable[[str], None] = print, client: Any = None,
                 tags: dict[str, str] | None = None, machine: Machine | None = None) -> None:
        self.site = site
        self.log = log
        self.tags = {"pickfit": "web-verify", "site": site[:60], **(tags or {})}
        # Any provider's VM (a real kernel, for nftables and Chromium's own sandbox) started from the web image;
        # Modal's unless one is handed in. Everything below goes through machine.Machine.
        self.machine: Machine = machine or ModalMachine(
            runtime="vm", cores=CPUS, memory_mb=MEMORY_MB, lifetime_s=LIFETIME_S, tags=self.tags,
            app_name=APP_NAME, client=client, log=lambda line: self.log(line), image_name=lambda: image_name(),
            publish=lambda client, app: publish_image(client, app, self.log))
        self.machine.lane = self.machine.purpose = "web"  # the ledger's row for the machine (meter.BoxMeter)
        self._open = False
        self.started_at: float | None = None
        self.start_s: float | None = None

    @property
    def sandbox(self) -> Any:
        """The provider's own handle while the machine is up (Modal's sandbox), else None."""
        return getattr(self.machine, "sandbox", None) if self._open else None

    @property
    def client(self) -> Any:
        return getattr(self.machine, "client", None)

    @property
    def sandbox_id(self) -> str | None:
        return self.machine.machine_id

    # -- lifecycle

    def create_kwargs(self) -> dict[str, Any]:
        """Modal's Sandbox.create arguments (a ModalMachine only)."""
        return self.machine.create_kwargs()  # type: ignore[attr-defined]

    def start(self, guard_config: dict[str, Any]) -> None:
        began = time.monotonic()
        self.machine.start()
        self._open = True
        self.started_at = time.monotonic()
        try:
            rules = self.root(["/usr/bin/bash", "-c", RULES], 60)
            if rules[0] != 0 or rules[1].strip() in ("", "0"):
                raise BoxError(f"network rules failed: {rules[2][-400:]}")
            self.write(NO_VSOCK, NO_VSOCK_SOURCE.encode(), mode="0644")
            self.write("/opt/pickfit/web_guard.py", GUARD_SOURCE.read_bytes(), mode="0644")
            self.write("/opt/pickfit/web_harness.py", HARNESS_SOURCE.read_bytes(), mode="0644")
            self.write(GUARD_CONFIG, json.dumps(guard_config).encode(), mode="0644")
            self._start_guard()
        except Exception:
            self.close()
            raise
        self.start_s = round(time.monotonic() - began, 1)

    def _start_guard(self) -> None:
        argv = [*_drop_to(GUARD_UID), PYTHON, NO_VSOCK, "/usr/bin/env", "-i", "HOME=/home/guard", "LANG=C.UTF-8",
                f"PICKFIT_GUARD_CONFIG={GUARD_CONFIG}", f"PICKFIT_GUARD_LOG={GUARD_LOG}",
                f"PICKFIT_GUARD_OFFLINE={OFFLINE_FLAG}", "/opt/guard/bin/mitmdump", "--listen-host", "127.0.0.1",
                "--listen-port", str(GUARD_PORT), "-s", "/opt/pickfit/web_guard.py",
                "--set", "confdir=/home/guard/.mitmproxy", "--set", "termlog_verbosity=warn",
                "--set", "flow_detail=0", "--set", "stream_large_bodies=5m", "--set", "http3=false"]
        quoted = " ".join(_quote(a) for a in argv)
        script = f"cd /home/guard && /usr/bin/setsid /usr/bin/nohup {quoted} >{GUARD_STDERR} 2>&1 </dev/null &"
        self.root(["/usr/bin/bash", "-c", script], 30)
        probe = ("import socket,time\nfor _ in range(60):\n    try:\n        socket.create_connection(('127.0.0.1', "
                 f"{GUARD_PORT}), 1).close(); print('up'); break\n    except OSError: time.sleep(0.5)\n")
        code, out, _ = self.root([PYTHON, "-c", probe], 45)
        if "up" not in out:
            _, log, _ = self.root(["/usr/bin/tail", "-c", "2000", GUARD_STDERR], 10)
            raise BoxError(f"the guard proxy did not start: {log}")

    def close(self) -> None:
        if not self._open:
            return
        try:
            self.machine.close()
        except Exception as err:  # the provider's lifetime cap reaps it anyway
            self.log(f"{self.machine.provider} close: {type(err).__name__}: {err}")
        self._open = False

    def seconds_alive(self) -> float:
        return 0.0 if self.started_at is None else time.monotonic() - self.started_at

    def usd_per_second(self) -> float:
        return self.machine.usd_per_second()

    # -- root commands and files

    def root(self, argv: list[str], timeout_s: int, stdin: bytes | None = None) -> tuple[int, str, str]:
        proc = self.machine.spawn(argv, timeout_s + 15)
        if stdin is not None:
            proc.stdin.write(stdin)
            proc.stdin.write_eof()
            proc.stdin.drain()
        out = b"".join(c if isinstance(c, bytes) else str(c).encode() for c in proc.stdout)
        err = b"".join(c if isinstance(c, bytes) else str(c).encode() for c in proc.stderr)
        return proc.wait(), out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    def write(self, path: str, data: bytes, *, mode: str = "0644", owner: int | None = None) -> None:
        own = f"-o {owner} -g {owner} " if owner is not None else ""
        code, _, err = self.root(["/usr/bin/bash", "-c", f"/usr/bin/install {own}-m {mode} /dev/stdin {_quote(path)}"],
                                 30, stdin=data)
        if code != 0:
            raise BoxError(f"write {path} failed: {err[-300:]}")

    def read(self, path: str, max_bytes: int = 50_000_000) -> bytes:
        proc = self.machine.spawn(["/usr/bin/head", "-c", str(max_bytes), path], 120)
        data = b"".join(c if isinstance(c, bytes) else str(c).encode() for c in proc.stdout)
        if proc.wait() != 0:
            return b""
        return data

    def list_evidence(self) -> list[str]:
        code, out, _ = self.root(["/usr/bin/find", EVIDENCE, "-maxdepth", "1", "-type", "f", "-printf", "%f\\n"], 30)
        return [n for n in out.splitlines() if n] if code == 0 else []

    def set_offline(self, offline: bool) -> None:
        code, _, err = self.root(["/usr/bin/bash", "-c", OFFLINE_ON if offline else OFFLINE_OFF], 30)
        if offline and code != 0:
            raise BoxError(f"cutting the network failed: {err[-300:]}")

    # -- the harness

    def run_harness(self, start: dict[str, Any], handle: Callable[[dict[str, Any]], dict[str, Any] | None], *,
                    timeout_s: int, stderr_path: Path) -> list[dict[str, Any]]:
        """Run the harness as the browser's uid and relay messages until it reports done; returns every message.

        `handle` gets each message and returns the answer to send (or None). "need_offline" is answered here.
        """
        argv = [*_drop_to(WEB_UID), PYTHON, NO_VSOCK, "/usr/bin/env", "-i", *AGENT_ENV, "/opt/agent/bin/python", "-u",
                "/opt/pickfit/web_harness.py"]
        proc = self.machine.spawn(argv, timeout_s, workdir="/home/web")
        lines: queue.Queue[bytes | None] = queue.Queue()

        def pump_out() -> None:
            buf = b""
            try:
                for chunk in proc.stdout:
                    buf += chunk if isinstance(chunk, bytes) else str(chunk).encode()
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        lines.put(line)
            except Exception:
                pass
            lines.put(None)

        def pump_err() -> None:
            with stderr_path.open("ab") as f:
                try:
                    for chunk in proc.stderr:
                        f.write(chunk if isinstance(chunk, bytes) else str(chunk).encode())
                        f.flush()
                except Exception:
                    pass

        threading.Thread(target=pump_out, daemon=True).start()
        threading.Thread(target=pump_err, daemon=True).start()

        def say(message: dict[str, Any]) -> None:
            proc.stdin.write((json.dumps(message) + "\n").encode())
            proc.stdin.drain()

        say({"type": "start", **start})
        seen: list[dict[str, Any]] = []
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                raw = lines.get(timeout=max(1.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            if raw is None:
                break
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            seen.append(message)
            if message.get("type") == "need_offline":
                self.set_offline(True)
                say({"type": "offline_on"})
                continue
            answer = handle(message)
            if answer is not None:
                say(answer)
            if message.get("type") in ("done", "error"):
                break
        try:
            proc.stdin.write_eof()
            proc.stdin.drain()
        except Exception:
            pass
        return seen


def _quote(arg: str) -> str:
    import shlex

    return shlex.quote(arg)
