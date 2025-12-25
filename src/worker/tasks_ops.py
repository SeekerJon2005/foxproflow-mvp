# -*- coding: utf-8 -*-
"""
Технические / ops-задачи: heartbeat, watchdog очередей, SLA-алёрты.

Цели:
- ops.beat.heartbeat:
    * фиксировать «пульс» Beat в Redis по ключу ops:beat:heartbeat
    * TTL берём из ALERT_BEAT_STALE_SEC или из аргумента ttl_sec
- ops.queue.watchdog:
    * измерять длину очередей Celery по данным Redis
    * писать агрегированную статистику в результат задачи и логи
- ops.alerts.sla:
    * на основе heartbeat + длины очередей давать простую оценку состояния
    * пока только логирование и структурированный JSON, без внешних интеграций

Важно:
- Никаких миграций по БД: всё хранится в Redis в тех же инстансах,
  которые уже используются брокером/бекендом Celery.
- Имена задач Celery остаются прежними:
    ops.beat.heartbeat
    ops.queue.watchdog
    ops.alerts.sla

Compat (чтобы не было "Received unregistered task"):
- routing.osrm.warmup
- autoplan.refresh

CRM smoke (CP1):
- crm.smoke.ping:
    * ультра-лёгкий smoke без БД
- crm.smoke.db_contract:
    * проверка DB-контракта для CP1 (по REQUEST от C-sql):
      sec.*, dev.dev_task, ops.event_log(correlation_id), planner.kpi_*,
      public.trips/trip_segments(compat), public.trucks, crm.leads_trial_candidates_v

Ключевое усиление против "unregistered task":
- Декоратор @_task(...) пытается регистрировать задачи напрямую в src.worker.celery_app.app,
  а если app недоступен (порядок импортов/циклы) — fallback на celery.shared_task.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from celery import shared_task

log = logging.getLogger(__name__)

try:  # pragma: no cover
    import redis  # type: ignore[import]
except Exception:  # pragma: no cover
    redis = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Celery task registration helper (reduce "unregistered task" risk)
# --------------------------------------------------------------------------- #

def _resolve_celery_app() -> Any:
    """
    Пытаемся получить именно тот Celery app, который использует worker.

    Аккуратно:
    - сначала sys.modules (чтобы не провоцировать циклы)
    - потом пробуем импорт src.worker.celery_app (если можно)
    """
    mod = sys.modules.get("src.worker.celery_app")
    if mod is not None:
        app = getattr(mod, "app", None) or getattr(mod, "celery_app", None)
        if app is not None:
            return app

    try:
        from src.worker.celery_app import app as worker_app  # type: ignore
        return worker_app
    except Exception:
        try:
            from src.worker.celery_app import celery_app as worker_app  # type: ignore
            return worker_app
        except Exception:
            return None


def _task(name: str, **opts: Any):
    """
    Декоратор задач:
    - если доступен src.worker.celery_app.app -> app.task(name=..., **opts)
    - иначе -> shared_task(name=..., **opts)
    """
    app = _resolve_celery_app()
    if app is not None:
        return app.task(name=name, **opts)
    return shared_task(name=name, **opts)


# --------------------------------------------------------------------------- #
# Общие helpers
# --------------------------------------------------------------------------- #

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _as_aware_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Redis helpers
# --------------------------------------------------------------------------- #

def _get_redis(db: int = 0):
    """
    Подключение к Redis.

    Приоритет:
      1) REDIS_URL (если задан)
      2) CELERY_BROKER_URL (если redis://...)
      3) REDIS_HOST / REDIS_PORT / REDIS_PASSWORD
    """
    if redis is None:  # type: ignore[truthy-function]
        log.warning("tasks_ops: redis client is not available (no 'redis' package?)")
        return None

    sock_connect_to = _env_float("OPS_REDIS_CONNECT_TIMEOUT_SEC", 2.0)
    sock_to = _env_float("OPS_REDIS_SOCKET_TIMEOUT_SEC", 2.0)

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        broker = (os.getenv("CELERY_BROKER_URL") or "").strip()
        if broker.startswith("redis://") or broker.startswith("rediss://"):
            url = broker

    if url:
        try:
            client = redis.Redis.from_url(  # type: ignore[attr-defined]
                url,
                db=db,
                decode_responses=True,
                socket_connect_timeout=sock_connect_to,
                socket_timeout=sock_to,
            )
            client.ping()
            return client
        except Exception as e:  # pragma: no cover
            log.warning("tasks_ops: failed to connect Redis via url=%s: %r", url, e)

    host = os.getenv("REDIS_HOST", "redis")
    port = _env_int("REDIS_PORT", 6379)
    password = os.getenv("REDIS_PASSWORD") or None

    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            decode_responses=True,
            socket_connect_timeout=sock_connect_to,
            socket_timeout=sock_to,
        )
        client.ping()
        return client
    except Exception as e:  # pragma: no cover
        log.warning("tasks_ops: failed to connect Redis: %r", e)
        return None


def _queue_names_from_env() -> List[str]:
    explicit = (os.getenv("OPS_QUEUE_NAMES") or "").strip()
    if explicit:
        parts = [q.strip() for q in explicit.split(",") if q.strip()]
        uniq = sorted({q for q in parts if q})
        return uniq or ["celery"]

    raw_parts: List[str] = []
    for env_name in (
        "CELERY_QUEUES",
        "CELERY_QUEUE_DEFAULT",
        "CELERY_DEFAULT_QUEUE",
        "AUTOPLAN_QUEUE",
        "ROUTING_QUEUE",
        "AGENTS_QUEUE",
        "DEVFACTORY_DISPATCH_QUEUE",
        "ATI_REFRESH_QUEUE",
        "MARKET_REFRESH_QUEUE",
    ):
        v = (os.getenv(env_name) or "").strip()
        if v:
            raw_parts.append(v)

    raw = ",".join(raw_parts).strip() or "celery"
    parts = [q.strip() for q in raw.split(",") if q.strip()]
    uniq = sorted({q for q in parts if q})
    if "celery" not in uniq:
        uniq.append("celery")
    return uniq or ["celery"]


def _collect_queue_stats(r) -> Dict[str, Any]:
    queues = _queue_names_from_env()
    stats: List[Dict[str, Any]] = []
    max_len = 0

    for q in queues:
        try:
            ln = int(r.llen(q))
        except Exception as e:  # pragma: no cover
            log.warning("ops.queue.watchdog: failed to read length for queue %s: %r", q, e)
            stats.append({"name": q, "len": None, "error": repr(e)})
            continue

        stats.append({"name": q, "len": ln})
        if ln > max_len:
            max_len = ln

    return {"queues": stats, "max_len": max_len}


# --------------------------------------------------------------------------- #
# Postgres helpers (для crm.smoke.db_contract)
# --------------------------------------------------------------------------- #

def _build_pg_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn and str(dsn).strip():
        return str(dsn).strip()

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")
    auth = f"{user}:{pwd}" if pwd else user
    return f"postgresql://{auth}@{host}:{port}/{db}"


def _connect_pg():
    dsn = _build_pg_dsn()
    connect_to = _env_int("CRM_PG_CONNECT_TIMEOUT_SEC", 3)

    first_exc: Optional[Exception] = None
    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn, connect_timeout=connect_to)
    except Exception as e1:  # noqa: BLE001
        first_exc = e1

    try:
        import psycopg2  # type: ignore
        return psycopg2.connect(dsn, connect_timeout=connect_to)
    except Exception as e2:  # noqa: BLE001
        msg = "crm.smoke.db_contract: cannot connect to Postgres via psycopg/psycopg2"
        if first_exc:
            msg += f" (psycopg error: {first_exc!r})"
        raise RuntimeError(msg) from e2


def _set_local_statement_timeout(cur) -> None:
    st_ms = _env_int("CRM_PG_STATEMENT_TIMEOUT_MS", 2500)
    try:
        cur.execute(f"SET LOCAL statement_timeout = '{int(st_ms)}ms'")
    except Exception:
        pass


def _db_contract_checks(cur) -> Dict[str, Any]:
    _set_local_statement_timeout(cur)
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
    try:
        checks["planner_kpi_like_cnt"] = int(checks.get("planner_kpi_like_cnt") or 0)
    except Exception:
        pass
    return checks


def _db_contract_ok(checks: Dict[str, Any]) -> bool:
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
        and checks.get("crm.leads_trial_candidates_v")
    )


# --------------------------------------------------------------------------- #
# ops.beat.heartbeat
# --------------------------------------------------------------------------- #

@_task("ops.beat.heartbeat")
def task_ops_beat_heartbeat(ttl_sec: Optional[int] = None) -> Dict[str, Any]:
    now_iso = _utcnow_iso()

    if ttl_sec is None:
        ttl_sec = _env_int("ALERT_BEAT_STALE_SEC", 180)
    ttl_sec = max(10, int(ttl_sec or 180))

    payload: Dict[str, Any] = {
        "ok": True,
        "ts": now_iso,
        "ttl_sec": ttl_sec,
        "redis": False,
        "key": "ops:beat:heartbeat",
    }

    r = _get_redis(db=0)
    if not r:
        log.warning("ops.beat.heartbeat: Redis unavailable, heartbeat only in logs")
        payload["ok"] = False
        payload["error"] = "redis_unavailable"
        return payload

    try:
        r.set(payload["key"], json.dumps({"ts": now_iso}), ex=ttl_sec)
        payload["redis"] = True
    except Exception as e:  # pragma: no cover
        payload["ok"] = False
        payload["error"] = repr(e)
        log.warning("ops.beat.heartbeat: failed to store heartbeat: %r", e)

    return payload


# --------------------------------------------------------------------------- #
# ops.queue.watchdog
# --------------------------------------------------------------------------- #

@_task("ops.queue.watchdog")
def task_ops_queue_watchdog() -> Dict[str, Any]:
    now_iso = _utcnow_iso()

    payload: Dict[str, Any] = {
        "ok": True,
        "ts": now_iso,
        "queues": [],
        "max_len": 0,
        "level": "unknown",
    }

    r = _get_redis(db=0)
    if not r:
        payload["ok"] = False
        payload["error"] = "redis_unavailable"
        log.warning("ops.queue.watchdog: Redis unavailable, cannot inspect queues")
        return payload

    stats = _collect_queue_stats(r)
    payload["queues"] = stats["queues"]
    payload["max_len"] = stats["max_len"]

    busy_threshold = _env_int("ALERT_QUEUE_BUSY_MIN", 50)
    if busy_threshold > 0 and payload["max_len"] >= busy_threshold:
        payload["ok"] = False
        payload["level"] = "busy"
        log.warning(
            "ops.queue.watchdog: busy queues detected (max_len=%s >= %s)",
            payload["max_len"],
            busy_threshold,
        )
    else:
        payload["level"] = "ok"
        log.info(
            "ops.queue.watchdog: queues ok (max_len=%s, threshold=%s)",
            payload["max_len"],
            busy_threshold,
        )

    return payload


# --------------------------------------------------------------------------- #
# ops.alerts.sla
# --------------------------------------------------------------------------- #

@_task("ops.alerts.sla")
def task_ops_alerts_sla() -> Dict[str, Any]:
    now_iso = _utcnow_iso()

    r = _get_redis(db=0)
    if not r:
        log.warning("ops.alerts.sla: Redis unavailable, cannot evaluate SLA")
        return {
            "ok": False,
            "level": "crit",
            "alerts": ["redis_unavailable"],
            "beat": None,
            "queues": None,
            "ts": now_iso,
        }

    beat_key = "ops:beat:heartbeat"
    beat_state: Dict[str, Any] = {"status": "unknown", "age_sec": None, "present": False}

    raw = r.get(beat_key)
    if not raw:
        beat_state.update({"status": "missing", "present": False})
    else:
        beat_state["present"] = True
        try:
            data = json.loads(raw)
            ts_str = data.get("ts")
            if ts_str:
                ts = _as_aware_utc(datetime.fromisoformat(ts_str))
                age_sec = max(0, int((_utcnow() - ts).total_seconds()))
                beat_state["age_sec"] = age_sec

                stale_sec = _env_int("ALERT_BEAT_STALE_SEC", 180)
                beat_state["stale_threshold_sec"] = stale_sec
                beat_state["status"] = "ok" if age_sec <= stale_sec else "stale"
            else:
                beat_state["status"] = "invalid"
        except Exception as e:  # pragma: no cover
            beat_state["status"] = "invalid"
            beat_state["error"] = repr(e)

    queue_stats = _collect_queue_stats(r)
    busy_threshold = _env_int("ALERT_QUEUE_BUSY_MIN", 50)
    max_len = int(queue_stats.get("max_len") or 0)

    level = "ok"
    alerts: List[str] = []

    if beat_state["status"] == "missing":
        level = "crit"
        alerts.append("beat_missing")
    elif beat_state["status"] == "invalid":
        level = "crit"
        alerts.append("beat_invalid")
    elif beat_state["status"] == "stale":
        level = "warn"
        alerts.append("beat_stale")

    if busy_threshold > 0 and max_len >= busy_threshold:
        if level == "ok":
            level = "warn"
        alerts.append("queues_busy")

    ok = level == "ok"
    if ok:
        log.info(
            "ops.alerts.sla: ok (beat=%s, max_queue_len=%s, thr=%s)",
            beat_state.get("status"),
            max_len,
            busy_threshold,
        )
    else:
        log.warning(
            "ops.alerts.sla: level=%s alerts=%s beat=%s max_queue_len=%s thr=%s",
            level,
            alerts,
            beat_state.get("status"),
            max_len,
            busy_threshold,
        )

    return {
        "ok": ok,
        "level": level,
        "alerts": alerts,
        "beat": beat_state,
        "queues": queue_stats,
        "ts": now_iso,
    }


# --------------------------------------------------------------------------- #
# CRM smoke (CP1)
# --------------------------------------------------------------------------- #

@_task("crm.smoke.ping")
def task_crm_smoke_ping() -> Dict[str, Any]:
    return {"ok": True, "ts": _utcnow_iso(), "service": "crm", "smoke": True}


@_task("crm.smoke.db_contract")
def task_crm_smoke_db_contract() -> Dict[str, Any]:
    conn = None
    try:
        conn = _connect_pg()
        with conn.cursor() as cur:
            checks = _db_contract_checks(cur)
        ok = _db_contract_ok(checks) if "error" not in checks else False
        return {"ok": ok, "ts": _utcnow_iso(), "service": "crm", "db_contract": ok, "checks": checks}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "ts": _utcnow_iso(), "service": "crm", "db_contract": False, "error": repr(ex)}
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Compat tasks (чтобы не ловить "unregistered task")
# --------------------------------------------------------------------------- #

@_task("routing.osrm.warmup")
def task_routing_osrm_warmup() -> Dict[str, Any]:
    base = (os.getenv("OSRM_URL") or os.getenv("ROUTING_BASE_URL") or "http://osrm:5000").rstrip("/")
    profile = (os.getenv("OSRM_PROFILE") or os.getenv("ROUTING_OSRM_PROFILE") or "driving").strip() or "driving"
    timeout_sec = _env_float("OSRM_WARMUP_TIMEOUT_SEC", 2.0)

    lon1 = float(os.getenv("OSRM_WARMUP_LON1", "37.6173") or "37.6173")
    lat1 = float(os.getenv("OSRM_WARMUP_LAT1", "55.7558") or "55.7558")
    lon2 = float(os.getenv("OSRM_WARMUP_LON2", "37.6273") or "37.6273")
    lat2 = float(os.getenv("OSRM_WARMUP_LAT2", "55.7658") or "55.7658")

    url = f"{base}/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}?overview=false"
    out: Dict[str, Any] = {"ok": True, "ts": _utcnow_iso(), "url": url}

    try:
        with urlopen(url, timeout=timeout_sec) as resp:
            out["http_status"] = int(getattr(resp, "status", 200) or 200)
            _ = resp.read(256)
    except HTTPError as e:  # pragma: no cover
        out["ok"] = False
        out["http_status"] = int(getattr(e, "code", 0) or 0)
        out["error"] = f"HTTPError: {e!r}"
    except URLError as e:  # pragma: no cover
        out["ok"] = False
        out["error"] = f"URLError: {e!r}"
    except Exception as e:  # pragma: no cover
        out["ok"] = False
        out["error"] = repr(e)

    return out


@_task("autoplan.refresh")
def task_autoplan_refresh() -> Dict[str, Any]:
    return {"ok": True, "ts": _utcnow_iso(), "note": "compat no-op (autoplan.refresh)"}


__all__ = [
    "task_ops_beat_heartbeat",
    "task_ops_queue_watchdog",
    "task_ops_alerts_sla",
    "task_crm_smoke_ping",
    "task_crm_smoke_db_contract",
    "task_routing_osrm_warmup",
    "task_autoplan_refresh",
]
