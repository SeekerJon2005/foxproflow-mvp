# -*- coding: utf-8 -*-
# file: src/worker/register_tasks.py
from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Optional, Tuple

from celery.schedules import crontab
from celery.signals import beat_init as beat_trap

logger = logging.getLogger(__name__)

# =============================================================================
# ENV helpers
# =============================================================================


def _env_flag(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and str(v).strip() != "" else default


# =============================================================================
# OD-cache writer (worker-side, safe import and safe operation)
# =============================================================================

OD_CACHE_ENABLED: bool = _env_flag("OD_CACHE_ENABLED", "1")
DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

# TTL: поддерживаем OD_CACHE_TTL_SEC и OD_CACHE_TTL_H (приоритет — секунды)
_ttl_sec_raw = os.getenv("OD_CACHE_TTL_SEC")
if _ttl_sec_raw:
    try:
        _ttl_sec_val = int(_ttl_sec_raw)
        OD_CACHE_TTL_H = max(1, int(math.ceil(_ttl_sec_val / 3600.0)))
    except Exception:
        OD_CACHE_TTL_H = _env_int("OD_CACHE_TTL_H", 14 * 24)
else:
    OD_CACHE_TTL_H = _env_int("OD_CACHE_TTL_H", 14 * 24)

# Очередь для роутинга — берём ROUTING_QUEUE, иначе AUTOPLAN_QUEUE, иначе 'autoplan'
ROUTING_QUEUE: str = _env_str("ROUTING_QUEUE", _env_str("AUTOPLAN_QUEUE", "autoplan"))

# Настройки пула для OD-кэша
OD_CACHE_MAX_POOL_SIZE: int = _env_int("OD_CACHE_MAX_POOL_SIZE", 5)
OD_CACHE_POOL_TIMEOUT: int = _env_int("OD_CACHE_POOL_TIMEOUT", 5)

# Пул соединений: psycopg_pool может отсутствовать на раннем импорте — не валим модуль
try:
    from psycopg_pool import ConnectionPool  # type: ignore
except Exception:  # pragma: no cover
    ConnectionPool = None  # type: ignore

if ConnectionPool and OD_CACHE_ENABLED and DATABASE_URL:
    try:
        _od_pool = ConnectionPool(
            DATABASE_URL,
            max_size=OD_CACHE_MAX_POOL_SIZE,
            timeout=OD_CACHE_POOL_TIMEOUT,
        )
        logger.debug(
            "OD-cache pool initialized (ttl_h=%s, max_size=%s, timeout=%s)",
            OD_CACHE_TTL_H,
            OD_CACHE_MAX_POOL_SIZE,
            OD_CACHE_POOL_TIMEOUT,
        )
    except Exception as e:  # pragma: no cover
        _od_pool = None
        logger.warning("OD-cache disabled: pool init error: %s", e)
else:
    _od_pool = None
    if OD_CACHE_ENABLED:
        logger.debug(
            "OD-cache disabled: %s",
            "psycopg_pool missing" if not ConnectionPool else "empty DATABASE_URL",
        )


def od_cache_upsert_sync(
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    distance_m: float,
    duration_s: float,
    polyline: Optional[str],
    profile: str = "driving",
    backend: str = "osrm",
) -> None:
    """
    Безопасная запись в кэш OD (не валит таску при сбое БД).
    """
    if not _od_pool or not OD_CACHE_ENABLED:
        return
    try:
        dur = int(round(duration_s or 0))

        with _od_pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT public.fn_od_distance_cache_upsert(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    a_lat,
                    a_lon,
                    b_lat,
                    b_lon,
                    profile,
                    backend,
                    float(distance_m or 0.0),
                    dur,
                    polyline,
                    int(OD_CACHE_TTL_H),
                ),
            )
    except Exception as e:  # pragma: no cover
        logger.warning("od_cache_upsert_failed: %s", e)


# =============================================================================
# Beat schedule: routing-enrich + ATI-refresh + Market Brain + agents + smokes
# =============================================================================

