"""Mac L2 in a throwaway tart VM (eval/README.md 9.1 C7; the 2026-11-02 method change in results/run-log.md).

Each VM is a fresh clone of one pinned macOS base image, started headless; VM.sh runs one command in the
guest through the Tart Guest Agent (vsock, so it keeps working while the guest's network is off) and records
its exit code and output tail, like l2_boxes.Box. get/put move files through the grader's machine. The clone
is stopped and deleted at the end, so every question and group starts from the same image.

  with VM("q11-control", out_dir, ["q11", "_mac", "_shared", "pins.json"], memory_mb=16384, keep=True) as vm:
      rc, out = vm.sh("sw_vers", "guest version")       # keep=True leaves the clone running for the next phase,
  with VM("q11-control", out_dir, [], name=vm.name) as vm:  # which attaches by name; the last phase deletes it
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_box  # noqa: E402

BASE = "ghcr.io/cirruslabs/macos-tahoe-base@sha256:4aaa751fa7538902d73c767f27a066fc87e83f183069da4e4b5022863abd4c77"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
FIX = "/Users/Shared/eval-fixtures"


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def tart(*args: str, timeout: float = 600, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["tart", *args], input=stdin, capture_output=True, timeout=timeout)


def pressure() -> int:
    """Host kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical."""
    out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


class VM:
    def __init__(self, label: str, out_dir: Path, fixtures: list[str], cpu: int = 8, memory_mb: int = 16384,
                 nested: bool = False, base: str = BASE, name: str | None = None, keep: bool = False):
        self.label, self.out_dir, self.fixtures = label, out_dir, fixtures
        self.cpu, self.memory_mb, self.nested, self.base = cpu, memory_mb, nested, base
        self.attached, self.keep = name is not None, keep
        self.name = name or f"p6-l2-{label}-{secrets.token_hex(2)}"
        self.proc: subprocess.Popen | None = None
        self.log: list[dict[str, Any]] = []
        self.host_pressure: list[tuple[str, int]] = []

    def __enter__(self) -> "VM":
        self.started_at = now()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        steps = self.out_dir / "steps.json"
        if self.attached and steps.exists():
            self.log = json.loads(steps.read_text(encoding="utf-8"))
        self.run_log = open(self.out_dir / "tart-run.log", "ab")
        if self.attached:
            self.wait_agent()
            return self
        (self.out_dir / "clone.txt").write_text(self.name + "\n")
        for args in (("clone", self.base, self.name), ("set", self.name, "--cpu", str(self.cpu), "--memory", str(self.memory_mb))):
            r = tart(*args, timeout=1800)
            if r.returncode:
                raise RuntimeError(f"tart {args[0]}: {r.stderr.decode()[-500:]}")
        self.start()
        if self.fixtures:
            self.put("/tmp/fixtures.tgz", calibrate_box.fixtures_tar(self.fixtures))
            self.sh(f"sudo mkdir -p {FIX} && sudo tar -C {FIX} -xzf /tmp/fixtures.tgz && sudo chmod -R a+rX {FIX}", "copy fixtures")
        return self

    def start(self) -> None:
        self.proc = subprocess.Popen(["tart", "run", self.name, "--no-graphics", "--suspendable"] + (["--nested"] if self.nested else []),
                                     stdout=self.run_log, stderr=subprocess.STDOUT, start_new_session=True)
        self.wait_agent()

    def reboot(self) -> None:
        """Shut down from inside the guest (so every write reaches the disk), then start the same clone again."""
        self.sh("sync; sudo shutdown -h now", "shutdown from inside the guest (the agent goes away with it)", timeout=60, quiet=True)
        try:
            self.proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            tart("stop", self.name, "--timeout", "120", timeout=300)
            self.proc.wait(timeout=60)
        self.start()

    def baseline(self, script: Path) -> None:
        """mac_baseline.sh as the image's admin, a clean reboot, and a check that the agent now runs as the new user."""
        self.put("/tmp/mac_baseline.sh", script.read_bytes())
        rc, _ = self.sh("bash /tmp/mac_baseline.sh", "baseline part 1 (new user, image Homebrew aside)")
        if rc:
            raise RuntimeError("baseline part 1 failed")
        self.reboot()
        rc, out = self.sh("whoami; stat -f %Su /dev/console; ls /opt", "baseline: logged-in user after reboot")
        _, sa = self.sh('sleep 20; pgrep -x "Setup Assistant" || echo none', "no first-login Setup Assistant in the session")
        if "none" not in sa:
            raise RuntimeError("Setup Assistant is showing; closing it ends the session")
        if out.split()[:2] != ["evaluser", "evaluser"] or "homebrew" in out.split()[2:]:
            raise RuntimeError(f"baseline check failed: {out!r}")

    def wait_agent(self, limit: float = 600) -> None:
        end = time.time() + limit
        while time.time() < end:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"tart run exited {self.proc.returncode}")
            try:
                if tart("exec", self.name, "true", timeout=20).returncode == 0:
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(5)
        raise RuntimeError("guest agent did not come up")

    def sh(self, cmd: str, what: str = "", timeout: int = 1200, quiet: bool = False) -> tuple[int, str]:
        """Run cmd with bash in the guest, as the user the guest agent runs as (after baseline(): evaluser, in its
        GUI login session, as a command typed in Terminal would be)."""
        inner = f"bash -c {shlex.quote(cmd)} 2>&1"
        full = f"perl -e 'alarm shift; exec @ARGV' {timeout} /bin/bash -c {shlex.quote(inner)}"
        self.host_pressure.append((now(), pressure()))
        try:
            r = tart("exec", self.name, "/bin/bash", "-c", full, timeout=timeout + 60)
            rc, out = r.returncode, (r.stdout + r.stderr).decode(errors="replace")
        except subprocess.TimeoutExpired:
            rc, out = 124, "host timeout"
        self.log.append({"what": what, "cmd": cmd, "exit": rc, "at": now(), "tail": out[-1500:]})
        print(f"[{self.label}] {what or cmd[:60]}: exit {rc}" + ("" if quiet else "\n    " + out[-300:].replace("\n", "\n    ")), flush=True)
        return rc, out

    def get(self, path: str) -> bytes:
        r = tart("exec", self.name, "/bin/sh", "-c", f"sudo base64 -i {shlex.quote(path)}", timeout=600)
        return base64.b64decode(r.stdout)

    def put(self, path: str, content: bytes) -> None:
        r = tart("exec", "-i", self.name, "/bin/sh", "-c", f"base64 -d -o {shlex.quote(path)}", stdin=base64.b64encode(content), timeout=600)
        if r.returncode:
            raise RuntimeError(f"put {path}: {r.stderr.decode()[-300:]}")

    def __exit__(self, *exc: Any) -> None:
        if self.keep:  # also on an error: the clone stays for a look or a later phase (delete it by hand)
            self.run_log.close()
            (self.out_dir / "steps.json").write_text(json.dumps(self.log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return
        guest = {}
        try:
            _, v = self.sh("sw_vers -productVersion; sw_vers -buildVersion", "guest version", quiet=True)
            guest["macos"] = v.split()
        except Exception:
            pass
        tart("stop", self.name, timeout=300)
        if self.proc is not None:
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.run_log.close()
        deleted = tart("delete", self.name, timeout=600).returncode == 0
        record = {"label": self.label, "base": self.base, "method": "agent (2026-11-02 method change)", "clone": self.name, "cpu": self.cpu, "memory_mib": self.memory_mb,
                  "nested_flag": self.nested, "guest": guest, "host": "Apple M5, 24 GiB, macOS 27.2",
                  "started_at": self.started_at, "ended_at": now(), "clone_deleted": deleted,
                  "host_pressure_levels": sorted({p for _, p in self.host_pressure}),
                  "host_pressure_critical_steps": sum(1 for _, p in self.host_pressure if p >= 4),
                  "error": repr(exc[1])[:500] if exc[1] else None}
        (self.out_dir / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self.out_dir / "steps.json").write_text(json.dumps(self.log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
