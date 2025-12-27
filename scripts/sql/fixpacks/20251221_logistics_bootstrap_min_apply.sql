-- FoxProFlow • FixPack • Logistics bootstrap MIN (public.* core tables)
-- file: scripts/sql/fixpacks/20251221_logistics_bootstrap_min_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Goal:
--   Create minimal but compatible logistics core tables when DB is empty:
--     public.vehicles, public.loads, public.trips, public.trip_segments
--   Idempotent and non-destructive: CREATE IF NOT EXISTS + ALTER ADD COLUMN IF NOT EXISTS.
--
-- Notes:
--   - We intentionally use a "wide" schema (mostly nullable) to reduce mismatch with existing code.
--   - If later code expects additional columns, we extend via ALTER ADD COLUMN IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ──────────────────────────────────────────────────────────────────────────────
-- public.vehicles
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.vehicles (
  id              bigserial PRIMARY KEY,
  public_id       uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  status          text NOT NULL DEFAULT 'active',      -- active|inactive|maintenance|archived
  vehicle_code    text,                                -- internal identifier
  plate_number    text,
  driver_name     text,

  home_country    text,
  home_region     text,
  home_city       text,

  capacity_kg     numeric,
  capacity_m3     numeric,

  -- availability / planning
  available_from  timestamptz,
  last_known_ts   timestamptz,
  last_known_lat  numeric,
  last_known_lon  numeric,

  meta            jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS vehicles_public_id_uidx ON public.vehicles(public_id);
CREATE INDEX IF NOT EXISTS vehicles_status_idx ON public.vehicles(status);
CREATE INDEX IF NOT EXISTS vehicles_available_from_idx ON public.vehicles(available_from);


-- ──────────────────────────────────────────────────────────────────────────────
-- public.loads
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.loads (
  id                 bigserial PRIMARY KEY,
  public_id          uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  status             text NOT NULL DEFAULT 'new',      -- new|planned|assigned|in_transit|delivered|canceled
  external_ref       text,                             -- client/external id

  shipper_name       text,
  consignee_name     text,

  origin_country     text,
  origin_region      text,
  origin_city        text,
  origin_address     text,

  dest_country       text,
  dest_region        text,
  dest_city          text,
  dest_address       text,

  cargo_name         text,
  weight_kg          numeric,
  volume_m3          numeric,

  -- Booking windows (canonical from earlier concept)
  load_window_start   timestamptz,
  load_window_end     timestamptz,
  unload_window_start timestamptz,
  unload_window_end   timestamptz,

  -- optional planning fields
  priority           integer,
  price_rub          numeric,

  meta               jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS loads_public_id_uidx ON public.loads(public_id);
CREATE INDEX IF NOT EXISTS loads_status_idx ON public.loads(status);
CREATE INDEX IF NOT EXISTS loads_origin_city_idx ON public.loads(origin_city);
CREATE INDEX IF NOT EXISTS loads_dest_city_idx ON public.loads(dest_city);
CREATE INDEX IF NOT EXISTS loads_load_window_start_idx ON public.loads(load_window_start);
CREATE INDEX IF NOT EXISTS loads_unload_window_start_idx ON public.loads(unload_window_start);


-- ──────────────────────────────────────────────────────────────────────────────
-- public.trips
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.trips (
  id              bigserial PRIMARY KEY,
  public_id       uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  status          text NOT NULL DEFAULT 'new',          -- new|planned|confirmed|in_progress|done|canceled
  vehicle_id      bigint REFERENCES public.vehicles(id) ON DELETE SET NULL,

  -- optional "main load" shortcut (not all systems use it)
  primary_load_id bigint REFERENCES public.loads(id) ON DELETE SET NULL,

  start_at        timestamptz,
  end_at          timestamptz,

  distance_km     numeric,
  duration_min    numeric,

  -- soft routing fields
  origin_city     text,
  dest_city       text,

  meta            jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS trips_public_id_uidx ON public.trips(public_id);
CREATE INDEX IF NOT EXISTS trips_status_idx ON public.trips(status);
CREATE INDEX IF NOT EXISTS trips_vehicle_id_idx ON public.trips(vehicle_id);
CREATE INDEX IF NOT EXISTS trips_created_at_idx ON public.trips(created_at);


-- ──────────────────────────────────────────────────────────────────────────────
-- public.trip_segments
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.trip_segments (
  id                  bigserial PRIMARY KEY,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  trip_id             bigint NOT NULL REFERENCES public.trips(id) ON DELETE CASCADE,
  seq                 integer NOT NULL DEFAULT 1,

  -- Which load is served in this segment (optional)
  load_id             bigint REFERENCES public.loads(id) ON DELETE SET NULL,

  -- planned windows (canonical concept)
  planned_load_start   timestamptz,
  planned_load_end     timestamptz,
  planned_unload_start timestamptz,
  planned_unload_end   timestamptz,

  -- actual timestamps (telemetry / execution)
  actual_load_start    timestamptz,
  actual_load_end      timestamptz,
  actual_unload_start  timestamptz,
  actual_unload_end    timestamptz,

  -- soft routing
  origin_city         text,
  dest_city           text,
  distance_km         numeric,
  duration_min        numeric,

  meta                jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- enforce unique seq per trip
CREATE UNIQUE INDEX IF NOT EXISTS trip_segments_trip_seq_uidx ON public.trip_segments(trip_id, seq);
CREATE INDEX IF NOT EXISTS trip_segments_trip_id_idx ON public.trip_segments(trip_id);
CREATE INDEX IF NOT EXISTS trip_segments_load_id_idx ON public.trip_segments(load_id);
CREATE INDEX IF NOT EXISTS trip_segments_planned_load_start_idx ON public.trip_segments(planned_load_start);
CREATE INDEX IF NOT EXISTS trip_segments_planned_unload_end_idx ON public.trip_segments(planned_unload_end);

-- ──────────────────────────────────────────────────────────────────────────────
-- Schema align block: add missing columns if tables already existed (safe)
-- ──────────────────────────────────────────────────────────────────────────────

-- vehicles
ALTER TABLE public.vehicles
  ADD COLUMN IF NOT EXISTS public_id uuid NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;

-- loads
ALTER TABLE public.loads
  ADD COLUMN IF NOT EXISTS public_id uuid NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'new',
  ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;

-- trips
ALTER TABLE public.trips
  ADD COLUMN IF NOT EXISTS public_id uuid NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'new',
  ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;

-- trip_segments
ALTER TABLE public.trip_segments
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;
