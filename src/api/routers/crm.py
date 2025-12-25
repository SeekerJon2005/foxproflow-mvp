# -*- coding: utf-8 -*-
# file: src/api/routers/crm.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger("uvicorn")

# ВАЖНО:
# prefix="/crm" + include_router(..., prefix="/api") в main.py
# дают итоговые пути /api/crm/...
router = APIRouter(
    prefix="/crm",
    tags=["crm"],
)

# =============================================================================
# Константы / таймауты (safe-default, без обязательных env)
# =============================================================================

# Connect timeout: чтобы не зависать при проблемах с БД
_PG_CONNECT_TIMEOUT_SEC: int = int(os.getenv("CRM_PG_CONNECT_TIMEOUT_SEC", "3") or "3")
# Statement timeout: чтобы не зависать на запросах
_PG_STATEMENT_TIMEOUT_MS: int = int(os.getenv("CRM_PG_STATEMENT_TIMEOUT_MS", "2500") or "2500")


# =============================================================================
# --- Вспомогательные функции подключения к Postgres --------------------------
# =============================================================================


def _build_pg_dsn() -> str:
    """
    Собираем DSN для Postgres по тем же правилам, что и в /health/extended.
    """
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")

    if pwd:
        auth = f"{user}:{pwd}"
    else:
        auth = user

    return f"postgresql://{auth}@{host}:{port}/{db}"


def _connect_pg():
    """
    Подключение к Postgres: сначала пробуем psycopg3, затем psycopg2.
    Добавлен connect_timeout, чтобы не зависать.
    """
    dsn = _build_pg_dsn()
    first_exc: Optional[Exception] = None

    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn, connect_timeout=_PG_CONNECT_TIMEOUT_SEC)
    except Exception as e1:  # noqa: BLE001
        first_exc = e1

    try:
        import psycopg2  # type: ignore

        return psycopg2.connect(dsn, connect_timeout=_PG_CONNECT_TIMEOUT_SEC)
    except Exception as e2:  # noqa: BLE001
        msg = "Unable to connect to Postgres via psycopg/psycopg2"
        if first_exc:
            msg += f" (psycopg error: {first_exc!r})"
        raise RuntimeError(msg) from e2


def _set_local_timeouts(cur) -> None:
    """
    Best-effort таймауты на уровне транзакции.
    """
    try:
        cur.execute(f"SET LOCAL statement_timeout = '{_PG_STATEMENT_TIMEOUT_MS}ms'")
    except Exception:
        # В некоторых режимах/драйверах может быть не поддержано — не валим endpoint
        pass


def _db_contract_checks(cur) -> Dict[str, Any]:
    """
    Проверки DB-контракта CP1 (по REQUEST от C-sql).
    Ничего не создаёт, только читает метаданные/наличие объектов.
    """
    _set_local_timeouts(cur)

    cur.execute(
        """
        SELECT
          EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='sec')      AS sec_schema,
          EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='planner') AS planner_schema,
          (SELECT COUNT(*)
             FROM pg_class c
             JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='planner'
              AND c.relkind IN ('r','v','m')
              AND c.relname ILIKE '%kpi%')                            AS planner_kpi_like_cnt,

          to_regclass('dev.dev_task')                  IS NOT NULL     AS dev_dev_task,
          to_regclass('ops.event_log')                 IS NOT NULL     AS ops_event_log,
          EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='ops'
               AND table_name='event_log'
               AND column_name='correlation_id'
          )                                                           AS ops_event_log_has_correlation_id,

          to_regclass('public.trucks')                 IS NOT NULL     AS public_trucks,
          to_regclass('public.trips')                  IS NOT NULL     AS public_trips,
          to_regclass('public.trip_segments')          IS NOT NULL     AS public_trip_segments,
          to_regclass('crm.leads_trial_candidates_v')  IS NOT NULL     AS crm_leads_trial_candidates_v
        """
    )

    row = cur.fetchone()
    if not row:
        return {"error": "no rows from db contract query"}

    cols = [d[0] for d in cur.description]  # type: ignore[attr-defined]
    checks: Dict[str, Any] = dict(zip(cols, row))

    # нормализуем числовой счётчик
    try:
        checks["planner_kpi_like_cnt"] = int(checks.get("planner_kpi_like_cnt") or 0)
    except Exception:
        pass

    return checks


