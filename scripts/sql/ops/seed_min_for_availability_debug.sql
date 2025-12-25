-- FoxProFlow • OPS • Seed minimal data for availability debug
-- file: scripts/sql/ops/seed_min_for_availability_debug.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   Minimal data to validate:
--     vehicles -> trips -> trip_segments -> vehicle_availability_mv
--
-- Safety:
--   - idempotent-ish via public_id uniqueness
--   - does NOT delete anything

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '5min';

-- >>> REPLACE these with real UUIDs from step 1
\set vehicle_public_id '2607ae31-ed84-45cd-bcb5-3f7662b0fddc'
\set load_public_id    '50fa78c2-20ca-41b9-b2d3-c4e362e7c015'
\set trip_public_id    'c27ce08a-b083-422f-b12b-d84e4cea4bcf'
-- 1) vehicle
INSERT INTO public.vehicles (
  public_id, status, vehicle_code, plate_number, driver_name,
  home_country, home_region, home_city,
  capacity_kg, capacity_m3, available_from,
  last_known_ts, last_known_lat, last_known_lon,
  meta
)
VALUES (
  :'vehicle_public_id'::uuid, 'active',
  'V-DEBUG-001', 'A000AA00', 'Debug Driver',
  'RU', 'DebugRegion', 'DebugCity',
  20000, 80, now(),
  now(), 55.7558, 37.6173,
  '{}'::jsonb
)
ON CONFLICT (public_id) DO NOTHING;

-- capture vehicle_id
WITH v AS (
  SELECT id FROM public.vehicles WHERE public_id = :'vehicle_public_id'::uuid
)
-- 2) load
INSERT INTO public.loads (
  public_id, status, external_ref,
  shipper_name, consignee_name,
  origin_country, origin_region, origin_city, origin_address,
  dest_country, dest_region, dest_city, dest_address,
  cargo_name, weight_kg, volume_m3,
  load_window_start, load_window_end,
  unload_window_start, unload_window_end,
  priority, price_rub,
  loading_region, unloading_region,
  meta
)
SELECT
  :'load_public_id'::uuid, 'new', 'L-DEBUG-001',
  'Shipper', 'Consignee',
  'RU', 'DebugOriginRegion', 'Moscow', 'Origin addr',
  'RU', 'DebugDestRegion', 'Saint Petersburg', 'Dest addr',
  'Debug Cargo', 1000, 5,
  now() + interval '1 hour', now() + interval '4 hour',
  now() + interval '10 hour', now() + interval '14 hour',
  1, 50000,
  'DebugOriginRegion', 'DebugDestRegion',
  '{}'::jsonb
FROM v
ON CONFLICT (public_id) DO NOTHING;

-- capture load_id
WITH l AS (
  SELECT id FROM public.loads WHERE public_id = :'load_public_id'::uuid
),
v AS (
  SELECT id FROM public.vehicles WHERE public_id = :'vehicle_public_id'::uuid
)
-- 3) trip
INSERT INTO public.trips (
  public_id, status, vehicle_id, primary_load_id,
  start_at, end_at,
  origin_city, dest_city,
  loading_region, unloading_region,
  confirmed_at,
  meta
)
SELECT
  :'trip_public_id'::uuid, 'planned', v.id, l.id,
  now() + interval '30 min', now() + interval '16 hour',
  'Moscow', 'Saint Petersburg',
  'DebugOriginRegion', 'DebugDestRegion',
  now(),
  '{}'::jsonb
FROM v, l
ON CONFLICT (public_id) DO NOTHING;

-- capture trip_id and ensure 1 segment exists
WITH t AS (
  SELECT id, vehicle_id FROM public.trips WHERE public_id = :'trip_public_id'::uuid
),
l AS (
  SELECT id FROM public.loads WHERE public_id = :'load_public_id'::uuid
)
INSERT INTO public.trip_segments (
  trip_id, seq, load_id,
  planned_load_start, planned_load_end,
  planned_unload_start, planned_unload_end,
  origin_city, dest_city,
  loading_region, unloading_region,
  segment_order,
  road_km, drive_sec, polyline,
  meta
)
SELECT
  t.id, 1, l.id,
  now() + interval '1 hour', now() + interval '2 hour',
  now() + interval '10 hour', now() + interval '12 hour',
  'Moscow', 'Saint Petersburg',
  'DebugOriginRegion', 'DebugDestRegion',
  1,
  700, 36000, NULL,
  '{}'::jsonb
FROM t, l
ON CONFLICT (trip_id, seq) DO NOTHING;

-- refresh MV
REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv;

SELECT
  v.vehicle_id, v.vehicle_public_id, v.available_from_calc, v.last_trip_id, v.last_unloading_region, v.computed_at
FROM public.vehicle_availability_mv v
WHERE v.vehicle_public_id = :'vehicle_public_id'::uuid;


