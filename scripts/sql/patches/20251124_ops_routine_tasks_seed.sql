-- 2025-11-24 — FoxProFlow
-- Первичное заполнение реестра рутинных задач ops.routine_tasks.
-- NDC: только INSERT ... ON CONFLICT DO UPDATE (без ALTER/DROP/DELETE).

INSERT INTO ops.routine_tasks (
    code,
    description,
    script_hint,
    frequency,
    manual_time_min,
    automated,
    notes
)
VALUES
    -- Суточный ETL ATI (парсинг, загрузка, обогащение)
    (
        'etl_ati_cycle',
        'Суточный цикл ETL по ATI: забрать новые грузы, загрузить в БД, обновить витрины freights_ati_ *.',
        'tools/ff-ati-daily-run.ps1',
        'daily',
        30,
        true,
        jsonb_build_object(
            'owner', 'Evgeniy',
            'agent_candidate', 'ETLFox',
            'comment', 'Запускается как часть ff-daily-orchestrator.'
        )
    ),
    -- GEO/OSRM refresh
    (
        'geo_osrm_refresh',
        'Обновление GEO/OSRM: геокодинг, расчёт маршрутов, заполнение road_km/drive_sec/polyline.',
        'tools/ff-geo-refresh-all.ps1',
        'daily',
        20,
        true,
        jsonb_build_object(
            'owner', 'Evgeniy',
            'agent_candidate', 'MVDoctor',
            'comment', 'Обеспечивает покрытие маршрутов по свежим рейсам.'
        )
    ),
    -- Ежедневный автоплан
    (
        'autoplan_daily_cycle',
        'Ежедневный запуск цепочки автоплана (msk_day/longhaul_night_prod и др.) по факту доступных фрахтов.',
        'tools/ff-autoplan-daily-cycle.ps1',
        'daily',
        15,
        true,
        jsonb_build_object(
            'owner', 'Evgeniy',
            'agent_candidate', 'AutoplanGuard',
            'comment', 'Входит в ff-daily-orchestrator; контролируется через автоплан-аудит.'
        )
    ),
    -- KPI + проверки маршрутов
    (
        'kpi_and_smoke',
        'Расчёт KPI автоплана и быстрые проверки маршрутов (routing smoke).',
        'tools/ff-autoplan-kpi.ps1, tools/ff-routing-smoke.ps1',
        'daily',
        10,
        true,
        jsonb_build_object(
            'owner', 'Evgeniy',
            'agent_candidate', 'LogFox',
            'comment', 'Финальный шаг боевого дня: проверка метрик и маршрутов.'
        )
    )
ON CONFLICT (code) DO UPDATE
SET
    description     = EXCLUDED.description,
    script_hint     = EXCLUDED.script_hint,
    frequency       = EXCLUDED.frequency,
    manual_time_min = EXCLUDED.manual_time_min,
    automated       = EXCLUDED.automated,
    notes           = COALESCE(ops.routine_tasks.notes, '{}'::jsonb) || EXCLUDED.notes,
    updated_at      = now();
