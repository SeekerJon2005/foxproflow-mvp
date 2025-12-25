# -*- coding: utf-8 -*-
"""
beat_anchor — последний и решающий слой, который гарантирует наличие
ключа 'routing-enrich-missing-2m' в расписании Celery Beat.

Особенности:
- Не импортирует celery_app (исключает циклы); работает через current_app.
- Срабатывает трижды: при импорте модуля, on_after_configure и beat_init.
- На beat_init выполняет принудительное обновление (force=True) — "последнее слово".
- Полностью управляется ENV (см. ниже).

ENV (необязательные):
  ROUTING_ENRICH_TASK         — имя задачи добивки (по умолчанию routing.enrich.trips)
  ROUTING_QUEUE               — очередь, по умолчанию AUTOPLAN_QUEUE или 'autoplan'
  ROUTING_ENRICH_LIMIT        — лимит отбора сегментов, по умолчанию 1500
  ROUTING_ENRICH_ONLY_MISSING — 1/0 или true/false; по умолчанию True
  ROUTING_ENRICH_EVERY_MIN    — период в минутах (int), по умолчанию 2 → '*/N'
  ROUTING_ENRICH_CRON_MINUTE  — cron-минуты (строка), приоритетнее ROUTING_ENRICH_EVERY_MIN
  ROUTING_ENRICH_CRON_HOUR    — cron-часы (строка), по умолчанию '*'
  BEAT_ANCHOR_FORCE           — 1/true для принудительной переустановки записи даже если она есть
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict

try:
    from celery import current_app as _cur
    from celery.schedules import crontab
except Exception:  # на крайний случай, чтобы не падать при статанализе
    _cur = None  # type: ignore

    def crontab(*args, **kwargs):  # type: ignore
        return None


log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=os.getenv("CELERY_LOG_LEVEL", "INFO"))

ENTRY_NAME = "routing-enrich-missing-2m"  # имя совместимо с логами/дашбордами


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v.strip() != "" else default


def _minute_spec() -> str:
    n = _env_int("ROUTING_ENRICH_EVERY_MIN", 2)
    if n <= 0:
        n = 2
    return f"*/{n}"


def _desired_entry() -> Dict[str, Any]:
    """Собрать запись расписания из ENV, с безопасными дефолтами."""
    task_name = _env_str("ROUTING_ENRICH_TASK", "routing.enrich.trips")
    queue = _env_str("ROUTING_QUEUE", _env_str("AUTOPLAN_QUEUE", "autoplan"))
    limit = _env_int("ROUTING_ENRICH_LIMIT", 1500)
    only_missing = _env_bool("ROUTING_ENRICH_ONLY_MISSING", True)

    minute = _env_str("ROUTING_ENRICH_CRON_MINUTE", _minute_spec())
    hour = _env_str("ROUTING_ENRICH_CRON_HOUR", "*")

    return {
        "task": task_name,
        "schedule": crontab(minute=minute, hour=hour),
        "kwargs": {"limit": limit, "only_missing": only_missing},
        "options": {"queue": queue},
    }


def _ensure(sender=None, force: bool | None = None, **kwargs) -> None:
    """
    Идемпотентно добавляет/обновляет запись ENTRY_NAME в app.conf.beat_schedule.

    - Если записи нет или она неполная/отличается — обновит.
    - Если force=True (или BEAT_ANCHOR_FORCE=1/true), обновит без сравнения.
    """
    try:
        app = sender or getattr(_cur, "_get_current_object", lambda: _cur)()
        if app is None:
            return

        desired = _desired_entry()
        bs = dict(getattr(app.conf, "beat_schedule", {}) or {})
        current = bs.get(ENTRY_NAME)
        need_update = False

        if not isinstance(current, dict):
            need_update = True
        else:
            # минимальная проверка "важных" полей
            if (
                current.get("task") != desired["task"]
                or current.get("kwargs") != desired["kwargs"]
                or (current.get("options") or {}).get("queue") != desired["options"]["queue"]
            ):
                need_update = True

        if force is None:
            force = _env_bool("BEAT_ANCHOR_FORCE", False)

        if need_update or force:
            bs[ENTRY_NAME] = desired
            app.conf.beat_schedule = bs
            try:
                log.info(
                    "beat_anchor: ensured '%s' -> task=%s, kwargs=%s, queue=%s",
                    ENTRY_NAME,
                    desired["task"],
                    desired["kwargs"],
                    desired["options"]["queue"],
                )
            except Exception:
                pass

    except Exception as e:
        try:
            log.warning("beat_anchor: ensure failed: %r", e)
        except Exception:
            pass


# Подключаемся к сигналам Celery (выполняется при импорте модуля)
try:
    from celery.signals import on_after_configure, beat_init

    # после конфигурации приложения
    on_after_configure.connect(_ensure, weak=False)

    # при старте планировщика — всегда "последнее слово"
    def _ensure_on_beat_init(sender=None, **kw):
        _ensure(sender=sender, force=True)

    beat_init.connect(_ensure_on_beat_init, weak=False)
except Exception:
    pass


# И один запуск на импорт модуля (нефорсированный)
try:
    _ensure()
except Exception:
    pass


__all__ = ["_ensure", "ENTRY_NAME"]
