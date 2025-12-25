-- 2025-11-15 — FoxProFlow
-- Нормализация цены и расстояния для фрахтов + OD-кэш (упрощённая версия без market_rates_mv)

-- Чистим предыдущие артефакты
DROP VIEW IF EXISTS public.od_distance_view;
DROP MATERIALIZED VIEW IF EXISTS public.freights_price_distance_norm_mv;
DROP TABLE IF EXISTS public.od_distance_cache;

-- A) Материализованная витрина: freights_price_distance_norm_mv
--    Берём сырые поля из freights_enriched_mv и приводим к:
--      • price_rub_final      — итоговая цена (пока считаем, что всё в рублях);
--      • distance_km_guess    — оценка дистанции;
--      • vat_norm / payment_terms — ярлыки НДС и условий оплаты.

CREATE MATERIALIZED VIEW public.freights_price_distance_norm_mv AS
WITH f AS (
  SELECT * FROM public.freights_enriched_mv
),
price_raw AS (
  SELECT
    (to_jsonb(f)->>'source_uid')               AS source_uid,
    (to_jsonb(f)->>'loading_region')           AS origin_region,
    (to_jsonb(f)->>'unloading_region')         AS dest_region,

    -- кандидаты цены
    NULLIF((to_jsonb(f)->>'revenue_rub')::numeric,0)  AS revenue_rub,
    NULLIF((to_jsonb(f)->>'price_rub')::numeric,0)    AS price_rub,
    NULLIF((to_jsonb(f)->>'bid_rub')::numeric,0)      AS bid_rub,
    NULLIF((to_jsonb(f)->>'amount_rub')::numeric,0)   AS amount_rub,
    NULLIF((to_jsonb(f)->>'sum_rub')::numeric,0)      AS sum_rub,
    NULLIF((to_jsonb(f)->>'price')::numeric,0)        AS price_raw,
    NULLIF((to_jsonb(f)->>'amount')::numeric,0)       AS amount_raw,
    NULLIF((to_jsonb(f)->>'sum')::numeric,0)          AS sum_raw,
    UPPER(NULLIF(TRIM(to_jsonb(f)->>'currency'),''))  AS currency_raw,

    -- кандидаты дистанции
    NULLIF((to_jsonb(f)->>'distance')::numeric,0)     AS dist1,
    NULLIF((to_jsonb(f)->>'od_km')::numeric,0)        AS dist2,
    NULLIF((to_jsonb(f)->>'distance_km')::numeric,0)  AS dist3,
    NULLIF((to_jsonb(f)->>'km')::numeric,0)           AS dist4,
    NULLIF((to_jsonb(f)->>'route_km')::numeric,0)     AS dist5,
    NULLIF((to_jsonb(f)->>'len_km')::numeric,0)       AS dist6,

    -- ярлыки
    (to_jsonb(f)->>'vat')                      AS vat_label,
    (to_jsonb(f)->>'nds')                      AS nds_label,
    (to_jsonb(f)->>'payment_terms')            AS payment_terms
  FROM f
),
dist_norm AS (
  SELECT *,
    COALESCE(dist1,dist2,dist3,dist4,dist5,dist6) AS distance_km_guess
  FROM price_raw
),
price_pref AS (
  SELECT *,
    -- приоритет цены: сначала явные рублёвые поля
    COALESCE(revenue_rub, price_rub, bid_rub, amount_rub, sum_rub) AS price_rub_first,
    COALESCE(price_raw, amount_raw, sum_raw) AS price_num_raw
  FROM dist_norm
),
enriched AS (
  SELECT
    p.*,
    COALESCE(p.currency_raw,'RUB') AS currency_guess
  FROM price_pref p
)
SELECT
  source_uid,
  origin_region,
  dest_region,
  distance_km_guess,

  CASE
    WHEN price_rub_first IS NOT NULL THEN price_rub_first
    WHEN price_num_raw  IS NOT NULL THEN price_num_raw  -- считаем уже рублями
    ELSE NULL
  END AS price_rub_final,

  CASE
    WHEN price_rub_first IS NOT NULL THEN 'rub_col'
    WHEN price_num_raw  IS NOT NULL THEN 'raw_no_rate'
    ELSE 'missing'
  END AS price_source,

  CASE
    WHEN distance_km_guess IS NOT NULL THEN 'fe_mv'
    ELSE 'missing'
  END AS distance_source,

  currency_guess,

  -- ярлык НДС: грубая типизация
  CASE
    WHEN vat_label ILIKE '%20%' OR nds_label ILIKE '%20%' THEN 'vat_20'
    WHEN vat_label ILIKE '%без%' OR nds_label ILIKE '%без%' THEN 'no_vat'
    WHEN vat_label IS NOT NULL OR nds_label IS NOT NULL THEN 'vat_other'
    ELSE 'vat_unknown'
  END AS vat_norm,

  payment_terms
