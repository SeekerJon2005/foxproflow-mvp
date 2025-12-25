# -*- coding: utf-8 -*-
# file: src/worker/tasks_devfactory.py
from __future__ import annotations

"""
Тонкий адаптер для задач DevFactory.

Назначение:
- обеспечить стабильный модуль "src.worker.tasks_devfactory" для Celery и register_tasks;
- реальная логика и Celery-задачи DevFactory живут в "src.worker.tasks.devfactory_code";
- сюда же можно добавлять тонкие Celery-обёртки верхнего уровня:
  - DF-3 Autofix (devfactory.autofix_df3.*)
  - коммерческий контур DevFactory (DEV-M0-01..04): devfactory.commercial.run_order

Таким образом:
- внешние импорты используют "src.worker.tasks_devfactory";
- внутренняя реализация (devfactory_code, адаптеры DF-3, commercial tasks) может меняться,
  не ломая стабильную точку входа для Celery/Beat и DevFactory.
"""

import logging
import os
from typing import Any, Dict, List, Tuple

from celery import shared_task

from src.devfactory.autofix_df3_adapter import run_autofix_df3_for_task
from src.core.devfactory import autofix as autofix_core

log = logging.getLogger(__name__)

# Важно:
#   - devfactory_code должен содержать только то, что безопасно экспортировать;
#   - Celery-задачи и функции DevFactory объявляются там, а не здесь,
#     за исключением тонких обёрток верхнего уровня (как devfactory.autofix_df3.*),
#     которые используют отдельные адаптеры и не привязаны к внутренней структуре devfactory_code.
from src.worker.tasks.devfactory_code import *  # noqa: F401,F403


# ============================================================================
# DEV-M0 (commercial loop): регистрация задач (side-effect import)
# ============================================================================
# ВАЖНО: Celery регистрирует shared_task при импорте модуля.
# Делаем best-effort импорт, чтобы коммерческие задачи всегда были доступны,
# даже если register_tasks импортирует только tasks_devfactory.
try:
    import src.worker.tasks.devfactory_commercial  # noqa: F401
except Exception:
    log.debug("devfactory commercial tasks import failed", exc_info=True)


# ============================================================================
# Локальный helper подключения к Postgres
# ============================================================================

def _normalize_pg_dsn(dsn: str) -> str:
    """
    Нормализация URL-DSN, чтобы переживать разные драйверные префиксы.
    """
    dsn = (dsn or "").strip()
    if not dsn:
        return ""
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    return dsn


def _build_pg_dsn() -> str:
    dsn = _normalize_pg_dsn(os.getenv("DATABASE_URL") or "")
    if dsn:
        return dsn

    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "")
    pg_host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    pg_port = os.getenv("POSTGRES_PORT", "5432") or "5432"
    pg_db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

    auth = f"{pg_user}:{pg_pass}@" if pg_pass else f"{pg_user}@"
    return f"postgresql://{auth}{pg_host}:{pg_port}/{pg_db}"


def _connect_pg():
    """
    Возвращает sync connection (psycopg v3 или psycopg2).
    """
    dsn = _build_pg_dsn()
    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


# ============================================================================
# DF-3: единичный запуск Autofix для задачи (через Celery)
# ============================================================================

@shared_task(name="devfactory.autofix_df3.run_for_task", ignore_result=False)
def devfactory_autofix_df3_run_for_task(devtask_id: int, dry_run: bool = True) -> Dict[str, Any]:
    """
    Celery-задача DF-3 для запуска Autofix v0.1 с логированием в
    dev.dev_autofix_event_df3_log и последующей агрегацией в
    analytics.devfactory_autofix_df3_kpi_daily_mv.

    Вход:
        devtask_id: int — ID записи в dev.dev_task.
        dry_run: bool — режим "только посчитать/сгенерировать" (если ядро его поддерживает).

    Выход (краткий JSON-результат):
        {
          "ok": bool,
          "decision": str,
          "latency_ms": int,
          "error": Optional[str],
        }

    Полный результат Autofix (raw_result) остаётся в адаптере и может
    использоваться на уровне API/логов при необходимости.
    """
    try:
        result = run_autofix_df3_for_task(devtask_id=int(devtask_id), dry_run=bool(dry_run))
        return {
            "ok": bool(result.ok),
            "decision": str(result.decision),
            "latency_ms": int(result.latency_ms),
            "error": result.error,
        }
    except Exception as e:
        # fail-fast: всегда формализованный ответ, не “тишина”
        log.exception("DF-3 run_for_task failed: devtask_id=%s", devtask_id)
        return {
            "ok": False,
            "decision": "error",
            "latency_ms": 0,
            "error": str(e),
        }


