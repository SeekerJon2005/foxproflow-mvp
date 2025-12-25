# -*- coding: utf-8 -*-
# file: src/worker/tasks/geokey.py
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from celery import shared_task

from src.core.geo.geokey import (
    pg_connect,
    normalize_raw,
    guess_kind,
    alias_touch,
    alias_resolve_point,
    quota_try_consume,
    YandexGeocoderClient,
    upsert_key_and_bind_alias,
)

log = logging.getLogger(__name__)


def _daily_limit() -> int:
    try:
        return int(os.getenv("YANDEX_GEOCODER_DAILY_LIMIT", "1000") or 1000)
    except Exception:
        return 1000


def _api_key() -> str:
    return (os.getenv("YANDEX_GEOCODER_API_KEY") or "").strip()


def _cooldown_min_default() -> int:
    try:
        return int(os.getenv("YANDEX_GEOCODER_COOLDOWN_MIN", "180") or 180)
    except Exception:
        return 180


@shared_task(name="geo.geokey.seed_aliases_from_trip_segments")
def geo_geokey_seed_aliases_from_trip_segments(
    limit: int = 5000,
    only_no_coords: bool = True,
    min_cnt: int = 1,
) -> Dict[str, Any]:
    """
    Наполняет geo.geo_aliases из public.trip_segments.origin_region/dest_region.
    Идемпотентно: UPSERT по raw_norm, hits суммируются.

    limit: max distinct raw_text to consider (after aggregation, ordered by cnt desc)
    only_no_coords: брать только сегменты, где road_km is null и нет src/dst coords
    min_cnt: не добавлять очень редкие ключи
    """
    limit = int(limit)
    min_cnt = int(min_cnt)
    only_no_coords = bool(only_no_coords)

    inserted = 0
    updated = 0
    blocked = 0
    skipped_empty = 0
    total_rows = 0

    conn = pg_connect()
    try:
        conn.autocommit = False

        sql = """
        WITH x AS (
          SELECT s.origin_region::text AS raw_text
            FROM public.trip_segments s
           WHERE s.origin_region IS NOT NULL
             AND (
               CASE WHEN %s::boolean
                 THEN (s.road_km IS NULL AND (s.src_lat IS NULL OR s.src_lon IS NULL OR s.dst_lat IS NULL OR s.dst_lon IS NULL))
                 ELSE TRUE
               END
             )

          UNION ALL

          SELECT s.dest_region::text AS raw_text
            FROM public.trip_segments s
           WHERE s.dest_region IS NOT NULL
             AND (
               CASE WHEN %s::boolean
                 THEN (s.road_km IS NULL AND (s.src_lat IS NULL OR s.src_lon IS NULL OR s.dst_lat IS NULL OR s.dst_lon IS NULL))
                 ELSE TRUE
               END
             )
        ),
        agg AS (
          SELECT raw_text, count(*)::bigint AS cnt
            FROM x
           GROUP BY raw_text
          HAVING count(*)::bigint >= %s
           ORDER BY cnt DESC
           LIMIT %s
        )
        SELECT raw_text, cnt FROM agg;
        """

        with conn.cursor() as cur:
            cur.execute(sql, (only_no_coords, only_no_coords, min_cnt, limit))
            rows = cur.fetchall()

        total_rows = len(rows)

        with conn.cursor() as cur:
            for raw_text, cnt in rows:
                raw_text_s = str(raw_text)
                cnt_i = int(cnt)

                raw_norm = normalize_raw(raw_text_s)
                if not raw_norm:
                    skipped_empty += 1
                    continue

                hint = guess_kind(raw_norm)

                # блокируем мусорные токены (не тратим квоту)
                if raw_norm in ("ru-unk", "ru unk", "unk"):
                    cur.execute(
                        """
                        INSERT INTO geo.geo_aliases(raw_text, raw_norm, hint_kind, status, hits, last_error)
                        VALUES (%s, %s, %s, 'blocked', %s, 'blocked: ru-unk')
                        ON CONFLICT(raw_norm) DO UPDATE
                          SET hits = geo.geo_aliases.hits + EXCLUDED.hits,
                              last_seen_at = now(),
                              raw_text = EXCLUDED.raw_text,
                              hint_kind = COALESCE(EXCLUDED.hint_kind, geo.geo_aliases.hint_kind),
                              status = 'blocked',
                              last_error = 'blocked: ru-unk';
                        """,
                        (raw_text_s, raw_norm, hint, cnt_i),
                    )
                    blocked += 1
                    continue

                # обычный alias
                cur.execute(
                    """
                    INSERT INTO geo.geo_aliases(raw_text, raw_norm, hint_kind, status, hits)
                    VALUES (%s, %s, %s, 'new', %s)
                    ON CONFLICT(raw_norm) DO UPDATE
                      SET hits = geo.geo_aliases.hits + EXCLUDED.hits,
                          last_seen_at = now(),
                          raw_text = EXCLUDED.raw_text,
                          hint_kind = COALESCE(EXCLUDED.hint_kind, geo.geo_aliases.hint_kind)
                    RETURNING (xmax = 0) AS inserted;
                    """,
                    (raw_text_s, raw_norm, hint, cnt_i),
                )
                r = cur.fetchone()
                if r and bool(r[0]):
                    inserted += 1
                else:
                    updated += 1

        conn.commit()

        return {
            "ok": True,
            "only_no_coords": only_no_coords,
            "limit": limit,
            "min_cnt": min_cnt,
            "rows": total_rows,
            "inserted": inserted,
            "updated": updated,
            "blocked": blocked,
            "skipped_empty": skipped_empty,
        }

    finally:
        try:
            conn.close()
        except Exception:
            pass


