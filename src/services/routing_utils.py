# -*- coding: utf-8 -*-
# file: src/services/routing_utils.py
from __future__ import annotations
import os, math, time
from typing import Any, Dict, Tuple, Optional
from urllib.parse import urlencode

OSRM_BASE   = (os.getenv("ROUTING_BASE_URL") or os.getenv("OSRM_URL") or "http://osrm:5000").rstrip("/")
PROFILE     = os.getenv("ROUTING_OSRM_PROFILE", os.getenv("OSRM_PROFILE","driving"))
TIMEOUT     = float(os.getenv("ROUTING_TIMEOUT_SEC", os.getenv("OSRM_TIMEOUT","8")))
USE_CACHE   = str(os.getenv("OD_CACHE_ENABLED","1")).lower() in ("1","true","yes","on")
TTL_H       = int(os.getenv("OD_CACHE_TTL_H","168"))

def _q(x: float, p: int = 5) -> float:
    return round(float(x), p)

def _db():
    dsn = os.getenv("DATABASE_URL")
    try:
        import psycopg
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg
        return psycopg.connect(dsn)

def _from_cache(a: Tuple[float,float], b: Tuple[float,float]) -> Optional[Dict[str,Any]]:
    if not USE_CACHE: return None
    (alat, alon), (blat, blon) = a, b
    q = (_q(alat), _q(alon), _q(blat), _q(blon), PROFILE)
    try:
        with _db() as cn, cn.cursor() as cur:
            cur.execute("""
              SELECT distance_m, duration_s, polyline, updated_at
              FROM public.routing_od_cache
              WHERE src_lat_q=%s AND src_lon_q=%s AND dst_lat_q=%s AND dst_lon_q=%s AND profile=%s
            """, q)
            row = cur.fetchone()
            if not row: return None
            dist, dur, poly, ts = row
            # TTL
            cur.execute("SELECT EXTRACT(EPOCH FROM (now()-%s))/3600.0", (ts,))
            age_h = float(cur.fetchone()[0])
            if age_h > TTL_H: return None
            return {"distance_m": int(dist), "duration_s": int(dur), "polyline": poly, "backend": "cache"}
    except Exception:
        return None

def _to_cache(a: Tuple[float,float], b: Tuple[float,float], r: Dict[str,Any]) -> None:
    if not USE_CACHE: return
    (alat, alon), (blat, blon) = a, b
    q = (_q(alat), _q(alon), _q(blat), _q(blon), PROFILE, int(r["distance_m"]), int(r["duration_s"]), r.get("polyline"))
    try:
        with _db() as cn, cn.cursor() as cur:
            cur.execute("""
              INSERT INTO public.routing_od_cache(src_lat_q,src_lon_q,dst_lat_q,dst_lon_q,profile,distance_m,duration_s,polyline,updated_at)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s, now())
              ON CONFLICT (src_lat_q,src_lon_q,dst_lat_q,dst_lon_q,profile) DO UPDATE
                 SET distance_m=EXCLUDED.distance_m, duration_s=EXCLUDED.duration_s,
                     polyline=EXCLUDED.polyline, updated_at=now();
            """, q)
            cn.commit()
    except Exception:
        pass

def route_osrm(a: Tuple[float,float], b: Tuple[float,float]) -> Dict[str,Any]:
    """
    Маршрут из точки A(lat,lon) в B(lat,lon) через OSRM (polyline6).
    Сначала читаем кэш, потом бьёмся в OSRM, по итогу пишем в кэш.
    """
    cached = _from_cache(a,b)
    if cached: return cached

    try:
        import httpx
        path = f"{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}"
        url  = f"{OSRM_BASE}/route/v1/{PROFILE}/{path}?{urlencode({'overview':'full','geometries':'polyline6','steps':'false','alternatives':'false'})}"
        with httpx.Client(timeout=TIMEOUT) as cli:
            r = cli.get(url); r.raise_for_status(); data = r.json()
        route = (data.get("routes") or [None])[0] or {}
        out = {
            "distance_m": int(route.get("distance",0) or 0),
            "duration_s": int(route.get("duration",0) or 0),
            "polyline": route.get("geometry"),
            "backend": "osrm",
        }
        if out["distance_m"]>0 and out["duration_s"]>0:
            _to_cache(a,b,out)
        return out
    except Exception:
        # Неболезненный фолбэк — хаверсайн
        R=6371008.8
        from math import radians, sin, cos, asin, sqrt
        lat1, lon1 = map(radians, a); lat2, lon2 = map(radians, b)
        dphi, dl = lat2-lat1, lon2-lon1
        h = sin(dphi/2)**2 + cos(lat1)*cos(lat2)*sin(dl/2)**2
        d = 2*R*asin(sqrt(h))  # м
        v = 60/3.6  # 60 км/ч
        return {"distance_m": int(d), "duration_s": int(d/v), "polyline": None, "backend": "haversine"}
