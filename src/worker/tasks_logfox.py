# -*- coding: utf-8 -*-
"""
FoxProFlow — LogFox (ежедневный отчёт по событиям).

Агент поверх agents_observability_scan:
  - делает скан ops.event_log за days_back дней;
  - считает общее количество событий;
  - считает количество источников и ошибок (error/critical);
  - берёт топ-источники;
  - пишет summary в лог и возвращает его как dict.

Никаких изменений в БД не делает — только чтение + лог.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TypedDict

from celery import shared_task

from src.worker.tasks_observability import agents_observability_scan

log = logging.getLogger(__name__)


class LogfoxSummary(TypedDict, total=False):
    ok: bool
    days_back: int
    rows_total: int
    sources: int
    errors: int
    top_sources: List[Dict[str, Any]]
    error: str
    obs: Dict[str, Any]


__all__ = [
    "agents_logfox_daily_report",
]


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


@shared_task(name="agents.logfox.daily_report", ignore_result=False)
def agents_logfox_daily_report(days_back: int = 1) -> LogfoxSummary:
    """
    Ежедневный отчёт по событиям (LogFox).

    Пример вызова:

        docker compose exec worker celery -A src.worker.celery_app call ^
            agents.logfox.daily_report --args='[1]'

    Возвращает summary вида:

        {
          "ok": true,
          "days_back": 1,
          "rows_total": 400,
          "sources": 7,
          "errors": 3,
          "top_sources": [...],
        }
    """
    obs = agents_observability_scan(days_back=days_back)

    if not obs.get("ok"):
        summary: LogfoxSummary = {
            "ok": False,
            "error": "observability_scan_failed",
            "days_back": obs.get("days_back", days_back),
            "obs": obs,  # сырой результат сканера для разборов
        }
        log.warning("agents.logfox.daily_report.failed", extra={"summary": summary})
        return summary

    rows_total = _safe_int(obs.get("rows_total"), 0)
    by_source: List[Dict[str, Any]] = list(obs.get("by_source") or [])
    errors_recent: List[Dict[str, Any]] = list(obs.get("errors_recent") or [])

    n_sources = len(by_source)
    n_errors = len(errors_recent)

    # by_source уже отсортирован по n DESC в agents_observability_scan
    top_sources = by_source[:5]

    summary: LogfoxSummary = {
        "ok": True,
        "days_back": obs.get("days_back", days_back),
        "rows_total": rows_total,
        "sources": n_sources,
        "errors": n_errors,
        "top_sources": top_sources,
    }

    log.info("agents.logfox.daily_report", extra={"summary": summary})
    return summary
