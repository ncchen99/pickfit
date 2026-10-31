"""ModalBox with a fake Modal sandbox: arguments, user switch, output capture, network policy."""

from __future__ import annotations

import ipaddress
import itertools
from typing import Any

import pytest

from pickfit.verify import modal_box as mb
from pickfit.verify.box import BOX_ENV, BoxError, BoxLimits
from pickfit.verify.limits import run_limits_test
from pickfit.verify.modal_box import BLOCKED_NETS, ONLINE_CIDRS, ModalBox, public_cidrs
from verify_fakes import FakeBox


class FakeStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        return iter(self.chunks)

    def read(self) -> bytes:
        return b"".join(self.chunks)


class FakeStdin:
    def __init__(self) -> None:
        self.data = b""
        self.eof = False

    def write(self, data: bytes) -> None:
        self.data += data

    def write_eof(self) -> None:
        self.eof = True

    def drain(self) -> None:
        pass


class FakeProc:
    def __init__(self, code: int, out: list[bytes], err: list[bytes]) -> None:
        self.stdout, self.stderr, self.stdin = FakeStream(out), FakeStream(err), FakeStdin()
        self.code = code

    def wait(self) -> int:
        return self.code


class FakeSandbox:
    object_id = "sb-test"

    def __init__(self, replies: list[Any] | None = None) -> None:
        self.replies = replies or []
        self.calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.procs: list[FakeProc] = []
        self.policies: list[dict[str, Any]] = []
        self.terminated = False

    def exec(self, *argv: str, **kw: Any) -> FakeProc:
        self.calls.append((argv, kw))
        reply = self.replies.pop(0) if self.replies else (0, [b"ok"], [])
        if isinstance(reply, Exception):
            raise reply
        proc = FakeProc(*reply)
        self.procs.append(proc)
        return proc

    def _experimental_set_outbound_network_policy(self, **kw: Any) -> None:
        self.policies.append(kw)

    def terminate(self) -> None:
        self.terminated = True


def started(sandbox: FakeSandbox, limits: BoxLimits = BoxLimits()) -> ModalBox:
    box = ModalBox(limits=limits, client=object(), log=lambda s: None)
    box.sandbox, box.started = sandbox, True
    return box


def test_public_cidrs_leave_out_metadata_and_private_ranges():
    nets = [ipaddress.ip_network(c) for c in ONLINE_CIDRS]

    def reachable(address: str) -> bool:
        return any(ipaddress.ip_address(address) in n for n in nets)

    for blocked in ("169.254.169.254", "10.1.2.3", "172.16.5.4", "192.168.0.1", "100.64.0.1"):
        assert not reachable(blocked), blocked
    for public in ("8.8.8.8", "151.101.0.223", "140.82.112.3", "104.16.0.1"):
        assert reachable(public), public
    assert public_cidrs(("0.0.0.0/1",)) == ["128.0.0.0/1"]
    assert all(ipaddress.ip_network(b).subnet_of(ipaddress.ip_network("0.0.0.0/0")) for b in BLOCKED_NETS)


def test_create_kwargs_use_gvisor_hard_limits_and_an_allowlist():
    kw = ModalBox(limits=BoxLimits(cpus=2.0, memory_mb=2048, lifetime_s=900), tags={"run": "x"}).create_kwargs()
    assert kw["runtime"] == "gvisor" and kw["timeout"] == 900
    assert kw["cpu"] == (1.0, 1.0) and kw["memory"] == (2048, 2048)  # request == limit
    assert kw["outbound_cidr_allowlist"] == ONLINE_CIDRS and kw["outbound_domain_allowlist"] == []
    assert kw["tags"] == {"pickfit": "verify", "run": "x"}
    assert "secrets" not in kw and "env" not in kw
    # 1 core and 2 GiB at sandbox prices: about $0.19 an hour alive.
    assert ModalBox().usd_per_second() == pytest.approx(0.00003942 + 2 * 0.00000667)


