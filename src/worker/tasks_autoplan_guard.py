# -*- coding: utf-8 -*-
# file: src/worker/tasks_autoplan_guard.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from celery import shared_task

from .tasks_agents import _connect_pg  # type: ignore[import]

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.getenv("CELERY_LOG_LEVEL", "INFO"))


def _utcnow_iso() -> str:
    """UTC-время в ISO-формате, усечённое до секунд (для payload/логов)."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_int(
    value: Any,
    default: int = 3,
    min_val: int = 1,
    max_val: int = 30,
) -> int:
    """Безопасное преобразование к int с ограничением диапазона."""
    try:
        v = int(value)
    except Exception:
        v = default
    if v < min_val:
        v = min_val
    if v > max_val:
        v = max_val
    return v


def _query_autoplan_audit_summary(conn, days_back: int) -> List[Dict[str, Any]]:
    """
    Агрегация по public.autoplan_audit:
      день, план, решение, количество.
    """
    sql = """
        SELECT
          date(ts) AS d,
          COALESCE(thresholds->>'flow_plan', 'unknown') AS flow_plan,
          decision,
          count(*) AS cnt
        FROM public.autoplan_audit
        WHERE ts >= now() - (%(days_back)s || ' days')::interval
        GROUP BY date(ts), flow_plan, decision
        ORDER BY d DESC, flow_plan, decision;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days_back": days_back})
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _query_autoplan_audit_top_reasons(conn, days_back: int) -> List[Dict[str, Any]]:
    """
    Топ-20 причин (decision, reason) из public.autoplan_audit.
    """
    sql = """
        SELECT
          decision,
          reason,
          count(*) AS cnt
        FROM public.autoplan_audit
        WHERE ts >= now() - (%(days_back)s || ' days')::interval
        GROUP BY decision, reason
        ORDER BY cnt DESC
        LIMIT 20;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days_back": days_back})
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _query_autoplan_trips_vs_market(conn, days_back: int) -> List[Dict[str, Any]]:
    """
    Срез по analytics.autoplan_trips_vs_market_v:
      день, план, количество рейсов, суммарная выручка по ставкам.
    """
    sql = """
        SELECT
          confirmed_at::date AS day,
          flow_plan,
          count(*)            AS trips_cnt,
          sum(trip_price_rub) AS total_price_rub
        FROM analytics.autoplan_trips_vs_market_v
        WHERE confirmed_at >= now() - (%(days_back)s || ' days')::interval
        GROUP BY day, flow_plan
        ORDER BY day DESC, flow_plan;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days_back": days_back})
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _query_autoplan_trips_daily(conn, days_back: int) -> List[Dict[str, Any]]:
    """
    Срез по analytics.autoplan_trips_daily_v:
      день, план, количество рейсов, событий, суммарная выручка.
    """
    sql = """
        SELECT
          d             AS day,
          flow_plan,
          trips_cnt,
          trip_events_cnt,
          sum_price_rub
        FROM analytics.autoplan_trips_daily_v
        WHERE d >= current_date - %(days_back)s::int
        ORDER BY day DESC, flow_plan;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days_back": days_back})
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _build_guard_meta(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Собирает компактное резюме по данным агента:
      - total_trips       — всего рейсов за окно;
      - last_day          — последний день с данными;
      - last_day_trips    — рейсов в последний день;
      - confirm_events    — число событий decision='confirm';
      - noop_events       — число событий decision='noop';
      - confirm_share     — доля confirm среди (confirm+noop), если есть;
      - plans_seen        — список планов, замеченных в окне;
      - flags             — простые флаги аномалий;
      - status            — свёрнутый статус ('ok', 'no_trips', 'warn_low_confirm_share').
    """
    daily_rows = summary.get("trips_daily") or []
    audit_rows = summary.get("audit_by_day") or []

    # Всего рейсов за окно
    total_trips = 0
    days_set = set()
    plans_set = set()

    for row in daily_rows:
        try:
            trips_cnt = int(row.get("trips_cnt") or 0)
        except Exception:
            trips_cnt = 0
        total_trips += trips_cnt

        day_val = row.get("day")
        if day_val is not None:
            days_set.add(day_val)

        flow_plan = row.get("flow_plan")
        if flow_plan:
            plans_set.add(flow_plan)

    last_day: Optional[datetime.date] = max(days_set) if days_set else None

    # Рейсы за последний день
    last_day_trips = 0
    if last_day is not None:
        for row in daily_rows:
            if row.get("day") == last_day:
                try:
                    last_day_trips += int(row.get("trips_cnt") or 0)
                except Exception:
                    continue

    # Статистика по решениям (confirm / noop)
    confirm_events = 0
    noop_events = 0
    for row in audit_rows:
        decision = row.get("decision")
        try:
            cnt = int(row.get("cnt") or 0)
        except Exception:
            cnt = 0

        if decision == "confirm":
            confirm_events += cnt
        elif decision == "noop":
            noop_events += cnt

    total_decisions = confirm_events + noop_events
    confirm_share: Optional[float]
    if total_decisions > 0:
        confirm_share = confirm_events / float(total_decisions)
    else:
        confirm_share = None

    flags: Dict[str, bool] = {
        "no_trips_window": total_trips == 0,
        "no_trips_last_day": last_day_trips == 0 and last_day is not None,
        "confirm_share_low": confirm_share is not None and confirm_share < 0.1,
    }

    if total_trips == 0:
        status = "no_trips"
    elif flags["confirm_share_low"]:
        status = "warn_low_confirm_share"
    else:
        status = "ok"

    meta: Dict[str, Any] = {
        "status": status,
        "total_trips": total_trips,
        "last_day": last_day.isoformat() if last_day is not None else None,
        "last_day_trips": last_day_trips,
        "confirm_events": confirm_events,
        "noop_events": noop_events,
        "confirm_share": confirm_share,
        "plans_seen": sorted(plans_set),
        "flags": flags,
    }

    return meta


