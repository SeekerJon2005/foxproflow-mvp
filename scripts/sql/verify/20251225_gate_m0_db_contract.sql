-- FoxProFlow • Gate M0+ • DB Contract Verify
-- file: scripts/sql/verify/20251225_gate_m0_db_contract.sql
-- owner: Архитектор Яцков Евгений Анатольевич
--
-- Goal:
--   Fail fast if DB misses required schemas/objects for M0/M0+.
--   All checks are schema-qualified (no dependency on search_path).

\pset pager off
\set ON_ERROR_STOP on

SELECT 'verify:gate_m0_db_contract:begin' AS _;

DO $$
DECLARE
  missing_schemas text[] := ARRAY[]::text[];
  missing_objs    text[] := ARRAY[]::text[];
  wrong_kinds     text[] := ARRAY[]::text[];
  r regclass;
  k text;
BEGIN
  -- =========================
  -- Schemas (LAW)
  -- =========================
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='public')    THEN missing_schemas := array_append(missing_schemas,'public'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='ops')       THEN missing_schemas := array_append(missing_schemas,'ops'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='dev')       THEN missing_schemas := array_append(missing_schemas,'dev'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='crm')       THEN missing_schemas := array_append(missing_schemas,'crm'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='planner')   THEN missing_schemas := array_append(missing_schemas,'planner'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='analytics') THEN missing_schemas := array_append(missing_schemas,'analytics'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='sec')       THEN missing_schemas := array_append(missing_schemas,'sec'); END IF;

  IF array_length(missing_schemas,1) IS NOT NULL THEN
    RAISE EXCEPTION 'MISSING_DB_SCHEMAS: %', array_to_string(missing_schemas, ', ');
  END IF;

  -- =========================
  -- Migration registries (existence)
  -- =========================
  r := to_regclass('public.alembic_version');
  IF r IS NULL THEN
    missing_objs := array_append(missing_objs,'public.alembic_version');
    RAISE NOTICE 'HINT: apply fixpack scripts/sql/fixpacks/20251226_migration_registries_apply.sql (or bootstrap_min apply) to create registries';
  ELSE
    SELECT relkind::text INTO k FROM pg_class WHERE oid=r;
    IF k <> 'r' THEN wrong_kinds := array_append(wrong_kinds,'public.alembic_version(kind='||k||')'); END IF;
  END IF;

  r := to_regclass('public.schema_migrations');
  IF r IS NULL THEN
    missing_objs := array_append(missing_objs,'public.schema_migrations');
    RAISE NOTICE 'HINT: apply fixpack scripts/sql/fixpacks/20251226_migration_registries_apply.sql (or bootstrap_min apply) to create registries';
  ELSE
    SELECT relkind::text INTO k FROM pg_class WHERE oid=r;
    IF k <> 'r' THEN wrong_kinds := array_append(wrong_kinds,'public.schema_migrations(kind='||k||')'); END IF;
  END IF;

  -- =========================
  -- Ops tables (M0+)
  -- =========================
  r := to_regclass('ops.audit_events');
  IF r IS NULL THEN
    missing_objs := array_append(missing_objs,'ops.audit_events');
    RAISE NOTICE 'HINT: apply fixpack scripts/sql/fixpacks/20251224_m0_ops_audit_events_apply.sql';
  ELSE
    SELECT relkind::text INTO k FROM pg_class WHERE oid=r;
    IF k <> 'r' THEN wrong_kinds := array_append(wrong_kinds,'ops.audit_events(kind='||k||')'); END IF;
  END IF;

  r := to_regclass('ops.agent_events');
  IF r IS NULL THEN
    missing_objs := array_append(missing_objs,'ops.agent_events');
    RAISE NOTICE 'HINT: apply fixpack scripts/sql/fixpacks/20251224_ops_agent_events_apply.sql';
  ELSE
    SELECT relkind::text INTO k FROM pg_class WHERE oid=r;
    IF k <> 'r' THEN wrong_kinds := array_append(wrong_kinds,'ops.agent_events(kind='||k||')'); END IF;
  END IF;

  -- =========================
  -- Fail
  -- =========================
  IF array_length(wrong_kinds,1) IS NOT NULL THEN
    RAISE EXCEPTION 'WRONG_DB_OBJECT_KINDS: %', array_to_string(wrong_kinds, ', ');
  END IF;

  IF array_length(missing_objs,1) IS NOT NULL THEN
    RAISE EXCEPTION 'MISSING_DB_OBJECTS: %', array_to_string(missing_objs, ', ');
  END IF;
END $$;

SELECT 'verify:gate_m0_db_contract:ok' AS _;
