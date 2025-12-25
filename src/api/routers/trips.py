# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Path, Query
from typing import Any, Dict, List, Optional, Tuple
import os
import uuid
import datetime as dt
import logging

router = APIRouter(prefix="/api/trips", tags=["trips"])
log = logging.getLogger(__name__)

# --- ENV-флаги для маршрутизации/обогащения ---
_ROUTING_ENABLED = os.getenv("ROUTING_ENABLED", "1") == "1"
_ROUTING_ENRICH_ON_CONFIRM = os.getenv("ROUTING_ENRICH_ON_CONFIRM", "1") == "1"

# Плагин для автоплана: имя DB-функции (например, logistics_apply_autoplan)
_AUTOPLAN_DB_FUNCTION = os.getenv("TRIPS_AUTOPLAN_DB_FUNCTION", "").strip()

# Пытаемся подключить клиент маршрутизации (OSRM/Valhalla); если не выйдет — будет локальный fallback
_ROUTING_CLIENT = None
try:
    from services.routing_client import RoutingClient  # type: ignore

    _ROUTING_CLIENT = RoutingClient()
except Exception as _e:  # pragma: no cover - best-effort
    log.warning("routing_client not available, fallback to haversine only: %r", _e)


# --------------------------------------------------------------------------------------
# БАЗОВЫЕ УТИЛИТЫ РАБОТЫ С БД (psycopg3 -> psycopg2 fallback)
# --------------------------------------------------------------------------------------


def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _connect_pg():
    try:
        import psycopg  # type: ignore  # v3

        return psycopg.connect(_db_dsn())
    except Exception:  # pragma: no cover - fallback
        import psycopg2 as psycopg  # type: ignore

        return psycopg.connect(_db_dsn())


