# -*- coding: utf-8 -*-
"""
FlowLang runtime для автоплана FoxProFlow.

Задача v0:
  1) Прочитать .flow-файл.
  2) Спарсить его в AutoplanPlanConfig.
  3) Запустить автоплан через HTTP API /api/autoplan/run?mode=chain.

На v0 мы фактически управляем только:
  - limit — сколько фрахтов обрабатываем за запуск;
  - dry   — выполнять ли запись (False) или только "сухой" прогон (True).

Остальные поля плана зарезервированы под будущие версии FlowLang
(управление окнами, порогами, расписаниями и т.п.).
"""

from __future__ import annotations

from typing import Any, Dict
import os

import requests

from .parser import parse_plan
from .model import AutoplanPlanConfig

# Базовый URL API автоплана.
# Можно переопределить через ENV (например, http://api:8080 внутри Docker).
API_BASE = os.getenv("FLOWLANG_API_BASE", "http://127.0.0.1:8080")


def run_autoplan_from_flow(path: str) -> Dict[str, Any]:
    """
    Прочитать .flow-файл, спарсить план и запустить автоплан через HTTP API.

    Возвращает:
      - при успехе: JSON-ответ /api/autoplan/run + добавляет поле "plan";
      - при ошибке HTTP/сети: словарь с ok=False и подробностями.
    """
    plan: AutoplanPlanConfig = parse_plan(path)

    # На v0 используем только limit + dry.
    body: Dict[str, Any] = {
        "limit": plan.limit,
        "dry": bool(plan.dry),
    }

    url = f"{API_BASE.rstrip('/')}/api/autoplan/run"

    try:
        resp = requests.post(
            url,
            params={"mode": "chain"},
            headers={"Accept": "application/json"},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            data = {"raw": data}
        # нормализуем флаг ok и имя плана
        data.setdefault("ok", True)
        data.setdefault("plan", plan.name)
        return data
    except Exception as exc:
        # Не роняем процесс, а возвращаем структурированную ошибку
        return {
            "ok": False,
            "error": str(exc),
            "api_url": url,
            "plan": plan.name,
            "body": body,
        }
