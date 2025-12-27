# -*- coding: utf-8 -*-
"""
DevFactory • Commercial task runner
file: src/worker/tasks/devfactory_commercial.py

Celery task:
  - devfactory.commercial.run_order

Важно:
- Этот модуль должен существовать всегда, потому что celery_app ожидает его в safe import list.
- Не должен падать на import-time (даже если нет драйвера Postgres в локальном Python).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import platform
import socket
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

try:
    import psycopg  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None  # type: ignore

try:
    import psycopg2  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None  # type: ignore

from src.worker.celery_app import app

log = logging.getLogger(__name__)
TASK_NAME = "devfactory.commercial.run_order"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _env_first(*names: str, default: Optional[str] = None) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v is not None and str(v).strip() != "":
            return str(v)
    return default


def _db_driver_name() -> Optional[str]:
    if psycopg is not None:
        return "psycopg"
    if psycopg2 is not None:
        return "psycopg2"
    return None


def _db_driver():
    drv = _db_driver_name()
    if drv == "psycopg":
        return psycopg  # type: ignore[return-value]
    if drv == "psycopg2":
        return psycopg2  # type: ignore[return-value]
    raise RuntimeError(
        "No Postgres driver installed (psycopg or psycopg2). "
        "Run worker in Docker image with dependencies or install psycopg[binary]."
    )


def _db_connect_timeout_s() -> int:
    raw = _env_first("FF_DB_CONNECT_TIMEOUT_S", "POSTGRES_CONNECT_TIMEOUT", "DB_CONNECT_TIMEOUT", default="5") or "5"
    try:
        v = int(str(raw).strip())
    except Exception:
        v = 5
    return max(1, min(60, v))


def _db_target_info() -> Dict[str, Any]:
    url = _env_first("DATABASE_URL", "DB_DSN", "POSTGRES_DSN")
    if url:
        try:
            u = urlparse(url)
            db = (u.path or "").lstrip("/") or None
            return {
                "source": "dsn",
                "scheme": u.scheme or None,
                "host": u.hostname or None,
                "port": int(u.port) if u.port else None,
                "db": db,
                "user": u.username or None,
                "has_password": bool(u.password),
            }
        except Exception:
            return {"source": "dsn", "parse_error": True}

    user = _env_first("POSTGRES_USER", "DB_USER", "PGUSER", default="admin") or "admin"
    db = _env_first("POSTGRES_DB", "DB_NAME", "PGDATABASE", default="foxproflow") or "foxproflow"
    host = _env_first("POSTGRES_HOST", "DB_HOST", "PGHOST", default="postgres") or "postgres"
    port = _env_first("POSTGRES_PORT", "DB_PORT", "PGPORT", default="5432") or "5432"
    password = _env_first("POSTGRES_PASSWORD", "DB_PASSWORD", "PGPASSWORD", default="") or ""
    try:
        port_i = int(str(port).strip())
    except Exception:
        port_i = None

    return {
        "source": "parts",
        "host": host,
        "port": port_i,
        "db": db,
        "user": user,
        "has_password": bool(password),
    }


def _db_dsn() -> str:
    url = _env_first("DATABASE_URL", "DB_DSN", "POSTGRES_DSN")
    if url:
        return url

    user = _env_first("POSTGRES_USER", "DB_USER", "PGUSER", default="admin") or "admin"
    password = _env_first("POSTGRES_PASSWORD", "DB_PASSWORD", "PGPASSWORD", default="") or ""
    db = _env_first("POSTGRES_DB", "DB_NAME", "PGDATABASE", default="foxproflow") or "foxproflow"
    host = _env_first("POSTGRES_HOST", "DB_HOST", "PGHOST", default="postgres") or "postgres"
    port = _env_first("POSTGRES_PORT", "DB_PORT", "PGPORT", default="5432") or "5432"

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return f"postgresql://{user}@{host}:{port}/{db}"


def _db_connect():
    drv = _db_driver()
    return drv.connect(_db_dsn(), connect_timeout=_db_connect_timeout_s())


def _table_columns(conn, schema: str, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema=%s AND table_name=%s
            """,
            (schema, table),
        )
        return {r[0] for r in (cur.fetchall() or [])}


