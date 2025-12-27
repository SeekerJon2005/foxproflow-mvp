-- 20251227_m0_vehicle_availability_mv_unique_truck_id.sql
-- Purpose: make public.vehicle_availability_mv CONCURRENTLY refreshable (gate_m0_matviews_concurrent_ready).
-- Created by: Архитектор Яцков Евгений Анатольевич

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_matviews WHERE schemaname='public' AND matviewname='vehicle_availability_mv'
  ) THEN
    RAISE EXCEPTION 'materialized view public.vehicle_availability_mv not found';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute a
    JOIN pg_class c ON c.oid=a.attrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname='vehicle_availability_mv'
      AND a.attname='truck_id' AND a.attnum>0 AND NOT a.attisdropped
  ) THEN
    RAISE EXCEPTION 'vehicle_availability_mv has no column truck_id; choose correct unique key';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.vehicle_availability_mv
    GROUP BY truck_id
    HAVING COUNT(*)>1
    LIMIT 1
  ) THEN
    RAISE EXCEPTION 'vehicle_availability_mv has duplicate truck_id values; cannot create unique index';
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_availability_mv_truck_id
  ON public.vehicle_availability_mv (truck_id);
