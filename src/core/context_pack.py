# -*- coding: utf-8 -*-
# file: src/core/context_pack.py
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


# -----------------------------
# Safe env snapshot (no secrets)
# -----------------------------

_SENSITIVE_SUBSTR = ("PASS", "PASSWORD", "SECRET", "TOKEN", "KEY", "PRIVATE", "DSN")

# Явно разрешённые "флаги" (без паролей).
_ENV_ALLOWLIST = (
    "APP_TITLE",
    "APP_VERSION",
    "FF_AUTODISCOVER_ROUTERS",
    "FF_ENABLE_DEBUG_ROUTER",
    "FF_ENABLE_AUTOPLAN_OPS",
    "FF_ENABLE_DF_GATEWAY_FALLBACK",
    "FF_ENABLE_DF_INTENT_FALLBACK",
    "FF_DIAG_FIXED_LENGTH",
    "FF_DIAG_DISABLE_GZIP",
    "AGENTS_ENABLE",
    "AGENTS_MODE",
    "ENABLE_BEAT_HEARTBEAT",
    "DEVFACTORY_DISPATCH_KWARG_GUARD_ENABLED",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "REDIS_HOST",
    "REDIS_PORT",
    "OSRM_HOST",
    "OSRM_PORT",
    "OSRM_BASE_URL",
    "COMPOSE_PROJECT_NAME",
    "FF_COMPOSE_SERVICES",
)

_GIT_SHA_ENV_CANDIDATES = ("FF_GIT_SHA", "GIT_SHA", "SOURCE_VERSION", "HEROKU_SLUG_COMMIT")


def _is_sensitive_key(k: str) -> bool:
    ku = (k or "").upper()
    return any(s in ku for s in _SENSITIVE_SUBSTR)


def _safe_env_flags() -> Dict[str, str]:
    flags: Dict[str, str] = {}

    # allowlist first
    for k in _ENV_ALLOWLIST:
        v = os.getenv(k)
        if v is None:
            continue
        if _is_sensitive_key(k):
            flags[k] = "<redacted>"
        else:
            flags[k] = str(v)

    # plus FF_*/AGENTS_*/DEVFACTORY_*/FLOWSEC_* (но без секретов)
    for k, v in os.environ.items():
        if not (k.startswith("FF_") or k.startswith("AGENTS_") or k.startswith("DEVFACTORY_") or k.startswith("FLOWSEC_")):
            continue
        if k in flags:
            continue
        if _is_sensitive_key(k):
            continue
        flags[k] = str(v)

    return flags


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


# -----------------------------
# Git SHA (facts, not guesses)
# -----------------------------

def _try_git_rev_parse_head() -> Optional[str]:
    # 1) env candidates
    for k in _GIT_SHA_ENV_CANDIDATES:
        v = (os.getenv(k) or "").strip()
        if v:
            return v

    # 2) git command (best-effort; container may not have git/.git)
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1.5,
            check=False,
            text=True,
        )
        out = (p.stdout or "").strip()
        if out:
            return out
    except Exception:
        return None

    return None


# -----------------------------
# Postgres connectivity (facts)
# -----------------------------

def _normalize_dsn(dsn: str) -> str:
    dsn = (dsn or "").strip()
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    return dsn


def _build_pg_dsn() -> str:
    dsn = _normalize_dsn(os.getenv("DATABASE_URL", ""))
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _connect_pg():
    dsn = _build_pg_dsn()
    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


def _to_regclass(conn, reg: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (reg,))
            row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _table_cols(conn, schema: str, table: str) -> List[str]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema, table),
            )
            return [str(r[0]) for r in (cur.fetchall() or [])]
    except Exception:
        return []


