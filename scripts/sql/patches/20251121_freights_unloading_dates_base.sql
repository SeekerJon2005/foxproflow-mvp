-- 20251121_freights_unloading_dates_base.sql
-- Цель: рассчитать unloading_date в базовой таблице freights (или market.freights_norm)
-- и после этого освежить материализованный вид freights_enriched_mv.

DO $$
DECLARE
    v_speed_kmh       numeric := 55;  -- AUTOPLAN_AVG_SPEED_KMH
    v_load_h          numeric := 2;   -- LOAD_DURATION_H
    v_unload_h        numeric := 2;   -- UNLOAD_DURATION_H
BEGIN
    RAISE NOTICE 'Recalculating unloading_date in market.freights_norm: speed=%, load_h=%, unload_h=%',
        v_speed_kmh, v_load_h, v_unload_h;

    -- 1. Гарантируем наличие колонки unloading_date в base-таблице.
    ALTER TABLE market.freights_norm
        ADD COLUMN IF NOT EXISTS unloading_date timestamptz;

    -- 2. Рассчитываем unloading_date ТОЛЬКО там, где есть и loading_date, и distance.
    UPDATE market.freights_norm AS fn
       SET unloading_date =
           fn.loading_date
           + (v_load_h || ' hours')::interval
           + ((fn.distance / NULLIF(v_speed_kmh, 0)) || ' hours')::interval
           + (v_unload_h || ' hours')::interval
     WHERE fn.loading_date IS NOT NULL
       AND fn.distance      IS NOT NULL;

    RAISE NOTICE 'Base unloading_date recalculated for % rows',
        (SELECT count(*) FROM market.freights_norm WHERE unloading_date IS NOT NULL);

    -- 3. Обновляем витрину freights_enriched_mv, чтобы она подтянула свежие unloading_date.
    -- Если у тебя уже есть функция mv.refresh.freights_enriched(), используем её.
    PERFORM mv.refresh.freights_enriched();
    RAISE NOTICE 'freights_enriched_mv refreshed';
END $$;
