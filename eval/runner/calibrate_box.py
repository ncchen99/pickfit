"""Run one calibration script in a fresh Modal sandbox of an L2 image, and bring its outputs back.

  calibrate_box.py --label q01 --script eval/fixtures/q01/calibrate.sh --fixtures q01 _shared \\
                   [--variant dev] [--cpu 2] [--memory 16384] [--timeout 3600] --confirm-spend

The sandbox starts from the published image of --variant (eval/results/l2-images.json), with the
network open. The listed fixture folders are copied to /opt/eval/fixtures/<name>; the script runs as
root with bash and F=/opt/eval/fixtures, SHARED=/opt/eval/fixtures/_shared, OUT=/out. Everything the
script leaves in /out (files under 5 MB) is copied to eval/results/calibration/<label>/, together with
run.json: image, sandbox id, cpu, memory, start and end, exit code, and the console log. The sandbox
is always terminated. Downloads inside the script must use eval/fixtures/PINS.md (version + sha256).

Run with: uv run python eval/runner/calibrate_box.py ...
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "eval" / "fixtures"
RESULTS = ROOT / "eval" / "results" / "calibration"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
MAX_FILE = 5 * 1024 * 1024
SKIP = {"__pycache__", "state", ".DS_Store"}


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def fixtures_tar(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in names:
            tar.add(FIXTURES / name, arcname=name,
                    filter=lambda ti: None if Path(ti.name).name in SKIP else ti)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eval/runner/calibrate_box.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True)
    p.add_argument("--script", required=True, type=Path)
    p.add_argument("--fixtures", nargs="+", required=True)
    p.add_argument("--variant", default="dev")
    p.add_argument("--cpu", type=float, default=2.0, help="Modal cpu; measured: 4.0 gives nproc 4 and a CFS quota of 4 CPUs")
    p.add_argument("--memory", type=int, default=16384, help="MiB (request = limit)")
    p.add_argument("--no-memory-limit", action="store_true", help="--memory is only the request; no hard limit")
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--confirm-spend", action="store_true")
    p.add_argument("--results", type=Path, default=RESULTS, help="parent of the output folder (L2 uses eval/results/l2)")
    a = p.parse_args(argv)
    if not a.confirm_spend:
        print("refused: this starts a Modal sandbox; pass --confirm-spend")
        return 2
    import modal

    sys.path.insert(0, str(ROOT / "eval" / "runner"))
    import l2_image

    image = l2_image.read_record()["images"][a.variant]["name"]
    client = l2_image.modal_client()
    app = modal.App.lookup(l2_image.APP_NAME, create_if_missing=True, client=client)
    out_dir = a.results.resolve() / a.label
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"label": a.label, "script": str(a.script), "fixtures": a.fixtures, "variant": a.variant, "image": image,
              "cpu": a.cpu, "memory_mib": a.memory, "memory_limit": not a.no_memory_limit, "started_at": now()}
    sb = modal.Sandbox.create("sleep", str(a.timeout + 300), app=app, client=client,
                              image=modal.Image.from_name(image), timeout=a.timeout + 600,
                              cpu=(a.cpu, a.cpu), memory=a.memory if a.no_memory_limit else (a.memory, a.memory))
    record["sandbox_id"] = getattr(sb, "object_id", None)
    log_lines: list[str] = []
    try:
        l2_image.put(sb, "/tmp/fixtures.tgz", fixtures_tar(a.fixtures))
        l2_image.put(sb, "/tmp/cal.sh", a.script.read_bytes())
        prep = sb.exec("/bin/sh", "-c", "mkdir -p /opt/eval/fixtures /out && tar -C /opt/eval/fixtures -xzf /tmp/fixtures.tgz")
        prep.wait()
        t0 = time.monotonic()
        proc = sb.exec("/bin/bash", "-c", "F=/opt/eval/fixtures SHARED=/opt/eval/fixtures/_shared OUT=/out "
                       f"timeout {a.timeout} bash /tmp/cal.sh 2>&1")
        try:
            for line in proc.stdout:
                print(line, end="", flush=True)
                log_lines.append(line)
            proc.wait()
            record.update(exit_code=proc.returncode, seconds=round(time.monotonic() - t0, 1))
        except (modal.exception.NotFoundError, modal.exception.ConflictError) as err:
            # The sandbox itself is gone: passing the hard memory limit ends the whole sandbox
            # with returncode 137 (q03 calibration 3b), not just the process.
            record.update(exit_code=None, sandbox_lost=repr(err)[:300], seconds=round(time.monotonic() - t0, 1))
            print(f"\nsandbox lost: {err}")
            return finish(record, out_dir, log_lines, sb)
        listing = sb.exec("/bin/sh", "-c", f"cd /out && find . -type f -size -{MAX_FILE // 1024}k | sort")
        listing.wait()
        names = [n for n in listing.stdout.read().split("\n") if n.strip()]
        if names:
            pack = sb.exec("/bin/sh", "-c", "cd /out && tar czf - " + " ".join(f"'{n}'" for n in names) + " | base64 -w0")
            pack.wait()
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(pack.stdout.read())), mode="r:gz") as tar:
                tar.extractall(out_dir, filter="data")
        record["files"] = names
    except BaseException:
        finish(record, out_dir, log_lines, sb)
        raise
    return finish(record, out_dir, log_lines, sb)


def finish(record, out_dir, log_lines, sb) -> int:
    try:
        record["sandbox_returncode"] = sb.poll()  # None while it still runs; 137 after an OOM kill
    except Exception:
        pass
    try:
        sb.terminate()
    except Exception:  # already gone
        pass
    record["ended_at"] = now()
    (out_dir / "console.log").write_text("".join(log_lines), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{record['label']}: exit {record.get('exit_code')} in {record.get('seconds')} s -> {out_dir.relative_to(ROOT)}")
    return 0 if record.get("exit_code") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
