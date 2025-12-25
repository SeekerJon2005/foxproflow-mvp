-- file: scripts/sql/verify/20251223_citymap_discovery.sql
-- FoxProFlow • Verify • CityMap discovery (what exists in DB)
\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

-- 1) list candidate relations by name
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','v','m')
  AND (
    c.relname ILIKE '%city%map%' OR
    c.relname ILIKE '%citymap%' OR
    c.relname ILIKE '%city%alias%' OR
    c.relname ILIKE '%citymap%alias%'
  )
ORDER BY n.nspname, c.relname;

-- 2) show columns for anything matching patterns
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE (table_name ILIKE '%city%map%' OR table_name ILIKE '%citymap%' OR table_name ILIKE '%city%alias%')
ORDER BY table_schema, table_name, ordinal_position;
