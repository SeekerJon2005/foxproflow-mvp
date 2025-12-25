-- FoxProFlow • Smoke • vehicle_availability_mv freshness
-- file: scripts/sql/verify/20251221_vehicle_availability_freshness_smoke.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT
  now() AS ts_now,
  (SELECT max(computed_at) FROM public.vehicle_availability_mv) AS mv_max_computed_at,
  (SELECT count(*) FROM public.vehicle_availability_mv) AS mv_rows;
