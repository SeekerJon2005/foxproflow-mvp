# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Path
import os

# ВАЖНО: изменён префикс и тег, чтобы убрать дубликаты маршрутов с актуальными автоплан-роутерами.
router = APIRouter(prefix="/api/autoplan_legacy", tags=["autoplan-legacy"])

def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd  = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    try:
        import psycopg  # type: ignore
        return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(_db_dsn())

@router.post("/run")
def run_pipeline(limit: int = 10):
    """
    Наследный запуск конвейера автоплана.
    Сохранён для обратной совместимости, но переведён под префикс /api/autoplan_legacy.
    """
    try:
        from src.worker.celery_app import celery as app
        ids = {
            "audit":   app.send_task("planner.autoplan.audit").id,
            "apply":   app.send_task("planner.autoplan.apply", kwargs={"limit": limit}).id,
            "push":    app.send_task("planner.autoplan.push_to_trips", kwargs={"limit": limit}).id,
            "confirm": app.send_task("planner.autoplan.confirm", kwargs={'limit': limit}).id,
        }
        return {"ok": True, "enqueued": ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"autoplan_run_failed: {e!r}")

@router.post("/trips/{trip_id}/revert")
def revert_trip(trip_id: str = Path(...), reason: str | None = None):
    """
    Переводит поездку в статус draft (наследный способ).
    """
    sql = "UPDATE public.trips SET status='draft', confirmed_at=NULL WHERE id=%s"
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute(sql, (trip_id,))
        conn.commit()
        return {"ok": True, "trip_id": trip_id, "reverted": True, "reason": reason}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"revert_failed: {e!r}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