def _update_dev_task(conn, dev_task_id: int, *, status: str, result_spec: Optional[dict], error: Optional[str]) -> None:
    cols = _table_columns(conn, "dev", "dev_task")
    sets = []
    params: Dict[str, Any] = {"id": dev_task_id}

    if "status" in cols:
        sets.append("status=%(status)s")
        params["status"] = status

    if "result_spec" in cols and result_spec is not None:
        sets.append("result_spec=%(result_spec)s::jsonb")
        params["result_spec"] = _json_dumps(result_spec)

    if "error" in cols:
        sets.append("error=%(error)s")
        params["error"] = error

    if "updated_at" in cols:
        sets.append("updated_at=now()")
    if "finished_at" in cols:
        sets.append("finished_at=now()")
    if "completed_at" in cols:
        sets.append("completed_at=now()")

    if not sets:
        return

    sql = "UPDATE dev.dev_task SET " + ", ".join(sets) + " WHERE id=%(id)s"
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _db_check_relations(conn, rels: list[str]) -> dict:
    out: Dict[str, bool] = {}
    with conn.cursor() as cur:
        for rel in rels:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (rel,))
            out[rel] = bool(cur.fetchone()[0])
    return out


def _versions() -> dict:
    def _ver(modname: str) -> Optional[str]:
        try:
            m = __import__(modname)
            return getattr(m, "__version__", None)
        except Exception:
            return None

    versions = {
        "python": platform.python_version(),
        "celery": _ver("celery"),
        "psycopg": _ver("psycopg"),
        "psycopg2": _ver("psycopg2"),
        "sqlalchemy": _ver("sqlalchemy"),
    }
    return {k: v for k, v in versions.items() if v is not None}


