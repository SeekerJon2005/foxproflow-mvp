# -*- coding: utf-8 -*-
# file: src/worker/tasks_salesfox.py
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from celery import shared_task

from src.core import emit_start, emit_done, emit_error
from src.core.pg_conn import _connect_pg

log = logging.getLogger(__name__)

# Допустимые значения channel в crm.sales_sessions.channel CHECK(...)
ALLOWED_CHANNELS = {"web_chat", "email", "partner_portal", "manual"}
DEFAULT_CHANNEL = "web_chat"


# === Core logic (callable из API и Celery) ===========================


def salesfox_start_session(lead_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создаёт crm.leads + crm.sales_sessions для нового лида.

    lead_payload может содержать:
    - source, company_name, contact_name, email, phone, country, region,
      fleet_size, channel, payload (любые поля).
    """
    corr_id = "sales.session:new"
    event_id = emit_start(
        "salesfox",
        correlation_id=corr_id,
        payload={"stage": "start_session", "lead_payload": lead_payload},
    )

    # Источник лида
    source = (lead_payload.get("source") or "web").strip()
    if not source:
        source = "web"

    # Канал коммуникации — приводим к whitelisted списку, чтобы не нарушать CHECK(channel IN (...))
    raw_channel = (lead_payload.get("channel") or DEFAULT_CHANNEL).strip()
    channel = raw_channel if raw_channel in ALLOWED_CHANNELS else DEFAULT_CHANNEL

    data = {
        "source": source,
        "status": "new",  # crm.leads.status CHECK (...) — 'new' допустим
        "company_name": lead_payload.get("company_name"),
        "contact_name": lead_payload.get("contact_name"),
        "email": lead_payload.get("email"),
        "phone": lead_payload.get("phone"),
        "country": lead_payload.get("country"),
        "region": lead_payload.get("region"),
        "payload": json.dumps(lead_payload, ensure_ascii=False),
    }

    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            # 1) создаём лида
            cur.execute(
                """
                INSERT INTO crm.leads (
                    source, status,
                    company_name, contact_name, email, phone,
                    country, region, payload
                )
                VALUES (
                    %(source)s, %(status)s,
                    %(company_name)s, %(contact_name)s, %(email)s, %(phone)s,
                    %(country)s, %(region)s, %(payload)s
                )
                RETURNING id
                """,
                data,
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("INSERT INTO crm.leads returned no id")
            lead_id = int(row[0])

            # 2) создаём сессию продаж
            cur.execute(
                """
                INSERT INTO crm.sales_sessions (
                    lead_id, channel, status, transcript, summary, last_event_id
                )
                VALUES (
                    %(lead_id)s, %(channel)s, %(status)s,
                    '[]'::jsonb, '{}'::jsonb, %(last_event_id)s
                )
                RETURNING id
                """,
                {
                    "lead_id": lead_id,
                    "channel": channel,
                    "status": "active",
                    "last_event_id": event_id,
                },
            )
            row2 = cur.fetchone()
            if not row2:
                raise RuntimeError("INSERT INTO crm.sales_sessions returned no id")
            session_id = int(row2[0])

            # 3) обновим ссылку в lead (last_session_id) для удобства
            cur.execute(
                """
                UPDATE crm.leads
                SET last_session_id = %s, updated_at = now()
                WHERE id = %s
                """,
                (session_id, lead_id),
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        emit_error(
            "salesfox",
            correlation_id=corr_id,
            payload={"stage": "start_session", "error": repr(exc)},
        )
        log.exception("salesfox.start_session failed")
        raise
    else:
        emit_done(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "start_session",
                "event_id": event_id,
                "lead_id": lead_id,
                "session_id": session_id,
            },
        )
        return {
            "ok": True,
            "lead_id": lead_id,
            "session_id": session_id,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def salesfox_handle_message(session_id: int, message: str) -> Dict[str, Any]:
    """
    Примитивный v0: просто сохраняем сообщение в transcript
    и возвращаем заглушку-ответ.
    """
    corr_id = f"sales.session:{session_id}"
    event_id = emit_start(
        "salesfox",
        correlation_id=corr_id,
        payload={"stage": "handle_message", "session_id": session_id},
    )

    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            # берём текущий transcript
            cur.execute(
                "SELECT transcript FROM crm.sales_sessions WHERE id = %s FOR UPDATE",
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"sales_session {session_id} not found")

            raw = row[0]
            try:
                transcript: List[Dict[str, Any]]
                if raw is None:
                    transcript = []
                elif isinstance(raw, str):
                    transcript = json.loads(raw)
                else:
                    # psycopg обычно уже даёт Python-структуру
                    transcript = list(raw)
            except Exception:
                transcript = []

            import datetime as _dt

            now_iso = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()

            transcript.append(
                {
                    "role": "user",
                    "ts": now_iso,
                    "text": message,
                }
            )

            # v0-ответ: эхо с подсказкой
            reply = (
                "SalesFox v0 здесь. Я сохранил ваш запрос, "
                "а в боевой версии буду считать выгоды и подбирать тариф."
            )

            transcript.append(
                {
                    "role": "assistant",
                    "ts": now_iso,
                    "text": reply,
                }
            )

            cur.execute(
                """
                UPDATE crm.sales_sessions
                SET transcript = %s::jsonb,
                    updated_at = now(),
                    last_event_id = %s
                WHERE id = %s
                """,
                (json.dumps(transcript, ensure_ascii=False), event_id, session_id),
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        emit_error(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "handle_message",
                "session_id": session_id,
                "error": repr(exc),
            },
        )
        log.exception("salesfox.handle_message failed")
        raise
    else:
        emit_done(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "handle_message",
                "session_id": session_id,
                "event_id": event_id,
            },
        )
        return {
            "ok": True,
            "session_id": session_id,
            "reply": reply,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def salesfox_generate_proposal(session_id: int) -> Dict[str, Any]:
    """
    v0: строим очень грубое предложение по подписке на основе лида.

    Дальше сюда подцепим экономический блок и FlowLang-план sales.flow.
    """
    corr_id = f"sales.session:{session_id}"
    event_id = emit_start(
        "salesfox",
        correlation_id=corr_id,
        payload={"stage": "generate_proposal", "session_id": session_id},
    )

    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.lead_id,
                    l.company_name,
                    l.country,
                    l.region,
                    l.payload
                FROM crm.sales_sessions s
                LEFT JOIN crm.leads l ON l.id = s.lead_id
                WHERE s.id = %s
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"sales_session {session_id} not found")

            lead_id = row[0]
            company_name = row[1]
            country = row[2]
            region = row[3]
            lead_payload_raw = row[4]

            try:
                if isinstance(lead_payload_raw, str):
                    lead_payload = json.loads(lead_payload_raw)
                else:
                    lead_payload = dict(lead_payload_raw or {})
            except Exception:
                lead_payload = {}

            # v0-логику делаем нарочито простой
            modules: List[str] = ["logistics"]
            if country in ("RU", "KZ", "BY"):
                modules.append("accounting")
                modules.append("legal")

            raw_fleet_size = lead_payload.get("fleet_size")
            try:
                fleet_size = int(raw_fleet_size) if raw_fleet_size is not None else 10
            except (TypeError, ValueError):
                fleet_size = 10

            base_price = 15000
            extra_per_truck = 3000
            price = base_price + max(0, fleet_size - 5) * extra_per_truck

            proposal = {
                "lead_id": lead_id,
                "company_name": company_name,
                "country": country,
                "region": region,
                "modules": modules,
                "plan_code": "basic",
                "fleet_size_estimate": fleet_size,
                "estimated_savings_rub_per_month": price * 2,
                "price_rub_per_month": price,
            }

            cur.execute(
                """
                UPDATE crm.sales_sessions
                SET summary = %s::jsonb,
                    updated_at = now(),
                    last_event_id = %s
                WHERE id = %s
                """,
                (json.dumps(proposal, ensure_ascii=False), event_id, session_id),
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        emit_error(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "generate_proposal",
                "session_id": session_id,
                "error": repr(exc),
            },
        )
        log.exception("salesfox.generate_proposal failed")
        raise
    else:
        emit_done(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "generate_proposal",
                "session_id": session_id,
                "event_id": event_id,
            },
        )
        return {
            "ok": True,
            "session_id": session_id,
            "proposal": proposal,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def crm_lead_win_trial_onboarding(
    lead_id: int,
    product_code: str = "logistics",
    plan_code: str = "mvp-5-15-trucks",
    currency: str = "RUB",
    amount_month: float | Decimal = 0.0,
    billing_period: str = "monthly",
    trial_days: int = 30,
) -> Dict[str, Any]:
    """
    Оркестратор lead → win → trial → onboarding через
    crm.fn_lead_win_trial_and_onboarding(...).

    Можно вызывать из Celery, API, CLI.
    """
    corr_id = f"crm.lead:{lead_id}"
    event_id = emit_start(
        "crm",
        correlation_id=corr_id,
        payload={
            "stage": "lead_win_trial_onboarding",
            "lead_id": lead_id,
            "product_code": product_code,
            "plan_code": plan_code,
            "currency": currency,
            "amount_month": amount_month,
            "billing_period": billing_period,
            "trial_days": trial_days,
        },
    )

    # Нормализуем types → под сигнатуру SQL-функции (bigint, numeric, integer)
    try:
        amount_month_dec = Decimal(str(amount_month))
    except (InvalidOperation, TypeError, ValueError):
        amount_month_dec = Decimal("0")

    lead_id_int = int(lead_id)
    trial_days_int = int(trial_days)

    conn = _connect_pg()
    trial_until: Optional[Any] = None

    try:
        # 1. Вызываем SQL-оркестратор
        with conn.cursor() as cur:
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
                    "lead_id": lead_id_int,
                    "product_code": product_code,
                    "plan_code": plan_code,
                    "currency": currency,
                    "amount_month": amount_month_dec,
                    "billing_period": billing_period,
                    "trial_days": trial_days_int,
                },
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"crm.fn_lead_win_trial_and_onboarding({lead_id_int}) returned no rows"
            )

        (
            lead_id_out,
            tenant_id_out,
            account_id_out,
            subscription_id,
            subscription_v2_id,
            onboarding_id,
        ) = row

        # 2. Берём trial_until из витрины account_overview_v (v2 или v1)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(trial_until_v2, trial_ends_at_v1) AS trial_until
                FROM crm.account_overview_v
                WHERE account_id = %s
                """,
                (account_id_out,),
            )
            row2 = cur.fetchone()
        if row2:
            (trial_until,) = row2

        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        emit_error(
            "crm",
            correlation_id=corr_id,
            payload={
                "stage": "lead_win_trial_onboarding",
                "lead_id": lead_id,
                "error": repr(exc),
            },
        )
        log.exception("crm.lead_win_trial_onboarding failed")
        raise
    else:
        if trial_until is not None and hasattr(trial_until, "isoformat"):
            trial_until_iso: Optional[str] = trial_until.isoformat()
        else:
            trial_until_iso = None

        emit_done(
            "crm",
            correlation_id=corr_id,
            payload={
                "stage": "lead_win_trial_onboarding",
                "event_id": event_id,
                "lead_id": lead_id_out,
                "tenant_id": str(tenant_id_out),
                "account_id": account_id_out,
                "subscription_id": subscription_id,
                "subscription_v2_id": str(subscription_v2_id),
                "plan_code": plan_code,
                "trial_until": trial_until_iso,
                "onboarding_id": onboarding_id,
            },
        )

        return {
            "ok": True,
            "lead_id": lead_id_out,
            "tenant_id": str(tenant_id_out),
            "account_id": account_id_out,
            "subscription_id": subscription_id,
            "subscription_v2_id": str(subscription_v2_id),
            "onboarding_id": onboarding_id,
            "plan_code": plan_code,
            "trial_until": trial_until_iso,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def salesfox_scan_and_start_trials(limit: int = 32) -> Dict[str, Any]:
    """
    SalesFox-агент: находит лиды со статусом 'ready_for_trial'
    (через crm.leads_trial_candidates_v) и запускает для них
    crm_lead_win_trial_onboarding(...).

    Возвращает агрегированный результат:
    - сколько лидов обработали;
    - какие lead_id прошли успешно / с ошибкой.
    """
    # Нормализуем лимит
    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        limit_int = 32
    if limit_int <= 0:
        limit_int = 1

    corr_id = "salesfox.trial_scan"
    event_id = emit_start(
        "salesfox",
        correlation_id=corr_id,
        payload={"stage": "scan_and_start_trials", "limit": limit_int},
    )

    conn = _connect_pg()
    lead_ids: List[int] = []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lead_id
                FROM crm.leads_trial_candidates_v
                ORDER BY created_at, lead_id
                LIMIT %s
                """,
                (limit_int,),
            )
            rows = cur.fetchall()
            lead_ids = [int(row[0]) for row in rows]

        # только чтение — commit не обязателен, но оставим для симметрии
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        emit_error(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "scan_and_start_trials",
                "error": repr(exc),
            },
        )
        log.exception("salesfox.scan_and_start_trials: failed to fetch candidates")
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not lead_ids:
        emit_done(
            "salesfox",
            correlation_id=corr_id,
            payload={
                "stage": "scan_and_start_trials",
                "event_id": event_id,
                "handled_count": 0,
                "handled": [],
                "failed": [],
            },
        )
        return {
            "ok": True,
            "handled_count": 0,
            "handled": [],
            "failed": [],
        }

    handled: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    log.info(
        "SalesFox: scan_and_start_trials: found %s leads: %s",
        len(lead_ids),
        lead_ids,
    )

    for lead_id in lead_ids:
        try:
            res = crm_lead_win_trial_onboarding(lead_id=lead_id)
            handled.append({"lead_id": lead_id, "result": res})
        except Exception as exc:
            failed.append({"lead_id": lead_id, "error": repr(exc)})
            log.exception(
                "SalesFox: failed to start trial for lead_id=%s: %s", lead_id, exc
            )

    ok = len(failed) == 0

    emit_done(
        "salesfox",
        correlation_id=corr_id,
        payload={
            "stage": "scan_and_start_trials",
            "event_id": event_id,
            "handled_count": len(handled),
            "failed_count": len(failed),
            "lead_ids": lead_ids,
        },
    )

    return {
        "ok": ok,
        "handled_count": len(handled),
        "handled": handled,
        "failed": failed,
    }


# === Celery wrappers (агенты) =======================================


@shared_task(name="agents.salesfox.start_session")
def agents_salesfox_start_session(lead_payload: Dict[str, Any]) -> Dict[str, Any]:
    return salesfox_start_session(lead_payload)


@shared_task(name="agents.salesfox.handle_message")
def agents_salesfox_handle_message(session_id: int, message: str) -> Dict[str, Any]:
    return salesfox_handle_message(session_id, message)


@shared_task(name="agents.salesfox.generate_proposal")
def agents_salesfox_generate_proposal(session_id: int) -> Dict[str, Any]:
    return salesfox_generate_proposal(session_id)


@shared_task(name="crm.lead_win_trial_onboarding")
def task_crm_lead_win_trial_onboarding(
    lead_id: int,
    product_code: str = "logistics",
    plan_code: str = "mvp-5-15-trucks",
    currency: str = "RUB",
    amount_month: float | Decimal = 0.0,
    billing_period: str = "monthly",
    trial_days: int = 30,
) -> Dict[str, Any]:
    """
    Celery-таска-обвязка для crm_lead_win_trial_onboarding(...).

    Пример вызова из контейнера worker:

      celery -A src.worker.celery_app call crm.lead_win_trial_onboarding --args='[1]'

    А затем посмотреть результат:

      celery -A src.worker.celery_app result <task_id>
    """
    return crm_lead_win_trial_onboarding(
        lead_id=lead_id,
        product_code=product_code,
        plan_code=plan_code,
        currency=currency,
        amount_month=amount_month,
        billing_period=billing_period,
        trial_days=trial_days,
    )


@shared_task(name="salesfox.scan_and_start_trials")
def task_salesfox_scan_and_start_trials(limit: int = 32) -> Dict[str, Any]:
    """
    Celery-задача для запуска SalesFox-агента, который:

    - читает crm.leads_trial_candidates_v (status='ready_for_trial');
    - запускает crm_lead_win_trial_onboarding(...) для найденных лидов.

    Можно повесить на beat (каждые N минут) или вызывать вручную:

      celery -A src.worker.celery_app call salesfox.scan_and_start_trials --kwargs='{"limit": 16}'
    """
    return salesfox_scan_and_start_trials(limit=limit)
