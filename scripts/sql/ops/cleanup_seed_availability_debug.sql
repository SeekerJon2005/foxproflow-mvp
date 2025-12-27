-- FoxProFlow • OPS • Cleanup seed_min_for_availability_debug
-- file: scripts/sql/ops/cleanup_seed_availability_debug.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '5min';

\set vehicle_public_id '2607ae31-ed84-45cd-bcb5-3f7662b0fddc'
\set load_public_id    '50fa78c2-20ca-41b9-b2d3-c4e362e7c015'
\set trip_public_id    'c27ce08a-b083-422f-b12b-d84e4cea4bcf'

-- delete in dependency order
DELETE FROM public.trip_segments
WHERE trip_id IN (SELECT id FROM public.trips WHERE public_id = :'trip_public_id'::uuid);

DELETE FROM public.trips
WHERE public_id = :'trip_public_id'::uuid;

DELETE FROM public.loads
WHERE public_id = :'load_public_id'::uuid;

DELETE FROM public.vehicles
WHERE public_id = :'vehicle_public_id'::uuid;

REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv;

SELECT
  (SELECT count(*) FROM public.vehicles WHERE public_id = :'vehicle_public_id'::uuid) AS vehicle_left,
  (SELECT count(*) FROM public.loads    WHERE public_id = :'load_public_id'::uuid)    AS load_left,
  (SELECT count(*) FROM public.trips    WHERE public_id = :'trip_public_id'::uuid)    AS trip_left;