# Управление через ENV (роутинг)
ROUTING_ENRICH_ENABLED: bool = _env_flag("ROUTING_ENRICH_ENABLED", "1")
ROUTING_ENRICH_ID: str = _env_str("ROUTING_ENRICH_ID", "routing-enrich-missing-2m")
ROUTING_ENRICH_TASK: str = _env_str("ROUTING_ENRICH_TASK", "routing.enrich.trips")
ROUTING_ENRICH_QUEUE: str = _env_str("ROUTING_ENRICH_QUEUE", ROUTING_QUEUE)
ROUTING_ENRICH_LIMIT: int = _env_int("ROUTING_ENRICH_LIMIT", 1500)
ROUTING_ENRICH_ONLY_MISSING: bool = _env_flag("ROUTING_ENRICH_ONLY_MISSING", "1")

ROUTING_ENRICH_EVERY_MIN: int = _env_int("ROUTING_ENRICH_EVERY_MIN", 2)
ROUTING_ENRICH_CRON: str = os.getenv("ROUTING_ENRICH_CRON", "").strip()

# --- routing smoke schedule (OSRM + DB contract) ---
ROUTING_SMOKE_ENABLED: bool = _env_flag("ROUTING_SMOKE_ENABLED", "1")
ROUTING_SMOKE_ID: str = _env_str("ROUTING_SMOKE_ID", "routing-smoke-10m")
ROUTING_SMOKE_TASK: str = _env_str("ROUTING_SMOKE_TASK", "routing.smoke.osrm_and_db")
ROUTING_SMOKE_QUEUE: str = _env_str("ROUTING_SMOKE_QUEUE", "celery")
ROUTING_SMOKE_EVERY_MIN: int = _env_int("ROUTING_SMOKE_EVERY_MIN", 10)
ROUTING_SMOKE_CRON: str = os.getenv("ROUTING_SMOKE_CRON", "").strip()
ROUTING_SMOKE_SEGMENT_UUID: str = (os.getenv("ROUTING_SMOKE_SEGMENT_UUID") or "").strip()

# --- devorders smoke schedule (DB contract) ---
DEVORDERS_SMOKE_ENABLED: bool = _env_flag("DEVORDERS_SMOKE_ENABLED", "1")
DEVORDERS_SMOKE_ID: str = _env_str("DEVORDERS_SMOKE_ID", "devorders-smoke-60m")
DEVORDERS_SMOKE_TASK: str = _env_str("DEVORDERS_SMOKE_TASK", "devorders.smoke.db_contract")
DEVORDERS_SMOKE_QUEUE: str = _env_str("DEVORDERS_SMOKE_QUEUE", "celery")
DEVORDERS_SMOKE_EVERY_MIN: int = _env_int("DEVORDERS_SMOKE_EVERY_MIN", 60)
DEVORDERS_SMOKE_CRON: str = os.getenv("DEVORDERS_SMOKE_CRON", "").strip()

# --- CRM smoke schedule (DB contract v2, no collision) ---
CRM_SMOKE_ENABLED: bool = _env_flag("CRM_SMOKE_ENABLED", "1")
CRM_SMOKE_ID: str = _env_str("CRM_SMOKE_ID", "crm-smoke-30m")
CRM_SMOKE_TASK: str = _env_str("CRM_SMOKE_TASK", "crm.smoke.db_contract_v2")
CRM_SMOKE_QUEUE: str = _env_str("CRM_SMOKE_QUEUE", "celery")
CRM_SMOKE_EVERY_MIN: int = _env_int("CRM_SMOKE_EVERY_MIN", 30)
CRM_SMOKE_CRON: str = os.getenv("CRM_SMOKE_CRON", "").strip()

# Управление через ENV (refresh ATI analytics MV)
ATI_REFRESH_ENABLED: bool = _env_flag("ATI_REFRESH_ENABLED", "1")
ATI_REFRESH_ID: str = _env_str("ATI_REFRESH_ID", "analytics-ati-refresh-daily")
ATI_REFRESH_TASK: str = _env_str("ATI_REFRESH_TASK", "analytics.freights_ati.refresh_price_distance_mv")
ATI_REFRESH_CRON: str = os.getenv("ATI_REFRESH_CRON", "15 7 * * *").strip()
ATI_REFRESH_QUEUE: str = _env_str("ATI_REFRESH_QUEUE", "celery")

