"""ModalBox: LinuxBox (linux_box.py) on a Modal Sandbox, gVisor or a VM (P3.6).

ModalMachine is the provider half (machine.Machine): it creates the sandbox, carries root's commands, sets the
outbound allowlist and terminates it. What happens inside the sandbox is LinuxBox's, and is documented there.

- Runtime gVisor, or "vm" (a microVM with its own kernel). Memory as request = limit; CPU with the box's limit
  (1 physical core is 2 vCPU under gVisor; a VM gives 1 vCPU per requested core) and a lower request
  (cpu_request(): Modal bills max(request, use), and the agent spends half its time waiting for the model), except a
  build box, whose request is its limit. A lifetime timeout.
- Each sandbox has a row in the ledger's boxes table (meter.BoxMeter), opened at create and closed at terminate.
- Network: created with an allowlist of public IPv4 ranges (machine.ONLINE_CIDRS), so it can be tightened
  later. set_egress(False) replaces it with an empty allowlist (`_experimental_set_outbound_network_policy`,
  Alpha). A running sandbox cannot be switched to Modal's blocked mode, and Modal's resolver 172.21.0.1 still
  answers with an empty allowlist (both runtimes), which is why LinuxBox closes DNS itself.
- Image: built once from sandbox.Dockerfile, plus linux_box.image_recipe()'s packages and commands, and
  published as `pickfit-sbx:<Dockerfile hash>`; sandboxes start from that name, and only a
  missing name triggers the build. (`Image.from_name(...).hydrate()` is not
  supported by the client, so the name is resolved by Sandbox.create.)
- gpu="T4" (or L4, A10) asks Modal for an NVIDIA card. Modal gives one only under gVisor (measured 2026-11-02:
  runtime="vm" with a GPU is refused, "GPUs are not supported with the VM runtime").

Credentials come from MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in .env and go to
an explicit modal.Client; nothing is put into the process environment, and the
sandbox gets no secrets.

Every name this module had before LinuxBox and Machine were split out of it is still importable from here.
"""

from __future__ import annotations

import hashlib  # noqa: F401
import ipaddress  # noqa: F401
import os
import shlex  # noqa: F401
import threading  # noqa: F401
import time
from collections.abc import Callable
from typing import Any

from pickfit.env import require_env
from pickfit.verify.audio import AUDIO_PACKAGES, PULSE_SERVER, pulse_script  # noqa: F401
from pickfit.verify.box import (  # noqa: F401
    BOX_ENV,
    BOX_HOME,
    BOX_WORKDIR,
    GO_VERSION,
    HOST_GRACE_S,
    OUTPUT_HEAD_BYTES,
    OUTPUT_TAIL_BYTES,
    RUST_VERSION,
    SANDBOX_DOCKERFILE,
    Box,
    BoxError,
    BoxLimits,
    ExecResult,
    _Capture,
    sandbox_image_tag,
)
from pickfit.verify.gui import (  # noqa: F401
    DISPLAY,
    DISPLAY_UID,
    EVIDENCE_DIR,
    GUI_PACKAGES,
    HARNESS_PATH,
    PYTHON,
    xvfb_script,
)
from pickfit.verify.linux_box import (  # noqa: F401
    _MAP_PY,
    BOX_UID,
    BWRAP_SHIM,
    BWRAP_SHIM_SOURCE,
    DISPLAY_MAPS,
    DNS_BLOCK,
    DNS_TABLE,
    DNS_UNBLOCK,
    FLATPAK_PACKAGES,
    GO_SHA256,
    GO_URL,
    GPU_NAME,
    INSTALL_BWRAP_SHIM,
    NET_UID,
    NETNS_MAPS,
    NO_VSOCK,
    NO_VSOCK_SOURCE,
    READ_TIMEOUT_S,
    RUST_SHA256,
    RUST_URL,
    SAME_NETNS_PY,
    SYSTEM_BUS,
    SYSTEM_BUS_CONF,
    SYSTEM_BUS_CONF_SOURCE,
    SYSTEM_BUS_LOG,
    SYSTEM_BUS_SOCKET,
    TAP,
    TAP_CONFIG,
    TOOLCHAIN_INSTALL,
    TOOLCHAIN_PACKAGES,
    UPLINK,
    UPLINK_LOG,
    UPLINK_MTU,
    VGL_DEB,
    VGL_HOME,
    VGL_INSTALL,
    VGL_OVERRIDE,
    VGL_SETUP,
    VGL_SHA256,
    VM_HARDEN,
    VM_PACKAGES,
    ImageRecipe,
    LinuxBox,
    _drop_to,
    display_netns_script,
    gl_env,
    holder_script,
    image_recipe,
    netns_script,
    uplink_script,
)
from pickfit.verify.machine import BLOCKED_NETS, ONLINE_CIDRS, RUNTIMES, Machine, Process, public_cidrs  # noqa: F401
from pickfit.verify.meter import BoxMeter, identity

