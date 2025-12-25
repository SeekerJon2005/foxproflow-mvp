# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\common\env.py
"""
FoxProFlow — common.env (NDC-safe)

Утилиты для безопасного чтения переменных окружения.
Цели:
- Избежать дублирования однотипного кода вроде: os.getenv(...) or default, int(...), float(...), json.loads(...).
- Стабильно парсить bool/int/float/json/list со значениями по умолчанию.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Sequence


def getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Возвращает строковое значение переменной окружения или default, если не задана.
    В отличие от os.getenv(name, default) не приводит None к 'None'.
    """
    v = os.getenv(name)
    return v if v is not None else default


def env_bool(name: str, default: bool = False) -> bool:
    """
    Булев парсер:
      true-подобные: '1','true','yes','on','y' (без учёта регистра)
      false-подобные: всё остальное или отсутствие переменной → default
    """
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name: str, default: int = 0) -> int:
    """
    Парсинг целого числа с запасной веткой default при ошибке.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_float(name: str, default: float = 0.0) -> float:
    """
    Парсинг числа с плавающей точкой с запасной веткой default при ошибке.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def env_json(name: str, default: Any = None) -> Any:
    """
    Парсинг JSON из строки окружения. При ошибке или отсутствии — default.
    Пример:
      ENV: MY_CFG='{"a":1,"b":[2,3]}'
      cfg = env_json("MY_CFG", {})  # -> {'a':1,'b':[2,3]}
    """
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def env_list(name: str, sep: str = ",", default: Optional[Sequence[str]] = None) -> list[str]:
    """
    Разбиение строки по разделителю в список с триммингом элементов.
    Пустые элементы отбрасываются.
    Пример:
      ENV: REGIONS="RU-MOW, RU-SPE ,  RU-NIZ ,"
      env_list("REGIONS") -> ["RU-MOW","RU-SPE","RU-NIZ"]
    """
    raw = os.getenv(name)
    if not raw:
        return list(default or [])
    return [part.strip() for part in raw.split(sep) if part and part.strip()]
