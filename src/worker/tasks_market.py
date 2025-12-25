# -*- coding: utf-8 -*-
# file: src/worker/tasks_market.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from celery import shared_task

# Эти функции мы уже используем в ETL/автоплане для event_log
from src.core import emit_start, emit_done, emit_error
from .tasks_agents import _connect_pg  # type: ignore[import]

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=os.getenv("CELERY_LOG_LEVEL", "INFO"))


# === helpers ================================================================


def _safe_int(
    value: Any,
    default: int,
    min_val: int = 1,
    max_val: int = 365,
) -> int:
    """
    Безопасное преобразование к int с ограничением диапазона.

    Нужен, чтобы days_back / horizon_days некрасиво не улетели в 0 или 10000.
    """
    try:
        v = int(value)
    except Exception:
        return default
    if v < min_val:
        return min_val
    if v > max_val:
        return max_val
    return v


# === demand_forecast (Market Brain L0) ======================================


def build_demand_forecast_from_ati(days_back: int = 14) -> Dict[str, Any]:
    """
    Market Brain L0: агрегировать фрахты (ATI → public.freights)
    в market.demand_forecast.

    Текущая реализация (L0.0, без догадок о схеме выручки):

    Источники:
      - public.freights — результат ETL из freights_ati_raw; гарантированно
        используются только поля:
          • loading_date  (дата погрузки),
          • loading_region,
          • unloading_region.

    Логика версии L0.0:
      1) Удаляем старые строки, сгенерированные нашим пайплайном
         (generated_by = 'MarketBrain.freights_v1') за последние N дней.
      2) Считаем по окну N дней по public.freights агрегаты:
         - day           = loading_date::date
         - origin_region = loading_region
         - dest_region   = unloading_region
         - n             = количество фрахтов
         - rpm_p25 / rpm_p50 / rpm_p75 = NULL (пока не знаем надёжный источник выручки)
      3) Вставляем результат в market.demand_forecast с meta, где явно указано,
         что RPM не считался (rpm_mode = 'none').

    Как только в схеме появится согласованный столбец выручки
    (или перейдём на analytics.freights_ati_price_distance_mv), сюда добавим
    расчёт RPM-квантилей без изменения внешнего контракта.
    """
    days_back_eff = _safe_int(days_back, default=14, min_val=1, max_val=365)

    result: Dict[str, Any] = {
        "ok": True,
        "source": "public.freights",
        "days_back": days_back_eff,
        "rows_deleted": 0,
        "rows_inserted": 0,
    }

    conn = None
    try:
        conn = _connect_pg()
        with conn.cursor() as cur:
            # 1) Чистим старый прогноз, сгенерированный этим же пайплайном
            cur.execute(
                """
                DELETE FROM market.demand_forecast
                WHERE generated_by = %s
                  AND day >= current_date - (%s::text || ' days')::interval;
                """,
                ("MarketBrain.freights_v1", days_back_eff),
            )
            result["rows_deleted"] = int(cur.rowcount or 0)

            # 2) Считаем агрегаты (пока только n; RPM-колонки — NULL)
            cur.execute(
                """
                INSERT INTO market.demand_forecast (
                    day,
                    origin_region,
                    dest_region,
                    n,
                    rpm_p25,
                    rpm_p50,
                    rpm_p75,
                    generated_by,
                    meta
                )
                SELECT
                    day,
                    origin_region,
                    dest_region,
                    n,
                    rpm_p25,
                    rpm_p50,
                    rpm_p75,
                    'MarketBrain.freights_v1' AS generated_by,
                    jsonb_build_object(
                        'days_back', %s::int,
                        'source',   'public.freights',
                        'rpm_mode', 'none'
                    ) AS meta
                FROM (
                    SELECT
                        f.loading_date::date AS day,
                        f.loading_region     AS origin_region,
                        f.unloading_region   AS dest_region,
                        count(*)::bigint     AS n,
                        -- RPM пока не считаем: нет надёжного столбца выручки
                        NULL::numeric(10,2)  AS rpm_p25,
                        NULL::numeric(10,2)  AS rpm_p50,
                        NULL::numeric(10,2)  AS rpm_p75
                    FROM public.freights AS f
                    WHERE f.loading_date >= current_date
                                          - (%s::text || ' days')::interval
                    GROUP BY
                        f.loading_date::date,
                        f.loading_region,
                        f.unloading_region
                ) AS agg;
                """,
                (days_back_eff, days_back_eff),
            )
            result["rows_inserted"] = int(cur.rowcount or 0)

        conn.commit()
        log.info("market.build_demand_forecast_from_ati.ok", extra=result)
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "market.build_demand_forecast_from_ati.failed",
            extra={"days_back": days_back_eff},
        )
        result["ok"] = False
        result["error"] = str(exc)
        # наружу пробрасываем исключение, чтобы Celery отметил таску как failed
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@shared_task(
    name="analytics.market.refresh_demand_forecast",
    ignore_result=False,
    acks_late=True,
)
def task_market_refresh_demand_forecast(days_back: int = 14) -> Dict[str, Any]:
    """
    Celery-таска для обновления market.demand_forecast.

    Запускает build_demand_forecast_from_ati и логирует ход через event_log.
    """
    days_back_eff = _safe_int(days_back, default=14, min_val=1, max_val=365)
    payload: Dict[str, Any] = {"days_back": days_back_eff}
    corr_id = f"market.refresh_demand_forecast:{days_back_eff}"

    emit_start(
        "analytics.market.refresh_demand_forecast",
        correlation_id=corr_id,
        payload=payload,
    )

    try:
        res = build_demand_forecast_from_ati(days_back=days_back_eff)
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "analytics.market.refresh_demand_forecast.error",
            extra={"days_back": days_back_eff},
        )
        emit_error(
            "analytics.market.refresh_demand_forecast",
            correlation_id=corr_id,
            payload={**payload, "error": str(exc)},
        )
        # Celery увидит exception и пометит таску как failed
        raise
    else:
        merged = {**payload, **res}
        emit_done(
            "analytics.market.refresh_demand_forecast",
            correlation_id=corr_id,
            payload=merged,
        )
        return merged


# === virtual_freights (пока stub) ===========================================


@shared_task(
    name="analytics.market.generate_virtual_freights",
    ignore_result=False,
    acks_late=True,
)
def task_market_generate_virtual_freights(horizon_days: int = 5) -> Dict[str, Any]:
    """
    Celery-таска для генерации виртуальных фрахтов.

    В будущем:
      - читает market.demand_forecast на горизонт 3–5 дней,
      - генерирует записи в market.virtual_freights,
      - возвращает статистику по созданным заявкам.

    Сейчас реализована как безопасный no-op (ничего не пишет в БД),
    но оставляет след в event_log и логах.
    """
    horizon_eff = _safe_int(horizon_days, default=5, min_val=1, max_val=30)
    payload: Dict[str, Any] = {"horizon_days": horizon_eff}
    corr_id = f"market.generate_virtual_freights:{horizon_eff}"

    emit_start(
        "analytics.market.generate_virtual_freights",
        correlation_id=corr_id,
        payload=payload,
    )

    res: Dict[str, Any] = {
        "ok": True,
        "status": "noop",
        "virtual_freights_created": 0,
        "note": "virtual freights generation is not implemented yet",
    }

    merged = {**payload, **res}
    emit_done(
        "analytics.market.generate_virtual_freights",
        correlation_id=corr_id,
        payload=merged,
    )
    log.info(
        "analytics.market.generate_virtual_freights.noop",
        extra=merged,
    )
    return merged