def try_insert_ops_agent_event(
    conn,
    *,
    agent: str,
    level: str,
    action: str,
    payload: Dict[str, Any],
    ok: bool,
    latency_ms: Optional[int] = None,
) -> bool:
    """
    Best-effort вставка в ops.agent_events (если таблица существует).
    Каноничная схема ожидается: (ts, agent, level, action, payload jsonb, ok, latency_ms)
    но допускаем дрейф — вставляем только существующие колонки.
    """
    if not _to_regclass(conn, "ops.agent_events"):
        return False

    cols = set(_table_cols(conn, "ops", "agent_events"))
    if not cols:
        return False

    fields: List[str] = []
    placeholders: List[str] = []
    params: List[Any] = []

    def add(col: str, placeholder: str, val: Any) -> None:
        if col in cols:
            fields.append(col)
            placeholders.append(placeholder)
            params.append(val)

    # ts: если есть — ставим now()
    if "ts" in cols:
        fields.append("ts")
        placeholders.append("now()")

    add("agent", "%s", str(agent))
    add("level", "%s", str(level))
    add("action", "%s", str(action))
    if "payload" in cols:
        fields.append("payload")
        placeholders.append("%s::jsonb")
        params.append(_json_dumps(payload))
    add("ok", "%s", bool(ok))
    if latency_ms is not None:
        add("latency_ms", "%s", int(latency_ms))

    if not fields:
        return False

    sql = f"INSERT INTO ops.agent_events ({', '.join(fields)}) VALUES ({', '.join(placeholders)});"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def attach_context_pack_to_dev_task(conn, *, dev_task_id: int, context_pack: Dict[str, Any]) -> bool:
    """
    Пишем context_pack в dev.dev_task.input_spec->context_pack (если возможно).
    """
    if not _to_regclass(conn, "dev.dev_task"):
        return False

    cols = set(_table_cols(conn, "dev", "dev_task"))
    if "input_spec" not in cols:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dev.dev_task
                   SET input_spec = COALESCE(input_spec, '{}'::jsonb)
                                  || jsonb_build_object('context_pack', %s::jsonb),
                       updated_at = CASE WHEN 'updated_at' = ANY(%s) THEN now() ELSE updated_at END
                 WHERE id = %s
                """,
                (_json_dumps(context_pack), list(cols), int(dev_task_id)),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def collect_context_pack(*, conn=None) -> Dict[str, Any]:
    """
    Собирает минимальный Context Pack.
    Если conn (psycopg/psycopg2) передан — использует его для DB фактов и логов.
    """
    missing: List[str] = []

    started = time.monotonic()
    ts = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()

    pack: Dict[str, Any] = {
        "ts": ts,
        "runtime": {
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "in_container": bool(os.getenv("KUBERNETES_SERVICE_HOST") or os.path.exists("/.dockerenv")),
        },
        "git": {},
        "services": {},
        "db": {},
        "env": {"flags": _safe_env_flags()},
        "missing": missing,
    }

    sha = _try_git_rev_parse_head()
    if sha:
        pack["git"] = {"sha": sha}
    else:
        missing.append("git_sha")
        pack["git"] = {"sha": None}

    # services: фактом считаем только то, что явно передали/сконфигурили
    services_env = (os.getenv("FF_COMPOSE_SERVICES") or "").strip()
    if services_env:
        services = [s.strip() for s in services_env.split(",") if s.strip()]
        pack["services"] = {"compose_services": services}
    else:
        missing.append("compose_services")
        pack["services"] = {
            "compose_services": None,
            "configured_endpoints": {
                "postgres_host": os.getenv("POSTGRES_HOST", "postgres"),
                "postgres_db": os.getenv("POSTGRES_DB", "foxproflow"),
                "redis_host": os.getenv("REDIS_HOST", os.getenv("REDIS_URL", "")) or None,
                "osrm_base_url": os.getenv("OSRM_BASE_URL", "") or None,
            },
        }

    # DB connectivity facts
    owns_conn = False
    if conn is None:
        try:
            conn = _connect_pg()
            owns_conn = True
        except Exception as e:
            missing.append("db_connectivity")
            pack["db"] = {"ok": False, "error": str(e)}
            conn = None

    if conn is not None:
        t0 = time.monotonic()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
                cur.execute("SELECT current_database(), current_user;")
                row = cur.fetchone() or (None, None)
                cur.execute("SHOW server_version;")
                ver = cur.fetchone()
            latency_ms = int((time.monotonic() - t0) * 1000.0)
            pack["db"] = {
                "ok": True,
                "latency_ms": latency_ms,
                "current_database": row[0],
                "current_user": row[1],
                "server_version": (ver[0] if ver else None),
            }
        except Exception as e:
            missing.append("db_connectivity")
            pack["db"] = {"ok": False, "error": str(e)}
            try:
                conn.rollback()
            except Exception:
                pass

    pack["latency_ms"] = int((time.monotonic() - started) * 1000.0)

    if owns_conn and conn is not None:
        try:
            conn.close()
        except Exception:
            pass

    return pack
