"""What the replay box actually installed: an SBOM taken before the box closes (docs/proposals/security.md, S3).

sec.v1 judged most records by the repository's latest lockfile, which is often not what a person installs (11/19:
OpenPets was scanned at a 10/30 commit while the verified install was the 10/18 v4.1.0 DMG). So once the replay has
installed the tool and its checks passed, and before the box is destroyed, pickfit reads the box user's side of the
disk with tools baked into the sandbox image (pickfit/verify/sandbox.Dockerfile):

- syft (Apache-2.0) over $HOME with its installed-package catalogers (its image set, so a lockfile left in a cloned
  repository is not taken for what was installed): npm packages under node_modules, Python dist-info in uv tool,
  pipx and --user environments, the Go modules a Go binary's build info lists, the crates a Rust binary built with
  cargo-auditable lists. Caches, module and registry source caches and uv's own Pythons are left out;
- `npm ls -g --all --omit=dev --json`: the global npm tree with its paths;
- `govulncheck -mode=binary -json` (BSD-3-Clause) on each Go binary syft found: which vulnerable packages are compiled
  in and which vulnerable functions are called (symbol level), against the Go vulnerability database;
- `cargo audit bin --json` (Apache-2.0 OR MIT) on each Rust binary with cargo-auditable data;
- the SHA-256 of the executables in the install folders, and the version the run recorded.

The box runs everything as the box user, with the image's own binaries named by absolute path. Linux boxes only for
now (macOS and Windows later). Never raises and never fails a run: what did not work is listed in `errors`. The
result is evidence, sbom.json beside the run's report.json; pickfit/security.py reads it as the installed_artifact
observation and ties it to the run id, the tool version and the artifacts' hashes.
"""

from __future__ import annotations

import json
import shlex
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pickfit.verify.box import Box, BoxError

SBOM_VERSION = "sbom.v1"
WORK = "/tmp/pickfit-sbom"
SYFT = "/usr/local/bin/syft"
GOVULNCHECK = "/usr/local/bin/govulncheck"
CARGO_AUDIT = "/usr/local/bin/cargo-audit"
PYTHON = "/usr/local/bin/python3"
NPM = "/usr/local/bin/npm"
# Where user-level installs land (box.BOX_PATH), and the work folder where downloads and builds go.
INSTALL_DIRS = (".local/bin", ".cargo/bin", "go/bin", "bin", "work", ".local/lib/node_modules")
SYFT_EXCLUDES = ("./.cache/**", "./.npm/**", "./.cargo/registry/**", "./.cargo/git/**", "./go/pkg/**",
                 "./.rustup/**", "./.local/share/uv/python/**", "./.local/share/pnpm/store/**")
MAX_BINARIES = 5  # Go or Rust binaries checked one by one
MAX_ARTIFACTS = 40
INVENTORY_MAX_BYTES = 12_000_000
BASE_TIMEOUT_S = 480
BINARY_TIMEOUT_S = 300
ECOSYSTEM_OF = {"npm": "npm", "python": "pypi", "go-module": "go", "rust-crate": "crates"}

