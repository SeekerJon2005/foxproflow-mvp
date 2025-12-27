-- FoxProFlow • FixPack • CityMap MIN bootstrap (for driver.alerts.offroute)
-- file: scripts/sql/fixpacks/20251223_city_map_min_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Provide minimal public.city_map so driver.offroute can resolve origin/dest coords.
-- Notes:
--   tasks_driver_alerts.py autodetects key/lat/lon columns in public.city_map.
--   We therefore provide a robust superset: key/region_key/region_code/name/city + lat/lon (+ generated latitude/longitude/lng).
-- Idempotent. No DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858377);

CREATE SCHEMA IF NOT EXISTS public;

-- 1) Base table
CREATE TABLE IF NOT EXISTS public.city_map (
  id          bigserial PRIMARY KEY,

  -- key columns (autodetect friendly)
  key         text,
  region_key  text,
  region_code text,
  name        text,
  city        text,

  -- coords (autodetect friendly)
  lat         double precision,
  lon         double precision,

  -- optional coords aliases (generated; safe if code prefers latitude/longitude/lng)
  latitude    double precision GENERATED ALWAYS AS (lat) STORED,
  longitude   double precision GENERATED ALWAYS AS (lon) STORED,
  lng         double precision GENERATED ALWAYS AS (lon) STORED,

  meta        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.city_map IS
  'CityMap: mapping of region/city keys to coordinates. Used by driver.alerts.offroute and other geo logic.';

-- 2) Schema-align if table existed in other shape
DO $$
BEGIN
  IF to_regclass('public.city_map') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS key         text;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS region_key  text;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS region_code text;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS name        text;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS city        text;

  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS lat         double precision;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS lon         double precision;

  -- generated aliases (if not present)
  BEGIN
    EXECUTE 'ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS latitude  double precision GENERATED ALWAYS AS (lat) STORED';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map latitude generated col skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS longitude double precision GENERATED ALWAYS AS (lon) STORED';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map longitude generated col skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS lng       double precision GENERATED ALWAYS AS (lon) STORED';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map lng generated col skipped: %', SQLERRM;
  END;

  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS meta        jsonb;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS created_at  timestamptz;
  ALTER TABLE public.city_map ADD COLUMN IF NOT EXISTS updated_at  timestamptz;

  -- defaults / NOT NULL best-effort
  BEGIN
    EXECUTE 'ALTER TABLE public.city_map ALTER COLUMN meta SET DEFAULT ''{}''::jsonb';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map meta default skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'UPDATE public.city_map SET meta = ''{}''::jsonb WHERE meta IS NULL';
    EXECUTE 'ALTER TABLE public.city_map ALTER COLUMN meta SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map meta NOT NULL align skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.city_map ALTER COLUMN created_at SET DEFAULT now()';
    EXECUTE 'ALTER TABLE public.city_map ALTER COLUMN updated_at SET DEFAULT now()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'city_map created_at/updated_at defaults skipped: %', SQLERRM;
  END;

END$$;

-- 3) Indexes for fast lookup (loose matching uses text; keep lower() indexes)
CREATE INDEX IF NOT EXISTS city_map_key_lc_idx
  ON public.city_map ((lower(key)));

CREATE INDEX IF NOT EXISTS city_map_region_key_lc_idx
  ON public.city_map ((lower(region_key)));

CREATE INDEX IF NOT EXISTS city_map_region_code_lc_idx
  ON public.city_map ((lower(region_code)));

CREATE INDEX IF NOT EXISTS city_map_name_lc_idx
  ON public.city_map ((lower(name)));

CREATE INDEX IF NOT EXISTS city_map_city_lc_idx
  ON public.city_map ((lower(city)));

-- 4) Seed minimal test keys used in your smoke run (safe, idempotent)
-- Coordinates are just stable demo points.
INSERT INTO public.city_map (key, region_key, region_code, name, city, lat, lon, meta, created_at, updated_at)
SELECT
  'test_origin', 'test_origin', 'test_origin', 'test_origin', 'test_origin',
  55.751244, 37.618423,
  jsonb_build_object('seed','citymap-smoke'),
  now(), now()
WHERE NOT EXISTS (
  SELECT 1 FROM public.city_map
  WHERE lower(coalesce(key,''))='test_origin'
     OR lower(coalesce(region_key,''))='test_origin'
     OR lower(coalesce(region_code,''))='test_origin'
     OR lower(coalesce(name,''))='test_origin'
     OR lower(coalesce(city,''))='test_origin'
);

INSERT INTO public.city_map (key, region_key, region_code, name, city, lat, lon, meta, created_at, updated_at)
SELECT
  'test_dest', 'test_dest', 'test_dest', 'test_dest', 'test_dest',
  59.939095, 30.315868,
  jsonb_build_object('seed','citymap-smoke'),
  now(), now()
WHERE NOT EXISTS (
  SELECT 1 FROM public.city_map
  WHERE lower(coalesce(key,''))='test_dest'
     OR lower(coalesce(region_key,''))='test_dest'
     OR lower(coalesce(region_code,''))='test_dest'
     OR lower(coalesce(name,''))='test_dest'
     OR lower(coalesce(city,''))='test_dest'
);

ANALYZE public.city_map;

SELECT pg_advisory_unlock(74858377);
