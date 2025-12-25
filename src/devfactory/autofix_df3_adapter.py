# -*- coding: utf-8 -*-
# file: src/devfactory/autofix_df3_adapter.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import datetime as dt
import json
import logging
import os
from uuid import UUID

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
#  Minimal PG connect (lazy psycopg import) — must not fail on module import
# -----------------------------------------------------------------------------

def _normalize_dsn(dsn: str) -> str:
    if not dsn:
        return dsn
    dsn = dsn.strip()
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    return dsn


def _connect_pg():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        dsn = _normalize_dsn(database_url)
    else:
        user = os.getenv("POSTGRES_USER", "admin")
        pwd = os.getenv("POSTGRES_PASSWORD", "admin")
        host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"
        auth = f"{user}:{pwd}@" if pwd else f"{user}@"
        dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _uuid_or_none(v: Any) -> Optional[UUID]:
    if v is None:
        return None
    if isinstance(v, UUID):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return UUID(s)
    except Exception:
        return None


def _resolve_task_id(conn, task_ref: Any) -> Optional[int]:
    """
    Accepts:
      - int id
      - numeric string
      - public_id UUID string
    Returns: dev.dev_task.id (int) or None
    """
    if task_ref is None:
        return None

    if isinstance(task_ref, int):
        return task_ref

    s = str(task_ref).strip()
    if not s:
        return None

    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return None

    pu = _uuid_or_none(s)
    if pu is None:
        return None

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM dev.dev_task WHERE public_id = %s", (str(pu),))
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _fetch_df3_ids(conn, task_id: int) -> Tuple[Optional[UUID], Optional[UUID], Optional[UUID], Optional[str]]:
    """
    Returns:
      (public_id, flowmind_plan_id, dev_order_id, stack)
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              public_id,
              meta->>'flowmind_plan_id' AS flowmind_plan_id,
              meta->>'dev_order_id'     AS dev_order_id,
              stack
            FROM dev.dev_task
            WHERE id = %s
            """,
            (int(task_id),),
        )
        row = cur.fetchone()

    if not row:
        return None, None, None, None

    public_id_raw, plan_raw, order_raw, stack_raw = row
    return (
        _uuid_or_none(public_id_raw),
        _uuid_or_none(plan_raw),
        _uuid_or_none(order_raw),
        (str(stack_raw) if stack_raw is not None else None),
    )


