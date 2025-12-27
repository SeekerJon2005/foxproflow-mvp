-- FoxProFlow • FIXPACK ROLLBACK • ops.agent_events indexes (non-destructive)
-- file: scripts/sql/fixpacks/20251224_ops_agent_events_rollback.sql
-- Notes: Drops only indexes created by fixpack. Table/data preserved.

\set ON_ERROR_STOP on
\pset pager off

DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_agent_events_level_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_agent_events_ok_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_agent_events_action_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_agent_events_agent_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_agent_events_ts;
