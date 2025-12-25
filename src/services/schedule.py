# -*- coding: utf-8 -*-
"""
Celery Beat schedule for FoxProFlow.

Экспортирует:
  - BEAT_SCHEDULE: dict  (основной)
  - CELERY_BEAT_SCHEDULE: dict (зеркало для совместимости)

Переключатели через ENV (булевы: 1/true/yes/on):
  OPS/Health:
    ENABLE_BEAT_HEARTBEAT=1
    ENABLE_QUEUE_WATCHDOG=1
    ENABLE_SLA_ALERTS=1

  Materialized Views / Forecast:
    ENABLE_AVAILABILITY_REFRESH=1              # mv.refresh.vehicle_availability (ежечасно)
    ENABLE_FORECAST_REFRESH=1                  # forecast.refresh каждые N часов
    FORECAST_REFRESH_EVERY_HOURS=3

  Planner/KPI:
    ENABLE_HOURLY_REPLAN=1                     # planner.hourly.replan.all
    ENABLE_PLANNER_KPI_SNAPSHOT=1              # planner.kpi.snapshot (ежечасно)
    ENABLE_KPI_DAILY_REFRESH=1                 # sql.refresh.kpi_daily (ежедневно)
    KPI_DAILY_HOUR=7
    KPI_DAILY_MINUTE=0

  Autoplan (SAFE-пайплайн и/или цепочка):
    ENABLE_AUTOPLAN_SAFE=1                     # включает пофазный audit/apply/push/confirm
      ENABLE_AUTOPLAN_AUDIT=1
      ENABLE_AUTOPLAN_APPLY=1
      ENABLE_AUTOPLAN_PUSH=1
      ENABLE_AUTOPLAN_CONFIRM=1
      AUTOPLAN_PHASE_LIMIT=10
    ENABLE_AUTOPLAN_CHAIN=1                    # task_autoplan_chain (часовая)
      AUTOPLAN_CHAIN_LIMIT=80
      AUTOPLAN_CHAIN_WRITE_AUDIT=1
    ENABLE_AUTOPLAN_HARDENING=1                # settle/backlog_stats интервальные

  Parsers (ATI):
    ENABLE_PARSER_ATI_FREIGHTS=1
    ENABLE_PARSER_ATI_TRUCKS=0
    ENABLE_PARSERS_WATCHDOG=1
    ENABLE_DEMO_FREIGHTS_HEARTBEAT=0           # опционально: пульс демо-фрахтов 30м

  Agents (advisory-first):
    AGENTS_ENABLE=0
    AGENTS_MODE=advisory                        # справочно; частоты не меняет
    AGENTS_KPI_HOUR=7                           # ежедневный отчёт агентов
    AGENTS_QUEUE=default

Очереди (по умолчанию):
  CELERY_DEFAULT_QUEUE=default
  AUTOPLAN_QUEUE=autoplan
  PARSERS_QUEUE=parsers
"""

import os
from celery.schedules import crontab
from celery.schedules import schedule as interval_schedule


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(str(os.getenv(key, default)).strip())
    except Exception:
        return default


def _every(seconds: int) -> interval_schedule:
    """Удобный алиас для интервальных расписаний в секундах."""
    return interval_schedule(seconds)


# Очереди
DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE", "default")
AUTOPLAN_QUEUE = os.getenv("AUTOPLAN_QUEUE", "autoplan")
PARSERS_QUEUE = os.getenv("PARSERS_QUEUE", "parsers")
AGENTS_QUEUE = os.getenv("AGENTS_QUEUE", DEFAULT_QUEUE)

# ---------------------------------------------------------------------------
# ЕДИНЫЙ СЛОВАРЬ РАСПИСАНИЯ
# ---------------------------------------------------------------------------
BEAT_SCHEDULE: dict = {}

# ---------------------------------------------------------------------------
# OPS / HEALTH
# ---------------------------------------------------------------------------
if _env_bool("ENABLE_BEAT_HEARTBEAT", True):
    BEAT_SCHEDULE["beat-heartbeat-1m"] = {
        "task": "ops.beat.heartbeat",
        "schedule": crontab(minute="*/1"),
        "options": {"queue": DEFAULT_QUEUE},
    }

if _env_bool("ENABLE_QUEUE_WATCHDOG", True):
    BEAT_SCHEDULE["queue-watchdog-5m"] = {
        "task": "ops.queue.watchdog",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": DEFAULT_QUEUE},
    }

