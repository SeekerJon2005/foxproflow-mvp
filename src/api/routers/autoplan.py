# -*- coding: utf-8 -*-
# file: src/api/routers/autoplan.py
#
# FoxProFlow — боевой роутер автоплана:
#   /run                 — запуск конвейера (chain/kick)
#   /result/{id}         — статус одной celery-задачи
#   /result/batch        — статус нескольких задач
#   /pipeline/*          — диагностические выборки по пайплайну
#                          (recent, summary, kpi, coords, no_km,
#                           recent_with_thresholds)
#   /vitrine/*           — витрины решений автоплана (для логиста/аналитика)
#   /trips/{id}/confirm  — адресное подтверждение рейса
#   /debug/celery        — проброс тестовой задачи/инспекция
#   /config              — текущие env/FlowLang-настройки автоплана
#   /health              — быстрый health DB+Celery
#   /diag/price_layer    — верификация слоя цен (freights_price_v)

from __future__ import annotations

import json
import logging
import os
import contextlib
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal, Tuple, Iterable

from fastapi import APIRouter, Path, Query, Body
from starlette.responses import Response

from celery import chain, signature
from celery.result import AsyncResult
from src.worker.celery_app import app as celery_app

# Опциональный типинг из writer (для совместимости старого кода)
try:
    from src.writer import typing as _typing  # noqa: F401
except Exception:  # pragma: no cover
    _typing = None  # type: ignore

# Опциональная интеграция FlowLang → AutoplanSettings
try:
    from src.flowlang.autoplan_adapter import get_autoplan_settings, AutoplanSettings  # type: ignore
except Exception:  # pragma: no cover
    get_autoplan_settings = None  # type: ignore[assignment]
    AutoplanSettings = None  # type: ignore[assignment]

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/autoplan", tags=["autoplan"])

# ─────────────────────────────────────────────
# Диагностические флаги вывода
# ─────────────────────────────────────────────
_DIAG_FIXED_LEN = os.getenv("FF_DIAG_FIXED_LENGTH", "1") == "1"
_DIAG_NO_GZIP = os.getenv("FF_DIAG_DISABLE_GZIP", "1") == "1"


def _json_default(x: Any) -> Any:
    """Базовый сериализатор для json.dumps (фолбэк — str(x))."""
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, Decimal):
        try:
            return float(x)
        except Exception:
            return str(x)
    if isinstance(x, _uuid.UUID):
        return str(x)
    if isinstance(x, (bytes, bytearray)):
        try:
            return x.decode("utf-8", "ignore")
        except Exception:
            return x.hex()
    return str(x)


def _sanitize_for_json(obj: Any) -> Any:
    """Рекурсивно приводит bytes/UUID→str, а также чистит вложенные коллекции/словари."""
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", "ignore")
        except Exception:
            return obj.hex()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    return obj


def _json_fixed(obj: Any, *, status_code: int = 200) -> Response:
    obj = _sanitize_for_json(obj)
    payload = json.dumps(obj, ensure_ascii=False, default=_json_default).encode("utf-8")
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Connection": "close",
        "Cache-Control": "no-store",
    }
    if _DIAG_FIXED_LEN:
        headers["Content-Length"] = str(len(payload))
    if _DIAG_NO_GZIP:
        headers["Content-Encoding"] = "identity"
    return Response(
        content=payload,
        headers=headers,
        status_code=status_code,
        media_type="application/json",
    )


# ─────────────────────────────────────────────
# Postgres
# ─────────────────────────────────────────────
def _db_params() -> Dict[str, Any]:
    return {
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "foxproflow"),
    }


def _db_dsn_from_params(p: Dict[str, Any]) -> str:
    return f"postgresql://{p['user']}:{p.get('password','')}@{p['host']}:{p['port']}/{p['dbname']}"


def _connect_pg():
    """
    Поддерживает:
      • DATABASE_URL / POSTGRES_DSN (полный DSN);
      • набор POSTGRES_* переменных окружения.

    Предпочтение — DSN в одной строке (DATABASE_URL).
    """
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    try:
        import psycopg  # v3

        if dsn:
            return psycopg.connect(dsn)
        p = _db_params()
        # Не блокируем пустой пароль: на dev/CI часто trust/peer.
        return psycopg.connect(**p)
    except Exception:
        import psycopg2  # v2

        if dsn:
            return psycopg2.connect(dsn)
        p = _db_params()
        return psycopg2.connect(_db_dsn_from_params(p))


def _rows(cur) -> List[Dict[str, Any]]:
    cols = [getattr(c, "name", c[0]) for c in (cur.description or [])]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]


def _pg_regclass_exists(cur, regclass: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (regclass,))
    row = cur.fetchone()
    return bool(row and row[0])


# ─────────────────────────────────────────────
# Celery helpers
# ─────────────────────────────────────────────
def _registered_contains(task_name: str, *, timeout: float = 2.0) -> bool:
    try:
        insp = celery_app.control.inspect(timeout=timeout)
        reg = insp.registered() or {}
        for tasks in reg.values():
            try:
                if task_name in tasks:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _pick_chain_task(timeout: float = 2.0) -> Optional[str]:
    for name in ("task_autoplan_chain", "autoplan.chain", "planner.autoplan.chain"):
        if _registered_contains(name, timeout=timeout):
            return name
    return None


