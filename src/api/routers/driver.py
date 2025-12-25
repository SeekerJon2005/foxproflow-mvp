from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import List, Optional

# Пытаемся использовать psycopg v3, если нет — падаем на psycopg2 под тем же именем.
try:  # pragma: no cover - зависит от установленной библиотеки
    import psycopg  # type: ignore[import]
except ImportError:  # pragma: no cover
    import psycopg2 as psycopg  # type: ignore[assignment,import]

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.core import emit_start, emit_done, emit_error

router = APIRouter(
    prefix="/driver",
    tags=["driver"],
)


# === DB helpers ======================================================


def _db_dsn() -> str:
    """
    DSN к Postgres, такой же подход, как в tasks_autoplan: host='postgres'
    внутри docker-сети.
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pg():
    """
    Подключение к Postgres. Использует либо psycopg3, либо psycopg2 (через fallback импорта).
    """
    dsn = _db_dsn()
    return psycopg.connect(dsn)


# === Pydantic-модели =================================================


class AuthRequest(BaseModel):
    phone: str = Field(
        ...,
        description="Телефон водителя (для Dev-стенда достаточно +7...)",
    )

    class Config:
        json_schema_extra = {"example": {"phone": "+70000000001"}}


class AuthConfirm(BaseModel):
    phone: str
    code: str = Field(
        ...,
        description="Код подтверждения (в Dev-режиме всегда '0000')",
    )


class AuthConfirmById(BaseModel):
    driver_id: uuid.UUID
    code: str = Field(
        ...,
        description="Код подтверждения (в Dev-режиме всегда '0000')",
    )


class AuthRequestResponse(BaseModel):
    ok: bool = True
    driver_id: uuid.UUID
    dev_code: Optional[str] = None


class AuthConfirmResponse(BaseModel):
    ok: bool = True
    driver_id: uuid.UUID


class TelemetryPoint(BaseModel):
    ts: datetime = Field(
        ...,
        description="Время точки в UTC",
    )
    lat: float
    lon: float
    speed_kph: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None


class TelemetryBatch(BaseModel):
    trip_id: uuid.UUID
    driver_id: Optional[uuid.UUID] = None
    truck_id: Optional[uuid.UUID] = None
    points: List[TelemetryPoint]


class AssignedTrip(BaseModel):
    id: uuid.UUID
    status: str
    origin_region: Optional[str] = None
    dest_region: Optional[str] = None
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class AssignedTripsResponse(BaseModel):
    ok: bool = True
    items: List[AssignedTrip]


class SimpleOkResponse(BaseModel):
    ok: bool = True


class TelemetryInsertResponse(BaseModel):
    ok: bool = True
    inserted: int


# === Auth endpoints (DEV-режим) ======================================


@router.post("/auth/request_code", response_model=AuthRequestResponse)
def driver_auth_request_code(payload: AuthRequest) -> AuthRequestResponse:
    """
    Dev-версия: создаём/находим водителя по телефону и «высылаем» код 0000.

    В бою код не должен возвращаться в ответе — это именно стендовая версия.
    """
    phone = payload.phone.strip()
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone_required")

    corr_id = f"driver.auth.request_code:{phone}"
    emit_start("driver.auth", correlation_id=corr_id, payload={"phone": phone})

    driver_id: Optional[uuid.UUID] = None

    try:
        with _pg() as conn, conn.cursor() as cur:
            # Ищем existing
            cur.execute(
                "SELECT id FROM public.drivers WHERE phone = %s LIMIT 1",
                (phone,),
            )
            row = cur.fetchone()
            if row:
                driver_id = uuid.UUID(str(row[0]))
            else:
                # Создаём пустого водителя с телефоном
                cur.execute(
                    """
                    INSERT INTO public.drivers (full_name, phone, is_active)
                    VALUES (%s, %s, TRUE)
                    RETURNING id
                    """,
                    ("TEST DRIVER", phone),
                )
                driver_id = uuid.UUID(str(cur.fetchone()[0]))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.auth",
            correlation_id=corr_id,
            payload={"phone": phone, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="driver_auth_request_failed") from exc

    emit_done(
        "driver.auth",
        correlation_id=corr_id,
        payload={"phone": phone, "driver_id": str(driver_id)},
    )

    # В DEV-режиме возвращаем код явно, чтобы упростить тестирование.
    return AuthRequestResponse(ok=True, driver_id=driver_id, dev_code="0000")


@router.post("/auth/confirm", response_model=AuthConfirmResponse)
def driver_auth_confirm(payload: AuthConfirm) -> AuthConfirmResponse:
    """
    Dev-версия: считаем код всегда '0000'. Возвращаем driver_id по телефону.
    """
    phone = payload.phone.strip()
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone_required")

    if payload.code != "0000":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_code_dev_mode")

    corr_id = f"driver.auth.confirm:{phone}"
    emit_start("driver.auth", correlation_id=corr_id, payload={"phone": phone})

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM public.drivers WHERE phone = %s LIMIT 1",
                (phone,),
            )
            row = cur.fetchone()
            if not row:
                emit_error(
                    "driver.auth",
                    correlation_id=corr_id,
                    payload={"phone": phone, "error": "driver_not_found"},
                )
                raise HTTPException(status_code=404, detail="driver_not_found")
            driver_id = uuid.UUID(str(row[0]))
    except HTTPException:
        # уже залогировали выше
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.auth",
            correlation_id=corr_id,
            payload={"phone": phone, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="driver_auth_confirm_failed") from exc

    emit_done(
        "driver.auth",
        correlation_id=corr_id,
        payload={"phone": phone, "driver_id": str(driver_id)},
    )
    return AuthConfirmResponse(ok=True, driver_id=driver_id)


@router.post("/auth/confirm_code", response_model=AuthConfirmResponse)
def driver_auth_confirm_code(payload: AuthConfirmById) -> AuthConfirmResponse:
    """
    Dev-эндпоинт для подтверждения кода по driver_id.

    Используется сценарий:
    1) /driver/auth/request_code -> driver_id + dev_code;
    2) /driver/auth/confirm_code  -> driver_id + code (в Dev всегда '0000').

    В бою здесь должен появиться нормальный токен и полноценная проверка кода.
    """
    if payload.code != "0000":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_code_dev_mode")

    driver_id = payload.driver_id
    corr_id = f"driver.auth.confirm_code:{driver_id}"
    emit_start(
        "driver.auth",
        correlation_id=corr_id,
        payload={"driver_id": str(driver_id)},
    )

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.drivers WHERE id = %s::uuid LIMIT 1",
                (str(driver_id),),
            )
            row = cur.fetchone()
            if not row:
                emit_error(
                    "driver.auth",
                    correlation_id=corr_id,
                    payload={"driver_id": str(driver_id), "error": "driver_not_found"},
                )
                raise HTTPException(status_code=404, detail="driver_not_found")
    except HTTPException:
        # Уже залогировано emit_error выше
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.auth",
            correlation_id=corr_id,
            payload={"driver_id": str(driver_id), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="driver_auth_confirm_failed") from exc

    emit_done(
        "driver.auth",
        correlation_id=corr_id,
        payload={"driver_id": str(driver_id)},
    )
    return AuthConfirmResponse(ok=True, driver_id=driver_id)


# === Assigned trips ==================================================


@router.get("/trips/assigned", response_model=AssignedTripsResponse)
def get_assigned_trips(driver_id: uuid.UUID):
    """
    Вернуть рейсы, назначенные водителю.

    Dev-логика:
      1. Ищем водителя в public.drivers и берём его truck_id.
      2. Если truck_id отсутствует — считаем, что рейсов нет (возвращаем пустой список).
      3. Если truck_id есть — выбираем из public.trips все рейсы для этого ТС
         со статусами 'planned' / 'confirmed', по дате создания.
    """
    corr_id = f"driver.trips.assigned:{driver_id}"
    emit_start(
        "driver.trips",
        correlation_id=corr_id,
        payload={"op": "assigned", "driver_id": str(driver_id)},
    )

    items: List[AssignedTrip] = []

    try:
        with _pg() as conn, conn.cursor() as cur:
            # 1. Truck для водителя
            cur.execute(
                """
                SELECT truck_id
                FROM public.drivers
                WHERE id = %s::uuid
                  AND is_active IS TRUE
                LIMIT 1
                """,
                (str(driver_id),),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                emit_done(
                    "driver.trips",
                    correlation_id=corr_id,
                    payload={
                        "op": "assigned",
                        "driver_id": str(driver_id),
                        "count": 0,
                        "note": "no_truck_bound",
                    },
                )
                return AssignedTripsResponse(ok=True, items=[])

            truck_id = row[0]

            # 2. Рейсы по этому ТС
            cur.execute(
                """
                SELECT
                    t.id,
                    t.status,
                    COALESCE(t.meta->'autoplan'->>'o', t.loading_region)   AS origin_region,
                    COALESCE(t.meta->'autoplan'->>'d', t.unloading_region) AS dest_region,
                    t.created_at,
                    t.confirmed_at
                FROM public.trips t
                WHERE t.truck_id = %s::uuid
                  AND t.status IN ('planned', 'confirmed')
                ORDER BY t.created_at ASC
                """,
                (str(truck_id),),
            )
            for row in cur.fetchall():
                (
                    trip_id,
                    status_val,
                    origin_region,
                    dest_region,
                    created_at,
                    confirmed_at,
                ) = row
                items.append(
                    AssignedTrip(
                        id=uuid.UUID(str(trip_id)),
                        status=str(status_val),
                        origin_region=origin_region,
                        dest_region=dest_region,
                        created_at=created_at,
                        confirmed_at=confirmed_at,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.trips",
            correlation_id=corr_id,
            payload={
                "op": "assigned",
                "driver_id": str(driver_id),
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="driver_trips_assigned_failed") from exc

    emit_done(
        "driver.trips",
        correlation_id=corr_id,
        payload={"op": "assigned", "driver_id": str(driver_id), "count": len(items)},
    )
    return AssignedTripsResponse(items=items, ok=True)


# === Ack / complete ==================================================


class AckBody(BaseModel):
    driver_id: Optional[uuid.UUID] = None


@router.post("/trips/{trip_id}/ack", response_model=SimpleOkResponse)
def ack_trip(trip_id: uuid.UUID, body: AckBody):
    """
    Фиксируем, что водитель увидел рейс: driver_ack_at + метка в meta.

    Безопасность здесь минимальная (Dev-режим): мы не проверяем, что driver_id действительно
    закреплён за этим рейсом. Это будет дорабатываться через FlowSec и нормальную аутентификацию.
    """
    corr_id = f"driver.trips.ack:{trip_id}"
    emit_start(
        "driver.trips",
        correlation_id=corr_id,
        payload={
            "op": "ack",
            "trip_id": str(trip_id),
            "driver_id": (str(body.driver_id) if body.driver_id else None),
        },
    )

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.trips
                   SET driver_ack_at = COALESCE(driver_ack_at, now()),
                       meta = jsonb_set(
                           COALESCE(meta, '{}'::jsonb),
                           '{driver_ack}',
                           'true'::jsonb,
                           true
                       )
                 WHERE id = %s
                """,
                (str(trip_id),),
            )
            if cur.rowcount == 0:
                emit_error(
                    "driver.trips",
                    correlation_id=corr_id,
                    payload={
                        "op": "ack",
                        "trip_id": str(trip_id),
                        "error": "trip_not_found",
                    },
                )
                raise HTTPException(status_code=404, detail="trip_not_found")
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.trips",
            correlation_id=corr_id,
            payload={"op": "ack", "trip_id": str(trip_id), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="driver_trip_ack_failed") from exc

    emit_done(
        "driver.trips",
        correlation_id=corr_id,
        payload={"op": "ack", "trip_id": str(trip_id)},
    )
    return SimpleOkResponse(ok=True)


