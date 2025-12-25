# -*- coding: utf-8 -*-
# file: src/worker/tasks_devfactory_analytics.py
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict

from src.worker.celery_app import app, _connect_pg

log = logging.getLogger(__name__)


@app.task(name="analytics.devfactory.daily")
def analytics_devfactory_daily(dt: str | None = None) -> Dict[str, Any]:
    """
    Суточный KPI-срез DevFactory.

    Логика:
    - Если dt не передан — берём сегодня (CURRENT_DATE на стороне Python).
    - Вызываем dev.refresh_devfactory_kpi_daily(dt), которая агрегирует
      данные из dev.devfactory_task_stats_v и обновляет dev.devfactory_kpi_daily.
    - После обновления читаем строки за dt из dev.devfactory_kpi_daily и
      возвращаем tasks_total / tasks_with_changes для наблюдаемости.
    """
    if dt:
        try:
            target_date = date.fromisoformat(dt)
        except ValueError:
            log.warning(
                "analytics.devfactory.daily: invalid dt=%r, falling back to today()",
                dt,
            )
            target_date = date.today()
    else:
        target_date = date.today()

    conn = _connect_pg()
    try:
        tasks_total: int | None = None
        tasks_with_changes: int | None = None

        with conn.cursor() as cur:
            # Пересчитываем KPI на указанную дату
            cur.execute("SELECT dev.refresh_devfactory_kpi_daily(%s);", (target_date,))

            # Читаем актуальные значения из dev.devfactory_kpi_daily
            cur.execute(
                """
                SELECT tasks_total, tasks_with_changes
                FROM dev.devfactory_kpi_daily
                WHERE dt = %s;
                """,
                (target_date,),
            )
            row = cur.fetchone()
            if row:
                # row — обычный tuple (psycopg2/psycopg default)
                tasks_total = int(row[0])
                tasks_with_changes = int(row[1])

        conn.commit()

        log.info(
            "analytics.devfactory.daily: KPI refreshed for dt=%s (tasks_total=%s, tasks_with_changes=%s)",
            target_date,
            tasks_total,
            tasks_with_changes,
        )

        return {
            "ok": True,
            "dt": str(target_date),
            "tasks_total": tasks_total,
            "tasks_with_changes": tasks_with_changes,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("analytics.devfactory.daily failed for dt=%s: %s", target_date, e)
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "dt": str(target_date),
            "error": str(e),
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
