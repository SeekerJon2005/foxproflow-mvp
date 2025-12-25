-- 20251206_logistics_pilot_kpi_v1.sql
-- stack=sql
-- project_ref=logistics-pilot-001
-- goal=Пилот логистики 5–15 ТС: базовые KPI-витрины по задачам DevFactory проекта logistics-pilot-001.
-- summary=Создаёт схему analytics (если нет) и две витрины: список задач пилота и агрегаты по дням.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'analytics'
    ) THEN
        EXECUTE 'CREATE SCHEMA analytics';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE VIEW analytics.logistics_pilot_tasks_v1 AS
SELECT
    t.id,
    t.created_at,
    t.status,
    t.source,
    t.stack,
    t.title,
    t.input_spec->>'project_ref'          AS project_ref,
    (t.input_spec->>'priority')::int      AS priority,
    (t.input_spec->>'value_score')::int   AS value_score
FROM dev.dev_task AS t
WHERE t.input_spec->>'project_ref' = 'logistics-pilot-001';

CREATE OR REPLACE VIEW analytics.logistics_pilot_tasks_day_kpi_v1 AS
SELECT
    (t.created_at AT TIME ZONE 'UTC')::date AS day_utc,
    t.input_spec->>'project_ref'            AS project_ref,
    COUNT(*)                                AS tasks_total,
    COUNT(*) FILTER (WHERE t.status = 'new')          AS tasks_new,
    COUNT(*) FILTER (WHERE t.status = 'in_progress')  AS tasks_in_progress,
    COUNT(*) FILTER (WHERE t.status = 'done')         AS tasks_done,
    COUNT(*) FILTER (WHERE t.status = 'failed')       AS tasks_failed,
    SUM( (t.input_spec->>'value_score')::int )        AS value_score_sum
FROM dev.dev_task AS t
WHERE t.input_spec->>'project_ref' = 'logistics-pilot-001'
GROUP BY
    day_utc,
    project_ref
ORDER BY
    day_utc DESC;
