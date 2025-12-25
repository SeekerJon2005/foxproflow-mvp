from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app (может отсутствовать в некоторых окружениях)
# ---------------------------------------------------------------------------
try:
    from src.worker.celery_app import app  # type: ignore[import]
except Exception:  # pragma: no cover - в тестах может не быть celery_app
    app = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Доступ к Engine
# ---------------------------------------------------------------------------

_FALLBACK_ENGINE: Engine | None = None


def _fallback_get_engine() -> Engine:
    """
    Минимальный fallback-Engine через DATABASE_URL / FF_DATABASE_URL.
    Используется, если src.db.session.get_engine недоступен.
    """
    global _FALLBACK_ENGINE

    if _FALLBACK_ENGINE is not None:
        return _FALLBACK_ENGINE

    db_url = os.getenv("FF_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "tasks_analytics: neither FF_DATABASE_URL nor DATABASE_URL is set; "
            "cannot construct fallback Engine"
        )

    _FALLBACK_ENGINE = create_engine(db_url)
    logger.warning(
        "tasks_analytics: src.db.session.get_engine not found, using fallback from DATABASE_URL",
        extra={"db_url": db_url},
    )
    return _FALLBACK_ENGINE


try:  # pragma: no cover - в тестах модуль может отсутствовать
    from src.db.session import get_engine as _get_engine  # type: ignore[import]
except Exception:  # noqa: BLE001
    _get_engine = None  # type: ignore[assignment]


def get_engine() -> Engine:
    """
    Унифицированная точка получения Engine.

    1. Пытаемся использовать src.db.session.get_engine(), если он есть.
    2. Иначе — собираем Engine по DATABASE_URL (fallback).
    """
    if _get_engine is not None:
        try:
            return _get_engine()  # type: ignore[call-arg]
        except TypeError:
            logger.warning(
                "tasks_analytics.get_engine: src.db.session.get_engine() "
                "raised TypeError, falling back to DATABASE_URL"
            )
    return _fallback_get_engine()


# ---------------------------------------------------------------------------
# REFRESH analytics.freights_ati_price_distance_mv
# ---------------------------------------------------------------------------


def refresh_freights_ati_price_distance_mv(
    concurrently: bool = True,
) -> None:
    """
    REFRESH MATERIALIZED VIEW analytics.freights_ati_price_distance_mv.

    Параметр `concurrently=True` сначала пытается сделать
    `REFRESH MATERIALIZED VIEW CONCURRENTLY`, а если Postgres не поддерживает
    CONCURRENTLY или матвью ещё не существует — делает обычный REFRESH.
    """
    engine = get_engine()

    sql_concurrent = text(
        "REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.freights_ati_price_distance_mv"
    )
    sql_plain = text(
        "REFRESH MATERIALIZED VIEW analytics.freights_ati_price_distance_mv"
    )

    if concurrently:
        try:
            logger.info(
                "refresh_freights_ati_price_distance_mv.start",
                extra={"concurrently": True},
            )
            with engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.execute(sql_concurrent)
            logger.info(
                "refresh_freights_ati_price_distance_mv.ok",
                extra={"concurrently": True},
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "refresh_freights_ati_price_distance_mv.concurrent_failed, fallback to plain",
                extra={"error": str(exc)},
            )

    logger.info(
        "refresh_freights_ati_price_distance_mv.start",
        extra={"concurrently": False},
    )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sql_plain)
    logger.info(
        "refresh_freights_ati_price_distance_mv.ok",
        extra={"concurrently": False},
    )


