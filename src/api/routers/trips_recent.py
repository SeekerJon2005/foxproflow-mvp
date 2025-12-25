# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import List, Dict, Any

from fastapi import APIRouter, Query


# Подключение к Postgres с фолбэком между psycopg3 и psycopg2.
# Важно: DSN собираем из POSTGRES_* и по умолчанию используем хост 'postgres',
# чтобы не зависеть от DATABASE_URL, который на хосте может быть с 127.0.0.1.
def _pg():
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    dsn = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


# Важно: здесь сразу /api/trips, потому что main подключает router без дополнительного prefix="/api"
router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.get("/recent")
def trips_recent(limit: int = Query(20, ge=1, le=500)) -> Dict[str, Any]:
    """
    GET /api/trips/recent?limit=N

    Списковая выдача последних рейсов:
      - id, status, created_at, confirmed_at;
      - origin_region / dest_region из meta.autoplan (o/d);
      - price_rub из meta.autoplan.price;
      - road_km / drive_sec из первого сегмента рейса.
    """
    items: List[Dict[str, Any]] = []
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              t.id::text,
              t.status::text,
              t.created_at,
              t.confirmed_at,
              (t.meta->'autoplan'->>'o')::text  AS origin_region,
              (t.meta->'autoplan'->>'d')::text  AS dest_region,
              NULLIF((t.meta->'autoplan'->>'price'),'')::numeric AS price_rub,
              s.road_km,
              s.drive_sec
            FROM public.trips t
            LEFT JOIN LATERAL (
              SELECT road_km, drive_sec
              FROM public.trip_segments s
              WHERE s.trip_id = t.id
              ORDER BY s.segment_order ASC
              LIMIT 1
            ) s ON TRUE
            ORDER BY t.created_at DESC
            LIMIT %s;
            """,
            (int(limit),),
        )
        for r in cur.fetchall():
            items.append(
                {
                    "id": r[0],
                    "status": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "confirmed_at": r[3].isoformat() if r[3] else None,
                    "origin_region": r[4],
                    "dest_region": r[5],
                    "price_rub": float(r[6]) if r[6] is not None else None,
                    "road_km": float(r[7]) if r[7] is not None else None,
                    "drive_sec": int(r[8]) if r[8] is not None else None,
                }
            )
    return {"ok": True, "items": items, "limit": int(limit)}


@router.get("/recent_clean")
def trips_recent_clean(limit: int = Query(20, ge=1, le=500)) -> Dict[str, Any]:
    """
    GET /api/trips/recent_clean?limit=N

    Списковая выдача последних рейсов для UI без мусорных регионов (RU-UNK, "Н/Д"):
      - данные берутся из public.trips_recent_clean_v,
      - confirmed_at подтягивается из public.trips по id,
      - форма ответа такая же, как у /api/trips/recent.
    """
    items: List[Dict[str, Any]] = []
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              v.id::text,
              v.status::text,
              v.created_at,
              t.confirmed_at,
              v.origin_region::text,
              v.dest_region::text,
              v.price_rub,
              v.road_km,
              v.drive_sec
            FROM public.trips_recent_clean_v v
            LEFT JOIN public.trips t ON t.id = v.id
            ORDER BY v.created_at DESC
            LIMIT %s;
            """,
            (int(limit),),
        )
        for r in cur.fetchall():
            items.append(
                {
                    "id": r[0],
                    "status": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "confirmed_at": r[3].isoformat() if r[3] else None,
                    "origin_region": r[4],
                    "dest_region": r[5],
                    "price_rub": float(r[6]) if r[6] is not None else None,
                    "road_km": float(r[7]) if r[7] is not None else None,
                    "drive_sec": int(r[8]) if r[8] is not None else None,
                }
            )
    return {"ok": True, "items": items, "limit": int(limit)}


@router.get("/recent_clean_strict")
def trips_recent_clean_strict(limit: int = Query(20, ge=1, le=500)) -> Dict[str, Any]:
    """
    GET /api/trips/recent_clean_strict?limit=N

    Строгая витрина для UI:
      - данные берутся из public.trips_recent_clean_strict_v,
      - только рейсы с маршрутом (road_km / drive_sec не NULL),
      - только за последние 3 дня (фильтр зашит во view),
      - форма ответа такая же, как у /api/trips/recent_clean.
    """
    items: List[Dict[str, Any]] = []
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              v.id::text,
              v.status::text,
              v.created_at,
              t.confirmed_at,
              v.origin_region::text,
              v.dest_region::text,
              v.price_rub,
              v.road_km,
              v.drive_sec
            FROM public.trips_recent_clean_strict_v v
            LEFT JOIN public.trips t ON t.id = v.id
            ORDER BY v.created_at DESC
            LIMIT %s;
            """,
            (int(limit),),
        )
        for r in cur.fetchall():
            items.append(
                {
                    "id": r[0],
                    "status": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "confirmed_at": r[3].isoformat() if r[3] else None,
                    "origin_region": r[4],
                    "dest_region": r[5],
                    "price_rub": float(r[6]) if r[6] is not None else None,
                    "road_km": float(r[7]) if r[7] is not None else None,
                    "drive_sec": int(r[8]) if r[8] is not None else None,
                }
            )
    return {"ok": True, "items": items, "limit": int(limit)}
