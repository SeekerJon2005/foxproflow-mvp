# -*- coding: utf-8 -*-
# file: src/core/pg_conn.py
from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name, "")
        return int(str(v).strip()) if str(v).strip() != "" else default
    except Exception:
        return default


def build_pg_dsn() -> str:
    """
    Единая точка сборки DSN для Postgres.
    NDC: читает DATABASE_URL если задан, иначе строит из POSTGRES_*.
    """
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn

    pg_user = os.getenv("POSTGRES_USER", os.getenv("POSTGRES_USERNAME", "admin"))
    pg_pass = os.getenv("POSTGRES_PASSWORD", os.getenv("POSTGRES_PASS", ""))
    pg_host = os.getenv("POSTGRES_HOST", "postgres")
    pg_port = _env_int("POSTGRES_PORT", 5432)
    pg_db = os.getenv("POSTGRES_DB", os.getenv("POSTGRES_DATABASE", "foxproflow"))

    auth = f"{pg_user}:{pg_pass}@" if pg_pass else f"{pg_user}@"
    return f"postgresql://{auth}{pg_host}:{pg_port}/{pg_db}"


def connect_pg() -> Any:
    """
    Возвращает psycopg3 connection если доступен, иначе psycopg2.
    Импорт драйверов внутри функции — модуль import-safe.
    """
    dsn = build_pg_dsn()
    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


def _connect_pg() -> Any:
    # Back-compat имя для текущих вызовов
    return connect_pg()
