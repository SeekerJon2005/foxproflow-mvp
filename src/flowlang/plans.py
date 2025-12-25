# -*- coding: utf-8 -*-
"""
FlowLang v0: загрузка и парсинг файлов планов *.flow.

Сейчас поддерживается упрощённый синтаксис:

    plan rolling_msk {
      # комментарий
      region_include       = ["RU-MOW", "RU-MOS"]
      freights_days_back   = 3
      routing_enabled      = true
      rpm_min              = 90
    }

Значения парсятся через ast.literal_eval с лёгкой нормализацией:
- true/false -> True/False
- числа -> int/float
- строки и списки — как в Python-литералах.

Никакой связи с автопланом пока нет — это чисто reader.
"""

from __future__ import annotations

import ast
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PlanConfig:
    name: str
    params: Dict[str, Any]
    path: str


# ------------------------ path helpers ------------------------


def _get_project_root() -> pathlib.Path:
    """
    __file__ = /app/src/flowlang/plans.py
    root     = /app
    """
    return pathlib.Path(__file__).resolve().parents[2]


def get_plans_dir() -> pathlib.Path:
    """
    Возвращает абсолютный путь к каталогу с планами.

    Базируется на:
      FLOWLANG_PLANS_DIR (по умолчанию 'flowplans')
      + корень проекта (/app в контейнере, корень репозитория на хосте).
    """
    root = _get_project_root()
    dir_name = os.getenv("FLOWLANG_PLANS_DIR", "flowplans")
    return (root / dir_name).resolve()


# ------------------------ parsing helpers ------------------------


def _parse_value(raw: str) -> Any:
    """
    Парсим правую часть "key = value".

    Пытаемся:
      - нормализовать true/false -> True/False;
      - прогнать через ast.literal_eval;
      - если не вышло — вернуть строку (без кавычек, если они есть).
    """
    s = raw.strip()
    if not s:
        return None

    # аккуратно нормализуем логические константы
    norm = s.replace("true", "True").replace("false", "False")

    try:
        return ast.literal_eval(norm)
    except Exception:
        # если это было просто "строка в кавычках" — убираем кавычки
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        return s


def load_plan(name: str) -> PlanConfig:
    """
    Загружает одиночный план по имени (имя файла без расширения).

    Пример:
      load_plan("rolling_msk") -> PlanConfig(name="rolling_msk", params={...})
    """
    plans_dir = get_plans_dir()
    path = plans_dir / f"{name}.flow"
    if not path.is_file():
        raise FileNotFoundError(f"FlowLang plan '{name}' not found at: {path}")

    text = path.read_text(encoding="utf-8")

    in_block = False
    plan_name: Optional[str] = None
    params: Dict[str, Any] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if not in_block:
            # ищем заголовок: plan <name> {
            if line.startswith("plan ") and "{" in line:
                head, _, _ = line.partition("{")
                _, _, nm = head.partition("plan")
                plan_name = nm.strip()
                in_block = True
            continue

        # внутри блока
        if line.startswith("}"):
            break
        if line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue

        params[key] = _parse_value(val)

    if plan_name is None:
        raise ValueError(f"FlowLang plan file '{path}' does not contain 'plan <name> {{' header")

    return PlanConfig(name=plan_name, params=params, path=str(path))


def list_plans() -> Dict[str, PlanConfig]:
    """
    Загружает все *.flow в каталоге планов.

    Возвращает dict: { plan_name: PlanConfig(...) }.
    Ошибочные файлы пропускаются.
    """
    plans_dir = get_plans_dir()
    result: Dict[str, PlanConfig] = {}

    if not plans_dir.is_dir():
        return result

    for f in sorted(plans_dir.glob("*.flow")):
        try:
            cfg = load_plan(f.stem)
        except Exception:
            continue
        result[cfg.name] = cfg

    return result
