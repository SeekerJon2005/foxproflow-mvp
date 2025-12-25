-- 20251113_freights_price_v.sql
-- Facade-view для цен грузов, совместим со старыми/новыми схемами.
-- price_rub:  numeric(14,2)
-- price_source: из какого поля взята цена (revenue/expected/posted/predicted/none)

BEGIN;

DO $$
DECLARE
  has_table     boolean;
  has_expected  boolean;
  has_posted    boolean;
  has_predicted boolean;
  view_sql      text;
BEGIN
  -- 0) Проверяем, что public.freights вообще есть; если нет — миграцию тихо пропускаем
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name   = 'freights'
  )
  INTO has_table;

  IF NOT has_table THEN
    RAISE NOTICE 'Table public.freights not found, skipping freights_price_v migration';
    RETURN;
  END IF;

  -- 1) Проверяем наличие опциональных колонок цен
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='freights'
      AND column_name='expected_price_rub'
  ) INTO has_expected;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='freights'
      AND column_name='posted_price_rub'
  ) INTO has_posted;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='freights'
      AND column_name='predicted_price_rub'
  ) INTO has_predicted;

  -- 2) Собираем SQL для вьюхи с учётом реально существующих колонок
  view_sql := 'CREATE OR REPLACE VIEW public.freights_price_v AS
  SELECT
    f.id,
    f.loading_region::text   AS loading_region,
    f.unloading_region::text AS unloading_region,
    COALESCE(f.revenue_rub';

  IF has_expected THEN
    view_sql := view_sql || ', f.expected_price_rub';
  END IF;

  IF has_posted THEN
    view_sql := view_sql || ', f.posted_price_rub';
  END IF;

  IF has_predicted THEN
    view_sql := view_sql || ', f.predicted_price_rub';
  END IF;

  view_sql := view_sql || ', 0)::numeric(14,2) AS price_rub,
    CASE
      WHEN f.revenue_rub IS NOT NULL THEN ''revenue_rub''';

  IF has_expected THEN
    view_sql := view_sql || ' WHEN f.expected_price_rub  IS NOT NULL THEN ''expected_price_rub''';
  END IF;

  IF has_posted THEN
    view_sql := view_sql || ' WHEN f.posted_price_rub    IS NOT NULL THEN ''posted_price_rub''';
  END IF;

  IF has_predicted THEN
    view_sql := view_sql || ' WHEN f.predicted_price_rub IS NOT NULL THEN ''predicted_price_rub''';
  END IF;

  view_sql := view_sql || ' ELSE ''none'' END AS price_source
  FROM public.freights f';

  -- 3) Создаём/обновляем вьюху
  EXECUTE view_sql;

  -- 4) Барьер безопасности и комментарии — тоже только если вьюха есть
  EXECUTE '
    ALTER VIEW public.freights_price_v
      SET (security_barrier = true)
  ';

  EXECUTE $cmt$
    COMMENT ON VIEW public.freights_price_v IS
      'Facade for freight price selection used by planner. Fallback: revenue -> expected -> posted -> predicted -> 0.';
    COMMENT ON COLUMN public.freights_price_v.price_rub IS
      'Selected price in RUB, numeric(14,2).';
    COMMENT ON COLUMN public.freights_price_v.price_source IS
      'Which column provided price_rub (revenue_rub | expected_price_rub | posted_price_rub | predicted_price_rub | none).';
  $cmt$;

END $$;

COMMIT;
