# -*- coding: utf-8 -*-
# file: src/worker/tasks_planner_kpi.py
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from src.worker.pg_connect import _connect_pg

logger = logging.getLogger(__name__)

TASK_SNAPSHOT = "planner.kpi.snapshot"
TASK_DAILY_REFRESH = "planner.kpi.daily_refresh"

_task_snapshot_obj = None
_task_daily_obj = None


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if v == "":
        return default
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on", "enable", "enabled"}


def _qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _pick_zeroarg_kpi_snapshot_callable(cur) -> Optional[Tuple[str, str, str]]:
    """
    Find a zero-arg function/procedure like '*kpi*snapshot*'.
    Returns: (schema, name, prokind) where prokind: 'f' function, 'p' procedure.
    """
    cur.execute(
        """
        SELECT n.nspname AS schema_name,
               p.proname AS fn_name,
               p.prokind AS prokind
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.pronargs = 0
          AND p.proname ILIKE '%kpi%'
          AND p.proname ILIKE '%snapshot%'
        ORDER BY
          (n.nspname = 'planner') DESC,
          (n.nspname = 'ops') DESC,
          n.nspname ASC,
          p.proname ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    return (str(row[0]), str(row[1]), str(row[2]))


def _call_zeroarg_callable(cur, schema: str, fn_name: str, prokind: str) -> None:
    ident = f"{_qident(schema)}.{_qident(fn_name)}"
    if prokind == "p":
        cur.execute(f"CALL {ident};")
    else:
        cur.execute(f"SELECT {ident}();")


def _pick_kpi_daily_matview(cur) -> Optional[Tuple[str, str]]:
    """
    Pick a matview like '*kpi*daily*' (prefer schema planner).
    """
    cur.execute(
        """
        SELECT n.nspname AS schema_name,
               c.relname AS relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND c.relname ILIKE '%kpi%'
          AND c.relname ILIKE '%daily%'
        ORDER BY
          (n.nspname = 'planner') DESC,
          c.relname ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    return (str(row[0]), str(row[1]))


def planner_kpi_snapshot(self) -> Dict[str, Any]:
    """
    Hourly KPI snapshot task.

    - ENABLE_PLANNER_KPI_SNAPSHOT=0 -> skipped.
    - Calls best matching DB callable '*kpi*snapshot*' (function/procedure).
    - Controlled NOOP if callable not found.
    """
    task_id = getattr(getattr(self, "request", None), "id", None)
    ts0 = datetime.now(timezone.utc).isoformat()

    if not _env_bool("ENABLE_PLANNER_KPI_SNAPSHOT", True):
        return {"ok": True, "skipped": True, "reason": "disabled_by_env", "ts": ts0, "task_id": task_id}

    t0 = time.perf_counter()
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            pick = _pick_zeroarg_kpi_snapshot_callable(cur)
            if not pick:
                conn.commit()
                logger.warning("%s: no db callable '*kpi*snapshot*' found -> noop", TASK_SNAPSHOT)
                return {"ok": False, "skipped": True, "reason": "no_snapshot_db_callable", "ts": ts0, "task_id": task_id}

            schema, fn_name, prokind = pick
            _call_zeroarg_callable(cur, schema=schema, fn_name=fn_name, prokind=prokind)
            conn.commit()

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info("%s: ok callable=%s.%s kind=%s latency_ms=%s task_id=%s", TASK_SNAPSHOT, schema, fn_name, prokind, latency_ms, task_id)
        return {"ok": True, "ts": ts0, "task_id": task_id, "called": f"{schema}.{fn_name}", "prokind": prokind, "latency_ms": latency_ms}

    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception("%s: failed task_id=%s: %s", TASK_SNAPSHOT, task_id, exc)
        return {"ok": False, "ts": ts0, "task_id": task_id, "error": str(exc), "latency_ms": latency_ms}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def planner_kpi_daily_refresh(self, concurrently: bool = True) -> Dict[str, Any]:
    """
    Daily refresh of KPI matview.

    - ENABLE_PLANNER_KPI_DAILY_REFRESH=0 -> skipped.
    - Finds matview '*kpi*daily*' and runs REFRESH (tries CONCURRENTLY first).
    """
    task_id = getattr(getattr(self, "request", None), "id", None)
    ts0 = datetime.now(timezone.utc).isoformat()

    if not _env_bool("ENABLE_PLANNER_KPI_DAILY_REFRESH", True):
        return {"ok": True, "skipped": True, "reason": "disabled_by_env", "ts": ts0, "task_id": task_id}

    t0 = time.perf_counter()
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            mv = _pick_kpi_daily_matview(cur)
            if not mv:
                conn.commit()
                logger.warning("%s: no matview '*kpi*daily*' found -> noop", TASK_DAILY_REFRESH)
                return {"ok": False, "skipped": True, "reason": "no_daily_matview", "ts": ts0, "task_id": task_id}

            schema, relname = mv
            ident = f"{_qident(schema)}.{_qident(relname)}"

            if concurrently:
                try:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {ident};")
                    conn.commit()
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    logger.info("%s: ok matview=%s.%s mode=concurrently latency_ms=%s task_id=%s", TASK_DAILY_REFRESH, schema, relname, latency_ms, task_id)
                    return {"ok": True, "ts": ts0, "task_id": task_id, "matview": f"{schema}.{relname}", "mode": "concurrently", "latency_ms": latency_ms}
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

            cur.execute(f"REFRESH MATERIALIZED VIEW {ident};")
            conn.commit()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info("%s: ok matview=%s.%s mode=plain latency_ms=%s task_id=%s", TASK_DAILY_REFRESH, schema, relname, latency_ms, task_id)
            return {"ok": True, "ts": ts0, "task_id": task_id, "matview": f"{schema}.{relname}", "mode": "plain", "latency_ms": latency_ms}

    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception("%s: failed task_id=%s: %s", TASK_DAILY_REFRESH, task_id, exc)
        return {"ok": False, "ts": ts0, "task_id": task_id, "error": str(exc), "latency_ms": latency_ms}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def register(app) -> Dict[str, str]:
    """
    Deterministic registration into конкретный Celery app (worker-side).
    This is the key fix for persistent 'unregistered task' issues.
    """
    global _task_snapshot_obj, _task_daily_obj

    if app is None:
        raise RuntimeError("tasks_planner_kpi.register(app): app is None")

    out: Dict[str, str] = {}

    if TASK_SNAPSHOT not in app.tasks:
        _task_snapshot_obj = app.task(name=TASK_SNAPSHOT, bind=True, acks_late=True, ignore_result=False)(planner_kpi_snapshot)
    else:
        _task_snapshot_obj = app.tasks[TASK_SNAPSHOT]
    out["snapshot"] = getattr(_task_snapshot_obj, "name", TASK_SNAPSHOT)

    if TASK_DAILY_REFRESH not in app.tasks:
        _task_daily_obj = app.task(name=TASK_DAILY_REFRESH, bind=True, acks_late=True, ignore_result=False)(planner_kpi_daily_refresh)
    else:
        _task_daily_obj = app.tasks[TASK_DAILY_REFRESH]
    out["daily_refresh"] = getattr(_task_daily_obj, "name", TASK_DAILY_REFRESH)

    return out


__all__ = [
    "register",
    "planner_kpi_snapshot",
    "planner_kpi_daily_refresh",
]