APP_NAME = "pickfit-verify"
# Sandbox prices (3x the function rates), docs/research/notes/sandbox-compare.md, read 2026-10-28.
# Billed on max(request, use). These rates times the limit are the most a second alive can cost; the ledger records
# that (an upper bound) and scripts/box_reconcile.py compares it with Modal's own report.
CORE_USD_PER_S = 0.00003942
GIB_USD_PER_S = 0.00000667
RATE_SOURCE = ("Modal sandbox rates (3x the function rates) read 2026-10-28, docs/research/notes/sandbox-compare.md; "
               "CPU and memory at their limits, billed on max(request, use): an upper bound")
# GPU sandboxes run only under gVisor, can be preempted, and bill GPUs at the
# plain rate (same note, read 2026-10-28). Only the small cards: a local AI
# tool's smoke test runs the smallest model it supports.
GPU_USD_PER_S = {"T4": 0.59 / 3600, "L4": 0.80 / 3600, "A10": 1.10 / 3600}
# CPU request (physical cores) of a box that is not a build box: the agent waits for the model about half of its
# time (54% in the 11/19 audit), and Modal bills max(request, use), so a low request makes that wait cheap. The limit
# stays the box's own: an install that needs the CPU still gets up to its limit when the host has it to give. A build
# box (toolchain) keeps request = limit, so a compile is never short of the cores it was sized for.
CPU_REQUEST_ENV = "PICKFIT_MODAL_CPU_REQUEST"
CPU_REQUEST_CORES = 0.5
MIN_CPU_REQUEST_CORES = 0.125  # Modal's smallest request


def cpu_request(cores: float, *, toolchain: bool = False) -> float:
    """The CPU request (cores) of a box with `cores` as its limit: CPU_REQUEST_CORES (or CPU_REQUEST_ENV), never
    above the limit; a build box's request is its limit."""
    if toolchain:
        return cores
    given = os.environ.get(CPU_REQUEST_ENV, "").strip()
    try:
        wanted = float(given) if given else CPU_REQUEST_CORES
    except ValueError:
        wanted = CPU_REQUEST_CORES
    return min(cores, max(MIN_CPU_REQUEST_CORES, wanted))


def image_layers(runtime: str = "gvisor", display: bool = False, audio: bool = False,
                 toolchain: bool = False, services: bool = False) -> tuple[str, tuple[str, ...]]:
    """(published image name, apt packages added on top of sandbox.Dockerfile) for a kind of box.

    The plain box keeps `pickfit-sbx:<Dockerfile hash>`; a variant hashes the Dockerfile, its packages and the
    commands that install what is not a package (VirtualGL, the build box's Rust and Go).
    """
    recipe = image_recipe(runtime, display, audio, toolchain, services)
    return recipe.tag(sandbox_image_tag()), recipe.packages


def modal_client() -> Any:
    import modal

    return modal.Client.from_credentials(require_env("MODAL_TOKEN_ID"), require_env("MODAL_TOKEN_SECRET"))


def publish_image(client: Any, app: Any, *, log: Callable[[str], None] = print, runtime: str = "gvisor",
                  display: bool = False, audio: bool = False, toolchain: bool = False,
                  services: bool = False) -> str:
    """Build the sandbox image from sandbox.Dockerfile (plus the variant's packages) and publish it.

    Modal caches the build, so an unchanged Dockerfile takes a few seconds.
    """
    import modal

    recipe = image_recipe(runtime, display, audio, toolchain, services)
    name = image_layers(runtime, display, audio, toolchain, services)[0]
    began = time.monotonic()
    image = modal.Image.from_dockerfile(SANDBOX_DOCKERFILE, context_dir=SANDBOX_DOCKERFILE.parent,
                                        ignore=lambda path: True)
    if recipe.packages:
        image = image.apt_install(*recipe.packages)
    for command in recipe.commands:  # VirtualGL for a display box, then Rust and Go for a build box
        image = image.run_commands(command)
    image.build(app)
    image.publish(name, client=client)
    log(f"Modal image {name} built and published in {time.monotonic() - began:.0f}s")
    return name


