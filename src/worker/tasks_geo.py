# -*- coding: utf-8 -*-
# file: src/worker/tasks_geo.py
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests
from celery import shared_task

# Единый PG-хелпер по всему проекту (как в tasks_etl / tasks_agents)
from .tasks_agents import _connect_pg

log = logging.getLogger(__name__)

GEOCODER_DAY_BUDGET = int(os.getenv("GEOCODER_DAY_BUDGET", "950"))
GEOCODER_QPS = float(os.getenv("GEOCODER_QPS", "0.8"))
YANDEX_KEY = os.getenv("YANDEX_GEOCODER_API_KEY", "") or ""
PARSERS_QUEUE = os.getenv("PARSERS_QUEUE", "parsers")

# Внутренний трекер для QPS-ограничения (на процесс-воркер)
_last_geocode_call_ts: float = 0.0


def _budget_state(cur) -> Tuple[int, int]:
    """
    Инициализирует и возвращает (used, cap) по суточному бюджету геокодера.

    Таблица ops.geocoder_budget хранит:
      - day  (PRIMARY KEY)
      - used (кол-во уже "использованных" попыток геокодинга за день).
    """
    # На всякий случай создаём схему ops, если её ещё нет
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops;")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.geocoder_budget (
          day        date PRIMARY KEY,
          used       integer     NOT NULL DEFAULT 0,
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    cur.execute(
        """
        INSERT INTO ops.geocoder_budget(day, used)
        VALUES (CURRENT_DATE, 0)
        ON CONFLICT (day) DO NOTHING;
        """
    )
    cur.execute("SELECT used FROM ops.geocoder_budget WHERE day = CURRENT_DATE;")
    row = cur.fetchone()
    # В зависимости от драйвера row может быть dict или tuple
    if isinstance(row, dict):
        used = int(row.get("used", 0))
    else:
        used = int(row[0])
    return used, GEOCODER_DAY_BUDGET


def _budget_inc(cur, n: int) -> None:
    """Увеличиваем счётчик использованных попыток геокодинга на n."""
    cur.execute(
        """
        UPDATE ops.geocoder_budget
           SET used = used + %s,
               updated_at = now()
         WHERE day = CURRENT_DATE;
        """,
        (n,),
    )


def _throttle_qps() -> None:
    """
    Примитивный limiter по GEOCODER_QPS: не даём вылезти за qps на процесс.
    """
    global _last_geocode_call_ts
    if GEOCODER_QPS <= 0:
        return

    min_interval = 1.0 / GEOCODER_QPS
    now = time.monotonic()
    sleep_for = _last_geocode_call_ts + min_interval - now
    if sleep_for > 0:
        time.sleep(sleep_for)
    _last_geocode_call_ts = time.monotonic()


