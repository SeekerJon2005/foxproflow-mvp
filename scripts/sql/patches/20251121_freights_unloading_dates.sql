-- 20251121_freights_unloading_dates.sql
-- Пересчёт unloading_date для всех фрахтов в freights_enriched_mv
-- по формуле:
--   unloading_date = loading_date
--                    + load_duration
--                    + drive_duration (distance / avg_speed)
--                    + unload_duration
--
-- Параметры берём из .env:
--   AUTOPLAN_AVG_SPEED_KMH = 55
--   LOAD_DURATION_H        = 2
--   UNLOAD_DURATION_H      = 2

DO $$
DECLARE
    v_speed_kmh       numeric := 55;  -- AUTOPLAN_AVG_SPEED_KMH
    v_load_h          numeric := 2;   -- LOAD_DURATION_H
    v_unload_h        numeric := 2;   -- UNLOAD_DURATION_H
BEGIN
    RAISE NOTICE 'Recalculating unloading_date: speed=%, load_h=%, unload_h=%',
        v_speed_kmh, v_load_h, v_unload_h;

    UPDATE public.freights_enriched_mv AS fe
       SET unloading_date =
           fe.loading_date
           + (v_load_h || ' hours')::interval
           + ((fe.distance / NULLIF(v_speed_kmh, 0)) || ' hours')::interval
           + (v_unload_h || ' hours')::interval;

    RAISE NOTICE 'Done recalculating unloading_date for % rows',
        (SELECT count(*) FROM public.freights_enriched_mv);
END $$;
