# -*- coding: utf-8 -*-
# file: src/api/routers/routing.py
from __future__ import annotations

import os
import json
import math
import urllib.request
import urllib.parse
from typing import List, Optional, Literal, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

# --- Router ---
router = APIRouter(prefix="/api/routing", tags=["routing"])

# --- ENV / Defaults ---
# Унифицируем дефолтный адрес контейнера OSRM из docker-compose
OSRM_URL = os.getenv("OSRM_URL", "http://osrm:5000").rstrip("/")
OSRM_PROFILE_DEFAULT = (os.getenv("OSRM_PROFILE", "driving").strip() or "driving")
# Чуть более щедрый таймаут для сетевых затыков
OSRM_TIMEOUT = float(os.getenv("OSRM_TIMEOUT", "8.0"))

# Скорость для фолбэка по прямой (км/ч) — общий флаг для API/worker
try:
    OSRM_FALLBACK_SPEED_KMH = float(os.getenv("OSRM_FALLBACK_SPEED_KMH", "70"))
except Exception:
    OSRM_FALLBACK_SPEED_KMH = 70.0

# OD-cache controls (мягко-опционально; при недоступности БД деградируем тихо)
OD_CACHE_ENABLED = os.getenv("OD_CACHE_ENABLED", "1") == "1"
try:
    OD_CACHE_TTL_H = int(os.getenv("OD_CACHE_TTL_H", "168"))  # 7 суток
except Exception:
    OD_CACHE_TTL_H = 168

# --- Models (Pydantic v2) ---
class Coord(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class RouteRequest(BaseModel):
    coords: List[Coord] = Field(..., min_length=2, max_length=100)
    profile: Optional[str] = None
    overview: Literal["simplified", "full", "false"] = "full"
    geometry: Literal["polyline", "polyline6", "geojson", "false"] = "polyline6"

class RouteResponse(BaseModel):
    distance_m: float
    duration_s: float
    polyline: Optional[str] = ""
    backend: Literal["osrm", "haversine"]

class MatrixRequest(BaseModel):
    # Универсальный формат: coords — список точек; по умолчанию строим полную матрицу NxN.
    coords: List[Coord] = Field(..., min_length=2, max_length=100)
    profile: Optional[str] = None
    sources: Optional[List[int]] = None          # индексы в coords
    destinations: Optional[List[int]] = None     # индексы в coords
    annotations: Literal["duration", "distance", "duration,distance"] = "duration,distance"

class MatrixResponse(BaseModel):
    distances: Optional[List[List[float]]] = None
    durations: Optional[List[List[float]]] = None
    backend: Literal["osrm", "haversine"]

# --- Helpers: parsing / math ---
def _parse_lonlat(text: str) -> Tuple[float, float]:
    # ожидаем "lon,lat"
    try:
        lon, lat = [float(x) for x in text.split(",", 1)]
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("out of range")
        return lon, lat
    except Exception:
        raise HTTPException(400, f"bad coord '{text}', expected 'lon,lat'")

def _parse_coords_list(text: str) -> List[Coord]:
    # "lon,lat;lon,lat;..."
    try:
        parts = [p for p in (text or "").split(";") if p]
        coords: List[Coord] = []
        for p in parts:
            lon, lat = _parse_lonlat(p)
            coords.append(Coord(lat=lat, lon=lon))
        if len(coords) < 2:
            raise ValueError("need at least 2 coords")
        return coords
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "bad 'coords' format, expected 'lon,lat;lon,lat;...'")

def _parse_indices(csv: Optional[str]) -> Optional[List[int]]:
    if not csv:
        return None
    try:
        vals = [int(x) for x in csv.split(",") if x.strip() != ""]
        if not vals:
            return None
        return vals
    except Exception:
        raise HTTPException(400, "bad indices, expected '0,1,2'")

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

# --- Helpers: HTTP/OSRM ---
def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",   # дружим с PowerShell
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)

def _fmt_coords_lonlat(coords: List[Coord]) -> str:
    # В пути (path) координаты не кодируем, сохраняем ',' и ';'
    return ";".join(f"{c.lon:.6f},{c.lat:.6f}" for c in coords)

def _route_osrm_sync(coords: List[Coord], profile: str, overview: str, geometry: str) -> RouteResponse:
    coords_str = _fmt_coords_lonlat(coords)
    # Сохраняем ';' и ',' в query-параметрах
    qs = urllib.parse.urlencode(
        {"overview": overview, "geometries": geometry, "steps": "false", "annotations": "false"},
        safe=";,",
    )
    url = f"{OSRM_URL}/route/v1/{urllib.parse.quote(profile)}/{coords_str}?{qs}"
    data = _http_get_json(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("message") or data.get("code") or "OSRM route error")
    r0 = data["routes"][0]
    return RouteResponse(
        distance_m=float(r0["distance"]),
        duration_s=float(r0["duration"]),
        polyline=(r0.get("geometry") or ""),
        backend="osrm",
    )

