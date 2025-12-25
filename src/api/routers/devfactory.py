# -*- coding: utf-8 -*-
# file: src/api/routers/devfactory.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import json
import logging
import os
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

try:
    from api.security.flowsec_middleware import require_policies  # type: ignore
    from api.security.architect_guard import require_architect_key  # type: ignore
except ImportError:  # pragma: no cover
    from src.api.security.flowsec_middleware import require_policies  # type: ignore
    from src.api.security.architect_guard import require_architect_key  # type: ignore

from src.core.devfactory.models import DevTask
from src.core.devfactory.intent_models import (
    IntentChannel,
    IntentContext,
    IntentHints,
    IntentLanguage,
    IntentSource,
    IntentSpecV0_1,
)
from src.core.devfactory.intent_parser import parse_intent
from src.core.devfactory.question_engine import generate_questions
from src.core.devfactory import repository as dev_repo
from src.core.devfactory import autofix as autofix_core

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  DF-3 logging helper (SQL builder for analytics.log_devfactory_autofix_df3_event)
# ---------------------------------------------------------------------------

def _pg_literal(value: Optional[str]) -> str:
    """Безопасный SQL literal для строк (fallback)."""
    if value is None:
        return "null"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def build_log_autofix_df3_sql(
    *,
    dev_task_id: UUID,
    resource_kind: str,
    action: str,
    status: str,
    dev_order_id: Optional[UUID] = None,
    flowmind_plan_id: Optional[UUID] = None,
    resource_path: Optional[str] = None,
    duration_ms: Optional[int] = None,
    engine: str = "df3-core",
    notes: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Строит SQL для вызова функции:

      analytics.log_devfactory_autofix_df3_event(
          p_dev_task_id uuid,
          p_resource_kind text,
          p_action text,
          p_status text,
          p_dev_order_id uuid DEFAULT NULL,
          p_flowmind_plan_id uuid DEFAULT NULL,
          p_resource_path text DEFAULT NULL,
          p_duration_ms integer DEFAULT NULL,
          p_engine text DEFAULT NULL,
          p_notes text DEFAULT NULL,
          p_payload jsonb DEFAULT NULL
      ) -> bigint

    Важно: используем именованные аргументы (p_* := ...), чтобы не зависеть от порядка параметров.
    """
    dev_task_id_l = _pg_literal(str(dev_task_id))
    resource_kind_l = _pg_literal(resource_kind)
    action_l = _pg_literal(action)
    status_l = _pg_literal(status)

    dev_order_id_l = _pg_literal(str(dev_order_id)) if dev_order_id else "null"
    flowmind_plan_id_l = _pg_literal(str(flowmind_plan_id)) if flowmind_plan_id else "null"
    resource_path_l = _pg_literal(resource_path) if resource_path else "null"
    duration_ms_l = str(int(duration_ms)) if duration_ms is not None else "null"
    engine_l = _pg_literal(engine)
    notes_l = _pg_literal(notes) if notes else "null"

    if payload is None:
        payload_sql = "null"
    else:
        payload_sql = _pg_literal(json.dumps(payload, ensure_ascii=False))

    return (
        "select analytics.log_devfactory_autofix_df3_event("
        f"p_dev_task_id := {dev_task_id_l}::uuid,"
        f"p_resource_kind := {resource_kind_l}::text,"
        f"p_action := {action_l}::text,"
        f"p_status := {status_l}::text,"
        f"p_dev_order_id := {dev_order_id_l}::uuid,"
        f"p_flowmind_plan_id := {flowmind_plan_id_l}::uuid,"
        f"p_resource_path := {resource_path_l}::text,"
        f"p_duration_ms := {duration_ms_l}::int,"
        f"p_engine := {engine_l}::text,"
        f"p_notes := {notes_l}::text,"
        f"p_payload := {payload_sql}::jsonb"
        ");"
    )

# ---------------------------------------------------------------------------
#  Подключение к Postgres (выравниваемся с остальными роутерами: DATABASE_URL first)
# ---------------------------------------------------------------------------

_DEV_TASK_COLS_CACHE: Optional[Set[str]] = None


def _normalize_dsn(dsn: str) -> str:
    """
    SQLAlchemy может давать DATABASE_URL вида postgresql+asyncpg://...
    psycopg/psycopg2 это не любят. Нормализуем.
    """
    if not dsn:
        return dsn
    dsn = dsn.strip()
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    return dsn


def _connect_pg():
    """
    Локальный helper подключения к Postgres для DevFactory API.

    Приоритет:
      1) DATABASE_URL (как у dev_orders / flowsec / kpi)
      2) POSTGRES_* (docker compose env)
    """
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
        conn = psycopg.connect(dsn)
        return conn
    except Exception:  # noqa: BLE001
        import psycopg2 as psycopg  # type: ignore
        conn = psycopg.connect(dsn)
        return conn


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_error(status_code: int, *, detail: str, error: Optional[str] = None) -> JSONResponse:
    """Единый JSON-ответ об ошибке без raise (защита от превращения 4xx в 500)."""
    payload: Dict[str, Any] = {"detail": detail, "status_code": int(status_code)}
    if error is not None:
        payload["error"] = str(error)
    return JSONResponse(status_code=int(status_code), content=payload)


def _model_validate(model_cls: Any, data: Any) -> Any:
    """Pydantic v2/v1 compatible validation (model_validate/parse_obj/ctor)."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)  # type: ignore[attr-defined]
    parse_obj = getattr(model_cls, "parse_obj", None)
    if callable(parse_obj):
        return parse_obj(data)
    if isinstance(data, dict):
        return model_cls(**data)
    return model_cls(data)


def _model_dump(model: Any) -> Dict[str, Any]:
    """Pydantic v2/v1 compatible dump (model_dump/dict)."""
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    if hasattr(model, "dict"):
        return model.dict()  # type: ignore[attr-defined]
    if isinstance(model, dict):
        return model
    return {"value": str(model)}


