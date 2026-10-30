"""One shared spending ledger for every pickfit process, session and worktree.

Meta's Spend Limit only sends email, so caps are enforced here. The ledger is a
SQLite file outside the repo (`~/.pickfit/ledger.sqlite`, override with
PICKFIT_LEDGER). Each paid request first reserves a worst-case cost inside a
`BEGIN IMMEDIATE` transaction, so parallel processes cannot both pass the same
cap check, and is settled to the actual cost once the response arrives.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pickfit.env import get_env

# Taiwan has no daylight saving time, so a fixed offset is exact and needs no tzdata.
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
DEFAULT_PATH = Path.home() / ".pickfit" / "ledger.sqlite"

# What counts against a cap: the reservation while a call is open, the actual cost after.
_SPEND = "COALESCE(SUM(CASE WHEN status = 'reserved' THEN reserved_usd ELSE cost_usd END), 0)"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    budget TEXT NOT NULL,
    run_id TEXT,
    stage TEXT,
    scope TEXT,
    provider TEXT,
    model TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    reserved_usd REAL NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    web_searches INTEGER NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    response_id TEXT
);
CREATE INDEX IF NOT EXISTS calls_budget_day ON calls (budget, day);
CREATE INDEX IF NOT EXISTS calls_budget_scope ON calls (budget, scope);
CREATE INDEX IF NOT EXISTS calls_response_id ON calls (response_id);
"""

TOKEN_FIELDS = ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens", "web_searches")


class BudgetExceeded(RuntimeError):
    """Raised before a request is sent when it could push spending past a cap."""

    def __init__(self, cap: str, limit_usd: float, spent_usd: float, needed_usd: float) -> None:
        self.cap = cap
        self.limit_usd = limit_usd
        self.spent_usd = spent_usd
        self.needed_usd = needed_usd
        super().__init__(
            f"{cap} cap ${limit_usd:.2f} would be exceeded: "
            f"spent ${spent_usd:.4f} + this call up to ${needed_usd:.4f}"
        )


def pipeline_daily_cap(day: date) -> float:
    """$3 a day before 2026-10-29 (validation), $25 from then on; $80 on 10/31 and $45 on 11/1-11/2 (plan section 2)."""
    if day < date(2026, 10, 29):
        return 3.0
    if day == date(2026, 10, 31):
        return 80.0
    return 45.0 if date(2026, 11, 1) <= day <= date(2026, 11, 2) else 25.0


@dataclass(frozen=True)
class Caps:
    total_usd: float
    daily_usd: Callable[[date], float]


PIPELINE_TOTAL_USD = 115.0
PIPELINE_CAPS = Caps(total_usd=PIPELINE_TOTAL_USD, daily_usd=pipeline_daily_cap)


def pipeline_caps() -> Caps:
    """PIPELINE_CAPS, with the total lowered by PICKFIT_PIPELINE_TOTAL_CAP_USD when it is set.

    The setting can only lower the total: a machine with its own ledger (the Windows host) gets a
    small hard stop of its own, and nothing can raise the shared one.
    """
    raw = get_env("PICKFIT_PIPELINE_TOTAL_CAP_USD")
    if raw is None:
        return PIPELINE_CAPS
    lowered = float(raw)  # a typo meant to lower the cap fails loudly instead of being ignored
    if not 0 <= lowered <= PIPELINE_TOTAL_USD:
        raise ValueError(f"PICKFIT_PIPELINE_TOTAL_CAP_USD must be between 0 and {PIPELINE_TOTAL_USD:g}")
    return Caps(total_usd=lowered, daily_usd=pipeline_daily_cap)
# Baseten's hackathon credits are separate from Meta's, so they get their own budget in the same
# file. $100 of credits, $80 hard stop: the account has a card on file that is charged past them.
BASETEN_CAPS = Caps(total_usd=80.0, daily_usd=lambda day: 25.0)


def taipei_now(clock: Callable[[], datetime] | None = None) -> datetime:
    return (clock or (lambda: datetime.now(UTC)))().astimezone(TAIPEI)


def taipei_date(clock: Callable[[], datetime] | None = None) -> str:
    """Today's date in Taipei as YYYY-MM-DD; daily caps and trace files use it."""
    return taipei_now(clock).date().isoformat()


