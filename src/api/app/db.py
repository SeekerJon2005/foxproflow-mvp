# src/api/app/db.py
import os
import asyncpg
from dotenv import load_dotenv
from pathlib import Path

# Загружаем .env.local, если он есть (для локального запуска uvicorn на Windows)
# иначе — .env (для Docker и общего окружения)
if Path(".env.local").exists():
    load_dotenv(dotenv_path=Path(".env.local"))
else:
    load_dotenv(dotenv_path=Path(".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Глобальный пул подключений
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    """Создаёт и кэширует пул подключений asyncpg"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
    return _pool

async def fetch_all(sql: str, params: tuple = ()):
    """Выполнить SELECT и вернуть список dict"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

async def fetch_one(sql: str, params: tuple = ()):
    """Выполнить SELECT и вернуть одну строку dict или None"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, *params)
        return dict(row) if row else None

async def execute(sql: str, params: tuple = ()):
    """Выполнить запрос без возврата (INSERT/UPDATE/DELETE)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql, *params)
