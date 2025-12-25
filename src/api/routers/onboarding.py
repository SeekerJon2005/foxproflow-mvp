# -*- coding: utf-8 -*-
# file: src/api/routers/onboarding.py
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# ВАЖНО:
# prefix="/onboarding" + include_router(..., prefix="/api") в main.py
# дают итоговые пути /api/onboarding/...
router = APIRouter(
    prefix="/onboarding",
    tags=["onboarding"],
)


# --- Вспомогательные функции подключения к Postgres -------------------------


def _build_pg_dsn() -> str:
    """
    Собираем DSN для Postgres по тем же правилам, что и в crm-роутере.
    """
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn

    user = os.getenv("POSTGRES_USER", "admin")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "foxproflow")

    if pwd:
        auth = f"{user}:{pwd}"
    else:
        auth = user

    return f"postgresql://{auth}@{host}:{port}/{db}"


def _connect_pg():
    """
    Подключение к Postgres: сначала пробуем psycopg3, затем psycopg2.
    """
    dsn = _build_pg_dsn()
    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except Exception:
        import psycopg2  # type: ignore

        return psycopg2.connect(dsn)


# --- Pydantic-модели --------------------------------------------------------


class OnboardingStep(BaseModel):
    step_code: str
    status: str
    updated_at: Optional[datetime] = None
    comment: Optional[str] = None

    class Config:
        orm_mode = True


class OnboardingSession(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    account_id: int
    status: str
    steps: List[OnboardingStep] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class OnboardingStepUpdateRequest(BaseModel):
    """
    Обновление статуса конкретного шага.

    Допустимые статусы шага:
    - pending
    - in_progress
    - done
    - blocked
    """

    status: str = Field(..., description="pending|in_progress|done|blocked")
    comment: Optional[str] = None


class OnboardingSessionOverview(BaseModel):
    """
    Строка витрины crm.onboarding_sessions_overview_v.
    """

    onboarding_id: int
    account_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    total_steps: int
    done_steps: int
    in_progress_steps: int
    blocked_steps: int
    has_blocked: bool
    open_steps: int
    done_pct: float


# --- Внутренние хелперы -----------------------------------------------------


_ALLOWED_STEP_STATUSES = {"pending", "in_progress", "done", "blocked"}
_ALLOWED_SESSION_STATUSES = {"pending", "in_progress", "completed", "blocked"}


def _parse_json_field(raw: Any, default: Any) -> Any:
    """
    Аккуратно раскодируем json/jsonb поле из БД (строка / dict / list).
    """
    if raw is None:
        return default

    if isinstance(raw, (dict, list)):
        return raw

    try:
        return json.loads(raw)
    except Exception:
        return default


def _compute_overall_status(steps: List[Dict[str, Any]]) -> str:
    """
    Вычисляем общий статус сессии на основе статусов шагов.

    Простая логика:
    - если есть blocked -> 'blocked'
    - elif все done -> 'completed'
    - elif есть in_progress -> 'in_progress'
    - иначе -> 'pending'
    """
    if not steps:
        return "pending"

    statuses = {str(s.get("status") or "").lower() for s in steps}

    if "blocked" in statuses:
        return "blocked"
    if statuses == {"done"}:
        return "completed"
    if "in_progress" in statuses:
        return "in_progress"
    return "pending"


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Endpoint обзора онбординга (витрина Overview) --------------------------


@router.get(
    "/sessions/overview",
    response_model=List[OnboardingSessionOverview],
    summary="Обзор прогресса по онбордингу",
)
def get_onboarding_sessions_overview(
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Максимальное количество строк в ответе",
    ),
    status: Optional[str] = Query(
        None,
        description="Фильтр по статусу сессии: pending | in_progress | completed | blocked",
    ),
    only_blocked: bool = Query(
        False,
        description="Если true — только сессии, где есть заблокированные шаги",
    ),
) -> List[OnboardingSessionOverview]:
    """
    Возвращает агрегированный список онбординг-сессий из
    crm.onboarding_sessions_overview_v.
    """
    if status and status not in _ALLOWED_SESSION_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid session status {status!r}; "
                f"allowed: {sorted(_ALLOWED_SESSION_STATUSES)}"
            ),
        )

    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    onboarding_id,
                    account_id,
                    status,
                    created_at,
                    updated_at,
                    total_steps,
                    done_steps,
                    in_progress_steps,
                    blocked_steps,
                    has_blocked,
                    open_steps,
                    done_pct
                FROM crm.onboarding_sessions_overview_v
            """
            conditions: List[str] = []
            params: List[Any] = []

            if status:
                conditions.append("status = %s")
                params.append(status)

            if only_blocked:
                conditions.append("has_blocked = true")

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            sql += " ORDER BY onboarding_id DESC LIMIT %s"
            params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        try:
            conn.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=(
                "DB error while reading crm.onboarding_sessions_overview_v: "
                f"{exc}"
            ),
        )

    try:
        conn.close()
    except Exception:
        pass

    result: List[OnboardingSessionOverview] = []
    for row in rows:
        result.append(
            OnboardingSessionOverview(
                onboarding_id=int(row[0]),
                account_id=int(row[1]),
                status=str(row[2]),
                created_at=row[3],
                updated_at=row[4],
                total_steps=int(row[5]),
                done_steps=int(row[6]),
                in_progress_steps=int(row[7]),
                blocked_steps=int(row[8]),
                has_blocked=bool(row[9]),
                open_steps=int(row[10]),
                done_pct=float(row[11]),
            )
        )

    return result


# --- Endpoints: сессии и шаги ----------------------------------------------


@router.get(
    "/sessions/{session_id}",
    response_model=OnboardingSession,
    summary="Получить сессию онбординга по id",
)
def get_onboarding_session(session_id: int) -> OnboardingSession:
    """
    Возвращает crm.onboarding_sessions с декодированным steps и summary.
    """
    conn = _connect_pg()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    created_at,
                    updated_at,
                    account_id,
                    status,
                    steps,
                    summary
                FROM crm.onboarding_sessions
                WHERE id = %s
                """,
                (session_id,),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        try:
            conn.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"DB error while loading onboarding_session {session_id}: {exc}",
        )

    try:
        conn.close()
    except Exception:
        pass

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Onboarding session {session_id} not found",
        )

    (
        sid,
        created_at,
        updated_at,
        account_id,
        status,
        steps_raw,
        summary_raw,
    ) = row

    steps_list = _parse_json_field(steps_raw, default=[])
    summary = _parse_json_field(summary_raw, default={})

    steps_models: List[OnboardingStep] = []
    if isinstance(steps_list, list):
        for item in steps_list:
            if isinstance(item, dict):
                try:
                    steps_models.append(OnboardingStep(**item))
                except Exception:
                    continue

    return OnboardingSession(
        id=int(sid),
        created_at=created_at,
        updated_at=updated_at,
        account_id=int(account_id),
        status=str(status),
        steps=steps_models,
        summary=dict(summary),
    )