if _env_bool("ENABLE_SLA_ALERTS", True):
    BEAT_SCHEDULE["ops-alerts-5m"] = {
        "task": "ops.alerts.sla",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": DEFAULT_QUEUE},
    }

# ---------------------------------------------------------------------------
# MATERIALIZED VIEWS / FORECAST
# ---------------------------------------------------------------------------
if _env_bool("ENABLE_AVAILABILITY_REFRESH", True):
    BEAT_SCHEDULE["mv-availability-refresh-hourly"] = {
        "task": "mv.refresh.vehicle_availability",
        "schedule": crontab(minute=0),  # каждый час в HH:00
        "options": {"queue": DEFAULT_QUEUE},
    }

if _env_bool("ENABLE_FORECAST_REFRESH", True):
    BEAT_SCHEDULE["forecast-refresh"] = {
        "task": "forecast.refresh",
        "schedule": crontab(minute=0, hour=f"*/{_env_int('FORECAST_REFRESH_EVERY_HOURS', 3)}"),
        "options": {"queue": DEFAULT_QUEUE},
    }

# ---------------------------------------------------------------------------
# PLANNER KPI / REPLAN
# ---------------------------------------------------------------------------
if _env_bool("ENABLE_HOURLY_REPLAN", True):
    BEAT_SCHEDULE["planner-hourly-replan-all"] = {
        "task": "planner.hourly.replan.all",
        "schedule": crontab(minute=5),  # HH:05
        "options": {"queue": DEFAULT_QUEUE},
    }

if _env_bool("ENABLE_PLANNER_KPI_SNAPSHOT", True):
    BEAT_SCHEDULE["planner-kpi-snapshot"] = {
        "task": "planner.kpi.snapshot",
        "schedule": crontab(minute=10),  # ежечасно в :10
        "options": {"queue": DEFAULT_QUEUE},
    }

if _env_bool("ENABLE_KPI_DAILY_REFRESH", True):
    BEAT_SCHEDULE["kpi-daily-refresh"] = {
        "task": "sql.refresh.kpi_daily",
        "schedule": crontab(
            hour=_env_int("KPI_DAILY_HOUR", 7),
            minute=_env_int("KPI_DAILY_MINUTE", 0),
        ),  # ежедневно
        "options": {"queue": DEFAULT_QUEUE},
    }

# ---------------------------------------------------------------------------
# AUTOPLAN PHASES (SAFE) + CHAIN + HARDENING
# ---------------------------------------------------------------------------
SAFE = _env_bool("ENABLE_AUTOPLAN_SAFE", True)
PH_LIMIT = _env_int("AUTOPLAN_PHASE_LIMIT", 10)

if SAFE and _env_bool("ENABLE_AUTOPLAN_AUDIT", True):
    BEAT_SCHEDULE["autoplan-audit-h06"] = {
        "task": "planner.autoplan.audit",
        "schedule": crontab(minute=6),  # HH:06
        "options": {"queue": AUTOPLAN_QUEUE},
    }

if SAFE and _env_bool("ENABLE_AUTOPLAN_APPLY", True):
    BEAT_SCHEDULE["autoplan-apply-h07"] = {
        "task": "planner.autoplan.apply",
        "schedule": crontab(minute=7),  # HH:07
        "kwargs": {"limit": PH_LIMIT},
        "options": {"queue": AUTOPLAN_QUEUE},
    }

if SAFE and _env_bool("ENABLE_AUTOPLAN_PUSH", True):
    BEAT_SCHEDULE["autoplan-push-h08"] = {
        "task": "planner.autoplan.push_to_trips",
        "schedule": crontab(minute=8),  # HH:08
        "kwargs": {"limit": PH_LIMIT, "status": "draft"},
        "options": {"queue": AUTOPLAN_QUEUE},
    }

if SAFE and _env_bool("ENABLE_AUTOPLAN_CONFIRM", True):
    BEAT_SCHEDULE["autoplan-confirm-h09"] = {
        "task": "planner.autoplan.confirm",
        "schedule": crontab(minute=9),  # HH:09
        "kwargs": {"limit": PH_LIMIT},
        "options": {"queue": AUTOPLAN_QUEUE},
    }

