# -*- coding: utf-8 -*-
"""
FlowSec middleware (B-dev)
file: src/api/security/flowsec_middleware.py

Fixes:
- Unicode-safe constant-time key compare (_ct_eq): avoids TypeError from hmac.compare_digest(str,str) on non-ASCII.
- Fail-closed, no "500-magic": policy errors => 403, dependency/db issues => 503 with clear next steps.
- Works both via FastAPI DI and when dependency is called manually (DependsMarker).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, List, Optional, Protocol, Sequence

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.params import Depends as DependsMarker
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

# Если есть T9 envelope — используем (предпочтительно)
try:
    from src.api.error_envelope import FoxError  # type: ignore
except Exception:  # pragma: no cover
    FoxError = None  # type: ignore


def _raise_policy_deny(*, message_ru: str, why_ru: str, next_step_ru: str, details: Optional[dict] = None) -> None:
    if FoxError is not None:
        raise FoxError.policy_deny(
            message_ru=message_ru,
            why_ru=why_ru,
            next_step_ru=next_step_ru,
            details=details,
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "ok": False,
            "error": {
                "kind": "policy",
                "message_ru": message_ru,
                "why_ru": why_ru,
                "next_step_ru": next_step_ru,
                "details": details or {},
            },
            "status_code": 403,
        },
    )


def _raise_dependency_unavailable(
    *,
    message_ru: str,
    why_ru: str,
    next_step_ru: str,
    details: Optional[dict] = None,
    status_code: int = 503,
) -> None:
    if FoxError is not None:
        raise FoxError.dependency_unavailable(
            message_ru=message_ru,
            why_ru=why_ru,
            next_step_ru=next_step_ru,
            details=details,
            status_code=status_code,
        )
    raise HTTPException(
        status_code=status_code,
        detail={
            "ok": False,
            "error": {
                "kind": "dependency",
                "message_ru": message_ru,
                "why_ru": why_ru,
                "next_step_ru": next_step_ru,
                "details": details or {},
            },
            "status_code": status_code,
        },
    )


# ---------------------------------------------------------------------------
# DB helper: asyncpg pool for FlowSec
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin@postgres:5432/foxproflow")
_pool: Optional[asyncpg.Pool] = None


class DbConnProtocol(Protocol):
    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]: ...
    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]: ...
    async def execute(self, query: str, *args: Any) -> str: ...


class DbConn(DbConnProtocol):
    """Обёртка над asyncpg.Connection для FlowSec."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]:
        return await self._conn.fetch(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        return await self._conn.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


async def _get_pool() -> asyncpg.Pool:
    """
    Lazy pool init. Must not turn into 500 -> only 503 with actionable message.
    """
    global _pool
    if _pool is not None:
        return _pool

    if not (DATABASE_URL or "").strip():
        _raise_dependency_unavailable(
            message_ru="FlowSec БД недоступна.",
            why_ru="DATABASE_URL не задан для FlowSec middleware.",
            next_step_ru="Задай DATABASE_URL внутри api контейнера и перезапусти сервис.",
        )

    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=_env_int("FF_FLOWSEC_POOL_MIN", 1),
            max_size=_env_int("FF_FLOWSEC_POOL_MAX", 10),
            command_timeout=_env_int("FF_FLOWSEC_CMD_TIMEOUT_S", 10),
        )
        return _pool
    except Exception as ex:
        log.exception("FlowSec pool init failed: %r", ex)
        _raise_dependency_unavailable(
            message_ru="FlowSec БД недоступна.",
            why_ru="Не удалось создать пул соединений asyncpg.",
            next_step_ru="Проверь доступность Postgres и корректность DATABASE_URL, затем повтори.",
            details={"error": f"{type(ex).__name__}: {ex}"},
        )
        raise  # pragma: no cover


async def get_db_conn() -> AsyncIterator[DbConnProtocol]:
    pool = await _get_pool()
    try:
        conn = await pool.acquire()
    except Exception as ex:
        log.exception("FlowSec pool acquire failed: %r", ex)
        _raise_dependency_unavailable(
            message_ru="FlowSec БД недоступна.",
            why_ru="Не удалось получить соединение из пула FlowSec.",
            next_step_ru="Проверь Postgres/сеть docker и повтори.",
            details={"error": f"{type(ex).__name__}: {ex}"},
        )
        raise  # pragma: no cover

    try:
        yield DbConn(conn)
    finally:
        try:
            await pool.release(conn)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FlowSec subject & bearer
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class FlowSecSubject:
    subject_type: str  # 'user' | 'service' | 'eri' | 'ai_agent'
    subject_id: str    # email, service-id, capsule-id и т.п.
    roles: List[str]


# ---------------------------------------------------------------------------
# Tokens / Architect Key
# ---------------------------------------------------------------------------

