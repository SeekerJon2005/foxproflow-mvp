-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\od_arrival_prob_sample.sql
-- FoxProFlow — почасовая вероятность появления груза по паре OD
-- -----------------------------------------------------------
-- Использование в psql:
--   \set origin 'RU-MOW'
--   \set dest   'RU-SPE'
--   \i scripts/sql/od_arrival_prob_sample.sql

SELECT
  hour_of_day,
  n,
  p_appear
FROM public.od_arrival_stats_mv
WHERE loading_region  = :'origin'
  AND unloading_region = :'dest'
ORDER BY hour_of_day;
