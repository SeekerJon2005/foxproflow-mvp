# -*- coding: utf-8 -*-
# file: src/worker/tasks_planner_kpi.py
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.worker.pg_connect import _connect_pg

log = logging.getLogger(__name__)

TASK_SNAPSHOT = "planner.kpi.snapshot"
TASK_DAILY = "planner.kpi.daily_refresh"


def _env_int(name: str, default: int = 0) -> int:
    v = os.getenv(name, "")
    if v == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_id(self) -> Optional[str]:
    try:
        return getattr(getattr(self, "request", None), "id", None)
    except Exception:
        return None


def _set_local_timeouts(cur) -> None:
    """
    Optional timeouts:
      - FF_PLANNER_KPI_STMT_TIMEOUT_MS
      - FF_PLANNER_KPI_LOCK_TIMEOUT_MS
    """
    stmt_timeout_ms = _env_int("FF_PLANNER_KPI_STMT_TIMEOUT_MS", 0)
    lock_timeout_ms = _env_int("FF_PLANNER_KPI_LOCK_TIMEOUT_MS", 0)
    if stmt_timeout_ms and stmt_timeout_ms > 0:
        cur.execute("SET LOCAL statement_timeout = %s;", (int(stmt_timeout_ms),))
    if lock_timeout_ms and lock_timeout_ms > 0:
        cur.execute("SET LOCAL lock_timeout = %s;", (int(lock_timeout_ms),))


def planner_kpi_snapshot(self) -> Dict[str, Any]:
    """
    Inserts KPI snapshot into planner.kpi_snapshots by calling SQL function planner.kpi_snapshot().
    """
    ts0 = _utc_now_iso()
    t0 = time.perf_counter()
    tid = _task_id(self)

    conn = _connect_pg()
    try:
        snapshots_cnt: int | None = None
        last_ts: Optional[str] = None

        with conn.cursor() as cur:
            _set_local_timeouts(cur)

            # Core snapshot function
            cur.execute("SELECT planner.kpi_snapshot();")

            # Small observability payload
            cur.execute("SELECT count(*) FROM planner.kpi_snapshots;")
            row = cur.fetchone()
            if row and row[0] is not None:
                snapshots_cnt = int(row[0])

            cur.execute("SELECT max(ts) FROM planner.kpi_snapshots;")
            row2 = cur.fetchone()
            if row2 and row2[0] is not None:
                # keep as string for JSON
                last_ts = str(row2[0])

        conn.commit()
        latency_ms = int((time.perf_counter() - t0) * 1000)

        log.info(
            "%s: ok snapshots_cnt=%s last_ts=%s latency_ms=%s task_id=%s",
            TASK_SNAPSHOT,
            snapshots_cnt,
            last_ts,
            latency_ms,
            tid,
        )
        return {
            "ok": True,
            "ts": ts0,
            "task_id": tid,
            "task": TASK_SNAPSHOT,
            "snapshots_cnt": snapshots_cnt,
            "last_ts": last_ts,
            "latency_ms": latency_ms,
        }
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.exception("%s: failed task_id=%s: %s", TASK_SNAPSHOT, tid, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "ts": ts0,
            "task_id": tid,
            "task": TASK_SNAPSHOT,
            "error": str(e),
            "latency_ms": latency_ms,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def planner_kpi_daily_refresh(self) -> Dict[str, Any]:
    """
    Refreshes MV planner.planner_kpi_daily (non-CONCURRENT for determinism).
    """
    ts0 = _utc_now_iso()
    t0 = time.perf_counter()
    tid = _task_id(self)

    conn = _connect_pg()
    try:
        rows: int | None = None
        with conn.cursor() as cur:
            _set_local_timeouts(cur)

            # Deterministic refresh (CONCURRENT has restrictions; keep it simple for Gate)
            cur.execute("REFRESH MATERIALIZED VIEW planner.planner_kpi_daily;")
            cur.execute("SELECT count(*) FROM planner.planner_kpi_daily;")
            r = cur.fetchone()
            if r and r[0] is not None:
                rows = int(r[0])

        conn.commit()
        latency_ms = int((time.perf_counter() - t0) * 1000)

        log.info("%s: ok rows=%s latency_ms=%s task_id=%s", TASK_DAILY, rows, latency_ms, tid)
        return {
            "ok": True,
            "ts": ts0,
            "task_id": tid,
            "task": TASK_DAILY,
            "rows": rows,
            "latency_ms": latency_ms,
        }
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.exception("%s: failed task_id=%s: %s", TASK_DAILY, tid, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "ts": ts0,
            "task_id": tid,
            "task": TASK_DAILY,
            "error": str(e),
            "latency_ms": latency_ms,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def register(app: Any) -> None:
    """
    Register tasks explicitly to the passed Celery app.
    This avoids shared_task binding ambiguity and guarantees presence in `inspect registered`.
    """
    try:
        tasks = getattr(app, "tasks", {})
        if TASK_SNAPSHOT not in tasks:
            app.task(name=TASK_SNAPSHOT, bind=True, acks_late=True, ignore_result=False)(planner_kpi_snapshot)
        if TASK_DAILY not in tasks:
            app.task(name=TASK_DAILY, bind=True, acks_late=True, ignore_result=False)(planner_kpi_daily_refresh)
    except Exception:
        log.exception("tasks_planner_kpi.register failed")


__all__ = ["register", "planner_kpi_snapshot", "planner_kpi_daily_refresh"]