_DEFAULT_DEV_ARCHITECT_SUBJECT = "e.yatskov@foxproflow.ru"
_ARCH_HEADER = "X-FF-Architect-Key"
_DEV_ANTI_LOCKOUT = (os.getenv("FF_DEV_ANTI_LOCKOUT", "1") or "1").strip().lower() in ("1", "true", "yes", "on")


def _strip_quotes_and_crlf(v: str) -> str:
    s = (v or "").strip().replace("\r", "").replace("\n", "")
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def _split_env_keys(raw: str) -> List[str]:
    raw = _strip_quotes_and_crlf(raw or "")
    if not raw:
        return []
    raw = raw.replace(";", ",")
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _normalize_presented_key(value: Optional[str]) -> str:
    if not value:
        return ""
    v = _strip_quotes_and_crlf(str(value))
    for prefix in ("Bearer ", "Token "):
        if v.startswith(prefix):
            v = v[len(prefix):].strip()
            break
    return v


def _ct_eq(a: str, b: str) -> bool:
    """
    IMPORTANT: hmac.compare_digest(str,str) is ASCII-only in Python -> TypeError on non-ASCII.
    Compare bytes instead (utf-8).
    """
    try:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except Exception:
        return False


def _extract_presented_key(request: Request, creds: Optional[HTTPAuthorizationCredentials]) -> str:
    v = _normalize_presented_key(request.headers.get(_ARCH_HEADER))
    if v:
        return v

    v = _normalize_presented_key(request.headers.get("Authorization"))
    if v:
        return v

    if creds is not None and getattr(creds, "credentials", None):
        return _normalize_presented_key(str(creds.credentials))

    return ""


def _is_valid_auth_token(token: str) -> bool:
    token = _strip_quotes_and_crlf(token or "")
    if not token:
        return False

    expected_list = _split_env_keys(os.getenv("FF_AUTH_TOKEN") or "")
    if not expected_list:
        return False

    for exp in expected_list:
        if _ct_eq(token, exp):
            return True
    return False


def _is_valid_architect_key_from_request(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = None,
) -> bool:
    """
    Architect override:
      - FF_ARCHITECT_KEY (list)
      - FF_ARCHITECT_KEY_SHA256 (list of sha256 hex)
    DEV:
      - if no keys configured and FF_DEV_ANTI_LOCKOUT=1 -> True (avoid lockout on stand)
    """
    try:
        expected_keys = _split_env_keys(os.getenv("FF_ARCHITECT_KEY") or "")
        expected_sha = [s.lower() for s in _split_env_keys(os.getenv("FF_ARCHITECT_KEY_SHA256") or "")]

        if not expected_keys and not expected_sha:
            return bool(_DEV_ANTI_LOCKOUT)

        presented = _extract_presented_key(request, creds)
        if not presented:
            return False

        for k in expected_keys:
            if _ct_eq(presented, k):
                return True

        if expected_sha:
            got = hashlib.sha256(presented.encode("utf-8")).hexdigest().lower()
            return got in set(expected_sha)

        return False
    except Exception as ex:
        log.warning("Architect key check failed (treat as invalid): %r", ex)
        return False


# ---------------------------------------------------------------------------
# Manual-call safety helpers for dependencies
# ---------------------------------------------------------------------------

def _is_depends_obj(v: Any) -> bool:
    return isinstance(v, DependsMarker)


async def _resolve_creds_if_needed(request: Request, creds: Any) -> Optional[HTTPAuthorizationCredentials]:
    if _is_depends_obj(creds):
        return await bearer_scheme(request)
    return creds  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Subject resolver
# ---------------------------------------------------------------------------

async def resolve_subject_from_request(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: DbConnProtocol = Depends(get_db_conn),
) -> FlowSecSubject:
    arch_ok = _is_valid_architect_key_from_request(request, creds)

    if creds is None:
        subject_type = "user"
        subject_id = _DEFAULT_DEV_ARCHITECT_SUBJECT
    else:
        token = _strip_quotes_and_crlf(creds.credentials or "")
        if _is_valid_auth_token(token) or arch_ok:
            subject_type = "user"
            subject_id = _DEFAULT_DEV_ARCHITECT_SUBJECT
        else:
            subject_type = "user"
            subject_id = token

    try:
        rows = await db.fetch_all(
            """
            SELECT r.role_code
            FROM sec.subject_roles sr
            JOIN sec.roles r
              ON r.role_code = sr.role_code
            WHERE sr.subject_type = $1
              AND sr.subject_id   = $2
            """,
            subject_type,
            subject_id,
        )
    except HTTPException:
        raise
    except Exception as ex:
        log.exception("FlowSec roles lookup failed: %r", ex)
        _raise_dependency_unavailable(
            message_ru="FlowSec недоступен.",
            why_ru="Не удалось загрузить роли субъекта из sec.subject_roles/sec.roles.",
            next_step_ru="Проверь миграции FlowSec (sec.*) и доступность Postgres.",
            details={"error": f"{type(ex).__name__}: {ex}", "subject_type": subject_type, "subject_id": subject_id},
        )
        raise  # pragma: no cover

    roles = [row["role_code"] for row in rows]
    return FlowSecSubject(subject_type=subject_type, subject_id=subject_id, roles=roles)