@router.post(
    "/sessions/{session_id}/steps/{step_code}/set-status",
    response_model=OnboardingSession,
    summary="Обновить статус конкретного шага онбординга",
)
def set_onboarding_step_status(
    session_id: int,
    step_code: str,
    body: OnboardingStepUpdateRequest,
) -> OnboardingSession:
    """
    Обновляет статус шага с указанным step_code в steps JSONB
    и пересчитывает общий статус сессии.
    """
    new_status = body.status.strip().lower()
    if new_status not in _ALLOWED_STEP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid step status {new_status!r}; "
                f"allowed: {sorted(_ALLOWED_STEP_STATUSES)}"
            ),
        )

    step_code_input = step_code.strip()
    step_code_norm = step_code_input.lower()

    conn = _connect_pg()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    created_at,
                    updated_at,
                    account_id,
                    status,
                    steps,
                    summary
                FROM crm.onboarding_sessions
                WHERE id = %s
                FOR UPDATE
                """,
                (session_id,),
            )
            row = cur.fetchone()

            if not row:
                conn.rollback()
                raise HTTPException(
                    status_code=404,
                    detail=f"Onboarding session {session_id} not found",
                )

            (
                sid,
                created_at,
                updated_at,
                account_id,
                status,
                steps_raw,
                summary_raw,
            ) = row

            steps_list = _parse_json_field(steps_raw, default=[])
            summary = _parse_json_field(summary_raw, default={})

            if not isinstance(steps_list, list):
                steps_list = []

            found = False
            now_iso = _now_iso_utc()

            new_steps: List[Dict[str, Any]] = []
            for item in steps_list:
                if not isinstance(item, dict):
                    new_steps.append(item)
                    continue

                scode = str(item.get("step_code") or "").strip()
                scode_norm = scode.lower()

                if scode_norm == step_code_norm:
                    found = True
                    new_item = dict(item)
                    new_item["status"] = new_status
                    new_item["updated_at"] = now_iso
                    if body.comment:
                        new_item["comment"] = body.comment
                    new_steps.append(new_item)
                else:
                    new_steps.append(item)

            if not found:
                conn.rollback()
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Step {step_code_input!r} not found in onboarding session {session_id}"
                    ),
                )

            overall_status = _compute_overall_status(new_steps)

            cur.execute(
                """
                UPDATE crm.onboarding_sessions
                SET
                    status     = %s,
                    steps      = %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                RETURNING updated_at;
                """,
                (
                    overall_status,
                    json.dumps(new_steps, ensure_ascii=False),
                    sid,
                ),
            )
            row2 = cur.fetchone()
            if row2:
                updated_at_new = row2[0]
            else:
                updated_at_new = updated_at

        conn.commit()
    except HTTPException:
        try:
            conn.close()
        except Exception:
            pass
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=(
                "DB error while updating onboarding step "
                f"{step_code_input!r} in session {session_id}: {exc}"
            ),
        )
    else:
        try:
            conn.close()
        except Exception:
            pass

    steps_models: List[OnboardingStep] = []
    for item in new_steps:
        if isinstance(item, dict):
            try:
                steps_models.append(OnboardingStep(**item))
            except Exception:
                continue

    return OnboardingSession(
        id=int(sid),
        created_at=created_at,
        updated_at=updated_at_new,
        account_id=int(account_id),
        status=overall_status,
        steps=steps_models,
        summary=dict(summary),
    )
