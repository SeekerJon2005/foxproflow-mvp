# -*- coding: utf-8 -*-
"""
FlowLang — слой декларативных планов для FoxProFlow.

Текущая цель (v0):
  • держать планы поведения (автоплан и др.) в .flow-файлах;
  • уметь их безопасно читать из кода;
  • постепенно подвязывать поведение системы к этим планам.

Слои API:

1) Базовый, generic (работает уже сейчас):
   - PlanConfig         — простая структура: имя плана + params + путь;
   - get_plans_dir()    — где лежат .flow-файлы (FLOWLANG_PLANS_DIR, по умолчанию flowplans);
   - load_plan(name)    — загрузить один план (например, "rolling_msk");
   - list_plans()       — загрузить все *.flow и вернуть dict name -> PlanConfig.

   Пример:

       from src.flowlang import load_plan

       cfg = load_plan("rolling_msk")
       print(cfg.name, cfg.params["rpm_min"])

2) Автоплан-уровень (опциональный, может быть доработан отдельно):
   - AutoplanPlanConfig     — специализированная модель плана автоплана;
   - parse_plan(path)       — парсер .flow -> AutoplanPlanConfig;
   - run_autoplan_from_flow(path) — запуск автоплана по плану через HTTP API.

   Пример использования (когда будут реализованы model/parser/runtime_autoplan):

       from src.flowlang import parse_plan, run_autoplan_from_flow

       plan_cfg = parse_plan("flowplans/autoplan_msk.flow")
       result = run_autoplan_from_flow("flowplans/autoplan_msk.flow")
"""

from __future__ import annotations

from typing import Any, Dict

# --- Базовый generic-слой: планы как PlanConfig (работает уже сейчас) ---

from .plans import PlanConfig, get_plans_dir, load_plan, list_plans

__all__ = [
    "PlanConfig",
    "get_plans_dir",
    "load_plan",
    "list_plans",
]

# --- Опциональный высокоуровневый API для автоплана ---
# Импортируем мягко, чтобы отсутствие model/parser/runtime_autoplan
# не ломало импорт всего пакета src.flowlang.

AutoplanPlanConfig: Any
parse_plan: Any
run_autoplan_from_flow: Any

try:
    from .model import AutoplanPlanConfig  # type: ignore
    from .parser import parse_plan         # type: ignore
    from .runtime_autoplan import run_autoplan_from_flow  # type: ignore
except Exception:
    # Модули верхнего уровня пока могут быть не реализованы.
    # Оставляем заглушки None; они не попадают в __all__, чтобы
    # не ломать `from src.flowlang import *`.
    AutoplanPlanConfig = None  # type: ignore[assignment]
    parse_plan = None          # type: ignore[assignment]
    run_autoplan_from_flow = None  # type: ignore[assignment]
else:
    __all__ += [
        "AutoplanPlanConfig",
        "parse_plan",
        "run_autoplan_from_flow",
    ]

# Опционально: версия языка на уровне пакета.
__version__ = "0.0.1"
