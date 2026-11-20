"""The Cloud Run deploy's checks in CI (.github/workflows/worker.yml, job deploy-cloudrun). Standard library only.

    python3 scripts/cloudrun_deploy.py changed --base SHA --head SHA   # deploy=true|false: does this push change the site?
    python3 scripts/cloudrun_deploy.py serving                         # the revision serving pickfit now (recorded as PREV)
    python3 scripts/cloudrun_deploy.py verify --prev REV               # after worker/cloudrun/deploy.sh

`verify` makes sure the new build is what pickfit.app serves, or puts the previous revision back:

1. the service's latest ready revision is new (not PREV); if the traffic did not follow it, it is moved to it;
2. GET https://pickfit.app/ (JSON) until its data_sha256 equals the one in worker/src/generated/index.json, which
   deploy.sh just built, and entries >= --min-entries, for at most --timeout seconds;
3. /mcp answers a JSON-RPC tools/list with pickfit's tools.

If 2 or 3 fails, the traffic goes back to PREV (`gcloud run services update-traffic pickfit --to-revisions=PREV=100`)
and the command exits 1. The decisions are plain functions, tested in tests/test_cloudrun_deploy.py without network.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE = "pickfit"
PROJECT = "pickfit-app"
REGION = "asia-east1"
SITE = "https://pickfit.app"
INDEX = REPO_ROOT / "worker" / "src" / "generated" / "index.json"
MIN_ENTRIES = 1000
REQUIRED_TOOLS = ("find_software", "get_install_guide")

# What the deployed image is built from: worker/ (minus what .gcloudignore leaves out), the records and their
# translations, the Python that builds the index (pickfit/index.py and what it imports), and this deploy itself.
DEPLOY_PATHS = (
    "worker/*",
    "data/software/*",
    "data/i18n/*",
    "pickfit/index.py",
    "pickfit/i18n.py",
    "pickfit/schema.py",
    "pickfit/usage_guide.py",
    "pickfit/userpaths.py",
    "scripts/build_index.py",
    "scripts/cloudrun_deploy.py",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/worker.yml",
)
IGNORED_PATHS = ("worker/bench/*", "worker/test/*", "worker/*.md", "worker/cloudrun/*.md")
NO_BASE = {"", "0" * 40}


# --- which pushes deploy ------------------------------------------------------------------------------------


def needs_deploy(paths: Iterable[str]) -> bool:
    """True when a changed path can change what pickfit.app serves."""
    for path in paths:
        if any(fnmatch.fnmatch(path, p) for p in IGNORED_PATHS):
            continue
        if any(fnmatch.fnmatch(path, p) for p in DEPLOY_PATHS):
            return True
    return False


def changed_paths(base: str, head: str, run=subprocess.run) -> list[str] | None:
    """Paths changed between two commits, or None when that cannot be told (a new branch, history not fetched)."""
    if base in NO_BASE:
        return None
    done = run(["git", "diff", "--name-only", base, head], cwd=REPO_ROOT, capture_output=True, text=True)
    return done.stdout.split() if done.returncode == 0 else None


# --- the service --------------------------------------------------------------------------------------------


def serving_revision(service: dict[str, Any]) -> str | None:
    """The revision taking the most traffic in a `gcloud run services describe --format=json`."""
    status = service.get("status") or {}
    best: tuple[int, str] | None = None
    for target in status.get("traffic") or []:
        name = target.get("revisionName") or (status.get("latestReadyRevisionName") if target.get("latestRevision") else None)
        percent = int(target.get("percent") or 0)
        if name and percent and (best is None or percent > best[0]):
            best = (percent, name)
    return best[1] if best else None


def latest_ready(service: dict[str, Any]) -> str | None:
    return (service.get("status") or {}).get("latestReadyRevisionName")


class Gcloud:
    def __init__(self, project: str = PROJECT, region: str = REGION, run=subprocess.run) -> None:
        self.where = ["--project", project, "--region", region]
        self.run = run

    def describe(self) -> dict[str, Any]:
        done = self.run(["gcloud", "run", "services", "describe", SERVICE, *self.where, "--format=json"],
                        capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    def route(self, *traffic: str) -> None:
        self.run(["gcloud", "run", "services", "update-traffic", SERVICE, *self.where, *traffic, "--quiet"], check=True)


# --- the site -----------------------------------------------------------------------------------------------


def health_problem(payload: Any, expect_sha: str, min_entries: int) -> str | None:
    """Why the site's JSON at / does not show this build yet, or None when it does."""
    if not isinstance(payload, dict):
        return "/ did not answer with a JSON object"
    served = payload.get("data_sha256")
    if served != expect_sha:
        return f"serves data {str(served)[:12]}, not {expect_sha[:12]}"
    entries = payload.get("entries")
    if not isinstance(entries, int) or entries < min_entries:
        return f"serves {entries} entries, fewer than {min_entries}"
    return None


def parse_mcp_body(content_type: str, body: str) -> list[dict[str, Any]]:
    """JSON-RPC messages from a Streamable HTTP answer: one JSON body, or SSE `data:` lines."""
    if "text/event-stream" in content_type:
        messages = []
        for event in body.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in event.split("\n") if line.startswith("data:"))
            if data:
                messages.append(json.loads(data))
        return messages
    parsed = json.loads(body)
    return parsed if isinstance(parsed, list) else [parsed]


