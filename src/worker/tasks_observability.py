# -*- coding: utf-8 -*-
"""
FoxProFlow — агент наблюдаемости (Observability v0).

Назначение:
    Считать сводную статистику по событиям из ops.event_log за последние N дней:
      - сколько событий по каждому source/event_type/severity;
      - последние ошибки (error/critical);
      - общее количество событий.

Режимы использования:

1) Вручную из контейнера worker как обычная Python-функция:

    python - << 'PY'
    from src.worker.tasks_observability import agents_observability_scan
    import json

    res = agents_observability_scan(days_back=3)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    PY

2) Через Celery как агент:

    docker compose exec worker celery -A src.worker.celery_app call ^
        agents.observability.scan --args='[3]'

    # В этом случае будет вызвана Celery-задача
    # agents_observability_scan_task (name="agents.observability.scan").

Функция НЕ вносит никаких изменений в БД — только SELECT из ops.event_log.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TypedDict

from celery import shared_task

from src.core.events import _pg_conn  # внутренний helper, уже используется в событийном слое

log = logging.getLogger(__name__)


class EventStats(TypedDict, total=False):
    ok: bool
    days_back: int
    rows_total: int | None
    by_source: List[Dict[str, Any]]
    errors_recent: List[Dict[str, Any]]


__all__ = [
    "agents_observability_scan",
    "agents_observability_scan_task",
]


_MIN_DAYS_BACK = 1
_MAX_DAYS_BACK = 90
_DEFAULT_DAYS_BACK = 3


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _normalize_days_back(days_back: int | float | str | None) -> int:
    """
    Нормализует days_back в безопасный диапазон [1; 90].

    - некорректные значения → _DEFAULT_DAYS_BACK (3);
    - значения < 1 → 1;
    - значения > 90 → 90.
    """
    try:
        if days_back is None:
            return _DEFAULT_DAYS_BACK
        value = int(days_back)
    except Exception:
        return _DEFAULT_DAYS_BACK

    if value < _MIN_DAYS_BACK:
        return _MIN_DAYS_BACK
    if value > _MAX_DAYS_BACK:
        return _MAX_DAYS_BACK
    return value


def agents_observability_scan(days_back: int = _DEFAULT_DAYS_BACK) -> EventStats:
    """
    Базовый агент наблюдаемости.

    Читает ops.event_log за последние days_back дней и возвращает словарь:

        {
          "ok": true/false,
          "days_back": 3,
          "rows_total": 123,
          "by_source": [
            {"source": "autoplan", "event_type": "error", "severity": "error", "n": 5},
            ...
          ],
          "errors_recent": [
            {
              "id": 42,
              "ts": "...",
              "source": "...",
              "event_type": "...",
              "severity": "...",
              "correlation_id": "...",
              "payload": {...}
            },
            ...
          ]
        }

    Никаких изменений в данных НЕ делает — только SELECT.
    """
    norm_days_back = _normalize_days_back(days_back)

    stats: EventStats = {
        "ok": False,
        "days_back": norm_days_back,
        "rows_total": None,
        "by_source": [],      # список агрегатов
        "errors_recent": [],  # последние ошибки
    }

    interval_str = f"{norm_days_back} days"

    try:
        with _pg_conn() as conn, conn.cursor() as cur:
            # 1) Общее количество событий за окно
            cur.execute(
                """
                SELECT count(*)::bigint AS rows_total
                  FROM ops.event_log
                 WHERE ts >= now() - %s::interval
                """,
                (interval_str,),
            )
            row = cur.fetchone()
            stats["rows_total"] = _as_int(row[0] if row else None)

            # 2) Агрегаты по source / event_type / severity
            cur.execute(
                """
                SELECT
                    source,
                    event_type,
                    severity,
                    count(*)::bigint AS n
                  FROM ops.event_log
                 WHERE ts >= now() - %s::interval
                 GROUP BY 1,2,3
                 ORDER BY n DESC, source, event_type, severity
                """,
                (interval_str,),
            )
            by_source: List[Dict[str, Any]] = []
            for src, event_type, severity, n in cur.fetchall():
                by_source.append(
                    {
                        "source": src,
                        "event_type": event_type,
                        "severity": severity,
                        "n": _as_int(n),
                    }
                )
            stats["by_source"] = by_source

            # 3) Последние ошибки за окно (error/critical), ограничим топ-50
            cur.execute(
                """
                SELECT
                    id,
                    ts,
                    source,
                    event_type,
                    severity,
                    correlation_id,
                    payload
                  FROM ops.event_log
                 WHERE ts >= now() - %s::interval
                   AND severity IN ('error', 'critical')
                 ORDER BY ts DESC
                 LIMIT 50
                """,
                (interval_str,),
            )
            errors_recent: List[Dict[str, Any]] = []
            for (
                ev_id,
                ts,
                source,
                event_type,
                severity,
                correlation_id,
                payload,
            ) in cur.fetchall():
                errors_recent.append(
                    {
                        "id": _as_int(ev_id),
                        "ts": ts,
                        "source": source,
                        "event_type": event_type,
                        "severity": severity,
                        "correlation_id": correlation_id,
                        "payload": payload,
                    }
                )
            stats["errors_recent"] = errors_recent

        stats["ok"] = True
        log.info(
            "agents.observability.scan.ok",
            extra={
                "days_back": stats["days_back"],
                "rows_total": stats["rows_total"],
                "sources": [row["source"] for row in stats["by_source"]],
            },
        )
    except Exception:
        log.exception(
            "agents.observability.scan.failed",
            extra={"days_back": norm_days_back},
        )
        stats["ok"] = False

    return stats


@shared_task(name="agents.observability.scan", ignore_result=False)
def agents_observability_scan_task(
    days_back: int = _DEFAULT_DAYS_BACK,
) -> EventStats:
    """
    Celery-обёртка над agents_observability_scan.

    Пример вызова из контейнера worker:

        docker compose exec worker celery -A src.worker.celery_app call ^
            agents.observability.scan --args='[3]'

    Возвращает тот же словарь, что и agents_observability_scan.
    """
    return agents_observability_scan(days_back=days_back)
