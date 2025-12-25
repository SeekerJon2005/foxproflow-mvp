from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FlowMindPlan, FlowMindAdvice, DevFactorySuggestion


async def ensure_demo_plan(db: AsyncSession) -> None:
    """
    Для v0.1: если в flowmind.plan пусто — создаём один демонстрационный план
    по DevFactory, чтобы API сразу что-то отдавал.
    """
    result = await db.execute(text("SELECT 1 FROM flowmind.plan LIMIT 1"))
    row = result.first()
    if row is not None:
        return

    plan_id = uuid.uuid4()

    demo_plan = {
        "plan_id": plan_id,
        "status": "draft",
        "domain": "devfactory",
        "goal": "Поднять FlowMind v0.1 и связать его с DevFactory.",
        "context": {
            "source": "flowmind.ensure_demo_plan",
            "note": "Автоматически созданный план, чтобы FlowMind сразу начал дышать.",
        },
        "plan_json": {
            "plan": {
                "name": "flowmind.v0_1.bootstrap",
                "goal": "Создать API и базовый reasoning для FlowMind.",
                "domain": "devfactory",
                "steps": [
                    "Реализовать модели FlowMind (plan/advice/snapshot).",
                    "Создать сервис FlowMind для чтения/записи планов и советов.",
                    "Создать API /api/flowmind/plans и /api/flowmind/advice.",
                    "Добавить вкладку FlowMind в DevFactory Operator UI.",
                ],
                "constraints": [
                    "Только чтение существующих витрин и таблиц.",
                    "Без ломающих миграций (NDC).",
                ],
            }
        },
        "meta": {
            "version": "v0.1",
            "created_by": "flowmind.bootstrap",
        },
    }

    await db.execute(
        text(
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
                :plan_id,
                :status,
                :domain,
                :goal,
                :context::jsonb,
                :plan_json::jsonb,
                :meta::jsonb
            )
            """
        ),
        {
            "plan_id": str(demo_plan["plan_id"]),
            "status": demo_plan["status"],
            "domain": demo_plan["domain"],
            "goal": demo_plan["goal"],
            "context": json.dumps(demo_plan["context"]),
            "plan_json": json.dumps(demo_plan["plan_json"]),
            "meta": json.dumps(demo_plan["meta"]),
        },
    )
    await db.commit()


async def list_plans(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 100,
) -> List[FlowMindPlan]:
    query = """
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
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}

    if status:
        query += " AND status = :status"
        params["status"] = status

    if domain:
        query += " AND domain = :domain"
        params["domain"] = domain

    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.mappings().all()
    return [FlowMindPlan(**row) for row in rows]


async def list_advice(
    db: AsyncSession,
    *,
    target_type: Optional[str] = None,
    target_ref: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[FlowMindAdvice]:
    query = """
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
        WHERE 1 = 1
    """
    params: dict[str, Any] = {}

    if target_type:
        query += " AND target_type = :target_type"
        params["target_type"] = target_type

    if target_ref:
        query += " AND target_ref = :target_ref"
        params["target_ref"] = target_ref

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.mappings().all()
    return [FlowMindAdvice(**row) for row in rows]


async def list_devfactory_suggestions(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> List[DevFactorySuggestion]:
    """
    v0.1: простое отображение советов, которые относятся к DevFactory,
    в более дружественный формат для Operator UI.
    В будущем сюда приедет реальное reasoning по KPI DevFactory.
    """

    # Берём только советы по DevFactory
    advice_rows = await list_advice(
        db,
        target_type="devfactory_task",
        limit=limit,
    )

    suggestions: List[DevFactorySuggestion] = []

    for adv in advice_rows:
        project_ref = adv.meta.get("project_ref", "foxproflow-core")
        stack = adv.meta.get("stack", "sql-postgres")
        title = adv.summary
        goal = adv.details.get("goal") or adv.summary

        deliverables = adv.details.get("deliverables") or []
        acceptance_criteria = adv.details.get("acceptance_criteria") or []

        # Гарантируем, что это списки строк
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
                    "advice_id": str(adv.advice_id),
                    "severity": adv.severity,
                    "status": adv.status,
                    "target_type": adv.target_type,
                    "target_ref": adv.target_ref,
                },
            )
        )

    return suggestions
