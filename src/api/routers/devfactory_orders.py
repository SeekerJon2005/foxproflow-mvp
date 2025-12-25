# -*- coding: utf-8 -*-
# file: src/api/routers/devfactory_orders.py
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
    from api.security.architect_guard import require_architect_key  # type: ignore
except Exception:  # pragma: no cover
    try:
        from src.api.security.flowsec_middleware import require_policies  # type: ignore
        from src.api.security.architect_guard import require_architect_key  # type: ignore
    except Exception:
        require_policies = None  # type: ignore
        require_architect_key = None  # type: ignore

from src.core.context_pack import (
    attach_context_pack_to_dev_task,
    collect_context_pack,
    try_insert_ops_agent_event,
)
from src.core.devfactory.catalog import get_catalog_item
from src.core.errors import ErrorEnvelope, make_error

DF_CELERY_TASK_NAME = "devfactory.commercial.run_order"

# -----------------------------
# Caches
# -----------------------------
_DEV_TASK_COLS: Optional[Set[str]] = None
_DEV_ORDER_COLS: Optional[Set[str]] = None

# -----------------------------
# Env helpers
# -----------------------------
_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


# Enable by setting FF_DEVFACTORY_REQUIRE_WORKER=1 in compose env_file (.env)
FF_DEVFACTORY_REQUIRE_WORKER = _env_bool("FF_DEVFACTORY_REQUIRE_WORKER", False)

# -----------------------------
# Postgres connection helpers
# -----------------------------


def _normalize_dsn(dsn: str) -> str:
    dsn = (dsn or "").strip()
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    return dsn


def _build_pg_dsn() -> str:
    dsn = _normalize_dsn(os.getenv("DATABASE_URL", ""))
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _connect_pg():
    dsn = _build_pg_dsn()
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


# -----------------------------
# DB introspection helpers
# -----------------------------


def _to_regclass(conn, reg: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (reg,))
            row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _table_cols(conn, schema: str, table: str) -> Set[str]:
    cols: Set[str] = set()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (schema, table),
            )
            for (name,) in cur.fetchall() or []:
                cols.add(str(name))
    except Exception:
        return set()
    return cols


