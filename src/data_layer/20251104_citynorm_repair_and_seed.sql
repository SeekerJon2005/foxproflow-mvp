-- 2025-11-04 — CityNorm REPAIR + SEED (safe/idempotent)
-- Приводим public.city_to_region_map к контракту (name, region_code), переносим данные из старых колонок
-- и загружаем семена для популярных регионов/синонимов (можно расширять далее простыми INSERT ... ON CONFLICT DO NOTHING).

BEGIN;

-- Мини-утилита для нормализации русских названий
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

-- 1) Создаём таблицу, если её нет
DO $$
BEGIN
  IF to_regclass('public.city_to_region_map') IS NULL THEN
    CREATE TABLE public.city_to_region_map(
      name        text,
      region_code text
    );
  END IF;
END$$;

-- 2) Гарантируем наличие нужных колонок (если раньше были другие, например city/region/code/iso)
DO $$
DECLARE
  has_name boolean;
  has_code boolean;
  has_city boolean;
  has_region boolean;
  has_iso boolean;
  has_code_col boolean;
BEGIN
  SELECT EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='name'
  ) INTO has_name;

  SELECT EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='region_code'
  ) INTO has_code;

  IF NOT has_name THEN
    EXECUTE 'ALTER TABLE public.city_to_region_map ADD COLUMN name text';
  END IF;

  IF NOT has_code THEN
    EXECUTE 'ALTER TABLE public.city_to_region_map ADD COLUMN region_code text';
  END IF;

  -- Мягкий перенос из возможных старых колонок
  SELECT EXISTS(SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='city') INTO has_city;
  SELECT EXISTS(SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='region') INTO has_region;
  SELECT EXISTS(SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='iso') INTO has_iso;
  SELECT EXISTS(SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='city_to_region_map' AND column_name='code') INTO has_code_col;

  IF has_city THEN
    EXECUTE 'UPDATE public.city_to_region_map SET name = COALESCE(name, city::text) WHERE name IS NULL';
  END IF;
  IF has_region THEN
    EXECUTE 'UPDATE public.city_to_region_map SET region_code = COALESCE(region_code, region::text) WHERE region_code IS NULL';
  END IF;
  IF has_iso THEN
    EXECUTE 'UPDATE public.city_to_region_map SET region_code = COALESCE(region_code, iso::text) WHERE region_code IS NULL';
  END IF;
  IF has_code_col THEN
    EXECUTE 'UPDATE public.city_to_region_map SET region_code = COALESCE(region_code, code::text) WHERE region_code IS NULL';
  END IF;

  -- Нормализуем name
  EXECUTE 'UPDATE public.city_to_region_map SET name = public.ff_ru_simplify(name) WHERE name IS NOT NULL';
END$$;

-- 3) Уникальный индекс по name (если его нет)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_city_to_region_map_name'
  ) THEN
    EXECUTE 'CREATE UNIQUE INDEX ux_city_to_region_map_name ON public.city_to_region_map(name) WHERE name IS NOT NULL';
  END IF;
END$$;

-- 4) Семена (то, что у вас всплывало в топе + ключевые столицы/регионы). Можно повторно запускать — конфликт игнорируется.
-- Столицы
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('МОСКВА','RU-MOW'),
  ('САНКТ-ПЕТЕРБУРГ','RU-SPE'),
  ('СПБ','RU-SPE'),
  ('С-ПЕТЕРБУРГ','RU-SPE')
ON CONFLICT DO NOTHING;

-- Ваши «топовые» из диагностики
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('ЗАБАЙКАЛЬСКИЙ КРАЙ','RU-ZAB'), ('ЧИТА','RU-ZAB'),
  ('ВЛАДИМИРСКАЯ ОБЛАСТЬ','RU-VLA'), ('ВЛАДИМИР','RU-VLA'),
  ('АЛТАЙСКИЙ КРАЙ','RU-ALT'), ('БАРНАУЛ','RU-ALT'),
  ('АМУРСКАЯ ОБЛАСТЬ','RU-AMU'), ('БЛАГОВЕЩЕНСК','RU-AMU'),
  ('БЕЛГОРОДСКАЯ ОБЛАСТЬ','RU-BEL'), ('БЕЛГОРОД','RU-BEL'),
  ('БРЯНСКАЯ ОБЛАСТЬ','RU-BRY'), ('БРЯНСК','RU-BRY'),
  ('ВОРОНЕЖСКАЯ ОБЛАСТЬ','RU-VOR'), ('ВОРОНЕЖ','RU-VOR'),
  ('ВОЛОГОДСКАЯ ОБЛАСТЬ','RU-VLG'), ('ВОЛОГДА','RU-VLG'),
  ('АРХАНГЕЛЬСК','RU-ARK'),
  ('ИВАНОВСКАЯ ОБЛАСТЬ','RU-IVA'), ('ИВАНОВО','RU-IVA')