def _columns(conn, table: str, schema: str = "public") -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            """,
            (schema, table),
        )
        return {r[0] for r in cur.fetchall()}


def _col(cols: set[str], *cands: str) -> Optional[str]:
    for c in cands:
        if c in cols:
            return c
    return None


# --------------------------------------------------------------------------------------
# ПЛАНИРОВАНИЕ
# --------------------------------------------------------------------------------------


@router.post("/plan")
def plan_trip(payload: Dict[str, Any] = Body(default={})):
    """
    Планирование рейса / автоплан.

    Режимы:

    1) Режим "одиночный рейс" (низкоуровневый):

       payload: {
         "truck_id": "...",
         "planned_load_window_start": "...",   # ISO-строки
         "planned_load_window_end": "...",
         "planned_unload_window_start": "...",
         "planned_unload_window_end": "...",
         "meta": { ... }                       # опционально, попадёт в jsonb meta/notes
       }

       -> создаётся строка в public.trips со статусом draft.

    2) Режим "автоплан для консоли логиста":

       payload: {
         "date":   "YYYY-MM-DD",
         "window": "day" | "rolling24" | "custom"
       }

       -> если сконфигурирована TRIPS_AUTOPLAN_DB_FUNCTION, вызывается
          соответствующая DB-функция:
              SELECT <fn>(date, window)
          и её результат (dict/JSON) возвращается как "result";

          если функции нет или она падает — возвращается безопасный stub-ответ,
          чтобы UI логиста не ломался.
    """
    conn = _connect_pg()
    try:
        cols = _columns(conn, "trips")

        truck_id = payload.get("truck_id")
        autoplan_date_raw = payload.get("date")
        autoplan_window = (payload.get("window") or "day").strip() or "day"

        # --- РЕЖИМ АВТОПЛАНА ДЛЯ КОНСОЛИ ЛОГИСТА -----------------------------
        # Если truck_id не передан, но есть date/window — считаем, что нас вызвали
        # с консоли логиста для автоплана. В этом режиме мы не создаём строку
        # в trips, а только запускаем (или имитируем запуск) автопланировщика.
        if not truck_id and autoplan_date_raw:
            log.info(
                "Autoplan request: date=%s window=%s payload_keys=%s",
                autoplan_date_raw,
                autoplan_window,
                list(payload.keys()),
            )

            # Валидация даты
            try:
                autoplan_date = dt.date.fromisoformat(str(autoplan_date_raw))
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="invalid 'date', expected format YYYY-MM-DD",
                )

            # Если настроена DB-функция — пытаемся вызвать её
            if _AUTOPLAN_DB_FUNCTION:
                try:
                    with conn.cursor() as cur:
                        # Ожидаем сигнатуру fn(date, window_text) -> json/jsonb или dict/text
                        sql = (
                            f"SELECT {_AUTOPLAN_DB_FUNCTION}(%s::date, %s::text)"  # nosec - fn name из ENV
                        )
                        cur.execute(sql, (autoplan_date, autoplan_window))
                        row = cur.fetchone()
                    # Коммитим, т.к. функция может делать изменения
                    conn.commit()
                except Exception as e:
                    log.warning(
                        "autoplan db function failed fn=%s date=%s window=%s: %r",
                        _AUTOPLAN_DB_FUNCTION,
                        autoplan_date,
                        autoplan_window,
                        e,
                    )
                    try:
                        conn.rollback()
                    except Exception:  # pragma: no cover - best-effort
                        pass
                    return {
                        "ok": False,
                        "mode": "autoplan_error",
                        "date": autoplan_date.isoformat(),
                        "window": autoplan_window,
                        "engine": f"db_function:{_AUTOPLAN_DB_FUNCTION}",
                        "error": repr(e),
                        "note": "autoplan db function failed, no changes applied",
                    }

                result_payload: Optional[Dict[str, Any]] = None
                if row is not None:
                    raw = row[0]
                    if isinstance(raw, dict):
                        # уже dict из psycopg/jsonb
                        result_payload = raw  # type: ignore[assignment]
                    else:
                        # пробуем распарсить как JSON, иначе просто строка
                        try:
                            import json

                            if isinstance(raw, (bytes, bytearray, memoryview)):
                                raw = bytes(raw).decode("utf-8", "replace")
                            result_payload = json.loads(raw)
                        except Exception:
                            result_payload = {"raw_result": str(raw)}

                response: Dict[str, Any] = {
                    "ok": True,
                    "mode": "autoplan",
                    "date": autoplan_date.isoformat(),
                    "window": autoplan_window,
                    "engine": f"db_function:{_AUTOPLAN_DB_FUNCTION}",
                }
                if result_payload is not None:
                    response["result"] = result_payload
                return response

            # Если движок автоплана ещё не настроен — мягкий stub-ответ
            log.info(
                "Autoplan stub used (no TRIPS_AUTOPLAN_DB_FUNCTION configured): "
                "date=%s window=%s",
                autoplan_date.isoformat(),
                autoplan_window,
            )
            return {
                "ok": True,
                "mode": "autoplan_stub",
                "date": autoplan_date.isoformat(),
                "window": autoplan_window,
                "engine": "stub",
                "note": (
                    "autoplan engine is not configured yet "
                    "(set TRIPS_AUTOPLAN_DB_FUNCTION to enable DB-backed planner)"
                ),
            }

        # --- РЕЖИМ СОЗДАНИЯ КОНКРЕТНОГО РЕЙСА --------------------------------
        if not truck_id and not autoplan_date_raw:
            raise HTTPException(400, "either truck_id or date is required")

        if not truck_id:
            # Теоретически сюда попасть не должны, но оставляем явную проверку
            raise HTTPException(400, "truck_id required for single-trip planning")

        status_col = _col(cols, "status") or "status"
        ts_col = _col(cols, "updated_at", "ts")
        meta_col = _col(cols, "meta", "notes")

        ls = payload.get("planned_load_window_start")
        le = payload.get("planned_load_window_end")
        us = payload.get("planned_unload_window_start")
        ue = payload.get("planned_unload_window_end")

        fields: List[str] = ["id", "truck_id", status_col]
        values: List[Any] = [str(uuid.uuid4()), truck_id, "draft"]

        if ls and _col(cols, "planned_load_window_start"):
            fields.append("planned_load_window_start")
            values.append(ls)
        if le and _col(cols, "planned_load_window_end"):
            fields.append("planned_load_window_end")
            values.append(le)
        if us and _col(cols, "planned_unload_window_start"):
            fields.append("planned_unload_window_start")
            values.append(us)
        if ue and _col(cols, "planned_unload_window_end"):
            fields.append("planned_unload_window_end")
            values.append(ue)

        if meta_col and isinstance(payload.get("meta"), dict):
            fields.append(meta_col)
            values.append(json_dumps(payload["meta"]))

        if ts_col:
            fields.append(ts_col)
            values.append(dt.datetime.utcnow())

        with conn.cursor() as cur:
            sql = (
                f"INSERT INTO public.trips ({','.join(fields)}) "
                f"VALUES ({','.join(['%s']*len(values))})"
            )
            cur.execute(sql, values)
            conn.commit()
            return {"ok": True, "trip_id": values[0]}
    except HTTPException:
        raise
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:  # pragma: no cover - best-effort
            pass
        raise HTTPException(500, f"plan_failed: {ex!r}")
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover - best-effort
            pass


# --------------------------------------------------------------------------------------
# READ-ONLY: ПОСЛЕДНИЙ ПРОГОН АВТОПЛАНА (без запуска нового plan)
# --------------------------------------------------------------------------------------


@router.get("/autoplan/latest")
def autoplan_latest(limit: int = Query(200, ge=1, le=500)) -> Dict[str, Any]:
    """
    Read-only: вернуть последний прогон DB-автоплана (logistics.autoplan_run)
    и назначения (logistics.autoplan_assignment), НЕ запуская новый /plan.

    Формат максимально совместим с UI autoplan_console.html:
    - верхний уровень: ok/mode/date/window/engine
    - result: ok/mode/run_id/window/summary/assignments_sample (+payload/created_at если есть)
    """
    conn = _connect_pg()
    try:
        run_cols = _columns(conn, "autoplan_run", schema="logistics")

        if not run_cols:
            return {
                "ok": True,
                "mode": "autoplan_latest",
                "engine": "db_table:logistics.autoplan_run",
                "note": "autoplan tables not found (apply autoplan engine SQL patch first)",
                "result": {"ok": False, "mode": "autoplan_latest", "note": "no_tables"},
            }

        # compat: колонка окна может называться plan_window или "window"
        if "plan_window" in run_cols:
            win_col = "plan_window"
        elif "window" in run_cols:
            win_col = '"window"'
        else:
            win_col = "NULL::text"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    run_id,
                    created_at,
                    requested_date,
                    {win_col} AS plan_window,
                    window_start,
                    window_end,
                    ok,
                    loads_considered,
                    vehicles_count,
                    assignments_count,
                    delayed_assignments,
                    avg_start_delay_min,
                    error,
                    payload
                FROM logistics.autoplan_run
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()

        if not row:
            return {
                "ok": True,
                "mode": "autoplan_latest",
                "engine": "db_table:logistics.autoplan_run",
                "note": "no autoplan runs yet",
                "result": {"ok": False, "mode": "autoplan_latest", "note": "no_runs"},
            }

        (
            run_id,
            created_at,
            requested_date,
            plan_window,
            window_start,
            window_end,
            ok,
            loads_considered,
            vehicles_count,
            assignments_count,
            delayed_assignments,
            avg_start_delay_min,
            error,
            payload,
        ) = row

        # payload jsonb: psycopg3 может вернуть dict, psycopg2 чаще строку
        payload_obj: Any = payload
        if isinstance(payload_obj, (bytes, bytearray, memoryview)):
            try:
                payload_obj = bytes(payload_obj).decode("utf-8", "replace")
            except Exception:
                payload_obj = str(payload_obj)

        if isinstance(payload_obj, str):
            try:
                import json

                payload_obj = json.loads(payload_obj)
            except Exception:
                payload_obj = {"raw_payload": payload_obj}

        # assignments_sample
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    vehicle_code,
                    seq,
                    load_id,
                    planned_pickup_at   AS pickup_planned_at,
                    planned_delivery_at AS delivery_planned_at,
                    start_delay_min,
                    note
                FROM logistics.autoplan_assignment
                WHERE run_id = %s
                ORDER BY vehicle_code, seq
                LIMIT %s
                """,
                (run_id, limit),
            )
            arows = cur.fetchall()

        akeys = [
            "vehicle_code",
            "seq",
            "load_id",
            "pickup_planned_at",
            "delivery_planned_at",
            "start_delay_min",
            "note",
        ]
        assignments_sample = [dict(zip(akeys, r)) for r in arows]

        summary = {
            "window_start": window_start,
            "window_end": window_end,
            "loads_considered": loads_considered,
            "vehicles_count": vehicles_count,
            "assignments_count": assignments_count,
            "delayed_assignments": delayed_assignments,
            "avg_start_delay_min": avg_start_delay_min,
        }

        resp: Dict[str, Any] = {
            "ok": True,
            "mode": "autoplan_latest",
            "date": requested_date.isoformat() if requested_date is not None else None,
            "window": plan_window,
            "engine": "db_table:logistics.autoplan_run",
            "result": {
                "ok": bool(ok),
                "mode": "autoplan_db_v0_2",
                "run_id": str(run_id),
                "window": plan_window,
                "summary": summary,
                "assignments_sample": assignments_sample,
            },
        }

        if created_at is not None:
            resp["result"]["created_at"] = created_at.isoformat()

        if error:
            resp["result"]["error"] = error

        if payload_obj is not None:
            resp["result"]["payload"] = payload_obj

        return resp
    except HTTPException:
        raise
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, f"autoplan_latest_failed: {ex!r}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# READ-ONLY: ИСТОРИЯ ПРОГОНОВ АВТОПЛАНА + ЗАГРУЗКА ПРОГОНА ПО run_id (без запуска нового plan)
# DevTask 121
# --------------------------------------------------------------------------------------