@shared_task(
    name="agents.autoplan.guard",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_autoplan_guard(self, days_back: int = 3) -> Dict[str, Any]:
    """
    Advisory-агент наблюдения за автопланом.

    Делает лёгкую выборку за последние N дней:
      • public.autoplan_audit:
          - агрегация по дням/планам/решениям;
          - топ-20 причин (decision/reason).
      • analytics.autoplan_trips_daily_v:
          - количество рейсов / событий / выручка по дням/планам.
      • analytics.autoplan_trips_vs_market_v:
          - количество и сумма рейсов по дням/планам (vs рынок).

    Ничего не пишет в БД, только читает.
    Если какая-то витрина отсутствует, пишет ошибку в payload.errors,
    но не падает целиком (advisory-режим).
    """
    window_days = _safe_int(days_back, default=3, min_val=1, max_val=30)

    payload: Dict[str, Any] = {
        "ok": True,
        "ts": _utcnow_iso(),
        "days_back": window_days,
        "summary": {},
        "errors": {},
        # meta добавим ниже, когда посчитаем
    }

    try:
        with _connect_pg() as conn:
            # 1) audit_by_day
            try:
                payload["summary"]["audit_by_day"] = _query_autoplan_audit_summary(
                    conn,
                    window_days,
                )
            except Exception as e:
                logger.warning("agents.autoplan.guard: audit_by_day failed: %r", e)
                payload["errors"]["audit_by_day"] = str(e)

            # 2) top_reasons
            try:
                payload["summary"]["top_reasons"] = _query_autoplan_audit_top_reasons(
                    conn,
                    window_days,
                )
            except Exception as e:
                logger.warning("agents.autoplan.guard: top_reasons failed: %r", e)
                payload["errors"]["top_reasons"] = str(e)

            # 3) trips_vs_market
            try:
                payload["summary"]["trips_vs_market"] = (
                    _query_autoplan_trips_vs_market(
                        conn,
                        window_days,
                    )
                )
            except Exception as e:
                logger.warning(
                    "agents.autoplan.guard: trips_vs_market failed (maybe view missing?): %r",
                    e,
                )
                payload["errors"]["trips_vs_market"] = str(e)

            # 4) trips_daily (KPI по нашей новой витрине)
            try:
                payload["summary"]["trips_daily"] = _query_autoplan_trips_daily(
                    conn,
                    window_days,
                )
            except Exception as e:
                logger.warning(
                    "agents.autoplan.guard: trips_daily failed (maybe view missing?): %r",
                    e,
                )
                payload["errors"]["trips_daily"] = str(e)

    except Exception as e:
        logger.exception("agents.autoplan.guard: database-level failure")
        payload["ok"] = False
        payload["errors"]["db"] = str(e)
        # meta посчитаем ниже из того, что удалось собрать (скорее всего пусто)

    # Пытаемся собрать свернутую мета-информацию даже если часть запросов упала
    try:
        payload["meta"] = _build_guard_meta(payload.get("summary") or {})
        logger.info("agents.autoplan.guard: meta=%s", payload["meta"])
    except Exception as e:
        logger.warning("agents.autoplan.guard: meta build failed: %r", e)
        payload.setdefault("errors", {})["meta"] = str(e)

    return payload
