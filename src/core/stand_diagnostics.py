# -*- coding: utf-8 -*-
# file: src/core/stand_diagnostics.py
from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from src.core.build_info import get_build_info
from src.core.compose_inspect import discover_compose_services


DEFAULT_FALLBACK_SERVICES = ["api", "worker", "beat", "postgres", "redis", "osrm"]


def _db_dsn() -> str:
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")

    auth = f"{user}:{pwd}" if pwd else user
    return f"postgresql://{auth}@{host}:{port}/{db}"


def _pg_connect(connect_timeout_sec: int = 2):
    dsn = _db_dsn()
    try:
        import psycopg  # type: ignore
        try:
            return psycopg.connect(dsn, connect_timeout=connect_timeout_sec)
        except TypeError:
            return psycopg.connect(dsn)
    except Exception:
        import psycopg2  # type: ignore
        try:
            return psycopg2.connect(dsn, connect_timeout=connect_timeout_sec)
        except TypeError:
            return psycopg2.connect(dsn)


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _to_regclass(cur, reg: str) -> bool:
    try:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL;", (reg,))
        r = cur.fetchone()
        return bool(r and r[0])
    except Exception:
        return False


def _pkg_ver(modname: str) -> Optional[str]:
    try:
        import importlib.metadata as md
        return md.version(modname)
    except Exception:
        try:
            m = importlib.import_module(modname)
            v = getattr(m, "__version__", None)
            return str(v) if v else None
        except Exception:
            return None


@dataclass
class StandDiagnostics:
    ok: bool
    order_type: str
    report_head: str
    ts_utc: str
    latency_ms: int
    missing: List[str]  # top-level contract missing (M0: should be empty)

    git_sha: str
    git_sha_source: str
    compose_services: List[str]
    compose_files_used: List[str]
    compose_errors: List[str]

    versions: Dict[str, Any]
    db: Dict[str, Any]
    host: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def collect_stand_diagnostics(
    *,
    order_type: str = "stand_diagnostics_v1",
    correlation_id: Optional[str] = None,
    repo_root: str = "/app",
) -> Dict[str, Any]:
    t0 = time.monotonic()

    # Build info (git sha never empty: fallback "unknown")
    bi = get_build_info(repo_root=repo_root)

    # Compose services best-effort; if cannot discover, use fallback list
    ci = discover_compose_services(repo_root=repo_root)
    compose_services = ci.services if ci.services else list(DEFAULT_FALLBACK_SERVICES)
    compose_errors = list(ci.errors)
    if not ci.services:
        compose_errors.append("fallback: DEFAULT_FALLBACK_SERVICES used (compose services not discovered)")

    # Versions (safe)
    versions: Dict[str, Any] = {
        "app_version": bi.app_version,
        "python": bi.python_version,
        "fastapi": _pkg_ver("fastapi"),
        "pydantic": _pkg_ver("pydantic"),
        "celery": _pkg_ver("celery"),
        "psycopg": _pkg_ver("psycopg"),
        "psycopg2": _pkg_ver("psycopg2"),
        "sqlalchemy": _pkg_ver("sqlalchemy"),
    }

    # DB probe (best-effort, quick)
    db: Dict[str, Any] = {"ok": True, "missing": [], "checks": {}, "details": {}}
    try:
        conn = _pg_connect(connect_timeout_sec=2)
        try:
            conn.autocommit = False
        except Exception:
            pass

        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("SET LOCAL statement_timeout = '1500ms';")
                except Exception:
                    pass

                cur.execute("SELECT now(), current_database(), current_user, current_setting('server_version', true);")
                row = cur.fetchone() or (None, None, None, None)
                db["details"]["now"] = str(row[0]) if row[0] is not None else None
                db["details"]["db"] = str(row[1]) if row[1] is not None else None
                db["details"]["db_user"] = str(row[2]) if row[2] is not None else None
                db["details"]["server_version"] = str(row[3]) if row[3] is not None else None

                required = [
                    "dev.dev_order",
                    "dev.dev_task",
                    "dev.v_dev_order_commercial_ctx",
                    "ops.audit_events",
                ]
                for reg in required:
                    ok = _to_regclass(cur, reg)
                    db["checks"][reg] = bool(ok)
                    if not ok:
                        db["missing"].append(reg)

                try:
                    conn.rollback()
                except Exception:
                    pass

                # DB missing objects are reflected in db.ok, but do not break diagnostics envelope
                if db["missing"]:
                    db["ok"] = False
        finally:
            _safe_close(conn)
    except Exception as e:
        db["ok"] = False
        db["details"]["error"] = f"{type(e).__name__}: {e}"

    # Overall ok: false only if DB totally unreachable (hard dependency failure)
    ok = True
    if db.get("ok") is False and "error" in (db.get("details") or {}):
        ok = False

    latency_ms = int((time.monotonic() - t0) * 1000.0)
    head = "stand_diagnostics: ok" if ok else "stand_diagnostics: failed"

    host = {
        "service_role": bi.service_role,
        "hostname": bi.hostname,
        "correlation_id": correlation_id,
    }

    # Top-level missing is for contract keys; in M0 we keep it empty by construction.
    out = StandDiagnostics(
        ok=bool(ok),
        order_type=order_type,
        report_head=head,
        ts_utc=bi.ts_utc,
        latency_ms=latency_ms,
        missing=[],

        git_sha=bi.git_sha,
        git_sha_source=bi.git_sha_source,
        compose_services=compose_services,
        compose_files_used=ci.files_used,
        compose_errors=compose_errors,

        versions=versions,
        db=db,
        host=host,
    )

    return out.to_dict()
