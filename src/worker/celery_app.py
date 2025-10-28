# src/worker/celery_app.py
from __future__ import annotations

import os
import logging
from datetime import date
from pathlib import Path

from celery import Celery

# ---------------------------------------------------------------------
# Загрузка переменных окружения: .env.local (локальный запуск) или .env (docker)
# ---------------------------------------------------------------------
try:
    from dotenv import load_dotenv  # type: ignore

    env_path = Path(".").joinpath(".env.local")
    if not env_path.exists():
        env_path = Path(".").joinpath(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except Exception:
    # dotenv опционален; если не установлен — просто пропускаем
    pass

# ---------------------------------------------------------------------
# Конфигурация брокера Celery (Redis) и Postgres
# ---------------------------------------------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:6379/{REDIS_DB}"
else:
    # допустим и пустой пароль
    REDIS_URL = f"redis://{REDIS_HOST}:6379/{REDIS_DB}"

# Строка подключения к Postgres: сначала берём DATABASE_URL,
# иначе собираем из POSTGRES_* (для docker по умолчанию host=postgres).
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "password")
    pg_host = os.getenv("POSTGRES_HOST", "postgres")  # локально можно поставить localhost
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "foxproflow")
    DATABASE_URL = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

# Инициализация приложения Celery
celery = Celery("foxproflow", broker=REDIS_URL, backend=REDIS_URL)

# ---------------------------------------------------------------------
# Вспомогательная функция подключения к БД с fallback на psycopg2
# ---------------------------------------------------------------------
def _connect_pg():
    """
    Возвращает соединение с Postgres.
    Сначала пытается psycopg (v3), затем psycopg2 (v2).
    """
    try:
        import psycopg  # psycopg 3
        return psycopg.connect(DATABASE_URL)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(DATABASE_URL)

# ---------------------------------------------------------------------
# Вспомогательная функция: безопасный REFRESH MV (с CONCURRENTLY + fallback)
# ---------------------------------------------------------------------
def _refresh_mv_safely(mv_name: str):
    """
    Пытается сделать REFRESH MATERIALIZED VIEW CONCURRENTLY <mv_name>.
    Если БД не позволяет CONCURRENTLY (нет уникального индекса/локи/ограничения),
    выполняет REFRESH без CONCURRENTLY как безопасный fallback.

    Возвращает dict с признаком concurrent/fallback.
    """
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        # Для CONCURRENTLY требуется autocommit=True (операция вне транзакции)
        fallback_error = None
        try:
            try:
                # psycopg2/psycopg3 оба поддерживают атрибут autocommit
                conn.autocommit = True  # type: ignore[attr-defined]
            except Exception:
                pass
            cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name};")
            return {"ok": True, "mv": mv_name, "concurrently": True}
        except Exception as e:
            # Переходим на обычный REFRESH (в транзакции)
            fallback_error = str(e)
            try:
                # выключим autocommit, если включен
                if getattr(conn, "autocommit", False):
                    conn.autocommit = False  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                conn.rollback()
            except Exception:
                pass
            cur.execute(f"REFRESH MATERIALIZED VIEW {mv_name};")
            conn.commit()
            return {
                "ok": True,
                "mv": mv_name,
                "concurrently": False,
                "fallback_reason": fallback_error,
            }
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ---------------------------------------------------------------------
# TASK: Ежедневный ETL макропоказателей в таблицу public.macro_data
# ---------------------------------------------------------------------
@celery.task(name="etl.macro_data.daily")
def etl_macro_data_daily():
    """
    Ежедневный апсерт макропоказателей.
    Источник по умолчанию — переменные окружения (USD_RATE, EUR_RATE, FUEL_PRICE_AVG, MACRO_SOURCE).
    При необходимости легко заменить на вызов внешнего API.
    """
    usd = float(os.getenv("USD_RATE", "92.5000"))       # под NUMERIC(10,4)
    eur = float(os.getenv("EUR_RATE", "98.3000"))       # под NUMERIC(10,4)
    fuel = float(os.getenv("FUEL_PRICE_AVG", "60.00"))  # под NUMERIC(10,2)
    src  = os.getenv("MACRO_SOURCE", "env/manual")
    today = date.today()

    conn = _connect_pg()
    try:
        cur = conn.cursor()
        # upsert по уникальному ключу (date)
        cur.execute(
            """
            INSERT INTO macro_data(date, usd_rate, eur_rate, fuel_price_avg, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE
            SET usd_rate       = EXCLUDED.usd_rate,
                eur_rate       = EXCLUDED.eur_rate,
                fuel_price_avg = EXCLUDED.fuel_price_avg,
                source         = EXCLUDED.source,
                updated_at     = now();
            """,
            (today, usd, eur, fuel, src),
        )
        conn.commit()
        return {"ok": True, "date": str(today), "usd": usd, "eur": eur, "fuel": fuel, "source": src}
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ---------------------------------------------------------------------
# TASK: REFRESH materialized view со ставками (таск оставляем; в beat не планируем)
# ---------------------------------------------------------------------
@celery.task(name="mv.refresh.market_rates")
def refresh_market_rates():
    """
    Обновление агрегатов ставок:
      REFRESH MATERIALIZED VIEW [CONCURRENTLY] market_rates_mv;
    """
    try:
        return _refresh_mv_safely("market_rates_mv")
    except Exception as e:
        logging.getLogger(__name__).warning("market_rates_mv refresh skipped: %s", e)
        return {"ok": True, "skipped": True, "reason": str(e)}

# (опционально) совместимость для старого имени
@celery.task(name="mv.refresh.freights_enriched")
def refresh_freights_enriched():
    """
    На случай, если где-то остались вызовы старого таска.
    Безопасно пропускаем, если такого MV нет.
    """
    try:
        return _refresh_mv_safely("freights_enriched_mv")
    except Exception as e:
        logging.getLogger(__name__).warning("freights_enriched_mv refresh skipped: %s", e)
        return {"ok": True, "skipped": True, "reason": str(e)}

# ---------------------------------------------------------------------
# NEW TASK: Hourly REFRESH vehicle_availability_mv (конкурентный)
# ---------------------------------------------------------------------
@celery.task(name="mv.refresh.vehicle_availability")
def mv_refresh_vehicle_availability():
    """
    Обновляет доступность ТС:
      REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv;

    Требования для CONCURRENTLY:
      - уникальный индекс на vehicle_availability_mv(truck_id).
    При ошибке выполняется безопасный fallback без CONCURRENTLY.
    """
    return _refresh_mv_safely("public.vehicle_availability_mv")

# --- Регистрация внешних тасков FoxProFlow ---
from src.worker.register_tasks import (
    task_planner_nextload_search,
    task_planner_hourly_replan_all,
    task_forecast_refresh,
)

# Регистрируем публичные имена задач (как было в проекте)
celery.task(name="planner.nextload.search")(task_planner_nextload_search)
celery.task(name="planner.hourly.replan.all")(task_planner_hourly_replan_all)
celery.task(name="forecast.refresh")(task_forecast_refresh)

# ---------------------------------------------------------------------
# Расписание Celery Beat: единый источник правды — services/schedule.py
# ---------------------------------------------------------------------
from src.services.schedule import BEAT_SCHEDULE
celery.conf.beat_schedule = BEAT_SCHEDULE

# Часовой пояс для beat. Можно переопределить ENV CELERY_TIMEZONE.
celery.conf.timezone = os.getenv("CELERY_TIMEZONE", "UTC")
