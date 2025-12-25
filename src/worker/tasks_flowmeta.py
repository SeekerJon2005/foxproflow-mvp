# -*- coding: utf-8 -*-
# file: src/worker/tasks_flowmeta.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from celery import shared_task

from src.flowlang.meta_loader import _load_world_auto
from src.flowlang.meta_sync import sync_from_meta

logger = logging.getLogger(__name__)

JsonDict = Dict[str, Any]


@shared_task(name="agents.flowmeta.summary", queue="agents")
def agents_flowmeta_summary() -> JsonDict:
    """
    Агенты FlowMeta: вернуть срез мира (domains/dsls/effects/agent_classes/plan_classes/policies).

    Используется для:
      - быстрой диагностики,
      - проверки, что мир загружается из БД без ошибок,
      - источника правды для других агентов (FlowSec, DevFactory и т.п.) в режиме advisory.

    Возвращает JSON-объект вида:
      {
        "world_name": "foxproflow",
        "summary": {
          "world": "foxproflow",
          "domains": [...],
          "dsls": [...],
          "effects": [...],
          "agent_classes": [...],
          "plan_classes": [...],
          "policies": [...]
        }
      }
    """
    world = _load_world_auto(world_name="foxproflow")
    summary = world.summary()
    payload: JsonDict = {
        "world_name": world.world_name,
        "summary": summary,
    }
    logger.info("[FlowMeta] world summary: %s", summary)
    return payload


@shared_task(name="agents.flowmeta.sync_from_meta", queue="agents")
def agents_flowmeta_sync_from_meta(
    meta_path: str = "config/flowmeta/flowmeta.meta",
) -> JsonDict:
    """
    Агенты FlowMeta: синхронизировать мир из .meta-файла в таблицы flowmeta.*.

    NDC-гарантии:
      - только INSERT ... ON CONFLICT DO UPDATE,
      - никаких DROP/DELETE/ALTER,
      - существующие записи только дополняются/обновляются.

    Параметры:
      meta_path: путь к .meta-файлу относительно /app (по умолчанию config/flowmeta/flowmeta.meta).

    Возвращает JSON-объект вида:
      {
        "meta_path": "config/flowmeta/flowmeta.meta",
        "synced": {
          "domains": 7,
          "dsls": 7,
          "effects": 9,
          "agent_classes": 6,
          "plan_classes": 5
        }
      }
    """
    meta_path_obj = Path(meta_path)
    result = sync_from_meta(meta_path_obj)
    logger.info(
        "[FlowMeta] synced world from %s: %s",
        meta_path_obj,
        result,
    )
    return {
        "meta_path": str(meta_path_obj),
        "synced": result,
    }
