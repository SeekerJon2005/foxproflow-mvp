-- FoxProFlow • FixPack • public.freights compat VIEW • CHECKS
-- file: scripts/sql/fixpacks/20251221_public_freights_compat_view_checks.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\echo '=== public.freights compat CHECKS ==='

SELECT 'public.market_history' AS obj, to_regclass('public.market_history') IS NOT NULL AS exists;
SELECT 'public.freights'       AS obj, to_regclass('public.freights')       IS NOT NULL AS exists;

SELECT n.nspname AS schemaname, c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname='freights';

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='freights'
ORDER BY ordinal_position;

-- should not error
SELECT COUNT(*) AS cnt FROM public.freights;

\echo '=== END ==='
