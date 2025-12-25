BEGIN;

CREATE OR REPLACE VIEW public.freights_from_ati_v AS
SELECT
  r.src,
  r.external_id,
  r.parsed_at,
  COALESCE((r.payload -> 'raw') ->> 'id', r.external_id) AS raw_id,

  COALESCE((r.payload -> 'raw') ->> 'title', r.payload ->> 'title') AS title_raw,

  -- Откуда (сырое текстовое поле)
  COALESCE(
    (r.payload -> 'raw') ->> 'loading',
    (r.payload -> 'raw') ->> 'from_city',
    (r.payload -> 'raw') ->> 'from',
    (r.payload -> 'raw' -> 'loading_points' ->> 0),
    r.payload ->> 'loading',
    r.payload ->> 'loading_city'
  ) AS loading_raw,

  -- Куда (сырое текстовое поле)
  COALESCE(
    (r.payload -> 'raw') ->> 'unloading',
    (r.payload -> 'raw') ->> 'to_city',
    (r.payload -> 'raw') ->> 'to',
    (r.payload -> 'raw' -> 'unloading_points' ->> 0),
    r.payload ->> 'unloading',
    r.payload ->> 'unloading_city'
  ) AS unloading_raw,

  -- Нормализованный ключ "откуда" (кусок до запятой)
  TRIM(BOTH FROM split_part(
    COALESCE(
      (r.payload -> 'raw') ->> 'loading',
      (r.payload -> 'raw') ->> 'from_city',
      (r.payload -> 'raw') ->> 'from',
      (r.payload -> 'raw' -> 'loading_points' ->> 0),
      r.payload ->> 'loading',
      r.payload ->> 'loading_city',
      ''
    ),
    ',', 1
  )) AS loading_place_key,

  -- Нормализованный ключ "куда" (кусок до запятой)
  TRIM(BOTH FROM split_part(
    COALESCE(
      (r.payload -> 'raw') ->> 'unloading',
      (r.payload -> 'raw') ->> 'to_city',
      (r.payload -> 'raw') ->> 'to',
      (r.payload -> 'raw' -> 'unloading_points' ->> 0),
      r.payload ->> 'unloading',
      r.payload ->> 'unloading_city',
      ''
    ),
    ',', 1
  )) AS unloading_place_key,

  -- Цена как сырое поле
  COALESCE(
    (r.payload -> 'raw') ->> 'price_rub',
    (r.payload -> 'raw') ->> 'price',
    r.payload ->> 'price_rub',
    r.payload ->> 'price'
  ) AS price_raw,

  -- Нормализованная цена (руб), чистим всё, кроме цифр, точки и запятой
  NULLIF(
    regexp_replace(
      COALESCE(
        (r.payload -> 'raw') ->> 'price_rub',
        (r.payload -> 'raw') ->> 'price',
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

  -- Нормализованная дистанция, км
  NULLIF(
    regexp_replace(
      COALESCE(
        (r.payload -> 'raw') ->> 'distance_km',
        (r.payload -> 'raw') ->> 'distance',
        (r.payload -> 'raw') ->> 'road_km',
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

  -- Нормализованный вес, тонны
  NULLIF(
    regexp_replace(
      COALESCE(
        (r.payload -> 'raw') ->> 'weight_tons',
        (r.payload -> 'raw') ->> 'weight',
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

  -- Нормализованный объём, м³
  NULLIF(
    regexp_replace(
      COALESCE(
        (r.payload -> 'raw') ->> 'volume_m3',
        (r.payload -> 'raw') ->> 'volume',
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

  -- Сырой текст даты готовности/погрузки
  COALESCE(
    (r.payload -> 'raw') ->> 'loading_date',
    (r.payload -> 'raw') ->> 'loading_date_text',
    (r.payload -> 'raw') ->> 'ready',
    r.payload ->> 'loading_date',
    r.payload ->> 'ready'
  ) AS loading_date_raw,

  -- Нормализованная дата погрузки:
  -- поддерживаем ISO (YYYY-MM-DD) и DD.MM.YYYY, и в raw, и на верхнем уровне
  CASE
    WHEN ((r.payload -> 'raw') ->> 'loading_date') ~ '\d{4}-\d{2}-\d{2}'
      THEN substring(
             (r.payload -> 'raw') ->> 'loading_date',
             '(\d{4}-\d{2}-\d{2})'
           )::date
    WHEN ((r.payload -> 'raw') ->> 'loading_date') ~ '\d{2}\.\d{2}\.\d{4}'
      THEN to_date(
             substring(
               (r.payload -> 'raw') ->> 'loading_date',
               '(\d{2}\.\d{2}\.\d{4})'
             ),
             'DD.MM.YYYY'
           )
    WHEN (r.payload ->> 'loading_date') ~ '\d{4}-\d{2}-\d{2}'
      THEN substring(
             r.payload ->> 'loading_date',
             '(\d{4}-\d{2}-\d{2})'
           )::date
    WHEN (r.payload ->> 'loading_date') ~ '\d{2}\.\d{2}\.\d{4}'
      THEN to_date(
             substring(
               r.payload ->> 'loading_date',
               '(\d{2}\.\d{2}\.\d{4})'
             ),
             'DD.MM.YYYY'
           )
    ELSE NULL::date
  END AS loading_date_norm

FROM public.freights_ati_raw r;

COMMIT;