if _env_bool("ENABLE_AUTOPLAN_CHAIN", True):
    BEAT_SCHEDULE["autoplan-chain-hourly"] = {
        "task": "task_autoplan_chain",
        "schedule": crontab(minute=5),  # HH:05
        "kwargs": {
            "limit": _env_int("AUTOPLAN_CHAIN_LIMIT", 80),
            "write_audit": _env_bool("AUTOPLAN_CHAIN_WRITE_AUDIT", True),
        },
        "options": {"queue": AUTOPLAN_QUEUE},
    }

if _env_bool("ENABLE_AUTOPLAN_HARDENING", True):
    BEAT_SCHEDULE["autoplan-settle-10m"] = {
        "task": "planner.autoplan.settle",
        "schedule": _every(10 * 60),
        "options": {"queue": AUTOPLAN_QUEUE},
    }
    BEAT_SCHEDULE["autoplan-backlog-stats-5m"] = {
        "task": "planner.autoplan.backlog_stats",
        "schedule": _every(5 * 60),
        "options": {"queue": AUTOPLAN_QUEUE},
    }

# ---------------------------------------------------------------------------
# PARSERS: ATI (freights / trucks) + watchdog
# ---------------------------------------------------------------------------
if _env_bool("ENABLE_PARSER_ATI_FREIGHTS", True):
    BEAT_SCHEDULE.setdefault("parser-ati-freights-10m", {
        "task": "parser.ati.freights.pull",
        "schedule": _every(10 * 60),  # каждые 10 минут
        "options": {"queue": PARSERS_QUEUE},
    })

if _env_bool("ENABLE_PARSER_ATI_TRUCKS", False):
    BEAT_SCHEDULE.setdefault("parser-ati-trucks-15m", {
        "task": "parser.ati.trucks.pull",
        "schedule": _every(15 * 60),  # каждые 15 минут
        "options": {"queue": PARSERS_QUEUE},
    })

if _env_bool("ENABLE_PARSERS_WATCHDOG", True):
    BEAT_SCHEDULE.setdefault("parsers-watchdog-5m", {
        "task": "parsers.watchdog",
        "schedule": _every(5 * 60),  # каждые 5 минут
        "options": {"queue": PARSERS_QUEUE},
    })

# (опционально) «демо-сердцебиение» фрахтов на пилоте — чтобы лампа parsers была зелёной
if _env_bool("ENABLE_DEMO_FREIGHTS_HEARTBEAT", False):
    BEAT_SCHEDULE.setdefault("parser-freights-demo-30m", {
        "task": "parser.ati.freights.pull",
        "schedule": _every(30 * 60),  # каждые 30 минут
        "options": {"queue": PARSERS_QUEUE},
    })

# ---------------------------------------------------------------------------
# AGENTS (advisory-first) — включаются флагом AGENTS_ENABLE=1
# ---------------------------------------------------------------------------
if _env_bool("AGENTS_ENABLE", False):
    # Город→регион, безопасный white-list apply позже
    BEAT_SCHEDULE["agents-citymap-hourly"] = {
        "task": "agents.citymap.suggest",
        "schedule": crontab(minute=4),  # HH:04
        "options": {"queue": AGENTS_QUEUE},
    }
    # Доктор витрин: свежесть MVs/индексы/конкурентные refresh
    BEAT_SCHEDULE["agents-mv-doctor-10m"] = {
        "task": "agents.mv.doctor",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": AGENTS_QUEUE},
    }
    # Advisory отчёт KPI (ежедневно)
    BEAT_SCHEDULE["agents-kpi-report-daily"] = {
        "task": "agents.kpi.report",
        "schedule": crontab(
            hour=_env_int("AGENTS_KPI_HOUR", 7),
            minute=30
        ),
        "options": {"queue": AGENTS_QUEUE},
    }
    # Санити-страж перед автопланом
    BEAT_SCHEDULE["agents-guard-sanity-6m"] = {
        "task": "agents.guard.sanity",
        "schedule": crontab(minute="*/6"),
        "options": {"queue": AGENTS_QUEUE},
    }
    # Динамический RPM советник (advisory)
    BEAT_SCHEDULE["agents-dynrpm-advice-daily"] = {
        "task": "agents.dynrpm.advice",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": AGENTS_QUEUE},
    }

# ---------------------------------------------------------------------------
# ЗЕРКАЛО на случай, если загрузчик ищет CELERY_BEAT_SCHEDULE
# ---------------------------------------------------------------------------
CELERY_BEAT_SCHEDULE = BEAT_SCHEDULE
