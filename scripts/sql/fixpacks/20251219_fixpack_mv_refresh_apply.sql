-- FoxProFlow • SQL Fix Pack • MV refresh apply • 2025-12-19
-- file: scripts/sql/fixpacks/20251219_fixpack_mv_refresh_apply.sql

\set refresh_all 0
\set do_analyze 1

-- psql vars are NOT substituted inside DO $$...$$
-- so we push them into session GUC via set_config (this is outside $$).
SELECT set_config('ff.refresh_all', :'refresh_all', true);
SELECT set_config('ff.do_analyze',  :'do_analyze',  true);

\echo '=== MV Refresh Fix Pack APPLY ==='
SELECT now() AS ts, current_database() AS db;

SET statement_timeout = 0;

DO $$
DECLARE
  v_refresh_all boolean := (COALESCE(current_setting('ff.refresh_all', true), '0') = '1');
  v_do_analyze  boolean := (COALESCE(current_setting('ff.do_analyze',  true), '1') = '1');
  r record;
  t0 timestamptz;
  dur_ms int;
  v_err text;
  v_ok boolean;
BEGIN
  CREATE TEMP TABLE IF NOT EXISTS __ff_fixpack_mv_refresh_results (
    ts timestamptz NOT NULL DEFAULT clock_timestamp(),
    schema_name text NOT NULL,
    matview_name text NOT NULL,
    attempted boolean NOT NULL,
    ok boolean,
    duration_ms int,
    error text
  ) ON COMMIT PRESERVE ROWS;

  FOR r IN
    SELECT n.nspname AS schema_name, c.relname AS matview_name, c.relispopulated AS is_populated
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'm'
      AND n.nspname NOT IN ('pg_catalog','information_schema')
    ORDER BY 1,2
  LOOP
    IF (NOT v_refresh_all) AND r.is_populated THEN
      INSERT INTO __ff_fixpack_mv_refresh_results(schema_name, matview_name, attempted, ok, duration_ms, error)
      VALUES (r.schema_name, r.matview_name, false, NULL, NULL, NULL);
      CONTINUE;
    END IF;

    t0 := clock_timestamp();
    v_ok := true;
    v_err := NULL;

    BEGIN
      EXECUTE format('REFRESH MATERIALIZED VIEW %I.%I', r.schema_name, r.matview_name);
      IF v_do_analyze THEN
        EXECUTE format('ANALYZE %I.%I', r.schema_name, r.matview_name);
      END IF;
    EXCEPTION WHEN OTHERS THEN
      v_ok := false;
      v_err := SQLSTATE || ': ' || SQLERRM;
    END;

    dur_ms := (extract(epoch from (clock_timestamp() - t0)) * 1000)::int;

    INSERT INTO __ff_fixpack_mv_refresh_results(schema_name, matview_name, attempted, ok, duration_ms, error)
    VALUES (r.schema_name, r.matview_name, true, v_ok, dur_ms, v_err);
  END LOOP;
END $$;

\echo ''
\echo '--- Summary (attempted/ok counts) ---'
SELECT attempted, ok, count(*) AS cnt
FROM __ff_fixpack_mv_refresh_results
GROUP BY 1,2
ORDER BY 1,2;

\echo ''
\echo '--- Failures (if any) ---'
SELECT *
FROM __ff_fixpack_mv_refresh_results
WHERE attempted IS TRUE AND ok IS FALSE
ORDER BY ts DESC, schema_name, matview_name;

\echo '=== END APPLY ==='
