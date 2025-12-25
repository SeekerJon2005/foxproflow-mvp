-- FoxProFlow • FIXPACK • ops.agent_events (idempotent, safe indexes)
-- file: scripts/sql/fixpacks/20251224_ops_agent_events.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Rollback: scripts/sql/fixpacks/20251224_ops_agent_events_rollback.sql

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.agent_events (
  ts         timestamptz NOT NULL DEFAULT now(),
  agent      text        NOT NULL,
  level      text        NOT NULL,
  action     text        NOT NULL,
  payload    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  ok         boolean     NOT NULL DEFAULT true,
  latency_ms integer     NULL
);

-- repair path (если таблица уже существовала в старом виде)
ALTER TABLE ops.agent_events ADD COLUMN IF NOT EXISTS payload    jsonb;
ALTER TABLE ops.agent_events ADD COLUMN IF NOT EXISTS ok         boolean;
ALTER TABLE ops.agent_events ADD COLUMN IF NOT EXISTS latency_ms integer;

ALTER TABLE ops.agent_events ALTER COLUMN payload SET DEFAULT '{}'::jsonb;
ALTER TABLE ops.agent_events ALTER COLUMN ok      SET DEFAULT true;

COMMIT;

-- Indexes (CONCURRENTLY must be outside transaction)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_agent_events_ts
  ON ops.agent_events (ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_agent_events_agent_ts
  ON ops.agent_events (agent, ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_agent_events_action_ts
  ON ops.agent_events (action, ts DESC);

-- полезно для быстрых выборок ошибок/алёртов
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_agent_events_ok_ts
  ON ops.agent_events (ok, ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_agent_events_level_ts
  ON ops.agent_events (level, ts DESC);
