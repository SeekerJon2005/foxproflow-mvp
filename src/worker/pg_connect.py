from __future__ import annotations

import os
from typing import Any


def _build_pg_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or "").strip()
    if dsn:
        return dsn

    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "")
    pg_host = os.getenv("POSTGRES_HOST", "postgres")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", os.getenv("POSTGRES_DATABASE", "foxproflow"))

    auth = f"{pg_user}:{pg_pass}@" if pg_pass else f"{pg_user}@"
    return f"postgresql://{auth}{pg_host}:{pg_port}/{pg_db}"


def _connect_pg() -> Any:
    """
    Return a sync Postgres connection.
    Tries psycopg (v3) first, then psycopg2.
    """
    dsn = _build_pg_dsn()
    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)
