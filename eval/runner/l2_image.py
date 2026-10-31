"""The L2 Linux images on Modal (eval/README.md section 5; open decision 6: the image content).

Section 5: Modal Sandbox (x86_64, the same platform as the product's verification),
an image based on ubuntu:24.04, its digest recorded. The proposal for decision 6 adds
only python3, git, ca-certificates, curl and strace (the `dev` variant). Two fixtures
cannot use it, so they get their own variant from the same pinned base:
  base      ubuntu:24.04 unchanged: q03 item 1 requires `command -v python3 java node`
            to print nothing after the answer's install (q03/needs.json);
  base-git  ubuntu:24.04 + git: q10 runs "in the base image (git only)".
The table VARIANTS is the only place the content is written; change it there once
念誠 decides, before any build.

  l2_image.py plan    [--variant V]                          what would be built; no network, no spend
  l2_image.py build   --variant V --base-digest sha256:... --confirm-spend [--apt-snapshot STAMP]
                                                              build and publish on Modal; record it
  l2_image.py inspect --variant V --confirm-spend            start one sandbox from the published image,
                                                              record package versions (and, for dev, the
                                                              egress selftest), terminate it

Nothing here runs without --confirm-spend: the build and the inspection are for after
念誠 confirms decision 6. Records go to eval/results/l2-images.json: the base digest,
the Modal image name and id, the apt snapshot (if any), and what `inspect` saw inside
(dpkg-query -W, python3 / git / strace versions, `command -v` of the runtimes q03 forbids).

Modal credentials come from MODAL_TOKEN_ID / MODAL_TOKEN_SECRET (process environment or
the repo-root .env) into an explicit modal.Client, as pickfit/verify/modal_box.py does.
Run with: uv run python eval/runner/l2_image.py ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
RECORD = EVAL / "results" / "l2-images.json"
SHARED = EVAL / "fixtures" / "_shared"
APP_NAME = "pickfit-eval-l2"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
BASE_TAG = "ubuntu:24.04"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SNAPSHOT_RE = re.compile(r"^\d{8}T\d{6}Z$")

VARIANTS: dict[str, dict[str, Any]] = {
    "dev": {"packages": ["python3", "git", "ca-certificates", "curl", "strace"],
            "for": "every Linux question except q03 and q10 (the decision-6 proposal)"},
    "base": {"packages": [], "for": "q03: no python3, node or java in the image"},
    "base-git": {"packages": ["git"], "for": "q10: the base image with git only"},
}
# What inspect runs inside a fresh sandbox of the image (as root, no network needed).
INSPECT = [
    ("os_release", "cat /etc/os-release"),
    ("arch", "uname -m"),
    ("dpkg", "dpkg-query -W -f='${Package} ${Version}\\n'"),
    ("runtimes", "for c in python3 java node git strace curl; do printf '%s ' \"$c\"; command -v \"$c\" || echo -; done"),
    ("versions", "python3 --version 2>&1; git --version 2>&1; strace -V 2>&1 | head -1; curl --version 2>&1 | head -1"),
]


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def image_name(variant: str, base_digest: str, apt_snapshot: str | None) -> str:
    """A name that changes whenever the content does: variant + hash of (base digest, packages, snapshot)."""
    spec = json.dumps({"base": f"{BASE_TAG}@{base_digest}", "packages": VARIANTS[variant]["packages"],
                       "apt_snapshot": apt_snapshot}, sort_keys=True)
    return f"pickfit-eval-l2-{variant}:{hashlib.sha256(spec.encode()).hexdigest()[:12]}"


def apt_commands(packages: list[str], apt_snapshot: str | None) -> list[str]:
    """One apt layer: update (optionally from an Ubuntu snapshot), install without recommends, clean."""
    if not packages:
        return []
    update = f"apt-get update --snapshot {apt_snapshot}" if apt_snapshot else "apt-get update"
    return [f"{update} && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
            f"{' '.join(packages)} && rm -rf /var/lib/apt/lists/*"]


def plan(variant: str, base_digest: str | None = None, apt_snapshot: str | None = None) -> dict[str, Any]:
    """The image as a Dockerfile-like description; nothing is contacted."""
    base = f"{BASE_TAG}@{base_digest}" if base_digest else f"{BASE_TAG}@<digest to pin>"
    lines = [f"FROM {base}"] + [f"RUN {c}" for c in apt_commands(VARIANTS[variant]["packages"], apt_snapshot)]
    return {"variant": variant, "for": VARIANTS[variant]["for"], "base": base,
            "packages": VARIANTS[variant]["packages"], "apt_snapshot": apt_snapshot,
            "name": image_name(variant, base_digest, apt_snapshot) if base_digest else None,
            "dockerfile": "\n".join(lines),
            "note": "Modal adds no Python (add_python=None); inspect confirms what is in the image."}


def define_image(modal: Any, variant: str, base_digest: str, apt_snapshot: str | None) -> Any:
    """The modal.Image for a variant: the pinned base, no Python added, one apt layer."""
    image = modal.Image.from_registry(f"{BASE_TAG}@{base_digest}", add_python=None)
    commands = apt_commands(VARIANTS[variant]["packages"], apt_snapshot)
    if commands:
        image = image.run_commands(*commands)
    return image


def read_record(path: Path = RECORD) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"images": {}}


def write_record(record: dict[str, Any], path: Path = RECORD) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def modal_client() -> Any:
    import modal

    sys.path.insert(0, str(ROOT))
    from pickfit.env import require_env

    return modal.Client.from_credentials(require_env("MODAL_TOKEN_ID"), require_env("MODAL_TOKEN_SECRET"))


def build(variant: str, base_digest: str, apt_snapshot: str | None, *, modal: Any = None, client: Any = None,
          record_path: Path = RECORD, log: Callable[[str], None] = print) -> dict[str, Any]:
    if not DIGEST_RE.match(base_digest):
        raise SystemExit(f"--base-digest must look like sha256:<64 hex>, got {base_digest!r}")
    if apt_snapshot and not SNAPSHOT_RE.match(apt_snapshot):
        raise SystemExit(f"--apt-snapshot must look like 20261101T000000Z, got {apt_snapshot!r}")
    if modal is None:
        import modal  # noqa: PLW0621 - the real module unless a test passes a fake
    client = client or modal_client()
    app = modal.App.lookup(APP_NAME, create_if_missing=True, client=client)
    name = image_name(variant, base_digest, apt_snapshot)
    image = define_image(modal, variant, base_digest, apt_snapshot)
    image.build(app)
    image.publish(name, client=client)
    entry = {**plan(variant, base_digest, apt_snapshot), "image_id": getattr(image, "object_id", None),
             "built_at": now(), "inspected": None}
    record = read_record(record_path)
    record["images"][variant] = entry
    write_record(record, record_path)
    log(f"built and published {name} ({entry['image_id']})")
    return entry


def put(sandbox: Any, path: str, content: bytes) -> None:
    """Write a file into the sandbox through stdin (Modal 1.6 has no file API on Sandbox)."""
    proc = sandbox.exec("/bin/sh", "-c", f"mkdir -p \"$(dirname '{path}')\" && cat > '{path}'")
    proc.stdin.write(content)
    proc.stdin.write_eof()
    proc.stdin.drain()
    proc.wait()


def inspect(variant: str, *, modal: Any = None, client: Any = None, record_path: Path = RECORD,
            log: Callable[[str], None] = print) -> dict[str, Any]:
    """Start one sandbox from the published image, read what is in it, terminate it."""
    record = read_record(record_path)
    entry = record["images"].get(variant)
    if not entry or not entry.get("name"):
        raise SystemExit(f"{variant} has not been built; run build first")
    if modal is None:
        import modal  # noqa: PLW0621
    client = client or modal_client()
    app = modal.App.lookup(APP_NAME, create_if_missing=True, client=client)
    sandbox = modal.Sandbox.create("sleep", "600", app=app, client=client, image=modal.Image.from_name(entry["name"]),
                                   timeout=900, cpu=(2.0, 2.0), memory=(4096, 4096))
    seen: dict[str, Any] = {"at": now(), "sandbox_id": getattr(sandbox, "object_id", None)}
    try:
        for key, command in INSPECT:
            proc = sandbox.exec("/bin/sh", "-c", command)
            proc.wait()
            seen[key] = proc.stdout.read()
        seen["dpkg_sha256"] = hashlib.sha256(seen["dpkg"].encode()).hexdigest()
        if variant == "dev":
            put(sandbox, "/opt/eval/fixtures/_shared/egress.py", (SHARED / "egress.py").read_bytes())
            proc = sandbox.exec("python3", "/opt/eval/fixtures/_shared/egress.py", "selftest", "--out", "/tmp/es")
            proc.wait()
            seen["egress_selftest"] = {"exit_code": proc.returncode, "output": proc.stdout.read()[-4000:]}
    finally:
        sandbox.terminate()
    entry["inspected"] = seen
    write_record(record, record_path)
    log(f"inspected {entry['name']}: {seen['runtimes'].strip()}")
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/l2_image.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--variant", choices=list(VARIANTS))
    p.add_argument("--base-digest")
    p.add_argument("--apt-snapshot")
    b = sub.add_parser("build")
    b.add_argument("--variant", required=True, choices=list(VARIANTS))
    b.add_argument("--base-digest", required=True)
    b.add_argument("--apt-snapshot")
    b.add_argument("--confirm-spend", action="store_true", help="念誠 confirmed decision 6; Modal spend is fine")
    i = sub.add_parser("inspect")
    i.add_argument("--variant", required=True, choices=list(VARIANTS))
    i.add_argument("--confirm-spend", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "plan":
        for variant in [args.variant] if args.variant else list(VARIANTS):
            print(json.dumps(plan(variant, args.base_digest, args.apt_snapshot), ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_spend:
        print("refused: building or inspecting starts Modal work; pass --confirm-spend once decision 6 is made")
        return 2
    if args.command == "build":
        build(args.variant, args.base_digest, args.apt_snapshot)
    else:
        inspect(args.variant)
    return 0


if __name__ == "__main__":
    sys.exit(main())
