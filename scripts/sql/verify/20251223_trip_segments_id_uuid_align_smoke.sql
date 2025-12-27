-- FoxProFlow • Verify/Smoke • trip_segments.id UUID contract
-- file: scripts/sql/verify/20251223_trip_segments_id_uuid_align_smoke.sql
--
-- Purpose:
--   Prove contract required by routing.enrich update-by-id (casts to ::uuid):
--     public.trip_segments.id MUST be type uuid.
--
-- Hard FAIL:
--   - table missing
--   - column id missing
--   - id type is not uuid
--
-- Soft WARN (NOTICE only):
--   - id is nullable
--   - id has no default
--   - no primary key on (id)
--
-- Output:
--   Prints PASS marker for automation: "PASS: ..."

\set ON_ERROR_STOP on
\pset pager off

-- Context header (useful in RAW logs)
SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  inet_server_addr() AS server_addr,
  inet_server_port() AS server_port,
  current_setting('server_version', true) AS pg_version,
  current_setting('TimeZone', true) AS timezone;

DO $$
DECLARE
  v_schema      text := 'public';
  v_table       text := 'trip_segments';
  v_column      text := 'id';

  udt           text;
  is_nullable   text;
  col_default   text;

  id_attnum     int;
  pk_has_id     boolean := false;
BEGIN
  -- 1) Table existence
  IF to_regclass(format('%I.%I', v_schema, v_table)) IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing %.%', v_schema, v_table;
  END IF;

  -- 2) Column existence + type
  SELECT c.udt_name, c.is_nullable, c.column_default
    INTO udt, is_nullable, col_default
  FROM information_schema.columns c
  WHERE c.table_schema = v_schema
    AND c.table_name   = v_table
    AND c.column_name  = v_column;

  IF udt IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing %.%.%', v_schema, v_table, v_column;
  END IF;

  IF udt <> 'uuid' THEN
    RAISE EXCEPTION 'FAILED: bad type %.%.% expected uuid, got %', v_schema, v_table, v_column, udt;
  END IF;

  -- 3) Soft checks (WARN only)
  IF is_nullable IS NOT NULL AND upper(is_nullable) = 'YES' THEN
    RAISE NOTICE 'WARN: %.%.% is nullable (expected NOT NULL for identifier)', v_schema, v_table, v_column;
  END IF;

  IF col_default IS NULL OR btrim(col_default) = '' THEN
    RAISE NOTICE 'WARN: %.%.% has no DEFAULT (ok if IDs are set by app/import; consider default for inserts)', v_schema, v_table, v_column;
  END IF;

  -- 4) Primary key presence on (id) — WARN only (contract for routing.update does not require PK, but DB health does)
  SELECT a.attnum
    INTO id_attnum
  FROM pg_attribute a
  WHERE a.attrelid = format('%I.%I', v_schema, v_table)::regclass
    AND a.attname = v_column
    AND a.attnum > 0
    AND NOT a.attisdropped;

  IF id_attnum IS NULL THEN
    -- should never happen if information_schema found the column, but keep it explicit
    RAISE NOTICE 'WARN: could not resolve pg_attribute attnum for %.%.%', v_schema, v_table, v_column;
  ELSE
    SELECT EXISTS (
      SELECT 1
      FROM pg_constraint con
      WHERE con.conrelid = format('%I.%I', v_schema, v_table)::regclass
        AND con.contype = 'p'
        AND id_attnum = ANY(con.conkey)
    )
    INTO pk_has_id;

    IF NOT pk_has_id THEN
      RAISE NOTICE 'WARN: %.%.% is not part of PRIMARY KEY (recommended: PK on id)', v_schema, v_table, v_column;
    END IF;
  END IF;
END $$;

SELECT 'PASS: public.trip_segments.id is uuid' AS pass;
