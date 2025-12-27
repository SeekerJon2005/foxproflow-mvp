-- DevFactory: табличное представление суточных KPI по стекам/типам патчей
-- Источник: dev.devfactory_kpi_daily (поле stacks jsonb)

CREATE SCHEMA IF NOT EXISTS dev;

CREATE OR REPLACE VIEW dev.devfactory_kpi_by_stack_v AS
SELECT
    d.dt,
    s->>'stack'                  AS stack,
    s->>'patch_type'             AS patch_type,
    s->>'status'                 AS status,
    (s->>'has_error')::boolean   AS has_error,
    (s->>'tasks_count')::integer AS tasks_count,
    (s->>'tasks_with_changes')::integer AS tasks_with_changes,
    (s->>'last_task_created_at')::timestamptz AS last_task_created_at
FROM dev.devfactory_kpi_daily AS d
CROSS JOIN LATERAL jsonb_array_elements(d.stacks) AS s;

COMMENT ON VIEW dev.devfactory_kpi_by_stack_v IS
    'Дневные KPI DevFactory по каждому стеку/типу патча: развёрнутый JSON stacks из dev.devfactory_kpi_daily.';
