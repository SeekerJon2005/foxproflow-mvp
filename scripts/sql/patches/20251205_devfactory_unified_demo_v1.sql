-- 20251205_devfactory_unified_demo_v1.sql
-- NDC-патч: создаёт VIEW dev.devfactory_unified_demo_v1, если его ещё нет.
-- DevFactory unified_diff demo v0.2
-- stack=sql
-- goal=Протестировать ff-dev-task-new-unidiff.ps1 (SQL unified_diff)
-- summary=DevFactory: unified_diff demo v0.2

DO $$
BEGIN
    -- Проверяем, нет ли уже такого VIEW
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_catalog.pg_class c
        JOIN   pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE  n.nspname = 'dev'
        AND    c.relname = 'devfactory_unified_demo_v1'
        AND    c.relkind = 'v'  -- view
    ) THEN
        EXECUTE $view$
            CREATE VIEW dev.devfactory_unified_demo_v1 AS
            SELECT
                t.id,
                t.created_at,
                t.updated_at,
                t.status,
                t.source,
                t.stack,
                t.title,
                t.project_ref,
                t.input_spec,
                t.result_spec,
                (t.input_spec->>'patch_type')::text              AS input_patch_type,
                (t.result_spec->>'patch_type')::text             AS result_patch_type,
                (t.result_spec->'safety'->>'ok')::boolean        AS safety_ok,
                (t.result_spec->'safety'->>'checked')::boolean   AS safety_checked,
                t.result_spec->'safety'->'violations'            AS safety_violations
            FROM dev.dev_task t
            WHERE t.result_spec->>'patch_type' = 'unified_diff_v1';
        $view$;
    END IF;
END $$;
