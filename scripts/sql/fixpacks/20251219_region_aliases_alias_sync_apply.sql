-- FoxProFlow • LANE-C • FixPack • region_aliases: keep alias synced with alias_key
-- file: scripts/sql/fixpacks/20251219_region_aliases_alias_sync_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Ensures compatibility for lookups using column "alias"
--  - Backfills alias from alias_key for existing rows
--  - Adds BEFORE INSERT/UPDATE trigger to keep alias non-empty
--  - Idempotent: safe to run multiple times
-- Preconditions: none
-- Rollback:
--  - DROP TRIGGER IF EXISTS region_aliases__biu_00_alias_sync ON public.region_aliases;
--  - DROP FUNCTION IF EXISTS public.region_aliases__biu_00_alias_sync();

\set ON_ERROR_STOP on
SET lock_timeout = '10s';

-- 0) Ensure column exists (standalone safety)
ALTER TABLE IF EXISTS public.region_aliases
  ADD COLUMN IF NOT EXISTS alias text;

-- 1) Backfill alias from alias_key where alias is empty
DO $$
BEGIN
  IF to_regclass('public.region_aliases') IS NOT NULL THEN
    EXECUTE $q$
      UPDATE public.region_aliases
      SET alias = alias_key
      WHERE (alias IS NULL OR btrim(alias) = '')
        AND alias_key IS NOT NULL
    $q$;
  END IF;
END$$;

-- 2) Trigger function: keep alias non-empty
CREATE OR REPLACE FUNCTION public.region_aliases__biu_00_alias_sync()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  IF NEW.alias IS NULL OR btrim(NEW.alias) = '' THEN
    NEW.alias := NEW.alias_key;
  END IF;
  RETURN NEW;
END
$function$;

-- 3) Trigger (created only if missing)
DO $$
BEGIN
  IF to_regclass('public.region_aliases') IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_trigger
      WHERE tgname = 'region_aliases__biu_00_alias_sync'
        AND tgrelid = 'public.region_aliases'::regclass
    ) THEN
      EXECUTE $q$
        CREATE TRIGGER region_aliases__biu_00_alias_sync
        BEFORE INSERT OR UPDATE ON public.region_aliases
        FOR EACH ROW
        EXECUTE FUNCTION public.region_aliases__biu_00_alias_sync()
      $q$;
    END IF;
  END IF;
END$$;

ANALYZE public.region_aliases;