def ensure_published_image(log: Callable[[str], None] = print, *, runtime: str = "gvisor",
                           display: bool = False, audio: bool = False, toolchain: bool = False,
                           services: bool = False) -> str:
    """Publish the image for the current Dockerfile before parallel boxes start; returns its name."""
    import modal

    client = modal_client()
    app = modal.App.lookup(APP_NAME, create_if_missing=True, client=client)
    return publish_image(client, app, log=log, runtime=runtime, display=display, audio=audio, toolchain=toolchain,
                         services=services)


def _missing_image(err: Exception) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return "notfound" in text.replace(" ", "") or "not found" in text


class ModalMachine(Machine):
    """A Modal Sandbox as a Machine: started from a published image, behind Modal's outbound allowlist.

    `image_name` gives the published name to start from and `publish` builds it when Modal does not have it;
    both are asked when the machine starts, so a box and the web box each bring their own image.
    """

    provider = "modal"

    def __init__(self, *, cores: float, memory_mb: int, lifetime_s: int, image_name: Callable[[], str],
                 publish: Callable[[Any, Any], Any], runtime: str = "gvisor", gpu: str | None = None,
                 tags: dict[str, str] | None = None, app_name: str = APP_NAME, client: Any = None,
                 log: Callable[[str], None] = print, cpu_request: float | None = None) -> None:
        self.cores = cores  # Modal counts physical cores: two vCPU under gVisor, one in a VM
        self.cpu_request = cpu_request  # cores asked for (billed at least); None: the limit, `cores`
        self.memory_mb = memory_mb
        self.lifetime_s = lifetime_s
        self.image_name = image_name
        self.publish = publish
        self.runtime = runtime
        self.gpu = gpu
        self.tags = dict(tags or {})
        self.app_name = app_name
        self.client = client
        self.log = log
        self.sandbox: Any = None
        self._image: str | None = None

    @property
    def image(self) -> str:  # type: ignore[override]
        """The image the sandbox started from; before it starts, the one it would start from now."""
        return self._image or self.image_name()

    @property
    def grace_s(self) -> int:  # type: ignore[override]
        return HOST_GRACE_S  # this module's, read when a command runs

    def create_kwargs(self) -> dict[str, Any]:
        """Sandbox.create arguments other than app, image and client (separate so tests can check them)."""
        request = self.cores if self.cpu_request is None else min(self.cpu_request, self.cores)
        kwargs = {"runtime": self.runtime, "timeout": self.lifetime_s, "cpu": (request, self.cores),
                  "memory": (self.memory_mb, self.memory_mb), "workdir": "/",
                  "outbound_cidr_allowlist": ONLINE_CIDRS, "outbound_domain_allowlist": [],
                  "tags": self.tags}
        if self.gpu:
            kwargs["gpu"] = self.gpu
        return kwargs

    def start(self) -> None:
        import modal

        self.client = self.client or modal_client()
        app = modal.App.lookup(self.app_name, create_if_missing=True, client=self.client)
        self._image = self.image_name()

        def create() -> Any:
            return modal.Sandbox.create("sleep", str(self.lifetime_s), app=app, client=self.client,
                                        image=modal.Image.from_name(self._image), **self.create_kwargs())

        try:
            try:
                self.sandbox = create()
            except Exception as err:
                if not _missing_image(err):
                    raise
                self.publish(self.client, app)  # first machine after the image changed
                self.sandbox = create()
        except Exception as err:
            raise BoxError(f"Modal sandbox create failed: {type(err).__name__}: {err}") from err
        self.machine_id = getattr(self.sandbox, "object_id", None)
        run_id, role = identity(self.tags)
        gpu = f" + {self.gpu} at Modal's GPU rate" if self.gpu else ""
        self.meter = BoxMeter("modal", lane=self.lane, purpose=self.purpose or role or "box", run_id=run_id,
                              vcpu=self.cores * (2 if self.runtime == "gvisor" else 1),
                              memory_gb=round(self.memory_mb / 1024, 3), usd_per_hour=self.usd_per_second() * 3600,
                              rate_source=RATE_SOURCE + gpu, lifetime_s=self.lifetime_s, log=self.log)
        self.meter.start(self.machine_id)

    def spawn(self, argv: list[str], timeout_s: int, *, workdir: str | None = None) -> Any:
        kwargs: dict[str, Any] = {"timeout": timeout_s, "text": False}
        if workdir is not None:
            kwargs["workdir"] = workdir
        return self.sandbox.exec(*argv, **kwargs)

    def set_egress(self, enabled: bool) -> None:
        try:
            self.sandbox._experimental_set_outbound_network_policy(
                outbound_cidr_allowlist=ONLINE_CIDRS if enabled else [], outbound_domain_allowlist=[])
        except Exception as err:
            raise BoxError(f"modal network policy failed: {type(err).__name__}: {err}") from err

    def close(self) -> None:
        if self.sandbox is None:
            return
        try:
            self.sandbox.terminate()
        except Exception as err:  # already gone; the lifetime timeout reaps it anyway
            self.log(f"modal terminate: {type(err).__name__}: {err}")
        if self.meter is not None:
            self.meter.end()

    def usd_per_second(self) -> float:
        gpu = GPU_USD_PER_S[self.gpu] if self.gpu else 0.0
        return self.cores * CORE_USD_PER_S + self.memory_mb / 1024 * GIB_USD_PER_S + gpu

    def explain(self, error: Exception) -> str:
        text = f"{type(error).__name__}: {error}"
        if "NotFound" in type(error).__name__ or "WaitPID" in text or "already shut down" in text:
            # Measured: going over the memory limit kills the whole gVisor sandbox, not one process.
            return (f"the sandbox died during this command (most likely over the {self.memory_mb} MiB "
                    f"memory limit, which kills the whole box on Modal): {text[:300]}")
        return f"modal exec failed: {text[:400]}"


