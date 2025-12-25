# -*- coding: utf-8 -*-
# file: src/api/routers/devfactory_intent.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.security.flowsec_middleware import require_policies


def _connect_pg():
    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
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


def _row_to_dict(cur, row) -> Dict[str, Any]:
    cols = []
    for d in cur.description or []:
        cols.append(getattr(d, "name", None) or d[0])
    return {cols[i]: row[i] for i in range(len(cols))}


router = APIRouter(
    prefix="/devfactory",
    tags=["devfactory"],
    dependencies=[Depends(require_policies("devfactory", ["view_tasks"]))],
)


class DevTaskIntentIn(BaseModel):
    project_ref: str = Field(..., description="Проект/контур (для контекста)")
    language: str = Field("ru", description="Язык смысла")
    channel: str = Field("text", description="Канал")
    raw_text: str = Field(..., description="Сырой текст IntentSpec/ResultSpec")


class DevTaskOut(BaseModel):
    id: int
    public_id: Optional[str] = None
    stack: str
    title: Optional[str] = None
    status: str
    input_spec: Dict[str, Any] = Field(default_factory=dict)
    result_spec: Dict[str, Any] = Field(default_factory=dict)


def _guess_title(raw_text: str) -> str:
    first = (raw_text or "").splitlines()[0].strip()
    return first or "DevTask (intent)"


@router.post("/tasks/intent", response_model=DevTaskOut, summary="Создать DevTask из raw_text (bootstrap intent)")
def create_task_intent(body: DevTaskIntentIn) -> DevTaskOut:
    conn = _connect_pg()
    try:
        title = _guess_title(body.raw_text)
        stack = "generic"

        input_spec = {
            "intent": None,
            "raw_text": body.raw_text,
            "intent_context": {
                "project_ref": body.project_ref,
                "language": body.language,
                "channel": body.channel,
            },
        }

        payload = json.dumps(input_spec, ensure_ascii=False)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dev.dev_task (stack, title, input_spec, source)
                VALUES (%s, %s, %s::jsonb, %s)
                RETURNING id, public_id, stack, title, status, input_spec, result_spec
                """,
                (stack, title, payload, "devfactory.intent.api"),
            )
            row = cur.fetchone()
        conn.commit()

        if not row:
            raise HTTPException(status_code=500, detail="Insert returned no row")

        # psycopg2 returns tuple, psycopg3 also
        # map by position
        tid, public_id, stack_val, title_val, status_val, input_spec_val, result_spec_val = row
        return DevTaskOut(
            id=int(tid),
            public_id=str(public_id) if public_id is not None else None,
            stack=str(stack_val),
            title=str(title_val) if title_val is not None else None,
            status=str(status_val),
            input_spec=input_spec_val or {},
            result_spec=result_spec_val or {},
        )
    finally:
        conn.close()


@router.get("/tasks/{task_id}", response_model=DevTaskOut, summary="Получить DevTask по id")
def get_task(task_id: int) -> DevTaskOut:
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, public_id, stack, title, status, input_spec, result_spec
                FROM dev.dev_task
                WHERE id = %s
                """,
                (int(task_id),),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="DevTask not found")

        tid, public_id, stack_val, title_val, status_val, input_spec_val, result_spec_val = row
        return DevTaskOut(
            id=int(tid),
            public_id=str(public_id) if public_id is not None else None,
            stack=str(stack_val),
            title=str(title_val) if title_val is not None else None,
            status=str(status_val),
            input_spec=input_spec_val or {},
            result_spec=result_spec_val or {},
        )
    finally:
        conn.close()


@router.get("/tasks", response_model=List[DevTaskOut], summary="Список DevTasks (простые фильтры)")
def list_tasks(
    status: Optional[str] = Query(None),
    stack: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> List[DevTaskOut]:
    conn = _connect_pg()
    try:
        where = []
        params: List[Any] = []
        if status:
            where.append("status = %s")
            params.append(status)
        if stack:
            where.append("stack = %s")
            params.append(stack)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, public_id, stack, title, status, input_spec, result_spec
                FROM dev.dev_task
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*params, int(limit)),
            )
            rows = cur.fetchall() or []

        out: List[DevTaskOut] = []
        for r in rows:
            tid, public_id, stack_val, title_val, status_val, input_spec_val, result_spec_val = r
            out.append(
                DevTaskOut(
                    id=int(tid),
                    public_id=str(public_id) if public_id is not None else None,
                    stack=str(stack_val),
                    title=str(title_val) if title_val is not None else None,
                    status=str(status_val),
                    input_spec=input_spec_val or {},
                    result_spec=result_spec_val or {},
                )
            )
        return out
    finally:
        conn.close()
