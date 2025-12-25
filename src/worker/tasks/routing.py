# -*- coding: utf-8 -*-
# file: src/worker/tasks/routing.py
from __future__ import annotations

import contextlib
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task

log = logging.getLogger(__name__)

# ───────────────────────────────── DB helpers ─────────────────────────────────


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


def _safe_rollback(conn, where: str = "") -> None:
    """
    Гарантированный rollback, чтобы не тянуть aborted-transaction дальше.
    """
    rb = getattr(conn, "rollback", None)
    try:
        if callable(rb):
            rb()
        else:
            conn.rollback()  # type: ignore[attr-defined]
        if where:
            log.debug("DB rollback executed (%s).", where)
    except Exception as e:
        # rollback может не пройти только в очень экзотических случаях — логируем
        if where:
            log.warning("DB rollback failed (%s): %s", where, e)
        else:
            log.warning("DB rollback failed: %s", e)


def _safe_commit(conn, where: str = "") -> bool:
    """
    Commit с защитой: если commit упал — rollback и False.
    """
    try:
        conn.commit()
        return True
    except Exception as e:
        log.warning("DB commit failed (%s): %s", where or "commit", e)
        _safe_rollback(conn, where=(where or "commit-failed"))
        return False


def _safe_close_cursor(cur) -> None:
    with contextlib.suppress(Exception):
        cur.close()


def _safe_close_conn(conn) -> None:
    with contextlib.suppress(Exception):
        conn.close()


def _is_in_failed_tx(exc: Exception) -> bool:
    # psycopg3: psycopg.errors.InFailedSqlTransaction
    name = exc.__class__.__name__
    if name == "InFailedSqlTransaction":
        return True
    rep = repr(exc)
    return "InFailedSqlTransaction" in rep or "current transaction is aborted" in rep


# ─────────────────────────────── OD-cache writer ──────────────────────────────
try:
    from src.worker.register_tasks import od_cache_upsert_sync  # type: ignore
except Exception:

    def od_cache_upsert_sync(*a, **k):  # type: ignore
        return None


# ─────────────────────────────── GeoKey helpers ───────────────────────────────


def _geo_norm_fallback(s: str) -> str:
    return (s or "").strip().lower().replace("ё", "е")


try:
    # важно: должен совпадать с normalize_raw, который использовался при seed_aliases
    from src.core.geo.geokey import normalize_raw as _geo_normalize_raw  # type: ignore
except Exception:
    _geo_normalize_raw = None


def _geo_norm(text: Optional[str]) -> str:
    if not text:
        return ""
    s = str(text)
    if _geo_normalize_raw is None:
        return _geo_norm_fallback(s)
    try:
        return _geo_normalize_raw(s)
    except Exception:
        return _geo_norm_fallback(s)


