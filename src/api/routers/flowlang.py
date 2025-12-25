# -*- coding: utf-8 -*-
from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from src.flowlang.plans import list_plans, load_plan  # наш NDC-интерфейс

# Опционально подтягиваем адаптер автоплана (FlowLang → AutoplanSettings)
try:
    from src.flowlang.autoplan_adapter import (  # type: ignore
        get_autoplan_settings,
        AutoplanSettings,
    )
except Exception:  # pragma: no cover
    get_autoplan_settings = None  # type: ignore[assignment]
    AutoplanSettings = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/flowlang", tags=["flowlang"])
log = logging.getLogger(__name__)


@router.get("/plans")
def get_plans() -> List[Dict[str, Any]]:
    """
    Возвращает список доступных FlowLang-планов.

    Поддерживает оба варианта реализации list_plans():
      • list[str]      — имена или пути к .flow;
      • list[PlanLike] — объекты с атрибутами .name / .path.

    Структура ответа:
      [
        {"name": "rolling_msk", "path": "/app/flowplans/rolling_msk.flow" | null},
        ...
      ]
    """
    items: List[Dict[str, Any]] = []

    for p in list_plans():
        # Вариант 1: list_plans() вернул строки
        if isinstance(p, str):
            raw = p

            # Если выглядит как путь к .flow-файлу
            if raw.endswith(".flow"):
                path = raw
                name = Path(raw).stem
            else:
                # Просто имя плана без расширения/пути
                name = raw
                path = None
        else:
            # Вариант 2: объект-план с атрибутами
            name = getattr(p, "name", None) or getattr(p, "plan_name", None) or str(p)
            path = getattr(p, "path", None) or getattr(p, "filepath", None)

        items.append({"name": name, "path": path})

    return items


@router.get("/plans/current")
def get_current_plan() -> Dict[str, Any]:
    """
    Возвращает активный FlowLang-план автоплана.

    Активный план определяется переменной:
      AUTOPLAN_FLOW_PLAN (по умолчанию 'rolling_msk').

    Возвращает:
      {
        "name": "rolling_msk",       # имя плана из .flow
        "env_name": "rolling_msk",   # значение AUTOPLAN_FLOW_PLAN
        "params": {...},             # raw-параметры плана
        "path": "...",               # путь к .flow
        "autoplan_settings": {...}   # (опционально) слитые AutoplanSettings
      }
    """
    env_name = os.getenv("AUTOPLAN_FLOW_PLAN", "rolling_msk")

    try:
        plan = load_plan(env_name)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"current_plan_not_found: {env_name!r}",
        )
    except Exception as e:
        log.warning("flowlang: load_plan(%r) failed in /plans/current: %r", env_name, e)
        raise HTTPException(status_code=500, detail="plan_load_failed")

    payload: Dict[str, Any] = {
        "name": plan.name,
        "env_name": env_name,
        "params": plan.params,
        "path": plan.path,
    }

    # Если адаптер настроек доступен — прикладываем AutoplanSettings
    if get_autoplan_settings is not None and AutoplanSettings is not None:
        try:
            settings = get_autoplan_settings(env_name)
            payload["autoplan_settings"] = dataclasses.asdict(settings)
        except Exception as e:  # pragma: no cover
            log.warning(
                "flowlang: get_autoplan_settings(%r) failed in /plans/current: %r",
                env_name,
                e,
            )

    return payload


@router.get("/plans/{name}")
def get_plan(name: str) -> Dict[str, Any]:
    """
    Возвращает параметры конкретного FlowLang-плана.

    Структура:
      {
        "name": "rolling_msk",
        "params": {...},   # словарь параметров плана
        "path": "/app/flowplans/rolling_msk.flow"
      }
    """
    try:
        plan = load_plan(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"plan_not_found: {name!r}")
    except Exception as e:
        log.warning("flowlang: load_plan(%r) failed: %r", name, e)
        raise HTTPException(status_code=500, detail="plan_load_failed")

    return {"name": plan.name, "params": plan.params, "path": plan.path}


@router.get("/plans/{name}/settings")
def get_plan_settings(name: str) -> Dict[str, Any]:
    """
    Возвращает AutoplanSettings для указанного FlowLang-плана.

    Здесь объединяются:
      • значения из .flow-файла (rolling_msk.flow и т.п.);
      • ENV-переменные (fallback);
      • жёсткие дефолты автоплана.

    Если самого .flow-плана нет — 404.
    Если адаптер недоступен — 503.
    """
    if get_autoplan_settings is None or AutoplanSettings is None:
        raise HTTPException(
            status_code=503,
            detail="autoplan_adapter_not_available",
        )

    # 1) Проверяем, что FlowLang-план реально существует (иначе — 404)
    try:
        load_plan(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"plan_not_found: {name!r}")
    except Exception as e:
        log.warning(
            "flowlang: load_plan(%r) failed in /plans/{name}/settings: %r",
            name,
            e,
        )
        raise HTTPException(status_code=500, detail="plan_load_failed")

    # 2) Забираем слитые настройки для данного плана
    try:
        settings = get_autoplan_settings(name)
    except Exception as e:
        log.warning(
            "flowlang: get_autoplan_settings(%r) failed in /plans/{name}/settings: %r",
            name,
            e,
        )
        raise HTTPException(status_code=500, detail="autoplan_settings_error")

    return {
        "name": name,
        "settings": dataclasses.asdict(settings),
    }
