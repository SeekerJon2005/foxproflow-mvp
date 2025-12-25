-- FoxProFlow • Verify/Smoke • trip_segments.id_uuid UUID contract
-- file: scripts/sql/verify/20251223_trip_segments_uuid_shadowcol_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

DO $$
DECLARE
  full_type text;
  base_type text;
  not_null_effective boolean;
  idx_ok boolean;
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trip_segments';
  END IF;

  -- Domain-safe type check via pg_catalog
  SELECT
    format_type(a.atttypid, a.atttypmod) AS full_type,
    (CASE WHEN t.typtype='d' THEN bt.typname ELSE t.typname END) AS base_type,
    (a.attnotnull OR (t.typtype='d' AND t.typnotnull)) AS not_null_effective
  INTO full_type, base_type, not_null_effective
  FROM pg_attribute a
  JOIN pg_type t ON t.oid=a.atttypid
  LEFT JOIN pg_type bt ON bt.oid=t.typbasetype
  WHERE a.attrelid='public.trip_segments'::regclass
    AND a.attname='id_uuid'
    AND a.attnum>0 AND NOT a.attisdropped;

  IF full_type IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trip_segments.id_uuid';
  END IF;

  IF base_type <> 'uuid' THEN
    RAISE EXCEPTION 'FAILED: bad type public.trip_segments.id_uuid expected uuid, got full_type=% base_type=%', full_type, base_type;
  END IF;

  IF NOT not_null_effective THEN
    RAISE EXCEPTION 'FAILED: public.trip_segments.id_uuid must be NOT NULL';
  END IF;

  -- Unique index is recommended: WARN only (do not fail CP1)
  SELECT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname='public'
      AND tablename='trip_segments'
      AND indexname='ux_trip_segments_id_uuid'
  ) INTO idx_ok;

  IF NOT idx_ok THEN
    RAISE NOTICE 'WARN: unique index ux_trip_segments_id_uuid not found (performance/uniqueness risk)';
  END IF;
END $$;

SELECT 'PASS: public.trip_segments.id_uuid is uuid and not null' AS pass;
