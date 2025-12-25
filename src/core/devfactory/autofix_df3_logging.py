"""
DevFactory DF-3 — helper для логирования событий Autofix DF-3.

Этот модуль не знает, КАК конкретно вызывать БД (SQLAlchemy, asyncpg, raw psycopg и т.п.).
Он только строит SQL-запрос для вызова функции:

    analytics.log_devfactory_autofix_df3_event(...)

ВАЖНО: сигнатура функции в БД (по факту \df+):
  analytics.log_devfactory_autofix_df3_event(
      p_dev_task_id uuid,
      p_resource_kind text,
      p_action text,
      p_status text,
      p_dev_order_id uuid DEFAULT NULL,
      p_flowmind_plan_id uuid DEFAULT NULL,
      p_resource_path text DEFAULT NULL,
      p_duration_ms integer DEFAULT NULL,
      p_engine text DEFAULT NULL,
      p_notes text DEFAULT NULL,
      p_payload jsonb DEFAULT NULL
  ) returns bigint

Поэтому здесь используем ИМЕНОВАННЫЕ аргументы (p_* := ...), чтобы:
  - не зависеть от порядка аргументов;
  - переживать эволюцию функции (добавление параметров с дефолтами).

Интеграция:
    sql = build_log_autofix_df3_sql(...)
    db_execute(sql)  # через ваш существующий слой работы с БД
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from uuid import UUID


def _pg_literal(value: Optional[str]) -> str:
    """
    Простая обёртка для безопасной вставки строковых литералов в SQL.

    В боевой интеграции лучше использовать параметризованные запросы.
    Здесь задача — дать готовый SQL для внутреннего использования внутри DevFactory.
    """
    if value is None:
        return "null"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def build_log_autofix_df3_sql(
    *,
    dev_task_id: UUID,
    resource_kind: str,
    action: str,
    status: str,
    dev_order_id: Optional[UUID] = None,
    flowmind_plan_id: Optional[UUID] = None,
    resource_path: Optional[str] = None,
    duration_ms: Optional[int] = None,
    engine: str = "df3-core",
    notes: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Собирает SQL-вызов функции analytics.log_devfactory_autofix_df3_event(...).

    Возвращает готовую строку SQL вида:
        select analytics.log_devfactory_autofix_df3_event(...);

    Параметры:
        dev_task_id       — public_id dev.dev_task (UUID)
        resource_kind     — 'sql'|'python'|'html'|'md'|'ps1'|'config'|'other'
        action            — 'run'|'apply'|'suggest'|'dry-run'|'validate'
        status            — 'ok'|'error'|'skipped'
        dev_order_id      — опциональный UUID dev.dev_order
        flowmind_plan_id  — опциональный UUID плана FlowMind
        resource_path     — относительный путь ресурса в репозитории
        duration_ms       — длительность выполнения, мс
        engine            — ярлык движка (модель, агент)
        notes             — заметки
        payload           — JSON payload (dict)
    """
    dev_task_id_l = _pg_literal(str(dev_task_id))
    dev_order_id_l = _pg_literal(str(dev_order_id)) if dev_order_id else "null"
    flowmind_plan_id_l = _pg_literal(str(flowmind_plan_id)) if flowmind_plan_id else "null"

    resource_kind_l = _pg_literal(resource_kind)
    action_l = _pg_literal(action)
    status_l = _pg_literal(status)

    resource_path_l = _pg_literal(resource_path) if resource_path else "null"
    duration_ms_l = str(int(duration_ms)) if duration_ms is not None else "null"
    engine_l = _pg_literal(engine)
    notes_l = _pg_literal(notes) if notes else "null"

    if payload is None:
        payload_sql = "null"
    else:
        import json
        payload_sql = _pg_literal(json.dumps(payload, ensure_ascii=False))

    # Используем named-args, чтобы не зависеть от порядка параметров в функции.
    sql = f"""
select analytics.log_devfactory_autofix_df3_event(
  p_dev_task_id      := {dev_task_id_l}::uuid,
  p_resource_kind    := {resource_kind_l}::text,
  p_action           := {action_l}::text,
  p_status           := {status_l}::text,
  p_dev_order_id     := {dev_order_id_l}::uuid,
  p_flowmind_plan_id := {flowmind_plan_id_l}::uuid,
  p_resource_path    := {resource_path_l}::text,
  p_duration_ms      := {duration_ms_l}::integer,
  p_engine           := {engine_l}::text,
  p_notes            := {notes_l}::text,
  p_payload          := {payload_sql}::jsonb
);
""".strip()

    return sql
