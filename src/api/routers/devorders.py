# -*- coding: utf-8 -*-
# file: src/api/routers/devorders.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.security.flowsec_middleware import require_policies


def _connect_pg():
    """
    Локальный helper подключения к Postgres для DevOrders API.

    Используем те же настройки, что и Invoke-FFSql.ps1:
      - сервис postgres
      - БД foxproflow
      - пользователь admin
    """
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore

        return psycopg.connect(dsn)


router = APIRouter(
    prefix="/devorders",
    tags=["devorders"],
    # Для чтения достаточно devfactory:view_tasks (как у DevFactory)
    dependencies=[Depends(require_policies("devfactory", ["view_tasks"]))],
)


# ---------------------------------------------------------------------------
#  Pydantic-модели
# ---------------------------------------------------------------------------


class DevOrderCreate(BaseModel):
    """Создание DevOrder (то, что отправляет DevOrders Console)."""

    title: str = Field(..., description="Заголовок заказа")
    description: Optional[str] = Field(None, description="Описание заказа")
    customer_name: Optional[str] = Field(None, description="Имя клиента")
    order_tenant_external_id: Optional[str] = Field(
        None, description="Внешний tenant_id (строковый идентификатор клиента)"
    )
    total_amount: Optional[float] = Field(None, description="Сумма заказа")
    currency_code: Optional[str] = Field(None, description="Код валюты (RUB/EUR/...)")
    status: Optional[str] = Field("new", description="Статус заказа")


class DevOrderSummary(BaseModel):
    """Краткое представление DevOrder для списка и деталки."""

    dev_order_id: str
    dev_order_public_id: str
    order_title: Optional[str]
    order_description: Optional[str]
    customer_name: Optional[str]
    order_tenant_external_id: Optional[str]
    total_amount: Optional[float]
    currency_code: Optional[str]
    order_status: str
    order_created_at: Optional[str]
    order_updated_at: Optional[str]

    # CRM-срез
    crm_tenant_table: Optional[str] = None
    crm_tenant_id: Optional[str] = None
    crm_lead_code: Optional[str] = None

    # billing-срез (для UI/KPI)
    billing_subscription_table: Optional[str] = None
    billing_subscription_id: Optional[str] = None
    billing_invoice_table: Optional[str] = None
    billing_invoice_id: Optional[str] = None


class DevOrderCommercialContext(BaseModel):
    """Полный коммерческий контекст DevOrder (из v_dev_order_commercial_ctx)."""

    dev_order_id: str
    dev_order_public_id: str
    order_title: Optional[str]
    order_description: Optional[str]
    customer_name: Optional[str]
    order_tenant_external_id: Optional[str]
    total_amount: Optional[float]
    currency_code: Optional[str]
    order_status: str
    order_created_at: Optional[str]
    order_updated_at: Optional[str]

    crm_tenant_table: Optional[str]
    crm_tenant_id: Optional[str]

    billing_subscription_table: Optional[str]
    billing_subscription_id: Optional[str]

    billing_invoice_table: Optional[str]
    billing_invoice_id: Optional[str]

    crm_lead_code: Optional[str]


class DevOrderLinkTenantIn(BaseModel):
    tenant_id: str = Field(..., description="UUID crm.tenant.id")


class DevOrderLinkBillingIn(BaseModel):
    link_type: str = Field(..., description="billing_subscription | billing_invoice")
    billing_table: Optional[str] = Field(
        None, description="Имя таблицы billing.subscription / billing.invoice"
    )
    billing_id: str = Field(..., description="UUID или внешний ID записи в billing.*")


class DevOrderLinkLeadIn(BaseModel):
    lead_code: str = Field(..., description="Код лида в CRM (строка)")


class DevOrderBootstrapIn(BaseModel):
    """Запрос на бутстрап DevFactory-задач под DevOrder."""

    plan_domain: Optional[str] = Field(
        None,
        description=(
            "Домен FlowMind-плана (по умолчанию devfactory/preflight/week01). "
            "Кладётся в meta.plan_domain у задач."
        ),
    )
    dry_run: bool = Field(
        False,
        description=(
            "Если true — задачи не создаются в dev.dev_task, "
            "а только возвращаются как рекомендованный список."
        ),
    )


