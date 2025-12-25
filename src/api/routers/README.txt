FoxProFlow — src/api/routers
Дата сборки: 2025-11-03 23:17:19

Файлы из этого архива скопируй в:
C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\src\api\routers\

Состав:
- health.py — расширенный health чек Postgres/Redis (/health/extended)
- health_ex.py — облегчённая версия health
- autoplan.py — /api/autoplan/pipeline/recent
- autoplan_ops.py — /api/autoplan/run, /api/autoplan/trips/{trip_id}/revert
- pipeline_summary.py — /api/autoplan/pipeline/summary
- trips_confirm.py — подтверждение трипов /api/autoplan/trips/{trip_id}/confirm
- parsers_ingest.py — приём батчей /api/parsers/ingest/freights и /trucks
- __init__.py — пустой файл-пакет

Подключение в FastAPI (пример):
    from fastapi import FastAPI
    from src.api.routers import health, health_ex, autoplan, autoplan_ops, pipeline_summary, trips_confirm, parsers_ingest
    app = FastAPI()
    for r in (health.router, health_ex.router, autoplan.router, autoplan_ops.router, pipeline_summary.router, trips_confirm.router, parsers_ingest.router):
        app.include_router(r)

Требования окружения:
- DATABASE_URL или POSTGRES_* переменные
- REDIS_HOST/PORT/PASSWORD (если брокер с паролем)
- Для trips_confirm: CONFIRM_P_MIN, CONFIRM_RPM_MIN, CONFIRM_HORIZON_H, CONFIRM_FREEZE_H_BEFORE (опционально)
- Для parsers_ingest: Celery доступен по src.worker.celery_app (опционально)
