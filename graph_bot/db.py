"""Postgres connection for the analytics warehouse.

The DSN comes from the environment so no credential ever lives in the repo:

    DATABASE_URL=postgresql://user:password@localhost:5432/youtube_db

or the standard libpq pieces (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD).
`.env` is loaded by config.py on import, so either works from a plain shell or
from the dashboard.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from .config import PROJECT_ROOT  # noqa: F401  (imported for its .env side effect)

DEFAULT_DB = "youtube_db"


class NotConfigured(RuntimeError):
    """Raised when no connection details are available at all."""


def dsn() -> str:
    """Build a libpq connection string from the environment."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PGHOST")
    user = os.getenv("PGUSER")
    if not host and not user:
        raise NotConfigured(
            "No database configured. Add DATABASE_URL to .env, e.g.\n"
            f"  DATABASE_URL=postgresql://postgres:YOURPASSWORD@localhost:5432/{DEFAULT_DB}"
        )
    parts = {
        "host": host or "localhost",
        "port": os.getenv("PGPORT", "5432"),
        "dbname": os.getenv("PGDATABASE", DEFAULT_DB),
        "user": user or "postgres",
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        parts["password"] = pw
    return " ".join(f"{k}={v}" for k, v in parts.items())


def safe_dsn() -> str:
    """The DSN with the password blanked, for logs and error messages."""
    raw = dsn()
    if "://" in raw:
        head, _, tail = raw.partition("://")
        creds, at, rest = tail.rpartition("@")
        if at and ":" in creds:
            user = creds.split(":", 1)[0]
            return f"{head}://{user}:***@{rest}"
        return raw
    return " ".join(
        "password=***" if p.startswith("password=") else p for p in raw.split()
    )


@contextmanager
def connect(**kwargs: Any) -> Iterator[Any]:
    """Yield a psycopg connection, committing on clean exit."""
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - install-time guidance
        raise RuntimeError(
            "psycopg is not installed. Run:  pip install \"psycopg[binary]\""
        ) from exc

    kwargs.setdefault("connect_timeout", 10)
    with psycopg.connect(dsn(), **kwargs) as conn:
        yield conn


def ping() -> str:
    """Return the server version, or raise with a readable message."""
    with connect() as conn:
        row = conn.execute("SELECT version()").fetchone()
    return row[0] if row else "unknown"
