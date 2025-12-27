-- refresh_od_stats.sql — безопасный рефреш витрин OD (CONCURRENTLY при наличии индексов)
-- Выполняется отдельно от создания (индексация уже есть)

-- ВАЖНО: REFRESH CONCURRENTLY требует уникального индекса на MV (мы его создали выше)
-- Если таблица пустая при первом запуске — это нормально.

-- od_arrival_stats_mv
DO $$
BEGIN
  IF to_regclass('public.od_arrival_stats_mv') IS NOT NULL THEN
    BEGIN
      EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY public.od_arrival_stats_mv';
    EXCEPTION WHEN OTHERS THEN
      -- fallback без CONCURRENTLY (если уникальный индекс недоступен)
      EXECUTE 'REFRESH MATERIALIZED VIEW public.od_arrival_stats_mv';
    END;
  END IF;
END$$;

-- od_price_quantiles_mv
DO $$
BEGIN
  IF to_regclass('public.od_price_quantiles_mv') IS NOT NULL THEN
    BEGIN
      EXECUTE 'REFRESH MATERIALIZED VIEW CONCURRENTLY public.od_price_quantiles_mv';
    EXCEPTION WHEN OTHERS THEN
      EXECUTE 'REFRESH MATERIALIZED VIEW public.od_price_quantiles_mv';
    END;
  END IF;
END$$;
