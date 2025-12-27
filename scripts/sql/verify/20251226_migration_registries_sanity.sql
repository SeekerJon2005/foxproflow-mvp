-- FoxProFlow • DB Contract Verify
-- file: scripts/sql/verify/20251226_migration_registries_sanity.sql
-- owner: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   Lock down migration registries as DB LAW:
--     public.alembic_version(version_num varchar(32) NOT NULL, PRIMARY KEY)
--     public.schema_migrations(version text NOT NULL, PRIMARY KEY)
--   Also ensure no duplicates in other non-system schemas.

\pset pager off
\set ON_ERROR_STOP on

SELECT 'verify:migration_registries_sanity:begin' AS _;

DO $$
DECLARE
  missing text[] := ARRAY[]::text[];
  dup text[] := ARRAY[]::text[];
  loc text;
BEGIN
  -- ---------- existence (public.*) ----------
  IF to_regclass('public.alembic_version') IS NULL THEN
    missing := array_append(missing, 'public.alembic_version');
  END IF;

  IF to_regclass('public.schema_migrations') IS NULL THEN
    missing := array_append(missing, 'public.schema_migrations');
  END IF;

  IF array_length(missing,1) IS NOT NULL THEN
    RAISE NOTICE 'HINT: apply fixpack scripts/sql/fixpacks/20251226_migration_registries_apply.sql (or bootstrap_min apply)';
    RAISE EXCEPTION 'MISSING_DB_OBJECTS: %', array_to_string(missing, ', ');
  END IF;

  -- ---------- duplicates (same name in other non-system schemas) ----------
  SELECT string_agg(n.nspname||'.'||c.relname, ', ' ORDER BY n.nspname) INTO loc
    FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind='r'
     AND c.relname='alembic_version'
     AND n.nspname NOT LIKE 'pg_%'
     AND n.nspname <> 'information_schema';

  IF (SELECT count(*)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE c.relkind='r' AND c.relname='alembic_version'
         AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema') <> 1 THEN
    dup := array_append(dup, 'alembic_version(found='||COALESCE(loc,'NONE')||')');
  END IF;

  SELECT string_agg(n.nspname||'.'||c.relname, ', ' ORDER BY n.nspname) INTO loc
    FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind='r'
     AND c.relname='schema_migrations'
     AND n.nspname NOT LIKE 'pg_%'
     AND n.nspname <> 'information_schema';

  IF (SELECT count(*)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE c.relkind='r' AND c.relname='schema_migrations'
         AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema') <> 1 THEN
    dup := array_append(dup, 'schema_migrations(found='||COALESCE(loc,'NONE')||')');
  END IF;

  IF array_length(dup,1) IS NOT NULL THEN
    RAISE EXCEPTION 'DUPLICATE_DB_OBJECTS: %', array_to_string(dup, '; ');
  END IF;

  -- ---------- columns/types/nullability ----------
  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema='public'
       AND table_name='alembic_version'
       AND column_name='version_num'
       AND data_type='character varying'
       AND character_maximum_length=32
       AND is_nullable='NO'
  ) THEN
    RAISE EXCEPTION 'WRONG_DB_CONTRACT: public.alembic_version.version_num must be varchar(32) NOT NULL';
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema='public'
       AND table_name='schema_migrations'
       AND column_name='version'
       AND data_type='text'
       AND is_nullable='NO'
  ) THEN
    RAISE EXCEPTION 'WRONG_DB_CONTRACT: public.schema_migrations.version must be text NOT NULL';
  END IF;

  -- ---------- PK ----------
  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name=kcu.constraint_name
       AND tc.table_schema=kcu.table_schema
       AND tc.table_name=kcu.table_name
     WHERE tc.table_schema='public'
       AND tc.table_name='alembic_version'
       AND tc.constraint_type='PRIMARY KEY'
       AND kcu.column_name='version_num'
  ) THEN
    RAISE EXCEPTION 'WRONG_DB_CONTRACT: public.alembic_version must have PRIMARY KEY(version_num)';
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name=kcu.constraint_name
       AND tc.table_schema=kcu.table_schema
       AND tc.table_name=kcu.table_name
     WHERE tc.table_schema='public'
       AND tc.table_name='schema_migrations'
       AND tc.constraint_type='PRIMARY KEY'
       AND kcu.column_name='version'
  ) THEN
    RAISE EXCEPTION 'WRONG_DB_CONTRACT: public.schema_migrations must have PRIMARY KEY(version)';
  END IF;

END $$;

SELECT 'info:alembic_version_rows='||(SELECT count(*) FROM public.alembic_version) AS _;
SELECT 'info:schema_migrations_rows='||(SELECT count(*) FROM public.schema_migrations) AS _;

SELECT 'verify:migration_registries_sanity:ok' AS _;
