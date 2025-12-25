# -*- coding: utf-8 -*-
"""
Celery tasks package for FoxProFlow.

Агрегирует задачи из подмодулей src.worker.tasks.* и, при наличии,
аккуратно «мостит» верхнеуровневые модули (напр., src.worker.tasks_autoplan),
чтобы Celery autodiscover('src.worker') стабильно находил все задачи,
даже если часть модулей отсутствует в конкретной сборке.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Iterable, Optional

log = logging.getLogger(__name__)

__all__: list[str] = []
__all_set: set[str] = set()


def _export(g: dict, m, name: str) -> None:
    try:
        g[name] = getattr(m, name)
        if name not in __all_set:
            __all__.append(name)
            __all_set.add(name)
    except Exception:
        # пропускаем частные/нестандартные атрибуты
        return


def _try_import(mod: str, names: Optional[Iterable[str]] | bool = None) -> None:
    """
    Безопасный импорт модуля.

    - names=None/True  → импортировать все публичные символы;
    - names=[...]      → импортировать перечисленные имена.

    Ошибки импорта не валят пакет, только логируются на debug.
    """
    try:
        m = import_module(mod)
    except Exception as e:
        # тихий режим: модуль опционален
        log.debug("tasks: optional module not imported: %s (%s)", mod, e)
        return

    g = globals()

    if names is True or names is None:
        exported = getattr(m, "__all__", None)
        if not exported:
            exported = [n for n in dir(m) if not n.startswith("_")]
        for n in exported:
            _export(g, m, n)
    else:
        for n in names:
            _export(g, m, n)


# 1) Нативные подмодули пакета tasks/*
_try_import("src.worker.tasks.routing", True)             # routing.enrich.trips / confirmed
_try_import("src.worker.tasks.forecast_refresh", ["task_forecast_refresh"])

# GeoKey layer (Yandex Geocoder batch resolver)
# Важно: модуль опционален, но если присутствует — задачи должны быть видны Celery autodiscover.
_try_import("src.worker.tasks.geokey", True)              # geo.geokey.resolve_yandex_batch

# 2) Опциональные «мосты» к верхнеуровневым модулям (если присутствуют)
_try_import("src.worker.tasks_autoplan", True)            # planner.autoplan.*
_try_import("src.worker.tasks_parsers", True)             # parser.* / parsers.*
_try_import("src.worker.tasks_agents", True)              # agents.*

# Примечание:
# Никаких жёстких импортов .autoplan / .planner_tasks — этих файлов у нас нет
# внутри пакета tasks, и их отсутствие не должно ломать autodiscover.
