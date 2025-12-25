# -*- coding: utf-8 -*-
from __future__ import annotations
from fastapi import APIRouter, Body, HTTPException, Path
from typing import Any, Dict
import os

router = APIRouter(prefix="/api", tags=["fleet"])

def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn: return dsn
    user = os.getenv("POSTGRES_USER","admin")
    pwd  = os.getenv("POSTGRES_PASSWORD","admin")
    host = os.getenv("POSTGRES_HOST","postgres")
    port = os.getenv("POSTGRES_PORT","5432")
    db   = os.getenv("POSTGRES_DB","foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    try:
        import psycopg; return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg; return psycopg.connect(_db_dsn())

@router.get("/trucks")
def trucks_list():
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, plate_number, role, body_type, region FROM public.trucks ORDER BY plate_number")
        rows = cur.fetchall()
        return {"ok": True, "items":[{"id":r[0], "plate_number":r[1], "role":r[2], "body_type":r[3], "region":r[4]} for r in rows]}
    finally:
        try: conn.close()
        except Exception: pass

@router.post("/trucks")
def trucks_create(data: Dict[str, Any] = Body(...)):
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("""
              INSERT INTO public.trucks(plate_number, role, body_type, region, features, caps)
              VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING id
            """, (
                data.get("plate_number"),
                (data.get("features") or {}).get("role") or data.get("role") or "tractor",
                data.get("body_type"),
                data.get("region"),
                JsonWrapper(data.get("features") or {}),
                JsonWrapper(data.get("caps") or {}),
            ))
            rid = cur.fetchone()[0]
            conn.commit()
            return {"ok": True, "id": rid}
    finally:
        try: conn.close()
        except Exception: pass

@router.post("/trucks/attach_trailer")
def attach_trailer(data: Dict[str, Any] = Body(...)):
    tractor_id = data.get("tractor_id"); trailer_id = data.get("trailer_id")
    if not tractor_id or not trailer_id: raise HTTPException(400, "tractor_id & trailer_id required")
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE public.trucks SET trailer_id=%s WHERE id=%s", (trailer_id, tractor_id))
            conn.commit()
            return {"ok": True}
    finally:
        try: conn.close()
        except Exception: pass

@router.post("/drivers")
def create_driver(data: Dict[str,Any] = Body(...)):
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO public.drivers(full_name, phone, license_no)
            VALUES (%s,%s,%s) RETURNING driver_id
        """, (data.get("full_name"), data.get("phone"), data.get("license_no")))
        rid = cur.fetchone()[0]
        conn.commit()
        return {"ok": True, "driver_id": rid}
    finally:
        try: conn.close()
        except Exception: pass

@router.post("/trucks/{truck_id}/driver/assign")
def assign_driver(truck_id: str = Path(...), data: Dict[str,Any] = Body(...)):
    driver_id = data.get("driver_id")
    if not driver_id: raise HTTPException(400, "driver_id required")
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE public.trucks SET driver_id=%s WHERE id=%s", (driver_id, truck_id))
            conn.commit()
            return {"ok": True}
    finally:
        try: conn.close()
        except Exception: pass

@router.get("/trucks/{truck_id}/card")
def truck_card(truck_id: str = Path(...)):
    conn=_connect_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
          SELECT t.id, t.plate_number, t.role, t.body_type, t.region, t.trailer_id, t.driver_id
          FROM public.trucks t WHERE t.id=%s
        """, (truck_id,))
        t = cur.fetchone()
        if not t: raise HTTPException(404,"truck_not_found")
        trailer, driver = None, None
        if t[5]:
            cur.execute("SELECT id, plate_number, body_type FROM public.trucks WHERE id=%s", (t[5],))
            r = cur.fetchone(); trailer = {"id": r[0], "plate_number": r[1], "body_type": r[2]} if r else None
        if t[6]:
            cur.execute("SELECT driver_id, full_name, phone, license_no FROM public.drivers WHERE driver_id=%s", (t[6],))
            r = cur.fetchone(); driver = {"driver_id": r[0], "full_name": r[1], "phone": r[2], "license_no": r[3]} if r else None
        return {"ok": True, "truck":{"id":t[0],"plate_number":t[1],"role":t[2],"body_type":t[3],"region":t[4]}, "trailer": trailer, "driver": driver}
    finally:
        try: conn.close()
        except Exception: pass

class JsonWrapper:
    def __init__(self, obj: Any): self.obj=obj
    def __conform__(self, proto): return self
    def getquoted(self):
        import json
        return ("'"+json.dumps(self.obj, ensure_ascii=False).replace("'","''")+"'").encode("utf-8")
