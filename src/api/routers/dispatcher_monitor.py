from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# psycopg3 -> fallback на psycopg2
try:  # pragma: no cover
    import psycopg  # type: ignore[import]
except ImportError:  # pragma: no cover
    import psycopg2 as psycopg  # type: ignore[assignment,import]


router = APIRouter(
    prefix="/dispatcher",
    tags=["dispatcher"],
)


# === DB helpers ======================================================


def _db_dsn() -> str:
    """
    DSN к Postgres, такой же подход, как в других роутерах (driver.py).
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    return psycopg.connect(dsn)


# === Pydantic-модель витрины ========================================


class DriverTripMonitorRow(BaseModel):
    trip_id: UUID
    status: str

    loading_region: Optional[str] = None
    unloading_region: Optional[str] = None
    origin_region: Optional[str] = None
    dest_region: Optional[str] = None

    truck_id: UUID
    driver_id: Optional[UUID] = None
    driver_phone: Optional[str] = None
    driver_name: Optional[str] = None

    driver_ack_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    last_ts: Optional[datetime] = None
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    speed_kph: Optional[float] = None

    alert_ts: Optional[datetime] = None
    alert_level: Optional[str] = None
    alert_type: Optional[str] = None
    detour_factor: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "62c0eec7-97c4-41ca-b863-b45602f54db9",
                "status": "confirmed",
                "origin_region": "RU-MOW",
                "dest_region": "RU-SPE",
                "truck_id": "14dc9d4f-64dd-462f-882c-8684d6097797",
                "driver_id": "475d6336-73db-4fcf-a4ad-bд57106f7658",
                "driver_phone": "+79990001122",
                "last_ts": "2025-11-26T01:21:55.593562+00:00",
                "last_lat": 43.1155,
                "last_lon": 131.8855,
                "speed_kph": 80.0,
                "alert_ts": "2025-11-26T01:21:57.350507+00:00",
                "alert_level": "critical",
                "alert_type": "off_route",
                "detour_factor": 20.46,
            }
        }


# === Эндпоинт мониторинга рейсов ====================================


@router.get(
    "/trips/monitor",
    response_model=List[DriverTripMonitorRow],
    summary="Мониторинг рейсов водителей (off-route, телеметрия, статус)",
)
def get_driver_trips_monitor(
    limit: int = Query(100, ge=1, le=1000),
    driver_id: Optional[UUID] = Query(
        None,
        description="Фильтр по конкретному водителю (driver_id)",
    ),
    only_with_alerts: bool = Query(
        False,
        description="Показывать только рейсы с активными off_route-алертами",
    ),
) -> List[DriverTripMonitorRow]:
    """
    Вернуть список рейсов для мониторинга водителей.

    Источник данных — analytics.driver_trip_monitor_v, которая уже собирает:
      - последний статус рейса;
      - origin/dest регион;
      - водителя и ТС;
      - последнюю точку телеметрии;
      - последний off_route-алерт (если есть).
    """
    rows: List[DriverTripMonitorRow] = []

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  trip_id,
                  status,
                  loading_region,
                  unloading_region,
                  origin_region,
                  dest_region,
                  truck_id,
                  driver_id,
                  driver_phone,
                  driver_name,
                  driver_ack_at,
                  completed_at,
                  last_ts,
                  last_lat,
                  last_lon,
                  speed_kph,
                  alert_ts,
                  alert_level,
                  alert_type,
                  detour_factor
                FROM analytics.driver_trip_monitor_v
                WHERE (%(driver_id)s::uuid IS NULL OR driver_id = %(driver_id)s::uuid)
                  AND (%(only_alerts)s = FALSE OR alert_level IS NOT NULL)
                ORDER BY last_ts DESC NULLS LAST
                LIMIT %(limit)s;
                """,
                {
                    # None → NULL::uuid; конкретный UUID → '...'::uuid
                    "driver_id": str(driver_id) if driver_id is not None else None,
                    "only_alerts": only_with_alerts,
                    "limit": limit,
                },
            )

            for row in cur.fetchall():
                (
                    trip_id,
                    status,
                    loading_region,
                    unloading_region,
                    origin_region,
                    dest_region,
                    truck_id,
                    driver_id_val,
                    driver_phone,
                    driver_name,
                    driver_ack_at,
                    completed_at,
                    last_ts,
                    last_lat,
                    last_lon,
                    speed_kph,
                    alert_ts,
                    alert_level,
                    alert_type,
                    detour_factor,
                ) = row

                rows.append(
                    DriverTripMonitorRow(
                        trip_id=trip_id,
                        status=status,
                        loading_region=loading_region,
                        unloading_region=unloading_region,
                        origin_region=origin_region,
                        dest_region=dest_region,
                        truck_id=truck_id,
                        driver_id=driver_id_val,
                        driver_phone=driver_phone,
                        driver_name=driver_name,
                        driver_ack_at=driver_ack_at,
                        completed_at=completed_at,
                        last_ts=last_ts,
                        last_lat=last_lat,
                        last_lon=last_lon,
                        speed_kph=float(speed_kph) if speed_kph is not None else None,
                        alert_ts=alert_ts,
                        alert_level=alert_level,
                        alert_type=alert_type,
                        detour_factor=float(detour_factor) if detour_factor is not None else None,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"driver_trip_monitor_failed: {exc}"
        ) from exc

    return rows
