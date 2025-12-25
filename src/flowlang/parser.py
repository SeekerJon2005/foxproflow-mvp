# -*- coding: utf-8 -*-
"""
Простой парсер FlowLang v0 для планов автоплана.

Синтаксис (v0):

    plan rolling_msk {
      region                = "RU-MOW"
      limit                 = 50
      window_minutes        = 240
      confirm_horizon_hours = 96
      freeze_hours_before   = 2

      rpm_floor_min         = 130
      p_arrive_min          = 0.5

      dry                   = false
      chain_every_min       = 15
    }

Поддерживаемые типы value:
  - "строка" / 'строка'
  - целое число (50)
  - число с плавающей (0.5)
  - true / false
"""

from __future__ import annotations

from typing import Any, Dict

from .model import AutoplanPlanConfig


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return None

    # строка в кавычках
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]

    # bool
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False

    # int / float
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        # fallback — оставляем как есть
        return raw


def _safe_int(value: Any, default: int) -> int:
    """
    Безопасно приводит значение к int, иначе возвращает default.
    """
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_plan(path: str) -> AutoplanPlanConfig:
    """
    Парсит .flow-файл в AutoplanPlanConfig.

    Ограничения v0:
      - ожидается один блок `plan <name> { ... }` в файле;
      - ключи внутри блока маппятся на поля AutoplanPlanConfig.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]

    if not lines:
        raise ValueError(f"Flow plan file '{path}' is empty")

    name: str | None = None
    body: Dict[str, Any] = {}
    in_block = False

    for ln in lines:
        # пустые/комментарии пропускаем
        if not ln or ln.startswith("#") or ln.startswith("//"):
            continue

        # заголовок плана
        if ln.startswith("plan "):
            parts = ln.split()
            if len(parts) < 2:
                raise ValueError(f"Invalid plan header in '{path}': {ln}")
            name = parts[1]

            # если строка сразу содержит '{' — входим в блок
            if "{" in ln:
                in_block = True
            else:
                in_block = False
            continue

        # отдельные строки с '{' / '}'
        if "{" in ln:
            in_block = True
            continue
        if "}" in ln:
            in_block = False
            continue

        if in_block:
            if "=" not in ln:
                # допускаем пустые/служебные строки внутри блока
                continue
            key, raw_val = ln.split("=", 1)
            key = key.strip()
            val = _parse_value(raw_val)
            body[key] = val

    if not name:
        raise ValueError(f"No 'plan <name> {{ ... }}' block found in '{path}'")

    # Маппинг ключей на поля AutoplanPlanConfig (с безопасным приведением типов)
    cfg = AutoplanPlanConfig(
        name=name,
        region=body.get("region"),
        limit=_safe_int(body.get("limit"), 50),
        window_minutes=_safe_int(body.get("window_minutes"), 240),
        confirm_horizon_hours=_safe_int(body.get("confirm_horizon_hours"), 96),
        freeze_hours_before=_safe_int(body.get("freeze_hours_before"), 2),
        rpm_floor_min=body.get("rpm_floor_min"),
        p_arrive_min=body.get("p_arrive_min"),
        dry=bool(body.get("dry", False)),
        chain_every_min=body.get("chain_every_min"),
    )

    return cfg
