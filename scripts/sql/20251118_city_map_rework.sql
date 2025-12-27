BEGIN;

-- 1. Разрешаем временно жить без координат (на время геокодинга)
ALTER TABLE public.city_map
    ALTER COLUMN lat DROP NOT NULL,
    ALTER COLUMN lon DROP NOT NULL;

-- 1.1. Фиксируем NOT NULL для ключевых полей (подстраховка)
ALTER TABLE public.city_map
    ALTER COLUMN region SET NOT NULL,
    ALTER COLUMN name   SET NOT NULL;

-- 1.2. Обновляем default для updated_at, чтобы новые записи не требовали ручной установки
ALTER TABLE public.city_map
    ALTER COLUMN updated_at SET DEFAULT now();

-- 2. Добавляем технический id, если его ещё нет
ALTER TABLE public.city_map
    ADD COLUMN IF NOT EXISTS id bigserial;

-- 2.1. Если есть старый PRIMARY KEY (по region), снимаем его
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM   pg_constraint
    WHERE  conrelid = 'public.city_map'::regclass
      AND  contype  = 'p'
  ) THEN
    -- ожидаем, что имя старого PK = city_map_pkey
    EXECUTE 'ALTER TABLE public.city_map DROP CONSTRAINT city_map_pkey';
  END IF;
END$$;

-- 2.2. Если PK ещё нет — ставим новый PK по id
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_constraint
    WHERE  conrelid = 'public.city_map'::regclass
      AND  contype  = 'p'
  ) THEN
    EXECUTE 'ALTER TABLE public.city_map ADD CONSTRAINT city_map_pkey PRIMARY KEY (id)';
  END IF;
END$$;

-- 3. Нормализованный ключ
ALTER TABLE public.city_map
    ADD COLUMN IF NOT EXISTS norm_key text;

UPDATE public.city_map
SET norm_key = fn_norm_key(name)
WHERE norm_key IS NULL;

ALTER TABLE public.city_map
    ALTER COLUMN norm_key SET NOT NULL;

-- 4. Метаданные
ALTER TABLE public.city_map
    ADD COLUMN IF NOT EXISTS source     text        NOT NULL DEFAULT 'import',
    ADD COLUMN IF NOT EXISTS precision  text,
    ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

-- 5. Новый уникальный индекс по (norm_key, region)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_class
    WHERE  relname = 'city_map_norm_region_uq'
  ) THEN
    CREATE UNIQUE INDEX city_map_norm_region_uq
      ON public.city_map(norm_key, region);
  END IF;
END$$;

-- 6. Дополнительный индекс по norm_key для быстрых поисков
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_class
    WHERE  relname = 'city_map_norm_idx'
  ) THEN
    CREATE INDEX city_map_norm_idx
      ON public.city_map(norm_key);
  END IF;
END$$;

COMMIT;
