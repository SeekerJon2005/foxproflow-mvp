-- DevFactory: суточные KPI по задачам
-- Источник данных: dev.devfactory_task_stats_v (агрегаты по стеку/типу патч/статусу)

CREATE SCHEMA IF NOT EXISTS dev;

CREATE TABLE IF NOT EXISTS dev.devfactory_kpi_daily (
    dt                  date PRIMARY KEY,
    tasks_total         integer      NOT NULL,
    tasks_with_changes  integer      NOT NULL,
    stacks              jsonb        NOT NULL,
    created_at          timestamptz  NOT NULL DEFAULT now(),
    updated_at          timestamptz  NOT NULL DEFAULT now()
);

COMMENT ON TABLE dev.devfactory_kpi_daily IS
    'Суточные KPI DevFactory: количество задач и агрегаты по стекам/типам патчей.';

COMMENT ON COLUMN dev.devfactory_kpi_daily.dt IS 'Дата, к которой относятся показатели.';
COMMENT ON COLUMN dev.devfactory_kpi_daily.tasks_total IS 'Общее количество задач DevFactory на момент среза.';
COMMENT ON COLUMN dev.devfactory_kpi_daily.tasks_with_changes IS 'Количество задач, у которых changed_files_count > 0.';
COMMENT ON COLUMN dev.devfactory_kpi_daily.stacks IS
    'JSONB-агрегаты по dev.devfactory_task_stats_v (stack, patch_type, status, has_error, tasks_count, tasks_with_changes, last_task_created_at).';

-- Функция суточного обновления KPI на указанную дату
CREATE OR REPLACE FUNCTION dev.refresh_devfactory_kpi_daily(p_dt date)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_total         integer;
    v_with_changes  integer;
    v_stacks        jsonb;
BEGIN
    -- Берём текущую агрегированную статистику из dev.devfactory_task_stats_v
    SELECT
        COALESCE(SUM(tasks_count), 0),
        COALESCE(SUM(tasks_with_changes), 0),
        COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'stack',                stack,
                    'patch_type',           patch_type,
                    'status',               status,
                    'has_error',            has_error,
                    'tasks_count',          tasks_count,
                    'tasks_with_changes',   tasks_with_changes,
                    'last_task_created_at', last_task_created_at
                )
                ORDER BY stack, patch_type, status, has_error
            ),
            '[]'::jsonb
        )
    INTO v_total, v_with_changes, v_stacks
    FROM dev.devfactory_task_stats_v;

    INSERT INTO dev.devfactory_kpi_daily (
        dt,
        tasks_total,
        tasks_with_changes,
        stacks,
        created_at,
        updated_at
    )
    VALUES (
        p_dt,
        v_total,
        v_with_changes,
        v_stacks,
        now(),
        now()
    )
    ON CONFLICT (dt) DO UPDATE
      SET tasks_total        = EXCLUDED.tasks_total,
          tasks_with_changes = EXCLUDED.tasks_with_changes,
          stacks             = EXCLUDED.stacks,
          updated_at         = now();
END;
$$;

COMMENT ON FUNCTION dev.refresh_devfactory_kpi_daily(date) IS
    'Пересчитывает суточные KPI DevFactory (dev.devfactory_kpi_daily) на указанную дату.';