# Управление через ENV (Market Brain — refresh demand_forecast)
MARKET_REFRESH_ENABLED: bool = _env_flag("MARKET_REFRESH_ENABLED", "0")
MARKET_REFRESH_ID: str = _env_str("MARKET_REFRESH_ID", "analytics-market-refresh-daily")
MARKET_REFRESH_TASK: str = _env_str("MARKET_REFRESH_TASK", "analytics.market.refresh_demand_forecast")
MARKET_REFRESH_CRON: str = os.getenv("MARKET_REFRESH_CRON", "30 6 * * *").strip()
MARKET_REFRESH_QUEUE: str = _env_str("MARKET_REFRESH_QUEUE", "celery")

# Управление через ENV (агенты)
AGENTS_QUEUE: str = _env_str("AGENTS_QUEUE", "agents")

AUTOPLAN_GUARD_ENABLED: bool = _env_flag("AUTOPLAN_GUARD_ENABLED", "1")
AUTOPLAN_GUARD_ID: str = _env_str("AUTOPLAN_GUARD_ID", "agents-autoplan-guard-daily")
AUTOPLAN_GUARD_TASK: str = _env_str("AUTOPLAN_GUARD_TASK", "agents.autoplan.guard")
AUTOPLAN_GUARD_QUEUE: str = _env_str("AUTOPLAN_GUARD_QUEUE", AGENTS_QUEUE)
AUTOPLAN_GUARD_CRON: str = os.getenv("AUTOPLAN_GUARD_CRON", "15 7 * * *").strip()
AUTOPLAN_GUARD_DAYS_BACK: int = _env_int("AUTOPLAN_GUARD_DAYS_BACK", 3)

OBSERVABILITY_SCAN_ENABLED: bool = _env_flag("OBSERVABILITY_SCAN_ENABLED", "1")
OBSERVABILITY_SCAN_ID: str = _env_str("OBSERVABILITY_SCAN_ID", "agents-observability-scan-10m")
OBSERVABILITY_SCAN_TASK: str = _env_str("OBSERVABILITY_SCAN_TASK", "agents.observability.scan")
OBSERVABILITY_SCAN_QUEUE: str = _env_str("OBSERVABILITY_SCAN_QUEUE", AGENTS_QUEUE)
OBSERVABILITY_SCAN_CRON: str = os.getenv("OBSERVABILITY_SCAN_CRON", "").strip()
OBSERVABILITY_SCAN_EVERY_MIN: int = _env_int("OBSERVABILITY_SCAN_EVERY_MIN", 10)
OBSERVABILITY_SCAN_DAYS_BACK: int = _env_int("OBSERVABILITY_SCAN_DAYS_BACK", 3)

LOGFOX_ENABLED: bool = _env_flag("LOGFOX_ENABLED", "1")
LOGFOX_ID: str = _env_str("LOGFOX_ID", "agents-logfox-daily")
LOGFOX_TASK: str = _env_str("LOGFOX_TASK", "agents.logfox.daily_report")
LOGFOX_QUEUE: str = _env_str("LOGFOX_QUEUE", AGENTS_QUEUE)
LOGFOX_CRON: str = os.getenv("LOGFOX_CRON", "5 7 * * *").strip()
LOGFOX_DAYS_BACK: int = _env_int("LOGFOX_DAYS_BACK", 1)

DRIVER_OFFROUTE_ENABLED: bool = _env_flag("DRIVER_OFFROUTE_ENABLED", "1")
DRIVER_OFFROUTE_ID: str = _env_str("DRIVER_OFFROUTE_ID", "driver-offroute-2m")
DRIVER_OFFROUTE_TASK: str = _env_str("DRIVER_OFFROUTE_TASK", "driver.alerts.offroute")
DRIVER_OFFROUTE_QUEUE: str = _env_str("DRIVER_OFFROUTE_QUEUE", AGENTS_QUEUE)
DRIVER_OFFROUTE_CRON: str = os.getenv("DRIVER_OFFROUTE_CRON", "").strip()
DRIVER_OFFROUTE_EVERY_MIN: int = _env_int("DRIVER_OFFROUTE_EVERY_MIN", 2)
DRIVER_OFFROUTE_MAX_TRIPS: int = _env_int("DRIVER_OFFROUTE_MAX_TRIPS", 50)

