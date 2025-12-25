-- FoxProFlow • FixPack • SQL-M0 • ops.agent_events
-- file: scripts/sql/fixpacks/20251224_ops_agent_events_apply.sql
-- Created: 2025-12-24
-- Created by: Архитектор Яцков Евгений Анатольевич
-- DevTask: (set real DevTask id)
-- Purpose:
--   Minimal contract for agent event logging:
--     (ts, agent, level, action, payload, ok, latency_ms)
-- Idempotent: yes
-- Rollback: scripts/sql/rollback/20251224_ops_agent_events_rollback.sql

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '5min';

-- One-writer safety
SELECT pg_advisory_lock(74858390);

CREATE SCHEMA IF NOT EXISTS ops;

-- Create table if missing
CREATE TABLE IF NOT EXISTS ops.agent_events (
  ts          timestamptz NOT NULL DEFAULT now(),
  agent       text        NOT NULL,
  level       text        NOT NULL,
  action      text        NOT NULL,
  payload     jsonb       NOT NULL DEFAULT '{}'::jsonb,
  ok          boolean     NOT NULL DEFAULT true,
  latency_ms  integer
);

-- If table existed with drift, add missing columns (idempotent)
ALTER TABLE ops.agent_events
  ADD COLUMN IF NOT EXISTS ts         timestamptz,
  ADD COLUMN IF NOT EXISTS agent      text,
  ADD COLUMN IF NOT EXISTS level      text,
  ADD COLUMN IF NOT EXISTS action     text,
  ADD COLUMN IF NOT EXISTS payload    jsonb,
  ADD COLUMN IF NOT EXISTS ok         boolean,
  ADD COLUMN IF NOT EXISTS latency_ms integer;

-- Defaults (safe + idempotent)
ALTER TABLE ops.agent_events ALTER COLUMN ts SET DEFAULT now();
ALTER TABLE ops.agent_events ALTER COLUMN payload SET DEFAULT '{}'::jsonb;
ALTER TABLE ops.agent_events ALTER COLUMN ok SET DEFAULT true;

-- Helpful indexes
CREATE INDEX IF NOT EXISTS ix_agent_events_ts
  ON ops.agent_events (ts);

CREATE INDEX IF NOT EXISTS ix_agent_events_agent_ts
  ON ops.agent_events (agent, ts DESC);

CREATE INDEX IF NOT EXISTS ix_agent_events_action_ts
  ON ops.agent_events (action, ts DESC);

CREATE INDEX IF NOT EXISTS ix_agent_events_ok_ts
  ON ops.agent_events (ok, ts DESC);

COMMENT ON TABLE ops.agent_events IS
  'FoxProFlow ops: agent events log (SQL-M0 minimal contract).';

SELECT pg_advisory_unlock(74858390);

\echo 'OK: applied ops.agent_events'