# ============================================================================
# DF-3: массовый Autofix — scan_and_run_pending
# ============================================================================

def _load_pending_autofix_tasks(conn, limit: int) -> Tuple[List[Tuple[int, str]], int]:
    """
    Загружаем dev-задачи, для которых:
      - autofix_enabled = true,
      - статус 'new' или 'failed'.

    Затем дополнительно фильтруем по стеку через autofix_core.can_autofix_stack().

    Возвращаем:
      - список (id, stack) для запуска,
      - skipped_due_to_stack: сколько кандидатур отфильтровано по стеку
    """
    lim = int(limit)
    if lim <= 0:
        lim = 1

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, stack
              FROM dev.dev_task
             WHERE COALESCE(autofix_enabled, FALSE) = TRUE
               AND status IN ('new','failed')
             ORDER BY created_at
             LIMIT %s;
            """,
            (lim,),
        )
        rows = cur.fetchall() or []

    result: List[Tuple[int, str]] = []
    skipped_due_to_stack = 0

    for tid, stack in rows:
        s = str(stack)
        try:
            if not autofix_core.can_autofix_stack(s):
                skipped_due_to_stack += 1
                continue
        except Exception:
            # Если ядро не умеет/не может проверить — не блокируем обработку (best-effort)
            pass

        result.append((int(tid), s))

    return result, skipped_due_to_stack


@shared_task(name="devfactory.autofix_df3.scan_and_run_pending", ignore_result=False)
def devfactory_autofix_df3_scan_and_run_pending(limit: int = 20, dry_run: bool = True) -> Dict[str, Any]:
    """
    Массовый Autofix DF-3:

      1) Находим dev-задачи с autofix_enabled = true и статусом 'new'/'failed'.
      2) Фильтруем по стеку через autofix_core.can_autofix_stack().
      3) Для каждой используем DF-3 адаптер run_autofix_df3_for_task().
      4) Лог DF-3 (dev.dev_autofix_event_df3_log) и KPI-витрина
         analytics.devfactory_autofix_df3_kpi_daily_mv пополняются автоматически.

    Параметры:
        limit:   макс. число задач за один проход.
        dry_run: пробный режим (если ядро поддерживает).

    Возвращаем краткий отчёт (backward-compatible: добавлены поля skipped/errors):
        {
          "total_candidates": int,
          "skipped_due_to_stack": int,
          "processed": int,
          "ok": int,
          "error": int,
          "ok_ids": [int, ...],
          "error_ids": [int, ...],
          "errors": { "<id>": "<error>", ... },   # optional details
          "dry_run": bool,
        }
    """
    conn = _connect_pg()
    try:
        candidates, skipped_due_to_stack = _load_pending_autofix_tasks(conn, limit=limit)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    total_candidates = len(candidates)
    processed = 0
    ok_count = 0
    err_count = 0
    ok_ids: List[int] = []
    err_ids: List[int] = []
    errors: Dict[str, str] = {}

    for devtask_id, stack in candidates:
        try:
            res = run_autofix_df3_for_task(devtask_id=int(devtask_id), dry_run=bool(dry_run))
            processed += 1
            if res.ok:
                ok_count += 1
                ok_ids.append(int(devtask_id))
            else:
                err_count += 1
                err_ids.append(int(devtask_id))
                if res.error:
                    errors[str(devtask_id)] = str(res.error)
        except Exception as e:
            processed += 1
            err_count += 1
            err_ids.append(int(devtask_id))
            errors[str(devtask_id)] = str(e)
            log.exception("DF-3 scan_and_run_pending failed: devtask_id=%s stack=%s", devtask_id, stack)

    return {
        "total_candidates": total_candidates,
        "skipped_due_to_stack": int(skipped_due_to_stack),
        "processed": processed,
        "ok": ok_count,
        "error": err_count,
        "ok_ids": ok_ids,
        "error_ids": err_ids,
        "errors": errors,
        "dry_run": bool(dry_run),
    }