class ModalBox(LinuxBox):
    """A Modal Sandbox (gVisor, or a VM) driven like a DockerBox: LinuxBox on a ModalMachine."""

    runner = "modal-gvisor"
    image = sandbox_image_tag()
    build_cpus = 8.0  # box.sized_for_build: Modal bills by the core-second, so a compile on twice the cores costs the same

    def __init__(self, *, limits: BoxLimits = BoxLimits(), tags: dict[str, str] | None = None,
                 app_name: str = APP_NAME, client: Any = None, gpu: str | None = None,
                 runtime: str = "gvisor", display: bool = False, audio: bool = False, toolchain: bool = False,
                 services: bool = False, log: Callable[[str], None] = print) -> None:
        if gpu is not None and gpu not in GPU_USD_PER_S:
            raise ValueError(f"gpu must be one of {sorted(GPU_USD_PER_S)}, got {gpu!r}")
        if runtime not in RUNTIMES:
            raise ValueError(f"runtime must be one of {RUNTIMES}, got {runtime!r}")
        if gpu and runtime != "gvisor":
            raise ValueError("Modal GPU sandboxes run only under gVisor")
        # The image and its build are named when they are needed, from what the box is then.
        machine = ModalMachine(
            cores=limits.cpus / 2, memory_mb=limits.memory_mb, lifetime_s=limits.lifetime_s, runtime=runtime,
            gpu=gpu, tags={"pickfit": "verify", **(tags or {})}, app_name=app_name, client=client,
            log=lambda line: self.log(line),
            image_name=lambda: image_layers(self.runtime, self.display is not None, self.audio, self.toolchain,
                                            self.services)[0],
            publish=lambda client, app: publish_image(client, app, log=self.log, runtime=self.runtime,
                                                      display=self.display is not None, audio=self.audio,
                                                      toolchain=self.toolchain, services=self.services))
        super().__init__(machine, limits=limits, display=display, audio=audio, toolchain=toolchain,
                         services=services, log=log)

    # -- what was the box's own before the split, now the machine's

    @property
    def sandbox(self) -> Any:
        return self.machine.sandbox

    @sandbox.setter
    def sandbox(self, value: Any) -> None:
        self.machine.sandbox = value

    @property
    def client(self) -> Any:
        return self.machine.client

    @client.setter
    def client(self, value: Any) -> None:
        self.machine.client = value

    @property
    def sandbox_id(self) -> str | None:
        return self.machine.machine_id

    @property
    def tags(self) -> dict[str, str]:
        return self.machine.tags

    @property
    def app_name(self) -> str:
        return self.machine.app_name

    @property
    def read_timeout_s(self) -> int:  # type: ignore[override]
        return READ_TIMEOUT_S  # this module's, read when a file is

    def _size(self) -> None:
        """The machine's size follows the box's limits, read when they are used."""
        lim = self.limits
        cores = lim.cpus / 2  # Modal counts physical cores; one core is two vCPU
        self.machine.cores, self.machine.memory_mb, self.machine.lifetime_s = cores, lim.memory_mb, lim.lifetime_s
        self.machine.cpu_request = cpu_request(cores, toolchain=self.toolchain)

    def create_kwargs(self) -> dict[str, Any]:
        """Sandbox.create arguments other than app, image and client (separate so tests can check them)."""
        self._size()
        return self.machine.create_kwargs()

    def start(self) -> None:
        if not self.started:
            self._size()
        super().start()

    def usd_per_second(self) -> float:
        self._size()
        return self.machine.usd_per_second()