# ---------------------------------------------------------------------------
# Policy checks
# ---------------------------------------------------------------------------

async def check_policies_allowed(
    db: DbConnProtocol,
    subject: FlowSecSubject,
    domain: str,
    actions: Iterable[str],
) -> None:
    actions_list = list(actions)

    try:
        rows = await db.fetch_all(
            """
            SELECT
                p.policy_code,
                p.effect,
                p.decision
            FROM sec.subject_roles sr
            JOIN sec.role_policy_bindings b
              ON b.role_code = sr.role_code
            JOIN sec.policies p
              ON p.policy_code = b.policy_code
            WHERE sr.subject_type = $1
              AND sr.subject_id   = $2
              AND p.is_active     = TRUE
              AND p.target_domain = $3
              AND (p.domain = $3 OR p.domain IS NULL)
              AND p.action        = ANY($4::text[])
            """,
            subject.subject_type,
            subject.subject_id,
            domain,
            actions_list,
        )
    except HTTPException:
        raise
    except Exception as ex:
        log.exception("FlowSec policy query failed: %r", ex)
        _raise_dependency_unavailable(
            message_ru="FlowSec недоступен.",
            why_ru="Не удалось выполнить запрос политик (sec.*).",
            next_step_ru="Проверь миграции FlowSec (sec.*) и доступность Postgres.",
            details={"error": f"{type(ex).__name__}: {ex}", "domain": domain, "actions": actions_list},
        )
        raise  # pragma: no cover

    has_allow = any((row["effect"] == "allow") or (row["decision"] == "allow") for row in rows)

    if not has_allow:
        _raise_policy_deny(
            message_ru="Доступ запрещён (FlowSec).",
            why_ru=f"FlowSec: access denied for domain={domain}, actions={actions_list}",
            next_step_ru="Назначь роль/политику в FlowSec (sec.*) или используй ключ Архитектора (если разрешено).",
            details={"domain": domain, "actions": actions_list, "subject_id": subject.subject_id},
        )


def require_policies(domain: str, actions: Sequence[str]):
    async def _dependency(
        request: Request,
        subject: Any = Depends(resolve_subject_from_request),
        db: Any = Depends(get_db_conn),
        creds: Any = Depends(bearer_scheme),
    ) -> None:
        real_creds = await _resolve_creds_if_needed(request, creds)

        async def _run_with(db_conn: DbConnProtocol, subj: FlowSecSubject) -> None:
            try:
                await check_policies_allowed(db=db_conn, subject=subj, domain=domain, actions=actions)
            except Exception as e:
                sc = getattr(e, "status_code", None)
                if (
                    sc == status.HTTP_403_FORBIDDEN
                    and domain == "devfactory"
                    and ("manage_tasks" in set(actions))
                    and _is_valid_architect_key_from_request(request, real_creds)
                ):
                    return
                raise

        if _is_depends_obj(db):
            agen = get_db_conn()
            try:
                db_conn = await agen.__anext__()
                if _is_depends_obj(subject):
                    subj = await resolve_subject_from_request(request=request, creds=real_creds, db=db_conn)
                else:
                    subj = subject  # type: ignore[assignment]
                await _run_with(db_conn, subj)
            finally:
                await agen.aclose()
            return

        db_conn = db  # type: ignore[assignment]
        if _is_depends_obj(subject):
            subj = await resolve_subject_from_request(request=request, creds=real_creds, db=db_conn)
        else:
            subj = subject  # type: ignore[assignment]

        await _run_with(db_conn, subj)

    return _dependency


# ---------------------------------------------------------------------------
# DevFactory write hook (used by src/api/main.py resolver)
# ---------------------------------------------------------------------------

async def require_devfactory_task_write(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    subject: FlowSecSubject = Depends(resolve_subject_from_request),
    db: DbConnProtocol = Depends(get_db_conn),
) -> bool:
    if _is_valid_architect_key_from_request(request, creds):
        return True
    await check_policies_allowed(db=db, subject=subject, domain="devfactory", actions=["manage_tasks"])
    return True


async def require_devfactory_write(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    subject: FlowSecSubject = Depends(resolve_subject_from_request),
    db: DbConnProtocol = Depends(get_db_conn),
) -> bool:
    return await require_devfactory_task_write(request, creds, subject, db)


async def require_devfactory_tasks_write(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    subject: FlowSecSubject = Depends(resolve_subject_from_request),
    db: DbConnProtocol = Depends(get_db_conn),
) -> bool:
    return await require_devfactory_task_write(request, creds, subject, db)
