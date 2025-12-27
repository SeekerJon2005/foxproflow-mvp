-- 20251113_freights_created_at_compat.sql
-- Совместимая колонка created_at для public.freights с умной обратной заливкой.
-- Скрипт безопасен к повторному запуску и спокойно переживает отсутствие таблицы freights.

DO $$
DECLARE
  cols text[] := ARRAY[
    'created_at',        -- если уже есть — используется напрямую, остальные колонки только как источник
    'created_ts',
    'ts_created',
    'ts_collected',
    'collected_at',
    'ingested_at',
    'parsed_at',
    'published_at',
    'inserted_at',
    'updated_at',
    'ts',
    'load_time',
    'extracted_at'
  ];
  c           text;
  has_table   boolean;
BEGIN
  -- 0) Проверяем наличие таблицы freights; если её ещё нет — тихо выходим
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name   = 'freights'
  )
  INTO has_table;

  IF NOT has_table THEN
    RAISE NOTICE 'Table public.freights not found, skipping created_at compat migration';
    RETURN;
  END IF;

  -- 1) Добавить колонку, если её нет
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='freights'
      AND column_name='created_at'
  ) THEN
    EXECUTE 'ALTER TABLE public.freights ADD COLUMN created_at timestamptz';
  END IF;

  -- 2) Обратная заливка по приоритету из имеющихся столбцов
  FOREACH c IN ARRAY cols LOOP
    IF c <> 'created_at' AND EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public'
        AND table_name='freights'
        AND column_name=c
    ) THEN
      EXECUTE format(
        'UPDATE public.freights
            SET created_at = COALESCE(created_at, %I)
          WHERE created_at IS NULL',
        c
      );
    END IF;
  END LOOP;

  -- 3) Добить NULL текущим временем (хвосты)
  EXECUTE '
    UPDATE public.freights
       SET created_at = COALESCE(created_at, now())
     WHERE created_at IS NULL
  ';

  -- 4) Индекс по времени (для окна/сортировки)
  EXECUTE '
    CREATE INDEX IF NOT EXISTS freights_created_at_idx
      ON public.freights (created_at DESC)
  ';

  -- 5) Комментарий к колонке (только если колонка уже гарантированно есть)
  EXECUTE $cmt$
    COMMENT ON COLUMN public.freights.created_at IS
      'Совместимая метка времени для окна автоплана. Заполнена из доступных ts-полей или now()'
  $cmt$;
END $$;