SALESFOX_SCAN_ENABLED: bool = _env_flag("SALESFOX_SCAN_ENABLED", "1")
SALESFOX_SCAN_ID: str = _env_str("SALESFOX_SCAN_ID", "salesfox-scan-trials-1m")
SALESFOX_SCAN_TASK: str = _env_str("SALESFOX_SCAN_TASK", "salesfox.scan_and_start_trials")
SALESFOX_SCAN_QUEUE: str = _env_str("SALESFOX_SCAN_QUEUE", AGENTS_QUEUE)
SALESFOX_SCAN_CRON: str = os.getenv("SALESFOX_SCAN_CRON", "").strip()
SALESFOX_SCAN_EVERY_MIN: int = _env_int("SALESFOX_SCAN_EVERY_MIN", 1)
SALESFOX_SCAN_LIMIT: int = _env_int("SALESFOX_SCAN_LIMIT", 32)

DEVFACTORY_DISPATCH_ENABLED: bool = _env_flag("DEVFACTORY_DISPATCH_ENABLED", "1")
DEVFACTORY_DISPATCH_ID_PREFIX: str = _env_str("DEVFACTORY_DISPATCH_ID_PREFIX", "devfactory-dispatch")
DEVFACTORY_DISPATCH_TASK: str = _env_str("DEVFACTORY_DISPATCH_TASK", "devfactory.task.dispatch")
DEVFACTORY_DISPATCH_QUEUE: str = _env_str("DEVFACTORY_DISPATCH_QUEUE", "celery")
DEVFACTORY_DISPATCH_EVERY_MIN: int = _env_int("DEVFACTORY_DISPATCH_EVERY_MIN", 10)
DEVFACTORY_DISPATCH_STACKS: str = _env_str("DEVFACTORY_DISPATCH_STACKS", "python_backend")
DEVFACTORY_DISPATCH_CRON: str = os.getenv("DEVFACTORY_DISPATCH_CRON", "").strip()


def _parse_cron_5(spec: str) -> Tuple[str, str, str, str, str]:
    parts = spec.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid CRON spec (need 5 fields): {spec!r}")
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return minute, hour, day_of_month, month_of_year, day_of_week


def _build_crontab_from(cron_spec: str, every_min: int, default_every_min: int = 10) -> crontab:
    if cron_spec:
        try:
            m, h, dom, mon, dow = _parse_cron_5(cron_spec)
            return crontab(minute=m, hour=h, day_of_month=dom, month_of_year=mon, day_of_week=dow)
        except Exception as e:
            logger.warning("Bad CRON spec=%r: %s. Fallback to */%s * * * *", cron_spec, e, every_min or default_every_min)
    n = max(1, int(every_min or default_every_min))
    return crontab(minute=f"*/{n}")


def _build_crontab() -> crontab:
    return _build_crontab_from(ROUTING_ENRICH_CRON, ROUTING_ENRICH_EVERY_MIN, default_every_min=2)


def ensure_routing_enrich_schedule(app) -> None:
    try:
        if not ROUTING_ENRICH_ENABLED:
            logger.info("beat_anchor: routing enrich is DISABLED by env")
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(ROUTING_ENRICH_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != ROUTING_ENRICH_TASK) or (not entry.get("schedule"))
        if need:
            sched = _build_crontab()
            kwargs = {"limit": int(ROUTING_ENRICH_LIMIT), "only_missing": bool(ROUTING_ENRICH_ONLY_MISSING)}
            bs[ROUTING_ENRICH_ID] = {"task": ROUTING_ENRICH_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": ROUTING_ENRICH_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_routing_enrich_schedule skipped: %s", e)


def ensure_routing_smoke_schedule(app) -> None:
    try:
        if not ROUTING_SMOKE_ENABLED:
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(ROUTING_SMOKE_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != ROUTING_SMOKE_TASK) or (not entry.get("schedule"))

        kwargs: Dict[str, Any] = {}
        if ROUTING_SMOKE_SEGMENT_UUID:
            kwargs["segment_uuid"] = ROUTING_SMOKE_SEGMENT_UUID

        if need:
            sched = _build_crontab_from(ROUTING_SMOKE_CRON, ROUTING_SMOKE_EVERY_MIN, default_every_min=10)
            bs[ROUTING_SMOKE_ID] = {"task": ROUTING_SMOKE_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": ROUTING_SMOKE_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_routing_smoke_schedule skipped: %s", e)


