-- 20251204_analytics_devfactory_kpi_v1.sql
-- Витрины по задачам DevFactory:
--  - analytics.devfactory_tasks_overview_v  — плоский срез по задачам;
--  - analytics.devfactory_kpi_daily_v      — дневные KPI по стекам.
-- NDC-патч: создаём только то, чего ещё нет.

DO $$
BEGIN
    --------------------------------------------------------------------------
    -- 1. Схема analytics
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_namespace
        WHERE nspname = 'analytics'
    ) THEN
        EXECUTE 'CREATE SCHEMA analytics';
    END IF;

    --------------------------------------------------------------------------
    -- 2. Вьюха analytics.devfactory_tasks_overview_v
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'analytics'
          AND c.relkind = 'v'
          AND c.relname = 'devfactory_tasks_overview_v'
    ) THEN
        EXECUTE $v$
        CREATE VIEW analytics.devfactory_tasks_overview_v AS
        SELECT
            t.id,
            t.created_at,
            t.updated_at,
            t.status,
            t.source,
            t.stack,
            t.title,
            t.input_spec,
            t.result_spec,
            t.error,
            t.links,

            -- Удобные вычисляемые поля
            (t.status = 'new')    AS is_new,
            (t.status = 'done')   AS is_done,
            (t.status = 'failed') AS is_failed,

            -- Возраст задачи с момента создания (в секундах)
            EXTRACT(EPOCH FROM (now() - t.created_at))::bigint AS age_sec,

            -- Длительность выполнения (от created_at до updated_at) для завершённых задач
            CASE
                WHEN t.status IN ('done', 'failed') THEN
                    EXTRACT(EPOCH FROM (t.updated_at - t.created_at))::bigint
                ELSE
                    NULL
            END AS duration_sec
        FROM dev.dev_task t;

        COMMENT ON VIEW analytics.devfactory_tasks_overview_v IS
            'Плоский срез по задачам DevFactory (dev.dev_task) с базовыми вычисляемыми полями: возраст, длительность, флаги статусов.';
        $v$;
    END IF;

    --------------------------------------------------------------------------
    -- 3. Вьюха analytics.devfactory_kpi_daily_v
    --------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'analytics'
          AND c.relkind = 'v'
          AND c.relname = 'devfactory_kpi_daily_v'
    ) THEN
        EXECUTE $v$
        CREATE VIEW analytics.devfactory_kpi_daily_v AS
        WITH base AS (
            SELECT
                date(t.created_at) AS kpi_date,
                t.stack,
                t.status,
                -- длительность только для завершённых задач
                CASE
                    WHEN t.status IN ('done', 'failed') THEN
                        EXTRACT(EPOCH FROM (t.updated_at - t.created_at))::bigint
                    ELSE
                        NULL
                END AS duration_sec
            FROM dev.dev_task t
        )
        SELECT
            b.kpi_date,
            b.stack,

            COUNT(*)                                  AS total_tasks,
            COUNT(*) FILTER (WHERE status = 'new')    AS new_tasks,
            COUNT(*) FILTER (WHERE status = 'done')   AS done_tasks,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed_tasks,

            -- Средняя длительность выполнения по завершённым задачам (секунды)
            AVG(duration_sec) FILTER (WHERE duration_sec IS NOT NULL) AS avg_duration_sec,

            -- Медиану можно добавить позже отдельной витриной, чтобы не усложнять view
            MIN(duration_sec) FILTER (WHERE duration_sec IS NOT NULL) AS min_duration_sec,
            MAX(duration_sec) FILTER (WHERE duration_sec IS NOT NULL) AS max_duration_sec
        FROM base b
        GROUP BY
            b.kpi_date,
            b.stack
        ORDER BY
            b.kpi_date,
            b.stack;

        COMMENT ON VIEW analytics.devfactory_kpi_daily_v IS
            'Дневные KPI по задачам DevFactory: количество задач по статусам и базовые метрики длительности выполнения по стекам.';
        $v$;
    END IF;
END;
$$ LANGUAGE plpgsql;