def _dev_task_cols(conn) -> Set[str]:
    """
    NDC-safe introspection: не предполагаем, что колонки навсегда одинаковые.
    """
    global _DEV_TASK_COLS_CACHE
    if _DEV_TASK_COLS_CACHE is not None:
        return _DEV_TASK_COLS_CACHE

    cols: Set[str] = set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'dev' AND table_name = 'dev_task'
            """
        )
        for (name,) in cur.fetchall():
            cols.add(str(name))

    _DEV_TASK_COLS_CACHE = cols
    return cols


def _guess_resource_kind_from_stack(stack: Optional[str]) -> str:
    """
    DF-3 events ожидают _resource_kind_: sql|python|html|md|ps1|config|other.
    Стек DevTask (python_backend/sql/typescript/pwsh/...) маппим аккуратно.
    """
    s = (stack or "").lower()
    if "sql" in s:
        return "sql"
    if "python" in s:
        return "python"
    if "type" in s or "tsx" in s or "react" in s or "ui" in s or "html" in s:
        return "html"
    if "pwsh" in s or "powershell" in s or "ps1" in s:
        return "ps1"
    if "md" in s or "docs" in s or "doc" in s:
        return "md"
    if "yaml" in s or "yml" in s or "json" in s or "toml" in s or "ini" in s:
        return "config"
    return "other"


# ---------------------------------------------------------------------------
#  DF-3 logging: write-through (analytics + dev) with rollback on failure
# ---------------------------------------------------------------------------

def _df3_log_event(
    conn,
    *,
    devtask_id_int: int,
    dev_task_public_id: Optional[UUID],
    stack: Optional[str],
    action: str,
    status: str,
    ok: bool,
    dev_order_id: Optional[UUID] = None,
    flowmind_plan_id: Optional[UUID] = None,
    duration_ms: Optional[int] = None,
    notes: Optional[str] = None,
    error: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Пишет событие Autofix DF-3 сразу в 2 места:

    1) analytics.devfactory_autofix_df3_events — через функцию analytics.log_devfactory_autofix_df3_event(...)
       (это “каноническая” витрина DF-3).

    2) dev.dev_autofix_event_df3_log — напрямую (историческая/отладочная таблица,
       используется KPI fallback'ом и быстрыми проверками без refresh MV).

    Ключевой момент: если analytics-вызов упал, Postgres переводит транзакцию в aborted.
    Поэтому перед попыткой dev-вставки делаем rollback(), чтобы не получить
    “current transaction is aborted”.
    """
    # --- 0) Нормализация входа
    decision = "applied" if status in ("ok", "skipped") else "error"
    final_stage = "completed" if status in ("ok", "skipped") else "failed"
    stack_s = (stack or "unknown").strip() or "unknown"

    # metadata payload для dev-таблицы (не путать с analytics payload)
    meta_payload: Dict[str, Any] = {
        "action": str(action),
        "status": str(status),
        "ok": bool(ok),
        "engine": "autofix-v0.1",
    }
    if notes:
        meta_payload["notes"] = str(notes)
    if payload:
        meta_payload["payload"] = payload
    if dev_order_id is not None:
        meta_payload["dev_order_id"] = str(dev_order_id)
    if flowmind_plan_id is not None:
        meta_payload["flowmind_plan_id"] = str(flowmind_plan_id)

    # --- 1) analytics log (если есть public_id)
    if dev_task_public_id is not None:
        try:
            sql = build_log_autofix_df3_sql(
                dev_task_id=dev_task_public_id,
                resource_kind=_guess_resource_kind_from_stack(stack_s),
                action=str(action),
                status=str(status),
                dev_order_id=dev_order_id,
                flowmind_plan_id=flowmind_plan_id,
                resource_path=None,
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                engine="autofix-v0.1",
                notes=notes,
                payload=payload,
            )
            with conn.cursor() as cur:
                cur.execute(sql)
                # Забираем результат, чтобы не оставлять dangling-resultset.
                try:
                    cur.fetchone()
                except Exception:
                    pass
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("DF-3 analytics log failed (devtask_id=%s): %s", devtask_id_int, exc)
            try:
                conn.rollback()
            except Exception:
                pass

    # --- 2) dev log (write-through; не зависит от analytics)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('dev.dev_autofix_event_df3_log') IS NOT NULL;")
            has_dev = bool(cur.fetchone()[0])
    except Exception:
        has_dev = False

    if not has_dev:
        # Нечего делать — таблицы нет (или нет прав).
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dev.dev_autofix_event_df3_log (
                    devtask_id,
                    stack,
                    plan_id,
                    decision,
                    final_stage,
                    ok,
                    error,
                    started_at,
                    finished_at,
                    latency_ms,
                    metadata
                )
                VALUES (
                    %s, %s, NULL, %s, %s, %s, %s,
                    now(), now(), %s,
                    %s::jsonb
                )
                """,
                (
                    int(devtask_id_int),
                    stack_s,
                    decision,
                    final_stage,
                    bool(ok),
                    (str(error) if error else None),
                    (int(duration_ms) if duration_ms is not None else None),
                    _json_dumps(meta_payload),
                ),
            )
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("DF-3 direct log insert failed (devtask_id=%s): %s", devtask_id_int, exc)
        try:
            conn.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Router / policies
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/devfactory",
    tags=["devfactory"],
    dependencies=[Depends(require_policies("devfactory", ["view_tasks"]))],
)

# ---------------------------------------------------------------------------
#  Pydantic models
# ---------------------------------------------------------------------------


class DevTaskCreate(BaseModel):
    """Создание задачи DevFactory вручную (низкоуровневый путь)."""

    stack: str
    title: Optional[str] = None
    input_spec: Dict[str, Any] = Field(default_factory=dict)
    project_ref: Optional[str] = Field(
        None,
        description="ProjectRef (пишем в meta->'project_ref' для KPI/аналитики).",
    )


class DevTaskOut(BaseModel):
    """
    Публичное представление DevTask.

    created_at/updated_at/meta/error/links — нужны операторским консолям.
    """

    id: str
    public_id: Optional[str] = None
    stack: str
    title: Optional[str] = None
    status: str

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    input_spec: Dict[str, Any] = Field(default_factory=dict)
    result_spec: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)
    links: Dict[str, Any] = Field(default_factory=dict)

    error: Optional[str] = None

    autofix_enabled: bool = False
    autofix_status: str = "disabled"

    @classmethod
    def from_model(cls, t: DevTask) -> "DevTaskOut":
        def _iso(v: Any) -> Optional[str]:
            if v is None:
                return None
            try:
                return v.isoformat()
            except Exception:  # noqa: BLE001
                return str(v)

        return cls(
            id=str(getattr(t, "id")),
            public_id=str(getattr(t, "public_id")) if getattr(t, "public_id", None) is not None else None,
            stack=getattr(t, "stack", "") or "",
            title=getattr(t, "title", None),
            status=getattr(t, "status", "unknown") or "unknown",
            created_at=_iso(getattr(t, "created_at", None)),
            updated_at=_iso(getattr(t, "updated_at", None)),
            input_spec=getattr(t, "input_spec", None) or {},
            result_spec=getattr(t, "result_spec", None) or {},
            meta=getattr(t, "meta", None) or {},
            links=getattr(t, "links", None) or {},
            error=getattr(t, "error", None),
            autofix_enabled=bool(getattr(t, "autofix_enabled", False)),
            autofix_status=getattr(t, "autofix_status", "disabled") or "disabled",
        )


class DevTaskIntentCreate(BaseModel):
    """
    Запрос на создание задачи DevFactory через Intent Parser.

    Поддерживаем 2 формата (для обратной совместимости):

    A) raw_text + intent_context{source,channel,language,project_ref,hints}
    B) плоский формат: raw_text + source/channel/language/project_ref/hints
    """

    raw_text: str = Field(..., description="Сырой текст задачи (из UI/CRM/voice).")

    # Формат A (preferred in CLI): raw_text + intent_context{...}
    intent_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Совместимость: intent_context{source,channel,language,project_ref,hints}.",
    )

    # Формат B (fallback): плоские поля
    project_ref: str = Field(
        "foxproflow-core",
        description="Идентификатор проекта (пишем в meta->'project_ref').",
    )
    stack: Optional[str] = Field(
        None,
        description="Стек DevFactory (python_backend/sql/typescript/pwsh/docs/...).",
    )
    source: Optional[str] = Field(
        "operator_cli",
        description="Источник текста для IntentContext (operator_cli/architect_session/devorder/crm_import/other).",
    )
    language: Optional[str] = Field("ru", description="Язык текста (ru/en/other).")
    channel: Optional[str] = Field("text", description="Канал (text/voice_transcript/...).")

    hints: Dict[str, Any] = Field(
        default_factory=dict,
        description='Подсказки парсеру: {"stack":["python"],"area":["devfactory"]} и т.п.',
    )


class AutofixToggleOut(BaseModel):
    id: str
    autofix_enabled: bool
    autofix_status: str


class AutofixRunOut(BaseModel):
    id: str
    autofix_enabled: bool
    autofix_status: str
    ok: bool = Field(..., description="True=ok, False=error/skipped/unsupported")


class AutofixTaskKpiOut(BaseModel):
    dev_task_id: Optional[str]
    events_total: int
    events_success: int
    events_failed: int
    first_event_at: Optional[str]
    last_event_at: Optional[str]


# ---------------------------------------------------------------------------
#  Helpers: INSERT/readback/update
# ---------------------------------------------------------------------------

def _insert_dev_task(
    conn,
    *,
    stack: str,
    title: Optional[str],
    input_spec: Dict[str, Any],
    source: str,
    meta: Optional[Dict[str, Any]] = None,
) -> DevTask:
    """
    Прямое создание записи dev.dev_task через INSERT + commit.

    Правка DevTask 150 / IDE-sanity:
      - не используем приватный repository._row_to_dict;
      - делаем NDC-safe INSERT: добавляем только существующие колонки;
      - делаем readback через dev_repo.get_task() (единый источник правды модели DevTask).
    """
    cols = _dev_task_cols(conn)

    fields: List[str] = []
    placeholders: List[str] = []
    params: List[Any] = []

    def add(col: str, placeholder: str, val: Any) -> None:
        if col in cols:
            fields.append(col)
            placeholders.append(placeholder)
            params.append(val)

    add("stack", "%s", stack)
    add("title", "%s", title)
    add("status", "%s", "new")
    add("source", "%s", source)
    add("input_spec", "%s::jsonb", _json_dumps(input_spec or {}))

    if meta is not None:
        add("meta", "%s::jsonb", _json_dumps(meta))

    # defaults for new rows
    add("autofix_enabled", "%s", False)
    add("autofix_status", "%s", "disabled")

    if not fields:
        raise HTTPException(status_code=500, detail="dev.dev_task: no writable columns discovered")

    sql = f"""
    INSERT INTO dev.dev_task ({", ".join(fields)})
    VALUES ({", ".join(placeholders)})
    RETURNING id
    """.strip()

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()

    conn.commit()

    if not row or row[0] is None:
        raise HTTPException(status_code=500, detail="Failed to insert dev.dev_task (no id returned)")

    task_id_int = int(row[0])
    task = dev_repo.get_task(conn, task_id_int)
    if not task:
        raise HTTPException(status_code=404, detail="DevTask not found after insert")
    return task


def _fetch_dev_task_out(conn, task_id_int: int) -> DevTaskOut:
    """
    Единый readback (NDC-safe) для GET, чтобы ответы были консистентны.
    """
    cols = _dev_task_cols(conn)
    select_cols = [
        c
        for c in (
            "id",
            "public_id",
            "stack",
            "title",
            "status",
            "created_at",
            "updated_at",
            "input_spec",
            "result_spec",
            "meta",
            "links",
            "error",
            "autofix_enabled",
            "autofix_status",
        )
        if c in cols
    ]
    if "id" not in select_cols:
        raise HTTPException(status_code=500, detail="dev.dev_task: id column missing")

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(select_cols)} FROM dev.dev_task WHERE id = %s",
            (int(task_id_int),),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="DevTask not found")

    data = {select_cols[i]: row[i] for i in range(len(select_cols))}

    created_at = data.get("created_at")
    updated_at = data.get("updated_at")

    try:
        created_at_s = created_at.isoformat() if created_at is not None else None
    except Exception:  # noqa: BLE001
        created_at_s = str(created_at) if created_at is not None else None

    try:
        updated_at_s = updated_at.isoformat() if updated_at is not None else None
    except Exception:  # noqa: BLE001
        updated_at_s = str(updated_at) if updated_at is not None else None

    return DevTaskOut(
        id=str(data.get("id")),
        public_id=str(data.get("public_id")) if data.get("public_id") is not None else None,
        stack=str(data.get("stack") or ""),
        title=data.get("title"),
        status=str(data.get("status") or "unknown"),
        created_at=created_at_s,
        updated_at=updated_at_s,
        input_spec=data.get("input_spec") or {},
        result_spec=data.get("result_spec") or {},
        meta=data.get("meta") or {},
        links=data.get("links") or {},
        error=data.get("error"),
        autofix_enabled=bool(data.get("autofix_enabled") or False),
        autofix_status=str(data.get("autofix_status") or "disabled"),
    )


# ---------------------------------------------------------------------------
#  DevTask write-contour — PATCH/PUT (устраняет класс 405 allow: GET)
# ---------------------------------------------------------------------------

_DF_MANAGE_TASKS_DEP = require_policies("devfactory", ["manage_tasks"])


def _architect_key_ok(request: Request, x_ff_architect_key: Optional[str]) -> bool:
    """
    Проверка архитект-ключа:
      1) Пытаемся использовать канонический require_architect_key (если его сигнатура совпадает).
      2) Fallback: прямое сравнение с env FF_ARCHITECT_KEY.
    """
    try:
        guard = require_architect_key(allow_if_missing=False)
        return bool(guard(request, x_ff_architect_key))
    except Exception:
        expected = (os.getenv("FF_ARCHITECT_KEY", "") or "").strip()
        return bool(expected and x_ff_architect_key and str(x_ff_architect_key).strip() == expected)


def require_devfactory_task_write(
    request: Request,
    x_ff_architect_key: Optional[str] = Header(default=None, alias="X-FF-Architect-Key"),
) -> bool:
    """
    Write allow if:
      - FlowSec grants devfactory:manage_tasks, OR
      - ARCHITECT key matches FF_ARCHITECT_KEY.
    """
    try:
        _DF_MANAGE_TASKS_DEP(request)
        return True
    except HTTPException as e:
        if e.status_code not in (401, 403):
            raise

    if _architect_key_ok(request, x_ff_architect_key):
        return True

    raise HTTPException(status_code=403, detail="Forbidden (devfactory.manage_tasks or X-FF-Architect-Key required)")


class DevTaskPatchIn(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    stack: Optional[str] = None
    input_spec: Optional[Dict[str, Any]] = None
    result_spec: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None

    class Config:
        extra = "forbid"


class DevTaskPutIn(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    stack: Optional[str] = None
    input_spec: Dict[str, Any] = Field(default_factory=dict)
    result_spec: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


def _update_dev_task_partial(conn, task_id_int: int, body: DevTaskPatchIn) -> DevTaskOut:
    cols = _dev_task_cols(conn)
    sets: List[str] = []
    params: List[Any] = []

    def add_set(expr: str, val: Any) -> None:
        sets.append(expr)
        params.append(val)

    if body.title is not None and "title" in cols:
        add_set("title = %s", body.title)
    if body.status is not None and "status" in cols:
        add_set("status = %s", body.status)
    if body.priority is not None and "priority" in cols:
        add_set("priority = %s", int(body.priority))
    if body.stack is not None and "stack" in cols:
        add_set("stack = %s", body.stack)

    # JSONB merge (patch)
    if body.input_spec is not None and "input_spec" in cols:
        add_set("input_spec = COALESCE(input_spec, '{}'::jsonb) || %s::jsonb", _json_dumps(body.input_spec))
    if body.result_spec is not None and "result_spec" in cols:
        add_set("result_spec = COALESCE(result_spec, '{}'::jsonb) || %s::jsonb", _json_dumps(body.result_spec))
    if body.meta is not None and "meta" in cols:
        add_set("meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb", _json_dumps(body.meta))

    if "updated_at" in cols:
        sets.append("updated_at = now()")

    if not sets:
        raise HTTPException(status_code=400, detail="No updatable fields supplied")

    with conn.cursor() as cur:
        cur.execute(f"UPDATE dev.dev_task SET {', '.join(sets)} WHERE id = %s", (*params, int(task_id_int)))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="DevTask not found")

    conn.commit()
    return _fetch_dev_task_out(conn, int(task_id_int))


def _update_dev_task_replace(conn, task_id_int: int, body: DevTaskPutIn) -> DevTaskOut:
    cols = _dev_task_cols(conn)
    sets: List[str] = []
    params: List[Any] = []

    def add_set(expr: str, val: Any) -> None:
        sets.append(expr)
        params.append(val)

    if body.title is not None and "title" in cols:
        add_set("title = %s", body.title)
    if body.status is not None and "status" in cols:
        add_set("status = %s", body.status)
    if body.priority is not None and "priority" in cols:
        add_set("priority = %s", int(body.priority))
    if body.stack is not None and "stack" in cols:
        add_set("stack = %s", body.stack)

    # JSONB replace (put)
    if "input_spec" in cols:
        add_set("input_spec = %s::jsonb", _json_dumps(body.input_spec or {}))
    if "result_spec" in cols:
        add_set("result_spec = %s::jsonb", _json_dumps(body.result_spec or {}))
    if "meta" in cols:
        add_set("meta = %s::jsonb", _json_dumps(body.meta or {}))

    if "updated_at" in cols:
        sets.append("updated_at = now()")

    if not sets:
        raise HTTPException(status_code=500, detail="dev.dev_task: no writable columns discovered")

    with conn.cursor() as cur:
        cur.execute(f"UPDATE dev.dev_task SET {', '.join(sets)} WHERE id = %s", (*params, int(task_id_int)))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="DevTask not found")

    conn.commit()
    return _fetch_dev_task_out(conn, int(task_id_int))


# ---------------------------------------------------------------------------
#  Endpoints: DevFactory tasks
# ---------------------------------------------------------------------------

@router.post("/tasks", response_model=DevTaskOut, summary="Создать задачу DevFactory (ручной режим)")
def create_dev_task(body: DevTaskCreate) -> DevTaskOut:
    conn = _connect_pg()
    try:
        project_ref = (body.project_ref or "").strip() or None
        meta: Dict[str, Any] = {}
        if project_ref:
            meta["project_ref"] = project_ref

        task = _insert_dev_task(
            conn,
            stack=body.stack,
            title=body.title,
            input_spec=body.input_spec or {},
            source="architect",
            meta=meta,
        )
        return _fetch_dev_task_out(conn, int(getattr(task, "id")))
    finally:
        _safe_close(conn)


@router.post("/tasks/intent", response_model=DevTaskOut, summary="Создать задачу DevFactory через Intent Parser")
def create_dev_task_from_intent(body: DevTaskIntentCreate) -> DevTaskOut:
    raw_text = (body.raw_text or "").strip()

    if not raw_text:
        raise HTTPException(status_code=422, detail="raw_text is required")

    # ---- merge format A (intent_context) + format B (flat)
    ctx_in: Dict[str, Any] = {}
    if body.intent_context:
        ctx_in = body.intent_context
    # если вдруг прилетело строкой (на всякий)
    if isinstance(ctx_in, str):
        try:
            ctx_in = json.loads(ctx_in)
        except Exception:
            ctx_in = {}

    project_ref = str((ctx_in.get("project_ref") or body.project_ref or "")).strip()
    source_raw = ctx_in.get("source") if "source" in ctx_in else body.source
    language_raw = ctx_in.get("language") if "language" in ctx_in else body.language
    channel_raw = ctx_in.get("channel") if "channel" in ctx_in else body.channel
    hints_raw = ctx_in.get("hints") if "hints" in ctx_in else (body.hints or {})

    if not project_ref:
        raise HTTPException(status_code=422, detail="project_ref is required (either top-level or intent_context.project_ref)")

    # Coerce enums/hints explicitly (invalid values => 422 JSON, not 500)
    try:
        source = IntentSource(str(source_raw)) if source_raw else IntentSource.OPERATOR_CLI
        language = IntentLanguage(str(language_raw)) if language_raw else IntentLanguage.RU
        channel = IntentChannel(str(channel_raw)) if channel_raw else IntentChannel.TEXT
        hints = _model_validate(IntentHints, hints_raw or {})

        ctx = IntentContext(
            project_ref=project_ref,
            source=source,
            language=language,
            channel=channel,
            hints=hints,
        )
    except (ValueError, ValidationError) as ve:
        return _json_error(422, detail="validation error", error=str(ve))

    try:
        intent_spec = parse_intent(raw_text, ctx)
    except Exception as exc:  # noqa: BLE001
        return _json_error(400, detail="intent parse failed", error=str(exc))

    # stack: explicit > body.stack > infer from intent
    stack = (body.stack or "").strip() or None
    if not stack:
        stack = "python_backend"
        try:
            if intent_spec.stack.languages:
                lang0 = intent_spec.stack.languages[0]
                if lang0 == "sql":
                    stack = "sql"
                elif lang0 not in ("python", "sql"):
                    stack = str(lang0)
        except Exception:  # noqa: BLE001
            pass

    input_spec: Dict[str, Any] = {
        "intent": intent_spec.to_storage_dict(),
        "raw_text": raw_text,
        "intent_context": {
            "project_ref": project_ref,
            "source": getattr(source, "value", str(source)),
            "language": getattr(language, "value", str(language)),
            "channel": getattr(channel, "value", str(channel)),
            "hints": _model_dump(hints),
        },
    }

    title = getattr(intent_spec.summary, "short_title", None) or raw_text.splitlines()[0].strip()

    meta = {
        "project_ref": project_ref,
        "language": getattr(language, "value", str(language)),
        "channel": getattr(channel, "value", str(channel)),
        "source": getattr(source, "value", str(source)),
    }

    conn = _connect_pg()
    try:
        task = _insert_dev_task(
            conn,
            stack=stack,
            title=title,
            input_spec=input_spec,
            source="intent_parser",
            meta=meta,
        )
        return _fetch_dev_task_out(conn, int(getattr(task, "id")))
    finally:
        _safe_close(conn)


@router.post(
    "/tasks/{task_id}/questions/regen",
    response_model=DevTaskOut,
    summary="Сгенерировать/обновить вопросы задачи через Question Engine",
)
def regen_questions_for_task(task_id: str) -> DevTaskOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")

        task = dev_repo.get_task(conn, task_id_int)
        if not task:
            raise HTTPException(status_code=404, detail="DevTask not found")

        input_spec = task.input_spec or {}
        intent_data = input_spec.get("intent")
        if not intent_data:
            raise HTTPException(
                status_code=400,
                detail="Task has no intent in input_spec['intent'] (create via /devfactory/tasks/intent).",
            )

        try:
            intent = _model_validate(IntentSpecV0_1, intent_data)
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Failed to parse intent from input_spec: {ex}") from ex

        ctx_raw = input_spec.get("intent_context") or {}
        ctx: Optional[IntentContext] = None

        if ctx_raw:
            try:
                ctx = _model_validate(IntentContext, ctx_raw)
            except ValidationError as ve:
                logger.warning("Invalid intent_context in task %s: %s", task_id_int, ve)
                ctx = None

        if ctx is None:
            pr = (
                (getattr(task, "meta", {}) or {}).get("project_ref")
                or input_spec.get("project_ref")
                or (getattr(task, "links", {}) or {}).get("project_ref")
                or "foxproflow-core"
            )
            ctx = IntentContext(
                project_ref=str(pr),
                source=IntentSource.OPERATOR_CLI,
                language=IntentLanguage.RU,
                channel=IntentChannel.TEXT,
                hints=IntentHints(stack=[getattr(task, "stack", "")], area=[]),
            )

        q_result = generate_questions(intent=intent, ctx=ctx)
        questions_json = _json_dumps(q_result.to_storage_dict())

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dev.dev_task
                   SET input_spec = COALESCE(input_spec, '{}'::jsonb)
                                     || jsonb_build_object('questions', %s::jsonb),
                       updated_at  = now()
                 WHERE id = %s
                """,
                (questions_json, task_id_int),
            )
        conn.commit()

        return _fetch_dev_task_out(conn, task_id_int)
    finally:
        _safe_close(conn)


