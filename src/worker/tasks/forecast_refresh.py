# -*- coding: utf-8 -*-
from __future__ import annotations

import os, asyncio
try:
    import asyncpg  # type: ignore
except Exception:
    asyncpg = None

def _dsn() -> str:
    return (os.getenv("DATABASE_URL")
            or f"postgresql://{os.getenv('POSTGRES_USER','admin')}:{os.getenv('POSTGRES_PASSWORD','admin')}"
               f"@{os.getenv('POSTGRES_HOST','postgres')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','foxproflow')}")

def _sql_refresh_stmt(mv: str) -> str:
    return f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv};"

async def _refresh_all():
    conn = await asyncpg.connect(_dsn())
    try:
        for mv in ("public.od_arrival_stats_mv","public.od_price_quantiles_mv","public.market_rates_mv"):
            try:
                await conn.execute(_sql_refresh_stmt(mv))
            except Exception:
                await conn.execute(f"REFRESH MATERIALIZED VIEW {mv};")
    finally:
        await conn.close()

def run_refresh_now() -> dict:
    if asyncpg is None:
        return {"ok": False, "error": "asyncpg_not_available"}
    asyncio.run(_refresh_all())
    return {"ok": True}

# интеграция с celery (импортируется из register_tasks)
def task_forecast_refresh() -> dict:
    return run_refresh_now()
