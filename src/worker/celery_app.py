# src/worker/celery_app.py
from celery import Celery
from celery.schedules import crontab
import asyncpg
import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем .env.local, если он есть (для локального запуска uvicorn/worker),
# иначе — .env (для Docker-контейнеров)
env_path = Path(".env.local") if Path(".env.local").exists() else Path(".env")
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URL = f"redis://:{REDIS_PASSWORD}@redis:6379/0"

# Создаём приложение Celery
celery = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@celery.task
def refresh_mv():
    """
    Обновление materialized view freights_enriched_mv.
    Можно вызывать вручную (refresh_mv.delay()) или по расписанию через beat.
    """
    import asyncio

    async def _refresh():
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY freights_enriched_mv;"
            )
        finally:
            await conn.close()

    asyncio.run(_refresh())
    return "MV refreshed"


# ---------------------------
# Расписание для beat
# ---------------------------
celery.conf.beat_schedule = {
    "refresh-mv-every-5-minutes": {
        "task": "src.worker.celery_app.refresh_mv",
        "schedule": crontab(minute="*/5"),  # каждые 5 минут
    },
}

# Часовой пояс (UTC по умолчанию, можно заменить на "Europe/Moscow")
celery.conf.timezone = "UTC"
