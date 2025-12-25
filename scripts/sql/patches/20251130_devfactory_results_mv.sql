-- DevFactory: витрина результатов задач
-- NDC: только add-only, без DROP/ALTER.

CREATE SCHEMA IF NOT EXISTS dev;

CREATE MATERIALIZED VIEW IF NOT EXISTS dev.devfactory_task_results_mv AS
SELECT
    t.id,
    t.created_at,
    t.updated_at,
    t.source,
    t.stack,
    t.status,
    t.title,
    -- Плоские поля из result_spec v0.3
    COALESCE(t.result_spec->>'version',      '')        AS version,
    COALESCE(t.result_spec->>'patch_type',   '')        AS patch_type,
    COALESCE(t.result_spec->>'target_file',  '')        AS target_file,
    COALESCE(t.result_spec->>'summary',      '')        AS summary,
    COALESCE(t.result_spec->>'goal',         '')        AS goal,
    -- Сколько файлов реально помечено как changed_files
    COALESCE(jsonb_array_length(t.result_spec->'changed_files'), 0)
        AS changed_files_count,
    -- Флаги удобства
    (t.result_spec ? 'patch')                AS has_patch,
    (t.error IS NOT NULL)                    AS has_error,
    t.error
FROM dev.dev_task AS t;

COMMENT ON MATERIALIZED VIEW dev.devfactory_task_results_mv IS
    'Материализованная витрина задач DevFactory: статус, стек, патч, ошибки.';

CREATE UNIQUE INDEX IF NOT EXISTS devfactory_task_results_mv_pk
    ON dev.devfactory_task_results_mv (id);

CREATE INDEX IF NOT EXISTS devfactory_task_results_mv_stack_status_created_at
    ON dev.devfactory_task_results_mv (stack, status, created_at DESC);

-- Утилитарная функция для обновления витрины (используем в Celery)
CREATE OR REPLACE FUNCTION dev.refresh_devfactory_task_results_mv()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    -- можно вызывать CONCURRENTLY снаружи, но в функции используем обычный REFRESH
    REFRESH MATERIALIZED VIEW dev.devfactory_task_results_mv;
END;
$$;

COMMENT ON FUNCTION dev.refresh_devfactory_task_results_mv() IS
    'Обновляет витрину dev.devfactory_task_results_mv.';