def stand_diagnostics_v1(*, correlation_id: Optional[str] = None, task_id: Optional[str] = None) -> dict:
    t0 = time.perf_counter()
    report: Dict[str, Any] = {
        "ok": True,
        "order_type": "stand_diagnostics_v1",
        "report_head": "stand_diagnostics: ok",
        "ts_utc": _utc_now_iso(),
        "latency_ms": None,
        "missing": [],
        "versions": _versions(),
        "host": {"hostname": socket.gethostname(), "service_role": os.environ.get("SERVICE_ROLE", "") or ""},
        "celery": {"task_id": task_id or "", "task_name": TASK_NAME},
        "correlation_id": correlation_id or "",
        "db": {"ok": False, "driver": _db_driver_name(), "target": _db_target_info(), "missing": [], "checks": {}, "details": {}},
    }

    if _db_driver_name() is None:
        report["ok"] = False
        report["report_head"] = "stand_diagnostics: dependency_missing"
        report["db"]["error"] = "db driver missing"
        report["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        return report

    try:
        with _db_connect() as conn:
            try:
                conn.autocommit = True
            except Exception:
                pass
            report["db"]["ok"] = True
            report["db"]["checks"] = _db_check_relations(
                conn,
                ["dev.dev_order", "dev.dev_task", "dev.v_dev_order_commercial_ctx", "ops.audit_events"],
            )
            with conn.cursor() as cur:
                cur.execute("SELECT now(), current_database(), current_user, version()")
                now, db, db_user, version = cur.fetchone()
                report["db"]["details"] = {"now": str(now), "db": str(db), "db_user": str(db_user), "server_version": str(version)}
            report["db"]["missing"] = [k for k, ok in (report["db"]["checks"] or {}).items() if not ok]
    except Exception as e:
        report["ok"] = False
        report["report_head"] = "stand_diagnostics: db_error"
        report["db"]["ok"] = False
        report["db"]["error"] = f"{type(e).__name__}: {e}"

    report["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return report


def _parse_args_kwargs(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Optional[int], Optional[str], dict, Optional[str]]:
    dev_task_id = kwargs.get("dev_task_id")
    order_type = kwargs.get("order_type")
    payload = kwargs.get("payload") or {}
    correlation_id = kwargs.get("correlation_id")

    if dev_task_id is None and len(args) >= 1 and isinstance(args[0], int):
        dev_task_id = args[0]
        if order_type is None and len(args) >= 2 and isinstance(args[1], str):
            order_type = args[1]
        if (not payload) and len(args) >= 3 and isinstance(args[2], dict):
            payload = args[2]
        if correlation_id is None and len(args) >= 4 and isinstance(args[3], str):
            correlation_id = args[3]

    try:
        dev_task_id_int = int(dev_task_id) if dev_task_id is not None else None
    except Exception:
        dev_task_id_int = None

    if not isinstance(payload, dict):
        payload = {"_raw_payload": payload}

    if correlation_id is not None and not isinstance(correlation_id, str):
        correlation_id = str(correlation_id)

    return dev_task_id_int, order_type, payload, correlation_id


@app.task(name=TASK_NAME, bind=True)
def run_order(self, *args: Any, **kwargs: Any) -> dict:
    dev_task_id, order_type, payload, correlation_id = _parse_args_kwargs(args, dict(kwargs))
    t0 = time.perf_counter()

    task_id = ""
    try:
        task_id = str(getattr(getattr(self, "request", None), "id", "") or "")
    except Exception:
        task_id = ""

    cid = (correlation_id or "").strip() or task_id or ""

    # mark running (best effort)
    if dev_task_id is not None and _db_driver_name() is not None:
        try:
            with _db_connect() as conn:
                try:
                    conn.autocommit = True
                except Exception:
                    pass
                _update_dev_task(conn, dev_task_id, status="running", result_spec=None, error=None)
        except Exception as e:
            log.warning("%s: cannot mark running (dev_task_id=%s): %s", TASK_NAME, dev_task_id, f"{type(e).__name__}: {e}")

    try:
        if order_type == "stand_diagnostics_v1":
            result = stand_diagnostics_v1(correlation_id=cid, task_id=task_id)
        else:
            result = {
                "ok": False,
                "order_type": order_type or "",
                "report_head": "order: unknown order_type",
                "ts_utc": _utc_now_iso(),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "missing": [],
                "correlation_id": cid,
                "celery": {"task_id": task_id, "task_name": TASK_NAME},
                "error": f"unknown order_type: {order_type!r}",
            }

        result.setdefault("latency_ms", int((time.perf_counter() - t0) * 1000))
        result.setdefault("correlation_id", cid)
        result.setdefault("celery", {"task_id": task_id, "task_name": TASK_NAME})

        # persist result (best effort)
        if dev_task_id is not None and _db_driver_name() is not None:
            try:
                with _db_connect() as conn:
                    try:
                        conn.autocommit = True
                    except Exception:
                        pass
                    ok = bool(result.get("ok"))
                    _update_dev_task(
                        conn,
                        dev_task_id,
                        status="done" if ok else "failed",
                        result_spec=result,
                        error=None if ok else (result.get("error") or "order failed"),
                    )
            except Exception as e:
                log.exception("%s: cannot persist result (dev_task_id=%s): %s", TASK_NAME, dev_task_id, f"{type(e).__name__}: {e}")

        return result

    except Exception as e:
        if dev_task_id is not None and _db_driver_name() is not None:
            try:
                with _db_connect() as conn:
                    try:
                        conn.autocommit = True
                    except Exception:
                        pass
                    _update_dev_task(
                        conn,
                        dev_task_id,
                        status="failed",
                        result_spec={"ok": False, "error": f"{type(e).__name__}: {e}", "correlation_id": cid},
                        error=f"{type(e).__name__}: {e}",
                    )
            except Exception:
                pass
        raise