def _col_udt_name(conn, schema: str, table: str, column: str) -> Optional[str]:
    """
    udt_name: json/jsonb/uuid/int4/...
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT udt_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                (schema, table, column),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0])
    except Exception:
        return None


def _dev_task_cols(conn, *, force_refresh: bool = False) -> Set[str]:
    global _DEV_TASK_COLS
    if force_refresh:
        _DEV_TASK_COLS = None
    if _DEV_TASK_COLS is not None:
        return _DEV_TASK_COLS
    _DEV_TASK_COLS = _table_cols(conn, "dev", "dev_task")
    return _DEV_TASK_COLS


def _dev_order_cols(conn, *, force_refresh: bool = False) -> Set[str]:
    global _DEV_ORDER_COLS
    if force_refresh:
        _DEV_ORDER_COLS = None
    if _DEV_ORDER_COLS is not None:
        return _DEV_ORDER_COLS
    _DEV_ORDER_COLS = _table_cols(conn, "dev", "dev_order")
    return _DEV_ORDER_COLS


# -----------------------------
# JSON / coercion helpers
# -----------------------------


def _json_dumps(obj: Any) -> str:
    # must never crash on Decimal/datetime/etc (audit + result_spec)
    return json.dumps(obj, ensure_ascii=False, default=str)


def _coerce_id_str(v: Any) -> str:
    """
    Opaque string id (в БД может быть int/uuid/text/bytes).
    """
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            return bytes(v).decode("utf-8", "replace").strip()
        except Exception:
            return str(v).strip()
    return str(v).strip()


def _maybe_int(v: Any) -> Optional[int]:
    try:
        s = _coerce_id_str(v)
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _coerce_json_obj(val: Any) -> Any:
    """
    json/jsonb из DB может вернуться как dict/list или как строка/bytes — приводим по возможности.
    """
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        if isinstance(val, (bytes, bytearray, memoryview)):
            val = bytes(val).decode("utf-8", "replace")
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    return json.loads(s)
                except Exception:
                    return None
    except Exception:
        return None
    return None


def _coerce_json_dict(val: Any) -> Dict[str, Any]:
    obj = _coerce_json_obj(val)
    return obj if isinstance(obj, dict) else {}


# -----------------------------
# Trace extractors (B-M1/B-M2)
# -----------------------------


def _extract_job_id_from_any(val: Any) -> Optional[str]:
    """
    Извлекаем celery_job_id / job_id из dict/строки-json/bytes.
    """
    if not val:
        return None
    try:
        if isinstance(val, dict):
            v = val.get("celery_job_id") or val.get("job_id")
            return str(v).strip() if v else None

        obj = _coerce_json_dict(val)
        if obj:
            v = obj.get("celery_job_id") or obj.get("job_id")
            return str(v).strip() if v else None

        return None
    except Exception:
        return None


def _extract_int_field_from_any(val: Any, field: str) -> Optional[int]:
    obj = val if isinstance(val, dict) else _coerce_json_dict(val)
    if not obj:
        return None
    v = obj.get(field)
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _extract_str_field_from_any(val: Any, field: str) -> Optional[str]:
    obj = val if isinstance(val, dict) else _coerce_json_dict(val)
    if not obj:
        return None
    v = obj.get(field)
    if v is None:
        return None
    try:
        s = str(v).strip()
        return s if s else None
    except Exception:
        return None


def _extract_retry_of_from_any(val: Any) -> Optional[int]:
    """
    Извлекаем retry_of_dev_task_id из dict/строки-json/bytes.
    """
    return _extract_int_field_from_any(val, "retry_of_dev_task_id")


def _extract_order_type_from_any(val: Any) -> Optional[str]:
    """
    Извлекаем order_type из dict/строки-json/bytes.
    """
    return _extract_str_field_from_any(val, "order_type")


def _extract_trace_fields(*vals: Any) -> Dict[str, Any]:
    """
    Коммерческий trace: job_id, order_type, retry_of_dev_task_id.
    Приоритет — порядок vals (передавай links/meta/input_spec/result_spec).
    """
    job_id: Optional[str] = None
    order_type: Optional[str] = None
    retry_of: Optional[int] = None

    for v in vals:
        if job_id is None:
            job_id = _extract_job_id_from_any(v)
        if order_type is None:
            order_type = _extract_order_type_from_any(v)
        if retry_of is None:
            retry_of = _extract_retry_of_from_any(v)

        if job_id is not None and order_type is not None and retry_of is not None:
            break

    return {"job_id": job_id, "order_type": order_type, "retry_of_dev_task_id": retry_of}


def _json_placeholder_for(conn, schema: str, table: str, column: str) -> str:
    """
    Возвращает плейсхолдер для json/jsonb: "%s::json" или "%s::jsonb".
    По умолчанию jsonb.
    """
    udt = _col_udt_name(conn, schema, table, column) or "jsonb"
    return "%s::json" if udt == "json" else "%s::jsonb"


# -----------------------------
# Validation / linkage helpers
# -----------------------------


def _validate_order_id_str(oid: str, *, correlation_id: Optional[str]) -> Optional[JSONResponse]:
    v = (oid or "").strip()
    if not v:
        return _err(
            400,
            make_error(
                code="INVALID_DEV_ORDER_ID",
                message="dev_order_id is empty.",
                remediation="Передай dev_order_id из ответа POST /api/devfactory/orders.",
                missing_inputs=["dev_order_id"],
                correlation_id=correlation_id,
            ),
            kind="validation",
            correlation_id=correlation_id,
        )
    if len(v) > 128:
        return _err(
            400,
            make_error(
                code="INVALID_DEV_ORDER_ID",
                message="dev_order_id is too long.",
                remediation="Передай корректный идентификатор заказа (как вернул API).",
                missing_inputs=["dev_order_id"],
                correlation_id=correlation_id,
            ),
            kind="validation",
            correlation_id=correlation_id,
        )
    return None


def _task_order_link_expr(cols: Set[str]) -> Optional[str]:
    """
    Link DevTask -> DevOrder:
      - prefer meta->>'dev_order_id'
      - fallback input_spec->>'dev_order_id'
    """
    if "meta" in cols:
        return "(meta->>'dev_order_id')"
    if "input_spec" in cols:
        return "(input_spec->>'dev_order_id')"
    return None


# -----------------------------
# Audit helpers (best-effort)
# -----------------------------


def _evidence_refs(*pairs: Tuple[str, Optional[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for kind, value in pairs:
        v = (value or "").strip()
        if v:
            out.append({"kind": str(kind), "value": v})
    return out


def _order_payload_summary(body: "DevOrderCreateIn") -> Dict[str, Any]:
    p = body.payload or {}
    keys = sorted([str(k) for k in p.keys()])[:50]
    payload_bytes = 0
    try:
        payload_bytes = len(_json_dumps(p).encode("utf-8"))
    except Exception:
        payload_bytes = 0

    cc = (body.currency_code or "").strip()
    return {
        "order_type": body.order_type,
        "title": (body.title or "").strip() or None,
        "customer_name": (body.customer_name or "").strip() or None,
        "tenant_external_id": (body.tenant_external_id or "").strip() or None,
        "total_amount": body.total_amount,
        "currency_code": (cc.upper() if cc else None),
        "payload_key_count": int(len(p)),
        "payload_keys": keys,
        "payload_bytes": int(payload_bytes),
    }


def _try_insert_audit_event(
    conn,
    *,
    actor: str,
    action: str,
    ok: bool,
    dev_order_id_int: Optional[int] = None,
    dev_task_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
    evidence_refs: Optional[List[Dict[str, Any]]] = None,
    err: Optional[str] = None,
) -> None:
    """
    Monetization audit trail (best-effort): ops.audit_events.
    Не ломает заказ, если таблицы нет или insert не удался.
    """
    if not _to_regclass(conn, "ops.audit_events"):
        return

    p = payload or {}
    refs = evidence_refs or []
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO ops.audit_events
                    (actor, action, ok, dev_order_id, dev_task_id, payload, evidence_refs, err)
                VALUES
                    (%s, %s, %s, %s, %s,
                     {_json_placeholder_for(conn, "ops", "audit_events", "payload")},
                     {_json_placeholder_for(conn, "ops", "audit_events", "evidence_refs")},
                     %s)
                """,
                (
                    str(actor),
                    str(action),
                    bool(ok),
                    int(dev_order_id_int) if dev_order_id_int is not None else None,
                    int(dev_task_id) if dev_task_id is not None else None,
                    _json_dumps(p),
                    _json_dumps(refs),
                    (str(err) if err else None),
                ),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _fetch_dev_order_public_id(conn, *, dev_order_id: str) -> Optional[str]:
    """
    Если в dev.dev_order есть dev_order_public_id и dev_order_id — int, возвращаем public id.
    """
    cols = _dev_order_cols(conn, force_refresh=False)
    if "dev_order_public_id" not in cols:
        return None

    oid = _maybe_int(dev_order_id)
    if oid is None:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT dev_order_public_id FROM dev.dev_order WHERE dev_order_id = %s", (int(oid),))
            row = cur.fetchone()
        if row and row[0] is not None:
            return _coerce_id_str(row[0]) or None
    except Exception:
        return None

    return None


def _fetch_dev_order_id_by_public_id(conn, *, dev_order_public_id: str) -> Optional[str]:
    """
    Возвращает dev_order_id по dev_order_public_id (UUID).
    """
    cols = _dev_order_cols(conn, force_refresh=False)
    if ("dev_order_id" not in cols) or ("dev_order_public_id" not in cols):
        return None

    try:
        pid = str(uuid.UUID(str(dev_order_public_id)))
    except Exception:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT dev_order_id FROM dev.dev_order WHERE dev_order_public_id = %s::uuid LIMIT 1",
                (pid,),
            )
            row = cur.fetchone()
        if row and row[0] is not None:
            return _coerce_id_str(row[0]) or None
    except Exception:
        return None

    return None


# -----------------------------
# Unified API envelope helpers (B-M2/B-M3)
# -----------------------------

_ERROR_KINDS = {"validation", "dependency", "runtime", "policy"}
_COMMERCIAL_STATUSES = {"accepted", "running", "succeeded", "failed", "rejected"}


def _norm_error_kind(kind: Optional[str]) -> str:
    k = (kind or "runtime").strip().lower()
    return k if k in _ERROR_KINDS else "runtime"


