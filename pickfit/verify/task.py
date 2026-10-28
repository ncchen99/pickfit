"""What the verification agent is asked to check, and how a fixture file becomes one.

A fixture is JSON: slug, repo_url, readme_url (pinned to a commit) and an
ExtractionResult. The README is fetched outside the box at run time, so no
third-party README text is stored in this repo.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pickfit.schema import ExtractionResult

README_FETCH_TIMEOUT_S = 30
README_MAX_BYTES = 512_000


@dataclass(frozen=True)
class VerifyTask:
    slug: str
    repo_url: str
    readme: str
    extraction: ExtractionResult
    readme_url: str | None = None


def fetch_readme(url: str) -> str:
    """GET a public README (https only); runs on the host, never in the box."""
    if not url.startswith("https://"):
        raise ValueError(f"readme_url must be https: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": "pickfit-verify"})
    with urllib.request.urlopen(request, timeout=README_FETCH_TIMEOUT_S) as response:
        return response.read(README_MAX_BYTES).decode("utf-8", errors="replace")


def load_fixture(path: Path | str, fetch: Callable[[str], str] = fetch_readme) -> VerifyTask:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    readme = data.get("readme")
    if readme is None:
        readme = fetch(data["readme_url"])
    return VerifyTask(slug=data["slug"], repo_url=data["repo_url"], readme=readme,
                      extraction=ExtractionResult.model_validate(data["extraction"]),
                      readme_url=data.get("readme_url"))