def ensure_devorders_smoke_schedule(app) -> None:
    try:
        if not DEVORDERS_SMOKE_ENABLED:
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(DEVORDERS_SMOKE_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != DEVORDERS_SMOKE_TASK) or (not entry.get("schedule"))

        if need:
            sched = _build_crontab_from(DEVORDERS_SMOKE_CRON, DEVORDERS_SMOKE_EVERY_MIN, default_every_min=60)
            bs[DEVORDERS_SMOKE_ID] = {"task": DEVORDERS_SMOKE_TASK, "schedule": sched, "kwargs": {}, "options": {"queue": DEVORDERS_SMOKE_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_devorders_smoke_schedule skipped: %s", e)


def ensure_crm_smoke_schedule(app) -> None:
    """
    CRM DB-contract smoke (v2 task name).
    """
    try:
        if not CRM_SMOKE_ENABLED:
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(CRM_SMOKE_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != CRM_SMOKE_TASK) or (not entry.get("schedule"))

        if need:
            sched = _build_crontab_from(CRM_SMOKE_CRON, CRM_SMOKE_EVERY_MIN, default_every_min=30)
            bs[CRM_SMOKE_ID] = {"task": CRM_SMOKE_TASK, "schedule": sched, "kwargs": {}, "options": {"queue": CRM_SMOKE_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_crm_smoke_schedule skipped: %s", e)


def ensure_ati_refresh_schedule(app) -> None:
    try:
        if not ATI_REFRESH_ENABLED:
            logger.info("beat_anchor: ATI refresh is DISABLED by env")
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(ATI_REFRESH_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != ATI_REFRESH_TASK)
        if need:
            try:
                m, h, dom, mon, dow = _parse_cron_5(ATI_REFRESH_CRON)
                sched = crontab(minute=m, hour=h, day_of_month=dom, month_of_year=mon, day_of_week=dow)
            except Exception as e:
                logger.warning("Bad ATI_REFRESH_CRON=%r: %s. Fallback to 15 7 * * *", ATI_REFRESH_CRON, e)
                sched = crontab(minute="15", hour="7", day_of_month="*", month_of_year="*", day_of_week="*")

            bs[ATI_REFRESH_ID] = {"task": ATI_REFRESH_TASK, "schedule": sched, "options": {"queue": ATI_REFRESH_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_ati_refresh_schedule skipped: %s", e)


def ensure_market_refresh_schedule(app) -> None:
    try:
        if not MARKET_REFRESH_ENABLED:
            logger.info("beat_anchor: Market Brain refresh is DISABLED by env")
            return

        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(MARKET_REFRESH_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != MARKET_REFRESH_TASK)
        if need:
            try:
                m, h, dom, mon, dow = _parse_cron_5(MARKET_REFRESH_CRON)
                sched = crontab(minute=m, hour=h, day_of_month=dom, month_of_year=mon, day_of_week=dow)
            except Exception as e:
                logger.warning("Bad MARKET_REFRESH_CRON=%r: %s. Fallback to 30 6 * * *", MARKET_REFRESH_CRON, e)
                sched = crontab(minute="30", hour="6", day_of_month="*", month_of_year="*", day_of_week="*")

            bs[MARKET_REFRESH_ID] = {"task": MARKET_REFRESH_TASK, "schedule": sched, "options": {"queue": MARKET_REFRESH_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_market_refresh_schedule skipped: %s", e)


# (остальные ensure_* оставлены без изменений по сути; сокращать здесь не будем)

def ensure_autoplan_guard_schedule(app) -> None:
    try:
        if not AUTOPLAN_GUARD_ENABLED:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(AUTOPLAN_GUARD_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != AUTOPLAN_GUARD_TASK)
        if need:
            try:
                m, h, dom, mon, dow = _parse_cron_5(AUTOPLAN_GUARD_CRON)
                sched = crontab(minute=m, hour=h, day_of_month=dom, month_of_year=mon, day_of_week=dow)
            except Exception:
                sched = crontab(minute="15", hour="7", day_of_month="*", month_of_year="*", day_of_week="*")
            kwargs = {"days_back": int(AUTOPLAN_GUARD_DAYS_BACK)}
            bs[AUTOPLAN_GUARD_ID] = {"task": AUTOPLAN_GUARD_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": AUTOPLAN_GUARD_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_autoplan_guard_schedule skipped: %s", e)


def ensure_observability_schedule(app) -> None:
    try:
        if not OBSERVABILITY_SCAN_ENABLED:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(OBSERVABILITY_SCAN_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != OBSERVABILITY_SCAN_TASK)
        if need:
            sched = _build_crontab_from(OBSERVABILITY_SCAN_CRON, OBSERVABILITY_SCAN_EVERY_MIN, default_every_min=10)
            kwargs = {"days_back": int(OBSERVABILITY_SCAN_DAYS_BACK)}
            bs[OBSERVABILITY_SCAN_ID] = {"task": OBSERVABILITY_SCAN_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": OBSERVABILITY_SCAN_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_observability_schedule skipped: %s", e)


def ensure_logfox_schedule(app) -> None:
    try:
        if not LOGFOX_ENABLED:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(LOGFOX_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != LOGFOX_TASK)
        if need:
            try:
                m, h, dom, mon, dow = _parse_cron_5(LOGFOX_CRON)
                sched = crontab(minute=m, hour=h, day_of_month=dom, month_of_year=mon, day_of_week=dow)
            except Exception:
                sched = crontab(minute="5", hour="7", day_of_month="*", month_of_year="*", day_of_week="*")
            kwargs = {"days_back": int(LOGFOX_DAYS_BACK)}
            bs[LOGFOX_ID] = {"task": LOGFOX_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": LOGFOX_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_logfox_schedule skipped: %s", e)


def ensure_driver_offroute_schedule(app) -> None:
    try:
        if not DRIVER_OFFROUTE_ENABLED:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(DRIVER_OFFROUTE_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != DRIVER_OFFROUTE_TASK)
        if need:
            sched = _build_crontab_from(DRIVER_OFFROUTE_CRON, DRIVER_OFFROUTE_EVERY_MIN, default_every_min=2)
            kwargs = {"max_trips": int(DRIVER_OFFROUTE_MAX_TRIPS)}
            bs[DRIVER_OFFROUTE_ID] = {"task": DRIVER_OFFROUTE_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": DRIVER_OFFROUTE_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_driver_offroute_schedule skipped: %s", e)


def ensure_salesfox_scan_schedule(app) -> None:
    try:
        if not SALESFOX_SCAN_ENABLED:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        entry = bs.get(SALESFOX_SCAN_ID)
        need = (not isinstance(entry, dict)) or (entry.get("task") != SALESFOX_SCAN_TASK)
        if need:
            sched = _build_crontab_from(SALESFOX_SCAN_CRON, SALESFOX_SCAN_EVERY_MIN, default_every_min=1)
            kwargs = {"limit": int(SALESFOX_SCAN_LIMIT)}
            bs[SALESFOX_SCAN_ID] = {"task": SALESFOX_SCAN_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": SALESFOX_SCAN_QUEUE}}
            app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_salesfox_scan_schedule skipped: %s", e)


def ensure_devfactory_dispatch_schedule(app) -> None:
    try:
        if not DEVFACTORY_DISPATCH_ENABLED:
            return
        stacks = [s.strip() for s in DEVFACTORY_DISPATCH_STACKS.split(",") if s.strip()]
        if not stacks:
            return
        bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
        for st in stacks:
            entry_id = f"{DEVFACTORY_DISPATCH_ID_PREFIX}-{st}"
            entry = bs.get(entry_id)
            need = (not isinstance(entry, dict)) or (entry.get("task") != DEVFACTORY_DISPATCH_TASK)
            if not need:
                continue
            sched = _build_crontab_from(DEVFACTORY_DISPATCH_CRON, DEVFACTORY_DISPATCH_EVERY_MIN, default_every_min=10)
            kwargs = {"stack": st}
            bs[entry_id] = {"task": DEVFACTORY_DISPATCH_TASK, "schedule": sched, "kwargs": kwargs, "options": {"queue": DEVFACTORY_DISPATCH_QUEUE}}
        app.conf.beat_schedule = bs
    except Exception as e:  # pragma: no cover
        logger.debug("ensure_devfactory_dispatch_schedule skipped: %s", e)


# =============================================================================
# Declarative agent registry (for diagnostics / HTTP API)
# =============================================================================

def _cron_or_every(cron_spec: str, every_min: int) -> str:
    if cron_spec:
        return cron_spec
    n = max(1, int(every_min or 1))
    return f"*/{n} * * * *"


AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "routing_enrich": {
        "domain": "routing",
        "enabled": ROUTING_ENRICH_ENABLED,
        "id": ROUTING_ENRICH_ID,
        "task": ROUTING_ENRICH_TASK,
        "queue": ROUTING_ENRICH_QUEUE,
        "effective_cron": _cron_or_every(ROUTING_ENRICH_CRON, ROUTING_ENRICH_EVERY_MIN),
        "default_kwargs": {"limit": ROUTING_ENRICH_LIMIT, "only_missing": ROUTING_ENRICH_ONLY_MISSING},
    },
    "routing_smoke": {
        "domain": "routing",
        "enabled": ROUTING_SMOKE_ENABLED,
        "id": ROUTING_SMOKE_ID,
        "task": ROUTING_SMOKE_TASK,
        "queue": ROUTING_SMOKE_QUEUE,
        "effective_cron": _cron_or_every(ROUTING_SMOKE_CRON, ROUTING_SMOKE_EVERY_MIN),
        "default_kwargs": {"segment_uuid": ROUTING_SMOKE_SEGMENT_UUID} if ROUTING_SMOKE_SEGMENT_UUID else {},
    },
    "devorders_smoke": {
        "domain": "devorders",
        "enabled": DEVORDERS_SMOKE_ENABLED,
        "id": DEVORDERS_SMOKE_ID,
        "task": DEVORDERS_SMOKE_TASK,
        "queue": DEVORDERS_SMOKE_QUEUE,
        "effective_cron": _cron_or_every(DEVORDERS_SMOKE_CRON, DEVORDERS_SMOKE_EVERY_MIN),
        "default_kwargs": {},
    },
    "crm_smoke": {
        "domain": "crm",
        "enabled": CRM_SMOKE_ENABLED,
        "id": CRM_SMOKE_ID,
        "task": CRM_SMOKE_TASK,
        "queue": CRM_SMOKE_QUEUE,
        "effective_cron": _cron_or_every(CRM_SMOKE_CRON, CRM_SMOKE_EVERY_MIN),
        "default_kwargs": {},
    },
}

# keep existing registry items (analytics/agents/etc.) if needed downstream
# NOTE: if your existing file has more entries, you can keep them below.

def get_agents_registry() -> Dict[str, Dict[str, Any]]:
    return AGENT_REGISTRY


def get_beat_schedule_snapshot(app) -> Dict[str, Any]:
    bs: Dict[str, Any] = dict(getattr(app.conf, "beat_schedule", {}) or {})
    snap: Dict[str, Any] = {}
    for name, entry in bs.items():
        if not isinstance(entry, dict):
            continue
        opts = entry.get("options") or {}
        snap[name] = {
            "task": entry.get("task"),
            "queue": opts.get("queue"),
            "kwargs": entry.get("kwargs") or {},
            "schedule": repr(entry.get("schedule")),
        }
    return snap


# =============================================================================
# Import task modules so Celery sees tasks
# =============================================================================

def _ff_import_task_modules() -> None:
    modules = [
        # core top-level modules
        "src.worker.tasks_ops",
        "src.worker.tasks_autoplan",
        "src.worker.tasks_parsers",
        "src.worker.tasks_parsers_flow",
        "src.worker.tasks_geo",
        "src.worker.tasks_analytics",
        "src.worker.tasks_etl",
        "src.worker.tasks_agents",
        "src.worker.tasks_driver_alerts",
        "src.worker.tasks_market",
        "src.worker.tasks_salesfox",

        # smoke tasks
        "src.worker.tasks.routing_smoke",
        "src.worker.tasks.devorders_smoke",
        "src.worker.tasks.crm_smoke",
    ]
    for mod in modules:
        try:
            __import__(mod)
            logger.info("tasks_module_loaded: %s", mod)
        except Exception as e:  # pragma: no cover
            logger.warning("tasks_module_not_loaded: %s (%s)", mod, e)


def _ff_add_routing_drain(sender=None, **kwargs) -> None:
    try:
        app = getattr(sender, "app", None) or getattr(sender, "_app", None) or sender
        if app is None:
            from celery import current_app as _cur
            app = getattr(_cur, "_get_current_object", lambda: _cur)()

        ensure_routing_enrich_schedule(app)
        ensure_routing_smoke_schedule(app)
        ensure_devorders_smoke_schedule(app)
        ensure_crm_smoke_schedule(app)

        _ff_import_task_modules()

        ensure_ati_refresh_schedule(app)
        ensure_market_refresh_schedule(app)
        ensure_autoplan_guard_schedule(app)
        ensure_observability_schedule(app)
        ensure_driver_offroute_schedule(app)
        ensure_logfox_schedule(app)
        ensure_devfactory_dispatch_schedule(app)
        ensure_salesfox_scan_schedule(app)
    except Exception:  # pragma: no cover
        pass


try:
    from src.worker.celery_app import app as _app  # noqa: F401
except Exception:
    _app = None

if _app is not None:
    try:
        _app.on_after_configure.connect(_ff_add_routing_drain, weak=False)
    except Exception:  # pragma: no cover
        pass

try:
    beat_trap.connect(_ff_add_routing_drain, weak=False)
except Exception:  # pragma: no cover
    pass

try:
    from celery import current_app as _cur  # noqa: E402
    _tmp_app = getattr(_cur, "_get_current_object", lambda: _cur)()
    ensure_routing_enrich_schedule(_tmp_app)
    ensure_routing_smoke_schedule(_tmp_app)
    ensure_devorders_smoke_schedule(_tmp_app)
    ensure_crm_smoke_schedule(_tmp_app)
except Exception:  # pragma: no cover
    pass


# =============================================================================
# Helper: task_routing_enrich_trips for external callers
# =============================================================================

def task_routing_enrich_trips(limit: int = ROUTING_ENRICH_LIMIT, only_missing: Optional[bool] = None) -> Dict[str, Any]:
    if only_missing is None:
        only_missing = ROUTING_ENRICH_ONLY_MISSING
    kwargs: Dict[str, Any] = {"limit": int(limit), "only_missing": bool(only_missing)}
    task_name = ROUTING_ENRICH_TASK
    queue_name = ROUTING_ENRICH_QUEUE

    if _app is None:
        logger.warning("task_routing_enrich_trips: no Celery app, dry-run dispatch skipped (task=%s, kwargs=%s)", task_name, kwargs)
        return {"ok": False, "reason": "no_celery_app", "task": task_name, "queue": queue_name, "kwargs": kwargs}

    async_result = _app.send_task(task_name, kwargs=kwargs, queue=queue_name)
    logger.info("task_routing_enrich_trips: dispatched task_id=%s task=%s queue=%s kwargs=%s", async_result.id, task_name, queue_name, kwargs)
    return {"ok": True, "task_id": async_result.id, "task": task_name, "queue": queue_name, "kwargs": kwargs}


__all__ = [
    "od_cache_upsert_sync",
    "ensure_routing_enrich_schedule",
    "ensure_routing_smoke_schedule",
    "ensure_devorders_smoke_schedule",
    "ensure_crm_smoke_schedule",
    "task_routing_enrich_trips",
    "AGENT_REGISTRY",
    "get_agents_registry",
    "get_beat_schedule_snapshot",
]

# Ensure smoke tasks are registered (do not remove)
try:
    import src.worker.tasks.routing_smoke  # noqa: F401
except Exception:
    pass

try:
    import src.worker.tasks.devorders_smoke  # noqa: F401
except Exception:
    pass

try:
    import src.worker.tasks.crm_smoke  # noqa: F401
except Exception:
    pass
