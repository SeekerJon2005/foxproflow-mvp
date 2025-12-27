BEGIN;

CREATE OR REPLACE VIEW analytics.devfactory_task_list_autofix_v1 AS
SELECT
  t.id,
  COALESCE(
    NULLIF(t.input_spec ->> 'project_ref', ''),
    NULLIF(t.links      ->> 'project_ref', ''),
    NULLIF(t.source, ''),
    'global'
  ) AS project_ref,
  t.stack,
  t.status,
  t.source,
  t.autofix_enabled,
  t.autofix_status,
  t.created_at
FROM dev.dev_task AS t;

COMMENT ON VIEW analytics.devfactory_task_list_autofix_v1 IS
  'Список задач DevFactory с autofix-флагами: project_ref, stack, status, source, autofix_enabled/autofix_status, created_at';

COMMIT;
