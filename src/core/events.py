import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Json

log = logging.getLogger(__name__)

__all__ = [
    "emit_event",
    "link_events",
    "emit_start",
    "emit_done",
    "emit_error",
]

# DSN берём из тех же переменных, что и вся система
_EVENT_DSN = os.getenv("FF_DB_DSN") or os.getenv("DATABASE_URL")

# Таблицы можно переопределять
_EVENT_TABLE = os.getenv("FF_EVENTS_TABLE", "ops.event_log")
_EVENT_LINKS_TABLE = os.getenv("FF_EVENTS_LINKS_TABLE", "ops.event_links")

# Быстро выключить события (на случай инцидента), не ломая боевой код
_EVENTS_DISABLE = os.getenv("FF_EVENTS_DISABLE", "0").strip().lower() in ("1", "true", "yes", "y", "on")

# Кэш списка колонок event_log (TTL, чтобы не ходить в information_schema на каждое событие)
_EVENT_LOG_COLS: Optional[Set[str]] = None
_EVENT_LOG_COLS_TS: float = 0.0
_EVENT_LOG_COLS_TTL_SEC = float(os.getenv("FF_EVENTS_COLS_TTL_SEC", "300"))  # 5 минут


def _split_qualname(name: str) -> Tuple[str, str]:
    """
    Разобрать имя таблицы вида schema.table.
    Если schema не задана, используем FF_EVENTS_SCHEMA (default: ops).
    """
    name = (name or "").strip()
    if "." in name:
        schema, table = name.split(".", 1)
        return schema.strip(), table.strip()
    schema = (os.getenv("FF_EVENTS_SCHEMA") or "ops").strip() or "ops"
    return schema, name


def _pg_conn() -> psycopg.Connection:
    """
    Новое соединение к Postgres для событий.

    ВАЖНО:
      - отдельное соединение (не общий пул), чтобы наблюдаемость не портила боевые транзакции;
      - autocommit=True: чтобы ошибки вставки не оставляли соединение "aborted".
    """
    if not _EVENT_DSN:
        raise RuntimeError("FF_DB_DSN / DATABASE_URL is not configured for events")
    conn = psycopg.connect(_EVENT_DSN)
    conn.autocommit = True
    return conn