class CompleteBody(BaseModel):
    driver_id: Optional[uuid.UUID] = None


@router.post("/trips/{trip_id}/complete", response_model=SimpleOkResponse)
def complete_trip(trip_id: uuid.UUID, body: CompleteBody):
    """
    Завершение рейса водителем (статус finished + completed_at).

    Как и в ack, тут пока нет привязки driver_id -> trip_id, т.к. это Dev-режим.
    """
    corr_id = f"driver.trips.complete:{trip_id}"
    emit_start(
        "driver.trips",
        correlation_id=corr_id,
        payload={
            "op": "complete",
            "trip_id": str(trip_id),
            "driver_id": (str(body.driver_id) if body.driver_id else None),
        },
    )

    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.trips
                   SET status = 'finished',
                       completed_at = COALESCE(completed_at, now())
                 WHERE id = %s
                """,
                (str(trip_id),),
            )
            if cur.rowcount == 0:
                emit_error(
                    "driver.trips",
                    correlation_id=corr_id,
                    payload={
                        "op": "complete",
                        "trip_id": str(trip_id),
                        "error": "trip_not_found",
                    },
                )
                raise HTTPException(status_code=404, detail="trip_not_found")
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.trips",
            correlation_id=corr_id,
            payload={"op": "complete", "trip_id": str(trip_id), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="driver_trip_complete_failed") from exc

    emit_done(
        "driver.trips",
        correlation_id=corr_id,
        payload={"op": "complete", "trip_id": str(trip_id)},
    )
    return SimpleOkResponse(ok=True)


# === Телеметрия ======================================================


@router.post("/telemetry/batch", response_model=TelemetryInsertResponse)
def post_telemetry_batch(batch: TelemetryBatch):
    """
    Принимаем батч GPS-точек и пишем их в public.driver_telemetry.
    """
    if not batch.points:
        return TelemetryInsertResponse(ok=True, inserted=0)

    corr_id = f"driver.telemetry:{batch.trip_id}"
    emit_start(
        "driver.telemetry",
        correlation_id=corr_id,
        payload={
            "trip_id": str(batch.trip_id),
            "driver_id": str(batch.driver_id) if batch.driver_id else None,
            "points": len(batch.points),
        },
    )

    inserted = 0

    try:
        with _pg() as conn, conn.cursor() as cur:
            rows = []
            for p in batch.points:
                rows.append(
                    (
                        str(batch.trip_id),
                        str(batch.driver_id) if batch.driver_id else None,
                        str(batch.truck_id) if batch.truck_id else None,
                        p.ts,
                        float(p.lat),
                        float(p.lon),
                        p.speed_kph,
                        p.heading_deg,
                        p.accuracy_m,
                        "driver_app",
                    )
                )

            cur.executemany(
                """
                INSERT INTO public.driver_telemetry (
                    trip_id,
                    driver_id,
                    truck_id,
                    ts,
                    lat,
                    lon,
                    speed_kph,
                    heading_deg,
                    accuracy_m,
                    source
                )
                VALUES (%s::uuid, %s::uuid, %s::uuid,
                        %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            inserted = int(cur.rowcount or 0)
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        emit_error(
            "driver.telemetry",
            correlation_id=corr_id,
            payload={
                "trip_id": str(batch.trip_id),
                "driver_id": str(batch.driver_id) if batch.driver_id else None,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="driver_telemetry_failed") from exc

    emit_done(
        "driver.telemetry",
        correlation_id=corr_id,
        payload={
            "trip_id": str(batch.trip_id),
            "driver_id": str(batch.driver_id) if batch.driver_id else None,
            "inserted": inserted,
        },
    )
    return TelemetryInsertResponse(ok=True, inserted=inserted)
