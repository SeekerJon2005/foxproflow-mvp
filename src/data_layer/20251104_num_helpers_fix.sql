-- 2025-11-04 — numeric & json helpers (fix+create, idempotent & safe)

-- 1) ff_get(j jsonb, path text)  — достаёт значение по "точечному" пути из JSONB
CREATE OR REPLACE FUNCTION public.ff_get(j jsonb, path text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE parts text[]; cur jsonb; i int; key text;
BEGIN
  IF j IS NULL OR path IS NULL OR path = '' THEN
    RETURN NULL;
  END IF;
  parts := string_to_array(path, '.');
  cur := j;
  FOR i IN 1..array_length(parts,1) LOOP
    key := parts[i];
    IF i < array_length(parts,1) THEN
      cur := cur->key;
      IF cur IS NULL THEN RETURN NULL; END IF;
    ELSE
      RETURN cur->>key;
    END IF;
  END LOOP;
  RETURN NULL;
END$$;

-- 2) ff_num(text) — ПЕРЕСОЗДАТЬ с тем же именем параметра 't', чтобы не ловить "cannot change name of input parameter"
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = 'ff_num'
      AND pg_get_function_identity_arguments(p.oid) = 'text'
  ) THEN
    EXECUTE 'DROP FUNCTION public.ff_num(text)';
  END IF;
END$$;

CREATE FUNCTION public.ff_num(t text)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE s text; res numeric;
BEGIN
  IF t IS NULL THEN RETURN NULL; END IF;

  -- нормализация: убираем редкие пробелы, буквы, валюты, %, '/', и т.д.
  s := translate(t, E'\u00A0\u2009\u202F', '   ');               -- NBSP/THIN/NNBSP → обычные пробелы
  s := regexp_replace(s, '[A-Za-zА-Яа-яЁё₽₴$€¥%/]+', '', 'g');   -- убрать буквы/валюты
  s := regexp_replace(s, '\s+', '', 'g');                        -- убрать все пробелы
  s := replace(s, ',', '.');                                     -- запятая → точка
  s := regexp_replace(s, '\.(?=.*\.)', '', 'g');                 -- оставить только последнюю точку

  BEGIN
    res := NULLIF(s,'')::numeric;
  EXCEPTION WHEN others THEN
    res := NULL;
  END;
  RETURN res;
END$$;

-- 3) ff_num_from_keys(j jsonb, keys text[]) — берёт первое ненулевое число из набора путей (в т.ч. payload.xxx)
CREATE OR REPLACE FUNCTION public.ff_num_from_keys(j jsonb, keys text[])
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE k text; v text; n numeric;
BEGIN
  IF j IS NULL OR keys IS NULL THEN RETURN NULL; END IF;
  FOREACH k IN ARRAY keys LOOP
    v := public.ff_get(j, k);
    n := public.ff_num(v);
    IF n IS NOT NULL AND n <> 0 THEN
      RETURN n;
    END IF;
  END LOOP;
  RETURN NULL;
END$$;
