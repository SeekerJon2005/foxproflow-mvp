-- FoxProFlow • FixPack • public matviews CONCURRENT-ready (no analytics dependency)
-- file: scripts/sql/fixpacks/20251221_public_matviews_concurrent_ready_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Uses psql conditionals to avoid errors when objects/columns are absent.
--  - Creates UNIQUE INDEX CONCURRENTLY IF NOT EXISTS, suitable for REFRESH ... CONCURRENTLY later.

\set ON_ERROR_STOP on
\echo '=== public matviews CONCURRENT-ready apply ==='

-- helper: planner (already ok, but keep idempotent)
SELECT to_regclass('planner.planner_kpi_daily') IS NOT NULL AS has_planner \gset
\if :has_planner
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS planner_kpi_daily_day_uidx
  ON planner.planner_kpi_daily(day);
\endif

-- freights_enriched_mv: unique by id
SELECT to_regclass('public.freights_enriched_mv') IS NOT NULL AS has_fe \gset
\if :has_fe
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_freights_enriched_mv_id
  ON public.freights_enriched_mv(id);
\endif

-- market_rates_mv: key varies by version (OD only vs OD×body×ton)
SELECT to_regclass('public.market_rates_mv') IS NOT NULL AS has_mr \gset
\if :has_mr
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='market_rates_mv' AND column_name='body_type'
) AS mr_has_body \gset
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='market_rates_mv' AND column_name='tonnage_class'
) AS mr_has_ton \gset

\if :mr_has_body
  \if :mr_has_ton
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_market_rates_mv_key
  ON public.market_rates_mv(loading_region, unloading_region, body_type, tonnage_class);
  \else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_market_rates_mv_key
  ON public.market_rates_mv(loading_region, unloading_region, body_type);
  \endif
\else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_market_rates_mv_key
  ON public.market_rates_mv(loading_region, unloading_region);
\endif
\endif

-- od_arrival_stats_mv: key varies (OD×hour vs OD×body×ton×hour)
SELECT to_regclass('public.od_arrival_stats_mv') IS NOT NULL AS has_od_arr \gset
\if :has_od_arr
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='od_arrival_stats_mv' AND column_name='body_type'
) AS oa_has_body \gset
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='od_arrival_stats_mv' AND column_name='tonnage_class'
) AS oa_has_ton \gset

\if :oa_has_body
  \if :oa_has_ton
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_arrival_stats_mv_key
  ON public.od_arrival_stats_mv(loading_region, unloading_region, body_type, tonnage_class, hour_of_day);
  \else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_arrival_stats_mv_key
  ON public.od_arrival_stats_mv(loading_region, unloading_region, body_type, hour_of_day);
  \endif
\else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_arrival_stats_mv_key
  ON public.od_arrival_stats_mv(loading_region, unloading_region, hour_of_day);
\endif
\endif

-- od_price_quantiles_mv: key varies (OD vs OD×body×ton)
SELECT to_regclass('public.od_price_quantiles_mv') IS NOT NULL AS has_od_q \gset
\if :has_od_q
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='od_price_quantiles_mv' AND column_name='body_type'
) AS oq_has_body \gset
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='od_price_quantiles_mv' AND column_name='tonnage_class'
) AS oq_has_ton \gset

\if :oq_has_body
  \if :oq_has_ton
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_price_quantiles_mv_key
  ON public.od_price_quantiles_mv(loading_region, unloading_region, body_type, tonnage_class);
  \else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_price_quantiles_mv_key
  ON public.od_price_quantiles_mv(loading_region, unloading_region, body_type);
  \endif
\else
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_price_quantiles_mv_key
  ON public.od_price_quantiles_mv(loading_region, unloading_region);
\endif
\endif

-- vehicle_availability_mv: key usually (truck_id, available_from)
SELECT to_regclass('public.vehicle_availability_mv') IS NOT NULL AS has_va \gset
\if :has_va
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='vehicle_availability_mv' AND column_name='truck_id'
) AS va_has_truck \gset
SELECT EXISTS (
  SELECT 1 FROM information_schema.columns
  WHERE table_schema='public' AND table_name='vehicle_availability_mv' AND column_name='available_from'
) AS va_has_from \gset

\if :va_has_truck
  \if :va_has_from
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_vehicle_availability_mv_key
  ON public.vehicle_availability_mv(truck_id, available_from);
  \endif
\endif
\endif

\echo '=== OK: public matviews CONCURRENT-ready apply finished ==='
