-- 2025-12-12 (DEPRECATED)
-- FoxProFlow • Legacy Patch Alias • Analytics
-- file: scripts/sql/patches/20251212_analytics_devfactory_task_kpi_v2.sql
--
-- DevFactory KPI v2: витрина analytics.devfactory_task_kpi_v2 (на основе dev.dev_task)
--
-- DEPRECATED / COMPATIBILITY ONLY
--   Этот файл сохранён только как временный алиас для обратной совместимости.
--   НОВЫЕ изменения сюда не добавлять.
--
-- WHY:
--   Историческая версия patch делала:
--     DROP MATERIALIZED VIEW IF EXISTS analytics.devfactory_task_kpi_v2;
--   Это опасно: сбрасывает состояние populated/индексы и может ломать REFRESH ... CONCURRENTLY readiness.
--
-- CANONICAL SOURCE OF TRUTH:
--   scripts/sql/fixpacks/20251227_analytics_devfactory_task_kpi_v2_ddl_apply.sql
--
-- IMPORTANT:
--   По политике C-линии “истина” живёт в fixpacks/migrations/verify.
--   Этот patch больше не содержит DDL, только прокси-включение.

\set ON_ERROR_STOP on
\echo 'DEPRECATED: scripts/sql/patches/20251212_analytics_devfactory_task_kpi_v2.sql'
\echo 'Using canonical fixpack: scripts/sql/fixpacks/20251227_analytics_devfactory_task_kpi_v2_ddl_apply.sql'

\ir ../fixpacks/20251227_analytics_devfactory_task_kpi_v2_ddl_apply.sql
