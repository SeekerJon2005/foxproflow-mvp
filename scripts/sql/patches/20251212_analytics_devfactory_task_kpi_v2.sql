-- 2025-12-12
-- FoxProFlow • Patch • Analytics
-- file: scripts/sql/patches/20251212_analytics_devfactory_task_kpi_v2.sql
--
-- DevFactory KPI v2: витрина analytics.devfactory_task_kpi_v2 (на основе dev.dev_task)
--
-- IMPORTANT:
--   This patch is DDL-only. It intentionally DOES NOT run REFRESH (especially not CONCURRENTLY).
--   On a fresh DB the MV is created unpopulated (WITH NO DATA), and Postgres forbids
--   REFRESH ... CONCURRENTLY until the MV has been populated at least once.
--   First populate must be done by bootstrap:
--     REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
--   Then a UNIQUE non-partial index can be created for future CONCURRENT refreshes.

CREATE SCHEMA IF NOT EXISTS analytics;

-- Старую версию (если была) аккуратно дропаем.
-- Индексы на MV будут пересозданы отдельным fixpack’ом (unique index).
DROP MATERIALIZED VIEW IF EXISTS analytics.devfactory_task_kpi_v2;

CREATE MATERIALIZED VIEW analytics.devfactory_task_kpi_v2 AS
WITH base AS (
    SELECT
        -- На первом шаге можно держать project_ref как meta->>'project_ref' с fallback.
        COALESCE(t.meta->>'project_ref', 'foxproflow-core') AS project_ref,
        t.stack::text                                      AS stack,
        t.status::text                                     AS status,
        t.created_at,
        t.updated_at
    FROM dev.dev_task t
)
SELECT
    project_ref,
    stack,
    COUNT(*)                                           AS total_tasks,
    COUNT(*) FILTER (WHERE status = 'new')             AS new_tasks,
    COUNT(*) FILTER (WHERE status = 'done')            AS done_tasks,
    COUNT(*) FILTER (WHERE status = 'failed')          AS failed_tasks,
    MAX(created_at)                                    AS last_created_at,
    MAX(updated_at)                                    AS last_updated_at,
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at)))
        FILTER (WHERE status = 'done')                 AS avg_duration_sec
FROM base
GROUP BY project_ref, stack
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW analytics.devfactory_task_kpi_v2 IS
'DevFactory KPI v2: агрегаты по задачам dev.dev_task (group by project_ref, stack). DDL-only here; first REFRESH is done by bootstrap without CONCURRENTLY.';

COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.project_ref IS 'Project reference (meta->>project_ref or fallback)';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.stack IS 'Stack/domain of task';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.total_tasks IS 'Total tasks count';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.new_tasks IS 'Count where status=new';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.done_tasks IS 'Count where status=done';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.failed_tasks IS 'Count where status=failed';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.last_created_at IS 'Max created_at in group';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.last_updated_at IS 'Max updated_at in group';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.avg_duration_sec IS 'Avg duration (sec) for done tasks';

-- NO REFRESH HERE (handled by bootstrap / fixpacks).
