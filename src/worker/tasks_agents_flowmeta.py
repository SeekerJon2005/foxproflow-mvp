# -*- coding: utf-8 -*-
# file: src/worker/tasks_agents_flowmeta.py
"""
Агенты FlowMeta / FlowSec:

- agents.flowmeta.validate: прогоняет meta_validator.validate_world
  и записывает результат в ops.flowmeta_events.

Интегрируется в рой агентов через тот же механизм, что и demo_hello:
    from src.worker.tasks_agents_flowmeta import flowmeta_validate
    res = flowmeta_validate.run()
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import psycopg  # psycopg v3
from psycopg.types.json import Json

from src.flowlang.meta_loader import load_world_from_conn
from src.flowlang.meta_validator import validate_world

__all__ = [
    "FlowmetaValidateAgent",
    "flowmeta_validate",
]

JsonDict = Dict[str, Any]


def _get_dsn_from_env(
    primary_var: str = "FF_DB_DSN",
    fallback_var: str = "DATABASE_URL",
) -> str:
    """
    Берём DSN для Postgres из переменных окружения.

    Приоритет: FF_DB_DSN, затем DATABASE_URL.
    """
    dsn = os.environ.get(primary_var) or os.environ.get(fallback_var)
    if not dsn:
        raise RuntimeError(
            f"Не найден DSN для БД: ни {primary_var}, ни {fallback_var} не заданы."
        )
    return dsn


def _calc_severity_max(result: JsonDict) -> str:
    """
    Определяем максимальную важность среди violations.
    Порядок: error > warning > info.
    """
    order = {"error": 3, "warning": 2, "info": 1}
    max_level = 0
    max_sev = "info"

    for v in result.get("violations", []):
        sev = str(v.get("severity") or "warning")
        lvl = order.get(sev, 2)
        if lvl > max_level:
            max_level = lvl
            max_sev = sev

    return max_sev


@dataclass
class FlowmetaValidateAgent:
    """
    Простой объект-агент с методом run(...),
    по паттерну demo_hello: hello.run(foo='bar', meaning=42).

    Использование:
        from src.worker.tasks_agents_flowmeta import flowmeta_validate
        res = flowmeta_validate.run()
    """

    name: str = "agents.flowmeta.validate"

    def run(self, *, world_name: str = "foxproflow", dsn: Optional[str] = None) -> JsonDict:
        """
        Загружает мир FlowMeta из БД, валидирует его и пишет результат
        в ops.flowmeta_events.

        Возвращает словарь:
        {
          "ok": bool,
          "n_violations": int,
          "severity_max": "info"|"warning"|"error",
          "event_id": int | None,
          "world_name": "...",
          "result": {... полное тело validate_world ...}
        }
        """
        if dsn is None:
            dsn = _get_dsn_from_env()

        # 1. Загружаем мир FlowMeta и валидируем
        with psycopg.connect(dsn) as conn:
            world = load_world_from_conn(conn, world_name=world_name)
            result = validate_world(world)

            ok = bool(result.get("ok", False))
            n_violations = int(result.get("n_violations", 0))
            severity_max = _calc_severity_max(result)

            # 2. Записываем событие в ops.flowmeta_events
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.flowmeta_events (
                        world_name, ok, n_violations, severity_max, payload
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        world_name,
                        ok,
                        n_violations,
                        severity_max,
                        Json(result),  # явно упаковываем dict в JSON для jsonb
                    ),
                )
                row = cur.fetchone()
                event_id = int(row[0]) if row is not None else None

            conn.commit()

        out: JsonDict = {
            "ok": ok,
            "n_violations": n_violations,
            "severity_max": severity_max,
            "event_id": event_id,
            "world_name": world_name,
            "result": result,
        }
        return out


# Экземпляр агента по аналогии с demo_hello. Можно использовать как hello.run(...)
flowmeta_validate = FlowmetaValidateAgent()
