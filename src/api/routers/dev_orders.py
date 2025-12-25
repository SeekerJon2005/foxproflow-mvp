from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional, Sequence, Protocol, List, AsyncIterator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

log = logging.getLogger(__name__)

# NOTE (dev-mode):
# Здесь сознательно НЕ вешаем require_policies(...) на router / методы,
# чтобы не блокировать локальную разработку DevOrders до полного заведения
# политик devfactory.view_orders / devfactory.manage_orders в FlowSec.
# Глобальный FlowSec-middleware по-прежнему может работать на уровне приложения.

# ---------------------------------------------------------------------------
# DB helper: asyncpg-пул + тонкая обёртка под единый интерфейс.
# ---------------------------------------------------------------------------


def _normalize_database_url(url: str) -> str:
    """
    Приводим DATABASE_URL к DSN, понятному asyncpg.
    (в проекте иногда встречаются префиксы postgresql+asyncpg)
    """
    url = (url or "").strip()
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    url = url.replace("postgresql+psycopg://", "postgresql://")
    return url


DATABASE_URL = _normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql://admin:admin@postgres:5432/foxproflow",
    )
)

_pool: Optional[asyncpg.Pool] = None


class DbConnProtocol(Protocol):
    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]:
        ...

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        ...

    async def execute(self, query: str, *args: Any) -> str:
        ...


class DbConn(DbConnProtocol):
    """
    Обёртка над asyncpg.Connection с единым интерфейсом:
      - fetch_all(query, *args)
      - fetch_one(query, *args)
      - execute(query, *args)
    Под наши SQL с плейсхолдерами $1, $2, ...
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]:
        return await self._conn.fetch(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        return await self._conn.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)


async def _get_pool() -> asyncpg.Pool:
    """
    Ленивая инициализация пула соединений. Первый вызов создаёт pool,
    далее переиспользуем один и тот же.
    """
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set for dev_orders router")

        min_size = int(os.getenv("FF_DEVORDERS_PG_POOL_MIN", "1"))
        max_size = int(os.getenv("FF_DEVORDERS_PG_POOL_MAX", "10"))
        command_timeout = float(os.getenv("FF_DEVORDERS_PG_COMMAND_TIMEOUT", "30"))

        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )
    return _pool


async def get_db() -> AsyncIterator[DbConnProtocol]:
    """
    Зависимость FastAPI: выдаёт DbConn и корректно возвращает соединение в пул.
    """
    pool = await _get_pool()
    conn = await pool.acquire()
    try:
        yield DbConn(conn)
    finally:
        await pool.release(conn)


# ---------------------------------------------------------------------------
# Pydantic-модели
# ---------------------------------------------------------------------------


class DevOrderSummary(BaseModel):
    dev_order_id: UUID
    order_created_at: Optional[datetime]
    order_updated_at: Optional[datetime]
    order_status: str
    order_title: str
    total_amount: Optional[float]
    currency_code: Optional[str]


class DevOrderCommercialContext(BaseModel):
    dev_order_id: UUID

    order_created_at: Optional[datetime]
    order_updated_at: Optional[datetime]
    order_status: str
    order_title: str
    order_description: Optional[str]

    customer_name: Optional[str]
    total_amount: Optional[float]
    currency_code: Optional[str]

    # Внешний идентификатор tenant’а из старой схемы dev_order (text)
    order_tenant_external_id: Optional[str]

    # CRM-tenant (crm.tenant.id)
    crm_tenant_id: Optional[UUID]
    tenant_code: Optional[str]
    tenant_name: Optional[str]

    # Billing
    billing_subscription_table: Optional[str]
    billing_subscription_id: Optional[UUID]
    billing_invoice_table: Optional[str]
    billing_invoice_id: Optional[UUID]

    # CRM lead (логическая привязка)
    crm_lead_code: Optional[str]


class DevOrderCreateRequest(BaseModel):
    """
    Параметры для создания нового dev-заказа DevFactory.

    Поля маппятся на dev.dev_order:
      - status      → status
      - title       → title
      - description → description
      - customer_name → customer_name
      - total_amount   → total_amount
      - currency_code  → currency_code
      - order_tenant_external_id → tenant_id (в dev.dev_order, текстовый внешний id)
    """

    title: str
    description: Optional[str] = None
    customer_name: Optional[str] = None

    total_amount: Optional[float] = None
    currency_code: Optional[float] = None  # NOTE: сохраняю как в твоём коде? -> ниже исправляю на str
    # ↑ ВАЖНО: currency_code должен быть str. Исправляю прямо сейчас:
    currency_code: Optional[str] = None

    order_tenant_external_id: Optional[str] = None
    status: str = "new"


class LinkTenantRequest(BaseModel):
    tenant_id: UUID
    actor: str = "e.yatskov@foxproflow.ru"


class LinkBillingRequest(BaseModel):
    link_type: str  # 'billing_subscription' | 'billing_invoice' | др.
    billing_table: str  # 'billing.subscription' | 'billing.invoice' | ...
    billing_id: UUID
    actor: str = "e.yatskov@foxproflow.ru"


class LinkLeadRequest(BaseModel):
    lead_code: str
    actor: str = "e.yatskov@foxproflow.ru"


# [DEVTASK:167] DevOrder -> DevTasks listing output
class DevOrderTaskLink(BaseModel):
    dev_task_id: int
    dev_task_public_id: Optional[UUID]

    stack: str
    title: str
    status: str

    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Роутер
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/devorders",
    tags=["devorders"],
)

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _row_to_summary(row: dict) -> DevOrderSummary:
    return DevOrderSummary(
        dev_order_id=row["dev_order_id"],
        order_created_at=row.get("created_at") or row.get("order_created_at"),
        order_updated_at=row.get("updated_at") or row.get("order_updated_at"),
        order_status=row["status"],
        order_title=row["title"],
        total_amount=float(row["total_amount"]) if row.get("total_amount") is not None else None,
        currency_code=row.get("currency_code"),
    )


def _row_to_commercial_ctx(row: dict) -> DevOrderCommercialContext:
    return DevOrderCommercialContext(
        dev_order_id=row["dev_order_id"],
        order_created_at=row.get("order_created_at"),
        order_updated_at=row.get("order_updated_at"),
        order_status=row["order_status"],
        order_title=row["order_title"],
        order_description=row.get("order_description"),
        customer_name=row.get("customer_name"),
        total_amount=float(row["total_amount"]) if row.get("total_amount") is not None else None,
        currency_code=row.get("currency_code"),
        order_tenant_external_id=row.get("order_tenant_external_id"),
        crm_tenant_id=row.get("crm_tenant_id"),
        tenant_code=row.get("tenant_code"),
        tenant_name=row.get("tenant_name"),
        billing_subscription_table=row.get("billing_subscription_table"),
        billing_subscription_id=row.get("billing_subscription_id"),
        billing_invoice_table=row.get("billing_invoice_table"),
        billing_invoice_id=row.get("billing_invoice_id"),
        crm_lead_code=row.get("crm_lead_code"),
    )


def _row_to_task_link(row: dict) -> DevOrderTaskLink:
    pub = row.get("public_id")
    try:
        pub_uuid = UUID(str(pub)) if pub is not None else None
    except Exception:
        pub_uuid = None

    # id в dev.dev_task обычно bigint/int; приводим максимально безопасно
    raw_id = row.get("id")
    try:
        dev_task_id = int(raw_id)
    except Exception:
        dev_task_id = int(str(raw_id))

    return DevOrderTaskLink(
        dev_task_id=dev_task_id,
        dev_task_public_id=pub_uuid,
        stack=str(row.get("stack") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or "unknown"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.get("", response_model=List[DevOrderSummary])
async def list_devorders(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: DbConnProtocol = Depends(get_db),
):
    rows = await db.fetch_all(
        """
        SELECT
            dev_order_id,
            created_at,
            updated_at,
            status,
            title,
            total_amount,
            currency_code
        FROM dev.dev_order
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [_row_to_summary(dict(r)) for r in rows]