@router.get("/autoplan/runs")
def autoplan_runs(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """
    Read-only: вернуть список последних прогонов DB-автоплана (logistics.autoplan_run),
    без запуска нового /plan.
    """
    conn = _connect_pg()
    try:
        run_cols = _columns(conn, "autoplan_run", schema="logistics")
        if not run_cols:
            return {
                "ok": True,
                "mode": "autoplan_runs",
                "engine": "db_table:logistics.autoplan_run",
                "note": "autoplan tables not found (apply autoplan engine SQL patch first)",
                "items": [],
            }

        if "plan_window" in run_cols:
            win_expr = "plan_window"
        elif "window" in run_cols:
            win_expr = '"window"'
        else:
            win_expr = "NULL::text"

        def col_or_null(name: str, cast: str) -> str:
            return name if name in run_cols else f"NULL::{cast} AS {name}"

        order_expr = "created_at" if "created_at" in run_cols else "run_id"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    run_id,
                    {col_or_null("created_at", "timestamptz")},
                    {col_or_null("requested_date", "date")},
                    {win_expr} AS plan_window,
                    {col_or_null("window_start", "timestamptz")},
                    {col_or_null("window_end", "timestamptz")},
                    {col_or_null("ok", "boolean")},
                    {col_or_null("loads_considered", "int")},
                    {col_or_null("vehicles_count", "int")},
                    {col_or_null("assignments_count", "int")},
                    {col_or_null("delayed_assignments", "int")},
                    {col_or_null("avg_start_delay_min", "numeric")},
                    {col_or_null("error", "text")}
                FROM logistics.autoplan_run
                ORDER BY {order_expr} DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        def iso(v: Any) -> Any:
            if v is None:
                return None
            try:
                return v.isoformat()
            except Exception:
                return str(v)

        items: List[Dict[str, Any]] = []
        for r in rows:
            (
                run_id,
                created_at,
                requested_date,
                plan_window,
                window_start,
                window_end,
                ok,
                loads_considered,
                vehicles_count,
                assignments_count,
                delayed_assignments,
                avg_start_delay_min,
                error,
            ) = r

            try:
                if avg_start_delay_min is not None and not isinstance(avg_start_delay_min, (int, float)):
                    avg_start_delay_min = float(avg_start_delay_min)
            except Exception:
                pass

            items.append(
                {
                    "run_id": str(run_id),
                    "created_at": iso(created_at),
                    "date": iso(requested_date),
                    "window": plan_window,
                    "window_start": iso(window_start),
                    "window_end": iso(window_end),
                    "ok": (bool(ok) if ok is not None else None),
                    "loads_considered": loads_considered,
                    "vehicles_count": vehicles_count,
                    "assignments_count": assignments_count,
                    "delayed_assignments": delayed_assignments,
                    "avg_start_delay_min": avg_start_delay_min,
                    "error": error,
                }
            )

        return {
            "ok": True,
            "mode": "autoplan_runs",
            "engine": "db_table:logistics.autoplan_run",
            "items": items,
        }
    except HTTPException:
        raise
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, f"autoplan_runs_failed: {ex!r}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/autoplan/run/{run_id}")
def autoplan_run_by_id(run_id: str, limit: int = Query(200, ge=1, le=2000)) -> Dict[str, Any]:
    """
    Read-only: вернуть конкретный прогон DB-автоплана (logistics.autoplan_run) и назначения
    (logistics.autoplan_assignment) по run_id, НЕ запуская новый /plan.
    """
    conn = _connect_pg()
    try:
        run_cols = _columns(conn, "autoplan_run", schema="logistics")
        if not run_cols:
            return {
                "ok": True,
                "mode": "autoplan_run",
                "engine": "db_table:logistics.autoplan_run",
                "note": "autoplan tables not found (apply autoplan engine SQL patch first)",
                "result": {"ok": False, "mode": "autoplan_run", "note": "no_tables"},
            }

        if "plan_window" in run_cols:
            win_expr = "plan_window"
        elif "window" in run_cols:
            win_expr = '"window"'
        else:
            win_expr = "NULL::text"

        def col_or_null(name: str, cast: str) -> str:
            return name if name in run_cols else f"NULL::{cast} AS {name}"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    run_id,
                    {col_or_null("created_at", "timestamptz")},
                    {col_or_null("requested_date", "date")},
                    {win_expr} AS plan_window,
                    {col_or_null("window_start", "timestamptz")},
                    {col_or_null("window_end", "timestamptz")},
                    {col_or_null("ok", "boolean")},
                    {col_or_null("loads_considered", "int")},
                    {col_or_null("vehicles_count", "int")},
                    {col_or_null("assignments_count", "int")},
                    {col_or_null("delayed_assignments", "int")},
                    {col_or_null("avg_start_delay_min", "numeric")},
                    {col_or_null("error", "text")},
                    {col_or_null("payload", "jsonb")}
                FROM logistics.autoplan_run
                WHERE run_id::text = %s
                LIMIT 1
                """,
                (run_id,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(404, "run_not_found")

        (
            run_id_db,
            created_at,
            requested_date,
            plan_window,
            window_start,
            window_end,
            ok,
            loads_considered,
            vehicles_count,
            assignments_count,
            delayed_assignments,
            avg_start_delay_min,
            error,
            payload,
        ) = row

        try:
            if avg_start_delay_min is not None and not isinstance(avg_start_delay_min, (int, float)):
                avg_start_delay_min = float(avg_start_delay_min)
        except Exception:
            pass

        payload_obj: Any = payload
        if isinstance(payload_obj, (bytes, bytearray, memoryview)):
            try:
                payload_obj = bytes(payload_obj).decode("utf-8", "replace")
            except Exception:
                payload_obj = str(payload_obj)

        if isinstance(payload_obj, str):
            try:
                import json
                payload_obj = json.loads(payload_obj)
            except Exception:
                payload_obj = {"raw_payload": payload_obj}

        rid = str(run_id_db)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    vehicle_code,
                    seq,
                    load_id,
                    planned_pickup_at   AS pickup_planned_at,
                    planned_delivery_at AS delivery_planned_at,
                    start_delay_min,
                    note
                FROM logistics.autoplan_assignment
                WHERE run_id::text = %s
                ORDER BY vehicle_code, seq
                LIMIT %s
                """,
                (rid, limit),
            )
            arows = cur.fetchall()

        akeys = [
            "vehicle_code",
            "seq",
            "load_id",
            "pickup_planned_at",
            "delivery_planned_at",
            "start_delay_min",
            "note",
        ]
        assignments_sample = [dict(zip(akeys, r)) for r in arows]

        summary = {
            "window_start": window_start,
            "window_end": window_end,
            "loads_considered": loads_considered,
            "vehicles_count": vehicles_count,
            "assignments_count": assignments_count,
            "delayed_assignments": delayed_assignments,
            "avg_start_delay_min": avg_start_delay_min,
        }

        resp: Dict[str, Any] = {
            "ok": True,
            "mode": "autoplan_run",
            "date": requested_date.isoformat() if requested_date is not None else None,
            "window": plan_window,
            "engine": "db_table:logistics.autoplan_run",
            "result": {
                "ok": bool(ok),
                "mode": "autoplan_db_v0_2",
                "run_id": rid,
                "window": plan_window,
                "summary": summary,
                "assignments_sample": assignments_sample,
            },
        }

        if created_at is not None:
            resp["result"]["created_at"] = created_at.isoformat()
        if error:
            resp["result"]["error"] = error
        if payload_obj is not None:
            resp["result"]["payload"] = payload_obj

        return resp
    except HTTPException:
        raise
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, f"autoplan_run_failed: {ex!r}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

