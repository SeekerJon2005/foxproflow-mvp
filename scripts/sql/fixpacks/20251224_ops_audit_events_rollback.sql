-- FoxProFlow • FIXPACK ROLLBACK • ops.audit_events indexes (non-destructive)
-- file: scripts/sql/fixpacks/20251224_ops_audit_events_rollback.sql
-- Notes: Drops only indexes created by fixpack. Table/data preserved.

\set ON_ERROR_STOP on
\pset pager off

DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_not_ok_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_task_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_order_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_action_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_actor_ts;
DROP INDEX CONCURRENTLY IF EXISTS ops.ix_ops_audit_events_ts;
