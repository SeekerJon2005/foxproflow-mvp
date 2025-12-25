# -*- coding: utf-8 -*-
# file: src/api/routers/health_ex.py
# Переработанная устойчивая версия расширенной health-ручки:
# - фикс-длина + identity-encoding (устойчиво для PowerShell/curl.exe)
# - «умный» DSN: если DATABASE_URL пустой/без пароля — собираем из POSTGRES_*
# - Postgres: psycopg3 → psycopg2 fallback
# - Redis: ping + beat/queue метрики (из ops.* задач)
# - Celery: control.ping() (если доступно) — сводка по воркерам
# Изменения в этой ревизии:
# - Агрегированный статус: "ok" если (pg_ok AND redis_ok), иначе "degraded".
# - Путь переименован на /health/extended2, чтобы не дублировать /health/extended.
from __future__ import annotations

import json
import os
import time
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter
from starlette.responses import Response

router = APIRouter(tags=["health"])

# ------------------------------------------------------------------------------
# Утилиты вывода (фикс-длина + identity), управляются флагами из .env
# ------------------------------------------------------------------------------
_DIAG_FIXED_LEN = os.getenv("FF_DIAG_FIXED_LENGTH", "1") == "1"
_DIAG_NO_GZIP = os.getenv("FF_DIAG_DISABLE_GZIP", "1") == "1"


def _json_fixed(obj: Any, *, status_code: int = 200) -> Response:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    headers = {
        "Connection": "close",
        "Cache-Control": "no-store",
    }
    if _DIAG_FIXED_LEN:
        headers["Content-Length"] = str(len(raw))
    if _DIAG_NO_GZIP:
        headers["Content-Encoding"] = "identity"
    return Response(content=raw, media_type="application/json", headers=headers, status_code=status_code)


def _mask(val: Optional[str], keep: int = 2) -> Optional[str]:
    if not val:
        return val
    return (val[:keep] + "***" + val[-keep:]) if len(val) > keep else "*" * len(val)


# ------------------------------------------------------------------------------
# DSN: берём DATABASE_URL; если пароль отсутствует — собираем из POSTGRES_*
# ------------------------------------------------------------------------------
def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _dsn_from_env() -> str:
    user = _env("POSTGRES_USER", "admin")
    pwd = _env("POSTGRES_PASSWORD", "")
    host = _env("POSTGRES_HOST", "postgres")
    port = _env("POSTGRES_PORT", "5432")
    db = _env("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _dsn_has_password(dsn: str) -> bool:
    try:
        u = urlparse(dsn)
        userinfo = (u.netloc or "").split("@", 1)[0]
        if ":" not in userinfo:
            return False
        pw = userinfo.split(":", 1)[1]
        return bool(pw)
    except Exception:
        return False


def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn and _dsn_has_password(dsn):
        return dsn
    # либо DATABASE_URL пуст/без пароля — используем POSTGRES_*:
    return _dsn_from_env()


# ------------------------------------------------------------------------------
# Postgres check: psycopg3 → psycopg2 fallback
# ------------------------------------------------------------------------------
def _sanitize_dsn(dsn: str) -> str:
    if not dsn:
        return dsn
    try:
        u = urlparse(dsn)
        userinfo = (u.netloc or "").split("@", 1)[0]
        if ":" in userinfo:
            user = userinfo.split(":", 1)[0]
            netloc = u.netloc.replace(userinfo, f"{user}:***")
            return u._replace(netloc=netloc).geturl()
        return dsn
    except Exception:
        return dsn


def _pg_ok() -> Dict[str, Any]:
    dsn = _db_dsn()
    try:
        import psycopg  # type: ignore
        with psycopg.connect(dsn, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "ok", "driver": "psycopg3"}
    except Exception:
        try:
            import psycopg2  # type: ignore
            cn = psycopg2.connect(dsn, connect_timeout=2)
            cur = cn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cn.close()
            return {"status": "ok", "driver": "psycopg2"}
        except Exception as e2:
            return {"status": "fail", "error": repr(e2), "dsn": _sanitize_dsn(dsn)}


# ------------------------------------------------------------------------------
# Redis check + beat/queue метрики (из ops.beat.heartbeat / ops.queue.watchdog)
# ------------------------------------------------------------------------------
def _redis_client():
    import redis  # type: ignore

    host = _env("REDIS_HOST", "redis")
    port = int(_env("REDIS_PORT", "6379"))
    pwd = os.getenv("REDIS_PASSWORD") or None
    return redis.Redis(
        host=host,
        port=port,
        password=pwd,
        db=0,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _redis_ok_and_stats() -> Dict[str, Any]:
    try:
        r = _redis_client()
        r.ping()
        # метрики, которые пишет наш beat/watchdog
        beat_ts = r.get("beat:heartbeat")
        queue_len = r.get("queue:len")
        busy_streak = r.get("queue:busy_streak_min")

        beat_age = None
        if beat_ts is not None:
            try:
                beat_age = int(time.time()) - int(beat_ts)
            except Exception:
                beat_age = None

        return {
            "status": "ok",
            "health": {
                "beat_age_sec": beat_age,
                "queue.len": int(queue_len) if queue_len is not None else None,
                "queue.busy_streak_min": int(busy_streak) if busy_streak is not None else None,
            },
        }
    except Exception as e:
        return {"status": "fail", "error": repr(e)}


# ------------------------------------------------------------------------------
# Celery workers: control.ping() (если доступно, не критично для статуса)
# ------------------------------------------------------------------------------
def _celery_workers() -> List[Dict[str, Any]]:
    try:
        from src.worker.celery_app import app as celery_app  # type: ignore
    except Exception:
        return []
    try:
        # уменьшаем риск зависаний
        socket.setdefaulttimeout(1.0)
        replies = celery_app.control.ping(timeout=0.5) or []
        out: List[Dict[str, Any]] = []
        for rep in replies:
            # формат [{'celery@<node>': {'ok': 'pong'}}]
            if not isinstance(rep, dict):
                continue
            for k, v in rep.items():
                out.append({"node": str(k), "reply": v})
        return out
    except Exception:
        return []


# ------------------------------------------------------------------------------
# Ручка /health/extended2 (не конфликтует с /health/extended)
# ------------------------------------------------------------------------------
@router.get("/health/extended2")
def health_extended2():
    data: Dict[str, Any] = {
        "postgres": {"status": "fail"},
        "redis": {"status": "unknown"},
        "health": {"beat_age_sec": None, "queue.len": None, "queue.busy_streak_min": None},
        "workers": [],
        "info": {
            # полезно для диагностики, секреты замаскированы
            "dsn": _sanitize_dsn(_db_dsn()),
            "redis_host": _env("REDIS_HOST", "redis"),
            "redis_port": _env("REDIS_PORT", "6379"),
        },
    }

    pg = _pg_ok()
    data["postgres"] = pg

    rd = _redis_ok_and_stats()
    data["redis"] = {"status": rd.get("status", "fail")}
    if "health" in rd:
        data["health"].update(rd["health"])

    data["workers"] = _celery_workers()

    # Итоговый агрегированный статус:
    # ok — когда оба (pg и redis) ok; иначе degraded (не валим в "fail", это диагностическая ручка).
    pg_ok = (data["postgres"].get("status") == "ok")
    redis_ok = (data["redis"].get("status") == "ok")
    status = "ok" if (pg_ok and redis_ok) else "degraded"

    return _json_fixed({"status": status, "data": data})
