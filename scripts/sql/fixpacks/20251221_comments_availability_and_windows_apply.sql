-- FoxProFlow • FixPack • COMMENTS for availability MV + window SLA view
-- file: scripts/sql/fixpacks/20251221_comments_availability_and_windows_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '5min';

SELECT pg_advisory_lock(74858371);

DO $$
BEGIN
  IF to_regclass('public.vehicle_availability_mv') IS NULL THEN
    RAISE EXCEPTION 'vehicle_availability_mv does not exist';
  END IF;
  IF to_regclass('public.v_window_sla_violations') IS NULL THEN
    RAISE EXCEPTION 'v_window_sla_violations does not exist';
  END IF;
END$$;

COMMENT ON MATERIALIZED VIEW public.vehicle_availability_mv IS
  'Derived per-vehicle availability snapshot for planner filtering. available_from_calc = GREATEST(vehicles.available_from, last planned_unload_end on assigned trips). Requires UNIQUE index for REFRESH CONCURRENTLY.';

COMMENT ON COLUMN public.vehicle_availability_mv.vehicle_id IS 'vehicles.id';
COMMENT ON COLUMN public.vehicle_availability_mv.vehicle_public_id IS 'vehicles.public_id';
COMMENT ON COLUMN public.vehicle_availability_mv.available_from_calc IS 'Planner-ready availability timestamp (see MV comment).';
COMMENT ON COLUMN public.vehicle_availability_mv.last_trip_id IS 'Last trip contributing planned_unload_end (if any).';
COMMENT ON COLUMN public.vehicle_availability_mv.last_segment_id IS 'Last segment contributing planned_unload_end (if any).';
COMMENT ON COLUMN public.vehicle_availability_mv.last_unloading_region IS 'Region where vehicle becomes available (from last segment).';
COMMENT ON COLUMN public.vehicle_availability_mv.last_dest_city IS 'City where vehicle becomes available (from last segment).';
COMMENT ON COLUMN public.vehicle_availability_mv.computed_at IS 'MV computation timestamp';

COMMENT ON VIEW public.v_window_sla_violations IS
  'Diagnostics: rows where windows are inverted or planned_* windows fall outside load/unload windows. Informational for QA/ops; not enforced on historical rows.';

SELECT pg_advisory_unlock(74858371);
