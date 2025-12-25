BEGIN;

-- Берём пачку свежих, однозначных предложений
WITH c AS (
  SELECT
    place_key,
    region_guess,
    samples,
    region_variants,
    fn_norm_key(place_key) AS norm_key
  FROM ops.citymap_suggest
  WHERE used = false
    AND region_variants = 1
    AND samples >= 20
    AND place_key IS NOT NULL
    AND region_guess IS NOT NULL
  ORDER BY samples DESC
  LIMIT 500
),

-- Вставляем города, которых ещё нет в city_map (по norm_key+region)
ins AS (
  INSERT INTO public.city_map AS cm (name, region, norm_key, source, precision)
  SELECT
    btrim(c.place_key)    AS name,
    btrim(c.region_guess) AS region,
    c.norm_key,
    'suggest'             AS source,
    'locality'            AS precision
  FROM c
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.city_map cm2
    WHERE cm2.norm_key = c.norm_key
      AND cm2.region   = c.region_guess
  )
  RETURNING norm_key, region
),

-- Обновляем region там, где он пустой, но город уже есть (по norm_key)
upd AS (
  UPDATE public.city_map cm
  SET region     = c.region_guess,
      updated_at = now()
  FROM c
  WHERE
    cm.norm_key = c.norm_key
    AND (cm.region IS NULL OR cm.region = '')
    AND NOT EXISTS (
      SELECT 1
      FROM ins
      WHERE ins.norm_key = c.norm_key
        AND ins.region   = c.region_guess
    )
  RETURNING cm.norm_key
)

-- Помечаем использованные предложения
UPDATE ops.citymap_suggest s
SET used = true
FROM c
WHERE s.place_key    = c.place_key
  AND s.region_guess = c.region_guess;

COMMIT;
