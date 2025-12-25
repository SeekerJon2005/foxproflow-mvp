# -*- coding: utf-8 -*-
# file: src/core/geo/geokey.py
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# ───────────────────────────────── DB connect ─────────────────────────────────

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


def pg_connect():
    dsn = _db_dsn()
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # psycopg2 fallback
        return psycopg.connect(dsn)


# ───────────────────────────── normalization / kind ───────────────────────────

_JUNK_TOKENS = {
    "нд", "г", "г.", "го", "гo", "г/о", "г.о", "город", "р-н", "район",
}

def normalize_raw(text: str) -> str:
    s = (text or "").strip().lower()
    s = s.replace("ё", "е")
    # unify punctuation to spaces
    s = re.sub(r"[^\w\s\-]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()
    if not s:
        return ""
    toks = [t for t in s.split(" ") if t and t not in _JUNK_TOKENS]
    # common cleanups
    if toks and toks[-1] == "нд":
        toks = toks[:-1]
    s = " ".join(toks).strip()
    return s


def guess_kind(raw_norm: str) -> str:
    s = raw_norm
    if not s:
        return "unknown"
    if s in ("ru-unk", "ru unk", "unk"):
        return "unknown"
    if any(x in s for x in ("область", "край", "республика", "ао", "округ")):
        return "region"
    return "locality"


# ─────────────────────────────── Yandex client ───────────────────────────────

@dataclass
class YandexGeocodeResult:
    ok: bool
    lat: Optional[float] = None
    lon: Optional[float] = None
    provider_uri: Optional[str] = None
    display_name: Optional[str] = None
    kind: str = "unknown"
    precision: Optional[str] = None
    country_code: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class YandexGeocoderClient:
    """
    HTTP Geocoder endpoint:
      https://geocode-maps.yandex.ru/v1/?apikey=...&geocode=...&lang=ru_RU&format=json
    """
    def __init__(self, api_key: str, lang: str = "ru_RU", timeout_sec: float = 8.0):
        self.api_key = api_key
        self.lang = lang
        self.timeout_sec = timeout_sec
        self.base_url = "https://geocode-maps.yandex.ru/v1/"

    def geocode_one(self, query: str) -> YandexGeocodeResult:
        if not self.api_key:
            return YandexGeocodeResult(ok=False, error="YANDEX_GEOCODER_API_KEY is empty")

        q = (query or "").strip()
        if not q:
            return YandexGeocodeResult(ok=False, error="empty query")

        # bias to Russia without being too strict
        q2 = q if ("россия" in q.lower()) else (q + ", Россия")

        params = {
            "apikey": self.api_key,
            "geocode": q2,
            "lang": self.lang,
            "format": "json",
            "results": 1,
        }

        try:
            import urllib.parse
            import urllib.request
            url = self.base_url + "?" + urllib.parse.urlencode(params)
            with urllib.request.urlopen(url, timeout=self.timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return YandexGeocodeResult(ok=False, error=f"request failed: {type(e).__name__}: {e}")

        try:
            fm = payload["response"]["GeoObjectCollection"]["featureMember"]
            if not fm:
                return YandexGeocodeResult(ok=False, raw=payload, error="no results")
            g = fm[0]["GeoObject"]
            pos = g["Point"]["pos"]  # "lon lat"
            lon_s, lat_s = pos.split()
            lon = float(lon_s); lat = float(lat_s)

            md = g.get("metaDataProperty", {}).get("GeocoderMetaData", {}) or {}
            precision = md.get("precision")
            kind = md.get("kind") or "unknown"

            addr = md.get("Address", {}) or {}
            country_code = addr.get("country_code")
            display = md.get("text") or g.get("name") or q2
            uri = g.get("uri")

            return YandexGeocodeResult(
                ok=True,
                lat=lat,
                lon=lon,
                provider_uri=uri,
                display_name=display,
                kind=str(kind),
                precision=str(precision) if precision is not None else None,
                country_code=str(country_code) if country_code is not None else None,
                raw=payload,
            )
        except Exception as e:
            return YandexGeocodeResult(ok=False, raw=payload, error=f"parse failed: {type(e).__name__}: {e}")


# ─────────────────────────────── quota (DB) ───────────────────────────────────

def quota_try_consume(conn, provider: str, n: int, daily_limit: int) -> bool:
    """
    Atomic quota: update used if used+n <= daily_limit.
    """
    provider = provider or "yandex"
    n = int(n)
    daily_limit = int(daily_limit)

    with conn.cursor() as cur:
        # ensure row exists
        cur.execute(
            """
            INSERT INTO geo.api_usage_daily(day, provider, used, daily_limit)
            VALUES (current_date, %s, 0, %s)
            ON CONFLICT(day, provider) DO UPDATE
              SET daily_limit = EXCLUDED.daily_limit;
            """,
            (provider, daily_limit),
        )
        cur.execute(
            """
            UPDATE geo.api_usage_daily
               SET used = used + %s
             WHERE day = current_date
               AND provider = %s
               AND used + %s <= daily_limit
            RETURNING used, daily_limit;
            """,
            (n, provider, n),
        )
        row = cur.fetchone()
        return row is not None


# ─────────────────────────────── aliases / keys ───────────────────────────────

def alias_touch(conn, raw_text: str, hint_kind: Optional[str] = None) -> Optional[str]:
    raw_norm = normalize_raw(raw_text)
    if not raw_norm:
        return None
    if raw_norm in ("ru-unk", "ru unk", "unk"):
        # do not spam unknown
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO geo.geo_aliases(raw_text, raw_norm, hint_kind, status, hits)
                VALUES (%s, %s, %s, 'blocked', 1)
                ON CONFLICT(raw_norm) DO UPDATE
                  SET hits = geo.geo_aliases.hits + 1,
                      last_seen_at = now(),
                      raw_text = EXCLUDED.raw_text;
                """,
                (raw_text, raw_norm, hint_kind),
            )
        return raw_norm

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO geo.geo_aliases(raw_text, raw_norm, hint_kind, status, hits)
            VALUES (%s, %s, %s, 'new', 1)
            ON CONFLICT(raw_norm) DO UPDATE
              SET hits = geo.geo_aliases.hits + 1,
                  last_seen_at = now(),
                  raw_text = EXCLUDED.raw_text;
            """,
            (raw_text, raw_norm, hint_kind),
        )
    return raw_norm


def alias_resolve_point(conn, raw_text: str) -> Optional[Tuple[float, float]]:
    """
    Fast path: if alias already resolved -> return lat/lon from geo_keys.
    """
    raw_norm = normalize_raw(raw_text)
    if not raw_norm:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT k.lat, k.lon
              FROM geo.geo_aliases a
              JOIN geo.geo_keys k ON k.id = a.geo_key_id
             WHERE a.raw_norm = %s
               AND a.status = 'resolved'
               AND k.lat IS NOT NULL AND k.lon IS NOT NULL
             LIMIT 1;
            """,
            (raw_norm,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return (float(row[0]), float(row[1]))


def upsert_key_and_bind_alias(conn, raw_norm: str, raw_text: str, hint_kind: str, res: YandexGeocodeResult) -> None:
    """
    Creates/updates geo_key and binds alias -> geo_key_id.
    """
    provider = "yandex"
    # canonical key: prefer yandex uri if present, else stable derived from normalized text
    if res.provider_uri:
        key = f"yandex:{res.provider_uri}"
    else:
        key = f"raw:{raw_norm}"

    confidence_map = {
        "exact": 0.95,
        "number": 0.85,
        "near": 0.75,
        "range": 0.70,
        "street": 0.60,
        "other": 0.40,
        None: 0.50,
    }
    conf = confidence_map.get(res.precision, 0.50)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO geo.geo_keys(key, provider, provider_uri, kind, country_code, display_name, lat, lon, precision, meta, source, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'yandex', %s)
            ON CONFLICT(key) DO UPDATE
              SET provider_uri = EXCLUDED.provider_uri,
                  kind = EXCLUDED.kind,
                  country_code = EXCLUDED.country_code,
                  display_name = EXCLUDED.display_name,
                  lat = EXCLUDED.lat,
                  lon = EXCLUDED.lon,
                  precision = EXCLUDED.precision,
                  meta = EXCLUDED.meta,
                  confidence = EXCLUDED.confidence,
                  updated_at = now()
            RETURNING id;
            """,
            (
                key,
                provider,
                res.provider_uri,
                res.kind or hint_kind or "unknown",
                res.country_code or "RU",
                res.display_name,
                res.lat,
                res.lon,
                res.precision,
                json.dumps(res.raw or {}, ensure_ascii=False),
                conf,
            ),
        )
        key_id = cur.fetchone()[0]

        cur.execute(
            """
            UPDATE geo.geo_aliases
               SET status = 'resolved',
                   geo_key_id = %s,
                   last_attempt_at = now(),
                   last_error = NULL,
                   last_provider_uri = %s,
                   last_provider_precision = %s
             WHERE raw_norm = %s;
            """,
            (key_id, res.provider_uri, res.precision, raw_norm),
        )
