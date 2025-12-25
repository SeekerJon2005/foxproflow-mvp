-- file: src/data_layer/20251102_freights_mv_v3.sql
BEGIN;

CREATE OR REPLACE FUNCTION public.ff_num(t text)
RETURNS numeric LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE s text; BEGIN
  IF t IS NULL THEN RETURN NULL; END IF;
  s := trim(replace(replace(replace(replace(t, chr(160), ' '), 'руб', ''), ' ', ''), ' ',''));
  s := replace(s, ',', '.');
  s := regexp_replace(s, '[^0-9\.\-]', '', 'g');
  IF s = '' OR s = '-' THEN RETURN NULL; END IF;
  RETURN s::numeric;
EXCEPTION WHEN others THEN RETURN NULL; END $$;

CREATE OR REPLACE FUNCTION public.ff_tstz(t text)
RETURNS timestamptz LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF t IS NULL OR btrim(t)='' THEN RETURN NULL; END IF;
  RETURN t::timestamptz;
EXCEPTION WHEN others THEN RETURN NULL; END $$;

-- при необходимости можно ссылаться на ту же базовую таблицу, как в v2
-- (для краткости здесь пропущено повторение всего SELECT; используйте v2 как основу)

COMMIT;
