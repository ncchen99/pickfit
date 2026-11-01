"""Flathub as a discovery source (P2.7): the AppStream catalog of the flatpak repository.

One GET of dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz, the catalog every
flatpak client downloads to list apps; not the website, its API or its install stats
(docs/source-terms.md). Each app's metadata is written by its authors under one of the
permissive metadata licenses AppStream accepts. Only the untranslated text is kept.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2

from pickfit.discover.github import USER_AGENT, runs_dir
from pickfit.discover.listings import Listing, github_repo
from pickfit.ledger import taipei_date, taipei_now

SOURCE = "flathub"
CATALOG = "https://dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz"
APP_PAGE = "https://flathub.org/apps/{}"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"
DESCRIPTION_MAX = 6_000
RELEASE_NOTES_MAX = 1_500
# The order a source repository is looked for among an app's URLs.
URL_ORDER = ("vcs-browser", "bugtracker", "homepage", "contribute", "help", "translate")


class FlathubError(RuntimeError):
    """The catalog could not be fetched or read."""


def fetch_catalog(http: httpx2.Client | None = None, trace_dir: Path | None = None) -> bytes:
    """The gzipped catalog bytes; one request, traced to runs/traces/flathub-<date>.jsonl."""
    client = http or httpx2.Client(timeout=120.0, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        resp = client.get(CATALOG, follow_redirects=True)
    except httpx2.TransportError as err:
        raise FlathubError(f"GET {CATALOG}: {type(err).__name__}") from None
    finally:
        if http is None:
            client.close()
    _trace(trace_dir, {"ts": taipei_now().isoformat(timespec="seconds"), "url": CATALOG,
                       "status": resp.status_code, "bytes": len(resp.content),
                       "last_modified": resp.headers.get("last-modified"),
                       "latency_s": round(time.monotonic() - started, 3)})
    if resp.status_code != 200:
        raise FlathubError(f"GET {CATALOG}: HTTP {resp.status_code}")
    return resp.content


def _trace(trace_dir: Path | None, record: dict[str, Any]) -> None:
    path = (trace_dir or runs_dir() / "traces") / f"flathub-{taipei_date()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(record) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _untranslated(parent: ET.Element, tag: str) -> list[ET.Element]:
    return [e for e in parent.findall(tag) if e.get(LANG) is None]


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    text = " ".join("".join(element.itertext()).split())
    return text or None


def description_text(element: ET.Element | None) -> str | None:
    """An AppStream description (p, ul/ol of li) as plain text: paragraphs and '- ' items."""
    if element is None:
        return None
    lines = []
    for child in element:
        if child.get(LANG) is not None:
            continue
        if child.tag in ("ul", "ol"):
            lines += [f"- {t}" for li in child.findall("li") if li.get(LANG) is None and (t := _text(li))]
        elif t := _text(child):
            lines.append(t)
    return "\n".join(lines) or _text(element)


def _release_time(release: ET.Element) -> datetime | None:
    stamp, date = release.get("timestamp"), release.get("date")
    try:
        if stamp:
            return datetime.fromtimestamp(int(stamp), UTC)
        if date:
            parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        return None
    return None


def to_listing(component: ET.Element) -> Listing | None:
    """One component as a Listing; None for anything that has no id or name."""
    app_id = (component.findtext("id") or "").strip()
    names = _untranslated(component, "name")
    name = _text(names[0]) if names else None
    if not app_id or not name:
        return None
    summaries = _untranslated(component, "summary")
    descriptions = _untranslated(component, "description")
    urls = {u.get("type"): (u.text or "").strip() for u in component.findall("url") if u.text}
    github = github_repo(*(urls.get(t) for t in URL_ORDER))
    upstream = urls.get("vcs-browser") or (f"https://github.com/{github}" if github else None)
    releases = []
    found = component.find("releases")
    for r in (found if found is not None else []):
        when = _release_time(r)
        if when is not None and r.get("type", "stable") == "stable":
            releases.append((when, r))
    releases.sort(key=lambda pair: pair[0], reverse=True)
    newest = releases[0] if releases else None
    notes = description_text(newest[1].find("description")) if newest else None
    custom = {v.get("key"): (v.text or "") for v in component.iter("value")}
    developer = component.find("developer")
    kind = {"desktop-application": "gui", "desktop": "gui"}.get(component.get("type") or "", "other")
    keywords = [k.text.strip() for kw in _untranslated(component, "keywords") for k in kw.findall("keyword")
                if k.get(LANG) is None and k.text and k.text.strip()]
    return Listing(
        source=SOURCE, item_id=app_id, name=name, url=APP_PAGE.format(app_id), kind=kind,
        summary=_text(summaries[0]) if summaries else None,
        description=(description_text(descriptions[0]) or "")[:DESCRIPTION_MAX] or None if descriptions else None,
        license=(component.findtext("project_license") or "").strip() or None,
        homepage=urls.get("homepage"), upstream=upstream, github=github,
        released_at=newest[0].isoformat(timespec="seconds").replace("+00:00", "Z") if newest else None,
        version=newest[1].get("version") if newest else None,
        install_command=f"flatpak install flathub {app_id}", run_command=f"flatpak run {app_id}",
        facts={
            "developer": _text(developer.find("name")) if developer is not None else
                         (component.findtext("developer_name") or "").strip() or None,
            "categories": [c.text for c in component.findall("categories/category") if c.text],
            "keywords": keywords[:20],
            "urls": urls,
            "release_notes": (notes or "")[:RELEASE_NOTES_MAX] or None,
            "runtime": (component.find("bundle").get("runtime") if component.find("bundle") is not None
                        else None),
            "verified_developer": custom.get("flathub::verification::verified") == "true",
        })


def parse_catalog(data: bytes) -> list[Listing]:
    """Every desktop application and console application in the catalog."""
    try:
        root = ET.parse(io.BytesIO(gzip.decompress(data))).getroot()
    except (OSError, EOFError, ET.ParseError) as err:
        raise FlathubError(f"catalog: {err}") from None
    out = []
    for component in root.findall("component"):
        if component.get("type") not in ("desktop-application", "desktop", "console-application"):
            continue
        listing = to_listing(component)
        if listing is not None:
            out.append(listing)
    return out
