"""DB connection helpers. Single place for pooling + URL handling."""

from __future__ import annotations

import atexit
import os
from functools import lru_cache

import psycopg
from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://agent:agentdev@localhost:5432/support"
DEFAULT_AGENT_DATABASE_URL = "postgresql://agent_readonly:readonlydev@localhost:5432/support"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def agent_database_url() -> str:
    """Read-only URL for the agent's run_sql tool. Never use the superuser URL there."""
    return os.environ.get("AGENT_DATABASE_URL", DEFAULT_AGENT_DATABASE_URL)


@lru_cache(maxsize=2)
def _pools() -> dict[str, ConnectionPool]:
    return {}


def pool(readonly: bool = False) -> ConnectionPool:
    """Return a small shared pool. Candidate TODO: tune min/max size + timeouts."""
    key = "ro" if readonly else "rw"
    cached = _pools()
    if key not in cached:
        cached[key] = ConnectionPool(
            database_url() if not readonly else agent_database_url(),
            min_size=1,
            max_size=5,
            timeout=10,
        )
    return cached[key]


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with pool().connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        return list(cur.fetchall())


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with pool().connection() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(query: str, params: tuple = ()) -> int:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        conn.commit()
        return cur.rowcount


def ping(connect_timeout: int = 3) -> None:
    """Fast failure if Postgres is unreachable (avoids slow pool timeouts)."""
    with psycopg.connect(database_url(), connect_timeout=connect_timeout) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")


@atexit.register
def _close_pools() -> None:
    for name, active_pool in _pools().items():
        try:
            active_pool.close()
        except Exception:  # noqa: BLE001, S110 — best effort at shutdown
            pass
