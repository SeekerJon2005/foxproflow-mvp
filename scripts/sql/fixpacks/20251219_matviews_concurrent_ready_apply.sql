-- FoxProFlow • FixPack • Make matviews CONCURRENT-refresh ready (unique indexes)
-- file: scripts/sql/fixpacks/20251219_matviews_concurrent_ready_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Idempotent: uses IF NOT EXISTS
--  - Safe: uses CREATE INDEX CONCURRENTLY to minimize locking
--  - Purpose: ensure each key matview has a VALID UNIQUE non-partial index for REFRESH ... CONCURRENTLY
-- Preconditions:
--  - Postgres 15+
--  - Run outside heavy load (best), but CONCURRENTLY minimizes lock time
-- Rollback:
--  - DROP INDEX CONCURRENTLY IF EXISTS <index_name>;

\set ON_ERROR_STOP on

-- Keep lock waits bounded; adjust if you prefer to wait longer.
SET lock_timeout = '10s';

-- ========= analytics =========

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_devfactory_autofix_df3_kpi_by_task_mv_dev_task
  ON analytics.devfactory_autofix_df3_kpi_by_task_mv (dev_task_id);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_devfactory_autofix_df3_kpi_daily_mv_day
  ON analytics.devfactory_autofix_df3_kpi_daily_mv (day);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_devfactory_dev_tasks_flow_daily_df3_mv_day_stack_status
  ON analytics.devfactory_dev_tasks_flow_daily_df3_mv (day_utc, stack, status);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_devfactory_task_kpi_v2_project_ref_stack
  ON analytics.devfactory_task_kpi_v2 (project_ref, stack);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_flowmind_df3_logistics_progress_plan
  ON analytics.flowmind_df3_logistics_progress_mv (plan_id);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_flowmind_plan_dev_progress_mv_plan_stack
  ON analytics.flowmind_plan_dev_progress_mv (plan_id, stack);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS flowmind_plan_devfactory_preflight_week01_progress_mv_idx
  ON analytics.flowmind_plan_devfactory_preflight_week01_progress_mv (plan_id, stack, status);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_freights_ati_price_distance_mv_pk
  ON analytics.freights_ati_price_distance_mv (source, loading_city, unloading_city);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_logistics_ontime_delivery_kpi_daily_day
  ON analytics.logistics_ontime_delivery_kpi_daily (day);

-- ========= public =========

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_driver_history_mv_tractor_driver_started
  ON public.driver_history_mv (tractor_id, driver_id, started_at);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_freights_enriched_key
  ON public.freights_enriched_mv (source, source_uid);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_fe_mv2_source_source_uid
  ON public.freights_enriched_mv_v2 (source, source_uid);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_fpd_norm_source_uid
  ON public.freights_price_distance_norm_mv (source_uid);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_market_rates_mv
  ON public.market_rates_mv (day, loading_region, unloading_region);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_arrival_stats_unique
  ON public.od_arrival_stats_mv (loading_region, unloading_region, body_type, tonnage_class, hour_of_day);

-- NOTE: od_price_quantiles_mv already has unique indexes in your inventory; keep one canonical name.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_od_price_quantiles_mv
  ON public.od_price_quantiles_mv (loading_region, unloading_region, body_type, tonnage_class);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_planner_kpi_daily_day
  ON public.planner_kpi_daily (day);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_vehicle_availability_key
  ON public.vehicle_availability_mv (truck_id, available_from);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_vehicle_avail_truck
  ON public.vehicle_availability_mv_base (truck_id);

-- Optional: stats refresh for planner decisions (cheap-ish)
ANALYZE analytics.devfactory_autofix_df3_kpi_by_task_mv;
ANALYZE analytics.devfactory_autofix_df3_kpi_daily_mv;
ANALYZE analytics.devfactory_dev_tasks_flow_daily_df3_mv;
ANALYZE analytics.devfactory_task_kpi_v2;
ANALYZE analytics.flowmind_df3_logistics_progress_mv;
ANALYZE analytics.flowmind_plan_dev_progress_mv;
ANALYZE analytics.flowmind_plan_devfactory_preflight_week01_progress_mv;
ANALYZE analytics.freights_ati_price_distance_mv;
ANALYZE analytics.logistics_ontime_delivery_kpi_daily;

ANALYZE public.driver_history_mv;
ANALYZE public.freights_enriched_mv;
ANALYZE public.freights_enriched_mv_v2;
ANALYZE public.freights_price_distance_norm_mv;
ANALYZE public.market_rates_mv;
ANALYZE public.od_arrival_stats_mv;
ANALYZE public.od_price_quantiles_mv;
ANALYZE public.planner_kpi_daily;
ANALYZE public.vehicle_availability_mv;
ANALYZE public.vehicle_availability_mv_base;