def _get_freights_ati_price_distance_mv_stats() -> Dict[str, Any]:
    """
    Возвращает простую статистику по витрине:
    - rows_total: общее количество строк.
    """
    engine = get_engine()
    sql = text(
        """
        SELECT count(*)::bigint AS rows_total
        FROM analytics.freights_ati_price_distance_mv
        """
    )

    try:
        with engine.connect() as conn:
            row = conn.execute(sql).one()
        return {
            "rows_total": int(row.rows_total),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "get_freights_ati_price_distance_mv_stats.failed",
            extra={"error": str(exc)},
        )
        return {
            "rows_total": None,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Celery-task: analytics.freights_ati.refresh_price_distance_mv
# ---------------------------------------------------------------------------

if app is not None:

    @app.task(  # type: ignore[misc]
        name="analytics.freights_ati.refresh_price_distance_mv",
        bind=False,
        acks_late=True,
        ignore_result=False,
    )
    def task_analytics_refresh_price_distance_mv(
        concurrently: bool = True,
    ) -> Dict[str, Any]:
        """
        Celery-таска для обновления витрины analytics.freights_ati_price_distance_mv.

        Возвращает словарь:
        - ok, error
        - before/after: статистика до и после REFRESH.
        """
        before = _get_freights_ati_price_distance_mv_stats()

        try:
            refresh_freights_ati_price_distance_mv(concurrently=concurrently)
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_analytics_refresh_price_distance_mv.failed",
                extra={"concurrently": concurrently},
            )
            ok, error = False, str(exc)

        after = _get_freights_ati_price_distance_mv_stats()
        payload: Dict[str, Any] = {
            "ok": ok,
            "error": error,
            "concurrently": concurrently,
            "before": before,
            "after": after,
        }
        logger.info(
            "task_analytics_refresh_price_distance_mv.done",
            extra={
                "ok": ok,
                "rows_before": before.get("rows_total"),
                "rows_after": after.get("rows_total"),
            },
        )
        return payload

else:

    def task_analytics_refresh_price_distance_mv(
        concurrently: bool = True,
    ) -> Dict[str, Any]:
        """
        Фоллбек-версии задачи (без Celery).
        """
        before = _get_freights_ati_price_distance_mv_stats()

        try:
            refresh_freights_ati_price_distance_mv(concurrently=concurrently)
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_analytics_refresh_price_distance_mv.failed (fallback)",
                extra={"concurrently": concurrently},
            )
            ok, error = False, str(exc)

        after = _get_freights_ati_price_distance_mv_stats()
        return {
            "ok": ok,
            "error": error,
            "concurrently": concurrently,
            "before": before,
            "after": after,
        }


# ---------------------------------------------------------------------------
# DynRPM: пересчёт analytics.dynrpm_config по данным витрины
# ---------------------------------------------------------------------------


def _recalc_dynrpm_config_from_mv(
    limit_buckets: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Пересчитывает таблицу analytics.dynrpm_config на основе
    analytics.freights_ati_price_distance_mv.
    """
    engine = get_engine()

    filter_clause = ""
    params: Dict[str, Any] = {}
    if limit_buckets:
        filter_clause = "WHERE c.bucket_code = ANY(:bucket_codes)"
        params["bucket_codes"] = limit_buckets

    sql = text(
        f"""
        WITH bucket_stats AS (
            SELECT
                c.bucket_code,
                COUNT(*) FILTER (
                    WHERE m.avg_rub_per_km IS NOT NULL
                      AND m.n_valid > 0
                ) AS n_corridors,
                percentile_cont(0.25) WITHIN GROUP (ORDER BY m.avg_rub_per_km)
                    FILTER (WHERE m.avg_rub_per_km IS NOT NULL AND m.n_valid > 0) AS rpm_p25,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY m.avg_rub_per_km)
                    FILTER (WHERE m.avg_rub_per_km IS NOT NULL AND m.n_valid > 0) AS rpm_p50,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY m.avg_rub_per_km)
                    FILTER (WHERE m.avg_rub_per_km IS NOT NULL AND m.n_valid > 0) AS rpm_p75
            FROM analytics.dynrpm_config c
            LEFT JOIN analytics.freights_ati_price_distance_mv m
              ON (
                    (c.distance_km_min IS NULL OR m.avg_distance_km >= c.distance_km_min)
                AND (c.distance_km_max IS NULL OR m.avg_distance_km <  c.distance_km_max)
              )
            {filter_clause}
            GROUP BY c.bucket_code
        )
        UPDATE analytics.dynrpm_config AS c
        SET
            rpm_p25   = b.rpm_p25,
            rpm_p50   = b.rpm_p50,
            rpm_p75   = b.rpm_p75,
            rpm_floor = COALESCE(b.rpm_p25, c.rpm_floor),
            updated_at = NOW()
        FROM bucket_stats AS b
        WHERE c.bucket_code = b.bucket_code
        RETURNING
            c.bucket_code,
            c.bucket_name,
            c.distance_km_min,
            c.distance_km_max,
            c.rpm_p25,
            c.rpm_p50,
            c.rpm_p75,
            c.rpm_floor,
            b.n_corridors;
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(sql, params).mappings().all()

    updated = [dict(row) for row in rows]

    logger.info(
        "dynrpm_config.recalc_from_mv.done",
        extra={
            "limit_buckets": limit_buckets,
            "updated_buckets": [r["bucket_code"] for r in updated],
        },
    )

    return {
        "ok": True,
        "updated_buckets": updated,
        "limit_buckets": limit_buckets,
        "source": "analytics.freights_ati_price_distance_mv",
    }


