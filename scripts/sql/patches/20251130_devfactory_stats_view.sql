-- DevFactory: агрегированная статистика по задачам
-- Используем обычное VIEW поверх dev.devfactory_task_results_mv,
-- чтобы не плодить дополнительные REFRESH-циклы.

CREATE SCHEMA IF NOT EXISTS dev;

CREATE OR REPLACE VIEW dev.devfactory_task_stats_v AS
SELECT
    r.stack,
    r.patch_type,
    r.status,
    r.has_error,
    count(*)                                                   AS tasks_count,
    count(*) FILTER (WHERE r.changed_files_count > 0)          AS tasks_with_changes,
    max(r.created_at)                                          AS last_task_created_at
FROM dev.devfactory_task_results_mv AS r
GROUP BY
    r.stack,
    r.patch_type,
    r.status,
    r.has_error;

COMMENT ON VIEW dev.devfactory_task_stats_v IS
    'Агрегированная статистика DevFactory по стеку, статусу, типу патча и наличию ошибок.';
