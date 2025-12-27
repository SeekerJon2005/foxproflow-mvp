-- FoxProFlow • Verify • Schema snapshot (core tables)
-- file: scripts/sql/verify/20251221_schema_snapshot_core.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

-- Core tables columns
SELECT table_name, ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('vehicles','loads','trips','trip_segments')
ORDER BY table_name, ordinal_position;

-- Core tables indexes
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND tablename IN ('vehicles','loads','trips','trip_segments')
ORDER BY tablename, indexname;