def _commercial_status_from_status(status: Optional[str]) -> str:
    """
    Backward-compat mapping only from status (B-M2 baseline).
    B-M3 overrides for read endpoints via _commercial_status_from_task().
    """
    s = (status or "").strip().lower()
    if s in ("new", "queued", "created", "accepted"):
        return "accepted"
    if s in ("running", "in_progress", "processing"):
        return "running"
    if s in ("done", "success", "succeeded", "ok"):
        return "succeeded"
    if s in ("failed", "error", "dead"):
        return "failed"
    if s in ("rejected", "denied", "invalid"):
        return "rejected"
    return "accepted" if s else "accepted"


def _commercial_status_for_error_kind(kind: str) -> str:
    k = _norm_error_kind(kind)
    return "rejected" if k in ("validation", "policy") else "failed"


def _extract_ok_from_result_spec(rs: Any) -> Optional[bool]:
    if not isinstance(rs, dict):
        return None
    v = rs.get("ok")
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return None


def _extract_error_kind_from_result_spec(rs: Any) -> Optional[str]:
    if not isinstance(rs, dict):
        return None
    err = rs.get("error")
    if isinstance(err, dict):
        k = err.get("kind")
        if k:
            return _norm_error_kind(str(k))
    return None


def _commercial_status_from_task(status: Optional[str], result_spec: Any) -> str:
    """
    B-M3 truth: derive commercial_status from (dev_task.status + result_spec.ok + result_spec.error.kind).
    Handles edge-case: status=done but ok=false => failed/rejected.
    """
    s = (status or "").strip().lower()

    if s in ("running", "in_progress", "processing"):
        return "running"

    ok = _extract_ok_from_result_spec(result_spec)
    kind = _extract_error_kind_from_result_spec(result_spec)

    if s in ("failed", "error", "dead"):
        if kind in ("validation", "policy"):
            return "rejected"
        return "failed"

    if s in ("done", "success", "succeeded", "ok"):
        if ok is True:
            return "succeeded"
        if ok is False:
            if kind in ("validation", "policy"):
                return "rejected"
            return "failed"
        # ok unknown
        if kind in ("validation", "policy"):
            return "rejected"
        if kind in ("dependency", "runtime"):
            return "failed"
        return "succeeded"

    if s in ("rejected", "denied", "invalid"):
        return "rejected"

    return "accepted" if s else "accepted"


def _err(
    status_code: int,
    error: ErrorEnvelope,
    *,
    kind: str = "runtime",
    correlation_id: Optional[str] = None,
    order_type: Optional[str] = None,
) -> JSONResponse:
    ek = _norm_error_kind(kind)
    payload: Dict[str, Any] = {
        "ok": False,
        "commercial_status": _commercial_status_for_error_kind(ek),
        "error": {**error.to_dict(), "kind": ek},
    }
    if correlation_id is not None:
        payload["correlation_id"] = str(correlation_id)
    if order_type is not None:
        payload["order_type"] = str(order_type)
    return JSONResponse(status_code=int(status_code), content=payload)


def _missing_db(conn, *, correlation_id: Optional[str]) -> JSONResponse:
    missing: List[str] = []
    if not _to_regclass(conn, "dev.dev_order"):
        missing.append("db:dev.dev_order")
    if not _to_regclass(conn, "dev.dev_task"):
        missing.append("db:dev.dev_task")

    e = make_error(
        code="DB_MISSING_OBJECT",
        message="DevFactory коммерческий контур не может стартовать: отсутствуют БД-объекты.",
        remediation="Нужен SQL-lane: восстановить таблицы dev.dev_order и dev.dev_task (без костылей).",
        missing_inputs=missing,
        evidence={},
        correlation_id=correlation_id,
    )
    return _err(424, e, kind="dependency", correlation_id=correlation_id)


def _err_with_refs(
    status_code: int,
    *,
    error: ErrorEnvelope,
    kind: str = "runtime",
    correlation_id: Optional[str] = None,
    order_type: Optional[str] = None,
    retry_of_dev_task_id: Optional[int] = None,
    commercial_status: Optional[str] = None,
    dev_order_id: Optional[str] = None,
    dev_order_public_id: Optional[str] = None,
    dev_task_id: Optional[int] = None,
    job_id: Optional[str] = None,
) -> JSONResponse:
    ek = _norm_error_kind(kind)
    cs = (commercial_status or "").strip().lower()
    if cs not in _COMMERCIAL_STATUSES:
        cs = _commercial_status_for_error_kind(ek)

    payload: Dict[str, Any] = {"ok": False, "commercial_status": cs, "error": {**error.to_dict(), "kind": ek}}
    if correlation_id is not None:
        payload["correlation_id"] = str(correlation_id)
    if order_type is not None:
        payload["order_type"] = str(order_type)
    if retry_of_dev_task_id is not None:
        payload["retry_of_dev_task_id"] = int(retry_of_dev_task_id)
    if dev_order_id is not None:
        payload["dev_order_id"] = str(dev_order_id)
    if dev_order_public_id is not None:
        payload["dev_order_public_id"] = str(dev_order_public_id)
    if dev_task_id is not None:
        payload["dev_task_id"] = int(dev_task_id)
    if job_id is not None:
        payload["job_id"] = str(job_id)
    return JSONResponse(status_code=int(status_code), content=payload)


# -----------------------------
# Pydantic models (contract)
# -----------------------------


class DevOrderCreateIn(BaseModel):
    """
    Minimal payload:
      - order_type (catalog)
      - payload (optional)
    """

    order_type: str = Field(..., description="Catalog order_type (e.g., stand_diagnostics_v1)")
    title: Optional[str] = Field(None, description="Optional title override")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Order payload (facts/inputs)")
    customer_name: Optional[str] = None
    currency_code: Optional[str] = None
    total_amount: Optional[float] = None
    tenant_external_id: Optional[str] = Field(
        None,
        description="External tenant/customer id (stored into dev.dev_order.order_tenant_external_id; tenant_id used as legacy fallback).",
    )


class DevOrderOut(BaseModel):
    correlation_id: Optional[str] = None
    order_type: Optional[str] = None
    retry_of_dev_task_id: Optional[int] = None
    commercial_status: Optional[str] = None

    dev_order_id: str
    dev_order_public_id: Optional[str] = None
    dev_task_id: int
    job_id: Optional[str] = None
    status: str
    result_spec: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None


