-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\mv_freshness.sql
-- FoxProFlow — MV Freshness quick check
-- -----------------------------------------------------------
-- Быстрый срез по ключевым витринам:
--   • количество строк
--   • для freights_enriched_mv — max(created_at) как прокси «свежести»

SELECT 'freights_enriched_mv' AS mv, COUNT(*) AS rows, MAX(created_at) AS max_created
FROM public.freights_enriched_mv
UNION ALL
SELECT 'market_rates_mv', COUNT(*), NULL
FROM public.market_rates_mv
UNION ALL
SELECT 'od_arrival_stats_mv', COUNT(*), NULL
FROM public.od_arrival_stats_mv
UNION ALL
SELECT 'od_price_quantiles_mv', COUNT(*), NULL
FROM public.od_price_quantiles_mv
UNION ALL
SELECT 'vehicle_availability_mv', COUNT(*), NULL
FROM public.vehicle_availability_mv;
