-- FoxProFlow • FixPack • market_history MIN • CHECKS
-- file: scripts/sql/fixpacks/20251221_market_history_min_checks.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\echo '=== market_history MIN CHECKS ==='

SELECT to_regclass('public.market_history') IS NOT NULL AS has_market_history;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='market_history'
ORDER BY ordinal_position;

SELECT count(*) AS rows_cnt FROM public.market_history;

\echo '=== END ==='
