-- file: src/data_layer/20251023_fleet_tracking.sql
BEGIN;

CREATE TABLE IF NOT EXISTS public.trucks(
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plate_number text UNIQUE,
  role         text,            -- 'tractor'|'trailer'
  body_type    text,
  region       text,
  trailer_id   uuid,
  driver_id    uuid,
  features     jsonb,
  caps         jsonb
);

CREATE TABLE IF NOT EXISTS public.drivers(
  driver_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name    text,
  phone        text,
  license_no   text
);

CREATE TABLE IF NOT EXISTS public.truck_status(
  truck_id     uuid PRIMARY KEY,
  region       text,
  state        text,
  updated_at   timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.truck_events(
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id     uuid,
  event_ts     timestamptz NOT NULL DEFAULT now(),
  event_type   text NOT NULL,
  payload_json jsonb,
  payload      jsonb,
  ts           timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.trips(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  truck_id uuid,
  status text,
  planned_load_window_start  timestamptz,
  planned_unload_window_end  timestamptz,
  confirmed_at timestamptz,
  updated_at timestamptz DEFAULT now(),
  price_rub_actual numeric,
  fuel_cost_rub_actual numeric,
  tolls_rub_actual numeric,
  other_costs_rub_actual numeric,
  meta jsonb
);

CREATE TABLE IF NOT EXISTS public.trip_segments(
  segment_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id      uuid,
  kind         text,     -- 'move'/'load'/'unload'/...
  a            jsonb,    -- точка A
  b            jsonb,    -- точка B
  ts_from      timestamptz,
  ts_to        timestamptz,
  distance_km  numeric,
  rate_plan    numeric,
  rate_fact    numeric
);

COMMIT;