@router.get("/tasks/{task_id}", response_model=DevTaskOut, summary="Получить задачу DevFactory по id")
def get_dev_task(task_id: str) -> DevTaskOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")
        return _fetch_dev_task_out(conn, task_id_int)
    finally:
        _safe_close(conn)


@router.patch("/tasks/{task_id}", response_model=DevTaskOut, summary="PATCH DevTask (partial update)")
def patch_dev_task(task_id: str, body: DevTaskPatchIn, _ok: bool = Depends(require_devfactory_task_write)) -> DevTaskOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")
        return _update_dev_task_partial(conn, task_id_int, body)
    finally:
        _safe_close(conn)


@router.put("/tasks/{task_id}", response_model=DevTaskOut, summary="PUT DevTask (replace JSONB fields)")
def put_dev_task(task_id: str, body: DevTaskPutIn, _ok: bool = Depends(require_devfactory_task_write)) -> DevTaskOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")
        return _update_dev_task_replace(conn, task_id_int, body)
    finally:
        _safe_close(conn)


@router.get("/tasks", response_model=List[DevTaskOut], summary="Список задач DevFactory")
def list_dev_tasks(
    status: Optional[str] = Query(None, description="Фильтр по статусу (new/in_progress/done/error/...)"),
    stack: Optional[str] = Query(None, description="Фильтр по стеку (substring match, ILIKE)"),
    dev_order_id: Optional[str] = Query(None, description="Фильтр по meta->>'dev_order_id' (UUID)"),
    flowmind_plan_id: Optional[str] = Query(None, description="Фильтр по meta->>'flowmind_plan_id' (UUID)"),
    q: Optional[str] = Query(None, description="Свободный поиск по id/public_id/title/raw_text (ILIKE)"),
    limit: int = Query(50, ge=1, le=500, description="Максимальное число задач в ответе"),
) -> List[DevTaskOut]:
    conn = _connect_pg()
    try:
        cols = _dev_task_cols(conn)

        select_cols = [
            c
            for c in (
                "id",
                "public_id",
                "stack",
                "title",
                "status",
                "created_at",
                "updated_at",
                "input_spec",
                "result_spec",
                "meta",
                "links",
                "error",
                "autofix_enabled",
                "autofix_status",
            )
            if c in cols
        ]
        if "id" not in select_cols:
            raise HTTPException(status_code=500, detail="dev.dev_task: id column missing")

        where: List[str] = []
        params: List[Any] = []

        if status and "status" in cols:
            where.append("status = %s")
            params.append(status)

        if stack and "stack" in cols:
            where.append("stack ILIKE %s")
            params.append(f"%{stack}%")

        if dev_order_id:
            if "meta" not in cols:
                raise HTTPException(
                    status_code=500,
                    detail="dev.dev_task: meta column missing (cannot filter by dev_order_id)",
                )
            where.append("(meta->>'dev_order_id') = %s")
            params.append(dev_order_id)

        if flowmind_plan_id:
            if "meta" not in cols:
                raise HTTPException(
                    status_code=500,
                    detail="dev.dev_task: meta column missing (cannot filter by flowmind_plan_id)",
                )
            where.append("(meta->>'flowmind_plan_id') = %s")
            params.append(flowmind_plan_id)

        if q:
            qq = f"%{q}%"
            parts: List[str] = []
            if "id" in cols:
                parts.append("CAST(id AS text) ILIKE %s")
                params.append(qq)
            if "public_id" in cols:
                parts.append("CAST(public_id AS text) ILIKE %s")
                params.append(qq)
            if "title" in cols:
                parts.append("COALESCE(title,'') ILIKE %s")
                params.append(qq)
            if "input_spec" in cols:
                parts.append("COALESCE(input_spec->>'raw_text','') ILIKE %s")
                params.append(qq)

            if parts:
                where.append("(" + " OR ".join(parts) + ")")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_col = "created_at" if "created_at" in cols else "id"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM dev.dev_task
                {where_sql}
                ORDER BY {order_col} DESC
                LIMIT %s
                """,
                (*params, int(limit)),
            )
            rows = cur.fetchall() or []

        out: List[DevTaskOut] = []
        for r in rows:
            data = {select_cols[i]: r[i] for i in range(len(select_cols))}

            created_at = data.get("created_at")
            updated_at = data.get("updated_at")
            try:
                created_at_s = created_at.isoformat() if created_at is not None else None
            except Exception:  # noqa: BLE001
                created_at_s = str(created_at) if created_at is not None else None
            try:
                updated_at_s = updated_at.isoformat() if updated_at is not None else None
            except Exception:  # noqa: BLE001
                updated_at_s = str(updated_at) if updated_at is not None else None

            out.append(
                DevTaskOut(
                    id=str(data.get("id")),
                    public_id=str(data.get("public_id")) if data.get("public_id") is not None else None,
                    stack=str(data.get("stack") or ""),
                    title=data.get("title"),
                    status=str(data.get("status") or "unknown"),
                    created_at=created_at_s,
                    updated_at=updated_at_s,
                    input_spec=data.get("input_spec") or {},
                    result_spec=data.get("result_spec") or {},
                    meta=data.get("meta") or {},
                    links=data.get("links") or {},
                    error=data.get("error"),
                    autofix_enabled=bool(data.get("autofix_enabled") or False),
                    autofix_status=str(data.get("autofix_status") or "disabled"),
                )
            )

        return out
    finally:
        _safe_close(conn)


# ---------------------------------------------------------------------------
#  Autofix: KPI по задаче (DF-3)
# ---------------------------------------------------------------------------

@router.get(
    "/tasks/{task_id}/autofix/kpi",
    response_model=AutofixTaskKpiOut,
    summary="Показатели Autofix DF-3 по задаче",
)
def get_autofix_kpi_for_task(task_id: str) -> AutofixTaskKpiOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")

        with conn.cursor() as cur:
            cur.execute("SELECT public_id FROM dev.dev_task WHERE id = %s", (task_id_int,))
            row = cur.fetchone()

        if row is None or row[0] is None:
            return AutofixTaskKpiOut(
                dev_task_id=None,
                events_total=0,
                events_success=0,
                events_failed=0,
                first_event_at=None,
                last_event_at=None,
            )

        public_id_str = str(row[0])

        # 1) Быстрый путь: MV (если она актуальна)
        mv_tuple: Optional[tuple] = None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        dev_task_id::text,
                        events_total,
                        events_success,
                        events_failed,
                        first_event_at,
                        last_event_at
                    FROM analytics.devfactory_autofix_df3_kpi_by_task_mv
                    WHERE dev_task_id = %s
                    """,
                    (public_id_str,),
                )
                mv = cur.fetchone()
            if mv:
                (
                    _dev_task_id_val,
                    events_total,
                    events_success,
                    events_failed,
                    first_event_at,
                    last_event_at,
                ) = mv
                mv_tuple = (
                    int(events_total or 0),
                    int(events_success or 0),
                    int(events_failed or 0),
                    first_event_at,
                    last_event_at,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autofix KPI MV read failed: %s", exc)
            mv_tuple = None

        # 2) Канонический fallback: напрямую из analytics.devfactory_autofix_df3_events (без refresh MV)
        analytics_tuple: Optional[tuple] = None
        try:
            # Считаем только если MV отсутствует или явно нулевая (обычная ситуация при stale MV).
            if mv_tuple is None or int(mv_tuple[0]) == 0:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            count(*)::int,
                            sum(CASE WHEN status IN ('ok','skipped') THEN 1 ELSE 0 END)::int,
                            sum(CASE WHEN status NOT IN ('ok','skipped') THEN 1 ELSE 0 END)::int,
                            min(created_at),
                            max(created_at)
                        FROM analytics.devfactory_autofix_df3_events
                        WHERE dev_task_id = %s::uuid
                        """,
                        (public_id_str,),
                    )
                    analytics_tuple = cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autofix KPI analytics base read failed: %s", exc)
            analytics_tuple = None

        # 3) Legacy fallback: напрямую из dev.dev_autofix_event_df3_log по внутреннему id задачи
        dev_tuple: Optional[tuple] = None
        try:
            if (mv_tuple is None or int(mv_tuple[0]) == 0) and (
                analytics_tuple is None or int((analytics_tuple[0] or 0)) == 0
            ):
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            count(*)::int,
                            sum(CASE WHEN ok THEN 1 ELSE 0 END)::int,
                            sum(CASE WHEN NOT ok THEN 1 ELSE 0 END)::int,
                            min(started_at),
                            max(coalesce(finished_at, started_at))
                        FROM dev.dev_autofix_event_df3_log
                        WHERE devtask_id = %s
                        """,
                        (task_id_int,),
                    )
                    dev_tuple = cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autofix KPI dev log read failed: %s", exc)
            dev_tuple = None

        # 4) Выбираем «самый полный» источник (по events_total)
        best = mv_tuple
        if analytics_tuple is not None:
            if best is None or int((analytics_tuple[0] or 0)) > int(best[0] or 0):
                best = analytics_tuple
        if dev_tuple is not None:
            if best is None or int((dev_tuple[0] or 0)) > int(best[0] or 0):
                best = dev_tuple

        if not best:
            return AutofixTaskKpiOut(
                dev_task_id=public_id_str,
                events_total=0,
                events_success=0,
                events_failed=0,
                first_event_at=None,
                last_event_at=None,
            )

        events_total, events_success, events_failed, first_event_at, last_event_at = best

        return AutofixTaskKpiOut(
            dev_task_id=public_id_str,
            events_total=int(events_total or 0),
            events_success=int(events_success or 0),
            events_failed=int(events_failed or 0),
            first_event_at=first_event_at.isoformat() if first_event_at else None,
            last_event_at=last_event_at.isoformat() if last_event_at else None,
        )
    finally:
        _safe_close(conn)