# -----------------------------
# Router / policies
# -----------------------------

_read_deps = []
_write_deps = []

if require_policies is not None:
    try:
        _read_deps = [Depends(require_policies("devfactory", ["view_tasks"]))]  # type: ignore
    except Exception:
        _read_deps = []
    try:
        _write_deps = [Depends(require_policies("devfactory", ["manage_tasks"]))]  # type: ignore
    except Exception:
        _write_deps = []

# write: если FlowSec политики ещё не заведены — спасаемся architect key
if require_architect_key is not None:
    _write_deps = _write_deps + [Depends(require_architect_key)]  # type: ignore

router = APIRouter(prefix="/devfactory", tags=["devfactory"], dependencies=_read_deps)

# -----------------------------
# Celery preflight helpers
# -----------------------------


def _assert_worker_ready(celery_app) -> None:
    """
    Fail-fast guards:
      - task is registered in current celery_app
      - optional: at least one live worker is reachable
    """
    if DF_CELERY_TASK_NAME not in getattr(celery_app, "tasks", {}):
        raise RuntimeError(f"task {DF_CELERY_TASK_NAME} is not registered in celery_app.tasks")

    if not FF_DEVFACTORY_REQUIRE_WORKER:
        return

    try:
        replies = celery_app.control.ping(timeout=0.6)
        if not replies:
            raise RuntimeError("no live celery workers (ping empty)")
    except Exception as e:
        raise RuntimeError(f"no live celery workers: {e}")


# -----------------------------
# Core DB operations
# -----------------------------


def _insert_dev_order(conn, *, body: DevOrderCreateIn) -> Tuple[str, Optional[str]]:
    cols = _dev_order_cols(conn, force_refresh=False)
    if "dev_order_id" not in cols:
        raise RuntimeError("dev.dev_order has no dev_order_id column")

    fields: List[str] = []
    placeholders: List[str] = []
    params: List[Any] = []

    def add(col: str, placeholder: str, val: Any) -> None:
        if col in cols:
            fields.append(col)
            placeholders.append(placeholder)
            params.append(val)

    cc = (body.currency_code or "").strip()
    tenant_ext = (body.tenant_external_id or "").strip() or None

    add("status", "%s", "new")
    add("title", "%s", (body.title or "").strip() or f"DevFactory: {body.order_type}")
    add("description", "%s", None)
    add("customer_name", "%s", (body.customer_name or "").strip() or None)
    add("total_amount", "%s", body.total_amount)
    add("currency_code", "%s", (cc.upper() if cc else None))

    # новый контракт (если колонка есть)
    add("order_tenant_external_id", "%s", tenant_ext)
    # legacy fallback
    add("tenant_id", "%s", tenant_ext)

    if "meta" in cols:
        fields.append("meta")
        placeholders.append(_json_placeholder_for(conn, "dev", "dev_order", "meta"))
        params.append(_json_dumps({"order_type": body.order_type}))

    if not fields:
        raise RuntimeError("dev.dev_order: no writable columns discovered")

    returning_cols = ["dev_order_id"]
    if "dev_order_public_id" in cols:
        returning_cols.append("dev_order_public_id")

    sql = f"""
    INSERT INTO dev.dev_order ({", ".join(fields)})
    VALUES ({", ".join(placeholders)})
    RETURNING {", ".join(returning_cols)}
    """.strip()

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
    conn.commit()

    if not row or row[0] is None:
        raise RuntimeError("Failed to insert dev.dev_order (no dev_order_id returned)")

    dev_order_id = _coerce_id_str(row[0])
    if not dev_order_id:
        raise RuntimeError("Failed to coerce dev_order_id to string")

    dev_order_public_id: Optional[str] = None
    if len(returning_cols) > 1 and len(row) > 1 and row[1] is not None:
        dev_order_public_id = _coerce_id_str(row[1]) or None

    return dev_order_id, dev_order_public_id


def _insert_dev_task(
    conn,
    *,
    dev_order_id: str,
    dev_order_public_id: Optional[str],
    body: DevOrderCreateIn,
    job_id: Optional[str] = None,
) -> int:
    cols = _dev_task_cols(conn, force_refresh=False)
    if "id" not in cols:
        raise RuntimeError("dev.dev_task has no id column")

    title = (body.title or "").strip() or f"{body.order_type}"
    stack = "python_backend"

    input_spec: Dict[str, Any] = {
        "dev_order_id": str(dev_order_id),
        "order_type": body.order_type,
        "payload": body.payload or {},
    }
    meta: Dict[str, Any] = {"dev_order_id": str(dev_order_id), "order_type": body.order_type}
    links: Dict[str, Any] = {}

    if dev_order_public_id:
        input_spec["dev_order_public_id"] = str(dev_order_public_id)
        meta["dev_order_public_id"] = str(dev_order_public_id)

    if body.tenant_external_id:
        input_spec["tenant_external_id"] = str(body.tenant_external_id)

    # job_id сохраняем СРАЗУ при INSERT (чтобы get_order мог вернуть его всегда)
    if job_id:
        jid = str(job_id)
        links["celery_job_id"] = jid
        meta["celery_job_id"] = jid
        input_spec["celery_job_id"] = jid

    fields: List[str] = []
    placeholders: List[str] = []
    params: List[Any] = []

    def add(col: str, placeholder: str, val: Any) -> None:
        if col in cols:
            fields.append(col)
            placeholders.append(placeholder)
            params.append(val)

    add("stack", "%s", stack)
    add("title", "%s", title)
    add("status", "%s", "new")
    add("source", "%s", "devfactory_orders")

    if "input_spec" in cols:
        fields.append("input_spec")
        placeholders.append(_json_placeholder_for(conn, "dev", "dev_task", "input_spec"))
        params.append(_json_dumps(input_spec))

    if "meta" in cols:
        fields.append("meta")
        placeholders.append(_json_placeholder_for(conn, "dev", "dev_task", "meta"))
        params.append(_json_dumps(meta))

    if ("links" in cols) and links:
        fields.append("links")
        placeholders.append(_json_placeholder_for(conn, "dev", "dev_task", "links"))
        params.append(_json_dumps(links))

    if not fields:
        raise RuntimeError("dev.dev_task: no writable columns discovered")

    sql = f"""
    INSERT INTO dev.dev_task ({", ".join(fields)})
    VALUES ({", ".join(placeholders)})
    RETURNING id
    """.strip()

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
    conn.commit()

    if not row or row[0] is None:
        raise RuntimeError("Failed to insert dev.dev_task (no id returned)")

    return int(row[0])