@shared_task(name="geo.geokey.resolve_yandex_batch")
def geo_geokey_resolve_yandex_batch(
    batch: int = 50,
    min_hits: int = 1,
    sleep_ms: int = 120,
    cooldown_min: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Resolve top pending aliases via Yandex Geocoder, respecting daily quota.

    batch: max aliases per run (keep small; schedule hourly -> ~<=1000/day)
    min_hits: only resolve aliases that appear often
    sleep_ms: delay between requests
    cooldown_min: do not re-try alias more often than this (minutes). default from env YANDEX_GEOCODER_COOLDOWN_MIN (180)
    force: ignore cooldown (manual run)
    """
    batch = int(batch)
    min_hits = int(min_hits)
    sleep_ms = int(sleep_ms)
    force = bool(force)

    if cooldown_min is None:
        cooldown_min = _cooldown_min_default()
    cooldown_min = int(cooldown_min)

    key = _api_key()
    if not key:
        return {"ok": False, "error": "YANDEX_GEOCODER_API_KEY is not set"}

    daily_limit = _daily_limit()
    client = YandexGeocoderClient(api_key=key, lang="ru_RU", timeout_sec=8.0)

    resolved = 0
    skipped_quota = 0
    skipped_already = 0
    blocked = 0
    failed = 0

    picked: List[Tuple[int, str, str]] = []

    conn = pg_connect()
    try:
        conn.autocommit = False

        # pick candidates (cooldown-aware)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, raw_text, raw_norm
                  FROM geo.geo_aliases
                 WHERE status IN ('new','retry')
                   AND hits >= %s
                   AND (
                     %s::boolean
                     OR last_attempt_at IS NULL
                     OR last_attempt_at < (now() - make_interval(mins => %s))
                   )
                 ORDER BY hits DESC, last_seen_at DESC
                 LIMIT %s;
                """,
                (min_hits, force, cooldown_min, batch),
            )
            picked = [(int(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]

        for _id, raw_text, raw_norm in picked:
            # mark attempt time early (so parallel runs don't thrash)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE geo.geo_aliases SET last_attempt_at=now() WHERE id=%s;",
                    (_id,),
                )
            conn.commit()

            # already resolved?
            if alias_resolve_point(conn, raw_text) is not None:
                skipped_already += 1
                # ensure status resolved (in case drift)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE geo.geo_aliases SET status='resolved', last_error=NULL WHERE raw_norm=%s;",
                        (raw_norm,),
                    )
                conn.commit()
                continue

            if raw_norm in ("ru-unk", "ru unk", "unk"):
                blocked += 1
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE geo.geo_aliases
                           SET status='blocked',
                               last_attempt_at=now(),
                               last_error='blocked: unknown token'
                         WHERE raw_norm=%s;
                        """,
                        (raw_norm,),
                    )
                conn.commit()
                continue

            # quota
            if not quota_try_consume(conn, "yandex", 1, daily_limit):
                conn.commit()
                skipped_quota += 1
                break

            hint = guess_kind(raw_norm)

            res = client.geocode_one(raw_text)
            if not res.ok:
                failed += 1
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE geo.geo_aliases
                           SET status='retry',
                               last_attempt_at=now(),
                               last_error=%s
                         WHERE raw_norm=%s;
                        """,
                        (res.error, raw_norm),
                    )
                conn.commit()
            else:
                with conn.cursor() as cur:
                    # ensure alias exists / touch hits (does not reset status)
                    alias_touch(conn, raw_text, hint_kind=hint)
                    upsert_key_and_bind_alias(conn, raw_norm, raw_text, hint, res)
                conn.commit()
                resolved += 1

            if sleep_ms > 0:
                time.sleep(max(0.0, sleep_ms / 1000.0))

        return {
            "ok": True,
            "picked": len(picked),
            "resolved": resolved,
            "failed": failed,
            "blocked": blocked,
            "skipped_already": skipped_already,
            "skipped_quota": skipped_quota,
            "daily_limit": daily_limit,
            "cooldown_min": cooldown_min,
            "force": force,
        }

    finally:
        try:
            conn.close()
        except Exception:
            pass


@shared_task(name="geo.geokey.quota_today")
def geo_geokey_quota_today(provider: str = "yandex") -> Dict[str, Any]:
    """
    Quick view: today quota usage from geo.api_usage_daily.
    """
    provider = (provider or "yandex").strip() or "yandex"
    conn = pg_connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT day, provider, used, daily_limit
                  FROM geo.api_usage_daily
                 WHERE day = current_date
                   AND provider = %s;
                """,
                (provider,),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": True, "provider": provider, "day": None, "used": 0, "daily_limit": _daily_limit()}
            return {"ok": True, "provider": str(row[1]), "day": str(row[0]), "used": int(row[2]), "daily_limit": int(row[3])}
    finally:
        try:
            conn.close()
        except Exception:
            pass
