"""ModalBox: the Box interface on a Modal Sandbox under gVisor (P3.6).

- Runtime gVisor, CPU and memory as request = limit (1 physical core is 2
  vCPU), a lifetime timeout; every command also runs under an in-box
  `timeout -s KILL`.
- Commands run as uid 1000 through `setpriv` (no capabilities, no new
  privileges), with an empty environment except BOX_ENV, and `ulimit` caps on
  processes, open files and file size: Modal has no pids or disk parameter.
- Network: created with an allowlist of public IPv4 ranges, so it can be
  tightened later; cloud metadata (169.254.0.0/16) and private ranges are
  never on it. set_network(False) replaces it with an empty allowlist
  (`_experimental_set_outbound_network_policy`, Alpha).
- Image: built once from sandbox.Dockerfile and published as
  `pickfit-sbx:<Dockerfile hash>`; boxes start from that name, and only a
  missing name triggers the build. (`Image.from_name(...).hydrate()` is not
  supported by the client, so the name is resolved by Sandbox.create.)

Credentials come from MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in .env and go to
an explicit modal.Client; nothing is put into the process environment, and the
sandbox gets no secrets.
"""

from __future__ import annotations

import ipaddress
import shlex
import threading
import time
from collections.abc import Callable
from typing import Any

from pickfit.env import require_env
from pickfit.verify.box import (
    BOX_ENV,
    BOX_HOME,
    BOX_WORKDIR,
    HOST_GRACE_S,
    OUTPUT_HEAD_BYTES,
    OUTPUT_TAIL_BYTES,
    SANDBOX_DOCKERFILE,
    Box,
    BoxError,
    BoxLimits,
    ExecResult,
    _Capture,
    sandbox_image_tag,
)

APP_NAME = "pickfit-verify"
BOX_UID = 1000
# Never reachable from a box: cloud metadata and link-local, private and shared address space.
BLOCKED_NETS = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12",
                "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4")


def public_cidrs(blocked: tuple[str, ...] = BLOCKED_NETS) -> list[str]:
    """0.0.0.0/0 minus `blocked`, as the fewest CIDRs."""
    nets = [ipaddress.ip_network("0.0.0.0/0")]
    for block in map(ipaddress.ip_network, blocked):
        nets = [part for net in nets
                for part in (net.address_exclude(block) if block.subnet_of(net) else
                             ([] if net.subnet_of(block) else [net]))]
    return [str(n) for n in ipaddress.collapse_addresses(nets)]


ONLINE_CIDRS = public_cidrs()


def modal_client() -> Any:
    import modal

    return modal.Client.from_credentials(require_env("MODAL_TOKEN_ID"), require_env("MODAL_TOKEN_SECRET"))


def publish_image(client: Any, app: Any, *, log: Callable[[str], None] = print) -> str:
    """Build the sandbox image from sandbox.Dockerfile and publish it under its hash name.

    Modal caches the build, so an unchanged Dockerfile takes a few seconds.
    """
    import modal

    name = sandbox_image_tag()
    began = time.monotonic()
    image = modal.Image.from_dockerfile(SANDBOX_DOCKERFILE, context_dir=SANDBOX_DOCKERFILE.parent,
                                        ignore=lambda path: True)
    image.build(app)
    image.publish(name, client=client)
    log(f"Modal image {name} built and published in {time.monotonic() - began:.0f}s")
    return name


def ensure_published_image(log: Callable[[str], None] = print) -> str:
    """Publish the image for the current Dockerfile before parallel boxes start; returns its name."""
    import modal

    client = modal_client()
    app = modal.App.lookup(APP_NAME, create_if_missing=True, client=client)
    return publish_image(client, app, log=log)


def _missing_image(err: Exception) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return "notfound" in text.replace(" ", "") or "not found" in text