FROM enriched
WITH NO DATA;

-- Индексы для быстрых выборок
CREATE INDEX IF NOT EXISTS fpdmv_od_idx
  ON public.freights_price_distance_norm_mv (origin_region, dest_region);

CREATE INDEX IF NOT EXISTS fpdmv_price_idx
  ON public.freights_price_distance_norm_mv (price_rub_final);

CREATE INDEX IF NOT EXISTS fpdmv_dist_idx
  ON public.freights_price_distance_norm_mv (distance_km_guess);

-- Первый REFRESH (может занять время на большом объёме)
REFRESH MATERIALIZED VIEW public.freights_price_distance_norm_mv;

-- B) Постоянная «книга расстояний» (OD-кэш)

CREATE TABLE public.od_distance_cache (
  id              bigserial PRIMARY KEY,
  origin_region   text NOT NULL,
  dest_region     text NOT NULL,
  mode            text NOT NULL DEFAULT 'truck', -- 'truck'|'car' и т.п.
  distance_km     numeric,       -- нормализованная дистанция
  drive_seconds   integer,       -- оценка времени пути
  polyline        text,          -- опционально, для карты
  source          text,          -- 'fe_mv'|'osrm'|'valhalla'|'haversine'
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (origin_region, dest_region, mode)
);

CREATE INDEX odc_od_idx
  ON public.od_distance_cache (origin_region, dest_region, mode);

-- Первичное заполнение OD-кэша напрямую из freights_enriched_mv
-- 1) тащим регионы и дистанцию,
-- 2) фильтруем NULL/пустые регионы,
-- 3) агрегируем до одной строки на (origin_region, dest_region).

INSERT INTO public.od_distance_cache (origin_region, dest_region, mode, distance_km, source)
SELECT
  origin_region,
  dest_region,
  'truck'                         AS mode,
  MIN(distance_km)                AS distance_km,
  'fe_mv'                         AS source
FROM (
  SELECT
    UPPER(TRIM(to_jsonb(f)->>'loading_region'))   AS origin_region,
    UPPER(TRIM(to_jsonb(f)->>'unloading_region')) AS dest_region,
    COALESCE(
      NULLIF((to_jsonb(f)->>'distance')::numeric,0),
      NULLIF((to_jsonb(f)->>'od_km')::numeric,0),
      NULLIF((to_jsonb(f)->>'distance_km')::numeric,0),
      NULLIF((to_jsonb(f)->>'km')::numeric,0),
      NULLIF((to_jsonb(f)->>'route_km')::numeric,0),
      NULLIF((to_jsonb(f)->>'len_km')::numeric,0)
    ) AS distance_km
  FROM public.freights_enriched_mv f
) AS t
WHERE
  distance_km IS NOT NULL
  AND origin_region IS NOT NULL
  AND dest_region   IS NOT NULL
  AND origin_region <> ''
  AND dest_region   <> ''
GROUP BY origin_region, dest_region;

-- C) Представление «истины» расстояний (на базе OD-кэша)

CREATE OR REPLACE VIEW public.od_distance_view AS
SELECT
  origin_region,
  dest_region,
  distance_km AS distance_km_final,
  source      AS distance_source
FROM public.od_distance_cache;
