-- 2025-11-04 — SMOKE seed: несколько будущих грузов (idempotent)
-- Цель:
--   • добавить несколько тестовых "будущих" фрахтов в public.freights;
--   • не дублировать их при повторном запуске (ON CONFLICT (source_uid) DO NOTHING);
--   • использовать source_uid как канонический ключ груза.
--
-- Требования к схеме:
--   • в public.freights есть UNIQUE (source_uid);
--   • поля, используемые ниже, существуют и совместимы по типам.

WITH s AS (
  SELECT NOW() AS now
)
INSERT INTO public.freights(
  source, source_uid,
  loading_region, unloading_region,
  loading_date,  unloading_date,
  distance, revenue_rub, body_type, weight, parsed_at, payload
)
SELECT *
FROM (
  SELECT
    'SMOKE'::text                              AS source,
    'SMK-MOW-SPE-01'::text                     AS source_uid,
    'RU-MOW'::text                             AS loading_region,
    'RU-SPE'::text                             AS unloading_region,
    (SELECT now FROM s) + interval '18 hours'  AS loading_date,
    (SELECT now FROM s) + interval '30 hours'  AS unloading_date,
    700::numeric                               AS distance,
    120000::numeric                            AS revenue_rub,
    'TENT'::text                               AS body_type,
    10000::numeric                             AS weight,
    (SELECT now FROM s)                        AS parsed_at,
    jsonb_build_object(
      'note','smoke_seed','distance_km','700','price','120000'
    )::jsonb                                   AS payload

  UNION ALL

  SELECT
    'SMOKE'::text                              AS source,
    'SMK-MOW-VLA-01'::text                     AS source_uid,
    'RU-MOW'::text                             AS loading_region,
    'RU-VLA'::text                             AS unloading_region,
    (SELECT now FROM s) + interval '8 hours'   AS loading_date,
    (SELECT now FROM s) + interval '16 hours'  AS unloading_date,
    200::numeric                               AS distance,
    40000::numeric                             AS revenue_rub,
    'TENT'::text                               AS body_type,
    8000::numeric                              AS weight,
    (SELECT now FROM s)                        AS parsed_at,
    jsonb_build_object(
      'note','smoke_seed','distance_km','200','price','40000'
    )::jsonb                                   AS payload

  UNION ALL

  SELECT
    'SMOKE'::text                              AS source,
    'SMK-SPE-VLG-01'::text                     AS source_uid,
    'RU-SPE'::text                             AS loading_region,
    'RU-VLG'::text                             AS unloading_region,
    (SELECT now FROM s) + interval '20 hours'  AS loading_date,
    (SELECT now FROM s) + interval '30 hours'  AS unloading_date,
    650::numeric                               AS distance,
    90000::numeric                             AS revenue_rub,
    'REF'::text                                AS body_type,
    12000::numeric                             AS weight,
    (SELECT now FROM s)                        AS parsed_at,
    jsonb_build_object(
      'note','smoke_seed','distance_km','650','price','90000'
    )::jsonb                                   AS payload
) AS q
ON CONFLICT (source_uid) DO NOTHING;
