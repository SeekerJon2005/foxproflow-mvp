"""
FoxProFlow — задачи анализа телеметрии водителей (off-route) и запись алертов
в ops.driver_alerts.

Эвристика: detour_factor = (D_oo + D_dd) / D_od, где:
  • D_od — расстояние origin → dest,
  • D_oo — origin → текущая точка,
  • D_dd — текущая точка → dest.

Если detour_factor > warn_factor  → off_route/warn,
если detour_factor > crit_factor  → off_route/critical.
"""

from __future__ import annotations

import os
import math
import json
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

# psycopg v3 → fallback на psycopg2
try:  # pragma: no cover
    import psycopg  # type: ignore[import]
except ImportError:  # pragma: no cover
    import psycopg2 as psycopg  # type: ignore[assignment,import]

try:
    from src.worker.celery_app import app  # type: ignore
except Exception:  # pragma: no cover
    app = None  # type: ignore

from src.core import emit_start, emit_done, emit_error


def _db_dsn() -> str:
    """
    Сборка DSN к Postgres (совместимо с остальными worker-модулями).
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pg():
    """
    Подключение к Postgres (psycopg3 или psycopg2).
    """
    dsn = _db_dsn()
    return psycopg.connect(dsn)


def _hav_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """
    Haversine-расстояние между двумя точками (lat, lon) в км.
    """
    (lat1, lon1), (lat2, lon2) = a, b
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def driver_offroute_scan(
    max_trips: int = 50,
    warn_factor: float = 1.6,
    crit_factor: float = 2.2,
    recent_minutes: int = 10,
) -> Dict[str, Any]:
    """
    Анализ последних точек driver_telemetry по активным рейсам и запись алертов ops.driver_alerts.

    Эвристика: detour_factor = (D_oo + D_dd) / D_od, где:
      • D_od — расстояние origin → dest,
      • D_oo — origin → текущая точка,
      • D_dd — текущая точка → dest.

    Если detour_factor > warn_factor → off_route/warn,
    если detour_factor > crit_factor → off_route/critical.
    """
    corr_id = f"driver.offroute:{datetime.utcnow().isoformat(timespec='seconds')}"
    emit_start(
        "driver.offroute",
        correlation_id=corr_id,
        payload={
            "max_trips": max_trips,
            "warn_factor": warn_factor,
            "crit_factor": crit_factor,
            "recent_minutes": recent_minutes,
        },
    )

    stats: Dict[str, Any] = {
        "scanned_trips": 0,
        "inserted_warn": 0,
        "inserted_critical": 0,
        "skipped_no_coords": 0,
        "skipped_recent_alert": 0,
        "skipped_short_baseline": 0,
    }

    try:
        with _pg() as conn, conn.cursor() as cur:
            # 1. Берём активные рейсы (confirmed, не завершены) с водителем
            #    и последней точкой телеметрии.
            #    Координаты origin/dest берём из city_map по region_code.
            cur.execute(
                """
                WITH base AS (
                    SELECT
                        t.id          AS trip_id,
                        tr.driver_id  AS driver_id,
                        COALESCE(t.meta->'autoplan'->>'o', t.loading_region)   AS origin_region,
                        COALESCE(t.meta->'autoplan'->>'d', t.unloading_region) AS dest_region
                    FROM public.trips t
                    JOIN public.trucks tr
                      ON tr.id = t.truck_id
                    WHERE tr.driver_id IS NOT NULL
                      AND t.status = 'confirmed'
                      AND (t.completed_at IS NULL)
                )
                SELECT
                    b.trip_id,
                    b.driver_id,
                    cm_o.lat AS o_lat,
                    cm_o.lon AS o_lon,
                    cm_d.lat AS d_lat,
                    cm_d.lon AS d_lon,
                    dt.ts    AS last_ts,
                    dt.lat   AS last_lat,
                    dt.lon   AS last_lon
                FROM base b
                JOIN public.city_map cm_o
                  ON cm_o.region_code = b.origin_region
                JOIN public.city_map cm_d
                  ON cm_d.region_code = b.dest_region
                JOIN LATERAL (
                    SELECT ts, lat, lon
                    FROM public.driver_telemetry dt
                    WHERE dt.trip_id = b.trip_id
                    ORDER BY ts DESC
                    LIMIT 1
                ) dt ON TRUE
                ORDER BY dt.ts DESC
                LIMIT %s;
                """,
                (max_trips,),
            )
            rows = cur.fetchall()
            stats["scanned_trips"] = len(rows)

            for row in rows:
                (
                    trip_id,
                    driver_id,
                    o_lat,
                    o_lon,
                    d_lat,
                    d_lon,
                    last_ts,
                    last_lat,
                    last_lon,
                ) = row

                # Проверка координат
                if (
                    o_lat is None
                    or o_lon is None
                    or d_lat is None
                    or d_lon is None
                    or last_lat is None
                    or last_lon is None
                ):
                    stats["skipped_no_coords"] += 1
                    continue

                origin = (float(o_lat), float(o_lon))
                dest = (float(d_lat), float(d_lon))
                point = (float(last_lat), float(last_lon))

                baseline_km = _hav_km(origin, dest)
                if baseline_km < 1.0:
                    # Слишком короткий маршрут, off-route неинтересен.
                    stats["skipped_short_baseline"] += 1
                    continue

                d_from_origin_km = _hav_km(origin, point)
                d_to_dest_km = _hav_km(point, dest)
                detour_factor = (d_from_origin_km + d_to_dest_km) / baseline_km

                # Всё ок или почти ок — ниже warn-порога
                if detour_factor <= warn_factor:
                    continue

                # Проверяем, не было ли недавно алерта off_route по этому рейсу
                cur.execute(
                    """
                    SELECT 1
                    FROM ops.driver_alerts
                    WHERE trip_id = %s
                      AND alert_type = 'off_route'
                      AND ts > now() - (%s || ' minutes')::interval
                    LIMIT 1;
                    """,
                    (trip_id, recent_minutes),
                )
                if cur.fetchone():
                    stats["skipped_recent_alert"] += 1
                    continue

                if detour_factor >= crit_factor:
                    level = "critical"
                else:
                    level = "warn"

                msg = (
                    f"off_route {level}: detour_factor={detour_factor:.2f} "
                    f"(baseline={baseline_km:.1f}km, from_origin={d_from_origin_km:.1f}km, "
                    f"to_dest={d_to_dest_km:.1f}km)"
                )

                details = {
                    "baseline_km": round(baseline_km, 3),
                    "from_origin_km": round(d_from_origin_km, 3),
                    "to_dest_km": round(d_to_dest_km, 3),
                    "detour_factor": round(detour_factor, 3),
                    "last_ts": last_ts.isoformat() if isinstance(last_ts, datetime) else str(last_ts),
                    "last_lat": float(last_lat),
                    "last_lon": float(last_lon),
                    "origin_lat": float(o_lat),
                    "origin_lon": float(o_lon),
                    "dest_lat": float(d_lat),
                    "dest_lon": float(d_lon),
                }

                cur.execute(
                    """
                    INSERT INTO ops.driver_alerts (
                        trip_id,
                        driver_id,
                        alert_type,
                        level,
                        message,
                        details
                    )
                    VALUES (%s, %s, 'off_route', %s, %s, %s::jsonb);
                    """,
                    (
                        trip_id,
                        driver_id,
                        level,
                        msg,
                        json.dumps(details, ensure_ascii=False),
                    ),
                )

                if level == "critical":
                    stats["inserted_critical"] += 1
                else:
                    stats["inserted_warn"] += 1

            conn.commit()

    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.offroute",
            correlation_id=corr_id,
            payload={"error": repr(exc), "stats": stats},
        )
        raise

    emit_done(
        "driver.offroute",
        correlation_id=corr_id,
        payload=stats,
    )
    return stats


# Celery-обёртка (если нужно дергать как задачу)
if app is not None:  # pragma: no cover

    @app.task(name="driver.alerts.offroute")
    def driver_alerts_offroute_task(
        max_trips: int = 50,
        warn_factor: float = 1.6,
        crit_factor: float = 2.2,
        recent_minutes: int = 10,
    ) -> Dict[str, Any]:
        """
        Celery-задача, обёртка над driver_offroute_scan.
        Параметры по умолчанию совпадают с функцией.
        """
        return driver_offroute_scan(
            max_trips=max_trips,
            warn_factor=warn_factor,
            crit_factor=crit_factor,
            recent_minutes=recent_minutes,
        )