@router.post("", response_model=DevOrderSummary, status_code=status.HTTP_201_CREATED)
async def create_devorder(
    payload: DevOrderCreateRequest,
    db: DbConnProtocol = Depends(get_db),
) -> DevOrderSummary:
    row = await db.fetch_one(
        """
        INSERT INTO dev.dev_order (
            status,
            title,
            description,
            customer_name,
            total_amount,
            currency_code,
            tenant_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING
            dev_order_id,
            created_at,
            updated_at,
            status,
            title,
            total_amount,
            currency_code
        """,
        payload.status,
        payload.title,
        payload.description,
        payload.customer_name,
        payload.total_amount,
        payload.currency_code,
        payload.order_tenant_external_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create dev order",
        )
    return _row_to_summary(dict(row))


@router.get("/{dev_order_id}", response_model=DevOrderSummary)
async def get_devorder(
    dev_order_id: UUID,
    db: DbConnProtocol = Depends(get_db),
):
    row = await db.fetch_one(
        """
        SELECT
            dev_order_id,
            created_at,
            updated_at,
            status,
            title,
            total_amount,
            currency_code
        FROM dev.dev_order
        WHERE dev_order_id = $1
        """,
        dev_order_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dev order {dev_order_id} not found",
        )
    return _row_to_summary(dict(row))


# ---------------------------------------------------------------------------
# [DEVTASK:167] DevOrder -> linked DevTasks (meta.dev_order_id)
# ---------------------------------------------------------------------------