def _pg_literal(value: Optional[str]) -> str:
    if value is None:
        return "null"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _build_df3_log_sql(
    *,
    dev_task_id: UUID,
    dev_order_id: Optional[UUID],
    flowmind_plan_id: Optional[UUID],
    resource_kind: str,
    action: str,
    status: str,
    duration_ms: Optional[int],
    engine: str,
    notes: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> str:
    payload_sql = "null"
    if payload is not None:
        payload_sql = _pg_literal(json.dumps(payload, ensure_ascii=False))

    dev_task_id_l = _pg_literal(str(dev_task_id))
    dev_order_id_l = _pg_literal(str(dev_order_id)) if dev_order_id else "null"
    flowmind_plan_id_l = _pg_literal(str(flowmind_plan_id)) if flowmind_plan_id else "null"
    resource_kind_l = _pg_literal(resource_kind or "unknown")
    action_l = _pg_literal(action)
    status_l = _pg_literal(status)
    duration_l = str(int(duration_ms)) if duration_ms is not None else "null"
    engine_l = _pg_literal(engine)
    notes_l = _pg_literal(notes) if notes else "null"

    return f"""
select analytics.log_devfactory_autofix_df3_event(
  {dev_task_id_l}::uuid,
  {dev_order_id_l}::uuid,
  {flowmind_plan_id_l}::uuid,
  {resource_kind_l}::text,
  null::text,
  {action_l}::text,
  {status_l}::text,
  {duration_l}::int,
  {engine_l}::text,
  {notes_l}::text,
  {payload_sql}::jsonb
);
""".strip()


def _df3_log_best_effort(
    conn,
    *,
    public_id: Optional[UUID],
    flowmind_plan_id: Optional[UUID],
    dev_order_id: Optional[UUID],
    stack: str,
    action: str,
    status: str,
    duration_ms: Optional[int],
    notes: str,
    payload: Dict[str, Any],
) -> None:
    if public_id is None:
        return
    try:
        sql = _build_df3_log_sql(
            dev_task_id=public_id,
            dev_order_id=dev_order_id,
            flowmind_plan_id=flowmind_plan_id,
            resource_kind=stack or "unknown",
            action=action,
            status=status,
            duration_ms=duration_ms,
            engine="autofix-v0.1",
            notes=notes,
            payload=payload,
        )
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


# -----------------------------------------------------------------------------
#  Public symbol expected by src.worker.tasks_devfactory
# -----------------------------------------------------------------------------

def run_autofix_df3_for_task(*args, **kwargs) -> Dict[str, Any]:
    """
    Entry point expected by tasks_devfactory.

    Flexible call shapes (NDC):
      - run_autofix_df3_for_task(conn, task_id, dry_run=True)
      - run_autofix_df3_for_task(task_id=..., dry_run=True, conn=...)
      - task_id may be numeric id or public_id UUID string
    """
    conn = None
    close_conn = False
    t0 = dt.datetime.now(dt.timezone.utc)

    try:
        if args and hasattr(args[0], "cursor"):
            conn = args[0]
            args = args[1:]
        else:
            conn = kwargs.pop("conn", None) or kwargs.pop("connection", None)

        if conn is None:
            conn = _connect_pg()
            close_conn = True

        task_ref = None
        if args:
            task_ref = args[0]
        task_ref = kwargs.get("task_id") or kwargs.get("id") or kwargs.get("dev_task_id") or task_ref

        dry_run = bool(kwargs.get("dry_run", True))

        task_id = _resolve_task_id(conn, task_ref)
        if task_id is None:
            return {"ok": False, "status": "bad_task_id", "task_ref": str(task_ref)}

        public_id, flowmind_plan_id, dev_order_id, stack = _fetch_df3_ids(conn, int(task_id))
        stack = stack or "unknown"

        # Lazy import: core autofix engine
        try:
            from src.core.devfactory import autofix as autofix_core  # type: ignore
        except Exception as exc:
            _df3_log_best_effort(
                conn,
                public_id=public_id,
                flowmind_plan_id=flowmind_plan_id,
                dev_order_id=dev_order_id,
                stack=stack,
                action="run" if dry_run else "apply",
                status="error",
                duration_ms=None,
                notes="Cannot import src.core.devfactory.autofix",
                payload={"error": f"{type(exc).__name__}: {exc}"},
            )
            return {"ok": False, "status": "engine_import_error", "error": f"{type(exc).__name__}: {exc}"}

        task = autofix_core.load_task(conn, int(task_id))
        if task is None:
            return {"ok": False, "status": "not_found", "task_id": int(task_id)}

        if not getattr(task, "autofix_enabled", False):
            _df3_log_best_effort(
                conn,
                public_id=public_id,
                flowmind_plan_id=flowmind_plan_id,
                dev_order_id=dev_order_id,
                stack=stack,
                action="run" if dry_run else "apply",
                status="disabled",
                duration_ms=None,
                notes="Autofix disabled (no-op)",
                payload={"dry_run": dry_run, "task_id": int(task_id)},
            )
            return {
                "ok": False,
                "status": "disabled",
                "task_id": int(task_id),
                "autofix_enabled": False,
                "autofix_status": getattr(task, "autofix_status", "disabled"),
            }

        if not autofix_core.can_autofix_stack(stack):
            _df3_log_best_effort(
                conn,
                public_id=public_id,
                flowmind_plan_id=flowmind_plan_id,
                dev_order_id=dev_order_id,
                stack=stack,
                action="run" if dry_run else "apply",
                status="skipped",
                duration_ms=None,
                notes="Stack not supported",
                payload={"dry_run": dry_run, "task_id": int(task_id), "stack": stack},
            )
            return {"ok": False, "status": "skipped", "task_id": int(task_id), "stack": stack}

        ok = False
        err: Optional[str] = None
        try:
            ok = bool(autofix_core.run_autofix_for_task(conn, int(task_id), dry_run=dry_run))
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            ok = False
            err = f"{type(exc).__name__}: {exc}"
            logger.exception("run_autofix_df3_for_task failed")

        t1 = dt.datetime.now(dt.timezone.utc)
        dur_ms = int((t1 - t0).total_seconds() * 1000)

        _df3_log_best_effort(
            conn,
            public_id=public_id,
            flowmind_plan_id=flowmind_plan_id,
            dev_order_id=dev_order_id,
            stack=stack,
            action="run" if dry_run else "apply",
            status="ok" if ok else "error",
            duration_ms=dur_ms,
            notes="run_autofix_df3_for_task",
            payload={"dry_run": dry_run, "task_id": int(task_id), "stack": stack, "error": err},
        )

        return {"ok": bool(ok), "status": "ok" if ok else "error", "task_id": int(task_id), "stack": stack, "dry_run": dry_run, "error": err}

    except Exception as exc:
        return {"ok": False, "status": "adapter_error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if close_conn and conn is not None:
            _safe_close(conn)


__all__ = ["run_autofix_df3_for_task"]
