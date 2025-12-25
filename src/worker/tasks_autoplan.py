# -*- coding: utf-8 -*-
# file: src/worker/tasks_autoplan.py
from __future__ import annotations

import json
import logging
import os
import uuid as _uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task

from src.core import emit_done, emit_error, emit_start
from src.flowlang.autoplan_adapter import AutoplanSettings, get_autoplan_settings

log = logging.getLogger(__name__)

# Кэш настроек автоплана (FlowLang-план + ENV), чтобы не читать план при каждом вызове
_SETTINGS_CACHE: Dict[str, AutoplanSettings] = {}

# Технический идентификатор "фиктивного" грузовика для noop-событий.
# truck_id в public.autoplan_audit хранится как text, так что это просто стабильный маркер.
NOOP_TRUCK_ID: str = os.getenv(
    "AUTOPLAN_NOOP_TRUCK_ID",
    "00000000-0000-0000-0000-000000000000",
)

# Debug-режим: позволяем учитывать "старые" фрахты, игнорируя срез по дате.
ALLOW_OLD_FREIGHTS: bool = str(os.getenv("AUTOPLAN_ALLOW_OLD_FREIGHTS", "0")).lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ─────────────────────────────────────────────
# JSON helpers
# ─────────────────────────────────────────────
def _to_jsonable(obj: Any) -> Any:
    """Приводим объект к JSON-дружелюбному виду (bytes/dict/list/tuple)."""
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.decode("utf-8", "replace")
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _maybe_uuid(val: Any) -> Optional[str]:
    """Вернёт str(uuid) если val похож на UUID, иначе None."""
    if val is None:
        return None
    try:
        return str(_uuid.UUID(str(val)))
    except Exception:
        return None


# ─────────────────────────────────────────────
# FlowLang settings
# ─────────────────────────────────────────────
def _current_plan_name() -> str:
    return os.getenv("AUTOPLAN_FLOW_PLAN", "msk_day")


def _get_autoplan_settings(plan_name: str | None = None) -> AutoplanSettings:
    name = plan_name or _current_plan_name()
    if name not in _SETTINGS_CACHE:
        _SETTINGS_CACHE[name] = get_autoplan_settings(name)
        log.info("autoplan: settings loaded from FlowLang plan %r", name)
    else:
        log.debug("autoplan: settings cache hit for plan %r", name)
    return _SETTINGS_CACHE[name]


# ─────────────────────────────────────────────
# Postgres helpers
# ─────────────────────────────────────────────
def _db_dsn() -> str:
    """
    Единый способ собрать DSN для Postgres.
    Осознанно используем POSTGRES_* (внутри docker-сети host=postgres).
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pg():
    """Подключение к Postgres с fallback между psycopg3 и psycopg2."""
    dsn = _db_dsn()
    try:
        import psycopg  # psycopg3

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # psycopg2 fallback

        return psycopg.connect(dsn)


def _table_exists(cur, fqname: str) -> bool:
    try:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (fqname,))
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _has_column(cur, schema: str, table: str, column: str) -> bool:
    try:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s
            LIMIT 1;
            """,
            (schema, table, column),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def _col_kind(cur, schema: str, table: str, column: str) -> str:
    """
    Возвращает грубый kind колонки: uuid|bigint|int|text|other.
    """
    try:
        cur.execute(
            """
            SELECT udt_name, data_type
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s
            LIMIT 1;
            """,
            (schema, table, column),
        )
        row = cur.fetchone()
        if not row:
            return "other"
        udt, data_type = (row[0] or "").lower(), (row[1] or "").lower()
        t = udt or data_type
        if t == "uuid":
            return "uuid"
        if t in ("int8", "bigint"):
            return "bigint"
        if t in ("int2", "int4", "integer", "smallint"):
            return "int"
        if t in ("text", "varchar", "bpchar", "character varying", "character"):
            return "text"
        return "other"
    except Exception:
        return "other"


def _today() -> date:
    return date.today()


def _freights_days_back(default: int = 2) -> int:
    """Окно свежести фрахтов (дней назад). Приоритет: FlowLang → ENV → default."""
    try:
        settings = _get_autoplan_settings()
        v = int(getattr(settings, "freights_days_back", default))
        return max(1, v)
    except Exception:
        raw = os.getenv("AUTOPLAN_FREIGHTS_DAYS_BACK")
        if not raw:
            return default
        try:
            v = int(raw)
            return max(1, v)
        except Exception:
            return default


