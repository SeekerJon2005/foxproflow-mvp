-- 2025-12-27
-- FoxProFlow • Fixpack • Analytics
-- file: scripts/sql/fixpacks/20251227_analytics_devfactory_task_kpi_v2_ddl_apply.sql
--
-- Canonicalize legacy patch:
--   scripts/sql/patches/20251212_analytics_devfactory_task_kpi_v2.sql
-- into fixpacks/** (C-branch policy: only fixpacks/migrations/verify).
--
-- IMPORTANT:
--   DDL-only. Creates MV WITH NO DATA if absent.
--   First populate must be done once (bootstrap):
--     REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
--   After that, a UNIQUE non-partial index enables REFRESH ... CONCURRENTLY (handled by separate fixpack).

SET client_min_messages = notice;
SET client_encoding = 'UTF8';
SET lock_timeout = '10s';
SET statement_timeout = '5min';

SELECT pg_advisory_lock(9223372036854775707); -- stable lock id for KPI v2 DDL

CREATE SCHEMA IF NOT EXISTS analytics;

DO $$
DECLARE
  col text;
BEGIN
  -- Preconditions (fail fast, explicit next-step)
  IF to_regclass('dev.dev_task') IS NULL THEN
    RAISE EXCEPTION
      'Missing required table dev.dev_task. Apply fixpack scripts/sql/fixpacks/20251224_m0_devfactory_contract_apply.sql first.';
  END IF;

  IF to_regclass('analytics.devfactory_task_kpi_v2') IS NULL THEN
    RAISE NOTICE 'creating analytics.devfactory_task_kpi_v2 (WITH NO DATA)';

    EXECUTE $mv$
      CREATE MATERIALIZED VIEW analytics.devfactory_task_kpi_v2 AS
      WITH base AS (
        SELECT
          COALESCE(t.meta->>'project_ref', 'foxproflow-core') AS project_ref,
          t.stack::text                                      AS stack,
          t.status::text                                     AS status,
          t.created_at,
          t.updated_at
        FROM dev.dev_task t
      )
      SELECT
        base.project_ref,
        base.stack,
        COUNT(*)                                             AS total_tasks,
        COUNT(*) FILTER (WHERE base.status = 'new')           AS new_tasks,
        COUNT(*) FILTER (WHERE base.status = 'done')          AS done_tasks,
        COUNT(*) FILTER (WHERE base.status = 'failed')        AS failed_tasks,
        MAX(base.created_at)                                  AS last_created_at,
        MAX(base.updated_at)                                  AS last_updated_at,
        AVG(EXTRACT(EPOCH FROM base.updated_at - base.created_at))
          FILTER (WHERE base.status = 'done')                 AS avg_duration_sec
      FROM base
      GROUP BY base.project_ref, base.stack
      WITH NO DATA;
    $mv$;

  ELSE
    -- Shape sanity (if someone created a different MV, we fail loudly)
    FOREACH col IN ARRAY ARRAY[
      'project_ref','stack','total_tasks','new_tasks','done_tasks','failed_tasks',
      'last_created_at','last_updated_at','avg_duration_sec'
    ] LOOP
      IF NOT EXISTS (
        SELECT 1
        FROM pg_attribute a
        WHERE a.attrelid = 'analytics.devfactory_task_kpi_v2'::regclass
          AND a.attname  = col
          AND a.attnum > 0
          AND NOT a.attisdropped
      ) THEN
        RAISE EXCEPTION
          'analytics.devfactory_task_kpi_v2 exists but missing expected column: %. Rebuild required: DROP MATERIALIZED VIEW analytics.devfactory_task_kpi_v2; then re-apply this DDL fixpack, REFRESH once, and re-apply UNIQUE-index fixpack.',
          col;
      END IF;
    END LOOP;

    RAISE NOTICE 'OK: analytics.devfactory_task_kpi_v2 already exists; skip DDL';
  END IF;
END
$$;

-- Comments (safe to re-run once MV exists)
COMMENT ON MATERIALIZED VIEW analytics.devfactory_task_kpi_v2 IS
'DevFactory KPI v2: aggregates over dev.dev_task grouped by (project_ref, stack). DDL-only; first REFRESH is done by bootstrap without CONCURRENTLY.';

COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.project_ref IS 'Project reference (meta->>project_ref or fallback)';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.stack IS 'Stack/domain of task';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.total_tasks IS 'Total tasks count';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.new_tasks IS 'Count where status=new';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.done_tasks IS 'Count where status=done';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.failed_tasks IS 'Count where status=failed';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.last_created_at IS 'Max created_at in group';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.last_updated_at IS 'Max updated_at in group';
COMMENT ON COLUMN analytics.devfactory_task_kpi_v2.avg_duration_sec IS 'Avg duration (sec) for done tasks';

SELECT pg_advisory_unlock(9223372036854775707);

SELECT 'OK: ensured analytics.devfactory_task_kpi_v2 DDL (WITH NO DATA) + comments' AS _;
