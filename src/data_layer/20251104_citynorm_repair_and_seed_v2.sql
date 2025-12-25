-- 2025-11-04 — CityNorm REPAIR + SEED v2 (safe/idempotent)
-- ЧТО ДЕЛАЕТ:
-- • Если public.city_to_region_map была «кривой» (city NOT NULL, нет region_code и т.п.) —
--   создаём правильную *_new (name, region_code), мигрируем данные из legacy через JSON,
--   затем атомарно подменяем таблицу.
-- • Добавляем базовые сиды (МОСКВА, СПБ, и топы из ваших логов).
-- • Не ломает текущие данные: старую таблицу сохраняем как city_to_region_map_legacy.

BEGIN;

-- Утилита нормализации русских названий
CREATE OR REPLACE FUNCTION public.ff_ru_simplify(s text)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE x text;
BEGIN
  IF s IS NULL THEN RETURN NULL; END IF;
  x := upper(btrim(s));
  x := replace(x, 'Ё', 'Е');
  x := regexp_replace(x, '\.', '', 'g');
  x := regexp_replace(x, '\s+', ' ', 'g');
  x := regexp_replace(x, '^\s*Г\.?\s+', '', 'g');      -- «г. »
  x := regexp_replace(x, '^\s*ГОРОД\s+', '', 'g');     -- «город …»
  x := regexp_replace(x, '\s+ОБЛАСТЬ$', '', 'g');      -- « … ОБЛАСТЬ»
  x := regexp_replace(x, '\s+КРАЙ$', '', 'g');         -- « … КРАЙ»
  x := btrim(x);
  RETURN x;
END$$;

-- Если таблицы нет — просто создаём правильную схему
DO $$
BEGIN
  IF to_regclass('public.city_to_region_map') IS NULL THEN
    CREATE TABLE public.city_to_region_map(
      name        text PRIMARY KEY,
      region_code text NOT NULL
    );
  END IF;
END$$;

-- Если таблица есть, но НЕ имеет нужных колонок -> делаем миграцию на новую
DO $$
DECLARE
  has_name bool;
  has_code bool;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='name'
  ) INTO has_name;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='region_code'
  ) INTO has_code;

  IF NOT (has_name AND has_code) THEN
    -- 1) создаём новую таблицу правильной формы
    CREATE TABLE IF NOT EXISTS public.city_to_region_map_new(
      name        text PRIMARY KEY,
      region_code text NOT NULL
    );

    -- 2) перенос данных из legacy, независимо от её колонок (через JSON)
    INSERT INTO public.city_to_region_map_new(name, region_code)
    SELECT DISTINCT
      public.ff_ru_simplify(
        COALESCE(
          NULLIF(j->>'name',''),
          NULLIF(j->>'city',''),
          NULLIF(j->>'region',''),
          NULLIF(j->>'region_name','')
        )
      ) AS name,
      COALESCE(
        NULLIF(j->>'region_code',''),
        NULLIF(j->>'iso',''),
        NULLIF(j->>'code',''),
        (CASE WHEN (j->>'region') ~ '^[A-Z]{2}-[A-Z0-9]{3}$' THEN j->>'region' END)
      ) AS region_code
    FROM (SELECT to_jsonb(t.*) AS j FROM public.city_to_region_map t) s
    WHERE COALESCE(
            NULLIF(j->>'name',''),
            NULLIF(j->>'city',''),
            NULLIF(j->>'region',''),
            NULLIF(j->>'region_name','')
          ) IS NOT NULL
      AND COALESCE(
            NULLIF(j->>'region_code',''),
            NULLIF(j->>'iso',''),
            NULLIF(j->>'code',''),
            (CASE WHEN (j->>'region') ~ '^[A-Z]{2}-[A-Z0-9]{3}$' THEN j->>'region' END)
          ) IS NOT NULL
    ON CONFLICT (name) DO NOTHING;

    -- 3) подмена: старую храним как *_legacy
    BEGIN
      EXECUTE 'ALTER TABLE public.city_to_region_map RENAME TO city_to_region_map_legacy';
    EXCEPTION WHEN duplicate_table THEN
      -- если legacy уже осталась с прошлого раза — удалим и переименуем заново
      EXECUTE 'DROP TABLE IF EXISTS public.city_to_region_map_legacy';
      EXECUTE 'ALTER TABLE public.city_to_region_map RENAME TO city_to_region_map_legacy';
    END;

    EXECUTE 'ALTER TABLE public.city_to_region_map_new RENAME TO city_to_region_map';
  ELSE
    -- просто нормализуем name, если схема уже правильная
    UPDATE public.city_to_region_map
    SET name = public.ff_ru_simplify(name)
    WHERE name IS NOT NULL;
  END IF;
END$$;

-- Уникальный индекс на name
CREATE UNIQUE INDEX IF NOT EXISTS ux_city_to_region_map_name
  ON public.city_to_region_map(name);

-- Сиды (можно повторно выполнять — не создадут дублей)
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('МОСКВА','RU-MOW'),
  ('САНКТ-ПЕТЕРБУРГ','RU-SPE'),
  ('СПБ','RU-SPE'),
  ('С-ПЕТЕРБУРГ','RU-SPE'),
  ('ЗАБАЙКАЛЬСКИЙ КРАЙ','RU-ZAB'), ('ЧИТА','RU-ZAB'),
  ('ВЛАДИМИРСКАЯ ОБЛАСТЬ','RU-VLA'), ('ВЛАДИМИР','RU-VLA'),
  ('АЛТАЙСКИЙ КРАЙ','RU-ALT'), ('БАРНАУЛ','RU-ALT'),
  ('АМУРСКАЯ ОБЛАСТЬ','RU-AMU'), ('БЛАГОВЕЩЕНСК','RU-AMU'),
  ('БЕЛГОРОДСКАЯ ОБЛАСТЬ','RU-BEL'), ('БЕЛГОРОД','RU-BEL'),
  ('БРЯНСКАЯ ОБЛАСТЬ','RU-BRY'), ('БРЯНСК','RU-BRY'),
  ('ВОРОНЕЖСКАЯ ОБЛАСТЬ','RU-VOR'), ('ВОРОНЕЖ','RU-VOR'),
  ('ВОЛОГОДСКАЯ ОБЛАСТЬ','RU-VLG'), ('ВОЛОГДА','RU-VLG'),
  ('АРХАНГЕЛЬСК','RU-ARK'),
  ('ИВАНОВСКАЯ ОБЛАСТЬ','RU-IVA'), ('ИВАНОВО','RU-IVA'),
  ('ЛЕНИНГРАДСКАЯ ОБЛАСТЬ','RU-LEN'),
  ('КРАСНОДАРСКИЙ КРАЙ','RU-KDA'),
  ('КРАСНОЯРСКИЙ КРАЙ','RU-KYA'),
  ('НОВОСИБИРСКАЯ ОБЛАСТЬ','RU-NVS'), ('НОВОСИБИРСК','RU-NVS'),
  ('КАЛИНИНГРАДСКАЯ ОБЛАСТЬ','RU-KGD'), ('КАЛИНИНГРАД','RU-KGD'),
  ('ХАБАРОВСКИЙ КРАЙ','RU-KHA'), ('ХАБАРОВСК','RU-KHA'),
  ('ПРИМОРСКИЙ КРАЙ','RU-PRI'), ('ВЛАДИВОСТОК','RU-PRI')
ON CONFLICT (name) DO NOTHING;

-- финальная нормализация name
UPDATE public.city_to_region_map SET name = public.ff_ru_simplify(name);

COMMIT;