class DevOrderBootstrapTaskOut(BaseModel):
    """Результат bootstrap-а DevFactory-задач под DevOrder."""

    dev_task_id: Optional[int] = Field(
        None, description="ID dev.dev_task, если задача создана"
    )
    dev_task_public_id: Optional[str] = Field(
        None, description="public_id dev.dev_task, если есть"
    )
    stack: str = Field(..., description="Стек задачи DevFactory (devfactory.*)")
    title: str = Field(..., description="Заголовок задачи")
    status: str = Field(..., description="Статус задачи (обычно new)")
    created_at: Optional[str] = Field(
        None,
        description="Время создания задачи в dev.dev_task, если задача создана",
    )


class DevOrderStatusUpdate(BaseModel):
    """Изменение статуса DevOrder."""

    dev_order_id: str = Field(..., description="UUID dev.dev_order.dev_order_id")
    status: str = Field(
        ...,
        description="Новый статус заказа (new | in_progress | done | error)",
    )


# ---------------------------------------------------------------------------
#  Хелперы
# ---------------------------------------------------------------------------


def _ensure_order_exists(conn, dev_order_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM dev.dev_order WHERE dev_order_id = %s",
            (dev_order_id,),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="DevOrder not found")


def _row_to_summary(row: Any) -> DevOrderSummary:
    """
    Маппинг строк из v_dev_order_commercial_ctx в DevOrderSummary.

    Ожидаемый порядок колонок в SELECT:
      0  dev_order_id
      1  dev_order_public_id
      2  order_title
      3  order_description
      4  customer_name
      5  order_tenant_external_id
      6  total_amount
      7  currency_code
      8  order_status
      9  order_created_at
      10 order_updated_at
      11 crm_tenant_table
      12 crm_tenant_id
      13 billing_subscription_table
      14 billing_subscription_id
      15 billing_invoice_table
      16 billing_invoice_id
      17 crm_lead_code
    """
    return DevOrderSummary(
        dev_order_id=str(row[0]),
        dev_order_public_id=str(row[1]),
        order_title=row[2],
        order_description=row[3],
        customer_name=row[4],
        order_tenant_external_id=row[5],
        total_amount=float(row[6]) if row[6] is not None else None,
        currency_code=row[7],
        order_status=row[8],
        order_created_at=str(row[9]) if row[9] is not None else None,
        order_updated_at=str(row[10]) if row[10] is not None else None,
        crm_tenant_table=row[11],
        crm_tenant_id=str(row[12]) if row[12] is not None else None,
        billing_subscription_table=row[13],
        billing_subscription_id=row[14],
        billing_invoice_table=row[15],
        billing_invoice_id=row[16],
        crm_lead_code=row[17],
    )


def _row_to_context(row: Any) -> DevOrderCommercialContext:
    """
    Маппинг полной строки v_dev_order_commercial_ctx в DevOrderCommercialContext.
    """
    return DevOrderCommercialContext(
        dev_order_id=str(row[0]),
        dev_order_public_id=str(row[1]),
        order_title=row[2],
        order_description=row[3],
        customer_name=row[4],
        order_tenant_external_id=row[5],
        total_amount=float(row[6]) if row[6] is not None else None,
        currency_code=row[7],
        order_status=row[8],
        order_created_at=str(row[9]) if row[9] is not None else None,
        order_updated_at=str(row[10]) if row[10] is not None else None,
        crm_tenant_table=row[11],
        crm_tenant_id=str(row[12]) if row[12] is not None else None,
        billing_subscription_table=row[13],
        billing_subscription_id=row[14],
        billing_invoice_table=row[15],
        billing_invoice_id=row[16],
        crm_lead_code=row[17],
    )