# ─────────────────────────────────────────────
# Args helpers
# ─────────────────────────────────────────────
def _normalize_apply_limit(limit: Any, default: int = 200) -> int:
    """
    limit может быть:
      - int/str/float
      - dict payload (limit=..., dry=..., etc)
    """
    raw = limit.get("limit") if isinstance(limit, dict) else limit
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if value <= 0:
        value = default
    return value


def _extract_dry_flag(limit: Any, dry: Any = None, **kwargs: Any) -> bool:
    """
    Dry-run флаг может прийти:
      - параметром dry=...
      - в payload dict: {"dry": true}
      - в kwargs
      - альтернативы: dry_run/dryRun/dry_run_only
    """
    if dry is not None:
        return bool(dry)
    if isinstance(limit, dict) and "dry" in limit:
        return bool(limit.get("dry"))
    if "dry" in kwargs:
        return bool(kwargs.get("dry"))
    if isinstance(limit, dict):
        for k in ("dry_run", "dryRun", "dry_run_only"):
            if k in limit:
                return bool(limit.get(k))
    return False


# ─────────────────────────────────────────────
# Audit helpers (tolerant to mixed ids)
# ─────────────────────────────────────────────
def _build_thresholds(
    settings: AutoplanSettings,
    phase: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "flow_plan": _current_plan_name(),
        "phase": phase,
        "freights_days_back": getattr(settings, "freights_days_back", None),
        "apply_window_min": getattr(settings, "apply_window_min", None),
        "confirm_window_min": getattr(settings, "confirm_window_min", None),
        "confirm_horizon_h": getattr(settings, "confirm_horizon_h", None),
        "rpm_min": getattr(settings, "rpm_min", None),
        "confirm_rpm_min": getattr(settings, "confirm_rpm_min", None),
        "rph_min": getattr(settings, "rph_min", None),
        "p_arrive_min_audit": getattr(settings, "p_arrive_min_audit", None),
        "p_arrive_min_confirm": getattr(settings, "p_arrive_min_confirm", None),
        "use_dynamic_rpm": getattr(settings, "use_dynamic_rpm", None),
        "dynamic_rpm_quantile": getattr(settings, "dynamic_rpm_quantile", None),
        "dynamic_rpm_floor_min": getattr(settings, "dynamic_rpm_floor_min", None),
        "allow_old_freights": ALLOW_OLD_FREIGHTS,
    }
    if extra:
        base.update(extra)
    return base


