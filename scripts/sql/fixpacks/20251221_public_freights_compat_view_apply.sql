-- FoxProFlow • FixPack • public.freights compat VIEW (for autoplan.* readers)
-- file: scripts/sql/fixpacks/20251221_public_freights_compat_view_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Unblock queries expecting public.freights by providing a compatibility VIEW over public.market_history.
-- Notes:
--   - Creates VIEW only if public.freights does NOT exist.
--   - If later you want a real table public.freights, DROP VIEW first.
-- Apply:
--   psql -v ON_ERROR_STOP=1 < this file

\set ON_ERROR_STOP on
SET client_min_messages = NOTICE;

DO $do$
DECLARE
  rk "char";
BEGIN
  IF to_regclass('public.market_history') IS NULL THEN
    RAISE EXCEPTION 'public.market_history is missing; cannot build public.freights compat view';
  END IF;

  IF to_regclass('public.freights') IS NULL THEN
    EXECUTE $v$
      CREATE VIEW public.freights AS
      SELECT
        mh.id::bigint AS id,

        -- common OD fields
        mh.loading_region,
        mh.unloading_region,
        mh.loading_date,
        mh.unloading_date,

        -- pricing
        mh.distance_km::numeric AS distance_km,
        mh.price_rub::numeric   AS price_rub,
        mh.price_rub::numeric   AS revenue_rub,  -- alias used by some downstream

        -- rpm (prefer source rpm, else compute from price/km)
        CASE
          WHEN mh.rpm IS NOT NULL AND mh.rpm > 0 THEN mh.rpm::numeric
          WHEN mh.distance_km IS NOT NULL AND mh.distance_km > 0 AND mh.price_rub IS NOT NULL
            THEN (mh.price_rub / NULLIF(mh.distance_km, 0))::numeric
          ELSE NULL
        END AS rpm,

        mh.body_type,
        mh.tonnage_class,
        mh.source,
        mh.created_at,

        -- optional compat fields (keep NULLs to satisfy select-lists if present)
        NULL::uuid  AS public_id,
        NULL::jsonb AS meta,
        NULL::text  AS loading_city,
        NULL::text  AS unloading_city
      FROM public.market_history mh
    $v$;

    RAISE NOTICE 'Created VIEW public.freights (compat) over public.market_history';
  ELSE
    SELECT c.relkind INTO rk
    FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname='freights';

    RAISE NOTICE 'public.freights already exists (relkind=%); skipping', rk;
  END IF;
END
$do$;

RESET client_min_messages;
\echo '=== OK: public.freights compat view apply finished ==='