# Runs inside the box with the image's Python (standard library only): turns each tool's output into the few fields
# pickfit keeps, so what comes back through read_file stays small.
REDUCER = r'''
import json, os, sys

ECO = {"npm": "npm", "python": "pypi", "go-module": "go", "rust-crate": "crates"}


def load(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def syft(path, home):
    try:
        doc = json.loads(load(path) or "{}")
    except ValueError:
        return [], [], [], None
    packages, go, rust = [], [], []
    for a in doc.get("artifacts") or []:
        locs = [l.get("path") for l in a.get("locations") or [] if l.get("path")]
        found_by = a.get("foundBy") or ""
        packages.append({"ecosystem": ECO.get(a.get("type"), a.get("type")), "name": a.get("name"),
                         "version": a.get("version"), "purl": a.get("purl"), "found_by": found_by,
                         "locations": locs[:3]})
        full = [os.path.join(home, p.lstrip("/")) if not p.startswith(home) else p for p in locs[:1]]
        if "go-module-binary" in found_by:
            go += full
        if "cargo-auditable" in found_by:
            rust += full
    version = (doc.get("descriptor") or {}).get("version")
    return packages, sorted(set(go)), sorted(set(rust)), version


def npm(path):
    try:
        doc = json.loads(load(path) or "{}")
    except ValueError:
        return []
    out, seen, stack = [], set(), [((), doc.get("dependencies") or {})]
    while stack:
        trail, deps = stack.pop()
        for name, info in sorted(deps.items()):
            if not isinstance(info, dict) or not info.get("version"):
                continue
            key = (name, info["version"])
            if key not in seen:
                seen.add(key)
                out.append({"ecosystem": "npm", "name": name, "version": info["version"], "found_by": "npm-ls",
                            "locations": [" > ".join(trail + (name,))]})
            if len(trail) < 40:
                stack.append((trail + (name,), info.get("dependencies") or {}))
    return out


def artifacts(path):
    out = []
    for line in load(path).splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out.append({"sha256": parts[0], "path": parts[1].strip()})
    return out


def objects(text):
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        try:
            obj, i = dec.raw_decode(text, i)
        except ValueError:
            break
        out.append(obj)
    return out


def govuln(path, binary):
    best = {}
    for obj in objects(load(path)):
        f = obj.get("finding") if isinstance(obj, dict) else None
        if not f or not f.get("osv"):
            continue
        top = (f.get("trace") or [{}])[0]
        level = "symbol" if top.get("function") else "package" if top.get("package") else "module"
        rank = ("symbol", "package", "module").index(level)
        row = {"binary": binary, "osv": f["osv"], "level": level, "module": top.get("module"),
               "version": top.get("version"), "package": top.get("package"),
               "function": ((top.get("receiver") + ".") if top.get("receiver") else "") + top["function"]
               if top.get("function") else None, "fixed_version": f.get("fixed_version")}
        if f["osv"] not in best or rank < best[f["osv"]][0]:
            best[f["osv"]] = (rank, row)
    return [row for _, row in best.values()]


def audit(path, binary):
    try:
        doc = json.loads(load(path) or "{}")
    except ValueError:
        return []
    out = []
    for v in ((doc.get("vulnerabilities") or {}).get("list") or []):
        adv, pkg = v.get("advisory") or {}, v.get("package") or {}
        out.append({"binary": binary, "advisory": adv.get("id"), "package": pkg.get("name"),
                    "version": pkg.get("version")})
    return out


mode, work = sys.argv[1], sys.argv[2]
if mode == "base":
    home = sys.argv[3]
    packages, go, rust, version = syft(os.path.join(work, "syft.json"), home)
    packages += npm(os.path.join(work, "npm.json"))
    status = dict(line.split(" ", 1) for line in load(os.path.join(work, "status")).split("\n") if " " in line)
    print(json.dumps({"packages": packages, "go_binaries": go, "rust_binaries": rust, "syft_version": version,
                      "artifacts": artifacts(os.path.join(work, "artifacts.txt")), "status": status,
                      "errors": {k: load(os.path.join(work, k + ".err"))[-400:] for k in ("syft", "npm")}}))
elif mode == "govuln":
    for row in govuln(sys.argv[3], sys.argv[4]):
        print(json.dumps(row))
elif mode == "audit":
    for row in audit(sys.argv[3], sys.argv[4]):
        print(json.dumps(row))
'''


def base_script(home: str) -> str:
    """The shell that hashes the installed executables, runs syft and npm ls, and reduces both to inventory.json."""
    w = shlex.quote(WORK)
    finds = " ".join(shlex.quote(f"{home}/{d}") for d in INSTALL_DIRS)
    excludes = " ".join(f"--exclude {shlex.quote(e)}" for e in SYFT_EXCLUDES)
    return (
        f"mkdir -p {w} && cd {shlex.quote(home)} && : > {w}/status; "
        f"{{ for d in {finds}; do [ -d \"$d\" ] && /usr/bin/find \"$d\" -maxdepth 3 \\( -type f -o -type l \\) "
        f"-perm -u+x 2>/dev/null; done; }} | while read -r f; do /usr/bin/readlink -f -- \"$f\"; done "
        f"| /usr/bin/sort -u | /usr/bin/head -n {MAX_ARTIFACTS} | while read -r f; do [ -f \"$f\" ] && "
        f"/usr/bin/sha256sum -- \"$f\"; done > {w}/artifacts.txt 2>/dev/null; "
        f"SYFT_CHECK_FOR_APP_UPDATE=false /usr/bin/timeout 360 {SYFT} scan dir:{shlex.quote(home)} "
        f"--override-default-catalogers image {excludes} -q -o syft-json={w}/syft.json 2> {w}/syft.err; "
        f"echo \"syft $?\" >> {w}/status; "
        f"/usr/bin/timeout 90 {NPM} ls -g --all --omit=dev --json > {w}/npm.json 2> {w}/npm.err; "
        f"echo \"npm $?\" >> {w}/status; "
        f"{PYTHON} {w}/reduce.py base {w} {shlex.quote(home)} > {w}/inventory.json")


def _read_json(box: Box, path: str, max_bytes: int) -> Any:
    return json.loads(box.read_file(path, max_bytes).decode("utf-8", errors="replace"))


