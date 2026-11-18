"""One command from this Mac: give the watch machine its secrets and state, then start pickfit watch there.

    uv run python deploy/watch/send_secrets.py root@HOST [--key ~/.ssh/KEY] [--dry-run]

It builds /etc/pickfit/watch.env from what this Mac already has, asks for the rest, and sends it over SSH on stdin,
so no value is printed, put in a command line or written to a local file:

- ANTHROPIC_API_KEY: the environment or the repository's .env
- MODAL_TOKEN_ID / MODAL_TOKEN_SECRET: the environment, or the active profile in ~/.modal.toml
- CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID: the environment or .env, else asked (a token with D1 edit on the
  account; wrangler's own login on this Mac is not copied)
- GH_PUSH_TOKEN, also used as GH_TOKEN: asked (a fine-grained token with Contents read and write on
  ncchen99/pickfit only; your `gh` login is not copied)
- AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY: asked, optional (Enter skips; the Windows lane then waits). Skipped,
  it offers this Mac's current AWS sign-in instead (`aws configure export-credentials`: temporary, with
  AWS_SESSION_TOKEN; the Windows lane works until it expires)
- SCW_ACCESS_KEY / SCW_SECRET_KEY: asked, optional: watch's own API key (an IAM application with Apple silicon rights
  only; the project and zone come from ~/.config/scw/config.yaml). Skipped, it offers this Mac's own key from that
  file instead, only if you say yes (the macOS lane renting Macs)

Then it copies runs/watch/jobs/ and runs/web/visits.jsonl (what was submitted and which sites were visited), and,
if you say yes, the Mac hosts in ~/.pickfit/mac-hosts with the SSH keys they name and the base manifests in
~/.pickfit/tart/hosts/ (the macOS lane uses a known host before it rents one). It checks that origin/main has the watch code the service runs, and starts the service.
--dry-run shows which names were found and what would run, never a value.
"""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENV_PATH = "/etc/pickfit/watch.env"
REMOTE_REPO = "/var/lib/pickfit/pickfit"
NEEDED_ON_MAIN = "pickfit/lanes.py"  # the service's flags (lanes, --publish push) come with it
DEFAULTS = {"PICKFIT_EC2_REGION": "ap-east-2", "SCW_DEFAULT_ZONE": "fr-par-1", "PICKFIT_PIPELINE_DAILY_CAP_USD": "80"}


def dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines (pickfit.env's rules: export, quotes, a trailing comment)."""
    sys.path.insert(0, str(REPO))
    from pickfit.env import _parse_line

    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        parsed = _parse_line(line)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out


def modal_tokens(path: Path) -> dict[str, str]:
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
    profiles = [p for p in config.values() if isinstance(p, dict)]
    active = next((p for p in profiles if p.get("active")), profiles[0] if len(profiles) == 1 else None)
    if not active or not active.get("token_id"):
        return {}
    return {"MODAL_TOKEN_ID": active["token_id"], "MODAL_TOKEN_SECRET": active.get("token_secret", "")}


def scw_profile(path: Path) -> dict[str, str]:
    """The default profile's top-level keys of the scw CLI's config.yaml (flat `key: value` lines)."""
    names = {"access_key": "SCW_ACCESS_KEY", "secret_key": "SCW_SECRET_KEY",
             "default_organization_id": "SCW_DEFAULT_ORGANIZATION_ID", "default_project_id": "SCW_DEFAULT_PROJECT_ID",
             "default_zone": "SCW_DEFAULT_ZONE"}
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        if line.startswith((" ", "\t")):  # inside `profiles:`; only the top level is the default profile
            continue
        key, _, value = line.partition(":")
        if key.strip() in names and value.strip():
            out[names[key.strip()]] = value.strip().strip("'\"")
    return out


def collect(args: argparse.Namespace, ask=getpass.getpass, confirm=input) -> dict[str, str]:
    found = {**dotenv(args.env_file), **{k: v for k, v in os.environ.items() if v}}
    values: dict[str, str] = dict(DEFAULTS)

    def take(name: str, *, prompt: str | None = None, optional: bool = False, hidden: bool = True) -> None:
        if found.get(name):
            values[name] = found[name]
            return
        if args.dry_run or prompt is None:
            return
        value = (ask if hidden else confirm)(f"{prompt}{' (Enter skips)' if optional else ''}: ").strip()
        if value:
            values[name] = value

    take("ANTHROPIC_API_KEY", prompt="Anthropic API key")
    modal = {k: v for k, v in found.items() if k.startswith("MODAL_TOKEN_")} or modal_tokens(args.modal_config)
    values.update(modal)
    take("CLOUDFLARE_API_TOKEN", prompt="Cloudflare API token with D1 edit")
    take("CLOUDFLARE_ACCOUNT_ID", prompt="Cloudflare account id", hidden=False)
    take("GH_PUSH_TOKEN", prompt="GitHub fine-grained token (Contents read/write on ncchen99/pickfit)")
    if values.get("GH_PUSH_TOKEN"):
        values.setdefault("GH_TOKEN", values["GH_PUSH_TOKEN"])
    take("AWS_ACCESS_KEY_ID", prompt="AWS access key id for the Windows lane", optional=True, hidden=False)
    if values.get("AWS_ACCESS_KEY_ID"):
        take("AWS_SECRET_ACCESS_KEY", prompt="AWS secret access key")
    elif not args.dry_run:
        signed_in = aws_sign_in(args.aws)
        if signed_in and confirm(f"Send this Mac's AWS sign-in instead (temporary, expires {signed_in['until']}), so "
                                 "the Windows lane works until then? [y/N] ").strip().lower() == "y":
            values.update(signed_in["values"])
    scw = scw_profile(args.scw_config)
    if args.dry_run:
        values.update({k: "" for k in scw})  # named in the dry run, never sent
    else:
        # Watch's own key (an IAM application with Apple silicon rights only) is better than this Mac's own login.
        access = confirm("Scaleway access key of watch's own API key (Enter skips): ").strip()
        if access:
            secret = ask("Its Scaleway secret key: ").strip()
            if secret:
                values.update({k: v for k, v in scw.items() if k not in ("SCW_ACCESS_KEY", "SCW_SECRET_KEY")})
                values.update({"SCW_ACCESS_KEY": access, "SCW_SECRET_KEY": secret})
        elif scw and confirm("Copy this Mac's own Scaleway key instead, so watch can rent Macs? [y/N] "
                             ).strip().lower() == "y":
            values.update(scw)
    return values


def aws_sign_in(aws: str = "aws", run=subprocess.run) -> dict | None:
    """This Mac's current AWS credentials (an `aws login` session): {values, until}, or None. Read from the CLI's
    output into memory only."""
    try:
        done = run([aws, "configure", "export-credentials", "--format", "process"], capture_output=True, text=True,
                   timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    try:
        creds = json.loads(done.stdout)
    except ValueError:
        return None
    if not creds.get("AccessKeyId") or not creds.get("SecretAccessKey"):
        return None
    values = {"AWS_ACCESS_KEY_ID": creds["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"]}
    if creds.get("SessionToken"):
        values["AWS_SESSION_TOKEN"] = creds["SessionToken"]
    return {"values": values, "until": creds.get("Expiration") or "when the session ends"}


REMOTE_HOME = "/var/lib/pickfit"


def tart_name(target: str) -> str:
    """The folder pickfit.verify.tart_host.SshHost keeps a host's base manifests in."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", target.split("@")[-1])


def mac_hosts_tar(hosts_dir: Path, tart_state: Path | None = None) -> tuple[bytes, list[str]]:
    """~/.pickfit/mac-hosts/*.json (and rentals.jsonl) with each host's SSH key, re-pointed at the pickfit user's
    ~/.pickfit/ssh/, and the base manifests in ~/.pickfit/tart/hosts/<host>/ (without them the macOS lane takes
    the host's bases for unbuilt and fails rebuilding them); paths relative to ~/.pickfit.
    Returns (the tar, the host names)."""
    buf = io.BytesIO()
    names: list[str] = []

    def add(name: str, data: bytes, mode: int = 0o600) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(data), mode
        tar.addfile(info, io.BytesIO(data))

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        keys: dict[str, str] = {}
        for path in sorted(hosts_dir.glob("*.json")):
            try:
                host = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = host.get("key")
            if key:
                local = Path(key).expanduser()
                if not local.is_file():
                    raise SystemExit(f"{path.name} names the SSH key {local}, which is not on this Mac")
                remote = keys.setdefault(str(local), f"ssh/{local.name}")
                if remote not in [n for n in tar.getnames()]:
                    add(remote, local.read_bytes())
                    if local.with_suffix(".pub").is_file():
                        add(remote + ".pub", local.with_suffix(".pub").read_bytes(), 0o644)
                host["key"] = f"{REMOTE_HOME}/.pickfit/{remote}"
            add(f"mac-hosts/{path.name}", (json.dumps(host, indent=2) + "\n").encode(), 0o644)
            names.append(path.stem)
            if host.get("target") and tart_state is not None:
                folder = tart_state / "hosts" / tart_name(host["target"])
                for manifest in sorted(folder.glob("*.json")) if folder.is_dir() else []:
                    add(f"tart/hosts/{folder.name}/{manifest.name}", manifest.read_bytes(), 0o644)
        rentals = hosts_dir / "rentals.jsonl"
        if rentals.is_file():
            add("mac-hosts/rentals.jsonl", rentals.read_bytes(), 0o644)
    return buf.getvalue(), names


REQUIRED = ("ANTHROPIC_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID", "GH_PUSH_TOKEN")


def env_text(values: dict[str, str]) -> str:
    for name, value in values.items():
        if "\n" in value or "\r" in value:
            raise SystemExit(f"{name} has a line break; fix it at its source")
    lines = ["# written by deploy/watch/send_secrets.py; root:pickfit 0640"]
    lines += [f"{k}={v}" for k, v in sorted(values.items()) if v]
    return "\n".join(lines) + "\n"


def state_tar(runs: Path) -> bytes:
    """runs/watch/jobs/ and runs/web/visits.jsonl, paths relative to runs/."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in ("watch/jobs", "web/visits.jsonl"):
            if (runs / rel).exists():
                tar.add(runs / rel, arcname=rel)
    return buf.getvalue()


def main(argv: list[str] | None = None, *, ask=getpass.getpass, confirm=input,
         run=subprocess.run) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("host", help="root@HOST of the watch machine")
    p.add_argument("--key", help="SSH private key for it")
    p.add_argument("--env-file", type=Path, default=REPO / ".env")
    p.add_argument("--modal-config", type=Path, default=Path.home() / ".modal.toml")
    p.add_argument("--scw-config", type=Path, default=Path.home() / ".config" / "scw" / "config.yaml")
    p.add_argument("--runs", type=Path, default=REPO / "runs", help="where this Mac's watch kept its state")
    p.add_argument("--mac-hosts", type=Path, default=Path.home() / ".pickfit" / "mac-hosts",
                   help="this Mac's known Mac hosts (offered to the macOS lane)")
    p.add_argument("--tart-state", type=Path, default=Path.home() / ".pickfit" / "tart",
                   help="where this Mac keeps the hosts' base manifests (sent with the Mac hosts)")
    p.add_argument("--aws", default="aws", help="the AWS CLI, for this Mac's sign-in when no key is typed")
    p.add_argument("--no-start", action="store_true", help="send the secrets and state, do not start the service")
    p.add_argument("--dry-run", action="store_true", help="name what was found and what would run; send nothing")
    args = p.parse_args(argv)
    ssh = ["ssh", "-o", "StrictHostKeyChecking=accept-new", *(["-i", args.key] if args.key else []), args.host]

    values = collect(args, ask=ask, confirm=confirm)
    missing = [n for n in REQUIRED if not values.get(n)]
    print("found: " + ", ".join(sorted(n for n, v in values.items() if v or args.dry_run)))
    if missing:
        print("missing: " + ", ".join(missing) + ("" if args.dry_run else "; nothing was sent"))
        if not args.dry_run:
            return 1
    state = state_tar(args.runs)
    hosts, host_names = (b"", [])
    if any(args.mac_hosts.glob("*.json")):
        found = sorted(p.stem for p in args.mac_hosts.glob("*.json"))
        if args.dry_run:
            print(f"would offer the Mac hosts {', '.join(found)} and their SSH keys")
        elif confirm(f"Copy the Mac hosts {', '.join(found)} and their SSH keys so the macOS lane can use them? "
                     "[y/N] ").strip().lower() == "y":
            hosts, host_names = mac_hosts_tar(args.mac_hosts, args.tart_state)
    steps = [
        ("secrets", f"install -m 640 -o root -g pickfit /dev/stdin {ENV_PATH}", env_text(values).encode()),
        ("state", f"install -d -o pickfit -g pickfit {REMOTE_REPO}/runs && "
                  f"tar -xzf - -C {REMOTE_REPO}/runs && chown -R pickfit:pickfit {REMOTE_REPO}/runs", state),
        *([("mac hosts", f"install -d -o pickfit -g pickfit -m 700 {REMOTE_HOME}/.pickfit && "
                         f"tar -xzf - -C {REMOTE_HOME}/.pickfit && chown -R pickfit:pickfit {REMOTE_HOME}/.pickfit && "
                         f"chmod 700 {REMOTE_HOME}/.pickfit/ssh {REMOTE_HOME}/.pickfit/mac-hosts", hosts)]
          if host_names else []),
        ("main", f"sudo -u pickfit git -C {REMOTE_REPO} fetch -q origin main && "
                 f"sudo -u pickfit git -C {REMOTE_REPO} cat-file -e origin/main:{NEEDED_ON_MAIN}", b""),
    ]
    if not args.no_start:
        steps.append(("start", "systemctl enable --now pickfit-watch && sleep 5 && "
                               "systemctl --no-pager --lines 20 status pickfit-watch", b""))
    for name, remote, data in steps:
        if args.dry_run:
            print(f"would run on {args.host}: {remote}" + (f"  (stdin: {len(data)} bytes)" if data else ""))
            continue
        done = run([*ssh, remote], input=data, capture_output=name != "start")
        if done.returncode != 0:
            if name == "main":
                print(f"origin/main has no {NEEDED_ON_MAIN} yet: the secrets and state are in place, but the service "
                      "was not started. Merge the watch work into main, then run this again with --no-start left off.")
            else:  # what the remote command said; the secrets went in on stdin and are never echoed back
                said = (done.stderr or b"").decode(errors="replace").strip().splitlines()[-3:]
                print(f"{name} failed on {args.host} (exit {done.returncode}): {' / '.join(said)}")
            return 1
        print(f"{name}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
