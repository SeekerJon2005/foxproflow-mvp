from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .models import DevTask, DevTaskStatus, DevTaskId


def _row_to_dict(cur, row) -> Dict[str, Any]:
    """
    Унификация для разных курсоров (psycopg2/psycopg3).
    Если курсор уже RealDictCursor — просто возвращаем row.
    """
    if isinstance(row, dict):
        return row
    colnames = [c.name for c in cur.description]
    return {name: value for name, value in zip(colnames, row)}


def _insert_event(
    conn,
    *,
    event_type: str,
    correlation_id: str,
    severity: str = "info",
    payload: Dict[str, Any],
) -> None:
    """
    Пишем событие DevFactory в ops.event_log.

    Ожидаемая схема ops.event_log:
      id             bigint,
      ts             timestamptz,
      source         text,
      event_type     text,
      severity       text,
      correlation_id text,
      tenant_id      text,
      payload        jsonb.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.event_log (
                    ts,
                    source,
                    event_type,
                    severity,
                    correlation_id,
                    tenant_id,
                    payload
                )
                VALUES (
                    now(),
                    'devfactory',
                    %s,
                    %s,
                    %s,
                    NULL,
                    %s::jsonb
                );
                """,
                (
                    event_type,
                    severity,
                    correlation_id,
                    json.dumps(payload),
                ),
            )
    except Exception:
        # Никогда не валим основную операцию DevFactory из-за проблем с логированием
        pass


def create_task(
    conn,
    *,
    stack: str,
    title: Optional[str],
    input_spec: Dict[str, Any],
    source: str = "architect",
) -> DevTask:
    """
    Создаёт новую задачу DevFactory и пишет событие task_created.

    id        — внутренний числовой идентификатор (bigint);
    public_id — устойчивый UUID (генерируется в БД через gen_random_uuid()).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dev.dev_task (stack, title, input_spec, source)
            VALUES (%s, %s, %s::jsonb, %s)
            RETURNING
                id,
                public_id,
                created_at,
                updated_at,
                status,
                source,
                stack,
                title,
                input_spec,
                result_spec,
                error,
                links
            """,
            (stack, title, json.dumps(input_spec), source),
        )
        row = cur.fetchone()
        row_dict = _row_to_dict(cur, row)

        _insert_event(
            conn,
            event_type="task_created",
            correlation_id=str(row_dict["id"]),
            payload={
                "stack": stack,
                "title": title,
                "source": source,
                "status": row_dict["status"],
                "input_spec": input_spec,
                "public_id": str(row_dict.get("public_id"))
                if row_dict.get("public_id")
                else None,
            },
        )

    conn.commit()
    return DevTask.from_row(row_dict)


def get_task(conn, task_id: DevTaskId) -> Optional[DevTask]:
    """
    Возвращает DevTask по числовому id или None.

    task_id — целое число (bigint в dev.dev_task).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                public_id,
                created_at,
                updated_at,
                status,
                source,
                stack,
                title,
                input_spec,
                result_spec,
                error,
                links
            FROM dev.dev_task
            WHERE id = %s
            """,
            (task_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        row_dict = _row_to_dict(cur, row)
    return DevTask.from_row(row_dict)


def fetch_next_task_for_stack(conn, stack: str) -> Optional[DevTask]:
    """
    Базовый диспетчер: берём следующую new-задачу для нужного стека.
    В реальности можно усложнить (приоритеты, шардирование и т.д.).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                public_id,
                created_at,
                updated_at,
                status,
                source,
                stack,
                title,
                input_spec,
                result_spec,
                error,
                links
            FROM dev.dev_task
            WHERE status = 'new' AND stack = %s
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
            (stack,),
        )
        row = cur.fetchone()
        if not row:
            return None
        row_dict = _row_to_dict(cur, row)

        # помечаем как in_progress
        cur.execute(
            """
            UPDATE dev.dev_task
            SET status = 'in_progress', updated_at = now()
            WHERE id = %s
            """,
            (row_dict["id"],),
        )

        _insert_event(
            conn,
            event_type="task_taken",
            correlation_id=str(row_dict["id"]),
            payload={
                "stack": row_dict["stack"],
                "title": row_dict.get("title"),
                "status": "in_progress",
                "public_id": str(row_dict.get("public_id"))
                if row_dict.get("public_id")
                else None,
            },
        )

    conn.commit()
    return DevTask.from_row(row_dict)


def save_result(
    conn,
    *,
    task_id: DevTaskId,
    result_spec: Dict[str, Any],
    status: DevTaskStatus = "done",
    error: Optional[str] = None,
) -> None:
    """
    Сохраняет результат выполнения задачи и пишет событие task_result.

    task_id — тот же bigint, который лежит в dev.dev_task.id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dev.dev_task
            SET result_spec = %s::jsonb,
                status = %s,
                error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (json.dumps(result_spec), status, error, task_id),
        )

        _insert_event(
            conn,
            event_type="task_result",
            correlation_id=str(task_id),
            payload={
                "status": status,
                "error": error,
                "result_spec": result_spec,
            },
        )

    conn.commit()


def update_input_spec(
    conn,
    *,
    task_id: DevTaskId,
    input_spec: Dict[str, Any],
) -> None:
    """
    Обновляет input_spec задачи DevFactory целиком.

    Используется, в частности, для записи результатов Question Engine
    в input_spec["questions"], Intent Parser — в input_spec["intent"], и т.п.

    NDC-принцип: не трогаем другие поля dev.dev_task, только input_spec/updated_at.
    """
    payload = json.dumps(input_spec)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dev.dev_task
               SET input_spec = %s::jsonb,
                   updated_at = now()
             WHERE id = %s
            """,
            (payload, task_id),
        )

        _insert_event(
            conn,
            event_type="task_input_spec_updated",
            correlation_id=str(task_id),
            payload={
                "task_id": task_id,
                "input_spec_keys": list(input_spec.keys()),
            },
        )

    conn.commit()
