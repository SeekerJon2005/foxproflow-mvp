BEGIN;

-- Универсальная нормализация строковых ключей для city_map / очереди и т.п.
-- NULL -> NULL, иначе:
--   1) trim по краям
--   2) перевод в верхний регистр
--   3) ё/Ё -> Е
--   4) схлопываем повторяющиеся пробелы в один
CREATE OR REPLACE FUNCTION public.fn_norm_key(p_input text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_input IS NULL THEN NULL
        ELSE
            regexp_replace(
                upper(
                    translate(
                        btrim(p_input),
                        'ёЁ',
                        'ее'
                    )
                ),
                '\s+',
                ' ',
                'g'
            )
    END
$$;

COMMENT ON FUNCTION public.fn_norm_key(text) IS
    'Нормализация строковых ключей: trim, upper, ё→е, схлопывание пробелов. Используется для city_map.norm_key и очереди ops.citymap_autofill_queue.';

COMMIT;
