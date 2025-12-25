# -*- coding: utf-8 -*-
# file: src/api/security/architect_guard.py
from __future__ import annotations

import hmac
import logging
import os
from typing import List, Optional, Set, Tuple

from fastapi import Header, HTTPException, Request

log = logging.getLogger(__name__)

# Чтобы не спамить логами на каждом запросе: предупреждаем 1 раз на env_name.
_WARNED_ENVS: Set[str] = set()


def _load_expected_keys(env_name: str) -> List[str]:
    """
    Загружает ключ(и) из env.

    Поддержка ротации ключей:
      FF_ARCHITECT_KEY="k1,k2,k3"  -> принимаем любой из списка.
    """
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return []

    # допускаем ',' и ';' как разделители
    raw = raw.replace(";", ",")
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _normalize_presented_key(value: Optional[str]) -> str:
    """
    Нормализует заголовок:
      - трим
      - поддержка "Bearer <key>" / "Token <key>" (на будущее удобнее в клиентах)
    """
    if not value:
        return ""
    v = str(value).strip()
    for prefix in ("Bearer ", "Token "):
        if v.startswith(prefix):
            v = v[len(prefix) :].strip()
            break
    return v


def require_architect_key(
    *,
    env_name: str = "FF_ARCHITECT_KEY",
    header_name: str = "X-FF-Architect-Key",
    allow_if_missing: bool = True,
    require_header_if_missing: bool = False,
) -> object:
    """
    ARCHITECT-only gate for write operations.

    Policy:
      - Если env_name задан -> требуем header_name и сравниваем (timing-safe).
      - Если env_name НЕ задан:
          - allow_if_missing=True  -> dev-mode: разрешаем, но логируем warning 1 раз
                                     (опционально можно требовать присутствие заголовка,
                                      если require_header_if_missing=True).
          - allow_if_missing=False -> 500 (misconfigured).

    Ротация ключей:
      - env может содержать список ключей через запятую/точку с запятой.

    Возвращает dependency-функцию FastAPI (Depends(...)).
    """

    def _dep(
        request: Request,
        x_ff_architect_key: Optional[str] = Header(default=None, alias=header_name),
    ) -> bool:
        expected_keys = _load_expected_keys(env_name)

        if not expected_keys:
            if allow_if_missing:
                if require_header_if_missing and not (x_ff_architect_key or "").strip():
                    raise HTTPException(status_code=401, detail=f"Missing {header_name}")

                # warn once per env_name
                if env_name not in _WARNED_ENVS:
                    _WARNED_ENVS.add(env_name)
                    client = getattr(request, "client", None)
                    client_host = getattr(client, "host", None) if client else None
                    log.warning(
                        "Architect guard: %s is NOT set -> allowing write (dev-mode). "
                        "Set %s in API container env to enforce. client=%s",
                        env_name,
                        env_name,
                        client_host,
                    )
                return True

            raise HTTPException(status_code=500, detail=f"{env_name} is not set in API environment")

        presented = _normalize_presented_key(x_ff_architect_key)
        if not presented:
            raise HTTPException(status_code=401, detail=f"Missing {header_name}")

        # timing-safe compare against each configured key
        for k in expected_keys:
            if hmac.compare_digest(presented, k):
                return True

        raise HTTPException(status_code=403, detail="Architect key invalid")

    return _dep
