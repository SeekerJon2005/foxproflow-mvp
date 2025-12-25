-- 20251126_freights_source_uid_uq.sql
-- Добавляет уникальное ограничение на public.freights.source_uid,
-- чтобы etl.freights.from_ati с ON CONFLICT (source_uid) DO NOTHING
-- работал, как задумано.
--
-- Поведение:
--   * если колонки source_uid нет — бросаем понятную ошибку;
--   * если есть дубликаты по source_uid (IS NOT NULL) — тоже бросаем ошибку,
--     чтобы не "молча" упасть на ALTER TABLE;
--   * если constraint freights_source_uid_uq уже есть — ничего не делаем;
--   * скрипт идемпотентен, можно запускать повторно.

DO $$
DECLARE
    col_exists boolean;
    dup_count  integer;
BEGIN
    -- 1) Проверяем, что колонка source_uid вообще существует
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'freights'
          AND column_name  = 'source_uid'
    ) INTO col_exists;

    IF NOT col_exists THEN
        RAISE EXCEPTION
            'Cannot add freights_source_uid_uq: column public.freights.source_uid does not exist';
    END IF;

    -- 2) Проверяем, нет ли дубликатов по source_uid (кроме NULL)
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT source_uid
        FROM public.freights
        WHERE source_uid IS NOT NULL
        GROUP BY source_uid
        HAVING COUNT(*) > 1
    ) t;

    IF dup_count > 0 THEN
        RAISE EXCEPTION
            'Cannot add freights_source_uid_uq: found % duplicate source_uid values in public.freights',
            dup_count;
    END IF;

    -- 3) Добавляем constraint, только если его ещё нет
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND t.relname = 'freights'
          AND c.conname = 'freights_source_uid_uq'
    ) THEN
        ALTER TABLE public.freights
            ADD CONSTRAINT freights_source_uid_uq UNIQUE (source_uid);
    END IF;
END
$$;
