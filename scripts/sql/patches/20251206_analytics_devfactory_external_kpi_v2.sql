-- 20251206_analytics_devfactory_external_kpi_v2.sql
-- stack=sql
-- goal=Создать KPI-вьюху для задач DevFactory во внешних проектах под реальную схему dev.dev_task.
-- summary=Создаёт analytics.devfactory_external_task_kpi_v1 с project_ref из JSON/источника и lead time по updated_at - created_at.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.devfactory_external_task_kpi_v1 AS
SELECT
    -- Пытаемся извлечь "проект" из JSON и source, с fallback в 'global'
    COALESCE(
        NULLIF(input_spec ->> 'project_ref',   ''),
        NULLIF(input_spec ->> 'project_code',  ''),
        NULLIF(input_spec ->> 'tenant_code',   ''),
        NULLIF(links      ->> 'project_ref',   ''),
        NULLIF(links      ->> 'project_code',  ''),
        NULLIF(source,                             ''),
        'global'
    )                               AS project_ref,
    created_at::date                AS task_date,
    COUNT(*)                        AS tasks_total,
    COUNT(*) FILTER (
        WHERE status IN ('done', 'success', 'succeeded')
    )                               AS tasks_done,
    COUNT(*) FILTER (
        WHERE status IN ('failed', 'error')
    )                               AS tasks_failed,
    AVG(updated_at - created_at)    AS avg_lead_time
FROM dev.dev_task
GROUP BY
    project_ref,
    created_at::date;
