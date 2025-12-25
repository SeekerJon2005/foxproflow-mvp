# file: src/api/routers/health.py
from __future__ import annotations

import os
import time
from typing import Any, Dict

import psycopg
import redis
from fastapi import APIRouter
from fastapi.responses import Response

"""
Устойчивые health-ручки:

- GET /health           — минимальный JSON ({"status":"ok"}). При FF_HEALTH_DIAG=1 (по умолчанию)
                         выставляет Content-Length и Connection: close — это устраняет
                         'Response ended prematurely' в PowerShell/WinHTTP.
- GET /health/text      — текстовый аналог ("ok", 2 байта), также с фиксированной длиной при FF_HEALTH_DIAG=1.
- GET /health/extended  — расширенная диагностика Postgres/Redis с латентностями.

Параметры окружения (необязательные):
- FF_HEALTH_DIAG                = "1"|"0"   (по умолчaniu "1"): включить фиксированные заголовки для /health и /health/text
- FF_HEALTH_PG_TIMEOUT_SEC      = "3"       (таймаут подключения к PG)
- FF_HEALTH_REDIS_TIMEOUT_SEC   = "2"       (socket_timeout Redis)
- DATABASE_URL / ...            (см. _pg_dsn)
- REDIS_HOST / REDIS_PORT / REDIS_PASSWORD / CELERY_BROKER_URL
"""

router = APIRouter(prefix="/health", tags=["health"])


def _env_flag(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _json_ok() -> Response:
    # Короткий ответ, дружелюбный к WinHTTP/IRM.
    payload = b'{"status":"ok"}'  # 15 байт
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    if _env_flag("FF_HEALTH_DIAG", "1"):
        headers["Content-Length"] = str(len(payload))
        headers["Connection"] = "close"
    return Response(content=payload, status_code=200, headers=headers)


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def health() -> Response:
    # /health  и /health/ — оба работают
    return _json_ok()


@router.get("/text", include_in_schema=False)
def health_text() -> Response:
    # Текстовый вариант — 2 байта "ok"
    payload = b"ok"
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
    }
    if _env_flag("FF_HEALTH_DIAG", "1"):
        headers["Content-Length"] = "2"
        headers["Connection"] = "close"
    return Response(content=payload, status_code=200, headers=headers)


def _pg_dsn() -> str:
    env = os.getenv
    # Приоритет: готовые DSN/URL
    for k in (
        "DATABASE_URL",
        "SQLALCHEMY_DATABASE_URL",
        "SQLALCHEMY_DATABASE_URI",
        "DATABASE_DSN",
        "DB_DSN",
    ):
        v = env(k)
        if v:
            return v
    # Сборка из атомарных переменных
    host = env("PGHOST") or env("DB_HOST") or env("POSTGRES_HOST") or "postgres"
    port = env("PGPORT") or env("DB_PORT") or env("POSTGRES_PORT") or "5432"
    user = env("PGUSER") or env("DB_USER") or env("POSTGRES_USER") or "admin"
    pwd = env("PGPASSWORD") or env("DB_PASSWORD") or env("POSTGRES_PASSWORD") or ""
    db = env("PGDATABASE") or env("DB_NAME") or env("POSTGRES_DB") or "foxproflow"
    return (
        f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
        if pwd
        else f"postgresql://{user}@{host}:{port}/{db}"
    )


def _check_postgres() -> Dict[str, Any]:
    dsn = _pg_dsn()
    t0 = time.perf_counter()
    timeout_sec = float(os.getenv("FF_HEALTH_PG_TIMEOUT_SEC", "3"))
    try:
        with psycopg.connect(dsn, connect_timeout=int(timeout_sec)) as conn:
            with conn.cursor() as cur:
                cur.execute("select current_user, current_database()")
                row = cur.fetchone()
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "who": row,
        }
    except Exception as e:
        return {"ok": False, "error": repr(e), "dsn_used": dsn}


def _check_redis() -> Dict[str, Any]:
    env = os.getenv
    host = env("REDIS_HOST") or "redis"  # сетевое имя сервиса в docker-compose
    port = int(env("REDIS_PORT") or "6379")
    pwd = env("REDIS_PASSWORD")
    url = env("CELERY_BROKER_URL") or env("REDIS_URL")
    t0 = time.perf_counter()
    socket_timeout = float(env("FF_HEALTH_REDIS_TIMEOUT_SEC") or "2")
    try:
        r = redis.Redis(
            host=host,
            port=port,
            password=pwd,
            db=0,
            socket_timeout=socket_timeout,
        )
        pong = r.ping()
        return {
            "ok": bool(pong),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "host": host,
            "port": port,
            "url_hint": url,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": repr(e),
            "host": host,
            "port": port,
            "url_hint": url,
        }


@router.get("/extended", include_in_schema=False)
def health_extended() -> Dict[str, Any]:
    pg = _check_postgres()
    rd = _check_redis()
    ok = bool(pg.get("ok") and rd.get("ok"))
    return {
        "status": "ok" if ok else "degraded",
        "ready": ok,
        "postgres": pg,
        "redis": rd,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