def _read_lines(box: Box, path: str) -> list[dict[str, Any]]:
    try:
        text = box.read_file(path, 2_000_000).decode("utf-8", errors="replace")
    except BoxError:
        return []
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def collect(box: Box, evidence_dir: Path | None, *, run_id: str, tool_version: str | None = None,
            log: Callable[[str], None] = print) -> dict[str, Any] | None:
    """Take the SBOM of what `box` installed and write it to evidence_dir/sbom.json; None on a box that is not Linux.
    Never raises: a tool that failed is named in `errors`."""
    if getattr(box, "os", "linux") != "linux":
        return None
    began = time.monotonic()
    home = getattr(box, "home", "/home/sbx")
    doc: dict[str, Any] = {"version": SBOM_VERSION, "run_id": run_id, "tool_version": tool_version,
                           "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "box": {"runner": getattr(box, "runner", None), "image": getattr(box, "image", None),
                                   "os": "linux", "arch": getattr(box, "arch", None)},
                           "tools": {}, "packages": [], "artifacts": [], "govulncheck": [], "govulncheck_ran": False,
                           "cargo_audit": [], "errors": []}
    try:
        box.write_file(f"{WORK}/reduce.py", REDUCER)
        ran = box.exec(base_script(home), BASE_TIMEOUT_S)
        if not ran.ok:
            doc["errors"].append(f"inventory exited {ran.exit_code}: {(ran.stderr or ran.stdout).strip()[-300:]}")
        inventory = _read_json(box, f"{WORK}/inventory.json", INVENTORY_MAX_BYTES)
        doc["packages"] = [p for p in inventory.get("packages") or [] if p.get("name") and p.get("version")]
        doc["artifacts"] = inventory.get("artifacts") or []
        doc["tools"]["syft"] = inventory.get("syft_version")
        for tool, code in (inventory.get("status") or {}).items():
            if str(code).strip() not in ("0", "1" if tool == "npm" else "0"):  # npm ls exits 1 on a peer warning
                doc["errors"].append(f"{tool} exited {str(code).strip()}: "
                                     f"{(inventory.get('errors') or {}).get(tool, '').strip()[-200:]}")
        for i, binary in enumerate((inventory.get("go_binaries") or [])[:MAX_BINARIES]):
            out = f"{WORK}/govuln-{i}.json"
            r = box.exec(f"/usr/bin/timeout {BINARY_TIMEOUT_S - 10} {GOVULNCHECK} -mode=binary -json "
                         f"{shlex.quote(binary)} > {out} 2> {out}.err; "
                         f"{PYTHON} {WORK}/reduce.py govuln {WORK} {out} {shlex.quote(binary)} >> {WORK}/govuln.jsonl",
                         BINARY_TIMEOUT_S)
            if not r.ok:
                doc["errors"].append(f"govulncheck {binary}: exited {r.exit_code}")
            doc["govulncheck_ran"] = True
        doc["govulncheck"] = _read_lines(box, f"{WORK}/govuln.jsonl") if doc["govulncheck_ran"] else []
        for i, binary in enumerate((inventory.get("rust_binaries") or [])[:MAX_BINARIES]):
            out = f"{WORK}/audit-{i}.json"
            r = box.exec(f"/usr/bin/timeout {BINARY_TIMEOUT_S - 10} {CARGO_AUDIT} audit --db {WORK}/advisory-db "
                         f"--json bin {shlex.quote(binary)} > {out} 2> {out}.err; "
                         f"{PYTHON} {WORK}/reduce.py audit {WORK} {out} {shlex.quote(binary)} >> {WORK}/audit.jsonl",
                         BINARY_TIMEOUT_S)
            if not r.ok:
                doc["errors"].append(f"cargo audit {binary}: exited {r.exit_code}")
        if inventory.get("rust_binaries"):
            doc["cargo_audit"] = _read_lines(box, f"{WORK}/audit.jsonl")
    except (BoxError, ValueError, OSError) as err:
        doc["errors"].append(f"{type(err).__name__}: {str(err)[:300]}")
    except Exception as err:  # noqa: BLE001 - evidence only: never fail a run over it
        doc["errors"].append(f"{type(err).__name__}: {str(err)[:300]}")
    doc["seconds"] = round(time.monotonic() - began, 1)
    log(f"  sbom: {len(doc['packages'])} packages, {len(doc['artifacts'])} executables, "
        f"{len(doc['govulncheck'])} govulncheck findings, {len(doc['errors'])} errors · {doc['seconds']:.0f}s")
    if evidence_dir is not None:
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "sbom.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8")
        except OSError as err:
            log(f"  sbom not saved: {err}")
    return doc
