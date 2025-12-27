-- FoxProFlow • LANE-C • FixPack • region_aliases: add missing "alias" column + norm index
-- file: scripts/sql/fixpacks/20251219_region_aliases_alias_compat_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Fixes runtime error: column "alias" does not exist (seen in postgres logs)
--  - Idempotent: ADD COLUMN IF NOT EXISTS; CREATE INDEX CONCURRENTLY IF NOT EXISTS
--  - Minimal locking: ADD COLUMN takes brief ACCESS EXCLUSIVE, but metadata-only for NULLable column
-- Preconditions: none
-- Rollback:
--  - DROP INDEX CONCURRENTLY IF EXISTS ix_region_aliases_alias_norm;
--  - (Optional) ALTER TABLE public.region_aliases DROP COLUMN alias;  -- only if you are sure no data needed

\set ON_ERROR_STOP on
SET lock_timeout = '10s';

-- 1) If table exists, ensure alias column exists
ALTER TABLE IF EXISTS public.region_aliases
  ADD COLUMN IF NOT EXISTS alias text;

-- 2) Best-effort backfill alias from common alternative column names (if present)
WITH cols AS (
  SELECT column_name
  FROM information_schema.columns
  WHERE table_schema='public' AND table_name='region_aliases'
),
pick AS (
  SELECT name AS src_col
  FROM (VALUES
    ('alias_text'),
    ('alias_name'),
    ('region_alias'),
    ('name'),
    ('value')
  ) v(name)
  WHERE EXISTS (SELECT 1 FROM cols WHERE column_name=v.name)
  ORDER BY
    CASE name
      WHEN 'alias_text' THEN 1
      WHEN 'alias_name' THEN 2
      WHEN 'region_alias' THEN 3
      WHEN 'name' THEN 4
      ELSE 5
    END
  LIMIT 1
),
stmts AS (
  SELECT format(
    'UPDATE public.region_aliases SET alias = NULLIF(trim(both from %I::text), '''') WHERE (alias IS NULL OR trim(both from alias)='''' ) AND %I IS NOT NULL;',
    src_col, src_col
  ) AS ddl
  FROM pick
)
SELECT ddl FROM stmts;
\gexec

-- 3) Add expression index to support lookup lower(trim(alias)) = $1
-- (Works even if alias mostly NULL; makes the query fast when data appears)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_region_aliases_alias_norm
  ON public.region_aliases (lower(trim(both from alias)));

ANALYZE public.region_aliases;