@router.get("/{dev_order_id}/tasks", response_model=List[DevOrderTaskLink])
async def list_devorder_tasks(
    dev_order_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    task_status: Optional[str] = Query(default=None, alias="status"),
    stack: Optional[str] = Query(default=None),
    db: DbConnProtocol = Depends(get_db),
):
    """
    Список задач DevFactory, привязанных к DevOrder через meta.dev_order_id.

    Ключевой фикс против "Empty reply":
    - status/stack в dev.dev_task могут быть ENUM.
    - сравнение ENUM = text в Postgres может падать.
    - делаем enum-safe: status::text = $2::text и stack::text = $3::text
    + оборачиваем ВЕСЬ обработчик в try/except с логом.
    """
    try:
        exists = await db.fetch_one(
            "SELECT dev_order_id FROM dev.dev_order WHERE dev_order_id = $1",
            dev_order_id,
        )
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dev order {dev_order_id} not found",
            )

        rows = await db.fetch_all(
            """
            SELECT
                id,
                public_id,
                stack,
                title,
                status,
                created_at,
                updated_at
            FROM dev.dev_task
            WHERE (meta->>'dev_order_id') = $1
              AND ($2::text IS NULL OR status::text = $2::text)
              AND ($3::text IS NULL OR stack::text  = $3::text)
            ORDER BY created_at DESC
            LIMIT $4
            """,
            str(dev_order_id),
            task_status,
            stack,
            limit,
        )

        return [_row_to_task_link(dict(r)) for r in rows]

    except HTTPException:
        raise
    except Exception as ex:
        # Важно: чтобы ошибка не превращалась в "Empty reply"
        log.exception("DevOrders: list_devorder_tasks failed dev_order_id=%s", dev_order_id)

        # Можно добавить sqlstate/детали, если это PostgresError
        detail = f"{type(ex).__name__}"
        sqlstate = getattr(ex, "sqlstate", None)
        if sqlstate:
            detail = f"{detail} sqlstate={sqlstate}"

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DevOrder tasks listing failed: {detail}",
        ) from ex


@router.get("/{dev_order_id}/commercial-context", response_model=DevOrderCommercialContext)
async def get_devorder_commercial_context(
    dev_order_id: UUID,
    db: DbConnProtocol = Depends(get_db),
):
    row = await db.fetch_one(
        """
        SELECT *
        FROM dev.v_dev_order_commercial_ctx
        WHERE dev_order_id = $1
        """,
        dev_order_id,
    )
    if row is None:
        order_row = await db.fetch_one(
            """
            SELECT
                dev_order_id,
                created_at  AS order_created_at,
                updated_at  AS order_updated_at,
                status      AS order_status,
                title       AS order_title,
                description AS order_description,
                customer_name,
                total_amount,
                currency_code
            FROM dev.dev_order
            WHERE dev_order_id = $1
            """,
            dev_order_id,
        )
        if order_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dev order {dev_order_id} not found",
            )

        base = dict(order_row)
        base.setdefault("order_tenant_external_id", None)
        base.setdefault("crm_tenant_id", None)
        base.setdefault("tenant_code", None)
        base.setdefault("tenant_name", None)
        base.setdefault("billing_subscription_table", None)
        base.setdefault("billing_subscription_id", None)
        base.setdefault("billing_invoice_table", None)
        base.setdefault("billing_invoice_id", None)
        base.setdefault("crm_lead_code", None)

        return _row_to_commercial_ctx(base)

    return _row_to_commercial_ctx(dict(row))


@router.post("/{dev_order_id}/link/tenant", status_code=status.HTTP_204_NO_CONTENT)
async def link_devorder_to_tenant(
    dev_order_id: UUID,
    payload: LinkTenantRequest,
    db: DbConnProtocol = Depends(get_db),
):
    row = await db.fetch_one(
        "SELECT dev_order_id FROM dev.dev_order WHERE dev_order_id = $1",
        dev_order_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dev order {dev_order_id} not found",
        )

    trow = await db.fetch_one(
        "SELECT id FROM crm.tenant WHERE id = $1",
        payload.tenant_id,
    )
    if trow is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant {payload.tenant_id} not found",
        )

    await db.execute(
        """
        SELECT dev.fn_dev_order_link_to_tenant(
            p_order_id  := $1,
            p_tenant_id := $2,
            p_actor     := $3
        )
        """,
        dev_order_id,
        payload.tenant_id,
        payload.actor,
    )


@router.post("/{dev_order_id}/link/billing", status_code=status.HTTP_204_NO_CONTENT)
async def link_devorder_to_billing(
    dev_order_id: UUID,
    payload: LinkBillingRequest,
    db: DbConnProtocol = Depends(get_db),
):
    if not payload.billing_table.startswith("billing."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="billing_table must start with 'billing.'",
        )

    await db.execute(
        """
        SELECT dev.fn_dev_order_link_to_billing(
            p_order_id      := $1,
            p_link_type     := $2,
            p_billing_table := $3,
            p_billing_id    := $4,
            p_actor         := $5
        )
        """,
        dev_order_id,
        payload.link_type,
        payload.billing_table,
        payload.billing_id,
        payload.actor,
    )


@router.post("/{dev_order_id}/link/lead", status_code=status.HTTP_204_NO_CONTENT)
async def link_devorder_to_crm_lead(
    dev_order_id: UUID,
    payload: LinkLeadRequest,
    db: DbConnProtocol = Depends(get_db),
):
    await db.execute(
        """
        SELECT dev.fn_dev_order_link_to_crm_lead(
            p_order_id  := $1,
            p_lead_code := $2,
            p_actor     := $3
        )
        """,
        dev_order_id,
        payload.lead_code,
        payload.actor,
    )