def _update_dev_task_job_refs(conn, *, dev_task_id: int, job_id: str) -> None:
    """
    Если Celery вернул другой id (редко) — подправляем links/meta/input_spec.
    """
    cols = _dev_task_cols(conn, force_refresh=False)
    if "id" not in cols:
        return

    set_parts: List[str] = []
    params: List[Any] = []
    job_id_s = str(job_id)

    def add_json_merge(col: str) -> None:
        udt = _col_udt_name(conn, "dev", "dev_task", col) or "jsonb"
        expr = f"COALESCE({col}::jsonb, '{{}}'::jsonb) || jsonb_build_object('celery_job_id', %s)"
        set_parts.append(f"{col} = ({expr})::json" if udt == "json" else f"{col} = ({expr})::jsonb")
        params.append(job_id_s)

    if "links" in cols:
        add_json_merge("links")
    if "meta" in cols:
        add_json_merge("meta")
    if "input_spec" in cols:
        add_json_merge("input_spec")

    if "updated_at" in cols:
        set_parts.append("updated_at = now()")

    if not set_parts:
        return

    sql = f"UPDATE dev.dev_task SET {', '.join(set_parts)} WHERE id = %s"
    params.append(int(dev_task_id))

    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _fail_dev_task_due_to_enqueue(conn, *, dev_task_id: int, correlation_id: Optional[str], reason: str) -> None:
    """
    Fail-fast: если enqueue не удалось — фиксируем в dev_task (best-effort).
    """
    cols = _dev_task_cols(conn, force_refresh=False)
    fields: List[str] = []
    params: List[Any] = []

    if "status" in cols:
        fields.append("status = %s")
        params.append("failed")

    if "error" in cols:
        fields.append("error = %s")
        params.append(str(reason))

    reason_l = str(reason or "").lower()
    if ("not registered" in reason_l) or ("unregistered" in reason_l):
        code = "TASK_NOT_REGISTERED"
        remediation = "Проверь, что worker импортирует src.worker.tasks.devfactory_commercial (celery_app.py anchors import)."
    elif "no live celery workers" in reason_l:
        code = "WORKER_UNAVAILABLE"
        remediation = "Нет живых Celery workers. Подними/перезапусти worker и повтори заказ."
    else:
        code = "CELERY_UNAVAILABLE"
        remediation = "Проверь worker/redis и регистрацию задачи devfactory.commercial.run_order."

    if "result_spec" in cols:
        e = make_error(
            code=code,
            message="Order accepted, but cannot enqueue worker job.",
            remediation=remediation,
            missing_inputs=[],
            evidence={"error": str(reason)},
            correlation_id=correlation_id,
        )
        e_dict = e.to_dict()
        e_dict["kind"] = "dependency"

        placeholder = _json_placeholder_for(conn, "dev", "dev_task", "result_spec")
        fields.append(f"result_spec = {placeholder}")
        params.append(_json_dumps({"ok": False, "error": e_dict, "correlation_id": correlation_id}))

    if "updated_at" in cols:
        fields.append("updated_at = now()")

    if not fields:
        return

    sql = f"UPDATE dev.dev_task SET {', '.join(fields)} WHERE id = %s"
    params.append(int(dev_task_id))

    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _fetch_order_task(
    conn, *, dev_order_id: str
) -> Optional[Tuple[int, str, Dict[str, Any], Optional[str], Optional[str], Optional[str], Optional[int]]]:
    """
    Возвращает (dev_task_id, status, result_spec, error, job_id, order_type, retry_of_dev_task_id) по последней задаче DevOrder.
    Линкуемся через meta->>'dev_order_id' или input_spec->>'dev_order_id'.

    trace читаем устойчиво: links/meta/input_spec как ::text + result_spec как dict.
    """
    cols = _dev_task_cols(conn, force_refresh=False)
    link_expr = _task_order_link_expr(cols)
    if not link_expr:
        return None

    select_exprs: List[Tuple[str, str]] = [("id", "id")]
    if "status" in cols:
        select_exprs.append(("status", "status"))
    if "result_spec" in cols:
        select_exprs.append(("result_spec", "result_spec"))
    if "error" in cols:
        select_exprs.append(("error", "error"))
    if "links" in cols:
        select_exprs.append(("links::text", "links_text"))
    if "meta" in cols:
        select_exprs.append(("meta::text", "meta_text"))
    if "input_spec" in cols:
        select_exprs.append(("input_spec::text", "input_spec_text"))

    select_sql = ", ".join([f"{expr} AS {alias}" if expr != alias else expr for expr, alias in select_exprs])
    aliases = [alias for _, alias in select_exprs]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {select_sql}
              FROM dev.dev_task
             WHERE {link_expr} = %s
             ORDER BY COALESCE(updated_at, created_at, now()) DESC
             LIMIT 1
            """,
            (str(dev_order_id),),
        )
        row = cur.fetchone()

    if not row:
        return None

    data: Dict[str, Any] = {aliases[i]: row[i] for i in range(len(aliases))}
    dev_task_id = int(data.get("id"))
    st = str(data.get("status") or "unknown")
    rs = _coerce_json_dict(data.get("result_spec"))
    err = (str(data.get("error")) if data.get("error") is not None else None)

    trace = _extract_trace_fields(
        data.get("links_text"),
        data.get("meta_text"),
        data.get("input_spec_text"),
        rs,
    )

    job_id = trace.get("job_id")
    order_type = trace.get("order_type")
    retry_of = trace.get("retry_of_dev_task_id")

    return (dev_task_id, st, rs, err, job_id, order_type, retry_of)


# -----------------------------
# Endpoints
# -----------------------------


@router.post(
    "/orders",
    summary="Create DevOrder (commercial) -> creates DevTask + enqueues worker job",
    dependencies=_write_deps,
)
def create_order(
    body: DevOrderCreateIn,
    x_ff_correlation_id: Optional[str] = Header(None, alias="X-FF-Correlation-Id"),
):
    corr = (x_ff_correlation_id or "").strip() or None
    if not corr:
        corr = str(uuid.uuid4())

    item = get_catalog_item(body.order_type)
    if not item:
        return _err(
            404,
            make_error(
                code="UNKNOWN_ORDER_TYPE",
                message="Unknown order_type (not in catalog).",
                remediation="Call GET /api/devfactory/catalog and use one of the returned order_type values.",
                missing_inputs=["order_type"],
                correlation_id=corr,
            ),
            kind="validation",
            correlation_id=corr,
            order_type=body.order_type,
        )

    conn = _connect_pg()
    try:
        if (not _to_regclass(conn, "dev.dev_order")) or (not _to_regclass(conn, "dev.dev_task")):
            return _missing_db(conn, correlation_id=corr)

        # 1) DevOrder (opaque string id) + public id
        dev_order_id, dev_order_public_id = _insert_dev_order(conn, body=body)
        dev_order_pk = _maybe_int(dev_order_id)

        # 2) job_id генерим заранее: сохраняем в dev_task и используем как celery task_id
        job_id = str(uuid.uuid4())

        # 3) DevTask (контракт: всегда есть task_id)
        dev_task_id = _insert_dev_task(
            conn,
            dev_order_id=str(dev_order_id),
            dev_order_public_id=dev_order_public_id,
            body=body,
            job_id=job_id,
        )

        _try_insert_audit_event(
            conn,
            actor="api.devfactory_orders",
            action="devorder.create",
            ok=True,
            dev_order_id_int=dev_order_pk,
            dev_task_id=int(dev_task_id),
            payload={
                "order": _order_payload_summary(body),
                "dev_order_id": str(dev_order_id),
                "dev_order_public_id": (str(dev_order_public_id) if dev_order_public_id else None),
                "job_id": str(job_id),
                "correlation_id": corr,
            },
            evidence_refs=_evidence_refs(("correlation_id", corr)),
        )

        # 4) enqueue (fail-fast preflight)
        enqueue_error: Optional[str] = None
        try:
            from src.worker.celery_app import app as celery_app  # type: ignore

            _assert_worker_ready(celery_app)

            ar = celery_app.send_task(
                DF_CELERY_TASK_NAME,
                args=[str(dev_order_id)],
                kwargs={"order_type": body.order_type, "correlation_id": corr},
                task_id=job_id,
            )

            # Если Celery вдруг вернул другой id — фиксируем это в task
            ar_id = getattr(ar, "id", None)
            if ar_id and str(ar_id) != str(job_id):
                job_id = str(ar_id)
                _update_dev_task_job_refs(conn, dev_task_id=int(dev_task_id), job_id=str(job_id))

            _try_insert_audit_event(
                conn,
                actor="api.devfactory_orders",
                action="devorder.enqueue",
                ok=True,
                dev_order_id_int=dev_order_pk,
                dev_task_id=int(dev_task_id),
                payload={"job_id": str(job_id), "task": DF_CELERY_TASK_NAME, "correlation_id": corr},
                evidence_refs=_evidence_refs(("correlation_id", corr), ("celery_job_id", str(job_id))),
            )

        except Exception as ex:
            enqueue_error = str(ex)
            _fail_dev_task_due_to_enqueue(conn, dev_task_id=int(dev_task_id), correlation_id=corr, reason=enqueue_error)

            _try_insert_audit_event(
                conn,
                actor="api.devfactory_orders",
                action="devorder.enqueue",
                ok=False,
                dev_order_id_int=dev_order_pk,
                dev_task_id=int(dev_task_id),
                payload={
                    "error": enqueue_error,
                    "job_id": str(job_id),
                    "task": DF_CELERY_TASK_NAME,
                    "correlation_id": corr,
                },
                evidence_refs=_evidence_refs(("correlation_id", corr)),
                err=enqueue_error,
            )

        # 5) Context Pack (facts) best-effort
        try:
            t0 = time.monotonic()
            cp = collect_context_pack(conn=conn)
            attach_context_pack_to_dev_task(conn, dev_task_id=int(dev_task_id), context_pack=cp)
            try_insert_ops_agent_event(
                conn,
                agent="devfactory.context_pack",
                level="info",
                action="collect_on_order_create",
                payload={"dev_order_id": str(dev_order_id), "dev_task_id": int(dev_task_id), "context_pack": cp},
                ok=True,
                latency_ms=int((time.monotonic() - t0) * 1000.0),
            )

            _try_insert_audit_event(
                conn,
                actor="api.devfactory_orders",
                action="devorder.context_pack",
                ok=True,
                dev_order_id_int=dev_order_pk,
                dev_task_id=int(dev_task_id),
                payload={
                    "latency_ms": int((time.monotonic() - t0) * 1000.0),
                    "context_pack_keys": sorted([str(k) for k in (cp or {}).keys()])[:50],
                    "correlation_id": corr,
                },
                evidence_refs=_evidence_refs(("correlation_id", corr)),
            )
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            _try_insert_audit_event(
                conn,
                actor="api.devfactory_orders",
                action="devorder.context_pack",
                ok=False,
                dev_order_id_int=dev_order_pk,
                dev_task_id=int(dev_task_id),
                payload={"error": "context_pack_failed", "correlation_id": corr},
                evidence_refs=_evidence_refs(("correlation_id", corr)),
            )

        # enqueue failed -> формализованный отказ + refs
        if enqueue_error is not None:
            reason_l = enqueue_error.lower()
            if ("not registered" in reason_l) or ("unregistered" in reason_l):
                code = "TASK_NOT_REGISTERED"
                remediation = "Проверь, что worker импортирует src.worker.tasks.devfactory_commercial (celery_app.py anchors import)."
            elif "no live celery workers" in reason_l:
                code = "WORKER_UNAVAILABLE"
                remediation = "Нет живых Celery workers. Подними/перезапусти worker и повтори заказ."
            else:
                code = "CELERY_UNAVAILABLE"
                remediation = "Проверь worker/redis и регистрацию задачи devfactory.commercial.run_order."

            e = make_error(
                code=code,
                message="Order accepted, but cannot enqueue worker job.",
                remediation=remediation,
                missing_inputs=[],
                evidence={"error": enqueue_error},
                correlation_id=corr,
            )
            return _err_with_refs(
                503,
                error=e,
                kind="dependency",
                correlation_id=corr,
                order_type=str(body.order_type),
                commercial_status="failed",
                dev_order_id=str(dev_order_id),
                dev_order_public_id=(str(dev_order_public_id) if dev_order_public_id else None),
                dev_task_id=int(dev_task_id),
                job_id=str(job_id),
            )

        status = "new"
        return {
            "ok": True,
            "correlation_id": corr,
            "order_type": str(body.order_type),
            "retry_of_dev_task_id": None,
            "commercial_status": _commercial_status_from_status(status),
            "dev_order_id": str(dev_order_id),
            "dev_order_public_id": (str(dev_order_public_id) if dev_order_public_id else None),
            "dev_task_id": int(dev_task_id),
            "job_id": str(job_id),
            "status": status,
            "result_spec": {},
            "error": None,
        }
    finally:
        _safe_close(conn)


@router.get("/orders/public/{dev_order_public_id}", summary="Get DevOrder by public UUID")
def get_order_by_public_id(
    dev_order_public_id: str,
    include_result: int = Query(1, ge=0, le=1),
    x_ff_correlation_id: Optional[str] = Header(None, alias="X-FF-Correlation-Id"),
):
    corr = (x_ff_correlation_id or "").strip() or None
    if not corr:
        corr = str(uuid.uuid4())

    try:
        pid = str(uuid.UUID(str(dev_order_public_id)))
    except Exception:
        return _err(
            400,
            make_error(
                code="INVALID_DEV_ORDER_PUBLIC_ID",
                message="dev_order_public_id is not a valid UUID.",
                remediation="Передай UUID dev_order_public_id, который вернул API при создании заказа.",
                missing_inputs=["dev_order_public_id"],
                correlation_id=corr,
            ),
            kind="validation",
            correlation_id=corr,
        )

    conn = _connect_pg()
    try:
        if not _to_regclass(conn, "dev.dev_order"):
            return _missing_db(conn, correlation_id=corr)
        if not _to_regclass(conn, "dev.dev_task"):
            return _missing_db(conn, correlation_id=corr)

        oid = _fetch_dev_order_id_by_public_id(conn, dev_order_public_id=pid)
        if not oid:
            return _err(
                404,
                make_error(
                    code="ORDER_NOT_FOUND",
                    message="Order not found for given dev_order_public_id.",
                    remediation="Проверь dev_order_public_id или запроси /orders/recent.",
                    missing_inputs=[],
                    correlation_id=corr,
                ),
                kind="validation",
                correlation_id=corr,
            )

        t = _fetch_order_task(conn, dev_order_id=str(oid))
        if not t:
            return _err(
                404,
                make_error(
                    code="ORDER_TASK_NOT_FOUND",
                    message="DevOrder found, but no DevTask linked yet.",
                    remediation="Подожди несколько секунд и повтори запрос.",
                    missing_inputs=[],
                    correlation_id=corr,
                ),
                kind="runtime",
                correlation_id=corr,
            )

        dev_task_id, st, rs, err, job_id, order_type, retry_of = t
        commercial_status = _commercial_status_from_task(st, rs)

        out: Dict[str, Any] = {
            "ok": True,
            "correlation_id": corr,
            "order_type": order_type,
            "retry_of_dev_task_id": retry_of,
            "commercial_status": commercial_status,
            "dev_order_id": str(oid),
            "dev_order_public_id": str(pid),
            "dev_task_id": int(dev_task_id),
            "job_id": (str(job_id) if job_id else None),
            "status": st,
            "result_spec": (rs if include_result else {}),
            "error": None,
        }
        if err:
            k = _extract_error_kind_from_result_spec(rs) or ("validation" if commercial_status == "rejected" else "runtime")
            e = make_error(
                code="TASK_ERROR",
                message=str(err),
                remediation="Смотри result_spec/error и context_pack.missing; если данных не хватает — добери факты и повтори.",
                missing_inputs=[],
                correlation_id=corr,
            ).to_dict()
            e["kind"] = _norm_error_kind(k)
            out["error"] = e
        return out
    finally:
        _safe_close(conn)


@router.get("/orders/recent", summary="List recent DevOrders (commercial) with last task status")
def list_recent_orders(
    limit: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None, description="Filter by dev.dev_order.status"),
    include_result: int = Query(0, ge=0, le=1, description="Include last task result_spec (may be heavy)"),
):
    conn = _connect_pg()
    try:
        if not _to_regclass(conn, "dev.dev_order"):
            return _missing_db(conn, correlation_id=None)

        cols_o = _dev_order_cols(conn, force_refresh=False)

        select_cols = [
            c
            for c in (
                "dev_order_id",
                "dev_order_public_id",
                "status",
                "title",
                "customer_name",
                "order_tenant_external_id",
                "total_amount",
                "currency_code",
                "created_at",
                "updated_at",
            )
            if c in cols_o
        ]
        if "dev_order_id" not in select_cols:
            select_cols = ["dev_order_id"]

        where_sql = ""
        params: List[Any] = []
        if status and "status" in cols_o:
            where_sql = "WHERE status = %s"
            params.append(str(status).strip())

        params.append(int(limit))

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                  FROM dev.dev_order
                  {where_sql}
                 ORDER BY dev_order_id DESC
                 LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall() or []

        items: List[Dict[str, Any]] = []
        for row in rows:
            d = {select_cols[i]: row[i] for i in range(len(select_cols))}
            oid = _coerce_id_str(d.get("dev_order_id"))
            pid = _coerce_id_str(d.get("dev_order_public_id")) if d.get("dev_order_public_id") is not None else None

            last_task: Optional[Dict[str, Any]] = None
            if _to_regclass(conn, "dev.dev_task"):
                t = _fetch_order_task(conn, dev_order_id=str(oid))
                if t:
                    tid, tstatus, rs, _err, job_id, order_type, retry_of = t
                    last_task = {
                        "dev_task_id": int(tid),
                        "status": str(tstatus),
                        "commercial_status": _commercial_status_from_task(str(tstatus), rs),
                        "job_id": (str(job_id) if job_id else None),
                        "order_type": order_type,
                        "retry_of_dev_task_id": retry_of,
                    }
                    if int(include_result) == 1:
                        last_task["result_spec"] = rs
                        try:
                            last_task["ok"] = bool((rs or {}).get("ok"))
                        except Exception:
                            pass

            total_amount = d.get("total_amount")
            if total_amount is not None:
                try:
                    total_amount = float(total_amount)
                except Exception:
                    total_amount = str(total_amount)

            items.append(
                {
                    "dev_order_id": str(oid),
                    "dev_order_public_id": (str(pid) if pid else None),
                    "status": str(d.get("status") or ""),
                    "title": d.get("title"),
                    "customer_name": d.get("customer_name"),
                    "order_tenant_external_id": d.get("order_tenant_external_id"),
                    "total_amount": total_amount,
                    "currency_code": d.get("currency_code"),
                    "created_at": d.get("created_at"),
                    "updated_at": d.get("updated_at"),
                    "last_task": last_task,
                }
            )

        return {"ok": True, "limit": int(limit), "items": items}
    finally:
        _safe_close(conn)


@router.get("/orders/{dev_order_id}", summary="Get DevOrder status/result via latest DevTask")
def get_order(
    dev_order_id: str,
    include_result: int = Query(1, ge=0, le=1),
    x_ff_correlation_id: Optional[str] = Header(None, alias="X-FF-Correlation-Id"),
):
    corr = (x_ff_correlation_id or "").strip() or None
    if not corr:
        corr = str(uuid.uuid4())

    bad = _validate_order_id_str(dev_order_id, correlation_id=corr)
    if bad is not None:
        return bad

    oid = (dev_order_id or "").strip()

    conn = _connect_pg()
    try:
        if not _to_regclass(conn, "dev.dev_task"):
            return _missing_db(conn, correlation_id=corr)

        t = _fetch_order_task(conn, dev_order_id=str(oid))
        if not t:
            return _err(
                404,
                make_error(
                    code="ORDER_NOT_FOUND",
                    message="No DevTask found for this dev_order_id (link missing or order not created here).",
                    remediation="Проверь, что dev.dev_task содержит meta/input_spec с dev_order_id и что заказ создавался через POST /devfactory/orders.",
                    missing_inputs=[],
                    correlation_id=corr,
                ),
                kind="validation",
                correlation_id=corr,
            )

        dev_order_public_id = _fetch_dev_order_public_id(conn, dev_order_id=str(oid))

        dev_task_id, st, rs, err, job_id, order_type, retry_of = t
        commercial_status = _commercial_status_from_task(st, rs)

        out: Dict[str, Any] = {
            "ok": True,
            "correlation_id": corr,
            "order_type": order_type,
            "retry_of_dev_task_id": retry_of,
            "commercial_status": commercial_status,
            "dev_order_id": str(oid),
            "dev_order_public_id": (str(dev_order_public_id) if dev_order_public_id else None),
            "dev_task_id": int(dev_task_id),
            "job_id": (str(job_id) if job_id else None),
            "status": st,
            "result_spec": (rs if include_result else {}),
            "error": None,
        }
        if err:
            k = _extract_error_kind_from_result_spec(rs) or ("validation" if commercial_status == "rejected" else "runtime")
            e = make_error(
                code="TASK_ERROR",
                message=str(err),
                remediation="Смотри result_spec/error и context_pack.missing; если данных не хватает — добери факты и повтори.",
                missing_inputs=[],
                correlation_id=corr,
            ).to_dict()
            e["kind"] = _norm_error_kind(k)
            out["error"] = e
        return out
    finally:
        _safe_close(conn)


@router.get("/orders/{dev_order_id}/tasks", summary="List DevTasks for DevOrder (by meta/input_spec->dev_order_id)")
def list_order_tasks(
    dev_order_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    oid = (dev_order_id or "").strip()
    if not oid:
        raise HTTPException(status_code=400, detail="Invalid dev_order_id (empty)")
    if len(oid) > 128:
        raise HTTPException(status_code=400, detail="Invalid dev_order_id (too long)")

    conn = _connect_pg()
    try:
        cols = _dev_task_cols(conn, force_refresh=False)
        link_expr = _task_order_link_expr(cols)
        if not link_expr:
            raise HTTPException(
                status_code=500,
                detail="dev.dev_task has neither meta nor input_spec (cannot link tasks to dev_order_id)",
            )

        select_exprs: List[Tuple[str, str]] = []
        select_exprs.append(("id", "id"))
        if "status" in cols:
            select_exprs.append(("status", "status"))
        if "title" in cols:
            select_exprs.append(("title", "title"))
        if "stack" in cols:
            select_exprs.append(("stack", "stack"))
        if "created_at" in cols:
            select_exprs.append(("created_at", "created_at"))
        if "updated_at" in cols:
            select_exprs.append(("updated_at", "updated_at"))

        # B-M3: need result_spec to compute commercial_status truthfully
        if "result_spec" in cols:
            select_exprs.append(("result_spec", "result_spec"))

        if "links" in cols:
            select_exprs.append(("links::text", "links_text"))
        if "meta" in cols:
            select_exprs.append(("meta::text", "meta_text"))
        if "input_spec" in cols:
            select_exprs.append(("input_spec::text", "input_spec_text"))

        select_sql = ", ".join([f"{expr} AS {alias}" if expr != alias else expr for expr, alias in select_exprs])
        aliases = [alias for _, alias in select_exprs]

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {select_sql}
                  FROM dev.dev_task
                 WHERE {link_expr} = %s
                 ORDER BY COALESCE(updated_at, created_at, now()) DESC
                 LIMIT %s
                """,
                (str(oid), int(limit)),
            )
            rows = cur.fetchall() or []

        out: List[Dict[str, Any]] = []
        for r in rows:
            d = {aliases[i]: r[i] for i in range(len(aliases))}
            trace = _extract_trace_fields(
                d.get("links_text"),
                d.get("meta_text"),
                d.get("input_spec_text"),
            )
            st = str(d.get("status") or "")
            rs = _coerce_json_dict(d.get("result_spec"))
            out.append(
                {
                    "id": int(d.get("id")),
                    "status": st,
                    "commercial_status": _commercial_status_from_task(st, rs),
                    "title": d.get("title"),
                    "stack": d.get("stack"),
                    "created_at": d.get("created_at"),
                    "updated_at": d.get("updated_at"),
                    "job_id": trace.get("job_id"),
                    "order_type": trace.get("order_type"),
                    "retry_of_dev_task_id": trace.get("retry_of_dev_task_id"),
                }
            )

        return {"ok": True, "dev_order_id": str(oid), "items": out}
    finally:
        _safe_close(conn)
