from __future__ import annotations

import os
from typing import Any, Optional, Sequence, AsyncIterator

import asyncpg

# Берём строку подключения из .env
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Лучше уронить сервис сразу, чем ловить непонятные ошибки позже
    raise RuntimeError("DATABASE_URL is not set in environment")

_pool: Optional[asyncpg.Pool] = None


class DbConn:
    """
    Тонкая обёртка над asyncpg.Connection с единым интерфейсом:
      - fetch_all(query, *args)
      - fetch_one(query, *args)
      - execute(query, *args)
    Под наши SQL с плейсхолдерами $1, $2, ...
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def fetch_all(self, query: str, *args: Any) -> Sequence[asyncpg.Record]:
        return await self._conn.fetch(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        return await self._conn.fetchrow(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(query, *args)


async def _get_pool() -> asyncpg.Pool:
    """
    Ленивая инициализация пула соединений. Первый вызов — создаёт pool,
    дальше переиспользуем.
    """
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
        )
    return _pool


async def get_db() -> AsyncIterator[DbConn]:
    """
    Зависимость FastAPI: выдаёт DbConn и корректно возвращает соединение в пул.

    Использование в роутерах:
        async def handler(..., db: DbConn = Depends(get_db)):
            rows = await db.fetch_all("SELECT ... WHERE id = $1", some_id)
    """
    pool = await _get_pool()
    conn = await pool.acquire()
    try:
        yield DbConn(conn)
    finally:
        await pool.release(conn)