# ---------------------------------------------------------------------------
#  Эндпоинты DevOrders
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DevOrderSummary,
    summary="Создать DevOrder (dev.dev_order)",
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def create_dev_order(body: DevOrderCreate) -> DevOrderSummary:
    """
    Создать DevOrder и вернуть его состояние из v_dev_order_commercial_ctx,
    чтобы сразу получить billing/CRM-поля и коммерческий контекст.
    """
    conn = _connect_pg()
    try:
        status = body.status or "new"
        dev_order_id: Optional[str] = None

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dev.dev_order (
                    title,
                    description,
                    customer_name,
                    order_tenant_external_id,
                    tenant_id,
                    total_amount,
                    currency_code,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING dev_order_id
                """,
                (
                    body.title,
                    body.description,
                    body.customer_name,
                    body.order_tenant_external_id,
                    body.order_tenant_external_id,  # tenant_id = внешний tenant
                    body.total_amount,
                    body.currency_code,
                    status,
                ),
            )
            dev_order_id = str(cur.fetchone()[0])

            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    order_description,
                    customer_name,
                    order_tenant_external_id,
                    total_amount,
                    currency_code,
                    order_status,
                    order_created_at,
                    order_updated_at,
                    crm_tenant_table,
                    crm_tenant_id,
                    billing_subscription_table,
                    billing_subscription_id,
                    billing_invoice_table,
                    billing_invoice_id,
                    crm_lead_code
                FROM dev.v_dev_order_commercial_ctx
                WHERE dev_order_id = %s
                """,
                (dev_order_id,),
            )
            row = cur.fetchone()

        conn.commit()

        if row is None:
            raise HTTPException(status_code=500, detail="DevOrder created, but context not found")

        return _row_to_summary(row)
    finally:
        conn.close()


@router.get(
    "",
    response_model=List[DevOrderSummary],
    summary="Список DevOrders (из v_dev_order_commercial_ctx)",
)
def list_dev_orders(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[DevOrderSummary]:
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    order_description,
                    customer_name,
                    order_tenant_external_id,
                    total_amount,
                    currency_code,
                    order_status,
                    order_created_at,
                    order_updated_at,
                    crm_tenant_table,
                    crm_tenant_id,
                    billing_subscription_table,
                    billing_subscription_id,
                    billing_invoice_table,
                    billing_invoice_id,
                    crm_lead_code
                FROM dev.v_dev_order_commercial_ctx
                ORDER BY order_created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()

        return [_row_to_summary(r) for r in rows]
    finally:
        conn.close()


@router.get(
    "/{dev_order_id}",
    response_model=DevOrderSummary,
    summary="Получить DevOrder по dev_order_id",
)
def get_dev_order(dev_order_id: str) -> DevOrderSummary:
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    order_description,
                    customer_name,
                    order_tenant_external_id,
                    total_amount,
                    currency_code,
                    order_status,
                    order_created_at,
                    order_updated_at,
                    crm_tenant_table,
                    crm_tenant_id,
                    billing_subscription_table,
                    billing_subscription_id,
                    billing_invoice_table,
                    billing_invoice_id,
                    crm_lead_code
                FROM dev.v_dev_order_commercial_ctx
                WHERE dev_order_id = %s
                """,
                (dev_order_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="DevOrder not found")

        return _row_to_summary(row)
    finally:
        conn.close()


@router.get(
    "/{dev_order_id}/commercial-context",
    response_model=DevOrderCommercialContext,
    summary="Коммерческий контекст DevOrder (tenant/billing/lead)",
)
def get_dev_order_context(dev_order_id: str) -> DevOrderCommercialContext:
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    order_description,
                    customer_name,
                    order_tenant_external_id,
                    total_amount,
                    currency_code,
                    order_status,
                    order_created_at,
                    order_updated_at,
                    crm_tenant_table,
                    crm_tenant_id,
                    billing_subscription_table,
                    billing_subscription_id,
                    billing_invoice_table,
                    billing_invoice_id,
                    crm_lead_code
                FROM dev.v_dev_order_commercial_ctx
                WHERE dev_order_id = %s
                """,
                (dev_order_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="DevOrder not found")

        return _row_to_context(row)
    finally:
        conn.close()


@router.post(
    "/status",
    summary="Изменить статус DevOrder",
    response_model=DevOrderSummary,
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def update_dev_order_status(body: DevOrderStatusUpdate) -> DevOrderSummary:
    """
    Обновить статус DevOrder (new / in_progress / done / error) и вернуть обновлённый summary.
    """
    allowed_statuses = {"new", "in_progress", "done", "error"}
    new_status = (body.status or "").strip()
    dev_order_id = body.dev_order_id

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{new_status}', allowed: {', '.join(sorted(allowed_statuses))}",
        )

    conn = _connect_pg()
    try:
        _ensure_order_exists(conn, dev_order_id)

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dev.dev_order
                SET status = %s,
                    updated_at = now()
                WHERE dev_order_id = %s
                """,
                (new_status, dev_order_id),
            )

            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    order_description,
                    customer_name,
                    order_tenant_external_id,
                    total_amount,
                    currency_code,
                    order_status,
                    order_created_at,
                    order_updated_at,
                    crm_tenant_table,
                    crm_tenant_id,
                    billing_subscription_table,
                    billing_subscription_id,
                    billing_invoice_table,
                    billing_invoice_id,
                    crm_lead_code
                FROM dev.v_dev_order_commercial_ctx
                WHERE dev_order_id = %s
                """,
                (dev_order_id,),
            )
            row = cur.fetchone()

        conn.commit()

        if row is None:
            raise HTTPException(status_code=500, detail="DevOrder updated, but context not found")

        return _row_to_summary(row)
    finally:
        conn.close()