def _table_osrm_sync(
    coords: List[Coord],
    profile: str,
    annotations: str,
    sources_idx: Optional[List[int]],
    dest_idx: Optional[List[int]],
) -> MatrixResponse:
    coords_str = _fmt_coords_lonlat(coords)
    params = {"annotations": annotations}
    if sources_idx:
        params["sources"] = ";".join(str(i) for i in sources_idx)
    if dest_idx:
        params["destinations"] = ";".join(str(i) for i in dest_idx)
    qs = urllib.parse.urlencode(params, safe=";,")
    url = f"{OSRM_URL}/table/v1/{urllib.parse.quote(profile)}/{coords_str}?{qs}"
    try:
        data = _http_get_json(url)
        if data.get("code") != "Ok":
            raise RuntimeError(data.get("message") or data.get("code") or "OSRM table error")
        return MatrixResponse(
            durations=data.get("durations"),
            distances=data.get("distances"),
            backend="osrm",
        )
    except Exception:
        # Fallback: считаем матрицу хаверсайном и оцениваем время по OSRM_FALLBACK_SPEED_KMH
        if not sources_idx:
            sources_idx = list(range(len(coords)))
        if not dest_idx:
            dest_idx = list(range(len(coords)))
        speed_mps = max(1.0, OSRM_FALLBACK_SPEED_KMH * (1000.0 / 3600.0))

        # матрицы Nsrc x Ndst
        distances: List[List[float]] = []
        durations: List[List[float]] = []
        for i in sources_idx:
            row_d: List[float] = []
            row_t: List[float] = []
            a = coords[i]
            for j in dest_idx:
                b = coords[j]
                d = _haversine_m(a.lat, a.lon, b.lat, b.lon)
                row_d.append(d)
                row_t.append(d / speed_mps)
            distances.append(row_d)
            durations.append(row_t)

        # Отдаём только то, что просили
        out_dist = distances if ("distance" in annotations) else None
        out_dur  = durations if ("duration" in annotations) else None
        return MatrixResponse(distances=out_dist, durations=out_dur, backend="haversine")

# --- Helpers: OD-cache (DB) ---
def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "admin")  # унифицируем дефолт
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    """
    Пытаемся использовать psycopg (v3), при неуспехе — psycopg2.
    Возвращает соединение; вызывающий обязан закрыть.
    """
    try:
        import psycopg  # type: ignore
        return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(_db_dsn())

def _od_cache_get(a_lat: float, a_lon: float, b_lat: float, b_lon: float,
                  profile: str, backend: str):
    """
    Возвращает (distance_m, duration_s, polyline) или None.
    Тихо проглатывает ошибки (кэш — оптимизация, не критичный путь).
    Ожидаемые функции в БД: fn_od_distance_cache_get(..., ttl_h DEFAULT)
    """
    if not OD_CACHE_ENABLED:
        return None
    try:
        with _connect_pg() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT distance_m, duration_s, polyline "
                    "FROM public.fn_od_distance_cache_get(%s,%s,%s,%s,%s,%s)",
                    (a_lat, a_lon, b_lat, b_lon, profile, backend),
                )
                row = cur.fetchone()
                if row:
                    dist = float(row[0]) if row[0] is not None else None
                    dur = int(row[1]) if row[1] is not None else None
                    poly = row[2]
                    if dist and dur:
                        return dist, dur, poly
    except Exception:
        pass
    return None

def _od_cache_put(a_lat: float, a_lon: float, b_lat: float, b_lon: float,
                  profile: str, backend: str,
                  distance_m: float, duration_s: float, polyline: Optional[str]):
    """
    Idempotent upsert результата. Тихая деградация при ошибках.
    Ожидаемая функция в БД: fn_od_distance_cache_upsert(..., ttl_h DEFAULT)
    """
    if not OD_CACHE_ENABLED:
        return
    if distance_m <= 0 or duration_s <= 0:
        return
    try:
        with _connect_pg() as conn:
            with conn.cursor() as cur:
                # пытаемся с TTL, если нет такой сигнатуры — падаем на короткую
                try:
                    cur.execute(
                        "SELECT public.fn_od_distance_cache_upsert(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (a_lat, a_lon, b_lat, b_lon, profile, backend,
                         float(distance_m), int(duration_s), polyline, int(OD_CACHE_TTL_H)),
                    )
                except Exception:
                    cur.execute(
                        "SELECT public.fn_od_distance_cache_upsert(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (a_lat, a_lon, b_lat, b_lon, profile, backend,
                         float(distance_m), int(duration_s), polyline),
                    )
                conn.commit()
    except Exception:
        pass

