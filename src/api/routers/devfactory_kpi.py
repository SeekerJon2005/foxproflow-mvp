"""
DevFactory KPI API router.

Endpoint: GET /api/devfactory/kpi/tasks
Источник данных: analytics.devfactory_task_kpi_v2

Назначение:
- читать агрегированные KPI задач DevFactory из витрины analytics.devfactory_task_kpi_v2;
- отдавать список объектов (project_ref, stack, total_tasks, new_tasks, done_tasks,
  failed_tasks, last_created_at, last_updated_at, avg_duration_sec) в формате JSON;
- использоваться Operator UI / DevFactory Studio для мониторинга состояния DevFactory.
"""

from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, List, Optional

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text  # type: ignore
from sqlalchemy.orm import Session, sessionmaker

from api.security.flowsec_middleware import require_policies

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB helper: используем тот же DATABASE_URL, что и в DevOrders / FlowSec.
# Для простоты: обычный sync SQLAlchemy Session поверх того же DSN.
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:admin@postgres:5432/foxproflow",
)

# sync engine для чтения витрины KPI (это лёгкий SELECT)
_sync_engine = create_engine(DATABASE_URL)
_SessionLocal = sessionmaker(bind=_sync_engine, autoflush=False, autocommit=False)


def get_db() -> AsyncIterator[Session]:
    """
    Зависимость FastAPI: выдаёт sync SQLAlchemy Session.
    Используем только для SELECT из витрины analytics.devfactory_task_kpi_v2.
    """
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pydantic-модель витрины KPI
# ---------------------------------------------------------------------------


class DevFactoryTaskKPI(BaseModel):
    """
    Строка витрины analytics.devfactory_task_kpi_v2.

    Поля совпадают с SELECT в этой витрине:
      - project_ref        — идентификатор проекта DevFactory (foxproflow-core,
                             logistics-pilot-001, devfactory-demo-001 и т.п.)
      - stack              — стек задачи (sql, sql-postgres, python_backend,
                             pwsh, docs, flowmeta и т.д.)
      - total_tasks        — всего задач по (project_ref, stack)
      - new_tasks          — задач в статусе new
      - done_tasks         — задач в статусе done
      - failed_tasks       — задач в статусе failed (на будущее)
      - last_created_at    — время последней созданной задачи
      - last_updated_at    — время последнего обновления любой задачи
      - avg_duration_sec   — средняя длительность (updated_at - created_at)
                             по задачам со статусом done
    """

    project_ref: str
    stack: str
    total_tasks: int
    new_tasks: int
    done_tasks: int
    failed_tasks: int
    last_created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    avg_duration_sec: Optional[float] = None

    class Config:
        orm_mode = True


# ВАЖНО по схеме:
# main.py включает этот роутер так:
#
#   devfactory_kpi_mod = importlib.import_module("api.routers.devfactory_kpi")
#   devfactory_kpi_router = getattr(devfactory_kpi_mod, "router", None)
#   app.include_router(devfactory_kpi_router, prefix="/api")
#
# Здесь prefix="/devfactory/kpi", общий "/api" добавляется в main.py.
# Итоговый путь: /api/devfactory/kpi/tasks
router = APIRouter(
    prefix="/devfactory/kpi",
    tags=["devfactory-kpi"],
    # FlowSec: для чтения KPI используем то же действие, что и для просмотра задач DevFactory:
    # devfactory:view_tasks.
    dependencies=[Depends(require_policies("devfactory", ["view_tasks"]))],
)


@router.get("/tasks", response_model=List[DevFactoryTaskKPI])
def get_devfactory_task_kpi(
    db: Session = Depends(get_db),
) -> List[DevFactoryTaskKPI]:
    """
    Вернуть агрегированные KPI по задачам DevFactory
    из витрины analytics.devfactory_task_kpi_v2.
    """
    try:
        result = db.execute(
            text(
                """
                SELECT
                    project_ref,
                    stack,
                    total_tasks,
                    new_tasks,
                    done_tasks,
                    failed_tasks,
                    last_created_at,
                    last_updated_at,
                    avg_duration_sec
                FROM analytics.devfactory_task_kpi_v2
                ORDER BY project_ref, stack
                """
            )
        )
    except Exception as exc:  # noqa: BLE001
        # Чёткая ошибка, чтобы Operator UI видел, что пошло не так.
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to fetch DevFactory KPI "
                "from analytics.devfactory_task_kpi_v2: "
                f"{exc}"
            ),
        ) from exc

    # SQLAlchemy 1.4/2.0: .mappings() даёт dict-подобные строки
    try:
        rows = result.mappings().all()
    except AttributeError:
        rows = result.fetchall()

    kpi_list: List[DevFactoryTaskKPI] = []
    for row in rows:
        data = dict(row)
        kpi_list.append(DevFactoryTaskKPI(**data))

    return kpi_list