def _geocode_yandex(text: str) -> Optional[Tuple[float, float]]:
    """
    Геокод через Яндекс.

    Возвращает (lat, lon) или None, если не удалось.
    Соблюдает GEOCODER_QPS (через _throttle_qps).
    """
    if not YANDEX_KEY or not text:
        return None

    _throttle_qps()

    params = {
        "apikey": YANDEX_KEY,
        "geocode": text,
        "format": "json",
        "lang": "ru_RU",
        "results": 1,
    }
    try:
        r = requests.get(
            "https://geocode-maps.yandex.ru/1.x/",
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        js = r.json()
        pos = (
            js["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        )
        lon_str, lat_str = pos.split()
        lat = float(lat_str)
        lon = float(lon_str)
        return lat, lon
    except Exception as e:
        log.warning("geo.geocode: yandex failed for %r: %r", text, e)
        return None


@shared_task(name="geo.geocode.batch", queue=PARSERS_QUEUE)
def geo_geocode_batch(limit: int = 100) -> Dict[str, Any]:
    """
    Батчевый геокодинг фрахтов в market.freights_norm.

    Берём market.freights_norm со status = 'needs_geo' и пустыми координатами,
    проставляем origin_lat/origin_lon и dest_lat/dest_lon:

      - сначала пытаемся найти точку в public.city_map по origin_text/dest_text;
      - если не нашли — дергаем Яндекс-геокодер (при наличии YANDEX_KEY);
      - соблюдаем суточный бюджет GEOCODER_DAY_BUDGET (по количеству успешно
        геокодированных записей).

    Таблица-цель: market.freights_norm
      - origin_text, dest_text — сырые строки (города/места);
      - origin_lat, origin_lon, dest_lat, dest_lon — координаты;
      - статус 'needs_geo' → после успешной геокодировки ты дальше можешь
        перевести записи в другой статус (через отдельный ETL/агента).
    """
    conn = _connect_pg()
    conn.autocommit = False
    try:
        # psycopg3: cursor_factory больше не используется → обычный курсор
        cur = conn.cursor()

        used, cap = _budget_state(cur)
        can = max(0, cap - used)
        if can <= 0:
            conn.commit()
            return {
                "ok": True,
                "note": "daily geocode budget exhausted",
                "taken": 0,
                "geocoded": 0,
                "used": used,
                "cap": cap,
            }

        # учитываем и внешнее ограничение limit, и остаток бюджета
        limit_eff = min(limit, can)
        if limit_eff <= 0:
            conn.commit()
            return {
                "ok": True,
                "note": "nothing to geocode (limit/budget)",
                "taken": 0,
                "geocoded": 0,
                "used": used,
                "cap": cap,
            }

        cur.execute(
            """
            SELECT id, origin_text, dest_text
              FROM market.freights_norm
             WHERE status = 'needs_geo'
               AND (origin_lat IS NULL OR dest_lat IS NULL)
             ORDER BY created_at DESC
             LIMIT %s
             FOR UPDATE SKIP LOCKED
            """,
            (limit_eff,),
        )
        rows = cur.fetchall()
        taken = len(rows)
        if taken == 0:
            conn.commit()
            return {
                "ok": True,
                "note": "no rows with status=needs_geo",
                "taken": 0,
                "geocoded": 0,
                "used": used,
                "cap": cap,
            }

        geocoded = 0

        for row in rows:
            # row = (id, origin_text, dest_text)
            row_id, origin_text, dest_text = row

            o_raw = (origin_text or "").strip()
            d_raw = (dest_text or "").strip()

            o_lat = o_lon = d_lat = d_lon = None

            # --- origin ---
            if o_raw:
                cur.execute(
                    """
                    SELECT lat, lon
                      FROM public.city_map
                     WHERE upper(name) = upper(%s)
                     LIMIT 1
                    """,
                    (o_raw,),
                )
                hit = cur.fetchone()
                if hit:
                    o_lat, o_lon = hit  # tuple (lat, lon)
                else:
                    p = _geocode_yandex(o_raw)
                    if p:
                        o_lat, o_lon = p

            # --- dest ---
            if d_raw:
                cur.execute(
                    """
                    SELECT lat, lon
                      FROM public.city_map
                     WHERE upper(name) = upper(%s)
                     LIMIT 1
                    """,
                    (d_raw,),
                )
                hit = cur.fetchone()
                if hit:
                    d_lat, d_lon = hit
                else:
                    p = _geocode_yandex(d_raw)
                    if p:
                        d_lat, d_lon = p

            # Обновляем только если обе точки успешно определены
            if (
                o_lat is not None
                and o_lon is not None
                and d_lat is not None
                and d_lon is not None
            ):
                cur.execute(
                    """
                    UPDATE market.freights_norm
                       SET origin_lat = %s,
                           origin_lon = %s,
                           dest_lat   = %s,
                           dest_lon   = %s,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (o_lat, o_lon, d_lat, d_lon, row_id),
                )
                geocoded += 1
            else:
                log.debug(
                    "geo.geocode.batch: unable to geocode id=%s origin=%r dest=%r "
                    "(origin_lat=%r, origin_lon=%r, dest_lat=%r, dest_lon=%r)",
                    row_id,
                    o_raw,
                    d_raw,
                    o_lat,
                    o_lon,
                    d_lat,
                    d_lon,
                )

        if geocoded:
            _budget_inc(cur, geocoded)
        conn.commit()

        return {
            "ok": True,
            "taken": taken,
            "geocoded": geocoded,
            "used": used + geocoded,
            "cap": cap,
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log.exception("geo.geocode.batch failed: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


__all__ = [
    "geo_geocode_batch",
]
