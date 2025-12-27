-- 20251208_dev_devfactory_add_public_uuid_v1.sql
-- Добавляем устойчивый UUID-идентификатор public_id в dev.dev_task.
-- id (bigint) остаётся как внутренний тех.ключ.

DO $$
BEGIN
    -- Если таблицы dev.dev_task нет, выходим: её создаёт DevFactory schema v1.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_task'
    ) THEN
        RETURN;
    END IF;

    -- Подключаем pgcrypto для gen_random_uuid(), если ещё не подключен.
    PERFORM 1
    FROM pg_extension
    WHERE extname = 'pgcrypto';

    IF NOT FOUND THEN
        BEGIN
            CREATE EXTENSION pgcrypto;
        EXCEPTION WHEN duplicate_object THEN
            -- уже подключено — ок
            NULL;
        END;
    END IF;

    -- Добавляем public_id, если его нет.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_task'
          AND column_name  = 'public_id'
    ) THEN
        ALTER TABLE dev.dev_task
            ADD COLUMN public_id uuid;

        -- Заполняем существующие строки
        UPDATE dev.dev_task
           SET public_id = gen_random_uuid()
         WHERE public_id IS NULL;

        ALTER TABLE dev.dev_task
            ALTER COLUMN public_id SET NOT NULL;

        -- Уникальный индекс по UUID
        CREATE UNIQUE INDEX dev_task_public_id_uidx
            ON dev.dev_task (public_id);
    END IF;
END;
$$ LANGUAGE plpgsql;
