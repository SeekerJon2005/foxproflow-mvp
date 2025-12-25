BEGIN;

CREATE OR REPLACE VIEW analytics.devfactory_autofix_kpi_v1 AS
WITH tasks AS (
  SELECT
    id,
    COALESCE(
      NULLIF(input_spec ->> 'project_ref', ''),
      NULLIF(links      ->> 'project_ref', ''),
      NULLIF(source, ''),
      'global'
    )                         AS project_ref,
    stack,
    status,
    autofix_enabled,
    autofix_status,
    created_at
  FROM dev.dev_task
)
SELECT
  project_ref,
  stack,
  COUNT(*)                                         AS total_tasks,
  COUNT(*) FILTER (WHERE autofix_enabled)          AS autofix_enabled_tasks,
  COUNT(*) FILTER (WHERE autofix_status = 'pending') AS autofix_pending,
  COUNT(*) FILTER (WHERE autofix_status = 'running') AS autofix_running,
  COUNT(*) FILTER (WHERE autofix_status = 'ok')      AS autofix_ok,
  COUNT(*) FILTER (WHERE autofix_status = 'failed')  AS autofix_failed,
  MAX(created_at)                                  AS last_task_created_at
FROM tasks
GROUP BY project_ref, stack;

COMMENT ON VIEW analytics.devfactory_autofix_kpi_v1 IS
  'KPI по Autofix для задач DevFactory: распределение статусов по проекту и стеку';

COMMIT;