def test_gpu_box_asks_modal_for_the_card_and_prices_it():
    assert "gpu" not in ModalBox().create_kwargs()
    box = ModalBox(gpu="T4")
    assert box.create_kwargs()["gpu"] == "T4" and box.create_kwargs()["runtime"] == "gvisor"
    assert box.usd_per_second() == pytest.approx(ModalBox().usd_per_second() + 0.59 / 3600)
    with pytest.raises(ValueError, match="gpu must be one of"):
        ModalBox(gpu="H100")


def test_commands_run_as_the_box_user_with_limits_and_no_host_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_API_KEY", "LLM_123_never")
    box = started(FakeSandbox([(0, [b"hel", b"lo\n"], [b"warn\n"])]), BoxLimits(pids=256, nofile=1024, home_mb=1536))
    result = box.exec("echo hello", 999)
    argv, kw = box.sandbox.calls[0]
    assert argv[:7] == ("/usr/bin/setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "--inh-caps=-all",
                        "--no-new-privs", "--")
    # Programs by absolute path: the box user's ~/.local/bin comes first on its own PATH.
    assert argv[7:9] == ("/usr/bin/env", "-i") and set(a.split("=", 1)[0] for a in argv[9:9 + len(BOX_ENV)]) == \
        set(BOX_ENV)
    assert argv[-3:-1] == ("/usr/bin/bash", "-c")
    assert "LLM_123" not in " ".join(argv)
    guard = argv[-1]
    assert guard.startswith("ulimit -u 256 -n 1024 -f 1572864 && cd /home/sbx/work && "
                            "exec /usr/bin/timeout -s KILL 600 /usr/bin/bash -c ")
    assert kw == {"timeout": 615, "text": False}  # the host backstop sits past the in-box kill
    assert (result.exit_code, result.stdout, result.stderr, result.command) == (0, "hello\n", "warn\n", "echo hello")


def test_kill_at_timeout_and_a_dead_sandbox(monkeypatch: pytest.MonkeyPatch):
    clock = itertools.count(0.0, 5.0)
    monkeypatch.setattr(mb.time, "monotonic", lambda: next(clock))
    box = started(FakeSandbox([(137, [], [])]))
    assert box.exec("sleep 30", 5).timed_out

    class NotFoundError(Exception):
        pass

    box = started(FakeSandbox([NotFoundError("Sandbox has already shut down")]))
    with pytest.raises(BoxError, match="sandbox died during this command .* memory limit"):
        box.exec("python3 big.py", 60)


def test_files_go_through_stdin_with_the_path_as_an_argument():
    box = started(FakeSandbox([(0, [], []), (0, [b"hello\n"], [])]))
    box.write_file("dir/a b.txt", "data")
    argv, _ = box.sandbox.calls[0]
    assert box.sandbox.procs[0].stdin.data == b"data" and box.sandbox.procs[0].stdin.eof
    assert 'cat > "$1"' in argv[-1] and "dir/a b.txt" in argv[-1]  # the path is $1, quoted
    assert box.read_file("dir/a b.txt") == b"hello\n"


def test_network_cut_and_restore_replace_the_allowlist():
    box = started(FakeSandbox())
    box.set_network(False)
    box.set_network(False)  # no-op
    box.set_network(True)
    assert box.sandbox.policies == [
        {"outbound_cidr_allowlist": [], "outbound_domain_allowlist": []},
        {"outbound_cidr_allowlist": ONLINE_CIDRS, "outbound_domain_allowlist": []}]
    box.close()
    assert box.sandbox.terminated and not box.started
    with pytest.raises(BoxError, match="not started"):
        box.exec("true", 5)


def test_start_creates_the_sandbox_from_the_published_image(monkeypatch: pytest.MonkeyPatch):
    import modal

    created: dict[str, Any] = {}
    sandbox = FakeSandbox()

    def create(*args: str, **kw: Any) -> FakeSandbox:
        created.update(args=args, **kw)
        return sandbox

    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: f"app:{name}")
    monkeypatch.setattr(modal.Sandbox, "create", create)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    monkeypatch.setattr(mb, "sandbox_image_tag", lambda: "pickfit-sbx:abc")
    box = ModalBox(limits=BoxLimits(lifetime_s=300), client="client", log=lambda s: None)
    box.start()
    assert created["args"] == ("sleep", "300") and created["app"] == "app:pickfit-verify"
    assert created["image"] == "image:pickfit-sbx:abc" and created["runtime"] == "gvisor"
    assert box.image == "pickfit-sbx:abc" and box.sandbox_id == "sb-test"
    mkdir, chown = (call[0] for call in sandbox.calls[:2])
    assert mkdir[:2] == ("/usr/bin/mkdir", "-p") and chown[:3] == ("/usr/bin/chown", "-R", "1000:1000")


