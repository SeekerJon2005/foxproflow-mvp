-- FoxProFlow • Verify • DB Inventory
-- file: scripts/sql/verify/20251221_db_inventory.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Быстро понять, "та ли БД" и есть ли базовая схема.

\set ON_ERROR_STOP on
\pset pager off

SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  inet_server_addr() AS server_addr,
  inet_server_port() AS server_port,
  version() AS pg_version;

SHOW search_path;

-- Схемы (кроме системных)
SELECT nspname AS schema
FROM pg_namespace
WHERE nspname NOT IN ('pg_catalog','information_schema')
ORDER BY 1;

-- Кол-во таблиц по схемам
SELECT schemaname, count(*) AS tables_cnt
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog','information_schema')
GROUP BY 1
ORDER BY 1;

-- Топ-100 таблиц (на глаз)
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY schemaname, tablename
LIMIT 100;

-- Ищем "trips/loads/segments" по всем схемам (на случай нестандартной схемы)
SELECT schemaname, tablename
FROM pg_tables
WHERE tablename ILIKE '%trip%'
   OR tablename ILIKE '%load%'
   OR tablename ILIKE '%segment%'
ORDER BY 1,2;

-- Частые таблицы миграций (если используете alembic/свои миграции)
SELECT to_regclass('public.alembic_version') AS alembic_version_tbl;
SELECT to_regclass('public.schema_migrations') AS schema_migrations_tbl;

-- Если alembic_version есть — покажем содержимое
DO $$
BEGIN
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    RAISE NOTICE 'alembic_version exists';
  END IF;
END$$;

-- Базовые объекты CP1 (ожидаемые)
SELECT
  to_regclass('public.trips') AS public_trips,
  to_regclass('public.trip_segments') AS public_trip_segments,
  to_regclass('public.loads') AS public_loads;
