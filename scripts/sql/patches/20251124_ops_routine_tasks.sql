-- 2025-11-24 — FoxProFlow
-- Реестр рутинных задач (кандидаты в агентов и расписание).
-- NDC: только CREATE ... IF NOT EXISTS и COMMENT/INDEX (без ALTER/DROP).

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.routine_tasks (
    id              bigserial PRIMARY KEY,
    code            text UNIQUE NOT NULL,          -- 'etl_ati_cycle', 'geo_refresh', 'autoplan_daily'
    description     text        NOT NULL,          -- человеческое описание
    script_hint     text,                          -- tools/ff-*.ps1 или Celery task name
    frequency       text        NOT NULL,          -- 'daily', 'hourly', 'weekly', 'monthly', 'ad_hoc'
    manual_time_min integer     NOT NULL DEFAULT 5,
    automated       boolean     NOT NULL DEFAULT false,
    notes           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Комментарии для удобства навигации по схеме

COMMENT ON TABLE ops.routine_tasks IS
    'Реестр рутинных задач (ручных/автоматизированных) для агентов FoxProFlow.';

COMMENT ON COLUMN ops.routine_tasks.code IS
    'Короткий код задачи: etl_ati_cycle, geo_refresh, autoplan_daily и т.п.';

COMMENT ON COLUMN ops.routine_tasks.description IS
    'Человеческое описание задачи (что делает, в каком контуре).';

COMMENT ON COLUMN ops.routine_tasks.script_hint IS
    'Подсказка: tools/ff-*.ps1, Celery-task, команда или другой запускной артефакт.';

COMMENT ON COLUMN ops.routine_tasks.frequency IS
    'Ожидаемая частота: daily/hourly/weekly/monthly/ad_hoc.';

COMMENT ON COLUMN ops.routine_tasks.manual_time_min IS
    'Оценка длительности ручного выполнения задачи (в минутах).';

COMMENT ON COLUMN ops.routine_tasks.automated IS
    'Флаг: задача уже автоматизирована (true) или пока выполняется вручную (false).';

COMMENT ON COLUMN ops.routine_tasks.notes IS
    'Дополнительные параметры задачи в формате jsonb (labels, владелец, agent-кандидат и т.п.).';

COMMENT ON COLUMN ops.routine_tasks.created_at IS
    'Время создания записи о задаче.';

COMMENT ON COLUMN ops.routine_tasks.updated_at IS
    'Время последнего обновления записи о задаче.';

-- Индексы для типовых выборок (частота/автоматизация)

CREATE INDEX IF NOT EXISTS idx_routine_tasks_frequency
    ON ops.routine_tasks (frequency);

CREATE INDEX IF NOT EXISTS idx_routine_tasks_automated
    ON ops.routine_tasks (automated);
