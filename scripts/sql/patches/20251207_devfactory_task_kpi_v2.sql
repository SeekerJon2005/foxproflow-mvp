-- 20251207_devfactory_task_kpi_v2.sql
-- NDC-патч: создаёт или обновляет VIEW analytics.devfactory_task_kpi_v2 (KPI задач DevFactory).
-- stack=sql
-- goal=DevFactory KPI: агрегировать dev.dev_task по project_ref/stack для Operator UI.
-- summary=DevFactory KPI v2: project_ref + stack, total/new/done/failed, last_created/updated, avg_duration_sec.

BEGIN;

-- На всякий случай убеждаемся, что схема существует
CREATE SCHEMA IF NOT EXISTS analytics;

-- Основная витрина KPI по задачам DevFactory
CREATE OR REPLACE VIEW analytics.devfactory_task_kpi_v2 AS
WITH base AS (
    SELECT
        COALESCE(
            links->>'project_ref',
            input_spec->>'project_ref',
            'unknown'
        )                           AS project_ref,
        stack                        AS stack,
        status                       AS status,
        created_at                   AS created_at,
        updated_at                   AS updated_at,
        EXTRACT(
            EPOCH FROM (updated_at - created_at)
        )                            AS duration_sec
    FROM dev.dev_task
),
agg AS (
    SELECT
        project_ref,
        stack,
        COUNT(*)                                             AS total_tasks,
        COUNT(*) FILTER (WHERE status = 'new')               AS new_tasks,
        COUNT(*) FILTER (WHERE status = 'done')              AS done_tasks,
        COUNT(*) FILTER (WHERE status = 'failed')            AS failed_tasks,
        MAX(created_at)                                      AS last_created_at,
        MAX(updated_at)                                      AS last_updated_at,
        AVG(duration_sec) FILTER (WHERE status = 'done')     AS avg_duration_sec
    FROM base
    GROUP BY project_ref, stack
)
SELECT
    project_ref,
    stack,
    total_tasks,
    new_tasks,
    done_tasks,
    failed_tasks,
    last_created_at,
    last_updated_at,
    avg_duration_sec
FROM agg;

COMMIT;