def test_limits_test_reports_each_probe():
    script = {
        "id -u": (0, "1000\nCapEff:\t0000000000000000\n", ""),
        "env |": (0, "HOME PATH GPG_KEY ", ""),
        "pypi.org": (0, "200", ""),
        "169.254.169.254": (7, "", "refused"),
        "10.0.0.1": (28, "", "timed out"),
        "127.0.0.1:8765": (0, "200", ""),
        "sleep 30": (137, "", ""),
        "head -c 1700M": (153, "", "File size limit exceeded"),
        "os.fork": (0, "blocked after 254 [Errno 11]", ""),
        "bytearray": (137, "", ""),
        "https://1.1.1.1/": (0, "301", ""),
        "/proc/net/route": (0, "hosts: 172.20.0.1 172.21.0.1\n", ""),
        "AF_VSOCK": (0, "closed 2 52 OSError 97\n", ""),
        "io_uring": (0, "io_uring refused errno 1\n", ""),
    }

    class Box(FakeBox):
        def exec(self, command, timeout_s, *, cwd=None):
            result = super().exec(command, timeout_s, cwd=cwd)
            if not self.network_enabled and ("pypi.org" in command or "1.1.1.1" in command):
                result.stdout, result.exit_code = "000", 28
            result.timed_out = result.exit_code == 137 and "sleep" in command
            return result

    results = run_limits_test(Box(script), log=lambda s: None)
    # A box with no root channel cannot run the controls those two probes need: undecided is a failure.
    assert [r.name for r in results if not r.ok] == ["no_userns", "vsock_closed"]
    assert [r.name for r in results][-1] == "memory_cap"
    assert len(results) == 22
    assert "no control" in next(r for r in results if r.name == "vsock_closed").detail


def test_a_missing_image_is_published_once_then_used(monkeypatch: pytest.MonkeyPatch):
    import modal

    class NotFoundError(Exception):
        pass

    attempts: list[str] = []
    published: list[str] = []

    def create(*args: str, **kw: Any) -> FakeSandbox:
        attempts.append(kw["image"])
        if len(attempts) == 1:
            raise NotFoundError("Image 'pickfit-sbx:abc' not found")
        return FakeSandbox()

    monkeypatch.setattr(modal.App, "lookup", lambda name, **kw: "app")
    monkeypatch.setattr(modal.Sandbox, "create", create)
    monkeypatch.setattr(modal.Image, "from_name", lambda name: f"image:{name}")
    monkeypatch.setattr(mb, "sandbox_image_tag", lambda: "pickfit-sbx:abc")
    monkeypatch.setattr(mb, "publish_image", lambda client, app, log, **kw: published.append("x") or "pickfit-sbx:abc")
    ModalBox(client="client", log=lambda s: None).start()
    assert attempts == ["image:pickfit-sbx:abc"] * 2 and published == ["x"]


def test_a_command_that_never_returns_is_given_up_on(monkeypatch: pytest.MonkeyPatch):
    import threading

    class HangingProc(FakeProc):
        def wait(self) -> int:
            threading.Event().wait()  # like a daemon child holding stdout open
            return 0

    sandbox = FakeSandbox()
    sandbox.exec = lambda *argv, **kw: HangingProc(0, [b"partial"], [])  # type: ignore[method-assign]
    monkeypatch.setattr(mb, "HOST_GRACE_S", 0)
    monkeypatch.setattr(mb, "READ_TIMEOUT_S", 1)
    box = started(sandbox)
    result = box.exec("corvus serve", 1)
    assert result.timed_out and result.exit_code == 124 and result.stdout == "partial"
    assert "start servers and daemons with run_background" in result.stderr
    with pytest.raises(BoxError, match="cannot read fifo"):
        box.read_file("fifo")
