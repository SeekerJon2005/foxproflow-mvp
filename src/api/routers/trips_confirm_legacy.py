# -*- coding: utf-8 -*-
# file: src/api/routers/trips_confirm.py
from __future__ import annotations

import os
import json
import math
import urllib.request
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP  # безопасное округление

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse

# --------------------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------------------
# Основные ручки подтверждения рейса и переобогащения сегментов:
router = APIRouter(prefix="/api/autoplan/trips", tags=["autoplan"])
# Конфигурация автоплана (если отдельного modules/api/routers/autoplan.py нет):
router_autoplan = APIRouter(prefix="/api/autoplan", tags=["autoplan"])

# --------------------------------------------------------------------------------------
# DB connection helpers
# --------------------------------------------------------------------------------------
def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    # унифицируем дефолт пароля
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    """
    psycopg3 -> psycopg2 fallback; для psycopg2 регистрируем UUID-адаптер.
    """
    try:
        import psycopg  # psycopg3
        return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg  # psycopg2
        conn = psycopg.connect(_db_dsn())
        try:
            from psycopg2.extras import register_uuid
            register_uuid(None, conn)
        except Exception:
            pass
        return conn

# --------------------------------------------------------------------------------------
# Routing / OSRM helpers
# --------------------------------------------------------------------------------------
# Унифицируем дефолт OSRM и таймаут
OSRM_URL = os.getenv("OSRM_URL", "http://osrm:5000")
OSRM_PROFILE = os.getenv("OSRM_PROFILE", "driving")
OSRM_TIMEOUT = float(os.getenv("OSRM_TIMEOUT", "8.0"))

ROUTING_ENRICH_ON_CONFIRM = os.getenv("ROUTING_ENRICH_ON_CONFIRM", "1") == "1"
ROUTING_REENRICH_IF_CONFIRMED = os.getenv("ROUTING_REENRICH_IF_CONFIRMED", "1") == "1"

# Совместимость с прежним именем переменной
OSRM_FALLBACK_SPEED_KMH = float(os.getenv("OSRM_FALLBACK_SPEED_KMH",
                                  os.getenv("ROUTING_FALLBACK_SPEED_KMH", "70")))
ROUTING_ENRICH_DEBUG = os.getenv("ROUTING_ENRICH_DEBUG", "1") == "1"

def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",  # дружим с PowerShell
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _osrm_route(a_lat: float, a_lon: float, b_lat: float, b_lon: float):
    """
    Возвращает (distance_m, duration_s, polyline, backend), backend='osrm'
    """
    coords = f"{a_lon:.6f},{a_lat:.6f};{b_lon:.6f},{b_lat:.6f}"
    qs = urllib.parse.urlencode(
        {"overview": "full", "geometries": "polyline6", "steps": "false", "annotations": "false"}
    )
    url = f"{OSRM_URL}/route/v1/{urllib.parse.quote(OSRM_PROFILE)}/{coords}?{qs}"
    data = _http_get_json(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("message") or data.get("code") or "OSRM route error")
    r0 = data["routes"][0]
    return float(r0["distance"]), float(r0["duration"]), (r0.get("geometry") or ""), "osrm"

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _fallback_route(a_lat: float, a_lon: float, b_lat: float, b_lon: float):
    """
    Возвращает (distance_m, duration_s, polyline, backend), backend='haversine'
    """
    dist_m = _haversine_m(a_lat, a_lon, b_lat, b_lon)
    speed_mps = (OSRM_FALLBACK_SPEED_KMH * 1000.0) / 3600.0
    dur_s = dist_m / speed_mps if speed_mps > 0 else 0
    return dist_m, dur_s, "", "haversine"

