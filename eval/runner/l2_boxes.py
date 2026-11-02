"""Several L2 sandboxes in one flow (eval/README.md 9.1 C7; q04 needs developers A, B and C apart).

Each Box is a fresh Modal sandbox of an L2 image (eval/results/l2-images.json) with the named fixture
folders at /opt/eval/fixtures. Box.sh runs one command with bash and records its exit code and output
tail in the flow's log; get/put move files between boxes through the grader's machine (the stand-in
for "copied between sandboxes" in the fixture READMEs). Everything is terminated at the end.

  with Flow("q04-control", out_dir, ["q04", "_shared"]) as flow:
      a = flow.box("A"); rc, out = a.sh("git --version", "check git")
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_box  # noqa: E402
import l2_image  # noqa: E402

TAIPEI = dt.timezone(dt.timedelta(hours=8))
ENV = "F=/opt/eval/fixtures SHARED=/opt/eval/fixtures/_shared"


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


class Box:
    def __init__(self, flow: "Flow", name: str, sandbox: Any):
        self.flow, self.name, self.sb = flow, name, sandbox

    def sh(self, cmd: str, what: str = "", timeout: int = 1200) -> tuple[int, str]:
        proc = self.sb.exec("/bin/bash", "-c", f"{ENV} timeout {timeout} bash -c {shlex.quote(cmd)} 2>&1")
        out = proc.stdout.read()
        proc.wait()
        rc = proc.returncode
        self.flow.log.append({"box": self.name, "what": what, "cmd": cmd, "exit": rc, "at": now(),
                              "tail": out[-1500:]})
        print(f"[{self.name}] {what or cmd[:60]}: exit {rc}\n    " + out[-400:].replace("\n", "\n    "), flush=True)
        return rc, out

    def get(self, path: str) -> bytes:
        proc = self.sb.exec("/bin/sh", "-c", f"base64 -w0 '{path}'")
        data = proc.stdout.read()
        proc.wait()
        return base64.b64decode(data)

    def put(self, path: str, content: bytes) -> None:
        l2_image.put(self.sb, path, content)


class Flow:
    def __init__(self, label: str, out_dir: Path, fixtures: list[str], variant: str = "dev",
                 cpu: float = 2.0, memory: int = 4096, timeout: int = 3600):
        self.label, self.out_dir, self.fixtures, self.variant = label, out_dir, fixtures, variant
        self.cpu, self.memory, self.timeout = cpu, memory, timeout
        self.log: list[dict[str, Any]] = []
        self.boxes: list[Box] = []

    def __enter__(self) -> "Flow":
        import modal

        self.modal = modal
        self.image = l2_image.read_record()["images"][self.variant]["name"]
        self.client = l2_image.modal_client()
        self.app = modal.App.lookup(l2_image.APP_NAME, create_if_missing=True, client=self.client)
        self.started_at = now()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self

    def box(self, name: str) -> Box:
        sb = self.modal.Sandbox.create("sleep", str(self.timeout + 300), app=self.app, client=self.client,
                                       image=self.modal.Image.from_name(self.image), timeout=self.timeout + 600,
                                       cpu=(self.cpu, self.cpu), memory=(self.memory, self.memory))
        b = Box(self, name, sb)
        b.put("/tmp/fixtures.tgz", calibrate_box.fixtures_tar(self.fixtures))
        b.sh("mkdir -p /opt/eval/fixtures /opt/eval/state /opt/eval/xfer && tar -C /opt/eval/fixtures -xzf /tmp/fixtures.tgz",
             "copy fixtures")
        self.boxes.append(b)
        return b

    def __exit__(self, *exc: Any) -> None:
        for b in self.boxes:
            try:
                b.sb.terminate()
            except Exception:
                pass
        record = {"label": self.label, "variant": self.variant, "image": self.image, "cpu": self.cpu,
                  "memory_mib": self.memory, "started_at": self.started_at, "ended_at": now(),
                  "sandboxes": {b.name: getattr(b.sb, "object_id", None) for b in self.boxes},
                  "error": repr(exc[1])[:500] if exc[1] else None}
        (self.out_dir / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self.out_dir / "steps.json").write_text(json.dumps(self.log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
