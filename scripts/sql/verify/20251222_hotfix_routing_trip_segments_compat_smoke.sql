-- file: scripts/sql/verify/20251222_hotfix_routing_trip_segments_compat_smoke.sql
-- FoxProFlow • Verify/Smoke • routing.enrich.trips compat columns

\set ON_ERROR_STOP on
\pset pager off

SELECT
  to_regclass('public.trips')         AS public_trips,
  to_regclass('public.trip_segments') AS public_trip_segments;

-- trips: required cols
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='trips'
  AND column_name IN ('id','created_at','confirmed_at')
ORDER BY column_name;

-- trip_segments: required cols (from routing.py)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='trip_segments'
  AND column_name IN (
    'id','trip_id','segment_order','origin_region','dest_region',
    'src_lat','src_lon','dst_lat','dst_lon',
    'road_km','drive_sec','route_polyline','polyline'
  )
ORDER BY column_name;

-- indexes quick look
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname='public' AND tablename IN ('trips','trip_segments')
  AND indexname IN ('trip_segments_trip_id_idx','trip_segments_trip_id_segord_idx','trips_created_at_idx','trips_confirmed_at_idx')
ORDER BY tablename, indexname;

-- Run the candidate pool query shape (should execute even if returns 0 rows)
SELECT
  s.id::text,
  s.trip_id::text,
  s.segment_order,
  s.origin_region::text,
  s.dest_region::text,
  s.src_lat, s.src_lon, s.dst_lat, s.dst_lon
FROM public.trip_segments s
JOIN public.trips t ON t.id = s.trip_id
WHERE (s.road_km IS NULL OR s.drive_sec IS NULL)
ORDER BY COALESCE(t.confirmed_at, t.created_at) DESC NULLS LAST,
         s.trip_id DESC,
         s.segment_order ASC
LIMIT 1;
