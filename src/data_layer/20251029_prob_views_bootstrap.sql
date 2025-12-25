-- 2025-10-29 — Prob/Enrichment Views Bootstrap (safe/idempotent)
-- Цель: нормализовать регионы к ISO-коду, вычислить rpm, поднять freights_enriched_mv,
--       сохранить контракт колонок, которые используют market_rates_mv / od_*.

BEGIN;

-- 1) Утилиты нормализации
CREATE OR REPLACE FUNCTION public.ff_nullish(t text)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
           WHEN t IS NULL THEN TRUE
           WHEN btrim(upper(t)) IN ('Н/Д','N/A','NA','N\\A','-','—','NONE','NULL','N.D.') THEN TRUE
           WHEN btrim(t) = '' THEN TRUE
           ELSE FALSE
         END
$$;

CREATE OR REPLACE FUNCTION public.ff_ru_simplify(s text)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE x text;
BEGIN
  IF s IS NULL THEN RETURN NULL; END IF;
  x := upper(btrim(s));
  x := replace(x, 'Ё', 'Е');
  x := regexp_replace(x, '\.', '', 'g');
  x := regexp_replace(x, '\s+', ' ', 'g');
  x := regexp_replace(x, '\yГ\.?\s', '', 'g');      -- «г. »
  x := regexp_replace(x, '\yГОРОД\s', '', 'g');     -- «город »
  x := regexp_replace(x, '\sОБЛАСТЬ\y', '', 'g');   -- « область»
  x := regexp_replace(x, '\sКРАЙ\y', '', 'g');      -- « край»
  x := btrim(x);
  RETURN x;
END$$;

CREATE TABLE IF NOT EXISTS public.city_to_region_map(
  name        text PRIMARY KEY,     -- каноническая форма (UPPER, без «область/край»)
  region_code text NOT NULL         -- ISO-код, например RU-MOW
);

CREATE OR REPLACE FUNCTION public.ff_region_by_text(txt text)
RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE t text; code text;
BEGIN
  IF txt IS NULL OR btrim(txt) = '' THEN
    RETURN NULL;
  END IF;

  t := public.ff_ru_simplify(txt);

  -- Прямое вхождение ISO
  IF t ~ 'RU-[A-Z0-9]{3}' THEN
    RETURN regexp_replace(t, '.*?(RU-[A-Z0-9]{3}).*', '\1');
  END IF;

  -- По карте соответствий
  SELECT m.region_code INTO code
  FROM public.city_to_region_map m
  WHERE public.ff_ru_simplify(m.name) = t
  LIMIT 1;

  RETURN code;  -- может быть NULL
END$$;

-- 2) Зависимые витрины временно гасим, чтобы не держали зависимость (пересоздадим ниже)
DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_price_quantiles_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_arrival_stats_mv;

-- 3) Пересборка основной витрины рынка
DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv;

CREATE MATERIALIZED VIEW public.freights_enriched_mv AS
SELECT
  f.source,
  f.source_uid,

  -- нормализованные к ISO коды
  public.ff_region_by_text(f.loading_region)   AS loading_region,
  public.ff_region_by_text(f.unloading_region) AS unloading_region,

  -- даты из инжеста
  f.loading_date,
  f.unloading_date,

  -- числовые поля
  f.distance::numeric        AS distance,
  f.revenue_rub::numeric     AS revenue_rub,
  f.body_type,
  f.weight::numeric          AS weight,

  -- rpm (руб/км)
  CASE WHEN f.revenue_rub IS NOT NULL AND f.distance IS NOT NULL AND f.distance > 0
       THEN (f.revenue_rub::numeric / f.distance::numeric)
       ELSE NULL::numeric
  END                        AS rpm,

  -- совместимость
  f.parsed_at                AS created_at,
  f.payload
FROM public.freights f
WITH NO DATA;

-- 4) Индексы под типовые срезы
CREATE INDEX IF NOT EXISTS ix_fe_loading_date
  ON public.freights_enriched_mv(loading_date);
CREATE INDEX IF NOT EXISTS ix_fe_regions
  ON public.freights_enriched_mv(loading_region, unloading_region);
CREATE INDEX IF NOT EXISTS ix_fe_rpm
  ON public.freights_enriched_mv(rpm);

COMMIT;
