# -*- coding: utf-8 -*-
"""
FoxProFlow Celery app bootstrap.

Goals:
- One import-safe module for celery app/beat/worker.
- Stable env parsing across Windows host + Docker Desktop.
- Hardened defaults, explicit broker/backend DSNs.
- Safe "force bind" (avoid 127.0.0.1/localhost inside containers).
- Deterministic task imports for Gate (worker inspect registered).

NOTE:
- This file must be import-safe: API routers may import Celery app for health/ops endpoints.
- Any exception at import-time can cascade into missing routers (e.g., /api/autoplan/* -> 404).

CRITICAL (Gate):
- Worker must register (live worker registry / inspect registered):
    - planner.kpi.snapshot
    - planner.kpi.daily_refresh
    - analytics.devfactory.daily
    - devfactory.commercial.run_order
Otherwise messages will be discarded as "Received unregistered task ...".
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sys
from typing import Any, Dict, Optional

from celery import Celery
from celery.schedules import crontab

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------

TRUE_SET = {"1", "true", "yes", "y", "on", "enable", "enabled"}
FALSE_SET = {"0", "false", "no", "n", "off", "disable", "disabled"}


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if v == "":
        return default
    s = str(v).strip().lower()
    if s in TRUE_SET:
        return True
    if s in FALSE_SET:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name, "")
    if v == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _safe_json_loads(v: Optional[str]) -> Optional[Dict[str, Any]]:
    if not v:
        return None
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _is_celery_worker_or_beat() -> bool:
    """
    True only for real `celery ... worker|beat ...` process.
    Avoid heavy bootstrap for API import and most celery CLI commands (inspect/report).
    """
    try:
        argv = [str(a).lower() for a in sys.argv]
        joined = " ".join(argv)
        if "celery" not in joined:
            return False
        return ("worker" in argv) or ("beat" in argv) or (" worker " in joined) or (" beat " in joined)
    except Exception:
        return False


# ---------------------------------------------------------------------
# Docker detection + DSN sanitization
# ---------------------------------------------------------------------


def _in_docker() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        if "docker" in txt or "kubepods" in txt or "containerd" in txt:
            return True
    except Exception:
        pass
    return False


def _replace_localhost_in_dsn(dsn: str, host: str) -> str:
    if not dsn:
        return dsn
    dsn = re.sub(r"(//)(localhost)([:/])", rf"\1{host}\3", dsn)
    dsn = re.sub(r"(@)(localhost)([:/])", rf"\1{host}\3", dsn)
    dsn = re.sub(r"(//)(127\.0\.0\.1)([:/])", rf"\1{host}\3", dsn)
    dsn = re.sub(r"(@)(127\.0\.0\.1)([:/])", rf"\1{host}\3", dsn)
    return dsn


def _dsn_scheme(dsn: str) -> str:
    try:
        return (dsn.split("://", 1)[0] or "").strip().lower()
    except Exception:
        return ""


def _sanitize_env_for_container() -> None:
    if not _in_docker():
        return

    pg_host = os.getenv("POSTGRES_HOST", "postgres")
    rd_host = os.getenv("REDIS_HOST", "redis")
    rb_host = os.getenv("RABBITMQ_HOST", "rabbitmq")

    def pick_host_for_dsn(dsn: str) -> str:
        s = _dsn_scheme(dsn)
        if s in {"postgres", "postgresql"}:
            return pg_host
        if s in {"redis", "rediss"}:
            return rd_host
        if s in {"amqp", "pyamqp"}:
            return rb_host
        return os.getenv("DOCKER_HOST_INTERNAL", "host.docker.internal")

    dsn_vars = [
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "REDIS_URL",
        "DATABASE_URL",
        "POSTGRES_DSN",
        "RABBITMQ_URL",
    ]
    for k in dsn_vars:
        v = os.getenv(k)
        if not v:
            continue
        v_str = str(v)
        if ("127.0.0.1" in v_str) or ("localhost" in v_str):
            os.environ[k] = _replace_localhost_in_dsn(v_str, pick_host_for_dsn(v_str))

    host_vars = [
        ("REDIS_HOST", rd_host),
        ("POSTGRES_HOST", pg_host),
        ("RABBITMQ_HOST", rb_host),
    ]
    for k, default_host in host_vars:
        v = os.getenv(k)
        if not v:
            continue
        v_str = str(v).strip().lower()
        if v_str in {"127.0.0.1", "localhost"}:
            os.environ[k] = default_host


# ---------------------------------------------------------------------
# DSN builders (redis/rabbit)
# ---------------------------------------------------------------------

_sanitize_env_for_container()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = _env_int("REDIS_PORT", 6379)
REDIS_DB_BROKER = _env_int("REDIS_DB", 0)
REDIS_DB_BACKEND = _env_int("REDIS_RESULT_DB", _env_int("REDIS_BACKEND_DB", 1))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = _env_int("RABBITMQ_PORT", 5672)
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")


def _build_redis_url(db_index: int) -> str:
    auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    return f"redis://{auth}{REDIS_HOST}:{REDIS_PORT}/{int(db_index)}"


def _build_rabbit_url() -> str:
    explicit = os.getenv("RABBITMQ_URL", "")
    if explicit:
        return explicit
    vhost = RABBITMQ_VHOST
    if vhost == "/":
        vhost = "%2F"
    return f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{vhost}"


# ---------------------------------------------------------------------
# Celery config
# ---------------------------------------------------------------------

USE_RABBITMQ = _env_bool("USE_RABBITMQ", False)

DEFAULT_REDIS_BROKER_URL = _build_redis_url(REDIS_DB_BROKER)
DEFAULT_REDIS_BACKEND_URL = _build_redis_url(REDIS_DB_BACKEND)
DEFAULT_RABBIT_URL = _build_rabbit_url()

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    DEFAULT_RABBIT_URL if USE_RABBITMQ else DEFAULT_REDIS_BROKER_URL,
)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", DEFAULT_REDIS_BACKEND_URL)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", os.getenv("TZ", "UTC"))
CELERY_ENABLE_UTC = _env_bool("CELERY_ENABLE_UTC", True)

CELERY_TASK_ACKS_LATE = _env_bool("CELERY_TASK_ACKS_LATE", True)
CELERY_TASK_REJECT_ON_WORKER_LOST = _env_bool("CELERY_TASK_REJECT_ON_WORKER_LOST", True)
CELERY_WORKER_PREFETCH_MULTIPLIER = _env_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1)
CELERY_WORKER_MAX_TASKS_PER_CHILD = _env_int("CELERY_MAX_TASKS_PER_CHILD", _env_int("CELERY_WORKER_MAX_TASKS_PER_CHILD", 500))
CELERY_WORKER_MAX_MEMORY_PER_CHILD = _env_int("CELERY_WORKER_MAX_MEMORY_PER_CHILD", 0)
CELERY_WORKER_CONCURRENCY = _env_int("CELERY_WORKER_CONCURRENCY", 0)
CELERY_HIJACK_ROOT_LOGGER = _env_bool("CELERY_HIJACK_ROOT_LOGGER", False)

CELERY_TASK_TIME_LIMIT_SEC = _env_int("CELERY_TASK_TIME_LIMIT_SEC", 0)
CELERY_TASK_SOFT_TIME_LIMIT_SEC = _env_int("CELERY_TASK_SOFT_TIME_LIMIT_SEC", 0)

CELERY_RESULT_EXPIRES_SEC = _env_int("CELERY_RESULT_EXPIRES_SEC", 86400)

CELERY_BROKER_HEARTBEAT = _env_int("CELERY_BROKER_HEARTBEAT", 0)
CELERY_BROKER_POOL_LIMIT = _env_int("CELERY_BROKER_POOL_LIMIT", 0)

BROKER_TRANSPORT_OPTIONS = _safe_json_loads(os.getenv("CELERY_BROKER_TRANSPORT_OPTIONS"))
BACKEND_TRANSPORT_OPTIONS = _safe_json_loads(os.getenv("CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS"))

CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = _env_bool("CELERY_TASK_EAGER_PROPAGATES", True)

CELERY_DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE", "celery")
CELERY_TASK_DEFAULT_QUEUE = CELERY_DEFAULT_QUEUE
CELERY_TASK_DEFAULT_EXCHANGE = os.getenv("CELERY_DEFAULT_EXCHANGE", "default")
CELERY_TASK_DEFAULT_ROUTING_KEY = os.getenv("CELERY_DEFAULT_ROUTING_KEY", "default")

CELERY_WORKER_SEND_TASK_EVENTS = _env_bool("CELERY_WORKER_SEND_TASK_EVENTS", True)
CELERY_TASK_SEND_SENT_EVENT = _env_bool("CELERY_TASK_SEND_SENT_EVENT", True)

ENABLE_BEAT = _env_bool("ENABLE_BEAT", True)
ENABLE_BEAT_HEARTBEAT = _env_bool("ENABLE_BEAT_HEARTBEAT", False)

# ---------------------------------------------------------------------
# Create Celery app
# ---------------------------------------------------------------------

app = Celery("foxproflow", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

# IMPORTANT: make this app current/default so shared_task binds correctly in this process.
try:
    app.set_current()
    app.set_default()
except Exception:
    pass

_conf: Dict[str, Any] = dict(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    accept_content=CELERY_ACCEPT_CONTENT,
    task_serializer=CELERY_TASK_SERIALIZER,
    result_serializer=CELERY_RESULT_SERIALIZER,
    timezone=CELERY_TIMEZONE,
    enable_utc=CELERY_ENABLE_UTC,
    task_acks_late=CELERY_TASK_ACKS_LATE,
    task_reject_on_worker_lost=CELERY_TASK_REJECT_ON_WORKER_LOST,
    worker_prefetch_multiplier=CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
    result_expires=CELERY_RESULT_EXPIRES_SEC,
    task_default_queue=CELERY_TASK_DEFAULT_QUEUE,
    task_default_exchange=CELERY_TASK_DEFAULT_EXCHANGE,
    task_default_routing_key=CELERY_TASK_DEFAULT_ROUTING_KEY,
    worker_send_task_events=CELERY_WORKER_SEND_TASK_EVENTS,
    task_send_sent_event=CELERY_TASK_SEND_SENT_EVENT,
    worker_hijack_root_logger=CELERY_HIJACK_ROOT_LOGGER,
    task_always_eager=CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=CELERY_TASK_EAGER_PROPAGATES,
    broker_connection_retry_on_startup=True,
    task_create_missing_queues=True,
)

if CELERY_TASK_TIME_LIMIT_SEC and CELERY_TASK_TIME_LIMIT_SEC > 0:
    _conf["task_time_limit"] = int(CELERY_TASK_TIME_LIMIT_SEC)
if CELERY_TASK_SOFT_TIME_LIMIT_SEC and CELERY_TASK_SOFT_TIME_LIMIT_SEC > 0:
    _conf["task_soft_time_limit"] = int(CELERY_TASK_SOFT_TIME_LIMIT_SEC)

if CELERY_WORKER_MAX_MEMORY_PER_CHILD and CELERY_WORKER_MAX_MEMORY_PER_CHILD > 0:
    _conf["worker_max_memory_per_child"] = int(CELERY_WORKER_MAX_MEMORY_PER_CHILD)

if CELERY_WORKER_CONCURRENCY and CELERY_WORKER_CONCURRENCY > 0:
    _conf["worker_concurrency"] = int(CELERY_WORKER_CONCURRENCY)

if CELERY_BROKER_HEARTBEAT and CELERY_BROKER_HEARTBEAT > 0:
    _conf["broker_heartbeat"] = int(CELERY_BROKER_HEARTBEAT)

if CELERY_BROKER_POOL_LIMIT and CELERY_BROKER_POOL_LIMIT > 0:
    _conf["broker_pool_limit"] = int(CELERY_BROKER_POOL_LIMIT)

if isinstance(BROKER_TRANSPORT_OPTIONS, dict):
    _conf["broker_transport_options"] = BROKER_TRANSPORT_OPTIONS

if isinstance(BACKEND_TRANSPORT_OPTIONS, dict):
    _conf["result_backend_transport_options"] = BACKEND_TRANSPORT_OPTIONS

app.conf.update(**_conf)

# ---------------------------------------------------------------------
# Module lists for deterministic imports
# ---------------------------------------------------------------------


def _split_modules(s: str) -> list[str]:
    out: list[str] = []
    for part in (s or "").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


CRITICAL_TASK_MODULES = [
    "src.worker.tasks_planner_kpi",          # planner.kpi.snapshot / planner.kpi.daily_refresh
    "src.worker.tasks_devfactory_analytics", # analytics.devfactory.daily
]

CRITICAL_TASK_NAMES = [
    "planner.kpi.snapshot",
    "planner.kpi.daily_refresh",
    "analytics.devfactory.daily",
    "devfactory.commercial.run_order",
]

BASE_MODULES = [
    "src.worker.register_tasks",
    "src.worker.tasks_ops",
    "src.worker.tasks.devfactory_commercial",
    *CRITICAL_TASK_MODULES,
]

ENV_IMPORTS = _split_modules(os.getenv("CELERY_IMPORTS", ""))
ENV_INCLUDE = _split_modules(os.getenv("CELERY_INCLUDE", ""))

MODULES = _dedupe(BASE_MODULES + ENV_IMPORTS + ENV_INCLUDE)

# publish for Celery loader
try:
    app.conf.imports = MODULES
    app.conf.include = MODULES
except Exception:
    try:
        log.exception("celery: failed to apply app.conf.imports/include")
    except Exception:
        pass

# Force-import configured modules in worker/beat runtime (this is the core Gate fix).
# Relying on Celery internals is sometimes not enough in this project due to layered bootstraps.
FF_CELERY_FORCE_IMPORT_DEFAULTS = _env_bool("FF_CELERY_FORCE_IMPORT_DEFAULTS", _is_celery_worker_or_beat())
if FF_CELERY_FORCE_IMPORT_DEFAULTS:
    try:
        app.loader.import_default_modules()
    except Exception:
        try:
            log.exception("celery: import_default_modules failed")
        except Exception:
            pass

# ---------------------------------------------------------------------
# Optional autodiscover (off by default; keep as knob)
# ---------------------------------------------------------------------

FF_CELERY_AUTODISCOVER = _env_bool("FF_CELERY_AUTODISCOVER", False)
if FF_CELERY_AUTODISCOVER:
    try:
        app.autodiscover_tasks(["src.worker"], force=True)
    except Exception:
        try:
            log.exception("celery: autodiscover failed")
        except Exception:
            pass

# ---------------------------------------------------------------------
# Beat schedule (minimal bootstrap schedules)
# ---------------------------------------------------------------------


def _schedule_enabled(name: str, default: bool = True) -> bool:
    return _env_bool(f"SCHEDULE_{name.upper()}_ENABLED", default)


def _schedule_crontab(spec: str) -> crontab:
    parts = (spec or "").strip().split()
    if len(parts) != 5:
        return crontab()
    minute, hour, dom, month, dow = parts
    return crontab(minute=minute, hour=hour, day_of_month=dom, month_of_year=month, day_of_week=dow)


def _add_schedule(task_name: str, schedule_obj: Any, args: Optional[tuple] = None, kwargs: Optional[Dict[str, Any]] = None) -> None:
    if not ENABLE_BEAT:
        return
    if not getattr(app.conf, "beat_schedule", None):
        app.conf.beat_schedule = {}
    app.conf.beat_schedule[task_name] = {
        "task": task_name,
        "schedule": schedule_obj,
        "args": args or (),
        "kwargs": kwargs or {},
        "options": {"queue": CELERY_DEFAULT_QUEUE},
    }


SCHEDULE_KEY_QUEUE_WATCHDOG = os.getenv("SCHEDULE_QUEUE_WATCHDOG", "*/5 * * * *")
SCHEDULE_KEY_OPS_ALERTS = os.getenv("SCHEDULE_OPS_ALERTS", "*/5 * * * *")
SCHEDULE_KEY_BEAT_HEARTBEAT = os.getenv("SCHEDULE_BEAT_HEARTBEAT", "*/1 * * * *")

SCHEDULE_KEY_KPI_SNAPSHOT = os.getenv("SCHEDULE_KPI_SNAPSHOT", "0 * * * *")
SCHEDULE_KEY_KPI_DAILY = os.getenv("SCHEDULE_KPI_DAILY", "5 0 * * *")


def _register_default_schedules() -> None:
    if _schedule_enabled("queue_watchdog", True):
        _add_schedule("ops.queue.watchdog", _schedule_crontab(SCHEDULE_KEY_QUEUE_WATCHDOG))
    if _schedule_enabled("ops_alerts", True):
        _add_schedule("ops.alerts.sla", _schedule_crontab(SCHEDULE_KEY_OPS_ALERTS))
    if ENABLE_BEAT_HEARTBEAT and _schedule_enabled("beat_heartbeat", True):
        _add_schedule("ops.beat.heartbeat", _schedule_crontab(SCHEDULE_KEY_BEAT_HEARTBEAT))
    if _schedule_enabled("kpi_snapshot", True):
        _add_schedule("planner.kpi.snapshot", _schedule_crontab(SCHEDULE_KEY_KPI_SNAPSHOT))
    if _schedule_enabled("kpi_daily", True):
        _add_schedule("planner.kpi.daily_refresh", _schedule_crontab(SCHEDULE_KEY_KPI_DAILY))


try:
    _register_default_schedules()
except Exception:
    pass

# ---------------------------------------------------------------------
# Diagnostics helpers
# ---------------------------------------------------------------------


def _mask_url(url: str) -> str:
    if not url:
        return url
    try:
        if url.startswith("redis://") and "@" in url:
            _pre, rest = url.split("redis://", 1)
            if "@" in rest and ":" in rest.split("@", 1)[0]:
                creds, host = rest.split("@", 1)
                user = creds.split(":", 1)[0]
                return f"redis://{user}:{'***'}@{host}"
    except Exception:
        pass
    return url


def _has_task(name: str) -> bool:
    try:
        return str(name) in getattr(app, "tasks", {})
    except Exception:
        return False


def celery_env_summary() -> Dict[str, Any]:
    return {
        "in_docker": _in_docker(),
        "broker": _mask_url(CELERY_BROKER_URL),
        "backend": _mask_url(CELERY_RESULT_BACKEND),
        "timezone": CELERY_TIMEZONE,
        "enable_utc": CELERY_ENABLE_UTC,
        "default_queue": CELERY_DEFAULT_QUEUE,
        "imports_count": len(MODULES),
        "force_import_defaults": FF_CELERY_FORCE_IMPORT_DEFAULTS,
        "tasks_registered": {k: _has_task(k) for k in CRITICAL_TASK_NAMES},
    }


def print_celery_env_summary() -> None:
    try:
        print(json.dumps(celery_env_summary(), ensure_ascii=False, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------
# Critical import anchors + registry check (log-only, must not crash)
# ---------------------------------------------------------------------


def _safe_import(mod: str) -> None:
    try:
        importlib.import_module(mod)
    except Exception:
        try:
            log.exception("celery: failed to import module: %s", mod)
        except Exception:
            pass


def _ensure_critical_tasks_registered() -> None:
    # deterministic imports (do NOT rely only on loader)
    for m in [
        "src.worker.register_tasks",
        "src.worker.tasks_ops",
        "src.worker.tasks.devfactory_commercial",
        *CRITICAL_TASK_MODULES,
    ]:
        _safe_import(m)

    # second chance: loader import (worker/beat)
    if FF_CELERY_FORCE_IMPORT_DEFAULTS:
        try:
            app.loader.import_default_modules()
        except Exception:
            try:
                log.exception("celery: import_default_modules failed (second-chance)")
            except Exception:
                pass

    missing = [t for t in CRITICAL_TASK_NAMES if not _has_task(t)]
    if missing:
        try:
            log.error("celery: live registry missing critical tasks: %s", ", ".join(missing))
        except Exception:
            pass


try:
    _ensure_critical_tasks_registered()
except Exception:
    pass

# Optional: force bind confirm (used by entrypoints / task name normalization)
try:
    from src.worker.ff_force_bind_confirm import *  # noqa: F401,F403
except Exception:
    pass

__all__ = ["app", "celery_env_summary", "print_celery_env_summary"]
