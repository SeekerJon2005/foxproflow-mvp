# -*- coding: utf-8 -*-
# file: src/api/routers/eri_attention.py
#
# ERI Attention Signal API:
#  - POST /api/eri/attention_signal
#  - GET  /api/eri/attention_signal/recent?limit=...
#
# DB: eri.attention_signal (NDC, динамически по колонкам)

from __future__ import annotations

import os
import json
import uuid
import decimal
import datetime as dt
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException, Depends, Query
from starlette.responses import Response

# --- optional FlowSec gate (temporary, as requested) ---
_DEPS: List[Any] = []
try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
    _DEPS = [Depends(require_policies("devfactory", ["view_tasks"]))]
except Exception:
    _DEPS = []

router = APIRouter(prefix="/api/eri", tags=["eri"], dependencies=_DEPS)

_COLS_CACHE: Optional[Set[str]] = None


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.decode("utf-8", "replace")
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, decimal.Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    return str(obj)


def _json_resp(payload: Any, *, status_code: int = 200) -> Response:
    raw = json.dumps(_to_jsonable(payload), ensure_ascii=False).encode("utf-8")
    return Response(
        content=raw,
        status_code=status_code,
        media_type="application/json",
        headers={"cache-control": "no-store", "content-encoding": "identity"},
    )


def _pg_connect():
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


def _cols(conn) -> Set[str]:
    global _COLS_CACHE
    if _COLS_CACHE is not None:
        return _COLS_CACHE
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='eri' AND table_name='attention_signal'
            """
        )
        _COLS_CACHE = {r[0] for r in (cur.fetchall() or [])}
    return _COLS_CACHE


def _insert_signal(conn, payload: Dict[str, Any]) -> Dict[str, Any]:
    cols = _cols(conn)

    # ожидаемые поля (но вставляем только те, что реально есть)
    signal_type = payload.get("signal_type")
    severity = payload.get("severity")
    message = payload.get("message")
    meta = payload.get("meta")
    snapshot_id = payload.get("snapshot_id")

    if signal_type is None:
        raise HTTPException(status_code=422, detail="signal_type is required")
    if severity is None:
        raise HTTPException(status_code=422, detail="severity is required")
    if message is None:
        raise HTTPException(status_code=422, detail="message is required")

    # нормализация meta
    if meta is None:
        meta = {}
    if not isinstance(meta, (dict, list)):
        meta = {"value": meta}

    fields: List[str] = []
    ph: List[str] = []
    vals: List[Any] = []

    def add(col: str, placeholder: str, val: Any):
        if col in cols:
            fields.append(col)
            ph.append(placeholder)
            vals.append(val)

    # ts/created_at (если есть)
    now = dt.datetime.now(dt.timezone.utc)
    if "ts" in cols and (payload.get("ts") is None):
        add("ts", "%s", now)
    elif "created_at" in cols and (payload.get("created_at") is None):
        add("created_at", "%s", now)

    add("signal_type", "%s", str(signal_type))
    # severity может быть числом/строкой — приводим к int
    add("severity", "%s", int(severity))
    add("message", "%s", str(message))

    if snapshot_id is not None:
        add("snapshot_id", "%s", int(snapshot_id))

    # meta jsonb
    if "meta" in cols:
        add("meta", "%s::jsonb", json.dumps(_to_jsonable(meta), ensure_ascii=False))

    # optional source/version, если есть в схеме
    if "source" in cols and payload.get("source") is not None:
        add("source", "%s", str(payload.get("source")))
    if "version" in cols and payload.get("version") is not None:
        add("version", "%s", str(payload.get("version")))

    if not fields:
        raise HTTPException(status_code=500, detail="eri.attention_signal: no insertable columns discovered")

    returning = [c for c in ("id", "ts", "created_at", "signal_type", "severity", "message", "snapshot_id", "source", "version", "meta") if c in cols]
    if not returning:
        returning = ["id"] if "id" in cols else []

    sql = f"""
        INSERT INTO eri.attention_signal ({", ".join(fields)})
        VALUES ({", ".join(ph)})
        RETURNING {", ".join(returning)}
    """

    with conn.cursor() as cur:
        cur.execute(sql, tuple(vals))
        row = cur.fetchone()

    conn.commit()

    out: Dict[str, Any] = {}
    if row is not None and returning:
        out = {returning[i]: row[i] for i in range(len(returning))}
    return out


@router.post("/attention_signal")
async def create_attention_signal(payload: Dict[str, Any]) -> Response:
    conn = _pg_connect()
    try:
        out = _insert_signal(conn, payload)
        return _json_resp({"ok": True, **out})
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/attention_signal/recent")
async def list_recent_attention_signals(limit: int = Query(50, ge=1, le=500)) -> Response:
    conn = _pg_connect()
    try:
        cols = _cols(conn)

        select_cols = [c for c in ("id", "ts", "created_at", "signal_type", "severity", "message", "snapshot_id", "source", "version", "meta") if c in cols]
        if not select_cols:
            raise HTTPException(status_code=500, detail="eri.attention_signal: no readable columns discovered")

        order_col = "id" if "id" in cols else ("ts" if "ts" in cols else ("created_at" if "created_at" in cols else select_cols[0]))

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM eri.attention_signal
                ORDER BY {order_col} DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cur.fetchall() or []

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({select_cols[i]: r[i] for i in range(len(select_cols))})

        return _json_resp(out)
    finally:
        try:
            conn.close()
        except Exception:
            pass
