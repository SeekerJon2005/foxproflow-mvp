# -*- coding: utf-8 -*-
# file: src/api/routers/devfactory_tasks_ro.py
from __future__ import annotations

import os
import uuid
import decimal
import datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response

# --- optional FlowSec dependency (не должен ломать запуск) ---
_deps: List[Any] = []
try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
    _deps = [Depends(require_policies("devfactory", ["view_tasks"]))]
except Exception:
    _deps = []


def _connect_pg():
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


_COLS_CACHE: Optional[set[str]] = None


def _cols(conn) -> set[str]:
    global _COLS_CACHE
    if _COLS_CACHE is not None:
        return _COLS_CACHE
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='dev' AND table_name='dev_task'
            """
        )
        _COLS_CACHE = {r[0] for r in (cur.fetchall() or [])}
    return _COLS_CACHE


def _to_jsonable(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, bytes):
        try:
            return x.decode("utf-8")
        except Exception:
            return x.decode("utf-8", "replace")
    if isinstance(x, (dt.datetime, dt.date, dt.time)):
        try:
            return x.isoformat()
        except Exception:
            return str(x)
    if isinstance(x, uuid.UUID):
        return str(x)
    if isinstance(x, decimal.Decimal):
        # безопасно для JSON
        try:
            return float(x)
        except Exception:
            return str(x)
    if isinstance(x, dict):
        return {str(k): _to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_to_jsonable(v) for v in x]
    return str(x)


def _json_response(payload: Any, status_code: int = 200) -> Response:
    import json
    raw = json.dumps(_to_jsonable(payload), ensure_ascii=False).encode("utf-8")
    return Response(content=raw, media_type="application/json", status_code=status_code)


def _select_cols(cols: set[str], *, include_specs: bool, include_result: bool) -> List[str]:
    base = [
        "id",
        "public_id",
        "stack",
        "status",
        "title",
        "flowmind_plan_id",
        "flowmind_plan_domain",
        "autofix_enabled",
        "autofix_status",
        "created_at",
    ]
    out = [c for c in base if c in cols]

    if include_specs and ("input_spec" in cols):
        out.append("input_spec")
    if include_result and ("result_spec" in cols):
        out.append("result_spec")

    if "id" not in out:
        out = ["id"]
    return out


router = APIRouter(prefix="/devfactory", tags=["devfactory"], dependencies=_deps)


@router.get("/tasks", summary="List DevTasks (read-only)")
def list_tasks(
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    stack: Optional[str] = Query(None),
    include_specs: int = Query(0, ge=0, le=1),
    include_result: int = Query(0, ge=0, le=1),
):
    conn = _connect_pg()
    try:
        cols = _cols(conn)
        select_cols = _select_cols(cols, include_specs=bool(include_specs), include_result=bool(include_result))

        where = []
        params: List[Any] = []
        if status and ("status" in cols):
            where.append("status = %s")
            params.append(status)
        if stack and ("stack" in cols):
            where.append("stack = %s")
            params.append(stack)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        order_col = "created_at" if "created_at" in cols else "id"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM dev.dev_task
                {where_sql}
                ORDER BY {order_col} DESC
                LIMIT %s
                """,
                (*params, int(limit)),
            )
            rows = cur.fetchall() or []

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({select_cols[i]: r[i] for i in range(len(select_cols))})

        return _json_response(out)
    finally:
        conn.close()


@router.get("/tasks/{task_id}", summary="Get DevTask by id (read-only)")
def get_task(
    task_id: int,
    include_specs: int = Query(1, ge=0, le=1),
    include_result: int = Query(1, ge=0, le=1),
):
    conn = _connect_pg()
    try:
        cols = _cols(conn)
        select_cols = _select_cols(cols, include_specs=bool(include_specs), include_result=bool(include_result))

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM dev.dev_task
                WHERE id = %s
                """,
                (int(task_id),),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="DevTask not found")

        out = {select_cols[i]: row[i] for i in range(len(select_cols))}
        return _json_response(out)
    finally:
        conn.close()
