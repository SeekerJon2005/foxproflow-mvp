# -*- coding: utf-8 -*-
"""
FoxProFlow: parser tasks shim (flow-level).

Этот модуль существует как тонкий адаптер:
- чтобы Celery и старые импорты по-прежнему видели задачи
  parsers.watchdog и parser.ati.freights.pull;
- вся реальная логика парсера и ETL живёт в src.worker.tasks_etl.

Если нужно менять поведение парсера ATI или watchdog — править
НУЖНО в src/worker/tasks_etl.py, а не здесь.
"""

from __future__ import annotations

import logging
import os

# Логгер оставляем, чтобы при необходимости можно было
# добавить дополнительные сообщения именно от этого слоя.
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.getenv("CELERY_LOG_LEVEL", "INFO"))

# Реальные реализации задач живут в tasks_etl.
# Здесь мы их просто реэкспортируем, чтобы:
#   - не дублировать код;
#   - сохранить совместимость с существующими импортами / автодискавером Celery.
from .tasks_etl import (  # noqa: E402
    task_parsers_watchdog,
    parser_ati_freights_pull,
)

__all__ = [
    "task_parsers_watchdog",
    "parser_ati_freights_pull",
]
