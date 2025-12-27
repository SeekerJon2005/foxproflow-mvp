-- 20251212_analytics_flowmind_df3_logistics_progress_mv_v2.sql
-- DevTask: 97
-- Назначение: исправить витрину прогресса DF-3 + Logistics — считать задачи по meta.flowmind_plan_id/domain (канон), а не по title
-- Создал Архитектор: Яцков Евгений Анатольевич
-- Принцип: NDC (MV можно пересоздавать — производная витрина)

BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;

-- Пересоздаём MV (старая версия считала по title ILIKE '%DF-3 + Logistics%')
DROP MATERIALIZED VIEW IF EXISTS analytics.flowmind_df3_logistics_progress_mv;

CREATE MATERIALIZED VIEW analytics.flowmind_df3_logistics_progress_mv
AS
WITH plan_ref AS (
    SELECT
        '54236a99-7afc-45f9-bc2e-fe45d281ffe9'::uuid AS plan_id,
        'devfactory+logistics/3week'::text      AS plan_domain
),
plan_tasks AS (
    -- LEFT JOIN гарантирует 1 строку даже если задач 0
    SELECT
        p.plan_id,
        p.plan_domain,
        count(t.id) AS dev_tasks_total,
        count(t.id) FILTER (WHERE t.status = 'done')        AS dev_tasks_done,
        count(t.id) FILTER (WHERE t.status = 'in_progress') AS dev_tasks_in_progress,
        count(t.id) FILTER (
            WHERE t.id IS NOT NULL
              AND (t.status IS NULL OR t.status NOT IN ('done','in_progress'))
        ) AS dev_tasks_other
    FROM plan_ref p
    LEFT JOIN dev.dev_task t
      ON (
           (t.meta->>'flowmind_plan_id')     = p.plan_id::text
        OR (t.meta->>'flowmind_plan_domain') = p.plan_domain
      )
    GROUP BY p.plan_id, p.plan_domain
),
kpi_agg AS (
    SELECT
        coalesce(sum(k.total_delivered), 0)    AS kpi_total_delivered,
        coalesce(sum(k.on_time_delivered), 0) AS kpi_on_time_delivered,
        coalesce(sum(k.late_delivered), 0)    AS kpi_late_delivered,
        round(
            100.0 * coalesce(sum(k.on_time_delivered), 0)
            / greatest(coalesce(sum(k.total_delivered), 0), 1),
            2
        ) AS kpi_on_time_pct
    FROM analytics.logistics_ontime_delivery_kpi_daily k
)
SELECT
    pt.plan_id,
    pt.plan_domain,
    pt.dev_tasks_total,
    pt.dev_tasks_done,
    pt.dev_tasks_in_progress,
    pt.dev_tasks_other,
    ka.kpi_total_delivered,
    ka.kpi_on_time_delivered,
    ka.kpi_late_delivered,
    ka.kpi_on_time_pct
FROM plan_tasks pt
CROSS JOIN kpi_agg ka
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_flowmind_df3_logistics_progress_plan
    ON analytics.flowmind_df3_logistics_progress_mv (plan_id);

COMMIT;