class Ledger:
    """Spending ledger for one budget ("pipeline") inside a shared SQLite file."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        budget: str = "pipeline",
        caps: Caps = PIPELINE_CAPS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self.budget = budget
        self.caps = caps
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One write transaction that holds the database write lock from the start."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _spent(self, conn: sqlite3.Connection, where: str = "", params: tuple = ()) -> float:
        sql = f"SELECT {_SPEND} FROM calls WHERE budget = ?{where}"
        return float(conn.execute(sql, (self.budget, *params)).fetchone()[0])

    def reserve(
        self,
        estimate_usd: float,
        *,
        run_id: str | None = None,
        stage: str | None = None,
        scope: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        attempt: int = 1,
        scope_cap_usd: float | None = None,
    ) -> int:
        """Check every cap and hold `estimate_usd`; return the row id to settle later.

        `scope_cap_usd` limits what `scope` may spend within this `run_id`, so the same
        scope (e.g. "verify:<slug>") gets the full cap again in a later run.
        """
        if estimate_usd < 0:
            raise ValueError("estimate_usd must not be negative")
        now = taipei_now(self.clock)
        day = now.date()
        with self._write() as conn:
            checks = [
                ("daily", self.caps.daily_usd(day), self._spent(conn, " AND day = ?", (day.isoformat(),))),
                ("total", self.caps.total_usd, self._spent(conn)),
            ]
            if scope_cap_usd is not None:
                if not scope:
                    raise ValueError("scope_cap_usd needs a scope")
                scope_spent = self._spent(conn, " AND scope = ? AND run_id IS ?", (scope, run_id))
                checks.append((f"scope {scope}", scope_cap_usd, scope_spent))
            for name, limit, spent in checks:
                if spent + estimate_usd > limit + 1e-9:
                    raise BudgetExceeded(name, limit, spent, estimate_usd)
            cur = conn.execute(
                "INSERT INTO calls (ts, day, budget, run_id, stage, scope, provider, model,"
                " attempt, status, reserved_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?)",
                (now.isoformat(), day.isoformat(), self.budget, run_id, stage, scope, provider,
                 model, attempt, estimate_usd),
            )
            return int(cur.lastrowid)

    def settle(
        self,
        row_id: int,
        cost_usd: float,
        *,
        tokens: Mapping[str, int] | None = None,
        response_id: str | None = None,
        status: str = "settled",
    ) -> None:
        """Replace a reservation with the actual cost (0 for a request that was not billed)."""
        counts = {f: int((tokens or {}).get(f) or 0) for f in TOKEN_FIELDS}
        assignments = ", ".join(f"{f} = ?" for f in TOKEN_FIELDS)
        with self._write() as conn:
            conn.execute(
                f"UPDATE calls SET status = ?, cost_usd = ?, response_id = ?, {assignments} "
                "WHERE id = ? AND budget = ?",
                (status, cost_usd, response_id, *counts.values(), row_id, self.budget),
            )

    def release(self, row_id: int, status: str = "error") -> None:
        """Drop a reservation for a request that failed without being billed."""
        self.settle(row_id, 0.0, status=status)

    def record_cache_hit(
        self,
        *,
        run_id: str | None = None,
        stage: str | None = None,
        scope: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tokens: Mapping[str, int] | None = None,
        response_id: str | None = None,
    ) -> int:
        """Log a call served from the dev cache: free, so no cap check."""
        now = taipei_now(self.clock)
        counts = {f: int((tokens or {}).get(f) or 0) for f in TOKEN_FIELDS}
        columns = ", ".join(TOKEN_FIELDS)
        marks = ", ".join("?" for _ in TOKEN_FIELDS)
        with self._write() as conn:
            cur = conn.execute(
                "INSERT INTO calls (ts, day, budget, run_id, stage, scope, provider, model, status,"
                f" cache_hit, response_id, {columns})"
                f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'cache', 1, ?, {marks})",
                (now.isoformat(), now.date().isoformat(), self.budget, run_id, stage, scope,
                 provider, model, response_id, *counts.values()),
            )
            return int(cur.lastrowid)

    def context_tokens(self, response_id: str) -> int | None:
        """Input + output tokens recorded for a response: the context a chained call carries."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT input_tokens + output_tokens FROM calls WHERE response_id = ?"
                " AND status IN ('settled', 'cache') ORDER BY id DESC LIMIT 1",
                (response_id,),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else None

    def spend_summary(self) -> dict[str, Any]:
        """Today (Taipei), total, open reservations, and spend by model and by stage."""
        today = taipei_now(self.clock).date()
        conn = self._connect()
        try:
            def grouped(column: str) -> dict[str, float]:
                rows = conn.execute(
                    f"SELECT COALESCE({column}, '?'), {_SPEND} FROM calls WHERE budget = ? "
                    f"GROUP BY 1 ORDER BY 2 DESC",
                    (self.budget,),
                ).fetchall()
                return {str(k): round(v, 6) for k, v in rows}

            calls, cache_hits, open_usd = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(cache_hit), 0), "
                "COALESCE(SUM(CASE WHEN status = 'reserved' THEN reserved_usd END), 0) "
                "FROM calls WHERE budget = ?",
                (self.budget,),
            ).fetchone()
            tokens = conn.execute(
                "SELECT " + ", ".join(f"COALESCE(SUM({f}), 0)" for f in TOKEN_FIELDS)
                + " FROM calls WHERE budget = ? AND cache_hit = 0",
                (self.budget,),
            ).fetchone()
            return {
                "budget": self.budget,
                "today": today.isoformat(),
                "today_usd": round(self._spent(conn, " AND day = ?", (today.isoformat(),)), 6),
                "daily_cap_usd": self.caps.daily_usd(today),
                "total_usd": round(self._spent(conn), 6),
                "total_cap_usd": self.caps.total_usd,
                "open_reservations_usd": round(float(open_usd), 6),
                "calls": int(calls),
                "cache_hits": int(cache_hits),
                "billed_tokens": dict(zip(TOKEN_FIELDS, map(int, tokens))),
                "by_model": grouped("model"),
                "by_stage": grouped("stage"),
            }
        finally:
            conn.close()


def default_ledger() -> Ledger:
    """The shared ledger: PICKFIT_LEDGER if set, else ~/.pickfit/ledger.sqlite."""
    return Ledger(get_env("PICKFIT_LEDGER") or DEFAULT_PATH, caps=pipeline_caps())


def baseten_ledger() -> Ledger:
    """The Baseten budget in the shared ledger file (prescreen calls on Muse Spark Open)."""
    return Ledger(get_env("PICKFIT_LEDGER") or DEFAULT_PATH, budget="baseten", caps=BASETEN_CAPS)
