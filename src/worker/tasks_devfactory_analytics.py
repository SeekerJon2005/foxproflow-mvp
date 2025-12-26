# -*- coding: utf-8 -*-
# file: src/worker/tasks_devfactory_analytics.py
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

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


def _parse_dt(dt: Optional[str]) -> Tuple[date, Optional[str], Optional[str]]:
    """
    Accepts:
      - YYYY-MM-DD
      - YYYY-MM-DDTHH:MM:SS...
      - fallback: today()
    Returns: (target_date, dt_input, dt_fallback_reason)
    """
    if not dt:
        return (date.today(), None, None)
    s = str(dt).strip()
    if not s:
        return (date.today(), dt, "empty_string")

    try:
        return (date.fromisoformat(s), s, None)
    except ValueError:
        pass

    try:
        return (datetime.fromisoformat(s).date(), s, "datetime_input_truncated_to_date")
    except ValueError:
        pass

    if len(s) >= 10:
        try:
            return (date.fromisoformat(s[:10]), s, "non_iso_input_used_first_10_chars")
        except ValueError:
            pass

    return (date.today(), s, "invalid_dt_fallback_to_today")


@shared_task(
    name="analytics.devfactory.daily",
    bind=True,
    acks_late=True,
    ignore_result=False,
)
def analytics_devfactory_daily(self, dt: str | None = None) -> Dict[str, Any]:
    """
    Суточный KPI-срез DevFactory.

    DB contract:
      - function: dev.refresh_devfactory_kpi_daily(date)
      - table:    dev.devfactory_kpi_daily(dt, tasks_total, tasks_with_changes, ...)
    """
    target_date, dt_input, dt_fallback_reason = _parse_dt(dt)
    task_id = getattr(getattr(self, "request", None), "id", None)
    ts0 = datetime.now(timezone.utc).isoformat()

    t0 = time.perf_counter()
    conn = _connect_pg()
    try:
        tasks_total: int | None = None
        tasks_with_changes: int | None = None

        stmt_timeout_ms = _env_int("FF_DEVFACTORY_KPI_STMT_TIMEOUT_MS", 0)
        lock_timeout_ms = _env_int("FF_DEVFACTORY_KPI_LOCK_TIMEOUT_MS", 0)

        with conn.cursor() as cur:
            if stmt_timeout_ms and stmt_timeout_ms > 0:
                cur.execute("SET LOCAL statement_timeout = %s;", (int(stmt_timeout_ms),))
            if lock_timeout_ms and lock_timeout_ms > 0:
                cur.execute("SET LOCAL lock_timeout = %s;", (int(lock_timeout_ms),))

            # refresh
            cur.execute("SELECT dev.refresh_devfactory_kpi_daily(%s);", (target_date,))

            # read back
            cur.execute(
                """
                SELECT tasks_total, tasks_with_changes
                FROM dev.devfactory_kpi_daily
                WHERE dt = %s;
                """,
                (target_date,),
            )
            row = cur.fetchone()
            if row:
                if row[0] is not None:
                    tasks_total = int(row[0])
                if row[1] is not None:
                    tasks_with_changes = int(row[1])

        conn.commit()

        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "analytics.devfactory.daily: ok dt=%s tasks_total=%s tasks_with_changes=%s latency_ms=%s task_id=%s",
            target_date,
            tasks_total,
            tasks_with_changes,
            latency_ms,
            task_id,
        )

        return {
            "ok": True,
            "ts": ts0,
            "task_id": task_id,
            "dt": str(target_date),
            "dt_input": dt_input,
            "dt_fallback_reason": dt_fallback_reason,
            "tasks_total": tasks_total,
            "tasks_with_changes": tasks_with_changes,
            "latency_ms": latency_ms,
        }

    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.exception("analytics.devfactory.daily failed dt=%s task_id=%s: %s", target_date, task_id, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "ts": ts0,
            "task_id": task_id,
            "dt": str(target_date),
            "dt_input": dt_input,
            "dt_fallback_reason": dt_fallback_reason,
            "error": str(e),
            "latency_ms": latency_ms,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
