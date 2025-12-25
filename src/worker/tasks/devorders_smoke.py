# -*- coding: utf-8 -*-
# file: src/worker/tasks/devorders_smoke.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from celery import shared_task

log = logging.getLogger(__name__)


def _db_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    auth = f":{pwd}" if pwd else ""
    return f"postgresql://{user}{auth}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # fallback psycopg2
        return psycopg.connect(dsn)


@shared_task(name="devorders.smoke.db_contract")
def devorders_smoke_db_contract() -> Dict[str, Any]:
    """
    Smoke for DevOrders DB contract:
      - dev.dev_order exists
      - dev.v_dev_order_commercial_ctx exists
      - INSERT minimal row works and view returns it
    """
    ok = False
    details: Dict[str, Any] = {}

    with _pg() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('dev.dev_order') IS NOT NULL;")
            has_table = bool(cur.fetchone()[0])
            cur.execute("SELECT to_regclass('dev.v_dev_order_commercial_ctx') IS NOT NULL;")
            has_view = bool(cur.fetchone()[0])

            details["has_table"] = has_table
            details["has_view"] = has_view

            if not (has_table and has_view):
                conn.rollback()
                return {"ok": False, **details}

            # insert minimal (title,status). rollback at end (no pollution)
            cur.execute(
                "INSERT INTO dev.dev_order (title, status) VALUES (%s, %s) RETURNING dev_order_id;",
                ("smoke", "new"),
            )
            dev_order_id = int(cur.fetchone()[0])
            details["dev_order_id"] = dev_order_id

            cur.execute(
                "SELECT 1 FROM dev.v_dev_order_commercial_ctx WHERE dev_order_id=%s LIMIT 1;",
                (dev_order_id,),
            )
            details["view_has_row"] = cur.fetchone() is not None

            ok = bool(details["view_has_row"])

        # rollback to keep DB clean
        conn.rollback()

    return {"ok": ok, **details}
