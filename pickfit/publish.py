"""`pickfit publish`: validate data/software, build the Worker's index, deploy.

Architecture F.1 #4: bad data never reaches a deploy. Every check runs
before anything is written, and any problem refuses the whole publish:

- a record fails software.v1 (build_index validates every file);
- no record is listed;
- the records are test fixtures (slug ``fixture-*`` or a repo on ``.invalid``);
- data/software has uncommitted changes, so the deploy would not match a
  commit (``--allow-dirty`` skips this one check);
- wrangler.jsonc still has the placeholder D1 id or no ALLOWED_HOSTS (for
  ``--env NAME``, in its ``env.NAME`` section: wrangler does not inherit
  vars or D1 bindings into an environment).

Then the index is written to worker/src/generated/index.json and
``npx wrangler deploy [--env NAME]`` runs in worker/. ``--dry-run`` runs every
check and prints the plan, including the deployment's settings, without
writing a file or calling wrangler.

Deployments differ only by wrangler.jsonc settings (TOOLS, MATCH_MODE, the
Meta caps), never by code: a frozen evaluation deployment is an env that is
not published again while the evaluation runs.

Remote D1 migrations and the MODEL_API_KEY secret are separate steps
(worker/README.md, deploy checklist).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHOWN_VARS = ("TOOLS", "MATCH_MODE", "META_DAILY_CAP_USD", "META_TOTAL_CAP_USD")
from urllib.parse import urlparse

from pickfit.index import DEFAULT_DATA_DIR, REPO_ROOT, IndexBuildError, build_index, write_index

DEFAULT_WORKER_DIR = REPO_ROOT / "worker"
INDEX_PATH = Path("src") / "generated" / "index.json"
DEPLOY_COMMAND = ["npx", "wrangler", "deploy"]
PLACEHOLDER_DB_ID = re.compile(r"^0{8}-0{4}-0{4}-0{4}-0{12}$")


@dataclass
class Plan:
    problems: list[str] = field(default_factory=list)
    index: dict[str, Any] | None = None
    commit: str | None = None
    vars: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def strip_jsonc(text: str) -> str:
    """JSONC -> JSON: drop // and /* */ comments outside strings, then trailing commas."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def check_wrangler(worker_dir: Path, env: str | None = None) -> tuple[list[str], dict[str, Any]]:
    """(problems, vars) of the top-level config, or of its env.<env> section."""
    path = worker_dir / "wrangler.jsonc"
    try:
        config = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as err:
        return [f"{path}: cannot read ({err})"], {}
    where = "wrangler.jsonc"
    if env:
        where = f"wrangler.jsonc env.{env}"
        config = config.get("env", {}).get(env)
        if not isinstance(config, dict):
            return [f"wrangler.jsonc: no env.{env} section"], {}
    variables = config.get("vars", {})
    problems: list[str] = []
    db = next((d for d in config.get("d1_databases", []) if d.get("binding") == "DB"), None)
    if not db:
        problems.append(f"{where}: no D1 binding DB")
    elif not db.get("database_id") or PLACEHOLDER_DB_ID.match(db["database_id"]):
        problems.append(f"{where}: database_id is still the placeholder; run `wrangler d1 create <name>` and put its id there")
    if not str(variables.get("ALLOWED_HOSTS", "")).strip():
        problems.append(f"{where}: ALLOWED_HOSTS is empty; set the workers.dev host name, or every remote request gets 403")
    return problems, variables


def fixture_entries(index: dict[str, Any]) -> list[str]:
    """Slugs that are test fixtures: they must never be deployed."""
    return [
        e["slug"]
        for e in index["entries"]
        if e["slug"].startswith("fixture-") or (urlparse(e["repo_url"]).hostname or "").endswith(".invalid")
    ]


def git_state(data_dir: Path) -> tuple[str | None, list[str]]:
    """(HEAD commit, uncommitted paths under data_dir); raises CalledProcessError outside a repository."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=data_dir, check=True, capture_output=True, text=True
        ).stdout

    head = git("rev-parse", "--short", "HEAD").strip() or None
    dirty = [line[3:] for line in git("status", "--porcelain", "--untracked-files=all", "--", ".").splitlines()]
    return head, dirty


def plan(
    data_dir: Path = DEFAULT_DATA_DIR,
    worker_dir: Path = DEFAULT_WORKER_DIR,
    allow_dirty: bool = False,
    env: str | None = None,
) -> Plan:
    result = Plan()
    try:
        built = build_index(data_dir)
    except IndexBuildError as err:
        result.problems += err.problems
    else:
        result.index = built.index
        if built.index["count"] == 0:
            result.problems.append(f"no listed records under {data_dir}")
        fixtures = fixture_entries(built.index)
        if fixtures:
            result.problems.append(f"test fixtures must not be deployed: {', '.join(fixtures[:5])}")
    dirty: list[str] = []
    if data_dir.is_dir():  # a missing directory is already a build problem
        try:
            result.commit, dirty = git_state(data_dir)
        except (subprocess.CalledProcessError, OSError):
            if not allow_dirty:
                result.problems.append(f"{data_dir} is not in a git repository, so the deploy would match no commit")
    if dirty and not allow_dirty:
        result.problems.append(
            f"{len(dirty)} uncommitted file(s) under {data_dir} (e.g. {dirty[0]}); commit them first or pass --allow-dirty"
        )
    problems, result.vars = check_wrangler(worker_dir, env)
    result.problems += problems
    return result


def publish(
    data_dir: Path = DEFAULT_DATA_DIR,
    worker_dir: Path = DEFAULT_WORKER_DIR,
    *,
    dry_run: bool = False,
    allow_dirty: bool = False,
    env: str | None = None,
    out=print,
) -> int:
    p = plan(data_dir, worker_dir, allow_dirty, env)
    if not p.ok:
        out(f"publish: refusing to deploy, {len(p.problems)} problem(s):")
        for problem in p.problems:
            out(f"- {problem}")
        return 1
    assert p.index is not None
    index_path = worker_dir / INDEX_PATH
    command = DEPLOY_COMMAND + (["--env", env] if env else [])
    out(
        f"publish: {p.index['count']} listed entries from {p.index['data_dir']} "
        f"(data sha256 {p.index['data_sha256'][:12]}, commit {p.commit or 'none'})"
    )
    shown = ", ".join(f"{name}={p.vars.get(name, '(default)')}" for name in SHOWN_VARS)
    out(f"publish: {'env ' + env if env else 'top-level'} settings: {shown}")
    if dry_run:
        out(f"publish: dry run; would write {index_path}")
        out(f"publish: dry run; would run `{' '.join(command)}` in {worker_dir}")
        return 0
    write_index(p.index, index_path)
    out(f"publish: wrote {index_path}; running `{' '.join(command)}` in {worker_dir}")
    return subprocess.run(command, cwd=worker_dir).returncode