# --------------------------------------------------------------------------------------
# СТАТУСЫ/ФАКТЫ
# --------------------------------------------------------------------------------------


def _update_trip_status(
    trip_id: str, new_status: str, meta_patch: Optional[Dict[str, Any]] = None
):
    conn = _connect_pg()
    try:
        cols = _columns(conn, "trips")
        status_col = _col(cols, "status") or "status"
        ts_col = _col(cols, "updated_at", "ts")
        meta_col = _col(cols, "meta", "notes")

        set_parts: List[str] = [f"{status_col}=%s"]
        params: List[Any] = [new_status]

        if ts_col:
            set_parts.append(f"{ts_col}=now()")

        if meta_patch and meta_col:
            set_parts.append(
                f"{meta_col}=COALESCE({meta_col}, '{{}}'::jsonb) || %s::jsonb"
            )
            params.append(json_dumps(meta_patch))

        params.append(trip_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE public.trips SET {', '.join(set_parts)} WHERE id=%s", params
            )
            if getattr(cur, "rowcount", 0) == 0:
                raise HTTPException(404, "trip_not_found")
            conn.commit()
            return {"ok": True, "trip_id": trip_id, "status": new_status}
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


@router.post("/{trip_id}/confirm")
def confirm_trip(trip_id: str = Path(...)):
    """
    Подтверждение рейса:
    1) обновляем статус -> confirmed;
    2) (опционально) обогащаем сегменты road_km/drive_sec/route_polyline через маршрутизатор.
       Любые ошибки маршрутизации логируются и НЕ ломают подтверждение (NDC).
    """
    result = _update_trip_status(
        trip_id,
        "confirmed",
        {"manual": {"at": dt.datetime.utcnow().isoformat()}},
    )
    if _ROUTING_ENABLED and _ROUTING_ENRICH_ON_CONFIRM:
        try:
            _maybe_enrich_segments_with_routing(trip_id)
        except Exception as e:  # pragma: no cover - best-effort
            # не валим confirm, просто предупреждаем
            log.warning("routing_enrich_failed trip_id=%s: %r", trip_id, e)
    return result


