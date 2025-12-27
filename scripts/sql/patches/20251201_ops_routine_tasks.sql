-- 20251201_ops_routine_tasks.sql
-- FoxProFlow — реестр рутинных задач (ops.routine_tasks)
-- NDC: только новая схема/таблица/индексы/триггеры, ничего не дропаем.

CREATE SCHEMA IF NOT EXISTS ops;

-- Базовая структура (для чистой БД)
CREATE TABLE IF NOT EXISTS ops.routine_tasks (
    id               bigserial PRIMARY KEY,
    code             text UNIQUE NOT NULL,          -- 'etl_ati_cycle', 'geo_refresh', 'autoplan_daily_report'
    description      text        NOT NULL,
    script_hint      text,                          -- tools/ff-*.ps1 или Celery task name
    frequency        text        NOT NULL,          -- 'daily', 'hourly', 'weekly', 'monthly', 'ad_hoc'
    manual_time_min  integer     NOT NULL DEFAULT 5,
    automated        boolean     NOT NULL DEFAULT false,
    notes            jsonb       NOT NULL DEFAULT '{}'::jsonb,
    category         text        NOT NULL DEFAULT 'generic',  -- etl/geo/autoplan/kpi/reporting/security/docs/other
    active           boolean     NOT NULL DEFAULT true,       -- можно выключить, не удаляя
    owner            text,                                    -- ответственный (человек или агент)
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- Дообновление, если таблица уже была создана в более простой версии
ALTER TABLE IF EXISTS ops.routine_tasks
    ADD COLUMN IF NOT EXISTS category   text    NOT NULL DEFAULT 'generic',
    ADD COLUMN IF NOT EXISTS active     boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS owner      text;

-- Комментарии
COMMENT ON TABLE  ops.routine_tasks IS
  'Реестр рутинных задач (из FF_Routine_Backlog), основа для агентов и Max Automation.';

COMMENT ON COLUMN ops.routine_tasks.id              IS 'Суррогатный ключ.';
COMMENT ON COLUMN ops.routine_tasks.code            IS 'Уникальный код задачи (etl_ati_cycle, geo_refresh, autoplan_daily_report и т.п.).';
COMMENT ON COLUMN ops.routine_tasks.description     IS 'Человеко-понятное описание рутины.';
COMMENT ON COLUMN ops.routine_tasks.script_hint     IS 'Подсказка: какой скрипт/таску дергает эта рутина (tools/ff-*.ps1 или Celery task name).';
COMMENT ON COLUMN ops.routine_tasks.frequency       IS 'Частота: hourly/daily/weekly/monthly/ad_hoc.';
COMMENT ON COLUMN ops.routine_tasks.manual_time_min IS 'Оценка ручного времени (в минутах) на один цикл выполнения.';
COMMENT ON COLUMN ops.routine_tasks.automated       IS 'True = уже автоматизировано скриптом/агентом.';
COMMENT ON COLUMN ops.routine_tasks.notes           IS 'Произвольные метаданные (JSONB), например agent_candidate, risk_level.';
COMMENT ON COLUMN ops.routine_tasks.category        IS 'Категория: etl/geo/autoplan/kpi/reporting/security/docs/other.';
COMMENT ON COLUMN ops.routine_tasks.active          IS 'Флаг активности задачи (false = задачу больше не ведём).';
COMMENT ON COLUMN ops.routine_tasks.owner           IS 'Ответственный (человек или агент), например evgeniy, ETLFox.';
COMMENT ON COLUMN ops.routine_tasks.created_at      IS 'Когда задача была впервые занесена в реестр.';
COMMENT ON COLUMN ops.routine_tasks.updated_at      IS 'Когда задача последний раз редактировалась.';

-- Индекс для быстрых выборок по частоте и автоматизации
CREATE INDEX IF NOT EXISTS routine_tasks_freq_auto_idx
    ON ops.routine_tasks (frequency, automated);

-- Индекс по активным задачам (для планирования автоматизации)
CREATE INDEX IF NOT EXISTS routine_tasks_active_idx
    ON ops.routine_tasks (active, automated, category);

-- Ограничение на ручное время (неотрицательное), idempotent
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conname = 'routine_tasks_manual_time_min_nonneg'
        AND    conrelid = 'ops.routine_tasks'::regclass
    ) THEN
        ALTER TABLE ops.routine_tasks
        ADD CONSTRAINT routine_tasks_manual_time_min_nonneg
        CHECK (manual_time_min >= 0);
    END IF;
END$$;

-- Триггер на updated_at
CREATE OR REPLACE FUNCTION ops.tg_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    -- если таблица существует, пересоздаём триггер (идемпотентно)
    IF to_regclass('ops.routine_tasks') IS NOT NULL THEN
        BEGIN
            DROP TRIGGER IF EXISTS tg_routine_tasks_set_updated_at ON ops.routine_tasks;
        EXCEPTION
            WHEN undefined_table THEN
                NULL;
        END;

        CREATE TRIGGER tg_routine_tasks_set_updated_at
        BEFORE UPDATE ON ops.routine_tasks
        FOR EACH ROW
        EXECUTE FUNCTION ops.tg_set_updated_at();
    END IF;
END$$;