def _mask_url(url: Optional[str]) -> str:
    if not url:
        return "env:CELERY_BROKER_URL"
    try:
        if "redis://" in url and "@redis" in url:
            login_host = url.split("redis://", 1)[1]
            if "@" in login_host:
                creds, host = login_host.split("@", 1)
                if ":" in creds:
                    parts = creds.split(":")
                    if len(parts) == 2:
                        user, _pwd = parts
                        return f"redis://{user}:{'*'*3}@{host}"
                    if len(parts) == 1:
                        return f"redis://:{'*'*3}@{host}"
        if "postgresql" in url or "postgres:" in url:
            # Маскируем пароль в DSN
            try:
                scheme, rest = url.split("://", 1)
                if "@" in rest and ":" in rest.split("@", 1)[0]:
                    creds, host = rest.split("@", 1)
                    user, _pwd = creds.split(":", 1)
                    return f"{scheme}://{user}:{'*'*3}@{host}"
            except Exception:
                pass
        return url
    except Exception:
        return url


# ─────────────────────────────────────────────
# Celery results → JSON
# ─────────────────────────────────────────────
def _safe_result(obj: Any) -> Any:
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [_safe_result(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _safe_result(v) for k, v in obj.items()}
        if hasattr(obj, "dict"):
            return obj.dict()
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, BaseException):
            return {"error": obj.__class__.__name__, "msg": str(obj)}
        return {"repr": repr(obj)}
    except Exception as e:  # pragma: no cover
        return {"error": "serialize_error", "msg": repr(e)}


def _id_str(x):
    try:
        v = getattr(x, "id", x)
        if isinstance(v, (bytes, bytearray)):
            return v.decode("utf-8")
        return str(v) if v is not None else None
    except Exception:
        return None


# ─────────────────────────────────────────────
# Canvas-цепочка
# ─────────────────────────────────────────────
def _build_canvas_chain(limit: int, write_audit: bool = False) -> Dict[str, Optional[str]]:
    s_a = (
        signature(
            "planner.autoplan.audit",
            kwargs={"write_audit": bool(write_audit)},
            immutable=True,
        )
        .set(queue="autoplan", ignore_result=False)
    )
    s_ap = (
        signature(
            "planner.autoplan.apply",
            kwargs={"limit": int(limit), "write_audit": bool(write_audit)},
            immutable=True,
        )
        .set(queue="autoplan", ignore_result=False)
    )
    s_ps = (
        signature(
            "planner.autoplan.push_to_trips",
            kwargs={"limit": int(limit), "write_audit": bool(write_audit)},
            immutable=True,
        )
        .set(queue="autoplan", ignore_result=False)
    )
    s_cf = (
        signature(
            "planner.autoplan.confirm",
            kwargs={"limit": int(limit), "write_audit": bool(write_audit)},
            immutable=True,
        )
        .set(queue="autoplan", ignore_result=False)
    )

    res = chain(s_a, s_ap, s_ps, s_cf).apply_async()
    confirm_res = res
    push_res = getattr(confirm_res, "parent", None)
    apply_res = getattr(push_res, "parent", None) if push_res else None
    audit_res = getattr(apply_res, "parent", None) if apply_res else None

    return {
        "root": _id_str(confirm_res),
        "confirm": _id_str(confirm_res),
        "push": _id_str(push_res),
        "apply": _id_str(apply_res),
        "audit": _id_str(audit_res),
    }


def _has_valid_ids(enq: Dict[str, Optional[str]]) -> bool:
    if not isinstance(enq, dict):
        return False
    for k in ("audit", "apply", "push", "confirm", "root"):
        v = enq.get(k)
        if isinstance(v, str) and v:
            return True
    return False


# ─────────────────────────────────────────────
# /run — запуск конвейера
# ─────────────────────────────────────────────
try:
    from src.worker.register_tasks import task_autoplan_chain  # noqa: F401

    _HAVE_WORKER_CHAIN = True
except Exception:
    _HAVE_WORKER_CHAIN = False


def _merge_run_payload(
    limit_query: int,
    window_min_query: Optional[int],
    body: Optional[Dict[str, Any]],
) -> Tuple[int, Optional[int], Dict[str, Any]]:
    body = body or {}
    limit_body = body.get("limit") or body.get("limit_candidates")
    limit_final = int(limit_body) if isinstance(limit_body, (int, float)) else int(limit_query)

    wm_body = body.get("window_minutes")
    window_final = (
        int(wm_body)
        if isinstance(wm_body, (int, float))
        else (int(window_min_query) if window_min_query is not None else None)
    )

    payload: Dict[str, Any] = {}
    for k in (
        "profile",
        "use_dynamic_rpm",
        "rpm_min",
        "p_arrive_min",
        "window_minutes",
        "limit_candidates",
        "limit",
        "write_audit",
        "dry",
    ):
        if k in body:
            payload[k] = body[k]

    payload.setdefault("limit", limit_final)
    if window_final is not None:
        payload.setdefault("window_minutes", window_final)
    return limit_final, window_final, payload