@router.post("/{trip_id}/start")
def start_trip(trip_id: str = Path(...)):
    return _update_trip_status(trip_id, "in_progress")


@router.post("/{trip_id}/finish")
def finish_trip(trip_id: str = Path(...)):
    return _update_trip_status(trip_id, "finished")


@router.post("/{trip_id}/facts")
def trip_facts(trip_id: str = Path(...), facts: Dict[str, Any] = Body(default={})):
    """
    Приём фактических затрат по рейсу. Обновляем только существующие колонки.

    Ожидаемый payload (поля опциональны, обновляются только существующие в таблице):
    {
      "price_rub_actual": ...
      "fuel_cost_rub_actual": ...
      "tolls_rub_actual": ...
      "other_costs_rub_actual": ...
    }
    """
    conn = _connect_pg()
    try:
        cols = _columns(conn, "trips")
        set_pairs: List[str] = []
        vals: List[Any] = []
        for k in (
            "price_rub_actual",
            "fuel_cost_rub_actual",
            "tolls_rub_actual",
            "other_costs_rub_actual",
        ):
            if k in facts and k in cols:
                set_pairs.append(f"{k}=%s")
                vals.append(facts[k])

        if not set_pairs:
            return {"ok": True, "note": "no_fact_columns"}

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE public.trips SET {', '.join(set_pairs)} WHERE id=%s",
                (*vals, trip_id),
            )
            conn.commit()
            return {"ok": True, "trip_id": trip_id}
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


