# -*- coding: utf-8 -*-
# Auto-generated Celery agent tasks for agents.demo.hello (FoxProFlow scaffold)

from __future__ import annotations

from typing import Any, Dict
from celery import shared_task
from src.core import emit_start, emit_done, emit_error
from src.worker.tasks_agents import _connect_pg


@shared_task(name="agents.demo.hello", queue="agents")  # type: ignore[misc]
def hello(**kwargs: Any) -> Dict[str, Any]:
    """
    Демонстрационный агент для проверки фабрики агентов.

    Поведение v0:
      * пишет события в Observability (emit_start / emit_done / emit_error);
      * делает простой запрос SELECT 1 в БД через _connect_pg();
      * возвращает result с полями:
          - ok: True/False (по факту выполнения);
          - processed: количество обработанных единиц (для демо = 1 при успешном SELECT 1);
          - event_id: идентификатор события запуска;
          - echo: входные kwargs для удобной отладки;
          - db_check: 1 при успешном SELECT 1, None если что-то пошло не так.
    """
    ev_id = emit_start(
        "agent",
        payload={
            "task": "agents.demo.hello",
            "kwargs": kwargs,
        },
    )

    result: Dict[str, Any] = {
        "ok": True,
        "processed": 0,
        "event_id": ev_id,
        "echo": kwargs,
    }

    try:
        # Пример минимальной бизнес-логики: проверяем подключение к БД
        with _connect_pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
            if row is not None:
                # Не трогаем row[0], потому что это может быть dict/RealDictRow/Row
                # Для демо достаточно самого факта, что SELECT 1 вернул строку.
                result["processed"] = 1
                result["db_check"] = 1
            else:
                result["db_check"] = None

        emit_done(
            "agent",
            payload={
                "task": "agents.demo.hello",
                "event_id": ev_id,
                "result": result,
            },
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        emit_error(
            "agent",
            payload={
                "task": "agents.demo.hello",
                "event_id": ev_id,
                "error": str(exc),
            },
        )
        # Не глотаем исключение — пусть Celery его увидит
        raise
