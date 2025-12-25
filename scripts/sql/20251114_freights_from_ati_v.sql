-- 20251114_freights_from_ati_v.sql
-- Плоская витрина для ATI-грузов из public.freights_ati_raw.
-- Источник: freights_ati_raw(src, external_id, payload jsonb, parsed_at).
--
-- Задачи:
--   • вытащить удобочитаемые поля (id, маршрут, цена, вес, объём, дата);
--   • очистить числовые значения от мусора;
--   • подготовить основу для последующей геокодированной витрины freights_from_ati_geocoded_v.

DO $$
DECLARE
  has_src boolean;
BEGIN
  -- 0) Если базовой таблицы ещё нет — миграцию просто пропускаем
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name   = 'freights_ati_raw'
  )
  INTO has_src;

  IF NOT has_src THEN
    RAISE NOTICE 'Table public.freights_ati_raw not found, skipping freights_from_ati_v migration';
    RETURN;
  END IF;

  -- 1) Создаём / обновляем витрину
  EXECUTE $view$
    CREATE OR REPLACE VIEW public.freights_from_ati_v AS
    /*
      Базовые колонки:
        • src           — источник (ati_html / ati_api и т.д.)
        • external_id   — внешний id (мы берём его из raw.id или hash при импорте)
        • parsed_at     — когда парсер увидел этот груз
        • raw_id        — дубль id из payload.raw.id (если есть)
        • title_raw     — исходный заголовок объявления (если есть)
        • loading_raw   — строка с пунктом(ами) погрузки (как есть в JSON)
        • unloading_raw — строка с пунктом(ами) выгрузки
        • loading_place_key / unloading_place_key — упрощённые ключи для city_map
        • price_raw     — исходная строка с ценой
        • price_rub     — очищенное число, numeric(14,2)
        • distance_km   — оценка расстояния, numeric(10,2), если где-то присутствует
        • weight_tons   — вес, numeric(10,3)
        • volume_m3     — объём, numeric(10,3)
        • loading_date_raw  — оригинальная строка про дату/сроки погрузки
        • loading_date_norm — грубая нормализация: пытаемся вытащить первую дату (date)
    */
    SELECT
      r.src,
      r.external_id,
      r.parsed_at,

      -- Базовый id из raw, если присутствует
      COALESCE(
        r.payload -> 'raw' ->> 'id',
        r.external_id
      ) AS raw_id,

      -- Заголовок/описание объявления
      COALESCE(
        r.payload -> 'raw' ->> 'title',
        r.payload ->> 'title'
      ) AS title_raw,

      -- Сырые поля маршрута (как строка)
      COALESCE(
        r.payload -> 'raw' ->> 'loading',
        r.payload -> 'raw' ->> 'from_city',
        r.payload -> 'raw' ->> 'from',
        r.payload ->> 'loading'
      ) AS loading_raw,

      COALESCE(
        r.payload -> 'raw' ->> 'unloading',
        r.payload -> 'raw' ->> 'to_city',
        r.payload -> 'raw' ->> 'to',
        r.payload ->> 'unloading'
      ) AS unloading_raw,

      -- Ключи для city_map: грубо чистим хвосты после запятой и пробельный мусор
      trim(
        split_part(
          COALESCE(
            r.payload -> 'raw' ->> 'loading',
            r.payload -> 'raw' ->> 'from_city',
            r.payload -> 'raw' ->> 'from',
            r.payload ->> 'loading',
            ''
          ),
          ',', 1
        )
      ) AS loading_place_key,

      trim(
        split_part(
          COALESCE(
            r.payload -> 'raw' ->> 'unloading',
            r.payload -> 'raw' ->> 'to_city',
            r.payload -> 'raw' ->> 'to',
            r.payload ->> 'unloading',
            ''
          ),
          ',', 1
        )
      ) AS unloading_place_key,

      -- Цена как сырая строка
      COALESCE(
        r.payload -> 'raw' ->> 'price_rub',
        r.payload -> 'raw' ->> 'price',
        r.payload ->> 'price_rub',
        r.payload ->> 'price'
      ) AS price_raw,

      -- Цена как число, numeric(14,2): выкидываем всё, кроме цифр, запятой и точки
      NULLIF(
        regexp_replace(
          COALESCE(
            r.payload -> 'raw' ->> 'price_rub',
            r.payload -> 'raw' ->> 'price',
            r.payload ->> 'price_rub',
            r.payload ->> 'price',
            ''
          ),
          '[^0-9\.,]+',
          '',
          'g'
        ),
        ''
      )::numeric(14,2) AS price_rub,

      -- Расстояние, если где-то лежит (km / distance / road_km и т.п.)
      NULLIF(
        regexp_replace(
          COALESCE(
            r.payload -> 'raw' ->> 'distance_km',
            r.payload -> 'raw' ->> 'distance',
            r.payload ->> 'road_km',
            r.payload ->> 'distance_km',
            r.payload ->> 'distance',
            ''
          ),
          '[^0-9\.,]+',
          '',
          'g'
        ),
        ''
      )::numeric(10,2) AS distance_km,

      -- Вес (тонны). Берём сначала уже нормализованный вес, потом текстовый.
      NULLIF(
        regexp_replace(
          COALESCE(
            r.payload -> 'raw' ->> 'weight_tons',
            r.payload -> 'raw' ->> 'weight',
            r.payload ->> 'weight_tons',
            r.payload ->> 'weight',
            ''
          ),
          '[^0-9\.,]+',
          '',
          'g'
        ),
        ''
      )::numeric(10,3) AS weight_tons,

      -- Объём (м³)
      NULLIF(
        regexp_replace(
          COALESCE(
            r.payload -> 'raw' ->> 'volume_m3',
            r.payload -> 'raw' ->> 'volume',
            r.payload ->> 'volume_m3',
            r.payload ->> 'volume',
            ''
          ),
          '[^0-9\.,]+',
          '',
          'g'
        ),
        ''
      )::numeric(10,3) AS volume_m3,

      -- Сырые строки дат/готовности
      COALESCE(
        r.payload -> 'raw' ->> 'loading_date',
        r.payload -> 'raw' ->> 'ready',
        r.payload ->> 'loading_date',
        r.payload ->> 'ready'
      ) AS loading_date_raw,

      -- Примитивная нормализация даты: ищем первый фрагмент вида DD.MM.YYYY или YYYY-MM-DD
      (
        CASE
          WHEN r.payload -> 'raw' ->> 'loading_date' ~ '\d{4}-\d{2}-\d{2}'
            THEN (substring(r.payload -> 'raw' ->> 'loading_date' from '(\d{4}-\d{2}-\d{2})'))::date
          WHEN r.payload -> 'raw' ->> 'loading_date' ~ '\d{2}\.\d{2}\.\d{4}'
            THEN to_date(substring(r.payload -> 'raw' ->> 'loading_date' from '(\d{2}\.\d{2}\.\d{4})'), 'DD.MM.YYYY')
          WHEN r.payload ->> 'loading_date' ~ '\d{4}-\d{2}-\d{2}'
            THEN (substring(r.payload ->> 'loading_date' from '(\d{4}-\d{2}-\d{2})'))::date
          WHEN r.payload ->> 'loading_date' ~ '\d{2}\.\d{2}\.\d{4}'
            THEN to_date(substring(r.payload ->> 'loading_date' from '(\d{2}\.\d{2}\.\d{4})'), 'DD.MM.YYYY')
          ELSE NULL
        END
      ) AS loading_date_norm

    FROM public.freights_ati_raw AS r;
  $view$;

  -- 2) Комментарии
  EXECUTE $cmt$
    COMMENT ON VIEW public.freights_from_ati_v IS
      'Flattened ATI freights view over freights_ati_raw: parsed id, route, price, weight, volume, dates.';

    COMMENT ON COLUMN public.freights_from_ati_v.src IS
      'Source tag for freights_ati_raw (e.g. ati_html).';

    COMMENT ON COLUMN public.freights_from_ati_v.external_id IS
      'External freight id (taken from raw.id or hash on import).';

    COMMENT ON COLUMN public.freights_from_ati_v.raw_id IS
      'Id from payload.raw.id when available.';

    COMMENT ON COLUMN public.freights_from_ati_v.loading_place_key IS
      'Simplified loading place key (city) used to join city_map.';

    COMMENT ON COLUMN public.freights_from_ati_v.unloading_place_key IS
      'Simplified unloading place key (city) used to join city_map.';

    COMMENT ON COLUMN public.freights_from_ati_v.price_rub IS
      'Parsed freight price (RUB), numeric(14,2), best-effort cleaned from text.';

    COMMENT ON COLUMN public.freights_from_ati_v.weight_tons IS
      'Freight weight in metric tons (if present in payload).';

    COMMENT ON COLUMN public.freights_from_ati_v.volume_m3 IS
      'Freight volume in cubic meters (if present in payload).';

    COMMENT ON COLUMN public.freights_from_ati_v.loading_date_norm IS
      'First parsed date from loading_date/ready fields (DD.MM.YYYY or YYYY-MM-DD), used as loading date.';
  $cmt$;

END $$;
