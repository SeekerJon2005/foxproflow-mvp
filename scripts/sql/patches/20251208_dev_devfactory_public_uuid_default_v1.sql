-- 20251208_dev_devfactory_public_uuid_default_v1.sql
-- Добавляем default gen_random_uuid() для dev.dev_task.public_id,
-- чтобы новые строки автоматически получали UUID.

DO $$
BEGIN
    -- Если таблицы dev.dev_task нет — выходим.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_task'
    ) THEN
        RETURN;
    END IF;

    -- Убеждаемся, что есть расширение pgcrypto (gen_random_uuid)
    PERFORM 1
    FROM pg_extension
    WHERE extname = 'pgcrypto';

    IF NOT FOUND THEN
        BEGIN
            CREATE EXTENSION pgcrypto;
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END;
    END IF;

    -- Ставим default, если его ещё нет
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'dev'
      AND table_name   = 'dev_task'
      AND column_name  = 'public_id'
      AND column_default IS NOT NULL;

    IF NOT FOUND THEN
        ALTER TABLE dev.dev_task
            ALTER COLUMN public_id SET DEFAULT gen_random_uuid();
    END IF;
END;
$$ LANGUAGE plpgsql;
