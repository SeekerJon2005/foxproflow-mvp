-- scripts/sql/20251113_freights_price_layer.sql
BEGIN;

-- Небольшие лимиты, чтобы миграции не зависали под блокировками
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- 0) Совместимый слой: гарантируем наличие и корректную семантику public.freights.price
DO $$
DECLARE
  v_ver           int  := current_setting('server_version_num')::int;  -- 120000 == PG12
  v_col_exists    bool := FALSE;
  v_is_generated  bool := FALSE;
  v_trg_exists    bool := FALSE;
BEGIN
  -- Проверяем наличие колонки и тип генерации
  SELECT TRUE,
         (a.attgenerated = 's')
  INTO  v_col_exists, v_is_generated
  FROM pg_attribute a
  JOIN pg_class     c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname   = 'public'
    AND c.relname   = 'freights'
    AND a.attname   = 'price'
    AND NOT a.attisdropped
  LIMIT 1;

  IF NOT v_col_exists THEN
    IF v_ver >= 120000 THEN
      -- PG12+: используем вычисляемую STORED-колонку — идеальный шим без триггеров
      EXECUTE '
        ALTER TABLE public.freights
        ADD COLUMN price numeric
        GENERATED ALWAYS AS (COALESCE(revenue_rub, 0::numeric)) STORED
      ';
    ELSE
      -- PG11 и ниже: добавляем обычную колонку + первичная инициализация
      EXECUTE 'ALTER TABLE public.freights ADD COLUMN price numeric';
      EXECUTE 'UPDATE public.freights SET price = COALESCE(revenue_rub, 0)';
    END IF;
  END IF;

  -- Если колонка НЕ generated (PG<12 или уже была обычной) — ставим триггер синхронизации
  IF (v_ver < 120000) OR (v_col_exists AND NOT v_is_generated) THEN
    -- Функция триггера (идемпотентно)
    CREATE OR REPLACE FUNCTION public.freights_price_sync_biu()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $fn$
    BEGIN
      NEW.price := COALESCE(NEW.revenue_rub, 0::numeric);
      RETURN NEW;
    END
    $fn$;

    -- Есть ли триггер?
    SELECT EXISTS (
      SELECT 1
      FROM pg_trigger t
      JOIN pg_class   c ON c.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public'
        AND c.relname = 'freights'
        AND t.tgname  = 'freights_price_sync_trg'
        AND NOT t.tgisinternal
    )
    INTO v_trg_exists;

    -- Если нет — создаём
    IF NOT v_trg_exists THEN
      EXECUTE '
        CREATE TRIGGER freights_price_sync_trg
        BEFORE INSERT OR UPDATE OF revenue_rub ON public.freights
        FOR EACH ROW
        EXECUTE FUNCTION public.freights_price_sync_biu()
      ';
    END IF;
  END IF;

  -- Немного метаданных
  COMMENT ON COLUMN public.freights.price IS
    'Временный совместимый шим. На PG>=12 - STORED generated из revenue_rub; иначе поддерживается триггером. Удалить после выноса цены в freights_price_v и рефакторинга кода.';
END
$$;

-- 1) Долгосрочный совместимый слой цены: единая вьюха для автопланировщика
CREATE OR REPLACE VIEW public.freights_price_v AS
SELECT
  f.id                                   AS freight_id,
  COALESCE(f.revenue_rub, 0::numeric)    AS price_rub
FROM public.freights f;

COMMENT ON VIEW public.freights_price_v IS
  'Единый источник цены для автопланировщика. Развиваем fallback-цепочку тут (revenue/expected/posted/predicted), а не в коде.';
COMMENT ON COLUMN public.freights_price_v.price_rub IS
  'Текущая цена, руб. Сейчас = revenue_rub; в будущем: COALESCE(revenue, expected, posted, predicted, ...).';

-- (необязательно) Права чтения для API/воркеров, если есть роль
-- GRANT SELECT ON public.freights_price_v TO app_ro;

COMMIT;
