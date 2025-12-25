# -*- coding: utf-8 -*-
"""
Пакет core — общие низкоуровневые helpers FoxProFlow.

Сюда складываем то, что нужно во всех подсистемах:
- событийная система (events);
- дальше появятся security/flowsec-адаптеры, общие утилиты и т.п.

Рекомендуемый способ использования:
    from src.core import emit_event, emit_start, emit_done, emit_error
или
    from src.core import events
"""

from __future__ import annotations

from typing import Any, Optional

_events_import_error: Optional[BaseException] = None

try:
    # Основной путь: events доступен (обычно внутри контейнеров api/worker)
    from . import events
    from .events import (
        emit_event,
        link_events,
        emit_start,
        emit_done,
        emit_error,
    )

except ModuleNotFoundError as e:
    # В хост-среде (не в контейнере) часто нет драйвера Postgres (psycopg/psycopg2).
    # Важно: core должен оставаться импортируемым для локальных инструментов/тестов/линтера.
    if getattr(e, "name", None) in ("psycopg", "psycopg2"):
        events = None  # type: ignore[assignment]
        _events_import_error = e

        def _raise_events_unavailable() -> None:
            missing = getattr(e, "name", None) or "psycopg"
            raise RuntimeError(
                "src.core.events недоступен: отсутствует Postgres-драйвер "
                f"({missing}). Запускай код внутри Docker-контейнера api/worker "
                "или установи зависимость в эту Python-среду."
            ) from e

        def emit_event(*args: Any, **kwargs: Any) -> Any:
            _raise_events_unavailable()

        def link_events(*args: Any, **kwargs: Any) -> Any:
            _raise_events_unavailable()

        def emit_start(*args: Any, **kwargs: Any) -> Any:
            _raise_events_unavailable()

        def emit_done(*args: Any, **kwargs: Any) -> Any:
            _raise_events_unavailable()

        def emit_error(*args: Any, **kwargs: Any) -> Any:
            _raise_events_unavailable()

    else:
        # Любые другие ошибки импорта events не маскируем — это реальная поломка.
        raise


def events_available() -> bool:
    """True, если подмодуль events успешно импортирован и доступен."""
    return events is not None  # type: ignore[truthy-bool]


def events_unavailable_reason() -> Optional[str]:
    """Причина недоступности events (если есть), строкой для диагностики."""
    return str(_events_import_error) if _events_import_error else None


__all__ = [
    # подмодуль
    "events",
    # функции событий
    "emit_event",
    "link_events",
    "emit_start",
    "emit_done",
    "emit_error",
    # диагностика доступности
    "events_available",
    "events_unavailable_reason",
]