def _load_geokey_map(conn) -> Dict[str, Tuple[float, float]]:
    """
    raw_norm -> (lat, lon) для всех resolved алиасов.
    """
    use_geokey = (os.getenv("ROUTING_ENRICH_USE_GEOKEY", "1") or "1").strip().lower() in ("1", "true", "yes", "y")
    if not use_geokey:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.raw_norm, k.lat, k.lon
                  FROM geo.geo_aliases a
                  JOIN geo.geo_keys k ON k.id = a.geo_key_id
                 WHERE a.status = 'resolved'
                   AND a.geo_key_id IS NOT NULL
                   AND k.lat IS NOT NULL AND k.lon IS NOT NULL;
                """
            )
            rows = cur.fetchall()
        mp: Dict[str, Tuple[float, float]] = {}
        for raw_norm, lat, lon in rows:
            if raw_norm is None or lat is None or lon is None:
                continue
            mp[str(raw_norm)] = (float(lat), float(lon))
        return mp
    except Exception as e:
        # geo schema может отсутствовать в некоторых сборках
        # важное: если ошибка была SQL-уровня, транзакция могла стать aborted -> rollback
        log.debug("GeoKey map load skipped: %s", e)
        _safe_rollback(conn, where="load_geokey_map")
        return {}


# ──────────────────────────────── OSRM / geometry ────────────────────────────


def _osrm_base_url() -> str:
    url = (os.getenv("OSRM_URL") or "").strip()
    if url:
        return url.rstrip("/")
    host = (os.getenv("OSRM_HOST") or "osrm").strip() or "osrm"
    port = (os.getenv("OSRM_PORT") or "5000").strip() or "5000"
    return f"http://{host}:{port}"


OSRM_URL = _osrm_base_url()
OSRM_PROFILE = os.getenv("OSRM_PROFILE", "driving")
OSRM_TIMEOUT = float(os.getenv("OSRM_TIMEOUT", "8.0") or 8.0)


def _is_valid_lat_lon(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except Exception:
        return False
    if lat_f == 0.0 and lon_f == 0.0:
        return False
    if abs(lat_f) > 90.0 or abs(lon_f) > 180.0:
        return False
    return True


def _haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    R = 6371000.0
    from math import atan2, cos, radians, sin, sqrt

    dlat = radians(b_lat - a_lat)
    dlon = radians(b_lon - a_lon)
    lat1 = radians(a_lat)
    lat2 = radians(b_lat)
    aa = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(aa), sqrt(1 - aa))
    return R * c


def _route_osrm(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> Tuple[float, int, Optional[str]]:
    path = f"/route/v1/{OSRM_PROFILE}/{a_lon:.6f},{a_lat:.6f};{b_lon:.6f},{b_lat:.6f}"
    qs = "?overview=full&geometries=polyline&alternatives=false&annotations=false&steps=false"
    url = OSRM_URL + path + qs
    try:
        try:
            import requests  # type: ignore

            r = requests.get(url, timeout=OSRM_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception:
            import urllib.request  # type: ignore

            with urllib.request.urlopen(url, timeout=OSRM_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

        routes = (data or {}).get("routes") or []
        if not routes:
            return (math.nan, 0, None)

        r0 = routes[0]
        dist = float(r0.get("distance") or 0.0)
        dur = int(round(float(r0.get("duration") or 0.0)))
        poly = r0.get("geometry")
        return (dist, dur, poly if isinstance(poly, str) else None)
    except Exception as e:
        log.debug("OSRM error: %s", e)
        return (math.nan, 0, None)


# ────────────────────────────── Region centroids cache ────────────────────────

_centroids: Dict[str, Tuple[float, float]] = {}


def _centroid(code: str) -> Optional[Tuple[float, float]]:
    if not code:
        return None
    if code in _centroids:
        return _centroids[code]
    try:
        with _pg() as c, c.cursor() as cur:
            cur.execute("SELECT lat, lon FROM public.region_centroids WHERE code = %s;", (code,))
            row = cur.fetchone()
            if not row:
                return None
            lat = float(row[0])
            lon = float(row[1])
            _centroids[code] = (lat, lon)
            return _centroids[code]
    except Exception:
        return None


def _maybe_centroid(code: Optional[str]) -> Optional[Tuple[float, float]]:
    # не долбим БД по строкам вида "ВОЛОГОДСКАЯ ОБЛАСТЬ"
    if not code:
        return None
    s = str(code).strip()
    if s.startswith("RU-") or s.startswith("ru-"):
        return _centroid(s)
    return None


# ───────────────────────────── Trip segments candidates ───────────────────────


def _candidate_segments_pool(conn, only_missing: bool, limit: int, prefer_coords: bool = True) -> List[Dict[str, Any]]:
    """
    Берём расширенный пул (limit * POOL_MULT), дальше фильтруем/сортируем в Python.

    ВАЖНО: если здесь случается SQL-ошибка (например UndefinedColumn),
    мы обязаны сделать rollback(), иначе conn останется в aborted-transaction,
    и дальше появятся InFailedSqlTransaction на любых SQL.

    ВАЖНО2: В нашей схеме public.trip_segments.id = int8, а UUID-ключ = public.trip_segments.id_uuid.
    Поэтому segment_id должен быть id_uuid.
    """
    cond: List[str] = []

    if only_missing:
        include_polyline_only = (os.getenv("ROUTING_ENRICH_INCLUDE_POLYLINE_ONLY", "0") or "0").strip().lower() in ("1", "true", "yes", "y")
        if include_polyline_only:
            # legacy режим: добивать polyline даже если road_km/drive_sec уже есть
            cond.append("(s.road_km IS NULL OR s.drive_sec IS NULL OR COALESCE(s.route_polyline, s.polyline) IS NULL)")
        else:
            # default: добиваем только core метрики (road_km/drive_sec)
            cond.append("(s.road_km IS NULL OR s.drive_sec IS NULL)")

    where = "WHERE " + " AND ".join(cond) if cond else ""

    if prefer_coords:
        order = """
            ORDER BY
              CASE
                WHEN s.src_lat IS NOT NULL AND s.src_lon IS NOT NULL AND s.dst_lat IS NOT NULL AND s.dst_lon IS NOT NULL THEN 0
                ELSE 9
              END ASC,
              COALESCE(t.confirmed_at, t.created_at) DESC NULLS LAST,
              s.trip_id DESC,
              s.segment_order ASC
        """
    else:
        order = """
            ORDER BY COALESCE(t.confirmed_at, t.created_at) DESC NULLS LAST, s.trip_id DESC, s.segment_order ASC
        """

    pool_mult = int(os.getenv("ROUTING_ENRICH_POOL_MULT", "5") or 5)
    pool_limit = max(int(limit), int(limit) * max(1, pool_mult))

    # IMPORTANT: segment_id = s.id_uuid::text (uuid key), NOT s.id::text (bigint)
    sql = f"""
        SELECT
          s.id_uuid::text,
          s.trip_id::text,
          s.segment_order,
          s.origin_region::text,
          s.dest_region::text,
          s.src_lat, s.src_lon, s.dst_lat, s.dst_lon
        FROM public.trip_segments s
        JOIN public.trips t ON t.id = s.trip_id
        {where}
        {order}
        LIMIT %s;
    """

    def _exec_pool() -> List[tuple]:
        with conn.cursor() as cur:
            cur.execute(sql, (int(pool_limit),))
            return cur.fetchall()

    try:
        rows = _exec_pool()
    except Exception as e:
        # если транзакция уже aborted, делаем rollback и один retry — это устраняет "фантомные" InFailedSqlTransaction
        if _is_in_failed_tx(e):
            log.warning("routing.enrich.trips: candidate pool hit aborted transaction; rollback+retry: %s", e)
            _safe_rollback(conn, where="candidate_segments_pool_aborted_pre_retry")
            rows = _exec_pool()
        else:
            log.warning("routing.enrich.trips: candidate pool query failed: %s", e)
            _safe_rollback(conn, where="candidate_segments_pool")
            raise

    out: List[Dict[str, Any]] = []
    for r in rows:
        seg_uuid = None if r[0] is None else str(r[0]).strip()
        if not seg_uuid:
            log.debug("routing.enrich.trips: skip row with empty id_uuid (trip_id=%s)", r[1])
            continue
        out.append(
            {
                "segment_id": seg_uuid,  # UUID string (id_uuid)
                "trip_id": str(r[1]),
                "seg_ord": int(r[2] or 1),
                "o_code": r[3],
                "d_code": r[4],
                "a_lat": None if r[5] is None else float(r[5]),
                "a_lon": None if r[6] is None else float(r[6]),
                "b_lat": None if r[7] is None else float(r[7]),
                "b_lon": None if r[8] is None else float(r[8]),
            }
        )
    return out


def _update_segment_by_id(cur, segment_id: str, km: float, sec: int, poly: Optional[str]) -> int:
    """
    Update by UUID key (public.trip_segments.id_uuid). Returns affected rows.
    """
    cur.execute(
        """
        UPDATE public.trip_segments
           SET road_km = %s,
               drive_sec = %s,
               route_polyline = COALESCE(%s, route_polyline),
               polyline = COALESCE(%s, polyline)
         WHERE id_uuid = %s::uuid;
        """,
        (float(km), int(sec), poly, poly, segment_id),
    )
    try:
        return int(cur.rowcount or 0)
    except Exception:
        return 0


def _same_place_seconds(km: float, kph: float) -> int:
    kph = max(1.0, float(kph))
    sec = int(round((float(km) / kph) * 3600.0))
    return max(1, sec)


# ───────────────────────────── Celery tasks (implementation) ──────────────────


@shared_task(name="routing.enrich.trips")
def routing_enrich_trips(only_missing: bool = True, limit: int = 1000, ttl_min: int = 60) -> Dict[str, Any]:
    """
    Enrich road/time metrics for trip_segments:

      1) direct coords (src/dst) → OSRM
      2) else GeoKey coords (geo.geo_aliases → geo.geo_keys) if available
      3) else region_centroids (only for RU-* codes)
      4) else skip

    Product heuristic:
      - if origin==destination (same normalized key) AND route collapses to ~0m (centroid case),
        set ROUTING_SAME_PLACE_KM (default 50km) instead of 0.
    """
    _ = ttl_min  # reserved

    avg_kph = float(os.getenv("ROUTING_FALLBACK_KPH", "60") or 60.0)
    avg_mps = max(1.0, (avg_kph * 1000.0) / 3600.0)

    # same-place heuristic
    same_place_km = float(os.getenv("ROUTING_SAME_PLACE_KM", "50") or 50.0)
    same_place_kph = float(os.getenv("ROUTING_SAME_PLACE_KPH", "40") or 40.0)
    same_place_eps_m = float(
        os.getenv(
            "ROUTING_SAME_PLACE_EPS_M",
            os.getenv("ROUTING_ZERO_DIST_EPS_M", "200"),
        )
        or 200.0
    )
    same_place_allow_wo_coords = (os.getenv("ROUTING_SAME_PLACE_ALLOW_WITHOUT_COORDS", "0") or "0").strip().lower() in ("1", "true", "yes", "y")

    prefer_coords = (os.getenv("ROUTING_ENRICH_PREFER_COORDS", "1") or "1").strip().lower() in ("1", "true", "yes", "y")
    require_geo = (os.getenv("ROUTING_ENRICH_REQUIRE_GEO", "1") or "1").strip().lower() in ("1", "true", "yes", "y")
    commit_every = int(os.getenv("ROUTING_ENRICH_COMMIT_EVERY", "200") or 200)

    conn = _pg()
    conn.autocommit = False

    # 🔥 P0 предохранитель: если conn каким-то образом оказался в aborted-transaction — очищаем сразу
    _safe_rollback(conn, where="routing.enrich.trips preflight")

    cur = None  # важно: чтобы finally не падал, если ошибка случится до cursor()

    try:
        geokey_map = _load_geokey_map(conn)
        # ещё один пояс: даже если geo отсутствует и был exception -> rollback уже сделан, но preflight-паттерн держим
        _safe_rollback(conn, where="routing.enrich.trips after_geokey_map")
        geokey_map_size = len(geokey_map)

        pool = _candidate_segments_pool(conn, bool(only_missing), int(limit), prefer_coords=prefer_coords)

        def _resolvable(it: Dict[str, Any]) -> Tuple[bool, bool, int]:
            """
            Returns (src_ok, dst_ok, rank)
            rank: lower is better.
              0 = both direct
              1 = one direct + one geokey
              2 = both geokey
              3 = direct/geokey + centroid
              4 = both centroid
              9 = not resolvable
            """
            a_ok = _is_valid_lat_lon(it["a_lat"], it["a_lon"])
            b_ok = _is_valid_lat_lon(it["b_lat"], it["b_lon"])

            o_norm = _geo_norm(it.get("o_code"))
            d_norm = _geo_norm(it.get("d_code"))
            same_key = bool(o_norm) and (o_norm == d_norm)

            g_a = o_norm in geokey_map
            g_b = d_norm in geokey_map

            c_a = False
            c_b = False
            if not a_ok and not g_a:
                c_a = _maybe_centroid(it.get("o_code")) is not None
            if not b_ok and not g_b:
                c_b = _maybe_centroid(it.get("d_code")) is not None

            # Optional: allow heuristic even if coords not resolvable (disabled by default)
            if same_key and same_place_allow_wo_coords:
                return (True, True, 2)

            src_ok = a_ok or g_a or c_a
            dst_ok = b_ok or g_b or c_b

            if not (src_ok and dst_ok):
                return (src_ok, dst_ok, 9)

            if a_ok and b_ok:
                return (True, True, 0)
            if (a_ok and g_b) or (g_a and b_ok):
                return (True, True, 1)
            if g_a and g_b:
                return (True, True, 2)
            if (a_ok or g_a) and c_b:
                return (True, True, 3)
            if (b_ok or g_b) and c_a:
                return (True, True, 3)
            if c_a and c_b:
                return (True, True, 4)
            return (True, True, 5)

        resolvable: List[Tuple[int, Dict[str, Any]]] = []
        non_resolvable: List[Dict[str, Any]] = []

        for it in pool:
            _, _, rank = _resolvable(it)
            if rank < 9:
                resolvable.append((rank, it))
            else:
                non_resolvable.append(it)

        resolvable.sort(key=lambda x: x[0])
        cand: List[Dict[str, Any]] = [it for _, it in resolvable[: int(limit)]]

        if not require_geo and len(cand) < int(limit):
            cand.extend(non_resolvable[: max(0, int(limit) - len(cand))])

        selected = len(cand)
        pool_selected = len(pool)
        pool_resolvable = len(resolvable)

        processed = 0
        updated = 0
        skipped = 0

        skipped_no_coords = 0
        skipped_bad_coords = 0

        used_geokey_src = 0
        used_geokey_dst = 0
        used_geokey_both = 0

        used_centroid_src = 0
        used_centroid_dst = 0
        used_centroid_both = 0

        same_place_cnt = 0
        same_place_no_coords_cnt = 0
        same_place_eps_cnt = 0

        osrm_ok = 0
        fallback_haversine_attempted = 0
        fallback_haversine_used = 0

        update_errors = 0
        last_update_error: Optional[str] = None
        update_zero_rowcount = 0

        cur = conn.cursor()
        pending = 0

        for it in cand:
            seg_id = str(it["segment_id"]).strip()
            if not seg_id:
                skipped += 1
                continue

            trip_id = it["trip_id"]
            seg_ord = it["seg_ord"]

            o_code = it.get("o_code")
            d_code = it.get("d_code")

            o_norm = _geo_norm(o_code)
            d_norm = _geo_norm(d_code)
            same_key = bool(o_norm) and (o_norm == d_norm)

            a_lat, a_lon = it["a_lat"], it["a_lon"]
            b_lat, b_lon = it["b_lat"], it["b_lon"]

            g_src_used = False
            g_dst_used = False
            c_src_used = False
            c_dst_used = False

            # GeoKey src
            if not _is_valid_lat_lon(a_lat, a_lon):
                p = geokey_map.get(o_norm)
                if p and _is_valid_lat_lon(p[0], p[1]):
                    a_lat, a_lon = p[0], p[1]
                    g_src_used = True

            # GeoKey dst
            if not _is_valid_lat_lon(b_lat, b_lon):
                p = geokey_map.get(d_norm)
                if p and _is_valid_lat_lon(p[0], p[1]):
                    b_lat, b_lon = p[0], p[1]
                    g_dst_used = True

            if g_src_used and g_dst_used:
                used_geokey_both += 1
            elif g_src_used:
                used_geokey_src += 1
            elif g_dst_used:
                used_geokey_dst += 1

            # RU-centroid fallback (only for RU-* codes)
            if not _is_valid_lat_lon(a_lat, a_lon):
                c0 = _maybe_centroid(o_code)
                if c0:
                    a_lat, a_lon = c0
                    c_src_used = True

            if not _is_valid_lat_lon(b_lat, b_lon):
                c1 = _maybe_centroid(d_code)
                if c1:
                    b_lat, b_lon = c1
                    c_dst_used = True

            if c_src_used and c_dst_used:
                used_centroid_both += 1
            elif c_src_used:
                used_centroid_src += 1
            elif c_dst_used:
                used_centroid_dst += 1

            # If still no coords: optionally apply same-place heuristic
            if not (_is_valid_lat_lon(a_lat, a_lon) and _is_valid_lat_lon(b_lat, b_lon)):
                if same_key and same_place_allow_wo_coords:
                    km = float(same_place_km)
                    sec = _same_place_seconds(km, same_place_kph)
                    processed += 1
                    same_place_cnt += 1
                    same_place_no_coords_cnt += 1
                    try:
                        rc = _update_segment_by_id(cur, seg_id, km, sec, None)
                        if rc <= 0:
                            update_zero_rowcount += 1
                        else:
                            updated += 1
                        pending += 1
                        if pending >= commit_every:
                            if _safe_commit(conn, where="routing.enrich.trips commit"):
                                pending = 0
                            else:
                                _safe_close_cursor(cur)
                                cur = conn.cursor()
                                pending = 0
                    except Exception as e:
                        update_errors += 1
                        if last_update_error is None:
                            last_update_error = f"{type(e).__name__}: {e}"
                            log.warning("routing.enrich.trips first update error: %s", last_update_error)
                        log.warning("segment update failed seg_id=%s trip=%s ord=%s: %s", seg_id, trip_id, seg_ord, e)
                        _safe_rollback(conn, where="segment_update_same_place_wo_coords")
                        _safe_close_cursor(cur)
                        cur = conn.cursor()
                    continue

                skipped += 1
                skipped_no_coords += 1
                continue

            a_lat_f = float(a_lat)  # type: ignore[arg-type]
            a_lon_f = float(a_lon)  # type: ignore[arg-type]
            b_lat_f = float(b_lat)  # type: ignore[arg-type]
            b_lon_f = float(b_lon)  # type: ignore[arg-type]

            # If points collapsed (centroid case) and same_key -> use heuristic
            try:
                d0 = _haversine_m(a_lat_f, a_lon_f, b_lat_f, b_lon_f)
            except Exception:
                d0 = math.nan

            if same_key and math.isfinite(d0) and d0 <= same_place_eps_m:
                km = float(same_place_km)
                sec = _same_place_seconds(km, same_place_kph)
                processed += 1
                same_place_cnt += 1
                same_place_eps_cnt += 1
                try:
                    rc = _update_segment_by_id(cur, seg_id, km, sec, None)
                    if rc <= 0:
                        update_zero_rowcount += 1
                    else:
                        updated += 1
                    pending += 1
                    if pending >= commit_every:
                        if _safe_commit(conn, where="routing.enrich.trips commit"):
                            pending = 0
                        else:
                            _safe_close_cursor(cur)
                            cur = conn.cursor()
                            pending = 0
                except Exception as e:
                    update_errors += 1
                    if last_update_error is None:
                        last_update_error = f"{type(e).__name__}: {e}"
                        log.warning("routing.enrich.trips first update error: %s", last_update_error)
                    log.warning("segment update failed seg_id=%s trip=%s ord=%s: %s", seg_id, trip_id, seg_ord, e)
                    _safe_rollback(conn, where="segment_update_same_place_eps")
                    _safe_close_cursor(cur)
                    cur = conn.cursor()
                continue

            dist_m, dur_s, poly = _route_osrm(a_lat_f, a_lon_f, b_lat_f, b_lon_f)

            if math.isfinite(dist_m) and dist_m > 0 and dur_s > 0:
                osrm_ok += 1
            else:
                # Fallback: Haversine + avg speed
                fallback_haversine_attempted += 1
                dist_m2 = _haversine_m(a_lat_f, a_lon_f, b_lat_f, b_lon_f)

                # if still collapsed and same_key -> use heuristic
                if same_key and math.isfinite(dist_m2) and dist_m2 <= same_place_eps_m:
                    km = float(same_place_km)
                    dur_s = _same_place_seconds(km, same_place_kph)
                    dist_m = km * 1000.0
                    poly = None
                    same_place_cnt += 1
                    same_place_eps_cnt += 1
                else:
                    if not (math.isfinite(dist_m2) and dist_m2 > 0):
                        skipped += 1
                        skipped_bad_coords += 1
                        continue
                    fallback_haversine_used += 1
                    dist_m = dist_m2
                    dur_s = int(max(1.0, dist_m / avg_mps))
                    poly = None

            km = dist_m / 1000.0
            sec = int(dur_s)
            processed += 1

            try:
                rc = _update_segment_by_id(cur, seg_id, km, sec, poly)
                if rc <= 0:
                    update_zero_rowcount += 1
                else:
                    updated += 1
                pending += 1
                if pending >= commit_every:
                    if _safe_commit(conn, where="routing.enrich.trips commit"):
                        pending = 0
                    else:
                        _safe_close_cursor(cur)
                        cur = conn.cursor()
                        pending = 0
            except Exception as e:
                update_errors += 1
                if last_update_error is None:
                    last_update_error = f"{type(e).__name__}: {e}"
                    log.warning("routing.enrich.trips first update error: %s", last_update_error)
                log.warning("segment update failed seg_id=%s trip=%s ord=%s: %s", seg_id, trip_id, seg_ord, e)
                _safe_rollback(conn, where="segment_update")
                _safe_close_cursor(cur)
                cur = conn.cursor()
                continue

            # OD-cache best-effort
            try:
                od_cache_upsert_sync(a_lat_f, a_lon_f, b_lat_f, b_lon_f, float(dist_m), int(sec), poly, OSRM_PROFILE, "osrm")
            except Exception:
                pass

        if pending > 0:
            _safe_commit(conn, where="routing.enrich.trips final_commit")

        return {
            "ok": True,
            "pool_selected": pool_selected,
            "pool_resolvable": pool_resolvable,
            "selected": selected,
            "processed": processed,
            "updated": updated,
            "update_zero_rowcount": update_zero_rowcount,
            "skipped": skipped,
            "skipped_no_coords": skipped_no_coords,
            "skipped_bad_coords": skipped_bad_coords,
            "same_place_cnt": same_place_cnt,
            "same_place_no_coords_cnt": same_place_no_coords_cnt,
            "same_place_eps_cnt": same_place_eps_cnt,
            "same_place_km": same_place_km,
            "same_place_kph": same_place_kph,
            "same_place_eps_m": same_place_eps_m,
            "geokey_map_size": geokey_map_size,
            "used_geokey_src": used_geokey_src,
            "used_geokey_dst": used_geokey_dst,
            "used_geokey_both": used_geokey_both,
            "used_centroid_src": used_centroid_src,
            "used_centroid_dst": used_centroid_dst,
            "used_centroid_both": used_centroid_both,
            "osrm_ok": osrm_ok,
            "fallback_haversine_attempted": fallback_haversine_attempted,
            "fallback_haversine_used": fallback_haversine_used,
            "update_errors": update_errors,
            "last_update_error": last_update_error,
            "only_missing": bool(only_missing),
            "limit": int(limit),
            "prefer_coords": bool(prefer_coords),
            "require_geo": bool(require_geo),
            "osrm_url": OSRM_URL,
            "profile": OSRM_PROFILE,
        }

    except Exception:
        _safe_rollback(conn, where="routing.enrich.trips outer")
        raise

    finally:
        if cur is not None:
            _safe_close_cursor(cur)
        _safe_close_conn(conn)


@shared_task(name="routing.enrich.confirmed")
def routing_enrich_confirmed(limit: int = 1500, only_missing: bool = True) -> Dict[str, Any]:
    return routing_enrich_trips(only_missing=bool(only_missing), limit=int(limit))