# --- Core (shared) ---
def _route_core(coords: List[Coord], profile: str, overview: str, geometry: str) -> RouteResponse:
    # OD-cache short path: только для пары A→B
    if OD_CACHE_ENABLED and len(coords) == 2:
        a, b = coords[0], coords[1]
        hit = _od_cache_get(a.lat, a.lon, b.lat, b.lon, profile, "osrm")
        if hit:
            dist_m, dur_s, poly = hit
            return RouteResponse(distance_m=dist_m, duration_s=float(dur_s), polyline=poly or "", backend="osrm")

    # Основной путь: OSRM
    try:
        resp = _route_osrm_sync(coords, profile, overview, geometry)

        # Кладём в кэш только «чистые» A→B
        if OD_CACHE_ENABLED and len(coords) == 2 and resp.backend == "osrm":
            a, b = coords[0], coords[1]
            try:
                _od_cache_put(a.lat, a.lon, b.lat, b.lon, profile, "osrm",
                              resp.distance_m, float(resp.duration_s), resp.polyline)
            except Exception:
                pass
        return resp

    except Exception as e:
        # Фоллбэк: прямая суммарная дистанция + оценка времени
        try:
            dist = 0.0
            for a, b in zip(coords, coords[1:]):
                dist += _haversine_m(a.lat, a.lon, b.lat, b.lon)
            speed_mps = max(1.0, OSRM_FALLBACK_SPEED_KMH * (1000.0 / 3600.0))
            duration_s = dist / speed_mps
            return RouteResponse(distance_m=dist, duration_s=duration_s, polyline="", backend="haversine")
        except Exception:
            raise HTTPException(status_code=502, detail=f"Routing failed: {str(e)}")

# --- Endpoints: health ---
@router.get("/health")
def routing_health():
    return {
        "ok": True,
        "backend": "osrm",
        "base": OSRM_URL,
        "profile": OSRM_PROFILE_DEFAULT,
        "timeout_sec": OSRM_TIMEOUT,
        "cache": {"enabled": OD_CACHE_ENABLED, "ttl_h": OD_CACHE_TTL_H},
        "fallback_speed_kmh": OSRM_FALLBACK_SPEED_KMH,
    }

# --- Endpoints: POST API (JSON) ---
@router.post("/route", response_model=RouteResponse)
async def route(req: RouteRequest) -> RouteResponse:
    profile = (req.profile or OSRM_PROFILE_DEFAULT)
    return await run_in_threadpool(_route_core, req.coords, profile, req.overview, req.geometry)

@router.post("/table", response_model=MatrixResponse)
async def table(req: MatrixRequest) -> MatrixResponse:
    profile = req.profile or OSRM_PROFILE_DEFAULT
    return await run_in_threadpool(
        _table_osrm_sync,
        req.coords,
        profile,
        req.annotations,
        req.sources,
        req.destinations,
    )

# --- Endpoints: GET convenience (query-string) ---
@router.get("/route", response_model=RouteResponse)
async def route_get(
    src: str = Query(..., description="lon,lat"),
    dst: str = Query(..., description="lon,lat"),
    profile: Optional[str] = Query(None),
    overview: Literal["simplified", "full", "false"] = "full",
    geometry: Literal["polyline", "polyline6", "geojson", "false"] = "polyline6",
) -> RouteResponse:
    s_lon, s_lat = _parse_lonlat(src)
    d_lon, d_lat = _parse_lonlat(dst)
    coords = [Coord(lat=s_lat, lon=s_lon), Coord(lat=d_lat, lon=d_lon)]
    pr = (profile or OSRM_PROFILE_DEFAULT)
    return await run_in_threadpool(_route_core, coords, pr, overview, geometry)

@router.get("/table", response_model=MatrixResponse)
async def table_get(
    coords: str = Query(..., description="lon,lat;lon,lat;..."),
    profile: Optional[str] = Query(None),
    sources: Optional[str] = Query(None, description="0,1,2"),
    destinations: Optional[str] = Query(None, description="0,2,3"),
    annotations: Literal["duration", "distance", "duration,distance"] = "duration,distance",
) -> MatrixResponse:
    c = _parse_coords_list(coords)
    s_idx = _parse_indices(sources)
    d_idx = _parse_indices(destinations)
    pr = (profile or OSRM_PROFILE_DEFAULT)
    return await run_in_threadpool(_table_osrm_sync, c, pr, annotations, s_idx, d_idx)
