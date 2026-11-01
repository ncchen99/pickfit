"""Homebrew Cask as a discovery source (P2.7): formulae.brew.sh's cask JSON and install analytics.

Four GETs per run, no key: api/cask.json (every cask in Homebrew/homebrew-cask, BSD-2-Clause)
and api/analytics/cask-install/{30d,90d,365d}.json. Install counts are a selection signal
only; records do not carry them (docs/source-terms.md). A cask has no license field, so
whether it is open source comes from GitHub's license for the repository its download URL
or homepage names (pickfit.discover.listings).
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx2

from pickfit.discover.github import USER_AGENT, runs_dir
from pickfit.discover.listings import Listing, github_repo
from pickfit.ledger import taipei_date, taipei_now

SOURCE = "homebrew_cask"
API = "https://formulae.brew.sh/api"
CATALOG = f"{API}/cask.json"
ANALYTICS = f"{API}/analytics/cask-install/{{}}.json"
WINDOWS = ("30d", "90d", "365d")
CASK_PAGE = "https://formulae.brew.sh/cask/{}"
CAVEATS_MAX = 1_000
# Artifact kinds, strongest first: what the cask puts on the Mac.
GUI_ARTIFACTS = ("app", "suite")
INSTALLER_ARTIFACTS = ("pkg", "installer")


class CaskError(RuntimeError):
    """The cask API could not be fetched or read."""


def _get_json(client: httpx2.Client, url: str, trace_dir: Path | None) -> Any:
    started = time.monotonic()
    try:
        resp = client.get(url, follow_redirects=True)
    except httpx2.TransportError as err:
        raise CaskError(f"GET {url}: {type(err).__name__}") from None
    path = (trace_dir or runs_dir() / "traces") / f"homebrew-cask-{taipei_date()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": taipei_now().isoformat(timespec="seconds"), "url": url, "status": resp.status_code,
              "bytes": len(resp.content), "latency_s": round(time.monotonic() - started, 3)}
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(record) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    if resp.status_code != 200:
        raise CaskError(f"GET {url}: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as err:
        raise CaskError(f"GET {url}: {err}") from None


def fetch(http: httpx2.Client | None = None, trace_dir: Path | None = None) -> tuple[list[dict[str, Any]],
                                                                                    dict[str, dict[str, int]]]:
    """(casks, {window: {token: install events}})."""
    client = http or httpx2.Client(timeout=120.0, headers={"User-Agent": USER_AGENT})
    try:
        casks = _get_json(client, CATALOG, trace_dir)
        installs = {w: install_counts(_get_json(client, ANALYTICS.format(w), trace_dir)) for w in WINDOWS}
    finally:
        if http is None:
            client.close()
    return casks, installs


def install_counts(report: dict[str, Any]) -> dict[str, int]:
    """token -> install events in one analytics report (a cask listed under several rows is summed)."""
    counts: Counter[str] = Counter()
    for item in report.get("items") or []:
        try:
            counts[item["cask"]] += int(str(item["count"]).replace(",", ""))
        except (KeyError, ValueError):
            continue
    return dict(counts)


def artifact_kinds(cask: dict[str, Any]) -> set[str]:
    return {key for artifact in cask.get("artifacts") or [] if isinstance(artifact, dict) for key in artifact}


def cask_kind(cask: dict[str, Any]) -> str:
    """gui (an app), cli (only command-line binaries), installer (a pkg or installer), or other."""
    kinds = artifact_kinds(cask)
    if kinds & set(GUI_ARTIFACTS):
        return "gui"
    if "binary" in kinds:
        return "cli"
    if kinds & set(INSTALLER_ARTIFACTS):
        return "installer"
    return "other"


def to_listing(cask: dict[str, Any], installs: dict[str, dict[str, int]]) -> Listing | None:
    token = cask.get("token")
    if not token:
        return None
    names = [n for n in cask.get("name") or [] if isinstance(n, str) and n.strip()]
    github = github_repo(cask.get("url"), cask.get("homepage"))
    kinds = artifact_kinds(cask)
    binaries = [b for a in cask.get("artifacts") or [] if isinstance(a, dict) for b in a.get("binary") or []
                if isinstance(b, str)]
    caveats = cask.get("caveats")
    return Listing(
        source=SOURCE, item_id=token, name=names[0] if names else token, url=CASK_PAGE.format(token),
        kind=cask_kind(cask), summary=(cask.get("desc") or "").strip() or None,
        homepage=cask.get("homepage"), upstream=f"https://github.com/{github}" if github else None,
        github=github, version=cask.get("version"),
        install_command=f"brew install --cask {token}",
        installs={w: installs.get(w, {}).get(token, 0) for w in WINDOWS},
        deprecated=bool(cask.get("deprecated") or cask.get("disabled")),
        facts={
            "names": names,
            "download_url": cask.get("url"),
            "artifacts": sorted(k for k in kinds if k not in ("uninstall", "zap", "uninstall_postflight",
                                                              "uninstall_preflight", "postflight", "preflight")),
            "binaries": [b.rsplit("/", 1)[-1] for b in binaries][:10],
            "depends_on": cask.get("depends_on") or {},
            "auto_updates": bool(cask.get("auto_updates")),
            "caveats": caveats[:CAVEATS_MAX] if isinstance(caveats, str) else None,
            "deprecation_reason": cask.get("deprecation_reason") or cask.get("disable_reason"),
        })


def parse(casks: list[dict[str, Any]], installs: dict[str, dict[str, int]]) -> list[Listing]:
    return [x for c in casks if isinstance(c, dict) and (x := to_listing(c, installs)) is not None]
