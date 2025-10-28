-- 20251028_availability_mv_with_defaults.sql
DROP MATERIALIZED VIEW IF EXISTS public.vehicle_availability_mv;

CREATE MATERIALIZED VIEW public.vehicle_availability_mv AS
WITH segs AS (
  SELECT
      tr.truck_id::uuid AS truck_id,
      s.dest_region     AS dest_region,
      COALESCE(s.planned_unload_window_end, s.planned_unload_window_start) AS unload_end,
      s.segment_order
  FROM public.trips tr
  JOIN public.trip_segments s ON s.trip_id = tr.id
),
last_unload AS (
  SELECT truck_id, MAX(unload_end) AS last_unload_end
  FROM segs
  WHERE unload_end IS NOT NULL
  GROUP BY truck_id
),
last_region AS (
  SELECT DISTINCT ON (s.truck_id)
         s.truck_id,
         s.dest_region AS available_region,
         s.unload_end
  FROM segs s
  JOIN last_unload lu
    ON lu.truck_id = s.truck_id AND s.unload_end = lu.last_unload_end
  ORDER BY s.truck_id, s.unload_end DESC, s.segment_order DESC
)
SELECT
    t.id AS truck_id,
    (
      COALESCE(lu.last_unload_end, now())
      + make_interval(mins => 120)  -- service: 2h
      + make_interval(mins => 480)  -- rest:   8h
    )::timestamptz AS available_from,
    COALESCE(lr.available_region, d.region)::text AS available_region,
    COALESCE(lr.available_region, d.region)::text AS next_region
FROM public.trucks t
LEFT JOIN last_unload lu ON lu.truck_id = t.id
LEFT JOIN last_region lr ON lr.truck_id = t.id
LEFT JOIN public.truck_region_defaults d ON d.truck_id = t.id;

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_availability_mv_truck
  ON public.vehicle_availability_mv(truck_id);

CREATE INDEX IF NOT EXISTS ix_vehicle_availability_mv_next_region
  ON public.vehicle_availability_mv(next_region);
