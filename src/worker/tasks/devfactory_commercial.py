# -*- coding: utf-8 -*-
# file: src/worker/tasks/devfactory_commercial.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from celery import shared_task

from src.core.stand_diagnostics import collect_stand_diagnostics

log = logging.getLogger(__name__)


# ----------------------------- DB helpers -----------------------------

_DEV_TASK_COLS: Optional[Set[str]] = None
_DEV_ORDER_COLS: Optional[Set[str]] = None


def _db_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")

    auth = f"{user}:{pwd}" if pwd else user
    return f"postgresql://{auth}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore

        conn = psycopg.connect(dsn)
        try:
            conn.autocommit = False
        except Exception:
            pass
        return conn


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _table_cols(conn, schema: str, table: str) -> Set[str]:
    key = f"{schema}.{table}"
    global _DEV_TASK_COLS, _DEV_ORDER_COLS

    if key == "dev.dev_task" and _DEV_TASK_COLS is not None:
        return _DEV_TASK_COLS
    if key == "dev.dev_order" and _DEV_ORDER_COLS is not None:
        return _DEV_ORDER_COLS

    cols: Set[str] = set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (schema, table),
        )
        for r in (cur.fetchall() or []):
            cols.add(str(r[0]))

    if key == "dev.dev_task":
        _DEV_TASK_COLS = cols
    if key == "dev.dev_order":
        _DEV_ORDER_COLS = cols

    return cols