if app is not None:

    @app.task(  # type: ignore[misc]
        name="analytics.freights_ati.dynrpm.refresh_config",
        bind=False,
        acks_late=True,
        ignore_result=False,
    )
    def task_analytics_dynrpm_refresh_config(
        limit_buckets: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Celery-таска: пересчитывает analytics.dynrpm_config
        по данным analytics.freights_ati_price_distance_mv.
        """
        try:
            result = _recalc_dynrpm_config_from_mv(limit_buckets=limit_buckets)
            logger.info(
                "task_analytics_dynrpm_refresh_config.done",
                extra={
                    "limit_buckets": limit_buckets,
                    "updated_buckets": len(result.get("updated_buckets", [])),
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_analytics_dynrpm_refresh_config.failed",
                extra={"limit_buckets": limit_buckets},
            )
            return {
                "ok": False,
                "error": str(exc),
                "limit_buckets": limit_buckets,
            }

else:

    def task_analytics_dynrpm_refresh_config(
        limit_buckets: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Фоллбек-реализация: позволяет пересчитать dynrpm_config
        без запуска Celery-воркера.
        """
        try:
            return _recalc_dynrpm_config_from_mv(limit_buckets=limit_buckets)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_analytics_dynrpm_refresh_config.failed (fallback)",
                extra={"limit_buckets": limit_buckets},
            )
            return {
                "ok": False,
                "error": str(exc),
                "limit_buckets": limit_buckets,
            }


# ---------------------------------------------------------------------------
# Backwards-совместимый alias для старых скриптов
# ---------------------------------------------------------------------------

if app is not None and hasattr(task_analytics_refresh_price_distance_mv, "apply_async"):
    analytics_freights_ati_refresh_price_distance_mv = (  # type: ignore[assignment]
        task_analytics_refresh_price_distance_mv
    )
else:

    def analytics_freights_ati_refresh_price_distance_mv(
        concurrently: bool = True,
    ) -> Dict[str, Any]:
        """
        Фоллбек-обёртка для совместимости:
        выполняет синхронный REFRESH и возвращает тот же формат,
        что и task_analytics_refresh_price_distance_mv.
        """
        before = _get_freights_ati_price_distance_mv_stats()

        try:
            refresh_freights_ati_price_distance_mv(concurrently=concurrently)
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "analytics_freights_ati_refresh_price_distance_mv.failed (compat)",
                extra={"concurrently": concurrently},
            )
            ok, error = False, str(exc)

        after = _get_freights_ati_price_distance_mv_stats()
        return {
            "ok": ok,
            "error": error,
            "concurrently": concurrently,
            "before": before,
            "after": after,
        }


# ---------------------------------------------------------------------------
# Logistics: On-Time Delivery KPI MV refresh
# ---------------------------------------------------------------------------


