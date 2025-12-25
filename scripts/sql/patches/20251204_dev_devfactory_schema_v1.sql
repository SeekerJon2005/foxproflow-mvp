-- 20251204_dev_devfactory_schema_v1.sql
-- Базовая схема DevFactory: dev.dev_task + индексы и триггер updated_at.
-- NDC-патч: создаём только то, чего ещё нет.

DO $$
BEGIN
    --------------------------------------------------------------------------
    -- 1. Схема dev
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'dev'
    ) THEN
        EXECUTE 'CREATE SCHEMA dev';
    END IF;

    --------------------------------------------------------------------------
    -- 2. Таблица dev.dev_task
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'dev'
          AND c.relkind = 'r'
          AND c.relname = 'dev_task'
    ) THEN
        CREATE TABLE dev.dev_task (
            id              bigserial PRIMARY KEY,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),

            -- Статус жизненного цикла задачи DevFactory:
            -- new | in_progress | proposed | applied | rejected | failed | archived ...
            status          text NOT NULL DEFAULT 'new'
                               CHECK (length(trim(status)) > 0),

            -- Стек (по DevFactory Governance): python_backend | sql | docs | infra | flowlang | ...
            stack           text NOT NULL
                               CHECK (length(trim(stack)) > 0),

            -- Область системы: logistics | crm | devfactory | observability | tpm | ...
            scope           text,

            -- Источник задачи: architect | user | agent | observability | external_contract | ...
            source          text,

            -- Краткое описание цели задачи
            title           text,

            -- Приоритет (0 = дефолт, больше = важнее)
            priority        integer NOT NULL DEFAULT 0,

            -- Структурированное описание входа (input_spec v0.x):
            -- что именно нужно изменить/создать, контекст, ограничения.
            input_spec      jsonb,

            -- Полный result_spec v0.3 (патчи, анализ и т.п.)
            result_spec     jsonb,

            -- Последняя ошибка (если есть) в человекочитаемом виде
            last_error      text,

            -- Дополнительная мета-информация / связи:
            -- ссылки на CRM, репозиторий, внешние задачи и т.п.
            meta            jsonb
        );

        COMMENT ON TABLE dev.dev_task IS
            'Базовая сущность DevFactory: задача разработки (stack, scope, status, input_spec/result_spec).';

        COMMENT ON COLUMN dev.dev_task.created_at IS
            'Момент создания задачи DevFactory.';

        COMMENT ON COLUMN dev.dev_task.updated_at IS
            'Последнее обновление записи (меняется триггером при UPDATE).';

        COMMENT ON COLUMN dev.dev_task.status IS
            'Жизненный цикл задачи: new, in_progress, proposed, applied, rejected, failed, archived и т.п.';

        COMMENT ON COLUMN dev.dev_task.stack IS
            'Целевой стек задачи DevFactory: python_backend, sql, docs, infra, flowlang и т.п.';

        COMMENT ON COLUMN dev.dev_task.scope IS
            'Функциональная область FoxProFlow: logistics, crm, devfactory, observability, tpm и т.п.';

        COMMENT ON COLUMN dev.dev_task.source IS
            'Источник задачи: architect, user, agent, observability, external_contract и т.п.';

        COMMENT ON COLUMN dev.dev_task.title IS
            'Краткое человекочитаемое описание задачи.';

        COMMENT ON COLUMN dev.dev_task.priority IS
            'Приоритет задачи (0 = дефолт, выше = важнее).';

        COMMENT ON COLUMN dev.dev_task.input_spec IS
            'Структурированное описание входа (что нужно сделать, контекст, ограничения).';

        COMMENT ON COLUMN dev.dev_task.result_spec IS
            'Структурированный результат DevFactory (патчи, анализ, статус выполнения).';

        COMMENT ON COLUMN dev.dev_task.last_error IS
            'Последняя ошибка при обработке задачи (если есть).';

        COMMENT ON COLUMN dev.dev_task.meta IS
            'Дополнительная мета-информация: связи с внешними сущностями, теги, ссылки.';

        -- Базовые индексы для типичных запросов DevFactory:
        CREATE INDEX dev_task_status_idx      ON dev.dev_task(status);
        CREATE INDEX dev_task_stack_idx       ON dev.dev_task(stack);
        CREATE INDEX dev_task_created_at_idx  ON dev.dev_task(created_at);
    END IF;

    --------------------------------------------------------------------------
    -- 3. Функция-триггер для updated_at
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'dev'
          AND p.proname = 'set_updated_at_dev_task'
    ) THEN
        CREATE FUNCTION dev.set_updated_at_dev_task()
        RETURNS trigger AS $f$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $f$ LANGUAGE plpgsql;
    END IF;

    --------------------------------------------------------------------------
    -- 4. Триггер updated_at для dev.dev_task
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c       ON c.oid = t.tgrelid
        JOIN pg_namespace n   ON n.oid = c.relnamespace
        WHERE n.nspname = 'dev'
          AND c.relname = 'dev_task'
          AND t.tgname = 'trg_dev_task_set_updated_at'
          AND NOT t.tgisinternal
    ) THEN
        CREATE TRIGGER trg_dev_task_set_updated_at
        BEFORE UPDATE ON dev.dev_task
        FOR EACH ROW
        EXECUTE FUNCTION dev.set_updated_at_dev_task();
    END IF;
END;
$$ LANGUAGE plpgsql;