def tools_problem(messages: list[dict[str, Any]], request_id: int = 1) -> str | None:
    """Why a tools/list answer is wrong, or None when it lists pickfit's tools."""
    answer = next((m for m in messages if isinstance(m, dict) and m.get("id") == request_id), None)
    if answer is None:
        return "no JSON-RPC answer to tools/list"
    if "error" in answer:
        return f"tools/list failed: {json.dumps(answer['error'])[:200]}"
    tools = (answer.get("result") or {}).get("tools")
    if not isinstance(tools, list):
        return "tools/list answer has no tools list"
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    missing = [name for name in REQUIRED_TOOLS if name not in names]
    return f"tools/list lacks {', '.join(missing)}" if missing else None


def http(url: str, *, data: bytes | None = None, headers: dict[str, str], timeout: float = 30) -> tuple[int, str, str]:
    request = urllib.request.Request(url, data=data, headers={"user-agent": "pickfit-ci-deploy", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("content-type", ""), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("content-type", ""), err.read().decode("utf-8", "replace")


def wait_for_build(site: str, expect_sha: str, min_entries: int, timeout: float, interval: float,
                   fetch=http, clock=time.monotonic, sleep=time.sleep, out=print) -> str | None:
    """Poll / until it serves this build; the last problem when the time runs out, else None."""
    deadline = clock() + timeout
    while True:
        try:
            status, _, body = fetch(f"{site}/", headers={"accept": "application/json", "cache-control": "no-cache"})
            problem = health_problem(json.loads(body), expect_sha, min_entries) if status == 200 else f"/ answered {status}"
        except (OSError, ValueError) as err:
            problem = f"/ failed: {type(err).__name__}: {err}"
        if problem is None:
            return None
        if clock() >= deadline:
            return problem
        out(f"cloudrun: waiting, {problem}")
        sleep(interval)


def mcp_smoke(site: str, fetch=http) -> str | None:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    try:
        status, content_type, body = fetch(f"{site}/mcp", data=json.dumps(request).encode(), headers={
            "content-type": "application/json", "accept": "application/json, text/event-stream"})
        if status != 200:
            return f"/mcp answered {status}: {body[:200]}"
        return tools_problem(parse_mcp_body(content_type, body))
    except (OSError, ValueError) as err:
        return f"/mcp failed: {type(err).__name__}: {err}"


def verify(prev: str | None, *, expect_sha: str, site: str = SITE, min_entries: int = MIN_ENTRIES,
           timeout: float = 300, interval: float = 10, gcloud: Gcloud | None = None, fetch=http,
           clock=time.monotonic, sleep=time.sleep, out: Callable[[str], None] = print) -> int:
    gcloud = gcloud or Gcloud()
    service = gcloud.describe()
    new, serving = latest_ready(service), serving_revision(service)
    if not new or new == prev:
        out(f"cloudrun: no new ready revision (latest ready {new}, before {prev}); the deploy did not take")
        return 1
    if serving != new:
        out(f"cloudrun: traffic is on {serving}, not the new {new}; moving it to the latest revision")
        gcloud.route("--to-latest")
    out(f"cloudrun: {new} serves; checking {site} for data {expect_sha[:12]}")
    problem = wait_for_build(site, expect_sha, min_entries, timeout, interval, fetch=fetch, clock=clock, sleep=sleep,
                             out=out) or mcp_smoke(site, fetch=fetch)
    if problem is None:
        out(f"cloudrun: {new} serves this build and /mcp lists its tools")
        return 0
    out(f"cloudrun: check failed: {problem}")
    if prev:
        out(f"cloudrun: rolling traffic back to {prev}")
        gcloud.route(f"--to-revisions={prev}=100")
    else:
        out("cloudrun: no previous revision recorded; nothing to roll back to")
    return 1


def built_sha(index_path: Path = INDEX) -> str:
    return json.loads(index_path.read_text(encoding="utf-8"))["data_sha256"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--region", default=REGION)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("changed", help="print deploy=true|false for $GITHUB_OUTPUT")
    c.add_argument("--base", default="")
    c.add_argument("--head", default="HEAD")
    sub.add_parser("serving", help="print the revision serving the traffic now")
    v = sub.add_parser("verify", help="check the new revision serves this build, else roll back to --prev")
    v.add_argument("--prev", default="")
    v.add_argument("--site", default=SITE)
    v.add_argument("--index", type=Path, default=INDEX)
    v.add_argument("--min-entries", type=int, default=MIN_ENTRIES)
    v.add_argument("--timeout", type=float, default=300)
    v.add_argument("--interval", type=float, default=10)
    args = parser.parse_args(argv)

    if args.command == "changed":
        paths = changed_paths(args.base, args.head)
        deploy = True if paths is None else needs_deploy(paths)
        why = "changes cannot be listed" if paths is None else f"{len(paths)} changed path(s)"
        print(f"cloudrun: {why}; deploy={'yes' if deploy else 'no'}", file=sys.stderr)
        print(f"deploy={'true' if deploy else 'false'}")
        return 0
    gcloud = Gcloud(args.project, args.region)
    if args.command == "serving":
        print(serving_revision(gcloud.describe()) or "")
        return 0
    return verify(args.prev or None, expect_sha=built_sha(args.index), site=args.site.rstrip("/"),
                  min_entries=args.min_entries, timeout=args.timeout, interval=args.interval, gcloud=gcloud)


if __name__ == "__main__":
    sys.exit(main())
