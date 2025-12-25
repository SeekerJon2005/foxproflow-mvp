-- FoxProFlow • VERIFY • Gate M0 DB Contract (core objects must exist)
-- file: scripts/sql/verify/20251225_gate_m0_db_contract.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes: READ-ONLY. Fail-fast. Prints explicit OK marker on success.

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE
  missing text[] := ARRAY[]::text[];
BEGIN
  -- DevFactory core
  IF to_regclass('dev.dev_task') IS NULL THEN
    missing := array_append(missing, 'dev.dev_task');
  END IF;

  -- Ops / Evidence (важно для наблюдаемости и доказуемости)
  IF to_regclass('ops.event_log') IS NULL THEN
    missing := array_append(missing, 'ops.event_log');
  END IF;

  IF to_regclass('ops.agent_events') IS NULL THEN
    missing := array_append(missing, 'ops.agent_events');
  END IF;

  -- FlowSec minimal skeleton (deny-by-default needs these anchors)
  IF to_regclass('sec.roles') IS NULL THEN
    missing := array_append(missing, 'sec.roles');
  END IF;

  IF to_regclass('sec.policies') IS NULL THEN
    missing := array_append(missing, 'sec.policies');
  END IF;

  IF to_regclass('sec.subject_roles') IS NULL THEN
    missing := array_append(missing, 'sec.subject_roles');
  END IF;

  IF to_regclass('sec.role_policy_bindings') IS NULL THEN
    missing := array_append(missing, 'sec.role_policy_bindings');
  END IF;

  IF array_length(missing, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'MISSING_DB_OBJECTS: %', array_to_string(missing, ', ');
  END IF;
END $$;

\echo OK: Gate M0 DB contract passed