# --------------------------------------------------------------------------------------
# ОПЕРАТОРСКАЯ КОНСОЛЬ ЛОГИСТА
# --------------------------------------------------------------------------------------


@router.get("/operator/overview")
def get_operator_overview_for_logistic(
    date: dt.date,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Обзор рейсов для консоли логиста.

    Используется HTML-страницей:
      src/static/logistics/logistics_console.html

    Параметры:
    - date: дата смены/планирования (формат YYYY-MM-DD).

    Логика:
    - Берём таблицу public.trips (адаптируясь к схеме через _columns/_col);
    - Пытаемся найти подходящие колонки для:
      id, статус, код машины, города, planned_* окна, задержку;
    - Фильтруем по дате (по planned_* окну или planned_date, если есть такие колонки).
    - Если в базе нет ни одной строки под этот фильтр — отдаём демонстрационный
      набор рейсов (stub), чтобы консоль была живой даже на пустой БД.

    Возвращаемый формат (JSON):
    {
      "trips": [
        {
          "trip_id": "...",
          "vehicle_code": "...",
          "load_city": "...",
          "unload_city": "...",
          "planned_load_window_start": "...",
          "planned_load_window_end": "...",
          "planned_unload_window_start": "...",
          "planned_unload_window_end": "...",
          "status": "planned|in_progress|finished|delayed|error|...",
          "delay_minutes": 0
        },
        ...
      ]
    }
    """
    conn = _connect_pg()
    try:
        cols = _columns(conn, "trips")
        id_col = _col(cols, "id", "trip_id")
        if not id_col:
            raise HTTPException(500, "trips_table_missing_id")

        status_col = _col(cols, "status") or "status"
        vehicle_col = _col(
            cols,
            "truck_code",
            "truck_name",
            "truck_id",
            "vehicle_code",
            "vehicle_name",
            "vehicle_id",
        )
        load_city_col = _col(cols, "load_city", "from_city", "origin_city")
        unload_city_col = _col(cols, "unload_city", "to_city", "dest_city")

        pls_col = _col(cols, "planned_load_window_start", "load_window_start")
        ple_col = _col(cols, "planned_load_window_end", "load_window_end")
        pus_col = _col(cols, "planned_unload_window_start", "unload_window_start")
        pue_col = _col(cols, "planned_unload_window_end", "unload_window_end")

        delay_col = _col(cols, "delay_minutes", "delay_min", "delay")

        select_parts: List[str] = [f"{id_col} AS trip_id", f"{status_col} AS status"]
        if vehicle_col:
            select_parts.append(f"{vehicle_col} AS vehicle_code")
        if load_city_col:
            select_parts.append(f"{load_city_col} AS load_city")
        if unload_city_col:
            select_parts.append(f"{unload_city_col} AS unload_city")
        if pls_col:
            select_parts.append(f"{pls_col} AS planned_load_window_start")
        if ple_col:
            select_parts.append(f"{ple_col} AS planned_load_window_end")
        if pus_col:
            select_parts.append(f"{pus_col} AS planned_unload_window_start")
        if pue_col:
            select_parts.append(f"{pue_col} AS planned_unload_window_end")
        if delay_col:
            select_parts.append(f"{delay_col} AS delay_minutes")

        # Выбираем, по какому полю фильтровать по дате
        filter_col = pls_col or pus_col or _col(cols, "planned_date", "service_date")
        params: List[Any] = []
        where_clause = ""
        if filter_col:
            where_clause = f"WHERE {filter_col}::date = %s"
            params.append(date)
        else:
            where_clause = ""

        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM public.trips "
            f"{where_clause} "
            f"ORDER BY {id_col} DESC"
        )

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]

        trips: List[Dict[str, Any]] = []
        for row in rows:
            rec: Dict[str, Any] = dict(zip(colnames, row))
            delay_val = rec.get("delay_minutes")
            if delay_val is None:
                delay = 0
            else:
                try:
                    delay = int(delay_val)
                except Exception:
                    delay = 0
            rec["delay_minutes"] = delay
            trips.append(rec)

        # Если в базе ничего нет — отдаём демонстрационный stub-набор,
        # чтобы консоль логиста была живой уже сейчас.
        if not trips:
            log.info(
                "operator_overview: no DB trips for date=%s, returning stub sample",
                date,
            )
            stub_trips: List[Dict[str, Any]] = [
                {
                    "trip_id": "DEMO-T-1001",
                    "vehicle_code": "МАЗ-001",
                    "load_city": "Москва",
                    "unload_city": "Тверь",
                    "planned_load_window_start": f"{date.isoformat()} 08:00",
                    "planned_load_window_end": f"{date.isoformat()} 09:00",
                    "planned_unload_window_start": f"{date.isoformat()} 13:00",
                    "planned_unload_window_end": f"{date.isoformat()} 14:00",
                    "status": "planned",
                    "delay_minutes": 0,
                },
                {
                    "trip_id": "DEMO-T-1002",
                    "vehicle_code": "КАМАЗ-007",
                    "load_city": "Москва",
                    "unload_city": "Ярославль",
                    "planned_load_window_start": f"{date.isoformat()} 07:30",
                    "planned_load_window_end": f"{date.isoformat()} 08:30",
                    "planned_unload_window_start": f"{date.isoformat()} 15:00",
                    "planned_unload_window_end": f"{date.isoformat()} 16:30",
                    "status": "in_progress",
                    "delay_minutes": 15,
                },
                {
                    "trip_id": "DEMO-T-1003",
                    "vehicle_code": "ГАЗель-015",
                    "load_city": "Дубна",
                    "unload_city": "Москва",
                    "planned_load_window_start": f"{date.isoformat()} 10:00",
                    "planned_load_window_end": f"{date.isoformat()} 11:00",
                    "planned_unload_window_start": f"{date.isoformat()} 17:00",
                    "planned_unload_window_end": f"{date.isoformat()} 18:00",
                    "status": "delayed",
                    "delay_minutes": 35,
                },
            ]
            return {"trips": stub_trips}

        return {"trips": trips}
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


# --------------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНОЕ: МАРШРУТИЗАЦИЯ И ОБОГАЩЕНИЕ СЕГМЕНТОВ
# --------------------------------------------------------------------------------------


def _maybe_enrich_segments_with_routing(trip_id: str) -> None:
    """
    Находим сегменты рейса и, если в схеме есть road_km/drive_sec/route_polyline и координаты,
    дополняем отсутствующие значения (безошибочно при отсутствии колонок/данных).
    """
    conn = _connect_pg()
    try:
        seg_cols = _columns(conn, "trip_segments")
        # Проверяем, что есть базовые поля
        if "trip_id" not in seg_cols or "id" not in seg_cols:
            return

        # Какие поля можем потенциально обновлять
        allow_road = "road_km" in seg_cols
        allow_drive = "drive_sec" in seg_cols
        allow_poly = "route_polyline" in seg_cols

        # Какие координаты вообще есть в схеме
        coord_keys = [
            k
            for k in (
                "load_lat",
                "load_lon",
                "unload_lat",
                "unload_lon",
                "start_lat",
                "start_lon",
                "end_lat",
                "end_lon",
                "origin_lat",
                "origin_lon",
                "dest_lat",
                "dest_lon",
            )
            if k in seg_cols
        ]

        # Если ни одного поля для апдейта/координат — выходим молча
        if not (allow_road or allow_drive or allow_poly):
            return
        if not coord_keys:
            return

        # Собираем SELECT только по доступным колонкам
        select_cols: List[str] = ["id"] + coord_keys
        # Добавим и текущие значения маршрута, чтобы понимать "надо ли"
        for k in ("road_km", "drive_sec", "route_polyline"):
            if k in seg_cols and k not in select_cols:
                select_cols.append(k)

        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(select_cols)} "
                f"FROM public.trip_segments "
                f"WHERE trip_id=%s",
                (trip_id,),
            )
            rows = cur.fetchall()

        if not rows:
            return

        # Подготовим маппинг имени колонки в индекс результата
        idx: Dict[str, int] = {col: i for i, col in enumerate(select_cols)}

        # Проходим по сегментам, запрашиваем маршрут и обновляем только пустые поля
        updates: List[Tuple[Any, float, int, Optional[str]]] = []  # (seg_id, road_km, drive_sec, poly)

        for row in rows:
            seg_id = row[idx["id"]]
            coords = _extract_coords_from_row(row, idx)
            if not coords:
                continue

            # Определяем, надо ли реально обновлять
            cur_road = row[idx["road_km"]] if "road_km" in idx else None
            cur_drive = row[idx["drive_sec"]] if "drive_sec" in idx else None
            cur_poly = row[idx["route_polyline"]] if "route_polyline" in idx else None

            need_any = False
            if allow_road and (cur_road is None or float(cur_road) == 0.0):
                need_any = True
            if allow_drive and (cur_drive is None or int(cur_drive) == 0):
                need_any = True
            if allow_poly and (cur_poly is None or str(cur_poly).strip() == ""):
                need_any = True

            if not need_any:
                continue

            dist_m, dur_s, poly, backend = _route_distance_duration(coords)
            road_km = dist_m / 1000.0
            drive_sec = int(dur_s)

            # Логируем только debug-подробности
            log.debug(
                "routing_enrich seg_id=%s backend=%s dist_km=%.2f drive_sec=%s",
                seg_id,
                backend,
                road_km,
                drive_sec,
            )
            updates.append((seg_id, road_km, drive_sec, poly))

        if not updates:
            return

        # Применяем обновления (в одном транзакционном куске, но мягко: не валим весь цикл,
        # чтобы не ломать частичный успех)
        with conn.cursor() as cur:
            for seg_id, road_km, drive_sec, poly in updates:
                set_parts: List[str] = []
                params: List[Any] = []
                if allow_road and road_km is not None:
                    set_parts.append("road_km=%s")
                    params.append(road_km)
                if allow_drive and drive_sec is not None:
                    set_parts.append("drive_sec=%s")
                    params.append(drive_sec)
                if allow_poly and poly is not None:
                    set_parts.append("route_polyline=%s")
                    params.append(poly)
                if not set_parts:
                    continue
                params.append(seg_id)
                cur.execute(
                    f"UPDATE public.trip_segments SET {', '.join(set_parts)} WHERE id=%s",
                    params,
                )
            conn.commit()

    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


def _extract_coords_from_row(
    row: Tuple[Any, Any], idx: Dict[str, int]
) -> Optional[List[Tuple[float, float]]]:
    """
    Достаём координаты сегмента: (lat, lon) -> (lat, lon).
    Поддерживаем разные схемы: load/unload, start/end, origin/dest.
    """

    def pick_latlon(lat_key: str, lon_key: str) -> Optional[Tuple[float, float]]:
        if lat_key in idx and lon_key in idx:
            lat = row[idx[lat_key]]
            lon = row[idx[lon_key]]
            if lat is None or lon is None:
                return None
            try:
                return float(lat), float(lon)
            except Exception:
                return None
        return None

    a = (
        pick_latlon("load_lat", "load_lon")
        or pick_latlon("start_lat", "start_lon")
        or pick_latlon("origin_lat", "origin_lon")
    )
    b = (
        pick_latlon("unload_lat", "unload_lon")
        or pick_latlon("end_lat", "end_lon")
        or pick_latlon("dest_lat", "dest_lon")
    )

    if a and b:
        return [a, b]
    return None


def _route_distance_duration(
    coords: List[Tuple[float, float]]
) -> Tuple[float, float, Optional[str], str]:
    """
    Универсальный вызов маршрутизатора:
    - если доступен services.routing_client и ROUTING_ENABLED=1 — используем его (async через asyncio.run),
    - иначе — грубый fallback Haversine с 60 км/ч.

    Возвращает: (distance_m, duration_s, polyline|None, backend)
    """
    # Попробуем через наш client
    if _ROUTING_ENABLED and _ROUTING_CLIENT:
        try:
            import asyncio

            data = asyncio.run(
                _ROUTING_CLIENT.route(coords)
            )  # safe: endpoint выполняется в threadpool
            return (
                float(data.get("distance_m", 0.0)),
                float(data.get("duration_s", 0.0)),
                data.get("polyline"),
                str(data.get("backend") or "unknown"),
            )
        except Exception as e:  # pragma: no cover
            log.warning("routing_client.route failed, fallback to haversine: %r", e)

    # Локальный fallback
    dist_km = _haversine_path_km(coords)
    dur_s = (dist_km / 60.0) * 3600.0  # 60 км/ч
    return dist_km * 1000.0, dur_s, None, "haversine"


# --------------------------------------------------------------------------------------
# МАТЕМАТИКА: HAVERSINE
# --------------------------------------------------------------------------------------


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371.0088
    from math import radians, sin, cos, asin, sqrt

    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dl / 2) ** 2
    return 2 * R * asin(sqrt(h))


def _haversine_path_km(coords: List[Tuple[float, float]]) -> float:
    s = 0.0
    for i in range(1, len(coords)):
        s += _haversine_km(coords[i - 1], coords[i])
    return s


# --------------------------------------------------------------------------------------
# JSON helper
# --------------------------------------------------------------------------------------


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