def _col_udt_name(conn, schema: str, table: str, column: str) -> Optional[str]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT udt_name
                FROM information_schema.columns
                WHERE table_schema=%s AND table_name=%s AND column_name=%s
                """,
                (schema, table, column),
            )
            row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def _json_placeholder_for(conn, schema: str, table: str, column: str) -> str:
    udt = (_col_udt_name(conn, schema, table, column) or "").lower()
    if udt == "json":
        return "%s::json"
    return "%s::jsonb"


def _task_job_id_expr(cols: Set[str]) -> Optional[str]:
    parts: List[str] = []
    if "links" in cols:
        parts.append("links::jsonb->>'celery_job_id'")
    if "meta" in cols:
        parts.append("meta::jsonb->>'celery_job_id'")
    if "input_spec" in cols:
        parts.append("input_spec::jsonb->>'celery_job_id'")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "COALESCE(" + ", ".join(parts) + ")"


def _task_order_id_expr(cols: Set[str]) -> Optional[str]:
    parts: List[str] = []
    if "meta" in cols:
        parts.append("meta::jsonb->>'dev_order_id'")
    if "input_spec" in cols:
        parts.append("input_spec::jsonb->>'dev_order_id'")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "COALESCE(" + ", ".join(parts) + ")"


def _task_order_type_expr(cols: Set[str]) -> Optional[str]:
    parts: List[str] = []
    if "meta" in cols:
        parts.append("meta::jsonb->>'order_type'")
    if "input_spec" in cols:
        parts.append("input_spec::jsonb->>'order_type'")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "COALESCE(" + ", ".join(parts) + ")"


def _find_dev_task_id(conn, *, dev_order_id: str, order_type: str, job_id: Optional[str]) -> Optional[int]:
    cols = _table_cols(conn, "dev", "dev_task")
    order_expr = _task_order_id_expr(cols)
    type_expr = _task_order_type_expr(cols)
    job_expr = _task_job_id_expr(cols)

    try:
        with conn.cursor() as cur:
            # Prefer job_id match (most precise)
            if job_id and job_expr:
                cur.execute(
                    f"""
                    SELECT id
                      FROM dev.dev_task
                     WHERE {job_expr} = %s
                     ORDER BY COALESCE(updated_at, created_at, now()) DESC, id DESC
                     LIMIT 1
                    """,
                    (str(job_id),),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

            # Fallback: by dev_order_id + order_type
            if order_expr and type_expr:
                cur.execute(
                    f"""
                    SELECT id
                      FROM dev.dev_task
                     WHERE {order_expr} = %s
                       AND {type_expr}  = %s
                     ORDER BY COALESCE(updated_at, created_at, now()) DESC, id DESC
                     LIMIT 1
                    """,
                    (str(dev_order_id), str(order_type)),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])

            # Last fallback: only by dev_order_id
            if order_expr:
                cur.execute(
                    f"""
                    SELECT id
                      FROM dev.dev_task
                     WHERE {order_expr} = %s
                     ORDER BY COALESCE(updated_at, created_at, now()) DESC, id DESC
                     LIMIT 1
                    """,
                    (str(dev_order_id),),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception as e:
        log.warning("devfactory.commercial: cannot locate dev_task_id: %s", e)

    return None


def _merge_jsonb_expr(col: str, json_param_placeholder: str, *, cast_to_json: bool) -> str:
    # col = COALESCE(col::jsonb,'{}') || (%s::jsonb)
    base = f"COALESCE({col}::jsonb, '{{}}'::jsonb) || ({json_param_placeholder}::jsonb)"
    return f"({base})::json" if cast_to_json else f"({base})::jsonb"


def _update_dev_task(
    conn,
    *,
    dev_task_id: int,
    status: Optional[str] = None,
    result_spec: Optional[Dict[str, Any]] = None,
    error_text: Optional[str] = None,
    meta_patch: Optional[Dict[str, Any]] = None,
) -> None:
    cols = _table_cols(conn, "dev", "dev_task")
    set_parts: List[str] = []
    params: List[Any] = []

    if status and "status" in cols:
        set_parts.append("status = %s")
        params.append(str(status))

    if error_text is not None and "error" in cols:
        set_parts.append("error = %s")
        params.append(str(error_text) if error_text else None)

    if result_spec is not None and "result_spec" in cols:
        ph = _json_placeholder_for(conn, "dev", "dev_task", "result_spec")
        set_parts.append(f"result_spec = {ph}")
        params.append(_json_dumps(result_spec))

    if meta_patch and "meta" in cols:
        udt = (_col_udt_name(conn, "dev", "dev_task", "meta") or "jsonb").lower()
        set_parts.append(f"meta = {_merge_jsonb_expr('meta', '%s', cast_to_json=(udt=='json'))}")
        params.append(_json_dumps(meta_patch))

    if "updated_at" in cols:
        set_parts.append("updated_at = now()")

    if not set_parts:
        return

    params.append(int(dev_task_id))
    sql = f"UPDATE dev.dev_task SET {', '.join(set_parts)} WHERE id = %s"

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
    conn.commit()


def _update_dev_order_status(conn, *, dev_order_id: str, status: str) -> None:
    cols = _table_cols(conn, "dev", "dev_order")
    if "status" not in cols:
        return
    try:
        with conn.cursor() as cur:
            # dev_order_id can be int-like; store as text in input_spec, so compare by ::text
            cur.execute(
                "UPDATE dev.dev_order SET status=%s WHERE dev_order_id::text = %s::text",
                (str(status), str(dev_order_id)),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


# ----------------------------- Handlers -----------------------------

def _verify_db_contract_v1(conn) -> Dict[str, Any]:
    t0 = time.monotonic()
    required = [
        "dev.dev_order",
        "dev.dev_task",
        "dev.v_dev_order_commercial_ctx",
        "ops.audit_events",
    ]
    checks: Dict[str, Any] = {}
    missing: List[str] = []

    with conn.cursor() as cur:
        for reg in required:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (reg,))
            ok = bool((cur.fetchone() or [False])[0])
            checks[reg] = ok
            if not ok:
                missing.append(reg)

        try:
            conn.rollback()
        except Exception:
            pass

    ok = (len(missing) == 0)
    ms = int((time.monotonic() - t0) * 1000.0)
    head = "verify_db_contract_v1: ok" if ok else f"verify_db_contract_v1: failed (missing={len(missing)})"

    return {
        "ok": ok,
        "order_type": "verify_db_contract_v1",
        "report_head": head,
        "latency_ms": ms,
        "missing": missing,
        "checks": checks,
    }


def _incident_triage_v1(conn, *, correlation_id: Optional[str]) -> Dict[str, Any]:
    # Minimal “не молчать” stub: структурно, без магии.
    _ = conn
    t0 = time.monotonic()
    ms = int((time.monotonic() - t0) * 1000.0)
    return {
        "ok": True,
        "order_type": "incident_triage_v1",
        "report_head": "incident_triage_v1: ok (stub)",
        "latency_ms": ms,
        "missing": [],
        "triage": {
            "note": "stub_v1 (no log ingestion in air-gapped core yet)",
            "correlation_id": correlation_id,
        },
    }


# ----------------------------- Main Celery task -----------------------------

@shared_task(name="devfactory.commercial.run_order", bind=True)
def devfactory_commercial_run_order(self, dev_order_id: str, order_type: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Commercial DevOrder executor (worker side).
    Required by API: task name MUST be 'devfactory.commercial.run_order'.
    Updates dev.dev_task.result_spec and dev.dev_task.status deterministically.
    """
    t0 = time.monotonic()
    job_id = getattr(getattr(self, "request", None), "id", None)

    conn = _pg()
    try:
        dev_task_id = _find_dev_task_id(conn, dev_order_id=str(dev_order_id), order_type=str(order_type), job_id=str(job_id) if job_id else None)

        # mark running early (best-effort)
        if dev_task_id is not None:
            _update_dev_task(
                conn,
                dev_task_id=int(dev_task_id),
                status="running",
                meta_patch={
                    "order_type": str(order_type),
                    "correlation_id": (str(correlation_id) if correlation_id else None),
                    "celery_job_id": (str(job_id) if job_id else None),
                },
            )

        # execute handler
        if str(order_type) == "stand_diagnostics_v1":
            result = collect_stand_diagnostics(order_type="stand_diagnostics_v1", correlation_id=correlation_id, repo_root="/app")
        elif str(order_type) == "verify_db_contract_v1":
            result = _verify_db_contract_v1(conn)
        elif str(order_type) == "incident_triage_v1":
            result = _incident_triage_v1(conn, correlation_id=correlation_id)
        else:
            result = {
                "ok": False,
                "order_type": str(order_type),
                "report_head": "unknown_order_type",
                "latency_ms": 0,
                "missing": ["order_type"],
                "error": {"code": "UNKNOWN_ORDER_TYPE", "message": f"Unknown order_type: {order_type}"},
            }

        # enforce stable keys (commercial vitrine contract relies on these)
        if "latency_ms" not in result:
            result["latency_ms"] = int((time.monotonic() - t0) * 1000.0)
        result.setdefault("missing", [])
        result.setdefault("order_type", str(order_type))

        # include trace
        result.setdefault("correlation_id", correlation_id)
        result.setdefault("job_id", str(job_id) if job_id else None)
        result.setdefault("dev_order_id", str(dev_order_id))

        ok = bool(result.get("ok") is True)
        final_status = "done" if ok else "failed"
        err_text = None if ok else _json_dumps(result.get("error") or "failed")

        # update DB
        if dev_task_id is not None:
            _update_dev_task(
                conn,
                dev_task_id=int(dev_task_id),
                status=final_status,
                result_spec=result,
                error_text=err_text,
                meta_patch={
                    "order_type": str(order_type),
                    "correlation_id": (str(correlation_id) if correlation_id else None),
                    "celery_job_id": (str(job_id) if job_id else None),
                    "latency_ms": int(result.get("latency_ms") or 0),
                },
            )

        # also set dev_order.status best-effort
        try:
            _update_dev_order_status(conn, dev_order_id=str(dev_order_id), status=final_status)
        except Exception:
            pass

        return result

    except Exception as ex:
        # best-effort failure persistence
        try:
            dev_task_id = _find_dev_task_id(conn, dev_order_id=str(dev_order_id), order_type=str(order_type), job_id=str(job_id) if job_id else None)
            fail_res = {
                "ok": False,
                "order_type": str(order_type),
                "report_head": "devfactory.commercial.run_order: exception",
                "latency_ms": int((time.monotonic() - t0) * 1000.0),
                "missing": [],
                "error": {"code": "RUNTIME_ERROR", "message": f"{type(ex).__name__}: {ex}"},
                "correlation_id": correlation_id,
                "job_id": str(job_id) if job_id else None,
                "dev_order_id": str(dev_order_id),
            }
            if dev_task_id is not None:
                _update_dev_task(conn, dev_task_id=int(dev_task_id), status="failed", result_spec=fail_res, error_text=str(ex))
            try:
                _update_dev_order_status(conn, dev_order_id=str(dev_order_id), status="failed")
            except Exception:
                pass
            return fail_res
        except Exception:
            return {"ok": False, "order_type": str(order_type), "error": {"code": "RUNTIME_ERROR", "message": f"{type(ex).__name__}: {ex}"}}
    finally:
        _safe_close(conn)
