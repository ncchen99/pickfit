"""The Worker's D1 from the pipeline: `pickfit watch` and `pickfit reverify` read and update it.

The Worker writes the rows (submit_software into `submissions`, report_outcome
into `events` and `reverify_queue`); the pipeline reads them and writes back
statuses. `D1` runs `wrangler d1 execute` in worker/, so wrangler's own login is
used and no token passes through pickfit; only the last lines of a failure are
kept. `--command` takes no bound parameters, so values go in as SQL literals
(`sql()` with ?1, ?2 placeholders, as in the Worker's own queries).

`SqliteD1` has the same two methods on a SQLite file built from
worker/migrations, so tests and local dry runs exercise the real schema and its
CHECK constraints.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pickfit.env import REPO_ROOT

DEFAULT_WORKER_DIR = REPO_ROOT / "worker"
DATABASE = "pickfit"  # wrangler.jsonc d1_databases[].database_name
WRANGLER_TIMEOUT_S = 120
ERROR_TAIL_CHARS = 600

_PLACEHOLDER = re.compile(r"\?(\d+)")
_JSON_START = re.compile(r"^\[\s*[{\]]", re.M)


def timestamp(moment: datetime) -> str:
    """The Worker's format (Date.toISOString): UTC with milliseconds and Z, so text order is time order."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class D1Error(RuntimeError):
    """A D1 statement failed (wrangler error, SQL error, or a reply that is not JSON)."""


def literal(value: Any) -> str:
    """One value as a SQLite literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("D1 literal: not a finite number")
        return repr(value)
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("D1 literal: NUL character")
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"D1 literal: unsupported type {type(value).__name__}")


def sql(template: str, *params: Any) -> str:
    """Fill ?1, ?2, ... with literals. Substituted text is never scanned again."""
    def fill(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if not 1 <= index <= len(params):
            raise ValueError(f"D1 sql: ?{index} has no parameter")
        return literal(params[index - 1])
    return _PLACEHOLDER.sub(fill, template)


class Database(Protocol):
    def query(self, statement: str) -> list[dict[str, Any]]: ...
    def execute(self, statement: str) -> int: ...


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= ERROR_TAIL_CHARS else "…" + text[-ERROR_TAIL_CHARS:]


class D1:
    """One statement per `wrangler d1 execute` call, against the remote database or the local one.

    `remote=False` is the database `wrangler dev` uses (worker/.wrangler/state).
    """

    def __init__(self, *, remote: bool = True, worker_dir: Path = DEFAULT_WORKER_DIR, database: str = DATABASE,
                 env: str | None = None, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self.remote = remote
        self.worker_dir = Path(worker_dir)
        self.database = database
        self.env = env
        self._run = run

    @property
    def where(self) -> str:
        return f"{'remote' if self.remote else 'local'} D1 {self.database}" + (f" (env {self.env})" if self.env else "")

    def _statement(self, statement: str) -> list[dict[str, Any]]:
        command = ["npx", "--no-install", "wrangler", "d1", "execute", self.database,
                   "--remote" if self.remote else "--local", "--json", "--command", statement]
        if self.env:
            command += ["--env", self.env]
        try:
            proc = self._run(command, cwd=self.worker_dir, capture_output=True, text=True, timeout=WRANGLER_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise D1Error(f"{self.where}: wrangler did not run: {type(err).__name__}") from None
        if proc.returncode != 0:
            raise D1Error(f"{self.where}: wrangler exit {proc.returncode}: {_tail(proc.stderr or proc.stdout)}")
        out = proc.stdout
        start = _JSON_START.search(out)  # wrangler may print warnings such as "▲ [WARNING] …" first
        try:
            data = json.loads(out[start.start():]) if start else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, list) or not data:
            raise D1Error(f"{self.where}: reply is not JSON: {_tail(out)}")
        for result in data:
            if not result.get("success", False):
                raise D1Error(f"{self.where}: statement failed: {_tail(json.dumps(result)[:2000])}")
        return data

    def query(self, statement: str) -> list[dict[str, Any]]:
        return list(self._statement(statement)[-1].get("results") or [])

    def execute(self, statement: str) -> int:
        """Rows changed by the statement."""
        return int((self._statement(statement)[-1].get("meta") or {}).get("changes") or 0)


class SqliteD1:
    """The Worker's schema (all of worker/migrations, in order) in a local SQLite file."""

    def __init__(self, path: Path | str, migrations: Path = DEFAULT_WORKER_DIR / "migrations") -> None:
        self.path = Path(path)
        self.where = f"sqlite {self.path.name}"
        fresh = not self.path.exists()
        if fresh:
            with self._connect() as conn:
                for migration in sorted(Path(migrations).glob("*.sql")):
                    conn.executescript(migration.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, statement: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            return [dict(row) for row in conn.execute(statement).fetchall()]
        except sqlite3.Error as err:
            raise D1Error(f"{self.where}: {err}") from None
        finally:
            conn.close()

    def execute(self, statement: str) -> int:
        conn = self._connect()
        try:
            with conn:
                return conn.execute(statement).rowcount
        except sqlite3.Error as err:
            raise D1Error(f"{self.where}: {err}") from None
        finally:
            conn.close()