# ---------------------------------------------------------------------------
#  Autofix: запуск, включение/выключение (DF-3)
# ---------------------------------------------------------------------------

@router.post(
    "/tasks/{task_id}/autofix/run",
    response_model=AutofixRunOut,
    summary="Запустить Autofix для задачи DevFactory (sync, DF-3 log)",
)
def run_autofix_for_task(
    task_id: str,
    dry_run: bool = True,
    _ok: bool = Depends(require_devfactory_task_write),
) -> AutofixRunOut:
    conn = _connect_pg()
    t0 = time.monotonic()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")

        task = autofix_core.load_task(conn, task_id_int)
        if task is None:
            raise HTTPException(status_code=404, detail="DevTask not found")

        dev_task_public_id: Optional[UUID] = None
        flowmind_plan_uuid: Optional[UUID] = None
        dev_order_uuid: Optional[UUID] = None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT public_id,
                           meta->>'flowmind_plan_id' AS flowmind_plan_id,
                           meta->>'dev_order_id'     AS dev_order_id
                    FROM dev.dev_task
                    WHERE id = %s
                    """,
                    (task_id_int,),
                )
                row = cur.fetchone()
            if row is not None:
                public_id_raw, plan_id_raw, dev_order_raw = row
                if public_id_raw is not None:
                    dev_task_public_id = public_id_raw if isinstance(public_id_raw, UUID) else UUID(str(public_id_raw))
                if plan_id_raw:
                    try:
                        flowmind_plan_uuid = UUID(str(plan_id_raw))
                    except Exception:  # noqa: BLE001
                        flowmind_plan_uuid = None
                if dev_order_raw:
                    try:
                        dev_order_uuid = UUID(str(dev_order_raw))
                    except Exception:  # noqa: BLE001
                        dev_order_uuid = None
        except Exception:  # noqa: BLE001
            pass

        if not getattr(task, "autofix_enabled", False):
            raise HTTPException(status_code=400, detail="Autofix is not enabled for this task")

        stack_supported = autofix_core.can_autofix_stack(getattr(task, "stack", None))

        if not stack_supported:
            duration_ms = int((time.monotonic() - t0) * 1000.0)
            _df3_log_event(
                conn,
                devtask_id_int=task_id_int,
                dev_task_public_id=dev_task_public_id,
                stack=getattr(task, "stack", None),
                action="run" if dry_run else "apply",
                status="skipped",
                ok=True,
                dev_order_id=dev_order_uuid,
                flowmind_plan_id=flowmind_plan_uuid,
                duration_ms=duration_ms,
                notes="Stack not supported, Autofix skipped",
                payload={
                    "dry_run": bool(dry_run),
                    "stack": getattr(task, "stack", None),
                    "reason": "stack_not_supported",
                },
            )

            return AutofixRunOut(
                id=str(getattr(task, "id")),
                autofix_enabled=bool(getattr(task, "autofix_enabled", False)),
                autofix_status=str(getattr(task, "autofix_status", "disabled") or "disabled"),
                ok=False,
            )

        ok = autofix_core.run_autofix_for_task(conn, task_id_int, dry_run=dry_run)
        conn.commit()

        updated = autofix_core.load_task(conn, task_id_int)
        if updated is None:
            raise HTTPException(status_code=404, detail="DevTask not found after autofix")

        duration_ms = int((time.monotonic() - t0) * 1000.0)

        _df3_log_event(
            conn,
            devtask_id_int=task_id_int,
            dev_task_public_id=dev_task_public_id,
            stack=getattr(task, "stack", None),
            action="run" if dry_run else "apply",
            status=("ok" if ok else "error"),
            ok=bool(ok),
            dev_order_id=dev_order_uuid,
            flowmind_plan_id=flowmind_plan_uuid,
            duration_ms=duration_ms,
            notes="DF-3 bridge from /devfactory/tasks/{task_id}/autofix/run",
            error=(getattr(updated, "error", None) if not ok else None),
            payload={
                "dry_run": bool(dry_run),
                "stack": getattr(task, "stack", None),
                "autofix_status_before": getattr(task, "autofix_status", None),
                "autofix_status_after": getattr(updated, "autofix_status", None),
            },
        )

        return AutofixRunOut(
            id=str(getattr(updated, "id")),
            autofix_enabled=bool(getattr(updated, "autofix_enabled", False)),
            autofix_status=str(getattr(updated, "autofix_status", "disabled") or "disabled"),
            ok=bool(ok),
        )
    finally:
        _safe_close(conn)


@router.post(
    "/tasks/{task_id}/autofix/enable",
    response_model=AutofixToggleOut,
    summary="Включить Autofix для задачи DevFactory",
)
def enable_autofix_for_task(task_id: str, _ok: bool = Depends(require_devfactory_task_write)) -> AutofixToggleOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")

        task = autofix_core.load_task(conn, task_id_int)
        if task is None:
            raise HTTPException(status_code=404, detail="DevTask not found")

        if not autofix_core.can_autofix_stack(getattr(task, "stack", None)):
            raise HTTPException(
                status_code=400,
                detail=f"Autofix not allowed for stack {getattr(task, 'stack', None)!r}",
            )

        autofix_core.enable_autofix(conn, task_id_int)
        conn.commit()

        updated = autofix_core.load_task(conn, task_id_int)
        if updated is None:
            raise HTTPException(status_code=404, detail="DevTask not found after update")

        return AutofixToggleOut(
            id=str(getattr(updated, "id")),
            autofix_enabled=bool(getattr(updated, "autofix_enabled", False)),
            autofix_status=str(getattr(updated, "autofix_status", "disabled") or "disabled"),
        )
    finally:
        _safe_close(conn)


@router.post(
    "/tasks/{task_id}/autofix/disable",
    response_model=AutofixToggleOut,
    summary="Выключить Autofix для задачи DevFactory",
)
def disable_autofix_for_task(task_id: str, _ok: bool = Depends(require_devfactory_task_write)) -> AutofixToggleOut:
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id (not an integer)")

        task = autofix_core.load_task(conn, task_id_int)
        if task is None:
            raise HTTPException(status_code=404, detail="DevTask not found")

        autofix_core.disable_autofix(conn, task_id_int)
        conn.commit()

        updated = autofix_core.load_task(conn, task_id_int)
        if updated is None:
            raise HTTPException(status_code=404, detail="DevTask not found after update")

        return AutofixToggleOut(
            id=str(getattr(updated, "id")),
            autofix_enabled=bool(getattr(updated, "autofix_enabled", False)),
            autofix_status=str(getattr(updated, "autofix_status", "disabled") or "disabled"),
        )
    finally:
        _safe_close(conn)
