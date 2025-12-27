-- od_arrival_stats_mv.sql — вероятность появления грузов по OD × час × кузов × тоннаж
-- Устойчива к отсутствию отдельных колонок в freights_enriched_mv:
-- поля читаются через to_jsonb(row)->>'key' с фолбэками и безопасным парсингом веса.

DROP MATERIALIZED VIEW IF EXISTS public.od_arrival_stats_mv;

CREATE MATERIALIZED VIEW public.od_arrival_stats_mv AS
WITH raw AS (
  SELECT
    /* Регион погрузки/выгрузки: поддерживаем альтернативные ключи */
    COALESCE(to_jsonb(f)->>'loading_region',  to_jsonb(f)->>'origin_region')   AS loading_region,
    COALESCE(to_jsonb(f)->>'unloading_region',to_jsonb(f)->>'dest_region')     AS unloading_region,

    /* Тип кузова: если ключа нет/пусто — 'unknown' */
    COALESCE(NULLIF(to_jsonb(f)->>'body_type',''),'unknown')                    AS body_type,

    /* Безопасный парсинг веса; допускаем строку/NULL; единицы: кг или т */
    CASE
      WHEN (to_jsonb(f)->>'weight') ~ '^[0-9]+(\.[0-9]+)?$'
        THEN (to_jsonb(f)->>'weight')::numeric
      ELSE NULL
    END                                                                         AS weight_num,

    /* Часовой бакет: loading_date -> load_window_start -> now() */
    date_trunc('hour',
      COALESCE(
        (to_jsonb(f)->>'loading_date')::timestamptz,
        (to_jsonb(f)->>'load_window_start')::timestamptz,
        now()
      )
    )                                                                           AS hour_bucket
  FROM public.freights_enriched_mv f
  WHERE COALESCE(to_jsonb(f)->>'loading_region', to_jsonb(f)->>'origin_region') IS NOT NULL
),
base AS (
  SELECT
    loading_region,
    unloading_region,
    body_type,

    /* Тоннажные классы: вес >1000 считаем в кг и переводим в т */
    CASE
      WHEN weight_num IS NULL THEN 'unknown'
      WHEN (CASE WHEN weight_num > 1000 THEN weight_num/1000.0 ELSE weight_num END) >= 20 THEN '20t'
      WHEN (CASE WHEN weight_num > 1000 THEN weight_num/1000.0 ELSE weight_num END) >= 10 THEN '10t'
      WHEN (CASE WHEN weight_num > 1000 THEN weight_num/1000.0 ELSE weight_num END) >= 5  THEN '5t'
      ELSE '1.5t'
    END AS tonnage_class,

    hour_bucket
  FROM raw
),
agg AS (
  SELECT
    loading_region, unloading_region, body_type, tonnage_class,
    EXTRACT(HOUR FROM hour_bucket)::int AS hour_of_day,
    COUNT(*) AS n
  FROM base
  GROUP BY 1,2,3,4,5
),
norm AS (
  /* Нормируем внутри (origin, body, tonnage, hour) — распределение по направлениям */
  SELECT
    loading_region, unloading_region, body_type, tonnage_class, hour_of_day, n,
    SUM(n) OVER (PARTITION BY loading_region, body_type, tonnage_class, hour_of_day) AS total_hour
  FROM agg
)
SELECT
  loading_region, unloading_region, body_type, tonnage_class, hour_of_day, n,
  CASE WHEN total_hour > 0 THEN n::numeric / total_hour ELSE 0 END AS p_appear
FROM norm
WITH NO DATA;

-- Индексы: уникальный (для REFRESH CONCURRENTLY) + btree под фильтры
CREATE UNIQUE INDEX IF NOT EXISTS ux_od_arrival_stats_unique
  ON public.od_arrival_stats_mv (loading_region, unloading_region, body_type, tonnage_class, hour_of_day);

CREATE INDEX IF NOT EXISTS od_arrival_stats_idx
  ON public.od_arrival_stats_mv (loading_region, unloading_region, hour_of_day);
