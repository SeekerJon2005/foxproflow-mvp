-- FoxProFlow • Verify • List databases
-- file: scripts/sql/verify/20251221_list_databases.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT
  datname,
  pg_get_userbyid(datdba) AS owner,
  pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC, datname;
