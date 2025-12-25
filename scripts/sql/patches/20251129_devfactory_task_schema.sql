-- Схема задач DevFactory
-- NDC: только CREATE IF NOT EXISTS.

CREATE SCHEMA IF NOT EXISTS dev;

CREATE TABLE IF NOT EXISTS dev.dev_task (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    status       text        NOT NULL DEFAULT 'new',   -- new / in_progress / done / failed / cancelled
    source       text        NOT NULL DEFAULT 'architect',
    stack        text        NOT NULL,                 -- python_backend / sql / tests / docs / powershell / etc.
    title        text,
    input_spec   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    result_spec  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    error        text,
    links        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE dev.dev_task IS
    'Атомарные задачи DevFactory (описание цели, стека и результатов).';

CREATE INDEX IF NOT EXISTS idx_dev_task_status_created_at
    ON dev.dev_task (status, created_at DESC);
