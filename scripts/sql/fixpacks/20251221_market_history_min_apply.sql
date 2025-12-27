-- FoxProFlow • FixPack • market_history MIN (needed for freights_enriched_mv and downstream *_mv)
-- file: scripts/sql/fixpacks/20251221_market_history_min_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Restore minimal public.market_history contract referenced by:
--     - data_layer/migrations/mv_freights_enriched.sql
--     - data_layer/migrations/mv_market_rates.sql
--     - data_layer/migrations/mv_od_arrival_stats.sql
--     - data_layer/migrations/mv_od_price_quantiles.sql
-- Notes:
--   - Idempotent: CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS
--   - Safe defaults; no NOT NULL except created_at default.
-- Apply:
--   psql -v ON_ERROR_STOP=1 < this file

\set ON_ERROR_STOP on
SET lock_timeout = '10s';
SET statement_timeout = '0';
SET client_min_messages = NOTICE;

CREATE TABLE IF NOT EXISTS public.market_history (
  id              bigserial PRIMARY KEY,
  loading_region  text,
  unloading_region text,
  loading_date    timestamptz,
  unloading_date  timestamptz,
  distance_km     numeric,
  price_rub       numeric,
  rpm             numeric,
  body_type       text,
  tonnage_class   text,
  source          text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Ensure columns exist (if table was created earlier with smaller shape)
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS loading_region    text;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS unloading_region  text;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS loading_date      timestamptz;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS unloading_date    timestamptz;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS distance_km       numeric;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS price_rub         numeric;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS rpm               numeric;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS body_type         text;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS tonnage_class     text;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS source            text;
ALTER TABLE IF EXISTS public.market_history ADD COLUMN IF NOT EXISTS created_at        timestamptz;

ALTER TABLE IF EXISTS public.market_history
  ALTER COLUMN created_at SET DEFAULT now();

-- Helpful indexes (safe)
CREATE INDEX IF NOT EXISTS market_history_lr_ur_idx
  ON public.market_history (loading_region, unloading_region);

CREATE INDEX IF NOT EXISTS market_history_loading_date_idx
  ON public.market_history (loading_date);

CREATE INDEX IF NOT EXISTS market_history_created_at_idx
  ON public.market_history (created_at);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

\echo '=== OK: market_history_min_apply finished ==='