def _db_contract_ok(checks: Dict[str, Any]) -> bool:
    """
    Сведение проверок к bool. KPI проверяем как cnt > 0.
    """
    try:
        kpi_cnt = int(checks.get("planner_kpi_like_cnt") or 0)
    except Exception:
        kpi_cnt = 0

    return bool(
        checks.get("sec_schema")
        and checks.get("planner_schema")
        and (kpi_cnt > 0)
        and checks.get("dev_dev_task")
        and checks.get("ops_event_log")
        and checks.get("ops_event_log_has_correlation_id")
        and checks.get("public_trucks")
        and checks.get("public_trips")
        and checks.get("public_trip_segments")
        and checks.get("crm_leads_trial_candidates_v")
    )


# =============================================================================
# --- Pydantic-модели ---------------------------------------------------------
# =============================================================================


class LeadWinAndStartOnboardingRequest(BaseModel):
    """
    Параметры триала, которые можно переопределить с фронта.

    Все значения имеют стандартные дефолты для FoxProFlow MVP:
    - продукт: logistics
    - план: mvp-5-15-trucks
    - валюта: RUB
    - период: monthly
    - trial_days: 30
    """

    product_code: str = "logistics"
    plan_code: str = "mvp-5-15-trucks"
    currency: str = "RUB"
    amount_month: Decimal = Decimal("0")
    billing_period: str = "monthly"
    trial_days: int = 30


class LeadWinAndStartOnboardingResponse(BaseModel):
    """
    Ответ оркестратора crm.fn_lead_win_trial_and_onboarding(...):
    """

    lead_id: int
    tenant_id: UUID
    account_id: int
    subscription_id: int
    subscription_v2_id: UUID
    onboarding_id: int


class LeadMarkReadyForTrialResponse(BaseModel):
    """
    Ответ на пометку лида как ready_for_trial.
    """

    lead_id: int
    status: str
    updated_at: datetime


class TrialAccountOverview(BaseModel):
    """
    Строка витрины crm.trial_accounts_overview_v.
    """

    account_id: int
    company_name: str
    product_code: str
    plan_code: str
    trial_until: Optional[datetime]
    is_expired: bool
    trial_status: str  # active | expiring_soon | expired | none
    days_left: int


# =============================================================================
# --- Константы ---------------------------------------------------------------
# =============================================================================

# какие значения trial_status допустимы в фильтре API
_ALLOWED_TRIAL_STATUSES = {"active", "expiring_soon", "expired", "none"}


# =============================================================================
# --- Smoke endpoints (CP1) ---------------------------------------------------
# =============================================================================


@router.get("/smoke/ping", summary="CRM smoke ping")
def crm_smoke_ping():
    """Ultra-light CRM smoke endpoint. No DB. No side effects."""
    return {"ok": True, "service": "crm", "smoke": True}


@router.get("/smoke/db", summary="CRM DB contract smoke (CP1)")
def crm_smoke_db_contract():
    """
    DB contract smoke: проверяет наличие обязательных объектов (по REQUEST от C-sql).
    Safe-degrade: если БД недоступна — возвращаем ok=false + error, без падения импорта.
    """
    conn = None
    try:
        conn = _connect_pg()
        with conn.cursor() as cur:
            checks = _db_contract_checks(cur)
        ok = _db_contract_ok(checks) if "error" not in checks else False
        return {"ok": ok, "service": "crm", "db_contract": ok, "checks": checks}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "service": "crm", "db_contract": False, "error": repr(ex)}
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


# =============================================================================
# --- Debug / Observability: trial candidates ---------------------------------
# =============================================================================


