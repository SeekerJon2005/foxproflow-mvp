-- FoxProFlow • Rollback • SQL-M0 • ops.agent_events
-- file: scripts/sql/rollback/20251224_ops_agent_events_rollback.sql
-- Created: 2025-12-24
-- Created by: Архитектор Яцков Евгений Анатольевич
-- DevTask: (set real DevTask id)
-- WARNING: drops table (data loss)

\set ON_ERROR_STOP on
\pset pager off

DROP TABLE IF EXISTS ops.agent_events;
\echo 'OK: rolled back ops.agent_events (dropped)'