def refresh_logistics_ontime_kpi_daily_mv() -> None:
    """
    REFRESH MATERIALIZED VIEW analytics.logistics_ontime_delivery_kpi_daily.
    """
    engine = get_engine()
    sql = text(
        "REFRESH MATERIALIZED VIEW analytics.logistics_ontime_delivery_kpi_daily"
    )

    logger.info("refresh_logistics_ontime_kpi_daily_mv.start")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sql)
    logger.info("refresh_logistics_ontime_kpi_daily_mv.ok")


def _get_logistics_ontime_kpi_stats(days: Optional[int] = None) -> Dict[str, Any]:
    """
    Возвращает агрегированную статистику по витрине
    analytics.logistics_ontime_delivery_kpi_daily.

    Если days задан, учитываем только последние N дней:
      day >= current_date - (days - 1).
    """
    engine = get_engine()

    base_sql = """
        SELECT
            coalesce(sum(total_delivered), 0)   AS total_delivered,
            coalesce(sum(on_time_delivered), 0) AS on_time_delivered,
            coalesce(sum(late_delivered), 0)    AS late_delivered,
            round(
                100.0 * coalesce(sum(on_time_delivered), 0)
                / greatest(coalesce(sum(total_delivered), 0), 1),
                2
            ) AS on_time_pct
        FROM analytics.logistics_ontime_delivery_kpi_daily
    """

    if days is not None:
        # ВАЖНО: без bind-параметра (:days::int), чтобы не ловить syntax error.
        days_int = int(days)
        base_sql += f"""
        WHERE day >= current_date - ({days_int}::int - 1)
        """

    sql = text(base_sql)

    try:
        with engine.connect() as conn:
            row = conn.execute(sql).one()
        total = int(row.total_delivered)
        on_time = int(row.on_time_delivered)
        late = int(row.late_delivered)
        pct = float(row.on_time_pct)
        return {
            "total_delivered": total,
            "on_time_delivered": on_time,
            "late_delivered": late,
            "on_time_pct": pct,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "get_logistics_ontime_kpi_stats.failed",
            extra={"error": str(exc), "days": days},
        )
        return {
            "total_delivered": None,
            "on_time_delivered": None,
            "late_delivered": None,
            "on_time_pct": None,
            "error": str(exc),
            "days": days,
        }


if app is not None:

    @app.task(  # type: ignore[misc]
        name="logistics.refresh_ontime_kpi_daily",
        bind=False,
        acks_late=True,
        ignore_result=False,
    )
    def task_logistics_refresh_ontime_kpi_daily(
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Celery-таска для обновления витрины логистического KPI
        analytics.logistics_ontime_delivery_kpi_daily.

        Возвращает словарь:
        - ok / error
        - days
        - before / after (агрегаты до и после REFRESH).
        """
        before = _get_logistics_ontime_kpi_stats(days=days)

        try:
            refresh_logistics_ontime_kpi_daily_mv()
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_logistics_refresh_ontime_kpi_daily.failed",
                extra={"days": days},
            )
            ok, error = False, str(exc)

        after = _get_logistics_ontime_kpi_stats(days=days)

        payload: Dict[str, Any] = {
            "ok": ok,
            "error": error,
            "days": days,
            "before": before,
            "after": after,
        }

        logger.info(
            "task_logistics_refresh_ontime_kpi_daily.done",
            extra={
                "ok": ok,
                "days": days,
                "total_before": before.get("total_delivered"),
                "total_after": after.get("total_delivered"),
            },
        )

        return payload

else:

    def task_logistics_refresh_ontime_kpi_daily(
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Фоллбек-версия задачи для логистического KPI (без Celery).
        """
        before = _get_logistics_ontime_kpi_stats(days=days)

        try:
            refresh_logistics_ontime_kpi_daily_mv()
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task_logistics_refresh_ontime_kpi_daily.failed (fallback)",
                extra={"days": days},
            )
            ok, error = False, str(exc)

        after = _get_logistics_ontime_kpi_stats(days=days)

        return {
            "ok": ok,
            "error": error,
            "days": days,
            "before": before,
            "after": after,
        }
