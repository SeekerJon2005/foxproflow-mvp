-- FoxProFlow • FixPack • Fill ops.driver_alerts.driver_id from telemetry/assignments when missing
-- file: scripts/sql/fixpacks/20251223_ops_driver_alerts_fill_driver_id_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Improve data quality: if driver_id is NULL/blank in ops.driver_alerts, resolve it from
--   public.driver_telemetry / public.driver_assignments and store details.driver_src.
-- Notes:
--   This is a DB safety-net. Root cause remains Python resolver; fix in DEV later.
-- Idempotent. No DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858383);

CREATE SCHEMA IF NOT EXISTS ops;

-- ---------------------------------------------------------
-- 1) Resolver: returns {"driver_id": "...", "driver_src":"..."} or {}
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION ops.driver_alerts_resolve_driver(p_trip_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  v_driver text;
  v_src text;
BEGIN
  -- telemetry (best)
  IF to_regclass('public.driver_telemetry') IS NOT NULL THEN
    SELECT dt.driver_id INTO v_driver
    FROM public.driver_telemetry dt
    WHERE dt.trip_id::text = p_trip_id::text
      AND dt.driver_id IS NOT NULL
      AND length(trim(dt.driver_id)) > 0
    ORDER BY dt.ts DESC
    LIMIT 1;

    IF v_driver IS NOT NULL AND length(trim(v_driver)) > 0 THEN
      v_src := 'telemetry';
      RETURN jsonb_build_object('driver_id', v_driver, 'driver_src', v_src);
    END IF;
  END IF;

  -- assignments by trip_id
  IF to_regclass('public.driver_assignments') IS NOT NULL THEN
    SELECT da.driver_id INTO v_driver
    FROM public.driver_assignments da
    WHERE da.trip_id = p_trip_id
      AND da.is_active
      AND da.started_at <= now()
      AND (da.ended_at IS NULL OR da.ended_at >= now())
      AND da.driver_id IS NOT NULL
      AND length(trim(da.driver_id)) > 0
    ORDER BY da.created_at DESC
    LIMIT 1;

    IF v_driver IS NOT NULL AND length(trim(v_driver)) > 0 THEN
      v_src := 'assign_trip';
      RETURN jsonb_build_object('driver_id', v_driver, 'driver_src', v_src);
    END IF;
  END IF;

  -- assignments by truck_id / tractor_id (via trips)
  IF to_regclass('public.trips') IS NOT NULL AND to_regclass('public.driver_assignments') IS NOT NULL THEN
    SELECT da.driver_id INTO v_driver
    FROM public.trips t
    JOIN public.driver_assignments da
      ON (
        (da.truck_id IS NOT NULL AND t.truck_id IS NOT NULL AND da.truck_id = t.truck_id)
        OR (da.tractor_id IS NOT NULL AND t.truck_id IS NOT NULL AND lower(trim(both from da.tractor_id)) = lower(trim(both from t.truck_id::text)))
      )
    WHERE t.id = p_trip_id
      AND da.is_active
      AND da.started_at <= now()
      AND (da.ended_at IS NULL OR da.ended_at >= now())
      AND da.driver_id IS NOT NULL
      AND length(trim(da.driver_id)) > 0
    ORDER BY da.created_at DESC
    LIMIT 1;

    IF v_driver IS NOT NULL AND length(trim(v_driver)) > 0 THEN
      v_src := 'assign_truck';
      RETURN jsonb_build_object('driver_id', v_driver, 'driver_src', v_src);
    END IF;
  END IF;

  RETURN '{}'::jsonb;
END$$;

-- ---------------------------------------------------------
-- 2) Trigger: fill NEW.driver_id when missing
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION ops.tg_driver_alerts_fill_driver_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  res jsonb;
  v_driver text;
  v_src text;
BEGIN
  IF NEW.driver_id IS NOT NULL AND length(trim(NEW.driver_id)) > 0 THEN
    RETURN NEW;
  END IF;

  res := ops.driver_alerts_resolve_driver(NEW.trip_id);
  v_driver := nullif(res->>'driver_id','');
  v_src := nullif(res->>'driver_src','');

  IF v_driver IS NOT NULL THEN
    NEW.driver_id := v_driver;

    IF NEW.details IS NULL THEN
      NEW.details := '{}'::jsonb;
    END IF;

    -- set driver_src if missing/blank
    IF (NEW.details ? 'driver_src') IS FALSE OR NEW.details->>'driver_src' IS NULL OR length(trim(NEW.details->>'driver_src')) = 0 THEN
      NEW.details := jsonb_set(NEW.details, '{driver_src}', to_jsonb(v_src), true);
    END IF;
  END IF;

  RETURN NEW;
END$$;

DO $$
BEGIN
  IF to_regclass('ops.driver_alerts') IS NOT NULL THEN
    EXECUTE 'DROP TRIGGER IF EXISTS t_driver_alerts_fill_driver_id ON ops.driver_alerts';
    EXECUTE 'CREATE TRIGGER t_driver_alerts_fill_driver_id
             BEFORE INSERT ON ops.driver_alerts
             FOR EACH ROW
             EXECUTE FUNCTION ops.tg_driver_alerts_fill_driver_id()';
  END IF;
END$$;

-- ---------------------------------------------------------
-- 3) Backfill existing alerts where driver_id is NULL/blank
-- ---------------------------------------------------------
DO $$
BEGIN
  IF to_regclass('ops.driver_alerts') IS NULL THEN
    RETURN;
  END IF;

  UPDATE ops.driver_alerts a
  SET driver_id = nullif(res->>'driver_id',''),
      details   = CASE
                    WHEN nullif(res->>'driver_src','') IS NOT NULL
                      THEN jsonb_set(coalesce(a.details,'{}'::jsonb), '{driver_src}', to_jsonb(nullif(res->>'driver_src','')), true)
                    ELSE a.details
                  END
  FROM (
    SELECT id, ops.driver_alerts_resolve_driver(trip_id) AS res
    FROM ops.driver_alerts
    WHERE driver_id IS NULL OR length(trim(driver_id)) = 0
  ) x
  WHERE a.id = x.id
    AND nullif(x.res->>'driver_id','') IS NOT NULL;
END$$;

ANALYZE ops.driver_alerts;

SELECT pg_advisory_unlock(74858383);
