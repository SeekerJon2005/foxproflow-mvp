-- FoxProFlow • FixPack • Align ops.driver_alerts.trip_id type with public.trips.id (offroute)
-- file: scripts/sql/fixpacks/20251223_ops_driver_alerts_trip_id_align_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Why:
--   driver.alerts.offroute uses public.trips.id as trip_id. If ops.driver_alerts.trip_id is uuid, offroute will skip_bad_id.
-- Idempotent. No DROP. Safe when ops.driver_alerts is empty.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858380);

DO $$
DECLARE
  trips_id_udt text;
  alerts_trip_udt text;
  alerts_rows bigint;
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RAISE EXCEPTION 'public.trips missing';
  END IF;
  IF to_regclass('ops.driver_alerts') IS NULL THEN
    RAISE EXCEPTION 'ops.driver_alerts missing';
  END IF;

  SELECT c.udt_name INTO trips_id_udt
  FROM information_schema.columns c
  WHERE c.table_schema='public' AND c.table_name='trips' AND c.column_name='id';

  SELECT c.udt_name INTO alerts_trip_udt
  FROM information_schema.columns c
  WHERE c.table_schema='ops' AND c.table_name='driver_alerts' AND c.column_name='trip_id';

  SELECT count(*) INTO alerts_rows FROM ops.driver_alerts;

  -- Only act on the known bad combo: trips.id is bigint/int8, alerts.trip_id is uuid
  IF trips_id_udt IN ('int8','bigint') AND alerts_trip_udt='uuid' THEN
    IF alerts_rows > 0 THEN
      -- We cannot safely convert existing uuid values to bigint automatically.
      RAISE NOTICE 'ops.driver_alerts has % rows; trip_id is uuid -> bigint conversion skipped for safety', alerts_rows;
    ELSE
      RAISE NOTICE 'Altering ops.driver_alerts.trip_id uuid -> bigint (table empty)';
      EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN trip_id TYPE bigint USING (NULLIF(trip_id::text, '''')::bigint)';
      EXECUTE 'COMMENT ON COLUMN ops.driver_alerts.trip_id IS ''Trip internal id (public.trips.id, bigint)''';
    END IF;
  ELSE
    RAISE NOTICE 'No action: public.trips.id udt=% ; ops.driver_alerts.trip_id udt=%', trips_id_udt, alerts_trip_udt;
  END IF;
END$$;

ANALYZE ops.driver_alerts;

SELECT pg_advisory_unlock(74858380);