@router.post("/run")
def run_autoplan(
    mode: Literal["chain", "kick"] = Query(
        default="chain", description="Полная цепочка ('chain') или 'kick'"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    window_min: Optional[int] = Query(default=None, ge=10, le=720),
    body: Optional[Dict[str, Any]] = Body(default=None),
):
    limit_final, window_final, payload = _merge_run_payload(limit, window_min, body)

    prev_env = os.environ.get("AUTOPLAN_APPLY_WINDOW_MIN")
    if window_final is not None:
        os.environ["AUTOPLAN_APPLY_WINDOW_MIN"] = str(window_final)

    try:
        if mode == "chain":
            task_name = _pick_chain_task(timeout=2.0)
            if task_name:
                try:
                    r = celery_app.send_task(task_name, kwargs=payload or {}, queue="autoplan")
                    return _json_fixed(
                        {
                            "ok": True,
                            "mode": "worker",
                            "task": task_name,
                            "enqueued": {"root": str(r.id)},
                        }
                    )
                except Exception as e_send:
                    log.warning("worker-chain send_task failed (%s): %s", task_name, e_send)
            # fallback: canvas-chain
            try:
                wa = bool(payload.get("write_audit", False)) or os.getenv(
                    "AUTOPLAN_WRITE_AUDIT", "0"
                ).lower() in {"1", "true", "yes", "on", "y"}
                alt = _build_canvas_chain(limit=limit_final, write_audit=wa)
                if not _has_valid_ids(alt):
                    raise ValueError("api-canvas produced no ids")
                note = "fallback: API-side canvas used " + (
                    f"because worker-chain '{task_name}' failed enqueue" if task_name
                    else "because no worker-chain is registered"
                )
                return _json_fixed({"ok": True, "mode": "chain", "enqueued": alt, "note": note})
            except Exception as e2:
                kick_kwargs = {
                    "limit": int(limit_final),
                    "dry": bool(payload.get("dry", False)),
                }
                rid = celery_app.send_task("autoplan.kick", kwargs=kick_kwargs, queue="autoplan").id
                note = f"fallback: executed (kick) because canvas failed: {e2!s}"
                return _json_fixed(
                    {
                        "ok": True,
                        "mode": "kick",
                        "enqueued": {"root": str(rid)},
                        "note": note,
                    }
                )

        # mode == "kick"
        kick_kwargs = {
            "limit": int(payload.get("limit", limit_final)),
            "dry": bool(payload.get("dry", False)),
        }
        rid = celery_app.send_task("autoplan.kick", kwargs=kick_kwargs, queue="autoplan").id
        return _json_fixed({"ok": True, "mode": "kick", "enqueued": {"root": str(rid)}})
    finally:
        if window_final is not None:
            if prev_env is None:
                os.environ.pop("AUTOPLAN_APPLY_WINDOW_MIN", None)
            else:
                os.environ["AUTOPLAN_APPLY_WINDOW_MIN"] = prev_env


@router.get("/run", include_in_schema=False)
def run_autoplan_get(
    mode: Literal["chain", "kick"] = Query(default="chain"),
    limit: int = Query(default=50, ge=1, le=200),
    window_min: Optional[int] = Query(default=None, ge=10, le=720),
):
    return run_autoplan(mode=mode, limit=limit, window_min=window_min, body=None)


# ─────────────────────────────────────────────
# /result — статус шага/цепочки
# ─────────────────────────────────────────────
@router.get("/result/{task_id}")
def get_task_status(task_id: str = Path(..., description="Celery task_id шага/цепочки")):
    try:
        res = AsyncResult(task_id, app=celery_app)
        state = res.state or "TBD"
        payload: Any = None
        if res.ready():
            try:
                payload = _safe_result(res.result)
            except Exception as e:
                payload = {"error": "result_decode_error", "msg": str(e)}
        out = {
            "id": task_id,
            "state": state,
            "ready": res.ready(),
            "successful": res.successful(),
            "failed": state == "FAILURE",
            "result": payload,
        }
        return _json_fixed(out)
    except Exception as e:
        return _json_fixed({"detail": f"bad task id: {e!s}"}, status_code=400)


@router.post("/result/batch")
def get_task_status_batch(
    ids: List[str] = Body(..., embed=True, description="Список task_id"),
):
    out: List[Dict[str, Any]] = []
    for task_id in ids or []:
        try:
            res = AsyncResult(task_id, app=celery_app)
            state = res.state or "TBD"
            payload: Any = None
            if res.ready():
                with contextlib.suppress(Exception):
                    payload = _safe_result(res.result)
            out.append(
                {
                    "id": task_id,
                    "state": state,
                    "ready": res.ready(),
                    "successful": res.successful(),
                    "failed": state == "FAILURE",
                    "result": payload,
                }
            )
        except Exception as e:
            out.append({"id": task_id, "error": repr(e)})
    return _json_fixed({"items": out})


# ─────────────────────────────────────────────
# /pipeline/* — чтение из БД
# ─────────────────────────────────────────────
def _has_autoplan_recent_view(cur) -> bool:
    cur.execute("SELECT to_regclass('public.autoplan_pipeline_recent_v') IS NOT NULL")
    row = cur.fetchone()
    return bool(row and row[0])


def _trip_status_cols(cur) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='trips'"
        )
        cols = {r[0] for r in cur.fetchall()}
    except Exception:
        cols = set()

    def pick(*names) -> Optional[str]:
        for n in names:
            if n in cols:
                return n
        return None

    status = pick("status", "state")
    ls = pick(
        "planned_load_window_start",
        "load_window_start",
        "pickup_earliest",
        "loading_date",
    )
    ue = pick(
        "planned_unload_window_end",
        "unload_window_end",
        "unloading_date",
        "delivery_dt",
    )
    return status, ls, ue


