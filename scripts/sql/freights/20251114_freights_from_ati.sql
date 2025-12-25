-- 2025-11-14 — FoxProFlow: просмотровый слой для ATI-сыра (freights_ati_raw)
--
-- Задача этого представления:
--   • разложить payload из public.freights_ati_raw по колонкам;
--   • НИЧЕГО не писать в public.freights (Только чтение);
--   • подготовить почву для дальнейшего ETL в основной слой freights.
--
-- ВАЖНО:
--   • loading_region / unloading_region здесь пока НЕ считаются;
--     поля с городами отдаются как *_city_raw / *_point_0, далее будут
--     нормализованы через city_map/region_centroids.
--   • Все числовые текстовые поля (weight/volume/price/distance) парсим
--     безопасно: сначала выкидываем всё, кроме цифр и точки, затем
--     NULLIF(..., '')::numeric. Строки вроде 'N/A' → NULL.

CREATE OR REPLACE VIEW public.freights_from_ati_v AS
SELECT
    r.id                         AS ati_row_id,      -- surrogate key из freights_ati_raw
    r.src                        AS src,             -- обычно 'ati_html'
    r.external_id                AS external_id,     -- raw.id из ATI (UUID строки)

    -- Нормализованные поля верхнего уровня (как их отдаёт парсер)
    (r.payload->>'loading_city')     AS loading_city_raw,
    (r.payload->>'unloading_city')   AS unloading_city_raw,
    (r.payload->>'cargo')            AS cargo_norm,
    (r.payload->>'body_type')        AS body_type_norm,
    (r.payload->>'loading_date')     AS loading_date_norm,   -- текст типа "готов 13-14 нояб."

    -- Безопасный парсинг чисел: выкидываем всё, кроме [0-9.] и приводим к numeric
    NULLIF(
        regexp_replace(r.payload->>'weight',  '[^0-9\.]', '', 'g'),
        ''
    )::numeric                    AS weight_ton,     -- тоннаж (тонны)

    NULLIF(
        regexp_replace(r.payload->>'volume',  '[^0-9\.]', '', 'g'),
        ''
    )::numeric                    AS volume_m3,      -- объём (м³)

    NULLIF(
        regexp_replace(r.payload->>'price',   '[^0-9\.]', '', 'g'),
        ''
    )::numeric                    AS price_rub,      -- цена как число (руб)

    -- Сырые поля из вложенного блока raw (как на сайте ATI)
    (r.payload->'raw'->>'loading_date_text')   AS loading_date_text,
    (r.payload->'raw'->>'body_type_text')      AS body_type_text,
    (r.payload->'raw'->>'loading_method_text') AS loading_method_text,
    (r.payload->'raw'->>'possible_reload')     AS possible_reload_text,

    NULLIF(
        regexp_replace(r.payload->'raw'->>'distance', '[^0-9\.]', '', 'g'),
        ''
    )::numeric                    AS distance_km,    -- дистанция, км

    (r.payload->'raw'->>'cargo')               AS cargo_raw,
    (r.payload->'raw'->>'weight_text')         AS weight_text,
    (r.payload->'raw'->>'volume_text')         AS volume_text,

    -- Цены с/без НДС в исходном виде (строки вида "95 000 руб")
    (r.payload->'raw'->'prices'->>'без_НДС')   AS price_no_vat_text,
    (r.payload->'raw'->'prices'->>'с_НДС')     AS price_with_vat_text,

    -- Первые точки погрузки/выгрузки как есть (для дальнейшей нормализации через city_map)
    (r.payload->'raw'->'loading_points'->>0)   AS loading_point_0,
    (r.payload->'raw'->'unloading_points'->>0) AS unloading_point_0,

    -- Служебные поля
    r.parsed_at,
    r.created_at,
    r.payload                                  -- полный JSONB на всякий случай
FROM public.freights_ati_raw AS r
WHERE r.parsed_at::date >= (CURRENT_DATE - INTERVAL '3 days');

COMMENT ON VIEW public.freights_from_ati_v IS
'Early-stage view: раскладывает payload из freights_ati_raw по колонкам для дальнейшего ETL в public.freights. Не пишет данных, только чтение.';
