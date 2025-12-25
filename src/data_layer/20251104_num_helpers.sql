-- 2025-11-04 — numeric & json helpers (safe/idempotent)

-- Достаёт строку по "точечному" пути из JSONB: ff_get(j,'payload.distance_km')
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

-- Жёстко нормализует «грязные» числа: удаляет буквы/валюты/пробелы, конвертирует , в .
CREATE OR REPLACE FUNCTION public.ff_num(txt text)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE s text; res numeric;
BEGIN
  IF txt IS NULL THEN RETURN NULL; END IF;

  -- NBSP / thin space / NNBSP -> обычный пробел
  s := translate(txt, E'\u00A0\u2009\u202F', '   ');
  -- убираем буквы, валюты и прочее
  s := regexp_replace(s, '[A-Za-zА-Яа-яЁё₽₴$€¥%/]+', '', 'g');
  -- убираем пробелы
  s := regexp_replace(s, '\s+', '', 'g');
  -- запятые -> точки
  s := replace(s, ',', '.');
  -- оставляем только последнюю точку как десятичный разделитель
  s := regexp_replace(s, '\.(?=.*\.)', '', 'g');

  BEGIN
    res := NULLIF(s,'')::numeric;
  EXCEPTION WHEN others THEN
    res := NULL;
  END;
  RETURN res;
END$$;

-- Берёт первое ненулевое число из набора ключей JSON (поддерживает "payload.xxx")
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
