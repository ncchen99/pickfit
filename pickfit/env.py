"""Read selected settings from the process environment or the repo-root `.env`.

Only the names a caller asks for are returned. Nothing is exported to
`os.environ` and values are never logged, so a key needed by one module does
not leak into child processes (for example ANTHROPIC_API_KEY into `claude`).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"


def _parse_line(line: str) -> tuple[str, str] | None:
    """Parse one `KEY=VALUE` line; return None for blanks, comments and junk."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    key, sep, value = line.partition("=")
    key = key.strip()
    if not sep or not key.isidentifier():
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    elif " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return key, value


def _read_dotenv(names: set[str], path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed and parsed[0] in names:
            found[parsed[0]] = parsed[1]
    return found


def read_env(names: Iterable[str], path: Path | None = None) -> dict[str, str]:
    """Return the requested variables that are set; the process env wins over `.env`."""
    wanted = set(names)
    values = {n: os.environ[n] for n in wanted if os.environ.get(n)}
    missing = wanted - values.keys()
    if missing:
        for key, value in _read_dotenv(missing, path or DOTENV_PATH).items():
            if value:
                values[key] = value
    return values


def get_env(name: str, default: str | None = None, path: Path | None = None) -> str | None:
    """Return one variable, or `default` when it is unset or empty."""
    return read_env([name], path).get(name, default)


def require_env(name: str, path: Path | None = None) -> str:
    """Return one variable or raise; the error names the variable, never a value."""
    value = get_env(name, path=path)
    if value is None:
        raise RuntimeError(f"{name} is not set (process environment or {DOTENV_PATH.name})")
    return value