def _autoplan_audit_log_batch(
    items: List[Tuple[Any, Any]],
    decision: str,
    reason: str,
    applied: bool,
    thresholds: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Пишем пачку событий в public.autoplan_audit.

    items: [(trip_id_any, truck_id_any)]

    ВАЖНО:
      - autoplan_audit.truck_id = text → пишем как str без ::uuid.
      - autoplan_audit.trip_id  = uuid → пишем только если trip_id реально UUID, иначе NULL,
        а реальное значение кладём в payload.trip_id_txt.
    """
    if not items:
        return 0

    thresholds_json = json.dumps(thresholds or {}, ensure_ascii=False)

    try:
        with _pg() as c, c.cursor() as cur:
            if not _table_exists(cur, "public.autoplan_audit"):
                return 0

            rows = []
            for trip_id_any, truck_id_any in items:
                trip_uuid = _maybe_uuid(trip_id_any)
                row_payload = dict(payload or {})
                row_payload.update(
                    {
                        "trip_id_txt": (str(trip_id_any) if trip_id_any is not None else None),
                        "truck_id_txt": (str(truck_id_any) if truck_id_any is not None else None),
                    }
                )
                rows.append(
                    (
                        str(truck_id_any) if truck_id_any is not None else None,
                        decision,
                        reason,
                        bool(applied),
                        trip_uuid,  # uuid or None
                        thresholds_json,
                        json.dumps(row_payload, ensure_ascii=False),
                    )
                )

            cur.executemany(
                """
                INSERT INTO public.autoplan_audit
                  (truck_id, decision, reason, applied, trip_id, thresholds, payload)
                VALUES
                  (%s, %s, %s, %s, %s::uuid, %s::jsonb, %s::jsonb);
                """,
                rows,
            )
            inserted = cur.rowcount or 0
            c.commit()
            return int(inserted)

    except Exception as e:
        log.warning("autoplan_audit batch insert failed: %s", e)
        return 0


def _autoplan_audit_log_event(
    *,
    decision: str,
    reason: str,
    phase: str,
    settings: AutoplanSettings,
    trip_id: Optional[Any] = None,
    truck_id: Optional[Any] = None,
    applied: bool = False,
    extra_thresholds: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Одиночная запись в autoplan_audit (в т.ч. audit/apply/confirm noop/scan)."""
    try:
        with _pg() as c, c.cursor() as cur:
            if not _table_exists(cur, "public.autoplan_audit"):
                return

            thresholds = _build_thresholds(settings, phase=phase, extra=extra_thresholds)
            thresholds_json = json.dumps(thresholds or {}, ensure_ascii=False)

            trip_uuid = _maybe_uuid(trip_id)
            row_payload = dict(payload or {})
            row_payload.update(
                {
                    "trip_id_txt": (str(trip_id) if trip_id is not None else None),
                    "truck_id_txt": (str(truck_id) if truck_id is not None else None),
                }
            )

            cur.execute(
                """
                INSERT INTO public.autoplan_audit
                  (truck_id, decision, reason, applied, trip_id, thresholds, payload)
                VALUES
                  (%s, %s, %s, %s, %s::uuid, %s::jsonb, %s::jsonb);
                """,
                (
                    str(truck_id) if truck_id is not None else None,
                    decision,
                    reason,
                    bool(applied),
                    trip_uuid,  # uuid or None
                    thresholds_json,
                    json.dumps(row_payload, ensure_ascii=False),
                ),
            )
            c.commit()
    except Exception as e:
        log.warning("autoplan_audit event insert failed: %s", e)


# ─────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────
@shared_task(name="planner.autoplan.audit", ignore_result=False)
def task_planner_autoplan_audit(
    limit: Any = 200,
    window_minutes: int = 240,
    write_audit: bool = True,
) -> Dict[str, Any]:
    """
    Фаза 0: разведка рынка — сколько свежих фрахтов и сколько ТС.
    """
    settings = _get_autoplan_settings()
    days_back = _freights_days_back(default=2)
    cutoff = _today() - timedelta(days=days_back)

    cutoff_param: date = cutoff
    if ALLOW_OLD_FREIGHTS:
        cutoff_param = date(1970, 1, 1)

    norm_limit = _normalize_apply_limit(limit, default=200)

    apply_window_min = getattr(settings, "apply_window_min", window_minutes)
    confirm_window_min = getattr(settings, "confirm_window_min", 240)
    confirm_horizon_h = getattr(settings, "confirm_horizon_h", 96)

    correlation_id = f"autoplan.audit:plan={_current_plan_name()}:limit={norm_limit}:window={apply_window_min}"
    emit_start(
        "autoplan.audit",
        correlation_id=correlation_id,
        payload={
            "limit_raw": _to_jsonable(limit),
            "limit_used": norm_limit,
            "window_minutes": window_minutes,
            "apply_window_min": apply_window_min,
            "confirm_window_min": confirm_window_min,
            "confirm_horizon_h": confirm_horizon_h,
            "freights_days_back": days_back,
            "cutoff_date": str(cutoff_param),
            "allow_old_freights": ALLOW_OLD_FREIGHTS,
            "write_audit": bool(write_audit),
        },
    )

    try:
        freights_window = 0
        trucks = 0

        with _pg() as c, c.cursor() as cur:
            if _table_exists(cur, "public.freights"):
                cur.execute(
                    """
                    SELECT count(*)
                    FROM public.freights
                    WHERE COALESCE(loading_date, created_at, parsed_at, now())::date >= %s;
                    """,
                    (cutoff_param,),
                )
                freights_window = int((cur.fetchone() or [0])[0] or 0)

            if _table_exists(cur, "public.trucks"):
                cur.execute("SELECT count(*) FROM public.trucks;")
                trucks = int((cur.fetchone() or [0])[0] or 0)

        log.info(
            "autoplan.audit: freights_today=%s, trucks=%s, cutoff=%s, allow_old=%s",
            freights_window,
            trucks,
            cutoff_param,
            ALLOW_OLD_FREIGHTS,
        )

        result: Dict[str, Any] = {
            "ok": True,
            "freights_today": freights_window,
            "trucks": trucks,
            "limit": norm_limit,
            "window_minutes": int(apply_window_min),
            "apply_window_min": int(apply_window_min),
            "confirm_window_min": int(confirm_window_min),
            "confirm_horizon_h": int(confirm_horizon_h),
            "freights_days_back": days_back,
            "cutoff_date": str(cutoff_param),
            "flow_plan": _current_plan_name(),
            "allow_old_freights": ALLOW_OLD_FREIGHTS,
        }

        # фиксируем audit-событие, чтобы thresholds/plan были видны даже при пустом apply
        if write_audit:
            _autoplan_audit_log_event(
                decision="audit",
                reason="market_scan",
                phase="audit",
                settings=settings,
                trip_id=None,
                truck_id=NOOP_TRUCK_ID,
                applied=False,
                extra_thresholds={
                    "limit_used": norm_limit,
                    "freights_today": freights_window,
                    "trucks": trucks,
                    "cutoff_date": str(cutoff_param),
                },
                payload={"note": "audit scan"},
            )

    except Exception as e:
        log.exception("autoplan.audit failed: %s", e)
        emit_error(
            "autoplan.audit",
            correlation_id=correlation_id,
            payload={
                "error": str(e),
                "limit_raw": _to_jsonable(limit),
                "limit_used": norm_limit,
                "cutoff_date": str(cutoff_param),
            },
        )
        raise
    else:
        emit_done("autoplan.audit", correlation_id=correlation_id, payload=result)
        return result


@shared_task(name="planner.autoplan.apply", ignore_result=False)
def task_planner_autoplan_apply(
    limit: Any = 200,
    window_minutes: int = 240,
    write_audit: bool = True,
    dry: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Фаза 1: создаём planned trips по свежим фрахтам.
    Источник: public.freights_price_v + public.freights.

    FIX:
      - trips.truck_id у нас bigint → вставляем bigint
      - trips.id у нас bigint → RETURNING id::text
      - audit.trip_id uuid → пишем NULL и сохраняем trip_id_txt в payload
    """
    settings = _get_autoplan_settings()
    days_back = _freights_days_back(default=2)

    norm_limit = _normalize_apply_limit(limit, default=200)
    dry_flag = _extract_dry_flag(limit, dry=dry, **kwargs)

    cutoff = _today() - timedelta(days=days_back)
    cutoff_param: date = cutoff
    if ALLOW_OLD_FREIGHTS:
        cutoff_param = date(1970, 1, 1)

    correlation_id = f"autoplan.apply:plan={_current_plan_name()}:limit={norm_limit}"
    emit_start(
        "autoplan.apply",
        correlation_id=correlation_id,
        payload={
            "limit_raw": _to_jsonable(limit),
            "limit_used": norm_limit,
            "freights_days_back": days_back,
            "cutoff_date": str(cutoff_param),
            "write_audit": bool(write_audit),
            "dry": bool(dry_flag),
        },
    )

    created = 0
    rows: List[Tuple[str, str]] = []  # (trip_id_txt, truck_id_txt)

    try:
        if dry_flag:
            if write_audit:
                _autoplan_audit_log_event(
                    decision="noop",
                    reason="apply_dry_run",
                    phase="apply",
                    settings=settings,
                    trip_id=None,
                    truck_id=NOOP_TRUCK_ID,
                    applied=False,
                    extra_thresholds={
                        "limit_used": norm_limit,
                        "cutoff_date": str(cutoff_param),
                        "freights_days_back": days_back,
                        "created": 0,
                        "dry": True,
                    },
                    payload={"note": "dry-run: no writes"},
                )

            result: Dict[str, Any] = {
                "ok": True,
                "created": 0,
                "dry": True,
                "limit_used": norm_limit,
                "freights_days_back": days_back,
                "cutoff_date": str(cutoff_param),
                "flow_plan": _current_plan_name(),
                "allow_old_freights": ALLOW_OLD_FREIGHTS,
            }
            emit_done("autoplan.apply", correlation_id=correlation_id, payload=result)
            return result

        with _pg() as c, c.cursor() as cur:
            # storage checks
            if not _table_exists(cur, "public.freights_price_v") or not _table_exists(cur, "public.freights"):
                if write_audit:
                    _autoplan_audit_log_event(
                        decision="noop",
                        reason="apply_storage_missing",
                        phase="apply",
                        settings=settings,
                        trip_id=None,
                        truck_id=NOOP_TRUCK_ID,
                        applied=False,
                        extra_thresholds={
                            "limit_used": norm_limit,
                            "cutoff_date": str(cutoff_param),
                            "freights_days_back": days_back,
                        },
                        payload={
                            "missing": {
                                "freights_price_v": (not _table_exists(cur, "public.freights_price_v")),
                                "freights": (not _table_exists(cur, "public.freights")),
                            }
                        },
                    )
                result = {
                    "ok": True,
                    "created": 0,
                    "note": "storage missing: freights or freights_price_v",
                    "dry": False,
                    "limit_used": norm_limit,
                    "freights_days_back": days_back,
                    "cutoff_date": str(cutoff_param),
                    "flow_plan": _current_plan_name(),
                }
                emit_done("autoplan.apply", correlation_id=correlation_id, payload=result)
                return result

            if not _table_exists(cur, "public.trips") or not _table_exists(cur, "public.trucks"):
                if write_audit:
                    _autoplan_audit_log_event(
                        decision="noop",
                        reason="apply_storage_missing_trips_or_trucks",
                        phase="apply",
                        settings=settings,
                        trip_id=None,
                        truck_id=NOOP_TRUCK_ID,
                        applied=False,
                        extra_thresholds={"limit_used": norm_limit},
                        payload={
                            "missing": {
                                "trips": (not _table_exists(cur, "public.trips")),
                                "trucks": (not _table_exists(cur, "public.trucks")),
                            }
                        },
                    )
                result = {
                    "ok": True,
                    "created": 0,
                    "note": "storage missing: trips or trucks",
                    "dry": False,
                    "limit_used": norm_limit,
                    "flow_plan": _current_plan_name(),
                }
                emit_done("autoplan.apply", correlation_id=correlation_id, payload=result)
                return result

            trip_truck_kind = _col_kind(cur, "public", "trips", "truck_id")
            if trip_truck_kind not in ("bigint", "int", "uuid", "text"):
                trip_truck_kind = "bigint"  # safest default for текущей схемы

            # ВАЖНО: trips.truck_id у нас bigint → выбираем trucks.id (bigint)
            truck_pick_expr = "tr.id"
            truck_insert_expr = "t.truck_id"
            if trip_truck_kind == "text":
                truck_pick_expr = "tr.id::text"
                truck_insert_expr = "t.truck_id"
            elif trip_truck_kind == "uuid":
                # В этой схеме есть trucks.public_id uuid (nullable). Если NULL — кандидаты не создаём.
                # Это лучше, чем пихать невалидный uuid.
                truck_pick_expr = "tr.public_id"
                truck_insert_expr = "t.truck_id"

            cur.execute(
                f"""
                WITH cand_raw AS (
                  SELECT
                    v.id::uuid                                       AS freight_uuid,
                    COALESCE(NULLIF(v.freight_id::text,''), v.id::text) AS freight_key,
                    v.ts                                              AS v_ts,
                    v.origin_region::text                              AS o,
                    v.dest_region::text                                AS d,
                    COALESCE(v.price_rub, 0)::numeric                  AS price_rub,
                    COALESCE(v.road_km, 0)::numeric                    AS road_km,
                    COALESCE(v.rpm, 0)::numeric                        AS rpm,
                    COALESCE(f.loading_date, f.created_at, f.parsed_at, now()) AS f_ts
                  FROM public.freights_price_v v
                  JOIN public.freights f ON f.id = v.id
                  WHERE COALESCE(f.loading_date, f.created_at, f.parsed_at, now())::date >= %s
                    AND COALESCE(NULLIF(v.origin_region, ''), 'RU-UNK') NOT IN ('RU-UNK', 'Н/Д')
                    AND COALESCE(NULLIF(v.dest_region, ''),   'RU-UNK') NOT IN ('RU-UNK', 'Н/Д')
                ),
                cand AS (
                  SELECT *
                  FROM cand_raw cr
                  WHERE NOT EXISTS (
                    SELECT 1
                    FROM public.trips tt
                    WHERE (tt.meta->'autoplan'->>'freight_uuid') = cr.freight_uuid::text
                       OR (tt.meta->'autoplan'->>'freight_id')   = cr.freight_key
                  )
                  ORDER BY COALESCE(cr.v_ts, cr.f_ts) DESC NULLS LAST
                  LIMIT %s
                ),
                truck_pick AS (
                  SELECT {truck_pick_expr} AS truck_id
                  FROM public.trucks tr
                  WHERE COALESCE(tr.is_active, true) = true
                  ORDER BY tr.id
                  LIMIT 1
                )
                INSERT INTO public.trips (
                  truck_id,
                  status,
                  created_at,
                  meta,
                  loading_region,
                  unloading_region
                )
                SELECT
                  {truck_insert_expr},
                  'planned'::text,
                  now(),
                  jsonb_build_object(
                    'autoplan',
                    jsonb_build_object(
                      'freight_uuid', cand.freight_uuid::text,
                      'freight_id',   cand.freight_key,
                      'o',            cand.o,
                      'd',            cand.d,
                      'price',        cand.price_rub,
                      'road_km',      cand.road_km,
                      'rpm',          cand.rpm
                    )
                  ),
                  cand.o,
                  cand.d
                FROM cand
                CROSS JOIN truck_pick t
                -- если trips.truck_id=uuid и public_id NULL — не создаём строку
                WHERE (t.truck_id IS NOT NULL)
                RETURNING id::text, truck_id::text;
                """,
                (cutoff_param, norm_limit),
            )
            rows = cur.fetchall() or []
            created = len(rows)
            c.commit()

        log.info(
            "autoplan.apply: created=%s, limit_used=%s, cutoff=%s, allow_old=%s, dry=%s",
            created,
            norm_limit,
            cutoff_param,
            ALLOW_OLD_FREIGHTS,
            dry_flag,
        )

        if write_audit:
            if created > 0:
                thresholds = _build_thresholds(
                    settings,
                    phase="apply",
                    extra={
                        "freights_days_back": days_back,
                        "limit_used": norm_limit,
                        "created": created,
                        "cutoff_date": str(cutoff_param),
                        "dry": False,
                    },
                )
                _autoplan_audit_log_batch(
                    items=[(trip_id_txt, truck_id_txt) for (trip_id_txt, truck_id_txt) in rows],
                    decision="apply",
                    reason="apply_planned_v1",
                    applied=True,
                    thresholds=thresholds,
                    payload={"created": created},
                )
            else:
                _autoplan_audit_log_event(
                    decision="noop",
                    reason="apply_no_candidates",
                    phase="apply",
                    settings=settings,
                    trip_id=None,
                    truck_id=NOOP_TRUCK_ID,
                    applied=False,
                    extra_thresholds={
                        "freights_days_back": days_back,
                        "limit_used": norm_limit,
                        "created": 0,
                        "cutoff_date": str(cutoff_param),
                        "dry": False,
                    },
                    payload={"note": "no candidates to apply (or no active truck)"},
                )

        result = {
            "ok": True,
            "created": created,
            "dry": False,
            "limit_used": norm_limit,
            "freights_days_back": days_back,
            "cutoff_date": str(cutoff_param),
            "flow_plan": _current_plan_name(),
            "allow_old_freights": ALLOW_OLD_FREIGHTS,
        }

    except Exception as e:
        log.exception("autoplan.apply failed: %s", e)
        emit_error(
            "autoplan.apply",
            correlation_id=correlation_id,
            payload={
                "error": str(e),
                "limit_raw": _to_jsonable(limit),
                "limit_used": norm_limit,
                "freights_days_back": days_back,
                "cutoff_date": str(cutoff_param),
                "dry": bool(dry_flag),
            },
        )
        raise
    else:
        emit_done("autoplan.apply", correlation_id=correlation_id, payload=result)
        return result


@shared_task(name="planner.autoplan.push_to_trips", ignore_result=False)
def task_planner_autoplan_push_to_trips(limit: Any = 200, **kwargs: Any) -> Dict[str, Any]:
    """В текущей модели отдельный push не нужен (apply уже создаёт planned trip)."""
    norm_limit = _normalize_apply_limit(limit, default=200)
    correlation_id = f"autoplan.push_to_trips:plan={_current_plan_name()}:limit={norm_limit}"

    emit_start(
        "autoplan.push_to_trips",
        correlation_id=correlation_id,
        payload={"limit_raw": _to_jsonable(limit), "limit_used": norm_limit},
    )

    result = {"ok": True, "pushed": 0, "flow_plan": _current_plan_name(), "limit_used": norm_limit}

    emit_done("autoplan.push_to_trips", correlation_id=correlation_id, payload=result)
    return result


@shared_task(name="planner.autoplan.confirm", ignore_result=False)
def task_planner_autoplan_confirm(limit: Any = 200, **kwargs: Any) -> Dict[str, Any]:
    """
    Фаза 2: planned -> confirmed.

    FIX:
      - никаких ::uuid для trips.id (у нас bigint)
      - UPDATE по id::text
      - аудит пишет trip_id=NULL + payload.trip_id_txt
    """
    settings = _get_autoplan_settings()
    norm_limit = _normalize_apply_limit(limit, default=200)

    correlation_id = f"autoplan.confirm:plan={_current_plan_name()}:limit={norm_limit}"
    emit_start(
        "autoplan.confirm",
        correlation_id=correlation_id,
        payload={"limit_raw": _to_jsonable(limit), "limit_used": norm_limit},
    )

    try:
        with _pg() as c, c.cursor() as cur:
            if not _table_exists(cur, "public.trips"):
                result = {
                    "ok": True,
                    "confirmed": 0,
                    "note": "trips missing",
                    "flow_plan": _current_plan_name(),
                }
                emit_done("autoplan.confirm", correlation_id=correlation_id, payload=result)
                return result

            status_col = "status" if _has_column(cur, "public", "trips", "status") else ("state" if _has_column(cur, "public", "trips", "state") else None)
            if not status_col:
                result = {
                    "ok": True,
                    "confirmed": 0,
                    "note": "trips has no status/state column",
                    "flow_plan": _current_plan_name(),
                }
                emit_done("autoplan.confirm", correlation_id=correlation_id, payload=result)
                return result

            has_confirmed_at = _has_column(cur, "public", "trips", "confirmed_at")
            has_updated_at = _has_column(cur, "public", "trips", "updated_at")

            set_confirmed_at = ", confirmed_at = COALESCE(confirmed_at, now())" if has_confirmed_at else ""
            set_updated_at = ", updated_at = now()" if has_updated_at else ""

            # Забираем planned рейсы (id как text)
            cur.execute(
                f"""
                WITH cand AS (
                  SELECT
                    t.id::text AS trip_id_txt,
                    t.truck_id::text AS truck_id_txt
                  FROM public.trips t
                  WHERE t.{status_col} = 'planned'
                  ORDER BY t.created_at DESC NULLS LAST
                  LIMIT %s
                ),
                upd AS (
                  UPDATE public.trips tt
                     SET {status_col} = 'confirmed'
                         {set_confirmed_at}
                         {set_updated_at}
                   FROM cand
                  WHERE tt.id::text = cand.trip_id_txt
                  RETURNING tt.id::text AS trip_id_txt, tt.truck_id::text AS truck_id_txt
                )
                SELECT trip_id_txt, truck_id_txt
                FROM upd;
                """,
                (norm_limit,),
            )
            rows = cur.fetchall() or []
            c.commit()

        confirmed = len(rows)
        if confirmed == 0:
            _autoplan_audit_log_event(
                decision="noop",
                reason="confirm_no_planned",
                phase="confirm",
                settings=settings,
                trip_id=None,
                truck_id=NOOP_TRUCK_ID,
                applied=False,
                extra_thresholds={"limit_used": norm_limit, "confirmed": 0},
                payload={"note": "no planned trips to confirm"},
            )
            result = {
                "ok": True,
                "confirmed": 0,
                "note": "no planned trips to confirm",
                "flow_plan": _current_plan_name(),
            }
            emit_done("autoplan.confirm", correlation_id=correlation_id, payload=result)
            return result

        # audit confirm batch (trip_id в uuid не лезет — уйдёт в payload.trip_id_txt)
        _autoplan_audit_log_batch(
            items=[(trip_id_txt, truck_id_txt) for (trip_id_txt, truck_id_txt) in rows],
            decision="confirm",
            reason="confirm_planned_v1",
            applied=True,
            thresholds=_build_thresholds(settings, phase="confirm", extra={"limit_used": norm_limit, "confirmed": confirmed}),
            payload={"confirmed": confirmed},
        )

        result = {
            "ok": True,
            "confirmed": confirmed,
            "limit_used": norm_limit,
            "flow_plan": _current_plan_name(),
        }

    except Exception as e:
        log.exception("autoplan.confirm failed: %s", e)
        emit_error("autoplan.confirm", correlation_id=correlation_id, payload={"error": str(e), "limit_used": norm_limit})
        raise
    else:
        emit_done("autoplan.confirm", correlation_id=correlation_id, payload=result)
        return result


# ─────────────────────────────────────────────
# CHAIN / FLOWLANG ALIAS
# ─────────────────────────────────────────────
@shared_task(name="task_autoplan_chain", ignore_result=False)
def task_autoplan_chain(
    limit: Any = 50,
    plan: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Верхнеуровневая цепочка автоплана.
    Важно: dry-run отключает confirm и делает apply без записи (см. apply.dry).
    """
    if isinstance(plan, bytes):
        try:
            plan = plan.decode("utf-8")
        except Exception:
            plan = plan.decode("utf-8", "replace")

    settings = _get_autoplan_settings(plan)
    default_chain_limit = getattr(settings, "chain_limit", 50)
    norm_limit = _normalize_apply_limit(limit, default=default_chain_limit)

    dry_run_flag = False
    if isinstance(limit, dict) and "dry" in limit:
        dry_run_flag = bool(limit.get("dry"))
    elif "dry" in kwargs:
        dry_run_flag = bool(kwargs.get("dry"))
    else:
        dry_run_flag = bool(getattr(settings, "chain_dry_run_only", False))

    enable_audit = bool(getattr(settings, "chain_enable_audit", True))
    enable_apply = bool(getattr(settings, "chain_enable_apply", True))
    enable_confirm = bool(getattr(settings, "chain_enable_confirm", True)) and not dry_run_flag

    payload: Dict[str, Any] = {}
    if isinstance(limit, dict):
        payload.update(limit)
    elif limit is not None:
        payload["limit"] = limit
    if plan is not None:
        payload["plan"] = plan
    payload["dry_run"] = dry_run_flag
    payload["chain_flags"] = {"enable_audit": enable_audit, "enable_apply": enable_apply, "enable_confirm": enable_confirm}
    for k, v in kwargs.items():
        payload.setdefault(k, v)

    log.info(
        "autoplan.chain: start (plan_env=%s, plan_arg=%r, limit=%s, payload=%r)",
        _current_plan_name(),
        plan,
        norm_limit,
        payload,
    )

    correlation_id = f"autoplan.chain:plan_env={_current_plan_name()}:plan_arg={plan}:limit={norm_limit}"
    emit_start(
        "autoplan.chain",
        correlation_id=correlation_id,
        payload=_to_jsonable(
            {
                "limit_raw": limit,
                "limit_used": norm_limit,
                "plan_arg": plan,
                "dry_run": dry_run_flag,
                "chain_flags": {"enable_audit": enable_audit, "enable_apply": enable_apply, "enable_confirm": enable_confirm},
                "extra_kwargs": kwargs,
            }
        ),
    )

    try:
        if enable_audit:
            audit_res = task_planner_autoplan_audit.run(limit=norm_limit, write_audit=True)
        else:
            audit_res = {"ok": True, "skipped": True, "reason": "audit_disabled_by_chain_settings", "flow_plan": _current_plan_name()}

        if enable_apply:
            apply_res = task_planner_autoplan_apply.run(limit=norm_limit, write_audit=True, dry=dry_run_flag)
            push_res = task_planner_autoplan_push_to_trips.run(limit=norm_limit)
        else:
            apply_res = {"ok": True, "skipped": True, "reason": "apply_disabled_by_chain_settings", "flow_plan": _current_plan_name()}
            push_res = {"ok": True, "skipped": True, "reason": "push_disabled_by_chain_settings", "flow_plan": _current_plan_name()}

        if enable_confirm:
            confirm_res = task_planner_autoplan_confirm.run(limit=norm_limit)
        else:
            confirm_res = {"ok": True, "skipped": True, "reason": "confirm_disabled_by_chain_settings_or_dry_run", "flow_plan": _current_plan_name()}

        result: Dict[str, Any] = {
            "ok": True,
            "flow_plan": _current_plan_name(),
            "plan_arg": plan,
            "limit_used": norm_limit,
            "settings_freights_days_back": getattr(settings, "freights_days_back", None),
            "settings_chain": {
                "enable_audit": enable_audit,
                "enable_apply": enable_apply,
                "enable_confirm": enable_confirm,
                "dry_run_only": dry_run_flag,
            },
            "phases": {"audit": audit_res, "apply": apply_res, "push_to_trips": push_res, "confirm": confirm_res},
            "payload": _to_jsonable(payload),
        }
        result = _to_jsonable(result)

        emit_done("autoplan.chain", correlation_id=correlation_id, payload=result)
        return result

    except Exception as e:
        log.exception("autoplan.chain failed: %s", e)
        emit_error("autoplan.chain", correlation_id=correlation_id, payload={"error": str(e), "limit_used": norm_limit, "plan_arg": plan})
        raise
