-- 20251208_dev_devfactory_dev_task_fix_v1.sql
-- NDC-патч: доводим структуру dev.dev_task до схемы, ожидаемой DevFactory.
-- Добавляем колонки error и links, если их нет.

DO $$
BEGIN
    -- Если таблицы dev.dev_task нет, выходим: её создаёт 20251204_dev_devfactory_schema_v1.sql.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_task'
    ) THEN
        RETURN;
    END IF;

    -- Колонка error text (описание ошибки / stacktrace)
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'dev'
      AND table_name   = 'dev_task'
      AND column_name  = 'error';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE dev.dev_task ADD COLUMN error text';
    END IF;

    -- Колонка links jsonb (доп. ссылки/метаданные), по умолчанию пустой объект
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'dev'
      AND table_name   = 'dev_task'
      AND column_name  = 'links';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE dev.dev_task ADD COLUMN links jsonb NOT NULL DEFAULT ''{}''::jsonb';
    END IF;
END;
$$ LANGUAGE plpgsql;
