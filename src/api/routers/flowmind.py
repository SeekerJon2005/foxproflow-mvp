from __future__ import annotations

import json
from typing import List, Optional, Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Query

from src.core.pg_conn import _connect_pg
from src.core.flowmind.models import (
    FlowMindPlan,
    FlowMindAdvice,
    DevFactorySuggestion,
)

# prefix="/api/flowmind" + include_router(...) в main.py без доп. prefix
# дают итоговые пути:
#   /api/flowmind/plans
#   /api/flowmind/advice
#   /api/flowmind/devfactory-suggestions
router = APIRouter(
    prefix="/api/flowmind",
    tags=["flowmind"],
)


def _rows_as_dicts(cur) -> List[Dict[str, Any]]:
    """
    Универсальное преобразование строк курсора (psycopg2/psycopg3) в список dict.
    """
    desc = cur.description or []
    colnames = [getattr(d, "name", d[0]) for d in desc]
    rows = cur.fetchall()
    return [dict(zip(colnames, row)) for row in rows]


def _ensure_demo_plan_sync(conn) -> None:
    """
    FlowMind v0.1: если в flowmind.plan пусто — создаём один демонстрационный план,
    чтобы /api/flowmind/plans всегда что-то возвращал.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM flowmind.plan LIMIT 1")
        row = cur.fetchone()
        if row:
            return

        plan_id = uuid4()
        cur.execute(
            """
            INSERT INTO flowmind.plan (
                plan_id,
                status,
                domain,
                goal,
                context,
                plan_json,
                meta
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb
            )
            """,
            (
                str(plan_id),
                "draft",
                "devfactory",
                "Поднять FlowMind v0.1 и связать его с DevFactory.",
                '{"source":"flowmind.ensure_demo_plan","note":"Автоматически созданный план, чтобы FlowMind сразу начал дышать."}',
                r'{"plan":{"name":"flowmind.v0_1.bootstrap","goal":"Создать API и базовый reasoning для FlowMind.","domain":"devfactory","steps":["Реализовать модели FlowMind (plan/advice/snapshot).","Создать сервис FlowMind для чтения/записи планов и советов.","Создать API /api/flowmind/plans и /api/flowmind/advice.","Добавить вкладку FlowMind в DevFactory Operator UI."],"constraints":["Только чтение существующих витрин и таблиц.","Без ломающих миграций (NDC)."]}}',
                '{"version":"v0.1","created_by":"flowmind.bootstrap"}',
            ),
        )
    conn.commit()


def _refresh_devfactory_advice(conn) -> None:
    """
    FlowMind v0.1: анализ dev.dev_task и генерация советов в flowmind.advice.

    Стратегия:
      1) Чистим предыдущие советы, созданные анализатором v0.1
         (meta->>'source' = 'flowmind.devfactory_analyzer_v0_1').
      2) Добавляем советы по двум простым правилам:
         - есть упавшие задачи в DevFactory за последние 24 часа;
         - есть задачи со статусом 'new', которые висят > 24 часов.

    Важно:
      - В dev.dev_task id (bigint) остаётся внутренним тех.ключом.
      - Внешний стабильный идентификатор — public_id (uuid),
        именно его FlowMind использует как example_task_id.
    """

    with conn.cursor() as cur:
        # 1. Чистим старые советы этого анализатора
        cur.execute(
            """
            DELETE FROM flowmind.advice
            WHERE meta->>'source' = 'flowmind.devfactory_analyzer_v0_1'
            """
        )

        # 2. Упавшие задачи за последние 24 часа
        # Используем public_id::text как example_task_id для стабильного внешнего ID.
        cur.execute(
            """
            SELECT
                stack,
                COUNT(*) AS failed_count,
                MIN(public_id::text) AS example_task_id
            FROM dev.dev_task
            WHERE status = 'failed'
              AND created_at >= now() - interval '24 hours'
            GROUP BY stack
            """
        )
        failed_rows = _rows_as_dicts(cur)

        for row in failed_rows:
            stack = row.get("stack") or "unknown"
            failed_count = int(row.get("failed_count") or 0)
            example_task_id = row.get("example_task_id")

            summary = (
                f"В DevFactory есть {failed_count} упавших задач "
                f"(stack={stack}) за последние 24 часа."
            )
            details = {
                "metric": "failed_tasks_24h",
                "stack": stack,
                "failed_count": failed_count,
                "example_task_id": str(example_task_id) if example_task_id else None,
            }
            meta = {
                "source": "flowmind.devfactory_analyzer_v0_1",
                "category": "devfactory_health",
                "stack": stack,
            }

            cur.execute(
                """
                INSERT INTO flowmind.advice (
                    advice_id,
                    plan_id,
                    target_type,
                    target_ref,
                    severity,
                    status,
                    summary,
                    details,
                    meta
                )
                VALUES (
                    %s,
                    NULL,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb
                )
                """,
                (
                    str(uuid4()),
                    "devfactory_task",           # target_type
                    f"stack:{stack}",            # target_ref
                    "warning",                   # severity
                    "new",                       # status
                    summary,
                    json.dumps(details, ensure_ascii=False),
                    json.dumps(meta, ensure_ascii=False),
                ),
            )

        # 3. Застрявшие 'new' > 24 часов
        cur.execute(
            """
            SELECT
                stack,
                COUNT(*) AS stale_count,
                MIN(public_id::text) AS example_task_id
            FROM dev.dev_task
            WHERE status = 'new'
              AND created_at <= now() - interval '24 hours'
            GROUP BY stack
            """
        )
        stale_rows = _rows_as_dicts(cur)

        for row in stale_rows:
            stack = row.get("stack") or "unknown"
            stale_count = int(row.get("stale_count") or 0)
            example_task_id = row.get("example_task_id")

            summary = (
                f"В DevFactory есть {stale_count} задач в статусе 'new' "
                f"более 24 часов (stack={stack})."
            )
            details = {
                "metric": "stale_new_tasks_24h",
                "stack": stack,
                "stale_count": stale_count,
                "example_task_id": str(example_task_id) if example_task_id else None,
            }
            meta = {
                "source": "flowmind.devfactory_analyzer_v0_1",
                "category": "devfactory_health",
                "stack": stack,
            }

            cur.execute(
                """
                INSERT INTO flowmind.advice (
                    advice_id,
                    plan_id,
                    target_type,
                    target_ref,
                    severity,
                    status,
                    summary,
                    details,
                    meta
                )
                VALUES (
                    %s,
                    NULL,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb
                )
                """,
                (
                    str(uuid4()),
                    "devfactory_task",           # target_type
                    f"stack:{stack}",            # target_ref
                    "info",                      # severity
                    "new",                       # status
                    summary,
                    json.dumps(details, ensure_ascii=False),
                    json.dumps(meta, ensure_ascii=False),
                ),
            )

    conn.commit()


@router.get("/plans", response_model=List[FlowMindPlan])
def get_flowmind_plans(
    status: Optional[str] = Query(
        None,
        description="Фильтр по статусу плана (draft|active|completed|cancelled).",
    ),
    domain: Optional[str] = Query(
        None,
        description="Фильтр по домену (devfactory|logistics|crm|security|...).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Максимальное количество планов.",
    ),
) -> List[FlowMindPlan]:
    """
    Список планов FlowMind (синхронная версия, без AsyncSession).

    Для v0.1:
      - гарантируем наличие хотя бы одного демонстрационного плана;
      - читаем записи из flowmind.plan с фильтрами по status/domain.
    """
    conn = _connect_pg()
    try:
        _ensure_demo_plan_sync(conn)

        where_clauses = []
        params: List[Any] = []
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        if domain:
            where_clauses.append("domain = %s")
            params.append(domain)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    plan_id,
                    created_at,
                    updated_at,
                    status,
                    domain,
                    goal,
                    context,
                    plan_json,
                    meta
                FROM flowmind.plan
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            rows = _rows_as_dicts(cur)

        return [FlowMindPlan(**row) for row in rows]
    finally:
        conn.close()


@router.get("/advice", response_model=List[FlowMindAdvice])
def get_flowmind_advice(
    target_type: Optional[str] = Query(
        None,
        description=(
            "Фильтр по типу цели совета "
            "(devfactory_task|devfactory_order|tenant|domain|...)."
        ),
    ),
    target_ref: Optional[str] = Query(
        None,
        description=(
            "Фильтр по идентификатору цели "
            "(task_id, order_id, tenant_id и т.п.)."
        ),
    ),
    status: Optional[str] = Query(
        None,
        description="Фильтр по статусу совета (new|ack|dismissed).",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Максимальное количество советов.",
    ),
) -> List[FlowMindAdvice]:
    """
    Список советов FlowMind.

    v0.1: перед каждым запросом обновляем советы по DevFactory,
    чтобы /api/flowmind/advice отражал текущее состояние dev.dev_task.
    """
    conn = _connect_pg()
    try:
        _refresh_devfactory_advice(conn)

        where_clauses = []
        params: List[Any] = []
        if target_type:
            where_clauses.append("target_type = %s")
            params.append(target_type)
        if target_ref:
            where_clauses.append("target_ref = %s")
            params.append(target_ref)
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    advice_id,
                    created_at,
                    plan_id,
                    target_type,
                    target_ref,
                    severity,
                    status,
                    summary,
                    details,
                    meta
                FROM flowmind.advice
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            rows = _rows_as_dicts(cur)

        return [FlowMindAdvice(**row) for row in rows]
    finally:
        conn.close()


@router.get("/devfactory-suggestions", response_model=List[DevFactorySuggestion])
def get_flowmind_devfactory_suggestions(
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Максимальное количество предложений для DevFactory.",
    ),
) -> List[DevFactorySuggestion]:
    """
    Список предложений FlowMind для DevFactory.

    v0.1:
      - обновляем советы по DevFactory;
      - фильтруем только те, что target_type='devfactory_task';
      - упаковываем их в DevFactorySuggestion.
    """
    conn = _connect_pg()
    try:
        _refresh_devfactory_advice(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    advice_id,
                    created_at,
                    plan_id,
                    target_type,
                    target_ref,
                    severity,
                    status,
                    summary,
                    details,
                    meta
                FROM flowmind.advice
                WHERE target_type = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                ("devfactory_task", limit),
            )
            rows = _rows_as_dicts(cur)

        suggestions: List[DevFactorySuggestion] = []
        for row in rows:
            details = row.get("details") or {}
            meta = row.get("meta") or {}

            project_ref = meta.get("project_ref", "foxproflow-core")
            stack = meta.get("stack") or details.get("stack") or "unknown"
            title = row.get("summary", "")
            goal = details.get("goal") or title

            deliverables = details.get("deliverables") or []
            acceptance_criteria = details.get("acceptance_criteria") or []

            deliverables = [str(x) for x in deliverables]
            acceptance_criteria = [str(x) for x in acceptance_criteria]

            suggestions.append(
                DevFactorySuggestion(
                    project_ref=project_ref,
                    stack=stack,
                    title=title,
                    goal=goal,
                    deliverables=deliverables,
                    acceptance_criteria=acceptance_criteria,
                    context={
                        "advice_id": str(row.get("advice_id")),
                        "severity": row.get("severity"),
                        "status": row.get("status"),
                        "target_type": row.get("target_type"),
                        "target_ref": row.get("target_ref"),
                    },
                )
            )

        return suggestions
    finally:
        conn.close()