@router.post(
    "/{dev_order_id}/bootstrap-tasks",
    response_model=List[DevOrderBootstrapTaskOut],
    summary="Создать базовый набор DevFactory-задач под DevOrder",
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def bootstrap_dev_tasks_for_order(
    dev_order_id: str,
    body: DevOrderBootstrapIn,
) -> List[DevOrderBootstrapTaskOut]:
    """
    Бутстрап набора dev.dev_task под конкретный DevOrder.

    Поведение:
      * если уже есть dev_task с meta->>'dev_order_id' = dev_order_id и dry_run = false —
        возвращает их как есть, новых не создаёт (идемпотентность);
      * если dry_run = true — возвращает шаблон задач, не создавая записей в dev.dev_task.
    """
    plan_domain = body.plan_domain or "devfactory/preflight/week01"
    dry_run = bool(body.dry_run)

    conn = _connect_pg()
    try:
        _ensure_order_exists(conn, dev_order_id)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dev_order_id,
                    dev_order_public_id,
                    order_title,
                    customer_name,
                    order_tenant_external_id
                FROM dev.v_dev_order_commercial_ctx
                WHERE dev_order_id = %s
                """,
                (dev_order_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="DevOrder not found")

        dev_order_uuid = str(row[0])
        dev_order_public_id = str(row[1])
        order_title = row[2]
        customer_name = row[3]
        tenant_external_id = row[4]

        base_title = order_title or f"DevOrder {dev_order_public_id}"

        existing: List[DevOrderBootstrapTaskOut] = []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, public_id, stack, title, status, created_at
                FROM dev.dev_task
                WHERE meta->>'dev_order_id' = %s
                ORDER BY id
                """,
                (dev_order_uuid,),
            )
            for t_id, public_id, stack, title, status, created_at in cur.fetchall():
                existing.append(
                    DevOrderBootstrapTaskOut(
                        dev_task_id=t_id,
                        dev_task_public_id=str(public_id)
                        if public_id is not None
                        else None,
                        stack=stack,
                        title=title,
                        status=status,
                        created_at=str(created_at) if created_at is not None else None,
                    )
                )

        if existing and not dry_run:
            return existing

        template_tasks = [
            {
                "stack": "devfactory.pipeline",
                "title": f"[DevOrder] Анализ и декомпозиция: {base_title}",
            },
            {
                "stack": "devfactory.pipeline",
                "title": f"[DevOrder] Реализация и интеграция: {base_title}",
            },
            {
                "stack": "devfactory.billing",
                "title": f"[DevOrder] Биллинг / счёт по заказу: {base_title}",
            },
        ]

        if dry_run:
            return [
                DevOrderBootstrapTaskOut(
                    dev_task_id=None,
                    dev_task_public_id=None,
                    stack=tpl["stack"],
                    title=tpl["title"],
                    status="new",
                    created_at=None,
                )
                for tpl in template_tasks
            ]

        meta_common: Dict[str, Any] = {
            "dev_order_id": dev_order_uuid,
            "dev_order_public_id": dev_order_public_id,
            "plan_domain": plan_domain,
        }
        if order_title:
            meta_common["order_title"] = order_title
        if customer_name:
            meta_common["customer_name"] = customer_name
        if tenant_external_id:
            meta_common["order_tenant_external_id"] = tenant_external_id

        result: List[DevOrderBootstrapTaskOut] = []
        with conn.cursor() as cur:
            for tpl in template_tasks:
                cur.execute(
                    """
                    INSERT INTO dev.dev_task (
                        stack,
                        title,
                        status,
                        meta
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s::jsonb
                    )
                    RETURNING id, public_id, stack, title, status, created_at
                    """,
                    (
                        tpl["stack"],
                        tpl["title"],
                        "new",
                        json.dumps(meta_common),
                    ),
                )
                t_id, public_id, stack, title, status, created_at = cur.fetchone()
                result.append(
                    DevOrderBootstrapTaskOut(
                        dev_task_id=t_id,
                        dev_task_public_id=str(public_id)
                        if public_id is not None
                        else None,
                        stack=stack,
                        title=title,
                        status=status,
                        created_at=str(created_at) if created_at is not None else None,
                    )
                )

        conn.commit()
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
#  Линки: tenant / billing / lead
# ---------------------------------------------------------------------------


