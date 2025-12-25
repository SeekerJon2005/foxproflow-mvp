# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\services\planner_tasks.py
"""
FoxProFlow — planner_tasks (stub, NDC-safe)

Назначение
---------
Опциональный модуль «планировщика», который ожидается воркером
(`src.worker.register_tasks`). В продвинутом варианте сюда можно вынести
логику подбора кандидатов для следующей загрузки грузовика. В текущем MVP
модуль выступает как «тонкая заглушка»: он не делает запросов к БД/сетям и
намеренно возвращает пустой список кандидатов, чтобы воркер автоматически
перешёл к FE-fallback (по витринам freights_enriched_mv / od_*_mv).

Гарантии
--------
- Безопасен: не меняет состояние, не трогает БД/Redis/OSRM.
- Отсутствие модуля не ломает воркер: в register_tasks есть _opt_import().
- Наличие модуля снимает «missing module» из логов и фиксирует контракт.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["planner_nextload_search", "planner_hourly_replan_all", "forecast_refresh"]
__version__ = "0.1.0"

log = logging.getLogger(__name__)


def _enabled() -> bool:
    """
    Переключатель заглушки (на будущее). Сейчас всегда True.
    Можно сделать зависимостью от ENV, если потребуется.
    """
    return True


def planner_nextload_search(
    truck_id: Optional[str] = None,
    *,
    limit: int = 5,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Возвращает кандидатов на следующую загрузку для конкретного ТС.

    ВЕРСИЯ STUB: всегда возвращает пустой список кандидатов.
    Воркер (task_planner_autoplan_audit) увидит это и переключится
    на FE-fallback (чтение кандидатов из витрин/рынка).

    Parameters
    ----------
    truck_id : Optional[str]
        UUID грузовика (строкой). Обязателен для реальной логики.
    limit : int
        Желаемое количество кандидатов (в заглушке не используется).

    Returns
    -------
    dict:
        {
          "ok": True|False,
          "candidates": [],          # всегда пусто (триггерим FE-fallback)
          "note": "planner stub: FE fallback will be used" | ошибка
        }
    """
    if not _enabled():
        return {"ok": False, "error": "planner stub disabled", "candidates": []}
    if not truck_id:
        return {"ok": False, "error": "truck_id required", "candidates": []}
    log.debug(
        "planner_tasks.stub planner_nextload_search called",
        extra={"truck_id": truck_id, "limit": limit, "kwargs": kwargs},
    )
    return {"ok": True, "candidates": [], "note": "planner stub: FE fallback will be used"}


def planner_hourly_replan_all(**kwargs: Any) -> Dict[str, Any]:
    """
    Заглушка «ежечасного» перепланирования.
    Реальной работы не выполняет; возвращает успешный no-op.
    """
    log.debug("planner_tasks.stub planner_hourly_replan_all called", extra={"kwargs": kwargs})
    return {"ok": True, "scheduled": False, "note": "planner stub (no-op)"}


def forecast_refresh(**kwargs: Any) -> Dict[str, Any]:
    """
    Заглушка «обновления прогноза» (используется task forecast.refresh).
    """
    log.debug("planner_tasks.stub forecast_refresh called", extra={"kwargs": kwargs})
    return {"ok": True, "note": "noop forecast (planner stub)"}


if __name__ == "__main__":
    # Простейший CLI для локальной проверки заглушки:
    #   python -m src.services.planner_tasks --truck-id <uuid>
    import argparse
    import json

    ap = argparse.ArgumentParser(description="FoxProFlow planner_tasks (stub)")
    ap.add_argument("--truck-id", help="Truck UUID", default=None)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--replan", action="store_true", help="Call planner_hourly_replan_all()")
    ap.add_argument("--forecast", action="store_true", help="Call forecast_refresh()")
    args = ap.parse_args()

    if args.replan:
        out = planner_hourly_replan_all()
    elif args.forecast:
        out = forecast_refresh()
    else:
        out = planner_nextload_search(args.truck_id, limit=args.limit)

    print(json.dumps(out, ensure_ascii=False))
