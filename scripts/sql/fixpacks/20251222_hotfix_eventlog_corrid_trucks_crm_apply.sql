-- file: scripts/sql/fixpacks/20251222_hotfix_eventlog_corrid_trucks_crm_apply.sql
-- FoxProFlow • FixPack • Hotfix: correlation_id + missing objects (public.trucks, crm.leads_trial_candidates_v)
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Stop worker task crashes due to:
--     - UndefinedColumn: event_log.correlation_id
--     - UndefinedTable: public.trucks
--     - UndefinedTable/View: crm.leads_trial_candidates_v
-- Notes:
--   - public.trucks and crm.leads_trial_candidates_v are COMPAT STUBS (minimal schema, 0 rows for view).
--   - Idempotent. Does not DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';

SELECT pg_advisory_lock(74858372);

-- =========================================================
-- 1) event_log: add correlation_id to the actual table (ops.event_log)
-- =========================================================
DO $$
BEGIN
  IF to_regclass('ops.event_log') IS NOT NULL THEN
    ALTER TABLE ops.event_log
      ADD COLUMN IF NOT EXISTS correlation_id text;

    -- optional: keep it searchable
    CREATE INDEX IF NOT EXISTS ops_event_log_correlation_id_idx
      ON ops.event_log(correlation_id);
  END IF;

  -- If some code uses public.event_log (unqualified name via search_path),
  -- add the column there too if the relation exists.
  IF to_regclass('public.event_log') IS NOT NULL THEN
    BEGIN
      EXECUTE 'ALTER TABLE public.event_log ADD COLUMN IF NOT EXISTS correlation_id text';
      EXECUTE 'CREATE INDEX IF NOT EXISTS public_event_log_correlation_id_idx ON public.event_log(correlation_id)';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'public.event_log correlation_id patch skipped: %', SQLERRM;
    END;
  END IF;
END$$;

-- =========================================================
-- 2) public.trucks: create missing object (compat stub table)
-- =========================================================
CREATE TABLE IF NOT EXISTS public.trucks (
  id           bigserial PRIMARY KEY,
  vehicle_id   bigint,
  public_id    uuid,
  external_id  text,
  name         text,
  reg_number   text,
  plate        text,
  vin          text,
  driver_name  text,
  driver_phone text,
  driver_email text,
  carrier_id   bigint,
  is_active    boolean NOT NULL DEFAULT true,
  meta         jsonb    NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS trucks_vehicle_id_idx   ON public.trucks(vehicle_id);
CREATE INDEX IF NOT EXISTS trucks_public_id_idx    ON public.trucks(public_id);
CREATE INDEX IF NOT EXISTS trucks_external_id_idx  ON public.trucks(external_id);
CREATE INDEX IF NOT EXISTS trucks_reg_number_idx   ON public.trucks(reg_number);
CREATE INDEX IF NOT EXISTS trucks_plate_idx        ON public.trucks(plate);
CREATE INDEX IF NOT EXISTS trucks_is_active_idx    ON public.trucks(is_active);

-- =========================================================
-- 3) crm.leads_trial_candidates_v: create missing schema + view (compat stub)
-- =========================================================
CREATE SCHEMA IF NOT EXISTS crm;

DO $$
BEGIN
  IF to_regclass('crm.leads_trial_candidates_v') IS NULL THEN
    EXECUTE $v$
      CREATE VIEW crm.leads_trial_candidates_v AS
      SELECT
        NULL::bigint       AS lead_id,
        NULL::uuid         AS lead_public_id,
        NULL::text         AS company_name,
        NULL::text         AS inn,
        NULL::text         AS kpp,
        NULL::text         AS contact_name,
        NULL::text         AS phone,
        NULL::text         AS email,
        NULL::text         AS city,
        NULL::text         AS region,
        NULL::text         AS source,
        NULL::text         AS utm_source,
        NULL::text         AS utm_campaign,
        NULL::numeric      AS score,
        NULL::timestamptz  AS created_at,
        NULL::timestamptz  AS updated_at,
        '{}'::jsonb        AS meta
      WHERE false
    $v$;
  END IF;
END$$;

ANALYZE ops.event_log;
ANALYZE public.trucks;

SELECT pg_advisory_unlock(74858372);