ON CONFLICT DO NOTHING;

-- Расширенная матрица (частые субъекты и столицы регионов; при желании доведём до 100%)
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('ЛЕНИНГРАДСКАЯ ОБЛАСТЬ','RU-LEN'),
  ('КРАСНОДАРСКИЙ КРАЙ','RU-KDA'),
  ('КРАСНОЯРСКИЙ КРАЙ','RU-KYA'),
  ('НОВОСИБИРСКАЯ ОБЛАСТЬ','RU-NVS'), ('НОВОСИБИРСК','RU-NVS'),
  ('КАЛИНИНГРАДСКАЯ ОБЛАСТЬ','RU-KGD'), ('КАЛИНИНГРАД','RU-KGD'),
  ('КУРСКАЯ ОБЛАСТЬ','RU-KRS'), ('КУРСК','RU-KRS'),
  ('КИРОВСКАЯ ОБЛАСТЬ','RU-KIR'), ('КИРОВ','RU-KIR'),
  ('КУРГАНСКАЯ ОБЛАСТЬ','RU-KGN'), ('КУРГАН','RU-KGN'),
  ('КЕМЕРОВСКАЯ ОБЛАСТЬ','RU-KEM'), ('КЕМЕРОВО','RU-KEM'),
  ('ХАБАРОВСКИЙ КРАЙ','RU-KHA'), ('ХАБАРОВСК','RU-KHA'),
  ('ПРИМОРСКИЙ КРАЙ','RU-PRI'), ('ВЛАДИВОСТОК','RU-PRI'),
  ('ИРКУТСКАЯ ОБЛАСТЬ','RU-IRK'), ('ИРКУТСК','RU-IRK'),
  ('ОМСКАЯ ОБЛАСТЬ','RU-OMS'), ('ОМСК','RU-OMS'),
  ('ТОМСКАЯ ОБЛАСТЬ','RU-TOM'), ('ТОМСК','RU-TOM'),
  ('СВЕРДЛОВСКАЯ ОБЛАСТЬ','RU-SVE'), ('ЕКАТЕРИНБУРГ','RU-SVE'),
  ('САМАРСКАЯ ОБЛАСТЬ','RU-SAM'), ('САМАРА','RU-SAM'),
  ('САРАТОВСКАЯ ОБЛАСТЬ','RU-SAR'), ('САРАТОВ','RU-SAR'),
  ('ВОЛГОГРАДСКАЯ ОБЛАСТЬ','RU-VGG'), ('ВОЛГОГРАД','RU-VGG'),
  ('РОСТОВСКАЯ ОБЛАСТЬ','RU-ROS'), ('РОСТОВ-НА-ДОНУ','RU-ROS'),
  ('РЯЗАНСКАЯ ОБЛАСТЬ','RU-RYA'), ('РЯЗАНЬ','RU-RYA'),
  ('ПСКОВСКАЯ ОБЛАСТЬ','RU-PSK'), ('ПСКОВ','RU-PSK'),
  ('МУРМАНСКАЯ ОБЛАСТЬ','RU-MUR'), ('МУРМАНСК','RU-MUR'),
  ('КОСТРОМСКАЯ ОБЛАСТЬ','RU-KOS'), ('КОСТРОМА','RU-KOS'),
  ('РЕСПУБЛИКА КОМИ','RU-KO'), ('СЫКТЫВКАР','RU-KO'),
  ('РЕСПУБЛИКА КАРЕЛИЯ','RU-KR'), ('ПЕТРОЗАВОДСК','RU-KR'),
  ('РЕСПУБЛИКА ТАТАРСТАН','RU-TA'), ('КАЗАНЬ','RU-TA'),
  ('УДМУРТСКАЯ РЕСПУБЛИКА','RU-UD'), ('ИЖЕВСК','RU-UD'),
  ('УЛЬЯНОВСКАЯ ОБЛАСТЬ','RU-ULY'), ('УЛЬЯНОВСК','RU-ULY'),
  ('ПЕРМСКИЙ КРАЙ','RU-PER'), ('ПЕРМЬ','RU-PER'),
  ('ПЕНЗЕНСКАЯ ОБЛАСТЬ','RU-PNZ'), ('ПЕНЗА','RU-PNZ'),
  ('ЛИПЕЦКАЯ ОБЛАСТЬ','RU-LIP'), ('ЛИПЕЦК','RU-LIP'),
  ('КАЛУЖСКАЯ ОБЛАСТЬ','RU-KLU'), ('КАЛУГА','RU-KLU'),
  ('РЕСПУБЛИКА КАЛМЫКИЯ','RU-KL'), ('ЭЛИСТА','RU-KL'),
  ('РЕСПУБЛИКА МАРИЙ ЭЛ','RU-ME'), ('ЙОШКАР-ОЛА','RU-ME'),
  ('КАБАРДИНО-БАЛКАРСКАЯ РЕСПУБЛИКА','RU-KB'), ('НАЛЬЧИК','RU-KB'),
  ('КАРАЧАЕВО-ЧЕРКЕССКАЯ РЕСПУБЛИКА','RU-KC'), ('ЧЕРКЕССК','RU-KC'),
  ('ЧЕЧЕНСКАЯ РЕСПУБЛИКА','RU-CE'), ('ГРОЗНЫЙ','RU-CE'),
  ('РЕСПУБЛИКА ДАГЕСТАН','RU-DA'), ('МАХАЧКАЛА','RU-DA'),
  ('РЕСПУБЛИКА ИНГУШЕТИЯ','RU-IN'), ('МАГАС','RU-IN'),
  ('РЕСПУБЛИКА СЕВЕРНАЯ ОСЕТИЯ-АЛАНИЯ','RU-SE'), ('ВЛАДИКАВКАЗ','RU-SE'),
  ('ХМАО-ЮГРА','RU-KHM'), ('СУРГУТ','RU-KHM'),
  ('ЯНАО','RU-YAN'), ('САЛЕХАРД','RU-YAN'),
  ('НЕНЕЦКИЙ АО','RU-NEN'), ('НАРЬЯН-МАР','RU-NEN'),
  ('ЧУКОТСКИЙ АО','RU-CHU'), ('АНАДЫРЬ','RU-CHU'),
  ('САХАЛИНСКАЯ ОБЛАСТЬ','RU-SAK'), ('ЮЖНО-САХАЛИНСК','RU-SAK'),
  ('ЕВРЕЙСКАЯ АО','RU-YEV'), ('БИРОБИДЖАН','RU-YEV'),
  ('РЕСПУБЛИКА АДЫГЕЯ','RU-AD'), ('МАЙКОП','RU-AD'),
  ('РЕСПУБЛИКА ХАКАСИЯ','RU-KK'), ('АБАКАН','RU-KK'),
  ('РЕСПУБЛИКА БУРЯТИЯ','RU-BU'), ('УЛАН-УДЭ','RU-BU'),
  ('РЕСПУБЛИКА ТЫВА','RU-TY'), ('КЫЗЫЛ','RU-TY'),
  ('РЕСПУБЛИКА АЛТАЙ','RU-AL'), ('ГОРНО-АЛТАЙСК','RU-AL'),
  ('КАЛУГА','RU-KLU'), ('ТУЛЬСКАЯ ОБЛАСТЬ','RU-TUL'), ('ТУЛА','RU-TUL'),
  ('ЯРОСЛАВСКАЯ ОБЛАСТЬ','RU-YAR'), ('ЯРОСЛАВЛЬ','RU-YAR'),
  ('МОСКОВСКАЯ ОБЛАСТЬ','RU-MOS')
ON CONFLICT DO NOTHING;

COMMIT;