def _get_event_log_cols(force_refresh: bool = False) -> Set[str]:
    """
    Получить список колонок ops.event_log (или FF_EVENTS_TABLE) и закэшировать.
    """
    global _EVENT_LOG_COLS, _EVENT_LOG_COLS_TS

    now = time.time()
    if (
        not force_refresh
        and _EVENT_LOG_COLS is not None
        and (now - _EVENT_LOG_COLS_TS) < _EVENT_LOG_COLS_TTL_SEC
    ):
        return _EVENT_LOG_COLS

    schema, table = _split_qualname(_EVENT_TABLE)

    try:
        conn = _pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    """,
                    (schema, table),
                )
                cols = {row[0] for row in cur.fetchall()}
                _EVENT_LOG_COLS = cols
                _EVENT_LOG_COLS_TS = now
                return cols
        finally:
            conn.close()
    except Exception:
        # Не ломаем боевой код: просто считаем, что писать некуда
        log.exception("events: failed to introspect columns for %s", _EVENT_TABLE)
        _EVENT_LOG_COLS = set()
        _EVENT_LOG_COLS_TS = now
        return _EVENT_LOG_COLS


def _build_event_row(
    cols: Set[str],
    *,
    source: str,
    event_type: str,
    severity: str,
    correlation_id: Optional[str],
    tenant_id: Optional[str],
    payload: Dict[str, Any],
    context: Optional[Dict[str, Any]],
    message: Optional[str],
    error: Optional[str],
    ok: Optional[bool],
) -> Dict[str, Any]:
    """
    Собрать словарь {col: value} только по реально существующим колонкам.
    Если tenant_id колонки нет — сохраняем tenant_id в context.
    """
    now = datetime.now(timezone.utc)

    row: Dict[str, Any] = {}

    # timestamps (в твоей таблице есть и ts, и created_at)
    if "ts" in cols:
        row["ts"] = now
    if "created_at" in cols:
        row["created_at"] = now

    # базовые поля
    if "source" in cols:
        row["source"] = source

    if "event_type" in cols:
        row["event_type"] = event_type
    # в твоей таблице есть и "type" — заполним для совместимости
    if "type" in cols:
        row["type"] = event_type

    if "severity" in cols:
        row["severity"] = severity

    if "correlation_id" in cols:
        row["correlation_id"] = correlation_id

    # tenant_id: если колонки нет — кладём в context
    if "tenant_id" in cols:
        row["tenant_id"] = tenant_id

    ctx: Dict[str, Any] = dict(context or {})
    if tenant_id and "tenant_id" not in cols:
        ctx.setdefault("tenant_id", tenant_id)

    if "context" in cols:
        row["context"] = Json(ctx) if ctx else Json({})

    if "payload" in cols:
        row["payload"] = Json(payload or {})

    # ok/message/error (в твоей таблице есть)
    if "ok" in cols:
        if ok is None:
            sev = (severity or "").strip().lower()
            et = (event_type or "").strip().lower()
            row["ok"] = (sev not in ("error", "critical", "fatal")) and (et != "error")
        else:
            row["ok"] = bool(ok)

    if "message" in cols and message is not None:
        row["message"] = message

    if "error" in cols and error is not None:
        row["error"] = error

    # мета-поля (в твоей таблице есть channel/project_ref/language/links)
    if "channel" in cols:
        row["channel"] = os.getenv("FF_EVENTS_CHANNEL") or os.getenv("SERVICE_ROLE") or "system"

    if "project_ref" in cols:
        row["project_ref"] = (
            os.getenv("FF_PROJECT_REF")
            or os.getenv("PROJECT_NAME")
            or os.getenv("COMPOSE_PROJECT_NAME")
            or "foxproflow"
        )

    if "language" in cols:
        row["language"] = os.getenv("FF_EVENTS_LANGUAGE") or os.getenv("LANGUAGE") or "ru"

    if "links" in cols:
        row["links"] = Json({})

    return row


def _insert_event(row: Dict[str, Any]) -> int:
    """
    INSERT в event_log с RETURNING id.
    """
    if not row:
        return 0

    schema, table = _split_qualname(_EVENT_TABLE)
    q_table = sql.Identifier(schema, table)

    keys = list(row.keys())
    q_cols = sql.SQL(", ").join(sql.Identifier(k) for k in keys)
    q_vals = sql.SQL(", ").join(sql.Placeholder() for _ in keys)

    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(q_table, q_cols, q_vals)

    conn = _pg_conn()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, [row[k] for k in keys])
            rec = cur.fetchone()
            if not rec:
                return 0
            rid = rec.get("id")
            return int(rid) if rid is not None else 0
    finally:
        conn.close()


def emit_event(
    source: str,
    event_type: str,
    severity: str = "info",
    correlation_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    # необязательные поля (совместимо со старыми вызовами)
    context: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    ok: Optional[bool] = None,
) -> int:
    """
    Записать событие в ops.event_log и вернуть его id.

    Не должен ронять бизнес-логику: в случае ошибок логируем и возвращаем 0.

    ВАЖНО: колонка tenant_id может отсутствовать (как сейчас).
    Тогда tenant_id сохраняем в context (jsonb), а INSERT строим по реальным колонкам.
    """
    if _EVENTS_DISABLE:
        return 0

    try:
        cols = _get_event_log_cols()
        if not cols:
            return 0

        row = _build_event_row(
            cols,
            source=source,
            event_type=event_type,
            severity=severity,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            payload=payload or {},
            context=context,
            message=message,
            error=error,
            ok=ok,
        )
        return _insert_event(row)

    except psycopg.errors.UndefinedColumn:
        # Схема изменилась: обновим кэш и попробуем один раз ещё.
        log.warning("emit_event: UndefinedColumn. Refreshing columns cache and retrying once.")
        try:
            cols = _get_event_log_cols(force_refresh=True)
            row = _build_event_row(
                cols,
                source=source,
                event_type=event_type,
                severity=severity,
                correlation_id=correlation_id,
                tenant_id=tenant_id,
                payload=payload or {},
                context=context,
                message=message,
                error=error,
                ok=ok,
            )
            return _insert_event(row)
        except Exception:
            log.exception(
                "emit_event failed after retry: source=%s type=%s correlation_id=%s",
                source,
                event_type,
                correlation_id,
            )
            return 0

    except Exception:
        log.exception("emit_event failed: source=%s type=%s correlation_id=%s", source, event_type, correlation_id)
        return 0


def link_events(parent_id: int, child_id: int, relation: str = "caused") -> None:
    """
    Связать два события отношением (по умолчанию 'caused').

    Если таблицы ops.event_links нет — просто не падаем.
    """
    if _EVENTS_DISABLE:
        return
    if not parent_id or not child_id:
        return

    schema, table = _split_qualname(_EVENT_LINKS_TABLE)
    q_table = sql.Identifier(schema, table)

    conn = None
    try:
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (parent_id, child_id, relation)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """
                ).format(q_table),
                (parent_id, child_id, relation),
            )
    except Exception:
        log.exception("link_events failed: parent_id=%s child_id=%s relation=%s", parent_id, child_id, relation)
    finally:
        if conn is not None:
            conn.close()


def emit_start(
    source: str,
    correlation_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
) -> int:
    return emit_event(
        source=source,
        event_type="start",
        severity="info",
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        payload=payload,
        ok=True,
    )


def emit_done(
    source: str,
    correlation_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
) -> int:
    return emit_event(
        source=source,
        event_type="done",
        severity="info",
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        payload=payload,
        ok=True,
    )


def emit_error(
    source: str,
    correlation_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    error: Optional[str] = None,
) -> int:
    return emit_event(
        source=source,
        event_type="error",
        severity="error",
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        payload=payload,
        error=error,
        ok=False,
    )