def _enrich_trip_segments_with_routing(conn, trip_id: str) -> dict:
    """
    Обогащает public.trip_segments дорожными метриками для заданного trip_id.
    Не бросает исключений наверх — фейлы OSRM/сети не блокируют confirm.
    Возвращает сводку: {'updated': N, 'failed': M, 'errors'?: [...]}
    """
    stats = {"updated": 0, "failed": 0}
    errors = []
    cur = conn.cursor()
    # Берём обе возможные схемы имён координат (from_*/to_* или start_*/end_*)
    cur.execute(
        """
        SELECT id,
               COALESCE(from_lat,  start_lat) AS a_lat,
               COALESCE(from_lon,  start_lon) AS a_lon,
               COALESCE(to_lat,    end_lat)   AS b_lat,
               COALESCE(to_lon,    end_lon)   AS b_lon
          FROM public.trip_segments
         WHERE trip_id = %s::uuid
         ORDER BY COALESCE(seq, 0), id
        """,
        (trip_id,),
    )
    rows = cur.fetchall()
    for sid, a_lat, a_lon, b_lat, b_lon in rows:
        if a_lat is None or a_lon is None or b_lat is None or b_lon is None:
            continue
        try:
            try:
                dist_m, dur_s, poly, backend = _osrm_route(a_lat, a_lon, b_lat, b_lon)
            except Exception:
                dist_m, dur_s, poly, backend = _fallback_route(a_lat, a_lon, b_lat, b_lon)

            # --- безопасный расчёт значений в Python ---
            road_km_dec = (Decimal(str(dist_m)) / Decimal('1000')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            dur_i = int(round(dur_s))
            sid_str = str(sid)  # исключаем проблемы адаптера UUID

            cur2 = conn.cursor()
            cur2.execute(
                """
                UPDATE public.trip_segments
                   SET road_km       = %s,      -- numeric(10,3)
                       drive_sec     = %s,      -- int
                       polyline      = %s,
                       route_backend = %s,
                       updated_at    = now()
                 WHERE id = %s::uuid
                """,
                (road_km_dec, dur_i, poly, backend, sid_str),
            )
            stats["updated"] += 1
        except Exception as e_upd:
            stats["failed"] += 1
            if ROUTING_ENRICH_DEBUG and len(errors) < 3:
                errors.append(f"{sid}: {type(e_upd).__name__}: {e_upd}")
            continue
    conn.commit()
    if ROUTING_ENRICH_DEBUG and errors:
        stats["errors"] = errors
    return stats

# --------------------------------------------------------------------------------------
# Confirm endpoint
# --------------------------------------------------------------------------------------
@router.post("/{trip_id}/confirm")
def confirm_trip(trip_id: str = Path(..., description="UUID of trip")):
    """
    Подтверждает рейс по порогам пригодности и (опционально) обогащает сегменты дорожными метриками.
    Возвращаем компактный JSON через JSONResponse (Connection: close), чтобы PowerShell не ловил ResponseEnded.
    """
    # Пороговые параметры подтверждения
    p_min = float(os.getenv("CONFIRM_P_MIN", os.getenv("AUTOPLAN_P_ARRIVE_MIN", "0.5")))
    rpm_min = float(os.getenv("CONFIRM_RPM_MIN", os.getenv("AUTOPLAN_RPM_MIN", "120")))
    horizon_h = int(os.getenv("CONFIRM_HORIZON_H", "24"))
    freeze_h = int(os.getenv("CONFIRM_FREEZE_H_BEFORE", "2"))
    # Разрешённые статусы, из которых можно подтверждать
    allowed_from = [s.strip() for s in os.getenv("CONFIRM_ALLOWED_FROM", "draft,planned").split(",") if s.strip()]

    conn = _connect_pg()
    try:
        cur = conn.cursor()

        # 1) Предварительная информация о рейсе
        cur.execute(
            """
            SELECT status,
                   planned_load_window_start AS ls,
                   planned_unload_window_end AS ue
              FROM public.trips
             WHERE id = %s::uuid
            """,
            (trip_id,),
        )
        pre = cur.fetchone()
        if not pre:
            raise HTTPException(status_code=404, detail={"confirmed": False, "reason": "not_found", "trip_id": trip_id})
        pre_status, pre_ls, pre_ue = pre

        # Если уже подтверждён — при флаге позволяем re-enrich
        if pre_status == "confirmed":
            enrich_stats = None
            if ROUTING_ENRICH_ON_CONFIRM and ROUTING_REENRICH_IF_CONFIRMED:
                try:
                    enrich_stats = _enrich_trip_segments_with_routing(conn, trip_id)
                except Exception:
                    enrich_stats = {"updated": 0, "failed": 0}
            payload = {"ok": True, "confirmed": True, "already": True, "trip_id": trip_id, "routing_enrich": enrich_stats}
            return JSONResponse(content=payload, headers={"Connection": "close"})

        if pre_status not in allowed_from:
            raise HTTPException(
                status_code=409,
                detail={"confirmed": False, "reason": "not_from_allowed_status", "status": pre_status, "trip_id": trip_id},
            )

        # 2) Проверка пригодности (frozen window + horizon + пороги p/rpm)
        base_cte = """
        WITH cand AS (
          SELECT t.id, t.status,
                 t.planned_load_window_start AS ls,
                 t.planned_unload_window_end AS ue,
                 d.p_arrive, d.rpm, COALESCE(d.source,'autoplan') AS src
            FROM public.trips t
            LEFT JOIN public.autoplan_draft_trips d ON d.trip_id = t.id
           WHERE t.id = %s::uuid
             AND t.status = %s
             AND t.planned_load_window_start IS NOT NULL
             AND t.planned_unload_window_end   IS NOT NULL
             AND t.planned_load_window_start >= (now() + %s::int * INTERVAL '1 hour')
             AND t.planned_load_window_start <= (now() + %s::int * INTERVAL '1 hour')
        ),
        ok AS (
          SELECT id, ls, ue, p_arrive, rpm, src
            FROM cand
           WHERE COALESCE(p_arrive,0)::float8 >= %s
             AND COALESCE(rpm,0)::float8      >= %s
        )
        """

        set_confirmed_at = "confirmed_at = now(), "

        sql = base_cte + """
        UPDATE public.trips t
           SET status = 'confirmed',
               """ + set_confirmed_at + """
               updated_at = now(),
               meta = COALESCE(t.meta, '{}'::jsonb) || jsonb_build_object(
                 'autoplan_confirm', jsonb_build_object(
                   'p_min', %s::float8,
                   'rpm_min', %s::float8,
                   'from', (SELECT src FROM ok)::text
                 )
               )
          WHERE t.id = (SELECT id FROM ok)
        RETURNING t.id;
        """

        cur.execute(sql, (trip_id, pre_status, freeze_h, horizon_h, p_min, rpm_min, p_min, rpm_min))
        row = cur.fetchone()
        conn.commit()

        if not row:
            # Диагностика причины отказа
            cur = conn.cursor()
            cur.execute(
                """
                SELECT t.id, t.status,
                       t.planned_load_window_start AS ls,
                       now() AS now_db,
                       d.p_arrive, d.rpm
                  FROM public.trips t
                  LEFT JOIN public.autoplan_draft_trips d ON d.trip_id = t.id
                 WHERE t.id = %s::uuid
                """,
                (trip_id,),
            )
            diag = cur.fetchone()
            raise HTTPException(status_code=409, detail={"confirmed": False, "reason": "not_eligible", "diag": diag})

        # 3) Обогащение дорожными метриками (не блокирует успешный confirm)
        enrich_stats = None
        if ROUTING_ENRICH_ON_CONFIRM:
            try:
                enrich_stats = _enrich_trip_segments_with_routing(conn, trip_id)
            except Exception as e:
                # не ломаем confirm из-за проблем с роутингом
                enrich_stats = {"updated": 0, "failed": 0, **({"errors": [str(e)]} if ROUTING_ENRICH_DEBUG else {})}

        payload = {
            "ok": True,
            "confirmed": True,
            "trip_id": row[0],
            "routing_enrich": enrich_stats,
        }
        return JSONResponse(content=payload, headers={"Connection": "close"})

    except HTTPException:
        raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        # Отдаём компактную ошибку стабильным ответом
        payload = {"ok": False, "confirmed": False, "error": f"confirm_failed: {e!r}", "trip_id": trip_id}
        return JSONResponse(status_code=500, content=payload, headers={"Connection": "close"})
    finally:
        try:
            conn.close()
        except Exception:
            pass

# --------------------------------------------------------------------------------------
# /api/autoplan/config — экспорт ключевых порогов/флагов из ENV
# --------------------------------------------------------------------------------------
def _autoplan_config_payload() -> dict:
    env = os.environ.get
    return {
        # Динамический RPM / квантили
        "use_dynamic_rpm": env("USE_DYNAMIC_RPM", "1"),
        "quantile": env("DYNAMIC_RPM_QUANTILE", "p25"),
        "rpm_floor_min": env("DYNAMIC_RPM_FLOOR_MIN", "110"),
        # Пороги confirm/autoplan
        "rpm_min": env("AUTOPLAN_RPM_MIN", env("CONFIRM_RPM_MIN", "130")),
        "p_arrive_min": env("AUTOPLAN_P_ARRIVE_MIN", env("CONFIRM_P_MIN", "0.40")),
        "apply_window_min": env("AUTOPLAN_APPLY_WINDOW_MIN", "240"),
        "horizon_h": env("PLANNER_PICKUP_HORIZON_H", "24"),
        # Интрасити / скорость
        "intracity_km": env("INTRACITY_FALLBACK_KM", "50"),
        "intracity_speed_kmh": env("INTRACITY_SPEED_KMH", "35"),
        "fallback_speed_kmh": env("OSRM_FALLBACK_SPEED_KMH",
                                  env("ROUTING_FALLBACK_SPEED_KMH", "70")),
        # Роутинг
        "osrm_url": env("OSRM_URL", "http://osrm:5000"),
        "osrm_profile": env("OSRM_PROFILE", "driving"),
        "osrm_timeout": env("OSRM_TIMEOUT", "8.0"),
        # Флаги обогащения
        "routing_enrich_on_confirm": env("ROUTING_ENRICH_ON_CONFIRM", "1"),
        "routing_reenrich_if_confirmed": env("ROUTING_REENRICH_IF_CONFIRMED", "1"),
        "routing_enrich_debug": env("ROUTING_ENRICH_DEBUG", "0"),
    }

@router_autoplan.get("/config")
def autoplan_config():
    return JSONResponse(content=_autoplan_config_payload(), headers={"Connection": "close"})

# скрытая копия — если второй роутер не будет смонтирован в main.py
@router.get("/__config", include_in_schema=False)
def autoplan_config_shadow():
    return JSONResponse(content=_autoplan_config_payload(), headers={"Connection": "close"})