@router.get("/pipeline/recent")
def pipeline_recent(limit: int = Query(default=50, ge=1, le=200)):
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)
    try:
        cur = cn.cursor()
        if _has_autoplan_recent_view(cur):
            cur.execute(
                """
                SELECT audit_id, ts, truck_id, decision, reason, applied,
                       draft_id, pushed, trip_id, status, ls, ue
                  FROM public.autoplan_pipeline_recent_v
                 ORDER BY ts DESC
                 LIMIT %s
                """,
                (limit,),
            )
            return _json_fixed(_rows(cur))

        status_col, ls_col, ue_col = _trip_status_cols(cur)
        status_sel = f"t.{status_col}" if status_col else "NULL::text"
        ls_sel = f"t.{ls_col}" if ls_col else "NULL::timestamptz"
        ue_sel = f"t.{ue_col}" if ue_col else "NULL::timestamptz"

        sql = f"""
            SELECT  a.id        AS audit_id,
                    a.ts        AS ts,
                    a.truck_id  AS truck_id,
                    a.decision  AS decision,
                    a.reason    AS reason,
                    COALESCE(a.applied,false) AS applied,
                    d.id        AS draft_id,
                    d.pushed    AS pushed,
                    COALESCE(a.trip_id, d.trip_id, t.id) AS trip_id,
                    {status_sel} AS status,
                    {ls_sel}     AS ls,
                    {ue_sel}     AS ue
              FROM public.autoplan_audit a
         LEFT JOIN public.autoplan_draft_trips d
                ON d.audit_id = a.id
         LEFT JOIN public.trips t
                ON t.id = a.trip_id
                OR (t.id = d.trip_id)
                OR (
                     (t.meta->'autoplan' ? 'audit_id')
                     AND (t.meta->'autoplan'->>'audit_id') = a.id::text
                     AND t.created_at > now() - interval '30 days'
                   )
             WHERE a.ts >= now() - make_interval(mins => 1440)
             ORDER BY a.ts DESC
             LIMIT %s
        """
        cur.execute(sql, (limit,))
        return _json_fixed(_rows(cur))
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/pipeline/recent_with_thresholds")
def pipeline_recent_with_thresholds(
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Плоская выборка последних событий автоплана из public.autoplan_audit
    вместе с thresholds.

    Удобно для отладки FlowLang-планов: видно flow_plan/phase и пороги,
    по которым принимались решения (или происходили noop-запуски).
    """
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    try:
        cur = cn.cursor()
        cur.execute(
            """
            SELECT
              a.ts,
              a.truck_id,
              a.decision,
              a.reason,
              COALESCE(a.applied, false) AS applied,
              a.trip_id,
              a.thresholds,
              COALESCE(a.thresholds->>'flow_plan', NULL) AS flow_plan,
              COALESCE(a.thresholds->>'phase', NULL)     AS phase
            FROM public.autoplan_audit a
            ORDER BY a.ts DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = _rows(cur)
        return _json_fixed({"items": rows, "limit": limit})
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


# ─────────────────────────────────────────────
# /vitrine/* — витрины решений автоплана
# ─────────────────────────────────────────────
@router.get("/vitrine/decisions")
def vitrine_decisions(
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(24, ge=1, le=168),
    plan: Optional[str] = Query(
        None,
        description="FlowLang-план (thresholds->>'flow_plan'), например 'rolling_msk' или 'longhaul_night'",
    ),
    phase: Optional[str] = Query(
        None,
        description="Фаза пайплайна (thresholds->>'phase'), например 'apply' или 'confirm'",
    ),
    decision: Optional[str] = Query(
        None,
        description="Фильтр по decision в autoplan_audit (accept/apply/confirm/noop/...)",
    ),
):
    """
    Витрина решений автоплана для логиста/аналитика.

    Источник: public.autoplan_audit.

    Фильтры:
      • hours    — горизонт по времени;
      • decision — тип решения (accept/apply/confirm/noop/...);
      • plan     — FlowLang-план (thresholds.flow_plan);
      • phase    — фаза пайплайна (thresholds.phase).
    """
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    try:
        cur = cn.cursor()
        cur.execute(
            """
            SELECT
              a.id AS audit_id,
              a.ts,
              a.truck_id,
              a.decision,
              a.reason,
              COALESCE(a.applied,false) AS applied,
              a.trip_id,
              a.thresholds,
              COALESCE(a.thresholds->>'flow_plan', NULL) AS flow_plan,
              COALESCE(a.thresholds->>'phase', NULL)     AS phase
            FROM public.autoplan_audit a
            WHERE a.ts >= now() - make_interval(hours => %s)
              AND (%s::text IS NULL OR a.decision = %s::text)
              AND (%s::text IS NULL OR a.thresholds->>'flow_plan' = %s::text)
              AND (%s::text IS NULL OR a.thresholds->>'phase' = %s::text)
            ORDER BY a.ts DESC
            LIMIT %s
            """,
            (hours, decision, decision, plan, plan, phase, phase, limit),
        )
        rows = _rows(cur)
        return _json_fixed(
            {
                "items": rows,
                "limit": limit,
                "hours": hours,
                "filters": {
                    "plan": plan,
                    "phase": phase,
                    "decision": decision,
                },
            }
        )
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/vitrine/decision/{audit_id}")
def vitrine_decision_detail(audit_id: str = Path(..., description="ID строки autoplan_audit (uuid)")):
    """
    Детальная карточка одного решения автоплана по audit_id.

    Возвращает:
      • всю строку public.autoplan_audit (thresholds, reason, applied, trip_id, truck_id и т.д.);
      • отдельные поля flow_plan/phase, вынутые из thresholds.
    """
    try:
        _ = _uuid.UUID(audit_id)
    except Exception:
        return _json_fixed(
            {"ok": False, "detail": "bad audit_id format", "audit_id": audit_id},
            status_code=400,
        )

    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    try:
        cur = cn.cursor()
        cur.execute(
            """
            SELECT
              a.*,
              COALESCE(a.thresholds->>'flow_plan', NULL) AS flow_plan,
              COALESCE(a.thresholds->>'phase',     NULL) AS phase
            FROM public.autoplan_audit a
            WHERE a.id = %s::uuid
            """,
            (audit_id,),
        )
        rows = _rows(cur)
        if not rows:
            return _json_fixed(
                {"ok": False, "detail": "audit_not_found", "audit_id": audit_id},
                status_code=404,
            )

        return _json_fixed({"ok": True, "item": rows[0]})
    except Exception as e:
        return _json_fixed(
            {"ok": False, "detail": "db query error", "error": repr(e)},
            status_code=500,
        )
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/pipeline/summary")
def pipeline_summary(
    horizon_minutes: int = Query(default=240, ge=30, le=7 * 24 * 60),
    hours: Optional[int] = Query(default=None),
    window_min_alias: Optional[int] = Query(default=None, alias="window_min"),
):
    try:
        if hours is not None and hours > 0:
            horizon_minutes = int(hours) * 60
        if window_min_alias is not None and window_min_alias > 0:
            horizon_minutes = int(window_min_alias)
    except Exception:
        pass

    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    try:
        cur = cn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM public.autoplan_audit "
            "WHERE ts >= now() - make_interval(mins => %s)",
            (horizon_minutes,),
        )
        total = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COALESCE(decision, '') AS decision, COUNT(*) AS cnt
              FROM public.autoplan_audit
             WHERE ts >= now() - make_interval(mins => %s)
             GROUP BY decision
            """,
            (horizon_minutes,),
        )
        by_decision = {r[0]: int(r[1]) for r in cur.fetchall()}

        cur.execute(
            """
            SELECT COALESCE(reason, '') AS reason, COUNT(*) AS cnt
              FROM public.autoplan_audit
             WHERE ts >= now() - make_interval(mins => %s)
             GROUP BY reason
             ORDER BY cnt DESC
             LIMIT 12
            """,
            (horizon_minutes,),
        )
        top_reasons = {r[0]: int(r[1]) for r in cur.fetchall()}

        return _json_fixed(
            {
                "total": total,
                "by_decision": by_decision,
                "top_reasons": top_reasons,
            }
        )
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/pipeline/kpi")
def pipeline_kpi(
    window_minutes: int = Query(default=60, ge=5, le=24 * 60),
    aged_minutes: int = Query(default=30, ge=5, le=24 * 60),
):
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)
    try:
        cur = cn.cursor()
        cur.execute(
            """
            WITH w AS (
              SELECT
                SUM((decision='accept')::int) AS accepts,
                SUM((decision='accept' AND applied)::int) AS applied
              FROM public.autoplan_audit
              WHERE ts > now() - make_interval(mins => %s)
            )
            SELECT accepts, applied,
                   ROUND(applied * 100.0 / NULLIF(accepts,0), 1) AS applied_pct
            FROM w
            """,
            (window_minutes,),
        )
        r1 = (
            _rows(cur)[0]
            if cur.rowcount is not None
            else {"accepts": None, "applied": None, "applied_pct": None}
        )

        cur.execute(
            """
            SELECT COUNT(*) AS aged_accepts
            FROM public.autoplan_audit
            WHERE decision='accept'
              AND COALESCE(applied,false)=false
              AND ts < now() - make_interval(mins => %s)
            """,
            (aged_minutes,),
        )
        r2 = _rows(cur)[0] if cur.rowcount is not None else {"aged_accepts": None}

        return _json_fixed(
            {
                **r1,
                **r2,
                "window_minutes": int(window_minutes),
                "aged_minutes": int(aged_minutes),
            }
        )
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/pipeline/coords/unknown")
def pipeline_coords_unknown(limit: int = Query(default=50, ge=1, le=500)):
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)
    try:
        cur = cn.cursor()
        cur.execute("SELECT to_regclass('ops.city_resolve_queue') IS NOT NULL")
        exists = bool(cur.fetchone()[0])
        if not exists:
            return _json_fixed({"items": [], "available": False})
        cur.execute(
            """
            SELECT key, first_seen, last_seen, total_hits, sample_type, sample_trip
            FROM ops.city_resolve_queue
            ORDER BY last_seen DESC
            LIMIT %s
            """,
            (limit,),
        )
        return _json_fixed({"items": _rows(cur), "available": True})
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


@router.get("/pipeline/no_km")
def pipeline_no_km(sample_limit: int = Query(default=50, ge=1, le=200)):
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)
    try:
        cur = cn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) AS no_km
            FROM public.trips t
            WHERE t.status='confirmed'
              AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = ''
            """
        )
        total = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT t.id, t.truck_id,
                   t.meta->'autoplan'->>'origin_region' AS origin_region,
                   t.meta->'autoplan'->>'dest_region'   AS dest_region,
                   t.meta->'autoplan'->>'origin_lat'    AS origin_lat,
                   t.meta->'autoplan'->>'origin_lon'    AS origin_lon,
                   t.meta->'autoplan'->>'dest_lat'      AS dest_lat,
                   t.meta->'autoplan'->>'dest_lon'      AS dest_lon,
                   t.updated_at
              FROM public.trips t
             WHERE t.status='confirmed'
               AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = ''
             ORDER BY t.updated_at DESC
             LIMIT %s
            """,
            (sample_limit,),
        )
        sample = _rows(cur)

        return _json_fixed({"no_km": total, "sample": sample})
    except Exception as e:
        return _json_fixed({"detail": "db query error", "error": repr(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            cn.close()


# ─────────────────────────────────────────────
# /trips/{trip_id}/confirm — адресное подтверждение
# ─────────────────────────────────────────────
@router.post("/trips/{trip_id}/confirm")
def confirm_trip_by_id(trip_id: str = Path(..., description="ID рейса (uuid, строка)")):
    """
    Подтверждает один рейс:
      • рассчитывает drive_hours_est и rph из meta.autoplan.{od_km|est_km|rpm|price};
      • проставляет confirm_ts; переводит статус в 'confirmed';
      • опционально пинает OSRM-обогащение (routing.enrich.trip.by_id).
    """
    try:
        _ = _uuid.UUID(trip_id)
    except Exception:
        return _json_fixed(
            {"ok": False, "detail": "bad trip_id format"},
            status_code=400,
        )

    speed_kmh = float(os.getenv("AUTOPLAN_AVG_SPEED_KMH", "55") or 55.0)
    overhead_min = float(os.getenv("AUTOPLAN_SERVICE_OVERHEAD_MIN", "45") or 45.0)
    fallback_km = float(os.getenv("AUTOPLAN_PRICE_FALLBACK_KM", "350") or 350.0)

    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    try:
        cur = cn.cursor()
        sql = """
        WITH c AS (
          SELECT id, meta
          FROM public.trips
          WHERE id=%(id)s::uuid
          FOR UPDATE
        ),
        calc AS (
          SELECT
            id,
            NULLIF((meta->'autoplan'->>'od_km')::numeric,0)  AS od_km,
            NULLIF((meta->'autoplan'->>'est_km')::numeric,0) AS est_km,
            NULLIF((meta->'autoplan'->>'price')::numeric,0)  AS price,
            NULLIF((meta->'autoplan'->>'rpm')::numeric,0)    AS rpm
          FROM c
        ),
        vals AS (
          SELECT
            id,
            COALESCE(od_km, est_km, %(fallback_km)s::numeric) AS km_eff,
            CASE WHEN COALESCE(od_km, est_km, %(fallback_km)s::numeric) > 0
                 THEN COALESCE(price, rpm * COALESCE(od_km, est_km, %(fallback_km)s::numeric))
                 ELSE price END AS price_eff
          FROM calc
        ),
        agg AS (
          SELECT
            id,
            km_eff,
            price_eff,
            CASE WHEN km_eff IS NOT NULL
                 THEN (km_eff/%(speed_kmh)s) + (%(overhead_min)s/60.0)
                 ELSE NULL END AS drive_hours,
            CASE WHEN price_eff IS NOT NULL
                      AND (CASE WHEN km_eff IS NOT NULL
                                THEN (km_eff/%(speed_kmh)s) + (%(overhead_min)s/60.0)
                                ELSE NULL END) > 0
                 THEN price_eff / ((km_eff/%(speed_kmh)s) + (%(overhead_min)s/60.0))
                 ELSE NULL END AS rph
          FROM vals
        )
        UPDATE public.trips t
           SET status='confirmed',
               confirmed_at = COALESCE(t.confirmed_at, now()),
               updated_at=now(),
               meta = jsonb_set(
                       jsonb_set(
                         jsonb_set(
                           jsonb_set(
                             jsonb_set(
                               COALESCE(t.meta,'{}'::jsonb),
                               '{autoplan,speed_kmh_used}', to_jsonb(%(speed_kmh)s::numeric), true
                             ),
                               '{autoplan,overhead_min_used}', to_jsonb(%(overhead_min)s::numeric), true
                           ),
                             '{autoplan,drive_hours_est}',    COALESCE(to_jsonb(a.drive_hours), 'null'::jsonb), true
                       ),
                         '{autoplan,rph}',                 COALESCE(to_jsonb(a.rph), 'null'::jsonb), true
                     ),
                     '{autoplan,confirm_ts}',             to_jsonb(now()), true
                   )
         FROM agg a
         WHERE t.id=a.id
         RETURNING t.id,
                   (t.meta->'autoplan'->>'road_km')::numeric AS road_km,
                   (t.meta->'autoplan'->>'drive_sec')::int    AS drive_sec;
        """
        cur.execute(
            sql,
            {
                "id": trip_id,
                "speed_kmh": speed_kmh,
                "overhead_min": overhead_min,
                "fallback_km": fallback_km,
            },
        )
        row = cur.fetchone()
        if not row:
            cn.rollback()
            return _json_fixed(
                {"ok": False, "confirmed": False, "detail": "trip not found"},
                status_code=404,
            )

        cn.commit()

        with contextlib.suppress(Exception):
            if os.getenv("ROUTING_ENRICH_ON_CONFIRM", "1").lower() in (
                "1",
                "true",
                "yes",
                "on",
            ):
                celery_app.send_task(
                    "routing.enrich.trip.by_id",
                    kwargs={"trip_id": trip_id},
                )

        return _json_fixed(
            {
                "ok": True,
                "confirmed": True,
                "trip_id": trip_id,
                "speed_kmh_used": speed_kmh,
                "overhead_min_used": overhead_min,
                "road_km": float(row[1]) if row[1] is not None else None,
                "drive_sec": int(row[2]) if row[2] is not None else None,
            }
        )
    except Exception as e:
        with contextlib.suppress(Exception):
            cn.rollback()
        return _json_fixed(
            {"ok": False, "confirmed": False, "error": repr(e)},
            status_code=500,
        )
    finally:
        with contextlib.suppress(Exception):
            cn.close()


# ─────────────────────────────────────────────
# /debug/celery и /config
# ─────────────────────────────────────────────
@router.get("/debug/celery")
def debug_celery():
    raw_broker = os.getenv("CELERY_BROKER_URL", "env:CELERY_BROKER_URL")
    info: Dict[str, Any] = {"broker": _mask_url(raw_broker), "ok": False}
    for name in ("ops.beat.heartbeat", "ops.queue.watchdog", "autoplan.kick"):
        try:
            r = celery_app.send_task(name, kwargs={"dry": True})
            info.update(
                {
                    "ok": True,
                    "via": "send_task",
                    "task": name,
                    "task_id": str(r.id),
                }
            )
            break
        except Exception:
            continue
    if not info["ok"]:
        try:
            replies = celery_app.control.ping(timeout=5)
            info.update(
                {"ok": bool(replies), "via": "control.ping", "replies": replies}
            )
        except Exception as e:
            info.update({"error": repr(e)})
    try:
        reg = celery_app.control.inspect(timeout=2.0).registered() or {}
    except Exception:
        reg = None
    if isinstance(reg, dict):

        def has(tn: str) -> bool:
            try:
                return any(tn in lst for lst in reg.values())
            except Exception:
                return False

        info["registered"] = {
            "task_autoplan_chain": has("task_autoplan_chain"),
            "autoplan.chain": has("autoplan.chain"),
            "planner.autoplan.chain": has("planner.autoplan.chain"),
            "planner.autoplan.audit": has("planner.autoplan.audit"),
            "planner.autoplan.apply": has("planner.autoplan.apply"),
            "planner.autoplan.push_to_trips": has("planner.autoplan.push_to_trips"),
            "planner.autoplan.confirm": has("planner.autoplan.confirm"),
        }
    else:
        info["registered"] = None
    return _json_fixed(info)


def _autoplan_config_payload() -> dict:
    """
    Возвращает текущие настройки автоплана.

    Формат совместим с существующими клиентами:
      • базовые параметры — из ENV (как и раньше);
      • дополнительно, если доступен FlowLang-план, добавляется блок
        flow_plan / flow_plan_name / flow_plan_enabled с "живыми"
        значениями из AutoplanSettings.
    """
    env = os.environ.get

    plan_name = os.getenv("AUTOPLAN_FLOW_PLAN", "rolling_msk")
    plan: Optional[AutoplanSettings] = None
    if get_autoplan_settings is not None:
        try:
            plan = get_autoplan_settings(plan_name)
        except Exception as e:  # pragma: no cover
            log.warning(
                "autoplan.config: failed to load FlowLang plan %r: %r",
                plan_name,
                e,
            )

    # Исторический, "env-only" слой — оставляем как есть для совместимости
    base: Dict[str, Any] = {
        "use_dynamic_rpm": env("USE_DYNAMIC_RPM", "1"),
        "quantile": env("DYNAMIC_RPM_QUANTILE", "p25"),
        "rpm_floor_min": env("DYNAMIC_RPM_FLOOR_MIN", "110"),
        "rpm_min": env("AUTOPLAN_RPM_MIN", env("CONFIRM_RPM_MIN", "130")),
        "p_arrive_min": env("AUTOPLAN_P_ARRIVE_MIN", env("CONFIRM_P_MIN", "0.40")),
        "apply_window_min": env("AUTOPLAN_APPLY_WINDOW_MIN", "240"),
        "horizon_h": env("PLANNER_PICKUP_HORIZON_H", "24"),
        "intracity_km": env("INTRACITY_FALLBACK_KM", "50"),
        "intracity_speed_kmh": env("INTRACITY_SPEED_KMH", "35"),
        "fallback_speed_kmh": env(
            "OSRM_FALLBACK_SPEED_KMH", env("ROUTING_FALLBACK_SPEED_KMH", "70")
        ),
        "osrm_url": env("OSRM_URL", "http://osrm:5000"),
        "osrm_profile": env("OSRM_PROFILE", "driving"),
        "osrm_timeout": env("OSRM_TIMEOUT", "8.0"),
        "routing_enrich_on_confirm": env("ROUTING_ENRICH_ON_CONFIRM", "1"),
        "routing_reenrich_if_confirmed": env("ROUTING_REENRICH_IF_CONFIRMED", "1"),
        "routing_enrich_debug": env("ROUTING_ENRICH_DEBUG", "0"),
        "ff_enable_pipeline_summary": env("FF_ENABLE_PIPELINE_SUMMARY", "1"),
    }

    # Добавляем поверх слой FlowLang-плана — без ломки старых ключей
    base["flow_plan_name"] = plan_name
    if plan is not None:
        base["flow_plan_enabled"] = True
        base["flow_plan"] = {
            "freights_days_back": plan.freights_days_back,
            "apply_window_min": plan.apply_window_min,
            "confirm_window_min": plan.confirm_window_min,
            "confirm_horizon_h": plan.confirm_horizon_h,
            "rpm_min": plan.rpm_min,
            "confirm_rpm_min": plan.confirm_rpm_min,
            "rph_min": plan.rph_min,
            "p_arrive_min_audit": plan.p_arrive_min_audit,
            "p_arrive_min_confirm": plan.p_arrive_min_confirm,
            "use_dynamic_rpm": plan.use_dynamic_rpm,
            "dynamic_rpm_quantile": plan.dynamic_rpm_quantile,
            "dynamic_rpm_floor_min": plan.dynamic_rpm_floor_min,
            "chain_every_minutes": plan.chain_every_minutes,
            "chain_limit": plan.chain_limit,
            "chain_queue": plan.chain_queue,
            "chain_task": plan.chain_task,
            "chain_slot_id": plan.chain_slot_id,
            "write_audit": plan.write_audit,
            "pipeline_summary_enabled": plan.pipeline_summary_enabled,
        }
    else:
        base["flow_plan_enabled"] = False

    return base


@router.get("/config")
def autoplan_config():
    """
    Текущая конфигурация автоплана.

    Возвращает:
      • ENV-параметры (как и раньше);
      • если доступен FlowLang-план — блок flow_plan с фактическими
        значениями AutoplanSettings для активного плана (AUTOPLAN_FLOW_PLAN).
    """
    return _json_fixed(_autoplan_config_payload())


# ─────────────────────────────────────────────
# Health/Diag
# ─────────────────────────────────────────────
@router.get("/health")
def autoplan_health():
    """
    Быстрый health:
      • проверка подключения к БД и версии;
      • ping Celery или запуск тестовой dry-задачи;
      • наличие ключевых задач в реестре.
    """
    db_ok = False
    db_ver = None
    try:
        cn = _connect_pg()
        with cn.cursor() as cur:
            cur.execute("SHOW server_version")
            db_ver = (cur.fetchone() or [None])[0]
        db_ok = True
    except Exception as e:
        db_ver = f"db_error: {e!r}"
    finally:
        with contextlib.suppress(Exception):
            cn.close()  # type: ignore

    celery_ok = False
    celery_via = None
    try:
        replies = celery_app.control.ping(timeout=3)
        celery_ok = bool(replies)
        celery_via = "control.ping"
    except Exception:
        try:
            r = celery_app.send_task("autoplan.kick", kwargs={"dry": True})
            celery_ok = bool(getattr(r, "id", None))
            celery_via = "send_task"
        except Exception:
            celery_ok = False
            celery_via = "error"

    reg = None
    with contextlib.suppress(Exception):
        insp = celery_app.control.inspect(timeout=2.0)
        reg_raw = insp.registered() or {}

        def has(name: str) -> bool:
            try:
                return any(name in lst for lst in reg_raw.values())
            except Exception:
                return False

        reg = {
            "planner.autoplan.audit": has("planner.autoplan.audit"),
            "planner.autoplan.apply": has("planner.autoplan.apply"),
            "planner.autoplan.push_to_trips": has("planner.autoplan.push_to_trips"),
            "planner.autoplan.confirm": has("planner.autoplan.confirm"),
        }

    return _json_fixed(
        {
            "ok": bool(db_ok and celery_ok),
            "db_ok": db_ok,
            "db_version": db_ver,
            "celery_ok": celery_ok,
            "celery_via": celery_via,
            "registered": reg,
        }
    )


@router.get("/diag/price_layer")
def diag_price_layer(sample: int = Query(default=3, ge=0, le=50)):
    """
    Верифицирует слой цен:
      • наличие public.freights_price_v;
      • rowcount (оценочно);
      • демонстрирует несколько записей (price_rub, freight_id/uuid/any).
    """
    try:
        cn = _connect_pg()
    except Exception as e:
        return _json_fixed({"detail": "db connect error", "error": repr(e)}, status_code=500)

    exists = False
    total = None
    items: List[Dict[str, Any]] = []
    err = None
    try:
        cur = cn.cursor()
        exists = _pg_regclass_exists(cur, "public.freights_price_v")
        if not exists:
            return _json_fixed(
                {
                    "exists": False,
                    "items": [],
                    "note": "view public.freights_price_v not found",
                }
            )

        with contextlib.suppress(Exception):
            cur.execute("SELECT COUNT(*) FROM public.freights_price_v")
            total = int((cur.fetchone() or [None])[0] or 0)

        if sample > 0:
            with contextlib.suppress(Exception):
                cur.execute(
                    """
                    SELECT *
                    FROM public.freights_price_v
                    LIMIT %s
                    """,
                    (sample,),
                )
                items = _rows(cur)
    except Exception as e:
        err = repr(e)
    finally:
        with contextlib.suppress(Exception):
            cn.close()

    return _json_fixed(
        {"exists": exists, "total": total, "sample": items, "error": err}
    )
