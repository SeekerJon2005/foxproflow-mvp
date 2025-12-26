# -*- coding: utf-8 -*-
# file: src/worker/tasks_planner_kpi.py
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from celery import shared_task

from src.worker.pg_connect import _connect_pg

log = logging.getLogger(__name__)


def _env_int(name: str, default: int = 0) -> int:
    v = os.getenv(name, "")
    if v == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _call_if_exists(cur, regproc: str, call_sql: str) -> bool:
    """
    regproc example: planner.kpi_snapshot()
    call_sql example: SELECT planner.kpi_snapshot();
    """
    cur.execute("SELECT to_regprocedure(%s);", (regproc,))
    row = cur.fetchone()
    if not row or row[0] is None:
        return False
    cur.execute(call_sql)
    return True


@shared_task(name="planner.kpi.snapshot", bind=True, acks_late=True, ignore_result=False)
def planner_kpi_snapshot(self) -> Dict[str, Any]:
    """
    Captures a KPI snapshot into planner.kpi_snapshots (prefer DB-side function if present).

    Prefer:
      - SELECT planner.kpi_snapshot();
    Fallback:
      - insert minimal payload into planner.kpi_snapshots(payload)
    """
    task_id = getattr(getattr(self, "request", None), "id", None)
    ts0 = datetime.now(timezone.utc).isoformat()

    t0 = time.perf_counter()
    conn = _connect_pg()
    try:
        stmt_timeout_ms = _env_int("FF_PLANNER_KPI_STMT_TIMEOUT_MS", 0)
        lock_timeout_ms = _env_int("FF_PLANNER_KPI_LOCK_TIMEOUT_MS", 0)

        did_call = False
        did_fallback_insert = False

        with conn.cursor() as cur:
            if stmt_timeout_ms and stmt_timeout_ms > 0:
                cur.execute("SET LOCAL statement_timeout = %s;", (int(stmt_timeout_ms),))
            if lock_timeout_ms and lock_timeout_ms > 0:
                cur.execute("SET LOCAL lock_timeout = %s;", (int(lock_timeout_ms),))

            # try DB-side function
            did_call = _call_if_exists(cur, "planner.kpi_snapshot()", "SELECT planner.kpi_snapshot();")

            if not did_call:
                # fallback: insert minimal payload if table exists
                cur.execute("SELECT to_regclass('planner.kpi_snapshots');")
                r = cur.fetchone()
                if r and r[0] is not None:
                    cur.execute(
                        "INSERT INTO planner.kpi_snapshots(payload) VALUES (%s::jsonb);",
                        ('{"source":"celery","note":"fallback_insert"}',),
                    )
                    did_fallback_insert = True

        conn.commit()

        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "planner.kpi.snapshot: ok latency_ms=%s task_id=%s (db_func=%s fallback_insert=%s)",
            latency_ms,
            task_id,
            did_call,
            did_fallback_insert,
        )
        return {
            "ok": True,
            "ts": ts0,
            "task_id": task_id,
            "db_func_used": did_call,
            "fallback_insert": did_fallback_insert,
            "latency_ms": latency_ms,
        }

    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.exception("planner.kpi.snapshot failed task_id=%s: %s", task_id, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "ts": ts0, "task_id": task_id, "error": str(e), "latency_ms": latency_ms}
    finally:
        try:
            conn.close()
        except Exception:
            pass


@shared_task(name="planner.kpi.daily_refresh", bind=True, acks_late=True, ignore_result=False)
def planner_kpi_daily_refresh(self) -> Dict[str, Any]:
    """
    Refreshes planner.planner_kpi_daily (prefer DB-side function if present).

    Prefer:
      - SELECT planner.kpi_daily_refresh();
    Fallback:
      - REFRESH MATERIALIZED VIEW planner.planner_kpi_daily;
    """
    task_id = getattr(getattr(self, "request", None), "id", None)
    ts0 = datetime.now(timezone.utc).isoformat()

    t0 = time.perf_counter()
    conn = _connect_pg()
    try:
        stmt_timeout_ms = _env_int("FF_PLANNER_KPI_DAILY_STMT_TIMEOUT_MS", 0)
        lock_timeout_ms = _env_int("FF_PLANNER_KPI_DAILY_LOCK_TIMEOUT_MS", 0)

        did_call = False
        did_refresh_mv = False

        with conn.cursor() as cur:
            if stmt_timeout_ms and stmt_timeout_ms > 0:
                cur.execute("SET LOCAL statement_timeout = %s;", (int(stmt_timeout_ms),))
            if lock_timeout_ms and lock_timeout_ms > 0:
                cur.execute("SET LOCAL lock_timeout = %s;", (int(lock_timeout_ms),))

            # try DB-side function first
            did_call = _call_if_exists(cur, "planner.kpi_daily_refresh()", "SELECT planner.kpi_daily_refresh();")

            if not did_call:
                # fallback: refresh MV if exists
                cur.execute("SELECT to_regclass('planner.planner_kpi_daily');")
                r = cur.fetchone()
                if r and r[0] is not None:
                    cur.execute("REFRESH MATERIALIZED VIEW planner.planner_kpi_daily;")
                    did_refresh_mv = True

        conn.commit()

        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "planner.kpi.daily_refresh: ok latency_ms=%s task_id=%s (db_func=%s mv_refresh=%s)",
            latency_ms,
            task_id,
            did_call,
            did_refresh_mv,
        )
        return {
            "ok": True,
            "ts": ts0,
            "task_id": task_id,
            "db_func_used": did_call,
            "mv_refresh": did_refresh_mv,
            "latency_ms": latency_ms,
        }

    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.exception("planner.kpi.daily_refresh failed task_id=%s: %s", task_id, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "ts": ts0, "task_id": task_id, "error": str(e), "latency_ms": latency_ms}
    finally:
        try:
            conn.close()
        except Exception:
            pass
