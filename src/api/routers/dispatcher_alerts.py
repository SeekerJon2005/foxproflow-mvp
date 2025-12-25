from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional

# psycopg / psycopg2 fallback
try:  # pragma: no cover
    import psycopg  # type: ignore[import]
except ImportError:  # pragma: no cover
    import psycopg2 as psycopg  # type: ignore[assignment,import]

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from src.core import emit_start, emit_done, emit_error

router = APIRouter(
    prefix="/dispatcher",
    tags=["dispatcher"],
)


def _db_dsn() -> str:
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    return psycopg.connect(dsn)


class DriverAlert(BaseModel):
    id: int
    ts: datetime
    trip_id: str
    driver_id: Optional[str]
    alert_type: str
    level: str
    message: Optional[str]
    details: Any

    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_comment: Optional[str] = None


class DriverAlertsResponse(BaseModel):
    ok: bool = True
    items: List[DriverAlert]


class AlertResolveRequest(BaseModel):
    resolved_by: Optional[str] = None
    resolved_comment: Optional[str] = None


class AlertResolveResponse(BaseModel):
    ok: bool = True
    alert: DriverAlert


class AlertsResolveByTripResponse(BaseModel):
    ok: bool = True
    trip_id: str
    updated: List[DriverAlert]


@router.get(
    "/alerts/recent",
    response_model=DriverAlertsResponse,
    summary="Последние алерты по водителям",
)
def dispatcher_alerts_recent(
    limit: int = Query(50, ge=1, le=500),
    alert_type: Optional[str] = Query(
        None,
        description="Фильтр по типу алерта (например, off_route, eta_delay).",
    ),
    level: Optional[str] = Query(
        None,
        description="Фильтр по уровню (info, warn, critical).",
    ),
    trip_id: Optional[str] = Query(
        None,
        description="Фильтр по рейсу (UUID, текстом).",
    ),
    driver_id: Optional[str] = Query(
        None,
        description="Фильтр по водителю (UUID, текстом).",
    ),
    minutes_back: Optional[int] = Query(
        None,
        ge=1,
        le=7 * 24 * 60,
        description="Если задан, возвращаем только алерты за последние N минут.",
    ),
    only_active: bool = Query(
        True,
        description="true — только незакрытые алерты (resolved_at IS NULL)",
    ),
) -> DriverAlertsResponse:
    """
    Последние алерты по водителям для диспетчера.

    v1:
      • плоский список ops.driver_alerts, ts DESC;
      • фильтры по типу, уровню, рейсу, водителю, окну по времени;
      • only_active управляет учётом resolved_at.
    """
    corr_id = f"dispatcher.alerts.recent:limit={limit}"
    emit_start(
        "dispatcher.alerts",
        correlation_id=corr_id,
        payload={
            "limit": limit,
            "alert_type": alert_type,
            "level": level,
            "trip_id": trip_id,
            "driver_id": driver_id,
            "minutes_back": minutes_back,
            "only_active": only_active,
        },
    )

    items: List[DriverAlert] = []

    try:
        where_parts: List[str] = []
        params: List[Any] = []

        if alert_type:
            where_parts.append("alert_type = %s")
            params.append(alert_type)

        if level:
            where_parts.append("level = %s")
            params.append(level)

        if trip_id:
            where_parts.append("trip_id::text = %s")
            params.append(trip_id)

        if driver_id:
            where_parts.append("driver_id::text = %s")
            params.append(driver_id)

        if minutes_back is not None:
            where_parts.append("ts >= now() - (%s || ' minutes')::interval")
            params.append(minutes_back)

        if only_active:
            where_parts.append("resolved_at IS NULL")

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        params.append(limit)

        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    ts,
                    trip_id::text,
                    driver_id::text,
                    alert_type,
                    level,
                    message,
                    details,
                    resolved_at,
                    resolved_by,
                    resolved_comment
                FROM ops.driver_alerts
                {where_sql}
                ORDER BY ts DESC
                LIMIT %s;
                """,
                tuple(params),
            )
            for row in cur.fetchall():
                (
                    aid,
                    ts,
                    trip_id_val,
                    driver_id_val,
                    alert_type_val,
                    level_val,
                    message_val,
                    details_val,
                    resolved_at,
                    resolved_by,
                    resolved_comment,
                ) = row
                items.append(
                    DriverAlert(
                        id=aid,
                        ts=ts,
                        trip_id=trip_id_val,
                        driver_id=driver_id_val,
                        alert_type=alert_type_val,
                        level=level_val,
                        message=message_val,
                        details=details_val,
                        resolved_at=resolved_at,
                        resolved_by=resolved_by,
                        resolved_comment=resolved_comment,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "dispatcher.alerts",
            correlation_id=corr_id,
            payload={"error": repr(exc)},
        )
        raise HTTPException(status_code=500, detail="dispatcher_alerts_failed") from exc

    emit_done(
        "dispatcher.alerts",
        correlation_id=corr_id,
        payload={"count": len(items)},
    )
    return DriverAlertsResponse(items=items, ok=True)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertResolveResponse,
    summary="Закрыть off-route алерт по id (resolved_at/resolved_by/resolved_comment)",
)
def dispatcher_alert_resolve(
    alert_id: int = Path(..., ge=1),
    payload: AlertResolveRequest = ...,
) -> AlertResolveResponse:
    """
    Закрывает алерт (по id) в ops.driver_alerts:

    - ставит resolved_at = now(), если ещё не стояло;
    - обновляет resolved_by / resolved_comment, если переданы;
    - возвращает обновлённый объект алерта.
    """
    corr_id = f"dispatcher.alerts.resolve:{alert_id}"
    emit_start(
        "dispatcher.alerts.resolve",
        correlation_id=corr_id,
        payload={
            "alert_id": alert_id,
            "resolved_by": payload.resolved_by,
        },
    )

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ops.driver_alerts
                   SET resolved_at = COALESCE(resolved_at, now()),
                       resolved_by = COALESCE(%(resolved_by)s, resolved_by),
                       resolved_comment = COALESCE(%(resolved_comment)s, resolved_comment)
                 WHERE id = %(id)s
                 RETURNING
                    id,
                    ts,
                    trip_id::text,
                    driver_id::text,
                    alert_type,
                    level,
                    message,
                    details,
                    resolved_at,
                    resolved_by,
                    resolved_comment;
                """,
                {
                    "id": alert_id,
                    "resolved_by": payload.resolved_by,
                    "resolved_comment": payload.resolved_comment,
                },
            )
            row = cur.fetchone()
            if not row:
                emit_error(
                    "dispatcher.alerts.resolve",
                    correlation_id=corr_id,
                    payload={"error": "alert_not_found"},
                )
                raise HTTPException(status_code=404, detail="alert_not_found")

            (
                aid,
                ts,
                trip_id_val,
                driver_id_val,
                alert_type_val,
                level_val,
                message_val,
                details_val,
                resolved_at,
                resolved_by,
                resolved_comment,
            ) = row

            conn.commit()

            alert = DriverAlert(
                id=aid,
                ts=ts,
                trip_id=trip_id_val,
                driver_id=driver_id_val,
                alert_type=alert_type_val,
                level=level_val,
                message=message_val,
                details=details_val,
                resolved_at=resolved_at,
                resolved_by=resolved_by,
                resolved_comment=resolved_comment,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "dispatcher.alerts.resolve",
            correlation_id=corr_id,
            payload={"error": repr(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail="dispatcher_alert_resolve_failed",
        ) from exc

    emit_done(
        "dispatcher.alerts.resolve",
        correlation_id=corr_id,
        payload={"alert_id": alert_id},
    )
    return AlertResolveResponse(alert=alert, ok=True)


@router.post(
    "/alerts/by_trip/{trip_id}/resolve_all",
    response_model=AlertsResolveByTripResponse,
    summary="Закрыть все алерты по рейсу (resolved_at/resolved_by/resolved_comment)",
)
def dispatcher_alerts_resolve_by_trip(
    trip_id: str = Path(..., description="UUID рейса (trip_id)"),
    payload: AlertResolveRequest = ...,
    only_active: bool = Query(
        True,
        description="true — закрывать только незакрытые алерты (resolved_at IS NULL)",
    ),
) -> AlertsResolveByTripResponse:
    """
    Массово закрывает все алерты по рейсу в ops.driver_alerts:

    - ставит resolved_at = now() там, где ещё NULL (или везде, если only_active=false);
    - resolved_by / resolved_comment — как в payload (если не заданы, сохраняются старые значения);
    - возвращает список обновлённых алертов.
    """
    corr_id = f"dispatcher.alerts.resolve_trip:{trip_id}"
    emit_start(
        "dispatcher.alerts.resolve_trip",
        correlation_id=corr_id,
        payload={
            "trip_id": trip_id,
            "resolved_by": payload.resolved_by,
            "only_active": only_active,
        },
    )

    updated: List[DriverAlert] = []

    try:
        with _pg() as conn, conn.cursor() as cur:
            where_active = "resolved_at IS NULL" if only_active else "TRUE"

            cur.execute(
                f"""
                UPDATE ops.driver_alerts
                   SET resolved_at = COALESCE(resolved_at, now()),
                       resolved_by = COALESCE(%(resolved_by)s, resolved_by),
                       resolved_comment = COALESCE(%(resolved_comment)s, resolved_comment)
                 WHERE trip_id = %(trip_id)s::uuid
                   AND {where_active}
                 RETURNING
                    id,
                    ts,
                    trip_id::text,
                    driver_id::text,
                    alert_type,
                    level,
                    message,
                    details,
                    resolved_at,
                    resolved_by,
                    resolved_comment;
                """,
                {
                    "trip_id": trip_id,
                    "resolved_by": payload.resolved_by,
                    "resolved_comment": payload.resolved_comment,
                },
            )
            rows = cur.fetchall()
            conn.commit()

            for row in rows:
                (
                    aid,
                    ts,
                    trip_id_val,
                    driver_id_val,
                    alert_type_val,
                    level_val,
                    message_val,
                    details_val,
                    resolved_at,
                    resolved_by,
                    resolved_comment,
                ) = row

                updated.append(
                    DriverAlert(
                        id=aid,
                        ts=ts,
                        trip_id=trip_id_val,
                        driver_id=driver_id_val,
                        alert_type=alert_type_val,
                        level=level_val,
                        message=message_val,
                        details=details_val,
                        resolved_at=resolved_at,
                        resolved_by=resolved_by,
                        resolved_comment=resolved_comment,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "dispatcher.alerts.resolve_trip",
            correlation_id=corr_id,
            payload={"error": repr(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail="dispatcher_alerts_resolve_trip_failed",
        ) from exc

    emit_done(
        "dispatcher.alerts.resolve_trip",
        correlation_id=corr_id,
        payload={"trip_id": trip_id, "count": len(updated)},
    )
    return AlertsResolveByTripResponse(trip_id=trip_id, updated=updated, ok=True)
