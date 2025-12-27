-- FoxProFlow • FIXPACK • ops.audit_events (idempotent, safe indexes)
-- file: scripts/sql/fixpacks/20251224_ops_audit_events.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Rollback: scripts/sql/fixpacks/20251224_ops_audit_events_rollback.sql

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.audit_events (
  id            bigserial   PRIMARY KEY,
  ts            timestamptz NOT NULL DEFAULT now(),
  actor         text        NOT NULL,
  action        text        NOT NULL,
  ok            boolean     NOT NULL,
  dev_order_id  bigint      NULL,
  dev_task_id   bigint      NULL,
  payload       jsonb       NULL,
  evidence_refs jsonb       NULL,
  err           text        NULL
);

-- repair path (если таблица уже существовала в старом виде)
ALTER TABLE ops.audit_events ADD COLUMN IF NOT EXISTS dev_order_id  bigint;
ALTER TABLE ops.audit_events ADD COLUMN IF NOT EXISTS dev_task_id   bigint;
ALTER TABLE ops.audit_events ADD COLUMN IF NOT EXISTS payload       jsonb;
ALTER TABLE ops.audit_events ADD COLUMN IF NOT EXISTS evidence_refs jsonb;
ALTER TABLE ops.audit_events ADD COLUMN IF NOT EXISTS err           text;

COMMIT;

-- Indexes (CONCURRENTLY must be outside transaction)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_ts
  ON ops.audit_events (ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_actor_ts
  ON ops.audit_events (actor, ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_action_ts
  ON ops.audit_events (action, ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_order_ts
  ON ops.audit_events (dev_order_id, ts DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_task_ts
  ON ops.audit_events (dev_task_id, ts DESC);

-- быстрый доступ к фейлам
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ops_audit_events_not_ok_ts
  ON ops.audit_events (ts DESC)
  WHERE ok IS NOT TRUE;
