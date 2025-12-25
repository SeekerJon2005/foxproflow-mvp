from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, List, Optional, Protocol, Sequence

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ---------------------------------------------------------------------------
# DB helper: asyncpg-пул для FlowSec
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:admin@postgres:5432/foxproflow",
)

_pool: Optional[asyncpg.Pool] = None


class DbConnProtocol(Protocol):
    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]: ...
    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]: ...
    async def execute(self, query: str, *args: Any) -> str: ...


class DbConn(DbConnProtocol):
    """
    Обёртка над asyncpg.Connection для FlowSec.
    """
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]:
        return await self._conn.fetch(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        return await self._conn.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)


async def _get_pool() -> asyncpg.Pool:
    """
    Ленивая инициализация пула соединений для FlowSec.
    """
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set for FlowSec middleware")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
        )
    return _pool


async def get_db_conn() -> AsyncIterator[DbConnProtocol]:
    """
    Зависимость для FlowSec: выдаёт DbConn и корректно возвращает соединение в пул.
    """
    pool = await _get_pool()
    conn = await pool.acquire()
    try:
        yield DbConn(conn)
    finally:
        await pool.release(conn)


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
# Internal helpers: tokens/architect key
# ---------------------------------------------------------------------------

_DEFAULT_DEV_ARCHITECT_SUBJECT = "e.yatskov@foxproflow.ru"
_ARCH_HEADER = "X-FF-Architect-Key"


def _split_env_keys(raw: str) -> List[str]:
    """
    Поддержка ротации:
      FF_ARCHITECT_KEY="k1,k2;k3" -> принимаем любой из списка.
      FF_AUTH_TOKEN="t1,t2" -> аналогично.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    raw = raw.replace(";", ",")
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _normalize_presented_key(value: Optional[str]) -> str:
    """
    Нормализует заголовок:
      - trim
      - поддержка "Bearer <key>" / "Token <key>"
    """
    if not value:
        return ""
    v = str(value).strip()
    for prefix in ("Bearer ", "Token "):
        if v.startswith(prefix):
            v = v[len(prefix):].strip()
            break
    return v


def _extract_presented_key(request: Request, creds: Optional[HTTPAuthorizationCredentials]) -> str:
    """
    Где ищем предъявленный ключ:
      1) X-FF-Architect-Key
      2) Authorization (Bearer/Token)
      3) creds.credentials (FastAPI HTTPBearer)
    """
    v = _normalize_presented_key(request.headers.get(_ARCH_HEADER))
    if v:
        return v

    v = _normalize_presented_key(request.headers.get("Authorization"))
    if v:
        return v

    if creds is not None and getattr(creds, "credentials", None):
        return str(creds.credentials).strip()

    return ""


def _is_valid_auth_token(token: str) -> bool:
    """
    Внутренний auth token (не architect key). Поддерживаем ротацию.
    """
    expected_list = _split_env_keys(os.getenv("FF_AUTH_TOKEN") or "")
    if not expected_list or not token:
        return False
    for exp in expected_list:
        if hmac.compare_digest(token, exp):
            return True
    return False


def _is_valid_architect_key_from_request(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = None,
) -> bool:
    """
    Architect override включается ТОЛЬКО если:
      - в env задан FF_ARCHITECT_KEY (один или несколько ключей)
      - и запрос предъявил один из этих ключей (см. _extract_presented_key)

    ВАЖНО: если FF_ARCHITECT_KEY НЕ задан — override ВЫКЛЮЧЕН (False).
    """
    expected_keys = _split_env_keys(os.getenv("FF_ARCHITECT_KEY") or "")
    if not expected_keys:
        return False  # никаких silent-allow

    presented = _extract_presented_key(request, creds)
    if not presented:
        return False

    for k in expected_keys:
        if hmac.compare_digest(presented, k):
            return True
    return False


# ---------------------------------------------------------------------------
# Резолвим subject из HTTP-запроса
# ---------------------------------------------------------------------------

async def resolve_subject_from_request(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: DbConnProtocol = Depends(get_db_conn),
) -> FlowSecSubject:
    """
    DEV-поведение (локальный стенд):
      A) Если Bearer отсутствует -> считаем запрос от Архитектора
      B) Если Bearer присутствует:
         - FF_AUTH_TOKEN или FF_ARCHITECT_KEY -> маппим на Архитектора
         - иначе subject_id=<токен>
    """
    arch_ok = _is_valid_architect_key_from_request(request, creds)

    if creds is None:
        subject_type = "user"
        subject_id = _DEFAULT_DEV_ARCHITECT_SUBJECT
    else:
        token = (creds.credentials or "").strip()

        if _is_valid_auth_token(token) or arch_ok:
            subject_type = "user"
            subject_id = _DEFAULT_DEV_ARCHITECT_SUBJECT
        else:
            subject_type = "user"
            subject_id = token

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

    roles = [row["role_code"] for row in rows]

    return FlowSecSubject(
        subject_type=subject_type,
        subject_id=subject_id,
        roles=roles,
    )


# ---------------------------------------------------------------------------
# Проверка политик FlowSec
# ---------------------------------------------------------------------------

async def check_policies_allowed(
    db: DbConnProtocol,
    subject: FlowSecSubject,
    domain: str,
    actions: Iterable[str],
) -> None:
    actions_list = list(actions)

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

    has_allow = any(
        (row["effect"] == "allow") or (row["decision"] == "allow")
        for row in rows
    )

    if not has_allow:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"FlowSec: access denied for domain={domain}, actions={actions_list}",
        )


def require_policies(domain: str, actions: Sequence[str]):
    """
    Зависимость FastAPI для проверки FlowSec-политик на эндпоинтах.

    DEV/Bootstrap (явный opt-in):
      - для devfactory:view_* и devfactory:manage_* разрешаем override ТОЛЬКО при предъявлении FF_ARCHITECT_KEY.
      - override выключен, если FF_ARCHITECT_KEY не задан.
    """

    async def _dependency(
        request: Request,
        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
        subject: FlowSecSubject = Depends(resolve_subject_from_request),
        db: DbConnProtocol = Depends(get_db_conn),
    ) -> None:
        # Быстрый bypass ДО запроса в БД (иначе view_tasks блокирует bootstrap devorders)
        if domain == "devfactory":
            a = set(actions)
            if a.intersection({"view_tasks", "view_orders", "manage_tasks", "manage_orders"}) and _is_valid_architect_key_from_request(request, creds):
                return

        await check_policies_allowed(
            db=db,
            subject=subject,
            domain=domain,
            actions=actions,
        )
        return

    return _dependency
