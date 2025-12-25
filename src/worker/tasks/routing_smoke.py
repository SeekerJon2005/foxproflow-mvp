# -*- coding: utf-8 -*-
# file: src/worker/tasks/routing_smoke.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

from celery import shared_task

log = logging.getLogger(__name__)


def _db_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    auth = f":{pwd}" if pwd else ""
    return f"postgresql://{user}{auth}@{host}:{port}/{db}"


def _pg():
    dsn = _db_dsn()
    try:
        import psycopg  # psycopg3

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # fallback psycopg2

        return psycopg.connect(dsn)


def _osrm_url() -> str:
    url = (os.getenv("OSRM_URL") or "").strip()
    if url:
        return url.rstrip("/")
    host = (os.getenv("OSRM_HOST") or "osrm").strip() or "osrm"
    port = (os.getenv("OSRM_PORT") or "5000").strip() or "5000"
    return f"http://{host}:{port}"


def _http_get_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    try:
        import requests  # type: ignore

        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        import urllib.request  # type: ignore

        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


@shared_task(name="routing.smoke.osrm_and_db")
def routing_smoke_osrm_and_db(segment_uuid: Optional[str] = None) -> Dict[str, Any]:
    """
    Smoke:
      1) OSRM /route endpoint responds and returns geometry.
      2) DB: public.trip_segments has id_uuid column.
      3) Optional: if segment_uuid provided, verifies row exists and can be selected.
    """
    t0 = time.time()
    osrm = _osrm_url()

    # OSRM smoke: Moscow -> SPb (same as our manual test)
    url = (
        f"{osrm}/route/v1/driving/"
        f"37.6173,55.7558;30.3351,59.9343"
        f"?overview=full&geometries=polyline&alternatives=false&steps=false"
    )
    data = _http_get_json(url, timeout=float(os.getenv("OSRM_TIMEOUT", "6") or 6))
    routes = (data or {}).get("routes") or []
    ok_osrm = bool(routes) and isinstance(routes[0].get("geometry"), str) and len(routes[0].get("geometry")) > 10

    db_ok = False
    seg_ok = None  # tri-state

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS(
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema='public' AND table_name='trip_segments' AND column_name='id_uuid'
            );
            """
        )
        db_ok = bool(cur.fetchone()[0])

        if segment_uuid is not None:
            cur.execute(
                "SELECT 1 FROM public.trip_segments WHERE id_uuid = %s::uuid LIMIT 1;",
                (segment_uuid,),
            )
            seg_ok = cur.fetchone() is not None

    dt_ms = int((time.time() - t0) * 1000)
    return {
        "ok": bool(ok_osrm and db_ok and (seg_ok is not False)),
        "osrm_ok": ok_osrm,
        "db_ok": db_ok,
        "segment_uuid_checked": segment_uuid,
        "segment_found": seg_ok,
        "elapsed_ms": dt_ms,
    }
