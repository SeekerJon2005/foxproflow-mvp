-- 2025-12-12
-- DevFactory KPI v2: витрина analytics.devfactory_task_kpi_v2 (stub на основе dev.dev_task)

CREATE SCHEMA IF NOT EXISTS analytics;

-- Старую версию (если вдруг была) аккуратно дропаем
DROP MATERIALIZED VIEW IF EXISTS analytics.devfactory_task_kpi_v2;

CREATE MATERIALIZED VIEW analytics.devfactory_task_kpi_v2 AS
WITH base AS (
    SELECT
        -- На первом шаге можно забить project_ref константой.
        -- Позже сюда можно подставить t.meta->>'project_ref' или что-то из dev_order.
        COALESCE(t.meta->>'project_ref', 'foxproflow-core') AS project_ref,
        t.stack::text                                        AS stack,
        t.status::text                                       AS status,
        t.created_at,
        t.updated_at
    FROM dev.dev_task t
)
SELECT
    project_ref,
    stack,
    COUNT(*)                                           AS total_tasks,
    COUNT(*) FILTER (WHERE status = 'new')            AS new_tasks,
    COUNT(*) FILTER (WHERE status = 'done')           AS done_tasks,
    COUNT(*) FILTER (WHERE status = 'failed')         AS failed_tasks,
    MAX(created_at)                                   AS last_created_at,
    MAX(updated_at)                                   AS last_updated_at,
    AVG(
        EXTRACT(EPOCH FROM (updated_at - created_at))
    ) FILTER (WHERE status = 'done')                  AS avg_duration_sec
FROM base
GROUP BY project_ref, stack
WITH NO DATA;

-- Первичное наполнение витрины
REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.devfactory_task_kpi_v2;
