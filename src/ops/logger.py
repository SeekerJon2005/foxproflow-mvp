# -*- coding: utf-8 -*-
# file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\ops\logger.py
"""
FoxProFlow — ops.logger (NDC-safe)

Лёгкий OPS-логгер с записью событий в таблицу ops.agent_events (если она есть),
либо с выводом предупреждений в стандартный логгер. Подходит для агентных задач
и служебных операций (heartbeat, watchdog, SLA, doctor-агенты и т.п.).

Функции:
- agent_event(agent, level, action, payload=None, ok=None, latency_ms=None) -> bool
- timeit(agent, action, level="info", payload=None): контекст-менеджер для измерения latency

Зависимости:
- psycopg (v3) или psycopg2 (fallback)
- переменные окружения для подключения к БД:
  • DATABASE_URL или (POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_HOST/POSTGRES_PORT/POSTGRES_DB)
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Optional

log = logging.getLogger(__name__)


def _dsn() -> str:
    """
    Сборка DSN для Postgres: при наличии DATABASE_URL используем его,
    иначе — POSTGRES_*.
    """
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _connect():
    """Подключение к Postgres через psycopg (v3) или psycopg2 (fallback)."""
    try:
        import psycopg  # type: ignore
        return psycopg.connect(_dsn())
    except Exception:  # pragma: no cover - fallback path
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(_dsn())


def agent_event(
    agent: str,
    level: str,
    action: str,
    payload: Optional[dict] = None,
    *,
    ok: Optional[bool] = None,
    latency_ms: Optional[int] = None,
) -> bool:
    """
    Записывает событие агента в ops.agent_events (если таблица существует).
    Если таблицы нет — пишет предупреждение в лог.

    Параметры:
      agent       — имя агента/компонента (например, 'autoplan-doctor')
      level       — 'info' | 'warn' | 'error'
      action      — произвольная метка действия (например, 'low-apply-ratio')
      payload     — словарь с данными события (будет сериализован в JSON)
      ok          — булево состояние (успех/неуспех)
      latency_ms  — длительность операции (мс)

    Возвращает:
      True, если запись в таблицу выполнена; False при логировании без БД/ошибке.
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        # Проверяем наличие таблицы (не падаем, если нет)
        cur.execute("SELECT to_regclass('ops.agent_events') IS NOT NULL;")
        have = bool(cur.fetchone()[0])

        if have:
            cur.execute(
                "INSERT INTO ops.agent_events (ts, agent, level, action, payload, ok, latency_ms) "
                "VALUES (now(), %s, %s, %s, %s::jsonb, %s, %s);",
                (
                    agent,
                    level,
                    action,
                    json.dumps(payload or {}, ensure_ascii=False),
                    ok,
                    latency_ms,
                ),
            )
            conn.commit()
            return True
        else:
            # Таблица отсутствует — логируем предупреждение и продолжаем работу
            log.warning(
                "OPS[%s] %s %s payload=%s ok=%s latency_ms=%s (ops.agent_events missing)",
                agent,
                level,
                action,
                payload,
                ok,
                latency_ms,
            )
            return False
    except Exception as e:  # pragma: no cover - защитный контур
        log.warning("ops.logger.agent_event failed: %r", e)
        return False
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
        except Exception:
            pass


@contextmanager
def timeit(
    agent: str,
    action: str,
    *,
    level: str = "info",
    payload: Optional[dict] = None,
):
    """
    Контекст-менеджер для измерения времени выполнения и записи события.

    Пример:
        from src.ops.logger import timeit
        with timeit("autoplan-doctor", "check-apply-ratio", level="info", payload={"window_min":30}):
            run_check()

    • При исключении записывается событие уровня "error" с полем payload['error'].
    • При успехе записывается событие указанного уровня, с latency_ms.
    """
    t0 = time.perf_counter()
    ok = True
    try:
        yield
    except Exception as e:
        ok = False
        # Немедленно фиксируем ошибку
        agent_event(
            agent,
            "error",
            action,
            {**(payload or {}), "error": repr(e)},
            ok=False,
            latency_ms=None,
        )
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        agent_event(agent, level, action, payload, ok=ok, latency_ms=elapsed_ms)