@router.get(
    "/leads/trial-candidates",
    response_model=List[Dict[str, Any]],
    summary="Список кандидатов на trial (debug) из crm.leads_trial_candidates_v",
)
def get_leads_trial_candidates(
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Максимальное количество строк",
    ),
) -> List[Dict[str, Any]]:
    """
    Возвращает кандидатов из crm.leads_trial_candidates_v в JSON-форме без знания колонок:
    SELECT to_jsonb(t) FROM crm.leads_trial_candidates_v t LIMIT ...
    """
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            _set_local_timeouts(cur)
            cur.execute(
                """
                SELECT to_jsonb(t)
                FROM crm.leads_trial_candidates_v t
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"DB error while reading crm.leads_trial_candidates_v: {exc}",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


# =============================================================================
# --- Business endpoints -------------------------------------------------------
# =============================================================================


@router.post(
    "/leads/{lead_id}/win-and-start-onboarding",
    response_model=LeadWinAndStartOnboardingResponse,
    summary="Перевести лида в won, создать trial и сессию онбординга",
)
def lead_win_and_start_onboarding(
    lead_id: int,
    body: LeadWinAndStartOnboardingRequest,
) -> LeadWinAndStartOnboardingResponse:
    """
    HTTP-обёртка над crm.fn_lead_win_trial_and_onboarding(...).

    Делает за один вызов:
    - находит лида в crm.leads;
    - при необходимости создаёт tenant_id и пишет его в leads.payload;
    - переводит лид в статус 'won';
    - запускает trial-подписку (v1 + v2);
    - создаёт запись в crm.onboarding_sessions.
    """
    conn = _connect_pg()

    try:
        with conn.cursor() as cur:
            _set_local_timeouts(cur)
            cur.execute(
                """
                SELECT
                    lead_id_out,
                    tenant_id_out,
                    account_id_out,
                    subscription_id,
                    subscription_v2_id,
                    onboarding_id
                FROM crm.fn_lead_win_trial_and_onboarding(
                    %(lead_id)s::bigint,
                    %(product_code)s::text,
                    %(plan_code)s::text,
                    %(currency)s::text,
                    %(amount_month)s::numeric,
                    %(billing_period)s::text,
                    %(trial_days)s::integer
                );
                """,
                {
                    "lead_id": lead_id,
                    "product_code": body.product_code,
                    "plan_code": body.plan_code,
                    "currency": body.currency,
                    "amount_month": body.amount_month,
                    "billing_period": body.billing_period,
                    "trial_days": body.trial_days,
                },
            )
            row = cur.fetchone()

        conn.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=(
                "DB error while running crm.fn_lead_win_trial_and_onboarding: "
                f"{exc}"
            ),
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Lead {lead_id} was not processed (function returned no rows)",
        )

    return LeadWinAndStartOnboardingResponse(
        lead_id=int(row[0]),
        tenant_id=UUID(str(row[1])),
        account_id=int(row[2]),
        subscription_id=int(row[3]),
        subscription_v2_id=UUID(str(row[4])),
        onboarding_id=int(row[5]),
    )


@router.post(
    "/leads/{lead_id}/mark-ready-for-trial",
    response_model=LeadMarkReadyForTrialResponse,
    summary="Пометить лида как готового к trial (status=ready_for_trial)",
)
def mark_lead_ready_for_trial(
    lead_id: int,
) -> LeadMarkReadyForTrialResponse:
    """
    Помечает лида в crm.leads статусом 'ready_for_trial'.
    """
    conn = _connect_pg()

    try:
        with conn.cursor() as cur:
            _set_local_timeouts(cur)
            cur.execute(
                """
                UPDATE crm.leads
                SET status = 'ready_for_trial',
                    updated_at = now()
                WHERE id = %(lead_id)s
                RETURNING id, status, updated_at;
                """,
                {"lead_id": lead_id},
            )
            row = cur.fetchone()

        if not row:
            try:
                conn.rollback()
            except Exception:
                pass
            raise HTTPException(
                status_code=404,
                detail=f"Lead {lead_id} not found",
            )

        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"DB error while marking lead {lead_id} ready_for_trial: {exc}",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    lead_id_out, status_out, updated_at_out = row
    return LeadMarkReadyForTrialResponse(
        lead_id=int(lead_id_out),
        status=str(status_out),
        updated_at=updated_at_out,
    )


@router.get(
    "/trials/overview",
    response_model=List[TrialAccountOverview],
    summary="Обзор trial-аккаунтов FoxProFlow",
)
def get_trial_accounts_overview(
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Максимальное количество строк в ответе",
    ),
    status: Optional[str] = Query(
        None,
        description="Фильтр по trial_status: active | expiring_soon | expired | none",
    ),
) -> List[TrialAccountOverview]:
    """
    Возвращает список trial-аккаунтов из crm.trial_accounts_overview_v.
    """
    if status and status not in _ALLOWED_TRIAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid trial_status={status!r}; "
                f"allowed: {sorted(_ALLOWED_TRIAL_STATUSES)}"
            ),
        )

    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            _set_local_timeouts(cur)

            sql = """
                SELECT
                    account_id,
                    company_name,
                    product_code,
                    plan_code,
                    trial_until,
                    is_expired,
                    trial_status,
                    days_left
                FROM crm.trial_accounts_overview_v
            """
            params: List[object] = []

            if status:
                sql += " WHERE trial_status = %s"
                params.append(status)

            sql += " ORDER BY trial_until ASC NULLS LAST LIMIT %s"
            params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"DB error while reading crm.trial_accounts_overview_v: {exc}",
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return [
        TrialAccountOverview(
            account_id=int(row[0]),
            company_name=str(row[1]),
            product_code=str(row[2]),
            plan_code=str(row[3]),
            trial_until=row[4],
            is_expired=bool(row[5]),
            trial_status=str(row[6]),
            days_left=int(row[7]),
        )
        for row in rows
    ]
