-- FoxProFlow • FixPack • Booking Windows + Vehicle Availability MV
-- file: scripts/sql/fixpacks/20251221_booking_windows_and_availability_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   1) Add lightweight window-order checks (NOT VALID) for future data hygiene
--   2) Provide diagnostic view v_window_sla_violations
--   3) Create materialized view vehicle_availability_mv as stable source of vehicle available_from
--
-- Rules:
--   - Idempotent
--   - One-writer via advisory lock
--   - No manual DB edits

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '20min';

SELECT pg_advisory_lock(74858371);

-- ---------------------------------------------------------------------------
-- PRECHECK: base objects must exist
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF to_regclass('public.loads') IS NULL
     OR to_regclass('public.trips') IS NULL
     OR to_regclass('public.trip_segments') IS NULL
     OR to_regclass('public.vehicles') IS NULL
  THEN
    RAISE EXCEPTION
      'FixPack blocked: core tables missing in db=% (expected public.loads/trips/trip_segments/vehicles).',
      current_database();
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 1) CHECK constraints for window ordering (NOT VALID)
--    NOT VALID = не проверяем исторические строки, но проверяем новые/обновляемые.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  -- loads: load window order
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'loads_load_window_order_chk'
      AND conrelid = 'public.loads'::regclass
  ) THEN
    EXECUTE $sql$
      ALTER TABLE public.loads
      ADD CONSTRAINT loads_load_window_order_chk
      CHECK (
        load_window_start IS NULL
        OR load_window_end IS NULL
        OR load_window_start <= load_window_end
      ) NOT VALID
    $sql$;
  END IF;

  -- loads: unload window order
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'loads_unload_window_order_chk'
      AND conrelid = 'public.loads'::regclass
  ) THEN
    EXECUTE $sql$
      ALTER TABLE public.loads
      ADD CONSTRAINT loads_unload_window_order_chk
      CHECK (
        unload_window_start IS NULL
        OR unload_window_end IS NULL
        OR unload_window_start <= unload_window_end
      ) NOT VALID
    $sql$;
  END IF;

  -- trip_segments: planned load window order
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'trip_segments_planned_load_order_chk'
      AND conrelid = 'public.trip_segments'::regclass
  ) THEN
    EXECUTE $sql$
      ALTER TABLE public.trip_segments
      ADD CONSTRAINT trip_segments_planned_load_order_chk
      CHECK (
        planned_load_start IS NULL
        OR planned_load_end IS NULL
        OR planned_load_start <= planned_load_end
      ) NOT VALID
    $sql$;
  END IF;

  -- trip_segments: planned unload window order
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'trip_segments_planned_unload_order_chk'
      AND conrelid = 'public.trip_segments'::regclass
  ) THEN
    EXECUTE $sql$
      ALTER TABLE public.trip_segments
      ADD CONSTRAINT trip_segments_planned_unload_order_chk
      CHECK (
        planned_unload_start IS NULL
        OR planned_unload_end IS NULL
        OR planned_unload_start <= planned_unload_end
      ) NOT VALID
    $sql$;
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2) Diagnostic view: v_window_sla_violations
--    Показывает нарушения порядка окон и выход planned_* за окна load/unload.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.v_window_sla_violations AS
WITH
bad_loads AS (
  SELECT
    l.id AS load_id,
    NULL::bigint AS trip_id,
    NULL::bigint AS segment_id,
    'load'::text AS scope,
    CASE
      WHEN l.load_window_start IS NOT NULL AND l.load_window_end IS NOT NULL AND l.load_window_start > l.load_window_end
        THEN 'load_window_start > load_window_end'
      WHEN l.unload_window_start IS NOT NULL AND l.unload_window_end IS NOT NULL AND l.unload_window_start > l.unload_window_end
        THEN 'unload_window_start > unload_window_end'
      ELSE NULL
    END AS violation,
    jsonb_build_object(
      'load_window_start', l.load_window_start,
      'load_window_end',   l.load_window_end,
      'unload_window_start', l.unload_window_start,
      'unload_window_end',   l.unload_window_end
    ) AS details
  FROM public.loads l
  WHERE
    (l.load_window_start IS NOT NULL AND l.load_window_end IS NOT NULL AND l.load_window_start > l.load_window_end)
    OR
    (l.unload_window_start IS NOT NULL AND l.unload_window_end IS NOT NULL AND l.unload_window_start > l.unload_window_end)
),
bad_segments AS (
  SELECT
    s.load_id AS load_id,
    t.id AS trip_id,
    s.id AS segment_id,
    'segment'::text AS scope,
    CASE
      WHEN s.planned_load_start IS NOT NULL AND s.planned_load_end IS NOT NULL AND s.planned_load_start > s.planned_load_end
        THEN 'planned_load_start > planned_load_end'
      WHEN s.planned_unload_start IS NOT NULL AND s.planned_unload_end IS NOT NULL AND s.planned_unload_start > s.planned_unload_end
        THEN 'planned_unload_start > planned_unload_end'
      WHEN l.id IS NOT NULL
           AND l.load_window_start IS NOT NULL AND s.planned_load_start IS NOT NULL
           AND s.planned_load_start < l.load_window_start
        THEN 'planned_load_start < load_window_start'
      WHEN l.id IS NOT NULL
           AND l.load_window_end IS NOT NULL AND s.planned_load_end IS NOT NULL
           AND s.planned_load_end > l.load_window_end
        THEN 'planned_load_end > load_window_end'
      WHEN l.id IS NOT NULL
           AND l.unload_window_start IS NOT NULL AND s.planned_unload_start IS NOT NULL
           AND s.planned_unload_start < l.unload_window_start
        THEN 'planned_unload_start < unload_window_start'
      WHEN l.id IS NOT NULL
           AND l.unload_window_end IS NOT NULL AND s.planned_unload_end IS NOT NULL
           AND s.planned_unload_end > l.unload_window_end
        THEN 'planned_unload_end > unload_window_end'
      ELSE NULL
    END AS violation,
    jsonb_build_object(
      'planned_load_start', s.planned_load_start,
      'planned_load_end', s.planned_load_end,
      'planned_unload_start', s.planned_unload_start,
      'planned_unload_end', s.planned_unload_end,
      'load_window_start', l.load_window_start,
      'load_window_end', l.load_window_end,
      'unload_window_start', l.unload_window_start,
      'unload_window_end', l.unload_window_end
    ) AS details
  FROM public.trip_segments s
  JOIN public.trips t ON t.id = s.trip_id
  LEFT JOIN public.loads l ON l.id = s.load_id
  WHERE
    (s.planned_load_start IS NOT NULL AND s.planned_load_end IS NOT NULL AND s.planned_load_start > s.planned_load_end)
    OR (s.planned_unload_start IS NOT NULL AND s.planned_unload_end IS NOT NULL AND s.planned_unload_start > s.planned_unload_end)
    OR (
      l.id IS NOT NULL AND (
        (l.load_window_start IS NOT NULL AND s.planned_load_start IS NOT NULL AND s.planned_load_start < l.load_window_start)
        OR (l.load_window_end IS NOT NULL AND s.planned_load_end IS NOT NULL AND s.planned_load_end > l.load_window_end)
        OR (l.unload_window_start IS NOT NULL AND s.planned_unload_start IS NOT NULL AND s.planned_unload_start < l.unload_window_start)
        OR (l.unload_window_end IS NOT NULL AND s.planned_unload_end IS NOT NULL AND s.planned_unload_end > l.unload_window_end)
      )
    )
)
SELECT * FROM bad_loads WHERE violation IS NOT NULL
UNION ALL
SELECT * FROM bad_segments WHERE violation IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) Materialized view: vehicle_availability_mv
--
-- Strategy:
--   - One row per vehicle.
--   - Compute "available_from_calc" = max(vehicles.available_from, last planned_unload_end across assigned trips)
--   - Include unload region/city for routing filters.
--
-- NOTE (architectural):
--   service/rest buffers are NOT applied here (no canonical columns in schema).
--   When buffers are formalized, we will extend calc = planned_unload_end + buffer.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF to_regclass('public.vehicle_availability_mv') IS NULL THEN
    EXECUTE $sql$
      CREATE MATERIALIZED VIEW public.vehicle_availability_mv AS
      WITH last_seg AS (
        SELECT DISTINCT ON (t.vehicle_id)
          t.vehicle_id,
          s.id AS segment_id,
          s.trip_id,
          s.planned_unload_end,
          s.unloading_region,
          s.dest_city
        FROM public.trips t
        JOIN public.trip_segments s ON s.trip_id = t.id
        WHERE t.vehicle_id IS NOT NULL
          AND s.planned_unload_end IS NOT NULL
        ORDER BY t.vehicle_id, s.planned_unload_end DESC, s.id DESC
      )
      SELECT
        v.id AS vehicle_id,
        v.public_id AS vehicle_public_id,
        GREATEST(
          COALESCE(v.available_from, 'epoch'::timestamptz),
          COALESCE(ls.planned_unload_end, 'epoch'::timestamptz)
        ) AS available_from_calc,
        ls.trip_id AS last_trip_id,
        ls.segment_id AS last_segment_id,
        ls.unloading_region AS last_unloading_region,
        ls.dest_city AS last_dest_city,
        now() AS computed_at
      FROM public.vehicles v
      LEFT JOIN last_seg ls ON ls.vehicle_id = v.id
    $sql$;
  END IF;
END$$;

-- Required for REFRESH MATERIALIZED VIEW CONCURRENTLY: unique, non-partial, valid index
CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_availability_mv_vehicle_id
  ON public.vehicle_availability_mv (vehicle_id);

CREATE INDEX IF NOT EXISTS ix_vehicle_availability_mv_available_from
  ON public.vehicle_availability_mv (available_from_calc);

CREATE INDEX IF NOT EXISTS ix_vehicle_availability_mv_last_unloading_region
  ON public.vehicle_availability_mv (last_unloading_region);

-- First refresh (safe even if just created; use non-concurrently here)
REFRESH MATERIALIZED VIEW public.vehicle_availability_mv;

ANALYZE public.vehicle_availability_mv;

SELECT pg_advisory_unlock(74858371);
