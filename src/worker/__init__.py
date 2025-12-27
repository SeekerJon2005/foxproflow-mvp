# -*- coding: utf-8 -*-
"""
FoxProFlow worker package.

Задача этого __init__.py — быть стабильной точкой входа для Celery CLI.

Поддерживаемые варианты:
  -A src.worker
  -A src.worker:celery_app
  -A src.worker:app
  -A src.worker.celery_app
  -A src.worker.celery_app:celery_app

Почему так:
- Celery иногда интерпретирует `src.worker.celery_app` как `src.worker:celery_app`,
  поэтому `src.worker` должен уметь отдавать атрибут `celery_app`.
- Также Celery часто ищет атрибут `app` по умолчанию.
"""

from __future__ import annotations

from typing import Any

__all__ = ["celery_app", "app"]


def __getattr__(name: str) -> Any:
    """
    Ленивый экспорт Celery app.

    Важно: не импортируем celery_app на уровне модуля, чтобы:
    - не ломать импорт пакета в контекстах, где worker/beat не запускаются;
    - избежать побочных эффектов при простом `import src.worker`.

    Когда Celery CLI запросит app — импорт произойдёт здесь.
    """
    if name in ("celery_app", "app"):
        from .celery_app import celery_app as _celery_app

        return _celery_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + ["celery_app", "app"])