@router.post(
    "/{dev_order_id}/link/tenant",
    summary="Привязать DevOrder к CRM tenant",
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def link_tenant(dev_order_id: str, body: DevOrderLinkTenantIn) -> Dict[str, Any]:
    conn = _connect_pg()
    try:
        _ensure_order_exists(conn, dev_order_id)

        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dev.dev_order_link
                WHERE dev_order_id = %s AND link_type = 'tenant'
                """,
                (dev_order_id,),
            )

            cur.execute(
                """
                INSERT INTO dev.dev_order_link (
                    order_id,
                    dev_order_id,
                    link_type,
                    ref_table,
                    ref_id,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    'tenant',
                    'crm.tenant',
                    %s,
                    now()
                )
                """,
                (dev_order_id, dev_order_id, body.tenant_id),
            )

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post(
    "/{dev_order_id}/link/billing",
    summary="Привязать DevOrder к billing.subscription или billing.invoice",
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def link_billing(dev_order_id: str, body: DevOrderLinkBillingIn) -> Dict[str, Any]:
    link_type = body.link_type
    if link_type not in ("billing_subscription", "billing_invoice"):
        raise HTTPException(
            status_code=400,
            detail="link_type must be 'billing_subscription' or 'billing_invoice'",
        )

    default_table = (
        "billing.subscription" if link_type == "billing_subscription" else "billing.invoice"
    )
    ref_table = body.billing_table or default_table

    conn = _connect_pg()
    try:
        _ensure_order_exists(conn, dev_order_id)

        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dev.dev_order_link
                WHERE dev_order_id = %s AND link_type = %s
                """,
                (dev_order_id, link_type),
            )

            cur.execute(
                """
                INSERT INTO dev.dev_order_link (
                    order_id,
                    dev_order_id,
                    link_type,
                    ref_table,
                    ref_id,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, now())
                """,
                (dev_order_id, dev_order_id, link_type, ref_table, body.billing_id),
            )

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post(
    "/{dev_order_id}/link/lead",
    summary="Привязать DevOrder к CRM lead (код лида)",
    dependencies=[Depends(require_policies("devfactory", ["manage_orders"]))],
)
def link_lead(dev_order_id: str, body: DevOrderLinkLeadIn) -> Dict[str, Any]:
    conn = _connect_pg()
    try:
        _ensure_order_exists(conn, dev_order_id)

        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dev.dev_order_link
                WHERE dev_order_id = %s AND link_type = 'lead'
                """,
                (dev_order_id,),
            )

            cur.execute(
                """
                INSERT INTO dev.dev_order_link (
                    order_id,
                    dev_order_id,
                    link_type,
                    ref_table,
                    ref_id,
                    created_at
                )
                VALUES (%s, %s, 'lead', 'crm.lead', %s, now())
                """,
                (dev_order_id, dev_order_id, body.lead_code),
            )

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
