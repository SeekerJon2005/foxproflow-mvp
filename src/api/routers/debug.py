# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\api\routers\debug.py
"""
FoxProFlow — Debug Router (NDC-safe)

Назначение
----------
Лёгкий отладочный роутер с дружелюбными к PowerShell/curl ответами:
- GET /debug/routes    — список всех зарегистрированных путей (method, path)
- GET /debug/env       — безопасная диагностическая выборка ENV
- GET /debug/version   — версия/метка сборки
- GET /debug/ping      — быстрый "pong" без зависимостей

Особенности
-----------
• Ответы — "fixed length" + "identity" (без сжатия), чтобы корректно
  работать в окружениях с жестким обработчиком заголовков (curl.exe/PS Invoke-RestMethod).
• Все импорты построены так, чтобы избежать циклов (late import main.app).
• Безопасно: не раскрывает секреты (пароли/ключи не логгируются).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.routing import APIRoute
from starlette.responses import Response

# --- Router ---
router = APIRouter(prefix="/debug", tags=["debug"])

# --- Output policy for diagnostics (PowerShell-friendly) ---
_DIAG_FIXED_LEN = str(os.getenv("FF_DIAG_FIXED_LENGTH", "1")).lower() in {"1", "true", "yes", "on"}
_DIAG_NO_GZIP = str(os.getenv("FF_DIAG_DISABLE_GZIP", "1")).lower() in {"1", "true", "yes", "on"}


def _json_response(obj: Any, *, status_code: int = 200) -> Response:
    """Return JSON with Content-Length and identity encoding (no gzip) for PS/curl."""
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    headers: Dict[str, str] = {
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "close",
        "Cache-Control": "no-store",
    }
    if _DIABoolean(_DIAG_NO_GZIP):
        headers["Content-Encoding"] = "identity"
    if _DIABoolean(_DIAG_FIXED_LEN):
        headers["Content-Length"] = str(len(raw))
    return Response(content=raw, status_code=status_code, headers=headers)


def _DIABoolean(flag: bool) -> bool:
    # small indirection to keep mypy quiet about constant folding
    return bool(flag)


def _safe_env(name: str, default: str = "") -> str:
    """Read env var without exposing secrets by accident."""
    val = os.getenv(name)
    if val is None:
        return default
    # redact obvious secrets
    if any(k in name.upper() for k in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
        return "****"
    return val


@router.get("/routes")
def list_routes() -> Response:
    """
    Вернёт плоский список всех зарегистрированных HTTP-маршрутов (method, path).
    Удобно для поиска пересечений и проверки подключения роутеров.
    """
    try:
        # late import to avoid circular imports
        from src.api.main import app as fastapi_app  # type: ignore
        items: List[Dict[str, str]] = []
        for r in getattr(fastapi_app, "routes", []):
            if isinstance(r, APIRoute):
                methods = sorted(r.methods or [])
                for m in methods:
                    items.append({"method": m, "path": r.path})
        items.sort(key=lambda it: (it["path"], it["method"]))
        return _json_response({"paths": items})
    except Exception as e:
        return _json_response({"error": repr(e)}, status_code=500)


@router.get("/env")
def env_diag() -> Response:
    """
    Безопасная выборка ключевых ENV (без секретов).
    Добавляйте сюда переменные, которые важно быстро проверить из продакшена.
    """
    safe = {
        "APP_NAME": _safe_env("APP_NAME", "foxproflow-api"),
        "FF_VERSION": _safe_env("FF_VERSION", "MVP-2.0"),
        "TZ": _safe_env("TZ", "Europe/Vilnius"),
        # DB
        "POSTGRES_HOST": _safe_env("POSTGRES_HOST", "postgres"),
        "POSTGRES_PORT": _safe_env("POSTGRES_PORT", "5432"),
        "POSTGRES_DB": _safe_env("POSTGRES_DB", "foxproflow"),
        # Redis/Celery (password redacted by _safe_env)
        "REDIS_HOST": _safe_env("REDIS_HOST", "redis"),
        "REDIS_PORT": _safe_env("REDIS_PORT", "6379"),
        "CELERY_DEFAULT_QUEUE": _safe_env("CELERY_DEFAULT_QUEUE", "default"),
        "AUTOPLAN_QUEUE": _safe_env("AUTOPLAN_QUEUE", "autoplan"),
        # Routing / OSRM / OD cache
        "OSRM_URL": _safe_env("OSRM_URL", "http://osrm:5000"),
        "OSRM_PROFILE": _safe_env("OSRM_PROFILE", "driving"),
        "OSRM_TIMEOUT": _safe_env("OSRM_TIMEOUT", "8.0"),
        "OD_CACHE_ENABLED": _safe_env("OD_CACHE_ENABLED", "1"),
        "OD_CACHE_TTL_H": _safe_env("OD_CACHE_TTL_H", "168"),
        # Planner thresholds (high level)
        "AUTOPLAN_SMOKE_MODE": _safe_env("AUTOPLAN_SMOKE_MODE", "0"),
        "USE_DYNAMIC_RPM": _safe_env("USE_DYNAMIC_RPM", "1"),
        "DYNAMIC_RPM_QUANTILE": _safe_env("DYNAMIC_RPM_QUANTILE", "p25"),
        "AUTOPLAN_RPM_MIN": _safe_env("AUTOPLAN_RPM_MIN", "130"),
        "AUTOPLAN_P_ARRIVE_MIN": _safe_env("AUTOPLAN_P_ARRIVE_MIN", "0.40"),
        "AUTOPLAN_SCORING_METRIC": _safe_env("AUTOPLAN_SCORING_METRIC", "rph"),
        "AUTOPLAN_RPH_MIN": _safe_env("AUTOPLAN_RPH_MIN", "2500"),
        # Diagnostics formatting
        "FF_DIAG_FIXED_LENGTH": _safe_env("FF_DIAG_FIXED_LENGTH", "1"),
        "FF_DIAG_DISABLE_GZIP": _safe_env("FF_DIAG_DISABLE_GZIP", "1"),
    }
    return _json_response({"env": safe})


@router.get("/version")
def version() -> Response:
    """Простая метка версии/сборки."""
    payload = {
        "ok": True,
        "name": _safe_env("APP_NAME", "foxproflow-api"),
        "version": _safe_env("FF_VERSION", "MVP-2.0"),
    }
    return _json_response(payload)


@router.get("/ping")
def ping() -> Response:
    """Минимальный health-like ответ без внешних завязок."""
    return _json_response({"ok": True, "pong": True})
