-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\od_quantiles_sample.sql
-- FoxProFlow — выборка квантилей rpm по паре OD
-- -----------------------------------------------------------
-- Использование в psql:
--   \set origin 'RU-MOW'
--   \set dest   'RU-SPE'
--   \i scripts/sql/od_quantiles_sample.sql

SELECT *
FROM public.od_price_quantiles_mv
WHERE loading_region  = :'origin'
  AND unloading_region = :'dest';