class ModalBox(Box):
    """A Modal Sandbox (gVisor) driven like a DockerBox."""

    runner = "modal-gvisor"
    image = sandbox_image_tag()

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 app_name: str = APP_NAME, client: Any = None, log: Callable[[str], None] = print) -> None:
        self.limits = limits
        self.tags = {"pickfit": "verify", **(tags or {})}
        self.app_name = app_name
        self.client = client
        self.log = log
        self.sandbox: Any = None
        self.started = False
        self.start_s: float | None = None
        self.network_enabled = True
        self.sandbox_id: str | None = None

    # -- lifecycle

    def create_kwargs(self) -> dict[str, Any]:
        """Sandbox.create arguments other than app, image and client (separate so tests can check them)."""
        lim = self.limits
        cores = lim.cpus / 2  # Modal counts physical cores; one core is two vCPU
        return {"runtime": "gvisor", "timeout": lim.lifetime_s, "cpu": (cores, cores),
                "memory": (lim.memory_mb, lim.memory_mb), "workdir": "/",
                "outbound_cidr_allowlist": ONLINE_CIDRS, "outbound_domain_allowlist": [],
                "tags": self.tags}

    def start(self) -> None:
        if self.started:
            return
        import modal

        began = time.monotonic()
        self.client = self.client or modal_client()
        app = modal.App.lookup(self.app_name, create_if_missing=True, client=self.client)
        self.image = sandbox_image_tag()

        def create() -> Any:
            return modal.Sandbox.create("sleep", str(self.limits.lifetime_s), app=app, client=self.client,
                                        image=modal.Image.from_name(self.image), **self.create_kwargs())

        try:
            try:
                self.sandbox = create()
            except Exception as err:
                if not _missing_image(err):
                    raise
                publish_image(self.client, app, log=self.log)  # first box after a Dockerfile change
                self.sandbox = create()
        except Exception as err:
            raise BoxError(f"Modal sandbox create failed: {type(err).__name__}: {err}") from err
        self.sandbox_id = getattr(self.sandbox, "object_id", None)
        self.started = True
        setup = self._exec_raw(["mkdir", "-p", BOX_WORKDIR, f"{BOX_HOME}/.local/bin"], 60, as_root=True)
        chown = self._exec_raw(["chown", "-R", f"{BOX_UID}:{BOX_UID}", BOX_HOME], 60, as_root=True)
        if setup.exit_code != 0 or chown.exit_code != 0:
            self.close()
            raise BoxError(f"box setup failed: {(setup.stderr or chown.stderr).strip()[-500:]}")
        self.start_s = round(time.monotonic() - began, 2)

    def close(self) -> None:
        if not self.started:
            return
        try:
            self.sandbox.terminate()
        except Exception as err:  # already gone; the lifetime timeout reaps it anyway
            self.log(f"modal terminate: {type(err).__name__}: {err}")
        self.started = False

    # -- commands and files

    def _require_started(self) -> None:
        if not self.started:
            raise BoxError("box is not started")

    def user_argv(self, command: str, timeout_s: int, cwd: str) -> list[str]:
        """argv that runs `command` as the box user with the limits (separate so tests can check it)."""
        lim = self.limits
        guard = (f"ulimit -u {lim.pids} -n {lim.nofile} -f {lim.home_mb * 1024} && cd {shlex.quote(cwd)} && "
                 f"exec timeout -s KILL {timeout_s} bash -c {shlex.quote(command)}")
        env = [f"{key}={value}" for key, value in BOX_ENV.items()]
        return ["setpriv", f"--reuid={BOX_UID}", f"--regid={BOX_UID}", "--clear-groups", "--inh-caps=-all",
                "--no-new-privs", "--", "env", "-i", *env, "bash", "-c", guard]

    def _exec_raw(self, argv: list[str], timeout_s: int, *, stdin: bytes | None = None,
                  as_root: bool = False) -> ExecResult:
        """Run argv in the sandbox, keeping the head and tail of its output."""
        began = time.monotonic()
        try:
            proc = self.sandbox.exec(*argv, timeout=timeout_s + HOST_GRACE_S, text=False)
            if stdin is not None:
                proc.stdin.write(stdin)
                proc.stdin.write_eof()
                proc.stdin.drain()
            out, err = _Capture(OUTPUT_HEAD_BYTES, OUTPUT_TAIL_BYTES), _Capture(OUTPUT_HEAD_BYTES, OUTPUT_TAIL_BYTES)

            def pump(stream: Any, capture: _Capture) -> None:
                for chunk in stream:
                    capture.feed(chunk if isinstance(chunk, bytes) else str(chunk).encode())

            threads = [threading.Thread(target=pump, args=(proc.stdout, out), daemon=True),
                       threading.Thread(target=pump, args=(proc.stderr, err), daemon=True)]
            for t in threads:
                t.start()
            code = proc.wait()
            for t in threads:
                t.join(timeout=10)
        except Exception as error:
            raise BoxError(self._exec_error(error)) from error
        seconds = round(time.monotonic() - began, 2)
        return ExecResult(command=" ".join(argv) if as_root else argv[-1], exit_code=code,
                          stdout=out.text(), stderr=err.text(), seconds=seconds,
                          truncated=bool(out.dropped or err.dropped))

    def exec(self, command: str, timeout_s: int, *, cwd: str | None = None) -> ExecResult:
        self._require_started()
        timeout_s = max(1, min(int(timeout_s), self.limits.max_command_s))
        result = self._exec_raw(self.user_argv(command, timeout_s, cwd or self.workdir), timeout_s)
        # `timeout -s KILL` exits 137; Modal's own backstop reports -1 or 124-ish codes.
        timed_out = result.exit_code in (124, 137, -1) and result.seconds >= timeout_s - 0.5
        return ExecResult(command=command, exit_code=result.exit_code, stdout=result.stdout,
                          stderr=result.stderr, seconds=result.seconds, timed_out=timed_out,
                          truncated=result.truncated)

    def write_file(self, path: str, content: str | bytes) -> None:
        self._require_started()
        data = content.encode("utf-8") if isinstance(content, str) else content
        # The path is passed as $1, never spliced into the script.
        script = 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"'
        argv = self.user_argv(f"sh -c {shlex.quote(script)} sh {shlex.quote(path)}", 60, self.workdir)
        result = self._exec_raw(argv, 60, stdin=data)
        if result.exit_code != 0:
            raise BoxError(f"cannot write {path}: {result.stderr.strip()[-300:]}")

    def read_file(self, path: str, max_bytes: int = 64_000) -> bytes:
        self._require_started()
        argv = self.user_argv(f"head -c {int(max_bytes)} -- {shlex.quote(path)}", 60, self.workdir)
        proc_result = self._read_bytes(argv, 60)
        if proc_result[0] != 0:
            raise BoxError(f"cannot read {path}: {proc_result[2].decode(errors='replace').strip()[-300:]}")
        return proc_result[1][:max_bytes]

    def _read_bytes(self, argv: list[str], timeout_s: int) -> tuple[int, bytes, bytes]:
        try:
            proc = self.sandbox.exec(*argv, timeout=timeout_s + HOST_GRACE_S, text=False)
            out, err = proc.stdout.read(), proc.stderr.read()
            return proc.wait(), out, err
        except Exception as error:
            raise BoxError(self._exec_error(error)) from error

    def _exec_error(self, error: Exception) -> str:
        text = f"{type(error).__name__}: {error}"
        if "NotFound" in type(error).__name__ or "WaitPID" in text or "already shut down" in text:
            # Measured: going over the memory limit kills the whole gVisor sandbox, not one process.
            return (f"the sandbox died during this command (most likely over the {self.limits.memory_mb} MiB "
                    f"memory limit, which kills the whole box on Modal): {text[:300]}")
        return f"modal exec failed: {text[:400]}"

    def set_network(self, enabled: bool) -> None:
        self._require_started()
        if enabled == self.network_enabled:
            return
        try:
            self.sandbox._experimental_set_outbound_network_policy(
                outbound_cidr_allowlist=ONLINE_CIDRS if enabled else [], outbound_domain_allowlist=[])
        except Exception as err:
            raise BoxError(f"modal network policy failed: {type(err).__name__}: {err}") from err
        self.network_enabled = enabled
