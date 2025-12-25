-- 20251206_analytics_devfactory_external_kpi_v1.sql
-- stack=sql
-- goal=Создать KPI-вьюху для задач DevFactory во внешних проектах.
-- summary=Создаёт analytics.devfactory_external_task_kpi_v1 поверх dev.dev_task, с авто-определением ключевых колонок.

-- На всякий случай создаём схему analytics, если её ещё нет
CREATE SCHEMA IF NOT EXISTS analytics;

DO $$
DECLARE
    v_has_table    boolean;

    v_project_col  text;
    v_status_col   text;
    v_created_col  text;
    v_completed_col text;

    v_lead_expr    text;
    v_sql          text;
BEGIN
    -- Проверяем, что таблица dev.dev_task существует
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_task'
    )
    INTO v_has_table;

    IF NOT v_has_table THEN
        RAISE NOTICE 'DevFactory KPI: table dev.dev_task not found, skipping analytics.devfactory_external_task_kpi_v1.';
        RETURN;
    END IF;

    -- Ищем колонку "проект" (project_ref / project_code / что-то с project)
    SELECT c.column_name
    INTO v_project_col
    FROM information_schema.columns c
    WHERE c.table_schema = 'dev'
      AND c.table_name   = 'dev_task'
      AND (
            c.column_name = 'project_ref'
         OR c.column_name = 'project_code'
         OR c.column_name ILIKE 'project_%'
         OR c.column_name ILIKE '%_project'
         OR c.column_name ILIKE '%project%'
      )
    ORDER BY CASE
        WHEN c.column_name = 'project_ref'  THEN 1
        WHEN c.column_name = 'project_code' THEN 2
        WHEN c.column_name ILIKE 'project_%' THEN 3
        WHEN c.column_name ILIKE '%_project' THEN 4
        ELSE 5
    END
    LIMIT 1;

    -- Ищем колонку статуса (status / task_status / что-то с status)
    SELECT c.column_name
    INTO v_status_col
    FROM information_schema.columns c
    WHERE c.table_schema = 'dev'
      AND c.table_name   = 'dev_task'
      AND (
            c.column_name = 'status'
         OR c.column_name = 'task_status'
         OR c.column_name ILIKE '%status%'
      )
    ORDER BY CASE
        WHEN c.column_name = 'status'       THEN 1
        WHEN c.column_name = 'task_status'  THEN 2
        ELSE 3
    END
    LIMIT 1;

    -- Ищем колонку "создано" (created_at / created_ts / created / inserted_at)
    SELECT c.column_name
    INTO v_created_col
    FROM information_schema.columns c
    WHERE c.table_schema = 'dev'
      AND c.table_name   = 'dev_task'
      AND (
            c.column_name = 'created_at'
         OR c.column_name = 'created_ts'
         OR c.column_name = 'created'
         OR c.column_name = 'inserted_at'
         OR c.column_name ILIKE 'created_%'
      )
    ORDER BY CASE
        WHEN c.column_name = 'created_at'   THEN 1
        WHEN c.column_name = 'created_ts'   THEN 2
        WHEN c.column_name = 'created'      THEN 3
        WHEN c.column_name = 'inserted_at'  THEN 4
        ELSE 5
    END
    LIMIT 1;

    IF v_project_col IS NULL OR v_status_col IS NULL OR v_created_col IS NULL THEN
        RAISE NOTICE 'DevFactory KPI: required columns (project/status/created) not found in dev.dev_task, skipping KPI view.';
        RETURN;
    END IF;

    -- Ищем колонку завершения (completed_at / finished_at / done_at)
    SELECT c.column_name
    INTO v_completed_col
    FROM information_schema.columns c
    WHERE c.table_schema = 'dev'
      AND c.table_name   = 'dev_task'
      AND c.column_name IN ('completed_at', 'finished_at', 'done_at')
    ORDER BY CASE c.column_name
                 WHEN 'completed_at' THEN 1
                 WHEN 'finished_at' THEN 2
                 ELSE 3
             END
    LIMIT 1;

    IF v_completed_col IS NOT NULL THEN
        v_lead_expr := format('avg(%I - %I)', v_completed_col, v_created_col);
    ELSE
        v_lead_expr := 'NULL::interval';
    END IF;

    v_sql := format($fmt$
        CREATE OR REPLACE VIEW analytics.devfactory_external_task_kpi_v1 AS
        SELECT
            %1$I AS project_ref,
            %2$I::date AS task_date,
            count(*) AS tasks_total,
            count(*) FILTER (WHERE %3$I = 'done')   AS tasks_done,
            count(*) FILTER (WHERE %3$I = 'failed') AS tasks_failed,
            %4$s AS avg_lead_time
        FROM dev.dev_task
        GROUP BY %1$I, %2$I::date;
    $fmt$, v_project_col, v_created_col, v_status_col, v_lead_expr);

    EXECUTE v_sql;

    RAISE NOTICE
        'analytics.devfactory_external_task_kpi_v1 created/updated (project_col=%, status_col=%, created_col=%)',
        v_project_col, v_status_col, v_created_col;
END;
$$ LANGUAGE plpgsql;
