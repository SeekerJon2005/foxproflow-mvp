-- FoxProFlow • FixPack • Telemetry source for driver offroute
-- file: scripts/sql/fixpacks/20251219_public_driver_telemetry_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
-- - Idempotent
-- - Minimal schema to satisfy autodetect in src/worker/tasks_driver_alerts.py
BEGIN;

-- Create base table if missing
CREATE TABLE IF NOT EXISTS public.driver_telemetry (
    id        BIGSERIAL PRIMARY KEY,
    trip_id   TEXT NOT NULL,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    lat       DOUBLE PRECISION,
    lon       DOUBLE PRECISION,
    payload   JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Ensure required columns exist (idempotent hardening)
ALTER TABLE public.driver_telemetry
    ADD COLUMN IF NOT EXISTS trip_id TEXT;

ALTER TABLE public.driver_telemetry
    ADD COLUMN IF NOT EXISTS ts TIMESTAMPTZ;

ALTER TABLE public.driver_telemetry
    ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;

ALTER TABLE public.driver_telemetry
    ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;

ALTER TABLE public.driver_telemetry
    ADD COLUMN IF NOT EXISTS payload JSONB;

-- Defaults / constraints (best-effort, idempotent)
ALTER TABLE public.driver_telemetry
    ALTER COLUMN ts SET DEFAULT now();

ALTER TABLE public.driver_telemetry
    ALTER COLUMN payload SET DEFAULT '{}'::jsonb;

-- trip_id NOT NULL: если колонка только что добавили, применяем аккуратно
DO $$
BEGIN
    -- Only try to enforce NOT NULL if there are no NULLs
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='public' AND table_name='driver_telemetry'
                 AND column_name='trip_id') THEN
        IF NOT EXISTS (SELECT 1 FROM public.driver_telemetry WHERE trip_id IS NULL) THEN
            BEGIN
                ALTER TABLE public.driver_telemetry ALTER COLUMN trip_id SET NOT NULL;
            EXCEPTION WHEN others THEN
                -- ignore
                NULL;
            END;
        END IF;
    END IF;
END$$;

-- Indexes for latest point lookup
CREATE INDEX IF NOT EXISTS driver_telemetry_trip_ts_desc_idx
    ON public.driver_telemetry (trip_id, ts DESC);

CREATE INDEX IF NOT EXISTS driver_telemetry_ts_desc_idx
    ON public.driver_telemetry (ts DESC);

COMMENT ON TABLE public.driver_telemetry IS
'FoxProFlow telemetry points for driver/offroute heuristics. Minimal schema: trip_id, ts, lat, lon, payload.';
COMMENT ON COLUMN public.driver_telemetry.trip_id IS 'Trip identifier (text; aligns with trips.id::text usage).';
COMMENT ON COLUMN public.driver_telemetry.ts IS 'Telemetry timestamp (UTC recommended).';
COMMENT ON COLUMN public.driver_telemetry.lat IS 'Latitude (WGS84).';
COMMENT ON COLUMN public.driver_telemetry.lon IS 'Longitude (WGS84).';
COMMENT ON COLUMN public.driver_telemetry.payload IS 'Raw payload JSON (optional).';

COMMIT;
